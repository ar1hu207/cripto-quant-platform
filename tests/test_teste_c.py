# -*- coding: utf-8 -*-
"""[AB-2] A conta C é a terceira instância: /testeC repassa para ela, e nenhuma conta sobe na
pasta de outra. Os testes da B (tests/test_teste_b.py) seguem valendo sem mudança."""
import base64
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

CRED = "Basic " + base64.b64encode(b"admin:s3nha").decode()


def _falsa(letra):
    class Falsa(BaseHTTPRequestHandler):
        vistos = []

        def _responde(self, corpo):
            dados = json.dumps(corpo).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def do_GET(self):
            Falsa.vistos.append(("GET", self.path, self.headers.get("Authorization")))
            self._responde({"conta": letra, "path": self.path})

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            corpo = self.rfile.read(n).decode()
            Falsa.vistos.append(("POST", self.path, corpo))
            self._responde({"conta": letra, "recebido": json.loads(corpo)})

        def log_message(self, *a):
            pass
    return Falsa


@pytest.fixture
def duas(banco, monkeypatch):
    """Uma falsa B e uma falsa C em portas diferentes, e a A apontando para as duas."""
    import api
    from fastapi.testclient import TestClient
    classes, servidores = {}, []
    for letra in ("B", "C"):
        classes[letra] = _falsa(letra)
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


# ---------------------------------------------------------------- 1. o repasse

def test_sem_credencial_a_A_recusa_e_nada_chega_na_C(duas):
    cliente, falsas = duas
    assert cliente.get("/testeC/estado").status_code == 401
    assert cliente.post("/testeC/reset").status_code == 401
    assert falsas["C"].vistos == [] and falsas["B"].vistos == []


def test_cada_rota_chega_so_na_conta_dela(duas):
    """O erro que este teste existe para pegar: /testeC cair na B (ou o contrário)."""
    cliente, falsas = duas
    r = cliente.get("/testeC/trades?limite=5", headers={"Authorization": CRED})
    assert r.status_code == 200 and r.json() == {"conta": "C", "path": "/trades?limite=5"}
    assert falsas["C"].vistos == [("GET", "/trades?limite=5", CRED)]
    assert falsas["B"].vistos == []
    r = cliente.get("/testeB/estado", headers={"Authorization": CRED})
    assert r.json()["conta"] == "B"
    assert len(falsas["C"].vistos) == 1 and len(falsas["B"].vistos) == 1


def test_post_na_C_leva_o_corpo_e_nao_toca_a_B(duas):
    cliente, falsas = duas
    r = cliente.post("/testeC/config", json={"tp_resto_livre": "1"},
                     headers={"Authorization": CRED})
    assert r.json() == {"conta": "C", "recebido": {"tp_resto_livre": "1"}}
    assert falsas["B"].vistos == []


def test_health_da_C_e_publico_so_em_GET(duas):
    cliente, falsas = duas
    assert cliente.get("/testeC/health").status_code == 200
    assert cliente.post("/testeC/health", content=b"x").status_code == 401
    assert [v[0] for v in falsas["C"].vistos] == ["GET"]


def test_C_fora_do_ar_e_502_que_diz_qual_conta(duas, monkeypatch):
    import api
    cliente, _ = duas
    monkeypatch.setattr(api, "TESTEC_URL", "http://127.0.0.1:9")
    r = cliente.get("/testeC/estado", headers={"Authorization": CRED})
    assert r.status_code == 502 and "Teste C fora do ar" in r.text
    assert cliente.get("/testeB/estado", headers={"Authorization": CRED}).status_code == 200


@pytest.mark.parametrize("conta", ["B", "C"])
def test_conta_de_teste_nao_repassa_para_ninguem(duas, monkeypatch, conta):
    """Nem a B alcança a C, nem a C alcança a B: só a A repassa."""
    import api
    cliente, falsas = duas
    monkeypatch.setattr(api, "CONTA", conta)
    for rota in ("/testeB/estado", "/testeC/estado"):
        assert cliente.get(rota, headers={"Authorization": CRED}).status_code == 404
    assert falsas["B"].vistos == [] and falsas["C"].vistos == []


# ---------------------------------------------------------------- 2. cada conta na pasta dela

@pytest.fixture
def pastas(monkeypatch, tmp_path):
    """`sobe(conta, pasta_do_banco, pasta_do_log=None)` roda a guarda de boot como aquela conta."""
    import api
    import db
    import logbot

    def sobe(conta, pasta, pasta_log=None):
        monkeypatch.setattr(api, "CONTA", conta)
        monkeypatch.setattr(db, "DB", str(pasta / "trading.db"))
        monkeypatch.setattr(logbot, "LOG_FILE", str((pasta_log or pasta) / "plataforma.log"))
        api._guarda_conta()

    for nome in ("b", "c"):
        (tmp_path / nome).mkdir()
    return sobe, tmp_path


