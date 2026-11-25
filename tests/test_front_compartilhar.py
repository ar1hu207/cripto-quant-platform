"""[SHARE-1] Card do resultado do mes para marketing (`web/app/compartilhar.js`).

O PNG sai da casa para rede social. Promessa que nao pode regredir sem alguem perceber:
NENHUM valor em R$ no card -- so percentuais e contagens. A banca e assunto do dono.

Existia uma segunda (o card dizer que a conta e simulada). O dono a retirou em 25/11/2026,
avisado de que sem ela a % de paper trading pode ser lida como lucro real: decisao dele.

Como os outros test_front_*: so leitura de arquivo, sem navegador, para rodar no CI.
"""
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(RAIZ, "web")


def _ler(*partes):
    with open(os.path.join(*partes), encoding="utf-8") as f:
        return f.read()


def _desenho():
    """o corpo de desenhar(): e so ele que vira pixel no PNG"""
    js = _ler(WEB, "app", "compartilhar.js")
    a = js.index("function desenhar(")
    return js[a:js.index("return cv;", a)]


def test_card_nao_desenha_dinheiro():
    d = _desenho()
    assert "R$" not in d
    for fmt in ("F.brl", "F.money", "fmt.brl", "fmt.money", "pnl_reais", "banca"):
        assert fmt not in d, f"desenhar() usa {fmt}: valor em dinheiro no card"


def test_os_dois_paineis_carregam_o_modulo_depois_do_api():
    for html in ("index.html", "m.html"):
        srcs = re.findall(r"<script[^>]*\ssrc=\"([^\"]+)\"", _ler(WEB, html))
        assert "app/compartilhar.js" in srcs, html
        assert srcs.index("app/api.js") < srcs.index("app/compartilhar.js"), html


def test_logo_do_card_existe_e_e_local():
    js = _ler(WEB, "app", "compartilhar.js")
    m = re.search(r"i\.src = '([^']+)'", js)
    assert m and not m.group(1).startswith(("http", "//")), "logo do card tem de ser caminho relativo"
    assert os.path.isfile(os.path.join(WEB, m.group(1)))
