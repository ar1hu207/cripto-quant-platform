"""
Sprint 2 - Motor de simulação. Transforma um sinal confirmado em posição simulada
no preço REAL ao vivo, com alavancagem, taxa, funding e LIQUIDAÇÃO. Persiste no banco.
Dinheiro fictício; preço de verdade.
"""
import threading

import ccxt
import pandas as pd

import db
import alertas
from logbot import log

ex = ccxt.binance({"enableRateLimit": True})
ex_fut = ccxt.binanceusdm({"enableRateLimit": True})   # funding (perp)
LIQ_BUFFER = 0.9   # liquida quando a perda chega a ~90% da margem (buffer de manutenção)
_abrir_lock = threading.Lock()   # serializa aberturas concorrentes (worker + API) — evita TOCTOU no teto

# Saúde da marcação, no mesmo padrão do signal_engine.ultimo_scan: sem isto, uma posição
# que deixou de ser marcada (rede caída) fica sem stop/trailing/liquidação em SILÊNCIO —
# o painel segue mostrando o último preço bom como se fosse o de agora.
ultima_marcacao = {"ts": None, "total": 0, "ok": 0, "falhas": 0, "ultimo_erro": None}

# [P2-10] Saúde da MEDIÇÃO de funding. Cumulativo de propósito — ao contrário de
# ultima_marcacao, que zera a cada ciclo: funding é medido uma vez por FECHAMENTO, não a
# cada ciclo. Um contador que zerasse esconderia exatamente o caso que motivou o card (o
# geo-bloqueio 451, em que TODO fechamento falha e o painel seguiria dizendo "0 erros").
funding_medicao = {"medidos": 0, "falhas": 0, "ultimo_erro": None, "ultimo_erro_ts": None}


_cfg_avisado = set()      # (chave, valor) já reclamados — evita um log por poll de 3s


def _cfg_float(cfg, chave, padrao):
    """Lê um float da config sem explodir. DEFESA EM PROFUNDIDADE do [P1-8]: a validação
    de verdade é na entrada (POST /config), mas lixo já gravado no banco antes dela — ou
    por um caminho que a contorne — não pode transformar guarda_risco() em ValueError e
    derrubar /estado e o ciclo do worker. Default do consumidor + aviso é degradação;
    exceção aqui é indisponibilidade total."""
    v = cfg.get(chave, padrao)
    try:
        return float(v)
    except (TypeError, ValueError):
        marca = (chave, str(v))
        if marca not in _cfg_avisado:
            if len(_cfg_avisado) > 200:
                _cfg_avisado.clear()
            _cfg_avisado.add(marca)
            log(f"config inválida: {chave}={v!r} — usando o padrão {padrao}", "error")
        return float(padrao)


def _funding_custo(ativo, aberto_em, fechado_em, direcao, nocional):
    """Funding pago (LONG) / recebido (SHORT) entre abertura e fechamento. Negativo = custo.
    LONG paga funding>0; SHORT recebe. Conta só os settlements no intervalo (8h).

    [P2-10] Devolve **None quando não foi possível MEDIR** — que não é a mesma coisa que
    medir zero. O `except: return 0.0` de antes fundia os dois casos e gravava a falha no
    banco como se fosse número: com o 451 em produção, todo trade saía com funding=0 e
    ninguém tinha como saber. Quem chama decide o que fazer com o None; o que não pode é
    o não-medido virar zero silencioso."""
    try:
        # str(pd.Timestamp.now()) é naive LOCAL; converte p/ UTC ms (= base dos ts da Binance)
        ini = int(pd.Timestamp(aberto_em).to_pydatetime().astimezone().timestamp() * 1000)
        fim = int(pd.Timestamp(fechado_em).to_pydatetime().astimezone().timestamp() * 1000)
        hist = ex_fut.fetch_funding_rate_history(ativo, since=ini, limit=500)
        soma = sum(h["fundingRate"] for h in hist if ini <= h["timestamp"] <= fim)
        d = 1 if direcao == "LONG" else -1
        funding_medicao["medidos"] += 1
        return -d * soma * nocional
    except Exception as e:
        funding_medicao["falhas"] += 1
        funding_medicao["ultimo_erro"] = f"{ativo}: {type(e).__name__}: {str(e)[:140]}"
        funding_medicao["ultimo_erro_ts"] = str(pd.Timestamp.now())
        log(f"funding falhou {ativo}: {type(e).__name__}: {e}", "warning")
        return None


