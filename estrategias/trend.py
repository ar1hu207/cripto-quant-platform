"""Estrategia trend-following (EMA + ADX). Migrada da versao monolitica anterior."""
import numpy as np

from indicadores import ema, atr, adx
from .base import Estrategia, Sinal


class TrendFollowing(Estrategia):
    nome = "trend"

    def __init__(self, cfg):
        self.cfg = cfg

    def preparar(self, df):
        df = df.copy()
        c = self.cfg
        df["ema_rapida"] = ema(df["close"], c.ema_rapida)
        df["ema_lenta"] = ema(df["close"], c.ema_lenta)
        df["atr"] = atr(df, c.atr_periodo)
        df["adx"], _, _ = adx(df, c.adx_periodo)
        # arrays p/ velocidade no loop
        self._adx = df["adx"].values
        self._er = df["ema_rapida"].values
        self._el = df["ema_lenta"].values
        self._atr = df["atr"].values
        self._close = df["close"].values
        return df

    def avaliar(self, df, i, pos=0) -> Sinal:
        c = self.cfg
        a, el, atr_v, close = self._adx[i], self._el[i], self._atr[i], self._close[i]
        if np.isnan(a) or np.isnan(el) or np.isnan(atr_v) or close <= 0:
            return Sinal(0, motivo="warmup")
        if a < c.adx_min:
            return Sinal(0, motivo="lateral")
        direcao = 1 if self._er[i] > el else -1
        stop_dist = c.trail_atr * atr_v / close
        return Sinal(direcao, stop_dist=stop_dist, motivo="tendencia", trailing=True)
