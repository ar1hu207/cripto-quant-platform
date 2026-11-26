"""
Modo DCA (Dollar-Cost Averaging) — acumulação periódica de cripto, SEM alavancagem,
SEM stop. A pesquisa (BASE-CONHECIMENTO §5.8) mostrou que DCA disciplinado supera o
trade ativo do varejo: captura o beta do ativo sem tentar adivinhar timing nem pagar
o "imposto" de giro/taxas. Dinheiro fictício, preço real. Separado da banca de trade.
"""
import math
import re

import pandas as pd

import db
import execucao
import mercado
import simulador
from logbot import log


_PAR = re.compile(r"^[A-Z0-9]{2,15}/[A-Z]{3,5}$")
VALOR_MAX = 1e9            # R$ por aporte: sanidade, não política
FREQ_MAX_DIAS = 3650
SO_PAPEL = "o DCA é simulação e esta conta opera em corretora: nenhuma moeda seria comprada"


def _so_no_papel():
    """[LIVE-6] O DCA soma unidades numa tabela e não compra nada. Na conta que opera em
    corretora ele poria "acumulado" de uma moeda que nunca foi comprada ao lado de posições que
    existem de verdade, com o painel dizendo "compra spot". Enquanto não houver DCA com ordem
    real (fora do PLANO-LIVE), ele não cria plano nem aporta nessa conta."""
    if execucao.real():
        raise ValueError(SO_PAPEL)


def criar(ativo, valor_aporte, freq_dias):
    _so_no_papel()
    # Validação aqui, e não só na rota: `aportar()` confia no plano gravado. Valor negativo ou
    # NaN viraria unidades negativas/NaN no acumulado; `freq_dias` 0 aportava a cada ciclo do
    # worker (15 s); e um par que não existe só falhava depois, a cada ciclo, no preço ao vivo.
    if not isinstance(ativo, str) or not _PAR.match(ativo):
        raise ValueError(f"ativo inválido: {ativo!r} (formato BASE/QUOTE, ex. BTC/USDT)")
    try:
        v, f = float(valor_aporte), float(freq_dias)
    except (TypeError, ValueError):
        raise ValueError("valor do aporte e frequência precisam ser números")
    # Teto, além do piso: dois aportes de 1e308 somam `inf` em `total_investido`, o JSON não
    # serializa `inf` e o `/estado` passava a responder 500 para sempre (sem ele o painel nem
    # mostra o plano para removê-lo).
    if not (math.isfinite(v) and 0 < v <= VALOR_MAX):
        raise ValueError(f"valor do aporte precisa estar entre 0 e {VALOR_MAX:,.0f}".replace(",", "."))
    if not (math.isfinite(f) and 1 <= f <= FREQ_MAX_DIAS):
        raise ValueError(f"frequência precisa estar entre 1 e {FREQ_MAX_DIAS} dias")
    # O formato não basta: "XYZ/USDT" casa com a regex e não existe. O plano nascia, falhava no
    # preço a cada ciclo do worker para sempre, e ainda derrubava a cotação em lote dos outros
    # planos (ver `mercado._buscar_tickers`). `None` = a tabela de mercados ainda não foi lida
    # (sem rede desde o start): aí não dá para saber, e o plano passa como passava.
    if mercado.par_listado(ativo) is False:
        raise ValueError(f"o par {ativo} não existe na Binance spot")
    with db.conectar() as c:
        c.execute("INSERT INTO dca(ativo,valor_aporte,freq_dias,unidades,total_investido,"
                  "n_aportes,ultimo_aporte,criado_em,status) VALUES(?,?,?,0,0,0,?,?, 'ativo')",
                  (ativo, float(valor_aporte), float(freq_dias),
                   "1970-01-01 00:00:00", str(pd.Timestamp.now())))   # aporta no 1o ciclo
    log(f"DCA plano criado: {ativo} R${valor_aporte}/{freq_dias}d")
    return True


def aportar(plano):
    """Executa 1 aporte (compra valor_aporte do ativo no preço ao vivo, acumula unidades)."""
    _so_no_papel()
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
    if execucao.real():       # [LIVE-6] plano criado no papel não aporta depois que a conta sai dele;
        return                # e não é erro de plano: sem este retorno o log ganharia uma linha por ciclo
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
    """True se havia um plano ATIVO com esse id. Devolvia True sempre, e a rota respondia
    `{"ok": true}` para um id que nunca existiu."""
    with db.conectar() as c:
        return c.execute("UPDATE dca SET status='removido' WHERE id=? AND status='ativo'",
                         (pid,)).rowcount == 1
