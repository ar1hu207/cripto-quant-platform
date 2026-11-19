"""
Auto-trader (EXPERIMENTO) — executa trades sozinho no preço real (paper trading).

A cada ciclo do worker: pega os MELHORES sinais novos (maior convicção, ja passaram
pelos portões do scan), dimensiona pelo risco e ABRE a posição automaticamente. Quem
fecha é o stop/trailing do `simulador`; o gestor de saída só fecha sozinho com o
trailing DESLIGADO (`auto_fechar_saida`, passo 1 abaixo) — com ele ligado, que é o vivo,
a recomendação dele vai para o painel (`GET /saidas`) e a decisão é de quem olha.

IMPORTANTE — o objetivo do projeto e LUCRO (`NORTE.md`). A confluência técnica, que e o
que este auto-trader executa, nao mostrou edge na régua ate hoje (walk-forward + DSR ~0,
e o [Q-4] mediu retorno direcional negativo na ENTRADA), e e esta estratégia que sai do
ar quando entrar sinal com evidência. Roda ao vivo porque o log de fill e de markout do
post-only só existe assim (`PLANO-V2` D-2), com o perfil de risco que o dono escolheu
(`api.CONFIG_RACIONAL`, [F-20]), e dentro dos mesmos portões de risco (trava diária +
teto de exposição): experimento CONTROLADO, nao um cassino sem freio.

Liga/desliga: config auto_trade = "1"/"0".
"""
import math

import pandas as pd

import db
import simulador
import tendencia
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


# [P1-11] Fração da distância até a liquidação em que o stop pode viver. 0,8 => a liquidação
# sobra 25% ALÉM do stop (1/0,8). Não é config de usuário e por isso não vai para o banco:
# é margem de engenharia sobre o `LIQ_BUFFER` do simulador, que é o modelo de liquidação.
FOLGA_LIQ = 0.8

# [P1-11] Quantas vezes o cap geométrico apertou a alavancagem, e o último caso. Mora em
# módulo, e não só no retorno do ciclo, porque quem precisa expor isso é o `/status`
# (`api.py` — território T-DECLARACAO, onda 2 do M4), que roda FORA do ciclo do auto-trader e
# não teria como somar os `res` já descartados. Quem for lê-lo lê `autotrader.CAPS_GEOMETRIA`.
CAPS_GEOMETRIA = {"total": 0, "ultimo": None}

# [P2-39] O gêmeo mudo do `CAPS_GEOMETRIA`, e por que ele precisava existir.
#
# `_tamanho` dimensiona por risco (`valor = risco_rs / (lev·sd)`) e depois aplica
# `min(valor, banca·max_frac)`. Quando o stop é apertado o `valor` explode e o cap SEMPRE
# morde — e o risco realizado despenca junto com ele. Medido em produção em 2026-08-24:
# `risco_inicial` entre **R$0,14 e R$83,16** num sistema que declara `risco_por_trade = 3%`
# (~R$39). Variação de ~600x, e nada no log dizia que o teto havia agido: o trade nascia com
# nocional grande e risco ~zero, isto é, **só taxa**.
#
# Isto NÃO aperta nem afrouxa guarda nenhuma — o cap continua exatamente onde estava, e
# `_tamanho` devolve o mesmo número que devolvia. O que muda é que ele para de agir em
# silêncio. É a mesma lição do `[P1-11]`: enquanto o cap geométrico não tinha contador,
# ninguém conseguia responder "quantas vezes isso já agiu?".
#
# `perda_de_risco` é a fração do risco pedido que o cap comeu (0 = não mordeu, 0,99 = o
# trade ficou com 1% do risco configurado). É ela, e não o `total`, que diz se o cap está
# sendo um teto ocasional ou o dimensionador de facto.
CAPS_TAMANHO = {"total": 0, "ultimo": None}


def _stop_dist(entrada, stop):
    """Distância relativa entrada→stop — a MESMA para o sizing e para a alavancagem.

    [P1-11] Vira função porque `_tamanho` e `_alavancagem` têm de concordar sobre a geometria
    do trade: se cada uma calculasse a sua, a garantia "liquidação atrás do stop" valeria com
    um número e a margem seria dimensionada com outro. 0.0 = não há geometria medível (sinal
    sem stop, stop na entrada, entrada degenerada); quem chama decide o que fazer com isso."""
    try:
        if entrada and stop and entrada != stop:
            return abs(float(entrada) - float(stop)) / float(entrada)
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return 0.0


