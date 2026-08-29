# -*- coding: utf-8 -*-
"""Testes de PARSING e NORMALIZACAO do `pesquisa/dados_bulk.py`. [N-1]

**Nenhum teste daqui toca a rede, e isso e requisito, nao preferencia.** A suite inteira
roda antes de todo merge (`CLAUDE.md` §0); teste que baixa arquivo transforma queda de
rede -- ou o bucket fora do ar -- em suite vermelha, e a partir dai ninguem distingue mais
"quebrei o codigo" de "o wi-fi caiu". A prova COM rede existe, e separada, e roda por
`python -m pesquisa.dados_bulk`.

As fixtures abaixo sao recortes LITERAIS de arquivos reais do bucket -- cada bloco diz de
qual arquivo veio. Fixture inventada testaria o parser contra a imaginacao de quem
escreveu o parser; estas testam contra o que a Binance realmente publicou, inclusive as
armadilhas.
"""
import io
import zipfile

import pandas as pd
import pytest

from pesquisa import dados_bulk as db


# ------------------------------------------------------------------ fixtures literais

_M_HDR = ("create_time,symbol,sum_open_interest,sum_open_interest_value,"
          "count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,"
          "count_long_short_ratio,sum_taker_long_short_vol_ratio\n")

# Formato de BTCUSDT-metrics-2024-08-08.zip: embaralhado. No real sao 74 quebras de ordem.
METRICS_FORA_DE_ORDEM = _M_HDR + (
    "2024-08-08 00:35:00,BTCUSDT,77082.018,3217372598.5128,2.402,1.395,2.653,1.057\n"
    "2024-08-08 00:20:00,BTCUSDT,77234.084,3232040965.3421,2.419,1.396,2.673,1.035\n"
    "2024-08-08 00:30:00,BTCUSDT,77100.000,3220000000.0000,2.410,1.390,2.660,1.040\n"
    "2024-08-08 00:25:00,BTCUSDT,77150.000,3225000000.0000,2.415,1.392,2.665,1.045\n"
)

# Formato de BTCUSDT-metrics-2020-09-01.zip: cada linha aparece DUAS vezes (576 p/ 288).
METRICS_DUPLICADO = _M_HDR + (
    "2020-09-01 00:00:00,BTCUSDT,39080.231,456144300.0,1.175,1.230,1.357,0.783\n"
    "2020-09-01 00:00:00,BTCUSDT,39080.231,456144300.0,1.175,1.230,1.357,0.783\n"
    "2020-09-01 00:05:00,BTCUSDT,39100.000,456400000.0,1.180,1.235,1.360,0.790\n"
    "2020-09-01 00:05:00,BTCUSDT,39100.000,456400000.0,1.180,1.235,1.360,0.790\n"
)

METRICS_LIMPO = _M_HDR + (
    "2024-01-15 00:00:00,BTCUSDT,77082.018,3217372598.5128,2.402,1.395,2.653,1.057\n"
    "2024-01-15 00:05:00,BTCUSDT,77234.084,3232040965.3421,2.419,1.396,2.673,1.035\n"
)


# ------------------------------------------------------------------ armadilhas 1 e 2

def test_metrics_fora_de_ordem_sai_estritamente_crescente():
    """Armadilha 1. Sem ordenar, a linha seguinte pode ser mais ANTIGA que a atual, e um
    backtest que caminha pelo arquivo le o futuro."""
    cru = pd.to_datetime(pd.read_csv(io.StringIO(METRICS_FORA_DE_ORDEM))["create_time"])
    assert not cru.is_monotonic_increasing            # a fixture reproduz o defeito

    df = db.normalizar_metrics(METRICS_FORA_DE_ORDEM)
    assert db.estritamente_crescente(df["datetime"])
    assert df["datetime"].iloc[0] == pd.Timestamp("2024-08-08 00:20:00")
    assert df["datetime"].iloc[-1] == pd.Timestamp("2024-08-08 00:35:00")


