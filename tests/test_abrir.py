# -*- coding: utf-8 -*-
"""Item 3 do [P2-6]: `simulador.abrir()` -- recusa quando estoura o teto, e o que a recusa
faz com o SINAL.

O invariante do CLAUDE.md §2 que este arquivo existe para travar:

    "Os tetos de risco e margem levantam **antes** do claim, de proposito -- recusa por teto
     nao pode consumir o sinal. Nao inverta essa ordem."

Uma inversao dessa ordem passa em qualquer teste que so olhe "levantou ValueError": o
comportamento visivel e identico. O que muda e o sinal ficar `confirmado` sem posicao
nenhuma -- e ele nunca mais volta para a fila. Por isso todo teste de recusa aqui termina
conferindo o `status` do sinal, e nao so a excecao.

A exclusao mutua do claim concorrente ([P1-6], duas threads) ja e provada por
`python prova_m1.py`, que a suite executa em `test_provas_existentes.py`; nao se repete aqui.
"""
import pandas as pd
import pytest

import db
import simulador
from conftest import semear_posicao, semear_sinal


def status_do(sid):
    with db.conectar() as c:
        return c.execute("SELECT status FROM sinais WHERE id=?", (sid,)).fetchone()["status"]


# ---------------------------------------------------------------- caminho feliz

def test_abre_a_posicao_e_consome_o_sinal(banco, sem_rede):
    sid = semear_sinal(preco=100.0, stop=95.0)
    pid = simulador.abrir(sid, 50.0, 2)
    p = db.listar("posicoes", 1)[0]
    assert p["id"] == pid
    assert (p["status"], p["ativo"], p["direcao"]) == ("aberta", "BTC/USDT", "LONG")
    assert (p["entrada"], p["valor_reais"], p["alavancagem"]) == (100.0, 50.0, 2)
    assert p["sinal_id"] == sid
    assert status_do(sid) == "confirmado"          # o claim so acontece quando a posicao nasce


def test_o_stop_e_recomposto_a_partir_da_entrada_ao_vivo(banco, sem_rede):
    """O sinal foi impresso a 100 com stop a 95 (5%). Se o preco ja andou para 200 quando a
    confirmacao chega, copiar o stop de 95 abriria a posicao com 52% de risco. Mantendo a
    DISTANCIA relativa, o risco dimensionado continua valendo."""
    sem_rede(200.0)
    sid = semear_sinal(preco=100.0, stop=95.0)
    simulador.abrir(sid, 50.0, 2)
    p = db.listar("posicoes", 1)[0]
    assert p["entrada"] == 200.0
    assert p["stop"] == pytest.approx(190.0)       # 200 x (1 - 0,05)


def test_no_short_o_stop_recomposto_fica_acima_da_entrada(banco, sem_rede):
    sem_rede(200.0)
    sid = semear_sinal(direcao="SHORT", preco=100.0, stop=105.0)
    simulador.abrir(sid, 50.0, 2)
    p = db.listar("posicoes", 1)[0]
    assert p["stop"] == pytest.approx(210.0)


def test_sinal_sem_stop_usa_o_stop_sugerido_como_esta(banco, sem_rede):
    """`stop_rel = 0` -> nao ha distancia para recompor; o fallback e o valor do sinal."""
    sem_rede(200.0)
    sid = semear_sinal(preco=100.0, stop=None)
    simulador.abrir(sid, 50.0, 2)
    assert db.listar("posicoes", 1)[0]["stop"] is None


# ---------------------------------------------------------------- parametros degenerados

@pytest.mark.parametrize("valor,lev", [(0, 2), (-10, 2), (50, 0), (50, -1)])
def test_valor_ou_alavancagem_nao_positivos_sao_recusados(banco, sem_rede, valor, lev):
    """Barrado na primeira linha, antes de qualquer leitura: uma posicao com alavancagem 0
    e uma divisao por zero esperando o proximo ciclo (`_preco_liquidacao`, `_pnl`)."""
    sid = semear_sinal()
    with pytest.raises(ValueError):
        simulador.abrir(sid, valor, lev)
    assert status_do(sid) == "novo"
    assert db.listar("posicoes", 10) == []


def test_sinal_inexistente_e_recusado(banco, sem_rede):
    with pytest.raises(ValueError, match="sinal"):
        simulador.abrir(99999, 50.0, 2)


def test_sinal_ja_confirmado_nao_vira_posicao_de_novo(banco, sem_rede):
    """[P1-6] pelo caminho sequencial: confirmar duas vezes o mesmo sinal."""
    sid = semear_sinal()
    simulador.abrir(sid, 50.0, 2)
    with pytest.raises(ValueError):
        simulador.abrir(sid, 50.0, 2)
    assert len(db.listar("posicoes", 10)) == 1


@pytest.mark.parametrize("status", ["pulado", "expirado", "rejeitado_fluxo"])
def test_sinal_fora_da_fila_nao_abre(banco, sem_rede, status):
    sid = semear_sinal(status=status)
    with pytest.raises(ValueError):
        simulador.abrir(sid, 50.0, 2)
    assert db.listar("posicoes", 10) == []


