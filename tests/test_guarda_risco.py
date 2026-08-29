# -*- coding: utf-8 -*-
"""Item 1 do [P2-6]: `simulador.guarda_risco()` -- trava diaria sticky e teto de risco aberto.

Sao invariantes de risco (CLAUDE.md §2): so o dono afrouxa. O que este arquivo faz e travar
o COMPORTAMENTO, para que afrouxar exija apagar uma asseracao com nome -- e nao so mudar um
sinal de comparacao sem ninguem ver.

O teto de MARGEM, que o card lista junto destes dois, nao vive aqui: ele levanta dentro de
`abrir()`, e por isso esta em `test_abrir.py`.
"""
import pandas as pd
import pytest

import db
import simulador
from conftest import semear_equity, semear_posicao, semear_sinal


HOJE = str(pd.Timestamp.now().date())
ONTEM = str(pd.Timestamp.now().date() - pd.Timedelta(days=1))


def _equity_do_dia(valor, hora="00:00:05"):
    semear_equity(HOJE + " " + hora, valor)


# ---------------------------------------------------------------- baseline do dia

def test_sem_snapshot_do_dia_o_baseline_e_o_equity_de_agora(banco):
    """Dia que ainda nao gravou equity: o baseline e o proprio equity atual, entao
    pnl_dia = 0. Sem esse fallback o primeiro ciclo do dia compararia contra zero e
    travaria sozinho."""
    g = simulador.guarda_risco()
    assert g["pnl_dia"] == 0.0
    assert g["trava_dia"] is False


def test_baseline_e_o_primeiro_snapshot_do_dia_nao_o_ultimo(banco):
    """`ORDER BY rowid ASC LIMIT 1`: a trava mede a variacao desde o INICIO do dia. Pegar o
    ultimo snapshot faria o baseline perseguir o equity e a trava nunca acionaria."""
    _equity_do_dia(1000.0, "00:00:05")
    _equity_do_dia(1200.0, "10:00:00")
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=960 WHERE id=1")
    g = simulador.guarda_risco()
    assert g["pnl_dia"] == -40.0          # 960 - 1000, e nao 960 - 1200


def test_snapshot_de_ontem_nao_serve_de_baseline_de_hoje(banco):
    semear_equity(ONTEM + " 23:59:59", 500.0)
    g = simulador.guarda_risco()
    assert g["pnl_dia"] == 0.0            # ignorou ontem, caiu no fallback do dia
    assert g["trava_dia"] is False


# ---------------------------------------------------------------- trava diaria

def test_trava_mede_equity_e_nao_pnl_realizado(banco):
    """O caso de 22/08 registrado no CLAUDE.md §2: +34,68 de realizado no dia e a trava
    disparada por -80,34 de EQUITY. Se a guarda olhasse `realizado_hoje` -- que ela calcula
    e devolve -- o dia teria seguido operando com a banca caindo."""
    _equity_do_dia(1000.0)
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=1034.68 WHERE id=1")
        c.execute("INSERT INTO trades(ativo,direcao,pnl_reais,fechado_em) "
                  "VALUES('BTC/USDT','LONG',34.68,?)", (HOJE + " 09:00:00",))
    semear_posicao(valor_reais=200.0, alavancagem=5, entrada=100.0, stop=99.0, pnl=-115.02)
    g = simulador.guarda_risco()
    assert g["realizado_hoje"] == 34.68           # realizado positivo...
    assert g["pnl_dia"] == -80.34                 # ...e o equity abaixo do inicio do dia
    assert g["trava_dia"] is True


def test_trava_nao_dispara_antes_do_limite(banco):
    _equity_do_dia(1000.0)
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=951 WHERE id=1")     # -49, limite e -50 (5%)
    g = simulador.guarda_risco()
    assert g["limite_rs"] == 50.0
    assert g["trava_dia"] is False
    assert db.get_config().get("trava_dia_em", "") == ""


def test_trava_dispara_exatamente_no_limite(banco):
    """`pnl_dia <= -limite_rs`: bater o limite ja e atingi-lo."""
    _equity_do_dia(1000.0)
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=950 WHERE id=1")
    assert simulador.guarda_risco()["trava_dia"] is True


def test_trava_e_sticky_no_dia_mesmo_com_o_equity_recuperando(banco):
    """O que o CLAUDE.md chama de sticky: acionou hoje, fica travado hoje. Sem isto, uma
    posicao aberta oscilando destravaria o dia sozinha a cada poll de 3s."""
    _equity_do_dia(1000.0)
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=900 WHERE id=1")
    assert simulador.guarda_risco()["trava_dia"] is True
    assert db.get_config()["trava_dia_em"] == HOJE            # gravou a marca no banco

    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=1100 WHERE id=1")   # recuperou, e passou do inicio
    g = simulador.guarda_risco()
    assert g["pnl_dia"] == 100.0
    assert g["trava_dia"] is True                             # continua travado


