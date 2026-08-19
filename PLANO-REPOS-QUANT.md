# PLANO — Repos de Quant Finance: o que aproveitar e como

**Origem:** post do Instagram ("4 github repos that teach you quant finance for free").
**Data:** 2026-07-24.
**Para:** agente de dev que vai implementar.
**Diretório do projeto:** `c:\Users\aboni\Pesquisas\1`

---

## 0. Contexto obrigatório (leia antes de escrever qualquer linha)

Este projeto é uma **plataforma de pesquisa quant + paper trading** de cripto. Ela já passou
por validação rigorosa e o veredito atual é:

| Estratégia | Veredito | Onde foi provado |
|---|---|---|
| Tendência (EMA/ADX/Donchian/RSI) | ❌ sem edge | `validacao.py` — walk-forward, 370 trades OOS, win 25,4%, PnL −R$807, IC95% [−7,4; +3,5] inclui 0, **DSR = 0,004** |
| Reversão (RSI + Bollinger) | ❌ breakeven | `validar_reversao_maker.py` — melhor caso +R$73 in / −R$76 OOS sobre ~1100 trades |
| Funding arb (cash & carry) | ❌ não-deployável | `funding_estudo.py` — always-in +1,9%/ano líquido; gated fica negativo (4 pernas de taxa comem o funding) |

**Nenhum edge deployável existe hoje.** A plataforma é um instrumento honesto: mede, avisa
quando NÃO operar, blinda risco e barra ideia ruim antes de dinheiro real.

### Regras invioláveis do projeto

Qualquer coisa implementada a partir deste plano **tem que** respeitar:

1. **Maker sempre.** Toda estratégia entra com ordem limite. Foi provado que a taxa sozinha
   virou −R$589 em +R$73 (swing de R$660) no mesmo sinal. `TAXA = 0.0005` por lado em
   `backtest_plataforma.py:18`. Nunca modelar entrada a mercado sem justificar.
2. **Paridade backtest ↔ live.** A pontuação vive em `scoring.py` e é usada igual pelo
   `signal_engine.py` (ao vivo) e pelo `backtest_plataforma.py` (histórico). Sinal no candle
   **FECHADO** `i`, execução no **open do candle `i+1`** + slippage `0.0002`. Não quebrar isso.
3. **Sem look-ahead.** Donchian e qualquer canal já entram com `.shift(1)` (`scoring.py:18-19`).
   Alvo de reversão usa `mids[i-1]` (`backtest_plataforma.py:68`).
4. **Nada é aprovado por resultado in-sample.** Critério de aceite está na §6.
5. **Resultado negativo é entregável.** Se a ideia morrer no teste, documente a morte com
   número e siga. Isso é o produto do projeto, não fracasso.
6. **Dependências enxutas no runtime.** `requirements.txt` hoje é fastapi/uvicorn/ccxt/
   pandas/numpy/pydantic. **Não adicionar dependência pesada ao runtime.** Se precisar de
   `statsmodels`/`scipy` para pesquisa, criar `requirements-pesquisa.txt` separado — o deploy
   (Azure VM) não pode engordar.
7. **Não mexer no caminho ao vivo** (`autotrader.py`, `simulador.py`, `api.py`, `index.html`)
   como parte deste plano. Tudo aqui é **pesquisa offline**. Só depois de um veredito positivo
   se discute integração.

---

## 1. Os 4 repositórios

### 1.1 `awesome-quant` — wilsonfreitas
<https://github.com/wilsonfreitas/awesome-quant>

Lista curada de ~150 bibliotecas e recursos para quants: bibliotecas numéricas, instrumentos
financeiros e pricing, indicadores técnicos, trading & backtesting, otimização de portfólio,
análise de fator, dados de mercado, séries temporais, visualização.

**Serve pro projeto?** 🟡 Marginal. É índice, não código. Valor: consulta pontual para achar
biblioteca. Único item com possível uso real: `vectorbt` (varredura de parâmetro vetorizada,
muito mais rápida que nosso loop Python) — mas **só se** a lentidão do sweep virar gargalo real.
Não é prioridade, e adotar traria dependência pesada (viola a regra 6 no runtime; ok em
`requirements-pesquisa.txt`).