def preco_ao_vivo(ativo):
    return float(ex.fetch_ticker(ativo)["last"])


def _preco_liquidacao(entrada, d, lev):
    """Movimento adverso que zera a margem ~= LIQ_BUFFER/lev. d=1 long, d=-1 short."""
    if not lev:
        return 0.0
    return entrada * (1 - d * (LIQ_BUFFER / lev))


def _liq_antes_do_stop(entrada, stop, alavancagem, d):
    """[P1-12] A liquidação alcança a entrada ANTES do stop? Devolve `(dist_stop, dist_liq)`
    em fração da entrada quando sim, e `None` quando a geometria é sadia — ou quando não há
    o que medir (sinal sem stop, stop na entrada, entrada/alavancagem degeneradas).

    Mede chamando `_preco_liquidacao` em vez de repetir `LIQ_BUFFER/lev`: o modelo de
    liquidação é UM, e uma cópia da fórmula aqui divergiria dele um dia. É o mesmo argumento
    que `autotrader._cap_geometrico` usa para ler o `LIQ_BUFFER` daqui em vez de escrever 0,9.

    `d` entra porque a liquidação é do lado da posição; a DISTÂNCIA é simétrica, então o
    resultado não depende dele — passá-lo é o que mantém a chamada honesta se o modelo
    deixar de ser simétrico um dia."""
    if not entrada or not stop or not alavancagem:
        return None
    dist_stop = abs(entrada - stop)
    dist_liq = abs(entrada - _preco_liquidacao(entrada, d, alavancagem))
    if dist_liq > dist_stop:                          # liquidação atrás do stop: geometria sadia
        return None
    return dist_stop / entrada, dist_liq / entrada


def _pnl(pos, preco_saida):
    if not pos["entrada"] or not pos["alavancagem"]:            # guard divisão por zero
        return 0.0, 0.0, 0.0
    d = 1 if pos["direcao"] == "LONG" else -1
    move = d * (preco_saida / pos["entrada"] - 1)               # retorno do ATIVO a favor
    bruto = pos["valor_reais"] * pos["alavancagem"] * move      # P&L em R$ (alavancado)
    taxa = 2 * _cfg_float(db.get_config(), "taxa_por_lado", 0.0005) * pos["valor_reais"] * pos["alavancagem"]
    pnl = bruto - taxa
    if pnl < -pos["valor_reais"]:                              # não perde mais que a margem
        pnl = -pos["valor_reais"]
    return pnl, taxa, move


def _risco_posicao(valor_reais, alavancagem, entrada, stop):
    """Risco-até-o-stop de uma posição (perda se o stop bater), capado pela margem —
    se a liquidação vem antes do stop, a perda real é a margem inteira."""
    valor_reais = valor_reais or 0
    if not stop or not entrada:                       # sem stop -> perda máxima = a margem
        return valor_reais
    sd = abs(entrada - stop) / entrada
    return min(valor_reais * alavancagem * sd, valor_reais)


