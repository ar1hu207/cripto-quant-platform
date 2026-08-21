# Investigação de lógica — 2026-08-19

> Segunda passada da investigação geral (a primeira, de infra/deploy, está em
> `STATUS-SISTEMA-2026-08-19.md`). Aqui o foco é **lógica de negócio**: ciclo de vida de
> sinal e posição, guardas de risco, sizing, funding, métricas e as práticas de engenharia
> que o projeto deveria adotar. Cada achado virou um card no Trello (quadro *Trading Bot*),
> série `[P1-6..9]` e `[P2-8..18]`, com critério de aceite verificável.

## O projeto, como eu o entendo

Plataforma de **pesquisa quant + paper trading** de cripto: dinheiro fictício, preço real
(Binance via ccxt). Um worker de 15s marca posições, fecha em stop/trailing/liquidação,
varre sinais (tendência + reversão pontuadas por `scoring.py`) e alimenta um auto-trader
experimental. A honestidade intelectual é explícita no código: o walk-forward + DSR
(`validacao.py`) mostrou que a estratégia de confluência **não tem edge comprovado**, e o
auto-trader existe para *ver o "no edge" acontecer ao vivo* dentro de guardas de risco
(trava diária, teto de risco aberto, teto de margem) — não para ganhar dinheiro. O valor
do sistema está na infraestrutura de pesquisa e nas guardas, não no alfa.

Isso define o que é sagrado aqui: **as guardas de risco e a paridade backtest↔live**.
A maioria dos achados abaixo é exatamente onde a lógica trai uma dessas duas coisas.

## O que verifiquei e está CORRETO (para não reabrirmos)

| Verificação | Resultado |
|---|---|
| Paridade do backtest (auditoria de junho, itens 1-2) | ✅ fechada de verdade: decisão no candle fechado `i`, fill no `open[i+1]` + slippage, empate stop×liq pelo mais perto da entrada (`backtest_plataforma.py:39-66`) |
| Símbolo spot no `binanceusdm` | ✅ `fetch_funding_rate_history("BTC/USDT")` resolve para `BTC/USDT:USDT` (testado ao vivo) — não há bug de mapeamento |
| Conversão de timestamp naive → epoch em `_funding_custo` | ✅ desvio de 2 ms (testado) — correta com o fuso da VM em America/Sao_Paulo |
| Atualização da banca em `fechar()` | ✅ o `SELECT` da banca acontece dentro da transação de escrita já iniciada — SQLite serializa; sem lost update |
| Warmup dos indicadores | ✅ guardado no call-site (`i >= 60` no live e no backtest); NaNs de Bollinger/Donchian barrados pelos `isnan` |
| Liquidação vs stop no live | ✅ empate resolvido pelo mais perto da entrada, coerente com o backtest |
| Trava diária sticky | ✅ não destrava no mesmo dia, reseta na virada |

## Achados → tickets

### Lógica com risco real (P1)

| Card | Achado | Onde |
|---|---|---|
| **[P1-6]** | `abrir()` não checa o status do sinal: confirmar 2× (duplo clique, ou corrida manual×auto-trader) abre **duas posições** do mesmo sinal; sinal pulado ainda é confirmável | `simulador.py:117-120` |
| **[P1-7]** | `/panico` fecha tudo mas **não desliga o auto-trader**: outros ativos reabrem em ~15s, os mesmos em 30min (cooldown). Kill-switch que se desmata | `api.py:369-382` |
| **[P1-8]** | `POST /config` aceita qualquer chave e valor sem validação; um `risco_por_trade: "abc"` faz `float()` explodir em `guarda_risco` → **todo `/estado` vira 500 e o worker erra a cada ciclo** até correção manual | `api.py:404-408` → `simulador.py:76-77` |
| **[P1-9]** | Dedupe de sinais **sem janela temporal**: o último sinal de (ativo,tf,tipo) — de qualquer idade e status — suprime a re-emissão se a direção e a convicção (±10) se mantêm. Com freshness de 12min no auto-trader, tendência persistente = fila seca. E sinais `novo` nunca expiram | `signal_engine.py:207-216`, `autotrader.py:115` |

