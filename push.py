"""[PUSH-1] Notificacao nativa no celular (Web Push), sem loja e sem Telegram.

O app instalado na tela de inicio (o PWA do `web/m.html`) se inscreve no servico de push do
proprio aparelho -- o da Apple no iPhone, o do Google no Android -- e entrega aqui o endereco
dessa inscricao. Quando algo acontece (abriu, encheu, fechou, TP parcial, trava diaria), este
modulo cifra a mensagem para aquele aparelho e a entrega ao servico de push, que a mostra como
notificacao do sistema. O servico so ve bytes cifrados (RFC 8291): quem le e o aparelho.

Tres regras, e o motivo de cada uma:

1. **Nunca no caminho do dinheiro.** `avisar()` so enfileira e volta; quem fala com a Apple e
   uma thread propria. Uma Apple lenta ou fora do ar nao pode atrasar o ciclo do worker nem
   fazer um `fechar()` levantar excecao depois de gravar o trade. Toda falha vira log.
2. **A chave nao mora no repositorio.** O repositorio e publico; a chave privada VAPID vem de
   `VAPID_PRIVATE` no `.env` (o mesmo que as contas A e B leem, entao uma chave serve as duas).
   Sem ela -- ou sem o `pywebpush` instalado no venv, porque o deploy nao roda `pip install` --
   o push fica desligado e diz por que, em vez de derrubar o import da plataforma.
3. **So entrega para servico de push conhecido.** O backend faz POST no endereco que o aparelho
   informou. Sem lista, quem tivesse a senha do painel poderia apontar esse POST para dentro da
   rede do dl380. Endereco fora da lista e recusado na inscricao.
4. **Quem decide o que toca e o aparelho.** [PUSH-2] Cada inscricao guarda as proprias
   preferencias (`prefs`): cada tipo de aviso vai "na hora", "so no resumo" ou "desligado"; um
   resumo periodico (de N em N horas, alinhado ao relogio) conta o resultado do dia e os trades
   da janela; e um horario silencioso segura o que nao e risco -- so a trava atravessa. O resumo
   e lido do BANCO, nao de uma fila em memoria: deploy ou queda no meio da janela nao perde trade.

Gerar o par de chaves (uma vez, e colar as duas linhas no `.env` do dl380):

    python -m push chaves
"""
import base64
import json
import os
import queue
import sys
import threading
import time
from urllib.parse import urlparse

import pandas as pd

import db
from logbot import log

# Hosts dos servicos de push dos navegadores. Sufixo: `web.push.apple.com` e o da Apple hoje,
# e a Apple ja trocou de subdominio antes; o Google entrega por `fcm.googleapis.com`.
HOSTS_PUSH = ("push.apple.com", "fcm.googleapis.com", "push.services.mozilla.com",
              "notify.windows.com")

# Aviso que nao chega em 12 h perdeu o sentido (um "abriu" de ontem a noite so confunde).
TTL_S = 12 * 3600
TIMEOUT_S = 10
FILA_MAX = 200
TIQUE_S = 60                     # de quanto em quanto tempo a thread olha se algum resumo venceu

# [PUSH-2] Preferencias por aparelho. `entrada` cobre abriu a mercado e ordem maker preenchida:
# para quem le no celular as duas sao "entrei na posicao". Aparelho inscrito antes do [PUSH-2]
# nao tem `prefs` e fica no padrao, que e exatamente o comportamento de antes: tudo na hora.
TIPOS = ("entrada", "parcial", "fechou", "trava")
MODOS = ("na_hora", "resumo", "off")
RESUMO_H = (0, 1, 2, 3, 4, 6, 8, 12, 24)    # divisores de 24: o resumo cai sempre na mesma hora
PREFS_PADRAO = {"entrada": "na_hora", "parcial": "na_hora", "fechou": "na_hora",
                "trava": "na_hora", "resumo_h": 0, "silencio": None}
RESUMO_LINHAS = 6                # trades listados no corpo; o resto vira "e mais N"

_fila = queue.Queue(maxsize=FILA_MAX)
_thread = None
_thread_lock = threading.Lock()


# ---------------------------------------------------------------- chaves e estado

