"""
Dados de mercado: sentimento (Fear & Greed + breadth) e "smart money" (funding
rate = multidão posicionada + zonas de liquidez = topos/fundos onde stops/liquidações
se acumulam). Tudo de fonte pública/grátis.

Honestidade: mapa de liquidação REAL (Coinglass/Hyblock) exige dados pagos. Aqui é
um PROXY: funding mostra a multidão, e os swing highs/lows mostram onde a liquidez
(stops) provavelmente está — pra onde o preço costuma ser "puxado".
"""
import json
import time
import urllib.request

import ccxt

import db

ex_spot = ccxt.binance({"enableRateLimit": True})
ex_fut = ccxt.binanceusdm({"enableRateLimit": True})
_cache = {"sent": None, "sent_t": 0.0}
_pcache = {"p": {}, "t": 0.0, "key": ""}


def precos(ativos):
    """Preço ao vivo (last) de vários ativos num request só (fetch_tickers). Cache 5s."""
    key = ",".join(sorted(ativos))
    if time.time() - _pcache["t"] < 5 and _pcache["key"] == key:
        return _pcache["p"]
    try:
        tk = ex_spot.fetch_tickers(ativos)
        p = {a: tk[a]["last"] for a in ativos if a in tk}
    except Exception:
        p = {}
    _pcache.update(p=p, t=time.time(), key=key)
    return p


def fear_greed():
    try:
        with urllib.request.urlopen("https://api.alternative.me/fng/?limit=1", timeout=6) as r:
            d = json.load(r)["data"][0]
        return {"valor": int(d["value"]), "label": d["value_classification"]}
    except Exception:
        return None


def breadth():
    ativos = [a.strip() for a in db.get_config()["ativos"].split(",") if a.strip()]
    up = tot = 0
    soma = 0.0
    for a in ativos:
        try:
            p = ex_spot.fetch_ticker(a)["percentage"]
            tot += 1
            soma += p
            up += 1 if p > 0 else 0
        except Exception:
            pass
    if not tot:
        return None
    return {"pct_subindo": round(up / tot * 100), "variacao_media": round(soma / tot, 2), "n": tot}


def sentimento():
    if _cache["sent"] is None or time.time() - _cache["sent_t"] > 60:
        _cache["sent"] = {"fear_greed": fear_greed(), "breadth": breadth()}
        _cache["sent_t"] = time.time()
    return _cache["sent"]


def funding(ativo):
    try:
        fr = ex_fut.fetch_funding_rate(ativo)
        return round(fr["fundingRate"] * 100, 4)   # em %
    except Exception:
        return None


_fcache = {"r": [], "t": 0.0}


def _settlements_dia(info):
    """Quantos settlements de funding por dia (8h=3, 4h=6). Lê o intervalo do ccxt; fallback 3."""
    iv = (info or {}).get("interval")                       # ex '8h', '4h' (ccxt unified)
    try:
        h = int(str(iv).rstrip("hH"))
        return (24 / h) if h else 3
    except Exception:
        return 3


def funding_ranking(thr_anual=15.0):
    """Funding de todas as moedas, anualizado (settlement POR MOEDA × 365) + flag 'gordo'
    (>=thr_anual%/ano). Gatilho do carry: quando engorda, há prêmio. Cache 60s."""
    if time.time() - _fcache["t"] < 60 and _fcache["r"]:
        return _fcache["r"]
    ativos = [a.strip() for a in db.get_config()["ativos"].split(",") if a.strip()]
    try:
        todos = ex_fut.fetch_funding_rates(ativos)         # 1 request pra todos
    except Exception:
        todos = {}
    out = []
    for a in ativos:
        info = todos.get(a) or {}
        fr = info.get("fundingRate")
        if fr is None:
            f = funding(a)                                  # fallback por moeda
            fr = f / 100 if f is not None else None
        if fr is None:
            continue
        sett = _settlements_dia(info)                       # 8h=3/dia, 4h=6/dia (corrige o ×3 fixo)
        anual = round(fr * sett * 365 * 100, 1)
        out.append({"ativo": a, "funding_pct": round(fr * 100, 4), "settl_dia": round(sett, 1),
                    "anual": anual, "gordo": anual >= thr_anual})
    out.sort(key=lambda x: -x["anual"])
    _fcache.update(r=out, t=time.time())
    return out


