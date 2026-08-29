# -*- coding: utf-8 -*-
"""Item 4 do [P2-6]: `autotrader._tamanho()` e `autotrader._alavancagem()`.

Sao as duas funcoes que decidem QUANTO o bot arrisca sem ninguem olhando. Nenhuma delas
toca banco nem rede -- recebem numeros e devolvem numeros -- entao aqui nao ha fixture de
banco: se algum dia uma delas passar a precisar de uma, este arquivo quebra, e isso e
informacao.

Tambem e a casa das provas do [P2-8] (o piso vira filtro) e da metade do [P1-11] que mora
em `autotrader.py` (o cap geometrico da alavancagem) -- os dois mexem nestas mesmas duas
funcoes, que e a razao de estarem no mesmo territorio.
"""
import pytest

import autotrader
import simulador


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


# ================================================================ [P1-11] cap geometrico


@pytest.fixture
def caps_zerados():
    """`autotrader.CAPS_GEOMETRIA` e estado de MODULO (vive o processo inteiro, porque quem o
    le e o `/status`, fora do ciclo do auto-trader). Teste que conta precisa zera-lo antes e
    devolve-lo depois, senao a ordem dos testes passa a decidir o resultado."""
    antes = dict(autotrader.CAPS_GEOMETRIA)
    autotrader.CAPS_GEOMETRIA.update({"total": 0, "ultimo": None})
    yield autotrader.CAPS_GEOMETRIA
    autotrader.CAPS_GEOMETRIA.clear()
    autotrader.CAPS_GEOMETRIA.update(antes)


def test_p1_11_o_criterio_de_aceite_stop_de_5pct_com_conviccao_pedindo_20x():
    """Item 1 do aceite, literal: `stop_dist=5%` e conviccao 100 (que pede o teto de 20x)
    -> lev efetiva <= 14, que e `0,8 x 0,9 / 0,05` = 14,4 truncado."""
    assert autotrader._alavancagem(CFG, 100, 0.05) <= 14
    assert autotrader._alavancagem(CFG, 100, 0.05) == pytest.approx(14.0)
    assert autotrader._alavancagem(CFG, 100) == 20.0        # sem geometria, o teto de sempre


@pytest.mark.parametrize("ativo,stop_dist", [
    ("BTC 15m p50", 0.0074), ("BTC 15m p95", 0.0164),       # a tabela do card, medida em barras
    ("SOL 1h p50", 0.0265), ("SOL 1h p95", 0.0473),
    ("DOGE 1h p50", 0.0279), ("DOGE 1h p95", 0.0483),
    ("AVAX 1h p50", 0.0290), ("AVAX 1h p95", 0.0456),
    ("SUI 1h p50", 0.0359), ("SUI 1h p95", 0.0586),
    ("NEAR 1h p50", 0.0373), ("NEAR 1h p95", 0.0919),
    ("INJ 1h p50", 0.0367), ("INJ 1h p95", 0.0950),
])
@pytest.mark.parametrize("direcao", [1, -1])
def test_p1_11_a_liquidacao_fica_sempre_atras_do_stop(ativo, stop_dist, direcao):
    """Item 2 do aceite ("nenhum trade novo com a liquidacao mais perto que o stop"), escrito
    como invariante sobre a tabela de stops MEDIDOS do card -- os mesmos ativos e percentis
    que produziam 37,2% de trades binarios no INJ 1h a 20x.

    A prova chama o `simulador._preco_liquidacao` de verdade em vez de repetir a formula: se
    o modelo de liquidacao mudar, isto acusa em vez de concordar com uma copia velha. Roda
    nos dois sentidos porque a liquidacao e simetrica e o bot opera LONG e SHORT."""
    lev = autotrader._alavancagem(CFG, 100, stop_dist, ativo)
    entrada = 100.0
    stop = entrada * (1 - direcao * stop_dist)
    liq = simulador._preco_liquidacao(entrada, direcao, lev)
    dist_stop, dist_liq = abs(entrada - stop), abs(entrada - liq)
    assert dist_liq > dist_stop                              # o stop volta a ser alcancavel
    assert dist_liq / dist_stop >= 1.249                     # com a folga de >=25% do FOLGA_LIQ


