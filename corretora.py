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
5. **Todo envio leva um id nosso (`client_oid`).** Repetir o id dá `-4116` e a ordem é achada
   por ele. Timeout de rede no envio é o caso clássico de abrir duas vezes: aqui ele vira uma
   BUSCA pelo id, nunca um reenvio cego. Se a busca não acha, levanta `EnvioIncerto` e quem
   chamou decide (a reconciliação resolve no ciclo seguinte).
6. **O relógio é o da Binance.** O PC do dono estava 18,7 s atrasado e a Binance recusou tudo
   (`-1021`, janela de 5 s). O adapter mede a diferença no início e de hora em hora.
7. **Teto de nocional por ordem**, última linha antes da corretora: um bug de dimensionamento
   vira recusa, não ordem (`PLANO-LIVE` Fase 6). E `dry_run`: monta a ordem inteira, já
   arredondada, e não manda.
8. **Chave real perigosa não opera.** No modo `binance` o adapter pergunta à Binance o que a
   chave pode fazer; com saque habilitado, transferência habilitada ou sem restrição de IP,
   recusa subir. Não há bandeira para desligar: é a lógica do `DASH_PASS` (CLAUDE.md §2).

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
    return {
        "id": str(o.get("id")) if o.get("id") is not None else None,
        "client_oid": o.get("clientOrderId") or info.get("clientAlgoId") or info.get("clientOrderId"),
        "simbolo": base(o["symbol"]) if o.get("symbol") else None,
        "lado": o.get("side"),
        "tipo": str(info.get("orderType") or info.get("type") or o.get("type") or "").upper(),
        "condicional": condicional,
        "status": status,
        "qty": _f(o.get("amount")) if o.get("amount") is not None else _f(info.get("quantity") or info.get("origQty")),
        "preenchido": _f(o.get("filled")) or _f(info.get("executedQty")) or 0.0,
        "preco": _f(o.get("price")),
        "preco_medio": _f(o.get("average")) or _f(info.get("avgPrice")) or None,
        "gatilho": _f(o.get("stopPrice")) or _f(info.get("triggerPrice")) or _f(info.get("stopPrice")),
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
        return {"livre": s, "total": s, "unrealized": 0.0}

    def posicoes(self):
        return []                       # no papel a posição é a linha do banco

    def ordens_abertas(self, simbolo=None):
        return []

    def marks(self, simbolos):
        return {s: self._preco(base(s)) for s in simbolos}

    def preparar_simbolo(self, simbolo, alavancagem):
        return None

    def arredondar(self, simbolo, qty, preco=None):
        return qty, preco

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

    def mover_stop(self, simbolo, ordem, novo_gatilho, novo_client_oid):
        return self.colocar_stop(simbolo, "LONG" if ordem.get("lado") == "sell" else "SHORT",
                                 novo_gatilho, novo_client_oid, qty=ordem.get("qty"))

    def cancelar(self, simbolo, ordem_id, condicional=False):
        return True

    def cancelar_tudo(self, simbolo):
        return 0

    def buscar(self, simbolo, client_oid, condicional=False):
        return None

    def fills(self, simbolo, desde_ms=None):
        return []

    def income(self, simbolo=None, desde_ms=None):
        return []

    def verificar_chave(self):
        return {"verificavel": False, "motivo": "papel"}


# ------------------------------------------------------------------------------ binance

class BinanceUSDM:
    """Ordens reais (demo ou real) na Binance USDⓈ-M, modo one-way, margem isolada.

    `ex` é o cliente ccxt já autenticado: injetado, para os testes trocarem por um dublê."""

    real = True
    RESYNC_RELOGIO_S = 3600

    def __init__(self, ex, modo, nocional_max, dry_run=False):
        if modo not in ("demo", "binance"):
            raise ValueError(f"modo inválido: {modo!r}")
        if not nocional_max or float(nocional_max) <= 0:
            raise ValueError("nocional_max é obrigatório e positivo: sem teto, sem ordem")
        self.ex = ex
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

    def _mercado(self, simbolo):
        return self.ex.market(perp(simbolo))

    def _mark(self, simbolo):
        return self.marks([simbolo])[base(simbolo)]

    # -------------------------------------------------------------- leitura

    def saldo(self):
        b = self.ex.fetch_balance()
        u = b.get("USDT") or {}
        info = b.get("info") or {}
        return {"livre": _f(u.get("free")), "total": _f(u.get("total")),
                "unrealized": _f(info.get("totalUnrealizedProfit")) or 0.0}

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

    def income(self, simbolo=None, desde_ms=None):
        """Taxa, funding e P&L realizados como a Binance os lançou (não como o modelo calcula)."""
        params = {"limit": 1000}
        if simbolo:
            params["symbol"] = self._mercado(simbolo)["id"]
        if desde_ms:
            params["startTime"] = int(desde_ms)
        out = []
        for i in self.ex.fapiPrivateGetIncome(params):
            out.append({"tipo": i.get("incomeType"), "valor": _f(i.get("income")),
                        "moeda": i.get("asset"), "simbolo": i.get("symbol"),
                        "ts": ms_para_sp(i.get("time"))})
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
        if problemas:
            raise ChaveInsegura("chave recusada: " + ", ".join(problemas))
        return {"verificavel": True, "ok": True}

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

    def arredondar(self, simbolo, qty, preco=None):
        """Quantidade e preço como VÃO ser enviados (truncados para baixo pelo ccxt). Abaixo do
        lote mínimo ou do nocional mínimo: `AbaixoDoMinimo`, nunca arredonda para cima."""
        s = perp(simbolo)
        m = self._mercado(simbolo)
        q = float(self.ex.amount_to_precision(s, qty))
        p = float(self.ex.price_to_precision(s, preco)) if preco is not None else None
        lim = m.get("limits") or {}
        qmin = _f((lim.get("amount") or {}).get("min")) or 0.0
        cmin = _f((lim.get("cost") or {}).get("min")) or 0.0
        if q <= 0 or q < qmin:
            raise AbaixoDoMinimo(f"{simbolo}: qty {qty} vira {q}, lote mínimo {qmin}")
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
        s = perp(simbolo)
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
                    "preco_medio": None, "gatilho": _f(p.get("stopPrice") or p.get("activationPrice")),
                    "reduce_only": bool(p.get("reduceOnly")),
                    "close_position": bool(p.get("closePosition")), "ts": pd.Timestamp.now(),
                    "params": p}
        self._sincronizar_relogio()
        try:
            o = self.ex.create_order(s, tipo, lado, qty, preco, p)
        except ccxt.OrderNotFillable as e:
            raise OrdemRecusada(str(e)) from e
        except (ccxt.InvalidOrder, ccxt.DuplicateOrderId) as e:
            if "-4116" in str(e) or isinstance(e, ccxt.DuplicateOrderId):
                achada = self.buscar(simbolo, client_oid, condicional)   # já foi: devolve a mesma
                if achada:
                    return achada
            raise OrdemRecusada(str(e)) from e
        except ccxt.NetworkError as e:                  # inclui RequestTimeout
            achada = self.buscar(simbolo, client_oid, condicional)
            if achada:
                log(f"corretora: rede falhou no envio de {client_oid}, mas a ordem existe", "warning")
                return achada
            raise EnvioIncerto(f"{client_oid}: {e}") from e
        except ccxt.ExchangeError as e:
            raise OrdemRecusada(str(e)) from e
        return normalizar_ordem(o)

    def abrir_mercado(self, simbolo, direcao, qty, client_oid):
        d = _direcao(direcao)
        o = self._enviar(simbolo, "market", _ABRE[d], qty, None, {}, client_oid)
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
        segue a posição de noite. Aproximação declarada: o do bot é em R/ATR, este é em %."""
        d = _direcao(direcao)
        cb = round(float(callback_pct), 1)
        if not 0.1 <= cb <= 10:
            raise OrdemRecusada(f"callback {callback_pct}% fora de [0,1; 10]")
        p = {"activationPrice": self.ex.price_to_precision(perp(simbolo), ativacao),
             "callbackRate": cb, "workingType": "MARK_PRICE", "reduceOnly": True}
        return self._enviar_sem_teto(simbolo, "TRAILING_STOP_MARKET", _FECHA[d], qty, None, p,
                                     client_oid, condicional=True)

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
        if not self.cancelar(simbolo, ordem["id"], condicional=True):
            log(f"corretora: stop antigo {ordem.get('client_oid')} já não existia ao mover", "warning")
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
    c.verificar_chave()                 # modo binance: levanta ChaveInsegura e não sobe
    return c
