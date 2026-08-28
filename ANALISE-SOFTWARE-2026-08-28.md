# Análise do software — 2026-08-28

> **Documento de continuidade.** Foi escrito no fim de uma sessão que gastou a janela de contexto
> lendo o repositório inteiro. Ele existe para que a próxima sessão **não releia tudo de novo**:
> aqui está o que foi apurado, o que foi apurado *com número*, o que é inferência, e o que ficou
> por fazer.
>
> **Origem:** o dono pediu uma revisão geral com foco em *"construir uma boa operação técnica, com
> bons sinais e bons parâmetros"*, *"uma máquina de imprimir dinheiro"*, e pediu explicitamente:
> *"o que estiver na documentação que estiver diferente do que estou te contando como meta de
> projeto, me reporte"*. A §4 é a resposta a esse pedido e é a seção mais importante do documento.
>
> **Base lida:** `api.py`, `db.py`, `simulador.py`, `signal_engine.py`, `scoring.py`,
> `autotrader.py`, `mercado.py`, `indicadores.py`, `dca.py`, `versao.py`, `logbot.py`,
> `alertas.py`, `pesquisa/` (`validacao`, `backtest_plataforma`, `dados`), `deploy/`, `NORTE.md`,
> `CLAUDE.md`, `ARQUITETURA.md`, `README.md`, `RUNBOOK-VM.md`, `CHANGELOG.md`, os vereditos
> `M4`, `M4-PRODUCAO`, `CX-1` a `CX-4`, `VARREDURA-GEOMETRIA`, `MEDICAO-ZERO-A-ZERO`,
> `INVESTIGACAO-MOTOR-2026-08-24`, e as memórias de sessão de 24 a 27/08.
>
> **Estado da árvore ao escrever:** `main` = `09cffdb`, versão `0.4.0`, worktree `wt/docs`.

---

# ⚠️ ADENDO 2026-08-28 (noite) — os dados de produção chegaram

> **Leia este bloco antes do resto do documento.** Ele corrige três afirmações erradas das seções
> abaixo e traz um achado novo que **reordena o plano da §8**. O texto original fica intacto: o que
> mudou está aqui, com o número que mudou. (Mesmo padrão do `VEREDITO-M4.md`.)
>
> **Fonte:** 9 chamadas somente-leitura ao `trading.db` da VM, 28/08 ~18:06 UTC. Nada foi alterado.

## A.1 O quadro medido

| | |
|---|---|
| Banca atual | **R$1.115,91** (+11,6% sobre R$1.000) |
| Pico de equity | **R$1.661,84** em 22/08 |
| **Drawdown do pico** | **−32,9%** |
| Trades fechados | **62** · P&L **+R$115,91** |
| Win rate | **38,7%** (24 de 62) |
| Ganho médio / perda média | +R$37,37 / −R$20,55 (razão 1,82) |
| Profit factor | **1,15** |
| Expectância | **+R$1,87** por trade |
| Taxa paga | **R$84,17 = ~42% do lucro bruto** |
| Alavancagem | média **7,69x**, máxima **20x** |

**O P&L por dia:**

| dia | n | P&L |
|---|---:|---:|
| 19/08 | 1 | −2,89 |
| 20/08 | 15 | +78,85 |
| **21/08** | **14** | **+374,86** |
| 22/08 | 6 | +34,68 |
| 23/08 | 6 | −87,57 |
| 24/08 | 5 | −88,39 |
| 25/08 | 4 | −101,55 |
| 26/08 | 5 | −54,96 |
| 27/08 | 2 | +34,28 |
| 28/08 | 4 | −71,41 |

📏 **O dia 21/08 sozinho vale 323% do resultado acumulado.** Sem ele o bot está em **−R$258,95**.
De 23/08 a 28/08 são **seis dias, −R$369,60, com um único dia positivo** (27/08, n=2).

📏 **E a qualidade caiu junto**, comparando os 47 trades de 24/08 com os 62 de agora:
win rate **44,7% → 38,7%**, profit factor **1,57 → 1,15**.

## A.2 O que eu tinha ERRADO

| § | eu disse | o medido |
|---|---|---|
| §2.1, §4.4 | o auto-trader provavelmente está desligado desde 27/08 | **`auto_trade = 1` — está LIGADO.** A memória de 27/08 estava desatualizada; foi religado entre 27 e 28/08 |
| §4.4, §8/1.1 | `exec_modo = mercado`; **ligar o post-only é a decisão de maior retorno do projeto** | **`exec_modo = post_only` — JÁ ESTÁ LIGADO.** A recomendação estava certa e **já foi executada por você**. Não é mais uma ação pendente |
| §2.2 | "18%" não bate com nada | é **+11,6%** hoje. O 18% era uma leitura anterior, no meio da queda |

**`trava_dia_em = 2026-08-28`** — a trava diária disparou **hoje**. 0 posições abertas, 0 ordens
pendentes. O bot está parado por guarda, funcionando como projetado.

## A.3 🐛 O bug do `risco_inicial`: **CONFIRMADO**

A §5.1 era um argumento dedutivo. Agora tem prova, e mais forte do que eu previa.

**Prova 1 — o stop está do lado errado.** Em **todos** os trades de saída por `trailing`, sendo
LONG, o `stop` gravado está **acima** da entrada: id 18 (+7,6%), id 24 (+8,8%), id 32 (+11,6%),
id 22 (+2,0%), id 17 (+4,3%), id 33 (+5,4%). Stop de LONG acima da entrada não é risco — é lucro
travado. Os `stop` puros estão corretos (id 35 LONG: entrada 0,691 / stop 0,6667).

**Prova 2 — excede o teto matemático.** Com `risco_por_trade = 3%`, no pico de banca o risco
máximo por trade era **R$49,86**. O trade 18 gravou **R$177,55** — **3,6× o teto**, impossível
pelo caminho do sizing.

**Prova 3 — `risco_inicial ≈ pnl`.** 177,55 vs 174,81 · 83,16 vs 81,98 · 63,47 vs 62,87 ·
55,01 vs 52,34 · 46,21 vs 45,02. **O "risco" gravado é o próprio lucro.** O denominador virou
o numerador.

**Prova 4 — o gradiente.** Risco médio por motivo: `trailing` 39,29 > `manual` 30,48 >
`stop` 23,86 > `stop-gap` 16,69. Ordena exatamente pelo tempo que o trailing teve para agir.

➡️ **`expectancia_r` e `sqn_r` estão inválidos**, e enviesados **para parecer melhores**. Nenhuma
métrica em R desta tabela pode ser usada até o fix.

## A.4 🔴 O ACHADO NOVO — e é ele que reordena tudo

O `[Q-4]` (validação prospectiva do portão de fluxo) **já tinha amostra e nunca havia sido lido**.
Saída literal:

