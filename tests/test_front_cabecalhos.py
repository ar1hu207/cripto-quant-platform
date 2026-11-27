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


# ------------------------------------------------------------- classico.html: o escape
# `${x.campo}` impresso como veio, com os enfeites que nao limpam nada: `||''`, `??'—'`,
# `.replace('/USDT','')`, `(x.ts||'').slice(11,16)`, `String(x.ts).slice(11,19)`.
_CAMPO_CRU = re.compile(
    r"""\$\{\s*(?:String\()?\(?\s*
        (?P<campo>[A-Za-z_$][\w$]*(?:\??\.[A-Za-z_$][\w$]*)+)
        \s*(?:(?:\|\||\?\?)\s*(?:'[^']*'|"[^"]*"|\d+)\s*)?\)?
        (?:\.(?:replace|slice|trim|toString|toUpperCase|toLowerCase)\([^()]*\))*
        \s*\}""", re.X)

# Destinos que NAO sao HTML: ali o navegador escreve texto como texto, e escapar estragaria.
_SO_TEXTO = (".textContent=", "toast(", "confirm(", "alert(", "createPriceLine(",
             "txt('",           # o escritor de textContent dos tiles
             "const qual=")     # vira o texto do confirm() de fechar posicao

# `st` e o retorno de statusEntrada(): duas strings fixas do proprio arquivo, nada do backend.
_LOCAIS = {"st.cls", "st.txt"}


def _app_do_classico():
    """O app do classico e um <script> embutido so (o outro e o preconnect, de duas linhas)."""
    return max(re.findall(r"<script>(.*?)</script>", _ler("web", "classico.html"), flags=re.S),
               key=len)


def test_no_classico_nenhum_campo_do_backend_entra_cru_no_html():
    """O classico.html fica com 'unsafe-inline' (teste acima), entao nele HTML injetado EXECUTA:
    um `<img onerror>` num campo de texto rodava na pagina e lia a credencial do localStorage.
    Sem a CSP por baixo, o escape e a guarda inteira -- e ele tem de valer para todo campo, nao
    para os que alguem lembrou. Quem acrescentar `${t.campo}` num template deste arquivo cai
    aqui: ou passa por escH(), ou o destino e texto e entra em _SO_TEXTO dizendo por que."""
    js = _app_do_classico()
    crus = []
    for m in _CAMPO_CRU.finditer(js):
        campo = m.group("campo")
        # `id` e INTEGER PRIMARY KEY: o SQLite recusa o que nao for inteiro. `.length` e do JS.
        if campo.endswith((".id", ".length")) or campo in _LOCAIS:
            continue
        # a instrucao em que o placeholder mora, do fim da anterior ate ele
        ini = max(js.rfind(fim, 0, m.start()) for fim in (";\n", "{\n", "}\n"))
        if any(alvo in js[ini:m.start()] for alvo in _SO_TEXTO):
            continue
        crus.append(f"linha {js.count(chr(10), 0, m.start()) + 1} do script: {m.group(0)}")
    assert crus == [], "\n".join(crus)

    # O que a regra de cima nao enxerga: concatenacao, callback de .map() e argumento de funcao.
    for limpo in ("txt+=escH(a.motivo)", "${escH(m)}</span>", "escH(m.n_trades||0)",
                  "${escH(gordos.map("):
        assert limpo in js, limpo

    # num() e brl() escapam na fonte. `"<img>".toLocaleString()` devolve a propria string: sem
    # isto, uma coluna REAL com texto dentro (o SQLite aceita) saia crua por um "formatador".
    assert "const num=v=>escH(" in js and "const brl=v=>'R$ '+escH(" in js
    for entidade in ("'&amp;'", "'&lt;'", "'&gt;'", "'&quot;'", "'&#39;'"):
        assert entidade in js, entidade      # aspas inclusive: escH() tambem vai em atributo


def test_no_classico_handler_em_atributo_so_recebe_id_ou_json_escapado():
    """Dentro de `onclick=` o texto e JavaScript, e escape de HTML nao segura JavaScript. Ali so
    entra `id` (inteiro garantido pelo banco) ou o JSON do sinal -- e este passa por escH(),
    porque JSON.stringify() nao escapa aspas simples e o atributo e `onclick='...'`: um apostrofo
    num campo do sinal fechava o atributo e o resto virava marcacao."""
    js = _app_do_classico()
    handlers = re.findall(r"""\son[a-z]+=(?:"[^"\n]*"|'[^'\n]*')""", js)
    assert len(handlers) >= 10                       # a regex continua achando os handlers
    for h in handlers:
        for expr in re.findall(r"\$\{([^}]*)\}", h):
            assert re.fullmatch(r"[\w$]+\.id|json|escH\(JSON\.stringify\(s\)\)", expr), h
    assert "const json=escH(JSON.stringify(s));" in js
