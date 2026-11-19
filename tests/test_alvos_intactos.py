# -*- coding: utf-8 -*-
"""[SR-2] `tp_so_intactos`: os alvos so usam pivos que nenhum fechamento posterior atravessou.

Nasce desligada (o plano sai identico ao de antes). Ligada, um fundo furado por fechamento deixa
de ser alvo de SHORT, um pavio alem do nivel nao o rompe, e Fibonacci nao muda.
"""
import api
import alvos
import db

H4 = 4 * 3600 * 1000


def _raw(lows, closes, highs=None):
    n = len(lows)
    highs = highs or [c + 1 for c in closes]
    return [[i * H4, c, h, lo, c, 1.0] for i, (lo, h, c) in enumerate(zip(lows, highs, closes))]


def _df(lows, closes, highs=None):
    return alvos._df(_raw(lows, closes, highs))


# fundo em 90 (vela 5) e fundo em 80 (vela 15); a vela 25 FECHA em 85, abaixo do 90 -> 90 rompido
LOWS = [100.0] * 5 + [90.0] + [100.0] * 9 + [80.0] + [100.0] * 9 + [84.0] + [100.0] * 9
CLOSES = [101.0] * 5 + [95.0] + [101.0] * 9 + [85.0] + [101.0] * 9 + [85.0] + [101.0] * 9


def test_fundo_furado_por_fechamento_sai_e_o_intacto_fica():
    _, todos = alvos.pivos(_df(LOWS, CLOSES))
    _, intactos = alvos.pivos_intactos(_df(LOWS, CLOSES))
    assert {90.0, 80.0} <= set(todos)
    assert 90.0 not in intactos and 80.0 in intactos


def test_pavio_alem_do_nivel_sem_fechamento_nao_rompe():
    closes = list(CLOSES); closes[15] = closes[25] = 91.0   # pavios a 80 e 84, fechos acima de 90
    _, intactos = alvos.pivos_intactos(_df(LOWS, closes))
    assert 90.0 in intactos


def test_topo_furado_por_fechamento_sai():
    highs = [102.0] * 5 + [110.0] + [102.0] * 20
    closes = [101.0] * 20 + [111.0] + [101.0] * 5       # fechou acima de 110
    topos, _ = alvos.pivos_intactos(_df([99.0] * 26, closes, highs))
    assert 110.0 not in topos
    topos_ok, _ = alvos.pivos_intactos(_df([99.0] * 26, [101.0] * 26, highs))
    assert 110.0 in topos_ok


def test_vazio_nao_quebra():
    assert alvos.pivos_intactos(_df([], [])) == ([], [])


def test_cfg_tp_le_a_chave_e_nasce_desligada():
    assert db.CONFIG_PADRAO["tp_so_intactos"] == "0"
    assert alvos.cfg_tp({})["so_intactos"] is False
    assert alvos.cfg_tp({"tp_so_intactos": "1"})["so_intactos"] is True


def test_calcular_desligado_e_o_plano_de_antes_e_ligado_tira_o_rompido():
    """SHORT em 100 com stop em 102 (R = 2): o fundo rompido em 90 esta a 5R e era alvo; ligado, sai."""
    raw4 = _raw(LOWS, CLOSES)
    raw1 = _raw([100.0] * 40, [101.0] * 40)
    pos = {"entrada": 100.0, "stop_abertura": 102.0, "direcao": "SHORT", "valor_reais": 100.0}
    cfg = alvos.cfg_tp({"tp_n": "3", "tp_min_r": "2", "tp_forca_min": "2", "tp_fracoes": "0.34", "tp_resto_livre": "1"})
    antes = alvos.calcular(pos, raw1, raw4, dict(cfg, so_intactos=False))
    depois = alvos.calcular(pos, raw1, raw4, dict(cfg, so_intactos=True))
    perto = lambda pl, nivel: any(abs(t["preco"] - nivel) < 1.0 for t in pl["niveis"])
    assert perto(antes, 90.0)
    assert not perto(depois, 90.0)


def test_catalogo(banco):
    assert api._validar_config("tp_so_intactos", "1") == "1"
    assert api._validar_config("tp_so_intactos", db.CONFIG_PADRAO["tp_so_intactos"]) == "0"