def test_metrics_ordenado_mantem_a_linha_junto_do_proprio_timestamp():
    """Ordenar so serve se a LINHA acompanhar. Um sort que reordenasse a coluna de tempo
    sozinha deixaria o indice crescente e o dado trocado -- pior que o defeito."""
    df = db.normalizar_metrics(METRICS_FORA_DE_ORDEM)
    linha = df[df["datetime"] == pd.Timestamp("2024-08-08 00:20:00")].iloc[0]
    assert linha["sum_open_interest"] == pytest.approx(77234.084)


def test_metrics_duplicado_e_deduplicado():
    """Armadilha 2. 576 linhas para 288 instantes: duplicata silenciosa dobra o peso de um
    instante em qualquer media, regressao ou contagem."""
    df = db.normalizar_metrics(METRICS_DUPLICADO)
    assert len(df) == 2
    assert db.estritamente_crescente(df["datetime"])


def test_metrics_traz_oi_os_tres_ratios_e_o_taker_ratio():
    """As colunas que o [N-1] promete, uma a uma."""
    df = db.normalizar_metrics(METRICS_LIMPO)
    for coluna in ("sum_open_interest",
                   "count_toptrader_long_short_ratio",
                   "sum_toptrader_long_short_ratio",
                   "count_long_short_ratio",
                   "sum_taker_long_short_vol_ratio"):
        assert coluna in df.columns
        assert df[coluna].notna().all()
    assert df["sum_open_interest"].iloc[0] == pytest.approx(77082.018)


def test_estritamente_crescente_pega_os_dois_defeitos():
    assert db.estritamente_crescente(pd.Series(pd.to_datetime(["2024-01-01", "2024-01-02"])))
    assert not db.estritamente_crescente(                       # fora de ordem
        pd.Series(pd.to_datetime(["2024-01-02", "2024-01-01"])))
    assert not db.estritamente_crescente(                       # repetido
        pd.Series(pd.to_datetime(["2024-01-01", "2024-01-01"])))


# ------------------------------------------------------------------ unidade do epoch

@pytest.mark.parametrize("valor,unidade", [
    (1_735_689_600, "s"),
    (1_735_689_600_000, "ms"),
    (1_735_689_600_000_000, "us"),
    (1_735_689_600_000_000_000, "ns"),
])
def test_unidade_epoch_reconhece_as_quatro(valor, unidade):
    assert db._unidade_epoch(valor) == unidade


@pytest.mark.parametrize("absurdo", [0, 1, 10 ** 25])
def test_unidade_epoch_recusa_o_que_nao_e_data(absurdo):
    """Falhar alto e melhor que escolher a unidade "menos errada" e seguir."""
    with pytest.raises(ValueError):
        db._unidade_epoch(absurdo)


def test_tem_cabecalho_decide_pelo_primeiro_campo():
    assert db._tem_cabecalho(METRICS_LIMPO) is True
    assert db._tem_cabecalho("2024-01-15 00:00:00,BTCUSDT\n") is True   # data nao e int
    assert db._tem_cabecalho("1598918400000,11658.11\n") is False


# ------------------------------------------------------------------ entrada invalida

def test_csv_vazio_falha_alto():
    with pytest.raises(ValueError):
        db.normalizar_metrics("   ")


def test_metrics_sem_coluna_essencial_falha_alto():
    """Devolver NaN aqui adiaria o erro para dentro do backtest, 200 linhas depois, onde
    ele vira "resultado ruim" em vez de "arquivo errado"."""
    with pytest.raises(ValueError, match="essenciais"):
        db.normalizar_metrics("create_time,symbol\n2024-01-15 00:00:00,BTCUSDT\n")


# ------------------------------------------------------------------ chaves do bucket

def test_metrics_usa_o_caminho_DIARIO_e_nao_o_mensal():
    """Guarda de regressao do fato mais caro desta entrega: `monthly/metrics/` devolve
    404 -- o bucket so publica `metrics` em `daily/`. Quem supuser a simetria com os
    klines escreve um baixador que nunca acha nada, e o 404 sai como "dia ausente"."""
    chave = db.chave_metrics("BTCUSDT", "2024-01-15")
    assert chave == ("data/futures/um/daily/metrics/BTCUSDT/"
                     "BTCUSDT-metrics-2024-01-15.zip")
    assert "/monthly/" not in chave