def guarda_risco():
    """Proteção de drawdown. (1) Trava diária: bloqueia novos trades se a perda do DIA
    (variação do equity vs INÍCIO DO DIA) bater o limite. (2) Teto de risco aberto: limita
    a soma do risco-até-o-stop das posições abertas. É o 'único alfa garantido'."""
    cfg = db.get_config()
    banca = db.get_banca()
    lim = _cfg_float(cfg, "limite_perda_dia", 0.05)
    lim_ab = _cfg_float(cfg, "risco_aberto_max", 0.10)
    hoje = str(pd.Timestamp.now().date())
    with db.conectar() as con:
        unreal = con.execute("SELECT COALESCE(SUM(pnl),0) FROM posicoes WHERE status='aberta'").fetchone()[0] or 0
        margem = con.execute("SELECT COALESCE(SUM(valor_reais),0) FROM posicoes WHERE status='aberta'").fetchone()[0] or 0
        abertas = [dict(r) for r in con.execute("SELECT valor_reais,alavancagem,entrada,stop "
                                                 "FROM posicoes WHERE status='aberta'")]
        realizado = con.execute("SELECT COALESCE(SUM(pnl_reais),0) FROM trades "
                                "WHERE substr(fechado_em,1,10)=?", (hoje,)).fetchone()[0] or 0
        eqrow = con.execute("SELECT equity_total FROM equity WHERE substr(ts,1,10)=? "
                            "ORDER BY rowid ASC LIMIT 1", (hoje,)).fetchone()
    equity_atual = banca["atual"] + unreal
    equity_inicio = eqrow["equity_total"] if eqrow else equity_atual    # baseline do dia (vs início do dia)
    pnl_dia = equity_atual - equity_inicio
    limite_rs = equity_inicio * lim
    risco_aberto = sum(_risco_posicao(p["valor_reais"], p["alavancagem"], p["entrada"], p["stop"]) for p in abertas)
    teto_ab = equity_inicio * lim_ab if lim_ab > 0 else None            # <=0 => sem teto
    # trava STICKY: uma vez acionada no dia, fica travada até a virada (não destrava se o unreal recupera)
    tripou = pnl_dia <= -limite_rs
    trava_em = cfg.get("trava_dia_em", "")
    if tripou and trava_em != hoje:
        db.set_config("trava_dia_em", hoje)        # marca o dia (idempotente: só na 1a vez)
        trava_em = hoje
    trava_dia = tripou or (trava_em == hoje)
    return {"pnl_dia": round(pnl_dia, 2), "realizado_hoje": round(realizado, 2),
            "limite_rs": round(limite_rs, 2), "limite_pct": round(lim * 100, 1),
            "trava_dia": trava_dia, "margem_aberta": round(margem, 2),
            "n_abertas": len(abertas),
            "risco_aberto_rs": round(risco_aberto, 2),
            "risco_aberto_max_rs": round(teto_ab, 2) if teto_ab is not None else None,
            "risco_aberto_pct": round(lim_ab * 100, 1),
            "teto_aberto": (teto_ab is not None) and (risco_aberto >= teto_ab)}


