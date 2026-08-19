"""
Pontuação de convicção — usada IGUAL no engine ao vivo (signal_engine) e no
backtest (backtest_plataforma). Esse compartilhamento É a paridade backtest<->live.
"""
import numpy as np

from indicadores import ema, atr, adx, rsi, donchian, bollinger


def preparar(df):
    df = df.copy()
    df["ema_r"] = ema(df["close"], 20)
    df["ema_l"] = ema(df["close"], 50)
    df["atr"] = atr(df, 14)
    df["adx"], _, _ = adx(df, 14)
    df["rsi"] = rsi(df["close"], 14)
    dch, dcl = donchian(df, 20)
    df["dch"] = dch.shift(1)     # canal ANTERIOR (sem look-ahead)
    df["dcl"] = dcl.shift(1)
    df["bb_mid"], df["bb_up"], df["bb_lo"] = bollinger(df["close"], 20, 2.0)
    return df


def pontuar(df, i):
    """Convicção (0-100) + direção + stop pra barra i. None se ainda em warmup."""
    c = df["close"].iloc[i]
    adxv, r = df["adx"].iloc[i], df["rsi"].iloc[i]
    er, el, atrv = df["ema_r"].iloc[i], df["ema_l"].iloc[i], df["atr"].iloc[i]
    if np.isnan(adxv) or np.isnan(el) or np.isnan(atrv) or c <= 0:
        return None
    vol = df["volume"].iloc[i]
    volm = df["volume"].iloc[max(0, i - 19):i + 1].mean()
    dch_a, dcl_a = df["dch"].iloc[i], df["dcl"].iloc[i]

    direcao = 1 if er > el else -1
    score, motivos = 0.0, []
    if adxv >= 25:
        score += 5 + min((adxv - 25) / 25, 1) * 35
        motivos.append(f"ADX {adxv:.0f}")
    score += min(abs(er - el) / c * 100 / 2, 1) * 10
    if direcao == 1 and not np.isnan(dch_a) and c >= dch_a:
        score += 22; motivos.append("rompeu resistência")
    elif direcao == -1 and not np.isnan(dcl_a) and c <= dcl_a:
        score += 22; motivos.append("rompeu suporte")
    if direcao == 1 and 45 <= r <= 72:
        score += 18; motivos.append(f"RSI {r:.0f}")
    elif direcao == -1 and 28 <= r <= 55:
        score += 18; motivos.append(f"RSI {r:.0f}")
    if vol > volm * 1.2:
        score += 15; motivos.append("volume alto")

    return dict(direcao=direcao, conviccao=min(round(score), 100),
                motivos=", ".join(motivos) or "fraco", stop_dist=3 * atrv / c,
                adx=round(adxv, 1), n_fatores=len(motivos), tipo="tendencia")


def pontuar_reversao(df, i):
    """Reversão à média — pra mercado LATERAL (ADX baixo). Compra fundo / vende topo
    do range (Bollinger + RSI extremo). É CONTRARIAN: aposta contra o movimento atual.
    None em warmup; conviccao 0 se o preço não está num extremo."""
    c = df["close"].iloc[i]
    adxv, r, atrv = df["adx"].iloc[i], df["rsi"].iloc[i], df["atr"].iloc[i]
    bb_up, bb_lo = df["bb_up"].iloc[i], df["bb_lo"].iloc[i]
    if np.isnan(adxv) or np.isnan(bb_up) or np.isnan(atrv) or c <= 0:
        return None
    vol = df["volume"].iloc[i]
    volm = df["volume"].iloc[max(0, i - 19):i + 1].mean()

    score, motivos, direcao = 0.0, [], 0
    if c <= bb_lo and r < 38:                      # sobrevendido -> espera repique (LONG)
        direcao = 1
        score += 30; motivos.append("tocou banda inferior")
        score += min((38 - r) / 13, 1) * 28; motivos.append(f"RSI {r:.0f} sobrevendido")
    elif c >= bb_up and r > 62:                    # sobrecomprado -> espera queda (SHORT)
        direcao = -1
        score += 30; motivos.append("tocou banda superior")
        score += min((r - 62) / 13, 1) * 28; motivos.append(f"RSI {r:.0f} sobrecomprado")
    else:
        return dict(direcao=1, conviccao=0, motivos="fora do range", stop_dist=2.5 * atrv / c,
                    adx=round(adxv, 1), n_fatores=0, tipo="reversao")

    if adxv < 20:                                  # confirma mercado lateral (reversão é mais segura)
        score += 22; motivos.append(f"lateral (ADX {adxv:.0f})")
    elif adxv < 25:
        score += 10; motivos.append(f"ADX {adxv:.0f}")
    if vol > volm * 1.3:                           # volume de capitulação reforça o extremo
        score += 15; motivos.append("volume alto")

    return dict(direcao=direcao, conviccao=min(round(score), 100),
                motivos=", ".join(motivos), stop_dist=2.5 * atrv / c,
                adx=round(adxv, 1), n_fatores=len(motivos), tipo="reversao")
