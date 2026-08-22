# -*- coding: utf-8 -*-
"""Item 1 do [P2-6]: `simulador.guarda_risco()` -- trava diaria sticky e teto de risco aberto.

Sao invariantes de risco (CLAUDE.md §2): so o dono afrouxa. O que este arquivo faz e travar
o COMPORTAMENTO, para que afrouxar exija apagar uma asseracao com nome -- e nao so mudar um
sinal de comparacao sem ninguem ver.

O teto de MARGEM, que o card lista junto destes dois, nao vive aqui: ele levanta dentro de
`abrir()`, e por isso esta em `test_abrir.py`.
"""
import pandas as pd
import pytest

import db
import simulador
from conftest import semear_equity, semear_posicao


HOJE = str(pd.Timestamp.now().date())
ONTEM = str(pd.Timestamp.now().date() - pd.Timedelta(days=1))


def _equity_do_dia(valor, hora="00:00:05"):
    semear_equity(HOJE + " " + hora, valor)


# ---------------------------------------------------------------- baseline do dia

def test_sem_snapshot_do_dia_o_baseline_e_o_equity_de_agora(banco):
    """Dia que ainda nao gravou equity: o baseline e o proprio equity atual, entao
    pnl_dia = 0. Sem esse fallback o primeiro ciclo do dia compararia contra zero e
    travaria sozinho."""
    g = simulador.guarda_risco()
    assert g["pnl_dia"] == 0.0
    assert g["trava_dia"] is False


def test_baseline_e_o_primeiro_snapshot_do_dia_nao_o_ultimo(banco):
    """`ORDER BY rowid ASC LIMIT 1`: a trava mede a variacao desde o INICIO do dia. Pegar o
    ultimo snapshot faria o baseline perseguir o equity e a trava nunca acionaria."""
    _equity_do_dia(1000.0, "00:00:05")
    _equity_do_dia(1200.0, "10:00:00")
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=960 WHERE id=1")
    g = simulador.guarda_risco()
    assert g["pnl_dia"] == -40.0          # 960 - 1000, e nao 960 - 1200


def test_snapshot_de_ontem_nao_serve_de_baseline_de_hoje(banco):
    semear_equity(ONTEM + " 23:59:59", 500.0)
    g = simulador.guarda_risco()
    assert g["pnl_dia"] == 0.0            # ignorou ontem, caiu no fallback do dia
    assert g["trava_dia"] is False


# ---------------------------------------------------------------- trava diaria

def test_trava_mede_equity_e_nao_pnl_realizado(banco):
    """O caso de 22/08 registrado no CLAUDE.md §2: +34,68 de realizado no dia e a trava
    disparada por -80,34 de EQUITY. Se a guarda olhasse `realizado_hoje` -- que ela calcula
    e devolve -- o dia teria seguido operando com a banca caindo."""
    _equity_do_dia(1000.0)
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=1034.68 WHERE id=1")
        c.execute("INSERT INTO trades(ativo,direcao,pnl_reais,fechado_em) "
                  "VALUES('BTC/USDT','LONG',34.68,?)", (HOJE + " 09:00:00",))
    semear_posicao(valor_reais=200.0, alavancagem=5, entrada=100.0, stop=99.0, pnl=-115.02)
    g = simulador.guarda_risco()
    assert g["realizado_hoje"] == 34.68           # realizado positivo...
    assert g["pnl_dia"] == -80.34                 # ...e o equity abaixo do inicio do dia
    assert g["trava_dia"] is True


def test_trava_nao_dispara_antes_do_limite(banco):
    _equity_do_dia(1000.0)
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=951 WHERE id=1")     # -49, limite e -50 (5%)
    g = simulador.guarda_risco()
    assert g["limite_rs"] == 50.0
    assert g["trava_dia"] is False
    assert db.get_config().get("trava_dia_em", "") == ""


def test_trava_dispara_exatamente_no_limite(banco):
    """`pnl_dia <= -limite_rs`: bater o limite ja e atingi-lo."""
    _equity_do_dia(1000.0)
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=950 WHERE id=1")
    assert simulador.guarda_risco()["trava_dia"] is True


def test_trava_e_sticky_no_dia_mesmo_com_o_equity_recuperando(banco):
    """O que o CLAUDE.md chama de sticky: acionou hoje, fica travado hoje. Sem isto, uma
    posicao aberta oscilando destravaria o dia sozinha a cada poll de 3s."""
    _equity_do_dia(1000.0)
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=900 WHERE id=1")
    assert simulador.guarda_risco()["trava_dia"] is True
    assert db.get_config()["trava_dia_em"] == HOJE            # gravou a marca no banco

    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=1100 WHERE id=1")   # recuperou, e passou do inicio
    g = simulador.guarda_risco()
    assert g["pnl_dia"] == 100.0
    assert g["trava_dia"] is True                             # continua travado


def test_a_marca_da_trava_e_idempotente(banco):
    """`if tripou and trava_em != hoje`: grava uma vez, nao um write por poll."""
    _equity_do_dia(1000.0)
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=900 WHERE id=1")
    simulador.guarda_risco()
    simulador.guarda_risco()
    with db.conectar() as c:
        n = c.execute("SELECT COUNT(*) FROM config WHERE chave='trava_dia_em'").fetchone()[0]
    assert n == 1
    assert db.get_config()["trava_dia_em"] == HOJE


