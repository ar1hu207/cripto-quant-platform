# `legado/` — fases 1-2 do projeto. Nada aqui roda, e nada aqui é importado.

Este diretório existe para **ser lido**, não para ser executado. Ele guarda o trilho de
pesquisa das fases 1 e 2 (motor de backtest próprio, `estrategias/`, gestão de banca,
scripts de varredura), que foi substituído pelo trilho atual — a plataforma na raiz mais a
régua em `pesquisa/`.

## Duas declarações, e as duas importam

**1. A plataforma viva não importa nada daqui.** Verificado por grafo de imports (AST) sobre
a `main` `5383394`, no `[P2-16]`: o fecho transitivo de `api.py` são exatamente onze módulos
— `alertas`, `api`, `autotrader`, `db`, `dca`, `indicadores`, `logbot`, `mercado`, `scoring`,
`signal_engine`, `simulador` — e todos estão na raiz. Nenhum deles alcança este diretório.
Apagar `legado/` inteiro não muda uma linha do que roda na VM.

**2. Os módulos daqui não são mais executáveis no lugar onde estão.** A quebra é conhecida e
foi aceita, não descoberta depois: `dados.py` era compartilhado entre pesquisa e legado e foi
para `pesquisa/`. Então `legado/monte_carlo.py`, `legado/run_backtest.py`, `legado/validar.py`
e os outros que faziam `import dados` deixam de importar. **Não conserte isso.** Consertar
significaria dar manutenção a um trilho que o projeto já concluiu que não tem edge, e o
`[P2-16]` é movimentação, não ressurreição. Quem precisar rodar um destes tem o git:

```bash
git show 5383394:monte_carlo.py > /tmp/monte_carlo.py   # a versão que rodava, na raiz antiga
```

## `config.py` é o caso que deu nome ao card

`legado/config.py` se declarava *a fonte única da verdade dos parâmetros do sistema* — e era
o config do trilho **legado**, com valores diferentes dos que a plataforma usa de verdade
(risco 0,5% × 3%, alavancagem 1× × 10×). A fonte real é `db.CONFIG_PADRAO` + a tabela
`config` do banco, validada no `POST /config`. O `[P2-16]` mudou o cabeçalho deste arquivo
para dizer o que ele é: dois arquivos disputando a mesma autoridade é o tipo de armadilha que
um humano com memória do projeto desvia e uma sessão de agente sem contexto não.

## O que há aqui

| Grupo | Arquivos |
|---|---|
| Motor de backtest próprio | `motor.py`, `motor_portfolio.py`, `execucao.py`, `estrategia.py`, `gestao_banca.py`, `metricas.py` |
| Estratégias da fase 2 | `estrategias/` (`base`, `trend`, `mean_reversion`) |
| Consumidores de `estrategias/` | `live_engine.py`, `monte_carlo.py`, `otimizar_risco.py`, `run_backtest.py`, `run_portfolio.py`, `run_portfolio_periodos.py`, `validar.py`, `validar_fase2.py`, `validar_periodos_fase2.py` |
| Backtests e estudos avulsos | `backtest.py`, `backtest_funding.py`, `scalp_backtest.py`, `dca_backtest.py`, `experimentos.py`, `funding_estudo.py`, `sweep.py`, `multi_ativo.py`, `scanner.py`, `dashboard.py`, `projecao.py`, `projecao_meta.py`, `teste_dados_gratis.py` |
| Config do trilho legado | `config.py` |
| Deploys mortos | `Procfile` (Railway), `DEPLOY-RAILWAY.md`, `DEPLOY-ORACLE.md` |

## Por que mover e não apagar

Decisão do dono, 2026-08-22, registrada na §4c do `PLANO-EXECUCAO-2026-08-20.md`. O card
recomendava apagar ("o git guarda tudo"); a escolha foi mover, por dois motivos: desfazer a
reorganização vira um `mv` em vez de arqueologia no `git log`, e o M4 (pesquisa) ainda
consegue olhar `backtest.py`, `monte_carlo.py` e `estrategias/` sem sair da árvore. O custo é
que `legado/` fica no repositório até alguém decidir apagá-lo — e essa alternativa continua
disponível a custo zero, porque mover não destrói nada.
