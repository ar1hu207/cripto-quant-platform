# ITEM 1 — Régua de validação rigorosa (Reality Check + FDR + purga)

**Origem:** `PLANO-REPOS-QUANT.md` §3 Item 1, estendido com achados da revisão de código.
**Data:** 2026-07-24 · **Status:** proposta, não implementada.
**Diretório:** `c:\Users\aboni\Pesquisas\1`

---

## 0. Contexto mínimo (para quem não conhece o projeto)

Plataforma de pesquisa quant + paper trading de cripto (Python, FastAPI, SQLite, ccxt/Binance).
Dinheiro fictício, preço real. Já passou por validação rigorosa e o veredito atual é:

| Estratégia | Veredito | Evidência |
|---|---|---|
| Tendência (EMA/ADX/Donchian/RSI) | ❌ sem edge | `validacao.py`: walk-forward, 370 trades OOS, win 25,4%, PnL −R$807, IC95% [−7,4; +3,5] inclui 0, **DSR = 0,004** |
| Reversão (RSI + Bollinger) | ❌ breakeven | `validar_reversao_maker.py`: +R$73 in / −R$76 OOS em ~1100 trades |
| Funding arb (cash & carry) | ❌ não-deployável | `funding_estudo.py`: +1,9%/ano always-in; gated fica negativo |

**Não existe edge deployável hoje.** O produto do projeto é o *instrumento honesto*: ele mede,
avisa quando NÃO operar e mata ideia ruim antes de dinheiro real. Resultado negativo é entregável.

**Este item não busca edge.** Ele conserta a **régua** que decide se algo tem edge. É pré-requisito
dos Itens 2 (Ornstein-Uhlenbeck) e 3 (dollar bars) do `PLANO-REPOS-QUANT.md`.

---

## 1. Estado atual do código (referências verificadas)

`validacao.py` (169 linhas) tem hoje:

| Onde | O quê |
|---|---|
| `:24-28` | `COINS` (12 moedas), `TF/DIAS/VALOR/LEV = "1h"/180/100/10`, `GRID` (3 cortes × 2 ADX = 6 configs), `N_FOLDS=5` — tudo constante de módulo |
| `:66-74` | `stats()` — n, win%, pnl, sharpe por trade |
| `:77-96` | `deflated_sharpe()` — DSR de Bailey & López de Prado, com ajuste de skew/curtose |
| `:99-109` | `bootstrap_ci()` — IC95% da média por trade, reamostragem **IID**, `random.randrange` **sem seed** |
| `:113-168` | `walk_forward(estrategia)` — a régua |

Dentro do `walk_forward`:

```
:114-115   plumbing de dados   baixa COINS/TF/DIAS -> dfs
:117-126   geração de trades   para cada config do GRID -> por_cfg
:127-131   bordas dos folds    quantis lineares entre 1o e último trade
:136-143   seleção + OOS       escolhe melhor config no treino, aplica no teste
:146-147   naive               melhor config no período inteiro (mede inflação do snooping)
:149       n_trials            len(GRID) * N_FOLDS = 30 (cravado)
:151-168   relatório           print; a função retorna None
:165       veredito            exige IC>0 E DSR>0.95
```

`backtest_plataforma.py`:

```
:25-84   backtest_ativo(...)   motor com paridade (sinal em candle fechado i, execução em open[i+1] + slippage)
:52      pos = dict(..., ts=int(tss[i+1]), ...)     timestamp de ENTRADA
:82      trades.append({"conv", "pnl", "motivo", "ts"})   <- NÃO grava timestamp de SAÍDA
```

---

## 2. Os seis problemas a resolver

**P1 — A régua está soldada a uma estratégia.** `walk_forward` carrega os próprios dados
(`:115`), itera um `GRID` cujas chaves são `min_conv`/`adx_min` (`:27`) e chama `backtest_ativo`
com assinatura fixa (`:122`). Os Itens 2 e 3 têm outros parâmetros e outra fonte de dados; do
jeito atual, cada um vai **copiar** a função. Com cópias, os critérios divergem e o "critério de
aceite universal" vira ficção.

**P2 — Vazamento na borda do fold.** A seleção de config no treino (`:138`) filtra por
`t["ts"] < tr_lim`, que é o timestamp de **entrada**. Um trade que entra antes da borda e **sai
depois** carrega P&L determinado por movimento de preço dentro da janela de teste. Hoje o efeito
é pequeno (tendência 1h, holds curtos). No Item 2 não é: o time-stop do OU é `k × meia_vida`,
com meia-vida até 50 barras e k até 3. **Pré-requisito bloqueante:** `backtest_ativo` não grava
`ts_saida` (`:82`), então purga é impossível de implementar hoje.

