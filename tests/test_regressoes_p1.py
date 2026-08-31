# -*- coding: utf-8 -*-
"""Criterio 3 do [P2-6]: "cada bug corrigido nos cards P1 ganha um teste de regressao".

A maior parte ja tinha: `prova_m1.py` cobre P1-1, P1-6, P1-7 e P1-8, e `api._prova_api()`
cobre P1-4 -- as duas sao executadas pela suite em `test_provas_existentes.py`, e repetir as
asseracoes aqui seria duplicar regressao (a decisao 1 da §4c do plano). O que sobrava sem
nenhuma prova automatizada eram tres, e sao estes:

    P1-3  `/candles` e `/trades` sem teto no `limite`
    P1-5  `breadth()` contava o ativo antes de ter um numero dele
    P1-9  janela de vida do sinal, nas duas pontas (dedupe e expiracao)

Fica de fora, declarado: **P1-2** e uma linha em `web/index.html` (o
`localStorage.removeItem('cbAuth')`). E front, nao e Python, e `web/` nao e territorio do
T-TESTE -- a verificacao dele e por hash do HTML em producao (CLAUDE.md §7).
"""
import time

import pandas as pd
import pytest

import db
import mercado
import signal_engine
import simulador
from conftest import semear_posicao, semear_sinal


# ================================================================ [P1-3] teto do `limite`

@pytest.fixture
def cliente(banco):
    """TestClient sem `with`: o `lifespan` -- e portanto a thread do worker -- nao sobe.

    `client=("127.0.0.1", ...)` porque o peer padrao do TestClient ("testclient") nao e
    loopback, e sem `DASH_PASS` o app responde 503 a tudo que venha de fora (o [P0-1]).
    Mesmo motivo, e mesma solucao, do `test_auth.py`.
    """
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app, client=("127.0.0.1", 5555))


@pytest.mark.parametrize("rota,limite", [
    ("/candles", 1001), ("/candles", 50000), ("/candles", 0), ("/candles", -1),
    ("/trades", 501), ("/trades", 0),
])
def test_limite_fora_da_faixa_e_recusado_na_borda(cliente, rota, limite):
    """[P1-3] O teto vive no `Query(..., ge=, le=)`, entao a recusa acontece ANTES de
    qualquer chamada a corretora ou ao banco -- por isso este teste nao precisa de rede.
    Sem o teto, `limite=50000` virava um fetch gigante (ou um 500 vindo do ccxt) disparado
    por quem so digitou um numero na URL."""
    assert cliente.get(f"{rota}?limite={limite}").status_code == 422


def test_o_limite_no_teto_ainda_e_valido(cliente):
    """A faixa e fechada: 500 passa na validacao (e ai sim vai ao banco, que esta vazio)."""
    r = cliente.get("/trades?limite=500")
    assert r.status_code == 200 and r.json() == []


# ================================================================ [P1-5] breadth()

@pytest.fixture
def ativos_fake(banco, monkeypatch):
    """Troca o unico ponto do modulo que fala com o ccxt. `_tickers` ja devolve so o que
    voltou da corretora -- o ativo ausente simplesmente nao esta no dicionario."""
    def usar(tickers, ativos=None):
        db.set_config("ativos", ",".join(ativos or tickers.keys()))
        monkeypatch.setattr(mercado, "_tickers", lambda lista: tickers)
    return usar


def test_leitura_ausente_fica_fora_dos_tres_contadores(ativos_fake):
    """[P1-5] O bug era `tot += 1` antes de `soma += p`: o ativo cujo `percentage` vinha
    None ja tinha entrado no denominador quando o TypeError caia no except, e distorcia
    `pct_subindo` e `variacao_media` para baixo. A regra que o comentario do codigo hoje
    declara e "daqui pra baixo o ativo entra nos tres contadores ou em nenhum"."""
    ativos_fake({"BTC/USDT": {"percentage": 2.0},
                 "ETH/USDT": {"percentage": -1.0},
                 "SOL/USDT": {"percentage": None}},
                ativos=["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"])
    b = mercado.breadth()
    assert b["n"] == 2                                  # SOL (None) e XRP (ausente) ficam fora
    assert b["pct_subindo"] == 50                       # 1 de 2, nao 1 de 4
    assert b["variacao_media"] == pytest.approx(0.5)    # (2 - 1) / 2, nao / 4


