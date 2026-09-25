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


def _csp(caminho):
    for regra in _headers(caminho):
        for h in regra["headers"]:
            if h["key"] == "Content-Security-Policy":
                return {d.split()[0]: d.split()[1:] for d in
                        (x.strip() for x in h["value"].split(";")) if d}
    raise AssertionError(f"{caminho} sem Content-Security-Policy")


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
