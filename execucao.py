"""[LIVE-3] A conta que opera numa corretora de verdade (Binance Demo ou real).

O `simulador` continua sendo o LIVRO: é ele quem valida, aplica os tetos, reivindica o sinal e
grava posição, trade e banca. Este módulo é o que troca "o processo olha o preço e decide" por
"a corretora executa e o livro copia". Só entra em cena quando a config `corretora` não é
`papel`; nas contas de papel nenhuma linha daqui roda (`real()` devolve False e os três pontos
de despacho do `simulador` seguem pelo caminho de sempre).

**As quatro regras deste arquivo** (as três do `PLANO-LIVE-BINANCE` §2 e a que a Fase 1 mediu):

1. **A corretora é a verdade; o banco é a cópia.** Todo ciclo começa por `reconciliar()`, e sem
   uma reconciliação recente a conta não abre nada (`_bloqueio_entrada`). O livro nunca decide
   que uma posição fechou olhando o preço: ele LÊ que ela fechou, com o negócio que a fechou.
2. **Nunca existe posição sem stop na corretora.** A entrada que descansa (post-only) sai com
   o stop junto, `reduceOnly` com quantidade, que a Binance aceita antes do preenchimento; a
   que ficar descansando sem ele ganha o stop no ciclo seguinte, ou é cancelada. A entrada a
   mercado também leva o stop ANTES de sair, e sem ele não sai. Posição que perde o stop ganha
   outro na hora; se ele não entrar em duas tentativas, as duas na mesma chamada, a posição é
   desfeita a mercado (`_garantir_stop`). O trailing move o stop NA corretora e só então grava
   o número no banco.
3. **Toda ordem tem um id nosso, derivado do id do livro** (`_coid`), com um prefixo próprio
   deste banco. Falha de rede no envio vira uma busca pelo id, nunca um reenvio, e um id
   nunca é usado duas vezes (`_seq`).
4. **Antes de ir à rede, a intenção já está gravada.** Toda entrada, inclusive a mercado, nasce
   como uma linha `pendente` em `ordens`: ela conta nos tetos, reivindica o sinal e leva o id.
   Se o processo cair entre o envio e a resposta, o ciclo seguinte acha a ordem pelo id.

O que é aproximação, declarado: a alavancagem é truncada para inteiro (a Binance só aceita
inteiro); o trailing só reenvia o stop quando ele anda `corretora_trailing_passo_r`; de noite
o trailing é o nativo da Binance, em % e não em R; um preenchimento parcial cancela o resto da
ordem em vez de esperar o prazo; o alvo cujo tamanho não chega a um lote fica sem ordem e essa
parte segue no trailing.

Unidade: nesta conta `valor_reais`, `pnl_reais` e a banca estão em USDT. Os nomes das colunas
são os do papel porque o livro é o mesmo.
"""
import json
import os
import secrets
import threading
import time

import pandas as pd

import alertas
import alvos
import corretora as C
import db
import push
import simulador
from logbot import log

_lock = threading.RLock()            # uma operação na corretora por vez (worker e rotas da API)
_cache = {"chave": None, "obj": None}
_teste = {"obj": None}               # os testes injetam a corretora falsa aqui (`usar`)
_escrita = {}                        # ativo -> monotonic da nossa última escrita (regra 4 da Fase 1)
_falta_fill = {}                     # posição -> ciclos seguidos sem achar o negócio que a fechou
_sem_stop = {}                       # posição -> tentativas seguidas de repor o stop
_fora_do_livro = set()               # (ativo, direção) já avisadas: posição lá que o dry_run não adota
_ordens_de_fora = set()              # ids já avisados: ordem aberta lá que não é deste livro

FOLGA_LEITURA_S = 5.0                # não reconcilia um ativo em que acabamos de escrever
RECONCILIACAO_MAX_S = 120.0          # sem reconciliar há mais que isto, a conta não abre
ESPERA_FILL_CICLOS = 20              # ~5 min esperando o negócio aparecer antes de fechar às cegas
ORDEM_SUMIDA_S = 60.0                # ordem que a corretora não conhece depois disto: não chegou

# Saúde da conta real, publicada no `/status`. Cumulativa na vida do processo, como
# `simulador.funding_medicao`: divergência que aconteceu uma vez às 3h tem de estar lá às 9h.
saude = {"modo": "papel", "reconciliado_em": None, "reconciliacoes": 0, "falhas": 0,
         "ultimo_erro": None, "divergencias": 0, "ultima_divergencia": None,
         "adotadas": 0, "orfas_canceladas": 0, "stops_repostos": 0, "fechadas_fora": 0,
         "ordens_de_fora": 0, "saldo": None, "noite": False}
_reconciliado = {"mono": None}


# ------------------------------------------------------------------------------ o modo

def modo(cfg=None):
    cfg = db.get_config() if cfg is None else cfg
    return str(cfg.get("corretora") or "papel").strip().lower()


def real(cfg=None):
    """Esta conta executa numa corretora? É a pergunta dos pontos de despacho do `simulador`."""
    return modo(cfg) != "papel"


def habilitada():
    """Só a instância que sobe com `CORRETORA_HABILITADA=1` pode sair do papel. A variável vai
    no `ExecStart` da unit da conta R, e não no `.env` que as quatro contas leem. É a segunda
    tranca: a primeira é a chave da Binance morar num arquivo que só aquela unit carrega
    (`deploy/cripto-bot-r.service`). Com as duas, um `DB_PATH` errado ou um backup restaurado
    na pasta errada não faz uma conta de papel mandar ordem."""
    return os.environ.get("CORRETORA_HABILITADA", "").strip() == "1"


def usar(obj):
    """Troca a corretora por um dublê (testes). `None` volta ao normal."""
    _teste["obj"] = obj
    _cache.update(chave=None, obj=None)


def obter(cfg=None):
    """A corretora da config, construída uma vez e reusada. Reconstrói se o modo, o teto ou o
    `dry_run` mudarem: são os três que o adapter fixa ao nascer."""
    if _teste["obj"] is not None:
        return _teste["obj"]
    cfg = db.get_config() if cfg is None else cfg
    m = modo(cfg)
    if m == "papel":
        raise C.ErroCorretora("conta de papel: não há corretora")
    if not habilitada():
        raise C.ErroCorretora("esta instância não pode operar em corretora "
                              "(falta CORRETORA_HABILITADA=1 no ambiente)")
    chave = (m, str(cfg.get("corretora_dry_run", "0")), str(cfg.get("corretora_nocional_max", "")))
    with _lock:
        if _cache["chave"] != chave:
            _cache.update(chave=chave, obj=C.obter(cfg))
            saude["modo"] = m
        return _cache["obj"]


_ns_cache = {}                       # caminho do banco -> prefixo (o banco não troca de prefixo)


def _ns(cfg=None):
    """O prefixo dos ids de ordem DESTE banco. Num banco novo os ids do livro recomeçam em 1, e
    a conta da corretora ainda lembra das ordens `e1`, `e2` do banco anterior: sem o prefixo, o
    envio seria recusado como duplicado e a busca devolveria a ordem ANTIGA como se fosse a
    nova. Gerado uma vez, gravado na config, fora do catálogo (ninguém edita)."""
    ns = _ns_cache.get(db.DB)
    if ns:
        return ns
    # Lido do BANCO, nunca de uma config que quem chama leu antes: uma cópia velha (sem o
    # prefixo) faria gerar outro, e as ordens do mesmo banco sairiam com dois prefixos.
    ns = str(db.get_config().get("corretora_ns") or "").strip()
    if not ns:
        ns = secrets.token_hex(3)
        db.set_config("corretora_ns", ns, "execucao._ns")
    _ns_cache[db.DB] = ns
    return ns


def _coid(letra, ident, seq=None, cfg=None):
    """`ap<ns><letra><id>[n<seq>]`. Letras: e = entrada, p = stop pré-colocado da ordem,
    s = stop da posição, t = alvo, x = fechamento, r = trailing da noite."""
    return f"ap{_ns(cfg)}{letra}{ident}" + (f"n{seq}" if seq is not None else "")


def _nosso(coid, cfg=None):
    return bool(coid) and str(coid).startswith(f"ap{_ns(cfg)}")


def _d(direcao):
    return 1 if direcao == "LONG" else -1


def _seq(pos):
    """O próximo número de ordem da posição, gravado ANTES de ir à rede. Um id nunca é usado
    duas vezes: se o envio ficou incerto, a tentativa seguinte sai com outro id, e a ordem da
    tentativa anterior (se chegou) é uma órfã com o nosso prefixo, que a reconciliação cancela.
    Reusar o id deixaria a busca devolver a ordem velha como se fosse a resposta da nova."""
    seq = int(pos.get("stop_seq") or 0) + 1
    with db.conectar() as con:
        con.execute("UPDATE posicoes SET stop_seq=? WHERE id=?", (seq, pos["id"]))
    pos["stop_seq"] = seq
    return seq


def _lote(c, ativo, qty):
    """`qty` no lote da corretora. É para o que SOBRA de uma subtração (`0.062 - 0.021` é
    `0.040999999999999995`): guardado assim no livro, o stop e o fechamento seguintes sairiam
    um lote menores que a posição."""
    try:
        return c.arredondar(ativo, qty, reduz=True)[0]
    except Exception:
        return qty


def _dry(c):
    return bool(getattr(c, "dry_run", False))


def _marcar_escrita(ativo):
    _escrita[ativo] = time.monotonic()


def _escrita_recente(ativo):
    t = _escrita.get(ativo)
    return t is not None and time.monotonic() - t < FOLGA_LEITURA_S


def _avisar(texto, nivel="error"):
    """Aviso que o dono precisa VER: log, Telegram e push. Os dois últimos são no-op sem
    configuração, e nenhum levanta: aviso que falha não pode derrubar o que estava protegendo."""
    log(texto, nivel)
    alertas.enviar(texto)
    try:
        push.avisar("Conta em corretora ⚠️", texto[:180], "#apollo", tipo="trava")
    except Exception as e:
        log(f"push do aviso falhou: {e}", "warning")


_avisado = {}                      # chave do aviso -> monotonic do último envio
AVISO_REPETE_S = 1800.0


def _avisar_uma_vez(chave, texto, nivel="error"):
    """`_avisar` no máximo uma vez por `AVISO_REPETE_S` por chave: o que falha a cada ciclo de
    7 s viraria 250 mensagens por hora, e a que importa se perderia entre elas."""
    agora = time.monotonic()
    if agora - _avisado.get(chave, -1e18) < AVISO_REPETE_S:
        log(texto, nivel)
        return
    _avisado[chave] = agora
    _avisar(texto, nivel)


def _divergencia(texto):
    saude["divergencias"] += 1
    saude["ultima_divergencia"] = f"{pd.Timestamp.now()} {texto}"
    _avisar(f"⚠️ corretora x livro: {texto}")


# ------------------------------------------------------------------------------ guardas

def noite(cfg, agora=None):
    """Estamos na janela da noite? `noite_inicio` > `noite_fim` é a janela que atravessa a
    meia-noite (19:00 a 07:00), que é o caso normal."""
    if str(cfg.get("noite_ativo", "0")) not in ("1", "true", "True"):
        return False
    agora = pd.Timestamp.now() if agora is None else pd.Timestamp(agora)
    try:
        ini = pd.Timestamp(f"2000-01-01 {cfg.get('noite_inicio', '19:00')}").time()
        fim = pd.Timestamp(f"2000-01-01 {cfg.get('noite_fim', '07:00')}").time()
    except (ValueError, TypeError):
        return False
    t = agora.time()
    return (ini <= t or t < fim) if ini > fim else (ini <= t < fim)


def guarda_total(cfg=None):
    """Teto de perda TOTAL: `perda_total_max` USDT contados da banca inicial do livro.

    Sticky, como a trava diária, mas sem virada de dia: batido, grava `trava_total_em` com a
    hora e o teto vigente, e a conta não abre mais. Só solta quando o dono SOBE o teto pelo
    `POST /config` (o que fica na auditoria). Equity que se recupera sozinho não solta: a
    regra existe para parar e chamar o dono, não para pausar."""
    cfg = db.get_config() if cfg is None else cfg
    teto = simulador._cfg_float(cfg, "perda_total_max", 0.0)
    marca = str(cfg.get("trava_total_em") or "")
    if teto <= 0:
        return {"teto": None, "perda": None, "travada": False}
    with db.conectar() as con:
        con.execute("BEGIN")
        b = dict(con.execute("SELECT inicial, atual FROM banca WHERE id=1").fetchone())
        unreal = con.execute("SELECT COALESCE(SUM(pnl),0) FROM posicoes "
                             "WHERE status='aberta'").fetchone()[0] or 0
    perda = b["inicial"] - (b["atual"] + unreal)
    travada = False
    if marca:
        try:
            teto_da_marca = float(marca.split("|")[1])
        except (IndexError, ValueError):
            teto_da_marca = teto
        if teto > teto_da_marca + 1e-9:               # o dono subiu o teto: solta
            db.set_config("trava_total_em", "", "execucao.guarda_total")
        else:
            travada = True
    if not travada and perda >= teto:
        # `repr`, e não `:g`: com 6 algarismos um teto de 33.3333333 seria gravado 33.3333, e na
        # chamada seguinte o próprio teto pareceria "maior que o da marca" e soltaria a trava.
        db.set_config("trava_total_em", f"{pd.Timestamp.now()}|{teto!r}", "execucao.guarda_total")
        db.set_config("auto_trade", "0", "execucao.guarda_total")
        _avisar(f"🛑 TETO DE PERDA TOTAL: perda de {perda:.2f} USDT passou o teto de {teto:.2f}. "
                "Auto-trader desligado; a conta não abre até o teto ser revisto.")
        travada = True
    return {"teto": teto, "perda": round(perda, 2), "travada": travada}


