# ITEM 1 — Régua de validação rigorosa (Reality Check + FDR + purga)

**Origem:** `PLANO-REPOS-QUANT.md` §3 Item 1, estendido com achados da revisão de código.
**Data:** 2026-07-24 · **Status:** **implementada em 2026-08-23 pelo `[Q-1]`**, com uma
exceção declarada (a purga — ver §5).
**Arquivo:** `pesquisa/validacao.py` (era `validacao.py` na raiz; o `[P2-16]` moveu).

> ⚠️ **Onde este documento e a revisão divergem, vale a revisão.** `REVISAO-ITEM1.md` é o
> parecer estatístico que auditou esta proposta linha a linha, e o `[Q-1]` implementou a
> versão dela. Os pontos em que o código **não** segue o que está escrito abaixo estão
> marcados no texto com o achado que mandou mudar (`F1`..`F19`). Os maiores:
>
> | §  desta proposta | O que o código faz, e por quê |
> |---|---|
> | §3.2 "bootstrap de bloco como modo padrão em `bootstrap_ci()`" | **recusa** lista de trades; bloco só sobre série temporal (`F1`) — a lista OOS está em ordem *(fold, moeda, tempo)*, e blocos ali seriam piores que o iid |
> | §3.6 `criterio="pnl"` como default | default é `"sharpe"` (`F3`); soma bruta favorece a config que mais **opera** — o que a própria §2/P5 diagnostica |
> | §3.6 `embargo_ms` | virou `gap_pre_teste_ms` (`F4`); num walk-forward sequencial não existe treino *após* o teste para embargar |
> | §3.6 assinatura com `criterio`/`modo`/`purga` livres | `walk_forward()` **não aceita** nenhum deles (`F3`): 120 maneiras de rodar a régua é multiplicar por 120 a superfície de snooping que ela existe para detectar |
> | §3.7 "veredito exige as 4 condições" | dois blocos rotulados, não quatro condições (`F8`); o FDR saiu do veredito (`F16`) |
> | §5 "`p` alto na maioria das seeds" | prova de **uniformidade** dos p-valores (`E.3`); "p alto" é smoke test e passa com um RC que nunca rejeita |
> | ausente | `DIAS: 180 → 1095` (`F6`), MDS como portão (`F14`), tabela de sensibilidade a `n_trials` (`F10`) |

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

## 1. Estado do código *antes* do `[Q-1]` (referências verificadas em jul/2026)

> As linhas abaixo são do arquivo **antigo** e não resolvem mais: o `[P2-16]` moveu
> `validacao.py` para `pesquisa/`, e o `[Q-1]` reescreveu o conteúdo. Fica como o retrato do
> que existia quando o problema foi diagnosticado — é o que permite auditar o conserto por
> diff. Para ver o arquivo desta seção: `git show 0fcf127:pesquisa/validacao.py`.

`validacao.py` (169 linhas) tinha:

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

### Onde cada um dos seis parou (`[Q-1]`, 2026-08-23)

| | Estado | Onde ver |
|---|---|---|
| P1 régua soldada | **resolvido** — `walk_forward(gerar_trades, grid, *, n_trials)` recebe o gerador injetado, com o contrato de causalidade escrito no docstring | `pesquisa/validacao.py`, `walk_forward` |
| P2 vazamento de borda | **NÃO resolvido, e declarado.** A purga existe e desliga sozinha por falta de `ts_saida`; o relatório imprime `purga: INATIVA`. Ver §5 | `_treino`, `purga_ativa` |
| P3 bootstrap iid | **resolvido** — bootstrap circular por blocos, com a guarda `F1` que recusa lista de trades. E o instrumento agora consegue dizer que *o problema não existia*: a ACF com banda está no relatório (`F12`) | `block_bootstrap_idx`, `bootstrap_ci`, `acf` |
| P4 falta o teste de "melhor de N" | **resolvido** — White's Reality Check com índices de bloco compartilhados, mais Hansen SPA estudentizado (`F15`) e `fdr_bh`. O FDR ficou **fora** do veredito (`F16`) | `reality_check`, `spa_hansen`, `fdr_bh` |
| P5 graus de liberdade | **resolvido pela direção oposta à proposta.** A §3.6 propunha parametrizar `criterio`/`modo`/`atribuir`/`block`/`purga`, o que são 120 maneiras de rodar a régua — a revisão (`F3`) mandou **travar**. O veredito sai só do `PADRAO`; as variantes viram `sensibilidade()`, que imprime todas e não decide. E `n_trials` virou piso **contado** (`F10`) | `PADRAO`, `sensibilidade`, `N_TRIALS` |
| P6 irreprodutibilidade | **resolvido** — `numpy.random.default_rng(seed)` com `seed` no `PADRAO`, nunca o `random` global; prova de determinismo na suíte | `test_padrao_e_o_criterio_do_veredito_e_nao_muda_entre_rodadas` |

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

