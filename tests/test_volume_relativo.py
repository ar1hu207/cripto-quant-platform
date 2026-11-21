# -*- coding: utf-8 -*-
"""[VR-1] O sinal registra o volume da ultima hora contra o normal do ativo (`sinais.vol_rel`).

E anotacao: nenhuma regra le a coluna. O que estes testes travam e (1) que a conta e a do C4 do
T72/T73 (12 velas de 5m FECHADAS e contiguas / mediana das horas inteiras nos 30 dias antes delas,
com pelo menos 20 dias); (2) que "nao medido" e NULL, nunca zero; (3) que a anotacao nao custa o
sinal quando a rede falha, e que o rejeitado por fluxo tambem e anotado.
"""
import sqlite3
import time

import db
import signal_engine as se

M5, H1, DIA = se._M5_MS, se._H1_MS, se._DIA_MS
# "agora" um minuto depois de uma vela de 5m fechar
L_FIM = (int(time.time() * 1000) // H1) * H1           # a ultima vela de 5m fechada termina aqui
AGORA = L_FIM + 60_000


def _raw5(vols, fim=L_FIM):
    """Velas de 5m com os volumes dados; a ultima FECHOU em `fim`."""
    n = len(vols)
    return [[fim - (n - i) * M5, 1.0, 1.0, 1.0, 1.0, float(v)] for i, v in enumerate(vols)]


def _raw1h(vols, ate):
    """Velas de 1h com os volumes dados; a ultima FECHA em `ate`."""
    n = len(vols)
    return [[ate - (n - i) * H1, 1.0, 1.0, 1.0, 1.0, float(v)] for i, v in enumerate(vols)]


S = L_FIM - 12 * M5                                     # abertura da primeira das 12
HORAS = _raw1h([60.0] * (30 * 24), S)                   # 30 dias de horas normais, volume 60


def test_a_conta_e_a_do_c4():
    # 12 velas x 10 = 120 na ultima hora, contra 60 normal -> 2,0
    assert se.volume_relativo(_raw5([10] * 12), HORAS, AGORA) == 2.0


def test_a_mediana_nao_a_media():
    horas = _raw1h([60.0] * (30 * 24 - 5) + [6000.0] * 5, S)   # cinco horas de pico nao mexem no normal
    assert se.volume_relativo(_raw5([10] * 12), horas, AGORA) == 2.0


def test_vela_em_formacao_nao_entra():
    raw = _raw5([10] * 12) + [[L_FIM, 1.0, 1.0, 1.0, 1.0, 99999.0]]   # abriu em L_FIM, fecha depois de AGORA
    assert se.volume_relativo(raw, HORAS, AGORA) == 2.0


def test_hora_a_partir_do_inicio_da_janela_nao_entra_no_normal():
    # horas que fecham depois de S (a propria ultima hora) nao podem contaminar o normal
    tarde = _raw1h([1e9] * 3, L_FIM)
    assert se.volume_relativo(_raw5([10] * 12), HORAS + tarde, AGORA) == 2.0


def test_hora_mais_velha_que_30_dias_nao_entra():
    velhas = _raw1h([1e9] * 200, S - 30 * DIA)          # terminam antes do inicio da janela
    assert se.volume_relativo(_raw5([10] * 12), velhas + HORAS, AGORA) == 2.0


def test_buraco_nas_12_e_ausencia():
    raw = _raw5([10] * 13)
    del raw[5]                                          # sobram 12, mas nao contiguas
    assert se.volume_relativo(raw, HORAS, AGORA) is None


def test_menos_de_12_velas_e_ausencia():
    assert se.volume_relativo(_raw5([10] * 11), HORAS, AGORA) is None


def test_menos_de_20_dias_de_horas_e_ausencia():
    assert se.volume_relativo(_raw5([10] * 12), _raw1h([60.0] * (20 * 24 - 1), S), AGORA) is None
    assert se.volume_relativo(_raw5([10] * 12), _raw1h([60.0] * (20 * 24), S), AGORA) == 2.0


def test_normal_zero_e_ausencia_e_hora_parada_e_zero():
    assert se.volume_relativo(_raw5([10] * 12), _raw1h([0.0] * (30 * 24), S), AGORA) is None
    assert se.volume_relativo(_raw5([0] * 12), HORAS, AGORA) == 0.0


# ------------------------------------------------------------------ no scan
SINAL = dict(ativo="BTC/USDT", tf="15m", tipo="tendencia", direcao="SHORT", conviccao=80,
             motivos="x", preco=96.0, stop_sugerido=98.0, adx=30, n_fatores=4, vela_ms=1)


def _scan(monkeypatch, confirma=lambda s, a, cfg: (True, "confirmado")):
    db.set_config("ativos", "BTC/USDT")
    db.set_config("timeframes", "15m")
    monkeypatch.setattr(se, "analisa", lambda a, tf: [dict(SINAL)])
    monkeypatch.setattr(se, "confirmado", confirma)
    monkeypatch.setattr(se, "marcar_desfechos", lambda *a, **k: 0)
    monkeypatch.setattr(se, "_velas", lambda a, tf, n: [])            # parede e afins: sem dado
    se.scan()
    with db.conectar() as c:
        return [(r["status"], r["vol_rel"]) for r in c.execute("SELECT status, vol_rel FROM sinais")]


def _com_volume(monkeypatch, vols5=(10,) * 12):
    # o scan usa o relogio de verdade: monta as velas em torno de agora
    fim = (int(time.time() * 1000) // M5) * M5
    s = fim - 12 * M5
    monkeypatch.setattr(se, "_velas_volume", lambda a: (_raw5(vols5, fim), _raw1h([60.0] * (30 * 24), s)))


def test_o_scan_grava_o_volume(banco, monkeypatch):
    _com_volume(monkeypatch)
    assert _scan(monkeypatch) == [("novo", 2.0)]


def test_volume_fora_do_ar_nao_custa_o_sinal(banco, monkeypatch):
    """A suite ja derruba `_velas_volume` por padrao (tests/conftest.py)."""
    assert _scan(monkeypatch) == [("novo", None)]


def test_o_rejeitado_por_fluxo_tambem_e_anotado(banco, monkeypatch):
    """Sem o lado rejeitado, nao ha como comparar depois quem o volume teria separado."""
    _com_volume(monkeypatch)

    def rejeita(s, a, cfg):
        s["rejeitado_por"] = "fluxo"
        return False, "fluxo contra o SHORT"
    assert _scan(monkeypatch, rejeita) == [(se.REJEITADO_FLUXO, 2.0)]


def test_quem_grava_sem_anotar_grava_null(banco):
    with db.conectar() as con:
        se._gravar(con, "2026-03-01 12:00:00", dict(SINAL), "BTC/USDT", "15m", "novo", None)
        assert con.execute("SELECT vol_rel FROM sinais").fetchone()[0] is None


def test_banco_que_ja_existia_ganha_a_coluna(tmp_path):
    caminho = str(tmp_path / "antigo.db")
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE sinais(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, ativo TEXT, "
                "direcao TEXT, conviccao REAL, motivos TEXT, preco REAL, stop_sugerido REAL, "
                "status TEXT DEFAULT 'novo')")
    con.execute("INSERT INTO sinais(ts,ativo,direcao) VALUES('2026-11-01 10:00:00','BTC/USDT','SHORT')")
    con.commit()
    con.close()
    original = db.DB
    db.DB = caminho
    try:
        db.init_db()
        with db.conectar() as c:
            colunas = {r["name"] for r in c.execute("PRAGMA table_info(sinais)")}
            velho = c.execute("SELECT vol_rel FROM sinais").fetchone()[0]
    finally:
        db.DB = original
    assert "vol_rel" in colunas and velho is None
