"""
Validação RIGOROSA (Onda 3): WALK-FORWARD (treina no passado, testa no FUTURO não-visto)
+ Deflated Sharpe Ratio (corrige data-snooping/multiple-testing) + bootstrap CI.

Por que: o split-por-moedas no MESMO período (validar_reversao*.py) não é honesto —
cripto é correlacionada e o corte era escolhido olhando o OOS. Aqui os parâmetros são
escolhidos SÓ no treino (passado) e avaliados no teste (futuro), nunca peeking. Separa
'tem edge' de 'teve sorte / overfit'.

Rodar:  python validacao.py
"""
import sys
import math
import random
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import dados
import scoring
from backtest_plataforma import backtest_ativo

COINS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT",
         "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "LTC/USDT", "DOT/USDT", "TRX/USDT"]
TF, DIAS, VALOR, LEV = "1h", 180, 100, 10
GRID = [{"min_conv": mc, "adx_min": ax} for mc in (50, 55, 65) for ax in (22, 25)]
N_FOLDS = 5
PPA = 24 * 365 / 1   # períodos/ano aproximado p/ anualizar (1h) — usado só pra leitura


# ---------- estatística ----------
def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_ppf(p):
    """Inversa da normal (Acklam) — sem scipy."""
    if p <= 0:
        return -1e9
    if p >= 1:
        return 1e9
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
        ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


def stats(pnls):
    n = len(pnls)
    if n < 2:
        return {"n": n, "win": 0, "pnl": round(sum(pnls), 2), "sharpe_trade": 0}
    m = sum(pnls) / n
    sd = (sum((x - m) ** 2 for x in pnls) / (n - 1)) ** 0.5
    return {"n": n, "win": round(sum(1 for x in pnls if x > 0) / n * 100, 1),
            "pnl": round(sum(pnls), 2),
            "sharpe_trade": round(m / sd, 4) if sd > 0 else 0}


def deflated_sharpe(pnls, n_trials):
    """DSR (Bailey & López de Prado): prob. de o Sharpe verdadeiro ser >0 DEPOIS de
    descontar o viés de ter testado n_trials configs. DSR>0.95 = significativo."""
    n = len(pnls)
    if n < 5:
        return {"sr": 0, "sr0": 0, "dsr": 0}
    m = sum(pnls) / n
    sd = (sum((x - m) ** 2 for x in pnls) / (n - 1)) ** 0.5
    if sd == 0:
        return {"sr": 0, "sr0": 0, "dsr": 0}
    sr = m / sd
    sk = sum(((x - m) / sd) ** 3 for x in pnls) / n
    ku = sum(((x - m) / sd) ** 4 for x in pnls) / n
    g, e = 0.5772156649, math.e
    var_sr = 1.0 / n
    sr0 = math.sqrt(var_sr) * ((1 - g) * _norm_ppf(1 - 1.0 / n_trials) +
                               g * _norm_ppf(1 - 1.0 / (n_trials * e)))
    denom = math.sqrt(max(1e-9, 1 - sk * sr + (ku - 1) / 4 * sr * sr))
    dsr = _norm_cdf((sr - sr0) * math.sqrt(n - 1) / denom)
    return {"sr": round(sr, 4), "sr0": round(sr0, 4), "dsr": round(dsr, 3)}


def bootstrap_ci(pnls, n=5000):
    """IC 95% da MÉDIA por trade. Se incluir 0 -> edge não significativo."""
    if len(pnls) < 5:
        return (0, 0)
    means = []
    L = len(pnls)
    for _ in range(n):
        s = sum(pnls[random.randrange(L)] for _ in range(L)) / L
        means.append(s)
    means.sort()
    return (round(means[int(n * 0.025)], 3), round(means[int(n * 0.975)], 3))