def abrir(sinal_id, valor_reais, alavancagem):
    if valor_reais <= 0 or alavancagem <= 0:              # valida parâmetros (evita posição degenerada / ÷0)
        raise ValueError("valor de entrada e alavancagem devem ser > 0")
    g = guarda_risco()
    if g["trava_dia"]:                                    # defesa: não abre com trava diária ativa
        raise ValueError("trava diária ativa — limite de perda do dia atingido")
    with db.conectar() as con:                            # leitura do sinal (sem lock de escrita / rede)
        sig = con.execute("SELECT * FROM sinais WHERE id=?", (sinal_id,)).fetchone()
    if not sig:
        raise ValueError("sinal não encontrado")
    if sig["status"] != "novo":                           # pré-check barato: recusa antes de gastar rede.
        raise ValueError(f"sinal já {sig['status']} — não pode virar posição de novo")
    preco = preco_ao_vivo(sig["ativo"])                   # rede FORA do lock
    d = 1 if sig["direcao"] == "LONG" else -1
    # stop recomposto a partir da ENTRADA ao vivo, mantendo a distância relativa do sinal —
    # evita abrir já-em-stop e mantém o risco coerente com o que foi dimensionado.
    stop_rel = (abs(sig["preco"] - sig["stop_sugerido"]) / sig["preco"]
                if sig["preco"] and sig["stop_sugerido"] else 0.0)
    stop = round(preco * (1 - d * stop_rel), 6) if stop_rel else sig["stop_sugerido"]
    # [P1-12] Geometria stop x liquidação, AQUI e não na rota. O cap do [P1-11] mora em
    # `autotrader._alavancagem`, e o `grep` mostrou que só o auto-trader passa por ele: o
    # `POST /confirmar` recebe a alavancagem do CLIENTE e a repassa. Guarda que se contorna
    # com um `curl` não é guarda — a lição da bandeira `PERMITIR_SEM_SENHA` (CLAUDE.md §2).
    # `abrir()` é o único ponto por onde os DOIS fluxos passam, então é aqui que a recusa
    # não tem como ser contornada por rota nova, cliente novo ou script.
    #
    # Levanta ANTES do claim, pela mesma razão que os tetos: recusa por geometria não é
    # defeito do sinal, e consumi-lo tiraria da fila um sinal que volta a ser confirmável
    # assim que a alavancagem pedida couber.
    #
    # Recusa, e não cap silencioso: capar 20x para 14x abriria uma posição que o operador
    # não pediu, com margem dimensionada para outra alavancagem, e sem ninguém saber. O
    # auto-trader capa porque é ele quem escolhe a lev; quem digitou o número merece um não.
    deg = _liq_antes_do_stop(preco, stop, alavancagem, d)
    if deg:
        sd, ld = deg
        raise ValueError(f"geometria degenerada — a {alavancagem:g}x a liquidação fica a "
                         f"{ld * 100:.2f}% da entrada e o stop a {sd * 100:.2f}%: o stop é "
                         f"inalcançável e a perda seria a margem inteira. Com este stop a "
                         f"alavancagem tem de ficar abaixo de {LIQ_BUFFER / sd:.1f}x.")
    cfg = db.get_config()
    exp_max = _cfg_float(cfg, "exposicao_max", 0.5)
    with _abrir_lock:                                     # serializa aberturas (worker + API) — sem TOCTOU no teto
        with db.conectar() as con:
            abertas = [dict(r) for r in con.execute("SELECT valor_reais,alavancagem,entrada,stop "
                                                     "FROM posicoes WHERE status='aberta'")]
            banca_atual = con.execute("SELECT atual FROM banca WHERE id=1").fetchone()["atual"]
            if g["risco_aberto_max_rs"] is not None:      # teto de risco-até-o-stop (recalc dentro do lock)
                risco_ab = sum(_risco_posicao(p["valor_reais"], p["alavancagem"], p["entrada"], p["stop"])
                               for p in abertas)
                r_novo = _risco_posicao(valor_reais, alavancagem, preco, stop)
                if risco_ab + r_novo > g["risco_aberto_max_rs"]:
                    raise ValueError(f"teto de risco aberto — exposição passaria o limite "
                                     f"(R${risco_ab:.2f} + R${r_novo:.2f} > R${g['risco_aberto_max_rs']:.2f})")
            if exp_max > 0:                               # teto de MARGEM (exposição nominal vs banca)
                margem_ab = sum((p["valor_reais"] or 0) for p in abertas)
                if margem_ab + valor_reais > banca_atual * exp_max:
                    raise ValueError(f"teto de margem — exposição (R${margem_ab + valor_reais:.2f}) passaria "
                                     f"{exp_max * 100:.0f}% da banca (R${banca_atual * exp_max:.2f})")
            # CLAIM ATÔMICO do sinal, na mesma transação da inserção e antes dela: quem
            # ganhar o UPDATE (rowcount 1) abre a posição; o segundo pedido vê rowcount 0 e
            # é recusado. O pré-check lá em cima é conveniência — a exclusão mútua é AQUI.
            # Mesmo padrão de rowcount que fechar() usa para não fechar duas vezes.
            if con.execute("UPDATE sinais SET status='confirmado' "
                           "WHERE id=? AND status='novo'", (sinal_id,)).rowcount != 1:
                raise ValueError("sinal já confirmado, pulado ou expirado")
            con.execute("INSERT INTO posicoes(ativo,direcao,entrada,valor_reais,alavancagem,stop,"
                        "preco_atual,pnl,aberto_em,status,conviccao,sinal_id) "
                        "VALUES(?,?,?,?,?,?,?,0,?, 'aberta',?,?)",
                        (sig["ativo"], sig["direcao"], preco, valor_reais, alavancagem,
                         stop, preco, str(pd.Timestamp.now()), sig["conviccao"], sig["id"]))
            pid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    ativo, direcao = sig["ativo"], sig["direcao"]
    log(f"ABRIU #{pid} {direcao} {ativo} @ {preco} | R${valor_reais} {alavancagem}x")
    alertas.enviar(f"🟢 Abriu {direcao} {ativo}\nR$ {valor_reais} @ {alavancagem}x · entrada {preco}")
    return pid


