# -*- coding: utf-8 -*-
"""[LIVE-3][LIVE-4] A conta que opera em corretora (`execucao.py`), contra uma corretora FALSA.

O dublê aqui é da INTERFACE do adapter (`corretora.BinanceUSDM`), não do ccxt: o adapter tem a
suíte dele (`test_corretora.py`, com dublê do ccxt e prova ao vivo no demo). O que se testa
aqui é a regra do livro: o que ele grava, quando, e o que ele se recusa a fazer.

A corretora falsa modela uma conta de futuros one-way: posição por ativo, ordens normais e
condicionais, negócios (fills) com taxa, carteira que anda com o realizado. Os testes mexem
nela pelo lado de fora (`encher`, `disparar`, `liquidar`) para simular o que acontece LÁ
enquanto o bot não está olhando, que é exatamente o que a reconciliação existe para cobrir.
"""
import json

import pandas as pd
import pytest

import corretora as C
import db
import execucao
import simulador
from tests.conftest import semear_sinal


class Falsa:
    nome = "demo"
    real = True
    TAKER, MAKER = 0.0005, 0.0002

    def __init__(self, carteira=1000.0, preco=100.0):
        self.preco = {}
        self.preco_padrao = preco
        self.pos = {}                # ativo -> {direcao, qty, entrada, alavancagem}
        self.ordens = {}             # id -> ordem
        self.negocios = []
        self.renda = []
        self.carteira = carteira
        self.seq = 0
        self.levs = {}
        self.falhar = {}             # método -> exceção (levantada enquanto estiver aqui)
        self.falhar_uma = {}         # método -> exceção (levantada uma vez)
        self.chamadas = []
        self.moeda_taxa = "USDT"
        self.modo_hedge = False
        self.dry_run = False
        self.perde_resposta = set()  # método -> a ordem CHEGA e a resposta se perde (uma vez)

    # ---------------------------------------------------------------- infraestrutura do dublê
    def _passa(self, nome):
        self.chamadas.append(nome)
        if nome in self.falhar_uma:
            raise self.falhar_uma.pop(nome)
        if nome in self.falhar:
            raise self.falhar[nome]

    def _id(self):
        self.seq += 1
        return str(1000 + self.seq)

    def _mark(self, ativo):
        return self.preco.get(ativo, self.preco_padrao)

    @staticmethod
    def _trunca(qty):
        """O que a corretora faz com a quantidade que recebe: corta no lote (0,001) pelo TEXTO
        do número, sem folga. `0.062 - 0.021` chega como 0.040999999999999995 e vira 0,040. Quem
        manda quantidade com resíduo de ponto flutuante perde um lote aqui, como perderia lá."""
        from decimal import Decimal, ROUND_DOWN
        return float(Decimal(repr(float(qty))).quantize(Decimal("0.001"), rounding=ROUND_DOWN))

    def _nova(self, ativo, lado, tipo, qty, coid, condicional=False, **kw):
        if self.dry_run:                            # monta e não envia: nada muda na conta
            return {"id": f"dry-{coid}", "client_oid": coid, "simbolo": ativo, "lado": lado,
                    "tipo": tipo, "condicional": condicional, "status": "dry_run", "qty": qty,
                    "preenchido": 0.0, "preco": None, "preco_medio": None,
                    "gatilho": kw.get("gatilho"), "reduce_only": False, "close_position": False,
                    "ts": pd.Timestamp.now()}
        for o in self.ordens.values():              # idempotência: mesmo id nosso, mesma ordem
            if o["client_oid"] == coid:
                return dict(o)
        qty = self._trunca(qty)
        if qty <= 0:
            raise C.AbaixoDoMinimo(f"{ativo}: qty menor que um lote")
        o = {"id": self._id(), "client_oid": coid, "simbolo": ativo, "lado": lado, "tipo": tipo,
             "condicional": condicional, "status": "aberta", "qty": qty, "preenchido": 0.0,
             "preco": None, "preco_medio": None, "gatilho": None, "reduce_only": False,
             "close_position": False, "ts": pd.Timestamp.now()}
        o.update(kw)
        self.ordens[o["id"]] = o
        return dict(o)

    def _negocio(self, ativo, lado, qty, preco, ordem_id, taxa_frac, pnl=None):
        nocional = qty * preco
        taxa = nocional * taxa_frac
        if self.moeda_taxa != "USDT":
            taxa = taxa / 600.0                     # "em BNB": número muito menor, outra moeda
        else:
            self.carteira -= taxa
        self.seq += 1
        self.negocios.append({"id": str(5000 + self.seq), "ordem_id": str(ordem_id), "simbolo": ativo,
                              "lado": lado, "qty": qty, "preco": preco, "taxa": taxa,
                              "taxa_moeda": self.moeda_taxa, "maker": taxa_frac == self.MAKER,
                              "pnl_realizado": pnl, "ts": pd.Timestamp.now()})

    def _abre(self, ativo, direcao, qty, preco, ordem_id, taxa_frac):
        p = self.pos.get(ativo)
        if p and p["direcao"] == direcao:
            tot = p["qty"] + qty
            p["entrada"] = (p["entrada"] * p["qty"] + preco * qty) / tot
            p["qty"] = tot
        else:
            self.pos[ativo] = {"direcao": direcao, "qty": qty, "entrada": preco,
                               "alavancagem": self.levs.get(ativo, 1)}
        self._negocio(ativo, C._ABRE[direcao], qty, preco, ordem_id, taxa_frac)

    def _reduz(self, ativo, qty, preco, ordem_id, taxa_frac=None):
        p = self.pos.get(ativo)
        if not p:
            return 0.0
        q = min(qty, p["qty"])
        d = 1 if p["direcao"] == "LONG" else -1
        pnl = d * (preco - p["entrada"]) * q
        self.carteira += pnl
        self._negocio(ativo, C._FECHA[p["direcao"]], q, preco, ordem_id,
                      self.TAKER if taxa_frac is None else taxa_frac, pnl)
        p["qty"] = round(p["qty"] - q, 9)           # a corretora guarda a quantidade exata
        if p["qty"] <= 1e-12:
            del self.pos[ativo]
        return q

    # ---------------------------------------------------------------- o mundo de fora
    def por_coid(self, trecho):
        return [o for o in self.ordens.values() if trecho in (o["client_oid"] or "")]

    def abertas(self, tipo=None):
        return [o for o in self.ordens.values()
                if o["status"] in ("aberta", "parcial") and (tipo is None or o["tipo"] == tipo)]

    def encher(self, ordem_id, qty=None):
        """A ordem limite que descansava encheu (toda, ou `qty`)."""
        o = self.ordens[ordem_id]
        q = o["qty"] - o["preenchido"] if qty is None else qty
        direcao = "LONG" if o["lado"] == "buy" else "SHORT"
        self._abre(o["simbolo"], direcao, q, o["preco"], o["id"], self.MAKER)
        o["preenchido"] += q
        o["preco_medio"] = o["preco"]
        o["status"] = "preenchida" if o["preenchido"] >= o["qty"] - 1e-12 else "parcial"

    def disparar(self, ordem_id, preco=None):
        """A condicional (stop, alvo, trailing) disparou LÁ. O negócio sai com o id de OUTRA
        ordem, como na Binance: a condicional é do serviço Algo e gera uma ordem a mercado."""
        o = self.ordens[ordem_id]
        o["status"] = "disparada"
        return self._reduz(o["simbolo"], o["qty"], preco if preco is not None else o["gatilho"],
                           self._id())

    def liquidar(self, ativo, preco):
        oid = self._id()
        self.ordens[oid] = {"id": oid, "client_oid": "autoclose-123456", "simbolo": ativo,
                            "lado": C._FECHA[self.pos[ativo]["direcao"]], "tipo": "LIMIT",
                            "condicional": False, "status": "preenchida", "qty": self.pos[ativo]["qty"],
                            "preenchido": self.pos[ativo]["qty"], "preco": preco, "preco_medio": preco,
                            "gatilho": None, "reduce_only": True, "close_position": False,
                            "ts": pd.Timestamp.now()}
        self._reduz(ativo, self.pos[ativo]["qty"], preco, oid)

    # ---------------------------------------------------------------- a interface do adapter
    def saldo(self):
        self._passa("saldo")
        unreal = sum((1 if p["direcao"] == "LONG" else -1) * (self._mark(a) - p["entrada"]) * p["qty"]
                     for a, p in self.pos.items())
        return {"livre": self.carteira, "total": self.carteira, "unrealized": unreal,
                "carteira": self.carteira, "equity": self.carteira + unreal}

    def hedge(self):
        return self.modo_hedge

    def multi_ativos(self):
        return getattr(self, "modo_multi", False)

    def posicoes(self):
        self._passa("posicoes")
        return [{"simbolo": a, "direcao": p["direcao"], "qty": p["qty"], "entrada": p["entrada"],
                 "mark": self._mark(a), "liq": None, "margem": None, "margem_modo": "isolated",
                 "alavancagem": p["alavancagem"], "unrealized": 0.0} for a, p in self.pos.items()]

    def ordens_abertas(self, simbolo=None):
        self._passa("ordens_abertas")
        return [dict(o) for o in self.abertas() if simbolo in (None, o["simbolo"])]

    def marks(self, simbolos):
        self._passa("marks")
        return {s: self._mark(s) for s in simbolos}

    def preparar_simbolo(self, simbolo, alavancagem):
        self._passa("preparar_simbolo")
        self.levs[simbolo] = int(alavancagem)
        return int(alavancagem)

    def preco_valido(self, simbolo, preco):
        return round(float(preco), 2)

    def arredondar(self, simbolo, qty, preco=None, reduz=False):
        q = int(float(qty) * 1000 + 1e-9) / 1000.0
        p = round(float(preco), 2) if preco is not None else None
        if q <= 0:
            raise C.AbaixoDoMinimo(f"{simbolo}: qty {qty} vira {q}")
        if not reduz and q * (p if p is not None else self._mark(simbolo)) < 5.0:
            raise C.AbaixoDoMinimo(f"{simbolo}: nocional abaixo de 5")
        return q, p

    def abrir_mercado(self, simbolo, direcao, qty, client_oid, ref_preco=None):
        self._passa("abrir_mercado")
        self.ref_preco = ref_preco
        o = self._nova(simbolo, C._ABRE[direcao], "MARKET", qty, client_oid)
        if o["status"] == "dry_run":
            return o
        if self.ordens[o["id"]]["status"] == "aberta":
            px = self._mark(simbolo)
            self._abre(simbolo, direcao, qty, px, o["id"], self.TAKER)
            self.ordens[o["id"]].update(status="preenchida", preenchido=qty, preco_medio=px)
        return dict(self.ordens[o["id"]])

    def fechar_mercado(self, simbolo, direcao, qty, client_oid):
        self._passa("fechar_mercado")
        # Reduce-only do lado que não fecha a posição é recusado como na Binance: fechar um LONG
        # mandando "SHORT" não pode "funcionar" aqui (revisão de testes de 26/11, mutação M24).
        if simbolo not in self.pos or self.pos[simbolo]["direcao"] != direcao:
            raise C.OrdemRecusada("binance -2022 ReduceOnly Order is rejected.")
        o = self._nova(simbolo, C._FECHA[direcao], "MARKET", qty, client_oid, reduce_only=True)
        if o["status"] == "dry_run":
            return o
        px = self._mark(simbolo)
        q = self._reduz(simbolo, o["qty"], px, o["id"])
        self.ordens[o["id"]].update(status="preenchida", preenchido=q, preco_medio=px)
        return dict(self.ordens[o["id"]])

    def colocar_limite_post_only(self, simbolo, direcao, qty, preco, client_oid):
        self._passa("colocar_limite_post_only")
        o = self._nova(simbolo, C._ABRE[direcao], "LIMIT", qty, client_oid, preco=preco)
        if "colocar_limite_post_only" in self.perde_resposta:
            self.perde_resposta.discard("colocar_limite_post_only")
            raise C.EnvioIncerto("a ordem chegou e a resposta se perdeu")
        return o

    def _cruzado(self, simbolo, direcao, gatilho, eh_tp):
        m, d = self._mark(simbolo), (1 if direcao == "LONG" else -1)
        return (m - gatilho) * d >= 0 if eh_tp else (gatilho - m) * d >= 0

    def colocar_stop(self, simbolo, direcao, gatilho, client_oid, qty=None):
        self._passa("colocar_stop")
        if self._cruzado(simbolo, direcao, gatilho, False):
            raise C.OrdemRecusada("binance -2021 Order would immediately trigger.")
        return self._nova(simbolo, C._FECHA[direcao], "STOP_MARKET", qty, client_oid, condicional=True,
                          gatilho=gatilho, reduce_only=True)

    def colocar_tp(self, simbolo, direcao, gatilho, qty, client_oid):
        self._passa("colocar_tp")
        if self._cruzado(simbolo, direcao, gatilho, True):
            raise C.OrdemRecusada("binance -2021 Order would immediately trigger.")
        return self._nova(simbolo, C._FECHA[direcao], "TAKE_PROFIT_MARKET", qty, client_oid,
                          condicional=True, gatilho=gatilho, reduce_only=True)

    def colocar_trailing(self, simbolo, direcao, qty, ativacao, callback_pct, client_oid):
        self._passa("colocar_trailing")
        return self._nova(simbolo, C._FECHA[direcao], "TRAILING_STOP_MARKET", qty, client_oid,
                          condicional=True, gatilho=ativacao, reduce_only=True, callback=callback_pct)

    def mover_stop(self, simbolo, ordem, novo_gatilho, novo_client_oid, qty=None):
        self._passa("mover_stop")
        direcao = "LONG" if ordem.get("lado") == "sell" else "SHORT"
        novo = self.colocar_stop(simbolo, direcao, novo_gatilho, novo_client_oid, qty=qty)
        self.cancelar(simbolo, ordem["id"], condicional=True)
        return novo

    def cancelar(self, simbolo, ordem_id, condicional=False):
        self._passa("cancelar")
        if self.dry_run:
            return True
        o = self.ordens.get(ordem_id)
        if not o or o["status"] not in ("aberta", "parcial"):
            return False
        o["status"] = "cancelada"
        return True

    def cancelar_tudo(self, simbolo):
        n = 0
        for o in self.abertas():
            if o["simbolo"] == simbolo:
                o["status"] = "cancelada"
                n += 1
        return n

    def buscar(self, simbolo, client_oid, condicional=False):
        self._passa("buscar")
        for o in self.ordens.values():
            if o["client_oid"] == client_oid:
                return dict(o)
        return None

    def buscar_por_id(self, simbolo, ordem_id):
        o = self.ordens.get(str(ordem_id))
        return dict(o) if o else None

    def fills(self, simbolo, desde_ms=None):
        self._passa("fills")
        desde = C.ms_para_sp(desde_ms) if desde_ms is not None else None
        return [dict(f) for f in self.negocios if f["simbolo"] == simbolo
                and (desde is None or pd.Timestamp(f["ts"]) >= desde)]

    def income(self, simbolo=None, desde_ms=None, tipo=None):
        self._passa("income")
        return [dict(x) for x in self.renda if simbolo in (None, x.get("simbolo"))
                and tipo in (None, x.get("tipo"))]


