# -*- coding: utf-8 -*-
"""Item 2 do [P2-6]: `simulador._pnl()` e `simulador._preco_liquidacao()`.

Aqui mora a aritmetica que decide quanto o historico de pesquisa registra. Um erro de sinal
ou de fator nao levanta excecao nenhuma -- ele so grava um numero errado, para sempre, e o
M4 depois mede estrategia em cima dele. Por isso as asseracoes sao de VALOR, com a conta
escrita ao lado, e nao de "nao explodiu".
"""
import pytest

import db
import simulador
from conftest import semear_posicao


def pos(direcao="LONG", entrada=100.0, valor=100.0, lev=10, stop=95.0):
    return {"direcao": direcao, "entrada": entrada, "valor_reais": valor,
            "alavancagem": lev, "stop": stop}


# ---------------------------------------------------------------- _pnl: direcao e fator

def test_long_ganha_com_o_preco_subindo(banco):
    """+1% no ativo a 10x = +10% sobre a margem. R$100 -> +R$10 bruto, menos a taxa dos
    dois lados (2 x 0,05% x R$1.000 nocional = R$1) = +R$9. E a conta que o `test_sim.py`
    conferia com um print; aqui ela falha se mudar."""
    pnl, taxa, move = simulador._pnl(pos(), 101.0)
    assert move == pytest.approx(0.01)
    assert taxa == pytest.approx(1.0)
    assert pnl == pytest.approx(9.0)


def test_short_ganha_com_o_preco_caindo(banco):
    """O `d = 1 if LONG else -1` e a unica coisa que separa lucro de prejuizo aqui.
    Simetria com o LONG: mesmo modulo, mesma taxa."""
    pnl, taxa, move = simulador._pnl(pos(direcao="SHORT"), 99.0)
    assert move == pytest.approx(0.01)
    assert pnl == pytest.approx(9.0)


def test_short_perde_com_o_preco_subindo(banco):
    pnl, _, move = simulador._pnl(pos(direcao="SHORT"), 101.0)
    assert move == pytest.approx(-0.01)
    assert pnl == pytest.approx(-11.0)          # -10 de bruto, -1 de taxa


def test_alavancagem_multiplica_o_resultado_e_a_taxa(banco):
    """A taxa e cobrada sobre o NOCIONAL, entao ela escala com a alavancagem junto com o
    P&L -- que e a razao de "a taxa decide" no README."""
    p1, t1, _ = simulador._pnl(pos(lev=1), 101.0)
    p10, t10, _ = simulador._pnl(pos(lev=10), 101.0)
    assert (p1, t1) == (pytest.approx(0.9), pytest.approx(0.1))
    assert (p10, t10) == (pytest.approx(9.0), pytest.approx(1.0))


def test_taxa_le_a_config_e_conta_os_dois_lados(banco):
    db.set_config("taxa_por_lado", "0.001")
    _, taxa, _ = simulador._pnl(pos(), 100.0)
    assert taxa == pytest.approx(2.0)           # 2 x 0,1% x R$1.000


def test_taxa_invalida_na_config_cai_no_padrao(banco):
    """Mesmo [P1-8] de `guarda_risco`: config podre nao pode virar excecao no meio de um
    fechamento -- a posicao ficaria aberta sem ninguem saber por que."""
    db.set_config("taxa_por_lado", "muito")
    _, taxa, _ = simulador._pnl(pos(), 100.0)
    assert taxa == pytest.approx(1.0)


# ---------------------------------------------------------------- _pnl: o cap na margem

def test_nunca_perde_mais_que_a_margem(banco):
    """Paper trading sem chamada de margem: o maximo que se perde e o que se pos. Sem o
    cap, um gap de -50% a 10x gravaria -R$501 numa posicao de R$100 e a banca ficaria
    negativa."""
    pnl, _, move = simulador._pnl(pos(), 50.0)
    assert move == pytest.approx(-0.5)          # o movimento do ativo continua honesto
    assert pnl == pytest.approx(-100.0)         # o P&L e que fica capado na margem


