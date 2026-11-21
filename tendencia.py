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
from indicadores import ema, rsi

MODOS = ("off", "d1", "d2")
DIA_MS = 86_400_000
MIN_VELAS = 50
LIMITE = 500        # EMA50 com 500 velas: o peso do valor inicial some (49/51)^450 ~ 1e-8
RSI_N = 14          # [CD-1] o RSI do diário anotado no sinal
RET_DIAS = 7        # [CD-1] retorno acumulado dos últimos N dias fechados

# ativo -> (dia UTC em que foi calculado, {"d1": lado, "d2": lado}, contexto). O diário só
# muda na virada do dia UTC, então uma requisição por ativo por dia basta -- e ela serve aos
# dois leitores: o filtro de lado [TD-1] e a anotação do sinal [CD-1].
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


def contexto_de(raw, agora_ms):
    """[CD-1] Quão esticado o diário do ativo está, só com velas FECHADAS: o RSI de 14 dias e
    o retorno acumulado dos últimos 7 dias, em %. `None` em cada campo que a história não
    alcança -- ausência de medição, nunca zero (RSI 0 e retorno 0 são leituras de verdade).

    É ANOTAÇÃO, não regra: nada no motor lê isto para decidir. Existe porque em 17/11 o motor
    vendeu rompimentos de suporte no fundo de uma queda de 15% em 7 dias, com o RSI diário
    médio em 30, e nenhuma coluna do sinal guardava esse estado para alguém conferir depois
    se "esticado no diário" separa sinal bom de ruim. As versões mecânicas dessa leitura já
    reprovaram fora da amostra (extensão de 24h, comprar pânico, filtro de regime), então o
    juiz que sobra é o registro ao vivo -- e ele só julga o que foi gravado."""
    c = pd.Series([float(v[4]) for v in raw if v[0] + DIA_MS <= agora_ms])
    r = float(rsi(c, RSI_N).iloc[-1]) if len(c) > RSI_N else float("nan")
    ret = None
    if len(c) > RET_DIAS and c.iloc[-1 - RET_DIAS] > 0:
        ret = round((float(c.iloc[-1]) / float(c.iloc[-1 - RET_DIAS]) - 1) * 100, 2)
    # [EST-2] O último dia fechado sozinho (ontem, no dia UTC): a queda de véspera que o T54b
    # mediu separada da semana.
    ret1 = None
    if len(c) > 1 and c.iloc[-2] > 0:
        ret1 = round((float(c.iloc[-1]) / float(c.iloc[-2]) - 1) * 100, 2)
    return {"rsi": None if r != r else round(r, 1), "ret7": ret, "ret1": ret1}   # r != r: NaN


def _do_dia(ativo, agora_ms=None):
    """A entrada do cache deste ativo para o dia UTC corrente; busca o diário se for preciso."""
    agora_ms = time.time() * 1000 if agora_ms is None else agora_ms
    dia = int(agora_ms // DIA_MS)
    ent = _cache.get(ativo)
    if not ent or ent[0] != dia:
        raw = _velas_1d(ativo)
        # Resposta VAZIA não é "moeda recém-listada": é a corretora não respondendo direito. Ela
        # virava "tendência indefinida = passa" e ficava no cache até a virada do dia UTC, com o
        # filtro desligado para aquele ativo por até 24 h. Agora levanta, como toda falha de rede
        # deste módulo: o auto-trader pula o candidato no ciclo e tenta de novo no próximo.
        if not raw:
            raise RuntimeError(f"a corretora devolveu o diário de {ativo} vazio")
        ent = (dia, lados(raw, agora_ms), contexto_de(raw, agora_ms))
        _cache[ativo] = ent
    return ent


def lado(ativo, modo, agora_ms=None):
    return _do_dia(ativo, agora_ms)[1][modo]


def contexto(ativo, agora_ms=None):
    """[CD-1] `{"rsi", "ret7", "ret1"}` do diário do ativo. Levanta em falha de rede, como `lado`:
    quem decide o que fazer com a ausência é quem chama (o scan grava NULL e segue)."""
    return _do_dia(ativo, agora_ms)[2]


def permite(ativo, direcao, modo, agora_ms=None):
    """True se o sinal pode abrir. `modo` fora de d1/d2 (inclusive 'off') não filtra nada."""
    if modo not in ("d1", "d2"):
        return True
    l = lado(ativo, modo, agora_ms)
    if l is None:
        return True
    return l == (1 if str(direcao).upper() == "LONG" else -1)
