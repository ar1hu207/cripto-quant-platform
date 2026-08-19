"""
Backtest da estrategia de SCALP do usuario: rompimento -> alvo pequeno (1-2%),
stop apertado (0,5-3%), alavancado (10x/20x). Mede o WIN RATE real e se a banca
cresce ou morre. Usa 5m (timeframe fino, justo p/ stops apertados) e checa
intrabar se stop ou alvo bateu primeiro (assume STOP em empate = conservador).
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import numpy as np
import pandas as pd

from dados import baixar_ohlcv
from indicadores import ema

ATIVOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TF, DIAS = "5m", 90
TAKER = 0.0005   # 0,05%/lado (taker futuros)


def trades_scalp(df, tgt, stp, don=20):
    df = df.reset_index(drop=True)
    high, low, close = df["high"].values, df["low"].values, df["close"].values
    dch = pd.Series(high).rolling(don).max().shift(1).values
    dcl = pd.Series(low).rolling(don).min().shift(1).values
    em = ema(df["close"], 50).values
    n = len(df); i = don + 2; out = []
    while i < n - 1:
        c = close[i]; d = 0
        if not np.isnan(dch[i]) and c > dch[i] and c > em[i]:
            d = 1
        elif not np.isnan(dcl[i]) and c < dcl[i] and c < em[i]:
            d = -1
        if d == 0:
            i += 1; continue
        entry = c; tp = entry * (1 + d * tgt); sl = entry * (1 - d * stp)
        j = i + 1; res = None
        while j < n:
            if d == 1:
                if low[j] <= sl: res = -stp; break       # empate -> stop primeiro
                if high[j] >= tp: res = tgt; break
            else:
                if high[j] >= sl: res = -stp; break
                if low[j] <= tp: res = tgt; break
            j += 1
        if res is None:
            break
        out.append(res); i = j + 1
    return np.array(out)


print(f"SCALP (rompimento Donchian + filtro EMA50) | {TF} | {DIAS} dias | taxa {TAKER*100:.2f}%/lado\n")
print(f"{'alvo':>5}{'stop':>7}{'R:R':>6}{'lev':>5}{'trades':>8}{'win%':>7}{'precisa':>9}{'R$1k vira':>14}")
print("-" * 71)
for tgt, stp in [(0.01, 0.005), (0.015, 0.0075), (0.02, 0.01), (0.02, 0.03)]:
    allr = np.concatenate([trades_scalp(baixar_ohlcv(a, TF, dias=DIAS), tgt, stp) for a in ATIVOS])
    win = (allr > 0).mean() * 100
    for lev in [10, 20]:
        r = lev * allr - 2 * TAKER * lev          # retorno sobre a margem, liquido de taxa
        eq = 1000.0
        for x in r:
            eq *= (1 + x)
            if eq <= 1:
                eq = 0; break                      # conta zerada
        w = lev * tgt - 2 * TAKER * lev
        loss = lev * stp + 2 * TAKER * lev
        be = loss / (w + loss) * 100               # win rate de breakeven
        print(f"{tgt*100:>4.1f}%{stp*100:>6.2f}%{tgt/stp:>5.1f}{lev:>4}x{len(allr):>8}"
              f"{win:>6.1f}%{be:>8.1f}%{eq:>14,.0f}")
print("\nwin% = acertividade REAL | precisa = win% minimo p/ nao perder | R$1k vira = banca final compondo")
