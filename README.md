# Plataforma de Pesquisa Quant + Paper Trading (cripto)

Sistema de **paper trading** e validação de estratégias em cripto. Dinheiro fictício, sem chave
de exchange, sem ordem real — só dados públicos da Binance via `ccxt`.

O objetivo do projeto **não é** um robô lucrativo. É um instrumento honesto: um framework que
mede estratégias com rigor estatístico e **mata as ruins antes que elas custem dinheiro real**.

---

## O veredito (o resultado mais importante do projeto)

Todas as estratégias implementadas foram testadas com **walk-forward** (parâmetros escolhidos
só no passado, avaliados no futuro não-visto), **Deflated Sharpe Ratio** e bootstrap:

| Estratégia | Veredito | Evidência |
|---|---|---|
| Tendência (EMA/ADX/Donchian/RSI) | ❌ sem edge | 370 trades OOS, win 25,4%, PnL −R$807, IC95% [−7,4; +3,5] inclui 0, **DSR = 0,004** |
| Reversão à média (RSI + Bollinger) | ❌ breakeven | Melhor caso +R$73 in-sample / −R$76 OOS em ~1100 trades |
| Funding arb (cash & carry) | ❌ não-deployável | +1,9%/ano líquido; versão *gated* fica negativa (4 pernas de taxa comem o funding) |

**Não existe edge deployável.** Isso não é fracasso — é o resultado com maior valor econômico
do projeto, obtido sem torrar banca real. Duas lições que se sustentaram em todos os testes:

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

### Mapa de pastas

Três eras do projeto, e a divisória é explícita desde o `[P2-16]`. Qual arquivo você edita
depende de qual destas você está tocando:

| Onde | O que é | Regra |
|---|---|---|
| **raiz** (`*.py`) | **plataforma viva** — os 11 módulos que o `api.py` alcança, mais as provas que se rodam por `python <arquivo>` | é o que roda na VM; o `deploy/cripto-bot.service` sobe `uvicorn api:app` daqui, e por isso a plataforma **não** sai da raiz |
| **`pesquisa/`** | **pesquisa viva** — a régua que mede estratégia (`validacao`, `backtest_plataforma`, `tune`, `dados`, `validar_*`) | pacote Python; roda por `python -m pesquisa.<modulo>` **da raiz**. Não é código de produção |
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
python -m pesquisa.validacao             # walk-forward + DSR + bootstrap
python -m pesquisa.backtest_plataforma   # backtest com paridade live<->histórico
```

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
| [BASE-CONHECIMENTO-TRADING.md](BASE-CONHECIMENTO-TRADING.md) | Base teórica: AT, microestrutura, risco/validação, cripto on-chain, o que funciona vs mito |
| [AUDITORIA-SISTEMA.md](AUDITORIA-SISTEMA.md) | Auditoria: 21 bugs + 6 gargalos sistêmicos, com as correções aplicadas |
| [PLANO-REPOS-QUANT.md](PLANO-REPOS-QUANT.md) | Próximos passos de pesquisa (Reality Check, Ornstein-Uhlenbeck, dollar bars) |

---

## Critério de aceite para qualquer estratégia nova

Uma estratégia só é considerada com edge se **todas** as condições valerem:

1. Validada por walk-forward (nunca split por moeda no mesmo período)
2. Bootstrap de bloco IC95% da média/trade **não inclui 0**
3. **DSR > 0,95** com `n_trials` contando as tentativas honestamente
4. White's Reality Check **p ≤ 0,05**
5. Ao menos uma config sobrevive ao **FDR** (Benjamini-Hochberg, q = 0,10)
6. Custo **maker** modelado, com o número correto de pernas
7. Sem look-ahead: sinal em candle fechado, execução no open seguinte + slippage
8. Alavancagem **1x** na validação

Falhou em qualquer uma → não tem edge. Documentar e seguir.

---

## Aviso

Software de pesquisa e educação. Não é recomendação de investimento. O próprio projeto
concluiu, com dados, que não encontrou vantagem operacional — trate qualquer resultado aqui
como hipótese a ser refutada, não como sinal para arriscar dinheiro.
