# -*- coding: utf-8 -*-
"""Territorio T-DECLARACAO (onda 2 do M4): o que a API DECLARA sobre risco e guardas.

Tres coisas moram aqui, e a linha que as une e a mesma: numero de risco que o sistema usa
sem dizer em voz alta e numero que ninguem audita.

    [P1-11]  a contagem do cap geometrico exposta em `/status`
    [Q-3]    os perfis `experimento`/`conservador` e o perfil ATIVO derivado
    [Q-3]    o racional por parametro no catalogo de config do [P1-8]
"""
import pytest

import db
from conftest import semear_posicao, semear_sinal


@pytest.fixture
def cliente(banco):
    """TestClient sem `with`: o `lifespan` -- e portanto a thread do worker -- nao sobe.

    `client=("127.0.0.1", ...)` porque o peer padrao do TestClient ("testclient") nao e
    loopback, e sem `DASH_PASS` o app responde 503 a tudo que venha de fora (o [P0-1]).
    Mesmo motivo, e mesma solucao, do `test_auth.py` e do `test_regressoes_p1.py`.
    """
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app, client=("127.0.0.1", 5555))


# ======================================================= [P1-11] cap geometrico no /status

@pytest.fixture
def caps_zerados(monkeypatch):
    """`autotrader.CAPS_GEOMETRIA` e estado de MODULO (cumulativo na vida do processo, que e
    o ponto dele). Trocar por um dicionario novo por teste evita que a ordem dos testes -- ou
    qualquer outro que chame `_cap_geometrico` -- decida o numero asseverado aqui."""
    import autotrader
    monkeypatch.setattr(autotrader, "CAPS_GEOMETRIA", {"total": 0, "ultimo": None})
    return autotrader


def test_status_publica_a_contagem_do_cap_geometrico(cliente, caps_zerados):
    """Terceiro item do aceite do [P1-11]: "contagem exposta em `/status`".

    Antes disto o cap so existia no log e no resumo de UM ciclo do auto-trader -- e o resumo
    do ciclo seguinte apaga o anterior, entao "quantas vezes isso ja agiu?" nao tinha
    resposta sem abrir o `plataforma.log` na VM.
    """
    j = cliente.get("/status").json()
    assert j["caps_geometria"] == {"total": 0, "ultimo": None}

    # o caso do proprio aceite do card: stop de 5%, lev por conviccao 20 -> teto 14
    # (0,8 * 0,9 / 0,05 = 14,4, truncado para baixo).
    assert caps_zerados._cap_geometrico(20, 0.05, "INJ/USDT") == 14.0

    j = cliente.get("/status").json()
    assert j["caps_geometria"]["total"] == 1
    assert j["caps_geometria"]["ultimo"]["ativo"] == "INJ/USDT"
    assert j["caps_geometria"]["ultimo"]["lev_conviccao"] == 20
    assert j["caps_geometria"]["ultimo"]["lev_efetiva"] == 14.0


def test_o_cap_nao_entra_no_criterio_de_saude(cliente, caps_zerados):
    """`saudavel` continua `not (cego or cego_pos)`. O cap agindo e a guarda FUNCIONANDO --
    trata-lo como sintoma faria o painel pintar de vermelho justamente o bot que se protegeu.
    Mexer no detector de cegueira e decisao do dono (CLAUDE.md sec. 2)."""
    caps_zerados._cap_geometrico(20, 0.05, "SUI/USDT")
    j = cliente.get("/status").json()
    assert j["caps_geometria"]["total"] == 1 and j["saudavel"] is True


def test_a_contagem_do_cap_nao_vai_para_o_estado(cliente, caps_zerados):
    """O `/estado` e polido a cada 3s pelo painel e a franquia de saida da Azure e 15 GB/mes
    (CLAUDE.md sec. 2). Diagnostico cumulativo mora no `/status`, que o front so busca no
    portao de login. Se um dia alguem mover isto para o `/estado`, este teste avisa."""
    assert "caps_geometria" not in cliente.get("/estado").json()


# ================================================== [Q-3] os dois perfis de risco

