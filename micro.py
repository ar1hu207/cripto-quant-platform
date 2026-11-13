"""[MICRO-1] Laboratório de microtrades: centenas de trades por minuto, em papel, no book real.

É a terceira vista do painel. Banca, banco (`micro.db`) e motor são PRÓPRIOS: nada aqui toca
banca, posições, tetos ou trava do bot principal, e nada do bot principal lê o que mora aqui.
A única coisa que vem de lá é a taxa (`taxa_por_lado`), lida da config, e só para leitura,
porque cobrar daqui uma taxa diferente da que o bot paga seria inventar um custo.

A estratégia: OFI + microprice, saída por tempo
-----------------------------------------------
Cont, Kukanov & Stoikov (2014, "The price impact of order book events") mostram que a
variação de curtíssimo prazo do preço médio é aproximadamente linear no Order Flow Imbalance
dividido pela profundidade:  ΔP ≈ β · OFI / D.  A cada atualização do topo do livro
(`bookTicker` da Binance USDT-M), o incremento do OFI é

    e = Qb·1{Pb ≥ pb} − qb·1{Pb ≤ pb} − Qa·1{Pa ≤ pa} + qa·1{Pa ≥ pa}

(minúsculas = topo anterior, maiúsculas = topo novo). Soma-se `e` na janela `janela_ofi_ms`,
divide-se pela profundidade média D (EWMA de (Qb+Qa)/2), e o resultado vira z-score contra o
próprio histórico do ativo (EWMA do quadrado). Com o limiar adaptativo, o mesmo `z_entrada`
serve para o BTC, com ~900 atualizações/s, e para a DOGE, com ~3.

Entrada: z > z_entrada com microprice acima do meio (Qb > Qa) → compra no ASK; o simétrico
vende no BID. Saída: `horizonte_ms` depois do fill, ou antes se o z virar além de −z_entrada,
sempre no lado oposto do livro. Entre a decisão e a execução passam `latencia_ms`, e o preço
é o do livro DEPOIS do atraso, não o do instante da decisão.

O resultado em três camadas
---------------------------
Cada trade grava três números em bps. O que este laboratório mede é a diferença entre eles:
  sinal      meio→meio, nos instantes das decisões: o quanto o OFI previu, sem custo nenhum
  executado  preço de execução: o sinal menos spread e latência
  líquido    o executado menos a taxa nas duas pernas
A sonda de 12/11 mediu ~0,2 bps de movimento do BTC em 20 s, contra 10 bps de taxa taker por
ida e volta. A previsão honesta é a curva líquida descer reta enquanto a do sinal fica perto de
zero. Ver isso ao vivo é o objetivo. Não maquie zerando a taxa: a camada `sinal` já mostra o
que existe antes de qualquer custo.

Uma ordem que espera a latência já conta em `max_por_ativo`, pela mesma razão do [EX-1]: teto
que só olha o que já abriu autoriza a exposição que ele mesmo proíbe.
"""
import asyncio
import collections
import json
import math
import os
import re
import sqlite3
import threading
import time
from datetime import datetime

import db
from logbot import log

WS_URL = "wss://fstream.binance.com/stream?streams="

# Os valores ficam no banco (`micro_config`); isto é só o que um banco novo recebe, no mesmo
# papel do db.CONFIG_PADRAO. Todos como string, como na config do bot.
PADRAO = {
    "ligado": "0",
    "ativos": "btcusdt,ethusdt,solusdt,xrpusdt,dogeusdt,bnbusdt,avaxusdt,linkusdt,suiusdt,1000pepeusdt",
    "janela_ofi_ms": "1000",      # janela em que o OFI é somado
    "z_entrada": "2.0",           # limiar em desvios do próprio ativo
    "horizonte_ms": "3000",       # tempo máximo em posição
    "max_por_ativo": "3",         # posições + ordens esperando latência, por ativo
    "intervalo_min_ms": "250",    # espaço mínimo entre duas entradas no mesmo ativo
    "latencia_ms": "100",         # dl380 (Brasil) até a Binance passa de 100 ms; 0 é otimismo
    "notional": "100",            # US$ por trade, sem alavancagem
    "banca_inicial": "10000",
    "perda_max_pct": "100",       # perdeu isto da banca → desliga sozinho (100 = quebrou)
}