def test_o_cap_nao_atrapalha_o_lucro(banco):
    pnl, _, _ = simulador._pnl(pos(), 150.0)
    assert pnl == pytest.approx(499.0)          # 100 x 10 x 0,5 - 1 de taxa


def test_perda_dentro_da_margem_passa_intacta(banco):
    pnl, _, _ = simulador._pnl(pos(), 99.5)
    assert pnl == pytest.approx(-6.0)           # -5 de bruto, -1 de taxa


# ---------------------------------------------------------------- _pnl: guardas de ÷0

@pytest.mark.parametrize("campo", ["entrada", "alavancagem"])
def test_entrada_ou_alavancagem_zero_devolve_zeros(banco, campo):
    """Posicao degenerada nao pode virar ZeroDivisionError dentro do `for` do ciclo: era
    exatamente esse tipo de excecao que o [P1-1] mostrou ser capaz de deixar as outras
    posicoes sem stop."""
    p = pos()
    p[campo] = 0
    assert simulador._pnl(p, 101.0) == (0.0, 0.0, 0.0)


# ---------------------------------------------------------------- _preco_liquidacao

@pytest.mark.parametrize("entrada,d,lev,esperado", [
    (100.0, 1, 10, 91.0),        # LONG: 100 x (1 - 0,9/10)
    (100.0, -1, 10, 109.0),      # SHORT: espelhado acima da entrada
    (100.0, 1, 20, 95.5),        # o dobro de alavancagem, metade da distancia
    (100.0, 1, 1, 10.0),         # 1x: so liquida com -90%
    (100.0, 1, 100, 99.1),
])
def test_preco_liquidacao(entrada, d, lev, esperado):
    assert simulador._preco_liquidacao(entrada, d, lev) == pytest.approx(esperado)


def test_liquidacao_do_long_fica_abaixo_e_a_do_short_acima(banco):
    assert simulador._preco_liquidacao(100.0, 1, 5) < 100.0 < simulador._preco_liquidacao(100.0, -1, 5)


def test_alavancagem_zero_nao_divide_por_zero(banco):
    assert simulador._preco_liquidacao(100.0, 1, 0) == 0.0


def test_a_distancia_ate_a_liquidacao_e_o_buffer_dividido_pela_alavancagem(banco):
    """Amarra o preco de liquidacao a constante que o documenta. Se alguem mudar
    `LIQ_BUFFER` sem querer, isto acusa em vez de deixar passar."""
    for lev in (2, 5, 10, 25, 50):
        liq = simulador._preco_liquidacao(100.0, 1, lev)
        assert (100.0 - liq) / 100.0 == pytest.approx(simulador.LIQ_BUFFER / lev)


# ------------------------------------------------- as duas funcoes juntas: coerencia

@pytest.mark.parametrize("lev", [2, 5, 10, 20, 50])
def test_fechar_no_preco_de_liquidacao_perde_o_buffer_mais_a_taxa(banco, lev):
    """A coerencia que o [P2-18] existe para nao quebrar: liquidar em `_preco_liquidacao`
    tem de custar ~LIQ_BUFFER da margem, e nao a margem inteira nem metade dela. O bruto e
    `valor x lev x (LIQ_BUFFER/lev)` = `valor x LIQ_BUFFER` -- independe da alavancagem, e
    so a taxa cresce com ela."""
    liq = simulador._preco_liquidacao(100.0, 1, lev)
    pnl, taxa, _ = simulador._pnl(pos(lev=lev), liq)
    assert pnl == pytest.approx(-(simulador.LIQ_BUFFER * 100.0) - taxa)


def test_alavancagem_extrema_liquida_exatamente_na_margem(banco):
    """A 100x a taxa sozinha come os 10% que sobravam do buffer: a perda encosta no cap.
    Documenta o ponto em que "liquidacao" e "perda total" passam a ser a mesma coisa."""
    liq = simulador._preco_liquidacao(100.0, 1, 100)
    pnl, _, _ = simulador._pnl(pos(lev=100), liq)
    assert pnl == pytest.approx(-100.0)


