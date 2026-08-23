"""
Pedra 1 - Baixador de dados historicos (GRATIS, sem chave de API).
Usa endpoint publico da exchange via ccxt e guarda em cache local (CSV).

Rodar (da RAIZ do repo):  python -m pesquisa.dados
"""
import os
import ccxt
import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_cache")


def _fechados(df, tf_ms, agora_ms):
    """[Q-6 (d)] Descarta o candle em FORMACAO -- a barra cujo intervalo ainda nao terminou.

    A exchange devolve a barra corrente junto com as fechadas, e ela nao e um dado: e um
    dado PELA METADE, que muda a cada trade ate o candle fechar. Gravada no CSV, ela vira
    um candle que nunca existiu -- congelado no estado em que estava no instante do
    download. Duas baixas no mesmo dia passam entao a discordar sobre a mesma barra, e o
    nome do arquivo de cache (que carrega a data) promete o contrario: uma janela
    reproduzivel por dia.

    O corte e `timestamp + tf <= agora`: a barra so entra depois de o intervalo dela ter
    fechado. Filtra o DataFrame inteiro em vez de olhar so a ultima linha -- as barras vem
    ordenadas, entao o resultado e o mesmo, mas nao depende dessa ordenacao estar certa.
    """
    if df.empty or not tf_ms:
        return df
    return df[df["timestamp"] + tf_ms <= agora_ms].reset_index(drop=True)


def baixar_ohlcv(par="ETH/USDT", timeframe="1h", dias=540,
                 exchange_id="binance", usar_cache=True):
    """Baixa ~`dias` de candles. Pagina automaticamente (1000 por requisicao).

    Toda barra devolvida daqui e uma barra FECHADA ([Q-6 (d)], `_fechados`)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    hoje = pd.Timestamp.now().strftime("%Y-%m-%d")        # data no nome -> janela reproduzível por dia
    nome = f"{exchange_id}_{par.replace('/', '-')}_{timeframe}_{dias}d_{hoje}.csv"
    cache_file = os.path.join(CACHE_DIR, nome)

    if usar_cache and os.path.exists(cache_file):
        df = pd.read_csv(cache_file, parse_dates=["datetime"])
        return df

    ex = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    tf_ms = ex.parse_timeframe(timeframe) * 1000
    desde = ex.milliseconds() - dias * 24 * 60 * 60 * 1000
    agora = ex.milliseconds()

    todos = []
    while desde < agora:
        lote = ex.fetch_ohlcv(par, timeframe=timeframe, since=desde, limit=1000)
        if not lote:
            break
        todos += lote
        desde = lote[-1][0] + tf_ms
        if len(lote) < 1000:
            break

    df = pd.DataFrame(todos, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
    # `agora` e o instante ANTERIOR ao download, de proposito: uma barra que fechou durante
    # a paginacao sai de fora, nunca uma barra em formacao entra. Erra para menos.
    df = _fechados(df, tf_ms, agora)

    if usar_cache:
        df.to_csv(cache_file, index=False)
    return df


if __name__ == "__main__":
    df = baixar_ohlcv()
    print(f"{len(df)} candles | {df['datetime'].iloc[0]} -> {df['datetime'].iloc[-1]}")
    print(df.tail())