**P3 — Bootstrap IID destrói autocorrelação.** `bootstrap_ci` (`:99-109`) reamostra trade a
trade de forma independente, o que produz IC otimista demais para série com dependência temporal.

**P4 — Não existe teste de "o melhor de N é melhor que a sorte?".** O DSR corrige
multiple-testing de forma **paramétrica**, com um `n_trials` estimado no olho (`:149`). Falta o
teste de reamostragem que ataca a pergunta diretamente, e falta controle de FDR.

**P5 — Graus de liberdade invisíveis.** Três escolhas metodológicas estão cravadas como se
fossem verdade natural:
- critério de seleção da config = **soma bruta de PnL** (`:138-140`) — favorece a config que
  mais opera, não a melhor;
- janela de treino **expandindo** (cumulativa, `:131`) — nunca comparada com rolante;
- `n_trials` = 30 (`:149`).

**P6 — Irreprodutibilidade.** `bootstrap_ci` usa `random` global sem seed (`:106`). Rodar
`python validacao.py` duas vezes hoje dá ICs diferentes. O Reality Check acrescenta ~2000
bootstraps. A §7 do `PLANO-REPOS-QUANT.md` é uma tabela de resultados registrados — registrar
número irreproduzível é registro decorativo.

---

## 3. O que implementar

Tudo em `validacao.py` (estender, não reescrever), exceto o `ts_saida` que é em
`backtest_plataforma.py`. **Sem dependência nova** — numpy/math/random puro, seguindo o padrão
do `_norm_ppf` (Acklam) que já está no arquivo.

### 3.1 `ts_saida` no motor de backtest

`backtest_plataforma.py:82` passa a emitir também o timestamp de saída. Mudança **aditiva**
(chave nova no dict); nada que consome hoje pode quebrar.

### 3.2 Bootstrap de bloco circular

```python
def block_bootstrap_idx(n, block=None, rng=None):
    """Índices de um bootstrap circular por blocos — preserva autocorrelação.
    block padrão = max(2, int(n ** (1/3)))."""
```

Usar como modo **padrão** em `bootstrap_ci()`, mantendo o IID acessível por parâmetro. Reportar
os dois: o delta entre eles mostra o quanto o IC IID estava inflado.

### 3.3 Agregação em série temporal comum

```python
def pnl_por_periodo(trades, bordas_ts, atribuir="saida"):
    """Agrega trades em PnL por período (padrão: diário) sobre um grid de timestamps
    COMUM a todas as configs. Período sem trade = 0.0."""
```

**Decisão que diverge do plano original:** o `PLANO-REPOS-QUANT.md` especifica atribuir pelo
timestamp de **entrada**. Esta spec usa **saída** por padrão, porque o P&L é realizado na saída
e o bootstrap de bloco existe justamente para preservar a estrutura temporal — alimentá-lo com
a série deslocada contradiz o propósito. Implementar os dois modos e comparar; se der igual,
documentar e seguir.

### 3.4 White's Reality Check

```python
def reality_check(matriz_pnl, n_boot=2000, block=None, seed=42):
    """H0: a MELHOR das N configs não tem performance esperada > 0.
    matriz_pnl: {config: [pnl_por_periodo]} — todas as séries no MESMO grid e tamanho.
    Retorna {'p_valor', 'melhor_cfg', 'V'}."""
```

Algoritmo:
1. `f_k = média(pnl_k)`; `V = sqrt(T) * max_k(f_k)`.
2. Para `b` em `1..n_boot`: sortear **um único** conjunto de índices por bloco — **o mesmo para
   todas as configs** (essencial: preserva a correlação cruzada entre elas); computar `f*_k`;
   `V*_b = sqrt(T) * max_k(f*_k − f_k)`.
3. `p_valor = #{V*_b > V} / n_boot`.

### 3.5 FDR — Benjamini-Hochberg

```python
def fdr_bh(p_valores, q=0.10):
    """Ordena p_(1)<=...<=p_(m); acha o maior k com p_(k) <= k/m*q; rejeita os k menores.
    Retorna (lista de bools, limiar)."""
```

Uso: um p-valor por config (bootstrap de bloco da média contra 0), aplica BH, reporta **quantas
configs sobrevivem**.

### 3.6 `walk_forward` generalizado