def _bloqueio_entrada(cfg):
    """O motivo de a conta real não abrir AGORA, ou None. Mensagens com "trava" e "teto" de
    propósito: é por essas palavras que o auto-trader encerra o ciclo em vez de tentar o
    próximo sinal (`autotrader.auto_executar`)."""
    m = _reconciliado["mono"]
    if m is None or time.monotonic() - m > RECONCILIACAO_MAX_S:
        return "trava da corretora — sem reconciliação recente, a conta não abre às cegas"
    if guarda_total(cfg)["travada"]:
        return "teto de perda total atingido — a conta não abre até o teto ser revisto"
    if noite(cfg):
        return "trava da noite — fora da janela de operação, a conta não abre"
    return None


# ------------------------------------------------------------------------------ entrada

def executar(sinal_id, valor_reais, alavancagem, exige_auto=False):
    """O `simulador.executar` da conta real. Devolve `("posicao", id)` ou `("ordem", id)`.

    As guardas são as do papel, na mesma ordem e pelas mesmas funções (`guarda_risco`,
    `_liq_antes_do_stop`, `_checar_tetos`, claim atômico); o que muda é o número sobre o qual
    elas rodam: a quantidade JÁ arredondada para o lote da corretora, e a alavancagem já
    inteira. Arredondar depois do teto seria o teto autorizando o que não mediu."""
    simulador._validar_entrada(valor_reais, alavancagem)
    cfg = db.get_config()
    c = obter(cfg)
    _ns()                 # o prefixo existe ANTES da transação do claim (gravá-lo abre outra conexão)
    lev = float(max(1, int(float(alavancagem))))          # a Binance só aceita inteiro: trunca
    g = simulador.guarda_risco()
    if g["trava_dia"]:
        raise ValueError("trava diária ativa — limite de perda do dia atingido")
    bloqueio = _bloqueio_entrada(cfg)
    if bloqueio:
        raise ValueError(bloqueio)
    with db.conectar() as con:
        sig = con.execute("SELECT * FROM sinais WHERE id=?", (sinal_id,)).fetchone()
    if not sig:
        raise ValueError("sinal não encontrado")
    if sig["status"] != "novo":
        raise ValueError(f"sinal já {sig['status']} — não pode virar ordem de novo")
    ativo, direcao = sig["ativo"], sig["direcao"]
    d = _d(direcao)
    stop_rel = (abs(sig["preco"] - sig["stop_sugerido"]) / sig["preco"]
                if sig["preco"] and sig["stop_sugerido"] else 0.0)
    if not stop_rel:                                       # regra 2: sem stop não há posição
        raise ValueError("sinal sem stop — a conta real não abre posição sem stop")
    # Recusa que depende só do sinal e do lote da corretora se repetiria igual a cada ciclo até o
    # sinal expirar (o auto-trader o reapresenta, e ele segue 'novo'). A memória curta evita ir à
    # rede para ouvir o mesmo não; a chave inclui o tamanho pedido, então outro tamanho é medido.
    memo = _recusas.get((sinal_id, round(float(valor_reais), 2), lev))
    if memo and time.monotonic() - memo[0] < RECUSA_MEMO_S:
        raise ValueError(memo[1])
    post_only = str(cfg.get("exec_modo", "mercado")) == "post_only"
    try:
        marca = float(c.marks([ativo])[ativo])
        ref = marca * (1 - d * simulador._cfg_float(cfg, "exec_maker_off", 0.0010)) if post_only else marca
        qty, preco = c.arredondar(ativo, float(valor_reais) * lev / ref, ref if post_only else None)
        entrada = preco if post_only else marca
        stop = c.preco_valido(ativo, entrada * (1 - d * stop_rel))
    except C.AbaixoDoMinimo as e:
        raise _recusa(sinal_id, valor_reais, lev, f"abaixo do mínimo da corretora — {e}")
    valor = qty * entrada / lev                            # a margem que VAI ser usada
    # Sem a palavra "teto" de propósito: o auto-trader encerra o ciclo quando lê "teto" (não há
    # mais espaço na conta), e este limite é de UMA ordem. Com "teto" aqui, um sinal grande
    # demais travaria todas as outras entradas até ele expirar.
    limite_ordem = simulador._cfg_float(cfg, "corretora_nocional_max", C.NOCIONAL_MAX_PADRAO)
    if qty * entrada > limite_ordem:
        raise _recusa(sinal_id, valor_reais, lev,
                      f"ordem grande demais — nocional de {qty * entrada:.2f} USDT passa o "
                      f"limite por ordem ({limite_ordem:.2f}, `corretora_nocional_max`)")
    deg = simulador._liq_antes_do_stop(entrada, stop, lev, d)
    if deg:
        sd, ld = deg
        raise ValueError(f"geometria degenerada — a {lev:g}x a liquidação fica a {ld * 100:.2f}% "
                         f"da entrada e o stop a {sd * 100:.2f}%")
    exp_max = simulador._cfg_float(cfg, "exposicao_max", 0.5)
    ttl = simulador._cfg_float(cfg, "exec_ordem_ttl_s", 3600.0)
    risco = simulador._risco_posicao(valor, lev, entrada, stop)
    agora = pd.Timestamp.now()
    with simulador._abrir_lock:
        with db.conectar() as con:
            # A conta opera em modo one-way: um ativo tem UMA posição. Uma segunda entrada no
            # mesmo ativo somaria à primeira (mesmo lado) ou a reduziria (lado oposto), e o livro
            # teria duas linhas para uma posição só. Antes do claim: não consome o sinal.
            if con.execute("SELECT 1 FROM posicoes WHERE ativo=? AND status='aberta' UNION ALL "
                           "SELECT 1 FROM ordens WHERE ativo=? AND status='pendente' LIMIT 1",
                           (ativo, ativo)).fetchone():
                raise ValueError(f"já existe posição ou ordem em {ativo} — a conta em corretora "
                                 "tem uma posição por ativo")
            simulador._checar_tetos(con, g, valor, risco, exp_max, exige_auto)
            if con.execute("UPDATE sinais SET status='confirmado' "
                           "WHERE id=? AND status='novo'", (sinal_id,)).rowcount != 1:
                raise ValueError("sinal já confirmado, pulado ou expirado")
            con.execute("INSERT INTO ordens(sinal_id,ativo,direcao,preco_ref,preco_limite,"
                        "valor_reais,alavancagem,stop,conviccao,criada_em,expira_em,status,"
                        "corretora,tipo,qty,stop_rel) VALUES(?,?,?,?,?,?,?,?,?,?,?,'pendente',?,?,?,?)",
                        (sig["id"], ativo, direcao, marca, entrada, valor, lev, stop,
                         sig["conviccao"], str(agora), str(agora + pd.Timedelta(seconds=ttl)),
                         c.nome, "limite" if post_only else "mercado", qty, stop_rel))
            oid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
            con.execute("UPDATE ordens SET client_oid=?, stop_coid=? WHERE id=?",
                        (_coid("e", oid, cfg=cfg), _coid("p", oid, cfg=cfg), oid))
    with _lock:
        return _enviar_entrada(c, _ordem(oid))


RECUSA_MEMO_S = 300.0
_recusas = {}                        # (sinal, valor, lev) -> (monotonic, mensagem)


def _recusa(sinal_id, valor_reais, lev, msg):
    if len(_recusas) > 500:          # não cresce para sempre: sinal velho não volta
        _recusas.clear()
    _recusas[(sinal_id, round(float(valor_reais), 2), lev)] = (time.monotonic(), msg)
    return ValueError(msg)


def _ordem(oid):
    with db.conectar() as con:
        r = con.execute("SELECT * FROM ordens WHERE id=?", (oid,)).fetchone()
    return dict(r) if r else None


def _posicao(pid, aberta=True):
    q = "SELECT * FROM posicoes WHERE id=?" + (" AND status='aberta'" if aberta else "")
    with db.conectar() as con:
        r = con.execute(q, (pid,)).fetchone()
    return dict(r) if r else None


def _resolver_ordem(oid, status, motivo, **cols):
    sets = "status=?, motivo=?, resolvida_em=?" + "".join(f", {k}=?" for k in cols)
    with db.conectar() as con:
        return con.execute(f"UPDATE ordens SET {sets} WHERE id=? AND status='pendente'",
                           (status, motivo, str(pd.Timestamp.now()), *cols.values(), oid)).rowcount


def _enviar_entrada(c, o):
    """Leva à corretora uma ordem que JÁ está gravada como `pendente`. Três desfechos:
    recusada com certeza (resolve `rejeitada`; o sinal segue consumido, como a ordem que
    expira), enviada, ou incerta (fica `pendente` e o ciclo a procura pelo id)."""
    ativo, direcao, oid = o["ativo"], o["direcao"], o["id"]
    # Relida sob o `_lock`: entre gravar a linha e chegar aqui o pânico pode tê-la cancelado.
    # Enviar assim mesmo poria na corretora uma ordem que o livro já deu por cancelada.
    if o["status"] != "pendente":
        raise ValueError(f"ordem #{oid} {o['status']} antes do envio ({o.get('motivo') or '-'})")
    _marcar_escrita(ativo)
    try:
        c.preparar_simbolo(ativo, o["alavancagem"])
    except Exception as e:                          # nada foi enviado ainda
        _resolver_ordem(oid, "rejeitada", f"preparo: {type(e).__name__}: {str(e)[:120]}")
        raise ValueError(f"ordem recusada pela corretora no preparo — {str(e)[:120]}")
    if o["tipo"] == "mercado":
        # O stop vai ANTES da entrada a mercado, como já ia junto da post-only: reduce-only com
        # quantidade, aceito sem posição. Colocá-lo só depois do preenchimento deixava uma janela
        # sem stop, e se o processo caísse nela (deploy, watchdog, o servidor desligando) a
        # posição passava a noite nua (revisão de 26/11). Sem o stop, a entrada não sai.
        try:
            _stop_da_ordem(c, o, cancela_se_falhar=False)
        except Exception as e:
            if _resolver_ordem(oid, "rejeitada", f"stop antes da entrada: {type(e).__name__}: "
                                                 f"{str(e)[:100]}"):
                _cancelar_stop_da_ordem(c, _ordem(oid))
            raise ValueError("ordem não enviada — a corretora não aceitou o stop que vai antes "
                             f"dela ({str(e)[:100]})")
        o = _ordem(oid)
    try:
        if o["tipo"] == "limite":
            ext = c.colocar_limite_post_only(ativo, direcao, o["qty"], o["preco_limite"], o["client_oid"])
        else:
            # `ref_preco`: o teto por ordem é medido no MESMO preço que as guardas mediram antes
            # do claim. Medido num mark mais novo, um tique de alta virava recusa depois de o
            # sinal já estar consumido (revisão de 26/11).
            ext = c.abrir_mercado(ativo, direcao, o["qty"], o["client_oid"], ref_preco=o["preco_ref"])
    except (C.OrdemRecusada, C.AcimaDoTeto, C.AbaixoDoMinimo) as e:
        _resolver_ordem(oid, "rejeitada", f"{type(e).__name__}: {str(e)[:120]}")
        _cancelar_stop_da_ordem(c, _ordem(oid))
        if isinstance(e, (C.AcimaDoTeto, C.AbaixoDoMinimo)):
            # Recusa por teto ou mínimo acontece ANTES da rede: nada foi enviado, e o sinal
            # volta para a fila ([P1-6]: recusa por teto não consome sinal).
            with db.conectar() as con:
                con.execute("UPDATE sinais SET status='novo' WHERE id=? AND status='confirmado'",
                            (o["sinal_id"],))
        raise ValueError(f"ordem recusada pela corretora — {str(e)[:120]}")
    except Exception as e:                          # `EnvioIncerto` e o inesperado: pode ter chegado
        log(f"ORDEM #{oid} {ativo}: envio incerto ({type(e).__name__}: {e}); o ciclo procura "
            "pelo id", "error")
        if o["tipo"] == "limite":
            # Se chegou, ela descansa lá e pode encher com o processo fora do ar. O stop vai
            # AGORA (reduce-only é aceito sem posição); se a entrada não chegou, ele sai junto
            # quando o ciclo resolver a linha. Não conseguiu: o ciclo tenta de novo.
            try:
                _stop_da_ordem(c, o, cancela_se_falhar=False)
            except Exception:
                pass
        return "ordem", oid
    if ext.get("status") == "dry_run":
        _resolver_ordem(oid, "dry_run", "corretora_dry_run: montada e não enviada")
        return "ordem", oid
    with db.conectar() as con:
        con.execute("UPDATE ordens SET ordem_ext_id=? WHERE id=?", (ext.get("id"), oid))
    if o["tipo"] == "mercado":
        if not ext.get("preenchido"):
            log(f"ORDEM #{oid} {ativo}: a mercado sem preenchimento na resposta; o ciclo confere",
                "warning")
            return "ordem", oid
        return "posicao", _materializar(c, _ordem(oid), ext)
    # post-only aceita: o stop sai JUNTO, antes do preenchimento (regra 2)
    pid = _stop_da_ordem(c, o)
    if pid:                                         # encheu enquanto a entrada era cancelada
        return "posicao", pid
    log(f"ORDEM #{oid} {direcao} {ativo} limite {o['preco_limite']} qty {o['qty']} "
        f"stop {o['stop']} [{c.nome}]")
    return "ordem", oid


