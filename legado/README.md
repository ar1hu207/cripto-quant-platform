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

⚠️ **Mas essa segunda declaração é acidente, não garantia — e o `[Q-2]` descobriu isso na
prática.** Os módulos do `[P2-16]` não rodam porque um `import` quebrou, não porque estejam
neste diretório. `legado/` não tem `__init__.py`, então ele vira *namespace package* e
`python -m legado.<modulo>` **da raiz** funciona: a raiz está no `sys.path`, `import pesquisa`
resolve, e o módulo executa. Foi exatamente o que aconteceu com os cinco do `[Q-2]` logo
depois do `git mv` — `python -m legado.tune` imprimiu a varredura inteira. Por isso os cinco
levaram uma recusa **escrita** (`raise SystemExit` com o motivo e o `git show` da versão que
rodava), em vez de depender de um import quebrar por sorte.

## Os cinco do `[Q-2]` — vereditos de edge por metodologia superada

Chegaram em 2026-08-23, vindos de `pesquisa/`. O que eles têm em comum não é a idade: é que os
cinco **imprimiam veredito de edge** (`POSITIVO`, `ROBUSTO`, `edge ROBUSTO ✅`) por uma
metodologia que o próprio `pesquisa/validacao.py` já declarava desonesta no docstring dele.

| Arquivo | O veredito que imprimia | O vício |
|---|---|---|
| `tune.py` | `<<< POSITIVO`, `MELHORES CONFIGS (positivas)` | varre TF × lev × corte no período **inteiro** caçando P&L positivo — escolher a config no mesmo dado em que ela é medida |
| `validar_oos.py` | `>>> POSITIVO → edge ROBUSTO (não foi só sorte) ✅` | "moedas novas" no **mesmo período**: cripto é correlacionada, então as novas andam com as antigas |
| `validar_reversao.py` | `<- ROBUSTO` | split-por-moedas no mesmo período, corte escolhido olhando o OOS |
| `validar_reversao_maker.py` | `<- ROBUSTO` | idem, com matriz maker/taker × 15m/1h — o custo muda, o vício não |
| `validar_swing.py` | `ROBUSTO ✅` | idem; o docstring dele já dizia *"acha o melhor corte ROBUSTO (positivo nos dois) pra virar o default"*, que é escolher parâmetro olhando o resultado |

**Por que aposentar e não consertar.** Não há o que consertar: o veredito honesto exige
walk-forward (parâmetro escolhido só no passado) e desconto de multiple-testing, e isso já
existe em `pesquisa/validacao.py`. Reescrever os cinco como wrappers da régua nova (a
preferência 2 do card) seria manter cinco portas de entrada para uma pergunta que tem uma
resposta só.

**Por que isso é mais grave do que parece.** O projeto é AI-first: o desenvolvimento é feito
por sessões de agente sem memória. Uma sessão futura roda `tune.py`, acha uma config
"positiva", lê o `✅ edge ROBUSTO` do `validar_oos.py` e calibra a plataforma com ruído —
desfazendo em silêncio a disciplina estatística que é o principal ativo do projeto. A
armadilha estava armada **e tinha aparência de ferramenta oficial**, dentro do pacote de
pesquisa viva.

**O que eles ainda valem, e é por isso que não foram apagados.** São tentativas gastas: cada
varredura daquelas é `n_trials` que a régua nova precisa descontar. A revisão do Item 1 conta
`tune.py` = 18 configs, `sweep.py` = 9, `experimentos.py` = 18, e é dali que sai o
`n_trials = 100` como **piso contado** em `pesquisa/validacao.py`. Apagar o código apagaria a
contagem.

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
| Vereditos de edge aposentados (`[Q-2]`, 2026-08-23) | `tune.py`, `validar_oos.py`, `validar_reversao.py`, `validar_reversao_maker.py`, `validar_swing.py` — **recusam-se a rodar**, ver a seção acima |
| Deploys mortos | `Procfile` (Railway), `DEPLOY-RAILWAY.md`, `DEPLOY-ORACLE.md` |

## Por que mover e não apagar

Decisão do dono, 2026-08-22, registrada na §4c do `PLANO-EXECUCAO-2026-08-20.md`. O card
recomendava apagar ("o git guarda tudo"); a escolha foi mover, por dois motivos: desfazer a
reorganização vira um `mv` em vez de arqueologia no `git log`, e o M4 (pesquisa) ainda
consegue olhar `backtest.py`, `monte_carlo.py` e `estrategias/` sem sair da árvore. O custo é
que `legado/` fica no repositório até alguém decidir apagá-lo — e essa alternativa continua
disponível a custo zero, porque mover não destrói nada.
