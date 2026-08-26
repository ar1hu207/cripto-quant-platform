# Crypto trading and market-analysis tool

**Where this is headed lives in [NORTE.md](NORTE.md) — read it first.** In one sentence: trade
on its own (day trading, swing trading and portfolio management) and be a market-analysis tool
that consolidates news, momentum, positioning and technicals. **It is meant to be profitable.**

**Today's stage:** paper trading — fictional money, no exchange key, no real order, only public
Binance data through `ccxt`. That is the stage, not the destination: this is the same panel that
will one day touch real money, which is why the risk guards are taken seriously already.

The goal is a **profitable** system — and the ruler (`pesquisa/`) exists so that profit, when it
comes, stands behind evidence instead of luck. It measures strategies with statistical rigor and
**kills the bad ones before they cost real money**. No strategy has passed it yet: the verdict
below is the state of the search, not its goal.

---

## The verdict (the most important result so far)

Every implemented strategy was tested with **walk-forward** (parameters chosen only on the past,
evaluated on the unseen future), **Deflated Sharpe Ratio** and bootstrap:

| Strategy | Verdict | Evidence |
|---|---|---|
| Trend (EMA/ADX/Donchian/RSI) | ❌ no evidence of edge | 3 years, 2,574 OOS trades, 908 days of daily series. Reality Check **p = 0.49** · block bootstrap 95% CI of the daily mean `[−13.1; +15.9]` includes 0 · PSR 0.57 · **DSR = 0.0095** · annualized Sharpe 0.11, 95% CI `[−1.69; +1.34]` |
| Mean reversion (RSI + Bollinger) | ❌ breakeven | Best case +R$73 in-sample / −R$76 OOS over ~1,100 trades |
| Funding arb (cash & carry) | ❌ not deployable | +1.9%/year net; the *gated* version turns negative (four fee legs eat the funding) |

**No deployable edge exists — in what has been implemented so far.** That is neither a failure
nor the destination: it is what is known today, obtained without burning real capital. It is the
floor the search starts from.

> ⚠️ **The "Trend" row above was measured at FIXED 10x leverage; production runs 2x–20x by
> conviction.** `[Q-12]` re-measured the four exit policies under the real configuration on
> 2026-08-25 (`VEREDITO-M4-PRODUCAO-2026-08-25.md`; discussion in
> `INVESTIGACAO-MOTOR-2026-08-24.md` §10). **The verdict does not change** — all four remain
> without evidence of edge and their ordering holds — but the magnitudes do: the policy running
> live (`C trailing 2% fixed`) comes out at **Sharpe 0.976** and **PSR 0.954** in production,
> against 0.645 and 0.854 at fixed 10x, and the 95% CI of the Sharpe `(−0.353 ; 2.074)` **still
> includes zero**. All four policies improved, which locates the gain in **position sizing**, not
> in exit management. Anyone quoting numbers from here must say which configuration they speak
> for.

> ⚠️ **The "Trend" row changed numbers in `[Q-1]`, and the old number was not comparable.** The
> earlier record — *370 trades, PnL −R$807, DSR = 0.004* — came from a ruler with `DIAS = 180`,
> DSR over the **trade list** and `n_trials = 30`. It measured something else, and measured it
> inflated: with 180 days the **minimum detectable annualized Sharpe was ~3.5**, meaning that
> "no edge" was issued by an instrument that **had no power to issue it**. The retroactive run
> with the new instrument is in §6 of
> [`ITEM1-VALIDACAO-RIGOROSA.md`](ITEM1-VALIDACAO-RIGOROSA.md), with the literal output.
>
> **The 3-year OOS P&L came out POSITIVE (+R$993) and the verdict is still negative** — that is
> the instrument working, not a contradiction: 3 positive folds out of 5, and fold 2 alone is
> worth **5.86× the total**. Huge dispersion around zero is the signature of noise.
>
> **And what the test does NOT rule out:** the 95% CI of the annualized Sharpe reaches **+1.34**.
> The data do not refute an edge — they fail to demonstrate one. *Absence of evidence is not
> evidence of absence*, and the new ruler prints that distinction instead of rounding "I could
> not measure" down to "it does not exist". When it cannot even do that, it answers
> `INCONCLUSIVO`. See *Acceptance criteria*.

Two lessons that held across every test:

1. **Fees decide the verdict.** `[Q-15]` (2026-08-26) held the window, the grid and the policy
   fixed and varied *only* the fee: at taker 0.05%/side the same strategy is `no evidence of
   edge` (RC p = 0.141, Sharpe 0.955); at 0% it is **`edge survives`** (RC p = 0.035, PSR 0.996,
   block CI above zero). The signal sits **~0.03%/side away from passing all three gates**, and
   today's fee eats 36% of gross profit. Trade count is identical at every fee level — fees do
   not filter entries, they only shave the P&L afterwards.
2. **Leverage amplifies risk, not edge.** In 100% of backtests, 2x produced worse return *and*
   worse drawdown than 1x.

