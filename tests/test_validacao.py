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
import math

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


def test_serie_oos_cobre_so_a_janela_oos_nao_a_timeline_inteira():
    """Bug que quase entrou no registro: a serie diaria OOS montada sobre a grade INTEIRA.

    O primeiro dos `N_FOLDS+1` segmentos e treino puro -- nunca foi testado, nao ha decisao a
    avaliar ali. Empilhar esses ~1/6 de dias como "dia de P&L zero" erra os DOIS numeros que
    o [Q-1] veio consertar, e em direcoes opostas: deflaciona o Sharpe diario (mais zeros no
    denominador da media) e infla o T que alimenta o MDS (portao de poder frouxo demais).

    O BLOCO A continua na timeline inteira, e isso e correto: cada config foi rodada nela
    inteira, e o nulo do Reality Check e sobre a familia in-sample.
    """
    res = _res_sintetico(mu=0.0, seed=11, n_dias=1200)
    grade_toda, grade_oos = res["grade"], res["grade_oos"]
    assert len(grade_oos) < len(grade_toda)
    assert 0.75 < len(grade_oos) / len(grade_toda) < 0.90       # ~5/6 da timeline
    assert res["bloco_b"]["T"] == len(grade_oos)
    assert len(res["bloco_a"]["serie_naive"]) == len(grade_toda)
    # nenhum trade OOS cai fora da janela, e a janela nao comeca com uma sequencia de zeros
    dias_oos = {t["ts"] // DIA for t in res["oos"]}
    assert min(dias_oos) >= grade_oos[0] and max(dias_oos) <= grade_oos[-1]
    assert res["serie_oos"][0] != 0.0 or res["serie_oos"][1] != 0.0


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
    t = _um_trade(df, "trailing", trailing_dist=0.02)
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
    t = _um_trade(df, "trailing", trailing_dist=0.02)
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
                          saida="trailing", trailing_dist=0.02)
    assert tr == []                                     # nao fechou dentro do candle do pico
    # ...mas o stop ficou armado em 108*0,98 = 105,84, e o candle SEGUINTE o encontra
    lows2 = list(lows)
    lows2[64] = 100.0
    df2 = df_com_indicadores(precos, highs=highs, lows=lows2)
    t = _um_trade(df2, "trailing", trailing_dist=0.02)
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
    t2 = _um_trade(df, "trailing", trailing_dist=0.02)
    assert t2["motivo"] == "trailing"                   # 2%: stop em 106*0,98 = 103,88 -> bate
    assert B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=sinal_em([60]),
                            saida="trailing", trailing_k_atr=1.0) == []   # 5%: 100,7 -> nao bate


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
                                saida="trailing", trailing_dist=0.02, **kw)

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
    mudem de numero."""
    precos = [100.0] * 62 + [101.5] * 2 + [98.0] * 6
    highs, lows = list(precos), list(precos)
    lows[64] = 98.0
    df = df_com_indicadores(precos, highs=highs, lows=lows)
    fn = sinal_em([60], stop_dist=0.01)                 # risco = 1% -- METADE do trailing

    def roda(**kw):
        return B.backtest_ativo("X/USDT", 0, 100, 10, df=df, sinal_fn=fn,
                                saida="trailing", trailing_dist=0.02, **kw)

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