def fechar(pos_id, motivo, preco_saida=None):
    with db.conectar() as con:                                 # lê a posição (transação curta de leitura)
        row = con.execute("SELECT * FROM posicoes WHERE id=? AND status='aberta'", (pos_id,)).fetchone()
    if not row:
        return None
    pos = dict(row)
    if preco_saida is None:
        preco_saida = preco_ao_vivo(pos["ativo"])              # rede FORA do lock de escrita
    pnl, taxa, move = _pnl(pos, preco_saida)                   # liquidação usa o preço de liq (coerente c/ LIQ_BUFFER)
    fechado_em = str(pd.Timestamp.now())
    nocional = pos["valor_reais"] * pos["alavancagem"]
    funding = _funding_custo(pos["ativo"], pos["aberto_em"], fechado_em, pos["direcao"], nocional)
    if funding is not None:
        pnl += funding                                         # funding entra no P&L realizado
        if pnl < -pos["valor_reais"]:                          # re-cap: nunca perde mais que a margem
            pnl = -pos["valor_reais"]
    # funding None = NÃO MEDIDO. O P&L segue sem ele (não dá pra cobrar o que não se mediu),
    # mas a coluna grava NULL, não 0.0: o portão do M2 exige número medido ou AUSENTE
    # declarado. Zero seria a pesquisa lendo "este trade não pagou carry" — que é falso.
    risco_ini = _risco_posicao(pos["valor_reais"], pos["alavancagem"], pos["entrada"], pos["stop"])
    with db.conectar() as con:                                 # transação de escrita curta
        cur = con.execute("UPDATE posicoes SET status='fechada', preco_atual=?, pnl=? "
                          "WHERE id=? AND status='aberta'", (preco_saida, pnl, pos_id))
        if cur.rowcount != 1:                                  # outra thread fechou primeiro — não duplica
            return None
        con.execute("INSERT INTO trades(ativo,direcao,entrada,saida,valor_reais,alavancagem,"
                    "ret_pct,pnl_reais,taxa,motivo_saida,aberto_em,fechado_em,conviccao,sinal_id,"
                    "stop,risco_inicial,funding) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pos["ativo"], pos["direcao"], pos["entrada"], preco_saida, pos["valor_reais"],
                     pos["alavancagem"], move * pos["alavancagem"] * 100, pnl, taxa, motivo,
                     pos["aberto_em"], fechado_em, pos["conviccao"], pos["sinal_id"],
                     pos["stop"], round(risco_ini, 4),
                     round(funding, 4) if funding is not None else None))
        banca = con.execute("SELECT atual FROM banca WHERE id=1").fetchone()["atual"]
        con.execute("UPDATE banca SET atual=? WHERE id=1", (banca + pnl,))
    emoji = "💥" if motivo == "liquidacao" else ("🔴" if pnl < 0 else "🟢")
    f_txt = f"{funding:+.2f}" if funding is not None else "n/d"    # n/d != 0.00, no log também
    log(f"FECHOU #{pos_id} {pos['direcao']} {pos['ativo']} | {motivo} | P&L R$ {pnl:+.2f} (funding {f_txt})")
    alertas.enviar(f"{emoji} Fechou {pos['direcao']} {pos['ativo']} ({motivo})\nP&L: R$ {pnl:+.2f}")
    return pnl


