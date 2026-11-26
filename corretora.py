"""[LIVE-1] A corretora: quem EXECUTA e INFORMA. O `simulador` continua sendo o livro-razão.

Fase 1 do `PLANO-LIVE-BINANCE`. Duas implementações atrás da mesma interface:

- `Papel`: o comportamento de hoje. Fill no preço ao vivo, stop e TP como ids sintéticos (quem
  dispara o stop no papel continua sendo o `simulador._marcar_uma`).
- `BinanceUSDM`: ordens reais na Binance USDⓈ-M Futures por ccxt, no ambiente DEMO (dinheiro
  fictício, `demo-fapi.binance.com`) ou no real.

Este módulo ainda NÃO é chamado pelo `simulador`: ligar os dois é a Fase 3. Por isso a config
`corretora` nasce `papel`, e nenhum caminho de hoje muda.

**As regras que este arquivo segura, e o que as provou** (demo, 16/11/2026, ordens reais com
dinheiro fictício; os testes em `tests/test_corretora.py` reproduzem cada uma com um dublê):

1. **O que protege a posição mora na corretora.** O dono exigiu: o dl380 desliga ~20h e volta
   ~8h, então SL e TP têm de existir NA BINANCE, não num poll em Python. `colocar_stop`,
   `colocar_tp` e `colocar_trailing` existem para isso.
2. **SL antes do fill precisa de quantidade.** `closePosition=true` sem posição aberta é recusado
   pela Binance (`-4509`); `reduceOnly` com quantidade é aceito. É o que deixa uma entrada
   post-only protegida mesmo se ela encher de madrugada com o servidor desligado. Com posição
   aberta, `closePosition` é melhor: some sozinho quando a posição fecha.
   Só pode haver UM `closePosition` por direção (`-4130`): por isso `mover_stop` troca para
   `reduceOnly` com quantidade.
3. **Condicional órfã fica viva.** Fechada a posição, o SL `closePosition` sumiu sozinho, mas o TP
   `reduceOnly` com quantidade CONTINUOU aberto. Numa posição nova no mesmo símbolo ele fecharia
   parte dela no preço antigo. `ordens_abertas` devolve as condicionais junto com as normais
   para que a reconciliação (Fase 5) as veja e cancele.
4. **Condicional mora em outro serviço da Binance ("Algo").** Não aparece na lista normal de
   ordens abertas; o status vem em `algoStatus`. E a LEITURA atrasa: cancelada uma condicional,
   a Binance confirma na hora, mas consultas feitas logo depois ainda dizem `NEW` por ~1,5 s
   (demo, 16/11, três leituras seguidas: NEW, CANCELED, CANCELED). A reconciliação (Fase 5) não
   pode agir sobre leitura feita no mesmo instante de uma escrita nossa.
5. **Todo envio leva um id nosso (`client_oid`).** Repetir o id dá `-4116` (normal) ou
   `-20132` (condicional, serviço Algo) e a ordem é achada por ele. Timeout de rede no envio é o caso clássico de abrir duas vezes: aqui ele vira uma
   BUSCA pelo id, nunca um reenvio cego. Se a busca não acha, levanta `EnvioIncerto` e quem
   chamou decide (a reconciliação resolve no ciclo seguinte).
6. **O relógio é o da Binance.** O PC do dono estava 18,7 s atrasado e a Binance recusou tudo
   (`-1021`, janela de 5 s). O adapter mede a diferença no início, de hora em hora, e de novo
   na hora a cada `-1021` (que é recusa certa: a chamada é repetida uma vez).
9. **Recusa da chave e limite de taxa não são "rede".** O ccxt põe o `-2015` (chave, IP ou
   permissão) e o 418/429 em `DDoSProtection`, que é filho de `NetworkError`: sem tradução, um
   IP de saída que mudou aparecia como envio incerto. Todo acesso ao ccxt passa por
   `_Cliente`, que os traduz (`ChaveRecusada`, `LimiteDeTaxa`) e, no limite de taxa, PARA de
   chamar até o `Retry-After`: insistir durante um ban de IP faz a Binance aumentá-lo.
7. **Teto de nocional por ordem**, última linha antes da corretora: um bug de dimensionamento
   vira recusa, não ordem (`PLANO-LIVE` Fase 6). E `dry_run`: monta a ordem inteira, já
   arredondada, e não manda.
8. **Chave real perigosa não ABRE nada.** No modo `binance` o adapter pergunta à Binance o que
   a chave pode fazer; com saque habilitado, transferência habilitada, sem restrição de IP, ou
   sem dar para conferir, toda ENTRADA é recusada (`bloqueio_entrada`). Fechar, stop e pânico
   seguem: recusar subir, como era, deixava a posição que já existe sem ninguém para fechá-la,
   justamente no dia em que algo está errado. Não há bandeira para desligar: é a lógica do
   `DASH_PASS` (CLAUDE.md §2).

Fronteiras que só este módulo atravessa: o símbolo (`BTC/USDT` no sistema, `BTC/USDT:USDT` na
perp) e o tempo (ms UTC na corretora, `pd.Timestamp` naive em hora de São Paulo no resto —
CLAUDE.md §1).
"""
import os
import threading
import time

import pandas as pd

from logbot import log

# ------------------------------------------------------------------------------ erros

class ErroCorretora(Exception):
    """Falha da corretora que o chamador precisa tratar."""


class OrdemRecusada(ErroCorretora):
    """A corretora recusou a ordem (post-only que cruzaria o livro, parâmetro inválido)."""


class EnvioIncerto(ErroCorretora):
    """A rede falhou no envio e a ordem NÃO foi achada pelo `client_oid`. Pode ter chegado ou não:
    quem resolve é a reconciliação, que procura de novo pelo mesmo id. Não reenvie às cegas."""


class AbaixoDoMinimo(ErroCorretora):
    """Quantidade abaixo do lote mínimo ou nocional abaixo do mínimo do símbolo. Recusa; nunca
    arredonda para cima (arredondar para cima é risco que o teto não mediu)."""


class AcimaDoTeto(ErroCorretora):
    """Nocional da ordem acima de `corretora_nocional_max`."""


class ChaveInsegura(ErroCorretora):
    """A chave real pode sacar, transferir, ou não está presa a um IP."""


class ChaveRecusada(OrdemRecusada):
    """A Binance recusou a CHAVE (`-2015`/`-2014`: chave, IP ou permissão). Nada foi executado.
    O caso real é o IP de saída do servidor que mudou: a chave presa a IP para de valer para
    tudo, inclusive para o pânico, e só o aplicativo da Binance consegue agir."""


class LimiteDeTaxa(OrdemRecusada):
    """Limite de requisições (429, `-1003`, `-1015`) ou IP banido (418). A requisição foi recusada
    antes de executar, e até o fim da pausa nenhuma outra sai (`_Cliente`)."""


