"""
Fase 2 - valida a mean-reversion SOZINHA e compara com a trend-following,
nos mesmos ativos, sob o mesmo Gestor de Banca (risco 0,5%, 1x).
"""
from dataclasses import replace
import ccxt

from config import PADRAO as cfg
from dados import baixar_ohlcv
from estrategias.trend import TrendFollowing
from estrategias.mean_reversion import MeanReversion
from gestao_banca import GestorBanca
from motor import rodar
from metricas import calcular

ATIVOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
ESTRATEGIAS = [("trend", TrendFollowing), ("mean-rev", MeanReversion)]
tf_horas = ccxt.binance().parse_timeframe(cfg.timeframe) / 3600.0

print(f"\n{'ativo':<10}{'estrategia':<11}{'trades':>8}{'retorno%':>11}{'B&H%':>9}"
      f"{'maxDD%':>9}{'Sharpe':>8}{'win%':>7}")
print("-" * 73)
for ativo in ATIVOS:
    df = baixar_ohlcv(ativo, cfg.timeframe, dias=cfg.dias)
    for nome, Cls in ESTRATEGIAS:
        c = replace(cfg, par=ativo)
        res = rodar(df, Cls(c), GestorBanca(c), c, tf_horas=tf_horas)
        m = calcular(res, df)
        marca = "  <<" if m["retorno_%"] > m["bh_%"] else ""
        print(f"{ativo:<10}{nome:<11}{m['n_trades']:>8}{m['retorno_%']:>11.1f}"
              f"{m['bh_%']:>9.1f}{m['max_dd_%']:>9.1f}{m['sharpe']:>8.2f}"
              f"{m['win_rate_%']:>7.1f}{marca}")
    print()
print('"<<" = bateu o buy-and-hold\n')
