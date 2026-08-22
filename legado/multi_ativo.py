"""
Teste de ROBUSTEZ: a estrategia funciona em varias moedas ou so no ETH?
Se o edge aparece em BTC/SOL/BNB tambem -> comeca a ser confiavel.
Se so no ETH -> foi sorte de periodo/ativo.
"""
from dados import baixar_ohlcv
from estrategia import gerar_sinais
from backtest import rodar_backtest

ATIVOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
DIAS = 540
TF_HORAS = {"4h": 4, "1d": 24}

for tf in ["4h", "1d"]:
    print(f"\n========== Timeframe {tf} ==========")
    print(f"{'ativo':<10}{'lev':>4}{'trades':>8}{'retorno%':>11}{'B&H%':>10}{'maxDD%':>9}{'win%':>7}")
    print("-" * 59)
    for ativo in ATIVOS:
        df = baixar_ohlcv(ativo, tf, dias=DIAS)
        df = gerar_sinais(df)
        closes = df["close"].values
        for lev in [1, 2]:
            res = rodar_backtest(df, leverage=lev, tf_horas=TF_HORAS[tf])
            start = res["start"]
            bh = (closes[-1] / closes[start] - 1) * 100
            trades = res["trades"]
            wr = (sum(1 for t in trades if t["ret_liq_%"] > 0) / len(trades) * 100) if trades else 0
            marca = "  <<" if res["retorno_%"] > bh else ""
            print(f"{ativo:<10}{lev:>4}{len(trades):>8}{res['retorno_%']:>11.1f}"
                  f"{bh:>10.1f}{res['max_drawdown_%']:>9.1f}{wr:>7.1f}{marca}")
        print()
print('"<<" = bateu o buy-and-hold\n')
