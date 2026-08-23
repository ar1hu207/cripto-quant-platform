"""
LEGADO -- metodologia superada. O "<- ROBUSTO" abaixo e falso. [Q-2]

Split-por-moedas no MESMO periodo, agora com matriz maker/taker x 15m/1h -- o vicio nao
muda com o custo: cripto e correlacionada e o corte era escolhido olhando o OOS.
"Positivo nos dois conjuntos" mede sorte correlacionada, nao edge. O caminho honesto e
`python -m pesquisa.validacao`. Nada aqui roda onde esta -- ver `legado/README.md`.

---
Docstring original, preservado:

Teste decisivo da reversão: ela perde com taker 0,05%/lado no 15m. Será que MAKER
(ordem limite, ~0,02%/lado) e/ou TIMEFRAME maior (1h, movimentos maiores diluem a
taxa) salvam? Matriz 15m/1h × maker/taker, in-sample vs OUT-OF-SAMPLE.

Rodar (da RAIZ do repo):  python -m pesquisa.validar_reversao_maker
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
    """LEGADO [Q-2]: aposentado. Este script imprime '<- ROBUSTO' a partir de split-por-moedas
    no MESMO periodo,
    e isso nao separa edge de sorte -- a config e escolhida no mesmo dado em que e medida.
    O veredito honesto do projeto sai de:  python -m pesquisa.validacao
    A versao que rodava esta no git:       git show 0fcf127:pesquisa/validar_reversao_maker.py"""
)

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from pesquisa import dados
import scoring
from pesquisa.backtest_plataforma import backtest_ativo

IN_SAMPLE = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT",
             "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "LTC/USDT", "DOT/USDT", "TRX/USDT"]
OOS = ["ATOM/USDT", "NEAR/USDT", "UNI/USDT", "AAVE/USDT", "APT/USDT", "ARB/USDT",
       "OP/USDT", "INJ/USDT", "FIL/USDT", "SUI/USDT", "ETC/USDT", "BCH/USDT"]
VALOR, LEV = 100, 10
MAKER, TAKER = 0.0002, 0.0005      # 0,02%/lado (limite) vs 0,05%/lado (mercado)
CONFIGS = [("15m", 60), ("1h", 120)]

_cache = {}


def df_de(a, tf, dias):
    k = (a, tf)
    if k not in _cache:
        _cache[k] = scoring.preparar(dados.baixar_ohlcv(a, tf, dias=dias))
    return _cache[k]


def roda(coins, mc, tf, dias, taxa):
    todos = []
    for a in coins:
        try:
            todos += backtest_ativo(a, mc, VALOR, LEV, estrategia="reversao",
                                    df=df_de(a, tf, dias), taxa=taxa)
        except Exception:
            pass
    n = len(todos)
    if not n:
        return 0, 0, 0
    wins = sum(1 for t in todos if t["pnl"] > 0)
    return n, wins / n * 100, sum(t["pnl"] for t in todos)


print("TESTE DECISIVO REVERSAO | maker vs taker | 15m vs 1h | 10x | in vs OOS\n")
print("baixando historico...")
for tf, dias in CONFIGS:
    for a in IN_SAMPLE + OOS:
        df_de(a, tf, dias)
print("ok.\n")

print(f"{'TF':>4} {'fee':>6} {'corte':>6}   {'IN-SAMPLE':>22}   {'OUT-OF-SAMPLE':>22}")
print("-" * 72)
robustos = []
for tf, dias in CONFIGS:
    for nome, taxa in [("maker", MAKER), ("taker", TAKER)]:
        for mc in [55, 65]:
            ni, wi, pi = roda(IN_SAMPLE, mc, tf, dias, taxa)
            no, wo, po = roda(OOS, mc, tf, dias, taxa)
            rob = "  <- ROBUSTO" if pi > 0 and po > 0 else ""
            print(f"{tf:>4} {nome:>6} >={mc:>3}   {ni:>4}t {wi:>3.0f}% R${pi:>+7.0f}    "
                  f"{no:>4}t {wo:>3.0f}% R${po:>+7.0f}{rob}")
            if pi > 0 and po > 0:
                robustos.append((tf, nome, mc, pi + po))
        print()

if robustos:
    print("=> CONFIGS ROBUSTAS (positivas in-sample E out-of-sample):")
    for tf, fee, mc, tot in sorted(robustos, key=lambda x: -x[3]):
        print(f"   {tf} {fee} corte>={mc}   (soma in+oos R${tot:+.0f})")
    print("=> A REVERSAO RENASCE com essas configs!")
else:
    print("=> Nenhuma config robusta nem com maker/1h. Reversao vai pro arquivo.")
