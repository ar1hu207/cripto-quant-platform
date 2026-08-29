# -*- coding: utf-8 -*-
"""
Baixador dos dumps publicos do `data.binance.vision` -- [N-1], [N-2], [N-3].

Rodar (da RAIZ do repo):  python -m pesquisa.dados_bulk

**O que este modulo e, e por que ele existe ao lado do `pesquisa/dados.py`.**
O `dados.py` fala com o REST da exchange via ccxt. O REST tem um muro que o `NORTE.md`
registra: serve ~30 dias de open interest e long/short ratio, e com serie curta a regua
devolve INCONCLUSIVO por falta de PODER, nao por falta de sinal. Este modulo existe porque
**esse muro e do REST, nao do bucket**: o `data.binance.vision` serve o mesmo dado desde
2020-09, de graca e sem chave de API. Os dois convivem; nenhum substitui o outro.

O que ele destrava:

* **[N-1]** `metrics`: open interest, os tres long/short ratios e o taker ratio em
  granularidade de 5 min desde 2020-09-01.
* **[N-2]** `taker_buy_volume` ja vem dentro dos klines. Permite backtestar o portao de
  fluxo do bot em ANOS, contra os 10 dias que produziram o p=0,58.
* **[N-3]** pares deslistados continuam no bucket. Baixa-los e o que mata o vies de
  sobrevivencia que o `PLANO-REPOS-QUANT.md` §5.4 registrou em julho e ninguem corrigiu.

--------------------------------------------------------------------------------------
AS QUATRO ARMADILHAS DESTE BUCKET -- todas MEDIDAS, nenhuma suposta
--------------------------------------------------------------------------------------

1. **O `metrics` vem fora de ordem cronologica.** Nao e teoria: `BTCUSDT-metrics-2024-08-08`
   tem **74 quebras de ordem**, comeca em 00:35 e termina em 23:45. Um backtest que confia
   na ordem do arquivo le o futuro -- literalmente, porque a linha seguinte pode ser mais
   antiga que a atual. `normalizar_metrics` ORDENA, e o `__main__` prova nesse dia.

2. **O `metrics` tem linhas duplicadas.** Tambem medido: `BTCUSDT-metrics-2020-09-01` traz
   576 linhas para 288 timestamps -- cada linha aparece DUAS vezes. Duplicata silenciosa
   dobra o peso de um instante em qualquer media ou regressao. `normalizar_metrics`
   deduplica por timestamp.

3. **O header dos klines e inconsistente entre meses.** Em `futures/um` os arquivos ate
   **2021-12** vem SEM linha de cabecalho e a partir de **2022-01** vem COM. Sem tratar,
   a primeira barra de cada mes antigo vira o nome das colunas, ou o cabecalho vira uma
   barra de precos absurdos.

4. **Os klines de `spot` trocaram a UNIDADE do timestamp em 2025-01, de milissegundo para
   MICROssegundo.** Esta nao estava no briefing e e a pior das quatro, porque nada a
   sinaliza: mesmo numero de colunas (12), sem header dos dois lados. `unit="ms"` aplicado
   a um arquivo de 2025 devolve datas no ano ~57000 -- sem excecao, sem aviso. Por isso a
   unidade aqui e **detectada pela grandeza do numero** (`_unidade_epoch`), nunca fixada.
   `futures/um` seguiu em milissegundo; ou seja, cada mercado tem a SUA inconsistencia, e
   elas nao coincidem.

--------------------------------------------------------------------------------------
DECISOES QUE NAO SE DEDUZEM DO CODIGO
--------------------------------------------------------------------------------------

* **Timestamps naive, em UTC de exchange** -- exatamente como o `pesquisa/dados.py` faz
  (`pd.to_datetime(..., unit="ms")`, sem fuso). O `CLAUDE.md` §1 fala de hora de Sao Paulo
  para o BANCO da plataforma; a pesquisa consome candle de exchange e o modulo irmao ja
  fixou essa convencao. Divergir aqui criaria duas escalas de tempo dentro do MESMO pacote,
  que e pior que qualquer uma das duas.

* **O cache guarda o .zip cru, e o nome NAO leva a data do download.** O `dados.py` poe a
  data no nome porque a janela do REST anda todo dia. Aqui e o contrario: dump de mes ou
  dia fechado e imutavel depois de publicado, entao carimbar a data do download quebraria
  o cache de graca e baixaria de novo o mesmo byte.

* **`baixar_*` NAO explode quando falta periodo** -- devolve o que existe e lista o que
  faltou em `df.attrs["ausentes"]`. Nao e leniencia: para o [N-3] o par deslistado
  PARAR de ter arquivo e o dado, nao o erro. `LUNAUSDT` em `futures/um` termina em 2022-05,
  e e disso que o vies de sobrevivencia e feito. Quem precisa de serie fechada passa
  `exigir_completo=True`.

* **Este modulo constroi o baixador; ele nao baixa o acervo.** Tudo e parametrizado por
  simbolo/mercado/intervalo/periodo, e a prova do `__main__` roda num recorte pequeno
  (poucos arquivos, ~centenas de KB). Baixar historico completo e decisao de quem for
  rodar a pesquisa, nao efeito colateral de importar isto.
"""
import hashlib
import io
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import pandas as pd

