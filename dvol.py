"""[DV-1] Volatilidade implícita do BTC (DVOL da Deribit): o percentil de ONTEM contra os 180 dias
anteriores, para anotar em cada sinal (`sinais.dvol_pct`) e para a chave `auto_dvol_corte`.

O que é: o DVOL é o "VIX do BTC", a volatilidade que as opções de 30 dias cobram. Uma leitura do
mercado inteiro, não do ativo -- o mesmo número vale para todos os sinais do dia.

Por que existe (testes\\T61 e testes\\T63, fora do repo): nos trades da regra de produção, abrir
com o DVOL de ONTEM no percentil >= 0,80 dos 180 dias anteriores rendeu pior nos dois lados.
Descoberta 2021-10..2023: +0,542R por trade a favor de não abrir [+0,294; +0,775]; reserva
2024-26, aberta só depois: +0,248R [+0,029; +0,471]; positivo em todo ano de 2022 a 2026; bate
20 de 20 placebos (a série deslocada no tempo). Não é o ATR% do ativo (o [AG-1]): a correlação
entre os dois é 0,14-0,20, e o DVOL separa dentro de cada terço de ATR%. Na carteira do motor
(T63, 1.000 caminhos, com a vaga recusada indo ao próximo candidato) a mediana subiu 5,3x na
config de hoje e 2,9x na B, com o DD mediano menor nas duas.

O relógio é o da medida: a vela diária do DVOL de D (rótulo 00:00 UTC) só conta depois de
FECHAR, em D+1 00:00 UTC. O sinal do dia D lê o close de D−1. O percentil usa os 180 dias
corridos antes de D−1, com no mínimo 150 leituras (dia sem vela fica fora da conta, não vira
zero). Abaixo disso: `None`, ausência de medição.

Uma requisição por dia UTC (cache como o do `tendencia`), API pública, sem chave.
"""
import json
import time
import urllib.request

DIA_MS = 86_400_000
JANELA = 180          # dias corridos antes do dia lido -- o número da medida, não config
MINIMO = 150          # leituras válidas exigidas na janela
URL = ("https://www.deribit.com/api/v2/public/get_volatility_index_data"
       "?currency=BTC&resolution=1D&start_timestamp={a}&end_timestamp={b}")

_cache = {}


def _baixar(agora_ms):
    """Velas diárias `[t, o, h, l, c]` dos últimos ~200 dias. Levanta em falha de rede."""
    a = int(agora_ms - (JANELA + 20) * DIA_MS)
    with urllib.request.urlopen(URL.format(a=a, b=int(agora_ms)), timeout=10) as r:
        return json.load(r)["result"]["data"]


def percentil_de(raw, agora_ms):
    """`{"dvol", "pct"}` do último dia FECHADO. `pct` = fração dos dias da janela com DVOL abaixo
    do dele (empate conta meio). `None` em cada campo que os dados não alcançam."""
    fechadas = {int(v[0]) // DIA_MS: float(v[4]) for v in raw
                if v and v[4] is not None and int(v[0]) + DIA_MS <= agora_ms}
    if not fechadas:
        return {"dvol": None, "pct": None}
    dia = max(fechadas)
    v = fechadas[dia]
    ant = [fechadas[d] for d in range(dia - JANELA, dia) if d in fechadas]
    if len(ant) < MINIMO:
        return {"dvol": round(v, 2), "pct": None}
    p = (sum(1 for x in ant if x < v) + 0.5 * sum(1 for x in ant if x == v)) / len(ant)
    return {"dvol": round(v, 2), "pct": round(p, 4)}


def contexto(agora_ms=None):
    """`{"dvol", "pct"}` de ontem. Uma requisição por dia UTC; levanta em falha de rede ou
    resposta vazia (vazio não é "sem medição", é a fonte não respondendo direito -- e ficaria no
    cache até a virada do dia). Quem chama decide o que fazer com a ausência."""
    agora_ms = time.time() * 1000 if agora_ms is None else agora_ms
    dia = int(agora_ms // DIA_MS)
    ent = _cache.get("btc")
    if not ent or ent[0] != dia:
        raw = _baixar(agora_ms)
        if not raw:
            raise RuntimeError("a Deribit devolveu o DVOL vazio")
        ent = (dia, percentil_de(raw, agora_ms))
        _cache["btc"] = ent
    return ent[1]
