"""
[TP-1] Alvos de lucro (take profit) por ESTRUTURA de mercado: suporte/resistência + Fibonacci.

Por que existe: até aqui o único jeito do bot realizar lucro era o trailing 3R/3R, que só fecha
quando o preço DEVOLVE 3R do pico. Com cinco posições correlacionadas no lucro, isso é devolver
3R cinco vezes ao mesmo tempo -- e o lucro do mês vinha dos fechamentos manuais do dono, pelo
segundo mês seguido (revisão de outubro). O dono decidiu (10/11) que o bot realiza no alvo, como
um trader: TP1/TP2/TP3 em zonas onde o preço costuma reagir, saindo em parcelas.

Ressalva declarada, para não maquiar: o T17 (01/11) mediu TP fracionado em % e em R, com stop
subindo em escada, e REPROVOU; Fibonacci isolado também reprovou no T1. Esta regra é diferente
em dois pontos (alvo em zona de estrutura, e o stop NÃO sobe em escada -- quem cuida do stop
continua sendo o trailing), mas não foi validada na régua. A decisão de ligar é do dono; a
medição fica por conta do `motivo_saida` = tp1/tp2/tp3 na tabela `trades`.

Como os níveis saem (tudo calculado UMA vez por posição e gravado em `posicoes.tps`):

1. **Pivôs** (fractal de 2k+1 velas) em 4h (peso 2) e em 1h (peso 1): máximas e mínimas locais
   são onde o mercado já virou -- topo antigo é resistência, fundo antigo é suporte.
2. **Fibonacci** do maior movimento das últimas ~20 dias de 4h: retrações 23,6/38,2/50/61,8/78,6%
   e extensões 127,2/161,8% para os dois lados (peso 1 cada).
3. Níveis a menos de `0,35 x ATR(1h)` uns dos outros viram uma **zona**; a força da zona é a
   soma dos pesos (zona onde pivô de 4h e Fibo coincidem é mais forte).
4. Os TPs são as zonas na direção do trade, a pelo menos `tp_min_r` R da entrada, escolhendo
   primeiro as fortes (força >= `tp_forca_min`), espaçadas de >= 0,5R. O alvo fica um pouco
   ANTES da zona (`0,2 x ATR`): o preço costuma reagir antes de tocar o nível, e alvo em cima
   do nível é alvo que não enche.
5. Sem estrutura suficiente, completa com múltiplos de R (`tp_fallback_r`), para toda posição
   ter alvo.
"""
import json

import pandas as pd

import indicadores

FIB_RETR = (0.236, 0.382, 0.5, 0.618, 0.786)
FIB_EXT = (1.272, 1.618)


def _df(raw):
    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    return df.astype({"open": float, "high": float, "low": float, "close": float})


def pivos(df, k=3):
    """Máximas e mínimas de fractal: a vela é o extremo de uma janela de 2k+1 centrada nela.
    As k últimas velas ficam de fora -- ainda não têm vizinhas à direita, e pivô que depende de
    vela futura é repaint."""
    janela = 2 * k + 1
    hi = df["high"].rolling(janela, center=True).max()
    lo = df["low"].rolling(janela, center=True).min()
    topos = df.loc[df["high"] == hi, "high"].tolist()
    fundos = df.loc[df["low"] == lo, "low"].tolist()
    return topos, fundos


def fibonacci(df):
    """Retrações e extensões do maior movimento da janela. A ordem de topo e fundo diz o sentido
    do movimento; as extensões vão para os dois lados porque o alvo de um SHORT está abaixo do
    fundo e o de um LONG acima do topo, qualquer que tenha sido o último movimento."""
    i_hi, i_lo = int(df["high"].values.argmax()), int(df["low"].values.argmin())
    hi, lo = float(df["high"].iloc[i_hi]), float(df["low"].iloc[i_lo])
    amp = hi - lo
    if amp <= 0:
        return []
    subiu = i_hi > i_lo                       # fundo antes do topo: o movimento foi de alta
    niveis = [(hi - r * amp) if subiu else (lo + r * amp) for r in FIB_RETR]
    niveis += [lo + e * amp for e in FIB_EXT] + [hi - e * amp for e in FIB_EXT]
    return [n for n in niveis if n > 0]


def zonas(niveis_pesos, tol):
    """Agrupa níveis próximos (gap <= tol) numa zona: preço = média ponderada, força = soma."""
    pts = sorted(niveis_pesos)
    out, grupo = [], []
    for p, w in pts:
        if grupo and p - grupo[-1][0] > tol:
            out.append(grupo)
            grupo = []
        grupo.append((p, w))
    if grupo:
        out.append(grupo)
    res = []
    for g in out:
        peso = sum(w for _, w in g)
        res.append({"preco": sum(p * w for p, w in g) / peso, "forca": peso})
    return res