def atualizar():
    """Marca posições abertas no preço ao vivo; fecha em stop/trailing ou liquidação.
    Trailing stop: quando a posição entra em lucro, o stop SOBE atrás do preço (nunca desce) —
    deixa o lucro correr e trava o ganho. Inverte a assimetria: ganha grande, perde pequeno."""
    cfg = db.get_config()
    trail_on = str(cfg.get("trailing_ativo", "1")) in ("1", "true", "True")
    trail_d = _cfg_float(cfg, "trailing_dist", 0.02)
    eventos = []
    with db.conectar() as con:
        abertas = [dict(r) for r in con.execute("SELECT * FROM posicoes WHERE status='aberta'")]
    ultima_marcacao.update(ts=str(pd.Timestamp.now()), total=len(abertas), ok=0, falhas=0,
                           ultimo_erro=None)     # zera a cada ciclo: erro velho não vira alarme eterno
    for pos in abertas:
        # try POR POSIÇÃO, não em volta do for: uma moeda que falha não pode tirar as OUTRAS
        # posições da vigilância de stop/trailing/liquidação, nem derrubar o resto do ciclo.
        try:
            _marcar_uma(pos, trail_on, trail_d, eventos)
            ultima_marcacao["ok"] += 1
        except Exception as e:
            ultima_marcacao["falhas"] += 1
            ultima_marcacao["ultimo_erro"] = f"{pos['ativo']}: {type(e).__name__}: {str(e)[:140]}"
            log(f"atualizar falhou {pos['ativo']}: {e}", "error")
            continue
    return eventos


def _marcar_uma(pos, trail_on, trail_d, eventos):
    """Marca UMA posição no preço ao vivo. Extraído do for de atualizar() para que o
    try/except tenha a granularidade de uma posição — os `continue` viram `return`."""
    preco = preco_ao_vivo(pos["ativo"])
    d = 1 if pos["direcao"] == "LONG" else -1
    # trailing: só sobe o stop (LONG) / só desce (SHORT), e só depois do preço passar +trail_d em lucro
    if trail_on and pos["stop"] and pos["entrada"]:
        if d == 1 and preco >= pos["entrada"] * (1 + trail_d):
            novo = preco * (1 - trail_d)
            if novo > pos["stop"]:
                pos["stop"] = round(novo, 8)
        elif d == -1 and preco <= pos["entrada"] * (1 - trail_d):
            novo = preco * (1 + trail_d)
            if novo < pos["stop"]:
                pos["stop"] = round(novo, 8)
    liq = _preco_liquidacao(pos["entrada"], d, pos["alavancagem"])
    hit_liq = (d == 1 and preco <= liq) or (d == -1 and preco >= liq)
    hit_stop = pos["stop"] and ((d == 1 and preco <= pos["stop"]) or (d == -1 and preco >= pos["stop"]))
    if hit_liq and hit_stop:                                # empate: o mais perto da entrada bate 1o (= backtest)
        if abs(pos["entrada"] - pos["stop"]) <= abs(pos["entrada"] - liq):
            return _fecha_stop(pos, eventos, preco, liq)
        fechar(pos["id"], "liquidacao", liq); eventos.append((pos["id"], "LIQUIDADO")); return
    if hit_liq:
        fechar(pos["id"], "liquidacao", liq); eventos.append((pos["id"], "LIQUIDADO")); return
    if hit_stop:
        return _fecha_stop(pos, eventos, preco, liq)
    pnl, _, _ = _pnl(pos, preco)
    with db.conectar() as con:                              # persiste o stop trailado (sobe entre ciclos)
        con.execute("UPDATE posicoes SET preco_atual=?, pnl=?, stop=? WHERE id=? AND status='aberta'",
                    (preco, pnl, pos["stop"], pos["id"]))


