# Zero-a-zero e alavancagem por convicção — saída literal, 2026-08-24

Duas rodadas, MESMA janela e MESMOS painéis da varredura de geometria.
Leitura e atribuição: `INVESTIGACAO-MOTOR-2026-08-24.md` §9.

## Rodada 1 — grade do zero-a-zero (24 configs, `n_trials=670`, 12,0 min)

```bash
python -m pesquisa.validacao zeroazero
```

```

[zero-a-zero] be_em_R x entrada — 24 configs, lev por conviccao
  [1/24] (50, 22, None) -> 6873 trades
  [2/24] (50, 22, 0.5) -> 7526 trades
  [3/24] (50, 22, 1.0) -> 6948 trades
  [4/24] (50, 22, 1.5) -> 6886 trades
  [5/24] (50, 25, None) -> 6458 trades
  [6/24] (50, 25, 0.5) -> 7040 trades
  [7/24] (50, 25, 1.0) -> 6520 trades
  [8/24] (50, 25, 1.5) -> 6470 trades
  [9/24] (55, 22, None) -> 6211 trades
  [10/24] (55, 22, 0.5) -> 6761 trades
  [11/24] (55, 22, 1.0) -> 6273 trades
  [12/24] (55, 22, 1.5) -> 6217 trades
  [13/24] (55, 25, None) -> 5694 trades
  [14/24] (55, 25, 0.5) -> 6175 trades
  [15/24] (55, 25, 1.0) -> 5743 trades
  [16/24] (55, 25, 1.5) -> 5699 trades
  [17/24] (65, 22, None) -> 4388 trades
  [18/24] (65, 22, 0.5) -> 4681 trades
  [19/24] (65, 22, 1.0) -> 4426 trades
  [20/24] (65, 22, 1.5) -> 4392 trades
  [21/24] (65, 25, None) -> 4365 trades
  [22/24] (65, 25, 0.5) -> 4658 trades
  [23/24] (65, 25, 1.0) -> 4403 trades
  [24/24] (65, 25, 1.5) -> 4369 trades

-- DIAGNOSTICO por braco (in-sample, todas as configs de entrada somadas) --
    be_em_R   trades        PnL  zero-a-zero    stop  trailing  liquid
       None    33989     +24045            0   12183     21806       0
        0.5    36841     +21284         5737   11043     20061       0
        1.0    34313     +23518          725   11996     21592       0
        1.5    34033     +24331          138   12115     21780       0

=== WALK-FORWARD: C trailing 2% + zero-a-zero | lev conviccao | 1h 1095d | 24 configs x 5 folds ===
PADRAO (travado): criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga: ATIVA
n_trials = 670 (PISO CONTADO, nao estimativa)
calibracao [Q-7]: o controle nulo rejeitou 8/200 paineis sem sinal (taxa 0.04) -> CALIBRADO
   banda de aceitacao CALCULADA (binomial exata, alfa=0,05, 95%): [4 ; 16] rejeicoes = [0.02 ; 0.08] | IC da taxa medida: (0.01742, 0.07729)

 fold   config (conv/adx)   trades    pnl OOS
    1      (50, 22, None)     1247  R$  +1491
    2       (55, 22, 1.5)     1159  R$  +2183
    3       (55, 22, 1.5)     1120  R$  -1233
    4       (50, 25, 1.5)     1023  R$  +2158
    5       (50, 25, 1.5)      893  R$   +741

OOS agregado: 5442 trades | win 61.5% | PnL R$+5338
  serie diaria da JANELA OOS: 910 dias (862 com P&L nao-nulo) -- o 1o dos 6 segmentos e treino puro e nao entra

-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.
   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO
   White's Reality Check (N=24 configs, 2000 bootstraps de bloco): p = 0.1434
   Hansen SPA (estudentizado):                                     p = 0.1369
   p da melhor config SOZINHA (sem multiplicidade):                p = 0.1054
     -> o grid custou 0.038 de multiplicidade. [F12]
   DSR da melhor config in-sample (50, 25, 1.5) sobre a SERIE DIARIA (1091 dias): DSR = 0.0302
     (sr=0.0423 vs sr0_esperado=0.095 para n_trials=670)
   [contraste] o numero ANTIGO -- DSR sobre a lista de 5442 trades OOS: 0.4624
     -> objeto errado duas vezes: trades correlacionados contados como independentes, e o agregado OOS em vez da melhor config in-sample. [Q-1 1 e 3]
   FDR (Benjamini-Hochberg, q=0,10): 0 de 24 configs sobrevivem -- FORA do veredito, nao-informativo em N=24 [F16]

   sensibilidade a n_trials (a dependencia e LOGARITMICA -- [F10]):
    n_trials       sr0      DSR
           6    0.0394   0.5419
          30    0.0628   0.2332
         100    0.0766    0.111
        1000    0.0985   0.0226
       10000    0.1169    0.004

-- BLOCO B -- out-of-sample, o PROCESSO. Nulo: E[pnl do walk-forward] <= 0.
   pergunta: 'o procedimento, aplicado cego pra frente, ganha dinheiro?'  papel: DECISAO
   IC95% da media/dia -- bloco (block=5): (-1.7716, 13.9373)   iid: (-1.0966, 13.3557)
   PSR (sem deflacao, SR*=0): 0.9557  (sr/dia = 0.0516)
   Sharpe ANUALIZADO: 0.985   IC95% (bloco): (-0.345, 2.081)
   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, T=910): 1.575
     -> comparacao de poder: T=180 dias daria MDS 3.54; T=1095 daria 1.44. [F6]
   concentracao [F17]: top-5 dias = 0.15 do lucro bruto | folds positivos 4/5 | maior fold = 0.41 do total
     (com 5 folds, 5 positivos de 5 dao p=0,031 e 4/5 dao p=0,19 -- diagnostico, nunca portao)
   ACF do P&L diario, lags 1..10: [0.113, 0.0316, -0.0088, -0.0391, -0.0031, 0.0316, -0.035, -0.0326, 0.0007, -0.0508]
     banda +-1,96/sqrt(T) = +-0.065 -- fora dela = autocorrelacao real [F12]

=> VEREDITO: SEM EVIDENCIA DE EDGE (IC-bloco (-1.7716, 13.9373) inclui 0 ou PSR 0.9557 <= 0,95 ou RC p = 0.1434 > 0,05).
   IC95% do Sharpe anualizado: [-0.345 ; 2.081].
   O teste NAO exclui edges de Sharpe ate 2.081 -- MDS = 1.575. Ausencia de evidencia nao e evidencia de ausencia. [F7]

=== fim em 12.0 min ===
```

