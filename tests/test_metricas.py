# -*- coding: utf-8 -*-
"""Item 6 do [P2-6]: `db.metricas()` -- as divisoes por zero com lista vazia de trades.

`metricas()` alimenta o painel e, no M4, a leitura da regua. Ela divide por `len(trades)`,
por `soma_p`, por `std`, por `maxdd` e por `peak`; qualquer um desses e zero num banco novo,
num banco so com vencedores, ou num banco com um trade so. O modo de falha nao e numero
errado -- e `/estado` inteiro caindo em ZeroDivisionError.
"""
import pytest

import db
from conftest import semear_equity


def trade(pnl, taxa=1.0, conviccao=70, fechado_em="2026-08-22 10:00:00", risco_inicial=None):
    with db.conectar() as c:
        c.execute("INSERT INTO trades(ativo,direcao,pnl_reais,taxa,conviccao,fechado_em,"
                  "risco_inicial) VALUES('BTC/USDT','LONG',?,?,?,?,?)",
                  (pnl, taxa, conviccao, fechado_em, risco_inicial))


def test_banco_novo_devolve_a_base_sem_dividir_por_zero(banco):
    m = db.metricas()
    assert m["n_trades"] == 0
    assert m["win_rate"] == 0 and m["profit_factor"] == 0 and m["sharpe"] == 0
    assert m["por_conviccao"] == []
    assert all(isinstance(v, (int, float, list)) for v in m.values())


def test_um_trade_so_nao_estoura_no_desvio_padrao(banco):
    """`std == 0` com uma amostra so: `sqn` e `sortino` viram 0 em vez de excecao."""
    trade(10.0)
    m = db.metricas()
    assert m["n_trades"] == 1 and m["win_rate"] == 100.0
    assert m["sqn"] == 0 and m["sortino"] == 0


def test_so_vencedores_nao_divide_por_soma_de_perdas_zero(banco):
    """`soma_p == 0`: o profit factor seria infinito. O codigo devolve 999, que e o
    'infinito' declarado do painel -- e `perda_media` fica 0 por nao haver perdedor."""
    trade(10.0)
    trade(5.0)
    m = db.metricas()
    assert m["profit_factor"] == 999
    assert m["perda_media"] == 0
    assert m["ganho_medio"] == pytest.approx(7.5)


def test_so_perdedores_nao_divide_por_zero_no_ganho_medio(banco):
    trade(-10.0)
    trade(-5.0)
    m = db.metricas()
    assert m["win_rate"] == 0.0
    assert m["ganho_medio"] == 0
    assert m["perda_media"] == pytest.approx(-7.5)
    assert m["profit_factor"] == pytest.approx(0.0)


def test_trade_zerado_conta_como_perda(banco):
    """`(pnl or 0) > 0` para vencedor: zero cai no outro lado. Nao e detalhe -- e o que
    impede um empate de inflar o win rate."""
    trade(0.0)
    m = db.metricas()
    assert m["win_rate"] == 0.0 and m["n_trades"] == 1


# [P2-36] Este teste nasceu `xfail(strict=True)` no [P2-6] -- achado registrado por quem nao
# podia consertar `db.py` (fora do territorio T-TESTE). O [P2-36] consertou, o xfail virou
# XPASS e QUEBROU a suite, que era exatamente o combinado (CLAUDE.md secao 6): o registro nao
# dependia de ninguem lembrar. Promovido a teste normal aqui.
#
# A ASSERCAO MUDOU, e a mudanca e a entrega do card. O xfail original pedia
# `win_rate == 50.0`, ou seja, o NULL contado como ZERO (cairia em `perdas`). O [P2-36]
# decidiu o contrario -- NULL e medicao AUSENTE, sai das razoes e e publicado em `n_sem_pnl`
# -- porque zero falso achata desvio padrao e expectancia sempre para o lado bonito. O card
# deixava a decisao em aberto de proposito ("trade ignorado na conta, OU contado como zero.
# Nao e a mesma coisa"); o que o autor do xfail fixou foi o defeito (o TypeError), e e o
# defeito que as duas versoes do teste continuam provando.
def test_pnl_nulo_no_banco_nao_derruba_a_conta(banco):
    """Trade gravado por um caminho antigo, sem `pnl_reais`. O bug era `TypeError` nas somas
    da coluna crua, que derrubava `/estado` inteiro (poll de 3s do painel)."""
    trade(None)
    trade(10.0)
    m = db.metricas()                                  # antes: TypeError aqui
    assert m["n_trades"] == 2                          # a linha nao some da contagem...
    assert m["n_sem_pnl"] == 1                         # ...e a ausencia fica VISIVEL
    assert m["win_rate"] == 100.0                      # 1 win entre os 1 MEDIDOS
    assert m["pnl_total"] == pytest.approx(10.0)       # o ausente nao entra como zero
    assert m["expectancia"] == pytest.approx(10.0)     # nem dilui a media


