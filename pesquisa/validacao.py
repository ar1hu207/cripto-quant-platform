"""
A REGUA: decide se uma estrategia tem edge, e sabe dizer quando NAO consegue decidir.

Walk-forward (parametro escolhido so no passado, avaliado no futuro nao-visto) + White's
Reality Check + Hansen SPA + Deflated/Probabilistic Sharpe + bootstrap de bloco, tudo sobre
a SERIE DIARIA agregada, sob um criterio unico e travado (`PADRAO`).

Por que: o split-por-moedas no MESMO periodo (`legado/validar_reversao*.py`, aposentados
pelo [Q-2] justamente por isto) nao e honesto -- cripto e correlacionada e o corte era
escolhido olhando o OOS. Aqui os parametros sao escolhidos SO no treino e avaliados no
teste, nunca peeking.

**A terceira resposta, que e o que o [Q-1] acrescenta.** Antes desta versao a regua so sabia
dizer "tem edge" ou "nao tem". Um instrumento sem poder estatistico emite "nao tem edge" para
tudo, inclusive para um edge real -- e ai o veredito negativo nao significa nada. Agora ela
calcula o Sharpe anualizado MINIMO DETECTAVEL (MDS) com 80% de poder a alfa=0,05 dado o T
efetivo, e se o MDS passar de `MDS_LIMITE` ela responde `INCONCLUSIVO: instrumento sem poder`
em vez de "sem edge". Ausencia de evidencia nao e evidencia de ausencia, e a regua passa a
dizer isso com numero (F14 da `REVISAO-ITEM1.md`).

**O veredito continua negativo, e isso e o produto.** Ver `CLAUDE.md`, cabecalho: honestidade
e premissa, nao bug a consertar. Praticamente todo conserto desta versao empurra o numero
para BAIXO (DSR sobre ~900 observacoes diarias em vez de 370 trades pseudo-independentes, IC
por blocos em vez de iid, n_trials 30 -> 100). Se o numero piorar, e o instrumento
funcionando.

Rodar (da RAIZ do repo):

    python -m pesquisa.validacao              # a politica A + o contraste de funding [P2-10]
    python -m pesquisa.validacao politicas    # A x B x C na mesma regua [P1-10]

---
De onde vem cada decisao. `ITEM1-VALIDACAO-RIGOROSA.md` (a proposta, jul/2026) e
`REVISAO-ITEM1.md` (o parecer estatistico que a revisou). Onde os dois divergem, vale a
revisao, e o achado dela esta citado por numero (F1..F19) no ponto do codigo.

O que o `T-EDGE` (onda 3 do M4) destravou, e que ate 2026-08-23 estava desligado:
`pesquisa/backtest_plataforma.py` passou a gravar `ts_saida` em cada trade.

  * PURGA (`ITEM1` §3.2 / F4): "so entra no treino trade com `ts_saida < tr_lim`". A funcao
    sempre existiu e sempre foi PEDIDA (`PADRAO["purga"] = True`); ela desligava sozinha por
    falta do campo, e o relatorio imprimia que desligou. Agora ela AGE, e o vazamento de
    borda de fold do `ITEM1` §2/P2 -- que empurrava o resultado para CIMA, contra a conclusao
    negativa -- deixa de estar presente e nao medido (F13). Numero que mudar por causa disso
    e o instrumento funcionando, nao regressao.
  * `atribuir="saida"` (`ITEM1` §3.3 / F3): a revisao quer o P&L atribuido ao dia da SAIDA,
    porque e onde ele e realizado. Isso passou a ser POSSIVEL, e mesmo assim o `PADRAO`
    continua `"entrada"`: trocar o criterio travado do veredito e decisao de dono, nao efeito
    colateral de um campo novo ([F3] existe justamente para o criterio nao virar grau de
    liberdade). A variante roda em `sensibilidade()`, que imprime as duas lado a lado sempre
    -- que e o lugar onde uma escolha se torna auditavel sem virar escolha de quem chama.
"""
import math
import sys

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from pesquisa import dados
import scoring
from pesquisa.backtest_plataforma import backtest_ativo

COINS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT",
         "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "LTC/USDT", "DOT/USDT", "TRX/USDT"]
TF, VALOR, LEV = "1h", 100, 10

# [F6] 180 -> 1095 dias. E a mudanca de maior retorno do Item 1 inteiro, e nao estava na
# proposta original. O gargalo do instrumento nunca foi o teste, foi o T: com 180 dias, alfa
# 0,05 unilateral e 80% de poder, a regua so detecta Sharpe anualizado ~3,5 -- um numero que
# quase nenhuma estrategia real atinge. Com 3 anos o minimo detectavel cai para ~1,5. Nenhum
# dos testes novos (Reality Check, SPA, FDR) mexe nisso; so o T mexe. Custo: uma constante,
# um download (`dados.baixar_ohlcv` ja pagina e cacheia) e ~13 min de backtest por passada.
DIAS = 1095

# [P2-10] O backtest_ativo tem o parametro funding_8h desde a auditoria de junho, e este
# script nunca o passou -- rodava no default 0.0. Uma validacao walk-forward que nao paga o
# carry que o live paga mede uma estrategia que nao existe. 0,0001/8h e a mediana historica
# de perpetuo que o config.py legado ja documentava (legado/config.py:28).
FUNDING_8H = 0.0001

GRID = [{"min_conv": mc, "adx_min": ax} for mc in (50, 55, 65) for ax in (22, 25)]
N_FOLDS = 5
PPA = 365            # periodos/ano da serie DIARIA (cripto negocia todo dia)

# [F10] n_trials como PISO CONTADO, nao estimativa no olho. O valor antigo (30 = GRID x
# N_FOLDS) contava so as tentativas deste arquivo e ignorava o data-snooping real do projeto.
# Contagem: `legado/tune.py` 3 TF x 2 lev x 3 cortes = 18 · `legado/sweep.py` 3x3 = 9 ·
# `legado/experimentos.py` 3x3x2 = 18 · GRID x N_FOLDS = 30 · mais os cinco `validar_*`
# aposentados pelo [Q-2], `scalp_backtest`, `dca_backtest`, `otimizar_risco`. 100 e defensavel
# como PISO. E a sensibilidade do DSR a este numero e LOGARITMICA (SR0 ~ sqrt(2 ln N)):
# errar por duas ordens de grandeza apenas dobra o SR0. O relatorio publica a tabela, para
# que ninguem precise acreditar no numero.
N_TRIALS = 100
N_TRIALS_TABELA = (6, 30, 100, 1000, 10000)

# [F14] Portao de emissao de veredito. Acima disto a regua nao responde "sem edge" -- responde
# INCONCLUSIVO. Nao e piso de contagem de trades de proposito: 370 trades em 12 moedas
# correlacionadas nao sao 370 observacoes, e um piso em contagem finge que sao.
MDS_LIMITE = 2.0
T_EFETIVO_MINIMO = 100          # cinto-e-suspensorio: dias com P&L nao-nulo na serie OOS

# [Q-7] Calibracao. `M` paineis nulos por rodada; a banda binomial e CALCULADA a partir
# destes dois numeros, nunca escrita como texto no print -- foi assim que a rodada do [Q-1]
# imprimiu "[0,02 ; 0,09]" ao lado de um 0,01 medido e ninguem comparou. `n_boot=200` dentro
# do controle e deliberado e barato: sob a regra `p = (1+#)/(B+1)` o TAMANHO do teste e
# 10/201 = 0,0498 com B=200 e 100/2001 = 0,04998 com B=2000 -- a discretizacao move menos de
# 0,5% relativo. O que `n_boot` grande compra e precisao de CADA p, nao tamanho, e a taxa de
# rejeicao media sobre M paineis nao precisa disso. Prova: `test_calibracao_nao_depende_de_n_boot`.
M_CONTROLE_NULO = 200
N_BOOT_CONTROLE = 200
CONF_BANDA = 0.95

# [Q-7] O TETO que bloqueia o veredito por SUPER-rejeicao, e por que ele nao e simplesmente
# "fora da banda de 95%".
#
# Um portao que bloqueia o marco inteiro tem de disparar so quando a impressao do proprio
# diagnostico nao pode explicar o achado. A banda de 95% e o DIAGNOSTICO que o card pediu, e
# ela continua sendo calculada e reportada; mas ela tem 2,5% de falso alarme por construcao,
# e com M=200 o IC exato da taxa medida e largo (2 rejeicoes -> [0,001 ; 0,036]). Gatear na
# banda faria a guarda depender do tamanho da amostra do diagnostico, nao do defeito.
#
# Entao o gatilho e MATERIALIDADE, lida pela ponta do IC que torna o disparo mais dificil:
# bloqueia quando o limite INFERIOR do IC exato passa de 0,10, o dobro do alfa nominal. Um
# teste com o dobro do tamanho torna a condicao de EDGE materialmente mais facil. A mesma
# regra, espelhada, vale para o lado de baixo: o portao de poder le o piso do MDS calculado
# com o alfa no TOPO do IC (`mds_piso_min`). As duas guardas leem a ponta menos conveniente
# para si -- e isso e o que impede "medi com M pequeno e o portao disparou" nos dois sentidos.
ALFA_TETO_PORTAO = 0.10

# [F3] O criterio e TRAVADO. `criterio` (3) x `modo` (2) x `atribuir` (2) x `block` (5) x
# `purga` (2) sao 120 maneiras de rodar a regua, e um instrumento que existe para detectar
# data-snooping nao pode multiplicar por 120 a superficie de snooping. Alguem -- talvez voce,
# daqui a um ano, cansado -- rodaria as variantes e reportaria a melhor.
#
#   * o veredito e computado EXCLUSIVAMENTE sob `PADRAO`, sempre;
#   * `walk_forward()` nao aceita `criterio`/`modo`/`atribuir`/`block` como argumento: nao ha
#     como pedir outro veredito, so como ler o diagnostico;
#   * as variantes rodam em `sensibilidade()`, que imprime TODAS de uma vez, sempre, como
#     diagnostico -- nunca como escolha de quem chama.
#
# `criterio="sharpe"` e troca deliberada do default antigo: soma bruta de P&L favorece a
# config que mais OPERA, nao a melhor -- e o proprio `ITEM1` §2/P5 diagnostica isso, mas a
# assinatura que ele propos manteve `"pnl"`.
PADRAO = {
    "criterio": "sharpe",
    "modo": "expandindo",
    "atribuir": "entrada",      # "saida" ja e possivel (ha `ts_saida`); trocar e do dono
    "block": 5,
    "purga": True,              # pedida sempre; desliga sozinha e avisa se faltar ts_saida
    "gap_pre_teste_ms": 0,
    "n_boot": 2000,
    "seed": 42,
    "periodo": "D",
}
CRITERIOS = ("sharpe", "pnl", "pnl_por_trade")
MODOS = ("expandindo", "rolante")
ATRIBUIR = ("entrada", "saida")  # so roda em sensibilidade(), e so quando ha `ts_saida`
BLOCKS = (1, 2, 5, 10, 20)      # [F18] sensibilidade a block; block=1 E o iid, de graca
DIA_MS = 86_400_000


