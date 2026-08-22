# Investigação de lógica de trade — 2026-08-19

> Terceira frente da investigação geral (infra em `STATUS-SISTEMA-2026-08-19.md`, lógica de
> negócio em `INVESTIGACAO-LOGICA-2026-08-19.md`). Aqui: **a matemática e o fundamento das
> operações** — P&L, liquidação, sizing, alavancagem, políticas de saída, scoring, estatística
> de validação e coerência com a própria base de conhecimento do projeto. Achados → cards
> `[P1-10..11]` e `[P2-19..24]` no Trello.
>
> **Nota de 2026-08-22:** os cards `[P2-19..24]` citados aqui foram renumerados para
> **`[P2-29..34]`** no Trello — a série do redesign do front reusou a numeração. Este documento
> é um registro datado de 2026-08-19 e fica como estava; quem procurar os cards, procure a série
> nova, ou melhor, o shortLink.

## Método

Leitura integral de `simulador`, `scoring`, `indicadores`, `autotrader`, `backtest_plataforma`,
`validacao`, `dados`, `tune`, `validar_oos` + cruzamento com `BASE-CONHECIMENTO-TRADING.md`,
`ITEM1-VALIDACAO-RIGOROSA.md` e `REVISAO-ITEM1.md`; e **quantificação empírica** com os dados
locais (cache de candles + `trading.db` com 56 trades do período de paper em junho).

## O que verifiquei e está CORRETO

| Verificação | Resultado |
|---|---|
| P&L linear de perp USDT-M (`move = d·(saída/entrada−1)`, `bruto = margem·lev·move`) | ✅ correto para contrato linear |
| Cap de perda na margem (nunca perde mais que `valor_reais`) | ✅ aplicado em `_pnl` e re-aplicado após funding |
| Modelo de liquidação `0.9/lev` vs fórmula real (`1/lev − mmr`) | ✅ aproximação **conservadora** (liquida ~0,5 p.p. antes): lev 10 → 9,0% vs ~9,6% real; lev 20 → 4,5% vs ~4,6% |
| Indicadores de Wilder (ATR/ADX/RSI via `ewm(alpha=1/n)`), Bollinger `ddof=0`, Donchian shiftado | ✅ construção canônica; warmup guardado no call-site (`i≥60`) |
| Fórmula do DSR (Bailey & López de Prado) | ✅ correta — confirmado também pela revisão externa (`REVISAO-ITEM1.md` §A.3: *"a fórmula está certa; a aplicação, não"* — ver [P2-19]) |
| Walk-forward escolhe config **só no treino** | ✅ estrutura honesta (`validacao.py:137-141`) |
| Sinal do funding (LONG paga rate>0, SHORT recebe) no live e no backtest | ✅ coerente nos dois |
| Sizing sinal→abertura (stop recomposto mantém distância relativa) | ✅ risco dimensionado ≈ risco aberto |
| Viés da taxa sobre nocional de entrada (vs saída real) | ✅ desprezível (~fee·|move|·nocional ≈ centavos/trade) |
| Cache de dados com data no nome do arquivo | ✅ janela reproduzível por dia (conserto da auditoria de junho) |

## Achado nº 1 — A política de saída que roda ao vivo NUNCA foi backtestada

O walk-forward que deu o veredito "sem edge" (370 trades OOS, win 25,4%, DSR 0,004) testou a
política de saída do backtest: **stop fixo de 3×ATR ou flip de regime** (`backtest_plataforma.py:73-76`).

O sistema ao vivo **nunca operou essa política**:

- Os 56 trades locais saíram por **`auto-saida`** (scalp em reversão com lucro): 49 de 56, ganho
  médio **+R$3,53**, contra 7 stops de **−R$18,25** — perda média **5,2×** o ganho médio, win 87,5%.
  A distribuição é incompatível com a validada (win 25,4%) porque **é outra estratégia**
- Hoje o default mudou de novo: `trailing_ativo=1` desliga o auto-fechar (`autotrader.py:75`) e a
  saída vira **trailing de 2%** — uma terceira política, também sem nenhum backtest (o
  `backtest_ativo` não tem trailing)
- O trailing de 2% é **fixo em espaço-preço**: cego ao ATR do ativo (o stop de entrada é 3×ATR,
  o de saída não) e cego à alavancagem (2% de preço = 4% de ROE a 2x, 40% a 20x). O `alvo_roe=5`
  do gestor de saída tem o problema espelhado (fixo em ROE, dispara com 0,25% de preço a 20x)

O perfil +pequeno/−grande dos 56 trades é exatamente a assinatura que a própria base de
conhecimento manda vigiar (§2.5, "grid = vender opções"). Pode até ser lucrativa — **ninguém mediu**.
→ **[P1-10]**

## Achado nº 2 — Alavancagem por convicção ignora a geometria stop×liquidação

`_alavancagem()` escala lev 2→20 pela convicção sem olhar o `stop_dist = 3·ATR/c`. Quando
`stop_dist > 0.9/lev`, a liquidação fica **mais perto que o stop**: o stop é inalcançável, a perda
vira ~a margem inteira, e o trade é binário. Medido no cache local (% das barras em que isso
acontece no teto lev=20 / e em lev=10):

