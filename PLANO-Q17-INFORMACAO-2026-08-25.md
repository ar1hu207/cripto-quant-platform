# [Q-17] Plano — "smart money" traduzido em algo mensurável

> Sessão B, 2026-08-25. Base: `main` = `1d04857`. Card `JjYKCbYz`.
> Este documento é o **passo 1 do próprio card**: *"o primeiro passo não é medir edge — é medir
> se dá para medir"*. Nada aqui entra no `scoring`, e nenhum número de edge foi produzido de
> propósito (ver §7).

---

## 1. O que a investigação achou, em três linhas

1. **A premissa central do card está errada, e para o lado bom.** O card diz *"quase nada disso
   tem histórico gratuito de 3 anos"*. Tem. O que tem janela de 30 dias é o **REST**
   (`futures/data/*`); os **dumps diários** da Binance servem os mesmos números, de 5 em 5
   minutos, desde 2021-12-01, para as 12 moedas da régua, **sem uma única lacuna**.
2. **Nenhuma fonte cai por falta de poder.** O `T` da régua continua 1095 e o `MDS` continua
   **1,436** — abaixo do `MDS_LIMITE = 2,0`. A única fonte que cai é o **CVD verdadeiro**, e cai
   por **custo de disco** (~250 GB), não por poder — e o dump já traz um proxy de 5 min do mesmo
   fenômeno por 0,1% do custo.
3. **Já existe um `/smartmoney` em produção, na tela do dono, e ele é narrativa não medida.**
   `mercado.py:148` → `api.py:788` → `web/index.html:1540`. É literalmente a coisa que o card
   pede para traduzir, e ela nunca passou pela régua.

O portão do card, portanto, **não é o poder estatístico**. É outro, e a §4 o descreve.

---

## 2. A tabela que o critério de aceite pede

Medições feitas em 2026-08-25 contra a API pública e contra o bucket
`data.binance.vision` (`s3-ap-northeast-1.amazonaws.com/data.binance.vision`), sem chave.
`MDS` pela `pesquisa/validacao.mds_sharpe` (poder 0,80, alfa 0,05 unilateral, `PPA=365`).
A janela da régua é `DIAS = 1095` terminando hoje, ou seja **2023-08-25 → 2026-08-25**.

| Fonte | Onde ela existe de graça | Cobertura VERIFICADA | Cobre a janela da régua? | T | MDS | Testável |
|---|---|---|---|---|---|---|
| **Funding** | REST `fapi/v1/fundingRate` (pagina) | BTCUSDT desde **2019-09-10**, ETHUSDT desde **2019-11-27** | sim, com 3,7 anos de folga | 1095 | **1,436** | **SIM** |
| **Open interest** (5 min) | dump `futures/um/daily/metrics` | **12/12 moedas**, 2021-12-01 → 2026-08-24, **0 lacunas** | sim, com 1,7 ano de folga | 1095 | **1,436** | **SIM** |
| **Long/short ratio** — top posições | mesmo arquivo `metrics` | idem | sim | 1095 | **1,436** | **SIM** |
| **Long/short ratio** — top contas, global contas | mesmo arquivo `metrics` | idem | sim | 1095 | 1,436 | **MARGINAL** — não reconcilia com o vivo (§4.2) |
| **Taker buy/sell vol ratio** (proxy agregado de CVD, 5 min) | mesmo arquivo `metrics` | idem | sim | 1095 | 1,436 | **MARGINAL** — outliers de 6,8 e sem reconciliação (§4.2) |
| **CVD verdadeiro** (trade a trade) | dump `futures/um/monthly/aggTrades` | desde 2020-01, completo | sim — mas **41,3 GB comprimidos só de ETHUSDT** | 1095 | 1,436 | **NÃO — por custo** |
| **Imbalance de livro** | dump `futures/um/daily/bookDepth` | 2023-01-01 → 2026-08-24, ~0,6 GB/moeda | sim, por **~8 meses** de folga só | 1095 | 1,436 | **MARGINAL** |
| **Clusters de liquidação** | **não existe fonte** | `allForceOrders` responde **HTTP 404** (endpoint removido); não há dump de liquidação | — | — | — | **NÃO — não há dado** |