def test_o_perfil_experimento_e_o_default_vivo(banco):
    """A trava que impede o [Q-3] de virar uma SEGUNDA fonte da verdade sobre risco.

    `experimento` nao e uma proposta: e o retrato do que esta rodando. Se alguem "melhorar"
    os numeros do perfil sem mexer no `CONFIG_PADRAO` (ou o contrario), o rotulo do painel
    passa a dizer 'personalizado' com o sistema no default, ou pior, 'experimento' com outra
    coisa viva. E o mesmo erro que o [P2-16] pagou com o `config.py` da raiz -- dois arquivos
    reivindicando a mesma frase com valores diferentes. Comparacao LITERAL, de proposito.
    """
    for chave, valor in db.PERFIS_RISCO["experimento"].items():
        assert db.CONFIG_PADRAO[chave] == valor, chave


def test_o_conservador_respeita_os_numeros_da_base(banco):
    """O que o card chama de "alinhado a base": risco <=1% por trade e alavancagem <=2x, em
    TODAS as portas (o padrao do fluxo manual e o teto do auto-trader)."""
    c = db.PERFIS_RISCO["conservador"]
    assert float(c["risco_por_trade"]) <= 0.01
    assert float(c["alavancagem_padrao"]) <= 2
    assert float(c["auto_lev_max"]) <= 2 and float(c["auto_lev_min"]) <= 2


def test_todo_valor_de_perfil_passa_no_catalogo_do_p1_8(banco):
    """Perfil nao tem via expressa para o banco. Se um valor de perfil nao passasse pelo
    `_validar_config`, aplica-lo gravaria algo que o `POST /config` recusaria -- config que so
    existe porque entrou pela porta dos fundos."""
    import api
    for nome, vals in db.PERFIS_RISCO.items():
        for chave, valor in vals.items():
            assert api._validar_config(chave, valor), (nome, chave)


def test_todo_parametro_de_perfil_tem_racional_escrito(banco):
    """O item 1 do aceite do [Q-3]: "cada default divergente da base tem decisao + racional
    registrados". Perfil sem racional e numero trocado sem justificativa -- exatamente o que
    o card existe para acabar."""
    import api
    for chave in db.PERFIS_RISCO["experimento"]:
        assert api.CONFIG_RACIONAL.get(chave), chave


def test_perfil_ativo_num_banco_novo_e_experimento(banco):
    assert db.perfil_ativo() == "experimento"


def test_aplicar_o_conservador_troca_o_perfil_e_o_estado_conta(cliente):
    """Item 3 do aceite: perfis "trocaveis por um comando/config"."""
    r = cliente.post("/perfil", json={"perfil": "conservador"}).json()
    assert r["ok"] and r["perfil_anterior"] == "experimento"
    assert r["perfil_ativo"] == "conservador"
    assert cliente.get("/estado").json()["perfil_risco"] == "conservador"
    cfg = cliente.get("/config").json()
    assert float(cfg["risco_por_trade"]) == 0.01 and float(cfg["auto_lev_max"]) == 2


def test_a_troca_de_perfil_e_simetrica(cliente):
    """Volta pelo mesmo comando. Um mecanismo de risco so de ida nao e reversivel, e um
    experimento que nao se desfaz nao e experimento."""
    cliente.post("/perfil", json={"perfil": "conservador"})
    r = cliente.post("/perfil", json={"perfil": "experimento"}).json()
    assert r["perfil_ativo"] == "experimento"
    for chave, valor in db.PERFIS_RISCO["experimento"].items():
        assert db._igual_cfg(db.get_config()[chave], valor), chave


def test_a_normalizacao_do_post_config_nao_quebra_o_reconhecimento(cliente):
    """A armadilha que faz `perfil_ativo` precisar comparar NUMERO e nao string: o
    `_validar_config` grava float normalizado, entao mandar `alavancagem_padrao=10` devolve
    "10.0" ao banco enquanto o perfil diz "10". Com comparacao textual, gravar o proprio
    default marcaria o sistema como 'personalizado'."""
    cliente.post("/config", json={"alavancagem_padrao": 10})
    assert cliente.get("/config").json()["alavancagem_padrao"] == "10.0"    # normalizado
    assert cliente.get("/estado").json()["perfil_risco"] == "experimento"   # e ainda assim


