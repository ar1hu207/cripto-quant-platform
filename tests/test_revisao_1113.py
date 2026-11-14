# -*- coding: utf-8 -*-
"""Furos achados na revisao completa de 2026-11-13 (base be2f87f). Cada teste afirma a REGRA
e falhava antes da correcao que veio no mesmo commit. O relatorio com o porque de cada um
esta em `REVISAO-2026-11-13.md`, na raiz.

Grupos: tp (alvos que criam dinheiro), entrada (margem e alavancagem), panico (corrida com o
bot), scan (duas varreduras ao mesmo tempo), borda (o que a API aceita de fora), segredo (o
token que saia em todo poll), mercado (um par ruim derrubando o lote).
"""
import json
import threading
import time

import pandas as pd
import pytest

import alvos
import autotrader
import db
import dca
import mercado
import signal_engine
import simulador
from conftest import semear_posicao, semear_sinal


@pytest.fixture
def cliente(banco):
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app, client=("127.0.0.1", 5555))


def _banca():
    return db.get_banca()["atual"]


def _n(tabela, where=""):
    with db.conectar() as c:
        return c.execute(f"SELECT COUNT(*) FROM {tabela} {where}").fetchone()[0]


def _status(sid):
    with db.conectar() as c:
        return c.execute("SELECT status FROM sinais WHERE id=?", (sid,)).fetchone()[0]


# ====================================================================== tp
@pytest.mark.parametrize("chave,valor", [
    ("tp_fracoes", "-0.5,1.5"),        # soma 1, primeira fracao negativa: creditava dinheiro
    ("tp_fracoes", "0,1"),             # fracao zero: parcial de nada
    ("tp_fracoes", "nan,0.5"),
    ("tp_fracoes", "0.5,abc"),
    ("tp_fracoes", ""),
    ("tp_fracoes", "0.2,0.2,0.2,0.2,0.2,0.2"),   # mais alvos do que `tp_n` admite
    ("tp_fallback_r", "-2,4"),         # alvo do lado do prejuizo: "batia" na hora
    ("tp_fallback_r", "0,2"),          # alvo em cima da entrada
    ("tp_fallback_r", "inf"),
])
def test_tp_config_de_alvo_invalida_e_recusada(cliente, chave, valor):
    r = cliente.post("/config", json={chave: valor})
    assert r.status_code == 422, r.text
    assert db.get_config()[chave] == db.CONFIG_PADRAO[chave]      # nada foi gravado


def test_tp_config_valida_continua_aceita(cliente):
    r = cliente.post("/config", json={"tp_fracoes": "0.5, 0.25,0.25", "tp_fallback_r": "1.5,3,6"})
    assert r.status_code == 200, r.text
    cfg = alvos.cfg_tp(db.get_config())
    assert cfg["tp_fracoes"] == [0.5, 0.25, 0.25] and cfg["tp_fallback_r"] == [1.5, 3.0, 6.0]


@pytest.mark.parametrize("frac", [-0.5, 0.0, 1.0, 1.5, float("nan")])
def test_tp_fechar_parcial_recusa_fracao_fora_de_0_1(banco, sem_rede, frac):
    """A defesa em profundidade: mesmo com lixo ja gravado no plano da posicao, uma fracao que
    nao e parte de um todo nao mexe em banca nem em margem."""
    pid = semear_posicao(valor_reais=100.0, alavancagem=2, stop=95.0)
    with db.conectar() as c:
        pos = dict(c.execute("SELECT * FROM posicoes WHERE id=?", (pid,)).fetchone())
    antes = _banca()
    with pytest.raises(ValueError):
        simulador.fechar_parcial(pos, frac, "tp1", 110.0, {"niveis": []})
    assert _banca() == antes
    with db.conectar() as c:
        assert c.execute("SELECT valor_reais FROM posicoes WHERE id=?", (pid,)).fetchone()[0] == 100.0
    assert _n("trades") == 0


def test_tp_politica_com_lixo_no_banco_cai_no_padrao(banco):
    """Config gravada antes da validacao existir (ou por fora da rota) nao vira plano de TP."""
    with db.conectar() as c:
        c.execute("UPDATE config SET valor='-0.5,1.5' WHERE chave='tp_fracoes'")
        c.execute("UPDATE config SET valor='-2,0' WHERE chave='tp_fallback_r'")
    cfg = alvos.cfg_tp(db.get_config())
    assert cfg["tp_fracoes"] == [0.34, 0.33, 0.33]
    assert cfg["tp_fallback_r"] == [2.0, 4.0, 6.0]


