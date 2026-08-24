# VEREDITO-M4 — a política de saída que está viva, medida pela régua corrigida

> **Estado em 2026-08-24: os números chegaram e estão colados.** As quatro políticas rodaram e
> as quatro saíram `SEM_EVIDENCIA DE EDGE`; a §7.2 aponta o Caso 1. A moldura abaixo fica como
> foi escrita para que se possa conferir que ela é anterior aos números.
>
> **Estado deste documento.** A estrutura, as ressalvas e a recomendação condicional são do
> `T-EDGE` (onda 3 do M4). **Os números são da matriz**, que roda o `A×B×C` em primeiro plano —
> cada bloco marcado `<!-- COLAR -->` recebe saída literal. Antes de a colagem existir, este
> documento **não** é um veredito: é a moldura que diz o que os números vão significar quando
> chegarem, escrita antes de eles chegarem *de propósito* (§7).
>
> Marco: **M4**. Cards: `[P1-10]` (`lz5wVY9l`, `toca-risco`) e `[Q-7]` (`W5GPISAV`, ✅ Feito).
> Base: `origin/main` = `851c707`. Commits desta onda: `44dd5b9`, `d313b99`, `234a423`,
> `ddbdf33`, `c08cba3`, `c8b4593`.

---

## 1. A pergunta do marco, e por que ela não estava respondida

O veredito central do projeto — *"tendência sem edge: DSR ≈ 0"*, que está no cabeçalho do
`CLAUDE.md`, no `README.md` e no `autotrader.py:8-13` — foi medido sobre **uma política de saída
que o sistema vivo nunca operou**.

A régua sempre mediu a política **A**: stop de 3×ATR fixado na entrada, ou **flip de regime**
(o scoring inverte e a posição fecha em `closes[i]`). O flip de regime **não existe em lugar
nenhum do caminho vivo**: não está em `simulador.atualizar()`, não está em
`autotrader.auto_executar()`, não está em `signal_engine`. Ele é um artefato do backtest — a
maneira que o motor por-ativo tinha de não deixar posição aberta para sempre.

O que o sistema vivo **de fato** operou, e continua operando:

| | política | quem a liga | backtestada antes desta onda? |
|---|---|---|---|
| **A** | stop fixo · liquidação · **flip de regime** | ninguém — é a do backtest | sim, e é a do veredito atual |
| **B** | stop fixo · liquidação · **auto-saída** | `auto_fechar_saida=1` **e** `trailing_ativo=0` (`autotrader.py:151`) | **não** |
| **C** | **stop que só sobe atrás do preço** · liquidação | `trailing_ativo=1` — **o default de hoje** (`db.py:95`) | **não** |

A política **B** é a que gerou o histórico local, e ela vem com a assinatura que a
`INVESTIGACAO-TRADING-2026-08-19.md` mandou vigiar: 49 saídas `auto-saida` a **+R$3,53** de média
contra 7 `stop` a **−R$18,25** — perda média **5,2×** o ganho médio, com win rate de 87,5%.
Ganha-pouco / perde-grande é exatamente o perfil que a `BASE-CONHECIMENTO-TRADING.md` §2.5 manda
avaliar por Sharpe ajustado a skew e **não** por taxa de acerto.

A política **C** é o default de hoje e nunca teve evidência histórica nenhuma: o
`ITEM1-VALIDACAO-RIGOROSA.md` §8 já registrava isso como débito conhecido — *"o comportamento que
o sistema ao vivo executa hoje não é reproduzível no backtest, e o efeito da feature é
desconhecido"*.

**A pergunta do marco, então:** rodando a régua corrigida sobre as políticas que o sistema
realmente executa, o veredito muda?

Uma quarta linha entra na comparação porque o item 3 do `[P1-10]` a pede, e ela é a mais
acionável das quatro: **C com a distância do trailing em k×ATR**. O `trailing_dist=2%` é fixo em
espaço-preço, portanto cego ao ATR (a *entrada* dimensiona o stop em 3×ATR e a *saída* ignora a
volatilidade do ativo) e cego à alavancagem (2% de preço = 4% de ROE a 2x, **40%** a 20x). Medir C
em k×ATR é o que transforma a comparação em uma decisão de parâmetro, e não só num placar.

---

## 2. As três correções que esta rodada tem e nenhuma anterior teve

Nenhuma delas foi pedida pelo `[P1-10]`. As três apareceram porque o território as continha e
porque as três contaminam o número que o marco ia publicar. **Se os números mudarem em relação à
rodada do `[Q-1]` (`ITEM1-VALIDACAO-RIGOROSA.md` §6), a causa provável é esta seção — e isso é
entrega, não regressão.**

### 2.1 A purga de borda de fold agiu pela primeira vez (`44dd5b9`)

`pesquisa/backtest_plataforma.py` não gravava `ts_saida` — só o instante da entrada. Sem esse
campo a purga do `[Q-1]` **desligava sozinha** e o relatório imprimia `purga: INATIVA`. Ela sempre
esteve *pedida* (`PADRAO["purga"] = True`); o que faltava era o dado para agir.

O que ela corta: o trade que **entra antes da borda do fold e sai depois** carrega P&L determinado
dentro da janela de teste. Ele entrava no treino, e é vazamento, não ruído.

**Direção do viés, e por isso ele não podia ficar:** o vazamento empurra o resultado para **CIMA**
— a favor do "tem edge", contra a conclusão negativa. Num marco cujo produto declarado é um
veredito honesto, o viés que favorece a resposta agradável é o pior lugar possível para economizar
trabalho.

O carimbo é o **fim** do candle de saída (`tss[i] + tf_ms`), não o começo. A purga pergunta quando
o desfecho deixou de ser incerto: saída por `regime`/`tempo` executa literalmente em `closes[i]`,
e saída por `stop`/`liquidacao`/`alvo` dispara em algum ponto **interno** do candle, que o modelo
não observa. Carimbar o começo afirmaria um instante não observado e purgaria **de menos**;
arredondar para o fim purga de mais, isto é, contra o resultado.

<!-- COLAR: a linha `purga: ...` do cabeçalho de cada política. Ela tem de dizer ATIVA nas quatro.
     Se disser INATIVA em alguma, PARE: o `ts_saida` não chegou naquele caminho e o número daquela
     linha carrega o vazamento. -->

```
A stop+flip de regime    purga: ATIVA
B auto-saida             purga: ATIVA
C trailing 2% fixo       purga: ATIVA
C trailing 3xATR         purga: ATIVA
```

### 2.2 O funding passou a ser cobrado pelo tempo certo (`44dd5b9`, direção corrigida em `ddbdf33`)

A duração da barra saía de `TF_MAPA[tf]`, e `tf` é parâmetro com default `"15m"`.
`validacao.gerador_tendencia` passa um `df` de **1h** e não passa `tf`. Resultado: desde o
`[P2-10]`, o funding vinha sendo cobrado sobre **um quarto** do tempo de hold real. A magnitude é
**4×** e não depende do período.

O conserto é de raiz: a duração da barra é **medida no próprio `df`** (`_horas_por_barra`), porque
o `df` sabe o próprio passo — está nos `timestamp` dele. O conserto de sintoma seria acrescentar
`tf=TF` na chamada da `validacao`; ele funciona hoje e quebra de novo, em silêncio, no próximo `df`
com outra granularidade.

**A direção do viés não é universal, e esse é o ponto que o `ddbdf33` levantou.** Cobrar 1/4 do
carry só é *otimista* para um livro que **paga** funding: net-LONG superestima o P&L, net-SHORT o
subestima. A regra a aplicar na leitura é *a direção segue o sinal do carry líquido do período
medido*, e quem reportar tem de declarar o período.

