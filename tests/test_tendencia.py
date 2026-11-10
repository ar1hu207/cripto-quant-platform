# -*- coding: utf-8 -*-
"""[TD-1] Filtro de lado pela tendência do diário (tendencia.py, T38)."""
import time

import numpy as np
import pandas as pd
import pytest

import autotrader
import db
import tendencia
from pesquisa import backtest_portfolio as bp
from scoring import preparar

DIA = tendencia.DIA_MS


def _raw(closes, ultimo_fecha_ms=None):
    """Velas diárias com os closes dados; a última FECHA em `ultimo_fecha_ms` (default: ontem)."""
    fim = ultimo_fecha_ms or (int(time.time() * 1000) // DIA) * DIA
    ini = fim - len(closes) * DIA
    return [[ini + i * DIA, c, c * 1.01, c * 0.99, c, 1.0] for i, c in enumerate(closes)]


SOBE = list(np.linspace(100, 200, 120))
CAI = list(np.linspace(200, 100, 120))
# alta longa e um tombo de 3 dias: a EMA20 segue acima da EMA50, mas o close já furou a EMA50
TOMBO = list(np.linspace(100, 200, 120)) + [150, 130, 120]


@pytest.fixture(autouse=True)
def _limpa_cache():
    tendencia._cache.clear()
    yield
    tendencia._cache.clear()


def test_regra_d1_e_d2():
    agora = time.time() * 1000
    assert tendencia.lados(_raw(SOBE), agora) == {"d1": 1, "d2": 1}
    assert tendencia.lados(_raw(CAI), agora) == {"d1": -1, "d2": -1}
    assert tendencia.lados(_raw(TOMBO), agora) == {"d1": 0, "d2": 1}


def test_mesma_ema_do_scoring_preparar():
    """Paridade com o backtest: o T38 leu `ema_r`/`ema_l` de `scoring.preparar`."""
    rng = np.random.default_rng(38)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, 300)))
    df = preparar(pd.DataFrame(dict(open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1.0)))
    er, el, cl = df.ema_r.iloc[-1], df.ema_l.iloc[-1], df.close.iloc[-1]
    esperado = 1 if (er > el and cl > el) else (-1 if (er < el and cl < el) else 0)
    assert tendencia.lados(_raw(list(c)), time.time() * 1000)["d1"] == esperado


def test_vela_do_dia_em_formacao_nao_entra():
    agora = time.time() * 1000
    raw = _raw(SOBE)
    forma = [[raw[-1][0] + DIA, 1.0, 1.0, 1.0, 1.0, 1.0]]       # abriu hoje, close absurdo
    assert tendencia.lados(raw + forma, agora) == tendencia.lados(raw, agora)


def test_menos_de_50_velas_e_indefinido_e_passa(monkeypatch):
    monkeypatch.setattr(tendencia, "_velas_1d", lambda a: _raw(CAI[:40]))
    assert tendencia.lado("NOVA/USDT", "d1") is None
    assert tendencia.permite("NOVA/USDT", "LONG", "d1") is True


def test_off_nao_chama_a_rede(monkeypatch):
    def explode(a):
        raise AssertionError("não devia buscar velas")
    monkeypatch.setattr(tendencia, "_velas_1d", explode)
    assert tendencia.permite("BTC/USDT", "SHORT", "off") is True


def test_uma_requisicao_por_ativo_por_dia(monkeypatch):
    chamadas = []
    monkeypatch.setattr(tendencia, "_velas_1d", lambda a: chamadas.append(a) or _raw(SOBE))
    for _ in range(5):
        assert tendencia.permite("BTC/USDT", "LONG", "d1")
        assert not tendencia.permite("BTC/USDT", "SHORT", "d1")
    assert chamadas == ["BTC/USDT"]


# ------------------------------------------------------------------ no auto-trader
def _sinal(ativo, ts, conviccao, direcao="LONG", preco=100.0, stop=97.0):
    with db.conectar() as c:
        c.execute("INSERT INTO sinais(ts,ativo,tf,tipo,direcao,conviccao,motivos,preco,"
                  "stop_sugerido,status) VALUES(?,?,'15m','tendencia',?,?,'x',?,?,'novo')",
                  (ts, ativo, direcao, conviccao, preco, stop))


def _cenario(amb, monkeypatch, velas):
    amb.precos.mapa = {"BTC/USDT": 100.0, "ETH/USDT": 100.0}
    monkeypatch.setattr(tendencia, "_velas_1d", velas)
    _sinal("BTC/USDT", "2026-03-01 11:58:00", 95)        # o melhor sinal, mas contra o diário
    _sinal("ETH/USDT", "2026-03-01 11:58:00", 80)


def test_contra_o_diario_nao_abre_e_a_vaga_vai_para_o_proximo(monkeypatch):
    with bp.Ambiente("2026-03-01 12:00:00", cfg={"tendencia_filtro": "d1", "auto_max_posicoes": "1"},
                     banca=10000.0) as amb:
        _cenario(amb, monkeypatch, lambda a: _raw(CAI if a == "BTC/USDT" else SOBE))
        res = autotrader.auto_executar(None)
        assert [a["ativo"] for a in res["abertos"]] == ["ETH/USDT"]
        assert res["contra_tendencia"] == ["BTC/USDT"]
        with db.conectar() as c:                          # o sinal recusado não é consumido
            assert c.execute("SELECT status FROM sinais WHERE ativo='BTC/USDT'").fetchone()[0] == "novo"


def test_desligado_e_o_comportamento_de_antes(monkeypatch):
    with bp.Ambiente("2026-03-01 12:00:00", cfg={"auto_max_posicoes": "1"}, banca=10000.0) as amb:
        assert db.get_config()["tendencia_filtro"] == "off"
        _cenario(amb, monkeypatch, lambda a: _raw(CAI if a == "BTC/USDT" else SOBE))
        res = autotrader.auto_executar(None)
        assert [a["ativo"] for a in res["abertos"]] == ["BTC/USDT"]
        assert res["contra_tendencia"] == []


def test_rede_caida_nao_abre_sem_saber_o_lado(monkeypatch):
    def cai(a):
        raise ConnectionError("binance fora")
    with bp.Ambiente("2026-03-01 12:00:00", cfg={"tendencia_filtro": "d1"}, banca=10000.0) as amb:
        _cenario(amb, monkeypatch, cai)
        res = autotrader.auto_executar(None)
        assert res["abertos"] == []
        assert {r["ativo"] for r in res["rejeitados"]} == {"BTC/USDT", "ETH/USDT"}
        assert all("tendência n/d" in r["erro"] for r in res["rejeitados"])


def test_catalogo_aceita_os_tres_modos_e_recusa_o_resto(banco):
    from fastapi.testclient import TestClient
    import api
    cli = TestClient(api.app, client=("127.0.0.1", 5555))
    for m in ("d1", "d2", "off"):
        assert cli.post("/config", json={"tendencia_filtro": m}).status_code == 200, m
    assert cli.post("/config", json={"tendencia_filtro": "d3"}).status_code == 422
