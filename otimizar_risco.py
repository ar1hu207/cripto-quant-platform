"""
Curva RISCO x RETORNO x DRAWDOWN no ciclo completo (2022-2026).
Acha a zona agressiva-mas-otima e mostra onde mais risco passa a DESTRUIR o
crescimento composto (imposto da volatilidade / Kelly). Rails desligados de
proposito p/ ver o comportamento puro do risco.
"""
from dataclasses import replace
import ccxt
import numpy as np
import pandas as pd

from config import PADRAO as cfg
from dados import baixar_ohlcv
from estrategias.trend import TrendFollowing
from gestao_banca import GestorBanca
from motor_portfolio import rodar_portfolio
from metricas import calcular

ATIVOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TF, DIAS = "4h", 1800
INI, FIM = "2022-01-01", "2026-06-01"
tf_horas = ccxt.binance().parse_timeframe(TF) / 3600.0
anos = (pd.Timestamp(FIM) - pd.Timestamp(INI)).days / 365.25
dados = {a: baixar_ohlcv(a, TF, dias=DIAS) for a in ATIVOS}

RISCOS = [0.005, 0.01, 0.02, 0.03, 0.05, 0.08]
SELIC = 0.105  # ~10,5%/ano (referencia "investimento broxa")

print(f"\nCiclo {INI} -> {FIM}  ({anos:.1f} anos) | portfolio BTC+ETH+SOL | rails OFF p/ analise")
print(f"{'risco/trade':>11}{'banca final':>13}{'CAGR%':>8}{'maxDD%':>9}{'Sharpe':>8}{'anos p/ 10x':>13}")
print("-" * 62)
for risco in RISCOS:
    c = replace(cfg, max_posicoes=3, timeframe=TF, risco_por_trade=risco,
                alavancagem=10.0, kill_switch_dd=0.99, limite_perda_dia=0.99,
                max_risco_aberto=1.0)
    gestor = GestorBanca(c)
    res = rodar_portfolio(dados, lambda: TrendFollowing(c), gestor, c,
                          tf_horas=tf_horas, inicio=INI, fim=FIM)
    m = calcular(res, dados[ATIVOS[0]])
    cagr = (m["banca_final"] / 1000.0) ** (1 / anos) - 1
    t10 = np.log(10) / np.log(1 + cagr) if cagr > 0 else float("inf")
    print(f"{risco*100:>10.1f}%{m['banca_final']:>13,.0f}{cagr*100:>8.1f}"
          f"{m['max_dd_%']:>9.1f}{m['sharpe']:>8.2f}{t10:>13.1f}")

print(f"\nReferencia Selic ~{SELIC*100:.1f}%/ano -> anos p/ 10x: {np.log(10)/np.log(1+SELIC):.1f}")
print("CAGR = crescimento composto anual. Repare onde o CAGR PARA de subir mesmo com mais risco.\n")
