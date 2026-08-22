"""
Sprint 0 - Camada de banco de dados (SQLite). Cria o esquema e helpers basicos.
Tabelas: sinais, posicoes, trades, equity, config, banca.
"""
import math
import os
import sqlite3
from contextlib import contextmanager

# caminho do banco: env DB_PATH (ex.: volume /data/trading.db no Railway) ou local
DB = os.environ.get("DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sinais(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, ativo TEXT, tf TEXT, tipo TEXT, direcao TEXT,
  conviccao REAL, motivos TEXT, preco REAL, stop_sugerido REAL,
  status TEXT DEFAULT 'novo',        -- novo|proposto|confirmado|pulado|rejeitado_fluxo
  -- [Q-4] validacao prospectiva do portao de fluxo. 'rejeitado_fluxo' NAO e fila: nenhuma
  -- consulta da fila/auto-trader o enxerga (todas filtram status='novo'). vela_ms e o instante
  -- EXATO em que o preco do sinal foi impresso (fechamento do candle usado) - e a ancora do
  -- contrafactual; sem ele o desfecho comecaria de um preco de ate 1 TF atras.
  vela_ms INTEGER, fluxo_comprador REAL, rejeicao TEXT,
  desfecho TEXT, desfecho_ts TEXT,   -- alvo|stop|aberto (24h sem tocar nenhum dos dois)
  preco_1h REAL, preco_4h REAL, preco_24h REAL);

CREATE TABLE IF NOT EXISTS posicoes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ativo TEXT, direcao TEXT, entrada REAL,
  valor_reais REAL, alavancagem REAL, stop REAL, preco_atual REAL, pnl REAL,
  aberto_em TEXT, status TEXT DEFAULT 'aberta', conviccao REAL, sinal_id INTEGER);

CREATE TABLE IF NOT EXISTS trades(
  id INTEGER PRIMARY KEY AUTOINCREMENT, sinal_id INTEGER, ativo TEXT, direcao TEXT,
  entrada REAL, saida REAL, valor_reais REAL, alavancagem REAL, ret_pct REAL,
  pnl_reais REAL, taxa REAL, motivo_saida TEXT, aberto_em TEXT, fechado_em TEXT, conviccao REAL);

CREATE TABLE IF NOT EXISTS equity(ts TEXT, banca REAL, equity_total REAL);

CREATE TABLE IF NOT EXISTS config(chave TEXT PRIMARY KEY, valor TEXT);

CREATE TABLE IF NOT EXISTS banca(id INTEGER PRIMARY KEY, nome TEXT, inicial REAL, atual REAL);

CREATE TABLE IF NOT EXISTS dca(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ativo TEXT, valor_aporte REAL, freq_dias REAL,
  unidades REAL DEFAULT 0, total_investido REAL DEFAULT 0, n_aportes INTEGER DEFAULT 0,
  ultimo_aporte TEXT, criado_em TEXT, status TEXT DEFAULT 'ativo');  -- acumulacao DCA (sem alavancagem)