# ============================================================================ fixtures

@pytest.fixture
def conta(banco, sem_rede, monkeypatch):
    """Banco novo em modo `demo`, com a corretora falsa no lugar do adapter, banca de 1000 nos
    dois lados e uma reconciliação já feita (sem ela a conta não abre). TP desligado: quem
    testa alvo grava o plano à mão, para não depender de velas."""
    monkeypatch.setattr(execucao, "FOLGA_LEITURA_S", 0.0)     # o dublê não tem atraso de leitura
    monkeypatch.setattr(execucao.time, "sleep", lambda s: None)
    f = Falsa()
    db.set_config("corretora", "demo", "teste")
    db.set_config("tp_ativo", "0", "teste")
    execucao.usar(f)
    for d in (execucao._escrita, execucao._falta_fill, execucao._sem_stop, execucao._recusas):
        d.clear()
    execucao._reconciliado["mono"] = None
    execucao.reconciliar()
    yield f
    execucao.usar(None)
    execucao._reconciliado["mono"] = None


def _pos(pid=None):
    with db.conectar() as c:
        if pid is None:
            return [dict(r) for r in c.execute("SELECT * FROM posicoes ORDER BY id")]
        r = c.execute("SELECT * FROM posicoes WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None


def _trades():
    with db.conectar() as c:
        return [dict(r) for r in c.execute("SELECT * FROM trades ORDER BY id")]


def _ordens():
    with db.conectar() as c:
        return [dict(r) for r in c.execute("SELECT * FROM ordens ORDER BY id")]


def _sinal(sid):
    with db.conectar() as c:
        return c.execute("SELECT status FROM sinais WHERE id=?", (sid,)).fetchone()["status"]


def _banca():
    return db.get_banca()["atual"]


def _abrir(conta, ativo="BTC/USDT", direcao="LONG", valor=50.0, lev=2, preco=100.0, stop=95.0):
    sid = semear_sinal(ativo=ativo, direcao=direcao, preco=preco, stop=stop)
    tipo, ident = simulador.executar(sid, valor, lev)
    assert tipo == "posicao"
    return ident, sid


# ============================================================================ entrada a mercado

def test_a_entrada_a_mercado_abre_la_e_o_livro_copia(conta):
    pid, sid = _abrir(conta)
    p = _pos(pid)
    assert conta.pos["BTC/USDT"]["qty"] == pytest.approx(1.0)
    assert p["corretora"] == "demo" and p["qty"] == pytest.approx(1.0)
    assert p["entrada"] == 100.0 and p["valor_reais"] == pytest.approx(50.0)
    assert p["taxa_entrada"] == pytest.approx(Falsa.TAKER)        # a taxa COBRADA, não a da config
    assert _sinal(sid) == "confirmado"
    o = _ordens()[0]
    assert o["status"] == "preenchida" and o["posicao_id"] == pid and o["tipo"] == "mercado"
    with db.conectar() as c:
        f = [dict(r) for r in c.execute("SELECT * FROM fills")]
    assert len(f) == 1 and f[0]["papel"] == "entrada" and f[0]["posicao_id"] == pid


def test_regra_2_a_posicao_nasce_com_stop_na_corretora(conta):
    pid, _ = _abrir(conta)
    p = _pos(pid)
    stops = conta.abertas("STOP_MARKET")
    assert len(stops) == 1
    assert stops[0]["id"] == p["stop_ext_id"] and stops[0]["gatilho"] == p["stop"] == 95.0
    assert stops[0]["qty"] == pytest.approx(1.0) and stops[0]["reduce_only"]


def test_sem_stop_a_entrada_a_mercado_nem_sai(conta):
    """Regra 2: o stop vai ANTES da entrada a mercado. Se a corretora não o aceita, a entrada
    não é enviada, e nenhuma posição nasce sem proteção (revisão de 26/11)."""
    conta.falhar["colocar_stop"] = C.OrdemRecusada("recusado")
    with pytest.raises(ValueError, match="não aceitou o stop"):
        simulador.executar(semear_sinal(), 50.0, 2)
    assert not conta.pos and "abrir_mercado" not in conta.chamadas
    assert _ordens()[0]["status"] == "rejeitada" and not _pos()


def test_stop_que_some_e_nao_volta_fecha_na_mesma_reconciliacao(conta):
    """Regra 2 pelo avesso: a posição perdeu o stop e ele não entra de novo. A segunda tentativa
    é na hora, e não no ciclo seguinte: entre dois ciclos o processo pode cair (revisão de 26/11)."""
    pid, _ = _abrir(conta)
    conta.cancelar("BTC/USDT", _pos(pid)["stop_ext_id"], True)
    conta.falhar["colocar_stop"] = C.OrdemRecusada("recusado")
    execucao.reconciliar()
    assert "BTC/USDT" not in conta.pos and _pos(pid)["status"] == "fechada"
    assert _trades()[0]["motivo_saida"] == "sem-stop"
    assert conta.chamadas.count("colocar_stop") >= 3            # a da entrada e as duas de agora


def test_a_alavancagem_e_truncada_e_a_margem_e_a_que_vai_ser_usada(conta):
    sid = semear_sinal()
    _, pid = simulador.executar(sid, 50.0, 2.9)
    p = _pos(pid)
    assert p["alavancagem"] == 2.0 and conta.levs["BTC/USDT"] == 2
    assert p["valor_reais"] == pytest.approx(p["qty"] * p["entrada"] / 2.0)


def test_sinal_sem_stop_nao_abre_e_nao_e_consumido(conta):
    sid = semear_sinal(stop=None)
    with pytest.raises(ValueError, match="sem stop"):
        simulador.executar(sid, 50.0, 2)
    assert _sinal(sid) == "novo" and not conta.pos and not _ordens()


def test_abaixo_do_minimo_recusa_sem_consumir_e_lembra_a_recusa(conta):
    sid = semear_sinal()
    with pytest.raises(ValueError, match="abaixo do mínimo"):
        simulador.executar(sid, 1.0, 2)               # nocional 2 < 5
    assert _sinal(sid) == "novo"
    n = conta.chamadas.count("marks")
    with pytest.raises(ValueError, match="abaixo do mínimo"):
        simulador.executar(sid, 1.0, 2)
    assert conta.chamadas.count("marks") == n         # a segunda recusa não foi à rede


def test_o_limite_por_ordem_recusa_sem_a_palavra_teto(conta):
    """`teto` na mensagem faria o auto-trader encerrar o ciclo: um sinal grande demais travaria
    as outras entradas até expirar."""
    db.set_config("corretora_nocional_max", "80", "teste")
    sid = semear_sinal()
    with pytest.raises(ValueError) as e:
        simulador.executar(sid, 50.0, 2)              # nocional 100 > 80
    assert "teto" not in str(e.value) and "trava" not in str(e.value)
    assert _sinal(sid) == "novo" and not conta.pos


def test_uma_posicao_por_ativo(conta):
    _abrir(conta)
    sid = semear_sinal(direcao="SHORT", preco=100.0, stop=105.0)
    with pytest.raises(ValueError, match="uma posição por ativo"):
        simulador.executar(sid, 50.0, 2)
    assert _sinal(sid) == "novo" and conta.pos["BTC/USDT"]["qty"] == pytest.approx(1.0)


def test_sem_reconciliacao_recente_a_conta_nao_abre(conta):
    execucao._reconciliado["mono"] = None
    sid = semear_sinal()
    with pytest.raises(ValueError, match="trava da corretora"):
        simulador.executar(sid, 50.0, 2)
    assert _sinal(sid) == "novo" and not conta.pos


def test_os_tetos_do_papel_valem_e_levantam_antes_do_claim(conta):
    db.set_config("exposicao_max", "0.04", "teste")   # 4% de 1000 = 40 de margem
    sid = semear_sinal()
    with pytest.raises(ValueError, match="teto de margem"):
        simulador.executar(sid, 50.0, 2)
    assert _sinal(sid) == "novo" and not conta.pos and not _ordens()


def test_abrir_e_colocar_ordem_recusam_na_conta_em_corretora(conta):
    """O caminho do papel criaria uma linha no livro para uma posição que não existe lá."""
    sid = semear_sinal()
    with pytest.raises(ValueError, match="conta em corretora"):
        simulador.abrir(sid, 50.0, 2)
    with pytest.raises(ValueError, match="conta em corretora"):
        simulador.colocar_ordem(sid, 50.0, 2)
    assert _sinal(sid) == "novo" and not _pos() and not _ordens()


def test_envio_incerto_a_ordem_fica_pendente_e_o_ciclo_a_acha_pelo_id(conta):
    """Regras 3 e 4: a intenção estava gravada antes da rede; o ciclo procura, não reenvia."""
    real = conta.abrir_mercado

    def chega_e_a_resposta_se_perde(*a, **k):
        real(*a, **k)
        raise C.EnvioIncerto("timeout")
    conta.abrir_mercado = chega_e_a_resposta_se_perde
    sid = semear_sinal()
    tipo, oid = simulador.executar(sid, 50.0, 2)
    assert tipo == "ordem" and _ordens()[0]["status"] == "pendente" and not _pos()
    conta.abrir_mercado = real
    simulador.processar_ordens()
    assert _ordens()[0]["status"] == "preenchida"
    p = _pos()[0]
    assert p["qty"] == pytest.approx(1.0) and len(conta.abertas("STOP_MARKET")) == 1
    assert conta.pos["BTC/USDT"]["qty"] == pytest.approx(1.0)     # uma ordem só chegou lá


def test_dry_run_monta_registra_e_nao_abre(conta):
    def dry(simbolo, direcao, qty, coid, ref_preco=None):
        return {"id": f"dry-{coid}", "client_oid": coid, "status": "dry_run", "preenchido": 0.0}
    conta.abrir_mercado = dry
    sid = semear_sinal()
    tipo, _ = simulador.executar(sid, 50.0, 2)
    assert tipo == "ordem" and _ordens()[0]["status"] == "dry_run" and not _pos()


# ============================================================================ post-only

@pytest.fixture
def post_only(conta):
    db.set_config("exec_modo", "post_only", "teste")
    return conta


def test_post_only_a_ordem_descansa_com_o_stop_junto(post_only):
    sid = semear_sinal()
    tipo, oid = simulador.executar(sid, 50.0, 2)
    o = _ordens()[0]
    assert tipo == "ordem" and o["status"] == "pendente" and o["tipo"] == "limite"
    assert o["preco_limite"] == pytest.approx(99.9)               # 0,10% do nosso lado
    lim, st = post_only.abertas("LIMIT"), post_only.abertas("STOP_MARKET")
    assert len(lim) == 1 and len(st) == 1                         # o stop já está lá, antes do fill
    assert st[0]["qty"] == pytest.approx(lim[0]["qty"])
    assert _sinal(sid) == "confirmado" and not _pos()


def test_post_only_a_ordem_pendente_conta_nos_tetos(post_only):
    db.set_config("exposicao_max", "0.06", "teste")               # 60 de margem
    simulador.executar(semear_sinal(), 50.0, 2)
    sid2 = semear_sinal(ativo="ETH/USDT")
    with pytest.raises(ValueError, match="teto de margem"):
        simulador.executar(sid2, 50.0, 2)
    assert _sinal(sid2) == "novo"


def test_post_only_encheu_vira_posicao_com_taxa_maker_e_o_mesmo_stop(post_only):
    simulador.executar(semear_sinal(), 50.0, 2)
    stop_id = post_only.abertas("STOP_MARKET")[0]["id"]
    post_only.encher(post_only.abertas("LIMIT")[0]["id"])
    r = simulador.processar_ordens()
    assert r["preenchidas"] == 1
    p = _pos()[0]
    assert p["entrada"] == pytest.approx(99.9) and p["taxa_entrada"] == pytest.approx(Falsa.MAKER)
    assert p["stop_ext_id"] == stop_id and post_only.ordens[stop_id]["status"] == "aberta"
    assert len(_pos()) == 1
    simulador.processar_ordens()                                  # segundo ciclo: nada em dobro
    assert len(_pos()) == 1


def test_post_only_ttl_cancela_la_e_o_sinal_nao_volta(post_only):
    db.set_config("exec_ordem_ttl_s", "0", "teste")
    sid = semear_sinal()
    simulador.executar(sid, 50.0, 2)
    r = simulador.processar_ordens()
    assert r["expiradas"] == 1 and _ordens()[0]["status"] == "expirada"
    assert not post_only.abertas()                                # entrada E stop cancelados lá
    assert _sinal(sid) == "confirmado" and not _pos()


def test_post_only_parcial_cancela_o_resto_e_o_stop_fica_do_tamanho_certo(post_only):
    simulador.executar(semear_sinal(), 50.0, 2)
    lim = post_only.abertas("LIMIT")[0]
    post_only.encher(lim["id"], qty=0.4)
    simulador.processar_ordens()
    p = _pos()[0]
    assert p["qty"] == pytest.approx(0.4) and post_only.pos["BTC/USDT"]["qty"] == pytest.approx(0.4)
    assert post_only.ordens[lim["id"]]["status"] == "cancelada"
    st = post_only.abertas("STOP_MARKET")
    assert len(st) == 1 and st[0]["qty"] == pytest.approx(0.4) and st[0]["id"] == p["stop_ext_id"]


def test_post_only_stop_recusado_cancela_a_entrada(post_only):
    post_only.falhar["colocar_stop"] = C.OrdemRecusada("recusado")
    sid = semear_sinal()
    with pytest.raises(ValueError, match="recusou o stop"):
        simulador.executar(sid, 50.0, 2)
    assert not post_only.abertas() and _ordens()[0]["status"] == "cancelada" and not _pos()


def test_post_only_trava_do_dia_cancela_a_ordem_que_esperava(post_only, monkeypatch):
    simulador.executar(semear_sinal(), 50.0, 2)
    db.set_config("trava_dia_em", str(pd.Timestamp.now().date()), "teste")
    simulador.processar_ordens()
    assert _ordens()[0]["status"] == "cancelada" and not post_only.abertas()


# ============================================================================ fechar

def test_fechar_manual_fecha_la_lanca_o_real_e_limpa_as_condicionais(conta):
    pid, _ = _abrir(conta)
    conta.preco["BTC/USDT"] = 110.0
    pnl = simulador.fechar(pid, "manual")
    taxas = 100.0 * Falsa.TAKER + 110.0 * Falsa.TAKER
    assert pnl == pytest.approx(10.0 - taxas)
    assert "BTC/USDT" not in conta.pos and not conta.abertas()
    t = _trades()[0]
    assert t["motivo_saida"] == "manual" and t["corretora"] == "demo" and t["qty"] == pytest.approx(1.0)
    assert t["saida"] == 110.0 and t["pnl_reais"] == pytest.approx(pnl)
    # O modelo do papel cobra a taxa de saída sobre o nocional de ENTRADA (100), a corretora
    # sobre o de saída (110). A diferença, meio centavo aqui, é o que a coluna existe para medir.
    assert t["pnl_modelo"] == pytest.approx(10.0 - 2 * 100.0 * Falsa.TAKER)
    assert t["taxa"] == pytest.approx(taxas) and t["taxa_modelo"] == pytest.approx(0.10)
    assert _banca() == pytest.approx(1000.0 + pnl)
    assert _banca() == pytest.approx(conta.carteira)              # o livro bate com a conta


def test_fechar_com_a_posicao_ja_fechada_la_nao_inventa_saida(conta):
    pid, _ = _abrir(conta)
    conta.disparar(_pos(pid)["stop_ext_id"], 95.0)
    with pytest.raises(ValueError, match="pode já ter fechado"):
        simulador.fechar(pid, "manual")
    assert _pos(pid)["status"] == "aberta" and not _trades()      # quem lança é a reconciliação
    execucao.reconciliar()
    assert _trades()[0]["motivo_saida"] == "stop"


def test_taxa_em_bnb_entra_estimada_e_nao_somada_como_dolar(conta):
    conta.moeda_taxa = "BNB"
    pid, _ = _abrir(conta)
    assert _pos(pid)["taxa_entrada"] == pytest.approx(0.0005)     # a da config, não BNB/USDT
    conta.preco["BTC/USDT"] = 110.0
    pnl = simulador.fechar(pid, "manual")
    assert pnl == pytest.approx(10.0 - (100.0 + 110.0) * 0.0005)
    with db.conectar() as c:
        moedas = {r["taxa_moeda"] for r in c.execute("SELECT taxa_moeda FROM fills")}
    assert moedas == {"BNB"}                                      # o original fica no registro


def test_funding_real_entra_no_pnl_e_o_modelo_fica_ao_lado(conta):
    pid, _ = _abrir(conta)
    conta.renda.append({"tipo": "FUNDING_FEE", "valor": -0.30, "moeda": "USDT",
                        "simbolo": "BTC/USDT", "ts": pd.Timestamp.now()})
    conta.renda.append({"tipo": "COMMISSION", "valor": -9.0, "moeda": "USDT",
                        "simbolo": "BTC/USDT", "ts": pd.Timestamp.now()})
    pnl = simulador.fechar(pid, "manual")
    t = _trades()[0]
    assert t["funding"] == pytest.approx(-0.30) and t["funding_modelo"] == 0.0
    assert pnl == pytest.approx(-0.10 - 0.30)                     # só as taxas e o funding


# ============================================================================ reconciliação

def test_stop_disparou_la_a_reconciliacao_lanca_com_o_negocio_real(conta):
    pid, _ = _abrir(conta)
    conta.disparar(_pos(pid)["stop_ext_id"], 94.5)                # executou PIOR que o gatilho
    execucao.reconciliar()
    t = _trades()[0]
    assert _pos(pid)["status"] == "fechada"
    assert t["motivo_saida"] == "stop-gap" and t["saida"] == 94.5
    assert t["pnl_reais"] == pytest.approx(-5.5 - 100 * Falsa.TAKER - 94.5 * Falsa.TAKER)
    assert _banca() == pytest.approx(conta.carteira)


def test_trailing_em_lucro_que_dispara_sai_como_trailing(conta):
    pid, _ = _abrir(conta)
    conta.preco["BTC/USDT"] = 120.0                               # +4R: arma (3R) e sobe o stop
    simulador.atualizar()
    p = _pos(pid)
    assert p["stop"] == pytest.approx(105.0)                      # 120 - 3R
    conta.disparar(p["stop_ext_id"], 105.0)
    execucao.reconciliar()
    assert _trades()[0]["motivo_saida"] == "trailing"


def test_liquidacao_e_reconhecida_pelo_id_da_ordem(conta):
    pid, _ = _abrir(conta)
    conta.liquidar("BTC/USDT", 60.0)
    execucao.reconciliar()
    assert _trades()[0]["motivo_saida"] == "liquidacao"
    assert not conta.abertas()                                    # o stop órfão foi cancelado


def test_fechada_por_fora_sai_como_externo(conta):
    pid, _ = _abrir(conta)
    conta._reduz("BTC/USDT", 1.0, 101.0, conta._id())             # alguém fechou no aplicativo
    execucao.reconciliar()
    assert _trades()[0]["motivo_saida"] == "externo" and _pos(pid)["status"] == "fechada"


def test_sem_o_negocio_a_reconciliacao_espera_antes_de_lancar_as_cegas(conta):
    pid, _ = _abrir(conta)
    del conta.pos["BTC/USDT"]                                     # sumiu e não há negócio
    execucao.reconciliar()
    assert _pos(pid)["status"] == "aberta" and not _trades()
    for _ in range(execucao.ESPERA_FILL_CICLOS):
        execucao.reconciliar()
    assert _pos(pid)["status"] == "fechada"                       # não vira posição fantasma
    assert execucao.saude["divergencias"] >= 1


def test_posicao_la_sem_linha_aqui_e_adotada_com_stop(conta):
    conta._abre("ETH/USDT", "SHORT", 2.0, 100.0, conta._id(), Falsa.TAKER)
    execucao.reconciliar()
    p = _pos()[0]
    assert p["ativo"] == "ETH/USDT" and p["direcao"] == "SHORT" and p["qty"] == 2.0
    assert p["stop"] == pytest.approx(103.0) and p["sinal_id"] is None
    st = conta.abertas("STOP_MARKET")
    assert len(st) == 1 and st[0]["gatilho"] == 103.0 and st[0]["id"] == p["stop_ext_id"]


def test_ordem_enchendo_nao_e_adotada_como_orfa(conta):
    db.set_config("exec_modo", "post_only", "teste")
    simulador.executar(semear_sinal(), 50.0, 2)
    conta.encher(conta.abertas("LIMIT")[0]["id"])
    execucao.reconciliar()                                        # antes do processar_ordens
    assert not _pos()
    simulador.processar_ordens()
    assert len(_pos()) == 1 and _pos()[0]["sinal_id"] is not None


def test_ordem_nossa_sem_dono_e_cancelada_e_a_de_outro_nao(conta):
    ns = execucao._ns()
    nossa = conta._nova("BTC/USDT", "sell", "STOP_MARKET", 1.0, f"ap{ns}s99n1", condicional=True,
                        gatilho=90.0)
    alheia = conta._nova("BTC/USDT", "sell", "LIMIT", 1.0, "web_abc123", preco=150.0)
    outra_ns = conta._nova("BTC/USDT", "sell", "LIMIT", 1.0, "apffffffe1", preco=150.0)
    execucao.reconciliar()
    assert conta.ordens[nossa["id"]]["status"] == "cancelada"
    assert conta.ordens[alheia["id"]]["status"] == "aberta"
    assert conta.ordens[outra_ns["id"]]["status"] == "aberta"     # outro banco, outro prefixo


def test_stop_sumido_e_reposto(conta):
    pid, _ = _abrir(conta)
    conta.cancelar("BTC/USDT", _pos(pid)["stop_ext_id"], True)
    execucao.reconciliar()
    st = conta.abertas("STOP_MARKET")
    assert len(st) == 1 and st[0]["gatilho"] == 95.0 and st[0]["id"] == _pos(pid)["stop_ext_id"]
    assert execucao.saude["stops_repostos"] >= 1


def test_stop_sumido_com_o_preco_ja_alem_dele_fecha_a_mercado(conta):
    pid, _ = _abrir(conta)
    conta.cancelar("BTC/USDT", _pos(pid)["stop_ext_id"], True)
    conta.preco["BTC/USDT"] = 93.0
    execucao.reconciliar()
    assert "BTC/USDT" not in conta.pos and _trades()[0]["motivo_saida"] == "stop"


def test_posicao_que_cresceu_la_o_livro_adota_e_o_stop_cobre_tudo(conta):
    pid, _ = _abrir(conta)
    conta._abre("BTC/USDT", "LONG", 1.0, 102.0, conta._id(), Falsa.TAKER)
    execucao.reconciliar()
    p = _pos(pid)
    assert p["qty"] == pytest.approx(2.0) and p["entrada"] == pytest.approx(101.0)
    st = conta.abertas("STOP_MARKET")
    assert len(st) == 1 and st[0]["qty"] == pytest.approx(2.0)


def test_uma_posicao_que_falha_nao_tira_as_outras_da_reconciliacao(conta, monkeypatch):
    p1, _ = _abrir(conta)
    p2, _ = _abrir(conta, ativo="ETH/USDT")
    conta.disparar(_pos(p1)["stop_ext_id"], 95.0)
    conta.disparar(_pos(p2)["stop_ext_id"], 95.0)
    real = conta.fills

    def so_eth(simbolo, desde_ms=None):
        if simbolo == "BTC/USDT":
            raise ConnectionError("fora")
        return real(simbolo, desde_ms)
    conta.fills = so_eth
    execucao.reconciliar()
    assert _pos(p1)["status"] == "aberta" and _pos(p2)["status"] == "fechada"


def test_leitura_da_conta_falhou_a_reconciliacao_falha_e_a_conta_para_de_abrir(conta):
    conta.falhar["posicoes"] = ConnectionError("fora")
    execucao._reconciliado["mono"] = None
    with pytest.raises(ConnectionError):
        execucao.reconciliar()
    with pytest.raises(ValueError, match="trava da corretora"):
        simulador.executar(semear_sinal(), 50.0, 2)


def test_dinheiro_que_saiu_por_fora_desce_a_banca_do_livro(conta):
    conta.carteira -= 300.0                                       # saque
    execucao.reconciliar()
    assert _banca() == pytest.approx(700.0)
    conta.carteira += 5000.0                                      # depósito NÃO sobe a banca
    execucao.reconciliar()
    assert _banca() == pytest.approx(700.0)


# ============================================================================ trailing

def test_o_trailing_move_o_stop_la_antes_de_gravar_aqui(conta):
    pid, _ = _abrir(conta)
    antigo = _pos(pid)["stop_ext_id"]
    conta.preco["BTC/USDT"] = 116.0                               # +3,2R: armou
    simulador.atualizar()
    p = _pos(pid)
    assert p["stop"] == pytest.approx(101.0) and p["stop_ext_id"] != antigo
    assert conta.ordens[antigo]["status"] == "cancelada"
    st = conta.abertas("STOP_MARKET")
    assert len(st) == 1 and st[0]["gatilho"] == pytest.approx(101.0)
    assert p["preco_atual"] == 116.0 and p["pnl"] > 0


def test_o_trailing_nao_reenvia_o_stop_por_um_passo_menor_que_o_configurado(conta):
    pid, _ = _abrir(conta)
    conta.preco["BTC/USDT"] = 116.0
    simulador.atualizar()
    n = conta.chamadas.count("mover_stop")
    conta.preco["BTC/USDT"] = 116.3                               # +0,06R < passo de 0,1R
    simulador.atualizar()
    assert conta.chamadas.count("mover_stop") == n
    conta.preco["BTC/USDT"] = 117.0                               # +0,2R
    simulador.atualizar()
    assert conta.chamadas.count("mover_stop") == n + 1
    assert _pos(pid)["stop"] == pytest.approx(102.0)


def test_se_mover_o_stop_falha_o_livro_fica_com_o_stop_que_esta_la(conta):
    pid, _ = _abrir(conta)
    antes = _pos(pid)
    conta.preco["BTC/USDT"] = 116.0
    conta.falhar["mover_stop"] = C.EnvioIncerto("timeout")
    simulador.atualizar()
    p = _pos(pid)
    assert p["stop"] == antes["stop"] and p["stop_ext_id"] == antes["stop_ext_id"]
    assert conta.ordens[antes["stop_ext_id"]]["status"] == "aberta"


def test_a_marcacao_nao_fecha_por_preco(conta):
    """O preço passou do stop e a corretora ainda não disparou: o livro NÃO fecha sozinho."""
    pid, _ = _abrir(conta)
    conta.preco["BTC/USDT"] = 90.0
    simulador.atualizar()
    assert _pos(pid)["status"] == "aberta" and not _trades()
    assert _pos(pid)["pnl"] < 0


# ============================================================================ alvos

def _com_plano(pid, niveis, resto_livre=False):
    plano = {"niveis": [{"preco": p, "r": r, "frac": f, "feito": False, "fonte": "teste"}
                        for p, r, f in niveis],
             "valor_inicial": _pos(pid)["valor_reais"], "r_preco": 5.0, "calc_em": "x"}
    if resto_livre:
        plano["resto_livre"] = True
    with db.conectar() as c:
        c.execute("UPDATE posicoes SET tps=? WHERE id=?", (json.dumps(plano), pid))
    db.set_config("tp_ativo", "1", "teste")


def test_os_alvos_viram_ordens_na_corretora_com_fracao_do_original(conta):
    pid, _ = _abrir(conta)
    _com_plano(pid, [(110.0, 2.0, 0.5), (120.0, 4.0, 0.5)])
    simulador.atualizar()
    tps = sorted(conta.abertas("TAKE_PROFIT_MARKET"), key=lambda o: o["gatilho"])
    assert [(o["gatilho"], o["qty"]) for o in tps] == [(110.0, 0.5), (120.0, 0.5)]
    simulador.atualizar()                                         # não recoloca
    assert len(conta.abertas("TAKE_PROFIT_MARKET")) == 2


def test_tp1_disparou_la_vira_parcial_no_livro_e_o_resto_segue(conta):
    pid, _ = _abrir(conta)
    _com_plano(pid, [(110.0, 2.0, 0.5), (120.0, 4.0, 0.5)])
    simulador.atualizar()
    tp1 = min(conta.abertas("TAKE_PROFIT_MARKET"), key=lambda o: o["gatilho"])
    conta.preco["BTC/USDT"] = 110.0
    conta.disparar(tp1["id"], 110.0)
    execucao.reconciliar()
    p, t = _pos(pid), _trades()
    assert p["status"] == "aberta" and p["qty"] == pytest.approx(0.5)
    assert p["valor_reais"] == pytest.approx(25.0)
    assert len(t) == 1 and t[0]["motivo_saida"] == "tp1" and t[0]["qty"] == pytest.approx(0.5)
    assert t[0]["pnl_reais"] == pytest.approx(5.0 - 50 * Falsa.TAKER - 55 * Falsa.TAKER)
    plano = json.loads(p["tps"])
    assert plano["niveis"][0]["feito"] and not plano["niveis"][1]["feito"]
    assert len(conta.abertas("STOP_MARKET")) == 1                 # o stop continua lá
    assert _banca() == pytest.approx(1000.0 + t[0]["pnl_reais"])
    # a carteira já pagou a taxa de entrada INTEIRA; o livro lançou só a metade que fechou
    assert conta.carteira == pytest.approx(_banca() - 50 * Falsa.TAKER)


def test_tp1_e_stop_no_mesmo_intervalo_cada_um_com_o_seu_negocio(conta):
    pid, _ = _abrir(conta)
    _com_plano(pid, [(110.0, 2.0, 0.5), (120.0, 4.0, 0.5)])
    simulador.atualizar()
    tp1 = min(conta.abertas("TAKE_PROFIT_MARKET"), key=lambda o: o["gatilho"])
    conta.disparar(tp1["id"], 110.0)
    conta.disparar(_pos(pid)["stop_ext_id"], 95.0)
    execucao.reconciliar()
    t = _trades()
    assert [x["motivo_saida"] for x in t] == ["tp1", "stop"]
    assert [x["saida"] for x in t] == [110.0, 95.0]
    assert _pos(pid)["status"] == "fechada" and not conta.abertas()


def test_stop_na_entrada_depois_do_tp1(conta):
    db.set_config("tp_stop_entrada", "1", "teste")
    pid, _ = _abrir(conta)
    _com_plano(pid, [(110.0, 2.0, 0.5), (120.0, 4.0, 0.5)])
    simulador.atualizar()
    tp1 = min(conta.abertas("TAKE_PROFIT_MARKET"), key=lambda o: o["gatilho"])
    conta.preco["BTC/USDT"] = 110.0
    conta.disparar(tp1["id"], 110.0)
    execucao.reconciliar()
    simulador.atualizar()
    assert _pos(pid)["stop"] == pytest.approx(100.0)
    st = conta.abertas("STOP_MARKET")
    assert len(st) == 1 and st[0]["gatilho"] == pytest.approx(100.0)


def test_alvo_que_o_preco_ja_passou_realiza_a_mercado(conta):
    pid, _ = _abrir(conta)
    _com_plano(pid, [(110.0, 2.0, 0.5), (120.0, 4.0, 0.5)])
    conta.preco["BTC/USDT"] = 112.0
    simulador.atualizar()
    t = _trades()
    assert len(t) == 1 and t[0]["motivo_saida"] == "tp1" and t[0]["saida"] == 112.0
    assert _pos(pid)["qty"] == pytest.approx(0.5)
    assert len(conta.abertas("TAKE_PROFIT_MARKET")) == 1          # o TP2 ficou descansando


def test_fechamento_lancado_sem_o_negocio_nao_e_contado_de_novo_na_saida_seguinte(conta):
    """O alvo realiza a mercado e o negócio ainda não aparece na leitura: a saída é lançada pelo
    preço médio da ordem. Quando o negócio aparece, ele não pode entrar na conta da PRÓXIMA
    saída do ativo (o stop do resto sairia a 103,5, a média de 112 com 95)."""
    pid, _ = _abrir(conta)
    _com_plano(pid, [(110.0, 2.0, 0.5), (120.0, 4.0, 0.5)])
    conta.preco["BTC/USDT"] = 112.0
    ler = conta.fills
    conta.fills = lambda simbolo, desde_ms=None: []               # "ainda não apareceu"
    simulador.atualizar()
    conta.fills = ler                                             # agora aparece
    t = _trades()
    assert len(t) == 1 and t[0]["motivo_saida"] == "tp1" and t[0]["saida"] == 112.0
    conta.disparar(_pos(pid)["stop_ext_id"], 95.0)
    execucao.reconciliar()
    t = _trades()
    assert len(t) == 2 and t[1]["saida"] == 95.0 and t[1]["qty"] == pytest.approx(0.5)
    assert t[1]["taxa"] == pytest.approx(50 * Falsa.TAKER + 47.5 * Falsa.TAKER)
    assert _pos(pid)["status"] == "fechada"


def test_alvo_menor_que_um_lote_fica_sem_ordem_e_segue_no_trailing(conta):
    pid, _ = _abrir(conta, valor=5.0, lev=1, preco=100.0)         # qty 0,05
    _com_plano(pid, [(110.0, 2.0, 0.001), (120.0, 4.0, 0.5)], resto_livre=True)
    simulador.atualizar()
    plano = json.loads(_pos(pid)["tps"])
    assert plano["niveis"][0].get("pulado") and plano["niveis"][0]["feito"]
    assert len(conta.abertas("TAKE_PROFIT_MARKET")) == 1


def test_resto_livre_o_ultimo_alvo_leva_so_a_fracao_dele(conta):
    pid, _ = _abrir(conta)
    _com_plano(pid, [(110.0, 2.0, 0.3)], resto_livre=True)
    simulador.atualizar()
    tps = conta.abertas("TAKE_PROFIT_MARKET")
    assert len(tps) == 1 and tps[0]["qty"] == pytest.approx(0.3)


# ============================================================================ travas

def test_teto_de_perda_total_trava_desliga_o_bot_e_so_solta_subindo_o_teto(conta):
    db.set_config("perda_total_max", "20", "teste")
    db.set_config("auto_trade", "1", "teste")
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=985 WHERE id=1")        # perda de 15 < 20
    assert not execucao.guarda_total()["travada"]
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=979 WHERE id=1")        # perda de 21
    g = execucao.guarda_total()
    assert g["travada"] and db.get_config()["auto_trade"] == "0"
    with pytest.raises(ValueError, match="teto de perda total"):
        simulador.executar(semear_sinal(), 50.0, 2)
    with db.conectar() as c:                                      # recuperou: continua travada
        c.execute("UPDATE banca SET atual=1000 WHERE id=1")
    assert execucao.guarda_total()["travada"]
    db.set_config("perda_total_max", "50", "POST /config")        # o dono subiu o teto
    assert not execucao.guarda_total()["travada"]
    assert db.get_config()["trava_total_em"] == ""


def test_baixar_o_teto_nao_solta_a_trava(conta):
    db.set_config("perda_total_max", "20", "teste")
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=970 WHERE id=1")
    assert execucao.guarda_total()["travada"]
    db.set_config("perda_total_max", "10", "teste")
    assert execucao.guarda_total()["travada"]


# ============================================================================ revisão de 25/11
# Um teste por defeito que a revisão independente do caminho de dinheiro real achou. O dublê
# corta a quantidade pelo texto do número (`Falsa._trunca`) e respeita o `desde` da leitura de
# negócios, como a corretora: é o que faz os defeitos de lote e de janela aparecerem aqui.

def _abrir_fino(conta):
    """0,062 a 100. Com um alvo de 0,021, o que sobra é 0.040999999999999995 em float."""
    return _abrir(conta, valor=3.1, lev=2)


def test_o_que_sobra_de_um_alvo_a_mercado_fica_no_lote_e_o_stop_e_o_fechamento_cobrem_tudo(conta):
    pid, _ = _abrir_fino(conta)
    assert _pos(pid)["qty"] == 0.062
    _com_plano(pid, [(110.0, 2.0, 0.34), (120.0, 4.0, 0.66)], resto_livre=True)
    conta.preco["BTC/USDT"] = 112.0                               # já passou do TP1: 0,021 a mercado
    simulador.atualizar()
    assert _trades()[0]["qty"] == pytest.approx(0.021)
    assert _pos(pid)["qty"] == 0.041                              # exato, sem resíduo
    execucao._garantir_stop(conta, _pos(pid), 101.0)
    st = conta.abertas("STOP_MARKET")
    assert len(st) == 1 and st[0]["qty"] == 0.041                 # o stop cobre a posição inteira
    simulador.fechar(pid, "manual")
    assert "BTC/USDT" not in conta.pos                            # nenhum lote ficou para trás
    assert _pos(pid)["status"] == "fechada" and not conta.abertas()


def test_o_que_sobra_de_um_alvo_disparado_la_e_a_quantidade_da_corretora(conta):
    pid, _ = _abrir_fino(conta)
    _com_plano(pid, [(110.0, 2.0, 0.34)], resto_livre=True)
    simulador.atualizar()
    conta.disparar(conta.abertas("TAKE_PROFIT_MARKET")[0]["id"], 110.0)
    execucao.reconciliar()
    assert _pos(pid)["qty"] == 0.041 == conta.pos["BTC/USDT"]["qty"]


def test_post_only_de_envio_incerto_nao_descansa_sem_stop(post_only):
    """A entrada chegou e a resposta se perdeu. Ela pode encher com o processo fora do ar: o
    stop vai na mesma hora, sem esperar o ciclo achar a ordem."""
    post_only.perde_resposta.add("colocar_limite_post_only")
    tipo, _ = simulador.executar(semear_sinal(), 50.0, 2)
    assert tipo == "ordem" and _ordens()[0]["status"] == "pendente"
    lim, st = post_only.abertas("LIMIT"), post_only.abertas("STOP_MARKET")
    assert len(lim) == 1 and len(st) == 1
    assert _ordens()[0]["stop_ext_id"] == st[0]["id"] and st[0]["qty"] == lim[0]["qty"]


def test_post_only_descansando_sem_stop_o_ciclo_coloca(post_only):
    post_only.perde_resposta.add("colocar_limite_post_only")
    post_only.falhar["colocar_stop"] = C.EnvioIncerto("sem rede")
    simulador.executar(semear_sinal(), 50.0, 2)
    assert len(post_only.abertas("LIMIT")) == 1 and not post_only.abertas("STOP_MARKET")
    del post_only.falhar["colocar_stop"]
    simulador.processar_ordens()
    st = post_only.abertas("STOP_MARKET")
    assert len(st) == 1 and _ordens()[0]["stop_ext_id"] == st[0]["id"]
    assert _ordens()[0]["status"] == "pendente"
    simulador.processar_ordens()                                  # e não coloca um segundo
    assert len(post_only.abertas("STOP_MARKET")) == 1


def test_post_only_descansando_sem_stop_e_o_stop_recusado_cancela_a_entrada(post_only):
    post_only.perde_resposta.add("colocar_limite_post_only")
    post_only.falhar["colocar_stop"] = C.OrdemRecusada("recusado")
    simulador.executar(semear_sinal(), 50.0, 2)
    assert len(post_only.abertas("LIMIT")) == 1
    r = simulador.processar_ordens()
    assert not post_only.abertas() and _ordens()[0]["status"] == "cancelada" and r["expiradas"] == 1


def test_encheu_e_stopou_com_o_servidor_desligado_a_saida_sai_com_o_negocio_real(post_only):
    """A ordem enche de madrugada e o stop dela dispara de madrugada. De manhã o livro cria a
    linha de uma posição que já fechou. `aberto_em` tem de ser a hora do NEGÓCIO da entrada:
    com a hora em que o livro soube, o negócio da saída fica antes da janela e nunca é achado."""
    simulador.executar(semear_sinal(), 50.0, 2)
    lim, st = post_only.abertas("LIMIT")[0], post_only.abertas("STOP_MARKET")[0]
    post_only.encher(lim["id"])
    post_only.disparar(st["id"], 94.9)
    agora = pd.Timestamp.now()
    post_only.negocios[0]["ts"] = agora - pd.Timedelta(hours=3)   # encheu 3 h atrás
    post_only.negocios[1]["ts"] = agora - pd.Timedelta(hours=2)   # stopou 1 h depois
    with db.conectar() as c:
        c.execute("UPDATE ordens SET criada_em=?", (str(agora - pd.Timedelta(hours=4)),))
    execucao.reconciliar()                                        # a manhã, na ordem do worker
    simulador.processar_ordens()
    p = _pos()[0]
    assert pd.Timestamp(p["aberto_em"]) == post_only.negocios[0]["ts"]
    execucao.reconciliar()
    t = _trades()
    assert len(t) == 1 and t[0]["saida"] == 94.9 and t[0]["motivo_saida"].startswith("stop")
    assert p["qty"] == 1.001                                      # 100 / 99,9, no lote
    assert t[0]["taxa"] == pytest.approx(1.001 * (99.9 * Falsa.MAKER + 94.9 * Falsa.TAKER))
    assert _pos(p["id"])["status"] == "fechada" and not post_only.abertas()
    with db.conectar() as c:
        assert c.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 2


def test_teto_de_perda_total_cancela_a_entrada_que_descansava(post_only):
    simulador.executar(semear_sinal(), 50.0, 2)
    db.set_config("perda_total_max", "10", "teste")
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=980 WHERE id=1")       # perda de 20, teto de 10
    simulador.processar_ordens()
    assert _ordens()[0]["status"] == "cancelada" and not post_only.abertas()
    assert _ordens()[0]["motivo"] == "teto de perda total"


def test_teto_com_muitas_casas_nao_solta_a_propria_trava(conta):
    db.set_config("perda_total_max", "33.3333333", "teste")
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=960 WHERE id=1")
    assert execucao.guarda_total()["travada"]
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=1000 WHERE id=1")      # o equity voltou sozinho
    assert execucao.guarda_total()["travada"]                     # sticky: só subir o teto solta
    db.set_config("perda_total_max", "50", "teste")
    assert not execucao.guarda_total()["travada"]


def test_queda_do_mercado_entre_duas_leituras_nao_desce_a_banca(conta):
    """O resultado aberto da corretora é de agora; o do livro, da última marcação. Comparar os
    dois fazia uma queda de mercado parecer dinheiro sumido, e a mesma perda entrava duas vezes."""
    _abrir(conta)
    d0 = execucao.saude["divergencias"]
    conta.preco["BTC/USDT"] = 70.0                                # -30 aberto LÁ; o livro marca 100
    execucao.reconciliar()
    assert _banca() == pytest.approx(1000.0) and execucao.saude["divergencias"] == d0


def test_alvo_ja_colocado_nao_perde_o_id_se_o_seguinte_estoura(conta):
    pid, _ = _abrir(conta)
    _com_plano(pid, [(110.0, 2.0, 0.5), (120.0, 4.0, 0.5)])
    real, n = conta.arredondar, {"v": 0}

    def estoura_no_segundo(*a, **k):
        n["v"] += 1
        if n["v"] == 2:
            raise RuntimeError("inesperado")
        return real(*a, **k)
    conta.arredondar = estoura_no_segundo
    simulador.atualizar()
    conta.arredondar = real
    assert json.loads(_pos(pid)["tps"])["niveis"][0].get("ext_id")
    execucao.reconciliar()                                        # não o cancela como ordem sem dono
    assert len(conta.abertas("TAKE_PROFIT_MARKET")) == 1
    simulador.atualizar()                                         # e o segundo entra no ciclo seguinte
    assert len(conta.abertas("TAKE_PROFIT_MARKET")) == 2


def test_alvo_ja_passado_com_envio_incerto_nao_realiza_duas_vezes(conta):
    pid, _ = _abrir(conta)
    _com_plano(pid, [(110.0, 2.0, 0.5), (130.0, 6.0, 0.5)])
    conta.preco["BTC/USDT"] = 112.0
    real = conta.fechar_mercado

    def executa_e_a_resposta_se_perde(*a):
        real(*a)
        raise C.EnvioIncerto("timeout")
    conta.fechar_mercado = executa_e_a_resposta_se_perde
    simulador.atualizar()                                         # realizou 0,5 LÁ; aqui ficou incerto
    conta.fechar_mercado = real
    assert conta.pos["BTC/USDT"]["qty"] == pytest.approx(0.5)
    execucao.reconciliar()                                        # o livro lança a redução
    simulador.atualizar()                                         # e o TP1 NÃO é realizado de novo
    assert conta.pos["BTC/USDT"]["qty"] == pytest.approx(0.5)
    assert sum(t["qty"] for t in _trades()) == pytest.approx(0.5)
    assert _pos(pid)["qty"] == pytest.approx(0.5)


def test_posicao_sem_stop_e_reposta_pela_marcacao_sem_depender_da_reconciliacao(conta):
    pid, _ = _abrir(conta)
    conta.cancelar("BTC/USDT", _pos(pid)["stop_ext_id"], True)
    with db.conectar() as c:                                      # o livro sabe que está sem
        c.execute("UPDATE posicoes SET stop_ext_id=NULL WHERE id=?", (pid,))
    assert not conta.abertas("STOP_MARKET") and not _pos(pid)["stop_ext_id"]
    conta.falhar["posicoes"] = C.ErroCorretora("leitura fora do ar")
    with pytest.raises(C.ErroCorretora):
        execucao.reconciliar()
    simulador.atualizar()
    st = conta.abertas("STOP_MARKET")
    assert len(st) == 1 and st[0]["id"] == _pos(pid)["stop_ext_id"] and st[0]["gatilho"] == 95.0


def test_cada_tentativa_de_stop_sai_com_id_novo(conta):
    """Id reusado depois de um envio incerto deixaria a busca devolver a ordem da tentativa
    anterior (que a reconciliação já cancelou) como se fosse a resposta da nova."""
    pid, _ = _abrir(conta)
    antes = _pos(pid)["stop_coid"]
    conta.falhar_uma["mover_stop"] = C.EnvioIncerto("timeout")
    execucao._garantir_stop(conta, _pos(pid), 96.0)               # falha: o antigo continua
    assert _pos(pid)["stop_coid"] == antes and _pos(pid)["stop"] == 95.0
    execucao._garantir_stop(conta, _pos(pid), 96.0)
    p = _pos(pid)
    assert p["stop"] == 96.0 and p["stop_coid"] != antes
    # o stop da entrada usa o id da ORDEM (`p<oid>`, pré-colocado): 1 a perdida, 2 esta
    assert p["stop_seq"] == 2


def test_fechamento_que_executa_so_parte_nao_tira_o_stop(conta):
    pid, _ = _abrir(conta)
    real = conta.fechar_mercado
    conta.fechar_mercado = lambda s, d, q, coid: real(s, d, q / 2, coid)
    with pytest.raises(ValueError, match="só parte"):
        simulador.fechar(pid, "manual")
    conta.fechar_mercado = real
    assert _pos(pid)["status"] == "aberta" and _pos(pid)["qty"] == pytest.approx(0.5)
    assert len(conta.abertas("STOP_MARKET")) == 1
    assert simulador.fechar(pid, "manual") is not None            # a segunda tentativa fecha o resto
    assert "BTC/USDT" not in conta.pos and not conta.abertas()


def test_dry_run_nao_finge_fechamento_nem_stop_nem_panico(conta):
    pid, _ = _abrir(conta)
    stop_id = _pos(pid)["stop_ext_id"]
    conta.dry_run = True
    with pytest.raises(ValueError, match="dry_run"):
        simulador.fechar(pid, "manual")
    assert _pos(pid)["status"] == "aberta" and conta.pos["BTC/USDT"]["qty"] == 1.0
    execucao._garantir_stop(conta, _pos(pid), 97.0)
    p = _pos(pid)
    assert p["stop"] == 95.0 and p["stop_ext_id"] == stop_id      # o livro não inventa stop
    r = execucao.panico()
    assert r["fechadas"] == 0 and len(r["falhas"]) == 2 and not r["varridas"]
    assert conta.pos["BTC/USDT"]["qty"] == 1.0 and conta.ordens[stop_id]["status"] == "aberta"


def test_dry_run_nao_adota_posicao_que_nao_consegue_proteger(conta):
    conta._abre("SOL/USDT", "LONG", 1.0, 100.0, conta._id(), Falsa.TAKER)
    conta.dry_run = True
    d0 = execucao.saude["divergencias"]
    execucao.reconciliar()
    execucao.reconciliar()
    assert not _pos() and execucao.saude["divergencias"] == d0 + 1   # avisa uma vez, não adota


def test_panico_diz_quando_uma_ordem_nossa_nao_cancelou(conta):
    _abrir(conta)
    conta.falhar["cancelar"] = C.ErroCorretora("sem rede")
    r = execucao.panico()
    assert "BTC/USDT" not in conta.pos
    assert any("não cancelou" in f["erro"] for f in r["falhas"])


def test_negocio_dividido_entre_dois_eventos_nao_volta_como_novo(conta):
    """Um negócio só fechou o alvo e o stop. Ele é gravado em dois pedaços; o id cru dele não
    pode reaparecer como negócio não lançado na saída seguinte do mesmo ativo."""
    pid, _ = _abrir(conta)
    _com_plano(pid, [(110.0, 2.0, 0.5)], resto_livre=True)
    simulador.atualizar()
    tp1 = conta.abertas("TAKE_PROFIT_MARKET")[0]
    conta.ordens[tp1["id"]]["status"] = "disparada"
    conta.ordens[_pos(pid)["stop_ext_id"]]["status"] = "disparada"
    conta._reduz("BTC/USDT", 1.0, 108.0, conta._id())             # UM negócio de 1,0
    execucao.reconciliar()
    t = _trades()
    assert [x["qty"] for x in t] == [pytest.approx(0.5), pytest.approx(0.5)]
    assert _pos(pid)["status"] == "fechada"
    assert execucao._fills_novos(conta, "BTC/USDT", t[0]["aberto_em"], "sell") == []


def test_ordem_de_fora_do_livro_e_avisada_uma_vez_e_nao_e_tocada(conta):
    conta._nova("BTC/USDT", "sell", "STOP_MARKET", 1.0, "outrobanco-s1", condicional=True,
                gatilho=90.0, reduce_only=True)
    d0 = execucao.saude["divergencias"]
    execucao.reconciliar()
    execucao.reconciliar()
    assert execucao.saude["divergencias"] == d0 + 1 and execucao.saude["ordens_de_fora"] == 1
    assert len(conta.abertas("STOP_MARKET")) == 1


def test_de_noite_o_trailing_ja_armado_vai_sem_preco_de_ativacao(conta, monkeypatch):
    db.set_config("noite_ativo", "1", "teste")
    _hora(monkeypatch, "12:00")
    _abrir(conta)
    conta.preco["BTC/USDT"] = 120.0                               # já passou de +3R: está armado
    _hora(monkeypatch, "22:00")
    simulador.atualizar()
    tr = conta.abertas("TRAILING_STOP_MARKET")
    assert len(tr) == 1 and tr[0]["gatilho"] is None


# ============================================================================ a noite

def _hora(monkeypatch, hhmm):
    """Fixa a hora que a janela da noite enxerga. SEMPRE `fixo`, também quando quem chama passa
    o próprio `agora` (`processar_ordens` passa o relógio de verdade): respeitar esse `agora`
    fazia o teste do cancelamento noturno passar à noite e falhar de dia (revisão de 26/11)."""
    real = pd.Timestamp.now
    fixo = pd.Timestamp(f"{real().date()} {hhmm}")
    monkeypatch.setattr(execucao, "noite", lambda cfg, agora=None: _NOITE(cfg, fixo))


_NOITE = execucao.noite              # a original: `_hora` chamada duas vezes não embrulha a si mesma


def test_a_janela_da_noite_atravessa_a_meia_noite():
    cfg = {"noite_ativo": "1", "noite_inicio": "19:00", "noite_fim": "07:00"}
    assert execucao.noite(cfg, "2026-11-25 19:00") and execucao.noite(cfg, "2026-11-26 03:00")
    assert execucao.noite(cfg, "2026-11-26 06:59") and not execucao.noite(cfg, "2026-11-26 07:00")
    assert not execucao.noite(cfg, "2026-11-25 12:00")
    assert not execucao.noite({**cfg, "noite_ativo": "0"}, "2026-11-26 03:00")
    assert not execucao.noite({**cfg, "noite_inicio": "lixo"}, "2026-11-26 03:00")


def test_de_noite_a_conta_nao_abre_e_cancela_o_que_esperava(conta, monkeypatch):
    db.set_config("exec_modo", "post_only", "teste")
    db.set_config("noite_ativo", "1", "teste")
    _hora(monkeypatch, "12:00")
    simulador.executar(semear_sinal(), 50.0, 2)
    _hora(monkeypatch, "22:00")
    with pytest.raises(ValueError, match="trava da noite"):
        simulador.executar(semear_sinal(ativo="ETH/USDT"), 50.0, 2)
    simulador.processar_ordens()
    assert _ordens()[0]["status"] == "cancelada" and not conta.abertas()


def test_de_noite_o_trailing_e_entregue_a_corretora_uma_vez(conta, monkeypatch):
    db.set_config("noite_ativo", "1", "teste")
    _hora(monkeypatch, "12:00")
    pid, _ = _abrir(conta)
    _hora(monkeypatch, "22:00")
    simulador.atualizar()
    simulador.atualizar()
    tr = conta.abertas("TRAILING_STOP_MARKET")
    assert len(tr) == 1
    assert tr[0]["gatilho"] == pytest.approx(115.0)               # arma em +3R
    assert tr[0]["callback"] == pytest.approx(10.0)               # 3R = 15 sobre 115 = 13% -> teto 10
    assert len(conta.abertas("STOP_MARKET")) == 1                 # o stop fixo continua
    assert json.loads(_pos(pid)["noite"])["id"] == tr[0]["id"]


def test_de_manha_o_trailing_nativo_sai_e_o_stop_sobe_pelo_pico_da_noite(conta, monkeypatch):
    db.set_config("noite_ativo", "1", "teste")
    _hora(monkeypatch, "22:00")
    with pytest.raises(ValueError):                               # de noite não abre: abre de dia
        _abrir(conta)
    _hora(monkeypatch, "12:00")
    pid, _ = _abrir(conta)
    _hora(monkeypatch, "22:00")
    simulador.atualizar()
    monkeypatch.setattr(simulador, "_velas_1m",
                        lambda ativo, a, b: [[0, 100, 118, 99, 110, 1]])   # pico 118 de madrugada
    conta.preco["BTC/USDT"] = 110.0
    _hora(monkeypatch, "08:00")
    simulador.atualizar()
    p = _pos(pid)
    assert p["noite"] is None and not conta.abertas("TRAILING_STOP_MARKET")
    assert p["stop"] == pytest.approx(103.0)                      # 118 - 3R
    assert conta.abertas("STOP_MARKET")[0]["gatilho"] == pytest.approx(103.0)


# ============================================================================ revisão de 26/11
# Seis revisores independentes, cada um com um papel (dinheiro, falhas e tempo, regras da casa,
# segurança, contrato com a Binance, testes). Um teste por defeito confirmado no motor.

def _fechamento_que_nao_executa(conta, status):
    """A Binance aceita a ordem de fechar e ela volta sem executar nada (proteção de preço num
    mercado rápido, ou o ACK sem o preenchimento)."""
    def fecha(simbolo, direcao, qty, coid):
        o = conta._nova(simbolo, C._FECHA[direcao], "MARKET", qty, coid, reduce_only=True)
        conta.ordens[o["id"]]["status"] = status
        return dict(conta.ordens[o["id"]])
    conta.fechar_mercado = fecha


def test_fechamento_que_volta_sem_executar_nao_e_lancado_e_o_stop_fica(conta):
    pid, _ = _abrir(conta)
    _fechamento_que_nao_executa(conta, "expirada")
    with pytest.raises(ValueError, match="SEGUE aberta"):
        simulador.fechar(pid, "manual")
    assert _pos(pid)["status"] == "aberta" and not _trades()
    assert conta.pos["BTC/USDT"]["qty"] == 1.0
    assert conta.ordens[_pos(pid)["stop_ext_id"]]["status"] == "aberta"


def test_fechamento_aceito_sem_execucao_conhecida_fica_incerto(conta):
    pid, _ = _abrir(conta)
    _fechamento_que_nao_executa(conta, "aberta")
    with pytest.raises(ValueError, match="não deu para confirmar"):
        simulador.fechar(pid, "manual")
    assert _pos(pid)["status"] == "aberta" and not _trades()
    assert conta.ordens[_pos(pid)["stop_ext_id"]]["status"] == "aberta"


def test_fechamento_que_executou_e_nao_teve_o_negocio_lido_e_lancado(conta):
    pid, _ = _abrir(conta)
    conta.preco["BTC/USDT"] = 110.0
    real = conta.fechar_mercado

    def fecha_e_a_leitura_cai(*a):
        r = real(*a)
        conta.falhar["fills"] = ConnectionError("fora")
        return r
    conta.fechar_mercado = fecha_e_a_leitura_cai
    pnl = simulador.fechar(pid, "manual")
    assert pnl is not None and _pos(pid)["status"] == "fechada"
    assert _trades()[0]["saida"] == 110.0 and not conta.abertas()


def test_panico_com_recusa_que_nao_e_a_do_reduce_only_e_falha(conta):
    conta._abre("ETH/USDT", "LONG", 1.0, 100.0, conta._id(), Falsa.TAKER)    # fora do livro
    real = conta.fechar_mercado

    def protege_o_preco(simbolo, direcao, qty, coid):
        if simbolo == "ETH/USDT":
            raise C.OrdemRecusada("binance -4131 The counterparty's best price does not meet the "
                                  "PERCENT_PRICE filter limit.")
        return real(simbolo, direcao, qty, coid)
    conta.fechar_mercado = protege_o_preco
    r = execucao.panico()
    assert "ETH/USDT" in conta.pos
    assert [f["ativo"] for f in r["falhas"]] == ["ETH/USDT"] and not r["varridas"]


def test_panico_confere_a_conta_no_fim_e_acusa_o_que_ficou(conta):
    """Uma resposta que diz "preenchida" não prova nada: a prova é a conta, relida no fim."""
    pid, _ = _abrir(conta)

    def mente(simbolo, direcao, qty, coid):
        o = conta._nova(simbolo, C._FECHA[direcao], "MARKET", qty, coid, reduce_only=True)
        conta.ordens[o["id"]].update(status="preenchida", preenchido=qty, preco_medio=100.0)
        return dict(conta.ordens[o["id"]])
    conta.fechar_mercado = mente
    r = execucao.panico()
    assert "BTC/USDT" in conta.pos
    assert any("segue ABERTA" in f["erro"] for f in r["falhas"])


def test_saida_que_espera_o_negocio_nao_desce_a_banca_duas_vezes(conta):
    pid, _ = _abrir(conta)
    conta.disparar(_pos(pid)["stop_ext_id"], 70.0)                # gap: −30 lá
    ler = conta.fills
    conta.fills = lambda simbolo, desde_ms=None: []               # o negócio ainda não aparece
    execucao.reconciliar()
    assert _pos(pid)["status"] == "aberta"
    assert _banca() == pytest.approx(1000.0)                      # a banca NÃO desce por ela
    conta.fills = ler
    execucao.reconciliar()
    assert _pos(pid)["status"] == "fechada"
    assert _banca() == pytest.approx(conta.carteira)              # e a perda entrou uma vez só


def test_funding_das_abertas_nao_desce_a_banca_nem_entra_duas_vezes(conta):
    pid, _ = _abrir(conta)
    conta.carteira -= 30.0                                        # o funding saiu da carteira
    conta.renda.append({"tipo": "FUNDING_FEE", "valor": -30.0, "moeda": "USDT",
                        "simbolo": "BTC/USDT", "ts": pd.Timestamp.now()})
    execucao.reconciliar()
    assert _banca() == pytest.approx(1000.0)
    simulador.fechar(pid, "manual")
    assert _trades()[0]["funding"] == pytest.approx(-30.0)
    assert _banca() == pytest.approx(conta.carteira)


def test_alvos_pulados_seguem_no_trailing_e_nao_vao_para_o_ultimo(conta):
    pid, _ = _abrir(conta, valor=5.0, lev=1, preco=100.0)         # qty 0,05
    _com_plano(pid, [(110.0, 2.0, 0.004), (115.0, 3.0, 0.004), (120.0, 4.0, 0.992)])
    simulador.atualizar()
    tps = conta.abertas("TAKE_PROFIT_MARKET")
    assert [(o["gatilho"], o["qty"]) for o in tps] == [(120.0, 0.049)]
    plano = json.loads(_pos(pid)["tps"])
    assert plano["niveis"][0]["pulado"] and plano["niveis"][1]["pulado"]


def test_zero_a_zero_arma_pelo_preco_quando_o_tp1_foi_pulado(conta):
    db.set_config("tp_stop_entrada", "1", "teste")
    pid, _ = _abrir(conta, valor=5.0, lev=1, preco=100.0)         # qty 0,05
    _com_plano(pid, [(110.0, 2.0, 0.004), (120.0, 4.0, 0.5)], resto_livre=True)
    simulador.atualizar()
    assert json.loads(_pos(pid)["tps"])["niveis"][0]["pulado"]
    assert _pos(pid)["stop"] == 95.0                              # o preço ainda não chegou ao TP1
    conta.preco["BTC/USDT"] = 111.0
    simulador.atualizar()
    assert _pos(pid)["stop"] == pytest.approx(100.0)
    assert conta.abertas("STOP_MARKET")[0]["gatilho"] == pytest.approx(100.0)


def test_o_teto_por_ordem_e_medido_no_preco_do_claim_e_a_recusa_devolve_o_sinal(conta):
    sid = semear_sinal()
    conta.falhar_uma["abrir_mercado"] = C.AcimaDoTeto("nocional 300.2 > teto 300")
    with pytest.raises(ValueError, match="recusada"):
        simulador.executar(sid, 50.0, 2)
    assert _sinal(sid) == "novo"                                  # nada foi enviado: o sinal volta
    assert _ordens()[0]["status"] == "rejeitada" and not conta.abertas()    # e o stop saiu junto
    simulador.executar(sid, 50.0, 2)
    assert conta.ref_preco == pytest.approx(100.0)                # o preço que as guardas mediram


def test_o_stop_nunca_recua_quando_o_preco_volta(conta):
    pid, _ = _abrir(conta)
    conta.preco["BTC/USDT"] = 117.0
    simulador.atualizar()
    assert _pos(pid)["stop"] == pytest.approx(102.0)
    for preco in (116.2, 110.0, 103.0):
        conta.preco["BTC/USDT"] = preco
        simulador.atualizar()
        assert _pos(pid)["stop"] == pytest.approx(102.0)
        st = conta.abertas("STOP_MARKET")
        assert len(st) == 1 and st[0]["gatilho"] == pytest.approx(102.0)


def test_pico_da_noite_abaixo_do_stop_nao_o_baixa_de_manha(conta, monkeypatch):
    db.set_config("noite_ativo", "1", "teste")
    _hora(monkeypatch, "12:00")
    pid, _ = _abrir(conta)
    conta.preco["BTC/USDT"] = 117.0
    simulador.atualizar()
    assert _pos(pid)["stop"] == pytest.approx(102.0)
    _hora(monkeypatch, "22:00")
    simulador.atualizar()
    monkeypatch.setattr(simulador, "_velas_1m",
                        lambda ativo, a, b: [[0, 110, 116, 108, 110, 1]])   # pico 116: stop 101 < 102
    conta.preco["BTC/USDT"] = 110.0
    _hora(monkeypatch, "08:00")
    simulador.atualizar()
    assert _pos(pid)["stop"] == pytest.approx(102.0)
    assert conta.abertas("STOP_MARKET")[0]["gatilho"] == pytest.approx(102.0)


def test_teto_de_perda_total_conta_o_resultado_aberto(conta):
    pid, _ = _abrir(conta)
    db.set_config("perda_total_max", "20", "teste")
    with db.conectar() as c:
        c.execute("UPDATE posicoes SET pnl=-25 WHERE id=?", (pid,))
    assert _banca() == pytest.approx(1000.0)
    assert execucao.guarda_total()["travada"]


def test_panico_desliga_o_auto_trade_antes_de_tocar_na_corretora(cliente, conta, monkeypatch):
    """[P1-7]: a ORDEM importa, não só o estado final. Desligar depois deixaria o bot reabrir
    entre o fechamento e o desligamento."""
    db.set_config("auto_trade", "1", "teste")
    _abrir(conta)
    visto = {}
    real = execucao.panico

    def espia(*a, **k):
        visto["auto"] = db.get_config()["auto_trade"]
        return real(*a, **k)
    monkeypatch.setattr(execucao, "panico", espia)
    cliente.post("/panico")
    assert visto["auto"] == "0"


def test_panico_bate_o_watchdog_a_cada_item(conta):
    _abrir(conta)
    _abrir(conta, ativo="ETH/USDT")
    batidas = []
    execucao.panico(batida=lambda: batidas.append(1))
    assert len(batidas) >= 2 and not conta.pos


# ============================================================================ a API

@pytest.fixture
def cliente(conta):
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app, client=("127.0.0.1", 5555))