# ---------- walk-forward ----------
def walk_forward(estrategia):
    print(f"baixando {len(COINS)} moedas ({TF}, {DIAS}d)...")
    dfs = {c: scoring.preparar(dados.baixar_ohlcv(c, TF, dias=DIAS)) for c in COINS}
    # roda backtest por config (full timeline), trades com ts
    por_cfg = {}
    for g in GRID:
        tr = []
        for c in COINS:
            try:
                tr += backtest_ativo(c, g["min_conv"], VALOR, LEV, estrategia=estrategia,
                                     df=dfs[c], adx_min=g["adx_min"])
            except Exception:
                pass
        por_cfg[(g["min_conv"], g["adx_min"])] = tr
    todos_ts = sorted(t["ts"] for tr in por_cfg.values() for t in tr)
    if len(todos_ts) < 30:
        print("poucos trades — sem dados pra walk-forward."); return
    t0, t1 = todos_ts[0], todos_ts[-1]
    bordas = [t0 + (t1 - t0) * k / (N_FOLDS + 1) for k in range(N_FOLDS + 2)]

    oos, detalhe = [], []
    for i in range(N_FOLDS):
        tr_lim, te_lim = bordas[i + 1], bordas[i + 2]
        melhor, melhor_pnl = None, -1e18
        for cfg, tr in por_cfg.items():                       # escolhe o melhor SÓ no treino (passado)
            pnl_tr = sum(t["pnl"] for t in tr if t["ts"] < tr_lim)
            if pnl_tr > melhor_pnl:
                melhor_pnl, melhor = pnl_tr, cfg
        teste = [t for t in por_cfg[melhor] if tr_lim <= t["ts"] < te_lim]  # aplica no FUTURO não-visto
        oos += teste
        detalhe.append((i + 1, melhor, len(teste), round(sum(t["pnl"] for t in teste), 2)))

    # naive (melhor config no período INTEIRO) — pra mostrar o quanto o data-snooping infla
    naive_cfg = max(por_cfg, key=lambda k: sum(t["pnl"] for t in por_cfg[k]))
    naive = [t["pnl"] for t in por_cfg[naive_cfg]]
    oos_pnls = [t["pnl"] for t in oos]
    n_trials = len(GRID) * N_FOLDS

    print(f"\n=== WALK-FORWARD: {estrategia} | {TF} {DIAS}d | {LEV}x | {len(GRID)} configs × {N_FOLDS} folds ===\n")
    print(f"{'fold':>5}  {'config (conv/adx)':>18}  {'trades':>7}  {'pnl OOS':>9}")
    for f, cfg, n, p in detalhe:
        print(f"{f:>5}  {str(cfg):>18}  {n:>7}  R${p:>+7.0f}")
    so = stats(oos_pnls)
    ci = bootstrap_ci(oos_pnls)
    ds = deflated_sharpe(oos_pnls, n_trials)
    print(f"\nOOS AGREGADO (walk-forward, honesto): {so['n']} trades | win {so['win']}% | "
          f"PnL R${so['pnl']:+.0f} | Sharpe/trade {so['sharpe_trade']}")
    print(f"  bootstrap IC95% da média/trade: [{ci[0]}, {ci[1]}]  -> {'SIGNIFICATIVO' if ci[0] > 0 else 'inclui 0 (NÃO significativo)'}")
    print(f"  Deflated Sharpe (descontando {n_trials} tentativas): DSR={ds['dsr']} (>0.95 = edge real; sr={ds['sr']} vs sr0_esperado={ds['sr0']})")
    sn = stats(naive)
    print(f"\nNAIVE (melhor config {naive_cfg} no período INTEIRO, in-sample): {sn['n']}t win {sn['win']}% PnL R${sn['pnl']:+.0f}")
    print(f"  -> a diferença OOS vs naive mede a INFLAÇÃO do data-snooping.\n")
    if ci[0] > 0 and ds["dsr"] > 0.95:
        print("=> VEREDITO: edge SOBREVIVE ao walk-forward + DSR. Vale calibrar/operar.")
    else:
        print("=> VEREDITO: edge NÃO comprovado (IC inclui 0 ou DSR<0.95). Não há evidência de alfa.")


if __name__ == "__main__":
    walk_forward("tendencia")