def escolher_tps(direcao, entrada, r, zs, atr1h, cfg):
    """Os TPs na direção do trade, do mais perto ao mais longe. `r` = 1R em preço (> 0)."""
    d = 1 if direcao == "LONG" else -1
    n = int(cfg["tp_n"])
    min_r, max_r, forca_min = cfg["tp_min_r"], cfg["tp_max_r"], cfg["tp_forca_min"]
    folga = 0.2 * atr1h
    cand = []
    for z in zs:
        alvo = z["preco"] - d * folga
        dist_r = d * (alvo - entrada) / r
        if min_r <= dist_r <= max_r:
            cand.append({"preco": alvo, "r": dist_r, "forca": z["forca"], "fonte": "estrutura"})
    cand.sort(key=lambda c: c["r"])

    escolhidos = []

    def cabe(c):
        return all(abs(c["r"] - e["r"]) >= 0.5 for e in escolhidos)

    for c in cand:                                    # 1o as zonas fortes, em ordem de distância
        if len(escolhidos) >= n:
            break
        if c["forca"] >= forca_min and cabe(c):
            escolhidos.append(c)
    for c in cand:                                    # depois as fracas, se faltou
        if len(escolhidos) >= n:
            break
        if c not in escolhidos and cabe(c):
            escolhidos.append(c)
    for mult in cfg["tp_fallback_r"]:                 # e por fim múltiplos de R
        if len(escolhidos) >= n:
            break
        c = {"preco": entrada + d * mult * r, "r": float(mult), "forca": 0, "fonte": "R"}
        if cabe(c):
            escolhidos.append(c)
    escolhidos.sort(key=lambda c: c["r"])
    return escolhidos[:n]


def fracoes(cfg, k):
    """Quanto da posição ORIGINAL sai em cada TP. O último sempre leva o que sobrou."""
    fr = list(cfg["tp_fracoes"])[:k]
    while len(fr) < k:
        fr.append(fr[-1] if fr else 1.0 / k)
    soma = sum(fr) or 1.0
    fr = [f / soma for f in fr]
    return fr


def calcular(pos, raw_1h, raw_4h, cfg):
    """Monta o plano de TPs de uma posição. Função pura: recebe as velas, não busca nada.
    Devolve o dict que vai, em JSON, para `posicoes.tps`."""
    entrada = float(pos["entrada"])
    sa = pos.get("stop_abertura") or pos.get("stop")
    r = abs(entrada - float(sa)) if sa else 0.0
    df1, df4 = _df(raw_1h), _df(raw_4h)
    atr1h = float(indicadores.atr(df1).iloc[-1]) if len(df1) > 15 else entrada * 0.01
    if r <= 0:                                        # sem stop não há R: usa 3 ATR (= o stop do motor)
        r = 3 * atr1h
    niveis = []
    for df, peso in ((df4, 2), (df1, 1)):
        topos, fundos = pivos(df)
        niveis += [(p, peso) for p in topos + fundos]
    niveis += [(p, 1) for p in fibonacci(df4.tail(120))]
    zs = zonas(niveis, 0.35 * atr1h)
    tps = escolher_tps(pos["direcao"], entrada, r, zs, atr1h, cfg)
    fr = fracoes(cfg, len(tps))
    for t, f in zip(tps, fr):
        t["preco"] = round(t["preco"], 8)
        t["r"] = round(t["r"], 2)
        t["frac"] = round(f, 4)
        t["feito"] = False
    return {"niveis": tps, "valor_inicial": float(pos["valor_reais"]), "r_preco": r,
            "calc_em": str(pd.Timestamp.now())}


def cfg_tp(cfg):
    """A política de TP da config, resolvida uma vez por ciclo (mesma razão do `_trailing_cfg`)."""
    def f(chave, padrao):
        try:
            return float(cfg.get(chave, padrao))
        except (TypeError, ValueError):
            return float(padrao)

    def lista(chave, padrao):
        try:
            return [float(x) for x in str(cfg.get(chave, padrao)).split(",") if x.strip()]
        except ValueError:
            return [float(x) for x in padrao.split(",")]

    return {"on": str(cfg.get("tp_ativo", "0")) in ("1", "true", "True"),
            "tp_n": int(f("tp_n", 3)),
            "tp_min_r": f("tp_min_r", 1.0),
            "tp_max_r": f("tp_max_r", 12.0),
            "tp_forca_min": f("tp_forca_min", 2.0),
            "tp_fracoes": lista("tp_fracoes", "0.34,0.33,0.33"),
            "tp_fallback_r": lista("tp_fallback_r", "2,4,6")}


def ler(pos):
    """O plano gravado na posição, ou None."""
    try:
        txt = pos["tps"]
    except (KeyError, IndexError):
        return None
    if not txt:
        return None
    try:
        return json.loads(txt)
    except (TypeError, ValueError):
        return None


def proximo(plano):
    """O primeiro TP ainda não feito, com o índice, ou (None, None)."""
    for i, t in enumerate((plano or {}).get("niveis", [])):
        if not t.get("feito"):
            return i, t
    return None, None


def bateu(direcao, preco, alvo):
    return preco >= alvo if direcao == "LONG" else preco <= alvo