def test_panico_desliga_cancela_la_e_fecha_tudo(cliente, conta):
    db.set_config("auto_trade", "1", "teste")
    _abrir(conta)
    db.set_config("exec_modo", "post_only", "teste")
    simulador.executar(semear_sinal(ativo="ETH/USDT"), 50.0, 2)
    conta._abre("SOL/USDT", "LONG", 1.0, 100.0, conta._id(), Falsa.TAKER)   # fora do livro
    j = cliente.post("/panico").json()
    assert j["auto_desligado"] and db.get_config()["auto_trade"] == "0"
    assert j["fechadas"] == 1 and j["ordens_canceladas"] == 1
    assert not conta.pos and not conta.abertas()
    assert _ordens()[-1]["status"] == "cancelada" and _pos()[0]["status"] == "fechada"


def test_panico_com_a_ordem_ja_cheia_fecha_a_posicao_que_nasceu(cliente, conta):
    db.set_config("exec_modo", "post_only", "teste")
    simulador.executar(semear_sinal(), 50.0, 2)
    conta.encher(conta.abertas("LIMIT")[0]["id"])                 # encheu e o ciclo ainda não viu
    j = cliente.post("/panico").json()
    assert not conta.pos and not conta.abertas()
    assert j["fechadas"] == 1 and _trades()[0]["motivo_saida"] == "panico"


