# Plano de Desenvolvimento & Arquitetura — Bot Multi-Estratégia com Gestão de Banca

**Data:** 2026-06-10 · **Foco:** day trade (swing permitido) · **Validação:** backtest grátis → testnet → real

Este documento é o planejamento técnico do sistema. Ele assume o que **já aprendemos com dados reais** no backtest anterior (ver `PLANO-PROJETO-CRYPTO-BOT.md` para o contexto de negócio).

---

## 1. Objetivo e princípios (não-negociáveis)

**Objetivo:** um sistema intradiário com **portfólio de estratégias** e **gestão de banca inteligente**, buscando **expectativa positiva + consistência** — NÃO "lucro todo dia" (impossível; é resultado, não meta).

**Princípios que governam toda decisão:**

1. **Ceticismo com dados.** Nada entra em produção sem bater o buy-and-hold **líquido de taxa**, em **vários ativos** e **vários períodos** (bull + bear). Número bonito em amostra pequena = lixo.
2. **Disciplina de taxa.** Já provamos: alta frequência morre na taxa. Logo: **ordem maker primeiro**, poucos setups de qualidade, edge por trade > taxa.
3. **Risco em primeiro lugar.** O **Gestor de Banca** é o coração. Ele, não os sinais, é quem produz consistência.
4. **Paridade backtest↔produção.** O mesmo núcleo (estratégias → gestor → execução) roda no backtest e ao vivo; só trocam a *fonte de dados* e o *backend de execução*. Evita o bug clássico de "funcionava no backtest".
5. **Modularidade.** Estratégias são *plugins* com interface comum. Adicionar/remover uma não mexe no núcleo.
6. **Validação grátis primeiro.** Backtest (R$0) → Testnet (R$0) → dinheiro real pequeno. Nessa ordem, sempre.
7. **Alavancagem é variável de teste, não premissa.** Começa em 1x (dados mostraram que mais alavancagem só piorou). Só sobe se o backtest provar que melhora o retorno **ajustado ao risco**.

---

## 2. Lições do backtest anterior (já incorporadas)

| Lição (com dado) | Como o plano responde |
|---|---|
| 1h trend = 289 trades, 33% da banca em taxa → perdeu | Maker-first + estratégias seletivas + métrica de taxa sempre visível |
| 2x/3x deram retorno PIOR e drawdown PIOR que 1x (100% dos casos) | Default 1x; alavancagem só via teste A/B explícito |
| ETH diário +137% era sorte (8 trades, não replicou em BTC/SOL/BNB) | Validação obrigatória multi-ativo + multi-período |
| Filtro MA200 piorou em 7/9 casos | Não adicionamos nada por "parecer inteligente" — só o que o dado aprova |
| Trend-following lag feio em bull (fez 1/6 do B&H) | Portfólio diversificado por regime (mean-reversion, breakout) |

---

## 3. Arquitetura de software

### 3.1 Visão em camadas

```
   FONTE DE DADOS                      BACKEND DE EXECUÇÃO
   (histórico | tempo real)            (simulado | CCXT testnet | CCXT real)
          │                                      ▲
          ▼                                      │
   ┌──────────────────────── NÚCLEO (igual em backtest e live) ───────────────┐
   │                                                                          │
   │  [Estratégias]  →  [Gestor de Banca]  →  [Roteador de Execução]          │
   │   plugins           risco/sizing          maker-first + trilhos          │
   │   geram Sinal       decide tamanho        emite ordem                    │
   │                     e se PODE operar                                     │
   └──────────────────────────────────────────────────────────────────────────┘
          │
          ▼
   [Métricas / Logs / Estado persistente]
```

A chave: o **Núcleo** não sabe se está no backtest ou ao vivo. Ele recebe candles e um objeto `Execucao` (que no backtest é simulado, ao vivo é CCXT). Isso garante a paridade.

### 3.2 Estrutura de pastas (alvo)

```
Pesquisas/1/
├── config.py                # FONTE ÚNICA DA VERDADE (todos os parâmetros)
├── dados.py                 # download + cache (já existe)
├── indicadores.py           # EMA, ATR, ADX, RSI, Bollinger... (já existe, expandir)
├── estrategias/
│   ├── base.py              # interface Estrategia + dataclass Sinal
│   ├── trend.py             # trend-following (refatorar a atual p/ cá)
│   ├── mean_reversion.py    # NOVA — reversão à média (RSI/Bollinger)
│   └── breakout.py          # NOVA (fase posterior) — rompimento
├── gestao_banca.py          # ★ Gestor de Banca (risco, sizing, limites diários)
├── execucao.py              # interface Execucao: Simulada (backtest) e CCXT (live)
├── motor.py                 # núcleo: orquestra estratégias→gestor→execução
├── metricas.py              # retorno, Sharpe/Sortino, DD, win rate, profit factor...
├── run_backtest.py          # ponto de entrada do backtest
├── run_testnet.py           # ponto de entrada do paper trade (fase posterior)
└── dados_cache/             # CSVs em cache
```

