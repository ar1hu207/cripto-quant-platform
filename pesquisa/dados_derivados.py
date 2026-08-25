"""
[Q-17] Pedra 2 - Dados de POSICIONAMENTO (o que esta fora do candle).

Open interest e razoes long/short da Binance USD-M, alinhados na grade da regua.
GRATIS, sem chave de API, como o `pesquisa/dados.py` que baixa OHLCV.

Rodar (da RAIZ do repo):  python -m pesquisa.dados_derivados

---
**O que este modulo NAO faz, e e deliberado.** Ele nao decide nada, nao entra no
`scoring`, nao emite veredito e nao consome uma unidade de `n_trials`. E o baixador da
Fase 1 do `PLANO-Q17-INFORMACAO-2026-08-25.md`; a hipotese e a regua vem depois, e so
depois de o dono aprovar o orcamento compartilhado da §5 daquele plano.

---
**De onde vem o dado, e por que nao e do REST.**

O REST `futures/data/*` (openInterestHist, topLongShortAccountRatio, ...) tem uma parede
de **30 dias**, medida em 2026-08-25: `startTime` de -30d devolve 24 linhas, e -31d
devolve HTTP 400. Com 30 dias o MDS da regua e 8,673 -- o instrumento nao responde nada.

Os **dumps diarios** de `data.binance.vision` servem os MESMOS numeros, de 5 em 5 minutos,
sem essa parede: as 12 moedas da regua tem cobertura contigua de 2021-12-01 ate ontem,
**zero lacunas**, ~243 MB comprimidos. Com isso o T da regua continua 1095 e o MDS
continua 1,436, abaixo do `MDS_LIMITE = 2,0`.

Nao existe dump MENSAL de `metrics` (so `aggTrades`, `bookTicker`, `fundingRate`,
`*Klines` e `trades` tem mensal). Entao sao zips diarios mesmo: ~13.100 requisicoes para
cobrir 12 moedas x 1095 dias. Ver `CACHE_DIR` abaixo -- elas acontecem uma vez so.
"""
import concurrent.futures
import datetime
import io
import os
import time
import urllib.error
import urllib.request
import zipfile

import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_cache", "metricas")

BASE_DUMP = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
BASE_REST = "https://fapi.binance.com"

MIN_MS = 60_000
BUCKET_MS = 5 * MIN_MS                      # o dump e carimbado de 5 em 5 minutos
DIA_MS = 24 * 60 * MIN_MS

# ============================ a regra de ponto-no-tempo ============================
# [Q-17 §4.1] O NUMERO MAIS IMPORTANTE DESTE ARQUIVO. Nao mexa sem refazer a medicao.
#
# Duas medicoes, feitas em 2026-08-25 ANTES de este modulo existir, e que juntas fixam a
# constante abaixo:
#
# 1. **O dump e o REST nao usam o mesmo carimbo.** Deslocando o dump e comparando com o
#    REST, o erro relativo de `sum_open_interest` (ETHUSDT, 2026-08-15, 288 buckets):
#
#        shift -3 (-15 min): mediana 1,508e-04   max 1,273e-03
#        shift -2 (-10 min): mediana 7,827e-05   max 1,141e-03
#        shift -1 ( -5 min): mediana 0,000e+00   max 0,000e+00   <-- 287/287 IDENTICOS
#        shift  0 (  0 min): mediana 7,853e-05   max 1,142e-03
#        shift +1 ( +5 min): mediana 1,492e-04   max 1,274e-03
#
#    Idem em BTCUSDT (2026-08-22) e TRXUSDT (2026-08-03). Nao e ruido, e convencao:
#
#        dump[create_time = s]  ==  REST[timestamp = s + 5 min]
#
#    O dump carimba o bucket pelo INICIO; o REST, pelo FIM. Portanto a regra ingenua --
#    "usa o bucket cujo create_time e o fechamento da barra" -- entrega, numa barra que
#    fecha as 12:00, o open interest observado as 12:05. Cinco minutos de FUTURO, em toda
#    barra, em todo trade. Backtest lindo, vivo que nao repete.
#
# 2. **O REST publica com atraso.** As 18:26:11 UTC de 2026-08-25, a ultima linha servida
#    estava 1,2 min atras (topLongShortAccountRatio) a 6,2 min atras (os outros tres).
#    Ou seja o dado carimbado `t` so existe, de fato, em `t + ate ~6 min`.
#
# Somando: dump `s` vale `s+5min` e chega com ate ~6 min de atraso, logo so e observavel
# em `s + ~11 min`. Com folga ate o proximo bucket, `s + 15 min`. Dai:
#
#        valor_da_barra(T) = dump[T - 15 min]
#
# Quinze minutos de defasagem numa barra de 1h em troca de ZERO look-ahead. A assimetria
# justifica sozinha: o open interest anda ~0,1% em 5 min, entao a defasagem custa quase
# nada -- e o vazamento custa o veredito inteiro. Provado em `test_dados_derivados.py`.
ATRASO_OBSERVACAO_MS = 15 * MIN_MS

