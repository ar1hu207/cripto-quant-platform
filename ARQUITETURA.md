# ARQUITETURA.md — como o sistema funciona, e por quê

Companheiro do `CLAUDE.md`. Lá estão as **regras** (o que não mudar); aqui está a **forma** (o
que existe, como se encaixa, e a razão registrada de cada escolha). Leia este quando for mexer
em algo; leia o `CLAUDE.md` sempre.

**Toda afirmação aqui sai de arquivo lido, e traz `arquivo:linha`.** É o que permite conferir em
vez de acreditar — se uma citação não bater com o código, o **código vence** e a linha aqui está
podre: conserte-a (é território do `P2-17`) ou abra card. Estado da árvore ao escrever: `3498ca4`,
fim do M3, mais a onda 1 do M4 (`P2-18` e `Q-6`, §5 e §10).

---

## 1. O que o sistema é

Paper trading de cripto: **dinheiro fictício, preço real** da Binance via `ccxt`. Um processo
`uvicorn` sobe a API FastAPI **e** um worker em thread; o worker gira a cada 15 s marcando
posições, escaneia sinais por relógio, e um auto-trader opcional abre e fecha sozinho dentro das
guardas de risco.

A postura importa para entender o desenho: o walk-forward + DSR já concluiu que **não há edge
comprovado** (`README.md` §"O veredito": DSR = 0,004 na tendência). O auto-trader existe para
*ver o "no edge" acontecer ao vivo dentro de guardas* — está escrito no cabeçalho do módulo,
`autotrader.py:8-13`. Consequência de arquitetura, não de humor: **o valor do sistema está nas
guardas e na paridade backtest↔live**, e é isso que o resto deste documento protege.

---

## 2. Os três territórios do repositório

| Onde | O que é | Roda como |
|---|---|---|
| **raiz** (`*.py`) | plataforma viva — os 11 módulos do fecho transitivo de `api.py`, mais 3 provas | `uvicorn api:app` na raiz |
| **`pesquisa/`** | a régua (walk-forward, DSR, backtest com paridade) | `python -m pesquisa.<mod>` da raiz |
| **`legado/`** | fases 1-2, arquivo morto legível | **não roda** (`legado/README.md`) |

A plataforma **não sai da raiz** e o motivo é o deploy: `deploy/cripto-bot.service:9` fixa
`WorkingDirectory=/home/ubuntu/cripto-bot` e `:13` roda `uvicorn api:app` a partir dela, e
`deploy/atualizar.sh:62` compila `./*.py` — glob de raiz, não recursivo. Mover um módulo vivo para
subdiretório o tira do portão de compilação do deploy sem que ninguém perceba.

**`scoring.py` e `indicadores.py` ficam na raiz e são importados pelos dois lados** — `scoring` por
`signal_engine.py:22` (vivo) e pela pesquisa. Isso **é** a paridade backtest↔live: o mesmo código
que pontua o sinal ao vivo pontua o candle histórico. Duplicar para "organizar" mataria a única
coisa que torna o backtest comparável ao live. O raciocínio completo está em `pesquisa/__init__.py`,
que também explica por que `python pesquisa/validacao.py` **não** funciona (rodar por caminho põe
`pesquisa/` no `sys.path` em vez da raiz, e `import scoring` falha).

---

## 3. O fluxo do worker — o coração do sistema

Um processo, duas coisas: a API atende requisições e uma thread daemon gira o ciclo. O worker sobe
no `lifespan` da aplicação (`api.py:120-126`), depois do `db.init_db()`, e morre com ela.

```
uvicorn api:app
   └─ lifespan (api.py:121) ──► db.init_db()  +  Thread(worker, daemon=True)
                                                     │
              ┌──────────────────────────────────────┘
              ▼   loop a cada POLL_ATUALIZAR = 15 s  (api.py:32, api.py:70)
   ┌──────────────────────────────────────────────────────────────────────┐
   │ try:                                             ← 1 try p/ o ciclo   │
   │   1. simulador.atualizar()   marca posições no preço vivo;            │
   │                              fecha em stop / trailing / liquidação    │
   │   2. signal_engine.avaliar_saida(p) p/ cada aberta  → _saidas["v"]    │
   │   3. dca.processar_devidos()   aportes DCA vencidos                   │
   │   4. autotrader.auto_executar(saidas)   ← try PRÓPRIO (api.py:78-81)  │
   │   5. INSERT INTO equity(...)   snapshot p/ o gráfico                  │
   │ except: _health["erros"] += 1; log()   ← nunca derruba o loop         │
   └──────────────────────────────────────────────────────────────────────┘
              │
              ├─ if _scan_devido():  signal_engine.scan()      ← FORA do try (api.py:91)
              │     expira sinais → varre ativos × TFs → pontua → portões → grava
              │
              ├─ 1×/dia:  db.podar_equity()                    ← bloco PRÓPRIO (api.py:100-110)
              │
              └─ time.sleep(15)
```

**Quatro decisões de ordem estão codificadas nesse desenho, e cada uma tem custo se invertida:**

1. **O `try` do passo 1 é por posição, não em volta do `for`** (`simulador.py:308-321`). Em volta do
   `for`, uma moeda que falha tira **todas** as posições seguintes da vigilância de stop, trailing e
   liquidação — funciona e perde dinheiro em silêncio. Invariante (`CLAUDE.md` §2).
2. **O auto-trader tem `try` próprio dentro do ciclo** (`api.py:78-81`): falha do bot não pode
   impedir o snapshot de equity do passo 5 — e o snapshot é o *baseline da trava diária*.
3. **O scan roda FORA e DEPOIS do `try` do ciclo** (`api.py:91-98`). Fora, porque uma falha na
   marcação não pode consumir o slot da varredura; depois, porque marcar posição é o caminho do
   stop e atrasá-lo pela duração do scan trocaria um instrumento impreciso por risco real. O
   comentário no código diz exatamente isso (`api.py:87-91`).