def _cap_geometrico(lev, stop_dist, ativo=None):
    """[P1-11] Teto da alavancagem que mantém a LIQUIDAÇÃO ATRÁS DO STOP.

    A liquidação fica a ~`LIQ_BUFFER/lev` da entrada (`simulador._preco_liquidacao`). Quando
    `stop_dist > LIQ_BUFFER/lev` ela vem ANTES do stop: o stop é inalcançável, a perda é a
    margem inteira e o trade vira binário — medido em 37,2% das barras de INJ 1h a 20x.

    Lê o `LIQ_BUFFER` do `simulador` em vez de repetir 0.9: o número é do modelo de
    liquidação, e uma cópia aqui garantiria divergir dele um dia."""
    if not stop_dist or stop_dist <= 0:                 # sinal sem stop: não há o que medir
        return lev
    lev_geo = FOLGA_LIQ * simulador.LIQ_BUFFER / stop_dist
    if lev_geo >= lev:
        return lev
    capada = max(1.0, float(int(lev_geo)))              # trunca PARA BAIXO: arredondar pra cima
    if capada >= lev:                                   # traria a liquidação de volta pra dentro
        return lev
    CAPS_GEOMETRIA["total"] += 1
    CAPS_GEOMETRIA["ultimo"] = {"ts": str(pd.Timestamp.now()), "ativo": ativo,
                                "lev_conviccao": lev, "lev_efetiva": capada,
                                "stop_dist": round(stop_dist, 6)}
    log(f"lev capada {lev}->{capada} por geometria stop/liq {ativo}")
    return capada


def _lev_por_risco(cfg, stop_dist):
    """[LEV-1] Alavancagem que sai da conta do trade, e não de um número cravado.

    O tamanho já sai do risco: nocional = banca x risco_por_trade / distância-do-stop. Falta
    decidir só QUANTA MARGEM esse nocional prende, e é isso que a alavancagem é aqui. A conta:

        margem por trade = banca x m,   m = exposicao_max / auto_max_posicoes  (0,5/5 = 10%)
        alavancagem      = nocional / margem = risco_por_trade / (stop_dist x m)

    Stop curto pede nocional grande e portanto mais alavancagem; stop largo, menos. Com isso
    todo slot prende a MESMA fatia de margem, e as N posições cabem no teto de exposição em vez
    de uma posição de stop largo comer a margem das outras. `auto_lev_margem_frac` > 0 fixa o
    `m` à mão.

    Arredonda PARA CIMA: para baixo a margem passaria de `m` e o último slot não caberia no
    teto. Quem garante a liquidação atrás do stop continua sendo o `_cap_geometrico`, que vem
    por cima em `_alavancagem` -- e se ele baixar a alavancagem, a margem sobe, e o teto de
    exposição do ciclo (`budget`) segue valendo.

    O que esta conta NÃO faz, dito para não haver ilusão: não muda o P&L em reais. O R$ perdido
    no stop e ganho no alvo é `risco_por_trade`; a alavancagem só decide margem e liquidação."""
    risco = float(cfg.get("risco_por_trade", 0.01))
    m = float(cfg.get("auto_lev_margem_frac", 0) or 0)
    if m <= 0:
        expo = float(cfg.get("exposicao_max", 0.5) or 0)
        n = float(cfg.get("auto_max_posicoes", 5) or 0)
        m = expo / n if expo > 0 and n > 0 else 0.10
    lev = math.ceil(risco / (stop_dist * m) - 1e-9)
    return float(max(1, min(lev, float(cfg.get("auto_lev_max", 20)))))