def zonas_liquidez(ativo, tf="1h", limite=200, k=5):
    raw = ex_spot.fetch_ohlcv(ativo, timeframe=tf, limit=limite)
    highs = [c[2] for c in raw]
    lows = [c[3] for c in raw]
    preco = raw[-1][4]
    topos, fundos = [], []
    for i in range(k, len(raw) - k):
        if highs[i] == max(highs[i - k:i + k + 1]):
            topos.append(round(highs[i], 6))
        if lows[i] == min(lows[i - k:i + k + 1]):
            fundos.append(round(lows[i], 6))
    acima = sorted(set(t for t in topos if t > preco))[:3]              # liquidez acima
    abaixo = sorted(set(f for f in fundos if f < preco), reverse=True)[:3]  # liquidez abaixo
    return {"preco": preco, "liquidez_acima": acima, "liquidez_abaixo": abaixo}


def smartmoney(ativo):
    f = funding(ativo)
    leitura = None
    if f is not None:
        if f > 0.01:
            leitura = "🔴 longs lotados (funding alto) → risco de squeeze pra BAIXO (liquidar longs)"
        elif f < -0.01:
            leitura = "🟢 shorts lotados (funding negativo) → risco de squeeze pra CIMA (liquidar shorts)"
        else:
            leitura = "⚪ funding neutro — sem multidão clara"
    return {"funding_pct": f, "leitura_funding": leitura, **zonas_liquidez(ativo)}


def book(ativo, prof=0.01):
    """Lê o order book + trades recentes: pressão compra/venda, paredes (dinheiro
    grande), e split dinheiro grande vs pequeno. Tudo de dados públicos."""
    try:
        ob = ex_spot.fetch_order_book(ativo, 100)
        trades = ex_spot.fetch_trades(ativo, limit=200)
    except Exception:
        return None
    bids, asks = ob["bids"], ob["asks"]
    if not bids or not asks:
        return None
    mid = (bids[0][0] + asks[0][0]) / 2
    bid_val = sum(p * q for p, q in bids if p >= mid * (1 - prof))   # $ de compra perto do preço
    ask_val = sum(p * q for p, q in asks if p <= mid * (1 + prof))   # $ de venda perto do preço
    tot = (bid_val + ask_val) or 1
    pb = max(bids[:50], key=lambda x: x[0] * x[1])                   # maior parede de compra
    pa = max(asks[:50], key=lambda x: x[0] * x[1])                   # maior parede de venda

    comprou = sum(t["amount"] * t["price"] for t in trades if t["side"] == "buy")
    vendeu = sum(t["amount"] * t["price"] for t in trades if t["side"] == "sell")
    vals = sorted(t["amount"] * t["price"] for t in trades)
    lim = vals[int(len(vals) * 0.9)] if vals else 0                  # top 10% = "dinheiro grande"
    gb = sum(t["amount"] * t["price"] for t in trades if t["amount"] * t["price"] >= lim and t["side"] == "buy")
    gs = sum(t["amount"] * t["price"] for t in trades if t["amount"] * t["price"] >= lim and t["side"] == "sell")
    return {
        "mid": round(mid, 6),
        "pressao_compra": round(bid_val / tot * 100, 1),            # % do book do lado comprador
        "parede_compra": {"preco": round(pb[0], 6), "valor": round(pb[0] * pb[1])},
        "parede_venda": {"preco": round(pa[0], 6), "valor": round(pa[0] * pa[1])},
        "fluxo_comprador": round(comprou / ((comprou + vendeu) or 1) * 100, 1),  # % taker comprando
        "grande_compra": round(gb), "grande_venda": round(gs),
        "lado_grande": "COMPRA" if gb > gs else ("VENDA" if gs > gb else "neutro"),
    }
