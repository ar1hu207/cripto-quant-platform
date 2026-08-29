# -*- coding: utf-8 -*-
"""Provas da REGUA (`pesquisa/validacao.py`) -- o [Q-1].

Por que este arquivo existe, e por que ele nao usa rede. A regua e o instrumento que decide
se existe edge; o resultado dela vira decisao de projeto. Um instrumento so vale se alguem
puder reexecutar a prova dele, e a prova de estatistica que mora em arquivo temporario e
prova que nao existe. Tudo aqui roda offline: `walk_forward` recebe um gerador injetado
(`ITEM1-VALIDACAO-RIGOROSA.md` §3.6), entao nenhuma moeda e baixada.

O que se prova aqui e o que o card [Q-1] mudou:

  * o bootstrap de BLOCO difere do iid num caso construido, e difere pelo FATOR CERTO
    (AR(1) com phi conhecido) -- e a diferenca entre testar a mecanica do bloco e testar a
    estatistica dele (`REVISAO-ITEM1.md` §E.3, item 1);
  * a guarda [F1]: bloco sobre lista de trades e ERRO, nao default;
  * o portao de MDS emite INCONCLUSIVO quando o instrumento nao tem poder [F14];
  * o `PADRAO` esta travado: nao ha argumento em `walk_forward` que mude o criterio [F3];
  * o p-valor e (1+#{>=})/(B+1), nunca zero [F5], e o Reality Check com N=1 reduz ao
    bootstrap unilateral da media (`REVISAO-ITEM1.md` §E.3, item 4);
  * a purga age nos dois sentidos, quando ha `ts_saida` para agir.

`REVISAO-ITEM1.md` §E.3 e explicita sobre o teste que NAO serve: "ruido puro -> p alto" e
smoke test, nao calibracao -- um bug que faca V* grande demais produz p~1 sempre e passa com
louvor. O que define teste calibrado e UNIFORMIDADE dos p-valores, e e isso que
`test_reality_check_calibrado` afirma.
"""
import json
import math
import os

import numpy as np
import pandas as pd
import pytest

from pesquisa import backtest_plataforma as B
from pesquisa import validacao as V

DIA = V.DIA_MS
T0 = 1_700_000_000_000 // DIA * DIA          # meia-noite de um dia qualquer, em ms


# ============================ helpers ============================
def trades_diarios(pnls, hora_ms=0, ts_saida=None):
    """Um trade por dia, comecando em T0. `ts_saida` opcional (lista de ms absolutos)."""
    fora = []
    for i, p in enumerate(pnls):
        t = {"ts": int(T0 + i * DIA + hora_ms), "pnl": float(p)}
        if ts_saida is not None:
            t["ts_saida"] = int(ts_saida[i])
        fora.append(t)
    return fora


def gerador_constante(por_cfg):
    return lambda cfg: por_cfg[cfg]


def serie_ar1(n, phi, sigma=1.0, seed=0, mu=0.0):
    """AR(1) estacionario com phi conhecido -- a autocorrelacao que o bootstrap de bloco
    tem de recuperar e o iid tem de perder."""
    rng = np.random.default_rng(seed)
    e = rng.normal(0.0, sigma, size=n)
    x = np.empty(n)
    x[0] = e[0] / math.sqrt(1 - phi ** 2)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return (x + mu).tolist()


# ============================ pnl_por_periodo / grade ============================
def test_pnl_por_periodo_soma_por_dia_e_zera_o_vazio():
    """Periodo sem trade e 0.0, nao ausencia: o Reality Check compara o MAXIMO entre configs
    e series de tamanhos diferentes comparariam coisas diferentes."""
    trades = [
        {"ts": T0 + 3_600_000, "pnl": 10.0},          # dia 0
        {"ts": T0 + 7_200_000, "pnl": -4.0},          # dia 0
        {"ts": T0 + 2 * DIA, "pnl": 7.0},             # dia 2 (dia 1 fica vazio)
    ]
    grade = V.grade_de_periodos(trades)
    assert len(grade) == 3
    assert V.pnl_por_periodo(trades, grade) == [6.0, 0.0, 7.0]


def test_grade_e_comum_entre_configs():
    a = trades_diarios([1.0] * 5)
    b = [dict(t) for t in trades_diarios([2.0] * 3)]          # so os 3 primeiros dias
    grade = V.grade_de_periodos(a + b)
    assert len(V.pnl_por_periodo(a, grade)) == len(V.pnl_por_periodo(b, grade)) == 5
    assert V.pnl_por_periodo(b, grade) == [2.0, 2.0, 2.0, 0.0, 0.0]


def test_atribuir_saida_recusa_trade_sem_ts_saida():
    """`atribuir='saida'` e o alvo da revisao, e hoje nao ha `ts_saida`. A funcao recusa em
    vez de cair no silencio para a entrada -- default silencioso aqui viraria numero errado
    sem aviso."""
    with pytest.raises(ValueError, match="ts_saida"):
        V.pnl_por_periodo(trades_diarios([1.0, 2.0]), [0, 1], atribuir="saida")


