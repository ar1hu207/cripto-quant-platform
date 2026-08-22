"""
Backtest HONESTO de DCA (Dollar-Cost Averaging) em dados reais da Binance.
v2 — corrigido apos auditoria adversarial (cash-drag, drawdown tautologico, enquadramento).

A pergunta "DCA vale a pena?" so faz sentido com o enquadramento certo. Sao DOIS:

  CENARIO A — "tenho o montante HOJE" (academico): lump vs DCA com o MESMO capital
    no MESMO dia 0. Pra ser JUSTO, o caixa que o DCA ainda nao aplicou tem que render
    o risk-free (CDI) — senao a comparacao e pessimista pro DCA (cash-drag). Aqui o
    DCA e modelado como carteira de 2 pernas: caixa@CDI + cripto, pingando no ativo.
    Drawdown medido sobre a carteira TOTAL (caixa+cripto) = dor real, comparavel ao lump.

  CENARIO B — "invisto minha RENDA aos poucos" (o caso do varejista): lump nem e opcao,
    o dinheiro nao existia antes. A regua honesta e o XIRR (money-weighted, conta cada
    R$ pelo tempo exposto) e a comparacao relevante e: pingar no ativo bateu deixar a
    mesma renda no CDI? E quanto do "beta" do ativo voce capturou?

Regua de comparacao: XIRR/CAGR (money-weighted), NUNCA "valor final cru" (que so mede
se o ativo subiu cedo). Vieses DECLARADOS: survivorship (so BTC/ETH, sobreviventes que
subiram — NAO extrapolar pra alts), end-point unico (fim = hoje; janelas roladas tem
overlap alto => ~poucos regimes independentes, % sao indicativos), sem impostos,
aporte nominal fixo em USDT (ignora inflacao/cambio BRL), taxa spot 0.1% (taker Binance).
"""
import numpy as np
import pandas as pd

import dados

RF_ANUAL_PADRAO = 0.10   # CDI/SELIC ~ Brasil no periodo (premissa do caixa parado; ajustavel)


# ----------------- dados -----------------
def historico(ativo="BTC/USDT", anos=6):
    df = dados.baixar_ohlcv(par=ativo, timeframe="1d", dias=int(anos * 365 + 5))
    df = df.dropna(subset=["close"]).reset_index(drop=True)
    return df["datetime"].to_numpy(), df["close"].to_numpy(dtype=float)


# ----------------- metricas -----------------
def max_drawdown_pct(serie):
    s = np.asarray(serie, dtype=float)
    if len(s) == 0:
        return float("nan")
    pico = np.maximum.accumulate(s)
    pico = np.where(pico <= 0, np.nan, pico)
    dd = (s - pico) / pico
    m = np.nanmin(dd) if np.any(np.isfinite(dd)) else np.nan
    return float(m * 100) if np.isfinite(m) else float("nan")


def _anos_entre(d0, d1):
    return max((pd.Timestamp(d1) - pd.Timestamp(d0)).days, 1) / 365.25


def cagr_pct(inicial, final, datas):
    if inicial <= 0 or final <= 0:
        return float("nan")
    return ((final / inicial) ** (1 / _anos_entre(datas[0], datas[-1])) - 1) * 100


def xirr(cashflows, lo=-0.9999, hi=100.0, tol=1e-7, it=200):
    """Retorno anual money-weighted. cashflows=[(date,amount)], saidas negativas.
    Consolida fluxos de MESMA data antes de resolver (corrige cashflow duplicado)."""
    if len(cashflows) < 2:
        return None
    acc = {}
    for d, a in cashflows:
        k = pd.Timestamp(d)
        acc[k] = acc.get(k, 0.0) + a
    itens = sorted(acc.items())
    t0 = itens[0][0]
    anos = np.array([_anos_entre(t0, d) if d != t0 else 0.0 for d, _ in itens])
    amt = np.array([a for _, a in itens], dtype=float)

    def npv(r):
        return float(np.sum(amt / (1.0 + r) ** anos))

    f_lo, f_hi = npv(lo), npv(hi)
    if np.isnan(f_lo) or np.isnan(f_hi) or f_lo * f_hi > 0:
        return None
    for _ in range(it):
        mid = (lo + hi) / 2
        f = npv(mid)
        if abs(f) < tol:
            return mid
        if f_lo * f < 0:
            hi = mid
        else:
            lo, f_lo = mid, f
    return (lo + hi) / 2


