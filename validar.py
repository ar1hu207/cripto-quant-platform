"""
Validacao de robustez da Fase 1: o Gestor de Banca funciona em varios ativos?
E qual o efeito do "botao de risco" (0,5% vs 1% por trade)?
"""
from dataclasses import replace
import ccxt

from config import PADRAO as cfg
from dados import baixar_ohlcv
from estrategias.trend import TrendFollowing
from gestao_banca import GestorBanca
from motor import rodar
from metricas import calcular

ATIVOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
RISCOS = [0.005, 0.01]
tf_horas = ccxt.binance().parse_timeframe(cfg.timeframe) / 3600.0

print(f"\n{'ativo':<10}{'risco':>7}{'retorno%':>11}{'B&H%':>10}{'maxDD%':>9}"
      f"{'Sharpe':>8}{'win%':>7}{'verde%':>8}")
print("-" * 70)
for ativo in ATIVOS:
    df = baixar_ohlcv(ativo, cfg.timeframe, dias=cfg.dias)
    for risco in RISCOS:
        c = replace(cfg, par=ativo, risco_por_trade=risco)
        res = rodar(df, TrendFollowing(c), GestorBanca(c), c, tf_horas=tf_horas)
        m = calcular(res, df)
        marca = "  <<" if m["retorno_%"] > m["bh_%"] else ""
        print(f"{ativo:<10}{risco*100:>6.1f}%{m['retorno_%']:>11.1f}{m['bh_%']:>10.1f}"
              f"{m['max_dd_%']:>9.1f}{m['sharpe']:>8.2f}{m['win_rate_%']:>7.1f}"
              f"{m['dias_verdes_%']:>8.1f}{marca}")
    print()
print('"<<" = bateu o buy-and-hold  |  risco = % da banca arriscado por trade\n')
