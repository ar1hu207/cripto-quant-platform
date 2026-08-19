"""
Experimento duplo:
  (1) o FILTRO de tendencia macro (MA200) melhora os resultados? (com vs sem)
  (2) a estrategia sobrevive numa BULL market, ou so funciona em bear?

Compara em 3 periodos (bull / bear / geral) x 3 moedas, em 4h e 1x.
"""
from dados import baixar_ohlcv
from estrategia import gerar_sinais
from backtest import rodar_backtest

ATIVOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
DIAS = 1800            # ~5 anos de historico p/ poder fatiar periodos
TF = "4h"
TF_HORAS = 4
LEV = 1

PERIODOS = {
    "BULL  (jan/2023 -> mar/2024)": ("2023-01-01", "2024-03-15"),
    "BEAR  (dez/2024 -> jun/2026)": ("2024-12-01", "2026-06-01"),
    "GERAL (jan/2022 -> jun/2026)": ("2022-01-01", "2026-06-01"),
}


def rodar_no_periodo(df_full, inicio, fim):
    sub = df_full[(df_full["datetime"] >= inicio) & (df_full["datetime"] <= fim)].reset_index(drop=True)
    if len(sub) < 50:
        return None
    res = rodar_backtest(sub, leverage=LEV, tf_horas=TF_HORAS)
    closes = sub["close"].values
    start = res["start"]
    bh = (closes[-1] / closes[start] - 1) * 100
    trades = res["trades"]
    wr = (sum(1 for t in trades if t["ret_liq_%"] > 0) / len(trades) * 100) if trades else 0
    return res["retorno_%"], bh, res["max_drawdown_%"], len(trades), wr


# pre-carrega dados e indicadores (com e sem filtro) por ativo
cache = {}
for ativo in ATIVOS:
    raw = baixar_ohlcv(ativo, TF, dias=DIAS)
    cache[ativo] = {
        "sem": gerar_sinais(raw, filtro_tendencia=False),
        "COM": gerar_sinais(raw, filtro_tendencia=True),
    }

for nome, (inicio, fim) in PERIODOS.items():
    print(f"\n{'='*70}\n  {nome}   |  {TF}, {LEV}x")
    print(f"{'='*70}")
    print(f"  {'ativo':<9}{'filtro':<7}{'trades':>7}{'retorno%':>11}{'B&H%':>10}{'maxDD%':>9}{'win%':>7}")
    print("  " + "-" * 58)
    for ativo in ATIVOS:
        for tag in ["sem", "COM"]:
            r = rodar_no_periodo(cache[ativo][tag], inicio, fim)
            if r is None:
                continue
            ret, bh, dd, n, wr = r
            marca = "  << B&H" if ret > bh else ""
            print(f"  {ativo:<9}{tag:<7}{n:>7}{ret:>11.1f}{bh:>10.1f}{dd:>9.1f}{wr:>7.1f}{marca}")
        print()
print('"<< B&H" = bateu o buy-and-hold naquele periodo\n')