4. **A poda é bloco próprio, fora dos dois** (`api.py:100-110`), e marca o dia **antes** de podar:
   se a poda falhar, ela volta amanhã em vez de martelar o banco a cada 15 s.

### 3.1 A cadência do scan é relógio, não contador — e o porquê é o card

`INTERVALO_SCAN = 60` (`api.py:33`) é aplicado por `_scan_devido()` (`api.py:42-59`), que compara
`time.monotonic()` com o próximo vencimento e **reagenda antes de rodar**.

Era `_health["ciclos"] % CICLOS_POR_SCAN == 0`, avaliado dentro do `try` do ciclo. Sob falha
intermitente, o slot se perdia e o intervalo real virava 2-3 minutos sem ninguém ter decidido isso
(`api.py:45-51`). **Contar ciclos executados mede o que sobreviveu; o que a cadência precisa medir é
tempo, e quem mede tempo é relógio.** A função está extraída do `while True` de propósito: com o
instante como parâmetro, `python api.py` prova a cadência sem esperar 60 s.

---

## 4. Ciclo de vida de um sinal

`sinais.status` é uma máquina de estados, e a coluna carrega o contrato (`db.py:19`):

```
                             scan() ──► analisa(ativo,tf)  →  pontuar / pontuar_reversao
                                              │                (scoring.py:24 e :57)
                                              ▼
                                       confirmado(s,ativo,cfg)      (signal_engine.py:62)
                                    ┌──────────┴───────────┐
                       passou       │                      │   reprovou
                                    ▼                      ▼
                    _repetido()? ── não ──► 'novo'    rejeição por FLUXO ──► 'rejeitado_fluxo'
                          │ sim                                (fora da fila — Q-4)
                          └─► descartado (dedupe)              outras rejeições: não gravadas
                                    │
            ┌───────────────────────┼─────────────────────────────┐
            ▼                       ▼                             ▼
     POST /confirmar         autotrader.auto_executar       expirar_sinais()
     ou auto-trader                                         (signal_engine.py:345)
            │                                                     │
            ▼ CLAIM ATÔMICO (simulador.py:239-246)                ▼
      'confirmado' ──► INSERT posicoes                       'expirado'
            │
      POST /pular ──► 'pulado'
```

**O claim atômico é o invariante** (`simulador.py:238-248`): o `UPDATE sinais SET
status='confirmado' WHERE id=? AND status='novo'` roda com checagem de `rowcount` **na mesma
transação** do `INSERT INTO posicoes`. Quem ganha o UPDATE abre; o segundo pedido vê `rowcount 0` e
é recusado. O pré-check de `simulador.py:186-187` é conveniência — a exclusão mútua é no UPDATE. E os
tetos de risco e margem (`simulador.py:223-237`) levantam **antes** do claim, de propósito: recusa
por teto não pode consumir o sinal.

**Dois relógios governam o envelhecimento**, e eles concordam por construção:

- **Janela de dedupe/expiração = 4 velas do próprio TF** (`signal_engine.py:231`, `janela_min()` em
  `:236`). Fixar "60 min" trataria um sinal de 5m e um de 4h igual. 4 velas é exatamente o horizonte
  que o front já chamava de "expirou — reavalie", então o banco passou a concordar com a tela.
- **Freshness do auto-trader = `auto_freshness_min` (12 min por padrão, `db.py:87`)**. A janela de
  expiração é maior que isso em todo TF em uso (5m→20, 15m→60, 1h→240), então sinal expirável já era
  não-fresco antes de chegar ao bot — é o que fecha a lacuna aberta quando o scan passou a rodar
  depois do ciclo (`signal_engine.py:385-394`).

### 4.1 O portão de fluxo falha ANOTADO, não fechado nem aberto

Quando `mercado.book()` não devolve dados, o portão de fluxo não roda. A decisão registrada
(`signal_engine.py:100-107`) é **passar anotado**: o sinal recebe `MOTIVO_FLUXO_ND` nos motivos e o
contador `ultimo_scan["fluxo_indisponivel"]` sobe, publicado pelo `/status`. Fail-closed secaria a
fila inteira numa instabilidade prolongada; fail-open silencioso seria um portão anunciado que não
rodou. **A degradação vira dado em dois lugares.**

O auto-trader lê essa marca e **recusa o sinal** (`autotrader.py:28-36`): o humano da fila vê o
aviso e decide, o bot não lê aviso — com `exigir_fluxo=1` o dono declarou que não opera tendência
sem fluxo a favor, então o bot também não opera sobre fluxo *não verificado*. É a constante
`MOTIVO_FLUXO_ND` (`signal_engine.py:59`) existindo justamente para não virar literal solto em dois
módulos.

---

## 5. As guardas de risco, e onde cada uma mora

Três tetos e uma geometria, avaliados em pontos diferentes de propósito.

| Guarda | Onde | Mede |
|---|---|---|
| **Trava diária** (sticky) | `simulador.py:135-173` | equity de agora **vs. equity do início do dia** |
| **Teto de risco aberto** | `simulador.py:223-231` | soma do risco-até-o-stop das abertas |
| **Teto de margem** | `simulador.py:232-237` | soma de `valor_reais` vs. `banca × exposicao_max` |
| **Geometria stop×liquidação** (`P1-12`) | `simulador.py:195-215` | a liquidação vem **antes** do stop? |

