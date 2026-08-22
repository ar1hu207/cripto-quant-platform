"""
Modo DCA (Dollar-Cost Averaging) — acumulação periódica de cripto, SEM alavancagem,
SEM stop. A pesquisa (BASE-CONHECIMENTO §5.8) mostrou que DCA disciplinado supera o
trade ativo do varejo: captura o beta do ativo sem tentar adivinhar timing nem pagar
o "imposto" de giro/taxas. Dinheiro fictício, preço real. Separado da banca de trade.
"""
import pandas as pd

import db
import mercado
import simulador
from logbot import log


def criar(ativo, valor_aporte, freq_dias):
    with db.conectar() as c:
        c.execute("INSERT INTO dca(ativo,valor_aporte,freq_dias,unidades,total_investido,"
                  "n_aportes,ultimo_aporte,criado_em,status) VALUES(?,?,?,0,0,0,?,?, 'ativo')",
                  (ativo, float(valor_aporte), float(freq_dias),
                   "1970-01-01 00:00:00", str(pd.Timestamp.now())))   # aporta no 1o ciclo
    log(f"DCA plano criado: {ativo} R${valor_aporte}/{freq_dias}d")
    return True


def aportar(plano):
    """Executa 1 aporte (compra valor_aporte do ativo no preço ao vivo, acumula unidades)."""
    pid = plano["id"] if isinstance(plano, dict) else plano
    with db.conectar() as c:                                   # leitura curta: so pega o plano
        p = c.execute("SELECT * FROM dca WHERE id=? AND status='ativo'", (pid,)).fetchone()
    if not p:
        return None
    preco = simulador.preco_ao_vivo(p["ativo"])                # rede FORA da conexao
    if not preco:
        return None
    unid = p["valor_aporte"] / preco
    with db.conectar() as c:                                   # escrita curta: so o UPDATE
        cur = c.execute("UPDATE dca SET unidades=unidades+?, total_investido=total_investido+?, "
                        "n_aportes=n_aportes+1, ultimo_aporte=? WHERE id=? AND status='ativo'",
                        (unid, p["valor_aporte"], str(pd.Timestamp.now()), pid))
        if not cur.rowcount:      # o plano saiu do ar durante a viagem de rede: nada foi aportado,
            return None           # e o log nao pode dizer que foi
    log(f"DCA aporte #{pid} {p['ativo']} R${p['valor_aporte']} @ {preco} (+{unid:.6f} un)")
    return preco


def processar_devidos():
    """Worker: executa aportes vencidos (agora - ultimo_aporte >= freq_dias)."""
    agora = pd.Timestamp.now()
    with db.conectar() as c:
        planos = [dict(r) for r in c.execute("SELECT id,ultimo_aporte,freq_dias FROM dca WHERE status='ativo'")]
    for p in planos:
        try:
            if (agora - pd.Timestamp(p["ultimo_aporte"])).total_seconds() >= p["freq_dias"] * 86400:
                aportar(p["id"])
        except Exception as e:
            log(f"DCA erro plano {p['id']}: {e}", "error")


def listar():
    """Planos ativos com valor atual + P&L (preço médio, valor de mercado)."""
    with db.conectar() as c:
        planos = [dict(r) for r in c.execute("SELECT * FROM dca WHERE status='ativo' ORDER BY id")]
    ativos = sorted({p["ativo"] for p in planos if p["unidades"]})
    try:
        cotacao = mercado.precos(ativos) if ativos else {}     # 1 request pelos N planos, cache de 5s
    except Exception:
        cotacao = {}
    out = []
    for p in planos:
        preco = (cotacao.get(p["ativo"]) or 0.0) if p["unidades"] else 0.0
        valor = p["unidades"] * preco
        inv = p["total_investido"]
        out.append({**p,
                    "preco_atual": round(preco, 6),
                    "preco_medio": round(inv / p["unidades"], 6) if p["unidades"] else 0,
                    "valor_atual": round(valor, 2),
                    "pnl": round(valor - inv, 2),
                    "pnl_pct": round((valor / inv - 1) * 100, 2) if inv else 0})
    return out


def remover(pid):
    with db.conectar() as c:
        c.execute("UPDATE dca SET status='removido' WHERE id=?", (pid,))
    return True