def test_p1_11_a_conviccao_alta_deixa_de_ser_o_caso_mais_perigoso():
    """A perversao que o card aponta: conviccao MAIOR -> lev maior -> MAIS provavel o trade
    ser binario, o inverso do desenho ("mais confianca, execucao melhor"). Com o stop do INJ
    1h no p95 (9,5%), o teto passa a ser GEOMETRICO: da conviccao 80 para cima a lev para de
    subir, e nenhum ponto da faixa produz trade binario.

    Nas conviccoes baixas a lev continua vindo da escala (2x, 6x) -- e correto: la ela ja
    esta abaixo do limite geometrico, e o cap nao tem nada a apertar."""
    stop_dist = 0.095
    levs = [autotrader._alavancagem(CFG, conv, stop_dist) for conv in range(60, 101)]
    assert max(levs) == 7.0                                  # 0,8 x 0,9 / 0,095 = 7,57 -> 7
    assert all(lev * stop_dist < 1.0 for lev in levs)        # nenhuma conviccao vira binario
    assert {autotrader._alavancagem(CFG, c, stop_dist) for c in (80, 90, 100)} == {7.0}


@pytest.mark.parametrize("stop_dist,esperado", [
    (0.0072, 20.0),      # 0,72/0,0072 = 100x: o teto de conviccao e que vence
    (0.036, 20.0),       # 0,72/0,036 = 20,0 exato -> empate NAO capa (a comparacao e >=)
    (0.037, 19.0),       # 19,45 -> 19: trunca pra baixo, nunca arredonda pra cima
    (0.05, 14.0),        # 14,4 -> 14
    (0.10, 7.0),         # 7,2 -> 7
    (0.20, 3.0),         # 3,6 -> 3
    (0.40, 1.0),         # 1,8 -> 1: desce ABAIXO de lev_min de proposito
    (0.90, 1.0),         # 0,8 -> piso absoluto de 1x
])
def test_p1_11_o_cap_trunca_para_baixo_e_tem_piso_de_1x(stop_dist, esperado):
    """Arredondar (14,6 -> 15) devolveria a liquidacao para DENTRO do stop e desfaria o cap no
    proprio ato de aplica-lo; por isso e truncamento. E o piso e 1x, nao `lev_min`: `lev_min`
    e o inicio da escala de conviccao e nunca foi promessa de risco -- respeita-lo aqui seria
    manter o trade binario para nao contrariar um parametro de UI."""
    assert autotrader._alavancagem(CFG, 100, stop_dist) == pytest.approx(esperado)


def test_p1_11_o_cap_tambem_vale_no_modo_fixo():
    """A geometria e fisica: `alavancagem_padrao=10` com stop de 9,5% e tao degenerado quanto
    20x por conviccao. Capar so o modo 'conviccao' deixaria o buraco aberto para quem virasse
    a chave para 'fixo' -- que e config de UI, nao um regime de risco diferente."""
    cfg = dict(CFG, auto_lev_modo="fixo", alavancagem_padrao="10")
    assert autotrader._alavancagem(cfg, 95) == 10.0                  # sem stop: nada muda
    assert autotrader._alavancagem(cfg, 95, 0.095) == 7.0            # com stop: capa igual


def test_p1_11_sem_geometria_medivel_nada_muda():
    """Sinal sem stop, stop na entrada, entrada degenerada: nao ha o que medir, e derivar um
    cap de `stop_dist=0` seria divisao por zero disfarcada de guarda."""
    for stop_dist in (None, 0, 0.0, -0.01):
        assert autotrader._alavancagem(CFG, 100, stop_dist) == 20.0


def test_p1_11_o_cap_conta_e_loga_quando_age(caps_zerados, monkeypatch):
    """Item 3 do aceite, a metade que mora aqui: o log no formato do card, e a contagem
    ACESSIVEL de fora do modulo. Quem a expoe no `/status` e o `api.py` (T-DECLARACAO,
    onda 2 do M4), que le exatamente este `autotrader.CAPS_GEOMETRIA`."""
    linhas = []
    monkeypatch.setattr(autotrader, "log", lambda msg, nivel="info": linhas.append(msg))

    assert autotrader._alavancagem(CFG, 100, 0.05, "INJ/USDT") == 14.0
    assert linhas == ["lev capada 20.0->14.0 por geometria stop/liq INJ/USDT"]
    assert caps_zerados["total"] == 1
    assert caps_zerados["ultimo"]["ativo"] == "INJ/USDT"
    assert caps_zerados["ultimo"]["lev_conviccao"] == 20.0
    assert caps_zerados["ultimo"]["lev_efetiva"] == 14.0
    assert caps_zerados["ultimo"]["stop_dist"] == pytest.approx(0.05)


