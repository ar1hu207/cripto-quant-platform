# -*- coding: utf-8 -*-
"""Territorio T-DECLARACAO (onda 2 do M4): o que a API DECLARA sobre risco e guardas.

Tres coisas moram aqui, e a linha que as une e a mesma: numero de risco que o sistema usa
sem dizer em voz alta e numero que ninguem audita.

    [P1-11]  a contagem do cap geometrico exposta em `/status`
    [Q-3]    os perfis `experimento`/`conservador` e o perfil ATIVO derivado
    [Q-3]    o racional por parametro no catalogo de config do [P1-8]
"""
import pytest


@pytest.fixture
def cliente(banco):
    """TestClient sem `with`: o `lifespan` -- e portanto a thread do worker -- nao sobe.

    `client=("127.0.0.1", ...)` porque o peer padrao do TestClient ("testclient") nao e
    loopback, e sem `DASH_PASS` o app responde 503 a tudo que venha de fora (o [P0-1]).
    Mesmo motivo, e mesma solucao, do `test_auth.py` e do `test_regressoes_p1.py`.
    """
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app, client=("127.0.0.1", 5555))


# ======================================================= [P1-11] cap geometrico no /status

@pytest.fixture
def caps_zerados(monkeypatch):
    """`autotrader.CAPS_GEOMETRIA` e estado de MODULO (cumulativo na vida do processo, que e
    o ponto dele). Trocar por um dicionario novo por teste evita que a ordem dos testes -- ou
    qualquer outro que chame `_cap_geometrico` -- decida o numero asseverado aqui."""
    import autotrader
    monkeypatch.setattr(autotrader, "CAPS_GEOMETRIA", {"total": 0, "ultimo": None})
    return autotrader


def test_status_publica_a_contagem_do_cap_geometrico(cliente, caps_zerados):
    """Terceiro item do aceite do [P1-11]: "contagem exposta em `/status`".

    Antes disto o cap so existia no log e no resumo de UM ciclo do auto-trader -- e o resumo
    do ciclo seguinte apaga o anterior, entao "quantas vezes isso ja agiu?" nao tinha
    resposta sem abrir o `plataforma.log` na VM.
    """
    j = cliente.get("/status").json()
    assert j["caps_geometria"] == {"total": 0, "ultimo": None}

    # o caso do proprio aceite do card: stop de 5%, lev por conviccao 20 -> teto 14
    # (0,8 * 0,9 / 0,05 = 14,4, truncado para baixo).
    assert caps_zerados._cap_geometrico(20, 0.05, "INJ/USDT") == 14.0

    j = cliente.get("/status").json()
    assert j["caps_geometria"]["total"] == 1
    assert j["caps_geometria"]["ultimo"]["ativo"] == "INJ/USDT"
    assert j["caps_geometria"]["ultimo"]["lev_conviccao"] == 20
    assert j["caps_geometria"]["ultimo"]["lev_efetiva"] == 14.0


def test_o_cap_nao_entra_no_criterio_de_saude(cliente, caps_zerados):
    """`saudavel` continua `not (cego or cego_pos)`. O cap agindo e a guarda FUNCIONANDO --
    trata-lo como sintoma faria o painel pintar de vermelho justamente o bot que se protegeu.
    Mexer no detector de cegueira e decisao do dono (CLAUDE.md sec. 2)."""
    caps_zerados._cap_geometrico(20, 0.05, "SUI/USDT")
    j = cliente.get("/status").json()
    assert j["caps_geometria"]["total"] == 1 and j["saudavel"] is True


def test_a_contagem_do_cap_nao_vai_para_o_estado(cliente, caps_zerados):
    """O `/estado` e polido a cada 3s pelo painel e a franquia de saida da Azure e 15 GB/mes
    (CLAUDE.md sec. 2). Diagnostico cumulativo mora no `/status`, que o front so busca no
    portao de login. Se um dia alguem mover isto para o `/estado`, este teste avisa."""
    assert "caps_geometria" not in cliente.get("/estado").json()
