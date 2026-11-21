# -*- coding: utf-8 -*-
"""[NOITE-1] Recuperação da lacuna: na volta do servidor, as velas de 1 min da madrugada passam
pela marcação de sempre, como se stop, TP e trailing fossem ordens descansando na corretora."""
import json

import pandas as pd
import pytest

import api
import db
import simulador

LACUNA_H = 12


def _pos(entrada=100.0, stop=103.0, direcao="SHORT", plano=None, aberto_em=None, valor=1000.0):
    aberto_em = aberto_em or str(pd.Timestamp.now() - pd.Timedelta(hours=LACUNA_H + 2))
    with db.conectar() as c:
        c.execute("INSERT INTO posicoes(ativo,direcao,entrada,valor_reais,alavancagem,stop,"
                  "stop_abertura,risco_abertura,preco_atual,pnl,aberto_em,status,conviccao,tps) "
                  "VALUES('X/USDT',?,?,?,10,?,?,100,?,0,?,'aberta',70,?)",
                  (direcao, entrada, valor, stop, stop, entrada, aberto_em,
                   json.dumps(plano) if plano else None))
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def _plano(valor=1000.0):
    niv = [{"preco": 95.0, "r": 1.67, "frac": 0.34, "feito": False, "forca": 2, "fonte": "estrutura"},
           {"preco": 90.0, "r": 3.33, "frac": 0.33, "feito": False, "forca": 2, "fonte": "estrutura"},
           {"preco": 85.0, "r": 5.0, "frac": 0.33, "feito": False, "forca": 2, "fonte": "estrutura"}]
    return {"niveis": niv, "valor_inicial": valor, "r_preco": 3.0, "calc_em": "t"}


def _trades():
    with db.conectar() as c:
        return [dict(r) for r in c.execute("SELECT * FROM trades ORDER BY id")]


def _posicao(pid):
    with db.conectar() as c:
        return dict(c.execute("SELECT * FROM posicoes WHERE id=?", (pid,)).fetchone())


@pytest.fixture
def noite(banco, sem_rede, monkeypatch):
    """Servidor que dormiu LACUNA_H horas. Devolve (desde, velas): `velas[min] = (o, h, l)`
    sobrescreve o minuto `min` depois de `desde`; o resto da madrugada é plano em 100."""
    db.set_config("recupera_lacuna", "1")
    db.set_config("tp_ativo", "0")
    db.set_config("trailing_ativo", "0")
    desde = pd.Timestamp.now().floor("min") - pd.Timedelta(hours=LACUNA_H)
    with db.conectar() as c:
        c.execute("INSERT INTO equity(ts,banca,equity_total) VALUES(?,?,?)", (str(desde), 10000, 10000))
    monkeypatch.setitem(simulador._marcado_ate, "ts", None)       # processo que acabou de subir
    velas, chamadas = {}, []

    def falsas(ativo, desde_ms, ate_ms):
        chamadas.append((ativo, desde_ms, ate_ms))
        out = []
        for m in range(LACUNA_H * 60 + 1):
            t = desde + pd.Timedelta(minutes=m)
            ms = simulador._ms(t)
            if ms < desde_ms or ms + 60_000 > ate_ms:
                continue
            o, h, l = velas.get(m, (100.0, 100.0, 100.0))
            out.append([ms, o, h, l, o, 1.0])
        return out

    monkeypatch.setattr(simulador, "_velas_1m", falsas)
    sem_rede(100.0)
    return desde, velas, chamadas


def test_padrao_desligado_e_no_catalogo():
    assert db.CONFIG_PADRAO["recupera_lacuna"] == "0"
    assert api.CONFIG_CATALOGO["recupera_lacuna"] == ("bool",)
    assert "recupera_lacuna_min" in api.CONFIG_CATALOGO


def test_stop_de_madrugada_fecha_no_stop_e_na_hora_da_vela(noite):
    desde, velas, _ = noite
    pid = _pos()
    velas[180] = (100.0, 104.0, 99.5)                    # 3h depois: o pavio passa do stop 103
    simulador.atualizar()
    tr = _trades()
    assert len(tr) == 1 and tr[0]["motivo_saida"] == "stop"
    assert tr[0]["saida"] == pytest.approx(103.0)         # ordem stop executa no stop, não no pavio
    assert tr[0]["fechado_em"].startswith(str(desde + pd.Timedelta(minutes=180))[:16])
    assert _posicao(pid)["status"] == "fechada"


def test_gap_de_madrugada_fecha_na_abertura(noite):
    _, velas, _ = noite
    _pos()
    velas[60] = (105.0, 105.5, 104.0)                    # a vela já abre além do stop
    simulador.atualizar()
    tr = _trades()
    assert tr[0]["motivo_saida"] == "stop-gap"
    assert tr[0]["saida"] == pytest.approx(105.0)


