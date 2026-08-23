# -*- coding: utf-8 -*-
"""[Q-5] Provas do backtest de portfolio.

O card aceita "mesmas funcoes OU testes de equivalencia". O modulo escolheu **mesmas
funcoes**: ele nao reimplementa regra, injeta banco/relogio/preco e roda o codigo vivo. Isso
muda o que estes testes tem de provar. Nao ha aritmetica minha para comparar com a do
`simulador` -- ha um ARNES, e o risco dele e outro:

  1. o arnes nao entrega o que promete (o relogio nao chega em `guarda_risco`, o preco nao
     chega em `atualizar`), e o backtest passa a medir um sistema onde o dia nunca vira;
  2. o arnes VAZA (deixa `db.DB` ou `simulador.pd` trocados) e contamina a suite inteira;
  3. a unica transcricao que sobrou -- `sinais_da_barra`, que existe porque
     `signal_engine.analisa` faz o `fetch_ohlcv` dentro de si -- diverge do original.

Os tres tem prova aqui, e a (3) e literalmente um teste de equivalencia: `analisa` com a
rede dublada, comparado campo a campo. Se alguem mexer em `analisa` sem mexer aqui, quebra.
"""
import math

import pandas as pd
import pytest

import alertas
import autotrader
import db
import signal_engine
import simulador
from pesquisa import backtest_portfolio as bp
from scoring import preparar

COLS = ["timestamp", "open", "high", "low", "close", "volume"]


# --------------------------------------------------------------------------------------
# Geradores de candle: deterministas, sem rede e sem `Timestamp.now()`
# --------------------------------------------------------------------------------------
def _ruido(semente):
    """LCG proprio em vez de `random`: a suite tem de dar o mesmo numero em toda maquina,
    e semear o `random` global e efeito colateral em cima de quem rodar depois."""
    r = semente

    def prox():
        nonlocal r
        r = (r * 1103515245 + 12345) % (2 ** 31)
        return r / 2 ** 31 - 0.5
    return prox