def test_fechar_grava_o_retorno_alavancado_e_o_risco_inicial(banco, sem_rede):
    """Fim a fim, sem rede: o que `_pnl` calcula tem de chegar na tabela `trades` com o
    mesmo valor, e o `ret_pct` gravado e o retorno sobre a MARGEM (move x lev), nao o
    movimento do ativo -- e a coluna que o M4 vai ler."""
    pid = semear_posicao(entrada=100.0, valor_reais=100.0, alavancagem=10, stop=98.0)
    pnl = simulador.fechar(pid, "teste", 101.0)
    assert pnl == pytest.approx(9.0)
    t = db.listar("trades", 1)[0]
    assert t["pnl_reais"] == pytest.approx(9.0)
    assert t["ret_pct"] == pytest.approx(10.0)          # 1% do ativo x 10x
    assert t["taxa"] == pytest.approx(1.0)
    assert t["risco_inicial"] == pytest.approx(20.0)    # 2% de distancia x 10x x R$100
    assert db.get_banca()["atual"] == pytest.approx(1009.0)


def test_fechar_duas_vezes_nao_duplica_o_trade(banco, sem_rede):
    """`rowcount != 1` no UPDATE: a segunda chamada devolve None e nao mexe na banca."""
    pid = semear_posicao(entrada=100.0, valor_reais=100.0, alavancagem=10)
    assert simulador.fechar(pid, "teste", 101.0) == pytest.approx(9.0)
    assert simulador.fechar(pid, "teste", 101.0) is None
    assert len(db.listar("trades", 10)) == 1


# ================================================================ [P2-18] o fill do stop
# O gatilho nao e o fill. Entre dois polls de 15s o preco rompe o stop e segue; fechar no
# preco do stop grava execucao que nunca houve, sempre para o mesmo lado (perda menor,
# trailing melhor). As asseracoes abaixo sao de VALOR pelo mesmo motivo do topo do arquivo:
# um fill otimista nao levanta excecao, so grava o numero errado no historico de pesquisa.

@pytest.mark.parametrize("d,stop,preco,liq,esperado,nota", [
    (1,  100.0, 98.0,  91.0,  98.0,  "LONG: gap abaixo do stop -> fill no preco observado"),
    (1,  100.0, 100.0, 91.0,  100.0, "LONG: preco exatamente no stop -> fill no stop"),
    (1,  100.0, 103.0, 91.0,  100.0, "LONG: preco melhor que o stop nao melhora o fill"),
    (1,  100.0, 85.0,  91.0,  91.0,  "LONG: passou da liquidacao -> piso na liq"),
    (-1, 100.0, 102.0, 109.0, 102.0, "SHORT: gap acima do stop"),
    (-1, 100.0, 100.0, 109.0, 100.0, "SHORT: preco exatamente no stop"),
    (-1, 100.0, 97.0,  109.0, 100.0, "SHORT: preco melhor que o stop nao melhora o fill"),
    (-1, 100.0, 115.0, 109.0, 109.0, "SHORT: passou da liquidacao -> teto na liq"),
])
def test_fill_stop(d, stop, preco, liq, esperado, nota):
    assert simulador._fill_stop(stop, preco, liq, d) == pytest.approx(esperado), nota


@pytest.mark.parametrize("d,stop,preco", [(1, 100.0, 85.0), (-1, 100.0, 115.0)])
def test_o_fill_nunca_fica_melhor_que_o_stop_de_hoje(d, stop, preco):
    """A direcao da mudanca e invariante, nao coincidencia: o [P2-18] APERTA a guarda, e
    apertar pode (CLAUDE.md secao 2). Um fill melhor que `stop` seria afrouxar -- e e o que
    um piso escrito como `max(min(stop,preco), liq)` faria quando o stop cai ABAIXO da
    liquidacao. Por isso a forma e `min(stop, max(preco, liq))`."""
    for liq in (0.0, 50.0, 91.0, 99.0, 100.0, 109.0, 150.0):
        fill = simulador._fill_stop(stop, preco, liq, d)
        assert (fill <= stop) if d == 1 else (fill >= stop)