def test_ordem_cancelada_pelo_panico_antes_do_envio_nao_vai_para_a_corretora(conta):
    sid = semear_sinal()
    simulador.executar(sid, 50.0, 2)
    with db.conectar() as c:                                      # uma ordem gravada e já cancelada
        c.execute("INSERT INTO ordens(sinal_id,ativo,direcao,preco_limite,valor_reais,alavancagem,"
                  "stop,status,motivo,corretora,tipo,qty,client_oid) "
                  "VALUES(1,'ETH/USDT','LONG',100,50,2,95,'cancelada','panico','demo','mercado',1,'apxe9')")
        oid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    with pytest.raises(ValueError, match="antes do envio"):
        execucao._enviar_entrada(conta, execucao._ordem(oid))
    assert "ETH/USDT" not in conta.pos


def test_reset_e_recusado_na_conta_em_corretora(cliente, conta):
    pid, _ = _abrir(conta)
    r = cliente.post("/reset", json={"confirmar": "RESET"})
    assert r.status_code == 409 and _pos(pid)["status"] == "aberta"


def test_banco_com_historico_de_dinheiro_real_nao_reseta_nem_em_papel(cliente, conta):
    with db.conectar() as c:
        c.execute("INSERT INTO trades(ativo,direcao,pnl_reais,corretora) VALUES('BTC/USDT','LONG',1,'binance')")
    db.set_config("corretora", "papel", "teste")
    r = cliente.post("/reset", json={"confirmar": "RESET"})
    assert r.status_code == 409 and len(_trades()) == 1