def serie_tendencia(n=400, tf_min=15, semente=7, inicio="2026-03-01", passo=0.0035,
                    ciclo=55, preco0=100.0):
    """Candles com tendencia de alta interrompida por pullbacks.

    A forma nao e enfeite: os portoes vivos exigem ADX>=25 (tendencia sustentada), rompimento
    de Donchian (maxima nova), RSI entre 45 e 72 (nao esticado) e volume acima da media. Um
    passeio aleatorio nao passa em nenhum, e um foguete reto estoura o RSI. O pullback
    periodico e o que mantem o RSI na faixa enquanto o ADX sobe.
    """
    rnd = _ruido(semente)
    ms = tf_min * 60 * 1000
    t0 = int(pd.Timestamp(inicio).value // 10 ** 6)
    x, linhas = preco0, []
    for i in range(n):
        u = rnd()
        onda = passo * (1.0 if (i % ciclo) < ciclo * 0.72 else -1.4)
        x *= (1 + onda + 0.0015 * u)
        o = x / (1 + onda + 0.0015 * u)
        h, l = max(o, x) * (1 + 0.0012 + 0.001 * abs(u)), min(o, x) * (1 - 0.0012 - 0.001 * abs(u))
        vol = 1000 * (1.0 + 0.6 * math.sin(i / 3.0) + 0.4 * abs(u))
        linhas.append((t0 + i * ms, o, h, l, x, vol))
    return pd.DataFrame(linhas, columns=COLS)


def serie_despencando(n=400, tf_min=15, semente=11, inicio="2026-03-01"):
    """Alta longa e depois um tombo -- para ver a trava diaria e a liquidacao acontecerem."""
    df = serie_tendencia(n, tf_min, semente, inicio)
    corte = int(n * 0.72)
    fator = 1.0
    linhas = df.values.tolist()
    for i in range(corte, n):
        fator *= 0.988
        o, h, l, c = (v * fator for v in linhas[i][1:5])
        linhas[i] = [linhas[i][0], o, h, l, c, linhas[i][5] * 1.5]
    return pd.DataFrame(linhas, columns=COLS)


def universo(ativos=("BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT"),
             tfs=("5m", "15m"), n_base=520, gerador=serie_tendencia):
    """Um dicionario `{(ativo, tf): df preparado}` no formato que `rodar(dfs=...)` aceita.
    O numero de barras por TF e escalado para que todos cubram a MESMA janela de tempo."""
    base = min(signal_engine.TF_MIN[t] for t in tfs)
    dfs = {}
    for k, a in enumerate(ativos):
        for tf in tfs:
            n = max(int(n_base * base / signal_engine.TF_MIN[tf]), 80)
            dfs[(a, tf)] = preparar(gerador(n=n, tf_min=signal_engine.TF_MIN[tf],
                                            semente=7 + 5 * k))
    return dfs


@pytest.fixture(scope="module")
def resultado():
    """UMA execucao do laco completo, compartilhada por todos os testes que a inspecionam.

    Uma so, e nao uma por teste, porque o laco roda o codigo VIVO e paga o preco dele: cada
    ciclo abre ~35 conexoes SQLite, o que da ~0,25 s por ciclo. O universo foi escolhido para
    caber nesse orcamento e ainda assim exercer TUDO que o card pede num relatorio:

      - TF base de 15m (e nao 5m): mesmo custo por ciclo, 3x mais DIAS simulados por ciclo --
        e sem varios dias nao ha o que dizer sobre a trava diaria, que e diaria;
      - `serie_despencando`: alta longa (entradas, trailing, stop) seguida de tombo
        (liquidacao e a trava acionando), num universo so.
    """
    dfs = universo(ativos=("BTC/USDT", "ETH/USDT", "SOL/USDT"), tfs=("15m", "1h"),
                   n_base=700, gerador=serie_despencando)
    return bp.rodar(dfs=dfs, banca=1000.0, verbose=False)


# --------------------------------------------------------------------------------------
# (3) Equivalencia: a unica transcricao do modulo concorda com o `signal_engine.analisa`
# --------------------------------------------------------------------------------------
def test_sinais_da_barra_equivale_ao_analisa(monkeypatch):
    """`sinais_da_barra` tem de devolver EXATAMENTE o que `analisa` devolveria.

    `analisa` nao aceita candles por parametro (o `fetch_ohlcv` esta dentro dela), entao a
    unica forma de compara-las e dublar a rede e rodar as duas sobre os mesmos 200 candles
    -- 200 porque e o `limit` que o `analisa` pede, e assim as duas veem a MESMA janela de
    warmup (fora daqui elas nao veem, e essa divergencia e o limite (d) declarado no modulo).
    """
    raw = serie_tendencia(n=200, tf_min=15).values.tolist()

    class _Ex:
        def fetch_ohlcv(self, ativo, timeframe=None, limit=None):
            assert limit == 200
            return raw

    monkeypatch.setattr(signal_engine, "ex", _Ex())
    esperado = signal_engine.analisa("BTC/USDT", "15m")
    assert esperado, "a serie do teste precisa gerar sinal, senao a comparacao e vazia"

    df = preparar(pd.DataFrame(raw, columns=COLS))
    obtido = bp.sinais_da_barra(df, len(df) - 2, "BTC/USDT", "15m")
    assert obtido == esperado


# --------------------------------------------------------------------------------------
# (2) O arnes nao vaza
# --------------------------------------------------------------------------------------
def _foto():
    return {"db.DB": db.DB, "simulador.pd": simulador.pd, "autotrader.pd": autotrader.pd,
            "simulador.preco_ao_vivo": simulador.preco_ao_vivo, "simulador.ex": simulador.ex,
            "simulador.ex_fut": simulador.ex_fut, "signal_engine.ex": signal_engine.ex,
            "autotrader._tamanho": autotrader._tamanho, "alertas.enviar": alertas.enviar,
            "CAPS": dict(autotrader.CAPS_GEOMETRIA),
            "scan": dict(signal_engine.ultimo_scan),
            "marcacao": dict(simulador.ultima_marcacao),
            "funding": dict(simulador.funding_medicao)}


def test_ambiente_restaura_tudo_na_saida_normal():
    antes = _foto()
    with bp.Ambiente("2026-03-01 00:00:00") as amb:
        assert db.DB != antes["db.DB"]
        assert simulador.preco_ao_vivo is amb.precos
    assert _foto() == antes


def test_ambiente_restaura_tudo_quando_o_corpo_levanta():
    """A restauracao por `finally` e o que separa 'um teste falhou' de 'a suite inteira
    passou a escrever no banco errado'."""
    antes = _foto()
    with pytest.raises(ZeroDivisionError):
        with bp.Ambiente("2026-03-01 00:00:00"):
            1 / 0
    assert _foto() == antes


def test_ambiente_recusa_trailing_desligado():
    """Limite (e): sem trailing o vivo fecha pelo gestor de saida, que le book AO VIVO. O
    arnes recusa em vez de rodar sem essa politica e chamar o resultado de paridade -- e
    tem de deixar os modulos limpos ao recusar."""
    antes = _foto()
    with pytest.raises(ValueError, match="trailing_ativo"):
        bp.Ambiente("2026-03-01 00:00:00", cfg={"trailing_ativo": "0"}).__enter__()
    assert _foto() == antes


def test_ambiente_barra_a_rede():
    antes = _foto()
    with bp.Ambiente("2026-03-01 00:00:00"):
        with pytest.raises(RuntimeError, match="tentou rede"):
            simulador.ex.fetch_ticker("BTC/USDT")
        with pytest.raises(RuntimeError, match="tentou rede"):
            signal_engine.ex.fetch_ohlcv("BTC/USDT", timeframe="15m")
    assert _foto() == antes


# --------------------------------------------------------------------------------------
# (1) O relogio simulado chega ate as funcoes vivas
# --------------------------------------------------------------------------------------
def _semear_posicao(ativo, direcao="LONG", entrada=100.0, valor=100.0, lev=5,
                    stop=95.0, pnl=0.0):
    with db.conectar() as c:
        c.execute("INSERT INTO posicoes(ativo,direcao,entrada,valor_reais,alavancagem,stop,"
                  "preco_atual,pnl,aberto_em,status,conviccao) "
                  "VALUES(?,?,?,?,?,?,?,?,?, 'aberta',80)",
                  (ativo, direcao, entrada, valor, lev, stop, entrada, pnl, "2026-03-01 00:00:00"))
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def test_relogio_simulado_manda_no_dia_da_trava_diaria():
    """A prova central do desenho: `guarda_risco` deriva o dia de `pd.Timestamp.now()`, e com
    o relogio simulado a trava STICKY e a soltura na virada acontecem em tempo SIMULADO.

    Sem isto o backtest inteiro seria um unico "hoje": a trava travaria no primeiro tropeco
    e nunca mais soltaria, e a contagem de acionamentos que o card pede seria sempre 1.
    """
    with bp.Ambiente("2026-03-01 09:00:00", banca=1000.0) as amb:
        with db.conectar() as c:                       # baseline do dia = 1000
            c.execute("INSERT INTO equity(ts,banca,equity_total) VALUES(?,?,?)",
                      ("2026-03-01 08:00:00", 1000.0, 1000.0))
        assert simulador.guarda_risco()["trava_dia"] is False

        _semear_posicao("BTC/USDT", pnl=-70.0)         # -7% > limite_perda_dia 5%
        g = simulador.guarda_risco()
        assert g["trava_dia"] is True
        assert db.get_config()["trava_dia_em"] == "2026-03-01"

        # sticky DENTRO do dia: some a perda, a trava fica
        with db.conectar() as c:
            c.execute("UPDATE posicoes SET pnl=0 WHERE status='aberta'")
        assert simulador.guarda_risco()["trava_dia"] is True

        # vira o dia SIMULADO -> solta, pelo codigo vivo, sem ninguem limpar `trava_dia_em`
        amb.relogio.agora = pd.Timestamp("2026-03-02 00:05:00")
        assert simulador.guarda_risco()["trava_dia"] is False


def test_relogio_simulado_manda_no_cooldown_e_na_freshness():
    """`auto_executar` filtra por `auto_freshness_min` (12 min) e `auto_cooldown_min` (30 min)
    contra `pd.Timestamp.now()`. Se o relogio nao chegasse la, TODO sinal historico pareceria
    velho e o backtest nunca abriria nada -- falha silenciosa, curva plana, zero trades."""
    with bp.Ambiente("2026-03-01 12:00:00", banca=1000.0) as amb:
        amb.precos.mapa = {"BTC/USDT": 100.0, "ETH/USDT": 100.0}
        _sinal("BTC/USDT", ts="2026-03-01 11:58:00")            # 2 min: fresco
        _sinal("ETH/USDT", ts="2026-03-01 11:40:00")            # 20 min: passou da janela
        res = autotrader.auto_executar(None)
        assert [a["ativo"] for a in res["abertos"]] == ["BTC/USDT"]

        # cooldown: um trade fechado ha 5 min no ETH bloqueia o ativo por 30 min
        with db.conectar() as c:
            c.execute("INSERT INTO trades(ativo,direcao,pnl_reais,fechado_em) "
                      "VALUES('ETH/USDT','LONG',-1.0,?)", ("2026-03-01 11:55:00",))
        _sinal("ETH/USDT", ts="2026-03-01 11:59:30")
        assert autotrader.auto_executar(None)["abertos"] == []

        amb.relogio.agora = pd.Timestamp("2026-03-01 12:40:00")  # 45 min depois: liberado
        _sinal("ETH/USDT", ts="2026-03-01 12:39:00")
        assert [a["ativo"] for a in autotrader.auto_executar(None)["abertos"]] == ["ETH/USDT"]


def _sinal(ativo, ts, conviccao=80, direcao="LONG", preco=100.0, stop=97.0, tf="15m"):
    with db.conectar() as c:
        c.execute("INSERT INTO sinais(ts,ativo,tf,tipo,direcao,conviccao,motivos,preco,"
                  "stop_sugerido,status) VALUES(?,?,?, 'tendencia',?,?,'x',?,?, 'novo')",
                  (ts, ativo, tf, direcao, conviccao, preco, stop))
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]