def test_atribuir_saida_funciona_quando_ha_ts_saida():
    """A implementacao ja esta pronta para o dia em que o [T-EDGE] gravar `ts_saida`: aqui o
    P&L cai no dia da SAIDA, nao no da entrada."""
    t = [{"ts": T0, "pnl": 5.0, "ts_saida": T0 + 2 * DIA}]
    assert V.pnl_por_periodo(t, [T0 // DIA, T0 // DIA + 1, T0 // DIA + 2],
                             atribuir="saida") == [0.0, 0.0, 5.0]


# ============================ bootstrap de bloco ============================
def test_block_bootstrap_devolve_n_indices_em_blocos_contiguos_e_circulares():
    rng = np.random.default_rng(1)
    idx = V.block_bootstrap_idx(20, block=5, rng=rng)
    assert len(idx) == 20
    assert idx.min() >= 0 and idx.max() < 20
    for b in range(4):                                        # cada bloco e contiguo mod n
        bloco = idx[b * 5:(b + 1) * 5]
        for j in range(1, 5):
            assert bloco[j] == (bloco[0] + j) % 20


def test_block_bootstrap_com_block_1_e_o_iid():
    """[F18] block=1 E o bootstrap iid -- e por isso a sensibilidade a block entrega de graca
    o delta 'quanto o iid estava inflado', sem precisar do Politis-White."""
    idx = V.block_bootstrap_idx(50, block=1, rng=np.random.default_rng(3))
    assert len(idx) == 50
    assert len(set(idx.tolist())) > 1                          # nao degenerou num bloco so


def test_block_bootstrap_e_deterministico_com_a_mesma_seed():
    a = V.block_bootstrap_idx(30, block=4, rng=np.random.default_rng(9))
    b = V.block_bootstrap_idx(30, block=4, rng=np.random.default_rng(9))
    assert a.tolist() == b.tolist()


def test_bootstrap_bloco_recusa_lista_de_trades():
    """[F1] O achado BLOQUEANTE da revisao. A lista OOS nao esta ordenada no tempo -- ela e
    montada moeda a moeda e depois filtrada por fold, entao a ordem e (fold, moeda, tempo).
    Bloco nessa ordem forma blocos que atravessam fronteira de moeda e saltam no tempo: seria
    PIOR que o iid, e com aparencia de mais rigor. Por isso a chamada tem de DECLARAR que a
    serie e temporal."""
    with pytest.raises(ValueError, match="serie ordenada no tempo"):
        V.bootstrap_ci([1.0] * 50, modo="bloco", eh_serie_temporal=False)


def test_ic_de_bloco_e_mais_largo_que_o_iid_pelo_fator_certo_em_ar1():
    """A prova que separa 'a mecanica do bloco funciona' de 'a estatistica do bloco funciona'.

    Sob AR(1) com phi, a variancia de longo prazo da media e a iid multiplicadas por
    (1+phi)/(1-phi); logo a largura do IC de bloco deve ser ~sqrt((1+phi)/(1-phi)) vezes a do
    iid. Com phi=0,5 o fator e 1,73. Um bootstrap de bloco que apenas reamostra em blocos sem
    preservar dependencia passaria num teste de 'e diferente do iid' e falharia aqui.
    """
    phi = 0.5
    serie = serie_ar1(1200, phi, seed=11)
    lo_b, hi_b = V.bootstrap_ci(serie, n_boot=1500, modo="bloco", eh_serie_temporal=True,
                                block=20, seed=7)
    lo_i, hi_i = V.bootstrap_ci(serie, n_boot=1500, modo="iid", eh_serie_temporal=True, seed=7)
    razao = (hi_b - lo_b) / (hi_i - lo_i)
    esperado = math.sqrt((1 + phi) / (1 - phi))               # 1,732
    assert razao > 1.0, "o IC de bloco tem de ser MAIS largo que o iid sob autocorrelacao"
    assert abs(razao - esperado) / esperado < 0.25, (razao, esperado)


def test_ic_de_bloco_e_iid_coincidem_em_ruido_branco():
    """O outro lado da mesma prova, e o que [F12] pede que a regua saiba dizer: quando NAO ha
    autocorrelacao, o iid nunca esteve inflado e o bloco nao corrige nada."""
    serie = serie_ar1(1200, 0.0, seed=12)
    lo_b, hi_b = V.bootstrap_ci(serie, n_boot=1500, modo="bloco", eh_serie_temporal=True,
                                block=20, seed=7)
    lo_i, hi_i = V.bootstrap_ci(serie, n_boot=1500, modo="iid", eh_serie_temporal=True, seed=7)
    assert abs((hi_b - lo_b) / (hi_i - lo_i) - 1.0) < 0.25


# ============================ p-valores ============================
def test_p_valor_nunca_e_zero():
    """[F5] `#{V*>=V}/B` pode dar 0, e p=0 e mentira: com B=2000 a resolucao e 5e-4. A forma
    (1+#{>=})/(B+1) corrige isso e o empate (a distribuicao bootstrap e discreta)."""
    assert V._p_bootstrap(0, 2000) == pytest.approx(1.0 / 2001)
    assert V._p_bootstrap(2000, 2000) == pytest.approx(1.0)
    serie = [50.0] * 300                                       # media enorme, sd zero-ish
    matriz = {("a",): serie, ("b",): serie}
    assert V.reality_check(matriz, n_boot=200, block=5, seed=1)["p_valor"] > 0


def test_reality_check_com_uma_config_reduz_ao_bootstrap_unilateral_da_media():
    """`REVISAO-ITEM1.md` §E.3, item 4. Com N=1 nao ha multiplicidade para corrigir, entao o
    RC tem de reproduzir o p-valor do bootstrap recentrado da media. Qualquer erro de
    recentragem por f_k aparece aqui."""
    serie = serie_ar1(400, 0.3, seed=5, mu=0.15)
    p_rc = V.reality_check({("so",): serie}, n_boot=1000, block=5, seed=3)["p_valor"]
    p_un = V.p_valor_config(serie, n_boot=1000, block=5, seed=3)
    assert p_rc == pytest.approx(p_un, abs=1e-9)


def test_reality_check_detecta_drift_forte():
    serie_boa = serie_ar1(600, 0.1, seed=21, mu=0.6)
    matriz = {("boa",): serie_boa}
    for k in range(4):
        matriz[("ruim", k)] = serie_ar1(600, 0.1, seed=30 + k, mu=0.0)
    assert V.reality_check(matriz, n_boot=1000, block=5, seed=4)["p_valor"] <= 0.05


def test_reality_check_calibrado_rapido():
    """Tamanho e uniformidade em M=40 paineis de ruido branco (`REVISAO-ITEM1.md` §E.3).

    A versao pesada (M=200, banda binomial [0,02; 0,09]) esta marcada `lento` abaixo. Aqui a
    banda e larga de proposito: o objetivo do laco rapido e pegar o instrumento QUEBRADO (um
    RC que rejeita sempre ou nunca), nao medir calibracao fina.
    """
    ps = _ps_de_paineis_nulos(M=40, T=250, K=4, n_boot=200, seed=101)
    assert 0.0 <= (ps <= 0.05).mean() <= 0.20
    assert abs(ps.mean() - 0.5) < 0.20


@pytest.mark.lento
def test_reality_check_calibrado_uniformidade():
    """A prova que define 'teste calibrado', e a que o `ITEM1` original nao tinha.

    "ruido puro -> p alto na maioria das seeds" e smoke test: um bug que faca V*
    sistematicamente grande demais produz p~1 sempre e passa com louvor -- ficaria um Reality
    Check que nunca rejeita nada, e um teste verde. Uniformidade dos p-valores pega os DOIS
    modos de falha de uma vez: anti-conservador e absurdamente conservador.
    """
    M = 200
    ps = _ps_de_paineis_nulos(M=M, T=300, K=5, n_boot=400, seed=202)
    taxa = float((ps <= 0.05).mean())
    assert 0.01 <= taxa <= 0.12, f"taxa de rejeicao a 5% fora da banda: {taxa}"
    assert abs(ps.mean() - 0.5) < 0.10, f"media dos p = {ps.mean()}"
    ks = float(np.abs(np.sort(ps) - np.arange(1, M + 1) / M).max())
    assert ks < 0.18, f"desvio maximo da CDF uniforme = {ks}"


def _ps_de_paineis_nulos(M, T, K, n_boot, seed):
    rng = np.random.default_rng(seed)
    ps = []
    for _ in range(M):
        matriz = {("c", k): rng.normal(0.0, 1.0, size=T).tolist() for k in range(K)}
        ps.append(V.reality_check(matriz, n_boot=n_boot, block=5,
                                  seed=int(rng.integers(1, 10 ** 8)))["p_valor"])
    return np.asarray(ps)


def test_spa_e_rc_colapsam_com_configs_quase_identicas():
    """[F15] Com configs correlacionadas a ~0,95 o RC e o SPA sao o mesmo teste. Quando os dois
    derem igual na rodada real, isso NAO e bug: e evidencia de que o grid inteiro vale ~1
    tentativa -- e e por isso que o `n_trials` nao pode sair do tamanho do GRID."""
    base = serie_ar1(500, 0.2, seed=77)
    rng = np.random.default_rng(78)
    matriz = {("c", k): (np.asarray(base) + rng.normal(0, 0.05, 500)).tolist()
              for k in range(6)}
    p_rc = V.reality_check(matriz, n_boot=800, block=5, seed=6)["p_valor"]
    p_spa = V.spa_hansen(matriz, n_boot=800, block=5, seed=6)["p_valor"]
    assert abs(p_rc - p_spa) < 0.10, (p_rc, p_spa)


# ============================ FDR ============================
def test_fdr_bh_do_criterio_de_aceite():
    """O caso literal da linha 272 do `ITEM1-VALIDACAO-RIGOROSA.md`."""
    sobrevive, limiar = V.fdr_bh([0.001, 0.2, 0.5], q=0.1)
    assert sobrevive == [True, False, False]
    assert limiar == pytest.approx(1 / 3 * 0.1, abs=1e-6)


def test_fdr_bh_casos_de_borda():
    assert V.fdr_bh([], q=0.1) == ([], 0.0)
    assert V.fdr_bh([0.05], q=0.1)[0] == [True]
    assert V.fdr_bh([0.5], q=0.1)[0] == [False]
    assert V.fdr_bh([0.02, 0.02, 0.02], q=1.0)[0] == [True, True, True]
    assert V.fdr_bh([0.9, 0.9], q=0.1)[0] == [False, False]


def test_fdr_esta_fora_do_veredito():
    """[F16] Uma condicao que nao pode falhar independentemente do Reality Check nao e
    condicao. O FDR e reportado e nao entra na decisao -- esta prova amarra isso, para que
    ninguem o promova de volta sem passar por aqui."""
    res = _res_sintetico(mu=0.0, seed=5)
    assert "fdr" in res["bloco_a"]
    assert "FDR" not in res["veredito"]["motivo"] and "fdr" not in res["veredito"]["motivo"]


# ============================ DSR, PSR, MDS ============================
def test_mds_bate_a_aritmetica_da_revisao():
    """[F6] T=180 -> ~3,5 e T=1095 -> ~1,5 sao os numeros que justificaram
    `DIAS: 180 -> 1095`. Se esta conta mudar, a justificativa da constante mudou junto."""
    assert V.mds_sharpe(180) == pytest.approx(3.54, abs=0.05)
    assert V.mds_sharpe(1095) == pytest.approx(1.44, abs=0.05)
    assert V.mds_sharpe(1095) < V.mds_sharpe(180)


def test_dsr_cresce_quando_n_trials_cai_e_a_dependencia_e_logaritmica():
    """[F10] Publicar a tabela so vale se a dependencia for mesmo logaritmica: errar
    `n_trials` por duas ordens de grandeza tem de apenas dobrar o sr0."""
    serie = serie_ar1(600, 0.0, seed=31, mu=0.05)
    tab = dict(V.sensibilidade_n_trials(serie, ns=(6, 100, 10000)))
    assert tab[6]["dsr"] >= tab[100]["dsr"] >= tab[10000]["dsr"]
    assert 1.5 < tab[10000]["sr0"] / tab[6]["sr0"] < 3.5


def test_dsr_sobre_serie_diaria_e_menor_que_sobre_a_lista_de_trades():
    """[Q-1, item 1] A mudanca de objeto e conservadora, e a prova afirma a DIRECAO.

    Varios trades por dia contados como observacoes independentes inflam o n do DSR, e o
    `sr0` esperado cai com sqrt(1/n): DSR sobre a lista de trades e maior que sobre a serie
    diaria que agrega os mesmos trades. Era exatamente o vies anti-conservador que o card
    veio remover.
    """
    rng = np.random.default_rng(44)
    trades, dia0 = [], T0 // DIA
    for d in range(400):
        for _ in range(4):                                     # 4 trades por dia
            trades.append({"ts": int((dia0 + d) * DIA + rng.integers(0, DIA)),
                           "pnl": float(rng.normal(0.4, 8.0))})
    grade = V.grade_de_periodos(trades)
    diaria = V.pnl_por_periodo(trades, grade)
    d_dia = V.deflated_sharpe(diaria, 100)
    d_trades = V.deflated_sharpe([t["pnl"] for t in trades], 100)
    assert d_trades["n"] == 4 * d_dia["n"]
    assert d_trades["dsr"] > d_dia["dsr"], (d_trades, d_dia)


def test_psr_nao_deflaciona():
    """[F8] No BLOCO B o objeto e o PROCESSO, que nao foi escolhido como maximo de n_trials --
    deflacionar ali seria descontar duas vezes. Logo PSR >= DSR sempre."""
    serie = serie_ar1(500, 0.0, seed=51, mu=0.08)
    assert V.probabilistic_sharpe(serie)["psr"] >= V.deflated_sharpe(serie, 100)["dsr"]


# ============================ walk-forward e veredito ============================
def _res_sintetico(mu=0.0, seed=0, n_dias=900, cfgs=((50, 22), (55, 22), (65, 25))):
    por_cfg = {}
    for k, cfg in enumerate(cfgs):
        rng = np.random.default_rng(seed * 100 + k)
        por_cfg[cfg] = trades_diarios(rng.normal(mu, 10.0, size=n_dias).tolist())
    return V.walk_forward(gerador_constante(por_cfg), list(cfgs), n_trials=100,
                          rotulo="sintetico")


def test_veredito_inconclusivo_quando_o_mds_e_grande():
    """[F14 / Q-1 item 4] A TERCEIRA resposta, e a razao de ser do card.

    Com poucos dias o instrumento nao tem poder, e "sem edge" seria uma afirmacao que o dado
    nao sustenta: a mesma frase sairia para uma estrategia sem edge e para um edge real que a
    regua nao consegue ver. Aqui o veredito tem de ser INCONCLUSIVO, e o motivo tem de citar
    o MDS.
    """
    res = _res_sintetico(mu=0.0, seed=1, n_dias=90)
    assert res["bloco_b"]["mds"] > V.MDS_LIMITE
    assert res["veredito"]["classe"] == "INCONCLUSIVO"
    assert "MDS" in res["veredito"]["motivo"]


def test_o_portao_de_poder_vem_antes_do_teste_de_edge():
    """A ordem e o conserto. Com serie curta E drift forte, um instrumento sem poder
    declarado responderia 'EDGE'; a regua nova recusa a emitir veredito antes de ter poder --
    e e isso que vai impedir o Item 2 (portoes restritivos, poucos trades) de virar falso
    positivo por amostra pequena."""
    res = _res_sintetico(mu=8.0, seed=2, n_dias=90)
    assert res["bloco_b"]["ic_bloco"][0] > 0                   # o dado "diz" que ha edge
    assert res["veredito"]["classe"] == "INCONCLUSIVO"         # e a regua se recusa mesmo assim


def test_veredito_sem_evidencia_diz_o_que_nao_exclui():
    """[F7] O veredito negativo antigo era mais forte do que o dado sustenta: ele arredondava
    'nao consegui medir' para 'nao existe'. Agora o negativo carrega o IC do Sharpe anualizado
    -- o limite superior e o edge que o teste NAO exclui."""
    res = _res_sintetico(mu=0.0, seed=3, n_dias=900)
    assert res["veredito"]["classe"] == "SEM_EVIDENCIA"
    lo, hi = res["veredito"]["nao_exclui"]
    assert lo < 0 < hi


def test_veredito_edge_quando_o_drift_e_real_e_ha_poder():
    res = _res_sintetico(mu=3.0, seed=4, n_dias=900)
    assert res["bloco_b"]["mds"] <= V.MDS_LIMITE
    assert res["veredito"]["classe"] == "EDGE"


def test_serie_oos_do_WALK_FORWARD_cobre_so_a_janela_oos_nao_a_timeline_inteira():
    """Bug que quase entrou no registro: a serie diaria OOS montada sobre a grade INTEIRA.

    O primeiro dos `N_FOLDS+1` segmentos e treino puro -- nunca foi testado, nao ha decisao a
    avaliar ali. Empilhar esses ~1/6 de dias como "dia de P&L zero" erra os DOIS numeros que
    o [Q-1] veio consertar, e em direcoes opostas: deflaciona o Sharpe diario (mais zeros no
    denominador da media) e infla o T que alimenta o MDS (portao de poder frouxo demais).

    O BLOCO A continua na timeline inteira, e isso e correto: cada config foi rodada nela
    inteira, e o nulo do Reality Check e sobre a familia in-sample.

    [N-7] O teste passou a rodar sob `cv="walk_forward"` EXPLICITO. A propriedade que ele
    guarda e do walk-forward e so dele -- ela nasce de haver um segmento que nunca foi testado.
    Sob CPCV nao ha esse segmento, e o teste companheiro logo abaixo afirma o oposto, com o
    porque.
    """
    por_cfg = {}
    for k, cfg in enumerate(((50, 22), (55, 22), (65, 25))):
        rng = np.random.default_rng(1100 + k)
        por_cfg[cfg] = trades_diarios(rng.normal(0.0, 10.0, 1200).tolist())
    base = V._nucleo(por_cfg, **{**V.PADRAO, "cv": "walk_forward"})
    grade_toda, grade_oos = base["grade"], base["grade_oos"]
    assert len(grade_oos) < len(grade_toda)
    assert 0.75 < len(grade_oos) / len(grade_toda) < 0.90       # ~5/6 da timeline
    assert len(base["serie_oos"]) == len(grade_oos)
    dias_oos = {t["ts"] // DIA for t in base["oos"]}
    assert min(dias_oos) >= grade_oos[0] and max(dias_oos) <= grade_oos[-1]
    assert base["serie_oos"][0] != 0.0 or base["serie_oos"][1] != 0.0


def test_N7_no_CPCV_a_janela_INTEIRA_e_OOS_e_isso_muda_o_T_do_portao_de_poder():
    """O contrario do teste acima, e a diferenca precisa ficar afirmada em vez de descoberta.

    Sob CPCV todo grupo e teste em algum corte, entao cada trajetoria cobre a janela inteira e
    `grade_oos == grade`. A consequencia e um T MAIOR, e T maior baixa o MDS -- ou seja, o
    instrumento passa a parecer com mais poder. Essa e a direcao CONFORTAVEL, e por isso ela
    tem de estar num teste e no relatorio, nao so no commit.

    Ela e legitima (aquele pedaco de fato foi avaliado fora da amostra que o escolheu) mas vem
    junto com o preco declarado do CPCV: em varios cortes o treino esta DEPOIS do teste, entao
    o numero nao e simulacao de operacao ao vivo.
    """
    por_cfg = {}
    for k, cfg in enumerate(((50, 22), (55, 22), (65, 25))):
        rng = np.random.default_rng(1100 + k)
        por_cfg[cfg] = trades_diarios(rng.normal(0.0, 10.0, 1200).tolist())
    cp = V._nucleo(por_cfg, **{**V.PADRAO, "cv": "cpcv"})
    wf = V._nucleo(por_cfg, **{**V.PADRAO, "cv": "walk_forward"})
    assert cp["grade_oos"] == cp["grade"]
    assert len(cp["grade_oos"]) > len(wf["grade_oos"])
    assert V.mds_sharpe(len(cp["grade_oos"])) < V.mds_sharpe(len(wf["grade_oos"]))
    # o BLOCO A nao muda: ele sempre foi a timeline inteira, nos dois esquemas
    assert cp["matriz_is"] == wf["matriz_is"]


def test_padrao_travado_walk_forward_nao_aceita_criterio():
    """[F3 / Q-1 item 6] `criterio` x `modo` x `atribuir` x `block` x `purga` sao 120 maneiras
    de rodar a regua. Um instrumento que existe para detectar data-snooping nao pode oferecer
    120 vereditos e deixar quem chama escolher. As variantes existem -- em `sensibilidade()`,
    que imprime todas, sempre, e nunca decide."""
    por_cfg = {(50, 22): trades_diarios([1.0] * 200)}
    g = gerador_constante(por_cfg)
    for proibido in ("criterio", "modo", "atribuir", "block", "purga"):
        with pytest.raises(TypeError):
            V.walk_forward(g, [(50, 22)], n_trials=100, **{proibido: "pnl"})


def test_padrao_e_o_criterio_do_veredito_e_nao_muda_entre_rodadas():
    """Determinismo: `random` global sem seed tornava `python -m pesquisa.validacao`
    irreproduzivel, e registrar numero irreproduzivel e registro decorativo (`ITEM1` §2/P6).
    Duas rodadas do mesmo dado tem de dar o MESMO veredito, bit a bit."""
    a = _res_sintetico(mu=0.0, seed=6)
    b = _res_sintetico(mu=0.0, seed=6)
    assert a["veredito"] == b["veredito"]
    assert a["bloco_a"]["reality_check"] == b["bloco_a"]["reality_check"]
    assert a["bloco_b"]["ic_bloco"] == b["bloco_b"]["ic_bloco"]
    assert a["padrao"] == V.PADRAO


def test_sensibilidade_roda_todas_as_variantes_e_nao_decide():
    """`sensibilidade()` devolve diagnostico; nenhuma variante carrega veredito."""
    res = _res_sintetico(mu=0.0, seed=7)
    sens = V.sensibilidade(res)
    assert [c for c, _ in sens["criterio"]] == list(V.CRITERIOS)
    assert [m for m, _ in sens["modo"]] == list(V.MODOS)
    assert [b for b, _ in sens["block"]] == list(V.BLOCKS)
    for _, r in sens["criterio"]:
        assert "veredito" not in r


def test_relatorio_imprime_os_dois_blocos_e_o_veredito(capsys):
    """[F8] Dois blocos ROTULADOS, com o nulo de cada um escrito -- e o que impede confundir
    'a melhor de N configs in-sample' com 'o processo aplicado cego pra frente'."""
    V.relatorio(_res_sintetico(mu=0.0, seed=8))
    saida = capsys.readouterr().out
    for esperado in ("BLOCO A", "BLOCO B", "Reality Check", "Hansen SPA", "MDS",
                     "sensibilidade a n_trials", "VEREDITO", "purga", "PADRAO (travado)"):
        assert esperado in saida, esperado


# ============================ purga ============================
def _por_cfg_com_saida(dur_dias):
    """Uma config so, 300 trades diarios, cada um durando `dur_dias`."""
    pnls = [1.0] * 300
    saidas = [T0 + (i + dur_dias) * DIA for i in range(300)]
    return {(50, 22): trades_diarios(pnls, ts_saida=saidas)}


def test_purga_tira_do_treino_o_trade_que_cruza_a_borda():
    """`ITEM1` §3.2, formulacao de Lopez de Prado: so entra no treino trade cujo span de label
    termine antes da borda. O trade que entra antes e sai depois carrega P&L determinado
    DENTRO da janela de teste -- e vazamento, nao ruido."""
    trades = _por_cfg_com_saida(dur_dias=5)[(50, 22)]
    borda = T0 + 100 * DIA
    com = V._treino(trades, T0, borda, purga=True, gap_ms=0, tem_saida=True)
    sem = V._treino(trades, T0, borda, purga=False, gap_ms=0, tem_saida=True)
    assert len(sem) == 100                                    # entradas nos dias 0..99
    assert len(com) == 95                                     # os 5 que saem depois da borda caem
    assert all(t["ts_saida"] < borda for t in com)


def test_purga_desliga_sozinha_e_avisa_quando_falta_ts_saida():
    """Sem `ts_saida` a purga nao tem como agir. O que ela NAO faz e fingir que agiu: o
    resultado carrega `purga_ativa=False` e o motivo, e o relatorio imprime.

    E o unico item do `ITEM1` §5 que ficou de fora do [Q-1], e ficou por fronteira de
    territorio: `pesquisa/backtest_plataforma.py:82` e do `T-EDGE`.
    """
    res = _res_sintetico(mu=0.0, seed=9, n_dias=300)
    assert res["purga_ativa"] is False
    assert "ts_saida" in res["purga_motivo"]
    assert res["padrao"]["purga"] is True                      # foi PEDIDA, e o registro fica


def test_gap_pre_teste_nao_e_o_embargo_de_lopez_de_prado():
    """[F4] O embargo de LdP existe porque em cross-validation parte do treino vem DEPOIS do
    teste. Num walk-forward sequencial nao ha treino apos o teste para embargar, e a spec
    original ("descarta faixa apos a janela de teste") descartaria trades de TESTE --
    degradando a amostra OOS sem corrigir vies nenhum. O que sobra de legitimo e descartar do
    TREINO os ultimos h ms antes da borda, e e isso que `gap_pre_teste_ms` faz."""
    trades = _por_cfg_com_saida(dur_dias=1)[(50, 22)]
    borda = T0 + 100 * DIA
    assert len(V._treino(trades, T0, borda, False, 0, True)) == 100
    assert len(V._treino(trades, T0, borda, False, 10 * DIA, True)) == 90
    assert not hasattr(V, "embargo_ms")
    assert "embargo_ms" not in V.PADRAO


# ============================ criterio de selecao ============================
def test_criterio_default_e_sharpe_e_nao_soma_bruta_de_pnl():
    """[F3] Soma bruta de P&L favorece a config que mais OPERA, nao a melhor -- o proprio
    `ITEM1` §2/P5 diagnostica isso e mesmo assim a assinatura proposta manteve `criterio='pnl'`.
    Aqui: uma config opera muito com edge nulo, outra opera pouco com edge claro."""
    assert V.PADRAO["criterio"] == "sharpe"
    rng = np.random.default_rng(71)
    muitos = ([0.1] * 100 + [-3.0, 3.2] * 50)                 # soma alta, sharpe baixo
    poucos = (0.5 + rng.normal(0, 0.02, 20)).tolist()         # soma baixa, sharpe alto
    assert sum(muitos) > sum(poucos)
    assert V._valor_criterio(muitos, "pnl") > V._valor_criterio(poucos, "pnl")
    assert V._valor_criterio(poucos, "sharpe") > V._valor_criterio(muitos, "sharpe")


def test_criterio_sharpe_com_variancia_zero_escolhe_pelo_sinal():
    """Ramo que a primeira versao errava, e errava para o lado ruim: com sd=0 o Sharpe diverge
    e quem decide e o SINAL do numerador. Tratar tudo como -1e18 faria o fold preferir uma
    config sem trades a uma config constante e LUCRATIVA."""
    assert V._valor_criterio([0.5] * 20, "sharpe") > 0
    assert V._valor_criterio([-0.5] * 20, "sharpe") < 0
    assert V._valor_criterio([], "sharpe") < 0


# ============================ diagnosticos ============================
def test_acf_recupera_o_phi_de_um_ar1():
    """[F12] A ACF existe para a regua conseguir dizer 'o problema que eu ia consertar nao
    existia'. Se ela nao recuperasse um phi conhecido, essa afirmacao nao valeria nada."""
    a = V.acf(serie_ar1(3000, 0.5, seed=61), lags=3)
    assert a[0] == pytest.approx(0.5, abs=0.08)
    assert a[1] == pytest.approx(0.25, abs=0.08)


def test_acf_de_ruido_branco_fica_dentro_da_banda():
    a = V.acf(serie_ar1(2000, 0.0, seed=62), lags=10)
    banda = V.banda_acf(2000)
    assert sum(1 for x in a if abs(x) > banda) <= 2            # ~5% de 10 lags, com folga


def test_concentracao_flagra_lucro_vindo_de_poucos_dias():
    """[F17] Diagnostico, nunca portao: com 5 folds a mediana e um teste de ~1 bit. O que
    informa e a dispersao."""
    serie = [0.0] * 200
    serie[3] = 100.0
    por_fold = [(1, "c", 10, 100.0), (2, "c", 10, 0.0), (3, "c", 10, 0.0),
                (4, "c", 10, 0.0), (5, "c", 10, 0.0)]
    c = V.concentracao(serie, por_fold)
    assert c["top5_dias_sobre_lucro_bruto"] == pytest.approx(1.0)
    assert c["folds_positivos"] == 1 and c["folds"] == 5


def test_controle_nulo_do_pipeline_nao_rejeita_em_massa():
    """[F9, parcial] Painel embaralhado por blocos e recentrado nao tem sinal; se o pipeline
    rejeitasse em massa aqui, o veredito positivo dele nao valeria nada em lugar nenhum."""
    res = _res_sintetico(mu=0.0, seed=10, n_dias=400)
    cn = V.controle_nulo(res, M=30, seed=99)
    assert cn["taxa_rejeicao_5pct"] <= 0.25
    assert 0.25 < cn["media_p"] < 0.75


# ============================ constantes que sao decisao ============================
def test_constantes_registradas():
    """Estas nao sao configuracao: sao decisao com justificativa escrita. Mudar qualquer uma
    muda o significado do veredito, e o teste existe para que a mudanca passe por aqui.

    `DIAS=1095` [F6] e o que da poder ao instrumento; `N_TRIALS=100` [F10] e piso CONTADO das
    varreduras historicas do projeto, nao estimativa; `MDS_LIMITE=2.0` [F14] e onde a regua
    para de responder.
    """
    assert V.DIAS == 1095
    assert V.N_TRIALS == 100
    assert V.MDS_LIMITE == 2.0
    assert V.T_EFETIVO_MINIMO == 100
    assert V.PPA == 365
    assert V.PADRAO["seed"] == 42


# ============================ o motor de backtest: `ts_saida` ============================
# Estas provas nao sao da regua: sao do gerador que alimenta a regua
# (`pesquisa/backtest_plataforma.backtest_ativo`). Moram aqui porque o campo que elas provam
# -- `ts_saida` -- so existe para a purga de borda de fold, que e da regua. Rodam offline
# porque o sinal e INJETADO (`sinal_fn`): sem isso, um `df` teria de disparar o `scoring` E
# andar pela trajetoria que o teste quer, e o teste passaria a provar o scoring.
TF_MS = 3_600_000


def df_sintetico(closes, highs=None, lows=None, opens=None, tf_ms=TF_MS):
    """`df` minimo que `backtest_ativo` consome: OHLC, timestamp, volume e `bb_mid`."""
    n = len(closes)
    return pd.DataFrame({
        "timestamp": [T0 + i * tf_ms for i in range(n)],
        "open": list(opens or closes), "high": list(highs or closes),
        "low": list(lows or closes), "close": list(closes),
        "volume": [1.0] * n, "bb_mid": list(closes),
    })


def sinal_em(indices, direcao=1, stop_dist=0.03, conv=99.0, adx=40.0):
    """Gerador de sinal que dispara SO nos indices pedidos -- o resto do df fica mudo."""
    alvo = set(indices)

    def fn(df, i):
        if i not in alvo:
            return None
        return {"direcao": direcao, "conviccao": conv, "adx": adx, "n_fatores": 3,
                "stop_dist": stop_dist, "tipo": "tendencia"}
    return fn


def test_backtest_grava_ts_saida_no_FIM_do_candle_de_saida():
    """A divida que a onda 1 deixou dentro do `T-EDGE`: sem `ts_saida` a purga desliga
    sozinha e o vazamento de borda de fold segue presente e nao medido -- empurrando o
    resultado para CIMA, contra a conclusao negativa.

    O carimbo e o FIM do candle de saida, nao o comeco: e o instante em que o desfecho deixou
    de ser incerto. Saida por stop dispara em algum ponto INTERNO do candle e o backtest nao
    sabe qual -- carimbar o comeco afirmaria um instante nao observado, e purgaria de MENOS.
    """
    precos = [100.0] * 70
    lows = list(precos)
    lows[65] = 90.0                                    # fura o stop de 3% no candle 65
    df = df_sintetico(precos, lows=lows)
    tr = B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=sinal_em([60]))
    assert len(tr) == 1
    t = tr[0]
    assert t["motivo"] == "stop"
    assert t["ts"] == T0 + 61 * TF_MS                  # fill no OPEN do candle seguinte
    assert t["ts_saida"] == T0 + 65 * TF_MS + TF_MS    # FIM do candle de saida
    assert t["ts_saida"] > t["ts"]


def test_ts_saida_existe_em_todo_trade_e_nunca_precede_a_entrada():
    """Vale para saida por regime tambem, que fecha em `closes[i]` e nao em nivel intrabar."""
    precos = [100.0] * 62 + [101.0] * 8
    df = df_sintetico(precos)
    tr = B.backtest_ativo("X/USDT", 0, 100, 10, df=df,
                          sinal_fn=sinal_em([60], direcao=1))
    # o sinal so dispara em 60; nos candles seguintes `fn` devolve None -> nao ha flip, a
    # posicao atravessa o df inteiro e o trade nao fecha
    assert tr == []
    tr = B.backtest_ativo("X/USDT", 0, 100, 10, df=df,
                          sinal_fn=sinal_em([60, 64], direcao=1))
    assert len(tr) == 0                                 # mesma direcao em 64: nao e flip
    def fn(df_, i):
        if i == 60:
            return {"direcao": 1, "conviccao": 99.0, "adx": 40.0, "n_fatores": 3,
                    "stop_dist": 0.03, "tipo": "tendencia"}
        if i == 64:
            return {"direcao": -1, "conviccao": 99.0, "adx": 40.0, "n_fatores": 3,
                    "stop_dist": 0.03, "tipo": "tendencia"}
        return None
    tr = B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=fn)
    assert len(tr) == 1 and tr[0]["motivo"] == "regime"
    assert tr[0]["ts_saida"] == T0 + 64 * TF_MS + TF_MS
    assert all(t["ts_saida"] >= t["ts"] for t in tr)