Both are why validation criterion #5 below requires **maker** cost. The live platform still
charges taker (`taxa_por_lado = 0.0005`), and closing that gap is the current milestone.

---

## Architecture

```
web/index.html ──► FastAPI (api.py) ──► SQLite (WAL)
                        │
                        └── worker (15s): marks positions, closes on stop/liquidation,
                                          scans for signals, records equity
```

The full design — worker flow, signal life cycle, the 7-table schema, deploy topology and the
recorded reason behind each decision, all with `file:line` — is in
**[ARQUITETURA.md](ARQUITETURA.md)**. If you are an AI session, start at
**[CLAUDE.md](CLAUDE.md)**: it is the contract between sessions and carries the invariants that
are never relaxed without a human decision.

### Folder map

Three eras of the project, with an explicit dividing line since `[P2-16]`. Which file you edit
depends on which one you are touching:

| Where | What it is | Rule |
|---|---|---|
| **root** (`*.py`) | **the live platform** — the 11 modules `api.py` reaches, plus the proofs run via `python <file>` | this is what runs on the VM; `deploy/cripto-bot.service` starts `uvicorn api:app` from here, so the platform **never** leaves the root |
| **`pesquisa/`** | **live research** — the ruler that measures strategies (`validacao`, `backtest_plataforma`, `dados`) | a Python package; run it with `python -m pesquisa.<module>` **from the root**. Not production code. `tune` and the `validar_*` scripts left in `[Q-2]` — they issued edge verdicts with superseded methodology |
| **`legado/`** | phases 1-2 — the old engine, `estrategias/`, `config.py`, sweep scripts | **nothing there is imported by the platform, and nothing there still runs where it sits.** Read [`legado/README.md`](legado/README.md) before touching it |
| **`tests/`** | the `pytest` suite | see *Tests* below |
| **`web/`** | static front end (Vercel) | merging into `main` **is** the publish step |
| **`deploy/`** | service unit, Caddyfile and `atualizar.sh` (one-command deploy) | runs on the VM |

**The source of truth for parameters is `db.CONFIG_PADRAO` plus the `config` table**, validated
in `POST /config` — there is no other. `legado/config.py` used to claim the same post with
different values (risk 0.5% vs 3%, leverage 1x vs 10x); `[P2-16]` removed that claim.

### Modules

| File | Role |
|---|---|
| `api.py` | FastAPI backend + background worker + authentication |
| `db.py` | SQLite (positions, trades, signals, equity, config, bankroll) and metrics |
| `scoring.py` | Conviction scoring — **shared** between live and backtest (this sharing *is* the parity) |
| `signal_engine.py` | Live scanning, confirmation gates, exit manager |
| `simulador.py` | Open/close, P&L with leverage/fees/funding, liquidation, risk guard |
| `autotrader.py` | Automatic mode (off by default) |
| `mercado.py` | Order book, taker flow, funding, sentiment |
| `dca.py` | Periodic accumulation, no leverage |
| `pesquisa/validacao.py` | **Walk-forward + Deflated Sharpe + bootstrap** — the ruler that blocks bad ideas |
| `pesquisa/backtest_plataforma.py` | Backtest with parity: signal on the closed candle, execution at the next open |
| `indicadores.py` | EMA, ATR, ADX, RSI, Donchian, Bollinger |

### Risk management (the tripod)
- **Risk-based sizing** — fixed R per trade, sized by ATR
- **Daily lock** — blocks new trades once the day's loss limit is crossed
- **Open-exposure ceiling** — sums the risk-to-stop of every open position

---

## Running locally

```bash
pip install -r requirements.txt
uvicorn api:app --port 8000
```
Panel at <http://localhost:8000>. With no `DASH_PASS` set, the app accepts **local access only**
— an external or proxied request gets a 503.

### Validating a strategy

`pesquisa/` is a package and runs with `-m`, **from the repository root**:

```bash
python -m pesquisa.validacao             # the full ruler (~30 min on the first run)
python -m pesquisa.backtest_plataforma   # backtest with live<->historical parity
python -m pytest tests/test_validacao.py # the ruler's own proofs (7 s, no network)
```

⚠️ **`python -m pesquisa.validacao` takes tens of minutes and is not stuck.** On the first run of
the day it downloads 12 coins × 3 years of 1h candles (~315k candles, paginated with rate
limiting) and caches them under `pesquisa/dados_cache/`; the cache file name **includes the
date**, so yesterday's cache is not reused. After that it is 6 configs × 12 coins of backtest,
twice (the pass with funding and the contrast without it, from `[P2-10]`) — ~13 min each.

`python pesquisa/validacao.py` does **not** work, by construction: running it by path puts
`pesquisa/` on `sys.path` instead of the root, and `import scoring` fails. `scoring.py` and
`indicadores.py` live in the root because they are shared between live and backtest — that
sharing is the parity, and the full reasoning is in `pesquisa/__init__.py`.

---

## Tests

