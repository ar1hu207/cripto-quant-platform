# -*- coding: utf-8 -*-
"""Embrulha as provas versionadas e reexecutaveis que o M1 e o M2 deixaram, mais o
`test_sim.py` que o proprio [P2-6] reescreveu.

Decisao registrada na §4c do PLANO-EXECUCAO, ponto 1: o pytest **chama** essas provas, nao
as move. Move-las para dentro de `tests/` exigiria editar `api.py`, `db.py` e `simulador.py`
para expor as funcoes -- plataforma viva, fora do territorio T-TESTE -- e o portao de
fronteira (§9.4/P2) reprova arquivo fora da lista mesmo com o codigo certo. Embrulhar custa
este arquivo e mantem o diff auditavel.

**Por que subprocesso, e nao `from simulador import _prova_funding`.** Duas delas nao tem
escolha -- `prova_m1.py` roda no import (nao tem funcao para chamar) e `test_auth.py` precisa
de um processo por cenario, porque `DASH_PASS` e lido no import do `api.py`. E `db._prova_p2_11`
**reatribui o global `db.DB` e nunca o restaura** (db.py:442-444): chamada em processo, ela
deixaria todo teste posterior escrevendo no banco sintetico dela. As outras duas restauram o
que mexem, mas ainda compartilhariam globais de modulo (`funding_medicao`, `_scan_sched`,
`_cfg_avisado`) com os testes unitarios desta suite. Uniformizar em subprocesso faz cada prova
medir aqui exatamente o que ela mede quando um humano roda o comando documentado -- que e o
unico jeito de o "verde no pytest" significar a mesma coisa que o "verde no terminal".

A contagem minima de asseracoes de cada prova esta na tabela abaixo e e conferida. Nao e
enfeite: uma prova pode passar com exit 0 tendo perdido metade das asseracoes num refactor
distraido, e o exit code sozinho nao acusa. O comparador e `>=` para nao punir quem
acrescentar asseracao -- so quem sumir com as que existem.
"""
import os
import re
import subprocess
import sys

import pytest

from conftest import RAIZ


# (rotulo, argumentos depois do python, asseracoes minimas, o que a prova cobre)
PROVAS = [
    pytest.param("prova_m1.py", ["prova_m1.py"], 7,
                 "guardas do M1: [P1-6] claim atomico, [P1-1] marcacao por posicao, "
                 "[P1-7] panico, [P1-8] config invalida, [P2-12] reset",
                 id="prova_m1"),
    pytest.param("simulador.py", ["simulador.py"], 11,
                 "[P2-10] funding: sinal, janela de settlements, e falha de medicao que "
                 "grava NULL em vez de zero",
                 id="simulador_funding"),
    pytest.param("api.py", ["api.py"], 27,
                 "[P1-4] _amostrar, [P2-15] ultimo_erro e cadencia do scan, [P2-3] commit no /health",
                 id="api"),
    pytest.param("test_auth.py", ["test_auth.py"], 27,
                 "[P0-1] o backend nao serve nada sem credencial (3 cenarios, 1 processo cada)",
                 id="auth"),
    pytest.param("test_sim.py", ["test_sim.py"], 13,
                 "caminho fim a fim sinal -> posicao -> fechamento, mais liquidacao no "
                 "preco de `_preco_liquidacao` (reescrito pelo proprio [P2-6])",
                 id="sim"),
    pytest.param("db.py prova", ["db.py", "prova"], 18,
                 "[P2-11] indices, poda e leitura da curva de equity sobre 1 ano sintetico",
                 id="db_equity", marks=pytest.mark.lento),
]


def _rodar(argv, tmp_path):
    """Roda a prova como um humano rodaria, so que com `DB_PATH` num diretorio temporario.

    Cada prova ja aponta o proprio banco para um temporario, entao o `DB_PATH` aqui e
    redundancia deliberada: se uma delas um dia esquecer, ela ainda nao alcanca o
    `trading.db` da raiz (vazio aqui, mas na VM e o historico inteiro -- CLAUDE.md §1).
    """
    env = dict(os.environ,
               DB_PATH=str(tmp_path / "prova.db"),
               PYTHONIOENCODING="utf-8")     # as provas imprimem acento; o console e cp1252
    return subprocess.run([sys.executable] + argv, cwd=RAIZ, env=env, timeout=900,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def _asseracoes_que_passaram(saida):
    """`  PASSA  <nome>` nas provas do M1/M2, `  PASS  <nome>` no `test_auth.py`."""
    return len(re.findall(r"^\s+(?:PASSA|PASS)\s", saida, re.M))


@pytest.mark.parametrize("rotulo,argv,minimo,cobre", PROVAS)
def test_prova_versionada(tmp_path, rotulo, argv, minimo, cobre):
    r = _rodar(argv, tmp_path)
    saida = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, (
        f"`python {rotulo}` saiu com {r.returncode} -- cobre {cobre}\n"
        f"---- saida ----\n{saida}")
    passaram = _asseracoes_que_passaram(saida)
    assert passaram >= minimo, (
        f"`python {rotulo}` passou em {passaram} asseracoes, e a prova tinha {minimo}. "
        f"Asseracao que some nao aparece no exit code.\n---- saida ----\n{saida}")
