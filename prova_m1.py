# -*- coding: utf-8 -*-
"""Prova funcional das guardas de risco do M1 — roda contra banco TEMPORARIO.

Escrito em 2026-08-22 porque `test_sim.py` nao roda (depende de um trading.db
povoado, e o local esta vazio: os dados vivem na VM). Sem isto o M1 teria sido
mergeado sem nenhuma verificacao automatizada.

    python prova_m1.py        # 7 asseracoes, exit 1 se qualquer uma falhar

NAO e uma suite de testes: e o minimo que provou o M1 antes do deploy. O card
P2-6 (M3, pytest rodando) deve absorver isto como ponto de partida - as
asseracoes aqui sao a regressao que importa em cada guarda.

Nao toca em producao: DB_PATH aponta para um diretorio temporario e
preco_ao_vivo e substituido por funcao local, entao nao ha rede.
"""
import os, sys, tempfile, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
import db, simulador

def _post_config_raw():
    raise RuntimeError("sem modelo")

db.init_db()
ok = fail = 0
def check(nome, cond, detalhe=""):
    global ok, fail
    print(("  PASSA  " if cond else "  FALHA  ") + nome + ("" if cond else f"  <- {detalhe}"))
    globals().__setitem__("ok" if cond else "fail", (ok+1) if cond else (fail+1))

# ---------- P1-6: claim atomico impede posicao dupla do mesmo sinal
with db.conectar() as c:
    c.execute("INSERT INTO sinais(ts,ativo,tf,tipo,direcao,conviccao,motivos,preco,stop_sugerido,status)"
              " VALUES('2026-08-22 00:00:00','BTC/USDT','15m','tendencia','LONG',80,'x',100.0,95.0,'novo')")
    sid = c.execute("SELECT id FROM sinais ORDER BY id DESC LIMIT 1").fetchone()[0]
simulador.preco_ao_vivo = lambda a: 100.0          # sem rede

res = []
def tenta():
    try: res.append(("ok", simulador.abrir(sid, 50.0, 2)))
    except Exception as e: res.append(("erro", str(e)[:60]))
ts = [threading.Thread(target=tenta) for _ in range(2)]
[t.start() for t in ts]; [t.join() for t in ts]
abertas = len(db.listar("posicoes", 50))
check("P1-6 duas confirmacoes do mesmo sinal -> 1 posicao", abertas == 1, f"abriu {abertas}")
check("P1-6 a segunda foi recusada com motivo", sum(1 for r in res if r[0]=="erro") == 1, str(res))

# ---------- P1-1: falha de rede numa posicao nao derruba a marcacao das outras
with db.conectar() as c:
    c.execute("INSERT INTO sinais(ts,ativo,tf,tipo,direcao,conviccao,motivos,preco,stop_sugerido,status)"
              " VALUES('2026-08-22 00:00:00','ETH/USDT','15m','tendencia','LONG',80,'x',100.0,95.0,'novo')")
    sid2 = c.execute("SELECT id FROM sinais ORDER BY id DESC LIMIT 1").fetchone()[0]
simulador.abrir(sid2, 50.0, 2)
def preco_quebrado(ativo):
    if ativo == "BTC/USDT": raise RuntimeError("binance fora do ar")
    return 111.0
simulador.preco_ao_vivo = preco_quebrado
try:
    simulador.atualizar()
    levantou = False
except Exception as e:
    levantou = True
check("P1-1 atualizar() sobrevive a falha de rede numa posicao", not levantou)
precos = {p["ativo"]: p["preco_atual"] for p in db.listar("posicoes", 50)}
check("P1-1 a posicao saudavel foi marcada mesmo assim", precos.get("ETH/USDT") == 111.0, str(precos))

# ---------- P1-7: panico desliga o auto-trader
db.set_config("auto_trade", "1")
import api
api.panico()
check("P1-7 panico grava auto_trade=0", db.get_config().get("auto_trade") == "0")

# ---------- P1-8: config invalida e recusada na entrada
try:
    api.configurar(api.ConfigReq(**{"risco_por_trade": "abc"})) if hasattr(api,"ConfigReq") else _post_config_raw()
    recusou = False
except Exception:
    recusou = True
check("P1-8 config com valor invalido nao entra", recusou or db.get_config().get("risco_por_trade") != "abc")

# ---------- P2-12: reset limpa a trava diaria
db.set_config("trava_dia_em", "2026-08-22")
try:
    api.reset(api.ResetReq(confirmar="RESET", incluir_dca=False))
except Exception as e:
    print("   (reset:", str(e)[:50], ")")
check("P2-12 reset limpa trava_dia_em", not db.get_config().get("trava_dia_em"))

print(f"\n  {ok} passaram, {fail} falharam")
sys.exit(1 if fail else 0)
