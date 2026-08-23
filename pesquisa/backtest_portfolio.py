# -*- coding: utf-8 -*-
"""
[Q-5] Backtest de PORTFOLIO -- a dinamica que nunca foi simulada.

Rodar (da RAIZ do repo):  python -m pesquisa.backtest_portfolio
(`python pesquisa/backtest_portfolio.py` NAO roda -- ver `pesquisa/__init__.py`.)

O que existia antes deste modulo: backtest POR ATIVO, uma posicao por vez, tamanho fixo e
alavancagem fixa (`pesquisa/backtest_plataforma.py`). O sistema vivo opera outra coisa --
24 moedas x 3 timeframes numa fila unica ordenada por conviccao, 5 slots, cooldown de 30
min por ativo, teto de risco agregado, teto de margem, trava diaria e sizing por risco com
alavancagem variavel. Win-rate por trade transfere razoavelmente do backtest por-ativo;
dinamica de BANCA nao transfere, e era exatamente ela que ninguem tinha medido.

------------------------------------------------------------------------------------------
A DECISAO DE DESENHO, QUE E A UNICA COISA QUE IMPORTA AUDITAR AQUI
------------------------------------------------------------------------------------------
Um backtest de portfolio que REIMPLEMENTA as regras mede outro sistema -- e o "outro
sistema" e justamente o defeito que o marco M4 existe para consertar. Entao este modulo
**nao reimplementa regra nenhuma**. Ele chama, sem copiar:

    autotrader.auto_executar   -> a fila: ordenacao por conviccao, slots, cooldown,
                                  freshness, 1 entrada por ativo/ciclo, orcamento de margem
    autotrader._alavancagem    -> lev por conviccao + cap geometrico stop x liquidacao
    autotrader._tamanho        -> sizing por risco (e o `0.0` que FILTRA o sinal, [P2-8])
    simulador.abrir            -> teto de risco aberto, teto de margem, claim atomico do sinal
    simulador.atualizar        -> marcacao, trailing, stop com `_fill_stop`, liquidacao
    simulador.guarda_risco     -> trava diaria sticky + teto de risco agregado
    simulador.fechar / _pnl    -> P&L com taxa e cap na margem
    signal_engine.confirmado   -> portoes de confirmacao (ADX, n_fatores, reversao)
    signal_engine._repetido / _gravar / expirar_sinais -> dedupe e janela de vida do sinal
    scoring.pontuar / pontuar_reversao                 -> a pontuacao de conviccao

O problema de engenharia do card era `guarda_risco()`: ela le o BANCO, e num backtest nao
existe banco com o estado simulado. As tres saidas possiveis eram extrair a aritmetica pura
(exige editar `simulador.py`, que e territorio de outro agente nesta onda), reimplementar e
provar equivalencia por teste, ou **injetar o estado**. Este modulo injeta o estado, e
generaliza a injecao: o codigo vivo depende do mundo por TRES acoplamentos, e nao um --

    1. o BANCO   -> `db.DB` aponta para um SQLite temporario com o esquema vivo
    2. o RELOGIO -> `simulador.pd` / `autotrader.pd` passam a ler o instante SIMULADO
    3. o PRECO   -> `simulador.preco_ao_vivo` passa a ler a barra do candle corrente

Trocados os tres (classe `Ambiente`), o codigo vivo roda inteiro sobre historico **sem uma
linha de regra duplicada**. E o ganho nao e so de hoje: se o `T-GUARDA` mudar `abrir()`
amanha, este backtest muda junto -- uma copia divergiria em silencio, que e o modo de falha
que o card nomeia.

O relogio e o pedaco que paga a maior parte da conta sozinho. `guarda_risco` deriva o dia
de `pd.Timestamp.now().date()`; com o relogio simulado, a trava diaria sticky, o baseline
de equity do dia e a soltura na virada acontecem pelo codigo VIVO, em tempo simulado. Sem
ele, os 30 dias do backtest seriam um unico "hoje" e a trava travaria para sempre no
primeiro tropeco.

------------------------------------------------------------------------------------------
CUSTO -- porque ele e uma consequencia direta da decisao acima, e nao um descuido
------------------------------------------------------------------------------------------
Rodar o codigo vivo significa pagar o preco dele: `db.conectar()` abre uma conexao SQLite
nova por chamada (com `PRAGMA journal_mode=WAL`), e um ciclo completo -- 3 sub-passos de
marcacao + auto-trader + snapshot de equity + scan -- gasta ~35 delas. Medido nesta maquina:
**~0,5 s por ciclo**, e o numero de ciclos e `dias x 24h / TF_mais_fino`.

    24 ativos x 3 TFs (5m,15m,1h) x 30 dias   = 8.640 ciclos  ~ 70 min
    24 ativos x 2 TFs (15m,1h)   x 30 dias    = 2.880 ciclos  ~ 25 min
     8 ativos x 3 TFs            x 10 dias    = 2.880 ciclos  ~ 25 min

O custo cresce com os DIAS e com a finura do TF base; o numero de ativos quase nao pesa
(as posicoes simultaneas sao no maximo 5). Por isso o CLI tem `--dias`, `--ativos` e
`--tfs`: a troca cobertura x granularidade e do operador, nao do modulo. Uma reescrita
mais rapida existiria -- bastaria reimplementar as regras com estado em memoria -- e e
exatamente ela que o card proibe.

------------------------------------------------------------------------------------------
LIMITES DECLARADOS -- o que este backtest NAO mede (ver `LIMITES`)
------------------------------------------------------------------------------------------
Estao na constante `LIMITES` com a DIRECAO do vies de cada um, e o relatorio os imprime
junto dos numeros de proposito: numero de banca sem o limite ao lado convida a leitura
errada. Nao ha `ARQUITETURA.md` aqui (territorio de outro agente nesta onda) -- a
declaracao mora no modulo e no relatorio, e a matriz a leva para la.
"""
import os
import shutil
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd

import alertas
import autotrader
import db
import signal_engine
import simulador
from pesquisa.dados import baixar_ohlcv
from scoring import preparar, pontuar, pontuar_reversao