# ============================ estatistica basica ============================
def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_ppf(p):
    """Inversa da normal (Acklam) -- sem scipy."""
    if p <= 0:
        return -1e9
    if p >= 1:
        return 1e9
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


def stats(pnls):
    n = len(pnls)
    if n < 2:
        return {"n": n, "win": 0, "pnl": round(sum(pnls), 2), "sharpe_trade": 0}
    m = sum(pnls) / n
    sd = (sum((x - m) ** 2 for x in pnls) / (n - 1)) ** 0.5
    return {"n": n, "win": round(sum(1 for x in pnls if x > 0) / n * 100, 1),
            "pnl": round(sum(pnls), 2),
            "sharpe_trade": round(m / sd, 4) if sd > 0 else 0}


def _sr(serie):
    """Sharpe por periodo da serie. Devolve None se nao der pra calcular."""
    a = np.asarray(serie, dtype=float)
    if a.size < 2:
        return None
    sd = a.std(ddof=1)
    return None if sd == 0 else float(a.mean() / sd)


def sharpe_anualizado(serie, ppa=PPA):
    sr = _sr(serie)
    return None if sr is None else sr * math.sqrt(ppa)


# ============================ agregacao temporal ============================
def grade_de_periodos(trades, atribuir="entrada", periodo="D"):
    """Grade COMUM de periodos, do primeiro ao ultimo trade, sem buracos.

    Comum e a palavra que importa: o Reality Check exige que todas as configs tenham series
    do MESMO tamanho e alinhadas no tempo, senao o maximo entre elas compara coisas
    diferentes. Periodo sem trade entra como 0.0, nao some.
    """
    if periodo != "D":
        raise ValueError("hoje so 'D' (diario); qualquer outro periodo precisa de decisao")
    chaves = [_chave_periodo(t, atribuir) for t in trades]
    if not chaves:
        return []
    return list(range(min(chaves), max(chaves) + 1))


def _chave_periodo(t, atribuir):
    if atribuir == "saida":
        if "ts_saida" not in t:
            raise ValueError(
                "atribuir='saida' exige `ts_saida` no trade -- o gerador nao gravou")
        return int(t["ts_saida"]) // DIA_MS
    if atribuir != "entrada":
        raise ValueError("atribuir deve ser 'entrada' ou 'saida'")
    return int(t["ts"]) // DIA_MS


def pnl_por_periodo(trades, grade, atribuir="entrada"):
    """Agrega trades em P&L por periodo sobre uma `grade` de chaves. Periodo sem trade = 0.0.

    Este e o passo que torna honesto o DSR do card [Q-1], item 1: 370 trades espalhados por
    12 moedas correlacionadas nao sao 370 observacoes independentes -- dois trades abertos no
    mesmo dia em BTC e ETH sao quase o mesmo evento. Agregar por dia nao conserta a
    correlacao entre moedas, mas para de CONTAR cada perna dela como amostra nova.
    """
    pos = {d: i for i, d in enumerate(grade)}
    fora = [0.0] * len(grade)
    for t in trades:
        i = pos.get(_chave_periodo(t, atribuir))
        if i is not None:
            fora[i] += float(t["pnl"])
    return fora


# ============================ bootstrap ============================
def block_bootstrap_idx(n, block=None, rng=None, n_amostras=None):
    """Indices de um bootstrap CIRCULAR por blocos -- preserva autocorrelacao.

    `block` padrao = max(2, round(n**(1/3))). `block=1` E o bootstrap iid, o que da de graca
    o delta "quanto o iid estava inflado" ([F18], no lugar do Politis-White).

    n_amostras=None devolve um vetor (n,); inteiro devolve (n_amostras, n) -- e a forma
    vetorizada que o Reality Check usa, porque ele precisa do MESMO conjunto de indices para
    todas as configs (e o ponto critico do algoritmo: preserva a correlacao cruzada).
    """
    if n <= 0:
        raise ValueError("n deve ser positivo")
    rng = rng if rng is not None else np.random.default_rng(PADRAO["seed"])
    if block is None:
        block = max(2, int(round(n ** (1 / 3))))
    block = max(1, min(int(block), n))
    a = 1 if n_amostras is None else int(n_amostras)
    k = -(-n // block)                                   # blocos necessarios (ceil)
    inicios = rng.integers(0, n, size=(a, k))
    idx = (inicios[:, :, None] + np.arange(block)[None, None, :]) % n
    idx = idx.reshape(a, k * block)[:, :n]
    return idx[0] if n_amostras is None else idx


def bootstrap_ci(serie, n_boot=2000, modo="iid", eh_serie_temporal=False,
                 block=None, seed=42, alfa=0.05):
    """IC da MEDIA por periodo. Se incluir 0 -> nao significativo.

    [F1] O modo "bloco" EXIGE serie ordenada no tempo, e a guarda abaixo e o achado
    bloqueante da revisao: a lista de trades que chega aqui NAO esta ordenada no tempo -- ela
    e montada concatenando moeda a moeda e depois filtrada por fold, entao a ordem e
    (fold, moeda, tempo). Bootstrap de bloco nessa ordem forma "blocos" que atravessam
    fronteira de moeda e saltam no tempo: ruido estruturado, PIOR que o iid, e com aparencia
    de mais rigor. Por isso a chamada tem de declarar `eh_serie_temporal=True`, que so a
    saida de `pnl_por_periodo` pode honestamente afirmar.
    """
    if modo not in ("iid", "bloco"):
        raise ValueError("modo deve ser 'iid' ou 'bloco'")
    if modo == "bloco" and not eh_serie_temporal:
        raise ValueError("bootstrap de bloco exige serie ordenada no tempo "
                         "(saida de pnl_por_periodo), nao lista de trades")
    a = np.asarray(serie, dtype=float)
    if a.size < 5:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    if modo == "iid":
        idx = rng.integers(0, a.size, size=(n_boot, a.size))
    else:
        idx = block_bootstrap_idx(a.size, block=block, rng=rng, n_amostras=n_boot)
    medias = a[idx].mean(axis=1)
    lo, hi = np.quantile(medias, [alfa / 2, 1 - alfa / 2])
    return (round(float(lo), 4), round(float(hi), 4))


def _boot_medias(matriz, n_boot, block, seed):
    """Reamostragem compartilhada: um unico conjunto de indices por replica, aplicado a
    TODAS as configs. E o ponto critico do Reality Check -- indices por config destruiriam a
    correlacao cruzada entre elas e o quantil nulo sairia errado.

    Devolve (cfgs, f, F_estrela) com F_estrela de forma (n_boot, n_cfgs).
    """
    cfgs = list(matriz.keys())
    M = np.asarray([matriz[c] for c in cfgs], dtype=float)      # (K, T)
    T = M.shape[1]
    rng = np.random.default_rng(seed)
    idx = block_bootstrap_idx(T, block=block, rng=rng, n_amostras=n_boot)   # (B, T)
    F = np.stack([M[k][idx].mean(axis=1) for k in range(M.shape[0])], axis=1)
    return cfgs, M.mean(axis=1), F


def _p_bootstrap(cont, n_boot):
    """[F5] p = (1 + #{>=}) / (B + 1).

    Duas correcoes num numero so: `#{...}/B` pode devolver 0, e p=0 e mentira (com B=2000 a
    resolucao e 5e-4); e a distribuicao bootstrap e discreta, entao empate acontece e o
    comparador tem de ser >=, nao >.
    """
    return (1.0 + float(cont)) / (n_boot + 1.0)


def reality_check(matriz, n_boot=2000, block=5, seed=42):
    """White's Reality Check. H0: a MELHOR das N configs nao tem performance esperada > 0.

    matriz: {config: serie de pnl por periodo} -- todas no MESMO grid e tamanho.
    """
    cfgs, f, F = _boot_medias(matriz, n_boot, block, seed)
    T = len(matriz[cfgs[0]])
    V = math.sqrt(T) * float(f.max())
    Vb = math.sqrt(T) * (F - f[None, :]).max(axis=1)
    return {"p_valor": round(_p_bootstrap(int((Vb >= V).sum()), n_boot), 4),
            "melhor_cfg": cfgs[int(f.argmax())], "V": round(V, 4), "n_cfgs": len(cfgs)}


def spa_hansen(matriz, n_boot=2000, block=5, seed=42):
    """Hansen (2005) SPA_c -- Reality Check com estudentizacao e recentragem por shrinkage.

    [F15] O argumento classico ("o RC sofre com modelos ruins no conjunto") NAO se aplica ao
    GRID de hoje: 6 configs correlacionadas a ~0,95 fazem RC e SPA colapsarem no mesmo teste.
    O motivo real de implementar e outro, e vale aqui: o RC toma o maximo de medias BRUTAS,
    entao a config que mais opera tem mais variancia e domina o maximo, inflando o quantil
    nulo -- e este GRID muda a frequencia de trade em multiplos (min_conv 50 vs 65). A
    estudentizacao conserta isso. Quando RC e SPA derem igual, isso e evidencia de que o grid
    inteiro vale ~1 teste, o que tambem e informacao.
    """
    cfgs, f, F = _boot_medias(matriz, n_boot, block, seed)
    T = len(matriz[cfgs[0]])
    rT = math.sqrt(T)
    omega = (rT * F).std(axis=0, ddof=1)
    omega = np.where(omega <= 0, 1e-12, omega)
    A = 0.25 * omega * math.sqrt(2 * math.log(max(math.log(max(T, 3)), 1.0001)) / T)
    g = np.where(f >= -A, f, 0.0)
    T_spa = max(0.0, float((rT * f / omega).max()))
    Z = rT * (F - g[None, :]) / omega[None, :]
    return {"p_valor": round(_p_bootstrap(int((Z.max(axis=1) >= T_spa).sum()), n_boot), 4),
            "T_spa": round(T_spa, 4)}


def p_valor_config(serie, n_boot=2000, block=5, seed=42):
    """p unilateral de H0: E[media da serie] <= 0, por bootstrap de bloco RECENTRADO.

    [F5] A recentragem e obrigatoria e nao e obvia: quem fizer `#{media* < 0}/B` (percentil da
    distribuicao NAO recentrada) obtem algo parecido, e nao equivalente sob assimetria -- e a
    serie de P&L e assimetrica por construcao, porque `backtest_plataforma.py:81` trunca a
    perda em -valor.
    """
    a = np.asarray(serie, dtype=float)
    if a.size < 5:
        return 1.0
    rng = np.random.default_rng(seed)
    idx = block_bootstrap_idx(a.size, block=block, rng=rng, n_amostras=n_boot)
    f = float(a.mean())
    est = a[idx].mean(axis=1) - f
    return round(_p_bootstrap(int((est >= f).sum()), n_boot), 4)


def fdr_bh(p_valores, q=0.10):
    """Benjamini-Hochberg. Devolve (lista de bools na ordem de entrada, limiar).

    [F16] Implementado e FORA do veredito. Com 6 configs `3 cortes x 2 ADX` sobre os mesmos 12
    ativos as series tem correlacao ~0,9+, os p-valores saem quase identicos e o BH passa
    todos ou nenhum -- nunca discrimina. Uma condicao que nao pode falhar independentemente do
    Reality Check nao e uma condicao. A funcao fica porque vale de verdade no grid de 100+
    configs do Item 2 do `PLANO-REPOS-QUANT.md`, que e para quem esta regua esta sendo feita.
    """
    m = len(p_valores)
    if m == 0:
        return [], 0.0
    ordem = sorted(range(m), key=lambda i: p_valores[i])
    k_max, limiar = 0, 0.0
    for pos, i in enumerate(ordem, start=1):
        if p_valores[i] <= pos / m * q:
            k_max, limiar = pos, pos / m * q
    sobrevive = [False] * m
    for i in ordem[:k_max]:
        sobrevive[i] = True
    return sobrevive, round(limiar, 6)


# ============================ Sharpe deflacionado e poder ============================
def _sr0_esperado(n_obs, n_trials):
    g, e = 0.5772156649, math.e
    return math.sqrt(1.0 / n_obs) * ((1 - g) * _norm_ppf(1 - 1.0 / n_trials) +
                                     g * _norm_ppf(1 - 1.0 / (n_trials * e)))


def _psr(serie, sr_ref):
    """Probabilistic Sharpe Ratio contra um `sr_ref` qualquer (Bailey & Lopez de Prado).
    DSR e este mesmo numero com sr_ref = SR0 esperado do maximo de n_trials."""
    a = np.asarray(serie, dtype=float)
    n = a.size
    if n < 5:
        return {"sr": 0.0, "sr0": round(sr_ref, 4), "p": 0.0, "n": n}
    m, sd = float(a.mean()), float(a.std(ddof=1))
    if sd == 0:
        return {"sr": 0.0, "sr0": round(sr_ref, 4), "p": 0.0, "n": n}
    sr = m / sd
    z = (a - m) / sd
    sk, ku = float((z ** 3).mean()), float((z ** 4).mean())
    denom = math.sqrt(max(1e-9, 1 - sk * sr + (ku - 1) / 4 * sr * sr))
    return {"sr": round(sr, 4), "sr0": round(sr_ref, 4), "n": n,
            "p": round(_norm_cdf((sr - sr_ref) * math.sqrt(n - 1) / denom), 4)}


def probabilistic_sharpe(serie):
    """PSR: prob. de o Sharpe verdadeiro ser > 0, SEM deflacao.

    [F8] E o teste do BLOCO B (decisao): o nulo ali e "o PROCESSO walk-forward, aplicado cego
    para frente, ganha dinheiro?", e esse processo nao foi escolhido como maximo de n_trials
    -- deflacionar ali seria descontar duas vezes.
    """
    r = _psr(serie, 0.0)
    return {"sr": r["sr"], "psr": r["p"], "n": r["n"]}


def deflated_sharpe(serie, n_trials):
    """DSR: prob. de o Sharpe verdadeiro ser > 0 DEPOIS de descontar o vies de ter testado
    n_trials configs. DSR > 0,95 = significativo.

    [Q-1 itens 1 e 3] Duas mudancas de OBJETO, nao de formula, e as duas empurram o numero
    para baixo:

    1. A `serie` e a SERIE DIARIA, nao a lista de trades. `var_sr = 1/n` com n = 370 trades de
       12 moedas correlacionadas trata cada perna como observacao independente e INFLA o DSR
       -- direcao anti-conservadora, a pior possivel num instrumento cujo produto e o
       resultado negativo.
    2. Quem recebe o DSR e a melhor config IN-SAMPLE (BLOCO A), nao o agregado OOS. O nulo do
       DSR e "maximo de N tentativas"; o agregado OOS do walk-forward mistura trades de
       configs DIFERENTES (cada fold escolhe a sua), entao ali nao existe "o maximo de N".
       [F8]

    [F19] O que deliberadamente NAO mudou: `var_sr = 1/n` continua sendo a simplificacao de
    Bailey-LdP, e nao vira variancia empirica entre as 6 configs. Trocar PIORARIA -- 6 configs
    quase identicas tem variancia de SR minuscula, o SR0 encolheria e o DSR INFLARIA. Alem de
    ser incoerente: usar N=100 para cobrir meses de snooping e medir V[SR] num universo de 6
    configs quase iguais mistura dois universos.
    """
    n = len(serie)
    if n < 5:
        return {"sr": 0.0, "sr0": 0.0, "dsr": 0.0, "n": n}
    r = _psr(serie, _sr0_esperado(n, n_trials))
    return {"sr": r["sr"], "sr0": r["sr0"], "dsr": r["p"], "n": n}


def sensibilidade_n_trials(serie, ns=N_TRIALS_TABELA):
    """[F10 / Q-1 item 2] Tabela DSR x n_trials.

    Existe para tirar `n_trials` do lugar de premissa indefensavel. A dependencia e
    LOGARITMICA (SR0 ~ sqrt(2 ln N)): errar por duas ordens de grandeza apenas dobra o SR0.
    Publicada a tabela, "mas e se as tentativas reais foram 10.000?" deixa de ser objecao e
    vira uma linha que qualquer um le.
    """
    return [(n, deflated_sharpe(serie, n)) for n in ns]


# ============================ calibracao [Q-7] ============================
def _binom_cdf(k, n, p):
    """P(X <= k) exata para X ~ Binomial(n, p). `math.comb` e inteiro exato; n aqui e da
    ordem de centenas, entao nao ha razao para aproximar por normal justamente na cauda,
    que e a regiao que o portao le."""
    if k < 0:
        return 0.0
    k = min(int(k), n)
    return float(sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1)))


