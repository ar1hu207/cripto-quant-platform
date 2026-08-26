# [CX-1] Veredito — o maker com o fill junto

> Rodada de 2026-08-26, branch `terr/custo-execucao` sobre `main = d9bab53`. 18,9 min.
> Hipótese, grade e prognóstico fixados **antes** em `PRE-REGISTRO-CX1-MAKER-2026-08-26.md`.
> Saída literal em `RODADA-CX1-MAKER-2026-08-26.txt`.

## 1. A tabela

Mesma janela, mesma grade de 6 configs, mesma política. Muda a taxa **e o fill**.

| nível | fill | trades | PnL OOS | Sharpe | IC95% Sharpe | PSR | RC p | DSR | veredito |
|---|---|---|---|---|---|---|---|---|---|
| taker 0,05% (hoje) | 100% | 5424 | +5167 | 0,955 | (−0,431; 2,026) | 0,9501 | 0,1409 | 0,0188 | SEM EVIDÊNCIA |
| **maker TETO** (off 0) | 100% | 5327 | +7766 | 1,423 | (0,077; 2,493) | 0,9951 | 0,0455 | 0,1005 | **edge SOBREVIVE** |
| maker off 0,05% | 93,3% | 4421 | +6736 | 1,203 | (−0,112; 2,321) | 0,9829 | 0,0625 | 0,0763 | SEM EVIDÊNCIA |
| maker off 0,10% | 88,3% | 4643 | +6759 | 1,249 | (−0,076; 2,395) | 0,9864 | 0,0515 | 0,0487 | SEM EVIDÊNCIA |
| maker off 0,20% | 76,6% | 4481 | +6651 | 1,250 | (−0,050; 2,353) | 0,9862 | 0,0485 | 0,0423 | SEM EVIDÊNCIA |

## 2. O teto cruzou — e o pré-registro já dizia por que isso não vale

O `maker TETO` sai `edge SOBREVIVE` nos três portões (IC-bloco `(0,372; 16,75)` > 0, PSR
0,9951, RC p 0,0455). **Não comemore.** Ele é o nível cujo fill é 100% *por definição de OHLC*,
e — o que eu não tinha notado ao registrar — ele também **zera o slippage**, porque quem põe o
preço não paga travessia: `e = lim`, sem o `slip=0,0002` que o taker paga.

Por isso ele não reproduz a linha `maker 0,02%` do `[Q-15]` (Sharpe 1,263), e sim quase a linha
**`taxa 0%`** dela (1,466). São 1,423. **O teto é o mundo sem atrito, com outro nome.**

## 3. O que a execução realista faz — e é aqui que está o resultado

Os três níveis com fill < 100% andam todos na mesma direção, e é uma direção grande:

- **Sharpe 0,955 → 1,20-1,25.**
- **RC p 0,1409 → 0,0485-0,0625.** A 0,20% de concessão o Reality Check **passa** (0,0485 ≤ 0,05).
- **PSR 0,9501 → 0,986-0,987.** Passa nos três.
- **Menos trades e mais dinheiro:** 5424 → ~4.500, e +R$5.167 → +R$6.700.

**O que segura o veredito é um portão só, e por um fio:** o IC-bloco da média/dia. A 0,20% ele
sai `(−0,269; 15,199)` — inclui o zero por 0,27 de um intervalo de 15,5 de largura.

Ou seja: a estratégia de hoje sai de **três portões reprovados** para **um reprovado, no limite**,
só trocando como a ordem entra. Sem tocar em sinal, parâmetro ou grade.

## 4. Onde eu errei o prognóstico

| # | prognóstico | o que deu |
|---|---|---|
| 1 | teto reproduz o `maker` do `[Q-15]` (~1,26), `SEM EVIDÊNCIA` por um fio | **ERRADO.** 1,423 e `edge SOBREVIVE` — porque o teto também zera o slippage |
| 2 | off 0,05% melhor que o taker, talvez melhor que o teto | **metade.** Muito melhor que o taker; pior que o teto |
| 3 | a curva tem topo no meio (0,05%) e cai em 0,20% | **ERRADO.** É praticamente **plana**: 1,203 / 1,249 / 1,250. O teste de fumaça no BTC isolado não generalizou |
| 4 | nenhum nível cruza para `edge SOBREVIVE` | **certo para os realistas**, errado para o teto |

O erro do 3 é o mais útil: **a concessão de preço quase não importa entre 0,05% e 0,20%.** O
ganho vem de ser maker, não de onde se põe o limite. Perder 23% dos fills custa quase nada.

## 5. Concentração — o teste que matou o `[Q-17]`

Nenhum nível é resultado de um fold só:

| nível | top-5 dias | folds positivos | maior fold |
|---|---|---|---|
| taker | 15,1% | 4/5 | 0,45 |
| teto | 15,2% | 4/5 | 0,36 |
| off 0,10% | 14,4% | 4/5 | 0,39 |
| off 0,20% | 14,2% | 4/5 | 0,44 |

Para contraste, o `[Q-17]` reprovou aqui com **maior fold = 1,0**. Este não tem esse defeito.

## 6. O que este veredito NÃO autoriza

- **Não muda o default.** `entrada="taker"` segue sendo o caminho da plataforma.
- **Não diz que dá para operar maker.** O backtest não mede se a corretora trata a ordem como
  maker, nem o que acontece com o sinal perdido no vivo — ele o descarta, e o vivo teria de
  decidir entre cancelar e virar taker.
- **`n_trials = 1210` subconta** esta grade de 30 (herdado do `[Q-15]` para comparabilidade).
  Afeta o DSR, que é diagnóstico; os três portões não dependem dele.
- **Um veredito que aparece depois de varrer 5 níveis é candidato, não conclusão.** O caminho
  honesto é re-medir fora desta janela.

## 7. O próximo experimento, e por que ele precisa de pré-registro

O `[Q-17]` mediu que o portão de open interest **corta 40% dos trades perdendo 22% do P&L**.
Este card mediu que **menos trade com taxa menor move o veredito**. São o mesmo remédio por
dois caminhos, e nenhum dos dois sozinho cruzou a linha com execução realista.

`CX-2` = maker realista **+** portão de OI. **Combinar dois resultados já vistos é tentativa
nova**, e entra com pré-registro próprio e `n_trials` que conte a grade inteira — foi
exatamente por isso que o `[Q-17]` levou falta na própria §4.