def test_a_marca_da_trava_e_idempotente(banco):
    """`if tripou and trava_em != hoje`: grava uma vez, nao um write por poll."""
    _equity_do_dia(1000.0)
    with db.conectar() as c:
        c.execute("UPDATE banca SET atual=900 WHERE id=1")
    simulador.guarda_risco()
    simulador.guarda_risco()
    with db.conectar() as c:
        n = c.execute("SELECT COUNT(*) FROM config WHERE chave='trava_dia_em'").fetchone()[0]
    assert n == 1
    assert db.get_config()["trava_dia_em"] == HOJE


def test_a_trava_solta_na_virada_do_dia(banco):
    """Marca de ontem nao trava hoje -- e o unico jeito de soltar previsto no codigo.
    Limpar `trava_dia_em` a mao seria relaxar invariante (CLAUDE.md §2)."""
    db.set_config("trava_dia_em", ONTEM)
    assert simulador.guarda_risco()["trava_dia"] is False


def test_marca_de_hoje_trava_mesmo_sem_perda_agora(banco):
    """O estado persistido manda: reiniciar o worker nao destrava o dia."""
    db.set_config("trava_dia_em", HOJE)
    assert simulador.guarda_risco()["trava_dia"] is True


# ---------------------------------------------------------------- teto de risco aberto

def test_teto_de_risco_aberto_soma_o_risco_ate_o_stop(banco):
    """Duas posicoes de R$50 a 10x com stop a 2%: risco 50*10*0.02 = R$10 cada. Teto
    padrao e 10% de R$1.000 = R$100 -- longe."""
    semear_posicao(ativo="BTC/USDT", entrada=100.0, stop=98.0, valor_reais=50.0, alavancagem=10)
    semear_posicao(ativo="ETH/USDT", entrada=100.0, stop=98.0, valor_reais=50.0, alavancagem=10)
    g = simulador.guarda_risco()
    assert g["n_abertas"] == 2
    assert g["risco_aberto_rs"] == 20.0
    assert g["risco_aberto_max_rs"] == 100.0
    assert g["teto_aberto"] is False


def test_teto_aberto_acusa_quando_o_risco_alcanca_o_limite(banco):
    db.set_config("risco_aberto_max", "0.02")                 # 2% de 1000 = R$20
    semear_posicao(entrada=100.0, stop=98.0, valor_reais=50.0, alavancagem=10)   # R$10
    semear_posicao(entrada=100.0, stop=98.0, valor_reais=50.0, alavancagem=10)   # R$10
    g = simulador.guarda_risco()
    assert g["risco_aberto_rs"] == 20.0
    assert g["risco_aberto_max_rs"] == 20.0
    assert g["teto_aberto"] is True                            # `>=`, nao `>`


def test_risco_aberto_max_zero_desliga_o_teto(banco):
    """`<=0 => sem teto`, conforme o comentario do CONFIG_PADRAO. `None` e a ausencia
    DECLARADA: `abrir()` le exatamente isso para pular a checagem."""
    db.set_config("risco_aberto_max", "0")
    semear_posicao(entrada=100.0, stop=98.0, valor_reais=500.0, alavancagem=10)
    g = simulador.guarda_risco()
    assert g["risco_aberto_max_rs"] is None
    assert g["teto_aberto"] is False


def test_margem_aberta_e_a_soma_das_margens_nao_do_nocional(banco):
    semear_posicao(valor_reais=50.0, alavancagem=10)
    semear_posicao(valor_reais=30.0, alavancagem=3)
    assert simulador.guarda_risco()["margem_aberta"] == 80.0


def test_posicao_fechada_nao_conta_em_nada(banco):
    semear_posicao(valor_reais=500.0, alavancagem=10, entrada=100.0, stop=98.0, status="fechada")
    g = simulador.guarda_risco()
    assert (g["n_abertas"], g["margem_aberta"], g["risco_aberto_rs"]) == (0, 0.0, 0.0)


# ---------------------------------------------------------------- _risco_posicao

@pytest.mark.parametrize("valor,lev,entrada,stop,esperado", [
    (50.0, 10, 100.0, 98.0, 10.0),      # 2% de distancia x 10x = 20% da margem
    (50.0, 2, 100.0, 95.0, 5.0),        # 5% x 2x = 10% da margem
    (50.0, 10, 100.0, None, 50.0),      # sem stop: a perda maxima e a margem inteira
    (50.0, 10, 100.0, 0, 50.0),         # stop 0 conta como sem stop
    (50.0, 20, 100.0, 90.0, 50.0),      # liquidacao antes do stop: capado na margem
    (50.0, 10, 100.0, 110.0, 50.0),     # stop do lado errado: `abs()`, e ainda capado
    (0.0, 10, 100.0, 98.0, 0.0),
])
def test_risco_posicao(banco, valor, lev, entrada, stop, esperado):
    assert simulador._risco_posicao(valor, lev, entrada, stop) == pytest.approx(esperado)