> **Respondidas.** As sete foram para `REVISAO-ITEM1.md` §B e voltaram com parecer; o `[Q-1]`
> implementou a resposta, não a pergunta. Em resumo, com o achado que decidiu cada uma:
>
> | | Resposta implementada |
> |---|---|
> | **Q1** empilhar 4 condições sobre nulos diferentes | Não. Dois **blocos rotulados** com o nulo escrito: A (in-sample, a família de configs) informa; B (OOS, o processo) decide (`F8`) |
> | **Q2** RC ou Hansen SPA | Os dois, lado a lado — e quando derem igual (vão dar, em N=6) isso é evidência de que o grid vale ~1 teste (`F15`) |
> | **Q3** comprimento do bloco | Sensibilidade a `block ∈ {1,2,5,10,20}` como linha fixa do relatório; `block=1` **é** o iid. Politis-White **não** (`F18`) |
> | **Q4** poder com 6 configs quase idênticas / `n_trials` honesto | `n_trials = 100` como **piso contado** das varreduras históricas, rotulado como piso; mais a tabela de sensibilidade, que é logarítmica (`F10`) |
> | **Q5** piso de amostra | Não em contagem de trades — **MDS como portão**, derivado do poder; abaixo dele o veredito é `INCONCLUSIVO` (`F14`) |
> | **Q6** consistência entre folds | Diagnóstico, **nunca** portão: com 5 folds, 5 positivos de 5 dão p = 0,031 e 4/5 dão p = 0,19. O que informa é a concentração (top-5 dias, maior fold) (`F17`) |
> | **Q7** variância empírica de SR no DSR | **Não trocar.** 6 configs quase idênticas têm variância de SR minúscula → SR0 encolhe → DSR **infla**. Piorar a régua para parecer mais rigoroso (`F19`) |

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

Estado em 2026-08-23, fechado pelo `[Q-1]`. Prova reexecutável: `python -m pytest
tests/test_validacao.py`.

- [x] `block_bootstrap_idx`, `reality_check`, `fdr_bh`, `pnl_por_periodo` em
      `pesquisa/validacao.py`, **sem dependência nova** — só `math` e o `numpy` que já é
      dependência de runtime (`requirements.txt`). Mais `spa_hansen` (`F15`),
      `probabilistic_sharpe` (`F8`), `mds_sharpe` (`F14`), `sensibilidade_n_trials` (`F10`),
      `acf` e `concentracao` (`F12`/`F17`), `controle_nulo` (`F9`, parcial).
- [ ] ~~`ts_saida` em `backtest_plataforma.py:82`~~ — **NÃO FEITO, e não por esquecimento.**
      `pesquisa/backtest_plataforma.py` é território do `T-EDGE` (onda 3 do M4, `P1-10`), e
      escrever nele reprovaria no portão de fronteira mesmo com o código certo. Consequências,
      todas declaradas em vez de silenciadas:
      - a **purga** (§3.2) está implementada e desliga sozinha; `walk_forward` devolve
        `purga_ativa=False` com o motivo, e o relatório imprime `purga: INATIVA -- ...`;
      - `atribuir="saida"` (§3.3) **levanta `ValueError`** se o trade não trouxer `ts_saida`,
        em vez de cair calado para a entrada; o `PADRAO` declara `"entrada"`, que é o que
        roda de verdade;
      - o vazamento de borda de fold da §2/P2 continua presente e **continua não medido**
        (`F13`). Ele empurra o resultado para **cima**, ou seja, contra a conclusão negativa —
        então não serve de desculpa para o número ruim.
- [x] `walk_forward` generalizado com injeção de gerador + seed + retorno estruturado;
      `walk_forward_tendencia()` mantém `python -m pesquisa.validacao` fazendo o que fazia.
      **Duas divergências deliberadas da assinatura da §3.6:** `criterio`/`modo`/`atribuir`/
      `block` **não** são parâmetros (`F3` — o veredito sai só do `PADRAO`; as variantes vivem
      em `sensibilidade()`, que imprime todas, sempre, e não decide); e `embargo_ms` virou
      `gap_pre_teste_ms` (`F4`).
