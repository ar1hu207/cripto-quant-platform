"""
Varredura de parametros: compara timeframes e alavancagens.
Objetivo: achar config que reduz taxa (menos trades) e drawdown.
"""
from dados import baixar_ohlcv
from estrategia import gerar_sinais
from backtest import rodar_backtest

PAR = "ETH/USDT"
DIAS = 540
TF_HORAS = {"1h": 1, "4h": 4, "1d": 24}

print(f"\n{'TF':<5}{'lev':>4}{'trades':>8}{'retorno%':>11}{'B&H%':>9}{'maxDD%':>9}{'taxa%cap':>10}{'win%':>7}")
print("-" * 63)
for tf in ["1h", "4h", "1d"]:
    df = baixar_ohlcv(PAR, tf, dias=DIAS)
    df = gerar_sinais(df)
    closes = df["close"].values
    for lev in [1, 2, 3]:
        res = rodar_backtest(df, leverage=lev, tf_horas=TF_HORAS[tf])
        start = res["start"]
        bh = (closes[-1] / closes[start] - 1) * 100
        trades = res["trades"]
        wr = (sum(1 for t in trades if t["ret_liq_%"] > 0) / len(trades) * 100) if trades else 0
        taxa = sum(t["taxa_paga"] for t in trades) / res["capital0"] * 100
        marca = "  <<" if res["retorno_%"] > bh else ""
        print(f"{tf:<5}{lev:>4}{len(trades):>8}{res['retorno_%']:>11.1f}{bh:>9.1f}"
              f"{res['max_drawdown_%']:>9.1f}{taxa:>10.1f}{wr:>7.1f}{marca}")
    print("-" * 63)
print('\n"<<" = bateu o buy-and-hold\n')