⚠️ **Para os 1.095 dias, esse sinal ainda NÃO foi medido — e a versão anterior desta seção
afirmava que sim.** Ela citava, como saída literal registrada na §6 do
`ITEM1-VALIDACAO-RIGOROSA.md`, um bloco `COM x SEM funding: R$+993 x R$+948 → efeito do carry
R$+45, net-SHORT`. Conferido com `grep -rn "efeito do carry\|net-SHORT\|948" --include=*.md .`:
**esse bloco não existe em lugar nenhum da árvore**. O que a §6 registra daquela rodada é o
`+R$993` **com** funding e, explicitamente, que o contraste não chegou a rodar — *"a sessão foi
cortada por tempo antes de a segunda passada do grid (~13 min) terminar"*.

Corrigido em `c8b4593`, aqui e no docstring de `_horas_por_barra`. Fica registrado porque o erro
tem uma forma perigosa: uma saída literal **inventada** já chega no formato que esta casa usa para
confiar (§7 — *"o que fecha card é a saída literal colada"*), e passa por conferência de quem só
leia a citação. Quando alguém rodar `python -m pesquisa.validacao` (com contraste), a linha
`-> efeito do carry no P&L OOS: ... net-LONG/net-SHORT` é onde o número vai aparecer.

⚠️ **A comparação de políticas roda `com_contraste=False`** (`validacao.comparar_politicas`): o
contraste de funding dobra o tempo de cada política e mede outra coisa, já registrada para a
política A. Então **o efeito do carry sob B e C não está medido nesta rodada** — se ele importar
para a decisão, é card novo.

### 2.3 O MDS passou a ser lido como piso, pela ponta menos conveniente do IC (`d313b99`, `c08cba3`)

O `[Q-7]` mediu o alfa efetivo do Bloco A e ligou a medida ao veredito. Duas consequências entram
no relatório:

* a linha do MDS ganha a marca **`-- e um PISO`** quando o controle nulo classifica sub-rejeição, e
  imprime o MDS recalculado com o **alfa efetivo medido**, não com o nominal de 0,05;
* o portão de poder passa a ler `mds_piso_min` — o piso calculado com o alfa na **ponta menos
  exigente** do IC exato. Ou seja: a guarda só bloqueia quando a imprecisão do próprio diagnóstico
  **não pode** explicar o achado. A guarda simétrica, do lado de cima, faz o mesmo em espelho
  (`ALFA_TETO_PORTAO`, lido pelo limite **inferior** do IC).

A aritmética que o card do `[Q-7]` propôs não sobreviveu à conferência, e o número corrigido está
fixado em `test_mds_vira_PISO_quando_o_teste_sub_rejeita`: com o `mds_sharpe` **deste arquivo**, a
razão entre alfa 0,01 e alfa 0,05 é **1,274**, não ~1,22. Sobre o `1,576` da rodada do `[Q-1]` isso
dá **2,008** — do **outro** lado de `MDS_LIMITE = 2,0`. A folga não cai de 27% para 4%: ela deixa
de existir.

**Isso é motivo para ler a §4 antes de ler qualquer número desta rodada.**

---

### 2.4 O que as três correções de fato moveram, medido em vez de suposto

A abertura desta seção diz que, se os números mudassem em relação ao `[Q-1]`, *"a causa provável
é esta seção"*. Eles mudaram: a política `A` deu **+R$1.127** contra os **+R$993** publicados na §6
do `ITEM1-VALIDACAO-RIGOROSA.md`. **"Provável" não fecha card nesta casa**, e havia uma segunda
causa candidata que ninguém tinha descartado: a janela. A rodada do `[Q-1]` baixou os painéis às
13h23 de 23/08 e esta rodada os baixou às 20h32 do mesmo dia — mesma data no nome do cache,
**última barra diferente**.

O discriminante separa as duas: o código **anterior** ao `44dd5b9` (worktree `t-regua`, `13bb90f`,
purga desligada e funding sobre 1/4 do tempo) rodando sobre **exatamente os painéis desta rodada**,
com `dados.baixar_ohlcv` e `scoring.preparar` interceptados para servir o painel serializado.

```
=== WALK-FORWARD: tendencia | 1h 1095d | 10x | 6 configs x 5 folds ===
PADRAO (travado): criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga: INATIVA -- backtest_plataforma.py:82 nao grava ts_saida (territorio T-EDGE)
n_trials = 100 (PISO CONTADO, nao estimativa)

 fold   config (conv/adx)   trades    pnl OOS
    1            (65, 25)      390  R$   +196
    2            (50, 22)      537  R$  +5817
    3            (55, 22)      528  R$  -1219
    4            (55, 22)      503  R$   +889
    5            (50, 22)      616  R$  -4690

OOS agregado: 2574 trades | win 29.8% | PnL R$+993
  serie diaria da JANELA OOS: 908 dias (721 com P&L nao-nulo) -- o 1o dos 6 segmentos e treino puro e nao entra

-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.
   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO
   White's Reality Check (N=6 configs, 2000 bootstraps de bloco): p = 0.4928
   Hansen SPA (estudentizado):                                     p = 0.4988
   p da melhor config SOZINHA (sem multiplicidade):                p = 0.4033
     -> o grid custou 0.09 de multiplicidade. [F12]
   DSR da melhor config in-sample (50, 22) sobre a SERIE DIARIA (1089 dias): DSR = 0.0095
     (sr=0.007 vs sr0_esperado=0.0767 para n_trials=100)
   [contraste] o numero ANTIGO -- DSR sobre a lista de 2574 trades OOS: 0.0116
     -> objeto errado duas vezes: trades correlacionados contados como independentes, e o agregado OOS em vez da melhor config in-sample. [Q-1 1 e 3]
   FDR (Benjamini-Hochberg, q=0,10): 0 de 6 configs sobrevivem -- FORA do veredito, nao-informativo em N=6 [F16]

   sensibilidade a n_trials (a dependencia e LOGARITMICA -- [F10]):
    n_trials       sr0      DSR
           6    0.0394   0.1377
          30    0.0628   0.0301
         100    0.0767   0.0095
        1000    0.0986    0.001
       10000     0.117   0.0001

-- BLOCO B -- out-of-sample, o PROCESSO. Nulo: E[pnl do walk-forward] <= 0.
   pergunta: 'o procedimento, aplicado cego pra frente, ganha dinheiro?'  papel: DECISAO
   IC95% da media/dia -- bloco (block=5): (-13.1424, 15.8736)   iid: (-11.0114, 14.479)
   PSR (sem deflacao, SR*=0): 0.5697  (sr/dia = 0.0057)
   Sharpe ANUALIZADO: 0.109   IC95% (bloco): (-1.688, 1.343)
   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, T=908): 1.576
     -> comparacao de poder: T=180 dias daria MDS 3.54; T=1095 daria 1.44. [F6]
   concentracao [F17]: top-5 dias = 0.223 do lucro bruto | folds positivos 3/5 | maior fold = 5.86 do total
     (com 5 folds, 5 positivos de 5 dao p=0,031 e 4/5 dao p=0,19 -- diagnostico, nunca portao)
   ACF do P&L diario, lags 1..10: [0.2217, 0.0323, -0.0051, -0.0028, -0.021, -0.0143, -0.0434, -0.0384, 0.021, 0.0251]
     banda +-1,96/sqrt(T) = +-0.065 -- fora dela = autocorrelacao real [F12]

=> VEREDITO: SEM EVIDENCIA DE EDGE (IC-bloco (-13.1424, 15.8736) inclui 0 ou PSR 0.5697 <= 0,95 ou RC p = 0.4928 > 0,05).
   IC95% do Sharpe anualizado: [-1.688 ; 1.343].
   O teste NAO exclui edges de Sharpe ate 1.343 -- MDS = 1.576. Ausencia de evidencia nao e evidencia de ausencia. [F7]

PnL OOS agregado (codigo antigo, paineis novos): R$+993  |  2574 trades
```

