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
    Cobrar um quarto do carry significa pagar 1/4 quando o livro é net-LONG (P&L superestimado)
    e RECEBER 1/4 quando é net-SHORT (P&L subestimado). No período de 1.095 dias registrado na
    §6 do `ITEM1-VALIDACAO-RIGOROSA.md` o livro foi net-SHORT — a saída literal diz
    `COM x SEM funding: R$+993 x R$+948 -> efeito do carry: R$+45, net-SHORT no período` —,
    então ali o erro foi PARA MENOS. Quem reportar esta correção tem de dizer sobre qual
    período fala; a magnitude é sempre 4x, o sinal não.

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
TRAILING_DIST = 0.02


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
                   sinal_fn=None, saida="regime", trailing_dist=TRAILING_DIST,
                   trailing_k_atr=None, alvo_roe=ALVO_ROE):
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
            d = p["direcao"]
            e = opens[i + 1] * (1 + d * slip)                   # fill no OPEN do próximo candle + slippage
            # distância do trailing FIXADA na entrada: k×ATR/preço se pedido, senão o % fixo
            td = trailing_dist
            if trailing_k_atr and atrv is not None and atrv[i] == atrv[i] and e > 0:
                td = trailing_k_atr * atrv[i] / e
            pos = dict(d=d, e=e, conv=p["conviccao"], i0=i + 1, ts=int(tss[i + 1]), td=td,
                       stop=e * (1 - d * p["stop_dist"]), liq=e * (1 - d * (LIQ_BUFFER / lev)))
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
                roe = _roe(pos, closes[i], valor, lev, taxa)
                if _sinais_reversao(d, i, closes, rsi, ema_r, ema_l) and (
                        roe >= alvo_roe or roe > ROE_MIN_LUCRO):
                    saida_p, motivo = closes[i], "auto-saida"
            else:                                               # A: flip de regime
                p = fn(df, i)                                   # a MESMA fonte de sinal da entrada
                if p and p["direcao"] != d:
                    saida_p, motivo = closes[i], "regime"
            if saida_p is None and saida == "trailing":
                # trailing DEPOIS da checagem: o stop só se move para o candle seguinte, porque
                # o OHLC não diz se o topo veio antes ou depois do fundo dentro deste candle
                if d == 1 and highs[i] >= pos["e"] * (1 + pos["td"]):
                    pos["stop"] = max(pos["stop"], highs[i] * (1 - pos["td"]))
                elif d == -1 and lows[i] <= pos["e"] * (1 - pos["td"]):
                    pos["stop"] = min(pos["stop"], lows[i] * (1 + pos["td"]))
            if saida_p is not None:
                saida_fill = saida_p if motivo == "liquidacao" else saida_p * (1 - d * slip)  # liq = preço de liq (= live)
                move = d * (saida_fill / pos["e"] - 1)
                fcost = d * funding_8h * ((i - pos["i0"]) * tfh / 8) * (valor * lev)  # funding: LONG paga>0, SHORT recebe
                pnl = max(valor * lev * move - 2 * taxa * valor * lev - fcost, -valor)
                trades.append({"conv": pos["conv"], "pnl": pnl, "motivo": motivo,
                               "ts": pos["ts"], "ts_saida": int(tss[i]) + tf_ms})
                pos = None
    return trades


def _motivo_stop(pos):
    """'trailing' quando o stop já está em lucro, 'stop' quando não — a MESMA distinção que
    `simulador._fecha_stop` grava em `trades.motivo_saida`. Vale a pena manter o vocabulário
    igual: é o que permite comparar a tabela de motivos do backtest com a do banco vivo sem
    tradução no meio."""
    d = pos["d"]
    em_lucro = (d == 1 and pos["stop"] >= pos["e"]) or (d == -1 and pos["stop"] <= pos["e"])
    return "trailing" if em_lucro else "stop"


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
