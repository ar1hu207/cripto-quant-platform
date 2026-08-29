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
    # [EX-1] Entrada e saida sao cobradas SEPARADAS. A saida e sempre `taxa_por_lado` (taker):
    # stop e trailing sao ordem a mercado por natureza -- quando o preco vira contra, nao da para
    # pendurar limite e torcer. A ENTRADA e a que pode ter sido maker, e quanto ela custou esta
    # gravado NA POSICAO (`taxa_entrada`), nao na config: as duas convivem enquanto posicoes
    # abertas a mercado ainda estao vivas, e cobrar a taxa de hoje sobre a entrada de ontem
    # inventaria lucro que nao houve. NULL = entrou a mercado.
    t_saida = _cfg_float(db.get_config(), "taxa_por_lado", 0.0005)
    try:
        t_entrada = pos["taxa_entrada"]
    except (KeyError, IndexError):
        t_entrada = None
    t_entrada = t_saida if t_entrada is None else float(t_entrada)
    taxa = (t_entrada + t_saida) * pos["valor_reais"] * pos["alavancagem"]
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
    # [F-1] O risco-até-o-stop DESTA abertura, medido uma vez, aqui, sobre `preco` e `stop` —
    # os dois valores que a posição vai nascer tendo. O mesmo número serve ao teto agregado e
    # à coluna `risco_abertura`: são a mesma grandeza, e computá-la duas vezes seria abrir a
    # porta para elas divergirem no dia em que `_risco_posicao` mudar.
    risco_ab = _risco_posicao(valor_reais, alavancagem, preco, stop)
    with _abrir_lock:                                     # serializa aberturas (worker + API) — sem TOCTOU no teto
        with db.conectar() as con:
            # [EX-1] Ordem pendente conta nos tetos como se ja fosse posicao. APERTA a guarda, e
            # de proposito: doze ordens pendentes que enchem no mesmo minuto sao doze posicoes, e
            # um teto que so olha o que ja abriu autoriza uma exposicao que ele proprio proibe.
            # Enquanto `exec_modo=mercado` a consulta devolve vazio e nada muda.
            abertas = ([dict(r) for r in con.execute("SELECT valor_reais,alavancagem,entrada,stop "
                                                     "FROM posicoes WHERE status='aberta'")]
                       + _pendentes(con))
            banca_atual = con.execute("SELECT atual FROM banca WHERE id=1").fetchone()["atual"]
            if g["risco_aberto_max_rs"] is not None:      # teto de risco-até-o-stop (recalc dentro do lock)
                risco_ja = sum(_risco_posicao(p["valor_reais"], p["alavancagem"], p["entrada"], p["stop"])
                               for p in abertas)
                if risco_ja + risco_ab > g["risco_aberto_max_rs"]:
                    raise ValueError(f"teto de risco aberto — exposição passaria o limite "
                                     f"(R${risco_ja:.2f} + R${risco_ab:.2f} > R${g['risco_aberto_max_rs']:.2f})")
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
                        "preco_atual,pnl,aberto_em,status,conviccao,sinal_id,"
                        "stop_abertura,risco_abertura) "
                        "VALUES(?,?,?,?,?,?,?,0,?, 'aberta',?,?,?,?)",
                        (sig["ativo"], sig["direcao"], preco, valor_reais, alavancagem,
                         stop, preco, str(pd.Timestamp.now()), sig["conviccao"], sig["id"],
                         stop, round(risco_ab, 4)))
            pid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    ativo, direcao = sig["ativo"], sig["direcao"]
    log(f"ABRIU #{pid} {direcao} {ativo} @ {preco} | R${valor_reais} {alavancagem}x")
    alertas.enviar(f"🟢 Abriu {direcao} {ativo}\nR$ {valor_reais} @ {alavancagem}x · entrada {preco}")
    return pid


def _pendentes(con):
    """[EX-1] Ordens pendentes no formato de posicao, para os tetos as somarem sem saber a
    diferenca. `preco_limite` faz as vezes de `entrada` porque e onde a posicao vai nascer."""
    return [{"valor_reais": r["valor_reais"], "alavancagem": r["alavancagem"],
             "entrada": r["preco_limite"], "stop": r["stop"]}
            for r in con.execute("SELECT valor_reais,alavancagem,preco_limite,stop "
                                 "FROM ordens WHERE status='pendente'")]


