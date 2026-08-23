# CLAUDE.md — cripto-quant-platform

Plataforma de **paper trading** de cripto: dinheiro fictício, preço real da Binance. Um worker
FastAPI varre o mercado 24/7, propõe trades, e um auto-trader opcional abre e fecha sozinho.
Projeto AI-first: o desenvolvimento é feito por sessões de agente, e este arquivo é o contrato
entre elas. Cada regra aqui nasceu de um erro real — as datas dizem quando doeu.

**Honestidade é premissa, não bug a consertar.** O walk-forward + DSR já concluiu que **não
existe edge deployável** (tendência: 370 trades OOS, **DSR = 0,004**; ver `README.md`), e o
auto-trader existe para *ver o "no edge" acontecer ao vivo dentro de guardas*, não para ganhar
dinheiro (`autotrader.py:8-13`). Não "melhore" o resultado ruim: ele é o produto.

**Produção:** backend na VM Azure `vm-cripto-bot` (southafricanorth,
`cripto-bot-24517.southafricanorth.cloudapp.azure.com`) · front no Vercel
(`cripto-quant-dashboard.vercel.app`) · banco SQLite `trading.db` **na VM** — o local está vazio.
Como o sistema funciona por dentro, com `arquivo:linha`: **`ARQUITETURA.md`**.

---

## 0. O mapa e os comandos

Três eras, e a divisória decide qual arquivo você edita (`P2-16`). **raiz** (`*.py`) =
plataforma viva, o que roda na VM — e **não sai da raiz**, porque o `deploy/cripto-bot.service`
sobe `uvicorn api:app` com `WorkingDirectory` nela e o `deploy/atualizar.sh` compila `./*.py`
(glob de raiz, não recursivo). **`pesquisa/`** = a régua, pacote que roda por `-m` **da raiz**.
**`legado/`** = fases 1-2: nada ali é importado pela plataforma e **nada ali roda onde está**,
de propósito — não conserte esses imports (`legado/README.md`).

| Módulo | Papel |
|---|---|
| `api.py` | FastAPI (31 rotas) + worker em thread no `lifespan` + auth por middleware + catálogo do `POST /config` |
| `db.py` | SQLite: 7 tabelas, `CONFIG_PADRAO`, índices, retenção da equity, `metricas()` |
| `simulador.py` | abrir/fechar, P&L com taxa e funding, liquidação, trailing e **`guarda_risco()`** |
| `signal_engine.py` | varredura, portões de confirmação, dedupe/expiração, gestor de saída |
| `scoring.py` | pontuação de convicção — **compartilhada com a pesquisa: é a paridade**, não duplique |
| `indicadores.py` | EMA, ATR, ADX, RSI, Donchian, Bollinger — também compartilhado |
| `mercado.py` | book, fluxo taker, funding, sentimento (1 request por lista, cache de 5s por ativo) |
| `autotrader.py` | modo automático (config `auto_trade`, desligado por padrão) |
| `dca.py` | acumulação periódica, sem alavancagem, banca conceitualmente separada |
| `alertas.py` | Telegram **opcional**: sem token na config é no-op |
| `logbot.py` | `from logbot import log` → grava em **`plataforma.log`** (10 MB × 5, teto no código) |
| `pesquisa/validacao.py` | walk-forward + DSR + bootstrap — a régua que barra ideia ruim |

```bash
pip install -r requirements.txt && uvicorn api:app --port 8000  # local; painel em :8000
pip install -r requirements-dev.txt
python -m pytest                    # 532 passed (~3 min) — rode antes de mergear
python -m pytest -m "not lento"     # laço rápido, sem a prova de 1 ano de curva de equity
python -m pesquisa.validacao        # a régua (da RAIZ; `python pesquisa/validacao.py` NÃO roda)
python -c "import api"              # smoke da plataforma
cripto-deploy                       # deploy na VM; rollback: bash deploy/atualizar.sh <sha>
```
Logs da VM: `journalctl -u cripto-bot -n 50 --no-pager`, por `az vm run-command` (§5).

## 1. Convenções que não se deduzem do código

- **Timestamps naive em hora de São Paulo** (`pd.Timestamp.now()`, sem fuso). Não converta, não
  "conserte" para UTC — o banco inteiro está assim e comparações mistas quebram em silêncio.
- **Config vive no banco** (`db.CONFIG_PADRAO` + tabela `config`), validada por catálogo no
  `POST /config` — `risco_por_trade`, `alavancagem_padrao`, `limite_perda_dia`, `auto_trade` e
  o resto. Código de plataforma lê do banco, **nunca constante literal no módulo**.
  O antigo `config.py` (dataclass) reivindicava o mesmo posto com valores diferentes; o `P2-16`
  o mandou para `legado/config.py` e tirou a reivindicação. **Não existe segunda fonte.**