**+R$993, 2.574 trades, Sharpe 0,109, DSR 0,0095, MDS 1,576, T=908** — reproduz o número publicado
do `[Q-1]` dígito por dígito. Como `antigo+antigo` e `antigo+novo` dão o mesmo número, **a janela
não contribuiu com nada**, e os R$134 de diferença são **integralmente** das correções desta seção.
A linha `purga: INATIVA -- backtest_plataforma.py:82 nao grava ts_saida` é a §2.1 dita pela própria
régua antiga, e a ausência de qualquer linha `calibracao [Q-7]` é a §2.3 pelo mesmo caminho.

### 2.5 A purga estava certa e não mudou nada; o funding mudou tudo o que mudou

O discriminante permite ir mais fundo do que separar janela de correção, porque as duas rodadas
escolheram **as mesmas configs em todos os cinco folds** — `(65,25)`, `(50,22)`, `(55,22)`,
`(55,22)`, `(50,22)` — com **contagem de trades idêntica** em cada um: 390, 537, 528, 503, 616.

Daí saem duas leituras, e nenhuma delas estava escrita aqui antes:

**A purga funcionou e foi inerte.** Ela só remove trade do **treino**, nunca do teste — o que os
números confirmam, já que o conjunto OOS não mudou. Ela mexeu no in-sample (Reality Check
`p = 0,4928 → 0,4873`, DSR `0,0095 → 0,0099`), mas **não virou nenhuma seleção**: as seis configs
mantiveram a ordem relativa em todos os folds. O vazamento que a §2.1 descreve era real e a
correção era obrigatória; **neste dado ele não estava alterando a resposta.** Registrar isso
importa porque a §2.1 avisa que o viés empurra *para cima* — verdadeiro como mecanismo, e de
magnitude **zero em seleção** aqui. Uma correção obrigatória pode ser inerte, e dizer que ela
"consertou o número" quando não consertou seria a mesma fabricação que o `c8b4593` teve de desfazer.

**O funding é a totalidade do movimento, e ele revela o sinal do carry.** Com trades idênticos,
sobra um único canal para os R$134: a duração da barra. Por fold:

| fold | antigo (funding sobre 1/4 do tempo) | novo (tempo real) | Δ |
|---|---|---|---|
| 1 | +196 | +216 | **+20** |
| 2 | +5.817 | +5.808 | −9 |
| 3 | −1.219 | −1.212 | +7 |
| 4 | +889 | +977 | **+88** |
| 5 | −4.690 | −4.663 | +27 |
| **OOS** | **+993** | **+1.127** | **+134** |

**Cobrar o funding por 4× mais tempo fez o P&L SUBIR.** Pela regra que o `ddbdf33` fixou — *a
direção segue o sinal do carry líquido do período* — isso só acontece num livro que **recebe** mais
do que paga: **net-SHORT nos 1.095 dias**, sob a política `A`. É a resposta à pergunta que a §2.2
deixou explicitamente em aberto (*"para os 1.095 dias, esse sinal ainda NÃO foi medido"*).

⚠️ **E ela não é o contraste do `[P2-10]`.** O que está medido aqui é *1/4 do tempo* contra
*tempo real*, não *com funding* contra *sem funding*; o módulo do efeito do carry continua sem
medida, e só o **sinal** está determinado. Quem quiser o módulo roda
`python -m pesquisa.validacao` (com contraste), que imprime a linha `COM x SEM funding`. O sinal
também é da política `A` e não se transfere às outras três sem medição: elas têm hold médio e
direção diferentes.

---

## 3. Os números

Comando, da **raiz** do repositório (`pesquisa/` é pacote — por caminho não roda):

```
python -m pesquisa.validacao politicas
```

Doze moedas × 1h × 1095 dias, seis configs × cinco folds, mesma janela e mesmos dados para as
quatro políticas. `seed=42` no `PADRAO`, `numpy.random.default_rng`, nunca o `random` global.

### 3.1 A tabela comparativa

<!-- COLAR: a saída literal do bloco "COMPARACAO DE POLITICAS DE SAIDA", incluindo a tabela de
     motivos de saída por política e as duas linhas finais sobre o P&L ser diagnóstico. -->

```
==============================================================================================================
COMPARACAO DE POLITICAS DE SAIDA -- mesma regua, mesmas janelas, mesmos dados [P1-10]
==============================================================================================================
politica                 trades   win%   PnL OOS Sharpe an.          IC95% Sharpe     DSR    MDS  veredito
A stop+flip de regime      2574   29.9     +1127      0.124       (-1.683, 1.359)  0.0099  1.576 (piso)  SEM_EVIDENCIA
B auto-saida               5314   63.9     -7837     -1.018       (-2.334, 0.075)     0.0  1.575  SEM_EVIDENCIA
C trailing 2% fixo         5342   61.2     +5040      0.645       (-0.714, 1.824)  0.0602  1.575  SEM_EVIDENCIA
C trailing 3xATR           4037   50.4     +4227      0.436       (-0.918, 1.634)  0.0145  1.575  SEM_EVIDENCIA

motivos de saida por politica (o que de fato fechou os trades):
   A stop+flip de regime    regime: 1334 | stop: 1227 | liquidacao: 13
   B auto-saida             auto-saida: 3394 | stop: 1847 | liquidacao: 73
   C trailing 2% fixo       trailing: 3420 | stop: 1871 | liquidacao: 51
   C trailing 3xATR         trailing: 2086 | stop: 1862 | liquidacao: 89

O P&L esta na tabela como DIAGNOSTICO. O que decide e o veredito da ultima coluna,
emitido sob o PADRAO travado -- soma bruta de P&L favorece quem mais opera [F3].
```

### 3.2 O relatório completo de cada política

<!-- COLAR: os quatro blocos "=== WALK-FORWARD: ... ===" completos, um por política, cada um com
     BLOCO A, BLOCO B e a linha de veredito. São eles que sustentam a tabela acima; a tabela
     sozinha não permite auditar o motivo de cada veredito. -->