def colocar_ordem(sinal_id, valor_reais, alavancagem):
    """[EX-1] O caminho post-only: o sinal vira uma ordem que DESCANSA, nao uma posicao.

    Roda as MESMAS guardas do `abrir()`, na mesma ordem, com uma diferenca: a entrada avaliada
    e o `preco_limite`, nao o preco ao vivo -- e o preco onde a posicao vai nascer se nascer.
    Avaliar geometria e risco sobre o preco de agora seria dimensionar sobre um preco que, por
    construcao, nao e o que vai ser pago.

    O sinal e reivindicado AQUI, na criacao da ordem, e nao no preenchimento. Sem isso o mesmo
    sinal viraria duas ordens, e o claim atomico do [P1-6] deixaria de valer justamente onde
    passou a existir uma janela de espera. Ordem que expira NAO devolve o sinal: e o que o
    [CX-1] mediu, e o [CX-3] mostrou que a alternativa -- esperar e mandar a mercado -- nao
    paga (Sharpe 0,960 contra 0,955 do taker de hoje).
    """
    if valor_reais <= 0 or alavancagem <= 0:
        raise ValueError("valor de entrada e alavancagem devem ser > 0")
    g = guarda_risco()
    if g["trava_dia"]:
        raise ValueError("trava diaria ativa - limite de perda do dia atingido")
    with db.conectar() as con:
        sig = con.execute("SELECT * FROM sinais WHERE id=?", (sinal_id,)).fetchone()
    if not sig:
        raise ValueError("sinal nao encontrado")
    if sig["status"] != "novo":
        raise ValueError("sinal ja %s - nao pode virar ordem de novo" % sig["status"])
    cfg = db.get_config()
    off = _cfg_float(cfg, "exec_maker_off", 0.0010)
    ttl = _cfg_float(cfg, "exec_ordem_ttl_s", 3600.0)
    preco = preco_ao_vivo(sig["ativo"])                        # rede FORA do lock
    d = 1 if sig["direcao"] == "LONG" else -1
    limite = round(preco * (1 - d * off), 8)                   # descansa do NOSSO lado do livro
    stop_rel = (abs(sig["preco"] - sig["stop_sugerido"]) / sig["preco"]
                if sig["preco"] and sig["stop_sugerido"] else 0.0)
    stop = round(limite * (1 - d * stop_rel), 6) if stop_rel else sig["stop_sugerido"]
    deg = _liq_antes_do_stop(limite, stop, alavancagem, d)     # [P1-12], sobre o preco do fill
    if deg:
        sd, ld = deg
        raise ValueError("geometria degenerada - a %gx a liquidacao fica a %.2f%% da entrada e o "
                         "stop a %.2f%%" % (alavancagem, ld * 100, sd * 100))
    exp_max = _cfg_float(cfg, "exposicao_max", 0.5)
    agora = pd.Timestamp.now()
    with _abrir_lock:
        with db.conectar() as con:
            abertas = ([dict(r) for r in con.execute("SELECT valor_reais,alavancagem,entrada,stop "
                                                     "FROM posicoes WHERE status='aberta'")]
                       + _pendentes(con))
            banca_atual = con.execute("SELECT atual FROM banca WHERE id=1").fetchone()["atual"]
            if g["risco_aberto_max_rs"] is not None:
                risco_ab = sum(_risco_posicao(x["valor_reais"], x["alavancagem"], x["entrada"], x["stop"])
                               for x in abertas)
                r_novo = _risco_posicao(valor_reais, alavancagem, limite, stop)
                if risco_ab + r_novo > g["risco_aberto_max_rs"]:
                    raise ValueError("teto de risco aberto - exposicao passaria o limite "
                                     "(R$%.2f + R$%.2f > R$%.2f)"
                                     % (risco_ab, r_novo, g["risco_aberto_max_rs"]))
            if exp_max > 0:
                margem_ab = sum((x["valor_reais"] or 0) for x in abertas)
                if margem_ab + valor_reais > banca_atual * exp_max:
                    raise ValueError("teto de margem - exposicao (R$%.2f) passaria %.0f%% da banca "
                                     "(R$%.2f)" % (margem_ab + valor_reais, exp_max * 100,
                                                   banca_atual * exp_max))
            if con.execute("UPDATE sinais SET status='confirmado' "
                           "WHERE id=? AND status='novo'", (sinal_id,)).rowcount != 1:
                raise ValueError("sinal ja confirmado, pulado ou expirado")
            con.execute("INSERT INTO ordens(sinal_id,ativo,direcao,preco_ref,preco_limite,"
                        "valor_reais,alavancagem,stop,conviccao,criada_em,expira_em,status) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,'pendente')",
                        (sig["id"], sig["ativo"], sig["direcao"], preco, limite, valor_reais,
                         alavancagem, stop, sig["conviccao"], str(agora),
                         str(agora + pd.Timedelta(seconds=ttl))))
            oid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    log("ORDEM #%s %s %s limite %s (ref %s) | R$%s %sx - expira em %.0fs"
        % (oid, sig["direcao"], sig["ativo"], limite, preco, valor_reais, alavancagem, ttl))
    return oid


