# [CX-3] Veredito — foi a TAXA. O preço de entrada não vale quase nada.

> Rodada de 2026-08-27, branch `terr/cx2-maker-oi`, 14,4 min, 30 backtests.
> Pergunta do dono; grade e prognóstico fixados antes em
> `PRE-REGISTRO-CX3-GATILHO-2026-08-27.md` (`0180421`).
> Saída literal em `RODADA-CX3-GATILHO-2026-08-27.txt`.

## 1. A tabela

| nível | fill | trades | PnL OOS | Sharpe | PSR | RC p |
|---|---|---|---|---|---|---|
| taker (hoje) | 100% | 5424 | +5.167 | 0,955 | 0,950 | 0,141 |
| gatilho off 0,05% | 93,3% | 5366 | +5.469 | 1,033 | 0,964 | 0,137 |
| gatilho off 0,10% | 88,3% | 5300 | +4.991 | 0,960 | 0,952 | 0,154 |
| gatilho off 0,20% | 76,6% | 4211 | +4.026 | 0,762 | 0,901 | 0,159 |
| **maker off 0,10%** (ref) | 88,3% | 4643 | **+6.759** | **1,249** | **0,986** | **0,052** |

## 2. A comparação que decide, e ela é limpa

**`gatilho off 0,10%` × `maker off 0,10%`.** Mesmo nível, **mesmo fill (88,3%)**, mesma condição
de entrada, mesmo instante. A **única** diferença é como se paga:

| | Sharpe | PnL | RC p |
|---|---|---|---|
| gatilho (taker + slippage) | 0,960 | +R$4.991 | 0,154 |
| maker (post-only) | **1,249** | **+R$6.759** | **0,052** |

**Todo o ganho do `[CX-1]` era a taxa.** Esperar o preço vir até você, sozinho, não move nada:
o `gatilho off 0,10%` sai em Sharpe 0,960 contra 0,955 do taker de hoje — **diferença de 0,005**,
ruído.

## 3. E esperar demais chega a MACHUCAR

Sob taker, quanto mais fundo se espera, pior fica: **1,033 → 0,960 → 0,762**. É seleção adversa
aparecendo limpa — o trade que volta até o seu preço é, em média, o trade que depois vai contra
você. Você filtra para pior.

O que salva isso no post-only é justamente a taxa: no `[CX-1]`, sob maker, a mesma varredura deu
**1,203 / 1,249 / 1,250** — plana. **A economia de taxa paga a seleção adversa. O preço melhor,
sozinho, não paga.**

Isso também explica por que a curva do `[CX-1]` era plana, coisa que eu não tinha entendido lá:
não era "o offset não importa", eram duas forças opostas se cancelando — seleção adversa puxando
para baixo e taxa segurando por cima.

## 4. O placar do prognóstico

| # | prognóstico | resultado |
|---|---|---|
| aposta principal | foi a **TAXA**, e a proposta do dono não captura o ganho | **CERTO** |
| número apostado | gatilho entre 0,95 e 1,10 de Sharpe | **certo em 0,05% (1,033) e 0,10% (0,960)**; errei em 0,20%, que caiu para 0,762 — pior do que eu previa |
| razão registrada | "a curva plana do `[CX-1]` denuncia que o constante (a taxa) é que trabalha" | **confirmada, e melhorada:** a planura era cancelamento de duas forças, não ausência de efeito |

## 5. O que isto decide, na prática

**Post-only é obrigatório. Não existe atalho.**

- Ficar olhando o preço e mandar a mercado **não funciona** — paga taker, e ainda herda a seleção
  adversa sem a compensação.
- O ganho inteiro mora em **~0,03% por lado** de taxa. Isso é frágil por construção: uma ordem
  limite que cruza o livro e executa na hora é cobrada como **taker**, e aí o ganho evapora sem
  ninguém perceber.
- Por isso o que vai para a plataforma é **`postOnly`/`GTX` explícito**, não "ordem limite". A
  corretora tem de recusar a execução imediata em vez de executá-la cara.

## 6. Observação de passagem, não é defeito

`gatilho 0,10%` fecha 5.300 trades e `maker 0,10%` fecha 4.643, apesar do fill idêntico. Não é
inconsistência: o `gatilho` paga slippage sobre o mesmo limite, entra alguns centavos pior, e com
trailing apertado isso antecipa saídas — o motor fica livre mais cedo e reentra mais vezes. Mais
trades e menos dinheiro, que é a assinatura de custo comendo resultado.

## 7. O que continua não medido

Se a Binance de fato preenche uma ordem `postOnly` nesses instantes, e o que fazer com os ~12%
de sinais que não enchem. **Backtest não responde isso** — só ligar no paper trading responde.