# ---------------------------------------------------------------- trava diaria

def test_trava_diaria_bloqueia_a_abertura_sem_consumir_o_sinal(banco, sem_rede):
    db.set_config("trava_dia_em", str(pd.Timestamp.now().date()))
    sid = semear_sinal()
    with pytest.raises(ValueError, match="trava"):
        simulador.abrir(sid, 50.0, 2)
    assert status_do(sid) == "novo"
    assert db.listar("posicoes", 10) == []


# ---------------------------------------------------------------- teto de risco aberto

def test_teto_de_risco_recusa_e_deixa_o_sinal_na_fila(banco, sem_rede):
    """A recusa e por RISCO, nao por defeito do sinal: quando a exposicao ceder, o mesmo
    sinal ainda deve poder ser confirmado. Se o claim viesse antes do teto, ele sairia
    daqui `confirmado` e perdido."""
    db.set_config("risco_aberto_max", "0.01")            # R$10 de teto
    sid = semear_sinal(preco=100.0, stop=95.0)           # risco novo = 50 x 10 x 5% = R$25
    with pytest.raises(ValueError, match="teto de risco aberto"):
        simulador.abrir(sid, 50.0, 10)
    assert status_do(sid) == "novo"
    assert db.listar("posicoes", 10) == []


def test_o_teto_soma_o_que_ja_esta_aberto_ao_candidato(banco, sem_rede):
    """R$18 de teto, R$10 ja abertos: um candidato de R$10 nao cabe, um de R$5 cabe."""
    db.set_config("risco_aberto_max", "0.018")
    semear_posicao(ativo="ETH/USDT", entrada=100.0, stop=98.0, valor_reais=50.0, alavancagem=10)
    sid = semear_sinal(preco=100.0, stop=98.0)           # 2% x 10x x 50 = R$10 -> 10+10 > 18
    with pytest.raises(ValueError, match="teto de risco aberto"):
        simulador.abrir(sid, 50.0, 10)

    sid2 = semear_sinal(ativo="SOL/USDT", preco=100.0, stop=99.0)   # 1% x 10x x 50 = R$5
    simulador.abrir(sid2, 50.0, 10)
    assert len(db.listar("posicoes", 10, "WHERE status='aberta'")) == 2


def test_teto_de_risco_desligado_deixa_passar(banco, sem_rede):
    """O risco tem de ser grande o bastante para o teto PEGAR se estivesse ligado -- senao o
    teste passa por nao haver risco, e nao por o teto estar desligado.

    [P1-12] A lev deste teste mudou, e o numero foi ESCOLHIDO. Era `100.0 @ 20x`, e 20x com
    stop de 5% poe a liquidacao a 4,5% da entrada: a geometria que `abrir()` agora recusa. A
    alavancagem alta estava aqui so para inflar o risco -- a geometria degenerada era acidente,
    nao o assunto. `300.0 @ 10x` infla o mesmo tanto (300 x 10 x 5% = R$150, contra o teto
    padrao de R$100) e fica do lado sadio da guarda (10 x 5% = 0,5 < `LIQ_BUFFER`). Nao volte
    para 20x "porque e menos margem": o teste passa a falhar por geometria, que e outra
    guarda e tem prova propria em `tests/test_guarda_risco.py`."""
    db.set_config("risco_aberto_max", "0")
    sid = semear_sinal(preco=100.0, stop=95.0)
    simulador.abrir(sid, 300.0, 10)                  # R$150 de risco: o teto pegaria, se ligado
    assert len(db.listar("posicoes", 10)) == 1


# ---------------------------------------------------------------- teto de margem

def test_teto_de_margem_recusa_e_deixa_o_sinal_na_fila(banco, sem_rede):
    """Mesmo invariante do teto de risco, no outro teto. `exposicao_max` = 0,5 sobre uma
    banca de R$1.000 da R$500 de margem; R$600 nao entra."""
    db.set_config("risco_aberto_max", "0")               # isola: so o teto de margem levanta
    sid = semear_sinal(preco=100.0, stop=95.0)
    with pytest.raises(ValueError, match="teto de margem"):
        simulador.abrir(sid, 600.0, 2)
    assert status_do(sid) == "novo"
    assert db.listar("posicoes", 10) == []


def test_o_teto_de_margem_soma_a_margem_ja_aberta(banco, sem_rede):
    db.set_config("risco_aberto_max", "0")
    semear_posicao(ativo="ETH/USDT", valor_reais=400.0, alavancagem=2)
    sid = semear_sinal(preco=100.0, stop=95.0)
    with pytest.raises(ValueError, match="teto de margem"):
        simulador.abrir(sid, 150.0, 2)                   # 400 + 150 > 500
    assert status_do(sid) == "novo"


def test_teto_de_margem_desligado_deixa_passar(banco, sem_rede):
    db.set_config("risco_aberto_max", "0")
    db.set_config("exposicao_max", "0")
    sid = semear_sinal(preco=100.0, stop=95.0)
    simulador.abrir(sid, 900.0, 2)
    assert db.listar("posicoes", 1)[0]["valor_reais"] == 900.0
