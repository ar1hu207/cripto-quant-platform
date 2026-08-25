"""[P2-40] e [P2-39] — os dois consertos que NAO dependem de haver edge.

Nenhum dos dois melhora resultado. Os dois fazem o sistema parar de afirmar coisa errada sobre
si mesmo: um gravava um retorno que ninguem recebeu, o outro capava o risco em silencio.
"""
import pytest

import autotrader
import db
import simulador


# --------------------------------------------------------------------- [P2-40]
def test_p2_40_ret_pct_e_bruto_e_ret_pct_liq_e_o_que_o_operador_recebe(tmp_path, monkeypatch):
    """`ret_pct` sempre foi `move*lev*100` -- SEM taxa e SEM funding -- enquanto `pnl_reais`,
    no mesmo INSERT, tem os dois. Quem lesse `ret_pct` como "o retorno do trade" lia um numero
    que ninguem recebeu, e o erro tinha sinal FIXO: sempre para o lado bom.

    O conserto NAO e trocar o significado de `ret_pct` (as linhas ja gravadas significam
    exatamente "ROE bruto", e reescreve-las viraria duas series coladas com o mesmo nome). E
    dar coluna PROPRIA ao numero liquido -- o mesmo que o [P2-10] fez com o funding.

    A prova precisa dos DOIS ao mesmo tempo: `ret_pct` continua bruto (sem regressao) E
    `ret_pct_liq` bate com `pnl/margem`. Testar so o novo deixaria passar uma mudanca que
    tivesse quebrado o antigo."""
    monkeypatch.setattr(db, "DB", str(tmp_path / "t.db"))
    db.init_db()
    db.set_config("taxa_por_lado", "0.0005")
    with db.conectar() as c:
        c.execute("INSERT INTO sinais(ts,ativo,direcao,conviccao,motivos,preco,stop_sugerido,"
                  "status) VALUES('t','X/USDT','LONG',80,'m',100.0,97.0,'novo')")
        c.execute("INSERT INTO posicoes(ativo,direcao,entrada,valor_reais,alavancagem,stop,"
                  "preco_atual,pnl,aberto_em,status,conviccao,sinal_id) "
                  "VALUES('X/USDT','LONG',100.0,100.0,10.0,97.0,100.0,0,'t','aberta',80,1)")

    monkeypatch.setattr(simulador, "_funding_custo", lambda *a, **k: None)
    pnl = simulador.fechar(1, "manual", preco_saida=101.0)      # +1% do ativo, 10x

    with db.conectar() as c:
        t = dict(c.execute("SELECT * FROM trades WHERE id=1").fetchone())

    # bruto: 1% x 10 = 10,0 -- inalterado, e e o que a suite antiga ja fixava
    assert t["ret_pct"] == pytest.approx(10.0)
    # liquido: o P&L de verdade sobre a margem. taxa = 2*0,0005*100*10 = 1,00
    assert t["pnl_reais"] == pnl
    assert t["ret_pct_liq"] == round(pnl / t["valor_reais"] * 100, 6)
    # e a diferenca entre os dois E a taxa -- se algum dia forem iguais, um dos dois quebrou
    assert t["ret_pct"] > t["ret_pct_liq"]
    assert abs((t["ret_pct"] - t["ret_pct_liq"]) / 100 * t["valor_reais"] - t["taxa"]) < 1e-9


def test_p2_40_ret_pct_liq_e_derivavel_do_historico_sem_inventar_dado():
    """A coluna e nova, mas o numero nao: `pnl_reais / valor_reais * 100` recupera o liquido
    de QUALQUER linha ja gravada. E o que autoriza um backfill sem inventar dado -- e o que
    distingue este caso do funding do [P2-10], que era genuinamente NAO MEDIDO e por isso
    tinha de ficar NULL. Ausente e ausente; derivavel e derivavel."""
    # trade #47 de producao (AAVE, 24/08): pnl -24,81 sobre margem de R$339,03
    pnl, margem = -24.81, 339.03
    assert pnl / margem * 100 == pytest.approx(-7.3179, abs=1e-4)
    # e o bruto gravado naquela linha era -7,017: o liquido e PIOR, sempre. O sinal do erro
    # e fixo, e e essa fixidez que fazia a coluna antiga embelezar o historico.
    assert pnl / margem * 100 < -7.017


# --------------------------------------------------------------------- [P2-39]
def test_p2_39_o_cap_de_tamanho_para_de_agir_em_silencio():
    """Producao, 2026-08-24: `risco_inicial` entre R$0,14 e R$83,16 num sistema que declara
    `risco_por_trade = 3%`. Variacao de ~600x, e nada dizia que o teto tinha agido.

    O teste prova as duas metades: o cap MORDE (o valor sai capado) e agora ele CONTA. E a
    metade que mais importa e `perda_de_risco`: `total` diz que aconteceu, mas so a fracao diz
    se o cap e um teto ocasional ou o dimensionador de facto."""
    autotrader.CAPS_TAMANHO.update(total=0, ultimo=None)
    banca, risco_frac, max_frac = 1000.0, 0.03, 0.25
    # stop a 0,19% da entrada (o TRX 5m de producao) a 3x: risco_rs/(lev*sd) = 30/0,0057 = R$5.263
    valor = autotrader._tamanho(banca, risco_frac, 3.0, 100.0, 99.81, max_frac, ativo="TRX/USDT")

    assert valor == 250.0                                   # capado em banca*max_frac
    assert autotrader.CAPS_TAMANHO["total"] == 1
    u = autotrader.CAPS_TAMANHO["ultimo"]
    assert u["ativo"] == "TRX/USDT"
    assert u["valor_efetivo"] == 250.0 and u["valor_pedido"] > 5000
    assert u["risco_pedido"] == 30.0                        # os 3% declarados
    assert u["risco_efetivo"] < 2.0                         # o que o trade REALMENTE arrisca
    assert u["perda_de_risco"] > 0.95                       # o teto comeu >95% do risco pedido


def test_p2_39_stop_largo_nao_capa_e_nao_conta():
    """Contraprova, e ela e o que impede o contador de virar ruido: com stop largo o sizing
    por risco pede POUCO valor, o cap nao morde e nada e registrado. Um contador que subisse
    sempre nao distinguiria o caso patologico do normal -- que era exatamente o problema."""
    autotrader.CAPS_TAMANHO.update(total=0, ultimo=None)
    # stop a 6% a 10x: 30/(0,6) = R$50, bem abaixo do cap de R$250
    valor = autotrader._tamanho(1000.0, 0.03, 10.0, 100.0, 94.0, 0.25, ativo="NEAR/USDT")
    assert valor == 50.0
    assert autotrader.CAPS_TAMANHO["total"] == 0
    assert autotrader.CAPS_TAMANHO["ultimo"] is None


def test_p2_39_o_cap_nao_mudou_o_numero_que_devolve():
    """A guarda nao foi apertada nem afrouxada -- so deixou de ser muda. `_tamanho` devolve
    exatamente `min(risco_rs/(lev*sd), banca*max_frac)`, com e sem o contador. Se algum dia
    este teste falhar, alguem transformou instrumentacao em mudanca de comportamento."""
    for lev, stop in ((3.0, 99.81), (10.0, 94.0), (20.0, 99.0), (5.0, 90.0)):
        esperado = min(1000.0 * 0.03 / min(lev * abs(100.0 - stop) / 100.0, 1.0), 1000.0 * 0.25)
        assert autotrader._tamanho(1000.0, 0.03, lev, 100.0, stop, 0.25) == round(esperado, 2)
