# -*- coding: utf-8 -*-
"""[PUSH-1] Notificacao nativa no celular: o que nao pode quebrar sem ninguem ver.

1. Sem chave no `.env`, push e no-op -- nem thread, nem rede, nem excecao. E o estado de todo
   ambiente que nao e o dl380 (CI, maquina de dev), e o do proprio dl380 ate o dono colar a chave.
2. A mensagem sai CIFRADA para o aparelho, e so ele a abre: o teste cifra com a chave publica
   de um aparelho de mentira e decifra com a privada dele, como o iPhone faria.
3. O backend so faz POST para servico de push conhecido (sem isso, a senha do painel viraria um
   jeito de mandar POST para dentro da rede do dl380).
4. Falha do servico de push nunca chega no caminho do dinheiro: inscricao morta sai do banco,
   falha passageira so conta, e `avisar` nunca levanta.
5. A trava diaria avisa UMA vez por dia, na virada para travado.
"""
import base64
import json
import threading
import time

import pandas as pd
import pytest

import db
import push
import simulador
from conftest import semear_equity, semear_sinal

CRED = "Basic " + base64.b64encode(b"admin:s3nha").decode()
APPLE = "https://web.push.apple.com/QGuQyavXutnMH6"


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _aparelho():
    """Par de chaves de um 'aparelho' de mentira: o que o iPhone gera ao se inscrever."""
    import os
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    k = ec.generate_private_key(ec.SECP256R1())
    pub = k.public_key().public_bytes(serialization.Encoding.X962,
                                      serialization.PublicFormat.UncompressedPoint)
    auth = os.urandom(16)
    return k, _b64(pub), auth, _b64(auth)


@pytest.fixture
def chaves(monkeypatch):
    pub, priv = push.gerar_chaves()
    monkeypatch.setenv("VAPID_PUBLIC", pub)
    monkeypatch.setenv("VAPID_PRIVATE", priv)
    monkeypatch.delenv("CONTA", raising=False)
    return pub, priv


class _Resp:
    def __init__(self, status):
        self.status_code = status
        self.reason = "Gone" if status == 410 else "Erro" if status >= 400 else "Created"
        self.text = ""
        self.content = b""
        self.headers = {}


@pytest.fixture
def servico(monkeypatch):
    """Troca o POST do pywebpush por um servico de push de mentira que guarda o que recebeu."""
    import requests
    estado = {"status": 201, "recebidos": []}

    def post(url, data=None, headers=None, timeout=None, **kw):
        estado["recebidos"].append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return _Resp(estado["status"])
    monkeypatch.setattr(requests, "post", post)
    return estado


# ---------------------------------------------------------------- 1. sem chave e no-op

def test_sem_chave_push_fica_desligado_e_diz_por_que(banco, monkeypatch):
    monkeypatch.delenv("VAPID_PUBLIC", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE", raising=False)
    ativo, motivo = push.estado()
    assert ativo is False and "VAPID" in motivo
    assert push.avisar("x", "y") is False
    assert push.enviar_agora("x", "y")["ok"] == 0


def test_com_chave_mas_sem_aparelho_nao_sobe_thread(banco, chaves, monkeypatch):
    monkeypatch.setattr(push, "_thread", None)
    assert push.avisar("x", "y") is False
    assert push._thread is None


# ---------------------------------------------------------------- 2. cifra de verdade

def test_a_mensagem_sai_cifrada_e_so_o_aparelho_abre(banco, chaves, servico):
    import http_ece
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, utils

    k, p256dh, auth_raw, auth = _aparelho()
    push.inscrever(APPLE, p256dh, auth)
    r = push.enviar_agora("Fechou LONG BTCUSDT · +R$ 39,21", "Saída por stop.", "#diario", "pos-7")
    assert r == {"ok": 1, "falhas": 0, "removidas": 0}

    env = servico["recebidos"][0]
    assert env["url"] == APPLE and env["timeout"] == push.TIMEOUT_S
    assert b"Fechou" not in env["data"]                       # nada legivel no caminho
    claro = http_ece.decrypt(env["data"], private_key=k, auth_secret=auth_raw, version="aes128gcm")
    assert json.loads(claro) == {"titulo": "Fechou LONG BTCUSDT · +R$ 39,21",
                                 "corpo": "Saída por stop.", "url": "#diario", "tag": "pos-7"}

    # VAPID: o JWT e assinado com a chave privada do .env e confere com a publica que o app usou
    h = {k_.lower(): v for k_, v in env["headers"].items()}
    assert h["ttl"] == str(push.TTL_S) and h["urgency"] == "high"
    tok = h["authorization"].split("t=")[1].split(",")[0].strip()
    cab, corpo, sig = tok.split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)                     # noqa: E731
    claims = json.loads(base64.urlsafe_b64decode(pad(corpo)))
    assert claims["aud"] == "https://web.push.apple.com"
    assert claims["sub"].startswith(("https://", "mailto:"))
    assert claims["exp"] > time.time()
    pub = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), base64.urlsafe_b64decode(pad(chaves[0])))
    s = base64.urlsafe_b64decode(pad(sig))
    der = utils.encode_dss_signature(int.from_bytes(s[:32], "big"), int.from_bytes(s[32:], "big"))
    pub.verify(der, (cab + "." + corpo).encode(), ec.ECDSA(hashes.SHA256()))