def _alavancagem(cfg, conviccao, stop_dist=None, ativo=None):
    """Alavancagem do trade. Modo 'conviccao': escala LINEAR da convicção mínima (lev_min) até
    100 (lev_max=teto), arredondada e limitada a [lev_min, lev_max]. Modo 'fixo': alavancagem_padrao.
    AVISO: escalar pra cima na convicção assume que convicção prevê acerto — NÃO comprovado (DSR~0).

    [P1-11] Sobre os DOIS modos vem o cap geométrico. Ele vale no modo 'fixo' também porque a
    geometria é física, não artefato da convicção: `alavancagem_padrao=10` com stop de 9,5% é
    tão degenerado quanto 20x por convicção. E ele pode descer ABAIXO de `lev_min` de
    propósito — `lev_min` é o piso da escala de convicção, nunca foi garantia de risco.

    Sem `stop_dist` (chamada antiga, ou sinal sem stop) nada muda: sem geometria não há cap."""
    if cfg.get("auto_lev_modo", "conviccao") == "risco" and stop_dist and stop_dist > 0:
        return _cap_geometrico(_lev_por_risco(cfg, stop_dist), stop_dist, ativo)
    if cfg.get("auto_lev_modo", "conviccao") != "conviccao":
        return _cap_geometrico(float(cfg.get("alavancagem_padrao", 10)), stop_dist, ativo)
    lev_min = float(cfg.get("auto_lev_min", 2))
    lev_max = float(cfg.get("auto_lev_max", 20))
    conv_min = float(cfg.get("auto_conviccao_min", 60))
    conv = conviccao if conviccao is not None else conv_min
    frac = (conv - conv_min) / max(100 - conv_min, 1)
    frac = min(max(frac, 0.0), 1.0)
    lev = lev_min + frac * (lev_max - lev_min)
    lev = float(max(lev_min, min(round(lev), lev_max)))      # inteiro, dentro de [lev_min, teto]
    return _cap_geometrico(lev, stop_dist, ativo)            # [P1-11] a geometria vem por cima


def _tamanho(banca, risco_frac, lev, entrada, stop, max_frac, min_valor=10.0, ativo=None):
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
    sd = _stop_dist(entrada, stop)              # [P1-11] a mesma geometria que capa a alavancagem
    denom = min(lev * sd, 1.0) if sd else 1.0   # se a liquidação vem antes do stop, risco=valor (denom=1)
    valor = risco_rs / denom if denom > 0 else risco_rs
    if valor < min_valor:                       # [P2-8] piso: FILTRA o sinal, não infla o risco
        return 0.0
    if valor > cap:                             # [P2-39] o cap vai morder: registra ANTES de aplicar
        CAPS_TAMANHO["total"] += 1
        CAPS_TAMANHO["ultimo"] = {
            "ts": str(pd.Timestamp.now()), "ativo": ativo,
            "valor_pedido": round(valor, 2), "valor_efetivo": round(cap, 2),
            "risco_pedido": round(risco_rs, 2),
            "risco_efetivo": round(cap * denom, 2),
            # quanto do risco configurado o teto comeu. 0,99 = o trade ficou com 1% dele.
            "perda_de_risco": round(1 - (cap / valor), 4)}
        log(f"tamanho capado R${valor:.2f}->R${cap:.2f} por max_frac {ativo} "
            f"(risco R${risco_rs:.2f}->R${cap * denom:.2f})")
    valor = min(valor, cap)                     # cap (>= min_valor, garantido acima)
    return round(valor, 2)


