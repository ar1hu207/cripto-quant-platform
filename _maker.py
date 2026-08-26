# -*- coding: utf-8 -*-
"""[CX-1] O maker que se PAGA x o maker que se DESEJA.

O [Q-15] mostrou que a mesma estrategia sai `SEM EVIDENCIA` a 0,05%/lado e `edge SOBREVIVE`
a 0%. Mas a linha `maker 0,02%` dele so trocou o NUMERO da taxa: manteve o fill no open, 100%
das vezes. Ordem limite nao funciona assim -- ela so enche se o preco vier ate ela, e o trade
que nao acontece e o custo real do maker.

Aqui a taxa de maker vem acompanhada do fill. Varre a concessao de preco (`maker_off`) e mede,
lado a lado com o baseline taker de hoje: quantos sinais viram trade, e o que sobra do veredito.

`maker_off=0` entra de proposito: e o TETO (fill 100% por construcao da barra, `low<=open`
sempre). E a hipotese do [Q-15] explicitada, nao uma execucao possivel.
"""
import concurrent.futures as cf, pickle, time, os
from pesquisa import validacao as V
from pesquisa.backtest_plataforma import backtest_ativo

TAKER, MAKER = 0.0005, 0.0002
NIVEIS = [
    ("taker 0,05% (hoje)",        dict(entrada="taker",                 taxa=TAKER)),
    ("maker TETO (off 0, 100%)",  dict(entrada="maker", maker_off=0.0,    taxa=MAKER)),
    ("maker off 0,05%",           dict(entrada="maker", maker_off=0.0005, taxa=MAKER)),
    ("maker off 0,10%",           dict(entrada="maker", maker_off=0.0010, taxa=MAKER)),
    ("maker off 0,20%",           dict(entrada="maker", maker_off=0.0020, taxa=MAKER)),
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
                                 trailing_dist=0.02, lev_modo="conviccao",
                                 exec_stats=st, **kw)
        except Exception:
            pass
    return rot, (mc, ax), tr, st

if __name__ == "__main__":
    t0 = time.time()
    dfs = pickle.load(open("_paineis.pkl", "rb"))
    grid = [V._chave(g) for g in V.GRID]
    pares = [(n, c) for n in NIVEIS for c in grid]
    print(f"[CX-1] {len(NIVEIS)} niveis x {len(grid)} configs = {len(pares)} rodadas", flush=True)
    por, fill = {}, {}
    with cf.ProcessPoolExecutor(max_workers=6, initializer=_init, initargs=(dfs,)) as p:
        for i, (rot, cfg, tr, st) in enumerate(p.map(_um, pares), 1):
            por.setdefault(rot, {})[cfg] = tr
            f = fill.setdefault(rot, {"sinais": 0, "preenchidos": 0})
            f["sinais"] += st.get("sinais", 0); f["preenchidos"] += st.get("preenchidos", 0)
            print(f"  [{i}/{len(pares)}] {rot} {cfg} -> {len(tr)} trades "
                  f"(fill {st.get('preenchidos',0)}/{st.get('sinais',0)})", flush=True)

    print(f"\n{'='*100}\nFILL POR NIVEL (somado sobre as 6 configs da grade)\n{'='*100}", flush=True)
    print(f"{'nivel':<28}{'sinais':>10}{'preenchidos':>14}{'taxa de fill':>15}")
    for rot, _ in NIVEIS:
        f = fill[rot]
        pc = 100.0 * f["preenchidos"] / f["sinais"] if f["sinais"] else 0.0
        print(f"{rot:<28}{f['sinais']:>10}{f['preenchidos']:>14}{pc:>14.1f}%", flush=True)

    out = []
    for rot, _ in NIVEIS:
        print(f"\n{'='*78}\nNIVEL: {rot}\n{'='*78}", flush=True)
        r = V.walk_forward(lambda c, _p=por[rot]: _p[c], grid, n_trials=1210,
                           rotulo=f"tendencia | lev conviccao | {rot}")
        V.relatorio(r); out.append((rot, r))

    print(f"\n{'='*118}\nCUSTO DE EXECUCAO -- mesma janela, mesma grade; muda a taxa E o fill\n{'='*118}")
    print(f"{'nivel':<28}{'fill':>7}{'trades':>8}{'PnL OOS':>10}{'Sharpe':>8}"
          f"{'IC95% Sharpe':>22}{'PSR':>8}{'RC p':>8}{'DSR':>8}  veredito")
    for rot, r in out:
        b, a = r["bloco_b"], r["bloco_a"]
        s = V.stats([t["pnl"] for t in r["oos"]])
        f = fill[rot]
        pc = 100.0 * f["preenchidos"] / f["sinais"] if f["sinais"] else 0.0
        print(f"{rot:<28}{pc:>6.1f}%{s['n']:>8}{s['pnl']:>+10.0f}{b['sharpe_anualizado']:>8}"
              f"{str(b['ic_sharpe_anualizado']):>22}{b['psr']['psr']:>8}"
              f"{a['reality_check']['p_valor']:>8}{a['dsr_melhor_is']['dsr']:>8}  "
              f"{r['veredito']['classe']}")
    print(f"\n=== fim em {(time.time()-t0)/60:.1f} min ===", flush=True)
