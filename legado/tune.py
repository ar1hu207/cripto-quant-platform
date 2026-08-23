"""
LEGADO -- metodologia superada. NAO use este resultado como veredito de edge. [Q-2]

Este script varre TF x lev x corte no periodo INTEIRO procurando P&L positivo e lista
"MELHORES CONFIGS (positivas)". Isso e data-snooping puro: escolher a config no mesmo
dado em que ela e medida nao separa edge de sorte. O veredito honesto sai de
`python -m pesquisa.validacao` (walk-forward + DSR + Reality Check), e ele diz que NAO ha
edge deployavel. A varredura daqui e uma das fontes contadas no `n_trials` daquela regua.
Nada aqui roda onde esta -- ver `legado/README.md`.

---
Docstring original, preservado:

Varredura de tunagem — testa timeframe × alavancagem × corte de convicção
sobre histórico (mesmo motor da plataforma) pra achar uma config LUCRATIVA.
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
    """LEGADO [Q-2]: aposentado. Este script varre TF x lev x corte no periodo INTEIRO cacando P&L positivo
    e lista 'MELHORES CONFIGS (positivas)',
    e isso nao separa edge de sorte -- a config e escolhida no mesmo dado em que e medida.
    O veredito honesto do projeto sai de:  python -m pesquisa.validacao
    A versao que rodava esta no git:       git show 0fcf127:pesquisa/tune.py"""
)

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
