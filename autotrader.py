"""
Auto-trader (EXPERIMENTO) — executa trades sozinho no preço real (paper trading).

A cada ciclo do worker: pega os MELHORES sinais novos (maior convicção, ja passaram
pelos portões do scan), dimensiona pelo risco e ABRE a posição automaticamente; e
fecha sozinho quando o gestor de saída aponta reversão com lucro.

IMPORTANTE — honestidade: ja provamos (walk-forward + DSR ~0) que a estratégia de
confluência NAO tem edge. O esperado aqui e o bot DERIVAR pra perda por causa de
taxa + alavancagem. Isto NAO e pra ganhar dinheiro — e pra VER o "no edge" acontecer
ao vivo. Roda dentro dos mesmos portões de risco (trava diária + teto de exposição),
entao e um experimento CONTROLADO, nao um cassino sem freio.

Liga/desliga: config auto_trade = "1"/"0".
"""
import pandas as pd

import db
import simulador
from logbot import log
from signal_engine import MOTIVO_FLUXO_ND


def _verdade(v):
    return str(v) in ("1", "true", "True")


def _fluxo_checado(s):
    """[P2-9] O sinal foi confirmado COM o portao de fluxo rodando?

    O humano da fila manual ve o aviso "fluxo n/d" no card do sinal e decide; o bot nao le
    aviso. Com `exigir_fluxo=1` o dono declarou que nao quer operar tendencia sem o fluxo a
    favor — entao o bot tambem nao opera sobre fluxo NAO VERIFICADO. Com `exigir_fluxo=0` o
    portao esta desligado e nada muda: nenhum sinal carrega a marca.
    """
    return MOTIVO_FLUXO_ND not in (s["motivos"] or "")


def _alavancagem(cfg, conviccao):
    """Alavancagem do trade. Modo 'conviccao': escala LINEAR da convicção mínima (lev_min) até
    100 (lev_max=teto), arredondada e limitada a [lev_min, lev_max]. Modo 'fixo': alavancagem_padrao.
    AVISO: escalar pra cima na convicção assume que convicção prevê acerto — NÃO comprovado (DSR~0).
    Alavancagem alta aproxima a liquidação (~LIQ_BUFFER/lev), virando stops em perdas de margem inteira."""
    if cfg.get("auto_lev_modo", "conviccao") != "conviccao":
        return float(cfg.get("alavancagem_padrao", 10))
    lev_min = float(cfg.get("auto_lev_min", 2))
    lev_max = float(cfg.get("auto_lev_max", 20))
    conv_min = float(cfg.get("auto_conviccao_min", 60))
    conv = conviccao if conviccao is not None else conv_min
    frac = (conv - conv_min) / max(100 - conv_min, 1)
    frac = min(max(frac, 0.0), 1.0)
    lev = lev_min + frac * (lev_max - lev_min)
    return float(max(lev_min, min(round(lev), lev_max)))     # inteiro, dentro de [lev_min, teto]


def _tamanho(banca, risco_frac, lev, entrada, stop, max_frac, min_valor=10.0):
    """Sizing por risco: valor tal que a perda-até-o-stop ~= banca*risco_frac.
    Capa em banca*max_frac. Retorna 0 (=pular o sinal) quando a banca não comporta o piso,
    quando o risco pedido não paga o piso, ou com banca morta (<=0).

    [P2-8] O piso é FILTRO, nunca inflador. `risco_por_trade` é TETO: subir o valor até o
    piso furava esse teto em silêncio (banca R$100 a 3% pede R$3 e abria R$10 = 10% da
    banca, 3,3x o configurado). Banca pequena passa a dar MENOS trades, nunca mais risco.
    A guarda `cap < min_valor` acima NÃO cobre isso: ela só pega banca tão pequena que o
    cap fica abaixo do piso (<R$40 com max_frac=0,25); o buraco estava na faixa do meio."""
    cap = banca * max_frac
    if banca <= 0 or cap < min_valor:           # banca morta ou pequena demais: não opera
        return 0.0
    risco_rs = banca * risco_frac
    if entrada and stop and entrada != stop:
        sd = abs(entrada - stop) / entrada
        denom = min(lev * sd, 1.0)              # se a liquidação vem antes do stop, risco=valor (denom=1)
    else:
        denom = 1.0
    valor = risco_rs / denom if denom > 0 else risco_rs
    if valor < min_valor:                       # [P2-8] piso: FILTRA o sinal, não infla o risco
        return 0.0
    valor = min(valor, cap)                     # cap (>= min_valor, garantido acima)
    return round(valor, 2)