def test_dias_e_inclusivo_nas_duas_pontas():
    assert db.dias("2024-01-30", "2024-02-01") == ["2024-01-30", "2024-01-31", "2024-02-01"]
    assert db.dias("2024-01-30", "2024-01-30") == ["2024-01-30"]


# ------------------------------------------------------------------ zip e checksum

def _zipar(nome, texto):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(nome, texto)
    return buf.getvalue()


def test_texto_do_zip_extrai_o_unico_csv():
    assert db.texto_do_zip(_zipar("x.csv", METRICS_LIMPO)) == METRICS_LIMPO


def test_zip_sem_csv_unico_falha_alto():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.csv", "1")
        z.writestr("b.csv", "2")
    with pytest.raises(ValueError):
        db.texto_do_zip(buf.getvalue())


def test_checksum_que_nao_bate_derruba_o_download(monkeypatch):
    """Zip truncado por rede ruim vira um dia faltando no meio do backtest, e nada avisa.
    O bucket publica o sha256 ao lado; conferir custa um GET."""
    def falso(url, **kwargs):
        return b"nao-e-o-zip" if url.endswith(".CHECKSUM") else b"conteudo"
    monkeypatch.setattr(db, "_http", falso)
    with pytest.raises(RuntimeError, match="sha256"):
        db.baixar_zip("data/qualquer.zip", usar_cache=False)


def test_checksum_que_bate_deixa_passar(monkeypatch):
    import hashlib
    conteudo = b"conteudo"
    soma = hashlib.sha256(conteudo).hexdigest().encode() + b"  arquivo.zip\n"

    def falso(url, **kwargs):
        return soma if url.endswith(".CHECKSUM") else conteudo
    monkeypatch.setattr(db, "_http", falso)
    assert db.baixar_zip("data/qualquer.zip", usar_cache=False) == conteudo


# ------------------------------------------------------------------ concatenacao

def test_metrics_concatena_dias_em_ordem(monkeypatch):
    """Cada dia sai ordenado, mas a CONCATENACAO tambem precisa sair -- e a virada de dia
    e justamente onde a sobreposicao aparece."""
    def falso(chave, usar_cache=True, verificar_hash=True):
        if chave.endswith("2020-09-01.zip"):
            return _zipar("m.csv", METRICS_DUPLICADO)
        if chave.endswith("2020-09-02.zip"):
            return _zipar("m.csv", METRICS_FORA_DE_ORDEM)
        return None
    monkeypatch.setattr(db, "baixar_zip", falso)

    df = db.baixar_metrics("BTCUSDT", "2020-09-01", "2020-09-02")
    assert db.estritamente_crescente(df["datetime"])
    assert len(df) == 2 + 4
    assert df.attrs["ausentes"] == []


def test_dia_ausente_nao_explode_e_fica_registrado(monkeypatch):
    """Buraco no historico e um fato do bucket. Levantar no primeiro 404 impediria de
    baixar qualquer janela que atravesse um dia faltando."""
    def falso(chave, usar_cache=True, verificar_hash=True):
        return _zipar("m.csv", METRICS_LIMPO) if chave.endswith("2024-01-15.zip") else None
    monkeypatch.setattr(db, "baixar_zip", falso)

    df = db.baixar_metrics("BTCUSDT", "2024-01-15", "2024-01-17")
    assert len(df) == 2
    assert df.attrs["ausentes"] == ["2024-01-16", "2024-01-17"]


def test_exigir_completo_transforma_ausencia_em_erro(monkeypatch):
    """Quem precisa de serie fechada pede -- o default e permissivo de proposito."""
    monkeypatch.setattr(db, "baixar_zip", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="ausentes"):
        db.baixar_metrics("BTCUSDT", "2024-01-15", "2024-01-15", exigir_completo=True)


def test_tudo_ausente_devolve_dataframe_vazio_e_nao_None(monkeypatch):
    monkeypatch.setattr(db, "baixar_zip", lambda *a, **k: None)
    df = db.baixar_metrics("BTCUSDT", "2024-01-15", "2024-01-15")
    assert len(df) == 0
    assert df.attrs["ausentes"] == ["2024-01-15"]