def _idx_aportes(n, freq):
    """Dias de aporte. NUNCA aporta no ultimo candle (evita compra marcada a mercado
    no mesmo instante = aporte de timing perfeito + cashflow duplicado na data final)."""
    return list(range(0, max(1, n - 1), max(1, int(freq))))


# ----------------- CENARIO A: tenho o montante hoje (JUSTO vs lump) -----------------
def dca_com_caixa(datas, closes, valor, freq, taxa, rf_anual):
    """Carteira de 2 pernas: comeca com TODO o capital em caixa (= lump), o caixa rende
    rf_anual ao dia, e a cada `freq` dias transfere `valor` do caixa pra cripto.
    Mesma base do lump (mesmo capital, mesmo dia 0) => comparacao money-neutral."""
    n = len(closes)
    idx = set(_idx_aportes(n, freq))
    capital = valor * len(idx)
    rf_d = (1 + rf_anual) ** (1 / 365.0) - 1
    caixa, unidades = float(capital), 0.0
    total = np.zeros(n)
    for i in range(n):
        if i > 0:
            caixa *= (1 + rf_d)              # caixa parado rende CDI todo dia
        if i in idx and caixa > 0:
            ap = min(valor, caixa)
            caixa -= ap
            unidades += ap * (1 - taxa) / closes[i]
        total[i] = caixa + unidades * closes[i]
    final = caixa + unidades * closes[-1]
    return {"capital": capital, "valor_final": float(final), "caixa_final": float(caixa),
            "unidades": unidades, "cagr_pct": cagr_pct(capital, final, datas),
            "max_dd_pct": max_drawdown_pct(total), "total_series": total}


def lump(datas, closes, capital, taxa):
    unidades = (capital * (1 - taxa)) / closes[0]
    serie = unidades * closes
    final = float(unidades * closes[-1])
    return {"capital": capital, "valor_final": final, "unidades": unidades,
            "cagr_pct": cagr_pct(capital, final, datas),
            "max_dd_pct": max_drawdown_pct(serie), "total_series": serie}


# ----------------- CENARIO B: invisto minha renda aos poucos -----------------
def dca_renda(datas, closes, valor, freq, taxa, rf_anual):
    """DCA puro: o dinheiro entra so quando e aportado (nao existia antes). XIRR sobre
    os cashflows REAIS. Compara com pingar a MESMA renda no CDI (sem cripto)."""
    n = len(closes)
    idx = _idx_aportes(n, freq)
    unidades, investido = 0.0, 0.0
    cf, cdi_final = [], 0.0
    rf = rf_anual
    for i in idx:
        unidades += valor * (1 - taxa) / closes[i]
        investido += valor
        cf.append((datas[i], -valor))
        cdi_final += valor * (1 + rf) ** _anos_entre(datas[i], datas[-1])  # mesma renda no CDI
    final = float(unidades * closes[-1])
    r = xirr(cf + [(datas[-1], final)])
    return {"n_aportes": len(idx), "investido": investido, "unidades": unidades,
            "valor_final": final, "retorno_total_pct": (final / investido - 1) * 100 if investido else 0,
            "xirr_pct": (r * 100) if r is not None else None,
            "custo_medio": investido / unidades if unidades else 0.0, "preco_final": float(closes[-1]),
            "cdi_final": cdi_final, "cdi_xirr_pct": rf_anual * 100}


# ----------------- janelas roladas (JUSTO: DCA-com-caixa vs lump) -----------------
def janelas_roladas(datas, closes, valor, freq, dur_dias, passo, taxa, rf_anual):
    n = len(closes)
    res = []
    for ini in range(0, n - dur_dias, passo):
        sl = slice(ini, ini + dur_dias)
        d, c = datas[sl], closes[sl]
        dca = dca_com_caixa(d, c, valor, freq, taxa, rf_anual)
        lp = lump(d, c, dca["capital"], taxa)
        res.append({"dca_vence": dca["valor_final"] > lp["valor_final"],
                    "razao": dca["valor_final"] / lp["valor_final"] if lp["valor_final"] else 1.0,
                    "dca_dd": dca["max_dd_pct"], "lump_dd": lp["max_dd_pct"]})
    return res