def banda_binomial(M, alfa=0.05, conf=CONF_BANDA):
    """Faixa de ACEITACAO exata: quantas rejeicoes em `M` paineis sao compativeis com um
    teste de tamanho `alfa`, a `conf` de confianca.

    [Q-7] Isto existe porque a banda era uma STRING no `print`. A rodada do [Q-1] imprimiu
    `taxa de rejeicao a 5% = 0.01 (banda binomial [0,02 ; 0,09])` -- o valor medido ja estava
    fora da banda que a propria linha anunciava, e nada no codigo comparou os dois. Medir e
    nao comparar e o mesmo erro de emitir veredito sem declarar poder.

    Devolve contagens (`k_lo`, `k_hi`) e taxas. Note que a banda literal antiga estava errada
    tambem no numero: para M=200 e alfa=0,05 a faixa exata e [4 ; 16] rejeicoes, ou seja
    [0,02 ; 0,08], nao [0,02 ; 0,09].
    """
    if M <= 0:
        return {"M": M, "alfa": alfa, "conf": conf, "k_lo": 0, "k_hi": 0,
                "taxa_lo": 0.0, "taxa_hi": 0.0}
    cauda = (1.0 - conf) / 2.0
    k_lo = 0
    while k_lo < M and _binom_cdf(k_lo, M, alfa) <= cauda:
        k_lo += 1
    k_hi = M
    while k_hi > 0 and (1.0 - _binom_cdf(k_hi - 1, M, alfa)) <= cauda:
        k_hi -= 1
    return {"M": M, "alfa": alfa, "conf": conf, "k_lo": k_lo, "k_hi": k_hi,
            "taxa_lo": round(k_lo / M, 4), "taxa_hi": round(k_hi / M, 4)}


def ic_clopper_pearson(k, n, conf=CONF_BANDA):
    """IC exato para a proporcao. Serve para dizer o que M paineis NAO conseguem separar --
    com M=200 e 2 rejeicoes o IC vai de ~0,001 a ~0,036, e um alfa efetivo dentro dessa faixa
    move o MDS em muito mais do que a folga do portao. Ou seja: a precisao do diagnostico faz
    parte do diagnostico."""
    if n <= 0:
        return (0.0, 1.0)
    lo, hi = 0.0, 1.0
    if k > 0:                                    # menor p com P(X >= k) >= (1-conf)/2
        a, b = 0.0, 1.0
        for _ in range(200):
            m = (a + b) / 2
            if 1.0 - _binom_cdf(k - 1, n, m) < (1 - conf) / 2:
                a = m
            else:
                b = m
        lo = (a + b) / 2
    if k < n:                                    # maior p com P(X <= k) >= (1-conf)/2
        a, b = 0.0, 1.0
        for _ in range(200):
            m = (a + b) / 2
            if _binom_cdf(k, n, m) > (1 - conf) / 2:
                a = m
            else:
                b = m
        hi = (a + b) / 2
    return (round(lo, 5), round(hi, 5))


def classificar_calibracao(rejeicoes, M, alfa=0.05, conf=CONF_BANDA):
    """CALIBRADO / FORA DA BANDA (abaixo) / FORA DA BANDA (acima) -- em codigo, comparando."""
    b = banda_binomial(M, alfa, conf)
    if M <= 0:
        classe = "NAO MEDIDO"
    elif rejeicoes < b["k_lo"]:
        classe = "FORA DA BANDA (abaixo)"
    elif rejeicoes > b["k_hi"]:
        classe = "FORA DA BANDA (acima)"
    else:
        classe = "CALIBRADO"
    return {"classe": classe, "rejeicoes": int(rejeicoes), "M": M,
            "taxa": round(rejeicoes / M, 4) if M else None, "banda": b,
            "ic_taxa": ic_clopper_pearson(rejeicoes, M, conf)}


def _params_do_painel(matriz):
    """Momentos do painel real que o controle DIRETO tem de reproduzir: tamanho, numero de
    configs, desvio por config, autocorrelacao de lag 1 e correlacao media entre configs."""
    cfgs = list(matriz)
    M0 = np.asarray([matriz[c] for c in cfgs], dtype=float)
    K, T = M0.shape
    sd = M0.std(axis=1, ddof=1)
    sd = np.where(sd <= 0, 1.0, sd)
    a = acf(M0.mean(axis=0).tolist(), lags=1)
    phi = float(min(max(a[0] if a else 0.0, -0.9), 0.9))
    if K > 1:
        C = np.corrcoef(M0)
        rho = float(np.nanmean(C[np.triu_indices(K, 1)]))
    else:
        rho = 0.0
    rho = float(min(max(rho if rho == rho else 0.0, 0.0), 0.999))
    return {"K": K, "T": T, "sd": sd, "phi": phi, "rho": rho}


def _painel_nulo(rng, par, dgp="normal"):
    """Um painel SEM sinal, com media populacional zero -- gerado, nao reamostrado.

    `dgp` e variavel controlada: "normal" e a forma de referencia; "pesada" e a caricatura da
    serie diaria de P&L (maioria dos dias zerada, truncada a esquerda, cauda longa a direita),
    e e trocando UMA pela outra que o [Q-7] identificou a causa da sub-rejeicao."""
    K, T, phi, rho = par["K"], par["T"], par["phi"], par["rho"]
    F = rng.standard_normal(T)
    E = rng.standard_normal((K, T))
    Z = math.sqrt(rho) * F[None, :] + math.sqrt(1 - rho) * E
    if dgp == "pesada":
        X = np.maximum(Z * 40.0 * np.exp(rng.standard_normal((K, T))), -100.0)
        X[rng.random((K, T)) < 0.2] = 0.0
        return (X - X.mean()) * (par["sd"][:, None] / max(X.std(), 1e-9))
    if phi:
        X = np.empty_like(Z)
        X[:, 0] = Z[:, 0]
        for t in range(1, T):
            X[:, t] = phi * X[:, t - 1] + Z[:, t]
        X *= math.sqrt(1 - phi ** 2)
    else:
        X = Z
    return X * par["sd"][:, None]


