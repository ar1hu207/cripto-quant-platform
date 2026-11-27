"""[front-csp] Os cabecalhos de seguranca do painel no Vercel -- e as duas maneiras de eles
quebrarem o painel em silencio.

A credencial do painel vive no `localStorage` (CLAUDE.md §2). Script injetado na pagina a le;
a CSP e o que impede esse script de manda-la para fora (`connect-src` so para o backend) e de a
pagina ser embutida num iframe de terceiro (`frame-ancestors 'none'`). Como `web/` publica
sozinho no merge, um cabecalho errado e o painel quebrado em producao sem passar por ninguem.
"""
import json
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _headers(caminho):
    with open(os.path.join(RAIZ, caminho), encoding="utf-8") as f:
        return json.load(f)["headers"]


CLASSICO = "/classico.html"


def _csp_texto(caminho, classico=False):
    """O texto da CSP. Sao DUAS regras: a geral (tudo menos o classico.html) e a do classico."""
    for regra in _headers(caminho):
        if (regra["source"] == CLASSICO) != classico:
            continue
        for h in regra["headers"]:
            if h["key"] == "Content-Security-Policy":
                return h["value"]
    raise AssertionError(f"{caminho} sem Content-Security-Policy (classico={classico})")


def _csp(caminho, classico=False):
    return {d.split()[0]: d.split()[1:] for d in
            (x.strip() for x in _csp_texto(caminho, classico).split(";")) if d}


def _ler(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as f:
        return f.read()


def test_os_dois_vercel_json_mandam_os_MESMOS_cabecalhos():
    """Existem dois `vercel.json` de proposito (build pelo GitHub le a raiz; `vercel --prod`
    roda de dentro de `web/`). Mexeu num, confira o outro -- este teste confere sozinho."""
    assert _headers("vercel.json") == _headers(os.path.join("web", "vercel.json"))


def test_o_connect_src_libera_o_backend_que_o_config_js_aponta():
    """Trocar o backend no `web/config.js` sem trocar a CSP bloquearia TODA chamada do painel
    -- e o erro no navegador diria "violates Content Security Policy", nao "backend fora"."""
    with open(os.path.join(RAIZ, "web", "config.js"), encoding="utf-8") as f:
        ativo = [l for l in f if l.strip().startswith("window.API_BASE")]
    assert len(ativo) == 1, "web/config.js deve ter exatamente uma linha ativa de API_BASE"
    host = re.search(r'"(https://[^"/]+)', ativo[0]).group(1)
    assert host in _csp("vercel.json")["connect-src"]


def test_a_csp_fecha_o_que_existe_para_fechar():
    for classico in (False, True):
        csp = _csp("vercel.json", classico)
        assert csp["frame-ancestors"] == ["'none'"]
        assert csp["base-uri"] == ["'none'"] and csp["object-src"] == ["'none'"]
        # script so da propria origem: o invariante do `web/` (nada de CDN) vira regra do navegador
        assert [s for s in csp["script-src"] if s.startswith("http")] == []


def test_script_embutido_nao_executa_no_painel():
    """`script-src 'self'` e mais nada. Com 'unsafe-inline', um campo da API que chegasse a um
    innerHTML sem escape executava na pagina, lia a credencial do localStorage e saia com ela por
    navegacao (`location.href`, que `connect-src` nao cobre). Sem ele, o mesmo HTML injetado vira
    texto morto. Quem recolocar 'unsafe-inline' "porque um botao parou" desfaz a guarda inteira:
    o conserto e tirar o handler do HTML (ver o teste de baixo)."""
    assert _csp("vercel.json")["script-src"] == ["'self'"]


def test_a_excecao_do_classico_e_so_do_classico():
    """O classico.html ainda tem dezenas de `onclick=` e o app inteiro num <script> embutido;
    sob `script-src 'self'` ele nao abre. Fica com a CSP de antes ate ser aposentado, em regra
    PROPRIA. As duas regras sao mutuamente exclusivas de proposito: nao depende de qual delas a
    Vercel aplica por ultimo quando duas casam com o mesmo caminho."""
    fontes = [r["source"] for r in _headers("vercel.json")
              if any(h["key"] == "Content-Security-Policy" for h in r["headers"])]
    assert len(fontes) == 2 and CLASSICO in fontes
    geral = re.compile("^" + next(f for f in fontes if f != CLASSICO) + "$")
    assert not geral.match(CLASSICO)
    for caminho in ("/", "/index.html", "/m.html", "/app/casca.js", "/sw.js", "/config.js"):
        assert geral.match(caminho), caminho
    assert "'unsafe-inline'" in _csp("vercel.json", classico=True)["script-src"]
    # os outros cabecalhos seguem valendo para TODO caminho, o classico inclusive
    resto = [r for r in _headers("vercel.json") if r["source"] == "/(.*)"]
    assert {h["key"] for h in resto[0]["headers"]} >= {"X-Content-Type-Options", "X-Frame-Options",
                                                       "Referrer-Policy", "Permissions-Policy"}


# Nomes de evento, e nao `on[a-z]+`: no JS, `ontem = '...'` e variavel, nao handler.
EVENTOS = ("click|dblclick|change|input|submit|reset|load|error|toggle|focus|blur|scroll|wheel|"
           "key[a-z]+|mouse[a-z]+|pointer[a-z]+|touch[a-z]+|drag[a-z]*|drop|animation[a-z]+|"
           "transition[a-z]+|contextmenu|beforeinput|paste|copy|cut")


def test_o_painel_nao_tem_script_embutido_nem_handler_em_atributo():
    """A outra metade do teste da CSP: sob `script-src 'self'` o navegador BLOQUEIA EM SILENCIO
    um <script> sem src e um `onclick=`/`onload=`. Nao da erro na tela: o botao so nao responde
    (ou o celular para de ser mandado ao m.html). Vale para o HTML e para o HTML que o JS monta
    em string."""
    for pagina in ("index.html", "m.html"):
        html = re.sub(r"<!--.*?-->", "", _ler("web", pagina), flags=re.S)
        assert re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html) == [], pagina
        assert re.findall(r"<[a-zA-Z][^>]*\son[a-z]+\s*=", html) == [], pagina
        assert "javascript:" not in html, pagina
    app = os.path.join(RAIZ, "web", "app")
    for pasta, _, nomes in os.walk(app):
        for nome in nomes:
            if nome.endswith(".js"):
                js = _ler(pasta, nome)
                assert re.findall(r"""[\s'"]on(?:%s)\s*=\s*\\?['"]""" % EVENTOS, js) == [], nome
                assert "javascript:" not in js, nome


def test_o_backend_manda_a_mesma_csp_do_vercel():
    """O backend serve o MESMO index.html em `GET /`, publico pelo Funnel: se a CSP dele
    ficasse com 'unsafe-inline', a copia servida de la continuaria com o furo que a do Vercel
    fechou. Lido por AST para este arquivo continuar sem importar a plataforma."""
    import ast
    arvore = ast.parse(_ler("api.py"))
    valor = next(n.value for n in ast.walk(arvore) if isinstance(n, ast.Assign)
                 and any(getattr(a, "id", "") == "_CSP" for a in n.targets))
    assert ast.literal_eval(valor) == _csp_texto("vercel.json")
