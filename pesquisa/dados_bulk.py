# -*- coding: utf-8 -*-
"""
Baixador dos dumps publicos do `data.binance.vision` -- [N-1].

Rodar (da RAIZ do repo):  python -m pesquisa.dados_bulk

**O que este modulo e, e por que ele existe ao lado do `pesquisa/dados.py`.**
O `dados.py` fala com o REST da exchange via ccxt. O REST tem um muro que o `NORTE.md`
registra: serve ~30 dias de open interest e long/short ratio, e com serie curta a regua
devolve INCONCLUSIVO por falta de PODER, nao por falta de sinal. Este modulo existe porque
**esse muro e do REST, nao do bucket**: o `data.binance.vision` serve o mesmo dado desde
2020-09, de graca e sem chave de API. Os dois convivem; nenhum substitui o outro.

**[N-1]** `metrics`: open interest, os tres long/short ratios e o taker ratio em
granularidade de 5 min desde 2020-09-01.

--------------------------------------------------------------------------------------
AS DUAS ARMADILHAS DO `metrics` -- ambas MEDIDAS, nenhuma suposta
--------------------------------------------------------------------------------------

1. **O `metrics` vem fora de ordem cronologica.** Nao e teoria: `BTCUSDT-metrics-2024-08-08`
   tem **74 quebras de ordem**, comeca em 00:35 e termina em 23:45. Um backtest que confia
   na ordem do arquivo le o futuro -- literalmente, porque a linha seguinte pode ser mais
   antiga que a atual. `normalizar_metrics` ORDENA, e o `__main__` prova nesse dia.

2. **O `metrics` tem linhas duplicadas.** Tambem medido: `BTCUSDT-metrics-2020-09-01` traz
   576 linhas para 288 timestamps -- cada linha aparece DUAS vezes. Duplicata silenciosa
   dobra o peso de um instante em qualquer media ou regressao. `normalizar_metrics`
   deduplica por timestamp.

--------------------------------------------------------------------------------------
DECISOES QUE NAO SE DEDUZEM DO CODIGO
--------------------------------------------------------------------------------------

* **Timestamps naive, em UTC de exchange** -- exatamente como o `pesquisa/dados.py` faz
  (`pd.to_datetime(..., unit="ms")`, sem fuso). O `CLAUDE.md` §1 fala de hora de Sao Paulo
  para o BANCO da plataforma; a pesquisa consome dado de exchange e o modulo irmao ja
  fixou essa convencao. Divergir aqui criaria duas escalas de tempo dentro do MESMO pacote,
  que e pior que qualquer uma das duas.

* **O cache guarda o .zip cru, e o nome NAO leva a data do download.** O `dados.py` poe a
  data no nome porque a janela do REST anda todo dia. Aqui e o contrario: dump de dia
  fechado e imutavel depois de publicado, entao carimbar a data do download quebraria o
  cache de graca e baixaria de novo o mesmo byte.

* **`baixar_metrics` NAO explode quando falta periodo** -- devolve o que existe e lista o
  que faltou em `df.attrs["ausentes"]`. Buraco no historico e um fato do bucket, e quem
  precisa de serie fechada passa `exigir_completo=True`.

* **Este modulo constroi o baixador; ele nao baixa o acervo.** Tudo e parametrizado por
  simbolo e periodo, e a prova do `__main__` roda num recorte pequeno (poucos arquivos,
  ~dezenas de KB). Baixar historico completo e decisao de quem for rodar a pesquisa, nao
  efeito colateral de importar isto.
"""
import hashlib
import io
import os
import time
import urllib.error
import urllib.request
import zipfile

import pandas as pd

BASE = "https://data.binance.vision"

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_cache", "bulk")

COLUNAS_METRICS = [
    "create_time", "symbol",
    "sum_open_interest", "sum_open_interest_value",
    "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
    "count_long_short_ratio", "sum_taker_long_short_vol_ratio",
]

