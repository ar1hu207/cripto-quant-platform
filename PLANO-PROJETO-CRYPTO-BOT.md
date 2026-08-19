# Plano de Negócio & Stack Técnica — Bot de Micro-Trade Cripto

**Data:** 2026-06-07
**Versão:** Final (consolidada + revisada pós-crítica)

Documento único consolidado a partir de nove análises especializadas e revisado para incorporar uma crítica adversarial (lacunas preenchidas, contradições reconciliadas, riscos adicionais e ressalvas realistas). Projeto: um robô de micro-trade automatizado de criptomoedas com arquitetura híbrida de três camadas — **bot mecânico** (executa), **LLM-gerente** (governa o risco em cadência lenta) e **trilhos de segurança** mecânicos (vetam e protegem). Tom deliberadamente honesto e calibrado: o objetivo primário é aprender engenharia de trading automatizado e testar, com rigor científico, se uma LLM agrega valor real à gestão de risco — não "ganhar dinheiro mágico".

---

## Sumário

1. [Resumo Executivo & Visão de Negócio](#1-resumo-executivo--visão-de-negócio)
2. [Análise Econômica & Estrutura de Custos](#2-análise-econômica--estrutura-de-custos)
3. [Estratégia Mecânica de Trade](#3-estratégia-mecânica-de-trade)
4. [Design do LLM-Gerente (Supervisor de Regime)](#4-design-do-llm-gerente-supervisor-de-regime)
5. [Gestão de Risco & Segurança](#5-gestão-de-risco--segurança)
6. [Stack Técnica & Infraestrutura](#6-stack-técnica--infraestrutura)
7. [Validação, Testes & Métricas](#7-validação-testes--métricas)
8. [Aspectos Legais & Tributários (Brasil)](#8-aspectos-legais--tributários-brasil)
9. [Roadmap, Fases & Orçamento](#9-roadmap-fases--orçamento)
10. [Resumo de Decisões Técnicas](#10-resumo-de-decisões-técnicas)
11. [Registro de Premissas e Constantes (fonte única da verdade)](#11-registro-de-premissas-e-constantes-fonte-única-da-verdade)
12. [Matriz Consolidada de Riscos](#12-matriz-consolidada-de-riscos)

---

## Glossário de terminologia (consistente em todo o documento)

- **Bot mecânico:** o motor de execução (Camada 1). Roda sempre ligado, sem LLM no loop quente, segue uma estratégia determinística (grid / mean-reversion). É onde o dinheiro é, de fato, ganho ou perdido.
- **LLM-gerente:** a camada de governança lenta (Camada 2). Lê o regime de mercado a cada 1–4h, classifica-o e ajusta parâmetros e o disjuntor (liga/desliga). **Nunca executa trades.** É um gerente de risco, não um gerador de lucro.
- **Trilhos de segurança:** checagens mecânicas em código puro (Camada 3) que vetam, limitam ou desligam. Sobrepõem-se a tudo, inclusive ao LLM-gerente. Funcionam mesmo se a OpenAI ou a Binance estiverem fora do ar.
- **Testnet:** a Binance Spot Testnet — ambiente de simulação com dinheiro fake rodando contra dados de mercado reais. Valida o *código*, não a *lucratividade*.
- **Teste A/B:** experimento controlado comparando **Bot A** (mecânico puro + trilhos) contra **Bot B** (idêntico + LLM-gerente), ambos contra o benchmark **buy-and-hold**.
- **Round-trip:** um ciclo completo de compra + venda do mesmo lote = duas taxas pagas.
- **Re-centralização:** reposicionamento da faixa `[P_min, P_max]` do grid quando o preço rompe a faixa (ver Seção 3.3.1).

---

## 1. Resumo Executivo & Visão de Negócio

### 1.1 Visão do projeto

Construir um robô de micro-trade automatizado que opera cripto na Binance via CCXT, executando muitos negócios pequenos por dia com uma estratégia mecânica (grid / mean-reversion). Sobre esse motor mecânico, um **LLM-gerente (GPT)** lê o regime de mercado a cada 1–4h e ajusta parâmetros e o disjuntor liga/desliga — **sem nunca executar trades**. Trilhos de segurança mecânicos protegem o capital acima de tudo. O objetivo central não é "ganhar dinheiro mágico", e sim **aprender a fundo a engenharia de trading automatizado e testar, com rigor científico (A/B em testnet), se uma LLM agrega valor real à gestão de risco.**

### 1.2 O problema / a oportunidade

| Dor real | Como o projeto ataca |
|---|---|
| Bots de varejo simples são "burros": rodam a mesma estratégia em qualquer mercado e quebram quando o regime muda (ex.: grid lateral pegando um crash de tendência). | LLM-gerente detecta mudança de regime e desliga/ajusta antes do estrago **lento** (regime que se forma em horas); os trilhos mecânicos cobrem o estrago **rápido** (crash em minutos). |
| A maioria dos bots de varejo **perde para as taxas e para o buy-and-hold**. Em micro-trade, a taxa é o inimigo nº 1. | Modelagem honesta de taxas desde o dia 1 + benchmark obrigatório contra buy-and-hold. |
| Reação emocional humana (pânico, FOMO) destrói contas. | Decisão de risco delegada a regras frias + um "gerente" que só pensa devagar, sem gatilho emocional. |
| Validar uma ideia de trading com dinheiro real é caro e arriscado. | Tudo nasce em **Binance Testnet** (dinheiro fake, mercado real) com teste A/B controlado. |

**A oportunidade não é "lucro garantido".** É um nicho pouco explorado de forma honesta: usar LLM **fora do loop quente** (camada de governança lenta e barata) em vez de tentar — caro e devagar — fazer a LLM operar trade a trade.

### 1.3 Proposta de valor (com a ressalva crítica sobre o papel do LLM)

- **Arquitetura híbrida correta:** rápido onde precisa ser rápido (bot mecânico em CCXT), inteligente onde compensa ser lento (LLM-gerente a cada horas, custo desprezível por decisão), e burro-porém-confiável onde a vida do capital está em jogo (trilhos de segurança).
- **LLM-gerente como gerente de risco, não como adivinho de preço.** A aposta realista é **perder menos** em mercados ruins, não acertar topos e fundos.
- **Prova ou refuta com dados:** o teste A/B (Bot A mecânico puro vs. Bot B mecânico + LLM-gerente) responde objetivamente "a LLM ajudou ou só queimou tokens?".
- **Custo operacional marginal da inteligência é irrisório** (ver Seção 2), então o downside financeiro da camada LLM é mínimo — o risco real está no bot mecânico e no mercado.

> **Ressalva honesta sobre a tese do LLM (ponto levantado na revisão):** existe uma tensão real na proposta de valor. Um crash agudo acontece em **minutos**; o LLM-gerente roda a cada **1–4h** e é estruturalmente *lento* para esse evento — por isso o crash agudo é coberto pelos **trilhos mecânicos**, não pela LLM. Então **onde sobra valor incremental para o LLM?** A resposta honesta delimita o escopo da tese:
> - O LLM **não** disputa o crash relâmpago (isso é dos trilhos).
> - O valor candidato do LLM está nas **transições de regime que se formam ao longo de horas/dias** — sair do grid quando uma *tendência de baixa sustentada* começa a se desenhar (antes de o trilho de drawdown disparar repetidamente), evitar reativar o grid cedo demais após uma queda, e cortar atividade (logo, taxas) em regimes onde o grid é estruturalmente perdedor.
> - Se o A/B mostrar que os trilhos sozinhos já capturam quase todo o benefício defensivo, **a conclusão honesta é rodar só o Bot A** — e isso é um resultado de pesquisa válido, não um fracasso.

### 1.4 Objetivos (com expectativas calibradas)

**Objetivo primário — Aprendizado (alta probabilidade de sucesso):**
- Dominar CCXT, modelagem de ordens, backtesting honesto, gestão de risco, prompt-engineering para saída JSON estruturada e MLOps leve.
- Entregável que tem valor mesmo se o bot não der lucro: um framework de teste A/B reproduzível e um relatório honesto de performance.

**Objetivo secundário — Potencial de lucro (probabilidade real, NÃO garantida):**
- Em testnet: provar edge estatístico positivo **líquido de taxas** e superior a buy-and-hold no mesmo período — com a ressalva (Seção 7) de que o PnL de testnet não é representativo de lucratividade real.
- Em produção (só se passar nos critérios): preservar capital e, na melhor hipótese, gerar retorno modesto ajustado ao risco.

> **Expectativa honesta:** o resultado mais provável de bots de varejo é empatar ou perder para buy-and-hold depois das taxas. Tratar QUALQUER lucro consistente líquido como **sucesso excepcional**, não como cenário-base.

### 1.5 Definição de SUCESSO e critérios Go / No-Go para dinheiro real

**Sucesso do projeto (independe de lucro):** o sistema roda estável em testnet, os trilhos de segurança disparam corretamente em testes de estresse, e o A/B produz uma conclusão clara e defensável sobre o valor do LLM-gerente.

**Critérios Go/No-Go para liberar dinheiro REAL** (todos obrigatórios — é um portão AND, não OR). Os números abaixo são fixados de forma única no **Registro de Premissas (Seção 11)** e referenciados aqui:

| # | Critério | Limiar (ver Seção 11 para o valor canônico) |
|---|---|---|
| 1 | Tempo mínimo em testnet | ≥ 60–90 dias corridos, cobrindo ≥ 1 regime de queda forte |
| 2 | Retorno líquido (pós-taxa) | Bot B > buy-and-hold da(s) moeda(s) no MESMO período |
| 3 | Valor do LLM-gerente comprovado | Bot B supera Bot A em retorno ajustado ao risco (Sortino) OU em drawdown máximo |
| 4 | Risco controlado | Drawdown máximo total dentro do limite canônico (circuit breaker **-12%**, ver §11); kill-switch nunca falhou em teste |
| 5 | Robustez operacional | Zero falhas catastróficas não tratadas (queda de API, ordem órfã, reconexão) em 30 dias |
| 6 | Custo não come o edge | Taxas + custo de API < margem bruta da estratégia, com folga |

**Se QUALQUER critério falhar → No-Go.** Permanecer em testnet ou encerrar. Ao migrar para real, começar com **capital mínimo que você pode perder 100% sem dor** (ver Seção 2 e §11), com os mesmos trilhos.

> Esses limiares qualitativos são detalhados em critérios numéricos objetivos e pré-registrados na Seção 7.6 (portões Go/No-Go por estágio). Todos os números de risco neste documento (drawdown diário, drawdown total, trades/dia, espaçamento) vêm do **Registro único da Seção 11** — não há mais valores divergentes espalhados pelo texto.

### 1.6 Perfil de quem opera

**Desenvolvedor solo brasileiro**, ambiente **Windows + Python**, perfil técnico, operando com **capital de risco descartável** e horizonte de **aprendizado em primeiro lugar**. Implicações para o desenho:

- Sem equipe de plantão 24/7 → os **trilhos de segurança e o kill-switch automático são inegociáveis**; o sistema precisa se proteger sozinho enquanto o operador dorme.
- Orçamento pessoal → preferir modelos LLM baratos (nano/mini) na camada gerente; custo de infra mínimo.
- Responsável também pela parte fiscal (ver Seção 8) e pelo **risco de compliance operacional** de um bot que gera milhares de operações/mês (ver Seção 8.5 e 12).
- **Natureza pessoa física vs. atividade habitual (risco regulatório novo):** a frequência/volume de um bot pode, em tese, levantar a discussão de se a operação ainda é "ganho de capital de pessoa física" ou se aproxima de atividade habitual/equiparável, com tratamento fiscal distinto. Isso **precisa ser validado com o contador** antes da operação real (ver Seção 8).

### 1.7 Riscos e retorno esperado (resumo honesto)

**O custo da camada de inteligência é desprezível** — o medo de "a LLM vai sair caro" não se sustenta na cadência-base (a cada 2–4h). Uma decisão a cada 1–4h (~6–24 chamadas/dia, alguns milhares de tokens cada) custa **centavos a poucos dólares por dia**. **Ressalva:** cadências agressivas (de hora em hora) com prompt pesado podem chegar a US$ 22–75/mês (ver tabela 2.4) — por isso a cadência intensiva é exceção, não regra. **O inimigo financeiro não é a LLM — são as taxas de trade.**

**As taxas de trade são o risco número 1.** Na Binance global, spot começa em **0,1% maker/taker**, caindo para **0,075% pagando em BNB** (desconto de 25%, com ressalvas — ver §2.2 e §2.3). Em micro-trade de alta frequência, 0,075% ida + 0,075% volta por ciclo **devora o edge rapidamente** — a estratégia precisa de margem por trade folgadamente acima do custo de round-trip, ou perde por construção.

Matriz resumida de riscos abaixo; a **matriz consolidada e completa** (incluindo riscos adicionados na revisão: depeg de USDT, risco de contraparte/exchange, slippage do kill-switch em flash-crash, latência+IP combinados, falha do provedor de câmbio, compliance recorrente, regulatório Binance/BCB) está na **Seção 12**.

| Risco | Severidade | Mitigação no projeto |
|---|---|---|
| Taxas comendo o lucro | **Alta** | Modelar taxa em todo backtest; exigir margem >> custo round-trip; medir tudo líquido |
| Perder para buy-and-hold (esp. em bull market) | Alta | Benchmark obrigatório; No-Go se não superar; ver risco de custo de oportunidade na §12 |
| Bug / ordem órfã / queda de API | Alta | Trilhos de segurança, idempotência, reconexão, kill-switch |
| Crash de mercado | Média-alta | Trilhos mecânicos (não o LLM) + stop global + limite de drawdown diário; ressalva de slippage do market order na §12 |
| LLM "alucinar" parâmetro ruim | Média | Saída JSON validada + limites rígidos (LLM só ajusta DENTRO de faixas seguras; trilhos vetam) |
| Overfitting em testnet | Média | Janela longa, múltiplos regimes, sem ajuste de parâmetro olhando o resultado |
| Diferença testnet vs. real (liquidez, slippage) | Média-alta | Capital mínimo no início real; reavaliar métricas pós-migração; ver tensão "decidir Go/No-Go com PnL de testnet" na §7 |
| Depeg de USDT (capital todo em USDT) | Média | Adicionado na revisão — ver §12 |
| Risco de contraparte (Binance: hack/congelamento/regulatório) | Média | Adicionado na revisão — ver §12 e §8 |

**Retorno esperado (honesto):**
- **Cenário-base (mais provável):** empate ou leve prejuízo líquido vs. buy-and-hold → fica em testnet; aprendizado entregue.
- **Cenário bom:** Bot B perde menos que Bot A nas quedas e empata/supera levemente buy-and-hold → tese do LLM-gerente validada.
- **Cenário excepcional (não esperar):** edge líquido positivo e consistente → candidato a dinheiro real, ainda em escala pequena.

O **maior valor esperado do LLM-gerente é defensivo** (menor drawdown, melhor sobrevivência em regimes ruins de horas/dias), não ofensivo (gerar alfa) e **não** disputar o crash de minutos (isso é dos trilhos). Sucesso aqui é, antes de tudo, **não quebrar e aprender muito**.

### 1.8 Disclaimer

> Este projeto é experimental e tem finalidade primária de **estudo**. Trading de cripto envolve **risco real de perda total do capital**. Nada aqui é recomendação de investimento. A maioria dos bots de varejo perde dinheiro. Opere **somente com capital que você pode perder integralmente**. No Brasil, ganhos com cripto têm obrigações fiscais (regras detalhadas e em movimento na Seção 8) — **regras mudam; confirme com fonte oficial e/ou contador antes de operar com dinheiro real**. Os limiares de Go/No-Go (drawdown, dias, etc.) são fixados no Registro da Seção 11 pelo operador **antes** de iniciar, nunca ajustados para justificar um resultado já obtido.

### Fontes (Seção 1)
- Taxas Binance spot: [Binance Square](https://www.binance.com/en/square/post/24640040632442)
- Preços OpenAI API: [OpenAI Pricing](https://openai.com/api/pricing/)
- Tributação cripto Brasil: [Mercado Bitcoin](https://www.mb.com.br/economia-digital/criptos/entenda-o-fim-da-mp-1303/), [Panorama Crypto / Transfero](https://panoramacrypto.transfero.com/como-declarar-criptomoedas-no-imposto-de-renda-2026/)

---

## 2. Análise Econômica & Estrutura de Custos

> **TL;DR honesto:** os dois inimigos do projeto são (1) as **taxas de trading**, que comem o micro-trade por dentro a cada round-trip, e (2) os **custos fixos de infra**, que comem capital pequeno por fora. As taxas decidem se a *estratégia* faz sentido; os custos fixos decidem se o *capital* faz sentido. O LLM-gerente é, de longe, o custo fixo menos preocupante na cadência-base (menos de US$ 10/mês). O problema real é o spread de 0,15–0,20% por round-trip que o grid precisa vencer dezenas de vezes por dia.

### 2.1 Estrutura de custos: as quatro fontes

| Fonte | Tipo | Quem paga | Ordem de grandeza |
|---|---|---|---|
| Taxas de trading (Binance) | **Variável** (por trade) | sangra a cada round-trip | 0,15–0,20% por ida+volta |
| LLM-gerente (OpenAI) | Fixo (recorrente) | infra | US$ 0,30–75/mês (cenário-base US$ 0,30–5; intensivo pode estourar) |
| VPS (servidor sempre ligado) | Fixo | infra | US$ 5–12/mês |
| APIs de dados (preço/funding) | Fixo ou US$ 0 | infra | US$ 0–35/mês |

A taxa de trading é a única que escala com a atividade do bot — e é a que mata bots de varejo. As outras três são fixas e diluíveis com mais capital.

### 2.2 Taxas da Binance Spot

Valores spot vigentes (2026):

| Nível | Maker | Taker | Como obter |
|---|---|---|---|
| **Padrão (VIP 0)** | 0,1000% | 0,1000% | conta nova |
| **Padrão + pagar taxa em BNB (−25%)** | 0,0750% | 0,0750% | ativar "Pay with BNB" |
| **VIP 1** | 0,0900% | 0,1000% | US$ 250 mil em volume/30d *ou* 25 BNB |
| **VIP 1 + BNB** | 0,0675% | ~0,0750% | combina os dois descontos |
| **VIP 9 (topo)** | 0,0200% | 0,0400% | > US$ 2 bi/mês de volume |

Fatos relevantes para o projeto:

- **Você vai operar no nível Padrão.** Para um bot de varejo com algumas centenas/milhares de dólares, atingir VIP 1 (US$ 250 mil de volume em 30 dias) é improvável e, se acontecer, é sinal de que você está *girando capital demais* e pagando taxa demais.
- **Ativar "Pay with BNB" reduz 25% das taxas** (0,10% → 0,075% por lado). É a otimização de maior ROI técnico do projeto, mas **não é "de graça" como simplificado em versões anteriores**:
  - exige **manter saldo de BNB** na conta (exposição adicional a um ativo volátil);
  - o desconto BNB **tem histórico de redução/expiração** pela Binance — não trate 0,075% como custo garantido perpétuo;
  - **pagar taxa em BNB é uma alienação de BNB → fato gerador tributável** a cada vez, e o preço do BNB flutua. Isso multiplica eventos no livro de custo médio (ver Seção 8.4). Decida com o contador se o ganho de 25% em taxa compensa a complexidade fiscal.
  > **Decisão recomendada:** ativar BNB pelo desconto, mas **modelar o cenário-base do backtest também com 0,10%/lado (sem BNB)** como piso de segurança, e tratar o desconto como upside, não como premissa.
- A taxa incide **dos dois lados** (compra e venda). Um micro-trade completo = 1 round-trip = 2 taxas.

(A Binance.US é uma entidade separada, com tabela diferente. Como o projeto usa a Binance global, assuma sempre **0,075%–0,1% por lado**.)

### 2.3 A MATEMÁTICA DAS TAXAS (o coração da viabilidade)

#### 2.3.1 Edge mínimo por trade só para empatar

Cada round-trip paga taxa duas vezes. O ganho bruto do trade precisa ser **maior** que isso só para zerar:

| Cenário de taxa | Por lado | **Round-trip (2 lados)** | Edge mínimo só p/ empatar |
|---|---|---|---|
| Padrão | 0,1000% | **0,2000%** | precisa capturar > 0,20% |
| Padrão + BNB (−25%) | 0,0750% | **0,1500%** | precisa capturar > 0,15% |
| VIP 1 + BNB | 0,0675% | **0,1350%** | precisa capturar > 0,135% |

**Leitura prática:** com BNB ativado (cenário otimista), **cada micro-trade precisa lucrar mais de 0,15% bruto só para não dar prejuízo**; sem BNB (cenário-base de segurança), mais de 0,20%. Para o bot ganhar dinheiro de verdade, o espaçamento do grid precisa render visivelmente acima desse piso por ciclo capturado — na prática, um grid com espaçamento abaixo de ~0,3–0,4% por nível tende a ser engolido pelas taxas mais a derrapagem (slippage) e o spread bid-ask.

> **Espaçamento mínimo do grid — valor canônico único (corrigido na revisão):** versões anteriores oscilavam entre "0,30–0,40%" e "0,30–0,50%". **Fica fixado um único número no Registro da Seção 11: piso prudente = 0,40% por nível** (com piso técnico absoluto de 2× a taxa de round-trip ≈ 0,15–0,20%). Esse 0,40% é um *trilho de segurança mecânico*, não um parâmetro que a LLM possa baixar livremente.

#### 2.3.2 Quantos trades/dia tornam isso viável ou inviável

O custo de taxa por dia, em % do notional movimentado por trade, cresce linearmente com o número de round-trips (cenário BNB, 0,15% RT):

| Trades/dia | Custo total de taxa/dia | Em que isso se traduz |
|---|---|---|
| 10 | 1,50% | exige edge médio > 0,15%/trade só p/ empatar |
| 30 | 4,50% | bot precisa "acertar" 0,15%+ trinta vezes |
| 50 | 7,50% | terreno arriscado: muito atrito acumulado |
| 100 | 15,00% | **provável sangria**: edge real raramente cobre |
| 200 | 30,00% | **inviável** na prática para varejo |

**Conclusão dura, sem hype:** "MUITOS micro-trades por dia" é uma faca de dois gumes. Cada trade extra é uma taxa garantida; o lucro é *probabilístico*. **É exatamente por isso que o disjuntor do LLM-gerente é a peça de maior valor econômico do sistema:** o maior ganho dele não é "achar trades bons", é **desligar o bot em regime ruim e parar de pagar taxa à toa.**

> **Reconciliação crítica — limite de trades/dia (corrigida na revisão):** o trilho de "trades/dia" precisa ser **coerente com esta tabela**. Como 100/dia já é "provável sangria" e 200/dia é "inviável", o teto do trilho **não pode ser 300**. **Valor canônico fixado na Seção 11: alerta em 50 trades/dia, teto duro (kill de novas ordens) em 80 trades/dia.** Acima disso, ou o espaçamento está pequeno demais, ou o regime virou — em ambos os casos a ação correta é pausar, não continuar girando.

### 2.4 Custo do LLM-gerente (OpenAI)

Preços por 1M de tokens (2026 — **revalidar antes de fechar orçamento; preços de LLM caem rápido e modelos são depreciados**):

| Modelo | Input | Cached input | Output |
|---|---|---|---|
| GPT-5.5 | US$ 5,00 | US$ 0,50 | US$ 30,00 |
| GPT-5.4 | US$ 2,50 | US$ 0,25 | US$ 15,00 |
| GPT-5.4 mini | US$ 0,75 | US$ 0,075 | US$ 4,50 |
| GPT-5.4 nano | US$ 0,20 | US$ 0,02 | US$ 1,25 |
| gpt-4o-mini | US$ 0,15 | — | US$ 0,60 |

> **Nota de modelo e risco de depreciação (ampliada na revisão):** os nomes de modelo acima são referências de 2026 e **podem ser renomeados, repreçados ou descontinuados** pela OpenAI a qualquer momento. Implicações que o projeto trata explicitamente:
> - **Abstrair o modelo atrás de uma variável de config** (`LLM_MODEL`) para troca sem mudar código.
> - **Fixar o modelo durante uma janela de A/B.** Trocar de modelo no meio do experimento **invalida a comparação** — se a OpenAI depreciar o modelo no meio de um A/B, a janela deve ser **descartada e reiniciada** com o modelo novo (registrar isso no log do experimento).
> - **Snapshot de versão:** quando possível, prender uma versão datada do modelo (model snapshot) para reduzir mudança de comportamento silenciosa entre versões.
> - A escolha-base recomendada é **um modelo da classe mini/nano**; a Seção 4 detalha o critério.

#### Custo mensal estimado do LLM-gerente (30 dias)

| Cadência | Tamanho da chamada | nano | mini | GPT-5.4 | GPT-5.5 |
|---|---|---|---|---|---|
| **a cada 4h** (6/dia) | leve (4k/0,5k) | $0,26 | $0,95 | $3,15 | $6,30 |
| a cada 4h | médio (12k/1k) | $0,66 | $2,43 | $8,10 | $16,20 |
| **a cada 2h** (12/dia) | médio (12k/1k) | $1,31 | $4,86 | $16,20 | $32,40 |
| **a cada 1h** (24/dia) | médio (12k/1k) | $2,63 | $9,72 | $32,40 | $64,80 |
| a cada 1h | pesado (30k/2k) | $6,12 | $22,68 | $75,60 | $151,20 |

**Recomendações concretas:**
- A tarefa é **classificação de regime + ajuste de parâmetros**, não raciocínio aberto. Um modelo **mini/nano é o ponto ótimo** custo/qualidade. Comece nele.
- **Cadência a cada 2h com modelo mini, prompt médio: ~US$ 5/mês.** Em nano com prompt leve, fica em **centavos/mês**.
- **Honestidade sobre o teto:** a mensagem "desprezível" vale para a **cadência-base (2–4h, prompt enxuto)**. As células destacadas em negrito na tabela acima são o orçamento real. Cadência de 1h com prompt pesado em modelo grande chega a **US$ 75–151/mês** — não use isso a menos que o A/B prove necessidade.
- Use **cached input** para o prompt de sistema fixo (cai ~90%).
- Considere **Batch/Flex API** (corta ~50%) para análises não urgentes.
- **Não use o modelo topo de linha no loop de gestão** a menos que o A/B prove que o modelo menor erra o regime.

### 2.5 VPS (servidor sempre ligado)

O bot mecânico precisa rodar 24/7 com estabilidade. VPS é obrigatório em produção.

| Provedor | Plano de entrada | Preço/mês | Observação |
|---|---|---|---|
| **Hetzner** | CX22 (2 vCPU / 4 GB) | ~€3,79–5,22 (~US$ 5) | melhor custo/desempenho; datacenter na Europa (latência maior à Binance) |
| **Hetzner** | CPX22 (reajuste pós-abril/2026) | €7,99 (~US$ 9,49) | após reajuste de preço |
| **Contabo** | Cloud VPS S | US$ 6,49 (ou ~US$ 3,96/ano antecipado) | mais RAM por dólar, disco mais lento |
| **DigitalOcean** | Droplet 1 vCPU / 1 GB | US$ 6,00 | mais caro, melhores ferramentas/docs |

**Recomendação:** uma VPS pequena (1–2 vCPU, 2–4 GB RAM) basta — o bot é leve (I/O-bound). Comece com **Hetzner CX22 (~US$ 5–9/mês)**. Para um bot que fala com a Binance em timeframe de minutos, a latência geográfica importa pouco — você não está competindo em microssegundos.

> **Risco combinado latência + IP whitelist (adicionado na revisão).** Há duas exigências que podem entrar em conflito: (a) a Seção 5.4 exige **IP whitelist estático** na API key; (b) a Binance **restringe acesso de alguns IPs/regiões**. Um datacenter europeu (Hetzner) pode estar em região com restrição ou comportamento instável para a API da Binance global. **Plano explícito (não apenas "valide o IP"):**
> 1. **Antes de assinar qualquer plano anual**, suba a instância no menor plano mensal e teste **autenticação real contra a API de produção** (não só testnet) com o IP fixo daquele datacenter.
> 2. **Plano B definido:** se o IP do provedor preferido for bloqueado/instável, alternativas são (i) outro datacenter/região do mesmo provedor, (ii) outro provedor (DigitalOcean/Contabo em região diferente), ou (iii) um IP estático/proxy dedicado autorizado. Não desligar a whitelist para "resolver".
> 3. Documentar qual datacenter/IP foi validado e a data do teste.

### 2.6 APIs de dados (preço, mercado, funding)

| Fonte | Custo | Para quê |
|---|---|---|
| **API pública da Binance** | **US$ 0** | preço, order book, candles, **funding rate**. Sem cartão, limite por *weight*. |
| CoinGecko — Free | US$ 0 | 10k créditos/mês, contexto macro do LLM. |
| CoinGecko — Basic | US$ 35/mês | 100k créditos, licença comercial, 2 anos de histórico |
| CoinGecko — Analyst | US$ 129/mês | WebSocket, tempo real |

**Recomendação:** a API pública da Binance é gratuita e suficiente para a validação. CoinGecko Free serve só como fonte secundária. CoinGecko pago não é custo do MVP.

> **Fonte de câmbio BRL é um requisito separado e crítico (adicionado na revisão).** A apuração fiscal (Seção 8) exige **converter cada operação para BRL na data certa e congelar a cotação**. Nenhuma das fontes acima é a fonte de câmbio oficial. **Defina uma fonte primária de câmbio BRL e um fallback** (ex.: PTAX do Banco Central como primária; cotação BRL da própria exchange/CoinGecko como secundária) **alinhada com o contador**, e trate a indisponibilidade dessa fonte como falha que **bloqueia o registro fiscal**, não como detalhe. Ver Seção 8.6 e o risco na Seção 12.

### 2.7 Tabela de custo mensal estimado (consolidada)

| Linha | Cenário enxuto (MVP/Testnet) | Cenário confortável (produção) |
|---|---|---|
| VPS | Hetzner CX22 — **US$ 5** | Hetzner CPX22 — **US$ 9,50** |
| LLM-gerente | nano @ 4h, leve — **US$ 0,30** | modelo mini @ 2h, médio — **US$ 5** |
| API de dados | Binance pública — **US$ 0** | Binance pública + CoinGecko Free — **US$ 0** |
| Câmbio BRL | PTAX (gratuita) — **US$ 0** | PTAX + fallback — **US$ 0** |
| Extras (domínio/monitoramento/logs) | **US$ 0** | **US$ 0–10** |
| **TOTAL FIXO/MÊS** | **~US$ 5–8** | **~US$ 15–30** |

> Taxas de trading **não** entram nesta tabela porque são variáveis e proporcionais ao volume girado. Veja a Seção 2.3.

### 2.8 Capital mínimo e análise de break-even

A pergunta certa: **a partir de quanto de capital os custos fixos param de comer o retorno?**

Custo fixo mensal como % do capital:

| Capital | Custo fixo US$ 8/mês (enxuto) | Custo fixo US$ 30/mês (confortável) |
|---|---|---|
| US$ 100 | **8,00%/mês** | **30,00%/mês** |
| US$ 300 | 2,67%/mês | 10,00%/mês |
| US$ 500 | 1,60%/mês | 6,00%/mês |
| US$ 1.000 | 0,80%/mês | 3,00%/mês |
| US$ 2.000 | 0,40%/mês | 1,50%/mês |
| US$ 5.000 | 0,16%/mês | 0,60%/mês |
| US$ 10.000 | 0,08%/mês | 0,30%/mês |

**Como ler isso, sem ilusão:**

- **Abaixo de ~US$ 300 de capital real, o projeto é economicamente irracional como negócio.**
- **A faixa de US$ 1.000–2.000 é onde o CUSTO FIXO DE INFRA vira ruído** (0,4–0,8%/mês no cenário enxuto).

> **Correção honesta (ponto da revisão):** dizer que "a partir de US$ 1.000–2.000 o jogo passa a ser só a estratégia" é **parcialmente enganoso** e foi ajustado. Mais capital dilui **apenas o custo fixo de infra**. As **taxas de trading são variáveis e continuam consumindo exatamente a mesma % do capital, independentemente do tamanho da conta.** Um bot que gira muito e captura menos que 2× a taxa por round-trip **perde a mesma fração do capital com US$ 1.000 ou com US$ 100.000**. Portanto: capital maior resolve o problema do *custo fixo*, **nunca** o problema do *custo variável de taxa* — esse só se resolve com espaçamento/seleção de regime corretos.

- **US$ 5.000+** torna a infra praticamente irrelevante (< 0,2%/mês) — aí o jogo é 100% sobre a qualidade da estratégia e a **gestão de taxas** (não "só a estratégia").

> **Conciliação com a Seção 1:** o critério "capital que você pode perder 100% sem dor" pode ser bem menor que US$ 1.000 (ex.: US$ 50–200), apropriado para o **piloto real inicial** (cujo objetivo é medir slippage/fills reais, não avaliar lucratividade). Para uma **avaliação econômica justa** da estratégia em produção, o capital recomendado é **US$ 1.000–2.000**, com conforto a partir de US$ 5.000.

#### Faseamento recomendado de capital

| Fase | Capital | Objetivo | Custo fixo aceitável |
|---|---|---|---|
| **1 — Testnet** | US$ 0 (fake) | provar A/B, validar trilhos | rode local ou VPS US$ 5; LLM nano |
| **2 — Piloto real** | US$ 50–1.000 | confirmar que P&L real ≈ Testnet (slippage, fills reais) | aceite que infra come 1–3%/mês; é o "preço do aprendizado" |
| **3 — Operação** | US$ 2.000–5.000+ | rodar a sério, custo fixo virou ruído | infra < 0,5%/mês |

### 2.9 Veredito econômico (honesto)

1. **Faça toda a Fase 1 em Testnet com custo perto de zero.** VPS US$ 5 + LLM nano + Binance pública = **~US$ 5–6/mês** durante toda a validação.
2. **O LLM-gerente é barato na cadência-base.** Mini a cada 2h custa ~US$ 5/mês. Só fica caro se você forçar 1h + prompt pesado + modelo grande — o que o projeto evita.
3. **A taxa de trading é o inimigo real, e capital maior NÃO a resolve.** Com BNB, cada round-trip precisa render > 0,15% (sem BNB, > 0,20%) só para empatar. O grid precisa de espaçamento prudente (**0,40%/nível**, valor canônico) como trilho mecânico fixo.
4. **O maior valor econômico do LLM-gerente é o disjuntor**, não a geração de sinal.
5. **Não rode dinheiro real abaixo de ~US$ 1.000 para fins de avaliação econômica.** Piloto inicial pode ser menor; avaliação justa exige US$ 1.000–2.000; conforto a partir de US$ 5.000.

### Fontes (Seção 2)
- [Binance — Spot Trading Fee Rate](https://www.binance.com/en/fee/schedule) · [TradersUnion — Binance Trading Fees 2026](https://tradersunion.com/brokers/crypto/view/binance/fees/) · [Bitget Academy — Binance Fees 2026](https://www.bitget.com/academy/binance-fees-2026)
- [DevTk.AI — OpenAI API Pricing Guide 2026](https://devtk.ai/en/blog/openai-api-pricing-guide-2026/) · [OpenAI API Pricing](https://openai.com/api/pricing/) · [PECollective — OpenAI API Pricing 2026](https://pecollective.com/tools/openai-api-pricing/)
- [Better Stack — DigitalOcean vs Hetzner 2026](https://betterstack.com/community/guides/web-servers/digitalocean-vs-hetzner/) · [TechPlained — Cheapest VPS Providers 2026](https://www.techplained.com/cheapest-vps-providers) · [Contabo VPS](https://contabo.com/en-us/vps/)
- [Binance Open Platform — Funding Rate API](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History) · [CoinGecko — API Pricing](https://www.coingecko.com/en/api/pricing) · [Banco Central — PTAX](https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes)

---

## 3. Estratégia Mecânica de Trade

Esta seção detalha o "coração" do projeto: o **bot mecânico** que executa os micro-trades. Ele roda sempre ligado, sem LLM no loop, e é onde o dinheiro de fato é ganho ou perdido.

### 3.1 Comparação: Grid Trading vs Mean-Reversion vs Market-Making

| Critério | Grid Trading | Mean-Reversion (estatística) | Market-Making (MM) |
|---|---|---|---|
| **Ideia central** | Grade fixa de ordens limite buy/sell em níveis pré-definidos. | "Preço justo" (média/banda); compra X desvios abaixo, vende ao voltar. | Cota bid e ask perto do mid-price e lucra o spread. |
| **Sinal de entrada** | Preço cruza um nível da grade. | Desvio estatístico (z-score, RSI, distância da média). | Não há "sinal" — está sempre no livro. |
| **Regime onde GANHA** | Lateral/range com volatilidade. | Lateral oscilante com reversão comprovada. | Lateral + alta liquidez + spread relevante. |
| **Regime onde PERDE** | Tendência forte (inventário acumulado). | Tendência forte e quebras de regime. | Tendência rápida → adverse selection. Crash = morte. |
| **Dependência de taxas** | Média. | Média/baixa. | **Extrema.** Inviável sem maker rebate / fees ~0. |
| **Sensibilidade a latência** | Baixa. | Baixa. | **Altíssima.** |
| **Complexidade real** | Baixa **a média** (ver ressalva 3.2). | Média. | Alta. |
| **Risco característico** | Acumular inventário num lado sem stop. | Reversão que não acontece. | Inventário tóxico + competição com HFT. |

Consenso das fontes: o grid "compra baixo e vende alto com lógica simples e transparente, muito compatível com mercados laterais". O risco número 1 é "acumular posições demais sem stop-loss adequado, levando a perdas grandes" em tendência.

### 3.2 Recomendação: começar com GRID TRADING (com viés de mean-reversion)

**Recomendo grid trading como estratégia inicial.** Justificativa concreta para *este* projeto:

1. **Encaixe com a arquitetura.** O grid é definido por parâmetros simples que o LLM-gerente vai ajustar; a LLM não precisa "inventar" um sinal.
2. **Market-making está descartado no começo.** Exige taxa próxima de zero, tick data, latência baixíssima e competição contra HFT.
3. **Mean-reversion "pura" vs grid.** Mean-reversion estatístico exige provar que o par realmente reverte; o grid entrega benefício similar sem precisar acertar o "preço justo" exato.
4. **Transparência para o teste A/B.** Como o grid é determinístico, fica fácil isolar a contribuição do LLM-gerente.

> **Ressalva de honestidade sobre a "simplicidade" do grid (corrigida na revisão).** Versões anteriores diziam "máximo aprendizado, mínimo de partes móveis". Isso **subestima** o grid robusto. Um grid de produção precisa de: (a) **lógica de re-centralização** quando o preço rompe a faixa (§3.3.1); (b) **gestão de inventário** com `max_inventory` (§3.4); (c) **detecção de breakout/tendência** para não "comprar a queda toda". Ou seja, um grid bem-feito tem **boa parte das "partes móveis"** que o texto atribuía só ao mean-reversion estatístico. O grid continua sendo o melhor *primeiro passo*, mas a simplicidade é **relativa**, não absoluta — planeje essas partes móveis desde o início.

**Honestidade obrigatória:** grid ganha em mercado lateral e *sangra em tendência forte*. Sem os trilhos de segurança e sem o LLM-gerente detectando regime de tendência para desligar, o grid eventualmente acumula inventário comprado num downtrend e leva uma perda grande. O maior valor do LLM-gerente é *desligar o grid antes da tendência destruir o inventário*.

### 3.3 Seleção de par e lógica de entrada/saída do Grid

#### 3.3.0 Seleção do par (lacuna preenchida na revisão)

Grid **exige um ativo lateral-oscilante**; ironicamente, o BTC tem **longos regimes de tendência** que são o pior cenário para grid. Critérios de seleção de par para o MVP:

- **Liquidez alta** (spread bid-ask apertado, livro profundo) → reduz slippage. Favorece pares grandes (BTC/USDT, ETH/USDT).
- **Volatilidade de range, não de tendência:** preferir pares que historicamente oscilam dentro de faixas. Um candidato clássico é um **par cripto-cripto correlacionado** (ex.: **ETH/BTC**), que tende a ser mais "lateral" do que cripto/USD, justamente porque os dois ativos sobem/descem juntos.
- **Filtro quantitativo:** medir, em janela histórica, a razão **tempo em range vs. tempo em tendência** (ex.: % de barras com ADX < 20). Escolher o par com maior fração lateral.
- **Custo mínimo de ordem viável:** `MIN_NOTIONAL` e `LOT_SIZE` compatíveis com o capital pequeno do piloto.
- **Trade-off explícito:** BTC/USDT e ETH/USDT têm liquidez excelente mas regimes de tendência longos (ruim p/ grid); ETH/BTC é mais lateral mas tem menos liquidez e introduz exposição cripto-cripto (e complexidade fiscal de conversão para BRL). **Recomendação do MVP:** começar com **ETH/USDT** pela liquidez e simplicidade de conversão BRL, e **avaliar ETH/BTC** como candidato a "mais lateral" no backtest comparativo antes de fixar.

#### 3.3.1 Conceito do grid e re-centralização (lacuna preenchida na revisão)

**Conceito.** Define-se `[P_min, P_max]` dividido em `N` níveis (recomendado: razão geométrica, espaçamento percentual constante). Abaixo do preço, ordens de compra limite; acima, ordens de venda limite.

**Ciclo de um nível:**
1. Preço cai e executa uma **buy limit** no nível `k`.
2. O bot coloca uma **sell limit** no nível `k+1`.
3. Preço sobe e executa a sell → lucro = (espaçamento) − (2 × taxa).
4. O bot recoloca uma buy no nível `k`.

**O que acontece quando o preço ROMPE a faixa (o ponto mais perigoso, antes omisso):**

- **Rompe para CIMA (`> P_max`):** todas as sell executam, o bot fica em caixa (sem inventário) e **perde o upside** enquanto o preço sobe fora da grade. Custo de oportunidade alto em bull market (ver risco na §12).
- **Rompe para BAIXO (`< P_min`):** todas as buy executam, **todo o capital vira inventário comprado no fundo** e o preço continua caindo → perda latente grande. **Este é o modo de morte do grid.**

**Política de re-centralização (definida, com responsabilidades claras):**

| Situação | Quem decide | Ação |
|---|---|---|
| Rompimento moderado para cima/baixo em regime ainda **lateral** | **Mecânico** (regra automática) | re-centra a grade em torno do novo preço (recalcula `P_min`/`P_max` por ATR), respeitando `max_inventory` |
| Rompimento para baixo com **sinais de tendência** (ADX↑, EMA empilhada) | **LLM-gerente** decide reduzir/pausar; **trilho** veta se drawdown estourar | **NÃO re-centra cegamente para baixo** (isso é "perseguir a faca caindo"); pausa novas compras |
| Drawdown/inventário estoura limite duro | **Trilho de segurança** (override) | kill-switch: cancela grade, sai a mercado |

**Regra de ouro da re-centralização:** **nunca re-centrar para baixo de forma automática durante uma queda com sinal de tendência** — re-centrar para baixo num downtrend transforma o grid numa máquina de comprar o caminho inteiro até o fundo. A re-centralização automática é permitida **apenas em regime lateral confirmado**; em qualquer suspeita de tendência, a decisão sobe para o LLM-gerente e os trilhos têm a palavra final.

#### 3.3.2 Grid neutro vs direcional

- **Neutro (spot):** modo seguro para começar em testnet spot.
- **Viés long/short:** o LLM-gerente inclina a grade conforme o regime. Em spot puro, "short" = reduzir/zerar exposição. **Começar spot** para evitar liquidação.

### 3.4 Parâmetros principais

| Parâmetro | O que é | Como definir / quem ajusta |
|---|---|---|
| `P_min`, `P_max` | Limites da faixa | Inicial: ATR/bandas dos últimos N dias. Ajustado pelo LLM-gerente; re-centralização por regra (§3.3.1). |
| `N` (níveis) | Número de degraus | Começar com 10–20. Mais níveis = mais trades, mais taxa. |
| `spacing` | Distância entre níveis | **Canônico: 0,40%/nível** (§11). Sempre `> 2 × taxa`, geométrico. |
| `order_size` | Quantidade por nível | `capital_alocado / N`. Respeitar `minNotional` e `LOT_SIZE`. |
| `bias` | Inclinação long/short/neutro | Saída do LLM-gerente (JSON). |
| `stop_global` / drawdown | Trilho de segurança | Mecânico, sobrepõe tudo. |
| `max_inventory` | Posição máxima acumulada | **Trilho mecânico** — impede o grid de "comprar o caminho todo para baixo". Crítico para o modo de morte do §3.3.1. |

**Regra de ouro do espaçamento:** lucro por ciclo = `spacing − 2 × fee`. Se `spacing ≤ 2 × fee`, você *perde dinheiro em cada trade que parece vencedor*.

### 3.5 Relação com as taxas

Um ciclo completo = duas taxas. Com fee de 0,075% (BNB) cada lado, round-trip = 0,15%; sem BNB (cenário-base de segurança), 0,20%. **Espaçamento canônico: 0,40%/nível** (folga sobre ambos os cenários, absorvendo slippage). Use **ordens limite (maker) + post-only** (§3.6). **Buy-and-hold é benchmark obrigatório** — em tendência de alta o grid frequentemente perde para simplesmente segurar a moeda (ver custo de oportunidade na §12).

### 3.6 Tipos de ordem no CCXT

| Tipo | Uso no grid |
|---|---|
| **Limit** | Ordem principal (maker). Cada nível da grade. |
| **Post-Only** (`params={'postOnly': True}`) | **Recomendado para todas as ordens do grid.** Garante maker; se fosse virar taker, é rejeitada. |
| **Market** | **Evitar no loop normal.** Só em saída de emergência (kill-switch). Paga taker e aceita slippage — ver ressalva crítica abaixo. |
| **Stop-Loss / Stop-Limit** | Stop por posição. O stop global/drawdown deve ser do lado do bot, não confiar só na exchange. |
| **fetchOpenOrders / cancelOrder** | Reconciliação no reinício. |

> **Ressalva crítica — slippage do kill-switch via market order (adicionada na revisão).** O kill-switch usa **ordem a mercado** para sair "AGORA". Mas o kill-switch dispara justamente em **crash/flash-crash**, que é exatamente quando o livro está fino e a market order **derrapa muito**. Consequência honesta: **um "stop em -X%" pode se realizar bem pior que -X%** na prática. Mitigações: (a) preferir **stop-limit com banda de tolerância** quando houver tempo, caindo para market só se não preencher; (b) **dimensionar o circuit breaker total contando com esse slippage extra** (por isso o limite total é conservador); (c) documentar que o drawdown *realizado* num crash pode exceder o limite *configurado*. Não tratar o stop como garantia de preço.

Notas práticas: use **WebSocket** para fills em tempo real; respeite `LOT_SIZE`, `PRICE_FILTER`, `MIN_NOTIONAL`; use `clientOrderId` idempotente por nível.

### 3.7 Como backtestar ANTES da testnet

**Pipeline recomendado:**

1. **Dados históricos.** OHLCV via CCXT ou dumps da Binance (`data.binance.vision`). Não usar OHLCV para validar MM/scalping fino.
2. **Framework.** **vectorbt** (varredura rápida de parâmetros), **Backtrader** (event-driven realista) ou **Freqtrade** (bot cripto com backtest embutido). Recomendo Freqtrade ou vectorbt.
3. **Modelar custos realistas (não negociável).** Comissão **0,1% (cenário-base de segurança) e 0,075% (cenário BNB)**; slippage 0,05%–0,30%; latência (fill não instantâneo).
4. **Evitar lookahead bias.** Sinais no fechamento, execução no open seguinte ou limite realista; para grid, fill apenas quando o preço *atravessa* o nível.
5. **Out-of-sample / walk-forward.** Reservar 20%–30% para fora da amostra.
6. **Testar nos três regimes** (lateral, tendência de alta, crash). Documentar a perda no crash — calibra o kill-switch.
7. **Métricas.** Retorno líquido, nº de trades, taxa total, max drawdown, Sharpe/Sortino, e **sempre o delta vs buy-and-hold** (fórmulas na §7.4).

**Ordem de validação completa:** `Backtest (vários regimes + walk-forward)` → `Paper/Testnet (Bot A vs Bot B, mesmo período)` → `dinheiro real pequeno`.

### 3.8 Resumo acionável

- **Comece com grid trading** em **spot testnet**, modo neutro, par **ETH/USDT** (avaliar ETH/BTC como mais lateral).
- **Market-making fica para depois.**
- **Limit + post-only**; **market só nos trilhos de emergência** (com ressalva de slippage).
- **Espaçamento canônico 0,40%/nível** (§11).
- **Implementar re-centralização e `max_inventory` desde o início** — não são opcionais.
- **Backtest primeiro**, modelando fee (com e sem BNB) + slippage + lookahead + walk-forward, três regimes, vs buy-and-hold.
- **Honestidade:** grid ganha em range, sangra em tendência. O LLM-gerente entrega valor desligando o grid antes da tendência — e o grid "simples" tem mais partes móveis do que parece.

### Fontes (Seção 3)
- [Binance Fee Schedule](https://www.binance.com/en/fee/schedule)
- [Hedge Think — Grid Trading Strategies](https://www.hedgethink.com/grid-trading-strategies-a-systematic-approach-for-fund-managers/) · [B2Broker — Grid Trading Pros & Cons](https://b2broker.com/news/understanding-grid-trading-purpose-pros-cons/) · [Cryptohopper — What is Grid Trading](https://www.cryptohopper.com/blog/what-is-grid-trading-11252)
- [vectorbt](https://vectorbt.dev/) · [Backtrader](https://www.backtrader.com/) · [Freqtrade docs](https://docs.pytrade.org/trading)
- [Stoic.ai — Backtest Crypto Strategies](https://stoic.ai/blog/backtesting-trading-strategies/) · [Blockchain Council — Lookahead bias/overfitting](https://www.blockchain-council.org/cryptocurrency/backtesting-ai-crypto-trading-strategies-avoiding-overfitting-lookahead-bias-data-leakage/) · [Bitget Academy — Backtesting Best Practices](https://www.bitget.com/academy/12560603877835)

---

## 4. Design do LLM-Gerente (Supervisor de Regime)

> **Princípio central:** o LLM-gerente é um **gerente de risco**, não um gerador de lucro. Ele não toca em ordens. Classifica o regime a cada poucas horas e **ajusta os botões** do bot mecânico — sobretudo o LIGA/DESLIGA. Se agregar valor, será **perdendo menos** em regimes ruins que se formam ao longo de horas/dias — **não** disputando o crash de minutos (isso é dos trilhos; ver ressalva em §1.3).

### 4.1 Frequência de execução e gatilhos

**Cadência agendada:**
- **Base: a cada 4 horas**, alinhado às janelas de funding da Binance.
- **Modo intensivo opcional: a cada 1h** em períodos de teste ou alta volatilidade declarada (custa mais — ver §2.4 — então é exceção).

Por que não rodar mais rápido: o LLM é lento e custa por token; mudanças intra-hora são cobertas pelos **trilhos de segurança**.

**Gatilhos de evento:**

| Gatilho | Condição (exemplo, calibrar no testnet) | Por quê |
|---|---|---|
| Pico de volatilidade | ATR(14) 1h > 2x média de ATR das 24h | Regime pode ter virado |
| Movimento abrupto | Variação > 3% em 15 min | Possível notícia/evento |
| Drawdown intradiário | P&L do dia atinge 50% do limite de kill-switch | Avaliar regime ANTES do trilho cortar |
| Funding extremo | Funding anualizado fora de banda (ex.: > +30% ou < -30% a.a.) | Custo de carrego mudou |
| Sequência de stops | 3 stops mecânicos numa janela curta | Parâmetros não casam com o mercado |

**Importante:** o evento dispara o LLM, mas **nunca** se espera o LLM para agir em emergência. Em emergência, a Camada 3 corta na hora; o LLM só decide se/quando **religar** (sujeito ao cooldown da §5).

### 4.2 INPUTS exatos que o LLM recebe

Um **único objeto JSON compacto e pré-digerido**, montado em Python. Regra de ouro: **números resumidos, nunca candles brutos em massa.**

```jsonc
{
  "timestamp_utc": "2026-06-07T16:00:00Z",
  "symbol": "ETH/USDT",
  "timeframe_base": "5m",

  "price": {
    "last": 3825.0,
    "change_pct": { "1h": -0.4, "4h": -1.9, "24h": -3.8 },
    "high_low_24h": { "high": 3990.0, "low": 3790.0 },
    "recent_closes_sample": [3960, 3940, 3915, 3900, 3880, 3860,
                             3845, 3830, 3815, 3825, 3818, 3825]
  },

  "volatility": {
    "atr14_5m": 6.1,
    "atr14_1h": 22.0,
    "atr_pct_of_price": 0.57,
    "atr_ratio_1h_vs_24h_avg": 1.8,
    "realized_vol_24h_annualized_pct": 62.0
  },

  "indicators": {
    "rsi14_1h": 38.0,
    "rsi_state": "neutral_baixo",
    "macd_1h": { "hist": -1.2, "trend": "bearish", "cross": "none" },
    "ema_stack_1h": "20<50<200",
    "bollinger_1h": { "pct_b": 0.18, "bandwidth_pct": 3.1, "state": "perto_banda_inferior" },
    "adx_1h": 28.0,
    "regime_hint_mecanico": "tendencia_baixa_fraca"
  },

  "derivatives": {
    "funding_rate_8h": 0.0001,
    "funding_rate_annualized_pct": 10.95,
    "funding_trend": "estavel",
    "open_interest_change_24h_pct": 4.2
  },

  "news_sentiment": {
    "available": true,
    "as_of_utc": "2026-06-07T15:30:00Z",
    "headlines_top": [
      { "src": "fonte_x", "t": "2026-06-07T14:50Z", "title": "...", "tag": "macro" }
    ],
    "agg_score": -0.2,
    "fear_greed_index": 41
  },

  "bot_performance": {
    "pnl_today_pct": -1.1,
    "pnl_7d_pct": 0.6,
    "trades_today": 47,
    "win_rate_today_pct": 53.0,
    "fees_paid_today_quote": 12.4,
    "pnl_after_fees_today_pct": -1.4,
    "stops_hit_today": 2,
    "vs_buy_and_hold_today_pct": -0.3,
    "consecutive_losing_cycles": 1,
    "price_broke_grid": "none"          // "up" | "down" | "none" — sinaliza rompimento de faixa
  },

  "current_state": {
    "engine_status": "ATIVO",
    "strategy_mode": "grid",
    "bias": "nenhum",
    "position_size_pct": 30,
    "grid_spacing_pct": 0.40,           // valor canônico (ver §11)
    "stop_loss_pct": 1.5,
    "open_position_quote": 850.0,
    "last_llm_decision_utc": "2026-06-07T12:00:00Z",
    "last_llm_regime": "lateral"
  },

  // LIMITES DOS TRILHOS (read-only) — valores canônicos da Seção 11
  "guardrails": {
    "max_position_pct": 50,
    "max_position_per_symbol_pct": 25,
    "daily_drawdown_kill_pct": 3.0,     // CANÔNICO = 3.0 (corrigido; antes havia 5.0 inconsistente)
    "total_drawdown_kill_pct": 12.0,    // circuit breaker total
    "max_trades_per_day": 80,           // CANÔNICO = 80 (corrigido; antes 200-300)
    "drawdown_used_today_pct": 1.4
  }
}
```

**Notas de design dos inputs:**
- **Tudo já vem interpretado** (RSI como número *e* `rsi_state`).
- **P&L sempre líquido de taxas** (`pnl_after_fees`, `vs_buy_and_hold`).
- **`price_broke_grid`** (novo) informa o LLM se a faixa foi rompida, insumo para a decisão de re-centralização (§3.3.1).
- **Guardrails refletem os valores canônicos da §11** — note que `daily_drawdown_kill_pct` agora é **3.0** (não mais 5.0) e `max_trades_per_day` é **80** (não mais 200), eliminando as inconsistências apontadas na revisão.
- **Sentimento/notícias é opcional e datado.** Se a fonte falhar, `available: false`. **Nunca deixar o LLM "preencher" notícia que não existe** — problema real corrigido no [TradingAgents](https://github.com/TauricResearch/TradingAgents).
- **`regime_hint_mecanico`** é heurística do bot, não ordem.

### 4.3 SCHEMA JSON de SAÍDA

Saída **JSON estruturada e validada** (Structured Outputs + Pydantic). JSON inválido/fora dos limites → sistema descarta e mantém estado anterior ou aciona PAUSAR.

```jsonc
{
  "schema_version": "1.1",
  "as_of_utc": "2026-06-07T16:00:00Z",
  "symbol": "ETH/USDT",

  "regime": "tendencia_baixa",
  // enum: ["lateral", "tendencia_alta", "tendencia_baixa", "crash", "incerto"]
  "regime_confidence": 0.62,

  "action": "reduzir",
  // enum: ["operar", "reduzir", "pausar"]

  "strategy_mode": "grid",
  // enum: ["grid", "mean_reversion", "off"]

  "bias": "short_leve",
  // enum: ["nenhum", "long", "long_leve", "short", "short_leve"]

  "recenter_grid": false,   // só true em regime lateral confirmado (§3.3.1); nunca para baixo em tendência

  "params": {
    "position_size_pct": 15,
    "grid_spacing_pct": 0.55,           // >= 0,40% canônico; será clampado
    "stop_loss_pct": 1.5,
    "max_concurrent_orders": 6,
    "take_profit_pct": 0.6
  },

  "reason": "EMA empilhada em baixa (20<50<200) e ADX 28 indicam tendência, não lateralidade; grid puro perde comprando a queda. Reduzo tamanho, alargo o grid e adoto viés short leve. NÃO re-centralizo para baixo. RSI 38 ainda não dá sobrevenda clara para reverter.",
  "key_risks": ["tendencia_baixa", "atr_subindo"],

  "reassess_in_minutes": 60,
  "request_human_review": false
}
```

**Regras de aplicação (no código, não no LLM):**
- **Clamp obrigatório:** todo número em `params` é forçado para dentro de `guardrails` (e `grid_spacing_pct` nunca abaixo do canônico 0,40%) antes de aplicar.
- **Trilhos vencem sempre:** em kill-switch, `action: "operar"` é ignorado.
- **`recenter_grid` é vetado** se houver sinal de tendência ou se levar a re-centralização para baixo num downtrend.
- **Confiança baixa → conservador:** `regime_confidence < 0.5` rebaixa a ação para no máximo `reduzir`.
- **Idempotência/log:** toda decisão é gravada (input + output + o aplicado pós-clamp) para o A/B **e para a auditoria de acerto de regime (§4.5.1)**.

### 4.4 Design do PROMPT do sistema

**System prompt fixo** (cacheável) + **user message** com o JSON do momento.

**Papel:** "Você é o **Gerente de Risco** de um bot de micro-trade. Você **NÃO executa trades**. Classifica o regime e ajusta parâmetros/estado. Objetivo: **PRESERVAR CAPITAL e evitar operar em regimes onde grid/mean-reversion perdem estruturalmente**. Você é avaliado por *perder menos*, não por *ganhar mais*."

**Regras duras:**
1. **Responda SOMENTE com o JSON do schema.**
2. **Na dúvida, seja conservador:** prefira `reduzir`/`pausar` a `operar`.
3. **Não exceda limites** (o sistema corta de qualquer forma).
4. **Grid/mean-reversion só prosperam em lateral/reversão.** Em tendência forte/crash → `pausar`/`reduzir`.
5. **Taxas importam:** se `pnl_after_fees` é negativo com bruto positivo, favoreça alargar grid ou `reduzir`.
6. **Buy-and-hold é a régua.**
7. **Não invente dados** (sentimento indisponível = ignorar).
8. **`reason` deve citar os números.**
9. **Nunca re-centralizar para baixo numa tendência de baixa** (`recenter_grid` só em lateral confirmado).

Heurísticas por campo e exemplos few-shot (incerto→pausar; lateral saudável→operar; tendência baixa→reduzir/short leve) conforme o schema acima.

### 4.5 Reaproveitando IDEIAS dos prompts do TradingAgents

Aproveitamos as **ideias/estrutura** condensadas em **um único prompt** (não a arquitetura de 7 agentes, que seria cara/lenta):

| Ideia do TradingAgents | Como reaproveitamos |
|---|---|
| Analista técnico | Bloco "indicators" + regras técnicas no prompt |
| Analista de notícias/sentimento | Bloco `news_sentiment` opcional e datado; regra de "não fabricar" |
| Debate Bull vs Bear | No `reason`, considerar o argumento contrário antes de decidir |
| Gerente de risco que arbitra | É o **papel principal** do nosso LLM-gerente |

#### 4.5.1 Auditoria de acerto de regime do LLM (lacuna preenchida na revisão)

O A/B (§7.3) mede se o Bot B é melhor que o Bot A, mas **não diz se o LLM acerta o regime ou só liga/desliga por sorte**. Sem isso, não dá para saber *por que* o LLM ajudou (ou não). Método de auditoria, separado do A/B:

1. **Rótulo ex-post (ground truth).** Após cada janela (ex.: 4h), classifique mecanicamente o regime *que de fato ocorreu* usando uma regra determinística sobre dados *futuros àquele instante* (ex.: retorno realizado + ADX da janela seguinte → lateral/tendência/crash). Esse rótulo só pode ser computado **depois**, então nunca entra no input do LLM.
2. **Matriz de confusão.** Compare `regime` previsto pelo LLM vs. rótulo ex-post. Métricas: acurácia por classe, e especialmente **recall de "tendência_baixa"/"crash"** (errar esses é o caro).
3. **Calibração de confiança.** Verifique se `regime_confidence` é calibrada: nas decisões com confiança 0,6, o LLM acerta ~60%? Confiança mal calibrada é sinal de problema no prompt/modelo.
4. **Valor incremental sobre a heurística barata.** Compare o acerto do LLM contra a `regime_hint_mecanico` (heurística ADX/EMA gratuita). **Se o LLM não bate a heurística barata, ele não se justifica** — rode só a heurística.
5. **Log para reprodutibilidade.** Cada decisão guarda input, output, rótulo ex-post (preenchido depois) e custo de tokens.

Essa auditoria responde à pergunta que o A/B sozinho não responde: *"o LLM realmente entende o regime, ou o ganho do Bot B é ruído?"*.

### 4.6 Controle de custo

(Tabela completa em §2.4.) Começar no modelo mais barato adequado (**nano** ou **gpt-4o-mini**); promover para mini só se a auditoria de regime (§4.5.1) ou o A/B justificarem; reservar modelo topo para anomalias.

**Estimativa (nano, cadência 4h + eventos ≈ 10 chamadas/dia):** ~US$ 0,25/mês. **O perigo de custo é só rodar de minuto em minuto — que não fazemos.**

> **Ressalva sobre "o LLM não pode custar mais do que o risco que evita" (ponto da revisão).** Essa frase é uma *diretriz*, não uma equação acionável a priori: o "risco evitado" só é mensurável **depois**, via A/B + auditoria de regime. Tratamento honesto: como o custo do LLM na cadência-base é de **centavos a poucos dólares/mês**, a barra para ele "se pagar" é baixíssima — mas a decisão de mantê-lo **só se confirma com os dados de saída** (§7.6), não por suposição.

**Técnicas de redução:** prompt caching (system fixo no início), payload enxuto, output curto (`reason` ≤ 60 palavras), `max_output_tokens` baixo, pular a chamada se nada relevante mudou, modelo escalonado.

### 4.7 Resumo de uma linha

O LLM-gerente roda a cada ~4h (ou por evento), recebe um JSON pré-digerido + P&L líquido + estado, devolve um JSON validado (regime, ação, modo, viés, params, recenter), sempre clampado pelos trilhos, tendendo a PAUSAR na dúvida, custando centavos/mês em nano — e seu acerto de regime é **auditado independentemente** do A/B. Ele **gere risco; não promete lucro**, e **não disputa o crash de minutos**.

### Fontes (Seção 4)
- [OpenAI API Pricing](https://developers.openai.com/api/docs/pricing)
- [Introduction to Binance Futures Funding Rates](https://www.binance.com/en/support/faq/introduction-to-binance-futures-funding-rates-360033525031)
- [TradingAgents — TauricResearch (GitHub)](https://github.com/TauricResearch/TradingAgents)

---

## 5. Gestão de Risco & Segurança

> **Princípio central:** o LLM-gerente *sugere*; os trilhos de segurança *protegem*. Nenhuma decisão do LLM pode violar um trilho. Os trilhos rodam em código puro, sem rede, então funcionam mesmo se a OpenAI/Binance estiverem fora do ar.

### 5.1 Trilhos de segurança independentes do LLM

Checagens "hard-coded" avaliadas **antes de cada ordem** e em *heartbeat* a cada poucos segundos. O LLM pode endurecer, **nunca afrouxar**. Cada trilho é uma função pura `(permitido: bool, motivo: str)` com log.

**Valores canônicos (fonte única: Seção 11).** Premissa: capital de referência `EQUITY`. Comece **mais apertado** e relaxe só com dados.

| Trilho | Valor canônico (§11) | O que dispara | Ação ao disparar |
|---|---|---|---|
| **Stop-loss por posição** | 1,0%–1,5% do preço de entrada | preço contra a posição além do limite | fecha *aquela* posição (preferir stop-limit; ver ressalva slippage §3.6) |
| **Drawdown diário (kill-switch)** | **-3% do equity do dia** (reset 00:00 UTC) | PnL do dia abaixo do limite | **DESLIGA até o próximo dia**; cancela ordens; não reabre por ordem do LLM |
| **Drawdown total (circuit breaker)** | **-12% do equity de pico** | equity vs. *high-water mark* | **PARADA TOTAL**, exige intervenção manual |
| **Exposição máxima total** | **50% do equity** | soma do valor de mercado das posições | bloqueia novas aberturas |
| **Exposição máxima por moeda** | **25% do equity** | exposição em um único par | bloqueia aumento naquele símbolo |
| **Limite de trades/dia** | **alerta 50 / teto duro 80** | contador de ordens no dia | pausa novas ordens; protege contra loop e taxas |
| **Exposição máxima à exchange (novo)** | capital operacional ≤ valor que você aceita perder por risco de contraparte | saldo na conta operacional acima do teto | alerta para retirar excedente (ver §5.4 e §12) |
| **Limite de ordens/intervalo (anti-runaway)** | máx. 10 ordens/min por símbolo | rajada anormal | pausa o símbolo + alerta |
| **Tamanho mín/máx de ordem** | min = `MIN_NOTIONAL`; max = 5% do equity | ordem fora da faixa | rejeita a ordem |
| **Saldo mínimo de operação** | ex.: 100 USDT livres | saldo abaixo do piso | desliga abertura |

> **Resolução das inconsistências apontadas na revisão (não apenas sinalizadas — corrigidas):**
> - **Kill-switch diário = -3%** (canônico). O exemplo de payload da §4.2 foi **corrigido de 5.0 para 3.0** para bater com este valor. Não há mais divergência.
> - **Circuit breaker total = -12%** (dentro da faixa "-10% a -15%" e coerente com o "≤ 15–20%" mencionado na §1.5; fixado num único número).
> - **Trades/dia: alerta 50, teto 80** — coerente com a §2.3.2 (100/dia já é "provável sangria"). O antigo teto de 200–300 foi **removido** por contradizer a própria matemática de taxas.
> - **Espaçamento mínimo = 0,40%** (canônico, §2.3.1/§11).
> Todos esses números vivem agora **apenas na Seção 11**; o resto do documento referencia.

- **Taxas comem o resultado de micro-trade** — por isso o limite de trades/dia é um **trilho financeiro**, não só técnico. Em testnet as taxas são fictícias — **não confie no PnL de testnet para validar lucratividade**; valide *comportamento* em testnet.
- **Drawdown diário e total são os dois trilhos mais importantes.** O *high-water mark* deve ser **persistido em disco**.

**Hierarquia de decisão:**

```
TRILHOS DE SEGURANÇA  (veto absoluto, sempre)
        ▲  podem só endurecer
LLM-GERENTE           (ajusta parâmetros dentro dos limites)
        ▲
BOT MECÂNICO          (executa dentro dos parâmetros)
```

### 5.2 Modos de falha e mitigação

Provoque cada modo de propósito em testnet (chaos testing) antes de confiar.

| Modo de falha | Sintoma | Mitigação | Estado-alvo |
|---|---|---|---|
| **Exchange/API fora do ar** | timeout, 5xx, WS cai | retry com backoff+jitter; após N falhas, **modo seguro** | SAFE / FLAT |
| **Rate limit / ban** | HTTP 429 (e 418 = ban) | respeitar `Retry-After`; monitorar `X-MBX-USED-WEIGHT-*`; throttle abaixo do teto | THROTTLE → SAFE |
| **LLM alucinando** | JSON absurdo | validação Pydantic + clamping; **manter config anterior** | último config válido |
| **LLM travando/lenta** | timeout OpenAI | timeout curto (30–60s); **bot mecânico segue com último config** | continua mecânico |
| **LLM contradiz trilho** | "ligar" durante drawdown | trilho vence; comando ignorado e logado | trilho prevalece |
| **Modelo LLM depreciado no meio do A/B** | erro de modelo inexistente / mudança de comportamento | fallback para config conservador; **descartar janela de A/B afetada** e reiniciar com modelo novo registrado | A/B reiniciado |
| **Flash crash** | queda violenta em segundos | trilhos mecânicos (não LLM); detecção > X% em 1 min → modo seguro; **ciente do slippage do market order (§3.6)** | SAFE / FLAT |
| **Ordem não preenchida (parcial/aberta)** | fill parcial, ordem pendurada | reconciliar via `openOrders`/`myTrades` no boot e periodicamente | estado reconciliado |
| **Ordem duplicada** | reenvio após timeout que preencheu | `newClientOrderId` idempotente; consultar status antes de reenviar | sem duplicata |
| **Desconexão (rede/WS)** | stream para | watchdog/heartbeat; reconectar e ressincronizar via REST | RESYNC → resume |
| **Reinício do bot** | processo morre com posições | **estado persistente** (SQLite): posições, ordens (client ids), HWM, PnL do dia, contador, flag do kill-switch, **livro de custo médio**. Boot: carregar → reconciliar → operar | recupera com segurança |
| **Relógio/timezone** | `-1021 recvWindow` | sync via `GET /time`, **UTC em tudo**, NTP, `recvWindow` 5000 ms; reset do "dia" em 00:00 UTC | sem rejeição |
| **Saldo insuficiente** | `-2010` | checar saldo antes; trilho de saldo mínimo | bloqueia abertura |
| **Falha da fonte de câmbio BRL (novo)** | cotação BRL indisponível | usar fallback definido (§2.6); se ambos caírem, **marcar a operação como "câmbio pendente"** e bloquear o fechamento contábil até reconciliar — nunca gravar BRL estimado errado | registro fiscal consistente |
| **Depeg de USDT (novo)** | USDT ≠ ~US$ 1 | alerta crítico; em depeg severo, **kill-switch e avaliar conversão**; ver §12 | SAFE + alerta |
| **Vazamento de chave** | ordens estranhas | chave **sem saque** + **IP whitelist**; alerta de ordem fora do padrão | dano limitado a trade |

**Padrão recomendado:** uma **máquina de estados** explícita — `RUNNING → THROTTLE → SAFE → HALTED`.

### 5.3 Princípio fail-safe

**Regra de ouro: na dúvida, o sistema PARA e NÃO OPERA.**

1. **Falha desconhecida** → `SAFE`, cancela ordens, alerta, não abre novas.
2. **Sem config válido do LLM** → ficar desligado até a primeira leitura válida (ou config conservador default explícito).
3. **Não consigo saber meu estado** → `HALTED`.
4. **Trilho disparou** → lado restritivo vence; circuit breaker total exige ação manual.
5. **Ambiguidade abrir vs proteger** → proteger.
6. **Kill-switch é "sticky"** até o reset, mesmo que o mercado recupere ou o LLM peça religar.

### 5.4 Segurança (chaves, permissões, conta) e risco de contraparte

**Chaves de API — nunca no código:** variáveis de ambiente / `.env` no `.gitignore` (`python-dotenv`), ou cofre; no Windows considere `keyring`. **Testnet ≠ produção** (`set_sandbox_mode(True)`). Adicione `.env`, `*.key`, `secrets.*`, `state.db`, logs ao `.gitignore` antes do primeiro commit. Rotacione periodicamente.

**Permissões da API key (mínimo privilégio):**

| Permissão | Configuração |
|---|---|
| Enable Reading | LIGADO |
| Enable Spot & Margin Trading | LIGADO (só Spot; **não** habilite margem) |
| **Enable Withdrawals (saque)** | **DESLIGADO — sempre.** |
| Enable Futures | DESLIGADO |
| Universal/Internal Transfer | DESLIGADO |
| **IP Access Restriction (whitelist)** | **LIGADO** com IP fixo da VPS (ver risco combinado em §2.5) |

- Withdrawals exigem IP whitelist (e você deixa saque OFF, reforçando segurança).
- Chave sem IP restriction expira em ~30 dias; com whitelist é mantida.
- IP residencial dinâmico quebra a whitelist → VPS com IP estático.

**Conta e 2FA:** 2FA por **app autenticador (TOTP)** ou hardware (não SMS); anti-phishing code; whitelist de endereços de saque na conta; alertas de login/API.

> **Risco de contraparte / custódia (lacuna preenchida na revisão).** Manter capital na Binance é manter capital com **um terceiro** sujeito a hack, congelamento, deslistagem, problemas de saque ou ação regulatória. Plano explícito, não "de passagem":
> - **Manter na conta operacional apenas o capital que o bot pode arriscar** — formalizado como **trilho de exposição máxima à exchange** (§5.1).
> - **Política de retirada periódica:** lucros acima de um teto são sacados para custódia própria (carteira self-custody) ou conta separada, em cadência definida.
> - **Diversificação de risco de plataforma** é desproporcional para um projeto de aprendizado, mas o operador deve **conscientemente aceitar** que 100% do capital operacional está exposto ao risco Binance.
> - Acompanhar a **situação regulatória da Binance no Brasil** (Lei 14.478 / marco das VASPs, regulamentação do BCB em curso), que pode afetar acesso/KYC/operação para residentes — ver §8 e §12.

### 5.5 Checklist de prontidão para "ligar de verdade"

- [ ] Trilhos como funções puras, com unit tests que **forçam cada disparo**.
- [ ] Kill-switch diário e circuit breaker total persistidos e "sticky".
- [ ] Estado persistente + reconciliação no boot, testado matando o processo com posição aberta.
- [ ] **Testes de reconciliação de estado e do livro de custo médio** (pontos de bug silencioso — ver §6/§8).
- [ ] Máquina de estados `RUNNING/THROTTLE/SAFE/HALTED` com logs.
- [ ] Validação de schema + clamping de todo output do LLM (incl. veto a re-centralização para baixo).
- [ ] `newClientOrderId` idempotente; retry com backoff; tratamento de 429/418.
- [ ] UTC em tudo; sync de relógio; `recvWindow`.
- [ ] `.env` no `.gitignore`; testnet ≠ produção.
- [ ] API key: reading + spot ON; **withdrawals OFF**; futures OFF; **IP whitelist ON** (datacenter validado contra a API real — §2.5).
- [ ] 2FA TOTP; whitelist de saque na conta; **trilho de exposição máxima à exchange** + política de retirada.
- [ ] Fonte de câmbio BRL + fallback definidos e testados.
- [ ] Rodou semanas em **testnet** provocando falhas de propósito.

### Fontes (Seção 5)
- [Binance Fees 2025 (coinspot.io)](https://coinspot.io/en/analysis/binance-fees-2025-the-ultimate-guide/) · [Spot Trading Fee Rate — Binance](https://www.binance.com/en/fee/spotMaker)
- [API Key Permission — Binance Developers](https://developers.binance.com/docs/wallet/account/api-key-permission) · [Binance API IP Whitelist (QuotaGuard)](https://www.quotaguard.com/blog/binance-api-ip-whitelist-cloud-static-ip)
- [REST API LIMITS — Binance Developers](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/limits)

---

## 6. Stack Técnica & Infraestrutura

> Foco: o que instalar, por quê, como organizar o repositório e como rodar 24/7 numa VPS com Docker. Dados de preço/versão verificados em 2026-06-07.

### 6.1 Linguagem e runtime

| Item | Decisão | Justificativa |
|---|---|---|
| Linguagem | **Python** | Ecossistema de trading/dados maduro. |
| Versão | **Python 3.13.x** | Estável, máxima compatibilidade com ta-lib/ccxt. Evitar 3.14 só "porque é novo". |
| Gerenciador de pacotes | **uv** (ou pip + venv) | Lockfile reprodutível. **Pinar versões** é obrigatório. |
| Concorrência | **asyncio** | CCXT async + python-telegram-bot v22. |

### 6.2 Bibliotecas principais

**Exchange / execução:**

| Lib | Versão ref. | Para quê |
|---|---|---|
| **ccxt** | 4.5.x | Acesso à Binance spot, testnet (`set_sandbox_mode(True)`), versão async. **Travar no lockfile e manter atualizada** — mudanças de endpoint da Binance já quebraram versões antigas (§7.1). |

**Dados e indicadores:** pandas 2.3.x, numpy 2.x. Lib de indicadores: **`ta`** (pura Python, MVP) → **ta-lib** se precisar de performance; `pandas-ta` original está inativo (fork ativo: `pandas-ta-classic`).

**LLM-gerente:** openai SDK 1.x (structured outputs) + **pydantic 2.x** (validação = camada de risco). Modelo abstraído em `LLM_MODEL` (ver §2.4 sobre depreciação).

**Agendamento/estado/observabilidade:** APScheduler, SQLAlchemy 2.x, **SQLite (MVP) → PostgreSQL (produção)**, alembic, structlog (JSON), python-telegram-bot 22.x.

**Config e qualidade:** pydantic-settings, python-dotenv, pytest + pytest-asyncio, ruff, mypy, freezegun/respx/vcrpy (mocks).

### 6.3 Estrutura de pastas / módulos

```
microtrade-bot/
├── pyproject.toml
├── uv.lock
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── src/microtrade/
│   ├── main.py
│   ├── config/        # settings.py, profiles.py (Bot A vs Bot B)
│   ├── exchange/      # client.py, orders.py, account.py (único lugar que toca a API)
│   ├── data/          # market_data.py, indicators.py
│   ├── strategy/      # base.py, grid.py (incl. re-centralização), mean_reversion.py, params.py
│   ├── manager/       # llm_client.py, prompts.py, schema.py, regime.py, decision.py, regime_audit.py
│   ├── risk/          # guards.py, kill_switch.py, limits.py, exchange_exposure.py
│   ├── engine/        # trade_loop.py, scheduler.py
│   ├── storage/       # db.py, models.py, repository.py, cost_basis.py (livro de custo médio)
│   ├── tax/           # fx_rates.py (câmbio BRL + fallback), fiscal_log.py
│   ├── alerts/        # telegram.py
│   └── observability/ # logging.py
├── scripts/           # ping_testnet.py, backtest.py, ab_report.py
├── migrations/
└── tests/
    ├── test_strategy.py
    ├── test_grid_recenter.py        # re-centralização e modo de morte
    ├── test_risk_guards.py          # PRIORIDADE
    ├── test_decision_schema.py
    ├── test_state_reconciliation.py # NOVO: ponto de bug silencioso
    ├── test_cost_basis.py           # NOVO: livro de custo médio + fee em BNB
    ├── test_fx_rates.py             # NOVO: câmbio BRL + fallback
    └── test_exchange_mock.py
```

> **Cobertura de testes ampliada (ponto da revisão).** Além de `test_risk_guards` (prioridade), são agora **igualmente prioritários**: `test_state_reconciliation` (reconciliação de estado no boot) e `test_cost_basis` (livro de custo médio, incluindo o caso da **fee paga em BNB como alienação** — §8.4), por serem os pontos mais propensos a bug silencioso com impacto financeiro/fiscal. `test_fx_rates` cobre a fonte de câmbio e o fallback.

**Ordem de avaliação no loop:** `data → strategy → risk.guards → exchange → storage`. O LLM atua **fora** do caminho quente, só reescrevendo `strategy/params` entre ciclos.

### 6.4 Deploy: VPS + Docker, 24/7

VPS pequena (Hetzner CX22 ~US$ 5–9/mês; provedores em §2.5). **Atenção ao risco combinado latência + IP whitelist + restrição geográfica da Binance — validar o IP contra a API REAL antes de plano anual (§2.5).**

- **Dockerfile multi-stage**, runtime `python:3.13-slim`, **usuário não-root**.
- **docker-compose** com `bot` + `postgres`; **`restart: unless-stopped`** (mecanismo principal de 24/7); healthcheck.
- `systemctl enable docker` para subir o daemon após reboot.

```yaml
services:
  bot:
    build: .
    restart: unless-stopped
    env_file: .env
    depends_on: [db]
    healthcheck:
      test: ["CMD", "python", "-m", "microtrade.healthcheck"]
      interval: 60s
      timeout: 10s
      retries: 3
  db:
    image: postgres:17
    restart: unless-stopped
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes: [pgdata:/var/lib/postgresql/data]
volumes: { pgdata: {} }
```

**Variáveis de ambiente (chaves nunca hardcoded):** `EXCHANGE_API_KEY/SECRET`, `TRADING_MODE` (testnet|live, **começa testnet**), `OPENAI_API_KEY`, `LLM_MODEL`, `MANAGER_INTERVAL_HOURS`, `MAX_DAILY_DRAWDOWN_PCT=3`, `TOTAL_DRAWDOWN_KILL_PCT=12`, `MAX_TRADES_PER_DAY=80`, `GRID_SPACING_PCT=0.40`, `MAX_POSITION_PCT=50`, `MAX_POSITION_PER_SYMBOL_PCT=25`, `FX_SOURCE_PRIMARY=ptax`, `FX_SOURCE_FALLBACK=...`, `TELEGRAM_*`, `DATABASE_URL`, `BOT_PROFILE` (A|B). **Esses defaults batem com a Seção 11.**

**Monitoramento:** Telegram (alertas de trilho, drawdown, erro, heartbeat diário; `/status`, `/pause`, `/kill`); healthcheck do container; structlog JSON + `docker logs` com rotação; **watchdog externo (dead man's switch, ex.: Healthchecks.io)** que alerta se a VPS inteira morrer.

### 6.5 Justificativas-chave

- **ccxt** pela portabilidade e testnet trivial; latência extra irrelevante para micro-trade em minutos.
- **pydantic no JSON do LLM** é camada de risco, não luxo.
- **Modelo mini/nano** porque o custo é desprezível e a tarefa não exige fronteira.
- **SQLite → PostgreSQL.**
- **Docker + `restart: unless-stopped`** para 24/7.
- **Custo dominante é taxa de trade**, não infra nem LLM.

### Fontes (Seção 6)
- [Status das versões Python](https://devguide.python.org/versions/) · [Python 3.13.13](https://www.python.org/downloads/release/python-31313/)
- [ccxt no PyPI](https://pypi.org/project/ccxt/) · [pandas-ta-classic](https://pypi.org/project/pandas-ta-classic/)
- [OpenAI API pricing](https://openai.com/api/pricing/) · [python-telegram-bot no PyPI](https://pypi.org/project/python-telegram-bot/)

---

## 7. Validação, Testes & Métricas

> **Princípio reitor:** o objetivo não é "provar que o bot funciona" — é **tentar arduamente provar que ele NÃO funciona**. Toda métrica deve ser computada **líquida de taxas e custo de API**, comparada contra **buy-and-hold**, e tratada com ceticismo estatístico.

### 7.1 Setup da Binance Testnet

A **Binance Spot Testnet** é simulação com **dinheiro virtual** contra **dados reais**. Testa o *código*, não o *capital*.

**Chaves:** em https://testnet.binance.vision/ (login GitHub/Google, separado da conta real). Tipos: HMAC-SHA-256 (mais simples no CCXT), RSA, Ed25519. Guardar em `.env`.

**No CCXT:**
```python
import ccxt
ex = ccxt.binance({'apiKey': API_KEY, 'secret': API_SECRET, 'enableRateLimit': True})
ex.set_sandbox_mode(True)
```

> **Armadilha conhecida:** a Binance já mudou o endpoint da testnet, quebrando versões antigas do CCXT com `Invalid API-key` ([ccxt#27266](https://github.com/ccxt/ccxt/issues/27266)). **Trave o CCXT no lockfile.** Erro de chave inválida na testnet → suspeite primeiro da versão do CCXT.

**Limitações (e impacto na validação):**

| Limitação | Impacto |
|---|---|
| **Reset periódico (~mensal)** (chaves preservadas) | Persista estado/PnL no **seu** banco; se um reset cair numa janela de teste, **descarte a janela**. |
| Apenas endpoints `/api` | Suficiente para grid spot. |
| Timeout de 10s | Trate timeouts desde já. |
| **Liquidez/order book sintético e fino** | **A limitação mais perigosa.** Fills/slippage **não representativos** — testnet valida *código*, não *lucratividade*. |
| Rate limits/filtros iguais à produção | Valida `minNotional`, `stepSize`, `tickSize`, pesos. |

### 7.2 Fases de teste (pipeline em 4 estágios)

```
[0] Backtest histórico  → "A lógica tem alguma vantagem no passado?"
        ↓
[1] Paper / Testnet     → "O código aguenta o mundo real?"
        ↓
[2] Forward / dinheiro real MÍNIMO → "Sobrevive a slippage/latência/liquidez REAIS?"
        ↓
[3] Escala gradual      → "Mantém edge com capital maior?"
```

**Estágio 0 — Backtest** (detalhado em §3.7): custos realistas (0,1% e 0,075%), sem lookahead, walk-forward, três regimes, LLM sobre dados com timestamp congelado.

**Estágio 1 — Testnet (1–2 semanas mín.):** valida engenharia. Checklist: reconexão; rate limit; idempotência; reconciliação no boot; **trilhos disparam de verdade** (force drawdown sintético); LLM retorna JSON válido e **clampado**.

**Estágio 2 — Dinheiro real MÍNIMO (4–12 semanas):** capital de brincar de perder (US$ 50–200). Mede slippage/profundidade/latência reais. Espere PnL pior que testnet/backtest.

**Estágio 3 — Escala gradual:** só após bater os portões da §7.6; degraus pequenos e reversíveis.

> **Tensão honesta não resolvível, mas explicitada (ponto da revisão): "não confie no PnL de testnet" vs "decidir Go/No-Go com A/B de testnet".** A conclusão científica central (LLM agrega valor?) é coletada majoritariamente em ambiente de liquidez sintética. Tratamento:
> - O A/B de testnet é válido para a pergunta **relativa e estrutural** ("o Bot B reduz drawdown / evita operar em regime ruim **mais** que o Bot A?"), porque ambos sofrem a **mesma** distorção de liquidez — a comparação A vs B é mais robusta à irrealidade da testnet do que o nível absoluto de lucro.
> - O A/B de testnet **não** é válido para a pergunta **absoluta de lucratividade**. Por isso o **Portão 1→2 não usa lucro de testnet como critério de lucratividade** — usa robustez de engenharia + sinal *relativo* de A/B. A **lucratividade só é julgada no Estágio 2 (dinheiro real)**, no Portão 2→3.

### 7.3 Metodologia do Teste A/B

| Braço | Composição |
|---|---|
| **Bot A (controle)** | Mecânico puro + trilhos. Sem LLM. |
| **Bot B (tratamento)** | Mecânico **idêntico** + trilhos **idênticos** + LLM-gerente. |
| **Benchmark** | **Buy-and-hold** da mesma moeda no mesmo período. |

**Regras para A/B justo:** mesmo período simultâneo; mesmo par/capital/trilhos; contas/subcontas separadas; **mesmo binário** com flag `--llm-manager on/off`; sementes/timestamps logados; **modelo LLM fixo durante a janela** (troca/depreciação invalida e reinicia — §2.4).

**Duração e tamanho de amostra (lacuna de poder estatístico preenchida na revisão):**
- Testnet (Estágio 1): 1–2 semanas — engenharia, não lucratividade.
- **A/B com significância: mínimo 8–12 semanas**, cobrindo idealmente um regime de cada tipo.
- **A confiança vem do número de TRADES e, sobretudo, do número de EVENTOS DE CAUDA, não do win rate.** Um grid tem win rate alto (80%+) com **raras perdas grandes** — a estatística que importa está na **cauda** (as poucas perdas grandes em tendência), não nos muitos ganhos pequenos.
  - **Implicação de tamanho de amostra:** centenas de trades dão significância ao win rate (que é quase irrelevante aqui), mas **pode haver pouquíssimos eventos de cauda** numa janela de 8–12 semanas. Conclusões sobre "o LLM reduz a perda de cauda" exigem **observar vários eventos de tendência/queda** — não bastam dias corridos. Se a janela teve só 1–2 episódios de tendência, **a conclusão sobre proteção de cauda é fraca por construção** e deve ser reportada como tal.
  - **Regra prática:** não declarar "o LLM protege em quedas" com menos de **~5 episódios de tendência/queda distintos** observados em A/B; até lá, é hipótese, não resultado.

> **Reconciliação da janela (corrigida na revisão):** o roadmap (§9.7) cita 3–6 semanas como **coleta inicial / primeira leitura**; a **conclusão Go/No-Go exige 8–12 semanas + eventos de cauda suficientes**. O quadro-resumo da §9.1 traz isso com asterisco para não subestimar o cronograma.

**Como decidir se a diferença é real:** métricas (§7.4) para A, B e hold; magnitude E robustez; teste por blocos (vencer em 8–9 de 10 blocos = sinal; 5 de 10 = ruído); **hipótese honesta esperada**: "B perde menos em quedas, retorno parecido em lateral" → melhora de *risco ajustado*, registrada como **sucesso parcial honesto**.

### 7.4 Métricas — fórmulas e interpretação

Coletar para **A, B e buy-and-hold**, **líquido de taxas e API**.

**Resultado:** Retorno líquido; **Retorno vs buy-and-hold** (métrica-rei; < 0 = destruiu valor); Win rate (enganoso sozinho); **Profit Factor** (mire ≥ 1,5 líquido); Payoff ratio.

**Risco:** **Max Drawdown** (sobrevivência); Sharpe (>1 razoável, >3 desconfie); **Sortino** (melhor aqui; o LLM deveria melhorá-lo mais que Sharpe); Calmar; nº trades/dia.

> **Nota técnica:** anualizar Sharpe de dados intradiários infla o número. Reporte a **periodicidade base** e seja consistente entre A, B e benchmark.

**Custo (decisivas):** Custo de taxas acumulado (`Σ notional × fee`); Custo de API (exclusivo do Bot B); **"Break-even edge" = 2 × fee** por round-trip (com BNB ≥ 0,15%; sem BNB ≥ 0,20%).

**Métrica de decisão final:**
```
Valor líquido do LLM-gerente = (Retorno_B_líquido − Custo_API_B) − Retorno_A_líquido
```
Se ≤ 0 de forma consistente, **o LLM não se paga** → rodar só o Bot A (ou repensar prompt/cadência). **Complementar com a auditoria de acerto de regime (§4.5.1)** para entender *por quê*.

### 7.5 Custos atuais para o backtest

Taxas (0,1% / 0,075% com BNB) e preços OpenAI unificados na §2. Use **0,075%–0,1% por lado** (cenário-base de segurança em 0,1%). **Revalide os preços de LLM antes de fechar o orçamento.**

### 7.6 Critérios Go / No-Go (objetivos, pré-registrados na §11)

**Portão 0 → 1 (sair do backtest):**
- [ ] Retorno líquido > buy-and-hold em walk-forward out-of-sample.
- [ ] Positivo em ≥ 2 regimes distintos.
- [ ] Profit Factor líquido ≥ 1,5.
- [ ] Max Drawdown < 20%.
- [ ] Taxas acumuladas < 50% do lucro bruto.

**Portão 1 → 2 (sair da testnet) — robustez + sinal relativo, NÃO lucratividade absoluta:**
- [ ] 100% do checklist de robustez (Estágio 1) passa.
- [ ] Trilhos disparam corretamente em teste forçado.
- [ ] LLM retorna JSON válido em ≥ 99% das chamadas; fora dos limites é **clampado**, nunca aplicado cru.
- [ ] Zero ordens duplicadas/órfãs em 1–2 semanas.
- [ ] **Sinal relativo de A/B** (B ≥ A em drawdown/risco) coerente — não usa lucro absoluto de testnet.

**Portão 2 → 3 (liberar escala com dinheiro real) — rigorosos e cumulativos:**
- [ ] Bate buy-and-hold líquido por ≥ 3 meses corridos de forward real pequeno.
- [ ] Max Drawdown realizado < 15% (mais apertado que no backtest; **contar com slippage do kill-switch — §3.6**).
- [ ] Sortino ≥ 1,0 (periodicidade declarada).
- [ ] Profit Factor líquido ≥ 1,3 com N ≥ algumas centenas de trades **e ≥ ~5 eventos de cauda observados**.
- [ ] Bot B ≥ Bot A em risco-ajustado *após* custo de API — OU decisão explícita de rodar só Bot A.
- [ ] Slippage real dentro do orçamento do backtest.

**Gatilhos de No-Go / parada imediata:** drawdown estoura o limite duro; 3 meses sem bater buy-and-hold; divergência estado local vs exchange; custo de API > valor adicionado de forma sustentada.

> **Lembrete final:** atingir o Portão 2 com dinheiro pequeno **não garante** sucesso com capital maior (slippage cresce com o tamanho da ordem). O Estágio 3 escala em degraus pequenos e reversíveis.

### Fontes (Seção 7)
- [Binance Spot Testnet](https://testnet.binance.vision/) · [General Info — Binance Docs](https://developers.binance.com/docs/binance-spot-api-docs/testnet/general-info) · [ccxt issue #27266](https://github.com/ccxt/ccxt/issues/27266)
- [Binance Fees 2025 — Coinspot](https://coinspot.io/en/analysis/binance-fees-2025-the-ultimate-guide/) · [Binance Spot Fee Rate](https://www.binance.com/en/fee/spotMaker)
- [OpenAI API Pricing](https://openai.com/api/pricing/) · [OpenAI API Cost in 2026 — CloudZero](https://www.cloudzero.com/blog/openai-pricing/)

---

## 8. Aspectos Legais & Tributários (Brasil)

> **AVISO — NÃO É ACONSELHAMENTO JURÍDICO OU CONTÁBIL.** Resumo técnico de regras vigentes em junho de 2026, para orientar o que o bot precisa **registrar**. A tributação de cripto no Brasil mudou várias vezes em 2024–2026 e ainda está em movimento. **Contrate um contador especializado em criptoativos antes de operar com dinheiro real** — especialmente num bot que gera centenas/milhares de operações/mês.

### 8.1 Panorama: dois regimes diferentes

A regra depende de **onde a cripto está custodiada**. Como a arquitetura usa Binance: **Binance global (estrangeira)** ou entidade nacional? Regimes radicalmente diferentes:

| Aspecto | Exchange **nacional** | Exchange **estrangeira** (Binance global) |
|---|---|---|
| Base legal | Ganho de capital (IN SRF 118/2004) | **Lei 14.754/2023** |
| Isenção mensal | **Sim** — vendas até **R$ 35.000/mês** | **Não existe** |
| Alíquota | Progressiva **15% a 22,5%** | **Fixa 15%** sobre lucro líquido anual |
| Periodicidade | **Mensal** (caixa) | **Anual** (DAA) |
| Recolhimento | **DARF 4600**, último dia útil do mês seguinte | Sem DARF mensal — pago na DAA |
| Compensação de prejuízo | Limitada | Permite compensar perdas e carregar prejuízo |

> Na **testnet** não há fato gerador. **Decida cedo qual entidade da exchange usar** — define isenção, DARF e regime inteiro.

### 8.2 Alíquotas (exchange nacional)

| Faixa de ganho (lucro) | Alíquota |
|---|---|
| Até R$ 5 mi | **15%** |
| R$ 5–10 mi | 17,5% |
| R$ 10–30 mi | 20% |
| Acima de R$ 30 mi | 22,5% |

Para um bot de varejo, quase tudo cai nos **15%**.

### 8.3 A isenção de R$ 35.000/mês — armadilha para bots

Só vale para exchanges nacionais. Incide sobre **valor total de alienações** (não sobre lucro); se as vendas do mês passam de R$ 35.000, **todo o ganho do mês vira tributável**.

> **ALERTA CRÍTICO:** um bot de grid faz **MUITOS micro-trades**. A isenção olha o **volume bruto de vendas**, não o lucro. Um bot que gira o capital dezenas de vezes ao dia **estoura R$ 35.000 em volume trivialmente** — possivelmente num único dia. **Na prática, a isenção quase nunca protege um bot de alta frequência.** Não conte com ela.

**Status político (junho/2026):** a isenção **continua válida**. A MP 1.303/2025 (alíquota única) **caducou em 8/out/2025**. O governo pode tentar de novo — reavalie a cada exercício.

### 8.4 Alta frequência, custo médio, DARF e a fee em BNB

Cripto **NÃO** segue a regra de day-trade de ações; é ganho de capital / Lei 14.754, intradiária ou não.

**Custo médio ponderado:** cada compra recalcula o custo médio; cada venda realiza lucro/prejuízo = (preço de venda − custo médio) × qtd. Num grid bot com **milhares de compras/vendas parciais**, a apuração manual é inviável — o bot precisa manter um **livro de custo médio rolante automatizado** (módulo `storage/cost_basis.py`, com testes — §6.3).

> **Tratamento fiscal da fee paga em BNB (lacuna preenchida na revisão).** Tornar "Pay with BNB" obrigatório tem custo fiscal escondido: **pagar fee em BNB é uma alienação de BNB → fato gerador**, e o preço do BNB flutua. Consequências que o livro de custo médio **precisa** tratar:
> - Cada pagamento de fee em BNB gera um **evento de venda de BNB** (com seu próprio ganho/perda vs. custo médio do BNB) — **multiplicando** o número de eventos tributáveis.
> - O **BNB tem seu próprio livro de custo médio**, separado do ativo operado.
> - Toda recompra de BNB para repor o saldo de fee é uma **nova aquisição** que recalcula o custo médio do BNB.
> - **Decisão a tomar com o contador:** se a complexidade fiscal de rastrear o BNB supera o ganho de 25% na taxa, pode ser mais simples **não** pagar fee em BNB. O backtest com cenário sem BNB (§2.2) ajuda a quantificar o trade-off.
> - `test_cost_basis.py` deve cobrir explicitamente o caso "fee paga em BNB".

**DARF (exchange nacional):** código **4600**, mensal, último dia útil do mês seguinte, recolhimento do contribuinte.

**Exchange estrangeira:** sem DARF mensal; lucro líquido anual a 15% na DAA (ficha "Aplicações Financeiras no Exterior"); compensa prejuízos.

### 8.5 Obrigações de declaração/reporte (e custo de compliance recorrente)

**Declarar ≠ pagar.** Você pode ter de declarar mesmo sem dever imposto.

**IRPF anual (DAA):** cripto na ficha **"Bens e Direitos"** pelo custo de aquisição, acima do limite de declaração (~R$ 5.000 por tipo — confirme o valor do ano).

**IN 1.888/2019 → DeCripto (IN RFB 2.291/2025):**
- IN 2.291/2025 **em vigor desde jan/2026**; **obrigação de enviar a DeCripto mensalmente começa em julho/2026** (e-CAC / Coleta Nacional).
- Novo limiar: **R$ 35.000/mês**.
- Em **exchange estrangeira/P2P**, **você** reporta; em nacional, a exchange reporta.
- Escopo ampliado: compra/venda/permuta, staking, mineração, airdrops, doações, transferências entre carteiras, empréstimos.

> **Custo de compliance operacional de um bot de alta frequência (lacuna preenchida na revisão).** Um bot que gera **milhares de operações/mês** que estouram o limiar precisa **gerar e submeter a DeCripto mensalmente** — e o **risco de erro em volume é alto**. Implicações práticas:
> - O reporte mensal não é trivial: exige consolidar milhares de eventos no layout exigido pela Coleta Nacional, todo mês, sem erro.
> - **Automatize a geração do arquivo de reporte** (módulo `tax/fiscal_log.py`) a partir do log fiscal append-only — não tente montar manualmente.
> - **Dimensione o esforço/tempo** desse compliance recorrente como um custo do projeto em produção (horas/mês + possivelmente honorários do contador por volume).
> - Erro/omissão em volume tem **risco de multa proporcional** — outra razão para o log fiscal ser requisito de primeira classe.

### 8.6 O que o BOT precisa registrar

Log fiscal **append-only**, em banco **e** CSV, com **fonte de verdade nos fills da exchange** (via API).

Por fill, no mínimo: `trade_id/order_id`; timestamp UTC + Brasília (define mês de competência); exchange + entidade (define regime); par + lado; quantidade + preço; **valor em BRL na data (cotação + fonte, congelada)**; **fees (e em qual ativo)**; **custo médio antes/depois**; **lucro/prejuízo realizado**; tipo de evento (trade/depósito/saque/staking/airdrop/conversão/**fee em BNB**).

**Relatórios automáticos:** resumo mensal por regime (checar teto R$ 35 mil); livro-razão de custo médio por ativo (incl. BNB); export anual para o contador; conversão BRL com cotação e fonte registradas.

> **Conversão BRL é a maior dor (e um ponto único de falha — ver §2.6 e §12).** Implemente desde o dia 1, **congele a cotação** por operação, com **fonte primária (PTAX) + fallback** definidos com o contador. Se ambas falharem, marque a operação como "câmbio pendente" e **bloqueie o fechamento contábil** até reconciliar — nunca grave um BRL estimado errado.

### 8.7 Checklist fiscal antes do dinheiro real

- [ ] Definir a **entidade da exchange** (nacional vs global).
- [ ] Contratar **contador especializado em cripto**; alinhar conversão BRL, fees, periodicidade, **tratamento da fee em BNB** e **questão PF vs atividade habitual**.
- [ ] **Log fiscal append-only** alimentado pelos fills reais.
- [ ] **Livro de custo médio rolante** por ativo (incl. BNB), com testes.
- [ ] Relatório mensal de volume de vendas + DARF estimado (4600).
- [ ] Export anual para DAA.
- [ ] **DeCripto obrigatória a partir de julho/2026** (e-CAC) se exchange estrangeira/P2P acima do limiar — **geração automatizada do arquivo**.
- [ ] Acompanhar **regulamentação da Binance no Brasil** (Lei 14.478 / VASPs / BCB).
- [ ] Revisar regras a cada ano.

### Fontes (Seção 8)
- [Mattos Filho — DeCripto / OCDE](https://www.mattosfilho.com.br/unico/decripto-receita-federal-ocde/) · [CEPEDA — IN RFB nº 2.291/2025](https://cepeda.law/instrucao-normativa-rfb-no-2-291-2025-declaracao-de-criptoativos-decripto/?lang=en) · [Coingape — DeCripto julho/2026](https://br.coingape.com/receita-federal-define-inicio-da-decripto-para-julho-de-2026/)
- [BlueConsult — IR cripto 2026](https://blueconsult.com.br/imposto-criptomoedas-brasil-2026/) · [DeclarandoBitcoin — Lei 14.754](https://www.declarandobitcoin.com.br/post/35-perguntas-e-respostas-sobre-a-lei-n%C2%BA-14-754-que-altera-a-tributa%C3%A7%C3%A3o-de-criptoativos-no-exterior) · [DeclarandoBitcoin — MP 1.303 derrubada](https://www.declarandobitcoin.com.br/post/mp-1303-derrubada-isen%C3%A7%C3%A3o-de-r-35-mil-para-criptomoedas-segue-v%C3%A1lida-em-2026)
- [Exame — MP 1.303 rejeitada](https://exame.com/future-of-money/mp-1-303-com-rejeicao-na-camara-tributacao-de-criptos-nao-vai-subir-em-2026-veja-regras-atuais/) · [Banco Central — Marco legal das VASPs (Lei 14.478)](https://www.bcb.gov.br/estabilidadefinanceira/criptoativos)

> **Reforço final:** este material orienta **o que registrar e o que perguntar**, não substitui um profissional.

---

## 9. Roadmap, Fases & Orçamento

> Tom honesto: o objetivo é provar (ou refutar) com dados se o LLM-gerente agrega valor, gastando o mínimo antes de arriscar dinheiro real. Custos consistentes com a Seção 2.

### 9.1 Visão geral das fases

| Fase | Nome | Objetivo central | Esforço | Custo/mês (USD) |
|---|---|---|---|---|
| **0** | Setup & esqueleto | Ambiente, chaves testnet, repo, CI | 1 sem (~10–15h) | ~US$ 0 |
| **1** | Bot mecânico em testnet | Loop de trade (grid), sem LLM | 2–3 sem (~30–40h) | ~US$ 0–6 |
| **2** | Trilhos + persistência + alertas | Segurança, DB, Telegram, **custo médio + log fiscal** | 1–2 sem (~15–25h) | ~US$ 6 |
| **3** | LLM-gerente integrado | GPT lê regime e ajusta via JSON | 2–3 sem (~25–35h) | ~US$ 6–8 |
| **4** | Teste A/B + métricas + auditoria de regime | Bot A vs Bot B vs hold | 3–6 sem coleta inicial; **8–12 sem* p/ conclusão** | ~US$ 10–15 |
| **5** | Go/No-Go + dinheiro real pequeno | Decisão com dados, capital mínimo | 2 sem + monitoramento | ~US$ 10–25 + capital |

> **\*** A janela de A/B de 3–6 semanas é **coleta inicial / primeira leitura**; a **conclusão Go/No-Go defensável exige 8–12 semanas + eventos de cauda suficientes** (§7.3). Não subestime o cronograma.

### 9.2 Definição do MVP

**MVP = conclusão da Fase 1 + trilhos críticos da Fase 2.** Sem LLM. Critério: *um bot mecânico que sobrevive a um fim de semana ligado na testnet sem travar nem estourar limites*.

**Dentro:** CCXT → Spot Testnet; 1 par (ETH/USDT); 1 estratégia (grid com re-centralização + `max_inventory`); loop com erro/reconexão; stop-loss global + kill-switch diário + limite de trades/dia; log estruturado.
**Fora:** LLM (Fase 3), múltiplos pares, dashboard, otimização sofisticada, dinheiro real.

### 9.3 Fase 0 — Setup

Repo + estrutura (§6.3); venv + lockfile (`ccxt`, `python-dotenv`, `pydantic`, `pytest`); conta testnet + chaves em `.env`; `scripts/ping_testnet.py` (sandbox, imprime saldo fake + preço); ruff + CI. **Pronto:** ping funciona, pytest passa, nenhuma chave no Git.

### 9.4 Fase 1 — Bot mecânico em testnet (SEM LLM)

Exchange wrapper (CCXT, retry, rate-limit); uma estratégia parametrizável **com re-centralização e `max_inventory` desde já**; loop resiliente; estado persistido; parâmetros 100% externalizados. **Pronto (= MVP com Fase 2):** roda **48h contínuas** sem crash, executa dezenas de micro-trades, log coerente.

### 9.5 Fase 2 — Trilhos + persistência + alertas + base fiscal

Trilhos (`risk/`, valores da §11); persistência SQLite (trades, equity, eventos); **livro de custo médio rolante (`cost_basis.py`) e log fiscal append-only (`tax/`) já nesta fase** (não deixar para depois — é onde mora o bug silencioso); câmbio BRL + fallback (`fx_rates.py`); alertas Telegram + `/status`. **Pronto:** injeção de queda dispara kill-switch + alerta; toda ordem no SQLite com PnL/taxa; reinício recupera estado sem ordens órfãs; **custo médio e câmbio testados**.

### 9.6 Fase 3 — LLM-gerente integrado

Coletor de contexto (§4.2); prompt do gerente; saída JSON validada (Pydantic, §4.3); aplicador com clamp e veto de re-centralização; **módulo de auditoria de regime (`regime_audit.py`, §4.5.1)**; logging completo; modelo mini/nano (config `LLM_MODEL`). **Pronto:** LLM em cron, JSON válido com fallback seguro, sugestão fora dos limites rejeitada e logada, log mostra "regime X → param Y mudou A→B → custo Z tokens".

### 9.7 Fase 4 — Teste A/B + métricas + auditoria

Dois bots em paralelo (contas separadas); baseline buy-and-hold; métricas (§7.4); **auditoria de acerto de regime (§4.5.1)**; dashboard simples (equity A vs B vs hold). **Coleta inicial 3–6 semanas; conclusão 8–12 semanas + ≥ ~5 eventos de cauda.** **Pronto:** dados contínuos no mesmo período; relatório comparativo; resposta clara para "B reduziu drawdown e/ou bateu o hold mais que A?" **e** "o LLM realmente acerta o regime?".

### 9.8 Fase 5 — Go/No-Go + dinheiro real pequeno

| Resultado na Fase 4 | Decisão |
|---|---|
| B bate hold **e** reduz drawdown vs A, líquido | **GO** com capital mínimo |
| B só reduz drawdown mas não bate hold | GO cauteloso se gestão de risco for o objetivo declarado |
| B não supera A nem hold | **NO-GO** — voltar à Fase 1/3 ou encerrar com aprendizado |

Se GO: testnet → mainnet (chaves com **saque OFF** + **IP whitelist** validado contra API real); recalibrar taxas reais; capital US$ 50–200; **base fiscal e câmbio funcionando**; **política de retirada / exposição máxima à exchange ativa**; "stop total" testado. **Pronto:** decisão documentada com números; bot real com capital mínimo, trilhos validados em produção, alertas e stop total funcionando.

### 9.9 Resumo do orçamento mensal por fase

| Fase | VPS | LLM | Outros | Total infra/mês |
|---|---|---|---|---|
| 0 | US$ 0 | US$ 0 | US$ 0 | **~US$ 0** |
| 1 | US$ 0–6 | US$ 0 | US$ 0 | **~US$ 0–6** |
| 2 | US$ 5–6 | US$ 0 | US$ 0 | **~US$ 6** |
| 3 | US$ 5–6 | centavos–US$ 1 | — | **~US$ 6–8** |
| 4 | US$ 6–12 | centavos–US$ 1 (até ~US$ 5 mini) | — | **~US$ 10–15** |
| 5 | US$ 6–12 | centavos–US$ 5 | + capital + **honorários contábeis/compliance** | **~US$ 10–25 + capital + contador** |

> Em produção, além de infra e capital, conte com **honorários do contador e o custo de compliance recorrente** (DeCripto mensal — §8.5). O LLM não é o gargalo; o VPS é o custo fixo recorrente; o maior dreno provável é a **taxa de ~0,1%/trade**.

### 9.10 Próximos passos imediatos (esta semana)

1. **Criar conta na Binance Spot Testnet** e gerar chaves; guardar em `.env`.
2. **Inicializar o repo** com a estrutura da §6.3 e o lockfile.
3. **Escrever e rodar `scripts/ping_testnet.py`** (sandbox, saldo fake + preço de ETH/USDT).
4. **Escolher o par do MVP (ETH/USDT)** e escrever os parâmetros no config (zero número mágico no código).
5. **Preencher o Registro da Seção 11 a frio** (drawdown diário, total, trades/dia, espaçamento, exposições) — a decisão de segurança mais importante, tomada antes de haver dinheiro em jogo.

### Fontes (Seção 9)
- [OpenAI — preços de API](https://openai.com/api/pricing/) · [Binance Spot Fee Rate](https://www.binance.com/en/fee/spotMaker) · [Best VPS for Crypto Trading Bots 2026 (BaCloud)](https://www.bacloud.com/en/blog/279/best-vps-servers-for-running-a-crypto-trading-bot-in-2026.html)

---

## 10. Resumo de Decisões Técnicas

**Arquitetura:**
- Três camadas com hierarquia rígida: trilhos (veto absoluto) > LLM-gerente (ajusta dentro dos limites) > bot mecânico (executa). LLM nunca executa nem afrouxa trilho.
- Ordem de avaliação: `dados → estratégia → trilhos → execução → registro`. LLM fora do loop quente.
- **Escopo honesto do LLM:** valor candidato em transições de regime de horas/dias; o crash de minutos é dos trilhos. Se os trilhos já capturam o benefício defensivo, a conclusão honesta é rodar só o Bot A.

**Estratégia:**
- **Grid trading** inicial em spot testnet, modo neutro, **par ETH/USDT** (avaliar ETH/BTC como mais lateral; critério de seleção em §3.3.0). MM descartado no início.
- **Espaçamento canônico 0,40%/nível** (§11), trilho mecânico.
- **Re-centralização e `max_inventory` obrigatórios** desde o início; **nunca re-centrar para baixo numa tendência**.
- Limit + post-only; market só nos trilhos (com ressalva de slippage em flash-crash).
- Backtest primeiro com fee (0,1% e 0,075%) + slippage + lookahead + walk-forward, três regimes, vs buy-and-hold.

**LLM-gerente:**
- Cadência base 4h (intensivo 1h opcional) + gatilhos por evento.
- Input JSON compacto pré-digerido (incl. `price_broke_grid`); output JSON validado com Pydantic (incl. `recenter_grid`). Clamp obrigatório; confiança < 0,5 rebaixa para `reduzir`.
- Modelo mini/nano, abstraído em config, **fixo durante cada janela de A/B** (depreciação invalida e reinicia).
- **Auditoria independente de acerto de regime (§4.5.1)** separada do A/B.

**Risco e segurança (valores canônicos na §11):**
- Stop-loss por posição 1,0–1,5%; kill-switch diário **-3%** (sticky, reset 00:00 UTC); circuit breaker total **-12%** (parada manual); exposição **50% total / 25% por moeda**; trades/dia **alerta 50 / teto 80**; **exposição máxima à exchange** + política de retirada.
- Fail-safe: na dúvida PARA. Máquina de estados `RUNNING → THROTTLE → SAFE → HALTED`.
- Robustez: `clientOrderId` idempotente, retry+backoff, 429/418, reconciliação no boot, estado persistido (incl. custo médio), UTC + `recvWindow`.
- Chaves: reading + spot ON, **saque OFF**, futures OFF, **IP whitelist ON** (datacenter validado contra API real); 2FA TOTP.
- Ressalva: **stop não é garantia de preço** (slippage do market order em flash-crash).

**Stack:**
- Python 3.13.x + asyncio; uv + lockfile.
- ccxt (async, sandbox; travado no lockfile); pandas/numpy + lib `ta` (MVP) → ta-lib.
- openai SDK + pydantic; APScheduler, SQLAlchemy + SQLite → PostgreSQL, alembic, structlog, python-telegram-bot v22.
- **Testes prioritários:** risk_guards, **state_reconciliation**, **cost_basis (incl. fee em BNB)**, fx_rates, grid_recenter.
- Deploy: Hetzner CX22 + Docker `restart: unless-stopped` + healthcheck; watchdog externo.

**Validação:**
- Pipeline 4 estágios; portões Go/No-Go pré-registrados (§11).
- A/B justo (mesmo binário, flag on/off; modelo fixo na janela); benchmark buy-and-hold; **8–12 semanas + ≥ ~5 eventos de cauda** para conclusão (a estatística que importa está na cauda, não no win rate).
- **Portão 1→2 não julga lucratividade absoluta** (testnet é sintética); lucratividade só no Estágio 2 (real).
- Tudo líquido de taxas e API. Decisão final: `Valor líquido do LLM = (Retorno_B − Custo_API_B) − Retorno_A`, complementada pela auditoria de regime.

**Economia e capital:**
- **Taxas de trade são o inimigo nº 1, e capital maior NÃO as resolve** (custo variável proporcional ao capital).
- BNB reduz 25% **mas** exige saldo de BNB, tem risco de expiração e **gera fato gerador tributável** — modelar também o cenário sem BNB.
- Infra ~US$ 5–8/mês (enxuto) a US$ 15–30/mês (confortável).
- Capital: piloto US$ 50–200; avaliação justa US$ 1.000–2.000; conforto US$ 5.000+. Abaixo de ~US$ 300 é irracional como negócio.

**Brasil (fiscal):**
- Decidir cedo a entidade da exchange.
- Isenção de R$ 35 mil/mês quase nunca protege bot de alta frequência.
- **Log fiscal append-only + livro de custo médio rolante (incl. BNB) + câmbio BRL congelado com fallback** são requisitos de primeira classe. DeCripto mensal desde julho/2026 (estrangeira/P2P) — **automatizar a geração** e dimensionar o **custo de compliance recorrente**.
- Validar **PF vs atividade habitual** e **regulamentação Binance/BCB** com o contador.
- Contratar contador especializado.

**Riscos adicionados na revisão (detalhe na §12):** depeg de USDT; risco de contraparte/exchange; slippage do kill-switch em flash-crash; latência + IP whitelist combinados; falha do provedor de câmbio BRL; compliance recorrente em volume; regulatório Binance/BCB; custo de oportunidade vs hold em bull market.

**Filosofia geral:**
- O objetivo primário é **aprender com rigor**, não ficar rico. O maior valor esperado do LLM é **defensivo** em regimes de horas/dias. O resultado mais provável e ainda valioso é uma conclusão honesta sobre se — e quando — o LLM reduz risco.

---

## 11. Registro de Premissas e Constantes (fonte única da verdade)

> Esta seção existe para **eliminar as contradições numéricas** apontadas na revisão. Todo número de risco/economia citado no resto do documento referencia este registro. **Preencher/confirmar a frio, antes de iniciar; nunca ajustar para justificar um resultado.**

| Constante | Valor canônico | Onde é usada |
|---|---|---|
| Espaçamento mínimo do grid | **0,40% por nível** | §2.3.1, §3.4, §3.5, §3.8 |
| Stop-loss por posição | **1,0%–1,5%** | §5.1 |
| Kill-switch drawdown diário | **-3% do equity do dia** (reset 00:00 UTC, sticky) | §1.5, §4.2, §5.1, §6.4 |
| Circuit breaker drawdown total | **-12% do equity de pico** (parada manual) | §1.5, §4.2, §5.1 |
| Exposição máxima total | **50% do equity** | §4.2, §5.1 |
| Exposição máxima por moeda | **25% do equity** | §4.2, §5.1 |
| Trades/dia — alerta | **50** | §2.3.2, §5.1 |
| Trades/dia — teto duro (kill de novas ordens) | **80** | §2.3.2, §4.2, §5.1, §6.4 |
| Taxa Binance — cenário-base de segurança | **0,10%/lado** (sem BNB) | §2.2, §2.3, §3.7, §7.5 |
| Taxa Binance — cenário otimista | **0,075%/lado** (com BNB) | §2.2, §2.3 |
| Modelo LLM inicial | **mini/nano** (config `LLM_MODEL`), fixo por janela de A/B | §2.4, §4.6 |
| Cadência LLM base | **4h** (intensivo 1h = exceção) | §4.1 |
| Par do MVP | **ETH/USDT** (avaliar ETH/BTC) | §3.3.0 |
| Capital — piloto real | **US$ 50–200** | §1.5, §2.8 |
| Capital — avaliação justa | **US$ 1.000–2.000** (conforto US$ 5.000+) | §2.8 |
| Janela A/B — coleta inicial | **3–6 semanas** | §7.3, §9.7 |
| Janela A/B — conclusão Go/No-Go | **8–12 semanas + ≥ ~5 eventos de cauda** | §7.3, §7.6, §9 |
| Fonte de câmbio BRL | **PTAX (primária) + fallback definido** | §2.6, §8.6 |
| Exposição máxima à exchange | **definir = capital que aceita perder por risco de contraparte** | §5.1, §5.4 |

---

## 12. Matriz Consolidada de Riscos

> Reúne os riscos do documento original **mais os adicionados na revisão** (técnicos, financeiros, regulatórios). Severidade: Baixa / Média / Alta.

| # | Risco | Categoria | Severidade | Mitigação |
|---|---|---|---|---|
| 1 | Taxas comendo o lucro | Financeiro | **Alta** | Espaçamento 0,40%; teto de 80 trades/dia; medir tudo líquido; **capital maior NÃO resolve** |
| 2 | Perder para buy-and-hold | Financeiro | Alta | Benchmark obrigatório; No-Go se não superar |
| 3 | **Custo de oportunidade vs hold em bull market** (novo) | Financeiro | Alta | Grid vende cedo e fica muito atrás do hold em tendência de alta sustentada — **o risco financeiro dominante para o usuário-alvo**. Quantificar no backtest de regime de alta; aceitar conscientemente; é parte do porquê de o objetivo ser aprendizado, não alfa |
| 4 | Bug / ordem órfã / queda de API | Técnico | Alta | Idempotência, reconciliação no boot, testes dedicados |
| 5 | Crash de mercado | Financeiro | Média-alta | Trilhos mecânicos (não LLM); stop global; drawdown diário |
| 6 | **Slippage do kill-switch em flash-crash** (novo) | Financeiro/Técnico | Média-alta | Market order derrapa exatamente no crash → drawdown realizado pode exceder o configurado. Preferir stop-limit com banda; dimensionar circuit breaker contando com isso; **stop não é garantia de preço** (§3.6) |
| 7 | **Depeg de USDT** (novo) | Financeiro | Média | Todo capital/PnL em USDT. Alerta crítico; em depeg severo, kill-switch + avaliar conversão; considerar diversificar a stable de denominação |
| 8 | **Risco de contraparte/exchange (Binance: hack/congelamento/insolvência/deslistagem)** (novo) | Financeiro/Regulatório | Média | Trilho de exposição máxima à exchange; política de retirada periódica de lucros para self-custody; aceitar conscientemente a concentração (§5.4) |
| 9 | LLM alucina parâmetro ruim | Técnico | Média | Pydantic + clamping; manter último config válido |
| 10 | **LLM lento demais para o crash / tese de valor frágil** (ampliado) | Conceitual | Média | Escopo do LLM redefinido para regimes de horas/dias; trilhos cobrem o crash; A/B + auditoria de regime decidem se o LLM se paga (§1.3, §4.5.1) |
| 11 | **Depreciação/mudança de modelo LLM** (novo) | Técnico | Média | Modelo em config; snapshot datado; **invalidar e reiniciar A/B** se o modelo mudar na janela (§2.4) |
| 12 | Overfitting em testnet/backtest | Metodológico | Média | Walk-forward, múltiplos regimes, sem ajuste olhando resultado |
| 13 | **Testnet sintética + decisão Go/No-Go** (ampliado) | Metodológico | Média-alta | Portão 1→2 usa só robustez + sinal *relativo* de A/B; lucratividade absoluta só no Estágio 2 real (§7.2) |
| 14 | **Amostra insuficiente de eventos de cauda** (novo) | Metodológico | Média | A estatística relevante está na cauda; exigir ≥ ~5 episódios de tendência/queda antes de afirmar proteção (§7.3) |
| 15 | **Latência + IP whitelist + restrição geográfica combinados** (novo) | Técnico | Média | Validar IP do datacenter contra API REAL antes de plano anual; plano B de datacenter/provedor/proxy (§2.5) |
| 16 | **Falha do provedor de câmbio BRL** (novo) | Técnico/Fiscal | Média | PTAX primária + fallback; se ambos caírem, marcar "câmbio pendente" e bloquear fechamento contábil (§2.6, §8.6) |
| 17 | **Complexidade fiscal da fee em BNB** (novo) | Fiscal | Média | Fee em BNB = alienação tributável; livro de custo médio separado para BNB; avaliar não usar BNB; `test_cost_basis` cobre o caso (§8.4) |
| 18 | **Custo/risco de compliance recorrente (DeCripto mensal em volume)** (novo) | Regulatório | Média | Automatizar geração do arquivo; dimensionar horas/honorários; risco de multa por erro em volume (§8.5) |
| 19 | **Regulatório Binance no Brasil (Lei 14.478/VASPs/BCB)** (novo) | Regulatório | Média | Acompanhar regulamentação; pode afetar acesso/KYC/operação para residentes (§5.4, §8.7) |
| 20 | **PF vs atividade habitual** (novo) | Regulatório/Fiscal | Média | Frequência/volume podem mudar o enquadramento; validar com contador antes do real (§1.6, §8.7) |
| 21 | Diferença testnet vs real (liquidez/slippage) | Metodológico | Média-alta | Capital mínimo no início; reavaliar métricas pós-migração |
| 22 | Vazamento/uso indevido de chave | Segurança | Média | Saque OFF; IP whitelist; 2FA TOTP; alerta de ordem fora do padrão |
| 23 | **Bug silencioso em reconciliação de estado / custo médio** (novo) | Técnico/Fiscal | Média-alta | Testes dedicados (`test_state_reconciliation`, `test_cost_basis`) como prioridade igual a `test_risk_guards` (§6.3) |

> **Leitura geral da matriz:** os riscos de severidade Alta concentram-se em **economia de taxas** e **custo de oportunidade vs hold** — ou seja, no *bot mecânico e no mercado*, não na camada LLM. Isso confirma a tese central do documento: a inteligência é barata e periférica; o dinheiro se ganha ou se perde na execução mecânica e na disciplina de não operar em regime ruim.