| ativo/tf | stop p50 | stop p95 | % barras binárias @20x | @10x |
|---|---|---|---|---|
| BTC 15m | 0,74% | 1,64% | 0,0% | 0,0% |
| SOL 1h | 2,65% | 4,73% | **7,0%** | 0,0% |
| DOGE 1h | 2,79% | 4,83% | **7,7%** | 0,0% |
| AVAX 1h | 2,90% | 4,56% | **5,5%** | 0,1% |
| SUI 1h | 3,59% | 5,86% | **21,5%** | 1,0% |
| NEAR 1h | 3,73% | 9,19% | **34,4%** | 6,2% |
| INJ 1h | 3,67% | 9,50% | **37,2%** | 6,1% |

E a perversão do desenho: convicção **maior** → lev maior → **mais** provável o trade ser binário.
O orçamento de risco não estoura (o sizing já assume perda = margem nesse caso), mas as métricas
de win-por-convicção ficam contaminadas por liquidações e o "stop de 3×ATR" vira ficção nos alts
de 1h. Nos 56 trades locais a lev variou de 2x a 20x — o mecanismo está ativo. → **[P1-11]**

## Achado nº 3 — A régua estatística tem plano de conserto escrito, revisado… e não implementado

`validacao.py` continua sendo a "Onda 3". Os defeitos que o próprio projeto já documentou
(`ITEM1-VALIDACAO-RIGOROSA.md` + `REVISAO-ITEM1.md`) seguem no código: IC iid sobre trades de 12
moedas **correlacionadas** tratados como independentes, DSR sobre o pool pseudo-independente
(infla — direção anti-conservadora), sem MDS/análise de poder ("instrumento sem poder emite 'não
tem edge' para tudo"), sem sensibilidade a `n_trials`. A revisão é explícita (linha 140): *"o
veredito negativo atual é mais fraco do que o documento acredita"*. → **[P2-19]**

E na mesma pasta, `tune.py` e `validar_oos.py` — a metodologia **pré**-honestidade (caça de config
full-sample + "OOS" por moedas no mesmo período) — continuam executáveis e imprimindo
*"edge ROBUSTO ✅"*. Num projeto AI-first, é uma armadilha armada para uma sessão futura calibrar
a plataforma com data-snooping. → **[P2-20]**

## Achado nº 4 — Os defaults de risco contradizem a própria base de conhecimento

| Parâmetro vivo | Default | O que a base diz |
|---|---|---|
| `risco_por_trade` | **3%** | tabela §5: 0,5–1% conservador, 1–2% moderado (3% nem aparece) |
| `alavancagem_padrao` / teto auto | **10x / 20x** | §5.4: "2x sempre pior que 1x" (medido no próprio projeto); único sobrevivente: trend **sem** alavancagem |
| 5 slots × 3% | 15% | > teto `risco_aberto_max` 10% — o teto manda, tensão não documentada |

O experimento "ver o no-edge acontecer" justifica agressividade deliberada — mas em lugar nenhum
está escrito que os defaults são deliberadamente agressivos e qual seria o perfil conservador.
→ **[P2-21]** (documentar no catálogo de config do [P1-8] e no CLAUDE.md do [P2-17])

## Achados menores

- **Portão de fluxo é invalidável retroativamente** (não há book/taker histórico) — roda ao vivo
  sem evidência em nenhuma direção. Proposta: validação **prospectiva** (logar sinais rejeitados
  por fluxo + desfecho hipotético). → **[P2-22]**
- **Paridade de portfólio inexistente**: o vivo mistura 24 moedas × 3 TFs numa fila com 5 slots,
  cooldown e tetos (win por TF nos 56 locais: 5m 89%, 15m 81%, 1h 100%); o backtest é por-ativo,
  1 posição, tamanho fixo. Curva/drawdown/trava diária nunca foram simulados. → **[P2-23]**
- **Micro-realismo** (pacote): mmr na liquidação; taxa de saída sobre nocional de saída; funding
  sobre nocional corrente; **último candle do cache pode ser o em formação** (truncar no
  download); risco-até-o-stop ignora taxas (2% da margem a 20x). → **[P2-24]**
- Nota (sem ticket): o fator "gap de EMAs" soma até 10 pts de convicção sem entrar em
  `motivos`/`n_fatores` — os buckets de win-por-convicção misturam um fator invisível; entra na
  calibração geral (item 6 da auditoria de junho, ainda aberto).

## Mapa achado → ticket

| Card | Título curto | Labels |
|---|---|---|
| [P1-10] | Política de saída viva nunca backtestada (auto-saida/trailing × flip validado) | P1 · pesquisa-quant · toca-risco |
| [P1-11] | Cap geométrico de alavancagem (liq antes do stop em alts 1h) | P1 · backend · pesquisa-quant · toca-risco |
| [P2-19] | Implementar os consertos da régua (Item 1 revisado) | P2 · pesquisa-quant |
| [P2-20] | Aposentar tune.py / validar_oos.py (vereditos enganosos) | P2 · pesquisa-quant |
| [P2-21] | Defaults de risco × base de conhecimento — alinhar ou declarar | P2 · pesquisa-quant · toca-risco |
| [P2-22] | Validação prospectiva do portão de fluxo | P2 · backend · pesquisa-quant |
| [P2-23] | Backtest de portfólio (paridade da dinâmica multi-ativo) | P2 · pesquisa-quant |
| [P2-24] | Micro-realismo do modelo de execução (pacote) | P2 · backend · pesquisa-quant |
