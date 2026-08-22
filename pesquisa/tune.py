"""
Varredura de tunagem — testa timeframe × alavancagem × corte de convicção
sobre histórico (mesmo motor da plataforma) pra achar uma config LUCRATIVA.
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from pesquisa.backtest_plataforma import backtest_ativo, ATIVOS

DIAS = {"15m": 60, "1h": 180, "4h": 365}   # mais histórico p/ timeframe maior

print("VARREDURA DE TUNAGEM — caçando config lucrativa\n")
print(f"{'TF':<5}{'lev':>5}{'corte':>7}{'trades':>8}{'win%':>7}{'P&L R$':>11}")
print("-" * 45)
melhores = []
for tf in ["15m", "1h", "4h"]:
    for lev in [3, 10]:
        for mc in [40, 55, 70]:
            todos = []
            for a in ATIVOS:
                todos += backtest_ativo(a, mc, 100, lev, tf=tf, dias=DIAS[tf])
            n = len(todos)
            if n < 10:
                continue
            wins = sum(1 for t in todos if t["pnl"] > 0)
            pnl = sum(t["pnl"] for t in todos)
            marca = "  <<< POSITIVO" if pnl > 0 else ""
            print(f"{tf:<5}{lev:>4}x{mc:>7}{n:>8}{wins/n*100:>6.0f}%{pnl:>+11,.0f}{marca}")
            if pnl > 0:
                melhores.append((pnl, tf, lev, mc, n, wins / n * 100))
    print()

print("=" * 45)
if melhores:
    melhores.sort(reverse=True)
    print("MELHORES CONFIGS (positivas):")
    for pnl, tf, lev, mc, n, wr in melhores[:5]:
        print(f"  {tf} · {lev}x · corte {mc} → P&L R$ {pnl:+,.0f} | {n} trades | win {wr:.0f}%")
else:
    print("Nenhuma config positiva nessa grade — sinal de que a estratégia atual")
    print("precisa de mais edge (filtro melhor, outra lógica) antes de valer a pena.")
