"""[front-apollux] O que a casca Apollux promete e um merge distraido quebraria sem ninguem ver.

`web/` publica sozinho no merge (CLAUDE.md §5): nao ha revisor entre o commit e o painel no
celular do dono. Cada teste aqui e uma regra do CLAUDE.md §2 ou do DESIGN.md que, se quebrar,
quebra em silencio -- script de terceiro lendo a credencial, cache servindo JS velho contra HTML
novo, view vazando CSS para outra, cor literal que nao troca com a paleta, paleta sem contraste.

Sem navegador e sem node: so leitura de arquivo, para rodar no CI como o resto da suite.
"""
import json
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(RAIZ, "web")
VIEWS = os.path.join(WEB, "app", "views")
ROTAS_COM_VIEW = ["painel", "operar", "apollo", "analise", "carteira", "pesquisa"]
ROTAS_EM_BREVE = ["acoes", "fundamentos", "noticias", "mobile"]


def _ler(*partes):
    with open(os.path.join(*partes), encoding="utf-8") as f:
        return f.read()


def _arquivos_web():
    for base, _, nomes in os.walk(WEB):
        for n in nomes:
            if n.endswith((".html", ".js")):
                yield os.path.join(base, n)


# ---------------------------------------------------------------- script de terceiro (§2)

def test_nenhum_script_de_terceiro_no_web():
    """O grep do CLAUDE.md §2 (`grep -rn "src=['\\"]http" web/` vazio), em Python. A credencial
    do painel vive no localStorage, e um script de CDN no mesmo documento a le."""
    achados = []
    for p in _arquivos_web():
        for i, linha in enumerate(_ler(p).splitlines(), 1):
            if re.search(r"src=['\"]http", linha):
                achados.append(f"{os.path.relpath(p, RAIZ)}:{i}")
    assert achados == []


def test_index_carrega_so_script_relativo_e_que_existe():
    html = _ler(WEB, "index.html")
    srcs = re.findall(r"<script[^>]*\ssrc=\"([^\"]+)\"", html)
    assert "vendor/gsap.min.js" in srcs and "app/casca.js" in srcs
    for s in srcs:
        assert not s.startswith(("http", "//")), s
        assert os.path.isfile(os.path.join(WEB, s)), f"index.html carrega {s}, que nao existe"


def test_gsap_vendorado_e_a_versao_declarada():
    cab = _ler(WEB, "vendor", "gsap.min.js")[:200]
    assert "GSAP 3.12.5" in cab


def test_o_painel_classico_continua_no_ar():
    """`web/classico.html` e o index de antes, intacto: comparacao e fuga para o que a casca
    ainda nao cobre."""
    html = _ler(WEB, "classico.html")
    assert "cbAuth" in html and "lightweight-charts" in html


# ---------------------------------------------------------------- contrato das views

@pytest.mark.parametrize("vid", ROTAS_COM_VIEW)
def test_cada_view_segue_o_contrato(vid):
    """`window.PULSE_VIEWS.<id> = {id, titulo, html, init(root), destroy()}` (contrato do mock).
    destroy e o que limpa timer, listener e canvas: sem ele, a view continua pollando depois de
    sair da tela."""
    js = _ler(VIEWS, f"{vid}.js")
    assert re.search(rf"window\.PULSE_VIEWS\.{vid}\s*=", js)
    assert re.search(rf"id:\s*'{vid}'", js)
    for chave in ("titulo:", "html:", "init:", "destroy:"):
        assert chave in js, f"{vid}.js sem {chave}"


def _css_da_view(js):
    m = re.search(r"var css = '<style>' \+(.*?)'</style>';", js, re.S)
    assert m, "bloco de CSS da view nao encontrado"
    return "".join(re.findall(r"'((?:[^'\\]|\\.)*)'", m.group(1)))


