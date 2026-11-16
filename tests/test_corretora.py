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
        self.restricoes = {"enableWithdrawals": False, "enableInternalTransfer": False,
                           "permitsUniversalTransfer": False, "ipRestrict": True, "enableFutures": True}
        self.relogio_sincronizado = 0

    # ---- mercado
    def market(self, s):
        return {"id": s.split("/")[0] + "USDT", "limits": {"amount": {"min": 0.01}, "cost": {"min": 5.0}}}

    def amount_to_precision(self, s, q):
        return str(int(float(q) * 100) / 100)           # trunca, como o ccxt (TRUNCATE)

    def price_to_precision(self, s, p):
        return f"{float(p):.2f}"

    def load_time_difference(self):
        self.relogio_sincronizado += 1

    def fetch_mark_prices(self, simbolos):
        return {s: {"markPrice": self.mark} for s in simbolos}

    # ---- ordens
    def create_order(self, s, tipo, lado, qty, preco, params):
        self.chamadas.append(("create_order", s, tipo, lado, qty, preco, dict(params)))
        coid = params["newClientOrderId"]
        if self.timeout_perde:
            raise ccxt.RequestTimeout("timeout")
        if coid in self.coids:                                         # demo: -4116
            raise ccxt.InvalidOrder('binanceusdm {"code":-4116,"msg":"ClientOrderId is duplicated."}')
        condicional = tipo.upper() in ("STOP_MARKET", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET")
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
                    "triggerPrice": params.get("stopPrice") or params.get("activationPrice")}
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
        if not o:
            raise ccxt.OrderNotFound('{"code":-2011,"msg":"Unknown order sent."}')
        chave = "algoStatus" if "algoId" in o["info"] else "status"
        if o["info"][chave] != "NEW":
            raise ccxt.OrderNotFound('{"code":-2011,"msg":"Unknown order sent."}')
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
        return {"USDT": {"free": 200.0, "total": 205.0}, "info": {"totalUnrealizedProfit": "5.0"}}

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
    assert (tr[2], tr[3], tr[6]["callbackRate"], tr[6]["activationPrice"]) == ("TRAILING_STOP_MARKET", "buy", 1.5, "95.00")


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
    assert b.saldo() == {"livre": 200.0, "total": 205.0, "unrealized": 5.0}
    (p,) = b.posicoes()
    assert (p["simbolo"], p["direcao"], p["qty"], p["liq"], p["margem_modo"]) == ("SOL/USDT", "LONG", 0.08, 58.15, "isolated")
    (f,) = b.fills("SOL/USDT")
    assert f["taxa"] == pytest.approx(0.00230144) and f["maker"] is False and f["ts"].tz is None
    (i,) = b.income("SOL/USDT")
    assert i["tipo"] == "COMMISSION" and i["valor"] == pytest.approx(-0.00230144)


# ------------------------------------------------------------------ chave (regra 8)

@pytest.mark.parametrize("campo,valor,motivo", [
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


def test_binance_com_chave_que_saca_nao_sobe():
    ex = _ExFake()
    ex.restricoes["enableWithdrawals"] = True
    with pytest.raises(C.ChaveInsegura):
        C.obter({"corretora": "binance"}, env={"BINANCE_KEY": "a", "BINANCE_SECRET": "b"},
                fabrica_ccxt=lambda *a: ex)


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
        assert b.cancelar(self.S, sl0["id"], condicional=True) is True
        assert self._espera(lambda: b.buscar(self.S, f"t-sl0-{sufixo}", condicional=True)["status"] == "cancelada")
        assert b.cancelar(self.S, lim["id"]) is True
        # posição mínima com SL closePosition, TP e trailing; mover o stop
        q, _ = b.arredondar(self.S, 6.5 / mark)
        e = b.abrir_mercado(self.S, "LONG", q, f"t-ent-{sufixo}")
        assert e["preco_medio"] and e["status"] == "preenchida"
        sl = b.colocar_stop(self.S, "LONG", mark * 0.97, f"t-sl-{sufixo}")
        tp = b.colocar_tp(self.S, "LONG", mark * 1.05, q, f"t-tp-{sufixo}")
        tr = b.colocar_trailing(self.S, "LONG", q, mark * 1.03, 1.5, f"t-tr-{sufixo}")
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
