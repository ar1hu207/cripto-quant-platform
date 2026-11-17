# -*- coding: utf-8 -*-
"""[RAJ-1] Teto de rajada: no maximo N entradas do MESMO lado por janela (autotrader).

Nasce desligado. O que estes testes travam: desligado e o comportamento de antes; ligado, ele
conta a DECISAO de entrar (ordem pendente, posicao a mercado, posicao ja stopada, entrada
manual), nao consome o sinal barrado, passa a vaga adiante e reabre quando a janela anda.
"""
import os
import re

import pandas as pd
import pytest

import autotrader
import db
import simulador
from pesquisa import backtest_portfolio as bp

QUATRO = ["ATOM/USDT", "ETC/USDT", "BTC/USDT", "DOGE/USDT"]
# 1% por trade: quatro entradas cabem no teto de risco aberto (10%) e quem barra e so a rajada
BASE = {"risco_por_trade": "0.01"}


def _sinal(ativo, ts, conviccao, direcao="SHORT", preco=100.0):
    stop = preco * (1.03 if direcao == "SHORT" else 0.97)
    with db.conectar() as c:
        c.execute("INSERT INTO sinais(ts,ativo,tf,tipo,direcao,conviccao,motivos,preco,"
                  "stop_sugerido,status) VALUES(?,?,'15m','tendencia',?,?,'x',?,?,'novo')",
                  (ts, ativo, direcao, conviccao, preco, stop))


def _status(ativo):
    with db.conectar() as c:
        return [r[0] for r in c.execute("SELECT status FROM sinais WHERE ativo=? ORDER BY id", (ativo,))]


def _amb(inicio, **cfg):
    amb = bp.Ambiente(inicio, cfg=dict(BASE, **cfg), banca=10000.0)
    return amb


def _precos(amb, preco=100.0, extra=()):
    amb.precos.mapa = {a: preco for a in list(QUATRO) + list(extra)}


def _abertos(res):
    return [a["ativo"] for a in res["abertos"]]


# ------------------------------------------------------------------ desligado
def test_nasce_desligado_e_e_o_comportamento_de_antes():
    with _amb("2026-03-01 08:00:30") as amb:
        assert db.get_config()["auto_rajada_max"] == "0"
        _precos(amb)
        for i, a in enumerate(QUATRO):
            _sinal(a, "2026-03-01 08:00:00", 90 - i)
        res = autotrader.auto_executar(None)
        assert _abertos(res) == QUATRO
        assert res["rajada"] == []


# ------------------------------------------------------------------ ligado
def test_quatro_do_mesmo_lado_na_mesma_vela_abrem_dois():
    with _amb("2026-03-01 08:00:30", auto_rajada_max="2") as amb:
        _precos(amb)
        for i, a in enumerate(QUATRO):
            _sinal(a, "2026-03-01 08:00:00", 90 - i)
        res = autotrader.auto_executar(None)
        assert _abertos(res) == QUATRO[:2]                 # os dois de maior conviccao
        assert res["rajada"] == QUATRO[2:]
        for a in QUATRO[2:]:                               # barrado nao e consumido
            assert _status(a) == ["novo"]


def test_a_vaga_barrada_vai_para_o_outro_lado():
    with _amb("2026-03-01 08:00:30", auto_rajada_max="1") as amb:
        _precos(amb, extra=["SOL/USDT"])
        _sinal("ATOM/USDT", "2026-03-01 08:00:00", 90)
        _sinal("ETC/USDT", "2026-03-01 08:00:00", 85)
        _sinal("SOL/USDT", "2026-03-01 08:00:00", 70, direcao="LONG")
        res = autotrader.auto_executar(None)
        assert _abertos(res) == ["ATOM/USDT", "SOL/USDT"]
        assert res["rajada"] == ["ETC/USDT"]