def controle_nulo_direto(matriz, M=M_CONTROLE_NULO, seed=42, alfa=0.05,
                         n_boot=N_BOOT_CONTROLE, dgp="normal"):
    """[Q-7] O controle que isola a CAUSA -- nao o que mede o alfa desta rodada.

    Cada um dos M paineis vem de um DGP **gerado**, com media populacional zero e forma de
    marginal escolhida (`dgp`), em vez de sair de uma reamostragem dos dados. Isso troca a
    pergunta: `controle_nulo` responde *"qual o alfa efetivo AQUI"* (e para isso precisa da
    marginal real, por isso e nao-parametrico); esta funcao responde *"o que, na forma dos
    dados, move o alfa"* -- e para isso a marginal tem de ser variavel controlada.

    Foi ela que fechou o item 3 do card. Sobre 800-1.200 paineis por celula, T=900, K=6,
    correlacao 0,95 (a forma do `matriz_is` real):

        normal ......................... RC 0,030-0,053 | SPA 0,0488
        cauda pesada + 20% de zeros .... RC 0,0025      | SPA 0,0000

    Isto e, trocando SO a marginal e mantendo tudo o mais, o tamanho cai uma ordem de
    grandeza -- e a linha de baixo bate com o 0,01 que a rodada do [Q-1] mediu sobre o dado
    real, que e a confirmacao de que o DGP nao esta caricaturando o problema para mais. E
    o que descarta as tres suspeitas do card (o `+1` do p, `block=5`, `M` pequeno) e nomeia a
    causa: o maximo de medias BRUTAS sobre cauda pesada infla o quantil nulo -- o mecanismo
    que `spa_hansen` ja descrevia em [F15] sem que ninguem o ligasse a este numero.

    Parametrica de proposito, e so serve para isso: um DGP gaussiano diria "calibrado" para um
    painel cuja marginal real da 0,01. **Por isso ela NAO alimenta o portao** -- quem alimenta
    e `controle_nulo`, que e a unica medida possivel sobre o dado real. O preco dessa escolha
    esta escrito la: o controle aninhado e cego para a propria falha e erra para o lado
    otimista.
    """
    par = _params_do_painel(matriz)
    rng = np.random.default_rng(seed)
    ps = []
    for _ in range(M):
        X = _painel_nulo(rng, par, dgp)
        emb = {k: X[k].tolist() for k in range(par["K"])}
        ps.append(reality_check(emb, n_boot=n_boot, block=PADRAO["block"],
                                seed=int(rng.integers(1, 10 ** 9)))["p_valor"])
    ps = np.asarray(ps)
    rej = int((ps <= alfa).sum())
    fora = classificar_calibracao(rej, M, alfa)
    fora.update({"media_p": round(float(ps.mean()), 4) if M else None,
                 "alfa_efetivo": fora["taxa"],
                 "dgp": {"forma": dgp, "phi": round(par["phi"], 4),
                         "rho": round(par["rho"], 4), "T": par["T"], "K": par["K"]},
                 "n_boot": n_boot})
    return fora


def mds_sharpe(T, poder=0.80, alfa=0.05, ppa=PPA):
    """Sharpe ANUALIZADO minimo detectavel com `poder` a `alfa` unilateral, dado T periodos.

    SR_periodo * sqrt(T) >= z_(1-alfa) + z_(poder)  ->  MDS = (z1+z2)/sqrt(T) * sqrt(ppa)

    Confere com os numeros da revisao: T=180 -> ~3,5 · T=1095 -> ~1,5.
    """
    if T < 2:
        return float("inf")
    z = _norm_ppf(1 - alfa) + _norm_ppf(poder)
    return z / math.sqrt(T) * math.sqrt(ppa)


# ============================ diagnosticos ============================
def acf(serie, lags=10):
    """[F12] Autocorrelacao da serie, lags 1..`lags`.

    Existe para a regua poder dizer "o problema que eu ia consertar nao existia": se a ACF for
    indistinguivel de zero em todos os lags -- desfecho provavel para holds curtos -- entao o
    IC iid nunca esteve inflado, e o bootstrap de bloco nao esta corrigindo nada. Registrar
    isso vale tanto quanto o conserto.
    """
    a = np.asarray(serie, dtype=float)
    n = a.size
    if n < 3:
        return []
    d = a - a.mean()
    den = float((d * d).sum())
    if den == 0:
        return [0.0] * lags
    return [round(float((d[k:] * d[:-k]).sum() / den), 4) for k in range(1, min(lags, n - 1) + 1)]


def banda_acf(T):
    return round(1.96 / math.sqrt(T), 4) if T > 0 else 0.0


def concentracao(serie, por_fold):
    """[F17] Concentracao no nivel de dia e de fold -- DIAGNOSTICO, nunca portao.

    Gatear em "mediana dos folds > 0" seria um teste de ~1 bit: com 5 folds, sob p=0,5,
    5 positivos de 5 dao p = 0,031 (mal passa) e 4/5 dao p = 0,19. Mata bom e aprova ruim ao
    acaso. O que informa de verdade e a dispersao: fracao do lucro bruto vinda dos 5 melhores
    dias e do melhor fold. Dispersao gigante em torno de zero e a assinatura de ruido.
    """
    a = np.asarray(serie, dtype=float)
    bruto = float(a[a > 0].sum())
    top5 = float(np.sort(a)[-5:].sum()) if a.size >= 5 else float(a.sum())
    pnls = [p for _, _, _, p in por_fold]
    tot = sum(pnls)
    melhor = max(pnls, key=abs) if pnls else 0.0
    return {"top5_dias_sobre_lucro_bruto": round(top5 / bruto, 3) if bruto > 0 else None,
            "folds_positivos": sum(1 for p in pnls if p > 0), "folds": len(pnls),
            "maior_fold_sobre_total": round(melhor / tot, 2) if tot else None,
            "pnl_por_fold": [round(p, 0) for p in pnls]}


# ============================ walk-forward ============================
def _valor_criterio(pnls, criterio):
    if not pnls:
        return -1e18
    if criterio == "pnl":
        return sum(pnls)
    if criterio == "pnl_por_trade":
        return sum(pnls) / len(pnls)
    if criterio == "sharpe":
        if len(pnls) < 2:
            return -1e18
        sr = _sr(pnls)
        if sr is not None:
            return sr
        # variancia zero: o Sharpe diverge, e o SINAL do numerador decide de que lado. Sem
        # este ramo, uma config constante e positiva -- Sharpe infinito, a melhor possivel --
        # cairia no mesmo -1e18 de uma config sem trades, e o fold escolheria a pior.
        return 1e18 if sum(pnls) > 0 else -1e18
    raise ValueError(f"criterio desconhecido: {criterio}")


def _tem_ts_saida(por_cfg):
    for tr in por_cfg.values():
        for t in tr:
            return "ts_saida" in t
    return False


def _treino(trades, ini, tr_lim, purga, gap_ms, tem_saida):
    """Trades elegiveis para TREINO na janela [ini, tr_lim).

    `purga` ([F4]/`ITEM1` §3.2, formulacao de Lopez de Prado): so entra trade cujo span de
    label termina antes da borda, isto e `ts_saida < tr_lim`. Sem `ts_saida` a purga nao tem
    como agir -- e o chamador ja foi avisado disso, aqui ela so nao mente.

    `gap_ms` NAO e o embargo de Lopez de Prado, e o nome mudou por isso ([F4]). O embargo de
    LdP existe porque em cross-validation parte do TREINO vem DEPOIS do teste; num
    walk-forward estritamente sequencial nao ha treino apos o teste para embargar, e
    "descartar faixa apos a janela de teste" -- como a proposta original especificava --
    descartaria trades de TESTE, degradando a amostra OOS sem corrigir vies nenhum. O que
    sobra de legitimo e o analogo sequencial: descartar do TREINO os trades nos ultimos h ms
    antes de `tr_lim`, cobrindo a memoria das features (EMA50, Donchian20, o `range(60, ...)`
    de backtest_plataforma.py:39).
    """
    corte = tr_lim - gap_ms
    fora = []
    for t in trades:
        if not (ini <= t["ts"] < corte):
            continue
        if purga and tem_saida and t["ts_saida"] >= tr_lim:
            continue
        fora.append(t)
    return fora


def _nucleo(por_cfg, *, criterio, modo, atribuir, block, purga, gap_pre_teste_ms,
            n_boot, seed, periodo, n_folds=N_FOLDS):
    """Motor do walk-forward. NAO e publico de proposito: quem chama de fora e
    `walk_forward()`, que fixa tudo em `PADRAO` ([F3]). As variantes so chegam aqui por
    `sensibilidade()`, e o resultado delas nunca vira veredito."""
    todos_ts = sorted(t["ts"] for tr in por_cfg.values() for t in tr)
    if len(todos_ts) < 30:
        return None
    t0, t1 = todos_ts[0], todos_ts[-1]
    bordas = [t0 + (t1 - t0) * k / (n_folds + 1) for k in range(n_folds + 2)]
    tem_saida = _tem_ts_saida(por_cfg)

    oos, por_fold = [], []
    for i in range(n_folds):
        tr_lim, te_lim = bordas[i + 1], bordas[i + 2]
        ini = t0 if modo == "expandindo" else bordas[i]
        melhor, melhor_v = None, -1e18
        for cfg, tr in por_cfg.items():
            v = _valor_criterio([t["pnl"] for t in _treino(tr, ini, tr_lim, purga,
                                                           gap_pre_teste_ms, tem_saida)],
                                criterio)
            if v > melhor_v:
                melhor_v, melhor = v, cfg
        teste = [t for t in por_cfg[melhor] if tr_lim <= t["ts"] < te_lim]
        oos += teste
        por_fold.append((i + 1, melhor, len(teste), round(sum(t["pnl"] for t in teste), 2)))

    # Duas grades, e a diferenca nao e detalhe. O BLOCO A (in-sample) olha a timeline
    # INTEIRA, porque cada config foi rodada nela inteira. O BLOCO B (OOS) so existe a partir
    # de bordas[1]: o primeiro segmento e treino puro, nunca foi testado, e nao ha decisao a
    # avaliar ali. Usar a grade inteira para a serie OOS empilharia ~1/6 de dias zerados a
    # esquerda -- dias em que a estrategia NAO estava sendo avaliada, contados como "dia de
    # P&L zero". Isso deflaciona o Sharpe diario e infla o T que alimenta o MDS, ou seja,
    # erra os dois numeros que o [Q-1] veio consertar, e erra em direcoes opostas.
    todos = [t for tr in por_cfg.values() for t in tr]
    grade = grade_de_periodos(todos, atribuir, periodo)
    d0, d1 = int(bordas[1]) // DIA_MS, int(bordas[n_folds + 1]) // DIA_MS
    grade_oos = list(range(d0, d1 + 1))
    serie_oos = pnl_por_periodo(oos, grade_oos, atribuir)
    naive_cfg = max(por_cfg, key=lambda k: _valor_criterio([t["pnl"] for t in por_cfg[k]],
                                                           criterio))
    matriz_is = {c: pnl_por_periodo(tr, grade, atribuir) for c, tr in por_cfg.items()}
    return {"oos": oos, "por_fold": por_fold, "grade": grade, "grade_oos": grade_oos,
            "serie_oos": serie_oos,
            "naive_cfg": naive_cfg, "matriz_is": matriz_is, "tem_ts_saida": tem_saida,
            "cfgs": list(por_cfg.keys()), "block": block, "n_boot": n_boot, "seed": seed}