def test_purga_fica_ATIVA_com_os_trades_do_motor_de_verdade():
    """O contraste com `test_purga_desliga_sozinha_e_avisa_quando_falta_ts_saida`: aquele
    prova que a regua nao MENTE quando o campo falta; este prova que o campo passou a vir."""
    precos = [100.0] * 70
    lows = list(precos)
    lows[65] = 90.0
    tr = B.backtest_ativo("X/USDT", 0, 100, 10, df=df_sintetico(precos, lows=lows),
                          sinal_fn=sinal_em([60]))
    assert V._tem_ts_saida({("c",): tr}) is True


def test_sensibilidade_roda_atribuir_so_quando_ha_ts_saida():
    """[F3] `atribuir='saida'` virou possivel com o `ts_saida`, e mesmo assim NAO virou o
    `PADRAO`: ele aparece como variante de diagnostico, ao lado de 'entrada'. Trocar o
    criterio travado do veredito e decisao de dono, nao efeito colateral de um campo novo."""
    assert V.PADRAO["atribuir"] == "entrada"
    sem = V.sensibilidade(_res_sintetico(mu=0.0, seed=3, n_dias=300))
    assert sem["atribuir"] == []                        # gerador sintetico nao grava ts_saida

    pnls = serie_ar1(300, 0.0, seed=4)
    saidas = [T0 + (i + 2) * DIA for i in range(300)]
    por_cfg = {(50, 22): trades_diarios(pnls, ts_saida=saidas)}
    res = V.walk_forward(gerador_constante(por_cfg), list(por_cfg), n_trials=100)
    com = V.sensibilidade(res)
    assert [nome for nome, _ in com["atribuir"]] == ["entrada", "saida"]
    assert all(r is not None for _, r in com["atribuir"])


def test_duracao_da_barra_sai_do_df_e_nao_do_default_de_tf():
    """A causa: `tfh` vinha de `TF_MAPA[tf]`, e `tf` tem default (`"15m"`). Quem passa um `df`
    pronto nao precisa passar `tf` -- e `validacao.gerador_tendencia` nao passava, com candles
    de 1h. A barra valia 0,25h para um df de 1h, entao o funding do `[P2-10]` era cobrado por
    UM QUARTO do hold real. A DIRECAO do erro segue o sinal do funding liquido do periodo --
    net-LONG paga 1/4 e o P&L sai alto, net-SHORT recebe 1/4 e o P&L sai baixo --, entao o que
    o teste fixa e a MAGNITUDE (4x), que essa sim nao depende do periodo.

    Aqui o df tem passo de 1h e `tf` fica no default errado de proposito. Se a duracao voltar
    a sair do default, `ts_saida` anda 15 min por barra e o funding volta a ser 1/4."""
    precos = [100.0] * 70
    lows = list(precos)
    lows[65] = 90.0
    df = df_sintetico(precos, lows=lows)               # passo de 1h nos timestamps
    assert B.TF == "15m"                               # o default que enganava
    t_medido = B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=sinal_em([60]),
                                funding_8h=0.001)[0]
    t_default = B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=sinal_em([60]),
                                 funding_8h=0.001, tf_horas=0.25)[0]   # o valor antigo
    # entrada no open da barra 61, saida no FIM da barra 65 -> 5 barras de distancia
    assert t_medido["ts_saida"] - t_medido["ts"] == 5 * TF_MS          # barras de 1h
    # com a duracao errada, os timestamps do df continuam de 1h mas a "barra" vale 15 min:
    # o carimbo de saida cai 45 min ANTES do fechamento real -- purga de menos, e em silencio
    assert t_default["ts_saida"] - t_default["ts"] == 4 * TF_MS + 900_000
    # funding e LINEAR no tempo de hold: 4x o hold, 4x o carry pago pelo LONG
    carry_medido = t_default["pnl"] - t_medido["pnl"]
    carry_default = (t_default["pnl"] - B.backtest_ativo(
        "X/USDT", 0, 100, 10, df=df, sinal_fn=sinal_em([60]), funding_8h=0.0,
        tf_horas=0.25)[0]["pnl"]) * -1
    assert carry_medido == pytest.approx(3 * carry_default, rel=1e-9)


def test_tf_horas_explicito_vence_a_medicao():
    """Quem declara, declarou -- a medicao e o conserto do ESQUECIMENTO, nao um veto."""
    df = df_sintetico([100.0] * 70)
    assert B._horas_por_barra(df, 4.0, "15m") == 4.0
    assert B._horas_por_barra(df, None, "15m") == pytest.approx(1.0)
    assert B._horas_por_barra(df.iloc[:1], None, "15m") == 0.25      # sem passo: cai no mapa


# ============================ calibracao [Q-7] ============================
def matriz_correlacionada(T=900, K=6, rho=0.95, seed=9, sd=10.0):
    """Painel com a forma do `matriz_is` real: K configs muito correlacionadas, T dias."""
    rng = np.random.default_rng(seed)
    F = rng.standard_normal(T)
    return {("c", k): (sd * (np.sqrt(rho) * F + np.sqrt(1 - rho) * rng.standard_normal(T))).tolist()
            for k in range(K)}


def test_banda_binomial_e_calculada_e_o_literal_antigo_estava_errado():
    """[Q-7] item 1. A banda era uma STRING no print. A rodada do [Q-1] imprimiu
    "taxa de rejeicao a 5% = 0.01 (banda binomial [0,02 ; 0,09])": o valor medido ja estava
    fora da banda que a propria linha anunciava, e nada no codigo comparou os dois. Aqui ela
    e conta -- e a conta mostra que o literal errava tambem o limite de cima."""
    b = V.banda_binomial(200, 0.05)
    assert (b["k_lo"], b["k_hi"]) == (4, 16)
    assert (b["taxa_lo"], b["taxa_hi"]) == (0.02, 0.08)      # o literal dizia 0,09
    assert V._binom_cdf(3, 200, 0.05) <= 0.025 < V._binom_cdf(4, 200, 0.05)
    assert V.banda_binomial(0, 0.05)["k_lo"] == 0            # borda: M=0 nao explode


def test_classificacao_da_banda_nos_tres_casos():
    """O criterio de aceite do card: os TRES casos, em codigo, mais as duas bordas."""
    assert V.classificar_calibracao(2, 200)["classe"] == "FORA DA BANDA (abaixo)"
    assert V.classificar_calibracao(4, 200)["classe"] == "CALIBRADO"      # borda inferior
    assert V.classificar_calibracao(10, 200)["classe"] == "CALIBRADO"
    assert V.classificar_calibracao(16, 200)["classe"] == "CALIBRADO"     # borda superior
    assert V.classificar_calibracao(30, 200)["classe"] == "FORA DA BANDA (acima)"
    # o IC exato da taxa medida e largo: M=200 nao separa alfa 0,001 de alfa 0,035, e essa
    # imprecisao faz parte do diagnostico -- e ela que impede o alfa medido de virar aritmetica
    lo, hi = V.classificar_calibracao(2, 200)["ic_taxa"]
    assert lo < 0.002 and 0.03 < hi < 0.05


def test_a_causa_da_sub_rejeicao_e_a_MARGINAL_nao_as_suspeitas_do_card():
    """[Q-7] item 3 -- a INVESTIGACAO, e ela desmente duas das tres suspeitas do card.

    O controle DIRETO gera paineis de um DGP conhecido e troca SO a forma da marginal. Tudo o
    mais fica igual: o mesmo `reality_check`, o mesmo `p = (1+#)/(B+1)`, o mesmo `block=5`, o
    mesmo M. Se a sub-rejeicao viesse do `+1` ou do `block`, a linha "normal" cairia junto --
    e ela nao cai: fica DENTRO da banda. A de cauda pesada cai uma ordem de grandeza.

    Quem derruba o tamanho e a marginal de P&L diario -- maioria dos dias zerada, truncada em
    `-valor` a esquerda, cauda longa a direita. O mecanismo ja estava escrito em `spa_hansen`
    [F15]: o RC toma o maximo de medias BRUTAS, e cauda pesada infla o quantil nulo.
    """
    m = matriz_correlacionada()
    normal = V.controle_nulo_direto(m, M=200, seed=101, dgp="normal")
    pesada = V.controle_nulo_direto(m, M=200, seed=101, dgp="pesada")
    banda = V.banda_binomial(200, 0.05)
    assert normal["classe"] == "CALIBRADO", normal["taxa"]
    assert pesada["classe"] == "FORA DA BANDA (abaixo)", pesada["taxa"]
    assert pesada["taxa"] < banda["taxa_lo"] <= normal["taxa"], (pesada["taxa"], normal["taxa"])
    assert pesada["taxa"] * 3 < normal["taxa"], (pesada["taxa"], normal["taxa"])


def test_a_estudentizacao_do_SPA_nao_conserta_e_registrar_isso_poupa_o_proximo_card():
    """A saida obvia seria "troque o RC pelo SPA, que e estudentizado". Medido: na mesma
    marginal de cauda pesada o SPA rejeita MENOS que o RC, porque o denominador dele tambem e
    inflado pela cauda."""
    m = matriz_correlacionada(T=600, K=6, seed=11)
    par = V._params_do_painel(m)
    rng = np.random.default_rng(31)
    rc, spa = [], []
    for _ in range(200):
        X = V._painel_nulo(rng, par, "pesada")
        painel = {k: X[k].tolist() for k in range(par["K"])}
        sd = int(rng.integers(1, 10 ** 9))
        rc.append(V.reality_check(painel, n_boot=200, block=5, seed=sd)["p_valor"])
        spa.append(V.spa_hansen(painel, n_boot=200, block=5, seed=sd)["p_valor"])
    t_rc = float((np.asarray(rc) <= 0.05).mean())
    t_spa = float((np.asarray(spa) <= 0.05).mean())
    assert t_spa <= t_rc, (t_spa, t_rc)
    assert t_rc < V.banda_binomial(200, 0.05)["taxa_lo"], t_rc


def test_controle_nulo_e_cego_para_a_propria_falha():
    """O degrau que muda como o 0,01 do dado real deve ser lido.

    Sobre um painel sorteado do DGP de cauda pesada, o controle DIRETO da 0,0025 e este aqui
    da ~0,04 -- perto do nominal. Os dois discordam por razao estrutural: no aninhado os dois
    niveis usam a MESMA distribuicao empirica, entao o erro do bootstrap entra dos dois lados
    e se cancela. Ele nao consegue ver a propria falha, e por isso o alfa efetivo que ele mede
    e uma estimativa OTIMISTA -- o piso do MDS que sai dela e um piso frouxo.
    """
    m = matriz_correlacionada(T=900, K=6, rho=0.95, seed=9)
    par = V._params_do_painel(m)
    X = V._painel_nulo(np.random.default_rng(3), par, "pesada")
    painel = {("c", k): X[k].tolist() for k in range(par["K"])}
    aninhado = V.controle_nulo(painel, M=300, seed=11)
    direto = V.controle_nulo_direto(painel, M=300, seed=11, dgp="pesada")
    assert direto["taxa"] < aninhado["taxa"], (direto["taxa"], aninhado["taxa"])
    assert direto["classe"] == "FORA DA BANDA (abaixo)"
    assert aninhado["classe"] == "CALIBRADO"          # cego: nao acusa o que o direto acusa


def test_cada_painel_nulo_e_um_sorteio_independente_do_painel_real():
    """Centrar por uma media que nao e a da distribuicao que gerou o painel deixa drift
    residual no nulo, e o Reality Check o detecta corretamente -- medido, a taxa foi a 0,225
    num painel gaussiano. O painel nulo e sorteado do dado e centrado pelo dado, uma vez so."""
    m = matriz_correlacionada(T=500, K=3, seed=17)
    cn = V.controle_nulo(m, M=200, seed=5)
    assert cn["classe"] == "CALIBRADO", cn["taxa"]
    import inspect
    assert "n_bases" not in inspect.signature(V.controle_nulo).parameters


def test_controle_nulo_direto_le_os_momentos_do_painel():
    par = V._params_do_painel({("a",): serie_ar1(500, 0.4, seed=11),
                               ("b",): serie_ar1(500, 0.4, seed=12)})
    assert par["K"] == 2 and par["T"] == 500
    assert 0.0 <= par["rho"] <= 1.0
    assert par["phi"] == pytest.approx(0.4, abs=0.15)
    cal = V.controle_nulo_direto({("a",): serie_ar1(400, 0.0, seed=13)}, M=20, seed=5)
    assert cal["dgp"]["T"] == 400 and cal["dgp"]["K"] == 1
    assert cal["dgp"]["forma"] == "normal"
    assert cal["alfa_efetivo"] == cal["taxa"]


def test_o_portao_de_calibracao_bloqueia_para_CIMA_por_MATERIALIDADE():
    """[Q-7] item 2, a decisao registrada e a assimetria dela.

    Super-rejeitar torna a condicao de EDGE facil demais -- ela le o Reality Check --, entao
    bloqueia. Mas o gatilho e MATERIALIDADE, nao significancia: o tamanho real do RC medido
    sobre 2.400 paineis normais e 0,0604, acima do nominal, entao uma banda de 95% centrada em
    0,05 acusaria 17+/200 com probabilidade 0,099. Portao que bloqueia uma rodada honesta a
    cada dez vira ruido, e portao que dispara por ruido e desligado por quem tem pressa.
    """
    base = _res_sintetico(mu=0.0, seed=21, n_dias=1000)
    assert base["bloco_b"]["mds"] < V.MDS_LIMITE                 # ha poder: o portao de MDS cala

    acima = dict(base)
    acima["calibracao"] = V.classificar_calibracao(60, 200)      # taxa 0,30
    v = V._veredito(acima)
    assert v["classe"] == "INCONCLUSIVO" and "descalibrado" in v["motivo"]

    quase = dict(base)
    quase["calibracao"] = V.classificar_calibracao(17, 200)      # FORA DA BANDA (acima)...
    assert quase["calibracao"]["classe"] == "FORA DA BANDA (acima)"
    assert quase["calibracao"]["ic_taxa"][0] < V.ALFA_TETO_PORTAO
    assert V._veredito(quase)["classe"] == base["veredito"]["classe"]   # ...e NAO bloqueia
    assert V.ALFA_TETO_PORTAO == 0.10


def test_mds_vira_PISO_quando_o_teste_sub_rejeita():
    """[Q-7] item 4. O MDS e calculado com alfa NOMINAL; com alfa efetivo menor o poder real e
    menor e o minimo detectavel e MAIOR. Publicar so o nominal seria publicar poder que o teste
    nao tem. Aqui, a aritmetica que o card pediu, com o `mds_sharpe` de verdade."""
    assert V.mds_sharpe(908, alfa=0.01) > V.mds_sharpe(908, alfa=0.05)
    assert V.mds_sharpe(908, alfa=0.05) == pytest.approx(1.576, abs=0.002)
    # o card estimou "~22%" pela formula da matriz; pelo `mds_sharpe` a razao e ~27,4%, e
    # 1,576 x 1,274 = 2,008 -- o OUTRO lado do MDS_LIMITE, nao "a folga cai para 4%"
    razao = V.mds_sharpe(908, alfa=0.01) / V.mds_sharpe(908, alfa=0.05)
    assert razao == pytest.approx(1.274, abs=0.005)
    assert V.mds_sharpe(908, alfa=0.01) > V.MDS_LIMITE