# Sem estas o arquivo nao serve para nada que este modulo promete, e falhar alto e melhor
# que devolver NaN que so aparece 200 linhas depois, dentro do backtest.
ESSENCIAIS_METRICS = [
    "create_time",
    "sum_open_interest",
    "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
    "count_long_short_ratio", "sum_taker_long_short_vol_ratio",
]


# ------------------------------------------------------------------ chaves do bucket

def chave_metrics(simbolo, dia="2024-01-15"):
    """Chave do dump de `metrics`. `dia` = 'YYYY-MM-DD'.

    **O `metrics` so existe em granularidade DIARIA.** O caminho mensal
    (`data/futures/um/monthly/metrics/...`) devolve 404 -- conferido, e a listagem do
    bucket confirma: `monthly/` nao tem a pasta `metrics`, so `daily/` tem. Quem escreveu
    "dump mensal de metrics" supos a simetria com os klines, e ela nao existe.
    """
    return f"data/futures/um/daily/metrics/{simbolo}/{simbolo}-metrics-{dia}.zip"


# ------------------------------------------------------------------ rede e cache

def _http(url, tentativas=3, timeout=60):
    """GET com retry. Devolve bytes, ou None em 404 (periodo que nao existe)."""
    ultimo = None
    for n in range(tentativas):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None            # ausencia e resposta, nao falha
            ultimo = e
        except Exception as e:         # rede instavel: tenta de novo antes de desistir
            ultimo = e
        time.sleep(1.5 * (n + 1))
    raise RuntimeError(f"falhou baixar {url}: {ultimo}")


def baixar_zip(chave, usar_cache=True, verificar_hash=True):
    """Baixa (ou le do cache) o .zip de uma chave do bucket. None se a chave nao existe.

    `verificar_hash` confere o sha256 contra o `.zip.CHECKSUM` que o proprio bucket
    publica ao lado de cada arquivo. E barato e e o padrao da casa (`CLAUDE.md` §7:
    confira o hash) -- um zip truncado por rede ruim vira um dia de dado faltando no meio
    do backtest, e nada avisa.
    """
    destino = os.path.join(CACHE_DIR, chave.replace("/", os.sep))
    if usar_cache and os.path.exists(destino):
        with open(destino, "rb") as f:
            return f.read()

    conteudo = _http(f"{BASE}/{chave}")
    if conteudo is None:
        return None

    if verificar_hash:
        soma = _http(f"{BASE}/{chave}.CHECKSUM")
        if soma:
            esperado = soma.decode().split()[0].strip()
            obtido = hashlib.sha256(conteudo).hexdigest()
            if esperado != obtido:
                raise RuntimeError(f"sha256 nao bate em {chave}: {obtido} != {esperado}")

    if usar_cache:
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with open(destino, "wb") as f:
            f.write(conteudo)
    return conteudo


def texto_do_zip(conteudo):
    """Extrai o unico CSV de dentro do zip do bucket."""
    z = zipfile.ZipFile(io.BytesIO(conteudo))
    nomes = [n for n in z.namelist() if n.lower().endswith(".csv")]
    if len(nomes) != 1:
        raise ValueError(f"esperava 1 CSV no zip, achei {nomes}")
    return z.read(nomes[0]).decode("utf-8")


# ------------------------------------------------------------------ normalizacao

def _tem_cabecalho(texto):
    """True se a primeira linha e header.

    O teste e "o primeiro campo e um inteiro?". Nao se pergunta ao nome da coluna se ele
    esta numa lista conhecida: header novo com nome que a lista nao preve seria lido como
    dado, e uma coluna renomeada la na frente quebraria em silencio aqui atras.
    """
    primeira = texto.split("\n", 1)[0].strip()
    if not primeira:
        return False
    campo = primeira.split(",")[0].strip().strip('"')
    try:
        int(campo)
        return False
    except ValueError:
        return True