def test_status_publica_a_saude_da_conta(cliente, conta):
    j = cliente.get("/status").json()
    assert j["corretora"]["modo"] == "demo" and j["corretora"]["reconciliacoes"] >= 1


def test_fechar_pela_rota_traduz_a_recusa_da_corretora(cliente, conta):
    pid, _ = _abrir(conta)
    conta.falhar["fechar_mercado"] = C.EnvioIncerto("timeout")
    j = cliente.post("/fechar", json={"id": pid}).json()
    assert j["ok"] is False and "reconciliação" in j["erro"]
    assert _pos(pid)["status"] == "aberta" and len(conta.abertas("STOP_MARKET")) == 1


# ---------------------------------------------------------------- a troca de modo

@pytest.fixture
def papel(banco, sem_rede, monkeypatch):
    """Banco em papel com a corretora falsa pronta para ser ligada pelo `POST /config`."""
    from fastapi.testclient import TestClient
    import api
    f = Falsa(carteira=5000.0)
    execucao.usar(f)
    execucao._reconciliado["mono"] = None
    monkeypatch.setenv("CORRETORA_HABILITADA", "1")
    yield TestClient(api.app, client=("127.0.0.1", 5555)), f
    execucao.usar(None)
    import push
    push.SIMBOLO = "R$"


