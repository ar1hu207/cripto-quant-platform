# golden/ — a saída congelada da régua `[N-6]`

Estes dois arquivos são o **teste de regressão ponta a ponta** da `pesquisa/validacao.py`. A
`REVISAO-ITEM1.md` §E chamou o golden file de *"o teste mais importante da lista e o único
ausente"* (F2) e prescreveu a ordem: **seed → congelar a saída → só então refatorar**.

| arquivo | o que é |
|---|---|
| `entrada_walk_forward.json` | o **painel sintético congelado**: 3 configs × ~1.000 dias de trades, com `ts_saida`. É a entrada de `walk_forward`, e ela não muda mais |
| `saida_walk_forward.json` | o **retrato numérico** que a régua tem de devolver sobre esse painel: série diária OOS inteira, p-valores, DSR, calibração, fold a fold, e digests sha256 de `oos`, `por_cfg`, `matriz_is` e `serie_naive` |

```bash
python -m pesquisa.validacao golden            # confere; sai != 0 se divergir (~3 s)
python -m pytest tests/test_validacao.py -k golden
```

## Por que estes arquivos são versionados apesar do `.gitignore`

`.gitignore` tem `dados_cache/`, e com razão: o que normalmente mora ali é **cache de download**
— CSV de OHLCV com data no nome, regerável e pesado. Este diretório é o contrário disso: é
**artefato de prova**, e prova que não está no repositório não é prova. Por isso os três
arquivos entraram por `git add -f`, exceção declarada no commit do `[N-6]`.

⚠️ **Consequência operacional:** como o diretório-pai continua ignorado, `git add -A` **não**
pega mudanças aqui. Quem regravar o golden tem de adicionar por caminho explícito:

```bash
git add -f pesquisa/dados_cache/golden/
```

## Quando (e como) regravar

```bash
python -m pesquisa.validacao golden --gravar
```

**Regravar é ato deliberado.** Se o golden quebrou, a pergunta não é *"como faço passar"* — é
*"que número mudou, e eu queria que mudasse?"*. O comando imprime **caminho a caminho** o que
divergiu, exatamente para que essa pergunta tenha resposta antes de qualquer regravação. O
commit que regrava tem de dizer qual número mudou e por quê; regravar para ficar verde é o
único jeito de este arquivo deixar de valer alguma coisa.

## O que ele NÃO congela, de propósito

A **prosa**: `veredito["motivo"]` e `purga_motivo` são frases derivadas de números que já estão
congelados aqui. Golden que quebra quando alguém conserta uma vírgula é golden que alguém
regrava sem ler.

E a armadilha oposta, que é a versão-sintoma deste item: **gravar o texto do veredito e chamar
de teste**. `SEM_EVIDENCIA` continua saindo igual mesmo que o Sharpe anualizado vá de −1,1 para
+1,4. A prova disso está rodada: com a seed do `PADRAO` mutada de 42 para 43, a classe do
veredito **não muda** e 24 números mudam — inclusive o Reality Check (0,8666 → 0,8806) e o
IC-bloco. É o `test_golden_PEGA_uma_mudanca_de_numero` que fixa isso.
