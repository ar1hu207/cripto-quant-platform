"""[P2-41] O versionamento so vale se as duas metades nao puderem andar separadas.

O defeito que originou estes testes: `"0.3"` era literal em TRES pontos do `api.py` e atravessou
M1 a M6 sem se mover -- o painel dizia `v0.3` a um sistema que ja nao era o `0.3` havia meses.
E o terceiro literal era o pior: uma auto-checagem que conferia `h["versao"] == "0.3"`, isto e,
uma trava que transformava "esqueci de subir a versao" em "nao pode subir a versao".

Entao aqui se testa o que o defeito ensinou, e nao "a versao vale X":
  1. ha uma fonte unica, e ninguem tem copia dela;
  2. subir `VERSAO` sem escrever no CHANGELOG quebra a suite (e vice-versa);
  3. o `/health` continua devolvendo versao E commit -- humano e prova, nunca um pelo outro.
"""
import os
import re

import pytest

import versao

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _changelog():
    with open(os.path.join(RAIZ, "CHANGELOG.md"), encoding="utf-8") as f:
        return f.read()


def test_versao_e_semver():
    assert SEMVER.match(versao.VERSAO), f"VERSAO={versao.VERSAO!r} nao e MAJOR.MINOR.PATCH"


def test_versao_atual_e_a_primeira_entrada_do_changelog():
    """A ordem importa: a versao corrente tem de ser a do TOPO, nao "estar em algum lugar" do
    arquivo. Uma versao que aparece so la embaixo e uma versao que ja foi lancada e voltou."""
    cabecalhos = re.findall(r"^## (\S+)", _changelog(), re.M)
    assert cabecalhos, "CHANGELOG.md sem nenhuma entrada '## <versao>'"
    assert cabecalhos[0] == versao.VERSAO, (
        f"topo do CHANGELOG e {cabecalhos[0]!r} mas versao.VERSAO e {versao.VERSAO!r} -- "
        "subir a versao e escrever a linha do changelog sao a MESMA acao")


def test_nenhum_modulo_repete_a_string_da_versao():
    """A causa raiz, e nao o sintoma. Cravar `!= "0.3"` teria consertado aquele numero e deixado
    o proximo literal nascer igual. O que se proibe e a COPIA: fora do `versao.py` e do
    CHANGELOG, a string da versao nao pode aparecer literal em modulo nenhum."""
    alvo = f'"{versao.VERSAO}"'
    alvo2 = f"'{versao.VERSAO}'"
    achados = []
    for nome in sorted(os.listdir(RAIZ)):
        if not nome.endswith(".py") or nome == "versao.py":
            continue
        with open(os.path.join(RAIZ, nome), encoding="utf-8") as f:
            corpo = f.read()
        if alvo in corpo or alvo2 in corpo:
            achados.append(nome)
    assert not achados, (f"{achados} repetem a string da versao -- importe `from versao import "
                         "VERSAO`. Copia e o que deixou o `0.3` parado por seis meses")


def test_health_devolve_versao_da_fonte_unica_E_o_commit():
    """Os dois, sempre. `versao` responde "o que e isto"; `commit` responde "qual codigo esta
    rodando" -- e as duas maquinas na mesma versao podem estar em commits diferentes, porque a
    `main` avanca e o deploy e ato deliberado (`CLAUDE.md` 5). Trocar um pelo outro devolve o
    painel ao estado em que ele mentia."""
    api = pytest.importorskip("api")
    h = api.health()
    assert h["status"] == "ok"
    assert h["versao"] == versao.VERSAO
    assert "commit" in h