def chave_publica():
    return (os.environ.get("VAPID_PUBLIC") or "").strip() or None


def _chave_privada():
    return (os.environ.get("VAPID_PRIVATE") or "").strip() or None


def _contato():
    # A Apple exige `sub` (mailto: ou https:). Nada pessoal aqui: o endereco do proprio painel.
    return (os.environ.get("VAPID_SUB") or "https://cripto-quant-dashboard.vercel.app").strip()


def estado():
    """(ativo, motivo). `motivo` e o texto que o app mostra quando o push esta desligado."""
    if not chave_publica() or not _chave_privada():
        return False, "o backend ainda nao tem a chave de push (VAPID_PUBLIC e VAPID_PRIVATE no .env)"
    try:
        import pywebpush  # noqa: F401
    except Exception:
        return False, "o backend ainda nao tem a biblioteca de push (pip install -r requirements.txt)"
    return True, ""


def _conta():
    return (os.environ.get("CONTA") or "A").strip().upper()


# ---------------------------------------------------------------- inscricoes

def endereco_valido(endpoint):
    try:
        u = urlparse(str(endpoint or ""))
    except Exception:
        return False
    host = (u.hostname or "").lower()
    return (u.scheme == "https" and bool(host)
            and any(host == h or host.endswith("." + h) for h in HOSTS_PUSH))


def _b64ok(s, minimo):
    try:
        s = str(s)
        return len(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))) >= minimo
    except Exception:
        return False


def inscrever(endpoint, p256dh, auth, ua=""):
    """Grava (ou renova) a inscricao de um aparelho. Levanta ValueError se ela nao serve."""
    if not endereco_valido(endpoint):
        raise ValueError("endereco de push desconhecido: so servicos de push de navegador")
    if not _b64ok(p256dh, 65) or not _b64ok(auth, 16):
        raise ValueError("chaves da inscricao invalidas")
    agora = str(pd.Timestamp.now())
    with db.conectar() as c:
        c.execute("INSERT INTO push_inscricoes(endpoint,p256dh,auth,ua,criado_em,falhas) "
                  "VALUES(?,?,?,?,?,0) ON CONFLICT(endpoint) DO UPDATE SET "
                  "p256dh=excluded.p256dh, auth=excluded.auth, ua=excluded.ua, falhas=0",
                  (endpoint, p256dh, auth, (ua or "")[:200], agora))
        return c.execute("SELECT COUNT(*) FROM push_inscricoes").fetchone()[0]


def sair(endpoint):
    with db.conectar() as c:
        return c.execute("DELETE FROM push_inscricoes WHERE endpoint=?", (endpoint,)).rowcount


def inscricoes():
    with db.conectar() as c:
        subs = [dict(r) for r in c.execute("SELECT * FROM push_inscricoes ORDER BY criado_em")]
    for x in subs:
        x["prefs"] = _ler_prefs(x.get("prefs"))
    return subs


# ---------------------------------------------------------------- [PUSH-2] preferencias

def _ler_prefs(bruto):
    """O que esta gravado, completado pelo padrao. Gravado ilegivel vale o padrao: preferencia
    corrompida nao pode calar o aparelho nem derrubar o envio dos outros."""
    p = dict(PREFS_PADRAO)
    try:
        p.update(normalizar_prefs(json.loads(bruto)) if bruto else {})
    except Exception:
        pass
    return p


def normalizar_prefs(d):
    """Valida o que o app mandou. Chave desconhecida ou valor fora do catalogo -> ValueError
    (mesmo espirito do catalogo do POST /config: recusa, nao adivinha). Chave ausente fica de
    fora e o padrao a completa na leitura."""
    if not isinstance(d, dict):
        raise ValueError("preferencias tem que ser um objeto")
    out = {}
    for k, v in d.items():
        if k in TIPOS:
            if v not in MODOS:
                raise ValueError(f"{k}: use um de {', '.join(MODOS)}")
            out[k] = v
        elif k == "resumo_h":
            if isinstance(v, bool) or not isinstance(v, int) or v not in RESUMO_H:
                raise ValueError(f"resumo_h: use um de {', '.join(map(str, RESUMO_H))} (0 desliga)")
            out[k] = v
        elif k == "silencio":
            if v is None:
                out[k] = None
                continue
            if not isinstance(v, dict) or set(v) != {"de", "ate"}:
                raise ValueError('silencio: {"de": hora, "ate": hora} ou null')
            de, ate = v["de"], v["ate"]
            if any(isinstance(x, bool) or not isinstance(x, int) or not 0 <= x <= 23 for x in (de, ate)):
                raise ValueError("silencio: horas inteiras de 0 a 23")
            if de == ate:
                raise ValueError("silencio: inicio e fim iguais")
            out[k] = {"de": de, "ate": ate}
        else:
            raise ValueError(f"preferencia desconhecida: {k}")
    return out