### 3.3 Interface de estratégia (contrato comum)

```python
# estrategias/base.py
from dataclasses import dataclass

@dataclass
class Sinal:
    direcao: int       # +1 long, -1 short, 0 sem sinal
    stop: float        # preço de stop -> DEFINE o risco do trade
    qualidade: float   # 0..1 confiança do setup (p/ priorizar e dimensionar)
    motivo: str

class Estrategia:
    nome: str
    def preparar(self, df):      # calcula os indicadores próprios na série
        ...
    def avaliar(self, df, i):    # -> Sinal para a barra i (sem olhar o futuro!)
        ...
```

Cada estratégia é independente, testável sozinha, e plugável. O motor itera os candles e pergunta a cada estratégia: "qual seu sinal agora?".

---

## 4. O Gestor de Banca (a estrela) — regras concretas

Tudo parametrizado em `config.py`. Valores iniciais (conservadores):

```python
RISCO_POR_TRADE   = 0.005   # 0,5% da banca por trade
LIMITE_PERDA_DIA  = 0.02    # -2% no dia -> PARA até o dia seguinte
META_LUCRO_DIA    = 0.03    # +3% no dia -> reduz risco/para (protege o verde) [opcional]
MAX_POSICOES      = 2       # nº máximo de posições simultâneas
MAX_RISCO_ABERTO  = 0.015   # soma do risco aberto <= 1,5% da banca
KILL_SWITCH_DD    = 0.20    # drawdown total -20% -> para tudo, revisão manual
ALAVANCAGEM       = 1.0     # começa em 1x
```

**Dimensionamento por risco (o núcleo da "banca segura"):**
```
risco_em_$      = banca_atual * RISCO_POR_TRADE
distancia_stop  = |preco_entrada - stop| / preco_entrada      # em %
tamanho_nocional = risco_em_$ / distancia_stop
```
→ Se o stop bater, a perda é **sempre ~0,5% da banca**, não importa o ativo nem a volatilidade. Stop largo = posição menor; stop curto = posição maior. Risco constante.

**Controles diários (o que cria a consistência):**
- `pnl_dia <= -LIMITE_PERDA_DIA` → **trava o dia** (mata revenge trade / death spiral).
- `pnl_dia >= META_LUCRO_DIA` → reduz risco à metade ou para (protege o dia verde). *[opcional/debatível — testaremos com e sem]*
- Risco aberto total respeita `MAX_RISCO_ABERTO`; novas entradas são recusadas se estourar.

**Consciência de correlação:** BTC/ETH/SOL andam juntos. 3 longs correlacionados ≈ 3× o risco. O gestor trata exposição correlacionada como risco somado, não independente.

**Composição:** o risco é sempre % da banca **atual** — cresce nos ganhos, encolhe nas perdas (proteção automática em maré ruim).

---

## 5. As estratégias do portfólio (uma de cada regime)

Adicionadas **uma por vez**, cada uma validada sozinha antes de entrar no portfólio.

| Estratégia | Regime onde ganha | Lógica base |
|---|---|---|
| **Trend-following** (temos) | tendência | EMA cruzamento + ADX; entra a favor, trailing stop |
| **Mean-reversion** (próxima) | lateral/choppy (maioria do tempo intradiário) | RSI/Bollinger: compra sobrevendido, vende sobrecomprado; stop fora da banda |
| **Breakout** (depois) | explosão de volatilidade | rompimento de range (Donchian) com confirmação de volume/volatilidade |

**Regra de ouro:** cada estratégia precisa, sozinha, bater o buy-and-hold líquido de taxa em multi-ativo/multi-período. A que não passar, **não entra** — diversificar com estratégia ruim só adiciona ruído e taxa.

---

## 6. Execução & taxas (maker-first)