**A trava diária compara equity, não P&L realizado** (`simulador.py:150-158`): o baseline é o
**primeiro** snapshot de `equity` do dia corrente (`ORDER BY rowid ASC LIMIT 1`), e o corrente é
`banca.atual + SUM(pnl)` das abertas. Por isso um dia pode fechar com trades realizados positivos e
a trava disparada — aconteceu em 22/08 (+34,68 realizados, trava por −80,34 de equity). É *sticky*:
uma vez marcada em `config.trava_dia_em`, não destrava se o não-realizado recuperar; solta na virada
do dia. Limpar `trava_dia_em` à mão é relaxar invariante.

Isso amarra três coisas que parecem independentes e não são: **o snapshot de equity do worker
(passo 5) é o baseline da trava**, e por isso a poda protege as últimas 48 h em resolução cheia
(`db.py:189`, e o comentário em `db.py:206-210` diz que podar o primeiro ponto do dia seria afrouxar
invariante de risco por efeito colateral de faxina).

**A liquidação é modelada, não decorativa**: `_preco_liquidacao` usa `LIQ_BUFFER = 0.9`
(`simulador.py:17`, `:84-88`) — liquida quando a perda chega a ~90% da margem. E quando stop e
liquidação batem no mesmo tick, ganha **o mais perto da entrada** (`simulador.py:340-343`) — a mesma
regra do backtest, o que faz o empate ser resolvido do mesmo jeito nos dois lados. Paridade de novo.

**E o modelo de liquidação virou guarda de entrada** (`P1-12`). Quando `lev × stop_dist ≥
LIQ_BUFFER` a liquidação chega **antes** do stop: o stop é inalcançável, a perda é a margem inteira
e o trade vira binário — 37,2% das barras de INJ 1h a 20x, medido no `P1-11`. `abrir()` recusa essa
geometria com `ValueError`, e três detalhes do desenho não são estilo:

- **Mora em `abrir()`, não na rota.** O cap do `P1-11` vive em `autotrader._alavancagem`, e só o
  auto-trader passa por lá: `POST /confirmar` recebe `alavancagem` do **cliente** e a repassa
  (`api.py:681`). Um pré-check na rota protegeria uma porta; `abrir()` é o único ponto por onde os
  **dois** fluxos passam, e uma recusa ali não se contorna por rota nova, cliente novo ou `curl`.
  `api.py:682` já traduz `ValueError` para `{ok:false, erro}`, então a rota não mudou.
- **Recusa, não cap silencioso.** O auto-trader capa porque é ele quem escolhe a alavancagem; quem
  digitou 20x no painel receberia uma posição de 14x que não pediu, dimensionada para outra
  alavancagem, sem nada na tela dizendo isso. A mensagem devolve as duas distâncias e o teto de
  alavancagem que aquele stop comporta.
- **As duas camadas usam números diferentes de propósito.** A guarda é a parede física
  (`LIQ_BUFFER`); o cap do auto-trader é o recuo de 25% que o bot se impõe antes dela
  (`FOLGA_LIQ = 0,8`). Se as duas usassem o mesmo número o bot viveria em cima da fronteira e um
  erro de ponto flutuante bastaria para ele recusar os próprios trades.

Ela levanta **antes do claim atômico**, pela mesma razão que os tetos: recusa por geometria não é
defeito do sinal, e consumi-lo tiraria da fila um sinal que volta a ser confirmável assim que a
alavancagem pedida couber.

**O stop tem gatilho e tem fill, e eles não são o mesmo preço** (`_fill_stop`,
`simulador.py:355-378`, `P2-18`). O worker olha o mercado a cada 15 s; entre dois polls o preço
rompe o stop e segue. Fechar no preço do stop grava uma execução que não houve, e o erro é sempre
para o **mesmo lado** — perda menor e trailing melhor que o real. Por isso o fill é o **pior** entre
o stop e o preço observado: LONG executa no mais baixo dos dois, SHORT no mais alto. Quando isso
acontece, o `motivo_saida` ganha o sufixo **`-gap`** (`stop-gap`, `trailing-gap`,
`simulador.py:391-393`), e é isso que torna o custo do gap mensurável depois por query em `trades`,
sem instrumentação nova.

O fill tem **piso no preço de liquidação**: passado ele a corretora já tomou a margem, então não
existe fill pior — é o mesmo argumento que mantém a liquidação fechando em `_preco_liquidacao`. Sem
o piso, o desempate stop×liquidação acima gravaria execução num preço em que a posição já não
existia, e o paper ficaria pessimista *além* do real. A forma `min(stop, max(preco, liq))` (e a
espelhada do SHORT) é deliberada: o piso encurta o gap, nunca melhora o fill para além do `stop` —
o resultado é sempre igual ou pior que o de antes do card. **Aperta a guarda, e apertar pode**
(`CLAUDE.md` §2).

---

## 6. A API

31 rotas (19 `GET`, 12 `POST`) em `api.py`, mais o mount estático `/vendor` (`api.py:425`).

**`/estado` é a rota que sustenta o painel**: devolve tudo num request só (`api.py:556-577`) —
banca, equity total, config, pendentes, posições, trades, curva de equity, métricas, risco, DCA e o
último ciclo do auto-trader. O painel faz poll dela a cada 3 s (`web/index.html:1669`).

**Autenticação é middleware, não dependência de rota** (`auth_basica`, `api.py:187-238`), e é
assim porque a decisão é sobre *todo* o app, não sobre endpoints escolhidos a dedo. O
comportamento:

- `/health` e `OPTIONS` passam sem credencial (`api.py:191-193`) — o primeiro é o endpoint de
  saúde, o segundo é preflight de CORS, que o navegador manda sem `Authorization`.
- **Sem `DASH_PASS`**: só loopback direto. Requisição externa ou via proxy leva **503**
  (`api.py:195-207`). Existiu uma bandeira `PERMITIR_SEM_SENHA` e foi exatamente ela que deixou
  `/reset`, `/panico`, `/config` e `/auto` abertos na internet — o comentário em `api.py:135-140`
  registra que **não há bandeira para desligar isso**: "a guarda que recusa acesso externo sem
  `DASH_PASS` só protege se não houver como desligá-la".