```
grupo           n  alvo  stop  aberto    win%   ret1h%   ret4h%  ret24h%   fluxo%
passou       1367   644   683      40    48.5   -0.111   -0.125    -0.31     47.4
rejeitado    1229   564   625      40    47.4   -0.134    -0.16    -0.295    52.6
delta win: +1.1 p.p.   z=0.55  p=0.5823
veredito: o portao ainda nao mostrou valor
```

**Duas conclusões, e a segunda é a importante:**

**(a) O portão de fluxo é ruído.** +1,1 p.p. com **p = 0,58**. E ele descarta **38,9% de todos os
sinais** (1.461 de 3.752). Uma guarda que joga fora 4 de cada 10 sinais sem valor medido.

**(b) 🔴 O retorno direcional dos sinais é NEGATIVO — nos dois grupos, nos três horizontes.**
São **seis medições independentes, todas negativas**, sobre **2.596 sinais** com desfecho marcado:
−0,111% / −0,125% / −0,31% no grupo que passou, e −0,134% / −0,16% / −0,295% no rejeitado.
Desfecho binário: **1.208 alvo contra 1.308 stop = 48,0%** de acerto num contrafactual de 1R
simétrico, onde o nulo é 50%.

⚠️ **Honestidade sobre a força disso:** os sinais são correlacionados (24 moedas que andam juntas,
mesma hora) e o relatório não publica IC — então é **indício forte, não prova**. E o empate na
mesma vela conta como stop por convenção, o que puxa o win% um pouco para baixo. **Mas os retornos
médios não sofrem dessa convenção, e são negativos em todas as seis leituras.**

**O que isso significa:** o problema **não é o custo, não é a política de saída e não é o
dimensionamento**. Esses três mexem na variância e no quanto se perde — não no sinal apontar para o
lado certo. **O gargalo é a ENTRADA.** Três evidências independentes agora dizem a mesma coisa:
3 anos de walk-forward (`SEM EVIDÊNCIA`), 10 dias de operação ao vivo (−32,9% do pico), e 2.596
sinais prospectivos com retorno médio negativo.

📏 **E há a confirmação prática:** o post-only **já está ligado**, e o bot perdeu **R$71,41 em 4
trades** no dia seguinte. n=4 não prova nada sozinho — mas fecha o argumento de que **baratear a
execução não conserta um sinal que aponta para o lado errado**.

## A.5 O funil, que ninguém tinha olhado

| etapa | n | % |
|---|---:|---:|
| sinais gerados | 3.752 | 100% |
| rejeitados pelo portão de fluxo | 1.461 | 38,9% |
| **expirados sem virar nada** | **1.966** | **52,4%** |
| pulados | 258 | 6,9% |
| **confirmados (viraram trade)** | **63** | **1,7%** |

**Mais da metade dos sinais morre de velhice.** A janela de vida é de 4 velas do próprio TF e o
auto-trader só opera sinal com até 12 min. O sistema gera 3.752 oportunidades e executa 63.

## A.6 Um dado de engenharia que confirma a §5.3

📏 **21 dos 62 trades (34%) saíram por `gap`** — o preço passou do stop entre dois polls do worker.
`stop-gap` sozinho: n=18, −R$336,34 (o maior bloco de perda em número). Isso é evidência direta de
que o ciclo de 15s **não está acompanhando o preço**, e reforça a hipótese da §5.3 (o scan alonga o
ciclo para ~40-50s). ⚠️ Não conclua que o gap *custa* mais: a perda média do `stop-gap` (−18,69) é
**menor** que a do `stop` puro (−25,29). O que está provado é a **latência**, não o custo dela.

## A.7 O que isso muda na §8 (o plano)

**A Onda 1 encolheu** — o item mais valioso dela (post-only) já está feito. Sobram o fix do
`risco_inicial` (agora confirmado), o `avaliar_saida` fora do laço quente, e a instrumentação do
ciclo.

**A ordem das ondas inverte.** O plano original tratava sinal na Onda 4. Com a §A.4, **a entrada
passa a ser a Onda 1**. Risco de carteira (Onda 2) continua valendo, mas muda de papel: deixa de
ser "ganhar mais" e passa a ser "sobreviver enquanto se procura sinal".

**Uma coisa que NÃO se deve fazer, e é contraintuitiva:** desligar o portão de fluxo por ele ser
ruído. Ele é inútil, mas **remover um filtro inútil de um sinal de expectativa negativa faz o bot
operar mais e perder mais rápido**. Deixe-o ligado até existir sinal com edge; o que muda é parar
de acreditar que ele protege alguma coisa.

**E o que continua verdadeiro:** é dinheiro fictício. Manter o bot rodando **não custa nada e gera
dado** — a tabela `sinais` com desfecho marcado é exatamente a matéria-prima da §7.3. Ele só não
vai dar lucro na forma atual.

## A.8 O que ficou sem resposta

- **Quando o `auto_trade` foi religado** — não há registro histórico de mudança de config no banco.
  💭 Vale criar uma tabela de auditoria de config (barato, e responde isso para sempre).
- **`/status` devolveu 401** (`DASH_PASS` setado). Os contadores de `caps_geometria`, `caps_tamanho`
  e saúde do scan não foram coletados.
- **`git status` na VM falhou** (`dubious ownership`) — o fix é escrita de config e a sessão,
  corretamente, não executou. O commit veio do `/health` e é confiável; o que não sei é se a
  árvore tem modificação não commitada.
- **A duração real do `scan()` não foi medida** — a §5.3 continua sendo hipótese.

---

## 0. Aviso de navegação para a próxima sessão

⚠️ **`C:\Users\aboni\Pesquisas\1` está 123 commits atrás**, na branch `feat/m6-design-system-cmc`.
O `README.md` de lá ainda diz *"o objetivo do projeto não é um robô lucrativo"* — texto que já foi
corrigido na `main` em 26/08. **A `main` está em `C:\Users\aboni\Pesquisas\wt\docs`.** Comece por lá.

Legenda usada abaixo:
- 📏 **MEDIDO** — tem número, veio de rodada versionada ou do banco de produção.
- 🔍 **ACHADO NESTA REVISÃO** — encontrado lendo o código agora; ainda **não** foi confirmado por
  execução. Precisa de prova antes de virar verdade.
- 💭 **INFERÊNCIA** — raciocínio meu, coerente com o código, sem medição.

---

## 1. Resposta curta à pergunta "o que está acontecendo com o bot"

**Não houve deterioração. Houve um dia bom e o resto é ruído em volta dele.**

Os números da produção, do `INVESTIGACAO-MOTOR-2026-08-24.md` §0 (47 trades fechados, 19→24/08,
lidos do `trading.db` da VM):