def _stop_da_ordem(c, o, cancela_se_falhar=True):
    """O stop que acompanha a entrada post-only: `reduceOnly` com quantidade, aceito antes do
    preenchimento. É ele que protege a ordem que enche com o servidor desligado (regra 2).

    Chamado no envio e, de novo, pelo ciclo enquanto a ordem descansar sem ele (envio incerto,
    processo que caiu entre a entrada e o stop). O id é o da ordem (`stop_coid`): repetir é
    idempotente. Se a corretora não aceita o stop, a entrada é cancelada: ordem que pode encher
    sem proteção não descansa. Devolve o id da posição se, ao cancelar, ela já tinha enchido."""
    oid, ativo = o["id"], o["ativo"]
    _marcar_escrita(ativo)
    try:
        sl = c.colocar_stop(ativo, o["direcao"], o["stop"], o["stop_coid"], qty=o["qty"])
    except Exception as e:
        if not cancela_se_falhar:
            raise
        log(f"ORDEM #{oid} {ativo}: stop recusado ({e}); cancelando a entrada", "error")
        pid = _cancelar_entrada(c, _ordem(oid), "stop recusado pela corretora")
        if pid:
            return pid
        raise ValueError(f"ordem cancelada — a corretora recusou o stop ({str(e)[:100]})")
    if sl.get("status") == "dry_run":
        return None
    with db.conectar() as con:
        con.execute("UPDATE ordens SET stop_ext_id=? WHERE id=?", (sl.get("id"), oid))
    o["stop_ext_id"] = sl.get("id")
    return None


def _cancelar_entrada(c, o, motivo, status="cancelada"):
    """Cancela a entrada na corretora e resolve a linha. Se ela encheu (toda ou parte) antes de
    o cancelamento chegar, a posição EXISTE: materializa em vez de fingir que não. Devolve o id
    da posição, ou None."""
    ativo = o["ativo"]
    _marcar_escrita(ativo)
    try:
        # pelo id NOSSO: a ordem de envio incerto existe lá e o livro não tem o id dela
        ext = c.buscar(ativo, o["client_oid"]) if o.get("client_oid") else None
        if ext and ext.get("status") in ("aberta", "parcial"):
            c.cancelar(ativo, ext["id"])
            ext = c.buscar(ativo, o["client_oid"])      # encheu enquanto o cancelamento ia?
    except Exception as e:
        log(f"ORDEM #{o['id']}: cancelamento falhou ({type(e).__name__}: {e}); fica pendente", "error")
        raise
    if ext and (ext.get("preenchido") or 0) > 0:
        return _materializar(c, o, ext)
    if _resolver_ordem(o["id"], status, motivo):
        _cancelar_stop_da_ordem(c, o)
    return None


def _cancelar_stop_da_ordem(c, o):
    if o.get("stop_ext_id"):
        try:
            c.cancelar(o["ativo"], o["stop_ext_id"], condicional=True)
        except Exception as e:                      # fica órfã: a reconciliação cancela
            log(f"ORDEM #{o['id']}: stop pré-colocado não cancelou ({e})", "warning")


def _gravar_fills(con, modo_c, fs, posicao_id, papel):
    for f in fs:
        con.execute("INSERT OR IGNORE INTO fills(id,corretora,ordem_id,ativo,lado,qty,preco,taxa,"
                    "taxa_moeda,maker,pnl_realizado,ts,posicao_id,papel) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f"{modo_c}:{f['id']}", modo_c, f.get("ordem_id"), f.get("simbolo"),
                     f.get("lado"), f.get("qty"), f.get("preco"), f.get("taxa"),
                     f.get("taxa_moeda"), 1 if f.get("maker") else 0, f.get("pnl_realizado"),
                     str(f.get("ts")) if f.get("ts") is not None else None, posicao_id, papel))


JANELA_FILLS = pd.Timedelta(days=6)  # a Binance devolve no máximo 7 dias a partir do `startTime`


def _taxa_usdt(fs, taxa_estimada):
    """A taxa dos negócios, em USDT. A Binance cobra em BNB quando o desconto de taxa está
    ligado na conta: o número vem em BNB e somá-lo como USDT erraria o P&L por um fator de
    centenas. Negócio com taxa em outra moeda entra pela taxa ESTIMADA (fração do nocional);
    o valor e a moeda originais ficam na tabela `fills`, que é o registro fiscal."""
    total = 0.0
    for f in fs:
        moeda = str(f.get("taxa_moeda") or "USDT").upper()
        if moeda in ("USDT", "USDC", "BUSD", "FDUSD"):
            total += f.get("taxa") or 0.0
        else:
            total += (f.get("qty") or 0.0) * (f.get("preco") or 0.0) * taxa_estimada
    return total


def _fills_novos(c, ativo, desde, lado=None):
    """Os negócios do ativo desde `desde` (naive SP) que o livro ainda NÃO lançou.

    A janela é cortada em 6 dias para trás: a Binance só devolve 7 dias a partir do início
    pedido, então para uma posição aberta há mais que isso pedir "desde a abertura" traria a
    primeira semana e nunca o fechamento de hoje. Negócio não lançado com mais de 6 dias não
    existe numa conta que reconcilia a cada ciclo."""
    inicio = max(pd.Timestamp(desde) - pd.Timedelta(seconds=5), pd.Timestamp.now() - JANELA_FILLS)
    todos = c.fills(ativo, C.sp_para_ms(inicio))
    if not todos:
        return []
    with db.conectar() as con:
        linhas = con.execute("SELECT id, ordem_id FROM fills WHERE ativo=? AND corretora=?",
                             (ativo, c.nome)).fetchall()
    # `#`: o negócio que atravessou dois eventos foi gravado em pedaços (`<id>#a`, `<id>#b`, por
    # `_ratear`). O id cru dele não está na tabela, e sem isto ele voltaria como "novo".
    vistos = {str(r["id"]).split("#")[0] for r in linhas}
    # Fechamento lançado SEM o negócio lido (`_fechar_qty` grava `ordem-<id>` no lugar): os
    # negócios daquela ordem aparecem depois e não estão em `vistos`. Sem tirá-los aqui, a
    # próxima saída do mesmo ativo os contaria de novo, no preço e na taxa.
    as_cegas = {str(r["ordem_id"]) for r in linhas
                if str(r["id"]).startswith(f"{c.nome}:ordem-") and r["ordem_id"] is not None}
    return sorted((f for f in todos
                   if f"{c.nome}:{f['id']}" not in vistos
                   and str(f.get("ordem_id")) not in as_cegas
                   and (lado is None or f.get("lado") == lado)),
                  key=lambda f: str(f.get("ts")))


def _materializar(c, o, ext):
    """A ordem encheu: nasce a posição, com o que a corretora de fato executou (preço médio,
    quantidade, taxa). O `rowcount` na ordem impede duas posições da mesma ordem."""
    ativo, direcao, lev = o["ativo"], o["direcao"], float(o["alavancagem"])
    d = _d(direcao)
    qty = float(ext.get("preenchido") or 0)
    if qty <= 0:
        raise ValueError("ordem sem preenchimento")
    entrada = float(ext.get("preco_medio") or o["preco_limite"])
    cfg = db.get_config()
    fs = []
    try:
        # A mercado acabou de executar, e o negócio pode levar um instante para aparecer na
        # leitura. Sem ele a entrada fica fora da tabela `fills` para sempre.
        for _ in range(3 if o["tipo"] == "mercado" else 1):
            fs = [f for f in _fills_novos(c, ativo, o["criada_em"], C._ABRE[direcao])
                  if str(f.get("ordem_id")) == str(ext.get("id"))]
            if fs:
                break
            time.sleep(0.4)
    except Exception as e:
        log(f"ORDEM #{o['id']}: negócios da entrada não lidos ({e}); taxa pela config", "warning")
        fs = []
    taxa_rate = simulador._cfg_float(cfg, "taxa_maker" if o["tipo"] == "limite" else "taxa_por_lado",
                                     0.0002 if o["tipo"] == "limite" else 0.0005)
    # A taxa que a corretora COBROU, como fração do nocional dos negócios LIDOS. Dividir pelo
    # nocional da ordem inteira subestimaria a taxa quando só parte dos negócios já apareceu.
    nocional_fs = sum((f.get("qty") or 0) * (f.get("preco") or 0) for f in fs)
    if nocional_fs > 0:
        taxa_rate = _taxa_usdt(fs, taxa_rate) / nocional_fs
    stop = o["stop"]
    if o["tipo"] == "mercado" and o.get("stop_rel") and not o.get("stop_ext_id"):
        # sem stop pré-colocado, o stop acompanha o preço que encheu; com ele, o livro fica com
        # o número que JÁ está protegendo na corretora
        stop = c.preco_valido(ativo, entrada * (1 - d * float(o["stop_rel"])))
    valor = qty * entrada / lev
    risco_ab = simulador._risco_posicao(valor, lev, entrada, stop)
    agora = str(pd.Timestamp.now())
    # `aberto_em` é a hora em que a posição nasceu NA CORRETORA, não a hora em que o livro
    # soube. A ordem que enche de madrugada só vira linha aqui de manhã; se o stop dela também
    # disparou de madrugada, o negócio da saída é ANTERIOR a "agora", e é a partir de
    # `aberto_em` que a reconciliação procura os negócios da saída e o funding. Sem o negócio
    # lido, a ordem limite usa a hora em que foi criada (antes disso ela não pode ter enchido).
    horas = [pd.Timestamp(f["ts"]) for f in fs if f.get("ts") is not None]
    aberto_em = str(min(horas)) if horas else (str(o["criada_em"]) if o["tipo"] == "limite" else agora)
    with simulador._abrir_lock:
        with db.conectar() as con:
            if con.execute("UPDATE ordens SET status='preenchida', resolvida_em=?, qty_preenchida=?, "
                           "ordem_ext_id=? WHERE id=? AND status='pendente'",
                           (agora, qty, ext.get("id"), o["id"])).rowcount != 1:
                raise ValueError("ordem já resolvida")
            con.execute("INSERT INTO posicoes(ativo,direcao,entrada,valor_reais,alavancagem,stop,"
                        "preco_atual,pnl,aberto_em,status,conviccao,sinal_id,taxa_entrada,"
                        "stop_abertura,risco_abertura,corretora,qty,qty_inicial,client_oid,"
                        "ordem_ext_id,stop_ext_id,stop_coid,stop_seq,funding_pago) "
                        "VALUES(?,?,?,?,?,?,?,0,?,'aberta',?,?,?,?,?,?,?,?,?,?,?,?,0,0)",
                        (ativo, direcao, entrada, valor, lev, stop, entrada, aberto_em,
                         o["conviccao"], o["sinal_id"], taxa_rate, stop, round(risco_ab, 4),
                         c.nome, qty, qty, o["client_oid"], ext.get("id"),
                         o.get("stop_ext_id"), o.get("stop_coid") if o.get("stop_ext_id") else None))
            pid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
            con.execute("UPDATE ordens SET posicao_id=? WHERE id=?", (pid, o["id"]))
            _gravar_fills(con, c.nome, fs, pid, "entrada")
    log(f"ABRIU #{pid} {direcao} {ativo} @ {entrada} qty {qty} | {valor:.2f} USDT {lev:g}x "
        f"[{c.nome}, ordem #{o['id']}]")
    pos = _posicao(pid)
    # stop pré-colocado serve se a quantidade é a que encheu; senão (a mercado, ou parcial)
    # coloca agora o do tamanho certo. Sem stop, a posição é desfeita (regra 2).
    if not pos["stop_ext_id"] or abs(qty - float(o["qty"])) > 1e-12:
        if not _garantir_stop(c, pos, pos["stop"], forcar=True):    # mesmo preço, outra quantidade
            return pid
    alertas.enviar(f"🟢 Abriu {direcao} {ativo} [{c.nome}]\n{valor:.2f} USDT @ {lev:g}x · entrada {entrada}")
    push.avisar(*push.msg_abriu(direcao, ativo, round(valor, 2), lev, entrada),
                f"#pos/{pid}", f"pos-{pid}", tipo="entrada")
    return pid


# ------------------------------------------------------------------------------ o stop