def test_17_de_novembro_com_o_teto_em_dois():
    """A manha que originou o card: um SHORT as 07:46 e tres na vela das 08:00. Com teto 2 e a
    janela padrao (30 min) abrem dois, e os outros dois envelhecem (12 min) ANTES de a janela
    andar -- barrar nao vira entrar atrasado no mesmo movimento."""
    with _amb("2026-03-01 07:46:30", auto_rajada_max="2") as amb:
        assert float(db.get_config()["auto_rajada_janela_min"]) == 30.0
        _precos(amb)
        _sinal("ATOM/USDT", "2026-03-01 07:46:00", 62)
        assert _abertos(autotrader.auto_executar(None)) == ["ATOM/USDT"]

        amb.relogio.agora = pd.Timestamp("2026-03-01 08:00:30")
        _sinal("ETC/USDT", "2026-03-01 08:00:00", 76)
        _sinal("BTC/USDT", "2026-03-01 08:00:00", 66)
        _sinal("DOGE/USDT", "2026-03-01 08:00:00", 65)
        res = autotrader.auto_executar(None)
        assert _abertos(res) == ["ETC/USDT"] and res["rajada"] == ["BTC/USDT", "DOGE/USDT"]

        abertos_depois = []
        for hhmm in ("08:05:00", "08:11:30", "08:13:00", "08:16:30", "08:20:00"):
            amb.relogio.agora = pd.Timestamp(f"2026-03-01 {hhmm}")
            abertos_depois += _abertos(autotrader.auto_executar(None))
        assert abertos_depois == []
        with db.conectar() as c:
            assert c.execute("SELECT COUNT(*) FROM posicoes").fetchone()[0] == 2


def test_a_janela_anda_e_o_lado_abre_de_novo():
    """E teto de ritmo, nao veto: a tendencia que continua dando sinal continua sendo operada."""
    with _amb("2026-03-01 08:00:30", auto_rajada_max="1") as amb:
        _precos(amb)
        _sinal("ATOM/USDT", "2026-03-01 08:00:00", 80)
        assert _abertos(autotrader.auto_executar(None)) == ["ATOM/USDT"]

        amb.relogio.agora = pd.Timestamp("2026-03-01 08:29:00")       # 29 min: ainda dentro
        _sinal("ETC/USDT", "2026-03-01 08:28:30", 80)
        res = autotrader.auto_executar(None)
        assert _abertos(res) == [] and res["rajada"] == ["ETC/USDT"]

        amb.relogio.agora = pd.Timestamp("2026-03-01 08:31:00")       # 31 min: a janela andou
        assert _abertos(autotrader.auto_executar(None)) == ["ETC/USDT"]


# ------------------------------------------------------------------ o que conta
def test_ordem_pendente_conta_e_ordem_expirada_nao():
    """Em post_only a decisao e a ORDEM. Contar so posicao deixaria tres ordens colocadas em
    ciclos seguidos passarem juntas; contar ordem que expirou barraria por exposicao que nunca
    existiu."""
    with _amb("2026-03-01 08:00:30", auto_rajada_max="1", exec_modo="post_only") as amb:
        _precos(amb)
        _sinal("ATOM/USDT", "2026-03-01 08:00:00", 80)
        res = autotrader.auto_executar(None)
        assert [a["tipo"] for a in res["abertos"]] == ["ordem"]

        amb.relogio.agora = pd.Timestamp("2026-03-01 08:05:00")
        _sinal("ETC/USDT", "2026-03-01 08:04:30", 80)
        res = autotrader.auto_executar(None)
        assert res["abertos"] == [] and res["rajada"] == ["ETC/USDT"]

        with db.conectar() as c:
            c.execute("UPDATE ordens SET status='expirada' WHERE ativo='ATOM/USDT'")
        assert _abertos(autotrader.auto_executar(None)) == ["ETC/USDT"]


def test_posicao_que_ja_stopou_ainda_conta():
    """Em 17/11 o primeiro stop bateu 18 minutos depois da entrada. Rajada cujo stop ja bateu
    ainda e a mesma rajada: se fechar tirasse da conta, o teto liberaria a proxima entrada
    exatamente quando o mercado acabou de dizer que o lado estava errado."""
    with _amb("2026-03-01 08:00:30", auto_rajada_max="1") as amb:
        _precos(amb)
        _sinal("ATOM/USDT", "2026-03-01 08:00:00", 80)
        assert _abertos(autotrader.auto_executar(None)) == ["ATOM/USDT"]

        amb.relogio.agora = pd.Timestamp("2026-03-01 08:10:00")
        amb.precos.mapa["ATOM/USDT"] = 104.0                          # passa do stop (103)
        simulador.atualizar()
        with db.conectar() as c:
            assert c.execute("SELECT status FROM posicoes").fetchone()[0] == "fechada"

        _sinal("ETC/USDT", "2026-03-01 08:09:30", 80)
        res = autotrader.auto_executar(None)
        assert res["abertos"] == [] and res["rajada"] == ["ETC/USDT"]


