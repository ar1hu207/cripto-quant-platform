# Ferramenta de operação e análise de criptoativos

**Para onde isto aponta está em [NORTE.md](NORTE.md) — leia primeiro.** Em uma frase: operar
sozinho (day trade, swing trade e gestão de carteira) e ser uma ferramenta de análise de mercado
que consolida notícia, momentum, posicionamento e técnica. É pra ser lucrativa.

**Estágio de hoje:** paper trading — dinheiro fictício, sem chave de exchange, sem ordem real,
só dados públicos da Binance via `ccxt`. Isso é o estágio, não o destino: o painel é o mesmo que
um dia encosta em dinheiro de verdade, e é por isso que as guardas de risco são levadas a sério
desde agora.

O objetivo é um sistema **lucrativo** — e a régua existe para que o lucro, quando vier, esteja
atrás de evidência e não de sorte. Ela mede estratégias com rigor estatístico e **mata as ruins
antes que elas custem dinheiro real**. Até hoje nenhuma estratégia medida passou: o veredito
abaixo é o estado da busca, não o objetivo dela.

---

## O veredito (o resultado mais importante do projeto)

Todas as estratégias implementadas foram testadas com **walk-forward** (parâmetros escolhidos
só no passado, avaliados no futuro não-visto), **Deflated Sharpe Ratio** e bootstrap:

| Estratégia | Veredito | Evidência |
|---|---|---|
| Tendência (EMA/ADX/Donchian/RSI) | ❌ sem evidência de edge | 3 anos, 2.574 trades OOS, 908 dias de série diária. Reality Check **p = 0,49** · IC95% da média/dia (bloco) `[−13,1; +15,9]` inclui 0 · PSR 0,57 · **DSR = 0,0095** · Sharpe anualizado 0,11, IC95% `[−1,69; +1,34]` |
| Reversão à média (RSI + Bollinger) | ❌ breakeven | Melhor caso +R$73 in-sample / −R$76 OOS em ~1100 trades |
| Funding arb (cash & carry) | ❌ não-deployável | +1,9%/ano líquido; versão *gated* fica negativa (4 pernas de taxa comem o funding) |

**Não existe edge deployável — no que foi implementado até aqui.** Isso não é fracasso nem é o
destino: é o que se sabe hoje, obtido sem torrar banca real. É o piso a partir do qual se procura
sinal novo.

> ⚠️ **A linha "Tendência" acima foi medida com alavancagem FIXA em 10x; a produção roda 2x–20x
> por convicção.** O `[Q-12]` re-mediu as quatro políticas de saída sob a configuração real em
> 2026-08-25 (`VEREDITO-M4-PRODUCAO-2026-08-25.md`; leitura em
> `INVESTIGACAO-MOTOR-2026-08-24.md` §10). **O veredito não muda** — as quatro seguem sem
> evidência de edge e a ordenação entre elas se mantém —, mas as magnitudes sim: a política que
> roda ao vivo (`C trailing 2% fixo`) sai com **Sharpe 0,976** e **PSR 0,954** em produção,
> contra 0,645 e 0,854 a 10x fixo, e o IC95% do Sharpe `(−0,353 ; 2,074)` **ainda inclui o
> zero**. As quatro políticas melhoraram, o que localiza o ganho no **dimensionamento** e não na
> gestão da posição. Quem citar números daqui tem de dizer sob qual configuração eles falam.