- **Com `DASH_PASS`**: Basic Auth com `secrets.compare_digest`, e `/docs`, `/redoc` e
  `/openapi.json` **somem** (`api.py:139-142`) — mapa da API não é coisa de deploy público.
- Throttle de 15 senhas erradas → bloqueio de 120 s por IP (`api.py:154-155`). Só conta quem
  **mandou** credencial errada (`api.py:229-234`): o painel dispara ~5 requisições sem credencial
  por ciclo antes do login, e contá-las bloquearia o usuário legítimo em segundos.

**A ordem dos middlewares é decisão, não acaso** (`api.py:241-249`): no Starlette o último
adicionado é o mais **externo**, então o CORS é registrado *depois* da auth para **embrulhá-la**.
Por dentro, as respostas que a auth devolve sozinha — 401, 429, 503 — saíam sem
`Access-Control-Allow-Origin`, e para o painel no Vercel isso não é "401", é falha de CORS: o
`fetch` rejeita, o `if(r.status===401)` nunca executa, o prompt de senha nunca aparece e o painel
parece backend fora do ar. Ficou latente enquanto tudo respondia 200 e apareceu inteiro no primeiro
deploy com senha.

**`POST /config` valida por catálogo fechado** (`_TFS` e o catálogo a partir de `api.py:260`). Sem
isso, qualquer chave com qualquer valor entrava e o erro só explodia lá no `float()` de
`guarda_risco()` — longe da causa e no caminho de **todo** `/estado`.

**`/health` devolve o commit que o processo está rodando** (`api.py:463-473`). A ordem é
`COMMIT_SHA` do ambiente → `git rev-parse` → **`None` declarado**, nunca `"desconhecido"` ou
`"dev"`: string inventada responde à pergunta com algo que *parece* resposta, e a checagem de deploy
passaria a comparar com um valor que nunca foi um commit. É lido **uma vez, no import**
(`api.py:468`) — pôr um subprocesso no único endpoint sem autenticação seria dar um `fork` de graça
a quem bate na porta.

---

## 7. O banco

SQLite, caminho em `DB_PATH` ou `trading.db` ao lado do código (`db.py:12`). **WAL + `busy_timeout`
de 30 s** (`db.py:103-104`): leituras concorrentes com um escritor, que é exatamente a forma do
sistema — a API lê enquanto o worker escreve.

Sete tabelas, todas em `db.SCHEMA` (`db.py:14-46`):

| Tabela | Linha | Papel | Notas de esquema |
|---|---|---|---|
| `sinais` | `db.py:15` | fila e histórico de oportunidades | `status`: `novo` \| `proposto` \| `confirmado` \| `pulado` \| `rejeitado_fluxo` \| `expirado`; colunas `vela_ms`/`fluxo_comprador`/`desfecho*` são a medição prospectiva do `Q-4` |
| `posicoes` | `db.py:27` | posições abertas/fechadas | `stop` é reescrito pelo trailing a cada ciclo |
| `trades` | `db.py:32` | fechamentos (o histórico de pesquisa) | `+ stop`, `risco_inicial`, `funding` via `_migrar` |
| `equity` | `db.py:37` | snapshot a cada 15 s | é o baseline da trava diária **e** a fonte do gráfico |
| `config` | `db.py:39` | **os parâmetros vigentes** | chave/valor, tudo `TEXT` |
| `banca` | `db.py:41` | linha única `id=1` | `inicial` × `atual` |
| `dca` | `db.py:43` | acumulação sem alavancagem | banca conceitualmente separada da de trade |

**Migração é aditiva e roda a cada start** (`_migrar`, `db.py:112-126`): adiciona coluna que faltar,
nunca reescreve. Os índices ficam **fora** do `SCHEMA` e rodam **depois** do `_migrar`
(`db.py:128-143`) — índice sobre coluna que o `_migrar` acabou de criar não existiria se o `CREATE`
viesse antes. `IF NOT EXISTS` não é estilo, é requisito: isso roda contra o banco de **produção**, a
cada start do worker.

`idx_equity_dia` é índice de **expressão** (`db.py:141`) e a razão é a trava diária: a consulta que
mais dói é `WHERE substr(ts,1,10)=?`, rodada a cada poll de 3 s, e `substr` sobre a coluna esconde a
coluna do planejador. Medido em banco sintético de 1 ano: **255 ms → 0 ms**.

### 7.1 Retenção: a poda reduz resolução, não corta passado

`podar_equity()` (`db.py:199-227`) mantém 48 h em resolução cheia (15 s), até 90 dias a 1 ponto por
5 min, e além disso 1 ponto por hora (`db.py:189-190`). O worker grava 5.760 linhas/dia — ~2,1
milhões/ano sem poda.

Guarda o **maior** `rowid` de cada balde, nunca o primeiro: o último ponto da janela é o que o
gráfico e o max-drawdown leem como o valor daquele instante. É idempotente e convergente — rodar
duas vezes seguidas não remove nada na segunda.

Os baldes são fatiamento de **string**, não `strftime` (`db.py:192-194`), e isso é convenção §1 do
`CLAUDE.md` virando código: o `ts` é naive em hora de São Paulo e vem de `str(pd.Timestamp.now())`,
que ora traz microssegundos ora não. `strftime` teria de parsear isso; `substr` **não parseia nada e
nunca inventa fuso**.

---

## 8. Topologia de deploy

