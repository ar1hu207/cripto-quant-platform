# -*- coding: utf-8 -*-
"""[LIVE-1] `corretora.py`: o adapter da Binance e o `Papel`, sem rede.

O dublê `_ExFake` reproduz o que o DEMO da Binance fez em 16/11/2026 com ordens de verdade
(dinheiro fictício). Cada comportamento dele tem a medição de origem ao lado. Se a Binance mudar,
é o dublê que fica velho: a prova `TestDemoAoVivo`, no fim, roda o mesmo roteiro contra o demo
real quando `RODAR_DEMO=1` e as chaves estão no ambiente.
"""
import os

import ccxt
import pandas as pd
import pytest

import corretora as C


class _ExFake:
    """Só a superfície do ccxt que o adapter usa."""

    def __init__(self, mark=100.0, timeout_no_envio=False, timeout_perde=False):
        self.options = {}
        self.mark = mark
        self.ordens = {}                 # id -> ordem crua no formato do ccxt
        self.coids = {}                  # client id -> id
        self.posicao = 0.0               # qty com sinal (one-way)
        self.chamadas = []
        self.timeout_no_envio = timeout_no_envio   # ordem CHEGA e a resposta se perde
        self.timeout_perde = timeout_perde         # ordem NÃO chega
        self.seq = 1000
        self.margem = {}
        self.lev = {}
        self.hedge = False
        self.restricoes = {"enableWithdrawals": False, "enableInternalTransfer": False,
                           "permitsUniversalTransfer": False, "ipRestrict": True, "enableFutures": True}
        self.relogio_sincronizado = 0
        self.multi = False
        self.mercados_carregados = 0
        self.ativacao_gravada = None             # força a Binance a gravar outra ativação
        self.erros = {}                          # método -> lista de exceções a levantar, uma por chamada
        self.last_response_headers = {}
        self.income_chamadas = []

    # ---- mercado
    def market(self, s):
        return {"id": s.split("/")[0] + "USDT", "limits": {"amount": {"min": 0.01}, "cost": {"min": 5.0}}}

    def amount_to_precision(self, s, q):
        # Trunca pelo TEXTO do número, como o `decimal_to_precision` do ccxt: `0.3 - 0.1` é
        # 0.19999999999999998 e vira 0,19. `int(q * 100)` dava 20 em float e escondia o lote
        # perdido que a folga do `_lote` existe para evitar (revisão de testes de 26/11, M05).
        from decimal import Decimal, ROUND_DOWN
        n = Decimal(repr(float(q))).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        if n <= 0:                                      # ccxt 4.5: levanta, não devolve "0"
            raise ccxt.InvalidOrder(f"binanceusdm amount of {s} must be greater than minimum "
                                    "amount precision of 0.01")
        return str(n)

    def price_to_precision(self, s, p):
        return f"{float(p):.2f}"

    def load_time_difference(self):
        self.relogio_sincronizado += 1

    def load_markets(self, recarregar=False):
        self.mercados_carregados += 1

    def _erro(self, metodo):
        fila = self.erros.get(metodo)
        if fila:
            raise fila.pop(0)

    def fetch_mark_prices(self, simbolos):
        return {s: {"markPrice": self.mark} for s in simbolos}

    # ---- ordens
    def create_order(self, s, tipo, lado, qty, preco, params):
        self.chamadas.append(("create_order", s, tipo, lado, qty, preco, dict(params)))
        self._erro("create_order")
        coid = params["newClientOrderId"]
        if getattr(self, "falha_no_envio", None) is not None:
            raise self.falha_no_envio
        if self.timeout_perde:
            raise ccxt.RequestTimeout("timeout")
        condicional = tipo.upper() in ("STOP_MARKET", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET")
        if coid in self.coids:
            if condicional:     # serviço Algo: -20132, que o ccxt 4.5.56 põe em BadRequest
                raise ccxt.BadRequest('binanceusdm {"code":-20132,"msg":"The client algo id is duplicated."}')
            raise ccxt.InvalidOrder('binanceusdm {"code":-4116,"msg":"ClientOrderId is duplicated."}')   # demo
        if condicional and params.get("closePosition") and self.posicao == 0:   # demo: -4509
            raise ccxt.ExchangeError('binanceusdm {"code":-4509,"msg":"Time in Force (TIF) GTE can only be used with open positions."}')
        if condicional and params.get("closePosition") and any(           # demo: -4130
                o["info"].get("closePosition") and o["info"].get("algoStatus") == "NEW"
                and o["side"] == lado and o["symbol"] == s for o in self.ordens.values()):
            raise ccxt.ExchangeError('binanceusdm {"code":-4130,"msg":"An open stop or take profit order with GTE and closePosition in the direction is existing."}')
        if params.get("timeInForce") == "GTX":                         # demo: -5022
            cruza = (lado == "buy" and preco >= self.mark) or (lado == "sell" and preco <= self.mark)
            if cruza:
                raise ccxt.OrderNotFillable('binanceusdm {"code":-5022,"msg":"Post Only order will be rejected"}')
        self.seq += 1
        oid = str(self.seq)
        if condicional:
            info = {"algoId": oid, "clientAlgoId": coid, "algoStatus": "NEW", "orderType": tipo.upper(),
                    "quantity": str(qty) if qty is not None else "0",
                    "closePosition": bool(params.get("closePosition")),
                    "reduceOnly": bool(params.get("reduceOnly")),
                    "triggerPrice": params.get("stopPrice")}
            if tipo.upper() == "TRAILING_STOP_MARKET":
                # Doc do Algo: o campo é `activatePrice`, e sem ele a ativação é o preço de agora.
                # O nome antigo (`activationPrice`) não é lido (revisão de 26/11, R5 #1).
                info["activatePrice"] = str(self.ativacao_gravada or params.get("activatePrice")
                                            or self.mark)
                if getattr(self, "sem_ativacao", False):    # a Binance não devolve o campo
                    info.pop("activatePrice")
            o = {"id": oid, "clientOrderId": coid, "symbol": s, "type": "market", "side": lado,
                 "status": "open", "amount": qty, "filled": 0.0, "price": None, "average": None,
                 "stopPrice": float(params["stopPrice"]) if params.get("stopPrice") else None,
                 "reduceOnly": bool(params.get("reduceOnly")), "timestamp": 1794866948000, "info": info}
        else:
            mercado = tipo == "market"
            if mercado:
                self.posicao += (qty if lado == "buy" else -qty)
            info = {"orderId": oid, "clientOrderId": coid, "status": "FILLED" if mercado else "NEW",
                    "type": tipo.upper(), "origQty": str(qty), "executedQty": str(qty if mercado else 0),
                    "avgPrice": "0", "reduceOnly": bool(params.get("reduceOnly")), "closePosition": False}
            o = {"id": oid, "clientOrderId": coid, "symbol": s, "type": tipo, "side": lado,
                 "status": "closed" if mercado else "open", "amount": qty,
                 "filled": qty if mercado else 0.0, "price": preco,
                 "average": None,                                       # demo: market veio sem average
                 "stopPrice": None, "reduceOnly": bool(params.get("reduceOnly")),
                 "timestamp": 1794866948000, "info": info}
        self.ordens[oid] = o
        self.coids[coid] = oid
        if self.timeout_no_envio:
            raise ccxt.RequestTimeout("timeout depois de chegar")
        return o

    def fetch_order(self, oid, s, params=None):
        params = params or {}
        self.chamadas.append(("fetch_order", oid, s, dict(params)))
        self._erro("fetch_order")
        if oid is None:
            coid = params.get("origClientOrderId") or params.get("clientAlgoId")
            oid = self.coids.get(coid)
        if oid not in self.ordens:
            raise ccxt.OrderNotFound('{"code":-2013,"msg":"Order does not exist."}')
        o = dict(self.ordens[oid])
        if o["type"] == "market" and "algoId" not in o["info"]:
            o["average"] = self.mark                                   # a segunda leitura traz o preço
            o["info"] = dict(o["info"], avgPrice=str(self.mark))
        return o

    def fetch_open_orders(self, s=None, since=None, limit=None, params=None):
        params = params or {}
        trig = bool(params.get("trigger"))
        out = []
        for o in self.ordens.values():
            alg = "algoId" in o["info"]
            st = o["info"].get("algoStatus") if alg else o["info"].get("status")
            if alg == trig and st == "NEW" and (s is None or o["symbol"] == s):
                out.append(o)
        return out

    def cancel_order(self, oid, s, params=None):
        self.chamadas.append(("cancel_order", oid, s, dict(params or {})))
        o = self.ordens.get(oid)
        trig = bool((params or {}).get("trigger"))
        if o is not None and ("algoId" in o["info"]) != trig:
            o = None                                    # o serviço errado não conhece a ordem
        if not o or o["info"]["algoStatus" if "algoId" in o["info"] else "status"] != "NEW":
            if trig:
                # condicional (Algo) já terminada ou desconhecida: o ccxt põe em BadRequest
                raise ccxt.BadRequest('binanceusdm {"code":-20124,"msg":"Invalid algo id or it '
                                      'has been completed."}')
            raise ccxt.OrderNotFound('{"code":-2011,"msg":"Unknown order sent."}')
        chave = "algoStatus" if "algoId" in o["info"] else "status"
        o["info"][chave] = "CANCELED"
        return o

    def cancel_all_orders(self, s, params=None):
        trig = bool((params or {}).get("trigger"))
        for o in self.fetch_open_orders(s, params={"trigger": trig}):
            self.cancel_order(o["id"], s, params)

    # ---- conta
    def set_margin_mode(self, modo, s):
        self.chamadas.append(("set_margin_mode", modo, s))
        if self.margem.get(s) == modo:
            raise ccxt.ExchangeError('{"code":-4046,"msg":"No need to change margin type."}')
        self.margem[s] = modo

    def set_leverage(self, lev, s):
        self.chamadas.append(("set_leverage", lev, s))
        self.lev[s] = lev

    def fetch_balance(self):
        self.chamadas.append(("fetch_balance",))
        self._erro("fetch_balance")
        return {"USDT": {"free": 200.0, "total": 205.0},
                "info": {"totalUnrealizedProfit": "5.0", "totalWalletBalance": "200.0",
                         "totalMarginBalance": "205.0"}}

    def fapiPrivateGetPositionSideDual(self, params=None):
        return {"dualSidePosition": self.hedge}

    def fapiPrivateGetMultiAssetsMargin(self, params=None):
        self._erro("multi")
        return {"multiAssetsMargin": self.multi}

    def fetch_positions(self, simbolos=None):
        if self.posicao:
            return [{"symbol": "SOL/USDT:USDT", "contracts": abs(self.posicao),
                     "side": "long" if self.posicao > 0 else "short", "entryPrice": self.mark,
                     "markPrice": self.mark, "liquidationPrice": None, "initialMargin": 1.0,
                     "marginMode": "isolated", "leverage": 5, "unrealizedPnl": 0.0}]
        return [{"symbol": "SOL/USDT:USDT", "contracts": 0.08, "side": "long", "entryPrice": 71.92,
                 "markPrice": 72.0, "liquidationPrice": 58.15, "initialMargin": 1.15,
                 "marginMode": "isolated", "leverage": 5, "unrealizedPnl": 0.0064},
                {"symbol": "ETH/USDT:USDT", "contracts": 0.0, "side": None}]

    def fetch_my_trades(self, s, since=None, limit=None):
        return [{"id": 1, "order": "1001", "symbol": s, "side": "buy", "amount": 0.08, "price": 71.92,
                 "fee": {"cost": 0.00230144, "currency": "USDT"}, "timestamp": 1794866948000,
                 "info": {"maker": False, "realizedPnl": "0"}}]

    def fapiPrivateGetIncome(self, params):
        self.income_chamadas.append(dict(params))
        if "endTime" in params:                 # janela: um funding por dia, dentro dela
            ini, fim = params["startTime"], params["endTime"]
            dia = 86400 * 1000
            return [{"incomeType": "FUNDING_FEE", "income": "-0.01", "asset": "USDT",
                     "symbol": "SOLUSDT", "time": str(t), "tranId": t}
                    for t in range((ini // dia + 1) * dia, fim + 1, dia)]
        return [{"incomeType": "COMMISSION", "income": "-0.00230144", "asset": "USDT",
                 "symbol": "SOLUSDT", "time": "1794866948000"}]

    def sapiGetAccountApiRestrictions(self):
        return dict(self.restricoes)


def _bin(ex=None, **kw):
    return C.BinanceUSDM(ex or _ExFake(), kw.pop("modo", "demo"), kw.pop("teto", 300.0), **kw)


def _creates(ex):
    return [c for c in ex.chamadas if c[0] == "create_order"]


# ------------------------------------------------------------------ fronteiras

def test_simbolo_ida_e_volta():
    assert C.perp("BTC/USDT") == "BTC/USDT:USDT"
    assert C.perp("BTC/USDT:USDT") == "BTC/USDT:USDT"
    assert C.base("BTC/USDT:USDT") == "BTC/USDT"
    assert C.base("BTC/USDT") == "BTC/USDT"


def test_tempo_vira_naive_em_sao_paulo():
    # 1794866948000 ms = 2026-11-16 22:09:08 UTC = 19:09:08 em São Paulo (UTC-3, sem horário de verão)
    t = C.ms_para_sp(1794866948000)
    assert t.tz is None
    assert t == pd.Timestamp("2026-11-16 19:09:08")


def test_direcao_invalida_levanta():
    with pytest.raises(ValueError):
        _bin().abrir_mercado("SOL/USDT", "compra", 0.1, "x1")


# ------------------------------------------------------------------ relógio (regra 6)

def test_relogio_sincroniza_ao_nascer_e_ressincroniza_depois_de_uma_hora(monkeypatch):
    ex = _ExFake()
    b = _bin(ex)
    assert ex.relogio_sincronizado == 1
    assert ex.options["adjustForTimeDifference"] is True
    b.colocar_limite_post_only("SOL/USDT", "LONG", 0.1, 90.0, "r1")
    assert ex.relogio_sincronizado == 1                      # dentro da hora: não repete
    b._relogio_em -= C.BinanceUSDM.RESYNC_RELOGIO_S + 1
    b.colocar_limite_post_only("SOL/USDT", "LONG", 0.1, 90.0, "r2")
    assert ex.relogio_sincronizado == 2


# ------------------------------------------------------------------ arredondar

def test_arredondar_trunca_e_respeita_minimos():
    b = _bin()
    assert b.arredondar("SOL/USDT", 0.0899, 70.123) == (0.08, 70.12)
    with pytest.raises(C.AbaixoDoMinimo):                    # lote: 0.009 trunca para 0.00
        b.arredondar("SOL/USDT", 0.009, 70.0)
    with pytest.raises(C.AbaixoDoMinimo):                    # nocional 0.05 x 70 = 3,50 < 5
        b.arredondar("SOL/USDT", 0.05, 70.0)


def test_arredondar_sem_preco_usa_o_mark():
    ex = _ExFake(mark=50.0)
    with pytest.raises(C.AbaixoDoMinimo):                    # 0.09 x 50 = 4,50 < 5
        _bin(ex).arredondar("SOL/USDT", 0.09)


# ------------------------------------------------------------------ teto e dry_run (regra 7)

def test_teto_recusa_antes_de_chegar_na_corretora():
    ex = _ExFake(mark=100.0)
    b = _bin(ex, teto=300.0)
    with pytest.raises(C.AcimaDoTeto):
        b.abrir_mercado("SOL/USDT", "LONG", 3.01, "t1")      # 301 USDT
    assert _creates(ex) == []


def test_teto_nao_impede_fechar_nem_proteger():
    """Fechar e proteger têm de ser sempre possíveis: o teto só barra ABRIR demais."""
    ex = _ExFake(mark=100.0)
    b = _bin(ex, teto=300.0)
    ex.posicao = 5.0
    b.fechar_mercado("SOL/USDT", "LONG", 5.0, "f1")
    b.colocar_stop("SOL/USDT", "LONG", 95.0, "s1", qty=5.0)
    b.colocar_tp("SOL/USDT", "LONG", 110.0, 5.0, "tp1")
    assert len(_creates(ex)) == 3


def test_sem_teto_nao_nasce():
    with pytest.raises(ValueError):
        C.BinanceUSDM(_ExFake(), "demo", 0)


def test_dry_run_monta_e_nao_envia():
    ex = _ExFake()
    b = _bin(ex, dry_run=True)
    o = b.colocar_stop("SOL/USDT", "LONG", 95.0, "d1", qty=0.1)
    assert o["status"] == "dry_run" and o["params"]["reduceOnly"] is True
    assert o["params"]["workingType"] == "MARK_PRICE" and o["gatilho"] == 95.0
    b.preparar_simbolo("SOL/USDT", 5)
    assert _creates(ex) == [] and not any(c[0] in ("set_leverage", "set_margin_mode") for c in ex.chamadas)


# ------------------------------------------------------------------ idempotência (regra 5)

def test_timeout_depois_de_chegar_devolve_a_ordem_achada_pelo_id():
    ex = _ExFake(timeout_no_envio=True)
    o = _bin(ex).colocar_limite_post_only("SOL/USDT", "LONG", 0.1, 90.0, "i1")
    assert o["client_oid"] == "i1" and o["status"] == "aberta"
    assert len(_creates(ex)) == 1                            # não reenviou


def test_timeout_sem_ordem_levanta_envio_incerto_e_nao_reenvia():
    ex = _ExFake(timeout_perde=True)
    with pytest.raises(C.EnvioIncerto):
        _bin(ex).colocar_limite_post_only("SOL/USDT", "LONG", 0.1, 90.0, "i2")
    assert len(_creates(ex)) == 1


def test_id_repetido_devolve_a_ordem_existente():
    ex = _ExFake()
    b = _bin(ex)
    a = b.colocar_limite_post_only("SOL/USDT", "LONG", 0.1, 90.0, "i3")
    again = b.colocar_limite_post_only("SOL/USDT", "LONG", 0.1, 90.0, "i3")
    assert again["id"] == a["id"]
    assert len(ex.ordens) == 1


def test_timeout_em_condicional_busca_pelo_id_de_algo():
    ex = _ExFake(timeout_no_envio=True)
    o = _bin(ex).colocar_stop("SOL/USDT", "LONG", 95.0, "i4", qty=0.1)
    assert o["condicional"] and o["client_oid"] == "i4"
    busca = [c for c in ex.chamadas if c[0] == "fetch_order"][-1]
    assert busca[3] == {"trigger": True, "clientAlgoId": "i4"}


def test_resto_de_subtracao_nao_perde_um_lote():
    """`0.3 - 0.1` é `0.19999999999999998` em float. Truncado cru vira 0,19: um lote a menos no
    stop ou no fechamento, que ficaria aberto e sem proteção."""
    ex = _ExFake()
    c = _bin(ex)
    assert c.arredondar("SOL/USDT", 0.3 - 0.1, reduz=True)[0] == 0.2
    ex.posicao = 0.2
    c.fechar_mercado("SOL/USDT", "LONG", 0.3 - 0.1, "x1")
    c.colocar_stop("SOL/USDT", "LONG", 95.0, "s1", qty=0.3 - 0.1)
    assert [x[4] for x in _creates(ex)] == [0.2, 0.2]
    assert c.arredondar("SOL/USDT", 0.2999, reduz=True)[0] == 0.29     # e não arredonda para cima


def test_menos_que_um_lote_e_abaixo_do_minimo_e_nao_erro_cru_do_ccxt():
    ex = _ExFake()
    c = _bin(ex)
    with pytest.raises(C.AbaixoDoMinimo):
        c.arredondar("SOL/USDT", 0.004, reduz=True)
    with pytest.raises(C.AbaixoDoMinimo):
        c.colocar_tp("SOL/USDT", "LONG", 110.0, 0.004, "t1")
    assert not _creates(ex)


def test_erro_de_operacao_que_nao_e_de_rede_tambem_e_envio_incerto():
    """-1000/-1001/-1006/-1008 da Binance chegam como `OperationFailed`, que não é
    `NetworkError` nem `ExchangeError`: subiam crus."""
    ex = _ExFake()
    ex.falha_no_envio = ccxt.OperationFailed('binanceusdm {"code":-1001,"msg":"Internal error"}')
    with pytest.raises(C.EnvioIncerto):
        _bin(ex).abrir_mercado("SOL/USDT", "LONG", 0.5, "e1")


def test_ordem_morta_com_o_mesmo_id_nao_confirma_o_envio():
    """O envio falhou e a busca acha uma ordem CANCELADA com o id: não é a resposta deste envio.
    Devolvê-la faria o `mover_stop` cancelar o stop bom por causa de um que não existe."""
    ex = _ExFake()
    c = _bin(ex)
    morto = c.colocar_stop("SOL/USDT", "LONG", 95.0, "s1", qty=0.5)
    c.cancelar("SOL/USDT", morto["id"], condicional=True)
    ex.timeout_perde = True
    with pytest.raises(C.EnvioIncerto):
        c.colocar_stop("SOL/USDT", "LONG", 96.0, "s1", qty=0.5)
    ex.timeout_perde = False
    with pytest.raises(C.OrdemRecusada):                               # -4116 de id já usado
        c.colocar_stop("SOL/USDT", "LONG", 96.0, "s1", qty=0.5)


def test_se_a_busca_depois_da_falha_tambem_falha_e_envio_incerto(monkeypatch):
    ex = _ExFake(timeout_perde=True)
    c = _bin(ex)

    def sem_rede(*a, **k):
        raise ccxt.RequestTimeout("x")
    monkeypatch.setattr(ex, "fetch_order", sem_rede)
    with pytest.raises(C.EnvioIncerto):
        c.abrir_mercado("SOL/USDT", "LONG", 0.5, "e1")


def test_mover_stop_nao_cancela_o_antigo_se_o_novo_voltou_morto(monkeypatch):
    ex = _ExFake()
    c = _bin(ex)
    antigo = c.colocar_stop("SOL/USDT", "LONG", 95.0, "s1", qty=0.5)
    monkeypatch.setattr(c, "colocar_stop", lambda *a, **k: {"id": "9", "status": "cancelada"})
    with pytest.raises(C.ErroCorretora):
        c.mover_stop("SOL/USDT", antigo, 96.0, "s2", qty=0.5)
    assert not [x for x in ex.chamadas if x[0] == "cancel_order"]


def test_trailing_ja_armado_vai_sem_preco_de_ativacao():
    ex = _ExFake()
    _bin(ex).colocar_trailing("SOL/USDT", "LONG", 0.5, None, 1.0, "r1")
    assert "activationPrice" not in _creates(ex)[0][6] and "activatePrice" not in _creates(ex)[0][6]


def test_ordem_sem_client_oid_nao_sai():
    with pytest.raises(ValueError):
        _bin().colocar_limite_post_only("SOL/USDT", "LONG", 0.1, 90.0, "")


# ------------------------------------------------------------------ entrada

def test_post_only_que_cruzaria_e_recusado():
    with pytest.raises(C.OrdemRecusada):
        _bin(_ExFake(mark=100.0)).colocar_limite_post_only("SOL/USDT", "LONG", 0.1, 101.0, "p1")


def test_post_only_vai_como_gtx_do_lado_certo():
    ex = _ExFake(mark=100.0)
    _bin(ex).colocar_limite_post_only("SOL/USDT", "SHORT", 0.1, 101.0, "p2")
    _, s, tipo, lado, qty, preco, params = _creates(ex)[0]
    assert (s, tipo, lado, preco, params["timeInForce"]) == ("SOL/USDT:USDT", "limit", "sell", 101.0, "GTX")


def test_mercado_traz_o_preco_medio_mesmo_quando_a_resposta_vem_sem():
    ex = _ExFake(mark=71.92)
    o = _bin(ex).abrir_mercado("SOL/USDT", "LONG", 0.08, "m1")
    assert o["preco_medio"] == 71.92 and o["status"] == "preenchida"


# ------------------------------------------------------------------ proteção (regras 1-3)

def test_stop_sem_qty_e_close_position_e_so_vale_com_posicao():
    ex = _ExFake()
    b = _bin(ex)
    with pytest.raises(C.OrdemRecusada):                     # demo: -4509 sem posição
        b.colocar_stop("SOL/USDT", "LONG", 95.0, "c1")
    ex.posicao = 0.1
    o = b.colocar_stop("SOL/USDT", "LONG", 95.0, "c2")
    p = _creates(ex)[-1][6]
    assert p["closePosition"] is True and "reduceOnly" not in p and o["close_position"]


def test_stop_com_qty_e_reduce_only_e_vale_antes_do_fill():
    """A entrada post-only pode encher de madrugada com o servidor desligado: o SL tem de
    existir ANTES do fill, e só o reduce-only com quantidade é aceito sem posição."""
    ex = _ExFake()
    o = _bin(ex).colocar_stop("SOL/USDT", "SHORT", 105.0, "c3", qty=0.1)
    _, _, tipo, lado, qty, _, p = _creates(ex)[-1]
    assert (tipo, lado, qty, p["reduceOnly"], p["workingType"]) == ("STOP_MARKET", "buy", 0.1, True, "MARK_PRICE")
    assert o["condicional"] and o["status"] == "aberta"


def test_tp_e_trailing_saem_do_lado_que_fecha():
    ex = _ExFake()
    b = _bin(ex)
    b.colocar_tp("SOL/USDT", "LONG", 110.0, 0.05, "tp")
    b.colocar_trailing("SOL/USDT", "SHORT", 0.1, 95.0, 1.5, "tr")
    tp, tr = _creates(ex)[-2:]
    assert (tp[2], tp[3], tp[6]["reduceOnly"]) == ("TAKE_PROFIT_MARKET", "sell", True)
    assert (tr[2], tr[3], tr[6]["callbackRate"], tr[6]["activatePrice"]) == ("TRAILING_STOP_MARKET", "buy", 1.5, "95.00")
    assert "activationPrice" not in tr[6]                       # o nome antigo não é lido pelo Algo


def test_trailing_fora_da_faixa_da_binance_e_recusado_aqui():
    with pytest.raises(C.OrdemRecusada):
        _bin().colocar_trailing("SOL/USDT", "LONG", 0.1, 110.0, 12, "tr2")


def test_ordens_abertas_traz_normais_e_condicionais():
    ex = _ExFake()
    b = _bin(ex)
    b.colocar_limite_post_only("SOL/USDT", "LONG", 0.1, 90.0, "o1")
    b.colocar_stop("SOL/USDT", "LONG", 85.0, "o2", qty=0.1)
    b.colocar_tp("SOL/USDT", "LONG", 120.0, 0.1, "o3")
    abertas = {o["client_oid"]: o for o in b.ordens_abertas("SOL/USDT")}
    assert set(abertas) == {"o1", "o2", "o3"}
    assert not abertas["o1"]["condicional"] and abertas["o2"]["condicional"]
    assert abertas["o2"]["tipo"] == "STOP_MARKET" and abertas["o3"]["tipo"] == "TAKE_PROFIT_MARKET"


def test_status_da_condicional_vem_do_algo_status():
    o = {"id": "9", "clientOrderId": "x", "symbol": "SOL/USDT:USDT", "status": "open", "side": "sell",
         "type": "market", "info": {"algoId": "9", "algoStatus": "CANCELED", "orderType": "STOP_MARKET"}}
    assert C.normalizar_ordem(o)["status"] == "cancelada"


def test_trailing_le_a_ativacao_do_campo_que_a_binance_usa():
    """Demo, 16/11: a ordem de trailing volta com `activatePrice`, sem stopPrice/triggerPrice."""
    o = {"id": "7", "clientOrderId": "tr", "symbol": "AAVE/USDT:USDT", "status": "open", "side": "sell",
         "type": "market", "stopPrice": None,
         "info": {"algoId": "7", "algoStatus": "NEW", "orderType": "TRAILING_STOP_MARKET", "activatePrice": "108.68"}}
    assert C.normalizar_ordem(o)["gatilho"] == 108.68


def test_cancelar_o_que_nao_existe_devolve_false():
    ex = _ExFake()
    b = _bin(ex)
    s = b.colocar_stop("SOL/USDT", "LONG", 95.0, "k1", qty=0.1)
    assert b.cancelar("SOL/USDT", s["id"], condicional=True) is True
    assert b.cancelar("SOL/USDT", s["id"], condicional=True) is False


def test_mover_stop_coloca_o_novo_antes_de_cancelar_o_antigo():
    ex = _ExFake()
    b = _bin(ex)
    velho = b.colocar_stop("SOL/USDT", "LONG", 95.0, "mv1", qty=0.1)
    ex.chamadas.clear()
    novo = b.mover_stop("SOL/USDT", velho, 97.0, "mv2")
    tipos = [c[0] for c in ex.chamadas if c[0] in ("create_order", "cancel_order")]
    assert tipos == ["create_order", "cancel_order"]
    assert novo["gatilho"] == 97.0 and novo["qty"] == 0.1


def test_dois_close_position_na_mesma_direcao_nao_convivem():
    ex = _ExFake()
    ex.posicao = 0.1
    b = _bin(ex)
    b.colocar_stop("SOL/USDT", "LONG", 95.0, "cp1")
    with pytest.raises(C.OrdemRecusada, match="-4130"):
        b.colocar_stop("SOL/USDT", "LONG", 96.0, "cp2")


def test_mover_stop_close_position_vira_reduce_only_com_a_qty_da_posicao():
    """Demo, 16/11: o roteiro ao vivo falhou aqui com -4130 antes deste conserto."""
    ex = _ExFake()
    ex.posicao = 0.08
    b = _bin(ex)
    velho = b.colocar_stop("SOL/USDT", "LONG", 95.0, "cp3")
    ex.chamadas.clear()
    novo = b.mover_stop("SOL/USDT", velho, 97.0, "cp4")
    p = _creates(ex)[0][6]
    assert p.get("reduceOnly") is True and "closePosition" not in p and novo["qty"] == 0.08
    assert [c[0] for c in ex.chamadas if c[0] in ("create_order", "cancel_order")] == ["create_order", "cancel_order"]


def test_mover_stop_sem_qty_e_sem_posicao_recusa():
    ex = _ExFake()
    ex.posicao = 0.1
    b = _bin(ex)
    velho = b.colocar_stop("SOL/USDT", "LONG", 95.0, "cp5")
    ex.posicao = 0.0
    ex.fetch_positions = lambda simbolos=None: []
    with pytest.raises(C.ErroCorretora, match="sem posição"):
        b.mover_stop("SOL/USDT", velho, 97.0, "cp6")


def test_mover_stop_com_o_mesmo_id_e_recusado_e_o_antigo_fica():
    """Com o mesmo id, a idempotência devolveria o stop antigo e o cancelamento seguinte
    deixaria a posição sem stop. Achado ao escrever este arquivo."""
    ex = _ExFake()
    b = _bin(ex)
    velho = b.colocar_stop("SOL/USDT", "LONG", 95.0, "mv3", qty=0.1)
    with pytest.raises(ValueError):
        b.mover_stop("SOL/USDT", velho, 97.0, "mv3")
    assert ex.ordens[velho["id"]]["info"]["algoStatus"] == "NEW"


def test_mover_stop_que_falha_no_envio_mantem_o_antigo():
    ex = _ExFake()
    b = _bin(ex)
    velho = b.colocar_stop("SOL/USDT", "LONG", 95.0, "mv4", qty=0.1)
    ex.timeout_perde = True
    with pytest.raises(C.EnvioIncerto):
        b.mover_stop("SOL/USDT", velho, 97.0, "mv5")
    assert ex.ordens[velho["id"]]["info"]["algoStatus"] == "NEW"   # o antigo segue protegendo


def test_mover_stop_que_nao_cancela_o_antigo_devolve_o_novo():
    """O novo já está lá: se o cancelamento do antigo falha, quem chama tem de receber o NOVO.
    Levantar fazia o livro ficar com o antigo e a reconciliação cancelar o novo (revisão 26/11)."""
    ex = _ExFake()
    b = _bin(ex)
    velho = b.colocar_stop("SOL/USDT", "LONG", 95.0, "mv6", qty=0.1)
    real = ex.cancel_order

    def cai(*a, **k):
        raise ccxt.RequestTimeout("timeout")
    ex.cancel_order = cai
    novo = b.mover_stop("SOL/USDT", velho, 97.0, "mv7")
    ex.cancel_order = real
    assert novo["gatilho"] == 97.0 and novo["client_oid"] == "mv7"
    assert ex.ordens[novo["id"]]["info"]["algoStatus"] == "NEW"


def test_cancelar_condicional_ja_terminada_devolve_false_e_nao_levanta():
    ex = _ExFake()
    b = _bin(ex)
    s = b.colocar_stop("SOL/USDT", "LONG", 95.0, "k2", qty=0.1)
    ex.ordens[s["id"]]["info"]["algoStatus"] = "FINISHED"      # disparou
    assert b.cancelar("SOL/USDT", s["id"], condicional=True) is False
    novo = b.mover_stop("SOL/USDT", s, 97.0, "k3")             # e o mover não quebra por isso
    assert novo["gatilho"] == 97.0


def test_cancelar_condicional_vai_ao_servico_de_algo():
    ex = _ExFake()
    b = _bin(ex)
    s = b.colocar_stop("SOL/USDT", "LONG", 95.0, "k4", qty=0.1)
    assert b.cancelar("SOL/USDT", s["id"]) is False             # sem `trigger`: não acha
    assert ex.ordens[s["id"]]["info"]["algoStatus"] == "NEW"
    assert b.cancelar("SOL/USDT", s["id"], condicional=True) is True


def test_fechar_mercado_vai_reduce_only_do_lado_que_fecha():
    ex = _ExFake()
    ex.posicao = 0.2
    b = _bin(ex)
    b.fechar_mercado("SOL/USDT", "LONG", 0.2, "x9")
    b.fechar_mercado("SOL/USDT", "SHORT", 0.2, "x10")
    c1, c2 = _creates(ex)
    assert c1[2] == "market" and c1[3] == "sell" and c1[6].get("reduceOnly") is True
    assert c2[3] == "buy" and c2[6].get("reduceOnly") is True


def test_abrir_mercado_mede_o_teto_no_preco_de_referencia():
    ex = _ExFake(mark=100.5)                    # o mark andou depois das guardas
    b = _bin(ex, teto=300.0)
    o = b.abrir_mercado("SOL/USDT", "LONG", 2.99, "e9", ref_preco=100.0)   # 299 no preço medido
    assert o["client_oid"] == "e9"
    with pytest.raises(C.AcimaDoTeto):
        b.abrir_mercado("SOL/USDT", "LONG", 2.99, "e10")                    # 300,5 no mark: passa


def test_cancelar_tudo_pega_normais_e_condicionais():
    ex = _ExFake()
    b = _bin(ex)
    b.colocar_limite_post_only("SOL/USDT", "LONG", 0.1, 90.0, "ct1")
    b.colocar_stop("SOL/USDT", "LONG", 85.0, "ct2", qty=0.1)
    assert b.cancelar_tudo("SOL/USDT") == 2
    assert b.ordens_abertas("SOL/USDT") == []


# ------------------------------------------------------------------ preparação

def test_preparar_simbolo_isola_aplica_lev_e_cacheia():
    ex = _ExFake()
    b = _bin(ex)
    assert b.preparar_simbolo("SOL/USDT", 5.7) == 5
    b.preparar_simbolo("SOL/USDT", 5)
    assert [c for c in ex.chamadas if c[0] == "set_leverage"] == [("set_leverage", 5, "SOL/USDT:USDT")]
    b._preparados.clear()                                    # margem já isolada: -4046 não é erro
    b.preparar_simbolo("SOL/USDT", 7)
    assert ex.lev["SOL/USDT:USDT"] == 7


# ------------------------------------------------------------------ leitura

def test_saldo_posicoes_fills_income_normalizados():
    b = _bin()
    # `carteira` e `equity` vêm dos campos da Binance, não de somar `total` com `unrealized`:
    # o `total` do ccxt aqui JÁ inclui os 5 de não realizado, e somar de novo daria 210.
    assert b.saldo() == {"livre": 200.0, "total": 205.0, "unrealized": 5.0,
                         "carteira": 200.0, "equity": 205.0}
    assert b.hedge() is False
    b.ex.hedge = True
    assert b.hedge() is True
    b.ex.fapiPrivateGetPositionSideDual = lambda params=None: (_ for _ in ()).throw(ConnectionError("x"))
    assert b.hedge() is None                                 # não leu: quem diz é a primeira ordem
    (p,) = b.posicoes()
    assert (p["simbolo"], p["direcao"], p["qty"], p["liq"], p["margem_modo"]) == ("SOL/USDT", "LONG", 0.08, 58.15, "isolated")
    (f,) = b.fills("SOL/USDT")
    assert f["taxa"] == pytest.approx(0.00230144) and f["maker"] is False and f["ts"].tz is None
    (i,) = b.income("SOL/USDT")
    assert i["tipo"] == "COMMISSION" and i["valor"] == pytest.approx(-0.00230144)


# ------------------------------------------------------------------ contrato com a Binance (revisão de 26/11)

def test_trailing_confere_a_ativacao_que_a_binance_gravou():
    ex = _ExFake()
    o = _bin(ex).colocar_trailing("SOL/USDT", "LONG", 0.1, 105.0, 1.5, "tr5")
    assert o["ativacao"] == 105.0 and ex.ordens[o["id"]]["info"]["algoStatus"] == "NEW"


def test_trailing_gravado_com_outra_ativacao_e_cancelado_e_recusado():
    """Se a Binance ativar o trailing no preço de agora (o padrão dela sem o campo certo), ele
    seguiria uma posição ainda não armada e a fecharia de madrugada. Não fica."""
    ex = _ExFake()
    ex.ativacao_gravada = 100.0
    with pytest.raises(C.OrdemRecusada, match="ativação"):
        _bin(ex).colocar_trailing("SOL/USDT", "LONG", 0.1, 105.0, 1.5, "tr6")
    (o,) = [x for x in ex.ordens.values() if x["clientOrderId"] == "tr6"]
    assert o["info"]["algoStatus"] == "CANCELED"


def test_id_repetido_de_condicional_devolve_a_mesma_ordem():
    """`-20132` (Algo) quer dizer o mesmo que o `-4116`: a ordem já foi. O `_stop_da_ordem`
    reenvia o mesmo id de propósito; virar recusa cancelava uma entrada protegida."""
    ex = _ExFake()
    b = _bin(ex)
    s1 = b.colocar_stop("SOL/USDT", "LONG", 95.0, "dup1", qty=0.1)
    s2 = b.colocar_stop("SOL/USDT", "LONG", 95.0, "dup1", qty=0.1)
    assert s2["id"] == s1["id"] and len(_creates(ex)) == 2


def test_chave_recusada_depois_do_primeiro_acesso_nao_vira_rede():
    """O ccxt põe o `-2015` em DDoSProtection (NetworkError) depois do primeiro acesso: sem
    tradução, um IP que mudou aparecia como envio incerto e disparava uma busca inútil."""
    ex = _ExFake()
    b = _bin(ex)
    corpo = 'binanceusdm {"code":-2015,"msg":"Invalid API-key, IP, or permissions for action."}'
    ex.erros["create_order"] = [ccxt.DDoSProtection(corpo)]
    with pytest.raises(C.ChaveRecusada, match="IP"):
        b.colocar_stop("SOL/USDT", "LONG", 95.0, "k1", qty=0.1)
    assert not [c for c in ex.chamadas if c[0] == "fetch_order"]
    ex.erros["fetch_balance"] = [ccxt.AuthenticationError(corpo)]          # e na leitura também
    with pytest.raises(C.ChaveRecusada):
        b.saldo()


def test_relogio_fora_ressincroniza_e_repete_uma_vez():
    ex = _ExFake()
    b = _bin(ex)
    antes = ex.relogio_sincronizado
    nonce = 'binanceusdm {"code":-1021,"msg":"Timestamp for this request is outside of the recvWindow."}'
    ex.erros["create_order"] = [ccxt.InvalidNonce(nonce)]
    o = b.colocar_stop("SOL/USDT", "LONG", 95.0, "n1", qty=0.1)
    assert o["status"] == "aberta" and ex.relogio_sincronizado == antes + 1
    assert len(_creates(ex)) == 2
    ex.erros["create_order"] = [ccxt.InvalidNonce(nonce), ccxt.InvalidNonce(nonce)]
    with pytest.raises(C.OrdemRecusada, match="relógio"):
        b.colocar_stop("SOL/USDT", "LONG", 95.0, "n2", qty=0.1)
    assert not [c for c in ex.chamadas if c[0] == "fetch_order"]           # recusa certa: sem busca


def test_limite_de_taxa_para_tudo_pelo_retry_after():
    ex = _ExFake()
    b = _bin(ex)
    ex.last_response_headers = {"Retry-After": "30"}
    ex.erros["create_order"] = [ccxt.DDoSProtection('binanceusdm 418 I\'m a teapot {"code":-1003}')]
    with pytest.raises(C.LimiteDeTaxa):
        b.colocar_stop("SOL/USDT", "LONG", 95.0, "t1", qty=0.1)
    assert not [c for c in ex.chamadas if c[0] == "fetch_order"]           # sem busca durante o ban
    n = len(ex.chamadas)
    with pytest.raises(C.LimiteDeTaxa):
        b.saldo()                                                       # nada vai à Binance
    assert len(ex.chamadas) == n
    assert b.preco_valido("SOL/USDT", 95.123) == 95.12                  # o que é local continua
    assert 25 < b._pausa_ate - __import__("time").monotonic() <= 30
    b._pausa_ate = 0.0
    assert b.saldo()["carteira"] == 200.0


def test_finished_so_e_preenchida_com_quantidade_executada():
    def o(**info):
        return {"id": "9", "clientOrderId": "x", "symbol": "SOL/USDT:USDT", "status": "closed",
                "side": "sell", "type": "market",
                "info": {"algoId": "9", "algoStatus": "FINISHED", "orderType": "STOP_MARKET", **info}}
    assert C.normalizar_ordem(o(actualQty="0"))["status"] == "cancelada"
    n = C.normalizar_ordem(o(actualQty="0.5", actualOrderId="77"))
    assert n["status"] == "preenchida" and n["preenchido"] == 0.5
    assert C.normalizar_ordem(o())["status"] == "preenchida"            # sem o campo: o de antes


def test_income_vem_em_janelas_de_sete_dias_filtrado_por_tipo():
    """Só com `startTime` a Binance não garante mais que 7 dias: o funding de uma posição de
    swing saía cortado sem aviso."""
    import time as _t
    ex = _ExFake()
    b = _bin(ex)
    desde = int(_t.time() * 1000) - 20 * 86400 * 1000
    linhas = b.income("SOL/USDT", desde, tipo="FUNDING_FEE")
    assert len(ex.income_chamadas) == 3
    for c in ex.income_chamadas:
        assert c["incomeType"] == "FUNDING_FEE" and c["endTime"] - c["startTime"] < 7 * 86400 * 1000
    assert 19 <= len(linhas) <= 21 and all(x["tipo"] == "FUNDING_FEE" for x in linhas)


def test_multi_ativos_e_lido_e_falha_de_leitura_e_none():
    ex = _ExFake()
    b = _bin(ex)
    assert b.multi_ativos() is False
    ex.multi = True
    assert b.multi_ativos() is True
    ex.erros["multi"] = [ConnectionError("x")]
    assert b.multi_ativos() is None
    assert C.Papel(lambda s: 100.0).multi_ativos() is False


def test_mercados_recarregam_uma_vez_por_dia():
    ex = _ExFake()
    b = _bin(ex)
    b.arredondar("SOL/USDT", 0.1)
    assert ex.mercados_carregados == 0                  # a fábrica acabou de carregar
    b._mercados_em -= b.RECARGA_MERCADOS_S + 1
    b.arredondar("SOL/USDT", 0.1)
    b.arredondar("SOL/USDT", 0.1)
    assert ex.mercados_carregados == 1


# ------------------------------------------------------------------ chave (regra 8)

@pytest.mark.parametrize("campo,valor,motivo", [
    ("enableSpotAndMarginTrading", True, "spot e margem"),
    ("enableMargin", True, "margem"),
    ("enablePortfolioMarginTrading", True, "portfolio margin"),
    ("enableVanillaOptions", True, "opções"),
    ("enableWithdrawals", True, "saque"),
    ("enableInternalTransfer", True, "transferência"),
    ("permitsUniversalTransfer", True, "transferência"),
    ("ipRestrict", False, "IP"),
    ("enableFutures", False, "futuros"),
])
def test_chave_real_perigosa_e_recusada(campo, valor, motivo):
    ex = _ExFake()
    ex.restricoes[campo] = valor
    with pytest.raises(C.ChaveInsegura, match=motivo):
        _bin(ex, modo="binance").verificar_chave()


def test_chave_real_correta_passa_e_demo_nao_e_verificavel():
    assert _bin(modo="binance").verificar_chave()["ok"] is True
    assert _bin(modo="demo").verificar_chave()["verificavel"] is False


# ------------------------------------------------------------------ fábrica

def test_sem_config_e_papel():
    c = C.obter({}, env={}, preco_fn=lambda a: 100.0)
    assert isinstance(c, C.Papel) and c.real is False


def test_modo_desconhecido_recusa():
    with pytest.raises(C.ErroCorretora):
        C.obter({"corretora": "bybit"}, env={}, preco_fn=lambda a: 1.0)


def test_binance_sem_chave_no_ambiente_recusa():
    with pytest.raises(C.ErroCorretora, match="BINANCE_KEY"):
        C.obter({"corretora": "binance"}, env={"BINANCE_DEMO_KEY": "a", "BINANCE_DEMO_SECRET": "b"})


def test_binance_com_chave_que_saca_nao_abre_mas_fecha():
    """Regra 8 (revisão de 26/11): recusar SUBIR deixava a posição que já existe sem ninguém
    para fechá-la. A chave insegura barra a entrada; fechar, stop e pânico seguem."""
    ex = _ExFake()
    ex.restricoes["enableWithdrawals"] = True
    c = C.obter({"corretora": "binance"}, env={"BINANCE_KEY": "a", "BINANCE_SECRET": "b"},
                fabrica_ccxt=lambda *a: ex)
    assert "saque" in c.bloqueio_entrada
    with pytest.raises(C.ChaveInsegura, match="saque"):
        c.abrir_mercado("SOL/USDT", "LONG", 0.1, "e1")
    with pytest.raises(C.ChaveInsegura):
        c.colocar_limite_post_only("SOL/USDT", "LONG", 0.1, 90.0, "e2")
    assert not _creates(ex)
    ex.posicao = 0.1
    c.colocar_stop("SOL/USDT", "LONG", 95.0, "s1", qty=0.1)
    assert c.fechar_mercado("SOL/USDT", "LONG", 0.1, "f1")["status"] == "preenchida"
    ex.restricoes["enableWithdrawals"] = False                  # consertada no site
    assert c.conferir_chave() is None and c.bloqueio_entrada is None
    assert c.abrir_mercado("SOL/USDT", "LONG", 0.1, "e3")["client_oid"] == "e3"


def _obter_binance(ex, **env):
    return C.obter({"corretora": "binance", "BINANCE_CHAVE_SEM_IP": "1", "chave_sem_ip": "1"},
                   env={"BINANCE_KEY": "a", "BINANCE_SECRET": "b", **env},
                   fabrica_ccxt=lambda *a: ex)


def test_chave_sem_ip_so_e_aceita_pelo_ambiente_do_servidor():
    """[LIVE-11] Decisão do dono em 26/11: IP de saída dinâmico. A linha no corretora.env aceita
    a chave sem restrição de IP; a config do banco (gravável por HTTP) não, mesmo com o nome igual."""
    ex = _ExFake()
    ex.restricoes["ipRestrict"] = False
    c = _obter_binance(ex)                                       # só a config pede: recusa
    assert "restrição de IP" in c.bloqueio_entrada and c.aviso_chave is None
    for valor in ("0", "true", "sim", " ", "yes"):               # só "1" liga
        assert "restrição de IP" in _obter_binance(ex, BINANCE_CHAVE_SEM_IP=valor).bloqueio_entrada
    c = _obter_binance(ex, BINANCE_CHAVE_SEM_IP="1")
    assert c.bloqueio_entrada is None and "sem restrição de IP" in c.aviso_chave
    assert c.abrir_mercado("SOL/USDT", "LONG", 0.1, "e1")["client_oid"] == "e1"
    ex.restricoes["ipRestrict"] = True                           # o dono prendeu a IP depois
    assert c.conferir_chave() is None and c.aviso_chave is None


@pytest.mark.parametrize("campo,valor,motivo", [
    ("enableWithdrawals", True, "saque"),
    ("enableInternalTransfer", True, "transferência"),
    ("permitsUniversalTransfer", True, "transferência"),
    ("enableSpotAndMarginTrading", True, "spot e margem"),
    ("enableFutures", False, "futuros"),
])
def test_chave_sem_ip_aceita_nao_afrouxa_mais_nada(campo, valor, motivo):
    ex = _ExFake()
    ex.restricoes["ipRestrict"] = False
    ex.restricoes[campo] = valor
    c = _obter_binance(ex, BINANCE_CHAVE_SEM_IP="1")
    assert motivo in c.bloqueio_entrada and "IP" not in c.bloqueio_entrada
    with pytest.raises(C.ChaveInsegura, match=motivo):
        c.abrir_mercado("SOL/USDT", "LONG", 0.1, "e1")


def test_conferencia_que_falha_por_rede_tambem_barra_a_entrada():
    ex = _ExFake()
    def cai():
        raise ccxt.RequestTimeout("timeout")
    ex.sapiGetAccountApiRestrictions = cai
    c = C.obter({"corretora": "binance"}, env={"BINANCE_KEY": "a", "BINANCE_SECRET": "b"},
                fabrica_ccxt=lambda *a: ex)
    assert "não foi conferida" in c.bloqueio_entrada


def test_mensagem_de_erro_sai_sem_assinatura_e_sem_ip():
    ex = _ExFake()
    b = _bin(ex)
    ex.erros["fetch_balance"] = [ccxt.NetworkError(
        "binanceusdm GET https://fapi.binance.com/fapi/v2/balance?timestamp=1&recvWindow=10000"
        "&signature=9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08 timeout")]
    with pytest.raises(ccxt.NetworkError) as e:
        b.saldo()
    assert "9f86d081" not in str(e.value) and "signature=***" in str(e.value)
    ex.erros["fetch_balance"] = [ccxt.AuthenticationError(
        'binanceusdm {"code":-2015,"msg":"Invalid API-key, IP, or permissions for action, '
        'request ip: 203.0.113.9"}')]
    with pytest.raises(C.ChaveRecusada) as e:
        b.saldo()
    assert "203.0.113.9" not in str(e.value)


def test_demo_le_as_chaves_de_demo_e_o_teto_da_config():
    vistos = {}

    def fab(modo, k, s):
        vistos.update(modo=modo, k=k, s=s)
        return _ExFake()

    c = C.obter({"corretora": "demo", "corretora_nocional_max": "150", "corretora_dry_run": "1"},
                env={"BINANCE_DEMO_KEY": "kd", "BINANCE_DEMO_SECRET": "sd", "BINANCE_KEY": "kr"},
                fabrica_ccxt=fab)
    assert vistos == {"modo": "demo", "k": "kd", "s": "sd"}
    assert c.nocional_max == 150.0 and c.dry_run is True


# ------------------------------------------------------------------ papel

def test_papel_preenche_no_preco_ao_vivo_e_nao_toca_rede():
    c = C.Papel(lambda a: {"SOL/USDT": 72.5}[a], saldo_fn=lambda: 10_000.0)
    o = c.abrir_mercado("SOL/USDT", "LONG", 1.0, "pp1")
    assert (o["preco_medio"], o["status"], o["lado"]) == (72.5, "preenchida", "buy")
    s = c.colocar_stop("SOL/USDT", "LONG", 70.0, "pp2", qty=1.0)
    assert s["id"].startswith("papel-sl-") and s["gatilho"] == 70.0 and s["lado"] == "sell"
    assert c.saldo()["total"] == 10_000.0 and c.ordens_abertas() == [] and c.posicoes() == []


# ------------------------------------------------------------------ prova contra o demo real

@pytest.mark.skipif(os.environ.get("RODAR_DEMO") != "1" or not os.environ.get("BINANCE_DEMO_KEY"),
                    reason="prova ao vivo: RODAR_DEMO=1 e BINANCE_DEMO_KEY/SECRET no ambiente")
class TestDemoAoVivo:
    """O roteiro do dublê contra a Binance DEMO de verdade (dinheiro fictício, centavos de taxa).
    Deixa a conta como achou: sem posição e sem ordem em SOL."""

    S = "SOL/USDT"

    @pytest.fixture
    def b(self):
        c = C.obter({"corretora": "demo", "corretora_nocional_max": "50"})
        c.cancelar_tudo(self.S)
        yield c
        c.cancelar_tudo(self.S)
        for p in c.posicoes():
            if p["simbolo"] == self.S:
                c.fechar_mercado(self.S, p["direcao"], p["qty"], f"limpa-{pd.Timestamp.now():%H%M%S%f}")

    @staticmethod
    def _espera(cond, segundos=6.0):
        """A leitura da Binance atrasa ~1,5 s depois de uma escrita (regra 4 do módulo)."""
        import time as _t
        fim = _t.monotonic() + segundos
        while _t.monotonic() < fim:
            if cond():
                return True
            _t.sleep(0.5)
        return cond()

    def test_roteiro(self, b):
        sufixo = pd.Timestamp.now().strftime("%H%M%S%f")
        mark = b.marks([self.S])[self.S]
        b.preparar_simbolo(self.S, 5)
        # post-only que cruzaria: recusado
        with pytest.raises(C.OrdemRecusada):
            b.colocar_limite_post_only(self.S, "LONG", 0.1, mark * 1.02, f"t-cruza-{sufixo}")
        # entrada que descansa + SL reduce-only pré-colocado
        q, p = b.arredondar(self.S, 0.1, mark * 0.9)
        lim = b.colocar_limite_post_only(self.S, "LONG", q, p, f"t-lim-{sufixo}")
        sl0 = b.colocar_stop(self.S, "LONG", mark * 0.85, f"t-sl0-{sufixo}", qty=q)
        assert {lim["client_oid"], sl0["client_oid"]} <= {o["client_oid"] for o in b.ordens_abertas(self.S)}
        # idempotência real
        assert b.colocar_limite_post_only(self.S, "LONG", q, p, f"t-lim-{sufixo}")["id"] == lim["id"]
        # cancelar condicional: status cru
        # id repetido de CONDICIONAL: a mesma ordem volta (o código de erro é o do serviço Algo)
        assert b.colocar_stop(self.S, "LONG", mark * 0.85, f"t-sl0-{sufixo}", qty=q)["id"] == sl0["id"]
        assert b.cancelar(self.S, sl0["id"], condicional=True) is True
        assert self._espera(lambda: b.buscar(self.S, f"t-sl0-{sufixo}", condicional=True)["status"] == "cancelada")
        assert b.cancelar(self.S, sl0["id"], condicional=True) is False     # já terminada: não levanta
        assert b.cancelar(self.S, lim["id"]) is True
        # posição mínima com SL closePosition, TP e trailing; mover o stop
        q, _ = b.arredondar(self.S, 6.5 / mark)
        e = b.abrir_mercado(self.S, "LONG", q, f"t-ent-{sufixo}")
        assert e["preco_medio"] and e["status"] == "preenchida"
        sl = b.colocar_stop(self.S, "LONG", mark * 0.97, f"t-sl-{sufixo}")
        tp = b.colocar_tp(self.S, "LONG", mark * 1.05, q, f"t-tp-{sufixo}")
        tr = b.colocar_trailing(self.S, "LONG", q, mark * 1.03, 1.5, f"t-tr-{sufixo}")
        assert tr["ativacao"] == b.preco_valido(self.S, mark * 1.03)       # o nome do campo vale
        sl2 = b.mover_stop(self.S, sl, mark * 0.975, f"t-sl2-{sufixo}")
        abertas = lambda: {o["client_oid"] for o in b.ordens_abertas(self.S)}
        assert self._espera(lambda: {sl2["client_oid"], tp["client_oid"], tr["client_oid"]} <= abertas()
                            and sl["client_oid"] not in abertas())
        # fecha: o SL closePosition some sozinho; TP e trailing reduce-only ficam órfãos
        f = b.fechar_mercado(self.S, "LONG", q, f"t-fec-{sufixo}")
        assert f["status"] == "preenchida" and f["reduce_only"]
        assert self._espera(lambda: not any(p["simbolo"] == self.S for p in b.posicoes()))
        # sl2 é reduce-only com qty: fica órfão como TP e trailing; a reconciliação limpa
        assert self._espera(lambda: {tp["client_oid"], tr["client_oid"], sl2["client_oid"]} <= abertas())
        b.cancelar_tudo(self.S)
        assert self._espera(lambda: b.ordens_abertas(self.S) == [])
        assert any(f["ordem_id"] == e["id"] for f in b.fills(self.S))


# ------------------------------------------------------------------ [LIVE-13] revisão de dinheiro de 26/11

def test_trailing_sem_ativacao_devolvida_e_cancelado():
    """Enviada a ativação e nada volta (nem na releitura): não dá para saber onde ativa. Fica o
    stop fixo; o trailing sai."""
    ex = _ExFake()
    ex.sem_ativacao = True
    with pytest.raises(C.OrdemRecusada, match="não devolvida"):
        _bin(ex).colocar_trailing("SOL/USDT", "LONG", 0.1, 105.0, 1.5, "tr9")
    (o,) = [x for x in ex.ordens.values() if x["clientOrderId"] == "tr9"]
    assert o["info"]["algoStatus"] == "CANCELED"


def test_limite_de_requisicoes_deixa_passar_stop_fechamento_e_cancelamento():
    """429 por excesso de leitura parava TUDO, inclusive o stop de uma posição nova: ela ficava
    sem stop até o fim da pausa. Só o ban de IP (418) para tudo."""
    ex = _ExFake()
    b = _bin(ex)
    ex.erros["fetch_balance"] = [ccxt.RateLimitExceeded(
        'binanceusdm {"code":-1003,"msg":"Too many requests; current limit is 2400 per minute."}')]
    with pytest.raises(C.LimiteDeTaxa, match="só stop"):
        b.saldo()
    n = len(ex.chamadas)
    with pytest.raises(C.LimiteDeTaxa):
        b.saldo()                                                       # leitura: não vai
    with pytest.raises(C.LimiteDeTaxa):
        b.abrir_mercado("SOL/USDT", "LONG", 0.1, "e1")                  # entrada: não vai
    assert len(ex.chamadas) == n
    ex.posicao = 0.1
    s = b.colocar_stop("SOL/USDT", "LONG", 95.0, "s1", qty=0.1)         # stop: vai
    assert s["client_oid"] == "s1"
    assert b.fechar_mercado("SOL/USDT", "LONG", 0.1, "f1")["status"] == "preenchida"
    assert b.cancelar("SOL/USDT", s["id"], condicional=True) is not None
