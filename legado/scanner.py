"""
SCANNER DE OPORTUNIDADES — varre varios ativos e ranqueia as melhores entradas
AGORA, com um score de conviccao (0-100) combinando tendencia + ADX + rompimento
(Donchian/S-R) + RSI + volume. Esse e o "ecossistema que acha os melhores trades".
Voce decide se entra, com quanto e qual alavancagem.

Rodar:  python scanner.py
"""
import sys
import ccxt
import pandas as pd

from indicadores import ema, atr, adx, rsi, donchian

try:
    sys.stdout.reconfigure(encoding="utf-8")   # console Windows aceita acentos/barras
except Exception:
    pass

ATIVOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
          "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "LTC/USDT"]
TF = "1h"
ex = ccxt.binance({"enableRateLimit": True})


def analisa(a):
    raw = ex.fetch_ohlcv(a, timeframe=TF, limit=250)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["ema_r"] = ema(df["close"], 20)
    df["ema_l"] = ema(df["close"], 50)
    df["atr"] = atr(df, 14)
    df["adx"], _, _ = adx(df, 14)
    df["rsi"] = rsi(df["close"], 14)
    dch, dcl = donchian(df, 20)
    i = len(df) - 1
    c = df["close"].iloc[i]
    adxv = df["adx"].iloc[i]
    r = df["rsi"].iloc[i]
    er, el = df["ema_r"].iloc[i], df["ema_l"].iloc[i]
    atrv = df["atr"].iloc[i]
    vol, volm = df["volume"].iloc[i], df["volume"].iloc[-20:].mean()
    dch_ant, dcl_ant = dch.iloc[i - 1], dcl.iloc[i - 1]   # canal anterior (sem look-ahead)

    direcao = 1 if er > el else -1
    score, motivos = 0.0, []

    if adxv >= 25:                                   # forca de tendencia
        score += 5 + min((adxv - 25) / 25, 1) * 35
        motivos.append(f"ADX {adxv:.0f}")
    score += min(abs(er - el) / c * 100 / 2, 1) * 10  # separacao das medias

    if direcao == 1 and c >= dch_ant:                # rompimento (S/R)
        score += 22; motivos.append("rompeu resistencia")
    elif direcao == -1 and c <= dcl_ant:
        score += 22; motivos.append("rompeu suporte")

    if direcao == 1 and 45 <= r <= 72:               # momentum alinhado
        score += 18; motivos.append(f"RSI {r:.0f}")
    elif direcao == -1 and 28 <= r <= 55:
        score += 18; motivos.append(f"RSI {r:.0f}")
    elif (direcao == 1 and r > 72) or (direcao == -1 and r < 28):
        motivos.append(f"RSI esticado {r:.0f}")

    if vol > volm * 1.2:                             # confirmacao de volume
        score += 15; motivos.append("volume alto")

    return dict(ativo=a, dir="LONG" if direcao == 1 else "SHORT", score=min(round(score), 100),
                preco=c, dist_stop=round(3 * atrv / c * 100, 2),
                motivos=", ".join(motivos) or "sinal fraco")


def main():
    print(f"Varrendo {len(ATIVOS)} ativos em {TF}...\n")
    res = []
    for a in ATIVOS:
        try:
            res.append(analisa(a))
        except Exception as e:
            print(f"  (falha {a}: {e})")
    res.sort(key=lambda x: -x["score"])

    print("=" * 80)
    print(" MELHORES OPORTUNIDADES AGORA (ranqueadas por convicção)")
    print("=" * 80)
    print(f"{'#':>2} {'ATIVO':<10}{'DIR':<6}{'CONV.':>6} {'':<11}{'PREÇO':>12}{'STOP':>7}  SINAIS")
    print("-" * 80)
    for i, r in enumerate(res, 1):
        barra = "█" * (r["score"] // 10)
        print(f"{i:>2} {r['ativo']:<10}{r['dir']:<6}{r['score']:>5} {barra:<11}{r['preco']:>12,.4f}"
              f"{r['dist_stop']:>6.1f}%  {r['motivos']}")
    print("-" * 80)
    print("Convicção 0-100 (tendência+ADX+rompimento+RSI+volume). Score alto = setup mais forte.")
    print("VOCÊ decide entrada, tamanho e alavancagem. STOP = distância sugerida (3×ATR).")


if __name__ == "__main__":
    main()