# [Q-17 §4] O TETO DE JANELA, e ele e o portao de verdade deste card.
#
# O backtest le 4,7 anos do dump. O bot ao vivo le 30 DIAS do REST. Uma feature do tipo
# "z-score do OI contra a media de 1 ano" backtesta lindamente e NAO PODE ser calculada em
# producao -- e a mesma quebra de paridade que o [Q-5] existiu para consertar.
#
# 14 e nao 29 porque o dump e D+1 e o REST tem indisponibilidade: 14 dias da o DOBRO de
# folga para um backfill atrasado dentro da parede de 30. Quem escrever feature aqui passa
# o lookback por `exigir_lookback_valido` e o teste cobra.
LOOKBACK_MAX_DIAS = 14

# ============================ as colunas ============================
# [Q-17 §4.2] O mapa de colunas foi CONFIRMADO por medicao (a diagonal e o minimo de toda
# linha da matriz coluna-do-dump x endpoint-do-REST), e a reconciliacao NAO e igual para
# todas. Isto aqui e a tabela do plano virada em dado:
#
#   coluna do dump                     endpoint REST                  shift  reconcilia?
#   sum_open_interest                  openInterestHist                 -1   EXATO 287/287
#   sum_toptrader_long_short_ratio     topLongShortPositionRatio        -1   dentro do arred. (285/287)
#   count_toptrader_long_short_ratio   topLongShortAccountRatio         -1   NAO (40/287)
#   count_long_short_ratio             globalLongShortAccountRatio      -1   NAO (28/287)
#   sum_taker_long_short_vol_ratio     takerlongshortRatio               0   NAO (dif. absoluta ate 6,80)
#
# O shift 0 do `taker` nao e erro: as quatro primeiras sao ESTOQUE (foto no fim do bucket)
# e a ultima e FLUXO (soma dentro do bucket). Uma regra unica aplicada as cinco erraria uma
# delas -- e a regra conservadora do `ATRASO_OBSERVACAO_MS` cobre as duas convencoes de uma
# vez, que e a razao de ela ser conservadora e nao exata.
COLUNAS = {
    "sum_open_interest": {
        "rest": ("openInterestHist", "sumOpenInterest"),
        "tol": 0.0,                                  # exato: 287/287 em 3 moedas e 3 dias
        "reconcilia": True,
    },
    "sum_toptrader_long_short_ratio": {
        "rest": ("topLongShortPositionRatio", "longShortRatio"),
        "tol": 5e-5,                                 # arredondamento de 4 casas do REST
        "reconcilia": True,
    },
    "count_toptrader_long_short_ratio": {
        "rest": ("topLongShortAccountRatio", "longShortRatio"),
        "tol": None,                                 # NAO reconcilia -- registrado, nao mascarado
        "reconcilia": False,
    },
    "count_long_short_ratio": {
        "rest": ("globalLongShortAccountRatio", "longShortRatio"),
        "tol": None,
        "reconcilia": False,
    },
    "sum_taker_long_short_vol_ratio": {
        "rest": ("takerlongshortRatio", "buySellRatio"),
        "tol": None,
        "reconcilia": False,
    },
}

#: As colunas que a §4 autoriza a virar feature. As outras ficam no DataFrame como
#: DIAGNOSTICO -- lê-las e permitido, decidir com elas nao, enquanto nao reconciliarem.
COLUNAS_RECONCILIADAS = tuple(c for c, m in COLUNAS.items() if m["reconcilia"])


def par_para_simbolo(par):
    """'ETH/USDT' -> 'ETHUSDT'. O dump usa o id do contrato perpetuo USD-M."""
    return par.replace("/", "").replace(":USDT", "").upper()


def exigir_lookback_valido(dias):
    """[Q-17 §4] Portao de paridade. Levanta se a feature pedir janela maior que o vivo
    consegue enxergar. Existe para o erro aparecer em quem ESCREVE a feature, e nao seis
    semanas depois num veredito que nao reproduz."""
    if dias <= 0:
        raise ValueError(f"lookback tem de ser positivo, veio {dias}")
    if dias > LOOKBACK_MAX_DIAS:
        raise ValueError(
            f"lookback de {dias} dias fura o teto de paridade de {LOOKBACK_MAX_DIAS} dias "
            f"([Q-17] §4): o backtest le o dump (4,7 anos) mas o bot ao vivo so enxerga 30 "
            f"dias pelo REST. Uma feature assim nao pode ser calculada em producao."
        )
    return dias


