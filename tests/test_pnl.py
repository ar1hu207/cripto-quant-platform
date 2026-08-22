# -*- coding: utf-8 -*-
"""Item 2 do [P2-6]: `simulador._pnl()` e `simulador._preco_liquidacao()`.

Aqui mora a aritmetica que decide quanto o historico de pesquisa registra. Um erro de sinal
ou de fator nao levanta excecao nenhuma -- ele so grava um numero errado, para sempre, e o
M4 depois mede estrategia em cima dele. Por isso as asseracoes sao de VALOR, com a conta
escrita ao lado, e nao de "nao explodiu".
"""
import pytest

import db
import simulador
from conftest import semear_posicao


def pos(direcao="LONG", entrada=100.0, valor=100.0, lev=10, stop=95.0):
    return {"direcao": direcao, "entrada": entrada, "valor_reais": valor,
            "alavancagem": lev, "stop": stop}


# ---------------------------------------------------------------- _pnl: direcao e fator

def test_long_ganha_com_o_preco_subindo(banco):
    """+1% no ativo a 10x = +10% sobre a margem. R$100 -> +R$10 bruto, menos a taxa dos
    dois lados (2 x 0,05% x R$1.000 nocional = R$1) = +R$9. E a conta que o `test_sim.py`
    conferia com um print; aqui ela falha se mudar."""
    pnl, taxa, move = simulador._pnl(pos(), 101.0)
    assert move == pytest.approx(0.01)
    assert taxa == pytest.approx(1.0)
    assert pnl == pytest.approx(9.0)


def test_short_ganha_com_o_preco_caindo(banco):
    """O `d = 1 if LONG else -1` e a unica coisa que separa lucro de prejuizo aqui.
    Simetria com o LONG: mesmo modulo, mesma taxa."""
    pnl, taxa, move = simulador._pnl(pos(direcao="SHORT"), 99.0)
    assert move == pytest.approx(0.01)
    assert pnl == pytest.approx(9.0)


def test_short_perde_com_o_preco_subindo(banco):
    pnl, _, move = simulador._pnl(pos(direcao="SHORT"), 101.0)
    assert move == pytest.approx(-0.01)
    assert pnl == pytest.approx(-11.0)          # -10 de bruto, -1 de taxa


def test_alavancagem_multiplica_o_resultado_e_a_taxa(banco):
    """A taxa e cobrada sobre o NOCIONAL, entao ela escala com a alavancagem junto com o
    P&L -- que e a razao de "a taxa decide" no README."""
    p1, t1, _ = simulador._pnl(pos(lev=1), 101.0)
    p10, t10, _ = simulador._pnl(pos(lev=10), 101.0)
    assert (p1, t1) == (pytest.approx(0.9), pytest.approx(0.1))
    assert (p10, t10) == (pytest.approx(9.0), pytest.approx(1.0))


def test_taxa_le_a_config_e_conta_os_dois_lados(banco):
    db.set_config("taxa_por_lado", "0.001")
    _, taxa, _ = simulador._pnl(pos(), 100.0)
    assert taxa == pytest.approx(2.0)           # 2 x 0,1% x R$1.000


def test_taxa_invalida_na_config_cai_no_padrao(banco):
    """Mesmo [P1-8] de `guarda_risco`: config podre nao pode virar excecao no meio de um
    fechamento -- a posicao ficaria aberta sem ninguem saber por que."""
    db.set_config("taxa_por_lado", "muito")
    _, taxa, _ = simulador._pnl(pos(), 100.0)
    assert taxa == pytest.approx(1.0)


# ---------------------------------------------------------------- _pnl: o cap na margem

def test_nunca_perde_mais_que_a_margem(banco):
    """Paper trading sem chamada de margem: o maximo que se perde e o que se pos. Sem o
    cap, um gap de -50% a 10x gravaria -R$501 numa posicao de R$100 e a banca ficaria
    negativa."""
    pnl, _, move = simulador._pnl(pos(), 50.0)
    assert move == pytest.approx(-0.5)          # o movimento do ativo continua honesto
    assert pnl == pytest.approx(-100.0)         # o P&L e que fica capado na margem


def test_o_cap_nao_atrapalha_o_lucro(banco):
    pnl, _, _ = simulador._pnl(pos(), 150.0)
    assert pnl == pytest.approx(499.0)          # 100 x 10 x 0,5 - 1 de taxa


def test_perda_dentro_da_margem_passa_intacta(banco):
    pnl, _, _ = simulador._pnl(pos(), 99.5)
    assert pnl == pytest.approx(-6.0)           # -5 de bruto, -1 de taxa


# ---------------------------------------------------------------- _pnl: guardas de ÷0

