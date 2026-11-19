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


# ---------------------------------------------------------------------------------------------
# [TP-2] Resto livre: o último alvo realiza só a fração dele, e o que sobra fica com o trailing.
# Nasceu da autópsia T50 (232 trades reais) e do T51 (45 meses): TP2 e TP3 são teto.
# ---------------------------------------------------------------------------------------------
def _plano_um_alvo(resto_livre, frac=0.34, valor=1000.0):
    p = {"niveis": [{"preco": 95.0, "r": 1.67, "frac": frac, "feito": False, "forca": 0, "fonte": "R"}],
         "valor_inicial": valor, "r_preco": 3.0, "calc_em": "t"}
    if resto_livre:
        p["resto_livre"] = True
    return p


def _posicao(pid):
    with db.conectar() as c:
        return dict(c.execute("SELECT * FROM posicoes WHERE id=?", (pid,)).fetchone())


def test_tp2_fracoes_valem_como_escritas_so_com_resto_livre():
    assert alvos.fracoes({"tp_fracoes": [0.34], "resto_livre": True}, 1) == [0.34]
    # sem a chave, um alvo só é a posição inteira: é por isso que `tp_n=1` sozinho não serve
    assert alvos.fracoes({"tp_fracoes": [0.34]}, 1) == [1.0]
    assert alvos.fracoes({"tp_fracoes": [0.34], "resto_livre": False}, 1) == [1.0]
    # e a lista não é completada até o número de níveis: nível sem fração não é alvo
    assert alvos.fracoes({"tp_fracoes": [0.34], "resto_livre": True}, 3) == [0.34]
    assert alvos.fracoes({"tp_fracoes": [0.34, 0.33], "resto_livre": True}, 3) == [0.34, 0.33]
    assert alvos.fracoes({"tp_fracoes": [0.34]}, 3) == pytest.approx([1 / 3, 1 / 3, 1 / 3])


def test_tp2_fracoes_que_passam_de_um_sao_normalizadas_mesmo_com_resto_livre():
    fr = alvos.fracoes({"tp_fracoes": [0.8, 0.8], "resto_livre": True}, 2)
    assert fr == pytest.approx([0.5, 0.5])                 # nunca vende mais do que a posição tem


def test_tp2_a_chave_nasce_desligada_e_o_cfg_a_le():
    assert db.CONFIG_PADRAO["tp_resto_livre"] == "0"
    assert alvos.cfg_tp({"tp_ativo": "1"})["resto_livre"] is False
    assert alvos.cfg_tp({"tp_ativo": "1", "tp_resto_livre": "1"})["resto_livre"] is True


def test_tp2_o_plano_grava_a_regra_so_quando_ligada():
    pos = {"entrada": 100.0, "stop_abertura": 103.0, "direcao": "SHORT", "valor_reais": 1000.0}
    velas = _velas([100 + (i % 20) - 10 for i in range(300)])
    desligado = alvos.calcular(pos, velas, velas, alvos.cfg_tp({"tp_ativo": "1"}))
    assert "resto_livre" not in desligado                  # plano de quem não usa: igual ao de antes
    cfg = alvos.cfg_tp({"tp_ativo": "1", "tp_resto_livre": "1", "tp_n": "1", "tp_fracoes": "0.34",
                        "tp_min_r": "2", "tp_max_r": "2"})
    ligado = alvos.calcular(pos, velas, velas, cfg)
    assert ligado["resto_livre"] is True
    assert [(t["r"], t["frac"], t["fonte"]) for t in ligado["niveis"]] == [(2.0, 0.34, "R")]
    assert ligado["niveis"][0]["preco"] == pytest.approx(94.0)   # SHORT: entrada - 2R


def test_tp2_tirar_tp2_e_tp3_nao_muda_o_tp1():
    """A conta que roda sem TP2 e TP3 tem que ter o MESMO TP1 de quem roda os três: os níveis
    são escolhidos com o mesmo `tp_n` e só depois cortados. Baixar `tp_n` para 1 escolheria
    outro nível (a zona forte mais próxima, sem o 2R de reserva) e a comparação entre as contas
    deixaria de ter uma diferença só."""
    pos = {"entrada": 100.0, "stop_abertura": 103.0, "direcao": "SHORT", "valor_reais": 1000.0}
    velas = _velas([100 + (i % 20) - 10 for i in range(300)])
    base = {"tp_ativo": "1", "tp_n": "3", "tp_min_r": "2", "tp_max_r": "8"}
    tres = alvos.calcular(pos, velas, velas, alvos.cfg_tp(base))
    um = alvos.calcular(pos, velas, velas, alvos.cfg_tp(
        {**base, "tp_fracoes": "0.34", "tp_resto_livre": "1"}))
    assert len(tres["niveis"]) == 3 and len(um["niveis"]) == 1
    for k in ("preco", "r", "fonte", "forca"):
        assert um["niveis"][0][k] == tres["niveis"][0][k]
    assert um["niveis"][0]["frac"] == tres["niveis"][0]["frac"] == 0.34
    assert um["resto_livre"] is True and "resto_livre" not in tres
    # dois alvos e um terço livre também é uma política válida
    dois = alvos.calcular(pos, velas, velas, alvos.cfg_tp(
        {**base, "tp_fracoes": "0.34,0.33", "tp_resto_livre": "1"}))
    assert [t["frac"] for t in dois["niveis"]] == [0.34, 0.33]
    assert [t["preco"] for t in dois["niveis"]] == [t["preco"] for t in tres["niveis"][:2]]


