# -*- coding: utf-8 -*-
"""Criterio 3 do [P2-6]: "cada bug corrigido nos cards P1 ganha um teste de regressao".

A maior parte ja tinha: `prova_m1.py` cobre P1-1, P1-6, P1-7 e P1-8, e `api._prova_api()`
cobre P1-4 -- as duas sao executadas pela suite em `test_provas_existentes.py`, e repetir as
asseracoes aqui seria duplicar regressao (a decisao 1 da §4c do plano). O que sobrava sem
nenhuma prova automatizada eram tres, e sao estes:

    P1-3  `/candles` e `/trades` sem teto no `limite`
    P1-5  `breadth()` contava o ativo antes de ter um numero dele
    P1-9  janela de vida do sinal, nas duas pontas (dedupe e expiracao)

Fica de fora, declarado: **P1-2** e uma linha em `web/index.html` (o
`localStorage.removeItem('cbAuth')`). E front, nao e Python, e `web/` nao e territorio do
T-TESTE -- a verificacao dele e por hash do HTML em producao (CLAUDE.md §7).
"""
import pandas as pd
import pytest

import db
import mercado
import signal_engine
from conftest import semear_sinal


# ================================================================ [P1-3] teto do `limite`

@pytest.fixture
def cliente(banco):
    """TestClient sem `with`: o `lifespan` -- e portanto a thread do worker -- nao sobe.

    `client=("127.0.0.1", ...)` porque o peer padrao do TestClient ("testclient") nao e
    loopback, e sem `DASH_PASS` o app responde 503 a tudo que venha de fora (o [P0-1]).
    Mesmo motivo, e mesma solucao, do `test_auth.py`.
    """
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app, client=("127.0.0.1", 5555))


@pytest.mark.parametrize("rota,limite", [
    ("/candles", 1001), ("/candles", 50000), ("/candles", 0), ("/candles", -1),
    ("/trades", 501), ("/trades", 0),
])
def test_limite_fora_da_faixa_e_recusado_na_borda(cliente, rota, limite):
    """[P1-3] O teto vive no `Query(..., ge=, le=)`, entao a recusa acontece ANTES de
    qualquer chamada a corretora ou ao banco -- por isso este teste nao precisa de rede.
    Sem o teto, `limite=50000` virava um fetch gigante (ou um 500 vindo do ccxt) disparado
    por quem so digitou um numero na URL."""
    assert cliente.get(f"{rota}?limite={limite}").status_code == 422


def test_o_limite_no_teto_ainda_e_valido(cliente):
    """A faixa e fechada: 500 passa na validacao (e ai sim vai ao banco, que esta vazio)."""
    r = cliente.get("/trades?limite=500")
    assert r.status_code == 200 and r.json() == []


# ================================================================ [P1-5] breadth()

@pytest.fixture
def ativos_fake(banco, monkeypatch):
    """Troca o unico ponto do modulo que fala com o ccxt. `_tickers` ja devolve so o que
    voltou da corretora -- o ativo ausente simplesmente nao esta no dicionario."""
    def usar(tickers, ativos=None):
        db.set_config("ativos", ",".join(ativos or tickers.keys()))
        monkeypatch.setattr(mercado, "_tickers", lambda lista: tickers)
    return usar


def test_leitura_ausente_fica_fora_dos_tres_contadores(ativos_fake):
    """[P1-5] O bug era `tot += 1` antes de `soma += p`: o ativo cujo `percentage` vinha
    None ja tinha entrado no denominador quando o TypeError caia no except, e distorcia
    `pct_subindo` e `variacao_media` para baixo. A regra que o comentario do codigo hoje
    declara e "daqui pra baixo o ativo entra nos tres contadores ou em nenhum"."""
    ativos_fake({"BTC/USDT": {"percentage": 2.0},
                 "ETH/USDT": {"percentage": -1.0},
                 "SOL/USDT": {"percentage": None}},
                ativos=["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"])
    b = mercado.breadth()
    assert b["n"] == 2                                  # SOL (None) e XRP (ausente) ficam fora
    assert b["pct_subindo"] == 50                       # 1 de 2, nao 1 de 4
    assert b["variacao_media"] == pytest.approx(0.5)    # (2 - 1) / 2, nao / 4