> ⚠️ **A linha "Tendência" mudou de números no `[Q-1]`, e o número velho não era comparável.**
> O registro anterior — *370 trades, PnL −R$807, DSR = 0,004* — saiu de uma régua com
> `DIAS = 180`, DSR sobre a **lista de trades** e `n_trials = 30`. Ela media outra coisa, e
> media inflado: com 180 dias o Sharpe anualizado **mínimo detectável era ~3,5**, ou seja aquele
> "sem edge" foi emitido por um instrumento que **não tinha poder para emiti-lo**. A rodada
> retroativa com o instrumento novo está na §6 do
> [`ITEM1-VALIDACAO-RIGOROSA.md`](ITEM1-VALIDACAO-RIGOROSA.md), com a saída literal.
>
> **O P&L OOS de 3 anos deu POSITIVO (+R$993) e o veredito continua negativo** — é o instrumento
> funcionando, não uma contradição: 3 folds positivos de 5, e o fold 2 sozinho vale **5,86× o
> total**. Dispersão enorme em torno de zero é a assinatura de ruído.
>
> **E o que o teste NÃO exclui:** o IC95% do Sharpe anualizado vai até **+1,34**. Os dados não
> refutam edge — falham em demonstrá-lo. *Ausência de evidência não é evidência de ausência*, e
> a régua nova imprime essa distinção em vez de arredondar "não consegui medir" para "não
> existe". Quando nem isso ela consegue, responde `INCONCLUSIVO`. Ver *Critério de aceite*.

Duas lições que se sustentaram em todos os testes:

1. **A taxa decide.** O mesmo sinal rendeu −R$589 (taker) e +R$73 (maker). Toda estratégia
   entra com ordem limite.
2. **Alavancagem amplifica risco, não edge.** Em 100% dos backtests, 2x deu retorno pior *e*
   drawdown pior que 1x.

---

## Arquitetura

```
web/index.html ──► FastAPI (api.py) ──► SQLite (WAL)
                        │
                        └── worker (15s): marca posições, fecha stop/liquidação,
                                          escaneia sinais, grava equity
```

O desenho completo — fluxo do worker, ciclo de vida do sinal, esquema das 7 tabelas, topologia
do deploy e a razão registrada de cada decisão, tudo com `arquivo:linha` — está em
**[ARQUITETURA.md](ARQUITETURA.md)**. Se você é uma sessão de IA, comece pelo
**[CLAUDE.md](CLAUDE.md)**: é o contrato entre sessões, e traz os invariantes que não se
relaxam sem decisão humana.

### Mapa de pastas

Três eras do projeto, e a divisória é explícita desde o `[P2-16]`. Qual arquivo você edita
depende de qual destas você está tocando:

| Onde | O que é | Regra |
|---|---|---|
| **raiz** (`*.py`) | **plataforma viva** — os 11 módulos que o `api.py` alcança, mais as provas que se rodam por `python <arquivo>` | é o que roda na VM; o `deploy/cripto-bot.service` sobe `uvicorn api:app` daqui, e por isso a plataforma **não** sai da raiz |
| **`pesquisa/`** | **pesquisa viva** — a régua que mede estratégia (`validacao`, `backtest_plataforma`, `dados`) | pacote Python; roda por `python -m pesquisa.<modulo>` **da raiz**. Não é código de produção. `tune` e os `validar_*` saíram daqui no `[Q-2]` — emitiam veredito de edge por metodologia superada |
| **`legado/`** | fases 1-2 — motor próprio, `estrategias/`, `config.py`, scripts de varredura | **nada ali é importado pela plataforma, e nada ali roda mais onde está.** Leia o [`legado/README.md`](legado/README.md) antes de mexer |
| **`tests/`** | a suíte do `pytest` | ver *Testes*, abaixo |
| **`web/`** | front estático (Vercel) | merge na `main` **é** a publicação |
| **`deploy/`** | service, Caddyfile e `atualizar.sh` (deploy de um comando) | roda na VM |

**A fonte da verdade dos parâmetros é `db.CONFIG_PADRAO` + a tabela `config`**, validada no
`POST /config` — não há outra. `legado/config.py` reivindicava o mesmo posto com valores
diferentes (risco 0,5% × 3%, alavancagem 1× × 10×); o `[P2-16]` tirou a reivindicação dele.

### Módulos

