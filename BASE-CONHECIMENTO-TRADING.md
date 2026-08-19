# Base de Conhecimento — Trading, Estratégias & Implementação

> **Propósito:** cérebro de referência do projeto. Reúne análise técnica, estratégias quantitativas, microestrutura, gestão de risco, validação e a realidade do mercado — tudo orientado a **extrair e codar estratégias em Python** no nosso sistema (scanner de sinais, gestor de banca, simulador com alavancagem, backtest com out-of-sample, order book). Pesquisa de 5 frentes sintetizada em 2026-06-11.
>
> **Regra-mãe (vale pra tudo abaixo):** todo indicador/estratégia é uma **hipótese a validar out-of-sample**, não verdade. ~90% das estratégias backtestadas são overfitting. Custo + ruído + eficiência de mercado são os inimigos. Use isso como cardápio de ideias — o filtro é sempre o backtest honesto.

---

## Sumário
1. [Análise Técnica & Price Action](#1-análise-técnica--price-action)
2. [Estratégias Quantitativas & Microestrutura](#2-estratégias-quantitativas--microestrutura)
3. [Gestão de Risco, Dimensionamento & Validação](#3-gestão-de-risco-dimensionamento--validação)
4. [Cripto: On-chain, Derivativos, Sentimento & Fundamentos](#4-cripto-on-chain-derivativos-sentimento--fundamentos)
5. [O Que Realmente Funciona vs Mitos](#5-o-que-realmente-funciona-vs-mitos)
6. [Síntese: Estratégias & Roadmap pro Nosso Sistema](#6-síntese-estratégias--roadmap-pro-nosso-sistema)

---

## 1. Análise Técnica & Price Action

> AT é heterogênea: alguns sinais têm evidência moderada, muitos são folclore. Consenso quant (2020-2025): sinais decaem em meses; funcionam melhor em **alta volatilidade + tendência**, falham no lateral; cripto é 5-10× mais volátil que ações (amplifica ganho E armadilha). Use AT mais como **gestão de ordem/timing** (definir stop/entrada) do que como gerador de alfa isolado.

### 1.1 Tendência
| Indicador | Lógica | Sinal em Python | Nota honesta |
|---|---|---|---|
| **EMA/SMA cruzamento** | média rápida vs lenta | `ema_f>ema_l → long` (9/21 intraday, 20/50 swing, 50/200 posicional) | lag inerente; whipsaw no lateral. É a base de trend-following. |
| **ADX/DMI** | força da tendência (não direção) | `ADX≥25` = tende; `<20` = lateral. **Usar como FILTRO de regime.** | bom filtro, péssimo gatilho sozinho. |
| **MACD** | momentum de médias | cruzamento da linha de sinal / histograma | redundante com EMA cross; divergências têm algum valor. |
| **Donchian** | rompimento de máx/mín de N | `close>max(high[-N:].shift(1)) → long` | base de breakout sistemático (Turtles). Forte em tendência. |
| **Supertrend / Ichimoku** | trailing por ATR / nuvem | stop dinâmico + direção | Supertrend é ótimo trailing; Ichimoku é pesado e subjetivo. |

```python
import pandas_ta as ta
df["ema_f"], df["ema_l"] = ta.ema(df.close,20), ta.ema(df.close,50)
df["adx"] = ta.adx(df.high, df.low, df.close, 14)["ADX_14"]
df["dir"] = (df.ema_f > df.ema_l).astype(int).replace(0,-1)
df["trade"] = df["dir"].where(df["adx"]>=25, 0)   # só opera com tendência forte
```

### 1.2 Momentum / Osciladores
- **RSI(14):** <30 sobrevendido, >70 sobrecomprado. **Melhor como timing dentro de contexto** (não como sinal primário). Divergência preço×RSI tem valor moderado.
- **Estocástico / Williams %R / ROC:** variações do mesmo tema (posição no range recente). Úteis em mean-reversion.
- ⚠️ Em **tendência forte**, osciladores ficam "grudados" no extremo e dão sinais falsos de reversão o tempo todo.

### 1.3 Volatilidade
- **ATR:** base de stop e sizing (ver §3). Não é direcional.
- **Bandas de Bollinger:** média ± k·σ. Toque na banda = mean-reversion (lateral) OU rompimento (tendência) — depende do regime. **Bollinger squeeze** (bandas estreitas) precede expansão de volatilidade.
- **Keltner:** como Bollinger mas com ATR (mais estável).

### 1.4 Volume
- **OBV / volume profile:** confirmação. Rompimento **com volume** > rompimento sem.
- **VWAP:** preço médio ponderado por volume; referência institucional intraday (preço acima/abaixo do VWAP = viés). Reset diário.

### 1.5 Price Action & S/R
- **Suporte/Resistência:** níveis onde stops/liquidez se acumulam. Mecanizar via Donchian, pivôs, swing highs/lows, números redondos, volume profile.
- **Rompimento (breakout):** quebra de S/R com confirmação (volume/fechamento). Cuidado com **fakeout** (rompe e volta).
- **SMC / Order Blocks / liquidity grabs:** popular mas **majoritariamente discricionário e não validado** — trate com ceticismo; o que é mecanizável (sweep de liquidez = varrer máx/mín anterior) pode virar regra testável.

**⚠️ Armadilhas de AT:** repintura (indicadores que mudam o passado), lag, e principalmente **overfitting de parâmetros**. Toda config de indicador = hipótese pra walk-forward.

---

## 2. Estratégias Quantitativas & Microestrutura

> Nenhuma estratégia é robusta em todos os regimes → a solução é **portfólio de estratégias** + alocação por regime. (Carver, *Systematic Trading*; López de Prado.)

### 2.1 Trend-Following / Momentum
**Lógica:** ativos que subiram tendem a continuar (curto/médio prazo). Duas formas:
- **Time-Series Momentum (TSMOM):** sinal do ativo contra ele mesmo (base dos CTAs).
- **Cross-Sectional (CSM):** ranqueia um universo, long nos top-N / short nos bottom-N. Aproveita a dispersão de altcoins.

```python
# TSMOM com volatility scaling (estilo Carver)
def tsmom(close, lookback=64, vol_win=25, target_vol=0.20):
    ret = close.pct_change()
    raw = close/close.shift(lookback) - 1
    vol = ret.rolling(vol_win).std()*np.sqrt(365)
    return (raw/vol).clip(-2,2)          # forecast escalado pela vol

# Breakout Donchian (Zarattini et al. 2025: ensemble com Sharpe>1.5 em cripto)
def donchian_sig(close, high, low, n=20):
    up, dn = high.shift(1).rolling(n).max(), low.shift(1).rolling(n).min()
    s = pd.Series(0, index=close.index); s[close>up]=1; s[close<dn]=-1
    return s.ffill()
```
- **Regime:** 🟢 tendência forte · 🔴 lateral (whipsaw). Filtro ADX>25.
- **Edge real:** existe mas decrescente. CTAs ~8%/ano com DD 20-40%. **O edge vem de diversificação entre ativos (CSM) + disciplina de stop**, não de parâmetro mágico. Custos corroem em timeframe curto.

### 2.2 Mean-Reversion
**Lógica:** preço desvia da média e reverte. Funciona em **lateral**, em spreads, e pós-liquidação (sobrevendido extremo).
```python
def mr_sig(close, bb_p=20, bb_std=2, rsi_p=14, lo=30, hi=70):
    bb = ta.bbands(close, bb_p, bb_std); rsi = ta.rsi(close, rsi_p)
    s = pd.Series(0, index=close.index)
    s[(close<bb[f'BBL_{bb_p}_{bb_std}.0']) & (rsi<lo)] = 1   # sobrevendido + banda
    s[(close>bb[f'BBU_{bb_p}_{bb_std}.0']) & (rsi>hi)] = -1
    return s                                                  # sai na média central
```
- **Regime:** 🟢 lateral / pós-crash · 🔴 tendência forte ("senta na banda e continua").
- **Edge:** existe intraday, MAS **uma tendência forte apaga meses de lucro** + alta sensibilidade a custo. **Sempre filtrar por tendência macro** (ex: só long acima da MA200) e usar stop absoluto. Win rate alto com retorno negativo é a armadilha clássica (ver §5).

### 2.3 Statistical Arbitrage / Pairs
**Lógica:** dois ativos cointegrados têm spread estacionário que reverte. (Ernie Chan.)
```python
from statsmodels.tsa.stattools import coint
score, pval, _ = coint(price_a, price_b)        # pval<0.05 = cointegrado
spread = price_a - hedge_ratio*price_b          # hedge via OLS ou Kalman
z = (spread - spread.rolling(20).mean())/spread.rolling(20).std()
# short spread se z>+2, long se z<-2, sai perto de z=0
```
- **Edge real está na arbitragem de basis** (spot vs perpétuo do mesmo ativo) — risco menor, spread mais estável. ⚠️ Cointegração **não é permanente** (re-testar mensal); taxa dupla (4 execuções/ciclo); em altseason as correlações vão a 1 e o spread não reverte.

### 2.4 Market Making
**Lógica:** posta bid+ask, lucra o spread; risco = inventário. Modelo Avellaneda-Stoikov (preço de reserva ajustado por inventário). 
- **⚠️ Honestidade nº1:** em BTC/ETH é **dominado por HFT com co-location e latência de µs**. Varejo (50-200ms) sofre **adverse selection** severa. Só faz sentido em **altcoins de baixa liquidez** (spread 0.3-1%) ou DEX/AMM (com risco de impermanent loss). O flash crash de out/2025 confirmou: makers tomaram perdas, takers lucraram.

### 2.5 Grid & DCA
- **Grid:** ordens em degraus; lucra o vai-e-vem. **Grid dinâmico** (reseta o centro ao sair do range) supera o estático (paper 2025: ~60-70% IRR em BTC com DD ~50%).
- **DCA:** compra valor fixo em intervalos; reduz preço médio. Não é timing, é acumulação.
- **⚠️ Grid = vender opções:** recebe prêmio (spread) em troca de risco de cauda (tendência). Avalie por **Sharpe ajustado a skew**, não IRR. Grid apertado (<0.2%) morre na taxa — tamanho mínimo ≈ 3× a taxa.

### 2.6 Microestrutura / Order Flow ⭐ (onde temos dados, ver nosso /book)
- **Order Book Imbalance (OBI):** `(bid_vol - ask_vol)/(bid_vol + ask_vol)`. Positivo = pressão compradora. ⚠️ Edge bruto pequeno (~0.42 bps a 30s no BTC) — **melhor como filtro de timing/feature de ML** do que estratégia isolada.
- **CVD (Cumulative Volume Delta):** soma do volume agressor (taker buy − taker sell). **Divergência preço×CVD** = sinal (preço sobe + CVD cai = fraqueza). É o que nosso "fluxo taker" mede.
- **Detecção de paredes/spoofing:** ordem grande que aparece e some em <3s = provável spoof. Por isso **fluxo executado (taker) > book parado** como sinal (executado não dá pra fingir).
- **VWAP/TWAP execution:** fatiar ordem grande pra não mover o mercado.
```python
def obi(book, depth=5):
    b = sum(l[1] for l in book['bids'][:depth]); a = sum(l[1] for l in book['asks'][:depth])
    return (b-a)/(b+a+1e-9)
def cvd(trades):   # trades['side'] = 'buy'/'sell' (taker)
    return np.where(trades.side=='buy', trades.size, -trades.size).cumsum()
```

### 2.7 Funding Rate Arb (cash & carry) — edge estrutural real
Long spot + short perpétuo quando funding positivo → **recebe funding sem risco direcional**. Em altcoins, funding 0.01-0.1%/8h ≈ 13-130%/ano neutro ao mercado. ⚠️ Em crash rápido o spot cai mais rápido que o funding compensa; monitorar basis.

### 2.8 Portfólio & Detecção de Regime
```python
def regime(close, high, low):
    adx = ta.adx(high,low,close,14)['ADX_14']
    atr_pct = ta.atr(high,low,close,14)/close*100
    r = pd.Series('lateral', index=close.index)
    r[adx>25] = 'tendencia'
    r[atr_pct > atr_pct.rolling(252).quantile(.8)] = 'volatil'
    return r
```
| Regime | Trend | Mean-Rev | Grid | Tamanho |
|---|---|---|---|---|
| Tendência | 100% | off | pausado | 100% |
| Lateral | 25% | 100% | 75% | 75% |
| Volátil | 50% | off | pausado | 25-50% |

**Combinar por risk-parity (peso ∝ 1/vol) + volatility targeting** (Carver). HMM (`hmmlearn`) é alternativa pra detectar regime probabilisticamente.

**Fontes §2:** Carver *Systematic Trading*; Ernie Chan *Algorithmic Trading*; López de Prado *AFML*; Zarattini/Pagani/Barbon "Catching Crypto Trends" (SSRN 2025); Avellaneda-Stoikov (2008); arXiv 2506.11921 (grid dinâmico), 2602.00776 (microestrutura cripto).

---

## 3. Gestão de Risco, Dimensionamento & Validação

> O sizing impacta a curva de capital **mais** que a entrada/saída (Van Tharp). E nenhuma gestão transforma sistema sem edge em lucrativo — ela protege de erro de implantação e eventos extremos.

### 3.1 Position Sizing
```python
# Fixed-fractional: arrisca r% do NAV; perda no stop = sempre r% (qualquer ativo/vol)
def size_ff(nav, entry, stop, risk=0.01):
    d = abs(entry-stop); return 0 if d==0 else (risk*nav)/d

# ATR sizing: normaliza risco pela volatilidade
def size_atr(nav, atr, mult=2.0, risk=0.01):
    return (nav*risk)/(atr*mult)

# Kelly (use 1/4 a 1/2 Kelly — NUNCA full)
def kelly(win_p, payoff): return max(0, win_p - (1-win_p)/payoff)
```
| Risco/trade | Perfil |
|---|---|
| 0.5-1% | conservador |
| 1-2% | moderado |
| 2-3% | agressivo |
| >3% | **território de ruína** em sequência de perdas |

**Kelly fracionário (simulação 500 caminhos):** Full Kelly = +88% mediano / -60% DD; Half = +72% / -34% DD; 1/4 ainda melhor risco-retorno. **Acima de 2× Kelly o crescimento esperado é NEGATIVO.** Sempre fracionário (estimativas de p/payoff são ruins, ainda mais em cripto).

### 3.2 Stops & Saídas
- **Fixo / ATR / trailing / Chandelier:** ver código abaixo. Trailing = `max(stop_ant, preço − k·ATR)` pra long.
- **Breakeven:** mover stop pra entrada só após **≥1R** de lucro (cedo demais = zera por pullback normal).
- **Take-profit parcial:** realizar 33% em 1.5×ATR, 33% em 3×ATR — reduz variância do P&L.
- **Gestão ativa ("fecha quando a tese quebra"):** sai quando a condição que abriu o trade some (RSI volta abaixo de 50, fluxo do book vira, falso breakout confirmado). **Quando ajuda:** reversões rápidas (pump-and-dump), setups com validade clara. **Quando atrapalha:** corta winners cedo, ruído dispara saída falsa. **Regra de ouro: se não foi backtestada, não tem borda — é viés comportamental.**
```python
def trailing(stop, price, atr, k=2, side='long'):
    new = price-atr*k if side=='long' else price+atr*k
    return max(stop,new) if side=='long' else min(stop,new)
```

### 3.3 Controle de Drawdown
- **Limite de perda diária** (~3× o risco/trade) → trava o dia. **Kill-switch** → fecha tudo + desativa (TESTAR periodicamente). **Risco aberto máx** (soma das posições). **Correlação:** corr>0.7 ≈ dobra o risco; em crise cripto toda correlação vai a 1 (diversificação intra-cripto some — hedge real é stablecoin/short BTC).

### 3.4 Métricas
- **Expectativa / R-múltiplos** (Van Tharp): R = PnL/risco_inicial. **SQN** = (média_R/std_R)·√n (>2 bom, >3 ótimo, >7 suspeito de overfit).
- **Win rate vs payoff vs profit factor:** win rate sozinho ENGANA (85% acerto com payoff 0.2 perde). **Profit factor** 1.5-2.0 = sólido; >3 = suspeite de overfit.
- **Sharpe / Sortino / Calmar:** Sharpe assume normalidade (inválido p/ cripto — fat tails); **Sortino** (só downside) e **Calmar** (retorno/maxDD) são mais honestos. Cripto: anualizar com 365.
```python
def sortino(r, ppy=365):
    dn = r[r<0].std()*np.sqrt(ppy); return 0 if dn==0 else r.mean()*ppy/dn
def maxdd(eq): peak=eq.cummax(); return ((eq-peak)/peak).min()
```

### 3.5 Validação Rigorosa (a seção mais ignorada e mais importante)
- **Look-ahead bias:** todo sinal usa `.shift(1)`; normalização **rolling**, nunca com a série toda (`StandardScaler().fit` na série inteira = vazamento). Executar no Open da PRÓXIMA vela, não no Close do sinal.
- **Overfitting:** N parâmetros em T dados captura ruído. Testar 100 configs gera ~5 "lucrativas" por acaso (5% sig). **Walk-forward** (treina janela → testa próxima → avança) é o mínimo; **CPCV** (combinatorial purged CV, López de Prado) é melhor (múltiplos caminhos + purga + embargo).
- **Deflated Sharpe Ratio:** corrige o Sharpe pelo nº de tentativas. 100 configs testadas → precisa Sharpe in-sample ~3 pra ter confiança. 
- **Sinal de overfit:** OOS é 30-70% pior que in-sample. (Foi **exatamente** o que vimos no nosso projeto — a config "vencedora" deu +R$313 in-sample e −R$1.233 OOS.)
```python
def walk_forward(df, strat_fn, train=252, test=63, step=21):
    out=[]; i=0
    while i+train+test<=len(df):
        out.append(strat_fn(df.iloc[i:i+train], df.iloc[i+train:i+train+test])); i+=step
    return pd.concat(out)
def bootstrap_sharpe_ci(r, n=10000, ppy=365):   # se IC inferior inclui 0, edge não é significativo
    s=[ (x:=r.sample(len(r),replace=True)).mean()/x.std()*np.sqrt(ppy) for _ in range(n)]
    return np.percentile(s,2.5), np.percentile(s,97.5)
```

**Checklist de backtest honesto:** OOS separado ANTES de desenvolver · nº de params documentado (calc DSR) · fee+slippage+funding incluídos · liquidez verificada · sem survivorship bias · walk-forward/CPCV feito · estável a ±10% nos params · bootstrap confirma significância.

> **Verdade inconveniente:** Sharpe 1.0 após custos reais, robusto a 3 regimes, validado walk-forward em 2 anos OOS **vale mais que qualquer Sharpe 3.0 de backtest ingênuo.**

**Fontes §3:** Van Tharp *Position Sizing*; Kelly (1956); Ralph Vince; López de Prado *AFML* + Deflated Sharpe (Bailey & LdP 2014).

---

## 4. Cripto: On-chain, Derivativos, Sentimento & Fundamentos

### 4.1 On-chain (os "fundamentos nativos" do cripto)
| Métrica | Sinaliza | Dado |
|---|---|---|
| **Endereços ativos** | adoção/uso real (leading de ciclo 90-180d) | Glassnode (pago); blockchain.info grátis p/ BTC |
| **Exchange flows** (in/out) | inflow→pressão de venda; outflow→acumulação | CryptoQuant/Glassnode |
| **MVRV** (market/realized value) | >3.7 topo; <1 fundo histórico | Glassnode |
| **SOPR** | >1 realizando lucro; <1 prejuízo (capitulação) | Glassnode/CryptoQuant |
| **NUPL, NVT, realized price, supply LTH/STH** | fases de ciclo, valuation | Glassnode |
⚠️ On-chain é **macro/cíclico** (semanas-meses), não intraday. Edge real em janelas longas; ruído no curto. Maioria das APIs boas é **paga**.

### 4.2 Derivativos ⭐ (parcialmente grátis — já usamos funding)
- **Funding rate:** longs pagam shorts (positivo) = multidão comprada → risco de squeeze pra baixo (e vice-versa). **Sentimento + crowding.** Grátis via ccxt (`fetch_funding_rate`).
- **Open Interest:** OI subindo + preço subindo = novos longs (vulneráveis). 
- **Long/Short ratio, basis.**
- **Mapa de liquidação:** onde posições alavancadas são liquidadas (preço é "puxado" pra lá). ⚠️ **Dado real é PAGO** (Coinglass/Hyblock). Nosso **proxy grátis**: funding + zonas de liquidez (swing highs/lows onde stops se acumulam). Cascatas de liquidação amplificam movimentos.

### 4.3 Sentimento
- **Fear & Greed Index:** grátis (`api.alternative.me/fng`). Contrarian em extremos (medo extremo = possível fundo). Já integrado.
- **Funding como sentimento** + breadth (% de moedas subindo) + social.

### 4.4 Fundamentos / Tokenomics
- Avaliar projeto: utilidade real, **supply/emissão** (inflação do token), TVL (DeFi Llama, grátis), atividade de devs, **narrativas/catalisadores** (ETF, halving, upgrades). Mais relevante pra **seleção de ativos** e holding de médio prazo do que pra timing.

**⚠️ Edge:** on-chain/fundamentos têm valor **macro**, não pra scalp. Funding + F&G são os sinais grátis mais acionáveis. Mapa de liquidação real precisa pagar.

**Fontes §4:** Glassnode, CryptoQuant, Coinglass, DeFi Llama, alternative.me.

---

## 5. O Que Realmente Funciona vs Mitos

> Seção desconfortável de propósito. Objetivo: **calibrar**, não desanimar.

### 5.1 Eficiência de mercado
HME forma fraca (preços já refletem o histórico de preços) é **amplamente sustentada** em mercados líquidos → TA pura não deveria gerar alfa consistente após custos. Cripto é **menos eficiente** (mais "aparência" de padrão), mas ineficiências são pequenas, transitórias e comidas pelos custos. AT vale como **gestão de ordem**, não como gerador de alfa garantido.

### 5.2 Estatísticas reais do varejo (os dados que ninguém mostra)
- **Barber & Odean (Taiwan, todos os trades 1992-2006):** >80% dos day traders perdem; **<1%** lucra de forma consistente líquida. Mais atividade = pior retorno.
- **FGV Brasil (Chague & Giovannetti, 19.646 day traders):** **92% desistiram em <1 ano**; dos que persistiram 300+ pregões, **97% perderam**; só **0,1-0,12%** ganhou >R$100/dia. *"Day trade é cassino, muito mais sorte que técnica."* Brasileiros perderam **R$9,9 bi** em day trade na pandemia.
- Taxa de acerto **PIORA com experiência** — oposto de habilidade aprendível.

### 5.3 Custos: o assassino silencioso
Custo total ida+volta = taxa + spread + slippage + funding = **0,1% a 1,5%+**. 10 trades/dia a 0,1% = **1%/dia** só de custo → precisa de >1.200%/ano bruto pra empatar (nem a Renaissance faz). **Backtest sem custo real = ficção.** (Sem taxas, a perda do varejo em Taiwan cai de 80% pra ~60% — as taxas transformam marginal em desastre.)

### 5.4 Alavancagem: amplifica risco, não edge
**Imposto da volatilidade:** `retorno_geométrico ≈ aritmético − vol²/2`. Estratégia +0,1%/dia com vol 2% → geométrico +0,08%/dia. A 10x (vol 20%): **−1,9%/dia** — a mesma estratégia vira ruína. Acima do Kelly = **ruína matematicamente garantida** com tempo suficiente. (Foi o que medimos: scalp alavancado zerou; 2x sempre pior que 1x.)

### 5.5 Os poucos edges com evidência real (e seus asteriscos)
- **Momentum cross-seccional** (Jegadeesh & Titman 1993, ~1%/mês): *requer short, sofre crashes severos, diluído em cripto pela alta correlação.*
- **Trend-following longo prazo** (AQR, 100 anos, 67 mercados, Sharpe ~0.4): *modesto, requer MUITOS mercados pra diversificar, melhores anos = proteção de cauda.*
- **Carry / funding arb:** *lógica econômica clara; sofre em crash.*
- **Market making com vantagem estrutural:** *dominado por HFT.*

### 5.6 Expectativas realistas
| Quem | Retorno líq/ano | Obs |
|---|---|---|
| **Renaissance Medallion** | ~39% (66% bruto) | melhor da história, fechado, centenas de PhDs — **anomalia**, não modelo |
| CTA top quartil | 8-15% | melhores do mundo |
| Quant médio | 6-12% | após taxas |
| S&P500 buy-hold | ~10% | benchmark passivo |

**"X% ao dia" é impossível:** 1%/dia = +1.103%/ano = +16 milhões% em 5 anos. Atrairia todo o capital do mundo e seria arbitrado a zero em semanas. Quem mostra isso em backtest tem overfit/look-ahead/custo ignorado.

### 5.7 O que dá pra fazer de útil (sem edge mágico)
1. **Gestão de risco = único alfa garantido** (não perder mais que X%).
2. **Automação = vantagem de processo** (sem emoção, 24/7, consistência).
3. **DCA / exposição estrutural ao beta** (capturar o prêmio de risco do ativo sem destruir com giro).
4. **Estratégias com lógica econômica** (funding harvest, rebalanceamento/vol harvesting, liquidez em nichos) — alguém paga por algo que você fornece, diferente de adivinhar direção.

**Fontes §5:** Fama (1970); Barber, Lee, Liu & Odean (Taiwan); Chague & Giovannetti (FGV); AQR "Century of Evidence"; Jegadeesh & Titman (1993); Bailey/López de Prado (PBO, DSR); Cornell Capital (Medallion).

---

## 6. Síntese: Estratégias & Roadmap pro Nosso Sistema

### 6.1 O que o nosso projeto já PROVOU (com dados)
- Confluência técnica (EMA+ADX+RSI+breakout+volume) **falhou OOS** em todos os regimes testados. Tuning ≠ edge.
- O único perfil que sobreviveu: **trend-following sem alavancagem, timeframe maior** (~10%/ano real, defensivo).
- A plataforma é **honesta** (pegou o próprio overfitting) — esse é o ativo.

### 6.2 Estratégias candidatas a codar (priorizadas por evidência)
| # | Estratégia | Por que vale | Risco/dificuldade |
|---|---|---|---|
| 1 | **Funding arb (cash & carry)** | edge ESTRUTURAL real, neutro ao mercado, lógica econômica | precisa spot+perp + execução; cuidado com basis em crash |
| 2 | **Trend portfolio multi-ativo (1x, 4h/1d)** | foi o que teve edge; diversificação = consistência | retorno modesto; lag em bull |
| 3 | **Cross-sectional momentum** (long top-N/short bottom-N em ~15 alts) | evidência acadêmica forte | precisa short; correlação cripto dilui |
| 4 | **Mean-reversion gated por regime** (só lateral, ADX<20, filtro MA200) | complementa trend | sensível a custo; valida OOS |
| 5 | **Order-flow filter** (OBI/CVD/fluxo taker como FILTRO de timing nas entradas existentes) | melhora execução; já temos /book | edge bruto pequeno; usar como filtro, não sinal |

### 6.3 Features de sistema a construir (polir a plataforma)
- **Gestor de saída ativa** ("fecha esse trade"): re-avalia a posição a cada barra; fecha se (a) a convicção que abriu sumiu, (b) o **fluxo do book virou** contra (usar /book), (c) momentum reverteu. **Backtestar A/B (com vs sem) — sair cedo pode cortar winner.** Stop continua como piso; isto é otimização em cima.
- **Detecção de regime** (ADX/ATR ou HMM) → alocação dinâmica entre estratégias da §6.2.
- **Sizing por convicção + ATR + 1/4-Kelly** (já temos fixed-fractional; evoluir).
- **Validação CPCV + Deflated Sharpe** no backtest (hoje temos OOS multi-ativo; CPCV é o próximo nível anti-overfit).
- **WebSocket** pra order flow tick-a-tick (hoje é polling 6s).
- **Métricas avançadas**: SQN, Calmar, profit factor, R-múltiplos no painel.

### 6.4 Princípios inegociáveis (de tudo acima)
1. Toda estratégia → **validação out-of-sample** antes de qualquer R$ real (in-sample mente).
2. **Custo + funding** sempre no backtest. Alta frequência morre na taxa.
3. **Alavancagem é dial de risco, não de edge** — 1/4 a 1/2 Kelly, nunca acima.
4. **Gestão de risco > sinal.** É o único alfa garantido.
5. Buscar **lógica econômica** (funding, carry, vol harvesting) > adivinhar direção.
6. Expectativa honesta: **dezenas de % ao ano é excelente**; "X%/dia" não existe.

---

*Documento vivo. Atualizar conforme novas estratégias forem validadas (ou refutadas) no nosso backtest/OOS. Pesquisa base: 5 frentes (análise técnica, quant/microestrutura, risco/validação, cripto on-chain/derivativos, realidade do mercado) — 2026-06-11.*