## Rodada 2 — CONTRASTE de atribuição: só o braço `be_em_R=None` (6 configs, `n_trials=700`, 9,4 min)

Mesmas 6 configs de entrada do baseline, mesma política de saída, mesma janela.
O ÚNICO fator que muda em relação ao baseline da §7 é `lev_modo`.

```

[zero-a-zero] be_em_R x entrada — 6 configs, lev por conviccao
  [1/6] (50, 22, None) -> 6873 trades
  [2/6] (50, 25, None) -> 6458 trades
  [3/6] (55, 22, None) -> 6211 trades
  [4/6] (55, 25, None) -> 5694 trades
  [5/6] (65, 22, None) -> 4388 trades
  [6/6] (65, 25, None) -> 4365 trades

-- DIAGNOSTICO por braco (in-sample, todas as configs de entrada somadas) --
    be_em_R   trades        PnL  zero-a-zero    stop  trailing  liquid
       None    33989     +24045            0   12183     21806       0

=== WALK-FORWARD: C trailing 2% + zero-a-zero | lev conviccao | 1h 1095d | 6 configs x 5 folds ===
PADRAO (travado): criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga: ATIVA
n_trials = 700 (PISO CONTADO, nao estimativa)
calibracao [Q-7]: o controle nulo rejeitou 8/200 paineis sem sinal (taxa 0.04) -> CALIBRADO
   banda de aceitacao CALCULADA (binomial exata, alfa=0,05, 95%): [4 ; 16] rejeicoes = [0.02 ; 0.08] | IC da taxa medida: (0.01742, 0.07729)

 fold   config (conv/adx)   trades    pnl OOS
    1      (50, 22, None)     1247  R$  +1491
    2      (55, 22, None)     1160  R$  +2158
    3      (55, 22, None)     1120  R$  -1239
    4      (50, 25, None)     1020  R$  +2134
    5      (50, 25, None)      887  R$   +742

OOS agregado: 5434 trades | win 61.6% | PnL R$+5285
  serie diaria da JANELA OOS: 910 dias (861 com P&L nao-nulo) -- o 1o dos 6 segmentos e treino puro e nao entra

-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.
   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO
   White's Reality Check (N=6 configs, 2000 bootstraps de bloco): p = 0.1404
   Hansen SPA (estudentizado):                                     p = 0.1339
   p da melhor config SOZINHA (sem multiplicidade):                p = 0.1074
     -> o grid custou 0.033 de multiplicidade. [F12]
   DSR da melhor config in-sample (50, 25, None) sobre a SERIE DIARIA (1091 dias): DSR = 0.0284
     (sr=0.0419 vs sr0_esperado=0.0954 para n_trials=700)
   [contraste] o numero ANTIGO -- DSR sobre a lista de 5434 trades OOS: 0.4453
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

=== fim em 9.4 min ===
```
