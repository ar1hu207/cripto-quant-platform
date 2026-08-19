# Plano de Desenvolvimento — Plataforma de Trading Bots (Simulação)

**Data:** 2026-06-10 · **Objetivo:** plataforma funcional de **paper trading** onde você roda os bots, recebe propostas de trade, **confirma com valor + alavancagem que você definir**, e vê tudo num painel — pra testar estratégias, risco e agressividade **sem dinheiro real**, com os dados te guiando.

---

## 1. Visão do sistema

Um sistema que:

- **Acha os melhores trades** — engine que varre N criptos ao vivo e pontua oportunidades (score de convicção).
- **Propõe e você confirma** — notificação "Confirmar trade?" com os detalhes; você define **valor de entrada** e **alavancagem**; confirma ou pula. **Só simulação.**
- **Simula com realismo** — fills, taxas, funding, alavancagem, stops, liquidação — tudo modelado.
- **Mede tudo** — win rate por estratégia e por convicção, P&L, drawdown, Sharpe, taxa paga. Pra você **tunar** com dados.
- **Roda contínuo** — backend + banco de dados + interface web, dados reais da Binance.

> Filosofia: **plataforma de experimentação.** Você crank a o risco/alavancagem que quiser e a **realidade simulada** mostra o resultado — sem arriscar 1 centavo. Backtest e ao-vivo usam o **mesmo motor** (paridade).

---

## 2. Arquitetura técnica

```
┌─ FRONTEND (UI web, dark trading terminal) ───────────────────┐
│  dashboard · feed de sinais · MODAL "confirmar trade"        │
│  (valor + alavancagem) · posições · journal · métricas       │
└───────────────▲───────────────────────┬──────────────────────┘
                │ REST/WebSocket         │ confirma trade
┌───────────────┴───────────────────────▼──────────────────────┐
│  BACKEND (FastAPI)                                            │
│   /sinais  /propor  /confirmar  /posicoes  /journal  /config │
└───────────────▲───────────────────────┬──────────────────────┘
                │                        │
┌───────────────┴───────┐   ┌────────────▼──────────────────────┐
│  ENGINE (bots)        │   │  BANCO DE DADOS (SQLite)          │
│  scanner + estrategias│   │  sinais·trades·posicoes·equity·   │
│  + gestor de banca +  │   │  config·banca                     │
│  motor de simulacao   │   └───────────────────────────────────┘
└───────────▲───────────┘
            │ dados reais
      ┌─────┴─────┐
      │  Binance  │ (ccxt, dados publicos, sem chave)
      └───────────┘
```

---

## 3. Stack técnica

| Camada | Tecnologia | Por quê |
|---|---|---|
| Engine/bots | **Python** | já temos tudo (ccxt, pandas, estratégias, gestor) |
| Backend/API | **FastAPI** | rápido, async, docs automáticas, ideal pra o fluxo de confirmação |
| Banco de dados | **SQLite** | zero setup (arquivo local), perfeito pra começar; migra pra Postgres se precisar escalar |
| Frontend | **HTML + CSS + JS + Chart.js** | UI dark customizada (controle total, leve) |
| Tempo real | **WebSocket** (ou polling) | empurrar sinais/preços pro navegador ao vivo |
| Dados | **ccxt / Binance** | preços reais, públicos, grátis |

**Banco de dados:** começo com **SQLite** (não precisa de nada — é arquivo, embutido no Python). Se mais pra frente você quiser rodar em nuvem/multi-acesso, a gente migra pra **Postgres** (aí sim você providencia). Por ora, **não precisa de nada da tua parte.**

### Esquema do banco (simplificado)
```
sinais(id, ts, ativo, direcao, conviccao, motivos, preco, stop_sugerido, status)
trades(id, sinal_id, ativo, direcao, entrada, saida, valor_reais, alavancagem,
       ret_pct, pnl_reais, taxa, motivo_saida, aberto_em, fechado_em)
posicoes(id, ativo, direcao, entrada, valor_reais, alavancagem, stop, preco_atual, pnl, aberto_em)
equity(ts, banca, equity_total)
config(chave, valor)        -- risco, alavancagem padrão, limites, ativos
banca(id, nome, inicial, atual)
```

---

## 4. Fluxo de "Confirmar Trade" (o coração da tua experiência)

```
1. Engine detecta sinal      →  "LINK SHORT · convicção 72 · rompeu suporte, RSI 38"
2. UI mostra NOTIFICAÇÃO     →  card na fila "Confirmar" + som/alerta
3. Você vê os detalhes       →  ativo, direção, score, motivos, entrada e stop sugeridos
4. Você define              →  [ valor de entrada: R$___ ]  [ alavancagem: __x ]
5. Você decide              →  [ ✅ Confirmar ]   [ ❌ Pular ]
6. Confirmou → abre posição simulada  →  aparece no painel "Posições" com P&L ao vivo
7. Fecha (stop/alvo/regime) →  vai pro Journal com o resultado
```

Tudo simulado — dinheiro fictício, mercado real.

---

## 5. Os Sprints

> Cada sprint tem **objetivo**, **entregáveis** e um **checkpoint** (só avança quando o checkpoint passa). Esforço: P (pequeno), M (médio), G (grande).