# --------------------------------------------------------------------------------------
# A fila: o que o card chama de "sinais competindo pelos slots"
# --------------------------------------------------------------------------------------
CONVS = {"BTC/USDT": 95, "ETH/USDT": 90, "SOL/USDT": 85, "BNB/USDT": 80,
         "XRP/USDT": 75, "ADA/USDT": 70, "DOGE/USDT": 65, "AVAX/USDT": 62}


def test_fila_ordena_por_conviccao_e_o_teto_de_risco_corta_antes_dos_slots():
    """Oito candidatos, cinco slots — e entram TRES.

    Quem corta nao e `auto_max_posicoes`: e o teto de risco agregado. Com os defaults vivos
    `risco_por_trade`=3% e `risco_aberto_max`=10%, a quarta entrada levaria a soma do
    risco-ate-o-stop a 12% e o `simulador.abrir` recusa. A tensao "5 slots x 3% = 15% > teto
    10%" ja estava escrita na INVESTIGACAO-TRADING-2026-08-19 sem numero; aqui ela vira
    comportamento observado, e e exatamente o tipo de coisa que so um backtest de PORTFOLIO
    consegue mostrar — no backtest por-ativo nao existe soma de risco.
    """
    with bp.Ambiente("2026-03-01 12:00:00", banca=100000.0) as amb:
        amb.precos.mapa = {a: 100.0 for a in CONVS}
        for a, cv in CONVS.items():
            _sinal(a, ts="2026-03-01 11:59:00", conviccao=cv)
        res = autotrader.auto_executar(None)
        assert [a["ativo"] for a in res["abertos"]] == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        assert any("teto de risco aberto" in r["erro"] for r in res["rejeitados"])


