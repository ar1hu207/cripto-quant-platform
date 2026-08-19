# Auditoria 100% do Sistema — Matemática, Estratégias, Indicadores

> Revisão cabo-a-rabo via workflow multi-agente (7 auditores em paralelo + verificação adversarial de cada achado + revisor-chefe). 21 bugs confirmados, 45 melhorias, 6 gargalos sistêmicos. 2026-06-11.

## 🔴 Os 6 gargalos sistêmicos (o que mais importa)

1. **FUNDING NÃO EXISTE NO SISTEMA INTEIRO.** O `simulador.py` promete funding na docstring mas nem `_pnl()` nem `atualizar()` aplicam carry; o backtest também não paga funding (só colhe no `carry_hold`); e `mercado.py` anualiza um snapshot único com settlement fixo de 8h (×3/dia). Resultado: manter posição perp alavancada tem **custo de carregamento ZERO** no paper e no backtest → toda decisão "manter vs fechar" está enviesada pro lado de manter.

2. **A PARIDADE BACKTEST↔LIVE NÃO EXISTE NA PRÁTICA.** Apesar de compartilhar `scoring.py`: (a) o **live pontua o candle EM FORMAÇÃO** (`i=len(df)-1`) = **repaint**; o backtest usa candle fechado; (b) o backtest **preenche no próprio `close[i]`** que gerou o sinal (sem slippage, impossível ao vivo); (c) o **Bollinger não tem `.shift(1)`** (só o Donchian tem) → reversão e alvo `bb_mid` leem o candle corrente = look-ahead. **O backtest é estruturalmente otimista; o número que ele cospe não é o que o live entrega.**

3. **OS PARÂMETROS SÃO CHUTES REDONDOS, NÃO CALIBRADOS.** Pesos do score (ADX 5..40, rompimento 22, RSI 18, volume 15), cortes (min_conviccao=55, 3×ATR, 2.5×ATR) — números bonitos sem evidência. E a "validação" OOS usa o **mesmo período de calendário**, só trocando o conjunto de moedas (cripto é altamente correlacionada) + **escolhe o corte olhando o OOS** (data-snooping). Sem walk-forward/CPCV. → **Não há evidência de que o score tem edge; o "OOS aprovado" é ilusório.**

4. **MATEMÁTICA DE RISCO/LIQUIDAÇÃO INCONSISTENTE CONSIGO MESMA.** `fechar()` debita 100% da margem na liquidação (`-valor`), mas o preço de liquidação foi calculado pra ~90% (`LIQ_BUFFER=0.9`); o backtest erra o empate stop-vs-liquidação (marca LIQUIDADO quando o stop, perda menor, bateria primeiro). Isso se propaga pro `guarda_risco` e pro sizing do frontend.

5. **VIÉS DE SOBREVIVÊNCIA + universo fixo.** Os 24 ativos são os que sobreviveram até hoje; tokens que morreram não estão na lista → backtest infla. Some o cache que pode re-baixar janelas de data diferentes sem aviso.

6. **MÉTRICAS MEDEM A COISA ERRADA.** SQN sobre P&L bruto em R$ com tamanho variável (viola Van Tharp — infla o std com variância de TAMANHO, não de R-múltiplo); sem Sharpe; Sortino/Sharpe por-trade em vez de por-período; drawdown sobre cumsum de P&L realizado, não sobre equity mark-to-market. → O painel pode mostrar "SQN bom" enquanto o sistema só teve sorte com poucos trades grandes.

## 🎯 Plano priorizado (ordem do revisor-chefe — impacto × facilidade)