def _garantir_stop(c, pos, gatilho, motivo_falha="sem-stop", forcar=False):
    """Põe na corretora um stop em `gatilho` para a quantidade ABERTA da posição, e só depois
    cancela o anterior (nunca há janela sem stop). Grava o número no banco depois de a
    corretora aceitar, nunca antes. Devolve True se a posição ficou protegida.

    Se a corretora recusa porque o gatilho já foi atravessado (`-2021`), o stop "bateu" sem
    estar lá: fecha a mercado, motivo `stop`. Se recusa por outro motivo duas vezes seguidas,
    também fecha: posição sem stop não fica aberta. False = a posição foi fechada.

    `forcar` é para quando o preço é o mesmo e o que mudou foi a QUANTIDADE (a posição cresceu
    na corretora). Sem ele, pedir o stop que já está lá no mesmo preço não faz nada."""
    ativo, direcao = pos["ativo"], pos["direcao"]
    gatilho = c.preco_valido(ativo, gatilho)
    antigo = ({"id": pos["stop_ext_id"], "client_oid": pos.get("stop_coid"),
               "lado": C._FECHA[direcao], "qty": None} if pos.get("stop_ext_id") else None)
    if antigo and not forcar and pos.get("stop") and abs(gatilho - float(pos["stop"])) < 1e-12:
        return True                                 # arredondado, é o stop que já está lá
    for tentativa in (1, 2):
        seq = _seq(pos)                             # id novo a cada tentativa, gravado antes da rede
        coid = _coid("s", pos["id"], seq)
        _marcar_escrita(ativo)
        try:
            if antigo:
                novo = c.mover_stop(ativo, antigo, gatilho, coid, qty=pos["qty"])
            else:
                novo = c.colocar_stop(ativo, direcao, gatilho, coid, qty=pos["qty"])
            break
        except C.OrdemRecusada as e:
            if "-2021" in str(e):                   # o preço já passou do gatilho
                log(f"#{pos['id']} {ativo}: stop {gatilho} já atravessado; fechando a mercado", "error")
                fechar(pos, "stop")
                return False
            erro = e
        except Exception as e:
            erro = e
        # Com um stop anterior de pé, a posição segue protegida: não há pressa. Sem ele, a
        # segunda tentativa é AGORA, e não no ciclo seguinte (CLAUDE.md [LIVE] regra 2): entre um
        # ciclo e outro o processo pode cair, e o servidor desliga à noite.
        if antigo or tentativa == 2:
            return _stop_falhou(c, pos, erro, motivo_falha)
        log(f"#{pos['id']} {ativo}: stop não entrou ({type(erro).__name__}: {erro}); "
            "tentando de novo agora", "error")
        time.sleep(0.5)
    if novo.get("status") == "dry_run":
        # Nada foi enviado. Gravar o id e o preço deste stop faria o livro mostrar uma proteção
        # que não existe na corretora.
        log(f"#{pos['id']} {ativo}: dry_run, o stop {gatilho} NÃO foi enviado", "warning")
        return True
    _sem_stop.pop(pos["id"], None)
    # O gatilho gravado é o que a corretora DEVOLVEU, não o que foi pedido: se os dois
    # diferirem, o livro fica com o número que está protegendo de verdade.
    gatilho = novo.get("gatilho") or gatilho
    with db.conectar() as con:
        con.execute("UPDATE posicoes SET stop=?, stop_ext_id=?, stop_coid=?, stop_seq=? "
                    "WHERE id=? AND status='aberta'", (gatilho, novo.get("id"), coid, seq, pos["id"]))
    pos.update(stop=gatilho, stop_ext_id=novo.get("id"), stop_coid=coid, stop_seq=seq)
    return True


def _stop_falhou(c, pos, erro, motivo):
    """O stop não entrou. Com um stop anterior de pé, nada muda (ele continua protegendo).
    Sem ele, as duas tentativas já foram feitas na mesma chamada: a posição é fechada."""
    tem_stop = bool(pos.get("stop_ext_id"))
    log(f"#{pos['id']} {pos['ativo']}: stop não colocado ({type(erro).__name__}: {erro}) "
        f"[{'há um stop anterior' if tem_stop else 'SEM stop na corretora'}]", "error")
    if tem_stop:                                    # o stop anterior continua protegendo
        return True
    _avisar(f"🛑 #{pos['id']} {pos['ativo']}: sem stop na corretora depois de 2 tentativas "
            f"({type(erro).__name__}). Fechando a mercado.")
    fechar(pos, motivo)
    return False


def _stop_desejado(pos, preco, trail, tp, plano, passo_r):
    """O stop que a posição deveria ter AGORA, ou None se o que está lá serve.

    As mesmas duas regras do papel, pelas mesmas funções: o trailing
    (`simulador._trailing_novo_stop`) e o zero a zero depois do TP1 (`tp_stop_entrada`). É
    catraca: só devolve um stop que anda a favor. O `passo_r` é o que impede reenviar o stop a
    cada centavo: o trailing só conta quando andou esse tanto, em R."""
    d = _d(pos["direcao"])
    atual = pos["stop"]
    melhor = None
    novo = simulador._trailing_novo_stop(pos, preco, d, trail)
    r = simulador._r_abertura(pos)
    passo = passo_r * r if r else 0.001 * preco     # sem R mensurável: 0,1% do preço
    if novo is not None and atual and (novo - atual) * d > passo:
        melhor = novo
    if tp and tp.get("stop_entrada") and plano:
        n0 = (plano.get("niveis") or [None])[0]
        # TP1 pulado (menor que um lote) não executa nada, e por isso não pode ser o gatilho do
        # zero a zero; quem arma é o PREÇO chegar ao alvo, como no papel. Sem isto a regra nunca
        # armava nas posições pequenas, justamente as da conta de US$200.
        atingido = n0 and n0.get("feito") and (
            not n0.get("pulado") or (n0.get("preco") and (preco - float(n0["preco"])) * d >= 0))
        if atingido:
            e = float(pos["entrada"])
            base = melhor if melhor is not None else atual
            if not base or (e - base) * d > 0:
                melhor = e
    return melhor


# ------------------------------------------------------------------------------ os alvos

def _colocar_tps(c, pos, plano):
    """Põe na corretora os alvos do plano que ainda não têm ordem. Fração do tamanho ORIGINAL,
    como no papel; o último leva o que sobrar, salvo no plano de resto livre.

    O alvo cujo tamanho não chega a um lote fica sem ordem (`pulado`) e essa parte segue no
    trailing. O alvo que o preço já passou (`-2021`) realiza a mercado, como no papel."""
    niveis = plano.get("niveis") or []
    q0 = float(pos.get("qty_inicial") or pos["qty"])
    mudou = False
    comprometido = sum(float(t.get("qty") or 0) for t in niveis if t.get("ext_id") and not t.get("feito"))
    try:
        for i, t in enumerate(niveis):
            if t.get("feito") or t.get("ext_id"):
                continue
            ultimo = i == len(niveis) - 1
            livre = max(float(pos["qty"]) - comprometido, 0.0)
            if ultimo and not plano.get("resto_livre"):
                # O último leva o que sobrar, MENOS a fração dos alvos pulados: essa parte segue
                # no trailing, como diz o log do pulo. Sem o desconto, com BTC em US$200 (0,002) o
                # TP1 e o TP2 eram pulados e o TP3, o mais longe, fechava a posição INTEIRA
                # (revisão de 26/11).
                pulada = sum(float(x.get("frac") or 0) * q0 for x in niveis if x.get("pulado"))
                alvo_q = max(livre - pulada, 0.0)
            else:
                alvo_q = min(t["frac"] * q0, livre)
            try:
                q, _ = c.arredondar(pos["ativo"], alvo_q, reduz=True)
            except C.AbaixoDoMinimo:
                t.update(feito=True, pulado=True)
                mudou = True
                log(f"#{pos['id']} {pos['ativo']}: TP{i + 1} menor que um lote; segue no trailing")
                continue
            # id novo a cada tentativa (`_seq`): o nível do alvo fica no plano, não no id
            coid = _coid("t", pos["id"], _seq(pos))
            _marcar_escrita(pos["ativo"])
            try:
                ext = c.colocar_tp(pos["ativo"], pos["direcao"], t["preco"], q, coid)
            except C.OrdemRecusada as e:
                if "-2021" not in str(e):
                    log(f"#{pos['id']} {pos['ativo']}: TP{i + 1} recusado ({e})", "error")
                    continue
                # O preço já passou do alvo: realiza a mercado. O alvo é marcado como feito e
                # GRAVADO antes de a ordem sair. Se o envio ficar incerto e a ordem tiver
                # executado, o ciclo seguinte não pode achar o alvo em aberto e realizar a
                # mesma fatia de novo; se não executou, essa fatia segue no trailing.
                t.update(feito=True, em=str(pd.Timestamp.now()))
                _salvar_plano(pos, plano)
                mudou = False
                if q >= float(pos["qty"]) - 1e-12:  # o alvo era a posição inteira
                    fechar(pos, f"tp{i + 1}")
                    return True
                _fechar_qty(c, pos, q, f"tp{i + 1}", plano)
                mudou = True
                continue
            except Exception as e:
                log(f"#{pos['id']} {pos['ativo']}: TP{i + 1} não colocado ({type(e).__name__}: {e})", "error")
                continue
            if ext.get("status") == "dry_run":
                continue
            t.update(ext_id=ext.get("id"), coid=coid, qty=q)
            comprometido += q
            mudou = True
    finally:
        # Também quando alguma coisa levanta no meio: o alvo que JÁ foi colocado tem de ficar
        # com o id dele no plano. Sem isso a reconciliação o cancelaria como ordem sem dono e o
        # ciclo seguinte o colocaria de novo, para sempre.
        if mudou:
            _salvar_plano(pos, plano)
    return False


def _salvar_plano(pos, plano):
    txt = json.dumps(plano)
    with db.conectar() as con:
        con.execute("UPDATE posicoes SET tps=? WHERE id=? AND status='aberta'", (txt, pos["id"]))
    pos["tps"] = txt


# ------------------------------------------------------------------------------ fechar

def _funding_real(c, pos, ate=None):
    """O funding que a corretora lançou para o ativo desde a abertura, ainda não atribuído a um
    fechamento parcial. None = não deu para medir (que não é zero: [P2-10])."""
    try:
        linhas = c.income(pos["ativo"], C.sp_para_ms(pos["aberto_em"]), tipo="FUNDING_FEE")
    except Exception as e:
        log(f"funding real não medido {pos['ativo']} #{pos['id']}: {type(e).__name__}: {e}", "warning")
        return None
    ini = pd.Timestamp(pos["aberto_em"])
    fim = pd.Timestamp(ate) if ate is not None else None
    total = sum((x.get("valor") or 0.0) for x in linhas
                if x.get("tipo") == "FUNDING_FEE" and x.get("ts") is not None
                and x["ts"] >= ini and (fim is None or x["ts"] <= fim))
    return total - float(pos.get("funding_pago") or 0.0)


def _lancar_saida(c, pos, fs, motivo, plano=None, qty_fechada=None):
    """Lança no livro uma saída JÁ acontecida na corretora, com os negócios `fs` que a fizeram.
    Inteira se a quantidade fechada é a posição toda, parcial senão. É o único ponto que grava
    saída da conta real, venha ela de um fechamento nosso ou de um que a corretora fez sozinha.

    P&L, taxa e funding são os LANÇADOS; o que o modelo do papel diria vai nas colunas
    `*_modelo` do trade, pelo próprio `simulador` (a diferença é a medição)."""
    q = float(qty_fechada if qty_fechada is not None else sum(f.get("qty") or 0 for f in fs))
    q_pos = float(pos["qty"])
    if q <= 0:
        return None
    q = min(q, q_pos)
    inteira = q >= q_pos * (1 - 1e-9)
    d = _d(pos["direcao"])
    qf = sum(f.get("qty") or 0 for f in fs)
    saida = (sum((f.get("qty") or 0) * (f.get("preco") or 0) for f in fs) / qf) if qf else float(pos["preco_atual"])
    taxa_saida = _taxa_usdt(fs, simulador._cfg_float(db.get_config(), "taxa_por_lado", 0.0005))
    entrada = float(pos["entrada"])
    taxa_ent = float(pos.get("taxa_entrada") or 0) * entrada * q
    bruto = d * (saida - entrada) * q
    fim = max((pd.Timestamp(f["ts"]) for f in fs if f.get("ts") is not None), default=None)
    fund_tot = _funding_real(c, pos, fim)
    funding = None if fund_tot is None else fund_tot * (1.0 if inteira else q / q_pos)
    pnl = bruto - taxa_ent - taxa_saida + (funding or 0.0)
    fechado_em = str(fim if fim is not None else pd.Timestamp.now())
    sobra = _lote(c, pos["ativo"], q_pos - q) if not inteira else 0.0

    def apos(con):
        _gravar_fills(con, c.nome, fs, pos["id"], "saida")
        if not inteira:
            con.execute("UPDATE posicoes SET qty=?, funding_pago=COALESCE(funding_pago,0)+? WHERE id=?",
                        (sobra, funding or 0.0, pos["id"]))

    dados = {"pnl": pnl, "taxa": taxa_ent + taxa_saida, "funding": funding, "fechado_em": fechado_em,
             "corretora": c.nome, "qty": q, "apos": apos}
    if inteira:
        r = simulador._fechar_uma(pos["id"], motivo, saida, real=dados)
        if r is simulador._MUDOU or r is None:
            return None
        _falta_fill.pop(pos["id"], None)
        _sem_stop.pop(pos["id"], None)
        return pnl
    plano = plano if plano is not None else (alvos.ler(pos) or {"niveis": []})
    resto = simulador.fechar_parcial(pos, q / q_pos, motivo, saida, plano, real=dados)
    if resto is None:
        return None
    pos.update(valor_reais=resto, qty=sobra, tps=json.dumps(plano),
               funding_pago=float(pos.get("funding_pago") or 0) + (funding or 0.0))
    if pos.get("risco_abertura") is not None:
        pos["risco_abertura"] = pos["risco_abertura"] * (1 - q / q_pos)
    return pnl