def salvar_prefs(endpoint, novas):
    """Mescla `novas` (validadas) nas do aparelho. Devolve as prefs completas, ou None se o
    aparelho nao esta inscrito nesta conta."""
    novas = normalizar_prefs(novas)
    with db.conectar() as c:
        r = c.execute("SELECT prefs FROM push_inscricoes WHERE endpoint=?", (endpoint,)).fetchone()
        if r is None:
            return None
        p = _ler_prefs(r["prefs"])
        mudou_intervalo = novas.get("resumo_h", p["resumo_h"]) != p["resumo_h"]
        p.update(novas)
        guardar = json.dumps({k: p[k] for k in PREFS_PADRAO})
        # Trocar o intervalo recomeca a contagem: sem isso, ligar o resumo as 15h10 dispararia
        # um resumo no minuto seguinte (a janela "venceu" desde sempre), e ninguem pediu um agora.
        if mudou_intervalo:
            c.execute("UPDATE push_inscricoes SET prefs=?, ultimo_resumo=? WHERE endpoint=?",
                      (guardar, str(pd.Timestamp.now()), endpoint))
        else:
            c.execute("UPDATE push_inscricoes SET prefs=? WHERE endpoint=?", (guardar, endpoint))
    return p


def em_silencio(prefs, agora):
    s = prefs.get("silencio")
    if not s:
        return False
    h, de, ate = agora.hour, s["de"], s["ate"]
    return de <= h < ate if de < ate else (h >= de or h < ate)


def quer_agora(prefs, tipo, agora):
    """Este aparelho quer ESTE aviso AGORA? `tipo=None` (o teste) sempre passa. No silencio so a
    trava atravessa: e o aviso de risco, e o que fica para o resumo nao se perde."""
    if tipo is None:
        return True
    if prefs.get(tipo, "na_hora") != "na_hora":
        return False
    return tipo == "trava" or not em_silencio(prefs, agora)


# ---------------------------------------------------------------- envio

def _mensagem(titulo, corpo, url, tag):
    if _conta() != "A":
        titulo = f"Conta {_conta()} · {titulo}"
    return json.dumps({"titulo": titulo, "corpo": corpo, "url": url or "#painel",
                       "tag": tag or ""}, ensure_ascii=False)


def enviar_agora(titulo, corpo, url="#painel", tag=None, so=None, tipo=None):
    """Entrega SINCRONA a cada aparelho inscrito (ou so ao `endpoint` em `so`) que quer este
    `tipo` de aviso agora ([PUSH-2]; `tipo=None` e o teste, que vai sempre).

    Devolve {"ok": n, "falhas": n, "removidas": n}. Inscricao que o servico diz que morreu
    (404/410: app desinstalado, permissao retirada) sai do banco na hora; outra falha so conta.
    """
    ativo, motivo = estado()
    res = {"ok": 0, "falhas": 0, "removidas": 0}
    if not ativo:
        res["motivo"] = motivo
        return res
    dados = _mensagem(titulo, corpo, url, tag)
    agora = pd.Timestamp.now()
    for s in inscricoes():
        if (so is None or s["endpoint"] == so) and quer_agora(s["prefs"], tipo, agora):
            res[_entregar(s, dados)] += 1
    return res