def test_p1_11_o_cap_fica_calado_quando_nao_age(caps_zerados, monkeypatch):
    """Contador que soma quando o cap nao apertou nada vira ruido no `/status`, e log por
    candidato numa varredura de 24 ativos vira arquivo de 10 MB. So conta quando muda a lev."""
    linhas = []
    monkeypatch.setattr(autotrader, "log", lambda msg, nivel="info": linhas.append(msg))

    assert autotrader._alavancagem(CFG, 100, 0.0074, "BTC/USDT") == 20.0
    assert autotrader._alavancagem(CFG, 60, 0.10, "BTC/USDT") == 2.0     # 7,2 > 2: nao aperta
    assert linhas == []
    assert caps_zerados["total"] == 0
    assert caps_zerados["ultimo"] is None


def test_p1_11_o_cap_desarma_o_trade_binario_no_sizing():
    """O fecho do raciocinio do card. Antes, INJ 1h no p95 (stop 9,5%) a 20x dava
    `denom = min(20 x 0,095, 1) = 1`: o sizing JA assumia perda = margem inteira, e por isso o
    orcamento de risco nao estourava enquanto o desenho do trade virava ficcao -- e a razao de
    ninguem ter percebido. Com o cap a 7x, `denom = 0,665 < 1`: o stop volta a decidir a perda."""
    stop_dist = 0.095
    assert min(20.0 * stop_dist, 1.0) == 1.0                         # binario: perda = margem

    lev = autotrader._alavancagem(CFG, 100, stop_dist)
    assert min(lev * stop_dist, 1.0) < 1.0
    valor = autotrader._tamanho(1000.0, 0.03, lev, 100.0, 100.0 * (1 - stop_dist), 0.25)
    assert valor * lev * stop_dist == pytest.approx(30.0, abs=0.01)  # R$30 no stop (1 centavo
                                                                     # de folga: o round do valor)


@pytest.mark.parametrize("entrada,stop,esperado", [
    (100.0, 95.0, 0.05),
    (100.0, 105.0, 0.05),        # short: a distancia e absoluta
    (100.0, 100.0, 0.0),         # stop na entrada
    (100.0, None, 0.0),
    (100.0, 0, 0.0),
    (0, 98.0, 0.0),              # entrada degenerada: nao pode virar divisao por zero
    (None, None, 0.0),
    ("x", "y", 0.0),             # campo corrompido no sinal: 0.0, nunca excecao no meio do ciclo
])
def test_p1_11_stop_dist_e_a_unica_fonte_da_geometria(entrada, stop, esperado):
    """`_tamanho` e `_alavancagem` leem daqui, e nao cada uma da sua conta: com duas contas a
    garantia "liquidacao atras do stop" valeria com um numero e a margem seria dimensionada
    com outro. Os casos degenerados devolvem 0.0 -- ausencia de geometria, nao erro."""
    assert autotrader._stop_dist(entrada, stop) == pytest.approx(esperado)


# ============================================================ [N-10] a escala DORME, nao morre
#
# O [Q-13] mediu a premissa da escala de conviccao em 2.945 sinais de tendencia com desfecho
# marcado, e ela nao se sustenta: os sinais que bateram no STOP tinham conviccao MEDIA MAIOR
# (67,10) que os que bateram no alvo (66,47), e o win% por faixa faz 63 -> 38 -> 45 -> 50 -> 47
# -- serrilha, nao escada. A faixa 80-90, que a escala premiava com ~12x, e a pior das cinco.
#
# O que o card desliga e o DEFAULT, nunca o mecanismo. A diferenca importa porque o `N-10b`
# vai construir um medidor que passe no teste do [Q-13] (win% monotonico por faixa, em amostra
# FORA da usada para construi-lo), e no dia em que passar a escala precisa estar inteira para
# voltar por config -- nao reimplementada de memoria por quem nunca leu este card. Os dois
# testes abaixo travam as duas metades: o default mudou, e a escala continua funcionando.