def _fracao_agitacao(cfg, s):
    """[AG-2] Fração do `risco_por_trade` com que este sinal abre: 1,0 ou `auto_agitacao_frac`.

    Com `auto_agitacao_corte` > 0, o sinal de tendência cujo `atr_rel` (`signal_engine._agitacao`:
    ATR do sinal contra a mediana dos sinais anteriores do mesmo ativo) é >= corte abre com o
    risco multiplicado pela fração. 0 = desligado, e é como nasce.

    A causa que ele ataca: o motor arrisca o MESMO tanto em todo sinal, e o resultado não é o
    mesmo. Medido em 18/11 nos trades da regra de produção (15m/30m/1h), com a razão calculada
    só com sinais anteriores: o terço mais agitado rendeu −0,14R por trade em 2023-26 e −0,11R
    em 2020-22, o mais calmo +0,23R e +0,06R; a diferença tem IC de 95% fora do zero nas duas
    janelas e o mesmo sentido em 6 de 7 anos (2026 inverteu). Só 23% e 29% dos 5% melhores
    trades estavam no terço agitado, então meio tamanho ali corta pouco da cauda que paga a
    conta. O corte desse terço foi 1,18.

    O que ele NÃO é: remédio de dia lateral. A pergunta que o originou foi essa, e a resposta
    medida foi que o "caixote" não tem memória (o que as últimas 6/12/24h foram não avisa as
    próximas) e que reduzir dentro dele inverte de sinal entre as janelas. Nos 10% piores dias
    esta regra corta ~20% da perda, pouco mais que reduzir tudo por igual; em 17/11 os três
    SHORTs stopados estavam CALMOS (0,75, 0,77 e 1,08) e passariam inteiros.

    Só reduz: fração fora de (0, 1] deixa a regra inerte em vez de inflar ou zerar o risco, e
    o catálogo do `POST /config` já recusa esse valor na entrada. Sem `atr_rel` (menos de 30
    sinais anteriores, ou sinal anterior à coluna) o sinal abre inteiro: ausência de medição
    não é bandeira. Reversão fica de fora -- a medida foi feita só na tendência.

    A versão-sintoma, que não foi feita: um detector de dia lateral reduzindo o tamanho. É a
    quinta forma dessa ideia, e as cinco caíram fora da amostra."""
    corte = simulador._cfg_float(cfg, "auto_agitacao_corte", 0.0)
    if corte <= 0 or s.get("tipo") != "tendencia":
        return 1.0
    try:
        rel = float(s.get("atr_rel"))
    except (TypeError, ValueError):
        return 1.0
    if not rel >= corte:                        # NaN cai aqui: comparação falsa, sinal inteiro
        return 1.0
    frac = simulador._cfg_float(cfg, "auto_agitacao_frac", 0.5)
    return frac if 0 < frac <= 1 else 1.0


ESTICADO_MEIO = 0.5


def _esticado(modo, corte, s):
    """[EST-1] `(fração do risco, ret7)` para este sinal: 1,0 (abre inteiro), 0,5 (meio) ou
    0,0 (veto). Levanta se o diário não vier -- quem chama pula o sinal no ciclo.

    Vale só para SHORT de tendência, e só com `auto_esticado_modo` em `meio` ou `veto`: quando
    o retorno dos últimos 7 dias FECHADOS do ativo (`tendencia.contexto`, a mesma conta que o
    [CD-1] grava em `sinais.ret7_d1`) é <= `auto_esticado_ret7` (−10%).

    A causa que ele ataca: a entrada de tendência vende rompimento de suporte do gráfico de
    15m/30m/1h, e esse gráfico não sabe que o diário já caiu 15% na semana. Vendido ali, o
    trade é o último da fila de vendedores e o primeiro a apanhar no repique -- 17/11 e 18/11
    foram isso (BNB e SUI stopados nas três contas). Medido em 19/11 (T54) nos trades da regra
    de produção: SHORT com 7d <= −10% rendeu −0,344R por trade em 2023-26 [−0,597; −0,060] e
    −0,395R em 2020-22 [−0,622; −0,178]. O LONG esticado para cima NÃO é pior, então a regra
    não é simétrica de propósito.

    O outro lado, e é por isso que existe `meio` e não só `veto`: ao vivo, de 02/11 a 18/11,
    esses mesmos SHORTs renderam +20,7R na conta A e +7,2R na B (−4,7R na C) -- novembro foi
    uma queda que continuou --, e em 2026 o histórico fica perto de zero (−0,04R). Vetar teria
    tirado o lucro do mês; meio tamanho paga metade da conta nos dois cenários.

    Reversão fica de fora: a medida foi feita só na tendência. `ret7` ausente (moeda com menos
    de 8 dias de diário) abre inteiro: ausência de medição não é bandeira.

    A versão-sintoma, que não foi feita: baixar `risco_por_trade` ou ligar um filtro macro
    (DXY, S&P, petróleo -- o T27 reprovou os 15 filtros e os 8 gatilhos). A primeira encolhe
    toda venda, inclusive a que vende o topo; a segunda não separou nada."""
    if modo not in ("meio", "veto") or str(s.get("direcao") or "").upper() != "SHORT" \
            or s.get("tipo") != "tendencia":
        return 1.0, None
    r7 = tendencia.contexto(s["ativo"]).get("ret7")
    if r7 is None or not r7 <= corte:
        return 1.0, r7
    return (0.0 if modo == "veto" else ESTICADO_MEIO), r7


