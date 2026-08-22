"""
Pedra 2 - Classificador de regime MECANICO (sem LLM).
Regra:
  - ADX >= adx_min  -> mercado em tendencia (vale operar na direcao)
  - EMA rapida > lenta -> alta  => LONG (+1)
  - EMA rapida < lenta -> baixa => SHORT (-1)
  - ADX < adx_min  -> lateral/indeciso => FLAT (0, fica de fora)
"""
import numpy as np

from indicadores import ema, atr, adx


def gerar_sinais(df, ema_rapida=20, ema_lenta=50, adx_periodo=14,
                 adx_min=25, atr_periodo=14, filtro_tendencia=False, ma_longa=200):
    df = df.copy()
    df["ema_rapida"] = ema(df["close"], ema_rapida)
    df["ema_lenta"] = ema(df["close"], ema_lenta)
    df["atr"] = atr(df, atr_periodo)
    df["adx"], df["plus_di"], df["minus_di"] = adx(df, adx_periodo)
    df["ma_longa"] = df["close"].rolling(ma_longa).mean()

    regime = np.zeros(len(df))
    em_tendencia = (df["adx"] >= adx_min).values
    em_alta = (df["ema_rapida"] > df["ema_lenta"]).values

    regime[em_tendencia & em_alta] = 1     # LONG
    regime[em_tendencia & ~em_alta] = -1   # SHORT

    if filtro_tendencia:
        # Filtro anti-whipsaw: so opera A FAVOR da tendencia macro (media longa).
        # LONG so quando preco ACIMA da MA longa; SHORT so quando ABAIXO. Senao, FLAT.
        acima = (df["close"] > df["ma_longa"]).values
        regime[(regime == 1) & ~acima] = 0
        regime[(regime == -1) & acima] = 0

    df["regime"] = regime
    return df
