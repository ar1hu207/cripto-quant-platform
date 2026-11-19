# -*- coding: utf-8 -*-
"""[AG-2] `auto_agitacao_corte` / `auto_agitacao_frac`: tamanho menor no ativo agitado.

Nasce desligada. Ligada, o sinal de tendencia com `sinais.atr_rel` ([AG-1]) no corte ou acima
abre com uma fracao do risco, e so isso: a alavancagem nao muda, a reversao fica de fora, sinal
sem medicao abre inteiro e fracao invalida nunca infla nem zera o risco.
"""
import os
import re

import pytest

import autotrader
import db
from pesquisa import backtest_portfolio as bp

# ------------------------------------------------------------------ [AG-2] o tamanho
# 1% por trade e stop de 3%: as entradas cabem em todos os tetos e quem mexe no valor e so a chave
BASE = {"risco_por_trade": "0.01"}
LIGADA = {"auto_agitacao_corte": "1.18"}
TRES = ["ATOM/USDT", "ETC/USDT", "BTC/USDT"]


def _sinal(ativo, conviccao, atr_rel, tipo="tendencia", preco=100.0):
    with db.conectar() as c:
        c.execute("INSERT INTO sinais(ts,ativo,tf,tipo,direcao,conviccao,motivos,preco,"
                  "stop_sugerido,status,atr_rel) VALUES('2026-03-01 08:00:00',?,'15m',?,'SHORT',?,"
                  "'x',?,?,'novo',?)", (ativo, tipo, conviccao, preco, preco * 1.03, atr_rel))


def _rodar(sinais, **cfg):
    """Um ciclo do auto-trader sobre os sinais dados. Devolve (res, {ativo: abertura})."""
    with bp.Ambiente("2026-03-01 08:00:30", cfg=dict(BASE, **cfg), banca=10000.0) as amb:
        amb.precos.mapa = {a: 100.0 for a in TRES}
        for i, (ativo, atr_rel, *resto) in enumerate(sinais):
            _sinal(ativo, 90 - i, atr_rel, *resto)
        res = autotrader.auto_executar(None)
        return res, {a["ativo"]: a for a in res["abertos"]}


def test_nasce_desligada_e_e_o_comportamento_de_antes():
    assert db.CONFIG_PADRAO["auto_agitacao_corte"] == "0"
    res, ab = _rodar([("ATOM/USDT", 2.0), ("ETC/USDT", 1.0)])
    assert ab["ATOM/USDT"]["valor"] == ab["ETC/USDT"]["valor"] > 0
    assert res["agitacao"] == []


def test_ligada_o_agitado_abre_com_meio_tamanho_e_a_mesma_alavancagem():
    res, ab = _rodar([("ATOM/USDT", 1.5), ("ETC/USDT", 1.0)], **LIGADA)
    assert ab["ATOM/USDT"]["valor"] == pytest.approx(ab["ETC/USDT"]["valor"] / 2, abs=0.01)
    assert ab["ATOM/USDT"]["lev"] == ab["ETC/USDT"]["lev"]
    assert res["agitacao"] == ["ATOM/USDT"]


def test_o_corte_e_maior_ou_igual_e_ausencia_de_medicao_nao_e_bandeira():
    res, ab = _rodar([("ATOM/USDT", 1.18), ("ETC/USDT", 1.17), ("BTC/USDT", None)], **LIGADA)
    inteiro = ab["ETC/USDT"]["valor"]
    assert ab["ATOM/USDT"]["valor"] == pytest.approx(inteiro / 2, abs=0.01)
    assert ab["BTC/USDT"]["valor"] == inteiro               # sem `atr_rel`: abre inteiro
    assert res["agitacao"] == ["ATOM/USDT"]


def test_a_fracao_e_a_da_config():
    _, ab = _rodar([("ATOM/USDT", 2.0), ("ETC/USDT", 1.0)], auto_agitacao_frac="0.25", **LIGADA)
    assert ab["ATOM/USDT"]["valor"] == pytest.approx(ab["ETC/USDT"]["valor"] / 4, abs=0.01)