# chave: (tipo, mínimo, máximo). `ligado` não entra: liga e desliga por rota própria.
CATALOGO = {
    "z_entrada": (float, 0.5, 10.0),
    "janela_ofi_ms": (int, 100, 10_000),
    "horizonte_ms": (int, 200, 120_000),
    "max_por_ativo": (int, 1, 10),
    "intervalo_min_ms": (int, 0, 60_000),
    "latencia_ms": (int, 0, 2_000),
    "notional": (float, 10.0, 100_000.0),
    "banca_inicial": (float, 100.0, 10_000_000.0),
    "perda_max_pct": (float, 1.0, 100.0),
}
ATIVO_RE = re.compile(r"^[a-z0-9]{2,20}usdt$")
MAX_ATIVOS = 20

# As médias móveis são por TEMPO, não por evento. A primeira versão usava memória de ~500
# eventos: no BTC (~900 atualizações/s) isso é meio segundo, o desvio se adaptava a cada
# rajada e o z quase nunca passava do limiar -- 5 trades de BTC em 60 s ao vivo, contra 12 da
# PEPE, que tem 2 atualizações/s. Por tempo, o mesmo z quer dizer o mesmo em todo ativo.
TAU_PROF_S = 30.0          # memória da profundidade média
TAU_VAR_S = 60.0           # memória do desvio do OFI normalizado
AQUECIMENTO_S = 30.0       # segundos de história por ativo antes do primeiro trade
AQUECIMENTO_N = 50         # ...e pelo menos estes eventos
RETENCAO_DIAS = 2          # micro_trades: centenas por minuto viram ~400 mil linhas por dia
MINUTOS_CURVA = 180        # pontos da curva no /micro/estado (o payload fica pequeno)


def _agora_txt():
    # Convenção da casa: hora de São Paulo, sem fuso (CLAUDE.md §1).
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


# ---------------------------------------------------------------- motor (puro, sem rede)

class _Livro:
    __slots__ = ("pb", "qb", "pa", "qa", "janela", "soma", "prof", "var", "n", "z",
                 "ult_entrada", "t", "t0", "ocup")

    def __init__(self):
        self.pb = self.qb = self.pa = self.qa = None
        self.janela = collections.deque()
        self.soma = 0.0
        self.prof = None
        self.var = 0.0
        self.n = 0
        self.z = 0.0
        self.ult_entrada = -1e18
        self.t = None
        self.t0 = None
        self.ocup = 0          # posições + ordens de abertura deste ativo (o teto lê isto)

    @property
    def meio(self):
        return (self.pb + self.pa) / 2