**Ação:** nenhuma. Deixar como referência de consulta.

---

### 1.2 `Computational-Finance-Course` — Lech Grzelak
<https://github.com/LechGrzelak/Computational-Finance-Course>

Curso universitário completo e gratuito, baseado no livro *"Mathematical Modeling and
Computation in Finance"* (Oosterlee & Grzelak, 2019). 14 aulas, cada uma com vídeo no YouTube,
PDF de slides e código Python/MATLAB:

1. Intro e classes de ativos · 2. Ações, opções e estocástica · 3. Precificação de opção e
simulação em Python · 4. Volatilidade implícita · 5. Processos de salto · 6. Affine Jump
Diffusion · 7. Modelos de vol estocástica · 8. Transformada de Fourier para pricing ·
9. Monte Carlo · 10. Monte Carlo do modelo de Heston · 11. Hedge e gregas · 12. Forward start
e modelo de Bates · 13. Derivativos exóticos · 14. Resumo.

**Serve pro projeto?** ❌ Não. É 100% precificação de derivativo (opções, vol estocástica,
exóticos). O bot opera direcional em perp/spot; não precifica opção nenhuma. Só viraria
relevante se houvesse pivot para **opções** (ex.: Deribit) — o que **não está no roadmap**.

**Ação:** nenhuma no código. Formação pessoal do usuário — excelente material, mas fora do
escopo de dev.

---

### 1.3 `machine-learning-for-trading` — Stefan Jansen ⭐ o mais relevante
<https://github.com/stefan-jansen/machine-learning-for-trading>

Código do livro *Machine Learning for Trading*, **3ª edição (2026)** — reconstruída do zero.
27 capítulos, +150 notebooks executáveis, 9 estudos de caso rodando o mesmo pipeline em
ativos diferentes.

Estrutura: Parte I Dados (taxonomia, viés de sobrevivência, microestrutura/livro de ofertas,
construção de barra, dados alternativos, dados sintéticos) · Parte II Design de pesquisa
(walk-forward, **triple-barrier labeling**, trend scanning, features de momentum/vol/liquidez,
features de modelo — Kalman, GARCH, HMM) · Parte III Modelos (linear, gradient boosting,
deep learning de série temporal, fatores latentes, causal ML) · Parte IV Implementação
(**backtesting com controle de overfitting: Deflated Sharpe, Rademacher Anti-Serum, White's
Reality Check**, construção de portfólio, **modelagem de custo de transação e execução**,
gestão de risco) · Parte V IA avançada (RL, RAG, knowledge graphs) · Parte VI Produção
(live trading, MLOps).

**Serve pro projeto?** ✅ **Sim — é o único com peça diretamente reaproveitável.** Mas repare
no motivo: não é o "ML acha padrão que humano não vê" (isso é exatamente o que nossos testes
refutaram). É a **infraestrutura de validação e a disciplina de pesquisa**.

Pontos que batem em falha *conhecida* do nosso processo:

| Capítulo | O que tem | Por que importa aqui |
|---|---|---|
| Cap. 16 | White's Reality Check, Rademacher Anti-Serum, FDR/Benjamini-Hochberg | `tune.py` varreu TF × lev × corte = data snooping massivo. Temos DSR, falta o teste formal de "testei N configs, quantas passam por sorte". **→ Item 1** |
| Cap. 4 | Dollar/volume bars vs time bars, microestrutura | O projeto inteiro rodou em candle de tempo (15m/1h/4h). Eixo nunca variado. **→ Item 3** |
| Cap. 7 | Triple-barrier labeling, trend scanning | Formaliza alvo/stop/tempo. Nosso trailing stop e gestor de saída são heurística. **→ backlog §5.2** |
| Cap. 18 | Modelagem de custo de transação e execução | Taxa é o assassino comprovado deste projeto. **→ backlog §5.3** |
| Cap. 2 | Viés de sobrevivência | `AUDITORIA-SISTEMA.md` já apontou isso no nosso universo de moedas. **→ backlog §5.4** |
| Case Study 2 | **Funding-rate arb em perp de cripto, 8-horário** | Bate direto no `funding_estudo.py`, que deu não-deployável. Nosso caveat registrado: **não modelamos o basis**. **→ backlog §5.1** |