def test_zero_por_cento_conta_como_leitura_valida_e_nao_como_subindo(ativos_fake):
    """`p is None` e a unica coisa que exclui. Um ativo parado e medicao: entra em `tot`
    e em `soma`, e nao entra em `up`."""
    ativos_fake({"BTC/USDT": {"percentage": 0.0}, "ETH/USDT": {"percentage": 4.0}})
    b = mercado.breadth()
    assert b["n"] == 2 and b["pct_subindo"] == 50 and b["variacao_media"] == pytest.approx(2.0)


def test_nenhuma_leitura_devolve_none_e_nunca_zero(ativos_fake):
    """`if not tot: return None`. Zero por cento subindo e uma AFIRMACAO sobre o mercado;
    a corretora fora do ar nao autoriza a fazer nenhuma."""
    ativos_fake({}, ativos=["BTC/USDT", "ETH/USDT"])
    assert mercado.breadth() is None


# ================================================================ [P1-9] janela do sinal

@pytest.mark.parametrize("tf,minutos", [
    ("5m", 20), ("15m", 60), ("1h", 240), ("4h", 960), ("1d", 5760),
    ("bagunca", 60), ("", 60), (None, 60),           # TF desconhecido cai no 15m
])
def test_a_janela_e_contada_em_velas_do_proprio_timeframe(tf, minutos):
    """[P1-9] Um sinal de 5m e um de 4h nao envelhecem no mesmo relogio. Fixar "60 min"
    para os dois -- que era o efeito de nao ter janela nenhuma por TF -- trata um sinal de
    4h como velho quatro velas antes da hora."""
    assert signal_engine.janela_min(tf) == minutos


def test_sinal_novo_fora_da_janela_vira_expirado(banco):
    """A outra ponta do card: sem isto o pendente de ontem seguia 'novo' para sempre, com
    preco e stop de ontem, disputando o ativo com o candidato de agora -- e tanto
    `/estado.pendentes` quanto o pool do auto-trader leem o banco, nao a tela."""
    agora = pd.Timestamp("2026-08-22 12:00:00")
    velho = semear_sinal(tf="15m", ts=str(agora - pd.Timedelta(minutes=61)))
    novo = semear_sinal(tf="15m", ts=str(agora - pd.Timedelta(minutes=59)))
    assert signal_engine.expirar_sinais(agora) == 1
    estados = {r["id"]: r["status"] for r in db.listar("sinais", 10)}
    assert estados[velho] == "expirado"
    assert estados[novo] == "novo"


def test_a_expiracao_respeita_a_janela_de_cada_timeframe(banco):
    """Roda por TF porque a janela e por TF: 90 minutos mata o sinal de 15m e nao encosta
    no de 4h."""
    agora = pd.Timestamp("2026-08-22 12:00:00")
    ts = str(agora - pd.Timedelta(minutes=90))
    curto = semear_sinal(tf="15m", ts=ts)
    longo = semear_sinal(tf="4h", ts=ts)
    signal_engine.expirar_sinais(agora)
    estados = {r["id"]: r["status"] for r in db.listar("sinais", 10)}
    assert (estados[curto], estados[longo]) == ("expirado", "novo")


@pytest.mark.parametrize("status", ["confirmado", "pulado", "rejeitado_fluxo"])
def test_a_expiracao_nao_reescreve_historico(banco, status):
    """`status='novo'` e o unico alvo. Reescrever 'rejeitado_fluxo' apagaria exatamente o
    que o [Q-4] esta medindo."""
    agora = pd.Timestamp("2026-08-22 12:00:00")
    sid = semear_sinal(tf="15m", ts=str(agora - pd.Timedelta(days=3)), status=status)
    assert signal_engine.expirar_sinais(agora) == 0
    assert db.listar("sinais", 1)[0]["status"] == status


def test_expirar_sem_sinal_nenhum_nao_quebra(banco):
    assert signal_engine.expirar_sinais(pd.Timestamp("2026-08-22 12:00:00")) == 0
