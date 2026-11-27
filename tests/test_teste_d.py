# -*- coding: utf-8 -*-
"""[AB-3] A conta D é a quinta instância: /testeD repassa para ela e para nenhuma outra, ela não
sobe na pasta de outra conta, e a unit dela tem pasta, porta e letra próprias. O mecanismo é o
do [AB-2] (tests/test_teste_c.py); aqui só o que a quinta conta acrescenta."""
import base64
import os
import threading
from http.server import HTTPServer

import pytest

from tests.test_teste_c import _falsa

CRED = "Basic " + base64.b64encode(b"admin:s3nha").decode()


@pytest.fixture
def tres(banco, monkeypatch):
    """Falsas B, C e D em portas diferentes, e a A apontando para as três."""
    import api
    from fastapi.testclient import TestClient
    classes, servidores = {}, []
    for letra in ("B", "C", "D"):
        classes[letra] = _falsa(letra)
        classes[letra].vistos = []
        srv = HTTPServer(("127.0.0.1", 0), classes[letra])
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servidores.append(srv)
        monkeypatch.setattr(api, f"TESTE{letra}_URL", f"http://127.0.0.1:{srv.server_address[1]}")
    monkeypatch.setattr(api, "DASH_PASS", "s3nha")
    monkeypatch.setattr(api, "DASH_USER", "admin")
    monkeypatch.setattr(api, "CONTA", "A")
    yield TestClient(api.app, client=("127.0.0.1", 5555)), classes
    for srv in servidores:
        srv.shutdown()


def test_sem_credencial_nada_chega_na_D(tres):
    cliente, falsas = tres
    assert cliente.get("/testeD/estado").status_code == 401
    assert cliente.post("/testeD/reset").status_code == 401
    assert all(f.vistos == [] for f in falsas.values())


def test_testeD_chega_so_na_D(tres):
    """O erro que este teste existe para pegar: /testeD cair na C (a linha copiada dela)."""
    cliente, falsas = tres
    r = cliente.post("/testeD/config", json={"tp_resto_livre": "1"}, headers={"Authorization": CRED})
    assert r.json() == {"conta": "D", "recebido": {"tp_resto_livre": "1"}}
    assert falsas["B"].vistos == [] and falsas["C"].vistos == []
    assert cliente.get("/testeC/estado", headers={"Authorization": CRED}).json()["conta"] == "C"
    assert len(falsas["D"].vistos) == 1


def test_health_da_D_e_publico_so_em_GET(tres):
    cliente, falsas = tres
    assert cliente.get("/testeD/health").status_code == 200
    assert cliente.post("/testeD/health", content=b"x").status_code == 401
    assert [v[0] for v in falsas["D"].vistos] == ["GET"]


@pytest.mark.parametrize("conta", ["B", "C", "D"])
def test_conta_de_teste_nao_repassa_para_a_D_nem_a_D_para_ninguem(tres, monkeypatch, conta):
    import api
    cliente, falsas = tres
    monkeypatch.setattr(api, "CONTA", conta)
    for rota in ("/testeB/estado", "/testeC/estado", "/testeD/estado"):
        assert cliente.get(rota, headers={"Authorization": CRED}).status_code == 404
    assert all(f.vistos == [] for f in falsas.values())


def _sobe(monkeypatch, tmp_path, conta, pasta):
    import api
    import db
    import logbot
    os.makedirs(pasta, exist_ok=True)
    monkeypatch.setattr(api, "CONTA", conta)
    monkeypatch.setattr(db, "DB", str(pasta / "trading.db"))
    monkeypatch.setattr(logbot, "LOG_FILE", str(pasta / "plataforma.log"))
    api._guarda_conta()


def test_D_nao_sobe_na_pasta_da_C_e_marca_a_dela(monkeypatch, tmp_path):
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / ".conta").write_text("C\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="pasta da conta C"):
        _sobe(monkeypatch, tmp_path, "D", tmp_path / "c")
    _sobe(monkeypatch, tmp_path, "D", tmp_path / "d")
    assert (tmp_path / "d" / ".conta").read_text(encoding="utf-8").strip() == "D"


def test_a_unit_da_D_tem_pasta_porta_e_conta_proprias():
    raiz = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    with open(os.path.join(raiz, "deploy", "cripto-bot-d.service"), encoding="utf-8") as f:
        linhas = [x for x in f.read().splitlines() if x.startswith("ExecStart=")]
    assert len(linhas) == 1
    ex = linhas[0]
    assert " CONTA=D " in ex and "--port 8004" in ex and "--host 127.0.0.1" in ex
    assert "DB_PATH=/home/cripto/cripto-bot-d/trading.db" in ex
    assert "LOG_PATH=/home/cripto/cripto-bot-d/plataforma.log" in ex
    for outra in ("cripto-bot-b", "cripto-bot-c", "8002", "8003"):
        assert outra not in ex
