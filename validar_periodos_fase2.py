"""
Teste JUSTO: trend vs mean-reversion em BULL (terreno da mean-rev) e BEAR.
Timeframe 4h, ~5 anos de historico fatiado por periodo. Risco 0,5%, 1x.
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
ESTRAT = [("trend", TrendFollowing), ("mean-rev", MeanReversion)]
TF, DIAS = "4h", 1800
tf_horas = ccxt.binance().parse_timeframe(TF) / 3600.0
PERIODOS = {
    "BULL (2023-01 -> 2024-03)": ("2023-01-01", "2024-03-15"),
    "BEAR (2024-12 -> 2026-06)": ("2024-12-01", "2026-06-01"),
}


def idx_periodo(df, ini, fim):
    d = df["datetime"]
    return int((d >= ini).idxmax()), int((d <= fim).sum())


for nome, (ini, fim) in PERIODOS.items():
    print(f"\n========== {nome}  (4h, 0,5%/trade, 1x) ==========")
    print(f"  {'ativo':<9}{'estrat':<10}{'trades':>7}{'retorno%':>11}{'B&H%':>10}"
          f"{'maxDD%':>9}{'Sharpe':>8}{'win%':>7}")
    print("  " + "-" * 61)
    for ativo in ATIVOS:
        df = baixar_ohlcv(ativo, TF, dias=DIAS)
        i0, i1 = idx_periodo(df, ini, fim)
        for ename, Cls in ESTRAT:
            c = replace(cfg, par=ativo, timeframe=TF)
            res = rodar(df, Cls(c), GestorBanca(c), c, tf_horas=tf_horas, i_inicio=i0, i_fim=i1)
            m = calcular(res, df)
            marca = "  <<" if m["retorno_%"] > m["bh_%"] else ""
            print(f"  {ativo:<9}{ename:<10}{m['n_trades']:>7}{m['retorno_%']:>11.1f}"
                  f"{m['bh_%']:>10.1f}{m['max_dd_%']:>9.1f}{m['sharpe']:>8.2f}"
                  f"{m['win_rate_%']:>7.1f}{marca}")
        print()
print('"<<" = bateu o buy-and-hold\n')
