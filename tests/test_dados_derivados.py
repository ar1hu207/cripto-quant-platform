# -*- coding: utf-8 -*-
"""[Q-17] Provas do baixador de dados de posicionamento (Fase 1 do plano).

**O que estes testes existem para impedir**, em uma frase cada:

* que o alinhamento entregue a uma barra um numero que so existiu DEPOIS dela (o
  look-ahead de 5 min que a reconciliacao achou -- `PLANO-Q17-INFORMACAO` §4.1);
* que uma feature nasca com janela maior do que o bot ao vivo consegue enxergar (o teto
  de 30 dias do REST -- §4);
* que um buraco no dump vire "o valor de ontem repetido" em vez de barra sem dado;
* que alguem promova a feature uma coluna que NAO reconcilia com o caminho ao vivo (§4.2).

**Nenhum destes testes usa rede.** O insumo e um dia REAL de `metrics`
(`tests/dados/ETHUSDT-metrics-2024-06-01.csv`, 288 buckets, baixado em 2026-08-25). A
reconciliacao de verdade precisa de rede e esta no fim do arquivo, atras do marcador
`rede`, pulando sozinha quando `CRIPTO_TESTE_REDE` nao esta ligado -- a suite tem de
continuar verde numa maquina offline.
"""
import io
import os

import pandas as pd
import pytest

from pesquisa import dados_derivados as dd

DIA_FIXTURE = "2024-06-01"
CSV_FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados",
                           f"ETHUSDT-metrics-{DIA_FIXTURE}.csv")
MIN = 60_000
HORA = 60 * MIN


@pytest.fixture
def metricas():
    """O dia real, ja como o `baixar_metricas` devolveria."""
    with io.open(CSV_FIXTURE, encoding="utf-8") as f:
        return dd._para_frame(f.read())


def _ms(txt):
    return int(pd.Timestamp(txt, tz="UTC").timestamp() * 1000)


# ============================ o carimbo e o look-ahead ============================
def test_carimbo_sai_em_milissegundos_de_verdade(metricas):
    """O bug que este teste trava, e que a primeira versao do modulo TINHA.

    `.astype("int64") // 1_000_000` sobre a coluna de datas parece a conversao obvia para
    ms -- e devolve SEGUNDOS quando o pandas infere `datetime64[us]` em vez de `[ns]`, o
    que ele passou a fazer. Carimbo mil vezes menor nao estoura: ele alinha com nada, e o
    DataFrame inteiro vira NaN sem uma linha de erro. Ancorado num instante conhecido.
    """
    assert metricas["timestamp"].iloc[0] == _ms(f"{DIA_FIXTURE} 00:00:00")
    assert metricas["timestamp"].iloc[0] == 1_717_200_000_000
    assert pd.Timestamp(metricas["timestamp"].iloc[0], unit="ms", tz="UTC").year == 2024


def test_fixture_e_um_dia_inteiro_de_5_em_5_minutos(metricas):
    """Sanidade do insumo: se a fixture mudar de forma, os testes abaixo mentem."""
    assert len(metricas) == 288
    assert metricas["timestamp"].iloc[0] == _ms(f"{DIA_FIXTURE} 00:00:00")
    assert (metricas["timestamp"].diff().dropna() == dd.BUCKET_MS).all()
    for col in dd.COLUNAS:
        assert col in metricas.columns


def test_barra_recebe_o_bucket_de_15_min_antes_do_fechamento(metricas):
    """[Q-17 §4.1] A regra, escrita como igualdade.

    Barra de 1h ABERTA as 12:00 fecha as 13:00; o valor que ela pode usar e o bucket
    `13:00 - 15 min = 12:45`, e nenhum mais novo. Se alguem "melhorar" o
    `ATRASO_OBSERVACAO_MS` para zero, e este teste que cai.
    """
    abertura = _ms(f"{DIA_FIXTURE} 12:00:00")
    alinhado = dd.alinhar(metricas, [abertura + HORA], HORA)            # instante de fechamento

    esperado = metricas.loc[metricas["timestamp"] == _ms(f"{DIA_FIXTURE} 12:45:00")]
    assert not esperado.empty, "a fixture precisa ter o bucket das 12:45"
    assert alinhado["sum_open_interest"].iloc[0] == esperado["sum_open_interest"].iloc[0]