def _seletores(css):
    """Seletores de nivel de regra, abrindo @media e ignorando @keyframes."""
    css = re.sub(r"@keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css)
    saida, i, buf = [], 0, ""
    while i < len(css):
        c = css[i]
        if c == "{":
            sel = buf.strip()
            buf = ""
            if sel.startswith("@media") or sel.startswith("@supports"):
                i += 1
                continue                       # o conteudo do @media segue sendo lido como regra
            saida.append(sel)
            fim = css.index("}", i)            # pula o corpo da declaracao
            i = fim + 1
            continue
        if c == "}":
            buf = ""                           # fecha um @media
        else:
            buf += c
        i += 1
    return saida


@pytest.mark.parametrize("vid", ROTAS_COM_VIEW)
def test_css_de_cada_view_e_escopado(vid):
    """Toda regra da view comeca em `.v-<id>`. Uma regra solta (`.side{...}`) vaza para a
    casca e para as outras views -- foi assim que a Carteira estourou a 390 px."""
    sels = _seletores(_css_da_view(_ler(VIEWS, f"{vid}.js")))
    assert sels, f"{vid}.js sem regra de CSS"
    soltas = [s for sel in sels for s in sel.split(",") if not s.strip().startswith(f".v-{vid}")]
    assert soltas == []


@pytest.mark.parametrize("vid", ROTAS_COM_VIEW)
def test_nenhuma_cor_literal_nas_views(vid):
    """Tudo por token (DESIGN.md, regra 1). Cor literal nao troca com a paleta: no Solar ou no
    Osso ela aparece como a cor do Eletrico, e um verde literal num P&L engana."""
    js = _ler(VIEWS, f"{vid}.js")
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b(?![-\w])", js) == []
    assert re.findall(r"rgba?\(\s*\d", js) == []


def test_nenhum_dialogo_nativo_no_front_novo():
    """Panico, reset e config confirmam DENTRO da pagina (diff antes -> depois, digitar RESET).
    `confirm()` e um clique unico que o navegador ainda deixa marcar "nao perguntar de novo"."""
    for p in _arquivos_web():
        if os.path.join("web", "app") not in p:
            continue
        assert not re.search(r"(?<![\w.])(confirm|alert|prompt)\(", _ler(p)), p


def test_trava_diaria_nao_tem_controle_no_editor_de_config():
    """Limpar `trava_dia_em` a mao e relaxar invariante (CLAUDE.md §2). O editor do #apollo a
    deixa de fora, junto com o auto_trade (botao proprio) e os segredos do Telegram."""
    js = _ler(VIEWS, "apollo.js")
    fora = re.search(r"var FORA = \{([^}]*)\}", js)
    assert fora, "apollo.js sem a lista FORA"
    for chave in ("trava_dia_em", "auto_trade", "telegram_token"):
        assert chave in fora.group(1)


def test_as_dez_rotas_estao_na_navegacao():
    html = _ler(WEB, "index.html")
    rotas = re.findall(r'data-route="([a-z]+)"', html)
    assert rotas == ROTAS_COM_VIEW + ROTAS_EM_BREVE
    for r in ROTAS_COM_VIEW:
        assert os.path.isfile(os.path.join(VIEWS, f"{r}.js"))


# ---------------------------------------------------------------- PWA

def test_service_worker_casca_v2_e_api_fora_do_cache():
    sw = _ler(WEB, "sw.js")
    assert re.search(r"const CASCA = 'casca-v2'", sw)
    # /app/ rede-primeiro: HTML novo com JS velho do cache quebra a tela no dia do deploy
    assert "'/app/'" in sw
    # a API mora em outra origem e responde com a credencial: o SW nao toca nela
    assert "location.origin" in sw or "self.location.origin" in sw


def test_manifesto_apollux():
    m = json.loads(_ler(WEB, "manifest.webmanifest"))
    assert m["name"] == "Apollux" and m["short_name"] == "Apollux"
    assert m["background_color"].upper() == m["theme_color"].upper() == "#0B0B0C"


# ---------------------------------------------------------------- backend: o mount de /app

def test_api_monta_app_com_a_guarda_do_vendor():
    """Diretorio ausente nao pode derrubar o processo (StaticFiles levanta RuntimeError): sem
    `web/app` o painel nao carrega, mas worker, risco e API seguem de pe."""
    src = _ler(RAIZ, "api.py")
    m = re.search(r'_APP = os\.path\.join\(WEB, "app"\)\nif os\.path\.isdir\(_APP\):\n'
                  r'    app\.mount\("/app", StaticFiles\(directory=_APP\), name="app"\)\nelse:', src)
    assert m


# ---------------------------------------------------------------- paletas e contraste

def _paletas():
    js = _ler(WEB, "app", "paletas.js")
    blocos = re.findall(r'id: "([a-z]+)".*?t: \{(.*?)\}', js, re.S)
    out = {}
    for pid, corpo in blocos:
        t = dict(re.findall(r'(\w+): "(#[0-9A-Fa-f]{6})"', corpo))
        t["glow"] = float(re.search(r"glow: ([0-9.]+)", corpo).group(1))
        out[pid] = t
    return out


def _lum(h):
    def canal(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(h[i:i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_doze_paletas_completas_e_osso_e_o_padrao():
    p = _paletas()
    assert len(p) == 12
    campos = {"bg", "panel", "panel2", "line", "line2", "text", "text2", "mute",
              "accent", "on", "pos", "neg", "warn", "info", "glow"}
    for pid, t in p.items():
        assert set(t) == campos, pid
    assert "osso" in p
    assert re.search(r"byId\('osso'\)", _ler(WEB, "app", "casca.js"))


PARES = [("text", "panel"), ("text2", "panel"), ("mute", "panel"), ("mute", "panel2"),
         ("accent", "panel"), ("on", "accent"), ("pos", "panel"), ("neg", "panel"),
         ("warn", "panel")]


@pytest.mark.parametrize("pid", sorted(_paletas()))
def test_contraste_AA_em_todos_os_pares_de_texto(pid):
    """O portao de contraste do DESIGN.md: 4,5:1 (WCAG 2.1 AA, texto normal) em cada par que a
    interface usa para texto. Paleta nova ou ajuste de hex que derrube um par nao entra."""
    t = _paletas()[pid]
    baixos = {f"{a}/{b}": round(_contraste(t[a], t[b]), 2) for a, b in PARES
              if _contraste(t[a], t[b]) < 4.5}
    assert baixos == {}


def test_cada_montagem_de_view_recebe_um_no_novo():
    """As views delegam clique no `root` que recebem. Se a casca passar o `#view-root` (permanente),
    cada visita soma um listener e um clique vira N POSTs: Painel -> Operar -> Painel e o "Pausar"
    mandava dois `POST /auto`; duas visitas a Carteira e o "Aportar" comprava duas vezes."""
    js = _ler(WEB, "app", "casca.js")
    assert "v.init(mount)" in js and "v.init(viewRoot)" not in js
    assert re.search(r"viewRoot\.innerHTML = head\(route\) \+ '<div class=\"view-mount\"></div>'", js)