| dia | trades | P&L |
|---|---:|---:|
| 19/08 | 1 | −2,89 |
| 20/08 | 15 | +78,85 |
| **21/08** | **14** | **+374,86** |
| 22/08 | 6 | +34,68 |
| 23/08 | 6 | −87,57 |
| 24/08 | 5 | −88,39 |
| **total** | **47** | **+309,54** |

📏 **Tire o dia 21/08 e o bot está em −65,32.** Um dia de seis vale **121%** do lucro acumulado.
Isso não é "estava indo bem e piorou" — é uma cauda única carregando a série inteira, que é
exatamente a assinatura estatística que a régua do projeto já detecta e chama de *concentração*
(`maior fold` de 0,56 a 1,03 nas rodadas de walk-forward).

**A aritmética do "não dá para concluir nada":**
- expectância = +309,54 / 47 = **+6,58 por trade**
- ganho médio +40,45 · perda média −20,77 · acerto 44,7% · profit factor 1,57
- 💭 desvio-padrão por trade estimado da mistura ≈ **30**
- t ≈ 6,58 / 30 × √47 ≈ **1,50** → p ≈ 0,07 unilateral

Ou seja: **mesmo o resultado positivo não se distingue de sorte com n=47.** E o teste acima é o
mais generoso possível — trata trades correlacionados como independentes, coisa que a régua do
projeto se recusa a fazer de propósito.

**A mecânica de por que sobe rápido e devolve rápido** (💭, mas cada peça está no código):

1. **3% de risco por trade × posições correlacionadas.** São 24 altcoins que andam juntas com o
   BTC. Cinco posições LONG não são cinco apostas — são **uma aposta com cinco vezes o tamanho**.
   O teto agregado (`risco_aberto_max = 10%`) barra na quarta posição, então na prática o sistema
   arrisca ~9% do equity numa direção só, por vez.
2. **Alavancagem 2x→20x proporcional à convicção**, e a convicção **nunca foi provada preditiva**.
   O próprio código admite: `autotrader.py:115` — *"AVISO: escalar pra cima na convicção assume que
   convicção prevê acerto — NÃO comprovado (DSR~0)"*. O sistema aloca **mais** risco onde tem
   **menos** evidência.
3. **O trailing só arma em +2% de preço.** A 20x isso é **+40% de ROE sem nenhuma proteção**.
   📏 `INVESTIGACAO-MOTOR` §8: **19 dos 20 trades que foram de lucro a prejuízo nunca tiveram o
   trailing armado.** É literalmente o mecanismo de "devolver o lucro", medido.
4. **A taxa.** 📏 R$66 em 48 trades = **18,5% do lucro bruto** em produção; e 📏 o `[Q-15]` mediu
   que num backtest de 3 anos a taxa taker come **36%** do lucro bruto.

**Conclusão da §1:** o problema não é que o bot piorou. É que ele nunca teve edge demonstrado, e a
configuração de risco amplifica a variância a ponto de o resultado de uma semana não significar
nada — nem quando é +60%, nem quando é +18%.

---

## 2. ~~⚠️ Três coisas que preciso confirmar~~ → **RESPONDIDAS em 28/08, ver ADENDO §A.2**

> ✅ **As três foram medidas.** (1) O auto-trader está **LIGADO**. (2) A banca é **R$1.115,91
> (+11,6%)**, e o drawdown do pico é **−32,9%**. (3) Sim, o perfil `experimento` continua ativo —
> e agora você sabe. O texto abaixo fica como registro do que era dúvida.

Estão aqui em primeiro lugar porque **mudam o diagnóstico**.

1. **O auto-trader está ligado?** A memória de 27/08 registra que o deploy congelou
   `auto_trade=0` e que a sessão **não religou** ("o dono estava indo dormir"). Se ele continua
   desligado, os 18% que você está vendo são de **antes** de 27/08 e o bot não opera há dois dias.
   Comando de conferência na §10.
2. **Os 18% e os 60% são sobre qual base?** Banca inicial = R$1.000. Pico de equity medido = 
   R$1.661,84 em 22/08 (**+66%**), e a banca fechou 25/08 em R$1.289,84 (**+29%**). "18%" não
   bate com nenhum dos dois — pode ser depois de mais perdas, ou pode ser outra leitura. Preciso
   do banco atual.
3. **Você sabia que o perfil de risco vivo se chama `experimento` e foi calibrado para PERDER
   mais rápido?** Ver §4.1. É a divergência mais cara que encontrei.

---

## 3. O que o projeto já mediu (para não remedir)

Isto é dinheiro já gasto. **Não re-rode nada disto sem motivo novo.**

| medição | resultado |
|---|---|
| `VEREDITO-M4` + `[Q-12]` | as **4 políticas de saída** saem `SEM EVIDÊNCIA DE EDGE` sob a config de produção. A que roda ao vivo (C trailing 2%) dá Sharpe 0,976, IC95% inclui 0 |
| `[Q-15]` | **a taxa decide o veredito**: a 0,05%/lado → sem evidência; a 0% → edge sobrevive. O sinal está a ~0,03%/lado de passar nos três portões |
| `[CX-1]` | post-only com fill modelado: Sharpe 0,955 → 1,25 (**sob custo otimista**) |
| `[CX-2]` | maker + portão de open interest **piorou os 4 níveis**. Overfitting demonstrado: 20 escolhas de fold, zero vezes escolheu "desligado" |
| `[CX-3]` | **o ganho é a TAXA, não o preço.** Esperar o preço e mandar a mercado = 0,960 vs 0,955. Não vale nada |
| `[CX-4]` | round-trip realista (maker entra, taker sai): sobrevive **61%** do ganho → Sharpe **1,134**. Continuam **2 portões reprovados** |
| `[Q-8]`/`[Q-9]`/`[Q-11]` | as 3 tentativas de consertar a saída (k×ATR, piso de stop, zero-a-zero) **não passaram** |
| `[Q-17]` | portão de OI corta 40% dos trades perdendo 22% do P&L — mas `maior fold = 1,0`, reprovado por concentração |

**A leitura honesta disso tudo:** o motor técnico atual (EMA/ADX/Donchian/RSI + confluência) foi
espremido de todos os lados e não entrega edge. **Não é o código — é o terreno.** Confluência de
indicador sobre candle público é a coisa mais disputada que existe: sem informação, sem
velocidade, sem prêmio estrutural.

---

## 4. 🔴 Divergências entre a documentação/código e a sua meta

**Esta é a seção que você pediu.** Ordenada por quanto custa.

### 4.1 O perfil de risco em produção foi escolhido para o bot PERDER mais rápido

Está escrito, com todas as letras, em `api.py` → `CONFIG_RACIONAL["risco_por_trade"]`:

> *"VIVO 3%. A base põe 0,5-1% como conservador (…) e chama >3% de território de ruína. **MANTIDO
> AGRESSIVO de propósito: o auto-trader existe para tornar visível a deriva por taxa+funding de uma
> estratégia sem edge, e a 0,5% por trade essa deriva leva meses para aparecer no equity — o
> experimento demoraria mais que a paciência de quem o observa.**"*

E em `alavancagem_padrao`:

> *"VIVO 10x. A base mede que 'a 10x a mesma estratégia vira ruína' (…) **MANTIDO pelo mesmo motivo
> (…) é o dial que acelera o experimento, não uma aposta em edge.**"*

O perfil se chama literalmente **`experimento`** em `db.PERFIS_RISCO`, e existe um perfil
**`conservador`** ao lado (1%/trade, 2x, teto 5%) que **nunca foi ativado**.

**Impacto:** você acha que está rodando uma configuração que busca lucro. Está rodando uma
configuração cujo racional escrito é *acelerar a perda para torná-la visível*. É a causa
mecânica direta do "sobe 60%, devolve para 18%": variância deliberadamente inflada.

**Não é bug — é uma decisão antiga, registrada, que ninguém revogou quando a direção do projeto
mudou em 26/08.** É a primeira coisa a decidir.

### 4.2 O módulo que executa declara que espera perder

`autotrader.py:8-14`, docstring do módulo que abre e fecha as posições:

> *"IMPORTANTE — o objetivo do projeto e LUCRO. A confluência técnica, que e o que este auto-trader
> executa, nao mostrou edge ate hoje (…) **entao o esperado AQUI e o bot DERIVAR pra perda por
> causa de taxa + alavancagem: rodar ao vivo dentro das guardas e como se ve isso acontecer.**"*

Mesma frase no `CLAUDE.md` §"O objetivo é lucro": *"O auto-trader roda essa estratégia ao vivo
dentro de guardas **para ver o 'no edge' acontecer**"*.

A correção de 26/08 (`f267a7a`) trocou a frase *"isto não é pra ganhar dinheiro"* — mas manteve
*"o esperado é derivar pra perda"*. **A meia-correção é pior que nenhuma**: o texto agora diz que
o objetivo é lucro e, duas linhas abaixo, que a expectativa é perder.

### 4.3 O `README.md` ainda é organizado em torno do veredito negativo

Na `main`, em inglês, a **primeira seção depois do título** é *"The verdict (the most important
result so far)"*, com três linhas ❌. É o cartão de visita do repositório. O `NORTE.md` já corrige
o enquadramento ("`SEM EVIDÊNCIA` é o piso da busca, não a meta"), mas o README não foi
reorganizado — só emendado.

### 4.4 ~~A melhoria mais barata já medida está DESLIGADA~~ → **JÁ FOI LIGADA. Ver ADENDO §A.2**

> ❌ **Esta seção estava ERRADA.** A medição de 28/08 mostra `exec_modo = post_only` em produção.
> A recomendação estava certa e **você já a executou**. Não é ação pendente. E o §A.4 acrescenta o
> que isso ensinou: o bot perdeu R$71,41 em 4 trades no dia seguinte — **execução barata não
> conserta sinal ruim**.

📏 `exec_modo = "mercado"` (taker) é o default vivo. O `[EX-1]` (post-only) está implementado,
testado, deployado em produção desde 27/08 — **e nunca foi ligado**. O `[CX-4]` mede que vale
**+R$840 em 3 anos sobre o mesmo sinal**, sem depender de achar sinal novo (Sharpe 0,955 → 1,134).

Custa **um `POST /config`**. É a decisão de maior retorno por esforço no projeto inteiro.

⚠️ Ressalva honesta que o próprio veredito registra: **backtest não responde se a Binance preenche
`postOnly` nesses instantes**, nem o que fazer com os ~12% de sinais que não enchem. Só ligar no
paper responde. Ligar é, portanto, **também uma medição**.

### 4.5 O projeto está sem próximo passo definido

`NORTE.md`, última linha: *"A ordem entre eles é decisão do dono e **ainda não foi tomada**. Não
invente uma."* Quatro marcos propostos, nenhum escolhido. Isso está travando o trabalho.

### 4.6 Divergências menores, mas registradas

- **A `BASE-CONHECIMENTO-TRADING.md` contradiz 4 parâmetros vivos** (risco, alavancagem, teto,
  lev máx). O `[Q-3]` documentou a contradição e criou os dois perfis, mas não a resolveu.
- **`auto_max_posicoes = 5` é config morta.** Com 3%/trade, o teto de risco agregado (10%) barra
  na **quarta** posição. Os 5 slots nunca acontecem. Documentado em `CONFIG_RACIONAL`.
- **`reversao_ativa = 0`** — metade do `scoring.py` (`pontuar_reversao`) não roda ao vivo.
- **`web/` e `DESIGN.md`** estão numa reforma visual (transposição CoinMarketCap night) que é
  trabalho de front, não de motor. Vale saber que existe e está inacabado.

---

## 5. 🐛 Defeitos encontrados no código

### 5.1 📏 **CONFIRMADO EM PRODUÇÃO — `trades.risco_inicial` grava o stop TRAILADO**

> ✅ **Deixou de ser hipótese em 28/08.** Quatro provas independentes no ADENDO §A.3, sobre os 62
> trades reais. O maior valor gravado é **R$177,55** — 3,6× o teto matemático de R$49,86 — e nos
> trades de `trailing` o "risco" é numericamente **igual ao lucro**. O argumento dedutivo abaixo
> estava certo, e o outlier real é ainda pior que o R$83,16 que o `[P2-39]` registrou.

**Onde:** `simulador.py`, função `fechar()`:
```python
risco_ini = _risco_posicao(pos["valor_reais"], pos["alavancagem"], pos["entrada"], pos["stop"])
```
`pos` vem de `SELECT * FROM posicoes` no início de `fechar()`. E a coluna `posicoes.stop` **é
reescrita pelo trailing a cada ciclo** (`_marcar_uma` → `UPDATE posicoes SET ... stop=?`).

**Consequência:** para todo trade que trailou para o lucro, `stop > entrada` (LONG), e o "risco
inicial" gravado é na verdade **a distância do lucro travado**. A coluna mede outra coisa, com o
nome errado.

**O que isso corrompe:** `db.metricas()` calcula
`rmults = [t["pnl_reais"] / t["risco_inicial"] ...]` → **`expectancia_r` e `sqn_r` estão errados
exatamente nos trades que mais importam** (os vencedores que correram). O R-múltiplo é a métrica
que você usaria para decidir se o sistema tem edge por trade — e ela está medindo um denominador
que se move.