def test_trocar_para_demo_renasce_a_banca_no_menor_entre_saldo_e_alocado(papel):
    cli, f = papel
    r = cli.post("/config", json={"corretora": "demo", "banca_alocada": 200})
    assert r.status_code == 200 and r.json()["corretora"] == "demo"
    b = db.get_banca()
    assert b["inicial"] == 200.0 and b["atual"] == 200.0          # saldo 5000, alocado 200
    import push
    assert push.SIMBOLO == "US$"


def test_sem_a_variavel_da_instancia_a_troca_e_recusada(papel, monkeypatch):
    cli, _ = papel
    monkeypatch.delenv("CORRETORA_HABILITADA")
    r = cli.post("/config", json={"corretora": "demo"})
    assert r.status_code == 422 and db.get_config()["corretora"] == "papel"
    assert db.get_banca()["atual"] == 1000.0


def test_a_troca_exige_o_livro_vazio(papel):
    cli, _ = papel
    simulador.abrir(semear_sinal(), 50.0, 2)
    r = cli.post("/config", json={"corretora": "demo"})
    assert r.status_code == 422 and "posição" in str(r.json())
    assert db.get_config()["corretora"] == "papel"


def test_a_troca_recusa_livro_com_historico_de_outro_modo(papel):
    cli, _ = papel
    simulador.fechar(simulador.abrir(semear_sinal(), 50.0, 2), "manual")
    r = cli.post("/config", json={"corretora": "demo"})
    assert r.status_code == 422 and "histórico" in str(r.json())


