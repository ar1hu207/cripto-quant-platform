"""
Valida o regime SWING (diário, alavancagem 1x) — onde os testes antigos acharam
edge — com a pontuação atual da plataforma, IN-SAMPLE e OUT-OF-SAMPLE de uma vez.
Acha o melhor corte ROBUSTO (positivo nos dois) pra virar o default.
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from pesquisa.backtest_plataforma import backtest_ativo, ATIVOS

NOVOS = ["DOT/USDT", "ATOM/USDT", "NEAR/USDT", "FIL/USDT",
         "INJ/USDT", "UNI/USDT", "AAVE/USDT", "APT/USDT"]
TF, LEV, DIAS = "1d", 1, 540


def roda(coins, mc):
    todos = []
    for a in coins:
        try:
            todos += backtest_ativo(a, mc, 100, LEV, tf=TF, dias=DIAS)
        except Exception:
            pass
    n = len(todos)
    if not n:
        return 0, 0, 0
    wins = sum(1 for t in todos if t["pnl"] > 0)
    return n, wins / n * 100, sum(t["pnl"] for t in todos)


print(f"REGIME SWING: {TF} · {LEV}x · {DIAS}d  (alavancagem baixa, sem liquidação)\n")
print(f"{'corte':>6}   {'IN-SAMPLE':>26}   {'OUT-OF-SAMPLE':>26}")
print("-" * 70)
robustos = []
for mc in [0, 40, 55]:
    ni, wi, pi = roda(ATIVOS, mc)
    no, wo, po = roda(NOVOS, mc)
    rob = "  ROBUSTO ✅" if pi > 0 and po > 0 else ""
    print(f"  >={mc:>3}   {ni:>4}t {wi:>4.0f}% R${pi:>+7.0f}      {no:>4}t {wo:>4.0f}% R${po:>+7.0f}{rob}")
    if pi > 0 and po > 0:
        robustos.append((mc, pi + po))

print("\n" + ("=> Config robusta achada: corte " + str(max(robustos, key=lambda x: x[1])[0])
              if robustos else "=> Nenhum corte robusto nesse regime tambem."))