```python
def walk_forward(gerar_trades, grid, *, n_folds=5, modo="expandindo",
                 criterio="pnl", purga=True, embargo_ms=0,
                 n_trials, seed=42, periodo="D", rotulo=""):
    """Walk-forward com purga/embargo.

    gerar_trades(cfg) -> [{"ts": int_ms, "ts_saida": int_ms, "pnl": float}, ...]

    CONTRATO — o gerador DEVE ser CAUSAL: cada trade só pode usar dado anterior à
    própria entrada. É isso que autoriza rodar na linha do tempo inteira e depois
    fatiar por timestamp, em vez de re-rodar em cada janela. Gerador que normaliza
    pela série inteira quebra a régua silenciosamente.

    Retorna dict: {oos, por_fold, stats, ic_bloco, ic_iid, dsr, reality_check,
                   fdr, naive, veredito}."""

def walk_forward_tendencia(estrategia="tendencia"):
    """Wrapper que mantém `python validacao.py` funcionando igual."""
```

Requisitos:
- `criterio`: pelo menos `"pnl"`, `"sharpe"`, `"pnl_por_trade"`. Rodar os três e reportar se o
  veredito muda — **a escolha do critério é um grau de liberdade do pesquisador** e essa
  sensibilidade é informação de primeira ordem.
- `modo`: `"expandindo"` (atual) e `"rolante"`.
- `purga=True`: só entra no treino trade com `ts_saida < tr_lim`.
- `embargo_ms`: descarta faixa após a janela de teste.
- `n_trials`: **sem default** — quem chama é obrigado a declarar e defender o número.
- `seed`: threaded por todo bootstrap.
- O gerador é chamado `len(grid)` vezes (uma por config, timeline inteira) — **não**
  `len(grid) × n_folds`. Custo importa: no Item 2/3 o gerador é caro.

### 3.7 Relatório e veredito

`walk_forward` **retorna estrutura**; um `relatorio(res)` separado imprime. Isso habilita
`comparar(res_a, res_b)` — necessário porque o Item 3 compara time bars vs dollar bars e o
Item 2 compara frente A vs frente B lado a lado.

Saída acrescenta:

```
White's Reality Check (N=<len(grid)> configs, <n_boot> bootstraps de bloco): p = <x>
  -> p<=0.05 = a melhor config bate a sorte | p>0.05 = indistinguível de sorte
FDR (Benjamini-Hochberg, q=0.10): <k> de <N> configs sobrevivem
Bootstrap IC95% (bloco): [a, b]   (IID era: [c, d]  <- quanto o IID inflava)
Sensibilidade ao critério de seleção: pnl=<v> | sharpe=<v> | pnl_por_trade=<v>
```

Veredito conjunto passa a exigir **todas**: `IC-bloco > 0` **E** `DSR > 0.95` **E**
`reality_check.p <= 0.05` **E** `>=1 config sobrevive ao FDR`.

### 3.8 Rodada retroativa

Rodar na tendência e registrar na §6 deste arquivo (e na §7 do `PLANO-REPOS-QUANT.md`). Não vai
mudar o veredito — DSR 0,004 não se salva — mas fecha a documentação com o instrumento completo.

---

## 4. Questões de design em aberto (o avaliador deve opinar)

**Q1 — Os testes se aplicam a objetos diferentes; empilhá-los como "4 condições" é válido?**
O Reality Check testa *"a melhor de N configs, in-sample"*. O agregado OOS do walk-forward mistura
trades de configs **diferentes** (cada fold escolhe a sua), então DSR e bootstrap ali testam *"o
processo de seleção"*, não *"uma estratégia"*. São **nulos diferentes**. Exigir os quatro é
conservador e provavelmente correto, mas o relatório precisa deixar explícito o que cada um mede
— senão a gente confunde os dois em seis meses.

**Q2 — White's RC ou Hansen SPA?** O RC é conhecido por ser conservador e sensível à inclusão de
modelos ruins no conjunto (um monte de config péssima infla o quantil e mascara a boa). O SPA
(Hansen, 2005) corrige isso com estudentização e recentragem. Vale a complexidade extra aqui?

**Q3 — Comprimento do bloco.** `n^(1/3)` é regra de bolo. Politis-White (2004) dão seleção
automática. Com nosso T (dias de trading numa janela de 180d), a escolha muda o resultado
materialmente? Vale implementar a seleção automática ou reportar sensibilidade a `block ∈ {2,5,10,20}`?