# ----------------- relatorio -----------------
def sensibilidade_rf(ativos=("BTC/USDT", "ETH/USDT"), anos_janelas=(2, 3, 6),
                     valor=50, freq=7, taxa=0.001, rfs=(0.04, 0.07, 0.10, 0.13)):
    """Cenario B (renda aos poucos): pingar no ativo BATE deixar a mesma renda no risk-free?
    Varre varias taxas risk-free (rf). Sacada provada aqui: como DCA e CDI tem os MESMOS
    cashflows (os aportes), o DCA bate o CDI <=> rf < XIRR_DCA. Ou seja, a taxa de
    breakeven e EXATAMENTE o XIRR do DCA (independe de rf). Provado numericamente abaixo."""
    L = "=" * 100
    print(L)
    print(f"SENSIBILIDADE AO RISK-FREE (cenario B: pingar R${valor}/{freq}d vs deixar no risk-free)")
    print(f"breakeven = XIRR do DCA (abaixo dele, cripto-DCA vence; acima, o risk-free vence)")
    print(L)
    cab = "  ativo  jan |  XIRR DCA | breakeven |" + "".join(f"  rf {int(r*100):>2}% " for r in rfs)
    print(cab)
    print("  " + "-" * (len(cab) - 2))
    for ativo in ativos:
        datas, closes = historico(ativo, anos=max(anos_janelas))
        sigla = ativo.split("/")[0]
        for anos in anos_janelas:
            ndias = int(anos * 365)
            if ndias > len(closes):
                continue
            d, c = datas[-ndias:], closes[-ndias:]
            B = dca_renda(d, c, valor, freq, taxa, 0.0)  # XIRR independe de rf
            xirr_pct = B["xirr_pct"]
            cels = ""
            for rf in rfs:
                Brf = dca_renda(d, c, valor, freq, taxa, rf)
                vence = Brf["valor_final"] > Brf["cdi_final"]
                cels += f"   {'DCA' if vence else 'CDI':>3}  "
            be = f"{xirr_pct:+5.1f}%" if xirr_pct is not None else " n/d "
            xs = f"{xirr_pct:+6.1f}%" if xirr_pct is not None else "  n/d "
            print(f"  {sigla:>4} {anos}a  | {xs}/a | {be}/a |{cels}")
    print("  " + "-" * (len(cab) - 2))
    # PROVA: ao escolher rf == XIRR_DCA, o valor no CDI deve igualar o valor final do DCA
    datas, closes = historico("BTC/USDT", anos=6)
    d, c = datas[-int(6*365):], closes[-int(6*365):]
    base = dca_renda(d, c, valor, freq, taxa, 0.0)
    rstar = base["xirr_pct"] / 100
    prova = dca_renda(d, c, valor, freq, taxa, rstar)
    print(f"\n  PROVA do breakeven (BTC 6a): rf = XIRR = {rstar*100:.2f}%/a -> "
          f"CDI final R${prova['cdi_final']:,.0f} ~ DCA final R${prova['valor_final']:,.0f} "
          f"(dif {abs(prova['cdi_final']-prova['valor_final'])/prova['valor_final']*100:.2f}%)")
    print(L)