def test_tp_plano_gravado_com_fracao_ruim_nao_credita(banco, sem_rede):
    """Ponta a ponta: plano ja gravado na posicao com fracao negativa (config antiga). O ciclo
    de marcacao nao pode mexer na banca por causa dele."""
    db.set_config("tp_ativo", "1")
    pid = semear_posicao(valor_reais=100.0, alavancagem=2, stop=95.0)
    plano = {"niveis": [{"preco": 105.0, "r": 1.0, "frac": -0.5, "feito": False, "fonte": "R"},
                        {"preco": 120.0, "r": 4.0, "frac": 1.5, "feito": False, "fonte": "R"}],
             "valor_inicial": 100.0, "r_preco": 5.0}
    with db.conectar() as c:
        c.execute("UPDATE posicoes SET tps=?, stop_abertura=95.0 WHERE id=?", (json.dumps(plano), pid))
    antes = _banca()
    sem_rede(106.0)                            # passou do "TP1"
    simulador.atualizar()
    assert _banca() == antes
    with db.conectar() as c:
        assert c.execute("SELECT valor_reais FROM posicoes WHERE id=?", (pid,)).fetchone()[0] == 100.0


# ================================================================= entrada
def _sem_tetos():
    db.set_config("exposicao_max", "0")       # o catalogo aceita: "0 = sem teto"
    db.set_config("risco_aberto_max", "0")


@pytest.mark.parametrize("abre", [simulador.abrir, simulador.colocar_ordem])
def test_entrada_margem_nunca_passa_da_banca_mesmo_sem_teto(banco, sem_rede, abre):
    """`exposicao_max=0` desliga o teto de CONFIGURACAO, nao a aritmetica: margem e dinheiro que
    a conta tem de ter. Banca 1000, margem pedida 5000."""
    _sem_tetos()
    sid = semear_sinal(preco=100.0, stop=95.0)
    with pytest.raises(ValueError, match="teto de margem"):
        abre(sid, 5000.0, 2)
    assert _status(sid) == "novo"             # recusa por teto nao consome o sinal
    assert _n("posicoes") == 0 and _n("ordens") == 0


@pytest.mark.parametrize("abre", [simulador.abrir, simulador.colocar_ordem])
def test_entrada_margem_somada_as_abertas_nao_passa_da_banca(banco, sem_rede, abre):
    _sem_tetos()
    semear_posicao(ativo="ETH/USDT", valor_reais=700.0, alavancagem=1, stop=None)
    sid = semear_sinal(preco=100.0, stop=95.0)
    with pytest.raises(ValueError, match="teto de margem"):
        abre(sid, 400.0, 2)                   # 700 + 400 > 1000
    assert _status(sid) == "novo"


@pytest.mark.parametrize("abre", [simulador.abrir, simulador.colocar_ordem])
@pytest.mark.parametrize("lev", [0.5, 126, 500])
def test_entrada_alavancagem_fora_do_que_a_corretora_oferece(banco, sem_rede, abre, lev):
    """Stop a 0,05% da entrada: a geometria stop x liquidacao deixava 500x passar (0,9/0,0005 =
    1800x). 0,5x nem existe como alavancagem. A faixa e a fisica da corretora (1x a 125x), nao
    uma politica de risco: quem aperta mais que isso e a config do dono."""
    sid = semear_sinal(preco=100.0, stop=99.95)
    with pytest.raises(ValueError, match="alavancagem"):
        abre(sid, 50.0, lev)
    assert _status(sid) == "novo"
    assert _n("posicoes") == 0 and _n("ordens") == 0


def test_entrada_alavancagem_na_borda_continua_valendo(banco, sem_rede):
    sid = semear_sinal(preco=100.0, stop=99.95)
    assert simulador.abrir(sid, 50.0, 125) > 0
    sid = semear_sinal(ativo="ETH/USDT", preco=100.0, stop=95.0)
    assert simulador.abrir(sid, 50.0, 1) > 0