# Universo padrao = o do sistema vivo (`db.CONFIG_PADRAO`), lido de la em vez de repetido:
# uma lista copiada aqui divergiria da varredura viva no dia em que o dono mexesse na config.
ATIVOS = [a.strip() for a in db.CONFIG_PADRAO["ativos"].split(",") if a.strip()]
TFS = [t.strip() for t in db.CONFIG_PADRAO["timeframes"].split(",") if t.strip()]
DIAS = 30
BANCA = 1000.0

# Quanto tempo separa, AO VIVO, o fechamento do candle da entrada do bot -- e o parametro
# que faz o backtest caber na granularidade de barra sem mentir sobre a latencia.
#
# A conta vem do `api.worker`: o scan roda por relogio a cada `INTERVALO_SCAN`=60s e o ciclo
# do auto-trader a cada `POLL_ATUALIZAR`=15s, entao a barra fecha em T, o sinal e gravado em
# ate T+60s e o bot abre no ciclo seguinte, em ate T+75s. Nao e detalhe cosmetico: com o
# ciclo do backtest valendo uma BARRA, tratar "o ciclo seguinte" como "a barra seguinte"
# poria a entrada 5 a 60 minutos depois do sinal -- e `auto_freshness_min` e 12 minutos.
# Num TF base de 15m ou 1h TODO sinal chegaria vencido ao bot e o backtest devolveria zero
# trades, silenciosamente, como se a estrategia nao operasse.
#
# Nao importo `api.INTERVALO_SCAN` porque `import api` arrasta FastAPI para dentro de um
# script de pesquisa; os dois numeros estao citados acima com o arquivo de origem.
LATENCIA_ENTRADA_S = 75

# Config do backtest = a config VIVA (`db.CONFIG_PADRAO`) com duas mudancas, e so duas.
# Cada uma esta declarada em `LIMITES`; nao ha terceira, de proposito -- quanto menos o
# backtest diverge do default vivo, menos ele mede um primo do sistema.
CONFIG_BACKTEST = {
    "auto_trade": "1",      # o objeto da medicao: sem isto `auto_executar` devolve {"ativo": False}
    "exigir_fluxo": "0",    # LIMITE (b): nao existe book/taker historico para reconstruir o portao
}

LIMITES = [
    ("(a) granularidade do ciclo",
     "o worker vivo marca posicao a cada 15s; aqui o ciclo e uma BARRA do TF mais fino. Stop "
     "e liquidacao sao detectados pelo extremo INTRABAR, entao o gatilho nao atrasa, e a "
     "entrada usa `LATENCIA_ENTRADA_S`=75s + abertura da barra seguinte, que e a latencia "
     "real. O que sobra e o FILL: como o preco observado no sub-passo E o extremo da barra, "
     "o `_fill_stop` ([P2-18]) quase sempre difere do gatilho e QUASE TODA saida por stop "
     "sai marcada `-gap`. Ao vivo o sufixo separa gap de fill limpo; aqui e o default do modelo.",
     "fill de stop PESSIMISTA (usa o extremo da barra, nao o preco 15s depois do gatilho)"),
    ("(b) portao de fluxo desligado",
     "`exigir_fluxo=0`. O portao le o book/taker AO VIVO e nao ha historico dele ([Q-4] o mede "
     "prospectivamente, justamente por isso). O backtest opera sinais que o vivo poderia "
     "recusar.",
     "MAIS trades que o vivo; direcao do efeito no P&L desconhecida (e o que o [Q-4] responde)"),
    ("(c) funding nao simulado",
     "`ex_fut` e um duble que devolve historico vazio, e vazio e medicao de ZERO ([P2-10]). "
     "O P&L sai sem carry.",
     "OTIMISTA para LONG em regime de funding positivo, que e o regime comum em cripto"),
    ("(d) indicadores sobre a serie INTEIRA, nao sobre 200 barras",
     "`signal_engine.analisa` calcula EMA/ATR/ADX/RSI sobre as ULTIMAS 200 barras que a "
     "exchange devolve; aqui eles saem da serie inteira. Sao recursivos (`ewm(adjust=False)`), "
     "entao os dois convergem mas nao coincidem. `divergencia_janela()` mede o residuo.",
     "ruido, nao vies dirigido -- mas e divergencia de paridade e por isso esta medida"),
    ("(e) gestor de saida ativo nao simulado",
     "`signal_engine.avaliar_saida` precisa de book ao vivo. Com o default `trailing_ativo=1` "
     "o proprio `auto_executar` DESLIGA o auto-fechar, entao no default nao ha divergencia -- "
     "e por isso o `Ambiente` RECUSA rodar com `trailing_ativo=0`, em vez de rodar mentindo.",
     "nenhuma no default; a recusa impede o caso em que haveria"),
    ("(f) posicoes abertas no fim ficam abertas",
     "o sistema vivo nao liquida carteira no fim do mes e o backtest tambem nao. Elas entram na "
     "curva de equity marcadas a mercado e ficam FORA das estatisticas de trade.",
     "nenhuma na curva; a amostra de trades e menor que o total de entradas"),
    ("(g) 1 posicao por ativo, herdada do vivo",
     "`auto_executar` filtra `ativo not in ativos_abertos`, entao o backtest tambem. Nao e "
     "aproximacao: e a regra.",
     "nenhuma"),
]


# --------------------------------------------------------------------------------------
# Os tres acoplamentos: relogio, preco, banco
# --------------------------------------------------------------------------------------
class _Relogio:
    """O instante SIMULADO. Um objeto mutavel, e nao um valor, porque quem o le e o codigo
    vivo atraves do shim de `pandas` -- e o shim precisa enxergar o avanco do ciclo."""

    def __init__(self, inicio):
        self.agora = pd.Timestamp(inicio)


