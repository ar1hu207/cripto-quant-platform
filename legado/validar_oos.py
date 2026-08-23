"""
LEGADO -- metodologia superada. O ">>> POSITIVO -> edge ROBUSTO" abaixo e falso. [Q-2]

"Validar" a config vencedora da tunagem em moedas NOVAS no MESMO periodo nao e
out-of-sample: cripto e correlacionada, entao as moedas "novas" andam com as antigas, e a
config testada ja fora escolhida olhando este mesmo periodo. P&L positivo aqui nao
distingue edge de sorte -- e o print de veredito afirma que distingue. O caminho honesto e
`python -m pesquisa.validacao`. Nada aqui roda onde esta -- ver `legado/README.md`.

---
Docstring original, preservado:

Validação OUT-OF-SAMPLE: testa a config vencedora da tunagem em moedas que NÃO
foram usadas na varredura. Se continuar positiva = edge robusto. Se virar
negativa = era overfitting (sorte da amostra de tunagem).
"""

# [Q-2] A recusa abaixo e DECLARADA, nao acidental -- e por isso ela existe.
# Os outros modulos de `legado/` nao rodam porque o [P2-16] quebrou `import dados` /
# `import config` ao mover a pesquisa: e efeito colateral, nao garantia. Estes cinco
# continuavam executaveis por `python -m legado.<modulo>` da raiz, porque `legado/` vira
# namespace package e a raiz esta no sys.path, entao `import pesquisa` resolve. Um script
# que ainda imprime veredito de edge nao passa a nao imprimir so por mudar de pasta.
# Apagar o codigo abaixo tambem resolveria, e perderia o que ele ensina: o `n_trials`
# da regua nova conta estas varreduras como tentativas gastas.
raise SystemExit(
    """LEGADO [Q-2]: aposentado. Este script imprime '>>> POSITIVO -> edge ROBUSTO' a partir de moedas
    novas testadas no MESMO periodo,
    e isso nao separa edge de sorte -- a config e escolhida no mesmo dado em que e medida.
    O veredito honesto do projeto sai de:  python -m pesquisa.validacao
    A versao que rodava esta no git:       git show 0fcf127:pesquisa/validar_oos.py"""
)

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from pesquisa.backtest_plataforma import backtest_ativo

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