def _fill_stop(stop, preco_atual, liq, d):
    """[P2-18] Preço de execução de um stop-market, e não o preço do gatilho.

    A causa do viés não é o stop estar errado — é confundir GATILHO com FILL. Entre dois
    polls do worker passam 15s, e em cripto o preço rompe o stop e segue: na corretora o
    stop-market dispara no gatilho e executa no book, que num gap está pior. Fechar no
    `stop` grava um preço em que ninguém foi executado, e o erro é sempre para o mesmo
    lado — perda menor e trailing melhor do que o real.

    Por isso o fill é o **pior** entre o stop e o preço observado, e não o stop:
    LONG executa no mais baixo dos dois, SHORT no mais alto.

    **Piso na liquidação, e ele não afrouxa nada.** Passado o preço de liquidação a
    posição não existe mais na corretora — a exchange tomou a margem no caminho, e não
    há fill pior que esse (é o mesmo argumento do card para manter a liquidação como
    está). Sem o piso, o empate stop×liquidação de `_marcar_uma` gravaria execução num
    preço em que a posição já tinha sido liquidada: o paper ficaria pessimista ALÉM do
    real, que é a mesma doença com o sinal trocado. A forma `min(stop, max(...))` é
    deliberada — o piso só encurta o gap, nunca melhora o fill para além do `stop` de
    hoje, então o resultado é sempre ≤ o atual. Aperta, nunca solta.
    """
    if d == 1:                                              # LONG: pior = mais baixo
        return min(stop, max(preco_atual, liq)) if liq else min(stop, preco_atual)
    return max(stop, min(preco_atual, liq)) if liq else max(stop, preco_atual)


def _fecha_stop(pos, eventos, preco_atual, liq):
    """Fecha por stop, distinguindo no journal: 'trailing' (stop já em lucro) vs 'stop' (perda).

    [P2-18] O sufixo `-gap` marca o fechamento em que o fill saiu pior que o gatilho. Não é
    enfeite de log: `motivo_saida` é coluna de `trades`, então medir depois quanto o gap
    custou vira uma query, sem instrumentação nova. Sem a marca, o gap fica indistinguível
    de um stop que executou no preço."""
    d = 1 if pos["direcao"] == "LONG" else -1
    em_lucro = (d == 1 and pos["stop"] >= pos["entrada"]) or (d == -1 and pos["stop"] <= pos["entrada"])
    motivo = "trailing" if em_lucro else "stop"
    fill = _fill_stop(pos["stop"], preco_atual, liq, d)
    if fill != pos["stop"]:
        motivo += "-gap"
    fechar(pos["id"], motivo, fill)
    eventos.append((pos["id"], motivo))