def test_mexer_num_parametro_sozinho_derruba_o_rotulo_para_personalizado(cliente):
    """O perfil ativo e DERIVADO, nunca guardado. Se fosse uma chave no banco, este
    `POST /config` deixaria o rotulo dizendo 'conservador' com 3% de risco vivo -- um rotulo
    de risco que mente e pior que rotulo nenhum."""
    cliente.post("/perfil", json={"perfil": "conservador"})
    cliente.post("/config", json={"risco_por_trade": 0.03})
    assert cliente.get("/estado").json()["perfil_risco"] == "personalizado"


def test_perfil_desconhecido_e_recusado_sem_gravar_nada(cliente):
    r = cliente.post("/perfil", json={"perfil": "agressivissimo"})
    assert r.status_code == 422
    assert cliente.get("/estado").json()["perfil_risco"] == "experimento"


# ================================================== [Q-3] o catalogo com racional

def test_o_catalogo_publica_faixa_padrao_e_racional(cliente):
    j = cliente.get("/catalogo").json()
    p = j["parametros"]["risco_por_trade"]
    assert (p["tipo"], p["min"], p["max"], p["padrao"]) == ("float", 0.001, 0.2, "0.03")
    assert "ruína" in p["racional"] or "ruina" in p["racional"]
    assert j["perfil_ativo"] == "experimento"
    assert set(j["perfis"]) == {"experimento", "conservador"}


def test_o_catalogo_cobre_o_catalogo_inteiro_e_admite_o_que_nao_tem_racional(cliente):
    """`racional: None` e resposta honesta -- diz "esta chave nao teve decisao registrada" em
    vez de inventar uma justificativa para caber no formato."""
    import api
    j = cliente.get("/catalogo").json()["parametros"]
    assert set(j) == set(api.CONFIG_CATALOGO)
    assert j["timeframe"]["opcoes"][0] == "1m" and j["timeframe"]["racional"] is None


def test_o_catalogo_nao_devolve_valores_vigentes(cliente):
    """Quem quer valor pede `GET /config`. Repetir o valor aqui repetiria o `telegram_token`
    em mais uma resposta, sem ganho nenhum."""
    j = cliente.get("/catalogo").json()["parametros"]
    assert "valor" not in j["telegram_token"]


# ================================================== [Q-3] a tensao dos 15%, MEDIDA

def abre_ate_recusar(teto_tentativas, entrada, stop, cfg):
    """Abre posicoes dimensionadas pelo caminho REAL do auto-trader ate `simulador.abrir`
    recusar, e devolve (quantas abriram, mensagem da recusa).

    Usa `autotrader._alavancagem` e `_tamanho` de proposito, em vez de valores escolhidos a
    mao: a pergunta do card e "quantas posicoes o sistema VIVO consegue ter abertas", e a
    resposta depende do sizing real. Os dois sao lidos, nunca escritos -- `autotrader.py` e
    territorio do T-GUARDA nesta onda.
    """
    import autotrader
    import simulador
    lev = autotrader._alavancagem(cfg, 100, abs(entrada - stop) / entrada)
    valor = autotrader._tamanho(1000.0, float(cfg["risco_por_trade"]), lev, entrada, stop,
                                float(cfg["auto_max_valor_frac"]))
    assert valor > 0
    for n in range(teto_tentativas):
        sid = semear_sinal(preco=entrada, stop=stop)
        try:
            simulador.abrir(sid, valor, lev)
        except ValueError as e:
            return n, str(e)
    return teto_tentativas, ""


