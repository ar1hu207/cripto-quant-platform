"""
Sprint 6 - Backtest INTEGRADO. Roda a MESMA pontuação (scoring.pontuar) e a MESMA
matemática de P&L (alavancagem + taxa + liquidação) da plataforma ao vivo, sobre
histórico. Auto-confirma sinais >= corte. Reporta WIN RATE POR CONVICÇÃO — a tunagem,
agora com centenas de trades em vez de esperar o paper acumular.

Rodar (da RAIZ do repo):  python -m pesquisa.backtest_plataforma
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np

from pesquisa.dados import baixar_ohlcv
from scoring import preparar, pontuar, pontuar_reversao

TAXA = 0.0005          # igual à plataforma (0,05%/lado)
LIQ_BUFFER = 0.9
ATIVOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
          "XRP/USDT", "ADA/USDT", "DOGE/USDT", "AVAX/USDT"]
TF, DIAS = "15m", 60


TF_MAPA = {"5m": 5 / 60, "15m": 0.25, "30m": 0.5, "1h": 1, "4h": 4, "1d": 24}


def _horas_por_barra(df, tf_horas, tf):
    """Duração de UMA barra, em horas — e a ordem de precedência é a correção do [P1-10].

    A causa do defeito: `tfh` saía de `TF_MAPA[tf]`, e `tf` é um parâmetro com default
    (`"15m"`) que quem passa um `df` pronto não precisa passar. `validacao.gerador_tendencia`
    passava `df=dfs[c]` com candles de **1h** e não passava `tf` — então a barra valia 0,25 h
    para um `df` de 1 h, e o funding do `[P2-10]` era cobrado por **um quarto** do tempo de
    hold real.

    **A direção do viés depende do sinal do funding líquido do período, e não é universal.**
    Cobrar um quarto do carry significa pagar 1/4 quando o livro é net-LONG (P&L
    superestimado) e RECEBER 1/4 quando é net-SHORT (P&L subestimado). A magnitude é sempre
    4×; o sinal, não — quem reportar esta correção tem de dizer sobre qual período fala.

    **E para o período de 1.095 dias o sinal AINDA NÃO FOI MEDIDO.** O contraste que o
    mediria é o do `[P2-10]` (`walk_forward_tendencia(com_contraste=True)`), e a §6 do
    `ITEM1-VALIDACAO-RIGOROSA.md` registra que ele não chegou a rodar: *"a sessão foi cortada
    por tempo antes de a segunda passada do grid (~13 min) terminar"*. O que está registrado
    daquela rodada é o P&L OOS com funding (`+R$993`); o par sem funding, não. Enquanto o
    contraste não for colado num documento, a direção nesse período é desconhecida — e a
    linha `-> efeito do carry: ... net-LONG/net-SHORT` que o próprio script imprime é onde ela
    vai aparecer.

    O conserto de sintoma seria acrescentar `tf=TF` na chamada da `validacao`. Ele funciona
    hoje e quebra de novo no próximo `df` com outra granularidade, em silêncio, porque a
    duração da barra continuaria vindo de uma string que o chamador pode esquecer. **O `df`
    sabe a própria granularidade** — está nos `timestamp` dele. Então ela é medida, e o mapa
    de `tf` vira só o que resta quando não dá para medir (df de uma linha, timestamps
    ausentes). `tf_horas` explícito continua vencendo: quem declara, declarou.
    """
    if tf_horas:
        return tf_horas
    try:
        ts = df["timestamp"].values
        if len(ts) >= 2:
            passo = float(np.median(np.diff(ts[:200].astype("float64"))))
            if passo > 0:
                return passo / 3_600_000.0
    except Exception:
        pass
    return TF_MAPA.get(tf, 0.25)


POLITICAS = ("regime", "auto", "trailing")

# [P1-10] Defaults das politicas B e C, copiados do que o banco carrega HOJE
# (`db.CONFIG_PADRAO`): `alvo_roe = 5`, `trailing_dist = 0.02`. Ficam aqui como constante de
# pesquisa e nao lidos do banco de proposito -- este modulo nao importa `db`, e um backtest
# que muda de resultado porque alguem mexeu na config do vivo nao e reproduzivel. Quem quiser
# outro valor passa por argumento, e o valor entra no rotulo da rodada.
ALVO_ROE = 5.0
ROE_MIN_LUCRO = 1.0

# [P-1 / D-6] A UNIDADE do trailing, e por que a pesquisa mudou de unidade em 2026-08-29.
#
# Ate aqui este modulo tinha uma politica de trailing PROPRIA: `TRAILING_DIST = 0.02`, isto e,
# arma em +2% de PRECO e trava 2% atras do extremo. O vivo fazia o mesmo -- ate o `[N-13]`
# (`simulador._trailing_novo_stop`) trocar a unidade para R, com o dono assinando 1R para armar
# e 1R de distancia (decisao `D-5`). No instante daquele merge, este arquivo passou a medir uma
# politica de saida que o sistema NAO EXECUTA MAIS, e a decisao `D-6` do dono resolveu a
# ambiguidade na direcao certa: **a pesquisa acompanha o vivo**.
#
# Por que R e nao preco -- e a razao e a mesma dos dois lados. Um gatilho em espaco-preco vira
# ROE quando multiplicado pela alavancagem (2% de preco sao 4% de ROE a 2x e 40% a 20x), entao
# o trailing desarmava justamente onde a aposta era maior; e em unidade de risco os mesmos 2%
# valem 3R num stop curto e meio R num stop largo. Em R o gatilho significa a mesma coisa em
# todo trade, qualquer que seja o ativo, a volatilidade ou a alavancagem -- que e por que o
# `be_em_R` do [Q-11] ja era medido assim. 1R aqui e `abs(entrada - stop_de_abertura)`, fixado
# na entrada e imutavel depois, espelhando o `stop_abertura` que o `[F-1]` criou no vivo.
#
# ⚠️ **O CUSTO ESTA DECLARADO E ACEITO (PLANO-V2 D.7/D-6):** os vereditos ja emitidos --
# `VEREDITO-M4.md` e o `DSR = 0,060` da politica `C trailing` -- foram medidos sobre a politica
# de PRECO. Eles continuam verdadeiros como historico e NAO se reescrevem; o que deixa de valer
# e apresenta-los como "o veredito da politica de producao". Comparar um veredito novo com eles
# e comparar duas politicas diferentes.
#
# `"preco"` continua inteiro, e nao por nostalgia: e o que mantem `POLITICAS_M4` reproduzindo os
# numeros do M4 e a varredura de geometria do [Q-8]/[Q-9] rodando na unidade em que foi medida.
TRAILING_UNIDADE = "R"
TRAILING_ARMA_R = 1.0        # espelha `db.CONFIG_PADRAO["trailing_arma_r"]` (D-5)
TRAILING_DIST_R = 1.0        # espelha `db.CONFIG_PADRAO["trailing_dist_r"]` (D-5)
TRAILING_DIST = 0.02         # so no caminho `trailing_unidade="preco"` (a politica ANTIGA)
UNIDADES_TRAILING = ("R", "preco")

# [Q-10] Transcricao do cap geometrico do `autotrader` ([P1-11]). Nao se importa `autotrader`
# aqui de proposito: `pesquisa/` nao depende da plataforma viva (ele importaria `db` e
# `simulador`), e os UNICOS modulos de raiz declarados compartilhados sao `scoring` e
# `indicadores` (`CLAUDE.md` 0). O preco dessa fronteira e uma copia -- e o preco da copia e
# pago por `test_Q10_lev_por_conviccao_e_transcricao_fiel_do_autotrader`, que importa os dois
# lados e QUEBRA quando divergirem. Copia sem teste de pinagem e que vira divergencia silenciosa.
FOLGA_LIQ = 0.8


def _lev_conviccao(conv, lev_min, lev_max, conv_min, stop_dist):
    """Alavancagem por conviccao + cap geometrico -- espelho de `autotrader._alavancagem`.

    [Q-10] Existe porque a regua roda com `LEV` FIXO (10x em `validacao.py`) e a producao rodava
    de 2x a 20x pela conviccao. Todo achado que dependa da INTERACAO entre alavancagem e um
    limiar fixo em preco e invisivel num backtest de alavancagem constante -- e foi exatamente
    um desses que a medicao de MFE de 2026-08-24 encontrou: o trailing SO ARMAVA em +2% de
    preco, o que a 14x significava 28% de ROE sem protecao nenhuma.

    [P-1] As duas frases acima estao no PASSADO de proposito, e as duas caducaram no mesmo dia
    (2026-08-29): o `[N-10]` fez `auto_lev_modo` nascer `"fixo"` e o `[N-13]` tirou o trailing
    do espaco-preco. O achado que motivou este helper continua valendo como historia -- foi ele
    que pagou os dois consertos --, e o helper continua existindo porque o modo `"conviccao"`
    nao foi apagado, so desligado, esperando o medidor do `N-10b`.
    """
    frac = min(max((conv - conv_min) / max(100 - conv_min, 1), 0.0), 1.0)
    lev = lev_min + frac * (lev_max - lev_min)
    lev = float(max(lev_min, min(round(lev), lev_max)))
    if stop_dist and stop_dist > 0:                     # cap geometrico: liquidacao ATRAS do stop
        lev_geo = FOLGA_LIQ * LIQ_BUFFER / stop_dist
        if lev_geo < lev:
            capada = max(1.0, float(int(lev_geo)))      # trunca PARA BAIXO, como o [P1-11]
            if capada < lev:
                lev = capada
    return lev


def _sinais_reversao(d, i, closes, rsi, ema_r, ema_l):
    """Os gatilhos de reversao do gestor de saida ao vivo (`signal_engine.avaliar_saida`).

    Paridade linha a linha com `signal_engine.py:133-146`, inclusive o uso do MESMO `ema_r[i]`
    nos dois lados da comparacao de cruzamento (`cp >= er and c < er`).

    **O que NAO da para reproduzir, e a direcao do erro.** O gestor ao vivo tem um quarto
    gatilho, o fluxo do book (`mercado.book`, `signal_engine.py:147-153`), e livro de ordens
    nao existe em historico OHLCV. Ele so ACRESCENTA motivos, nunca remove: entao a politica
    B medida aqui fecha MENOS vezes que a viva, segura a posicao por mais tempo e fica mais
    perto da politica A do que a de verdade. O vies e contra a diferenca entre as politicas,
    isto e, contra o proprio achado que este card procura -- que e o lado seguro para errar.
    """
    if rsi[i] != rsi[i] or ema_r[i] != ema_r[i] or ema_l[i] != ema_l[i]:
        return 0                                        # warmup: ao vivo devolve None
    n = 0
    if d == 1:
        n += 1 if (rsi[i - 1] >= 68 and rsi[i] < rsi[i - 1]) else 0
        n += 1 if (closes[i - 1] >= ema_r[i] and closes[i] < ema_r[i]) else 0
        n += 1 if (ema_r[i] < ema_l[i]) else 0
    else:
        n += 1 if (rsi[i - 1] <= 32 and rsi[i] > rsi[i - 1]) else 0
        n += 1 if (closes[i - 1] <= ema_r[i] and closes[i] > ema_r[i]) else 0
        n += 1 if (ema_r[i] > ema_l[i]) else 0
    return n


def _roe(pos, preco, valor, lev, taxa):
    """ROE% da posicao marcada em `preco` -- a MESMA conta de `simulador._pnl`, inclusive o
    teto de perda na margem. E ela que o gestor de saida ao vivo compara com `alvo_roe`."""
    move = pos["d"] * (preco / pos["e"] - 1)
    pnl = valor * lev * move - 2 * taxa * valor * lev
    return max(pnl, -valor) / valor * 100


def backtest_ativo(ativo, min_conv, valor, lev, tf=TF, dias=DIAS,
                   estrategia="tendencia", df=None, adx_min=25, adx_max_rev=22,
                   max_hold=20, taxa=TAXA, slip=0.0002, funding_8h=0.0, tf_horas=None,
                   sinal_fn=None, saida="regime", trailing_unidade=TRAILING_UNIDADE,
                   trailing_arma_r=TRAILING_ARMA_R, trailing_dist_r=TRAILING_DIST_R,
                   trailing_dist=TRAILING_DIST,
                   trailing_k_atr=None, alvo_roe=ALVO_ROE, sd_min=0.0,
                   be_em_R=None, lev_modo="fixo", lev_min=2.0, lev_max=20.0, conv_min_lev=60.0):
    """Backtest com PARIDADE honesta: sinal no candle FECHADO i, execução no OPEN do
    candle SEGUINTE (i+1) + slippage. estrategia: 'tendencia' ou 'reversao' (alvo = volta à
    média + time-stop). df pré-carregado evita re-baixar.

    **`saida` — a política de saída, e o motivo de ela existir ([P1-10]).** O veredito central
    do projeto — *"tendência sem edge"* — mediu a política **A**, que é a única que este
    arquivo sabia executar. **O sistema ao vivo nunca operou a política A.** Já operou duas
    outras, nenhuma backtestada, e a que roda hoje é a C:

    | `saida` | o que fecha a posição | o que liga isso ao vivo |
    |---|---|---|
    | `"regime"` (A) | stop 3×ATR fixo, liquidação, ou flip de regime | **não existe no vivo** — é a política do backtest |
    | `"auto"` (B) | stop 3×ATR fixo, liquidação, ou auto-saída | `auto_fechar_saida=1` **e** `trailing_ativo=0` (`autotrader.py:151`) |
    | `"trailing"` (C) | stop que só sobe atrás do preço, ou liquidação | `trailing_ativo=1` — **o default de hoje** (`db.py`) |

    **`trailing_unidade` — a unidade da política C, e ela mudou em 2026-08-29 ([P-1]/`D-6`).**
    Default `"R"`, espelhando o `[N-13]` do vivo: arma quando a excursão favorável atinge
    `trailing_arma_r` × 1R e trava `trailing_dist_r` × 1R atrás do extremo, com
    `1R = abs(entrada − stop_de_abertura)` fixado na entrada. Com o `1R/1R` assinado pelo dono
    (`D-5`), o stop cai exatamente no preço de entrada no instante em que arma — é o `be_em_R=1`
    da pesquisa chegando ao vivo pela outra porta. `"preco"` é a política antiga
    (`entrada·(1±td)` para armar, `extremo·(1∓td)` para o stop), preservada expressão por
    expressão: é ela que faz `POLITICAS_M4` continuar reproduzindo os números do `VEREDITO-M4`.

    O flip de regime **não existe no sistema vivo**: nada em `simulador.atualizar()` nem em
    `autotrader.auto_executar()` fecha por inversão do scoring. Por isso B e C não o herdam —
    herdá-lo faria as três políticas compartilharem uma saída que só a A tem, e a comparação
    mediria menos diferença do que existe.

    **A ordem dentro do candle é decisão, não detalhe.** Em cada candle: primeiro testa stop e
    liquidação contra o stop vigente (fixado por dados até `i-1`), *depois* atualiza o trailing
    com o `high`/`low` do candle `i`. O contrário — subir o stop com o topo do candle e só
    então perguntar se o fundo do mesmo candle o furou — supõe que o topo veio antes do fundo,
    que o OHLC não diz. Assim o stop de C só se move para o candle seguinte, o que é
    conservador: trava menos lucro do que o vivo, que faz poll a cada 15 s.

    **`trailing_k_atr` — o item 3 do card, e o mais fácil de esquecer.** `trailing_dist` é fixo
    em espaço-preço, e por isso é cego ao ATR (a *entrada* usa stop 3×ATR e a *saída* ignora a
    volatilidade do ativo) e cego à alavancagem (2% de preço = 4% de ROE a 2x, **40%** a 20x).
    Com `trailing_k_atr=k` a distância vira `k·ATR/preço`, medida **na entrada** e fixa depois:
    coerente com o stop de entrada, e um número por trade, como o vivo. Recalculá-la a cada
    candle seria outra política, não a mesma em outra unidade.

    ⚠️ **`trailing_k_atr` FORÇA `trailing_unidade="preco"`, e isso é declarado e não implícito.**
    `k·ATR/preço` **é** uma distância em espaço-preço por construção; deixá-la conviver com o
    default `"R"` daria duas unidades para a mesma geometria e uma delas seria ignorada em
    silêncio — que é a doença que o `[N-13]` veio curar, renascida do outro lado. A alternativa
    (levantar erro) reprovaria a varredura de geometria do `[Q-8]`/`[Q-9]`, que passa só `k` e
    foi medida nesta unidade. Elas são quase a mesma coisa, aliás: como `stop_dist = 3·ATR/c`
    (`scoring.py:53`), `k=3` é ≈ `dist_r=1` — o que a varredura de `k` já varreu foi, sem saber,
    a vizinhança do 1R.

    **`sd_min` — o piso de distância do stop ([Q-9]).** Portão de CUSTO: recusa o sinal cujo
    stop está tão perto que o round-trip come o risco (`taxa/risco = 2·taxa_lado/sd`). Default
    `0.0` = desligado, para que nenhuma rodada anterior mude de resultado. O porquê completo
    está no ponto do gate, junto do `continue`.

    **`be_em_R` — o stop zero-a-zero ([Q-11]), e por que ele é medido em R e não em preço.**
    A medição de MFE de 2026-08-24 (`INVESTIGACAO-MOTOR-2026-08-24.md` §8) mostrou que **19 dos
    20 trades que foram de lucro a prejuízo nunca tiveram o trailing armado**: ele só arma em
    `+trailing_dist` de PREÇO, e abaixo disso a proteção é zero. Como o lucro que o operador vê
    é ROE (= preço × alavancagem), o limiar em preço vira um limiar em ROE que ESCALA com a
    alavancagem — 2% de preço são 6% de ROE a 3x e **40% a 20x**. O sistema desprotege
    exatamente os trades em que mais confia, porque convicção alta é alavancagem alta.

    `be_em_R=r` move o stop para o zero-a-zero quando a excursão favorável atinge `r` vezes o
    risco-até-o-stop inicial. Em R, e não em preço nem em ROE, porque R é a única unidade em
    que o gatilho não muda de significado quando o ativo, a volatilidade ou a alavancagem
    mudam — é a mesma correção de unidade da §1, aplicada ao outro parâmetro.

    O zero-a-zero cobre a TAXA (`e·(1 ± 2·taxa)`), não o preço de entrada seco: parar em `e`
    fecharia com `−2·taxa·valor·lev`, que não é zero a zero, é uma perda pequena com nome
    bonito. O `move` que zera o P&L é `2·taxa`, e ele não depende da alavancagem.

    **`lev_modo="conviccao"` ([Q-10]).** A régua roda `LEV` fixo e a produção roda 2x-20x pela
    convicção; sem isto, medir `be_em_R` não responde nada, porque o defeito que ele ataca É a
    interação entre alavancagem e limiar. Default `"fixo"` mantém toda rodada anterior idêntica.

    **`direcao`, e por que ela é `+1/-1` e não `"LONG"/"SHORT"` ([P-4]).**
    Cada trade grava o lado da posição. Sem ele a `validacao.exposicao_liquida` — a linha que
    o `[N-5]` acrescentou para separar **alfa de beta** — sai `NAO COMPUTAVEL` na rodada real,
    e sem ela um P&L positivo não tem como ser distinguido de "estava comprado num bull". É o
    portão bloqueante de qualquer veredito POSITIVO da V2, e ele caía por uma chave ausente.

    Há **duas** convenções de `direcao` nesta casa, e elas não são intercambiáveis: o **banco**
    guarda TEXTO (`posicoes.direcao` é `"LONG"`/`"SHORT"`, `db.py:29`, e `simulador` converte
    com `1 if pos["direcao"] == "LONG" else -1`), enquanto a **camada numérica** — `scoring`
    (`scoring.py:35,52`), este motor e a régua — usa `+1/-1`. Aqui vale a numérica, por dois
    motivos: `d` já É o `p["direcao"]` que veio do `scoring`, e o consumidor deste campo
    (`exposicao_liquida`) exige `{+1,-1}` de propósito, porque o número que ela calcula é
    `sum(direcao·duracao)/sum(duracao)` — uma média ponderada, não uma contagem de rótulos.
    Gravar `"LONG"` aqui deixaria a exposição `None` com o mesmo motivo de antes, isto é,
    fecharia o card sem fechar o buraco.

    **`ts_saida`, e por que ele é o FECHAMENTO do candle de saída e não a abertura.**
    Cada trade grava o instante da entrada (`ts`, o open do candle i+1, que é o fill) e o
    instante em que o desfecho ficou conhecido (`ts_saida`). A régua usa esse segundo campo
    para a purga de borda de fold (`pesquisa/validacao.py:_treino`): só entra no treino o
    trade cujo span de label termina ANTES da borda. Sem ele a purga desligava sozinha e o
    vazamento de borda continuava presente e não medido — e ele empurra o resultado para
    CIMA, contra a conclusão negativa, que é o pior lado para economizar trabalho.

    O carimbo é `tss[i] + tf_ms`, o FIM do candle de saída, e não `tss[i]` (o começo dele).
    A razão é o que a purga precisa saber: quando o P&L deixou de ser incerto. As saídas por
    `regime`/`tempo` executam literalmente em `closes[i]`, então só no fechamento do candle
    o resultado existe; as saídas por `stop`/`liq`/`alvo` disparam em algum ponto INTERNO do
    candle e o backtest não sabe qual — carimbar o começo afirmaria um instante que o modelo
    não observa, e erraria para MENOS purga. Arredondar para o fim do candle erra para mais
    purga, isto é, contra o resultado, que é o lado permitido nesta casa.

    **`sinal_fn` — de onde vem o sinal, e por que ele é injetável.** Default: `scoring.pontuar`
    (ou `pontuar_reversao`), que é a paridade com o vivo e continua sendo o que roda em
    produção de pesquisa. Injetar existe por duas razões escritas:

      * **provar este motor sem rede.** Com o sinal fixo em `pontuar`, testar "trajetória
        conhecida → saída esperada" exige construir um `df` que ao mesmo tempo dispare o
        scoring E ande pelo caminho que o teste quer — duas restrições que brigam, e o teste
        acaba provando o scoring em vez da saída. Com o sinal injetado, a trajetória é livre.
      * **a dívida do `F9`** (`pesquisa/validacao.py`, docstring de `controle_nulo`): o
        controle nulo COMPLETO passa M geradores de sinal aleatório pelo pipeline inteiro, e
        estava bloqueado exatamente em "`backtest_ativo` não aceita uma função de sinal".

    O flip de regime também usa `fn`, não `pontuar` fixo: entrada e saída de uma mesma política
    têm de ler a mesma fonte. Para `estrategia="tendencia"` sem injeção nada muda — `fn` É
    `pontuar`.

    **O que este motor NÃO modela, em nenhuma das três políticas** (é backtest por ativo, e o
    de carteira é `pesquisa/backtest_portfolio.py`): o `auto_cooldown_min`, o
    `auto_max_posicoes`, o teto de exposição, a trava diária e o sizing por risco. Todos
    reduzem o número de trades ao vivo; nenhum muda a saída de um trade já aberto, que é o que
    este card compara.
    """
    if saida not in POLITICAS:
        raise ValueError(f"saida deve ser uma de {POLITICAS}, veio {saida!r}")
    if trailing_unidade not in UNIDADES_TRAILING:
        raise ValueError(f"trailing_unidade deve ser uma de {UNIDADES_TRAILING}, "
                         f"veio {trailing_unidade!r}")
    if trailing_k_atr:                       # k.ATR E espaco-preco: ver o aviso na docstring
        trailing_unidade = "preco"
    if df is None:
        df = preparar(baixar_ohlcv(ativo, tf, dias=dias))
    tfh = _horas_por_barra(df, tf_horas, tf)                    # medida no df, nao adivinhada
    tf_ms = int(round(tfh * 3_600_000))                         # duracao do candle, para o `ts_saida`
    opens, closes, tss = df["open"].values, df["close"].values, df["timestamp"].values
    highs, lows = df["high"].values, df["low"].values
    mids = df["bb_mid"].values
    precisa_auto = (saida == "auto" and estrategia == "tendencia")
    rsi = df["rsi"].values if precisa_auto else None
    ema_r = df["ema_r"].values if precisa_auto else None
    ema_l = df["ema_l"].values if precisa_auto else None
    atrv = df["atr"].values if trailing_k_atr else None
    fn = sinal_fn or (pontuar if estrategia == "tendencia" else pontuar_reversao)
    trades, pos = [], None
    for i in range(60, len(df) - 1):                            # -1: precisa do open[i+1] pra entrar
        if pos is None:
            p = fn(df, i)
            if not p or p["conviccao"] < min_conv:
                continue
            if estrategia == "tendencia":                       # mesmos portões do ao vivo
                if p["adx"] < adx_min or p["n_fatores"] < 3:
                    continue
            else:                                               # reversão: só mercado lateral
                if p["adx"] > adx_max_rev or p["n_fatores"] < 2:
                    continue
            # [Q-9] Piso de distância do stop — portão de CUSTO, não de estratégia.
            #
            # `taxa/risco = 2·taxa_lado/sd`: a fração do risco-até-o-stop que vira taxa não
            # depende de tamanho, de alavancagem nem de edge, só de `sd`. Com `taxa=0,0005`,
            # `sd=0,19%` (TRX 5m em produção, 2026-08-24) põe **53%** do risco na corretora
            # antes de o mercado se mexer. O gate espelha o `_liq_antes_do_stop` do
            # `simulador` ([P1-12]), que recusa a degeneração do outro lado — stop LONGE
            # demais, atrás da liquidação. Perto demais é a mesma doença com o sinal trocado,
            # e não tinha guarda nenhuma.
            #
            # Fica no `backtest_ativo` e não no `scoring` de propósito: `scoring` é a paridade
            # com o vivo (`CLAUDE.md` §0) e mudar a pontuação mudaria o SINAL. Isto não muda o
            # sinal — recusa executá-lo quando o custo do round-trip come o risco. Default 0,0
            # = portão desligado, então nenhuma rodada anterior muda de resultado.
            if sd_min and (p.get("stop_dist") or 0.0) < sd_min:
                continue
            d = p["direcao"]
            e = opens[i + 1] * (1 + d * slip)                   # fill no OPEN do próximo candle + slippage
            # distância do trailing FIXADA na entrada: k×ATR/preço se pedido, senão o % fixo
            td = trailing_dist
            if trailing_k_atr and atrv is not None and atrv[i] == atrv[i] and e > 0:
                td = trailing_k_atr * atrv[i] / e
            lev_pos = (_lev_conviccao(p["conviccao"], lev_min, lev_max, conv_min_lev,
                                      p["stop_dist"]) if lev_modo == "conviccao" else lev)
            stop0 = e * (1 - d * p["stop_dist"])
            pos = dict(d=d, e=e, conv=p["conviccao"], i0=i + 1, ts=int(tss[i + 1]), td=td,
                       stop=stop0, liq=e * (1 - d * (LIQ_BUFFER / lev_pos)), lev=lev_pos,
                       risco=abs(e - stop0), be=None)
        else:
            d, saida_p, motivo = pos["d"], None, None
            hit_liq = (d == 1 and lows[i] <= pos["liq"]) or (d == -1 and highs[i] >= pos["liq"])
            hit_stop = (d == 1 and lows[i] <= pos["stop"]) or (d == -1 and highs[i] >= pos["stop"])
            if hit_liq and hit_stop:                            # empate intrabar: o mais PERTO da entrada bate 1o
                if abs(pos["e"] - pos["stop"]) <= abs(pos["e"] - pos["liq"]):
                    saida_p, motivo = pos["stop"], _motivo_stop(pos)
                else:
                    saida_p, motivo = pos["liq"], "liquidacao"
            elif hit_liq:
                saida_p, motivo = pos["liq"], "liquidacao"
            elif hit_stop:
                saida_p, motivo = pos["stop"], _motivo_stop(pos)
            elif estrategia == "reversao":
                alvo = mids[i - 1]                              # mid do candle ANTERIOR (sem look-ahead intrabar)
                if (d == 1 and highs[i] >= alvo) or (d == -1 and lows[i] <= alvo):
                    saida_p, motivo = alvo, "alvo"
                elif i - pos["i0"] >= max_hold:                 # time-stop (não fica preso)
                    saida_p, motivo = closes[i], "tempo"
            elif saida == "trailing":
                pass                                            # só stop trailado e liquidação fecham
            elif saida == "auto":                               # B: reversão COM lucro (gestor de saída)
                roe = _roe(pos, closes[i], valor, pos["lev"], taxa)
                if _sinais_reversao(d, i, closes, rsi, ema_r, ema_l) and (
                        roe >= alvo_roe or roe > ROE_MIN_LUCRO):
                    saida_p, motivo = closes[i], "auto-saida"
            else:                                               # A: flip de regime
                p = fn(df, i)                                   # a MESMA fonte de sinal da entrada
                if p and p["direcao"] != d:
                    saida_p, motivo = closes[i], "regime"
            if saida_p is None:
                # Movimentos de stop DEPOIS da checagem de saída: o stop só vale para o candle
                # SEGUINTE, porque o OHLC não diz se o topo veio antes ou depois do fundo dentro
                # deste candle. [Q-11] o zero-a-zero segue a MESMA regra -- se ele agisse no
                # próprio candle, o backtest leria o extremo e decidiria com ele, que é
                # look-ahead intrabar com outro nome.
                if be_em_R and not pos["be"] and pos["risco"] > 0:
                    ganho = (highs[i] - pos["e"]) if d == 1 else (pos["e"] - lows[i])
                    if ganho >= be_em_R * pos["risco"]:
                        be = pos["e"] * (1 + d * 2 * taxa)       # zero a zero COBRINDO a taxa
                        pos["stop"] = max(pos["stop"], be) if d == 1 else min(pos["stop"], be)
                        pos["be"] = be
                if saida == "trailing":
                    # [P-1] Duas unidades, e a escolha e do chamador. Em "R" o gatilho e a
                    # distancia saem do MESMO 1R do stop de abertura (`pos["risco"]`, fixado na
                    # entrada e nunca relido do stop vigente -- reler seria o [F-1] renascendo
                    # dentro do conserto: o R encolheria a cada candle e "1R" passaria a
                    # significar um lucro menor a cada passada).
                    #
                    # A CATRACA (`max`/`min`) e a mesma nas duas unidades, e nao e detalhe: um
                    # stop que anda para tras e um stop que o mercado escolhe. Espelha o
                    # `simulador._marcar_uma`, que so aceita `novo` se ele andar a favor.
                    #
                    # `risco == 0` (sinal sem stop) NAO cai no caminho de preco: sem 1R
                    # mensuravel nao ha politica em R para executar, e emprestar os 2% do modo
                    # antigo inventaria uma politica para o caso degenerado. O vivo cai para
                    # "preco" ali por outro motivo -- posicoes abertas ANTES de a coluna
                    # `stop_abertura` existir --, e aqui nao ha posicao antiga.
                    if trailing_unidade == "R" and pos["risco"] > 0:
                        if d == 1 and highs[i] >= pos["e"] + trailing_arma_r * pos["risco"]:
                            pos["stop"] = max(pos["stop"],
                                              highs[i] - trailing_dist_r * pos["risco"])
                        elif d == -1 and lows[i] <= pos["e"] - trailing_arma_r * pos["risco"]:
                            pos["stop"] = min(pos["stop"],
                                              lows[i] + trailing_dist_r * pos["risco"])
                    elif trailing_unidade == "preco":
                        if d == 1 and highs[i] >= pos["e"] * (1 + pos["td"]):
                            pos["stop"] = max(pos["stop"], highs[i] * (1 - pos["td"]))
                        elif d == -1 and lows[i] <= pos["e"] * (1 - pos["td"]):
                            pos["stop"] = min(pos["stop"], lows[i] * (1 + pos["td"]))
            if saida_p is not None:
                lev_p = pos["lev"]
                saida_fill = saida_p if motivo == "liquidacao" else saida_p * (1 - d * slip)  # liq = preço de liq (= live)
                move = d * (saida_fill / pos["e"] - 1)
                fcost = d * funding_8h * ((i - pos["i0"]) * tfh / 8) * (valor * lev_p)  # funding: LONG paga>0, SHORT recebe
                pnl = max(valor * lev_p * move - 2 * taxa * valor * lev_p - fcost, -valor)
                trades.append({"conv": pos["conv"], "pnl": pnl, "motivo": motivo,
                               "ts": pos["ts"], "ts_saida": int(tss[i]) + tf_ms,
                               "direcao": d})
                pos = None
    return trades


def _motivo_stop(pos):
    """'trailing' quando o stop já está em lucro, 'stop' quando não — a MESMA distinção que
    `simulador._fecha_stop` grava em `trades.motivo_saida`. Vale a pena manter o vocabulário
    igual: é o que permite comparar a tabela de motivos do backtest com a do banco vivo sem
    tradução no meio.

    [Q-11] `zero-a-zero` é motivo PRÓPRIO, e não `trailing`. Os dois deixam o stop em lucro e
    cairiam no mesmo balde, mas medem coisas opostas: `trailing` é lucro que correu e foi
    travado atrás do pico; `zero-a-zero` é lucro que NÃO correu e virou empate. Somá-los
    esconderia justamente o que o card veio contar — quantas vezes a guarda salvou um trade que
    teria ido ao stop cheio."""
    d = pos["d"]
    em_lucro = (d == 1 and pos["stop"] >= pos["e"]) or (d == -1 and pos["stop"] <= pos["e"])
    if not em_lucro:
        return "stop"
    if pos.get("be") and pos["stop"] == pos["be"]:     # não avançou além do zero-a-zero
        return "zero-a-zero"
    return "trailing"


def relatorio(trades, valor, lev):
    if not trades:
        print("  nenhum trade gerado"); return
    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    print(f"\n  TOTAL: {n} trades | Win rate: {len(wins)/n*100:.1f}% | "
          f"P&L: R$ {sum(t['pnl'] for t in trades):+,.0f}  (R${valor} @ {lev}x por trade)")
    print(f"\n  {'faixa conv':<12}{'trades':>8}{'win rate':>11}{'P&L':>12}   (a TUNAGEM)")
    print("  " + "-" * 46)
    for nome, lo, hi in [("80-100", 80, 101), ("60-80", 60, 80), ("40-60", 40, 60), ("0-40", 0, 40)]:
        g = [t for t in trades if lo <= t["conv"] < hi]
        if g:
            w = sum(1 for t in g if t["pnl"] > 0) / len(g) * 100
            print(f"  {nome:<12}{len(g):>8}{w:>10.1f}%{sum(t['pnl'] for t in g):>+11,.0f}")


def relatorio_politicas(por_politica, valor, lev):
    """[P1-10] O SMOKE: prova, em poucas moedas e poucos dias, que as tres politicas de saida
    executam e produzem trades DIFERENTES entre si.

    Nao e a regua e nao emite veredito -- para isso e
    `python -m pesquisa.validacao politicas`, que leva ~1h. Este aqui existe para o caso em
    que alguem mexe no motor de saida e precisa saber em um minuto se as tres ainda divergem:
    se as colunas de motivo colapsarem numa so, a comparacao do marco perdeu o objeto e nao ha
    por que gastar a hora."""
    print(f"\n{'politica':<22}{'trades':>8}{'win%':>8}{'P&L':>11}   motivos de saida")
    print("  " + "-" * 92)
    for nome, trades in por_politica:
        if not trades:
            print(f"{nome:<22}{0:>8}   nenhum trade")
            continue
        n = len(trades)
        w = sum(1 for t in trades if t["pnl"] > 0) / n * 100
        conta = {}
        for t in trades:
            conta[t["motivo"]] = conta.get(t["motivo"], 0) + 1
        mot = " | ".join(f"{k}: {v}" for k, v in sorted(conta.items(), key=lambda x: -x[1]))
        print(f"{nome:<22}{n:>8}{w:>8.1f}{sum(t['pnl'] for t in trades):>+11,.0f}   {mot}")
    assinaturas = {nome: tuple(sorted((t["ts_saida"], round(t["pnl"], 4)) for t in tr))
                   for nome, tr in por_politica}
    iguais = [(a, b) for i, a in enumerate(assinaturas) for b in list(assinaturas)[i + 1:]
              if assinaturas[a] == assinaturas[b]]
    if iguais:
        print("\n  ATENCAO: politicas com saidas IDENTICAS -- " +
              "; ".join(f"{a} == {b}" for a, b in iguais))
    else:
        print("\n  as politicas produzem saidas distintas duas a duas (ts_saida, pnl)")


if __name__ == "__main__":
    MIN_CONV, VALOR, LEV = 25, 100, 10
    # [P-1] as politicas de PRECO tem a unidade PINADA: sem `trailing_unidade="preco"` elas
    # herdariam o default novo e o rotulo "2% fixo" passaria a nomear uma politica em R.
    POLITICAS_SMOKE = [("A stop+flip de regime", {"saida": "regime"}),
                       ("B auto-saida", {"saida": "auto"}),
                       ("C trailing 1R/1R (vivo)", {"saida": "trailing"}),
                       ("C trailing 2% fixo", {"saida": "trailing",
                                               "trailing_unidade": "preco",
                                               "trailing_dist": 0.02}),
                       ("C trailing 3xATR", {"saida": "trailing", "trailing_k_atr": 3.0})]
    print(f"BACKTEST INTEGRADO (paridade c/ a plataforma) | {len(ATIVOS)} ativos | {TF} | {DIAS}d | "
          f"corte>={MIN_CONV} | R${VALOR} @ {LEV}x")
    dfs = {a: preparar(baixar_ohlcv(a, TF, dias=DIAS)) for a in ATIVOS}

    todos = []
    for a in ATIVOS:
        todos += backtest_ativo(a, MIN_CONV, VALOR, LEV, df=dfs[a])
    relatorio(todos, VALOR, LEV)

    por_politica = []
    for nome, kw in POLITICAS_SMOKE:
        tr = []
        for a in ATIVOS:
            tr += backtest_ativo(a, MIN_CONV, VALOR, LEV, df=dfs[a], **kw)
        por_politica.append((nome, tr))
    relatorio_politicas(por_politica, VALOR, LEV)
