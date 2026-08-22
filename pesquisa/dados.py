"""
Pedra 1 - Baixador de dados historicos (GRATIS, sem chave de API).
Usa endpoint publico da exchange via ccxt e guarda em cache local (CSV).
"""
import os
import ccxt
import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_cache")


def baixar_ohlcv(par="ETH/USDT", timeframe="1h", dias=540,
                 exchange_id="binance", usar_cache=True):
    """Baixa ~`dias` de candles. Pagina automaticamente (1000 por requisicao)."""
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

    if usar_cache:
        df.to_csv(cache_file, index=False)
    return df


if __name__ == "__main__":
    df = baixar_ohlcv()
    print(f"{len(df)} candles | {df['datetime'].iloc[0]} -> {df['datetime'].iloc[-1]}")
    print(df.tail())