class Motor:
    """Recebe o topo do livro e o relógio; devolve trades fechados em `self.fechados`.

    Não sabe de rede nem de banco, para poder ser testado com livro sintético. Os tempos `t`
    são de relógio monotônico em segundos."""

    def __init__(self, cfg, taxa_lado, pnl_base=0.0):
        self.ativos = [a for a in cfg["ativos"].split(",") if a]
        self.janela_s = int(cfg["janela_ofi_ms"]) / 1000
        self.z_entrada = float(cfg["z_entrada"])
        self.horizonte_s = int(cfg["horizonte_ms"]) / 1000
        self.max_por_ativo = int(cfg["max_por_ativo"])
        self.intervalo_s = int(cfg["intervalo_min_ms"]) / 1000
        self.latencia_s = int(cfg["latencia_ms"]) / 1000
        self.notional = float(cfg["notional"])
        self.banca_inicial = float(cfg["banca_inicial"])
        self.piso = self.banca_inicial * (1 - float(cfg["perda_max_pct"]) / 100)
        self.taxa = float(taxa_lado)
        self.pnl = pnl_base                     # líquido acumulado desde o último zerar
        self.livros = {a: _Livro() for a in self.ativos}
        self.ordens = []                        # esperando a latência: abrir ou fechar
        self.posicoes = []                      # abertas
        self.fechados = []                      # trades prontos para gravar/agregar
        self.parado_por = None

    # -- contagem para o teto: ordem pendente de abertura conta como posição ([EX-1] regra 1)
    def _ocupacao(self, ativo):
        return self.livros[ativo].ocup

    @property
    def banca(self):
        return self.banca_inicial + self.pnl

    def livro(self, ativo, t, pb, qb, pa, qa):
        lv = self.livros.get(ativo)
        if lv is None or pb <= 0 or pa <= 0 or pa < pb:
            return
        if lv.pb is not None:
            e = ((qb if pb >= lv.pb else 0.0) - (lv.qb if pb <= lv.pb else 0.0)
                 - (qa if pa <= lv.pa else 0.0) + (lv.qa if pa >= lv.pa else 0.0))
            lv.janela.append((t, e))
            lv.soma += e
            while lv.janela and t - lv.janela[0][0] > self.janela_s:
                lv.soma -= lv.janela.popleft()[1]
        prof = (qb + qa) / 2
        if lv.t is None:
            lv.t0, lv.prof, dt = t, prof, 0.0
        else:
            dt = max(t - lv.t, 0.0)
            lv.prof += (1 - math.exp(-dt / TAU_PROF_S)) * (prof - lv.prof)
        x = lv.soma / lv.prof if lv.prof > 0 else 0.0
        # peso pelo tempo que o valor anterior VALEU: rajada de 100 eventos em 10 ms pesa 10 ms
        lv.var += (1 - math.exp(-dt / TAU_VAR_S)) * (x * x - lv.var) if lv.n else x * x - lv.var
        lv.n += 1
        aquecido = lv.n >= AQUECIMENTO_N and t - lv.t0 >= AQUECIMENTO_S
        lv.z = x / math.sqrt(lv.var) if lv.var > 0 and aquecido else 0.0
        lv.pb, lv.qb, lv.pa, lv.qa, lv.t = pb, qb, pa, qa, t

        self._executar(t, ativo)
        self._saidas(t, ativo)
        self._entrada(t, ativo, lv)

    def relogio(self, t):
        """Chamado a cada ~100 ms. Ativo com pouca atualização (DOGE, ~3/s) não pode prender
        uma saída por tempo esperando o próximo evento dele; o livro parado continua válido."""
        for a in self.ativos:
            if self.livros[a].pb is not None and self.livros[a].ocup:
                self._executar(t, a)
                self._saidas(t, a)

    def _entrada(self, t, ativo, lv):
        if self.parado_por or lv.z == 0.0:
            return
        if lv.z > self.z_entrada and lv.qb > lv.qa:
            lado = 1
        elif lv.z < -self.z_entrada and lv.qa > lv.qb:
            lado = -1
        else:
            return
        if t - lv.ult_entrada < self.intervalo_s or self._ocupacao(ativo) >= self.max_por_ativo:
            return
        lv.ult_entrada = t
        lv.ocup += 1
        self.ordens.append({"tipo": "abre", "ativo": ativo, "lado": lado, "t_exec": t + self.latencia_s,
                            "meio_dec": lv.meio, "z": lv.z})
        self._executar(t, ativo)                # latência 0 executa no mesmo livro

    def _saidas(self, t, ativo):
        lv = self.livros[ativo]
        if not lv.ocup:
            return
        for p in self.posicoes:
            if p["ativo"] != ativo or p["saindo"]:
                continue
            motivo = None
            if t - p["t_fill"] >= self.horizonte_s:
                motivo = "tempo"
            elif lv.z * p["lado"] < -self.z_entrada:
                motivo = "virada"
            if motivo:
                p["saindo"] = True
                self.ordens.append({"tipo": "fecha", "ativo": ativo, "pos": p, "motivo": motivo,
                                    "t_exec": t + self.latencia_s, "meio_dec": lv.meio})
        self._executar(t, ativo)

    def _executar(self, t, ativo):
        if not self.ordens:
            return
        lv = self.livros[ativo]
        restam = []
        for o in self.ordens:
            if o["ativo"] != ativo or t < o["t_exec"]:
                restam.append(o)
                continue
            if o["tipo"] == "abre":
                px = lv.pa if o["lado"] == 1 else lv.pb
                self.posicoes.append({"ativo": ativo, "lado": o["lado"], "px": px, "meio": o["meio_dec"],
                                      "z": o["z"], "t_fill": t, "ts": _agora_txt(), "saindo": False})
            else:
                p = o["pos"]
                px = lv.pb if p["lado"] == 1 else lv.pa
                self.posicoes.remove(p)
                lv.ocup -= 1
                self._fechar(p, px, o["meio_dec"], t, o["motivo"])
        self.ordens = restam

    def _fechar(self, p, px_sai, meio_sai, t, motivo):
        lado, n = p["lado"], self.notional
        rel = px_sai / p["px"]
        pnl_exec = n * lado * (rel - 1)
        pnl_liq = pnl_exec - self.taxa * n * (1 + rel)    # taxa nas duas pernas, sobre o notional de cada uma
        bps_sinal = lado * (meio_sai / p["meio"] - 1) * 1e4
        self.pnl += pnl_liq
        self.fechados.append({
            "ts_abre": p["ts"], "ts_fecha": _agora_txt(), "ativo": p["ativo"], "lado": lado,
            "px_ent": p["px"], "px_sai": px_sai, "mid_ent": p["meio"], "mid_sai": meio_sai,
            "bps_sinal": bps_sinal, "bps_exec": pnl_exec / n * 1e4, "bps_liq": pnl_liq / n * 1e4,
            "pnl_sinal": n * bps_sinal / 1e4, "pnl_exec": pnl_exec, "pnl_liq": pnl_liq,
            "z": p["z"], "dur_ms": int((t - p["t_fill"]) * 1000), "motivo": motivo})
        if self.banca <= self.piso and not self.parado_por:
            self.parado_por = f"banca {self.banca:.2f} chegou ao piso {self.piso:.2f}"


