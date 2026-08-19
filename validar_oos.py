"""
Validação OUT-OF-SAMPLE: testa a config vencedora da tunagem em moedas que NÃO
foram usadas na varredura. Se continuar positiva = edge robusto. Se virar
negativa = era overfitting (sorte da amostra de tunagem).
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from backtest_plataforma import backtest_ativo

# moedas NOVAS (não estavam nos 8 ativos da tunagem)
NOVOS = ["DOT/USDT", "ATOM/USDT", "NEAR/USDT", "FIL/USDT",
         "INJ/USDT", "UNI/USDT", "AAVE/USDT", "APT/USDT"]
TF, LEV, MC, DIAS = "15m", 10, 70, 60   # config candidata vencedora

print(f"VALIDAÇÃO OUT-OF-SAMPLE: config {TF} · {LEV}x · corte {MC}  em moedas NOVAS\n")
todos = []
for a in NOVOS:
    try:
        t = backtest_ativo(a, MC, 100, LEV, tf=TF, dias=DIAS)
        todos += t
        print(f"  {a:<12} {len(t)} trades")
    except Exception as e:
        print(f"  {a:<12} pulou ({type(e).__name__})")

n = len(todos)
if n:
    wins = sum(1 for t in todos if t["pnl"] > 0)
    pnl = sum(t["pnl"] for t in todos)
    print(f"\n>>> {n} trades | win {wins/n*100:.0f}% | P&L R$ {pnl:+,.0f}")
    print(">>> POSITIVO → edge ROBUSTO (não foi só sorte) ✅" if pnl > 0
          else ">>> NEGATIVO → era OVERFITTING (sorte da amostra de tunagem) ⚠️")