def walk_forward(gerar_trades, grid, *, n_trials, rotulo="", m_calibracao=M_CONTROLE_NULO):
    """A regua. Roda SEMPRE sob `PADRAO` -- nao ha argumento que mude o criterio ([F3]).

    `gerar_trades(cfg) -> [{"ts": int_ms, "pnl": float, "ts_saida": int_ms (opcional)}, ...]`

    CONTRATO -- o gerador DEVE ser CAUSAL: cada trade so pode usar dado anterior a propria
    entrada. E isso que autoriza rodar a linha do tempo inteira uma vez e depois fatiar por
    timestamp, em vez de re-rodar em cada janela -- o gerador e chamado `len(grid)` vezes, nao
    `len(grid) * n_folds`, e no Item 2/3 do `PLANO-REPOS-QUANT.md` o gerador e caro. Gerador
    que normaliza pela serie inteira quebra a regua em silencio, e nenhum teste daqui pega.

    `n_trials` nao tem default de proposito: quem chama e obrigado a declarar e defender o
    numero de tentativas que o resultado precisa descontar ([F10]).

    `m_calibracao` [Q-7]: quantos paineis nulos medem o alfa efetivo do Reality Check ANTES
    de o veredito ser emitido. Nao ha como desligar -- so como medir com menos paineis, e
    menos paineis alargam a banda, que e a consequencia certa: um diagnostico impreciso
    reclama menos, nao mais. O portao dele esta em `_veredito`.

    Devolve estrutura; quem imprime e `relatorio()` ([F3] §3.7). A separacao existe porque o
    Item 3 compara time bars vs dollar bars e o Item 2 compara frente A vs frente B lado a
    lado -- funcao que so imprime nao se compara.
    """
    por_cfg = {cfg: gerar_trades(cfg) for cfg in grid}
    base = _nucleo(por_cfg, **PADRAO)
    if base is None:
        return {"rotulo": rotulo, "erro": "poucos trades -- sem dados pra walk-forward",
                "veredito": {"classe": "INCONCLUSIVO", "motivo": "amostra insuficiente"}}

    block, n_boot, seed = PADRAO["block"], PADRAO["n_boot"], PADRAO["seed"]
    # [Q-7] A calibracao e computada ANTES do veredito, e o veredito le. Medir e nao comparar
    # foi o defeito que este card veio consertar; deixar a medida fora da estrutura que
    # `_veredito` recebe seria repeti-lo com outra roupa.
    calib = controle_nulo(base["matriz_is"], M=m_calibracao, seed=seed)
    serie = base["serie_oos"]
    T = len(serie)
    T_efetivo = int(sum(1 for x in serie if x != 0.0))

    # ---- BLOCO A: in-sample, familia de configs. DIAGNOSTICO ([F8]) ----
    matriz = base["matriz_is"]
    rc = reality_check(matriz, n_boot=n_boot, block=block, seed=seed)
    spa = spa_hansen(matriz, n_boot=n_boot, block=block, seed=seed)
    ps = [p_valor_config(s, n_boot=n_boot, block=block, seed=seed) for s in matriz.values()]
    sobrevive, limiar = fdr_bh(ps)
    serie_naive = matriz[base["naive_cfg"]]
    ds = deflated_sharpe(serie_naive, n_trials)
    p_sozinha = p_valor_config(serie_naive, n_boot=n_boot, block=block, seed=seed)
    bloco_a = {"reality_check": rc, "spa": spa, "dsr_melhor_is": ds,
               "fdr": {"sobrevivem": sum(sobrevive), "de": len(ps), "limiar": limiar,
                       "p_valores": ps},
               "p_melhor_sozinha": p_sozinha, "serie_naive": serie_naive,
               "naive_cfg": base["naive_cfg"]}

    # ---- BLOCO B: out-of-sample, o PROCESSO. DECISAO ([F8]) ----
    ic_bloco = bootstrap_ci(serie, n_boot=n_boot, modo="bloco", eh_serie_temporal=True,
                            block=block, seed=seed)
    ic_iid = bootstrap_ci(serie, n_boot=n_boot, modo="iid", eh_serie_temporal=True, seed=seed)
    psr = probabilistic_sharpe(serie)
    sr_an = sharpe_anualizado(serie)
    ic_sr = _ic_sharpe_anualizado(serie, n_boot, block, seed)
    mds = mds_sharpe(T)
    # [Q-7] O MDS e calculado com o alfa NOMINAL (0,05). Se o teste rejeitar menos que isso, o
    # poder real e menor e o MDS verdadeiro e MAIOR -- o reportado vira um PISO. So se calcula
    # o piso quando ha medida que o justifique; `None` significa "medido e nao e piso".
    mds_piso, mds_piso_min = None, None
    if calib["classe"] == "FORA DA BANDA (abaixo)" and calib["alfa_efetivo"]:
        mds_piso = round(mds_sharpe(T, alfa=max(calib["alfa_efetivo"], 1e-6)), 3)
        # o piso MENOS exigente compativel com a imprecisao do diagnostico: alfa no topo do
        # IC. E ele que o portao le, para que a guarda so dispare quando a largura do IC nao
        # puder explicar o achado.
        mds_piso_min = round(mds_sharpe(T, alfa=max(calib["ic_taxa"][1], 1e-6)), 3)
    bloco_b = {"T": T, "T_efetivo": T_efetivo, "ic_bloco": ic_bloco, "ic_iid": ic_iid,
               "psr": psr, "sharpe_anualizado": None if sr_an is None else round(sr_an, 3),
               "ic_sharpe_anualizado": ic_sr, "mds": round(mds, 3), "mds_piso": mds_piso,
               "mds_piso_min": mds_piso_min,
               "concentracao": concentracao(serie, base["por_fold"]),
               "acf": acf(serie), "banda_acf": banda_acf(T)}

    res = {"rotulo": rotulo, "n_trials": n_trials, "bloco_a": bloco_a, "bloco_b": bloco_b,
           "calibracao": calib,
           "padrao": dict(PADRAO), "purga_ativa": PADRAO["purga"] and base["tem_ts_saida"],
           "purga_motivo": ("" if base["tem_ts_saida"] else
                            "o gerador nao grava ts_saida nos trades"),
           "sensibilidade_n_trials": sensibilidade_n_trials(serie_naive),
           # o numero antigo, preservado para o contraste do relatorio
           "dsr_legado_trades": deflated_sharpe([t["pnl"] for t in base["oos"]], n_trials),
           "por_cfg": por_cfg}
    res.update({k: base[k] for k in ("oos", "por_fold", "serie_oos", "naive_cfg",
                                     "matriz_is", "grade", "grade_oos")})
    res["veredito"] = _veredito(res)
    return res


def _ic_sharpe_anualizado(serie, n_boot, block, seed):
    """[F7] IC do Sharpe ANUALIZADO por bootstrap de bloco. E o numero que diz o que o teste
    NAO exclui -- e a razao de o veredito negativo atual ser mais fraco do que o projeto
    acredita: revertendo o IC registrado da tendencia, o limite superior admite Sharpe
    anualizado ~1,9, que seria uma estrategia excelente."""
    a = np.asarray(serie, dtype=float)
    if a.size < 5:
        return (None, None)
    rng = np.random.default_rng(seed)
    idx = block_bootstrap_idx(a.size, block=block, rng=rng, n_amostras=n_boot)
    am = a[idx]
    sd = am.std(axis=1, ddof=1)
    ok = sd > 0
    if not ok.any():
        return (None, None)
    srs = am.mean(axis=1)[ok] / sd[ok] * math.sqrt(PPA)
    lo, hi = np.quantile(srs, [0.025, 0.975])
    return (round(float(lo), 3), round(float(hi), 3))


def _veredito(res):
    """Tres respostas, e a terceira e a que o [Q-1] acrescenta. O [Q-7] poe um portao ANTES
    das tres: se o instrumento nao estiver calibrado, nao ha resposta a dar.

    Ordem importa: o portao de PODER vem ANTES do teste de edge ([F14]). Um instrumento sem
    poder emite "nao tem edge" tanto quando nao tem quanto quando nao da pra saber, e as duas
    frases sao a mesma no relatorio antigo. Enquanto o MDS estiver acima de `MDS_LIMITE`, a
    resposta honesta e INCONCLUSIVO -- e e ela que vai impedir o Item 2 (portoes restritivos,
    poucos trades) de virar falso negativo por amostra pequena.

    O que decide e o BLOCO B ([F8]): o nulo dele e "o processo walk-forward, aplicado cego
    para frente, ganha dinheiro?". O FDR fica FORA ([F16]) porque com 6 configs correlacionadas
    a ~0,9 ele passa todas ou nenhuma e nunca discrimina.
    """
    b, a = res["bloco_b"], res["bloco_a"]
    cal = res.get("calibracao") or {}
    # [Q-7] O portao de poder passa a ler o MDS **corrigido pelo alfa efetivo**, e le a ponta
    # MENOS exigente do IC dele: so bloqueia quando nem a imprecisao do controle nulo explica
    # a falta de poder. O MDS nominal continua valendo sozinho quando nao ha medida de alfa.
    piso_min = b.get("mds_piso_min")
    if piso_min and piso_min > MDS_LIMITE:
        return {"classe": "INCONCLUSIVO",
                "motivo": (f"instrumento sem poder: o MDS nominal {b['mds']} e um PISO -- com "
                           f"o alfa efetivo medido ({cal.get('alfa_efetivo')}, IC "
                           f"{cal.get('ic_taxa')}) ele vale ao menos {piso_min}, acima do "
                           f"limite {MDS_LIMITE}")}
    if b["mds"] > MDS_LIMITE or b["T_efetivo"] < T_EFETIVO_MINIMO:
        return {"classe": "INCONCLUSIVO",
                "motivo": (f"instrumento sem poder: MDS = {b['mds']} "
                           f"(limite {MDS_LIMITE}), T_efetivo = {b['T_efetivo']} "
                           f"(minimo {T_EFETIVO_MINIMO})")}
    # [Q-7] Portao de CALIBRACAO, DEPOIS do de poder e ANTES do de edge. Depois do poder
    # porque num painel curto os dois disparam e o MDS e a causa, nao o sintoma -- a mensagem
    # util e "T pequeno demais". Antes do edge porque a condicao de EDGE le o Reality Check
    # (`reality_check <= 0,05`, logo abaixo): emitir EDGE com o teste super-rejeitando e
    # decidir com a regua que este card veio conferir.
    #
    # A direcao e ASSIMETRICA de proposito. Super-rejeitar torna o EDGE facil demais e
    # bloqueia. Sub-rejeitar e conservador, nao bloqueia, e vira a marca de PISO no MDS --
    # que e a outra metade da correcao do card.
    if cal.get("ic_taxa") and cal["ic_taxa"][0] > ALFA_TETO_PORTAO:
        return {"classe": "INCONCLUSIVO",
                "motivo": (f"instrumento descalibrado: o controle nulo direto rejeitou "
                           f"{cal['rejeicoes']} de {cal['M']} paineis SEM sinal "
                           f"(taxa {cal['taxa']}, IC {cal['ic_taxa']}), e o piso desse IC "
                           f"passa de {ALFA_TETO_PORTAO} -- o dobro do alfa nominal")}
    if b["ic_bloco"][0] > 0 and b["psr"]["psr"] > 0.95 and a["reality_check"]["p_valor"] <= 0.05:
        return {"classe": "EDGE",
                "motivo": (f"IC-bloco {b['ic_bloco']} > 0, PSR {b['psr']['psr']} > 0,95, "
                           f"Reality Check p = {a['reality_check']['p_valor']} <= 0,05")}
    return {"classe": "SEM_EVIDENCIA",
            "motivo": (f"IC-bloco {b['ic_bloco']} inclui 0 ou PSR {b['psr']['psr']} <= 0,95 "
                       f"ou RC p = {a['reality_check']['p_valor']} > 0,05"),
            "nao_exclui": b["ic_sharpe_anualizado"], "mds": b["mds"],
            "mds_piso": b.get("mds_piso")}


