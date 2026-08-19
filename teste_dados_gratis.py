"""
Teste rapido: baixar dados historicos reais de cripto DE GRACA (sem chave de API).
Prova que da pra comecar as simulacoes sem gastar nada.
"""
import ccxt
import pandas as pd

PAR = "ETH/USDT"
TIMEFRAME = "1d"   # candles diarios
LIMITE = 30        # ultimos 30 dias

def baixar(exchange_id):
    ex = getattr(ccxt, exchange_id)()
    # fetch_ohlcv usa endpoint PUBLICO -> nao precisa de chave
    ohlcv = ex.fetch_ohlcv(PAR, timeframe=TIMEFRAME, limit=LIMITE)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["data"] = pd.to_datetime(df["timestamp"], unit="ms").dt.date
    return df, ex.id

# tenta Binance; se a regiao bloquear, cai pra outra exchange (dados equivalentes)
df = None
for exid in ["binance", "kraken", "coinbase", "kucoin"]:
    try:
        df, usada = baixar(exid)
        print(f"[OK] Dados baixados da exchange: {usada}  (sem chave de API)\n")
        break
    except Exception as e:
        print(f"[--] {exid} falhou ({type(e).__name__}); tentando proxima...")

if df is None:
    raise SystemExit("Nenhuma exchange respondeu. Verifique a conexao.")

# mostra os ultimos dias
print(f"Par: {PAR} | timeframe: {TIMEFRAME} | {len(df)} candles\n")
print(df[["data", "open", "high", "low", "close", "volume"]].tail(10).to_string(index=False))

# uma amostradinha de "analise" pra mostrar o potencial
df["var_%"] = (df["close"] / df["open"] - 1) * 100
dias_fortes = (df["var_%"].abs() >= 2).sum()
print(f"\nPreco atual de {PAR}: {df['close'].iloc[-1]:,.2f} USDT")
print(f"Nos ultimos {len(df)} dias, {dias_fortes} tiveram movimento >= 2% (candidatos a trade direcional)")
print(f"Volatilidade diaria media: {df['var_%'].abs().mean():.2f}%")
print("\n>>> Tudo isso de graca, sem chave, rodando no seu PC. As simulacoes podem comecar.")