**Prova aritmética de que o defeito existe** (💭, mas é dedutivo e fecha):
o comentário do `[P2-39]` em `autotrader.py` registra `risco_inicial` medido em produção entre
**R$0,14 e R$83,16** e atribui a variação ao cap de tamanho. **O cap não pode explicar o R$83.**
Pelo caminho do sizing, `risco = min(risco_rs, cap × denom) ≤ risco_rs`, e `risco_rs = banca × 3%`
≈ R$39 (≈R$50 no pico de banca). O cap **só reduz**, nunca aumenta. Portanto valores acima de
~R$39 **não podem vir do sizing** — só podem vir do stop ter se movido. O outlier de R$83 é
provavelmente este bug, e não o cap.

**Quebra de paridade junto:** no backtest (`backtest_plataforma.py`) o risco é fixado na entrada
(`pos["risco"] = abs(e - stop0)`) e nunca se move. Então **R-múltiplo do backtest e R-múltiplo do
vivo não são comparáveis** — e a paridade backtest↔live é o valor central declarado do projeto.

**Correção proposta:** gravar `risco_inicial` no momento de `abrir()`/`_abrir_da_ordem()` (coluna
nova em `posicoes`, ex. `risco_ini`), e `fechar()` apenas copiar. Nunca recalcular a partir de um
campo mutável. **Antes de corrigir:** decidir o que fazer com as ~50 linhas já gravadas — o padrão
desta casa (`[P2-40]`) é **não reescrever histórico**, e sim criar coluna nova com o nome certo.

### 5.2 🔍 **ALTO — o gestor de saída é calculado a cada 15s e o bot NUNCA age sobre ele**

**Onde:** `autotrader.auto_executar()`:
```python
if _verdade(cfg.get("auto_fechar_saida", "1")) and not _verdade(cfg.get("trailing_ativo", "1")) and saidas:
```
Com o default vivo `trailing_ativo=1`, `not _verdade("1")` é `False` → **o bloco inteiro nunca
executa**. É intencional e está comentado ("com trailing, quem fecha o vencedor é o trailing").

**O problema não é a lógica — é o custo.** No `api.worker()`, a cada ciclo de 15s:
```python
_saidas["v"] = [r for r in (signal_engine.avaliar_saida(p) for p in abertas) if r]
```
e cada `avaliar_saida` faz **3 chamadas de rede**: `fetch_ohlcv(limit=120)` + `fetch_order_book(100)`
+ `fetch_trades(200)` (via `mercado.book`).

💭 Com 4 posições abertas: **12 chamadas de rede a cada 15 segundos = ~48/min**, para alimentar
**apenas um widget do painel**. É provavelmente a operação mais cara do loop inteiro, e ela não
influencia nenhuma decisão na configuração vigente.

**Correção proposta:** calcular `_saidas` sob demanda (na rota `/saidas`) com cache curto, ou
condicionar ao `auto_fechar_saida and not trailing_ativo`. Ganho imediato de latência do ciclo.

### 5.3 🔍 **MÉDIO — o ciclo de 15s vira ~40-50s quando o scan roda**

**Onde:** `api.worker()`. O `sleep(15)` está no fim; o scan roda **dentro** do mesmo laço, depois
do bloco de marcação:
```python
if _scan_devido():
    signal_engine.scan()
...
time.sleep(POLL_ATUALIZAR)
```
💭 O `scan()` faz **24 pares × 3 TFs = 72 chamadas `fetch_ohlcv(limit=200)`**, sequenciais, com
`enableRateLimit`, de uma VM em South Africa North. Estimativa de 25-35s. Mais `mercado.book()` por
sinal confirmado e até 6 `fetch_ohlcv` do `marcar_desfechos`.

**Consequência:** uma vez por minuto, as posições abertas ficam **~40-50 segundos sem checagem de
stop, trailing e liquidação**, em vez de 15. O comentário do `[P2-15]` no código diz que o scan foi
posto **depois** para não atrasar a marcação — mas ele não atrasa a marcação *deste* ciclo, atrasa a
do *próximo*. Meio problema resolvido.

**Não medido.** Primeiro passo é instrumentar: cronometrar `scan()` e o ciclo, publicar no
`/status`. **Não conserte antes de medir.**

### 5.4 🔍 **MÉDIO — o gestor de saída usa o TF errado**

`signal_engine.avaliar_saida()` sempre lê `cfg.get("timeframe", "15m")` — o TF *primário*. Mas o
scanner varre `timeframes = "5m,15m,1h"`. Então um sinal nascido em **1h** é gerido por um gestor de
saída que olha **15m**. Entrada e saída leem horizontes diferentes.

### 5.5 🔍 **BAIXO — `_pnl()` abre o banco dentro do laço de marcação**

`simulador._pnl()` chama `db.get_config()` (abre conexão, `PRAGMA`, `SELECT *`) a cada avaliação —
e ele é chamado por posição, por ciclo, e de novo em `fechar()`. Custo pequeno, mas é I/O de banco
num caminho quente que roda 4× por minuto por posição.

### 5.6 🔍 **BAIXO — `preco_ao_vivo` é 1 request por posição**

`_marcar_uma` faz `fetch_ticker(ativo)` individual. `mercado.precos()` já existe, faz `fetch_tickers`
em **1 request para a lista toda** e tem cache de 5s — e não é usado pelo caminho de marcação.

---

## 6. Gargalos do sinal e dos parâmetros

Aqui está o coração do "bons sinais com bons parâmetros".

### 6.1 A convicção é uma soma arbitrária — e ela dimensiona o risco

`scoring.pontuar()` monta o score assim:

| fator | peso |
|---|---|
| ADX ≥ 25 | 5 + até 35 |
| distância EMA20-EMA50 | até 10 |
| rompimento Donchian 20 | 22 |
| RSI em faixa | 18 |
| volume > 1,2× média | 15 |

💭 **Nenhum desses pesos foi ajustado por dado.** São números escolhidos à mão. E esse número
inventado (0-100) alimenta `autotrader._alavancagem()`, que o converte **linearmente em alavancagem
de 2x a 20x**. Ou seja: **uma heurística não validada decide quanto dinheiro é apostado.**

O card `[Q-13]` ("a convicção prevê acerto?") existe justamente para medir isso e **está aberto**.
Até ele fechar, o defensável é **alavancagem fixa e baixa**.

### 6.2 A direção vem de uma coisa só

`direcao = 1 if er > el else -1` — EMA20 vs EMA50, e nada mais. Todo o resto do score é *força*, não
direção. **O bot é um cruzamento de médias com filtros de qualidade.** Isso é o estado da arte de
1980 e é o que 100% dos participantes do mercado já veem.

### 6.3 O portão de fluxo tem descasamento de horizonte grave

`mercado.book()` calcula `fluxo_comprador` sobre os **últimos 200 trades** — isso é uma janela de
**segundos** em BTC/USDT. Esse número é usado como portão binário (`> 50%` para LONG) sobre um sinal
de candle de **1 hora**.

