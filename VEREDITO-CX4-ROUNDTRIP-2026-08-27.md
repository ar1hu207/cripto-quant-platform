# [CX-4] Veredito — o round-trip realista corta o prêmio pela metade

> Rodada de 2026-08-27, branch `terr/cx2-maker-oi`, 20,0 min, 30 backtests.
> Saída literal em `RODADA-CX4-ROUNDTRIP-2026-08-27.txt`.

## 1. Por que este card existiu

O `[CX-1]` cobrou **maker nas duas pernas**. Isso é otimista: a saída do motor é stop/trailing,
que é **ordem a mercado por natureza** — quando o preço vira contra, não dá para pendurar limite
e torcer. O round-trip realista do post-only é **maker entrando + taker saindo**.

## 2. A tabela

| nível | trades | PnL OOS | Sharpe | IC95% Sharpe | PSR | RC p |
|---|---|---|---|---|---|---|
| taker/taker (hoje) | 5424 | +5.167 | 0,955 | (−0,431; 2,026) | 0,9501 | 0,1409 |
| maker-in/taker-out 0,05% | 4722 | +5.841 | 1,062 | (−0,295; 2,191) | 0,9678 | 0,0920 |
| **maker-in/taker-out 0,10%** | 4997 | **+6.007** | **1,134** | (−0,215; 2,291) | 0,9766 | 0,0750 |
| maker-in/taker-out 0,20% | 4481 | +5.821 | 1,098 | (−0,224; 2,205) | 0,9718 | 0,0790 |
| maker/maker 0,10% (otimista) | 4643 | +6.759 | 1,249 | (−0,076; 2,395) | 0,9864 | 0,0515 |

Nenhum nível cruza. **Todos saem `SEM EVIDÊNCIA DE EDGE`.**

## 3. O que isto CORRIGE do que foi dito antes

O `[CX-1]` publicou a manchete *"de três portões reprovados para um, no limite"*. **Essa frase
valia sob a hipótese otimista, e ela não se sustenta com a saída em taker.**

| | portões que passam | portões que falham |
|---|---|---|
| taker de hoje | PSR (0,9501, raspando) | IC-bloco, Reality Check |
| **maker realista 0,10%** | PSR (0,9766, com folga) | **IC-bloco, Reality Check (0,075)** |
| maker otimista 0,20% (`[CX-1]`) | PSR + Reality Check (0,0485) | IC-bloco |

Com custo realista o Reality Check **volta a reprovar**. Continuam **dois** portões falhando, não
um. O que melhorou de verdade foi a margem: RC p de 0,1409 para 0,0750, e PSR de raspando para
folgado.

## 4. Quanto do prêmio sobrevive

- Ganho de Sharpe sobre o taker: **+0,179** realista, contra **+0,294** otimista → **61%**.
- Ganho de PnL: **+R$840** realista, contra **+R$1.592** otimista → **53%**.

Faz sentido pela aritmética: a economia por round-trip cai de 0,06% (0,10% → 0,04%) para 0,03%
(0,10% → 0,07%), exatamente metade.

## 5. O que continua verdadeiro, e é o que importa para a decisão

**Post-only continua valendo, e por larga margem.** +R$840 em três anos sobre o mesmo sinal, os
mesmos trades e a mesma lógica — só mais barato de executar. É a melhoria mais barata que este
projeto já mediu, e **não depende de achar sinal novo**.

O que muda é a expectativa: **isso não coloca a estratégia do lado certo da linha.** Aproxima.
Quem esperava que baratear a execução resolvesse o veredito precisa reler a §3.

## 6. Consequência para o código, e ela já está implementada

O `[EX-1]` foi escrito assumindo exatamente este modelo: `taxa_maker` cobrada **só na perna de
entrada**, gravada em `posicoes.taxa_entrada`, e a saída sempre em `taxa_por_lado`. A implementação
não precisa mudar — este card confirma que ela está certa, e diz quanto ela vale.

## 7. O que continua não medido

Se a Binance preenche `postOnly` nesses instantes, e o que fazer com os sinais que não enchem.
**Backtest não responde isso.** Só o paper trading com a execução ligada responde — e agora ele
existe.