# ---------------------------------------------------------------- [P1-8] em profundidade

def test_config_invalida_no_banco_nao_derruba_a_guarda(banco):
    """Defesa em profundidade do [P1-8]: a validacao de verdade e no POST /config, mas lixo
    que ja esteja gravado nao pode transformar a guarda em ValueError -- isso derrubaria
    `/estado` E o ciclo do worker, que e indisponibilidade total em vez de degradacao."""
    db.set_config("limite_perda_dia", "abc")
    db.set_config("risco_aberto_max", "")
    g = simulador.guarda_risco()
    assert g["limite_pct"] == 5.0                  # caiu no padrao 0.05
    assert g["risco_aberto_pct"] == 10.0


# ---------------------------------------------------------------- [P1-12] geometria em abrir()
#
# Por que aqui e nao em `tests/test_abrir.py`, onde o teto de MARGEM mora (docstring do topo):
# a recusa do [P1-12] e guarda de RISCO -- ela nao pergunta se o trade cabe no orcamento,
# pergunta se o DESENHO do trade e possivel -- e o territorio T-GUARDA da onda 2 do M4 tem
# `tests/test_guarda_risco.py` e `tests/test_sizing.py`, nao `tests/test_abrir.py`. A convencao
# do arquivo e a fronteira do territorio discordam aqui, e a fronteira manda (§9.4/P2).

TABELA_STOPS_P1_11 = [0.0074, 0.0164, 0.0265, 0.0473, 0.0279, 0.0483, 0.0290,
                      0.0456, 0.0359, 0.0586, 0.0373, 0.0919, 0.0367, 0.0950]


def _sem_tetos():
    """Desliga os tetos de risco e de margem. Sem isto, uma posicao de 20x com stop de 5% ja
    estoura o teto de risco aberto, e o teste passaria pelo motivo errado -- provando a
    recusa que JA existia em vez da que o card pede."""
    db.set_config("risco_aberto_max", "0")
    db.set_config("exposicao_max", "0")


def test_p1_12_a_alavancagem_do_cliente_com_liquidacao_antes_do_stop_e_recusada(banco, sem_rede):
    """Item 1 do aceite. O caso vivo: o `POST /confirmar` recebe `alavancagem` do CLIENTE e a
    repassa para `abrir()`; a 20x com stop de 5% a liquidacao fica a 4,5% -- o stop e
    inalcancavel e a perda e a margem inteira. O cap do [P1-11] nao alcanca este caminho.

    A mensagem tem de DIZER a geometria: "recusado" sem os dois numeros nao diz ao operador
    qual dos dois lados ele tem de mexer."""
    _sem_tetos()
    sid = semear_sinal(preco=100.0, stop=95.0)
    with pytest.raises(ValueError, match="geometria degenerada") as e:
        simulador.abrir(sid, 100.0, 20)
    assert "4.50%" in str(e.value) and "5.00%" in str(e.value)     # liquidacao e stop, os dois
    assert "abaixo de 18.0x" in str(e.value)                       # e o que fazer a respeito


def test_p1_12_a_recusa_por_geometria_nao_consome_o_sinal(banco, sem_rede):
    """O invariante do CLAUDE.md §2 que `tests/test_abrir.py` trava para os tetos, aplicado a
    guarda nova: ela levanta ANTES do claim atomico. Recusa por geometria nao e defeito do
    sinal -- o mesmo sinal volta a ser confirmavel com uma alavancagem que caiba, e um claim
    aqui o tiraria da fila para sempre."""
    _sem_tetos()
    sid = semear_sinal(preco=100.0, stop=95.0)
    with pytest.raises(ValueError, match="geometria"):
        simulador.abrir(sid, 100.0, 20)
    with db.conectar() as c:
        assert c.execute("SELECT status FROM sinais WHERE id=?", (sid,)).fetchone()["status"] == "novo"
    assert db.listar("posicoes", 10) == []
    simulador.abrir(sid, 100.0, 10)                                # e a 10x o MESMO sinal abre
    assert len(db.listar("posicoes", 10)) == 1


def test_p1_12_a_recusa_chega_ao_painel_como_ok_false_e_nao_como_500(banco, sem_rede):
    """Item 2 do aceite: reproduzivel SEM navegador. Chama a funcao da rota direto, que e o
    que um `curl` alcanca -- e o que ele recebe e o contrato `{ok: false, erro}` que o painel
    ja entende, porque `api.py:682` traduz o `ValueError`. Foi por isso que a opcao B do card
    nao precisou de mudanca no `api.py`: se a rota devolvesse 500, uma recusa deliberada do
    sistema apareceria como falha do servidor."""
    import api
    _sem_tetos()
    sid = semear_sinal(preco=100.0, stop=95.0)
    r = api.confirmar(api.ConfirmarReq(sinal_id=sid, valor_reais=100.0, alavancagem=20))
    assert r["ok"] is False
    assert "geometria degenerada" in r["erro"]
    assert db.listar("posicoes", 10) == []