# ================================================================== panico
def test_panico_no_meio_do_ciclo_do_bot_nao_deixa_posicao(cliente, sem_rede, monkeypatch):
    """O bot leu `auto_trade=1`, escolheu o sinal e foi buscar o preco na rede. Nesse intervalo
    o dono aperta o panico. Quando a rede responde, o bot NAO pode abrir: o panico ja passou e
    nao volta para fechar o que nasceu depois dele."""
    db.set_config("auto_trade", "1")
    db.set_config("tendencia_filtro", "off")
    db.set_config("exigir_fluxo", "0")
    sid = semear_sinal(preco=100.0, stop=95.0, conviccao=90)
    apertou = {"n": 0}

    def preco_lento(ativo):
        if not apertou["n"]:                  # o panico chega enquanto o bot esta na rede
            apertou["n"] += 1
            assert cliente.post("/panico").json()["auto_desligado"] is True
        return 100.0

    monkeypatch.setattr(simulador, "preco_ao_vivo", preco_lento)
    res = autotrader.auto_executar([])
    assert apertou["n"] == 1, "o cenario nao exercitou a corrida"
    assert res["abertos"] == []
    assert _n("posicoes", "WHERE status='aberta'") == 0
    assert _n("ordens", "WHERE status='pendente'") == 0
    assert _status(sid) == "novo"             # a recusa nao consome o sinal


def test_panico_idem_no_caminho_post_only(cliente, sem_rede, monkeypatch):
    db.set_config("auto_trade", "1")
    db.set_config("tendencia_filtro", "off")
    db.set_config("exigir_fluxo", "0")
    db.set_config("exec_modo", "post_only")
    semear_sinal(preco=100.0, stop=95.0, conviccao=90)
    apertou = {"n": 0}

    def preco_lento(ativo):
        if not apertou["n"]:
            apertou["n"] += 1
            cliente.post("/panico")
        return 100.0

    monkeypatch.setattr(simulador, "preco_ao_vivo", preco_lento)
    autotrader.auto_executar([])
    assert apertou["n"] == 1
    assert _n("ordens", "WHERE status='pendente'") == 0


def test_entrada_manual_nao_depende_do_bot_estar_ligado(banco, sem_rede):
    """A trava nova vale so para quem abre EM NOME do bot: o dono confirma sinal a mao com o
    auto-trader desligado, que e o estado normal do fluxo manual."""
    assert db.get_config()["auto_trade"] == "0"
    sid = semear_sinal(preco=100.0, stop=95.0)
    tipo, pid = simulador.executar(sid, 50.0, 2)
    assert tipo == "posicao" and pid > 0


