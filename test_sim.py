"""Teste do Sprint 2: sinal -> posição -> fechamento com P&L correto."""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import db
import simulador

db.init_db()
banca_ini = db.get_banca()["atual"]
print(f"Banca inicial: R$ {banca_ini:.2f}\n")

# 1) pega o sinal de maior convicção
sig = max(db.listar("sinais", 20), key=lambda x: x["conviccao"])
print(f"1) Sinal escolhido: #{sig['id']} {sig['ativo']} {sig['direcao']} (conv {sig['conviccao']})")

# 2) abre posição: R$100, 10x
pid = simulador.abrir(sig["id"], valor_reais=100, alavancagem=10)
pos = [p for p in db.listar("posicoes", 10) if p["id"] == pid][0]
print(f"2) Posição #{pid} ABERTA: {pos['ativo']} {pos['direcao']} | entrada {pos['entrada']:.4f} | "
      f"R$100 @ 10x = nocional R$1.000 | stop {pos['stop']:.4f}")

# 3) fecha com +1% A FAVOR (deve dar +10% sobre a margem = +R$10, menos taxa)
d = 1 if pos["direcao"] == "LONG" else -1
preco_saida = pos["entrada"] * (1 + d * 0.01)      # 1% a favor
pnl = simulador.fechar(pid, "teste", preco_saida)
print(f"3) Fechado em {preco_saida:.4f} (+1% a favor) -> P&L = R$ {pnl:+.2f}")
print(f"   esperado: +10% de R$100 (alav) = +R$10, menos taxa ~R$1 = ~+R$9 [OK]" if 8 < pnl < 10
      else f"   (conferir math!)")

# 4) banca e trade gravados
print(f"\n4) Banca agora: R$ {db.get_banca()['atual']:.2f}  (era {banca_ini:.2f})")
t = db.listar("trades", 1)[0]
print(f"   Trade no banco: {t['ativo']} {t['direcao']} ret {t['ret_pct']:+.1f}% | "
      f"pnl R$ {t['pnl_reais']:+.2f} | taxa R$ {t['taxa']:.2f} | motivo {t['motivo_saida']}")

# 5) teste de LIQUIDAÇÃO (abre e força movimento contra)
print("\n5) Teste de liquidação (R$100 @ 20x, movimento de -6% contra):")
pid2 = simulador.abrir(sig["id"], valor_reais=100, alavancagem=20)
pos2 = [p for p in db.listar("posicoes", 10) if p["id"] == pid2][0]
liq = simulador._preco_liquidacao(pos2["entrada"], 1 if pos2["direcao"] == "LONG" else -1, 20)
print(f"   entrada {pos2['entrada']:.4f} | preço de liquidação {liq:.4f} (movimento de ~{0.9/20*100:.1f}%)")
pnl2 = simulador.fechar(pid2, "liquidacao", liq)   # passa o preço de liq (como atualizar() faz)
esperado = -(0.9 + 0.001 * 20) * 100               # ~-92: ~90% da margem (LIQ_BUFFER) + taxa
print(f"   LIQUIDADO -> P&L = R$ {pnl2:+.2f}  (esperado ~R$ {esperado:.0f}: 90% do buffer + taxa) [OK]"
      if abs(pnl2 - esperado) < 0.5 else f"   pnl={pnl2} (esperado ~{esperado:.2f}, conferir)")
print(f"   Banca final: R$ {db.get_banca()['atual']:.2f}")
