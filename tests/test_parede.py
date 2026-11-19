# -*- coding: utf-8 -*-
"""[SR-3] O sinal registra a distancia, em R, ao nivel INTACTO do 4h mais proximo a frente.

E anotacao: nenhuma regra le `sinais.parede_4h`. O que estes testes travam e (1) a conta, so com
vela de 4h fechada e so com nivel que nenhum fechamento atravessou; (2) que "nenhum nivel" e 99
e "nao medido" e NULL; (3) que a anotacao nao custa o sinal quando a rede falha.
"""
import time

import alvos
import db
import signal_engine

H4 = alvos.H4_MS


def _raw4(lows, highs=None, closes=None, fim_ms=None):
    """Velas de 4h com as minimas dadas; a ultima FECHOU em `fim_ms` (default: agora arredondado)."""
    fim = fim_ms or (int(time.time() * 1000) // H4) * H4
    n = len(lows)
    highs = highs or [lo + 4 for lo in lows]
    closes = closes or [lo + 2 for lo in lows]
    return [[fim - (n - i) * H4, c, h, lo, c, 1.0] for i, (lo, h, c) in enumerate(zip(lows, highs, closes))]


AGORA = (int(time.time() * 1000) // H4) * H4 + 60_000

# um fundo em 90 na vela 10, que segurou; o resto acima de 95
LOWS = [100.0] * 10 + [90.0] + [100.0] * 10


def test_short_mede_ate_o_suporte_intacto_abaixo():
    # preco 96, stop 98 -> R = 2; suporte intacto em 90 -> 3R
    assert alvos.parede_r(_raw4(LOWS), "SHORT", 96.0, 98.0, AGORA) == 3.0


def test_fundo_furado_por_fechamento_nao_e_suporte():
    closes = [lo + 2 for lo in LOWS]
    closes[15] = 89.0                                  # uma vela FECHOU abaixo do fundo de 90
    lows = list(LOWS); lows[15] = 88.5
    r = alvos.parede_r(_raw4(lows, closes=closes), "SHORT", 96.0, 98.0, AGORA)
    assert r != 3.0                                    # o 90 saiu; sobra so o 88,5 se for pivo


def test_pavio_abaixo_sem_fechamento_nao_rompe():
    lows = list(LOWS); lows[15] = 89.5                 # pavio abaixo de 90, mas fecha em 91,5
    assert alvos.parede_r(_raw4(lows), "SHORT", 96.0, 98.0, AGORA) == 3.0


def test_nenhum_nivel_a_frente_e_99_e_sem_geometria_e_none():
    assert alvos.parede_r(_raw4(LOWS), "SHORT", 80.0, 82.0, AGORA) == alvos.PAREDE_NENHUM
    assert alvos.parede_r(_raw4(LOWS), "SHORT", 96.0, 96.0, AGORA) is None
    assert alvos.parede_r([], "SHORT", 96.0, 98.0, AGORA) is None


def test_long_mede_ate_a_resistencia_intacta_acima():
    highs = [104.0] * 10 + [110.0] + [104.0] * 10
    r = alvos.parede_r(_raw4(LOWS, highs=highs, closes=[102.0] * 21), "LONG", 105.0, 103.0, AGORA)
    assert r == 2.5                                    # (110 - 105) / 2


def test_vela_em_formacao_nao_entra():
    raw = _raw4(LOWS)
    forma = [[raw[-1][0] + H4, 95.0, 96.0, 50.0, 60.0, 1.0]]   # abriu agora, fecha absurdo
    assert alvos.parede_r(raw + forma, "SHORT", 96.0, 98.0, AGORA) == alvos.parede_r(raw, "SHORT", 96.0, 98.0, AGORA)


# ------------------------------------------------------------------ no scan
SINAL = dict(ativo="BTC/USDT", tf="15m", tipo="tendencia", direcao="SHORT", conviccao=80,
             motivos="x", preco=96.0, stop_sugerido=98.0, adx=30, n_fatores=4, vela_ms=1)


def _scan(monkeypatch, velas4):
    db.set_config("ativos", "BTC/USDT")
    db.set_config("timeframes", "15m")
    monkeypatch.setattr(signal_engine, "analisa", lambda a, tf: [dict(SINAL)])
    monkeypatch.setattr(signal_engine, "confirmado", lambda s, a, cfg: (True, "confirmado"))
    monkeypatch.setattr(signal_engine, "marcar_desfechos", lambda *a, **k: 0)
    monkeypatch.setattr(signal_engine, "_velas", lambda a, tf, n: velas4(a, tf, n))
    signal_engine.scan()
    with db.conectar() as c:
        return [r["parede_4h"] for r in c.execute("SELECT parede_4h FROM sinais")]


def test_o_scan_grava_a_parede(banco, monkeypatch):
    pedidos = []

    def velas4(a, tf, n):
        pedidos.append(tf)
        return _raw4(LOWS)
    assert _scan(monkeypatch, velas4) == [3.0]
    assert pedidos == ["4h"]


def test_4h_fora_do_ar_nao_custa_o_sinal(banco, monkeypatch):
    def cai(a, tf, n):
        raise ConnectionError("binance fora")
    assert _scan(monkeypatch, cai) == [None]