def test_o_portao_de_poder_le_o_PISO_mas_pela_ponta_menos_exigente_do_IC():
    """A outra metade da assimetria. Sub-rejeicao nao bloqueia por si; ela corrige o MDS, e o
    portao le o piso calculado com o alfa no TOPO do IC -- o piso menos exigente compativel com
    a imprecisao do diagnostico. Assim a guarda so dispara quando a largura do IC nao pode
    explicar o achado, e nunca por um M pequeno demais."""
    res = _res_sintetico(mu=0.0, seed=23, n_dias=1000)
    b = res["bloco_b"]
    T = b["T"]

    # 2 rejeicoes em 200: alfa 0,01, IC [0,0012 ; 0,0357]
    cal = V.classificar_calibracao(2, 200)
    forjado = dict(res)
    forjado["calibracao"] = cal
    forjado["bloco_b"] = dict(b)
    forjado["bloco_b"]["mds_piso"] = round(V.mds_sharpe(T, alfa=cal["taxa"]), 3)
    forjado["bloco_b"]["mds_piso_min"] = round(V.mds_sharpe(T, alfa=cal["ic_taxa"][1]), 3)
    assert forjado["bloco_b"]["mds_piso"] > forjado["bloco_b"]["mds_piso_min"]
    # com T grande o piso menos exigente nao passa do limite -> o veredito NAO vira
    assert forjado["bloco_b"]["mds_piso_min"] < V.MDS_LIMITE
    assert V._veredito(forjado)["classe"] == res["veredito"]["classe"]

    # ja um piso que nem no topo do IC cabe no limite bloqueia, e o motivo cita o PISO
    duro = dict(forjado)
    duro["bloco_b"] = dict(forjado["bloco_b"])
    duro["bloco_b"]["mds_piso_min"] = V.MDS_LIMITE + 0.01
    v = V._veredito(duro)
    assert v["classe"] == "INCONCLUSIVO" and "PISO" in v["motivo"]


def test_calibracao_entra_no_resultado_e_no_relatorio(capsys):
    res = _res_sintetico(mu=0.0, seed=31, n_dias=300)
    assert res["calibracao"]["M"] == V.M_CONTROLE_NULO
    assert "mds_piso" in res["bloco_b"] and "mds_piso_min" in res["bloco_b"]
    V.relatorio(res)
    out = capsys.readouterr().out
    assert "calibracao [Q-7]" in out
    assert "banda de aceitacao CALCULADA" in out
    assert res["calibracao"]["classe"] in out


def test_relatorio_do_controle_nulo_imprime_o_alfa_e_a_causa(capsys):
    res = _res_sintetico(mu=0.0, seed=41, n_dias=300)
    causa = [(f, V.controle_nulo_direto(res["matriz_is"], M=20, seed=7, dgp=f))
             for f in ("normal", "pesada")]
    V.relatorio_controle_nulo(res["calibracao"], causa)
    out = capsys.readouterr().out
    assert "banda CALCULADA" in out and "a CAUSA" in out
    assert "marginal   normal" in out and "marginal   pesada" in out
    assert "F15" in out


def test_m_calibracao_menor_alarga_a_banda_em_vez_de_desligar_a_guarda():
    """Nao ha bandeira para desligar a calibracao -- so como medir com menos paineis. E menos
    paineis alargam a banda, que e a consequencia certa: diagnostico impreciso reclama menos,
    nunca mais. (CLAUDE.md §2: a guarda so protege se nao houver como desliga-la.)"""
    assert V.banda_binomial(20, 0.05)["taxa_hi"] > V.banda_binomial(400, 0.05)["taxa_hi"]
    assert V.ic_clopper_pearson(1, 20)[1] > V.ic_clopper_pearson(20, 400)[1]
    import inspect
    assinatura = inspect.signature(V.walk_forward).parameters
    assert "m_calibracao" in assinatura
    assert not any(n.startswith("sem_") or n == "calibrar" for n in assinatura)


# ================= as politicas de saida A x B x C [P1-10] =================
# O veredito central do projeto mediu a politica A -- stop 3xATR ou flip de regime -- e o
# sistema ao vivo NUNCA operou A. Estas provas fixam, com trajetoria conhecida, o que cada
# politica fecha e quando. Rodam offline pelo `sinal_fn`.
def df_com_indicadores(closes, highs=None, lows=None, rsi=None, ema_r=None, ema_l=None,
                       atr=None, tf_ms=TF_MS):
    """`df_sintetico` mais as colunas que a politica B (gestor de saida) e o trailing em ATR
    consomem. Sem valor passado, os indicadores ficam neutros: nao disparam nada."""
    df = df_sintetico(closes, highs=highs, lows=lows, tf_ms=tf_ms)
    n = len(closes)
    df["rsi"] = list(rsi) if rsi is not None else [50.0] * n
    df["ema_r"] = list(ema_r) if ema_r is not None else list(closes)
    df["ema_l"] = list(ema_l) if ema_l is not None else list(closes)
    df["atr"] = list(atr) if atr is not None else [1.0] * n
    return df


def _um_trade(df, saida, **kw):
    tr = B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=sinal_em([60]),
                          saida=saida, **kw)
    assert len(tr) == 1, (saida, tr)
    return tr[0]


def test_politica_invalida_recusa_em_vez_de_cair_no_default():
    """Errar o nome da politica nao pode virar 'rodou a A e ninguem viu' -- num card cujo
    produto e a COMPARACAO entre as tres, isso e o pior modo de falha possivel."""
    with pytest.raises(ValueError, match="saida deve ser"):
        B.backtest_ativo("X/USDT", 0, 100, 10, df=df_com_indicadores([100.0] * 70),
                         sinal_fn=sinal_em([60]), saida="trailling")


def test_A_fecha_no_flip_de_regime_e_B_e_C_nao_herdam_esse_flip():
    """O flip de regime NAO existe no sistema vivo: nada em `simulador.atualizar()` nem em
    `autotrader.auto_executar()` fecha por inversao do scoring. Herda-lo em B e C faria as
    tres politicas compartilharem uma saida que so a A tem, e a comparacao mediria menos
    diferenca do que existe."""
    df = df_com_indicadores([100.0] * 70)

    def fn(_df, i):
        if i in (60, 64):
            return {"direcao": 1 if i == 60 else -1, "conviccao": 99.0, "adx": 40.0,
                    "n_fatores": 3, "stop_dist": 0.03, "tipo": "tendencia"}
        return None

    a = B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=fn, saida="regime")
    assert [t["motivo"] for t in a] == ["regime"]
    for pol in ("auto", "trailing"):
        assert B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=fn, saida=pol) == []


def test_C_trailing_sobe_o_stop_atras_do_preco_e_fecha_EM_LUCRO():
    """A trajetoria: sobe 6% e volta. Com A o stop fixo de 3% nunca e tocado e a posicao
    segue aberta; com C o stop subiu para 4% acima da entrada (pico 6% menos 2%) e a queda o
    encontra -- fechando com LUCRO, e com o motivo `trailing`, que e o mesmo nome que
    `simulador._fecha_stop` grava no banco vivo."""
    precos = [100.0] * 62 + [106.0] * 3 + [100.5] * 5
    highs = list(precos)
    lows = list(precos)
    lows[65] = 100.5                                    # a volta acontece no candle 65
    df = df_com_indicadores(precos, highs=highs, lows=lows)

    assert B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=sinal_em([60]),
                            saida="regime") == []       # A: stop fixo de 3% nao e tocado
    t = _um_trade(df, "trailing", trailing_unidade="preco", trailing_dist=0.02)
    assert t["motivo"] == "trailing"
    assert t["pnl"] > 0
    assert t["ts_saida"] == T0 + 65 * TF_MS + TF_MS


def test_C_so_arma_o_trailing_depois_do_lucro_passar_da_distancia():
    """Paridade com `simulador._marcar_uma`: o stop so comeca a subir depois de o preco passar
    de `entrada*(1+trailing_dist)`. Subida de 1% com trailing de 2% nao arma nada, e o stop
    continua sendo o de 3xATR da entrada -- ou seja, o trade fecha em PERDA, nao em lucro."""
    precos = [100.0] * 62 + [101.0] * 3 + [96.0] * 5
    lows = list(precos)
    lows[65] = 96.0
    df = df_com_indicadores(precos, lows=lows)
    t = _um_trade(df, "trailing", trailing_unidade="preco", trailing_dist=0.02)
    assert t["motivo"] == "stop"                        # nunca armou: e o stop de entrada
    assert t["pnl"] < 0


def test_C_o_stop_do_trailing_so_se_move_para_o_candle_SEGUINTE():
    """A ordem dentro do candle e decisao, nao detalhe. Subir o stop com o topo do candle e so
    entao perguntar se o fundo do MESMO candle o furou supoe que o topo veio antes -- o OHLC
    nao diz isso. Aqui topo e fundo estao no mesmo candle: o trailing NAO fecha nele.

    O efeito e conservador: C trava menos lucro do que o vivo, que faz poll a cada 15 s."""
    precos = [100.0] * 63 + [106.0] * 7
    highs = list(precos)
    lows = list(precos)
    highs[63] = 108.0                                   # topo e fundo no MESMO candle
    lows[63] = 100.0                                    # o fundo furaria o stop pos-trailing
    df = df_com_indicadores(precos, highs=highs, lows=lows)
    tr = B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=sinal_em([60]),
                          saida="trailing", trailing_unidade="preco", trailing_dist=0.02)
    assert tr == []                                     # nao fechou dentro do candle do pico
    # ...mas o stop ficou armado em 108*0,98 = 105,84, e o candle SEGUINTE o encontra
    lows2 = list(lows)
    lows2[64] = 100.0
    df2 = df_com_indicadores(precos, highs=highs, lows=lows2)
    t = _um_trade(df2, "trailing", trailing_unidade="preco", trailing_dist=0.02)
    assert t["motivo"] == "trailing" and t["pnl"] > 0
    assert t["ts_saida"] == T0 + 64 * TF_MS + TF_MS


def test_C_em_k_ATR_e_o_item_3_do_card_distancia_em_unidade_do_ATR():
    """`trailing_dist=2%` e fixo em espaco-preco: cego ao ATR (a entrada usa stop 3xATR e a
    saida ignora a volatilidade do ativo) e cego a alavancagem (2% de preco = 4% de ROE a 2x,
    40% a 20x). Com `trailing_k_atr=k` a distancia vira k*ATR/preco, medida NA ENTRADA.

    Aqui o ATR e 5 no candle da entrada: k=1 da 5% de distancia, mais larga que os 2% fixos --
    entao o mesmo repique que fechava a de 2% NAO fecha a de k*ATR."""
    precos = [100.0] * 62 + [106.0] * 3 + [102.5] * 5
    lows = list(precos)
    lows[65] = 102.5
    df = df_com_indicadores(precos, lows=lows, atr=[5.0] * len(precos))
    t2 = _um_trade(df, "trailing", trailing_unidade="preco", trailing_dist=0.02)
    assert t2["motivo"] == "trailing"                   # 2%: stop em 106*0,98 = 103,88 -> bate
    assert B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=sinal_em([60]),
                            saida="trailing", trailing_k_atr=1.0) == []   # 5%: 100,7 -> nao bate


# ============================ [P-1 / D-6] trailing em R: a pesquisa acompanha o vivo =====
def test_P1_o_DEFAULT_do_trailing_e_R_e_nao_mais_espaco_preco():
    """[P-1] O default mudou, e o teste existe para que ele nao volte por descuido.

    Ate 2026-08-29 o motor tinha politica de trailing PROPRIA (2% de preco). O `[N-13]` trocou
    a unidade no vivo (1R para armar, 1R de distancia, assinado pelo dono na `D-5`) e a `D-6`
    decidiu que a pesquisa acompanha. Um default e uma afirmacao sobre o que se mede por
    omissao -- e este arquivo inteiro roda por omissao.
    """
    assert B.TRAILING_UNIDADE == "R"
    assert (B.TRAILING_ARMA_R, B.TRAILING_DIST_R) == (1.0, 1.0)
    assert B.UNIDADES_TRAILING == ("R", "preco")
    with pytest.raises(ValueError, match="trailing_unidade deve ser"):
        B.backtest_ativo("X/USDT", 0, 100, 10, df=df_com_indicadores([100.0] * 70),
                         sinal_fn=sinal_em([60]), saida="trailing", trailing_unidade="atr")


def test_P1_em_R_o_gatilho_e_a_distancia_saem_do_stop_de_ABERTURA():
    """A resposta e conhecida por construcao, e e por isso que ela vale mais que dez asercoes
    sobre dado real.

    Entrada em ~100 com `stop_dist=2%` -> 1R = ~2,0 em preco. Com `arma_r=1` o trailing so
    arma quando o preco toca ~102,0; com `dist_r=1` o stop vai para `pico - 1R`.

      * pico 101,5 (menos de 1R): NAO arma. O stop segue em ~98,0 e a queda a 97 fecha por
        `stop`, com prejuizo;
      * pico 106,0 (3R): arma, stop = ~104,0. A volta a 104 fecha por `trailing`, com LUCRO --
        e 104 e um numero que so existe se a distancia tiver saido do 1R de abertura.

    Se a implementacao lesse o R do stop VIGENTE em vez do de abertura, a distancia encolheria
    a cada candle -- o [F-1] renascendo dentro do proprio conserto.
    """
    fn = sinal_em([60], stop_dist=0.02)                 # 1R ~ 2,00 em preco

    curto = [100.0] * 62 + [101.5] * 2 + [97.0] * 6     # pico 1,5 < 1R
    t = B.backtest_ativo("X/USDT", 0, 100, 10,
                         df=df_com_indicadores(curto, highs=list(curto), lows=list(curto)),
                         sinal_fn=fn, saida="trailing")[0]
    assert t["motivo"] == "stop" and t["pnl"] < 0

    longo = [100.0] * 62 + [106.0] * 3 + [104.5] * 5    # pico 6,0 = 3R -> stop em ~104,0
    lows = list(longo)
    lows[65] = 103.9
    df = df_com_indicadores(longo, highs=list(longo), lows=lows)
    t = B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=fn, saida="trailing")[0]
    assert t["motivo"] == "trailing" and t["pnl"] > 0
    # o MESMO df com 1R MAIOR (stop_dist=4% -> 1R~4,0): arma em 104 e poe o stop em ~102, que
    # a queda a 103,9 nao encontra -- a posicao segue aberta. Prova que gatilho e distancia
    # escalam com o R do trade, e nao com um numero fixo em preco.
    assert B.backtest_ativo("X/USDT", 0, 100, 10, df=df,
                            sinal_fn=sinal_em([60], stop_dist=0.04), saida="trailing") == []


def test_P1_o_gatilho_em_R_NAO_muda_de_significado_com_a_alavancagem_F19():
    """O F-19, que e a razao do card, dito como teste.

    Em espaco-preco o gatilho vira ROE quando multiplicado pela alavancagem: 2% de preco sao
    4% de ROE a 2x e 40% a 20x, entao a protecao desaparecia justamente onde a aposta era
    maior. Em R o gatilho e a distancia sao os MESMOS precos em qualquer alavancagem -- o que
    muda e so quanto dinheiro aquele mesmo movimento vale.

    A asercao e literal: a 2x e a 20x, a MESMA trajetoria fecha no MESMO candle e pelo MESMO
    motivo, e o P&L difere exatamente pelo fator de alavancagem (a taxa tambem escala com ela).
    """
    precos = [100.0] * 62 + [106.0] * 3 + [104.5] * 5
    lows = list(precos)
    lows[65] = 103.9
    df = df_com_indicadores(precos, highs=list(precos), lows=lows)
    fn = sinal_em([60], stop_dist=0.02)

    def roda(lev):
        return B.backtest_ativo("X/USDT", 0, 100, lev, df=df, sinal_fn=fn, saida="trailing")[0]

    a, b = roda(2), roda(20)
    assert a["motivo"] == b["motivo"] == "trailing"
    assert a["ts_saida"] == b["ts_saida"]               # o MESMO candle fecha os dois
    assert b["pnl"] == pytest.approx(a["pnl"] * 10, rel=1e-9)


def test_P1_em_1R_1R_o_stop_cai_no_zero_a_zero_no_instante_em_que_ARMA():
    """A consequencia da `D-5` que o dono assinou, e que so aparece quando arma_r == dist_r.

    Ao armar, `preco = entrada + 1R` e o stop vai para `preco - 1R = entrada`. Ou seja: o
    `1R/1R` E o `be_em_R=1` da pesquisa, chegando ao vivo pela outra porta. Aqui a trajetoria
    sobe pouco mais de 1R, arma, e desaba muito abaixo do stop de entrada: sob a politica de
    PRECO isso vai ao stop cheio, sob 1R/1R fecha perto do empate -- perdendo so a taxa do
    round-trip, que o zero-a-zero do trailing nao cobre.

    O `stop_dist=1%` e o que separa as duas politicas neste df: 1R vale 1,0 em preco, entao o
    gatilho em R e +1% e o gatilho de 2% ainda nao chegou. Com `stop_dist=2%` os dois gatilhos
    coincidem por aritmetica (1R = 2% da entrada) e o teste nao teria objeto -- e essa
    coincidencia e exatamente o motivo de o defeito ter passado despercebido tanto tempo: nos
    trades de stop MEDIO as duas unidades quase concordam, e so divergem nas caudas.
    """
    precos = [100.0] * 62 + [101.05] * 2 + [95.0] * 6   # 1R = 1,00: o pico mal passa de 1R
    df = df_com_indicadores(precos, highs=list(precos), lows=list(precos))
    fn = sinal_em([60], stop_dist=0.01)

    t = B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=fn, saida="trailing")[0]
    cheio = B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=fn, saida="trailing",
                             trailing_unidade="preco", trailing_dist=0.02)[0]
    assert t["motivo"] == "trailing"                    # armou: o stop subiu ate a entrada
    assert cheio["motivo"] == "stop"                    # em preco, +1,05% nao chega aos 2%
    # o que sobra de perda no caso 1R/1R e a taxa do round-trip (2 x 0,05% x valor x lev = 1,00)
    # e o slippage -- nao um R de prejuizo. O zero-a-zero do trailing e no PRECO de entrada, e
    # nao cobre a taxa, ao contrario do `be_em_R`, que cobre de proposito (e a diferenca entre
    # "empate" e "perda pequena com nome bonito").
    assert t["pnl"] > cheio["pnl"]
    assert abs(t["pnl"]) < 1.1                          # ~ a taxa, nao ~ 1R alavancado
    assert cheio["pnl"] < -10                           # 1R a 10x = ~10% da margem, + taxa