def test_tp2_tp1_realiza_a_fracao_e_o_resto_segue_aberto_sem_alvo(tp_ligado):
    pid = _pos(None, _plano_um_alvo(True))
    tp_ligado(94.0)
    simulador.atualizar()
    t = _trades()
    assert [x["motivo_saida"] for x in t] == ["tp1"]
    assert t[0]["valor_reais"] == pytest.approx(340.0)
    assert t[0]["saida"] == 95.0
    p = _posicao(pid)
    assert p["status"] == "aberta"
    assert p["valor_reais"] == pytest.approx(660.0)
    assert p["risco_abertura"] == pytest.approx(66.0)
    tp_ligado(60.0)                                        # anda muito mais: não há alvo para bater
    simulador.atualizar()
    simulador.atualizar()
    assert [x["motivo_saida"] for x in _trades()] == ["tp1"]
    p = _posicao(pid)
    assert p["status"] == "aberta" and p["valor_reais"] == pytest.approx(660.0)


def test_tp2_sem_a_regra_no_plano_o_ultimo_alvo_continua_levando_tudo(tp_ligado):
    """O comportamento do TP-1 não muda: plano antigo, ou de conta que não ligou a chave."""
    pid = _pos(None, _plano_um_alvo(False))
    tp_ligado(94.0)
    simulador.atualizar()
    t = _trades()
    assert [x["motivo_saida"] for x in t] == ["tp1"]
    assert t[0]["valor_reais"] == pytest.approx(1000.0)
    assert _posicao(pid)["status"] == "fechada"


def test_tp2_a_regra_e_do_plano_e_nao_da_config_do_ciclo(tp_ligado):
    """Ligar a chave no meio da vida de uma posição não muda o plano com que ela nasceu."""
    db.set_config("tp_resto_livre", "1")
    pid = _pos(None, _plano())                             # plano antigo, três alvos, sem a regra
    tp_ligado(84.0)
    simulador.atualizar()
    assert [x["motivo_saida"] for x in _trades()] == ["tp1", "tp2", "tp3"]
    assert _posicao(pid)["status"] == "fechada"


def test_tp2_fracoes_que_somam_a_posicao_inteira_fecham_tudo_no_ultimo_alvo(tp_ligado):
    plano = _plano()
    plano["resto_livre"] = True
    pid = _pos(None, plano)
    tp_ligado(84.0)
    simulador.atualizar()
    t = _trades()
    assert [x["motivo_saida"] for x in t] == ["tp1", "tp2", "tp3"]
    assert sum(x["valor_reais"] for x in t) == pytest.approx(1000.0)
    assert _posicao(pid)["status"] == "fechada"            # não sobra posição de centavos


def test_tp2_o_resto_sai_pelo_trailing_onde_o_movimento_acabar(tp_ligado):
    db.set_config("trailing_ativo", "1")
    db.set_config("trailing_unidade", "R")
    db.set_config("trailing_arma_r", "3")
    db.set_config("trailing_dist_r", "3")
    pid = _pos(None, _plano_um_alvo(True))                 # SHORT 100, stop 103: 1R = 3
    tp_ligado(94.0)
    simulador.atualizar()                                  # TP1: 34% a 95
    tp_ligado(79.0)
    simulador.atualizar()                                  # +7R: trailing arma, stop vai a 79 + 9 = 88
    assert _posicao(pid)["stop"] == pytest.approx(88.0)
    assert [x["motivo_saida"] for x in _trades()] == ["tp1"]
    tp_ligado(88.5)
    simulador.atualizar()                                  # devolveu 3R do pico: o trailing fecha o resto
    t = _trades()
    assert [x["motivo_saida"].split("-")[0] for x in t] == ["tp1", "trailing"]
    assert t[1]["valor_reais"] == pytest.approx(660.0)
    assert t[1]["saida"] == 88.5                           # 3,8R no resto: um TP2/TP3 teria vendido antes
    assert _posicao(pid)["status"] == "fechada"
    assert sum(x["valor_reais"] for x in t) == pytest.approx(1000.0)