def test_zero_por_cento_conta_como_leitura_valida_e_nao_como_subindo(ativos_fake):
    """`p is None` e a unica coisa que exclui. Um ativo parado e medicao: entra em `tot`
    e em `soma`, e nao entra em `up`."""
    ativos_fake({"BTC/USDT": {"percentage": 0.0}, "ETH/USDT": {"percentage": 4.0}})
    b = mercado.breadth()
    assert b["n"] == 2 and b["pct_subindo"] == 50 and b["variacao_media"] == pytest.approx(2.0)


def test_nenhuma_leitura_devolve_none_e_nunca_zero(ativos_fake):
    """`if not tot: return None`. Zero por cento subindo e uma AFIRMACAO sobre o mercado;
    a corretora fora do ar nao autoriza a fazer nenhuma."""
    ativos_fake({}, ativos=["BTC/USDT", "ETH/USDT"])
    assert mercado.breadth() is None


# ================================================================ [P1-9] janela do sinal

@pytest.mark.parametrize("tf,minutos", [
    ("5m", 20), ("15m", 60), ("1h", 240), ("4h", 960), ("1d", 5760),
    ("bagunca", 60), ("", 60), (None, 60),           # TF desconhecido cai no 15m
])
def test_a_janela_e_contada_em_velas_do_proprio_timeframe(tf, minutos):
    """[P1-9] Um sinal de 5m e um de 4h nao envelhecem no mesmo relogio. Fixar "60 min"
    para os dois -- que era o efeito de nao ter janela nenhuma por TF -- trata um sinal de
    4h como velho quatro velas antes da hora."""
    assert signal_engine.janela_min(tf) == minutos


def test_sinal_novo_fora_da_janela_vira_expirado(banco):
    """A outra ponta do card: sem isto o pendente de ontem seguia 'novo' para sempre, com
    preco e stop de ontem, disputando o ativo com o candidato de agora -- e tanto
    `/estado.pendentes` quanto o pool do auto-trader leem o banco, nao a tela."""
    agora = pd.Timestamp("2026-08-22 12:00:00")
    velho = semear_sinal(tf="15m", ts=str(agora - pd.Timedelta(minutes=61)))
    novo = semear_sinal(tf="15m", ts=str(agora - pd.Timedelta(minutes=59)))
    assert signal_engine.expirar_sinais(agora) == 1
    estados = {r["id"]: r["status"] for r in db.listar("sinais", 10)}
    assert estados[velho] == "expirado"
    assert estados[novo] == "novo"


def test_a_expiracao_respeita_a_janela_de_cada_timeframe(banco):
    """Roda por TF porque a janela e por TF: 90 minutos mata o sinal de 15m e nao encosta
    no de 4h."""
    agora = pd.Timestamp("2026-08-22 12:00:00")
    ts = str(agora - pd.Timedelta(minutes=90))
    curto = semear_sinal(tf="15m", ts=ts)
    longo = semear_sinal(tf="4h", ts=ts)
    signal_engine.expirar_sinais(agora)
    estados = {r["id"]: r["status"] for r in db.listar("sinais", 10)}
    assert (estados[curto], estados[longo]) == ("expirado", "novo")


@pytest.mark.parametrize("status", ["confirmado", "pulado", "rejeitado_fluxo"])
def test_a_expiracao_nao_reescreve_historico(banco, status):
    """`status='novo'` e o unico alvo. Reescrever 'rejeitado_fluxo' apagaria exatamente o
    que o [Q-4] esta medindo."""
    agora = pd.Timestamp("2026-08-22 12:00:00")
    sid = semear_sinal(tf="15m", ts=str(agora - pd.Timedelta(days=3)), status=status)
    assert signal_engine.expirar_sinais(agora) == 0
    assert db.listar("sinais", 1)[0]["status"] == status


def test_expirar_sem_sinal_nenhum_nao_quebra(banco):
    assert signal_engine.expirar_sinais(pd.Timestamp("2026-08-22 12:00:00")) == 0