def test_a_trava_solta_na_virada_do_dia(banco):
    """Marca de ontem nao trava hoje -- e o unico jeito de soltar previsto no codigo.
    Limpar `trava_dia_em` a mao seria relaxar invariante (CLAUDE.md §2)."""
    db.set_config("trava_dia_em", ONTEM)
    assert simulador.guarda_risco()["trava_dia"] is False


def test_marca_de_hoje_trava_mesmo_sem_perda_agora(banco):
    """O estado persistido manda: reiniciar o worker nao destrava o dia."""
    db.set_config("trava_dia_em", HOJE)
    assert simulador.guarda_risco()["trava_dia"] is True


# ---------------------------------------------------------------- teto de risco aberto

def test_teto_de_risco_aberto_soma_o_risco_ate_o_stop(banco):
    """Duas posicoes de R$50 a 10x com stop a 2%: risco 50*10*0.02 = R$10 cada. Teto
    padrao e 10% de R$1.000 = R$100 -- longe."""
    semear_posicao(ativo="BTC/USDT", entrada=100.0, stop=98.0, valor_reais=50.0, alavancagem=10)
    semear_posicao(ativo="ETH/USDT", entrada=100.0, stop=98.0, valor_reais=50.0, alavancagem=10)
    g = simulador.guarda_risco()
    assert g["n_abertas"] == 2
    assert g["risco_aberto_rs"] == 20.0
    assert g["risco_aberto_max_rs"] == 100.0
    assert g["teto_aberto"] is False


def test_teto_aberto_acusa_quando_o_risco_alcanca_o_limite(banco):
    db.set_config("risco_aberto_max", "0.02")                 # 2% de 1000 = R$20
    semear_posicao(entrada=100.0, stop=98.0, valor_reais=50.0, alavancagem=10)   # R$10
    semear_posicao(entrada=100.0, stop=98.0, valor_reais=50.0, alavancagem=10)   # R$10
    g = simulador.guarda_risco()
    assert g["risco_aberto_rs"] == 20.0
    assert g["risco_aberto_max_rs"] == 20.0
    assert g["teto_aberto"] is True                            # `>=`, nao `>`


def test_risco_aberto_max_zero_desliga_o_teto(banco):
    """`<=0 => sem teto`, conforme o comentario do CONFIG_PADRAO. `None` e a ausencia
    DECLARADA: `abrir()` le exatamente isso para pular a checagem."""
    db.set_config("risco_aberto_max", "0")
    semear_posicao(entrada=100.0, stop=98.0, valor_reais=500.0, alavancagem=10)
    g = simulador.guarda_risco()
    assert g["risco_aberto_max_rs"] is None
    assert g["teto_aberto"] is False


def test_margem_aberta_e_a_soma_das_margens_nao_do_nocional(banco):
    semear_posicao(valor_reais=50.0, alavancagem=10)
    semear_posicao(valor_reais=30.0, alavancagem=3)
    assert simulador.guarda_risco()["margem_aberta"] == 80.0


def test_posicao_fechada_nao_conta_em_nada(banco):
    semear_posicao(valor_reais=500.0, alavancagem=10, entrada=100.0, stop=98.0, status="fechada")
    g = simulador.guarda_risco()
    assert (g["n_abertas"], g["margem_aberta"], g["risco_aberto_rs"]) == (0, 0.0, 0.0)


# ---------------------------------------------------------------- _risco_posicao

@pytest.mark.parametrize("valor,lev,entrada,stop,esperado", [
    (50.0, 10, 100.0, 98.0, 10.0),      # 2% de distancia x 10x = 20% da margem
    (50.0, 2, 100.0, 95.0, 5.0),        # 5% x 2x = 10% da margem
    (50.0, 10, 100.0, None, 50.0),      # sem stop: a perda maxima e a margem inteira
    (50.0, 10, 100.0, 0, 50.0),         # stop 0 conta como sem stop
    (50.0, 20, 100.0, 90.0, 50.0),      # liquidacao antes do stop: capado na margem
    (50.0, 10, 100.0, 110.0, 50.0),     # stop do lado errado: `abs()`, e ainda capado
    (0.0, 10, 100.0, 98.0, 0.0),
])
def test_risco_posicao(banco, valor, lev, entrada, stop, esperado):
    assert simulador._risco_posicao(valor, lev, entrada, stop) == pytest.approx(esperado)


# ---------------------------------------------------------------- [P1-8] em profundidade

def test_config_invalida_no_banco_nao_derruba_a_guarda(banco):
    """Defesa em profundidade do [P1-8]: a validacao de verdade e no POST /config, mas lixo
    que ja esteja gravado nao pode transformar a guarda em ValueError -- isso derrubaria
    `/estado` E o ciclo do worker, que e indisponibilidade total em vez de degradacao."""
    db.set_config("limite_perda_dia", "abc")
    db.set_config("risco_aberto_max", "")
    g = simulador.guarda_risco()
    assert g["limite_pct"] == 5.0                  # caiu no padrao 0.05
    assert g["risco_aberto_pct"] == 10.0
