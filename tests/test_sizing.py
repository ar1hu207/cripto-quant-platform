# -*- coding: utf-8 -*-
"""Item 4 do [P2-6]: `autotrader._tamanho()` e `autotrader._alavancagem()`.

Sao as duas funcoes que decidem QUANTO o bot arrisca sem ninguem olhando. Nenhuma delas
toca banco nem rede -- recebem numeros e devolvem numeros -- entao aqui nao ha fixture de
banco: se algum dia uma delas passar a precisar de uma, este arquivo quebra, e isso e
informacao.
"""
import pytest

import autotrader


CFG = {"auto_lev_modo": "conviccao", "auto_lev_min": "2", "auto_lev_max": "20",
       "auto_conviccao_min": "60", "alavancagem_padrao": "10"}


# ================================================================ _tamanho

def test_o_tamanho_faz_a_perda_ate_o_stop_bater_o_risco_pedido(banco):
    """A promessa da funcao: `valor` tal que perder no stop custe `banca x risco_frac`.
    Banca R$1.000, 3% de risco = R$30. Stop a 2% com 10x => a posicao perde 20% da margem,
    entao a margem tem de ser R$150."""
    valor = autotrader._tamanho(1000.0, 0.03, 10, 100.0, 98.0, 0.25)
    assert valor == pytest.approx(150.0)
    assert valor * 10 * 0.02 == pytest.approx(30.0)     # a conta de volta: R$30 no stop


@pytest.mark.parametrize("lev,stop,max_frac,esperado", [
    (10, 98.0, 0.25, 150.0),     # 2% x 10x = 20% da margem
    (5, 98.0, 0.50, 300.0),      # metade da alavancagem, o dobro da margem para o mesmo R$30
    (10, 99.0, 0.50, 300.0),     # stop na metade da distancia, o dobro da margem
    (2, 90.0, 0.25, 150.0),      # 10% x 2x = 20% da margem: mesma margem do primeiro caso
])
def test_o_tamanho_compensa_alavancagem_e_distancia_do_stop(lev, stop, max_frac, esperado):
    """O cap sobe nos casos do meio de proposito: sem isso eles baterem no teto de 25% e o
    teste mediria o cap, nao a compensacao (foi o que aconteceu na primeira escrita)."""
    valor = autotrader._tamanho(1000.0, 0.03, lev, 100.0, stop, max_frac)
    assert valor == pytest.approx(esperado)
    assert valor * lev * (abs(100.0 - stop) / 100.0) == pytest.approx(30.0)


def test_o_cap_por_trade_vence_o_sizing_por_risco(banco):
    """Stop colado (0,1%) pediria R$3.000 de margem para arriscar R$30. O cap de 25% da
    banca e o que impede o sizing por risco de virar alavancagem disfarcada."""
    assert autotrader._tamanho(1000.0, 0.03, 10, 100.0, 99.9, 0.25) == pytest.approx(250.0)


def test_o_piso_levanta_o_trade_pequeno_demais(banco):
    """Risco minusculo pediria centavos; a Binance nao aceita e o trade nao mede nada."""
    assert autotrader._tamanho(1000.0, 0.0001, 10, 100.0, 98.0, 0.25) == pytest.approx(10.0)


def test_banca_morta_nao_opera(banco):
    assert autotrader._tamanho(0.0, 0.03, 10, 100.0, 98.0, 0.25) == 0.0
    assert autotrader._tamanho(-50.0, 0.03, 10, 100.0, 98.0, 0.25) == 0.0


def test_quando_o_cap_nao_alcanca_o_piso_a_resposta_e_pular(banco):
    """O caso que o docstring chama de "nunca infla pro piso furando o cap": banca de R$30
    com cap de 25% da R$7,50, e o piso e R$10. Devolver 10 seria abrir um trade de 33% da
    banca -- o cap existe justamente contra isso. Devolver 0 e pular o sinal."""
    assert autotrader._tamanho(30.0, 0.03, 10, 100.0, 98.0, 0.25) == 0.0


def test_no_limite_o_cap_igual_ao_piso_ainda_opera(banco):
    """Banca R$40, cap 25% = R$10 = piso exato. `cap < min_valor` e estrito, entao passa."""
    assert autotrader._tamanho(40.0, 0.03, 10, 100.0, 98.0, 0.25) == pytest.approx(10.0)