**Aviso:** o repo tem stack pesada (deep learning, RL, IB/Alpaca). **Não instalar o ambiente
dele.** A abordagem é: ler o notebook do capítulo, entender o método, **portar o conceito**
para o nosso código puro numpy/pandas. Nada de dependência nova no runtime.

---

### 1.4 `Financial-Models-Numerical-Methods` — cantaro86
<https://github.com/cantaro86/Financial-Models-Numerical-Methods>

Coleção de notebooks Jupyter sobre matemática financeira: Black-Scholes, SDEs, modelos de
salto (Merton, Heston), calibração de volatilidade, métodos PDE, Fourier, opções americanas,
filtro de Kalman.

**Serve pro projeto?** 🟡 **Parcialmente — 4 notebooks salvam o repo.** A maioria é pricing de
opção (não serve, mesma razão do 1.2). Mas tem:

- **6.1 — Processo de Ornstein-Uhlenbeck e aplicações**: estimação de parâmetros, *hitting
  time*, PDE de Vasicek, filtro de Kalman e **estratégia de trading**. Isso é mean-reversion
  **formal**. → **Item 2**
- **5.1 — Regressão linear e filtro de Kalman**: limpeza de dado de mercado, desenho do filtro,
  escolha de parâmetros. Dá **hedge ratio dinâmico** (base de par/spread).
- **5.2 — Kalman: tracking de autocorrelação, AR(1)**: estimação de processo autorregressivo
  com parâmetro variando no tempo. É literalmente a estimação do OU em versão adaptativa.
- **5.3 — Tracking de volatilidade**: Kalman + GARCH(1,1) para vol variável no tempo.
- (7.1 — MVO clássica: baixo valor, já temos gestor de banca por risco fixo.)

**Por que o OU importa:** nós rejeitamos mean-reversion, mas rejeitamos uma **implementação
heurística** (RSI + Bollinger com números chutados), não a classe. O diagnóstico que ficou
registrado foi: *"sinal tem valor direcional (win 57-62%) mas o payoff mata — wins pequenos até
a média, losses grandes até o stop, mais taxa"*. Payoff é exatamente o que o OU dimensiona:
ele estima a **meia-vida** da reversão a partir do dado e deriva alvo/stop/time-stop do
*hitting time*, em vez de chute. Merece um teste com o rigor de sempre.

---

## 2. O aviso que não muda

**Nada disso cria edge.** Matemática mais sofisticada sobre o **mesmo dado público** não vira
alfa — foi isso que os testes deste projeto mostraram. O ML4T inclusive dá mais ferramenta pra
*provar que não tem*, que é diferente de dar edge.

A diferença é que **dois** itens abaixo atacam falha real do nosso *processo* (validação
anti-data-snooping formal; barra de tempo nunca questionada) e **um** reabre uma porta que
talvez fechamos cedo demais (mean-reversion formal em vez de heurística).

Expectativa honesta a priori: **os três provavelmente confirmam "sem edge"**. O ganho é que
passamos a saber disso com rigor maior e com menos chance de ter descartado algo por
implementação ruim.

---

## 3. Itens de trabalho

### ITEM 1 — White's Reality Check + FDR em `validacao.py` 🔴 prioridade máxima

**Arquivo:** `validacao.py` (estender, não reescrever).
**Fonte conceitual:** ML4T Cap. 16.
**Esforço:** baixo. **Valor:** alto e retroativo (aplicável a tudo que já testamos).

#### Problema que resolve

`validacao.py` hoje tem `deflated_sharpe()` (linha 77) e `bootstrap_ci()` (linha 99). O DSR
corrige multiple-testing via `n_trials` (linha 149: `len(GRID) * N_FOLDS`), mas:

- É uma correção **paramétrica** e depende de um `n_trials` que a gente estimou "no olho" —
  o número real de tentativas do projeto é muito maior (todo o `tune.py`, todos os
  `validar_*.py`, todos os cortes testados ao longo de meses).
- `bootstrap_ci()` (linha 99-109) faz reamostragem **IID por trade**, o que **destrói a
  autocorrelação** dos retornos e produz IC otimista demais.
- Não existe teste que responda: *"o melhor de N configs é melhor que o esperado por sorte?"*

