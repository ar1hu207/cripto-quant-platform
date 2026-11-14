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

Gerar o par de chaves (uma vez, e colar as duas linhas no `.env` do dl380):

    python -m push chaves
"""
import base64
import json
import os
import queue
import sys
import threading
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
        return [dict(r) for r in c.execute("SELECT * FROM push_inscricoes ORDER BY criado_em")]


# ---------------------------------------------------------------- envio

def _mensagem(titulo, corpo, url, tag):
    if _conta() != "A":
        titulo = f"Conta {_conta()} · {titulo}"
    return json.dumps({"titulo": titulo, "corpo": corpo, "url": url or "#painel",
                       "tag": tag or ""}, ensure_ascii=False)


def enviar_agora(titulo, corpo, url="#painel", tag=None, so=None):
    """Entrega SINCRONA a cada aparelho inscrito (ou so ao `endpoint` em `so`).

    Devolve {"ok": n, "falhas": n, "removidas": n}. Inscricao que o servico diz que morreu
    (404/410: app desinstalado, permissao retirada) sai do banco na hora; outra falha so conta.
    """
    ativo, motivo = estado()
    res = {"ok": 0, "falhas": 0, "removidas": 0}
    if not ativo:
        res["motivo"] = motivo
        return res
    from pywebpush import WebPushException, webpush
    dados = _mensagem(titulo, corpo, url, tag)
    alvo = [s for s in inscricoes() if so is None or s["endpoint"] == so]
    for s in alvo:
        info = {"endpoint": s["endpoint"], "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}}
        try:
            webpush(info, data=dados, vapid_private_key=_chave_privada(),
                    vapid_claims={"sub": _contato()}, ttl=TTL_S, timeout=TIMEOUT_S,
                    headers={"Urgency": "high"})
            res["ok"] += 1
            with db.conectar() as c:
                c.execute("UPDATE push_inscricoes SET falhas=0, ultimo_ok=? WHERE endpoint=?",
                          (str(pd.Timestamp.now()), s["endpoint"]))
        except WebPushException as e:
            st = getattr(getattr(e, "response", None), "status_code", None)
            if st in (404, 410):
                sair(s["endpoint"])
                res["removidas"] += 1
                log(f"push: inscricao expirada removida ({st})", "warning")
            else:
                res["falhas"] += 1
                _contar_falha(s["endpoint"])
                log(f"push falhou ({st}): {str(e)[:200]}", "warning")
        except Exception as e:
            res["falhas"] += 1
            _contar_falha(s["endpoint"])
            log(f"push falhou: {str(e)[:200]}", "warning")
    return res


def _contar_falha(endpoint):
    try:
        with db.conectar() as c:
            c.execute("UPDATE push_inscricoes SET falhas=falhas+1 WHERE endpoint=?", (endpoint,))
    except Exception:
        pass


def _laco():
    while True:
        item = _fila.get()
        try:
            enviar_agora(*item)
        except Exception as e:                       # nada mata a thread de envio
            log(f"push: erro inesperado no envio: {e}", "warning")
        finally:
            _fila.task_done()


def avisar(titulo, corpo, url="#painel", tag=None):
    """Enfileira um aviso e volta na hora. Nunca levanta, nunca bloqueia o chamador.

    Sem chave/biblioteca, ou sem nenhum aparelho inscrito, e no-op (sem thread, sem rede)."""
    global _thread
    try:
        if not estado()[0]:
            return False
        with db.conectar() as c:
            if not c.execute("SELECT 1 FROM push_inscricoes LIMIT 1").fetchone():
                return False
        with _thread_lock:
            if _thread is None or not _thread.is_alive():
                _thread = threading.Thread(target=_laco, name="push", daemon=True)
                _thread.start()
        _fila.put_nowait((titulo, corpo, url, tag))
        return True
    except queue.Full:
        log("push: fila cheia, aviso descartado", "warning")
        return False
    except Exception as e:
        log(f"push: aviso nao enfileirado: {e}", "warning")
        return False


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