- **Nunca `cp` do `trading.db` vivo** — o bot escreve a cada ciclo. Cópia íntegra é
  `sqlite3 trading.db ".backup '...'"`, sempre seguida de `PRAGMA integrity_check`.
- **Dinheiro é fictício, preço é real.** Isso não relaxa nada: o histórico de pesquisa é perda
  real se corromper, e o painel é o mesmo que um dia encosta em dinheiro de verdade.

## 2. Invariantes — nunca relaxar sem decisão humana registrada

Cards com a label `toca-risco` não fecham sem humano assinando; auditor automático roda os
portões e **para** (§9.8 do plano). O que está em produção hoje:

- **Trava diária** (sticky): compara o equity de agora com o do **início do dia** — não com o
  P&L realizado. Dia pode fechar com trades positivos e a trava disparada (22/08: +34,68
  realizados, trava por −80,34 de equity). Não solta no mesmo dia, solta na virada. Limpar
  `trava_dia_em` à mão = relaxar invariante.
- **Claim atômico do sinal** (`P1-6`): `UPDATE ... WHERE status='novo'` com rowcount na mesma
  transação do INSERT. Os tetos de risco e margem levantam **antes** do claim, de propósito —
  recusa por teto não pode consumir o sinal. Não inverta essa ordem.
- **Marcação por posição** (`P1-1`): o try/except do ciclo é **por posição**, nunca em volta do
  `for`. Em volta do `for` "funciona" e deixa toda posição após a primeira falha sem stop.
- **Pânico mata a fonte primeiro** (`P1-7`): `/panico` grava `auto_trade=0` **antes** de fechar.
- **Sem `DASH_PASS` o backend recusa acesso externo, e não há bandeira para desligar isso.**
  Existiu uma (`PERMITIR_SEM_SENHA`) e foi ela que deixou `/reset`, `/panico`, `/config` e
  `/auto` abertos na internet: a guarda só protege se não houver como desligá-la.
- **O `web/` não carrega script de terceiro.** Chart.js e Lightweight-Charts estão
  **commitadas** em `web/vendor/`, carregadas por caminho relativo. A credencial do painel vive
  no `localStorage`, e script de CDN no mesmo documento a lê — não troque `vendor/` por CDN
  "para atualizar a versão". Confere em um segundo: `grep -rn "src=['\"]http" web/` é vazio.
  Única exceção, declarada no HTML: a stylesheet do Google Fonts, que não executa JS.
- **A franquia de saída da Azure é 15 GB/mês, e ela molda o `/estado`.** Com o painel em poll
  de 3s, o tamanho da resposta é decisão de arquitetura: a curva de equity sozinha era 72% do
  payload (51 KB de 71 KB) antes do `_amostrar` (`api.py:539-541`). Quem engorda o `/estado`
  gasta franquia continuamente — pague com amostragem, ou com outra rota.

Apertar guarda pode. Afrouxar, só o dono.

## 3. Git e commits

- **Identidade:** `ar1hu207 <88159256+ar1hu207@users.noreply.github.com>` (já no `.git/config`,
  vale nas worktrees). O e-mail pessoal sobe mas fica `NAO ATRIBUIDO`, e há **duas** contas gh
  nesta máquina — o noreply acima é só da `ar1hu207`.
- **A mensagem de commit registra o raciocínio:** a causa (não o sintoma), por que a correção
  ataca a causa, e **como seria a versão-sintoma que você não fez**. É o que permite auditar por
  diff em vez de acreditar em relato. Commit sem isso é reprovado (§9.5).
- **Um commit por card**, diff estreito: não reformate nem "aproveite para arrumar" o que está
  perto — cada linha a mais é conflito que outro resolve sem saber sua intenção.
- ⚠️ **A `main` local fica velha** (27 commits atrás em 22/08) e push de worktree nunca a
  adianta. Antes de criar worktree: `git fetch origin main:main`, e
  `rev-list --count main..origin/main` = 0.

## 4. Trello (quadro "Trading Bot")

- **Chave canônica de um card é o shortLink** (`trello.com/c/XXXX`), **nunca** o `[P2-n]` do
  título: a numeração colidiu duas vezes num só dia (21-22/08), o shortLink não muda. Fluxo novo
  nasce com prefixo próprio (quant = `Q-`); `P2-` é sequência compartilhada e duas sessões
  numerando em paralelo colidem sempre. **Worker não cria, não renumera, não renomeia card**:
  pede, e a matriz cria — alocação de número tem um escritor só (§9.6b).
- Listas = **estado** (Triagem → Priorizado → Fazendo → Validando → Feito → Bloqueado); marcos =
  **labels**. Worker move Triagem→Fazendo (é o lock); **só o auditor tira de Fazendo**, inclusive
  para devolver (§9.6).
- Card fechado = commit + critério de aceite **rodado, com a saída colada** no card. Efeito
  observável em produção passa por 🔍 Validando antes de ✅ Feito.