def _cancelar_condicionais(c, pos, menos=()):
    """Cancela stop, alvos e trailing da noite que a posição ainda tem na corretora. É o que
    impede a condicional órfã de fechar parte da PRÓXIMA posição no mesmo ativo."""
    ativo = pos["ativo"]
    ids = []
    if pos.get("stop_ext_id"):
        ids.append(pos["stop_ext_id"])
    for t in (alvos.ler(pos) or {}).get("niveis", []):
        if t.get("ext_id") and not t.get("feito"):
            ids.append(t["ext_id"])
    try:
        nt = json.loads(pos["noite"]) if pos.get("noite") else None
    except (TypeError, ValueError):
        nt = None
    if nt and nt.get("id"):
        ids.append(nt["id"])
    _marcar_escrita(ativo)
    for i in ids:
        if i in menos:
            continue
        try:
            c.cancelar(ativo, i, condicional=True)
        except Exception as e:                      # fica órfã: a reconciliação cancela
            log(f"#{pos['id']} {ativo}: condicional {i} não cancelou ({e})", "warning")


def _fechar_qty(c, pos, qty, motivo, plano=None):
    """Fecha `qty` a mercado (reduce-only) e lança a saída com os negócios reais."""
    seq = _seq(pos)                                 # o contador é da posição, não só do stop
    _marcar_escrita(pos["ativo"])
    ext = c.fechar_mercado(pos["ativo"], pos["direcao"], qty, _coid("x", pos["id"], seq))
    if ext.get("status") == "dry_run":
        # Não é sucesso: nada saiu daqui. Devolver None faria o `/fechar` e o pânico
        # responderem "ok" com a posição aberta na corretora.
        raise ValueError("corretora_dry_run está ligado: o fechamento NÃO foi enviado. Desligue "
                         "o dry_run, ou feche no aplicativo da corretora.")
    fs = []
    for _ in range(3):                              # o negócio pode levar um instante para aparecer
        try:
            fs = [f for f in _fills_novos(c, pos["ativo"], pos["aberto_em"], C._FECHA[pos["direcao"]])
                  if str(f.get("ordem_id")) == str(ext.get("id"))]
        except Exception as e:
            # A ordem JÁ executou; o que falhou foi ler o negócio. Subir a exceção aqui diria
            # "não deu para confirmar o fechamento" de uma posição que fechou (revisão de 26/11).
            log(f"#{pos['id']} {pos['ativo']}: negócio do fechamento não lido ({type(e).__name__}: "
                f"{e}); segue pelo que a ordem devolveu", "warning")
            fs = []
            break
        if fs:
            break
        time.sleep(0.4)
    feito = float(ext.get("preenchido") or 0) or sum(f.get("qty") or 0 for f in fs)
    if feito <= 0:
        # Nada executado, ou nada que se saiba. Lançar a quantidade PEDIDA como fechada (o que
        # este código fazia) gravava um resultado que não houve e, logo depois, o `fechar`
        # cancelava stop e alvos de uma posição que continuava aberta lá (revisão de 26/11).
        st = ext.get("status")
        if st in ("cancelada", "expirada", "rejeitada"):
            raise C.OrdemRecusada(f"o fechamento voltou {st} sem executar nada "
                                  f"(ordem {ext.get('id')})")
        if st != "preenchida":
            raise C.EnvioIncerto(f"o fechamento voltou '{st}' sem quantidade executada "
                                 f"(ordem {ext.get('id')}); a reconciliação confere")
        feito = float(qty)                          # FILLED sem o número: a ordem inteira executou
    if not fs:                                      # sem negócio lido: usa o preço médio da ordem
        # `taxa_moeda="estimada"` faz a taxa entrar pela fração da config (`_taxa_usdt`): a saída
        # a mercado pagou taxa de taker, e lançar zero inflaria o resultado.
        fs = [{"id": f"ordem-{ext.get('id')}", "ordem_id": ext.get("id"), "simbolo": pos["ativo"],
               "lado": C._FECHA[pos["direcao"]], "qty": feito,
               "preco": ext.get("preco_medio") or pos["preco_atual"], "taxa": 0.0,
               "taxa_moeda": "estimada", "maker": False, "pnl_realizado": None,
               "ts": pd.Timestamp.now()}]
        log(f"#{pos['id']} {pos['ativo']}: negócio do fechamento não lido; preço médio da ordem "
            "e taxa estimada pela config", "warning")
    return _lancar_saida(c, pos, fs, motivo, plano, qty_fechada=feito)


def _nada_a_reduzir(e):
    """A recusa é a de "não há posição para reduzir" (`-2022`, ReduceOnly rejected)? É a ÚNICA
    recusa que diz que a posição já fechou. O adapter põe em `OrdemRecusada` todo erro da
    corretora, inclusive proteção de preço (`-4131`) e ordem que expirou sem executar."""
    return "-2022" in str(e)


def fechar(pos, motivo):
    """Fecha a posição INTEIRA a mercado na corretora e lança a saída. É para onde o
    `simulador.fechar` despacha quando a posição tem `corretora` (manual, pânico, auto-saída).

    Primeiro fecha, depois cancela stop e alvos: se o fechamento falhar, o stop continua lá."""
    with _lock:
        pos = _posicao(pos["id"])
        if not pos:
            return None
        c = obter()
        try:
            pnl = _fechar_qty(c, pos, float(pos["qty"]), motivo)
        except C.OrdemRecusada as e:
            log(f"#{pos['id']} {pos['ativo']}: fechamento recusado ({e}); a reconciliação confere",
                "warning")
            if _nada_a_reduzir(e):
                # reduce-only recusado por não haver o que reduzir: a posição já fechou lá
                # (stop, alvo, liquidação) e a reconciliação lança a saída com o negócio certo.
                raise ValueError("a corretora recusou o fechamento: a posição pode já ter fechado "
                                 "lá. A reconciliação confere no próximo ciclo.")
            # Qualquer outra recusa (proteção de preço, ordem expirada sem executar) quer dizer
            # que a posição SEGUE aberta. Dizer "pode já ter fechado" seria mentir para quem clicou.
            raise ValueError(f"a corretora recusou o fechamento ({str(e)[:120]}). A posição SEGUE "
                             "aberta lá, com o stop; tente de novo ou feche no aplicativo.")
        except C.ErroCorretora as e:
            # envio incerto: pode ter fechado ou não. O stop continua lá, e a reconciliação
            # lança a saída se fechou. Recusa de domínio, não 500: quem clicou precisa do motivo.
            log(f"#{pos['id']} {pos['ativo']}: fechamento incerto ({type(e).__name__}: {e})", "error")
            raise ValueError(f"não deu para confirmar o fechamento na corretora ({str(e)[:100]}). "
                             "O stop segue lá; a reconciliação confere no próximo ciclo.")
        except ValueError:
            raise
        except Exception as e:                      # o que o adapter não traduziu: mesma resposta
            log(f"#{pos['id']} {pos['ativo']}: fechamento falhou ({type(e).__name__}: {e})", "error")
            raise ValueError("não deu para confirmar o fechamento na corretora "
                             f"({type(e).__name__}). O stop segue lá; a reconciliação confere "
                             "no próximo ciclo.")
        if _posicao(pos["id"]):
            # A ordem a mercado encheu só PARTE. Stop e alvos ficam: cancelá-los agora deixaria
            # o resto aberto sem proteção, com o livro dizendo que fechou.
            _avisar(f"⚠️ #{pos['id']} {pos['ativo']}: o fechamento ({motivo}) executou só parte. "
                    "O resto segue aberto, com o stop na corretora.")
            raise ValueError("a corretora fechou só parte da posição. O resto segue aberto, com "
                             "o stop lá; tente fechar de novo.")
        _cancelar_condicionais(c, pos)
        return pnl


# ------------------------------------------------------------------------------ o ciclo

def processar_ordens(cfg=None):
    """Um ciclo sobre as entradas pendentes: pergunta à corretora o que houve com cada uma.
    Try POR ORDEM ([P1-1]). Preencheu vira posição; venceu o prazo, travou o dia ou anoiteceu,
    cancela LÁ e só então resolve a linha."""
    cfg = db.get_config() if cfg is None else cfg
    with db.conectar() as con:
        pend = [dict(r) for r in con.execute("SELECT * FROM ordens WHERE status='pendente'")]
    res = {"vistas": len(pend), "preenchidas": 0, "expiradas": 0, "falhas": 0}
    if not pend:
        return res
    c = obter(cfg)
    agora = pd.Timestamp.now()
    trava = simulador.guarda_risco()["trava_dia"]
    # O teto de perda total desliga o `auto_trade`, mas a ordem que JÁ descansa na corretora
    # não lê config nenhuma: sem cancelá-la, ela enche e vira posição com a conta travada.
    travada_total = guarda_total(cfg)["travada"]
    de_noite = noite(cfg, agora)
    for o in pend:
        try:
            with _lock:
                o = _ordem(o["id"])
                if not o or o["status"] != "pendente":
                    continue
                if _escrita_recente(o["ativo"]):
                    continue
                ext = c.buscar(o["ativo"], o["client_oid"])
                if ext is None:
                    idade = (agora - pd.Timestamp(o["criada_em"])).total_seconds()
                    if idade > ORDEM_SUMIDA_S:
                        if _resolver_ordem(o["id"], "rejeitada", "a corretora não conhece a ordem"):
                            _cancelar_stop_da_ordem(c, o)
                        res["expiradas"] += 1
                    continue
                if not o.get("ordem_ext_id"):
                    with db.conectar() as con:
                        con.execute("UPDATE ordens SET ordem_ext_id=? WHERE id=?", (ext.get("id"), o["id"]))
                    o["ordem_ext_id"] = ext.get("id")
                st, feito = ext.get("status"), float(ext.get("preenchido") or 0)
                if st == "preenchida":
                    _materializar(c, o, ext)
                    res["preenchidas"] += 1
                elif st in ("aberta", "parcial"):
                    vencida = bool(o["expira_em"]) and agora >= pd.Timestamp(o["expira_em"])
                    motivo = ("parcial: o resto foi cancelado" if feito > 0 else
                              "trava diaria ativa" if trava else
                              "teto de perda total" if travada_total else
                              "modo noite" if de_noite else "ttl" if vencida else None)
                    if motivo is None:
                        # Vai continuar descansando: tem de ter o stop junto (regra 2). Falta
                        # quando o envio da entrada ficou incerto, ou o processo caiu entre a
                        # entrada e o stop. Se a corretora o recusa, a entrada é cancelada.
                        if o.get("tipo") == "limite" and not o.get("stop_ext_id") and not _dry(c):
                            log(f"ORDEM #{o['id']} {o['ativo']}: descansando sem o stop; colocando",
                                "warning")
                            try:
                                if _stop_da_ordem(c, o):
                                    res["preenchidas"] += 1
                            except ValueError:
                                res["expiradas"] += 1
                        continue
                    pid = _cancelar_entrada(c, o, motivo, "expirada" if motivo == "ttl" else "cancelada")
                    res["preenchidas" if pid else "expiradas"] += 1
                else:                               # cancelada, expirada ou rejeitada LÁ
                    if feito > 0:
                        _materializar(c, o, ext)
                        res["preenchidas"] += 1
                    else:
                        if _resolver_ordem(o["id"], "cancelada", f"{st} na corretora"):
                            _cancelar_stop_da_ordem(c, o)
                        res["expiradas"] += 1
        except Exception as e:
            res["falhas"] += 1
            log(f"ordem #{o['id']} falhou: {type(e).__name__}: {e}", "error")
    return res


