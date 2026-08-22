"""
Pedra 1+2 - Motor de backtest HONESTO (desconta taxa + funding, modela alavancagem
e trailing stop). Compara contra buy-and-hold.

Rode:  python backtest.py
"""
import numpy as np
import pandas as pd

from dados import baixar_ohlcv
from estrategia import gerar_sinais


def rodar_backtest(df, leverage=3.0, taxa_por_lado=0.0005, funding_8h=0.0001,
                   trail_atr=3.0, liq_limite=0.9, tf_horas=1.0, capital0=1000.0):
    """
    leverage      : alavancagem (3x)
    taxa_por_lado : 0.05% (taker futuros Binance) -> ida+volta = 0.10%
    funding_8h    : custo de funding aproximado por 8h
    trail_atr     : trailing stop a `trail_atr` x ATR do pico
    liq_limite    : perda (fracao da margem) que dispara liquidacao
    """
    closes = df["close"].values
    regime = df["regime"].values
    atr_v = df["atr"].values
    dt = df["datetime"].values

    custo_rt = 2 * taxa_por_lado * leverage  # taxa ida+volta sobre o nocional alavancado

    mask_ok = df[["ema_lenta", "adx", "atr"]].notna().all(axis=1)
    start = int(mask_ok.idxmax())

    equity = capital0
    pos = 0
    entry_price = entry_equity = entry_dt = None
    bars_held = 0
    peak_price = trough_price = None
    locked = 0  # direcao travada apos um stop, ate o regime sair dela

    trades, eq_curve = [], []
    peak_eq, max_dd = equity, 0.0

    def fechar(motivo_saida):
        nonlocal equity
        if motivo_saida == "liquidacao":
            ret = -liq_limite
        else:
            ret = pos * (price / entry_price - 1) * leverage
        funding = funding_8h * (bars_held * tf_horas / 8.0) * leverage
        ret_liq = ret - funding - custo_rt
        equity = entry_equity * (1 + ret_liq)
        trades.append({
            "entrada_dt": entry_dt, "saida_dt": dt[i],
            "direcao": "LONG" if pos == 1 else "SHORT",
            "entrada": float(entry_price), "saida": float(price),
            "ret_liq_%": ret_liq * 100, "motivo": motivo_saida,
            "taxa_paga": custo_rt * entry_equity,
            "horas": bars_held * tf_horas,
        })

    for i in range(start, len(df)):
        price = closes[i]
        a = atr_v[i]

        # marca a mercado (p/ drawdown)
        if pos != 0:
            mtm = pos * (price / entry_price - 1) * leverage
            funding = funding_8h * (bars_held * tf_horas / 8.0) * leverage
            marked = entry_equity * (1 + mtm - funding)
        else:
            marked = equity
        peak_eq = max(peak_eq, marked)
        max_dd = min(max_dd, marked / peak_eq - 1)
        eq_curve.append((dt[i], marked))

        # stop / liquidacao
        motivo = None
        if pos == 1:
            peak_price = max(peak_price, price)
            if price <= peak_price - trail_atr * a:
                motivo = "trailing"
            if (price / entry_price - 1) * leverage <= -liq_limite:
                motivo = "liquidacao"
        elif pos == -1:
            trough_price = min(trough_price, price)
            if price >= trough_price + trail_atr * a:
                motivo = "trailing"
            if -(price / entry_price - 1) * leverage <= -liq_limite:
                motivo = "liquidacao"

        alvo = int(regime[i])

        if motivo and pos != 0:
            dir_antiga = pos
            fechar(motivo)
            locked = dir_antiga
            pos, entry_price, bars_held = 0, None, 0

        if locked != 0 and alvo != locked:
            locked = 0
        alvo_ef = 0 if (locked != 0 and alvo == locked) else alvo

        if alvo_ef != pos:
            if pos != 0:
                fechar("regime")
                pos, entry_price, bars_held = 0, None, 0
            if alvo_ef != 0:
                pos = alvo_ef
                entry_price = price
                entry_equity = equity
                entry_dt = dt[i]
                bars_held = 0
                peak_price = trough_price = price

        if pos != 0:
            bars_held += 1

    return {
        "equity_final": equity, "retorno_%": (equity / capital0 - 1) * 100,
        "max_drawdown_%": max_dd * 100, "trades": trades,
        "eq_curve": eq_curve, "start": start, "capital0": capital0,
    }


def imprimir_relatorio(df, res, par, timeframe, leverage):
    closes = df["close"].values
    start = res["start"]
    trades = res["trades"]
    bh = (closes[-1] / closes[start] - 1) * 100

    wins = [t for t in trades if t["ret_liq_%"] > 0]
    losses = [t for t in trades if t["ret_liq_%"] <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    avg_w = np.mean([t["ret_liq_%"] for t in wins]) if wins else 0
    avg_l = np.mean([t["ret_liq_%"] for t in losses]) if losses else 0
    taxa_total = sum(t["taxa_paga"] for t in trades)
    liqs = [t for t in trades if t["motivo"] == "liquidacao"]

    print("\n" + "=" * 64)
    print(f" BACKTEST  {par}  {timeframe}  |  alavancagem {leverage:g}x")
    print(f" Periodo: {df['datetime'].iloc[start]}  ->  {df['datetime'].iloc[-1]}")
    print("=" * 64)
    print(f" Capital inicial ....... {res['capital0']:>12,.2f}")
    print(f" Capital final ......... {res['equity_final']:>12,.2f}")
    print(f" RETORNO do bot ........ {res['retorno_%']:>11,.2f}%")
    print(f" Buy & Hold (benchmark)  {bh:>11,.2f}%")
    print(f" >> Bot {'BATEU' if res['retorno_%'] > bh else 'PERDEU para'} o buy-and-hold")
    print("-" * 64)
    print(f" Max drawdown .......... {res['max_drawdown_%']:>11,.2f}%")
    print(f" Numero de trades ...... {len(trades):>12}")
    print(f" Win rate .............. {win_rate:>11,.1f}%   (esperado ser baixo!)")
    print(f" Ganho medio (trade+) .. {avg_w:>11,.2f}%")
    print(f" Perda media (trade-) .. {avg_l:>11,.2f}%")
    print(f" Taxa total paga ....... {taxa_total:>12,.2f}  ({taxa_total/res['capital0']*100:.1f}% do capital)")
    print(f" Liquidacoes ........... {len(liqs):>12}")
    print("-" * 64)

    print(" Ultimos 10 trades:")
    print(f"   {'entrada':<16} {'dir':<6} {'entrada':>9} {'saida':>9} {'ret%':>8} {'motivo':<11}")
    for t in trades[-10:]:
        ent = pd.Timestamp(t["entrada_dt"]).strftime("%Y-%m-%d %H:%M")
        print(f"   {ent:<16} {t['direcao']:<6} {t['entrada']:>9.2f} {t['saida']:>9.2f} "
              f"{t['ret_liq_%']:>7.2f}% {t['motivo']:<11}")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    PAR, TF, DIAS, LEV = "ETH/USDT", "1h", 540, 3.0
    print(f"Baixando {DIAS} dias de {PAR} {TF} (gratis, sem chave)...")
    df = baixar_ohlcv(PAR, TF, dias=DIAS)
    print(f"OK: {len(df)} candles.")
    df = gerar_sinais(df)
    res = rodar_backtest(df, leverage=LEV, tf_horas=1.0)
    imprimir_relatorio(df, res, PAR, TF, LEV)
    pd.DataFrame(res["eq_curve"], columns=["datetime", "equity"]).to_csv("equity_curve.csv", index=False)
    print("Curva de capital salva em equity_curve.csv")