def _pandas_com_relogio(relogio):
    """Um objeto que se comporta como o modulo `pandas`, exceto por `Timestamp.now()`.

    Por que trocar o modulo inteiro e nao so a funcao: `pd.Timestamp.now` e metodo de um
    tipo de extensao C, nao ha onde escrever nele. O que da para trocar e a referencia
    `pd` que cada modulo vivo guarda no proprio namespace -- reatribuicao de global, o
    mesmo mecanismo que `tests/conftest.py` usa para `db.DB` e pelo mesmo motivo (o codigo
    le o global a cada chamada). `__getattr__` repassa todo o resto para o pandas de
    verdade, entao `pd.Timedelta`, `pd.isna` e companhia continuam sendo os originais.
    """
    class _TS(pd.Timestamp):
        @classmethod
        def now(cls, tz=None):
            return pd.Timestamp(relogio.agora)

    class _PandasSimulado:
        Timestamp = _TS

        def __getattr__(self, nome):
            return getattr(pd, nome)

    return _PandasSimulado()


class _Precos:
    """Fonte de preco do ciclo. `simulador.preco_ao_vivo` aponta para ca.

    O mapa e reescrito a cada SUB-PASSO do ciclo (extremo adverso, extremo favoravel,
    fechamento), e e por ativo porque a assinatura viva e `preco_ao_vivo(ativo)` -- cada
    posicao aberta ve o preco da propria moeda, igual ao vivo.
    """

    def __init__(self):
        self.mapa = {}

    def __call__(self, ativo):
        p = self.mapa.get(ativo)
        if p is None:
            raise RuntimeError(f"backtest sem preco para {ativo} neste sub-passo")
        return float(p)


class _SemFunding:
    """Duble do cliente de futuros. Historico vazio = funding MEDIDO como zero ([P2-10]);
    um duble que levantasse excecao gravaria NULL, que e outra coisa (ausencia declarada)."""

    def fetch_funding_rate_history(self, ativo, since=None, limit=None):
        return []


class _SemRede:
    """Qualquer chamada de mercado que escapar da troca acima estoura aqui, alto. Backtest
    que silenciosamente busca preco ao vivo mede o presente, nao o historico."""

    def __getattr__(self, nome):
        def _boom(*a, **k):
            raise RuntimeError(f"backtest tentou rede: ex.{nome}()")
        return _boom


class _Contador:
    """Envelope que CONTA chamadas de uma funcao viva sem trocar o que ela faz.

    Existe por um buraco de observabilidade real: `auto_executar` pula o sinal quando
    `_tamanho` devolve 0 ([P2-8]) com um `continue` mudo -- nao entra em `res["rejeitados"]`
    nem em log. De fora nao da para distinguir "a fila estava vazia" de "a banca nao
    comportava nenhum dos candidatos", e essa e uma das perguntas do card. Contar a funcao
    viva responde sem tocar nela.
    """

    def __init__(self, fn):
        self.fn, self.chamadas, self.zeros = fn, 0, 0

    def __call__(self, *a, **k):
        r = self.fn(*a, **k)
        self.chamadas += 1
        if not r:
            self.zeros += 1
        return r


class Ambiente:
    """Troca banco, relogio, preco e rede dos modulos VIVOS -- e devolve tudo no `__exit__`.

    Restaurar nao e higiene opcional: a suite inteira compartilha esses modulos, e um
    `db.DB` ou um `simulador.pd` que vazasse deste bloco quebraria testes que nada tem a
    ver com o backtest. Por isso todo alvo entra numa pilha e sai dela na ordem inversa,
    inclusive se o corpo levantar.
    """

    def __init__(self, inicio, cfg=None, banca=BANCA, manter_db=False):
        self.relogio = _Relogio(inicio)
        self.precos = _Precos()
        self.cfg = dict(CONFIG_BACKTEST)
        self.cfg.update(cfg or {})
        self.banca = float(banca)
        self.manter_db = manter_db
        self.dir_db = None
        self.tamanho = None          # o `_Contador` sobre `autotrader._tamanho`
        self._pilha = []

    def _trocar(self, mod, nome, novo):
        self._pilha.append((mod, nome, getattr(mod, nome)))
        setattr(mod, nome, novo)

    def _congelar(self, dic):
        self._pilha.append((dic, None, dict(dic)))

    def __enter__(self):
        self.dir_db = tempfile.mkdtemp(prefix="backtest_portfolio_")
        self._trocar(db, "DB", os.path.join(self.dir_db, "portfolio.db"))
        db.init_db()
        with db.conectar() as con:
            con.execute("UPDATE banca SET inicial=?, atual=? WHERE id=1", (self.banca, self.banca))
        for k, v in self.cfg.items():
            db.set_config(k, v)
        # A recusa do limite (e): com `trailing_ativo=0` o vivo passa a fechar pelo gestor de
        # saida, que le book ao vivo e nao tem historico. Rodar assim seria medir um sistema
        # com uma politica de saida a menos e chamar o resultado de paridade.
        if str(db.get_config().get("trailing_ativo", "1")) not in ("1", "true", "True"):
            self.__exit__(None, None, None)
            raise ValueError("backtest de portfolio nao simula `avaliar_saida`: rode com "
                             "trailing_ativo=1 (o default vivo) ou o resultado nao e paridade")

        shim = _pandas_com_relogio(self.relogio)
        self._trocar(simulador, "pd", shim)
        self._trocar(autotrader, "pd", shim)
        self._trocar(simulador, "preco_ao_vivo", self.precos)
        self._trocar(simulador, "ex_fut", _SemFunding())
        self._trocar(simulador, "ex", _SemRede())
        self._trocar(signal_engine, "ex", _SemRede())
        # Alerta e EFEITO no mundo, nao regra: um backtest de 30 dias mandaria centenas de
        # mensagens de Telegram para o dono se a config tivesse token. Sem token `enviar` ja
        # e no-op, mas "ja e" nao e garantia -- a config do backtest e parametrizavel.
        self._trocar(alertas, "enviar", lambda msg: False)
        self.tamanho = _Contador(autotrader._tamanho)
        self._trocar(autotrader, "_tamanho", self.tamanho)

        # Contadores de modulo que o codigo vivo ACUMULA. Congelados e zerados: o backtest
        # precisa dos SEUS numeros, e um processo vivo que importasse este modulo nao pode
        # herdar a contagem dele.
        self._congelar(autotrader.CAPS_GEOMETRIA)
        self._congelar(simulador.ultima_marcacao)
        self._congelar(simulador.funding_medicao)
        self._congelar(signal_engine.ultimo_scan)
        autotrader.CAPS_GEOMETRIA.update(total=0, ultimo=None)
        return self

    def __exit__(self, *exc):
        for alvo, nome, antigo in reversed(self._pilha):
            if nome is None:
                alvo.clear()
                alvo.update(antigo)
            else:
                setattr(alvo, nome, antigo)
        self._pilha = []
        if self.dir_db and not self.manter_db:
            shutil.rmtree(self.dir_db, ignore_errors=True)
            self.dir_db = None
        return False


