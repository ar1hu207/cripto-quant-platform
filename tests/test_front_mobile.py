"""[app-mobile] O app do celular (`web/m.html`) e o que ele divide com o painel do desktop.

Sao duas telas sobre o mesmo backend e as MESMAS regras: a conta do ticket (tamanho pelo risco,
liquidacao antes do stop, teto de risco aberto) mora uma vez so, em `web/app/comum.js`. Se o
celular ganhasse uma copia, a primeira correcao feita num lado deixaria o outro mostrando uma
perda no pior caso diferente para o mesmo sinal -- e o backend recusando o que a tela aprovou.

Como o test_front_apollux: so leitura de arquivo, sem navegador, para rodar no CI.
"""
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(RAIZ, "web")


def _ler(*partes):
    with open(os.path.join(*partes), encoding="utf-8") as f:
        return f.read()


def _srcs(html):
    return re.findall(r"<script[^>]*\ssrc=\"([^\"]+)\"", html)


def test_m_html_carrega_so_script_relativo_e_que_existe():
    srcs = _srcs(_ler(WEB, "m.html"))
    for s in ("app/api.js", "app/comum.js", "app/m/app.js"):
        assert s in srcs, s
    for s in srcs:
        assert not s.startswith(("http", "//")), s
        assert os.path.isfile(os.path.join(WEB, s)), f"m.html carrega {s}, que nao existe"


def test_comum_vem_depois_do_api_e_antes_de_quem_o_usa():
    """comum.js pendura as regras em window.APX, que o api.js cria: fora de ordem, A.ticket e
    undefined e o ticket do sinal quebra na primeira tecla."""
    for html, quem in (("index.html", "app/casca.js"), ("m.html", "app/m/app.js")):
        srcs = _srcs(_ler(WEB, html))
        assert srcs.index("app/api.js") < srcs.index("app/comum.js") < srcs.index(quem), html


def test_a_conta_do_ticket_mora_so_no_comum():
    """O desktop e o celular calculam a previa pelo A.ticket; nenhum dos dois tem a formula."""
    comum = _ler(WEB, "app", "comum.js")
    assert re.search(r"A\.ticket\s*=\s*\{", comum)
    casca, mob = _ler(WEB, "app", "casca.js"), _ler(WEB, "app", "m", "app.js")
    assert "A.ticket.calc" in casca and "A.ticket.previa" in casca
    assert "A.ticket.calc" in mob and "A.ticket.previa" in mob
    for nome, js in (("casca.js", casca), ("m/app.js", mob)):
        assert not re.search(r"function calc\s*\(", js), f"{nome} voltou a ter um calc proprio"
        assert "0.9 /" not in js and "0.9/" not in js, f"{nome} recalcula a alavancagem maxima"


def test_nenhuma_cor_literal_no_app_do_celular():
    """Mesma regra das views (DESIGN.md, regra 1): cor por token, para trocar com a paleta."""
    js = _ler(WEB, "app", "m", "app.js")
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b(?![-\w])", js) == []
    assert re.findall(r"rgba?\(\s*\d", js) == []


def test_acao_destrutiva_no_celular_passa_pelo_arraste():
    """Um toque no bolso nao pode abrir trade, fechar posicao nem disparar o panico (DS §5):
    cada POST destrutivo do app vive numa funcao que so roda depois do arraste."""
    js = _ler(WEB, "app", "m", "app.js")
    # fechar e o panico do topo: o POST vem depois de um sheet com slide
    for fn, rota in (("fechar", "/fechar"), ("panico", "/panico")):
        m = re.search(rf"async function {fn}\(.*?\n  \}}\n", js, re.S)
        assert m, fn
        corpo = m.group(0)
        if rota in corpo:
            assert corpo.index("slide:") < corpo.index(f"'{rota}'"), fn
        else:
            assert "slide:" in corpo and "executaPanico" in corpo, fn
    # confirmar: so pelo slide do ticket
    assert re.search(r"armaSlide\(\$\('tk-slide'\), function \(\) \{ return self\.confirma\(\); \}\)", js)
    # ligar o Apollo: arraste; pausar e imediato (apertar guarda pode, afrouxar pede gesto)
    m = re.search(r"async function alternaAuto\(.*?\n  \}\n", js, re.S)
    assert m and "Arraste para ligar" in m.group(0)