def test_fila_para_nos_slots_quando_o_teto_de_risco_nao_morde():
    """Solto o teto de risco, quem corta passa a ser `auto_max_posicoes`=5 — e o ciclo
    seguinte nao arruma slot novo. Os dois testes juntos mostram QUAL guarda esta mordendo."""
    with bp.Ambiente("2026-03-01 12:00:00", banca=100000.0,
                     cfg={"risco_aberto_max": "0.30"}) as amb:
        amb.precos.mapa = {a: 100.0 for a in CONVS}
        for a, cv in CONVS.items():
            _sinal(a, ts="2026-03-01 11:59:00", conviccao=cv)
        res = autotrader.auto_executar(None)
        assert [a["ativo"] for a in res["abertos"]] == ["BTC/USDT", "ETH/USDT", "SOL/USDT",
                                                        "BNB/USDT", "XRP/USDT"]
        for a, cv in CONVS.items():
            _sinal(a, ts="2026-03-01 11:59:30", conviccao=cv)
        assert autotrader.auto_executar(None)["motivo"].startswith("limite de posições")


def test_trailing_em_lucro_INFLA_o_risco_aberto__achado_do_Q5_para_o_T_GUARDA():
    """Achado, nao regra: `_risco_posicao` usa `abs(entrada - stop)` e NAO olha o lado.

    Quando o trailing leva o stop para o lucro, a distancia entrada->stop cresce e a funcao
    a le como risco. Uma posicao que so pode fechar GANHANDO passa a ocupar o teto de risco
    agregado -- e, no limite, a barrar entradas novas justamente enquanto os vencedores
    correm. So um backtest de PORTFOLIO faz isso aparecer: no backtest por-ativo nao existe
    soma de risco nem teto que ela possa estourar.

    Este teste fixa o comportamento de HOJE, com numero. `simulador._risco_posicao` e
    territorio do `T-GUARDA` e nao se conserta daqui ([Q-5] so le). Quando o card sair, este
    teste quebra -- e e para quebrar mesmo: e o gatilho que obriga a atualizar a leitura em
    vez de deixar a mudanca passar em silencio.
    """
    ini = simulador._risco_posicao(100.0, 10, entrada=100.0, stop=97.0)     # stop 3% ABAIXO
    lucro = simulador._risco_posicao(100.0, 10, entrada=100.0, stop=110.0)  # stop 10% ACIMA
    assert ini == pytest.approx(30.0)
    assert lucro == pytest.approx(100.0)      # capado na margem, e conta como risco INTEIRO

    with bp.Ambiente("2026-03-01 12:00:00", banca=1000.0):
        pid = _semear_posicao("BTC/USDT", entrada=100.0, valor=100.0, lev=10, stop=97.0)
        assert simulador.guarda_risco()["risco_aberto_rs"] == pytest.approx(30.0)
        with db.conectar() as c:              # o trailing subiu o stop para o lucro
            c.execute("UPDATE posicoes SET stop=110.0 WHERE id=?", (pid,))
        g = simulador.guarda_risco()
        assert g["risco_aberto_rs"] == pytest.approx(100.0)
        assert g["teto_aberto"] is True       # 100 >= 10% de 1000: o teto FECHOU a fila