```
   navegador
      │  HTTPS
      ▼
  ┌──────────────────────────┐        ┌──────────────────────────────────────────┐
  │ Vercel                   │        │ VM Azure  vm-cripto-bot (southafricanorth)│
  │ cripto-quant-dashboard   │  API   │                                           │
  │ .vercel.app              │ ─────► │  Caddy :443  (TLS Let's Encrypt, auto)    │
  │ serve web/ estático      │  CORS  │    │ reverse_proxy (deploy/Caddyfile:7)   │
  │ (vercel.json:5           │        │    ▼                                      │
  │  outputDirectory: web)   │        │  uvicorn 127.0.0.1:8000                   │
  └──────────────────────────┘        │  (cripto-bot.service:13, --host 127.0.0.1)│
        merge na main = publicar      │    ├── FastAPI  (31 rotas)                │
                                      │    └── worker thread (15 s)               │
                                      │  trading.db (SQLite WAL) ── cron 03:17 ──►│ Azure Blob
                                      └──────────────────────────────────────────┘
```

**O uvicorn escuta só em loopback** (`deploy/cripto-bot.service:11-13`): quem fala com a internet é
o Caddy. É por isso que a auth trata "veio por proxy" como "veio da internet"
(`_via_proxy`, `api.py:161-163`) e só confia no `X-Forwarded-For` quando o peer direto é o proxy
local (`_cliente_ip`, `api.py:166-172`) — senão qualquer um forjaria o header e escaparia do
bloqueio de IP.

**O `.env` da VM não está no repositório** (`deploy/cripto-bot.env.example` é o modelo): `DB_PATH`,
`DASH_USER`, `DASH_PASS` e `CORS_ORIGINS`. O `atualizar.sh` não toca nele nem no banco
(`deploy/atualizar.sh:10-13`).

### 8.1 O hostname mora em mais de um lugar, e eles têm de concordar

São **dois nomes** e **três pontos de acoplamento** — trocar o domínio sem tocar nos três derruba
o painel de um jeito que parece backend fora do ar:

| Nome | Onde | Papel |
|---|---|---|
| hostname do **backend** | `deploy/Caddyfile:5` | de quem o Caddy tira o certificado TLS |
| hostname do **backend** | `web/config.js:9` (`window.API_BASE`) | para onde o front aponta — tem de ser `https://`, página HTTPS não chama HTTP |
| origem do **front** | `CORS_ORIGINS` no `.env` da VM (modelo em `deploy/cripto-bot.env.example:11`) | quem o backend aceita como origem; lido em `api.py:147` |

O `web/config.js` é servido com `Cache-Control: no-store` nos dois `vercel.json` (raiz `:9` e
`web/vercel.json:9`) — é o arquivo que redireciona o front, e um cache dele apontaria o painel para
um backend velho.

### 8.2 O deploy é um comando, e ele para em cada portão

`cripto-deploy` → `deploy/atualizar.sh` (`P2-3`, fechado em 2026-08-22). A VM **é** repositório git
e autentica por deploy key SSH somente-leitura. Ordem e portões, do próprio script:

1. **aborta com árvore suja** (`:23-28`) — senão a modificação local some sem ninguém ver
2. **backup do banco antes de qualquer troca; aborta se falhar** (`:34-35`)
3. **congela**: `auto_trade=0` e conta posições abertas (`:37-42`)
4. `git checkout` do alvo (`:44-48`)
5. **`py_compile` no venv de PRODUÇÃO; falhou, volta ao commit anterior** (`:62-63`)
6. restart + verificação: serviço ativo, tracebacks, `PRAGMA integrity_check`, **equity nova no
   último minuto** e `/health` (`:66-77`)
7. **não religa o `auto_trade`** — imprime o comando (`:81-83`)

O passo 7 é a decisão mais deliberada do script, e está escrita nele (`:10-13`): *religar sozinho
seria o script decidindo por você que está tudo bem.* O rollback é o mesmo script com um SHA.

O glob `./*.py` do passo 5 continua sendo de raiz **de propósito** depois do `P2-16`
(`deploy/atualizar.sh:51-61`): pesquisa não é código de produção e estender o glob acoplaria a
disponibilidade do bot a um script de pesquisa quebrado que a produção nunca carrega. Quem quiser
portão para pesquisa, o lugar é o pytest.

---

## 9. Decisões de design, com o porquê

**Basic Auth em vez de sessão/JWT.** É um painel de um usuário. O navegador guarda a credencial e a
reenvia sozinho, o que dispensa refresh, cookie, CSRF e tela de sessão expirada. A credencial fica no
`localStorage` (`web/index.html:799`) — e é essa escolha que cria o invariante do CDN abaixo. O
custo aceito está anotado no próprio código: a comparação usa `compare_digest` e o throttle contém
scanner barulhento, não força bruta, porque a senha de 24 caracteres alfanuméricos já torna a força
bruta inviável por construção (`api.py:151-153`).

**Bibliotecas vendorizadas, nunca CDN.** `web/vendor/` guarda `chart.umd.min.js` (Chart.js 4.4.1) e
`lightweight-charts.standalone.production.js` (4.1.3), commitadas, e o HTML as carrega por caminho
relativo (`web/index.html:16-17`). O motivo está no comentário logo acima (`:14-15`): **script de
terceiro no mesmo documento lê o `localStorage`**, ou seja, um CDN comprometido rouba a credencial
do painel. `grep -rn "src=['\"]http" web/` não devolve nada — e é o teste de um segundo.
A **única** exceção é a stylesheet do Google Fonts (`web/index.html:13`), declarada e justificada
em `:9-12`: *folha de estilo não executa JS, então não é vetor para roubar a credencial* — que é o
motivo da regra. Trocar `vendor/` por CDN "para atualizar a versão" é quebrar o invariante.
O mount de `/vendor` degrada em vez de derrubar (`api.py:423-428`): diretório ausente vira aviso no
log, porque sem as libs o gráfico não renderiza mas **API, worker e risco seguem de pé**.