def test_nenhuma_barra_usa_bucket_posterior_ao_seu_fechamento(metricas):
    """A prova geral do mesmo ponto: varre o dia inteiro e exige que o valor de CADA barra
    tenha aparecido em algum bucket cujo instante observavel ja passou.

    Escrito por busca no dado, e nao repetindo a formula do modulo -- um teste que refaz a
    conta do codigo passa junto com o bug.
    """
    aberturas = [_ms(f"{DIA_FIXTURE} 00:00:00") + k * HORA for k in range(24)]
    alinhado = dd.alinhar(metricas, [a + HORA for a in aberturas], HORA)

    for fechamento, valor in zip(alinhado["timestamp"], alinhado["sum_open_interest"]):
        if pd.isna(valor):
            continue
        origem = metricas.loc[metricas["sum_open_interest"] == valor, "timestamp"]
        assert not origem.empty
        # observavel = carimbo do dump + o atraso medido. Tem de caber ANTES do fechamento.
        assert (origem + dd.ATRASO_OBSERVACAO_MS <= fechamento).any(), (
            f"barra que fecha em {fechamento} usou um bucket ainda nao observavel")


def test_atraso_cobre_o_pior_atraso_medido():
    """[Q-17 §4.1] A constante nao e gosto: ela tem de cobrir os dois efeitos medidos --
    o deslocamento de 1 bucket entre dump e REST (5 min) mais o atraso de publicacao
    observado (ate 6,2 min em 2026-08-25). Com folga ate o proximo bucket."""
    PIOR_ATRASO_MEDIDO_MS = int(6.2 * MIN)
    assert dd.ATRASO_OBSERVACAO_MS >= dd.BUCKET_MS + PIOR_ATRASO_MEDIDO_MS
    assert dd.ATRASO_OBSERVACAO_MS % dd.BUCKET_MS == 0, "ficar na grade de 5 min"


# ============================ buracos ============================
def test_buraco_no_dump_vira_nan_e_nao_o_valor_de_ontem(metricas):
    """`merge_asof` sem teto propaga o ultimo valor para sempre. Uma barra sem dado tem de
    aparecer como barra sem dado -- senao um mes faltando no dump vira um mes de OI
    congelado, que e pior do que nao ter o dado."""
    depois = _ms(f"{DIA_FIXTURE} 23:55:00") + 3 * dd.DIA_MS
    alinhado = dd.alinhar(metricas, [depois], HORA)
    assert pd.isna(alinhado["sum_open_interest"].iloc[0])


def test_borda_d_mais_1_vira_nan_e_nao_valor_repetido(metricas):
    """A CICATRIZ. O dump e D+1, entao quando as barras de hoje sao alinhadas o ultimo
    bucket disponivel e o de ontem 23:55. Com teto de um dia, o `merge_asof` dava a TODAS
    as 24 barras de hoje o MESMO numero de ontem -- o smoke test pegou quatro barras
    seguidas com `sum_open_interest = 2417752.521`, e nada estourou.

    Aqui a fixture faz o papel de "ontem" e se pede o dia seguinte inteiro. O invariante
    cobrado e "nenhum valor aparece em duas barras": a barra que fecha as 01:00 ainda cobre
    a ultima leitura (23:55 de ontem, observavel as 00:10), e essa e medida legitima -- o
    defeito era ela se REPETIR nas 23 barras seguintes.
    """
    amanha = _ms(f"{DIA_FIXTURE} 00:00:00") + dd.DIA_MS
    barras = [amanha + k * HORA for k in range(1, 25)]             # o dia seguinte inteiro
    alinhado = dd.alinhar(metricas, barras, HORA)

    oi = alinhado["sum_open_interest"]
    assert oi.notna().sum() <= 1, (
        "so a primeira barra pode alcancar o ultimo bucket de ontem; o resto e NaN. "
        f"veio: {oi.tolist()}")
    assert oi.dropna().is_unique, "nenhum valor pode aparecer em duas barras"
    assert oi.iloc[1:].isna().all()