def test_uma_entrada_por_ativo_por_ciclo():
    """Tres sinais do MESMO ativo no mesmo ciclo abrem UMA posicao; os outros viram 'pulado'."""
    with bp.Ambiente("2026-03-01 12:00:00", banca=100000.0) as amb:
        amb.precos.mapa = {"BTC/USDT": 100.0}
        for cv in (95, 88, 70):
            _sinal("BTC/USDT", ts="2026-03-01 11:59:00", conviccao=cv)
        res = autotrader.auto_executar(None)
        assert len(res["abertos"]) == 1 and res["abertos"][0]["conviccao"] == 95
        with db.conectar() as c:
            estados = dict(c.execute("SELECT status, COUNT(*) FROM sinais GROUP BY status"))
        assert estados == {"confirmado": 1, "pulado": 2}


def test_sizing_zero_pula_o_sinal_e_o_contador_ve():
    """[P2-8]: com banca pequena `_tamanho` devolve 0,0, e 0 significa PULAR -- nao e erro e
    nao e posicao de tamanho zero. O `_Contador` existe porque `auto_executar` faz isso com
    um `continue` mudo: sem ele, "fila vazia" e "banca nao comporta" ficam indistinguiveis."""
    with bp.Ambiente("2026-03-01 12:00:00", banca=30.0) as amb:
        amb.precos.mapa = {"BTC/USDT": 100.0}
        _sinal("BTC/USDT", ts="2026-03-01 11:59:00")
        res = autotrader.auto_executar(None)
        assert res["abertos"] == [] and res["rejeitados"] == []
        assert amb.tamanho.zeros == 1 and amb.tamanho.chamadas == 1
        assert db.listar("posicoes", 10, "WHERE status='aberta'") == []


