# -*- coding: utf-8 -*-
"""[CD-1] O sinal registra o estado do DIARIO do ativo (RSI de 14 dias e retorno de 7 dias).

E anotacao: nenhuma regra le as duas colunas. O que estes testes travam e (1) a conta, so
com vela fechada; (2) que ausencia de medicao e NULL e nunca zero; (3) que a anotacao nao
custa o sinal quando a rede falha; e (4) que ela nao gasta requisicao alem da que o filtro
[TD-1] ja gastava.
"""
import sqlite3
import time

import numpy as np
import pandas as pd
import pytest

import db
import signal_engine
import tendencia
from indicadores import rsi

DIA = tendencia.DIA_MS


def _raw(closes):
    """Velas diarias com os closes dados; a ultima FECHOU na virada do dia UTC de hoje."""
    fim = (int(time.time() * 1000) // DIA) * DIA
    ini = fim - len(closes) * DIA
    return [[ini + i * DIA, c, c * 1.01, c * 0.99, c, 1.0] for i, c in enumerate(closes)]


SOBE = list(np.linspace(100, 200, 120))
CAI = list(np.linspace(200, 100, 120))


@pytest.fixture(autouse=True)
def _limpa_cache():
    tendencia._cache.clear()
    yield
    tendencia._cache.clear()


# ------------------------------------------------------------------ a conta
def test_rsi_e_retorno_batem_com_a_conta_na_mao():
    rng = np.random.default_rng(17)
    c = list(100 * np.exp(np.cumsum(rng.normal(0, 0.03, 200))))
    ctx = tendencia.contexto_de(_raw(c), time.time() * 1000)
    assert ctx["rsi"] == round(float(rsi(pd.Series(c), 14).iloc[-1]), 1)
    assert ctx["ret7"] == round((c[-1] / c[-8] - 1) * 100, 2)


def test_vela_do_dia_em_formacao_nao_entra():
    agora = time.time() * 1000
    raw = _raw(CAI)
    forma = [[raw[-1][0] + DIA, 1.0, 1.0, 1.0, 9999.0, 1.0]]     # abriu hoje, close absurdo
    assert tendencia.contexto_de(raw + forma, agora) == tendencia.contexto_de(raw, agora)


def test_zero_e_leitura_e_nao_ausencia():
    """Queda em linha reta da RSI 0, e 0 tem de sair como 0.0: quem le a coluna depois precisa
    distinguir "o mais esticado possivel" de "nao foi medido"."""
    agora = time.time() * 1000
    cai, sobe = tendencia.contexto_de(_raw(CAI), agora), tendencia.contexto_de(_raw(SOBE), agora)
    assert cai["rsi"] == 0.0 and cai["rsi"] is not None
    assert sobe["rsi"] == 100.0
    assert cai["ret7"] < 0 < sobe["ret7"]


def test_historia_curta_e_ausencia():
    agora = time.time() * 1000
    assert tendencia.contexto_de(_raw(CAI[:5]), agora) == {"rsi": None, "ret7": None}
    dez = tendencia.contexto_de(_raw(CAI[:10]), agora)
    assert dez["rsi"] is None and dez["ret7"] is not None        # 7 dias cabem, 14 nao


def test_uma_requisicao_por_ativo_por_dia_para_o_filtro_e_para_a_anotacao(monkeypatch):
    chamadas = []
    monkeypatch.setattr(tendencia, "_velas_1d", lambda a: chamadas.append(a) or _raw(CAI))
    for _ in range(3):
        assert tendencia.permite("BTC/USDT", "SHORT", "d1")
        assert tendencia.contexto("BTC/USDT")["rsi"] == 0.0
    assert chamadas == ["BTC/USDT"]


# ------------------------------------------------------------------ no scan
SINAL = dict(ativo="BTC/USDT", tf="15m", tipo="tendencia", direcao="SHORT", conviccao=80,
             motivos="x", preco=100.0, stop_sugerido=103.0, adx=30, n_fatores=4, vela_ms=1)


def _scan(monkeypatch, confirmado=lambda s, a, cfg: (True, "confirmado")):
    db.set_config("ativos", "BTC/USDT")
    db.set_config("timeframes", "15m")
    monkeypatch.setattr(signal_engine, "analisa", lambda a, tf: [dict(SINAL)])
    monkeypatch.setattr(signal_engine, "confirmado", confirmado)
    monkeypatch.setattr(signal_engine, "marcar_desfechos", lambda *a, **k: 0)
    signal_engine.scan()
    with db.conectar() as c:
        return [dict(r) for r in c.execute("SELECT status, rsi_d1, ret7_d1 FROM sinais")]


def test_o_scan_grava_o_contexto_no_sinal(banco, monkeypatch):
    monkeypatch.setattr(tendencia, "_velas_1d", lambda a: _raw(CAI))
    esperado = tendencia.contexto_de(_raw(CAI), time.time() * 1000)
    linhas = _scan(monkeypatch)
    assert linhas == [{"status": "novo", "rsi_d1": 0.0, "ret7_d1": esperado["ret7"]}]


def test_diario_fora_do_ar_nao_custa_o_sinal(banco, monkeypatch):
    """O contrario do filtro [TD-1]: la, nao saber o lado e motivo para nao abrir; aqui, nao
    conseguir anotar NAO e motivo para perder a fila. (O diario ja falha por padrao na suite:
    tests/conftest.py.)"""
    assert _scan(monkeypatch) == [{"status": "novo", "rsi_d1": None, "ret7_d1": None}]


def test_o_rejeitado_por_fluxo_tambem_e_anotado(banco, monkeypatch):
    """Os dois grupos com a mesma regua, como o [Q-4] faz com o fluxo: anotar so quem passou
    deixaria a comparacao sem o lado de la."""
    monkeypatch.setattr(tendencia, "_velas_1d", lambda a: _raw(CAI))

    def rejeita(s, a, cfg):
        s["rejeitado_por"] = "fluxo"
        return False, "fluxo contra o SHORT"
    linhas = _scan(monkeypatch, rejeita)
    assert [(l["status"], l["rsi_d1"]) for l in linhas] == [(signal_engine.REJEITADO_FLUXO, 0.0)]


def test_quem_grava_sem_anotar_grava_null(banco):
    """`pesquisa/backtest_portfolio` chama `_gravar` direto, com o sinal que ele mesmo montou:
    sem as chaves, as colunas ficam NULL e o backtest nao fala com a rede."""
    with db.conectar() as con:
        signal_engine._gravar(con, "2026-03-01 12:00:00", dict(SINAL), "BTC/USDT", "15m", "novo", None)
        r = con.execute("SELECT rsi_d1, ret7_d1 FROM sinais").fetchone()
    assert (r["rsi_d1"], r["ret7_d1"]) == (None, None)


# ------------------------------------------------------------------ migracao
def test_banco_que_ja_existia_ganha_as_colunas(tmp_path):
    """O banco de producao nasceu antes destas colunas: o `init_db` do boot as acrescenta, e o
    que ja estava gravado fica com NULL."""
    caminho = str(tmp_path / "antigo.db")
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE sinais(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, ativo TEXT, "
                "direcao TEXT, conviccao REAL, motivos TEXT, preco REAL, stop_sugerido REAL, "
                "status TEXT DEFAULT 'novo')")
    con.execute("INSERT INTO sinais(ts,ativo,direcao) VALUES('2026-11-01 10:00:00','BTC/USDT','SHORT')")
    con.commit()
    con.close()
    original = db.DB
    db.DB = caminho
    try:
        db.init_db()
        with db.conectar() as c:
            colunas = {r["name"] for r in c.execute("PRAGMA table_info(sinais)")}
            velho = c.execute("SELECT rsi_d1, ret7_d1 FROM sinais").fetchone()
    finally:
        db.DB = original
    assert {"rsi_d1", "ret7_d1"} <= colunas
    assert (velho["rsi_d1"], velho["ret7_d1"]) == (None, None)
