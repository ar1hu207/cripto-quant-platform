"""[MICRO-1] Laboratório de microtrades: o motor com livro sintético, sem rede.

O que se prova aqui é a CONTA, não a estratégia: fluxo comprador vira compra no ask, a saída
sai no bid, as três camadas (sinal / executado / líquido) batem com a aritmética feita à mão,
a latência usa o livro DEPOIS do atraso, ordem esperando latência ocupa o teto, e o piso da
banca desliga o motor. Se alguma dessas falhar, o painel mostra um número que não aconteceu.
"""
import threading

import pytest

import micro

A = "tstusdt"


def _cfg(**kw):
    c = dict(micro.PADRAO)
    c.update(ativos=A, z_entrada="3", latencia_ms="0", horizonte_ms="2000", intervalo_min_ms="0",
             max_por_ativo="1", notional="100", banca_inicial="10000", perda_max_pct="100")
    c.update({k: str(v) for k, v in kw.items()})
    return c


def _quieto(m, t0, t1, pb=100.0, pa=100.01, qb0=10.0, qa0=10.0):
    """Livro parado com tamanhos alternando ±1: OFI pequeno e simétrico, |z| fica perto de 1."""
    t, i = t0, 0
    while t < t1:
        m.livro(A, t, pb, qb0 + (i % 2), pa, qa0 + 1 - (i % 2))
        t += 0.01
        i += 1
    return t


def _rajada_compradora(m, t, pb=100.0, pa=100.01):
    """Cinco eventos com o lance engordando 200 de cada vez: OFI fortemente positivo."""
    for k in range(1, 6):
        m.livro(A, t, pb, 10.0 + 200 * k, pa, 10.0)
        t += 0.01
    return t


def test_fluxo_comprador_compra_no_ask_e_vende_no_bid_com_as_tres_camadas():
    m = micro.Motor(_cfg(), taxa_lado=0.0005)
    t = _quieto(m, 0.0, 40.0)
    assert not m.posicoes and not m.fechados, "livro parado não pode disparar com z_entrada=3"
    t = _rajada_compradora(m, t)
    assert len(m.posicoes) == 1
    p = m.posicoes[0]
    assert p["lado"] == 1 and p["px"] == 100.01          # comprou no ASK
    _quieto(m, t, t + 2.5, qb0=1010.0)                   # lance continua gordo: não vira
    assert len(m.fechados) == 1
    tr = m.fechados[0]
    assert tr["motivo"] == "tempo" and tr["px_sai"] == 100.0   # vendeu no BID
    rel = 100.0 / 100.01
    assert tr["bps_sinal"] == pytest.approx(0.0, abs=1e-9)     # meio não andou: sinal zero
    assert tr["bps_exec"] == pytest.approx((rel - 1) * 1e4)    # pagou o spread
    assert tr["bps_liq"] == pytest.approx((rel - 1) * 1e4 - 5 * (1 + rel))
    assert tr["pnl_liq"] == pytest.approx(100 * ((rel - 1) - 0.0005 * (1 + rel)))
    assert m.banca == pytest.approx(10000 + tr["pnl_liq"])


def test_latencia_executa_no_livro_depois_do_atraso_e_nao_no_da_decisao():
    m = micro.Motor(_cfg(latencia_ms=100), taxa_lado=0.0005)
    t = _quieto(m, 0.0, 40.0)
    t = _rajada_compradora(m, t)
    assert not m.posicoes and len(m.ordens) == 1         # decidiu, ainda não executou
    meio_dec = m.ordens[0]["meio_dec"]
    m.livro(A, t + 0.05, 100.0, 1010.0, 100.05, 10.0)    # antes do atraso: não executa
    assert not m.posicoes
    m.livro(A, t + 0.11, 100.0, 1010.0, 100.08, 10.0)    # depois do atraso: executa AQUI
    assert m.posicoes[0]["px"] == 100.08
    assert m.posicoes[0]["meio"] == meio_dec             # o sinal mede a partir da decisão


