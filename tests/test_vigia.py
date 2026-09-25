"""[vigia] Processo vivo com o ciclo parado -- o buraco que nenhuma guarda cobria.

`Restart=always` so pega processo que MORRE. As tres regras de metrica da Azure (RUNBOOK-VM.md
§8) veem a VM, nunca o processo. E o `alertas.py` so avisa de trade, de dentro do proprio
processo: um bot morto nao manda mensagem dizendo que morreu. Estes testes travam as duas
pontas que fecham o buraco:

  1. o watchdog do systemd -- o worker avisa a cada ciclo COMPLETO; sem aviso por
     `VIGIA_CICLO_S`, o systemd reinicia o servico (auto-cura);
  2. o `/health` -- responde 503 quando o ciclo parou, e e o que a vigia externa
     (`.github/workflows/vigia.yml`) le para mandar e-mail ao dono.
"""
import os
import re
import socket
import sys
import tempfile
import time

import pytest

import api

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def cliente(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(api, "_vigia", {"ultimo": None})
    return TestClient(api.app, client=("127.0.0.1", 5555))   # sem `with`: o worker nao sobe


def test_health_com_ciclo_recente_e_200(cliente, monkeypatch):
    monkeypatch.setattr(api, "_INICIO_MONO", time.monotonic() - 10_000)
    api._vigia["ultimo"] = time.monotonic() - 20
    r = cliente.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok" and 19 <= j["ciclo_ha_s"] <= 60
    assert j["versao"] and "commit" in j                     # o contrato do [P2-3] continua


def test_health_com_ciclo_parado_e_503_e_continua_dizendo_versao_e_commit(cliente, monkeypatch):
    """O caso que motivou o card: processo respondendo, worker sem ciclo ha mais de 5 min."""
    monkeypatch.setattr(api, "_INICIO_MONO", time.monotonic() - 10_000)
    api._vigia["ultimo"] = time.monotonic() - (api.VIGIA_CICLO_S + 60)
    r = cliente.get("/health")
    assert r.status_code == 503
    j = r.json()
    assert j["status"] == "ciclo parado" and j["ciclo_ha_s"] > api.VIGIA_CICLO_S
    assert j["versao"] and "commit" in j


def test_health_sem_ciclo_nenhum_depois_da_subida_e_503(cliente, monkeypatch):
    """Worker que nunca completou um ciclo (thread morta no primeiro, banco travado) tambem e
    bot parado -- o `None` nao pode passar por "sem informacao, entao ok"."""
    monkeypatch.setattr(api, "_INICIO_MONO", time.monotonic() - 10_000)
    r = cliente.get("/health")
    assert r.status_code == 503 and r.json()["ciclo_ha_s"] is None


def test_health_na_subida_nao_alarma(cliente, monkeypatch):
    """Um restart de deploy nao pode virar e-mail: nos primeiros `VIGIA_CICLO_S` do processo o
    /health responde 200 mesmo sem ciclo."""
    monkeypatch.setattr(api, "_INICIO_MONO", time.monotonic())
    assert cliente.get("/health").status_code == 200


def test_health_continua_publico_com_senha_ligada(cliente, monkeypatch):
    """A vigia externa le sem credencial. Se o /health passasse a pedir senha, o workflow veria
    401 para sempre e o alarme viraria ruido."""
    monkeypatch.setattr(api, "DASH_PASS", "senha-de-teste")
    monkeypatch.setattr(api, "_INICIO_MONO", time.monotonic())
    assert cliente.get("/health").status_code == 200


def test_sd_notify_fora_do_systemd_e_noop(monkeypatch):
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    assert api._sd_notify(b"WATCHDOG=1") is False


@pytest.mark.skipif(sys.platform == "win32", reason="datagrama AF_UNIX e coisa do Linux (a VM)")
def test_sd_notify_fala_o_protocolo_do_systemd(monkeypatch):
    caminho = os.path.join(tempfile.mkdtemp(), "notify.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    srv.bind(caminho)
    try:
        monkeypatch.setenv("NOTIFY_SOCKET", caminho)
        assert api._sd_notify(b"WATCHDOG=1") is True
        srv.settimeout(2)
        assert srv.recv(64) == b"WATCHDOG=1"
    finally:
        srv.close()


def test_a_unit_tem_o_watchdog_com_o_MESMO_prazo_do_codigo():
    """Dois numeros para o mesmo fato divergem um dia. Se a unit disser 120 e o codigo 300, o
    systemd mata o bot antes de o /health admitir que ele parou -- ou o contrario."""
    with open(os.path.join(RAIZ, "deploy", "cripto-bot.service"), encoding="utf-8") as f:
        unit = f.read()
    m = re.search(r"^WatchdogSec=(\d+)\s*$", unit, re.M)
    assert m, "deploy/cripto-bot.service sem WatchdogSec"
    assert int(m.group(1)) == api.VIGIA_CICLO_S
    # Type=simple so aceita sd_notify com NotifyAccess explicito; sem ele o aviso e descartado
    # e o systemd reiniciaria o bot a cada VIGIA_CICLO_S, com o worker perfeitamente vivo.
    assert re.search(r"^NotifyAccess=main\s*$", unit, re.M)


def test_a_vigia_externa_le_o_health_de_producao():
    with open(os.path.join(RAIZ, ".github", "workflows", "vigia.yml"), encoding="utf-8") as f:
        wf = f.read()
    assert "schedule:" in wf and "cron:" in wf
    assert "/health" in wf