def test_no_experimento_o_teto_agregado_barra_antes_dos_cinco_slots(banco, sem_rede):
    """A tensao que o [Q-3] manda parar de ser implicita: 5 slots x 3% = 15% agregado contra
    um `risco_aberto_max` de 10%. Quem manda e o TETO, e a conta e esta -- com 3% por trade a
    QUARTA posicao e recusada, entao `auto_max_posicoes=5` nunca chega a valer.

    Nao e opiniao: `simulador.abrir` recusa quando `risco_ab + r_novo > teto`
    (simulador.py:185). O numero de slots vivo e config MORTA, e o [Q-3] registra isso em vez
    de baixa-lo para 3 -- baixar daria a impressao de que o slot e a guarda."""
    assert db.perfil_ativo() == "experimento"
    abertas, erro = abre_ate_recusar(6, 100.0, 98.0, db.get_config())
    assert abertas == 3, f"deveria barrar na quarta, barrou na {abertas + 1}a"
    assert "teto de risco aberto" in erro
    assert int(db.get_config()["auto_max_posicoes"]) == 5      # o slot nunca foi alcancado


def test_no_conservador_os_cinco_slots_cabem_exatamente_no_teto(cliente, sem_rede):
    """O outro lado da mesma conta, e a razao de o `conservador` mexer TAMBEM no
    `risco_aberto_max`: 5 x 1% = 5% = teto. Os dois numeros passam a dizer a mesma coisa em
    vez de um anular o outro em silencio."""
    cliente.post("/perfil", json={"perfil": "conservador"})
    cfg = db.get_config()
    abertas, erro = abre_ate_recusar(8, 100.0, 92.0, cfg)       # stop de 8%, tipico de alt 1h
    assert abertas == 5, f"os cinco slots deveriam caber, couberam {abertas}"
    assert "teto de risco aberto" in erro


def test_com_stop_curto_o_conservador_esbarra_na_margem_antes_dos_slots(cliente, sem_rede):
    """O que a construcao do perfil NAO resolve, e fica registrado em vez de escondido.

    Alavancagem baixa exige MAIS margem para o mesmo risco: 1% de risco com stop de 2% a 2x
    pede 25% da banca por posicao, e ai o `exposicao_max` (50%, teto de MARGEM) barra na
    terceira -- antes do teto de risco e antes dos slots. O perfil conservador so entrega os
    cinco slots com stops largos; com stop curto, quem manda e um terceiro numero.

    Subir `exposicao_max` no perfil resolveria a aritmetica e AFROUXARIA uma guarda, o que e
    do dono e nao de agente (CLAUDE.md sec. 2). Fica medido aqui."""
    cliente.post("/perfil", json={"perfil": "conservador"})
    abertas, erro = abre_ate_recusar(6, 100.0, 98.0, db.get_config())
    assert abertas == 2 and "teto de margem" in erro


# ============================== [P-3] as tres chaves de trailing em R, no catalogo do [P1-8]
#
# ANTES deste card o `POST /config` respondia 422 "chave desconhecida" as tres, e o
# `GET /catalogo` nao as listava. O efeito nao era cosmetico: a onda A pos o trailing para
# medir em R (`[N-13]`), entao a chave que DECIDE a politica de saida do vivo so valeria pelo
# default em producao, e reverter exigiria um DEPLOY em vez de um clique -- que e o motivo
# concreto da decisao D-7 ter segurado a VM ate aqui.

TRAILING_R = ("trailing_unidade", "trailing_arma_r", "trailing_dist_r")


def test_p3_o_post_config_aceita_as_tres_chaves_de_trailing_em_r(cliente):
    """O antes/depois deste card, na porta por onde o painel fala.

    As tres juntas num lote so, de proposito: `_validar_lote` e tudo-ou-nada, entao uma chave
    ainda sem verbete derrubaria as outras duas com ela."""
    r = cliente.post("/config", json={"trailing_unidade": "preco",
                                      "trailing_arma_r": 2, "trailing_dist_r": 1.5})
    assert r.status_code == 200, r.json()
    cfg = cliente.get("/config").json()
    assert cfg["trailing_unidade"] == "preco"
    assert float(cfg["trailing_arma_r"]) == 2.0 and float(cfg["trailing_dist_r"]) == 1.5


