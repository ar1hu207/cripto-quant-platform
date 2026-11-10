# -*- coding: utf-8 -*-
"""[TP-1] Take profit por estrutura: os alvos saem certos e o bot realiza neles, em parcelas."""
import json

import pytest

import alvos
import db
import simulador


def _velas(precos):
    """Velas sintéticas de 1h a partir de uma lista de closes (high/low a 0,2% do close)."""
    return [[i * 3_600_000, p, p * 1.002, p * 0.998, p, 1.0] for i, p in enumerate(precos)]


CFG = alvos.cfg_tp({"tp_ativo": "1"})


def test_pivos_acham_topo_e_fundo():
    import pandas as pd
    df = alvos._df(_velas([10, 11, 12, 13, 12, 11, 10, 9, 8, 9, 10, 11, 12]))
    topos, fundos = alvos.pivos(df, k=3)
    assert max(topos) == pytest.approx(13 * 1.002)
    assert min(fundos) == pytest.approx(8 * 0.998)
    assert isinstance(df, pd.DataFrame)


def test_zonas_juntam_niveis_proximos_e_somam_forca():
    zs = alvos.zonas([(100.0, 2), (100.2, 1), (110.0, 1)], tol=0.5)
    assert len(zs) == 2
    assert zs[0]["forca"] == 3
    assert zs[0]["preco"] == pytest.approx((200 + 100.2) / 3)


def test_alvos_ficam_do_lado_do_trade_e_antes_da_zona():
    zs = [{"preco": 95.0, "forca": 3}, {"preco": 90.0, "forca": 2}, {"preco": 105.0, "forca": 5}]
    tps = alvos.escolher_tps("SHORT", 100.0, 2.0, zs, atr1h=1.0, cfg=CFG)
    precos = [round(t["preco"], 2) for t in tps]
    assert 95.2 in precos and 90.2 in precos                         # 0,2 ATR antes da zona
    assert precos == sorted(precos, reverse=True)                    # do mais perto ao mais longe
    assert all(t["preco"] < 100 for t in tps)                       # nada acima da entrada num SHORT
    assert len(tps) == 3                                             # o 3o vem do fallback em R


def test_alvo_perto_demais_nao_entra():
    zs = [{"preco": 99.5, "forca": 9}]                               # 0,25R: não paga o risco
    tps = alvos.escolher_tps("SHORT", 100.0, 2.0, zs, atr1h=1.0, cfg=CFG)
    assert all(t["r"] >= 1.0 for t in tps)


def _pos(banco, plano, valor=1000.0, entrada=100.0, stop=103.0):
    with db.conectar() as c:
        c.execute("INSERT INTO posicoes(ativo,direcao,entrada,valor_reais,alavancagem,stop,"
                  "stop_abertura,risco_abertura,preco_atual,pnl,aberto_em,status,conviccao,tps) "
                  "VALUES('X/USDT','SHORT',?,?,10,?,?,100,?,0,'2026-11-06 09:00:00','aberta',70,?)",
                  (entrada, valor, stop, stop, entrada, json.dumps(plano)))
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def _plano(valor=1000.0):
    niv = [{"preco": 95.0, "r": 0.5, "frac": 0.34, "feito": False, "forca": 2, "fonte": "estrutura"},
           {"preco": 90.0, "r": 1.0, "frac": 0.33, "feito": False, "forca": 2, "fonte": "estrutura"},
           {"preco": 85.0, "r": 1.5, "frac": 0.33, "feito": False, "forca": 2, "fonte": "estrutura"}]
    return {"niveis": niv, "valor_inicial": valor, "r_preco": 10.0, "calc_em": "t"}


@pytest.fixture
def tp_ligado(banco, sem_rede, monkeypatch):
    db.set_config("tp_ativo", "1")
    db.set_config("trailing_ativo", "0")              # isola o TP do trailing
    monkeypatch.setattr(simulador, "_precos_em_lote", lambda ativos: {})
    return sem_rede


def _trades():
    with db.conectar() as c:
        return [dict(r) for r in c.execute("SELECT * FROM trades ORDER BY id")]


