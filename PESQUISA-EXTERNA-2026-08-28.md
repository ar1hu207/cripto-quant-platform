# PESQUISA EXTERNA — o que a literatura diz sobre o gargalo deste bot

**Data:** 29/08/2026 (pesquisa despachada sobre o estado de 28/08)
**Método:** quatro frentes de busca independentes na web (não conhecimento de memória), com exigência de URL + ano em cada afirmação e classificação explícita da qualidade da evidência.
**Escopo:** o que prevê retorno em perpétuo de cripto; microestrutura e posicionamento; risco/sizing/carteira; fontes de dados e método de validação.

**Convenção de qualidade de evidência usada em todo o documento:**
`[PEER-REVIEWED]` · `[PREPRINT/SSRN/arXiv]` · `[LIVRO/PRÁTICA CONSAGRADA]` · `[DOCUMENTAÇÃO OFICIAL]` · `[VERIFICAÇÃO DIRETA]` (o pesquisador baixou/abriu o dado) · `[BACKTEST DE PRATICANTE]` · `[ANEDOTA]` · `[MARKETING]`

---

## 1. SUMÁRIO EXECUTIVO — as 5 conclusões que mais mudam o rumo

### 1.1 O achado interno não é anomalia local. É o resultado que a literatura prevê.

Três trabalhos independentes, sem contato entre si, mediram exatamente o que este bot mediu:

- **Frontiers in Blockchain, 2026** `[PEER-REVIEWED]` — Binance, 6 criptos, **3,4 milhões de observações de 1 minuto**, horizonte de 5 minutos, features de OFI + depth imbalance + VPIN + Kyle + Amihud. **Sharpe LÍQUIDO de −10,68 a −52,05** com taxas VIP-0. Frase do paper: *"The information is far too weak to overcome Binance VIP-0 frictions at a 5-min holding horizon."* — https://www.frontiersin.org/journals/blockchain/articles/10.3389/fbloc.2026.1811716/full
- **Mesfin, arXiv 2605.04004, 2026** `[PREPRINT]` — 14 famílias de sinais OHLCV, 947 dias de 5m, critérios pré-registrados. **Nenhuma passou.** Edge bruto de 0,07 a 1,50 pontos por trade contra 2 pontos de fricção. — https://arxiv.org/abs/2605.04004
- **Jadouli, arXiv 2607.19453, 2026** `[PREPRINT]` — Binance 2025-2026, gradient boosting com **AUC 0,885/0,896**. Custo de 31 bps por ciclo. **Todas as políticas falharam economicamente. Decisão registrada no paper: `NO_TRADE`.** — https://arxiv.org/html/2607.19453v1

**AUC de 0,885 e prejuízo.** Esse é o número que reenquadra o problema: a previsibilidade existe e é pequena demais para pagar a taxa. O `SEM EVIDÊNCIA DE EDGE` medido internamente é o resultado esperado, não má implementação nem azar.

### 1.2 A taxa não é uma variável secundária — é *a* variável, e há folga não explorada.

A medição interna já dizia: a 0,05%/lado reprova, a 0% passaria. A pesquisa acrescenta o número que faltava: **maker com desconto BNB = 0,018%/lado** (Binance USDT-M VIP 0: maker 0,02% / taker 0,05%, −10% pagando em BNB) — https://www.binance.com/en/support/faq/detail/360033544231

0,018% está **três vezes mais perto de zero do que de 0,05%**. É a única alavanca que move a variável decisiva sem precisar de sinal novo. **Com a ressalva grave da §5.1 — saída de emergência não pode ser post-only.**

E o corolário de Bysik & Ślepaczuk (arXiv 2606.00060, 2026) `[PREPRINT]`, ~70.000 barras horárias de BTCUSDT perp, walk-forward de 27 folds, custo de 10 bps: *"estratégias ingênuas baseadas em sinal colapsam assim que 10 bps de custo são impostos"*. O que restaurou lucratividade foi um **filtro de magnitude** que cortou o turnover de **10.619 trades para 251 (−97,6%)**. Conclusão dos autores: *"o principal obstáculo no trading horário de cripto não é apenas a previsibilidade fraca, mas o modo como previsões são convertidas em trades"* — https://arxiv.org/html/2606.00060

**Isso é literalmente o "menos trades, mais certos" que o dono pediu, com evidência.**

### 1.3 O dado histórico que estava travando a pesquisa é gratuito e baixa em uma hora.

O endpoint REST corta em 30 dias — confirmado na doc oficial (`openInterestHist`: *"Only the data of the latest 1 month is available"*) — https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics

**Mas o dump `metrics` do bucket público tem as mesmas séries, em 5 minutos, desde 2020-09-01 (BTC) e 2021-12-01 (alts)** `[VERIFICAÇÃO DIRETA — o pesquisador baixou e abriu os arquivos]`:

`https://data.binance.vision/data/futures/um/daily/metrics/{SYMBOL}/{SYMBOL}-metrics-YYYY-MM-DD.zip`

Colunas: `create_time, symbol, sum_open_interest, sum_open_interest_value, count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio, count_long_short_ratio, sum_taker_long_short_vol_ratio`.

**24 pares × 1.731 dias = 41.544 arquivos ≈ 487 MB, ~70 minutos com 20 conexões.** Custo: R$ 0.

E dois bônus que valem mais que o OI:
- **`taker_buy_volume` já está nos klines gratuitos** desde 2019/2020 — o portão de fluxo taker tem proxy histórico de anos, sem baixar um único aggTrade.
- **O bucket é livre de viés de sobrevivência**: FTT, LUNA, SRM, ANT, MATIC continuam lá até a deslistagem. Ammann et al. (2022, SSRN 4287573) mediu esse viés em **62,19% ao ano** equal-weighted em 3.904 criptos.

### 1.4 O risco atual destrói a banca *mesmo se o sinal fosse tão bom quanto o backtest otimista.*

Cinco posições de 3% em altcoins com ρ=0,85 dão σ_carteira de **14,07%** e **N_eff = 1,14** — cinco posições são *uma aposta e um oitavo*. Com o edge medido (WR 38,7%, PF 1,15 ⇒ b=1,821), o Kelly ótimo é **5,04%**. Você está em **2,79× Kelly**.

Acima de 2× Kelly o crescimento de longo prazo é negativo mesmo com edge real (MacLean, Thorp & Ziemba) `[LIVRO/PEER-REVIEWED]`:

| f efetivo | múltiplo de Kelly | ganho em 1.000 trades (edge REAL) |
|---|---|---|
| 1,25% | 0,25× | +172% |
| 3,00% | 0,60× | +577% |
| 5,03% | 1,00× | +878% |
| 10,06% | 2,00× | **+11%** |
| **14,07% (config atual)** | **2,79×** | **−99,1%** |

E com edge verdadeiro = zero (que é o que os 2.596 sinais dizem), o drag de variância em 1.000 trades: **−2,2% a f=0,5%; −8,7% a f=1%; −55,4% a f=3%; −100% na configuração agregada atual.**

**Isso é um orçamento de sobrevivência.** A f=0,5-1% dá para rodar 5.000 trades e ainda ter 60-90% da banca para medir. A 3% × 5 correlacionados não se chega a 500.

### 1.5 A régua de validação usada (walk-forward, 3 anos) comprou ~14 tentativas independentes — e o orçamento estourou há muito.

Bailey, Borwein, López de Prado & Zhu (2014), *Notices of the AMS* 61(5):458-471 `[PEER-REVIEWED]` — https://www.ams.org/notices/201405/rnoti-p458.pdf

Sob a hipótese nula de **zero skill**, o Sharpe máximo esperado entre N tentativas é `E[max_N] ≈ (1−γ)·Z⁻¹[1−1/N] + γ·Z⁻¹[1−1/(N·e)]`, com γ = 0,5772. Citação verbatim: *"if the researcher tries only N = 10 alternative configurations of an investment strategy, she is expected to find a strategy with a Sharpe ratio IS of 1.57 despite the fact that all have expected OOS Sharpe of zero."*

| Backtest disponível | N máximo de configurações **independentes** |
|---|---|
| 2 anos | ~7 |
| **3 anos (o nosso)** | **~14** |
| 5 anos | 45 |

24 pares × 3 timeframes × 4 políticas de saída × hiperparâmetros passa de 14 por ordens de magnitude. Pares correlacionados não são independentes — o N efetivo se estima por **PCA**, e mesmo assim quase certamente passa de 14.

**E há uma crítica peer-reviewed direta ao método usado:** Arian, Norouzi & Seco (2024), *Knowledge-Based Systems* 305:112477 `[PEER-REVIEWED]` — em ambiente sintético controlado, **CPCV é marcadamente superior (PBO menor, DSR melhor) e o walk-forward exibe deficiências notáveis na prevenção de falsas descobertas** — https://www.sciencedirect.com/science/article/abs/pii/S0950705124011110

---

## 2. TEMA 1 — O que realmente tem edge em perp de cripto

### 2.1 Momentum: sobrevive, mas encolheu

**O clássico.** Liu & Tsyvinski, *Risks and Returns of Cryptocurrency*, **Review of Financial Studies** 34(6):2689-2727, 2021 `[PEER-REVIEWED]` — momentum de série temporal forte + previsibilidade por atenção: **1 dp a mais de busca no Google por "Bitcoin" ⇒ +2,3% nas 2 semanas seguintes**. https://academic.oup.com/rfs/article-abstract/34/6/2689/5912024 · NBER w24877: https://www.nber.org/system/files/working_papers/w24877/w24877.pdf

Ressalva que quase nunca é citada junto: **é semanal, não intradiário, e não modela custo de execução em perp.**

**O decaimento — pelos próprios autores.** Borri, Liu, Tsyvinski & Wu, arXiv 2510.14435, out/2025 `[PREPRINT]` — https://arxiv.org/html/2510.14435v2

| Fator | Amostra completa | Pós-2020 |
|---|---|---|
| CMOM (momentum 2 semanas) | 0,026 (t=3,89) | 0,021 (t=3,70) |
| Momentum 12-24 semanas | **não significante** | **não significante** |
| CSIZE | −0,023 (t=−2,66) | −0,009 (t=−1,69) |
| CVALUE | −0,035 (t=−3,50) | −0,023 (t=−2,32) |

**Três papers peer-reviewed contra a robustez do momentum cross-sectional:**
- *On survivor cryptocurrency momentum*, **Finance Research Letters** 92, 2026: com 9 moedas free-floating do top-100, **"cryptocurrency momentum is not evident when applied to survivor coins"**. https://ideas.repec.org/a/eee/finlet/v92y2026ics1544612326001339.html
- *Cryptocurrency Momentum: Is It an Illusion?*, **IJFE** 31(2):2180-2193, 2026: as variâncias realizadas seguem leis de potência e **média e variância populacionais do fator não são estatisticamente definidas** — logo Sharpe é "não informativo" para esse fator. https://ideas.repec.org/a/wly/ijfiec/v31y2026i2p2180-2193.html
- *Cryptocurrency momentum has (not) its moments*, **FMPM** 39(4), 2025: em large-caps equal-weighted, **momentum não gera payoff significativo** por causa das caudas gordas. https://link.springer.com/article/10.1007/s11408-025-00474-9

**O contraponto.** *Cryptocurrency market risk-managed momentum strategies*, **FRL**, 2025 `[PEER-REVIEWED]`: escalar por volatilidade leva o retorno semanal de 3,18% → 3,47% e o **Sharpe de 1,12 → 1,42**. https://www.sciencedirect.com/science/article/abs/pii/S1544612325011377

**O fator de tendência mais bem publicado.** Fieberg et al., *A Trend Factor for the Cross Section of Cryptocurrency Returns*, **JFQA**, 2024 `[PEER-REVIEWED]` — CTREND sobre 3.000+ moedas, Sharpes de **−1,45 a 10,92, mediana 1,34**. https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178
*Ceticismo:* universo de 3.000+ moedas = microcaps inoperáveis em perp; dispersão de Sharpe de −1,45 a 10,92 entre especificações é medida de fragilidade.

### 2.2 Funding / basis / carry: a melhor evidência — e a que mais decaiu

**A magnitude.** Schmeling, Schrimpf & Todorov, *Crypto Carry*, BIS WP 1087 / CEPR DP20719 `[PEER-REVIEWED / BIS-CEPR]` — o carry chega a **60% ao ano**, explicado por *convenience yield* volátil de investidores pequenos alavancados contra escassez de capital de arbitragem. https://cepr.org/voxeu/columns/crypto-carry-market-segmentation-and-price-distortions-digital-asset-markets · https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4268371
⚠️ *O link direto do BIS deu 404 nas duas frentes que tentaram. Os Sharpes abaixo vêm de citação secundária — não verificados no original.*

**O decaimento — o número mais importante desta seção.** Borri et al., arXiv 2510.14435, 2025:
- Sharpe do carry, amostra completa (ago/2020 – mai/2025): **6,45**
- A partir de 2024: **4,06**
- Em 2025: **NEGATIVO**

Os autores registram a implicação: produtos de "yield" delta-neutro colhendo funding perderam a base econômica. **É a coisa mais próxima de uma prova de decaimento de edge que existe em cripto hoje.**

Versão mais crível e mais modesta: Fan, Jiao, Lu & Tong, SSRN 4666425 `[PREPRINT]` — carry **cross-sectional** (long funding alto / short funding baixo) com 43,4% a.a. e **Sharpe 0,74**. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4666425

**O paper mais diretamente relevante ao instrumento.** Cao, Zhai & Luo, *Anatomy of Cryptocurrency Perpetual Futures Returns*, **Journal of Futures Markets**, 2024 `[PEER-REVIEWED]` — testaram **134 preditores**, acharam **48 significantes a 5%**, e mostraram que **um modelo de dois fatores (basis + preço-volume) explica todas as 48**. https://www.research.ed.ac.uk/en/publications/anatomy-of-cryptocurrency-perpetual-futures-returns/