def test_entrada_manual_conta_mas_so_o_bot_e_barrado():
    with _amb("2026-03-01 08:00:30", auto_rajada_max="1") as amb:
        _precos(amb)
        with db.conectar() as c:                                      # o dono abriu um SHORT a mao
            c.execute("INSERT INTO posicoes(ativo,direcao,entrada,valor_reais,alavancagem,stop,"
                      "preco_atual,pnl,aberto_em,status) VALUES('ATOM/USDT','SHORT',100,50,2,103,"
                      "100,0,'2026-03-01 07:55:00','aberta')")
        _sinal("ETC/USDT", "2026-03-01 08:00:00", 80)
        _sinal("BTC/USDT", "2026-03-01 08:00:00", 70, direcao="LONG")
        res = autotrader.auto_executar(None)
        assert _abertos(res) == ["BTC/USDT"] and res["rajada"] == ["ETC/USDT"]
        # a mao continua livre: o teto mora no auto-trader, nao no simulador
        with db.conectar() as c:
            sid = c.execute("SELECT id FROM sinais WHERE ativo='ETC/USDT'").fetchone()[0]
        tipo, pid = simulador.executar(sid, 50.0, 2)
        assert tipo == "posicao" and pid > 0


def test_contagem_por_lado_separa_ordem_de_posicao_a_mercado():
    """Posicao que veio de ordem aparece nas duas tabelas e conta UMA vez."""
    with _amb("2026-03-01 08:00:30", exec_modo="post_only") as amb:
        _precos(amb)
        _sinal("ATOM/USDT", "2026-03-01 08:00:00", 80)
        autotrader.auto_executar(None)
        amb.precos.mapa["ATOM/USDT"] = 100.2                          # o preco vem ate a ordem
        simulador.processar_ordens()
        agora = pd.Timestamp("2026-03-01 08:01:00")
        assert autotrader._entradas_recentes(agora, 30) == {"LONG": 0, "SHORT": 1}
        assert autotrader._entradas_recentes(agora + pd.Timedelta(minutes=40), 30) == {"LONG": 0, "SHORT": 0}


# ------------------------------------------------------------------ catalogo e painel
def test_catalogo_aceita_a_faixa_e_recusa_o_resto(banco):
    from fastapi.testclient import TestClient
    import api
    cli = TestClient(api.app, client=("127.0.0.1", 5555))
    for chave in ("auto_rajada_max", "auto_rajada_janela_min"):
        assert api._validar_config(chave, db.CONFIG_PADRAO[chave]), chave
    for v in (0, 1, 2, 20):
        assert cli.post("/config", json={"auto_rajada_max": v}).status_code == 200, v
    for v in (-1, 2.5, 21, "muitas"):
        assert cli.post("/config", json={"auto_rajada_max": v}).status_code == 422, v
    assert cli.post("/config", json={"auto_rajada_janela_min": 0}).status_code == 422
    assert cli.post("/config", json={"auto_rajada_janela_min": 45}).status_code == 200
    racional = cli.get("/catalogo").json()["parametros"]["auto_rajada_max"]["racional"]
    assert "NÃO FOI MEDIDO" in racional                 # quem liga no painel le que e hipotese


def test_o_painel_mostra_as_duas_chaves_entre_as_guardas_e_marcadas_como_risco():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(raiz, "web", "app", "views", "apollo.js"), encoding="utf-8") as f:
        js = f.read()
    guardas = re.search(r"\['Guardas', \[([^\]]*)\]\]", js).group(1)
    risco = re.search(r"var RISCO = \{([^}]*)\}", js).group(1)
    nomes = re.search(r"var NOMES = \{(.*?)\};", js, re.S).group(1)
    for chave in ("auto_rajada_max", "auto_rajada_janela_min"):
        assert f"'{chave}'" in guardas and f"{chave}: 1" in risco and f"{chave}: '" in nomes