def test_P1_k_ATR_FORCA_espaco_preco_e_nao_convive_em_silencio_com_o_R():
    """Duas unidades para a mesma geometria e a doenca que o [N-13] veio curar. `k*ATR/preco`
    E espaco-preco por construcao, entao pedir `trailing_k_atr` com o default `"R"` nao pode
    deixar uma das duas ser ignorada sem aviso.

    A prova e comportamental e nao de flag: com ATR=5 e k=1 a distancia e 5% (~5,00 em preco),
    enquanto 1R aqui vale ~3,00. O pico de 106 arma nos dois; o stop fica em ~101,0 sob k*ATR e
    em ~103,0 sob R. A queda a 102,5 encontra SO o de R -- entao se o `k` estivesse sendo
    ignorado, este trade teria fechado.
    """
    precos = [100.0] * 62 + [106.0] * 3 + [102.5] * 5
    lows = list(precos)
    lows[65] = 102.5
    df = df_com_indicadores(precos, highs=list(precos), lows=lows, atr=[5.0] * len(precos))
    fn = sinal_em([60], stop_dist=0.03)                 # 1R ~ 3,00

    em_r = B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=fn, saida="trailing")
    assert [t["motivo"] for t in em_r] == ["trailing"]  # stop em ~103,0 -> a queda a 102,5 bate
    # o mesmo df com k=1 (5%): stop em ~101,0, a queda a 102,5 NAO bate. E `trailing_k_atr`
    # sozinho basta -- nao e preciso lembrar de passar `trailing_unidade`.
    assert B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=fn, saida="trailing",
                            trailing_k_atr=1.0) == []


def test_P1_as_politicas_do_M4_continuam_reproduzindo_a_unidade_que_o_nome_promete():
    """O risco especifico deste card: mudar um default e reescrever, em silencio, um numero ja
    publicado. `POLITICAS_M4` e a tupla que o `VEREDITO-M4.md` mediu -- se a linha chamada
    "C trailing 2% fixo" passasse a rodar em R, o veredito deixaria de ser reproduzivel por ela
    e ninguem teria como notar pelo rotulo.

    Entao as linhas de PRECO tem de trazer a unidade pinada, e a linha nova tem de ser a do
    vivo. Este teste le a tupla, nao a documentacao.
    """
    por_nome = dict(V.POLITICAS_M4)
    assert por_nome["C trailing 2% fixo"]["trailing_unidade"] == "preco"
    assert por_nome["C trailing 2% fixo"]["trailing_dist"] == 0.02
    assert por_nome["C trailing 1R/1R (vivo)"]["trailing_unidade"] == "R"
    assert (por_nome["C trailing 1R/1R (vivo)"]["trailing_arma_r"],
            por_nome["C trailing 1R/1R (vivo)"]["trailing_dist_r"]) == (1.0, 1.0)
    # o k*ATR nao precisa pinar: ele forca a unidade sozinho (teste acima)
    assert "trailing_unidade" not in por_nome["C trailing 3xATR"]
    # e as cinco politicas continuam distintas duas a duas -- se colapsarem, a comparacao do
    # marco perde o objeto
    assert len({str(sorted(kw.items())) for _, kw in V.POLITICAS_M4}) == len(V.POLITICAS_M4)


def test_Q9_sd_min_recusa_o_sinal_de_stop_curto_e_o_default_nao_recusa_nada():
    """[Q-9] O piso de distancia do stop e portao de CUSTO, e a conta que o justifica nao
    depende de amostra: `taxa/risco = 2*taxa_lado/sd`. Com `taxa=0,0005`, um stop a 0,19% da
    entrada (medido em producao em 2026-08-24, TRX 5m) poe 53% do risco-ate-o-stop na
    corretora antes de o mercado se mexer.

    O default `0.0` tem de deixar TUDO passar: e o que garante que nenhuma rodada anterior --
    inclusive os numeros ja publicados no `VEREDITO-M4.md` -- mude de resultado por causa
    deste parametro. Um piso que agisse por default reescreveria o veredito em silencio.

    E o portao mede a distancia do SINAL, nao o desfecho: por isso o teste compara o mesmo df,
    o mesmo sinal e a mesma politica, mudando so `sd_min` -- o unico jeito de provar que quem
    recusou foi o piso."""
    precos = [100.0] * 62 + [106.0] * 3 + [100.5] * 5
    lows = list(precos)
    lows[65] = 100.5
    df = df_com_indicadores(precos, lows=lows)
    fn = sinal_em([60], stop_dist=0.019)                # 1,9% -- abaixo de 2%, acima de 1%

    def roda(**kw):
        return B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=fn,
                                saida="trailing", trailing_unidade="preco",
                                trailing_dist=0.02, **kw)

    assert len(roda()) == 1                             # default: portao desligado
    assert len(roda(sd_min=0.0)) == 1                   # explicito e igual ao default
    assert len(roda(sd_min=0.01)) == 1                  # 1,9% >= 1% -> passa
    assert roda(sd_min=0.02) == []                      # 1,9% < 2% -> recusado no portao
    assert roda(sd_min=0.04) == []


def test_Q10_lev_por_conviccao_e_transcricao_fiel_do_autotrader():
    """[Q-10] `pesquisa/` nao pode importar `autotrader` (ele arrasta `db` e `simulador`, e a
    fronteira do `CLAUDE.md` 0 declara so `scoring` e `indicadores` como compartilhados). O
    preco dessa fronteira e uma copia da formula de alavancagem -- e este teste E o preco da
    copia: ele importa OS DOIS lados e quebra no dia em que divergirem.

    Sem ele, alguem ajusta `autotrader._alavancagem` (ou o cap do [P1-11]) e a pesquisa segue
    medindo a alavancagem de ontem, em silencio, produzindo numero que nao descreve a producao.
    Varre a faixa inteira de conviccao E o regime em que o cap geometrico morde."""
    import autotrader

    cfg = {"auto_lev_modo": "conviccao", "auto_lev_min": 2, "auto_lev_max": 20,
           "auto_conviccao_min": 60}
    for conv in (0, 55, 60, 61, 70, 80, 99, 100, 120):
        for sd in (0.0, 0.005, 0.02, 0.05, 0.12, 0.4):
            esperado = autotrader._alavancagem(cfg, conv, stop_dist=sd, ativo="X/USDT")
            obtido = B._lev_conviccao(conv, 2.0, 20.0, 60.0, sd)
            assert obtido == esperado, f"conv={conv} sd={sd}: {obtido} != {esperado}"


def test_Q11_zero_a_zero_arma_em_R_salva_o_trade_e_o_default_nao_arma_nada():
    """[Q-11] A medicao de MFE de 2026-08-24 achou 19 dos 20 trades que foram de lucro a
    prejuizo SEM o trailing jamais ter armado: ele so arma em `+trailing_dist` de PRECO, e
    abaixo disso a protecao e zero. Em ROE isso escala com a alavancagem -- 2% de preco sao 40%
    de ROE a 20x.

    O cenario TEM de ser o da zona cega, senao nao prova nada: risco (1%) MENOR que a distancia
    do trailing (2%). O preco sobe 1,5% -- passa de 1R de ganho, mas nao chega nos 2% que armam
    o trailing -- e depois desaba ate abaixo do stop de entrada. E exatamente a geometria dos
    #38/#39/#40 de producao, que ficaram a menos de meio ponto percentual de ganhar protecao.

    Com `be_em_R=1` a guarda ja moveu o stop para o zero-a-zero e o trade fecha em EMPATE; sem
    ela, vai ao stop cheio. Mesmo df, mesmo sinal, mesma politica -- o unico fator e a guarda.

    O default `None` nao pode armar nada: e o que garante que as rodadas ja publicadas nao
    mudem de numero.

    [P-1] `trailing_unidade="preco"` esta PINADO aqui, e a razao e o achado: sob o default novo
    (`"R"`, 1R/1R) este teste nao teria objeto. O trailing em 1R/1R poe o stop no preco de
    entrada no instante em que arma, isto e, ELE JA FAZ o zero-a-zero -- `sem` fecharia por
    `trailing` e nao por `stop`, e a comparacao com `be_em_R=1` mediria a guarda contra uma
    politica que ja a implementa. O [Q-11] mediu `be_em_R` CONTRA o trailing de 2%, e e essa a
    pergunta que este teste guarda."""
    precos = [100.0] * 62 + [101.5] * 2 + [98.0] * 6
    highs, lows = list(precos), list(precos)
    lows[64] = 98.0
    df = df_com_indicadores(precos, highs=highs, lows=lows)
    fn = sinal_em([60], stop_dist=0.01)                 # risco = 1% -- METADE do trailing

    def roda(**kw):
        return B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=fn,
                                saida="trailing", trailing_unidade="preco",
                                trailing_dist=0.02, **kw)

    sem = roda()[0]
    assert sem["motivo"] == "stop" and sem["pnl"] < 0    # sem guarda: stop cheio

    com = roda(be_em_R=1.0)[0]
    assert com["motivo"] == "zero-a-zero"               # motivo PROPRIO, nao 'trailing'
    assert com["pnl"] > sem["pnl"]
    assert abs(com["pnl"]) < abs(sem["pnl"]) / 5        # empate, nao lucro nem perda cheia

    # gatilho alto demais para a excursao (2R de ganho contra 5R pedidos): nao arma
    assert roda(be_em_R=5.0)[0]["motivo"] == "stop"


def test_B_fecha_em_reversao_COM_lucro_e_nao_fecha_sem_lucro():
    """Paridade com `autotrader.auto_executar` passo 1: fecha quando o gestor de saida devolve
    nivel 'forte' ou 'lucro', que e reversao COM ROE acima de 1%. Sem lucro o nivel vira
    'risco' e o bot ao vivo NAO fecha -- so avisa."""
    n = 70
    rsi = [50.0] * n
    rsi[63], rsi[64] = 70.0, 65.0                       # RSI revertendo do topo no candle 64

    com_lucro = [100.0] * 62 + [101.0] * 8              # +1% de preco = +10% de ROE a 10x
    t = _um_trade(df_com_indicadores(com_lucro, rsi=rsi), "auto")
    assert t["motivo"] == "auto-saida" and t["pnl"] > 0
    assert t["ts_saida"] == T0 + 64 * TF_MS + TF_MS

    sem_lucro = [100.0] * 62 + [99.9] * 8               # ROE negativo: nivel 'risco', nao fecha
    assert B.backtest_ativo("X/USDT", 0, 100, 10, df=df_com_indicadores(sem_lucro, rsi=rsi),
                            sinal_fn=sinal_em([60]), saida="auto") == []


def test_B_reconhece_os_tres_gatilhos_do_gestor_de_saida_ao_vivo():
    """Os mesmos tres de `signal_engine.py:133-146`, um a um. O quarto -- fluxo do book -- nao
    existe em historico OHLCV; ele so ACRESCENTA motivos, entao B aqui fecha MENOS que a viva
    e fica mais perto de A do que a de verdade. O vies e contra a diferenca entre politicas,
    que e contra o proprio achado deste card."""
    n = 70
    base = [100.0] * 62 + [101.0] * 2 + [100.9] * 6      # +0,9% no fim = ROE ~ +8% a 10x
    neutro = df_com_indicadores(base)
    assert B.backtest_ativo("X/USDT", 0, 100, 10, df=neutro, sinal_fn=sinal_em([60]),
                            saida="auto") == []          # nenhum gatilho: nao fecha

    rsi = [50.0] * n
    rsi[63], rsi[64] = 70.0, 65.0
    assert _um_trade(df_com_indicadores(base, rsi=rsi), "auto")["motivo"] == "auto-saida"

    ema_r = list(base)
    ema_r[64] = 100.95                                   # close cruza a EMA20 para BAIXO
    assert _um_trade(df_com_indicadores(base, ema_r=ema_r), "auto")["motivo"] == "auto-saida"

    ema_l = list(base)
    ema_l[64] = 110.0                                    # ema_r < ema_l: tendencia virou
    assert _um_trade(df_com_indicadores(base, ema_l=ema_l), "auto")["motivo"] == "auto-saida"


def test_B_no_warmup_do_indicador_nao_fecha_igual_ao_vivo():
    """`avaliar_saida` devolve None quando RSI/EMA sao NaN, e o auto-trader nao fecha nada.
    Aqui o mesmo: NaN nao pode virar 'sem sinal de reversao' por acidente nem gatilho por
    comparacao com NaN."""
    n = 70
    base = [100.0] * 62 + [101.0] * 8
    rsi = [float("nan")] * n
    assert B.backtest_ativo("X/USDT", 0, 100, 10, df=df_com_indicadores(base, rsi=rsi),
                            sinal_fn=sinal_em([60]), saida="auto") == []


def test_as_tres_politicas_dao_saidas_DIFERENTES_na_mesma_trajetoria():
    """O que a comparacao A x B x C precisa que seja verdade para significar alguma coisa: na
    MESMA trajetoria e com o MESMO sinal de entrada, as tres fecham em candles diferentes, por
    motivos diferentes e com P&L diferente."""
    n = 74
    precos = [100.0] * 62 + [106.0] * 3 + [101.0] * 9
    lows = list(precos)
    lows[65] = 101.0
    rsi = [50.0] * n
    rsi[63], rsi[64] = 70.0, 65.0                       # reversao do topo no 64 -> B fecha ali

    def fn(_df, i):
        if i in (60, 68):
            return {"direcao": 1 if i == 60 else -1, "conviccao": 99.0, "adx": 40.0,
                    "n_fatores": 3, "stop_dist": 0.03, "tipo": "tendencia"}
        return None

    df = df_com_indicadores(precos, lows=lows, rsi=rsi)
    saidas = {}
    for pol in B.POLITICAS:
        tr = B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=fn, saida=pol)
        assert len(tr) == 1, (pol, tr)
        saidas[pol] = (tr[0]["motivo"], tr[0]["ts_saida"], round(tr[0]["pnl"], 4))
    assert saidas["auto"][1] < saidas["trailing"][1] < saidas["regime"][1]
    assert len({m for m, _, _ in saidas.values()}) == 3
    assert len({p for _, _, p in saidas.values()}) == 3


def test_o_ROE_da_politica_B_e_a_conta_do_simulador_inclusive_o_teto_na_margem():
    """`_roe` tem de ser a MESMA conta de `simulador._pnl` -- alavancada, com as duas pernas de
    taxa sobre o nocional de entrada e a perda travada na margem. Se divergisse, B fecharia em
    ROE que o vivo nao reconheceria."""
    pos = {"d": 1, "e": 100.0}
    assert B._roe(pos, 101.0, 100, 10, 0.0) == pytest.approx(10.0)
    assert B._roe(pos, 101.0, 100, 10, 0.0005) == pytest.approx(10.0 - 1.0)
    assert B._roe(pos, 50.0, 100, 10, 0.0) == pytest.approx(-100.0)      # teto na margem
    assert B._roe({"d": -1, "e": 100.0}, 99.0, 100, 10, 0.0) == pytest.approx(10.0)


def test_a_politica_nao_muda_a_paridade_de_entrada():
    """Os portoes de entrada sao os mesmos nas tres: conviccao, ADX e n_fatores. A politica
    escolhe COMO se sai, nunca QUANDO se entra -- se mudasse, a comparacao teria dois fatores
    e nenhum deles ficaria isolado."""
    df = df_com_indicadores([100.0] * 70)
    fraco = lambda _df, i: (sinal_em([60], adx=10.0)(_df, i))
    for pol in B.POLITICAS:
        assert B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=fraco,
                                saida=pol, adx_min=25) == []


# ============================ [N-6] golden file ============================
def test_golden_reproduz_a_saida_congelada_bit_a_bit():
    """[N-6 / F2] O teste que a `REVISAO-ITEM1.md` §E chamou de "o mais importante da lista e
    o unico ausente".

    Todo o resto deste arquivo prova PECAS: o bootstrap de bloco, o MDS, a purga, o FDR. Uma
    regua pode ter todas as pecas certas e mesmo assim mudar o veredito porque a ordem de
    duas delas trocou, ou porque um `round()` virou outro. Este e o unico teste que roda a
    regua PONTA A PONTA sobre uma entrada congelada e exige o mesmo numero de volta.

    Se ele quebrar, a pergunta NAO e "como faco ele passar" -- e "que numero mudou, e eu
    queria que mudasse?". Regravar (`python -m pesquisa.validacao golden --gravar`) e ato
    deliberado, e o commit que regrava tem de dizer por que.
    """
    ok, difs = V.conferir_golden()
    assert ok, "a regua mudou o numero congelado:\n  " + "\n  ".join(difs)


def test_golden_congela_NUMERO_e_nao_a_frase_do_veredito():
    """A versao-sintoma deste item seria gravar o texto do veredito e chamar de teste.

    "SEM_EVIDENCIA" continua saindo igual mesmo que o Sharpe anualizado va de -1,1 para +1,4:
    a classe do veredito e uma de tres strings, e tres strings nao detectam regressao. O que
    o golden guarda tem de ser a serie numerica -- e e isso que este teste afirma, para que
    ninguem "simplifique" o snapshot depois.
    """
    snap = json.load(open(V.GOLDEN_SAIDA, encoding="utf-8"))["snapshot"]
    assert len(snap["serie_oos"]) > 500                      # a serie diaria OOS inteira
    assert snap["bloco_b"]["T"] == len(snap["serie_oos"])
    for chave in ("reality_check", "spa", "dsr_melhor_is", "p_melhor_sozinha"):
        assert chave in snap["bloco_a"], chave
    for chave in ("ic_bloco", "ic_iid", "psr", "sharpe_anualizado",
                  "ic_sharpe_anualizado", "mds", "acf", "concentracao"):
        assert chave in snap["bloco_b"], chave
    assert set(snap["digest"]) == {"oos", "por_cfg", "matriz_is", "serie_naive"}
    # e a PROSA fica de fora, de proposito: golden que quebra por virgula e golden regravado
    # sem ler.
    assert "veredito_motivo" not in snap and "motivo" not in snap.get("veredito_numeros", {})