💭 Dois problemas somados: (a) horizonte errado por 3 ordens de grandeza; (b) o corte em 50% é
exatamente o ponto neutro, então **metade das rejeições é ruído amostral**. O card `[Q-4]` já montou
a instrumentação para medir isso prospectivamente (grupo "passou" × grupo "rejeitado", com desfecho
hipotético) — **rodar `python signal_engine.py --relatorio` na VM é uma medição que já existe e
provavelmente já tem amostra.** É barato e responde se o portão vale.

### 6.4 Zero informação fora do candle entra na decisão

`mercado.py` **já coleta**: funding por moeda, ranking de funding anualizado, Fear & Greed, breadth
(% de altcoins subindo), paredes do book, split dinheiro grande/pequeno, zonas de liquidez. 
📏 O `NORTE.md` confirma: **só o `fluxo_comprador` entra na decisão. Todo o resto é display puro.**

Essa é a maior oportunidade não explorada do sistema, e ela é **barata** — o coletor existe.

### 6.5 Os três timeframes não conversam

O scanner varre 5m, 15m e 1h **de forma independente**. Não há hierarquia (ex.: direção definida no
4h, gatilho no 15m). O resultado é que o mesmo ativo pode gerar sinais contraditórios em TFs
diferentes no mesmo minuto, e o dedupe é por `(ativo, tf, tipo)` — ou seja, **não deduplica entre
TFs**. O `auto_max_posicoes` e o `vistos` do auto-trader limitam a 1 entrada por ativo por ciclo,
mas nada impede LONG em 5m e SHORT em 1h em ciclos seguidos.

### 6.6 O trailing e o stop estão em unidades diferentes

📏 Já documentado no `INVESTIGACAO-MOTOR` §1 e listado no `CHANGELOG` como **defeito aberto**:
stop em `3×ATR` (unidade de volatilidade), trailing em `2% de preço` (unidade fixa). Existe uma
faixa de `sd` (1-2%) em que **o trade não tem ramo vencedor possível**. E o gatilho do trailing em
% de preço vira, em ROE, um limiar que **escala com a alavancagem**: 2% de preço = 4% de ROE a 2x e
**40% a 20x**.

As três tentativas de conserto (`Q-8` k×ATR, `Q-9` piso de stop, `Q-11` zero-a-zero) **reprovaram na
régua**. 💭 Minha leitura: elas falharam porque atacavam a *saída* de um sinal que não tem edge na
*entrada*. Consertar a unidade continua sendo certo do ponto de vista de engenharia — mas não vai
criar edge sozinho.

---

## 7. Engenharia e arquitetura

### 7.1 O que está genuinamente bem feito (não quebrar)

Isto precisa estar escrito, porque o resto da seção é crítica:

- **Guardas de risco** — trava diária sticky, teto de risco-até-o-stop, teto de margem, claim
  atômico do sinal, lock contra TOCTOU, geometria stop×liquidação, ordem pendente contando nos
  tetos. É a melhor parte do sistema, de longe.
- **Paridade backtest↔live** via `scoring.py` compartilhado. É a decisão de arquitetura mais
  valiosa do projeto.
- **A régua** (`pesquisa/validacao.py`, 1.759 linhas): walk-forward com purga, Reality Check,
  Hansen SPA, PSR/DSR, bootstrap de bloco, FDR, controle nulo calibrado, e — o mais raro —
  **um portão de poder que responde `INCONCLUSIVO` quando o instrumento não consegue decidir**.
  Isso é melhor do que a maioria das mesas institucionais tem.
- **Ausência ≠ zero**: `funding` NULL, `pnl_reais` NULL fora das razões, `/health` devolvendo
  `None` em vez de `"desconhecido"`. Disciplina rara.
- **594-605 testes** que rodam sem rede e sem tocar o banco de produção.
- **Segurança**: sem bandeira para desligar a auth, vendor commitado em vez de CDN, throttle que
  só conta credencial errada, `/docs` fechado em produção.
- **Deploy com portões** que aborta e não religa o `auto_trade` sozinho.

### 7.2 O gargalo estrutural: polling REST sem cache

💭 Por ciclo de 60s o sistema faz, estimado:

| operação | chamadas |
|---|---|
| scan (24 pares × 3 TFs × `fetch_ohlcv(200)`) | 72 |
| `mercado.book` por sinal de tendência confirmado | N |
| `marcar_desfechos` | até 6 |
| marcação de posições (`fetch_ticker` × 4 ciclos × N posições) | ~16 |
| `avaliar_saida` (3 chamadas × N posições × 4 ciclos) | ~48 |

**~140+ requisições REST por minuto**, e o scan **rebaixa 200 candles inteiros toda vez** quando
1-2 candles novos bastariam. 💭 Desperdício estimado em ~99% da banda do scan.

Não estoura o rate limit da Binance, mas: gasta franquia de saída da Azure (já é preocupação
declarada no `CLAUDE.md` §2), alonga o ciclo (§5.3), e **impede aumentar o número de pares** — que é
justamente o que "enxergar o cenário" pediria.

**Correções, em ordem de custo:**
1. **Cache incremental de candles** (tabela nova ou Parquet): baixar só o delta desde o último
   candle fechado. Barato, resolve 90% do desperdício, não muda arquitetura.
2. **Websocket** para preço/book/trades (`ccxt.pro`, `python-binance`, ou
   `unicorn-binance-websocket-api`). Elimina o polling de marcação e dá o book em tempo real de
   graça. Custo médio, ganho grande.
3. **Separar o worker do processo da API** (processo próprio + fila). Hoje o worker é uma thread
   dentro do `uvicorn`, competindo pelo GIL com as requisições do painel (que faz poll de 3s).

### 7.3 O sistema não guarda o que VIU — só o que FEZ

💭 **Este é, na minha opinião, o gargalo mais importante para o futuro do projeto.**

O banco tem `sinais`, `posicoes`, `trades`, `equity`, `ordens`, `config`, `dca`. **Não há tabela de
candles, nem de book, nem de features.** Então:

- Nenhuma pesquisa pode ser feita sobre **o estado do mercado no momento da decisão** — só sobre o
  resultado dela.
- Qualquer ideia de ML (meta-labeling, filtro de regime, combinação de sinais) precisa de features
  históricas alinhadas ao instante do sinal — e elas **não existem e não podem ser reconstruídas**
  (book e fluxo taker não têm histórico público).
- O `[Q-4]` já provou o padrão certo: `sinais` guarda `fluxo_comprador`, `vela_ms`, `desfecho`,
  `preco_1h/4h/24h`. **Isso é uma máquina de coleta de labels prospectivos que já funciona.**

