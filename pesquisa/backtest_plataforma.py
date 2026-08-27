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

# [Q-17] Os modos do portao de open interest. `"off"` e a HIPOTESE NULA e o default: com ele
# nada muda, e toda rodada anterior a este card devolve exatamente o que devolvia.
#
#   "off"            o open interest nao e consultado (a estrategia de hoje)
#   "concorda"       recusa o sinal quando d_oi <= 0 (desmonte de posicao)
#   "concorda_tend"  idem, mas so quando adx >= adx_min; fora de tendencia passa
#   "peso"           nao recusa: soma +-OI_PESO de conviccao conforme concorde ou nao
#
# A grade esta declarada em `PRE-REGISTRO-Q17-OI-2026-08-25.md` §3 e e travada: nao havera
# varredura de limiar de d_oi nem das outras colunas do dump -- as razoes long/short NAO
# reconciliam com o caminho ao vivo e estao barradas de decidir.
OI_MODOS = ("off", "concorda", "concorda_tend", "peso")

# O passo do modo "peso", em pontos de conviccao. Fixo e nao varrido de proposito: varrer o
# passo seria transformar um modo em quatro e multiplicar a grade -- e a §3 do pre-registro
# declarou 24 configs, nao 96. 10 e uma faixa inteira das quatro do `db.metricas()`
# (0-40/40-60/60-80/80-100): grande o bastante para mover a decisao, pequeno o bastante para
# nao atropelar o `min_conv`.
OI_PESO = 10.0

# [P1-10] Defaults das politicas B e C, copiados do que o banco carrega HOJE
# (`db.CONFIG_PADRAO`): `alvo_roe = 5`, `trailing_dist = 0.02`. Ficam aqui como constante de
# pesquisa e nao lidos do banco de proposito -- este modulo nao importa `db`, e um backtest
# que muda de resultado porque alguem mexeu na config do vivo nao e reproduzivel. Quem quiser
# outro valor passa por argumento, e o valor entra no rotulo da rodada.
ALVO_ROE = 5.0
ROE_MIN_LUCRO = 1.0
TRAILING_DIST = 0.02

# [Q-10] Transcricao do cap geometrico do `autotrader` ([P1-11]). Nao se importa `autotrader`
# aqui de proposito: `pesquisa/` nao depende da plataforma viva (ele importaria `db` e
# `simulador`), e os UNICOS modulos de raiz declarados compartilhados sao `scoring` e
# `indicadores` (`CLAUDE.md` 0). O preco dessa fronteira e uma copia -- e o preco da copia e
# pago por `test_Q10_lev_por_conviccao_e_transcricao_fiel_do_autotrader`, que importa os dois
# lados e QUEBRA quando divergirem. Copia sem teste de pinagem e que vira divergencia silenciosa.
FOLGA_LIQ = 0.8