def _unidade_epoch(valor):
    """Descobre se um epoch inteiro esta em s, ms, us ou ns.

    Escolhe a unidade que poe o instante numa janela plausivel de mercado (2009-2100) --
    grandeza, nao contagem de digitos. Contar digitos e a mesma conta escrita de um jeito
    que passa a mentir na proxima ordem de magnitude; a janela diz o que se quer de fato,
    que e "isto e uma data de verdade".
    """
    v = abs(int(valor))
    for unidade, por_segundo in (("s", 1), ("ms", 10 ** 3), ("us", 10 ** 6), ("ns", 10 ** 9)):
        segundos = v / por_segundo
        if 1_230_768_000 <= segundos <= 4_102_444_800:   # 2009-01-01 .. 2100-01-01
            return unidade
    raise ValueError(f"epoch {valor!r} nao cai em nenhuma unidade plausivel (s/ms/us/ns)")


def _para_datetime(serie):
    """Serie de epoch (qualquer unidade) ou de texto -> datetime64 naive."""
    if pd.api.types.is_numeric_dtype(serie):
        limpa = serie.dropna()
        if limpa.empty:
            raise ValueError("coluna de tempo vazia")
        return pd.to_datetime(serie, unit=_unidade_epoch(limpa.iloc[0]))
    return pd.to_datetime(serie, format="mixed")


def _ordenar_unico(df, coluna):
    """Ordena por `coluna` e remove timestamp repetido. Armadilhas 1 e 2.

    Ordena SEMPRE, mesmo quando o arquivo parece ordenado: "parece" e uma leitura da
    primeira e da ultima linha, e o 2024-08-08 tem 74 quebras no meio com as pontas quase
    certas. E deduplica DEPOIS de ordenar, com `keep="first"`, para que a linha mantida
    nao dependa da ordem em que o bucket resolveu escrever.
    """
    df = df.sort_values(coluna, kind="mergesort")     # estavel: empate mantem a ordem do arquivo
    df = df[~df[coluna].duplicated(keep="first")]
    return df.reset_index(drop=True)


def normalizar_metrics(texto):
    """CSV cru de `metrics` -> DataFrame ordenado, sem timestamp repetido, + `datetime`.

    Trata as armadilhas 1 (fora de ordem) e 2 (duplicatas). O indice temporal que sai
    daqui e ESTRITAMENTE crescente, e e isso que o `__main__` afirma com assert.
    """
    if not texto.strip():
        raise ValueError("CSV de metrics vazio")

    tem_header = _tem_cabecalho(texto)
    df = pd.read_csv(io.StringIO(texto), header=0 if tem_header else None)
    if tem_header:
        df.columns = [str(c).strip().lower() for c in df.columns]
    else:
        n = df.shape[1]
        if n > len(COLUNAS_METRICS):
            raise ValueError(
                f"metrics sem header com {n} colunas; canonicas sao {len(COLUNAS_METRICS)}")
        df.columns = COLUNAS_METRICS[:n]

    faltando = [c for c in ESSENCIAIS_METRICS if c not in df.columns]
    if faltando:
        raise ValueError(f"metrics sem colunas essenciais {faltando}; veio {list(df.columns)}")

    df = df.copy()
    for c in df.columns:
        if c not in ("create_time", "symbol"):
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df["datetime"] = _para_datetime(df["create_time"])
    df = df.dropna(subset=["datetime"])
    return _ordenar_unico(df, "datetime")


def estritamente_crescente(serie):
    """O predicado que as armadilhas 1 e 2 violam juntas: ordenado E sem repeticao."""
    return bool(serie.is_monotonic_increasing) and not bool(serie.duplicated().any())


# ------------------------------------------------------------------ periodos

def dias(inicio, fim):
    """['2024-01-15', '2024-01-16', ...] inclusive nas duas pontas."""
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(inicio, fim, freq="D")]


# ------------------------------------------------------------------ os baixadores

def _juntar(partes, ausentes, coluna="datetime"):
    if not partes:
        df = pd.DataFrame(columns=[coluna])
    else:
        df = _ordenar_unico(pd.concat(partes, ignore_index=True), coluna)
    df.attrs["ausentes"] = ausentes
    return df