def test_golden_exercita_o_caminho_inteiro_e_nao_um_atalho():
    """Golden de painel curto congelaria o portao de poder, nao o teste de edge.

    O painel foi construido para que TODOS os portoes sejam atravessados e o veredito seja de
    fato EMITIDO: MDS abaixo do limite (ha poder), controle nulo calibrado (o portao do [Q-7]
    nao bloqueia), purga ATIVA (ha `ts_saida`), e mais de uma config escolhida ao longo dos
    folds (a selecao walk-forward esta mesmo selecionando). Se algum desses deixar de valer,
    o golden passa a congelar menos regua do que aparenta.
    """
    snap = json.load(open(V.GOLDEN_SAIDA, encoding="utf-8"))["snapshot"]
    assert snap["veredito_classe"] == "SEM_EVIDENCIA"        # veredito EMITIDO, nao INCONCLUSIVO
    assert snap["bloco_b"]["mds"] <= V.MDS_LIMITE
    assert snap["bloco_b"]["T_efetivo"] >= V.T_EFETIVO_MINIMO
    assert snap["calibracao"]["classe"] == "CALIBRADO"
    assert snap["purga_ativa"] is True
    escolhidas = {tuple(f[1]) for f in snap["por_fold"]}
    assert len(escolhidas) > 1, "os folds escolheram sempre a mesma config"


def test_golden_PEGA_uma_mudanca_de_numero(monkeypatch):
    """Golden que passa nao prova nada; golden que REPROVA uma mutacao prova.

    A mutacao aqui e a seed do `PADRAO` -- ela nao muda a estrategia nem os dados, so o
    sorteio de todos os bootstraps. Um golden que so olhasse a classe do veredito passaria
    (continua `SEM_EVIDENCIA`); este tem de reprovar, porque os p-valores mudam.

    Foi escolhida uma mutacao que comprovadamente move o numero: numa auditoria anterior uma
    mutacao "obvia" nao quebrou nada porque uma guarda acima a tornava equivalente.
    """
    monkeypatch.setitem(V.PADRAO, "seed", V.PADRAO["seed"] + 1)
    ok, difs = V.conferir_golden()
    assert not ok, "o golden NAO pegou uma troca de seed -- ele nao esta medindo nada"
    caminhos = " ".join(difs)
    assert "reality_check" in caminhos or "calibracao" in caminhos or "ic_bloco" in caminhos


def test_golden_PEGA_uma_mudanca_de_constante_do_PADRAO(monkeypatch):
    """A segunda mutacao, num eixo diferente: `block`, o comprimento do bloco do bootstrap.

    Seed troca o sorteio; `block` troca a ESTATISTICA (quanto de autocorrelacao o IC
    preserva). Se o golden so pegasse a seed, ele estaria travando o gerador de numeros
    aleatorios e nao a regua.
    """
    monkeypatch.setitem(V.PADRAO, "block", 20)
    ok, difs = V.conferir_golden()
    assert not ok, "o golden NAO pegou block=5 -> 20"
    assert any("ic_bloco" in d or "block" in d for d in difs), difs


def test_golden_le_a_entrada_do_disco_e_nao_regera_por_seed(tmp_path):
    """A entrada e congelada em ARQUIVO de proposito.

    Um painel regerado por `default_rng(seed)` faria o golden depender do fluxo de numeros do
    numpy continuar identico para sempre -- e ai o teste passaria a medir o numpy junto com a
    regua. Prova: mexer no arquivo muda o resultado, ou seja, e ele que manda.
    """
    por_cfg, meta = V.carregar_golden_entrada()
    assert meta["n_trials"] == V.GOLDEN_N_TRIALS and len(por_cfg) == len(V.GOLDEN_CFGS)
    d = json.load(open(V.GOLDEN_ENTRADA, encoding="utf-8"))
    d["painel"][0]["trades"][0]["pnl"] += 1.0                # um centavo em um trade
    alt = tmp_path / "entrada.json"
    alt.write_text(json.dumps(d), encoding="utf-8")
    ok, _ = V.conferir_golden(caminho_entrada=str(alt))
    assert not ok, "trocar a entrada nao mudou o resultado -- o golden nao a esta lendo"


# ============================ [N-5] benchmark no Reality Check ============================
def _matriz_drift(mu_bench, mu_extra, T=500, seed=0, k=3):
    """Benchmark com drift `mu_bench` e K configs que sao o benchmark + `mu_extra` + ruido.

    `mu_extra=0` e a estrategia que NAO tem alfa nenhum: ela e o benchmark com ruido em cima.
    Contra ZERO ela parece otima; contra o proprio benchmark, nao e nada. E a demonstracao
    literal do que a `REVISAO-ITEM1.md` §A.1 chamou de "estava comprado num bull".
    """
    rng = np.random.default_rng(seed)
    bench = rng.normal(mu_bench, 3.0, size=T)
    matriz = {(50 + i, 22): (bench + rng.normal(mu_extra, 1.0, size=T)).tolist()
              for i in range(k)}
    return matriz, bench.tolist()


def test_benchmark_none_reproduz_o_numero_de_hoje_bit_a_bit():
    """[N-5] O default nao pode mexer em nada. `None` NAO subtrai um vetor de zeros -- ele nao
    subtrai coisa nenhuma --, e a prova de que isso bastou e o golden do [N-6], que continuou
    verde depois deste card. Aqui fica a versao unitaria da mesma afirmacao.
    """
    matriz, _ = _matriz_drift(0.0, 0.0, seed=1)
    assert V.reality_check(matriz) == V.reality_check(matriz, benchmark=None)


def test_benchmark_de_zeros_e_identico_a_benchmark_none():
    """Subtrair zero e a identidade -- se nao fosse, a compatibilidade seria acidental."""
    matriz, _ = _matriz_drift(0.0, 0.0, seed=2)
    T = len(next(iter(matriz.values())))
    assert V.reality_check(matriz, benchmark=[0.0] * T) == V.reality_check(matriz)


def test_estrategia_IDENTICA_ao_benchmark_da_diferenca_nula_e_p_maximo():
    """Caso construido com resposta CONHECIDA: se a estrategia E o benchmark, `f_k,t` e zero
    em todo t. Entao V = 0, V*_b = 0, e sob a regra `p = (1+#{>=})/(B+1)` com empate em toda
    replica o p-valor tem de ser exatamente 1,0 -- nenhuma evidencia de superar a referencia.
    """
    _, bench = _matriz_drift(1.0, 0.0, seed=3)
    matriz = {(50, 22): list(bench), (55, 22): list(bench)}
    rc = V.reality_check(matriz, benchmark=bench)
    assert rc["V"] == 0.0
    assert rc["p_valor"] == 1.0


def test_o_benchmark_e_o_que_separa_ALFA_de_BETA():
    """O item bloqueante da V2, num teste so.

    A mesma familia de configs, o mesmo dado: contra ZERO ela tem "edge" com folga; contra o
    benchmark de que ela e uma copia ruidosa, nao tem nada. Se o p-valor nao mudasse, o
    parametro seria decorativo.
    """
    matriz, bench = _matriz_drift(mu_bench=1.0, mu_extra=0.0, seed=4)
    contra_zero = V.reality_check(matriz)["p_valor"]
    contra_bench = V.reality_check(matriz, benchmark=bench)["p_valor"]
    assert contra_zero <= 0.05, contra_zero          # "ganhou do zero"
    assert contra_bench > 0.20, contra_bench         # "nao ganhou do benchmark"


def test_alfa_de_verdade_sobrevive_ao_benchmark():
    """O espelho do teste acima: quem tem alfa REAL continua passando depois de descontado o
    beta. Sem este par, o teste anterior seria compativel com um benchmark que simplesmente
    mata tudo."""
    matriz, bench = _matriz_drift(mu_bench=1.0, mu_extra=0.6, seed=5)
    assert V.reality_check(matriz, benchmark=bench)["p_valor"] <= 0.05


def test_benchmark_de_tamanho_errado_e_erro_e_nao_corte_silencioso():
    """Alinhar por corte seria comparar dias diferentes e nao avisar."""
    matriz, bench = _matriz_drift(0.0, 0.0, T=300, seed=6)
    with pytest.raises(ValueError, match="benchmark"):
        V.reality_check(matriz, benchmark=bench[:200])


# ============================ [N-5] exposicao liquida ============================
def test_exposicao_liquida_e_ponderada_por_TEMPO_e_nao_por_contagem():
    """Caso com resposta conhecida: 3 dias comprado + 1 dia vendido -> (3-1)/4 = +0,5.

    Contando CABECAS o resultado seria 0,0 (um long e um short), que e a resposta errada e a
    mais confortavel -- "sou neutro". A ponderacao por tempo e o que impede isso.
    """
    D = V.DIA_MS
    trades = [{"ts": 0, "ts_saida": 3 * D, "direcao": 1, "pnl": 0.0},
              {"ts": 3 * D, "ts_saida": 4 * D, "direcao": -1, "pnl": 0.0}]
    assert V.exposicao_liquida(trades)["liquida"] == 0.5


def test_exposicao_liquida_nos_extremos():
    """+1 = comprado o tempo todo; -1 = vendido o tempo todo; 0 = simetrica no tempo."""
    D = V.DIA_MS
    so_long = [{"ts": i * D, "ts_saida": (i + 1) * D, "direcao": 1} for i in range(10)]
    so_short = [{**t, "direcao": -1} for t in so_long]
    assert V.exposicao_liquida(so_long)["liquida"] == 1.0
    assert V.exposicao_liquida(so_short)["liquida"] == -1.0
    assert V.exposicao_liquida(so_long[:5] + so_short[5:])["liquida"] == 0.0


def test_exposicao_liquida_aceita_o_apelido_d_do_motor():
    """`backtest_plataforma` chama o lado de `d` internamente; `scoring` chama de `direcao`."""
    D = V.DIA_MS
    assert V.exposicao_liquida([{"ts": 0, "ts_saida": D, "d": -1}])["liquida"] == -1.0


def test_sem_direcao_a_exposicao_e_None_COM_MOTIVO_e_nunca_zero():
    """Zero significa "direcionalmente neutra", que e uma afirmacao FORTE.

    Emiti-la por falta de campo seria inventar a resposta mais conveniente que existe -- e
    justamente a que faria o benchmark = 0 parecer justificado. O motivo tem de nomear o campo
    que falta, senao quem le nao sabe o que consertar.
    """
    D = V.DIA_MS
    ex = V.exposicao_liquida([{"ts": 0, "ts_saida": D, "pnl": 1.0}])
    assert ex["liquida"] is None
    assert "direcao" in ex["motivo"]
    assert ex["cobertura"] is not None          # o BRUTO continua saindo: so depende do tempo


def test_sem_ts_saida_nao_ha_ponderacao_por_tempo():
    ex = V.exposicao_liquida([{"ts": 0, "pnl": 1.0, "direcao": 1}])
    assert ex["liquida"] is None and "ts_saida" in ex["motivo"]


def _res_com_direcao(n_dias=900, seed=21, cfgs=((50, 22), (55, 22))):
    """Um walk-forward cujos trades trazem `direcao` -- 70% long, para dar exposicao != 0."""
    D = V.DIA_MS
    por_cfg = {}
    for k, cfg in enumerate(cfgs):
        rng = np.random.default_rng(seed + k)
        tr = []
        for i in range(n_dias):
            d = 1 if rng.random() < 0.7 else -1
            ts = int(T0 + i * D)
            tr.append({"ts": ts, "ts_saida": ts + D, "direcao": d,
                       "pnl": float(rng.normal(0.0, 10.0))})
        por_cfg[cfg] = tr
    return V.walk_forward(gerador_constante(por_cfg), list(cfgs), n_trials=100,
                          rotulo="com direcao")


def test_relatorio_imprime_a_exposicao_liquida_COM_NUMERO(capsys):
    """[N-5] O criterio de aceite: a linha existe e traz numero, nao promessa."""
    res = _res_com_direcao()
    V.relatorio(res)
    saida = capsys.readouterr().out
    assert "exposicao LIQUIDA ponderada por tempo em posicao" in saida
    assert "NAO COMPUTAVEL" not in saida
    assert "tempo em mercado" in saida
    esperado = V.exposicao_liquida(res["oos"], res["grade_oos"])["liquida"]
    assert esperado is not None and abs(esperado) > 0.2          # long-biased, como construido
    assert f"{esperado:+.4f}" in saida


def test_relatorio_declara_quando_a_exposicao_NAO_e_computavel(capsys):
    """A rodada REAL cai neste ramo, e ele tem de falar alto.

    O gerador de hoje grava `ts_saida` mas NAO grava `direcao` -- entao o relatorio de
    producao imprime NAO COMPUTAVEL, nomeia o arquivo que precisa mudar, e carrega o portao
    junto: sem exposicao liquida, veredito POSITIVO nao se emite. Omitir a linha, ou imprimir
    0,0 e seguir a vida, seria a versao-sintoma deste item -- e a mais perigosa, porque 0,0 e
    exatamente o numero que faria o `benchmark = 0` do Reality Check parecer justificado.
    """
    res = _res_com_direcao()
    for t in res["oos"]:                              # a forma exata do trade de hoje
        t.pop("direcao")
    V.relatorio(res)
    saida = capsys.readouterr().out
    assert "exposicao LIQUIDA ponderada por tempo em posicao: NAO COMPUTAVEL" in saida
    assert "veredito POSITIVO nao se emite" in saida
    assert "backtest_plataforma" in saida
    assert "tempo em mercado" in saida                # o BRUTO continua saindo, com numero


def test_relatorio_tambem_declara_quando_falta_ts_saida(capsys):
    """O outro ramo: sem `ts_saida` nao ha nem duracao, entao nem o bruto sai. Duas faltas
    diferentes, dois motivos diferentes -- um motivo generico mandaria consertar o campo
    errado."""
    V.relatorio(_res_sintetico(mu=0.0, seed=9))
    saida = capsys.readouterr().out
    assert "exposicao LIQUIDA ponderada por tempo em posicao: NAO COMPUTAVEL" in saida
    assert "ts_saida" in saida
    assert "tempo em mercado" not in saida


def test_a_regua_real_COMPUTA_exposicao_porque_o_motor_grava_a_direcao():
    """[P-4] O xfail estrito do `[N-5]` PROMOVIDO -- e a promocao e o ponto.

    Ate aqui este teste era `xfail(strict=True)`, que nesta casa e card em aberto e nao teste
    quebrado (`CLAUDE.md` §6): `backtest_plataforma` gravava conv/pnl/motivo/ts/ts_saida e
    jogava fora o lado da posicao, entao a exposicao liquida da rodada REAL saia
    `NAO COMPUTAVEL` e o portao que separa alfa de beta ficava caido. No instante em que o
    motor passou a gravar `direcao`, o xfail virou XPASS e QUEBROU a suite -- de proposito,
    para obrigar a trocar "o buraco existe" por "o buraco fechou, e eis a asercao".

    O que se afirma agora e o numero, nao a mera ausencia de `None`: um unico trade LONG tem
    de dar exposicao liquida **+1,0 exata**. Aceitar qualquer nao-`None` deixaria passar um
    sinal trocado, que e o erro que mais importa aqui -- ele transformaria um short em beta
    comprado no relatorio que existe justamente para pegar beta.
    """
    precos = [100.0] * 70
    lows = list(precos)
    lows[65] = 90.0                                    # fura o stop de 3% no candle 65
    trades = B.backtest_ativo("X/USDT", 0, 100, 10, df=df_sintetico(precos, lows=lows),
                              sinal_fn=sinal_em([60]))
    assert trades, "o motor nao gerou trade -- o teste nao esta medindo o que promete"
    assert all(t["direcao"] in (1, -1) for t in trades)
    assert V.exposicao_liquida(trades)["liquida"] == 1.0


def test_a_exposicao_liquida_da_rodada_real_ACOMPANHA_o_lado_da_posicao():
    """O contraponto do teste acima: se a exposicao nao mudar de sinal quando a posicao muda
    de lado, ela nao esta medindo direcao nenhuma -- esta devolvendo uma constante bonita.

    Tres casos com resposta conhecida, que e o padrao que o `[N-5]` usou (estrategia identica
    ao benchmark tem de dar `p = 1,0` exato): so LONG -> +1; so SHORT -> -1; um de cada com a
    MESMA duracao -> 0,0 exato, isto e, direcionalmente neutra.
    """
    precos = [100.0] * 70
    lows, highs = list(precos), list(precos)
    lows[65] = 90.0                                    # fura o stop do LONG
    highs[65] = 110.0                                  # fura o stop do SHORT
    df = df_sintetico(precos, highs=highs, lows=lows)

    longo = B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=sinal_em([60], direcao=1))
    curto = B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=sinal_em([60], direcao=-1))
    assert len(longo) == len(curto) == 1
    assert V.exposicao_liquida(longo)["liquida"] == 1.0
    assert V.exposicao_liquida(curto)["liquida"] == -1.0

    # mesma duracao dos dois lados -> a media ponderada por tempo tem de ser 0,0 exato
    assert longo[0]["ts_saida"] - longo[0]["ts"] == curto[0]["ts_saida"] - curto[0]["ts"]
    assert V.exposicao_liquida(longo + curto)["liquida"] == 0.0
    assert V.exposicao_liquida(longo + curto)["motivo"] == ""


# ============================ [N-7] CPCV no lugar do walk-forward =======================
def test_N7_o_PADRAO_roda_CPCV_e_o_walk_forward_continua_existindo():
    """O default e uma afirmacao sobre o que se mede por omissao, e ele mudou.

    O walk-forward NAO foi apagado -- ele responde a outra pergunta (deployment), e apaga-lo
    seria trocar uma pergunta pela outra fingindo que sao a mesma. Ele deixa de emitir
    veredito e passa a rodar em `sensibilidade()`, sempre, lado a lado.
    """
    assert V.PADRAO["cv"] == "cpcv"
    assert V.CVS == ("cpcv", "walk_forward")
    with pytest.raises(ValueError, match="cv deve ser"):
        V._nucleo({}, **{**V.PADRAO, "cv": "kfold"})


