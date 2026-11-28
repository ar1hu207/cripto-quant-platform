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
from conftest import semear_equity, semear_posicao, semear_sinal


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


# =================================================================== leva2
def test_leva2_rotulo_do_fear_greed_nao_e_texto_de_terceiro(monkeypatch):
    """O `value_classification` da alternative.me era repassado cru e o painel classico o
    escrevia em innerHTML: HTML de terceiro na pagina onde mora a credencial."""
    import io

    def falso(url, timeout=0):
        corpo = b'{"data":[{"value":"73","value_classification":"<img src=x onerror=alert(1)>"}]}'
        return io.BytesIO(corpo)

    monkeypatch.setattr(mercado.urllib.request, "urlopen", falso)
    fg = mercado.fear_greed()
    assert fg == {"valor": 73, "label": "Greed"}
    for v, rot in ((0, "Extreme Fear"), (24, "Extreme Fear"), (30, "Fear"), (50, "Neutral"),
                   (60, "Greed"), (90, "Extreme Greed"), (100, "Extreme Greed")):
        assert mercado._rotulo_fg(v) == rot


def test_leva2_panico_diz_qual_posicao_nao_fechou(cliente, sem_rede, monkeypatch):
    """A falha de uma posicao nao interrompe as outras, mas tambem nao pode sumir: a resposta
    dizia so `fechadas`, e a tela anunciava sucesso com uma posicao viva."""
    boa = semear_posicao(ativo="BTC/USDT")
    ruim = semear_posicao(ativo="ETH/USDT")
    fechar = simulador.fechar

    def fechar_com_defeito(pid, motivo, preco_saida=None):
        if pid == ruim:
            raise RuntimeError("corretora fora do ar")
        return fechar(pid, motivo, preco_saida)

    monkeypatch.setattr(simulador, "fechar", fechar_com_defeito)
    r = cliente.post("/panico").json()
    assert r["fechadas"] == 1 and r["auto_desligado"] is True
    assert r["ok"] is False and [f["ativo"] for f in r["falhas"]] == ["ETH/USDT"]
    with db.conectar() as c:
        vivas = [x["id"] for x in c.execute("SELECT id FROM posicoes WHERE status='aberta'")]
    assert vivas == [ruim] and boa not in vivas


def test_leva2_panico_sem_falha_continua_ok(cliente, sem_rede):
    semear_posicao()
    r = cliente.post("/panico").json()
    assert r["ok"] is True and r["falhas"] == [] and r["fechadas"] == 1