@pytest.mark.parametrize("lev,abre", [(2, True), (10, True), (16, True), (17, True),
                                      (18, False), (19, False), (20, False), (50, False)])
def test_p1_12_a_fronteira_e_a_liquidacao_ENCOSTANDO_no_stop(banco, sem_rede, lev, abre):
    """Com stop de 5% o limite e `LIQ_BUFFER/0,05` = 18x exatos: a 17x a liquidacao fica a
    5,29% (atras do stop) e a 18x fica a 5,00% (em cima dele).

    O empate e RECUSADO, e isso e um aperto deliberado sobre a letra do card ("mais perto da
    entrada que o stop"): com a liquidacao no mesmo preco do stop, quem bate primeiro passa a
    ser decidido por um desempate de `_marcar_uma`, e a perda e a margem inteira dos dois
    jeitos. Apertar guarda pode; afrouxar e do dono (CLAUDE.md §2)."""
    _sem_tetos()
    sid = semear_sinal(preco=100.0, stop=95.0)
    if abre:
        assert simulador.abrir(sid, 20.0, lev)
    else:
        with pytest.raises(ValueError, match="geometria"):
            simulador.abrir(sid, 20.0, lev)


@pytest.mark.parametrize("lev,stop", [
    (2, 95.0), (2, 90.0), (2, 60.0),        # 2x so degenera com stop > 45%
    (5, 98.0), (5, 90.0), (5, 85.0),
    (10, 99.0), (10, 98.0), (10, 95.0),     # 10x: o limite e 9%
    (20, 99.0), (20, 98.0), (20, 96.0),     # 20x: o limite e 4,5%
])
def test_p1_12_o_caso_normal_abre_exatamente_como_hoje(banco, sem_rede, lev, stop):
    """Item 3 do aceite, e a parte que segura a mao: a recusa so pode agir na geometria
    degenerada. Cada par aqui tem `lev x stop_dist < 0,9`, entao a liquidacao esta atras do
    stop e nada muda -- inclusive os pares que a suite ja usava antes deste card (`2x` com
    stop de 5% em `tests/test_abrir.py`, `10x` com stop de 2% em `test_sim.py`)."""
    _sem_tetos()
    sid = semear_sinal(preco=100.0, stop=stop)
    pid = simulador.abrir(sid, 20.0, lev)
    p = db.listar("posicoes", 1)[0]
    assert (p["id"], p["status"], p["alavancagem"]) == (pid, "aberta", lev)


def test_p1_12_sinal_sem_stop_nao_e_barrado_pela_geometria(banco, sem_rede):
    """Sem stop nao ha distancia para comparar, e derivar uma recusa de `stop=None` seria
    inventar geometria. Quem cobre este caso e o teto de risco: `_risco_posicao` ja devolve a
    MARGEM INTEIRA quando nao ha stop, que e a leitura honesta da perda maxima."""
    _sem_tetos()
    for i, stop in enumerate((None, 0)):
        sid = semear_sinal(ativo="X%d/USDT" % i, preco=100.0, stop=stop)
        assert simulador.abrir(sid, 20.0, 50)
    db.set_config("risco_aberto_max", "0.10")                      # e com o teto ligado, ele pega
    sid = semear_sinal(ativo="Y/USDT", preco=100.0, stop=None)
    with pytest.raises(ValueError, match="teto de risco aberto"):
        simulador.abrir(sid, 200.0, 50)


def test_p1_12_a_guarda_vale_no_short(banco, sem_rede):
    """A liquidacao e simetrica e o painel opera SHORT. Uma guarda que so olhasse LONG
    deixaria metade do fluxo manual passar."""
    _sem_tetos()
    sid = semear_sinal(direcao="SHORT", preco=100.0, stop=105.0)
    with pytest.raises(ValueError, match="geometria"):
        simulador.abrir(sid, 100.0, 20)


def test_p1_12_a_guarda_mede_a_entrada_AO_VIVO_e_o_stop_RECOMPOSTO(banco, sem_rede):
    """A guarda fica DEPOIS da recomposicao do stop de proposito: `abrir()` refaz o stop a
    partir do preco ao vivo mantendo a distancia RELATIVA, entao medir os campos do sinal
    (100/95) em vez do que vai para o banco (200/190) seria medir uma posicao que nao existe.

    Aqui as duas contas dao 5% e o veredito e o mesmo -- o que este teste trava e a ORDEM: se
    alguem mover a guarda para antes da recomposicao, no dia em que as duas divergirem a
    guarda estara olhando para o numero errado, e nenhum teste de valor acusaria."""
    _sem_tetos()
    sem_rede(200.0)
    sid = semear_sinal(preco=100.0, stop=95.0)
    with pytest.raises(ValueError, match="geometria"):
        simulador.abrir(sid, 100.0, 20)


