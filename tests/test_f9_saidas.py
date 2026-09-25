"""[F-9] O gestor de saida rodava a cada ciclo, por posicao, e nunca fechava nada.

Medido no PLANO-V2: zero `auto-saida` em 62 trades. O motivo e de desenho, nao de sorte: o
auto-trader so fecha pelo gestor com `auto_fechar_saida=1` E `trailing_ativo=0`
(`autotrader.auto_executar`, passo 1), e o vivo roda com o trailing ligado. Mesmo assim o
worker pedia livro de ofertas e trades para cada posicao, 24/7.

O conserto NAO e desligar o gestor: a recomendacao dele aparece no painel (`GET /saidas`),
ao lado de cada posicao. Ele passa a rodar no ciclo so quando decide alguma coisa, e sob
demanda (com cache curto) quando so o painel pergunta.
"""
import time

import pytest

import api
import db
import signal_engine
from conftest import semear_posicao


@pytest.fixture
def contador(banco, monkeypatch):
    chamadas = []

    def falso(pos, cfg=None):
        chamadas.append(pos["id"])
        return {"posicao_id": pos["id"], "ativo": pos["ativo"], "nivel": "ok"}
    monkeypatch.setattr(signal_engine, "avaliar_saida", falso)
    monkeypatch.setattr(api, "_saidas", {"v": [], "t": None})
    return chamadas


def test_com_trailing_ligado_o_ciclo_nao_decide_por_saida(banco):
    """O vivo: trailing ligado. O passo 1 do auto-trader nao age, entao o ciclo nao calcula."""
    cfg = db.get_config()
    assert cfg["trailing_ativo"] == "1"
    assert api._saidas_decidem(cfg) is False


def test_com_trailing_desligado_e_auto_fechar_o_ciclo_calcula(banco):
    db.set_config("trailing_ativo", "0")
    db.set_config("auto_fechar_saida", "1")
    assert api._saidas_decidem(db.get_config()) is True
    db.set_config("auto_fechar_saida", "0")
    assert api._saidas_decidem(db.get_config()) is False


def test_o_painel_recebe_a_recomendacao_sob_demanda_e_reusa_por_30s(contador, monkeypatch):
    """Painel aberto continua vendo a recomendacao -- e duas perguntas dentro do TTL custam
    UM calculo, nao dois."""
    from fastapi.testclient import TestClient
    semear_posicao(ativo="BTC/USDT")
    semear_posicao(ativo="ETH/USDT")
    c = TestClient(api.app, client=("127.0.0.1", 5555))
    r1 = c.get("/saidas").json()
    r2 = c.get("/saidas").json()
    assert len(r1) == 2 and r1 == r2
    assert len(contador) == 2                       # um calculo, duas posicoes
    monkeypatch.setattr(api, "_saidas", {"v": r1, "t": time.monotonic() - api.SAIDAS_TTL_S - 1})
    c.get("/saidas")
    assert len(contador) == 4                       # vencido o TTL, recalcula


def test_o_reset_invalida_o_cache_das_saidas(contador):
    """Sem isto o painel mostraria, por ate 30 s depois do reset, recomendacao de saida para
    posicao que nao existe mais -- o mesmo defeito que o reset ja limpava antes do cache."""
    from fastapi.testclient import TestClient
    api._saidas.update(v=[{"posicao_id": 1}], t=time.monotonic())
    c = TestClient(api.app, client=("127.0.0.1", 5555))
    assert c.post("/reset", json={"confirmar": "RESET"}).status_code == 200
    assert api._saidas == {"v": [], "t": None}
    assert c.get("/saidas").json() == []            # recalcula: nao ha posicao aberta
