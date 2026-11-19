# -*- coding: utf-8 -*-
"""[DV-1] O sinal registra o percentil do DVOL (volatilidade implicita do BTC) de ONTEM.

E anotacao: so a chave `auto_dvol_corte` le a coluna, e ela nasce desligada. O que estes testes
travam e (1) a conta, igual a da medida (T61): close do ultimo dia FECHADO contra os 180 dias
corridos anteriores, dia sem vela fora da conta, minimo de 150; (2) que ausencia e NULL e nunca
zero; (3) que a anotacao nao custa o sinal quando a Deribit falha; (4) uma requisicao por dia UTC.
"""
import sqlite3
import time

import numpy as np
import pytest

import db
import dvol
import signal_engine

DIA = dvol.DIA_MS


def _raw(closes, faltam=()):
    """Velas diarias do DVOL; a ultima FECHOU na virada do dia UTC de hoje. `faltam` = indices
    que a fonte nao devolveu."""
    fim = (int(time.time() * 1000) // DIA) * DIA
    ini = fim - len(closes) * DIA
    return [[ini + i * DIA, c, c, c, c] for i, c in enumerate(closes) if i not in faltam]


def _a_mao(closes):
    """A conta do T61 escrita de novo: o ultimo contra os 180 anteriores, empate vale meio."""
    v, ant = closes[-1], closes[-181:-1]
    return (sum(x < v for x in ant) + 0.5 * sum(x == v for x in ant)) / len(ant)


RNG = np.random.default_rng(61)
SERIE = [float(x) for x in np.round(45 + 10 * np.cumsum(RNG.normal(0, 0.1, 220)), 2)]


@pytest.fixture
def com_dvol(monkeypatch):
    """Troca a falha padrao da suite (tests/conftest.py) por uma Deribit que responde."""
    def usar(closes, faltam=()):
        chamadas = []
        monkeypatch.setattr(dvol, "_baixar", lambda agora: chamadas.append(agora) or _raw(closes, faltam))
        return chamadas
    return usar


# ------------------------------------------------------------------ a conta
def test_o_percentil_bate_com_a_conta_da_medida():
    agora = time.time() * 1000
    r = dvol.percentil_de(_raw(SERIE), agora)
    assert r["dvol"] == round(SERIE[-1], 2)
    assert r["pct"] == round(_a_mao(SERIE), 4)


def test_a_vela_de_hoje_ainda_aberta_nao_entra():
    agora = time.time() * 1000
    raw = _raw(SERIE)
    hoje = [[raw[-1][0] + DIA, 999.0, 999.0, 999.0, 999.0]]      # abriu hoje, valor absurdo
    assert dvol.percentil_de(raw + hoje, agora) == dvol.percentil_de(raw, agora)


def test_o_maior_da_janela_e_1_e_o_menor_e_0():
    agora = time.time() * 1000
    assert dvol.percentil_de(_raw(list(range(1, 190))), agora)["pct"] == 1.0
    assert dvol.percentil_de(_raw(list(range(190, 1, -1))), agora)["pct"] == 0.0


def test_zero_e_leitura_e_nao_ausencia():
    """Percentil 0 (o DVOL mais baixo dos 6 meses) tem de sair 0.0, distinto de NULL."""
    r = dvol.percentil_de(_raw(list(range(190, 1, -1))), time.time() * 1000)
    assert r["pct"] == 0.0 and r["pct"] is not None


def test_empate_conta_meio():
    r = dvol.percentil_de(_raw([50.0] * 190), time.time() * 1000)
    assert r["pct"] == 0.5


def test_dia_que_a_fonte_nao_devolveu_fica_fora_da_conta():
    """O dia sem vela sai do numerador E do denominador (a medida trata assim): nao vira zero."""
    faltam = set(range(200, 210))                                    # 10 dias dentro da janela
    r = dvol.percentil_de(_raw(SERIE, faltam), time.time() * 1000)
    ant = [c for i, c in enumerate(SERIE[:-1]) if i >= len(SERIE) - 181 and i not in faltam]
    v = SERIE[-1]
    assert len(ant) == 170
    assert r["pct"] == round((sum(x < v for x in ant) + 0.5 * sum(x == v for x in ant)) / 170, 4)


def test_historia_curta_e_ausencia():
    agora = time.time() * 1000
    r = dvol.percentil_de(_raw(SERIE[-150:]), agora)              # 149 anteriores: falta 1
    assert r["pct"] is None and r["dvol"] == round(SERIE[-1], 2)
    assert dvol.percentil_de(_raw(SERIE[-151:]), agora)["pct"] is not None
    assert dvol.percentil_de([], agora) == {"dvol": None, "pct": None}


def test_uma_requisicao_por_dia_utc(com_dvol):
    chamadas = com_dvol(SERIE)
    agora = time.time() * 1000
    for _ in range(3):
        assert dvol.contexto(agora)["pct"] == round(_a_mao(SERIE), 4)
    assert len(chamadas) == 1
    dvol.contexto(agora + DIA)                                     # virou o dia: busca de novo
    assert len(chamadas) == 2


def test_resposta_vazia_levanta_e_nao_fica_no_cache(monkeypatch):
    monkeypatch.setattr(dvol, "_baixar", lambda agora: [])
    with pytest.raises(RuntimeError):
        dvol.contexto()
    assert dvol._cache == {}


# ------------------------------------------------------------------ no scan
SINAL = dict(ativo="BTC/USDT", tf="15m", tipo="tendencia", direcao="SHORT", conviccao=80,
             motivos="x", preco=100.0, stop_sugerido=103.0, adx=30, n_fatores=4, vela_ms=1)


def _scan(monkeypatch, confirmado=lambda s, a, cfg: (True, "confirmado")):
    db.set_config("ativos", "BTC/USDT,ETH/USDT")
    db.set_config("timeframes", "15m")
    monkeypatch.setattr(signal_engine, "analisa", lambda a, tf: [dict(SINAL, ativo=a)])
    monkeypatch.setattr(signal_engine, "confirmado", confirmado)
    monkeypatch.setattr(signal_engine, "marcar_desfechos", lambda *a, **k: 0)
    signal_engine.scan()
    with db.conectar() as c:
        return [dict(r) for r in c.execute("SELECT ativo, status, dvol_pct FROM sinais ORDER BY ativo")]


def test_o_scan_grava_o_mesmo_dvol_em_todos_os_sinais_com_uma_requisicao(banco, monkeypatch, com_dvol):
    chamadas = com_dvol(SERIE)
    p = round(_a_mao(SERIE), 4)
    assert _scan(monkeypatch) == [{"ativo": "BTC/USDT", "status": "novo", "dvol_pct": p},
                                  {"ativo": "ETH/USDT", "status": "novo", "dvol_pct": p}]
    assert len(chamadas) == 1


def test_deribit_fora_do_ar_nao_custa_o_sinal(banco, monkeypatch):
    """A suite ja derruba a Deribit por padrao (tests/conftest.py): o sinal sai com NULL."""
    assert [l["dvol_pct"] for l in _scan(monkeypatch)] == [None, None]
    assert [l["status"] for l in _scan(monkeypatch)] == ["novo", "novo"]


def test_o_rejeitado_por_fluxo_tambem_e_anotado(banco, monkeypatch, com_dvol):
    com_dvol(SERIE)

    def rejeita(s, a, cfg):
        s["rejeitado_por"] = "fluxo"
        return False, "fluxo contra o SHORT"
    linhas = _scan(monkeypatch, rejeita)
    assert {(l["status"], l["dvol_pct"]) for l in linhas} == {(signal_engine.REJEITADO_FLUXO, round(_a_mao(SERIE), 4))}


def test_quem_grava_sem_anotar_grava_null(banco):
    """`pesquisa/backtest_portfolio` chama `_gravar` direto: sem a chave, NULL, e sem rede."""
    with db.conectar() as con:
        signal_engine._gravar(con, "2026-03-01 12:00:00", dict(SINAL), "BTC/USDT", "15m", "novo", None)
        assert con.execute("SELECT dvol_pct FROM sinais").fetchone()["dvol_pct"] is None


# ------------------------------------------------------------------ migracao
def test_banco_que_ja_existia_ganha_a_coluna(tmp_path):
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
            velho = c.execute("SELECT dvol_pct FROM sinais").fetchone()
    finally:
        db.DB = original
    assert "dvol_pct" in colunas and velho["dvol_pct"] is None