def atualizar(cfg, trail, tp):
    """A marcação da conta real: preço de MARCAÇÃO do futuro para todas as posições num pedido
    só, e para cada uma (try por posição, [P1-1]) o P&L do livro, os alvos e o stop.

    Não fecha nada por preço: stop, alvo e liquidação são ordens na corretora, e quem lança a
    saída é a reconciliação. Devolve a lista de eventos, no formato do `simulador.atualizar`."""
    eventos = []
    with db.conectar() as con:
        abertas = [dict(r) for r in con.execute(
            "SELECT * FROM posicoes WHERE status='aberta' AND corretora IS NOT NULL")]
    simulador.ultima_marcacao.update(ts=str(pd.Timestamp.now()), total=len(abertas), ok=0,
                                     falhas=0, ultimo_erro=None)
    if not abertas:
        return eventos
    c = obter(cfg)
    try:
        marks = c.marks(sorted({p["ativo"] for p in abertas}))
    except Exception as e:
        simulador.ultima_marcacao.update(falhas=len(abertas),
                                         ultimo_erro=f"marks: {type(e).__name__}: {str(e)[:140]}")
        log(f"marcação real falhou: {type(e).__name__}: {e}", "error")
        return eventos
    passo_r = simulador._cfg_float(cfg, "corretora_trailing_passo_r", 0.1)
    de_noite = noite(cfg)
    saude["noite"] = de_noite
    for pos in abertas:
        try:
            with _lock:
                pos = _posicao(pos["id"])
                if not pos:
                    continue
                preco = marks.get(pos["ativo"])
                if not preco:
                    raise ValueError("sem preço de marcação")
                preco = float(preco)
                plano = alvos.ler(pos)
                if tp and tp.get("on") and float(pos["qty"]) > 0:
                    # try PRÓPRIO, como no papel: uma falha ao buscar velas para os alvos não
                    # pode tirar esta posição do trailing logo abaixo.
                    try:
                        if plano is None:
                            plano, _ = simulador._plano_tps(pos, tp)
                        if any(not t.get("feito") and not t.get("ext_id")
                               for t in plano.get("niveis", [])):
                            if _colocar_tps(c, pos, plano):
                                eventos.append((pos["id"], "tp"))
                                continue
                            pos = _posicao(pos["id"]) or pos
                    except Exception as e:
                        log(f"TP falhou {pos['ativo']} #{pos['id']}: {type(e).__name__}: "
                            f"{str(e)[:140]}", "error")
                if not pos.get("stop_ext_id") and not _dry(c):
                    # Sem stop na corretora (o envio falhou depois de uma entrada a mercado):
                    # repõe AQUI, a cada ciclo. A reconciliação também repõe, mas só quando as
                    # leituras dela passam; isto não depende delas.
                    if not _garantir_stop(c, pos, pos["stop"], forcar=True):
                        eventos.append((pos["id"], "stop"))
                        continue
                if de_noite:
                    _trailing_da_noite(c, pos, preco, trail)
                else:
                    _fim_da_noite(c, pos, trail)
                novo = _stop_desejado(pos, preco, trail, tp, plano, passo_r)
                if novo is not None and not _garantir_stop(c, pos, novo):
                    eventos.append((pos["id"], "stop"))
                    continue
                pnl, _, _ = simulador._pnl(pos, preco, cfg)
                with db.conectar() as con:
                    con.execute("UPDATE posicoes SET preco_atual=?, pnl=? WHERE id=? AND status='aberta'",
                                (preco, pnl, pos["id"]))
            simulador.ultima_marcacao["ok"] += 1
        except Exception as e:
            simulador.ultima_marcacao["falhas"] += 1
            simulador.ultima_marcacao["ultimo_erro"] = (f"{pos['ativo']}: {type(e).__name__}: "
                                                        f"{str(e)[:140]}")
            log(f"marcação real falhou {pos['ativo']} #{pos['id']}: {e}", "error")
    return eventos


# ------------------------------------------------------------------------------ a noite

def _trailing_da_noite(c, pos, preco, trail):
    """Entrega o trailing à corretora enquanto o servidor estiver desligado: uma ordem
    TRAILING_STOP_MARKET nativa por posição, uma vez por noite.

    Aproximação declarada: o trailing do bot é em R, o nativo é em % do preço. A distância em
    R é convertida em % sobre o preço de ativação. O stop fixo continua lá: dos dois, o que
    disparar primeiro fecha, e o outro a reconciliação da manhã cancela."""
    if pos.get("noite") or not trail.get("on") or trail.get("unidade") != "R":
        return
    r = simulador._r_abertura(pos)
    if not r:
        return
    d = _d(pos["direcao"])
    arma = float(pos["entrada"]) + d * trail["arma_r"] * r
    ativacao = arma if (arma - preco) * d > 0 else None      # None = já armou: ativa no preço atual
    ref = ativacao or preco
    cb = min(10.0, max(0.1, round(trail["dist_r"] * r / ref * 100, 1)))
    seq = _seq(pos)
    coid = _coid("r", pos["id"], seq)
    _marcar_escrita(pos["ativo"])
    try:
        # já armado: SEM preço de ativação (a Binance ativa no preço do momento). Mandar o preço
        # de agora como ativação é recusado quando o mercado anda um tique antes de a ordem chegar.
        ext = c.colocar_trailing(pos["ativo"], pos["direcao"], pos["qty"], ativacao, cb, coid)
    except Exception as e:
        log(f"#{pos['id']} {pos['ativo']}: trailing da noite não colocado ({type(e).__name__}: {e})",
            "warning")
        return
    if ext.get("status") == "dry_run":
        return
    nt = json.dumps({"id": ext.get("id"), "coid": coid, "cb": cb, "ativacao": ativacao,
                     "desde": str(pd.Timestamp.now())})
    with db.conectar() as con:
        con.execute("UPDATE posicoes SET noite=?, stop_seq=? WHERE id=? AND status='aberta'",
                    (nt, seq, pos["id"]))
    pos.update(noite=nt, stop_seq=seq)
    log(f"#{pos['id']} {pos['ativo']}: trailing da noite na corretora (callback {cb}%, "
        f"ativação {ativacao if ativacao is not None else 'imediata'})")


def _fim_da_noite(c, pos, trail):
    """De manhã o trailing volta para o bot. Antes de cancelar o nativo, o stop fixo sobe para
    onde o trailing em R estaria pelo melhor preço da noite (velas de 1 min): cancelar primeiro
    trocaria a proteção que a corretora deu de madrugada pelo preço de agora."""
    if not pos.get("noite"):
        return
    try:
        nt = json.loads(pos["noite"])
    except (TypeError, ValueError):
        nt = {}
    d = _d(pos["direcao"])
    r = simulador._r_abertura(pos)
    if r and trail.get("on") and nt.get("desde"):
        velas = simulador._velas_1m(pos["ativo"], simulador._ms(nt["desde"]),
                                    simulador._ms(pd.Timestamp.now()))
        if velas:
            pico = max(float(v[2]) for v in velas) if d == 1 else min(float(v[3]) for v in velas)
            novo = simulador._trailing_novo_stop(pos, pico, d, trail)
            if novo is not None and pos["stop"] and (novo - pos["stop"]) * d > 0:
                if not _garantir_stop(c, pos, novo):
                    return
    _marcar_escrita(pos["ativo"])
    if nt.get("id"):
        c.cancelar(pos["ativo"], nt["id"], condicional=True)
    with db.conectar() as con:
        con.execute("UPDATE posicoes SET noite=NULL WHERE id=?", (pos["id"],))
    pos["noite"] = None


# ------------------------------------------------------------------------------ reconciliar

def _ratear(fs, quantidades):
    """Divide os negócios, em ordem de tempo, entre eventos de quantidade conhecida. O que
    sobrar depois do último evento vai numa lista a mais, no fim. Os alvos disparam do mais
    perto para o mais longe, então a ordem do tempo é a ordem dos alvos."""
    fila = [dict(f) for f in fs]
    partes = []
    for alvo_q in quantidades:
        parte, falta = [], float(alvo_q)
        while fila and falta > 1e-12:
            f = fila[0]
            q = float(f.get("qty") or 0)
            if q <= falta + 1e-12:
                parte.append(fila.pop(0))
                falta -= q
            else:                                   # um negócio que atravessa dois eventos
                frac = falta / q
                a = dict(f, qty=falta, taxa=(f.get("taxa") or 0) * frac, id=f"{f['id']}#a")
                fila[0] = dict(f, qty=q - falta, taxa=(f.get("taxa") or 0) * (1 - frac), id=f"{f['id']}#b")
                parte.append(a)
                falta = 0.0
        partes.append(parte)
    partes.append(fila)
    return partes


def _motivo_do_stop(pos, fs):
    d = _d(pos["direcao"])
    em_lucro = (pos["stop"] - pos["entrada"]) * d >= 0
    motivo = "trailing" if em_lucro else "stop"
    qf = sum(f.get("qty") or 0 for f in fs)
    if qf:
        px = sum((f.get("qty") or 0) * (f.get("preco") or 0) for f in fs) / qf
        if (pos["stop"] - px) * d > 0:              # executou pior que o gatilho ([P2-18])
            motivo += "-gap"
    return motivo


def _motivo_externo(c, pos, fs):
    """Fechamento que nenhuma ordem nossa fez: liquidação, redução forçada, ou alguém no
    aplicativo da corretora."""
    for f in fs:
        try:
            o = c.buscar_por_id(pos["ativo"], f.get("ordem_id"))
        except Exception:
            o = None
        coid = str((o or {}).get("client_oid") or "")
        if coid.startswith("autoclose"):
            return "liquidacao"
        if coid.startswith("adl_autoclose"):
            return "adl"
    return "externo"


def _disparou(c, ativo, coid):
    if not coid:
        return False
    try:
        o = c.buscar(ativo, coid, condicional=True)
    except Exception:
        return False
    return bool(o) and o.get("status") in ("disparada", "preenchida")


def _reduziu(c, pos, qty_ex):
    """A posição diminuiu (ou sumiu) na corretora sem o livro saber. Lança o que houve, com os
    negócios reais, na ordem: os alvos que dispararam, depois o resto (stop, trailing da noite,
    liquidação ou fechamento externo). Devolve True se lançou tudo."""
    ativo = pos["ativo"]
    delta = float(pos["qty"]) - float(qty_ex)
    fs = _fills_novos(c, ativo, pos["aberto_em"], C._FECHA[pos["direcao"]])
    lido = sum(f.get("qty") or 0 for f in fs)
    if lido < delta * (1 - 1e-6):
        n = _falta_fill.get(pos["id"], 0) + 1
        _falta_fill[pos["id"]] = n
        if n == 3:
            _divergencia(f"#{pos['id']} {ativo} diminuiu {delta:g} na corretora e os negócios "
                         f"lidos somam {lido:g}; esperando")
        if n < ESPERA_FILL_CICLOS:
            return False
        # Não pode ficar para sempre: posição fantasma ocupa vaga e risco. Lança com o que há.
        _divergencia(f"#{pos['id']} {ativo}: saída lançada SEM os negócios, pelo último preço")
        falta = delta - lido
        fs = fs + [{"id": f"sem-fill-{pos['id']}-{int(time.time())}", "ordem_id": None,
                    "simbolo": ativo, "lado": C._FECHA[pos["direcao"]], "qty": falta,
                    "preco": pos["preco_atual"], "taxa": 0.0, "taxa_moeda": "estimada",
                    "maker": False, "pnl_realizado": None, "ts": pd.Timestamp.now()}]
    plano = alvos.ler(pos) or {"niveis": []}
    tps = [(i, t) for i, t in enumerate(plano.get("niveis", []))
           if t.get("ext_id") and not t.get("feito") and _disparou(c, ativo, t.get("coid"))]
    partes = _ratear(fs, [float(t["qty"]) for _, t in tps])
    for (i, t), parte in zip(tps, partes):
        q = sum(f.get("qty") or 0 for f in parte)
        if q <= 0:
            continue
        qf = sum((f.get("qty") or 0) * (f.get("preco") or 0) for f in parte) / q
        t.update(feito=True, fill=qf, em=str(parte[-1].get("ts") or pd.Timestamp.now()))
        _lancar_saida(c, pos, parte, f"tp{i + 1}", plano, qty_fechada=q)
        if not _posicao(pos["id"]):
            break
    resto = partes[-1]
    if resto and _posicao(pos["id"]):
        q = sum(f.get("qty") or 0 for f in resto)
        try:
            nt = json.loads(pos["noite"]) if pos.get("noite") else {}
        except (TypeError, ValueError):
            nt = {}
        if _disparou(c, ativo, pos.get("stop_coid")):
            motivo = _motivo_do_stop(pos, resto)
        elif _disparou(c, ativo, nt.get("coid")):
            motivo = "trailing"
        else:
            motivo = _motivo_externo(c, pos, resto)
            if float(qty_ex) > 0:
                motivo += "-parcial"
        _lancar_saida(c, pos, resto, motivo, plano, qty_fechada=q)
    # Sobrou posição: o stop que está lá continua valendo. Ele é reduce-only com a quantidade
    # antiga, e reduce-only maior que a posição fecha só o que existe (regra 2 da Fase 1).
    vivo = _posicao(pos["id"])
    if vivo is None:                                # fechou inteira: limpa o que sobrou lá
        saude["fechadas_fora"] += 1
        _cancelar_condicionais(c, pos)
    elif 0 < abs(float(vivo["qty"]) - float(qty_ex)) <= 1e-6 * float(qty_ex):
        # A quantidade que sobrou é a que a corretora diz, até a última casa: a do livro saiu
        # de subtrações em ponto flutuante. Diferença maior que isso não é ruído, é divergência,
        # e fica para o ciclo seguinte medir.
        with db.conectar() as con:
            con.execute("UPDATE posicoes SET qty=? WHERE id=? AND status='aberta'",
                        (float(qty_ex), pos["id"]))
    return True


