# -*- coding: utf-8 -*-
"""[LIVE-10] `deploy/backup_banco.py`: cópia íntegra de banco vivo, com rotação."""
import importlib.util
import os
import sqlite3
from datetime import datetime, timedelta

import pytest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("backup_banco",
                                               os.path.join(_RAIZ, "deploy", "backup_banco.py"))
bb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bb)


def _banco(caminho, linhas=50):
    c = sqlite3.connect(caminho)
    c.execute("PRAGMA journal_mode=WAL")            # como o do bot
    c.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, v TEXT)")
    c.executemany("INSERT INTO t(v) VALUES(?)", [(f"x{i}",) for i in range(linhas)])
    c.commit()
    return c


def test_copia_com_o_banco_aberto_e_escrevendo_e_integra(tmp_path):
    vivo = _banco(str(tmp_path / "trading.db"))
    vivo.execute("INSERT INTO t(v) VALUES('ainda no wal')")
    vivo.commit()                                   # está no -wal, não no arquivo principal
    copia = bb.fazer(str(tmp_path / "trading.db"), str(tmp_path / "bk"))
    c = sqlite3.connect(copia)
    assert c.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 51
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    vivo.close()


def test_rotacao_guarda_as_n_mais_novas(tmp_path):
    _banco(str(tmp_path / "trading.db")).close()
    t0 = datetime(2026, 11, 26, 3, 17)
    for d in range(5):
        bb.fazer(str(tmp_path / "trading.db"), str(tmp_path / "bk"), manter=3,
                 agora=t0 + timedelta(days=d))
    assert sorted(os.listdir(tmp_path / "bk")) == [
        "trading-20261128-031700.db", "trading-20261129-031700.db", "trading-20261130-031700.db"]


def test_banco_que_nao_existe_falha_alto(tmp_path, capsys):
    assert bb.main([str(tmp_path / "nao.db"), str(tmp_path / "bk")]) == 1
    assert "FALHOU" in capsys.readouterr().out


def test_copia_corrompida_e_apagada_e_falha(tmp_path, monkeypatch):
    _banco(str(tmp_path / "trading.db")).close()
    monkeypatch.setattr(bb, "_integridade", lambda caminho: "row 3 missing from index")
    with pytest.raises(RuntimeError, match="integrity_check"):
        bb.fazer(str(tmp_path / "trading.db"), str(tmp_path / "bk"))
    assert os.listdir(tmp_path / "bk") == []
