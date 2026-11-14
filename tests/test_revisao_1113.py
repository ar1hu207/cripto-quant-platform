# -*- coding: utf-8 -*-
"""Furos achados na revisao completa de 2026-11-13 (base be2f87f). Cada teste afirma a REGRA
e falhava antes da correcao que veio no mesmo commit. O relatorio com o porque de cada um
esta em `REVISAO-2026-11-13.md`, na raiz.

Grupos: tp (alvos que criam dinheiro), entrada (margem e alavancagem), panico (corrida com o
bot), scan (duas varreduras ao mesmo tempo), borda (o que a API aceita de fora), segredo (o
token que saia em todo poll), mercado (um par ruim derrubando o lote).
"""
import json
import threading
import time

import pandas as pd
import pytest

import alvos
import autotrader
import db
import dca
import mercado
import signal_engine
import simulador
from conftest import semear_posicao, semear_sinal


@pytest.fixture
def cliente(banco):
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app, client=("127.0.0.1", 5555))


def _banca():
    return db.get_banca()["atual"]


def _n(tabela, where=""):
    with db.conectar() as c:
        return c.execute(f"SELECT COUNT(*) FROM {tabela} {where}").fetchone()[0]


def _status(sid):
    with db.conectar() as c:
        return c.execute("SELECT status FROM sinais WHERE id=?", (sid,)).fetchone()[0]


# ====================================================================== tp
@pytest.mark.parametrize("chave,valor", [
    ("tp_fracoes", "-0.5,1.5"),        # soma 1, primeira fracao negativa: creditava dinheiro
    ("tp_fracoes", "0,1"),             # fracao zero: parcial de nada
    ("tp_fracoes", "nan,0.5"),
    ("tp_fracoes", "0.5,abc"),
    ("tp_fracoes", ""),
    ("tp_fracoes", "0.2,0.2,0.2,0.2,0.2,0.2"),   # mais alvos do que `tp_n` admite
    ("tp_fallback_r", "-2,4"),         # alvo do lado do prejuizo: "batia" na hora
    ("tp_fallback_r", "0,2"),          # alvo em cima da entrada
    ("tp_fallback_r", "inf"),
])
def test_tp_config_de_alvo_invalida_e_recusada(cliente, chave, valor):
    r = cliente.post("/config", json={chave: valor})
    assert r.status_code == 422, r.text
    assert db.get_config()[chave] == db.CONFIG_PADRAO[chave]      # nada foi gravado


def test_tp_config_valida_continua_aceita(cliente):
    r = cliente.post("/config", json={"tp_fracoes": "0.5, 0.25,0.25", "tp_fallback_r": "1.5,3,6"})
    assert r.status_code == 200, r.text
    cfg = alvos.cfg_tp(db.get_config())
    assert cfg["tp_fracoes"] == [0.5, 0.25, 0.25] and cfg["tp_fallback_r"] == [1.5, 3.0, 6.0]


@pytest.mark.parametrize("frac", [-0.5, 0.0, 1.0, 1.5, float("nan")])
def test_tp_fechar_parcial_recusa_fracao_fora_de_0_1(banco, sem_rede, frac):
    """A defesa em profundidade: mesmo com lixo ja gravado no plano da posicao, uma fracao que
    nao e parte de um todo nao mexe em banca nem em margem."""
    pid = semear_posicao(valor_reais=100.0, alavancagem=2, stop=95.0)
    with db.conectar() as c:
        pos = dict(c.execute("SELECT * FROM posicoes WHERE id=?", (pid,)).fetchone())
    antes = _banca()
    with pytest.raises(ValueError):
        simulador.fechar_parcial(pos, frac, "tp1", 110.0, {"niveis": []})
    assert _banca() == antes
    with db.conectar() as c:
        assert c.execute("SELECT valor_reais FROM posicoes WHERE id=?", (pid,)).fetchone()[0] == 100.0
    assert _n("trades") == 0


def test_tp_politica_com_lixo_no_banco_cai_no_padrao(banco):
    """Config gravada antes da validacao existir (ou por fora da rota) nao vira plano de TP."""
    with db.conectar() as c:
        c.execute("UPDATE config SET valor='-0.5,1.5' WHERE chave='tp_fracoes'")
        c.execute("UPDATE config SET valor='-2,0' WHERE chave='tp_fallback_r'")
    cfg = alvos.cfg_tp(db.get_config())
    assert cfg["tp_fracoes"] == [0.34, 0.33, 0.33]
    assert cfg["tp_fallback_r"] == [2.0, 4.0, 6.0]


def test_tp_plano_gravado_com_fracao_ruim_nao_credita(banco, sem_rede):
    """Ponta a ponta: plano ja gravado na posicao com fracao negativa (config antiga). O ciclo
    de marcacao nao pode mexer na banca por causa dele."""
    db.set_config("tp_ativo", "1")
    pid = semear_posicao(valor_reais=100.0, alavancagem=2, stop=95.0)
    plano = {"niveis": [{"preco": 105.0, "r": 1.0, "frac": -0.5, "feito": False, "fonte": "R"},
                        {"preco": 120.0, "r": 4.0, "frac": 1.5, "feito": False, "fonte": "R"}],
             "valor_inicial": 100.0, "r_preco": 5.0}
    with db.conectar() as c:
        c.execute("UPDATE posicoes SET tps=?, stop_abertura=95.0 WHERE id=?", (json.dumps(plano), pid))
    antes = _banca()
    sem_rede(106.0)                            # passou do "TP1"
    simulador.atualizar()
    assert _banca() == antes
    with db.conectar() as c:
        assert c.execute("SELECT valor_reais FROM posicoes WHERE id=?", (pid,)).fetchone()[0] == 100.0