def _adotar(c, px, cfg):
    """Posição que existe na corretora e não no livro: entra no livro com os dados de lá, sem
    sinal, e ganha um stop a `corretora_stop_adocao` da entrada. O dono é avisado."""
    ativo, direcao = px["simbolo"], px["direcao"]
    d = _d(direcao)
    lev = float(px.get("alavancagem") or 1) or 1.0
    entrada, qty = float(px["entrada"]), float(px["qty"])
    stop = c.preco_valido(ativo, entrada * (1 - d * simulador._cfg_float(cfg, "corretora_stop_adocao", 0.03)))
    valor = qty * entrada / lev
    agora = str(pd.Timestamp.now())
    with simulador._abrir_lock:
        with db.conectar() as con:
            con.execute("INSERT INTO posicoes(ativo,direcao,entrada,valor_reais,alavancagem,stop,"
                        "preco_atual,pnl,aberto_em,status,stop_abertura,risco_abertura,corretora,"
                        "qty,qty_inicial,stop_seq,funding_pago) "
                        "VALUES(?,?,?,?,?,?,?,0,?,'aberta',?,?,?,?,?,0,0)",
                        (ativo, direcao, entrada, valor, lev, stop, px.get("mark") or entrada, agora,
                         stop, round(simulador._risco_posicao(valor, lev, entrada, stop), 4),
                         c.nome, qty, qty))
            pid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    saude["adotadas"] += 1
    # O aviso sai DEPOIS da tentativa, e diz o que aconteceu com o stop: "stop em X" antes de
    # ele existir seria o dono lendo uma proteção que talvez não esteja lá.
    try:
        _garantir_stop(c, _posicao(pid), stop)
        erro = None
    except Exception as e:
        erro = e
    p = _posicao(pid)
    _divergencia(f"posição {direcao} {ativo} qty {qty:g} existia na corretora e não no livro: "
                 f"adotada como #{pid}, " +
                 (f"stop em {p['stop']} na corretora" if p and p.get("stop_ext_id") else
                  "e FECHADA a mercado: o stop não entrou" if not p else
                  f"stop em {stop} AINDA NÃO colocado"
                  f"{f' ({type(erro).__name__})' if erro else ''}; o bot tenta de novo a cada ciclo"))
    return pid


def reconciliar(cfg=None):
    """Compara a corretora com o livro e conserta o LIVRO (regra 1). Roda no começo de cada
    ciclo, e é a primeira coisa que o processo faz ao subir: é ela que descobre o que encheu,
    fechou ou sumiu enquanto o servidor estava desligado.

    Try por item: uma posição que não reconcilia não tira as outras da conferência. Falha de
    rede na leitura inicial faz o ciclo inteiro falhar, e a conta para de abrir até a próxima
    reconciliação boa (`_bloqueio_entrada`)."""
    cfg = db.get_config() if cfg is None else cfg
    c = obter(cfg)
    with _lock:
        try:
            pxs = c.posicoes()
            abertas_ex = c.ordens_abertas()
            saldo = c.saldo()
        except Exception as e:
            saude["falhas"] += 1
            saude["ultimo_erro"] = f"{pd.Timestamp.now()} leitura: {type(e).__name__}: {str(e)[:140]}"
            # Chave recusada e limite de taxa não se resolvem sozinhos em um ciclo, e o dono
            # precisa saber POR QUÊ: "rede" num IP que mudou o manda esperar, quando só o
            # aplicativo da Binance age (revisão de 26/11).
            if isinstance(e, C.ChaveRecusada):
                _avisar_uma_vez("chave", "🔑 A Binance recusou a chave da conta real (IP de saída "
                                "mudou? chave revogada?). O bot não move stop nem fecha nada até "
                                "isso voltar; os stops que já estão lá continuam valendo. Confira "
                                f"no aplicativo da Binance. {str(e)[:120]}")
            elif isinstance(e, C.LimiteDeTaxa):
                _avisar_uma_vez("taxa", "⏸️ A Binance limitou as requisições da conta real; o bot "
                                f"para de chamar até o fim da pausa. {str(e)[:120]}")
            raise
        por_ativo = {(p["simbolo"], p["direcao"]): p for p in pxs}
        ids_abertos = {o["id"] for o in abertas_ex}
        with db.conectar() as con:
            livro = [dict(r) for r in con.execute(
                "SELECT * FROM posicoes WHERE status='aberta' AND corretora IS NOT NULL")]
            pend = [dict(r) for r in con.execute("SELECT * FROM ordens WHERE status='pendente'")]
        ativos_pend = {o["ativo"] for o in pend}
        # Alguma posição ficou sem conferir NESTE ciclo (pulada pela folga de leitura, saída que
        # espera o negócio aparecer, falha)? Então a carteira pode já mostrar um resultado que o
        # livro ainda vai lançar, e ajustar a banca por ela contaria a mesma perda duas vezes.
        incompleto = False
        for pos in livro:
            if _escrita_recente(pos["ativo"]):
                incompleto = True
                continue
            try:
                px = por_ativo.get((pos["ativo"], pos["direcao"]))
                qty_ex = float(px["qty"]) if px else 0.0
                if qty_ex < float(pos["qty"]) * (1 - 1e-9):
                    if not _reduziu(c, pos, qty_ex):
                        incompleto = True
                    continue
                if qty_ex > float(pos["qty"]) * (1 + 1e-9):
                    _aumentou(c, pos, px)
                    continue
                _falta_fill.pop(pos["id"], None)
                if not pos.get("stop_ext_id") or pos["stop_ext_id"] not in ids_abertos:
                    saude["stops_repostos"] += 1
                    log(f"#{pos['id']} {pos['ativo']}: sem stop aberto na corretora; repondo", "error")
                    pos["stop_ext_id"] = None       # o anterior não existe mais: coloca, não move
                    _garantir_stop(c, pos, pos["stop"])
            except Exception as e:
                incompleto = True
                saude["falhas"] += 1
                saude["ultimo_erro"] = (f"{pd.Timestamp.now()} #{pos['id']} {pos['ativo']}: "
                                        f"{type(e).__name__}: {str(e)[:140]}")
                log(f"reconciliar falhou #{pos['id']} {pos['ativo']}: {e}", "error")
        # posição lá sem linha aqui. Ativo com entrada pendente não é órfã: é ordem enchendo, e
        # quem a transforma em posição é o `processar_ordens` deste mesmo ciclo.
        no_livro = {(p["ativo"], p["direcao"]) for p in livro}
        for chave, px in por_ativo.items():
            if chave in no_livro or px["simbolo"] in ativos_pend or _escrita_recente(px["simbolo"]):
                continue
            if _dry(c):
                # Em dry_run nada é enviado: adotar poria no livro uma posição que o bot não
                # consegue proteger nem fechar. Avisa (uma vez por posição) e não toca.
                if chave not in _fora_do_livro:
                    _fora_do_livro.add(chave)
                    _divergencia(f"posição {px['direcao']} {px['simbolo']} qty {px['qty']:g} existe "
                                 "na corretora e não no livro. Com corretora_dry_run ligado o bot "
                                 "NÃO a adota nem protege: cuide dela no aplicativo")
                continue
            try:
                _adotar(c, px, cfg)
            except Exception as e:
                saude["falhas"] += 1
                log(f"adoção falhou {px['simbolo']}: {e}", "error")
        # ordem NOSSA aberta lá sem dono aqui: cancela. Ordem de outro (sem o nosso prefixo)
        # não se toca: só se avisa.
        _orfas(c, abertas_ex, cfg)
        _conferir_saldo(c, saldo, cfg, ajustar=not incompleto)
    guarda_total(cfg)
    _reconciliado["mono"] = time.monotonic()
    saude["reconciliado_em"] = str(pd.Timestamp.now())
    saude["reconciliacoes"] += 1
    saude["modo"] = c.nome
    return saude


def _aumentou(c, pos, px):
    """A posição CRESCEU na corretora (alguém somou pelo aplicativo). O livro adota a quantidade
    e o preço médio de lá, e o stop passa a valer para o tamanho novo."""
    qty, entrada = float(px["qty"]), float(px.get("entrada") or pos["entrada"])
    valor = qty * entrada / float(pos["alavancagem"])
    with db.conectar() as con:
        con.execute("UPDATE posicoes SET qty=?, entrada=?, valor_reais=? WHERE id=? AND status='aberta'",
                    (qty, entrada, valor, pos["id"]))
    _divergencia(f"#{pos['id']} {pos['ativo']} cresceu na corretora: {pos['qty']:g} -> {qty:g}; "
                 "o livro adotou")
    _garantir_stop(c, _posicao(pos["id"]), pos["stop"], forcar=True)


def _orfas(c, abertas_ex, cfg):
    with db.conectar() as con:
        livro = [dict(r) for r in con.execute(
            "SELECT * FROM posicoes WHERE status='aberta' AND corretora IS NOT NULL")]
        pend = [dict(r) for r in con.execute("SELECT * FROM ordens WHERE status='pendente'")]
    donos = set()
    for p in livro:
        donos.add(p.get("stop_ext_id"))
        for t in (alvos.ler(p) or {}).get("niveis", []):
            donos.add(t.get("ext_id"))
        try:
            donos.add((json.loads(p["noite"]) if p.get("noite") else {}).get("id"))
        except (TypeError, ValueError):
            pass
    for o in pend:
        donos.add(o.get("ordem_ext_id"))
        donos.add(o.get("stop_ext_id"))
    coids_pend = {o.get("client_oid") for o in pend} | {o.get("stop_coid") for o in pend}
    de_fora = [o for o in abertas_ex if o["id"] not in donos
               and o.get("client_oid") not in coids_pend and not _nosso(o.get("client_oid"), cfg)]
    saude["ordens_de_fora"] = len(de_fora)
    novas = [o for o in de_fora if o["id"] not in _ordens_de_fora]
    if novas:
        # Não se toca, mas se avisa: uma condicional reduce-only que sobrou de outro banco (ou
        # que alguém pôs à mão) dispara na PRÓXIMA posição do ativo sem o livro saber de onde veio.
        _ordens_de_fora.update(o["id"] for o in novas)
        _divergencia(f"{len(novas)} ordem(ns) aberta(s) na conta que não são deste livro ("
                     + ", ".join(f"{o.get('simbolo')} {o.get('tipo')}" for o in novas[:5])
                     + "). O bot não as toca; se não são suas, cancele no aplicativo")
    _ordens_de_fora.intersection_update({o["id"] for o in de_fora})
    for o in abertas_ex:
        if o["id"] in donos or o.get("client_oid") in coids_pend:
            continue
        if _escrita_recente(o.get("simbolo")):
            continue
        if not _nosso(o.get("client_oid"), cfg):
            continue                                # não é nossa: não se toca
        try:
            c.cancelar(o["simbolo"], o["id"], condicional=bool(o.get("condicional")))
            saude["orfas_canceladas"] += 1
            log(f"ordem órfã cancelada na corretora: {o.get('simbolo')} {o.get('tipo')} "
                f"{o.get('client_oid')}", "warning")
        except Exception as e:
            log(f"órfã {o.get('client_oid')} não cancelou: {e}", "error")


def _conferir_saldo(c, saldo, cfg, ajustar=True):
    """O livro não pode achar que tem mais dinheiro do que a conta tem. Se a CARTEIRA da
    corretora ficar abaixo da banca do livro por mais que a folga, saiu dinheiro por fora
    (saque, transferência, taxa que o livro não lançou): a banca desce até as duas baterem.
    Só desce.

    Carteira contra banca, e não equity contra equity: as duas são dinheiro REALIZADO. O
    resultado aberto fica fora de propósito. O da corretora é de agora e o do livro é o da
    última marcação: comparados, uma queda do mercado entre as duas leituras (ou a noite
    inteira, na primeira reconciliação da manhã) parecia dinheiro sumido, a banca descia, e
    logo depois a marcação descontava a mesma queda de novo.

    A carteira já pagou a taxa de entrada das posições abertas, que o livro só lança no
    fechamento: ela entra na conta. O funding das abertas também já saiu da carteira e só entra
    no livro no fechamento: quando a diferença passa da folga, ele é medido e descontado antes de
    concluir que saiu dinheiro (senão o fechamento o lançaria de novo, sobre a banca já baixada).

    `ajustar=False` quando alguma posição não fechou a conferência neste ciclo: a carteira pode
    já refletir uma saída que o livro ainda vai lançar. Lançada a saída, a banca desceria DUAS
    vezes pela mesma perda, e como a regra só desce, o erro ficaria para sempre e empurraria a
    conta para o teto de perda total (revisão de 26/11)."""
    cart = saldo.get("carteira")
    if cart is None:
        return
    with db.conectar() as con:
        con.execute("BEGIN")
        banca = con.execute("SELECT atual FROM banca WHERE id=1").fetchone()["atual"]
        taxas = con.execute("SELECT COALESCE(SUM(COALESCE(taxa_entrada,0)*entrada*qty),0) "
                            "FROM posicoes WHERE status='aberta' AND corretora IS NOT NULL"
                            ).fetchone()[0] or 0
    cart, esperada = float(cart), banca - taxas
    saude["saldo"] = {"carteira": round(cart, 2), "equity_corretora": saldo.get("equity"),
                      "banca_livro": round(banca, 2)}
    folga = max(1.0, 0.02 * banca)
    if not ajustar or cart >= esperada - folga:
        return
    with db.conectar() as con:
        abertas = [dict(r) for r in con.execute(
            "SELECT * FROM posicoes WHERE status='aberta' AND corretora IS NOT NULL")]
    funding = 0.0
    for p in abertas:
        f = _funding_real(c, p)
        if f is None:                               # sem medir o funding, não se conclui nada
            return
        funding += f
    if cart < esperada + funding - folga:
        nova = cart + taxas - funding
        with db.conectar() as con:
            con.execute("UPDATE banca SET atual=? WHERE id=1", (nova,))
        _divergencia(f"carteira na corretora ({cart:.2f}) abaixo da banca do livro "
                     f"({banca:.2f}): banca ajustada para {nova:.2f}")