- [x] `tests/test_validacao.py` com testes determinísticos e **sem rede** (o gerador injetado
      da §3.6 é o que torna isso possível). Onde a lista abaixo foi endurecida, a razão está
      no teste:
      - ~~ruído puro → `p` alto~~ → **tamanho e uniformidade** dos p-valores sobre M painéis
        de ruído branco (`E.3`): "p alto" passa com louvor num RC que nunca rejeita nada;
      - drift positivo forte numa config → `p ≤ 0,05`;
      - `fdr_bh([0.001, 0.2, 0.5], q=0.1)` → só o primeiro sobrevive; mais `m=1`, empates e
        `q=1,0`;
      - `pnl_por_periodo` com trades conhecidos → soma por período correta, vazios = 0;
      - purga nos dois sentidos: trade que cruza a borda não entra no treino, e `purga=False`
        reproduz a contagem antiga;
      - `block_bootstrap_idx` devolve n índices, blocos contíguos, wrap circular, determinismo;
      - **acrescentados**: IC de bloco vs iid sob AR(1) com `φ` conhecido, exigindo o fator
        `sqrt((1+φ)/(1−φ))` (testa a *estatística*, não a mecânica); RC com N=1 reduzindo ao
        bootstrap unilateral da média; `p > 0` sempre (`F5`); o portão de MDS emitindo
        `INCONCLUSIVO`; o `PADRAO` travado (`walk_forward` recusa `criterio=`); DSR sobre a
        série diária < DSR sobre a lista de trades.
- [x] Relatório em **dois blocos rotulados** com o nulo de cada um escrito (`F8`) —
      Bloco A informa, Bloco B decide — mais sensibilidade a critério/modo/`block`, tabela de
      sensibilidade a `n_trials`, ACF com banda, concentração, e veredito de **três** valores.
- [ ] **Rodada retroativa da tendência registrada na §6 — PENDENTE, e é o único item de
      entregável que ficou aberto.** O instrumento está pronto e provado em dados sintéticos;
      o que falta é apontá-lo para os dados reais, e isso são ~30 min de CPU que não cabem numa
      sessão de agente em segundo plano. Passou para a matriz (`ORQUESTRACAO-ORCA.md` §14.2).
      Ver a §6 para o comando e para o que **não** fazer com a tabela enquanto ela está vazia.

---

## 6. Registro de resultados

### Tendencia, regua nova, rodada retroativa de 2026-08-23 (`[Q-1]`)

Comando, da raiz do repositorio: `python -m pesquisa.validacao`. Dados: 12 moedas x 1h x
1095 dias da Binance (26.280 candles por moeda), cache datado em `pesquisa/dados_cache/`.
Reprodutivel: `seed=42` no `PADRAO`, `numpy.random.default_rng`, nunca o `random` global.

**Saida literal:**