def test_na_conta_B_o_titulo_diz_a_conta(banco, chaves, servico, monkeypatch):
    import http_ece
    monkeypatch.setenv("CONTA", "B")
    k, p256dh, auth_raw, auth = _aparelho()
    push.inscrever(APPLE, p256dh, auth)
    push.enviar_agora("Trava diária disparou", "x")
    claro = http_ece.decrypt(servico["recebidos"][0]["data"], private_key=k,
                             auth_secret=auth_raw, version="aes128gcm")
    assert json.loads(claro)["titulo"] == "Conta B · Trava diária disparou"


# ---------------------------------------------------------------- 3. so servico de push

@pytest.mark.parametrize("url", [
    "https://web.push.apple.com/abc", "https://api.push.apple.com/abc",
    "https://fcm.googleapis.com/fcm/send/abc", "https://updates.push.services.mozilla.com/wpush/v2/x",
])
def test_aceita_servico_de_push(url):
    assert push.endereco_valido(url)


@pytest.mark.parametrize("url", [
    "http://web.push.apple.com/abc",              # sem TLS
    "https://web.push.apple.com.evil.com/abc",    # sufixo falso
    "https://evil.com/web.push.apple.com",        # host no caminho
    "https://127.0.0.1:8001/reset",               # a conta B, por dentro
    "https://localhost/x", "file:///etc/passwd", "", None,
])
def test_recusa_o_que_nao_e_servico_de_push(url):
    assert not push.endereco_valido(url)


def test_inscricao_com_chave_ruim_e_recusada(banco):
    with pytest.raises(ValueError):
        push.inscrever(APPLE, "curta", _b64(b"x" * 16))
    with pytest.raises(ValueError):
        push.inscrever("https://evil.com/x", _aparelho()[1], _b64(b"x" * 16))


def test_reinscrever_o_mesmo_aparelho_nao_duplica(banco):
    _, p, _, a = _aparelho()
    assert push.inscrever(APPLE, p, a) == 1
    assert push.inscrever(APPLE, p, a) == 1
    assert push.sair(APPLE) == 1 and push.inscricoes() == []


# ---------------------------------------------------------------- 4. falha nao sobe

def test_inscricao_morta_sai_do_banco(banco, chaves, servico):
    _, p, _, a = _aparelho()
    push.inscrever(APPLE, p, a)
    servico["status"] = 410
    assert push.enviar_agora("x", "y") == {"ok": 0, "falhas": 0, "removidas": 1}
    assert push.inscricoes() == []


def test_falha_passageira_conta_e_mantem(banco, chaves, servico):
    _, p, _, a = _aparelho()
    push.inscrever(APPLE, p, a)
    servico["status"] = 503
    assert push.enviar_agora("x", "y")["falhas"] == 1
    assert push.inscricoes()[0]["falhas"] == 1


def test_avisar_nunca_levanta_nem_com_o_banco_quebrado(chaves, monkeypatch):
    monkeypatch.setattr(db, "DB", "/caminho/que/nao/existe/x.db")
    assert push.avisar("x", "y") is False