# =========================================== [F-13] o custo de rede do ciclo, sem rede

class _ExContado:
    """Corretora de mentira que CONTA as chamadas. Nao existe rede aqui, de proposito.

    O `cronometrar()` do `signal_engine` mede TEMPO e precisa de rede -- e por isso ele e
    comando de linha, e nao teste: numero de parede depende de onde se roda. O que a suite
    trava e a outra metade da mesma medicao, a que E determinista: **quantas idas a rede o
    ciclo faz**. Uma requisicao que volte a nascer por posicao aparece aqui na hora, mesmo
    numa maquina lenta e sem internet.
    """

    def __init__(self):
        self.n = {}
        self.tfs = []          # [F-14] os timeframes pedidos, na ordem

    def _conta(self, nome):
        self.n[nome] = self.n.get(nome, 0) + 1

    @property
    def total(self):
        return sum(self.n.values())

    def fetch_ticker(self, ativo):
        self._conta("fetch_ticker")
        return {"last": 100.0}

    def fetch_tickers(self, ativos):
        self._conta("fetch_tickers")
        return {a: {"last": 100.0, "percentage": 1.0} for a in ativos}

    def fetch_ohlcv(self, ativo, timeframe=None, limit=200, since=None):
        self._conta("fetch_ohlcv")
        self.tfs.append(timeframe)
        # serie sintetica com deriva e ruido deterministico: o suficiente para EMA/RSI/ADX
        # sairem do warmup. O que este teste mede e a CONTAGEM, nao o veredito do indicador.
        #
        # Ancorada em AGORA, e nao numa data fixa, porque o cache do [F-10] vale ate a vela em
        # formacao FECHAR: com velas de 2023 toda entrada ja nasceria vencida e o teste passaria
        # sem exercitar o cache -- verde por nao medir nada.
        passo = signal_engine.TF_MIN.get((timeframe or "15m").strip(), 15) * 60_000
        abertura = int(time.time() * 1000) // passo * passo      # a vela em formacao abriu aqui
        n = limit or 200
        velas = []
        for k in range(n):
            base = 100.0 + k * 0.1 + (k % 7) * 0.05
            velas.append([abertura - (n - 1 - k) * passo, base, base * 1.003,
                          base * 0.997, base * 1.001, 1000.0 + (k % 5) * 10])
        return velas

    def fetch_order_book(self, ativo, n=100):
        self._conta("fetch_order_book")
        return {"bids": [[99.9 - i * 0.01, 1.0] for i in range(n)],
                "asks": [[100.1 + i * 0.01, 1.0] for i in range(n)]}

    def fetch_trades(self, ativo, limit=200):
        self._conta("fetch_trades")
        return [{"amount": 1.0, "price": 100.0, "side": "buy" if i % 2 else "sell"}
                for i in range(limit)]


@pytest.fixture
def corretora_contada(banco, monkeypatch):
    """Substitui os clientes ccxt dos TRES modulos do ciclo. Sao objetos distintos, criados
    no import de cada modulo: trocar so um deles daria uma contagem menor que a real."""
    fake = _ExContado()
    for modulo, nome in [(signal_engine, "ex"), (simulador, "ex"), (simulador, "ex_fut"),
                         (mercado, "ex_spot"), (mercado, "ex_fut")]:
        monkeypatch.setattr(modulo, nome, fake)
    mercado._tcache.clear()                       # cache de 5s nao pode vazar de outro teste
    signal_engine._velas_cache.clear()            # idem o cache de velas do [F-10]
    signal_engine._tf_por_sinal.clear()           # idem o memo de TF do [F-14]
    return fake