@pytest.mark.parametrize("campo", ["entrada", "alavancagem"])
def test_entrada_ou_alavancagem_zero_devolve_zeros(banco, campo):
    """Posicao degenerada nao pode virar ZeroDivisionError dentro do `for` do ciclo: era
    exatamente esse tipo de excecao que o [P1-1] mostrou ser capaz de deixar as outras
    posicoes sem stop."""
    p = pos()
    p[campo] = 0
    assert simulador._pnl(p, 101.0) == (0.0, 0.0, 0.0)


# ---------------------------------------------------------------- _preco_liquidacao

@pytest.mark.parametrize("entrada,d,lev,esperado", [
    (100.0, 1, 10, 91.0),        # LONG: 100 x (1 - 0,9/10)
    (100.0, -1, 10, 109.0),      # SHORT: espelhado acima da entrada
    (100.0, 1, 20, 95.5),        # o dobro de alavancagem, metade da distancia
    (100.0, 1, 1, 10.0),         # 1x: so liquida com -90%
    (100.0, 1, 100, 99.1),
])
def test_preco_liquidacao(entrada, d, lev, esperado):
    assert simulador._preco_liquidacao(entrada, d, lev) == pytest.approx(esperado)


def test_liquidacao_do_long_fica_abaixo_e_a_do_short_acima(banco):
    assert simulador._preco_liquidacao(100.0, 1, 5) < 100.0 < simulador._preco_liquidacao(100.0, -1, 5)


def test_alavancagem_zero_nao_divide_por_zero(banco):
    assert simulador._preco_liquidacao(100.0, 1, 0) == 0.0


def test_a_distancia_ate_a_liquidacao_e_o_buffer_dividido_pela_alavancagem(banco):
    """Amarra o preco de liquidacao a constante que o documenta. Se alguem mudar
    `LIQ_BUFFER` sem querer, isto acusa em vez de deixar passar."""
    for lev in (2, 5, 10, 25, 50):
        liq = simulador._preco_liquidacao(100.0, 1, lev)
        assert (100.0 - liq) / 100.0 == pytest.approx(simulador.LIQ_BUFFER / lev)


# ------------------------------------------------- as duas funcoes juntas: coerencia

@pytest.mark.parametrize("lev", [2, 5, 10, 20, 50])
def test_fechar_no_preco_de_liquidacao_perde_o_buffer_mais_a_taxa(banco, lev):
    """A coerencia que o [P2-18] existe para nao quebrar: liquidar em `_preco_liquidacao`
    tem de custar ~LIQ_BUFFER da margem, e nao a margem inteira nem metade dela. O bruto e
    `valor x lev x (LIQ_BUFFER/lev)` = `valor x LIQ_BUFFER` -- independe da alavancagem, e
    so a taxa cresce com ela."""
    liq = simulador._preco_liquidacao(100.0, 1, lev)
    pnl, taxa, _ = simulador._pnl(pos(lev=lev), liq)
    assert pnl == pytest.approx(-(simulador.LIQ_BUFFER * 100.0) - taxa)


def test_alavancagem_extrema_liquida_exatamente_na_margem(banco):
    """A 100x a taxa sozinha come os 10% que sobravam do buffer: a perda encosta no cap.
    Documenta o ponto em que "liquidacao" e "perda total" passam a ser a mesma coisa."""
    liq = simulador._preco_liquidacao(100.0, 1, 100)
    pnl, _, _ = simulador._pnl(pos(lev=100), liq)
    assert pnl == pytest.approx(-100.0)


def test_fechar_grava_o_retorno_alavancado_e_o_risco_inicial(banco, sem_rede):
    """Fim a fim, sem rede: o que `_pnl` calcula tem de chegar na tabela `trades` com o
    mesmo valor, e o `ret_pct` gravado e o retorno sobre a MARGEM (move x lev), nao o
    movimento do ativo -- e a coluna que o M4 vai ler."""
    pid = semear_posicao(entrada=100.0, valor_reais=100.0, alavancagem=10, stop=98.0)
    pnl = simulador.fechar(pid, "teste", 101.0)
    assert pnl == pytest.approx(9.0)
    t = db.listar("trades", 1)[0]
    assert t["pnl_reais"] == pytest.approx(9.0)
    assert t["ret_pct"] == pytest.approx(10.0)          # 1% do ativo x 10x
    assert t["taxa"] == pytest.approx(1.0)
    assert t["risco_inicial"] == pytest.approx(20.0)    # 2% de distancia x 10x x R$100
    assert db.get_banca()["atual"] == pytest.approx(1009.0)


def test_fechar_duas_vezes_nao_duplica_o_trade(banco, sem_rede):
    """`rowcount != 1` no UPDATE: a segunda chamada devolve None e nao mexe na banca."""
    pid = semear_posicao(entrada=100.0, valor_reais=100.0, alavancagem=10)
    assert simulador.fechar(pid, "teste", 101.0) == pytest.approx(9.0)
    assert simulador.fechar(pid, "teste", 101.0) is None
    assert len(db.listar("trades", 10)) == 1
