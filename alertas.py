"""
Sprint 7 - Alertas Telegram (OPCIONAL). Se telegram_token e telegram_chat_id
estiverem no config, manda mensagem; senão, no-op. Usa urllib (sem dependência extra).

Pra ativar: defina no banco (ou via POST /config):
  telegram_token   = token do seu bot (criado no @BotFather)
  telegram_chat_id = seu chat id (do @userinfobot)
"""
import urllib.parse
import urllib.request

import db
from logbot import log


def enviar(msg):
    cfg = db.get_config()
    token = (cfg.get("telegram_token") or "").strip()
    chat = (cfg.get("telegram_chat_id") or "").strip()
    if not token or not chat:
        return False   # alertas desativados (opcional)
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat, "text": msg}).encode()
        urllib.request.urlopen(url, data, timeout=5)
        return True
    except Exception as e:
        log(f"alerta Telegram falhou: {e}", "warning")
        return False