BASE = "https://data.binance.vision"

# Listagem do bucket (S3 puro). Serve para descobrir o que existe sem contar 404 -- e o
# que o [N-3] precisa para achar a data de morte de um par.
LISTAGEM = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_cache", "bulk")

# Prefixo de cada mercado dentro do bucket. `futures_um` = USD-M perpetuo, que e o que a
# plataforma opera; `spot` entra porque tem historico mais longo (BTCUSDT desde 2017-08).
MERCADOS = {
    "futures_um": "futures/um",
    "futures_cm": "futures/cm",
    "spot": "spot",
}

# As 12 colunas do kline, na ordem em que o bucket as escreve. `taker_buy_volume` -- a
# coluna que o [N-2] persegue -- e a decima.
COLUNAS_KLINES = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "count",
    "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]

# Sem estas o arquivo nao serve para nada que este modulo promete, e falhar alto e melhor
# que devolver NaN que so aparece 200 linhas depois, dentro do backtest.
ESSENCIAIS_KLINES = ["open_time", "open", "high", "low", "close", "volume", "taker_buy_volume"]

COLUNAS_METRICS = [
    "create_time", "symbol",
    "sum_open_interest", "sum_open_interest_value",
    "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
    "count_long_short_ratio", "sum_taker_long_short_vol_ratio",
]

ESSENCIAIS_METRICS = [
    "create_time",
    "sum_open_interest",
    "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
    "count_long_short_ratio", "sum_taker_long_short_vol_ratio",
]

# Nomes que ja apareceram no header do bucket para a mesma coluna.
ALIAS_KLINES = {
    "opentime": "open_time", "closetime": "close_time",
    "quote_asset_volume": "quote_volume",
    "number_of_trades": "count", "trades": "count",
    "taker_buy_base_asset_volume": "taker_buy_volume",
    "taker_buy_quote_asset_volume": "taker_buy_quote_volume",
}


# ------------------------------------------------------------------ chaves do bucket

def _mercado(mercado):
    if mercado not in MERCADOS:
        raise ValueError(f"mercado {mercado!r} desconhecido; use um de {sorted(MERCADOS)}")
    return MERCADOS[mercado]


def chave_klines(simbolo, intervalo="1h", periodo="2024-01", mercado="futures_um"):
    """Chave do dump MENSAL de klines. `periodo` = 'YYYY-MM'."""
    m = _mercado(mercado)
    return f"data/{m}/monthly/klines/{simbolo}/{intervalo}/{simbolo}-{intervalo}-{periodo}.zip"


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
    confira o hash) -- um zip truncado por rede ruim vira um mes de dado faltando no meio
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
    """True se a primeira linha e header. Armadilha 3.

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
    """Descobre se um epoch inteiro esta em s, ms, us ou ns. Armadilha 4.

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


