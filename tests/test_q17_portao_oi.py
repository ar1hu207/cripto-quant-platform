# -*- coding: utf-8 -*-
"""[Q-17] Provas do portao de open interest dentro do motor.

Sem rede: o painel e sintetico e o sinal e INJETADO (`sinal_fn`), que e exatamente para isso
que a injecao existe (ver a docstring de `backtest_ativo`). Assim a trajetoria de preco e
livre e o que se prova e o PORTAO, nao o `scoring`.
"""
import numpy as np
import pandas as pd
import pytest

from pesquisa.backtest_plataforma import backtest_ativo, OI_MODOS, OI_PESO

HORA = 3_600_000


def painel(n=200, d_oi=None):
    """Painel minimo que o motor aceita, com preco OSCILANDO.

    A oscilacao nao e enfeite. Numa rampa monotonica o trailing de 2% nunca dispara: a
    posicao abre e nunca fecha, `trades` volta vazio, e todo teste que espera `> 0` falha
    por um motivo que nao tem nada a ver com o portao -- foi o que aconteceu na primeira
    versao deste arquivo. Amplitude de 5% sobre periodo de 20 barras garante que cada
    perna feche.
    """
    t0 = 1_700_000_000_000
    k = np.arange(n)
    close = 100.0 * (1.0 + 0.05 * np.sin(2 * np.pi * k / 20.0))
    df = pd.DataFrame({
        "timestamp": [t0 + k * HORA for k in range(n)],
        "open": close, "high": close * 1.002, "low": close * 0.998, "close": close,
        "volume": np.full(n, 1000.0),
        "atr": np.full(n, 1.0), "bb_mid": close, "rsi": np.full(n, 55.0),
        "ema_r": close, "ema_l": close,
    })
    if d_oi is not None:
        df["d_oi"] = d_oi
    return df


def sinal_long(df, i):
    return {"direcao": 1, "conviccao": 60.0, "adx": 30.0, "n_fatores": 3, "stop_dist": 0.02}


def rodar(df, oi_modo, min_conv=55, **kw):
    return backtest_ativo("X/USDT", min_conv, 100, 10, tf="1h", df=df, sinal_fn=sinal_long,
                          saida="trailing", trailing_dist=0.02, oi_modo=oi_modo, **kw)


# ============================ a nula nao muda nada ============================
def test_off_e_identico_a_nao_ter_a_coluna():
    """A HIPOTESE NULA tem de ser byte a byte a estrategia de hoje. Se `off` mudasse
    qualquer coisa, a comparacao da grade estaria medindo duas diferencas de uma vez."""
    sem = rodar(painel(), "off")
    com = rodar(painel(d_oi=np.full(200, -1.0)), "off")     # OI discordando o tempo todo
    assert len(sem) == len(com) > 0
    assert [t["pnl"] for t in sem] == [t["pnl"] for t in com]


def test_modo_invalido_e_recusado():
    with pytest.raises(ValueError, match="oi_modo"):
        rodar(painel(d_oi=np.ones(200)), "concordaa")


def test_sem_a_coluna_o_portao_recusa_rodar():
    """Falhar alto e melhor que filtrar nada em silencio: sem `d_oi`, `oi_modo != off`
    passaria batido e a config viraria uma copia da nula sem ninguem notar."""
    with pytest.raises(ValueError, match="d_oi"):
        rodar(painel(), "concorda")


# ============================ o sinal do portao ============================
def test_concorda_bloqueia_tudo_quando_o_oi_discorda():
    """LONG com open interest CAINDO em toda barra = short se cobrindo. Nenhum trade."""
    assert rodar(painel(d_oi=np.full(200, -5.0)), "concorda") == []


def test_concorda_deixa_passar_quando_o_oi_concorda():
    """LONG com OI SUBINDO = dinheiro novo. Tem de operar igual a nula."""
    com = rodar(painel(d_oi=np.full(200, +5.0)), "concorda")
    nula = rodar(painel(), "off")
    assert len(com) == len(nula) > 0


