# -*- coding: utf-8 -*-
"""Prova do caminho fim a fim: sinal -> posicao -> fechamento com P&L correto.

REESCRITO em 2026-08-22 pelo [P2-6]. A versao anterior nao rodava e, se rodasse, nao
provava nada. Tres defeitos, e os tres sao o motivo da reescrita:

1. **Dependia de um `trading.db` povoado.** Escolhia o sinal por
   `max(db.listar("sinais", 20), ...)`, entao so funcionava numa maquina que ja tivesse
   sinais gravados. Os dados vivem na VM; o banco local esta vazio (CLAUDE.md, cabecalho),
   e o script morria em `ValueError: max() arg is an empty sequence`.
2. **Nao tinha asseracao nenhuma.** Imprimia `[OK]` ou `(conferir math!)` num operador
   ternario dentro do `print` e saia com codigo 0 nos dois casos. Um P&L errado passava em
   silencio -- que e a definicao de teste que nao testa.
3. **Contradizia o comportamento atual.** Reutilizava o MESMO `sig["id"]` para a segunda
   abertura (a de liquidacao). Depois do [P1-6], `abrir()` faz claim atomico do sinal e
   recusa o segundo pedido: o script de antes falharia hoje mesmo com banco povoado.

O que ele cobre continua sendo o mesmo -- e o unico lugar da suite que percorre o caminho
inteiro em vez de uma funcao isolada. O que mudou: banco temporario, dados semeados pelo
proprio teste, nenhuma rede, e cada afirmacao vira exit code. E o padrao do `prova_m1.py`.

    python test_sim.py        # 13 asseracoes, exit 1 se qualquer uma falhar

O pytest chama este arquivo por subprocesso, em `tests/test_provas_existentes.py`. O corpo
fica atras do `if __name__ == "__main__"` de proposito: o nome casa com `test_*.py`, e sem a
guarda uma coleta acidental executaria a prova dentro do processo do pytest.
"""
import os
import sys
import tempfile


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_sim.db")   # nunca producao

    import pandas as pd
    import db
    import simulador

    class SemFunding:
        """Historico de funding vazio = medicao de ZERO, que e diferente de falha de
        medicao ([P2-10]). Aqui interessa isolar entrada/saida/taxa, entao zero medido."""
        def fetch_funding_rate_history(self, ativo, since=None, limit=None):
            return []

    simulador.preco_ao_vivo = lambda ativo: 100.0     # sem rede
    simulador.ex_fut = SemFunding()                   # sem rede

    db.init_db()
    ok = fail = 0

    def check(nome, cond, detalhe=""):
        nonlocal ok, fail
        print(("  PASSA  " if cond else "  FALHA  ") + nome + ("" if cond else "  <- " + str(detalhe)))
        if cond:
            ok += 1
        else:
            fail += 1

    def semear(ativo="BTC/USDT", direcao="LONG", preco=100.0, stop=98.0, conv=80):
        with db.conectar() as c:
            c.execute("INSERT INTO sinais(ts,ativo,tf,tipo,direcao,conviccao,motivos,preco,"
                      "stop_sugerido,status) VALUES(?,?,'15m','tendencia',?,?,'prova',?,?,'novo')",
                      (str(pd.Timestamp.now()), ativo, direcao, conv, preco, stop))
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]

    banca_ini = db.get_banca()["atual"]
    print("Banca inicial: R$ %.2f\n" % banca_ini)

    # ---------- 1) sinal -> posicao
    sid = semear()
    pid = simulador.abrir(sid, valor_reais=100, alavancagem=10)
    pos = [p for p in db.listar("posicoes", 10) if p["id"] == pid][0]
    print("1) posicao #%d: %s %s | entrada %.4f | R$100 @ 10x = nocional R$1.000 | stop %.4f"
          % (pid, pos["ativo"], pos["direcao"], pos["entrada"], pos["stop"]))
    check("a posicao nasce aberta, com a entrada no preco ao vivo",
          pos["status"] == "aberta" and pos["entrada"] == 100.0, str(pos))
    check("o stop mantem a distancia relativa do sinal (2%)", abs(pos["stop"] - 98.0) < 1e-9,
          str(pos["stop"]))
    with db.conectar() as c:
        st = c.execute("SELECT status FROM sinais WHERE id=?", (sid,)).fetchone()[0]
    check("o sinal foi consumido pelo claim atomico [P1-6]", st == "confirmado", st)

    # ---------- 2) o mesmo sinal nao abre duas vezes  (era o que a versao antiga fazia)
    try:
        simulador.abrir(sid, valor_reais=100, alavancagem=20)
        recusou = False
    except ValueError:
        recusou = True
    check("reusar o mesmo sinal e recusado [P1-6]", recusou)
    check("e nenhuma segunda posicao nasceu", len(db.listar("posicoes", 10)) == 1)

    # ---------- 3) fecha com +1% A FAVOR: +10% sobre a margem, menos a taxa
    pnl = simulador.fechar(pid, "prova", 101.0)
    print("3) fechado em 101.0 (+1%% a favor) -> P&L = R$ %+.2f" % pnl)
    check("P&L = +10% da margem menos R$1 de taxa = +R$9", abs(pnl - 9.0) < 1e-9, repr(pnl))
    check("a banca recebeu exatamente o P&L", abs(db.get_banca()["atual"] - (banca_ini + 9.0)) < 1e-9,
          str(db.get_banca()["atual"]))

    t = db.listar("trades", 1)[0]
    print("   trade: %s %s ret %+.1f%% | pnl R$ %+.2f | taxa R$ %.2f | motivo %s"
          % (t["ativo"], t["direcao"], t["ret_pct"], t["pnl_reais"], t["taxa"], t["motivo_saida"]))
    check("ret_pct e o retorno sobre a MARGEM (1% do ativo x 10x)", abs(t["ret_pct"] - 10.0) < 1e-9,
          repr(t["ret_pct"]))
    check("a taxa dos dois lados sobre o nocional = R$1", abs(t["taxa"] - 1.0) < 1e-9, repr(t["taxa"]))
    check("risco_inicial gravado = 2% x 10x x R$100 = R$20", abs(t["risco_inicial"] - 20.0) < 1e-9,
          repr(t["risco_inicial"]))
    check("funding medido como zero grava 0.0, nao NULL [P2-10]", t["funding"] == 0.0,
          repr(t["funding"]))

    # ---------- 4) liquidacao: R$100 @ 20x, fechado no proprio preco de liquidacao
    sid2 = semear(preco=100.0, stop=98.0)
    pid2 = simulador.abrir(sid2, valor_reais=100, alavancagem=20)
    pos2 = [p for p in db.listar("posicoes", 10) if p["id"] == pid2][0]
    d = 1 if pos2["direcao"] == "LONG" else -1
    liq = simulador._preco_liquidacao(pos2["entrada"], d, 20)
    print("\n4) liquidacao: entrada %.4f | preco de liquidacao %.4f (%.1f%% contra)"
          % (pos2["entrada"], liq, simulador.LIQ_BUFFER / 20 * 100))
    pnl2 = simulador.fechar(pid2, "liquidacao", liq)
    esperado = -(simulador.LIQ_BUFFER + 0.001 * 20) * 100      # 90% da margem + taxa = -92
    print("   LIQUIDADO -> P&L = R$ %+.2f  (esperado R$ %.2f)" % (pnl2, esperado))
    check("liquidar custa LIQ_BUFFER da margem mais a taxa", abs(pnl2 - esperado) < 1e-9,
          "%s vs %s" % (pnl2, esperado))
    check("e ainda assim menos que a margem inteira", pnl2 > -100.0, repr(pnl2))
    print("   banca final: R$ %.2f" % db.get_banca()["atual"])

    print("\n  %d passaram, %d falharam" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    try:                                   # console do Windows em cp1252 mutila o acento
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