def test_pnl_nulo_nao_e_a_mesma_coisa_que_pnl_zero(banco):
    """O par que fixa a decisao do [P2-36]: `0.0` e medicao ("empatou", conta como perda,
    `test_trade_zerado_conta_como_perda`); `None` e ausencia de medicao. Com os dois no mesmo
    banco os numeros tem de discordar -- se um dia voltarem a coincidir, o `or 0` voltou."""
    trade(0.0)
    trade(None)
    m = db.metricas()
    assert m["n_trades"] == 2 and m["n_sem_pnl"] == 1
    assert m["win_rate"] == 0.0                        # o 0.0 e o unico medido, e e perda
    assert m["perda_media"] == 0                       # -0.0/1 -- perda medida de zero
    assert m["pnl_total"] == pytest.approx(0.0)


def test_banco_so_de_pnl_ausente_nao_divide_por_zero(banco):
    """Caso degenerado do [P2-36]: `medidos` vazio com `trades` cheio. Sem o desvio a media
    dividiria por `len(medidos)` == 0 -- trocar um TypeError por um ZeroDivisionError seria
    o mesmo `/estado` caido com outro nome."""
    trade(None)
    trade(None)
    m = db.metricas()
    assert m["n_trades"] == 2 and m["n_sem_pnl"] == 2
    assert m["win_rate"] == 0 and m["profit_factor"] == 0 and m["sqn"] == 0
    assert m["por_conviccao"] == []


def test_pnl_ausente_sai_tambem_do_por_conviccao_e_dos_r_multiplos(banco):
    """As somas que o card do [P2-36] nomeia nao sao so as duas de cima: a de `por_conviccao`
    e a dos R-multiplos leem a mesma coluna. Um NULL em qualquer uma derrubava a rota."""
    trade(None, conviccao=85, risco_inicial=5.0)
    trade(10.0, conviccao=85, risco_inicial=5.0)
    m = db.metricas()
    faixas = {g["faixa"]: g for g in m["por_conviccao"]}
    assert faixas["80-100"]["n"] == 1                  # so o medido entra na faixa
    assert faixas["80-100"]["win_rate"] == 100.0
    assert faixas["80-100"]["pnl"] == pytest.approx(10.0)
    assert m["expectancia_r"] == pytest.approx(2.0)    # 10/5, e nao a media com um 0 falso


def test_win_rate_e_profit_factor_com_os_dois_lados(banco):
    trade(10.0)
    trade(-5.0)
    m = db.metricas()
    assert m["win_rate"] == 50.0
    assert m["pnl_total"] == pytest.approx(5.0)
    assert m["profit_factor"] == pytest.approx(2.0)
    assert m["taxa_total"] == pytest.approx(2.0)


def test_sem_risco_inicial_os_r_multiplos_ficam_zerados_e_nao_estouram(banco):
    """`rmults` fica vazio quando nenhum trade tem `risco_inicial` -- historico anterior ao
    [P2-11]. Dividir por `len(rmults)` ali seria divisao por zero."""
    trade(10.0)
    m = db.metricas()
    assert m["expectancia_r"] == 0 and m["sqn_r"] == 0


def test_um_unico_r_multiplo_nao_divide_pelo_desvio_zero(banco):
    trade(10.0, risco_inicial=5.0)
    m = db.metricas()
    assert m["expectancia_r"] == pytest.approx(2.0)
    assert m["sqn_r"] == 0                     # `sr == 0` com uma amostra


def test_por_conviccao_ignora_faixa_vazia(banco):
    trade(10.0, conviccao=85)
    trade(-5.0, conviccao=85)
    trade(3.0, conviccao=50)
    faixas = {g["faixa"]: g for g in db.metricas()["por_conviccao"]}
    assert set(faixas) == {"80-100", "40-60"}
    assert faixas["80-100"]["n"] == 2 and faixas["80-100"]["win_rate"] == 50.0


def test_curva_de_equity_com_um_ponto_so_nao_estoura(banco):
    """`eq[0]` como pico inicial e `if pk else 0` na divisao: um snapshot so, ou um zerado,
    tem de sair com drawdown 0."""
    trade(10.0)
    semear_equity("2026-08-22 00:00:05", 1000.0)
    assert db.metricas()["max_dd_mtm_pct"] == 0


def test_equity_zerado_nao_divide_por_zero(banco):
    trade(-10.0)
    semear_equity("2026-08-22 00:00:05", 0.0)
    semear_equity("2026-08-22 00:00:20", 0.0)
    assert db.metricas()["max_dd_mtm_pct"] == 0


def test_drawdown_mark_to_market_mede_o_pico_ate_o_vale(banco):
    trade(-10.0)
    for ts, v in [("2026-08-22 00:00:05", 1000.0), ("2026-08-22 00:00:20", 1200.0),
                  ("2026-08-22 00:00:35", 900.0)]:
        semear_equity(ts, v)
    assert db.metricas()["max_dd_mtm_pct"] == pytest.approx(25.0)     # 1200 -> 900


def test_sharpe_exige_tres_dias_e_ate_la_fica_zero(banco):
    """`len(eq_diario) >= 3`: com dois dias a divisao pelo desvio de UM retorno seria 0/0."""
    trade(10.0)
    semear_equity("2026-08-21 23:59:00", 1000.0)
    semear_equity("2026-08-22 23:59:00", 1010.0)
    assert db.metricas()["sharpe"] == 0
