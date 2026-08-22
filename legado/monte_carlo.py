"""
Monte Carlo do PLANO B (aposta agressiva): simula milhares de cenarios de 1 ano
reamostrando os trades reais da estrategia, escalados pra niveis de risco altos.
Barreiras: chegou em R$10k (sucesso, sacaria) OU caiu -90% (ruina).
Mostra a PROBABILIDADE real de cada desfecho.
"""
from dataclasses import replace
import ccxt
import numpy as np

from config import PADRAO as cfg
from dados import baixar_ohlcv
from estrategias.trend import TrendFollowing
from gestao_banca import GestorBanca
from motor_portfolio import rodar_portfolio

rng = np.random.default_rng(42)
ATIVOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TF, DIAS, INI, FIM = "4h", 1800, "2022-01-01", "2026-06-01"
tf_horas = ccxt.binance().parse_timeframe(TF) / 3600.0
anos = 4.42
dados = {a: baixar_ohlcv(a, TF, dias=DIAS) for a in ATIVOS}

# distribuicao real de retorno por trade no risco base 0,5%
cb = replace(cfg, max_posicoes=3, timeframe=TF, risco_por_trade=0.005, alavancagem=10.0,
             kill_switch_dd=0.99, limite_perda_dia=0.99, max_risco_aberto=1.0)
res = rodar_portfolio(dados, lambda: TrendFollowing(cb), GestorBanca(cb), cb,
                      tf_horas=tf_horas, inicio=INI, fim=FIM)
rets = np.array([t["ret_liq_%"] / 100 for t in res["trades"]])
n_ano = int(round(len(rets) / anos))
print(f"Base: {len(rets)} trades / {anos} anos = ~{n_ano} trades/ano | "
      f"win rate {(rets > 0).mean()*100:.0f}% | expectativa {rets.mean()*100:.3f}%/trade")


def monte(risco, n_sims=40000):
    M = risco / 0.005
    R = np.maximum(rng.choice(rets, size=(n_sims, n_ano)) * M, -0.99)  # -99% = liquidacao
    eq = 1000.0 * np.cumprod(1 + R, axis=1)
    hit = eq >= 10000
    rui = eq <= 100
    f_hit = np.where(hit.any(1), hit.argmax(1), n_ano + 1)
    f_rui = np.where(rui.any(1), rui.argmax(1), n_ano + 1)
    sucesso = float((f_hit < f_rui).mean())
    ruina = float((f_rui < f_hit).mean())
    final = eq[:, -1].copy()
    final[f_hit < f_rui] = 10000
    final[f_rui < f_hit] = 50
    return sucesso, ruina, float(np.median(final))


print(f"\nPLANO B - simulacao de 1 ANO (reinvestindo tudo), 40k cenarios cada:")
print(f"{'risco/trade':>11}{'P(chega 10k)':>15}{'P(ruina -90%)':>15}{'mediana R$':>13}")
print("-" * 54)
for risco in [0.03, 0.05, 0.10, 0.15, 0.20]:
    p10, pr, med = monte(risco)
    print(f"{risco*100:>10.0f}%{p10*100:>14.1f}%{pr*100:>14.1f}%{med:>13,.0f}")
print("\n(Otimista: a simulacao NAO modela gaps/liquidacao real nem sequencias ruins agrupadas)")