def rodar(ativos=("BTC/USDT", "ETH/USDT"), anos_janelas=(2, 3, 6),
          valor=50, freq=7, taxa=0.001, rf_anual=RF_ANUAL_PADRAO):
    L = "=" * 100
    print(L)
    print(f"BACKTEST DCA v2 (honesto) | aporte R${valor}/{freq}d | taxa {taxa*100:.2f}% | "
          f"caixa rende CDI {rf_anual*100:.0f}%/a | hoje {pd.Timestamp.now():%Y-%m-%d}")
    print(L)
    for ativo in ativos:
        datas, closes = historico(ativo, anos=max(anos_janelas))
        print(f"\n### {ativo}  ({len(closes)} dias, desde {pd.Timestamp(datas[0]):%Y-%m-%d})  "
              f"preco {closes[0]:,.0f} -> {closes[-1]:,.0f}")
        for anos in anos_janelas:
            ndias = int(anos * 365)
            if ndias > len(closes):
                continue
            d, c = datas[-ndias:], closes[-ndias:]
            ini = pd.Timestamp(d[0]).strftime("%Y-%m-%d")
            ativo_ret = (c[-1] / c[0] - 1) * 100
            A = dca_com_caixa(d, c, valor, freq, taxa, rf_anual)
            LP = lump(d, c, A["capital"], taxa)
            B = dca_renda(d, c, valor, freq, taxa, rf_anual)
            print(f"\n  -- janela {anos}a (desde {ini}) | o ativo fez {ativo_ret:+.0f}% no periodo --")
            print(f"   [A] tenho R${A['capital']:,.0f} hoje (regua JUSTA: caixa rende CDI, mesma base):")
            print(f"       DCA c/ caixa: final R${A['valor_final']:>9,.0f} | CAGR {A['cagr_pct']:+6.1f}%/a | maxDD carteira {A['max_dd_pct']:6.1f}%")
            print(f"       LUMP (dia 0): final R${LP['valor_final']:>9,.0f} | CAGR {LP['cagr_pct']:+6.1f}%/a | maxDD {LP['max_dd_pct']:6.1f}%")
            venc = "DCA" if A["valor_final"] > LP["valor_final"] else "LUMP"
            print(f"       -> {venc} rende mais (regua CAGR); DCA segura {A['caixa_final']/A['capital']*100:.0f}% em caixa no fim")
            print(f"   [B] invisto R${valor}/{freq}d da minha renda (lump nem e opcao):")
            xb = f"{B['xirr_pct']:+.1f}%/a" if B["xirr_pct"] is not None else "n/d"
            print(f"       DCA renda: investido R${B['investido']:,.0f} -> R${B['valor_final']:,.0f} | XIRR {xb} "
                  f"| vs mesma renda no CDI R${B['cdi_final']:,.0f} ({rf_anual*100:.0f}%/a)")
            ganhou = "BATEU o CDI" if B["valor_final"] > B["cdi_final"] else "PERDEU pro CDI"
            print(f"       -> pingar no {ativo.split('/')[0]} {ganhou} | custo medio R${B['custo_medio']:,.0f} (preco final R${B['preco_final']:,.0f})")
        # janelas roladas JUSTAS (com caixa@CDI), 2 duracoes
        for dur in (365, 730):
            if len(closes) > dur + 60:
                jr = janelas_roladas(datas, closes, valor, freq, dur, 30, taxa, rf_anual)
                if jr:
                    pv = 100 * sum(x["dca_vence"] for x in jr) / len(jr)
                    razoes = sorted(x["razao"] for x in jr)
                    med = razoes[len(razoes) // 2]
                    print(f"\n  -- janelas roladas {dur//365 if dur%365==0 else dur}{'a' if dur%365==0 else 'd'} "
                          f"({len(jr)} inicios, passo 30d, regua JUSTA c/ caixa@CDI) --")
                    print(f"     DCA rende MAIS que lump em {pv:.0f}% | razao mediana DCA/lump {med:.2f}  "
                          f"(overlap alto => ~poucos regimes independentes; indicativo, nao probabilidade)")
    print("\n" + L)
    print("LEITURA HONESTA:")
    print("  - Regua justa = CAGR/XIRR (money-weighted). 'Valor final cru' so mede se o ativo subiu cedo.")
    print("  - [A] Em ativo que SOBE, lump tende a render mais (mais tempo no mercado) MESMO com caixa@CDI;")
    print("        a vantagem encolhe vs o backtest ingenuo, mas em bull longo (6a) sobrevive.")
    print("  - [B] Pro varejista (renda aos poucos) lump nem existe: a pergunta e 'bati o CDI / capturei o beta?'.")
    print("  - DCA NAO 'reduz drawdown' como proteca: aquele 100% era artefato (menos capital exposto cedo).")
    print("  - Tudo condicionado a o ativo SOBREVIVER e subir (BTC/ETH). Pra alt que estagna, DCA acumula perda.")
    print(L)


if __name__ == "__main__":
    rodar()
