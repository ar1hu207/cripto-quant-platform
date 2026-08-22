"""Sprint 7 - logging central (arquivo + console). `from logbot import log`."""
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plataforma.log")

_logger = logging.getLogger("plataforma")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    # teto conhecido: 10 MB no arquivo vivo + 5 rotacionados = ~60 MB, contra os 61 GB do disco.
    # No codigo, e nao no logrotate, porque assim a poda viaja com o repositorio.
    fh = RotatingFileHandler(LOG_FILE, maxBytes=10_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    _logger.addHandler(ch)


def log(msg, nivel="info"):
    getattr(_logger, nivel, _logger.info)(msg)
