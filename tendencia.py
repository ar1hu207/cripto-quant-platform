"""[TD-1] Filtro de direção pela tendência do DIÁRIO -- o T38 (`testes/T38/`, fora do repo).

O motor decide o lado no mesmo gráfico rápido em que entra (15m/30m/1h) e, medido em 45
meses de futuros, entra CONTRA a tendência do diário do próprio ativo em ~metade das vezes.
Com o filtro, no histórico (2023-01..2026-09, motor do T24 a 1,5%): mediana de 1.000
caminhos R$4.132 -> R$42.612, R médio +0,086 -> +0,145R, positivo nos 4 anos, e 19 de 20
placebos (cortar a MESMA quantidade de candidatos por mês, sem olhar o lado) abaixo dele.
Reprovou na régua do T24 só no item P(DD>50%), que é 100% em qualquer variante a 1,5% --
quem decide esse item é o tamanho, não a entrada. É descoberta, não confirmação: por isso
nasce DESLIGADO e entra pela conta B (`PLANO-CONTA-B`), por decisão do dono em 10/11.

A regra é a do pré-registro, sem ajuste:
  * vela DIÁRIA (UTC, a da Binance) do PRÓPRIO ativo; só velas FECHADAS (a do dia corrente
    está em formação e repinta -- ler ela seria olhar o futuro do dia);
  * `d1` (estrito): LONG só com EMA20 > EMA50 **e** close > EMA50; SHORT só com EMA20 < EMA50
    **e** close < EMA50; no meio, nenhum lado;
  * `d2`: só o cruzamento EMA20 x EMA50;
  * menos de 50 velas fechadas = tendência indefinida = o sinal PASSA (é o aquecimento do
    backtest: moeda recém-listada não é barrada por falta de histórico).

Falha de rede NÃO vira "passa": a exceção sobe e o auto-trader pula o candidato no ciclo (o
sinal segue 'novo' e é reavaliado no próximo). Apertar na dúvida pode; afrouxar não.

O que NÃO foi medido e fica declarado: o T38 leu velas de FUTUROS; aqui o cliente é o spot
(`mercado.ex_spot`), como todo o resto do motor até o B-2. EMA de 20/50 dias de spot e perp
do mesmo ativo diferem por base de centésimos; o lado quase nunca troca por isso.
"""
import time

import pandas as pd

import mercado
from indicadores import ema

MODOS = ("off", "d1", "d2")
DIA_MS = 86_400_000
MIN_VELAS = 50
LIMITE = 500        # EMA50 com 500 velas: o peso do valor inicial some (49/51)^450 ~ 1e-8

# ativo -> (dia UTC em que foi calculado, {"d1": lado, "d2": lado}). O diário só muda na
# virada do dia UTC, então uma requisição por ativo por dia basta.
_cache = {}


def _velas_1d(ativo):
    return mercado.ex_spot.fetch_ohlcv(ativo, timeframe="1d", limit=LIMITE)


def lados(raw, agora_ms):
    """Dos candles diários crus, o lado permitido por modo: +1, -1, 0 (nenhum) ou None
    (indefinido -> passa). Só entra vela cujo fecho (abertura + 1 dia) já passou."""
    fech = [v for v in raw if v[0] + DIA_MS <= agora_ms]
    if len(fech) < MIN_VELAS:
        return {"d1": None, "d2": None}
    c = pd.Series([float(v[4]) for v in fech])
    er, el, cl = float(ema(c, 20).iloc[-1]), float(ema(c, 50).iloc[-1]), float(c.iloc[-1])
    d2 = 1 if er > el else (-1 if er < el else 0)
    d1 = 1 if (er > el and cl > el) else (-1 if (er < el and cl < el) else 0)
    return {"d1": d1, "d2": d2}


def lado(ativo, modo, agora_ms=None):
    agora_ms = time.time() * 1000 if agora_ms is None else agora_ms
    dia = int(agora_ms // DIA_MS)
    ent = _cache.get(ativo)
    if not ent or ent[0] != dia:
        ent = (dia, lados(_velas_1d(ativo), agora_ms))
        _cache[ativo] = ent
    return ent[1][modo]


def permite(ativo, direcao, modo, agora_ms=None):
    """True se o sinal pode abrir. `modo` fora de d1/d2 (inclusive 'off') não filtra nada."""
    if modo not in ("d1", "d2"):
        return True
    l = lado(ativo, modo, agora_ms)
    if l is None:
        return True
    return l == (1 if str(direcao).upper() == "LONG" else -1)