### Lógica com risco menor / qualidade (P2)

| Card | Achado | Onde |
|---|---|---|
| **[P2-8]** | Piso de R$10 no sizing **fura o `risco_por_trade`** em banca pequena (banca 100 → risco 3,3× o configurado) | `autotrader.py:58` |
| **[P2-9]** | Portão de fluxo **falha-aberto**: `book()` → `None` → sinal passa sem a checagem e sem anotação | `signal_engine.py:74-82` |
| **[P2-10]** | Falha de rede **zera o funding silenciosamente** (`except: return 0.0`, sem log) — em prod hoje (451) todo fechamento teria funding 0; e o backtest tem `funding_8h` mas os chamadores usam o default 0 | `simulador.py:32-33`, `validacao.py` |
| **[P2-11]** | `equity` cresce sem limite (5.760 linhas/dia), o gráfico mostra só ~2h (500×15s), `metricas()` lê a tabela inteira, zero índices | `api.py:61-63,268`, `db.py` |
| **[P2-12]** | `/reset` não limpa `trava_dia_em` (sistema "resetado" continua travado até amanhã) nem decide sobre DCA | `api.py:236-242` |
| **[P2-13]** | `/estado` faz **chamada de rede por plano DCA a cada poll de 3s**; `aportar()` segura transação aberta durante fetch | `dca.py:27-38,62-67` |
| **[P2-14]** | Recusa pelo teto de margem vira **HTTP 500** no `/confirmar` (`ValueError` de `abrir()` não capturado; o pre-check cobre trava e risco, não margem) | `api.py:349-366`, `simulador.py:142-146` |
| **[P2-15]** | `ultimo_scan.ultimo_erro` nunca é limpo (scan verde segue exibindo erro velho) e a cadência do scan deriva quando o ciclo falha | `signal_engine.py:188`, `api.py:54` |
| **[P2-18]** | Fill otimista no stop ao vivo: gap entre polls fecha **no preço do stop**, não no preço real — paper superestima; o backtest já tem slippage, o live não | `simulador.py:238-244` |

### Melhores práticas (P2)

| Card | Proposta |
|---|---|
| **[P2-16]** | Organizar o repositório: 50+ arquivos na raiz misturam plataforma viva (11 módulos), pesquisa viva (backtest/validação) e **legado das fases 1-2** (`estrategias/`, `motor*.py`, `live_engine.py`, `run_*.py`, 15+ scripts). E há **dois "config fonte-única da verdade"** concorrentes: `config.py` (dataclass, legado) × `db.CONFIG_PADRAO` (o real). Num projeto AI-first isso é convite a erro de agente |
| **[P2-17]** | Criar `CLAUDE.md` + `ARQUITETURA.md`: convenções (timestamps naive em hora de SP, config via banco, dinheiro fictício/preço real), invariantes de risco que nunca se relaxam sem decisão humana, comandos, fluxo de deploy, processo de tickets. É o que faz "desenvolvido com IA" não depender da memória de uma sessão |

*(O ticket de testes automatizados já existe: `[P2-6]`.)*

## Mapa de dependências levantado (base do P2-16)

```
PLATAFORMA (viva):  api → {db, simulador, signal_engine, mercado, dca, autotrader}
                    simulador → {db, alertas};  signal_engine → {db, mercado, scoring}
                    scoring → indicadores;  todos → logbot
PESQUISA (viva):    validacao, tune, validar_oos, validar_reversao*, validar_swing
                    → backtest_plataforma → {dados, scoring}
LEGADO (fases 1-2): estrategias/ ← {live_engine, monte_carlo, otimizar_risco,
                    run_backtest, run_portfolio*, validar, validar_fase2,
                    validar_periodos_fase2} · motor*, dashboard, estrategia, execucao,
                    gestao_banca, metricas, scanner, backtest, backtest_funding,
                    scalp_backtest, dca_backtest, experimentos, funding_estudo, sweep,
                    projecao*, multi_ativo, config.py, Procfile (Railway)
```
