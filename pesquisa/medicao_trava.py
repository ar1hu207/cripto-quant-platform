"""[trava] Mede a trava diaria: o que os sinais barrados depois da trava teriam dado com o vivo.

Uso (da RAIZ, como todo o pacote):

    python -m pesquisa.medicao_trava <backup-do-trading.db>

O backup vem do blob diario (`RUNBOOK-VM.md` §6) -- nunca `cp` do banco vivo (CLAUDE.md §1).
As velas de 1m do SPOT da Binance (a fonte do `preco_ao_vivo` do bot) sao baixadas uma vez para
`pesquisa/dados_cache/trava_velas1m/`, que e cache ignorado pelo git.

Replica, minuto a minuto, o que `autotrader.auto_executar` + `simulador` fariam SEM a trava, nas
janelas em que ela estava ativa (do disparo ate a virada do dia). O livro real (posicoes que ja
estavam abertas) entra como restricao: ocupa slot, ativo, margem e risco. Politica de hoje:
post-only a 0,10% com TTL 1h, 10x fixo, 3% de risco, trailing 3R/3R, maker 0,02% na entrada,
taker 0,05% na saida.

Antes de medir, VALIDA o simulador contra o que producao fez de verdade:
  (1) ordens: o preenchimento simulado bate com o status real?
  (2) posicoes: o desfecho simulado (motivo e P&L) bate com o trade real?
Resultado de 2026-09-24 e leitura: `MEDICAO-TRAVA-2026-09-24.md`.
"""

import json, os, sqlite3, sys, time, urllib.request
from collections import defaultdict
import numpy as np
import pandas as pd

VELAS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados_cache", "trava_velas1m")
con = None

def Q(sql, a=()):
    return [dict(r) for r in con.execute(sql, a)]

INICIO_3R = pd.Timestamp("2026-09-09 23:09:21")
FIM_DADO = pd.Timestamp("2026-09-24 03:10")
CONV_MIN, FRESH_MIN, COOLDOWN_MIN = 60.0, 12, 30
MAX_POS, RISCO, MAX_FRAC, EXP_MAX, RISCO_AB_MAX = 5, 0.03, 0.25, 0.5, 0.10
LEV, OFF, TTL_MIN = 10.0, 0.0010, 60
T_MAKER, T_TAKER = 0.0002, 0.0005
ARMA_R = DIST_R = 3.0
LIQ = 0.9

# ------------------------------------------------------------------ velas
VELAS = {}
def velas(ativo):
    if ativo not in VELAS:
        df = pd.read_parquet(os.path.join(VELAS_DIR, ativo.replace("/", "") + ".parquet"))
        df = df.set_index("t").sort_index()
        VELAS[ativo] = df
    return VELAS[ativo]

def barra(ativo, t):
    """Vela de 1m que CONTEM o instante t (floor)."""
    df = velas(ativo)
    k = t.floor("min")
    return df.loc[k] if k in df.index else None

# ------------------------------------------------------------------ motor de posicao
def gerir(ativo, d, entrada, stop0, t_ini, t_fim=FIM_DADO):
    """Anda de vela em vela a partir do minuto SEGUINTE ao fill. Stop antes do trailing dentro
    da vela (lado conservador). Saida no stop; se a vela ABRE alem do stop, sai na abertura (gap)."""
    df = velas(ativo)
    R = abs(entrada - stop0)
    stop = stop0
    liq = entrada * (1 - d * LIQ / LEV)
    seg = df.loc[t_ini.floor("min") + pd.Timedelta(minutes=1): t_fim]
    for t, v in seg.iterrows():
        o, h, l = v["o"], v["h"], v["l"]
        adverso = l if d == 1 else h
        if (d == 1 and adverso <= stop) or (d == -1 and adverso >= stop):
            px = stop
            if (d == 1 and o < stop) or (d == -1 and o > stop):
                px = o                                          # abriu alem do stop
            if (d == 1 and px <= liq) or (d == -1 and px >= liq):
                px = liq
            motivo = "trailing" if (d == 1 and stop >= entrada) or (d == -1 and stop <= entrada) else "stop"
            return motivo, px, t
        fav = h if d == 1 else l
        if d == 1 and fav >= entrada + ARMA_R * R:
            stop = max(stop, fav - DIST_R * R)
        elif d == -1 and fav <= entrada - ARMA_R * R:
            stop = min(stop, fav + DIST_R * R)
    ult = seg.iloc[-1]["c"] if len(seg) else entrada
    return "aberta", ult, seg.index[-1] if len(seg) else t_ini