@pytest.mark.parametrize("d", [1, -1])
def test_sem_liquidacao_modelada_o_piso_some_em_vez_de_zerar_o_gap(d):
    """`_preco_liquidacao` devolve 0.0 quando a alavancagem e falsy. Zero e "nao ha liq
    modelada", nao "a liq e no preco zero" -- e para um SHORT um teto em 0.0 anularia o gap
    inteiro em silencio. O `if liq` existe para isso."""
    assert simulador._fill_stop(100.0, 98.0, 0.0, d) == pytest.approx(98.0 if d == 1 else 100.0)
    assert simulador._fill_stop(100.0, 102.0, 0.0, d) == pytest.approx(100.0 if d == 1 else 102.0)


# ---------------------------------------------- fim a fim: o que chega na tabela `trades`

def _fecha_por_stop(sem_rede, **kw):
    """Semeia uma posicao, poe o preco ao vivo em `preco` e roda um ciclo de marcacao.
    Devolve (id, eventos, trade gravado ou None)."""
    preco = kw.pop("preco")
    db.set_config("trailing_ativo", "0")        # o trailing tem teste proprio abaixo
    pid = semear_posicao(**kw)
    sem_rede(preco)
    eventos = simulador.atualizar()
    trades = db.listar("trades", 1)
    return pid, eventos, (trades[0] if trades else None)


def test_gap_no_stop_fecha_no_preco_observado_e_marca_o_motivo(banco, sem_rede):
    """O criterio de aceite do card, literal: LONG com stop 100 e preco atual 98 fecha a
    98, nao a 100, com motivo `stop-gap`."""
    pid, eventos, t = _fecha_por_stop(sem_rede, direcao="LONG", entrada=102.0, valor_reais=100.0,
                                      alavancagem=10, stop=100.0, preco=98.0)
    assert t["saida"] == pytest.approx(98.0)
    assert t["motivo_saida"] == "stop-gap"
    assert eventos == [(pid, "stop-gap")]


def test_o_gap_custa_dinheiro_de_verdade(banco, sem_rede):
    """Nao basta gravar outro preco: o P&L tem de piorar na mesma proporcao. -1,96% ate o
    stop viram -3,92% ate o fill, a 10x sobre R$100 de margem."""
    _, _, t = _fecha_por_stop(sem_rede, direcao="LONG", entrada=102.0, valor_reais=100.0,
                              alavancagem=10, stop=100.0, preco=98.0)
    esperado = 100 * 10 * (98.0 / 102.0 - 1) - 1.0          # bruto alavancado - taxa dos 2 lados
    assert t["pnl_reais"] == pytest.approx(esperado)
    assert t["pnl_reais"] < -20.6                            # no stop exato seria -20,61


def test_sem_gap_o_comportamento_e_identico_ao_de_antes(banco, sem_rede):
    """Poll que pega o toque exato: fecha no stop, motivo sem sufixo. E o caso comum, e ele
    nao pode mudar -- senao todo trade do historico ganharia `-gap` sem ter havido gap."""
    pid, eventos, t = _fecha_por_stop(sem_rede, direcao="LONG", entrada=102.0, valor_reais=100.0,
                                      alavancagem=10, stop=100.0, preco=100.0)
    assert t["saida"] == pytest.approx(100.0)
    assert t["motivo_saida"] == "stop"
    assert eventos == [(pid, "stop")]


def test_preco_entre_o_stop_e_a_entrada_nao_fecha_nada(banco, sem_rede):
    """A outra metade de "sem gap": o stop nem foi tocado. A posicao segue aberta e nenhum
    trade e gravado."""
    _, eventos, t = _fecha_por_stop(sem_rede, direcao="LONG", entrada=102.0, valor_reais=100.0,
                                    alavancagem=10, stop=100.0, preco=101.0)
    assert eventos == []
    assert t is None
    assert db.listar("posicoes", 1)[0]["status"] == "aberta"


