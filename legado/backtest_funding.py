"""
Backtest do FUNDING ARBITRAGE (cash & carry): long spot + short perp, delta-neutral.
Você COLHE o funding (longs pagam shorts quando funding>0). P&L ~= funding recebido
- taxas. Valida se o edge ESTRUTURAL sobrevive aos custos ANTES de construir o motor
de 2 pernas.

Caveat honesto: NAO modela o basis (perp vs spot) na entrada/saida -- risco extra nao
capturado. Mas o termo dominante (funding - taxa) e o que decide se ha edge.

Rodar:  python backtest_funding.py
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import ccxt

ex = ccxt.binanceusdm({"enableRateLimit": True})
COINS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT",
         "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "LTC/USDT", "DOT/USDT", "NEAR/USDT",
         "ARB/USDT", "OP/USDT", "INJ/USDT"]
NOTIONAL = 1000
MAKER, TAKER = 0.0002, 0.0005


def hist(sym):
    fr = ex.fetch_funding_rate_history(sym, limit=1000)
    return [(f["timestamp"], f["fundingRate"]) for f in fr if f.get("fundingRate") is not None]


def carry_hold(h, taxa):
    """Cash & carry REALISTA: entra UMA vez, SEGURA, colhe todo o funding (recebe quando
    >0, paga quando <0), 1 round-trip de taxa. Isola o rendimento bruto do carry."""
    soma_fr = sum(fr for _, fr in h)
    bruto = soma_fr * NOTIONAL
    custo = 4 * taxa * NOTIONAL                       # 1 entrada (2 legs) + 1 saida (2 legs)
    liq = bruto - custo
    dias = (h[-1][0] - h[0][0]) / 1000 / 86400 if len(h) > 1 else 0
    anual = (liq / NOTIONAL / dias * 365 * 100) if dias > 0 else 0
    funding_medio_anual = (soma_fr / len(h)) * 3 * 365 * 100 if h else 0   # funding medio anualizado
    pct_alto = sum(1 for _, fr in h if fr > 0.0001) / len(h) * 100 if h else 0  # % tempo funding "gordo" (>0,01%/8h)
    return dict(liq=liq, anual=anual, fmed=funding_medio_anual, pct_alto=pct_alto, dias=round(dias))


print("FUNDING ARB (cash & carry) | long spot + short perp | SEGURA a posicao (sem girar)")
print(f"notional R${NOTIONAL}\n")
print("baixando historico de funding...")
hs = {}
for c in COINS:
    try:
        hs[c] = hist(c)
    except Exception as e:
        print(f"  falha {c}: {e}")
print("ok.\n")

dias_hist = 0
print(f"{'coin':<10}{'funding med/ano':>16}{'% tempo gordo':>15}{'liq/ano MAKER':>15}{'liq/ano TAKER':>15}")
print("-" * 71)
fmeds, makers, takers = [], [], []
for c in COINS:
    if c not in hs or len(hs[c]) < 30:
        continue
    rm = carry_hold(hs[c], MAKER)
    rt = carry_hold(hs[c], TAKER)
    dias_hist = rm["dias"]
    fmeds.append(rm["fmed"]); makers.append(rm["anual"]); takers.append(rt["anual"])
    print(f"{c:<10}{rm['fmed']:>+15.1f}%{rm['pct_alto']:>14.0f}%{rm['anual']:>+14.1f}%{rt['anual']:>+14.1f}%")

n = len(fmeds)
print("-" * 71)
print(f"{'MEDIA':<10}{sum(fmeds)/n:>+15.1f}%{'':>15}{sum(makers)/n:>+14.1f}%{sum(takers)/n:>+14.1f}%")
print(f"\n(~{dias_hist}d de historico | 'gordo' = funding > 0,01%/8h)")
print("\nLeitura: 'funding med/ano' = o rendimento BRUTO do carry, neutro ao mercado.")
print("Se baixo agora => mercado calmo (sem multidao comprada). O edge APARECE em")
print("regimes de funding alto (bull com longs lotados). E uma estrategia de DEPLOY")
print("OPORTUNISTA (liga quando funding ta gordo), nao um gerador sempre-ligado.")