def test_tp2_o_stop_de_abertura_continua_valendo_para_o_resto(tp_ligado):
    """Depois do TP1 o resto NÃO vai para o zero a zero (T51: K1BE não passou)."""
    pid = _pos(None, _plano_um_alvo(True))
    tp_ligado(94.0)
    simulador.atualizar()
    assert _posicao(pid)["stop"] == pytest.approx(103.0)
    tp_ligado(104.0)
    simulador.atualizar()
    t = _trades()
    assert [x["motivo_saida"].split("-")[0] for x in t] == ["tp1", "stop"]
    assert t[1]["valor_reais"] == pytest.approx(660.0)


def test_tp2_o_post_config_aceita_a_chave_e_recusa_lixo(banco):
    import api
    assert api._validar_config("tp_resto_livre", "1") == "1"
    assert api._validar_config("tp_resto_livre", "0") == "0"
    with pytest.raises(ValueError):
        api._validar_config("tp_resto_livre", "talvez")


def test_tp2_o_painel_diz_que_o_resto_nao_tem_teto(banco):
    """Com resto livre, o ultimo alvo nao e "meta final": o rotulo nao pode prometer um teto."""
    import signal_engine
    db.set_config("tp_ativo", "1")
    pos = {"direcao": "SHORT", "entrada": 100.0, "stop": 103.0, "stop_abertura": 103.0, "preco_atual": 99.0,
           "tps": json.dumps(_plano())}
    _, texto, _ = signal_engine._plano_do_bot(pos, db.get_config())
    assert "meta final" in texto and "resto sem teto" not in texto
    plano = _plano()
    plano["resto_livre"] = True
    pos["tps"] = json.dumps(plano)
    _, texto, _ = signal_engine._plano_do_bot(pos, db.get_config())
    assert "resto sem teto" in texto and "meta final" not in texto


# ------------------------------------------------ [TP-3] stop no 0x0 depois do TP1

def _stop(pid):
    with db.conectar() as c:
        return dict(c.execute("SELECT status, stop FROM posicoes WHERE id=?", (pid,)).fetchone())


def test_tp_stop_entrada_nasce_desligado_e_o_catalogo_aceita_bool():
    import api
    assert db.CONFIG_PADRAO["tp_stop_entrada"] == "0"
    assert alvos.cfg_tp({"tp_ativo": "1"})["stop_entrada"] is False
    assert api._validar_config("tp_stop_entrada", "1") == "1"
    with pytest.raises(Exception):
        api._validar_config("tp_stop_entrada", "talvez")


def test_sem_a_chave_o_tp1_nao_mexe_no_stop(tp_ligado):
    pid = _pos(None, _plano())
    tp_ligado(94.0)
    simulador.atualizar()
    assert _stop(pid) == {"status": "aberta", "stop": 103.0}


def test_com_a_chave_o_tp1_leva_o_stop_para_a_entrada_e_a_volta_fecha(tp_ligado):
    db.set_config("tp_stop_entrada", "1")
    pid = _pos(None, _plano())
    tp_ligado(94.0)                                    # TP1 (95) enche
    simulador.atualizar()
    assert _stop(pid) == {"status": "aberta", "stop": 100.0}
    tp_ligado(100.0)                                   # SHORT voltou na entrada
    simulador.atualizar()
    assert _stop(pid)["status"] == "fechada"
    t = _trades()
    assert [x["motivo_saida"].split("-")[0] for x in t][0] == "tp1"
    assert len(t) == 2 and t[1]["valor_reais"] == pytest.approx(660.0)
    assert -0.02 * 660.0 < t[1]["pnl_reais"] < 0      # só a taxa; o stop cheio seria -30% (3% x 10x)


def test_tp1_feito_antes_da_chave_tambem_ganha_o_stop_na_entrada(tp_ligado):
    pl = _plano()
    pl["niveis"][0]["feito"] = True
    pid = _pos(None, pl, valor=660.0)
    db.set_config("tp_stop_entrada", "1")
    tp_ligado(98.0)                                    # longe dos alvos; só o estado do TP1 conta
    simulador.atualizar()
    assert _stop(pid) == {"status": "aberta", "stop": 100.0}


def test_stop_ja_alem_da_entrada_nao_volta(tp_ligado):
    db.set_config("tp_stop_entrada", "1")
    pid = _pos(None, _plano(), stop=103.0)
    with db.conectar() as c:                            # trailing já trouxe o stop para 97 (SHORT)
        c.execute("UPDATE posicoes SET stop=97.0 WHERE id=?", (pid,))
    tp_ligado(94.0)
    simulador.atualizar()
    assert _stop(pid) == {"status": "aberta", "stop": 97.0}