def sensibilidade(res):
    """[F3] Roda as variantes de criterio, modo e block e devolve o veredito de cada uma.

    Imprime SEMPRE, todas de uma vez, como diagnostico -- nunca como escolha de quem chama. E
    o que impede a variante virar grau de liberdade: se o veredito nao muda em nenhuma delas,
    a escolha do `PADRAO` nao esta segurando a conclusao; se muda, isso e informacao de
    primeira ordem e tem de aparecer no relatorio, nao ficar guardada.
    """
    por_cfg = res["por_cfg"]
    n_trials = res["n_trials"]
    fora = {"criterio": [], "modo": [], "atribuir": [], "block": []}
    for c in CRITERIOS:
        r = _nucleo(por_cfg, **{**PADRAO, "criterio": c})
        fora["criterio"].append((c, _resumo_variante(r, n_trials)))
    for m in MODOS:
        r = _nucleo(por_cfg, **{**PADRAO, "modo": m})
        fora["modo"].append((m, _resumo_variante(r, n_trials)))
    # `atribuir` so entra aqui depois que o gerador passou a gravar `ts_saida`. Enquanto o
    # campo faltava, "saida" nem era rodavel; agora que e, ele NAO vira default em silencio --
    # vira linha de diagnostico ao lado de "entrada", que e onde a revisao (F3/`ITEM1` §3.3)
    # pode ser conferida sem que o veredito passe a depender da escolha.
    if _tem_ts_saida(por_cfg):
        for at in ATRIBUIR:
            r = _nucleo(por_cfg, **{**PADRAO, "atribuir": at})
            fora["atribuir"].append((at, _resumo_variante(r, n_trials)))
    base = _nucleo(por_cfg, **PADRAO)
    for bl in BLOCKS:
        s = base["serie_oos"]
        fora["block"].append((bl, bootstrap_ci(s, n_boot=PADRAO["n_boot"], modo="bloco",
                                               eh_serie_temporal=True, block=bl,
                                               seed=PADRAO["seed"])))
    return fora


def _resumo_variante(r, n_trials):
    if r is None:
        return None
    s = r["serie_oos"]
    ic = bootstrap_ci(s, n_boot=PADRAO["n_boot"], modo="bloco", eh_serie_temporal=True,
                      block=PADRAO["block"], seed=PADRAO["seed"])
    return {"trades": len(r["oos"]), "pnl": round(sum(t["pnl"] for t in r["oos"]), 0),
            "ic_bloco": ic, "psr": probabilistic_sharpe(s)["psr"],
            "sharpe_anual": None if sharpe_anualizado(s) is None
            else round(sharpe_anualizado(s), 2)}


def controle_nulo(res, M=M_CONTROLE_NULO, seed=42, alfa=0.05, n_boot=N_BOOT_CONTROLE):
    """[F9] Alfa EFETIVO do BLOCO A sobre ESTES dados: permuta em blocos a serie diaria de
    cada config -- preservando autocorrelacao, o alinhamento entre configs e, o que mais
    importa, a MARGINAL --, centra, e faz o Reality Check rodar M vezes sobre painel sem
    sinal. Cobre selecao, agregacao diaria, Reality Check e o proprio veredito.

    **[Q-7] O que a investigacao achou, e nao era o que o card supunha.**

    A rodada do [Q-1] deu `taxa de rejeicao a 5% = 0,01` contra uma banda impressa como texto,
    e ninguem comparou os dois numeros. Comparando -- e depois procurando a causa com o
    controle DIRETO (`controle_nulo_direto`, paineis gerados de DGP conhecido, M=600 cada):

    | marginal do painel nulo     | RC, controle DIRETO    | Hansen SPA, direto     |
    |-----------------------------|------------------------|------------------------|
    | normal                      | 0,030-0,053            | 0,049 [0,035 ; 0,066]  |
    | cauda pesada + 20% de zeros | **0,0025 [0 ; 0,009]**  | **0,0000 [0 ; 0,005]** |

    (paineis com a forma do `matriz_is` real -- T=900, K=6, correlacao 0,95 --, entre 800 e
    1.200 paineis por celula; a faixa da linha "normal" e a dispersao entre sementes e cobre o
    nominal de 0,05.)

    A sub-rejeicao e REAL e a causa e a **forma da marginal**, nao as tres suspeitas do card:

      * nao e o `p = (1+#)/(B+1)` [F5] -- ele esta presente igual na linha "normal", que fica
        compativel com o nominal. Se o `+1` empurrasse o p para cima o bastante para importar,
        a marginal normal cairia junto;
      * nao e `block=5` -- idem: o mesmo `block` roda nas duas linhas;
      * `M=200` e pequeno, mas isso e imprecisao, nao vies: com 2 rejeicoes o IC exato vai de
        0,001 a 0,036, e a decisao tem de respeitar essa largura -- e respeita, ver `_veredito`.

    O mecanismo ja estava escrito neste arquivo, em `spa_hansen`, [F15]: *"o RC toma o maximo
    de medias BRUTAS, entao a config que mais opera tem mais variancia e domina o maximo,
    inflando o quantil nulo"*. Quantil nulo inflado = sub-rejeicao. Numa serie diaria de P&L
    -- zerada na maioria dos dias, truncada em `-valor` a esquerda e com cauda longa a direita
    -- essa inflacao e grande. O que ninguem tinha feito era ligar esse comentario ao numero
    do controle nulo.

    **E a estudentizacao NAO conserta**: na mesma marginal o SPA rejeitou 0 de 800, ainda mais
    longe do nominal que o RC, porque o denominador dele tambem e inflado pela cauda. Entao
    "trocar RC por SPA" nao e a saida, e registrar isso poupa o proximo card a descoberta.

    **E ha um degrau a mais, que muda como este numero deve ser lido.** Rodando ESTE controle
    (o aninhado) sobre um painel sorteado daquele mesmo DGP de cauda pesada, ele devolve
    0,040 -- perto do nominal, enquanto o controle direto, sobre o mesmo DGP, devolve 0,0025.
    Os dois discordam por uma razao estrutural: aqui os dois niveis usam a MESMA distribuicao
    empirica, entao o erro do bootstrap aparece nos dois lados e se cancela. **Este controle e
    cego para a propria falha.** Consequencia para a leitura: o 0,01 medido sobre o dado real
    e uma estimativa OTIMISTA do alfa efetivo -- o valor verdadeiro tende a ser ainda menor, e
    portanto o PISO do MDS calculado com ele e um piso frouxo.

    Isso nao o desqualifica como insumo do portao: e a unica medida que se pode fazer com o
    dado real (o controle direto precisa de um DGP inventado), e ela erra para o lado que
    torna a guarda mais dificil de disparar, que e o lado permitido.

    **E "frouxo" tem de vir com o tamanho da frouxidao, que e DESCONHECIDO -- essa parte
    tambem e entrega.** O card do [Q-7] fez a conta com alfa = 0,01 e concluiu que o MDS de
    1,576 viraria ~1,92, deixando 4% de folga ate o `MDS_LIMITE = 2,0`. Duas coisas derrubam
    essa tranquilidade:

      * a conta com o `mds_sharpe` DESTE arquivo nao da 1,92 e sim **2,008** -- a razao entre
        alfa 0,01 e alfa 0,05 e 1,274, nao ~1,22 (`test_mds_vira_PISO_quando_o_teste_sub_rejeita`
        fixa os dois numeros). Ja com o alfa OTIMISTA o MDS encosta do OUTRO lado do limite: a
        folga nao cai para 4%, ela deixa de existir;
      * e o alfa verdadeiro e MENOR que 0,01. Quanto menor, ninguem sabe. O controle direto
        sobre um DGP com aquela marginal deu 0,0025, uma ordem de grandeza abaixo -- mas esse
        DGP e uma caricatura escolhida a mao, e tratar o numero dele como medida do dado real
        seria trocar um chute por outro.

    O que se pode afirmar, entao, e so isto: **o MDS reportado e um piso, o piso e frouxo, e a
    distancia ate o valor verdadeiro nao foi medida.** Fechar essa distancia exige o controle
    nulo COMPLETO do F9 -- M geradores de sinal aleatorio pelo pipeline inteiro --, que
    continua pendente por relogio. Quem escrever o veredito do M4 escreve isso, e nao a folga.

    **Consequencia, e ela e a metade que o card acertou:** o MDS e calculado supondo alfa
    nominal 0,05. Com alfa efetivo menor o poder real e menor e o minimo detectavel e MAIOR --
    **o MDS reportado e um PISO**, e o relatorio passa a dizer isso na linha dele.

    **Cada um dos M paineis e um embaralhamento INDEPENDENTE do painel real**, centrado pela
    media do real -- nao M reamostragens de um painel intermediario. A distincao custou uma
    tentativa errada nesta sessao e vale escrever: centrar por uma media que nao e a da
    distribuicao que gerou o painel deixa drift residual no nulo, e o Reality Check o detecta
    corretamente -- a taxa de rejeicao explodiu para 0,225 num painel gaussiano. O painel nulo
    tem de ser sorteado do dado e centrado pelo dado, uma vez so. Como os M sorteios sao
    independentes entre si, a banda binomial vale.

    O que continua NAO coberto (a divida original do F9): M geradores de SINAL aleatorio
    passando pelo pipeline INTEIRO, o que validaria tambem `scoring.pontuar`, o modelo de custo
    e o pooling de moedas. O bloqueio de territorio caiu -- `backtest_ativo` aceita `sinal_fn`
    desde o [P1-10] --, o que resta e relogio: uma passada do grid leva ~13 min e M=200
    passadas nao cabem numa rodada. Fica registrado como divida, nao como feito.
    """
    matriz = res["matriz_is"] if isinstance(res, dict) and "matriz_is" in res else res
    cfgs = list(matriz)
    M0 = np.asarray([matriz[c] for c in cfgs], dtype=float)
    T = M0.shape[1]
    medias = M0.mean(axis=1)
    rng = np.random.default_rng(seed)
    ps = []
    for _ in range(M):
        idx = block_bootstrap_idx(T, block=PADRAO["block"], rng=rng)
        emb = {c: (M0[k][idx] - medias[k]).tolist() for k, c in enumerate(cfgs)}
        ps.append(reality_check(emb, n_boot=n_boot, block=PADRAO["block"],
                                seed=int(rng.integers(1, 10 ** 9)))["p_valor"])
    ps = np.asarray(ps)
    rej = int((ps <= alfa).sum())
    fora = classificar_calibracao(rej, len(ps), alfa)
    fora.update({"taxa_rejeicao_5pct": round(float((ps <= alfa).mean()), 4),
                 "alfa_efetivo": fora["taxa"],
                 "media_p": round(float(ps.mean()), 4),
                 "ks_max": round(float(np.abs(np.sort(ps) -
                                              (np.arange(1, len(ps) + 1) / len(ps))).max()), 4),
                 "ks_critico": round(1.36 / math.sqrt(len(ps)), 4) if len(ps) else None,
                 "n_boot": n_boot})
    return fora