def test_p3_o_catalogo_publica_as_tres_com_racional(cliente):
    """Sem verbete no `CONFIG_RACIONAL` o painel mostraria a chave e nao o PORQUE dela --
    e a unidade R e justamente o que ninguem deduz do nome."""
    p = cliente.get("/catalogo").json()["parametros"]
    for chave in TRAILING_R:
        assert chave in p, chave
        assert p[chave]["racional"], chave
    assert p["trailing_unidade"]["opcoes"] == ["R", "preco"]
    assert (p["trailing_arma_r"]["min"], p["trailing_arma_r"]["max"]) == (0.1, 10.0)
    assert (p["trailing_dist_r"]["min"], p["trailing_dist_r"]["max"]) == (0.1, 10.0)
    # o racional tem de explicar a UNIDADE, que e a metade que o nome da chave nao conta
    assert "R" in p["trailing_unidade"]["racional"]
    assert "stop_abertura" in p["trailing_unidade"]["racional"]


@pytest.mark.parametrize("chave,valor", [
    ("trailing_unidade", "atr"),      # unidade que nao existe -- o [N-13] explica por que nao
    ("trailing_unidade", ""),
    ("trailing_arma_r", 0),           # 0 armaria o trailing na abertura: stop colado na entrada
    ("trailing_arma_r", 10.1),
    ("trailing_arma_r", "banana"),
    ("trailing_dist_r", 0),           # 0 poria o stop EM CIMA do preco
    ("trailing_dist_r", -1),
    ("trailing_dist_r", 10.1),
])
def test_p3_valor_fora_de_faixa_e_recusado_sem_gravar_nada(cliente, chave, valor):
    """A metade que importa mais que o "aceita": faixa aberta demais e o mesmo que faixa
    nenhuma. E `_validar_lote` e tudo-ou-nada -- o valor bom que veio junto tambem nao grava."""
    antes = cliente.get("/config").json()
    r = cliente.post("/config", json={chave: valor, "trailing_ativo": 0})
    assert r.status_code == 422, r.json()
    assert cliente.get("/config").json() == antes      # nada gravado, nem o `trailing_ativo`


def test_p3_o_default_vivo_do_trailing_em_r_passa_no_proprio_catalogo(banco):
    """Config que o `init_db` grava e o `POST /config` recusaria seria config entrada pela
    porta dos fundos -- o mesmo teste que os perfis ja fazem, aplicado ao default."""
    import api
    for chave in TRAILING_R:
        assert api._validar_config(chave, db.CONFIG_PADRAO[chave]), chave
    assert db.get_config()["trailing_unidade"] == "R"      # D-5: 1R arma, 1R de distancia
    assert float(db.get_config()["trailing_arma_r"]) == 1.0
    assert float(db.get_config()["trailing_dist_r"]) == 1.0


# ================================== [P-3b] o modo de alavancagem entra no perfil `experimento`
#
# A metade travada do `[N-10]`: o modo nascia "fixo" no `CONFIG_PADRAO` e NAO no perfil, porque
# declara-lo no perfil exigia verbete em `api.CONFIG_RACIONAL` -- e `api.py` nao era territorio
# do T-RISCO. O buraco ficou medido em `tests/test_sizing.py`, e a promocao daquele teste e o
# gatilho que este card cumpriu.

def test_p3b_o_experimento_declara_o_modo_de_alavancagem(banco):
    """O perfil e o retrato do que esta vivo. Um retrato que nao mostra o dial que multiplica
    a alavancagem por 5,5x nao e retrato do mesmo sistema."""
    assert db.PERFIS_RISCO["experimento"]["auto_lev_modo"] == "fixo"
    assert db.CONFIG_PADRAO["auto_lev_modo"] == "fixo"     # e as duas pontas seguem iguais