def pnl(valor, d, entrada, saida):
    return valor * LEV * d * (saida / entrada - 1) - (T_MAKER + T_TAKER) * valor * LEV

def encheu(ativo, d, limite, t_criada):
    df = velas(ativo)
    seg = df.loc[t_criada.floor("min") + pd.Timedelta(minutes=1): t_criada + pd.Timedelta(minutes=TTL_MIN)]
    for t, v in seg.iterrows():
        if (d == 1 and v["l"] <= limite) or (d == -1 and v["h"] >= limite):
            return t
    return None


# ------------------------------------------------------------------ download
INI_LOCAL = pd.Timestamp("2026-09-09 20:00")
FIM_LOCAL = pd.Timestamp("2026-09-24 03:30")
TZ = pd.Timedelta(hours=3)                       # banco = hora de SP naive; kline = UTC


def ms(ts_local):
    return int((ts_local + TZ).value // 10**6)


def baixar(DB, OUT):
    """Baixa (uma vez) as velas de 1m dos ativos do periodo."""
    os.makedirs(OUT, exist_ok=True)
    con = sqlite3.connect(DB)
    ativos = sorted({r[0] for r in con.execute(
        "SELECT DISTINCT ativo FROM sinais WHERE ts >= '2026-09-09' UNION SELECT DISTINCT ativo FROM trades "
        "WHERE fechado_em >= '2026-09-09'")})
    print(len(ativos), "ativos")
    for a in ativos:
        arq = os.path.join(OUT, a.replace("/", "") + ".parquet")
        if os.path.exists(arq):
            continue
        sym = a.replace("/", "")
        ini, fim, linhas = ms(INI_LOCAL), ms(FIM_LOCAL), []
        while ini < fim:
            url = (f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1m"
                   f"&startTime={ini}&endTime={fim}&limit=1000")
            with urllib.request.urlopen(url, timeout=30) as r:
                lote = json.loads(r.read())
            if not lote:
                break
            linhas += lote
            ini = lote[-1][0] + 60_000
            time.sleep(0.15)
        df = pd.DataFrame([l[:5] for l in linhas], columns=["t", "o", "h", "l", "c"]).astype(float)
        df["t"] = pd.to_datetime(df["t"], unit="ms") - TZ     # volta para hora de SP, como o banco
        df.to_parquet(arq)
        print(a, len(df), df["t"].min(), df["t"].max())


def medir():
    # ================================================================== VALIDACAO
    print("=" * 78)
    print("VALIDACAO 1 -- preenchimento de ordem (sim x producao), desde", INICIO_3R)
    ords = Q("SELECT * FROM ordens WHERE criada_em >= ? ORDER BY id", (str(INICIO_3R),))
    bate = tot = 0
    matriz = defaultdict(int)
    for o in ords:
        if o["status"] == "cancelada":
            continue                      # cancelada pela trava no preenchimento: nao ha verdade
        d = 1 if o["direcao"] == "LONG" else -1
        tf = encheu(o["ativo"], d, o["preco_limite"], pd.Timestamp(o["criada_em"]))
        sim = "preenchida" if tf is not None else "expirada"
        matriz[(o["status"], sim)] += 1
        tot += 1
        bate += (sim == o["status"])
    print(f"   {bate}/{tot} batem ({bate/tot:.0%})   matriz (real, sim): {dict(matriz)}")

    print("\nVALIDACAO 2 -- desfecho da posicao (sim x producao), trades nao-manuais")
    trs = Q("""SELECT t.*, p.stop_abertura FROM trades t LEFT JOIN posicoes p
               ON p.sinal_id = t.sinal_id AND p.aberto_em = t.aberto_em
               WHERE t.aberto_em >= ? ORDER BY t.id""", (str(INICIO_3R),))
    linhas = []
    for t in trs:
        if t["motivo_saida"] == "manual" or not t["risco_abertura"]:
            continue
        d = 1 if t["direcao"] == "LONG" else -1
        ra = t["risco_abertura"]
        stop0 = t["entrada"] - d * ra / (t["valor_reais"] * t["alavancagem"]) * t["entrada"]
        m, px, tt = gerir(t["ativo"], d, t["entrada"], stop0, pd.Timestamp(t["aberto_em"]))
        lev_real = t["alavancagem"]
        p_sim = t["valor_reais"] * lev_real * d * (px / t["entrada"] - 1) - (T_MAKER + T_TAKER) * t["valor_reais"] * lev_real
        linhas.append((t["id"], t["ativo"], t["motivo_saida"].split("-")[0], m,
                       round(t["pnl_reais"], 2), round(p_sim, 2), round(t["pnl_reais"] / ra, 2), round(p_sim / ra, 2)))
    df_v = pd.DataFrame(linhas, columns=["id", "ativo", "motivo_real", "motivo_sim", "pnl_real", "pnl_sim", "R_real", "R_sim"])
    print(df_v.to_string(index=False))
    print(f"   motivo bate: {(df_v.motivo_real == df_v.motivo_sim).sum()}/{len(df_v)}"
          f" | soma P&L real {df_v.pnl_real.sum():+.2f} x sim {df_v.pnl_sim.sum():+.2f}"
          f" | corr R {np.corrcoef(df_v.R_real, df_v.R_sim)[0,1]:.3f}")

    # ================================================================== CONTRAFACTUAL
    aud = Q("SELECT ts, valor_novo FROM config_auditoria WHERE chave='trava_dia_em' AND ts >= ? ORDER BY ts",
            (str(INICIO_3R),))
    janelas = [(pd.Timestamp(a["ts"]), pd.Timestamp(a["valor_novo"]) + pd.Timedelta(days=1)) for a in aud]

    trades_all = Q("SELECT * FROM trades")
    pos_abertas = Q("SELECT * FROM posicoes WHERE status='aberta'")
    def livro_real(t):
        """Posicoes REAIS abertas no instante t: (ativo, margem, risco)."""
        out = []
        for x in trades_all:
            if x["aberto_em"] and pd.Timestamp(x["aberto_em"]) <= t < pd.Timestamp(x["fechado_em"]):
                out.append((x["ativo"], x["valor_reais"], x["risco_abertura"] or x["valor_reais"]))
        for x in pos_abertas:
            if pd.Timestamp(x["aberto_em"]) <= t:
                out.append((x["ativo"], x["valor_reais"], x["risco_abertura"] or x["valor_reais"]))
        return out

    def fechados_reais_desde(t0, t):
        return {x["ativo"] for x in trades_all
                if x["fechado_em"] and t0 <= pd.Timestamp(x["fechado_em"]) <= t}

    eq = pd.DataFrame(Q("SELECT ts, banca, equity_total FROM equity WHERE ts >= '2026-09-09'"))
    eq["ts"] = pd.to_datetime(eq["ts"], format="mixed")
    eq = eq.set_index("ts").sort_index()
    def banca_em(t):
        return float(eq.loc[:t].iloc[-1]["banca"])
    def equity_inicio_dia(t):
        dia = eq.loc[str(t.date())]
        return float(dia.iloc[0]["equity_total"])

    sinais = pd.DataFrame(Q("SELECT id, ts, ativo, direcao, conviccao, motivos, preco, stop_sugerido, status "
                            "FROM sinais WHERE ts >= ?", (str(INICIO_3R),)))
    sinais["ts"] = pd.to_datetime(sinais["ts"], format="mixed")

    print("\n" + "=" * 78)
    print("CONTRAFACTUAL -- sinais que o bot teria pego se a trava NAO existisse")
    todas = []
    for ini, fim in janelas:
        fim_dado = min(fim, FIM_DADO)
        cand_all = sinais[(sinais.ts > ini - pd.Timedelta(minutes=FRESH_MIN)) & (sinais.ts < fim_dado)
                          & (sinais.status != "rejeitado_fluxo") & (sinais.conviccao >= CONV_MIN)
                          & ~sinais.motivos.fillna("").str.contains("fluxo n/d")]
        usados, sim_pos, sim_ord, sim_fech = set(), [], [], []   # sim_pos: dicts
        realizado = 0.0
        t = ini.ceil("min")
        while t < fim_dado:
            # ordens -> posicao ou expira
            for o in list(sim_ord):
                if o["t_fill"] is not None and o["t_fill"] <= t:
                    sim_ord.remove(o)
                    m, px, tt = gerir(o["ativo"], o["d"], o["limite"], o["stop"], o["t_fill"])
                    o.update(motivo=m, saida=px, t_saida=tt, pnl=pnl(o["valor"], o["d"], o["limite"], px))
                    sim_pos.append(o)
                elif o["t_fill"] is None and t >= o["t_criada"] + pd.Timedelta(minutes=TTL_MIN):
                    sim_ord.remove(o)
                    o.update(motivo="expirou", pnl=0.0)
                    sim_fech.append(o)
            # posicoes que ja fecharam liberam slot e contam no realizado
            for p in list(sim_pos):
                if p["motivo"] != "aberta" and p["t_saida"] <= t:
                    sim_pos.remove(p); sim_fech.append(p); realizado += p["pnl"]
            real = livro_real(t)
            ativos_ocup = {a for a, _, _ in real} | {p["ativo"] for p in sim_pos} | {o["ativo"] for o in sim_ord}
            slots = MAX_POS - len(real) - len(sim_pos) - len(sim_ord)
            if slots > 0:
                banca = banca_em(t) + realizado
                margem = sum(m for _, m, _ in real) + sum(x["valor"] for x in sim_pos + sim_ord)
                budget = banca * EXP_MAX - margem
                teto_r = equity_inicio_dia(t) * RISCO_AB_MAX
                risco_ab = sum(r for _, _, r in real) + sum(x["risco"] for x in sim_pos + sim_ord)
                cool = fechados_reais_desde(t - pd.Timedelta(minutes=COOLDOWN_MIN), t) | \
                       {x["ativo"] for x in sim_fech if x.get("t_saida") is not None
                        and t - pd.Timedelta(minutes=COOLDOWN_MIN) <= x["t_saida"] <= t}
                c = cand_all[(cand_all.ts <= t) & (cand_all.ts > t - pd.Timedelta(minutes=FRESH_MIN))]
                c = c[~c.id.isin(usados) & ~c.ativo.isin(ativos_ocup) & ~c.ativo.isin(cool)]
                c = c.sort_values(["conviccao", "ts"], ascending=[False, False])
                vistos = set()
                for _, s in c.iterrows():
                    if slots <= 0 or budget < 10:
                        break
                    if s.ativo in vistos:
                        continue
                    sd = abs(s.preco - s.stop_sugerido) / s.preco
                    lev = LEV if LEV * sd < 0.8 * LIQ else max(1.0, float(int(0.8 * LIQ / sd)))
                    valor = min(banca * RISCO / min(lev * sd, 1.0), banca * MAX_FRAC)
                    if valor < 10:
                        continue
                    valor = min(valor, budget)
                    b = barra(s.ativo, t)
                    if b is None:
                        continue
                    d = 1 if s.direcao == "LONG" else -1
                    limite = b["c"] * (1 - d * OFF)
                    stop = limite * (1 - d * sd)
                    r_novo = min(valor * lev * sd, valor)
                    if risco_ab + r_novo > teto_r:
                        break                                   # teto de risco: nao adianta tentar mais
                    o = dict(sinal=int(s.id), ativo=s.ativo, d=d, limite=limite, stop=stop, valor=valor,
                             risco=r_novo, conv=s.conviccao, t_criada=t, dia=str(ini.date()),
                             t_fill=encheu(s.ativo, d, limite, t))
                    sim_ord.append(o)
                    usados.add(s.id); vistos.add(s.ativo)
                    cand_all = cand_all[~((cand_all.ativo == s.ativo) & (cand_all.ts <= t) & (cand_all.id != s.id))]
                    slots -= 1; budget -= valor; risco_ab += r_novo
            t += pd.Timedelta(minutes=1)
        # o que ainda esta em ordem/posicao no fim da janela: resolve sem abrir mais nada
        for o in sim_ord:
            if o["t_fill"] is not None:
                m, px, tt = gerir(o["ativo"], o["d"], o["limite"], o["stop"], o["t_fill"])
                o.update(motivo=m, saida=px, t_saida=tt, pnl=pnl(o["valor"], o["d"], o["limite"], px))
            else:
                o.update(motivo="expirou", pnl=0.0)
            sim_fech.append(o)
        sim_fech += sim_pos
        todas += sim_fech

    res = pd.DataFrame(todas)
    real_dia = pd.DataFrame(Q("SELECT substr(fechado_em,1,10) dia, SUM(pnl_reais) pnl, COUNT(*) n "
                              "FROM trades WHERE fechado_em >= ? GROUP BY 1", (str(INICIO_3R),)))
    real_dia = real_dia.set_index("dia")
    print(f"{'dia':>10} {'trava':>6} {'ordens':>6} {'fills':>5} {'W':>3} {'L':>3} {'abertas':>7} "
          f"{'P&L sim R$':>11} {'em R':>6} {'dia real R$':>11}")
    for ini, fim in janelas:
        dia = str(ini.date())
        r = res[res.dia == dia] if len(res) else res
        fills = r[r.motivo != "expirou"] if len(r) else r
        w = int((fills.pnl > 0).sum()) if len(fills) else 0
        l = int((fills.pnl <= 0).sum()) if len(fills) else 0
        ab = int((fills.motivo == "aberta").sum()) if len(fills) else 0
        p = float(fills.pnl.sum()) if len(fills) else 0.0
        rr = p / (banca_em(ini) * RISCO)
        pr = float(real_dia.loc[dia, "pnl"]) if dia in real_dia.index else 0.0
        print(f"{dia:>10} {ini.strftime('%H:%M'):>6} {len(r):>6} {len(fills):>5} {w:>3} {l:>3} {ab:>7} "
              f"{p:>+11.2f} {rr:>+6.2f} {pr:>+11.2f}")
    fills = res[res.motivo != "expirou"]
    print(f"\nTOTAL: {len(res)} ordens, {len(fills)} preenchidas, P&L {fills.pnl.sum():+.2f} R$ "
          f"| motivos: {fills.motivo.value_counts().to_dict()}")
    print(f"maior ganho {fills.pnl.max():+.2f} | maior perda {fills.pnl.min():+.2f}")
    return res


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("uso: python -m pesquisa.medicao_trava <backup-do-trading.db>")
    con = sqlite3.connect(sys.argv[1])
    con.row_factory = sqlite3.Row
    baixar(sys.argv[1], VELAS_DIR)
    medir()