def test_a_primeira_barra_apos_o_fim_do_dump_ainda_e_valida(metricas):
    """O espelho do teste acima: o teto e UMA barra, entao a barra imediatamente seguinte
    ao ultimo bucket ainda tem medida. Sem isto, "conservador" viraria "descarta tudo"."""
    fechamento = _ms(f"{DIA_FIXTURE} 23:55:00") + dd.ATRASO_OBSERVACAO_MS
    alinhado = dd.alinhar(metricas, [fechamento], HORA)
    assert not pd.isna(alinhado["sum_open_interest"].iloc[0])


def test_barra_anterior_ao_primeiro_bucket_vira_nan(metricas):
    antes = _ms(f"{DIA_FIXTURE} 00:00:00") - HORA
    alinhado = dd.alinhar(metricas, [antes], HORA)
    assert pd.isna(alinhado["sum_open_interest"].iloc[0])


def test_metricas_vazias_devolvem_colunas_e_nao_estouram():
    vazio = pd.DataFrame(columns=["timestamp", *dd.COLUNAS])
    alinhado = dd.alinhar(vazio, [_ms(f"{DIA_FIXTURE} 12:00:00")], HORA)
    assert len(alinhado) == 1
    assert pd.isna(alinhado["sum_open_interest"].iloc[0])


# ============================ o portao de paridade ============================
def test_lookback_acima_do_teto_e_recusado():
    """[Q-17 §4] O portao de verdade do card. O bot ao vivo so enxerga 30 dias pelo REST
    (medido: -30d responde, -31d devolve HTTP 400), entao feature com janela longa
    backtesta e nao roda."""
    assert dd.exigir_lookback_valido(dd.LOOKBACK_MAX_DIAS) == dd.LOOKBACK_MAX_DIAS
    with pytest.raises(ValueError, match="paridade"):
        dd.exigir_lookback_valido(dd.LOOKBACK_MAX_DIAS + 1)
    with pytest.raises(ValueError, match="paridade"):
        dd.exigir_lookback_valido(365)
    with pytest.raises(ValueError):
        dd.exigir_lookback_valido(0)


def test_teto_de_lookback_tem_folga_dentro_da_parede_de_30_dias():
    """14 e nao 29: o dump e D+1 e o REST cai, entao o teto precisa do DOBRO de folga
    dentro da parede medida de 30 dias."""
    assert dd.LOOKBACK_MAX_DIAS * 2 <= 30


def test_so_o_que_reconcilia_esta_liberado_para_virar_feature():
    """[Q-17 §4.2] A lista nao e opiniao: sai da matriz de reconciliacao medida. Promover
    uma coluna daqui exige refazer a medicao, e este teste e onde isso e cobrado."""
    assert dd.COLUNAS_RECONCILIADAS == ("sum_open_interest",
                                        "sum_toptrader_long_short_ratio")
    assert dd.COLUNAS["sum_open_interest"]["tol"] == 0.0, "o OI casa EXATO, 287/287"
    for col in ("count_toptrader_long_short_ratio", "count_long_short_ratio",
                "sum_taker_long_short_vol_ratio"):
        assert dd.COLUNAS[col]["reconcilia"] is False
        assert dd.COLUNAS[col]["tol"] is None


def test_o_taker_e_fluxo_e_por_isso_tem_deslocamento_proprio():
    """As quatro primeiras colunas sao ESTOQUE (foto no fim do bucket) e a ultima e FLUXO
    (soma dentro dele). O modulo tem de saber a diferenca -- ela foi medida."""
    assert dd.COLUNAS["sum_taker_long_short_vol_ratio"]["rest"][0] == "takerlongshortRatio"
    assert dd.COLUNAS["sum_open_interest"]["rest"][0] == "openInterestHist"


