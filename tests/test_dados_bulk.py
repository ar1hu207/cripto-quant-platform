# -*- coding: utf-8 -*-
"""Testes de PARSING e NORMALIZACAO do `pesquisa/dados_bulk.py`. [N-1] [N-2] [N-3]

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

# BTCUSDT-1h-2020-09.zip (futures/um) -- SEM linha de cabecalho. Ate 2021-12 e assim.
KLINES_SEM_HEADER = (
    "1598918400000,11658.11,11675.00,11531.34,11618.27,15015.299,"
    "1598921999999,174112062.33123,48351,6666.854,77327235.25097,0\n"
    "1598922000000,11618.27,11643.75,11593.00,11634.31,4410.780,"
    "1598925599999,51261715.25539,18795,2151.537,25008941.58982,0\n"
)

# BTCUSDT-1h-2025-06.zip (futures/um) -- COM cabecalho. De 2022-01 em diante e assim.
KLINES_COM_HEADER = (
    "open_time,open,high,low,close,volume,close_time,quote_volume,count,"
    "taker_buy_volume,taker_buy_quote_volume,ignore\n"
    "1748736000000,104544.60,104599.60,104277.30,104408.70,3438.526,"
    "1748739599999,358998670.72560,71534,1691.726,176614558.10500,0\n"
    "1748739600000,104408.70,104500.00,104300.00,104450.00,2000.000,"
    "1748743199999,208900000.00000,50000,1000.000,104450000.00000,0\n"
)

# BTCUSDT-1h-2025-01.zip (spot) -- sem header E com timestamp em MICROssegundo.
KLINES_SPOT_MICROSSEGUNDO = (
    "1735689600000000,93548.80,94449.20,93460.20,94363.60,5744.609,"
    "1735693199999999,539615914.46460,105263,3278.334,308056781.54270,0\n"
)

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


# ------------------------------------------------------------------ armadilha 3: header

def test_kline_sem_header_recebe_as_colunas_canonicas():
    """Ate 2021-12 o arquivo comeca direto no dado. Sem tratar, a primeira BARRA vira o
    nome das colunas e o mes perde o candle de abertura em silencio."""
    df = db.normalizar_klines(KLINES_SEM_HEADER)
    assert list(df.columns) == db.COLUNAS_KLINES + ["datetime"]
    assert len(df) == 2                        # as duas linhas sao dado, nenhuma e header
    assert df["open"].iloc[0] == pytest.approx(11658.11)


def test_kline_com_header_nao_le_o_cabecalho_como_barra():
    df = db.normalizar_klines(KLINES_COM_HEADER)
    assert list(df.columns) == db.COLUNAS_KLINES + ["datetime"]
    assert len(df) == 2
    assert df["open"].iloc[0] == pytest.approx(104544.60)


def test_as_duas_epocas_normalizam_para_o_mesmo_conjunto_de_colunas():
    """O criterio de aceite do [N-2], em memoria: 2020 (sem header) e 2025 (com header)
    tem que sair identicos, senao concatenar os dois cria coluna pela metade."""
    antigo = db.normalizar_klines(KLINES_SEM_HEADER)
    novo = db.normalizar_klines(KLINES_COM_HEADER)
    assert list(antigo.columns) == list(novo.columns)
    assert "taker_buy_volume" in antigo.columns
    assert pd.concat([antigo, novo]).notna().all().all()


def test_taker_buy_volume_chega_com_o_valor_certo():
    """E a coluna inteira do [N-2]: e ela que permite backtestar o portao de fluxo em
    anos, contra os 10 dias que deram p=0,58."""
    assert db.normalizar_klines(KLINES_SEM_HEADER)["taker_buy_volume"].iloc[0] \
        == pytest.approx(6666.854)
    assert db.normalizar_klines(KLINES_COM_HEADER)["taker_buy_volume"].iloc[0] \
        == pytest.approx(1691.726)


# ------------------------------------------------------------------ armadilha 4: unidade

def test_spot_em_microssegundo_nao_vira_ano_57000():
    """Armadilha 4. O spot trocou ms por us em 2025-01 sem mudar coluna nem header.
    Com `unit="ms"` fixo o mesmo numero daria 56971-10-25 -- sem excecao e sem aviso."""
    df = db.normalizar_klines(KLINES_SPOT_MICROSSEGUNDO)
    assert df["datetime"].iloc[0] == pd.Timestamp("2025-01-01 00:00:00")


def test_futures_em_milissegundo_continua_certo():
    """A deteccao nao pode "consertar" quem ja estava certo."""
    df = db.normalizar_klines(KLINES_COM_HEADER)
    assert df["datetime"].iloc[0] == pd.Timestamp("2025-06-01 00:00:00")


# ------------------------------------------------------------------ klines invalidos

def test_kline_sem_coluna_essencial_falha_alto():
    truncado = "1598918400000,11658.11,11675.00,11531.34,11618.27,15015.299\n"
    with pytest.raises(ValueError, match="essenciais"):
        db.normalizar_klines(truncado)


def test_kline_com_colunas_demais_falha_alto():
    with pytest.raises(ValueError):
        db.normalizar_klines("1," * 13 + "1\n")


def test_kline_vazio_falha_alto():
    with pytest.raises(ValueError):
        db.normalizar_klines("   ")


def test_chave_klines_por_mercado():
    assert db.chave_klines("BTCUSDT", "1h", "2024-01", "futures_um") == (
        "data/futures/um/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-01.zip")
    assert db.chave_klines("BTCUSDT", "1h", "2024-01", "spot") == (
        "data/spot/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2024-01.zip")


def test_mercado_desconhecido_falha_alto():
    with pytest.raises(ValueError):
        db.chave_klines("BTCUSDT", "1h", "2024-01", "futuros")


def test_meses_e_inclusivo_nas_duas_pontas():
    assert db.meses("2024-11", "2025-01") == ["2024-11", "2024-12", "2025-01"]
    assert db.meses("2024-01", "2024-01") == ["2024-01"]


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


def test_meses_de_klines_concatenados_saem_ordenados_e_sem_repeticao(monkeypatch):
    """Cada mes vem ordenado, mas a CONCATENACAO tambem precisa vir -- e o limite de mes e
    onde a sobreposicao aparece."""
    por_mes = {
        "2020-09": KLINES_SEM_HEADER,
        "2020-10": KLINES_SEM_HEADER + KLINES_SEM_HEADER,   # repete o mesmo instante
    }

    def falso(chave, usar_cache=True, verificar_hash=True):
        for mes, texto in por_mes.items():
            if mes in chave:
                return _zipar("k.csv", texto)
        return None
    monkeypatch.setattr(db, "baixar_zip", falso)

    df = db.baixar_klines("BTCUSDT", "1h", "2020-09", "2020-10")
    assert db.estritamente_crescente(df["datetime"])
    assert len(df) == 2
    assert df.attrs["ausentes"] == []


# ------------------------------------------------------------------ [N-3] par que morreu

def test_par_deslistado_para_de_ter_arquivo_e_isso_e_o_DADO(monkeypatch):
    """[N-3]. Par deslistado simplesmente PARA de ter mes no bucket. Se `baixar_klines`
    levantasse no primeiro 404, o vies de sobrevivencia ficaria impossivel de medir
    justamente pelo modulo que existe para mata-lo."""
    def falso(chave, usar_cache=True, verificar_hash=True):
        if "2022-05" in chave:
            return _zipar("k.csv", KLINES_SEM_HEADER)
        return None                                    # 404: o par ja tinha morrido
    monkeypatch.setattr(db, "baixar_zip", falso)

    df = db.baixar_klines("LUNAUSDT", "1h", "2022-05", "2022-07")
    assert len(df) == 2
    assert df.attrs["ausentes"] == ["2022-06", "2022-07"]


def test_listar_periodos_le_a_listagem_e_devolve_os_meses_ordenados(monkeypatch):
    """O ultimo mes devolvido aqui e a data de MORTE do par -- e o que torna o vies
    visivel sem pedir mes a mes e contar 404."""
    xml = (b"<ListBucketResult>"
           b"<Contents><Key>data/futures/um/monthly/klines/LUNAUSDT/1h/"
           b"LUNAUSDT-1h-2022-05.zip</Key></Contents>"
           b"<Contents><Key>data/futures/um/monthly/klines/LUNAUSDT/1h/"
           b"LUNAUSDT-1h-2021-01.zip</Key></Contents>"
           b"<Contents><Key>data/futures/um/monthly/klines/LUNAUSDT/1h/"
           b"LUNAUSDT-1h-2022-05.zip.CHECKSUM</Key></Contents>"
           b"</ListBucketResult>")
    monkeypatch.setattr(db, "_http", lambda *a, **k: xml)
    assert db.listar_periodos("LUNAUSDT", "1h", "futures_um") == ["2021-01", "2022-05"]


def test_listar_periodos_de_par_que_nunca_existiu_e_lista_vazia(monkeypatch):
    monkeypatch.setattr(db, "_http", lambda *a, **k: b"<ListBucketResult></ListBucketResult>")
    assert db.listar_periodos("NAOEXISTEUSDT", "1h", "futures_um") == []