```
=== WALK-FORWARD: tendencia | 1h 1095d | 10x | saida: A stop+flip de regime | 6 configs x 5 folds ===
PADRAO (travado): criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga: ATIVA
n_trials = 100 (PISO CONTADO, nao estimativa)
calibracao [Q-7]: o controle nulo rejeitou 1/200 paineis sem sinal (taxa 0.005) -> FORA DA BANDA (abaixo)
   banda de aceitacao CALCULADA (binomial exata, alfa=0,05, 95%): [4 ; 16] rejeicoes = [0.02 ; 0.08] | IC da taxa medida: (0.00013, 0.02754)

 fold   config (conv/adx)   trades    pnl OOS
    1            (65, 25)      390  R$   +216
    2            (50, 22)      537  R$  +5808
    3            (55, 22)      528  R$  -1212
    4            (55, 22)      503  R$   +977
    5            (50, 22)      616  R$  -4663

OOS agregado: 2574 trades | win 29.9% | PnL R$+1127
  serie diaria da JANELA OOS: 908 dias (721 com P&L nao-nulo) -- o 1o dos 6 segmentos e treino puro e nao entra

-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.
   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO
   White's Reality Check (N=6 configs, 2000 bootstraps de bloco): p = 0.4873
   Hansen SPA (estudentizado):                                     p = 0.4958
   p da melhor config SOZINHA (sem multiplicidade):                p = 0.4013
     -> o grid custou 0.086 de multiplicidade. [F12]
   DSR da melhor config in-sample (50, 22) sobre a SERIE DIARIA (1089 dias): DSR = 0.0099
     (sr=0.0074 vs sr0_esperado=0.0767 para n_trials=100)
   [contraste] o numero ANTIGO -- DSR sobre a lista de 2574 trades OOS: 0.0127
     -> objeto errado duas vezes: trades correlacionados contados como independentes, e o agregado OOS em vez da melhor config in-sample. [Q-1 1 e 3]
   FDR (Benjamini-Hochberg, q=0,10): 0 de 6 configs sobrevivem -- FORA do veredito, nao-informativo em N=6 [F16]

   sensibilidade a n_trials (a dependencia e LOGARITMICA -- [F10]):
    n_trials       sr0      DSR
           6    0.0394    0.141
          30    0.0628   0.0311
         100    0.0767   0.0099
        1000    0.0986   0.0011
       10000     0.117   0.0001

-- BLOCO B -- out-of-sample, o PROCESSO. Nulo: E[pnl do walk-forward] <= 0.
   pergunta: 'o procedimento, aplicado cego pra frente, ganha dinheiro?'  papel: DECISAO
   IC95% da media/dia -- bloco (block=5): (-12.931, 16.0049)   iid: (-10.7905, 14.5654)
   PSR (sem deflacao, SR*=0): 0.5792  (sr/dia = 0.0065)
   Sharpe ANUALIZADO: 0.124   IC95% (bloco): (-1.683, 1.359)
   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, T=908): 1.576 -- e um PISO
     -> alfa efetivo medido 0.005 (nao 0,05), IC (0.00013, 0.02754): com ele o MDS vale 2.167; com a ponta MENOS exigente do IC, 1.75. Limite = 2.0.
        O numero da linha acima e um PISO -- e o portao le 1.75, para nao bloquear por imprecisao do diagnostico.
     -> comparacao de poder: T=180 dias daria MDS 3.54; T=1095 daria 1.44. [F6]
   concentracao [F17]: top-5 dias = 0.223 do lucro bruto | folds positivos 3/5 | maior fold = 5.15 do total
     (com 5 folds, 5 positivos de 5 dao p=0,031 e 4/5 dao p=0,19 -- diagnostico, nunca portao)
   ACF do P&L diario, lags 1..10: [0.2218, 0.0319, -0.0054, -0.0031, -0.0205, -0.0143, -0.0434, -0.0389, 0.0209, 0.0243]
     banda +-1,96/sqrt(T) = +-0.065 -- fora dela = autocorrelacao real [F12]

=> VEREDITO: SEM EVIDENCIA DE EDGE (IC-bloco (-12.931, 16.0049) inclui 0 ou PSR 0.5792 <= 0,95 ou RC p = 0.4873 > 0,05).
   IC95% do Sharpe anualizado: [-1.683 ; 1.359].
   O teste NAO exclui edges de Sharpe ate 1.359 -- MDS = 1.576 (PISO; com o alfa efetivo medido, 2.167). Ausencia de evidencia nao e evidencia de ausencia. [F7]

=== WALK-FORWARD: tendencia | 1h 1095d | 10x | saida: B auto-saida | 6 configs x 5 folds ===
PADRAO (travado): criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga: ATIVA
n_trials = 100 (PISO CONTADO, nao estimativa)
calibracao [Q-7]: o controle nulo rejeitou 8/200 paineis sem sinal (taxa 0.04) -> CALIBRADO
   banda de aceitacao CALCULADA (binomial exata, alfa=0,05, 95%): [4 ; 16] rejeicoes = [0.02 ; 0.08] | IC da taxa medida: (0.01742, 0.07729)

 fold   config (conv/adx)   trades    pnl OOS
    1            (65, 22)      858  R$  -1683
    2            (55, 25)     1190  R$   +478
    3            (55, 25)     1171  R$  -3378
    4            (55, 25)     1081  R$   -695
    5            (55, 25)     1014  R$  -2559

OOS agregado: 5314 trades | win 63.9% | PnL R$-7837
  serie diaria da JANELA OOS: 910 dias (844 com P&L nao-nulo) -- o 1o dos 6 segmentos e treino puro e nao entra

-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.
   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO
   White's Reality Check (N=6 configs, 2000 bootstraps de bloco): p = 0.985
   Hansen SPA (estudentizado):                                     p = 0.0315
   p da melhor config SOZINHA (sem multiplicidade):                p = 0.987
     -> o grid custou -0.002 de multiplicidade. [F12]
   DSR da melhor config in-sample (55, 25) sobre a SERIE DIARIA (1092 dias): DSR = 0.0
     (sr=-0.0612 vs sr0_esperado=0.0766 para n_trials=100)
   [contraste] o numero ANTIGO -- DSR sobre a lista de 5314 trades OOS: 0.0
     -> objeto errado duas vezes: trades correlacionados contados como independentes, e o agregado OOS em vez da melhor config in-sample. [Q-1 1 e 3]
   FDR (Benjamini-Hochberg, q=0,10): 0 de 6 configs sobrevivem -- FORA do veredito, nao-informativo em N=6 [F16]

   sensibilidade a n_trials (a dependencia e LOGARITMICA -- [F10]):
    n_trials       sr0      DSR
           6    0.0393   0.0008
          30    0.0627      0.0
         100    0.0766      0.0
        1000    0.0985      0.0
       10000    0.1168      0.0

-- BLOCO B -- out-of-sample, o PROCESSO. Nulo: E[pnl do walk-forward] <= 0.
   pergunta: 'o procedimento, aplicado cego pra frente, ganha dinheiro?'  papel: DECISAO
   IC95% da media/dia -- bloco (block=5): (-17.9768, 0.6426)   iid: (-18.8722, 2.1717)
   PSR (sem deflacao, SR*=0): 0.0613  (sr/dia = -0.0533)
   Sharpe ANUALIZADO: -1.018   IC95% (bloco): (-2.334, 0.075)
   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, T=910): 1.575
     -> comparacao de poder: T=180 dias daria MDS 3.54; T=1095 daria 1.44. [F6]
   concentracao [F17]: top-5 dias = 0.137 do lucro bruto | folds positivos 1/5 | maior fold = 0.43 do total
     (com 5 folds, 5 positivos de 5 dao p=0,031 e 4/5 dao p=0,19 -- diagnostico, nunca portao)
   ACF do P&L diario, lags 1..10: [-0.0528, -0.0341, -0.0211, -0.0294, -0.0581, 0.0604, -0.0172, -0.0287, -0.0228, -0.023]
     banda +-1,96/sqrt(T) = +-0.065 -- fora dela = autocorrelacao real [F12]

=> VEREDITO: SEM EVIDENCIA DE EDGE (IC-bloco (-17.9768, 0.6426) inclui 0 ou PSR 0.0613 <= 0,95 ou RC p = 0.985 > 0,05).
   IC95% do Sharpe anualizado: [-2.334 ; 0.075].
   O teste NAO exclui edges de Sharpe ate 0.075 -- MDS = 1.575. Ausencia de evidencia nao e evidencia de ausencia. [F7]

=== WALK-FORWARD: tendencia | 1h 1095d | 10x | saida: C trailing 2% fixo | 6 configs x 5 folds ===
PADRAO (travado): criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga: ATIVA
n_trials = 100 (PISO CONTADO, nao estimativa)
calibracao [Q-7]: o controle nulo rejeitou 14/200 paineis sem sinal (taxa 0.07) -> CALIBRADO
   banda de aceitacao CALCULADA (binomial exata, alfa=0,05, 95%): [4 ; 16] rejeicoes = [0.02 ; 0.08] | IC da taxa medida: (0.0388, 0.11466)

 fold   config (conv/adx)   trades    pnl OOS
    1            (55, 22)     1116  R$  +1681
    2            (55, 22)     1163  R$  +2862
    3            (55, 22)     1119  R$   -732
    4            (55, 22)      986  R$  +2183
    5            (50, 22)      958  R$   -955

OOS agregado: 5342 trades | win 61.2% | PnL R$+5040
  serie diaria da JANELA OOS: 910 dias (863 com P&L nao-nulo) -- o 1o dos 6 segmentos e treino puro e nao entra

-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.
   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO
   White's Reality Check (N=6 configs, 2000 bootstraps de bloco): p = 0.2034
   Hansen SPA (estudentizado):                                     p = 0.2294
   p da melhor config SOZINHA (sem multiplicidade):                p = 0.1724
     -> o grid custou 0.031 de multiplicidade. [F12]
   DSR da melhor config in-sample (50, 22) sobre a SERIE DIARIA (1092 dias): DSR = 0.0602
     (sr=0.0311 vs sr0_esperado=0.0766 para n_trials=100)
   [contraste] o numero ANTIGO -- DSR sobre a lista de 5342 trades OOS: 0.2823
     -> objeto errado duas vezes: trades correlacionados contados como independentes, e o agregado OOS em vez da melhor config in-sample. [Q-1 1 e 3]
   FDR (Benjamini-Hochberg, q=0,10): 0 de 6 configs sobrevivem -- FORA do veredito, nao-informativo em N=6 [F16]

   sensibilidade a n_trials (a dependencia e LOGARITMICA -- [F10]):
    n_trials       sr0      DSR
           6    0.0393   0.3887
          30    0.0627   0.1398
         100    0.0766   0.0602
        1000    0.0985   0.0107
       10000    0.1168   0.0017

-- BLOCO B -- out-of-sample, o PROCESSO. Nulo: E[pnl do walk-forward] <= 0.
   pergunta: 'o procedimento, aplicado cego pra frente, ganha dinheiro?'  papel: DECISAO
   IC95% da media/dia -- bloco (block=5): (-5.4961, 16.9222)   iid: (-4.4958, 16.4639)
   PSR (sem deflacao, SR*=0): 0.8544  (sr/dia = 0.0338)
   Sharpe ANUALIZADO: 0.645   IC95% (bloco): (-0.714, 1.824)
   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, T=910): 1.575
     -> comparacao de poder: T=180 dias daria MDS 3.54; T=1095 daria 1.44. [F6]
   concentracao [F17]: top-5 dias = 0.11 do lucro bruto | folds positivos 3/5 | maior fold = 0.57 do total
     (com 5 folds, 5 positivos de 5 dao p=0,031 e 4/5 dao p=0,19 -- diagnostico, nunca portao)
   ACF do P&L diario, lags 1..10: [0.0854, 0.0217, -0.0219, -0.0438, -0.0431, 0.046, -0.0555, -0.0407, 0.0, -0.0101]
     banda +-1,96/sqrt(T) = +-0.065 -- fora dela = autocorrelacao real [F12]

=> VEREDITO: SEM EVIDENCIA DE EDGE (IC-bloco (-5.4961, 16.9222) inclui 0 ou PSR 0.8544 <= 0,95 ou RC p = 0.2034 > 0,05).
   IC95% do Sharpe anualizado: [-0.714 ; 1.824].
   O teste NAO exclui edges de Sharpe ate 1.824 -- MDS = 1.575. Ausencia de evidencia nao e evidencia de ausencia. [F7]

=== WALK-FORWARD: tendencia | 1h 1095d | 10x | saida: C trailing 3xATR | 6 configs x 5 folds ===
PADRAO (travado): criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga: ATIVA
n_trials = 100 (PISO CONTADO, nao estimativa)
calibracao [Q-7]: o controle nulo rejeitou 9/200 paineis sem sinal (taxa 0.045) -> CALIBRADO
   banda de aceitacao CALCULADA (binomial exata, alfa=0,05, 95%): [4 ; 16] rejeicoes = [0.02 ; 0.08] | IC da taxa medida: (0.02078, 0.0837)

 fold   config (conv/adx)   trades    pnl OOS
    1            (55, 22)      793  R$  -1058
    2            (50, 22)      804  R$  +3140
    3            (50, 22)      812  R$   +520
    4            (50, 22)      815  R$  +3649
    5            (50, 22)      813  R$  -2024

OOS agregado: 4037 trades | win 50.4% | PnL R$+4227
  serie diaria da JANELA OOS: 910 dias (844 com P&L nao-nulo) -- o 1o dos 6 segmentos e treino puro e nao entra

-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.
   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO
   White's Reality Check (N=6 configs, 2000 bootstraps de bloco): p = 0.4453
   Hansen SPA (estudentizado):                                     p = 0.4608
   p da melhor config SOZINHA (sem multiplicidade):                p = 0.3603
     -> o grid custou 0.085 de multiplicidade. [F12]
   DSR da melhor config in-sample (50, 22) sobre a SERIE DIARIA (1092 dias): DSR = 0.0145
     (sr=0.0113 vs sr0_esperado=0.0766 para n_trials=100)
   [contraste] o numero ANTIGO -- DSR sobre a lista de 4037 trades OOS: 0.087
     -> objeto errado duas vezes: trades correlacionados contados como independentes, e o agregado OOS em vez da melhor config in-sample. [Q-1 1 e 3]
   FDR (Benjamini-Hochberg, q=0,10): 0 de 6 configs sobrevivem -- FORA do veredito, nao-informativo em N=6 [F16]

   sensibilidade a n_trials (a dependencia e LOGARITMICA -- [F10]):
    n_trials       sr0      DSR
           6    0.0393    0.174
          30    0.0627   0.0427
         100    0.0766   0.0145
        1000    0.0985   0.0018
       10000    0.1168   0.0002

-- BLOCO B -- out-of-sample, o PROCESSO. Nulo: E[pnl do walk-forward] <= 0.
   pergunta: 'o procedimento, aplicado cego pra frente, ganha dinheiro?'  papel: DECISAO
   IC95% da media/dia -- bloco (block=5): (-8.7558, 18.8564)   iid: (-8.4918, 17.8807)
   PSR (sem deflacao, SR*=0): 0.7594  (sr/dia = 0.0228)
   Sharpe ANUALIZADO: 0.436   IC95% (bloco): (-0.918, 1.634)
   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, T=910): 1.575
     -> comparacao de poder: T=180 dias daria MDS 3.54; T=1095 daria 1.44. [F6]
   concentracao [F17]: top-5 dias = 0.12 do lucro bruto | folds positivos 3/5 | maior fold = 0.86 do total
     (com 5 folds, 5 positivos de 5 dao p=0,031 e 4/5 dao p=0,19 -- diagnostico, nunca portao)
   ACF do P&L diario, lags 1..10: [0.0613, 0.0077, 0.0239, -0.0321, -0.0278, -0.0016, -0.0182, -0.0424, 0.0225, -0.0128]
     banda +-1,96/sqrt(T) = +-0.065 -- fora dela = autocorrelacao real [F12]

=> VEREDITO: SEM EVIDENCIA DE EDGE (IC-bloco (-8.7558, 18.8564) inclui 0 ou PSR 0.7594 <= 0,95 ou RC p = 0.4453 > 0,05).
   IC95% do Sharpe anualizado: [-0.918 ; 1.634].
   O teste NAO exclui edges de Sharpe ate 1.634 -- MDS = 1.575. Ausencia de evidencia nao e evidencia de ausencia. [F7]
```

