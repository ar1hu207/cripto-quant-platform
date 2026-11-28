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


def _regras_csp(caminho):
    return [r for r in _headers(caminho)
            if any(h["key"] == "Content-Security-Policy" for h in r["headers"])]


def _csp_texto(caminho):
    """O texto da CSP. E UMA regra so, para todo caminho (ver o teste da excecao, abaixo)."""
    regras = _regras_csp(caminho)
    assert len(regras) == 1, f"{caminho}: {len(regras)} regras com Content-Security-Policy"
    return next(h["value"] for h in regras[0]["headers"] if h["key"] == "Content-Security-Policy")


def _csp(caminho):
    return {d.split()[0]: d.split()[1:] for d in
            (x.strip() for x in _csp_texto(caminho).split(";")) if d}


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
    csp = _csp("vercel.json")
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


def test_nenhum_caminho_tem_excecao_na_csp():
    """Existiu uma regra PROPRIA para o /classico.html, com 'unsafe-inline' no script-src: o
    painel antigo tinha o app num <script> embutido e dezenas de `onclick=`. Nela HTML injetado
    executava, e o escape de cada campo era a guarda inteira. A excecao saiu, e depois o proprio
    painel antigo (tests/test_front_apollux.py confere que ele nao volta). Quem criar uma regra
    a parte "porque um botao parou" numa pagina nova desfaz a guarda so para ela: o conserto e
    tirar o handler do HTML (teste de baixo), nao afrouxar aqui."""
    for arquivo in ("vercel.json", os.path.join("web", "vercel.json")):
        regras = _regras_csp(arquivo)
        assert [r["source"] for r in regras] == ["/(.*)"], arquivo      # uma regra, todo caminho
        geral = re.compile("^" + regras[0]["source"] + "$")
        for caminho in ("/", "/index.html", "/m.html", "/pagina-nova.html",
                        "/app/casca.js", "/sw.js", "/config.js"):
            assert geral.match(caminho), caminho
        assert _csp(arquivo)["script-src"] == ["'self'"], arquivo
        # e nenhuma OUTRA regra devolve script embutido por um segundo cabecalho de CSP
        for regra in _headers(arquivo):
            for h in regra["headers"]:
                if "content-security-policy" in h["key"].lower():
                    script = [d for d in h["value"].split(";")
                              if d.split()[:1] in (["script-src"], ["script-src-elem"],
                                                   ["script-src-attr"], ["default-src"])]
                    assert script and not any("'unsafe-" in d for d in script), (arquivo, regra)
        # os outros cabecalhos valem para todo caminho, na mesma regra
        assert {h["key"] for h in regras[0]["headers"]} >= {
            "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy"}


# Nomes de evento, e nao `on[a-z]+`: no JS, `ontem = '...'` e variavel, nao handler.
EVENTOS = ("click|dblclick|change|input|submit|reset|load|error|toggle|focus|blur|scroll|wheel|"
           "key[a-z]+|mouse[a-z]+|pointer[a-z]+|touch[a-z]+|drag[a-z]*|drop|animation[a-z]+|"
           "transition[a-z]+|contextmenu|beforeinput|paste|copy|cut")


def test_o_painel_nao_tem_script_embutido_nem_handler_em_atributo():
    """A outra metade do teste da CSP: sob `script-src 'self'` o navegador BLOQUEIA EM SILENCIO
    um <script> sem src e um `onclick=`/`onload=`. Nao da erro na tela: o botao so nao responde
    (ou o celular para de ser mandado ao m.html). Vale para o HTML e para o HTML que o JS monta
    em string."""
    # toda pagina publicada, e nao uma lista: pagina nova em web/ entra sozinha na regra
    paginas = sorted(n for n in os.listdir(os.path.join(RAIZ, "web")) if n.endswith(".html"))
    assert {"index.html", "m.html"} <= set(paginas), paginas
    for pagina in paginas:
        html = re.sub(r"<!--.*?-->", "", _ler("web", pagina), flags=re.S)
        assert re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html) == [], pagina
        assert re.findall(r"<[a-zA-Z][^>]*\son[a-z]+\s*=", html) == [], pagina
        assert "javascript:" not in html, pagina
    app = os.path.join(RAIZ, "web", "app")
    arquivos = [(pasta, nome) for pasta, _, nomes in os.walk(app) for nome in nomes]
    for pasta, nome in arquivos:
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