# ============================ a estrategia de tendencia ============================
def _chave(g):
    return (g["min_conv"], g["adx_min"])


def gerador_tendencia(dfs, estrategia, funding_8h, saida_kw=None):
    """Fabrica um `gerar_trades(cfg)` causal para a estrategia da plataforma.

    Causal por construcao: `backtest_ativo` pontua no candle FECHADO i e executa no open de
    i+1, e os canais usam `.shift(1)` -- nada olha para a frente. E o que autoriza gerar a
    timeline inteira uma vez e fatiar depois.

    `saida_kw` [P1-10] escolhe a POLITICA DE SAIDA (`saida`, `trailing_dist`,
    `trailing_k_atr`). Ele nao toca em nada da entrada: os portoes de conviccao, ADX e
    n_fatores continuam os mesmos nas tres politicas, que e o que mantem a comparacao com um
    fator so.
    """
    kw = dict(saida_kw or {})

    def gerar(cfg):
        mc, ax = cfg
        tr = []
        for c in COINS:
            try:
                tr += backtest_ativo(c, mc, VALOR, LEV, estrategia=estrategia, df=dfs[c],
                                     adx_min=ax, funding_8h=funding_8h, **kw)
            except Exception:
                pass
        return tr
    return gerar


# [P1-10] As politicas que o card manda comparar, na mesma regua e nas mesmas janelas.
#
# A e a do backtest e NUNCA rodou ao vivo. B e o que gerou o historico local
# (`auto_fechar_saida=1` com `trailing_ativo=0`). C e o default de HOJE (`db.py:95-96`), e a
# quarta linha e o item 3 do card: a mesma politica C com a distancia em unidade de ATR, para
# que a saida deixe de ser cega a volatilidade do ativo e a alavancagem.
POLITICAS_M4 = (
    ("A stop+flip de regime", {"saida": "regime"}),
    ("B auto-saida", {"saida": "auto"}),
    ("C trailing 2% fixo", {"saida": "trailing", "trailing_dist": 0.02}),
    ("C trailing 3xATR", {"saida": "trailing", "trailing_k_atr": 3.0}),
)


def baixar_paineis():
    """As 12 moedas, preparadas uma vez. Separado porque a comparacao de politicas roda quatro
    walk-forwards sobre EXATAMENTE os mesmos dados -- baixar de novo por politica nao seria so
    lento, seria outra janela se a rodada virasse o dia."""
    print(f"baixando {len(COINS)} moedas ({TF}, {DIAS}d)...", flush=True)
    return {c: scoring.preparar(dados.baixar_ohlcv(c, TF, dias=DIAS)) for c in COINS}


def walk_forward_tendencia(estrategia="tendencia", funding_8h=FUNDING_8H, com_contraste=True,
                           saida_kw=None, dfs=None, rotulo_extra=""):
    """Roda a regua na estrategia da plataforma e imprime. Mantem `python -m pesquisa.validacao`
    fazendo o que fazia -- so que sob o instrumento novo."""
    dfs = dfs if dfs is not None else baixar_paineis()
    grid = [_chave(g) for g in GRID]
    rot = f"{estrategia} | {TF} {DIAS}d | {LEV}x{rotulo_extra}"

    print(f"rodando {len(grid)} configs x {len(COINS)} moedas...", flush=True)
    res = walk_forward(gerador_tendencia(dfs, estrategia, funding_8h, saida_kw), grid,
                       n_trials=N_TRIALS, rotulo=rot)
    relatorio(res)

    if com_contraste and funding_8h:
        # [P2-10] MESMO walk-forward com funding zerado -- que e o que este script media antes,
        # por usar o default do backtest_ativo. A diferenca e o carry que a pesquisa nao pagava.
        print("\nrodando o contraste sem funding...", flush=True)
        r0 = walk_forward(gerador_tendencia(dfs, estrategia, 0.0, saida_kw), grid,
                          n_trials=N_TRIALS, rotulo="funding 0")
        p1 = sum(t["pnl"] for t in res["oos"])
        p0 = sum(t["pnl"] for t in r0["oos"])
        lado = ("net-SHORT no periodo: recebeu mais do que pagou" if p1 - p0 > 0
                else "net-LONG no periodo: pagou o carry")
        print(f"\nCOM x SEM funding (mesmo walk-forward): R${p1:+.0f} pagando "
              f"{funding_8h * 100:.4f}%/8h  x  R${p0:+.0f} com funding 0")
        print(f"  -> efeito do carry no P&L OOS: R${p1 - p0:+.0f} -- {lado}.")
    return res


def comparar_politicas(politicas=POLITICAS_M4, funding_8h=FUNDING_8H, dfs=None):
    """[P1-10] A x B x C na MESMA regua, nas MESMAS janelas, sobre os MESMOS dados.

    Rodar (da RAIZ do repo):  python -m pesquisa.validacao politicas

    O contraste de funding do [P2-10] fica FORA daqui de proposito: ele dobra o tempo de cada
    politica e mede outra coisa (o carry), que ja esta registrado para a politica A. Aqui o
    unico fator que varia e a saida.

    A tabela final e comparativa; o veredito de cada politica sai do relatorio dela, sob o
    `PADRAO` travado. Nao existe "a melhor politica pelo P&L": P&L nao e criterio nesta casa
    ([F3]) e a coluna esta na tabela como diagnostico, ao lado do que decide.
    """
    dfs = dfs if dfs is not None else baixar_paineis()
    fora = []
    for nome, kw in politicas:
        print(f"\n{'=' * 78}\nPOLITICA: {nome}   {kw}\n{'=' * 78}", flush=True)
        r = walk_forward_tendencia(funding_8h=funding_8h, com_contraste=False,
                                   saida_kw=kw, dfs=dfs, rotulo_extra=f" | saida: {nome}")
        fora.append((nome, kw, r))
    relatorio_politicas(fora)
    return fora


def relatorio_politicas(resultados):
    """A tabela que o `VEREDITO-M4.md` cola. Uma linha por politica, o veredito na ultima
    coluna -- porque tabela sem veredito nao e resposta ([P1-10], criterio de aceite 4)."""
    print(f"\n{'=' * 110}")
    print("COMPARACAO DE POLITICAS DE SAIDA -- mesma regua, mesmas janelas, mesmos dados "
          "[P1-10]")
    print("=" * 110)
    print(f"{'politica':<24}{'trades':>7}{'win%':>7}{'PnL OOS':>10}{'Sharpe an.':>11}"
          f"{'IC95% Sharpe':>22}{'DSR':>8}{'MDS':>7}  veredito")
    for nome, _kw, r in resultados:
        if "erro" in r:
            print(f"{nome:<24}{'--':>7}  {r['erro']}")
            continue
        b, a = r["bloco_b"], r["bloco_a"]
        so = stats([t["pnl"] for t in r["oos"]])
        piso = " (piso)" if b.get("mds_piso") else ""
        print(f"{nome:<24}{so['n']:>7}{so['win']:>7.1f}{so['pnl']:>+10.0f}"
              f"{str(b['sharpe_anualizado']):>11}{str(b['ic_sharpe_anualizado']):>22}"
              f"{a['dsr_melhor_is']['dsr']:>8}{b['mds']:>7}{piso}  {r['veredito']['classe']}")
    print("\nmotivos de saida por politica (o que de fato fechou os trades):")
    for nome, _kw, r in resultados:
        if "erro" in r:
            continue
        conta = {}
        for t in r["oos"]:
            conta[t["motivo"]] = conta.get(t["motivo"], 0) + 1
        linha = " | ".join(f"{k}: {v}" for k, v in sorted(conta.items(), key=lambda x: -x[1]))
        print(f"   {nome:<24} {linha}")
    print("\nO P&L esta na tabela como DIAGNOSTICO. O que decide e o veredito da ultima "
          "coluna,\nemitido sob o PADRAO travado -- soma bruta de P&L favorece quem mais "
          "opera [F3].")