```
=== WALK-FORWARD: tendencia | 1h 1095d | 10x | 6 configs x 5 folds ===
PADRAO (travado): criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga: INATIVA -- backtest_plataforma.py:82 nao grava ts_saida (territorio T-EDGE)
n_trials = 100 (PISO CONTADO, nao estimativa)

 fold   config (conv/adx)   trades    pnl OOS
    1            (65, 25)      390  R$   +196
    2            (50, 22)      537  R$  +5817
    3            (55, 22)      528  R$  -1219
    4            (55, 22)      503  R$   +889
    5            (50, 22)      616  R$  -4690

OOS agregado: 2574 trades | win 29.8% | PnL R$+993
  serie diaria da JANELA OOS: 908 dias (721 com P&L nao-nulo) -- o 1o dos 6 segmentos e treino puro e nao entra

-- BLOCO A -- in-sample, a familia de configs. Nulo: max_k E[f_k] <= 0.
   pergunta: 'a melhor do grid bateu a sorte NO DADO QUE A ESCOLHEU?'  papel: DIAGNOSTICO
   White's Reality Check (N=6 configs, 2000 bootstraps de bloco): p = 0.4928
   Hansen SPA (estudentizado):                                     p = 0.4988
   p da melhor config SOZINHA (sem multiplicidade):                p = 0.4033
     -> o grid custou 0.09 de multiplicidade. [F12]
   DSR da melhor config in-sample (50, 22) sobre a SERIE DIARIA (1089 dias): DSR = 0.0095
     (sr=0.007 vs sr0_esperado=0.0767 para n_trials=100)
   [contraste] o numero ANTIGO -- DSR sobre a lista de 2574 trades OOS: 0.0116
     -> objeto errado duas vezes: trades correlacionados contados como independentes, e o agregado OOS em vez da melhor config in-sample. [Q-1 1 e 3]
   FDR (Benjamini-Hochberg, q=0,10): 0 de 6 configs sobrevivem -- FORA do veredito, nao-informativo em N=6 [F16]

   sensibilidade a n_trials (a dependencia e LOGARITMICA -- [F10]):
    n_trials       sr0      DSR
           6    0.0394   0.1377
          30    0.0628   0.0301
         100    0.0767   0.0095
        1000    0.0986    0.001
       10000     0.117   0.0001

-- BLOCO B -- out-of-sample, o PROCESSO. Nulo: E[pnl do walk-forward] <= 0.
   pergunta: 'o procedimento, aplicado cego pra frente, ganha dinheiro?'  papel: DECISAO
   IC95% da media/dia -- bloco (block=5): (-13.1424, 15.8736)   iid: (-11.0114, 14.479)
   PSR (sem deflacao, SR*=0): 0.5697  (sr/dia = 0.0057)
   Sharpe ANUALIZADO: 0.109   IC95% (bloco): (-1.688, 1.343)
   MDS (Sharpe anualizado minimo detectavel, 80% de poder, alfa=0,05, T=908): 1.576
     -> comparacao de poder: T=180 dias daria MDS 3.54; T=1095 daria 1.44. [F6]
   concentracao [F17]: top-5 dias = 0.223 do lucro bruto | folds positivos 3/5 | maior fold = 5.86 do total
     (com 5 folds, 5 positivos de 5 dao p=0,031 e 4/5 dao p=0,19 -- diagnostico, nunca portao)
   ACF do P&L diario, lags 1..10: [0.2217, 0.0323, -0.0051, -0.0028, -0.021, -0.0143, -0.0434, -0.0384, 0.021, 0.0251]
     banda +-1,96/sqrt(T) = +-0.065 -- fora dela = autocorrelacao real [F12]

=> VEREDITO: SEM EVIDENCIA DE EDGE (IC-bloco (-13.1424, 15.8736) inclui 0 ou PSR 0.5697 <= 0,95 ou RC p = 0.4928 > 0,05).
   IC95% do Sharpe anualizado: [-1.688 ; 1.343].
   O teste NAO exclui edges de Sharpe ate 1.343 -- MDS = 1.576. Ausencia de evidencia nao e evidencia de ausencia. [F7]
```

### O que esta rodada resolveu, e nao era garantido

**1. O `P3` era real, e a revisao apostou que nao seria.** O `F12` pedia a ACF no relatorio
justamente para o instrumento poder dizer *"o problema que eu ia consertar nao existia"* -- e
chamava isso de *"desfecho provavel para holds curtos"*. Nao foi: **ACF no lag 1 = 0,2217
contra banda de +-0,065**, tres vezes fora. O IC de bloco saiu mais largo que o iid
(`(-13,14 ; 15,87)` contra `(-11,01 ; 14,48)`, ~14% mais largo), que e o sinal de que o iid
estava mesmo otimista. O motivo casa com o `F13`: em `backtest_plataforma.py:71` o `max_hold`
esta dentro do ramo `elif estrategia == "reversao"`, ou seja **a tendencia nao tem time-stop
nenhum** -- o hold e ilimitado por construcao, posicoes atravessam dias, e o P&L diario
autocorrelaciona. Trocar o iid pelo bloco nao foi cerimonia.

**2. A mudanca de objeto do DSR e conservadora, medida:** `DSR = 0,0095` sobre a serie diaria
contra `0,0116` sobre a lista de 2.574 trades. O numero antigo era o maior -- exatamente o vies
anti-conservador que o `[Q-1]` item 1 veio remover.

**3. RC e SPA colapsaram, como o `F15` previu** (0,4928 x 0,4988). Com 6 configs correlacionadas
os dois sao o mesmo teste, e isso **e** informacao: o grid inteiro vale ~1 tentativa. E a
confirmacao de que `n_trials` nao pode sair do tamanho do `GRID` -- dai o piso contado de 100.