def test_p3b_com_o_modo_no_perfil_o_rotulo_para_de_mentir(cliente):
    """O que a declaracao COMPRA, medido na porta do painel: antes disto, ligar a escala por
    conviccao (2x-20x sobre um score que o [Q-13] mediu nao prever acerto) deixava o `/estado`
    dizendo 'experimento'. Rotulo de risco que mente e pior que rotulo nenhum ([Q-3])."""
    assert cliente.get("/estado").json()["perfil_risco"] == "experimento"
    cliente.post("/auto", json={"auto_lev_modo": "conviccao"})
    assert cliente.get("/estado").json()["perfil_risco"] == "personalizado"
    cliente.post("/perfil", json={"perfil": "experimento"})       # e o perfil restaura o modo
    cfg = cliente.get("/config").json()
    assert cfg["auto_lev_modo"] == "fixo"
    assert cliente.get("/estado").json()["perfil_risco"] == "experimento"


def test_p3b_o_conservador_NAO_declara_o_modo_e_a_assimetria_e_deliberada(cliente, sem_rede):
    """A metade que este card recusou fazer, medida em vez de virar nota de rodape.

    Sob `conservador` declarar "fixo" seria AFROUXAR: `auto_lev_min`=1, entao o modo
    "conviccao" entrega 1x na conviccao minima enquanto "fixo" entrega `alavancagem_padrao`=2x
    SEMPRE. Subir o piso de 1x para 2x no perfil alinhado a base -- cuja §6.1 diz que o unico
    regime que sobreviveu foi "trend-following SEM alavancagem" -- e decisao do dono, nao de
    agente (CLAUDE.md §2).

    O preco fica dito: la o rotulo continua sem enxergar o modo. E buraco LIMITADO, e o teto
    de 2x e quem o limita -- os dois modos vivem inteiros dentro dele."""
    import autotrader
    assert "auto_lev_modo" not in db.PERFIS_RISCO["conservador"]
    cliente.post("/perfil", json={"perfil": "conservador"})
    cliente.post("/auto", json={"auto_lev_modo": "conviccao"})
    assert cliente.get("/estado").json()["perfil_risco"] == "conservador"   # nao acusa
    cfg = db.get_config()                                                   # e o teto e o motivo
    assert autotrader._alavancagem(cfg, 60) == 1.0 and autotrader._alavancagem(cfg, 100) == 2.0


# ============================================ [F-15][N-26] auditoria de config: TODO caminho
#
# A pergunta que nasceu sem resposta na analise de 2026-08-28 foi "quando o `auto_trade` foi
# religado?", e ela nao tinha resposta porque a tabela `config` guarda o valor de AGORA: o
# UPSERT apaga o anterior sem deixar marca.
#
# 🔴 O que estes testes NAO provam, e nao poderiam: que o passado esta la. Nao esta, nao ha de
# onde tira-lo, e a `NOTA_AUDITORIA` diz isso na propria resposta da rota. O que se prova aqui
# e a outra metade -- que daqui pra frente NENHUM caminho de escrita escapa. Uma auditoria com
# um escritor de fora mente por omissao justamente sobre o escritor que se esqueceu, e o
# `/panico` (que grava `auto_trade=0`) seria o pior candidato a ser esquecido.

def ultima_auditoria(chave):
    linhas = db.auditoria_config(50, chave)
    return linhas[0] if linhas else None


def test_f15_num_banco_novo_a_auditoria_nasce_VAZIA(banco):
    """O `init_db` semeia o `CONFIG_PADRAO` com `INSERT OR IGNORE`, e isso NAO e mudanca de
    config: e o default chegando. Registra-lo encheria a auditoria de dezenas de linhas que
    nao sao eventos e enterraria a primeira mudanca real no meio delas -- e daria a impressao
    de que a tabela sabe de onde o sistema veio, quando ela so sabe para onde ele foi."""
    assert db.auditoria_config() == []


def test_f15_post_config_aparece_na_auditoria_com_os_dois_valores(cliente):
    cliente.post("/config", json={"min_conviccao": 70})
    a = ultima_auditoria("min_conviccao")
    assert a["valor_antigo"] == "55" and a["valor_novo"] == "70.0"
    assert a["origem"] == "POST /config" and a["ts"]