def test_liquidacao_antes_do_stop_faz_o_risco_ser_a_margem_inteira(banco):
    """`denom = min(lev * sd, 1.0)`. Com 50x e stop a 5%, o stop esta atras da liquidacao:
    a perda real e a margem toda, entao a margem tem de ser o proprio risco pedido (R$30) --
    e nao R$12, que e o que sairia sem o `min`."""
    assert autotrader._tamanho(1000.0, 0.03, 50, 100.0, 95.0, 0.25) == pytest.approx(30.0)


@pytest.mark.parametrize("entrada,stop", [
    (100.0, 100.0),      # stop na entrada: sem distancia
    (100.0, None),       # sinal sem stop
    (100.0, 0),
    (0, 98.0),           # entrada degenerada: nao pode virar divisao por zero
    (None, None),
])
def test_sem_distancia_ate_o_stop_o_risco_e_a_margem(entrada, stop):
    assert autotrader._tamanho(1000.0, 0.03, 10, entrada, stop, 0.25) == pytest.approx(30.0)


def test_o_valor_sai_arredondado_em_centavos(banco):
    valor = autotrader._tamanho(1000.0, 0.03, 3, 100.0, 97.3, 0.9)
    assert valor == round(valor, 2)


# ================================================================ _alavancagem

def test_modo_fixo_ignora_a_conviccao(banco):
    cfg = dict(CFG, auto_lev_modo="fixo")
    assert autotrader._alavancagem(cfg, 95) == 10.0
    assert autotrader._alavancagem(cfg, 60) == 10.0


def test_modo_fixo_le_a_alavancagem_padrao(banco):
    assert autotrader._alavancagem(dict(CFG, auto_lev_modo="fixo", alavancagem_padrao="7"), 95) == 7.0


def test_na_conviccao_minima_usa_o_piso(banco):
    assert autotrader._alavancagem(CFG, 60) == 2.0


def test_na_conviccao_maxima_usa_o_teto(banco):
    assert autotrader._alavancagem(CFG, 100) == 20.0


def test_no_meio_da_faixa_escala_linearmente(banco):
    """Conviccao 80 = metade do caminho de 60 a 100 -> metade do caminho de 2x a 20x."""
    assert autotrader._alavancagem(CFG, 80) == 11.0


@pytest.mark.parametrize("conv,esperado", [
    (0, 2.0),        # abaixo do minimo: `frac` clampado em 0
    (59, 2.0),
    (150, 20.0),     # acima de 100: clampado em 1
    (None, 2.0),     # sem conviccao gravada: trata como a minima, nao como a maxima
])
def test_conviccao_fora_da_faixa_nao_estoura_os_limites(conv, esperado):
    assert autotrader._alavancagem(CFG, conv) == esperado


def test_a_alavancagem_e_sempre_inteira_e_dentro_da_faixa(banco):
    """O `round` no meio da expressao e a razao de o resultado nunca ser 6,5x -- e o
    `max/min` em volta e a razao de o arredondamento nunca empurrar para fora da faixa."""
    for conv in range(0, 121):
        lev = autotrader._alavancagem(CFG, conv)
        assert lev == int(lev)
        assert 2.0 <= lev <= 20.0


def test_a_alavancagem_nunca_cai_quando_a_conviccao_sobe(banco):
    anterior = 0.0
    for conv in range(0, 121):
        lev = autotrader._alavancagem(CFG, conv)
        assert lev >= anterior
        anterior = lev


def test_conviccao_minima_em_100_nao_divide_por_zero(banco):
    """`max(100 - conv_min, 1)`: config extrema degrada para o piso em vez de estourar."""
    assert autotrader._alavancagem(dict(CFG, auto_conviccao_min="100"), 100) == 2.0


def test_faixa_invertida_nao_devolve_alavancagem_abaixo_do_piso(banco):
    """`lev_max` menor que `lev_min` e config errada; o `max(lev_min, ...)` garante que o
    erro nao vire alavancagem 1x silenciosa no meio de um trade."""
    assert autotrader._alavancagem(dict(CFG, auto_lev_min="10", auto_lev_max="5"), 100) >= 10.0
