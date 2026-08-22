# -*- coding: utf-8 -*-
"""Pesquisa viva: a regua que mede estrategia. Nao e codigo de producao. [P2-16]

**Por que isto e um pacote, e nao um diretorio de scripts soltos.**

`scoring.py` e `indicadores.py` ficaram na RAIZ (decisao 3 da §4c do PLANO-EXECUCAO: a
plataforma viva nao sai da raiz, porque o `deploy/cripto-bot.service` roda `uvicorn api:app`
com `WorkingDirectory` na raiz). Mas eles sao compartilhados: `scoring` e importado por
`signal_engine` (vivo) E por `backtest_plataforma`/`validacao`/`validar_reversao*` (aqui).
Esse compartilhamento **e** a paridade backtest<->live, e por isso nao se duplica.

Consequencia: `python pesquisa/validacao.py` NAO funciona -- rodar um arquivo por caminho poe
`pesquisa/` no `sys.path`, nao a raiz, e o `import scoring` falha. O comando e:

    python -m pesquisa.validacao        # da RAIZ do repositorio

`-m` poe o diretorio corrente no `sys.path`, entao `import scoring` acha a raiz e
`from pesquisa.dados import ...` acha este pacote. Cada modulo daqui traz o comando no
proprio docstring.

**Por que pacote e nao um shim de `sys.path` no topo de cada arquivo.** As duas saidas
resolvem o import. A diferenca esta no que um agente novo le. Com o pacote, a fronteira
aparece na propria linha de import: `import scoring` = plataforma (raiz),
`from pesquisa import dados` = pesquisa. Com o shim, todo import fica com a mesma cara e a
divisoria some do codigo -- que e exatamente a armadilha que o [P2-16] veio remover. O shim
tambem seria boilerplate copiado em 8 arquivos, ou seja, 8 lugares para apodrecer em vez de
um.

**O que NAO passa pelo portao de compilacao do deploy.** O `deploy/atualizar.sh` compila
`./*.py` (glob de raiz, nao recursivo) e continua assim de proposito -- ver o comentario no
passo 4 daquele script. Pesquisa nao e importada por `api.py` e nao sobe com o servico.
"""