def _encheu(direcao, limite, preco):
    """A ordem post-only encheu? LONG so enche em preco <= limite; SHORT em preco >= limite."""
    return preco <= limite if direcao == "LONG" else preco >= limite


def processar_ordens():
    """[EX-1] Um ciclo do worker sobre as ordens pendentes: enche, ou expira.

    O try/except e POR ORDEM, nunca em volta do `for` -- e a licao do [P1-1], e aqui ela morde
    igual: uma moeda cuja cotacao falha nao pode impedir as outras ordens de encher nem de
    expirar.
    """
    with db.conectar() as con:
        pend = [dict(r) for r in con.execute("SELECT * FROM ordens WHERE status='pendente'")]
    if not pend:
        return {"vistas": 0, "preenchidas": 0, "expiradas": 0, "falhas": 0}
    taxa_maker = _cfg_float(db.get_config(), "taxa_maker", 0.0002)
    agora = pd.Timestamp.now()
    res = {"vistas": len(pend), "preenchidas": 0, "expiradas": 0, "falhas": 0}
    for o in pend:
        try:
            if o["expira_em"] and agora >= pd.Timestamp(o["expira_em"]):
                _resolver(o["id"], "expirada", "ttl")          # o sinal NAO volta: ver colocar_ordem
                res["expiradas"] += 1
                continue
            preco = preco_ao_vivo(o["ativo"])
            if not _encheu(o["direcao"], o["preco_limite"], preco):
                continue
            # A trava diaria e re-checada NO FILL, e nao so na criacao: a ordem espera, e o dia
            # pode ter estourado o limite de perda enquanto ela esperava. Deixar encher aqui
            # seria a trava diaria valendo so para quem entra a mercado.
            if guarda_risco()["trava_dia"]:
                _resolver(o["id"], "cancelada", "trava diaria ativa no preenchimento")
                res["expiradas"] += 1
                continue
            pid = _abrir_da_ordem(o, taxa_maker)
            res["preenchidas"] += 1
            log("ORDEM #%s PREENCHIDA -> posicao #%s @ %s (preco %s) - taxa de entrada %.3f%%"
                % (o["id"], pid, o["preco_limite"], preco, taxa_maker * 100))
        except Exception as e:
            res["falhas"] += 1
            log("ordem #%s falhou: %s" % (o["id"], e))
    return res


def _resolver(oid, status, motivo):
    with db.conectar() as con:
        con.execute("UPDATE ordens SET status=?, motivo=?, resolvida_em=? "
                    "WHERE id=? AND status='pendente'",
                    (status, motivo, str(pd.Timestamp.now()), oid))


