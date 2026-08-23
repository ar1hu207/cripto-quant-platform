# VEREDITO-M4 — a política de saída que está viva, medida pela régua corrigida

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
(cole aqui a linha "purga: ATIVA" de uma das políticas, como prova de que ligou)
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
(cole aqui o bloco COMPARACAO DE POLITICAS DE SAIDA inteiro)
```

### 3.2 O relatório completo de cada política

<!-- COLAR: os quatro blocos "=== WALK-FORWARD: ... ===" completos, um por política, cada um com
     BLOCO A, BLOCO B e a linha de veredito. São eles que sustentam a tabela acima; a tabela
     sozinha não permite auditar o motivo de cada veredito. -->

```
(cole aqui os quatro relatórios completos, na ordem A, B, C-2%, C-3xATR)
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

As provas das políticas rodam **offline**, sem rede, porque o sinal é injetado (`sinal_fn`) —
trajetória conhecida → saída esperada, em `tests/test_validacao.py`.