@pytest.mark.parametrize("stop_dist", TABELA_STOPS_P1_11)
def test_p1_12_o_auto_trader_nunca_bate_na_propria_guarda(stop_dist):
    """As duas camadas nao podem brigar. O cap do [P1-11] usa `FOLGA_LIQ` = 0,8 (25% de folga
    ALEM do stop) e esta guarda usa a fronteira fisica (`LIQ_BUFFER`): o cap e estritamente
    mais apertado, entao toda lev que o bot escolhe passa aqui com sobra.

    Se as duas usassem o MESMO numero, o bot viveria em cima da fronteira e um erro de ponto
    flutuante bastaria para ele recusar os proprios trades. A guarda e a parede; o cap e o
    recuo que o bot se impoe antes dela.

    Roda sobre a tabela de stops MEDIDOS do [P1-11] -- os mesmos ativos e percentis que
    produziam 37,2% de trades binarios no INJ 1h a 20x."""
    import autotrader
    cfg = {"auto_lev_modo": "conviccao", "auto_lev_min": "2", "auto_lev_max": "20",
           "auto_conviccao_min": "60"}
    lev = autotrader._alavancagem(cfg, 100, stop_dist)
    entrada = 100.0
    assert simulador._liq_antes_do_stop(entrada, entrada * (1 - stop_dist), lev, 1) is None


@pytest.mark.parametrize("entrada,stop,lev", [
    (100.0, 100.0, 50),      # stop na entrada: distancia zero, nao ha o que comparar
    (100.0, None, 50),
    (100.0, 0, 50),
    (0, 95.0, 50),           # entrada degenerada: nao pode virar divisao por zero
    (None, None, 50),
    (100.0, 95.0, 0),        # lev 0: `abrir()` ja recusa na primeira linha, e aqui nao explode
])
def test_p1_12_sem_geometria_medivel_a_guarda_se_cala(entrada, stop, lev):
    """Mesma regra de `autotrader._stop_dist`: ausencia de geometria devolve ausencia, nunca
    excecao no meio do ciclo do worker."""
    assert simulador._liq_antes_do_stop(entrada, stop, lev, 1) is None


# ------------------------------------------------- [P2-38] as taxas ficam FORA do risco medido
#
# A decisao do card foi a opcao C: documentar em `ARQUITETURA.md` §10(e), nao implementar. O que
# segue nao prova um conserto -- prova a APROXIMACAO que foi decidida, e e o que impede que ela
# seja desfeita de passagem. `_risco_posicao` grava `trades.risco_inicial` (`simulador.py:273`),
# que e o denominador de `expectancia_r`/`sqn_r` em `db.metricas()`: somar as taxas aqui reescala
# a unidade R no meio do historico, e NENHUM numero do painel acusa. Documentacao que ninguem
# executa envelhece calada; esta tem um teste com o nome do card em cima.

FEE = 0.0005          # db.CONFIG_PADRAO["taxa_por_lado"]


@pytest.mark.parametrize("valor,lev,sd", [
    (100.0, 2, 0.02), (100.0, 10, 0.02), (100.0, 20, 0.02), (150.0, 10, 0.0074),
    (50.0, 5, 0.0164), (200.0, 3, 0.0367),
])
def test_p2_38_o_risco_medido_exclui_as_taxas_e_isso_e_decisao_registrada(banco, valor, lev, sd):
    """A formula vigente e `valor x lev x sd`, sem os `2 x fee x lev x valor` das duas pernas.

    O segundo assert e o conteudo da §10(e) que a intuicao erra: o fator de subestimacao e
    `(sd + 2*fee)/sd` e **a alavancagem CANCELA** -- os dois termos escalam com `lev x valor`.
    Ou seja, o caso perigoso nao e a alavancagem alta, e o STOP CURTO: a 50x com stop de 9,5% o
    erro relativo e 1,1%; a 2x com stop de 0,5% e 20%. A tabela por alavancagem que o [Q-6]
    deixou mede outra coisa (fracao da MARGEM), e e por isso que as duas convivem na secao."""
    entrada = 100.0
    stop = entrada * (1 - sd)
    medido = simulador._risco_posicao(valor, lev, entrada, stop)
    real = valor * lev * (sd + 2 * FEE)

    assert medido == pytest.approx(valor * lev * sd)          # sem taxas, e de proposito
    assert real / medido == pytest.approx((sd + 2 * FEE) / sd)
    assert real > medido                                       # a direcao do vies: subestima


