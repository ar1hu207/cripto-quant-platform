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


def test_o_piso_nao_levanta_o_trade_pequeno_demais_ele_pula(banco):
    """Risco minusculo pediria centavos; a Binance nao aceita e o trade nao mede nada.

    [P2-8] Ate 2026-08-23 a resposta era INFLAR ate R$10 -- que e furar o `risco_por_trade`.
    Agora a resposta e 0 (pular o sinal): risco pedido abaixo do piso da corretora significa
    MENOS trade, nunca mais risco."""
    assert autotrader._tamanho(1000.0, 0.0001, 10, 100.0, 98.0, 0.25) == 0.0


def test_banca_morta_nao_opera(banco):
    assert autotrader._tamanho(0.0, 0.03, 10, 100.0, 98.0, 0.25) == 0.0
    assert autotrader._tamanho(-50.0, 0.03, 10, 100.0, 98.0, 0.25) == 0.0


def test_quando_o_cap_nao_alcanca_o_piso_a_resposta_e_pular(banco):
    """O caso que o docstring chama de "nunca infla pro piso furando o cap": banca de R$30
    com cap de 25% da R$7,50, e o piso e R$10. Devolver 10 seria abrir um trade de 33% da
    banca -- o cap existe justamente contra isso. Devolver 0 e pular o sinal."""
    assert autotrader._tamanho(30.0, 0.03, 10, 100.0, 98.0, 0.25) == 0.0


def test_no_limite_o_cap_igual_ao_piso_ainda_opera(banco):
    """Banca R$40, cap 25% = R$10 = piso exato. `cap < min_valor` e estrito, entao passa --
    desde que o RISCO pedido tambem alcance o piso: 5% de R$40 = R$2, que com stop de 2% a
    10x pede exatamente R$10 de margem.

    [P2-8] mudou a segunda linha. Com 3% o valor pedido e R$6, e R$6 nao vira R$10: a mesma
    banca de R$40 que operava agora pula. As duas guardas sao diferentes e ambas necessarias
    -- `cap < min_valor` protege o CAP (banca <R$40), o filtro do piso protege o RISCO."""
    assert autotrader._tamanho(40.0, 0.05, 10, 100.0, 98.0, 0.25) == pytest.approx(10.0)
    assert autotrader._tamanho(40.0, 0.03, 10, 100.0, 98.0, 0.25) == 0.0


# ---------------------------------------------------------------- [P2-8] o piso como filtro

def test_p2_8_banca_pequena_com_liquidacao_antes_do_stop_pula_o_sinal(banco):
    """O caso literal do card: banca R$100, `risco_por_trade` 3% = R$3 pretendidos. Stop a
    10% com 10x poe a liquidacao antes do stop (`denom=1`), entao o sizing por risco pede
    exatamente os R$3 -- e o piso os transformava em R$10, ou 10% da banca, 3,3x o
    configurado, sem log nem aviso.

    A guarda que ja existia nao pegava este caso, e o assert do meio e o que prova isso:
    o cap de 25% da R$25, que e MAIOR que o piso, entao `cap < min_valor` e falso."""
    assert 100.0 * 0.25 > 10.0                                          # a guarda antiga nao dispara
    assert autotrader._tamanho(100.0, 0.03, 10, 100.0, 90.0, 0.25) == 0.0
    assert autotrader._tamanho(100.0, 0.03, 10, 100.0, 90.0, 0.25, min_valor=1.0) == pytest.approx(3.0)


@pytest.mark.parametrize("lev,stop,esperado", [
    (2, 99.9, 250.0), (2, 99.0, 250.0), (2, 98.0, 250.0), (2, 97.0, 250.0), (2, 95.0, 250.0), (2, 90.0, 150.0),
    (3, 99.9, 250.0), (3, 99.0, 250.0), (3, 98.0, 250.0), (3, 97.0, 250.0), (3, 95.0, 200.0), (3, 90.0, 100.0),
    (5, 99.9, 250.0), (5, 99.0, 250.0), (5, 98.0, 250.0), (5, 97.0, 200.0), (5, 95.0, 120.0), (5, 90.0, 60.0),
    (10, 99.9, 250.0), (10, 99.0, 250.0), (10, 98.0, 150.0), (10, 97.0, 100.0), (10, 95.0, 60.0), (10, 90.0, 30.0),
    (20, 99.9, 250.0), (20, 99.0, 150.0), (20, 98.0, 75.0), (20, 97.0, 50.0), (20, 95.0, 30.0), (20, 90.0, 30.0),
    (50, 99.9, 250.0), (50, 99.0, 60.0), (50, 98.0, 30.0), (50, 97.0, 30.0), (50, 95.0, 30.0), (50, 90.0, 30.0),
])
def test_p2_8_a_banca_padrao_de_mil_a_3pct_nao_muda_em_nenhum_ponto(lev, stop, esperado):
    """Item 2 do aceite, e a parte que segura a mao: a correcao so pode agir na faixa onde o
    piso vencia o risco. Estes 36 valores foram MEDIDOS rodando a versao anterior de
    `_tamanho` sobre a grade, e sao literais aqui de proposito -- se o diff mudar o caso
    comum (banca R$1.000, `risco_por_trade` 3%, que e o que esta vivo), isto acusa.

    Na banca de R$1.000 o piso so vencia com `risco_por_trade` <= 0,5%; a 3% ele nunca
    vence, e por isso a grade inteira e imune."""
    assert autotrader._tamanho(1000.0, 0.03, lev, 100.0, stop, 0.25) == pytest.approx(esperado)


@pytest.mark.parametrize("banca", [40.0, 60.0, 100.0, 150.0, 250.0, 330.0, 1000.0])
@pytest.mark.parametrize("risco_frac", [0.005, 0.01, 0.03, 0.05])
@pytest.mark.parametrize("lev,stop", [(2, 90.0), (5, 97.0), (10, 98.0), (20, 95.0), (50, 99.0)])
def test_p2_8_o_risco_ate_o_stop_nunca_passa_do_configurado(banca, risco_frac, lev, stop):
    """Item 3 do aceite, escrito como invariante e nao como caso: `valor x min(lev x sd, 1)`
    e a perda-ate-o-stop (a mesma conta do `simulador._risco_posicao`), e ela nunca pode
    passar de `banca x risco_por_trade`. A tolerancia de 1 centavo e o `round(valor, 2)`.

    A faixa de banca cobre exatamente onde o card diz que o buraco estava (~R$40-330)."""
    valor = autotrader._tamanho(banca, risco_frac, lev, 100.0, stop, 0.25)
    if valor == 0.0:
        return                                                          # sinal pulado: sem risco
    perda_no_stop = valor * min(lev * (100.0 - stop) / 100.0, 1.0)
    assert perda_no_stop <= banca * risco_frac + 0.01


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