#### O que implementar

**1a. Bootstrap de bloco** (substitui/complementa o IID)

```python
def block_bootstrap_idx(n, block=None, rng=None):
    """Índices de um bootstrap circular por blocos. Preserva autocorrelação.
    block padrão = int(n ** (1/3)) (regra prática), mínimo 2."""
```

Usar em `bootstrap_ci()` como modo padrão; manter o IID acessível via parâmetro para comparar
(o próprio delta entre os dois é informativo: mostra quanto o IC IID estava inflado).

**1b. White's Reality Check (bootstrap)**

```python
def reality_check(matriz_pnl, n_boot=2000, block=None):
    """White's Reality Check.
    matriz_pnl: dict {config: [pnl_por_periodo]} — TODAS as séries no MESMO grid temporal
                e do MESMO tamanho (períodos sem trade = 0.0).
    Retorna {'p_valor': float, 'melhor_cfg': cfg, 'V': float}.
    H0: a MELHOR das N configs não tem performance esperada > 0.
    p_valor > 0.05 => não dá pra rejeitar a sorte.
    """
```

Algoritmo:
1. Para cada config `k`: `f_k = média(pnl_k)`. `V = sqrt(T) * max_k(f_k)`.
2. Para `b` em `1..n_boot`: sortear **um único** conjunto de índices por bloco (o **mesmo**
   para todas as configs — isso é essencial, preserva a correlação entre configs), computar
   `f*_k`, e `V*_b = sqrt(T) * max_k(f*_k − f_k)`.
3. `p_valor = #{V*_b > V} / n_boot`.

**Ponto crítico de implementação:** os trades hoje saem como lista por config com tamanhos
diferentes (`backtest_ativo` retorna `[{conv, pnl, motivo, ts}]`). O Reality Check exige
**séries alinhadas**. Escrever um helper:

```python
def pnl_por_periodo(trades, bordas_ts):
    """Agrega trades em PnL por período (recomendado: diário) sobre um grid de timestamps
    comum a todas as configs. Período sem trade = 0.0. Usa t['ts'] (timestamp de ENTRADA)."""
```

**1c. FDR / Benjamini-Hochberg**

```python
def fdr_bh(p_valores, q=0.10):
    """Benjamini-Hochberg. Ordena p_(1)<=...<=p_(m); acha o maior k com p_(k) <= k/m*q;
    rejeita H0 para os k menores. Retorna lista de bools (True = sobrevive) + limiar usado."""
```

Uso: gera um p-valor por config (bootstrap de bloco da média contra 0), aplica BH, e reporta
**quantas configs sobrevivem ao controle de FDR**. Se zero sobrevive — que é o esperado —
está encerrado.

**1d. Integrar no relatório do `walk_forward()`**

Estender o bloco de saída (hoje linhas 151-168) com:

```
White's Reality Check (N=<len(GRID)> configs, <n_boot> bootstraps de bloco): p = <x>
  -> p<=0.05 = a melhor config bate a sorte | p>0.05 = indistinguível de sorte
FDR (Benjamini-Hochberg, q=0.10): <k> de <N> configs sobrevivem
Bootstrap IC95% (bloco): [a, b]   (IID era: [c, d]  <- quanto o IID inflava)
```

E mudar o veredito final (linha 165) para exigir **as quatro** condições:
`IC-bloco > 0` **E** `DSR > 0.95` **E** `reality_check.p <= 0.05` **E** `pelo menos 1 config sobrevive ao FDR`.

**1e. Rodar retroativamente**

Depois de pronto, rodar `python validacao.py` na tendência de novo e registrar os números.
Não vai mudar o veredito (DSR = 0,004 não se salva), mas fecha a documentação com o
instrumento completo.

#### Aceite do Item 1

- [ ] `block_bootstrap_idx`, `reality_check`, `fdr_bh`, `pnl_por_periodo` implementados em
      `validacao.py`, sem dependência nova (numpy/math puro — seguir o padrão do
      `_norm_ppf` Acklam que já está lá).