def normalizar_klines(texto):
    """CSV cru de klines -> DataFrame com as 12 colunas canonicas + `datetime`.

    Trata as armadilhas 3 (header presente ou nao) e 4 (unidade do timestamp), e devolve
    SEMPRE o mesmo conjunto de colunas, venha o arquivo de 2020 ou de 2026.
    """
    if not texto.strip():
        raise ValueError("CSV de klines vazio")

    tem_header = _tem_cabecalho(texto)
    df = pd.read_csv(io.StringIO(texto), header=0 if tem_header else None)

    if tem_header:
        nomes = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        df.columns = [ALIAS_KLINES.get(n, n) for n in nomes]
    else:
        # Sem header a unica informacao e a POSICAO. O bucket escreve na ordem canonica.
        n = df.shape[1]
        if n > len(COLUNAS_KLINES):
            raise ValueError(
                f"kline sem header com {n} colunas; canonicas sao {len(COLUNAS_KLINES)}")
        df.columns = COLUNAS_KLINES[:n]

    faltando = [c for c in ESSENCIAIS_KLINES if c not in df.columns]
    if faltando:
        raise ValueError(f"kline sem colunas essenciais {faltando}; veio {list(df.columns)}")

    for c in COLUNAS_KLINES:
        if c not in df.columns:
            df[c] = pd.NA                      # "ignore" sumindo nao invalida o arquivo
    df = df[COLUNAS_KLINES].copy()

    for c in COLUNAS_KLINES:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["datetime"] = _para_datetime(df["open_time"])
    df = df.dropna(subset=["datetime"])
    return _ordenar_unico(df, "datetime")


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

def meses(inicio, fim):
    """['2024-01', '2024-02', ...] inclusive nas duas pontas."""
    return [d.strftime("%Y-%m")
            for d in pd.date_range(f"{inicio}-01", f"{fim}-01", freq="MS")]


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


def baixar_klines(simbolo="BTCUSDT", intervalo="1h", inicio="2024-01", fim="2024-02",
                  mercado="futures_um", usar_cache=True, exigir_completo=False):
    """[N-2][N-3] Klines mensais concatenados, normalizados e ordenados.

    Traz `taker_buy_volume` de graca -- e o [N-2]: o portao de fluxo do bot passa a ser
    backtestavel em anos. Mes ausente nao interrompe: vai para `df.attrs["ausentes"]`,
    porque par deslistado simplesmente PARA de ter arquivo ([N-3]).
    """
    partes, ausentes = [], []
    for periodo in meses(inicio, fim):
        bruto = baixar_zip(chave_klines(simbolo, intervalo, periodo, mercado), usar_cache)
        if bruto is None:
            ausentes.append(periodo)
            continue
        partes.append(normalizar_klines(texto_do_zip(bruto)))
    if exigir_completo and ausentes:
        raise RuntimeError(f"{simbolo}: meses ausentes {ausentes}")
    return _juntar(partes, ausentes)


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


def listar_periodos(simbolo="LUNAUSDT", intervalo="1h", mercado="futures_um"):
    """[N-3] Meses que o bucket TEM para um par -- inclusive par que ja morreu.

    E a consulta que torna o vies de sobrevivencia visivel: o ultimo mes devolvido aqui e
    a data de morte do par. Sem isso a unica forma de saber e pedir mes a mes e contar 404.
    """
    prefixo = f"data/{_mercado(mercado)}/monthly/klines/{simbolo}/{intervalo}/"
    url = f"{LISTAGEM}?prefix={urllib.parse.quote(prefixo)}&max-keys=1000"
    xml = _http(url)
    if not xml:
        return []
    chaves = re.findall(r"<Key>([^<]+)</Key>", xml.decode())
    marca = f"-{intervalo}-"
    return sorted({k.rsplit(marca, 1)[-1][:-4] for k in chaves if k.endswith(".zip")})


# ------------------------------------------------------------------ prova de rede