# ---------------------------------------------------------------- banco próprio

def caminho_db():
    # Ao lado do banco do bot: a conta B, que tem DB_PATH próprio, ganha micro.db próprio junto.
    return os.environ.get("MICRO_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(db.DB)), "micro.db")


def _con():
    c = sqlite3.connect(caminho_db(), timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init():
    with _con() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS micro_config (chave TEXT PRIMARY KEY, valor TEXT);
        CREATE TABLE IF NOT EXISTS micro_trades (
            id INTEGER PRIMARY KEY, ts_abre TEXT, ts_fecha TEXT, ativo TEXT, lado INTEGER,
            px_ent REAL, px_sai REAL, mid_ent REAL, mid_sai REAL,
            bps_sinal REAL, bps_exec REAL, bps_liq REAL, pnl_liq REAL, z REAL, dur_ms INTEGER, motivo TEXT);
        CREATE INDEX IF NOT EXISTS ix_micro_trades_ts ON micro_trades(ts_fecha);
        CREATE TABLE IF NOT EXISTS micro_minuto (
            minuto TEXT PRIMARY KEY, n INTEGER, ganhos_sinal INTEGER, ganhos_liq INTEGER,
            sinal REAL, exec REAL, liq REAL);
        CREATE TABLE IF NOT EXISTS micro_ativo (
            ativo TEXT PRIMARY KEY, n INTEGER, ganhos_sinal INTEGER, ganhos_liq INTEGER,
            bps_sinal REAL, bps_exec REAL, bps_liq REAL, pnl_sinal REAL, pnl_exec REAL, pnl_liq REAL);
        """)
        for k, v in PADRAO.items():
            c.execute("INSERT OR IGNORE INTO micro_config VALUES (?, ?)", (k, v))


def get_config():
    with _con() as c:
        return {r["chave"]: r["valor"] for r in c.execute("SELECT * FROM micro_config")}


def _set(chave, valor):
    with _con() as c:
        c.execute("INSERT OR REPLACE INTO micro_config VALUES (?, ?)", (chave, str(valor)))


def validar(body):
    """Mesmo contrato do POST /config do bot: chave fora do catálogo, tipo errado ou valor
    fora de faixa levantam ValueError dizendo o que foi recusado, e nada é gravado."""
    if not isinstance(body, dict) or not body:
        raise ValueError("corpo vazio")
    aceitos = {}
    for k, v in body.items():
        if k == "ativos":
            lista = [a.strip().lower() for a in str(v).split(",") if a.strip()]
            ruins = [a for a in lista if not ATIVO_RE.match(a)]
            if not lista or ruins or len(lista) > MAX_ATIVOS:
                raise ValueError(f"ativos: lista de 1 a {MAX_ATIVOS} pares *usdt; recusados: {ruins}")
            aceitos[k] = ",".join(dict.fromkeys(lista))
            continue
        if k not in CATALOGO:
            raise ValueError(f"{k}: chave fora do catálogo")
        tipo, lo, hi = CATALOGO[k]
        try:
            x = float(v)
            if tipo is int:
                # int(2.5) devolve 2 sem reclamar: truncar em silêncio grava o que ninguém pediu
                if not x.is_integer():
                    raise ValueError
                x = int(x)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f"{k}: esperado {tipo.__name__}, veio {v!r}")
        if not (lo <= x <= hi) or (isinstance(x, float) and not math.isfinite(x)):
            raise ValueError(f"{k}: {x} fora da faixa [{lo}, {hi}]")
        aceitos[k] = str(x)
    return aceitos


# ---------------------------------------------------------------- agregados em memória

class _Agregado:
    """O que o /micro/estado devolve sem tocar no banco a cada poll. Carrega do banco ao
    nascer e depois soma o que o motor fecha."""

    def __init__(self):
        self.por_ativo = {}
        self.por_minuto = collections.OrderedDict()
        self.ultimos = collections.deque(maxlen=25)
        self.fechou_em = collections.deque()      # monotônico de cada fechamento, últimos 60 s

    def carregar(self):
        with _con() as c:
            for r in c.execute("SELECT * FROM micro_ativo"):
                self.por_ativo[r["ativo"]] = dict(r)
            for r in c.execute("SELECT * FROM micro_minuto ORDER BY minuto DESC LIMIT ?", (MINUTOS_CURVA,)):
                self.por_minuto[r["minuto"]] = dict(r)
            self.por_minuto = collections.OrderedDict(sorted(self.por_minuto.items()))
            for r in c.execute("SELECT * FROM micro_trades ORDER BY id DESC LIMIT 25"):
                self.ultimos.appendleft(dict(r))

    def somar(self, tr, t_mono):
        a = self.por_ativo.setdefault(tr["ativo"], {"ativo": tr["ativo"], "n": 0, "ganhos_sinal": 0,
                                                    "ganhos_liq": 0, "bps_sinal": 0.0, "bps_exec": 0.0,
                                                    "bps_liq": 0.0, "pnl_sinal": 0.0, "pnl_exec": 0.0,
                                                    "pnl_liq": 0.0})
        m = self.por_minuto.setdefault(tr["ts_fecha"][:16], {"minuto": tr["ts_fecha"][:16], "n": 0,
                                                             "ganhos_sinal": 0, "ganhos_liq": 0,
                                                             "sinal": 0.0, "exec": 0.0, "liq": 0.0})
        for d in (a, m):
            d["n"] += 1
            d["ganhos_sinal"] += tr["bps_sinal"] > 0
            d["ganhos_liq"] += tr["bps_liq"] > 0
        a["bps_sinal"] += tr["bps_sinal"]
        a["bps_exec"] += tr["bps_exec"]
        a["bps_liq"] += tr["bps_liq"]
        a["pnl_sinal"] += tr["pnl_sinal"]
        a["pnl_exec"] += tr["pnl_exec"]
        a["pnl_liq"] += tr["pnl_liq"]
        m["sinal"] += tr["pnl_sinal"]
        m["exec"] += tr["pnl_exec"]
        m["liq"] += tr["pnl_liq"]
        while len(self.por_minuto) > MINUTOS_CURVA:
            self.por_minuto.popitem(last=False)
        self.ultimos.appendleft(tr)
        self.fechou_em.append(t_mono)

    def taxa_min(self, agora):
        while self.fechou_em and agora - self.fechou_em[0] > 60:
            self.fechou_em.popleft()
        return len(self.fechou_em)


def _gravar(trades, agg):
    """Uma transação por lote (~2 s). Os agregados são reescritos do que está em memória:
    o mesmo dado que o painel mostra é o que fica no banco."""
    if not trades:
        return
    cols = ("ts_abre", "ts_fecha", "ativo", "lado", "px_ent", "px_sai", "mid_ent", "mid_sai",
            "bps_sinal", "bps_exec", "bps_liq", "pnl_liq", "z", "dur_ms", "motivo")
    ativos = {t["ativo"] for t in trades}
    minutos = {t["ts_fecha"][:16] for t in trades}
    with _con() as c:
        c.executemany(f"INSERT INTO micro_trades ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                      [tuple(t[k] for k in cols) for t in trades])
        for a in ativos:
            d = agg.por_ativo[a]
            c.execute("INSERT OR REPLACE INTO micro_ativo VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (a, d["n"], d["ganhos_sinal"], d["ganhos_liq"], d["bps_sinal"], d["bps_exec"],
                       d["bps_liq"], d["pnl_sinal"], d["pnl_exec"], d["pnl_liq"]))
        for m in minutos:
            d = agg.por_minuto.get(m)
            if d:
                c.execute("INSERT OR REPLACE INTO micro_minuto VALUES (?,?,?,?,?,?,?)",
                          (m, d["n"], d["ganhos_sinal"], d["ganhos_liq"], d["sinal"], d["exec"], d["liq"]))


def _podar():
    limite = (datetime.now().timestamp() - RETENCAO_DIAS * 86400)
    corte = datetime.fromtimestamp(limite).strftime("%Y-%m-%d %H:%M:%S")
    with _con() as c:
        return c.execute("DELETE FROM micro_trades WHERE ts_fecha < ?", (corte,)).rowcount


# ---------------------------------------------------------------- execução ao vivo

_lock = threading.RLock()
_st = {"thread": None, "parar": None, "motor": None, "agg": None, "conectado": False,
       "desde": None, "erro": None, "eventos": 0, "eventos_s": 0.0, "parado_por": None,
       "taxa": None, "ws": None, "fila_ms": 0.0, "atraso_min": float("inf")}


def _agg():
    if _st["agg"] is None:
        init()
        a = _Agregado()
        a.carregar()
        _st["agg"] = a
    return _st["agg"]


def _taxa_do_bot():
    try:
        return float(db.get_config().get("taxa_por_lado", "0.0005"))
    except Exception:
        return 0.0005


async def _relogio(parar):
    ult_grav = ult_eps = time.monotonic()
    ult_poda = 0.0
    ev0 = _st["eventos"]
    while not parar.is_set():
        await asyncio.sleep(0.1)
        t = time.monotonic()
        # Uma exceção aqui mataria a tarefa CALADA: o websocket seguiria "ao vivo" e nenhum
        # trade seria mais agregado nem gravado. Registra e segue no próximo tique.
        novos = []
        try:
            with _lock:
                m = _st["motor"]
                m.relogio(t)
                novos, m.fechados = m.fechados, []
                for tr in novos:
                    _st["agg"].somar(tr, t)
                if m.parado_por and not _st["parado_por"]:
                    _st["parado_por"] = m.parado_por
        except Exception as e:
            _st["erro"] = f"relógio: {type(e).__name__}: {e}"
            log(f"[micro] {_st['erro']}", "error")
        if novos:
            _st.setdefault("_buffer", []).extend(novos)
        if t - ult_eps >= 2:
            _st["eventos_s"] = (_st["eventos"] - ev0) / (t - ult_eps)
            ev0, ult_eps = _st["eventos"], t
        if t - ult_grav >= 2 and _st.get("_buffer"):
            # Sem o _lock: o agregado só é escrito por esta mesma thread, e segurar o lock
            # durante o I/O travaria o websocket, que precisa dele a cada evento.
            lote, _st["_buffer"] = _st["_buffer"], []
            try:
                _gravar(lote, _st["agg"])
            except Exception as e:
                log(f"[micro] gravação falhou ({len(lote)} trades): {e}", "error")
            ult_grav = t
        if t - ult_poda > 3600:
            ult_poda = t
            try:
                n = _podar()
                if n:
                    log(f"[micro] retenção: {n} trades com mais de {RETENCAO_DIAS} dias removidos")
            except Exception as e:
                log(f"[micro] poda falhou: {e}", "error")
        if _st["parado_por"]:
            log(f"[micro] parado sozinho: {_st['parado_por']}", "error")
            _set("ligado", "0")
            parar.set()
    ws = _st.get("ws")
    if ws is not None and not ws.closed:
        await ws.close()


async def _sessao(ativos, parar):
    import aiohttp      # vem com o ccxt (dependência dele); sem pacote novo na requirements
    url = WS_URL + "/".join(f"{a}@bookTicker" for a in ativos)
    relogio = asyncio.create_task(_relogio(parar))
    espera = 1
    while not parar.is_set():
        try:
            async with aiohttp.ClientSession() as cs:
                async with cs.ws_connect(url, heartbeat=20, receive_timeout=30) as ws:
                    _st["ws"], _st["conectado"], _st["erro"] = ws, True, None
                    espera = 1
                    log(f"[micro] conectado: {len(ativos)} ativos")
                    async for msg in ws:
                        if parar.is_set():
                            break
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
                            continue
                        d = json.loads(msg.data).get("data") or {}
                        try:
                            a, pb, qb, pa, qa = (d["s"].lower(), float(d["b"]), float(d["B"]),
                                                 float(d["a"]), float(d["A"]))
                        except (KeyError, ValueError, AttributeError):
                            continue
                        t = time.monotonic()
                        with _lock:
                            _st["motor"].livro(a, t, pb, qb, pa, qa)
                        _st["eventos"] += 1
                        # Fila = (relógio local − hora do evento na Binance) − o menor valor já
                        # visto. A diferença bruta carrega o erro do relógio desta máquina (13,8 s
                        # no Windows de desenvolvimento em 12/11); subtrair o mínimo tira o erro e
                        # a parte fixa da rede e deixa o que importa: se o motor está ficando para
                        # trás. Fila crescendo = a latência simulada deixou de ser a real.
                        if "E" in d:
                            atraso = time.time() * 1000 - d["E"]
                            if atraso < _st["atraso_min"]:
                                _st["atraso_min"] = atraso
                            _st["fila_ms"] += 0.01 * (atraso - _st["atraso_min"] - _st["fila_ms"])
                    log(f"[micro] websocket fechou: código {ws.close_code}, exceção {ws.exception()}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _st["erro"] = f"{type(e).__name__}: {e}"
            log(f"[micro] websocket caiu: {_st['erro']}", "error")
        _st["conectado"] = False
        if not parar.is_set():
            await asyncio.sleep(espera)
            espera = min(espera * 2, 30)
    await relogio


def _thread(ativos, parar):
    try:
        asyncio.run(_sessao(ativos, parar))
    except Exception as e:
        _st["erro"] = f"{type(e).__name__}: {e}"
        log(f"[micro] motor encerrou com erro: {_st['erro']}", "error")
    finally:
        _st["conectado"] = False
        buf = _st.pop("_buffer", None)
        if buf:
            try:
                with _lock:
                    _gravar(buf, _st["agg"])
            except Exception as e:
                log(f"[micro] gravação final falhou: {e}", "error")


def ligado():
    th = _st["thread"]
    return bool(th and th.is_alive())


def ligar():
    with _lock:
        if ligado():
            return estado()
        agg = _agg()
        cfg = get_config()
        pnl_base = sum(d["pnl_liq"] for d in agg.por_ativo.values())
        taxa = _taxa_do_bot()
        m = Motor(cfg, taxa, pnl_base)
        if m.banca <= m.piso:
            raise ValueError(f"banca {m.banca:.2f} já está no piso {m.piso:.2f}: zere o laboratório antes")
        parar = threading.Event()
        _st.update(motor=m, parar=parar, taxa=taxa, desde=_agora_txt()[:19], erro=None,
                   parado_por=None, eventos=0, eventos_s=0.0, fila_ms=0.0,
                   atraso_min=float("inf"))
        _set("ligado", "1")
        th = threading.Thread(target=_thread, args=(m.ativos, parar), daemon=True, name="micro")
        _st["thread"] = th
        th.start()
    log(f"[micro] ligado: {cfg['ativos']} | z {cfg['z_entrada']} | horizonte {cfg['horizonte_ms']} ms "
        f"| latência {cfg['latencia_ms']} ms | taxa {taxa}")
    return estado()


def desligar(persistir=True, esperar=5.0):
    th, parar = _st["thread"], _st["parar"]
    if persistir:
        init()
        _set("ligado", "0")
    if parar is not None:
        parar.set()
    if th is not None and th.is_alive():
        th.join(timeout=esperar)
    return estado()


def retomar():
    """Chamado no lifespan: volta a rodar se estava ligado quando o processo caiu. Diferente do
    `auto_trade`, aqui não há dinheiro, posição nem trava do bot em jogo -- é um laboratório."""
    try:
        init()
        if get_config().get("ligado") == "1":
            ligar()
    except Exception as e:
        log(f"[micro] não retomou: {e}", "error")


def set_config(body):
    aceitos = validar(body)
    rodando = ligado()
    if rodando:
        desligar(persistir=False)
    for k, v in aceitos.items():
        _set(k, v)
    if rodando:
        ligar()
    return estado()


def zerar():
    rodando = ligado()
    if rodando:
        desligar(persistir=False)
    init()
    with _lock:
        with _con() as c:
            c.execute("DELETE FROM micro_trades")
            c.execute("DELETE FROM micro_minuto")
            c.execute("DELETE FROM micro_ativo")
        _st["agg"] = None
        _st["parado_por"] = None
        _agg()
    log("[micro] laboratório zerado")
    if rodando:
        ligar()
    return estado()


def estado():
    with _lock:
        agg = _agg()
        cfg = get_config()
        m = _st["motor"] if ligado() else None
        t = time.monotonic()
        tot = {"n": 0, "ganhos_sinal": 0, "ganhos_liq": 0, "bps_sinal": 0.0, "bps_exec": 0.0,
               "bps_liq": 0.0, "pnl_sinal": 0.0, "pnl_exec": 0.0, "pnl_liq": 0.0}
        for d in agg.por_ativo.values():
            for k in tot:
                tot[k] += d[k]
        n = tot["n"] or 1
        taxa = _st["taxa"] if _st["taxa"] is not None else _taxa_do_bot()
        banca_ini = float(cfg["banca_inicial"])
        por_ativo = []
        for d in sorted(agg.por_ativo.values(), key=lambda d: -d["n"]):
            k = d["n"] or 1
            lv = m.livros.get(d["ativo"]) if m else None
            por_ativo.append({
                "ativo": d["ativo"], "n": d["n"], "acerto_sinal": d["ganhos_sinal"] / k,
                "acerto_liq": d["ganhos_liq"] / k, "bps_sinal": d["bps_sinal"] / k,
                "bps_exec": d["bps_exec"] / k, "bps_liq": d["bps_liq"] / k, "pnl_liq": d["pnl_liq"],
                "spread_bps": ((lv.pa - lv.pb) / lv.meio * 1e4) if lv and lv.pb else None,
                "z": round(lv.z, 2) if lv else None})
        curva = {"t": [], "sinal": [], "exec": [], "liq": []}
        acc = [0.0, 0.0, 0.0]
        for mi, d in agg.por_minuto.items():
            acc = [acc[0] + d["sinal"], acc[1] + d["exec"], acc[2] + d["liq"]]
            curva["t"].append(mi[11:16])
            for i, k in enumerate(("sinal", "exec", "liq")):
                curva[k].append(round(acc[i], 2))
        ultimos = [[u["ts_fecha"][11:23], u["ativo"], u["lado"], u["dur_ms"], round(u["bps_sinal"], 2),
                    round(u["bps_exec"], 2), round(u["bps_liq"], 2), u["motivo"]] for u in agg.ultimos]
        return {
            "ligado": m is not None, "conectado": _st["conectado"] and m is not None,
            "desde": _st["desde"] if m else None, "erro": _st["erro"], "parado_por": _st["parado_por"],
            "eventos_s": round(_st["eventos_s"], 1) if m else 0.0,
            "fila_ms": round(_st["fila_ms"]) if m else None,
            "abertas": (len(m.posicoes) + len(m.ordens)) if m else 0,
            "trades_min": agg.taxa_min(t),
            "cfg": {k: v for k, v in cfg.items() if k != "ligado"},
            "taxa_lado_bps": round(taxa * 1e4, 2),
            "banca_inicial": banca_ini, "banca": round(banca_ini + tot["pnl_liq"], 2),
            "n": tot["n"], "acerto_sinal": tot["ganhos_sinal"] / n, "acerto_liq": tot["ganhos_liq"] / n,
            "media_bps": {"sinal": tot["bps_sinal"] / n, "exec": tot["bps_exec"] / n,
                          "liq": tot["bps_liq"] / n},
            "pnl": {"sinal": round(tot["pnl_sinal"], 2), "exec": round(tot["pnl_exec"], 2),
                    "liq": round(tot["pnl_liq"], 2)},
            "curva": curva, "por_ativo": por_ativo, "ultimos": ultimos,
        }