# O ciclo do worker (`api.worker`), depois do [F-11], gasta:
#
#   `simulador.atualizar()`                             = 1 requisicao, SEMPRE (constante)
#       ate 1 posicao  -> `preco_ao_vivo`               = 1 fetch_ticker
#       2 ou mais      -> `_precos_em_lote`             = 1 fetch_tickers pela lista inteira
#   `signal_engine.avaliar_saida()`, POR POSICAO        = 1 fetch_ohlcv   (cacheado, [F-10])
#                                 + `mercado.book()`    = 1 fetch_order_book + 1 fetch_trades
#
# A separacao entre os dois numeros e o card: a marcacao deixou de crescer com o tamanho da
# carteira, o gestor de saida nao. Um so `CUSTO_POR_POSICAO` juntava as duas coisas e
# escondia justamente qual delas escala.
CUSTO_MARCACAO = 1                      # [F-11] constante: nao depende de n_pos
CUSTO_SAIDA_FRIO = 3                    # por posicao, cache de velas vazio
CUSTO_SAIDA_REGIME = 2                  # [F-10] por posicao, com a vela ainda aberta


@pytest.mark.parametrize("n_pos", [1, 3, 5])
def test_f13_o_custo_de_rede_do_ciclo_cresce_por_posicao(corretora_contada, n_pos):
    """[F-13] O ciclo continua LINEAR no numero de posicoes -- o coeficiente e que caiu.

    Medido com o relogio em 2026-08-29 (`python signal_engine.py --cronometro`, 5 posicoes,
    a partir do Brasil): 20 requisicoes e **18,5 s** num ciclo cujo teto e 15 s, ou seja o
    ciclo ja estourava ANTES de o scan entrar. Depois do [F-11] a mesma medicao deu **16
    requisicoes e 11,8 s**, e o ciclo passou a caber.

    [F-11] A marcacao saiu da conta linear: e 1 requisicao para qualquer carteira. O que
    sobra crescendo com `n_pos` e o gestor de saida, que e exatamente o que o [F-9] mede.
    """
    for i in range(n_pos):
        semear_posicao(ativo=f"MOEDA{i}/USDT", entrada=100.0, stop=50.0,
                       valor_reais=50.0, alavancagem=2)
    simulador.atualizar()
    assert corretora_contada.total == CUSTO_MARCACAO      # 1, para 1 ou para 5 posicoes
    abertas = db.listar("posicoes", 50, "WHERE status='aberta'")
    assert len(abertas) == n_pos                     # nada fechou: o stop esta longe
    for pos in abertas:
        signal_engine.avaliar_saida(pos)
    assert corretora_contada.total == CUSTO_MARCACAO + n_pos * CUSTO_SAIDA_FRIO


def _um_ciclo():
    """As tres etapas de rede de `api.worker()`, na ordem em que ele as chama."""
    simulador.processar_ordens()
    simulador.atualizar()
    for pos in db.listar("posicoes", 50, "WHERE status='aberta'"):
        signal_engine.avaliar_saida(pos)


@pytest.mark.parametrize("n_pos", [1, 3, 5])
def test_f10_o_ciclo_SEGUINTE_nao_rebaixa_o_candle_que_nao_mudou(corretora_contada, n_pos):
    """[F-10] O numero que interessa nao e o do primeiro ciclo -- e o do regime, porque o
    worker roda 5.760 ciclos por dia e so um deles e o primeiro.

    Primeiro ciclo: 3 requisicoes por posicao (o cache esta frio). Do segundo em diante, 2 --
    o candle sai do cache ate a vela fechar, que num TF de 15 min significa **59 dos 60
    ciclos**. E o mesmo sinal, nao um parecido: ver o argumento de igualdade em `_velas`.

    A marcacao continua custando 1 nos dois ciclos: ela nao e cacheada e nao deve ser -- o
    preco ao vivo e o que decide stop e liquidacao, e serve-lo de cache seria vigiar o
    mercado por uma foto velha. O [F-11] tirou o N dela, nao a frequencia.
    """
    for i in range(n_pos):
        semear_posicao(ativo=f"MOEDA{i}/USDT", entrada=100.0, stop=50.0,
                       valor_reais=50.0, alavancagem=2)
    _um_ciclo()
    assert corretora_contada.total == CUSTO_MARCACAO + n_pos * CUSTO_SAIDA_FRIO
    corretora_contada.n.clear()
    # O cache de tickers do `mercado` vale 5 s, e existe para que os varios consumidores de UM
    # ciclo nao pecam o mesmo preco varias vezes. Entre ciclos ele nunca vale: o worker dorme
    # 15 s e a medicao do [F-13] poe o ciclo entre 11,8 s e 43,7 s, de modo que os 5 s sempre
    # vencem no caminho. Dois `_um_ciclo()` colados num teste sao a unica cadencia em que ele
    # sobreviveria -- limpa-lo aqui e o que faz o teste medir o REGIME de producao em vez de um
    # cache que a producao nunca ve.
    # O cache de VELAS ([F-10]) e o contrario e por isso NAO se toca aqui: ele vale ate a vela
    # fechar, sobrevive entre ciclos de proposito, e e justamente ele que este teste mede.
    mercado._tcache.clear()
    _um_ciclo()
    assert corretora_contada.n.get("fetch_ohlcv") is None      # nenhum candle rebaixado
    assert corretora_contada.total == CUSTO_MARCACAO + n_pos * CUSTO_SAIDA_REGIME