**Tradução operacional: em perp, quase tudo que funciona no cross-section é basis ou preço-volume disfarçado. Confluência de EMA/RSI/ADX não aparece como fator.**

**Funding como sinal direcional: evidência fraca.** Presto Research, ago/2024 `[BACKTEST DE PRATICANTE, firma séria]`, perps USDⓈ-M da Binance 2021-2024 — https://www.prestolabs.io/research/can-funding-rate-predict-price-change
- Contemporâneo (mesma janela de 7 dias): **R² = 12,5%**, relação positiva, p = 1,91e-115.
- **Preditivo (T → T+1): R² ≈ zero, p-valor grande. Sem capacidade preditiva.**
- Cross-sectional em 50 ativos a cada 5 min: alpha promissor mas **turnover diário extremo e backtest sem custo**.

**Veredito honesto: "funding acima de 0,1%/8h sinaliza topo" é `[ANEDOTA]`/`[MARKETING]`.** Tudo que defende isso (Zipmex, Phemex, Bimal Institute) cita percentis e a narrativa da FTX 2022, nunca um backtest com custo.

### 2.3 Breakout / Donchian / Turtle: mais folclore que evidência

**A favor:** Gerritsen, Bouri et al., **FRL** 34, 2019/2020 `[PEER-REVIEWED]` — *trading range breakout* tem poder preditivo significativo em BTC diário e supera buy-and-hold no Sharpe via bootstrap. https://www.sciencedirect.com/science/article/abs/pii/S1544612319303770
*Contexto que desinfla:* o Sharpe do buy-and-hold na amostra era **0,056**. A régua era baixíssima, e o período contém 2013 e 2017.

**Contra, e mais recente:** *Are simple technical trading rules profitable in bitcoin markets?*, **IREF**, 2024 `[PEER-REVIEWED]` — abordagens técnicas lucrativas antes de dez/2021 **falharam no out-of-sample subsequente, especialmente após ajuste para data snooping**. https://www.sciencedirect.com/science/article/abs/pii/S1059056024003010

**Donchian/Turtle em cripto especificamente: nenhum estudo peer-reviewed com teste de data snooping.** O que existe é blog: CoinQuant reporta +36,50% em ~4,5 anos de BTC diário com **25 trades e 36% de acerto** — menos que o próprio BTC no período, com n=25 `[BACKTEST DE PRATICANTE, amostra insuficiente]`. https://www.coinquant.ai/blog/donchian-channel-breakout-on-crypto-backtest-vs-keltner

**Diga-se com todas as letras: o portão Donchian 20 deste bot não tem sustentação empírica publicada em perp de cripto.**

### 2.4 Reversão à média e momentum intradiário: existe, em horários específicos

- *Intraday return predictability in the cryptocurrency markets: momentum, reversal, or both*, **NAJEF**, 2022 `[PEER-REVIEWED]` — existem **ambos**, e o padrão muda com saltos de preço, FOMC, liquidez e COVID. https://www.sciencedirect.com/science/article/abs/pii/S1062940822000833
- *Bitcoin intraday time-series momentum* (Reading/Birmingham) `[PEER-REVIEWED]` — o retorno da primeira meia hora prevê o da última meia hora: **retorno médio 2,28%, Sharpe 0,53**. Combinando primeira e penúltima meia-hora: **13,95% a.a., Sharpe 1,15**. https://centaur.reading.ac.uk/100181/
  *Caveat sério:* o próprio paper atribui o mecanismo a **provisão de liquidez** — quem captura é o lado passivo, não quem cruza o spread.

### 2.5 Calendário: um sobrevive, dois morreram, e o mais rigoroso não paga a taxa

**Hora do dia — sobrevive com ressalvas.** Quantpedia / Padyšák & Vojtko, SSRN 4081000, 2021 `[BACKTEST DE PRATICANTE]`: comprar BTC às 22:00 UTC e segurar 2h rendeu **CAGR 33%, Sharpe 1,58, DD −34,04%** (2015-2021). **A página não declara custos** — e são ~365 trades/ano. https://quantpedia.com/strategies/intraday-seasonality-in-bitcoin

**Dia da semana — provavelmente morto em BTC.** *Bitcoin's Weekend Effect (2014-2024)* `[PEER-REVIEWED, journal de baixo impacto]`: **nenhum gap detectável de retorno** fim-de-semana vs dia útil; só volatilidade e volume menores. https://ojs.bbwpublisher.com/index.php/PBES/article/view/11691

**Settlements de funding 00/08/16 UTC — NÃO é fonte de edge.** Kim & Hansen (2026) excluem explicitamente os quartos-de-hora que coincidem com settlement e **o padrão fica essencialmente inalterado**.

**O achado de calendário mais sólido — e a lição mais instrutiva do relatório inteiro.** Chan Kim & Peter Reinhard Hansen (o do teste SPA que já usamos), *The Quarter-Hour Effect*, arXiv 2607.09426, ago/2026 `[PREPRINT, autores de altíssimo nível]` — perps USDT-M da Binance (BTC, ETH, XRP, SOL, DOGE, ADA), jan/2021-out/2024 — https://arxiv.org/html/2607.09426v2
- Trading algorítmico periódico cria bursts previsíveis nas marcas de 0/15/30/45 min.
- **R² out-of-sample de 1,6% a 5,8%**; acurácia direcional OOS **57,12%**; Diebold-Mariano p<0,01 em 5 de 6 contratos.
- O desequilíbrio de ordens na abertura do quarto-de-hora **prevê retornos de 4 a 12 horas** (pico entre 8 e 12h); o de 1 min e 5 min tem *"little predictive association"*.
- **E o componente previsível vale ~0,5 basis point por fronteira — um décimo da taxa taker padrão e um vigésimo de um round-trip.** Os autores concluem que é *insumo para execução e provisão de liquidez, não estratégia isolada*.
- Detalhe crucial: o efeito cumulativo é **NEGATIVO na primeira meia hora** (reversão) e só depois vira positivo.

**Esse é o padrão que se repete em todo lugar: a previsibilidade intradiária existe, é estatisticamente sólida, e é pequena demais para pagar taxa.**

### 2.6 Cascatas de liquidação e stop hunts: previsibilidade não comprovada

Garcia Seuma, arXiv 2607.27070, ago/2026 `[PREPRINT]` — 7 cascatas de 2022-2025 (LUNA, FTX, carry do iene, tarifas, a de out/2025 com US$ 19 bi), testando variância rolante, autocorrelação lag-1 e Kendall-τ sobre **open interest, top-trader long/short ratio, global long/short account ratio e taker buy/sell volume ratio**. https://arxiv.org/html/2607.27070

**Conclusão: "nenhuma variável é invariante ao evento".** A variância sobe antes da maioria das cascatas **mas também sobe em janelas ordinárias** — não-específica. Preço carregou assinatura de *critical slowing down* em 5 dos 7 eventos e **ficou mudo exatamente nos 2 choques de notícia**. O único achado de nível populacional (compressão da variância do fluxo taker antes de 6 de 6 cascatas, Kendall-τ mediana −0,13 a −0,44, placebo p ≈ 5×10⁻⁶) é declarado pelos autores como *"too weak for per-event warning"*.

