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
    hold real. Erro a favor do resultado: carry menor = P&L maior, contra a conclusão negativa.

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


def backtest_ativo(ativo, min_conv, valor, lev, tf=TF, dias=DIAS,
                   estrategia="tendencia", df=None, adx_min=25, adx_max_rev=22,
                   max_hold=20, taxa=TAXA, slip=0.0002, funding_8h=0.0, tf_horas=None,
                   sinal_fn=None):
    """Backtest com PARIDADE honesta: sinal no candle FECHADO i, execução no OPEN do
    candle SEGUINTE (i+1) + slippage. estrategia: 'tendencia' (sai no flip de regime)
    ou 'reversao' (alvo = volta à média + time-stop). df pré-carregado evita re-baixar.

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

    **`sinal_fn` — de onde vem o sinal, e por que ele passou a ser injetável.** Default:
    `scoring.pontuar` (ou `pontuar_reversao`), que é a paridade com o vivo e continua sendo o
    que roda em produção de pesquisa. Injetar existe por duas razões escritas:

      * **provar este motor sem rede.** Com o sinal fixo em `pontuar`, testar "trajetória
        conhecida → saída esperada" exige construir um `df` que ao mesmo tempo dispare o
        scoring E ande pelo caminho que o teste quer — duas restrições que brigam, e o teste
        acaba provando o scoring em vez da saída. Com o sinal injetado, a trajetória é livre.
      * **a dívida do `F9`** (`pesquisa/validacao.py`, docstring de `controle_nulo`): o
        controle nulo COMPLETO passa M geradores de sinal aleatório pelo pipeline inteiro, e
        estava bloqueado exatamente em "`backtest_ativo` não aceita uma função de sinal".
        Aceita agora; o que falta é orçamento de relógio, não território.

    O flip de regime também passou a usar `fn`, não `pontuar` fixo: entrada e saída de uma
    mesma política têm de ler a mesma fonte, senão um sinal injetado abriria trades que só o
    scoring real conseguiria fechar. Para `estrategia="tendencia"` sem injeção nada muda —
    `fn` É `pontuar`."""
    if df is None:
        df = preparar(baixar_ohlcv(ativo, tf, dias=dias))
    tfh = _horas_por_barra(df, tf_horas, tf)                    # medida no df, nao adivinhada
    tf_ms = int(round(tfh * 3_600_000))                         # duracao do candle, para o `ts_saida`
    opens, closes, tss = df["open"].values, df["close"].values, df["timestamp"].values
    highs, lows = df["high"].values, df["low"].values
    mids = df["bb_mid"].values
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
            pos = dict(d=d, e=e, conv=p["conviccao"], i0=i + 1, ts=int(tss[i + 1]),
                       stop=e * (1 - d * p["stop_dist"]), liq=e * (1 - d * (LIQ_BUFFER / lev)))
        else:
            d, saida, motivo = pos["d"], None, None
            hit_liq = (d == 1 and lows[i] <= pos["liq"]) or (d == -1 and highs[i] >= pos["liq"])
            hit_stop = (d == 1 and lows[i] <= pos["stop"]) or (d == -1 and highs[i] >= pos["stop"])
            if hit_liq and hit_stop:                            # empate intrabar: o mais PERTO da entrada bate 1o
                if abs(pos["e"] - pos["stop"]) <= abs(pos["e"] - pos["liq"]):
                    saida, motivo = pos["stop"], "stop"
                else:
                    saida, motivo = pos["liq"], "liquidacao"
            elif hit_liq:
                saida, motivo = pos["liq"], "liquidacao"
            elif hit_stop:
                saida, motivo = pos["stop"], "stop"
            elif estrategia == "reversao":
                alvo = mids[i - 1]                              # mid do candle ANTERIOR (sem look-ahead intrabar)
                if (d == 1 and highs[i] >= alvo) or (d == -1 and lows[i] <= alvo):
                    saida, motivo = alvo, "alvo"
                elif i - pos["i0"] >= max_hold:                 # time-stop (não fica preso)
                    saida, motivo = closes[i], "tempo"
            else:
                p = fn(df, i)                                   # a MESMA fonte de sinal da entrada
                if p and p["direcao"] != d:
                    saida, motivo = closes[i], "regime"
            if saida is not None:
                saida_fill = saida if motivo == "liquidacao" else saida * (1 - d * slip)  # liq = preço de liq (= live)
                move = d * (saida_fill / pos["e"] - 1)
                fcost = d * funding_8h * ((i - pos["i0"]) * tfh / 8) * (valor * lev)  # funding: LONG paga>0, SHORT recebe
                pnl = max(valor * lev * move - 2 * taxa * valor * lev - fcost, -valor)
                trades.append({"conv": pos["conv"], "pnl": pnl, "motivo": motivo,
                               "ts": pos["ts"], "ts_saida": int(tss[i]) + tf_ms})
                pos = None
    return trades


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


if __name__ == "__main__":
    MIN_CONV, VALOR, LEV = 25, 100, 10
    print(f"BACKTEST INTEGRADO (paridade c/ a plataforma) | {len(ATIVOS)} ativos | {TF} | {DIAS}d | "
          f"corte>={MIN_CONV} | R${VALOR} @ {LEV}x")
    todos = []
    for a in ATIVOS:
        todos += backtest_ativo(a, MIN_CONV, VALOR, LEV)
    relatorio(todos, VALOR, LEV)