def test_f10_o_segundo_scan_dentro_da_mesma_vela_nao_gasta_requisicao(corretora_contada):
    """[F-10] O scan roda a cada 60 s sobre TFs de 5m, 15m e 1h: 3 de 4 varreduras de 5m,
    14 de 15 de 15m e 59 de 60 de 1h rebaixavam exatamente as mesmas velas fechadas."""
    db.set_config("ativos", "AAA/USDT,BBB/USDT")
    db.set_config("timeframes", "5m,15m,1h")
    signal_engine.scan()
    assert corretora_contada.n["fetch_ohlcv"] == 2 * 3
    corretora_contada.n.clear()
    signal_engine.scan()
    assert corretora_contada.n.get("fetch_ohlcv") is None


def test_f10_o_cache_vence_quando_a_vela_fecha(corretora_contada):
    """A validade e o fechamento da vela, nao um TTL em segundos. Vencido, refaz -- que e o
    que impede o bot de operar sobre uma vela de meia hora atras."""
    db.set_config("ativos", "AAA/USDT")
    db.set_config("timeframes", "15m")
    signal_engine.scan()
    assert corretora_contada.n["fetch_ohlcv"] == 1
    for ent in signal_engine._velas_cache.values():
        ent["ate_ms"] = 0                                       # a vela fechou
    corretora_contada.n.clear()
    signal_engine.scan()
    assert corretora_contada.n["fetch_ohlcv"] == 1


def test_f10_o_sinal_servido_do_cache_e_IDENTICO_ao_da_rede(corretora_contada):
    """A asseracao que autoriza o cache a existir sem chave para desliga-lo. Nao e "parecido"
    nem "dentro da tolerancia": e o mesmo dicionario, porque as duas leituras que `analisa`
    faz (vela fechada, e o timestamp de abertura da vela em formacao) sao constantes dentro
    do periodo."""
    da_rede = signal_engine.analisa("AAA/USDT", "15m")
    assert corretora_contada.n["fetch_ohlcv"] == 1
    do_cache = signal_engine.analisa("AAA/USDT", "15m")
    assert corretora_contada.n["fetch_ohlcv"] == 1              # nao foi a rede
    assert do_cache == da_rede


def test_f10_o_cache_serve_a_janela_pedida_e_nunca_uma_maior(corretora_contada):
    """`avaliar_saida` calcula os indicadores sobre 120 velas. Servir as 200 do scan mudaria
    o warmup e portanto o numero -- seria trocar "mesma resposta mais barata" por "resposta
    diferente", que nao e o que este card autoriza."""
    assert len(signal_engine._velas("AAA/USDT", "15m", 200)) == 200
    assert len(signal_engine._velas("AAA/USDT", "15m", 120)) == 120
    assert corretora_contada.n["fetch_ohlcv"] == 1              # a fatia saiu da mesma busca


def test_f10_a_janela_maior_pedida_depois_da_menor_nao_e_servida_truncada(corretora_contada):
    """A ordem inversa: o gestor de saida (120) chega antes do scan (200). O cache nao pode
    devolver 120 para quem pediu 200 -- refaz, e passa a guardar a janela maior."""
    assert len(signal_engine._velas("AAA/USDT", "15m", 120)) == 120
    assert len(signal_engine._velas("AAA/USDT", "15m", 200)) == 200
    assert corretora_contada.n["fetch_ohlcv"] == 2
    assert len(signal_engine._velas("AAA/USDT", "15m", 200)) == 200
    assert corretora_contada.n["fetch_ohlcv"] == 2              # a segunda ja cobre as duas


