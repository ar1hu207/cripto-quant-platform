# [CX-2] Veredito — somar informação ao custo PIOROU tudo

> Rodada de 2026-08-26/27, branch `terr/cx2-maker-oi`, 58,9 min, 72 backtests.
> Grade e prognóstico fixados antes em `PRE-REGISTRO-CX2-MAKER-OI-2026-08-26.md` (`9f4d10e`) e
> no adendo `e552d9c`. Saída literal em `RODADA-CX2-MAKER-OI-2026-08-26.txt`.

## 1. A tabela, e a comparação que importa

Mesma janela, mesma política, mesma alavancagem de produção. A **única** diferença para o
`[CX-1]` é que a grade do walk-forward ganhou a dimensão de open interest: 18 configs
(6 conv/adx × 3 modos) em vez de 6.

| nível | `[CX-1]` sem OI na grade | `[CX-2]` com OI na grade | Δ Sharpe |
|---|---|---|---|
| taker 0,05% | 0,955 · +R$5.167 · RC p 0,141 | **0,734** · +R$3.449 · RC p 0,121 | **−0,221** |
| maker off 0,05% | 1,203 · +R$6.736 · RC p 0,063 | **1,103** · +R$5.274 · RC p 0,061 | −0,100 |
| maker off 0,10% | 1,249 · +R$6.759 · RC p 0,052 | **1,081** · +R$4.985 · RC p 0,051 | −0,168 |
| maker off 0,20% | 1,250 · +R$6.651 · **RC p 0,0485** | **1,215** · +R$5.492 · **RC p 0,0725** | −0,035 |

**Todos os quatro níveis pioraram.** E o nível que no `[CX-1]` passava no Reality Check
(0,0485 ≤ 0,05) deixou de passar (0,0725). Nenhum veredito cruzou. Nada aqui está mais perto da
linha do que o `[CX-1]` já estava — está mais longe.

## 2. Por que este resultado é limpo, e não uma comparação torta

A grade do `[CX-2]` **contém** a do `[CX-1]`: as 6 configs com `oi_modo="off"` são exatamente as
6 configs do card anterior. O treino podia ter reproduzido o `[CX-1]` inteiro simplesmente
escolhendo `off` em todo fold.

**Ele nunca escolheu.** Vinte escolhas de fold (4 níveis × 5 folds), **zero `off`**:

```
taker 0,05%       (50,22,peso) | (65,22,concorda) | (65,22,concorda) | (65,22,concorda) | (65,22,concorda)
maker off 0,05%   (50,25,peso) | (50,25,peso)     | (65,22,concorda) | (65,22,concorda) | (55,22,concorda)
maker off 0,10%   (50,25,peso) | (50,25,peso)     | (65,22,concorda) | (55,22,concorda) | (55,22,concorda)
maker off 0,20%   (50,22,peso) | (50,22,peso)     | (65,22,concorda) | (55,22,concorda) | (55,22,concorda)
```

**Dada a opção, o treino andou para longe da config que teria ido melhor no futuro não-visto.**
Isso não é inferência sobre overfitting — é overfitting demonstrado, com a hipótese nula
disponível em todo fold e recusada em todos.

O `[Q-17]` viu a primeira metade disto e leu como promissor ("o treino escolheu o portão em 5
folds de 5"). Era a metade que não decide. **A segunda metade é que o OOS paga a conta.**

## 3. A concentração piorou junto

| nível | `[CX-1]` maior fold | `[CX-2]` maior fold | folds positivos |
|---|---|---|---|
| taker | 0,45 | **0,82** | 3/5 (era 4/5) |
| maker off 0,20% | 0,44 | 0,51 | 4/5 |

No taker, 82% do resultado mora num fold só. É a direção do defeito que reprovou o `[Q-17]`
(`maior fold = 1,0`), agora aparecendo também aqui.

## 4. O placar do prognóstico

| # | prognóstico | resultado |
|---|---|---|
| 1 | não vai ser aditivo, ~o melhor dos dois | **certo, e mais forte:** não é aditivo, é **subtrativo** |
| 2 | espero que CRUZE em pelo menos um nível | **ERRADO.** Nada cruzou, e tudo se afastou da linha |
| 3 | `peso` aumenta os trades em vez de cortar | **certo** (5.693 → 6.319 na config amostrada) |
| 4 | a curva de concessão segue plana | **quase:** 1,103 / 1,081 / 1,215 — plana com mais ruído, e a ordem trocou |

O 2 era o prognóstico arriscado, escrito com "confiança pouco acima de meio a meio". Errou.

## 5. O que isto significa para o rumo

**A melhor configuração medida até hoje continua sendo a do `[CX-1]`: execução maker, sozinha,
sem portão de informação.** Adicionar a única fonte de informação que o projeto tem hoje —
divergência de open interest — não aproximou nada; afastou.

Isso NÃO diz que informação não serve. Diz três coisas mais estreitas, e é só isso que está
medido:

1. **Este** sinal (`d_oi` de uma barra, sem limiar, sem janela, sem suavização) não generaliza.
2. Ele é um **atrator in-sample**: piora o OOS *porque* o treino gosta dele.
3. Enfiar uma dimensão nova na mesma grade de walk-forward tem custo — mais configs para
   escolher é mais chance de escolher errado. Uma fonte de informação nova precisa provar que
   paga esse custo, e esta não pagou.

## 6. O que ficou em aberto, e o que eu NÃO posso concluir daqui

- **Não separei "o portão de OI é ruim" de "a grade de 18 é ruim".** O controle que separaria os
  dois é rodar 18 configs onde as 12 extras são dimensões de LIXO (ruído sorteado): se o estrago
  for o mesmo, a culpa é do tamanho da grade, não do open interest. **Esse controle não rodou.**
- **Continua valendo o viés que declarei antes de rodar:** esta foi a terceira visita à mesma
  janela de 3 anos, e nenhum teste desconta isso.
- **Nada muda em produção.** `entrada="taker"` e `oi_modo="off"` seguem sendo o default.
