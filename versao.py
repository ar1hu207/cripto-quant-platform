"""Versão da plataforma — FONTE ÚNICA.

**Por que este arquivo existe.** Até 2026-08-24 a string `"0.3"` era literal repetida em três
pontos do `api.py` (o `FastAPI(version=)`, o `/health` e a auto-checagem que conferia o
`/health`). Ela atravessou M1, M2, M3, M4, M5 e M6 sem se mover — o painel dizia `v0.3` a um
sistema que já não era o `0.3` havia meses. **Versão parada é pior que versão nenhuma**: a
ausência não afirma nada, e uma versão errada afirma. E o terceiro literal era o pior dos três:
era um TESTE conferindo que a versão continuava `"0.3"`, ou seja, uma trava que transformava
"esqueci de subir a versão" em "não pode subir a versão".

Agora há um lugar só. Quem sobe a versão edita aqui e escreve a linha no `CHANGELOG.md`; o
`test_versao.py` recusa as duas metades separadas.

**Qual número muda (SemVer adaptado a uma plataforma que não tem consumidor externo):**

* `MAJOR` — muda o que o operador entende por "o sistema". Trocar a política de saída que roda
  ao vivo, mudar o significado de uma coluna do banco, aposentar uma rota do painel.
* `MINOR` — capacidade nova sem quebrar o que existe: rota, tela, guarda, indicador,
  instrumento de pesquisa.
* `PATCH` — correção que não muda contrato: bug, texto, desempenho, teste.

**O que a versão NÃO responde, e o `/health` responde:** *qual código está rodando*. Duas
máquinas na mesma `0.4.0` podem estar em commits diferentes, porque `main` avança e o deploy é
ato deliberado (`CLAUDE.md` §5). Por isso o `/health` devolve os DOIS — `versao` para humano,
`commit` para prova. Nunca troque um pelo outro.
"""

VERSAO = "0.4.0"