# ------------------------------------------------------------------------------ fronteiras

DIRECOES = ("LONG", "SHORT")
_ABRE = {"LONG": "buy", "SHORT": "sell"}
_FECHA = {"LONG": "sell", "SHORT": "buy"}
FUSO = "America/Sao_Paulo"


def perp(simbolo):
    """`BTC/USDT` -> `BTC/USDT:USDT`. Idempotente."""
    return simbolo if ":" in simbolo else f"{simbolo}:{simbolo.split('/')[1]}"


def base(simbolo):
    """`BTC/USDT:USDT` -> `BTC/USDT`. Idempotente."""
    return simbolo.split(":")[0]


def ms_para_sp(ms):
    """ms UTC da corretora -> `pd.Timestamp` naive em hora de São Paulo (convenção do banco)."""
    if ms is None:
        return None
    return pd.Timestamp(int(ms), unit="ms", tz="UTC").tz_convert(FUSO).tz_localize(None)


def sp_para_ms(ts):
    """`pd.Timestamp` naive em hora de São Paulo (o banco) -> ms UTC (a corretora). A volta do
    `ms_para_sp`, com o fuso ESCRITO: não depende do fuso da máquina onde o processo roda."""
    if ts is None:
        return None
    return int(pd.Timestamp(ts).tz_localize(FUSO).timestamp() * 1000)


def _direcao(d):
    d = str(d).upper()
    if d not in DIRECOES:
        raise ValueError(f"direção inválida: {d!r}")
    return d


# status cru da Binance -> o nosso. Normais em `status`, condicionais (Algo) em `algoStatus`.
_STATUS = {
    "NEW": "aberta", "ACCEPTED": "aberta", "PARTIALLY_FILLED": "parcial",
    "FILLED": "preenchida", "FINISHED": "preenchida",
    "TRIGGERING": "disparada", "TRIGGERED": "disparada",
    "CANCELED": "cancelada", "CANCELLED": "cancelada",
    "EXPIRED": "expirada", "EXPIRED_IN_MATCH": "expirada", "REJECTED": "rejeitada",
}


def _f(x):
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def normalizar_ordem(o):
    """Ordem do ccxt -> dicionário nosso. O status vem do dado CRU (regra 4 do módulo)."""
    info = o.get("info") or {}
    condicional = "algoId" in info or "algoStatus" in info
    cru = info.get("algoStatus") if condicional else info.get("status")
    status = _STATUS.get(str(cru or "").upper()) or {
        "open": "aberta", "closed": "preenchida", "canceled": "cancelada",
        "expired": "expirada", "rejected": "rejeitada"}.get(o.get("status"), o.get("status"))
    preenchido = _f(o.get("filled")) or _f(info.get("executedQty")) or 0.0
    if condicional and str(cru or "").upper() == "FINISHED" and _f(info.get("actualQty")) is not None:
        # `FINISHED` é "preenchida OU cancelada no motor de casamento" (doc do Algo). Quem diz
        # qual das duas é a quantidade da ordem filha: com zero, ela não executou nada. Sem o
        # campo fica o de antes (preenchida), e quem decide o que houve são os negócios lidos.
        preenchido = _f(info.get("actualQty"))
        status = "preenchida" if preenchido > 0 else "cancelada"
    return {
        "id": str(o.get("id")) if o.get("id") is not None else None,
        "client_oid": o.get("clientOrderId") or info.get("clientAlgoId") or info.get("clientOrderId"),
        "simbolo": base(o["symbol"]) if o.get("symbol") else None,
        "lado": o.get("side"),
        "tipo": str(info.get("orderType") or info.get("type") or o.get("type") or "").upper(),
        "condicional": condicional,
        "status": status,
        "qty": _f(o.get("amount")) if o.get("amount") is not None else _f(info.get("quantity") or info.get("origQty")),
        "preenchido": preenchido,
        "preco": _f(o.get("price")),
        "preco_medio": _f(o.get("average")) or _f(info.get("avgPrice")) or None,
        "gatilho": (_f(o.get("stopPrice")) or _f(info.get("triggerPrice")) or _f(info.get("stopPrice"))
                    or _f(info.get("activatePrice"))),      # trailing: a Binance chama de activatePrice
        "ativacao": _f(info.get("activatePrice")),              # o que a Binance GRAVOU
        "reduce_only": bool(o.get("reduceOnly") or info.get("reduceOnly")),
        "close_position": str(info.get("closePosition")).lower() == "true",
        "ts": ms_para_sp(o.get("timestamp") or info.get("updateTime") or info.get("createTime")),
    }


# ------------------------------------------------------------------------------ papel