## 5. Produção: deploy, acesso e backup

Versão completa: `RUNBOOK-VM.md`. Topologia e o porquê: `ARQUITETURA.md` §8.

- **A VM É repositório git desde 2026-08-22** (`P2-3`), privada, por deploy key SSH read-only.
  Deploy é `cripto-deploy`, que aborta em cada portão (árvore suja, backup falho, `py_compile`)
  e **não religa o `auto_trade`** — religar sozinho seria o script decidindo por você que está
  tudo bem. `/health` devolve o commit rodando; rollback é `bash deploy/atualizar.sh <sha>`.
  **Commit na `main` ainda não significa código rodando**: o deploy é ato deliberado.
- **Nunca deploye copiando arquivo de uma árvore Windows.** Foi assim no M1 e os quatro `.py`
  chegaram em CRLF: rodam igual, mas o md5 deixa de bater justamente nos arquivos que o deploy
  toca (o `.gitattributes` normaliza em checkout, não em `tar`). O caminho é `git checkout`.
- **SSH quase sempre falha**: o NSG libera 1 IP e o do dono é dinâmico. Não conserte a regra
  (bloqueado, §8) — use `az vm run-command invoke ... --scripts @arquivo.sh`. Três armadilhas:
  aspas aninhadas em script inline quebram no meio (**sempre `@arquivo`**); a saída trunca em
  4.095 chars; uma execução por vez (`Conflict` se sobrepor).
- **Backup diário**: cron 03:17 → Azure Blob, de **dentro para fora**. O SAS em
  `/etc/cripto-bot-backup.sas` é write-only e **expira em 2027-08-22** — rotacione antes.
- **Front publica sozinho**: merge na `main` → Vercel. Para `web/`, o merge **é** a publicação.

## 6. Trabalho paralelo entre sessões

Regras completas em `PLANO-EXECUCAO-2026-08-20.md` (§3, §4, §9) e `ORQUESTRACAO-ORCA.md`:

- **A unidade de despacho é o território de arquivo, não o card** — `api.py` é citado por 10
  cards; um agente por card seria colisão garantida. Worktree por território, base `origin/main`
  explícita, SHA no card; nunca branche do HEAD do checkout compartilhado.
- **Matriz despacha e integra; worker coda e para.** Worker não faz push, não mergeia, não toca
  no Trello, não acessa a VM. O briefing **transcreve** o plano, nunca acrescenta — território
  que só existe no briefing é inauditável (§9.2).
- **Paralelismo é dentro do marco, nunca entre marcos** (§9.2). E território particiona
  *arquivo*: esquema de banco, numeração e produção seguem compartilhados — serialize (§9.2b).
- **Colheita é git, não relato:** `git diff --name-only <SHA-base>...<branch>` cruzado com a
  lista de territórios **do plano** (§4 dele, não desta página). Arquivo fora do território
  reprova mesmo com código bom.
- **Antes de mergear, `python -m pytest`** (§0). Ela exige que o repositório seja um **checkout
  git** (a prova do `/health` roda `git rev-parse`) — audite com `git worktree add --detach`,
  nunca com cópia. E `prova_m1.py`, `test_sim.py` e `test_auth.py` **não saem da raiz**: é por
  caminho que a suíte os chama.
- **`xfail(strict=True)` aqui é card em aberto, não teste quebrado** (hoje:
  `tests/test_metricas.py`, defeito latente do `P2-36`). Quando o card fechar ele vira XPASS e
  **quebra a suíte** de propósito, obrigando a promover o teste. Não o "limpe" — vá ao card.

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
| `ARQUITETURA.md` | **como funciona por dentro**: fluxo do worker, esquema, topologia, decisões com o porquê |
| `README.md` | o que o projeto é, o veredito de pesquisa, rodar/testar/validar |
| `PLANO-EXECUCAO-2026-08-20.md` | **o plano vivo**: marcos, territórios, ondas, portões (§9) |
| `ORQUESTRACAO-ORCA.md` | despachar sessões (Orca + fallback manual) e operar o Trello pela API |
| `RUNBOOK-VM.md` | **operar a VM**: acesso, transferências, deploy, backup, diagnóstico (§5 completo) |
| `legado/README.md` · `pesquisa/__init__.py` | o que cada território é, e por que ele é assim |
| `DESIGN.md` | direção visual do front (transposição CoinMarketCap night) |
| `STATUS-SISTEMA-*.md`, `INVESTIGACAO-*.md`, `AUDITORIA-*.md`, `PLANO-SPRINTS.md`, `PLANO-DEV-*.md` | **histórico datado**: origem dos cards e a fase de construção. É aqui que mora o que não é regra |
| `DEPLOY-AZURE.md` | roteiro de provisionamento (⚠️ descreve SSH; ver §5 acima) |
