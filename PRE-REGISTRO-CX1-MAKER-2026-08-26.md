# [CX-1] Pré-registro — o maker que se PAGA, com o fill junto

> Escrito em **2026-08-26, 01:0x**, com a rodada já em `[6/30]` — os seis backtests do
> **baseline taker** tinham saído (6868 / 6452 / 6210 / 5693 / 4384 / 4361, idênticos aos do
> `[Q-15]`, o que confirma que a branch reproduz). **Nenhum nível maker e nenhum walk-forward
> tinham rodado.** O prognóstico abaixo é anterior a todo veredito desta rodada.

## 1. A pergunta

O `[Q-15]` mediu que a taxa decide o veredito: a 0,05%/lado a estratégia sai `SEM EVIDÊNCIA`,
a 0% sai `edge SOBREVIVE`. Mas a linha `maker 0,02%` dele **só trocou o número da taxa** — o
fill continuou no open, 100% das vezes. Ordem limite não funciona assim.

**Pergunta:** quando o desconto de maker vem acompanhado do fill que ele custa, o que sobra?

## 2. O modelo de execução

Post-only: limite a `maker_off` do open, **do nosso lado** (abaixo no long, acima no short).
Enche só se o preço vier até ele dentro do candle de execução; senão **o sinal é perdido** —
cancela, não vira taker. Sem `slip`: quem põe o preço não paga travessia de spread. O custo do
maker não é slippage, é o trade que não aconteceu.

`maker_off = 0` entra na grade **como teto declarado, não como execução possível**: com o
limite no próprio open, `low <= lim` é verdade por definição de OHLC, então o fill é 100% por
construção da barra. É a hipótese que o `[Q-15]` embutiu sem declarar, agora explícita.

**Grade:** taker 0,05% (baseline) · maker 0,02% com off ∈ {0 (teto), 0,05%, 0,10%, 0,20%}.
Mesma janela, mesma grade de 6 configs, mesma política (`tendencia | lev conviccao | trailing 2%`).

## 3. Viés metodológico declarado

`n_trials = 1210`, o mesmo do `[Q-15]`, **para os números serem comparáveis lado a lado**. A
grade cresceu de 18 para 30 rodadas, então 1210 subconta a multiplicidade desta rodada. O
efeito é no DSR, que é diagnóstico e não portão (§ *Critério de aceite* do `README`); o
veredito sai de IC-bloco, PSR e Reality Check, que não dependem de `n_trials`. Fica dito aqui
em vez de descoberto depois.

Segundo viés, mais sutil: **o denominador do fill se move.** Um sinal que não enche deixa o
motor livre para entrar no sinal seguinte, então níveis com concessão maior VÊEM mais sinais.
"Fill 68%" não é "perdi 32% dos trades do baseline" — é "de tudo que tentei, 68% virou trade".

## 4. Prognóstico (antes dos números)

1. **O teto (off 0) reproduz a linha maker do `[Q-15]`**: Sharpe ~1,26, PSR ~0,988, RC p ~0,07,
   veredito `SEM EVIDÊNCIA` por um fio.
2. **A concessão de 0,05% sai MELHOR que o taker, e talvez melhor que o teto.** No teste de
   fumaça em BTC isolado ela deu PnL +445 contra +223 do taker, com 91,2% de fill: o preço
   melhor na entrada mais que pagou os 9% de sinal perdido. Espero que isso se sustente no
   agregado.
3. **A concessão de 0,20% piora** — no BTC caiu para +290 com 68,5% de fill. A curva tem topo
   no meio, não na ponta.
4. **Nenhum nível cruza para `edge SOBREVIVE`.** Este é o prognóstico que mais me interessa
   errar. O MDS é 1,574: para o IC-bloco sair de zero é preciso Sharpe anualizado perto disso,
   e o `[Q-15]` só chegou lá com taxa ZERO, que não existe. Maker realista deve parar entre
   1,2 e 1,4 — melhor que hoje, ainda sem evidência.

**Se o 4 errar** — se algum nível com fill < 100% sair `edge SOBREVIVE` — isso NÃO fecha o
assunto: vira candidato a re-medição fora desta janela, porque um veredito positivo que aparece
depois de varrer 5 níveis é exatamente o que o Reality Check existe para descontar, e a
concentração por fold (`[F17]`) precisa ser lida antes de qualquer comemoração.

## 5. O que este card NÃO faz

Não muda o default: `entrada="taker"` continua sendo o caminho da plataforma, e o portão de
regressão provou que a mudança não move nenhum número no caminho default (4 moedas, contagem e
P&L idênticos ao `origin/main`). Ligar maker em produção depende de uma coisa que este backtest
**não** mede: se a corretora de fato trata a ordem como maker, e o que acontece com o sinal
perdido no vivo.
