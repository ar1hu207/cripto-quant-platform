"""
Sprint 1 - Engine de Sinais. Varre as criptos AO VIVO (preço real Binance),
pontua a convicção de cada oportunidade (trend + ADX + rompimento + RSI + volume)
e grava os sinais no banco. Esses sinais alimentam a fila de "confirmar trade".

Rodar:  python signal_engine.py               (loop)
        python signal_engine.py --once        (uma varredura)
        python signal_engine.py --desfechos   ([Q-4] marca desfecho hipotético agora)
        python signal_engine.py --relatorio   ([Q-4] portão de fluxo: passou x rejeitado)
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
    # instante em que esse preço foi impresso = abertura do candle seguinte (o em formação).
    # [Q-4] ancora o desfecho hipotético aqui, e não na hora do scan: num sinal de 1h o scan
    # pode acontecer 59 min depois do fechamento, e o contrafactual começaria de um preço morto.
    vela_ms = int(df["timestamp"].iloc[i + 1])
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
                        adx=p["adx"], n_fatores=p["n_fatores"], vela_ms=vela_ms))
    return out


# [P2-9] Marca do sinal que passou SEM a checagem de fluxo. O portao so roda se `book()`
# devolveu dados; quando nao devolve, a garantia deixa de existir e isso precisa ficar
# ESCRITO no sinal — e a unica coisa que o auto-trader consegue ler depois (ele nao ve o
# ciclo do scan). Constante em vez de literal solto porque `autotrader.py` a le.
MOTIVO_FLUXO_ND = "fluxo n/d"


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
            s["fluxo_comprador"] = fc        # [Q-4] medido: vale pros DOIS grupos, não só pro rejeitado
            if s["direcao"] == "LONG" and fc < 50:
                s["rejeitado_por"] = "fluxo"
                return False, f"fluxo contra o LONG ({fc:.0f}% comprador)"
            if s["direcao"] == "SHORT" and fc > 50:
                s["rejeitado_por"] = "fluxo"
                return False, f"fluxo contra o SHORT ({fc:.0f}% comprador)"
            s["motivos"] += f", fluxo {fc:.0f}% taker"
        else:
            # [P2-9] book indisponivel (rede, exchange fora, book vazio) = portao PULADO.
            # Decisao registrada na §4b do plano: opcao B — passa ANOTADO e medido, em vez de
            # rejeitar (fail-closed secaria a fila inteira numa instabilidade prolongada).
            # A degradacao vira dado em dois lugares: no sinal (motivos, que o auto-trader le)
            # e no contador do ciclo (ultimo_scan, que o /status publica).
            s["fluxo_indisponivel"] = True
            s["motivos"] += f", {MOTIVO_FLUXO_ND}"
            ultimo_scan["fluxo_indisponivel"] += 1
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
ultimo_scan = {"ts": None, "total": 0, "ok": 0, "falhas": 0, "ultimo_erro": None,
               # [P2-9] quantos sinais do ciclo passaram sem a checagem de fluxo
               # (book indisponivel). Zero e a operacao normal; qualquer numero aqui
               # e portao anunciado que nao rodou. Aparece sozinho no /status: o
               # endpoint devolve este dicionario inteiro sob a chave "scan".
               "fluxo_indisponivel": 0,
               # [P2-15] `ultimo_erro` e do scan CORRENTE (zerado a cada varredura);
               # `ultimo_erro_historico` nunca e zerado. Sao a mesma string com dois
               # significados, e o bug era um campo so servindo aos dois: depois de uma
               # varredura 100% verde o /status seguia exibindo o erro de horas atras como
               # se fosse de agora. Separar e o que deixa limpar um sem perder o outro.
               "ultimo_erro_historico": None}


REJEITADO_FLUXO = "rejeitado_fluxo"      # [Q-4] status fora da fila: nenhuma consulta de
                                         # pendentes/auto-trader o lê (todas filtram status='novo')
HORIZONTE_H = 24                         # janela do desfecho hipotético
HORIZONTE_MS = HORIZONTE_H * 3600 * 1000
DESFECHOS_POR_SCAN = 6                   # teto de fetch extra por varredura (o scan já faz ~72)

# [P1-9] Janela de vida de um sinal, em VELAS do proprio timeframe. Um sinal de 5m e um de 4h
# nao envelhecem no mesmo relogio: fixar "60 min" trataria os dois igual. 4 velas e exatamente
# o horizonte que o front ja chama de "expirou — sinal antigo, reavalie" (statusEntrada, em
# web/index.html), entao o banco passa a concordar com o que o painel mostra em vez de
# contradize-lo. Nao vira config: acrescentar chave exigiria `db.CONFIG_PADRAO` e o catalogo do
# POST /config, que sao territorio de outro agente nesta onda.
JANELA_VELAS = 4
TF_MIN = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
          "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720, "1d": 1440}


def janela_min(tf):
    """Janela do sinal em minutos. TF desconhecido cai no 15m (o `timeframe` padrao)."""
    return JANELA_VELAS * TF_MIN.get((tf or "").strip(), 15)


def _repetido(con, s, ativo, tf, status, ts):
    """Dedupe por ativo+tf+tipo DENTRO da própria linhagem de status, e DENTRO da janela.

    A fila e o log de rejeição não se enxergam: cada um compara com o último da SUA espécie.
    Sem essa separação, uma rejeição gravada viraria o "último sinal" de ativo+tf+tipo e
    mudaria quando a fila aceita um sinal novo — efeito colateral proibido pelo card ([Q-4]
    exige zero impacto na fila) e colisão direta com o dedupe do [P1-9].

    [P1-9] `ts >= corte` é o que separa "spam" de "condição que ainda está lá". O comparador é
    string porque `ts` é `str(pd.Timestamp)` (naive, São Paulo — CLAUDE.md §1) e o formato
    ISO ordena lexicograficamente; converter a coluna aqui só desligaria índice futuro.
    """
    lado = "= ?" if status == REJEITADO_FLUXO else "<> ?"
    corte = str(pd.Timestamp(ts) - pd.Timedelta(minutes=janela_min(tf)))
    ult = con.execute("SELECT direcao,conviccao FROM sinais WHERE ativo=? AND tf=? AND tipo=? "
                      f"AND IFNULL(status,'novo') {lado} AND ts >= ? ORDER BY id DESC LIMIT 1",
                      (ativo, tf, s["tipo"], REJEITADO_FLUXO, corte)).fetchone()
    # mudou de direção, convicção variou >=10, ou é o primeiro -> não é repetido
    return not (ult is None or ult["direcao"] != s["direcao"]
                or abs(s["conviccao"] - ult["conviccao"]) >= 10)


def _gravar(con, ts, s, ativo, tf, status, rejeicao):
    """INSERT único pros dois grupos — a mesma linha, o mesmo dedupe, só o status muda.
    É o que permite comparar os dois depois sem discutir se a amostragem foi diferente."""
    con.execute("INSERT INTO sinais(ts,ativo,tf,tipo,direcao,conviccao,motivos,preco,stop_sugerido,"
                "status,vela_ms,fluxo_comprador,rejeicao) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ts, ativo, tf, s["tipo"], s["direcao"], s["conviccao"], s["motivos"],
                 s["preco"], s["stop_sugerido"], status, s.get("vela_ms"),
                 s.get("fluxo_comprador"), rejeicao))


def _desfecho(sinal, velas):
    """Desfecho HIPOTÉTICO de um sinal contra candle de 5m, na janela de 24h.

    Contrafactual declarado: stop = a distância do `stop_sugerido` (3xATR), alvo = a MESMA
    distância espelhada (1R). 1R simétrico porque sob passeio aleatório o acerto é 50% — é o
    nulo certo pra comparar dois grupos. Empate na mesma vela conta como STOP (5m não ordena
    o que aconteceu dentro dela; o viés fica no lado pessimista, igual pros dois grupos).
    Não é P&L: sem fill, sem taxa, sem funding, sem alavancagem.
    """
    ini = sinal["vela_ms"]
    velas = [v for v in velas if ini <= v[0] <= ini + HORIZONTE_MS]
    if len(velas) < 12:                     # menos de 1h de mercado: não dá pra marcar nada
        return None
    d = 1 if sinal["direcao"] == "LONG" else -1
    entrada = float(sinal["preco"])
    dist = abs(entrada - float(sinal["stop_sugerido"]))
    if entrada <= 0 or dist <= 0:
        return None
    stop, alvo = entrada - d * dist, entrada + d * dist
    saida = "aberto"
    for t, o, h, l, c, v in velas:
        bateu_stop = (l <= stop) if d == 1 else (h >= stop)
        bateu_alvo = (h >= alvo) if d == 1 else (l <= alvo)
        if bateu_stop:
            saida = "stop"
            break
        if bateu_alvo:
            saida = "alvo"
            break

    def fechamento(horas):
        ate = ini + horas * 3600 * 1000
        antes = [v for v in velas if v[0] <= ate]
        return round(float(antes[-1][4]), 8) if antes else None

    return {"desfecho": saida, "preco_1h": fechamento(1),
            "preco_4h": fechamento(4), "preco_24h": fechamento(24)}


def marcar_desfechos(limite=DESFECHOS_POR_SCAN, agora_ms=None):
    """[Q-4] Job leve do worker: marca o desfecho hipotético dos sinais já VENCIDOS.

    Roda sobre os DOIS grupos — quem passou e quem o fluxo rejeitou — com a mesma régua.
    Medir só o rejeitado não responderia nada: o grupo que passou virou trade com política de
    saída própria (auto-saida/trailing), e comparar isso com um contrafactual seria comparar
    duas coisas diferentes. Só pega sinal que já completou 24h de mercado: aí uma única
    chamada de candles resolve stop, alvo e os três horizontes de uma vez.
    """
    agora = agora_ms if agora_ms is not None else int(time.time() * 1000)
    with db.conectar() as con:
        pend = [dict(r) for r in con.execute(
            "SELECT id,ativo,direcao,preco,stop_sugerido,vela_ms FROM sinais "
            "WHERE desfecho IS NULL AND vela_ms IS NOT NULL AND vela_ms <= ? "
            "ORDER BY vela_ms LIMIT ?", (agora - HORIZONTE_MS, limite))]
    feitos = 0
    for r in pend:
        try:                                    # 289 velas de 5m = 24h05 a partir do sinal
            velas = ex.fetch_ohlcv(r["ativo"], timeframe="5m", since=int(r["vela_ms"]), limit=289)
        except Exception as e:
            log(f"desfecho falhou {r['ativo']} #{r['id']}: {type(e).__name__}: {e}", "error")
            continue
        d = _desfecho(r, velas)
        if not d:
            continue
        with db.conectar() as con:
            con.execute("UPDATE sinais SET desfecho=?,desfecho_ts=?,preco_1h=?,preco_4h=?,preco_24h=? "
                        "WHERE id=?", (d["desfecho"], str(pd.Timestamp.now()), d["preco_1h"],
                                       d["preco_4h"], d["preco_24h"], r["id"]))
        feitos += 1
    return feitos


def expirar_sinais(agora=None):
    """[P1-9] Fecha a outra ponta da janela: sinal 'novo' mais velho que ela vira 'expirado'.

    Sem isto, a janela do dedupe deixaria a fila DUPLICADA — o candidato novo entra, e o
    pendente de ontem continua lá, com preço e stop de ontem, disputando o mesmo ativo. O
    painel já desenhava "expirou — reavalie", mas só na tela: no banco o registro seguia
    'novo' para sempre, e `/estado.pendentes` e o pool do auto-trader são consultas ao banco,
    não à tela.

    Roda por TF porque a janela é por TF. `status='novo'` é o único alvo: 'confirmado',
    'pulado' e 'rejeitado_fluxo' são histórico, e reescrevê-los apagaria o que o [Q-4] mede.
    """
    agora = pd.Timestamp(agora) if agora is not None else pd.Timestamp.now()
    n = 0
    with db.conectar() as con:
        tfs = [r[0] for r in con.execute(
            "SELECT DISTINCT IFNULL(tf,'') FROM sinais WHERE status='novo'")]
        for tf in tfs:
            corte = str(agora - pd.Timedelta(minutes=janela_min(tf)))
            n += con.execute("UPDATE sinais SET status='expirado' WHERE status='novo' "
                             "AND IFNULL(tf,'')=? AND ts < ?", (tf, corte)).rowcount
    return n


def scan():
    cfg = db.get_config()
    ativos = [a.strip() for a in cfg["ativos"].split(",") if a.strip()]
    tfs = [t.strip() for t in cfg.get("timeframes", cfg.get("timeframe", "15m")).split(",") if t.strip()]
    ts = str(pd.Timestamp.now())
    # [P2-15] `ultimo_erro=None` entra aqui: o scan zera ts/total/ok/falhas mas nao zerava
    # o erro, e por isso o painel de saude nao distinguia problema atual de memoria.
    ultimo_scan.update(ts=ts, total=0, ok=0, falhas=0, fluxo_indisponivel=0,
                       ultimo_erro=None)                                   # zera a cada varredura
    try:
        # [P1-9] limpeza ANTES da varredura: o que for gravado agora nasce dentro da janela, e
        # o auto-trader (que roda logo depois, no mesmo ciclo do worker) já lê a fila limpa.
        # Job local e barato, mas segue a regra do `marcar_desfechos`: nunca derruba o scan.
        expirados = expirar_sinais(ts)
        if expirados:
            log(f"[P1-9] {expirados} sinal(is) 'novo' expirados (fora da janela)")
    except Exception as e:
        log(f"expirar_sinais falhou: {e}", "error")
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
                ultimo_scan["ultimo_erro_historico"] = f"{ts} {ultimo_scan['ultimo_erro']}"
                log(f"scan falhou {a} {tf}: {e}", "error")
                continue
            for s in sigs:
                resultados.append(s)
                ok, motivo_rej = confirmado(s, a, cfg)
                if not ok:
                    s["rejeicao"] = motivo_rej
                    if s.get("rejeitado_por") == "fluxo":
                        # [Q-4] a rejeição por fluxo é o único dado que valida o portão, e ela
                        # só existe agora: não há book/taker histórico pra reconstruir depois.
                        with db.conectar() as con:
                            if not _repetido(con, s, a, tf, REJEITADO_FLUXO, ts):
                                _gravar(con, ts, s, a, tf, REJEITADO_FLUXO, motivo_rej)
                    continue
                with db.conectar() as con:
                    if not _repetido(con, s, a, tf, "novo", ts):
                        _gravar(con, ts, s, a, tf, "novo", None)
                        novos += 1
    try:
        marcar_desfechos()          # job leve do worker: nunca pode derrubar a varredura
    except Exception as e:
        log(f"marcar_desfechos falhou: {e}", "error")
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


def imprimir_relatorio_fluxo():
    """[Q-4] Imprime a comparação passou x rejeitado pelo portão de fluxo.
    Fica aqui como comando pra não depender de endpoint: `api.py` é território de outro
    agente nesta onda, e o número da pesquisa tem que ser obtenível sem subir a API."""
    r = db.relatorio_fluxo()
    print("PORTAO DE FLUXO — validacao prospectiva [Q-4]\n")
    print(f"{'grupo':<12}{'n':>5}{'alvo':>6}{'stop':>6}{'aberto':>8}{'win%':>8}"
          f"{'ret1h%':>9}{'ret4h%':>9}{'ret24h%':>9}{'fluxo%':>9}")
    for nome in ("passou", "rejeitado"):
        g = r[nome]
        f = lambda v: "-" if v is None else f"{v}"
        print(f"{nome:<12}{g['n']:>5}{g['alvo']:>6}{g['stop']:>6}{g['aberto']:>8}"
              f"{f(g['win']):>8}{f(g['ret_1h']):>9}{f(g['ret_4h']):>9}"
              f"{f(g['ret_24h']):>9}{f(g['fluxo_medio']):>9}")
    d = r["delta_win"]
    print(f"\ndelta win (passou - rejeitado): {'-' if d is None else f'{d:+.1f} p.p.'}"
          f"   z={r['z']}  p={r['p']}")
    print(f"veredito: {r['veredito']}")
    print(f"nota: {r['nota']}")
    return r


if __name__ == "__main__":
    if "--relatorio" in sys.argv:
        db.init_db()
        imprimir_relatorio_fluxo()
    elif "--desfechos" in sys.argv:
        db.init_db()
        print(f"{marcar_desfechos(limite=200)} desfechos marcados")
    else:
        run(once="--once" in sys.argv)
