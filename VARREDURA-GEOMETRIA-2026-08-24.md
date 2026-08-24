# Varredura de geometria — saída literal, 2026-08-24

Comando (da RAIZ do repo), 94,9 min, 6 workers:

```bash
python -m pesquisa.validacao geometria
```

Grade: `min_conv`(3) x `adx_min`(2) x `k` em {1,2,3,4} x `sd_min` em {0%,1%,2%,4%} = 96 configs.
`n_trials = 550`. Baseline `C trailing 2% fixo` re-medido na MESMA janela.
Leitura e vereditos: `INVESTIGACAO-MOTOR-2026-08-24.md` §7.

```

[baseline] C trailing 2% fixo — 6 configs

=== WALK-FORWARD: C trailing 2% fixo | 1h 1095d | 10x | 6 configs x 5 folds ===
PADRAO (travado): criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga: ATIVA
n_trials = 100 (PISO CONTADO, nao estimativa)
calibracao [Q-7]: o controle nulo rejeitou 12/200 paineis sem sinal (taxa 0.06) -> CALIBRADO
   banda de aceitacao CALCULADA (binomial exata, alfa=0,05, 95%): [4 ; 16] rejeicoes = [0.02 ; 0.08] | IC da taxa medida: (0.03138, 0.10246)

 fold   config (conv/adx)   trades    pnl OOS
    1            (55, 22)     1118  R$  +1720
    2            (55, 22)     1161  R$  +2823
    3            (55, 22)     1120  R$   -728
    4            (55, 22)      985  R$  +2179
    5            (50, 22)      958  R$   -955

OOS agregado: 5342 trades | win 61.2% | PnL R$+5040
  serie diaria da JANELA OOS: 910 dias (863 com P&L nao-nulo) -- o 1o dos 6 segmentos e treino puro e nao entra

-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.
   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO
   White's Reality Check (N=6 configs, 2000 bootstraps de bloco): p = 0.2014
   Hansen SPA (estudentizado):                                     p = 0.2309
   p da melhor config SOZINHA (sem multiplicidade):                p = 0.1629
     -> o grid custou 0.039 de multiplicidade. [F12]
   DSR da melhor config in-sample (50, 22) sobre a SERIE DIARIA (1091 dias): DSR = 0.0625
     (sr=0.0317 vs sr0_esperado=0.0766 para n_trials=100)
   [contraste] o numero ANTIGO -- DSR sobre a lista de 5342 trades OOS: 0.2823
     -> objeto errado duas vezes: trades correlacionados contados como independentes, e o agregado OOS em vez da melhor config in-sample. [Q-1 1 e 3]
   FDR (Benjamini-Hochberg, q=0,10): 0 de 6 configs sobrevivem -- FORA do veredito, nao-informativo em N=6 [F16]

   sensibilidade a n_trials (a dependencia e LOGARITMICA -- [F10]):
    n_trials       sr0      DSR
           6    0.0394   0.3963
          30    0.0628   0.1442
         100    0.0766   0.0625
        1000    0.0985   0.0112
       10000    0.1169   0.0018

-- BLOCO B -- out-of-sample, o PROCESSO. Nulo: E[pnl do walk-forward] <= 0.
   pergunta: 'o procedimento, aplicado cego pra frente, ganha dinheiro?'  papel: DECISAO
   IC95% da media/dia -- bloco (block=5): (-5.4961, 16.9222)   iid: (-4.4958, 16.4639)
   PSR (sem deflacao, SR*=0): 0.8544  (sr/dia = 0.0338)
   Sharpe ANUALIZADO: 0.645   IC95% (bloco): (-0.714, 1.824)
   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, T=910): 1.575
     -> comparacao de poder: T=180 dias daria MDS 3.54; T=1095 daria 1.44. [F6]
   concentracao [F17]: top-5 dias = 0.11 do lucro bruto | folds positivos 3/5 | maior fold = 0.56 do total
     (com 5 folds, 5 positivos de 5 dao p=0,031 e 4/5 dao p=0,19 -- diagnostico, nunca portao)
   ACF do P&L diario, lags 1..10: [0.0854, 0.0217, -0.0219, -0.0438, -0.0431, 0.046, -0.0555, -0.0407, 0.0, -0.0101]
     banda +-1,96/sqrt(T) = +-0.065 -- fora dela = autocorrelacao real [F12]

=> VEREDITO: SEM EVIDENCIA DE EDGE (IC-bloco (-5.4961, 16.9222) inclui 0 ou PSR 0.8544 <= 0,95 ou RC p = 0.2014 > 0,05).
   IC95% do Sharpe anualizado: [-0.714 ; 1.824].
   O teste NAO exclui edges de Sharpe ate 1.824 -- MDS = 1.575. Ausencia de evidencia nao e evidencia de ausencia. [F7]

[varredura] k x sd_min — 96 configs
  [1/96] (50, 22, 1.0, 0.0) -> 9696 trades
  [2/96] (50, 22, 1.0, 0.01) -> 9403 trades
  [3/96] (50, 22, 1.0, 0.02) -> 7926 trades
  [4/96] (50, 22, 1.0, 0.04) -> 3316 trades
  [5/96] (50, 22, 2.0, 0.0) -> 6575 trades
  [6/96] (50, 22, 2.0, 0.01) -> 6390 trades
  [7/96] (50, 22, 2.0, 0.02) -> 5404 trades
  [8/96] (50, 22, 2.0, 0.04) -> 2376 trades
  [9/96] (50, 22, 3.0, 0.0) -> 4905 trades
  [10/96] (50, 22, 3.0, 0.01) -> 4770 trades
  [11/96] (50, 22, 3.0, 0.02) -> 4078 trades
  [12/96] (50, 22, 3.0, 0.04) -> 1828 trades
  [13/96] (50, 22, 4.0, 0.0) -> 3994 trades
  [14/96] (50, 22, 4.0, 0.01) -> 3893 trades
  [15/96] (50, 22, 4.0, 0.02) -> 3355 trades
  [16/96] (50, 22, 4.0, 0.04) -> 1537 trades
  [17/96] (50, 25, 1.0, 0.0) -> 9012 trades
  [18/96] (50, 25, 1.0, 0.01) -> 8753 trades
  [19/96] (50, 25, 1.0, 0.02) -> 7409 trades
  [20/96] (50, 25, 1.0, 0.04) -> 3182 trades
  [21/96] (50, 25, 2.0, 0.0) -> 6119 trades
  [22/96] (50, 25, 2.0, 0.01) -> 5958 trades
  [23/96] (50, 25, 2.0, 0.02) -> 5067 trades
  [24/96] (50, 25, 2.0, 0.04) -> 2291 trades
  [25/96] (50, 25, 3.0, 0.0) -> 4614 trades
  [26/96] (50, 25, 3.0, 0.01) -> 4492 trades
  [27/96] (50, 25, 3.0, 0.02) -> 3848 trades
  [28/96] (50, 25, 3.0, 0.04) -> 1761 trades
  [29/96] (50, 25, 4.0, 0.0) -> 3787 trades
  [30/96] (50, 25, 4.0, 0.01) -> 3693 trades
  [31/96] (50, 25, 4.0, 0.02) -> 3178 trades
  [32/96] (50, 25, 4.0, 0.04) -> 1491 trades
  [33/96] (55, 22, 1.0, 0.0) -> 8550 trades
  [34/96] (55, 22, 1.0, 0.01) -> 8286 trades
  [35/96] (55, 22, 1.0, 0.02) -> 7027 trades
  [36/96] (55, 22, 1.0, 0.04) -> 2960 trades
  [37/96] (55, 22, 2.0, 0.0) -> 5938 trades
  [38/96] (55, 22, 2.0, 0.01) -> 5759 trades
  [39/96] (55, 22, 2.0, 0.02) -> 4886 trades
  [40/96] (55, 22, 2.0, 0.04) -> 2131 trades
  [41/96] (55, 22, 3.0, 0.0) -> 4534 trades
  [42/96] (55, 22, 3.0, 0.01) -> 4398 trades
  [43/96] (55, 22, 3.0, 0.02) -> 3763 trades
  [44/96] (55, 22, 3.0, 0.04) -> 1666 trades
  [45/96] (55, 22, 4.0, 0.0) -> 3738 trades
  [46/96] (55, 22, 4.0, 0.01) -> 3638 trades
  [47/96] (55, 22, 4.0, 0.02) -> 3143 trades
  [48/96] (55, 22, 4.0, 0.04) -> 1399 trades
  [49/96] (55, 25, 1.0, 0.0) -> 7776 trades
  [50/96] (55, 25, 1.0, 0.01) -> 7547 trades
  [51/96] (55, 25, 1.0, 0.02) -> 6431 trades
  [52/96] (55, 25, 1.0, 0.04) -> 2797 trades
  [53/96] (55, 25, 2.0, 0.0) -> 5391 trades
  [54/96] (55, 25, 2.0, 0.01) -> 5239 trades
  [55/96] (55, 25, 2.0, 0.02) -> 4476 trades
  [56/96] (55, 25, 2.0, 0.04) -> 2024 trades
  [57/96] (55, 25, 3.0, 0.0) -> 4141 trades
  [58/96] (55, 25, 3.0, 0.01) -> 4020 trades
  [59/96] (55, 25, 3.0, 0.02) -> 3451 trades
  [60/96] (55, 25, 3.0, 0.04) -> 1576 trades
  [61/96] (55, 25, 4.0, 0.0) -> 3446 trades
  [62/96] (55, 25, 4.0, 0.01) -> 3356 trades
  [63/96] (55, 25, 4.0, 0.02) -> 2896 trades
  [64/96] (55, 25, 4.0, 0.04) -> 1330 trades
  [65/96] (65, 22, 1.0, 0.0) -> 5631 trades
  [66/96] (65, 22, 1.0, 0.01) -> 5472 trades
  [67/96] (65, 22, 1.0, 0.02) -> 4765 trades
  [68/96] (65, 22, 1.0, 0.04) -> 2190 trades
  [69/96] (65, 22, 2.0, 0.0) -> 4110 trades
  [70/96] (65, 22, 2.0, 0.01) -> 3995 trades
  [71/96] (65, 22, 2.0, 0.02) -> 3477 trades
  [72/96] (65, 22, 2.0, 0.04) -> 1623 trades
  [73/96] (65, 22, 3.0, 0.0) -> 3291 trades
  [74/96] (65, 22, 3.0, 0.01) -> 3192 trades
  [75/96] (65, 22, 3.0, 0.02) -> 2787 trades
  [76/96] (65, 22, 3.0, 0.04) -> 1292 trades
  [77/96] (65, 22, 4.0, 0.0) -> 2822 trades
  [78/96] (65, 22, 4.0, 0.01) -> 2742 trades
  [79/96] (65, 22, 4.0, 0.02) -> 2391 trades
  [80/96] (65, 22, 4.0, 0.04) -> 1113 trades
  [81/96] (65, 25, 1.0, 0.0) -> 5611 trades
  [82/96] (65, 25, 1.0, 0.01) -> 5452 trades
  [83/96] (65, 25, 1.0, 0.02) -> 4745 trades
  [84/96] (65, 25, 1.0, 0.04) -> 2171 trades
  [85/96] (65, 25, 2.0, 0.0) -> 4099 trades
  [86/96] (65, 25, 2.0, 0.01) -> 3984 trades
  [87/96] (65, 25, 2.0, 0.02) -> 3466 trades
  [88/96] (65, 25, 2.0, 0.04) -> 1613 trades
  [89/96] (65, 25, 3.0, 0.0) -> 3280 trades
  [90/96] (65, 25, 3.0, 0.01) -> 3181 trades
  [91/96] (65, 25, 3.0, 0.02) -> 2776 trades
  [92/96] (65, 25, 3.0, 0.04) -> 1282 trades
  [93/96] (65, 25, 4.0, 0.0) -> 2816 trades
  [94/96] (65, 25, 4.0, 0.01) -> 2736 trades
  [95/96] (65, 25, 4.0, 0.02) -> 2385 trades
  [96/96] (65, 25, 4.0, 0.04) -> 1107 trades

=== WALK-FORWARD: C trailing kxATR + piso sd | 1h 1095d | 10x | 96 configs x 5 folds ===
PADRAO (travado): criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga: ATIVA
n_trials = 550 (PISO CONTADO, nao estimativa)
calibracao [Q-7]: o controle nulo rejeitou 8/200 paineis sem sinal (taxa 0.04) -> CALIBRADO
   banda de aceitacao CALCULADA (binomial exata, alfa=0,05, 95%): [4 ; 16] rejeicoes = [0.02 ; 0.08] | IC da taxa medida: (0.01742, 0.07729)

 fold   config (conv/adx)   trades    pnl OOS
    1  (65, 25, 4.0, 0.0)      489  R$  +1172
    2  (65, 25, 4.0, 0.0)      506  R$  +1303
    3  (65, 22, 1.0, 0.04)      468  R$  -1006
    4  (55, 22, 4.0, 0.0)      620  R$  +3512
    5  (50, 22, 4.0, 0.0)      697  R$  -1554

OOS agregado: 2780 trades | win 47.6% | PnL R$+3426
  serie diaria da JANELA OOS: 910 dias (702 com P&L nao-nulo) -- o 1o dos 6 segmentos e treino puro e nao entra

-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.
   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO
   White's Reality Check (N=96 configs, 2000 bootstraps de bloco): p = 0.4148
   Hansen SPA (estudentizado):                                     p = 0.5037
   p da melhor config SOZINHA (sem multiplicidade):                p = 0.2329
     -> o grid custou 0.182 de multiplicidade. [F12]
   DSR da melhor config in-sample (65, 22, 4.0, 0.04) sobre a SERIE DIARIA (1091 dias): DSR = 0.0065
     (sr=0.0203 vs sr0_esperado=0.0933 para n_trials=550)
   [contraste] o numero ANTIGO -- DSR sobre a lista de 2780 trades OOS: 0.02
     -> objeto errado duas vezes: trades correlacionados contados como independentes, e o agregado OOS em vez da melhor config in-sample. [Q-1 1 e 3]
   FDR (Benjamini-Hochberg, q=0,10): 0 de 96 configs sobrevivem -- FORA do veredito, nao-informativo em N=96 [F16]

   sensibilidade a n_trials (a dependencia e LOGARITMICA -- [F10]):
    n_trials       sr0      DSR
           6    0.0394    0.258
          30    0.0628   0.0741
         100    0.0766   0.0276
        1000    0.0985   0.0039
       10000    0.1169   0.0005

-- BLOCO B -- out-of-sample, o PROCESSO. Nulo: E[pnl do walk-forward] <= 0.
   pergunta: 'o procedimento, aplicado cego pra frente, ganha dinheiro?'  papel: DECISAO
   IC95% da media/dia -- bloco (block=5): (-8.1029, 16.4889)   iid: (-7.5508, 15.6472)
   PSR (sem deflacao, SR*=0): 0.748  (sr/dia = 0.0216)
   Sharpe ANUALIZADO: 0.412   IC95% (bloco): (-1.016, 1.649)
   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, T=910): 1.575
     -> comparacao de poder: T=180 dias daria MDS 3.54; T=1095 daria 1.44. [F6]
   concentracao [F17]: top-5 dias = 0.152 do lucro bruto | folds positivos 3/5 | maior fold = 1.03 do total
     (com 5 folds, 5 positivos de 5 dao p=0,031 e 4/5 dao p=0,19 -- diagnostico, nunca portao)
   ACF do P&L diario, lags 1..10: [0.0742, 0.0381, 0.065, 0.0117, -0.0538, -0.0338, -0.0086, -0.0093, -0.0276, 0.0283]
     banda +-1,96/sqrt(T) = +-0.065 -- fora dela = autocorrelacao real [F12]

=> VEREDITO: SEM EVIDENCIA DE EDGE (IC-bloco (-8.1029, 16.4889) inclui 0 ou PSR 0.748 <= 0,95 ou RC p = 0.4148 > 0,05).
   IC95% do Sharpe anualizado: [-1.016 ; 1.649].
   O teste NAO exclui edges de Sharpe ate 1.649 -- MDS = 1.575. Ausencia de evidencia nao e evidencia de ausencia. [F7]

=== fim em 94.9 min ===
```