| Arquivo | Papel |
|---|---|
| `api.py` | Backend FastAPI + worker em background + autenticação |
| `db.py` | SQLite (posições, trades, sinais, equity, config, banca) e métricas |
| `scoring.py` | Pontuação de convicção — **compartilhada** entre live e backtest (é a paridade) |
| `signal_engine.py` | Varredura ao vivo, portões de confirmação, gestor de saída |
| `simulador.py` | Abertura/fechamento, P&L com alavancagem/taxa/funding, liquidação, guarda de risco |
| `autotrader.py` | Modo automático (desligado por padrão) |
| `mercado.py` | Order book, fluxo taker, funding, sentimento |
| `dca.py` | Acumulação periódica sem alavancagem |
| `pesquisa/validacao.py` | **Walk-forward + Deflated Sharpe + bootstrap** — a régua que barra ideia ruim |
| `pesquisa/backtest_plataforma.py` | Backtest com paridade: sinal no candle fechado, execução no open seguinte |
| `indicadores.py` | EMA, ATR, ADX, RSI, Donchian, Bollinger |

### Gestão de risco (o tripé)
- **Sizing por risco** — R fixo por trade, dimensionado por ATR
- **Trava diária** — bloqueia novos trades ao passar do limite de perda do dia
- **Teto de exposição aberta** — soma o risco-até-o-stop de todas as posições

---

## Rodar local

```bash
pip install -r requirements.txt
uvicorn api:app --port 8000
```
Painel em <http://localhost:8000>. Sem `DASH_PASS` definido, o app aceita **apenas acesso
local** — requisição externa ou via proxy recebe 503.

### Validar uma estratégia

`pesquisa/` é um pacote e roda com `-m`, **a partir da raiz do repositório**:

```bash
python -m pesquisa.validacao             # a régua completa (~30 min na 1a vez)
python -m pesquisa.backtest_plataforma   # backtest com paridade live<->histórico
python -m pytest tests/test_validacao.py # as provas da régua (7 s, sem rede)
```

⚠️ **`python -m pesquisa.validacao` leva dezenas de minutos, e não está travado.** Na primeira
execução do dia ele baixa 12 moedas × 3 anos de candles de 1h (~315 mil candles, paginado com
rate-limit) e cacheia em `pesquisa/dados_cache/`; o nome do arquivo de cache **inclui a data**,
então o cache de ontem não é reaproveitado. Depois disso são 6 configs × 12 moedas de backtest,
duas vezes (a passada com funding e o contraste sem, do `[P2-10]`) — ~13 min cada.

`python pesquisa/validacao.py` **não** funciona, e isso é por construção: rodar por caminho
põe `pesquisa/` no `sys.path` em vez da raiz, e o `import scoring` falha. `scoring.py` e
`indicadores.py` ficam na raiz porque são compartilhados entre live e backtest — esse
compartilhamento é a paridade, e o motivo completo está em `pesquisa/__init__.py`.

---

## Testes

**Rode antes de todo deploy.** A suíte não faz rede e não toca no `trading.db`: cada teste
usa um banco temporário e substitui `preco_ao_vivo`.

```bash
pip install -r requirements-dev.txt
python -m pytest                       # tudo — 144 testes, de 45 s a ~2 min
python -m pytest -m "not lento"        # laço rápido, sem a prova de 1 ano de equity
```

A suíte tem duas metades. Em `tests/` estão os testes das funções que doem se quebrarem —
`guarda_risco()`, `_pnl()`, `_preco_liquidacao()`, `abrir()`, o sizing do auto-trader e
`db.metricas()`. A outra metade **embrulha as provas que já estavam versionadas**: o pytest
as executa por subprocesso, cada uma no processo isolado em que ela foi escrita para rodar,
e confere o código de saída e a contagem de asserções.

| Comando | O que prova |
|---|---|
| `python prova_m1.py` | guardas do M1 — `P1-6`, `P1-1`, `P1-7`, `P1-8`, `P2-12` |
| `python test_sim.py` | caminho fim a fim: sinal → posição → fechamento, e liquidação |
| `python simulador.py` | funding do `P2-10` — não medido grava `NULL`, não zero |
| `python db.py prova` | índices, poda e curva de equity do `P2-11` |
| `python api.py` | `_amostrar` (`P1-4`), saúde do scan (`P2-15`), commit no `/health` |
| `python test_auth.py` | `P0-1` — nada é servido sem credencial (3 cenários) |

Cada uma roda sozinha, e é assim que se lê a saída completa quando o pytest acusa falha.

