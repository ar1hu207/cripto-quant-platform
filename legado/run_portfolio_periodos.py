"""
Teste de regime do PORTFOLIO trend (BTC+ETH+SOL) ao longo de ~5 anos,
fatiado por mercado: bull, bear e o ciclo completo. Banca reiniciada por periodo.
Responde: o edge se sustenta atraves dos regimes ou foi sorte do periodo recente?
"""
from dataclasses import replace
import ccxt

from config import PADRAO as cfg
from dados import baixar_ohlcv
from estrategias.trend import TrendFollowing
from gestao_banca import GestorBanca
from motor_portfolio import rodar_portfolio
from metricas import calcular

ATIVOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TF, DIAS = "4h", 1800
tf_horas = ccxt.binance().parse_timeframe(TF) / 3600.0
c = replace(cfg, max_posicoes=3, timeframe=TF)
dados = {a: baixar_ohlcv(a, TF, dias=DIAS) for a in ATIVOS}

PERIODOS = {
    "BULL  (jan/23 -> mar/24)": ("2023-01-01", "2024-03-15"),
    "BEAR  (dez/24 -> jun/26)": ("2024-12-01", "2026-06-01"),
    "GERAL (jan/22 -> jun/26)": ("2022-01-01", "2026-06-01"),
}

print(f"\nPORTFOLIO trend (BTC+ETH+SOL), 4h, 0,5%/trade, 1x, max 3 posicoes")
print(f"{'periodo':<26}{'trades':>7}{'retorno%':>11}{'B&H%':>10}{'maxDD%':>9}"
      f"{'Sharpe':>8}{'verde%':>8}")
print("-" * 79)
for nome, (ini, fim) in PERIODOS.items():
    gestor = GestorBanca(c)
    res = rodar_portfolio(dados, lambda: TrendFollowing(c), gestor, c,
                          tf_horas=tf_horas, inicio=ini, fim=fim)
    m = calcular(res, dados[ATIVOS[0]])
    marca = "  <<" if m["retorno_%"] > m["bh_%"] else ""
    print(f"{nome:<26}{m['n_trades']:>7}{m['retorno_%']:>11.1f}{m['bh_%']:>10.1f}"
          f"{m['max_dd_%']:>9.1f}{m['sharpe']:>8.2f}{m['dias_verdes_%']:>8.1f}{marca}")
print('\n"<<" = bateu o buy-and-hold (media equal-weight dos 3 ativos)\n')