def test_preco_do_backtest_chega_na_abertura_e_na_marcacao():
    """`simulador.abrir` le `preco_ao_vivo` para a entrada e `atualizar` para a marcacao. Se
    o preco do arnes nao chegasse nos dois, o backtest abriria no preco do sinal e fecharia
    no preco de mercado de hoje -- que e olhar o futuro."""
    with bp.Ambiente("2026-03-01 12:00:00", banca=10000.0) as amb:
        amb.precos.mapa = {"BTC/USDT": 250.0}
        _sinal("BTC/USDT", ts="2026-03-01 11:59:00", preco=100.0, stop=97.0)
        autotrader.auto_executar(None)
        pos = db.listar("posicoes", 1, "WHERE status='aberta'")[0]
        assert pos["entrada"] == 250.0
        # o stop foi RECOMPOSTO mantendo os 3% relativos do sinal (`simulador.abrir`)
        assert pos["stop"] == pytest.approx(250.0 * 0.97, rel=1e-6)

        amb.precos.mapa = {"BTC/USDT": 240.0}     # abaixo do stop -> fecha por stop
        simulador.atualizar()
        t = db.listar("trades", 1)[0]
        assert t["motivo_saida"].startswith("stop")
        assert t["saida"] <= 250.0 * 0.97         # [P2-18] fill nunca melhor que o gatilho


# --------------------------------------------------------------------------------------
# Concentracao por correlacao
# --------------------------------------------------------------------------------------
def _retornos(**series):
    return {a: pd.Series(v) for a, v in series.items()}


def test_concentracao_correlacao_alta_colapsa_as_posicoes():
    """Tres moedas que sobem e descem juntas, tres LONGs: 3 posicoes valem ~1 aposta. E a
    frase do card ("5 posicoes ~ 1 posicao grande em beta") virada em numero."""
    r = _retornos(A=[0.01, -0.02, 0.03, -0.01, 0.02], B=[0.01, -0.02, 0.03, -0.01, 0.02],
                  C=[0.01, -0.02, 0.03, -0.01, 0.02])
    c = bp.concentracao([[("A", 1), ("B", 1), ("C", 1)]], r)
    assert c["rho_medio"] == pytest.approx(1.0, abs=1e-6)
    assert c["efetivas_medias"] == pytest.approx(1.0, abs=0.01)
    assert c["fator_concentracao"] == pytest.approx(3.0, abs=0.01)


def test_concentracao_long_e_short_no_mesmo_beta_se_cancelam():
    """LONG em A e SHORT em B, com A e B correlacionadas, e um par com correlacao NEGATIVA:
    a conta tem de enxergar hedge, nao concentracao."""
    r = _retornos(A=[0.01, -0.02, 0.03, -0.01, 0.02], B=[0.01, -0.02, 0.03, -0.01, 0.02])
    c = bp.concentracao([[("A", 1), ("B", -1)]], r)
    assert c["rho_medio"] == pytest.approx(-1.0, abs=1e-6)
    assert c["efetivas_medias"] == pytest.approx(2.0, abs=0.01)   # capado em n