def test_reversao_fica_de_fora():
    """A medida foi feita so nos sinais de tendencia."""
    res, ab = _rodar([("ATOM/USDT", 2.0, "reversao"), ("ETC/USDT", 1.0)], **LIGADA)
    assert ab["ATOM/USDT"]["valor"] == ab["ETC/USDT"]["valor"]
    assert res["agitacao"] == []


@pytest.mark.parametrize("lixo", ["2", "1.01", "0", "-0.5"])
def test_fracao_fora_da_faixa_nunca_infla_nem_zera(lixo):
    """O catalogo recusa estes valores na entrada; se chegarem ao banco por outro caminho, a
    regra fica inerte. Inflar seria afrouxar o `risco_por_trade` por uma chave que so reduz."""
    res, ab = _rodar([("ATOM/USDT", 2.0), ("ETC/USDT", 1.0)], auto_agitacao_frac=lixo, **LIGADA)
    assert ab["ATOM/USDT"]["valor"] == ab["ETC/USDT"]["valor"]
    assert res["agitacao"] == []


def test_a_manha_de_17_11_passa_inteira():
    """O registro honesto do que esta chave NAO resolve. Os tres SHORTs stopados em 17/11
    estavam calmos contra o normal deles (ATOM 0,75, ETC 0,77, BTC 1,08): com a chave ligada
    no corte medido, os tres abrem com o tamanho inteiro."""
    res, ab = _rodar([("ATOM/USDT", 0.75), ("ETC/USDT", 0.77), ("BTC/USDT", 1.08)], **LIGADA)
    assert len({a["valor"] for a in ab.values()}) == 1 and len(ab) == 3
    assert res["agitacao"] == []


# ------------------------------------------------------------------ catalogo e painel
def test_catalogo_aceita_a_faixa_e_recusa_o_resto(banco):
    from fastapi.testclient import TestClient
    import api
    cli = TestClient(api.app, client=("127.0.0.1", 5555))
    for chave in ("auto_agitacao_corte", "auto_agitacao_frac"):
        assert api._validar_config(chave, db.CONFIG_PADRAO[chave]), chave
    for v in (0, 1.18, 10):
        assert cli.post("/config", json={"auto_agitacao_corte": v}).status_code == 200, v
    for v in (-1, 10.5, "alto"):
        assert cli.post("/config", json={"auto_agitacao_corte": v}).status_code == 422, v
    for v in (0.1, 0.5, 1):
        assert cli.post("/config", json={"auto_agitacao_frac": v}).status_code == 200, v
    for v in (0, 0.05, 1.5, 2):                             # so reduz: nunca zera, nunca infla
        assert cli.post("/config", json={"auto_agitacao_frac": v}).status_code == 422, v
    racional = cli.get("/catalogo").json()["parametros"]["auto_agitacao_corte"]["racional"]
    assert "2026 foi o ano que inverteu" in racional    # quem liga no painel le a ressalva
    assert "NÃO é proteção de dia lateral" in racional


def test_o_painel_mostra_as_duas_chaves_no_tamanho_e_marcadas_como_risco():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "web", "app", "views", "apollo.js"), encoding="utf-8") as f:
        js = f.read()
    tamanho = re.search(r"\['Tamanho e alavancagem', \[([^\]]*)\]\]", js).group(1)
    risco = re.search(r"var RISCO = \{([^}]*)\}", js).group(1)
    nomes = re.search(r"var NOMES = \{(.*?)\};", js, re.S).group(1)
    pct = re.search(r"var PCT = \{([^}]*)\}", js).group(1)
    for chave in ("auto_agitacao_corte", "auto_agitacao_frac"):
        assert f"'{chave}'" in tamanho and f"{chave}: 1" in risco and f"{chave}: '" in nomes
    assert "auto_agitacao_frac: 1" in pct and "auto_agitacao_corte" not in pct
