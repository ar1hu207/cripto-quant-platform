# -*- coding: utf-8 -*-
"""[CX-4] O round-trip REALISTA: maker na entrada, taker na saida.

O [CX-1] cobrou maker nas duas pernas. A saida do motor e stop/trailing, que e ordem a MERCADO
por natureza. Entao o custo real de post-only e 0,02% entrando + 0,05% saindo = 0,07%, nao 0,04%.
"""
import concurrent.futures as cf, pickle, time
from pesquisa import validacao as V
from pesquisa.backtest_plataforma import backtest_ativo
TAKER, MAKER = 0.0005, 0.0002
NIVEIS = [
    ("taker/taker (hoje)",   dict(entrada="taker",                       taxa=TAKER)),
    ("maker-in/taker-out 0,05%", dict(entrada="maker", maker_off=0.0005, taxa=MAKER, taxa_saida=TAKER)),
    ("maker-in/taker-out 0,10%", dict(entrada="maker", maker_off=0.0010, taxa=MAKER, taxa_saida=TAKER)),
    ("maker-in/taker-out 0,20%", dict(entrada="maker", maker_off=0.0020, taxa=MAKER, taxa_saida=TAKER)),
    ("maker/maker 0,10% (otimista)", dict(entrada="maker", maker_off=0.0010, taxa=MAKER)),
]
_D = None
def _init(dfs):
    global _D; _D = dfs
def _um(par):
    (rot, kw), (mc, ax) = par
    tr, st = [], {}
    for c in V.COINS:
        try:
            tr += backtest_ativo(c, mc, V.VALOR, V.LEV, estrategia="tendencia", df=_D[c],
                                 adx_min=ax, funding_8h=V.FUNDING_8H, saida="trailing",
                                 trailing_dist=0.02, lev_modo="conviccao", exec_stats=st, **kw)
        except Exception:
            pass
    return rot, (mc, ax), tr, st
if __name__ == "__main__":
    t0 = time.time()
    dfs = pickle.load(open("_paineis.pkl", "rb"))
    grid = [V._chave(g) for g in V.GRID]
    pares = [(n, c) for n in NIVEIS for c in grid]
    print(f"[CX-4] {len(NIVEIS)} niveis x {len(grid)} configs = {len(pares)} rodadas", flush=True)
    por = {}
    with cf.ProcessPoolExecutor(max_workers=6, initializer=_init, initargs=(dfs,)) as p:
        for i, (rot, cfg, tr, st) in enumerate(p.map(_um, pares), 1):
            por.setdefault(rot, {})[cfg] = tr
            print(f"  [{i}/{len(pares)}] {rot} {cfg} -> {len(tr)} trades", flush=True)
    out = []
    for rot, _ in NIVEIS:
        print(f"\n{'='*78}\nNIVEL: {rot}\n{'='*78}", flush=True)
        r = V.walk_forward(lambda c, _p=por[rot]: _p[c], grid, n_trials=1210,
                           rotulo=f"tendencia | lev conviccao | {rot}")
        V.relatorio(r); out.append((rot, r))
    print(f"\n{'='*120}\n[CX-4] CUSTO REALISTA DO ROUND-TRIP\n{'='*120}")
    print(f"{'nivel':<30}{'trades':>8}{'PnL OOS':>10}{'Sharpe':>8}{'IC95% Sharpe':>22}"
          f"{'PSR':>8}{'RC p':>8}  veredito")
    for rot, r in out:
        b, a = r["bloco_b"], r["bloco_a"]
        s = V.stats([t["pnl"] for t in r["oos"]])
        print(f"{rot:<30}{s['n']:>8}{s['pnl']:>+10.0f}{b['sharpe_anualizado']:>8}"
              f"{str(b['ic_sharpe_anualizado']):>22}{b['psr']['psr']:>8}"
              f"{a['reality_check']['p_valor']:>8}  {r['veredito']['classe']}")
    print(f"\n=== fim em {(time.time()-t0)/60:.1f} min ===", flush=True)