def auto_executar(saidas=None):
    """Roda 1 ciclo do auto-trader. `saidas` = lista do avaliar_saida (pra auto-fechar).
    Retorna resumo das ações (pra UI/log). Sem efeito se auto_trade desligado."""
    cfg = db.get_config()
    if not _verdade(cfg.get("auto_trade", "0")):
        return {"ativo": False}

    res = {"ativo": True, "abertos": [], "fechados": [], "rejeitados": [],
           "ts": str(pd.Timestamp.now())}

    # 1) auto-fechar (scalp em reversão+lucro) — DESLIGADO quando o trailing está ativo:
    #    com trailing, deixamos o lucro correr e quem fecha o vencedor é o trailing stop, não o scalp.
    if _verdade(cfg.get("auto_fechar_saida", "1")) and not _verdade(cfg.get("trailing_ativo", "1")) and saidas:
        for sd in saidas:
            if sd and sd.get("nivel") in ("forte", "lucro"):
                try:
                    pnl = simulador.fechar(sd["posicao_id"], "auto-saida")
                    if pnl is not None:
                        res["fechados"].append({"ativo": sd["ativo"], "pnl": round(pnl, 2),
                                                "motivo": sd["nivel"]})
                except Exception as e:
                    log(f"auto-trader fechar erro pos {sd.get('posicao_id')}: {e}", "error")

    # 2) trava diária bloqueia novas entradas
    g = simulador.guarda_risco()
    if g["trava_dia"]:
        res["motivo"] = "trava diária ativa"
        return res

    # 3) slots livres
    abertas = db.listar("posicoes", 200, "WHERE status='aberta'")
    max_pos = int(float(cfg.get("auto_max_posicoes", 5)))
    slots = max_pos - len(abertas)
    if slots <= 0:
        res["motivo"] = f"limite de posições ({max_pos}) atingido"
        return res
    ativos_abertos = {p["ativo"] for p in abertas}

    # 4) orçamento de margem (teto de exposição) — trades encolhem conforme a exposição cresce
    banca = db.get_banca()["atual"]
    risco_frac = float(cfg.get("risco_por_trade", 0.03))
    max_frac = float(cfg.get("auto_max_valor_frac", 0.25))
    exp_max = float(cfg.get("exposicao_max", 0.5))
    min_valor = 10.0
    margem_aberta = sum((p["valor_reais"] or 0) for p in abertas)
    budget = (banca * exp_max - margem_aberta) if exp_max > 0 else float("inf")
    if banca <= 0 or budget < min_valor:
        res["motivo"] = "sem margem/banca disponível"
        return res

    # 5) cooldown: não reabre ativos fechados há pouco (evita churn abre→fecha→reabre)
    conv_min = float(cfg.get("auto_conviccao_min", cfg.get("min_conviccao", 55)))
    fresh_min = float(cfg.get("auto_freshness_min", 12))
    cooldown_min = float(cfg.get("auto_cooldown_min", 30))
    agora = pd.Timestamp.now()
    corte_cd = str(agora - pd.Timedelta(minutes=cooldown_min))
    with db.conectar() as con:
        em_cooldown = {r["ativo"] for r in con.execute(
            "SELECT DISTINCT ativo FROM trades WHERE fechado_em >= ?", (corte_cd,))}

    def fresco(s):
        try:
            return (agora - pd.Timestamp(s["ts"])).total_seconds() <= fresh_min * 60
        except Exception:
            return False

    def ts_val(s):
        try:
            return pd.Timestamp(s["ts"]).value
        except Exception:
            return 0

    exige_fluxo = _verdade(cfg.get("exigir_fluxo", "1"))
    novos = db.listar("sinais", 80, "WHERE status='novo'")
    cands = [s for s in novos
             if (s["conviccao"] or 0) >= conv_min
             and s["ativo"] not in ativos_abertos
             and s["ativo"] not in em_cooldown
             and fresco(s)
             and not (exige_fluxo and not _fluxo_checado(s))]   # [P2-9] fluxo n/d: o bot nao opera
    cands.sort(key=lambda s: (-(s["conviccao"] or 0), -ts_val(s)))   # melhor convicção; empate -> mais fresco

    vistos = set()
    for s in cands:
        if slots <= 0 or budget < min_valor:
            break
        if s["ativo"] in vistos:                          # 1 entrada por ativo por ciclo
            continue
        lev = _alavancagem(cfg, s["conviccao"])           # alavancagem ∝ convicção (ou fixa)
        valor = _tamanho(banca, risco_frac, lev, s["preco"], s["stop_sugerido"], max_frac)
        if valor <= 0:                                    # banca não comporta: pula
            continue
        valor = min(valor, round(budget, 2))              # não passa do teto de margem restante
        if valor < min_valor:
            break
        try:
            pid = simulador.abrir(s["id"], valor, lev)
            res["abertos"].append({"ativo": s["ativo"], "direcao": s["direcao"], "tf": s.get("tf"),
                                   "valor": valor, "lev": lev, "conviccao": s["conviccao"] or 0, "pid": pid})
            vistos.add(s["ativo"])
            slots -= 1
            budget -= valor
            with db.conectar() as con:                    # consome os outros 'novo' do ativo (anti-churn)
                con.execute("UPDATE sinais SET status='pulado' WHERE ativo=? AND status='novo' AND id<>?",
                            (s["ativo"], s["id"]))
        except ValueError as e:
            res["rejeitados"].append({"ativo": s["ativo"], "erro": str(e)})
            if "teto" in str(e) or "trava" in str(e):     # teto/trava: nao adianta tentar mais nesse ciclo
                break
        except Exception as e:                            # rede/etc: pula o candidato, não derruba o ciclo
            res["rejeitados"].append({"ativo": s["ativo"], "erro": f"falha: {e}"})
            log(f"auto-trader abrir erro {s['ativo']}: {e}", "error")
            continue

    if res["abertos"] or res["fechados"]:
        log(f"auto-trader: +{len(res['abertos'])} aberto(s), {len(res['fechados'])} fechado(s)")
    return res