- [ ] Testes determinísticos em `test_validacao.py` (usar `random.seed`):
      - série de puro ruído N(0,1) → Reality Check deve dar `p` alto (não rejeita) na
        maioria das seeds;
      - série com drift positivo forte injetado numa config → `p` baixo (rejeita H0);
      - `fdr_bh([0.001, 0.2, 0.5], q=0.1)` → só o primeiro sobrevive;
      - `pnl_por_periodo` com trades conhecidos → soma diária correta e períodos vazios = 0.
- [ ] `walk_forward()` imprime as 4 métricas e o veredito conjunto.
- [ ] Rodada retroativa da tendência registrada no fim deste arquivo (§7).

---

### ITEM 2 — Mean-reversion formal via Ornstein-Uhlenbeck 🟠

**Arquivos novos:** `ou.py` (estimação e sinal), `validar_ou.py` (runner de validação).
**Fonte conceitual:** cantaro86 notebooks 6.1 (OU), 5.1/5.2 (Kalman).
**Esforço:** médio. **Valor:** reabre uma classe descartada por implementação, não por teste.

#### Modelo

OU: `dX = θ(μ − X)dt + σ dW`. Estimação por AR(1) sobre a série discreta:

```
X_{t+1} = a + b·X_t + ε
θ  = −ln(b) / Δt                       (velocidade de reversão; exige 0 < b < 1)
μ  = a / (1 − b)                       (média de longo prazo)
σ_eq = sd(ε) / sqrt(1 − b²)            (desvio de equilíbrio — a régua do z-score)
meia_vida = ln(2) / θ                  (em barras)
```

```python
def estimar_ou(x):
    """x: array 1D (log-preço ou spread). Retorna dict(theta, mu, sigma_eq, meia_vida, b, r2)
    ou None se b>=1 / b<=0 (sem reversão) ou amostra < min."""
```

#### Onde aplicar (duas frentes, nesta ordem)

**Frente A — ativo único, log-preço.** Mais simples, mas **espere fracasso**: log-preço de
cripto tende a ser não-estacionário (é justamente por isso que trend-following existe).
Obrigatório **portão de estacionariedade** antes de operar.

**Frente B — spread entre dois ativos (a que realmente importa).** OU vive em *spread*, não em
preço. Ex.: `spread = log(P_ETH) − β·log(P_BTC)`, com `β` estimado por regressão rolante ou
por **filtro de Kalman** (notebook 5.1 — hedge ratio dinâmico é superior a β fixo). Testar
pares dentro do nosso universo de 12 moedas: L1s entre si (ETH/BTC, SOL/AVAX, BNB/BTC),
não pares aleatórios.

#### Portões (não negociáveis)

1. **Estacionariedade:** teste ADF no spread da janela de treino. Sem ADF significativo
   (p < 0,05), não opera. Sem `scipy`/`statsmodels` no runtime → duas saídas aceitáveis:
   (a) implementar ADF com valores críticos de MacKinnon direto em `ou.py`; ou
   (b) usar `statsmodels` **apenas** em `requirements-pesquisa.txt`. **Preferir (b)** para
   pesquisa — mais rápido e menos superfície de bug — e só portar à mão se algum dia isso
   for pro ao vivo.
2. **Meia-vida sã:** só operar se `2 <= meia_vida <= 50` barras. Meia-vida muito curta = ruído/
   custo; muito longa = capital preso e o regime muda antes.
3. **Parâmetros SÓ do passado:** estimar em janela rolante (ex.: 500 barras) e **refit a cada
   N barras** (ex.: 50). Nunca estimar no período inteiro e depois "operar" nele — isso é o
   look-ahead clássico que mataria o resultado.

#### Regra de trade

- `z = (X_t − μ) / σ_eq`, com μ e σ_eq **da janela de treino anterior**.
- Entra contra o desvio quando `|z| >= z_entrada` (grid: 1,5 / 2,0 / 2,5).
- Alvo: `z = 0` (volta à média). Stop: `|z| >= z_stop` (grid: 3,0 / 4,0).
- **Time-stop:** `k × meia_vida` barras (grid k: 2 / 3). Se não reverteu em k meias-vidas, a
  hipótese de reversão foi refutada — sai. (Esse é o parâmetro que o RSI+Bollinger não tinha
  e que pode ser exatamente o que arrumava o payoff.)

#### Custo (a parte que mata, modelar desde o primeiro run)

