"""[SHARE-1] Card do resultado do mes para marketing (`web/app/compartilhar.js`).

O PNG sai da casa para rede social. Duas promessas que nao podem regredir sem alguem perceber:
1. NENHUM valor em R$ no card -- so percentuais e contagens. A banca e assunto do dono.
2. O card DIZ que a conta e simulada. Publicar a % de paper trading sem isso vende como real um
   resultado que nao foi (CLAUDE.md: nao maquiar o resultado).

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


def test_card_diz_que_a_conta_e_simulada():
    assert re.search(r"Conta simulada \(paper trading\)", _desenho())


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
