# CLAUDE.md — cripto-quant-platform

Plataforma de **paper trading** de cripto: dinheiro fictício, preço real da Binance. Um worker
FastAPI varre o mercado 24/7, propõe trades, e um auto-trader opcional abre e fecha sozinho.
Projeto AI-first: o desenvolvimento é feito por sessões de agente, e este arquivo é o contrato
entre elas. Cada regra aqui nasceu de um erro real — as datas dizem quando doeu.

**Produção:** backend na VM Azure `vm-cripto-bot` (southafricanorth,
`cripto-bot-24517.southafricanorth.cloudapp.azure.com`) · front no Vercel
(`cripto-quant-dashboard.vercel.app`) · banco SQLite `trading.db` **na VM** — o local está vazio.

---

## 1. Convenções que não se deduzem do código

- **Timestamps naive em hora de São Paulo** (`pd.Timestamp.now()`, sem fuso). Não converta, não
  "conserte" para UTC — o banco inteiro está assim e comparações mistas quebram em silêncio.
- **Config vive no banco** (`db.CONFIG_PADRAO` + tabela `config`), validada por catálogo no
  `POST /config`. O `config.py` (dataclass) é **legado** — não o use; morre no `P2-16`.
- **Nunca `cp` do `trading.db` vivo** — o bot escreve a cada ciclo. Cópia íntegra é
  `sqlite3 trading.db ".backup '...'"`, sempre seguida de `PRAGMA integrity_check`.
- **Dinheiro é fictício, preço é real.** Isso não relaxa nada: o histórico de pesquisa é perda
  real se corromper, e o painel é o mesmo que um dia encosta em dinheiro de verdade.

## 2. Invariantes de risco — nunca relaxar sem decisão humana registrada

Cards com a label `toca-risco` no Trello não fecham sem humano assinando. Auditor automático
roda os portões e **para** (§9.8 do plano). Guardas em produção hoje:

- **Trava diária** (sticky): compara o equity de agora com o do **início do dia** — não com o
  P&L realizado. Dia pode fechar com trades positivos e a trava disparada (aconteceu em
  22/08: +34,68 realizados, trava por −80,34 de equity). Não solta no mesmo dia; solta na
  virada. Limpar `trava_dia_em` à mão = relaxar invariante.
- **Claim atômico do sinal** (`P1-6`): `UPDATE ... WHERE status='novo'` com rowcount na mesma
  transação do INSERT. Os tetos de risco e margem levantam **antes** do claim, de propósito —
  recusa por teto não pode consumir o sinal. Não inverta essa ordem.
- **Marcação por posição** (`P1-1`): o try/except do ciclo é **por posição**, nunca em volta do
  `for`. Em volta do `for` "funciona" e deixa toda posição após a primeira falha sem stop.
- **Pânico mata a fonte primeiro** (`P1-7`): `/panico` grava `auto_trade=0` **antes** de fechar.

Apertar guarda pode. Afrouxar, só o dono.

## 3. Git e commits

- **Identidade:** `ar1hu207 <88159256+ar1hu207@users.noreply.github.com>` (já no `.git/config`,
  vale nas worktrees). O e-mail pessoal sobe mas fica `NAO ATRIBUIDO` no GitHub. Há **duas**
  contas gh autenticadas nesta máquina — o noreply acima é só da `ar1hu207`.
- **Mensagem de commit registra o raciocínio:** a causa (não o sintoma), por que a correção
  ataca a causa, e **como seria a versão-sintoma que você não fez**. É o que permite auditar
  por diff em vez de acreditar em relato. Commit sem isso é reprovado (§9.5).
- **Um commit por card.** Diff estreito: não reformate nem "aproveite para arrumar" o que está
  perto — cada linha fora do necessário é conflito que outro resolve sem saber sua intenção.
- ⚠️ **A `main` local fica velha.** Push de worktree (`git push origin HEAD:main`) nunca a
  adianta — ela chegou a ficar 27 commits atrás em 22/08. Antes de criar worktree ou branch:
  `git fetch origin main:main` e confira `rev-list --count main..origin/main` = 0.

## 4. Trello (quadro "Trading Bot")

- **Chave canônica de um card é o shortLink** (`trello.com/c/XXXX`), **nunca** o `[P2-n]` do
  título. A numeração colidiu duas vezes num só dia (21-22/08); o shortLink não muda.
- **Fluxo novo nasce com prefixo próprio** (quant = `Q-`). `P2-` é sequência compartilhada e
  duas sessões numerando em paralelo colidem sempre — não há lock no quadro.
- **Worker não cria, não renumera, não renomeia card** — pede, e a sessão-matriz cria.
  Alocação de número tem um escritor só (§9.6b).
- Listas = **estado** (Triagem → Priorizado → Fazendo → Validando → Feito → Bloqueado).
  Marcos = **labels** (`M1`…). Worker move Triagem→Fazendo (é o lock); **só o auditor tira de
  Fazendo** — inclusive para devolver (§9.6).