---

## Deploy

VM Ubuntu na Azure + Caddy (TLS automático) + front estático no Vercel.

- **[PLANO-DEPLOY-AZURE.md](PLANO-DEPLOY-AZURE.md)** — plano completo com decisões justificadas
- **[DEPLOY-VERCEL-AZURE.md](DEPLOY-VERCEL-AZURE.md)** — passo a passo operacional
- `deploy/provisionar-azure.sh` — provisionamento via Azure CLI

```bash
bash deploy/provisionar-azure.sh
```

---

## Documentação

| Documento | Conteúdo |
|---|---|
| [NORTE.md](NORTE.md) | **Para onde o projeto aponta**: a direção do dono, os cinco pilares e o estado de cada um, o que não se rediscute. Manda no `CLAUDE.md` quando os dois divergirem |
| [CLAUDE.md](CLAUDE.md) | **Contrato entre sessões de IA**: mapa de módulos, comandos, convenções e os invariantes que não se relaxam sem decisão humana |
| [ARQUITETURA.md](ARQUITETURA.md) | **Como funciona por dentro**: fluxo do worker, ciclo do sinal, esquema do banco, topologia do deploy, decisões com o porquê |
| [BASE-CONHECIMENTO-TRADING.md](BASE-CONHECIMENTO-TRADING.md) | Base teórica: AT, microestrutura, risco/validação, cripto on-chain, o que funciona vs mito |
| [AUDITORIA-SISTEMA.md](AUDITORIA-SISTEMA.md) | Auditoria: 21 bugs + 6 gargalos sistêmicos, com as correções aplicadas |
| [PLANO-REPOS-QUANT.md](PLANO-REPOS-QUANT.md) | Próximos passos de pesquisa (Reality Check, Ornstein-Uhlenbeck, dollar bars) |

---

## Critério de aceite para qualquer estratégia nova

**Antes de qualquer condição, o portão de poder.** A régua calcula o Sharpe anualizado
**mínimo detectável** (MDS, 80% de poder a α = 0,05) para o T que ela tem. Se o MDS passar de
2,0, ela **não emite veredito**: emite `INCONCLUSIVO — instrumento sem poder`. Um instrumento
sem poder responde "não tem edge" tanto quando não tem quanto quando não dá para saber, e as
duas frases são a mesma no relatório — foi o `[Q-1]` que separou as duas. *Ausência de
evidência não é evidência de ausência.*

Passado o portão, uma estratégia só é considerada com edge se **todas** valerem:

1. Validada por walk-forward (nunca split por moeda no mesmo período)
2. Bootstrap **de bloco** IC95% da média/**dia** — série diária agregada, não lista de
   trades — **não inclui 0**
3. **PSR > 0,95** sobre a série OOS (sem deflação: o processo walk-forward não foi escolhido
   como máximo de `n_trials`, e deflacionar ali descontaria duas vezes)
4. White's Reality Check **p ≤ 0,05** sobre a família de configs in-sample
5. Custo **maker** modelado, com o número correto de pernas
6. Sem look-ahead: sinal em candle fechado, execução no open seguinte + slippage
7. Alavancagem **1x** na validação

Falhou em qualquer uma → não tem edge. Documentar e seguir.

Fora do conjunto, e de propósito: o **DSR** (deflacionado por `n_trials`) mede a família de
configs *in-sample* — é diagnóstico de quanto do resultado é artefato de max-de-N, não
decisão; e o **FDR** (Benjamini-Hochberg, q = 0,10) é reportado mas não gateia, porque com 6
configs correlacionadas a ~0,9 ele passa todas ou nenhuma. Uma condição que não pode falhar
independentemente do Reality Check não é uma condição.

---

## Aviso

Não é recomendação de investimento, e nada aqui vale para a carteira de outra pessoa. O
projeto busca vantagem operacional e **ainda não encontrou uma que passe na régua** — enquanto
não passar, trate todo resultado como hipótese a ser refutada, não como sinal para arriscar
dinheiro. É essa a diferença entre o que o projeto quer e o que ele já provou.