def _entradas_recentes(agora, janela_min):
    """[RAJ-1] Quantas entradas nasceram em cada lado nos últimos `janela_min` minutos.

    Conta a DECISÃO de entrar, e por isso lê duas fontes:
      * `ordens` pendentes ou preenchidas, pelo `criada_em` -- em `post_only` a ordem é o
        instante em que o bot decidiu; a posição nasce segundos ou minutos depois, e contar
        pelo preenchimento deixaria três ordens colocadas no mesmo ciclo passarem juntas;
      * `posicoes` que NÃO vieram de ordem (entrada a mercado), pelo `aberto_em`.
    Posição já FECHADA continua contando, de propósito: em 17/11 o stop bateu 18 minutos
    depois da entrada, e uma rajada cujos stops já bateram ainda é a mesma rajada. Ordem
    expirada ou cancelada não conta -- nunca virou exposição. Entrada manual conta: o teto
    só barra o bot, mas o que o dono abriu à mão é aposta no mesmo lado do mesmo jeito.

    O comparador é string, como no cooldown: `criada_em`/`aberto_em` são `str(pd.Timestamp)`
    naive de São Paulo (CLAUDE.md §1) e o formato ISO ordena lexicograficamente."""
    corte = str(agora - pd.Timedelta(minutes=janela_min))
    n = {"LONG": 0, "SHORT": 0}
    with db.conectar() as con:
        linhas = list(con.execute(
            "SELECT direcao, COUNT(*) AS n FROM ordens "
            "WHERE status IN ('pendente','preenchida') AND criada_em >= ? GROUP BY direcao", (corte,)))
        linhas += list(con.execute(
            "SELECT direcao, COUNT(*) AS n FROM posicoes WHERE aberto_em >= ? "
            "AND id NOT IN (SELECT posicao_id FROM ordens WHERE posicao_id IS NOT NULL) "
            "GROUP BY direcao", (corte,)))
    for r in linhas:
        lado = str(r["direcao"] or "").upper()
        n[lado] = n.get(lado, 0) + r["n"]
    return n