@pytest.mark.parametrize("sd,fator", [
    (0.0050, 1.200), (0.0074, 1.135), (0.0164, 1.061),
    (0.0265, 1.038), (0.0367, 1.027), (0.0950, 1.011),
])
def test_p2_38_a_tabela_de_magnitude_da_arquitetura_e_esta(sd, fator):
    """Os seis fatores tabelados em `ARQUITETURA.md` §10(e), conferidos contra a conta. Item
    final do aceite da opcao C: a magnitude fica TABELADA, e uma tabela que ninguem recalcula
    e so um numero velho com formatacao."""
    assert (sd + 2 * FEE) / sd == pytest.approx(fator, abs=0.001)


def test_p2_38_o_caso_vivo_arrisca_5pct_a_mais_do_que_a_guarda_conta(banco):
    """O numero que a §10(e) usa para dizer o tamanho do buraco, medido em vez de estimado:
    banca R$1.000 com `risco_por_trade` 3% e stop de 2% a 10x. `_tamanho` pede R$150, a guarda
    conta R$30 e a perda real no stop e R$31,50.

    Este teste tambem prova a premissa que sustenta a decisao C: `_tamanho` e `_risco_posicao`
    sao INVERSAS EXATAS hoje. Mexer so num lado quebra esta igualdade, e e por isso que a opcao
    B do card nao fecha -- ela desalinha as duas por construcao."""
    import autotrader
    valor = autotrader._tamanho(1000.0, 0.03, 10, 100.0, 98.0, 0.25)
    medido = simulador._risco_posicao(valor, 10, 100.0, 98.0)
    assert valor == pytest.approx(150.0)
    assert medido == pytest.approx(30.0)                       # a inversa exata do sizing
    assert medido + 2 * FEE * 10 * valor == pytest.approx(31.50)


@pytest.mark.parametrize("lev", [2, 5, 10, 20, 50])
def test_p2_38_o_cap_na_margem_deixou_de_mascarar_a_subestimacao(banco, lev):
    """O que mudou HOJE e a §10(e) registra. Antes do [P1-12], `lev x sd >= 1` fazia
    `_risco_posicao` devolver a margem inteira, e nesse regime nao havia o que subestimar. Com a
    guarda nova toda posicao NOVA tem `lev x sd < LIQ_BUFFER`, entao o `min(...)` nunca morde e a
    subestimacao passa a valer em 100% delas.

    O segundo assert e o que mantem o cap correto: mesmo na pior geometria que ainda passa, a
    perda real COM as taxas continua abaixo da margem (0,95 dela a 50x). O cap nao virou mentira
    -- so deixou de ser alcancado."""
    sd = (simulador.LIQ_BUFFER / lev) * 0.999999               # o mais degenerado que ainda abre
    assert simulador._liq_antes_do_stop(100.0, 100.0 * (1 - sd), lev, 1) is None
    assert simulador._risco_posicao(100.0, lev, 100.0, 100.0 * (1 - sd)) < 100.0   # nao capou
    assert lev * (sd + 2 * FEE) < 1.0                          # e a perda real cabe na margem


# ==================================================== [F-1][F-2] o risco que NAO se move
#
# `trades.risco_inicial` promete "quanto eu arrisquei ao ENTRAR" e grava "onde o stop estava ao
# SAIR": o `fechar()` o calcula a partir de `pos["stop"]`, que o trailing reescreve e persiste a
# cada ciclo. Quatro provas nos 62 trades de producao: stop de LONG ACIMA da entrada, maximo de
# R$177,55 contra um teto matematico de R$49,86, e casos com `risco ~= pnl` (177,55 vs 174,81).
#
# O conserto e coluna NOVA (`risco_abertura`), gravada na abertura e apenas COPIADA no
# fechamento -- nunca recalculada de campo mutavel. `risco_inicial` fica exatamente como estava:
# as 62 linhas ja gravadas significam o que significam, e reescreve-las coalharia duas series
# com o mesmo nome, que e pior que o defeito ([P2-40]).
#
# A DIRECAO do vies nao e uma so, e o plano registrou so uma delas. Como o trailing move o stop
# na direcao da entrada e depois ALEM dela, `abs(entrada - stop)` primeiro ENCOLHE e depois
# CRESCE. Antes de cruzar a entrada o denominador fica menor que o real e o R-multiplo sai
# INFLADO; depois de cruzar ele fica maior e o R-multiplo sai DEFLACIONADO (ate o cap da margem,
# que e de onde saem os R$177,55). Os testes abaixo fixam os dois lados: o defeito nao e "o
# numero parece melhor", e sim "o numero nao mede nada estavel".


def _abre_com_stop(sem_rede, preco=100.0, stop=98.0, valor=100.0, lev=10, direcao="LONG"):
    """Abre pelo caminho REAL (`simulador.abrir`), que e o unico que grava as ancoras."""
    _sem_tetos()
    sem_rede(preco)
    sid = semear_sinal(direcao=direcao, preco=preco, stop=stop)
    return simulador.abrir(sid, valor, lev)