**Conclusão escrita, como o critério pede:** *das cinco fontes que o card listou, nenhuma cai por
falta de poder — o histórico existe e o MDS não se move. O que separa as fontes não é o poder, é
a **reconciliação com o caminho ao vivo** (§4.2): o **open interest** reconcilia bit a bit e é
testável sem ressalva; o `topLongShortPositionRatio` reconcilia dentro do arredondamento; as
outras duas razões não reconciliam e ficam marginais; o **CVD verdadeiro** é testável em teoria e
inviável em disco (41,3 GB só de ETHUSDT); e os **clusters de liquidação** não têm fonte pública
nenhuma — `allForceOrders` responde 404 e não há dump —, de modo que só existiriam como derivação
do open interest, o que os torna uma reescrita do OI e não uma fonte nova.*

### 2.1 As medições cruas, para ninguém ter de acreditar na tabela

**A janela de 30 dias do REST é real e é uma parede:**

```
openInterestHist ETHUSDT period=1h, variando startTime:
  -25d: n=24   -28d: n=24   -29d: n=24   -30d: n=24
  -31d: HTTP 400   -35d: HTTP 400   -45d: HTTP 400   -60d: HTTP 400
```

**O dump não tem essa parede** (`futures/um/daily/metrics/<SYMBOL>/`, zips diários):

```
BTCUSDT   n= 2184  2020-09-01 -> 2026-08-24  lacunas=0    25.3 MB
ETHUSDT   n= 1728  2021-12-01 -> 2026-08-24  lacunas=0    20.4 MB
SOLUSDT   n= 1728  2021-12-01 -> 2026-08-24  lacunas=0    19.4 MB
BNBUSDT   n= 1728  2021-12-01 -> 2026-08-24  lacunas=0    19.5 MB
XRPUSDT   n= 1728  2021-12-01 -> 2026-08-24  lacunas=0    20.2 MB
ADAUSDT   n= 1728  2021-12-01 -> 2026-08-24  lacunas=0    19.6 MB
DOGEUSDT  n= 1728  2021-12-01 -> 2026-08-24  lacunas=0    20.2 MB
AVAXUSDT  n= 1728  2021-12-01 -> 2026-08-24  lacunas=0    19.0 MB
LINKUSDT  n= 1728  2021-12-01 -> 2026-08-24  lacunas=0    20.1 MB
LTCUSDT   n= 1728  2021-12-01 -> 2026-08-24  lacunas=0    20.1 MB
DOTUSDT   n= 1728  2021-12-01 -> 2026-08-24  lacunas=0    19.5 MB
TRXUSDT   n= 1728  2021-12-01 -> 2026-08-24  lacunas=0    19.5 MB
                                        TOTAL ~243 MB comprimidos, as 12
```

**As colunas** (amostra de `ETHUSDT-metrics-2024-06-01.csv`, 289 linhas = 288 buckets de 5 min
mais o cabeçalho):

```
create_time,symbol,sum_open_interest,sum_open_interest_value,
count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,
count_long_short_ratio,sum_taker_long_short_vol_ratio
2024-06-01 00:00:00,ETHUSDT,1127415.71,4249139617.73,2.60429334,2.48699400,2.49720177,1.02574100
```

São os mesmos quatro endpoints que o card lista, num arquivo só:
`count_toptrader…` = `topLongShortAccountRatio` · `sum_toptrader…` = `topLongShortPositionRatio` ·
`count_long_short_ratio` = `globalLongShortAccountRatio` · `sum_taker_long_short_vol_ratio` =
`takerlongshortRatio`.

**MDS por T** (a conta que o card pediu):