def test_N7_toda_trajetoria_cobre_a_linha_do_tempo_INTEIRA_uma_vez_so():
    """A propriedade que define o CPCV, e a que um bug de remontagem quebraria em silencio.

    Com N grupos e k=2 saem C(N,2) cortes e C(N-1,1) = N-1 trajetorias, e cada trajetoria tem
    de conter cada trade OOS exatamente UMA vez. Se a remontagem duplicasse, o P&L da
    trajetoria inflaria e o T da serie diaria continuaria igual -- ou seja, o Sharpe subiria
    sem que nada no relatorio denunciasse.
    """
    rng = np.random.default_rng(17)
    por_cfg = {}
    for k, cfg in enumerate(((50, 22), (55, 22), (65, 25))):
        por_cfg[cfg] = trades_diarios(rng.normal(0.0, 8.0, 800).tolist(),
                                      ts_saida=[T0 + (i + 1) * DIA for i in range(800)])
    base = V._nucleo_cpcv(por_cfg, criterio="sharpe", block=5, purga=True,
                          gap_pre_teste_ms=0, embargo_frac=0.0, atribuir="entrada",
                          periodo="D", n_boot=2000, seed=42)
    cp = base["cpcv"]
    assert cp["n_cortes"] == math.comb(V.CPCV_GRUPOS, V.CPCV_TESTE)
    assert cp["n_caminhos"] == math.comb(V.CPCV_GRUPOS - 1, V.CPCV_TESTE - 1)
    assert len(cp["sharpes"]) == cp["n_caminhos"]

    # remonta as trajetorias e confere: sem duplicata dentro de cada uma, e cobrindo a janela
    grupos = V._grupos_tempo(min(t["ts"] for tr in por_cfg.values() for t in tr),
                             max(t["ts"] for tr in por_cfg.values() for t in tr),
                             V.CPCV_GRUPOS)
    for n_trades in cp["trades_por_caminho"]:
        assert n_trades > 0
    # todo trade de uma trajetoria vem de um grupo distinto, e os 8 grupos aparecem
    tocados = set()
    for t in base["oos"]:
        for g, (a, b) in enumerate(grupos):
            if a <= t["ts"] < b or (g == len(grupos) - 1 and t["ts"] >= a):
                tocados.add(g)
                break
    assert tocados == set(range(V.CPCV_GRUPOS))
    assert len({id(t) for t in base["oos"]}) == len(base["oos"])


def test_N7_a_serie_de_recorde_e_a_trajetoria_MEDIANA_e_nunca_a_melhor():
    """Escolher a melhor trajetoria seria escolher no OOS -- o pecado que esta regua inteira
    existe para impedir, cometido pela porta que o proprio conserto abriu. Com numero PAR de
    trajetorias fica a MENOR das duas centrais, que e o lado conservador."""
    rng = np.random.default_rng(23)
    por_cfg = {cfg: trades_diarios(rng.normal(0.0, 8.0, 800).tolist(),
                                   ts_saida=[T0 + (i + 1) * DIA for i in range(800)])
               for cfg in ((50, 22), (55, 22), (65, 25))}
    base = V._nucleo_cpcv(por_cfg, criterio="sharpe", block=5, purga=True,
                          gap_pre_teste_ms=0, embargo_frac=0.0, atribuir="entrada",
                          periodo="D", n_boot=2000, seed=42)
    cp = base["cpcv"]
    srs = [x for x in cp["sharpes"] if x is not None]
    rep = cp["sharpes"][cp["caminho_representativo"]]
    assert rep == pytest.approx(float(np.median(srs)), abs=1e-9)
    # "nunca a melhor" dito de forma que sobrevive a EMPATE: com trajetorias empatadas no topo
    # a mediana pode COINCIDIR com o maximo valor, e ainda assim nao ser uma escolha pelo
    # maximo. O que se afirma e a posicao: no maximo metade das trajetorias esta acima dela.
    assert sum(1 for x in srs if x > rep) <= len(srs) // 2
    assert V.sharpe_anualizado(base["serie_oos"]) == pytest.approx(rep, abs=1e-4)


def test_N7_o_EMBARGO_de_LdP_volta_a_existir_e_de_fato_descarta_treino_DEPOIS_do_teste():
    """O achado do card, e ele corrige o `F4` sem contradize-lo.

    O `F4` da `REVISAO-ITEM1.md` estava certo: num walk-forward ESTRITAMENTE SEQUENCIAL nao ha
    treino apos o teste, logo o embargo de Lopez de Prado nao tinha o que embargar, e o
    parametro virou `gap_pre_teste_ms` (default 0). **Sob CPCV a premissa cai**: em quase todo
    corte existe treino depois do teste. Entao o embargo volta -- e trazer o CPCV sem ele seria
    importar a metade que da numero e deixar a metade que protege.

    A prova e direta: um trade que comeca logo DEPOIS do fim do bloco de teste entra no treino
    com embargo 0 e sai dele com embargo > 0.
    """
    bloco = [(1000.0, 2000.0)]
    tr = [{"ts": 500, "ts_saida": 600},       # antes do teste, fecha antes -> fica
          {"ts": 900, "ts_saida": 1500},      # span CRUZA a borda -> purga tira
          {"ts": 1500, "ts_saida": 1600},     # dentro do teste -> nunca e treino
          {"ts": 2050, "ts_saida": 2100},     # DEPOIS do teste -> so o embargo tira
          {"ts": 2500, "ts_saida": 2600}]     # bem depois -> fica
    sem = V._treino_cpcv(tr, bloco, purga=True, gap_ms=0, embargo_ms=0,
                         tem_saida=True, ultimo=9000)
    assert [t["ts"] for t in sem] == [500, 2050, 2500]

    com = V._treino_cpcv(tr, bloco, purga=True, gap_ms=0, embargo_ms=100,
                         tem_saida=True, ultimo=9000)
    assert [t["ts"] for t in com] == [500, 2500]       # o de 2050 caiu no embargo

    # e o gap PRE-teste continua valendo, agora antes de CADA bloco (a outra borda)
    gap = V._treino_cpcv(tr, bloco, purga=True, gap_ms=600, embargo_ms=0,
                         tem_saida=True, ultimo=9000)
    assert [t["ts"] for t in gap] == [2050, 2500]      # o de 500 caiu no gap [400, 1000)


def test_N7_a_purga_no_CPCV_e_BILATERAL_e_nao_afrouxa_a_do_walk_forward():
    """No walk-forward a purga era unilateral (`ts_saida < tr_lim`) porque so havia uma borda.
    No CPCV cada bloco de teste tem duas, e um trade cujo label ATRAVESSA qualquer uma delas
    sai do treino. CPCV precisa de MAIS purga, nao de menos -- afrouxar aqui deixaria vazar
    exatamente pelo lado que o esquema novo criou."""
    bloco = [(1000.0, 2000.0)]
    tr = [{"ts": 900, "ts_saida": 1001}]              # entra antes, sai DENTRO do teste
    assert V._treino_cpcv(tr, bloco, purga=True, gap_ms=0, embargo_ms=0,
                          tem_saida=True, ultimo=9000) == []
    # sem `ts_saida` a purga nao tem como agir -- e ela NAO finge que agiu
    tr2 = [{"ts": 900}]
    assert len(V._treino_cpcv(tr2, bloco, purga=True, gap_ms=0, embargo_ms=0,
                              tem_saida=False, ultimo=9000)) == 1


def test_N7_o_ultimo_bloco_de_teste_nao_inventa_embargo_fora_da_janela():
    """Embargo depois do fim da linha do tempo nao descarta nada -- so confundiria quem lesse
    o codigo achando que ha treino ali. A guarda e `b < ultimo`."""
    tr = [{"ts": 8500, "ts_saida": 8600}]
    # bloco terminando NO fim da janela: nao ha treino posterior, entao o trade fica
    assert len(V._treino_cpcv(tr, [(1000.0, 9000.0)], purga=True, gap_ms=0, embargo_ms=1000,
                              tem_saida=True, ultimo=9000)) == 0   # (esta DENTRO do teste)
    tr2 = [{"ts": 9500, "ts_saida": 9600}]
    assert len(V._treino_cpcv(tr2, [(1000.0, 9000.0)], purga=True, gap_ms=0, embargo_ms=1000,
                              tem_saida=True, ultimo=9000)) == 1


def test_N7_os_grupos_cobrem_a_janela_sem_buraco_e_sem_sobreposicao():
    """Grupo com buraco perderia trades sem avisar; grupo sobreposto poria o mesmo trade em
    dois blocos de teste e a trajetoria remontada teria duplicata."""
    g = V._grupos_tempo(1000, 9000, 8)
    assert len(g) == 8
    assert g[0][0] == 1000 and g[-1][1] == 9000
    assert all(g[i][1] == g[i + 1][0] for i in range(7))


def test_N7_o_CPCV_recusa_particao_impossivel_em_vez_de_calar():
    with pytest.raises(ValueError, match="n_grupos >= 3"):
        V._nucleo_cpcv({("a", 0): trades_diarios([1.0] * 100)}, criterio="sharpe", block=5,
                       purga=False, gap_pre_teste_ms=0, embargo_frac=0.0, atribuir="entrada",
                       periodo="D", n_boot=100, seed=1, n_grupos=2, k_teste=1)


def test_N7_o_walk_forward_continua_dando_EXATAMENTE_o_numero_de_antes():
    """A troca do [N-7] muda o numero por CONSTRUCAO -- e por isso ela so e auditavel se o
    esquema antigo continuar reproduzindo o que reproduzia. Este teste e o que separa "o CPCV
    mediu diferente" de "alguem quebrou o motor no caminho".

    O painel e o do golden, e o numero e o que o golden congelava ANTES do [N-7]:
    Sharpe anualizado -1,14 e IC-bloco (-1,2478 ; 0,0928) na trajetoria unica do walk-forward.
    """
    por_cfg, meta = V.carregar_golden_entrada()
    base = V._nucleo(por_cfg, **{**V.PADRAO, "cv": "walk_forward"})
    assert V.sharpe_anualizado(base["serie_oos"]) == pytest.approx(-1.14, abs=0.005)
    ic = V.bootstrap_ci(base["serie_oos"], n_boot=2000, modo="bloco", eh_serie_temporal=True,
                        block=5, seed=42)
    assert ic == (-1.2478, 0.0928)
    assert len(base["por_fold"]) == V.N_FOLDS


def test_N7_a_sensibilidade_imprime_os_DOIS_esquemas_lado_a_lado(capsys):
    """O CPCV nao responde a pergunta de deployment: em varios cortes o treino esta DEPOIS do
    teste, e isso e da definicao dele, nao defeito. Entao a linha `cv=walk_forward` tem de
    continuar saindo -- e imprimir as duas e a unica forma de a troca ser auditavel sem
    alguem ter de rodar o commit anterior."""
    res = _res_sintetico(mu=0.0, seed=3, n_dias=600)
    V.relatorio_sensibilidade(V.sensibilidade(res))
    saida = capsys.readouterr().out
    assert "cv=cpcv" in saida and "cv=walk_forward" in saida


def test_N7_o_relatorio_declara_que_o_CPCV_nao_e_simulacao_de_operacao(capsys):
    """A frase que impede a leitura errada mais cara possivel: ler um Sharpe de CPCV como "o
    que eu teria ganhado". Ele nao e isso, e o relatorio tem de dizer no lugar onde o numero
    aparece -- nao so no commit, que ninguem le junto com a saida."""
    res = _res_sintetico(mu=0.0, seed=4, n_dias=800)
    V.relatorio(res)
    saida = capsys.readouterr().out
    assert "CPCV" in saida
    assert "NAO e simulacao de operacao ao vivo" in saida
    assert "trajetoria MEDIANA" in saida
    assert "embargo LdP" in saida


# ============================ [N-8] PBO por CSCV e n_trials efetivo =====================
#
# O padrao de prova e o que o [N-5] usou e funcionou: um caso construido onde a resposta e
# CONHECIDA vale mais que dez asercoes sobre dado real. Aqui sao tres respostas conhecidas --
# 0,0 / ~0,5 / 1,0 -- e um instrumento que nao produzisse as tres nao estaria medindo nada.
def _serie_diaria(pnls):
    return [float(x) for x in pnls]


def test_N8_pbo_zero_quando_a_selecao_TRANSFERE():
    """Uma config domina em TODO periodo: e escolhida no treino sempre e e a melhor no teste
    sempre. Escolher transfere perfeitamente -> PBO = 0,0 EXATO, e o rank medio da campea tem
    de ser N (o topo), nao "alto"."""
    rng = np.random.default_rng(2026)
    m = {("boa", 0): _serie_diaria(rng.normal(3.0, 5.0, 960))}
    for k in range(1, 6):
        m[("ruim", k)] = _serie_diaria(rng.normal(-3.0, 5.0, 960))
    r = V.pbo_cscv(m)
    assert r["pbo"] == 0.0
    assert r["rank_medio"] == float(r["n_cfgs"])
    assert r["n_combinacoes"] == math.comb(16, 8)


def test_N8_pbo_um_no_pior_caso_possivel_cada_config_so_brilha_no_SEU_bloco():
    """O adversarial de verdade, e construi-lo ensina o que o CSCV e.

    A tentacao e fazer "a config que ganha na 1a metade perde na 2a". Isso NAO da PBO alto, e
    a razao e o ponto do metodo: o CSCV nao usa um corte cronologico -- ele usa TODAS as
    C(S,S/2) maneiras de escolher metade dos blocos, entao quase toda "metade" mistura os dois
    lados da linha do tempo e o efeito se cancela. (Medido: aquela construcao da PBO ~ 0,53,
    indistinguivel de ruido.)

    O caso que de fato satura: cada config tem um PICO num bloco proprio e deriva negativa em
    todos os outros. Qualquer que seja a metade sorteada para treino, a campea e uma config
    cujo pico esta NO treino -- e portanto ausente do teste, onde ela so tem a deriva
    negativa e cai abaixo das que guardaram o pico. PBO = 1,0 para qualquer particao.
    """
    rng = np.random.default_rng(99)
    S, N, T = 8, 8, 960
    blocos = V._blocos_iguais(T, S)
    m = {}
    for k in range(N):
        a = rng.normal(-1.0, 4.0, T)
        ini, fim = blocos[k]
        a[ini:fim] += 12.0
        m[("pico", k)] = _serie_diaria(a)
    r = V.pbo_cscv(m, S=S)
    assert r["pbo"] == 1.0
    assert r["rank_medio"] < (N + 1) / 2.0            # abaixo da mediana, sempre


def test_N8_pbo_meio_quando_e_so_RUIDO_e_escolher_nao_vale_mais_que_sortear():
    """Configs iid indistinguiveis: a campea do treino e campea por sorte, e no teste cai onde
    qualquer uma cairia. E o caso que calibra o instrumento -- 0,0 e 1,0 sozinhos passariam
    tambem num medidor que so olhasse o sinal da media."""
    rng = np.random.default_rng(1234)
    m = {("ruido", k): _serie_diaria(rng.normal(0, 10, 960)) for k in range(8)}
    r = V.pbo_cscv(m)
    assert 0.35 < r["pbo"] < 0.65
    assert abs(r["rank_medio"] - (r["n_cfgs"] + 1) / 2.0) < 1.0


def test_N8_o_logit_e_ESTRITO_e_por_isso_o_nulo_sob_ruido_e_publicado():
    """O bug que a primeira versao deste medidor teve, virado em teste.

    Contar `omega <= 0,5` em vez de `omega < 0,5` parece detalhe de borda e nao e: com N IMPAR
    existe um rank exatamente mediano, e ele sozinho move o PBO sob ruido puro de `(N-1)/2N`
    para `(N+1)/2N`. Com N=3 isso e 0,3333 contra 0,6667 -- e o teto de 0,5 passaria a REPROVAR
    ruido puro, um instrumento acusando overfit onde nao ha selecao nenhuma para overfitar.
    (Foi assim que o painel do golden mediu 0,7902 antes do conserto.)

    Por isso o `pbo_nulo` sai no resultado: com N par ele vale 0,5 e coincide com o teto (o caso
    do `GRID` de 6 configs desta casa); com N impar ele e menor, e quem le precisa saber contra
    que numero ler.
    """
    for N, esperado in ((2, 1 / 2), (3, 1 / 3), (4, 0.5), (6, 0.5), (7, 3 / 7), (8, 0.5)):
        rng = np.random.default_rng(500 + N)
        m = {("r", k): _serie_diaria(rng.normal(0, 10, 480)) for k in range(N)}
        assert V.pbo_cscv(m, S=8)["pbo_nulo"] == pytest.approx(esperado, abs=1e-4), N


def test_N8_o_pbo_sob_ruido_CALIBRA_no_proprio_nulo_em_media_sobre_paineis():
    """A calibracao do medidor -- e a razao de ela ser em MEDIA sobre paineis, nao num painel.

    O CSCV nao reamostra: ele reparticiona UMA realizacao. Se, naquela realizacao, uma config
    tem media amostral mais alta que as outras, ela tende a vencer em quase toda metade E em
    quase toda metade complementar -- e o PBO daquele painel sai bem longe de 0,5 nos dois
    sentidos. Isso nao e defeito: e o que "probabilidade de overfit DESTE backtest" significa.
    O que tem de calibrar e a MEDIA sobre painas nulos independentes, exatamente como o
    `test_reality_check_calibrado` faz com o alfa.

    Medir num painel so e afirmar precisao que o metodo nao entrega -- e foi o erro que a
    primeira versao deste teste cometeu (N=4, S=8, um painel: PBO = 0,0857 contra nulo 0,5).
    """
    for N in (4, 8):
        pbos = []
        for r in range(24):
            rng = np.random.default_rng(9000 + 100 * N + r)
            m = {("r", k): _serie_diaria(rng.normal(0, 10, 480)) for k in range(N)}
            pbos.append(V.pbo_cscv(m, S=8)["pbo"])
        media = float(np.mean(pbos))
        assert abs(media - 0.5) < 0.12, (N, media, pbos)


def test_N8_pbo_recusa_em_vez_de_inventar_quando_nao_ha_o_que_medir():
    """Duas faltas diferentes, dois motivos diferentes -- e NUNCA um 0,0.

    `pbo = 0.0` significa "nunca overfitou", que e a resposta mais confortavel que existe.
    Emiti-la por ausencia de objeto (uma config so) ou por serie curta seria a regua mentindo
    para o proprio lado, que e o modo de falha que este arquivo inteiro existe para impedir.
    """
    rng = np.random.default_rng(7)
    so_uma = V.pbo_cscv({("x", 0): _serie_diaria(rng.normal(0, 1, 960))})
    assert so_uma["pbo"] is None and "2 configs" in so_uma["motivo"]

    curta = V.pbo_cscv({("a", 0): [1.0, 2.0] * 10, ("b", 1): [2.0, 1.0] * 10}, S=16)
    assert curta["pbo"] is None and "curta" in curta["motivo"]

    with pytest.raises(ValueError, match="par e >= 4"):
        V.pbo_cscv({("a", 0): [1.0] * 100, ("b", 1): [2.0] * 100}, S=7)


