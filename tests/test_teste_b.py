# -*- coding: utf-8 -*-
"""[AB-1] A rota /testeB repassa para a instância B, e a autenticação da A vale ANTES do repasse."""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

CRED = "Basic " + base64.b64encode(b"admin:s3nha").decode()


class _FalsaB(BaseHTTPRequestHandler):
    vistos = []

    def _responde(self, status, corpo):
        dados = json.dumps(corpo).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        _FalsaB.vistos.append(("GET", self.path, self.headers.get("Authorization")))
        if self.path.startswith("/config"):
            return self._responde(422, {"detail": "recusado pela B"})
        self._responde(200, {"conta": "B", "path": self.path})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(n).decode()
        _FalsaB.vistos.append(("POST", self.path, corpo))
        self._responde(200, {"recebido": json.loads(corpo)})

    def log_message(self, *a):
        pass


@pytest.fixture
def falsa_b():
    srv = HTTPServer(("127.0.0.1", 0), _FalsaB)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _FalsaB.vistos = []
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def cliente(banco, falsa_b, monkeypatch):
    from fastapi.testclient import TestClient
    import api
    monkeypatch.setattr(api, "DASH_PASS", "s3nha")
    monkeypatch.setattr(api, "DASH_USER", "admin")
    monkeypatch.setattr(api, "TESTEB_URL", falsa_b)
    monkeypatch.setattr(api, "CONTA", "A")
    return TestClient(api.app, client=("127.0.0.1", 5555))


def test_sem_credencial_a_A_recusa_e_nada_chega_na_B(cliente):
    r = cliente.get("/testeB/estado")
    assert r.status_code == 401
    assert _FalsaB.vistos == []


def test_com_credencial_repassa_com_query_e_credencial(cliente):
    r = cliente.get("/testeB/trades?limite=5", headers={"Authorization": CRED})
    assert r.status_code == 200
    assert r.json() == {"conta": "B", "path": "/trades?limite=5"}
    assert _FalsaB.vistos == [("GET", "/trades?limite=5", CRED)]


def test_post_leva_o_corpo(cliente):
    r = cliente.post("/testeB/config", json={"risco_por_trade": "0.01"},
                     headers={"Authorization": CRED})
    assert r.json() == {"recebido": {"risco_por_trade": "0.01"}}


def test_erro_da_B_volta_com_o_status_dela(cliente):
    r = cliente.get("/testeB/config", headers={"Authorization": CRED})
    assert r.status_code == 422
    assert r.json()["detail"] == "recusado pela B"


def test_health_da_B_e_publico_como_o_da_A(cliente):
    assert cliente.get("/testeB/health").status_code == 200


def test_B_fora_do_ar_e_502_declarado(cliente, monkeypatch):
    import api
    monkeypatch.setattr(api, "TESTEB_URL", "http://127.0.0.1:9")
    r = cliente.get("/testeB/estado", headers={"Authorization": CRED})
    assert r.status_code == 502
    assert "Teste B fora do ar" in r.text


def test_na_propria_B_a_rota_nao_existe(cliente, monkeypatch):
    import api
    monkeypatch.setattr(api, "CONTA", "B")
    r = cliente.get("/testeB/estado", headers={"Authorization": CRED})
    assert r.status_code == 404
    assert _FalsaB.vistos == []


def test_health_diz_a_conta(cliente):
    assert cliente.get("/health").json()["conta"] in ("A", "B")


def test_conta_B_no_banco_da_A_nao_sobe(monkeypatch, tmp_path):
    """O incidente de 10/11: o .env da A venceu o Environment= da unit e a B abriu o banco da A."""
    import os
    import api
    import db
    import logbot
    raiz = os.path.dirname(os.path.realpath(api.__file__))
    monkeypatch.setattr(api, "CONTA", "B")
    monkeypatch.setattr(logbot, "LOG_FILE", str(tmp_path / "b.log"))
    monkeypatch.setattr(db, "DB", os.path.join(raiz, "trading.db"))
    with pytest.raises(RuntimeError, match="DB_PATH"):
        api._guarda_conta()
    monkeypatch.setattr(db, "DB", str(tmp_path / "b.db"))
    monkeypatch.setattr(logbot, "LOG_FILE", os.path.join(raiz, "plataforma.log"))
    with pytest.raises(RuntimeError, match="LOG_PATH"):
        api._guarda_conta()
    monkeypatch.setattr(logbot, "LOG_FILE", str(tmp_path / "b.log"))
    api._guarda_conta()                                   # caminhos próprios: sobe


def test_conta_A_no_proprio_diretorio_sobe(monkeypatch):
    import api
    monkeypatch.setattr(api, "CONTA", "A")
    api._guarda_conta()