def test_short_tambem_fecha_no_pior_preco(banco, sem_rede):
    """O `d = 1 if LONG else -1` de novo: para o SHORT o pior e o mais ALTO."""
    _, _, t = _fecha_por_stop(sem_rede, direcao="SHORT", entrada=98.0, valor_reais=100.0,
                              alavancagem=10, stop=100.0, preco=102.0)
    assert t["saida"] == pytest.approx(102.0)
    assert t["motivo_saida"] == "stop-gap"


def test_o_trailing_tambem_fecha_no_pior_preco(banco, sem_rede):
    """Terceiro item do aceite. O trailing usa o MESMO caminho (`_fecha_stop`), entao o
    vies era o mesmo -- e ele doia mais ali: o trailing so age em lucro, e o gap come
    justamente o ganho travado."""
    db.set_config("trailing_ativo", "1")
    pid = semear_posicao(direcao="LONG", entrada=100.0, valor_reais=100.0,
                         alavancagem=10, stop=105.0)         # stop acima da entrada = lucro travado
    sem_rede(103.0)
    eventos = simulador.atualizar()
    t = db.listar("trades", 1)[0]
    assert t["saida"] == pytest.approx(103.0)
    assert t["motivo_saida"] == "trailing-gap"
    assert eventos == [(pid, "trailing-gap")]


def test_o_gap_nao_passa_do_preco_de_liquidacao(banco, sem_rede):
    """A metade que o card manda NAO mexer, vista do outro lado. Passado o preco de liq a
    corretora ja tomou a margem: nao existe fill pior. Sem o piso, o desempate
    stop x liquidacao de `_marcar_uma` gravaria -R$100 onde a liquidacao grava -R$91."""
    _, _, t = _fecha_por_stop(sem_rede, direcao="LONG", entrada=100.0, valor_reais=100.0,
                              alavancagem=10, stop=98.0, preco=85.0)
    liq = simulador._preco_liquidacao(100.0, 1, 10)
    assert t["saida"] == pytest.approx(liq)                  # 91,0 e nao 85,0
    assert t["motivo_saida"] == "stop-gap"
    assert t["pnl_reais"] == pytest.approx(-(simulador.LIQ_BUFFER * 100.0) - t["taxa"])


def test_a_liquidacao_continua_fechando_no_preco_de_liquidacao(banco, sem_rede):
    """Regressao explicita: o card decide manter a liquidacao como esta, e o motivo nao
    ganha sufixo. Aqui o stop esta MAIS LONGE da entrada que a liq, entao o desempate manda
    para o ramo de liquidacao."""
    db.set_config("trailing_ativo", "0")
    pid = semear_posicao(direcao="LONG", entrada=100.0, valor_reais=100.0,
                         alavancagem=10, stop=80.0)
    sem_rede(70.0)
    eventos = simulador.atualizar()
    t = db.listar("trades", 1)[0]
    assert t["saida"] == pytest.approx(simulador._preco_liquidacao(100.0, 1, 10))
    assert t["motivo_saida"] == "liquidacao"
    assert eventos == [(pid, "LIQUIDADO")]


def test_as_metricas_leem_o_trade_com_gap_sem_quebrar(banco, sem_rede):
    """Quarto item do aceite. `db.metricas()` faz `SELECT *` e nunca compara `motivo_saida`
    (varredura do repositorio colada no relatorio do card) -- mas o P&L pior entra nas
    contas, e e isso que se confere aqui: conta como perda e mexe no R-multiplo."""
    _fecha_por_stop(sem_rede, direcao="LONG", entrada=102.0, valor_reais=100.0,
                    alavancagem=10, stop=100.0, preco=98.0)
    m = db.metricas()
    assert m["n_trades"] == 1
    assert m["win_rate"] == 0
    assert m["pnl_total"] == pytest.approx(round(100 * 10 * (98.0 / 102.0 - 1) - 1.0, 2))
    assert m["expectancia_r"] != 0                           # risco_inicial gravado -> R vivo