**Proposta:** estender esse padrão. Gravar, no instante de cada sinal (passou ou não), um snapshot
de features: funding, OI, long/short ratio, breadth, F&G, pressão do book, paredes, CVD, ADX/RSI/ATR
de 3 TFs. Custa quase nada (os coletores existem) e, em 60-90 dias, cria o dataset que hoje não
existe e que **destrava tudo que vem depois**.

### 7.4 Outros pontos de arquitetura

- **Timestamps naive em hora de São Paulo.** É convenção declarada e consistente, mas é uma bomba
  para cruzar com qualquer dado de exchange (UTC). Já mordeu uma vez (o `astimezone()` no funding).
  💭 Não mexer agora — mas qualquer tabela nova deve nascer em **UTC epoch ms**.
- **SQLite numa VM de 1 GiB** com RAM em 85-88%. O `[P2-5]` (resize) está parado esperando decisão
  de gasto. Se entrar coleta de features, isso deixa de ser opcional.
- **`MemoryMax=900M` numa VM de 892 MiB** — o teto está acima da RAM física, então a guarda nunca
  dispara. Uma linha, mas muda comportamento sob pressão; está esperando sua palavra.
- **`legado/`** tem 30+ arquivos mortos. Está bem sinalizado (`legado/README.md`), não é problema.
- **Sem métricas/observabilidade** além do `/status` e do arquivo de log. Há um MCP de Grafana
  disponível nesta máquina — 💭 vale considerar exportar métricas do worker.

---

## 8. Plano proposto

**Nada aqui foi executado.** É proposta, e a ordem é minha recomendação — a decisão é sua.

### Onda 0 — Reconciliar a realidade (antes de qualquer código)

| # | ação | custo |
|---|---|---|
| 0.1 | Puxar o `trading.db` da VM e recalcular: equity atual, curva, trades por dia, expectância com IC, R-múltiplos, drawdown | 1 comando |
| 0.2 | Confirmar se `auto_trade` está ligado e desde quando | mesmo comando |
| 0.3 | Rodar `python signal_engine.py --relatorio` na VM — o `[Q-4]` já mede se o portão de fluxo vale | 1 comando |
| 0.4 | **Decidir o perfil de risco** (§4.1): continua `experimento` ou vai para `conservador`? | sua decisão |
| 0.5 | **Decidir a ordem dos marcos** do `NORTE.md` (§4.5) | sua decisão |

### Onda 1 — Parar de sangrar (barato, medido, alto retorno)

| # | ação | por quê |
|---|---|---|
| 1.1 | **Ligar `exec_modo = post_only`** | 📏 +R$840/3 anos medido. É `POST /config`. E ligar É a medição que falta (§4.4) |
| 1.2 | Corrigir `risco_inicial` (§5.1) | sem isso o R-múltiplo mente, e ele é a métrica de decisão |
| 1.3 | Tirar `avaliar_saida` do laço quente (§5.2) | ~48 requisições/min que não decidem nada |
| 1.4 | Instrumentar a duração de `scan()` e do ciclo (§5.3) | medir antes de consertar |
| 1.5 | Alinhar as declarações de propósito (§4.2, §4.3) | um agente novo lê "espera-se perder" e opera contra você |

### Onda 2 — Risco de carteira (é aqui que mora o "não devolver o lucro")

| # | ação |
|---|---|
| 2.1 | **Alavancagem fixa e baixa** enquanto o `[Q-13]` não provar que convicção prevê acerto |
| 2.2 | **Exposição direcional líquida** como guarda nova: somar o beta das posições, não contá-las. 5 LONGs em altcoin ≠ 5 apostas |
| 2.3 | **Vol targeting**: risco por trade proporcional ao inverso da volatilidade recente, em vez de 3% fixo |
| 2.4 | Trailing em **R** ou em **ATR** (mesma unidade do stop), fechando o defeito aberto da §6.6 |
| 2.5 | Circuit breaker **semanal**, além do diário |

### Onda 3 — Coleta de informação (o que destrava o futuro)

| # | ação |
|---|---|
| 3.1 | **Tabela de features por sinal** (§7.3). Barato, e é pré-requisito de tudo em ML |
| 3.2 | **Trazer para a decisão o que já é coletado**: funding extremo, breadth, OI — um por vez, cada um medido pela régua |
| 3.3 | **Dados históricos longos**: `data.binance.vision` serve aggTrades, métricas de OI e long/short ratio com **anos** de histórico, gratuito. 💭 Isso derruba o muro documentado no `NORTE.md` ("a Binance serve só ~30 dias") — aquele limite é do endpoint REST, não do dump. **Verificar isto é a primeira tarefa da onda** |
| 3.4 | Notícias (`N-1`): CryptoPanic / RSS / GDELT + classificação por LLM |

### Onda 4 — Sinal novo (só depois que houver dado)

| # | ação |
|---|---|
| 4.1 | **Meta-labeling** (López de Prado): manter o sinal atual como primário e treinar um modelo secundário que decide **se** opera. É literalmente o "menos trades, mais certos" que você pediu, e é a técnica com melhor razão evidência/esforço |
| 4.2 | **Filtro de regime**: só operar tendência quando o regime é de tendência (variance ratio / Hurst / ADX do TF superior) |
| 4.3 | **Hierarquia de timeframes**: direção no 4h, gatilho no 15m |
| 4.4 | **Swing (`SW-1`)**: regime 1d/4h, stop largo, alavancagem 1-2x. Menos trades = menos taxa, e foge da faixa doente da §6.6 |
| 4.5 | Substituir o portão binário de fluxo por **CVD / order-flow imbalance** com magnitude e horizonte coerentes (§6.3) |

### Onda 5 — Engenharia

| # | ação |
|---|---|
| 5.1 | Cache incremental de candles |
| 5.2 | Websocket para preço/book/trades |
| 5.3 | Worker em processo separado da API |
| 5.4 | Avaliar migrar para/aprender de **freqtrade**, **nautilus_trader**, **jesse**, **hummingbot** — 💭 pesquisa pendente (§9) |

### Onda 6 — O segundo papel do produto

A tela de **análise por criptoativo** que o `NORTE.md` pede: consolidar técnica + fluxo +
posicionamento + notícias com o *porquê* à vista. Hoje o painel só mostra sinal e posição, que é
metade da direção declarada.

---

## 9. ⏳ O que ficou faltando nesta análise

**Esta seção é o "de onde retomar".**

### 9.1 ~~Não executado~~ → **FEITO em 28/08 (noite). Resultados no ADENDO**

- [x] **Dados de produção da VM.** ✅ Coletados. ADENDO §A.1.
- [x] **`--relatorio` do portão de fluxo** (`[Q-4]`). ✅ Lido — e foi ele que produziu o achado
      mais importante de todos. ADENDO §A.4.