def auto_executar(saidas=None):
    """Roda 1 ciclo do auto-trader. `saidas` = lista do avaliar_saida (pra auto-fechar).
    Retorna resumo das ações (pra UI/log). Sem efeito se auto_trade desligado."""
    cfg = db.get_config()
    if not _verdade(cfg.get("auto_trade", "0")):
        return {"ativo": False}

    res = {"ativo": True, "abertos": [], "fechados": [], "rejeitados": [],
           "caps_geometria": 0, "ts": str(pd.Timestamp.now())}
    caps_antes = CAPS_GEOMETRIA["total"]              # [P1-11] quantos caps ESTE ciclo produziu
    capt_antes = CAPS_TAMANHO["total"]                # [P2-39] idem, para o teto de tamanho

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
    # [EX-1] Ordem pendente ocupa vaga, ativo e margem como se já fosse posição -- a mesma regra
    # que os tetos do `simulador` aplicam (CLAUDE.md §2, regra 1). Sem ela, em `post_only` o bot
    # colocava uma ordem por ciclo no mesmo ativo e passava do `auto_max_posicoes` quando elas
    # enchiam juntas; o teto de risco não pega isso, porque cada ordem cabe sozinha nele.
    abertas = (db.listar("posicoes", 200, "WHERE status='aberta'")
               + db.listar("ordens", 200, "WHERE status='pendente'"))
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

    modo_tend = str(cfg.get("tendencia_filtro", "off") or "off").strip().lower()
    res["contra_tendencia"] = []
    # [RAJ-1] Teto de rajada: no máximo `auto_rajada_max` entradas do MESMO lado dentro de
    # `auto_rajada_janela_min` minutos. 0 = desligado, e é como nasce.
    #
    # A causa que ele ataca: os sinais de vários ativos disparam JUNTOS, porque leem a mesma
    # vela do mesmo mercado (T42: 24 ativos são ~2 apostas, e na queda a correlação quase dobra). Em
    # 17/11 quatro SHORTs de rompimento saíram em 14 minutos, na vela que fez a mínima da manhã;
    # cada um cabia sozinho em todos os tetos, e os três stops somaram a trava do dia. Nenhuma
    # guarda via que eram a mesma informação contada quatro vezes -- `auto_max_posicoes` conta
    # vagas e `risco_aberto_max` soma risco, mas nenhum dos dois olha QUANDO.
    #
    # NÃO é o teto por direção, que o T12 e o histórico de setembro reprovaram: aquele limita
    # quantas posições do mesmo lado ficam abertas, e corta o dia de tendência, que é onde o
    # motor ganha. Este limita o ritmo: passada a janela o lado abre de novo, e uma tendência
    # que continua dando sinal continua sendo operada.
    #
    # NÃO FOI MEDIDO. Nasce desligado porque é hipótese tirada de um dia ruim, e regra ajustada
    # a um dia ruim é o que a casa não liga sem régua. A versão-sintoma seria baixar
    # `auto_max_posicoes` ou afrouxar `limite_perda_dia`: a primeira corta a tendência junto com
    # a rajada, a segunda remove o freio que segurou o dia.
    #
    # O sinal barrado NÃO é consumido (segue 'novo'), como no [TD-1], e a vaga vai para o
    # próximo candidato -- que pode ser do outro lado. A janela padrão (30 min) passa de
    # `auto_freshness_min` (12) em 18 minutos: um sinal barrado por entradas da mesma vela de
    # 15m, ou da anterior, envelhece antes de a janela abrir, então barrar não vira "entrar
    # atrasado no mesmo movimento". Barrado por entrada mais antiga que isso, ele ainda abre
    # quando a janela andar: é teto de ritmo, não veto.
    rajada_max = int(simulador._cfg_float(cfg, "auto_rajada_max", 0.0))
    rajada = (_entradas_recentes(agora, simulador._cfg_float(cfg, "auto_rajada_janela_min", 30.0))
              if rajada_max > 0 else None)
    res["rajada"] = []
    res["agitacao"] = []                              # [AG-2] quem abriu com o risco reduzido
    # [EST-1] Venda com o diário já esticado para baixo. Ver `_esticado`.
    modo_est = str(cfg.get("auto_esticado_modo", "off") or "off").strip().lower()
    corte_est = simulador._cfg_float(cfg, "auto_esticado_ret7", -10.0)
    res["esticado"] = []                              # [EST-1] {ativo, ret7, acao: veto|meio}
    vistos = set()
    for s in cands:
        if slots <= 0 or budget < min_valor:
            break
        if s["ativo"] in vistos:                          # 1 entrada por ativo por ciclo
            continue
        lado_s = str(s["direcao"] or "").upper()
        if rajada is not None and rajada.get(lado_s, 0) >= rajada_max:
            res["rajada"].append(s["ativo"])
            continue
        # [TD-1] Só a favor da tendência do diário (T38). Dentro do laço, e não na lista de
        # candidatos, para que o slot recusado vá para o próximo sinal -- foi assim que o
        # backtest mediu: o motor enche as vagas com OUTROS candidatos, não com menos trades.
        # Rede falhou: pula no ciclo (o sinal segue 'novo'), nunca abre sem saber o lado.
        if modo_tend != "off":
            try:
                if not tendencia.permite(s["ativo"], s["direcao"], modo_tend):
                    res["contra_tendencia"].append(s["ativo"])
                    continue
            except Exception as e:
                res["rejeitados"].append({"ativo": s["ativo"], "erro": f"tendência n/d: {e}"})
                continue
        # [EST-1] Rede falhou: pula no ciclo, como o [TD-1] -- com a chave ligada, abrir sem
        # saber o diário seria abrir inteira justamente a venda que ela existe para segurar.
        try:
            frac_est, r7 = _esticado(modo_est, corte_est, s)
        except Exception as e:
            res["rejeitados"].append({"ativo": s["ativo"], "erro": f"diário n/d: {e}"})
            continue
        if frac_est == 0.0:                               # veto: o sinal segue 'novo', a vaga anda
            res["esticado"].append({"ativo": s["ativo"], "ret7": r7, "acao": "veto"})
            continue
        # [P1-11] a lev sai da convicção e passa pelo cap geométrico ANTES de dimensionar: a
        # margem tem de ser calculada sobre a alavancagem que vai ser aberta de fato. O
        # `simulador.abrir` recompõe o stop mantendo a distância RELATIVA do sinal (`stop_rel`),
        # então a garantia "liquidação atrás do stop" sobrevive ao preço de entrada ao vivo.
        stop_dist = _stop_dist(s["preco"], s["stop_sugerido"])
        lev = _alavancagem(cfg, s["conviccao"], stop_dist, s["ativo"])
        # [AG-2] O ativo agitado acima do normal dele abre com uma fração do risco. A
        # alavancagem fica a do trade inteiro, de propósito: é o mesmo trade com menos
        # dinheiro, e a geometria stop/liquidação que o `_cap_geometrico` garantiu não muda.
        frac_ag = _fracao_agitacao(cfg, s)
        valor = _tamanho(banca, risco_frac * frac_ag * frac_est, lev, s["preco"], s["stop_sugerido"], max_frac,
                         ativo=s["ativo"])
        if valor <= 0:                                    # banca não comporta: pula
            continue
        # TRUNCA, não arredonda: `round(budget, 2)` subia até meio centavo ACIMA do orçamento, o
        # `abrir()` recusava por "teto de margem" e o `break` abaixo encerrava o ciclo. O sinal
        # seguia 'novo' e a recusa se repetia a cada 15 s até ele expirar.
        valor = min(valor, math.floor(budget * 100) / 100)   # não passa do teto de margem restante
        if valor < min_valor:
            break
        try:
            # [EX-1] O bot tambem passa pelo `executar`: com `exec_modo=post_only` ele COLOCA a
            # ordem e segue. O slot e o budget sao consumidos aqui do mesmo jeito -- a ordem ja
            # conta nos tetos (`simulador._pendentes`), entao tratar pendente como "ainda tem
            # espaco" faria o bot colocar mais ordens do que o teto permite e depois apanhar
            # delas uma a uma no preenchimento.
            # `exige_auto`: o `auto_trade` lido no topo deste ciclo pode ter sido desligado pelo
            # `/panico` enquanto o laço estava na rede; quem confere de novo é o simulador, sob o
            # mesmo lock em que o pânico desliga.
            tipo, ident = simulador.executar(s["id"], valor, lev, exige_auto=True)
            pid = ident if tipo == "posicao" else None
            res["abertos"].append({"ativo": s["ativo"], "direcao": s["direcao"], "tf": s.get("tf"),
                                   "valor": valor, "lev": lev, "conviccao": s["conviccao"] or 0,
                                   "pid": pid, "tipo": tipo, "ordem_id": ident if tipo == "ordem" else None})
            vistos.add(s["ativo"])
            slots -= 1
            budget -= valor
            if rajada is not None:                        # [RAJ-1] a entrada deste ciclo já conta
                rajada[lado_s] = rajada.get(lado_s, 0) + 1
            if frac_ag < 1.0:                             # [AG-2] fica escrito: não age em silêncio
                res["agitacao"].append(s["ativo"])
                log(f"[AG-2] {s['ativo']} agitado (atr_rel {s.get('atr_rel')}): "
                    f"risco x{frac_ag:g}, valor R${valor:.2f}")
            if frac_est < 1.0:                            # [EST-1] idem
                res["esticado"].append({"ativo": s["ativo"], "ret7": r7, "acao": "meio"})
                log(f"[EST-1] {s['ativo']} SHORT com o diário em {r7:+.1f}% em 7d: "
                    f"risco x{frac_est:g}, valor R${valor:.2f}")
            with db.conectar() as con:                    # consome os outros 'novo' do ativo (anti-churn)
                con.execute("UPDATE sinais SET status='pulado' WHERE ativo=? AND status='novo' AND id<>?",
                            (s["ativo"], s["id"]))
        except ValueError as e:
            res["rejeitados"].append({"ativo": s["ativo"], "erro": str(e)})
            if "teto" in str(e) or "trava" in str(e) or "desligado" in str(e):
                break                                     # teto/trava/pânico: o ciclo acabou
        except Exception as e:                            # rede/etc: pula o candidato, não derruba o ciclo
            res["rejeitados"].append({"ativo": s["ativo"], "erro": f"falha: {e}"})
            log(f"auto-trader abrir erro {s['ativo']}: {e}", "error")
            continue

    res["caps_geometria"] = CAPS_GEOMETRIA["total"] - caps_antes
    res["caps_tamanho"] = CAPS_TAMANHO["total"] - capt_antes
    if res["abertos"] or res["fechados"]:
        log(f"auto-trader: +{len(res['abertos'])} aberto(s), {len(res['fechados'])} fechado(s)")
    return res
