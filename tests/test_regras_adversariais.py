# -*- coding: utf-8 -*-
"""Regras de negocio atacadas de proposito: cada teste afirma a REGRA e falha se ela estiver
furada. Nasceram de uma auditoria adversarial em 2026-11-12, contra a `main` d628f8f: 55
cenarios, 16 furados. Os furos foram fechados no mesmo commit que trouxe este arquivo; os 39
que ja passavam ficam aqui como cerca, porque sao exatamente as regras do CLAUDE.md §2 que um
refactor quebraria sem ninguem ver (trava sticky, claim atomico, tetos antes do claim,
pendente nos tetos, panico desligando antes de fechar, conservacao de taxa e P&L).

Os nomes `test_<n><letra>` seguem a numeracao da auditoria: 1 trava, 2 claim, 3 tetos,
4 panico, 5 taxa e P&L, 6 liquidacao, 7 fechamento, 8 DCA, 9 config e entrada, 10 reset.
"""
import threading

import pandas as pd
import pytest

import autotrader
import db
import dca
import simulador
from conftest import semear_equity, semear_posicao, semear_sinal


@pytest.fixture
def cliente(banco):
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app, client=("127.0.0.1", 5555))


def hoje():
    return str(pd.Timestamp.now().date())


def _sinal_status(sid):
    with db.conectar() as c:
        return c.execute("SELECT status FROM sinais WHERE id=?", (sid,)).fetchone()[0]


def _n(tabela, where=""):
    with db.conectar() as c:
        return c.execute(f"SELECT COUNT(*) FROM {tabela} {where}").fetchone()[0]


def _travar_e_recuperar():
    """Equity do inicio do dia 1000; posicao com unreal -60 (limite 5% = 50) -> trava.
    Depois o unreal volta a 0: a trava tem de continuar (sticky)."""
    semear_equity(hoje() + " 00:00:01", 1000.0)
    pid = semear_posicao(pnl=-60.0)
    assert simulador.guarda_risco()["trava_dia"] is True
    with db.conectar() as c:
        c.execute("UPDATE posicoes SET pnl=0 WHERE id=?", (pid,))
    return pid


def _auto_on(**extra):
    db.set_config("auto_trade", "1")
    db.set_config("tendencia_filtro", "off")
    for k, v in extra.items():
        db.set_config(k, v)


# =============================================================== 1. trava diaria
def test_1a_trava_sticky_e_por_equity_nao_por_realizado(banco, sem_rede):
    semear_equity(hoje() + " 00:00:01", 1000.0)
    with db.conectar() as c:      # realizado do dia POSITIVO (+34,68), equity -80 -> trava
        c.execute("INSERT INTO trades(ativo,direcao,pnl_reais,fechado_em) VALUES('X','LONG',34.68,?)",
                  (str(pd.Timestamp.now()),))
        c.execute("UPDATE banca SET atual=atual+34.68")
    pid = semear_posicao(pnl=-114.68)
    g = simulador.guarda_risco()
    assert g["realizado_hoje"] > 0 and g["trava_dia"] is True
    with db.conectar() as c:
        c.execute("UPDATE posicoes SET pnl=0 WHERE id=?", (pid,))
    assert simulador.guarda_risco()["trava_dia"] is True          # nao solta no mesmo dia


def test_1b_trava_solta_na_virada(banco, sem_rede):
    db.set_config("trava_dia_em", str((pd.Timestamp.now() - pd.Timedelta(days=1)).date()))
    semear_equity(hoje() + " 00:00:01", 1000.0)
    assert simulador.guarda_risco()["trava_dia"] is False


def test_1c_nenhuma_rota_de_abertura_fura_a_trava(cliente, sem_rede):
    _travar_e_recuperar()
    sid = semear_sinal(ts=str(pd.Timestamp.now()))
    r = cliente.post("/confirmar", json={"sinal_id": sid, "valor_reais": 20, "alavancagem": 2}).json()
    assert r["ok"] is False
    _auto_on()
    res = autotrader.auto_executar()
    assert res.get("abertos", []) == []
    db.set_config("exec_modo", "post_only")
    with pytest.raises(ValueError):
        simulador.colocar_ordem(sid, 20, 2)
    assert _sinal_status(sid) == "novo"          # recusa pela trava nao consome o sinal
    assert _n("posicoes", "WHERE sinal_id IS NOT NULL") == 0


