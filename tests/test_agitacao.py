# -*- coding: utf-8 -*-
"""[AG-1] `sinais.atr_rel`: o ATR do sinal contra o normal do proprio ativo.

E anotacao: a distancia do stop do sinal dividida pela mediana da mesma distancia nos sinais
anteriores do MESMO ativo, grafico e tipo. O que estes testes travam: a conta; que o "normal" so
usa o passado, uma vez por vela e so do proprio ativo; que ausencia de medicao e NULL e nunca
"calmo"; e que a conta nunca custa o sinal. Quem le a coluna e o [AG-2]
(tests/test_agitacao_tamanho.py).
"""
import sqlite3

import db
import signal_engine

SINAL = dict(ativo="BTC/USDT", tf="15m", tipo="tendencia", direcao="SHORT", conviccao=80,
             motivos="x", preco=100.0, stop_sugerido=103.0, adx=30, n_fatores=4, vela_ms=900000)


def _semear(n, dist, ativo="BTC/USDT", tf="15m", tipo="tendencia", vela0=1000, status="novo",
            vela_fixa=None):
    """n sinais anteriores com a distancia de stop `dist`, cada um na sua vela."""
    with db.conectar() as c:
        for i in range(n):
            c.execute("INSERT INTO sinais(ts,ativo,tf,tipo,direcao,conviccao,motivos,preco,"
                      "stop_sugerido,status,vela_ms) VALUES('2026-03-01 00:00:00',?,?,?,'SHORT',"
                      "70,'x',100.0,?,?,?)",
                      (ativo, tf, tipo, 100.0 * (1 + dist), status,
                       vela_fixa if vela_fixa is not None else vela0 + i))


def _gravar(stop=103.0, vela_ms=900000, **mais):
    """Grava um sinal pelo INSERT unico do motor e devolve o `atr_rel` que saiu no banco."""
    s = dict(SINAL, stop_sugerido=stop, vela_ms=vela_ms, **mais)
    with db.conectar() as con:
        signal_engine._gravar(con, "2026-03-01 12:00:00", s, s["ativo"], s["tf"], "novo", None)
        return con.execute("SELECT atr_rel FROM sinais ORDER BY id DESC LIMIT 1").fetchone()[0]


# ------------------------------------------------------------------ [AG-1] a conta
def test_a_razao_e_a_distancia_do_sinal_sobre_a_mediana_das_anteriores(banco):
    _semear(30, 0.03)
    assert _gravar(stop=106.0, vela_ms=900001) == 2.0       # ATR o dobro do normal
    assert _gravar(stop=103.0, vela_ms=900002) == 1.0
    assert _gravar(stop=101.5, vela_ms=900003) == 0.5


def test_long_e_short_medem_igual(banco):
    """A distancia e relativa e sem sinal: stop 3% abaixo ou 3% acima e a mesma agitacao."""
    _semear(30, 0.03)
    assert _gravar(stop=97.0, vela_ms=900001, direcao="LONG") == 1.0


def test_sem_trinta_velas_anteriores_e_ausencia_e_nao_calmo(banco):
    _semear(29, 0.03)
    assert _gravar(stop=106.0, vela_ms=900001) is None      # 29 anteriores: nao ha normal
    assert _gravar(stop=106.0, vela_ms=900002) == 2.0       # o de cima virou o 30o


def test_o_normal_e_do_proprio_ativo_grafico_e_tipo(banco):
    _semear(30, 0.10, ativo="ETH/USDT", vela0=1000)
    _semear(30, 0.10, tf="1h", vela0=2000)
    _semear(30, 0.10, tipo="reversao", vela0=3000)
    assert _gravar(stop=103.0) is None                      # nenhum dos tres e o normal dele
    _semear(30, 0.03, vela0=4000)
    assert _gravar(stop=103.0, vela_ms=900001) == 1.0


def test_a_mesma_vela_conta_uma_vez(banco):
    """O mesmo candle aparece na fila e no log de rejeicao por fluxo: sao 29 velas, nao 34."""
    _semear(29, 0.03)
    _semear(5, 0.03, status=signal_engine.REJEITADO_FLUXO, vela_fixa=1000)
    assert _gravar(stop=106.0) is None


def test_a_vela_do_proprio_sinal_nao_entra_no_normal(banco):
    """A rejeicao gravada um minuto antes, no mesmo candle, nao e 'sinal anterior'."""
    _semear(29, 0.03)
    _semear(1, 0.03, status=signal_engine.REJEITADO_FLUXO, vela_fixa=900000)
    assert _gravar(stop=106.0, vela_ms=900000) is None
    assert _gravar(stop=106.0, vela_ms=900001) == 2.0       # outra vela: agora sao 30 anteriores


def test_so_as_200_velas_mais_recentes(banco):
    _semear(200, 0.09, vela0=1000)                          # o normal de antes
    _semear(200, 0.03, vela0=5000)                          # o normal de agora
    assert _gravar(stop=103.0) == 1.0


def test_sinal_sem_geometria_grava_null_e_nao_custa_o_sinal(banco):
    _semear(30, 0.03)
    assert _gravar(stop=100.0, vela_ms=900001) is None      # stop em cima do preco
    assert _gravar(stop=None, vela_ms=900002) is None
    with db.conectar() as c:
        assert c.execute("SELECT COUNT(*) FROM sinais WHERE status='novo'").fetchone()[0] == 32


def test_falha_na_conta_nao_custa_o_sinal(banco, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("conta quebrada")
    monkeypatch.setattr(signal_engine, "_agitacao", quebra)
    assert _gravar(stop=106.0) is None
    with db.conectar() as c:
        assert c.execute("SELECT COUNT(*) FROM sinais").fetchone()[0] == 1


def _scan(monkeypatch, confirmado=lambda s, a, cfg: (True, "confirmado")):
    db.set_config("ativos", "BTC/USDT")
    db.set_config("timeframes", "15m")
    monkeypatch.setattr(signal_engine, "analisa", lambda a, tf: [dict(SINAL, stop_sugerido=106.0)])
    monkeypatch.setattr(signal_engine, "confirmado", confirmado)
    monkeypatch.setattr(signal_engine, "marcar_desfechos", lambda *a, **k: 0)
    signal_engine.scan()
    with db.conectar() as c:
        return [(r["status"], r["atr_rel"]) for r in
                c.execute("SELECT status, atr_rel FROM sinais ORDER BY id DESC LIMIT 1")]


def test_o_scan_anota_quem_entra_na_fila(banco, monkeypatch):
    _semear(30, 0.03)
    assert _scan(monkeypatch) == [("novo", 2.0)]


def test_o_scan_anota_tambem_o_rejeitado_por_fluxo(banco, monkeypatch):
    """Os dois grupos com a mesma regua, como o [Q-4] e o [CD-1]."""
    _semear(30, 0.03)

    def rejeita(s, a, cfg):
        s["rejeitado_por"] = "fluxo"
        return False, "fluxo contra o SHORT"
    assert _scan(monkeypatch, rejeita) == [(signal_engine.REJEITADO_FLUXO, 2.0)]


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
            velho = c.execute("SELECT atr_rel FROM sinais").fetchone()
    finally:
        db.DB = original
    assert "atr_rel" in colunas and velho["atr_rel"] is None