**Q4 — Poder estatístico com 6 configs quase idênticas.** O `GRID` atual é 3 cortes × 2 ADX;
todas as séries são altamente correlacionadas. Quanto poder o RC tem nesse cenário? E,
principalmente: **o data snooping real do projeto foram meses de `tune.py` e `validar_*.py`
ad-hoc, que nenhum teste formal recupera retroativamente.** Como declarar `n_trials` de forma
honesta sem fingir precisão que não temos?

**Q5 — Piso de amostra.** Nenhum critério de aceite exige N mínimo de trades OOS. O único piso no
código é `n < 5` (`:81`, `:104`), que é guard contra divisão por zero, e `len(todos_ts) < 30`
(`:128`), que decide se dá pra *rodar*, não se dá pra *aprovar*. O Item 2 (OU com portões
restritivos) vai gerar poucos trades por construção — exatamente onde um golpe de sorte passa.
Que piso propor, e ele deve ser fixo ou derivado do poder desejado?

**Q6 — Consistência entre folds.** Nada captura "um fold fez todo o dinheiro". A tendência teve
folds em gangorra (+1841 / −2240 / −1494 / −449 / +1534). Vale um critério de consistência
(ex.: mediana dos folds > 0, ou fração de folds positivos)?

**Q7 — DSR com `n_trials` pequeno.** `_norm_ppf(1 - 1/n_trials)` (`:92`) com `n_trials`=30 está
numa região confortável, mas a fórmula usa `var_sr = 1/n` como variância dos SRs entre trials —
simplificação de Bailey-LdP. Vale estimar a variância empírica entre as configs?

---

## 5. Critério de aceite

- [ ] `block_bootstrap_idx`, `reality_check`, `fdr_bh`, `pnl_por_periodo` em `validacao.py`,
      **sem dependência nova**.
- [ ] `ts_saida` em `backtest_plataforma.py:82`, aditivo, com teste de retrocompatibilidade.
- [ ] `walk_forward` generalizado com injeção de gerador + purga/embargo + seed +
      critério/modo parametrizados + retorno estruturado; `walk_forward_tendencia()` mantém
      `python validacao.py` funcionando idêntico.
- [ ] `test_validacao.py` com testes **determinísticos** (`random.seed`):
      - ruído N(0,1) puro → Reality Check dá `p` alto na maioria das seeds;
      - drift positivo forte injetado numa config → `p` baixo;
      - `fdr_bh([0.001, 0.2, 0.5], q=0.1)` → só o primeiro sobrevive;
      - `pnl_por_periodo` com trades conhecidos → soma por período correta, vazios = 0;
      - purga: trade que cruza a borda **não** entra no treino;
      - `block_bootstrap_idx` devolve n índices, blocos contíguos, wrap circular OK.
- [ ] Relatório imprime as 4 métricas + sensibilidade ao critério + veredito conjunto.
- [ ] Rodada retroativa da tendência registrada na §6.

---

## 6. Registro de resultados (preencher ao executar)

| O quê | Data | Números | Veredito |
|---|---|---|---|
| Tendência, régua nova (retroativo) | | | |
| Sensibilidade critério de seleção | | | |
| Delta IC bloco vs IID | | | |

---

## 7. Regras invioláveis (do projeto)

1. **Sem dependência nova no runtime.** `requirements.txt` é fastapi/uvicorn/ccxt/pandas/numpy/
   pydantic e roda numa VM Azure B1s (1 vCPU / 1 GB, `MemoryMax=900M`). Dependência de pesquisa
   vai em `requirements-pesquisa.txt` — **que ainda não existe e precisa ser criado**.
2. **Não mexer no caminho ao vivo** (`autotrader.py`, `simulador.py`, `api.py`, `index.html`).
   Este item é 100% pesquisa offline.
3. **Paridade e ausência de look-ahead** são invariantes: sinal em candle fechado, execução no
   open seguinte + slippage, canais com `.shift(1)`.
4. **Nada é aprovado por resultado in-sample.**
5. **Resultado negativo é entregável.** Documentar a morte com número e seguir.
6. **Não ajustar parâmetro olhando o OOS.** É o data snooping que este item existe para detectar.

---

## 8. Débito conhecido, fora do escopo deste item

A paridade backtest↔live **está quebrada hoje**: `simulador.atualizar()`
(`simulador.py:197-235`) tem trailing stop e `trailing_ativo=1` está ligado no banco, mas
`backtest_ativo` não modela trailing nenhum — o stop é fixado na entrada e nunca se move. Logo o
comportamento que o sistema ao vivo executa hoje **não é reproduzível** no backtest, e o efeito
da feature é desconhecido. Registrado aqui para que ninguém assuma que a regra 7.3 descreve o
estado atual — ela descreve a intenção.