### 🏗️ Sprint 0 — Fundação & Arquitetura · [M]
- **Objetivo:** estrutura limpa do projeto + banco + backend esqueleto.
- **Entregáveis:** reorganizar código em pacote; criar `db.py` (SQLite + esquema); FastAPI rodando com `/health`; camada de config.
- ✅ **Checkpoint:** `GET /health` responde, banco criado com as tabelas, projeto roda sem erro.

### 🧠 Sprint 1 — Engine de Sinais (os bots) · [G]
- **Objetivo:** formalizar as estratégias como plugins e o scanner que pontua oportunidades ao vivo.
- **Entregáveis:** estratégias plugáveis (trend, breakout, mean-reversion, scalp) com params configuráveis; engine que varre 10-15 criptos, pontua convicção, **grava sinais no banco**.
- ✅ **Checkpoint:** engine gera sinais pontuados pra 10+ moedas, persistidos no banco, visíveis via `GET /sinais`.

### ⚖️ Sprint 2 — Risco & Motor de Simulação · [G]
- **Objetivo:** transformar sinal confirmado em posição simulada com P&L real.
- **Entregáveis:** gestor de banca configurável (risco, **alavancagem**, stops, limites diários, liquidação); motor de simulação (abre/segura/fecha posição, taxa+funding+alavancagem); persistência de posições/trades.
- ✅ **Checkpoint:** um sinal vira posição simulada que abre e fecha certo, com P&L e taxa corretos no banco.

### 🔌 Sprint 3 — Backend API & Confirmação · [M]
- **Objetivo:** o fluxo completo propor → confirmar via API.
- **Entregáveis:** endpoints `/propor`, `/confirmar` (recebe valor + alavancagem), `/posicoes`, `/journal`, `/config`.
- ✅ **Checkpoint:** round-trip completo via API — propor um trade, confirmar com valor/alavancagem, posição abre na simulação.

### 🎨 Sprint 4 — Interface Funcional (UI/UX) · [G]
- **Objetivo:** a interface que você pediu — funcional, sustenta a operação.
- **Entregáveis:** UI dark (trading terminal); dashboard ao vivo; feed de sinais; **MODAL "confirmar trade"** com inputs de valor + alavancagem; painel de posições com P&L ao vivo; journal; notificações de sinal forte.
- ✅ **Checkpoint:** você assiste os sinais, recebe "confirmar trade?", define valor + alavancagem, confirma, e vê a posição aparecer — **tudo no navegador.**

### 📊 Sprint 5 — Métricas, Journal & Tunagem · [M]
- **Objetivo:** os dados pra você tunar e buscar mais lucro/risco com método.
- **Entregáveis:** painel de métricas (win rate **por convicção e por estratégia**, Sharpe, drawdown, P&L, taxa total); journal filtrável; comparador de configs.
- ✅ **Checkpoint:** depois de rodar, você vê claramente "convicção 70+ acerta X%, estratégia Y rende Z" pra ajustar.

### 🔁 Sprint 6 — Backtest Integrado & Validação · [M]
- **Objetivo:** testar qualquer config no passado com o MESMO motor (paridade).
- **Entregáveis:** modo backtest no mesmo pipeline; validação walk-forward; relatório multi-ativo/multi-período.
- ✅ **Checkpoint:** qualquer estratégia/config roda em backtest E em paper com o mesmo código, resultados consistentes.

### 🛡️ Sprint 7 — Robustez & Operação Contínua · [M]
- **Objetivo:** rodar dias sozinho sem quebrar.
- **Entregáveis:** auto-restart, recuperação de estado, logs, alertas (Telegram opcional); portfólio multi-estratégia + alocação por regime.
- ✅ **Checkpoint:** sistema roda dias ininterrupto, sobrevive a reinício, registra tudo.

### 🤖 Sprint 8 (opcional) — LLM como camada de contexto · [M]
- **Objetivo:** testar se a LLM melhora o edge (Bot A vs Bot B).
- **Entregáveis:** camada LLM (regime/sentimento/notícias) + harness de teste A/B. (Precisa de chave OpenAI — custa API.)
- ✅ **Checkpoint:** comparação A/B com dados — a LLM agrega ou só queima token?

---

## 6. Resumo do caminho

```
Sprint 0  fundação + banco + backend
Sprint 1  bots + engine de sinais (acha os trades)
Sprint 2  risco + simulação (vira posição com P&L)
Sprint 3  API + fluxo confirmar
Sprint 4  INTERFACE funcional (confirmar trade no navegador)  ← marco grande
Sprint 5  métricas + tunagem
Sprint 6  backtest integrado
Sprint 7  robustez 24/7
Sprint 8  LLM (opcional, A/B)
```

Os Sprints 0-7 são **grátis** (dados públicos + simulação). Só o 8 (LLM) custa API.

**Banco de dados:** SQLite — **não precisa providenciar nada agora.** Se for escalar pra nuvem depois, aí pedimos Postgres.

---

## 7. Próximo passo

Começar pelo **Sprint 0** (fundação: estrutura + banco SQLite + FastAPI esqueleto). É a base que sustenta todo o resto. Aproveito boa parte do que já construímos (estratégias, gestor, scanner, motor).
