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
    """O texto da CSP. E UMA regra so, para todo caminho (ver o teste do classico, abaixo)."""
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


def test_nenhum_caminho_tem_excecao_na_csp_nem_o_classico():
    """Existiu uma regra PROPRIA para o /classico.html, com 'unsafe-inline' no script-src: ele
    tinha o app num <script> embutido e dezenas de `onclick=`. Nela HTML injetado executava, e o
    escape de cada campo era a guarda inteira. O app foi para web/classico.js e os handlers viraram
    data-acao; a excecao saiu. Quem a recolocar "porque um botao do classico parou" desfaz a
    segunda camada: o conserto e tirar o handler do HTML (teste de baixo), nao afrouxar aqui."""
    for arquivo in ("vercel.json", os.path.join("web", "vercel.json")):
        regras = _regras_csp(arquivo)
        assert [r["source"] for r in regras] == ["/(.*)"], arquivo      # uma regra, todo caminho
        geral = re.compile("^" + regras[0]["source"] + "$")
        for caminho in ("/", "/index.html", "/m.html", "/classico.html", "/classico.js",
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
    for pagina in ("index.html", "m.html", "classico.html"):
        html = re.sub(r"<!--.*?-->", "", _ler("web", pagina), flags=re.S)
        assert re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html) == [], pagina
        assert re.findall(r"<[a-zA-Z][^>]*\son[a-z]+\s*=", html) == [], pagina
        assert "javascript:" not in html, pagina
    app = os.path.join(RAIZ, "web", "app")
    arquivos = [(pasta, nome) for pasta, _, nomes in os.walk(app) for nome in nomes]
    arquivos.append((os.path.join(RAIZ, "web"), "classico.js"))     # o app do painel classico
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
    """O app do classico: era um <script> embutido no classico.html, hoje e web/classico.js."""
    return _ler("web", "classico.js")


def test_no_classico_nenhum_campo_do_backend_entra_cru_no_html():
    """A primeira camada. Enquanto o classico teve 'unsafe-inline', um `<img onerror>` num campo
    de texto rodava na pagina e lia a credencial do localStorage, e o escape era a guarda
    inteira. A CSP estrita (testes acima) passou a segurar o script; o HTML injetado ela nao
    segura: sem escape ele ainda entra na tela (formulario falso, link, botao com data-acao).
    Por isso o escape continua valendo para todo campo, nao para os que alguem lembrou. Quem
    acrescentar `${t.campo}` num template deste arquivo cai aqui: ou passa por escH(), ou o
    destino e texto e entra em _SO_TEXTO dizendo por que."""
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
        crus.append(f"web/classico.js:{js.count(chr(10), 0, m.start()) + 1}: {m.group(0)}")
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


def test_no_classico_o_sinal_so_entra_em_atributo_como_json_escapado():
    """O botao Operar leva o sinal inteiro em `data-sinal='...'` e o clique faz JSON.parse()
    dele (era `onclick='abrirModal({...})'`). O JSON passa por escH() antes de entrar no
    atributo: JSON.stringify() nao escapa aspas simples, e um apostrofo num campo do sinal
    fechava o atributo e o resto virava marcacao. Trocar o handler pelo data-sinal nao pode
    perder isso."""
    js = _app_do_classico()
    codigo = re.sub(r"(?m)^\s*//.*$", "", js)        # o comentario do linhaSinal cita o atributo
    destinos = re.findall(r"""data-sinal=(?:'([^'\n]*)'|"([^"\n]*)")""", codigo)
    assert len(destinos) == 3                        # Operar da linha, Analisar, Operar da analise
    for simples, duplas in destinos:
        assert (simples or duplas) in ("${json}", "${escH(JSON.stringify(s))}"), (simples, duplas)
    assert "const json=escH(JSON.stringify(s));" in js
    assert js.count("JSON.parse(el.dataset.sinal)") == 2          # o clique le o atributo, nao avalia


