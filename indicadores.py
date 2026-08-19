"""
Indicadores tecnicos calculados na mao (sem dependencia extra).
EMA (tendencia), ATR (volatilidade), ADX (forca da tendencia).
"""
import numpy as np
import pandas as pd


def ema(serie, span):
    return serie.ewm(span=span, adjust=False).mean()


def _true_range(df):
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    return pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)


def atr(df, periodo=14):
    tr = _true_range(df)
    # suavizacao de Wilder
    return tr.ewm(alpha=1 / periodo, adjust=False).mean()


def adx(df, periodo=14):
    h, l = df["high"], df["low"]
    up = h.diff()
    down = -l.diff()

    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    tr = _true_range(df)
    atr_ = tr.ewm(alpha=1 / periodo, adjust=False).mean()

    plus_dm = pd.Series(plus_dm, index=df.index).ewm(alpha=1 / periodo, adjust=False).mean()
    minus_dm = pd.Series(minus_dm, index=df.index).ewm(alpha=1 / periodo, adjust=False).mean()

    atr_ = atr_.replace(0, np.nan)               # evita 0/0=NaN silencioso em mercado flat
    plus_di = 100 * plus_dm / atr_
    minus_di = 100 * minus_dm / atr_

    soma = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / soma
    adx_ = dx.ewm(alpha=1 / periodo, adjust=False).mean()

    return adx_, plus_di, minus_di


def rsi(serie, periodo=14):
    delta = serie.diff()
    ganho = delta.clip(lower=0)
    perda = -delta.clip(upper=0)
    avg_ganho = ganho.ewm(alpha=1 / periodo, adjust=False).mean()
    avg_perda = perda.ewm(alpha=1 / periodo, adjust=False).mean()
    rs = avg_ganho / avg_perda
    return 100 - 100 / (1 + rs)


def bollinger(serie, periodo=20, k=2.0):
    media = serie.rolling(periodo).mean()
    desvio = serie.rolling(periodo).std(ddof=0)   # populacional (Bollinger canônico), não amostral
    return media, media + k * desvio, media - k * desvio


def donchian(df, periodo=20):
    """Canal de Donchian: maxima e minima dos ultimos `periodo` candles (base de S/R e breakout)."""
    return df["high"].rolling(periodo).max(), df["low"].rolling(periodo).min()