def _lev_conviccao(conv, lev_min, lev_max, conv_min, stop_dist):
    """Alavancagem por conviccao + cap geometrico -- espelho de `autotrader._alavancagem`.

    [Q-10] Existe porque a regua roda com `LEV` FIXO (10x em `validacao.py`) e a producao roda
    de 2x a 20x pela conviccao. Todo achado que dependa da INTERACAO entre alavancagem e um
    limiar fixo em preco e invisivel num backtest de alavancagem constante -- e foi exatamente
    um desses que a medicao de MFE de 2026-08-24 encontrou: o trailing so arma em +2% de preco,
    o que a 14x significa 28% de ROE sem protecao nenhuma.
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
                   entrada="taker", maker_off=0.0, exec_stats=None, taxa_saida=None,
                   sinal_fn=None, saida="regime", trailing_dist=TRAILING_DIST,
                   trailing_k_atr=None, alvo_roe=ALVO_ROE, sd_min=0.0,
                   be_em_R=None, lev_modo="fixo", lev_min=2.0, lev_max=20.0, conv_min_lev=60.0,
                   oi_modo="off"):
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
    | `"trailing"` (C) | stop que só sobe atrás do preço, ou liquidação | `trailing_ativo=1` — **o default de hoje** (`db.py:95`) |

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
    if oi_modo not in OI_MODOS:
        raise ValueError(f"oi_modo deve ser um de {OI_MODOS}, veio {oi_modo!r}")
    if df is None:
        df = preparar(baixar_ohlcv(ativo, tf, dias=dias))
    tfh = _horas_por_barra(df, tf_horas, tf)                    # medida no df, nao adivinhada
    tf_ms = int(round(tfh * 3_600_000))                         # duracao do candle, para o `ts_saida`
    # [CX-4] Taxa de ENTRADA e de SAIDA separadas. `taxa_saida=None` = a mesma da entrada, que
    # deixa todo caminho anterior BYTE-IDENTICO (`taxa + taxa_saida` == `2 * taxa`).
    #
    # Existe porque o [CX-1] cobrou MAKER nas duas pernas, e isso e otimista: a saida do motor e
    # stop/trailing, que e ordem a MERCADO por natureza -- quando o preco vira contra, nao da
    # para pendurar limite e torcer. O round-trip realista de post-only e maker na entrada +
    # taker na saida.
    taxa_saida = taxa if taxa_saida is None else taxa_saida
    taxa_rt = taxa + taxa_saida                                 # o que o round-trip custa, em fracao
    opens, closes, tss = df["open"].values, df["close"].values, df["timestamp"].values
    highs, lows = df["high"].values, df["low"].values
    mids = df["bb_mid"].values
    precisa_auto = (saida == "auto" and estrategia == "tendencia")
    rsi = df["rsi"].values if precisa_auto else None
    ema_r = df["ema_r"].values if precisa_auto else None
    ema_l = df["ema_l"].values if precisa_auto else None
    atrv = df["atr"].values if trailing_k_atr else None
    # [Q-17] `d_oi` e a variacao do open interest de uma barra para a outra, ja alinhada sem
    # look-ahead por `pesquisa.dados_derivados.serie_1h` e anexada ao painel por
    # `anexar_oi`. `None` = painel sem a coluna, e ai `oi_modo` so pode ser "off".
    d_oi = df["d_oi"].values if "d_oi" in df.columns else None
    if oi_modo != "off" and d_oi is None:
        raise ValueError("oi_modo != 'off' exige a coluna `d_oi` no painel "
                         "(use pesquisa.backtest_plataforma.anexar_oi)")
    fn = sinal_fn or (pontuar if estrategia == "tendencia" else pontuar_reversao)
    trades, pos = [], None
    for i in range(60, len(df) - 1):                            # -1: precisa do open[i+1] pra entrar
        if pos is None:
            p = fn(df, i)
            if not p:
                continue
            # [Q-17] O portao de INFORMACAO, e o unico ponto do motor que le algo que nao vem
            # do candle. `PRE-REGISTRO-Q17-OI-2026-08-25.md` fixou a hipotese antes dos
            # numeros: preco subindo com open interest SUBINDO e dinheiro novo entrando na
            # direcao; preco subindo com OI CAINDO e short se cobrindo, e isso morre quando a
            # cobertura acaba. O mesmo candle verde com dois significados opostos -- e o
            # `scoring` nao distingue os dois porque le preco e volume do proprio ativo.
            #
            # Fica aqui e nao no `scoring` pela mesma razao do `sd_min`: `scoring` e a
            # paridade com o vivo (`CLAUDE.md` §0) e mexer nele mudaria o SINAL. Os modos
            # "concorda*" nao mudam o sinal -- recusam executa-lo. O "peso" muda a conviccao,
            # e por isso e o modo de que se desconfia mais (ver §5 do pre-registro: a
            # conviccao ainda nao foi verificada, o [Q-13] esta aberto).
            #
            # `d_oi` NaN = barra sem open interest medido (o D+1 do dump, ou buraco). NaN NAO
            # filtra: "nao operar quando falta dado" e outra hipotese, e deixa-la entrar sem
            # querer seria medir duas coisas de uma vez.
            if oi_modo != "off":
                v = d_oi[i]
                if v == v:                                  # NaN falha esta comparacao
                    # CONFIRMACAO = open interest SUBINDO, e isso INDEPENDE da direcao.
                    # Ver a §2.1-A do pre-registro: OI sobe quando posicao NOVA e aberta, e
                    # todo contrato tem um comprado e um vendido. Entao preco subindo com OI
                    # subindo = longs novos, e preco CAINDO com OI subindo = shorts novos --
                    # nos dois casos e dinheiro novo na direcao do movimento, e a direcao do
                    # movimento ja e a direcao do sinal. OI caindo e desmonte nos dois casos:
                    # short se cobrindo na alta, long liquidando na baixa.
                    #
                    # A primeira versao deste portao escreveu `(v * direcao) > 0`, que para
                    # SHORT exige OI CAINDO -- justamente o desmonte. Errado em metade dos
                    # trades. Quem pegou foi `test_a_confirmacao_independe_da_direcao`, antes
                    # de a regua rodar; a correcao esta registrada no pre-registro como
                    # emenda datada, nao reescrita em silencio.
                    concorda = v > 0
                    if oi_modo == "concorda" and not concorda:
                        continue
                    if (oi_modo == "concorda_tend" and not concorda
                            and p["adx"] >= adx_min):
                        continue
                    if oi_modo == "peso":
                        p = dict(p, conviccao=p["conviccao"] + (OI_PESO if concorda
                                                                else -OI_PESO))
            if p["conviccao"] < min_conv:
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
            if exec_stats is not None:
                exec_stats["sinais"] = exec_stats.get("sinais", 0) + 1
            if entrada == "gatilho":
                # [CX-3] A ideia do dono: NAO pendura ordem. Fica olhando o preco e, quando ele
                # chega no nivel, manda a MERCADO. Enche igual ao post-only -- mesma condicao,
                # mesmo `maker_off` -- mas paga taxa de TAKER e paga slippage, porque quem manda
                # a mercado consome a fila. A corretora nao cobra pela paciencia, cobra por quem
                # tirou liquidez.
                #
                # Existe para ISOLAR os dois efeitos que o `maker` mistura: preco de entrada
                # melhor e taxa menor. `gatilho` tem o primeiro e nao tem o segundo.
                lim = opens[i + 1] * (1 - d * maker_off)
                if (lows[i + 1] > lim) if d > 0 else (highs[i + 1] < lim):
                    continue
                e = lim * (1 + d * slip)
            elif entrada == "maker":
                # [CX-1] Ordem LIMITE post-only, `maker_off` MELHOR que o open, do nosso lado.
                # Só existe trade se o preço vier até ela DENTRO do candle de execução; senão
                # o sinal é PERDIDO (cancela, não vira taker) — é isso que separa a taxa de
                # maker que se paga da que se deseja.
                #
                # `maker_off=0` é o LIMITE SUPERIOR do ganho, não uma execução: com o limite no
                # próprio open, `low <= lim` é verdade por definição de OHLC (e `high >= lim`
                # para o short), então o fill é 100% por construção da barra, não por
                # comportamento do mercado. É exatamente a hipótese que a linha `maker 0,02%`
                # do [Q-15] embutiu sem declarar. Ele entra na grade para que o teto apareça
                # ao lado dos números que custam fill, e não sozinho.
                #
                # Sem `slip`: quem põe o preço não paga travessia de spread. O custo do maker
                # não é slippage, é o trade que não aconteceu.
                lim = opens[i + 1] * (1 - d * maker_off)
                if (lows[i + 1] > lim) if d > 0 else (highs[i + 1] < lim):
                    continue                                    # não encheu: sinal perdido
                e = lim
            else:
                e = opens[i + 1] * (1 + d * slip)               # fill no OPEN do próximo candle + slippage
            if exec_stats is not None:
                exec_stats["preenchidos"] = exec_stats.get("preenchidos", 0) + 1
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
                roe = _roe(pos, closes[i], valor, pos["lev"], taxa_rt / 2.0)
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
                        be = pos["e"] * (1 + d * taxa_rt)        # zero a zero COBRINDO a taxa do round-trip
                        pos["stop"] = max(pos["stop"], be) if d == 1 else min(pos["stop"], be)
                        pos["be"] = be
                if saida == "trailing":
                    if d == 1 and highs[i] >= pos["e"] * (1 + pos["td"]):
                        pos["stop"] = max(pos["stop"], highs[i] * (1 - pos["td"]))
                    elif d == -1 and lows[i] <= pos["e"] * (1 - pos["td"]):
                        pos["stop"] = min(pos["stop"], lows[i] * (1 + pos["td"]))
            if saida_p is not None:
                lev_p = pos["lev"]
                saida_fill = saida_p if motivo == "liquidacao" else saida_p * (1 - d * slip)  # liq = preço de liq (= live)
                move = d * (saida_fill / pos["e"] - 1)
                fcost = d * funding_8h * ((i - pos["i0"]) * tfh / 8) * (valor * lev_p)  # funding: LONG paga>0, SHORT recebe
                pnl = max(valor * lev_p * move - taxa_rt * valor * lev_p - fcost, -valor)
                trades.append({"conv": pos["conv"], "pnl": pnl, "motivo": motivo,
                               "ts": pos["ts"], "ts_saida": int(tss[i]) + tf_ms})
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


def anexar_oi(df, ativo, dias=None, usar_cache=True):
    """[Q-17] Anexa `sum_open_interest` e `d_oi` ao painel de um ativo.

    Uma chamada por moeda, ANTES da varredura -- e nao dentro dela. As 24 configs da grade
    leem a mesma coluna; recalcula-la por config seria 24 vezes o mesmo download para o
    mesmo numero.

    `d_oi` e a diferenca de UMA barra, como o pre-registro fixou: sem limiar, sem janela, sem
    suavizacao. A primeira barra fica NaN por construcao (nao ha barra anterior), e NaN nao
    filtra nada no portao.

    **O merge e por `timestamp` e nao por posicao.** Alinhar por indice suporia que as duas
    series tem exatamente as mesmas barras, na mesma ordem, sem buraco -- e o dump TEM
    buraco (o D+1 de hoje, no minimo). Um desalinhamento de uma barra aqui e o mesmo
    look-ahead de 5 minutos que a §4.1 do plano existiu para matar, so que por outra porta.
    """
    from pesquisa import dados_derivados

    serie = dados_derivados.serie_1h(ativo, dias=dias or len(df), df_ohlcv=df,
                                     usar_cache=usar_cache)
    col = "sum_open_interest"
    out = df.merge(serie[["timestamp", col]], on="timestamp", how="left")
    out["d_oi"] = out[col].diff()
    return out


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
    POLITICAS_SMOKE = [("A stop+flip de regime", {"saida": "regime"}),
                       ("B auto-saida", {"saida": "auto"}),
                       ("C trailing 2% fixo", {"saida": "trailing", "trailing_dist": 0.02}),
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