# --------------------------------------------------------------------------------------
# Sinais: a unica transcricao do modulo, e ela tem prova de equivalencia
# --------------------------------------------------------------------------------------
def sinais_da_barra(df, i, ativo, tf):
    """O que `signal_engine.analisa` devolveria para a barra FECHADA `i`.

    Por que transcrever em vez de chamar: `analisa` faz o `fetch_ohlcv` DENTRO dela, entao
    ela e inseparavel da rede -- nao ha parametro por onde entregar um candle historico.
    Transcrito esta so o empacotamento do dict; a pontuacao (`pontuar`/`pontuar_reversao`)
    e importada, e e ela que decide qualquer coisa.

    A equivalencia nao fica no meu relato: `tests/test_portfolio.py` chama `analisa` com o
    `fetch_ohlcv` dublado e compara campo a campo com esta funcao. Se o [Q-7] ou o [P1-10]
    mexerem em `analisa`, o teste quebra -- que e o ponto.
    """
    c = float(df["close"].iloc[i])
    vela_ms = int(df["timestamp"].iloc[i + 1])
    out = []
    for fn in (pontuar, pontuar_reversao):
        p = fn(df, i)
        if p is None or p["conviccao"] == 0:
            continue
        stop = c * (1 - p["direcao"] * p["stop_dist"])
        out.append(dict(ativo=ativo, tf=tf, tipo=p["tipo"],
                        direcao="LONG" if p["direcao"] == 1 else "SHORT",
                        conviccao=p["conviccao"], motivos=p["motivos"],
                        preco=round(c, 6), stop_sugerido=round(stop, 6),
                        adx=p["adx"], n_fatores=p["n_fatores"], vela_ms=vela_ms))
    return out