**Run them before every deploy.** The suite does no networking and never touches `trading.db`:
each test uses a temporary database and replaces `preco_ao_vivo`.

```bash
pip install -r requirements-dev.txt
python -m pytest                       # everything — 594 tests, ~2-3 min
python -m pytest -m "not lento"        # fast loop, without the 1-year equity-curve proof
```

The suite has two halves. Under `tests/` are the tests for the functions that hurt when they
break — `guarda_risco()`, `_pnl()`, `_preco_liquidacao()`, `abrir()`, the auto-trader's sizing
and `db.metricas()`. The other half **wraps the proofs that were already versioned**: pytest runs
them as subprocesses, each in the isolated process it was written for, and checks the exit code
and the assertion count.

| Command | What it proves |
|---|---|
| `python prova_m1.py` | M1 guards — `P1-6`, `P1-1`, `P1-7`, `P1-8`, `P2-12` |
| `python test_sim.py` | end-to-end path: signal → position → close, and liquidation |
| `python simulador.py` | `P2-10` funding — unmeasured writes `NULL`, not zero |
| `python db.py prova` | indexes, pruning and the equity curve from `P2-11` |
| `python api.py` | `_amostrar` (`P1-4`), scan health (`P2-15`), commit in `/health` |
| `python test_auth.py` | `P0-1` — nothing is served without credentials (3 scenarios) |

Each one runs standalone, which is how you read the full output when pytest reports a failure.

---

## Deploy

Ubuntu VM on Azure + Caddy (automatic TLS) + static front end on Vercel.

- **[PLANO-DEPLOY-AZURE.md](PLANO-DEPLOY-AZURE.md)** — full plan with justified decisions
- **[DEPLOY-VERCEL-AZURE.md](DEPLOY-VERCEL-AZURE.md)** — operational step by step
- `deploy/provisionar-azure.sh` — provisioning via Azure CLI

```bash
bash deploy/provisionar-azure.sh
```

---

## Documentation

Most documents are written in Portuguese — this README is the English entry point.

| Document | Contents |
|---|---|
| [NORTE.md](NORTE.md) | **Where the project points**: the owner's direction, the five pillars and the state of each, and what is not up for debate. It overrides `CLAUDE.md` when the two disagree |
| [CLAUDE.md](CLAUDE.md) | **Contract between AI sessions**: module map, commands, conventions and the invariants that are never relaxed without a human decision |
| [ARQUITETURA.md](ARQUITETURA.md) | **How it works inside**: worker flow, signal cycle, database schema, deploy topology, decisions with their reasons |
| [BASE-CONHECIMENTO-TRADING.md](BASE-CONHECIMENTO-TRADING.md) | Theory base: technical analysis, microstructure, risk/validation, on-chain crypto, what works vs myth |
| [AUDITORIA-SISTEMA.md](AUDITORIA-SISTEMA.md) | Audit: 21 bugs + 6 systemic bottlenecks, with the fixes applied |
| [PLANO-REPOS-QUANT.md](PLANO-REPOS-QUANT.md) | Next research steps (Reality Check, Ornstein-Uhlenbeck, dollar bars) |

---

## Acceptance criteria for any new strategy

**Before any other condition, the power gate.** The ruler computes the **minimum detectable**
annualized Sharpe (MDS, 80% power at α = 0.05) for the T it has. If the MDS exceeds 2.0 it
**issues no verdict**: it returns `INCONCLUSIVO — instrument without power`. An instrument
without power answers "no edge" both when there is none and when it cannot tell, and the two read
identically in the report — `[Q-1]` separated them. *Absence of evidence is not evidence of
absence.*

Past that gate, a strategy is considered to have an edge only if **all** of these hold:

1. Validated by walk-forward (never a per-coin split within the same period)
2. **Block** bootstrap 95% CI of the **daily** mean — aggregated daily series, not the trade
   list — **excludes 0**
3. **PSR > 0.95** over the OOS series (undeflated: the walk-forward process was not selected as
   the max of `n_trials`, and deflating there would discount twice)
4. White's Reality Check **p ≤ 0.05** over the in-sample family of configs
5. **Maker** cost modeled, with the correct number of legs
6. No look-ahead: signal on the closed candle, execution at the next open plus slippage
7. Leverage **1x** during validation

Fail any one → no edge. Document it and move on.

Deliberately outside the set: the **DSR** (deflated by `n_trials`) measures the *in-sample*
family of configs — it is a diagnostic of how much of the result is a max-of-N artifact, not a
decision; and the **FDR** (Benjamini-Hochberg, q = 0.10) is reported but does not gate, because
with 6 configs correlated at ~0.9 it passes all of them or none. A condition that cannot fail
independently of the Reality Check is not a condition.

---

## Disclaimer

This is not investment advice, and nothing here transfers to anyone else's portfolio. The project
is looking for an operational edge and **has not yet found one that passes the ruler** — until it
does, treat every result as a hypothesis to be refuted, not as a signal to risk money. That is
the difference between what the project is aiming for and what it has already proven.