| # | O quê | Tipo | Esforço |
|---|---|---|---|
| 1 | **Corrigir paridade**: pontuar candle FECHADO (live `i=len-2`) + `.shift(1)` no Bollinger | bug alta | baixo |
| 2 | **Fill realista no backtest**: entrar no `open[i+1]` + slippage; empate intrabar → stop antes da liquidação | bug alta | baixo |
| 3 | **Aplicar funding** ao P&L (sim + backtest) + settlement por moeda (8h=3×, 4h=6×) | bug alta | médio |
| 4 | **Unificar liquidação**: `_pnl(pos, liq)` em vez de `-valor` + guards de divisão por zero | bug alta | baixo |
| 5 | **Walk-forward + multiple-testing** no lugar do split-por-moedas; travar cache | bug+melhoria | alto |
| 6 | **Calibrar pesos do score** por evidência (win-rate por fator); suavizar descontinuidades | melhoria alta | médio |
| 7 | **Métricas em R-múltiplos**: gravar stop/risco no trade, Sharpe, Sortino por-período, DD mark-to-market | melhoria alta | médio |
| 8 | **Frontend**: capar perda pela margem, R efetivo=min(stop,liq), bloquear confirmar se liq<stop, taxa no risco | bug+melhoria | baixo |

> **Ordem importa:** o item 1 vem primeiro — "enquanto o live faz repaint e o backtest lê o candle corrente, nenhum resultado é confiável; todo o resto é otimizar ruído." Calibrar pesos (6) só DEPOIS de paridade (1,2) + validação honesta (5).

## 🐛 Bugs confirmados (21) — por severidade

**ALTA:**
- Paridade quebrada (repaint live + fill otimista backtest) — `scoring.py`/`backtest_plataforma.py`
- OOS desonesto (mesmo período, só troca moedas correlacionadas + data-snooping) — `validar_reversao*.py`

**MÉDIA:**
- Funding nunca aplicado em posições mantidas — `simulador.py _pnl/atualizar`
- P&L de liquidação (-100% margem) inconsistente com preço de liquidação (~90%) — `simulador.py fechar`
- Divisão por zero (ATR=0 no DI; lev=0/entrada=0 em liquidação/_pnl) — `indicadores.py`/`simulador.py`
- Indicadores de Wilder sem máscara de warmup (ADX=100 com 2 candles) — `indicadores.py`
- Backtest: empate intrabar marca LIQUIDADO quando STOP bateria primeiro — `backtest_plataforma.py`
- Anualização funding ×3 fixo (errado p/ moedas 4h=6×) + snapshot único superestima — `mercado.py`
- `breadth()` soma None silenciosamente + 24 requests sequenciais — `mercado.py`
- `max_drawdown_pct` preso no ponto de maior DD absoluto (não o maior % ) — `db.py`
- SQN sobre P&L bruto (viola R-múltiplos de Van Tharp) — `db.py`
- "Perda no stop" não capada pela margem (mostra perda > dinheiro investido) — `index.html`
- `calcSugestao` quebra "arrisca risco%" quando liquida antes do stop — `index.html`
- ROE inconsistente: posições abertas (com taxa) vs journal (sem taxa) — `index.html`
- `statusEntrada` não cobre '30m' (expira 2× mais rápido) — `index.html`

**BAIXA:**
- Bollinger usa desvio amostral (ddof=1) em vez de populacional (ddof=0) — `indicadores.py`
- Alvo da reversão usa `bb_mid[i]` do mesmo candle (look-ahead leve) — `backtest_plataforma.py`
- Anualização do funding arb mistura rendimento recorrente com custo fixo de 4 pernas — `backtest_funding.py`

## 💡 Melhorias de maior impacto (top do lote de 45)
- **Indicadores faltando** pra micro-trade: MACD, VWAP, StochRSI, OBV, Keltner (squeeze).
- **Tendência sem take-profit** — P&L refém do flip lento de EMA; adicionar trailing por ATR / alvo Donchian oposto.
- **Slippage + spread** em todos os backtests (a base de conhecimento já diz "backtest sem custo real = ficção").
- **Walk-forward + CPCV + Deflated Sharpe** (anti data-snooping).
- **Drawdown sobre equity mark-to-market** (a tabela `equity` já existe).
- **Reversão com volume alto pode estar invertida** (volume no rompimento = continuação, não exaustão) — validar empiricamente.

---
*Artefato gerado pela auditoria multi-agente. Ver o sistema em c:\Users\aboni\Pesquisas\1\. Próximo: implementar o plano priorizado, começando pela paridade (#1).*