### 3.3 O smoke curto, que já está rodado

Este não é a régua e não emite veredito — é a prova, em um minuto, de que as quatro políticas
executam e produzem trades **diferentes entre si**. Se as colunas de motivo colapsarem numa só, a
comparação do marco perdeu o objeto e não há por que gastar a hora da régua. Saída literal,
`python -m pesquisa.backtest_plataforma` (8 ativos, 15m, 60 dias):

```
politica                trades    win%        P&L   motivos de saida
  --------------------------------------------------------------------------------------------
A stop+flip de regime      528    20.8       -107   stop: 266 | regime: 262
B auto-saida              1072    57.7       -554   auto-saida: 619 | stop: 453
C trailing 2% fixo         485    37.7       +169   stop: 296 | trailing: 189
C trailing 3xATR           694    45.0       +521   trailing: 352 | stop: 342

  as politicas produzem saidas distintas duas a duas (ts_saida, pnl)
```

**Sessenta dias não têm poder e isto não é veredito.** O que ele mostra que vale registrar: a linha
**B** reproduz sozinha a assinatura que a `INVESTIGACAO-TRADING-2026-08-19.md` levantou no banco
vivo — **win 57,7% com P&L negativo**. Ganha-pouco / perde-grande sobrevive fora da amostra que o
originou, o que é uma razão a mais para não ler win rate como qualidade.