def test_relogio_executa_e_sai_mesmo_sem_evento_novo_do_ativo():
    m = micro.Motor(_cfg(latencia_ms=100), taxa_lado=0.0005)
    t = _rajada_compradora(m, _quieto(m, 0.0, 40.0))
    m.relogio(t + 0.2)                                   # nenhum evento do ativo, só o relógio
    assert len(m.posicoes) == 1
    m.relogio(t + 0.2 + 2.0)                             # passou o horizonte: decide sair
    m.relogio(t + 0.2 + 2.2)                             # passou a latência: executa a saída
    assert len(m.fechados) == 1 and not m.posicoes


def test_ordem_esperando_latencia_ocupa_o_teto():
    m = micro.Motor(_cfg(latencia_ms=1000, max_por_ativo=1), taxa_lado=0.0005)
    t = _rajada_compradora(m, _quieto(m, 0.0, 40.0))
    _rajada_compradora(m, t)                             # segundo disparo dentro da latência
    assert len(m.ordens) == 1, "ordem pendente tem de contar no teto, como no [EX-1]"


def test_piso_da_banca_para_o_motor():
    m = micro.Motor(_cfg(banca_inicial=100, notional=10000, perda_max_pct=1), taxa_lado=0.0005)
    t = _rajada_compradora(m, _quieto(m, 0.0, 40.0))
    t = _quieto(m, t, t + 2.5, qb0=1010.0)
    assert m.parado_por and "piso" in m.parado_por
    _rajada_compradora(m, _quieto(m, t, t + 5, qb0=10.0))
    assert not m.posicoes and not m.ordens, "depois do piso não abre mais nada"


def test_validar_recusa_o_que_nao_esta_no_catalogo_ou_na_faixa():
    assert micro.validar({"z_entrada": "2.5", "max_por_ativo": 4}) == {"z_entrada": "2.5", "max_por_ativo": "4"}
    assert micro.validar({"ativos": "BTCUSDT, ethusdt,btcusdt"}) == {"ativos": "btcusdt,ethusdt"}
    for ruim in ({"z_entrada": 0.1}, {"latencia_ms": -1}, {"max_por_ativo": 2.5}, {"auto_trade": 1},
                 {"ativos": "btc/usdt"}, {"ativos": ""}, {"notional": "nan"}, {}):
        with pytest.raises(ValueError):
            micro.validar(ruim)


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("MICRO_DB_PATH", str(tmp_path / "micro.db"))
    monkeypatch.setitem(micro._st, "agg", None)
    # sem rede: a thread do motor só espera o pedido de parar
    monkeypatch.setattr(micro, "_thread", lambda ativos, parar: parar.wait(5))
    yield
    micro.desligar(persistir=False)


def test_gravacao_e_recarga_dao_o_mesmo_agregado(lab):
    m = micro.Motor(_cfg(), taxa_lado=0.0005)
    t = _rajada_compradora(m, _quieto(m, 0.0, 40.0))
    _quieto(m, t, t + 2.5, qb0=1010.0)
    micro.init()
    agg = micro._Agregado()
    for tr in m.fechados:
        agg.somar(tr, 0.0)
    micro._gravar(m.fechados, agg)
    de_novo = micro._Agregado()
    de_novo.carregar()
    assert de_novo.por_ativo == agg.por_ativo
    assert dict(de_novo.por_minuto) == dict(agg.por_minuto)


def test_ligar_desligar_e_zerar_sem_rede(lab):
    e = micro.estado()
    assert e["ligado"] is False and e["n"] == 0 and e["banca"] == 10000.0
    e = micro.ligar()
    assert e["ligado"] is True and micro.get_config()["ligado"] == "1"
    e = micro.set_config({"z_entrada": 2.5})               # ligado: reinicia com o valor novo
    assert e["ligado"] is True and e["cfg"]["z_entrada"] == "2.5"
    assert micro._st["motor"].z_entrada == 2.5
    e = micro.desligar()
    assert e["ligado"] is False and micro.get_config()["ligado"] == "0"
    e = micro.zerar()
    assert e["n"] == 0 and e["ligado"] is False


def test_retomar_so_religa_o_que_estava_ligado(lab):
    micro.retomar()
    assert not micro.ligado()
    micro.init()
    micro._set("ligado", "1")
    micro.retomar()
    assert micro.ligado()