def test_n10_o_default_vivo_da_alavancagem_e_fixo(banco):
    """O default do repositorio E o que o worker carrega num banco novo -- as duas pontas, e
    nao so o dicionario: quem le `CONFIG_PADRAO` sem conferir o banco esta lendo a intencao,
    e o que decide o dinheiro e o que o `init_db` gravou."""
    import db
    assert db.CONFIG_PADRAO["auto_lev_modo"] == "fixo"
    assert db.get_config()["auto_lev_modo"] == "fixo"


def test_n10_no_default_a_conviccao_deixa_de_virar_alavancagem(banco):
    """A consequencia medivel do card, e a razao dele: a escala mapeava 60 -> `auto_lev_min` e
    99 -> `auto_lev_max`, entao 20 pontos de um score que NAO preve acerto viravam 5,5x mais
    dinheiro em risco. No default de hoje o mesmo par de sinais recebe a mesma alavancagem.

    Nao e "ficar seguro": e parar de espalhar 20x sobre sinais que a medicao nao distingue
    entre si. O risco que sai daqui e o que sobra para a oportunidade que se souber medir."""
    import db
    cfg = db.get_config()
    assert autotrader._alavancagem(cfg, 62) == autotrader._alavancagem(cfg, 99)
    assert autotrader._alavancagem(cfg, 99) == float(cfg["alavancagem_padrao"])


def test_n10_o_modo_conviccao_continua_inteiro_quando_ligado_de_proposito(banco):
    """A metade que costuma sumir: ninguem prova que o codigo desligado ainda funciona, e um
    ano depois ele nao funciona mais. Com `auto_lev_modo=conviccao` gravado na config VIVA (e
    nao num dict de teste), a escala tem de entregar piso, teto e a rampa entre eles.

    Se este teste quebrar, o mecanismo morreu -- e ai o `N-10b` nao tem para onde voltar."""
    import db
    db.set_config("auto_lev_modo", "conviccao")
    cfg = db.get_config()
    assert autotrader._alavancagem(cfg, 60) == 2.0                   # piso = auto_lev_min
    assert autotrader._alavancagem(cfg, 100) == 20.0                 # teto = auto_lev_max
    assert autotrader._alavancagem(cfg, 80) == 11.0                  # rampa: 2 + 0,5x(20-2)
    assert autotrader._alavancagem(cfg, 100, 0.095) == 7.0           # e o cap [P1-11] por cima


def test_n10_o_perfil_experimento_nao_declara_o_modo_e_isso_esta_registrado(banco):
    """⚠️ O que este card NAO conseguiu entregar, travado com um teste em vez de uma nota.

    O plano manda `auto_lev_modo` nascer "fixo" no `CONFIG_PADRAO` **e no perfil
    `experimento`**. A primeira metade esta feita; a segunda esbarra em
    `tests/test_config.py::test_todo_parametro_de_perfil_tem_racional_escrito`, que exige que
    TODA chave do perfil tenha verbete em `api.CONFIG_RACIONAL` -- e `api.py` nao e territorio
    do T-RISCO. Acrescentar a chave aqui deixaria a suite vermelha num territorio `toca-risco`,
    que e o pior lugar possivel para entregar teste quebrado.

    Enquanto isso, `perfil_ativo()` NAO enxerga o modo: um sistema com `auto_lev_modo=conviccao`
    vivo continua sendo rotulado 'experimento'. E a mesma classe de mentira de rotulo que o
    [Q-3] documentou, e por isso fica medida aqui em vez de anotada num relatorio que ninguem
    reabre. Quando o verbete entrar no `api.py`, este teste quebra -- e e o gatilho para
    promover a chave ao perfil."""
    import db
    assert "auto_lev_modo" not in db.PERFIS_RISCO["experimento"]
    db.set_config("auto_lev_modo", "conviccao")
    assert db.perfil_ativo() == "experimento"     # o rotulo nao acusa: e o buraco, medido
