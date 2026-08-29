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
from conftest import semear_sinal


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