---

## 4. A ressalva do `[Q-7]`, e ela é a mais importante deste documento

**O controle nulo que mede o alfa efetivo é cego para a falha que importa.**

O `[Q-7]` investigou por que a régua rejeitava 0,01 dos painéis sem sinal, contra 0,05 nominal. A
causa não é o `+1` do p-valor nem o `block=5` — os dois estão presentes numa marginal normal, que
fica calibrada. A causa é a **forma da marginal**: o Reality Check toma o máximo de médias
**brutas**, e numa série diária de P&L — zerada na maioria dos dias, truncada em `−valor` à
esquerda, cauda longa à direita — isso infla o quantil nulo. O mecanismo já estava escrito no
próprio arquivo, em `spa_hansen`, `[F15]`; ninguém tinha ligado o comentário ao número. A
estudentização **não conserta**: o SPA fica pior.

O degrau que muda como o `0,01` se lê: rodando o controle **aninhado** — o que roda sobre o dado
real — num painel sorteado daquela mesma marginal pesada, ele devolve ~0,04, perto do nominal. Os
dois níveis dele usam a **mesma** distribuição empírica, o erro do bootstrap entra dos dois lados e
se cancela. Logo:

* **o `0,01` é estimativa otimista do alfa efetivo** — o valor verdadeiro tende a ser menor;
* **o piso do MDS calculado com ele é frouxo**;
* **de quanto, ninguém sabe.** O controle direto sobre um DGP com aquela marginal deu `0,0025`, mas
  esse DGP é caricatura escolhida à mão, e usar o número dele como medida do dado real seria trocar
  um chute por outro. Fechar essa distância exige o controle nulo **completo** do `[F9]` — M
  geradores de sinal aleatório pelo pipeline inteiro. O bloqueio de território caiu
  (`backtest_ativo` aceita `sinal_fn` desde o `234a423`); o que resta é relógio: uma passada do
  grid leva ~13 min e M=200 passadas não cabem numa rodada.

### O que fazer com isso ao ler a tabela

**Se alguma política sair `INCONCLUSIVO` por `mds_piso_min > MDS_LIMITE`, isso não é falha da
rodada nem defeito da política.** É o instrumento dizendo o que consegue e o que não consegue
medir — que é, palavra por palavra, o que o `[Q-1]` acrescentou à régua e o que o `[Q-7]` estendeu
uma camada abaixo. *Ausência de evidência não é evidência de ausência.*

E vale para o outro lado com a mesma força: **se as políticas saírem `SEM_EVIDENCIA` com o MDS
marcado como piso, a leitura correta não é "está provado que não há edge"** — é "não há evidência,
e o poder real de detectar é menor do que o número publicado, em quantidade não medida". A linha
`IC95% do Sharpe anualizado` do relatório é o que diz o que o teste **não exclui**, e é ela que
deve ser citada junto do veredito, nunca o veredito sozinho.

<!-- COLAR: para cada política, se a linha do MDS trouxer "-- e um PISO", cole também as duas
     linhas seguintes (alfa efetivo medido, IC, mds_piso e mds_piso_min). Sem elas o leitor não
     tem como saber quanto de folga sobrou. -->

**Das quatro políticas, só uma trouxe `-- e um PISO`: a `A`.** As outras três saíram `CALIBRADO`,
e por isso o MDS delas se lê como está impresso, sem a folga desconhecida desta seção.

```
A stop+flip de regime    o controle nulo rejeitou 1/200 paineis sem sinal (taxa 0.005) -> FORA DA BANDA (abaixo)
B auto-saida             o controle nulo rejeitou 8/200 paineis sem sinal (taxa 0.04) -> CALIBRADO
C trailing 2% fixo       o controle nulo rejeitou 14/200 paineis sem sinal (taxa 0.07) -> CALIBRADO
C trailing 3xATR         o controle nulo rejeitou 9/200 paineis sem sinal (taxa 0.045) -> CALIBRADO
```

```
   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, T=908): 1.576 -- e um PISO
     -> alfa efetivo medido 0.005 (nao 0,05), IC (0.00013, 0.02754): com ele o MDS vale 2.167; com a ponta MENOS exigente do IC, 1.75. Limite = 2.0.
        O numero da linha acima e um PISO -- e o portao le 1.75, para nao bloquear por imprecisao do diagnostico.
```

### O que esta rodada acrescentou ao `[Q-7]`, e não estava previsto aqui

**A miscalibração não é propriedade da régua: é propriedade da régua *aplicada àquela política*.**
O controle nulo roda o pipeline inteiro, saída incluída, então trocar a política troca a marginal
que ele amostra — e a §4 diz que a causa do desvio é exatamente **a forma da marginal**.

A rodada dá quatro pontos, e eles ficam em ordem com o mecanismo:

| política | dias com P&L não-nulo | rejeições em 200 | leitura |
|---|---|---|---|
| A stop+flip de regime | 721 / 908 (79%) | 1 (0,005) | **FORA DA BANDA (abaixo)** |
| B auto-saída | 844 / 910 (93%) | 8 (0,04) | CALIBRADO |
| C trailing 3×ATR | 844 / 910 (93%) | 9 (0,045) | CALIBRADO |
| C trailing 2% fixo | 863 / 910 (95%) | 14 (0,07) | CALIBRADO |

