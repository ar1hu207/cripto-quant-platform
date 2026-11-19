# -*- coding: utf-8 -*-
"""[DV-2] `auto_dvol_corte`: nao abrir com as opcoes do BTC caras (DVOL de ontem no percentil >= corte).

Nasce desligada. Ligada, o sinal de tendencia com `sinais.dvol_pct` >= corte nao abre, nos dois
lados; o sinal segue 'novo' e a vaga vai para o proximo candidato (foi assim que a carteira do T63
mediu). Reversao e sinal sem leitura ficam de fora. A decisao nao vai a rede: le o que o scan gravou.
"""
import pytest

import autotrader
import db
import dvol
from pesquisa import backtest_portfolio as bp

BASE = {"risco_por_trade": "0.01"}
ATIVOS = ("ATOM/USDT", "ETC/USDT", "BTC/USDT")


def _sinal(ativo, conviccao, direcao, tipo, pct):
    preco = 100.0
    stop = preco * (1.03 if direcao == "SHORT" else 0.97)
    with db.conectar() as c:
        c.execute("INSERT INTO sinais(ts,ativo,tf,tipo,direcao,conviccao,motivos,preco,"
                  "stop_sugerido,status,dvol_pct) VALUES('2026-03-01 08:00:00',?,'15m',?,?,?,'x',?,?,'novo',?)",
                  (ativo, tipo, direcao, conviccao, preco, stop, pct))


def _rodar(monkeypatch, sinais, **cfg):
    """Um ciclo do auto-trader. `sinais` = [(ativo, direcao, tipo, dvol_pct)]."""
    def nao_chame(agora):
        raise AssertionError("o veto le a coluna do sinal; nao vai a Deribit")
    monkeypatch.setattr(dvol, "_baixar", nao_chame)
    with bp.Ambiente("2026-03-01 08:00:30", cfg=dict(BASE, **cfg), banca=10000.0) as amb:
        amb.precos.mapa = {a: 100.0 for a in ATIVOS}
        for i, (ativo, direcao, tipo, pct) in enumerate(sinais):
            _sinal(ativo, 90 - i, direcao, tipo, pct)
        res = autotrader.auto_executar(None)
        with db.conectar() as c:
            status = {r[0]: r[1] for r in c.execute("SELECT ativo, status FROM sinais")}
        return res, {a["ativo"]: a for a in res["abertos"]}, status


ALTO_E_CALMO = [("ATOM/USDT", "SHORT", "tendencia", 0.95), ("ETC/USDT", "LONG", "tendencia", 0.40)]


def test_nasce_desligada():
    assert db.CONFIG_PADRAO["auto_dvol_corte"] == "0"


def test_desligada_abre_tudo(monkeypatch):
    res, ab, _ = _rodar(monkeypatch, ALTO_E_CALMO)
    assert set(ab) == {"ATOM/USDT", "ETC/USDT"}
    assert res["dvol"] == []


def test_ligada_nao_abre_com_dvol_alto_e_nao_consome_o_sinal(monkeypatch):
    res, ab, status = _rodar(monkeypatch, ALTO_E_CALMO, auto_dvol_corte="0.8")
    assert list(ab) == ["ETC/USDT"]
    assert status["ATOM/USDT"] == "novo"
    assert res["dvol"] == [{"ativo": "ATOM/USDT", "pct": 0.95}]


def test_a_vaga_vai_para_o_proximo_candidato(monkeypatch):
    """Com uma vaga so, o barrado (maior conviccao) nao a ocupa: abre o seguinte."""
    res, ab, _ = _rodar(monkeypatch, ALTO_E_CALMO, auto_dvol_corte="0.8", auto_max_posicoes="1")
    assert list(ab) == ["ETC/USDT"]


def test_vale_nos_dois_lados(monkeypatch):
    sinais = [("ATOM/USDT", "LONG", "tendencia", 0.81), ("ETC/USDT", "SHORT", "tendencia", 0.99)]
    res, ab, _ = _rodar(monkeypatch, sinais, auto_dvol_corte="0.8")
    assert ab == {}
    assert [d["ativo"] for d in res["dvol"]] == ["ATOM/USDT", "ETC/USDT"]


def test_o_corte_e_inclusivo_e_vem_da_config(monkeypatch):
    sinais = [("ATOM/USDT", "SHORT", "tendencia", 0.8), ("ETC/USDT", "SHORT", "tendencia", 0.79)]
    _, ab, _ = _rodar(monkeypatch, sinais, auto_dvol_corte="0.8")
    assert list(ab) == ["ETC/USDT"]
    _, ab, _ = _rodar(monkeypatch, sinais, auto_dvol_corte="0.9")
    assert set(ab) == {"ATOM/USDT", "ETC/USDT"}


def test_sem_leitura_abre(monkeypatch):
    """Deribit fora do ar no scan grava NULL; a medida tratou o dia sem leitura como 'nao bloqueia'."""
    sinais = [("ATOM/USDT", "SHORT", "tendencia", None), ("ETC/USDT", "SHORT", "tendencia", 0.95)]
    res, ab, _ = _rodar(monkeypatch, sinais, auto_dvol_corte="0.8")
    assert list(ab) == ["ATOM/USDT"]
    assert [d["ativo"] for d in res["dvol"]] == ["ETC/USDT"]


def test_reversao_fica_de_fora(monkeypatch):
    """A medida foi feita nos trades de tendencia."""
    sinais = [("ATOM/USDT", "SHORT", "reversao", 0.99), ("ETC/USDT", "SHORT", "tendencia", 0.99)]
    res, ab, _ = _rodar(monkeypatch, sinais, auto_dvol_corte="0.8")
    assert list(ab) == ["ATOM/USDT"]


def test_o_catalogo_aceita_de_0_a_1_e_tem_racional():
    import api
    assert api.CONFIG_CATALOGO["auto_dvol_corte"] == ("float", 0.0, 1.0)
    assert "DESLIGADO" in api.CONFIG_RACIONAL["auto_dvol_corte"]