def _abrir_da_ordem(o, taxa_maker):
    """Materializa a posicao de uma ordem que encheu. A entrada e o `preco_limite`, nao o preco
    de agora: post-only significa que o preco foi NOSSO. Sem slippage, de proposito -- quem poe
    o preco nao paga travessia de spread. O rowcount no UPDATE da ordem e o que impede duas
    posicoes nascerem da mesma ordem se dois ciclos se cruzarem."""
    with _abrir_lock:
        with db.conectar() as con:
            if con.execute("UPDATE ordens SET status='preenchida', resolvida_em=? "
                           "WHERE id=? AND status='pendente'",
                           (str(pd.Timestamp.now()), o["id"])).rowcount != 1:
                raise ValueError("ordem ja resolvida")
            # [F-1] As mesmas duas âncoras do `abrir()`, sobre o preço que ESTA posição pagou
            # — `preco_limite`, não o preço de agora. Dimensionar a âncora sobre o preço de
            # mercado no instante do fill gravaria um risco que a posição não correu, e o
            # caminho post-only é justamente o que separa os dois preços no tempo.
            risco_ab = _risco_posicao(o["valor_reais"], o["alavancagem"],
                                      o["preco_limite"], o["stop"])
            con.execute("INSERT INTO posicoes(ativo,direcao,entrada,valor_reais,alavancagem,stop,"
                        "preco_atual,pnl,aberto_em,status,conviccao,sinal_id,taxa_entrada,"
                        "stop_abertura,risco_abertura) "
                        "VALUES(?,?,?,?,?,?,?,0,?,'aberta',?,?,?,?,?)",
                        (o["ativo"], o["direcao"], o["preco_limite"], o["valor_reais"],
                         o["alavancagem"], o["stop"], o["preco_limite"],
                         str(pd.Timestamp.now()), o["conviccao"], o["sinal_id"], taxa_maker,
                         o["stop"], round(risco_ab, 4)))
            pid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
            con.execute("UPDATE ordens SET posicao_id=? WHERE id=?", (pid, o["id"]))
    alertas.enviar("Ordem preenchida %s %s - R$ %s @ %sx - entrada %s"
                   % (o["direcao"], o["ativo"], o["valor_reais"], o["alavancagem"],
                      o["preco_limite"]))
    return pid