- Frente A: 2 pernas de taxa (entrada + saída) → `2 × 0.0005`.
- **Frente B: 4 pernas** (abre 2 ativos, fecha 2 ativos) → `4 × 0.0005 = 0.2%` por round-trip.
  **Foi exatamente isso que matou o funding arb.** Se o movimento médio capturado não for
  confortavelmente maior que 0,2%, a estratégia está morta antes de começar — cheque isso
  **primeiro**, com um cálculo de guardanapo, antes de escrever o backtest inteiro.
- Alavancagem: **1x** nesta pesquisa. Alavancagem não cria edge, só amplifica (já provado).

#### Validação

`validar_ou.py` **tem que** usar `validacao.walk_forward()` — inclusive os critérios novos do
Item 1. Não criar régua paralela. Isso pode exigir generalizar `walk_forward()` para aceitar
uma função de backtest injetada em vez de chamar `backtest_ativo` direto (linha 122) — fazer
essa refatoração de forma que a chamada atual continue funcionando.

#### Aceite do Item 2

- [ ] `ou.py` com `estimar_ou`, `adf` (ou wrapper), `sinal_ou`, e estimação **rolante**.
- [ ] Teste determinístico: simular um OU sintético com θ e μ **conhecidos** → o estimador
      recupera os parâmetros dentro de ~10%. Sem esse teste passando, qualquer resultado de
      backtest é lixo.
- [ ] Teste de não-reversão: alimentar um random walk puro → `estimar_ou` retorna None ou
      ADF reprova (não pode gerar sinal em passeio aleatório).
- [ ] Backtest com custo maker correto (2 ou 4 pernas conforme a frente), 1x.
- [ ] Rodado por `validacao.walk_forward()` com os 4 critérios do Item 1.
- [ ] Veredito registrado na §7 — **positivo ou negativo**.

---

### ITEM 3 — Dollar bars (barra por volume financeiro) 🟡

**Arquivos novos:** `barras.py` (construtor), `validar_barras.py` (runner).
**Fonte conceitual:** ML4T Cap. 4 (microestrutura e construção de barra; ideia original de
López de Prado, *Advances in Financial ML* cap. 2).
**Esforço:** médio. **Valor:** é o **único eixo do problema que nunca variamos**.

#### Tese

Barra de tempo (15m, 1h, 4h) amostra o mercado em intervalo fixo, independente de atividade —
gera retornos com heterocedasticidade e sazonalidade intradiária fortes. Barra de **dólar**
(fecha a cada X de volume financeiro negociado) amostra por **informação**, e a literatura
mostra retornos mais próximos de IID/normal. Todo o nosso projeto rodou em barra de tempo.

#### Passo 3.0 — pré-check estatístico (FAÇA ISSO ANTES DE QUALQUER BACKTEST)

Não reprocessar a estratégia inteira antes de confirmar que a barra nova é estatisticamente
melhor. Comparar, sobre o mesmo período e mesmo ativo, retornos de time bars vs dollar bars:

- autocorrelação de lag 1 dos retornos (|ACF| menor é melhor);
- Jarque-Bera / assimetria e curtose (mais perto de normal é melhor);
- teste de heterocedasticidade (ex.: ACF dos retornos **ao quadrado**).

**Se as propriedades não melhorarem, PARE e registre.** O item morre aqui, barato.

#### Construção

```python
def dollar_bars(df_1m, limiar):
    """Constrói barras de dólar a partir de OHLCV de 1m.
    Acumula close*volume até passar `limiar`, então emite a barra:
      open  = open da primeira barra do bucket
      high  = max(high), low = min(low)
      close = close da última
      volume = soma, timestamp = timestamp da última
    Retorna DataFrame com as MESMAS colunas de dados.baixar_ohlcv (+ datetime),
    para plugar direto em scoring.preparar().
    """

def calibrar_limiar(df_1m, barras_por_dia_alvo):
    """limiar = volume financeiro total / (dias * barras_por_dia_alvo).
    Para comparar de igual pra igual com 15m: barras_por_dia_alvo=96. Com 1h: 24."""
```