# ============================ cache e simbolo ============================
def test_par_vira_simbolo_do_contrato():
    assert dd.par_para_simbolo("ETH/USDT") == "ETHUSDT"
    assert dd.par_para_simbolo("BTC/USDT") == "BTCUSDT"


def test_dia_historico_e_imutavel_e_o_dia_de_ontem_nao(monkeypatch):
    """O cache so pode ser eterno para o que nao muda mais. O dump e D+1, entao os dois
    ultimos dias continuam volateis -- e e por isso que a chave nao carrega a data de hoje,
    ao contrario do `dados.baixar_ohlcv`."""
    import datetime
    hoje = datetime.date(2026, 8, 25)
    assert dd._volatil("2026-08-25", hoje) is True
    assert dd._volatil("2026-08-24", hoje) is True
    assert dd._volatil("2026-08-23", hoje) is False
    assert dd._volatil(DIA_FIXTURE, hoje) is False


def test_cache_evita_a_rede_no_segundo_acesso(tmp_path, monkeypatch):
    """Prova que os ~13.100 downloads da janela da regua acontecem UMA vez: com o arquivo
    ja em cache, `baixar_dia` nao pode chamar a rede. `_baixar` vira uma bomba."""
    monkeypatch.setattr(dd, "CACHE_DIR", str(tmp_path))
    alvo = dd.caminho_cache("ETHUSDT", DIA_FIXTURE)
    os.makedirs(os.path.dirname(alvo), exist_ok=True)
    with io.open(CSV_FIXTURE, encoding="utf-8") as f:
        conteudo = f.read()
    with io.open(alvo, "w", encoding="utf-8", newline="") as f:
        f.write(conteudo)

    def _bomba(*a, **k):
        raise AssertionError("tocou a rede com o dia ja em cache")

    monkeypatch.setattr(dd, "_baixar", _bomba)
    assert dd.baixar_dia("ETHUSDT", DIA_FIXTURE) == conteudo


def test_dia_inexistente_no_dump_devolve_none(tmp_path, monkeypatch):
    """Moeda que ainda nao listava naquele dia da 404 -- e 404 e ausencia, nao falha."""
    import urllib.error
    monkeypatch.setattr(dd, "CACHE_DIR", str(tmp_path))

    def _404(*a, **k):
        raise urllib.error.HTTPError("u", 404, "Not Found", None, None)

    monkeypatch.setattr(dd, "_baixar", _404)
    assert dd.baixar_dia("ETHUSDT", "2015-01-01") is None


# ============================ reconciliacao de verdade (rede) ============================
@pytest.mark.rede
@pytest.mark.skipif(not os.environ.get("CRIPTO_TESTE_REDE"),
                    reason="precisa de rede; ligue com CRIPTO_TESTE_REDE=1")
def test_reconciliacao_dump_x_rest():
    """[Q-17 §4.2] O teste de PARIDADE. Backfill e vivo sao dois caminhos de codigo para o
    mesmo numero; sem esta prova, o backtest mede uma serie e a producao mede outra.

    Roda contra um dia que esta nos DOIS lados (dentro dos 30 dias do REST e ja fechado no
    dump). O `sum_open_interest` tem de casar EXATO -- foi assim em 3 moedas e 3 dias.
    """
    import datetime
    dia = (datetime.datetime.now(datetime.timezone.utc).date()
           - datetime.timedelta(days=10)).isoformat()
    placar = dd.reconciliar("ETH/USDT", dia, colunas=dd.COLUNAS_RECONCILIADAS)

    oi = placar["sum_open_interest"]
    assert oi["comparados"] >= 280, f"poucos buckets comparados: {oi}"
    assert oi["iguais"] == oi["comparados"], f"o open interest deixou de casar exato: {oi}"

    top = placar["sum_toptrader_long_short_ratio"]
    assert top["iguais"] >= 0.95 * top["comparados"], f"fora do arredondamento: {top}"