# ============================ download e cache ============================
def _baixar(url, tentativas=4, timeout=60):
    """GET cru com backoff. 404 sobe na hora: dia que nao existe no dump nao e falha de
    rede, e insistir so gasta tempo."""
    ultimo = None
    for n in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cripto-bot/Q-17"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            ultimo = e
        except Exception as e:                                    # rede, DNS, timeout
            ultimo = e
        time.sleep(0.5 * (2 ** n))
    raise ultimo


def caminho_cache(simbolo, dia):
    return os.path.join(CACHE_DIR, simbolo, f"{simbolo}-metrics-{dia}.csv")


def _volatil(dia, hoje=None):
    """Os dois ultimos dias sao VOLATEIS: o dump e D+1, entao o arquivo de ontem pode
    aparecer ou ser reescrito enquanto o dia corre. Todo o resto e historia congelada."""
    hoje = hoje or datetime.datetime.now(datetime.timezone.utc).date()
    return (hoje - datetime.date.fromisoformat(dia)).days <= 1


def baixar_dia(simbolo, dia, usar_cache=True):
    """Um dia de `metrics` (288 buckets de 5 min), como texto CSV cru.

    **O cache nunca expira, e isso e medido.** Rebaixei o mesmo arquivo e ele voltou
    IDENTICO byte a byte (11.462 bytes, ETHUSDT 2026-08-15). Arquivo diario historico e
    imutavel, entao a chave e `(simbolo, dia)` e nao carrega a data de HOJE -- ao contrario
    do `dados.baixar_ohlcv`, cujo nome de cache carrega o dia do download justamente porque
    a janela dele desliza. Consequencia pratica: os ~13.100 downloads da janela da regua
    acontecem UMA vez na vida, rerodar sai de graca, e uma queda no meio nao perde nada.

    Devolve `None` quando o dia nao existe no dump (404) -- moeda que ainda nao listava.
    """
    alvo = caminho_cache(simbolo, dia)
    if usar_cache and os.path.exists(alvo) and not _volatil(dia):
        with io.open(alvo, encoding="utf-8") as f:
            return f.read()

    url = f"{BASE_DUMP}/data/futures/um/daily/metrics/{simbolo}/{simbolo}-metrics-{dia}.zip"
    try:
        bruto = _baixar(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    with zipfile.ZipFile(io.BytesIO(bruto)) as z:
        texto = z.read(z.namelist()[0]).decode("utf-8")

    if usar_cache:
        os.makedirs(os.path.dirname(alvo), exist_ok=True)
        with io.open(alvo, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
    return texto


#: 1970-01-01T00:00:00Z, a referencia da conversao para ms.
_EPOCA = pd.Timestamp("1970-01-01", tz="UTC")


def _para_frame(texto):
    """CSV cru -> DataFrame com `timestamp` em ms UTC. `create_time` e naive e E UTC.

    A conversao e por SUBTRACAO da epoca e divisao por 1 ms, e nao por
    `.astype("int64") // 1_000_000`. O atalho parece equivalente e nao e: a resolucao que o
    pandas infere de uma coluna de texto mudou de `datetime64[ns]` para `datetime64[us]`, e
    com `[us]` o mesmo `//1_000_000` devolve SEGUNDOS -- carimbos mil vezes menores, que
    alinham silenciosamente com nada e viram um DataFrame inteiro de NaN. Escrito assim, a
    conta nao depende da resolucao que a versao do pandas escolher. Coberto por
    `test_carimbo_sai_em_milissegundos_de_verdade`.
    """
    df = pd.read_csv(io.StringIO(texto))
    ts = pd.to_datetime(df["create_time"], utc=True)
    df.insert(0, "timestamp", ((ts - _EPOCA) // pd.Timedelta(milliseconds=1)).astype("int64"))
    return df.drop(columns=["create_time", "symbol"], errors="ignore")


def baixar_metricas(par, dias=1095, usar_cache=True, trabalhadores=8, ate=None):
    """Todos os buckets de 5 min de `dias` dias, um DataFrame ordenado por `timestamp`.

    `trabalhadores` baixa em paralelo porque sao milhares de arquivos pequenos; o cache
    imutavel faz a segunda chamada nao tocar a rede.
    """
    fim = ate or datetime.datetime.now(datetime.timezone.utc).date()
    simbolo = par_para_simbolo(par)
    datas = [(fim - datetime.timedelta(days=k)).isoformat() for k in range(dias, 0, -1)]

    partes = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=trabalhadores) as pool:
        futuros = {pool.submit(baixar_dia, simbolo, d, usar_cache): d for d in datas}
        for fut in concurrent.futures.as_completed(futuros):
            texto = fut.result()
            if texto:
                partes[futuros[fut]] = texto

    if not partes:
        return pd.DataFrame(columns=["timestamp", *COLUNAS])
    df = pd.concat([_para_frame(partes[d]) for d in sorted(partes)], ignore_index=True)
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


# ============================ alinhamento na grade da regua ============================
def alinhar(df_metricas, timestamps_barra, tf_ms, colunas=None):
    """[Q-17 §4.1] Traz cada metrica para a grade de barras SEM look-ahead.

    `timestamps_barra` sao instantes de FECHAMENTO de barra (o `dados.baixar_ohlcv` carimba
    a ABERTURA, entao quem chama soma o timeframe antes -- ver `serie_1h`). `tf_ms` e a
    duracao da barra, e ela nao e decoracao: e o teto de defasagem.

    A regra e o `merge_asof` para tras sobre o instante OBSERVAVEL:

        valor_da_barra(T) = ultimo bucket com create_time + 15 min <= T,
                            desde que esse bucket caia DENTRO da propria barra

    **O teto e uma barra, e nao um dia -- e o motivo tem cicatriz.** Com teto de um dia, o
    `merge_asof` propagava o ultimo valor conhecido por 24 barras seguidas: como o dump e
    D+1, todas as barras de HOJE recebiam, identico, o open interest do ultimo bucket de
    ONTEM. O smoke test ponta a ponta pegou quatro barras seguidas com
    `sum_open_interest = 2417752.521`. Nao estourava nada -- so entregava um dado velho com
    cara de dado. Com teto de uma barra, a mesma situacao vira `NaN`, que e o que ela e:
    barra sem medida. Quem consumir decide o que fazer com o buraco, mas decide sabendo.
    Coberto por `test_borda_d_mais_1_vira_nan_e_nao_valor_repetido`.
    """
    colunas = list(colunas or COLUNAS)
    esq = pd.DataFrame({"timestamp": pd.Series(list(timestamps_barra), dtype="int64")})
    esq = esq.sort_values("timestamp").reset_index(drop=True)
    if df_metricas.empty:
        for c in colunas:
            esq[c] = float("nan")
        return esq

    dir_ = df_metricas[["timestamp", *colunas]].copy()
    dir_["timestamp"] = dir_["timestamp"] + ATRASO_OBSERVACAO_MS   # carimba pelo instante em
    dir_ = dir_.sort_values("timestamp").reset_index(drop=True)     # que o dado E OBSERVAVEL

    return pd.merge_asof(esq, dir_, on="timestamp", direction="backward",
                         tolerance=int(tf_ms))


def serie_1h(par, dias=1095, df_ohlcv=None, usar_cache=True, ate=None):
    """As metricas na MESMA grade que o `backtest_ativo` ja usa, sem look-ahead.

    Devolve um DataFrame com `timestamp` (abertura da barra, igual ao do OHLCV) mais uma
    coluna por metrica, pronto para `df.merge(..., on='timestamp')`. Nenhuma coluna nova
    entra no `scoring` por este caminho: quem decide isso e a Fase 3 do plano, depois da
    regua.
    """
    from pesquisa import dados                                    # import tardio: sem ciclo

    if df_ohlcv is None:
        df_ohlcv = dados.baixar_ohlcv(par=par, timeframe="1h", dias=dias, usar_cache=usar_cache)
    if df_ohlcv.empty:
        return pd.DataFrame(columns=["timestamp", *COLUNAS])

    tf_ms = 60 * MIN_MS
    aberturas = df_ohlcv["timestamp"].astype("int64").tolist()
    # o dump so precisa cobrir a janela do OHLCV; +2 dias de margem para o merge_asof ter
    # de onde puxar a primeira barra.
    fim = ate or (datetime.datetime.fromtimestamp(aberturas[-1] / 1000, datetime.timezone.utc).date()
                  + datetime.timedelta(days=1))
    span = max(1, (fim - datetime.datetime.fromtimestamp(aberturas[0] / 1000,
                                                         datetime.timezone.utc).date()).days + 2)
    met = baixar_metricas(par, dias=span, usar_cache=usar_cache, ate=fim)

    alinhado = alinhar(met, [t + tf_ms for t in aberturas], tf_ms)  # instante de FECHAMENTO
    alinhado["timestamp"] = alinhado["timestamp"] - tf_ms           # volta para a abertura
    return alinhado


# ============================ funding, historico longo ============================
def funding_historico(par, dias=1095, ate=None):
    """Funding pago, do REST paginado. Nao tem parede de 30 dias: BTCUSDT vai a 2019-09-10
    e ETHUSDT a 2019-11-27 (medido). Sao 3 settlements/dia na maioria dos pares -- o
    intervalo real esta em `fapi/v1/fundingInfo`, e `mercado._settlements_dia` ja o le.
    """
    import json
    simbolo = par_para_simbolo(par)
    fim = int((ate or time.time()) * 1000) if ate else int(time.time() * 1000)
    ini = fim - dias * DIA_MS
    linhas, cursor = [], ini
    while cursor < fim:
        url = (f"{BASE_REST}/fapi/v1/fundingRate?symbol={simbolo}&limit=1000"
               f"&startTime={cursor}&endTime={fim}")
        lote = json.loads(_baixar(url).decode("utf-8"))
        if not lote:
            break
        linhas += lote
        cursor = int(lote[-1]["fundingTime"]) + 1
        if len(lote) < 1000:
            break
    if not linhas:
        return pd.DataFrame(columns=["timestamp", "funding"])
    df = pd.DataFrame({"timestamp": [int(x["fundingTime"]) for x in linhas],
                       "funding": [float(x["fundingRate"]) for x in linhas]})
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


# ============================ reconciliacao (precisa de rede) ============================
def reconciliar(par, dia, colunas=None):
    """[Q-17 §4.2] Compara o dump com o REST no mesmo dia e devolve o placar por coluna.

    E o teste de PARIDADE do plano: backfill e vivo sao dois caminhos de codigo para o
    mesmo numero, e sem isto o backtest mede uma serie e a producao outra. Devolve, por
    coluna: quantos bateram dentro da tolerancia, quantos foram comparados, e a maior
    diferenca absoluta. Nao levanta -- quem julga e o teste, que conhece a tolerancia.
    """
    import json
    colunas = list(colunas or COLUNAS)
    simbolo = par_para_simbolo(par)
    texto = baixar_dia(simbolo, dia)
    if texto is None:
        return {}
    dump = {int(t): r for t, r in zip(_para_frame(texto)["timestamp"],
                                      _para_frame(texto).to_dict("records"))}
    ini = int(pd.Timestamp(dia, tz="UTC").timestamp() * 1000)

    placar = {}
    for col in colunas:
        endpoint, campo = COLUNAS[col]["rest"]
        url = (f"{BASE_REST}/futures/data/{endpoint}?symbol={simbolo}&period=5m&limit=288"
               f"&startTime={ini}&endTime={ini + DIA_MS - 1}")
        rest = json.loads(_baixar(url).decode("utf-8"))
        # o REST carimba pelo FIM do bucket e o dump pelo INICIO -- exceto o taker, que e
        # fluxo e usa a mesma borda nos dois. `deslocamento` traduz um para o outro.
        desloc = 0 if col == "sum_taker_long_short_vol_ratio" else -BUCKET_MS
        ok = n = 0
        pior = 0.0
        tol = COLUNAS[col]["tol"]
        for linha in rest:
            t = int(linha["timestamp"]) + desloc
            if t not in dump:
                continue
            a, b = float(linha[campo]), float(dump[t][col])
            n += 1
            pior = max(pior, abs(a - b))
            if tol is not None and abs(a - b) <= tol:
                ok += 1
        placar[col] = {"iguais": ok, "comparados": n, "maior_dif": pior,
                       "tol": tol, "reconcilia": COLUNAS[col]["reconcilia"]}
    return placar


if __name__ == "__main__":
    import sys
    par = sys.argv[1] if len(sys.argv) > 1 else "ETH/USDT"
    dias = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    df = baixar_metricas(par, dias=dias)
    print(f"{par}: {len(df)} buckets de 5 min | "
          f"{pd.to_datetime(df['timestamp'].iloc[0], unit='ms')} -> "
          f"{pd.to_datetime(df['timestamp'].iloc[-1], unit='ms')}")
    print(df.tail())
    print(f"\ncolunas que reconciliam com o vivo: {COLUNAS_RECONCILIADAS}")
    print(f"teto de lookback (paridade com o REST de 30 dias): {LOOKBACK_MAX_DIAS} dias")