Quanto mais dias zerados, mais degenerada a marginal, mais inflado o quantil nulo, menos
rejeições — que é, palavra por palavra, o mecanismo que o `[Q-7]` descreveu em `spa_hansen`,
`[F15]`. **Quatro pontos não demonstram uma relação**, e nenhum deles foi desenhado para testá-la;
o que eles fazem é dar ao mecanismo a primeira evidência empírica que ele tinha, e apontar a
variável que o controle nulo completo do `[F9]` deveria varrer.

**E a consequência desconfortável:** a política `A` é a única fora de banda, e é justamente a que
a régua sempre mediu — é dela o *"sem edge"* que está no cabeçalho do `CLAUDE.md`, no `README.md`
e no `autotrader.py:8-13`. O veredito histórico do projeto foi emitido no único ponto do espaço
medido em que o instrumento se sabe descalibrado. Isso **não** o invalida: descalibrado *para baixo*
significa alfa efetivo menor que o nominal, portanto MDS maior, portanto **menos** poder — o erro
empurra na direção de não detectar edge, que é a direção do veredito que já está publicado. O que
ele faz é medir a folga: para `A`, o MDS honesto é **2,167**, não 1,576, e 2,167 está **acima** do
`MDS_LIMITE = 2,0`. Se o portão lesse o alfa medido em vez da ponta menos exigente do IC, a
política `A` sairia **`INCONCLUSIVO`**.

Uma política **B**, **C-2%** ou **C-3×ATR** não tem esse problema: o piso delas é o número impresso.

---

## 5. A ressalva do `[Q-4]`, com data

O **portão de fluxo** (`exigir_fluxo`) roda ao vivo, lê o book e o fluxo taker, e **recusa sinais**
que o backtest opera. Ele não existe em histórico: não há livro de ordens em OHLCV. O `[Q-4]` mede
prospectivamente quanto ele distorce o que foi medido — e ele **não fecha nesta onda**.

* Medição da matriz no banco da VM, **2026-08-23**: **21 rejeições com desfecho, 327 sem**. O
  critério de aceite pede **≥100**.
* O job marca cada sinal exatamente **+24h** depois de ele nascer, então a amostra fecha **sozinha
  em 2026-08-24**.
* O card fica em 🔍 Validando; o relatório comparativo é da matriz quando a amostra fechar.

**O que o `[Q-4]` dá ao `[P1-10]` é ressalva, não insumo.** O veredito das políticas não depende
dele. O que ele responde é *quanto* o portão de fluxo desloca o que foi medido — e a direção do
efeito no P&L é **desconhecida** hoje (é literalmente o que o `[Q-5]` declara no limite (b)). Até
2026-08-24, a tabela desta rodada mede um universo de sinais **maior** que o que o vivo aceita.

---

## 6. Limites herdados do `[Q-5]` que afetam esta leitura

O `[Q-5]` (backtest de portfólio, `pesquisa/backtest_portfolio.py`) imprime os limites dele junto
dos próprios números, de propósito. Três deles mudam como esta comparação de políticas deve ser
lida — e o primeiro é o que mais importa:

* **(e) o backtest de portfólio não consegue medir a política B.** Com `trailing_ativo=1` o próprio
  `auto_executar` **desliga** o auto-fechar (`autotrader.py:151`), e o `Ambiente` do `[Q-5]`
  **recusa** rodar com `trailing_ativo=0` em vez de rodar mentindo. Consequência: a comparação
  A×B×C existe **apenas** no backtest por-ativo. Nenhum número de **banca** — drawdown, curva de
  equity, trava diária, teto de exposição — está disponível para B. Quem quiser isso precisa de
  card novo, e ele depende de o `[Q-5]` aprender a simular o gestor de saída.
* **(c) o backtest de portfólio não paga funding**; o por-ativo paga (`FUNDING_8H = 0,0001`, e agora
  pelo tempo certo — §2.2). Os dois não são comparáveis nesse eixo, e é o por-ativo que sustenta
  esta tabela.
* **(b) o portão de fluxo está desligado nos dois** — é a mesma ressalva da §5, e ela vale igual
  para as quatro políticas, portanto **não** distorce a comparação *relativa* entre elas. Distorce
  o nível absoluto das quatro.

Um limite do **por-ativo**, que é o motor desta rodada e precisa ficar dito aqui porque não está no
`[Q-5]`: ele não modela `auto_cooldown_min`, `auto_max_posicoes`, teto de exposição, trava diária
nem sizing por risco. Todos reduzem o número de trades ao vivo; **nenhum muda a saída de um trade
já aberto**, que é exatamente o que esta comparação isola.

E um limite da política **B** especificamente, que empurra na direção contra o achado: o gestor de
saída ao vivo tem um **quarto** gatilho — o fluxo do book — que não existe em OHLCV. Ele só
**acrescenta** motivos, nunca remove. Então a B medida aqui fecha **menos** vezes que a viva,
segura a posição por mais tempo e fica **mais perto de A** do que a de verdade. O viés é contra a
diferença entre políticas, isto é, contra o próprio achado que o card procura.

---

## 7. Recomendação — o quarto item do aceite

O `[P1-10]` pede: *"decidir o default do vivo pelo resultado — **ou** registrar explicitamente que
o experimento roda política não-validada (decisão consciente, documentada)"*. **As duas são
respostas.** O que **não** é resposta é a tabela sem veredito.

Esta seção está escrita **antes** dos números de propósito: recomendação formulada depois de ver o
placar é escolha, não critério. O que segue é o critério, e ele se aplica sozinho quando a §3 for
colada.

### 7.1 O que decide, e o que não decide

**Não decide:** o P&L da coluna `PnL OOS`. Soma bruta de P&L favorece a config que mais **opera**,
não a melhor — é o `[F3]`, e é por isso que o `PADRAO` usa `criterio="sharpe"`. A coluna está na
tabela como diagnóstico. Também não decide o **win rate**: a política B tem o maior win rate das
quatro e o P&L mais negativo do smoke, o que é a demonstração mais curta possível de por quê.

**Decide:** o `veredito` da última coluna, emitido sob o `PADRAO` travado, com o `IC95% do Sharpe
anualizado` lido junto — nunca o veredito sozinho (§4).

### 7.2 As quatro leituras possíveis, e a recomendação sob cada uma

> **Aplica-se o Caso 1.** As quatro políticas saíram `SEM_EVIDENCIA` (§3.1), nenhuma passou do
> `MDS_LIMITE` na leitura do portão, e nenhuma saiu `INCONCLUSIVO`. A recomendação é, portanto:
> **registrar o desvio, não trocar o default** — a segunda metade do item 4 do aceite.
> O texto dos quatro casos fica exatamente como foi escrito antes da rodada: é ele que prova que
> o critério não foi escolhido depois de ver o placar.

**Caso 1 — todas as quatro saem `SEM_EVIDENCIA` (o desfecho esperado).**
Recomendação: **registrar o desvio, não trocar o default.** Ou seja, a segunda metade do item 4 do
aceite. Se nenhuma política tem edge demonstrável, trocar o default do vivo por outra política sem
edge é movimento sem justificativa que só gasta a única coisa que o experimento produz — o
histórico contínuo de uma configuração conhecida. O que fica documentado no `[P2-17]` é: *o
experimento ao vivo roda a política C, que foi backtestada nesta rodada e não demonstrou edge; a
decisão de mantê-la é consciente e o motivo é continuidade da série, não expectativa de retorno.*
Isso é uma resposta completa, e é a que o `CLAUDE.md` prevê no cabeçalho.