def test_avisar_entrega_em_segundo_plano(banco, chaves, servico):
    _, p, _, a = _aparelho()
    push.inscrever(APPLE, p, a)
    t0 = time.time()
    assert push.avisar("Abriu LONG BTCUSDT", "R$ 50,00") is True
    assert time.time() - t0 < 0.5                      # o chamador nao espera a Apple
    push._fila.join()
    assert len(servico["recebidos"]) == 1


def test_fechar_a_posicao_nao_depende_do_push(banco, sem_rede, monkeypatch):
    """O aviso vem depois do trade gravado; mesmo um push que explodisse nao desfaz nada."""
    def explode(*a, **k):
        raise RuntimeError("Apple fora do ar")
    sid = semear_sinal(preco=100.0, stop=95.0)
    pid = simulador.abrir(sid, 50.0, 2)
    monkeypatch.setattr(push, "enviar_agora", explode)  # a thread engole; o fechar nao ve
    assert simulador.fechar(pid, "manual") is not None
    with db.conectar() as c:
        assert c.execute("SELECT status FROM posicoes WHERE id=?", (pid,)).fetchone()[0] == "fechada"


# ---------------------------------------------------------------- 5. eventos

def test_abrir_e_fechar_avisam_com_o_link_certo(banco, sem_rede, monkeypatch):
    vistos = []
    monkeypatch.setattr(push, "avisar", lambda *a, **k: vistos.append(a))
    sid = semear_sinal(preco=100.0, stop=95.0)
    pid = simulador.abrir(sid, 50.0, 2)
    simulador.fechar(pid, "manual")
    assert vistos[0][0] == "Nova posição aberta 🚀" and "LONG BTCUSDT" in vistos[0][1]
    assert vistos[0][2] == f"#pos/{pid}"
    assert vistos[1][1].endswith("LONG BTCUSDT · fechada por você") and vistos[1][2] == "#diario"
    assert vistos[0][3] == vistos[1][3] == f"pos-{pid}"   # o de fechar substitui o de abrir


def test_trava_avisa_uma_vez_por_dia(banco, monkeypatch):
    vistos = []
    monkeypatch.setattr(push, "avisar", lambda *a, **k: vistos.append(a))
    semear_equity(str(pd.Timestamp.now().date()) + " 00:00:05", 1000.0)
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=900 WHERE id=1")
    assert simulador.guarda_risco()["trava_dia"] is True
    assert simulador.guarda_risco()["trava_dia"] is True   # o poll de 3s chama de novo
    assert len(vistos) == 1
    assert vistos[0][0] == "Trava diária acionada 🛑" and vistos[0][2] == "#apollo"
    assert "−R$ 100,00" in vistos[0][1] and "R$ 50,00" in vistos[0][1]


def test_textos_no_formato_do_painel():
    assert push.brl(1234.5) == "R$ 1.234,50" and push.brl(-80.34) == "−R$ 80,34"
    assert push.money(39.21) == "+R$ 39,21" and push.money(0) == "R$ 0,00"
    assert push.px(68869.6) == "68.869,6" and push.px(0.06281) == "0,06281"
    assert push.par("BTC/USDT:USDT") == "BTCUSDT"
    assert push.motivo("manual") == "fechada por você" and push.motivo("tp2") == "bateu o TP2"
    assert push.motivo("trailing") == "saiu pelo trailing" and push.motivo("panico") == "fechada no pânico"


def test_estilo_comemora_so_lucro_e_poe_o_dinheiro_primeiro():
    t, c = push.msg_fechou("LONG", "BTC/USDT", 39.21, "trailing")
    assert t == "Lucro no bolso! 💰" and c == "Lucro: +R$ 39,21 · LONG BTCUSDT · saiu pelo trailing"
    t, c = push.msg_fechou("SHORT", "SOL/USDT", -29.88, "stop")
    assert "💰" not in t and "Lucro" not in t and c.startswith("Resultado: −R$ 29,88")
    assert push.msg_fechou("LONG", "X/USDT", -50, "liquidacao")[0] == "Posição liquidada ⚠️"
    t, c = push.msg_parcial("LONG", "BTC/USDT", 12.4, "tp1", 0.33)
    assert t == "Lucro parcial no bolso! 💸" and c.startswith("Lucro: +R$ 12,40 · bateu o TP1 com 33%")
    assert push.msg_abriu("LONG", "BTC/USDT", 500, 5, 68869.6) == (
        "Nova posição aberta 🚀", "LONG BTCUSDT · R$ 500,00 a 5x · entrada 68.869,6")
    assert push.msg_trava(-100, 50) == (
        "Trava diária acionada 🛑", "Perda do dia: −R$ 100,00 (limite R$ 50,00) · sem novas entradas até a virada")


