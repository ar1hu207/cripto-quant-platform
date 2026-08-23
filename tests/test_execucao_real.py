# -*- coding: utf-8 -*-
"""Item (d) do [Q-6]: `pesquisa.dados.baixar_ohlcv` nao grava candle em FORMACAO.

Este arquivo e o par de `test_pnl.py` no territorio T-EXEC-REAL: la mora a aritmetica do
P&L, aqui mora o resto do modelo de execucao -- comecando pelo DADO em que o backtest roda.

O defeito nao levanta excecao e nao aparece em nenhum numero: ele so faz duas baixas do
mesmo dia discordarem sobre a mesma barra, e o nome do arquivo de cache promete o
contrario. Por isso as asseracoes sao de IGUALDADE entre dois downloads, e nao de "rodou".

**Sem rede e sem esperar os 22 minutos do criterio de aceite.** O que decide se uma barra
fechou e o timestamp dela contra o "agora", e os dois vem do objeto da exchange
(`ex.milliseconds()`, `ex.fetch_ohlcv`) -- entao os dois sao injetaveis. O duble abaixo e a
exchange inteira que `baixar_ohlcv` usa.
"""
import types

import pandas as pd
import pytest

from pesquisa import dados

H = 3_600_000                                   # 1h em ms
BASE = (1_756_000_000_000 // H) * H             # instante fixo, alinhado na hora cheia
AS_14H37 = BASE + 14 * H + 37 * 60_000          # a barra das 14h esta em formacao
AS_14H59 = BASE + 14 * H + 59 * 60_000          # a MESMA barra ainda esta em formacao


class _ExFake:
    """So o que `baixar_ohlcv` chama: `parse_timeframe`, `milliseconds` e `fetch_ohlcv`.

    `parcial` e o candle corrente com os valores que ele tinha NAQUELE instante -- e a peca
    que muda entre 14h37 e 14h59 no mundo real, e e ela que nao pode chegar ao CSV."""

    def __init__(self, agora_ms, n_barras=15, parcial_close=None):
        self.agora_ms = agora_ms
        self.barras = [[BASE + k * H, 100.0 + k, 101.0 + k, 99.0 + k, 100.5 + k, 10.0]
                       for k in range(n_barras)]
        if parcial_close is not None:           # a ultima e a barra em formacao
            self.barras[-1][4] = parcial_close
            self.barras[-1][2] = max(self.barras[-1][2], parcial_close)

    def parse_timeframe(self, timeframe):
        return {"1h": 3600, "15m": 900, "5m": 300}[timeframe]

    def milliseconds(self):
        return self.agora_ms

    def fetch_ohlcv(self, par, timeframe=None, since=None, limit=1000):
        return [list(b) for b in self.barras if b[0] >= (since or 0)][:limit]


@pytest.fixture
def cache_isolado(tmp_path, monkeypatch):
    """`CACHE_DIR` num diretorio do teste: nada escreve em `pesquisa/dados_cache/`.
    Devolve um `baixar(agora, ...)` que troca a exchange e o diretorio a cada chamada, para
    que duas baixas seguidas sejam duas baixas de verdade (e nao cache-hit)."""
    contador = {"n": 0}

    def baixar(agora_ms, parcial_close=None, **kw):
        contador["n"] += 1
        alvo = tmp_path / f"baixa{contador['n']}"
        alvo.mkdir()
        ex = _ExFake(agora_ms, parcial_close=parcial_close)
        monkeypatch.setattr(dados, "CACHE_DIR", str(alvo))
        monkeypatch.setattr(dados, "ccxt", types.SimpleNamespace(binance=lambda _cfg: ex))
        df = dados.baixar_ohlcv(par="ETH/USDT", timeframe="1h", dias=1, **kw)
        return df, alvo

    return baixar


# ---------------------------------------------------------------- `_fechados`, isolado

@pytest.mark.parametrize("ultimo_ts,agora,mantem", [
    (BASE + 13 * H, BASE + 14 * H,           True),   # fechou exatamente agora: entra
    (BASE + 13 * H, BASE + 14 * H + 1,       True),   # fechou ha 1 ms: entra
    (BASE + 13 * H, BASE + 14 * H - 1,       False),  # falta 1 ms pra fechar: NAO entra
    (BASE + 13 * H, BASE + 13 * H,           False),  # acabou de abrir: NAO entra
])
def test_o_corte_e_o_fim_do_intervalo_e_nao_o_inicio(ultimo_ts, agora, mantem):
    """A confusao que este item corrige e usar `timestamp <= agora`: o timestamp de um
    candle e a ABERTURA dele, entao esse teste aceitaria toda barra em formacao. O corte e
    `timestamp + tf <= agora`."""
    df = pd.DataFrame({"timestamp": [ultimo_ts], "close": [1.0]})
    assert len(dados._fechados(df, H, agora)) == (1 if mantem else 0)


def test_descarta_todas_as_barras_ainda_abertas_nao_so_a_ultima():
    """Filtra o DataFrame, nao a ultima linha: se o feed vier fora de ordem, o resultado
    continua sendo "so barra fechada"."""
    df = pd.DataFrame({"timestamp": [BASE + k * H for k in range(6)]})
    out = dados._fechados(df, H, BASE + 4 * H)
    assert list(out["timestamp"]) == [BASE + k * H for k in range(4)]


def test_frame_vazio_e_timeframe_zero_nao_explodem():
    """`baixar_ohlcv` chama isto com o que a exchange devolveu, inclusive nada."""
    vazio = pd.DataFrame({"timestamp": []})
    assert dados._fechados(vazio, H, BASE).empty
    cheio = pd.DataFrame({"timestamp": [BASE]})
    assert len(dados._fechados(cheio, 0, BASE)) == 1        # sem tf nao ha o que decidir


# ------------------------------------------------- o criterio de aceite do card, fim a fim

def test_baixar_as_14h37_e_as_14h59_produz_a_mesma_ultima_barra_fechada(cache_isolado):
    """O criterio de aceite, literal. As duas baixas caem dentro do mesmo candle de 1h, e a
    barra corrente esta em estados diferentes nos dois instantes -- mas nenhuma das duas a
    grava, entao os dois DataFrames sao identicos, ultima barra inclusive."""
    df_37, _ = cache_isolado(AS_14H37, parcial_close=999.0)
    df_59, _ = cache_isolado(AS_14H59, parcial_close=555.0)

    assert df_37["timestamp"].iloc[-1] == BASE + 13 * H          # a barra das 14h ficou fora
    assert df_59["timestamp"].iloc[-1] == BASE + 13 * H
    pd.testing.assert_frame_equal(df_37, df_59)


def test_o_teste_acima_nao_e_vazio_a_barra_em_formacao_de_fato_diferia(cache_isolado):
    """A igualdade so prova alguma coisa se houvesse o que diferir. Aqui a mesma comparacao
    e feita SEM o corte -- e as duas baixas discordam, que era o estado anterior ao card."""
    ex_37 = _ExFake(AS_14H37, parcial_close=999.0)
    ex_59 = _ExFake(AS_14H59, parcial_close=555.0)
    cru_37 = ex_37.fetch_ohlcv("ETH/USDT", since=0)
    cru_59 = ex_59.fetch_ohlcv("ETH/USDT", since=0)
    assert cru_37[-1][0] == cru_59[-1][0]                        # a MESMA barra...
    assert cru_37[-1][4] != cru_59[-1][4]                        # ...com fechamento diferente
    assert cru_37[:-1] == cru_59[:-1]                            # e as fechadas ja concordavam


def test_o_csv_gravado_so_tem_barra_fechada(cache_isolado):
    """O CSV e o que os validadores leem depois -- e o que o nome do arquivo promete ser uma
    janela reproduzivel do dia. A garantia tem de valer no arquivo, nao so no retorno."""
    _, alvo = cache_isolado(AS_14H37, parcial_close=999.0)
    arquivos = list(alvo.glob("*.csv"))
    assert len(arquivos) == 1
    csv = pd.read_csv(arquivos[0], parse_dates=["datetime"])
    assert ((csv["timestamp"] + H) <= AS_14H37).all()
    assert 999.0 not in set(csv["close"])


def test_a_barra_fecha_e_a_baixa_seguinte_a_inclui(cache_isolado):
    """O corte nao e uma janela fixa: passada a hora cheia, a barra que estava em formacao
    entra -- com os valores DEFINITIVOS dela, nao com os do download anterior."""
    df_antes, _ = cache_isolado(AS_14H59, parcial_close=999.0)
    df_depois, _ = cache_isolado(BASE + 15 * H + 60_000, parcial_close=None)
    assert df_antes["timestamp"].iloc[-1] == BASE + 13 * H
    assert df_depois["timestamp"].iloc[-1] == BASE + 14 * H
    assert 999.0 not in set(df_depois["close"])


def test_as_barras_fechadas_sobrevivem_intactas(cache_isolado):
    """Regressao na outra direcao: cortar demais seria perder historico em silencio. Tudo
    que o feed deu como fechado tem de chegar ao DataFrame, com as colunas de sempre."""
    df, _ = cache_isolado(AS_14H37, parcial_close=999.0)
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume", "datetime"]
    assert len(df) == 14                                        # 15 barras do feed, 1 em formacao
    assert list(df["timestamp"]) == [BASE + k * H for k in range(14)]
    assert df["datetime"].iloc[-1] == pd.to_datetime(BASE + 13 * H, unit="ms")