def executar(sinal_id, valor_reais, alavancagem):
    """[EX-1] PONTO UNICO de entrada: despacha pelo `exec_modo` da config.

    Devolve `("posicao", id)` ou `("ordem", id)`. O `abrir()` continua existindo intacto e
    continua sendo o caminho a mercado -- nao virou wrapper nem mudou de assinatura, porque e
    ele que as provas do M1 e a suite exercitam, e trocar o significado dele por baixo seria
    mexer no risco pela porta dos fundos.
    """
    if str(db.get_config().get("exec_modo", "mercado")) == "post_only":
        return "ordem", colocar_ordem(sinal_id, valor_reais, alavancagem)
    return "posicao", abrir(sinal_id, valor_reais, alavancagem)


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
    # [F-1] `risco_inicial` é LEGADO e fica exatamente como estava: lê `pos["stop"]`, que o
    # trailing reescreveu, e por isso grava "risco no stop da SAÍDA" sob um nome que promete
    # "da entrada". Não se conserta o significado dele porque as 62 linhas já em produção
    # significam o que significam — reescrever a coluna coalharia duas séries com o mesmo
    # nome, que é pior que o defeito ([P2-40]). A versão-sintoma que NÃO se fez aqui era
    # arredondar este número para o teto matemático: o valor pararia de ofender a vista
    # (R$177,55 contra um teto de R$49,86) e continuaria medindo a coisa errada.
    #
    # `risco_abertura` é o conserto, e ele é uma CÓPIA — o número foi decidido no `abrir()` /
    # `_abrir_da_ordem()` e aqui não se recalcula nada. Recalcular é o defeito: toda conta
    # feita neste ponto tem `pos["stop"]` como única geometria disponível, e `pos["stop"]` se
    # move. NULL quando a posição nasceu antes da coluna existir — ausência de medição não é
    # zero, e não se deriva de `risco_inicial` para "ficar completo".
    risco_ini = _risco_posicao(pos["valor_reais"], pos["alavancagem"], pos["entrada"], pos["stop"])
    risco_ab = pos.get("risco_abertura")
    with db.conectar() as con:                                 # transação de escrita curta
        cur = con.execute("UPDATE posicoes SET status='fechada', preco_atual=?, pnl=? "
                          "WHERE id=? AND status='aberta'", (preco_saida, pnl, pos_id))
        if cur.rowcount != 1:                                  # outra thread fechou primeiro — não duplica
            return None
        # [P2-40] DUAS colunas de retorno, e a distinção é o conserto.
        #
        # `ret_pct` sempre foi `move * lev * 100` — o retorno BRUTO, sem taxa e sem funding —
        # enquanto `pnl_reais`, no mesmo INSERT, tem os dois. Quem lesse "ret_pct" como "o
        # retorno do trade" lia um número que ninguém recebeu, e o erro tinha sinal FIXO:
        # sempre para o lado bom. É a mesma doença que o [P2-18] curou no preço de fill
        # (gatilho ≠ execução), sobrevivendo numa outra coluna.
        #
        # A correção NÃO é trocar o significado de `ret_pct`: as 47 linhas já gravadas em
        # produção significam exatamente "ROE bruto", e reescrevê-las transformaria a série
        # em duas séries coladas com o mesmo nome — pior que o defeito. Sobrecarregar a
        # coluna também não: é o oposto do que o [P2-10] fez ao dar coluna PRÓPRIA ao
        # funding em vez de embuti-lo, justamente para a medição ficar explícita.
        #
        # Então `ret_pct` fica sendo o bruto, com o nome do que é, e `ret_pct_liq` passa a
        # gravar o que o operador recebe: `pnl / margem`. Vem do `pnl` já calculado, e não
        # de uma segunda fórmula — duas contas para a mesma grandeza divergem um dia. E é
        # exatamente derivável para o histórico (`pnl_reais / valor_reais`), então o
        # backfill do `prova_p2_40` não inventa dado: recupera o que já estava lá.
        ret_liq = (pnl / pos["valor_reais"] * 100) if pos["valor_reais"] else None
        con.execute("INSERT INTO trades(ativo,direcao,entrada,saida,valor_reais,alavancagem,"
                    "ret_pct,ret_pct_liq,pnl_reais,taxa,motivo_saida,aberto_em,fechado_em,"
                    "conviccao,sinal_id,stop,risco_inicial,funding,risco_abertura) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (pos["ativo"], pos["direcao"], pos["entrada"], preco_saida, pos["valor_reais"],
                     pos["alavancagem"], move * pos["alavancagem"] * 100,
                     round(ret_liq, 6) if ret_liq is not None else None,
                     pnl, taxa, motivo,
                     pos["aberto_em"], fechado_em, pos["conviccao"], pos["sinal_id"],
                     pos["stop"], round(risco_ini, 4),
                     round(funding, 4) if funding is not None else None,
                     round(risco_ab, 4) if risco_ab is not None else None))
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
    trail = _trailing_cfg(cfg)
    eventos = []
    with db.conectar() as con:
        abertas = [dict(r) for r in con.execute("SELECT * FROM posicoes WHERE status='aberta'")]
    ultima_marcacao.update(ts=str(pd.Timestamp.now()), total=len(abertas), ok=0, falhas=0,
                           ultimo_erro=None)     # zera a cada ciclo: erro velho não vira alarme eterno
    for pos in abertas:
        # try POR POSIÇÃO, não em volta do for: uma moeda que falha não pode tirar as OUTRAS
        # posições da vigilância de stop/trailing/liquidação, nem derrubar o resto do ciclo.
        try:
            _marcar_uma(pos, trail, eventos)
            ultima_marcacao["ok"] += 1
        except Exception as e:
            ultima_marcacao["falhas"] += 1
            ultima_marcacao["ultimo_erro"] = f"{pos['ativo']}: {type(e).__name__}: {str(e)[:140]}"
            log(f"atualizar falhou {pos['ativo']}: {e}", "error")
            continue
    return eventos


def _trailing_cfg(cfg):
    """[N-13] A política de trailing da config, já resolvida em números.

    Lida uma vez por ciclo em `atualizar()`, e não por posição: são leituras de config a menos,
    e — o que importa mais — todas as posições de um mesmo ciclo passam a ser marcadas sob a
    MESMA política. Reler a config dentro do `for` deixaria metade das posições sob uma regra e
    metade sob outra no ciclo em que alguém mexesse no painel."""
    return {"on": str(cfg.get("trailing_ativo", "1")) in ("1", "true", "True"),
            "unidade": str(cfg.get("trailing_unidade", "R")).strip(),
            "arma_r": _cfg_float(cfg, "trailing_arma_r", 1.0),
            "dist_r": _cfg_float(cfg, "trailing_dist_r", 1.0),
            "dist_preco": _cfg_float(cfg, "trailing_dist", 0.02)}