def _marca(pasta):
    f = pasta / ".conta"
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


def test_conta_nova_marca_a_pasta_e_sobe_de_novo(pastas):
    sobe, raiz = pastas
    sobe("C", raiz / "c")
    assert _marca(raiz / "c") == "C"
    (raiz / "c" / "trading.db").write_bytes(b"")          # o banco agora existe
    sobe("C", raiz / "c")                                 # e a dona sobe quantas vezes quiser


def test_C_nao_sobe_na_pasta_da_B(pastas):
    """A unit da C copiada da B com o DB_PATH esquecido: o erro que a marca existe para barrar."""
    sobe, raiz = pastas
    sobe("B", raiz / "b")
    (raiz / "b" / "trading.db").write_bytes(b"")
    with pytest.raises(RuntimeError, match="pasta da conta B"):
        sobe("C", raiz / "b")
    assert _marca(raiz / "b") == "B"                      # e a marca da dona não foi trocada


def test_B_nao_sobe_na_pasta_da_C(pastas):
    sobe, raiz = pastas
    sobe("C", raiz / "c")
    with pytest.raises(RuntimeError, match="pasta da conta C"):
        sobe("B", raiz / "c")


def test_A_nao_abre_banco_de_conta_de_teste(pastas):
    """A guarda antiga saía cedo para a A. Um DB_PATH da A apontando para a pasta da B punha o
    worker de produção no banco do teste -- o incidente de 10/11 ao contrário."""
    sobe, raiz = pastas
    sobe("B", raiz / "b")
    with pytest.raises(RuntimeError, match="pasta da conta B"):
        sobe("A", raiz / "b")


def test_banco_que_ja_existe_sem_marca_so_a_B_adota(pastas):
    """O banco da B nasceu em 10/11, antes da marca. Qualquer outra conta, diante de um banco
    que já existe e não diz de quem é, recusa -- senão a C adotaria o banco da B no deploy em
    que a B ainda não tivesse subido com este código."""
    sobe, raiz = pastas
    (raiz / "b" / "trading.db").write_bytes(b"")
    with pytest.raises(RuntimeError, match="já existe"):
        sobe("C", raiz / "b")
    assert _marca(raiz / "b") is None                     # recusar não marca
    sobe("B", raiz / "b")
    assert _marca(raiz / "b") == "B"


def test_log_na_pasta_de_outra_conta_recusa_e_nao_toma_a_pasta(pastas):
    sobe, raiz = pastas
    sobe("B", raiz / "b")
    with pytest.raises(RuntimeError, match="LOG_PATH"):
        sobe("C", raiz / "c", pasta_log=raiz / "b")
    assert _marca(raiz / "b") == "B"


def test_log_em_pasta_sem_marca_nao_ganha_marca(pastas):
    """A marca só nasce pela pasta do BANCO. Se o log errado marcasse a pasta onde caiu, a
    conta com a unit errada tomaria a pasta da outra, e a dona é que seria recusada depois."""
    sobe, raiz = pastas
    sobe("C", raiz / "c", pasta_log=raiz / "b")
    assert _marca(raiz / "c") == "C" and _marca(raiz / "b") is None


def test_A_na_raiz_nao_escreve_marca(monkeypatch):
    """A A é reconhecida pela pasta do código. Um arquivo novo ali sujaria a árvore do deploy."""
    import api
    raiz = os.path.dirname(os.path.realpath(api.__file__))
    antes = os.path.exists(os.path.join(raiz, ".conta"))
    monkeypatch.setattr(api, "CONTA", "A")
    api._guarda_conta()
    assert os.path.exists(os.path.join(raiz, ".conta")) == antes


def test_a_unit_da_C_tem_pasta_porta_e_conta_proprias():
    raiz = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    with open(os.path.join(raiz, "deploy", "cripto-bot-c.service"), encoding="utf-8") as f:
        linhas = [x for x in f.read().splitlines() if x.startswith("ExecStart=")]
    assert len(linhas) == 1
    ex = linhas[0]
    assert " CONTA=C " in ex and "--port 8002" in ex and "--host 127.0.0.1" in ex
    assert "DB_PATH=/home/cripto/cripto-bot-c/trading.db" in ex
    assert "LOG_PATH=/home/cripto/cripto-bot-c/plataforma.log" in ex
    assert "cripto-bot-b" not in ex
