# -*- coding: utf-8 -*-
"""[CX-2] Maker realista + portao de open interest, na config de PRODUCAO (lev conviccao).

Grade e prognostico em PRE-REGISTRO-CX2-MAKER-OI-2026-08-26.md, commitados antes desta rodada.
4 niveis de execucao x 18 configs (6 conv/adx x 3 modos de OI) = 72 backtests.
"""
import concurrent.futures as cf, pickle, time
from pesquisa import validacao as V
from pesquisa.backtest_plataforma import backtest_ativo

TAKER, MAKER = 0.0005, 0.0002
NIVEIS = [
    ("taker 0,05% (hoje)", dict(entrada="taker",                 taxa=TAKER)),
    ("maker off 0,05%",    dict(entrada="maker", maker_off=0.0005, taxa=MAKER)),
    ("maker off 0,10%",    dict(entrada="maker", maker_off=0.0010, taxa=MAKER)),
    ("maker off 0,20%",    dict(entrada="maker", maker_off=0.0020, taxa=MAKER)),
]
# `off` e a hipotese nula e fica na grade: se o OI nao ajudar, o treino escolhe operar sem ele.
# `concorda_tend` fora -- o [Q-17] mediu que e degenerado com `concorda` (§2 do pre-registro).
GRID = [(mc, ax, om) for mc in (50, 55, 65) for ax in (22, 25)
        for om in ("off", "concorda", "peso")]
_D = None
def _init(dfs):
    global _D; _D = dfs

def _um(par):
    (rot, kw), (mc, ax, om) = par
    tr, st = [], {}
    for c in V.COINS:
        try:
            tr += backtest_ativo(c, mc, V.VALOR, V.LEV, estrategia="tendencia", df=_D[c],
                                 adx_min=ax, funding_8h=V.FUNDING_8H, saida="trailing",
                                 trailing_dist=0.02, lev_modo="conviccao", oi_modo=om,
                                 exec_stats=st, **kw)
        except Exception:
            pass
    return rot, (mc, ax, om), tr, st

if __name__ == "__main__":
    t0 = time.time()
    dfs = pickle.load(open("_paineis_oi.pkl", "rb"))
    pares = [(n, c) for n in NIVEIS for c in GRID]
    print(f"[CX-2] {len(NIVEIS)} niveis x {len(GRID)} configs = {len(pares)} rodadas", flush=True)
    por, fill = {}, {}
    with cf.ProcessPoolExecutor(max_workers=6, initializer=_init, initargs=(dfs,)) as p:
        for i, (rot, cfg, tr, st) in enumerate(p.map(_um, pares), 1):
            por.setdefault(rot, {})[cfg] = tr
            f = fill.setdefault(rot, {"sinais": 0, "preenchidos": 0})
            f["sinais"] += st.get("sinais", 0); f["preenchidos"] += st.get("preenchidos", 0)
            print(f"  [{i}/{len(pares)}] {rot} {cfg} -> {len(tr)} trades", flush=True)

    out = []
    for rot, _ in NIVEIS:
        print(f"\n{'='*78}\nNIVEL: {rot}\n{'='*78}", flush=True)
        r = V.walk_forward(lambda c, _p=por[rot]: _p[c], GRID, n_trials=1210,
                           rotulo=f"tendencia | lev conviccao | OI na grade | {rot}")
        V.relatorio(r); out.append((rot, r))

    print(f"\n{'='*126}\n[CX-2] MAKER + PORTAO DE OI -- a grade escolhe o modo de OI em cada fold"
          f"\n{'='*126}")
    print(f"{'nivel':<22}{'fill':>7}{'trades':>8}{'PnL OOS':>10}{'Sharpe':>8}"
          f"{'IC95% Sharpe':>22}{'PSR':>8}{'RC p':>8}{'DSR':>8}  veredito")
    for rot, r in out:
        b, a = r["bloco_b"], r["bloco_a"]
        s = V.stats([t["pnl"] for t in r["oos"]])
        f = fill[rot]
        pc = 100.0 * f["preenchidos"] / f["sinais"] if f["sinais"] else 0.0
        print(f"{rot:<22}{pc:>6.1f}%{s['n']:>8}{s['pnl']:>+10.0f}{b['sharpe_anualizado']:>8}"
              f"{str(b['ic_sharpe_anualizado']):>22}{b['psr']['psr']:>8}"
              f"{a['reality_check']['p_valor']:>8}{a['dsr_melhor_is']['dsr']:>8}  "
              f"{r['veredito']['classe']}")
    print("\nCONFIG ESCOLHIDA POR FOLD (o 3o item e o modo de OI):", flush=True)
    for rot, r in out:
        print(f"  {rot:<22}" + " | ".join(str(f[1]) for f in r["por_fold"]))
    print(f"\n=== fim em {(time.time()-t0)/60:.1f} min ===", flush=True)