# --------------------------------------------------------------------------------------
# O laco inteiro
# --------------------------------------------------------------------------------------
def test_rodar_sobre_candles_sinteticos(resultado):
    """Roda o portfolio inteiro sem rede e confere o que o card pede como relatorio."""
    res = resultado

    assert res["ciclos"] > 100
    assert len(res["curva"]) == res["ciclos"]               # 1 snapshot de equity por ciclo
    assert res["metricas"]["n_trades"] > 0, "a serie do teste precisa gerar trade"
    assert res["sinais_confirmados"] > 0

    # O teto de MARGEM vale dentro do backtest, porque quem o aplica e o `simulador.abrir`,
    # e o denominador aqui e o DELE (a banca realizada), nao o que daria numero bonito.
    assert max(res["exposicao"]) <= 0.5 + 1e-9, "furou o teto de margem (exposicao_max)"

    # nunca mais de `auto_max_posicoes` simultaneas, e nunca duas do mesmo ativo
    for cesta in res["cestas"]:
        assert len(cesta) <= 5
        assert len({a for a, _ in cesta}) == len(cesta)


def test_a_entrada_acontece_75s_depois_do_sinal_e_nao_uma_barra_depois(resultado):
    """A correcao que fez o laco existir, e a prova de que ela nao pode regredir.

    `auto_freshness_min` e 12 minutos. Se o backtest tratasse "o ciclo seguinte do worker"
    (15 s ao vivo) como "a barra seguinte", num TF base de 15m ou 1h TODO sinal chegaria
    vencido ao auto-trader: `_tamanho` nunca seria chamado, o resultado seria zero trades, e
    nada no relatorio diria que a causa foi a traducao errada da latencia. Foi exatamente o
    que aconteceu na primeira versao deste modulo.

    O TF base deste universo e 15m > 12 min de freshness DE PROPOSITO: e o caso em que o erro
    aparece. Um universo de 5m passaria nos dois desenhos e nao provaria nada.
    """
    assert resultado["sizing_chamadas"] > 0, "nenhum sinal chegou fresco ao auto-trader"
    assert resultado["metricas"]["n_trades"] > 0


def test_rodar_aciona_a_trava_diaria_e_solta_na_virada(resultado):
    """Trava diaria dentro do laco completo, com os defaults vivos (`limite_perda_dia`=5%).

    Prova a diferenca que o relogio simulado faz: a trava aciona, o backtest ATRAVESSA a
    virada e continua rodando. Com relogio de parede o backtest inteiro seria um "hoje" so —
    a trava prenderia no primeiro tropeco e a contagem de acionamentos seria sempre 1.
    """
    assert resultado["dias_travados"], "a trava nunca acionou — o cenario nao serve de prova"
    assert resultado["ciclos_travados"] > 0
    dias = sorted({ts[:10] for ts, _ in resultado["curva"]})
    assert len(dias) > 1, "o backtest tem de atravessar mais de um dia SIMULADO"
    assert dias[-1] > max(resultado["dias_travados"]), \
        "a curva tem de continuar depois do ultimo dia travado (a trava solta na virada)"


def test_relatorio_declara_os_limites(capsys, resultado):
    """A alternativa minima do card e "declarar o limite". Aqui ela nao substitui o
    simulador -- ela ACOMPANHA os numeros, impressa junto, porque numero de banca sem a
    ressalva ao lado convida a leitura errada."""
    bp.relatorio(resultado)
    saida = capsys.readouterr().out
    assert "NAO descrevem o vivo" in saida
    assert len(bp.LIMITES) >= 5
    for chave in ("(a)", "(b)", "(c)", "(d)", "(e)", "(f)", "(g)"):
        assert chave in saida
    for secao in ("CURVA E DRAWDOWN", "TRAVA DIARIA", "EXPOSICAO",
                  "CONCENTRACAO POR CORRELACAO", "A FILA"):
        assert secao in saida