def test_1d_POST_config_nao_pode_limpar_a_trava_no_mesmo_dia(cliente, sem_rede):
    """CLAUDE.md §2: 'Limpar trava_dia_em a mao = relaxar invariante'. O catalogo do
    POST /config aceita a chave `trava_dia_em` (api.py:420)."""
    _travar_e_recuperar()
    r = cliente.post("/config", json={"trava_dia_em": ""})
    sid = semear_sinal(ts=str(pd.Timestamp.now()))
    aberto = cliente.post("/confirmar", json={"sinal_id": sid, "valor_reais": 20,
                                              "alavancagem": 2}).json()
    assert r.status_code == 422 and simulador.guarda_risco()["trava_dia"] is True, \
        f"POST /config respondeu {r.status_code}; trava agora={simulador.guarda_risco()['trava_dia']}; /confirmar={aberto}"


def test_1e_auto_e_perfil_nao_alcancam_a_trava(cliente, sem_rede):
    _travar_e_recuperar()
    assert cliente.post("/auto", json={"trava_dia_em": ""}).status_code == 422
    for p in ("experimento", "conservador"):
        cliente.post("/perfil", json={"perfil": p})
        assert simulador.guarda_risco()["trava_dia"] is True


def test_1f_limite_zero_trava_so_com_perda(cliente, sem_rede):
    """Catalogo (api.py:355): `limite_perda_dia` 0 = 'trava no primeiro centavo de PERDA'.
    Sem perda nenhuma o dia nao pode travar."""
    assert cliente.post("/config", json={"limite_perda_dia": "0"}).status_code == 200
    semear_equity(hoje() + " 00:00:01", 1000.0)
    g = simulador.guarda_risco()
    assert g["pnl_dia"] == 0 and g["trava_dia"] is False, g


# =============================================================== 2. claim atomico
def test_2a_confirmar_duas_vezes_em_sequencia(cliente, sem_rede):
    sid = semear_sinal()
    r1 = cliente.post("/confirmar", json={"sinal_id": sid, "valor_reais": 20, "alavancagem": 2}).json()
    r2 = cliente.post("/confirmar", json={"sinal_id": sid, "valor_reais": 20, "alavancagem": 2}).json()
    assert r1["ok"] is True and r2["ok"] is False
    assert _n("posicoes") == 1


@pytest.mark.parametrize("modo", ["mercado", "post_only"])
def test_2b_confirmar_concorrente_8_threads(banco, sem_rede, modo):
    db.set_config("exec_modo", modo)
    sid = semear_sinal()
    ok, barreira = [], threading.Barrier(8)

    def go():
        barreira.wait()
        try:
            ok.append(simulador.executar(sid, 20, 2))
        except ValueError:
            pass
    ts = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(ok) == 1
    assert _n("posicoes") + _n("ordens") == 1


@pytest.mark.parametrize("status", ["expirado", "pulado", "confirmado", "rejeitado_fluxo"])
def test_2c_confirmar_sinal_fora_da_fila_e_recusado(cliente, sem_rede, status):
    sid = semear_sinal(status=status)
    r = cliente.post("/confirmar", json={"sinal_id": sid, "valor_reais": 20, "alavancagem": 2}).json()
    assert r["ok"] is False and _n("posicoes") == 0


@pytest.mark.parametrize("status", ["confirmado", "expirado", "rejeitado_fluxo"])
def test_2d_pular_nao_reescreve_sinal_fora_da_fila(cliente, sem_rede, status):
    """/pular (api.py:1205-1209) faz UPDATE sem `AND status='novo'`."""
    sid = semear_sinal(status=status)
    cliente.post("/pular", json={"id": sid})
    assert _sinal_status(sid) == status


def test_2d2_pular_um_sinal_que_ja_virou_posicao(cliente, sem_rede):
    sid = semear_sinal()
    pid = cliente.post("/confirmar", json={"sinal_id": sid, "valor_reais": 20,
                                           "alavancagem": 2}).json()["posicao_id"]
    cliente.post("/pular", json={"id": sid})
    with db.conectar() as c:
        st = c.execute("SELECT status FROM posicoes WHERE id=?", (pid,)).fetchone()[0]
    assert (st, _sinal_status(sid)) == ("aberta", "confirmado")