| janela | T | MDS | veredito de poder |
|---|---|---|---|
| REST `futures/data` sozinho | 30 | 8,673 | não testável |
| 180 dias (o instrumento que o `[F6]` aposentou) | 180 | 3,541 | não testável |
| 365 dias | 365 | 2,486 | não testável |
| **`DIAS=1095` — a régua de hoje** | **1095** | **1,436** | **testável** |
| janela comum do dump (2021-12-01) | 1729 | 1,142 | testável |
| dump do BTC (2020-09-01) | 2185 | 1,016 | testável |
| funding desde 2019 | 2463 | 0,957 | testável |

O ganho de esticar a janela além de 1095 é real mas pequeno (1,436 → 1,142) e **custa a
comparabilidade com todo o resto do M4**. Recomendação: **não mexer no `DIAS`**. O que o dump
compra aqui não é poder — é a existência do dado.

---

## 3. O terceiro achado: o `/smartmoney` que já está em produção

O card pergunta como traduzir "smart money" em algo mensurável. **O sistema já respondeu essa
pergunta uma vez, sem medir, e a resposta está na tela do dono.**

`mercado.py:148`:

```python
def smartmoney(ativo):
    f = funding(ativo)                       # em %, ou seja fundingRate * 100
    if f > 0.01:
        leitura = "🔴 longs lotados (funding alto) → risco de squeeze pra BAIXO"
    elif f < -0.01:
        leitura = "🟢 shorts lotados (funding negativo) → risco de squeeze pra CIMA"
    else:
        leitura = "⚪ funding neutro — sem multidão clara"
    return {..., **zonas_liquidez(ativo)}     # topos/fundos de swing com k=5, limite=200
```

Medido contra os 3.285 settlements de funding de cada moeda nos últimos 3 anos:

| moeda | "longs lotados" dispara | "shorts lotados" dispara | neutro | mediana f/8h | média f/8h |
|---|---|---|---|---|---|
| BTCUSDT | 8,3% | **0,4%** | 91,3% | +0,0059% | +0,00666% |
| ETHUSDT | 9,4% | **1,0%** | 89,6% | +0,0061% | +0,00689% |
| SOLUSDT | 9,9% | 7,8% | 82,4% | +0,0049% | +0,00462% |

O que isso diz:

- O limiar é **simétrico** (`±0,01%`) sobre uma distribuição que **não é** — o funding de
  BTC/ETH é positivo quase o tempo todo. O ramo verde (`🟢 shorts lotados`) é, na prática, um
  texto que **quase nunca aparece** em BTC e ETH: 0,4% e 1,0% do tempo.
- `zonas_liquidez` é o `order block`/`liquidity grab` do card, escrito como topo/fundo de swing
  com `k=5` e `limite=200` — dois parâmetros escolhidos sem nenhuma medição, no exato formato
  que o card diz não poder entrar sem teste.
- Nada disso alimenta decisão: o `/smartmoney` é só leitura de tela. **Mas está na tela**, com a
  palavra "smart money" nela, e o dono lê aquilo como se fosse medida.

**Isto é um defeito, e ele não depende de edge nenhum.** Ou os limiares passam a sair de um
quantil medido do histórico (o `fundingRate` está aqui, é grátis e tem 6 anos), ou o painel para
de chamar aquilo de "smart money". Vira card próprio — ver §6, Fase 4.

---

## 4. O portão de verdade deste card: **paridade de 30 dias**, não poder

Esta é a conclusão mais importante do plano, e ela **não estava no card**.

O backtest lê 4,7 anos do dump. **O bot ao vivo lê 30 dias do REST.** Logo:

> **Toda feature deste card tem de ser computável com uma janela de lookback estritamente menor
> que 30 dias.**

Uma feature do tipo *"z-score do open interest contra a média de 1 ano"* backtesta lindamente e
**não pode ser calculada em produção**. Não é uma dificuldade de implementação: é a mesma
quebra de paridade que o `[Q-5]` existiu para consertar, e ela apareceria como um sistema que
mede uma coisa e opera outra.