def _entregar(s, dados):
    """Um aparelho, uma mensagem. Devolve a chave do placar: "ok", "falhas" ou "removidas"."""
    from pywebpush import WebPushException, webpush
    info = {"endpoint": s["endpoint"], "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}}
    try:
        webpush(info, data=dados, vapid_private_key=_chave_privada(),
                vapid_claims={"sub": _contato()}, ttl=TTL_S, timeout=TIMEOUT_S,
                headers={"Urgency": "high"})
        with db.conectar() as c:
            c.execute("UPDATE push_inscricoes SET falhas=0, ultimo_ok=? WHERE endpoint=?",
                      (str(pd.Timestamp.now()), s["endpoint"]))
        return "ok"
    except WebPushException as e:
        st = getattr(getattr(e, "response", None), "status_code", None)
        if st in (404, 410):
            sair(s["endpoint"])
            log(f"push: inscricao expirada removida ({st})", "warning")
            return "removidas"
        _contar_falha(s["endpoint"])
        log(f"push falhou ({st}): {str(e)[:200]}", "warning")
        return "falhas"
    except Exception as e:
        _contar_falha(s["endpoint"])
        log(f"push falhou: {str(e)[:200]}", "warning")
        return "falhas"


def _contar_falha(endpoint):
    try:
        with db.conectar() as c:
            c.execute("UPDATE push_inscricoes SET falhas=falhas+1 WHERE endpoint=?", (endpoint,))
    except Exception:
        pass


def _laco():
    ultimo_tique = 0.0
    while True:
        try:
            item = _fila.get(timeout=TIQUE_S)
        except queue.Empty:
            item = None
        if item is not None:
            try:
                enviar_agora(*item)
            except Exception as e:                   # nada mata a thread de envio
                log(f"push: erro inesperado no envio: {e}", "warning")
            finally:
                _fila.task_done()
        # [PUSH-2] o relogio do resumo roda AQUI, na thread do push, e nao no ciclo do worker:
        # montar o resumo le o banco, e nada disso pode atrasar uma marcacao de stop.
        if time.monotonic() - ultimo_tique >= TIQUE_S:
            ultimo_tique = time.monotonic()
            try:
                resumos_vencidos()
            except Exception as e:
                log(f"push: resumo falhou: {e}", "warning")


def _garantir_thread():
    global _thread
    with _thread_lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_laco, name="push", daemon=True)
            _thread.start()


def iniciar():
    """[PUSH-2] Sobe a thread no boot (lifespan), para o resumo das 15h sair mesmo num dia sem
    trade nenhum. Sem chave, no-op; nunca levanta."""
    try:
        if estado()[0]:
            _garantir_thread()
            return True
    except Exception as e:
        log(f"push: thread nao subiu: {e}", "warning")
    return False


def avisar(titulo, corpo, url="#painel", tag=None, tipo=None):
    """Enfileira um aviso e volta na hora. Nunca levanta, nunca bloqueia o chamador.

    `tipo` ([PUSH-2]: entrada, parcial, fechou, trava) e o que cada aparelho filtra nas proprias
    preferencias, na thread de envio. Sem chave/biblioteca, ou sem nenhum aparelho inscrito, e
    no-op (sem thread, sem rede)."""
    try:
        if not estado()[0]:
            return False
        with db.conectar() as c:
            if not c.execute("SELECT 1 FROM push_inscricoes LIMIT 1").fetchone():
                return False
        _garantir_thread()
        _fila.put_nowait((titulo, corpo, url, tag, None, tipo))
        return True
    except queue.Full:
        log("push: fila cheia, aviso descartado", "warning")
        return False
    except Exception as e:
        log(f"push: aviso nao enfileirado: {e}", "warning")
        return False


# ---------------------------------------------------------------- [PUSH-2] resumo periodico

