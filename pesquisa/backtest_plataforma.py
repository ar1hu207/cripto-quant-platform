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

from pesquisa.dados import baixar_ohlcv
from scoring import preparar, pontuar, pontuar_reversao

TAXA = 0.0005          # igual à plataforma (0,05%/lado)
LIQ_BUFFER = 0.9
ATIVOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
          "XRP/USDT", "ADA/USDT", "DOGE/USDT", "AVAX/USDT"]
TF, DIAS = "15m", 60


def backtest_ativo(ativo, min_conv, valor, lev, tf=TF, dias=DIAS,
                   estrategia="tendencia", df=None, adx_min=25, adx_max_rev=22,
                   max_hold=20, taxa=TAXA, slip=0.0002, funding_8h=0.0, tf_horas=None):
    """Backtest com PARIDADE honesta: sinal no candle FECHADO i, execução no OPEN do
    candle SEGUINTE (i+1) + slippage. estrategia: 'tendencia' (sai no flip de regime)
    ou 'reversao' (alvo = volta à média + time-stop). df pré-carregado evita re-baixar."""
    if df is None:
        df = preparar(baixar_ohlcv(ativo, tf, dias=dias))
    tfh = tf_horas or {"5m": 5 / 60, "15m": 0.25, "30m": 0.5, "1h": 1, "4h": 4, "1d": 24}.get(tf, 0.25)
    opens, closes, tss = df["open"].values, df["close"].values, df["timestamp"].values
    highs, lows = df["high"].values, df["low"].values
    mids = df["bb_mid"].values
    fn = pontuar if estrategia == "tendencia" else pontuar_reversao
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
                p = pontuar(df, i)
                if p and p["direcao"] != d:
                    saida, motivo = closes[i], "regime"
            if saida is not None:
                saida_fill = saida if motivo == "liquidacao" else saida * (1 - d * slip)  # liq = preço de liq (= live)
                move = d * (saida_fill / pos["e"] - 1)
                fcost = d * funding_8h * ((i - pos["i0"]) * tfh / 8) * (valor * lev)  # funding: LONG paga>0, SHORT recebe
                pnl = max(valor * lev * move - 2 * taxa * valor * lev - fcost, -valor)
                trades.append({"conv": pos["conv"], "pnl": pnl, "motivo": motivo, "ts": pos["ts"]})
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