Corolários que viram teste, não comentário:

- **Teto de janela declarado.** Recomendo **≤ 14 dias** de lookback, não 29: o dump é D+1 e o
  REST tem indisponibilidade; 14 dias dá o dobro de folga para um backfill atrasado.
- **Reconciliação dump × REST.** O backfill e o vivo são **dois caminhos de código para o mesmo
  número**. Tem de existir um teste que baixa um dia presente nos dois e compara. Sem ele, o
  backtest mede uma série e o vivo outra, e ninguém percebe.
  **Este teste foi rodado antes de o plano ser aprovado, e ele achou um look-ahead — ver §4.1.**
- **Point-in-time.** O `metrics` é carimbado de 5 em 5 minutos, e a regra ingênua ("entra o
  bucket fechado antes do fechamento da barra") **vaza futuro**. A regra correta está na §4.1 e
  é uma constante testada, não um comentário.
- **Cache com data no nome**, como o `dados.baixar_ohlcv` já faz — e atenção à armadilha
  registrada no fim do `VEREDITO-M4.md` §9: nome de cache que carrega a data de hoje, rodada que
  atravessa a meia-noite, janelas diferentes dentro da mesma comparação.

### 4.1 O look-ahead de 5 minutos que a reconciliação achou — e a regra que o mata

Rodei a reconciliação **antes** de escrever código, e ela derrubou a versão anterior desta seção.
Dump e REST **não são o mesmo carimbo**.

**A medida.** Para cada deslocamento aplicado ao dump, o erro relativo de `sum_open_interest`
contra o REST (ETHUSDT, 2026-08-15, 288 buckets):

```
  shift= -3 (-15 min): mediana=1.508e-04   max=1.273e-03
  shift= -2 (-10 min): mediana=7.827e-05   max=1.141e-03
  shift= -1 ( -5 min): mediana=0.000e+00   max=0.000e+00     <-- casa EXATO
  shift= +0 (  0 min): mediana=7.853e-05   max=1.142e-03
  shift= +1 ( +5 min): mediana=1.492e-04   max=1.274e-03
```

`287/287` valores idênticos, e o mesmo resultado em **BTCUSDT (2026-08-22)** e **TRXUSDT
(2026-08-03)**. Não é ruído: é convenção.

> **`dump[create_time = s]` é o mesmo número que `REST[timestamp = s + 5 min]`.**
> O dump carimba o bucket pelo **início**; o REST, pelo **fim**.

Logo a regra ingênua — *"usar o bucket cujo `create_time` é o fechamento da barra"* — entrega,
numa barra que fecha às 12:00, o open interest observado às **12:05**. Cinco minutos de futuro,
em toda barra, em todo trade. É o modo de falha clássico: backtest lindo, vivo que não repete.

**O atraso de publicação, medido ao vivo** (2026-08-25 18:26 UTC): a última linha servida pelo
REST estava **1,2 a 6,2 minutos** atrás do relógio, conforme o endpoint. Ou seja o dado carimbado
`t` só existe, na prática, em `t + até ~6 min`.

**A regra que este plano fixa**, juntando as duas medidas — dump `s` vale `s+5min`, publicado com
até ~6 min de atraso, com folga:

> **`valor_da_barra(T) = dump[T − 15 min]`**, e nada mais recente.

Quinze minutos de defasagem numa barra de 1h, em troca de zero look-ahead. A assimetria justifica:
o open interest anda ~0,1% em 5 min, então a defasagem custa quase nada, e o vazamento custa o
veredito inteiro. **Vira constante declarada com a medição ao lado, e um teste que a trava** — não
um comentário.

### 4.2 O que a reconciliação disse sobre CADA coluna — e por que ela decide a hipótese

Matriz completa (erro relativo mediano de cada coluna do dump contra cada endpoint do REST, no
melhor deslocamento). A diagonal é o mínimo de toda linha, então **o mapa de colunas da §2.1 está
certo** — mas o deslocamento **não é o mesmo para todas**:

| coluna do dump | endpoint REST correspondente | melhor shift | erro rel. mediano | reconcilia? |
|---|---|---|---|---|
| `sum_open_interest` | `openInterestHist` | **−1** | **0,00e+00** | **exato, 287/287** |
| `sum_toptrader_long_short_ratio` | `topLongShortPositionRatio` | −1 | 1,8e−05 | sim, dentro do arredondamento (285/287) |
| `count_toptrader_long_short_ratio` | `topLongShortAccountRatio` | −1 | 1,1e−04 | **não** — só 40/287 dentro do arredondamento |
| `count_long_short_ratio` | `globalLongShortAccountRatio` | −1 | 1,3e−04 | **não** — só 28/287 |
| `sum_taker_long_short_vol_ratio` | `takerlongshortRatio` | **0** | 4,1e−05 | **não** — maior diferença absoluta **6,80** |

Três consequências, e elas melhoram o plano:

1. **O critério de aceite "igualdade exigida" estava errado como eu escrevi.** Só o
   `sum_open_interest` o cumpre. Para as demais, o critério é **por coluna, com tolerância
   declarada**, e duas delas não passam nem assim.
2. **A coluna de fluxo tem shift diferente das de estoque** (0 contra −1) — coerente com o que
   elas são (o estoque é foto no fim do bucket, o fluxo é soma dentro dele). Uma regra única
   aplicada às cinco erraria uma delas nos dois sentidos. A regra da §4.1, por ser conservadora,
   cobre as duas convenções de uma vez.
3. **Isto confirma a escolha de hipótese da Fase 2, e agora por medição e não por gosto.** A
   única coluna que reconcilia **bit a bit** entre o caminho do backfill e o caminho do vivo é
   exatamente a que a hipótese recomendada usa: o open interest. As razões long/short carregam
   uma discrepância irredutível de ~1e−4, e o `taker ratio` tem outliers de módulo 6,8 — uma
   razão sem transformação é insumo ruim, e sem reconciliação é insumo proibido pela §4.

---

## 5. O orçamento de `n_trials`, que é compartilhado com o `[Q-16]` e o `[Q-18]`

`Q-16` (regime), `Q-17` (informação) e `Q-18` (janela de horário) nasceram do mesmo pedido do
dono e **os três propõem a mesma coisa**: mais uma dimensão na grade do treino. As dimensões
**multiplicam**.

`_sr0_esperado(n_obs=1095, n_trials)` — a barra que o Sharpe tem de vencer no DSR, anualizada:

| `n_trials` | SR0 anualizado | leitura |
|---|---|---|
| 100 (o piso contado de hoje) | **1,461** | a barra atual |
| 400 (um card rodando 4 opções) | 1,723 | +18% |
| 1.600 (dois cards) | 1,955 | +34% |
| **6.400 (os três, cada um com sua grade de 4)** | **2,165** | **+48%** |

Contra um **MDS de 1,436**. Ou seja: com os três cards rodando grades independentes, a régua
passa a poder **detectar** um efeito (1,436) que já **não consegue certificar** (2,165). Os três
cards se matam mutuamente, e a conta inteira aparece no último a rodar, que leva a culpa sozinho.

**Decisão que este plano recomenda ao dono:** os três cards **compartilham um orçamento**, e
isso é escrito antes de o primeiro rodar. Em ordem:

1. **`[Q-13]` primeiro, e sozinho** (`GgBouesy`). Ele não adiciona dimensão de grade — é análise
   do OOS que já existe. E ele **bloqueia**: se a convicção não ordena o resultado, o desenho de
   alavancagem muda e as grades dos outros três mudam junto. Rodar os outros antes é gastar
   `n_trials` numa grade que pode ser reescrita.
   *(A dependência que o `Q-13` declara — `lev_modo="conviccao"` do `[Q-10]` — **já está pronta**
   em `pesquisa/backtest_plataforma.py:93,302` desde `2563a26`/`d1e1eaf`; o Trello é que não foi
   movido. Ver a memória `quadro-desatualizado-q8-q12`.)*
2. Depois, **um card por vez**, com `n_trials` **cumulativo declarado** — não 100 de novo.
3. Uma feature por card, **não um menu**. O `Q-17` entra com **UMA** hipótese, não com cinco.

---

## 6. O plano de execução

Cinco fases. As fases 0 e 4 **não dependem de edge nenhum** e podem sair já; as fases 1–3 entram
na fila da §5.

### Fase 0 — fechar o `[Q-17]` como ele foi escrito *(pronta: é este documento)*
Território: `PLANO-Q17-INFORMACAO-2026-08-25.md`. Entrega: a §2 e a conclusão escrita.
**Nenhuma linha em `scoring`.** Comentário no card com a tabela; o card sai da Triagem.
*Isto é entrega, não fracasso* — e desta vez a entrega é *"dá para medir, e o motivo de eu achar
que não dava era o endpoint errado"*.

### Fase 1 — o baixador (`pesquisa/dados_derivados.py`) — **APLICADA em 2026-08-25**
Território exclusivo: `pesquisa/dados_derivados.py` + `tests/test_dados_derivados.py` +
`tests/dados/ETHUSDT-metrics-2024-06-01.csv` (fixture) + o marcador `rede` no `pytest.ini`.
Zero mudança em `scoring`, `signal_engine`, `api` ou `motor` — nada que decida nada foi tocado.

**Estado:** 18 testes novos passando, `612 passed, 1 skipped` na suíte inteira (9 min 43 s), e a
reconciliação real contra a rede executada: `sum_open_interest` **287/287 idênticos**,
`sum_toptrader_long_short_ratio` 285/287 dentro do arredondamento. Ver §6.1 — a implementação
achou dois defeitos que a leitura do plano não tinha achado.

- Baixa e cacheia os zips diários do `metrics`, alinha na grade de 1h da régua **pela regra da
  §4.1**, e devolve um `DataFrame` indexado por `timestamp` — o mesmo formato que o
  `dados.baixar_ohlcv` já devolve, para o `backtest_ativo` não precisar aprender nada novo.
- Funding vem do REST paginado (6 anos), no mesmo módulo.
- **Custo medido, e ele não é desprezível:** **não existe dump mensal de `metrics`** (só
  `aggTrades`, `bookTicker`, `fundingRate`, `*Klines` e `trades` têm mensal). São zips **diários**,
  logo `12 moedas × 1095 dias ≈ 13.100 requisições` para a janela da régua, ~150 MB.
- **O cache é imutável, e isso é medido:** rebaixei o mesmo arquivo e ele voltou **idêntico byte a
  byte**. Então o cache é chaveado por `(símbolo, dia)` e **nunca expira** — ao contrário do
  `dados.baixar_ohlcv`, que carrega a data de hoje no nome. Os 13 mil downloads acontecem **uma
  vez na vida**; rerodar é de graça, e uma queda no meio não perde nada.
- **Critério de aceite, corrigido pela §4.2** — "igualdade exigida" não sobrevive ao contato com
  o dado, e só valia para uma coluna:
  (a) **reconciliação por coluna** contra o REST num dia sobreposto, com a tolerância declarada de
  cada uma: `sum_open_interest` **exato**, `sum_toptrader_long_short_ratio` dentro do
  arredondamento de 4 casas, e as demais apenas **registradas** como não-reconciliáveis;
  (b) **teste de look-ahead** — o valor da barra `T` é `dump[T − 15 min]`, e o teste falha se
  qualquer bucket mais recente que isso alcançar a barra;
  (c) **teste de janela** — a feature declara seu lookback e ele é `<= 14 dias` (§4);
  (d) o orçamento de disco/requisições acima é respeitado, e o cache imutável é exercitado.
- **Os testes não usam rede.** Fixture com um dia real de `metrics` gravado no repositório; a
  reconciliação de verdade (que precisa de rede) fica atrás de marcador próprio e **pula sozinha**
  quando a rede não está liberada, para a suíte continuar verde offline.

### Fase 2 — a hipótese, escrita ANTES dos números
Território: um `.md` de pré-registro. **Uma** hipótese mecânica, uma grade pequena e declarada,
com **"sem filtro" dentro da grade como hipótese nula** — o protocolo que barrou o `[Q-8]`, o
`[Q-9]` e o `[Q-11]`.

A candidata que este plano recomenda, e o motivo:

> **Divergência OI × preço**, na barra de 1h: preço subindo com open interest subindo é dinheiro
> novo entrando na direção; preço subindo com OI caindo é short cobrindo, e o movimento morre
> quando a cobertura acaba.

Por que essa e não outra: (i) é **mecânica** — sinal de duas diferenças, sem desenho no gráfico;
(ii) usa **só o OI**, que é a coluna mais limpa do dump; (iii) tem lookback de **uma barra**,
então passa folgado no portão da §4; (iv) é ortogonal ao que o `scoring` já vê — o `scoring`
inteiro é preço e volume **do próprio ativo**, e OI é posicionamento, não preço.

Grade sugerida, **quatro opções, declaradas aqui**: `{sem filtro, exige OI concordante, exige OI
concordante só em tendência (ADX ≥ limiar), usa OI como peso de convicção}`.

**Ressalva de mercado, e ela é pré-existente.** A régua baixa candles de **spot**
(`ccxt.binance`, `defaultType='spot'`, `api.binance.com/api/v3`), enquanto OI, funding e razões
são de **perpétuo USD-M**. Isso não é defeito novo deste card: o sistema inteiro já é assim — o
`simulador` é papel, o preço vem de `ex_spot` e o funding vem de `ex_fut` (`simulador.py:16`), e o
backtest já cobra `funding_8h` (custo de perp) sobre candle de spot. Juntar OI de perp a candle de
spot **mantém a convenção que já existe** em vez de criar uma nova, e os carimbos são UTC nos dois
lados. Fica declarado, não consertado aqui.

**Alternativa barata, se o custo de download da Fase 1 for recusado.** Existe
`monthly/premiumIndexKlines` em **1h**, com 79 meses e **1,3 MB por moeda** — ~16 MB e ~950
requisições para as 12, contra 150 MB e 13 mil. É o prêmio (base) que *gera* o funding, na
resolução exata da grade da régua. É **pior como resposta ao card** (prêmio é preço, não
posicionamento, e o funding o projeto já tem) e **muito melhor de custo**. Fica como plano B
explícito, não como escolha silenciosa.

### Fase 3 — a régua
`walk_forward` com a dimensão nova, `n_trials` cumulativo da §5, veredito emitido sob o `PADRAO`
travado. **Custo de relógio: ~30 min por passada** — não cabe em sessão de worker, é da matriz
(`ORQUESTRACAO-ORCA.md` §14.2).
As três saídas possíveis, todas entrega: **edge**, **sem evidência de edge** (registra e não
troca o default — Caso 1 da §7.2 do `VEREDITO-M4.md`), ou **inconclusivo**.

### Fase 4 — o conserto do `/smartmoney` *(independente de tudo acima)*
Território: `mercado.py` + `web/index.html`. Card novo — sugestão de numeração ao orquestrador:
**`P2-41`**, série de plataforma e não `Q-`, porque é defeito de produto e não pergunta de
pesquisa.
Duas saídas aceitáveis, e o dono escolhe: **(a)** os limiares passam a vir de quantil medido do
histórico de funding por moeda (p90/p10 dos 3 anos, recalculado no deploy), e o texto diz o
percentil em vez de "lotados"; ou **(b)** o painel para de usar a expressão "smart money" e
passa a mostrar o número cru com a legenda do que ele é.
**Critério de aceite:** nenhum texto do painel afirma um estado de mercado que não saia de um
número medido.

### 6.1 Os dois defeitos que só apareceram quando a Fase 1 foi escrita

Registrados porque os dois são silenciosos — nenhum levanta exceção, os dois entregam um
`DataFrame` de aparência normal.

**1. A conversão de época saía em segundos.** `pd.to_datetime(...).astype("int64") // 1_000_000`
é o idioma óbvio para milissegundos e estava errado: o pandas passou a inferir `datetime64[us]`
(e não `[ns]`) para coluna vinda de texto, e com `[us]` a mesma conta devolve **segundos**.
Carimbos mil vezes menores não estouram — eles alinham com nada, e a série inteira vira `NaN` sem
uma linha de erro. Corrigido para subtração da época (independente de resolução) e travado em
`test_carimbo_sai_em_milissegundos_de_verdade`, ancorado num instante literal.

**2. A tolerância do `merge_asof` repetia o valor de ontem por 24 barras.** Eu tinha escrito teto
de **um dia**. Como o dump é D+1, todas as barras de hoje recebiam, idêntico, o open interest do
último bucket de ontem — o smoke test ponta a ponta pegou quatro barras seguidas com
`sum_open_interest = 2417752.521`. O teto passou a ser **uma barra**: fora do alcance vira `NaN`,
que é o que aquilo é. Depois do conserto, no mesmo caminho real: **0 valores repetidos** (eram 24),
e as 17 barras de hoje aparecem como ausência.

O teste que eu escrevi primeiro para cobrar isso **estava errado, e o código estava certo**: a
barra que fecha às 01:00 cobre 00:00–01:00 e alcança legitimamente a última leitura de ontem
(23:55, observável às 00:10). O invariante correto não é "tudo NaN", é **"nenhum valor aparece em
duas barras"** — é assim que está escrito agora.

---

## 7. O que este plano deliberadamente NÃO fez

**Não rodou nenhum teste de edge, nem exploratório.** Olhar a associação entre OI e retorno
futuro "só para ver" é exatamente o data-snooping que a régua existe para punir: seria uma
tentativa não contada, feita antes do pré-registro, escolhendo a hipótese *depois* de ver o dado.
O `n_trials` deste projeto é um **piso contado** (`[F10]`), e este documento não o aumentou em
uma unidade.

**Não mexeu no `DIAS`.** O dump permitiria 1729 dias e um MDS de 1,142; a comparabilidade com o
M4 inteiro vale mais que 0,29 de MDS.

**Não criou nem renumerou card, nem moveu card no quadro.** Worker não numera; a §6 sugere, o
orquestrador cria.

**Não mediu `bookDepth` além de 4 moedas** (ETH, BTC, TRX, DOT — todas 2023-01-01 → 2026-08-24,
~0,6 GB cada). Por isso ele está como **MARGINAL** na tabela e não como SIM: a folga sobre a
janela da régua é de 7 meses, e uma moeda que comece depois derruba a fonte inteira. Conferir as
12 antes de considerá-lo.

---

## 8. Pendências de dono

1. **Aprovar o orçamento compartilhado da §5** — os quatro cards (`Q-13`, `Q-16`, `Q-17`,
   `Q-18`) em fila com `n_trials` cumulativo, ou cada um com sua grade e a barra do DSR subindo
   48%. É decisão de gasto, como o `P2-5`.
2. **Escolher a saída da Fase 4** — (a) limiar medido, ou (b) tirar a palavra da tela.
3. **Confirmar a hipótese da Fase 2** antes de ela ser pré-registrada. Depois de escrita, ela não
   se troca sem contar a tentativa.