# ---------------------------------------------------------------------------
def _prova_funding():
    """Prova de regressão do [P2-10]: sinal do funding (LONG paga × SHORT recebe), janela
    de settlements, e — o que o card existe para consertar — falha de medição que NÃO vira
    zero. Sem rede e sem banco de produção.

        python simulador.py

    Mora dentro do módulo, e não num arquivo próprio, por uma razão de processo, não de
    desenho: a onda 1 do M2 fechou o território T-EXEC em simulador.py + validacao.py, e
    criar prova_funding.py reprovaria no portão de fronteira (§9.4/P2) mesmo com o código
    certo. Quando o P2-6 (pytest) abrir, isto é o ponto de partida para migrar."""
    global ex_fut
    import os, tempfile
    falhas = []

    def check(nome, cond, detalhe=""):
        print(("  PASSA  " if cond else "  FALHA  ") + nome + ("" if cond else f"  <- {detalhe}"))
        if not cond:
            falhas.append(nome)

    def ms(txt):   # mesma conversão naive-local -> UTC ms que _funding_custo faz
        return int(pd.Timestamp(txt).to_pydatetime().astimezone().timestamp() * 1000)

    class ExFake:
        def __init__(self, hist):
            self.hist = hist

        def fetch_funding_rate_history(self, ativo, since=None, limit=None):
            return self.hist

    class ExJanela:
        """1 settlement logo depois do início da janela — independe da data de hoje."""
        def fetch_funding_rate_history(self, ativo, since=None, limit=None):
            return [{"timestamp": since + 1, "fundingRate": 0.0001}]

    class ExQuebrado:
        def fetch_funding_rate_history(self, *a, **k):
            raise RuntimeError("HTTP 451 — servico indisponivel por restricao geografica")

    original, db_original = ex_fut, db.DB
    ab, fe, nocional = "2026-08-22 00:00:00", "2026-08-22 23:59:59", 1000.0
    try:
        # --- sinal e janela: 3 settlements DENTRO da janela + 1 fora (não pode contar)
        ex_fut = ExFake([{"timestamp": ms("2026-08-22 04:00:00"), "fundingRate": 0.0001},
                         {"timestamp": ms("2026-08-22 12:00:00"), "fundingRate": 0.0001},
                         {"timestamp": ms("2026-08-22 20:00:00"), "fundingRate": 0.0001},
                         {"timestamp": ms("2026-08-23 04:00:00"), "fundingRate": 0.0001}])
        f_long = _funding_custo("BTC/USDT", ab, fe, "LONG", nocional)
        f_short = _funding_custo("BTC/USDT", ab, fe, "SHORT", nocional)
        check("LONG paga funding>0 (custo, negativo)", f_long is not None and f_long < 0, repr(f_long))
        check("SHORT recebe funding>0 (crédito, positivo)", f_short is not None and f_short > 0, repr(f_short))
        check("LONG e SHORT são simétricos", abs(f_long + f_short) < 1e-12, f"{f_long} vs {f_short}")
        check("conta só os settlements DENTRO da janela", abs(f_long - (-0.30)) < 1e-9,
              f"{f_long} — com o 4o settlement (fora da janela) daria -0.40")

        # --- medir zero continua sendo zero: history vazio é MEDIÇÃO, não falha
        ex_fut = ExFake([])
        antes = dict(funding_medicao)
        z = _funding_custo("BTC/USDT", ab, fe, "LONG", nocional)
        check("history vazio = medição de zero, devolve 0.0", z == 0.0, repr(z))
        check("medição de zero não conta como falha", funding_medicao["falhas"] == antes["falhas"])

        # --- o card: falha de rede NÃO É ZERO
        ex_fut = ExQuebrado()
        antes = dict(funding_medicao)
        r = _funding_custo("BTC/USDT", ab, fe, "LONG", nocional)
        check("falha de medição devolve None, não 0.0", r is None, repr(r))
        check("falha incrementa o contador de falhas",
              funding_medicao["falhas"] == antes["falhas"] + 1, str(funding_medicao))
        check("falha registra o motivo (não só o fato)",
              "451" in (funding_medicao["ultimo_erro"] or ""), repr(funding_medicao["ultimo_erro"]))

        # --- persistência: é aqui que o zero falso entrava no histórico de pesquisa
        db.DB = os.path.join(tempfile.mkdtemp(), "prova_funding.db")   # nunca o banco real
        db.init_db()

        def _fecha_com(ex, direcao="LONG"):
            global ex_fut
            with db.conectar() as c:
                c.execute("INSERT INTO posicoes(ativo,direcao,entrada,valor_reais,alavancagem,stop,"
                          "preco_atual,pnl,aberto_em,status) VALUES('BTC/USDT',?,100,50,2,95,100,0,?,'aberta')",
                          (direcao, str(pd.Timestamp.now() - pd.Timedelta(hours=9))))
                pid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
            ex_fut = ex
            fechar(pid, "prova", 101.0)                                # preço explícito: sem rede
            with db.conectar() as c:
                return c.execute("SELECT funding FROM trades WHERE id=(SELECT MAX(id) FROM trades)").fetchone()[0]

        nao_medido = _fecha_com(ExQuebrado())
        check("funding não medido grava NULL (ausente, não zero)", nao_medido is None, repr(nao_medido))
        medido = _fecha_com(ExJanela())      # 1 settlement × 0,0001 × (50×2) = 0,01 pago
        check("funding medido grava o valor com o sinal certo (LONG paga)",
              medido is not None and abs(medido - (-0.01)) < 1e-9, repr(medido))
    finally:
        ex_fut, db.DB = original, db_original      # nada do teste sobrevive à função
    print(f"\n  {len(falhas)} falharam")
    return 1 if falhas else 0


if __name__ == "__main__":
    import sys
    try:                                   # console do Windows em cp1252 mutila o acento
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(_prova_funding())
