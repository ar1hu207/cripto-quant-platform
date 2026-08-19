"""Sprint 7 - logging central (arquivo + console). `from logbot import log`."""
import logging
import os

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plataforma.log")

_logger = logging.getLogger("plataforma")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    _logger.addHandler(ch)


def log(msg, nivel="info"):
    getattr(_logger, nivel, _logger.info)(msg)