def test_f15_post_auto_aparece_e_e_o_caminho_do_auto_trade(cliente):
    """A chave da pergunta original. O `/auto` e a porta pela qual o painel religa o bot."""
    cliente.post("/auto", json={"auto_trade": 1})
    a = ultima_auditoria("auto_trade")
    assert (a["valor_antigo"], a["valor_novo"], a["origem"]) == ("0", "1", "POST /auto")


def test_f15_o_panico_aparece_E_A_ORDEM_DO_P1_7_NAO_MUDA(cliente, sem_rede):
    """Duas coisas num teste so porque sao a mesma: auditar nao pode custar a ordem.

    O [P1-7] manda o `/panico` gravar `auto_trade=0` ANTES de fechar posicao -- se fechar
    falhar no meio, o bot ja esta morto e nao reabre. A auditoria entra DENTRO do mesmo
    `set_config`, na mesma transacao, entao ela nao acrescenta um passo antes de a fonte
    morrer. A posicao aberta aqui prova que o desligamento ficou registrado mesmo havendo
    trabalho depois dele."""
    cliente.post("/auto", json={"auto_trade": 1})
    semear_posicao()
    r = cliente.post("/panico").json()
    assert r["auto_desligado"] and r["fechadas"] == 1
    a = ultima_auditoria("auto_trade")
    assert (a["valor_antigo"], a["valor_novo"], a["origem"]) == ("1", "0", "POST /panico")


def test_f15_o_perfil_aparece_com_o_nome_do_perfil_na_origem(cliente):
    """`POST /perfil` grava VARIAS chaves de uma vez -- e sem o nome do perfil na origem, as
    linhas soltas na auditoria nao contariam que foram um gesto so."""
    cliente.post("/perfil", json={"perfil": "conservador"})
    mudaram = [k for k in db.PERFIS_RISCO["conservador"]
               if not db._igual_cfg(db.PERFIS_RISCO["experimento"].get(k),
                                    db.PERFIS_RISCO["conservador"][k])]
    assert len(mudaram) == 5                      # 5 das 6: `auto_max_posicoes` e "5" nos dois
    for chave in mudaram:
        a = ultima_auditoria(chave)
        assert a and a["origem"] == "POST /perfil:conservador", chave
    assert ultima_auditoria("risco_por_trade")["valor_antigo"] == "0.03"
    # e o que NAO mudou de valor nao virou linha, mesmo tendo sido gravado no mesmo gesto
    assert ultima_auditoria("auto_max_posicoes") is None


def test_f15_o_reset_aparece_apesar_de_NAO_passar_pelo_set_config(cliente):
    """O unico escritor que nao pode usar `db.set_config`: a limpeza da trava tem de cair na
    MESMA transacao dos DELETEs do reset, e `set_config` abre a sua propria. Ele chama
    `db._auditar_config` a mao com a conexao que ja tem -- e e por isso que este teste existe
    separado: e o caminho que uma instrumentacao so do chokepoint deixaria de fora."""
    db.set_config("trava_dia_em", "2026-08-22")
    cliente.post("/reset", json={"confirmar": "RESET"})
    a = ultima_auditoria("trava_dia_em")
    assert (a["valor_antigo"], a["valor_novo"], a["origem"]) == ("2026-08-22", "", "POST /reset")


def test_f15_a_trava_diaria_do_simulador_aparece_identificada_pelo_frame(banco, sem_rede):
    """`simulador.guarda_risco` grava `trava_dia_em` e nao passa `origem` -- `simulador.py` e
    territorio de outro agente. O fallback pelo frame do chamador e o que faz um escritor que
    nao se declarou aparecer identificavel em vez de virar um "?" na tabela."""
    import simulador
    db.set_config("limite_perda_dia", "0.0")     # trava no primeiro centavo de perda
    semear_posicao(entrada=100.0, valor_reais=100.0, alavancagem=10, preco_atual=99.0, pnl=-100.0)
    assert simulador.guarda_risco()["trava_dia"] is True
    a = ultima_auditoria("trava_dia_em")
    assert a["valor_antigo"] == "" and a["valor_novo"] and a["origem"].startswith("simulador.py:")


