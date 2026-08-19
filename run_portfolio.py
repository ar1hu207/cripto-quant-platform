"""
Opcao A - portfolio multi-ativo da trend (BTC+ETH+SOL), banca unica.
Compara com a media dos mesmos ativos rodados sozinhos (mostra a diversificacao).
"""
from dataclasses import replace
import ccxt

from config import PADRAO as cfg
from dados import baixar_ohlcv
from estrategias.trend import TrendFollowing
from gestao_banca import GestorBanca
from motor import rodar
from motor_portfolio import rodar_portfolio
from metricas import calcular, imprimir

ATIVOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
tf_horas = ccxt.binance().parse_timeframe(cfg.timeframe) / 3600.0
c = replace(cfg, max_posicoes=3)  # deixa segurar os 3 ao mesmo tempo

dados = {a: baixar_ohlcv(a, cfg.timeframe, dias=cfg.dias) for a in ATIVOS}

# --- referencia: cada ativo SOZINHO ---
print("\nReferencia (cada ativo sozinho, 0,5%/trade, 1x):")
print(f"  {'ativo':<10}{'retorno%':>10}{'maxDD%':>9}{'Sharpe':>8}")
solo = []
for a in ATIVOS:
    ci = replace(c, par=a)
    r = rodar(dados[a], TrendFollowing(ci), GestorBanca(ci), ci, tf_horas=tf_horas)
    ms = calcular(r, dados[a])
    solo.append(ms)
    print(f"  {a:<10}{ms['retorno_%']:>10.1f}{ms['max_dd_%']:>9.1f}{ms['sharpe']:>8.2f}")
print(f"  {'MEDIA':<10}{sum(x['retorno_%'] for x in solo)/3:>10.1f}"
      f"{sum(x['max_dd_%'] for x in solo)/3:>9.1f}{sum(x['sharpe'] for x in solo)/3:>8.2f}")

# --- portfolio: os 3 juntos, banca unica ---
gestor = GestorBanca(c)
res = rodar_portfolio(dados, lambda: TrendFollowing(c), gestor, c, tf_horas=tf_horas)
m = calcular(res, dados[ATIVOS[0]])
imprimir(m, c, titulo="PORTFOLIO multi-ativo (BTC+ETH+SOL, banca unica)")