**Caso 2 — todas saem `INCONCLUSIVO`.**
Recomendação: **registrar o desvio e abrir card para o `[F9]` completo.** `INCONCLUSIVO` significa
que o instrumento não tem poder para separar as políticas; trocar o default nessa condição é
decidir na moeda. O card a abrir é o controle nulo completo (§4), porque é ele que fecha a
distância entre o piso frouxo e o alfa verdadeiro — e é essa distância que hoje impede a régua de
responder. Prioridade: **alta**, porque enquanto ela existir o marco M4 não consegue ser fechado
com número em que se aposte, apenas com a declaração honesta de que não consegue.

**Caso 3 — exatamente uma política sai `EDGE` e as outras não.**
Recomendação: **não trocar o default ainda; abrir card de replicação.** Um `EDGE` isolado numa
comparação de quatro é uma seleção entre quatro tentativas, e o `n_trials = 100` do DSR foi contado
para o data-snooping **histórico** do projeto, não para esta comparação. O passo correto é
re-rodar a política vencedora com `n_trials` que inclua estas quatro (o piso sobe, o DSR desce) e
verificar se ela sobrevive. Só depois disso a troca de default vira proposta. Se a vencedora for
**C em k×ATR**, some a isso a recomendação de §7.3, que é barata e independente.

**Caso 4 — duas ou mais saem `EDGE`.**
Recomendação: **suspeitar do instrumento antes de comemorar.** Quatro políticas sobre a mesma
entrada, no mesmo período, nas mesmas moedas, são fortemente correlacionadas; dois `EDGE`
simultâneos são mais compatíveis com um portão frouxo do que com dois edges. Antes de qualquer
troca de default, conferir a linha de `calibracao [Q-7]` das quatro: se ela estiver na metade de
cima da banda, o portão de EDGE está mais fácil do que o nominal e o `[Q-7]` previu exatamente esse
modo de falha. Nesse caso o card é sobre a régua, não sobre o default.

### 7.3 Uma recomendação que vale sob qualquer um dos quatro casos

**O `trailing_dist=2%` fixo é incoerente em unidade, e isso é verdade independentemente do
veredito.** A entrada dimensiona o stop em 3×ATR — proporcional à volatilidade do ativo — e a saída
usa uma constante em espaço-preço. O mesmo 2% é um stop apertadíssimo em BTC e frouxo em DOGE, e a
2x vale 4% de ROE enquanto a 20x vale **40%**. O espelho existe no `alvo_roe=5` do gestor de saída,
que é fixo em ROE e a 20x dispara com 0,25% de movimento de preço — ruído.

Recomendação: **trocar `trailing_dist` por `trailing_k_atr`, com `k` escolhido no treino, mesmo
que a rodada não separe as políticas.** O argumento não é de performance, é de coerência de
unidade: o parâmetro atual mede uma coisa diferente em cada ativo e em cada alavancagem, o que
torna qualquer resultado sobre ele não-transferível. A linha `C trailing 3xATR` da tabela dá a
ordem de grandeza; o `k` de produção sai do walk-forward, não desta recomendação.

**O placar NÃO apoiou esta recomendação, e isso fica registrado aqui em vez de ser omitido.**
`C trailing 3×ATR` ficou **abaixo** de `C trailing 2% fixo` nas três medidas que importam: Sharpe
anualizado 0,436 contra 0,645, PSR 0,759 contra 0,854, DSR 0,0145 contra 0,0602. Se o argumento
desta seção fosse de performance, a rodada o teria derrubado.

Ele não é, e por isso segue de pé: a incoerência de unidade do `trailing_dist=2%` é verdadeira
independentemente de qual das duas pontua mais, e foi por isso que esta seção foi escrita **antes**
dos números. Some-se que as duas saíram `SEM_EVIDENCIA` e que os IC95% de Sharpe se sobrepõem
quase inteiros — `(-0,714; 1,824)` contra `(-0,918; 1,634)`: a ordenação entre elas **não é uma
diferença demonstrada**, é ruído com sinal. Ler o placar como "o 2% é melhor" seria cometer, na
comparação entre políticas, o mesmo erro que a §7.1 proíbe cometer com o P&L.

O que a rodada muda de fato na recomendação: o `k=3` usado aqui é o do smoke, **não** foi escolhido
no treino, e a §7.3 sempre disse que o `k` de produção sai do walk-forward. Um `k` varrido no grid
é pré-requisito de qualquer proposta de troca — e a comparação acima, com `k` fixo e arbitrário,
não é evidência contra o k×ATR nem a favor dele.

**Isto é recomendação escrita, não commit.** `autotrader.py`, `simulador.py`, `db.py` e `api.py`
estão em produção desde hoje e **não** são território do `T-EDGE`.

---

## 8. Quem assina

O `[P1-10]` tem a label **`toca-risco`**. Pela §9.8 do `PLANO-EXECUCAO-2026-08-20.md`, card com
essa label **não fecha sem humano assinando**, e o auditor automático roda os portões e **para**.

* O **worker** (`T-EDGE`) implementou as políticas, escreveu as provas e recomendou. Não decide.
* A **matriz** roda a régua, cola os números e integra. Não decide.
* **O dono assina** a troca do default de saída do sistema vivo — ou assina explicitamente a
  decisão de manter o default não-validado, que é resposta igualmente boa e está escrita como tal
  na §7.2, caso 1.

E vale a regra que está no `CLAUDE.md` §2, porque ela decide o caso de dúvida: **apertar guarda
pode; afrouxar, só o dono.** Trocar a política de saída do vivo não é apertar nem afrouxar uma
guarda — é trocar a estratégia. Sobe.

---

## 9. Como reproduzir

```
python -m pesquisa.backtest_plataforma      # smoke A x B x C, ~1 min, sem veredito
python -m pesquisa.validacao politicas      # a régua, A x B x C, ~1 h
python -m pesquisa.validacao                # a política A + o contraste de funding [P2-10]
python -m pytest                            # a suíte
```

Tudo da **raiz** do repositório: `pesquisa/` é pacote e `python pesquisa/validacao.py` **não**
funciona (`pesquisa/__init__.py` explica por quê).

**Como esta rodada foi produzida, que não foi pelo comando canonico.** A matriz rodou as quatro
políticas **uma por invocação**, para que um corte no meio não levasse junto as já concluídas. Isso
abre um risco que o comando canoónico não tem: `comparar_politicas` chama `baixar_paineis()` **uma
vez** e passa o mesmo `dfs` às quatro, enquanto quatro invocações separadas chamariam
`baixar_paineis()` quatro vezes — e o nome do cache carrega a data (`pesquisa/dados.py:39`), de
modo que uma rodada que atravessa a meia-noite mediria as primeiras políticas numa janela e as
últimas em outra. A rodada começou às 23h08 de 23/08 e terminou depois da meia-noite, então o
risco era real e não hipotético.

O que foi feito: os painéis foram preparados uma vez e **serializados**, e cada invocação carregou
o mesmo arquivo — 12 moedas × 26.280 barras, janela `2023-08-24 17:00 → 2026-08-23 16:00`,
idêntica nas quatro. **A rodada inteira foi executada duas vezes e as quatro saídas conferem bit a
bit**, o que é a reprodução independente que o `seed=42` promete.

Quem quiser reproduzir pelo caminho canoônico usa `python -m pesquisa.validacao politicas`, que
não tem esse risco por construir os painéis uma única vez — ao custo de perder tudo se for
cortado.

As provas das políticas rodam **offline**, sem rede, porque o sinal é injetado (`sinal_fn`) —
trajetória conhecida → saída esperada, em `tests/test_validacao.py`.
