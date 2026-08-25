# Q-12 — as quatro políticas na configuração de PRODUÇÃO, saída literal (2026-08-25)

```bash
python -m pesquisa.validacao politicas-prod
```

Mesma régua, mesmas janelas, mesmos painéis das rodadas de 24/08. Único fator alterado em
relação ao `POLITICAS_M4`: `lev_modo="conviccao"` (2x-20x + cap geométrico do `P1-11`), que é o
que a produção executa. `n_trials = 820` (piso contado cumulativo).
Leitura: `INVESTIGACAO-MOTOR-2026-08-24.md` §10.

```

[Q-12] 4 politicas x 6 configs = 24 rodadas, lev por conviccao
  [1/24] A stop+flip de regime [prod] (50, 22) -> 3391 trades
  [2/24] A stop+flip de regime [prod] (50, 25) -> 3201 trades
  [3/24] A stop+flip de regime [prod] (55, 22) -> 3151 trades
  [4/24] A stop+flip de regime [prod] (55, 25) -> 2894 trades
  [5/24] A stop+flip de regime [prod] (65, 22) -> 2327 trades
  [6/24] A stop+flip de regime [prod] (65, 25) -> 2325 trades
  [7/24] B auto-saida [prod] (50, 22) -> 7762 trades
  [8/24] B auto-saida [prod] (50, 25) -> 7267 trades
  [9/24] B auto-saida [prod] (55, 22) -> 7068 trades
  [10/24] B auto-saida [prod] (55, 25) -> 6471 trades
  [11/24] B auto-saida [prod] (65, 22) -> 4951 trades
  [12/24] B auto-saida [prod] (65, 25) -> 4938 trades
  [13/24] C trailing 2% fixo [prod] (50, 22) -> 6873 trades
  [14/24] C trailing 2% fixo [prod] (50, 25) -> 6458 trades
  [15/24] C trailing 2% fixo [prod] (55, 22) -> 6211 trades
  [16/24] C trailing 2% fixo [prod] (55, 25) -> 5694 trades
  [17/24] C trailing 2% fixo [prod] (65, 22) -> 4388 trades
  [18/24] C trailing 2% fixo [prod] (65, 25) -> 4365 trades
  [19/24] C trailing 3xATR [prod] (50, 22) -> 4771 trades
  [20/24] C trailing 3xATR [prod] (50, 25) -> 4488 trades
  [21/24] C trailing 3xATR [prod] (55, 22) -> 4381 trades
  [22/24] C trailing 3xATR [prod] (55, 25) -> 4004 trades
  [23/24] C trailing 3xATR [prod] (65, 22) -> 3204 trades
  [24/24] C trailing 3xATR [prod] (65, 25) -> 3195 trades

==============================================================================
POLITICA: A stop+flip de regime [prod]   {'saida': 'regime', 'lev_modo': 'conviccao'}
==============================================================================

=== WALK-FORWARD: tendencia | 1h 1095d | lev conviccao | saida: A stop+flip de regime [prod] | 6 configs x 5 folds ===
PADRAO (travado): criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga: ATIVA
n_trials = 820 (PISO CONTADO, nao estimativa)
calibracao [Q-7]: o controle nulo rejeitou 6/200 paineis sem sinal (taxa 0.03) -> CALIBRADO
   banda de aceitacao CALCULADA (binomial exata, alfa=0,05, 95%): [4 ; 16] rejeicoes = [0.02 ; 0.08] | IC da taxa medida: (0.01109, 0.06415)

 fold   config (conv/adx)   trades    pnl OOS
    1            (65, 22)      392  R$   +273
    2            (65, 22)      401  R$  +2946
    3            (65, 22)      411  R$   -819
    4            (65, 22)      377  R$   -124
    5            (50, 25)      577  R$  -1374

OOS agregado: 2158 trades | win 28.2% | PnL R$+902
  serie diaria da JANELA OOS: 908 dias (670 com P&L nao-nulo) -- o 1o dos 6 segmentos e treino puro e nao entra

-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.
   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO
   White's Reality Check (N=6 configs, 2000 bootstraps de bloco): p = 0.5507
   Hansen SPA (estudentizado):                                     p = 0.5477
   p da melhor config SOZINHA (sem multiplicidade):                p = 0.4158
     -> o grid custou 0.135 de multiplicidade. [F12]
   DSR da melhor config in-sample (50, 25) sobre a SERIE DIARIA (1089 dias): DSR = 0.0012
     (sr=0.0063 vs sr0_esperado=0.0969 para n_trials=820)
   [contraste] o numero ANTIGO -- DSR sobre a lista de 2158 trades OOS: 0.002
     -> objeto errado duas vezes: trades correlacionados contados como independentes, e o agregado OOS em vez da melhor config in-sample. [Q-1 1 e 3]
   FDR (Benjamini-Hochberg, q=0,10): 0 de 6 configs sobrevivem -- FORA do veredito, nao-informativo em N=6 [F16]

   sensibilidade a n_trials (a dependencia e LOGARITMICA -- [F10]):
    n_trials       sr0      DSR
           6    0.0394    0.133
          30    0.0628   0.0288
         100    0.0767    0.009
        1000    0.0986    0.001
       10000     0.117   0.0001

-- BLOCO B -- out-of-sample, o PROCESSO. Nulo: E[pnl do walk-forward] <= 0.
   pergunta: 'o procedimento, aplicado cego pra frente, ganha dinheiro?'  papel: DECISAO
   IC95% da media/dia -- bloco (block=5): (-6.8558, 9.3546)   iid: (-5.603, 8.2112)
   PSR (sem deflacao, SR*=0): 0.6114  (sr/dia = 0.0092)
   Sharpe ANUALIZADO: 0.176   IC95% (bloco): (-1.446, 1.446)
   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, T=908): 1.576
     -> comparacao de poder: T=180 dias daria MDS 3.54; T=1095 daria 1.44. [F6]
   concentracao [F17]: top-5 dias = 0.195 do lucro bruto | folds positivos 2/5 | maior fold = 3.26 do total
     (com 5 folds, 5 positivos de 5 dao p=0,031 e 4/5 dao p=0,19 -- diagnostico, nunca portao)
   ACF do P&L diario, lags 1..10: [0.1572, 0.1024, 0.0282, -0.039, -0.0033, -0.036, -0.0336, -0.0591, -0.0019, -0.0119]
     banda +-1,96/sqrt(T) = +-0.065 -- fora dela = autocorrelacao real [F12]

=> VEREDITO: SEM EVIDENCIA DE EDGE (IC-bloco (-6.8558, 9.3546) inclui 0 ou PSR 0.6114 <= 0,95 ou RC p = 0.5507 > 0,05).
   IC95% do Sharpe anualizado: [-1.446 ; 1.446].
   O teste NAO exclui edges de Sharpe ate 1.446 -- MDS = 1.576. Ausencia de evidencia nao e evidencia de ausencia. [F7]

==============================================================================
POLITICA: B auto-saida [prod]   {'saida': 'auto', 'lev_modo': 'conviccao'}
==============================================================================

=== WALK-FORWARD: tendencia | 1h 1095d | lev conviccao | saida: B auto-saida [prod] | 6 configs x 5 folds ===
PADRAO (travado): criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga: ATIVA
n_trials = 820 (PISO CONTADO, nao estimativa)
calibracao [Q-7]: o controle nulo rejeitou 4/200 paineis sem sinal (taxa 0.02) -> CALIBRADO
   banda de aceitacao CALCULADA (binomial exata, alfa=0,05, 95%): [4 ; 16] rejeicoes = [0.02 ; 0.08] | IC da taxa medida: (0.00548, 0.05041)

 fold   config (conv/adx)   trades    pnl OOS
    1            (50, 22)     1355  R$   -712
    2            (55, 25)     1143  R$  +1334
    3            (55, 25)     1145  R$  -1722
    4            (55, 22)     1162  R$   -603
    5            (50, 25)     1120  R$   -750

OOS agregado: 5925 trades | win 61.4% | PnL R$-2454
  serie diaria da JANELA OOS: 909 dias (865 com P&L nao-nulo) -- o 1o dos 6 segmentos e treino puro e nao entra

-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.
   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO
   White's Reality Check (N=6 configs, 2000 bootstraps de bloco): p = 0.7891
   Hansen SPA (estudentizado):                                     p = 0.2579
   p da melhor config SOZINHA (sem multiplicidade):                p = 0.7416
     -> o grid custou 0.047 de multiplicidade. [F12]
   DSR da melhor config in-sample (50, 25) sobre a SERIE DIARIA (1091 dias): DSR = 0.0001
     (sr=-0.0203 vs sr0_esperado=0.0968 para n_trials=820)
   [contraste] o numero ANTIGO -- DSR sobre a lista de 5925 trades OOS: 0.0
     -> objeto errado duas vezes: trades correlacionados contados como independentes, e o agregado OOS em vez da melhor config in-sample. [Q-1 1 e 3]
   FDR (Benjamini-Hochberg, q=0,10): 0 de 6 configs sobrevivem -- FORA do veredito, nao-informativo em N=6 [F16]

   sensibilidade a n_trials (a dependencia e LOGARITMICA -- [F10]):
    n_trials       sr0      DSR
           6    0.0394   0.0275
          30    0.0628   0.0038
         100    0.0766   0.0009
        1000    0.0985   0.0001
       10000    0.1169      0.0

-- BLOCO B -- out-of-sample, o PROCESSO. Nulo: E[pnl do walk-forward] <= 0.
   pergunta: 'o procedimento, aplicado cego pra frente, ganha dinheiro?'  papel: DECISAO
   IC95% da media/dia -- bloco (block=5): (-10.8964, 5.6696)   iid: (-10.92, 5.3324)
   PSR (sem deflacao, SR*=0): 0.2655  (sr/dia = -0.0213)
   Sharpe ANUALIZADO: -0.408   IC95% (bloco): (-1.894, 0.786)
   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, T=909): 1.576
     -> comparacao de poder: T=180 dias daria MDS 3.54; T=1095 daria 1.44. [F6]
   concentracao [F17]: top-5 dias = 0.16 do lucro bruto | folds positivos 1/5 | maior fold = 0.7 do total
     (com 5 folds, 5 positivos de 5 dao p=0,031 e 4/5 dao p=0,19 -- diagnostico, nunca portao)
   ACF do P&L diario, lags 1..10: [0.0283, 0.0076, -0.0213, -0.0124, -0.0458, -0.0018, -0.0235, -0.0303, -0.0193, -0.0503]
     banda +-1,96/sqrt(T) = +-0.065 -- fora dela = autocorrelacao real [F12]

=> VEREDITO: SEM EVIDENCIA DE EDGE (IC-bloco (-10.8964, 5.6696) inclui 0 ou PSR 0.2655 <= 0,95 ou RC p = 0.7891 > 0,05).
   IC95% do Sharpe anualizado: [-1.894 ; 0.786].
   O teste NAO exclui edges de Sharpe ate 0.786 -- MDS = 1.576. Ausencia de evidencia nao e evidencia de ausencia. [F7]

==============================================================================
POLITICA: C trailing 2% fixo [prod]   {'saida': 'trailing', 'trailing_dist': 0.02, 'lev_modo': 'conviccao'}
==============================================================================

=== WALK-FORWARD: tendencia | 1h 1095d | lev conviccao | saida: C trailing 2% fixo [prod] | 6 configs x 5 folds ===
PADRAO (travado): criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga: ATIVA
n_trials = 820 (PISO CONTADO, nao estimativa)
calibracao [Q-7]: o controle nulo rejeitou 8/200 paineis sem sinal (taxa 0.04) -> CALIBRADO
   banda de aceitacao CALCULADA (binomial exata, alfa=0,05, 95%): [4 ; 16] rejeicoes = [0.02 ; 0.08] | IC da taxa medida: (0.01742, 0.07729)

 fold   config (conv/adx)   trades    pnl OOS
    1            (50, 22)     1247  R$  +1491
    2            (55, 22)     1160  R$  +2158
    3            (55, 22)     1120  R$  -1239
    4            (50, 25)     1020  R$  +2134
    5            (50, 25)      887  R$   +742

OOS agregado: 5434 trades | win 61.6% | PnL R$+5285
  serie diaria da JANELA OOS: 910 dias (861 com P&L nao-nulo) -- o 1o dos 6 segmentos e treino puro e nao entra

-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.
   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO
   White's Reality Check (N=6 configs, 2000 bootstraps de bloco): p = 0.1404
   Hansen SPA (estudentizado):                                     p = 0.1339
   p da melhor config SOZINHA (sem multiplicidade):                p = 0.1074
     -> o grid custou 0.033 de multiplicidade. [F12]
   DSR da melhor config in-sample (50, 25) sobre a SERIE DIARIA (1091 dias): DSR = 0.0253
     (sr=0.0419 vs sr0_esperado=0.0968 para n_trials=820)
   [contraste] o numero ANTIGO -- DSR sobre a lista de 5434 trades OOS: 0.427
     -> objeto errado duas vezes: trades correlacionados contados como independentes, e o agregado OOS em vez da melhor config in-sample. [Q-1 1 e 3]
   FDR (Benjamini-Hochberg, q=0,10): 0 de 6 configs sobrevivem -- FORA do veredito, nao-informativo em N=6 [F16]

   sensibilidade a n_trials (a dependencia e LOGARITMICA -- [F10]):
    n_trials       sr0      DSR
           6    0.0394   0.5358
          30    0.0628   0.2287
         100    0.0766   0.1083
        1000    0.0985   0.0219
       10000    0.1169   0.0038

-- BLOCO B -- out-of-sample, o PROCESSO. Nulo: E[pnl do walk-forward] <= 0.
   pergunta: 'o procedimento, aplicado cego pra frente, ganha dinheiro?'  papel: DECISAO
   IC95% da media/dia -- bloco (block=5): (-1.7808, 13.8669)   iid: (-1.1824, 13.3015)
   PSR (sem deflacao, SR*=0): 0.954  (sr/dia = 0.0511)
   Sharpe ANUALIZADO: 0.976   IC95% (bloco): (-0.353, 2.074)
   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, T=910): 1.575
     -> comparacao de poder: T=180 dias daria MDS 3.54; T=1095 daria 1.44. [F6]
   concentracao [F17]: top-5 dias = 0.151 do lucro bruto | folds positivos 4/5 | maior fold = 0.41 do total
     (com 5 folds, 5 positivos de 5 dao p=0,031 e 4/5 dao p=0,19 -- diagnostico, nunca portao)
   ACF do P&L diario, lags 1..10: [0.1133, 0.0313, -0.0087, -0.039, -0.0035, 0.0314, -0.0353, -0.0325, 0.0004, -0.0512]
     banda +-1,96/sqrt(T) = +-0.065 -- fora dela = autocorrelacao real [F12]

=> VEREDITO: SEM EVIDENCIA DE EDGE (IC-bloco (-1.7808, 13.8669) inclui 0 ou PSR 0.954 <= 0,95 ou RC p = 0.1404 > 0,05).
   IC95% do Sharpe anualizado: [-0.353 ; 2.074].
   O teste NAO exclui edges de Sharpe ate 2.074 -- MDS = 1.575. Ausencia de evidencia nao e evidencia de ausencia. [F7]

==============================================================================
POLITICA: C trailing 3xATR [prod]   {'saida': 'trailing', 'trailing_k_atr': 3.0, 'lev_modo': 'conviccao'}
==============================================================================

=== WALK-FORWARD: tendencia | 1h 1095d | lev conviccao | saida: C trailing 3xATR [prod] | 6 configs x 5 folds ===
PADRAO (travado): criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga: ATIVA
n_trials = 820 (PISO CONTADO, nao estimativa)
calibracao [Q-7]: o controle nulo rejeitou 4/200 paineis sem sinal (taxa 0.02) -> CALIBRADO
   banda de aceitacao CALCULADA (binomial exata, alfa=0,05, 95%): [4 ; 16] rejeicoes = [0.02 ; 0.08] | IC da taxa medida: (0.00548, 0.05041)

 fold   config (conv/adx)   trades    pnl OOS
    1            (50, 22)      846  R$   +462
    2            (55, 22)      712  R$  +1533
    3            (50, 22)      799  R$   +240
    4            (50, 22)      765  R$  +2014
    5            (50, 22)      811  R$   +648

OOS agregado: 3933 trades | win 50.2% | PnL R$+4897
  serie diaria da JANELA OOS: 909 dias (841 com P&L nao-nulo) -- o 1o dos 6 segmentos e treino puro e nao entra

-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.
   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO
   White's Reality Check (N=6 configs, 2000 bootstraps de bloco): p = 0.1629
   Hansen SPA (estudentizado):                                     p = 0.1489
   p da melhor config SOZINHA (sem multiplicidade):                p = 0.1129
     -> o grid custou 0.05 de multiplicidade. [F12]
   DSR da melhor config in-sample (50, 22) sobre a SERIE DIARIA (1090 dias): DSR = 0.0261
     (sr=0.0413 vs sr0_esperado=0.0969 para n_trials=820)
   [contraste] o numero ANTIGO -- DSR sobre a lista de 3933 trades OOS: 0.174
     -> objeto errado duas vezes: trades correlacionados contados como independentes, e o agregado OOS em vez da melhor config in-sample. [Q-1 1 e 3]
   FDR (Benjamini-Hochberg, q=0,10): 0 de 6 configs sobrevivem -- FORA do veredito, nao-informativo em N=6 [F16]

   sensibilidade a n_trials (a dependencia e LOGARITMICA -- [F10]):
    n_trials       sr0      DSR
           6    0.0394   0.5268
          30    0.0628   0.2263
         100    0.0766   0.1084
        1000    0.0986   0.0226
       10000    0.1169   0.0041

-- BLOCO B -- out-of-sample, o PROCESSO. Nulo: E[pnl do walk-forward] <= 0.
   pergunta: 'o procedimento, aplicado cego pra frente, ganha dinheiro?'  papel: DECISAO
   IC95% da media/dia -- bloco (block=5): (-3.5636, 14.9298)   iid: (-2.6037, 13.745)
   PSR (sem deflacao, SR*=0): 0.9156  (sr/dia = 0.0432)
   Sharpe ANUALIZADO: 0.825   IC95% (bloco): (-0.634, 2.066)
   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, T=909): 1.576
     -> comparacao de poder: T=180 dias daria MDS 3.54; T=1095 daria 1.44. [F6]
   concentracao [F17]: top-5 dias = 0.159 do lucro bruto | folds positivos 5/5 | maior fold = 0.41 do total
     (com 5 folds, 5 positivos de 5 dao p=0,031 e 4/5 dao p=0,19 -- diagnostico, nunca portao)
   ACF do P&L diario, lags 1..10: [0.1004, 0.0616, 0.0263, -0.0051, -0.0092, -0.0049, -0.0154, -0.0334, 0.0053, -0.012]
     banda +-1,96/sqrt(T) = +-0.065 -- fora dela = autocorrelacao real [F12]

=> VEREDITO: SEM EVIDENCIA DE EDGE (IC-bloco (-3.5636, 14.9298) inclui 0 ou PSR 0.9156 <= 0,95 ou RC p = 0.1629 > 0,05).
   IC95% do Sharpe anualizado: [-0.634 ; 2.066].
   O teste NAO exclui edges de Sharpe ate 2.066 -- MDS = 1.576. Ausencia de evidencia nao e evidencia de ausencia. [F7]

==============================================================================================================
COMPARACAO DE POLITICAS DE SAIDA -- mesma regua, mesmas janelas, mesmos dados [P1-10]
==============================================================================================================
politica                 trades   win%   PnL OOS Sharpe an.          IC95% Sharpe     DSR    MDS  veredito
A stop+flip de regime [prod]   2158   28.2      +902      0.176       (-1.446, 1.446)  0.0012  1.576  SEM_EVIDENCIA
B auto-saida [prod]        5925   61.4     -2454     -0.408       (-1.894, 0.786)  0.0001  1.576  SEM_EVIDENCIA
C trailing 2% fixo [prod]   5434   61.6     +5285      0.976       (-0.353, 2.074)  0.0253  1.575  SEM_EVIDENCIA
C trailing 3xATR [prod]    3933   50.2     +4897      0.825       (-0.634, 2.066)  0.0261  1.576  SEM_EVIDENCIA

motivos de saida por politica (o que de fato fechou os trades):
   A stop+flip de regime [prod] stop: 1085 | regime: 1073
   B auto-saida [prod]      auto-saida: 3639 | stop: 2286
   C trailing 2% fixo [prod] trailing: 3510 | stop: 1924
   C trailing 3xATR [prod]  trailing: 2028 | stop: 1905

O P&L esta na tabela como DIAGNOSTICO. O que decide e o veredito da ultima coluna,
emitido sob o PADRAO travado -- soma bruta de P&L favorece quem mais opera [F3].

=== fim em 8.6 min ===
```