# ---------------------------------------------------------------- rotas

@pytest.fixture
def cliente(banco, monkeypatch):
    from fastapi.testclient import TestClient
    import api
    monkeypatch.setattr(api, "DASH_PASS", "s3nha")
    monkeypatch.setattr(api, "DASH_USER", "admin")
    return TestClient(api.app, client=("127.0.0.1", 5555))


def test_rotas_de_push_pedem_a_senha(cliente):
    for metodo, rota in (("get", "/push/chave"), ("post", "/push/inscrever"),
                         ("post", "/push/sair"), ("post", "/push/teste")):
        assert getattr(cliente, metodo)(rota).status_code == 401, rota


def test_sem_chave_a_rota_avisa_e_nao_grava(cliente, monkeypatch):
    monkeypatch.delenv("VAPID_PUBLIC", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE", raising=False)
    h = {"Authorization": CRED}
    k = cliente.get("/push/chave", headers=h).json()
    assert k["ativo"] is False and k["chave"] is None and "VAPID" in k["motivo"]
    _, p, _, a = _aparelho()
    r = cliente.post("/push/inscrever", headers=h, json={"endpoint": APPLE, "keys": {"p256dh": p, "auth": a}}).json()
    assert r["ok"] is False and push.inscricoes() == []


def test_ciclo_completo_pelas_rotas(cliente, chaves, servico):
    h = {"Authorization": CRED}
    k = cliente.get("/push/chave", headers=h).json()
    assert k["ativo"] is True and k["chave"] == chaves[0] and k["inscrito"] is False
    assert "VAPID_PRIVATE" not in json.dumps(k) and chaves[1] not in json.dumps(k)

    _, p, _, a = _aparelho()
    ruim = cliente.post("/push/inscrever", headers=h,
                        json={"endpoint": "https://127.0.0.1:8001/reset", "keys": {"p256dh": p, "auth": a}}).json()
    assert ruim["ok"] is False and push.inscricoes() == []

    # o app manda o sub.toJSON() inteiro, com expirationTime
    r = cliente.post("/push/inscrever", headers=h,
                     json={"endpoint": APPLE, "expirationTime": None, "keys": {"p256dh": p, "auth": a}}).json()
    assert r == {"ok": True, "aparelhos": 1}
    assert cliente.get("/push/chave", headers=h, params={"endpoint": APPLE}).json()["inscrito"] is True

    t = cliente.post("/push/teste", headers=h, json={"endpoint": APPLE}).json()
    assert t["ok"] is True and t["enviados"] == 1 and len(servico["recebidos"]) == 1

    assert cliente.post("/push/sair", headers=h, json={"endpoint": APPLE}).json()["removidas"] == 1
    assert cliente.get("/push/chave", headers=h, params={"endpoint": APPLE}).json()["inscrito"] is False


def test_a_chave_privada_nunca_aparece_em_rota_nenhuma(cliente, chaves):
    h = {"Authorization": CRED}
    for rota in ("/push/chave", "/config", "/estado", "/health"):
        r = cliente.get(rota, headers=h)
        assert chaves[1] not in r.text, rota


def test_gerar_chaves_devolve_um_par_que_o_pywebpush_aceita():
    from py_vapid import Vapid
    pub, priv = push.gerar_chaves()
    v = Vapid.from_string(priv)
    from cryptography.hazmat.primitives import serialization
    assert _b64(v.public_key.public_bytes(serialization.Encoding.X962,
                                          serialization.PublicFormat.UncompressedPoint)) == pub


# ---------------------------------------------------------------- [PUSH-2] preferencias e resumo
# O dono (13/11): "modelavel quanto tempo cada notificacao vai tocar ... opcional os tipos ...
# de 3 em 3h falando de lucro, de alguns trades ... resultado do dia". Cada aparelho escolhe,
# por tipo, na hora / so no resumo / desligado; o resumo sai alinhado ao relogio.

def _inscrito(prefs=None, endpoint=APPLE):
    _, p, _, a = _aparelho()
    push.inscrever(endpoint, p, a)
    if prefs:
        push.salvar_prefs(endpoint, prefs)
    return endpoint


def test_aparelho_antigo_fica_no_padrao_de_antes(banco):
    """Inscrito antes do [PUSH-2] (prefs NULL) recebe tudo na hora e nenhum resumo."""
    _inscrito()
    assert push.inscricoes()[0]["prefs"] == push.PREFS_PADRAO
    with db.conectar() as c:                              # gravado ilegivel tambem vale o padrao
        c.execute("UPDATE push_inscricoes SET prefs='{lixo'")
    assert push.inscricoes()[0]["prefs"] == push.PREFS_PADRAO


@pytest.mark.parametrize("ruim", [{"entrada": "talvez"}, {"resumo_h": 5}, {"resumo_h": "3"},
                                  {"resumo_h": True}, {"silencio": {"de": 23}},
                                  {"silencio": {"de": 7, "ate": 7}}, {"silencio": {"de": 24, "ate": 7}},
                                  {"som": "alto"}, ["entrada"]])
def test_preferencia_fora_do_catalogo_e_recusada(ruim):
    with pytest.raises(ValueError):
        push.normalizar_prefs(ruim)


def test_preferencias_gravam_mesclam_e_sobrevivem_a_reinscricao(banco):
    ep = _inscrito({"entrada": "resumo", "resumo_h": 3})
    p = push.salvar_prefs(ep, {"fechou": "off"})
    assert p["entrada"] == "resumo" and p["fechou"] == "off" and p["resumo_h"] == 3
    _, k, _, a = _aparelho()
    push.inscrever(ep, k, a)                              # o app renova a inscricao sozinho
    assert push.inscricoes()[0]["prefs"]["fechou"] == "off"
    assert push.salvar_prefs("https://web.push.apple.com/outro", {"fechou": "off"}) is None


def test_quem_quer_o_que_e_quando():
    t = pd.Timestamp("2026-11-13 02:00")
    p = dict(push.PREFS_PADRAO, entrada="resumo", parcial="off", silencio={"de": 23, "ate": 7})
    assert push.quer_agora(p, None, t) is True            # o teste vai sempre
    assert push.quer_agora(p, "entrada", t.replace(hour=12)) is False   # so no resumo
    assert push.quer_agora(p, "parcial", t.replace(hour=12)) is False   # desligado
    assert push.quer_agora(p, "fechou", t.replace(hour=12)) is True
    assert push.quer_agora(p, "fechou", t) is False       # 2h esta no silencio 23h-7h
    assert push.quer_agora(p, "trava", t) is True         # a trava atravessa
    assert push.em_silencio({"silencio": {"de": 13, "ate": 15}}, t.replace(hour=14))
    assert not push.em_silencio({"silencio": {"de": 13, "ate": 15}}, t.replace(hour=15))


def test_cada_aparelho_recebe_so_o_que_escolheu(banco, chaves, servico):
    google = "https://fcm.googleapis.com/fcm/send/abc"
    _inscrito({"entrada": "off"}, APPLE)
    _inscrito(None, google)
    r = push.enviar_agora(*push.msg_abriu("LONG", "BTC/USDT", 500, 5, 1), tipo="entrada")
    assert r["ok"] == 1 and [x["url"] for x in servico["recebidos"]] == [google]
    assert push.enviar_agora("x", "y", tipo="fechou")["ok"] == 2


def test_resumo_sai_alinhado_ao_relogio_e_uma_vez_por_bloco():
    p = dict(push.PREFS_PADRAO, resumo_h=3)
    t = pd.Timestamp
    assert push.inicio_do_bloco(t("2026-11-13 16:40"), 3) == t("2026-11-13 15:00")
    assert not push.resumo_vencido(p, "2026-11-13 14:10:00", t("2026-11-13 14:59"))
    assert push.resumo_vencido(p, "2026-11-13 14:10:00", t("2026-11-13 15:00"))
    assert not push.resumo_vencido(p, "2026-11-13 15:00:30", t("2026-11-13 17:59"))
    assert not push.resumo_vencido(dict(p, resumo_h=0), None, t("2026-11-13 15:00"))
    calado = dict(p, silencio={"de": 23, "ate": 7})       # o das 3h espera o fim do silencio
    assert not push.resumo_vencido(calado, "2026-11-13 21:00", t("2026-11-14 03:00"))
    assert push.resumo_vencido(calado, "2026-11-13 21:00", t("2026-11-14 07:01"))


def test_ligar_o_resumo_nao_dispara_um_na_hora(banco):
    ep = _inscrito()
    push.salvar_prefs(ep, {"resumo_h": 3})
    s = push.inscricoes()[0]
    assert s["ultimo_resumo"] and not push.resumo_vencido(s["prefs"], s["ultimo_resumo"],
                                                          pd.Timestamp(s["ultimo_resumo"]))


def _dia_com_trades(hoje):
    """Inicio do dia com R$ 1.000; uma posicao aberta as 13h que realizou TP1 as 14h e segue
    aberta; uma que fechou inteira no stop as 14h30; banca hoje em 1.030 + 5 em aberto."""
    semear_equity(f"{hoje} 00:00:05", 1000.0)
    ins_pos = ("INSERT INTO posicoes(ativo,direcao,entrada,valor_reais,alavancagem,stop,preco_atual,"
               "pnl,aberto_em,status) VALUES(?,?,?,?,?,?,?,?,?,?)")
    ins_tr = ("INSERT INTO trades(ativo,direcao,pnl_reais,motivo_saida,aberto_em,fechado_em) "
              "VALUES(?,?,?,?,?,?)")
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=1030 WHERE id=1")
        c.execute(ins_pos, ("ETH/USDT:USDT", "LONG", 3000, 300, 5, 2900, 3010, 5,
                            f"{hoje} 13:00:00", "aberta"))
        c.execute(ins_tr, ("ETH/USDT:USDT", "LONG", 40.0, "tp1", f"{hoje} 13:00:00", f"{hoje} 14:00:00"))
        c.execute(ins_pos, ("SOL/USDT:USDT", "SHORT", 150, 200, 3, 155, 155, 0,
                            f"{hoje} 12:50:00", "fechada"))
        c.execute(ins_tr, ("SOL/USDT:USDT", "SHORT", -10.0, "stop", f"{hoje} 12:50:00", f"{hoje} 14:30:00"))


def test_resumo_conta_o_dia_e_os_trades_da_janela(banco):
    hoje = str(pd.Timestamp.now().date())
    _dia_com_trades(hoje)
    agora = pd.Timestamp(f"{hoje} 15:00")
    titulo, corpo = push.montar_resumo(push.PREFS_PADRAO, pd.Timestamp(f"{hoje} 12:00"), agora)
    linhas = corpo.split("\n")
    assert titulo == "Resumo das 15h · dia no verde 💰"
    # o dia pela regua da trava: 1.035 de equity agora contra 1.000 no inicio
    assert linhas[0] == "Hoje: +R$ 35,00 · realizado +R$ 30,00 · aberto +R$ 5,00"
    assert linhas[1:5] == ["↗ Entrou SHORT SOLUSDT · R$ 200,00 a 3x",
                           "↗ Entrou LONG ETHUSDT · R$ 300,00 a 5x",
                           "✓ +R$ 40,00 · LONG ETHUSDT · bateu o TP1 (parcial)",
                           "✕ −R$ 10,00 · SHORT SOLUSDT · bateu o stop"]
    assert linhas[-1] == "1 posição aberta"

    so_saidas = dict(push.PREFS_PADRAO, entrada="off", parcial="off")
    _, corpo = push.montar_resumo(so_saidas, pd.Timestamp(f"{hoje} 12:00"), agora)
    assert corpo.split("\n")[1:-1] == ["✕ −R$ 10,00 · SHORT SOLUSDT · bateu o stop"]

    _, corpo = push.montar_resumo(push.PREFS_PADRAO, pd.Timestamp(f"{hoje} 14:45"), agora)
    assert "Nenhum trade desde as 14h45" in corpo


def test_resumo_de_dia_ruim_nao_comemora_e_fala_da_trava(banco):
    hoje = str(pd.Timestamp.now().date())
    semear_equity(f"{hoje} 00:00:05", 1000.0)
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=900 WHERE id=1")
    db.set_config("trava_dia_em", hoje)
    titulo, corpo = push.montar_resumo(push.PREFS_PADRAO, pd.Timestamp(f"{hoje} 09:00"),
                                       pd.Timestamp(f"{hoje} 12:00"))
    assert titulo == "Resumo das 12h" and corpo.startswith("Hoje: −R$ 100,00")
    assert corpo.endswith("trava diária acionada 🛑")


def test_resumo_que_atravessa_a_meia_noite_fecha_o_dia_de_ontem(banco):
    ontem, hoje = "2026-11-12", "2026-11-13"
    semear_equity(f"{ontem} 00:00:05", 1000.0)
    semear_equity(f"{hoje} 00:00:05", 1080.0)
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=1080 WHERE id=1")
        c.execute("INSERT INTO trades(ativo,direcao,pnl_reais,motivo_saida,aberto_em,fechado_em) "
                  "VALUES(?,?,?,?,?,?)", ("BTC/USDT:USDT", "LONG", 80.0, "trailing",
                                          f"{ontem} 20:00:00", f"{ontem} 22:00:00"))
    _, corpo = push.montar_resumo(push.PREFS_PADRAO, pd.Timestamp(f"{ontem} 21:00"),
                                  pd.Timestamp(f"{hoje} 00:00"))
    assert corpo.split("\n")[1] == "Ontem: +R$ 80,00 em 1 trade"


def test_resumo_agendado_sai_uma_vez_por_bloco(banco, chaves, servico):
    _inscrito({"resumo_h": 3})
    with db.conectar() as c:
        c.execute("UPDATE push_inscricoes SET ultimo_resumo='2026-11-13 12:00:00'")
    assert push.resumos_vencidos(pd.Timestamp("2026-11-13 14:59")) == 0
    assert push.resumos_vencidos(pd.Timestamp("2026-11-13 15:00:20")) == 1
    assert push.resumos_vencidos(pd.Timestamp("2026-11-13 15:01:20")) == 0   # o tique seguinte
    assert len(servico["recebidos"]) == 1
    assert push.inscricoes()[0]["ultimo_resumo"] == "2026-11-13 15:00:20"
    servico["status"] = 500                                # Apple fora: nao repete a cada minuto
    assert push.resumos_vencidos(pd.Timestamp("2026-11-13 18:00:10")) == 1
    assert push.resumos_vencidos(pd.Timestamp("2026-11-13 18:01:10")) == 0


def test_eventos_do_simulador_dizem_o_tipo(banco, sem_rede, monkeypatch):
    tipos = []
    monkeypatch.setattr(push, "avisar", lambda *a, **k: tipos.append(k.get("tipo")))
    sid = semear_sinal(preco=100.0, stop=95.0)
    pid = simulador.abrir(sid, 50.0, 2)
    simulador.fechar(pid, "manual")
    assert tipos == ["entrada", "fechou"]


def test_rotas_de_preferencia(cliente, chaves, servico):
    h = {"Authorization": CRED}
    for rota in ("/push/prefs", "/push/resumo"):
        assert cliente.post(rota).status_code == 401, rota
    _inscrito()
    k = cliente.get("/push/chave", headers=h, params={"endpoint": APPLE}).json()
    assert k["prefs"] == push.PREFS_PADRAO and k["catalogo"]["resumo_h"] == list(push.RESUMO_H)
    r = cliente.post("/push/prefs", headers=h, json={"endpoint": APPLE, "prefs": {
        "resumo_h": 3, "entrada": "resumo", "silencio": {"de": 23, "ate": 7}}}).json()
    assert r["ok"] is True and r["prefs"]["resumo_h"] == 3 and r["prefs"]["fechou"] == "na_hora"
    ruim = cliente.post("/push/prefs", headers=h, json={"endpoint": APPLE, "prefs": {"resumo_h": 5}})
    assert ruim.json()["ok"] is False
    assert push.inscricoes()[0]["prefs"]["resumo_h"] == 3          # recusa nao grava nada
    outro = cliente.post("/push/prefs", headers=h, json={"endpoint": "https://web.push.apple.com/x",
                                                         "prefs": {"resumo_h": 3}}).json()
    assert outro["ok"] is False and "inscrito" in outro["erro"]
    antes = push.inscricoes()[0]["ultimo_resumo"]
    r = cliente.post("/push/resumo", headers=h, json={"endpoint": APPLE}).json()
    assert r["ok"] is True and len(servico["recebidos"]) == 1
    assert push.inscricoes()[0]["ultimo_resumo"] == antes          # o botao nao mexe no relogio