def test_a_troca_recusa_conta_com_posicao_ou_em_hedge(papel):
    cli, f = papel
    f.modo_hedge = True
    assert cli.post("/config", json={"corretora": "demo"}).status_code == 422
    f.modo_hedge = False
    f._abre("BTC/USDT", "LONG", 1.0, 100.0, f._id(), 0.0)
    assert cli.post("/config", json={"corretora": "demo"}).status_code == 422
    assert db.get_config()["corretora"] == "papel"


def test_a_troca_recusa_multi_ativos_e_modo_que_nao_se_leu(papel):
    """Revisão de 26/11: em Multi-Assets a margem isolada é recusada (-4168) e toda entrada
    sairia rejeitada no preparo; e modo NÃO LIDO é descobrir pela primeira ordem."""
    cli, f = papel
    for hedge, multi, palavra in ((False, True, "Multi-Assets"), (False, None, "Multi-Assets"),
                                  (None, False, "modo de posição")):
        f.modo_hedge, f.modo_multi = hedge, multi
        r = cli.post("/config", json={"corretora": "demo"})
        assert r.status_code == 422 and palavra in str(r.json()), (hedge, multi)
        assert db.get_config()["corretora"] == "papel"
    f.modo_hedge, f.modo_multi = False, False
    assert cli.post("/config", json={"corretora": "demo"}).status_code == 200


def test_chave_recusada_na_leitura_avisa_o_dono_uma_vez_e_diz_o_porque(conta, monkeypatch):
    avisos = []
    monkeypatch.setattr(execucao, "_avisar", lambda texto, nivel="error": avisos.append(texto))
    monkeypatch.setattr(execucao, "_avisado", {})
    conta.falhar["posicoes"] = C.ChaveRecusada("binance -2015 Invalid API-key, IP, or permissions")
    for _ in range(3):
        with pytest.raises(C.ChaveRecusada):
            execucao.reconciliar()
    assert len(avisos) == 1 and "chave" in avisos[0] and "IP" in avisos[0]
    conta.falhar["posicoes"] = C.LimiteDeTaxa("429")
    with pytest.raises(C.LimiteDeTaxa):
        execucao.reconciliar()
    assert len(avisos) == 2 and "limitou" in avisos[1]


def test_binance_exige_teto_de_perda_total_e_canal_de_alerta(papel):
    cli, _ = papel
    r = cli.post("/config", json={"corretora": "binance", "corretora_dry_run": 1})
    txt = str(r.json())
    assert r.status_code == 422 and "perda_total_max" in txt and "canal de alerta" in txt
    r = cli.post("/config", json={"corretora": "binance", "corretora_dry_run": 1, "perda_total_max": 60})
    assert r.status_code == 422 and "canal de alerta" in str(r.json())
    r = cli.post("/config", json={"corretora": "binance", "corretora_dry_run": 1, "perda_total_max": 60,
                                  "telegram_token": "t", "telegram_chat_id": "1"})
    assert r.status_code == 200 and db.get_config()["corretora"] == "binance"
    # e, já em binance, não dá para zerar o teto nem apagar o canal
    assert cli.post("/config", json={"perda_total_max": 0}).status_code == 422
    assert cli.post("/config", json={"telegram_token": ""}).status_code == 422
    assert db.get_config()["perda_total_max"] == "60.0"


def _em_binance(cli):
    r = cli.post("/config", json={"corretora": "binance", "corretora_dry_run": 1,
                                  "perda_total_max": 60, "corretora_nocional_max": 300,
                                  "telegram_token": "t", "telegram_chat_id": "1"})
    assert r.status_code == 200, r.text


def test_em_binance_a_senha_do_painel_so_aperta(papel):
    """Revisão de 26/11 (segurança): a senha do painel mora no navegador e é a das contas de
    papel. Em binance ela não sobe teto, banca nem alavancagem, nem solta a perda total."""
    cli, _ = papel
    _em_binance(cli)
    for corpo in ({"corretora_nocional_max": 500}, {"perda_total_max": 80},
                  {"risco_aberto_max": 0}, {"banca_alocada": 1000}, {"risco_por_trade": 0.05}):
        r = cli.post("/config", json=corpo)
        assert r.status_code == 422 and "só aperta" in str(r.json()), corpo
    cfg = db.get_config()
    alav = float(cfg.get("alavancagem_padrao") or 1)
    assert cli.post("/auto", json={"alavancagem_padrao": alav + 5}).status_code == 422
    assert cli.post("/config", json={"corretora_nocional_max": 100, "perda_total_max": 40}).status_code == 200
    assert cli.post("/auto", json={"alavancagem_padrao": 1}).status_code == 200
    cfg = db.get_config()
    assert float(cfg["corretora_nocional_max"]) == 100 and float(cfg["perda_total_max"]) == 40


def test_o_envio_de_verdade_so_liga_no_servidor(papel, capsys):
    cli, _ = papel
    _em_binance(cli)
    r = cli.post("/config", json={"corretora_dry_run": 0})
    assert r.status_code == 422 and db.get_config()["corretora_dry_run"] in ("1", "True", "true")
    # no servidor, pela linha de comando: o mesmo catálogo, e afrouxar pode
    assert execucao._cli(["config", "corretora_dry_run=0", "corretora_nocional_max=400"]) == 0
    out = capsys.readouterr().out
    assert "corretora_dry_run = " in out and "corretora_nocional_max = 400" in out
    cfg = db.get_config()
    assert cfg["corretora_dry_run"] not in ("1", "True", "true")
    # já real: o painel ainda só aperta, e o catálogo vale também na linha de comando
    assert cli.post("/config", json={"corretora_nocional_max": 450}).status_code == 422
    assert execucao._cli(["config", "corretora_nocional_max=banana"]) == 1
    assert execucao._cli(["config", "perda_total_max=0"]) == 1      # binance exige o teto


def test_no_demo_e_no_papel_a_senha_segue_livre(cliente, conta):
    assert cliente.post("/config", json={"corretora_nocional_max": 900}).status_code == 200


def test_a_troca_de_modo_exige_o_auto_desligado(papel):
    cli, _ = papel
    db.set_config("auto_trade", "1", "teste")
    r = cli.post("/config", json={"corretora": "demo"})
    assert r.status_code == 422 and "auto_trade" in str(r.json())
    assert db.get_config()["corretora"] == "papel"
    db.set_config("auto_trade", "0", "teste")
    assert cli.post("/config", json={"corretora": "demo"}).status_code == 200


def test_post_de_navegador_sem_json_e_recusado(cliente, conta, monkeypatch):
    """Um formulário de outra página é POST "simples": leva a credencial guardada sem preflight."""
    import api
    import base64
    from fastapi.testclient import TestClient
    monkeypatch.setattr(api, "DASH_PASS", "s3nha")
    monkeypatch.setattr(api, "DASH_USER", "admin")
    cli = TestClient(api.app, client=("127.0.0.1", 5555))
    cred = {"Authorization": "Basic " + base64.b64encode(b"admin:s3nha").decode()}
    fora = {**cred, "Origin": "https://pagina-qualquer.example"}
    db.set_config("auto_trade", "1", "teste")
    r = cli.post("/panico", headers={**fora, "Content-Type": "application/x-www-form-urlencoded"},
                 content=b"x=1")
    assert r.status_code == 403 and db.get_config()["auto_trade"] == "1"
    assert cli.post("/panico", headers=fora).status_code == 403            # fetch no-cors, sem tipo
    assert cli.post("/panico", headers=cred).status_code == 200            # curl / panico.sh
    assert db.get_config()["auto_trade"] == "0"


def test_status_do_papel_nao_carrega_a_saude_da_corretora(papel):
    cli, _ = papel
    execucao.usar(None)
    assert "corretora" not in cli.get("/status").json()


def test_so_o_panico_da_conta_real_espera_mais(monkeypatch):
    import api
    vistos = []

    class Resp:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    def abre(req, timeout):
        vistos.append(timeout)
        return Resp()
    monkeypatch.setattr(api.urllib.request, "urlopen", abre)
    for conta in ("B", "C", "R"):
        api._repassar(conta, "POST", "panico", "", b"", None, None)
    assert vistos == [30, 30, 170]


def test_estado_das_travas_nao_e_editavel_pelo_config(papel):
    cli, _ = papel
    assert cli.post("/config", json={"trava_total_em": ""}).status_code == 422
    assert cli.post("/config", json={"corretora_ns": "abc"}).status_code == 422


def test_hora_da_noite_e_validada(papel):
    cli, _ = papel
    assert cli.post("/config", json={"noite_inicio": "25:00"}).status_code == 422
    assert cli.post("/config", json={"noite_inicio": "18:30", "noite_fim": "07:30"}).status_code == 200


def test_dry_run_nao_liga_com_posicao_aberta_na_corretora(cliente, conta):
    """Parece cautela e é o contrário: em dry_run nem o fechamento nem o pânico são enviados."""
    _abrir(conta)
    r = cliente.post("/config", json={"corretora_dry_run": 1})
    assert r.status_code == 422 and db.get_config()["corretora_dry_run"] == "0"
    simulador.fechar(_pos()[0]["id"], "manual")
    assert cliente.post("/config", json={"corretora_dry_run": 1}).status_code == 200


def test_voltar_ao_papel_exige_a_conta_vazia_la_tambem(cliente, conta):
    conta._abre("SOL/USDT", "LONG", 1.0, 100.0, conta._id(), Falsa.TAKER)     # lá, fora do livro
    r = cliente.post("/config", json={"corretora": "papel"})
    assert r.status_code == 422 and db.get_config()["corretora"] == "demo"


def test_estado_da_conta_em_corretora_traz_as_colunas_dela(cliente, conta):
    _abrir(conta)
    j = cliente.get("/estado").json()
    assert j["posicoes"][0]["qty"] == 1.0 and j["posicoes"][0]["corretora"] == "demo"
    assert "corretora_dry_run" in j["config"] and "noite_ativo" in j["config"]


def test_a_troca_recusa_conta_com_ordem_aberta_de_antes(papel):
    """Uma condicional reduce-only esquecida dispara na primeira posição que o bot abrir."""
    cli, f = papel
    f._nova("BTC/USDT", "sell", "STOP_MARKET", 1.0, "outrobanco-s1", condicional=True,
            gatilho=90.0, reduce_only=True)
    r = cli.post("/config", json={"corretora": "demo"})
    assert r.status_code == 422 and db.get_config()["corretora"] == "papel"


def test_estado_do_papel_nao_carrega_o_vazio_da_corretora(papel):
    """O `/estado` é servido a cada 3 s nas quatro contas: no papel, as colunas e as chaves que
    só a conta em corretora usa não viajam."""
    cli, _ = papel
    execucao.usar(None)
    simulador.executar(semear_sinal(), 50.0, 2)
    j = cli.get("/estado").json()
    assert j["posicoes"] and j["config"]["corretora"] == "papel"
    for chave in ("qty", "corretora", "stop_ext_id", "client_oid", "funding_pago"):
        assert chave not in j["posicoes"][0]
    for chave in ("corretora_dry_run", "banca_alocada", "noite_ativo", "corretora_ns"):
        assert chave not in j["config"]
    assert "corretora_dry_run" in cli.get("/config").json()       # a rota de config traz tudo


def test_banco_em_modo_corretora_nao_sobe_em_instancia_de_papel(banco, monkeypatch):
    import api
    monkeypatch.delenv("CORRETORA_HABILITADA", raising=False)
    api._guarda_corretora()                                       # papel: sobe
    db.set_config("corretora", "binance", "teste")
    with pytest.raises(RuntimeError, match="CORRETORA_HABILITADA"):
        api._guarda_corretora()
    monkeypatch.setenv("CORRETORA_HABILITADA", "1")
    api._guarda_corretora()
    import push
    push.SIMBOLO = "R$"


def test_sem_a_variavel_o_adapter_nao_e_construido(banco, monkeypatch):
    monkeypatch.delenv("CORRETORA_HABILITADA", raising=False)
    execucao.usar(None)
    db.set_config("corretora", "demo", "teste")
    with pytest.raises(C.ErroCorretora, match="CORRETORA_HABILITADA"):
        execucao.obter()


# ============================================================================ o papel não mudou

def test_no_papel_nada_do_modulo_roda(banco, sem_rede, monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("o papel chamou a execução em corretora")
    for nome in ("executar", "fechar", "atualizar", "processar_ordens", "reconciliar", "obter"):
        monkeypatch.setattr(execucao, nome, proibido)
    pid = simulador.executar(semear_sinal(), 50.0, 2)[1]
    simulador.processar_ordens()
    simulador.atualizar()
    assert simulador.fechar(pid, "manual") is not None
    t = _trades()[0]
    assert t["corretora"] is None and t["qty"] is None and t["pnl_modelo"] is None


def test_o_prefixo_dos_ids_e_do_banco_e_nao_muda(conta):
    ns = execucao._ns()
    assert len(ns) == 6 and execucao._ns() == ns
    assert execucao._coid("e", 7) == f"ap{ns}e7" and execucao._coid("s", 7, 3) == f"ap{ns}s7n3"
    assert execucao._nosso(f"ap{ns}t1n2") and not execucao._nosso("ap000000e1")
    assert len(execucao._coid("s", 10 ** 9, 10 ** 6)) <= 36


# ============================================================================ a conta R

def test_a_conta_real_chega_pelo_repasse_da_A_e_so_por_ela(banco, monkeypatch):
    """[LIVE-5] /testeR repassa para a quarta instância. Só a A repassa; health público só em GET."""
    import base64
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from fastapi.testclient import TestClient
    import api

    vistos = []

    class R(BaseHTTPRequestHandler):
        def _ok(self):
            d = b'{"conta": "R"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(d)))
            self.end_headers()
            self.wfile.write(d)

        def do_GET(self):
            vistos.append(("GET", self.path, self.headers.get("Authorization")))
            self._ok()

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            vistos.append(("POST", self.path, self.headers.get("Authorization")))
            self._ok()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), R)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        cred = "Basic " + base64.b64encode(b"admin:s3nha").decode()
        monkeypatch.setattr(api, "REAL_URL", f"http://127.0.0.1:{srv.server_address[1]}")
        monkeypatch.setattr(api, "DASH_PASS", "s3nha")
        monkeypatch.setattr(api, "DASH_USER", "admin")
        monkeypatch.setattr(api, "CONTA", "A")
        cli = TestClient(api.app, client=("127.0.0.1", 5555))
        assert cli.get("/testeR/health").json() == {"conta": "R"}          # a vigia lê sem senha
        assert cli.post("/testeR/panico").status_code == 401               # o resto exige a senha
        assert cli.post("/testeR/panico", headers={"Authorization": cred}).status_code == 200
        assert vistos[-1] == ("POST", "/panico", cred)                     # e a R confere de novo
        monkeypatch.setattr(api, "REAL_URL", "http://127.0.0.1:9")
        r = cli.get("/testeR/estado", headers={"Authorization": cred})
        assert r.status_code == 502 and "Conta real fora do ar" in r.text
        for outra in ("B", "C", "R"):                                      # só a A repassa
            monkeypatch.setattr(api, "CONTA", outra)
            assert cli.get("/testeR/estado", headers={"Authorization": cred}).status_code == 404
    finally:
        srv.shutdown()