**Comparação justa:** calibrar o limiar para produzir **aproximadamente o mesmo número de
barras** que o timeframe de tempo comparado. Senão você está comparando frequência de trade,
não tipo de barra, e o resultado não quer dizer nada.

**Aproximação honesta a declarar:** construir dollar bars a partir de OHLCV de 1m perde a
ordem intra-minuto dos negócios. O ideal seria tick data (que não temos de graça). É
aproximação aceitável — **documente no docstring**, não esconda.

`dados.baixar_ohlcv` já pagina e cacheia por data (`dados.py:16-17`); baixar 1m de 60-90 dias
por moeda é volumoso mas viável. Atenção ao tamanho do `dados_cache/`.

#### Armadilha de integração (LEIA COM ATENÇÃO)

`backtest_ativo()` assume **duração fixa de barra** em dois lugares:

- `tfh` (linha 33) converte índice de barra em horas para o **custo de funding** (linha 80:
  `(i - pos["i0"]) * tfh / 8`);
- `max_hold` (time-stop da reversão, linha 71) conta **barras**.

Com dollar bars a duração é **variável**. Corrigir: usar o timestamp real —
`(tss[i] - tss[pos["i0"]]) / 3_600_000` horas — em vez de `(i - i0) * tfh`. Fazer isso de forma
retrocompatível (se a duração for fixa, o resultado tem que bater com o de hoje; escrever um
teste que confirma isso).

#### Experimento

Rodar a **mesma** estratégia de tendência, **sem mudar nada em `scoring.py`**, sobre dollar
bars, via `validacao.walk_forward()`. Comparar lado a lado com o resultado conhecido de barra
de tempo (OOS: 370 trades, win 25,4%, PnL −R$807, DSR 0,004).

#### Aceite do Item 3

- [ ] Pré-check estatístico rodado e reportado ANTES do backtest.
- [ ] `dollar_bars` e `calibrar_limiar` com teste determinístico (entrada sintética conhecida →
      buckets corretos; OHLC do bucket correto; nenhuma barra vazia).
- [ ] Correção de duração variável em `backtest_ativo` + teste de retrocompatibilidade em
      barra de tempo.
- [ ] Walk-forward completo (critérios do Item 1) comparando time bars vs dollar bars.
- [ ] Veredito registrado na §7.

---

## 4. Ordem de execução

```
Item 1 (Reality Check + FDR)  ─┬─→  Item 2 (OU)      ─→ veredito
                               └─→  Item 3 (barras)  ─→ veredito
```

**Item 1 primeiro, sempre.** Ele é a régua. Rodar Item 2 ou 3 antes de ter a régua nova
significa medir com instrumento que já sabemos ser incompleto — e correr o risco de
"aprovar" ruído.

Itens 2 e 3 são independentes entre si; podem ir em paralelo depois do 1.

---

## 5. Backlog secundário (só depois dos 3 itens, e só se fizer sentido)

### 5.1 Revisar funding arb contra o Case Study 2 do ML4T
Nosso `funding_estudo.py` concluiu não-deployável (+1,9%/ano always-in). Caveat registrado:
**não modelamos o basis** (spread spot-perp). Ler o estudo de caso 2 do ML4T (funding-rate arb
em perp, frequência 8h) e checar: (a) eles modelam basis e convergência? (b) qual custo de
execução assumem? (c) o resultado deles é compatível com o nosso? Se o basis mudar a
conclusão materialmente, o estudo merece uma v2. Se não, fechamos o assunto de vez.

### 5.2 Triple-barrier labeling (ML4T cap. 7)
Formalizar saída como três barreiras (alvo, stop, tempo) calibradas por **volatilidade**
(ex.: múltiplos de ATR) em vez de percentual fixo. Nosso trailing stop (`simulador.atualizar`,
`trailing_dist` padrão 2%) e o gestor de saída são heurísticos. Isso é melhoria de **formato**
de payoff, não de edge — e já sabemos que formato não cria alfa. Baixa prioridade, mas é a
peça certa se algum dia um sinal passar na régua.

### 5.3 Modelo de custo de transação (ML4T cap. 18)
Hoje modelamos taxa fixa (`TAXA`) + slippage fixo (`slip=0.0002`). Custo real varia com
tamanho e liquidez (impacto de mercado). Para R$100 de nocional é irrelevante; viraria
relevante só com capital maior. **Não fazer agora.**