**Stop hunts:** há evidência peer-reviewed apenas do *substrato* — clustering em números redondos (FRL 2022: frequência de finais "00" mais que o dobro do esperado em ETH, XRP, LTC — https://www.sciencedirect.com/science/article/pii/S1544612322001179; e JEF 2026 sobre desequilíbrios em torno desses níveis). **Nenhum estudo demonstra lucro líquido ao antecipar stop hunts.** Todo o conteúdo "smart money / liquidity sweep" é `[ANEDOTA]`/`[MARKETING]`.

*Implicação direta: stop em 3×ATR com trailing de 2% em números óbvios é o lado errado dessa mesa.*

### 2.7 Por que indicador clássico falha: 25 anos de literatura de data snooping

- **Sullivan, Timmermann & White**, *Data-Snooping, Technical Trading Rule Performance, and the Bootstrap*, **Journal of Finance** 54(5):1647-1691, 1999 `[PEER-REVIEWED]` — expandiram Brock-Lakonishok-LeBaron e aplicaram Reality Check a 100 anos do Dow. A melhor regra sobrevivia ao snooping **no período original mas não entregou nos 10 anos seguintes**; no S&P 500 futuro, **nenhuma evidência de superioridade após ajuste**. https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00163
- **Bajgrowicz & Scaillet**, **JFE** 106(3):473-491, 2012 `[PEER-REVIEWED]` — Dow 1897-2011 com FDR. Dois resultados letais: **(a)** um investidor **nunca teria conseguido selecionar ex ante** as regras que seriam as melhores no futuro; **(b)** mesmo in-sample, **a performance é completamente anulada por custos de transação baixos**. https://www.sciencedirect.com/science/article/abs/pii/S0304405X1200116X
- **RSI em cripto:** *Effectiveness of the RSI Signals in Timing the Cryptocurrency Market*, **Sensors** 23(3):1664, 2023 `[PEER-REVIEWED]` — 10 criptos, 2018-2022, custo 0,1%. Sobrecompra/sobrevenda long+short **levou o portfólio à falência completa**; divergências renderam 86,15% contra 275,22% do buy-and-hold; **só usar RSI para seguir tendência** (faixa 60-80) superou o B&H. Conclusão textual: *"o RSI deve ser usado não para procurar reversões de tendência, mas para determinar e seguir a própria tendência"*. https://pmc.ncbi.nlm.nih.gov/articles/PMC9920669/
- **E o problema é maior que snooping de regras:** *Non-standard errors in the cryptocurrency world*, **IRFA**, 2024 `[PEER-REVIEWED]` — geraram **20.736 desenhos de pesquisa** variando 10 decisões banais sobre 43 variáveis de ordenação. **Os erros não-padrão em cripto superam os do mercado acionário e superam claramente os erros-padrão.** Ou seja: *como* você monta o teste importa mais que o ruído do teste. https://www.sciencedirect.com/science/article/abs/pii/S1057521924000383
- *Crypto factor zoo (.Zip)*, **IRFA** 113, 2026 `[PEER-REVIEWED]` — 36 fatores, 2018-2024: **dois a três fatores eliminam todos os alphas significativos**, e os dominantes são de **liquidez** e on-chain. https://www.sciencedirect.com/science/article/abs/pii/S1057521926000645
- *Cryptocurrency anomalies and economic constraints*, **IRFA** 94, 2024 `[PEER-REVIEWED]` — 3.956 moedas, 2014-2022: **alphas de momentum caem 26% a 53% após custos**; o alpha vem majoritariamente da **perna vendida**; e as estratégias **prosperam depois de bull markets e perdem significância em bear markets**. https://www.sciencedirect.com/science/article/abs/pii/S1057521924001509
- *A reality check on trading rule performance in the cryptocurrency market: ML vs. TA*, **FRL**, 2020 `[PEER-REVIEWED]` — após White's Reality Check e fricções, retornos em excesso significativos **raramente aparecem, independente da frequência**; e **ML perde para análise técnica por causa do turnover maior**. https://www.sciencedirect.com/science/article/abs/pii/S1544612320304414

### 2.8 Realidade de mercado para calibrar expectativa

- Binance USDT-M VIP 0: **maker 0,02%, taker 0,05%**. Round-trip post-only entrada + taker saída = **7 bps**. https://tradersunion.com/brokers/crypto/view/binance/futures-fees/
- Crypto Fund Research, revisão anual 2025: BTC caiu 6,3% em 2025; o **fundo de hedge cripto médio rendeu −7,2%** — pior que o BTC. No Q4/2025: BTC −23,3%, índice de fundos −14,5%. https://cryptofundresearch.com/crypto-hedge-fund-performance/
- Man Group, *In Crypto We Trend*, dez/2024 `[PESQUISA INSTITUCIONAL]` — o Sharpe de trend-following em cripto **atinge o pico em torno de 10-15 moedas**; além disso, custos superam o benefício de diversificação. **Estamos em 24 pares.** https://www.man.com/insights/in-crypto-we-trend

### 2.9 Ranking do tema 1

| # | Estratégia | Evidência | Sharpe líquido reportado | Horizonte que sobrevive ao custo | Status |
|---|---|---|---|---|---|
| 1 | Carry / funding delta-neutro | PEER-REVIEWED + preprint dos autores | 6,45 (2020-25) → 4,06 (2024) → **negativo (2025)** | dias-semanas | **decaiu; possivelmente morto** |
| 2 | Basis como fator cross-sectional em perps | PEER-REVIEWED (JFM 2024) | 48 de 134 preditores, todos explicados por basis + preço-volume | dias | vivo, é o fator dominante |
| 3 | TS-momentum diário/semanal com escala de vol | PEER-REVIEWED, contestado | 1,12 → 1,42; mediana 1,34 (CTREND) | semanas | vivo mas encolhendo |
| 4 | Momentum intradiário BTC (1ª meia-h → última) | PEER-REVIEWED | 0,53 simples; 1,15 combinado | horas, 1×/dia | vivo; mecanismo = provisão de liquidez |
| 5 | Sazonalidade horária (22:00 UTC) | BACKTEST DE PRATICANTE | 1,58 (custos não declarados) | horas, 1×/dia | frágil, não auditado |
| 6 | Order flow imbalance | PEER-REVIEWED + preprint | IR 0,25 em BTC; 8,97 em ilíquidas (irrealista) | **segundos** | real, exige infra |
| 7 | Efeito quarto-de-hora | PREPRINT de alto nível | ~0,5 bp/fronteira vs 5 bp taker | **nenhum** | insumo de execução |
| 8 | Momentum cross-sectional | PEER-REVIEWED, três papers contra | fragmentado, dependente da amostra | semanas | duvidoso |
| 9 | Cascatas de liquidação | PREPRINT | sinais não-específicos | — | **sem previsibilidade demonstrada** |
| 10 | Breakout Donchian/Turtle em cripto | só blog | n=25 trades | — | **folclore** |
| 11 | Funding extremo como contrarian | marketing | nenhum | — | **folclore** |
| 12 | **Confluência EMA/RSI/ADX/MACD** | PEER-REVIEWED contra, 25 anos | zero após snooping + custo | — | **refutado** |

---

## 3. TEMA 2 — Order book, fluxo e posicionamento

**Veredito antecipado:** a literatura de microestrutura é sólida, mas quase toda ela vive entre **1 segundo e 2 minutos**. Este bot segura posição por **horas**. Essa incompatibilidade de horizonte, somada a 5 bps de taxa taker, é o motivo estrutural de o portão de fluxo medir p=0,58 — e é por isso que **trocar o portão por um OFI "melhor" não resolve nada** se o horizonte de saída continuar o mesmo.

### 3.1 Order Flow Imbalance: o que o paper original realmente diz

**Cont, Kukanov & Stoikov**, *The Price Impact of Order Book Events*, arXiv 2010 → **Journal of Financial Econometrics** 12(1):47-88, 2014 `[PEER-REVIEWED]` — https://arxiv.org/pdf/1011.6402 · https://academic.oup.com/jfec/article-abstract/12/1/47/816163

Números exatos: 50 ações do S&P 500, TAQ, abril/2010, 21 pregões, **Δt = 10 segundos**.
- **R² médio do OFI = 65%. R² médio do trade imbalance (TI) = 32%.**
- Com as duas variáveis juntas, **o TI fica estatisticamente insignificante em 69% das subamostras.**
- β_i = c/AD_i^λ com λ≈1: **o impacto é inversamente proporcional à profundidade.**

⚠️ **A armadilha que precisa ficar registrada: esses 65% são CONTEMPORÂNEOS, não preditivos.** É uma regressão do ΔP do mesmo intervalo contra o OFI do mesmo intervalo — uma equação de formação de preço, não um sinal.

**A prova disso, em cripto.** Dean Markwick replicou o OFI em **BTCUSD da Coinbase, buckets de 1 segundo** `[BACKTEST DE PRATICANTE]` — https://dm13450.github.io/2022/02/02/Order-Flow-Imbalance.html (2022):
- Versão com vazamento de futuro: R² **0,397 IS / 0,410 OOS**.
- Versão corrigida (**preditiva**): R² **0,034 IS / 0,030 OOS**.
- **Sharpe 0,12. Acurácia direcional 53%.** Conclusão do autor: *"trading costs will eat you alive"*.

**R² 65% contemporâneo → R² 3% preditivo → Sharpe 0,12.** É a demonstração mais limpa que a pesquisa achou.

**Extensão multi-nível:** Xu, Gould & Howison, *Multi-Level Order-Flow Imbalance*, arXiv 1907.06230 `[PEER-REVIEWED]` — incluir L1-L10 reduz o RMSE em **65-75% para ações de tick grande e 15-30% para tick pequeno** frente ao OFI de L1 só. Ganho real, mas continua no regime de segundos. https://arxiv.org/abs/1907.06230

### 3.2 Book imbalance L1-L5 e microprice

**Stoikov**, *The Micro-Price*, SSRN 2970694, 2017/2018 → **Quantitative Finance** `[PEER-REVIEWED]` — melhor preditor de curto prazo que mid e weighted-mid; horizontes de avaliação começam em **100 ms**. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2970694

**Em cripto, com números** `[BACKTEST DE PRATICANTE]` — ETH-USD Coinbase, mai a dez/2019, **1.920.617 observações a cada 10 s, L1 a L5** — https://towardsdatascience.com/price-impact-of-order-book-imbalance-in-cryptocurrency-markets-bf39695246f6/
- Correlações com retorno subsequente **fracas**; L5 só marginalmente melhor que L1.
- Poder preditivo **máximo em 10 segundos** e *"quickly deteriorate with the time horizon"*.
- **Retorno esperado abaixo de 10 bps** nos períodos de 10 s.
- Conclusão: com taxa da ordem de 10 bps e dois trades, *"order imbalances do not directly imply a profitable strategy on its own"*.

Consenso convergente: o imbalance tem poder preditivo sobre **as duas próximas mudanças de mid-price**, com melhor acurácia em **3 a 10 segundos**, e depois cai para perto de zero.

### 3.3 CVD / taker buy-sell ratio em 5m-1h: o buraco que interessa

**Não existe evidência acadêmica de que CVD tenha poder preditivo.** A busca específica retornou exclusivamente conteúdo de plataforma e blog (Bookmap, LuxAlgo, Phemex, Gate, CryptoQuant). **Nenhum paper.** E o material honesto dentro do próprio marketing diz o mesmo: CVD *"does not predict — it describes"*; *"reactive, not predictive"* `[MARKETING]`. https://markettrace.ai/blog/cumulative-volume-delta

**O que existe de sério em horizonte de minutos** — o paper do *Frontiers in Blockchain* (2026) já citado em §1.1, com o detalhe metodológico completo:
- LightGBM sobre essas features: **R² in-sample 35,9%, out-of-sample −10,94%** (overfitting catastrófico), Diebold-Mariano −6,83 (pior que random walk).
- Modelo linear hierárquico: melhora de R² de ~1,23%.
- **Sharpe líquido: −52,05 a −31,29 no spot; −18,42 a −10,68 nos futuros.** Turnover diário de 124-204× o notional.

**A única evidência decente em horizonte lento** é a de Kim & Hansen (§2.5): imbalance de fluxo na abertura do quarto-de-hora prevê 4-12h, mas vale **0,5 bp = 1/20 de round-trip**.

**Horizonte diário/semanal:** *Order Flow and Cryptocurrency Returns* (Anastasopoulos & Gradojevic), **JIFMIM**, 2026 `[PEER-REVIEWED]` — 1 dp de "world order flow" ⇒ **+0,2% no retorno diário e +0,9% no semanal**. ⚠️ *Não foi possível abrir o texto completo (403 no ScienceDirect); números vindos de resumos indexados — não verificados no original.* https://www.sciencedirect.com/science/article/pii/S1386418126000029

**VPIN:** *Bitcoin wild moves: Evidence from order flow toxicity and price jumps*, **RIBAF**, 2026 `[PEER-REVIEWED]` — VPIN prevê significativamente **saltos de preço** futuros, **não direção**. Candidato a filtro de risco, não a portão direcional. ⚠️ *Effect size não extraído (paywall).* https://www.sciencedirect.com/science/article/pii/S0275531925004192

### 3.4 Open interest + preço: os "4 quadrantes" são folclore

**Nenhuma evidência acadêmica para os 4 quadrantes em cripto.** Todas as fontes que descrevem "preço sobe + OI sobe = força" são material educacional de corretora e cursos (5paisa, commodity.com, TradingView, Gate). **Nenhuma traz backtest, tamanho de efeito ou teste de significância** `[ANEDOTA]`.

O que existe de sério é **de outro horizonte e de outro mercado**: Hong & Yogo (2011/2012) `[PEER-REVIEWED]` — a **variação de 12 meses** do OI prevê retornos; 1 dp em futuros de commodities ⇒ **+0,63%/mês**; em moedas ⇒ +0,35%/mês. Horizonte **mensal/anual**, mercados tradicionais. Não tem relação com um portão de OI de 1 hora em altcoin. https://www.cxoadvisory.com/commodity-futures/futures-market-open-interest-as-return-predictor/

E há refutação direta: o paper de cascatas (arXiv 2607.27070) testou OI como early-warning em 7 eventos e **não achou poder preditivo consistente**.

**Isso é coerente com o [CX-2] interno (o portão de OI piorou os quatro níveis). O overfitting demonstrado foi o resultado esperado pela literatura, não azar.**

### 3.5 Long/short ratio de top traders: nenhum estudo mede o poder preditivo

**A busca específica não achou nenhum estudo, acadêmico ou de praticante.** O que achou:
1. **A definição já mata metade do apelo:** o "top trader" da Binance é o **top 20% por saldo de margem**, explicitamente *"not necessarily the best traders or those with the highest profits"* `[DOCUMENTAÇÃO OFICIAL]`. https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Top-Long-Short-Account-Ratio
2. **O ratio de contas não é o ratio de dinheiro** — o mercado pode ter mais contas long enquanto o size grande está do outro lado. https://www.walletfinder.ai/blog/long-short-ratio
3. A própria divulgação admite empate: *"There is no conclusion on whether the Long-Short Ratio is a contrarian indicator."* `[ANEDOTA]`
4. **Teste negativo indireto e sério:** o paper de cascatas incluiu `topLongShortAccountRatio`, `globalLongShortAccountRatio` **e** `takerBuySellVolumeRatio` no conjunto de early-warning e **nenhum previu evento algum de forma consistente**.

**A evidência peer-reviewed de posicionamento que existe é de outro instrumento e outra frequência:** *Predictability of crypto returns: The impact of trading behavior*, **JBEF**, 2023 `[PEER-REVIEWED]` — usando o **COT semanal da CFTC** para futuros de BTC na CME: 1 dp na variação do posicionamento líquido de especulativos de varejo ⇒ **+0,62% (BTC), +0,93% (ETH), +1,05% (XRP) no retorno semanal**. https://www.sciencedirect.com/science/article/abs/pii/S2214635023000266

**Semanal, CME, dado regulado e auditado. Não é o ratio de contas da Binance a cada 5 minutos. Não transponha.**

### 3.6 Liquidation heatmaps e o stream `forceOrder`

**O heatmap é marketing.** O próprio disclaimer da Coinglass diz ser *"a prediction based algorithm and is not true or accurate data"*. Exchanges **não publicam stops, alavancagem por conta nem zonas de liquidação** — o heatmap é uma **simulação** sob um modelo de alavancagem assumido `[MARKETING]`. https://www.coinglass.com/learn/how-to-use-liqmap-to-assist-trading-en

**O `forceOrder` é incompleto por design.** Doc oficial: *"For each symbol, only the largest one liquidation order within 1000ms will be pushed as the snapshot."* Máximo **1 push por segundo por símbolo** `[DOCUMENTAÇÃO OFICIAL]`. https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams

**Consequência quase nunca mencionada: não dá para somar volume de liquidação a partir desse stream.** Durante uma cascata — exatamente quando o dado importaria — chega uma ordem por segundo e o resto some. Qualquer "volume de liquidações" calculado do `forceOrder` está sistematicamente subestimado, **com viés máximo nos eventos extremos**.

### 3.7 REST a cada 15 s vs. websocket

**Exige websocket obrigatoriamente:**

| Sinal | Por quê |
|---|---|
| OFI de Cont et al. | Precisa de **eventos** do book. Um snapshot a 15 s não distingue "cancelaram 10 BTC" de "executaram 10 BTC". Impossível reconstruir. |
| MLOFI (L1-L10) | Idem, em 10 níveis. |
| Microprice | Precisa de L1 com timestamp de evento (`<symbol>@bookTicker`). |
| Book imbalance L1-L5 usável | Amostrável por REST, mas o sinal tem meia-vida de segundos: tecnicamente possível, economicamente inútil. |

**NÃO exige websocket:**

| Sinal | Fonte |
|---|---|
| **Taker imbalance em 5m/15m/1h** | Já vem no kline: `Taker buy base asset volume` e `Taker buy quote asset volume` na resposta de `/fapi/v1/klines`. https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data |
| OI, funding, long/short ratio | REST, granularidade mínima 5 min (e dump histórico — §4.1). |
| Liquidações | Só existe em WS, e é incompleto. |

**Limites da Binance USDT-M** `[DOCUMENTAÇÃO OFICIAL]` — https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams
- `<symbol>@bookTicker` real-time; `<symbol>@depth@100ms|500ms`; `<symbol>@depth{5|10|20}@{100ms|250ms|500ms}`.
- **Máximo 1024 streams por conexão**; **10 mensagens de entrada/segundo** em futuros.
- **Mudança anunciada:** a partir de 2025-11-26 07:00 UTC, `@depth` e `@depth20` passam a **50 ms** — o dobro do volume de mensagens.
- Book local: snapshot REST + validação de sequência (`U`, `u`, `pu`); se `pu ≠ u` anterior, **descartar e reinicializar**.
- REST em futuros: **REQUEST_WEIGHT 2400/min por IP**; HTTP 429; bans de 2 min a 3 dias.

**🔴 CORREÇÃO IMPORTANTE: `ccxt.pro` é GRÁTIS desde outubro de 2022.** Foi fundido no pacote principal `ccxt` na **v1.95+**, licença **MIT**. Anúncio oficial: *"CCXT Pro is now a part of the free CCXT package as of version 1.95+"* e *"A word to existing CCXT Pro users: please, ignore the subscription expiry notifications and switch to CCXT."* — https://github.com/ccxt/ccxt/issues/15171 (03/out/2022)

⚠️ Sites de comparação de software (SourceForge, SoftwareSuggest, SaaSCounter) **continuam anunciando "CCXT Pro a partir de US$ 29/mês" — está desatualizado e errado.** Se alguém no projeto disse que a migração para WS custa assinatura, está enganado. **Custo de licença: zero.**

Alternativas: `binance-futures-connector-python` (oficial), `python-binance`, `websockets` puro.

### 3.8 Post-only: seleção adversa — o resultado que mais mexe com o desenho atual

**Albers, Cucuringu, Howison & Shestopaloff**, *The Market Maker's Dilemma: Navigating the Fill Probability vs. Post-Fill Returns Trade-Off*, arXiv 2502.18625 (fev/2025, rev. nov/2025) `[PREPRINT, mas com experimento de trading AO VIVO no perp de BTC da Binance]` — https://arxiv.org/abs/2502.18625

Abstract, na parte que importa:
> *"We document a fundamental trade-off: a negative correlation between maker fill likelihood and post-fill returns. This dictates that **viable maker strategies often require a contrarian approach, counter-trading the prevailing order book imbalance**. These dynamics render **commonly-cited strategies highly unprofitable**."*

Determinantes da probabilidade de fill: (1) fila do lado próximo pequena ⇒ fill mais provável; (2) fila do lado oposto grande ⇒ preço tem menos chance de andar contra, aumentando o tempo de residência e a chance de um taker grande chegar.

**A implicação direta para este bot:** ele posta post-only **na direção do sinal** — comprando quando o momentum é comprador. Isso é precisamente a configuração que o paper chama de *"commonly-cited strategy highly unprofitable"*: **você só é preenchido quando o mercado está prestes a ir contra você.** O viés dos fills é adverso por construção. O post-only cortou taxa (Sharpe 0,955 → 1,134, como medido internamente) mas **trocou custo explícito por seleção adversa implícita** — e por isso não bastou para passar.

### 3.9 Por que o nosso portão mediu p=0,58 — cinco causas concretas

1. **É trade imbalance, e o TI é a variável dominada.** Cont et al.: o TI vira insignificante em **69% das subamostras** quando o OFI entra na mesma regressão. Estamos usando a versão fraca do sinal.
2. **É binário num limiar de 50%, que é a mediana.** Joga fora toda a magnitude — a diferença entre 51% e 85% é a informação inteira — e ainda descarta 38,9% dos sinais com base num flag sem poder.
3. **200 trades é janela de EVENTO, não de tempo.** Em BTCUSDT pode ser 2 segundos; numa altcoin da cesta pode ser 10 minutos. **Estamos comparando 24 pares em 24 janelas temporais diferentes e desconhecidas.** Isso sozinho injeta ruído suficiente para produzir p=0,58.
4. **Não é normalizado por profundidade nem por volatilidade.** Cont et al.: β ∝ 1/profundidade. Sem normalizar, o mesmo valor de imbalance significa coisas diferentes em cada par.
5. **O horizonte não bate — e essa é a falha de raiz.** Trade imbalance tem meia-vida de **segundos**; o bot segura por **horas**. O quarter-hour paper mostra que o efeito de imbalance é **negativo na primeira meia hora** antes de virar positivo: **o sinal literalmente inverte de sinal dentro do horizonte de holding.**

---

## 4. TEMA 3 — Risco, sizing e carteira

### 4.1 Risco correlacionado: a matemática

σ_p = √( Σσᵢ² + 2·Σ_{i<j} ρ·σᵢσⱼ ). Com n=5 posições iguais de σ=3% e ρ uniforme: **σ_p = 3% · √(5 + 20ρ)**

| ρ | σ_p | soma nominal | N_eff = n/(1+(n−1)ρ) |
|---|---|---|---|
| 0,00 | **6,71%** | 15% | 5,00 |
| 0,30 | **9,95%** | 15% | 2,27 |
| 0,60 | **12,37%** | 15% | 1,47 |
| **0,85** | **14,07%** | 15% | **1,14** |
| 1,00 | 15,00% | 15% | 1,00 |

**Leitura honesta:** em desvio-padrão, ρ=0,85 dá 14,07%, *menos* que a soma nominal de 15%. Quem disser "é mais que 15%" está errado na variância. O problema real é outro e é pior: **N_eff = 1,14 — cinco posições a ρ=0,85 são uma aposta e um oitavo.** Toda a diversificação que justifica o teto agregado de 10% não existe.

**A cauda, que é o que mata.** Modelo de 1 fator gaussiano com taxa marginal de perda de 61,3% (= 1 − WR de 38,7%):

| ρ | P(as 5 perderem juntas) → −15% da banca |
|---|---|
| 0,00 | 8,66% |
| 0,60 | 30,70% |
| **0,85** | **43,27%** |

**A cada cluster de 5 posições abertas, 43% de chance de as cinco irem ao stop juntas.** A trava diária de −5% é *reativa* — checada depois que as posições já existem.

**Os ρ reais em cripto (2024-2026):**
- `[PEER-REVIEWED]` 10 maiores criptos, 2017-2022: ETH, BNB, LTC contra BTC entre **0,70 e 0,90**; BTC-ETH ≈ 0,9. https://finst.com/en/learn/articles/price-correlation-between-bitcoin-and-altcoins
- `[DADO DE PROVEDOR]` DefiLlama, dez/2025: BTC-ETH **0,89**, BTC-SOL **0,99** (máximas históricas). https://cryptopotato.com/defillama-crypto-correlations-hit-record-highs-as-btc-sol-reaches-0-99/
- `[PESQUISA INSTITUCIONAL]` Coinbase Institutional, ago/2024: beta de 90 dias — ETH 0,85, SOL 0,83. https://www.coinbase.com/institutional/research-insights/research/monthly-outlook/monthly-outlook-august-2024
- `[PEER-REVIEWED]` *Cryptocurrency systematic risk dynamics*, **Economics Letters**, 2024: beta sistemático subiu de 0,032 → **0,834** (BTC) e 0,087 → **1,003** (ETH), *"reduzindo drasticamente o benefício de diversificação"*. https://www.sciencedirect.com/science/article/pii/S0165176524002726

**Use ρ = 0,85 como cenário de trabalho e ρ = 0,95 como estresse.**

### 4.2 Kelly: o 3% por trade é defensável; o 5× não é

f* = (p·b − q)/b. Com os números medidos (WR 38,7%, PF 1,15 ⇒ b = 1,15·0,613/0,387 = **1,821**): expectancy **0,0917R**, **f\* = 5,04%**. Meio-Kelly 2,52%, quarto-Kelly 1,26%.

**3% por trade ≈ 0,60× Kelly** — defensável em isolado. **O problema não é o 3%. É o 5×.** 14,07% / 5,04% = **2,79× Kelly**.

Crescimento log g(f) = f·μ − f²σ²/2, zero em f = 2f*. **Acima de 2× Kelly o crescimento de longo prazo é negativo mesmo com edge real.** MacLean, Thorp & Ziemba, *Good and Bad Properties of the Kelly Criterion* `[LIVRO/PEER-REVIEWED]` — *"quick bankruptcy for the aggressive overbet strategies"*. https://webhomes.maths.ed.ac.uk/mckinnon/blackouts/StochOptFinanceAndEnergySpringer/Chap1_KellyZiemba.pdf

**E se o edge estiver errado (o caso mais provável):** o p que zera a expectancy com b=1,821 é **35,46%**. Medimos 38,7% — **3,2 pontos percentuais de folga**, dentro do ruído amostral de algumas centenas de trades. E o achado central diz que o edge verdadeiro é ≤ 0. A tabela de drag de variância com edge zero está na §1.4.

**Optimal f (Vince)** `[LIVRO/PRÁTICA]` — **inaplicável aqui**: calibra sobre um histórico que já provamos não ter edge, não impõe teto de drawdown e é hipersensível ao melhor/pior trade. Daria f alto exatamente porque o dia 21/08 (323% do lucro) está na amostra. https://www.turtletrader.com/optimal-f/

**"Regra de 1-2%":** `[PRÁTICA CONSAGRADA, sem base acadêmica]` — não há literatura peer-reviewed que valide o 1% como número. O que existe é racionalização retroativa de que 1% ≈ quarto-Kelly para edges finos. Acidentalmente correto, mas é heurística, não resultado.

### 4.3 Vol targeting: boa evidência, e um contraponto que precisa ser lido

**A favor:**
- Moskowitz, Ooi & Pedersen, *Time Series Momentum*, **JFE** 104(2), 2012 `[PEER-REVIEWED]` — posições dimensionadas por 1/vol ex-ante. https://www.sciencedirect.com/science/article/pii/S0304405X11002613
- Barroso & Santa-Clara, *Momentum has its moments*, **JFE** 116(1), 2015 `[PEER-REVIEWED]` — escalar pelo inverso da variância realizada leva o **Sharpe de 0,53 → 0,97** e elimina os crashes. https://www.sciencedirect.com/science/article/abs/pii/S0304405X14002566
- Harvey, Hoyle, Korgaonkar, Rattray, Sargaison & Van Hemert, *The Impact of Volatility Targeting*, **JPM** 45(1), 2018 `[PEER-REVIEWED]` — 60+ ativos desde 1926, **meia-vida de 20 dias**. Sharpe melhora em ativos de risco (leverage effect), desprezível em bonds/moedas/commodities. Reduz max DD e a "vol da vol" anual cai de 4,6% para 1,8%. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3175538
- Em cripto: *Cryptocurrency Market Risk-Managed Momentum Strategies*, **FRL**, 2025 — **Sharpe 1,12 → 1,42**; e *Liquidity Shocks, Price Volatilities, and Risk-managed Strategy*, **JIFMIM**, 2022 — **Sharpe 0,72 → 1,21** e assimetria de −1,0 → +0,41 contra buy-and-hold de BTC. https://www.sciencedirect.com/science/article/abs/pii/S1042444X22000019

**🔴 O CONTRAPONTO OBRIGATÓRIO.** Kim, Tse & Wald, *Time series momentum and volatility scaling*, **Journal of Financial Markets**, 2016 `[PEER-REVIEWED]`: **os alfas do TSMOM são em grande parte dirigidos pelo vol scaling; sem ele o TSMOM não é melhor que buy-and-hold.** https://www.sciencedirect.com/science/article/abs/pii/S1386418116301379

**Faca de dois gumes: vol targeting pode GERAR performance aparente sem que o sinal tenha edge. Se ligarmos vol targeting e o Sharpe melhorar, isso NÃO é evidência de que a entrada melhorou.**

**O gap no bot.** Com nocional por posição = risco/stop = 3%/3% = **1,0× a banca**, cinco posições dão **gross 500% da banca**. Com vol anualizada de altcoin ≈ 90% e ρ=0,85:

σ_carteira = 1,00 × 0,90 × √(5 + 20·0,85) ≈ **422% ao ano**

Mesmo com stop de 5% (nocional 60% cada, gross 300%): **~253% ao ano**. Comparação: um CTA de trend targeta **10-20%** de vol anualizada. https://thehedgefundjournal.com/managed-futures-d1/

Para chegar a alvos sãos, mesmo ρ e mesma vol de ativo:

| alvo de vol da carteira | nocional por posição | gross |
|---|---|---|
| 40% a.a. | **9,5% da banca** | 47% |
| 25% a.a. | **5,9% da banca** | 30% |

**É uma redução de ~10× sobre o que rodamos hoje.** ⚠️ Precisa ser confirmado medindo o gross notional real e a vol realizada da curva — pode ser que os stops de 3×ATR estejam mais largos que 3% na prática e o gross seja 2-3× em vez de 5×. Mas nem 2× é aceitável para vol de altcoin.

### 4.4 Alavancagem e funding

**Alavancagem.** Sistemáticos profissionais **não pensam em "alavancagem"** — pensam em alvo de volatilidade e deixam a alavancagem cair de lá `[PRÁTICA CONSAGRADA]`.

**A alavancagem proporcional à convicção (2x-20x) tem um problema estrutural: o score de convicção foi medido com retorno direcional NEGATIVO em 2.596 sinais. Estamos alocando mais alavancagem onde a medição diz que o sinal é pior.** Enquanto o score não for revalidado, a alavancagem deve ser **constante**.

**Funding.** Baseline: 0,01% a cada 8h = 0,03%/dia = **10,95% ao ano** `[DOC OFICIAL]`. https://www.binance.com/en/support/faq/detail/360033525031

Médias efetivas medidas (Deribit, FRNT Financial, 2026) `[DADO DE PROVEDOR]`: **BTC perp 10,24% a.a. em 2024 e 5,38% em 2025**; picos de 71,73% (mar/2024) e 61,49% (jan/2025). ETH perp 8,20% (2024) e 0,85% (2025). Em 2021 chegou a 190,25% (BTC). https://frnt.substack.com/p/comparing-risk-and-leverage-dynamics

Custo por ano, sempre comprado, em % da banca:

| gross | baseline 10,95% | média BTC 2024 | média BTC 2025 |
|---|---|---|---|
| **5,0×** | **54,8%** | 51,2% | 26,9% |
| 3,0× | 32,9% | 30,7% | 16,1% |
| 1,0× | 10,9% | 10,2% | 5,4% |

**Com gross 5×, o funding sozinho come 27-55% da banca por ano se ficarmos preponderantemente comprados.** A expectancy medida é 0,0917R ≈ 0,275% da banca por trade — são ~100-200 trades vencedores por ano só para pagar o funding. **Isso tem que estar no P&L do paper trading; se não estiver, o resultado ao vivo está inflado.**

### 4.5 Liquidação × stop: a assimetria

**Distância até a liquidação ≈ 1/L − MMR − taxa taker.** MMR do primeiro tier de BTCUSDT = **0,4%**; alts costumam começar em ~1% `[DOC OFICIAL]`. https://developers.binance.com/docs/derivatives/usds-margined-futures/account/rest-api/Notional-and-Leverage-Brackets

| L | dist. liq. (MMR 0,4%) | dist. liq. (MMR 1,0%) |
|---|---|---|
| 5x | 19,56% | 18,96% |
| 10x | 9,56% | 8,96% |
| **20x** | **4,56%** | **3,96%** |

**3×ATR em números** (vol anualizada 90%, ATR ≈ 1,2σ da barra): 5m → **1,00%**; 15m → **1,73%**; 1h → **3,46%**.

**Cruzamento** (L acima do qual a liquidação fica mais perto que o stop): 15m/stop 1,46%/MMR 1% → **40,0x**; 1h/stop 2,92% → **25,3x**; **1h em alt volátil/stop 4,5% → 18,1x**.

**A 20x, num sinal de 1h numa altcoin volátil, a liquidação já está dentro ou colada no stop.** E são justamente as configurações de maior convicção — as que a medição diz que não funcionam.

**Quatro assimetrias que tornam a liquidação pior:**
1. **Perda maior.** A 20x com taxa de clearance de 0,5%: **5,06% da banca contra 3,00% no stop = 1,69×**. A 10x seria 3,35× e a 5x, 6,69× — porque a alavancagem baixa faz o stop disparar *antes*, que é o desenho correto.
2. **É ordem a mercado, na hora errada** — taker num livro fino, em cascata.
3. **🔴 Interação com post-only — o risco específico deste bot.** Se a saída de stop for enviada como maker (post-only), num movimento rápido ela **não preenche**; o preço atravessa o stop e vai para a liquidação. **Post-only na entrada é economia de fee; post-only na saída de emergência é uma bomba. Verificar no código.**
4. **Perda de opcionalidade** — sai no pior ponto e não participa da reversão.

**Aritmética do buraco** (RG = 1/(1−DD) − 1): DD 20% → +25%; **DD 32,9% (o nosso, do pico) → +49,0%**; DD 50% → +100%; DD 80% → +400%.

### 4.6 Circuit breakers e equity curve trading

**Equity curve trading: a evidência é ruim. Diga-se isso.**
- Kisela et al., *Trading the Equity Curves*, **Procedia Economics and Finance** 32, 2015 `[PEER-REVIEWED, proceedings]` — indicadores técnicos sobre a curva de capital de uma estratégia real: **melhora em apenas 22 de 80 casos — e só nos casos em que a curva bruta já era negativa.** https://www.sciencedirect.com/science/article/pii/S2212567115013635
- KJ Trading Systems `[BACKTEST DE PRATICANTE]` — 3 estratégias reais, 450 trades cada, dois métodos: ouro **quase sempre pior**; iene **sempre pior**; ES misto e dependente de parâmetro. *"É relativamente fácil pegar uma boa estratégia e degradá-la significativamente com equity curve trading."* https://kjtradingsystems.com/equity-curve-trading.html
- Alvarez Quant Trading chega à mesma leitura, e nota que **não é recomendável para trend following** porque desligar faz perder a entrada que carrega o ano. https://alvarezquanttrading.com/blog/trading-the-equity-curve/

**Argumento teórico:** se os retornos por trade forem i.i.d., filtrar pelo passado da curva tem efeito zero sobre a média e reduz a exposição — **corta retorno sem cortar risco proporcional**. Só funciona se houver autocorrelação genuína dos retornos da *estratégia*. Não medimos isso.

**Distinção que salva o conceito:** *equity curve trading como filtro de alfa* → sem evidência, não fazer. *De-risking por drawdown como restrição de sobrevivência* → outra coisa, e é defensável — não porque melhora o Sharpe, mas porque limita a perda máxima. **Declarar qual dos dois se está fazendo.**

**Circuit breakers dia/semana/mês:** `[PRÁTICA CONSAGRADA, sem literatura acadêmica]` — a busca **não achou pesquisa peer-reviewed sobre eficácia de limites diários de perda em sistemas automatizados**. O que existe é a prática de prop firms (limite diário 2-5%), e a razão declarada é **limitação de responsabilidade do capital do firm**, não melhora de retorno esperado. **Trate igual: circuit breaker é seguro, não alfa.**

**A falha do desenho atual:** a trava de −5%/dia é reativa e o risco agregado (5 × 3% correlacionados) permite −15% num único movimento. **O circuit breaker precisa ser ex-ante:** teto de risco agregado *ajustado por correlação*, checado antes de abrir cada posição.

### 4.7 Medir a carteira: quanto tempo leva para saber se há edge

**Lo, *The Statistics of Sharpe Ratios*, Financial Analysts Journal, jul/ago 2002, pp. 36-52** `[PEER-REVIEWED]` — sob retornos i.i.d.: **SE(ŜR) = √( (1 + ŜR²/2) / T )**. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=377260

Anualizando com dados diários e Y anos: SE(SR_a) ≈ √( (1 + SR_a²/504)/Y ) ≈ 1/√Y. Rejeitar SR=0 exige SR_a·√Y > z:

| Sharpe verdadeiro | 95% bicaudal | 95% unicaudal |
|---|---|---|
| **1,0** | **3,85 anos** (1.405 dias) | 2,71 anos |
| **0,5** | **15,37 anos** (5.612 dias) | 10,83 anos |
| 1,5 | 1,72 anos | 1,21 anos |
| 2,0 | 0,97 ano | 0,68 ano |

E o outro lado, o nosso:

| janela | SE do Sharpe anualizado | IC95 |
|---|---|---|
| **10 dias ao vivo** | **6,05** | **±11,85** |
| 1 mês | 3,49 | ±6,84 |
| 3 meses | 2,00 | ±3,92 |
| 1 ano | 1,00 | ±1,96 |

**Os 10 dias ao vivo produzem um Sharpe com intervalo de confiança de ±11,9. Não é um resultado fraco — é literalmente zero informação.** O "+11,6%" e o "−32,9% do pico" são ambos ruído puro do ponto de vista inferencial. E isso *antes* de deflacionar por múltiplos testes.

**O painel de carteira (não de trade):**

| métrica | frequência | uso |
|---|---|---|
| Vol realizada anualizada (EWMA meia-vida 20d) | diária | insumo do vol targeting |
| Gross notional / patrimônio e exposição líquida | contínua, **pré-trade** | teto duro |
| Correlação média par-a-par das posições abertas | **pré-trade** | teto de risco ajustado por ρ |
| Beta ao BTC da curva de capital | semanal | mede se temos estratégia ou long de BTC alavancado |
| Max DD e DD corrente do pico | contínua | circuit breaker |
| Sharpe **+ SE(Sharpe) e IC** | mensal | **nunca reportar Sharpe sem a barra de erro** |
| Sortino, Calmar | mensal | assimetria e retorno por unidade de DD |
| Custo de funding acumulado e slippage | diária | é o vazamento estrutural |
| **Contribuição de retorno do melhor dia** | mensal | 21/08 = 323% do lucro. Se um dia domina, não temos estratégia, temos um bilhete |

---

## 5. TEMA 4 — Dados e método de validação

### 5.1 `data.binance.vision` — inventário verificado por download

`[VERIFICAÇÃO DIRETA — enumerado via API S3 e com arquivos baixados e abertos]`

| Dataset | Caminho | Início (BTCUSDT) | Início (alts) | Granularidade | Tamanho/dia | Estado |
|---|---|---|---|---|---|---|
| **metrics** | `daily/metrics/{SYM}/` | **2020-09-01** | **2021-12-01** | **5 min, 288 linhas/dia** | ~12 KB | **ATIVO, D-1** |
| klines | `daily/klines/{SYM}/{intv}/` | 2019-12-31 | varia | 1m…1mo (16 intervalos) | 14 KB (5m) | ATIVO, D-1 |
| aggTrades | `daily/aggTrades/{SYM}/` | 2019-12-31 | — | tick agregado | **33 MB** | ATIVO |
| trades | `daily/trades/{SYM}/` | **2019-09-08** | — | tick | grande | ATIVO |
| bookDepth | `daily/bookDepth/{SYM}/` | **2023-01-01** | 2023-01-01 | **snapshot 30 s, 12 níveis** | 566 KB | ATIVO (961 símbolos) |
| bookTicker | `daily/bookTicker/{SYM}/` | 2023-05-16 | — | tick de topo | 50-90 MB | ⚠️ **MORTO — último arquivo 2024-03-30** |
| indexPriceKlines | `daily/…` | 2019-12-23 | — | 16 intervalos | trivial | ATIVO |
| markPriceKlines | `daily/…` | 2019-12-23 | — | 16 intervalos | trivial | ATIVO |
| premiumIndexKlines | `daily/…` | 2019-12-24 | — | 16 intervalos | trivial | ATIVO |
| **fundingRate** | **`monthly/` apenas** | **2020-01** | — | 8h | trivial | ATIVO |
| liquidationSnapshot | — | — | — | — | — | ❌ **NÃO EXISTE para USDT-M**. Só `cm`, e lá morreu em 2024-10-14 |

**URL do metrics:** `https://data.binance.vision/data/futures/um/daily/metrics/{SYMBOL}/{SYMBOL}-metrics-YYYY-MM-DD.zip` (+ `.CHECKSUM` sha256 ao lado). Sem chave, sem rate limit publicado.

**Cinco armadilhas que só aparecem abrindo os arquivos:**
1. **As linhas do `metrics` NÃO estão em ordem cronológica.** No arquivo de 2026-08-20, **246 das 288 linhas estão fora de ordem**. Ordene por `create_time` no ingest ou produz features com look-ahead invertido.
2. **Duplicatas no primeiro dia.** `BTCUSDT-metrics-2020-09-01` tem 576 linhas = cada timestamp duas vezes. `drop_duplicates()` sempre.
3. **O header dos klines é INCONSISTENTE.** 2020-03 e 2021-07: sem header. 2022-01 e 2022-04: com. 2022-06/07/08: **sem**. 2022-09 em diante: com. **Fareje a primeira linha, nunca assuma.**
4. **`metrics` só existe em `daily`** — não há agregação mensal; são ~1.731 requisições por símbolo.
5. **Há nomes corrompidos no bucket** (`MATICUSDT-metrics-1993.zip`). Valide o parse da data.

**Custo real medido:** 20 arquivos em paralelo em **2 segundos**. **24 pares × 1.731 dias = 41.544 arquivos ≈ 487 MB, ~70 minutos com 20 conexões.**

**Bônus:** `data/option/daily/BVOLIndex/{BTCBVOLUSDT,ETHBVOLUSDT}` — índice de volatilidade implícita, grátis, útil como variável de regime.

### 5.2 Provedores pagos: a tabela que economiza dinheiro

| Provedor | Free | Preço que serve | Histórico 5m de OI que esse preço libera | Fonte |
|---|---|---|---|---|
| **data.binance.vision** | tudo | **US$ 0** | **5m desde 2020-09** | verificado |
| Coinglass Hobbyist | não | US$ 29/mês | **nenhum** (só ≥4h) | https://www.coinglass.com/pricing |
| **Coinglass Standard** | — | **US$ 299/mês** | **30 dias** | tabela oficial de tiers |
| Coinglass Professional | — | US$ 699/mês | 60 dias | idem |
| Tardis.dev Perpetuals | amostras do 1º dia de cada mês | **US$ 700/mês** | OI a cada ~6 s desde 2020-05-13 | https://docs.tardis.dev/historical-data-details/binance-futures |
| Velo Data | app web | US$ 199/mês | mensal = 3 meses | https://docs.velo.xyz/ |
| CryptoQuant Pro | limitado | US$ 99/mês | **API só 24h de resolução** | https://cryptoquant.com/pricing |
| Glassnode | não | Advanced US$ 49 **sem API**; Pro **US$ 999/mês** | 10 min no Pro | https://studio.glassnode.com/pricing |
| Laevitas | US$ 0, 1 semana | Premium US$ 50; **API só Enterprise US$ 500** | 1 ano | https://www.laevitas.ch/pricing |
| Kaiko | não | contrato ~US$ 9.500 mín., média ~28.500/ano `[ANEDOTA AGREGADA]` | — | https://www.vendr.com/buyer-guides/kaiko |
| Amberdata | plataforma web | **não publica preço** | — | https://www.amberdata.io/pricing |
| Coinalyze | **API grátis, 40 req/min** | US$ 0 | retém só 1.500-2.000 pontos, apagados diariamente | https://api.coinalyze.net/v1/doc/ |

**A leitura desconfortável: o Coinglass Standard a US$ 299/mês entrega 30 dias de 5m — exatamente o que o REST grátis já dá, e 70× menos histórico que o dump gratuito. Nenhum tier do Coinglass bate o `curl`.** O único pago que entrega **mais** que o dump é o Tardis (6 s vs 5 min), a US$ 700/mês.

**Evidência de valor preditivo dos dados desses vendors: NÃO EXISTE.** Nenhum publica paper, estudo ou backtest de terceiro `[MARKETING]`. **E existe o contrário:** Giagkiozis & Said, *Reconciling Open Interest with Traded Volume in Perpetual Swaps*, **Ledger** vol. 9, 2024 `[PEER-REVIEWED]` — *"open interest in Bitcoin perpetual swaps is systematically misquoted by some of the largest derivatives exchanges"*, com erros de "wholly implausible" a atraso no reporte de liquidações. https://arxiv.org/abs/2310.14973

**Pegar o número na fonte (Binance) é mais limpo que pagar um agregador que revende o mesmo feed com uma camada de erro a mais.**

### 5.3 Notícias e sentimento — o filtro é "dá para backtestar?"

| Fonte | Custo 2026 | Histórico backtestável? |
|---|---|---|
| **GDELT 2.0 GKG** (raw / BigQuery) | **US$ 0** | **SIM — desde 19/02/2015, batch de 15 min** |
| **Fear & Greed** (alternative.me) | **US$ 0**, sem chave | SIM desde 2018 — **mas 1 ponto/DIA** |
| GDELT DOC 2.0 API | US$ 0 | NÃO — janela móvel de 3 meses |
| RSS (Cointelegraph, The Block) | US$ 0 | NÃO — testado: **30 itens, ~2 dias** |
| CryptoPanic | Free 200 créditos/mês | **NÃO — sem filtro de data, sem retrieval histórico** |
| **X/Twitter** | pay-per-use US$ 0,005/post; **full-archive só no Pro US$ 5.000/mês, tier FECHADO desde 06/02/2026** | NÃO, na prática |
| Santiment Free/Pro | US$ 0 / US$ 49 | **lag de 30 dias** → inútil. Primeiro tier tradeável: Max **US$ 249/mês**, 2 anos |
| LunarCrush | US$ 90/mês mínimo | **não publica rate limit nem profundidade** |
| NewsAPI.ai | Free 2.000 tokens; US$ 90/mês | arquivo desde 2014, mas **5 tokens por ano pesquisado** |
| CoinDesk Data (ex-CryptoCompare) | **free tier aposentado em 21/05/2026** | preço só por vendas |

**A EVIDÊNCIA — e ela é ruim.**

O único paper que testa *exatamente* a nossa pergunta ("sentimento adiciona algo em cima de um sinal técnico, pagando custo?") é Chen (2026), arXiv 2508.16378 `[PREPRINT]`, 5 moedas, 2020-2025, custo de 0,1% one-way — https://arxiv.org/html/2508.16378

| Estratégia | Sharpe |
|---|---|
| Sentimento + Técnico | **0,7102** |
| Só Técnico | **0,7026** |
| **Só Sentimento** | **0,5976** |
| BTC buy-and-hold | 0,5454 |

**O ganho de somar sentimento é 0,0076 de Sharpe. Ruído.** E sentimento sozinho é **pior** que técnico sozinho. Drawdown de 82% em todas as variantes.

**Fear & Greed — a evidência mais recente é NEGATIVA.** *Do bitcoin returns move sentiment?*, 2026 `[PEER-REVIEWED]`, diário 2018-2025: **∆FGI não Granger-causa retornos e não oferece ganho out-of-sample; retornos Granger-causam ∆FGI.** Robusto a agregação semanal, VIX, EPU, splits pré/pós-2021 e assimetria. https://www.sciencedirect.com/science/article/pii/S305070062600006X
*Faz sentido: 50% da composição do FGI é volatilidade + momentum/volume — coisa que o bot já lê. Seria alimentar o modelo com uma versão diluída e defasada do próprio preço.*

O que sobrevive é outra coisa: Farzulla (2026), arXiv 2602.07018 `[PREPRINT]`, N=2.896 — o "extremity premium": **medo e ganância extremos preveem SPREAD MAIS LARGO**, não direção (Cohen's d = 0,21; o autor admite que o endpoint pré-especificado não sobrevive à correção de múltiplos testes). **Uso defensável: reduzir tamanho quando o custo vai subir. Não é gatilho de entrada.**

Google Trends: mesmo padrão `[PEER-REVIEWED]` — testado horário, diário e semanal: **retorno imprevisível em todas; volatilidade previsível em todas.** https://www.sciencedirect.com/science/article/abs/pii/S1057521918304198

**O padrão é consistente e vale mais que qualquer paper isolado: atenção e sentimento preveem VOLATILIDADE de forma robusta e RETORNO de forma frágil.** É economicamente coerente — atenção traz volume e dispersão, não direção.

**E há um problema de reprodutibilidade que ninguém menciona:** quase toda a literatura de "Twitter prevê Bitcoin" foi escrita quando a API era grátis. **Desde 06/02/2026 o full-archive custa US$ 5.000/mês num tier fechado a novos clientes. Um resultado que não se pode replicar não é evidência disponível.**

### 5.4 Meta-labeling: o que é, e por que pode não ser o que esperamos

**A ideia** (López de Prado, *Advances in Financial Machine Learning*, cap. 3, 2018 `[LIVRO/PRÁTICA CONSAGRADA]`): o primário decide o **lado**, otimizado para **alta recall**; um secundário treina **só nos positivos do primário** e decide **se opera e com que tamanho**. Corrige precisão sem tocar no lado.

**A evidência a favor.** Singh & Joubert, *Does Meta-Labeling Add to Signal Efficacy?* `[BACKTEST DE PRATICANTE, com conflito de interesse — a Hudson & Thames vende a biblioteca]` — E-mini S&P 500, OOS 2018-2019: https://hudsonthames.org/wp-content/uploads/2022/04/Does-Meta-Labeling-Add-to-Signal-Efficacy.pdf
- Trend-following: acurácia 48% → 55%, **precisão 0,48 → 0,54**
- Mean-reversion: acurácia 17% → 63%, **precisão 0,17 → 0,20**

⚠️ **Leia a segunda linha com cuidado.** O "17% → 63%" que circula pela internet compara métricas diferentes — a acurácia do meta-rótulo binário ("o primário acertou?") não é comparável à acurácia direcional do primário. **O número honesto é a precisão: +0,03.**

Os quatro papers do *Journal of Financial Data Science* (Joubert 2022, SSRN 4032018) `[PEER-REVIEWED]` têm código em https://github.com/hudson-and-thames/meta-labeling — **sem arquivo LICENSE (404), então não assuma uso livre.**

**A crítica.** Baldisserri, QuantConnect, dez/2023 `[BACKTEST DE PRATICANTE]` — *"você não espreme a mesma laranja duas vezes"*. Grid search com um único toggle `use_meta`: o meta-modelo **piorou o Sharpe médio** e apenas alargou a variância entre seeds. Argumentos: (1) o secundário não tem informação nova; (2) se cascatear ajudasse, cascatearia infinitamente; (3) dimensionar posição é tão difícil quanto gerar sinal. https://www.quantconnect.com/forum/discussion/14706/why-meta-labeling-is-not-a-silver-bullet/

**🔴 O ponto que decide o nosso caso, e que não estava escrito em lugar nenhum:** meta-labeling pressupõe um primário de **alta recall com baixa precisão** — ou seja, que existam verdadeiros positivos escondidos no meio dos falsos. **O nosso primário acerta 48,0% (nulo 50%) e o retorno direcional médio é NEGATIVO em 1h, 4h E 24h, tanto no grupo aprovado quanto no rejeitado.** Isso não é "alta recall, baixa precisão". O fato de **os dois grupos** terem drift negativo sugere que o problema é **custo maior que o drift**, não filtrabilidade. **Meta-labeling não muda a taxa.**

### 5.5 Ferramental: o que é livre em 2026

| Peça | Biblioteca livre em 2026 |
|---|---|
| Triple-barrier | `mlfinpy` (MIT, mas **v0.1.2, parado em out/2024**) |
| **Purged/Embargoed K-Fold, CPCV** | ✅ **`skfolio` — BSD-3, `CombinatorialPurgedCV` + `optimal_folds_number`, v1.0.1 de 29/08/2026** — paper: https://arxiv.org/pdf/2507.04176 |
| Sample weights por unicidade | `mlfinpy` |
| Fractional differentiation | `fracdiff` (BSD-3, v0.9.0, **2022**) |
| PBO / CSCV | `pypbo` (GitHub, último commit jul/2026, **não está no PyPI**) |
| Deflated Sharpe | `deflated-sharpe` (PyPI, v0.1.0, mar/2026); `purged-cross-validation` |

**🔴 `mlfinlab` é PROPRIETÁRIO.** O LICENSE.txt diz *"all rights reserved"* e o preço é **£100 + VAT por mês, por usuário** — https://hudsonthames.org/mlfinlab/ . **Use `skfolio`: BSD-3, sklearn-nativa, com paper, atualizada este mês.**

**Por que purging não é opcional aqui:** horizonte de 24h em barras de 5m gera **288 rótulos sobrepostos por evento**. A unicidade média em barras financeiras cai para valores como 0,435 — a amostra efetivamente independente é menos da metade da contagem nominal de linhas. **Qualquer split ingênuo é vazamento garantido.**

### 5.6 Gradient boosting: acurácias reais vs. acurácias falsas

**Os créveis:**
- **Bysik & Ślepaczuk (2026)**, arXiv 2606.00060 — já detalhado em §1.2. Não reporta DSR nem PBO; trate o ">65% a.a." como não-verificado.
- **Jadouli (2026)**, arXiv 2607.19453 — **AUC 0,885/0,896 e decisão `NO_TRADE`**. Leia primeiro.
- **Chen (2026)**, arXiv 2608.26106 — SPY, 800 pregões: logística 71,09%, RF 61,20%, **XGBoost 58,45%**, momentum ingênuo 50,25%. Os 71% vêm de prever o fechamento **depois de ver a abertura** — o gap já contém a resposta.
- **Begušić & Kostanjčar (2019)**, arXiv 1904.00890 — **sobrevive a 100 bps** (IR 2,16). Mas o rebalanceamento é **quinzenal**, cross-sectional, long-only. **Não transfere para 5m.**

**Os falsos:** XGBoost 90,57% / AUC 97,48 (ResearchGate 379180753); LightGBM 0,905 e 0,952 (arXiv 2410.14475); XGBoost **92,40%** em BTC 15m (arXiv 2410.06935 — auditado: sem cross-validation, escalonamento com timing ambíguo, rótulos derivados de média móvel que usa preço futuro, **zero custo de transação**, e viés de sobrevivência).

**Os oito mecanismos que produzem 90%+.** Fonte-mãe: Kapoor & Narayanan (2023), *Patterns* 4(9):100804 `[PEER-REVIEWED]` — 20 relatos, 17 campos, **329 papers afetados**, taxonomia de 8 tipos de vazamento. https://www.cell.com/patterns/fulltext/S2666-3899(23)00159-9

(a) K-fold aleatório em série temporal (o *default* do `cross_val_score`; sozinho leva 50% → 85%+); (b) scaler ajustado antes do split; (c) rótulos sobrepostos — **o nosso caso, 288 por evento**; (d) feature que é proxy do alvo; (e) prever o NÍVEL e reportar R² (R²=0,99 e o baseline de persistência empata); (f) taxa base num regime único; (g) sem custo/slippage/funding; (h) seleção sobre N sem reportar N.

**🔑 O teste que denuncia (a)-(f) de uma vez: treine com os rótulos EMBARALHADOS. Pipeline limpo cai para ~50%. Se ficar acima, há vazamento e nada mais importa.**

**Existe edge sobrevivendo a 0,05%/lado?** Resposta honesta: **evidência fraca e condicionada, nenhuma limpa.** Todos os edges que sobrevivem a custo na literatura têm **baixo turnover** ou um filtro que corta a maioria das operações. **Nenhum estudo crível mostra edge direcional intradiário puro (5m/15m) sobrevivendo a 10 bps round-trip.**

### 5.7 Detecção de regime: mais folclore do que evidência

**O paper que decide a questão: Dacco & Satchell (1999), *Why do regime-switching models forecast so badly?*, Journal of Forecasting 18(1):1-16** `[PEER-REVIEWED]` — https://onlinelibrary.wiley.com/doi/abs/10.1002/(SICI)1099-131X(199901)18:1%3C1::AID-FOR685%3E3.0.CO;2-B

O argumento é contraintuitivo e é exatamente o nosso caso: **mesmo que o processo gerador seja literalmente um Markov switching de dois estados, uma taxa pequena de erro na classificação do regime destrói toda a vantagem de conhecer o modelo verdadeiro** — porque a decisão exige **prever** o regime do próximo passo, não apenas **detectá-lo**, e detecção é retroativa por construção. Corroborado por *Empirical Economics* (2020): mais regimes melhoram sobre 1 e 2, mas **Markov switching continua incapaz de bater um random walk**. https://link.springer.com/article/10.1007/s00181-019-01623-6

**Expoente de Hurst — não use ingenuamente.** Couillard & Davison (2005), *Physica A* 348:404-418 `[PEER-REVIEWED]`: **conjuntos finitos de movimento Browniano SEMPRE produzem H > 0,5.** Sem teste de significância, `if H > 0.55: regime_tendência` está classificando ruído como tendência. Requisito de amostra: **n ≥ 1000**. Em barras de 1h isso são **42 dias** — o regime mudou várias vezes dentro da janela de estimação. https://www.stats.uwo.ca/faculty/aim/TIES2012/articles/CouillardDavison.pdf

**Variance ratio em cripto** (Yi et al., *Scientific Reports* 13:4789, 2023) `[PEER-REVIEWED]`: VR(q)≈1 no longo prazo, VR(q)<1 no curto — mas a conclusão é que *"desenvolver uma estratégia lucrativa baseada simplesmente em tendências passadas do preço do Bitcoin é difícil"*. E a literatura converge para o Bitcoin **caminhando para a eficiência**. https://doi.org/10.1038/s41598-023-31618-4

**Isso significa que um edge de 2018 pode ter existido de verdade e ter morrido — o que não é overfitting, é *concept drift*, e nenhum reajuste de hiperparâmetro corrige.**

**O que TEM evidência boa e ninguém trata como "regime": volatility scaling.** Ver §4.3.

### 5.8 Armadilhas de validação — os números que doem

O orçamento de N está na §1.5. Complementos:

**PBO/CSCV** — Bailey et al., *Journal of Computational Finance* 20(4):39-69 `[PEER-REVIEWED]`, SSRN 2326253. Monta a matriz M (T×N) com o P&L de cada trial, parte em S submatrizes (S par), forma todas as C(S,S/2) combinações (S=16 → **12.780**), e para cada uma: identifica o melhor **in-sample**, mede o rank **out-of-sample**, ω̄ ∈ (0,1), logit λ = ln[ω̄/(1−ω̄)]. **PBO = ∫f(λ)dλ de −∞ a 0. Rejeite acima de 0,05.** A analogia dos autores: o rank OOS é o **placebo**. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253

**Deflated Sharpe** — Bailey & López de Prado, *JPM* 40(5):94-107 `[PEER-REVIEWED]`. PSR cujo limiar é `SR₀ = √V[{SR̂ₙ}] · E[max_N]`, deflacionado por assimetria γ̂₃, curtose γ̂₄, comprimento T, variância dos Sharpes entre trials, e N. **Detalhe operacional que quase todo mundo erra: V[{SR̂ₙ}] é a variância ENTRE OS TRIALS. Se você não guardou o Sharpe de cada configuração testada, não consegue calcular DSR. Guarde a matriz M.** https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf

**Críticas legítimas ao próprio López de Prado** (de falseabilidade, não de matemática): **N é inobservável e é um botão que o pesquisador gira**; o CSCV assume matriz síncrona e quebra métricas dependentes de trajetória (drawdown) ao recombinar fora de ordem — o próprio Algoritmo 2.3 admite isso.

**Viés de sobrevivência:** Ammann et al. (2022, SSRN 4287573) `[PREPRINT/SSRN]` — 3.904 criptos 2014-2021: **31% morreram**; o viés vale **62,19% ao ano** equal-weighted (0,93% value-weighted), com o prêmio de tamanho superestimado em 50%. **O bucket da Binance guarda os deslistados — dá para reconstruir o universo point-in-time de graça, e quase ninguém faz.** https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4287573

**Look-ahead específico do nosso caso:**
- **Funding:** `/fapi/v1/fundingRate` devolve a taxa **já liquidada**, carimbada em `fundingTime`. Forward-fill **para trás** dentro da janela de 8h ⇒ até **8 horas de look-ahead** numa feature diretamente correlacionada com pressão direcional. A taxa carimbada em T entra nas features **a partir de T**.
- **OI:** o `create_time` do `metrics` é o **fim** do bucket de 5 min — usar o OI carimbado no fechamento da barra para decidir a entrada naquele mesmo fechamento é look-ahead sutil e real. **Defase uma barra.**
- 🔴 **O [CX-2] mediu que o portão de OI PIORA os quatro níveis. Antes de concluir "overfitting", cheque o carimbo de tempo — feature contaminada é o outro candidato, e produz o mesmo sintoma.**

---

## 6. RANKING DAS 8 IDEIAS MAIS PROMISSORAS

### #1 — Cortar a taxa: maker + BNB, e auditar onde o post-only é seguro

**O que é.** Levar o round-trip do patamar atual (post-only entrada + taker saída = 7 bps) para o mais perto possível de 0,036% (maker 0,018%/lado com desconto BNB), **exceto nas saídas de emergência, que devem ser taker/stop-market na exchange**.

**Evidência e qualidade.** `[DOCUMENTAÇÃO OFICIAL]` para os números de taxa; `[MEDIÇÃO INTERNA]` para "a 0,05%/lado reprova, a 0% passaria"; `[PEER-REVIEWED]` (Bajgrowicz & Scaillet 2012; FRL 2020) para "custo baixo já anula a performance in-sample"; `[PREPRINT com experimento ao vivo]` (Albers et al. 2025) para o risco de seleção adversa que isso introduz.

**Esforço em Python.** Baixo — configuração de conta + auditoria do caminho de saída no código. Horas, não dias.

**O que medir antes de acreditar.** (a) fração real de fills maker nos últimos 30 dias e taxa efetiva paga por trade, extraídas do income history; (b) **taxa de não-fill do post-only e o custo de oportunidade dela**; (c) **markout de 1 s, 10 s, 60 s e 5 min pós-fill, em bps** — se o markout ficar plano ou piorar com o tempo, temos seleção adversa confirmada e quantificada, e a decisão post-only vs mercado deixa de ser palpite.

---

### #2 — Baixar o dump `metrics` do `data.binance.vision`

**O que é.** ~487 MB, 24 pares, 1.731 dias, 5 minutos: OI em contratos e USDT, três razões de posicionamento, e taker long/short vol ratio. Destrava a pesquisa que está travada pelo limite de 30 dias do REST.

**Evidência e qualidade.** `[VERIFICAÇÃO DIRETA]` — arquivos baixados e abertos; `[DOCUMENTAÇÃO OFICIAL]` para o limite de 30 dias do REST.

**Esforço em Python.** Baixo-médio: ~70 min de download + 1 dia de engenharia de ingest, com as cinco armadilhas da §5.1 tratadas (ordenar por `create_time`, deduplicar, farejar header dos klines, defasar uma barra, validar parse de data).

**O que medir antes de acreditar.** Emende a cauda D-1 com o REST e **valide a junção comparando 3 dias de sobreposição.** Se não bater, pare aí.

---

### #3 — Desligar o portão binário de fluxo e re-medir o mesmo dado como preditor contínuo em 4-12h (incluindo o sinal invertido)

**O que é.** Três movimentos: (a) remover o flag que descarta 38,9% dos sinais com p=0,58; (b) reconstruir `imb = (2·takerBuyBaseVolume − volume)/volume` por candle com **z-score rolante por par** (300-500 candles), normalizado, contínuo, e testar contra retorno futuro de 1h, 4h e 24h; (c) **testar o sinal invertido** sobre os 2.596 desfechos já marcados.

**Evidência e qualidade.** `[PEER-REVIEWED]` Cont et al. (TI é a variável dominada, insignificante em 69% das subamostras); `[PREPRINT de alto nível]` Kim & Hansen (o imbalance prevê 4-12h, mas **é negativo na primeira meia hora**); `[PREPRINT com experimento ao vivo]` Albers et al. (a estratégia maker viável é *contrária* ao imbalance). **Três evidências independentes apontando que o sinal pode estar com o sinal trocado.**

**Esforço em Python.** (a) e (c) são de 1 linha cada. (b) é uma tarde, usando klines gratuitos — anos de histórico, sem baixar um aggTrade.

**O que medir antes de acreditar.** IC de Spearman contra retorno futuro por par e agregado, com bootstrap de bloco. **Portão de aceite honesto: IC out-of-sample ≥ 0,02 com IC95 que não cruza zero.** ⚠️ E note: **mesmo passando no IC, ainda precisa passar no custo** — o Frontiers achou R² marginal de 1,23% e ainda assim Sharpe líquido negativo.

---

### #4 — Filtro de MAGNITUDE (não de sinal): cortar turnover em uma ordem de grandeza

**O que é.** Só operar quando a magnitude prevista excede um limiar derivado do custo. É o "menos trades, mais certos" com evidência. Consulta imediata e gratuita: **qual seria a P&L do sistema atual se só os 2,5% de sinais de maior convicção fossem executados?** — é uma query no banco de 2.596 sinais, não um projeto.

**Evidência e qualidade.** `[PREPRINT]` Bysik & Ślepaczuk 2026 — o filtro cortou 10.619 → 251 trades e foi o que transformou colapso pós-taxa em Sharpe 1,09; `[PEER-REVIEWED]` FRL 2020 (ML perde para TA *por causa do turnover*); `[PEER-REVIEWED]` IRFA 2024 (alphas de momentum caem 26-53% após custos).

**Esforço em Python.** Baixo para a query; médio para o limiar em produção.

**O que medir antes de acreditar.** Varra o limiar e reporte a curva **turnover × Sharpe líquido**, com DSR ajustado pelo número de limiares testados. **Se o Sharpe só melhora no limiar mais alto, onde sobraram 30 trades, é seleção, não edge.**

---

### #5 — Vol targeting da carteira + teto de risco ajustado por correlação + alavancagem constante

**O que é.** Substituir "3% por trade, até 5 posições, teto agregado 10%, alavancagem 2x-20x" por: alvo de **20-25% de vol anualizada** da carteira (nocional ≈ 6% da banca por posição, gross ≈ 30%), teto **σ_p = √(Σσᵢ² + 2Σρσᵢσⱼ) ≤ 4% da banca** checado **ex-ante** com piso de ρ=0,7 entre alts, risco por trade **0,75-1,0%**, e **alavancagem constante 3x-5x, teto 10x**.

**Evidência e qualidade.** `[PEER-REVIEWED]` Barroso & Santa-Clara 2015 (Sharpe 0,53 → 0,97), Harvey et al. 2018, Moskowitz et al. 2012, FRL 2025 e JIFMIM 2022 em cripto; `[LIVRO/PEER-REVIEWED]` MacLean/Thorp/Ziemba para o limite de 2× Kelly; `[DOC OFICIAL]` para MMR e distância de liquidação. **⚠️ Com o contraponto de Kim/Tse/Wald 2016 — ver §7.**

**Esforço em Python.** Médio: EWMA de vol com meia-vida 20 dias, matriz de correlação rolante 30 dias, e um gate pré-trade. 2-3 dias.

**O que medir antes de acreditar.** (a) **gross notional real e vol realizada anualizada da curva** nos últimos 30 dias — se a vol da curva estiver acima de 100% a.a., a discussão de sinal é secundária; (b) **correlação par-a-par realizada das posições que o bot efetivamente abriu junto** e o N_eff — se N_eff < 2, o teto de 5 posições é ficção; (c) **funding pago acumulado vs. lucro acumulado**; (d) o teste de placebo da §7.

---

### #6 — Trocar a régua: CPCV (`skfolio`) + PBO + DSR com N efetivo por PCA + teste de rótulo embaralhado

**O que é.** Substituir walk-forward por `CombinatorialPurgedCV` com purging e embargo dimensionados pelo horizonte máximo (24h em barras de 5m ⇒ embargo ≥ 288 barras); estimar o **N efetivo** por PCA sobre a matriz de retornos dos trials; recalcular DSR com esse N; rodar PBO e rejeitar acima de 0,05.

**Evidência e qualidade.** `[PEER-REVIEWED]` Arian, Norouzi & Seco 2024 (**CPCV marcadamente superior; walk-forward com deficiências notáveis em controle de falso positivo**); `[PEER-REVIEWED]` Bailey et al. 2014 (o orçamento de ~14 tentativas); `[PEER-REVIEWED]` Kapoor & Narayanan 2023 (os 8 mecanismos de vazamento); `[PEER-REVIEWED]` IRFA 2024 (erros não-padrão em cripto superam os erros-padrão).

**Esforço em Python.** Médio: `skfolio` é BSD-3 e sklearn-nativa. 2-3 dias.

**O que medir antes de acreditar.** 🔑 **O teste de rótulo embaralhado, ANTES de tudo.** Se o pipeline atual, com rótulos aleatórios, der acima de ~52%, há vazamento e nada nesta lista importa até isso ser corrigido. E **guarde a matriz M** — sem o Sharpe de cada trial, não há DSR.

---

### #7 — Basis / funding como fator de RANKING cross-sectional (não como gatilho de reversão)

**O que é.** Ordenar os pares por basis/funding e operar o cross-section, em vez de usar "funding extremo" como gatilho direcional. O dado já é gratuito na API e no dump (`premiumIndexKlines`, `fundingRate` mensal, `metrics`).

**Evidência e qualidade.** `[PEER-REVIEWED]` Cao, Zhai & Luo (JFM 2024) — **dois fatores, basis + preço-volume, explicam as 48 estratégias significantes de 134 testadas**; `[PEER-REVIEWED/BIS]` Schmeling et al. para a economia do carry; `[PREPRINT/SSRN]` Fan et al. — carry cross-sectional com **Sharpe 0,74** (o número crível).
⚠️ **Com o alerta de decaimento: o carry harvest saiu de Sharpe 6,45 para NEGATIVO em 2025.**

**Esforço em Python.** Médio: é uma mudança de arquitetura de decisão (de por-par para cross-sectional), não um indicador novo.

**O que medir antes de acreditar.** Reproduza o ranking sobre 2024-2026 separadamente de 2020-2023 e veja se o efeito ainda existe **na janela recente**. **Não use "funding acima de X = reversão"** — isso é folclore sem backtest.

---

### #8 — Momentum intradiário de horário fixo (1 trade/dia/ativo)

**O que é.** Um trade por dia por ativo na janela documentada: retorno da primeira meia hora prevendo o da última; ou a janela 22:00-00:00 UTC. Turnover baixíssimo, custo previsível.

**Evidência e qualidade.** `[PEER-REVIEWED]` Bitcoin intraday TS momentum (Sharpe 0,53 simples, **1,15 combinado**, 13,95% a.a.); `[BACKTEST DE PRATICANTE]` Quantpedia/Padyšák & Vojtko para o 22:00 UTC (Sharpe 1,58 **mas sem custos declarados** e ~365 trades/ano).
⚠️ **Caveat sério: o próprio paper atribui o mecanismo a provisão de liquidez — quem captura é o lado passivo, não quem cruza o spread.**

**Esforço em Python.** Baixo: é uma regra de horário sobre klines gratuitos.

**O que medir antes de acreditar.** Reproduza no perp da Binance (o paper original é de outra fonte de preço) sobre 2022-2026, com 7 bps de round-trip, e cheque se o efeito ainda existe fora do bull de 2020-2021. **E reporte quantas variantes de horário foram testadas** — o horário é um hiperparâmetro e entra no N do DSR.

---

**Menções que não entraram no top 8, mas são baratas:** reduzir de **24 para 10-15 pares** (Man Group mediu o pico de Sharpe nessa faixa; além disso o custo come a diversificação); **reconstruir o universo point-in-time** com os deslistados do bucket (viés de sobrevivência de 62,19% a.a. medido por Ammann et al.); e **começar a gravar book/`forceOrder` prospectivamente** — cada dia sem coletar é um dia de histórico que não se recupera, já que o dump não publica bookDepth antes de 2023 nem `metrics` em granularidade fina.

---

## 7. O QUE A PESQUISA DIZ PARA **NÃO** FAZER

1. **Não continue consertando a confluência técnica.** É a hipótese mais bem refutada de todo o relatório: Sullivan-Timmermann-White 1999, Bajgrowicz-Scaillet 2012, IREF 2024, Sensors 2023, FRL 2020. Bajgrowicz & Scaillet fecham a porta duas vezes: **não dá para selecionar ex ante a regra que vai funcionar, e mesmo in-sample o custo baixo já zera tudo.**

2. **Não adicione portão de open interest.** Já medimos que piora; a literatura acadêmica de OI é de horizonte **mensal** em commodities e moedas (Hong & Yogo); o teste direto em cripto (arXiv 2607.27070) não achou poder preditivo; e os "4 quadrantes" não têm **uma única fonte com número**.

3. **Não adicione long/short ratio de top traders.** Zero estudos medindo poder preditivo; "top trader" é o top 20% **por margem, não por lucro** (doc oficial); é contagem de **contas**, não de dinheiro; e foi testado e reprovado no paper de cascatas. A única evidência peer-reviewed de posicionamento é **COT semanal da CME** — outro instrumento, outra frequência. Não transponha.

4. **Não compre nem construa liquidation heatmap.** É um algoritmo de predição vendido como dado; exchanges não publicam stops nem alavancagem. E o `forceOrder` envia **uma ordem por segundo por símbolo, só a maior** — incompleto por design **exatamente durante as cascatas**, com viés máximo nos eventos extremos.

5. **Não use CVD como confluência.** Nenhum paper. O material honesto dentro do próprio marketing diz que ele **descreve, não prevê**. Adicionar CVD ao score de convicção é adicionar mais um peso à mão sem evidência — exatamente o mecanismo que já produziu overfitting no [CX-2].

6. **Não pague por dado de OI.** Coinglass Standard: **US$ 299/mês para receber 30 dias de 5m — o mesmo que o REST grátis, e 70× menos que o dump gratuito.** X/Twitter full-archive: US$ 5.000/mês num tier **fechado a novos clientes**. Santiment Max: US$ 249/mês. LunarCrush: US$ 90/mês e não publica os limites que importam. mlfinlab: £100/mês por algo que `skfolio` faz de graça. **E o paper do Ledger (2024) mostra que agregadores adicionam uma camada de erro sobre o feed da própria exchange.**

7. **Não use Fear & Greed como gatilho de entrada.** A evidência mais recente e robusta (2026, peer-reviewed) diz que **retornos Granger-causam sentimento, não o contrário**, e que ∆FGI não oferece ganho out-of-sample. Além disso, 50% da composição do índice é volatilidade + momentum/volume — seria alimentar o modelo com uma versão diluída e defasada do próprio preço. **Uso defensável: modular tamanho/custo (o "extremity premium" prevê spread mais largo).**

8. **Não faça equity curve trading como filtro de alfa.** Kisela et al.: melhora em **22 de 80 casos, e só onde a curva bruta já era negativa**. KJ Trading: ouro quase sempre pior, iene sempre pior. **De-risking por drawdown como restrição de sobrevivência é outra coisa e é defensável — declare qual dos dois você está fazendo.**

9. **Não use Optimal f nem Kelly cheio.** Optimal f calibra sobre um histórico que já provamos não ter edge e daria f alto **exatamente porque o dia 21/08 (323% do lucro) está na amostra**. E acima de 2× Kelly o crescimento é negativo mesmo com edge real — estamos em 2,79×.

10. **Não mande saída de emergência como post-only.** Num movimento rápido ela não preenche, o preço atravessa o stop e vai para a liquidação — que custa 1,69× a 6,69× o stop, dependendo da alavancagem. **Verificar no código hoje.**

11. **Não acredite em acurácia acima de ~60% em classificação direcional de cripto.** Os 8 mecanismos de vazamento de Kapoor & Narayanan explicam todos os 90%+. E Jadouli (2026) mostra o caso decisivo: **AUC 0,885 e `NO_TRADE`.**

12. **Não filtre por regime com HMM/Hurst ingênuo.** Dacco & Satchell: mesmo com o modelo verdadeiro, erro pequeno de classificação destrói a vantagem, porque é preciso **prever** o regime, não detectá-lo. Couillard & Davison: **movimento Browniano finito sempre dá H > 0,5** — sem teste de significância você está chamando ruído de tendência.

13. **Não reporte Sharpe sem erro-padrão.** Com 10 dias, SE = 6,05 e IC95 = ±11,85. Não é resultado fraco; é **zero informação**.

14. **Não conte o dia 21/08 como parte da estratégia até provar o contrário.** Recorte-o e recalcule tudo. Se sem ele o resultado vira negativo, a manchete "+11,6%" não existe.

---

## 8. CONTRADIÇÕES ENTRE AS FONTES — declaradas, não resolvidas

### 8.1 🔴 Vol targeting: remédio ou gerador de miragem?

Harvey et al. (2018), Barroso & Santa-Clara (2015), FRL 2025 e JIFMIM 2022 mostram melhoras substanciais de Sharpe. **Mas Kim, Tse & Wald (2016, Journal of Financial Markets, peer-reviewed) sustentam que os alfas do TSMOM são em grande parte DIRIGIDOS pelo vol scaling — e que sem ele o TSMOM não bate buy-and-hold.**

**Consequência prática que não pode ser ignorada: se ligarmos vol targeting e o Sharpe melhorar, isso não prova que a entrada melhorou.** O teste de placebo obrigatório: rodar o mesmo vol targeting sobre **sinais aleatórios** com a mesma frequência e distribuição de holding. Se o Sharpe melhorar igual, a melhora era do sizing, não do sinal.

**Não resolvida.** As duas leituras são compatíveis com os mesmos dados; a diferença é sobre a atribuição do efeito.

### 8.2 🔴 Cortar a taxa (maker nos dois lados) × não morrer liquidado × seleção adversa

Três achados colidem:
- A frente de **dados/método** recomenda maker + BNB nos dois lados (0,036% round-trip) como a alavanca mais barata.
- A frente de **risco** exige que **saídas de emergência nunca sejam post-only** — post-only na saída em movimento rápido leva à liquidação, que custa 1,69× a 6,69× o stop.
- A frente de **microestrutura** mostra (Albers et al., experimento ao vivo) que postar maker **na direção do sinal** é a configuração *"highly unprofitable"* por seleção adversa: você só é preenchido quando o mercado vai contra.

**Não há síntese limpa.** O maker cheio nos dois lados é o mais barato em fee e o mais caro em risco de cauda e em seleção adversa. **A resolução tem que vir de medição própria** — markout pós-fill e taxa de não-fill — não de escolher qual das três fontes é a "certa".

### 8.3 Momentum em cripto: vivo ou artefato de amostra?

Três papers peer-reviewed de 2025-2026 atacam a robustez (não existe em survivor coins; média e variância populacionais não definidas; sem payoff em large-caps equal-weighted). Um paper peer-reviewed de 2025 reporta melhora com risk-management (Sharpe 1,12 → 1,42). E os próprios autores do paper seminal medem o fator **encolhendo** pós-2020 (0,026 → 0,021), com o de horizonte longo **não significante**.

**Não resolvida.** A leitura mais defensável é que **momentum de curto prazo (~2 semanas) é o único que sobrevive, e encolheu** — mas isso é interpretação, não consenso da literatura.

### 8.4 Correlação de altcoins: recorde histórico ou desacoplamento pós-ETF?

DefiLlama (dez/2025) reporta BTC-ETH 0,89 e BTC-SOL 0,99, **máximas históricas**; Economics Letters (2024) mede o beta sistemático subindo de 0,03 para 0,83. **Mas Cogent Economics & Finance (2026), com 18 altcoins e 2021-2025, argumenta desacoplamento estrutural pós-ETF spot.**

**Não resolvida.** Se o desacoplamento for real, muda o número (ρ), não a lógica (N_eff). A recomendação de usar ρ=0,85 de trabalho e 0,95 de estresse é conservadora nos dois cenários — mas deve ser **medida na nossa própria carteira**, não herdada.

### 8.5 O portão de fluxo: matar ou reconstruir?

A frente de **microestrutura** diz "mate hoje, é 1 linha, não substitua por nada ainda — só remova e re-meça". A frente de **estratégia** diz "teste o mesmo dado como preditor contínuo em 4-12h antes de descartá-lo como inútil — pode ser que o dado preste e o uso é que esteja errado".

**Compatíveis em sequência, não em simultâneo.** A ordem defensável é: desligar o flag binário (que comprovadamente descarta 38,9% sem poder), e **em paralelo** medir o dado contínuo offline. Mas as duas frentes concordam num ponto forte: **o horizonte de 4-12h é onde o sinal vive, e não é o horizonte em que o bot decide.**

### 8.6 Meta-labeling: o método que o dono pediu pode não se aplicar ao nosso primário

A literatura (López de Prado; Joubert et al. no JFDS) sustenta o método, e ele é a tradução técnica exata do "menos trades, mais certos". **Mas a análise da frente de dados aponta que meta-labeling pressupõe um primário de alta recall e baixa precisão — e o nosso primário tem drift negativo TANTO no grupo aprovado QUANTO no rejeitado**, o que sugere que o problema é custo > drift, não filtrabilidade. E a crítica do QuantConnect mostra o meta-modelo **piorando o Sharpe médio** num grid controlado.

**Não resolvida — e é a contradição mais cara.** Se o método não se aplicar, a conclusão correta é **trocar o primário**, não empilhar um segundo modelo. O filtro de magnitude (#4) é a versão barata da mesma ideia e deve vir antes.

### 8.7 Carry: o único edge com evidência forte é também o que a evidência diz estar morto

Schmeling et al. (BIS) documentam carry de até 60% a.a. com base econômica sólida. Cao et al. (JFM 2024) mostram basis como fator dominante em perps. **Mas os próprios Borri/Liu/Tsyvinski/Wu medem Sharpe 6,45 → 4,06 → negativo em 2025.**

**Não resolvida.** Ficam duas leituras: (a) o *harvest* do carry morreu, mas o *basis como variável de ranking* continua informativo; (b) ambos morreram junto. **A #7 do ranking existe justamente para separar as duas — testando 2024-2026 separadamente de 2020-2023.**

---

## 9. O QUE NÃO FOI POSSÍVEL APURAR

1. **Taxa de fill realista de ordens post-only em perps.** O SSRN de Albers et al. retornou 403 e o PDF do arXiv veio com streams comprimidos ilegíveis. **E há uma razão de fundo, declarada no próprio paper:** *"order-by-order data that would allow precise backtesting of candidate maker strategies is not available in crypto markets"*. **Não existe dado público que permita estimar taxa de fill sem rodar um experimento ao vivo.** Essa estatística tem de vir do nosso próprio log de ordens.

2. **Banda, CPU e RAM para 24 pares em websocket.** Não existe fonte oficial nem benchmark público. Dá para dimensionar de forma defensável (`depth20@100ms` × 24 pares = 240 msg/s, **480/s após a mudança para 50 ms em 26/11/2025**, mais aggTrade e bookTicker), **mas isso precisa ser medido na nossa VM** — que já está com 88,7% de RAM.

3. **Os Sharpes originais do *Crypto Carry* (BIS WP 1087).** O link direto do BIS deu 404 nas duas frentes que tentaram. Os números (6,45 / 4,06 / negativo) vêm de citações secundárias e do preprint de Borri et al. — **não verificados no documento original.**

4. **Effect size do VPIN** em *Bitcoin wild moves* (RIBAF 2026) — paywall.

5. **Números completos de *Order Flow and Cryptocurrency Returns*** (+0,2% diário, +0,9% semanal por 1 dp) — 403 no ScienceDirect e erro de certificado no EFMA; vindos de resumos indexados.

6. **Preço da Amberdata** — não publicado. **Limites de rate e profundidade do LunarCrush** — não publicados.

7. **Licença do repositório `hudson-and-thames/meta-labeling`** — o arquivo LICENSE dá 404. Não assuma uso livre.

8. **DSR e PBO do Bysik & Ślepaczuk (2026)** — o paper não os reporta, então o ">65% a.a. com Sharpe 1,09" fica como **não-verificado quanto a overfitting**, apesar de o desenho (27 folds, 10 bps) ser o mais próximo do nosso problema.

9. **Quanto do nosso resultado ao vivo vem do funding.** Não sabemos se o funding está no P&L do paper trading. Se não estiver, o resultado está inflado em algo entre 3% e 55% da banca ao ano, dependendo do gross real.

10. **Nossa distribuição real de stops.** A conta de gross 500% assume stop de 3% (risco 3% / stop 3% = nocional 1,0× banca). **Se os stops de 3×ATR forem materialmente mais largos na prática, o gross é menor** — mas nenhuma das frentes tinha acesso ao log para medir. Isso muda a magnitude do problema de risco, não a direção.

---

## 10. A FRASE QUE RESUME

> Não temos problema de dados — os dados que faltavam estão de graça no bucket da própria Binance e baixam em uma hora. Temos um sinal cujo drift é menor que a taxa, medido com uma régua (walk-forward) que a literatura peer-reviewed identifica como a mais fraca em controle de falso positivo, sobre um orçamento de ~14 tentativas independentes que estourou há muito tempo, e executado com um sizing que destruiria a banca **mesmo se o sinal fosse bom**.
>
> **Corte a taxa, corte o turnover, corte o risco, troque a régua — e só depois pergunte se o sinal presta.**

E a advertência de calibragem, que vale para tudo que vier depois: os números mais chamativos desta pesquisa — 2,16% ao dia líquido, IR 8,97 a 3 segundos, Sharpe 2,41 com DD de −12,7% atravessando 2022, Sharpe 6,45 do carry — são todos implausíveis ou já mortos. **Os números críveis são pequenos: Sharpe 0,5 a 1,4, alphas que caem 26-53% com custo, 57% de acurácia direcional, 0,5 bp de previsibilidade por evento.** É essa a escala do que existe. Um sistema de varejo com US$ 1k-50k, sem colocation, com Sharpe realista de 0,5-1,0 e turnover baixo, é um resultado **bom**. Qualquer coisa acima disso, em backtest, é overfitting até prova em contrário — e já provamos isso três vezes internamente.