def test_f15_regravar_o_MESMO_valor_nao_e_evento(cliente):
    """O `POST /perfil` reaplica o perfil inteiro e o painel reenvia o formulario todo. Se
    regravacao identica virasse linha, a mudanca real ficaria enterrada no ruido -- e achar a
    mudanca real e a unica coisa que esta tabela existe para fazer."""
    cliente.post("/config", json={"min_conviccao": 70})
    n = len(db.auditoria_config(500))
    cliente.post("/config", json={"min_conviccao": 70})       # de novo, mesmo valor
    cliente.post("/perfil", json={"perfil": "experimento"})   # ja e o perfil vivo
    assert len(db.auditoria_config(500)) == n


def test_f15_a_rota_expoe_a_auditoria_E_DIZ_QUE_O_PASSADO_NAO_EXISTE(cliente):
    """A metade honesta da entrega, e ela viaja com o dado: lista vazia sem ressalva deixa
    quem le concluir que nada mudou, que e a unica leitura pior que nao ter auditoria."""
    import api
    j = cliente.get("/config/auditoria").json()
    assert j["total"] == 0 and j["linhas"] == []
    assert "auto_trade" in j["nota"] and "2026-08-29" in j["nota"]
    assert j["nota"] == api.NOTA_AUDITORIA

    cliente.post("/auto", json={"auto_trade": 1})
    cliente.post("/config", json={"min_conviccao": 70})
    j = cliente.get("/config/auditoria").json()
    assert j["total"] == 2 and j["linhas"][0]["chave"] == "min_conviccao"   # mais recente 1o
    j = cliente.get("/config/auditoria", params={"chave": "auto_trade"}).json()
    assert j["total"] == 1 and j["linhas"][0]["valor_novo"] == "1"


def test_f15_a_auditoria_NAO_vai_para_o_estado(cliente):
    """Mesmo motivo do `caps_geometria`: o `/estado` e polido a cada 3s contra uma franquia de
    15 GB/mes (CLAUDE.md §2). Historico so se le quando alguem pergunta -- rota propria."""
    cliente.post("/auto", json={"auto_trade": 1})
    j = cliente.get("/estado").json()
    assert "auditoria" not in j and "config_auditoria" not in j


def test_f15_NENHUM_escritor_de_config_escapa_da_auditoria(banco):
    """A trava que faz esta entrega durar mais que hoje.

    Instrumentar os escritores que existem hoje nao impede o de amanha de gravar direto e
    sumir da tabela -- e o defeito voltaria calado, que e como ele nasceu. Este teste varre o
    codigo de PLATAFORMA atras de SQL que escreve na tabela `config` e exige que cada
    ocorrencia esteja numa lista de excecoes conhecidas. Escritor novo nao passa sem alguem
    decidir aqui que ele e legitimo.

    `db.set_config` (o chokepoint) e o `/reset` (que audita a mao, na sua transacao) sao as
    duas unicas. `db.init_db` semeia o default com `INSERT OR IGNORE` e nao e mudanca."""
    import glob
    import os
    import re
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    padrao = re.compile(r"(INSERT|REPLACE)\s+(OR\s+\w+\s+)?INTO\s+config\b|UPDATE\s+config\b",
                        re.I)
    CONHECIDOS = {
        ("db.py", "INSERT INTO CONFIG"),            # set_config: o chokepoint auditado
        ("db.py", "INSERT OR IGNORE INTO CONFIG"),  # init_db: semeia o default, nao e mudanca
        ("api.py", "INSERT INTO CONFIG"),           # /reset: audita a mao, na sua transacao
    }
    achados = set()
    for caminho in sorted(glob.glob(os.path.join(raiz, "*.py"))):
        nome = os.path.basename(caminho)
        if nome.startswith(("test_", "prova_")):     # provas mexem no proprio banco, de fora
            continue
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                m = padrao.search(linha)
                if m:
                    achados.add((nome, " ".join(m.group(0).split()).upper()))
    assert achados == CONHECIDOS, f"escritor de config fora da auditoria: {achados ^ CONHECIDOS}"
