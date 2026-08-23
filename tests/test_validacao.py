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
import pytest

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
