# -*- coding: utf-8 -*-
"""[EX-1] Execucao post-only: a ordem que descansa, o preenchimento e a taxa de maker.

O que estes testes protegem, e por que cada um existe:

- **O default nao muda.** `exec_modo` nasce em `mercado`, e enquanto estiver assim o caminho
  e o `abrir()` de sempre, com a taxa de sempre. Feature de execucao que muda comportamento
  sem ninguem ligar e mudanca de risco pela porta dos fundos.
- **A taxa cobrada e a que a posicao pagou.** O ganho inteiro do post-only mora em ~0,03% por
  lado ([CX-1]); se o `_pnl` cobrar taker na entrada maker, o ganho some no relatorio sem
  ninguem ver. E se cobrar maker na SAIDA, inventa lucro que nao houve -- stop e ordem a
  mercado ([CX-4]).
- **O sinal e reivindicado na ORDEM, nao no fill.** Senao o mesmo sinal vira duas ordens
  durante a janela de espera, que e exatamente onde o claim atomico do [P1-6] passou a ser
  necessario.
- **Ordem pendente conta nos tetos.** Doze ordens que enchem no mesmo minuto sao doze
  posicoes.
"""
import pandas as pd
import pytest

import db
import simulador
from tests.conftest import semear_sinal, semear_posicao


@pytest.fixture
def post_only(banco):
    db.set_config("exec_modo", "post_only")
    db.set_config("exec_maker_off", "0.0010")
    db.set_config("taxa_maker", "0.0002")
    db.set_config("taxa_por_lado", "0.0005")
    return banco


# --------------------------------------------------------------- o default nao muda
def test_default_e_mercado_e_executar_abre_posicao(banco, sem_rede):
    assert db.get_config()["exec_modo"] == "mercado"
    sid = semear_sinal()
    tipo, pid = simulador.executar(sid, 50.0, 2)
    assert tipo == "posicao"
    with db.conectar() as c:
        assert c.execute("SELECT COUNT(*) FROM ordens").fetchone()[0] == 0
        pos = c.execute("SELECT * FROM posicoes WHERE id=?", (pid,)).fetchone()
    assert pos["taxa_entrada"] is None          # entrou a mercado: paga `taxa_por_lado` nas duas pernas


def test_taxa_de_posicao_a_mercado_continua_sendo_2x_taker(banco, sem_rede):
    """Regressao do [EX-1] contra ele mesmo: separar entrada e saida nao pode mover o numero
    de quem entrou a mercado. 2 x 0,0005 x 50 x 2 = 0,10."""
    pid = semear_posicao(entrada=100.0, valor_reais=50.0, alavancagem=2)
    with db.conectar() as c:
        pos = dict(c.execute("SELECT * FROM posicoes WHERE id=?", (pid,)).fetchone())
    _, taxa, _ = simulador._pnl(pos, 100.0)
    assert taxa == pytest.approx(0.10)


# --------------------------------------------------------------- a ordem descansa
def test_post_only_cria_ordem_e_nao_posicao(post_only, sem_rede):
    sid = semear_sinal(direcao="LONG", preco=100.0, stop=95.0)
    tipo, oid = simulador.executar(sid, 50.0, 2)
    assert tipo == "ordem"
    with db.conectar() as c:
        assert c.execute("SELECT COUNT(*) FROM posicoes").fetchone()[0] == 0
        o = c.execute("SELECT * FROM ordens WHERE id=?", (oid,)).fetchone()
        sig = c.execute("SELECT status FROM sinais WHERE id=?", (sid,)).fetchone()
    assert o["status"] == "pendente"
    assert o["preco_limite"] == pytest.approx(99.90)      # 100 - 0,10%, do NOSSO lado
    assert sig["status"] == "confirmado"                  # claim na ORDEM, nao no fill


def test_short_descansa_ACIMA_do_preco(post_only, sem_rede):
    sid = semear_sinal(direcao="SHORT", preco=100.0, stop=105.0)
    _, oid = simulador.executar(sid, 50.0, 2)
    with db.conectar() as c:
        o = c.execute("SELECT * FROM ordens WHERE id=?", (oid,)).fetchone()
    assert o["preco_limite"] == pytest.approx(100.10)


def test_mesmo_sinal_nao_vira_duas_ordens(post_only, sem_rede):
    sid = semear_sinal()
    simulador.executar(sid, 50.0, 2)
    with pytest.raises(ValueError, match="confirmado|pulado|expirado|de novo"):
        simulador.executar(sid, 50.0, 2)


# --------------------------------------------------------------- preenchimento
def test_nao_enche_enquanto_o_preco_nao_vem(post_only, sem_rede):
    semear_sinal()
    simulador.executar(semear_sinal(ativo="ETH/USDT"), 50.0, 2)
    sem_rede(100.0)                                   # preco parado: limite 99,90 nao foi tocado
    r = simulador.processar_ordens()
    assert (r["preenchidas"], r["expiradas"]) == (0, 0)
    with db.conectar() as c:
        assert c.execute("SELECT COUNT(*) FROM posicoes").fetchone()[0] == 0


