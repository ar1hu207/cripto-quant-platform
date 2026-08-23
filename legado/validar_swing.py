"""
LEGADO -- metodologia superada. O "ROBUSTO" abaixo e falso. [Q-2]

Mesmo vicio dos outros `validar_*`: split-por-moedas no MESMO periodo. E o docstring
original abaixo declara o problema por escrito -- "acha o melhor corte ROBUSTO (positivo
nos dois) pra virar o default" e escolher parametro olhando o resultado, que e exatamente
o data-snooping que a regua existe para detectar. O caminho honesto e
`python -m pesquisa.validacao`. Nada aqui roda onde esta -- ver `legado/README.md`.

---
Docstring original, preservado:

Valida o regime SWING (diário, alavancagem 1x) — onde os testes antigos acharam
edge — com a pontuação atual da plataforma, IN-SAMPLE e OUT-OF-SAMPLE de uma vez.
Acha o melhor corte ROBUSTO (positivo nos dois) pra virar o default.
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
    """LEGADO [Q-2]: aposentado. Este script imprime 'ROBUSTO' a partir de split-por-moedas no MESMO
    periodo,
    e isso nao separa edge de sorte -- a config e escolhida no mesmo dado em que e medida.
    O veredito honesto do projeto sai de:  python -m pesquisa.validacao
    A versao que rodava esta no git:       git show 0fcf127:pesquisa/validar_swing.py"""
)

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