**Polling de 3 s em vez de WebSocket.** O dado de fundo muda a cada 15 s (o ciclo do worker), então
push traria complexidade de conexão para uma frequência que polling atende. `/estado` existe para
que esse poll seja **um** request e não dez (`api.py:556`). O preço disso é o tamanho da resposta —
ver abaixo.

**Amostragem da curva de equity, e a franquia de banda.** `_amostrar()` reduz a série para ~125
pontos (`api.py:538-555`). O motivo é explícito no docstring (`api.py:539-541`): a curva era
reenviada inteira a cada poll de 3 s e sozinha respondia por **72% do payload — 51 KB de 71 KB — e
a franquia de saída da Azure é de 15 GB/mês**. Com esse poll, **o tamanho da resposta é decisão de
arquitetura, não detalhe**: quem engordar `/estado` está gastando franquia, e a conta é contínua.
O passo é **fracionário** (`round(i * n / alvo)`, `api.py:552`) — era divisão inteira, e por isso
qualquer `len` entre 125 e 249 devolvia a série inteira: a função não reduzia nada justamente na
faixa em que ela começa a ser necessária.

**Teto de itens escolhido pelo servidor.** `limite` chegava como inteiro livre direto no `LIMIT` do
SQLite (`api.py:599-603`): quem decide quanto o servidor materializa é o servidor.

**`serie_equity` rareia, não corta.** O `max_linhas=50000` (`db.py:229-253`) é teto de RAM, não
janela — e quando morde, ele **rareia** por faixa de `rowid`, porque cortar pelo fim reintroduziria
exatamente a janela enganosa de ~2 h que o `P2-11` fechou.

**Cache de 5 s por ativo no `mercado`** (`mercado.py:23-42`): um `fetch_tickers` serve N
consumidores. A **ausência também é cacheada** — símbolo que a corretora não lista não refaz request
a cada chamada — e falha de rede faz o ativo sair **ausente**, nunca virar zero. É o mesmo princípio
do `None` declarado do `/health` e do funding não medido do `P2-10`: **ausência de medição não vira
valor plausível.**

**Rede fora de transação.** `abrir()` lê o sinal, sai da conexão, busca preço, e só então entra no
lock + transação (`simulador.py:182-248`). `dca.aportar()` faz o mesmo em três passos — leitura
curta, rede, escrita curta com `rowcount` (`dca.py:25-42`) — e se o plano sumiu durante a viagem de
rede, nada é aportado **e o log não pode dizer que foi**.

**Alertas Telegram são opcionais e no-op por padrão** (`alertas.py`): sem `telegram_token` e
`telegram_chat_id` na config, `enviar()` retorna `False` sem tocar na rede. Usa `urllib`, sem
dependência extra.

**Log com teto conhecido, no código e não no logrotate** (`logbot.py:6-16`): `RotatingHandler` de 10
MB × 5 backups = ~60 MB, "porque assim a poda viaja com o repositório". O arquivo é
**`plataforma.log`**, ao lado do código — `logbot` é o *módulo*, não o nome do arquivo.

---

## 10. Aproximações conhecidas do modelo

Paper trading é simulação, e toda simulação aproxima. O que está aqui são os pontos em que o
modelo **sabidamente** difere de uma corretora real, com a **direção** do viés e a decisão de cada
um. Registrar a direção é o ponto: um número só é interpretável se você souber para que lado ele
erra — e a maior parte destes erra a favor do pessimismo, que é o lado permitido nesta casa. O
levantamento é o `Q-6`; os números conferidos estão abaixo de cada item.

| # | Onde | O modelo faz | Direção | Decisão |
|---|---|---|---|---|
| **(a)** | `_preco_liquidacao` (`simulador.py:84-88`) | `LIQ_BUFFER/lev`, sem *maintenance margin* | conservador **até ~20-25x**, otimista acima | documentar |
| **(b)** | `_pnl` (`simulador.py:118`) | taxa das duas pernas sobre o nocional de **entrada** | segue o movimento do preço, ±R$0,01 no trade típico | documentar |
| **(c)** | `_funding_custo` (`simulador.py:54-77`) | soma dos rates sobre o nocional de **entrada** | idem, e cresce com o tempo de hold | documentar |
| **(d)** | `dados.baixar_ohlcv` (`pesquisa/dados.py`) | gravava o candle **em formação** no cache | irreprodutível — não é viés, é ruído | **corrigido** |
| **(e)** | `_risco_posicao` (`simulador.py:125-132`) | risco-até-o-stop **sem as taxas** | subestima o risco por `1 + 2·fee/sd` | **documentar** (`P2-38`) |

**(a) A liquidação não tem *maintenance margin*, e a conservadoria dela tem um ponto de virada.**
O modelo liquida no movimento adverso de `LIQ_BUFFER/lev` = `0,9/lev`. Uma perpétua real liquida
perto de `1/lev − mmr`, com `mmr` ~0,4-0,5% nos tiers baixos. Em `LIQ_BUFFER` equivalente isso é
`1 − mmr·lev`, ou seja: **a régua real fica mais frouxa com alavancagem baixa e mais apertada com
alavancagem alta**, e o `0,9` fixo cruza com ela.

| lev | modelo | real (mmr 0,4%) | real (mmr 0,5%) | `LIQ_BUFFER` equivalente (0,4%) |
|---|---|---|---|---|
| 5x | 18,00% | 19,60% | 19,50% | 0,980 |
| 10x | 9,00% | 9,60% | 9,50% | 0,960 |
| **20x** | **4,50%** | 4,60% | **4,50%** | 0,920 |
| 25x | 3,60% | **3,60%** | 3,50% | **0,900** |
| 50x | 1,80% | 1,60% | 1,50% | 0,800 |

