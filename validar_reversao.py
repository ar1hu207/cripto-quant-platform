"""
Valida a estratégia de REVERSÃO out-of-sample. Treina/observa num conjunto de moedas
(IN-SAMPLE) e testa noutro conjunto DIFERENTE (OUT-OF-SAMPLE). Se só vai bem no
in-sample e quebra no OOS => overfitting / sem edge real (a mesma armadilha que pegamos
na estratégia de tendência). Roda vários cortes de convicção pra achar config robusta.

Rodar:  python validar_reversao.py
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import dados
import scoring
from backtest_plataforma import backtest_ativo

IN_SAMPLE = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT",
             "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "LTC/USDT", "DOT/USDT", "TRX/USDT"]
OOS = ["ATOM/USDT", "NEAR/USDT", "UNI/USDT", "AAVE/USDT", "APT/USDT", "ARB/USDT",
       "OP/USDT", "INJ/USDT", "FIL/USDT", "SUI/USDT", "ETC/USDT", "BCH/USDT"]
TF, LEV, VALOR, DIAS = "15m", 10, 100, 60

_cache = {}


def df_de(a):
    if a not in _cache:
        _cache[a] = scoring.preparar(dados.baixar_ohlcv(a, TF, dias=DIAS))
    return _cache[a]


def roda(coins, mc):
    todos = []
    for a in coins:
        try:
            todos += backtest_ativo(a, mc, VALOR, LEV, estrategia="reversao", df=df_de(a))
        except Exception as e:
            print(f"  falha {a}: {e}")
    n = len(todos)
    if not n:
        return 0, 0, 0, {}
    wins = sum(1 for t in todos if t["pnl"] > 0)
    motivos = {}
    for t in todos:
        motivos[t["motivo"]] = motivos.get(t["motivo"], 0) + 1
    return n, wins / n * 100, sum(t["pnl"] for t in todos), motivos


print(f"VALIDACAO REVERSAO | {TF} | {LEV}x | {DIAS}d | R${VALOR}/trade")
print(f"In-sample: {len(IN_SAMPLE)} moedas | OOS: {len(OOS)} moedas DIFERENTES\n")
print("baixando historico (cacheado)...")
for a in IN_SAMPLE + OOS:
    df_de(a)
print("ok.\n")

print(f"{'corte':>6}   {'IN-SAMPLE':>24}   {'OUT-OF-SAMPLE':>24}")
print("-" * 64)
robustos = []
for mc in [50, 55, 65, 75]:
    ni, wi, pi, _ = roda(IN_SAMPLE, mc)
    no, wo, po, _ = roda(OOS, mc)
    rob = "  <- ROBUSTO" if pi > 0 and po > 0 else ""
    print(f"  >={mc:>3}   {ni:>4}t {wi:>4.0f}% R${pi:>+7.0f}      {no:>4}t {wo:>4.0f}% R${po:>+7.0f}{rob}")
    if pi > 0 and po > 0:
        robustos.append((mc, pi + po))

_, _, _, mi = roda(IN_SAMPLE, 55)
print(f"\nSaidas (in-sample, corte 55): {mi}")
print()
if robustos:
    best = max(robustos, key=lambda x: x[1])[0]
    print(f"=> Config ROBUSTA: corte {best} (positivo in-sample E out-of-sample). A reversao TEM mao.")
else:
    print("=> Nenhum corte robusto: a reversao NAO validou OOS (miragem, como a tendencia).")