def divergencia_janela(df, amostras=40, limite=200):
    """Mede o limite (d): quanto a conviccao muda quando os indicadores saem de 200 barras
    (o que o scan vivo enxerga) em vez da serie inteira (o que o backtest enxerga).

    Devolve (n_comparadas, maior diferenca absoluta de conviccao, media). Numero, nao
    adjetivo -- e a unica forma de o relatorio dizer se o limite (d) e residual ou nao.
    """
    n = len(df)
    if n < limite + 5:
        return 0, 0.0, 0.0
    passo = max((n - limite) // max(amostras, 1), 1)
    difs = []
    for i in range(limite, n - 1, passo):
        cheio = pontuar(df, i)
        janela = preparar(df.iloc[i - limite + 1:i + 1].reset_index(drop=True))
        curto = pontuar(janela, len(janela) - 1)
        if cheio and curto:
            difs.append(abs(cheio["conviccao"] - curto["conviccao"]))
    if not difs:
        return 0, 0.0, 0.0
    return len(difs), float(max(difs)), round(sum(difs) / len(difs), 2)


# --------------------------------------------------------------------------------------
# Dados
# --------------------------------------------------------------------------------------
def _tf_ms(tf):
    """Duracao do TF em ms, pela tabela do `signal_engine` -- a mesma que decide a janela de
    vida do sinal. Uma segunda tabela aqui divergiria dela no dia em que alguem varresse 4h."""
    return signal_engine.TF_MIN[tf] * 60 * 1000


def carregar(ativos=None, tfs=None, dias=DIAS, verbose=True):
    """Baixa (com cache em CSV) e prepara os candles de cada par ativo x timeframe."""
    ativos, tfs = ativos or ATIVOS, tfs or TFS
    dfs = {}
    for a in ativos:
        for tf in tfs:
            df = preparar(baixar_ohlcv(a, tf, dias=dias))
            dfs[(a, tf)] = df
            if verbose:
                print(f"  {a:<12} {tf:<4} {len(df):>6} barras", flush=True)
    return dfs


# --------------------------------------------------------------------------------------
# O laco
# --------------------------------------------------------------------------------------
def rodar(ativos=None, tfs=None, dias=DIAS, banca=BANCA, cfg=None, dfs=None, verbose=True):
    """Roda o portfolio inteiro sobre o historico e devolve o resultado bruto.

    **O ciclo, e por que ele nao copia a ordem do `api.worker` linha a linha.** O worker
    roda `atualizar -> auto_executar -> equity -> scan` (`api.py:74-86`), e o efeito dessa
    ordem, depois do [P2-15], esta escrito no proprio comentario dele: o auto-trader consome
    o sinal *no ciclo seguinte*, "folgado dentro dos `auto_freshness_min`". Ciclo, la, e 15
    SEGUNDOS. Aqui um ciclo e uma BARRA. Copiar a ordem literalmente traduziria "15 s" em "1
    barra" e poria a entrada 5 a 60 minutos depois do sinal -- fora dos 12 minutos de
    freshness, e o backtest devolveria zero trades sem dizer por que.

    Entao o que se preserva e o EFEITO, nao a ordem: marcar -> scan (relogio em T) ->
    adiantar o relogio em `LATENCIA_ENTRADA_S` -> auto-trader -> snapshot de equity. O bot
    ve um sinal de ~75 s, que e a idade que ele ve ao vivo, e entra na ABERTURA da barra
    seguinte -- o primeiro preco negociado depois do sinal, sem olhar o futuro (e a mesma
    convencao do `backtest_plataforma`, `opens[i+1]`).
    """
    ativos = list(ativos or (sorted({a for a, _ in dfs}) if dfs else ATIVOS))
    tfs = list(tfs or (sorted({t for _, t in dfs}) if dfs else TFS))
    dfs = dfs if dfs is not None else carregar(ativos, tfs, dias, verbose)
    tfs = sorted(tfs, key=lambda t: signal_engine.TF_MIN[t])
    tf_base, base_ms = tfs[0], _tf_ms(tfs[0])

    # Indice "instante de FECHAMENTO da barra -> i". O scan vivo so ve barra fechada, entao
    # a barra i entra no ciclo cujo relogio marca timestamp[i] + duracao do TF. `i+1` tem de
    # existir porque `vela_ms` e o timestamp da barra SEGUINTE (mesma ancora do `analisa`).
    fechamentos, warmup = {}, []
    for (a, tf), df in dfs.items():
        ms = df["timestamp"].values
        fechamentos[(a, tf)] = {int(ms[i]) + _tf_ms(tf): i for i in range(60, len(df) - 1)}
        if len(df) > 61:
            warmup.append(int(ms[60]) + _tf_ms(tf))

    # `barras` e indexado pelo FECHAMENTO da barra (a que acabou de terminar no ciclo);
    # `aberturas`, pela ABERTURA (o primeiro preco negociado DEPOIS do ciclo). Sao dois
    # papeis diferentes: a primeira marca as posicoes que ja existiam, a segunda e o preco
    # de entrada de quem o auto-trader abrir agora.
    barras, aberturas = {}, {}
    for a in ativos:
        df = dfs[(a, tf_base)]
        barras[a] = {int(t) + base_ms: (float(o), float(h), float(l), float(c))
                     for t, o, h, l, c in zip(df["timestamp"], df["open"], df["high"],
                                              df["low"], df["close"])}
        aberturas[a] = {int(t): float(o) for t, o in zip(df["timestamp"], df["open"])}

    inicio_ms = max(warmup) if warmup else 0
    grade = sorted({m for a in ativos for m in barras[a] if m >= inicio_ms})
    if not grade:
        raise ValueError("historico curto demais: nenhum ciclo depois do warmup de 60 barras")

    retornos = {a: pd.Series({m: c for m, (_, _, _, c) in barras[a].items()}).sort_index().pct_change()
                for a in ativos}

    with Ambiente(pd.Timestamp(grade[0], unit="ms"), cfg=cfg, banca=banca) as amb:
        estado = _laco(amb, ativos, tfs, dfs, fechamentos, barras, aberturas, grade,
                       base_ms, verbose)
        estado.update(_colher(amb, ativos, tfs, dfs, retornos, estado))
    estado["banca_inicial"] = banca
    return estado


def _laco(amb, ativos, tfs, dfs, fechamentos, barras, aberturas, grade, base_ms, verbose):
    # A latencia nunca pode passar de meia barra: se passasse, o relogio do auto-trader
    # entraria no ciclo seguinte e a ordem dos eventos deixaria de ser monotona.
    latencia = pd.Timedelta(seconds=min(LATENCIA_ENTRADA_S, base_ms / 2000))
    ultimo = {}                       # ultimo OHLC conhecido por ativo (forward fill de buraco)
    curva_exp, curva_exp_eq, curva_risco, cestas = [], [], [], []
    dias_travados, rejeicoes = set(), {}
    ciclos_travados = 0
    dia_corrente, equity_inicio_dia = None, None
    n_sinais = n_confirmados = n_expirados = 0

    for k, ts_ms in enumerate(grade):
        ts = pd.Timestamp(ts_ms, unit="ms")
        amb.relogio.agora = ts
        dia = str(ts.date())
        novo_dia = dia != dia_corrente
        if dia_corrente is not None and novo_dia:
            # Virada de dia SIMULADO: se a trava marcou o dia que acabou, ela acionou nele.
            # E a leitura exata -- `guarda_risco` grava `trava_dia_em` no instante em que
            # tripa, e nada mais escreve nessa chave.
            if db.get_config().get("trava_dia_em", "") == dia_corrente:
                dias_travados.add(dia_corrente)
        dia_corrente = dia

        for a in ativos:
            b = barras[a].get(ts_ms)
            if b is not None:
                ultimo[a] = b
            elif a in ultimo:                       # buraco de candle: repete o fechamento
                c = ultimo[a][3]
                ultimo[a] = (c, c, c, c)
        fechos = {a: ohlc[3] for a, ohlc in ultimo.items()}

        # ---- 1) marcacao das posicoes abertas -------------------------------------------
        abertas = db.listar("posicoes", 200, "WHERE status='aberta'")
        if abertas:
            direcoes = {p["ativo"]: p["direcao"] for p in abertas}
            # Sub-passo ADVERSO primeiro: a barra nao diz se a maxima veio antes da minima, e
            # a convencao conservadora e supor que o extremo CONTRA a posicao chegou primeiro
            # (a mesma do `backtest_plataforma`, que testa stop/liquidacao contra low/high).
            amb.precos.mapa = {a: (ohlc[2] if direcoes.get(a) == "LONG" else
                                   ohlc[1] if direcoes.get(a) == "SHORT" else ohlc[3])
                               for a, ohlc in ultimo.items()}
            simulador.atualizar()
            # Sub-passo FAVORAVEL: so avanca o trailing. O worker vivo poda ~20 vezes dentro
            # de uma barra de 5m, entao ele VE a maxima; um backtest que so olhasse fechamento
            # daria ao trailing uma inercia que o vivo nao tem.
            if db.listar("posicoes", 1, "WHERE status='aberta'"):
                amb.precos.mapa = {a: (ohlc[1] if direcoes.get(a) == "LONG" else
                                       ohlc[2] if direcoes.get(a) == "SHORT" else ohlc[3])
                                   for a, ohlc in ultimo.items()}
                simulador.atualizar()
                amb.precos.mapa = dict(fechos)
                simulador.atualizar()

        # ---- 2) scan (relogio ainda em T: o sinal nasce no fechamento da barra) ------------
        cfg = db.get_config()
        n_expirados += signal_engine.expirar_sinais(ts)
        with db.conectar() as con:
            for a in ativos:
                for tf in tfs:
                    i = fechamentos[(a, tf)].get(ts_ms)
                    if i is None:
                        continue
                    for s in sinais_da_barra(dfs[(a, tf)], i, a, tf):
                        n_sinais += 1
                        if not signal_engine.confirmado(s, a, cfg)[0]:
                            continue
                        n_confirmados += 1
                        if not signal_engine._repetido(con, s, a, tf, "novo", str(ts)):
                            signal_engine._gravar(con, str(ts), s, a, tf, "novo", None)

        # ---- 3) auto-trader, 75 s depois do sinal e na ABERTURA da barra seguinte ----------
        # `saidas=None`: com `trailing_ativo=1` (default vivo, exigido pelo `Ambiente`) o
        # proprio `auto_executar` ignora o auto-fechar. Passar None nao apaga comportamento.
        amb.relogio.agora = ts + latencia
        amb.precos.mapa = {a: aberturas[a].get(ts_ms, fechos.get(a)) for a in ativos}
        res = autotrader.auto_executar(None)
        amb.relogio.agora = ts       # o snapshot de equity pertence ao INSTANTE DO CICLO: e ele
        if res.get("motivo") == "trava diária ativa":   # que ancora o dia e a curva do relatorio
            dias_travados.add(dia)
            ciclos_travados += 1
        for r in res.get("rejeitados", []):
            chave = str(r.get("erro", ""))[:60]
            rejeicoes[chave] = rejeicoes.get(chave, 0) + 1

        # ---- 4) snapshot de equity (o que o worker grava a cada ciclo) ---------------------
        # A carteira e relida AQUI, e nao reaproveitada de `abertas` la de cima: entre um
        # ponto e outro rodaram a marcacao (que fecha) e o auto-trader (que abre). Amostrar a
        # exposicao com a lista velha contaria margem de posicao ja liquidada.
        with db.conectar() as con:
            banca_atual = con.execute("SELECT atual FROM banca WHERE id=1").fetchone()["atual"]
            carteira = [dict(r) for r in con.execute(
                "SELECT ativo,direcao,valor_reais,alavancagem,entrada,stop,pnl "
                "FROM posicoes WHERE status='aberta'")]
            equity = banca_atual + sum((p["pnl"] or 0) for p in carteira)
            con.execute("INSERT INTO equity(ts,banca,equity_total) VALUES(?,?,?)",
                        (str(ts), banca_atual, equity))
        if novo_dia or equity_inicio_dia is None:
            equity_inicio_dia = equity          # o MESMO baseline que `guarda_risco` le do banco
        margem = sum((p["valor_reais"] or 0) for p in carteira)
        # DOIS denominadores, e a diferenca entre eles nao e detalhe. O teto `exposicao_max`
        # do `simulador.abrir` compara a margem com a BANCA REALIZADA; quem le o painel pensa
        # em patrimonio. Com prejuizo aberto o patrimonio e menor que a banca, entao a
        # exposicao vista de fora passa dos 50% sem que guarda nenhuma tenha sido violada.
        curva_exp.append(margem / banca_atual if banca_atual else 0.0)
        curva_exp_eq.append(margem / equity if equity else 0.0)
        # `_risco_posicao` e a funcao VIVA do teto de risco agregado, e o denominador e o
        # equity do INICIO DO DIA -- os dois iguais aos de `guarda_risco`, senao a fracao aqui
        # nao seria comparavel com o teto que o `abrir` aplica.
        curva_risco.append(sum(simulador._risco_posicao(p["valor_reais"], p["alavancagem"],
                                                        p["entrada"], p["stop"])
                               for p in carteira) / equity_inicio_dia
                           if equity_inicio_dia else 0.0)
        if len(carteira) >= 2:
            cestas.append([(p["ativo"], 1 if p["direcao"] == "LONG" else -1) for p in carteira])

        if verbose and k % max(len(grade) // 20, 1) == 0:
            print(f"  {k:>6}/{len(grade)}  {ts}  equity R$ {equity:,.2f}  "
                  f"abertas {len(carteira)}", flush=True)

    if db.get_config().get("trava_dia_em", "") == dia_corrente:
        dias_travados.add(dia_corrente)
    return {"ciclos": len(grade), "exposicao": curva_exp, "exposicao_equity": curva_exp_eq,
            "risco": curva_risco,
            "cestas": cestas, "dias_travados": sorted(dias_travados),
            "ciclos_travados": ciclos_travados, "rejeicoes": rejeicoes,
            "sinais_gerados": n_sinais, "sinais_confirmados": n_confirmados,
            "sinais_expirados": n_expirados,
            "periodo": (str(pd.Timestamp(grade[0], unit="ms")),
                        str(pd.Timestamp(grade[-1], unit="ms")))}


def _colher(amb, ativos, tfs, dfs, retornos, estado):
    """Le do banco simulado tudo que o relatorio precisa, ANTES de o `Ambiente` apaga-lo."""
    met = db.metricas()
    with db.conectar() as con:
        motivos = {r["motivo_saida"]: r["n"] for r in con.execute(
            "SELECT motivo_saida, COUNT(*) n FROM trades GROUP BY motivo_saida ORDER BY n DESC")}
        win_tf = {r["tf"]: (r["w"], r["n"]) for r in con.execute(
            "SELECT s.tf tf, SUM(CASE WHEN t.pnl_reais>0 THEN 1 ELSE 0 END) w, COUNT(*) n "
            "FROM trades t JOIN sinais s ON s.id=t.sinal_id GROUP BY s.tf")}
        abertas_fim = con.execute("SELECT COUNT(*) n, COALESCE(SUM(pnl),0) p "
                                  "FROM posicoes WHERE status='aberta'").fetchone()
        equity_fim = con.execute("SELECT equity_total FROM equity ORDER BY rowid DESC "
                                 "LIMIT 1").fetchone()
        curva = [(r["ts"], r["equity_total"]) for r in con.execute(
            "SELECT ts, equity_total FROM equity ORDER BY rowid")]
    return {"metricas": met, "motivos_saida": motivos, "win_por_tf": win_tf, "curva": curva,
            "curva_diaria": _curva_diaria(curva),
            "abertas_no_fim": abertas_fim["n"], "pnl_aberto_no_fim": round(abertas_fim["p"] or 0, 2),
            "equity_final": equity_fim["equity_total"] if equity_fim else None,
            "caps_geometria": dict(autotrader.CAPS_GEOMETRIA),
            "sizing_zerado": amb.tamanho.zeros, "sizing_chamadas": amb.tamanho.chamadas,
            "concentracao": concentracao(estado["cestas"], retornos),
            "divergencia_janela": divergencia_janela(dfs[(ativos[0], tfs[0])])}


def _curva_diaria(curva):
    """A curva de equity condensada por DIA simulado, com o drawdown intradia.

    O drawdown do dia sai do pico DENTRO do dia, e nao do pico global: e o par natural da
    trava diaria, que tambem mede contra o inicio do dia (`simulador.guarda_risco`). O
    drawdown global continua sendo o `max_dd_mtm_pct` de `db.metricas()`.
    """
    dias, ordem = {}, []
    for ts, eq in curva:
        d = ts[:10]
        if d not in dias:
            dias[d] = {"dia": d, "abre": eq, "min": eq, "max": eq, "fecha": eq, "pico": eq,
                       "dd_pct": 0.0}
            ordem.append(d)
        r = dias[d]
        r["min"], r["max"], r["fecha"] = min(r["min"], eq), max(r["max"], eq), eq
        r["pico"] = max(r["pico"], eq)
        if r["pico"]:
            r["dd_pct"] = max(r["dd_pct"], (r["pico"] - eq) / r["pico"] * 100)
    return [dias[d] for d in ordem]


def concentracao(cestas, retornos):
    """Concentracao por correlacao: 5 posicoes em cripto nao sao 5 apostas.

    Para cada ciclo com >=2 posicoes abertas, mede a correlacao media dos pares COM SINAL
    (um LONG e um SHORT em moedas correlacionadas se cancelam, e isso tem de aparecer como
    correlacao NEGATIVA). Dai sai `posicoes efetivas` = n / (1 + (n-1)*rho), o numero de
    apostas independentes equivalentes: com rho=1 cinco posicoes valem uma; com rho=0 valem
    cinco. E o numero que o card pede quando diz "5 posicoes ~ 1 posicao grande em beta".

    A matriz de correlacao e ESTATICA (o periodo inteiro), nao rolante -- declarado aqui
    porque rolante mediria tambem a variacao do regime, e o card pergunta pela concentracao.
    """
    if not cestas:
        return {"ciclos": 0}
    matriz = pd.DataFrame(retornos).corr()
    n_pos, rhos, efetivas = [], [], []
    for cesta in cestas:
        n = len(cesta)
        pares = [matriz.loc[a, b] * sa * sb
                 for x, (a, sa) in enumerate(cesta) for (b, sb) in cesta[x + 1:]]
        pares = [p for p in pares if p == p]                        # descarta NaN
        if not pares:
            continue
        rho = sum(pares) / len(pares)
        denom = 1 + (n - 1) * rho
        n_pos.append(n)
        rhos.append(rho)
        # `denom <= 0` e o hedge perfeito (rho = -1/(n-1)): a exposicao liquida ao beta comum
        # zera e a formula diverge. O teto e `n` -- nunca menos apostas do que posicoes, e
        # nunca mais. Mandar isso para 1.0 (o erro obvio) inverteria a leitura: a carteira
        # mais diversificada possivel apareceria como a mais concentrada.
        efetivas.append(float(n) if denom <= 0 else min(max(n / denom, 1.0), float(n)))
    if not n_pos:
        return {"ciclos": 0}
    media_n = sum(n_pos) / len(n_pos)
    media_ef = sum(efetivas) / len(efetivas)
    return {"ciclos": len(n_pos), "posicoes_medias": round(media_n, 2),
            "rho_medio": round(sum(rhos) / len(rhos), 3),
            "efetivas_medias": round(media_ef, 2),
            "fator_concentracao": round(media_n / media_ef, 2) if media_ef else None}


# --------------------------------------------------------------------------------------
# Relatorio
# --------------------------------------------------------------------------------------
def relatorio(res):
    m = res["metricas"]
    banca = res.get("banca_inicial", BANCA)
    fim = res["equity_final"] or 0
    p = print
    p("\n" + "=" * 86)
    p("[Q-5] BACKTEST DE PORTFOLIO — a dinamica de banca do sistema vivo")
    p("=" * 86)
    p(f"periodo simulado : {res['periodo'][0]}  ->  {res['periodo'][1]}   ({res['ciclos']} ciclos)")
    p(f"banca            : R$ {banca:,.2f} inicial  ->  R$ {fim:,.2f} final "
      f"({(fim / banca - 1) * 100:+.2f}%)")

    p("\n--- CURVA E DRAWDOWN ------------------------------------------------------------")
    p(f"  drawdown maximo (mark-to-market, curva de equity) : {m['max_dd_mtm_pct']:.1f}%")
    p(f"  drawdown maximo (realizado, so trades fechados)   : R$ {m['max_drawdown']:,.2f} "
      f"({m['max_drawdown_pct']:.1f}%)")
    p(f"  sharpe (diario, anualizado) {m['sharpe']:>7}   calmar {m['calmar']:>7}   "
      f"sqn {m['sqn']:>6}   sqn_r {m['sqn_r']:>6}")
    # A curva por DIA, e nao so o numero de pontos: o card pede a curva REGISTRADA, e uma
    # linha "2145 pontos" nao e curva -- e a promessa de uma. Por dia cabe num relatorio
    # colavel; a serie cheia fica em `res["curva"]` para quem quiser plotar.
    p(f"  curva ({len(res['curva'])} pontos, {len(res['curva_diaria'])} dias simulados):")
    p(f"  {'dia':<12}{'abertura':>12}{'minima':>12}{'maxima':>12}{'fechamento':>13}{'dd no dia':>11}")
    for d in res["curva_diaria"]:
        p(f"  {d['dia']:<12}{d['abre']:>12,.2f}{d['min']:>12,.2f}{d['max']:>12,.2f}"
          f"{d['fecha']:>13,.2f}{d['dd_pct']:>10.1f}%")

    p("\n--- TRAVA DIARIA ----------------------------------------------------------------")
    p(f"  dias em que a trava acionou : {len(res['dias_travados'])}")
    for d in res["dias_travados"]:
        p(f"      {d}")
    p(f"  ciclos com entrada bloqueada pela trava : {res['ciclos_travados']}")

    p("\n--- EXPOSICAO -------------------------------------------------------------------")
    exp, expe, risco = res["exposicao"], res["exposicao_equity"], res["risco"]
    p(f"  margem / BANCA realizada    : media {sum(exp) / len(exp) * 100:.1f}%   "
      f"maxima {max(exp) * 100:.1f}%   (e este o denominador do teto exposicao_max 50%)")
    p(f"  margem / EQUITY (patrimonio): media {sum(expe) / len(expe) * 100:.1f}%   "
      f"maxima {max(expe) * 100:.1f}%   (passa de 50% com prejuizo aberto, sem furar guarda)")
    p(f"  risco-ate-o-stop / equity do inicio do dia : media {sum(risco) / len(risco) * 100:.1f}%"
      f"   maxima {max(risco) * 100:.1f}%   (teto vivo: risco_aberto_max 10%)")
    p(f"  posicoes abertas no fim     : {res['abertas_no_fim']}  "
      f"(P&L nao realizado R$ {res['pnl_aberto_no_fim']:+,.2f})")

    c = res["concentracao"]
    p("\n--- CONCENTRACAO POR CORRELACAO -------------------------------------------------")
    if c.get("ciclos"):
        p(f"  ciclos com >=2 posicoes     : {c['ciclos']}")
        p(f"  posicoes simultaneas medias : {c['posicoes_medias']}")
        p(f"  correlacao media com sinal  : {c['rho_medio']:+.3f}")
        p(f"  posicoes EFETIVAS medias    : {c['efetivas_medias']}   "
          f"=> fator de concentracao {c['fator_concentracao']}x")
        p(f"  leitura: {c['posicoes_medias']} posicoes simultaneas valem "
          f"{c['efetivas_medias']} apostas independentes.")
    else:
        p("  nunca houve 2 posicoes simultaneas — nada a medir")

    p("\n--- TRADES ----------------------------------------------------------------------")
    p(f"  {m['n_trades']} trades | win {m['win_rate']}% | P&L R$ {m['pnl_total']:+,.2f} | "
      f"taxas R$ {m['taxa_total']:,.2f} | PF {m['profit_factor']}")
    p(f"  expectancia R$ {m['expectancia']:+.2f}  |  expectancia_r {m['expectancia_r']:+.3f} R")
    if m["por_conviccao"]:
        p(f"  {'faixa conv':<12}{'trades':>8}{'win':>8}{'P&L':>12}")
        for f in m["por_conviccao"]:
            p(f"  {f['faixa']:<12}{f['n']:>8}{f['win_rate']:>7.1f}%{f['pnl']:>+12,.2f}")
    if res["win_por_tf"]:
        p(f"  {'tf':<12}{'trades':>8}{'win':>8}   (a mistura que o backtest por-ativo nao reproduz)")
        for tf, (w, n) in sorted(res["win_por_tf"].items()):
            p(f"  {str(tf):<12}{n:>8}{(w or 0) / n * 100:>7.1f}%")
    p(f"  motivos de saida: {res['motivos_saida'] or '—'}")

    p("\n--- A FILA ----------------------------------------------------------------------")
    p(f"  sinais pontuados {res['sinais_gerados']} | confirmados pelos portoes "
      f"{res['sinais_confirmados']} | expirados na janela {res['sinais_expirados']}")
    p(f"  sizing: {res['sizing_chamadas']} chamadas de `_tamanho`, "
      f"{res['sizing_zerado']} devolveram 0 (=sinal PULADO por banca, [P2-8])")
    p(f"  cap geometrico de alavancagem ([P1-11]): {res['caps_geometria']['total']} vezes")
    if res["rejeicoes"]:
        p("  recusas do `abrir`:")
        for k, v in sorted(res["rejeicoes"].items(), key=lambda kv: -kv[1]):
            p(f"      {v:>5}x  {k}")

    d = res["divergencia_janela"]
    p("\n--- LIMITES DECLARADOS ----------------------------------------------------------")
    p("  Numeros de banca deste backtest NAO descrevem o vivo sem estas ressalvas:")
    for nome, oque, direcao in LIMITES:
        p(f"  {nome}")
        p(f"      {oque}")
        p(f"      vies: {direcao}")
    p(f"  medida do limite (d): {d[0]} barras comparadas, maior diferenca de conviccao "
      f"{d[1]:.0f} pts, media {d[2]} pts")
    p("=" * 86 + "\n")
    return res


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="[Q-5] backtest de portfolio")
    ap.add_argument("--dias", type=int, default=DIAS)
    ap.add_argument("--ativos", type=int, default=len(ATIVOS),
                    help="quantos ativos do topo da lista viva")
    ap.add_argument("--tfs", default=",".join(TFS),
                    help="timeframes varridos; o mais fino define a cadencia do ciclo")
    ap.add_argument("--banca", type=float, default=BANCA)
    a = ap.parse_args()
    alvo = ATIVOS[:a.ativos]
    tfs = [t.strip() for t in a.tfs.split(",") if t.strip()]
    ciclos = a.dias * 24 * 60 // min(signal_engine.TF_MIN[t] for t in tfs)
    print(f"[Q-5] {len(alvo)} ativos x {len(tfs)} TFs ({a.tfs}) x {a.dias}d "
          f"-> ~{ciclos} ciclos (~{ciclos * 0.5 / 60:.0f} min). cache em pesquisa/dados_cache/")
    relatorio(rodar(ativos=alvo, tfs=tfs, dias=a.dias, banca=a.banca))