def inicio_do_bloco(agora, h):
    """Comeco do bloco de `h` horas em que `agora` cai, alinhado a meia-noite: de 3 em 3 h os
    resumos saem as 0, 3, 6, ..., 21 h, e nao "3 h depois de quando voce ligou"."""
    return agora.normalize() + pd.Timedelta(hours=(agora.hour // h) * h)


def resumo_vencido(prefs, ultimo, agora):
    h = prefs.get("resumo_h") or 0
    if not h or em_silencio(prefs, agora):
        return False
    return ultimo is None or pd.Timestamp(ultimo) < inicio_do_bloco(agora, h)


def resumos_vencidos(agora=None):
    """Manda o resumo a cada aparelho cujo bloco virou. Marca `ultimo_resumo` ANTES de entregar:
    se a Apple falhar, o proximo resumo vem no proximo bloco, e nao um por minuto."""
    if not estado()[0]:
        return 0
    agora = agora or pd.Timestamp.now()
    n = 0
    for s in inscricoes():
        p = s["prefs"]
        if not resumo_vencido(p, s.get("ultimo_resumo"), agora):
            continue
        ini = (pd.Timestamp(s["ultimo_resumo"]) if s.get("ultimo_resumo")
               else inicio_do_bloco(agora, p["resumo_h"]) - pd.Timedelta(hours=p["resumo_h"]))
        with db.conectar() as c:
            c.execute("UPDATE push_inscricoes SET ultimo_resumo=? WHERE endpoint=?",
                      (str(agora), s["endpoint"]))
        _entregar(s, _mensagem(*montar_resumo(p, ini, agora), "#painel", "resumo"))
        n += 1
    return n


def enviar_resumo_agora(endpoint):
    """O botao "ver um resumo agora" do app: a janela e desde o ultimo resumo (ou o ultimo
    intervalo), e NAO mexe no relogio -- o agendado sai na hora de sempre."""
    res = {"ok": 0, "falhas": 0, "removidas": 0}
    ativo, motivo = estado()
    if not ativo:
        return {**res, "motivo": motivo}
    s = next((x for x in inscricoes() if x["endpoint"] == endpoint), None)
    if s is None:
        return {**res, "motivo": "este aparelho nao esta inscrito nesta conta"}
    agora = pd.Timestamp.now()
    ini = (pd.Timestamp(s["ultimo_resumo"]) if s.get("ultimo_resumo")
           else agora - pd.Timedelta(hours=s["prefs"]["resumo_h"] or 3))
    res[_entregar(s, _mensagem(*montar_resumo(s["prefs"], ini, agora), "#painel", "resumo"))] += 1
    return res


def resultado_dia(data, agora=None):
    """P&L de um dia pela MESMA regua da trava diaria (`simulador.guarda_risco`): equity de agora
    (ou do inicio do dia seguinte, para dia passado) menos o equity do inicio do dia. Somar so o
    realizado contaria como bom um dia com stop aberto (22/08: +34,68 realizados, -80,34 de equity)."""
    agora = agora or pd.Timestamp.now()
    d = str(pd.Timestamp(data).date())
    prox = str((pd.Timestamp(data) + pd.Timedelta(days=1)).date())
    um = "SELECT equity_total FROM equity WHERE substr(ts,1,10)=? ORDER BY rowid {} LIMIT 1"
    with db.conectar() as c:
        ini = c.execute(um.format("ASC"), (d,)).fetchone()
        realizado = c.execute("SELECT COALESCE(SUM(pnl_reais),0) FROM trades "
                              "WHERE substr(fechado_em,1,10)=?", (d,)).fetchone()[0] or 0
        n = c.execute("SELECT COUNT(*) FROM trades WHERE substr(fechado_em,1,10)=?", (d,)).fetchone()[0]
        unreal = c.execute("SELECT COALESCE(SUM(pnl),0) FROM posicoes "
                           "WHERE status='aberta'").fetchone()[0] or 0
        abertas = c.execute("SELECT COUNT(*) FROM posicoes WHERE status='aberta'").fetchone()[0]
        b = c.execute("SELECT atual FROM banca WHERE id=1").fetchone()
        banca = (b[0] if b else 0) or 0
        if d == str(agora.date()):
            fim = banca + unreal
        else:
            f = c.execute(um.format("ASC"), (prox,)).fetchone() or c.execute(um.format("DESC"), (d,)).fetchone()
            fim = f[0] if f else None
    pnl = (fim - ini[0]) if (ini and fim is not None) else realizado
    return {"pnl": round(pnl, 2), "realizado": round(realizado, 2), "aberto": round(unreal, 2),
            "trades": n, "abertas": abertas}


def _eventos(prefs, ini, fim):
    """Entradas e saidas da janela (ini, fim], lidas do banco, ja filtradas pelas prefs."""
    a, b = str(ini), str(fim)
    ev = []
    with db.conectar() as c:
        if prefs.get("entrada") != "off":
            for r in c.execute("SELECT ativo,direcao,valor_reais,alavancagem,aberto_em FROM posicoes "
                               "WHERE aberto_em>? AND aberto_em<=?", (a, b)):
                ev.append((r["aberto_em"], f"↗ Entrou {r['direcao']} {par(r['ativo'])} · "
                                           f"{brl(r['valor_reais'])} a {float(r['alavancagem']):g}x"))
        for r in c.execute("SELECT ativo,direcao,pnl_reais,motivo_saida,aberto_em,fechado_em FROM trades "
                           "WHERE fechado_em>? AND fechado_em<=?", (a, b)):
            # Parcial = sobrou pedaco da mesma posicao: ela segue aberta, ou fechou DEPOIS. A
            # posicao e (ativo, aberto_em): o trade da parcial copia o aberto_em da posicao.
            parcial = bool(
                c.execute("SELECT 1 FROM posicoes WHERE ativo=? AND aberto_em=? AND status='aberta'",
                          (r["ativo"], r["aberto_em"])).fetchone()
                or c.execute("SELECT 1 FROM trades WHERE ativo=? AND aberto_em=? AND fechado_em>?",
                             (r["ativo"], r["aberto_em"], r["fechado_em"])).fetchone())
            if prefs.get("parcial" if parcial else "fechou") == "off":
                continue
            pnl = r["pnl_reais"] or 0
            ic = "✓" if pnl > 0 else "✕" if pnl < 0 else "·"
            ev.append((r["fechado_em"], f"{ic} {money(pnl)} · {r['direcao']} {par(r['ativo'])} · "
                                        f"{motivo(r['motivo_saida'])}{' (parcial)' if parcial else ''}"))
    ev.sort(key=lambda x: x[0])
    return [t for _, t in ev]


def _hora(ts):
    return f"{ts.hour}h" if ts.minute == 0 else f"{ts.hour}h{ts.minute:02d}"


def montar_resumo(prefs, ini, agora):
    """(titulo, corpo) do resumo. Primeira linha = o dinheiro do dia (o que a tela de bloqueio
    mostra inteiro); depois os trades da janela; por ultimo, o que esta aberto agora."""
    ini, agora = pd.Timestamp(ini), pd.Timestamp(agora)
    hoje = resultado_dia(agora, agora)
    linhas = [f"Hoje: {money(hoje['pnl'])} · realizado {money(hoje['realizado'])} · "
              f"aberto {money(hoje['aberto'])}"]
    if ini.date() < agora.date():          # a janela atravessou a meia-noite: o dia que fechou
        ontem = resultado_dia(agora - pd.Timedelta(days=1), agora)
        linhas.append(f"Ontem: {money(ontem['pnl'])} em {ontem['trades']} "
                      f"{'trade' if ontem['trades'] == 1 else 'trades'}")
    ev = _eventos(prefs, ini, agora)
    if len(ev) > RESUMO_LINHAS:            # os mais recentes ficam; os de antes viram uma linha
        ev = [f"… e mais {len(ev) - RESUMO_LINHAS + 1} antes"] + ev[-(RESUMO_LINHAS - 1):]
    linhas += ev or [f"Nenhum trade desde as {_hora(ini)}"]
    rodape = f"{hoje['abertas']} {'posição aberta' if hoje['abertas'] == 1 else 'posições abertas'}"
    if prefs.get("trava") != "off" and db.get_config().get("trava_dia_em") == str(agora.date()):
        rodape += " · trava diária acionada 🛑"
    linhas.append(rodape)
    # Comemora so lucro (mesma regra dos outros avisos); dia no vermelho tem titulo neutro.
    titulo = f"Resumo das {_hora(agora)}" + (" · dia no verde 💰" if hoje["pnl"] > 0 else "")
    return titulo, "\n".join(linhas)


# ---------------------------------------------------------------- texto dos avisos

def brl(v):
    """R$ no formato do painel: R$ 1.234,56 (sinal so quando pedido por `money`)."""
    s = f"{abs(float(v)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if float(v) < 0 else "") + "R$ " + s


def money(v):
    return ("+" if float(v) > 0 else "") + brl(v)


_MOTIVOS = {"manual": "fechada por você", "stop": "bateu o stop",
            "trailing": "saiu pelo trailing", "liquidacao": "liquidada",
            "panico": "fechada no pânico", "auto-saida": "saída automática do Apollo"}


def motivo(m):
    """O `motivo` gravado no trade, em português de gente ("tp2" -> "bateu o TP2")."""
    m = str(m or "")
    if m.startswith("tp") and m[2:].isdigit():
        return "bateu o TP" + m[2:]
    return _MOTIVOS.get(m, m.replace("_", " ") or "fechada")


# ---------------------------------------------------------------- o estilo dos avisos
# Pedido do dono (13/11): "no estilo da Utmify". Título curto que comemora ou alerta, com um
# emoji, e o DINHEIRO na primeira palavra do corpo -- é o que a tela de bloqueio mostra inteiro.
# Comemoração só para lucro: perda tem título neutro e o valor com sinal, sem maquiagem
# (CLAUDE.md, cabeçalho). Cada função devolve (título, corpo).

def msg_abriu(direcao, ativo, valor, lev, preco):
    return ("Nova posição aberta 🚀",
            f"{direcao} {par(ativo)} · {brl(valor)} a {lev}x · entrada {px(preco)}")


def msg_ordem(direcao, ativo, valor, lev, preco):
    return ("Ordem executada ✅",
            f"{direcao} {par(ativo)} · {brl(valor)} a {lev}x · entrada {px(preco)} (maker)")


def msg_fechou(direcao, ativo, pnl, m):
    if m == "liquidacao":
        titulo = "Posição liquidada ⚠️"
    elif pnl > 0:
        titulo = "Lucro no bolso! 💰"
    elif pnl < 0:
        titulo = "Posição fechada no vermelho 🔻"
    else:
        titulo = "Posição fechada"
    rot = "Lucro" if pnl > 0 else "Resultado"
    return titulo, f"{rot}: {money(pnl)} · {direcao} {par(ativo)} · {motivo(m)}"


def msg_parcial(direcao, ativo, pnl, m, frac):
    titulo = "Lucro parcial no bolso! 💸" if pnl > 0 else "Parcial realizada"
    rot = "Lucro" if pnl > 0 else "Resultado"
    return titulo, (f"{rot}: {money(pnl)} · {motivo(m)} com {frac:.0%} de {direcao} {par(ativo)}; "
                    "o resto segue com stop")


def msg_trava(pnl_dia, limite):
    return ("Trava diária acionada 🛑",
            f"Perda do dia: {brl(pnl_dia)} (limite {brl(limite)}) · sem novas entradas até a virada")


MSG_TESTE = ("Notificações ligadas! 🔔",
             "É assim que o Apollux avisa cada lucro, entrada e stop.")


def par(ativo):
    return str(ativo).replace("/", "").replace(":USDT", "")


def px(v):
    """Preco com as mesmas casas do painel (api.js pxCasas)."""
    v = float(v)
    a = abs(v)
    d = 1 if a >= 10000 else 2 if a >= 1000 else 3 if a >= 10 else 4 if a >= 1 else 5 if a >= 0.01 else 7
    s = f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s


# ---------------------------------------------------------------- linha de comando

def gerar_chaves():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    k = ec.generate_private_key(ec.SECP256R1())
    priv = k.private_numbers().private_value.to_bytes(32, "big")
    pub = k.public_key().public_bytes(serialization.Encoding.X962,
                                      serialization.PublicFormat.UncompressedPoint)
    b = lambda x: base64.urlsafe_b64encode(x).rstrip(b"=").decode()  # noqa: E731
    return b(pub), b(priv)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "chaves":
        pub, priv = gerar_chaves()
        print("# cole no .env do dl380 (as contas A e B leem o mesmo arquivo). NAO commite.")
        print(f"VAPID_PUBLIC={pub}")
        print(f"VAPID_PRIVATE={priv}")
    else:
        print(__doc__)