def _r_abertura(pos):
    """[N-13] 1R em PREÇO: a distância entrada→stop **da abertura**, lida de `stop_abertura`.

    Sai da coluna imutável e nunca de `pos["stop"]`. Medir o R a partir do stop vigente seria o
    defeito do [F-1] renascendo dentro do próprio conserto: o trailing move o stop, o R
    encolheria a cada ciclo, e o gatilho "1R" passaria a significar um lucro menor a cada
    passada — um trailing que se persegue e trava o vencedor cedo demais.

    0.0 = não há R mensurável (posição aberta antes da coluna existir, ou sinal sem stop). Quem
    chama trata isso como ausência, não como zero."""
    try:
        sa = pos["stop_abertura"]
    except (KeyError, IndexError):                # posição montada à mão, sem SELECT *
        return 0.0
    if not sa or not pos["entrada"]:
        return 0.0
    return abs(float(pos["entrada"]) - float(sa))


def _trailing_novo_stop(pos, preco, d, trail):
    """[N-13] O stop que o trailing propõe, ou None enquanto ele não armou.

    Duas unidades, e a escolha é da config (`trailing_unidade`):

    **"R"** põe gatilho e distância na MESMA unidade do stop — 1R = `_r_abertura`. É o conserto
    do F-19: em espaço-preço o gatilho vira ROE quando multiplicado pela alavancagem (2% de
    preço são 4% de ROE a 2x e 40% a 20x), então o trailing desarmava justamente onde a aposta
    era maior; e em unidade de risco os mesmos 2% valem 3R num stop curto e meio R num stop
    largo. Em R o gatilho significa a mesma coisa em todo trade, qualquer que seja o ativo, a
    volatilidade ou a alavancagem — que é a razão de o `be_em_R` da pesquisa já ser medido assim
    (`pesquisa/backtest_plataforma`).

    **"preco"** é o comportamento histórico, preservado expressão por expressão
    (`entrada*(1±td)` e `preco*(1∓td)`, não uma reescrita algebricamente equivalente — igualdade
    em ponto flutuante não sobrevive a "equivalente"). Ele também é o caminho das posições SEM
    `stop_abertura`: elas nasceram sob esta política e continuam sob ela. Escolher um R para
    elas exigiria adivinhar o stop de entrada a partir do stop de agora, que é exatamente a
    adivinhação que este card veio remover."""
    if not (trail["on"] and pos["stop"] and pos["entrada"]):
        return None
    r = _r_abertura(pos)
    if trail["unidade"] == "R" and r:
        if d == 1 and preco >= pos["entrada"] + trail["arma_r"] * r:
            return preco - trail["dist_r"] * r
        if d == -1 and preco <= pos["entrada"] - trail["arma_r"] * r:
            return preco + trail["dist_r"] * r
        return None
    td = trail["dist_preco"]
    if d == 1 and preco >= pos["entrada"] * (1 + td):
        return preco * (1 - td)
    if d == -1 and preco <= pos["entrada"] * (1 - td):
        return preco * (1 + td)
    return None


def _marcar_uma(pos, trail, eventos):
    """Marca UMA posição no preço ao vivo. Extraído do for de atualizar() para que o
    try/except tenha a granularidade de uma posição — os `continue` viram `return`."""
    preco = preco_ao_vivo(pos["ativo"])
    d = 1 if pos["direcao"] == "LONG" else -1
    # trailing: só sobe o stop (LONG) / só desce (SHORT). O `novo` só é aceito se andar a favor —
    # a catraca não muda de unidade, e um stop que anda para trás é um stop que o mercado escolhe.
    novo = _trailing_novo_stop(pos, preco, d, trail)
    if novo is not None and ((d == 1 and novo > pos["stop"]) or (d == -1 and novo < pos["stop"])):
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
