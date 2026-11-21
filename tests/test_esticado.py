# -*- coding: utf-8 -*-
"""[EST-1] `auto_esticado_modo` / `auto_esticado_ret7`: venda com o diario ja caido.
[EST-2] `auto_esticado_veto7` / `auto_esticado_ret1`: os degraus de veto (7 dias fundo, vespera).

Nasce desligada. Ligada, o SHORT de tendencia cujo ativo caiu <= corte nos ultimos 7 dias
FECHADOS abre com metade do risco (`meio`) ou nao abre (`veto`). O LONG, a reversao e a moeda
sem diario suficiente ficam de fora; o diario fora do ar pula o sinal no ciclo, sem consumi-lo.
"""
import time

import numpy as np
import pytest

import api
import autotrader
import db
import tendencia
from pesquisa import backtest_portfolio as bp

DIA = tendencia.DIA_MS


def _raw(closes):
    """Velas diarias com os closes dados; a ultima FECHOU na virada do dia UTC de hoje."""
    fim = (int(time.time() * 1000) // DIA) * DIA
    ini = fim - len(closes) * DIA
    return [[ini + i * DIA, c, c * 1.01, c * 0.99, c, 1.0] for i, c in enumerate(closes)]


# 7d fechados: 110 / 150 - 1 = −26,7%  |  CALMO: −5,6% (queda lenta, abaixo do corte de −10%)
CAIU = list(np.linspace(300, 150, 113)) + list(np.linspace(145, 110, 7))
CALMO = list(np.linspace(200, 100, 120))
NOVA = [100.0, 95, 90, 85, 80]                   # 5 dias de diario: sem ret7
# [EST-2] 7d −12% (faixa do meio), ontem −2%  |  semana −8% mas ONTEM −8% sozinho
MEIO12 = list(np.linspace(300, 200, 113)) + list(np.linspace(198, 176, 7))
VESPERA = [150.0] * 119 + [138.0]
DIARIO = {"ATOM/USDT": CAIU, "ETC/USDT": CALMO, "BTC/USDT": NOVA, "SOL/USDT": MEIO12,
          "ADA/USDT": VESPERA}
BASE = {"risco_por_trade": "0.01"}


@pytest.fixture(autouse=True)
def _limpa_cache():
    tendencia._cache.clear()
    yield
    tendencia._cache.clear()


def _sinal(ativo, conviccao, direcao="SHORT", tipo="tendencia", preco=100.0):
    stop = preco * (1.03 if direcao == "SHORT" else 0.97)
    with db.conectar() as c:
        c.execute("INSERT INTO sinais(ts,ativo,tf,tipo,direcao,conviccao,motivos,preco,"
                  "stop_sugerido,status) VALUES('2026-03-01 08:00:00',?,'15m',?,?,?,'x',?,?,'novo')",
                  (ativo, tipo, direcao, conviccao, preco, stop))


def _rodar(monkeypatch, sinais, velas=None, **cfg):
    """Um ciclo do auto-trader. `sinais` = [(ativo, direcao, tipo)]. Devolve (res, abertos, status)."""
    monkeypatch.setattr(tendencia, "_velas_1d", velas or (lambda a: _raw(DIARIO[a])))
    with bp.Ambiente("2026-03-01 08:00:30", cfg=dict(BASE, **cfg), banca=10000.0) as amb:
        amb.precos.mapa = {a: 100.0 for a in DIARIO}
        for i, (ativo, direcao, tipo) in enumerate(sinais):
            _sinal(ativo, 90 - i, direcao, tipo)
        res = autotrader.auto_executar(None)
        with db.conectar() as c:
            status = {r[0]: r[1] for r in c.execute("SELECT ativo, status FROM sinais")}
        return res, {a["ativo"]: a for a in res["abertos"]}, status


DOIS = [("ATOM/USDT", "SHORT", "tendencia"), ("ETC/USDT", "SHORT", "tendencia")]


def test_conta_do_diario_e_a_que_o_teste_supoe():
    agora = time.time() * 1000
    assert tendencia.contexto_de(_raw(CAIU), agora)["ret7"] == pytest.approx(-26.67, abs=0.01)
    assert tendencia.contexto_de(_raw(CALMO), agora)["ret7"] > -10
    assert tendencia.contexto_de(_raw(NOVA), agora)["ret7"] is None
    m12 = tendencia.contexto_de(_raw(MEIO12), agora)
    assert m12["ret7"] == pytest.approx(-12.0, abs=0.01) and m12["ret1"] > -5
    vesp = tendencia.contexto_de(_raw(VESPERA), agora)
    assert vesp["ret7"] == vesp["ret1"] == pytest.approx(-8.0, abs=0.01)


def test_nasce_desligada_e_nem_consulta_o_diario(monkeypatch):
    assert db.CONFIG_PADRAO["auto_esticado_modo"] == "off"
    def nao_chame(a):
        raise AssertionError("com a chave desligada o diario nao e lido")
    res, ab, _ = _rodar(monkeypatch, DOIS, velas=nao_chame)
    assert ab["ATOM/USDT"]["valor"] == ab["ETC/USDT"]["valor"] > 0
    assert res["esticado"] == []


def test_meio_o_short_esticado_abre_com_metade_e_a_mesma_alavancagem(monkeypatch):
    res, ab, _ = _rodar(monkeypatch, DOIS, auto_esticado_modo="meio")
    assert ab["ATOM/USDT"]["valor"] == pytest.approx(ab["ETC/USDT"]["valor"] / 2, abs=0.01)
    assert ab["ATOM/USDT"]["lev"] == ab["ETC/USDT"]["lev"]
    assert res["esticado"] == [{"ativo": "ATOM/USDT", "ret7": pytest.approx(-26.67, abs=0.01),
                                "acao": "meio"}]


def test_veto_nao_vende_nao_consome_o_sinal_e_a_vaga_anda(monkeypatch):
    res, ab, status = _rodar(monkeypatch, DOIS, auto_esticado_modo="veto", auto_max_posicoes="1")
    assert list(ab) == ["ETC/USDT"]                   # a unica vaga foi para o proximo
    assert status["ATOM/USDT"] == "novo"
    assert [e["acao"] for e in res["esticado"]] == ["veto"]


def test_long_e_reversao_ficam_de_fora(monkeypatch):
    """O LONG esticado para cima nao foi pior no T54, e a reversao nao foi medida."""
    sinais = [("ATOM/USDT", "LONG", "tendencia"), ("ETC/USDT", "SHORT", "tendencia")]
    res, ab, _ = _rodar(monkeypatch, sinais, auto_esticado_modo="veto")
    assert set(ab) == {"ATOM/USDT", "ETC/USDT"}
    sinais = [("ATOM/USDT", "SHORT", "reversao"), ("ETC/USDT", "SHORT", "tendencia")]
    res, ab, _ = _rodar(monkeypatch, sinais, auto_esticado_modo="veto")
    assert set(ab) == {"ATOM/USDT", "ETC/USDT"}
    assert res["esticado"] == []


def test_o_corte_e_da_config(monkeypatch):
    res, ab, _ = _rodar(monkeypatch, DOIS, auto_esticado_modo="veto", auto_esticado_ret7="-30")
    assert set(ab) == {"ATOM/USDT", "ETC/USDT"}       # −26,7% nao chega a −30%
    assert res["esticado"] == []


def test_moeda_sem_diario_suficiente_abre_inteira(monkeypatch):
    sinais = [("BTC/USDT", "SHORT", "tendencia"), ("ETC/USDT", "SHORT", "tendencia")]
    res, ab, _ = _rodar(monkeypatch, sinais, auto_esticado_modo="meio")
    assert ab["BTC/USDT"]["valor"] == ab["ETC/USDT"]["valor"]
    assert res["esticado"] == []


def test_diario_fora_do_ar_pula_no_ciclo_sem_consumir(monkeypatch):
    def cai(a):
        raise ConnectionError("binance fora")
    res, ab, status = _rodar(monkeypatch, DOIS, velas=cai, auto_esticado_modo="meio")
    assert ab == {}
    assert all("diário n/d" in r["erro"] for r in res["rejeitados"])
    assert set(status.values()) == {"novo"}


def test_com_o_filtro_d1_ligado_usa_a_mesma_requisicao(monkeypatch):
    """[TD-1] e [EST-1] leem o mesmo cache do dia: uma requisicao por ativo, nao duas."""
    chamadas = []
    def conta(a):
        chamadas.append(a)
        return _raw(DIARIO[a])
    res, ab, _ = _rodar(monkeypatch, DOIS, velas=conta, auto_esticado_modo="meio",
                        tendencia_filtro="d1")
    assert sorted(chamadas) == ["ATOM/USDT", "ETC/USDT"]
    assert ab["ATOM/USDT"]["valor"] == pytest.approx(ab["ETC/USDT"]["valor"] / 2, abs=0.01)


# ------------------------------------------------------------------ [EST-2]
TRES = [("ATOM/USDT", "SHORT", "tendencia"), ("SOL/USDT", "SHORT", "tendencia"),
        ("ETC/USDT", "SHORT", "tendencia")]


def test_est2_nasce_desligado_e_meio_segue_como_era(monkeypatch):
    assert db.CONFIG_PADRAO["auto_esticado_veto7"] == db.CONFIG_PADRAO["auto_esticado_ret1"] == "0"
    res, ab, _ = _rodar(monkeypatch, TRES, auto_esticado_modo="meio")
    assert set(ab) == {"ATOM/USDT", "SOL/USDT", "ETC/USDT"}
    assert {e["ativo"]: e["acao"] for e in res["esticado"]} == {"ATOM/USDT": "meio", "SOL/USDT": "meio"}


def test_est2_veto7_veta_o_fundo_e_deixa_o_meio_no_meio(monkeypatch):
    res, ab, status = _rodar(monkeypatch, TRES, auto_esticado_modo="meio", auto_esticado_veto7="-15")
    assert set(ab) == {"SOL/USDT", "ETC/USDT"}                 # ATOM: −26,7% <= −15
    assert ab["SOL/USDT"]["valor"] == pytest.approx(ab["ETC/USDT"]["valor"] / 2, abs=0.01)
    assert status["ATOM/USDT"] == "novo"                       # veto nao consome o sinal
    assert {e["ativo"]: e["acao"] for e in res["esticado"]} == {"ATOM/USDT": "veto", "SOL/USDT": "meio"}


def test_est2_vespera_veta_mesmo_com_a_semana_acima_do_corte(monkeypatch):
    sinais = [("ADA/USDT", "SHORT", "tendencia"), ("SOL/USDT", "SHORT", "tendencia"),
              ("ETC/USDT", "SHORT", "tendencia")]
    res, ab, status = _rodar(monkeypatch, sinais, auto_esticado_modo="meio", auto_esticado_ret1="-5")
    assert set(ab) == {"SOL/USDT", "ETC/USDT"}                 # ADA: 7d −8% (fora), ontem −8%
    assert status["ADA/USDT"] == "novo"
    assert ab["SOL/USDT"]["valor"] == pytest.approx(ab["ETC/USDT"]["valor"] / 2, abs=0.01)
    assert {e["ativo"]: e["acao"] for e in res["esticado"]} == {"ADA/USDT": "veto", "SOL/USDT": "meio"}


def test_est2_o_corte_da_vespera_e_da_config(monkeypatch):
    sinais = [("ADA/USDT", "SHORT", "tendencia"), ("ETC/USDT", "SHORT", "tendencia")]
    res, ab, _ = _rodar(monkeypatch, sinais, auto_esticado_modo="meio", auto_esticado_ret1="-10")
    assert set(ab) == {"ADA/USDT", "ETC/USDT"}                 # −8% nao chega a −10%
    assert ab["ADA/USDT"]["valor"] == ab["ETC/USDT"]["valor"]  # e a semana (−8%) nao e meio
    assert res["esticado"] == []


def test_est2_com_o_modo_off_os_degraus_nao_valem(monkeypatch):
    def nao_chame(a):
        raise AssertionError("com o modo desligado o diario nao e lido")
    res, ab, _ = _rodar(monkeypatch, TRES, velas=nao_chame, auto_esticado_veto7="-15",
                        auto_esticado_ret1="-5")
    assert set(ab) == {"ATOM/USDT", "SOL/USDT", "ETC/USDT"}
    assert res["esticado"] == []


def test_est2_long_e_reversao_continuam_de_fora(monkeypatch):
    sinais = [("ADA/USDT", "LONG", "tendencia"), ("ATOM/USDT", "SHORT", "reversao")]
    res, ab, _ = _rodar(monkeypatch, sinais, auto_esticado_modo="meio", auto_esticado_veto7="-15",
                        auto_esticado_ret1="-5")
    assert set(ab) == {"ADA/USDT", "ATOM/USDT"}
    assert res["esticado"] == []


def test_catalogo_est2(banco):
    for chave in ("auto_esticado_veto7", "auto_esticado_ret1"):
        assert api._validar_config(chave, db.CONFIG_PADRAO[chave])
        assert chave in api.CONFIG_RACIONAL
    for chave, ok in (("auto_esticado_veto7", "-15"), ("auto_esticado_ret1", "-5")):
        assert api._validar_config(chave, ok)
    for chave, ruim in (("auto_esticado_veto7", "5"), ("auto_esticado_veto7", "-80"),
                        ("auto_esticado_ret1", "1"), ("auto_esticado_ret1", "-40")):
        with pytest.raises(ValueError):
            api._validar_config(chave, ruim)


def test_catalogo(banco):
    for chave in ("auto_esticado_modo", "auto_esticado_ret7"):       # o padrao passa no catalogo
        assert api._validar_config(chave, db.CONFIG_PADRAO[chave])
    for chave, ok in (("auto_esticado_modo", "meio"), ("auto_esticado_modo", "veto"),
                      ("auto_esticado_ret7", "-15")):
        assert api._validar_config(chave, ok)
    for chave, ruim in (("auto_esticado_modo", "metade"), ("auto_esticado_ret7", "5"),
                        ("auto_esticado_ret7", "-80")):
        with pytest.raises(ValueError):
            api._validar_config(chave, ruim)
    assert "auto_esticado_modo" in api.CONFIG_RACIONAL
    assert "auto_esticado_ret7" in api.CONFIG_RACIONAL