# ==================================================================== scan
def test_scan_dois_ao_mesmo_tempo_nao_duplicam_sinal(banco, monkeypatch):
    """Worker e `POST /scan` no mesmo instante: cada um via a fila vazia, e os dois gravavam o
    mesmo sinal. O dedupe e leitura + escrita, entao precisa de exclusao mutua."""
    db.set_config("ativos", "BTC/USDT")
    db.set_config("timeframes", "15m")
    sinal = dict(ativo="BTC/USDT", tf="15m", tipo="tendencia", direcao="LONG", conviccao=80,
                 motivos="x", preco=100.0, stop_sugerido=95.0, adx=30, n_fatores=3, vela_ms=1)
    monkeypatch.setattr(signal_engine, "analisa", lambda a, tf: [dict(sinal)])
    monkeypatch.setattr(signal_engine, "confirmado", lambda s, a, cfg: (True, "confirmado"))
    monkeypatch.setattr(signal_engine, "marcar_desfechos", lambda *a, **k: 0)
    gravar = signal_engine._gravar

    def gravar_devagar(*a, **k):              # abre a janela entre o "ja existe?" e o INSERT
        time.sleep(0.25)
        return gravar(*a, **k)

    monkeypatch.setattr(signal_engine, "_gravar", gravar_devagar)
    ts = [threading.Thread(target=signal_engine.scan) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(20)
    assert _n("sinais", "WHERE status='novo'") == 1


# =================================================================== borda
@pytest.mark.parametrize("rota", [
    "/candles?ativo=BTC%2FUSDT&tf=7m",
    "/candles?ativo=..%2F..%2Fetc&tf=15m",
    "/candles?ativo=BTC%2FUSDT&tf=15m&limite=0",
    "/analise?ativo=BTC%2FUSDT&tf=banana",
    "/analise?ativo=BTC%2FUSDT&tf=15m&limite=100000000",
    "/analise?ativo=BTC%2FUSDT&tf=15m&limite=-1",
    "/analise?ativo=%3Cscript%3E&tf=15m",
    "/book?ativo=btc-usdt",
    "/smartmoney?ativo=BTC",
    "/precos?ativos=" + ",".join(f"A{i}/USDT" for i in range(200)),
    "/precos?ativos=BTC%2FUSDT,lixo",
])
def test_borda_rota_de_mercado_valida_antes_de_ir_a_rede(cliente, monkeypatch, rota):
    """Par, timeframe e limite iam crus para o ccxt: o erro voltava como 500 com a excecao da
    corretora, e `/analise` aceitava o `limite` que o `/trades` ja recusa. Nenhuma destas
    requisicoes pode chegar a sair da maquina."""
    def rede(*a, **k):
        raise AssertionError("foi a rede com entrada invalida")

    for nome in ("fetch_ohlcv", "fetch_tickers", "fetch_order_book", "fetch_trades"):
        monkeypatch.setattr(mercado.ex_spot, nome, rede, raising=False)
    monkeypatch.setattr(mercado.ex_fut, "fetch_funding_rate", rede, raising=False)
    r = cliente.get(rota)
    assert r.status_code == 422, (r.status_code, r.text[:200])


def test_borda_sem_senha_recusa_requisicao_de_outro_site(cliente):
    """Modo local, sem DASH_PASS: o backend so atende loopback, mas o NAVEGADOR do dono tambem
    e loopback. Uma pagina qualquer aberta nele conseguia mandar POST /reset para
    127.0.0.1:8000. Quem denuncia e o cabecalho Origin, que o navegador sempre manda em POST."""
    import api
    assert not api.DASH_PASS, "este teste e do modo sem senha"
    antes = _banca()
    r = cliente.post("/reset", json={"confirmar": "RESET"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403, r.text
    r = cliente.post("/panico", headers={"Origin": "null"})          # iframe sandbox / file://
    assert r.status_code == 403
    r = cliente.get("/estado", headers={"Origin": "http://evil.example:8000"})
    assert r.status_code == 403
    assert _banca() == antes


@pytest.mark.parametrize("origem", ["http://localhost:8000", "http://127.0.0.1:8000",
                                    "http://[::1]:8000", None])
def test_borda_sem_senha_o_proprio_painel_local_continua_entrando(cliente, origem):
    r = cliente.get("/estado", headers={"Origin": origem} if origem else {})
    assert r.status_code == 200, r.text


def test_borda_ip_do_cliente_e_o_que_o_proxy_escreveu_nao_o_que_o_cliente_mandou():
    """Proxy que ANEXA ao X-Forwarded-For entrega "forjado, real". Ler o primeiro item deixava
    quem erra a senha trocar de "IP" a cada tentativa e nunca cair no bloqueio."""
    import api

    class Req:
        def __init__(self, peer, xff):
            self.client = type("C", (), {"host": peer})()
            self.headers = {"x-forwarded-for": xff} if xff else {}

    assert api._cliente_ip(Req("127.0.0.1", "1.2.3.4, 203.0.113.9")) == "203.0.113.9"
    assert api._cliente_ip(Req("127.0.0.1", "203.0.113.9")) == "203.0.113.9"
    assert api._cliente_ip(Req("198.51.100.7", "1.2.3.4")) == "198.51.100.7"   # sem proxy nosso
    assert api._cliente_ip(Req("127.0.0.1", "")) == "127.0.0.1"


# ================================================================= segredo
TOKEN = "123456:AAH-segredo-do-bot"


def test_segredo_token_do_telegram_nao_sai_em_nenhuma_resposta(cliente):
    r = cliente.post("/config", json={"telegram_token": TOKEN, "telegram_chat_id": "42"})
    assert r.status_code == 200 and TOKEN not in r.text
    assert db.get_config()["telegram_token"] == TOKEN                 # gravou o de verdade
    for rota in ("/estado", "/config", "/config/auditoria?limite=500"):
        corpo = cliente.get(rota).text
        assert TOKEN not in corpo, rota
    assert cliente.get("/estado").json()["config"]["telegram_token"]  # a tela ainda sabe que EXISTE


def test_segredo_devolver_a_mascara_nao_apaga_o_token(cliente):
    cliente.post("/config", json={"telegram_token": TOKEN})
    mascara = cliente.get("/config").json()["telegram_token"]
    r = cliente.post("/config", json={"telegram_token": mascara, "min_conviccao": "56"})
    assert r.status_code == 200
    cfg = db.get_config()
    assert cfg["telegram_token"] == TOKEN and float(cfg["min_conviccao"]) == 56


def test_segredo_vazio_continua_vazio(cliente):
    assert cliente.get("/estado").json()["config"]["telegram_token"] == ""
    cliente.post("/config", json={"telegram_token": TOKEN})
    cliente.post("/config", json={"telegram_token": ""})              # apagar continua possivel
    assert db.get_config()["telegram_token"] == ""


# ================================================================= mercado
class _ExLote:
    """ccxt de mentira: como o de verdade, recusa o LOTE inteiro se um simbolo nao existe."""
    def __init__(self):
        self.markets = {"BTC/USDT": {}, "ETH/USDT": {}}
        self.pedidos = []

    def fetch_tickers(self, simbolos):
        self.pedidos.append(list(simbolos))
        ruins = [s for s in simbolos if s not in self.markets]
        if ruins:
            raise RuntimeError(f"binance does not have market symbol {ruins[0]}")
        return {s: {"last": 100.0, "percentage": 1.0} for s in simbolos}


def test_mercado_um_par_inexistente_nao_derruba_o_lote(monkeypatch):
    ex = _ExLote()
    monkeypatch.setattr(mercado, "ex_spot", ex)
    mercado._tcache.clear()
    p = mercado.precos(["BTC/USDT", "NAOEXISTE/USDT", "ETH/USDT"])
    assert p == {"BTC/USDT": 100.0, "ETH/USDT": 100.0}
    assert ex.pedidos == [["BTC/USDT", "ETH/USDT"]]
    mercado._tcache.clear()


def test_mercado_cache_de_ticker_aguenta_duas_threads(monkeypatch):
    """Worker e rotas da API varrem o mesmo cache. Com `del` sobre uma lista de vencidos
    calculada antes, a segunda thread levantava KeyError (500 no /precos, DCA zerado)."""
    ex = _ExLote()
    monkeypatch.setattr(mercado, "ex_spot", ex)
    erros = []

    def martela():
        try:
            for _ in range(300):
                mercado._tcache["BTC/USDT"] = (0.0, {"last": 1.0})     # sempre vencido
                mercado._tcache["ETH/USDT"] = (0.0, {"last": 1.0})
                mercado.precos(["BTC/USDT", "ETH/USDT"])
        except Exception as e:                                         # noqa: BLE001
            erros.append(repr(e))

    ts = [threading.Thread(target=martela) for _ in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    mercado._tcache.clear()
    assert erros == []


def test_mercado_dca_recusa_par_que_a_corretora_nao_lista(banco, monkeypatch):
    monkeypatch.setattr(mercado, "ex_spot", _ExLote())
    with pytest.raises(ValueError, match="não existe"):
        dca.criar("NAOEXISTE/USDT", 100, 7)
    assert dca.criar("BTC/USDT", 100, 7) is True


def test_mercado_dca_sem_tabela_de_mercados_nao_trava_a_criacao(banco, monkeypatch):
    """Antes do primeiro contato com a corretora o ccxt nao sabe o que existe. Recusar ai seria
    trocar um par ruim por plano nenhum quando a rede cai."""
    ex = _ExLote()
    ex.markets = None
    monkeypatch.setattr(mercado, "ex_spot", ex)
    assert dca.criar("QUALQUER/USDT", 100, 7) is True


def test_mercado_dca_remover_o_que_nao_existe_diz_que_nao_removeu(cliente):
    r = cliente.post("/dca/remover", json={"id": 99999}).json()
    assert r["ok"] is False


# ==================================================================== front
def test_front_o_panico_nao_diz_mais_que_a_ordem_pendente_sobrevive():
    """O backend cancela as ordens post-only no panico desde a PR #27; os dois apps ainda
    avisavam o contrario, no dialogo da acao mais critica do sistema."""
    import os
    web = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "app")
    for arq in ("casca.js", os.path.join("m", "app.js")):
        txt = open(os.path.join(web, arq), encoding="utf-8").read()
        assert "NÃO é cancelada" not in txt and "NÃO são canceladas" not in txt, arq
        assert "ordens_canceladas" in txt, arq + ": o resultado do panico tem de dizer quantas cancelou"
