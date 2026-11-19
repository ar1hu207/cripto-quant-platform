# -*- coding: utf-8 -*-
"""Fixtures da suite. Herda o padrao que o `prova_m1.py` estabeleceu: banco TEMPORARIO
via `DB_PATH`, e `preco_ao_vivo` trocado por funcao local para nao existir rede.

Duas travas de seguranca, nesta ordem:

1. `DB_PATH` e apontado para um diretorio temporario ANTES do primeiro `import db`, porque
   `db.DB` e resolvido no import (db.py:12). Sem isto, um teste que esquecesse a fixture
   escreveria no `trading.db` da raiz -- que aqui esta vazio, mas na VM e o historico de
   pesquisa inteiro (CLAUDE.md, cabecalho).
2. A fixture `banco` reaponta `db.DB` para um arquivo POR TESTE e restaura no fim. E
   reatribuicao de global mesmo, e nao monkeypatch de objeto, porque `conectar()` le o
   global a cada chamada -- que e o mesmo mecanismo que `db._prova_p2_11` e
   `simulador._prova_funding` ja usam.
"""
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
# Atribuicao INCONDICIONAL, e nao `setdefault`: num shell com o `.env` do servidor carregado o
# `DB_PATH` ja existe e apontaria a suite para o banco vivo. O mesmo vale para o log (a suite
# gravava no `plataforma.log` da raiz, que no servidor e o log vivo da conta A, com um segundo
# handler girando o mesmo arquivo) e para a senha (`api.DASH_PASS` e lido no import: com ela
# exportada, toda fixture de TestClient levava 401).
_TMP = tempfile.mkdtemp(prefix="pytest_cripto_")
os.environ["DB_PATH"] = os.path.join(_TMP, "guarda.db")
os.environ["LOG_PATH"] = os.path.join(_TMP, "plataforma.log")
os.environ.pop("DASH_PASS", None)

import pytest                                                    # noqa: E402

import db                                                        # noqa: E402
import simulador                                                 # noqa: E402
import tendencia                                                 # noqa: E402
import dvol                                                      # noqa: E402


@pytest.fixture(autouse=True)
def _diario_sem_rede(monkeypatch):
    """[CD-1] O scan passou a ler o diario do ativo para ANOTAR o sinal
    (`signal_engine._anotar_diario`), e essa leitura e rede de verdade (`mercado.ex_spot`), por
    um caminho que os dubles de `signal_engine.ex` nao cobrem. Sem isto, todo teste que roda o
    scan e grava um sinal falaria com a Binance -- lento, e verde ou vermelho conforme a rede
    do dia. Aqui o diario FALHA por padrao, que e o caso que o scan trata gravando NULL; quem
    precisa de diario (tests/test_tendencia.py, tests/test_contexto_diario.py) troca
    `tendencia._velas_1d` pelo proprio duble, por cima deste."""
    def sem_diario(ativo):
        raise ConnectionError("suite: o diario nao sai para a rede")
    monkeypatch.setattr(tendencia, "_velas_1d", sem_diario)


@pytest.fixture(autouse=True)
def _dvol_sem_rede(monkeypatch):
    """[DV-1] O scan passou a ler o DVOL da Deribit para ANOTAR o sinal
    (`signal_engine._anotar_dvol`). Mesmo motivo do `_diario_sem_rede`: sem isto, todo teste que
    roda o scan falaria com a Deribit. Aqui a leitura FALHA por padrao (o scan grava NULL); quem
    precisa de DVOL (tests/test_dvol.py) troca `dvol._baixar` pelo proprio duble. O cache e
    zerado nos dois sentidos, porque ele vive no modulo e sobreviveria de um teste ao outro."""
    def sem_dvol(agora_ms):
        raise ConnectionError("suite: o DVOL nao sai para a rede")
    dvol._cache.clear()
    monkeypatch.setattr(dvol, "_baixar", sem_dvol)
    yield
    dvol._cache.clear()


@pytest.fixture
def banco(tmp_path):
    """Banco vazio, com esquema e config padrao, so deste teste."""
    original = db.DB
    db.DB = str(tmp_path / "t.db")
    db.init_db()
    try:
        yield db.DB
    finally:
        db.DB = original


@pytest.fixture
def sem_rede(monkeypatch):
    """Nenhuma chamada de mercado sai daqui.

    `preco_ao_vivo` vira funcao local (100.0 para todo ativo) e `ex_fut` vira um duble que
    devolve historico de funding vazio -- vazio e MEDICAO de zero, nao falha, entao
    `fechar()` grava funding 0.0 e o P&L do teste fica sendo so entrada/saida/taxa. Um duble
    que levantasse excecao tambem serviria, mas gravaria NULL e mudaria o que se mede aqui
    ([P2-10]; a falha de medicao tem prova propria em `simulador._prova_funding`).
    """
    class _SemFunding:
        def fetch_funding_rate_history(self, ativo, since=None, limit=None):
            return []

    monkeypatch.setattr(simulador, "preco_ao_vivo", lambda ativo: 100.0)
    monkeypatch.setattr(simulador, "ex_fut", _SemFunding())
    return lambda preco: monkeypatch.setattr(simulador, "preco_ao_vivo", lambda ativo: preco)


def semear_sinal(ativo="BTC/USDT", direcao="LONG", preco=100.0, stop=95.0,
                 conviccao=80, tf="15m", tipo="tendencia", status="novo", ts=None, motivos="x"):
    """Insere um sinal e devolve o id. Escrita direta: o caminho de producao passa pelo
    scan, que precisa de rede."""
    import pandas as pd
    ts = ts or str(pd.Timestamp.now())
    with db.conectar() as c:
        c.execute("INSERT INTO sinais(ts,ativo,tf,tipo,direcao,conviccao,motivos,preco,"
                  "stop_sugerido,status) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (ts, ativo, tf, tipo, direcao, conviccao, motivos, preco, stop, status))
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def semear_posicao(ativo="BTC/USDT", direcao="LONG", entrada=100.0, valor_reais=50.0,
                   alavancagem=2, stop=95.0, preco_atual=None, pnl=0.0, status="aberta",
                   aberto_em=None, conviccao=80):
    """Posicao aberta gravada direto no banco -- sem sinal, sem lock e sem rede. Usada
    quando o objeto do teste e o ESTADO (guarda_risco, metricas), nao o caminho de abertura."""
    import pandas as pd
    with db.conectar() as c:
        c.execute("INSERT INTO posicoes(ativo,direcao,entrada,valor_reais,alavancagem,stop,"
                  "preco_atual,pnl,aberto_em,status,conviccao) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (ativo, direcao, entrada, valor_reais, alavancagem, stop,
                   preco_atual if preco_atual is not None else entrada, pnl,
                   aberto_em or str(pd.Timestamp.now()), status, conviccao))
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def semear_equity(ts, equity_total):
    with db.conectar() as c:
        c.execute("INSERT INTO equity(ts,banca,equity_total) VALUES(?,?,?)",
                  (ts, equity_total, equity_total))