# ============================ relatorio ============================
def relatorio(res):
    """[F8] Dois blocos ROTULADOS, nao "4 condicoes".

    Os testes se aplicam a objetos diferentes e empilha-los como um checklist de quatro itens
    confunde nulos: o Reality Check testa "a melhor de N configs, IN-SAMPLE"; o agregado OOS
    mistura trades de configs diferentes (cada fold escolhe a sua), entao ali o objeto e o
    PROCESSO de selecao, nao uma estrategia. Bloco A informa. Bloco B decide.
    """
    if "erro" in res:
        print(res["erro"])
        return
    a, b = res["bloco_a"], res["bloco_b"]
    p = res["padrao"]
    print(f"\n=== WALK-FORWARD: {res['rotulo']} | {len(res['matriz_is'])} configs "
          f"x {N_FOLDS} folds ===")
    print(f"PADRAO (travado): criterio={p['criterio']} modo={p['modo']} "
          f"atribuir={p['atribuir']} block={p['block']} n_boot={p['n_boot']} seed={p['seed']}")
    print(f"purga: {'ATIVA' if res['purga_ativa'] else 'INATIVA -- ' + res['purga_motivo']}")
    print(f"n_trials = {res['n_trials']} (PISO CONTADO, nao estimativa)")
    cal = res.get("calibracao")
    if cal:
        bb = cal["banda"]
        print(f"calibracao [Q-7]: o controle nulo rejeitou {cal['rejeicoes']}/{cal['M']} "
              f"paineis sem sinal (taxa {cal['taxa']}) -> {cal['classe']}")
        print(f"   banda de aceitacao CALCULADA (binomial exata, alfa=0,05, {bb['conf']:.0%}): "
              f"[{bb['k_lo']} ; {bb['k_hi']}] rejeicoes = [{bb['taxa_lo']} ; {bb['taxa_hi']}] "
              f"| IC da taxa medida: {cal['ic_taxa']}")

    print(f"\n{'fold':>5}  {'config (conv/adx)':>18}  {'trades':>7}  {'pnl OOS':>9}")
    for f, cfg, n, pn in res["por_fold"]:
        print(f"{f:>5}  {str(cfg):>18}  {n:>7}  R${pn:>+7.0f}")
    so = stats([t["pnl"] for t in res["oos"]])
    print(f"\nOOS agregado: {so['n']} trades | win {so['win']}% | PnL R${so['pnl']:+.0f}")
    print(f"  serie diaria da JANELA OOS: {b['T']} dias ({b['T_efetivo']} com P&L nao-nulo) "
          f"-- o 1o dos {N_FOLDS + 1} segmentos e treino puro e nao entra")

    print("\n-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.")
    print("   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO")
    rc, spa = a["reality_check"], a["spa"]
    print(f"   White's Reality Check (N={rc['n_cfgs']} configs, {p['n_boot']} bootstraps de "
          f"bloco): p = {rc['p_valor']}")
    print(f"   Hansen SPA (estudentizado):                                     p = {spa['p_valor']}")
    print(f"   p da melhor config SOZINHA (sem multiplicidade):                p = {a['p_melhor_sozinha']}")
    print(f"     -> o grid custou {round(rc['p_valor'] - a['p_melhor_sozinha'], 3)} de "
          f"multiplicidade. [F12]")
    d = a["dsr_melhor_is"]
    print(f"   DSR da melhor config in-sample {a['naive_cfg']} sobre a SERIE DIARIA "
          f"({d['n']} dias): DSR = {d['dsr']}")
    print(f"     (sr={d['sr']} vs sr0_esperado={d['sr0']} para n_trials={res['n_trials']})")
    dl = res["dsr_legado_trades"]
    print(f"   [contraste] o numero ANTIGO -- DSR sobre a lista de {dl['n']} trades OOS: "
          f"{dl['dsr']}")
    print(f"     -> objeto errado duas vezes: trades correlacionados contados como "
          f"independentes, e o agregado OOS em vez da melhor config in-sample. [Q-1 1 e 3]")
    fdr = a["fdr"]
    print(f"   FDR (Benjamini-Hochberg, q=0,10): {fdr['sobrevivem']} de {fdr['de']} configs "
          f"sobrevivem -- FORA do veredito, nao-informativo em N={fdr['de']} [F16]")

    print("\n   sensibilidade a n_trials (a dependencia e LOGARITMICA -- [F10]):")
    print(f"   {'n_trials':>9}  {'sr0':>8}  {'DSR':>7}")
    for n, dd in res["sensibilidade_n_trials"]:
        print(f"   {n:>9}  {dd['sr0']:>8}  {dd['dsr']:>7}")

    print("\n-- BLOCO B -- out-of-sample, o PROCESSO. Nulo: E[pnl do walk-forward] <= 0.")
    print("   pergunta: 'o procedimento, aplicado cego pra frente, ganha dinheiro?'  papel: DECISAO")
    print(f"   IC95% da media/dia -- bloco (block={p['block']}): {b['ic_bloco']}   "
          f"iid: {b['ic_iid']}")
    print(f"   PSR (sem deflacao, SR*=0): {b['psr']['psr']}  (sr/dia = {b['psr']['sr']})")
    print(f"   Sharpe ANUALIZADO: {b['sharpe_anualizado']}   IC95% (bloco): "
          f"{b['ic_sharpe_anualizado']}")
    piso = b.get("mds_piso")
    marca = " -- e um PISO" if piso else ""
    print(f"   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, "
          f"T={b['T']}): {b['mds']}{marca}")
    if piso:
        # [Q-7] So aparece quando o controle nulo mediu sub-rejeicao. O MDS e calculado com
        # o alfa NOMINAL; com alfa efetivo menor o poder real e menor e o minimo detectavel e
        # MAIOR. Reportar so o nominal seria publicar poder que o teste nao tem.
        cl = res["calibracao"]
        print(f"     -> alfa efetivo medido {cl['alfa_efetivo']} (nao 0,05), IC {cl['ic_taxa']}: "
              f"com ele o MDS vale {piso}; com a ponta MENOS exigente do IC, "
              f"{b.get('mds_piso_min')}. Limite = {MDS_LIMITE}.")
        print(f"        O numero da linha acima e um PISO -- e o portao le "
              f"{b.get('mds_piso_min')}, para nao bloquear por imprecisao do diagnostico.")
    print(f"     -> comparacao de poder: T=180 dias daria MDS {round(mds_sharpe(180), 2)}; "
          f"T=1095 daria {round(mds_sharpe(1095), 2)}. [F6]")
    c = b["concentracao"]
    print(f"   concentracao [F17]: top-5 dias = {c['top5_dias_sobre_lucro_bruto']} do lucro "
          f"bruto | folds positivos {c['folds_positivos']}/{c['folds']} | "
          f"maior fold = {c['maior_fold_sobre_total']} do total")
    print(f"     (com 5 folds, 5 positivos de 5 dao p=0,031 e 4/5 dao p=0,19 -- diagnostico, "
          f"nunca portao)")
    print(f"   ACF do P&L diario, lags 1..{len(b['acf'])}: {b['acf']}")
    print(f"     banda +-1,96/sqrt(T) = +-{b['banda_acf']} -- fora dela = autocorrelacao real "
          f"[F12]")

    v = res["veredito"]
    print()
    if v["classe"] == "INCONCLUSIVO":
        print(f"=> VEREDITO: INCONCLUSIVO -- {v['motivo']}.")
        print("   A regua NAO diz 'sem edge': diz que nao consegue medir. Sao coisas "
              "diferentes e o [Q-1] existe para separar as duas. [F14]")
    elif v["classe"] == "EDGE":
        print(f"=> VEREDITO: edge SOBREVIVE ({v['motivo']}). Vale calibrar/operar.")
    else:
        print(f"=> VEREDITO: SEM EVIDENCIA DE EDGE ({v['motivo']}).")
        ne = v.get("nao_exclui")
        if ne and ne[1] is not None:
            print(f"   IC95% do Sharpe anualizado: [{ne[0]} ; {ne[1]}].")
            piso = v.get("mds_piso")
            print(f"   O teste NAO exclui edges de Sharpe ate {ne[1]} -- MDS = {v['mds']}"
                  f"{f' (PISO; com o alfa efetivo medido, {piso})' if piso else ''}. "
                  f"Ausencia de evidencia nao e evidencia de ausencia. [F7]")


def relatorio_controle_nulo(cal, causa=None):
    """[F9 / Q-7] O alfa efetivo desta rodada, e -- quando pedida -- a exibicao da CAUSA.

    `cal` e o controle nao-parametrico (`controle_nulo`), que preserva a marginal real e por
    isso responde "qual o alfa aqui". `causa` e a tabela do controle gerado
    (`controle_nulo_direto`) trocando SO a forma da marginal, que e o que identifica o
    culpado. Os dois juntos porque separados um vira numero sem explicacao e o outro vira
    explicacao sem numero.
    """
    b = cal["banda"]
    print("")
    print("-- CONTROLE NULO do pipeline (parcial -- ver docstring de controle_nulo) [F9] --")
    print(f"   M={cal['M']} paineis embaralhados por blocos, independentes entre si, "
          f"n_boot={cal['n_boot']}")
    print(f"   rejeicao a 5%: {cal['rejeicoes']}/{cal['M']} = {cal['taxa']}  ->  {cal['classe']}")
    print(f"   banda CALCULADA (binomial exata, {b['conf']:.0%}): [{b['k_lo']} ; {b['k_hi']}] "
          f"rejeicoes = [{b['taxa_lo']} ; {b['taxa_hi']}] | IC da taxa: {cal['ic_taxa']}")
    print(f"   media dos p = {cal['media_p']} (uniforme -> 0,5) | desvio maximo da CDF "
          f"uniforme = {cal['ks_max']} (critico 1,36/sqrt(M) = {cal['ks_critico']})")
    if causa:
        print("   [Q-7] a CAUSA, por controle gerado -- so a marginal muda, tudo o mais fica:")
        for forma, c in causa:
            print(f"         marginal {forma:>8}: {c['rejeicoes']}/{c['M']} = {c['taxa']}  "
                  f"({c['classe']})")
        print("         O maximo de medias BRUTAS sobre cauda pesada infla o quantil nulo --")
        print("         e o mecanismo que [F15] ja descrevia em `spa_hansen`. Nao e o `+1` do")
        print("         p-valor nem o `block=5`: os dois estao presentes na linha 'normal'.")


def relatorio_sensibilidade(sens):
    print("\n-- SENSIBILIDADE (diagnostico; o veredito acima e SO do PADRAO) [F3] --")
    print(f"   {'criterio':>14}  {'trades':>7}  {'pnl':>8}  {'IC95% bloco':>20}  "
          f"{'PSR':>6}  {'Sharpe an.':>10}")
    for nome, r in sens["criterio"]:
        if r:
            print(f"   {nome:>14}  {r['trades']:>7}  {r['pnl']:>+8.0f}  "
                  f"{str(r['ic_bloco']):>20}  {r['psr']:>6}  {str(r['sharpe_anual']):>10}")
    for nome, r in sens["modo"]:
        if r:
            print(f"   {nome:>14}  {r['trades']:>7}  {r['pnl']:>+8.0f}  "
                  f"{str(r['ic_bloco']):>20}  {r['psr']:>6}  {str(r['sharpe_anual']):>10}")
    for nome, r in sens.get("atribuir", []):
        if r:
            print(f"   {('atrib=' + nome):>14}  {r['trades']:>7}  {r['pnl']:>+8.0f}  "
                  f"{str(r['ic_bloco']):>20}  {r['psr']:>6}  {str(r['sharpe_anual']):>10}")
    if not sens.get("atribuir"):
        print("   atribuir: nao rodado -- os trades deste gerador nao trazem `ts_saida`")
    print(f"\n   {'block':>14}  {'IC95% da media/dia':>24}   (block=1 E o iid) [F18]")
    for bl, ic in sens["block"]:
        print(f"   {bl:>14}  {str(ic):>24}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "politicas":
        comparar_politicas()                          # [P1-10] A x B x C, mesma regua
        sys.exit(0)
    r = walk_forward_tendencia("tendencia")
    if "erro" not in r:
        relatorio_sensibilidade(sensibilidade(r))
        causa = [(f, controle_nulo_direto(r["matriz_is"], M=200, seed=7, dgp=f))
                 for f in ("normal", "pesada")]
        relatorio_controle_nulo(r["calibracao"], causa)