def test_enche_no_limite_e_grava_a_taxa_de_maker(post_only, sem_rede):
    sid = semear_sinal(direcao="LONG", preco=100.0, stop=95.0)
    _, oid = simulador.executar(sid, 50.0, 2)
    sem_rede(99.5)                                    # preco veio ATE a ordem
    r = simulador.processar_ordens()
    assert r["preenchidas"] == 1
    with db.conectar() as c:
        o = c.execute("SELECT * FROM ordens WHERE id=?", (oid,)).fetchone()
        pos = c.execute("SELECT * FROM posicoes WHERE id=?", (o["posicao_id"],)).fetchone()
    assert o["status"] == "preenchida"
    # a entrada e o LIMITE, nao o preco de agora: post-only significa que o preco foi nosso
    assert pos["entrada"] == pytest.approx(99.90)
    assert pos["taxa_entrada"] == pytest.approx(0.0002)


def test_taxa_do_round_trip_e_maker_entrando_e_taker_saindo(post_only, sem_rede):
    """O numero que o [CX-4] mediu. (0,0002 + 0,0005) x 50 x 2 = 0,07 -- e NAO 0,04 (maker nas
    duas pernas, otimista) nem 0,10 (taker nas duas, o de hoje)."""
    sid = semear_sinal()
    simulador.executar(sid, 50.0, 2)
    sem_rede(99.5)
    simulador.processar_ordens()
    with db.conectar() as c:
        pos = dict(c.execute("SELECT * FROM posicoes WHERE status='aberta'").fetchone())
    _, taxa, _ = simulador._pnl(pos, 100.0)
    assert taxa == pytest.approx(0.07)


def test_ordem_expirada_nao_devolve_o_sinal(post_only, sem_rede):
    sid = semear_sinal()
    db.set_config("exec_ordem_ttl_s", "0")            # expira no proximo ciclo
    _, oid = simulador.executar(sid, 50.0, 2)
    r = simulador.processar_ordens()
    assert r["expiradas"] == 1
    with db.conectar() as c:
        assert c.execute("SELECT status FROM ordens WHERE id=?", (oid,)).fetchone()["status"] == "expirada"
        # o sinal NAO volta para a fila: e a escolha que o [CX-1] mediu
        assert c.execute("SELECT status FROM sinais WHERE id=?", (sid,)).fetchone()["status"] == "confirmado"
        assert c.execute("SELECT COUNT(*) FROM posicoes").fetchone()[0] == 0


def test_trava_diaria_no_meio_da_espera_cancela_em_vez_de_encher(post_only, sem_rede, monkeypatch):
    """A ordem espera, e o dia pode estourar enquanto ela espera. Deixar encher seria a trava
    diaria valendo so para quem entra a mercado."""
    sid = semear_sinal()
    simulador.executar(sid, 50.0, 2)
    monkeypatch.setattr(simulador, "guarda_risco",
                        lambda: {"trava_dia": True, "risco_aberto_max_rs": None})
    sem_rede(99.5)
    r = simulador.processar_ordens()
    assert r["preenchidas"] == 0
    with db.conectar() as c:
        o = c.execute("SELECT * FROM ordens").fetchone()
        assert o["status"] == "cancelada"
        assert c.execute("SELECT COUNT(*) FROM posicoes").fetchone()[0] == 0


def test_uma_ordem_que_falha_nao_impede_as_outras(post_only, sem_rede, monkeypatch):
    """A licao do [P1-1] no terreno novo: try/except POR ORDEM, nunca em volta do `for`."""
    simulador.executar(semear_sinal(ativo="BTC/USDT"), 20.0, 2)
    simulador.executar(semear_sinal(ativo="ETH/USDT"), 20.0, 2)

    def preco_quebrado(ativo):
        if ativo == "BTC/USDT":
            raise RuntimeError("exchange fora do ar")
        return 99.5

    monkeypatch.setattr(simulador, "preco_ao_vivo", preco_quebrado)
    r = simulador.processar_ordens()
    assert r["falhas"] == 1 and r["preenchidas"] == 1


# --------------------------------------------------------------- tetos
def test_ordem_pendente_conta_no_teto_de_margem(post_only, sem_rede):
    """Banca 1000, exposicao_max 0,5 -> teto de R$500 de margem. Duas ordens de R$300 nao cabem,
    mesmo sem NENHUMA posicao aberta."""
    simulador.executar(semear_sinal(ativo="BTC/USDT"), 300.0, 2)
    with pytest.raises(ValueError, match="teto de margem"):
        simulador.executar(semear_sinal(ativo="ETH/USDT"), 300.0, 2)


def test_ordem_pendente_conta_no_teto_ao_abrir_a_mercado(post_only, sem_rede):
    """O aperto vale nos DOIS caminhos: uma ordem pendente tem de bloquear tambem quem tenta
    entrar a mercado, senao a guarda so vale para metade do sistema."""
    simulador.executar(semear_sinal(ativo="BTC/USDT"), 300.0, 2)
    db.set_config("exec_modo", "mercado")
    with pytest.raises(ValueError, match="teto de margem"):
        simulador.executar(semear_sinal(ativo="ETH/USDT"), 300.0, 2)