O cruzamento é `lev = (1 − LIQ_BUFFER)/mmr` — **25x** com mmr 0,4%, **20x** com mmr 0,5%. Abaixo
dele o paper liquida **antes** do real (conservador, e é o caso do card). Acima, liquida **depois**:
o paper deixa a posição viva num ponto em que a corretora já teria tomado a margem — otimista. O
`auto_lev_max` padrão é **20x** (`db.CONFIG_PADRAO`), ou seja, o teto de hoje encosta exatamente no
ponto de virada com mmr 0,5%. Parametrizar `mmr` é possível e barato; o que decidiu por documentar
é que mexer no `LIQ_BUFFER` reprecifica **todo** o histórico de trades já fechado, e a diferença
dentro da faixa operada é de décimos de ponto percentual.

**(b) A taxa de saída é cobrada sobre o nocional de entrada.** `_pnl` faz
`2 · fee · valor_reais · alavancagem`: as duas pernas sobre o nocional inicial. Na corretora a
perna de saída incide sobre o nocional de **saída**, então o erro é
`fee · nocional · (saída/entrada − 1)` — **positivo quando o preço subiu no hold, negativo quando
caiu, independentemente de ser LONG ou SHORT**. Numa margem de R$100 a 10x (nocional R$1.000) e
`fee` 0,05%: R$0,005 num movimento de 1%, R$0,01 em 2%, R$0,05 em 10%. Implementar exigiria passar
o preço de saída para dentro do cálculo da taxa e reprecificar a paridade com
`backtest_plataforma.TAXA`, que usa a mesma forma — custo alto para corrigir centavos.

**(c) O funding também é somado sobre o nocional de entrada.** `_funding_custo` aplica a soma dos
rates da janela sobre o nocional inicial (`simulador.py:265`); o real liquida a cada *settlement*
de 8 h sobre o nocional **corrente**. Mesma forma de erro do (b), e pequeno enquanto o hold for
curto — a política viva é intraday e a maioria dos trades não atravessa nem um settlement. Cresce
com o tempo de hold, e é a aproximação que mais rapidamente deixa de valer se a estratégia virar
swing. **Nota de leitura:** funding não medido é `None`/`NULL`, e isso é outra coisa — ausência
declarada, não aproximação (`P2-10`, §9).

**(d) O candle em formação — o único item do pacote com conserto de código, e ele está feito.**
A exchange devolve a barra corrente junto das fechadas, e ela muda a cada trade até fechar.
Gravada no CSV, virava um candle que nunca existiu, congelado no estado em que estava no instante
do download: duas baixas do mesmo dia discordavam sobre a mesma barra, enquanto o nome do arquivo
de cache — que carrega a data — prometia uma janela reproduzível por dia. `_fechados`
(`pesquisa/dados.py:14-30`) corta em `timestamp + tf <= agora`, e a garantia passa a ser
**toda barra que sai de `baixar_ohlcv` é barra fechada**. Prova em `tests/test_execucao_real.py`.

**(e) O risco-até-o-stop ignora as taxas — e o que ele alimenta não é o sizing.** `_risco_posicao`
(`simulador.py:125-132`) mede `valor · lev · sd`, capado na margem, onde `sd` é a distância relativa
até o stop. Quando o stop bate, as taxas das duas pernas somam `2 · fee · lev · valor` à perda, e
elas ficam de fora da conta. Então o teto de risco aberto e o `risco_inicial` gravado estão
subestimados nessa fração. Decidido no `P2-38`, em 2026-08-23: **documentar** (opção C do card).

**A magnitude tem dois denominadores, e só um deles é o decisivo.**

Em fração da **margem**, o erro cresce com a alavancagem — é a leitura que o `Q-6` registrou:

| lev | taxa no stop, em fração da margem (`2·fee·lev`) |
|---|---|
| 2x | 0,20% |
| 5x | 0,50% |
| **10x** (`alavancagem_padrao`) | **1,00%** |
| **20x** (`auto_lev_max`) | **2,00%** |
| 50x | 5,00% |

Mas o número que decide é o erro **relativo ao risco medido**, e nele **a alavancagem cancela** —
os dois termos escalam com `lev · valor`, então `real/medido = (sd + 2·fee)/sd` depende **só da
distância do stop**:

| stop | onde aparece | fator | erro |
|---|---|---|---|
| 0,50% | stop colado (o cap por trade já morde antes) | 1,200x | +20,0% |
| 0,74% | BTC 15m p50 | 1,135x | +13,5% |
| 1,64% | BTC 15m p95 | 1,061x | +6,1% |
| 2,65% | SOL 1h p50 | 1,038x | +3,8% |
| 3,67% | INJ 1h p50 | 1,027x | +2,7% |
| 9,50% | INJ 1h p95 | 1,011x | +1,1% |

(`fee` = `taxa_por_lado` = 0,05%, `db.CONFIG_PADRAO`. Stops medidos: tabela do `P1-11`.)

**Isto inverte a intuição da leitura por margem:** o caso perigoso não é a alavancagem alta, é o
**stop curto**. A 50x com stop de 9,5% o erro relativo é 1,1%; a 2x com stop de 0,5% é 20%.

**No que está vivo hoje** — banca R$1.000, `risco_por_trade` 3%, stop de 2%, 10x — `_tamanho` pede
R$150 de margem, `guarda_risco` conta R$30 de risco e a perda real no stop é **R$31,50**: 5% acima
do orçamento. No teto de risco aberto (10% do equity), a guarda vincula com R$90 medidos, que são
R$94,50 reais — **9,4% do equity, não 9,0%**.

**Por que documentar, e não consertar — as três opções do `P2-38` e o motivo de duas caírem.**

- **(A) Corrigir os dois lados e declarar um corte no histórico.** Cai por **território e por
  esquema**. Fazer `db.metricas()` não misturar duas unidades R exige escrever em `db.py`
  (`T-DECLARACAO` na onda 2 do M4) e provavelmente uma coluna nova; esquema é estado compartilhado
  que o território não isola (§9.2b do plano).