def _acoes(js, tabela):
    """`const TABELA={ nome:el=>corpo, outro:()=>corpo };` do classico.js, como {nome: corpo}."""
    miolo = re.search(r"const %s=\{\n(.*?)\n\};" % tabela, js, flags=re.S).group(1)
    pares = re.findall(r"(?:^|[\s,])([A-Za-z_]\w*):(?:\w+|\([\w,]*\))=>(\w+\()", miolo)
    assert len(pares) == len(dict(pares)), tabela            # nome repetido: o segundo venceria
    return dict(pares)


def test_no_classico_todo_botao_tem_dono_e_o_app_entra_por_arquivo():
    """Sob `script-src 'self'` o defeito desta troca nao aparece: o botao so nao responde. O
    clique sai de `data-acao` e so roda se o nome estiver numa das duas tabelas do classico.js,
    entao nome sem dono = botao morto, e dono sem botao = codigo morto. As duas tabelas tem
    papeis diferentes (ver o comentario la): acao de botao fixo do HTML nao pode ser atendida
    pela delegacao, senao um data-acao="panico" injetado numa linha passaria a responder."""
    html = re.sub(r"<!--.*?-->", "", _ler("web", "classico.html"), flags=re.S)
    js = _app_do_classico()
    codigo = re.sub(r"(?m)^\s*//.*$", "", js)        # os comentarios citam data-acao="..."

    fixas, linha = _acoes(js, "ACOES_FIXAS"), _acoes(js, "ACOES_LINHA")
    assert len(fixas) == 15 and len(linha) == 9
    assert set(fixas) & set(linha) == set()
    assert set(re.findall(r'data-acao="(\w+)"', html)) == set(fixas)
    assert set(re.findall(r'data-acao="(\w+)"', codigo)) == set(linha)
    for nome, chama in {**fixas, **linha}.items():   # cada acao chama a funcao de mesmo nome
        assert chama == nome + "(", (nome, chama)
        assert re.search(r"\bfunction %s\(" % nome, js), nome
    # o argumento que o onclick trazia escrito agora vem de um data-* do proprio botao
    for acao, dado, n in (("trocaConta", "conta", 4), ("aba", "v", 2), ("subaba", "sub", 7),
                          ("mudarTf", "tf", 6)):
        botoes = re.findall(r'<button[^>]*data-acao="%s"[^>]*>' % acao, html)
        assert len(botoes) == n and all(' data-%s="' % dado in b for b in botoes), acao
    for acao in ("pular", "fechar", "aportarDca", "removerDca"):
        assert re.findall(r'data-acao="%s"(?! data-id="\$\{[ps]\.id\}")' % acao, codigo) == [], acao
    linha_do_sinal = re.search(r'<tr class="sig-row[^>]*>', codigo, flags=re.S).group(0)
    assert 'data-sid="${s.id}"' in linha_do_sinal and 'data-acao="toggleSinal"' in linha_do_sinal
    # a previa do modal recalculava por oninput= nos tres campos
    assert ("['m-valor','m-lev','m-risco'].forEach(id=>document.getElementById(id)"
            ".addEventListener('input',()=>previa()));") in js
    for campo in ("m-valor", "m-lev", "m-risco"):
        assert 'id="%s"' % campo in html

    # O app entra por arquivo, da propria origem. O app/cabeca.js faz o que o <head> fazia em
    # script embutido e em onload= (conexao com o backend, folha de fontes): depois do config.js,
    # que define o API_BASE. O classico.js vem no fim do <body>, sem defer: ele le o DOM ao rodar.
    srcs = re.findall(r'<script[^>]*\ssrc="([^"]+)"', html)
    assert srcs == ["config.js", "app/cabeca.js", "classico.js"]
    for s in srcs:
        assert os.path.isfile(os.path.join(RAIZ, "web", s)), s
    assert re.search(r'<link rel="preload" as="style" href="https://fonts\.googleapis\.com/[^"]+">', html)
    assert html.index('src="classico.js"') > html.index('id="toast"')
    assert "defer" not in re.search(r'<script[^>]*src="classico\.js"[^>]*>', html).group(0)