# ------------------------------------------------------------------------------ pânico e troca

def panico(batida=None):
    """A metade do `/panico` que mora na corretora. O `auto_trade` já foi desligado por quem
    chama ([P1-7]). Cancela as entradas pendentes LÁ, fecha a mercado tudo o que o livro tem,
    e por fim varre a conta: qualquer posição que sobrar é fechada, qualquer ordem nossa é
    cancelada. Devolve o resumo; `falhas` nomeia o que ficou, inclusive posição que a releitura
    final ainda acha aberta.

    `batida` é chamada a cada item: o worker fica parado no `_lock` enquanto o pânico corre, e
    é ele quem alimenta o watchdog do systemd. Sem a batida, um pânico longo com a rede ruim
    passava dos 300 s e o systemd matava o processo no meio dele (revisão de 26/11)."""
    bate = batida or (lambda: None)
    c = obter()
    res = {"fechadas": 0, "pnl": 0.0, "ordens_canceladas": 0, "falhas": [], "varridas": []}
    with _lock:
        with db.conectar() as con:
            pend = [dict(r) for r in con.execute("SELECT * FROM ordens WHERE status='pendente'")]
        for o in pend:
            bate()
            try:
                _cancelar_entrada(c, o, "panico")
                res["ordens_canceladas"] += 1
            except Exception as e:
                res["falhas"].append({"ordem": o["id"], "ativo": o["ativo"],
                                      "erro": f"{type(e).__name__}: {str(e)[:120]}"})
        with db.conectar() as con:
            abertas = [dict(r) for r in con.execute(
                "SELECT * FROM posicoes WHERE status='aberta' AND corretora IS NOT NULL")]
        for p in abertas:
            bate()
            try:
                pnl = fechar(p, "panico")
                if pnl is not None:
                    res["pnl"] += pnl
                    res["fechadas"] += 1
            except Exception as e:
                res["falhas"].append({"id": p["id"], "ativo": p["ativo"],
                                      "erro": f"{type(e).__name__}: {str(e)[:120]}"})
        try:                                        # a varredura: o que o livro não conhecia
            for px in c.posicoes():
                bate()
                try:
                    ext = c.fechar_mercado(px["simbolo"], px["direcao"], px["qty"],
                                           _coid("x", f"p{int(time.time() * 1000) % 10 ** 9}"))
                    if ext.get("status") == "dry_run":      # nada saiu: não é "varrida"
                        raise ValueError("corretora_dry_run ligado: o fechamento NÃO foi enviado")
                    if not float(ext.get("preenchido") or 0) and ext.get("status") != "preenchida":
                        # aceita não é executada: só conta como varrida o que encheu
                        raise C.EnvioIncerto(f"fechamento voltou '{ext.get('status')}' sem executar")
                    c.cancelar_tudo(px["simbolo"])
                    # fechada, mas fora do livro: a reconciliação lança a saída se a linha existir
                    res["varridas"].append({"ativo": px["simbolo"], "direcao": px["direcao"],
                                            "qty": px["qty"]})
                    log(f"PÂNICO: {px['direcao']} {px['simbolo']} qty {px['qty']} fechada na "
                        "varredura da conta", "error")
                except C.OrdemRecusada as e:
                    if not _nada_a_reduzir(e):
                        res["falhas"].append({"ativo": px["simbolo"],
                                              "erro": f"varredura: recusado: {str(e)[:120]}"})
                        continue
                    # reduce-only recusado = não há o que reduzir: a leitura de posições estava
                    # um instante atrasada e esta acabou de ser fechada acima. Não é falha.
                    log(f"PÂNICO: varredura de {px['simbolo']} sem o que fechar ({e})", "warning")
                except Exception as e:
                    res["falhas"].append({"ativo": px["simbolo"],
                                          "erro": f"varredura: {type(e).__name__}: {str(e)[:120]}"})
            # A prova do pânico é a conta, não as respostas: o que ainda estiver aberto lá depois
            # de tudo isso é falha, mesmo que nenhuma chamada tenha levantado (revisão de 26/11).
            ja = {f.get("ativo") for f in res["falhas"]}
            for px in c.posicoes():
                if px["simbolo"] not in ja:
                    res["falhas"].append({"ativo": px["simbolo"],
                                          "erro": f"segue ABERTA na corretora depois do pânico "
                                                  f"({px['direcao']} qty {px['qty']:g})"})
            for o in c.ordens_abertas():
                if _nosso(o.get("client_oid")):
                    try:
                        c.cancelar(o["simbolo"], o["id"], condicional=bool(o.get("condicional")))
                    except Exception as e:          # ordem nossa que ficou viva: o resumo diz
                        res["falhas"].append({"ativo": o.get("simbolo"),
                                              "erro": f"ordem {o.get('tipo')} não cancelou: "
                                                      f"{type(e).__name__}: {str(e)[:100]}"})
        except Exception as e:
            res["falhas"].append({"erro": f"varredura da conta: {type(e).__name__}: {str(e)[:120]}"})
    res["pnl"] = round(res["pnl"], 2)
    return res


def trocar_modo(novo, cfg=None):
    """Valida a troca da config `corretora` e prepara o livro para o modo novo. Levanta
    ValueError com o motivo; quem grava a config é quem chamou (`POST /config`).

    A troca só acontece com o livro VAZIO de exposição (nenhuma posição, nenhuma ordem): mudar
    de corretora com posição aberta é o livro apontando para uma conta onde ela não está.
    Entrando num modo real, a banca do livro renasce em min(saldo da conta, `banca_alocada`)."""
    vigente = db.get_config()
    novo = str(novo).strip().lower()
    if novo == modo(vigente):
        return None
    cfg = {**vigente, **(cfg or {})}                # a config como VAI ficar (teto, dry_run, banca)
    if novo != "papel" and not habilitada():
        raise ValueError("'corretora': esta instância só opera em papel (a conta real é a que "
                         "sobe com CORRETORA_HABILITADA=1)")
    with db.conectar() as con:
        n_pos = con.execute("SELECT COUNT(*) FROM posicoes WHERE status='aberta'").fetchone()[0]
        n_ord = con.execute("SELECT COUNT(*) FROM ordens WHERE status='pendente'").fetchone()[0]
        n_trd = con.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    if n_pos or n_ord:
        raise ValueError(f"'corretora': há {n_pos} posição(ões) e {n_ord} ordem(ns) abertas; "
                         "feche tudo antes de trocar de corretora")
    if novo == "papel":
        # O livro está vazio; a CONTA também tem de estar. Sair para o papel com posição ou
        # ordem nossa viva na corretora é largar exposição que ninguém mais vai olhar.
        try:
            c = obter(vigente)
            n_px = len(c.posicoes())
            n_ox = sum(1 for o in c.ordens_abertas() if _nosso(o.get("client_oid"), vigente))
        except Exception as e:
            raise ValueError("'corretora': não deu para conferir a conta antes de voltar ao papel "
                             f"({type(e).__name__}: {str(e)[:100]}). Tente de novo")
        if n_px or n_ox:
            raise ValueError(f"'corretora': a conta na corretora ainda tem {n_px} posição(ões) e "
                             f"{n_ox} ordem(ns) do bot; feche e cancele lá antes de voltar ao papel")
        _cache.update(chave=None, obj=None)
        _reconciliado["mono"] = None
        return None
    if n_trd:
        raise ValueError("'corretora': o livro tem histórico de outro modo. Faça o reset em papel "
                         "antes de trocar (a curva e as métricas não misturam duas contas)")
    cfg["corretora"] = novo
    if _teste["obj"] is not None:
        c = _teste["obj"]
    else:
        try:
            c = C.obter(cfg)
        except C.ErroCorretora as e:
            raise ValueError(f"'corretora': {e}")
    try:
        saldo = c.saldo()
        if c.posicoes():
            raise ValueError("'corretora': a conta na corretora já tem posição aberta; feche lá "
                             "antes de ligar o bot nela")
        # Ordem aberta de antes (de outro banco, ou posta à mão): uma condicional reduce-only
        # esquecida dispara na primeira posição que o bot abrir naquele ativo.
        n_ox = len(c.ordens_abertas())
        if n_ox:
            raise ValueError(f"'corretora': a conta na corretora tem {n_ox} ordem(ns) aberta(s); "
                             "cancele lá antes de ligar o bot nela")
        # Com posição nos dois lados (hedge mode) a Binance recusa toda ordem sem `positionSide`.
        # Não abriria nada, mas cada sinal seria consumido por uma ordem rejeitada: melhor dizer
        # agora. None = não deu para ler, e aí quem diz é a primeira ordem.
        # Não lido também recusa: ligar o bot numa conta cujo modo não se conhece é descobrir
        # pela primeira ordem, com o sinal já consumido (revisão de 26/11).
        h = c.hedge()
        if h is not False:
            raise ValueError("'corretora': a conta está em Hedge Mode; o bot opera em One-way. "
                             "Troque em Preferências > Modo de posição, na Binance" if h else
                             "'corretora': não deu para ler o modo de posição da conta. Tente de novo")
        # Em Multi-Assets a Binance recusa margem isolada (-4168): nenhuma entrada passaria.
        m = c.multi_ativos()
        if m is not False:
            raise ValueError("'corretora': a conta está em Multi-Assets; o bot opera em margem "
                             "isolada, que exige Single-Asset. Troque em Preferências, na Binance"
                             if m else "'corretora': não deu para ler o modo de margem da conta "
                             "(Multi-Assets). Tente de novo")
    except C.ErroCorretora as e:
        raise ValueError(f"'corretora': {e}")
    except ValueError:
        raise
    except Exception as e:                          # rede: sem ler a conta, não se liga o bot nela
        raise ValueError(f"'corretora': não deu para ler a conta ({type(e).__name__}: {str(e)[:120]})")
    total = float(saldo.get("carteira") or saldo.get("total") or 0)
    banca = min(total, simulador._cfg_float(cfg, "banca_alocada", 200.0))
    if banca <= 0:
        raise ValueError("'corretora': a conta está sem saldo em USDT")
    with db.conectar() as con:
        con.execute("UPDATE banca SET inicial=?, atual=? WHERE id=1", (banca, banca))
        con.execute("DELETE FROM equity")
    _cache.update(chave=None, obj=None)
    _reconciliado["mono"] = None
    log(f"corretora: {modo(vigente)} -> {novo}; banca do livro {banca:.2f} USDT "
        f"(saldo na conta {total:.2f})", "warning")
    return {"banca": banca, "saldo": total}


# ------------------------------------------------------------------------------ linha de comando

def _cli(argv):
    """`python -m execucao estado|panico`, com o ambiente da conta R (`deploy/panico.sh` monta).

    É o caminho para quando o serviço não responde: fala direto com a corretora, usando o banco
    e a chave da conta. `estado` só lê. `panico` desliga o `auto_trade` ANTES de fechar ([P1-7]),
    cancela e fecha tudo; rodar duas vezes é seguro (todo fechamento é reduce-only)."""
    if len(argv) != 1 or argv[0] not in ("estado", "panico"):
        print("uso: python -m execucao estado|panico")
        return 2
    cfg = db.get_config()
    if not real(cfg):
        print(f"conta em papel (banco {db.DB}): nada a fazer na corretora")
        return 0
    c = obter(cfg)
    if argv[0] == "panico":
        db.set_config("auto_trade", "0", "execucao panico (linha de comando)")
        log("PÂNICO pela linha de comando: auto-trader desligado", "error")
        r = panico()
        print(json.dumps(r, ensure_ascii=False, default=str))
    pos, ords = c.posicoes(), c.ordens_abertas()
    with db.conectar() as con:
        livro = con.execute("SELECT COUNT(*) FROM posicoes WHERE status='aberta'").fetchone()[0]
    print(f"modo {c.nome} | na corretora: {len(pos)} posição(ões), {len(ords)} ordem(ns) | "
          f"no livro: {livro} posição(ões) aberta(s) | auto_trade={db.get_config().get('auto_trade')}")
    for p in pos:
        print(f"  {p['direcao']} {p['simbolo']} qty {p['qty']} entrada {p['entrada']}")
    return 0 if argv[0] == "estado" or not (pos or r["falhas"]) else 1


if __name__ == "__main__":
    import sys
    sys.exit(_cli(sys.argv[1:]))