def test_N8_o_sharpe_de_uma_uniao_de_blocos_bate_com_o_sharpe_da_serie_concatenada():
    """A otimizacao que torna C(16,8) barato -- somatorios por bloco em vez da serie -- so vale
    se ela devolver o MESMO numero. Um atalho que erra na 5a casa transformaria o PBO num
    numero plausivel e errado, que e pior que um numero ausente."""
    rng = np.random.default_rng(11)
    T, S = 480, 8
    m = {("a", 0): _serie_diaria(rng.normal(0.3, 2.0, T)),
         ("b", 1): _serie_diaria(rng.normal(-0.1, 3.0, T))}
    blocos = V._blocos_iguais(T, S)
    cfgs, n, soma, quad = V._agregados_por_bloco(m, blocos)
    escolha = (0, 2, 3, 6)
    rapido = V._sharpe_de_blocos(n, soma, quad, escolha)
    for i, c in enumerate(cfgs):
        direto = np.concatenate([np.asarray(m[c])[a:b] for a, b in
                                 [blocos[j] for j in escolha]])
        assert rapido[i] == pytest.approx(V._sr(direto), rel=1e-12)


def test_N8_os_blocos_do_cscv_cobrem_a_serie_inteira_e_a_sobra_nao_empilha_no_ultimo():
    """Bloco que valesse o dobro dos outros desbalancearia toda combinacao que o contivesse --
    e o desbalanceio seria invisivel, porque o PBO sai como um numero so."""
    for T, S in ((960, 16), (901, 16), (100, 4), (17, 4)):
        b = V._blocos_iguais(T, S)
        assert len(b) == S
        assert b[0][0] == 0 and b[-1][1] == T
        assert all(b[i][1] == b[i + 1][0] for i in range(S - 1))
        tam = [f - i for i, f in b]
        assert max(tam) - min(tam) <= 1


def test_N8_n_trials_efetivo_reconhece_grid_ortogonal_e_grid_de_gemeas():
    """Os dois extremos com resposta conhecida: 6 configs independentes valem ~6 tentativas;
    6 copias da mesma coisa valem ~1. Entre os dois esta a pergunta que o [N-9] deixou aberta
    -- quantas das varreduras contadas sao de fato independentes."""
    rng = np.random.default_rng(31)
    orto = {("o", k): _serie_diaria(rng.normal(0, 1, 900)) for k in range(6)}
    e = V.n_trials_efetivo(orto)
    assert 5.0 < e["participacao"] <= 6.0
    assert e["pcs_95"] == 6

    base = rng.normal(0, 1, 900)
    gemeas = {("g", k): _serie_diaria(base + rng.normal(0, 0.02, 900)) for k in range(6)}
    e = V.n_trials_efetivo(gemeas)
    assert 1.0 <= e["participacao"] < 1.2
    assert e["pcs_95"] == 1
    assert e["corr_media"] > 0.99


def test_N8_o_efetivo_usa_CORRELACAO_e_nao_covariancia():
    """Config que opera mais tem P&L de variancia maior. Sob covariancia ela dominaria o
    espectro sozinha e o numero mediria VOLUME DE OPERACAO em vez de redundancia -- e mediria
    para o lado errado, porque um grid com uma config barulhenta pareceria mais independente.

    Aqui as 4 series sao a MESMA coisa em escalas muito diferentes: redundancia total. Sob
    correlacao o efetivo tem de dar ~1 apesar das escalas."""
    rng = np.random.default_rng(41)
    base = rng.normal(0, 1, 900)
    m = {("esc", k): _serie_diaria(base * (10.0 ** k)) for k in range(4)}
    e = V.n_trials_efetivo(m)
    assert e["participacao"] == pytest.approx(1.0, abs=1e-6)


def test_N8_o_efetivo_NAO_entra_no_veredito_e_o_relatorio_diz_por_que(capsys):
    """A guarda que impede este numero de virar a ferramenta errada.

    `n_trials` menor -> SR0 menor -> DSR MAIOR. Existe um caminho direto entre "meu grid e
    redundante" e "meu Sharpe deflacionado ficou bonito", e ele e o tipo de conserto que o
    NORTE.md proibe. Entao o DSR que DECIDE tem de continuar saindo do n_trials declarado, e o
    relatorio tem de imprimir o outro ao lado -- deixando a tentacao visivel em vez de
    disponivel.
    """
    res = _res_sintetico(mu=0.0, seed=5)
    d = res["bloco_a"]["dsr_melhor_is"]
    ef = res["bloco_a"]["n_trials_efetivo"]
    de = res["bloco_a"]["dsr_se_n_trials_fosse_o_efetivo"]
    # o DSR do veredito le o n_trials DECLARADO (arredondado como o relatorio o publica)
    assert d["sr0"] == round(V._sr0_esperado(d["n"], res["n_trials"]), 4)
    assert ef["participacao"] < ef["n_cfgs"] + 1e-9
    assert de is not None and de["dsr"] != d["dsr"]                 # o outro existe, e diverge

    V.relatorio(res)
    saida = capsys.readouterr().out
    assert "n_trials EFETIVO" in saida
    assert "NAO entra no veredito" in saida
    assert "n_trials menor levanta o DSR" in saida


def test_N8_o_PBO_e_condicao_de_EDGE_e_so_APERTA_nunca_afrouxa(capsys):
    """[CLAUDE.md] 2: apertar guarda pode; afrouxar, so o dono.

    O PBO entra no `_veredito` como condicao a MAIS para EDGE -- ele so consegue transformar
    EDGE em SEM_EVIDENCIA, nunca o contrario. Provado nos dois sentidos sobre um resultado
    REAL, mexendo so no PBO: com PBO acima do teto o veredito cai e o motivo cita o CSCV; com
    o PBO removido (nao calculavel) o veredito volta a ser o que era.

    Poe-lo no portao em vez de so no relatorio nao e zelo: "medir e nao comparar" e
    literalmente o defeito que o [Q-7] veio consertar neste arquivo.
    """
    res = _res_sintetico(mu=8.0, seed=6, n_dias=900)
    assert res["veredito"]["classe"] == "EDGE"
    assert res["bloco_a"]["pbo"]["pbo"] <= V.PBO_TETO

    ruim = json.loads(json.dumps(V._canonico({k: v for k, v in res.items()
                                              if k not in ("por_cfg", "oos", "matriz_is")})))
    ruim["bloco_a"]["pbo"]["pbo"] = 0.9
    v = V._veredito(ruim)
    assert v["classe"] == "SEM_EVIDENCIA" and "PBO = 0.9" in v["motivo"]
    assert "CSCV" in v["motivo"]

    # PBO ausente NAO bloqueia: sem ordenacao entre configs nao ha overfit DE SELECAO a medir,
    # e bloquear ali faria a guarda depender do tamanho do grid, nao do defeito.
    ruim["bloco_a"]["pbo"] = {"pbo": None, "motivo": "so uma config"}
    assert V._veredito(ruim)["classe"] == "EDGE"


# ============================ [N-9] log append-only de tentativas ========================
def _grid3():
    return [(50, 22), (55, 22), (65, 25)]


def _resumo():
    return {"veredito": "SEM_EVIDENCIA", "sharpe_anualizado": 0.1}


def test_o_log_e_APPEND_only_e_a_linha_antiga_nao_muda(tmp_path):
    """[N-9/F10] Append-only nao e detalhe de implementacao: e a propriedade inteira.

    Um JSON unico re-serializado a cada rodada perde tentativa por corrida de escrita e deixa
    "limpar" o historico sem rastro. O registro existe justamente para ser inconveniente de
    encolher, e o teste afirma isso: a primeira linha tem de sobreviver byte a byte a segunda
    escrita.
    """
    alvo = str(tmp_path / "t.jsonl")
    V.registrar_tentativa("primeira", _grid3(), 100, _resumo(), caminho=alvo)
    primeira = open(alvo, encoding="utf-8").readlines()[0]
    V.registrar_tentativa("segunda", _grid3(), 100, _resumo(), caminho=alvo)
    linhas = open(alvo, encoding="utf-8").readlines()
    assert len(linhas) == 2
    assert linhas[0] == primeira
    assert json.loads(linhas[0])["rotulo"] == "primeira"
    assert json.loads(linhas[1])["rotulo"] == "segunda"


def test_o_registro_traz_o_que_o_F10_pediu(tmp_path):
    """"hash do grid + timestamp + seed + resultado" -- o parecer foi literal."""
    alvo = str(tmp_path / "t.jsonl")
    reg = V.registrar_tentativa("r", _grid3(), 100, _resumo(), caminho=alvo)
    for chave in ("ts", "grid_hash", "seed", "resultado", "n_cfgs", "n_trials_declarado",
                  "selecoes", "padrao_hash", "criterio", "n_folds"):
        assert chave in reg, chave
    assert reg["seed"] == V.PADRAO["seed"]
    assert reg["selecoes"] == len(_grid3()) * V.N_FOLDS
    assert len(reg["grid_hash"]) == 64                       # sha256 em hex


def test_grids_iguais_dao_o_MESMO_hash_e_grids_diferentes_nao(tmp_path):
    """Sem isso o log nao distingue "rodei de novo o mesmo grid" de "abri um grid novo" -- e
    essa e a diferenca entre repetir uma tentativa e gastar outra."""
    alvo = str(tmp_path / "t.jsonl")
    a = V.registrar_tentativa("a", _grid3(), 100, _resumo(), caminho=alvo)
    b = V.registrar_tentativa("b", list(_grid3()), 100, _resumo(), caminho=alvo)
    c = V.registrar_tentativa("c", _grid3() + [(70, 30)], 100, _resumo(), caminho=alvo)
    assert a["grid_hash"] == b["grid_hash"]
    assert a["grid_hash"] != c["grid_hash"]


def test_contar_tentativas_soma_as_SELECOES_e_nao_so_as_linhas(tmp_path):
    """O numero que um dia substitui o `N_TRIALS` contado a mao nao e "quantas vezes rodei" --
    e quantas ESCOLHAS de parametro o procedimento fez: `n_cfgs x N_FOLDS` por varredura."""
    alvo = str(tmp_path / "t.jsonl")
    for _ in range(4):
        V.registrar_tentativa("r", _grid3(), 100, _resumo(), caminho=alvo)
    c = V.contar_tentativas(alvo)
    assert c["varreduras"] == 4
    assert c["selecoes"] == 4 * len(_grid3()) * V.N_FOLDS
    assert c["grids_distintos"] == 1


def test_linha_corrompida_e_CONTADA_e_nao_engolida(tmp_path):
    """Engolir a linha ilegivel seria mentir PARA BAIXO justamente no numero que este log
    existe para dar -- e para baixo em `n_trials` significa DSR para cima, que e a direcao
    confortavel."""
    alvo = tmp_path / "t.jsonl"
    V.registrar_tentativa("boa", _grid3(), 100, _resumo(), caminho=str(alvo))
    with open(alvo, "a", encoding="utf-8") as f:
        f.write("{isto nao e json\n\n")
    c = V.contar_tentativas(str(alvo))
    assert c["varreduras"] == 1 and c["linhas_ilegiveis"] == 1


def test_log_que_nao_pode_escrever_NAO_derruba_a_varredura(tmp_path, monkeypatch):
    """Um log que derruba a varredura que ele veio medir e pior do que nao ter log."""
    def explode(*a, **k):
        raise OSError("disco somente leitura")
    monkeypatch.setattr(V.os, "makedirs", explode)
    assert V.registrar_tentativa("r", _grid3(), 100, _resumo(),
                                 caminho=str(tmp_path / "t.jsonl")) is None


def test_o_pytest_NAO_escreve_no_log_de_verdade():
    """Um painel sintetico de 3 configs nao e tentativa de data-snooping contra o mercado.

    Deixar a suite escrever encheria o contador de ruido e o numero deixaria de significar o
    que promete. A guarda e esta, e ela esta ligada agora mesmo -- este teste roda sob pytest.
    """
    assert V._deve_registrar() is False
    antes = V.contar_tentativas()["varreduras"]
    _res_sintetico(mu=0.0, seed=31, n_dias=300)
    assert V.contar_tentativas()["varreduras"] == antes


def test_o_runner_escreve_UMA_linha_por_varredura(tmp_path, monkeypatch):
    """A outra metade: fora do pytest, `walk_forward` -- o unico ponto por onde TODA varredura
    passa -- grava sozinho. Sem isso o log dependeria de alguem lembrar de chamar."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    alvo = str(tmp_path / "t.jsonl")
    monkeypatch.setattr(V, "CAMINHO_TENTATIVAS", alvo)
    assert V._deve_registrar() is True
    _res_sintetico(mu=0.0, seed=32, n_dias=300)
    c = V.contar_tentativas(alvo)
    assert c["varreduras"] == 1
    reg = V.ler_tentativas(alvo)[0][0]
    assert reg["resultado"]["veredito"] in ("SEM_EVIDENCIA", "INCONCLUSIVO", "EDGE")
    assert reg["resultado"]["rc_p"] is not None


def test_a_varredura_que_FALHOU_tambem_entra_no_log(tmp_path, monkeypatch):
    """Registrar so o que deu certo e vies de publicacao aplicado a si mesmo.

    E ele empurra `n_trials` para BAIXO, ou seja, o DSR para cima -- a direcao confortavel.
    Poucos trades, veredito INCONCLUSIVO: voce olhou para o dado do mesmo jeito.
    """
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    alvo = str(tmp_path / "t.jsonl")
    monkeypatch.setattr(V, "CAMINHO_TENTATIVAS", alvo)
    por_cfg = {(50, 22): trades_diarios([1.0] * 5)}
    r = V.walk_forward(gerador_constante(por_cfg), [(50, 22)], n_trials=100, rotulo="curta")
    assert "erro" in r
    regs, _ = V.ler_tentativas(alvo)
    assert len(regs) == 1 and regs[0]["resultado"]["veredito"] == "INCONCLUSIVO"
    assert "erro" in regs[0]["resultado"]


def test_a_lista_de_divergencias_AVISA_quando_esta_incompleta(tmp_path, monkeypatch):
    """Defeito do `[N-6]` achado ao rodar o `[N-7]`, e ele e do tipo mais caro: o silencioso.

    `_diferencas` parava em 30 e o CLI imprimia as 30 sem dizer que havia mais. A troca do
    walk-forward pelo CPCV produziu 45, e as 15 escondidas eram `pnl_oos`, `n_oos`,
    `serie_oos`, `por_fold` e o digest do OOS -- exatamente as que dizem se o esquema novo
    mudou o que devia mudar. Uma lista que parece inteira e nao e faz de "eu li a divergencia"
    uma frase falsa dita de boa-fe, que e como o golden vira decorativo sem ninguem mentir.

    O teto continua existindo (divergencia estrutural gera milhares de linhas e enterra o
    terminal); o que mudou e que agora ele FALA.
    """
    monkeypatch.setattr(V, "TETO_DIFERENCAS", 3)
    esp = {f"k{i}": i for i in range(10)}
    atu = {f"k{i}": i + 1 for i in range(10)}
    difs = V._diferencas(esp, atu, teto=V.TETO_DIFERENCAS)
    assert len(difs) == 3                              # o teto continua valendo

    saida = tmp_path / "s.json"
    saida.write_text(json.dumps({"snapshot": esp}), encoding="utf-8")
    monkeypatch.setattr(V, "golden_snapshot", lambda _res: atu)
    monkeypatch.setattr(V, "rodar_golden", lambda _c=None: None)
    ok, difs = V.conferir_golden(caminho_saida=str(saida))
    assert not ok
    assert "INCOMPLETA" in difs[-1]                    # ...e agora ele avisa


def test_o_golden_NAO_conta_como_tentativa(tmp_path, monkeypatch):
    """Conferir regressao sobre painel congelado nao gasta orcamento estatistico. Se contasse,
    cada rodada de CI inflaria `n_trials` e o numero mediria ruido de suite."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    alvo = str(tmp_path / "t.jsonl")
    monkeypatch.setattr(V, "CAMINHO_TENTATIVAS", alvo)
    ok, _ = V.conferir_golden()
    assert ok
    assert V.contar_tentativas(alvo)["varreduras"] == 0
    assert V.REGISTRAR_TENTATIVAS is True            # e a flag volta ao que era


def test_o_registro_NAO_entra_no_resultado_e_por_isso_nao_quebra_o_golden(tmp_path, monkeypatch):
    """O timestamp e a unica coisa irreproduzivel que este card introduz. Ele mora no arquivo,
    nunca no dicionario que `walk_forward` devolve -- se morasse, o golden do [N-6] passaria a
    falhar a cada segundo e a "solucao" seria tirar do golden o que ele veio congelar."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(V, "CAMINHO_TENTATIVAS", str(tmp_path / "t.jsonl"))
    res = _res_sintetico(mu=0.0, seed=33, n_dias=300)
    assert not any("tentativa" in k or "registro" in k for k in res)
    assert "ts" not in res


def test_relatorio_de_tentativas_diz_que_o_N_TRIALS_ainda_e_PISO(capsys, tmp_path):
    """O log nao substitui o `N_TRIALS` hoje -- ele so conta desta maquina e so daqui pra
    frente. Um relatorio que nao dissesse isso convidaria a trocar um piso honesto por uma
    contagem que subestima todo o passado do projeto."""
    alvo = str(tmp_path / "t.jsonl")
    V.registrar_tentativa("r", _grid3(), 100, _resumo(), caminho=alvo)
    V.relatorio_tentativas(alvo)
    saida = capsys.readouterr().out
    assert "PISO CONTADO" in saida and str(V.N_TRIALS) in saida
    assert "desta maquina" in saida


def test_log_inexistente_le_vazio_sem_quebrar(tmp_path):
    """Primeira maquina, primeira rodada: o log ainda nao existe e isso nao e erro."""
    assert V.ler_tentativas(str(tmp_path / "nao-existe.jsonl")) == ([], 0)
    assert V.contar_tentativas(str(tmp_path / "nao-existe.jsonl"))["varreduras"] == 0