- **Maker primeiro:** ordens limite que adicionam liquidez (taxa ~0,02% vs ~0,05% taker). Round-trip maker ~0,04%.
- **Modelo honesto de fill no backtest:** ordem maker só é considerada preenchida se o preço **negociar através** do limite; assumimos uma taxa de não-preenchimento (nem toda maker enche). Sem isso, o backtest mente a favor.
- **Slippage:** modelado (pequeno, mas presente) para taker e em gaps.
- **Funding** (se usarmos futuros): contabilizado por posição mantida.

---

## 7. Métricas & critérios de sucesso

`metricas.py` reporta sempre:
- Retorno total e **vs buy-and-hold (líquido de taxa)** — o benchmark que importa
- **Expectativa por trade**, profit factor, win rate, ganho médio / perda média
- **Sharpe e Sortino** (retorno ajustado ao risco)
- **Max drawdown** e duração
- **% de dias verdes**, melhor/pior dia, sequência de perdas
- **Taxa total paga** e **custo de API** (quando houver LLM)

**Portões Go/No-Go (AND, todos obrigatórios):**

| De → Para | Critério |
|---|---|
| Estratégia entra no portfólio | bate B&H líquido de taxa em ≥ 3 ativos e ≥ 2 períodos (bull+bear) |
| Backtest → Testnet | portfólio + gestor com Sharpe > 1, max DD < 25%, em walk-forward fora da amostra |
| Testnet → Real | roda estável semanas, execução fiel, bate B&H no período, drawdown sob controle |

**Anti-overfitting:** validação **walk-forward** (otimiza num pedaço, testa no pedaço seguinte que nunca viu). Resultado in-sample não conta.

---

## 8. Roadmap de desenvolvimento (fases)

```
FASE 0 — Refatoração p/ a arquitetura modular
   • config.py (parâmetros) + estrategias/base.py (interface) + metricas.py + execucao.py
   • migrar a trend-following atual p/ estrategias/trend.py
   ✓ pronto: backtest antigo roda igual, mas na estrutura nova

FASE 1 — Gestor de Banca  ★ a peça que você mais quer ★
   • gestao_banca.py: risco fixo, sizing por ATR, limite de perda diária, trava de lucro
   • integra com a trend-following e re-backtesta
   ✓ pronto: curva mais suave, dias vermelhos pequenos, DD menor que a v1

FASE 2 — Estratégia mean-reversion + portfólio de 2
   • estrategias/mean_reversion.py, validada sozinha (multi-ativo/período)
   • roda as 2 juntas sob o gestor de banca
   ✓ pronto: portfólio das 2 bate cada uma isolada em consistência

FASE 3 — Estratégia breakout + portfólio de 3
   ✓ pronto: 3 estratégias validadas convivendo

FASE 4 — Alocação por regime (mecânica)
   • quanto de banca cada estratégia recebe conforme o regime atual
   ✓ pronto: alocação adaptativa bate alocação fixa

FASE 5 — Paper trade na Testnet (execução real, dinheiro fake)
   • execucao.py CCXT + maker; estado persistente; alertas Telegram
   ✓ pronto: roda dias seguidos sozinho, execução fiel ao backtest

FASE 6 — (OPCIONAL) LLM como conselheiro de regime/alocação + teste A/B
   ✓ decide: LLM agrega ou só custa? (Bot A mecânico vs Bot B com LLM)

FASE 7 — Dinheiro real pequeno, 1x, só se passar em todos os portões
```

**Custo:** Fases 0–5 = **R$0** (backtest + testnet). Só a Fase 6 (LLM) e a 7 (capital) custam.

---

## 9. Riscos & decisões em aberto

- **Fill de ordem maker no backtest é incerto** — vamos ser conservadores (assumir não-preenchimento parcial). Day trade depende muito disso.
- **Day trade é o modo mais difícil e competitivo** — honestamente, swing (timeframe maior) é estatisticamente mais amigável. Manteremos o foco day trade, mas medindo friamente se sobra edge depois da taxa.
- **"Consistência" tem limite** — nenhum sistema é verde todo dia. O gestor de banca suaviza, não milagrifica.
- **Volume de dados intradiário** — 15m/5m gera muitos candles; cache local resolve.
- **Overfitting** — o maior inimigo silencioso; walk-forward é obrigatório, não opcional.

---

## 10. Próximo passo imediato

Começar pela **Fase 0 (refatoração)** seguida da **Fase 1 (Gestor de Banca)** — a peça que entrega a segurança que você quer. Tudo no backtest, grátis.

**Parâmetros de partida (em `config.py`):** banca fictícia R$1.000 · risco 0,5%/trade · perda-dia -2% · lucro-dia +3% · BTC+ETH · 15m · maker · 1x.