def _pos(pid):
    with db.conectar() as c:
        return dict(c.execute("SELECT * FROM posicoes WHERE id=?", (pid,)).fetchone())


def test_f1_a_abertura_grava_as_duas_ancoras_a_mercado(banco, sem_rede):
    """Entrada 100, stop 98, R$100 a 10x: 2% x 10x x R$100 = R$20 de risco-ate-o-stop."""
    p = _pos(_abre_com_stop(sem_rede))
    assert p["stop_abertura"] == pytest.approx(98.0)
    assert p["risco_abertura"] == pytest.approx(20.0)
    assert p["stop"] == pytest.approx(98.0)          # na abertura as duas coincidem, e so aqui


def test_f1_o_trailing_move_o_stop_e_NAO_move_o_risco_da_abertura(banco, sem_rede):
    """O teste que so passa se a causa foi atacada.

    Abre (entrada 100, stop 98, R$100 a 10x => risco real R$20), deixa o TRAILING subir o stop
    -- nao um UPDATE de teste, o trailing de verdade, que e o mecanismo acusado -- fecha, e
    pergunta as duas coisas na mesma linha do banco.

    O legado nao grava um numero errado por acaso: ele grava exatamente
    `_risco_posicao(..., stop_de_saida)`, e a assercao confere isso contra o stop OBSERVADO. E
    a diferenca nao e de arredondamento -- e um fator de quase 4 sobre o risco que a posicao
    de fato correu. Se `risco_abertura` fosse calculado no `fechar()` a partir de qualquer
    campo disponivel ali, daria o mesmo numero do legado: `pos["stop"]` e a unica geometria que
    existe naquele ponto, e ela ja se moveu.

    A versao-sintoma que este card NAO fez: capar `risco_inicial` no teto matematico
    (`valor x lev x sd_max`). Os R$177,55 medidos em producao virariam R$49,86, o numero
    pararia de ofender a vista, e continuaria sendo o risco de um stop que a posicao nunca teve
    na entrada. Corrigir a APARENCIA do sintoma e o que fecharia o card sem consertar nada."""
    pid = _abre_com_stop(sem_rede)
    sem_rede(110.0)
    simulador.atualizar()
    p = _pos(pid)
    assert p["stop"] > p["entrada"]                    # o trailing levou o stop ALEM da entrada
    assert p["stop_abertura"] == pytest.approx(98.0)   # a ancora nao se mexeu
    assert p["risco_abertura"] == pytest.approx(20.0)

    simulador.fechar(pid, "prova", 110.0)
    t = db.listar("trades", 1)[0]
    assert t["risco_abertura"] == pytest.approx(20.0)  # o conserto: risco DA ENTRADA
    # o legado, intacto e errado de proposito: e o risco medido no stop de SAIDA
    assert t["risco_inicial"] == pytest.approx(
        simulador._risco_posicao(100.0, 10, 100.0, p["stop"]))
    assert t["risco_inicial"] > 3.5 * t["risco_abertura"]


def test_f1_o_vies_do_legado_tem_OS_DOIS_sinais(banco, sem_rede):
    """A correcao de fato ao plano, medida em vez de argumentada.

    O plano registra o vies do `risco_inicial` como sendo "para parecer melhor". Ele tem os
    DOIS sinais, e o motivo e geometrico: o trailing move o stop na direcao da entrada e depois
    ALEM dela, entao `abs(entrada - stop)` primeiro ENCOLHE e so depois cresce.

    Roda na unidade `preco`, e isso NAO e detalhe de arranjo: e a regra sob a qual os 62 trades
    de producao nasceram. Caracterizar o defeito com a regra nova descreveria um historico que
    nunca existiu.

    Mesma geometria de entrada nos dois casos (entrada 100, stop 99,50 => risco real R$5), so o
    caminho do preco muda:
      - preco 102: o stop trailado (102 x 0,98 = 99,96) para ENTRE o stop de entrada e a
        entrada. O denominador encolhe para R$0,40 e o R-multiplo sai INFLADO em 12,5x.
      - preco 110: o stop (107,80) passa da entrada, o denominador cresce para R$78 e o
        R-multiplo sai DEFLACIONADO -- e e dai que vem o maximo de R$177,55 dos 62 trades.

    Ou seja: o defeito nao e "o numero parece melhor", e sim "o numero nao mede nada estavel".
    Quem tentasse consertar so o lado inflado deixaria metade do defeito de pe.

    Nota que vale para o [N-13], e que NAO e conserto: com 1R para armar e 1R de distancia o
    stop cai exatamente NA entrada no instante da armacao e so se afasta dela depois, entao o
    lado inflado deixa de ser alcancavel. O legado continua enviesado -- so que sempre para o
    mesmo lado. E mais uma razao para o denominador ser GRAVADO, e nao inferido."""
    db.set_config("trailing_unidade", "preco")
    pid = _abre_com_stop(sem_rede, stop=99.5)
    assert _pos(pid)["risco_abertura"] == pytest.approx(5.0)
    sem_rede(102.0)
    simulador.atualizar()
    simulador.fechar(pid, "prova", 102.0)
    t = db.listar("trades", 1)[0]
    assert t["risco_abertura"] == pytest.approx(5.0)
    assert t["risco_inicial"] < 1.0                    # denominador encolhido: R-multiplo INFLADO

    pid2 = _abre_com_stop(sem_rede, stop=99.5)
    sem_rede(110.0)
    simulador.atualizar()
    simulador.fechar(pid2, "prova", 110.0)
    t2 = db.listar("trades", 1)[0]
    assert t2["risco_abertura"] == pytest.approx(5.0)
    assert t2["risco_inicial"] > 50.0                  # denominador inchado: R-multiplo DEFLACIONADO