- [x] **Confirmar a §5.1.** ✅ **Bug CONFIRMADO** com 4 provas. ADENDO §A.3.
- [ ] **Cronometrar o `scan()`** — ⏳ **continua pendente.** A §5.3 segue sendo hipótese. Mas
      ganhou apoio indireto: 34% dos trades saem por `gap` (ADENDO §A.6).
- [ ] **Coletar o `/status`** — devolveu 401. Precisa do `DASH_PASS` para ler `caps_geometria`,
      `caps_tamanho` e a saúde do scan.
- [ ] **Tabela de auditoria de config** — não dá para saber quando o `auto_trade` foi religado.

### 9.2 Pesquisa externa — **lançada e perdida, zero entregue**

A sessão despachou **7 agentes de pesquisa em paralelo** e eles morreram com a sessão sem entregar
nada. ⚠️ **Foi isso que consumiu a janela de contexto.** Se refizer: **2 a 3 agentes por vez, não 7**.

Temas, em ordem de retorno esperado:

| # | tema | por que importa aqui |
|---|---|---|
| 1 | **Order book, fluxo e posicionamento**: OFI, CVD, book imbalance, microprice, OI, long/short ratio, funding como sinal, liquidação; horizontes e se sobrevivem à taxa | ataca §6.3 e §6.4 diretamente |
| 2 | **Risco, sizing e carteira em perps**: Kelly fracionário, vol targeting, correlação entre altcoins, faixa de alavancagem de sistemáticos profissionais, circuit breakers | é a onda 2 inteira |
| 3 | **Fontes de dados**: `data.binance.vision`, Coinglass, Tardis, CryptoQuant, CryptoPanic, GDELT — custo, histórico, granularidade | valida ou derruba a §8/3.3, que é a hipótese mais valiosa em aberto |
| 4 | **Estratégias com edge documentado em perp cripto**: TSMOM/XSMOM, funding carry, vol breakout, efeitos de horário/settlement | onde procurar sinal novo |
| 5 | **ML**: meta-labeling, triple-barrier, purged K-fold, boosting sobre features de book/OI, detecção de regime | é a onda 4 |
| 6 | **Frameworks open-source**: freqtrade/FreqAI, nautilus_trader, jesse, hummingbot, ccxt.pro | onda 5, e a decisão "migrar ou não" |
| 7 | **Experiência de varejo** (Reddit/X/fóruns): o que dá certo e o que falha em bots reais | calibra expectativa |

### 9.3 Código não lido em profundidade

- `pesquisa/validacao.py` — li a estrutura, os 100 primeiros parâmetros e o índice de funções, mas
  **não as ~1.500 linhas de implementação dos testes estatísticos**. Nada indica problema; só não
  foi auditado.
- `pesquisa/backtest_portfolio.py` (819 linhas) — **não lido**. É o backtest de carteira, e é
  relevante para a onda 2.
- `web/index.html` (130 KB) — **não lido**. É front.
- A suíte de testes (`tests/`, ~3.000 linhas) — **não lida**; só os nomes dos arquivos.
- `BASE-CONHECIMENTO-TRADING.md`, `PLANO-REPOS-QUANT.md`, `ITEM1-VALIDACAO-RIGOROSA.md`,
  `REVISAO-ITEM1.md` — **não lidos**. O `REVISAO-ITEM1.md` (35 KB) é o parecer estatístico e
  provavelmente tem conteúdo relevante.

### 9.4 Decisões suas que travam o resto

1. Perfil de risco: `experimento` ou `conservador`? (§4.1)
2. Ordem dos marcos do `NORTE.md`. (§4.5)
3. Ligar o `post_only`? (§4.4)
4. Resize da VM (custa crédito Azure) e `MemoryMax`. (§7.4)
5. O auto-trader deve ser religado? (§2.1)

---

## 10. Comandos para retomar

```bash
# A main está AQUI, não em Pesquisas/1
cd C:/Users/aboni/Pesquisas/wt/docs
git fetch origin main:main && git log --oneline -5
```

**Diagnóstico da produção** (salvar como `diag.sh` e usar `--scripts @diag.sh` — nunca inline):
```bash
cd /home/ubuntu/cripto-bot
sq() { sqlite3 -cmd '.timeout 15000' trading.db "$@"; }
systemctl is-active cripto-bot
curl -s http://127.0.0.1:8000/health
sq "SELECT 'auto='||valor FROM config WHERE chave='auto_trade';"
sq "SELECT 'exec='||valor FROM config WHERE chave='exec_modo';"
sq "SELECT 'trava='||valor FROM config WHERE chave='trava_dia_em';"
sq "SELECT 'banca='||ROUND(atual,2) FROM banca;"
sq "SELECT 'abertas='||COUNT(*) FROM posicoes WHERE status='aberta';"
sq "SELECT substr(fechado_em,1,10) dia, COUNT(*) n, ROUND(SUM(pnl_reais),2) pnl,
           SUM(pnl_reais>0) wins, ROUND(SUM(taxa),2) taxa
    FROM trades GROUP BY dia ORDER BY dia;"
sq "SELECT motivo_saida, COUNT(*), ROUND(SUM(pnl_reais),2) FROM trades GROUP BY motivo_saida;"
sq "SELECT 'equity_max='||ROUND(MAX(equity_total),2)||' min='||ROUND(MIN(equity_total),2)
    FROM equity;"
# a prova da §5.1 — risco_inicial vs geometria do stop
sq "SELECT id, motivo_saida, ROUND(risco_inicial,2), ROUND(valor_reais*alavancagem*ABS(entrada-stop)/entrada,2)
    FROM trades WHERE risco_inicial IS NOT NULL ORDER BY risco_inicial DESC LIMIT 15;"
```

```bash
az vm run-command invoke -g rg-cripto-bot -n vm-cripto-bot \
  --command-id RunShellScript --scripts @diag.sh --query "value[0].message" -o tsv
```
⚠️ Essa chamada leva **~45-60s**. Rodar com timeout generoso (a sessão anterior a perdeu por
usar 90s e ela ter passado disso).

**Medição do portão de fluxo** (já implementada, nunca lida):
```bash
cd /home/ubuntu/cripto-bot && venv/bin/python signal_engine.py --relatorio
```

**Suíte local**, antes de qualquer merge: `python -m pytest` (~3 min, da raiz).

---

## 11. A frase que resume

O sistema tem **engenharia de risco melhor que a estratégia que ele executa**. As guardas, a
paridade e a régua são de qualidade rara; o sinal é cruzamento de médias com filtros, num terreno
onde isso não paga. **O caminho para "máquina de imprimir dinheiro" não passa por ajustar os
parâmetros do que existe** — passa por (a) parar de amplificar a variância de propósito, (b)
capturar a taxa que já está medida, e (c) trazer informação que o candle não tem. Nessa ordem,
porque as duas primeiras são baratas e certas, e a terceira é cara e incerta.