def test_panico_pela_linha_de_comando_desliga_cancela_e_fecha(conta, capsys):
    """O caminho do `deploy/panico.sh` quando o serviço não responde."""
    db.set_config("auto_trade", "1", "teste")
    _abrir(conta)
    assert execucao._cli(["estado"]) == 0
    assert "1 posição(ões)" in capsys.readouterr().out and conta.pos   # `estado` só lê
    assert execucao._cli(["panico"]) == 0
    assert db.get_config()["auto_trade"] == "0" and not conta.pos and not conta.abertas()
    assert _trades()[0]["motivo_saida"] == "panico"
    assert execucao._cli(["panico"]) == 0                              # duas vezes: seguro
    assert execucao._cli([]) == 2 and execucao._cli(["outro"]) == 2


def test_linha_de_comando_em_conta_de_papel_nao_toca_em_nada(banco, capsys):
    execucao.usar(None)
    assert execucao._cli(["panico"]) == 0
    assert "papel" in capsys.readouterr().out and db.get_config()["auto_trade"] == "0"


# ============================================================================ o pânico visto do painel

def test_panico_pela_rota_diz_o_que_a_varredura_fechou_fora_do_livro(cliente, conta):
    """[LIVE-6] Posição que a conta tinha e o livro não: a varredura fecha, e a resposta diz."""
    conta._abre("SOL/USDT", "LONG", 1.0, 100.0, conta._id(), Falsa.TAKER)
    j = cliente.post("/panico").json()
    assert j["ok"] and j["fechadas"] == 0 and not conta.pos
    assert [v["ativo"] for v in j["varridas"]] == ["SOL/USDT"]


def test_o_repasse_espera_o_panico_da_corretora_e_nao_chama_demora_de_fora_do_ar(banco, monkeypatch):
    """[LIVE-6] O pânico na corretora fecha posição por posição lá e passa de 30 s. A conta A
    espera por ele o que o `deploy/panico.sh` espera; e tempo esgotado não é "fora do ar": a
    requisição chegou, a ação pode ter sido executada, e a resposta diz isso."""
    from fastapi.testclient import TestClient
    import api
    esperas = []

    class _Resposta:
        status = 200
        headers = {"Content-Type": "application/json"}

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def abre(req, timeout=None):
        rota = req.full_url.rsplit("/", 1)[-1]
        esperas.append((rota, timeout))
        if rota == "fechar":
            raise TimeoutError("timed out")
        return _Resposta()

    monkeypatch.setattr(api, "CONTA", "A")
    monkeypatch.setattr(api.urllib.request, "urlopen", abre)
    cli = TestClient(api.app, client=("127.0.0.1", 5555))
    assert cli.post("/testeR/panico").status_code == 200
    assert cli.get("/testeR/estado").status_code == 200
    assert esperas == [("panico", 170), ("estado", 30)]
    r = cli.post("/testeR/fechar", json={"id": 1})
    assert r.status_code == 504 and "Conta real não respondeu a tempo" in r.text
    assert "PODE ter sido executada" in r.text and "fora do ar" not in r.text


# ============================================================================ o que é só de papel

def test_dca_nao_cria_plano_na_conta_em_corretora(cliente, conta):
    """[LIVE-6] O DCA soma unidades numa tabela e não compra nada: na conta que opera em
    corretora ele mostraria "acumulado" de moeda que nunca foi comprada."""
    import dca
    j = cliente.post("/dca", json={"ativo": "BTC/USDT", "valor_aporte": 50, "freq_dias": 7}).json()
    assert j["ok"] is False and "simulação" in j["erro"]
    with pytest.raises(ValueError, match="simulação"):
        dca.criar("BTC/USDT", 50, 7)
    with db.conectar() as c:
        assert c.execute("SELECT COUNT(*) FROM dca").fetchone()[0] == 0


def test_plano_de_dca_do_papel_para_de_aportar_quando_a_conta_vai_para_a_corretora(banco, sem_rede):
    import dca
    from fastapi.testclient import TestClient
    import api
    dca.criar("BTC/USDT", 50, 7)
    dca.processar_devidos()                                    # no papel o 1º aporte sai no 1º ciclo
    with db.conectar() as c:
        pid, n = c.execute("SELECT id, n_aportes FROM dca").fetchone()
        assert n == 1
        c.execute("UPDATE dca SET ultimo_aporte='1970-01-01 00:00:00'")     # vencido de novo
    db.set_config("corretora", "demo", "teste")
    dca.processar_devidos()                                    # o worker passa e não aporta
    cli = TestClient(api.app, client=("127.0.0.1", 5555))
    j = cli.post("/dca/aportar", json={"id": pid}).json()      # nem à mão
    assert j["ok"] is False and "simulação" in j["erro"]
    with db.conectar() as c:
        assert c.execute("SELECT n_aportes, total_investido FROM dca").fetchone()[:] == (1, 50.0)
    assert cli.post("/dca/remover", json={"id": pid}).json() == {"ok": True}   # remover segue valendo


# ============================================================================ prova ao vivo (demo)
# Roda só com RODAR_DEMO=1 e a chave do Demo Trading no ambiente. Manda ordens DE VERDADE para a
# Binance Demo (dinheiro de mentira): é a prova de que o livro e a conta batem, negócio a
# negócio, e de que nada fica para trás. Deixa a conta limpa: zero posição, zero ordem.

import os                                                          # noqa: E402
import time as _time                                               # noqa: E402

_DEMO = (os.environ.get("RODAR_DEMO") == "1" and os.environ.get("BINANCE_DEMO_KEY")
         and os.environ.get("BINANCE_DEMO_SECRET"))


@pytest.mark.skipif(not _DEMO, reason="prova ao vivo: RODAR_DEMO=1 e BINANCE_DEMO_KEY/SECRET no ambiente")
class TestDemoAoVivo:
    S = "SOL/USDT"

    @pytest.fixture
    def c(self, banco, monkeypatch):
        monkeypatch.setenv("CORRETORA_HABILITADA", "1")
        execucao.usar(None)
        for k, v in (("corretora", "demo"), ("corretora_nocional_max", "60"), ("tp_ativo", "0"),
                     ("exposicao_max", "0.5"), ("risco_aberto_max", "0.5")):
            db.set_config(k, v, "prova demo")
        with db.conectar() as con:
            con.execute("UPDATE banca SET inicial=200, atual=200 WHERE id=1")
        c = execucao.obter()
        if c.posicoes():
            pytest.skip("a conta demo tem posição aberta: a reconciliação a adotaria. Limpe antes.")
        c.cancelar_tudo(self.S)
        execucao._reconciliado["mono"] = None
        yield c
        try:                                                       # limpa SEMPRE, passe ou falhe
            c.cancelar_tudo(self.S)
            for p in c.posicoes():
                if p["simbolo"] == self.S:
                    c.fechar_mercado(self.S, p["direcao"], p["qty"], f"limpa-{pd.Timestamp.now():%H%M%S%f}")
            c.cancelar_tudo(self.S)
        finally:
            execucao._cache.update(chave=None, obj=None)
            execucao._reconciliado["mono"] = None

    @staticmethod
    def _ate(cond, segundos=25.0, passo=1.0):
        fim = _time.monotonic() + segundos
        while _time.monotonic() < fim:
            if cond():
                return True
            _time.sleep(passo)
        return cond()

    def _abertas(self, c, tipo=None):
        return [o for o in c.ordens_abertas(self.S) if tipo is None or o["tipo"] == tipo]

    def _sinal(self, c, stop_frac=0.03):
        m = c.marks([self.S])[self.S]
        return semear_sinal(ativo=self.S, direcao="LONG", preco=m, stop=m * (1 - stop_frac)), m

    def test_roteiro(self, c):
        inicio = pd.Timestamp.now()
        execucao.reconciliar()

        # 1. entrada a mercado: posição lá, stop lá, livro igual
        sid, m = self._sinal(c)
        tipo, pid = simulador.executar(sid, 4.0, 5)                # nocional ~20 USDT
        assert tipo == "posicao"
        p = _pos(pid)
        (px,) = [x for x in c.posicoes() if x["simbolo"] == self.S]
        assert px["qty"] == pytest.approx(p["qty"]) and px["direcao"] == "LONG"
        assert p["entrada"] == pytest.approx(px["entrada"], rel=1e-6)
        assert self._ate(lambda: p["stop_ext_id"] in {o["id"] for o in self._abertas(c)})
        (st,) = self._abertas(c, "STOP_MARKET")
        assert st["gatilho"] == pytest.approx(p["stop"]) and st["client_oid"] == p["stop_coid"]

        # 2. o stop sobe: novo lá, antigo cancelado, livro com o número que a corretora tem
        antigo = p["stop_ext_id"]
        assert execucao._garantir_stop(c, p, p["stop"] * 1.005)
        p = _pos(pid)
        assert p["stop_ext_id"] != antigo
        assert self._ate(lambda: [o["id"] for o in self._abertas(c, "STOP_MARKET")] == [p["stop_ext_id"]])
        assert self._abertas(c, "STOP_MARKET")[0]["gatilho"] == pytest.approx(p["stop"])

        # 3. alvos viram ordens (metade em +5%, resto livre)
        _com_plano(pid, [(c.preco_valido(self.S, m * 1.05), 1.7, 0.5)], resto_livre=True)
        simulador.atualizar()
        assert self._ate(lambda: len(self._abertas(c, "TAKE_PROFIT_MARKET")) == 1)
        (tp,) = self._abertas(c, "TAKE_PROFIT_MARKET")
        assert tp["qty"] == pytest.approx(c.arredondar(self.S, p["qty"] * 0.5, reduz=True)[0])

        # 4. a posição fecha POR FORA (como um stop que disparou sem o bot ver): a reconciliação
        #    lança com o negócio real e cancela o que ficou órfão
        c.fechar_mercado(self.S, "LONG", p["qty"], f"fora-{pd.Timestamp.now():%H%M%S%f}")

        def reconciliou():
            execucao.reconciliar()
            return _pos(pid)["status"] == "fechada"
        assert self._ate(reconciliou, 40.0, 2.0)
        t1 = _trades()[-1]
        assert t1["motivo_saida"] == "externo" and t1["corretora"] == "demo"
        assert t1["qty"] == pytest.approx(p["qty"]) and t1["taxa"] > 0

        def sem_ordens():
            execucao.reconciliar()
            return self._abertas(c) == []
        assert self._ate(sem_ordens, 30.0, 2.0)                    # stop e alvo órfãos cancelados

        # 5. segunda posição, fechada pelo livro (rota /fechar): limpa as condicionais dela
        sid, m = self._sinal(c)
        _, pid2 = simulador.executar(sid, 4.0, 5)
        assert self._ate(lambda: len(self._abertas(c, "STOP_MARKET")) == 1)
        # 5b. trailing da noite de posição JÁ armada: vai sem preço de ativação, a Binance
        #     aceita e ele aparece lá. O fechamento logo abaixo tem de cancelá-lo junto.
        armado = {"on": True, "unidade": "R", "arma_r": -1.0, "dist_r": 1.0}
        execucao._trailing_da_noite(c, _pos(pid2), c.marks([self.S])[self.S], armado)
        nt = json.loads(_pos(pid2)["noite"])
        assert nt["ativacao"] is None and nt["id"]
        assert self._ate(lambda: [o["id"] for o in self._abertas(c, "TRAILING_STOP_MARKET")] == [nt["id"]])
        pnl2 = simulador.fechar(pid2, "manual")
        assert pnl2 is not None and _pos(pid2)["status"] == "fechada"
        assert self._ate(lambda: self._abertas(c) == [] and
                         not any(x["simbolo"] == self.S for x in c.posicoes()))

        # 6. post-only que não enche: descansa com o stop junto, vence e some de lá
        db.set_config("exec_modo", "post_only", "prova demo")
        db.set_config("exec_maker_off", "0.03", "prova demo")      # 3% abaixo: não enche
        db.set_config("exec_ordem_ttl_s", "0", "prova demo")       # já nasce vencida
        sid, m = self._sinal(c)
        tipo, oid = simulador.executar(sid, 4.0, 5)
        assert tipo == "ordem"
        assert self._ate(lambda: {o["tipo"] for o in self._abertas(c)} == {"LIMIT", "STOP_MARKET"})
        _time.sleep(execucao.FOLGA_LEITURA_S + 1)
        simulador.processar_ordens()
        assert _ordens()[-1]["status"] == "expirada"
        assert self._ate(lambda: self._abertas(c) == [])

        # 7. o livro bate com a conta: o realizado do livro == o que a Binance lançou
        def renda():
            linhas = c.income(self.S, C.sp_para_ms(inicio - pd.Timedelta(seconds=5)))
            return sum(x["valor"] or 0 for x in linhas
                       if x["tipo"] in ("REALIZED_PNL", "COMMISSION", "FUNDING_FEE") and x["ts"] >= inicio)
        livro = sum(t["pnl_reais"] for t in _trades())
        assert self._ate(lambda: abs(renda() - livro) < 0.02, 30.0, 3.0), (renda(), livro)
        assert _banca() == pytest.approx(200.0 + livro)
        with db.conectar() as con:
            n = con.execute("SELECT COUNT(*) FROM fills").fetchone()[0]
        assert n >= 4                                              # 2 entradas + 2 saídas
        assert not [x for x in _pos() if x["status"] == "aberta"]