- Card fechado = commit + critério de aceite **rodado, com a saída colada** no card. Efeito
  observável em produção passa por 🔍 Validando antes de ✅ Feito.

## 5. Produção: deploy, acesso e backup

- **A VM não é repositório git** (`P2-3` aberto). Deploy é cópia manual; **commit na `main`
  não significa código rodando**. Rollback só existe se você criar antes (`cp *.py` para
  `/home/ubuntu/rollback-<stamp>/`).
- **SSH quase sempre falha**: o NSG libera 1 IP e o do dono é dinâmico. Não conserte a regra
  (bloqueado, ver §8). O caminho é `az vm run-command invoke ... --scripts @arquivo.sh`.
  Três armadilhas: script inline com aspas aninhadas quebra no meio (**sempre `@arquivo`**);
  a saída trunca em 4.095 chars; uma execução por vez (`Conflict` se sobrepor).
- **Procedimento de deploy que funcionou (22/08):** backup → snapshot p/ rollback → md5 antes →
  `auto_trade=0` + zero posições abertas → staging em `/tmp` com sha256 + `py_compile` no venv
  de produção → troca + restart → verificar (serviço, integrity, contagens, journal, equity
  nova) → só então `auto_trade=1`.
- **Backup diário existe**: cron 03:17 na VM → Azure Blob (`criptobotbkp28836/trading-db`),
  empurrando de **dentro para fora**. O SAS em `/etc/cripto-bot-backup.sas` é write-only e
  **expira em 2027-08-22** — precisa de rotação antes.
- **Front publica sozinho**: merge na `main` → Vercel. Para `web/`, o merge **é** a publicação.

## 6. Trabalho paralelo entre sessões

Regras completas: `PLANO-EXECUCAO-2026-08-20.md` (§3, §4, §9) e `ORQUESTRACAO-ORCA.md`.
O essencial:

- **A unidade de despacho é o território de arquivo, não o card** — `api.py` é citado por 10
  cards; um agente por card seria colisão garantida.
- **Worktree por território, base `origin/main` explícita, SHA registrado no card.** Nunca
  branche do HEAD do checkout compartilhado — costuma haver 7-8 sessões do dono lá dentro.
- **Matriz despacha e integra; worker coda e para.** Worker não faz push, não mergeia, não
  toca no Trello, não acessa a VM. O briefing **transcreve** o plano, nunca acrescenta —
  território que só existe no briefing é inauditável (§9.2, caso real do `Q-4`).
- **Paralelismo é dentro do marco, nunca entre marcos** — o mapa de territórios não vale
  entre eles (§9.2). E território particiona *arquivo*: esquema de banco, numeração e
  produção continuam compartilhados — serialize (§9.2b).
- **Colheita é git, não relato:** `git diff --name-only <SHA-base>...<branch>` cruzado com a
  lista da §4. Arquivo fora do território reprova mesmo com código bom.
- Antes de mergear M1+ na `main`: rode `python prova_m1.py` (7 asserções das guardas, banco
  temporário, sem rede). O `test_sim.py` **não roda** localmente — depende do banco da VM.

## 7. Verificação: o padrão desta casa

"Validado" sem comando rodado não conta. O que fecha card é **saída literal colada**. Não
confie em relato de agente (nem no seu de ontem): leia o diff, rode o comando, confira o hash.
Exemplos do padrão: front verificado por hash do HTML em produção vs `main`; backup por sha256
VM vs local; deploy por md5 antes/depois + journal + equity nova.

## 8. Fronteiras do classificador de permissões — não insista

Bloqueado por design, e pedir ao dono é o caminho: editar `settings.json` de permissões ·
alterar regra de NSG · `az role assignment create` (a assinatura Students recusa mesmo Owner) ·
lançar `nohup claude -p` sem regra de allow. Todas são a mesma família: **agente ampliando o
próprio alcance**. Uma sessão queimou seis tentativas nisso em 22/08; vá direto à alternativa.

## 9. Mapa de documentos

| Doc | Para quê |
|---|---|
| `PLANO-EXECUCAO-2026-08-20.md` | **o plano vivo**: marcos, territórios, ondas, portões (§9) |
| `ORQUESTRACAO-ORCA.md` | despachar sessões (Orca + fallback manual) e operar o Trello pela API |
| `RUNBOOK-VM.md` | **operar a VM**: acesso, transferências, deploy, backup, diagnóstico — a versão completa do §5 |
| `prova_m1.py` | prova funcional das guardas — rode antes de mergear backend |
| `DESIGN.md` | direção visual do front (transposição CoinMarketCap night) |
| `STATUS-SISTEMA-2026-08-19.md` + `INVESTIGACAO-*.md` | origem dos cards; registros datados |
| `DEPLOY-AZURE.md` | roteiro de provisionamento (⚠️ descreve SSH; ver §5 acima) |
| `PLANO-SPRINTS.md`, `PLANO-DEV-*.md`, `AUDITORIA-*.md` | históricos da fase de construção |

*ARQUITETURA.md ainda não existe (`P2-17`, pendente da reorganização do `P2-16`).*