def test_2e_auto_trader_e_manual_disputam_o_mesmo_sinal(banco, sem_rede):
    _auto_on()
    sid = semear_sinal(ts=str(pd.Timestamp.now()))
    barreira = threading.Barrier(2)
    erros = []

    def manual():
        barreira.wait()
        try:
            simulador.abrir(sid, 20, 2)
        except ValueError as e:
            erros.append(str(e))

    def bot():
        barreira.wait()
        autotrader.auto_executar()
    ts = [threading.Thread(target=manual), threading.Thread(target=bot)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    with db.conectar() as c:
        n = c.execute("SELECT COUNT(*) FROM posicoes WHERE sinal_id=?", (sid,)).fetchone()[0]
    assert n == 1


# =============================================================== 3. tetos
def test_3a_recusa_por_teto_de_risco_nao_consome_o_sinal(banco, sem_rede):
    semear_posicao(valor_reais=100, alavancagem=10, entrada=100, stop=95)   # risco 50 > ... teto 100
    semear_posicao(valor_reais=100, alavancagem=10, entrada=100, stop=95)   # 2 x 50 = 100 = teto
    sid = semear_sinal()
    with pytest.raises(ValueError, match="teto de risco"):
        simulador.abrir(sid, 20, 2)
    assert _sinal_status(sid) == "novo"


def test_3b_ordem_pendente_conta_no_teto_de_RISCO_nos_dois_caminhos(banco, sem_rede):
    db.set_config("exec_modo", "post_only")
    simulador.colocar_ordem(semear_sinal(ativo="ETH/USDT"), 100, 10)   # risco ~50
    simulador.colocar_ordem(semear_sinal(ativo="SOL/USDT"), 80, 10)    # risco ~40 -> 90 de 100
    s_ord, s_mkt = semear_sinal(), semear_sinal()        # +20 de risco; margem 380 < 500
    with pytest.raises(ValueError, match="teto de risco"):
        simulador.colocar_ordem(s_ord, 200, 2)
    with pytest.raises(ValueError, match="teto de risco"):
        simulador.abrir(s_mkt, 200, 2)
    assert _sinal_status(s_ord) == "novo" and _sinal_status(s_mkt) == "novo"


def test_3c_auto_max_posicoes_conta_ordem_pendente(banco, sem_rede):
    """auto_max_posicoes=1 em post_only: o bot nao pode ter 2 ordens/posicoes vivas.
    autotrader.py:239-241 conta so `posicoes` abertas."""
    _auto_on(exec_modo="post_only", auto_max_posicoes="1")
    semear_sinal(ativo="BTC/USDT", ts=str(pd.Timestamp.now()))
    autotrader.auto_executar()                                  # ciclo 1: ordem BTC
    semear_sinal(ativo="ETH/USDT", ts=str(pd.Timestamp.now()))
    autotrader.auto_executar()                                  # ciclo 2: nao devia colocar
    n_ordens = _n("ordens", "WHERE status='pendente'")
    sem_rede(99.0)
    simulador.processar_ordens()
    n_pos = _n("posicoes", "WHERE status='aberta'")
    assert n_ordens <= 1 and n_pos <= 1, f"ordens pendentes={n_ordens}, posicoes apos fill={n_pos} (max=1)"


def test_3d_auto_trader_nao_duplica_ativo_com_ordem_pendente(banco, sem_rede):
    _auto_on(exec_modo="post_only")
    semear_sinal(ativo="BTC/USDT", ts=str(pd.Timestamp.now()))
    autotrader.auto_executar()
    semear_sinal(ativo="BTC/USDT", ts=str(pd.Timestamp.now()), conviccao=95)
    autotrader.auto_executar()
    sem_rede(99.0)
    simulador.processar_ordens()
    with db.conectar() as c:
        n = c.execute("SELECT COUNT(*) FROM posicoes WHERE ativo='BTC/USDT' AND status='aberta'").fetchone()[0]
    assert n <= 1, f"{n} posicoes BTC/USDT simultaneas (mercado barraria em ativos_abertos)"


# =============================================================== 4. panico
def test_4a_panico_desliga_antes_de_fechar(cliente, sem_rede, monkeypatch):
    db.set_config("auto_trade", "1")
    semear_posicao()
    visto = []
    orig = simulador.fechar

    def espia(*a, **k):
        visto.append(db.get_config()["auto_trade"])
        return orig(*a, **k)
    monkeypatch.setattr(simulador, "fechar", espia)
    cliente.post("/panico")
    assert visto == ["0"]


def test_4b_ordem_pendente_nao_vira_posicao_depois_do_panico(cliente, sem_rede):
    _auto_on(exec_modo="post_only")
    semear_sinal(ts=str(pd.Timestamp.now()))
    autotrader.auto_executar()
    assert _n("ordens", "WHERE status='pendente'") == 1
    cliente.post("/panico")
    sem_rede(99.0)
    simulador.processar_ordens()
    cfg = db.get_config()
    n = _n("posicoes", "WHERE status='aberta'")
    assert n == 0, f"{n} posicao aberta apos panico, com auto_trade={cfg['auto_trade']}"


# =============================================================== 5. taxas e P&L
def test_5a_round_trip_mercado_preco_menos_taxa(banco, sem_rede):
    sid = semear_sinal()
    pid = simulador.abrir(sid, 50, 2)
    sem_rede(110.0)
    pnl = simulador.fechar(pid, "manual")
    assert pnl == pytest.approx(50 * 2 * 0.10 - 2 * 0.0005 * 100)
    assert db.get_banca()["atual"] == pytest.approx(1000 + pnl)


def test_5b_round_trip_post_only_maker_so_na_entrada(banco, sem_rede):
    db.set_config("exec_modo", "post_only")
    sid = semear_sinal()
    _, oid = simulador.executar(sid, 50, 2)
    sem_rede(99.0)
    simulador.processar_ordens()
    with db.conectar() as c:
        pid = c.execute("SELECT posicao_id FROM ordens WHERE id=?", (oid,)).fetchone()[0]
    db.set_config("taxa_maker", "0.009")          # mudar config depois NAO muda a entrada gravada
    sem_rede(110.0)
    pnl = simulador.fechar(pid, "manual")
    with db.conectar() as c:
        t = dict(c.execute("SELECT * FROM trades").fetchone())
    assert t["taxa"] == pytest.approx((0.0002 + 0.0005) * 100)
    assert pnl == pytest.approx(50 * 2 * (110 / 99.9 - 1) - t["taxa"])


def test_5c_funding_entra_no_pnl(banco, sem_rede, monkeypatch):
    class F:
        def fetch_funding_rate_history(self, ativo, since=None, limit=None):
            return [{"timestamp": since + 1, "fundingRate": 0.001}]
    monkeypatch.setattr(simulador, "ex_fut", F())
    pid = semear_posicao(valor_reais=50, alavancagem=2, aberto_em=str(pd.Timestamp.now() - pd.Timedelta(hours=9)))
    pnl = simulador.fechar(pid, "manual", 100.0)
    assert pnl == pytest.approx(-0.1 - 0.001 * 100)


def test_5d_parciais_somam_o_fechamento_inteiro(banco, sem_rede):
    ids = [semear_posicao(valor_reais=90, alavancagem=3) for _ in range(2)]
    for i in ids:
        with db.conectar() as c:
            c.execute("UPDATE posicoes SET risco_abertura=13.5 WHERE id=?", (i,))
    inteiro = simulador.fechar(ids[0], "x", 107.3)
    b0 = db.get_banca()["atual"]
    with db.conectar() as c:
        pos = dict(c.execute("SELECT * FROM posicoes WHERE id=?", (ids[1],)).fetchone())
    resto = simulador.fechar_parcial(pos, 0.34, "tp1", 107.3, {"niveis": []})
    pos["valor_reais"] = resto
    resto = simulador.fechar_parcial(pos, 0.5, "tp2", 107.3, {"niveis": []})
    simulador.fechar(ids[1], "tp3", 107.3)
    with db.conectar() as c:
        soma = c.execute("SELECT SUM(pnl_reais), SUM(taxa) FROM trades WHERE id>1").fetchone()
    assert soma[0] == pytest.approx(inteiro, abs=1e-9)
    assert db.get_banca()["atual"] - b0 == pytest.approx(inteiro, abs=1e-9)


# =============================================================== 6. liquidacao
def test_6a_manual_recusa_liquidacao_antes_do_stop(banco, sem_rede):
    sid = semear_sinal(stop=95.0)                     # stop 5% -> lev max 18x
    with pytest.raises(ValueError, match="geometria"):
        simulador.abrir(sid, 20, 20)
    assert _sinal_status(sid) == "novo"


@pytest.mark.parametrize("modo,extra", [("fixo", {"alavancagem_padrao": "50"}),
                                        ("conviccao", {"auto_lev_max": "50", "auto_lev_min": "50"}),
                                        ("risco", {"auto_lev_max": "50", "risco_por_trade": "0.1", "risco_aberto_max": "0", "auto_max_valor_frac": "1"})])
def test_6b_auto_trader_capa_a_mesma_geometria(banco, sem_rede, modo, extra):
    _auto_on(auto_lev_modo=modo, **extra)
    semear_sinal(stop=95.0, ts=str(pd.Timestamp.now()))
    res = autotrader.auto_executar()
    with db.conectar() as c:
        p = c.execute("SELECT entrada,stop,alavancagem FROM posicoes").fetchone()
    assert p is not None, res
    assert simulador._liq_antes_do_stop(p["entrada"], p["stop"], p["alavancagem"], 1) is None


# =============================================================== 7. fechar duas vezes
def test_7a_fechar_duas_vezes_credita_uma(cliente, sem_rede):
    pid = semear_posicao()
    sem_rede(110.0)
    r1 = cliente.post("/fechar", json={"id": pid}).json()
    r2 = cliente.post("/fechar", json={"id": pid}).json()
    assert r2["pnl"] is None and db.get_banca()["atual"] == pytest.approx(1000 + r1["pnl"])
    assert _n("trades") == 1


def test_7b_fechar_manual_concorrente_com_TP_parcial_nao_credita_em_dobro(banco, sem_rede, monkeypatch):
    """/fechar le a posicao (valor_reais=100), vai a rede (preco + funding) e so entao faz
    `UPDATE ... WHERE id=? AND status='aberta'` -- sem conferir valor_reais. Se no meio disso o
    worker realiza um TP parcial (fechar_parcial reduz valor_reais e credita a parcela), o
    fechamento manual credita a posicao INTEIRA de novo."""
    pid = semear_posicao(valor_reais=100, alavancagem=2, entrada=100, stop=95)
    feito = {"v": False}
    orig = simulador._funding_custo

    def no_meio(*a, **k):                       # roda entre a leitura e a escrita de fechar()
        if not feito["v"]:
            feito["v"] = True
            with db.conectar() as c:
                pos = dict(c.execute("SELECT * FROM posicoes WHERE id=?", (pid,)).fetchone())
            simulador.fechar_parcial(pos, 0.5, "tp1", 110.0, {"niveis": []})
        return orig(*a, **k)
    monkeypatch.setattr(simulador, "_funding_custo", no_meio)
    sem_rede(110.0)
    simulador.fechar(pid, "manual")
    esperado = 100 * 2 * 0.10 - 2 * 0.0005 * 200       # 19,80: a posicao inteira, uma vez
    ganho = db.get_banca()["atual"] - 1000
    with db.conectar() as c:
        margem = c.execute("SELECT SUM(valor_reais) FROM trades").fetchone()[0]
    assert ganho == pytest.approx(esperado), f"banca creditada R${ganho:.2f}, devia R${esperado:.2f}; margem somada nos trades={margem} (posicao era 100)"


# =============================================================== 8. DCA
def test_8a_dca_nao_mexe_na_banca_nem_na_trava(banco, sem_rede):
    semear_equity(hoje() + " 00:00:01", 1000.0)
    dca.criar("BTC/USDT", 5000, 7)
    with db.conectar() as c:
        did = c.execute("SELECT id FROM dca").fetchone()[0]
    g0 = simulador.guarda_risco()
    assert dca.aportar(did) == 100.0
    assert dca.aportar(did) == 100.0                       # aportar NAO e idempotente (2 compras)
    with db.conectar() as c:
        n = c.execute("SELECT n_aportes, total_investido FROM dca").fetchone()
    assert tuple(n) == (2, 10000.0)
    assert db.get_banca()["atual"] == 1000 and simulador.guarda_risco() == g0


def test_8b_aportar_plano_removido_nao_compra(cliente, sem_rede):
    dca.criar("BTC/USDT", 50, 7)
    with db.conectar() as c:
        did = c.execute("SELECT id FROM dca").fetchone()[0]
    cliente.post("/dca/remover", json={"id": did})
    r = cliente.post("/dca/aportar", json={"id": did}).json()
    with db.conectar() as c:
        n = c.execute("SELECT n_aportes FROM dca").fetchone()[0]
    assert r["ok"] is False and n == 0


@pytest.mark.parametrize("corpo", [{"ativo": "BTC/USDT", "valor_aporte": -100, "freq_dias": 7},
                                   {"ativo": "BTC/USDT", "valor_aporte": 50, "freq_dias": 0},
                                   {"ativo": "lixo; DROP", "valor_aporte": 50, "freq_dias": 7}])
def test_8c_dca_valida_entrada(cliente, sem_rede, corpo):
    r = cliente.post("/dca", json=corpo)
    assert r.status_code == 422 or r.json().get("ok") is False, f"aceito: {corpo} -> {r.json()}"


# =============================================================== 9. config
@pytest.mark.parametrize("k,v", [("risco_por_trade", -0.01), ("risco_por_trade", 0.5),
                                 ("alavancagem_padrao", 1000), ("limite_perda_dia", 1),
                                 ("risco_por_trade", "0.03; DROP TABLE config"),
                                 ("chave_nova", 1), ("risco_por_trade", "nan"),
                                 ("risco_por_trade", "inf"), ("auto_max_posicoes", 2.5)])
def test_9a_config_fora_de_faixa_recusada(cliente, k, v):
    antes = db.get_config()
    r = cliente.post("/config", json={k: v})
    assert r.status_code == 422 and db.get_config() == antes


def test_9b_confirmar_com_valor_NaN_e_recusado(cliente, sem_rede):
    """JSON do Python aceita o literal NaN; pydantic v2 aceita nan em float; `nan <= 0` e False
    e toda comparacao de teto com nan e False (simulador.py:243,302,307)."""
    sid = semear_sinal()
    corpo = '{"sinal_id": %d, "valor_reais": NaN, "alavancagem": 2}' % sid
    r = cliente.post("/confirmar", content=corpo, headers={"content-type": "application/json"})
    with db.conectar() as c:
        p = c.execute("SELECT id, valor_reais FROM posicoes").fetchone()
    detalhe = f"resposta={r.status_code} {r.text[:120]}; posicao={tuple(p) if p else None}"
    if p is not None:                           # mostra a consequencia: a posicao nao fecha
        try:
            simulador.fechar(p["id"], "manual")
            detalhe += "; fechar() ok"
        except Exception as e:
            detalhe += f"; fechar() levanta {type(e).__name__}: {e}"
    assert p is None, detalhe


def test_9c_perfil_so_toca_as_chaves_do_perfil(cliente):
    antes = db.get_config()
    cliente.post("/perfil", json={"perfil": "conservador"})
    depois = db.get_config()
    mudou = {k for k in depois if not db._igual_cfg(antes.get(k), depois[k])}
    assert mudou <= set(db.PERFIS_RISCO["conservador"])
    assert "limite_perda_dia" not in mudou and "exposicao_max" not in mudou


# =============================================================== 10. reset
def test_10a_reset_nao_deixa_ordem_orfa(cliente, sem_rede):
    db.set_config("exec_modo", "post_only")
    simulador.executar(semear_sinal(), 50, 2)
    semear_posicao()
    cliente.post("/reset", json={"confirmar": "RESET"})
    pend = _n("ordens", "WHERE status='pendente'")
    sem_rede(99.0)
    simulador.processar_ordens()
    pos = _n("posicoes", "WHERE status='aberta'")
    assert pend == 0 and pos == 0, f"apos reset: {pend} ordem pendente; apos 1 ciclo: {pos} posicao aberta na conta zerada"


def test_10b_reset_limpa_trava_posicoes_e_equity(cliente, sem_rede):
    _travar_e_recuperar()
    cliente.post("/reset", json={"confirmar": "RESET"})
    assert db.get_config()["trava_dia_em"] == ""
    assert _n("posicoes") == 0 and _n("equity") == 0 and db.get_banca()["atual"] == 1000
    assert simulador.guarda_risco()["trava_dia"] is False


def test_10c_reset_sem_confirmacao_nao_apaga(cliente):
    semear_posicao()
    assert cliente.post("/reset", json={}).status_code == 400
    assert _n("posicoes") == 1


def test_9d_dca_com_NaN(cliente, sem_rede):
    r = cliente.post("/dca", content='{"ativo":"BTC/USDT","valor_aporte":NaN,"freq_dias":7}',
                     headers={"content-type": "application/json"})
    with db.conectar() as c:
        n = c.execute("SELECT COUNT(*) FROM dca").fetchone()[0]
    assert n == 0, f"{r.status_code} {r.text}"
