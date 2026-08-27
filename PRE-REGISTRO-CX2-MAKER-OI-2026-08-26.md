# [CX-2] Pré-registro — maker realista **+** portão de open interest

> Escrito em **2026-08-26**, com os painéis de OI ainda sendo montados (`BTC` era a única moeda
> anexada) e **nenhum backtest desta grade executado**. Merge dos territórios em `e573962`,
> portão de regressão rodado depois dele: 5 moedas idênticas à `origin/main`.

## 1. Por que somar os dois

Dois cards mediram, separadamente, coisas que empurram **o mesmo portão** — o IC-bloco da
média/dia, o único que sobrou reprovado no `[CX-1]`, e por 0,27 num intervalo de 15,5:

- **`[CX-1]`**: execução maker realista leva Sharpe de 0,955 → ~1,25, RC p de 0,141 → 0,049.
  Passa em PSR e Reality Check; falha só no IC-bloco.
- **`[Q-17]`**: o portão de OI corta **40% dos trades perdendo 22% do P&L** (+30,2% de P&L por
  trade) e foi escolhido pelo treino em 5 folds de 5 — com veredito `SEM EVIDÊNCIA`, reprovado
  sobretudo por concentração (`maior fold = 1,0`).

**A hipótese:** taxa menor e menos trade são o mesmo remédio por dois caminhos. Somar não é
óbvio — pode ser **redundante** (os dois cortam o mesmo trade ruim) ou **aditivo** (cortam
trades diferentes). É isso que a rodada decide.

## 2. A grade, fixada agora

- **Walk-forward:** 6 configs `(min_conv, adx_min)` × **3** modos de OI = **18 configs**.
- **Modos:** `off` (nula), `concorda`, `peso`. **`concorda_tend` fica de fora**, e a razão é
  medida: o `[Q-17]` achou contagem idêntica à do `concorda` nas seis comparações, porque o
  motor já exige `adx >= adx_min` para entrar em tendência. Eram 4 modos declarados e 3
  distintos. O `[Q-17]` **não** corrigiu a grade dele no meio do caminho, e agiu certo — a §4
  do pré-registro dele proíbe. Corrigir vale **aqui**, num pré-registro novo, antes dos números.
- **Níveis de execução:** taker 0,05% (baseline re-medido nesta janela) e maker 0,02% com
  concessão de **0,05%, 0,10% e 0,20%**. Os três, e não o melhor do `[CX-1]`: escolher o nível
  depois de ver a curva do card anterior é escolher no dado visto. Rodar os três também testa
  se a **curva plana** do `[CX-1]` sobrevive ao portão de OI.
- **Total:** 4 níveis × 18 configs = **72 backtests**.

## 3. Vieses declarados

- **`n_trials = 1210`**, herdado do `[Q-15]`/`[CX-1]` para os números ficarem comparáveis lado a
  lado. **Subconta** esta grade, que é maior. Afeta o DSR, que é diagnóstico e não portão; os
  três portões do veredito não dependem dele, e a régua imprime a sensibilidade a `n_trials` de
  6 a 10.000 em toda rodada.
- **O denominador do fill se move** (`[CX-1]` §3): sinal não preenchido libera o motor para o
  seguinte, então níveis com concessão maior VÊEM mais sinais.
- **Esta é a terceira rodada sobre a mesma janela de 3 anos.** Reality Check e DSR descontam a
  multiplicidade *dentro* de uma rodada; nenhum dos dois desconta eu ter voltado três vezes ao
  mesmo dado. É o argumento mais forte contra este card, e ele não tem conserto estatístico —
  só re-medição fora da janela.

## 4. Prognóstico (antes dos números)

1. **Não vai ser aditivo.** Os dois mecanismos mordem o mesmo trade marginal. Espero o
   combinado perto do **melhor dos dois isolados**, não da soma: Sharpe ~1,3-1,5, não ~1,9.
2. **Espero que CRUZE em pelo menos um nível** — e digo isto sabendo que é o prognóstico
   arriscado. O `[CX-1]` ficou a 0,27 de largura do IC de sair do zero, e o portão de OI
   aumenta o P&L por trade em 30%. Confiança honesta: pouco acima de meio a meio.
3. **`peso` deve AUMENTAR os trades**, não cortar: o `[Q-17]` mediu `d_oi > 0` em ~76% das
   barras (o OI tem tendência secular de alta, então o filtro é fraco e assimétrico). Com taxa
   de maker, mais trades machuca menos do que machucava no taker — então espero `peso` menos
   ruim aqui do que foi lá.
4. **A curva de concessão segue plana** entre 0,05% e 0,20%, como no `[CX-1]`.

## 5. O que eu vou olhar ANTES de comemorar, se o 2 acertar

**A concentração por fold.** O `[Q-17]` reprovou com `maior fold = 1,0` — o fold 2 era 99,95%
do resultado e os outros quatro somavam R$ 2 em três anos. Se o combinado cruzar carregando
essa herança, **não é edge, é um fold**. O `[CX-1]` estava saudável nesse teste (maior fold
0,36-0,44, 4/5 positivos); se o `[CX-2]` piorar em vez de manter, o portão de OI é a causa e o
cruzamento não vale.

Segundo: **um veredito positivo que aparece na terceira visita à mesma janela é candidato, não
conclusão.** O caminho é re-medir fora dela — janela nova, ou moedas fora das 12.

## 6. O que este card não faz

Não muda default nenhum: `entrada="taker"` e `oi_modo="off"` seguem sendo a plataforma. E o
backtest continua sem medir o que decide se isso é operável: se a corretora trata a ordem como
maker, e o que o vivo faz com o sinal que não encheu.

## 7. Adendo, antes de qualquer número: o `[Q-17]` mediu noutra configuração

Achado ao ler `_trades_oi` para montar esta rodada: o `[Q-17]` chamou o `backtest_ativo` **sem
`lev_modo`**, ou seja com alavancagem **FIXA** — não com a de convicção que a produção roda e
que o `[Q-15]` e o `[CX-1]` usaram. É por isso que o baseline dele é Sharpe 0,620 e o do
`[CX-1]` é 0,955: não são a mesma coisa medida duas vezes, são duas configurações.

**O `[CX-2]` roda em `lev_modo="conviccao"`**, a de produção, porque é a única que deixa esta
rodada comparável com o `[CX-1]` — e porque é a que se opera.

**Consequência que pode invalidar o prognóstico 2:** o efeito do portão de OI medido pelo
`[Q-17]` (+30,2% de P&L por trade) foi medido com lev fixa. Sob dimensionamento por convicção o
efeito pode ser maior, menor ou trocar de sinal, porque o portão e a convicção podem estar
cortando o mesmo trade. **Não estou herdando aquele número: estou re-medindo o portão numa
configuração em que ele nunca rodou.**