if __name__ == "__main__":
    print("PROVA DE REDE -- pesquisa/dados_bulk.py  ([N-1] [N-2] [N-3])")
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

    # ---- [N-2] klines: duas epocas, mesmas colunas, taker_buy_volume ----------------
    print("\n[N-2] klines de DUAS EPOCAS normalizam para o mesmo conjunto de colunas")
    a = baixar_klines("BTCUSDT", "1h", "2020-09", "2020-09")      # SEM header no arquivo
    b = baixar_klines("BTCUSDT", "1h", "2025-06", "2025-06")      # COM header no arquivo
    assert list(a.columns) == list(b.columns), "as duas epocas divergiram nas colunas"
    assert "taker_buy_volume" in a.columns and "taker_buy_volume" in b.columns
    assert a["taker_buy_volume"].notna().all() and b["taker_buy_volume"].notna().all()
    assert estritamente_crescente(a["datetime"]) and estritamente_crescente(b["datetime"])
    assert a["datetime"].iloc[0].year == 2020 and b["datetime"].iloc[0].year == 2025
    print(f"      2020-09 (arquivo SEM header): {len(a):4d} barras | "
          f"{a['datetime'].iloc[0]} -> {a['datetime'].iloc[-1]}")
    print(f"      2025-06 (arquivo COM header): {len(b):4d} barras | "
          f"{b['datetime'].iloc[0]} -> {b['datetime'].iloc[-1]}")
    print(f"      colunas identicas: {list(a.columns)}")
    print(f"      taker_buy_volume medio: 2020-09={a['taker_buy_volume'].mean():.2f}"
          f"  2025-06={b['taker_buy_volume'].mean():.2f}")

    # ---- armadilha 4: a unidade do timestamp no spot --------------------------------
    print("\n[armadilha 4] spot trocou ms -> MICROssegundo em 2025-01, sem header e sem aviso")
    s1 = baixar_klines("BTCUSDT", "1h", "2024-12", "2024-12", mercado="spot")
    s2 = baixar_klines("BTCUSDT", "1h", "2025-01", "2025-01", mercado="spot")
    assert s1["datetime"].iloc[0].year == 2024 and s2["datetime"].iloc[0].year == 2025, \
        "a deteccao de unidade falhou -- e o erro sairia como ano ~57000, calado"
    print(f"      2024-12 open_time cru={int(s1['open_time'].iloc[0])} "
          f"-> {s1['datetime'].iloc[0]}")
    print(f"      2025-01 open_time cru={int(s2['open_time'].iloc[0])} "
          f"-> {s2['datetime'].iloc[0]}")
    print(f"      com unit='ms' fixo, 2025-01 daria: "
          f"{pd.to_datetime(int(s2['open_time'].iloc[0]), unit='ms')}")

    # ---- [N-3] par deslistado -------------------------------------------------------
    print("\n[N-3] par DESLISTADO ainda baixa -- e a morte dele fica visivel")
    disponiveis = listar_periodos("LUNAUSDT", "1h", "futures_um")
    assert disponiveis, "LUNAUSDT nao tem nenhum mes em futures/um"
    ultimo = disponiveis[-1]
    luna = baixar_klines("LUNAUSDT", "1h", ultimo, ultimo, mercado="futures_um")
    assert len(luna) > 0, "o ultimo mes de LUNAUSDT veio vazio"
    assert "taker_buy_volume" in luna.columns
    depois_da_morte = baixar_klines("LUNAUSDT", "1h", "2026-01", "2026-01",
                                    mercado="futures_um")
    assert depois_da_morte.attrs["ausentes"] == ["2026-01"], \
        "2026-01 deveria estar ausente para um par que morreu em 2022"
    assert len(depois_da_morte) == 0
    print(f"      LUNAUSDT futures/um: {len(disponiveis)} meses, "
          f"{disponiveis[0]} -> {ultimo}")
    print(f"      ultimo mes ({ultimo}): {len(luna)} barras | "
          f"{luna['datetime'].iloc[0]} -> {luna['datetime'].iloc[-1]}")
    print(f"      2026-01 ausente={depois_da_morte.attrs['ausentes']}  "
          f"<- o par morreu; BTCUSDT nao morreu, e e so ele que a pesquisa backtesta hoje")

    print("\nTODAS AS AFIRMACOES PASSARAM.")
    print(f"cache em: {CACHE_DIR}")