def test_f10_falha_de_rede_nao_e_servida_do_cache_vencido(corretora_contada, monkeypatch):
    """Cache que sobrevive a propria validade para "nao quebrar" e o defeito que o [P2-9] e o
    `ultima_marcacao` existem para evitar: dado velho servido como se fosse de agora. Vencida
    a vela, a excecao sobe igual a antes."""
    signal_engine._velas("AAA/USDT", "15m", 200)
    for ent in signal_engine._velas_cache.values():
        ent["ate_ms"] = 0

    def caiu(*a, **k):
        raise RuntimeError("HTTP 451")

    monkeypatch.setattr(signal_engine.ex, "fetch_ohlcv", caiu)
    with pytest.raises(RuntimeError):
        signal_engine._velas("AAA/USDT", "15m", 200)


def test_f13_o_scan_gasta_uma_requisicao_por_par_ativo_x_timeframe(corretora_contada):
    """[F-13] O scan e `ativos x timeframes` chamadas de candle. Com a grade viva
    (24 ativos x 3 TFs) sao 72 -- e cada uma baixa 200 velas que, na maior parte dos ciclos,
    sao as MESMAS de 60 s atras. Aqui a grade e pequena para o teste ser rapido; o que se
    trava e a forma da conta, nao o 72."""
    db.set_config("ativos", "AAA/USDT,BBB/USDT")
    db.set_config("timeframes", "5m,15m,1h")
    signal_engine.scan()
    assert corretora_contada.n.get("fetch_ohlcv") == 2 * 3


# ================================ [F-14] o gestor de saida olha o grafico em que a entrada nasceu

@pytest.fixture(autouse=True)
def _memo_tf_limpo():
    """O memo de `sinal_id -> tf` e de processo, e os ids de sinal recomecam do 1 a cada banco
    temporario. Sem limpar, o sinal #1 de um teste responderia pelo #1 do teste seguinte."""
    signal_engine._tf_por_sinal.clear()
    yield
    signal_engine._tf_por_sinal.clear()


def _pos_de_sinal(tf, **kw):
    """Posicao aberta ligada a um sinal do TF pedido. `tf=None` = sinal sem TF gravado."""
    sid = semear_sinal(ativo="AAA/USDT", tf=tf)
    pid = semear_posicao(ativo="AAA/USDT", entrada=100.0, stop=50.0,
                         valor_reais=50.0, alavancagem=2, **kw)
    with db.conectar() as c:
        c.execute("UPDATE posicoes SET sinal_id=? WHERE id=?", (sid, pid))
    return db.listar("posicoes", 1, "WHERE id=%d" % pid)[0]


@pytest.mark.parametrize("tf_do_sinal", ["5m", "15m", "1h"])
def test_f14_a_saida_usa_o_tf_do_SINAL_e_nao_o_primario_da_config(corretora_contada, tf_do_sinal):
    """[F-14] O scanner varre `timeframes` (5m,15m,1h) e grava o TF em cada sinal, mas o
    gestor de saida lia sempre `cfg["timeframe"]`. Uma posicao aberta por sinal de 1 h era
    vigiada em velas de 15 min -- o ruido de 15 min pedindo a saida de uma tese de 1 h.

    A prova e sobre o TF que chega na corretora, e nao sobre o veredito: quem decide a saida e
    o indicador, e o card e sobre em QUE grafico ele e calculado."""
    db.set_config("timeframe", "15m")                 # o primario continua sendo 15m
    pedidos = []
    real = signal_engine.ex.fetch_ohlcv
    signal_engine.ex.fetch_ohlcv = lambda a, timeframe=None, limit=200, since=None: (
        pedidos.append(timeframe), real(a, timeframe, limit, since))[1]
    try:
        signal_engine.avaliar_saida(_pos_de_sinal(tf_do_sinal))
    finally:
        signal_engine.ex.fetch_ohlcv = real
    assert pedidos == [tf_do_sinal]


