"""
Ponto de entrada do backtest com a arquitetura nova (Fase 0) + Gestor de Banca (Fase 1).
Rode:  python run_backtest.py
"""
import ccxt

from config import PADRAO as cfg
from dados import baixar_ohlcv
from estrategias.trend import TrendFollowing
from gestao_banca import GestorBanca
from motor import rodar
from metricas import calcular, imprimir


def tf_para_horas(tf):
    return ccxt.binance().parse_timeframe(tf) / 3600.0


def main():
    print(f"Baixando {cfg.dias}d de {cfg.par} {cfg.timeframe}...")
    df = baixar_ohlcv(cfg.par, cfg.timeframe, dias=cfg.dias)
    print(f"OK: {len(df)} candles.")

    estrategia = TrendFollowing(cfg)
    gestor = GestorBanca(cfg)
    res = rodar(df, estrategia, gestor, cfg, tf_horas=tf_para_horas(cfg.timeframe))

    m = calcular(res, df)
    imprimir(m, cfg, titulo="FASE 1 - Trend + Gestor de Banca")

    print("Comparacao com a v1 (sem gestor, 100% da banca por trade, 3x):")
    print("  v1: retorno -60,7% | maxDD -91% | 289 trades")
    print(f"  v2: retorno {m['retorno_%']:.1f}% | maxDD {m['max_dd_%']:.1f}% | {m['n_trades']} trades")


if __name__ == "__main__":
    main()
