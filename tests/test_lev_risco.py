# -*- coding: utf-8 -*-
"""[LEV-1] Alavancagem pela conta do trade: risco / (stop x margem por slot)."""
import pytest

import autotrader

CFG = {"auto_lev_modo": "risco", "risco_por_trade": "0.015", "exposicao_max": "0.5",
       "auto_max_posicoes": "5", "auto_lev_max": "20", "alavancagem_padrao": "10"}


@pytest.mark.parametrize("stop, esperado", [(0.0166, 10.0), (0.0296, 6.0), (0.05, 3.0), (0.004, 20.0)])
def test_stop_curto_mais_alavancagem_stop_largo_menos(stop, esperado):
    assert autotrader._alavancagem(CFG, 70, stop, "X/USDT") == esperado


def test_todo_slot_prende_no_maximo_a_mesma_margem():
    banca = 10_000.0
    for stop in (0.008, 0.0166, 0.0296, 0.05, 0.09):
        lev = autotrader._alavancagem(CFG, 70, stop, "X/USDT")
        margem = autotrader._tamanho(banca, 0.015, lev, 100.0, 100.0 * (1 - stop), 0.25)
        if lev * stop <= autotrader.FOLGA_LIQ * 0.9:          # fora do cap geométrico
            assert margem <= banca * 0.10 + 0.01


def test_a_liquidacao_segue_atras_do_stop():
    for stop in (0.004, 0.02, 0.06, 0.12):
        lev = autotrader._alavancagem(CFG, 70, stop, "X/USDT")
        assert lev * stop <= autotrader.FOLGA_LIQ * 0.9 + 1e-9 or lev == 1.0


def test_margem_fixada_a_mao_manda():
    assert autotrader._alavancagem(dict(CFG, auto_lev_margem_frac="0.05"), 70, 0.0296, "X") == 11.0


def test_sem_stop_cai_no_fixo():
    assert autotrader._alavancagem(CFG, 70, None, "X/USDT") == 10.0