"""

CONFIG_PADRAO = {
    "risco_por_trade": "0.03",
    "alavancagem_padrao": "10",
    "timeframe": "15m",                        # TF primário (gráfico + gestor de saída)
    "timeframes": "5m,15m,1h",                 # TFs que o scanner varre (alargamento)
    "ativos": ("BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT,ADA/USDT,DOGE/USDT,AVAX/USDT,"
               "LINK/USDT,LTC/USDT,DOT/USDT,TRX/USDT,ATOM/USDT,NEAR/USDT,UNI/USDT,AAVE/USDT,"
               "APT/USDT,ARB/USDT,OP/USDT,INJ/USDT,FIL/USDT,SUI/USDT,ETC/USDT,BCH/USDT"),
    "limite_perda_dia": "0.05",
    "taxa_por_lado": "0.0005",
    "min_conviccao": "55",     # convicção mínima (confluência geral) — era 20-35, ruído
    "adx_min": "25",           # exige TENDÊNCIA (ADX) — não opera mercado choppy
    "min_fatores": "3",        # exige >=3 confirmações (ADX/rompimento/RSI/volume)
    "exigir_fluxo": "1",       # exige order flow (taker) concordando (só tendência)
    "adx_max_rev": "22",       # ADX MÁXIMO pra reversão (só opera mercado lateral)
    "reversao_ativa": "0",     # reversão DESLIGADA ao vivo (não validou no backtest)
    "risco_aberto_max": "0.10",  # teto da soma do risco-até-o-stop das posições abertas (fração da banca; <=0 = sem teto)
    "exposicao_max": "0.5",      # teto da MARGEM total aberta (soma de valor_reais) como fração da banca (<=0 = sem teto)
    "trava_dia_em": "",          # data em que a trava diária acionou (sticky: não destrava no mesmo dia)
    "alvo_roe": "5",           # ROE% que conta como "bom lucro" pro gestor de saída
    "auto_trade": "0",            # AUTO-TRADER: 1=liga o bot que abre/fecha sozinho (experimento)
    "auto_conviccao_min": "60",   # convicção mínima pro bot operar (mais exigente que a fila manual)
    "auto_max_posicoes": "5",     # máx. de posições abertas simultâneas pelo bot
    "auto_max_valor_frac": "0.25",  # teto do tamanho de UM trade (fração da banca)
    "auto_fechar_saida": "1",     # bot fecha sozinho em reversão com lucro (gestor de saída)
    "auto_freshness_min": "12",   # só opera sinais com até N minutos (price/stop envelhecem)
    "auto_cooldown_min": "30",    # após fechar um ativo, não reabre por N minutos (evita churn)
    "auto_lev_modo": "conviccao", # "conviccao"=alavancagem ∝ convicção (até o teto) | "fixo"=alavancagem_padrao
    "auto_lev_min": "2",          # alavancagem na convicção mínima
    "auto_lev_max": "20",         # TETO de alavancagem (na convicção máxima)
    "trailing_ativo": "1",        # trailing stop: deixa o lucro correr, trava o ganho (sobe o stop atrás do preço)
    "trailing_dist": "0.02",      # distância do trailing (2% atrás do pico) — ativa quando o lucro passa disso
    "telegram_token": "",
    "telegram_chat_id": "",
}


@contextmanager
def conectar():
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")     # leituras concorrentes + 1 escritor (menos 'database is locked')
    con.execute("PRAGMA busy_timeout=30000")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _migrar(c):
    """Adiciona colunas novas a tabelas que já existiam (dev)."""
    faltantes = {"sinais": [("tf", "TEXT"), ("tipo", "TEXT"),
                            ("vela_ms", "INTEGER"), ("fluxo_comprador", "REAL"), ("rejeicao", "TEXT"),
                            ("desfecho", "TEXT"), ("desfecho_ts", "TEXT"),
                            ("preco_1h", "REAL"), ("preco_4h", "REAL"), ("preco_24h", "REAL")],
                 "posicoes": [("conviccao", "REAL"), ("sinal_id", "INTEGER")],
                 "trades": [("conviccao", "REAL"), ("stop", "REAL"),
                            ("risco_inicial", "REAL"), ("funding", "REAL")]}
    for tabela, novas in faltantes.items():
        existentes = {r["name"] for r in c.execute(f"PRAGMA table_info({tabela})")}
        for nome, tipo in novas:
            if nome not in existentes:
                c.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}")


def init_db():
    with conectar() as c:
        c.executescript(SCHEMA)
        _migrar(c)
        if c.execute("SELECT COUNT(*) FROM banca").fetchone()[0] == 0:
            c.execute("INSERT INTO banca(id,nome,inicial,atual) VALUES(1,'principal',1000,1000)")
        for k, v in CONFIG_PADRAO.items():
            c.execute("INSERT OR IGNORE INTO config(chave,valor) VALUES(?,?)", (k, v))


# ---------- helpers ----------
def get_config():
    with conectar() as c:
        return {r["chave"]: r["valor"] for r in c.execute("SELECT * FROM config")}


def set_config(chave, valor):
    with conectar() as c:
        c.execute("INSERT INTO config(chave,valor) VALUES(?,?) "
                  "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, str(valor)))


def get_banca():
    with conectar() as c:
        return dict(c.execute("SELECT * FROM banca WHERE id=1").fetchone())


def listar(tabela, limite=50, where=""):
    with conectar() as c:
        q = f"SELECT * FROM {tabela} {where} ORDER BY rowid DESC LIMIT ?"  # rowid serve p/ toda tabela
        return [dict(r) for r in c.execute(q, (limite,))]


def metricas():
    """Estatísticas pra tunar: win rate, profit factor, e win rate POR convicção."""
    with conectar() as c:
        trades = [dict(r) for r in c.execute("SELECT * FROM trades")]
        bi = c.execute("SELECT inicial FROM banca WHERE id=1").fetchone()
        eq = [r["equity_total"] for r in c.execute("SELECT equity_total FROM equity ORDER BY rowid")]
        eq_diario = [r["e"] for r in c.execute(
            "SELECT MAX(rowid) mr, equity_total e FROM equity GROUP BY substr(ts,1,10) ORDER BY mr")]
    banca_ini = bi["inicial"] if bi else 1000
    base = {"n_trades": 0, "win_rate": 0, "pnl_total": 0, "taxa_total": 0,
            "profit_factor": 0, "ganho_medio": 0, "perda_media": 0, "por_conviccao": [],
            "sqn": 0, "sortino": 0, "sharpe": 0, "max_drawdown": 0, "max_drawdown_pct": 0,
            "max_dd_mtm_pct": 0, "calmar": 0, "expectancia": 0, "expectancia_r": 0, "sqn_r": 0}
    if not trades:
        return base
    wins = [t for t in trades if (t["pnl_reais"] or 0) > 0]
    perdas = [t for t in trades if (t["pnl_reais"] or 0) <= 0]
    soma_g = sum(t["pnl_reais"] for t in wins)
    soma_p = -sum(t["pnl_reais"] for t in perdas)
    faixas = [("80-100", 80, 101), ("60-80", 60, 80), ("40-60", 40, 60), ("0-40", 0, 40)]
    por_conv = []
    for nome, lo, hi in faixas:
        grp = [t for t in trades if lo <= (t.get("conviccao") or 0) < hi]
        if grp:
            gw = sum(1 for t in grp if (t["pnl_reais"] or 0) > 0)
            por_conv.append({"faixa": nome, "n": len(grp), "win_rate": round(gw / len(grp) * 100, 1),
                             "pnl": round(sum(t["pnl_reais"] for t in grp), 2)})
    # --- métricas avançadas (Van Tharp / risco) ---
    pnls = [t["pnl_reais"] or 0 for t in sorted(trades, key=lambda t: t.get("fechado_em") or "")]
    nn = len(pnls)
    media = sum(pnls) / nn
    std = math.sqrt(sum((p - media) ** 2 for p in pnls) / nn)
    cap = math.sqrt(min(nn, 100))                                          # Van Tharp: cap o fator em sqrt(min(n,100))
    sqn = round(media / std * cap, 2) if std > 0 else 0
    neg = [p for p in pnls if p < 0]
    ddv = math.sqrt(sum(p * p for p in neg) / nn) if neg else 0            # downside deviation
    sortino = round(media / ddv * cap, 2) if ddv > 0 else 0
    # R-múltiplos (só trades com risco_inicial gravado — pnl / risco-até-o-stop; isola QUALIDADE do tamanho)
    rmults = [(t["pnl_reais"] or 0) / t["risco_inicial"] for t in trades if t.get("risco_inicial")]
    if rmults:
        mr = sum(rmults) / len(rmults)
        sr = math.sqrt(sum((r - mr) ** 2 for r in rmults) / len(rmults))
        expectancia_r = round(mr, 3)
        sqn_r = round(mr / sr * math.sqrt(min(len(rmults), 100)), 2) if sr > 0 else 0
    else:
        expectancia_r = sqn_r = 0
    # max drawdown da curva REALIZADA (banca_ini + cumsum) — base do Calmar
    cum = peak = banca_ini
    maxdd = maxdd_pct = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        maxdd = max(maxdd, peak - cum)
        maxdd_pct = max(maxdd_pct, (peak - cum) / peak * 100 if peak else 0)   # maior %, independente do abs
    calmar = round(sum(pnls) / maxdd, 2) if maxdd > 0 else 0
    # max drawdown MARK-TO-MARKET (curva de equity real, inclui flutuação de posições abertas)
    dd_mtm = 0.0
    if eq:
        pk = eq[0]
        for v in eq:
            pk = max(pk, v)
            dd_mtm = max(dd_mtm, (pk - v) / pk * 100 if pk else 0)
    # Sharpe (retornos DIÁRIOS da curva de equity, anualizado) — por-período, não por-trade
    sharpe = 0
    if len(eq_diario) >= 3:
        rets = [eq_diario[i] / eq_diario[i - 1] - 1 for i in range(1, len(eq_diario)) if eq_diario[i - 1]]
        if rets:
            m = sum(rets) / len(rets)
            sd = math.sqrt(sum((r - m) ** 2 for r in rets) / len(rets))
            sharpe = round(m / sd * math.sqrt(365), 2) if sd > 0 else 0
    return {
        "n_trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "pnl_total": round(sum(t["pnl_reais"] for t in trades), 2),
        "taxa_total": round(sum(t["taxa"] or 0 for t in trades), 2),
        "profit_factor": round(min(soma_g / soma_p, 999), 2) if soma_p > 0 else 999,
        "ganho_medio": round(soma_g / len(wins), 2) if wins else 0,
        "perda_media": round(-soma_p / len(perdas), 2) if perdas else 0,
        "por_conviccao": por_conv,
        "expectancia": round(media, 2), "expectancia_r": expectancia_r,
        "sqn": sqn, "sqn_r": sqn_r, "sortino": sortino, "sharpe": sharpe,
        "max_drawdown": round(maxdd, 2), "max_drawdown_pct": round(maxdd_pct, 1),
        "max_dd_mtm_pct": round(dd_mtm, 1), "calmar": calmar,
    }


# ---------- [Q-4] validação prospectiva do portão de fluxo ----------
# O portão `exigir_fluxo` só existe ao vivo: não há book/taker histórico, então ele é
# ininvalidável olhando pra trás. A saída é medir pra frente — gravar a rejeição e marcar,
# nos DOIS grupos, o mesmo desfecho hipotético (candle, não fill). Se o rejeitado performa
# igual ou melhor, o portão é ruído; se performa pior, o portão tem valor.

def _erfc_p(z):
    """p-valor bicaudal da normal padrão, sem scipy (a plataforma não tem)."""
    return round(math.erfc(abs(z) / math.sqrt(2)), 4)


def _resumo_grupo(linhas):
    """n, contagem por desfecho, win hipotético e retorno médio por horizonte."""
    n = len(linhas)
    r = {"n": n, "alvo": 0, "stop": 0, "aberto": 0, "win": None,
         "n_resolvido": 0, "ret_1h": None, "ret_4h": None, "ret_24h": None, "fluxo_medio": None}
    if not n:
        return r
    for l in linhas:
        r[l["desfecho"]] = r.get(l["desfecho"], 0) + 1
    r["n_resolvido"] = r["alvo"] + r["stop"]
    if r["n_resolvido"]:
        r["win"] = round(r["alvo"] / r["n_resolvido"] * 100, 1)
    for h in ("1h", "4h", "24h"):
        # retorno assinado pela DIREÇÃO do sinal: um SHORT que caiu é retorno positivo
        rets = [(1 if l["direcao"] == "LONG" else -1) * (l["preco_" + h] / l["preco"] - 1) * 100
                for l in linhas if l.get("preco_" + h) and l.get("preco")]
        if rets:
            r["ret_" + h] = round(sum(rets) / len(rets), 3)
    fl = [l["fluxo_comprador"] for l in linhas if l.get("fluxo_comprador") is not None]
    if fl:
        r["fluxo_medio"] = round(sum(fl) / len(fl), 1)
    return r


def relatorio_fluxo(min_amostra=100):
    """Compara o desfecho hipotético dos sinais de TENDÊNCIA que o portão de fluxo deixou
    passar contra os que ele rejeitou.

    Só entram sinais de `tipo='tendencia'` — a reversão nem chega ao portão (é contrarian,
    `signal_engine.confirmado`), e misturá-la compararia populações diferentes.
    Só entram sinais com desfecho marcado: sem desfecho não há o que comparar.

    NÃO é P&L. É comparação de SINAL: o mesmo contrafactual (stop = a distância do
    `stop_sugerido`, alvo = a mesma distância espelhada = 1R) medido em candle de 5m, sem
    fill, sem taxa e sem funding — nos dois grupos, com a mesma régua.
    """
    with conectar() as c:
        linhas = [dict(r) for r in c.execute(
            "SELECT status,direcao,preco,preco_1h,preco_4h,preco_24h,desfecho,fluxo_comprador "
            "FROM sinais WHERE desfecho IS NOT NULL AND tipo='tendencia'")]
    passou = _resumo_grupo([l for l in linhas if l["status"] != "rejeitado_fluxo"])
    rejeit = _resumo_grupo([l for l in linhas if l["status"] == "rejeitado_fluxo"])

    delta = z = p = None
    if passou["win"] is not None and rejeit["win"] is not None:
        delta = round(passou["win"] - rejeit["win"], 1)
        # teste z de duas proporções sobre os resolvidos (alvo/stop) — só pra dizer se o
        # delta sobrevive ao ruído amostral. Não corrige dependência entre sinais da mesma
        # moeda/hora: é um piso de exigência, não um selo de significância.
        n1, n2 = passou["n_resolvido"], rejeit["n_resolvido"]
        p1, p2 = passou["alvo"] / n1, rejeit["alvo"] / n2
        pool = (passou["alvo"] + rejeit["alvo"]) / (n1 + n2)
        ep = math.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))     # erro padrao da diferenca
        if ep > 0:
            z = round((p1 - p2) / ep, 2)
            p = _erfc_p(z)

    if min(passou["n"], rejeit["n"]) < min_amostra:
        veredito = (f"amostra insuficiente ({passou['n']} passaram / {rejeit['n']} rejeitados; "
                    f"o card pede >={min_amostra} de cada) — nao concluir nada ainda")
    elif delta is None:
        veredito = "sem desfechos resolvidos (todos 'aberto') — contrafactual nao discrimina"
    elif p is not None and p > 0.05:
        veredito = (f"delta {delta:+.1f} p.p. nao se distingue de ruido (p={p}) — "
                    "o portao ainda nao mostrou valor")
    elif delta > 0:
        veredito = f"o portao TEM valor: quem passou acerta {delta:+.1f} p.p. a mais (p={p})"
    else:
        veredito = f"o portao e RUIDO ou pior: quem passou acerta {delta:+.1f} p.p. (p={p})"

    return {"passou": passou, "rejeitado": rejeit, "delta_win": delta, "z": z, "p": p,
            "min_amostra": min_amostra, "veredito": veredito,
            "nota": "comparacao de SINAL (candle, 1R espelhado), nao de P&L; empate na mesma vela conta stop"}



if __name__ == "__main__":
    init_db()
    with conectar() as c:
        tabelas = [r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    print("Banco criado em:", DB)
    print("Tabelas:", tabelas)
    print("Banca:", get_banca())
    print("Config:", get_config())