- **(B) Corrigir só na guarda, não no sizing.** Cai por **contradizer o próprio critério de aceite**,
  que pede "`guarda_risco()` e `_tamanho()` concordam sobre o que 'risco' significa — teste que
  prove que uma é inversa da outra". B, por definição, as desalinha: o bot dimensionaria para R$30
  enquanto a guarda contaria R$31,50. Estender B ao `_tamanho` deixa de ser B — encolhe toda
  posição viva em ~5%, e mudar sizing vivo num card `toca-risco` é assinatura do dono (§9.8).
- **(C) Documentar.** É esta seção, e é a mesma resposta que o `Q-6` deu para (a), (b) e (c).

**O que mudou hoje e a próxima pessoa precisa saber: o `min(..., valor_reais)` deixou de mascarar.**
Antes, a geometria degenerada (`lev·sd ≥ 1`) fazia `_risco_posicao` devolver a margem inteira, e
nesse regime não havia o que subestimar. O `P1-12` recusa `lev·sd ≥ LIQ_BUFFER` na abertura, então
**toda posição nova tem `lev·sd < 0,9`** e o cap nunca morde: a subestimação passa a valer em 100%
das posições novas, em vez de só nas de geometria sadia. Na pior geometria que ainda passa, a perda
real é 0,95 da margem (50x) — ainda abaixo dela, então o cap continua correto, só deixou de ser
alcançado.

**A decisão é executável, não só prosa.**
`tests/test_guarda_risco.py::test_p2_38_o_risco_medido_exclui_as_taxas_e_isso_e_decisao_registrada`
fixa a fórmula sem taxas e os fatores desta tabela. Quem "consertar" `_risco_posicao` de passagem
derruba esse teste e cai aqui, no parágrafo sobre a unidade R — que é o efeito que nenhum número do
painel acusaria sozinho.

---

## 11. A suíte

`python -m pytest` → **532 passed** (medido na `main` com as ondas 1 e 2 do M4 mescladas, ~3 min;
eram 143 em `3498ca4` e 445 antes da onda 2). Sem rede, banco temporário por teste,
`preco_ao_vivo` substituído.

> **O `xfail` que esta seção descrevia não existe mais, e o mecanismo continua valendo.** Havia um
> `xfail(strict=True)` em `tests/test_metricas.py`, plantado pelo `P2-6` (M3) por um worker que
> **achou** o defeito de `db.metricas()` e **não podia consertá-lo** — `db.py` estava fora do
> território dele. Ele virou o card `P2-36`, e o `strict=True` era a armadilha: no dia em que o card
> fechasse, o teste passaria a XPASS e **quebraria a suíte**, obrigando quem consertou a promovê-lo.
>
> Foi exatamente o que aconteceu em 2026-08-23, na onda 2 do M4. O card fechou, a suíte reprovou, e
> o teste foi promovido a teste normal. **A conta hoje não tem `xfailed` nenhum** — e isso é o
> mecanismo tendo funcionado até o fim, não o mecanismo tendo sido removido. Se um worker futuro
> plantar outro `xfail(strict=True)` porque achou um defeito fora do território dele, a regra do
> `CLAUDE.md` §6 continua sendo a mesma: **não o "limpe" — vá ao card.**

A suíte tem duas metades. Em `tests/` estão os testes das funções que doem se quebrarem; a outra
metade **embrulha as seis provas já versionadas** (`tests/test_provas_existentes.py`), executando
cada uma por subprocesso, no processo isolado em que ela foi escrita para rodar. Por isso
`prova_m1.py`, `test_sim.py` e `test_auth.py` **não saem da raiz**, e por isso `testpaths = tests`
no `pytest.ini:8` os mantém fora da coleta: eles casam com `test_*.py`, mas são programas de
`python <arquivo>` — coletá-los faria o pytest importá-los e rodar duas provas dentro do próprio
processo, fora do isolamento das fixtures.

**A suíte exige que o repositório seja um checkout git**, e isso é intencional: a prova do `api.py`
verifica que `/health` devolve o commit, e para isso roda `git rev-parse HEAD`. Rodar a suíte numa
cópia sem `.git` a reprova por um motivo que não é defeito. Quem auditar, use `git worktree add
--detach`, não `copytree`.

**`tests/test_metricas.py::test_pnl_nulo_no_banco_nao_derruba_a_conta` está `xfail(strict=True)`, e
não é teste quebrado — é um defeito latente registrado.** `db.metricas()` classifica os trades
tolerando NULL (`db.py:272-273`, `(t["pnl_reais"] or 0)`) e **soma a coluna crua** duas linhas
abaixo (`db.py:274-275`): um `pnl_reais` NULL levanta `TypeError` e derruba o `/estado` inteiro.
Latente hoje porque `simulador.py:279` é o único INSERT em `trades` e sempre passa float. O card é
o `P2-36`. O `strict=True` é o ponto: **no dia em que o `P2-36` fechar, o xfail vira XPASS e quebra
a suíte**, obrigando quem consertou a promover o teste. É convenção do projeto — um xfail estrito
aqui é um card em aberto, não sujeira para limpar.

---

## 12. O que este documento não cobre

| Pergunta | Onde |
|---|---|
| O que eu não posso mudar? | `CLAUDE.md` §2 |
| Como operar a VM (acesso, backup, diagnóstico) | `RUNBOOK-VM.md` |
| Como rodar e validar uma estratégia | `README.md` §Testes e §Validar uma estratégia |
| Por que o projeto conclui "sem edge" | `README.md` §O veredito · `pesquisa/validacao.py` |
| Cores, tipografia, tokens do painel | `DESIGN.md` |
| O plano de marcos, territórios e portões | `PLANO-EXECUCAO-2026-08-20.md` §4, §9 |
