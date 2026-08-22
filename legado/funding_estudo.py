"""
Estudo RIGOROSO do funding arb (cash & carry: long spot + short perp, delta-neutro).
Testa a estratégia REAL que o monitor habilita: DEPLOY quando o funding anualizado passa
um gatilho, SAI quando esfria (histerese p/ não girar à toa). Histórico LONGO (multi-regime)
pra capturar bull (funding gordo) e calmo (funding ~0). Líquido de taxa MAKER (ordem limite).

Caveat honesto: NÃO modela o basis (perp vs spot) — risco residual; o termo dominante é
funding − taxa. Idle = capital não rende (anualização sobre o período TOTAL é a real).

Rodar:  python funding_estudo.py
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import ccxt

ex = ccxt.binanceusdm({"enableRateLimit": True})
COINS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT",
         "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "LTC/USDT", "DOT/USDT", "NEAR/USDT"]
DIAS = 540
MAKER = 0.0002
NOTIONAL = 1000


def hist_longo(sym, dias):
    fim = ex.milliseconds()
    since = fim - dias * 86400 * 1000
    out, seen = [], set()
    while since < fim:
        lote = ex.fetch_funding_rate_history(sym, since=since, limit=1000)
        if not lote:
            break
        for h in lote:
            ts, fr = h["timestamp"], h.get("fundingRate")
            if fr is not None and ts not in seen:
                seen.add(ts)
                out.append((ts, fr))
        since = lote[-1]["timestamp"] + 1
        if len(lote) < 1000:
            break
    out.sort()
    return out


def simular(hist, thr_in_anual, thr_out_anual, taxa=MAKER, notional=NOTIONAL):
    """Deploy quando funding anualizado > thr_in; sai quando < thr_out. Short recebe funding>0."""
    if len(hist) < 30:
        return None
    difs = sorted(hist[i][0] - hist[i - 1][0] for i in range(1, len(hist)))
    dt = difs[len(difs) // 2] or 8 * 3600 * 1000
    settl_dia = 86400000 / dt
    em_pos = False
    funding = custo = 0.0
    ciclos = t_in = 0
    for ts, fr in hist:
        anual = fr * settl_dia * 365 * 100         # anualizado em % (mesma unidade do gatilho)
        if not em_pos:
            if anual > thr_in_anual:
                em_pos = True
                ciclos += 1
                custo += 4 * taxa * notional       # entrar (2 legs) + sair (2 legs)
        else:
            funding += fr * notional               # short recebe funding>0
            t_in += 1
            if anual < thr_out_anual:
                em_pos = False
    liq = funding - custo
    dias = (hist[-1][0] - hist[0][0]) / 86400000
    return {"liq": liq, "anual_total": (liq / notional / dias * 365 * 100) if dias > 0 else 0,
            "anual_deploy": (liq / notional / (t_in / settl_dia) * 365 * 100) if t_in else 0,
            "pct_in": t_in / len(hist) * 100, "ciclos": ciclos, "dias": round(dias), "settl": round(settl_dia, 1)}


print(f"ESTUDO FUNDING ARB | {len(COINS)} moedas | {DIAS}d | maker {MAKER*100}%/lado | notional R${NOTIONAL}")
print("baixando histórico de funding (longo)...")
hs = {}
for c in COINS:
    try:
        hs[c] = hist_longo(c, DIAS)
    except Exception as e:
        print(f"  falha {c}: {e}")
ok = {c: h for c, h in hs.items() if len(h) >= 100}
print(f"ok — {len(ok)} moedas com histórico suficiente\n")

# always-in (baseline) vs gated em vários gatilhos
print(f"{'estratégia':>26}  {'anual médio (total)':>20}  {'%tempo':>7}  {'positivas':>10}")
print("-" * 70)
estrategias = [("always-in", -1e9, -1e9)] + [(f"gate {t}%/-{max(t//3,5)}%", t, max(t // 3, 5))
                                             for t in (10, 15, 20, 30, 50)]
for nome, ti, to in estrategias:
    anuais, pcts = [], []
    for c, h in ok.items():
        r = simular(h, ti, to)
        if r:
            anuais.append(r["anual_total"]); pcts.append(r["pct_in"])
    if anuais:
        med = sum(anuais) / len(anuais)
        pos = sum(1 for a in anuais if a > 0)
        print(f"{nome:>26}  {med:>+18.1f}%  {sum(pcts)/len(pcts):>6.0f}%  {pos:>4}/{len(anuais)}")

# detalhe por moeda no gate 20%
print(f"\nDetalhe por moeda (gate 20%/-6%):")
print(f"{'moeda':>10}  {'anual total':>12}  {'anual deployado':>16}  {'%tempo':>7}  {'ciclos':>7}  {'dias':>5}")
for c, h in ok.items():
    r = simular(h, 20, 6)
    if r:
        print(f"{c:>10}  {r['anual_total']:>+11.1f}%  {r['anual_deploy']:>+15.1f}%  {r['pct_in']:>6.0f}%  {r['ciclos']:>7}  {r['dias']:>5}")

print("\nLeitura: 'anual total' = rendimento líquido anualizado sobre o período INTEIRO (idle=0).")
print("'anual deployado' = rendimento só nos períodos em que estava na trade (mostra o prêmio quando o funding está gordo).")
print("Edge real = anual total positivo e consistente (maioria das moedas) num gate operável.")