def test_tp1_fecha_um_terco_e_a_posicao_segue_aberta(tp_ligado):
    pid = _pos(None, _plano())
    banca0 = db.get_banca()["atual"]
    tp_ligado(94.0)                                    # passou do TP1 (95), não do TP2 (90)
    simulador.atualizar()
    t = _trades()
    assert [x["motivo_saida"] for x in t] == ["tp1"]
    assert t[0]["valor_reais"] == pytest.approx(340.0)
    assert t[0]["saida"] == 95.0                       # limite que já existia enche no preço DELE
    with db.conectar() as c:
        p = dict(c.execute("SELECT * FROM posicoes WHERE id=?", (pid,)).fetchone())
    assert p["status"] == "aberta"
    assert p["valor_reais"] == pytest.approx(660.0)
    assert p["risco_abertura"] == pytest.approx(66.0)
    assert json.loads(p["tps"])["niveis"][0]["feito"] is True
    assert db.get_banca()["atual"] == pytest.approx(banca0 + t[0]["pnl_reais"])
    assert t[0]["pnl_reais"] > 0


def test_tp3_fecha_o_resto_e_a_soma_das_parcelas_e_a_posicao_inteira(tp_ligado):
    pid = _pos(None, _plano())
    tp_ligado(84.0)                                    # passou dos três no mesmo ciclo
    simulador.atualizar()
    t = _trades()
    assert [x["motivo_saida"] for x in t] == ["tp1", "tp2", "tp3"]
    assert sum(x["valor_reais"] for x in t) == pytest.approx(1000.0)
    with db.conectar() as c:
        st = c.execute("SELECT status FROM posicoes WHERE id=?", (pid,)).fetchone()[0]
    assert st == "fechada"


def test_stop_decide_antes_do_tp(tp_ligado):
    _pos(None, _plano(), stop=95.5)                    # stop (trailado) entre o preço e o TP1
    tp_ligado(96.0)                                    # SHORT: 96 >= stop 95,5 -> stop
    simulador.atualizar()
    assert [x["motivo_saida"].split("-")[0] for x in _trades()] == ["trailing"]


def test_tp_desligado_nao_faz_nada(banco, sem_rede, monkeypatch):
    monkeypatch.setattr(simulador, "_precos_em_lote", lambda ativos: {})
    db.set_config("trailing_ativo", "0")
    _pos(None, _plano())
    sem_rede(84.0)
    simulador.atualizar()
    assert _trades() == []


def test_plano_calculado_agora_realiza_a_mercado_no_preco_de_agora(tp_ligado, monkeypatch):
    """Posição aberta antes da regra: o alvo que o preço já passou não tinha ordem lá."""
    with db.conectar() as c:
        c.execute("INSERT INTO posicoes(ativo,direcao,entrada,valor_reais,alavancagem,stop,"
                  "stop_abertura,preco_atual,pnl,aberto_em,status,conviccao) "
                  "VALUES('X/USDT','SHORT',100,1000,10,103,103,100,0,'2026-11-06 09:00:00','aberta',70)")
    precos = [100 + (i % 20) - 10 for i in range(300)]           # serra entre 90 e 110
    monkeypatch.setattr(simulador.ex, "fetch_ohlcv", lambda *a, **k: _velas(precos))
    tp_ligado(80.0)
    simulador.atualizar()
    t = _trades()
    assert t, "nenhum TP realizado"
    assert all(x["saida"] == 80.0 for x in t)


def test_falha_ao_calcular_alvos_nao_tira_a_posicao_do_stop(tp_ligado, monkeypatch):
    with db.conectar() as c:
        c.execute("INSERT INTO posicoes(ativo,direcao,entrada,valor_reais,alavancagem,stop,"
                  "stop_abertura,preco_atual,pnl,aberto_em,status,conviccao) "
                  "VALUES('X/USDT','SHORT',100,1000,10,103,103,100,0,'2026-11-06 09:00:00','aberta',70)")

    def quebra(*a, **k):
        raise RuntimeError("rede")
    monkeypatch.setattr(simulador.ex, "fetch_ohlcv", quebra)
    tp_ligado(97.0)
    simulador.atualizar()
    assert simulador.ultima_marcacao["ok"] == 1         # a marcação seguiu
    with db.conectar() as c:
        assert c.execute("SELECT preco_atual FROM posicoes").fetchone()[0] == 97.0
    tp_ligado(104.0)
    simulador.atualizar()
    assert [x["motivo_saida"].split("-")[0] for x in _trades()] == ["stop"]