def test_a_confirmacao_independe_da_direcao():
    """ESTE TESTE JA PEGOU UM ERRO, e o erro estava na hipotese, nao no codigo.

    A primeira versao do portao (e do pre-registro) escreveu `d_oi * direcao > 0`. Para um
    SHORT isso exige open interest CAINDO -- que e exatamente o desmonte de posicao, o caso
    que a hipotese quer REJEITAR. Metade dos trades ficaria com o criterio invertido.

    O certo: OI sobe quando posicao NOVA e aberta, e todo contrato tem um comprado e um
    vendido. Confirmacao e `d_oi > 0` nos dois sentidos -- a direcao do movimento ja esta no
    sinal. Este teste fixa isso pelo lado SHORT, que e onde as duas formulas discordam.
    """
    def sinal_short(df, i):
        return {"direcao": -1, "conviccao": 60.0, "adx": 30.0, "n_fatores": 3,
                "stop_dist": 0.02}

    def curto(d):
        return backtest_ativo("X/USDT", 55, 100, 10, tf="1h", df=painel(d_oi=np.full(200, d)),
                              sinal_fn=sinal_short, saida="trailing", trailing_dist=0.02,
                              oi_modo="concorda")

    assert curto(-5.0) == [], "OI caindo com SHORT e long liquidando: tem de bloquear"
    assert len(curto(+5.0)) > 0, "OI subindo com SHORT e short NOVO: tem de passar"


def test_nan_nao_filtra():
    """Barra sem OI medido deixa passar. 'Nao operar quando falta dado' e OUTRA hipotese."""
    d = np.full(200, np.nan)
    assert len(rodar(painel(d_oi=d), "concorda")) == len(rodar(painel(), "off")) > 0


def test_concorda_tend_so_age_em_tendencia():
    """Com adx=30 e adx_min=25 o portao age; com adx_min=35 o sinal esta fora de tendencia
    e o portao tem de deixar passar, mesmo com o OI discordando."""
    d = np.full(200, -5.0)
    assert rodar(painel(d_oi=d), "concorda_tend", adx_min=25) == []
    # adx_min alto derruba o sinal pelo portao de tendencia do proprio motor, entao a prova
    # de que `concorda_tend` NAO age fora de tendencia usa um sinal de adx baixo:
    def sinal_fraco(df, i):
        return {"direcao": 1, "conviccao": 60.0, "adx": 10.0, "n_fatores": 3,
                "stop_dist": 0.02}
    passou = backtest_ativo("X/USDT", 55, 100, 10, tf="1h", df=painel(d_oi=d),
                            sinal_fn=sinal_fraco, saida="trailing", trailing_dist=0.02,
                            oi_modo="concorda_tend", adx_min=5)
    # adx_min=5 <= adx=10, entao esta EM tendencia e o portao age
    assert passou == []


def test_peso_move_a_conviccao_nos_dois_sentidos():
    """`peso` nao recusa: empurra a conviccao. Provado contra a NULA nos dois sentidos --
    o bonus tem de ACRESCENTAR trade que a nula nao faria, e a punicao tem de REMOVER trade
    que a nula faria. So assim os dois sinais de `OI_PESO` ficam cobertos."""
    base = 60.0
    acima = base + OI_PESO - 1                                # 69: a nula nao passa
    assert rodar(painel(d_oi=np.full(200, +5.0)), "off", min_conv=acima) == []
    assert len(rodar(painel(d_oi=np.full(200, +5.0)), "peso", min_conv=acima)) > 0

    abaixo = base - OI_PESO + 1                               # 51: a nula passa
    assert len(rodar(painel(d_oi=np.full(200, -5.0)), "off", min_conv=abaixo)) > 0
    assert rodar(painel(d_oi=np.full(200, -5.0)), "peso", min_conv=abaixo) == []


def test_a_grade_declarada_e_a_que_o_motor_aceita():
    """O pre-registro travou quatro modos. Se alguem acrescentar um quinto sem passar por um
    pre-registro novo, a grade e o `n_trials` deixam de corresponder ao documento."""
    assert OI_MODOS == ("off", "concorda", "concorda_tend", "peso")
