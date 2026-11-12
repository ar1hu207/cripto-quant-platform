"""[RJ-1] O rótulo do gestor de saída diz o que o bot faz, em R -- e não manda realizar.

O painel mostrava "🟢 REALIZAR JÁ" a +5% de ROE com qualquer cruzamento de EMA20 e o bot não
realizava (com trailing ligado o gestor de saída só avisa). O T39 mediu a ordem literal: R$10k
→ R$40 em 45 meses. Os testes travam três coisas: o texto não volta a mandar realizar, o NÍVEL
não muda (é dele que o auto-fechar e o botão do painel dependem), e o plano descrito é o real.
"""
import json

import pandas as pd
import pytest

import signal_engine


def _df_reversao_long():
    """Velas já com indicadores: no candle fechado (n-2) o LONG perde a EMA20."""
    n = 10
    df = pd.DataFrame({"close": [101.0] * n, "rsi": [55.0] * n,
                       "ema_r": [100.0] * n, "ema_l": [99.0] * n})
    df.loc[n - 2, "close"] = 99.5            # cp >= er e c < er: "perdeu a EMA20"
    return df


@pytest.fixture
def sem_rede(monkeypatch):
    monkeypatch.setattr(signal_engine, "_velas", lambda *a, **k: [])
    monkeypatch.setattr(signal_engine, "preparar", lambda _df: _df_reversao_long())
    monkeypatch.setattr(signal_engine.mercado, "book", lambda _a: None)


CFG = {"timeframe": "15m", "alvo_roe": "5", "trailing_ativo": "1", "trailing_unidade": "R",
       "trailing_arma_r": "3", "tp_ativo": "1", "auto_trade": "1", "auto_fechar_saida": "1"}


def _pos(preco=102.0, stop=99.0, tps=None, pnl=20.0):
    # entrada 100, stop da abertura 99 -> 1R = 1,0 de preço; preço 102 = +2R
    return {"id": 7, "ativo": "X/USDT", "direcao": "LONG", "entrada": 100.0,
            "stop_abertura": 99.0, "stop": stop, "preco_atual": preco,
            "pnl": pnl, "valor_reais": 100.0, "tps": tps}


PLANO = json.dumps({"valor_inicial": 100.0, "niveis": [
    {"preco": 101.5, "r": 1.5, "frac": 0.34, "fonte": "pivo", "feito": True},
    {"preco": 103.8, "r": 3.8, "frac": 0.33, "fonte": "pivo"},
    {"preco": 107.9, "r": 7.9, "frac": 0.33, "fonte": "fallback"}]})


def test_forte_nao_manda_realizar_e_diz_o_plano_em_R(sem_rede):
    sd = signal_engine.avaliar_saida(_pos(tps=PLANO), dict(CFG))
    assert sd["nivel"] == "forte"                       # o nível segue o mesmo
    assert "REALIZAR" not in sd["acao"]
    assert "+2.0R" in sd["acao"] and "perdeu a EMA20" in sd["acao"] and "15m" in sd["acao"]
    assert "TP2 em 3.8R" in sd["acao"] and "meta final 7.9R" in sd["acao"]
    assert "trailing arma em 3R" in sd["acao"]
    assert sd["r"] == 2.0


def test_stop_ja_acima_da_entrada_aparece_travado(sem_rede):
    sd = signal_engine.avaliar_saida(_pos(preco=105.0, stop=102.0, pnl=50.0), dict(CFG))
    assert "stop travado em +2.0R" in sd["acao"] and "trailing arma" not in sd["acao"]


def test_ultimo_tp_nao_repete_meta_final(sem_rede):
    plano = json.loads(PLANO)
    plano["niveis"][1]["feito"] = True
    sd = signal_engine.avaliar_saida(_pos(tps=json.dumps(plano)), dict(CFG))
    assert "TP3 em 7.9R" in sd["acao"] and "meta final" not in sd["acao"]


def test_quando_o_bot_fecha_de_verdade_o_rotulo_diz_isso(sem_rede):
    """Única config em que o auto-trader realiza no aviso: auto_trade on, trailing off,
    auto_fechar_saida on (autotrader.auto_executar, passo 1)."""
    cfg = dict(CFG, trailing_ativo="0")
    sd = signal_engine.avaliar_saida(_pos(tps=PLANO), cfg)
    assert sd["nivel"] == "forte" and "o bot realiza neste ciclo" in sd["acao"]
    cfg["auto_trade"] = "0"
    assert "o bot segura" in signal_engine.avaliar_saida(_pos(tps=PLANO), cfg)["acao"]


def test_sem_stop_de_abertura_volta_ao_roe(sem_rede):
    p = _pos()
    p["stop_abertura"] = None
    sd = signal_engine.avaliar_saida(p, dict(CFG))
    assert sd["r"] is None and "+20.0%" in sd["acao"] and "REALIZAR" not in sd["acao"]


def test_risco_mostra_o_stop_em_R(sem_rede):
    sd = signal_engine.avaliar_saida(_pos(preco=99.5, pnl=-5.0), dict(CFG))
    assert sd["nivel"] == "risco"
    assert "-0.5R" in sd["acao"] and "stop em -1.0R" in sd["acao"]