### 5.4 Viés de sobrevivência (ML4T cap. 2)
`AUDITORIA-SISTEMA.md` item (5): nosso universo (`COINS` em `validacao.py:24-25`) é composto
só de sobreviventes de 2026. Backtests de 2022-2024 nesse universo são otimistas por
construção. Correção: montar universo **point-in-time** (top-N por volume **na data**, não
hoje). É trabalhoso (precisa de histórico de listagem/volume) mas é um viés real e conhecido.

### 5.5 `vectorbt` (do awesome-quant)
Só se o tempo de sweep virar gargalo mensurável. Em `requirements-pesquisa.txt`, nunca no
runtime.

---

## 6. Critério de aceite — vale para QUALQUER estratégia daqui pra frente

Uma estratégia só é considerada com edge se **todas** as condições abaixo forem verdadeiras:

1. Validada por `validacao.walk_forward()` — parâmetros escolhidos **só** no treino (passado),
   avaliados no teste (futuro não-visto). Nunca split por moeda no mesmo período.
2. Bootstrap **de bloco** IC95% da média/trade **não inclui 0**.
3. **DSR > 0,95** com `n_trials` contando honestamente as tentativas.
4. **White's Reality Check p ≤ 0,05**.
5. Ao menos uma config sobrevive ao **FDR (BH, q = 0,10)**.
6. Custo **maker** modelado, com o número correto de pernas.
7. Sem look-ahead: sinal em candle fechado, execução no open seguinte + slippage.
8. Alavancagem **1x** na fase de validação. (Alavancagem entra depois, se entrar, como decisão
   de sizing — nunca como muleta pra fazer um resultado ruim parecer bom.)

Falhou em qualquer uma → **não tem edge**. Documentar e seguir.

---

## 7. Registro de resultados (preencher conforme executar)

| Item | Data | Resultado | Veredito |
|---|---|---|---|
| 1 — Reality Check + FDR | | | |
| 1e — tendência retroativa | | | |
| 2 — OU frente A (ativo único) | | | |
| 2 — OU frente B (spread/pares) | | | |
| 3.0 — pré-check estatístico barras | | | |
| 3 — dollar bars, tendência | | | |

---

## 8. O que NÃO fazer

- ❌ Não instalar o ambiente do ML4T (deep learning, RL, brokers). Ler e portar o conceito.
- ❌ Não adicionar dependência ao `requirements.txt` do runtime. Pesquisa vai em
  `requirements-pesquisa.txt`.
- ❌ Não mexer em `autotrader.py`, `simulador.py`, `api.py`, `index.html` neste plano.
- ❌ Não implementar nada do Grzelak (pricing de opção) — não há opção no roadmap.
- ❌ Não ajustar parâmetro olhando o resultado OOS. Isso é o data snooping que os itens deste
  plano existem justamente para detectar.
- ❌ Não comemorar amostra pequena. O walk-forward precisou de 370 trades para concluir;
  4 trades bons não são sinal de nada (já caímos nessa uma vez).
- ❌ Não esconder resultado ruim. É o produto.

---

## 9. Referências

- awesome-quant — <https://github.com/wilsonfreitas/awesome-quant>
- Computational-Finance-Course — <https://github.com/LechGrzelak/Computational-Finance-Course>
- machine-learning-for-trading — <https://github.com/stefan-jansen/machine-learning-for-trading>
- Financial-Models-Numerical-Methods — <https://github.com/cantaro86/Financial-Models-Numerical-Methods>

Documentos internos relacionados:
- `BASE-CONHECIMENTO-TRADING.md` — base teórica do projeto (6 seções, fontes: Carver,
  López de Prado, AQR, FGV/Barber-Odean). §6.2 lista estratégias candidatas por evidência.
- `AUDITORIA-SISTEMA.md` — 21 bugs + 45 melhorias + 6 gargalos sistêmicos; ondas 1-3 já
  implementadas.
- `validacao.py` — walk-forward + DSR + bootstrap (o que o Item 1 estende).
- `backtest_plataforma.py` — motor de backtest com paridade.
- `scoring.py` — pontuação compartilhada live ↔ backtest.