def test_nenhum_dialogo_nativo_no_celular():
    js = _ler(WEB, "app", "m", "app.js")
    assert not re.search(r"(?<![\w.])(confirm|alert|prompt)\(", js)


def test_index_manda_o_celular_para_o_app_e_respeita_a_escolha():
    """Largura decide; escolha explicita (apx.ui) vence. Sem o `pref !== 'desktop'`, quem toca
    em "Versao completa" no celular volta para o app num loop."""
    html = _ler(WEB, "index.html")
    m = re.search(r"<script>((?:(?!</script>).)*?location\.replace(?:(?!</script>).)*)</script>", html, re.S)
    assert m, "redirecionamento do index nao encontrado"
    js = m.group(1)
    assert "localStorage.getItem('apx.ui')" in js
    assert "pref === 'mobile'" in js and "pref !== 'desktop'" in js
    assert "location.replace('m.html' + location.search + location.hash)" in js
    # e roda antes de qualquer script da casca: senao o desktop pinta antes de sair
    assert html.index("apx.ui") < html.index('src="app/api.js"')
    # o app grava a mesma chave com o mesmo valor que o index le
    assert "A.store.set('apx.ui', 'desktop')" in _ler(WEB, "app", "m", "app.js")


def test_o_app_usa_o_mesmo_gate_de_login():
    """api.js procura o gate por id; o m.html tem que ter todos, ou o login nao abre."""
    html = _ler(WEB, "m.html")
    for i in ("gate", "gate-form", "gate-user", "gate-pass", "gate-btn", "gate-msg", "toast"):
        assert f'id="{i}"' in html, i


# ---------------------------------------------------------------- [PUSH-1] notificacao nativa

def test_todo_push_vira_notificacao_no_service_worker():
    """O iOS retira a permissao do app que recebe push e nao mostra nada. O handler mostra
    notificacao em todo caminho, inclusive com corpo que nao e JSON."""
    sw = _ler(WEB, "sw.js")
    m = re.search(r"addEventListener\('push', e => \{(.*?)\n\}\);", sw, re.S)
    assert m, "sw.js sem handler de push"
    corpo = m.group(1)
    assert "e.waitUntil(self.registration.showNotification(" in corpo
    assert "catch (x)" in corpo                      # JSON quebrado nao derruba o showNotification
    assert corpo.count("return") == 0                # nenhum caminho sai antes de mostrar
    assert "addEventListener('notificationclick'" in sw


def test_toque_na_notificacao_so_aceita_hash():
    """A pagina so troca de tela com o que comeca por '#': uma mensagem com 'javascript:' ou URL
    de fora nao navega para lugar nenhum."""
    js = _ler(WEB, "app", "m", "app.js")
    assert "d.tipo === 'abrir' && typeof d.url === 'string' && d.url.charAt(0) === '#'" in js


def test_pedido_de_permissao_e_a_primeira_coisa_do_toque():
    """No iPhone o dialogo de permissao so abre dentro do gesto; um await de rede antes dele o
    tira do gesto e o iOS nega calado."""
    js = _ler(WEB, "app", "m", "app.js")
    m = re.search(r"ativar: async function \(\) \{(.*?)\n    \},", js, re.S)
    assert m, "ativar() nao encontrado"
    corpo = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)     # comentario nao e codigo
    assert corpo.index("Notification.requestPermission()") < corpo.index("await A.api")
    primeiro_await = re.search(r"await ([\w.]+)", corpo).group(1)
    assert primeiro_await == "Notification.requestPermission"
    assert "userVisibleOnly: true" in corpo


def test_push_saiu_do_em_construcao():
    js = _ler(WEB, "app", "m", "app.js")
    assert "cad('Push no celular'" not in js
    assert 'id="nt-st"' in js