class Papel:
    """O comportamento de hoje atrás da interface. Fill no preço ao vivo (injetado, para não
    importar o `simulador` e criar ciclo); stop/TP/trailing devolvem id sintético e não fazem
    nada, porque no papel quem dispara é o `simulador._marcar_uma`."""

    nome = "papel"
    real = False

    def __init__(self, preco_fn, saldo_fn=None):
        self._preco = preco_fn
        self._saldo = saldo_fn
        self._seq = 0
        self._lock = threading.Lock()

    def _id(self, prefixo):
        with self._lock:
            self._seq += 1
            return f"papel-{prefixo}-{self._seq}"

    def _sintetica(self, prefixo, simbolo, lado, tipo, qty, client_oid, status="aberta", **kw):
        return {"id": self._id(prefixo), "client_oid": client_oid, "simbolo": base(simbolo),
                "lado": lado, "tipo": tipo, "condicional": tipo not in ("LIMIT", "MARKET"),
                "status": status, "qty": qty, "preenchido": 0.0, "preco": None,
                "preco_medio": None, "gatilho": None, "reduce_only": False,
                "close_position": False, "ts": pd.Timestamp.now(), **kw}

    def saldo(self):
        s = self._saldo() if self._saldo else None
        return {"livre": s, "total": s, "unrealized": 0.0, "carteira": s, "equity": s}

    def hedge(self):
        return False

    def multi_ativos(self):
        return False

    def posicoes(self):
        return []                       # no papel a posição é a linha do banco

    def ordens_abertas(self, simbolo=None):
        return []

    def marks(self, simbolos):
        return {s: self._preco(base(s)) for s in simbolos}

    def preparar_simbolo(self, simbolo, alavancagem):
        return None

    def arredondar(self, simbolo, qty, preco=None, reduz=False):
        return qty, preco

    def preco_valido(self, simbolo, preco):
        return preco

    def abrir_mercado(self, simbolo, direcao, qty, client_oid):
        px = self._preco(base(simbolo))
        o = self._sintetica("ent", simbolo, _ABRE[_direcao(direcao)], "MARKET", qty, client_oid,
                            status="preenchida")
        o.update(preenchido=qty, preco_medio=px)
        return o

    def fechar_mercado(self, simbolo, direcao, qty, client_oid):
        px = self._preco(base(simbolo))
        o = self._sintetica("fec", simbolo, _FECHA[_direcao(direcao)], "MARKET", qty, client_oid,
                            status="preenchida", reduce_only=True)
        o.update(preenchido=qty, preco_medio=px)
        return o

    def colocar_limite_post_only(self, simbolo, direcao, qty, preco, client_oid):
        o = self._sintetica("lim", simbolo, _ABRE[_direcao(direcao)], "LIMIT", qty, client_oid)
        o["preco"] = preco
        return o

    def colocar_stop(self, simbolo, direcao, gatilho, client_oid, qty=None):
        o = self._sintetica("sl", simbolo, _FECHA[_direcao(direcao)], "STOP_MARKET", qty, client_oid,
                            reduce_only=True, close_position=qty is None)
        o["gatilho"] = gatilho
        return o

    def colocar_tp(self, simbolo, direcao, gatilho, qty, client_oid):
        o = self._sintetica("tp", simbolo, _FECHA[_direcao(direcao)], "TAKE_PROFIT_MARKET", qty,
                            client_oid, reduce_only=True)
        o["gatilho"] = gatilho
        return o

    def colocar_trailing(self, simbolo, direcao, qty, ativacao, callback_pct, client_oid):
        o = self._sintetica("tr", simbolo, _FECHA[_direcao(direcao)], "TRAILING_STOP_MARKET", qty,
                            client_oid, reduce_only=True)
        o["gatilho"] = ativacao
        return o

    def mover_stop(self, simbolo, ordem, novo_gatilho, novo_client_oid, qty=None):
        return self.colocar_stop(simbolo, "LONG" if ordem.get("lado") == "sell" else "SHORT",
                                 novo_gatilho, novo_client_oid, qty=qty or ordem.get("qty"))

    def cancelar(self, simbolo, ordem_id, condicional=False):
        return True

    def cancelar_tudo(self, simbolo):
        return 0

    def buscar(self, simbolo, client_oid, condicional=False):
        return None

    def buscar_por_id(self, simbolo, ordem_id):
        return None

    def fills(self, simbolo, desde_ms=None):
        return []

    def income(self, simbolo=None, desde_ms=None, tipo=None):
        return []

    def verificar_chave(self):
        return {"verificavel": False, "motivo": "papel"}


# ------------------------------------------------------------------------------ binance

import re as _re

# Métodos do ccxt que não vão à rede: valem durante a pausa por limite de taxa.
_LOCAIS = frozenset({"market", "amount_to_precision", "price_to_precision", "cost_to_precision"})


_SEGREDOS = (
    (_re.compile(r"(signature=)[0-9a-fA-F]+"), r"\1***"),         # HMAC da requisição, na URL
    (_re.compile(r"(request ip:\s*)[0-9a-fA-F.:]+"), r"\1***"),   # o IP de saída, no -2015
)


def limpo(texto):
    """A mensagem de erro sem o que não pode ir para log, `/status` e resposta HTTP: o ccxt
    escreve a URL assinada inteira no erro de rede, e a Binance devolve o IP de saída do
    servidor no -2015 (o repositório é público e o log circula em relato)."""
    t = str(texto)
    for padrao, troca in _SEGREDOS:
        t = padrao.sub(troca, t)
    return t


def _codigo(e, *codigos):
    """O erro traz algum destes códigos da Binance? Por texto, com fronteira: o ccxt muda a
    CLASSE de um código conforme a tabela e o momento (o `-2015` é `AuthenticationError` na
    primeira chamada e `DDoSProtection` depois), mas o corpo cru vai sempre na mensagem."""
    txt = str(e)
    return any(_re.search(_re.escape(c) + r"(?!\d)", txt) for c in codigos)


class _Cliente:
    """O cliente ccxt com a regra 9 do módulo: TODA chamada à Binance passa por aqui, inclusive
    leitura, busca depois de timeout e o pânico. Traduzir só no `_enviar` deixaria a
    reconciliação dizendo "rede" para uma chave que deixou de valer."""

    def __init__(self, ex, dono):
        object.__setattr__(self, "_ex", ex)
        object.__setattr__(self, "_dono", dono)

    def __getattr__(self, nome):
        alvo = getattr(self._ex, nome)
        if not callable(alvo):
            return alvo
        return lambda *a, **k: self._dono._chamar(nome, alvo, a, k)

    def __setattr__(self, nome, valor):         # dublê de teste trocando um método: vale no ccxt
        setattr(self._ex, nome, valor)