def test_leva2_config_js_servido_pelo_backend_aponta_para_ele_mesmo(cliente):
    """O `web/config.js` versionado e o do Vercel e aponta para a PRODUCAO. Servido pelo
    backend, fazia o painel local (localhost:8000) operar a producao."""
    r = cliente.get("/config.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert r.text.strip() == 'window.API_BASE = "";'
    assert "ts.net" not in r.text and "http" not in r.text


def test_leva2_front_nao_reenvia_post_depois_do_login_nem_some_com_recusa():
    import os
    web = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
    ler = lambda *p: open(os.path.join(web, *p), encoding="utf-8").read()   # noqa: E731
    api_js = ler("app", "api.js")
    assert "A ação NÃO foi enviada" in api_js            # POST que tomou 401 nao e refeito sozinho
    assert ".replace(/'/g, '&#39;')" in api_js           # esc() cobre atributo de aspas simples
    for arq in (("app", "casca.js"), ("app", "m", "app.js")):
        txt = ler(*arq)
        assert "r.falhas" in txt, arq                    # panico incompleto aparece
        assert "hasOwnProperty" in txt, arq              # #constructor nao e rota


def test_leva2_a_suite_nao_escreve_no_log_nem_no_banco_da_raiz():
    import os
    import logbot
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.dirname(os.path.abspath(logbot.LOG_FILE)) != raiz
    assert os.path.dirname(os.path.abspath(os.environ["DB_PATH"])) != raiz


# =================================================================== leva3
# Furos da rodada adversarial independente (subagente, 2026-11-14), cada um provado antes.
class _ConComFechamento:
    """Conexao que, logo depois de ler a banca, deixa "a outra thread" fechar uma posicao."""
    def __init__(self, con, aoLerBanca):
        self._c, self._ao = con, aoLerBanca

    def execute(self, sql, *a):
        r = self._c.execute(sql, *a)
        if "FROM banca" in sql and self._ao:
            linhas = r.fetchall()
            ao, self._ao = self._ao, None
            ao()
            return type("Cur", (), {"fetchone": lambda s: linhas[0]})()
        return r


def _fechar_no_meio_da_leitura(monkeypatch, pid, motivo):
    from contextlib import contextmanager
    original, feito = db.conectar, {"v": False}

    def fecha():
        feito["v"] = True
        monkeypatch.setattr(db, "conectar", original)
        assert simulador.fechar(pid, motivo, 110.0) == pytest.approx(99.0)

    @contextmanager
    def conectar():
        with original() as con:
            yield _ConComFechamento(con, None if feito["v"] else fecha)

    monkeypatch.setattr(db, "conectar", conectar)
    return original, feito


def test_leva3_trava_nao_dispara_por_leitura_rasgada(banco, sem_rede, monkeypatch):
    """Um vencedor fecha entre a leitura da banca e a do unreal: nada foi perdido, e a trava
    (sticky ate a virada) disparava. Agora as leituras saem de um retrato so."""
    pid = semear_posicao(valor_reais=100, alavancagem=10, entrada=100, stop=95,
                         preco_atual=110, pnl=99.0)
    semear_equity(str(pd.Timestamp.now().date()) + " 00:00:01", 1099.0)
    original, feito = _fechar_no_meio_da_leitura(monkeypatch, pid, "trailing")
    g = simulador.guarda_risco()
    monkeypatch.setattr(db, "conectar", original)
    assert feito["v"], "o cenario nao exercitou a corrida"
    assert g["trava_dia"] is False and db.get_config()["trava_dia_em"] == ""
    assert g["pnl_dia"] == pytest.approx(0.0)


def test_leva3_snapshot_de_equity_nao_rasga(banco, sem_rede, monkeypatch):
    import api
    pid = semear_posicao(valor_reais=100, alavancagem=10, entrada=100, stop=95, preco_atual=110, pnl=99.0)
    original, feito = _fechar_no_meio_da_leitura(monkeypatch, pid, "manual")
    banca, equity = api._banca_e_equity()
    monkeypatch.setattr(db, "conectar", original)
    assert feito["v"] and equity == pytest.approx(1099.0)


def test_leva3_dois_tps_no_mesmo_ciclo_conservam_o_risco_de_abertura(banco, sem_rede, monkeypatch):
    db.set_config("tp_ativo", "1")
    db.set_config("trailing_ativo", "0")
    monkeypatch.setattr(simulador, "_precos_em_lote", lambda ativos: {})
    niv = [{"preco": p, "r": r, "frac": f, "feito": False, "forca": 2, "fonte": "R"}
           for p, r, f in ((110.0, 2.0, 0.34), (120.0, 4.0, 0.33), (130.0, 6.0, 0.33))]
    plano = json.dumps({"niveis": niv, "valor_inicial": 300.0, "r_preco": 5.0})
    pid = semear_posicao(ativo="X/USDT", valor_reais=300.0, alavancagem=3, stop=95.0)
    with db.conectar() as c:
        c.execute("UPDATE posicoes SET stop_abertura=95, risco_abertura=45, tps=? WHERE id=?", (plano, pid))
    sem_rede(121.0)                                  # passou TP1 e TP2 no mesmo poll
    simulador.atualizar()
    with db.conectar() as c:
        t = [dict(r) for r in c.execute("SELECT motivo_saida,risco_abertura FROM trades ORDER BY id")]
        resto = c.execute("SELECT risco_abertura FROM posicoes WHERE id=?", (pid,)).fetchone()[0]
    assert [x["motivo_saida"] for x in t] == ["tp1", "tp2"]
    assert sum(x["risco_abertura"] for x in t) + resto == pytest.approx(45.0, abs=0.01)


@pytest.mark.parametrize("preco", [0.00001234, 0.0000008])
def test_leva3_stop_de_moeda_de_preco_baixo_mantem_a_distancia(banco, sem_rede, preco):
    sem_rede(preco)
    sid = semear_sinal(ativo="PEPE/USDT", preco=preco, stop=preco * 0.95)
    pid = simulador.abrir(sid, 20, 2)
    with db.conectar() as c:
        p = dict(c.execute("SELECT entrada,stop FROM posicoes WHERE id=?", (pid,)).fetchone())
    assert (p["entrada"] - p["stop"]) / p["entrada"] == pytest.approx(0.05, rel=0.01)


def test_leva3_arredondamento_nao_muda_preco_de_1_para_cima():
    for x in (67123.456789123, 104.50000000000001, 1.0, 33.3333333333):
        assert mercado.arred_preco(x) == round(x, 6)
        assert mercado.arred_preco(x, 8) == round(x, 8)
    assert mercado.arred_preco(0.0000123456789) == pytest.approx(0.0000123456789, rel=1e-7)


def test_leva3_bot_usa_o_orcamento_que_ele_mesmo_calculou(banco, sem_rede):
    db.set_config("auto_trade", "1")
    db.set_config("tendencia_filtro", "off")
    db.set_config("exigir_fluxo", "0")
    db.set_config("risco_aberto_max", "0")
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=1000.337 WHERE id=1")      # teto de margem = 500,1685
    semear_posicao(ativo="ETH/USDT", valor_reais=400.0, alavancagem=2, entrada=100, stop=99)
    semear_sinal(ativo="BTC/USDT", preco=100.0, stop=99.0)
    res = autotrader.auto_executar()                 # orcamento 100,1685: round() dava 100,17
    assert len(res["abertos"]) == 1, res["rejeitados"]


def test_leva3_config_recusa_piso_de_alavancagem_acima_do_teto(cliente):
    """Cada chave cabia na propria faixa e a dupla invertida entrava; no `_alavancagem` o piso
    vence o teto de proposito (test_sizing trava), entao o "teto" deixava de ser teto. A recusa
    e na ENTRADA, e cruza com o valor ja gravado quando so uma das duas vem no corpo."""
    r = cliente.post("/config", json={"auto_lev_min": "10", "auto_lev_max": "3"})
    assert r.status_code == 422 and "auto_lev_min" in r.text
    assert cliente.post("/config", json={"auto_lev_min": "30"}).status_code == 422   # teto gravado: 20
    assert cliente.post("/config", json={"auto_lev_max": "1"}).status_code == 422    # piso gravado: 2
    cfg = db.get_config()
    assert (float(cfg["auto_lev_min"]), float(cfg["auto_lev_max"])) == (2.0, 20.0)   # nada gravado
    assert cliente.post("/config", json={"auto_lev_min": "3", "auto_lev_max": "3"}).status_code == 200
    assert cliente.post("/perfil", json={"perfil": "conservador"}).status_code == 200


def test_leva3_confirmar_sem_alavancagem_usa_a_config(cliente, sem_rede):
    db.set_config("alavancagem_padrao", "2")
    sid = semear_sinal(stop=95.0)
    r = cliente.post("/confirmar", json={"sinal_id": sid, "valor_reais": 20}).json()
    assert r["ok"] is True, r
    with db.conectar() as c:
        lev = c.execute("SELECT alavancagem FROM posicoes WHERE id=?", (r["posicao_id"],)).fetchone()[0]
    assert lev == 2.0


def test_leva3_precheck_do_confirmar_mede_o_mesmo_risco_que_o_abrir(cliente, sem_rede):
    semear_posicao(valor_reais=100, alavancagem=10, entrada=100, stop=92)     # risco 80 de 100
    sid = semear_sinal(preco=100.0, stop=95.0)
    sem_rede(110.0)                                  # risco real: 100 x 2 x 5% = 10 -> 90 <= 100
    r = cliente.post("/confirmar", json={"sinal_id": sid, "valor_reais": 100, "alavancagem": 2}).json()
    assert r["ok"] is True, r


def test_leva3_tendencia_vazia_e_falha_e_nao_fica_no_cache(monkeypatch):
    import tendencia
    queda = [[i * tendencia.DIA_MS, 0, 0, 0, 200.0 - i, 0] for i in range(120)]
    respostas = [[], queda]
    monkeypatch.setattr(tendencia, "_velas_1d",
                        lambda ativo: respostas.pop(0) if len(respostas) > 1 else respostas[0])
    monkeypatch.setattr(tendencia, "_cache", {})
    agora = 121 * tendencia.DIA_MS
    with pytest.raises(RuntimeError):                # vazio = falha: o bot pula o candidato
        tendencia.permite("Z/USDT", "LONG", "d1", agora)
    assert tendencia.permite("Z/USDT", "LONG", "d1", agora + 60_000) is False


def test_leva3_perfil_grava_tudo_ou_nada(banco, monkeypatch):
    antes = db.get_config()
    auditar, n = db._auditar_config, {"v": 0}

    def trava_na_terceira(c, chave, valor, origem):
        n["v"] += 1
        if n["v"] == 3:
            raise RuntimeError("database is locked")
        return auditar(c, chave, valor, origem)

    monkeypatch.setattr(db, "_auditar_config", trava_na_terceira)
    with pytest.raises(RuntimeError):
        db.set_configs(db.PERFIS_RISCO["conservador"], "teste")
    monkeypatch.setattr(db, "_auditar_config", auditar)
    depois = db.get_config()
    assert {k for k in depois if not db._igual_cfg(antes.get(k), depois[k])} == set()
    assert _n("config_auditoria") == 0


def test_leva3_perfil_inteiro_continua_sendo_aplicado(cliente):
    r = cliente.post("/perfil", json={"perfil": "conservador"})
    assert r.status_code == 200 and r.json()["perfil_ativo"] == "conservador"


def test_leva3_panico_fecha_todas_mesmo_com_mais_de_200(cliente, sem_rede):
    for _ in range(205):
        semear_posicao(valor_reais=1.0)
    r = cliente.post("/panico").json()
    assert r["fechadas"] == 205 and _n("posicoes", "WHERE status='aberta'") == 0


def test_leva3_dca_gigante_e_recusado_e_o_estado_segue_de_pe(cliente, sem_rede):
    r = cliente.post("/dca", json={"ativo": "BTC/USDT", "valor_aporte": 1e308, "freq_dias": 1}).json()
    assert r["ok"] is False and _n("dca") == 0
    assert cliente.get("/estado").status_code == 200


@pytest.mark.parametrize("rota,corpo", [("/fechar", {"id": 2 ** 64}), ("/pular", {"id": 2 ** 64}),
                                        ("/dca/aportar", {"id": 2 ** 64}), ("/fechar", {"id": 0}),
                                        ("/confirmar", {"sinal_id": 2 ** 64, "valor_reais": 20, "alavancagem": 2})])
def test_leva3_id_fora_da_faixa_e_422_e_nao_500(cliente, sem_rede, rota, corpo):
    assert cliente.post(rota, json=corpo).status_code == 422


def test_leva3_testeB_health_publico_so_em_GET(cliente, monkeypatch):
    import api
    monkeypatch.setattr(api, "DASH_PASS", "senha-de-teste")
    visto = []
    monkeypatch.setattr(api, "_repassar_b", lambda m, c, q, corpo, a, ct:
                        (visto.append((m, c)) or (200, b"{}", "application/json")))
    assert cliente.post("/testeB/health", content=b"x" * 100_000).status_code == 401
    assert visto == []                               # nada foi repassado sem credencial
    assert cliente.get("/testeB/health").status_code == 200 and visto == [("GET", "health")]


def test_leva3_testeB_com_caminho_estranho_nao_e_500(cliente, monkeypatch):
    import http.client

    def sem_rede_aqui(self):
        raise OSError("sem rede no teste")

    monkeypatch.setattr(http.client.HTTPConnection, "connect", sem_rede_aqui)
    assert cliente.get("/testeB/a%20b").status_code == 502     # era 500 (InvalidURL)