def test_f14_posicao_sem_sinal_continua_no_timeframe_da_config(corretora_contada):
    """Posicao aberta a mao (rota da API, sem `sinal_id`) e sinal antigo com `tf` NULL caem no
    `timeframe` da config -- que e exatamente o que faziam antes. O card corrige quem TEM TF
    proprio; nao inventa um para quem nao tem."""
    db.set_config("timeframe", "5m")
    pedidos = []
    real = signal_engine.ex.fetch_ohlcv
    signal_engine.ex.fetch_ohlcv = lambda a, timeframe=None, limit=200, since=None: (
        pedidos.append(timeframe), real(a, timeframe, limit, since))[1]
    try:
        sem_sinal = db.listar("posicoes", 1, "WHERE id=%d" % semear_posicao(
            ativo="AAA/USDT", entrada=100.0, stop=50.0, valor_reais=50.0, alavancagem=2))[0]
        signal_engine.avaliar_saida(sem_sinal)
        signal_engine._tf_por_sinal.clear()
        # o [F-10] ja guardou (AAA/USDT, 5m): sem esvaziar, a segunda chamada seria servida do
        # cache e nao chegaria a pedir TF nenhum -- o teste passaria a nao medir nada.
        signal_engine._velas_cache.clear()
        signal_engine.avaliar_saida(_pos_de_sinal(None))       # sinal com tf NULL
    finally:
        signal_engine.ex.fetch_ohlcv = real
    assert pedidos == ["5m", "5m"]


def test_f14_o_default_nao_e_memoizado_junto_com_o_fato(banco):
    """O memo guarda o fato imutavel (o `tf` do sinal, "" quando nao ha) e nunca o default.
    Se guardasse o default, trocar `timeframe` no painel ficaria congelado no valor de quando
    a posicao foi vista pela primeira vez -- config que so vale para quem chegou depois."""
    cfg = {"timeframe": "5m"}
    pos = _pos_de_sinal(None)
    assert signal_engine.tf_da_posicao(pos, cfg) == "5m"
    cfg["timeframe"] = "1h"                                    # alguem mexe no painel
    assert signal_engine.tf_da_posicao(pos, cfg) == "1h"       # vale na hora


def test_f14_o_tf_do_sinal_e_lido_uma_vez_so_por_sinal(banco, monkeypatch):
    """O TF de um sinal e imutavel (gravado no INSERT do scan, nunca reescrito), entao o memo
    nao precisa de invalidacao -- e o gestor de saida nao volta ao banco a cada ciclo, que
    seria reabrir a conexao por posicao que o [F-12] acabou de tirar do laco."""
    pos = _pos_de_sinal("1h")
    cfg = {"timeframe": "15m"}
    n = {"v": 0}
    real = db.conectar

    def contando(*a, **k):
        n["v"] += 1
        return real(*a, **k)

    monkeypatch.setattr(db, "conectar", contando)
    assert [signal_engine.tf_da_posicao(pos, cfg) for _ in range(10)] == ["1h"] * 10
    assert n["v"] == 1


def test_f14_banco_indisponivel_nao_vira_tf_errado_para_sempre(banco, monkeypatch):
    """A ultima ponta do memo: falha ao LER o TF cai no primario e nao grava nada.

    Gravar "" num erro transitorio (banco travado, disco cheio) fixaria o TF errado para o
    resto da vida do processo, e o gestor de saida seguiria vigiando o grafico errado muito
    depois de o banco ter voltado -- sem nenhum sintoma, porque o valor cacheado responde."""
    pos = _pos_de_sinal("1h")
    cfg = {"timeframe": "15m"}

    def travado(*a, **k):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(db, "conectar", travado)
    assert signal_engine.tf_da_posicao(pos, cfg) == "15m"      # degrada para o primario
    assert signal_engine._tf_por_sinal == {}                   # e NAO memoiza a falha
    monkeypatch.undo()
    assert signal_engine.tf_da_posicao(pos, cfg) == "1h"       # o banco volta, o TF certo volta