class BinanceUSDM:
    """Ordens reais (demo ou real) na Binance USDⓈ-M, modo one-way, margem isolada.

    `ex` é o cliente ccxt já autenticado: injetado, para os testes trocarem por um dublê."""

    real = True
    RESYNC_RELOGIO_S = 3600
    RECARGA_MERCADOS_S = 86400          # tick e lote mudam com o processo de pé; o dl380 religa de manhã, mas não é garantia
    PAUSA_PADRAO_S = 60.0               # limite de taxa sem `Retry-After`

    def __init__(self, ex, modo, nocional_max, dry_run=False):
        if modo not in ("demo", "binance"):
            raise ValueError(f"modo inválido: {modo!r}")
        if not nocional_max or float(nocional_max) <= 0:
            raise ValueError("nocional_max é obrigatório e positivo: sem teto, sem ordem")
        self._pausa_ate = 0.0           # monotonic: até quando nada vai à Binance (limite de taxa)
        self.bloqueio_entrada = None    # regra 8: o motivo de não ABRIR nada, ou None
        self.chave_conferida_em = None  # monotonic da última conferência da chave
        self._mercados_em = time.monotonic()      # a fábrica já carregou
        self.ex = _Cliente(ex, self)
        self.nome = modo
        self.nocional_max = float(nocional_max)
        self.dry_run = bool(dry_run)
        self._preparados = {}           # simbolo -> alavancagem já aplicada
        self._relogio_em = 0.0
        self._lock = threading.Lock()
        opts = getattr(ex, "options", None)
        if isinstance(opts, dict):
            opts["adjustForTimeDifference"] = True
            opts["warnOnFetchOpenOrdersWithoutSymbol"] = False
        self._sincronizar_relogio(forcar=True)

    # -------------------------------------------------------------- infraestrutura

    def _sincronizar_relogio(self, forcar=False):
        agora = time.monotonic()
        if not forcar and agora - self._relogio_em < self.RESYNC_RELOGIO_S:
            return
        try:
            self.ex.load_time_difference()
            self._relogio_em = agora
        except Exception as e:      # sem relógio a próxima ordem falha com -1021 e diz por quê
            log(f"corretora: não sincronizou o relógio com a Binance ({e})", "warning")

    def _chamar(self, nome, fn, a, k):
        """Regra 9. `-2015` vira `ChaveRecusada`; `-1021` ressincroniza o relógio e repete UMA
        vez (é recusa certa: nada foi executado, e o id repetido ainda cairia na busca); 418,
        429, `-1003` e `-1015` param tudo até o `Retry-After`."""
        import ccxt
        if nome not in _LOCAIS:
            falta = self._pausa_ate - time.monotonic()
            if falta > 0:
                raise LimiteDeTaxa(f"Binance em pausa por limite de requisições por mais {falta:.0f}s; "
                                   f"{nome} não foi enviado")
        for tentativa in (1, 2):
            try:
                return fn(*a, **k)
            except ccxt.BaseError as e:
                if e.args:                      # limpa NA ORIGEM: todo log/HTTP depois herda
                    e.args = (limpo(e.args[0]),) + tuple(e.args[1:])
                if _codigo(e, "-2015", "-2014"):
                    raise ChaveRecusada(
                        "a Binance recusou a chave (IP, chave ou permissão). Se o IP de saída do "
                        f"servidor mudou, só o aplicativo da Binance age agora: {str(e)[:160]}") from e
                if isinstance(e, ccxt.InvalidNonce) or _codigo(e, "-1021"):
                    if tentativa == 1:
                        log(f"corretora: relógio fora da janela em {nome}; ressincronizando e "
                            "repetindo uma vez", "warning")
                        self._sincronizar_relogio(forcar=True)
                        continue
                    raise OrdemRecusada(f"relógio fora da janela da Binance mesmo depois de "
                                        f"ressincronizar: {str(e)[:160]}") from e
                if (isinstance(e, (ccxt.DDoSProtection, ccxt.RateLimitExceeded))
                        or _codigo(e, "-1003", "-1015")):
                    pausa = self._pausar()
                    raise LimiteDeTaxa(f"limite de requisições da Binance; nada sai pelos próximos "
                                       f"{pausa:.0f}s: {str(e)[:160]}") from e
                raise

    def _pausar(self):
        """Pausa global pelo `Retry-After` da resposta (segundos), ou `PAUSA_PADRAO_S`."""
        cab = getattr(self.ex._ex, "last_response_headers", None) or {}
        pausa = None
        try:
            for k, v in dict(cab).items():
                if str(k).lower() == "retry-after":
                    pausa = float(v)
        except (TypeError, ValueError):
            pausa = None
        pausa = pausa if pausa and pausa > 0 else self.PAUSA_PADRAO_S
        self._pausa_ate = max(self._pausa_ate, time.monotonic() + pausa)
        log(f"corretora: limite de requisições da Binance; pausa de {pausa:.0f}s", "error")
        return pausa

    def _recarregar_mercados(self):
        """Tick e lote podem mudar com o processo de pé; com os de ontem, o stop seria recusado
        por precisão duas vezes e a posição fechada a mercado. Uma vez por dia, sem derrubar."""
        if time.monotonic() - self._mercados_em < self.RECARGA_MERCADOS_S:
            return
        try:
            self.ex.load_markets(True)
            self._mercados_em = time.monotonic()
        except Exception as e:
            log(f"corretora: não recarregou os mercados ({type(e).__name__}: {e})", "warning")

    def _mercado(self, simbolo):
        return self.ex.market(perp(simbolo))

    def _mark(self, simbolo):
        return self.marks([simbolo])[base(simbolo)]

    # -------------------------------------------------------------- leitura

    def saldo(self):
        """`carteira` é o saldo sem o não realizado e `equity` é com ele, lidos dos campos da
        própria Binance (`totalWalletBalance`, `totalMarginBalance`). O `total` do ccxt fica por
        compatibilidade e NÃO se soma ao `unrealized`: conforme a versão ele já o inclui."""
        b = self.ex.fetch_balance()
        u = b.get("USDT") or {}
        info = b.get("info") or {}
        unreal = _f(info.get("totalUnrealizedProfit")) or 0.0
        carteira = _f(info.get("totalWalletBalance"))
        equity = _f(info.get("totalMarginBalance"))
        if equity is None and carteira is not None:
            equity = carteira + unreal
        return {"livre": _f(u.get("free")), "total": _f(u.get("total")), "unrealized": unreal,
                "carteira": carteira if carteira is not None else _f(u.get("total")),
                "equity": equity}

    def hedge(self):
        """True se a conta está em Hedge Mode (posição nos dois lados), False em One-way, None
        se não deu para ler. Este adapter só opera One-way: não manda `positionSide`."""
        try:
            r = self.ex.fapiPrivateGetPositionSideDual()
            return str(r.get("dualSidePosition")).lower() == "true"
        except Exception as e:
            log(f"corretora: modo de posição não lido ({type(e).__name__}: {e})", "warning")
            return None

    def multi_ativos(self):
        """True se a conta está em Multi-Assets, False se não, None se não deu para ler. Em
        Multi-Assets a Binance recusa margem isolada (`-4168`): toda entrada sairia rejeitada
        no preparo, depois de o sinal estar consumido."""
        try:
            r = self.ex.fapiPrivateGetMultiAssetsMargin()
            return str(r.get("multiAssetsMargin")).lower() == "true"
        except Exception as e:
            log(f"corretora: modo Multi-Assets não lido ({type(e).__name__}: {e})", "warning")
            return None

    def posicoes(self):
        out = []
        for p in self.ex.fetch_positions():
            qty = _f(p.get("contracts")) or 0.0
            if not qty:
                continue
            out.append({
                "simbolo": base(p["symbol"]),
                "direcao": "LONG" if p.get("side") == "long" else "SHORT",
                "qty": abs(qty),
                "entrada": _f(p.get("entryPrice")),
                "mark": _f(p.get("markPrice")),
                "liq": _f(p.get("liquidationPrice")),
                "margem": _f(p.get("initialMargin")) or _f(p.get("collateral")),
                "margem_modo": p.get("marginMode"),
                "alavancagem": _f(p.get("leverage")),
                "unrealized": _f(p.get("unrealizedPnl")) or 0.0,
            })
        return out

    def ordens_abertas(self, simbolo=None):
        """Normais E condicionais (regra 3): a reconciliação precisa ver as duas."""
        s = perp(simbolo) if simbolo else None
        normais = self.ex.fetch_open_orders(s)
        condicionais = self.ex.fetch_open_orders(s, params={"trigger": True})
        vistas, out = set(), []
        for o in list(normais) + list(condicionais):
            n = normalizar_ordem(o)
            if n["id"] in vistas:
                continue
            vistas.add(n["id"])
            out.append(n)
        return out

    def marks(self, simbolos):
        r = self.ex.fetch_mark_prices([perp(s) for s in simbolos])
        out = {}
        for k, v in r.items():
            out[base(k)] = _f(v.get("markPrice")) or _f((v.get("info") or {}).get("markPrice"))
        return out

    def buscar(self, simbolo, client_oid, condicional=False):
        """A ordem com este `client_oid`, ou None se a corretora não a conhece."""
        import ccxt
        params = ({"trigger": True, "clientAlgoId": client_oid} if condicional
                  else {"origClientOrderId": client_oid})
        try:
            return normalizar_ordem(self.ex.fetch_order(None, perp(simbolo), params))
        except ccxt.OrderNotFound:
            return None

    def buscar_por_id(self, simbolo, ordem_id):
        """A ordem NORMAL com este id da corretora, ou None. É como se descobre de quem foi um
        fechamento que o bot não mandou: a liquidação chega com `client_oid` começando em
        `autoclose-`, e a redução forçada (ADL) em `adl_autoclose`."""
        import ccxt
        try:
            return normalizar_ordem(self.ex.fetch_order(str(ordem_id), perp(simbolo)))
        except ccxt.OrderNotFound:
            return None

    def fills(self, simbolo, desde_ms=None):
        out = []
        for t in self.ex.fetch_my_trades(perp(simbolo), since=desde_ms):
            fee = t.get("fee") or {}
            info = t.get("info") or {}
            out.append({"id": str(t.get("id")), "ordem_id": str(t.get("order")),
                        "simbolo": base(t["symbol"]), "lado": t.get("side"),
                        "qty": _f(t.get("amount")), "preco": _f(t.get("price")),
                        "taxa": _f(fee.get("cost")) or 0.0, "taxa_moeda": fee.get("currency"),
                        "maker": str(info.get("maker")).lower() == "true",
                        "pnl_realizado": _f(info.get("realizedPnl")),
                        "ts": ms_para_sp(t.get("timestamp"))})
        return out

    JANELA_INCOME_MS = 7 * 86400 * 1000 - 1     # a Binance não garante mais que isso por chamada
    HISTORICO_INCOME_MS = 90 * 86400 * 1000     # e só guarda três meses

    def income(self, simbolo=None, desde_ms=None, tipo=None):
        """Taxa, funding e P&L realizados como a Binance os lançou (não como o modelo calcula).

        Em janelas de 7 dias com `endTime`, como os negócios (`execucao.JANELA_FILLS`): só com
        `startTime`, uma posição de swing com mais de uma semana tinha o funding cortado sem
        aviso. `tipo` filtra lá (`FUNDING_FEE`), para o limite de 1000 linhas ser de funding."""
        agora = int(time.time() * 1000)
        base_p = {"limit": 1000}
        if simbolo:
            base_p["symbol"] = self._mercado(simbolo)["id"]
        if tipo:
            base_p["incomeType"] = tipo
        if not desde_ms:
            janelas = [None]
        else:
            ini = max(int(desde_ms), agora - self.HISTORICO_INCOME_MS)
            janelas = []
            while ini <= agora:
                janelas.append((ini, min(ini + self.JANELA_INCOME_MS, agora)))
                ini += self.JANELA_INCOME_MS + 1
        out, vistos = [], set()
        for jan in janelas:
            params = dict(base_p)
            if jan:
                params["startTime"], params["endTime"] = jan
            for _ in range(50):                     # paginação por tempo dentro da janela
                lote = self.ex.fapiPrivateGetIncome(params) or []
                for i in lote:
                    chave = (i.get("tranId"), i.get("incomeType"), i.get("time"), i.get("income"))
                    if chave in vistos:
                        continue
                    vistos.add(chave)
                    out.append({"tipo": i.get("incomeType"), "valor": _f(i.get("income")),
                                "moeda": i.get("asset"), "simbolo": i.get("symbol"),
                                "ts": ms_para_sp(i.get("time"))})
                if len(lote) < 1000 or not jan:
                    break
                params["startTime"] = int(max(int(x.get("time") or 0) for x in lote))
        return out

    def verificar_chave(self):
        """Regra 8. No demo o endpoint não existe: devolve `verificavel=False` e segue."""
        if self.nome == "demo":
            return {"verificavel": False, "motivo": "demo: a Binance não expõe as restrições"}
        r = self.ex.sapiGetAccountApiRestrictions()
        sim = lambda k: str(r.get(k)).lower() == "true"
        problemas = []
        if sim("enableWithdrawals"):
            problemas.append("saque habilitado")
        if sim("enableInternalTransfer") or sim("permitsUniversalTransfer"):
            problemas.append("transferência habilitada")
        if not sim("ipRestrict"):
            problemas.append("sem restrição de IP")
        if not sim("enableFutures"):
            problemas.append("futuros desabilitado")
        # O que o bot não usa não fica ligado: chave que vaza com spot, margem ou opções
        # habilitados opera fora dos tetos que o livro conhece.
        extras = [n for k, n in (("enableSpotAndMarginTrading", "spot e margem"),
                                 ("enableMargin", "margem"),
                                 ("enablePortfolioMarginTrading", "portfolio margin"),
                                 ("enableVanillaOptions", "opções")) if sim(k)]
        if extras:
            problemas.append("habilitado sem uso pelo bot: " + ", ".join(extras))
        if problemas:
            raise ChaveInsegura("chave recusada: " + ", ".join(problemas))
        return {"verificavel": True, "ok": True}

    def conferir_chave(self):
        """Regra 8 sem travar o fechamento: confere e guarda o motivo de não abrir (None = pode).
        Falha de rede na conferência também bloqueia a entrada, e quem chama tenta de novo."""
        self.chave_conferida_em = time.monotonic()
        try:
            self.verificar_chave()
            self.bloqueio_entrada = None
        except ChaveInsegura as e:
            self.bloqueio_entrada = str(e)
        except Exception as e:
            self.bloqueio_entrada = (f"a chave não foi conferida ({type(e).__name__}: "
                                     f"{limpo(e)[:100]})")
        if self.bloqueio_entrada:
            log(f"corretora: entradas bloqueadas: {self.bloqueio_entrada}", "error")
        return self.bloqueio_entrada

    # -------------------------------------------------------------- preparação

    def preparar_simbolo(self, simbolo, alavancagem):
        """Margem isolada + alavancagem, uma vez por valor. Isolada para uma posição ruim não
        comer a margem das outras (o plano deixa cross fora, de propósito)."""
        import ccxt
        s = perp(simbolo)
        lev = int(alavancagem)
        with self._lock:
            if self._preparados.get(s) == lev:
                return lev
        if self.dry_run:
            log(f"corretora[dry_run]: prepararia {s} isolada {lev}x")
            return lev
        try:
            self.ex.set_margin_mode("isolated", s)
        except ccxt.ExchangeError as e:
            if "-4046" not in str(e) and "No need to change" not in str(e):
                raise
        self.ex.set_leverage(lev, s)
        with self._lock:
            self._preparados[s] = lev
        return lev

    def preco_valido(self, simbolo, preco):
        """O preço no passo que a corretora aceita. O livro grava ESTE número como stop, para
        que o gatilho do banco e o da corretora sejam o mesmo."""
        return float(self.ex.price_to_precision(perp(simbolo), preco))

    def _lote(self, simbolo, qty):
        """`qty` truncada para o lote do símbolo, sem perder um lote para o ponto flutuante.

        O ccxt trunca pelo texto do número: `0.062 - 0.021` é `0.040999999999999995` e sairia
        `0.040`, um lote a menos. Num stop ou num fechamento, esse lote ficaria aberto e sem
        proteção. A folga de 1e-9 (relativa) é mil vezes maior que o resíduo de uma conta em
        float e um milhão de vezes menor que qualquer lote: absorve o ruído e não arredonda
        para cima quantidade nenhuma que alguém tenha pedido.

        Quando o resultado é zero o ccxt levanta `InvalidOrder` em vez de devolver "0": aqui
        vira `AbaixoDoMinimo`, que é o que quem chama sabe tratar."""
        import ccxt
        try:
            return float(self.ex.amount_to_precision(perp(simbolo), float(qty) * (1 + 1e-9)))
        except ccxt.InvalidOrder as e:
            raise AbaixoDoMinimo(f"{simbolo}: qty {qty} não chega a um lote ({e})") from e

    def arredondar(self, simbolo, qty, preco=None, reduz=False):
        """Quantidade e preço como VÃO ser enviados (truncados para baixo pelo ccxt). Abaixo do
        lote mínimo ou do nocional mínimo: `AbaixoDoMinimo`, nunca arredonda para cima.

        `reduz=True` é para ordem que só fecha (TP, fechamento parcial): a Binance não aplica
        o nocional mínimo a ordem reduce-only, só o lote."""
        s = perp(simbolo)
        self._recarregar_mercados()
        m = self._mercado(simbolo)
        q = self._lote(simbolo, qty)
        p = float(self.ex.price_to_precision(s, preco)) if preco is not None else None
        lim = m.get("limits") or {}
        qmin = _f((lim.get("amount") or {}).get("min")) or 0.0
        cmin = _f((lim.get("cost") or {}).get("min")) or 0.0
        if q <= 0 or q < qmin:
            raise AbaixoDoMinimo(f"{simbolo}: qty {qty} vira {q}, lote mínimo {qmin}")
        if reduz:
            return q, p
        ref = p if p is not None else self._mark(simbolo)
        if cmin and q * ref < cmin:
            raise AbaixoDoMinimo(f"{simbolo}: nocional {q * ref:.2f} < mínimo {cmin}")
        return q, p

    # -------------------------------------------------------------- envio

    def _enviar(self, simbolo, tipo, lado, qty, preco, params, client_oid, ref_preco=None,
                condicional=False, com_teto=True):
        """O único ponto que chama `create_order`. Teto, dry_run e idempotência moram aqui."""
        import ccxt
        if not client_oid:
            raise ValueError("toda ordem leva client_oid (regra 5)")
        if com_teto and self.bloqueio_entrada:      # só a ENTRADA: reduzir segue sempre
            raise ChaveInsegura(f"entrada recusada: {self.bloqueio_entrada}. Fechar, stop e "
                                "pânico seguem funcionando")
        s = perp(simbolo)
        if qty is not None:
            qty = self._lote(simbolo, qty)              # o que VAI, sem resíduo de ponto flutuante
        if com_teto and qty is not None:
            ref = ref_preco or preco or self._mark(simbolo)
            nocional = float(qty) * float(ref)
            if nocional > self.nocional_max:
                raise AcimaDoTeto(f"{simbolo}: nocional {nocional:.2f} > teto {self.nocional_max:.2f}")
        p = dict(params or {})
        p["newClientOrderId"] = client_oid
        if self.dry_run:
            log(f"corretora[dry_run]: {tipo} {lado} {qty} {s} preço={preco} {p}")
            return {"id": f"dry-{client_oid}", "client_oid": client_oid, "simbolo": base(simbolo),
                    "lado": lado, "tipo": tipo.upper(), "condicional": condicional,
                    "status": "dry_run", "qty": qty, "preenchido": 0.0, "preco": preco,
                    "preco_medio": None, "gatilho": _f(p.get("stopPrice") or p.get("activatePrice")),
                    "ativacao": _f(p.get("activatePrice")),
                    "reduce_only": bool(p.get("reduceOnly")),
                    "close_position": bool(p.get("closePosition")), "ts": pd.Timestamp.now(),
                    "params": p}
        self._sincronizar_relogio()
        try:
            o = self.ex.create_order(s, tipo, lado, qty, preco, p)
        except ccxt.OrderNotFillable as e:
            raise OrdemRecusada(str(e)) from e
        except getattr(ccxt, "OperationFailed", ccxt.NetworkError) as e:
            # `OperationFailed` é a mãe do `NetworkError` (timeout, 5xx) e é também onde o ccxt
            # põe os -1000/-1001/-1006/-1008 da Binance ("não sei se executei"): todos são
            # envio incerto, e nenhum pode subir cru para quem chamou.
            achada = self._achar_viva(simbolo, client_oid, condicional)
            if achada:
                log(f"corretora: rede falhou no envio de {client_oid}, mas a ordem existe", "warning")
                return achada
            raise EnvioIncerto(f"{client_oid}: {e}") from e
        except ccxt.ExchangeError as e:
            # Id repetido: `-4116` nas normais, `-20132` nas condicionais (Algo), que o ccxt põe
            # em BadRequest/ExchangeError e não em InvalidOrder. Os dois querem dizer "esta ordem
            # já foi": busca e devolve a mesma. Sem o -20132, o reenvio idempotente de um stop
            # (`_stop_da_ordem`) virava recusa e cancelava uma entrada que estava protegida.
            if isinstance(e, ccxt.DuplicateOrderId) or _codigo(e, "-4116", "-20132"):
                achada = self._achar_viva(simbolo, client_oid, condicional)
                if achada:
                    return achada
            raise OrdemRecusada(str(e)) from e
        return normalizar_ordem(o)

    def _achar_viva(self, simbolo, client_oid, condicional):
        """A ordem com este id, se ela serve de resposta para o envio que acabou de falhar: viva
        (aberta, parcial) ou executada. Uma ordem MORTA com o mesmo id (cancelada, expirada,
        rejeitada) não confirma nada: devolvê-la faria o `mover_stop` cancelar o stop bom por
        causa de um stop que não existe. A própria busca pode falhar (a rede já estava ruim):
        isso também é "não sei", nunca exceção crua."""
        try:
            achada = self.buscar(simbolo, client_oid, condicional)
        except Exception as e:
            log(f"corretora: busca de {client_oid} depois da falha também falhou ({e})", "warning")
            return None
        if achada and achada.get("status") in ("cancelada", "expirada", "rejeitada"):
            log(f"corretora: {client_oid} existe mas está {achada.get('status')}; não confirma "
                "o envio", "warning")
            return None
        return achada

    def abrir_mercado(self, simbolo, direcao, qty, client_oid, ref_preco=None):
        """`ref_preco` é o preço em que quem chama já mediu o teto: sem ele, o teto é medido no
        mark de agora, e um tique de diferença recusa depois de o sinal estar consumido."""
        d = _direcao(direcao)
        o = self._enviar(simbolo, "market", _ABRE[d], qty, None, {}, client_oid, ref_preco=ref_preco)
        return self._com_preco_medio(simbolo, o)

    def fechar_mercado(self, simbolo, direcao, qty, client_oid):
        """Reduce-only: nunca abre posição do outro lado, nem por bug de quantidade. Sem teto:
        o teto existe para impedir abrir demais, e fechar é sempre permitido."""
        d = _direcao(direcao)
        o = self._enviar_sem_teto(simbolo, "market", _FECHA[d], qty, None, {"reduceOnly": True},
                                  client_oid)
        return self._com_preco_medio(simbolo, o)

    def _enviar_sem_teto(self, *a, **kw):
        """Ordens que só REDUZEM posição (fechar, SL, TP, trailing): o teto existe para impedir
        abrir demais, e fechar tem de ser sempre possível."""
        return self._enviar(*a, com_teto=False, **kw)

    def _com_preco_medio(self, simbolo, o):
        """A resposta da ordem a mercado veio sem `average` no demo: busca de novo pelo id."""
        if o.get("status") == "dry_run" or o.get("preco_medio"):
            return o
        try:
            again = normalizar_ordem(self.ex.fetch_order(o["id"], perp(simbolo)))
            if again.get("preco_medio"):
                return again
        except Exception as e:
            log(f"corretora: sem preço médio de {o.get('client_oid')} ({e})", "warning")
        return o

    def colocar_limite_post_only(self, simbolo, direcao, qty, preco, client_oid):
        """GTX: se cruzaria o livro, a Binance recusa (`-5022`) e nada fica registrado."""
        d = _direcao(direcao)
        return self._enviar(simbolo, "limit", _ABRE[d], qty, preco, {"timeInForce": "GTX"}, client_oid)

    def colocar_stop(self, simbolo, direcao, gatilho, client_oid, qty=None):
        """SL a mercado, disparado pelo MARK price (não pelo last: pavio de um negócio só não
        stopa). `qty=None` -> `closePosition` (só com posição aberta; some quando ela fecha).
        Com `qty` -> `reduceOnly` (aceito antes do fill; pode ficar órfão, ver regra 3)."""
        d = _direcao(direcao)
        p = {"stopPrice": self.ex.price_to_precision(perp(simbolo), gatilho), "workingType": "MARK_PRICE"}
        if qty is None:
            p["closePosition"] = True
        else:
            p["reduceOnly"] = True
        return self._enviar_sem_teto(simbolo, "STOP_MARKET", _FECHA[d], qty, None, p, client_oid,
                                     condicional=True)

    def colocar_tp(self, simbolo, direcao, gatilho, qty, client_oid):
        d = _direcao(direcao)
        p = {"stopPrice": self.ex.price_to_precision(perp(simbolo), gatilho), "workingType": "MARK_PRICE",
             "reduceOnly": True}
        return self._enviar_sem_teto(simbolo, "TAKE_PROFIT_MARKET", _FECHA[d], qty, None, p, client_oid,
                                     condicional=True)

    def colocar_trailing(self, simbolo, direcao, qty, ativacao, callback_pct, client_oid):
        """Trailing nativo: ativa em `ativacao` e devolve `callback_pct`% do melhor preço. É o que
        segue a posição de noite. Aproximação declarada: o do bot é em R/ATR, este é em %.

        `ativacao=None` = já está armado: o campo não vai, e a Binance ativa no preço do momento.
        Mandar o preço de agora como ativação é recusado metade das vezes (`-2021`): para ela a
        ativação tem de estar do lado que o preço ainda não alcançou.

        O campo é `activatePrice`, o nome da doc do serviço Algo, para onde as condicionais vão
        desde dez/2025. O ccxt 4.5.56 manda `activationPrice` (o nome antigo), e se a Binance o
        ignorar o padrão dela é ativar NO PREÇO DE AGORA: o trailing de uma posição ainda não
        armada seguiria o preço desde já e a fecharia de madrugada. Por isso o nome vai certo e
        o que a Binance gravou é conferido na volta (`_conferir_ativacao`)."""
        d = _direcao(direcao)
        cb = round(float(callback_pct), 1)
        if not 0.1 <= cb <= 10:
            raise OrdemRecusada(f"callback {callback_pct}% fora de [0,1; 10]")
        p = {"callbackRate": cb, "workingType": "MARK_PRICE", "reduceOnly": True}
        if ativacao is not None:
            p["activatePrice"] = self.ex.price_to_precision(perp(simbolo), ativacao)
        o = self._enviar_sem_teto(simbolo, "TRAILING_STOP_MARKET", _FECHA[d], qty, None, p,
                                  client_oid, condicional=True)
        if ativacao is not None and o.get("status") != "dry_run":
            self._conferir_ativacao(simbolo, o, float(p["activatePrice"]))
        return o

    def _conferir_ativacao(self, simbolo, o, enviada):
        """A ativação que a Binance gravou é a que foi enviada? Se não, o trailing é cancelado e
        a recusa sobe: o stop fixo continua lá, e um trailing ativado no lugar errado fecharia a
        posição antes do que o plano manda. Sem o campo na resposta, lê de novo pelo id; sem o
        campo nas duas, não dá para conferir e fica registrado."""
        gravada = o.get("ativacao")
        if gravada is None:
            try:
                lida = self.buscar(simbolo, o.get("client_oid"), condicional=True)
                gravada = (lida or {}).get("ativacao")
            except Exception as e:
                log(f"corretora: ativação de {o.get('client_oid')} não relida ({e})", "warning")
        if gravada is None:
            log(f"corretora: a Binance não devolveu a ativação de {o.get('client_oid')}; "
                "não deu para conferir", "warning")
            return
        if abs(gravada - enviada) <= 1e-9 * max(1.0, abs(enviada)):
            return
        try:
            self.cancelar(simbolo, o["id"], condicional=True)
        except Exception as e:
            log(f"corretora: trailing {o.get('client_oid')} com ativação errada NÃO cancelou ({e})",
                "error")
        raise OrdemRecusada(f"trailing {o.get('client_oid')}: a Binance gravou ativação {gravada}, "
                            f"enviada {enviada}; cancelado")

    def mover_stop(self, simbolo, ordem, novo_gatilho, novo_client_oid, qty=None):
        """Coloca o stop NOVO e só então cancela o antigo. A ordem inversa (cancelar e depois
        colocar, como o plano escreveu) deixa uma janela sem stop, e se o envio falhar nessa
        janela a posição fica nua. Nesta ordem, por um instante há DOIS stops: o primeiro que
        disparar fecha, e o outro não tem o que reduzir.

        O novo sai SEMPRE `reduceOnly` com quantidade: a Binance só aceita UM `closePosition`
        por direção (`-4130`, demo 16/11), então dois stops `closePosition` não convivem nem
        pelo instante da troca. Se o antigo era `closePosition` (sem qty), a quantidade vem da
        posição na corretora. Reduce-only com qty maior que a posição fecha só o que existe,
        então o mesmo stop serve depois de um TP parcial."""
        if not novo_client_oid or novo_client_oid == ordem.get("client_oid"):
            # mesmo id: a idempotência devolveria o stop ANTIGO e o cancelamento logo abaixo
            # deixaria a posição nua
            raise ValueError("mover_stop exige um client_oid novo")
        direcao = "LONG" if ordem.get("lado") == "sell" else "SHORT"
        qty = qty or ordem.get("qty")
        if not qty:
            qty = next((p["qty"] for p in self.posicoes()
                        if p["simbolo"] == base(simbolo) and p["direcao"] == direcao), None)
        if not qty:
            raise ErroCorretora(f"mover_stop {simbolo}: sem quantidade e sem posição na corretora")
        novo = self.colocar_stop(simbolo, direcao, novo_gatilho, novo_client_oid, qty=qty)
        if novo.get("id") == ordem.get("id"):
            return novo
        if novo.get("status") in ("cancelada", "expirada", "rejeitada"):
            # o antigo só sai quando o novo está de pé
            raise ErroCorretora(f"mover_stop {simbolo}: o stop novo voltou {novo.get('status')}; "
                                "o antigo fica")
        # O novo JÁ está na corretora: daqui para baixo nada pode levantar. Se o cancelamento do
        # antigo falhar (rede, ou o -20124 de condicional que já terminou), quem chama precisa
        # receber o NOVO para gravá-lo. Levantar aqui fazia o livro ficar com o id do antigo, e a
        # reconciliação seguinte cancelava o novo como órfão: a catraca do trailing andava para
        # trás (revisão de 26/11). O antigo que sobrar é nosso e sem dono: a reconciliação o tira.
        try:
            if not self.cancelar(simbolo, ordem["id"], condicional=True):
                log(f"corretora: stop antigo {ordem.get('client_oid')} já não existia ao mover",
                    "warning")
        except Exception as e:
            log(f"corretora: stop antigo {ordem.get('client_oid')} não cancelou ao mover "
                f"({type(e).__name__}: {e}); o novo vale, e a reconciliação tira o antigo", "warning")
        return novo

    def cancelar(self, simbolo, ordem_id, condicional=False):
        """True se cancelou; False se a corretora não conhecia a ordem (já executou ou já foi
        cancelada). Não levanta nesse caso: cancelar o que já não existe é o estado desejado."""
        import ccxt
        if self.dry_run:
            log(f"corretora[dry_run]: cancelaria {ordem_id}")
            return True
        try:
            self.ex.cancel_order(ordem_id, perp(simbolo), {"trigger": True} if condicional else {})
            return True
        except ccxt.OrderNotFound:
            return False
        except ccxt.BadRequest as e:
            # Condicional (Algo) que já disparou ou já foi cancelada volta -20124 ("Invalid algo
            # id or it has been completed"), que o ccxt põe em BadRequest e não em OrderNotFound.
            if "-20124" in str(e) or "-2011" in str(e):
                return False
            raise

    def cancelar_tudo(self, simbolo):
        """Normais e condicionais do símbolo. Devolve quantas havia."""
        n = len(self.ordens_abertas(simbolo))
        if self.dry_run:
            log(f"corretora[dry_run]: cancelaria {n} ordens de {simbolo}")
            return n
        s = perp(simbolo)
        self.ex.cancel_all_orders(s)
        self.ex.cancel_all_orders(s, {"trigger": True})
        return n