def test_f1_o_caminho_post_only_grava_as_ancoras_no_preco_do_FILL(banco, sem_rede):
    """[EX-1] A ordem que descansa nasce posicao em `_abrir_da_ordem`, que e um SEGUNDO ponto de
    abertura. Consertar so o `abrir()` deixaria metade do sistema gravando o risco errado -- e
    seria a metade que o projeto esta ligando agora.

    As ancoras saem do `preco_limite` (99,90), nao do preco de mercado no instante do fill
    (99,50): post-only significa que o preco foi NOSSO, e a posicao nasce no limite."""
    _sem_tetos()
    db.set_config("exec_modo", "post_only")
    sem_rede(100.0)
    sid = semear_sinal(preco=100.0, stop=98.0)
    tipo, oid = simulador.executar(sid, 100.0, 10)
    assert tipo == "ordem"
    sem_rede(99.5)                                    # o preco veio ate a ordem
    assert simulador.processar_ordens()["preenchidas"] == 1
    with db.conectar() as c:
        pid = c.execute("SELECT posicao_id FROM ordens WHERE id=?", (oid,)).fetchone()[0]
    p = _pos(pid)
    assert p["entrada"] == pytest.approx(99.90)
    assert p["stop_abertura"] == pytest.approx(99.90 * 0.98)
    assert p["risco_abertura"] == pytest.approx(20.0)  # 2% x 10x x R$100, sobre o preco do fill

    sem_rede(110.0)
    simulador.atualizar()
    simulador.fechar(pid, "prova", 110.0)
    t = db.listar("trades", 1)[0]
    assert t["risco_abertura"] == pytest.approx(20.0)
    assert t["risco_inicial"] > 3.5 * t["risco_abertura"]   # o legado seguiu o stop trailado


def test_f2_as_metricas_dividem_pelo_denominador_que_nao_se_move(banco, sem_rede):
    """O R-multiplo do mesmo trade sob os dois denominadores, lado a lado.

    Pnl +R$99 (10% do ativo x 10x, menos R$1 de taxa). Sobre o risco da ABERTURA (R$20) sao
    4,95R -- o que o operador de fato arriscou para ganhar aquilo. Sobre o legado (o stop
    trailado, que passou da entrada) sao menos de 1,5R. Nao e diferenca de arredondamento entre
    os dois numeros: e um fator maior que 3, no mesmo trade, no mesmo instante."""
    pid = _abre_com_stop(sem_rede)
    sem_rede(110.0)
    simulador.atualizar()
    simulador.fechar(pid, "prova", 110.0)
    t = db.listar("trades", 1)[0]
    m = db.metricas()
    assert m["n_r_ab"] == 1
    assert m["expectancia_r_ab"] == pytest.approx(99.0 / 20.0, abs=1e-3)   # 4,95R: o real
    assert m["expectancia_r"] == pytest.approx(99.0 / t["risco_inicial"], abs=1e-3)
    assert m["expectancia_r"] < m["expectancia_r_ab"] / 3


def test_f2_trade_antigo_sem_a_coluna_nova_NAO_entra_na_serie(banco):
    """"Nao invente numero para eles". O historico de producao tem `risco_inicial` gravado e
    `risco_abertura` NULL; derivar um do outro seria fabricar exatamente o numero de que o card
    veio desconfiar. `n_r_ab` publica quantos trades sustentam a serie honesta -- e zero e uma
    resposta, nao uma falha."""
    with db.conectar() as c:
        c.execute("INSERT INTO trades(ativo,direcao,pnl_reais,taxa,conviccao,fechado_em,"
                  "risco_inicial) VALUES('BTC/USDT','LONG',10.0,1.0,70,'2026-08-22 10:00:00',5.0)")
    m = db.metricas()
    assert m["expectancia_r"] == pytest.approx(2.0)     # a serie legada continua respondendo
    assert m["n_r_ab"] == 0                             # e a nova diz, sem rodeio, que nao mediu
    assert m["expectancia_r_ab"] == 0 and m["sqn_r_ab"] == 0
