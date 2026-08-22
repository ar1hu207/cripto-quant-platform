"""
Estrategia mean-reversion: compra sobrevendido / vende sobrecomprado,
aposta na volta a media. Boa em mercado lateral (onde a trend apanha).
Entrada: preco fora da Banda de Bollinger + RSI no extremo.
Saida:   volta a media (take-profit) OU stop fixo (ATR).
"""
import numpy as np

from indicadores import rsi, bollinger, atr, adx
from .base import Estrategia, Sinal


class MeanReversion(Estrategia):
    nome = "mean_reversion"

    def __init__(self, cfg):
        self.cfg = cfg

    def preparar(self, df):
        df = df.copy()
        c = self.cfg
        df["rsi"] = rsi(df["close"], c.rsi_periodo)
        mid, up, low = bollinger(df["close"], c.bb_periodo, c.bb_k)
        df["bb_mid"], df["bb_up"], df["bb_low"] = mid, up, low
        df["atr"] = atr(df, c.atr_periodo)
        df["adx"], _, _ = adx(df, c.adx_periodo)
        self._close = df["close"].values
        self._rsi = df["rsi"].values
        self._mid = mid.values
        self._up = up.values
        self._low = low.values
        self._atr = df["atr"].values
        self._adx = df["adx"].values
        return df

    def avaliar(self, df, i, pos=0) -> Sinal:
        c = self.cfg
        close, r = self._close[i], self._rsi[i]
        mid, up, low, a = self._mid[i], self._up[i], self._low[i], self._atr[i]
        if np.isnan(r) or np.isnan(mid) or np.isnan(a) or close <= 0:
            return Sinal(0, motivo="warmup")

        stop_dist = c.mr_stop_atr * a / close

        # JA posicionado: segura ate reverter a media (take-profit)
        if pos == 1:
            if close >= mid:
                return Sinal(0, motivo="alvo-media")
            return Sinal(1, stop_dist=stop_dist, trailing=False, motivo="segura-long")
        if pos == -1:
            if close <= mid:
                return Sinal(0, motivo="alvo-media")
            return Sinal(-1, stop_dist=stop_dist, trailing=False, motivo="segura-short")

        # FLAT: so entra se NAO ha tendencia forte (mercado lateral)
        adxv = self._adx[i]
        if np.isnan(adxv) or adxv >= c.mr_adx_max:
            return Sinal(0, motivo="tendencia-forte-evita")
        if close < low and r < c.rsi_baixo:
            return Sinal(1, stop_dist=stop_dist, trailing=False, motivo="sobrevendido")
        if close > up and r > c.rsi_alto:
            return Sinal(-1, stop_dist=stop_dist, trailing=False, motivo="sobrecomprado")
        return Sinal(0, motivo="sem-setup")