# ------------------------------------------------------------------------------ fábrica

MODOS = ("papel", "demo", "binance")
NOCIONAL_MAX_PADRAO = 300.0      # USDT por ordem; conta inicial de US$200 (dono, 16/11)


def _cliente_ccxt(modo, chave, segredo):
    import ccxt
    ex = ccxt.binanceusdm({"apiKey": chave, "secret": segredo, "enableRateLimit": True,
                           "options": {"adjustForTimeDifference": True,
                                       "warnOnFetchOpenOrdersWithoutSymbol": False}})
    if modo == "demo":
        ex.enable_demo_trading(True)
    ex.load_markets()
    return ex


def obter(cfg=None, env=None, preco_fn=None, saldo_fn=None, fabrica_ccxt=_cliente_ccxt):
    """A corretora que a config pede. `corretora` ausente = `papel`: nada muda até o dono trocar.

    Chaves vêm do ambiente (`EnvironmentFile` do serviço, `chmod 600`), nunca da config nem do
    banco: o banco vai para backup e o `/config` é lido pelo painel."""
    cfg = cfg or {}
    env = os.environ if env is None else env
    modo = str(cfg.get("corretora") or "papel").strip().lower()
    if modo not in MODOS:
        raise ErroCorretora(f"corretora inválida: {modo!r} (aceitas: {', '.join(MODOS)})")
    if modo == "papel":
        if preco_fn is None:
            raise ErroCorretora("Papel precisa de preco_fn")
        return Papel(preco_fn, saldo_fn)
    pref = "BINANCE_DEMO" if modo == "demo" else "BINANCE"
    chave, segredo = (env.get(f"{pref}_KEY") or "").strip(), (env.get(f"{pref}_SECRET") or "").strip()
    if not chave or not segredo:
        raise ErroCorretora(f"corretora={modo} sem {pref}_KEY/{pref}_SECRET no ambiente")
    teto = _f(cfg.get("corretora_nocional_max")) or NOCIONAL_MAX_PADRAO
    dry = str(cfg.get("corretora_dry_run") or "0").strip().lower() in ("1", "true", "sim")
    c = BinanceUSDM(fabrica_ccxt(modo, chave, segredo), modo, teto, dry_run=dry)
    c.conferir_chave()                  # modo binance: chave insegura bloqueia a ENTRADA (regra 8)
    return c