def baixar_metrics(simbolo="BTCUSDT", inicio="2024-01-15", fim="2024-01-16",
                   usar_cache=True, exigir_completo=False):
    """[N-1] `metrics` diario concatenado: OI, os 3 long/short ratios e o taker ratio, 5 min.

    E o item que derruba o muro do `NORTE.md` -- que valia para o REST (~30 dias), nao
    para o bucket (desde 2020-09-01).
    """
    partes, ausentes = [], []
    for dia in dias(inicio, fim):
        bruto = baixar_zip(chave_metrics(simbolo, dia), usar_cache)
        if bruto is None:
            ausentes.append(dia)
            continue
        partes.append(normalizar_metrics(texto_do_zip(bruto)))
    if exigir_completo and ausentes:
        raise RuntimeError(f"{simbolo}: dias ausentes {ausentes}")
    return _juntar(partes, ausentes)


# ------------------------------------------------------------------ prova de rede

if __name__ == "__main__":
    print("PROVA DE REDE -- pesquisa/dados_bulk.py  ([N-1])")
    print("Recorte pequeno de proposito: o modulo e o baixador, nao o acervo.\n")

    # ---- [N-1] metrics: as colunas prometidas existem -------------------------------
    print("[N-1] metrics BTCUSDT 2024-01-15 (o dump so existe em granularidade DIARIA)")
    m = baixar_metrics("BTCUSDT", "2024-01-15", "2024-01-15")
    for coluna in ("sum_open_interest",
                   "count_toptrader_long_short_ratio",
                   "sum_toptrader_long_short_ratio",
                   "count_long_short_ratio",
                   "sum_taker_long_short_vol_ratio"):
        assert coluna in m.columns, f"faltou {coluna}"
    assert len(m) == 288, f"esperava 288 barras de 5 min, vieram {len(m)}"
    assert estritamente_crescente(m["datetime"])
    print(f"      OK  {len(m)} barras de 5 min | "
          f"{m['datetime'].iloc[0]} -> {m['datetime'].iloc[-1]}")
    print(f"      OI + os 3 ratios + taker ratio: "
          f"{[c for c in m.columns if 'ratio' in c or 'interest' in c]}")

    # ---- armadilha 1: fora de ordem -------------------------------------------------
    print("\n[armadilha 1] 2024-08-08 vem FORA DE ORDEM dentro do arquivo")
    cru = texto_do_zip(baixar_zip(chave_metrics("BTCUSDT", "2024-08-08")))
    antes = pd.to_datetime(pd.read_csv(io.StringIO(cru))["create_time"])
    quebras = int((antes.diff().dropna() < pd.Timedelta(0)).sum())
    depois = normalizar_metrics(cru)
    assert quebras > 0, "o arquivo de controle deixou de estar fora de ordem"
    assert estritamente_crescente(depois["datetime"]), "nao ficou estritamente crescente"
    print(f"      cru..... monotonico={antes.is_monotonic_increasing}  "
          f"quebras de ordem={quebras}  ({antes.iloc[0]} -> {antes.iloc[-1]})")
    print(f"      tratado. estritamente crescente="
          f"{estritamente_crescente(depois['datetime'])}  "
          f"({depois['datetime'].iloc[0]} -> {depois['datetime'].iloc[-1]})")

    # ---- armadilha 2: duplicatas ----------------------------------------------------
    print("\n[armadilha 2] 2020-09-01 vem com TODA linha duplicada")
    cru2 = texto_do_zip(baixar_zip(chave_metrics("BTCUSDT", "2020-09-01")))
    n_cru = len(pd.read_csv(io.StringIO(cru2)))
    tratado2 = normalizar_metrics(cru2)
    assert n_cru == 2 * len(tratado2), f"esperava dobra exata, vi {n_cru} -> {len(tratado2)}"
    assert estritamente_crescente(tratado2["datetime"])
    print(f"      cru {n_cru} linhas -> tratado {len(tratado2)} | "
          f"estritamente crescente={estritamente_crescente(tratado2['datetime'])}")

    print("\nTODAS AS AFIRMACOES PASSARAM.")
    print(f"cache em: {CACHE_DIR}")