**4. O grid nao e a fonte do snooping.** RC `p = 0,4928` contra `p = 0,4033` da melhor config
sozinha: a multiplicidade custou **0,09**. O data-snooping do projeto esta nos meses de
varredura ad-hoc, nao nas 6 configs deste arquivo -- que e o que o `n_trials = 100` desconta.

**5. O `F6` e o que permite haver veredito.** Com `T = 908` dias de janela OOS o
**MDS = 1,576**, abaixo do limite de 2,0, entao a regua **emite**. Com os `DIAS = 180` antigos
o MDS seria ~3,5 e a resposta honesta teria sido `INCONCLUSIVO` -- isto e, **o "sem edge, DSR
0,004" registrado ate hoje foi emitido por um instrumento que nao tinha poder para emiti-lo.**
A revisao dizia isso em palavras (linha 140: *"o veredito negativo atual e mais fraco do que o
documento acredita"*); agora esta dito com numero.

**6. O P&L OOS deu POSITIVO -- `+R$993` -- e o veredito continua negativo.** E o instrumento
funcionando: 3 folds positivos de 5, o fold 2 sozinho vale **5,86x o total** (+R$5.817 contra
+R$993), e os 5 melhores dias respondem por 22,3% do lucro bruto. Dispersao enorme em torno de
zero e a assinatura de ruido, e nenhuma das condicoes do Bloco B passou.

**7. E o que o teste NAO exclui.** `IC95%` do Sharpe anualizado `[-1,688 ; +1,343]`. O limite
superior admite uma estrategia boa. Os dados **nao refutam** edge; eles falham em demonstra-lo.
Um documento cujo produto declarado e o resultado negativo precisa dessa distincao mais que
qualquer outro -- e o `F7`, e e a linha que o relatorio antigo nao imprimia.

### Delta IC bloco vs IID

| | IC95% da media/dia | largura |
|---|---|---|
| bloco (`block=5`) | `(-13,1424 ; 15,8736)` | 29,02 |
| iid (`block=1`) | `(-11,0114 ; 14,4790)` | 25,49 |

O bloco e **14% mais largo**. Sob AR(1) com o `phi ~ 0,22` medido, o fator teorico
`sqrt((1+phi)/(1-phi))` e 1,25 -- a serie real nao e AR(1) puro, mas a direcao e a ordem de
grandeza batem, e a prova que amarra o fator num caso construido esta em
`tests/test_validacao.py::test_ic_de_bloco_e_mais_largo_que_o_iid_pelo_fator_certo_em_ar1`.

### Sensibilidade ao criterio de selecao

Roda em `sensibilidade()` e sai no mesmo comando, depois do contraste de funding do `[P2-10]`.
**Nao ficou registrada nesta rodada** -- a sessao foi cortada por tempo antes de a segunda
passada do grid (~13 min) terminar. O relatorio acima, que e o que o criterio de aceite pede,
esta completo. Quem retomar roda o mesmo comando com o cache do dia quente.

---

## 7. Regras invioláveis (do projeto)

1. **Sem dependência nova no runtime.** `requirements.txt` é fastapi/uvicorn/ccxt/pandas/numpy/
   pydantic e roda numa VM Azure B1s (1 vCPU / 1 GB, `MemoryMax=900M`). Dependência de pesquisa
   vai em `requirements-pesquisa.txt` — **que ainda não existe e precisa ser criado**.

   > **Corrigido em 2026-08-23 (`E.2` da revisão): esta regra estava mais estrita que a do
   > próprio projeto, e a diferença ia cobrar caro no Item 2.** Nada da plataforma viva importa
   > `pesquisa/validacao.py` — ela não está no caminho ao vivo, e o `deploy/atualizar.sh`
   > compila `./*.py` (glob de raiz, não recursivo), então `pesquisa/` nem sobe com o serviço.
   > A regra 6 do `PLANO-REPOS-QUANT.md:39-42` proíbe dependência nova no **runtime** e
   > autoriza `requirements-pesquisa.txt` explicitamente — o próprio plano recomenda
   > `statsmodels` para o ADF do Item 2. Escrever "sem dependência nova" ponto final criaria a
   > situação de bater de frente com a regra que a gente mesmo escreveu.
   >
   > **O que vale, então:** dependência nova no que a VM roda, não. Em `pesquisa/`, sim, via
   > `requirements-pesquisa.txt`. O `[Q-1]` **não precisou** de nenhuma: tudo é `math` mais o
   > `numpy` que já é dependência de runtime — e ficou puro por escolha, não por proibição.
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
