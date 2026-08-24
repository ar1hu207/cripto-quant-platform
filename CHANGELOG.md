# Changelog

Versão em `versao.py` (fonte única) · commit em produção em `GET /health` · o que cada número
significa está documentado no próprio `versao.py`.

**Regra desta casa:** subir a versão e escrever a linha aqui são a mesma ação. O
`tests/test_versao.py` recusa as duas metades separadas — `VERSAO` que não aparece no topo deste
arquivo quebra a suíte, de propósito.

**Aviso honesto sobre o histórico:** o versionamento começa em `0.4.0`. A string `"0.3"` existiu
literal no `api.py` de junho a 24/08/2026 e **nunca se moveu**, atravessando os marcos M1 a M6 —
não há como reconstruir a posteriori quais commits foram "0.1" ou "0.2" sem inventar. As
entradas abaixo de `0.4.0` descrevem o que já estava de pé quando o versionamento passou a
existir, e estão marcadas como tal. O histórico de verdade é o `git log`.

---

## 0.4.0 — 2026-08-24

Versionamento nasce, e o dia da investigação do motor entra no registro.

### Adicionado
- `versao.py` como fonte única de `VERSAO`, e este `CHANGELOG.md`. O `/health` passa a devolver
  a versão da fonte única em vez do literal repetido em três pontos do `api.py`.
- `pesquisa`: `backtest_ativo(sd_min=...)` — piso de distância do stop, portão de custo (`Q-9`).
- `pesquisa`: `backtest_ativo(be_em_R=...)` — stop zero-a-zero disparado em múltiplo de R, com
  motivo de saída próprio `zero-a-zero` (`Q-11`).
- `pesquisa`: `backtest_ativo(lev_modo="conviccao")` — alavancagem por convicção com o cap
  geométrico do `P1-11`, transcrita do `autotrader` e presa por teste de pinagem (`Q-10`).
- `pesquisa`: `python -m pesquisa.validacao geometria` e `... zeroazero` — as duas varreduras,
  com `k` e `sd_min` escolhidos **dentro do fold de treino** e não no rótulo da rodada.

### Medido (nenhuma mudança de comportamento em produção)
- **`k×ATR` no trailing:** varredura de 96 configs, `n_trials=550`. `SEM EVIDÊNCIA DE EDGE`, e o
  treino escolheu `k=4,0` — **teto da grade**, boundary hit. A pergunta do `k` foi movida, não
  resolvida. Não troca o default.
- **Piso de custo (`sd_min`):** o treino escolheu `0%` em 4 dos 5 folds. Hipótese nula
  sobreviveu.
- **Stop zero-a-zero (`be_em_R`):** reprovado. Quanto mais a guarda age, pior — `0,5R` armou
  5.737 vezes e perdeu R$2.761 contra o sem-guarda; o braço vencedor armou 138 vezes em 34.033
  trades.
- **A régua media 10x fixo; a produção roda 2x–20x por convicção.** Corrigido o objeto, Sharpe
  0,645 → 0,976 e PSR 0,854 → 0,954 — e mesmo assim `SEM EVIDÊNCIA DE EDGE` (o IC do Sharpe
  ainda inclui o zero, RC p = 0,1404). Ver `Q-12`: o veredito publicado descreve uma
  configuração que ninguém executa.

### Documentado
- `INVESTIGACAO-MOTOR-2026-08-24.md` (§1–§9) e as saídas literais das três rodadas em
  `VARREDURA-GEOMETRIA-2026-08-24.md` e `MEDICAO-ZERO-A-ZERO-2026-08-24.md`.

### Defeitos abertos e registrados (não corrigidos nesta versão)
- Trailing em % de preço contra stop em ATR — na faixa `sd` 1–2% o trade não tem ramo vencedor.
- Trailing só arma em +2% de **preço**, e em ROE isso escala com a alavancagem (40% a 20x).
- `auto_max_valor_frac` desliga o alvo de risco em silêncio (risco realizado varia ~600×).
- `ret_pct` gravado bruto enquanto `pnl_reais` é líquido.

---

## 0.3 e anteriores — até 2026-08-23 *(reconstrução declarada, não histórico)*

Não versionado na época. O que estava de pé quando o versionamento nasceu: plataforma de paper
trading com worker 24/7, auto-trader dentro de guardas (trava diária sticky, tetos de risco e
margem, claim atômico de sinal, geometria stop×liquidação), backend na VM Azure como repositório
git com deploy por `cripto-deploy` e backup diário, painel no Vercel sem script de terceiro, a
régua de pesquisa (walk-forward + DSR + bootstrap + controle nulo) e o `VEREDITO-M4.md`.

Para saber o que mudou nesse período: `git log`.
