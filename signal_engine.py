"""
Sprint 1 - Engine de Sinais. Varre as criptos AO VIVO (preço real Binance),
pontua a convicção de cada oportunidade (trend + ADX + rompimento + RSI + volume)
e grava os sinais no banco. Esses sinais alimentam a fila de "confirmar trade".

Rodar:  python signal_engine.py          (loop)
        python signal_engine.py --once   (uma varredura)
"""
import sys
import time
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import ccxt
import pandas as pd

import db
from logbot import log
import mercado
from scoring import preparar, pontuar, pontuar_reversao

ex = ccxt.binance({"enableRateLimit": True})


def analisa(ativo, tf):
    """Avalia AMBAS as estratégias (tendência + reversão) pra um ativo/timeframe.
    Retorna LISTA de sinais candidatos (cada um com tipo e tf)."""
    raw = ex.fetch_ohlcv(ativo, timeframe=tf, limit=200)
    df = preparar(pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"]))
    i = len(df) - 2               # candle FECHADO (o último, -1, ainda está em formação = repaint)
    if i < 60:
        return []
    c = float(df["close"].iloc[i])
    out = []
    for fn in (pontuar, pontuar_reversao):              # mesma pontuação do backtest + reversão
        p = fn(df, i)
        if p is None or p["conviccao"] == 0:
            continue
        stop = c * (1 - p["direcao"] * p["stop_dist"])
        out.append(dict(ativo=ativo, tf=tf, tipo=p["tipo"],
                        direcao="LONG" if p["direcao"] == 1 else "SHORT",
                        conviccao=p["conviccao"], motivos=p["motivos"],
                        preco=round(c, 6), stop_sugerido=round(stop, 6),
                        adx=p["adx"], n_fatores=p["n_fatores"]))
    return out


def confirmado(s, ativo, cfg):
    """Portões de confirmação — DIFERENTES por estratégia.
    TENDÊNCIA: exige ADX alto + confluência + fluxo a favor.
    REVERSÃO: exige mercado LATERAL (ADX baixo); é contrarian (não exige fluxo)."""
    min_conv = float(cfg.get("min_conviccao", 55))
    if s["conviccao"] < min_conv:
        return False, f"convicção {s['conviccao']:.0f} < {min_conv:.0f}"

    if s.get("tipo") == "reversao":
        if str(cfg.get("reversao_ativa", "0")) not in ("1", "true", "True"):
            return False, "reversão desativada (não validada no backtest)"
        adx_max = float(cfg.get("adx_max_rev", 22))
        if s.get("adx", 0) > adx_max:            # reversão só faz sentido em range
            return False, f"mercado em tendência (ADX {s.get('adx', 0):.0f} > {adx_max:.0f}) — reversão arriscada"
        if s.get("n_fatores", 0) < 2:
            return False, "confluência fraca"
        return True, "confirmado (reversão)"

    # tendência
    adx_min = float(cfg.get("adx_min", 25))
    min_fatores = int(float(cfg.get("min_fatores", 3)))
    if s.get("adx", 0) < adx_min:                # precisa de TENDÊNCIA
        return False, f"sem tendência (ADX {s.get('adx', 0):.0f} < {adx_min:.0f})"
    if s.get("n_fatores", 0) < min_fatores:
        return False, f"só {s.get('n_fatores', 0)} confirmações (min {min_fatores})"
    if str(cfg.get("exigir_fluxo", "1")) in ("1", "true", "True"):
        bk = mercado.book(ativo)
        if bk:
            fc = bk["fluxo_comprador"]
            if s["direcao"] == "LONG" and fc < 50:
                return False, f"fluxo contra o LONG ({fc:.0f}% comprador)"
            if s["direcao"] == "SHORT" and fc > 50:
                return False, f"fluxo contra o SHORT ({fc:.0f}% comprador)"
            s["motivos"] += f", fluxo {fc:.0f}% taker"
    return True, "confirmado"


def avaliar_saida(pos, cfg=None):
    """Gestor de saída ativa: olha cada posição ABERTA e sugere fechar quando
    (a) já tem lucro razoável E (b) a tendência está revertendo / o fluxo virou.
    Retorna dict com nível (forte/lucro/alvo/risco/ok), ação e ROE%. None se warmup."""
    cfg = cfg or db.get_config()
    ativo, direcao = pos["ativo"], pos["direcao"]
    valor = pos.get("valor_reais") or 1
    roe = (pos.get("pnl") or 0) / valor * 100
    alvo = float(cfg.get("alvo_roe", 5))
    try:
        raw = ex.fetch_ohlcv(ativo, timeframe=cfg.get("timeframe", "15m"), limit=120)
        df = preparar(pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"]))
    except Exception:
        return None
    i = len(df) - 2               # candle FECHADO (evita repaint no aviso de saída)
    rsi_n, rsi_p = df["rsi"].iloc[i], df["rsi"].iloc[i - 1]
    er, el = df["ema_r"].iloc[i], df["ema_l"].iloc[i]
    c, cp = df["close"].iloc[i], df["close"].iloc[i - 1]
    if pd.isna(rsi_n) or pd.isna(er) or pd.isna(el):
        return None

    sinais = []
    if direcao == "LONG":
        if rsi_p >= 68 and rsi_n < rsi_p:
            sinais.append("RSI revertendo do topo")
        if cp >= er and c < er:
            sinais.append("perdeu a EMA20")
        if er < el:
            sinais.append("tendência virou de baixa")
    else:  # SHORT
        if rsi_p <= 32 and rsi_n > rsi_p:
            sinais.append("RSI revertendo do fundo")
        if cp <= er and c > er:
            sinais.append("recuperou a EMA20")
        if er > el:
            sinais.append("tendência virou de alta")
    bk = mercado.book(ativo)
    if bk:
        fc = bk["fluxo_comprador"]
        if direcao == "LONG" and fc < 45:
            sinais.append(f"fluxo virou vendedor ({fc:.0f}%)")
        elif direcao == "SHORT" and fc > 55:
            sinais.append(f"fluxo virou comprador ({fc:.0f}%)")

    motivos = ", ".join(sinais)
    if roe >= alvo and sinais:
        nivel, acao = "forte", f"🟢 REALIZAR JÁ: +{roe:.1f}% e reversão — {motivos}"
    elif roe > 1 and sinais:
        nivel, acao = "lucro", f"💰 Considere fechar: +{roe:.1f}%, reversão começando — {motivos}"
    elif roe >= alvo:
        nivel, acao = "alvo", f"🎯 Bom lucro (+{roe:.1f}%) — preço esticado, fique atento"
    elif sinais and roe < 0:
        nivel, acao = "risco", f"⚠️ Reversão contra a posição ({roe:+.1f}%) — {motivos}"
    else:
        nivel, acao = "ok", None
    return {"posicao_id": pos["id"], "ativo": ativo, "roe": round(roe, 2),
            "nivel": nivel, "acao": acao}


def analise(ativo, tf="15m", limite=200):
    """Candles + séries dos indicadores (EMA20/50, Bollinger) + snapshot (RSI/ADX/etc)
    + leitura em texto do cenário. Pro modo 'analisar sinal' da UI."""
    raw = ex.fetch_ohlcv(ativo, timeframe=tf, limit=limite)
    df = preparar(pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"]))

    def serie(col):
        return [{"time": int(t // 1000), "value": round(float(v), 8)}
                for t, v in zip(df["timestamp"], df[col]) if pd.notna(v)]

    r = df.iloc[-1]
    g = lambda v: round(float(v), 8) if pd.notna(v) else None
    snap = {"preco": g(r["close"]),
            "rsi": round(float(r["rsi"]), 1) if pd.notna(r["rsi"]) else None,
            "adx": round(float(r["adx"]), 1) if pd.notna(r["adx"]) else None,
            "ema20": g(r["ema_r"]), "ema50": g(r["ema_l"]),
            "bb_up": g(r["bb_up"]), "bb_mid": g(r["bb_mid"]), "bb_lo": g(r["bb_lo"])}
    tend = "alta" if (snap["ema20"] or 0) > (snap["ema50"] or 0) else "baixa"
    forte = (snap["adx"] or 0) >= 25
    if pd.notna(r["bb_up"]) and r["close"] >= r["bb_up"]:
        pos = "no TOPO da banda (sobrecomprado)"
    elif pd.notna(r["bb_lo"]) and r["close"] <= r["bb_lo"]:
        pos = "no FUNDO da banda (sobrevendido)"
    else:
        pos = "no meio do range"
    leitura = (f"Tendência de {tend} ({'forte' if forte else 'fraca'} — ADX {snap['adx']}). "
               f"Preço {pos}. RSI {snap['rsi']}.")
    return {"ema20": serie("ema_r"), "ema50": serie("ema_l"), "bb_up": serie("bb_up"),
            "bb_mid": serie("bb_mid"), "bb_lo": serie("bb_lo"), "snapshot": snap, "leitura": leitura}


# Saúde do último scan. Sem isto, uma falha total de rede/exchange fica invisível: o loop
# do worker completa "com sucesso" (o except de cada moeda engolia tudo num print) e o
# /status reporta 0 erros enquanto o bot está cego. Foi exatamente o que aconteceu quando
# a Binance devolveu 451 para o IP da VM.
ultimo_scan = {"ts": None, "total": 0, "ok": 0, "falhas": 0, "ultimo_erro": None}


def scan():
    cfg = db.get_config()
    ativos = [a.strip() for a in cfg["ativos"].split(",") if a.strip()]
    tfs = [t.strip() for t in cfg.get("timeframes", cfg.get("timeframe", "15m")).split(",") if t.strip()]
    ts = str(pd.Timestamp.now())
    ultimo_scan.update(ts=ts, total=0, ok=0, falhas=0)    # zera a cada varredura
    resultados, novos = [], 0
    for a in ativos:
        for tf in tfs:                                   # alargamento: varre cada timeframe
            ultimo_scan["total"] += 1
            try:
                sigs = analisa(a, tf)                    # tendência + reversão
                ultimo_scan["ok"] += 1
            except Exception as e:
                ultimo_scan["falhas"] += 1
                ultimo_scan["ultimo_erro"] = f"{a} {tf}: {type(e).__name__}: {str(e)[:140]}"
                log(f"scan falhou {a} {tf}: {e}", "error")
                continue
            for s in sigs:
                resultados.append(s)
                ok, motivo_rej = confirmado(s, a, cfg)
                if not ok:
                    s["rejeicao"] = motivo_rej
                    continue
                with db.conectar() as con:
                    # dedupe por ativo+tf+tipo: mudou direção, convicção variou >=10, ou é o primeiro
                    ult = con.execute("SELECT direcao,conviccao FROM sinais WHERE ativo=? AND tf=? AND tipo=? "
                                      "ORDER BY id DESC LIMIT 1", (a, tf, s["tipo"])).fetchone()
                    if ult is None or ult["direcao"] != s["direcao"] or abs(s["conviccao"] - ult["conviccao"]) >= 10:
                        con.execute("INSERT INTO sinais(ts,ativo,tf,tipo,direcao,conviccao,motivos,preco,"
                                    "stop_sugerido,status) VALUES(?,?,?,?,?,?,?,?,?,'novo')",
                                    (ts, a, tf, s["tipo"], s["direcao"], s["conviccao"], s["motivos"],
                                     s["preco"], s["stop_sugerido"]))
                        novos += 1
    return resultados, novos


def run(once=False, intervalo=60):
    db.init_db()
    print("ENGINE DE SINAIS | varrendo ao vivo (preço real Binance)\n")
    while True:
        res, novos = scan()
        res.sort(key=lambda x: -x["conviccao"])
        print(f"[{pd.Timestamp.now().strftime('%H:%M:%S')}] {len(res)} ativos varridos | "
              f"{novos} sinais novos gravados")
        for s in res[:8]:
            print(f"   {s['ativo']:<10} {s.get('tf',''):<4} {s.get('tipo','')[:4]:<5} {s['direcao']:<6} "
                  f"conv {s['conviccao']:>3}  {s['motivos']}")
        if once:
            break
        time.sleep(intervalo)


if __name__ == "__main__":
    run(once="--once" in sys.argv)