def test_tp_tocado_e_devolvido_realiza(noite):
    _, velas, _ = noite
    db.set_config("tp_ativo", "1")
    pid = _pos(plano=_plano())
    velas[300] = (100.0, 100.0, 94.5)                    # toca o TP1 (95) e o preço volta a 100
    simulador.atualizar()
    tr = _trades()
    assert [t["motivo_saida"] for t in tr] == ["tp1"]
    assert tr[0]["saida"] == pytest.approx(95.0)
    p = _posicao(pid)
    assert p["status"] == "aberta" and p["valor_reais"] == pytest.approx(660.0)
    assert json.loads(p["tps"])["niveis"][0]["feito"] is True


def test_trailing_anda_de_madrugada_e_fecha_no_lucro(noite):
    _, velas, _ = noite
    db.set_config("trailing_ativo", "1")                 # R: arma 3R, distância 3R (padrão)
    _pos()                                               # SHORT 100, stop 103: 1R = 3
    velas[100] = (100.0, 100.0, 88.0)                    # 4R a favor: stop vai a 88 + 9 = 97
    for m in range(101, 400):
        velas[m] = (90.0, 90.0, 90.0)                    # caminho contínuo: sem gap até o repique
    velas[400] = (95.0, 98.0, 95.0)                      # repique: passa do 97
    simulador.atualizar()
    tr = _trades()
    assert len(tr) == 1 and tr[0]["motivo_saida"] == "trailing"
    assert tr[0]["saida"] == pytest.approx(97.0)


def test_mesmo_minuto_com_stop_e_alvo_a_protecao_decide(noite):
    _, velas, _ = noite
    db.set_config("tp_ativo", "1")
    _pos(plano=_plano())
    velas[200] = (100.0, 104.0, 94.0)                    # a vela tem o stop E o TP1
    simulador.atualizar()
    assert [t["motivo_saida"] for t in _trades()] == ["stop"]


def test_posicao_aberta_na_lacuna_ignora_a_vela_da_entrada(noite):
    desde, velas, _ = noite
    entrada_em = desde + pd.Timedelta(minutes=120, seconds=30)
    pid = _pos(aberto_em=str(entrada_em))
    velas[120] = (100.0, 104.0, 99.0)                    # minuto da entrada: preço de antes dela
    simulador.atualizar()
    assert _trades() == []
    assert _posicao(pid)["status"] == "aberta"


def test_nao_repassa_a_mesma_lacuna_duas_vezes(noite):
    _, _, chamadas = noite
    _pos()
    simulador.atualizar()
    simulador.atualizar()                                # ciclo seguinte: lacuna de segundos
    assert len(chamadas) == 1


def test_chave_desligada_nao_busca_vela(noite):
    _, velas, chamadas = noite
    db.set_config("recupera_lacuna", "0")
    _pos()
    velas[180] = (100.0, 104.0, 99.5)
    simulador.atualizar()
    assert chamadas == [] and _trades() == []


def test_lacuna_pequena_e_ciclo_normal(noite, monkeypatch):
    _, _, chamadas = noite
    monkeypatch.setitem(simulador._marcado_ate, "ts", pd.Timestamp.now() - pd.Timedelta(minutes=1))
    _pos()
    simulador.atualizar()
    assert chamadas == []


def test_fonte_de_preco_trocada_sem_velas_trocadas_sai_de_cena(banco, sem_rede, monkeypatch):
    """O backtest de carteira troca o `preco_ao_vivo`: velas reais de agora seriam o futuro."""
    db.set_config("recupera_lacuna", "1")
    desde = pd.Timestamp.now() - pd.Timedelta(hours=LACUNA_H)
    with db.conectar() as c:
        c.execute("INSERT INTO equity(ts,banca,equity_total) VALUES(?,?,?)", (str(desde), 1, 1))
    monkeypatch.setitem(simulador._marcado_ate, "ts", None)

    class _Explode:
        def fetch_ohlcv(self, *a, **k):
            raise AssertionError("a recuperação não pode buscar vela com a fonte de preço trocada")

    monkeypatch.setattr(simulador, "ex", _Explode())
    _pos()
    simulador.atualizar()
    assert simulador.recuperacao["ultimo_erro"] is None or "AssertionError" not in simulador.recuperacao["ultimo_erro"]
    assert _trades() == []


def test_relogio_da_vela_nao_vaza_para_o_fechamento_manual(noite):
    _, velas, _ = noite
    _pos()
    velas[180] = (100.0, 100.5, 99.5)                    # nada acontece de madrugada
    simulador.atualizar()
    pid2 = _pos()
    simulador.fechar(pid2, "manual", 100.0)
    fechado = pd.Timestamp(_trades()[-1]["fechado_em"])
    assert abs((pd.Timestamp.now() - fechado).total_seconds()) < 60
