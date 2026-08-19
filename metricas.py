"""Metricas de performance honestas (sempre vs buy-and-hold, sempre liquido de taxa)."""
import numpy as np
import pandas as pd


def calcular(res, df):
    trades = res["trades"]
    eq = pd.DataFrame(res["eq_curve"], columns=["datetime", "equity"])
    closes = df["close"].values
    bh = res.get("bh_%")
    if bh is None:
        bh = (closes[-1] / closes[0] - 1) * 100

    # drawdown sobre a curva marcada
    eq["pico"] = eq["equity"].cummax()
    max_dd = (eq["equity"] / eq["pico"] - 1).min() * 100

    rets = [t["ret_liq_%"] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    pf = (sum(wins) / abs(sum(losses))) if losses else float("inf")
    expectativa = np.mean(rets) if rets else 0

    # retornos diarios -> Sharpe/Sortino + % dias verdes
    eq["dia"] = eq["datetime"].dt.date
    diario = eq.groupby("dia")["equity"].last().pct_change().dropna()
    ann = np.sqrt(365)
    sharpe = (diario.mean() / diario.std() * ann) if diario.std() > 0 else 0
    downside = diario[diario < 0].std()
    sortino = (diario.mean() / downside * ann) if downside and downside > 0 else float("inf")
    dias_verdes = (diario > 0).mean() * 100 if len(diario) else 0

    taxa_total = sum(t["taxa_paga"] for t in trades)

    return {
        "retorno_%": (res["banca_final"] / res["banca_inicial"] - 1) * 100,
        "bh_%": bh, "banca_final": res["banca_final"],
        "max_dd_%": max_dd, "n_trades": len(trades), "win_rate_%": win_rate,
        "profit_factor": pf, "expectativa_%": expectativa,
        "ganho_medio_%": np.mean(wins) if wins else 0,
        "perda_media_%": np.mean(losses) if losses else 0,
        "sharpe": sharpe, "sortino": sortino, "dias_verdes_%": dias_verdes,
        "taxa_total": taxa_total, "n_dias": len(diario) + 1,
        "dias_travados": res.get("dias_travados", 0),
    }


def imprimir(m, cfg, titulo=""):
    print("\n" + "=" * 60)
    print(f" {titulo or 'RESULTADO'}  |  {cfg.par} {cfg.timeframe} {cfg.alavancagem:g}x"
          f"  risco {cfg.risco_por_trade*100:g}%/trade")
    print("=" * 60)
    print(f" Banca final ........... {m['banca_final']:>12,.2f}")
    print(f" RETORNO do bot ........ {m['retorno_%']:>11,.2f}%")
    print(f" Buy & Hold ............ {m['bh_%']:>11,.2f}%   "
          f"{'(BATEU)' if m['retorno_%'] > m['bh_%'] else '(perdeu)'}")
    print("-" * 60)
    print(f" Max drawdown .......... {m['max_dd_%']:>11,.2f}%")
    print(f" Sharpe / Sortino ...... {m['sharpe']:>6.2f} / {m['sortino']:>6.2f}")
    print(f" Trades ................ {m['n_trades']:>12}")
    print(f" Win rate .............. {m['win_rate_%']:>11,.1f}%")
    print(f" Profit factor ......... {m['profit_factor']:>12,.2f}")
    print(f" Expectativa/trade ..... {m['expectativa_%']:>11,.2f}%")
    print(f" Ganho medio / Perda ... {m['ganho_medio_%']:>6.2f}% / {m['perda_media_%']:.2f}%")
    print(f" % dias verdes ......... {m['dias_verdes_%']:>11,.1f}%   ({m['n_dias']} dias)")
    print(f" Dias travados (limite)  {m['dias_travados']:>12}")
    print(f" Taxa total paga ....... {m['taxa_total']:>12,.2f}")
    print("=" * 60 + "\n")