# ============================== [F-12] a config do laco de marcacao, lida uma vez so

def _contar_get_config(monkeypatch):
    """Envelopa `db.get_config` contando as chamadas, sem mudar o que ela devolve."""
    n = {"v": 0}
    real = db.get_config

    def contando():
        n["v"] += 1
        return real()

    monkeypatch.setattr(db, "get_config", contando)
    return n


def test_f12_pnl_com_cfg_dado_nao_abre_o_banco(banco, monkeypatch):
    """[F-12] O parametro existe para uma coisa so: nao reabrir o banco. Se `_pnl` ainda
    chamar `get_config()` tendo recebido a config, o teste falha em vez de so ficar lento --
    o custo do defeito e invisivel no resultado, entao a prova tem de ser sobre a CHAMADA."""
    monkeypatch.setattr(db, "get_config",
                        lambda: pytest.fail("_pnl abriu o banco mesmo com cfg no parametro"))
    pnl, taxa, move = simulador._pnl(pos(), 101.0, {"taxa_por_lado": "0.0005"})
    assert (move, taxa, pnl) == (pytest.approx(0.01), pytest.approx(1.0), pytest.approx(9.0))


def test_f12_pnl_sem_cfg_continua_lendo_a_config_de_agora(banco, monkeypatch):
    """A outra metade, e ela e deliberada: `fechar()` e chamado de FORA do ciclo (API,
    panico, auto-trader) e ali a taxa vigente e a certa. Um default que nao lesse o banco
    congelaria a config no valor do ultimo ciclo do worker."""
    n = _contar_get_config(monkeypatch)
    db.set_config("taxa_por_lado", "0.001")
    _, taxa, _ = simulador._pnl(pos(), 101.0)
    assert n["v"] == 1
    assert taxa == pytest.approx(2.0)            # 2 x 0,1% x R$1.000 de nocional


def test_f12_a_marcacao_le_a_config_uma_vez_por_CICLO_e_nao_por_posicao(banco, sem_rede,
                                                                        monkeypatch):
    """[F-12] Era uma conexao SQLite nova + PRAGMA + SELECT da tabela inteira + commit POR
    POSICAO, a cada 15 s, para ler um numero que nao muda dentro do ciclo.

    A asseracao e `== 1` e nao `<= n`: o ponto do card e que o custo pare de crescer com o
    numero de posicoes, e um teto frouxo deixaria a leitura por posicao voltar de mansinho
    numa carteira pequena."""
    for i in range(5):
        semear_posicao(ativo=f"MOEDA{i}/USDT", entrada=100.0, stop=50.0,
                       valor_reais=50.0, alavancagem=2)
    n = _contar_get_config(monkeypatch)
    simulador.atualizar()
    assert simulador.ultima_marcacao["ok"] == 5      # as cinco foram marcadas de fato
    assert n["v"] == 1


def test_f12_a_config_do_ciclo_e_a_MESMA_para_todas_as_posicoes(banco, sem_rede, monkeypatch):
    """Efeito colateral que vale como garantia, e e o mesmo argumento do `_trailing_cfg`:
    com a leitura por posicao, um `POST /config` no meio do laco marcava metade da carteira
    com a taxa velha e metade com a nova. Aqui a config muda DEPOIS da primeira posicao e
    nenhuma das cinco enxerga a mudanca."""
    for i in range(5):
        semear_posicao(ativo=f"MOEDA{i}/USDT", entrada=100.0, stop=50.0,
                       valor_reais=100.0, alavancagem=10, preco_atual=100.0)
    real = simulador._marcar_uma
    vistos = []

    def espiando(pos, trail, eventos, cfg=None):
        vistos.append((cfg or {}).get("taxa_por_lado"))
        db.set_config("taxa_por_lado", "0.009")      # alguem mexe no painel no meio do laco
        return real(pos, trail, eventos, cfg)

    monkeypatch.setattr(simulador, "_marcar_uma", espiando)
    simulador.atualizar()
    assert vistos == ["0.0005"] * 5
