# Status do sistema — investigação geral (2026-08-19)

> Varredura de ponta a ponta: código, backend, worker, deploy, VM Azure, Caddy/TLS, front no Vercel,
> banco, segredos e operação. Complementa a `AUDITORIA-SISTEMA.md` (junho, matemática/estratégia).

---

# ⚠️ DOCUMENTO HISTÓRICO — NÃO descreve o sistema de hoje

**Este relatório é uma fotografia de 2026-08-19.** Tudo que ele chama de "agora" era verdade
naquela data e **não é mais**. Ele ficou público por uma semana afirmando que o backend estava
aberto na internet, num repositório público, com o hostname de produção versionado em outros
cinco documentos. Isso era um convite, não um relatório.

**Estado verificado em 2026-08-26**, contra o host de produção:

```
GET  /              -> 401
GET  /estado        -> 401
GET  /docs          -> 401
GET  /openapi.json  -> 401
POST /reset         -> 401
```

| Item de 19/08 | Estado hoje | Onde conferir |
|---|---|---|
| **P0-1** backend aberto | ✅ **fechado.** A bandeira `PERMITIR_SEM_SENHA` **não existe mais no código** — foi removida, não desligada. Sem `DASH_PASS` o backend atende **só loopback**; com `DASH_PASS`, `/docs`, `/redoc` e `/openapi.json` deixam de existir. Há throttle por IP (15 falhas → 120 s) | `api.py:135-143`, `test_auth.py`, invariante no `CLAUDE.md` §2 |
| **P0-2** Binance 451 | ✅ **fechado.** VM migrada para `southafricanorth` — a única região que a Azure Policy da assinatura permite E que a Binance não geo-bloqueia | `deploy/provisionar-azure.sh:8-14` |
| **P1-1** falha de rede paralisa o ciclo | ✅ **fechado.** `try/except` **por posição** dentro do `for`, nunca em volta dele — virou invariante | `simulador.atualizar()`, `CLAUDE.md` §2 |
| **P1-2** front descarta a credencial | ✅ **fechado.** Existe tela de login; o `removeItem('cbAuth')` só roda no logout e no tratamento de 401 | `web/index.html:953, 974` |
| **P1-3** `/trades?limite` sem teto | ✅ **fechado.** `Query(50, ge=1, le=500)`; `/candles` em `le=1000` | `api.py:768, 774` |
| **P1-4** `_amostrar()` não reduzia | ✅ **fechado.** Passo fracionário por `round(i*n/alvo)` | `api.py`, `_amostrar` |
| **P1-5** `breadth()` contava antes de falhar | ✅ **fechado.** `continue` antes de qualquer contador | `mercado.py:64-69` |
| **P2-1** sem rotação de log | ✅ **fechado.** `RotatingFileHandler`, 10 MB × 5 | `logbot.py:13` |
| **P2-2** sem backup do banco | ✅ **fechado.** `cripto-backup.sh` na VM, e o **deploy aborta** se o backup falhar. Além disso o `POST /reset` passou a exigir `{"confirmar": "RESET"}` — POST solto não apaga nada | `deploy/atualizar.sh:30-35`, `api.py` `/reset` |
| **P2-3** VM não era repositório git | ✅ **fechado** desde 22/08. `/health` devolve o commit rodando; rollback é `bash deploy/atualizar.sh <sha>` | `RUNBOOK-VM.md` |
| **P2-4** comentário errado sobre região | ✅ **fechado.** O comentário agora explica as duas restrições e por que sobra uma região só | `deploy/provisionar-azure.sh:8-14` |
| **P2-5** RAM apertada | ⏳ **ABERTO — é o único.** Espera decisão do dono sobre redimensionar a VM | — |
| **P2-6** sem testes automatizados | ✅ **fechado.** 594 testes no `pytest`, rodados antes de mergear | `python -m pytest` |
| **P2-7** `web/.gitignore` untracked | ✅ **fechado.** Versionado | `git ls-files web/` |

**A lição que este documento passou a carregar:** relatório de segurança em repositório público
envelhece para o lado errado. Enquanto a correção não sobe, ele é um mapa; depois que sobe e
ninguém o carimba, ele vira uma mentira que soa autorizada. **Carimbe na hora do fix, não depois.**

---

## Veredito em uma linha — *como estava em 19/08/2026*

A infraestrutura está de pé e saudável (VM rodando, TLS válido, Caddy ok, front no ar), mas o sistema
**não faz nada e está aberto para qualquer um na internet**. Dois problemas P0 anulam o resto.

> Daqui para baixo, tudo está no presente do dia 19/08 e **os dois P0 já foram corrigidos** — ver
> a tabela de estado no topo. O texto original fica preservado porque o raciocínio é o valor: é
> ele que explica por que a guarda de hoje foi desenhada sem bandeira de desligar.

| Camada | Estado |
|---|---|
| VM Azure (`vm-cripto-bot`, northcentralus) | 🟢 running, disco 8%, swap ok, fuso America/Sao_Paulo |
| Caddy + TLS | 🟢 ativo, HTTPS válido, HTTP/3, portas 22 (só seu IP) / 80 / 443 |
| Serviço `cripto-bot` | 🟢 active, restart automático, uvicorn em 127.0.0.1:8000 |
| Front (Vercel) | 🟢 200, aponta pro backend certo, CORS negociando ok |
| **Autenticação** | 🔴 **desligada — painel e todos os POSTs abertos na internet** |
| **Dados de mercado** | 🔴 **Binance devolve 451 — o bot está cego, 504 falhas em 33 min** |
| Banco de produção | ⚪ vazio (0 sinais, 0 posições, 0 trades) — consequência do item acima |

---

## ✅ P0-1 — O backend está aberto para a internet inteira · **CORRIGIDO**

> **Constatação ao vivo removida deste documento em 2026-08-26.** Ela listava, rota por rota, o
> que respondia sem credencial — e o repositório é público. O achado está preservado; o mapa de
> ataque não precisa estar. Hoje toda rota citada responde **401**.

**Causa:** no `.env` da VM, `DASH_PASS=` está **vazio** e `PERMITIR_SEM_SENHA=1`. A guarda do
[api.py:140-152](api.py#L140-L152) foi projetada para recusar acesso externo sem senha — mas o
`PERMITIR_SEM_SENHA` a desliga por completo, e foi exatamente o que está setado em produção.

**Impacto (em 19/08):** qualquer pessoa que descobrisse o hostname alcançava as rotas destrutivas
e as de configuração. Era dinheiro fictício — mas é o mesmo painel que um dia encosta em dinheiro
de verdade, e o histórico de pesquisa já é perda real se apagado.

**Correção — aplicada, e mais forte do que o que este documento pediu:** a bandeira não foi
desligada, foi **removida do código**, porque guarda que se desliga por variável de ambiente não é
guarda. E o `/reset` ganhou confirmação explícita (`{"confirmar": "RESET"}`), que era o item 4
abaixo. O que foi pedido em 19/08:

1. Gerar uma senha forte, pôr em `DASH_PASS` e **remover** `PERMITIR_SEM_SENHA` do `.env`; `systemctl restart cripto-bot`.
2. Corrigir o front antes disso (ver P1-2), senão a senha fica impraticável de usar.
3. Desligar `/docs` e `/openapi.json` em produção (`FastAPI(docs_url=None, openapi_url=None)` quando `DASH_PASS` estiver setado).
4. Considerar mover `/reset` para trás de uma confirmação explícita — é destrutivo e irreversível.

---

## 🔴 P0-2 — O bot está cego: Binance bloqueia o IP da VM (HTTP 451)

```
scan falhou BCH/USDT 1h: binance GET .../api/v3/exchangeInfo 451
"Service unavailable from a restricted location according to 'b. Eligibility'"
```

`/status` reporta `total: 72, ok: 0, falhas: 72, saudavel: false`. **504 falhas** registradas no log
em 33 minutos. Banco de produção: 0 sinais, 0 posições, 0 trades — nunca teve dado nenhum.

**Causa raiz — confirmada por teste direto:** a Binance recusa IPs dos EUA. A VM está em
`northcentralus`. Do seu PC no Brasil, a mesma chamada devolve `200` e o preço do BTC normalmente.
Não é bug de código, rede ou credencial: é a **região da VM**.

**Correção — mover a VM para fora dos EUA.** O comentário do
[provisionar-azure.sh:8](deploy/provisionar-azure.sh#L8) diz que *"Brazil South NÃO oferece a família B"* —
**isso está incorreto**. Verificado agora:

| Região | Família B disponível | Quota vCPU | Nota |
|---|---|---|---|
| **brazilsouth** | `B2als_v2` (2 vCPU/4 GiB), `B2as_v2`, `B1s` | 0/6 livre | 🏆 mesmo país, menor latência, sem geo-bloqueio |
| francecentral | `B2ats_v2` e família B v2 | 0/6 livre | alternativa |
| germanywestcentral | idem | 0/6 livre | alternativa |
| ~~canadacentral~~ | disponível | — | ⚠️ a Binance também restringe o Canadá |

Recomendação: **brazilsouth com `Standard_B2als_v2`** — resolve o bloqueio, corta a latência até a
Binance e ainda quadruplica a RAM (4 GiB contra 1 GiB de hoje, que já está em 536/897 MB usados).
Como a conta é *Azure for Students* (crédito, não free-tier de 750 h), o tamanho não precisa ficar
preso ao `B2ats_v2`.

> Alternativa se a região tiver de ficar onde está: trocar a exchange de dados (`ccxt.binance` →
> `bybit`/`okx`/`kucoin`). Custa bem mais trabalho — `mercado.py` e `simulador.py` dependem de
> `binanceusdm` para funding — e é a opção pior.

---

## 🟠 P1 — Bugs de código

### P1-1 — Uma falha de rede paralisa o ciclo inteiro do worker *(provado em teste)*

[simulador.py:208](simulador.py#L208) chama `preco_ao_vivo(pos["ativo"])` dentro do `for` **sem
try/except**. Com uma posição aberta e a Binance fora do ar, `atualizar()` levanta, o `except` geral do
[api.py:65](api.py#L65) engole — e **nada mais do ciclo roda**: sem `avaliar_saida`, sem DCA, sem scan,
sem auto-trader e sem snapshot de equity.

O pior: a posição aberta fica **sem stop, sem trailing e sem checagem de liquidação** enquanto durar
a falha. Hoje não dispara só porque não há posição aberta — o `for` não itera.

**Correção:** envolver o corpo do `for` em try/except por posição (uma moeda que falha não pode
derrubar as outras nem o resto do ciclo) e contabilizar a falha num contador de saúde, como já é
feito no `scan()`.

### P1-2 — O front descarta a credencial a cada carregamento

[web/index.html:881](web/index.html#L881) executa `localStorage.removeItem('cbAuth'); _cred='';` na
inicialização — **todo F5 joga fora o login**. Com `DASH_PASS` ativo, isso obriga a digitar usuário e
senha em dois prompts a cada refresh. É quase certo que foi essa fricção que levou a desligar a senha
no servidor (P0-1); corrigir isto é pré-requisito para reativar a autenticação.

**Correção:** remover a linha. A limpeza de credencial já acontece corretamente no tratamento de 401
([web/index.html:343-345](web/index.html#L343-L345)), que é o lugar certo.

### P1-3 — `/trades?limite` sem teto

[api.py:296](api.py#L296): `limite: int = 50` vai direto para o `LIMIT` do SQLite.
`/trades?limite=100000000` faz o servidor materializar a tabela toda em memória — num host com 1 GiB
e sem autenticação, é um DoS de uma linha de curl. **Correção:** capar (`min(limite, 500)`), e o mesmo
em `/candles?limite`.

### P1-4 — `_amostrar()` não reduz nada entre 126 e 249 pontos

[api.py:245](api.py#L245): `passo = len(seq) // alvo` vale 1 nessa faixa, então a série volta inteira.
Medido: 249 pontos entram, 249 saem; 250 entram, 126 saem. A economia de banda que a função existe
para fazer só começa no dobro do alvo. **Correção:** usar passo fracionário (índices por `round(i*len/alvo)`).

### P1-5 — `breadth()` conta o ativo antes de poder falhar

[mercado.py:53-55](mercado.py#L53-L55): `tot += 1` vem **antes** de `soma += p`. Se `percentage` vier
`None`, o `TypeError` cai no `except`, mas o ativo já entrou no denominador — distorcendo
`pct_subindo` e `variacao_media`. Item que sobrou da auditoria de junho. **Correção:** validar `p`
antes de incrementar qualquer contador.

---

## 🟡 P2 — Operação e deploy

| # | Problema | Correção |
|---|---|---|
| P2-1 | **Sem rotação de log.** `plataforma.log` cresce sem limite — 200 KB em 33 min no ritmo atual de erro. Vai encher o disco em algum mês silencioso. | `logrotate` diário com `rotate 7 / compress`, ou trocar o `FileHandler` por `RotatingFileHandler` no [logbot.py:10](logbot.py#L10) |
| P2-2 | **Sem backup do `trading.db`.** Todo o histórico de pesquisa vive num arquivo só, numa VM só, sem cópia. Um `POST /reset` anônimo (P0-1) apaga tudo. | cron diário com `sqlite3 trading.db ".backup"` + cópia para fora da VM |
| P2-3 | **A VM não é um repositório git** — o deploy foi cópia manual. Sem rastreabilidade de qual commit está rodando e sem rollback. Hoje os md5 batem com a árvore local, mas isso é sorte, não processo. | `git clone` na VM + script de deploy (`git pull && systemctl restart`), ou registrar o commit no `/health` |
| P2-4 | **Comentário incorreto** no [provisionar-azure.sh:8](deploy/provisionar-azure.sh#L8) sobre Brazil South — foi o que empurrou o deploy para os EUA e causou o P0-2. | corrigir junto com a migração de região |
| P2-5 | **RAM apertada:** 536 MB de 897 MB usados, 360 MB livres, com `MemoryMax=900M` no service. Pandas com 24 moedas × 3 timeframes vai encostar no teto. | resolvido de graça ao migrar para `B2als_v2` (4 GiB) |
| P2-6 | **Sem testes automatizados rodando.** Existe `test_sim.py`, mas o pytest não está instalado nem local nem na VM. Nenhum CI. | `pip install pytest` + rodar antes de cada deploy |
| P2-7 | `web/.gitignore` está sem commit (untracked). | `git add web/.gitignore` |

---

## ✅ O que está certo (e vale não quebrar)

- **TLS e proxy reverso corretos:** Caddy com Let's Encrypt, uvicorn preso em `127.0.0.1`, porta 8000 fechada no NSG, SSH restrito ao seu IP. A topologia de rede está bem feita.
- **`/status` agora denuncia cegueira** (`saudavel: false` quando o scan roda e nenhuma moeda responde) — foi essa instrumentação, do commit `d9b21fe`, que tornou o P0-2 visível em vez de silencioso.
- **Dependências idênticas** entre local e VM (fastapi 0.136.3, ccxt 4.5.56, pandas 3.0.3, Python 3.12).
- **Nenhum segredo versionado** — `.env` fora do git, só o `.env.example` com placeholder, e `chmod 600` correto na VM.
- **Guardas de risco íntegras:** trava diária sticky, teto de risco-até-o-stop, teto de margem, lock de abertura contra TOCTOU, cap de perda na margem.
- **A maioria dos bugs ALTA/MÉDIA da auditoria de junho está fechada:** candle fechado no live (fim do repaint), funding aplicado no P&L, settlement por moeda, liquidação coerente com o `LIQ_BUFFER`, empate stop-vs-liquidação, R-múltiplos (`sqn_r`, `expectancia_r`), Sharpe por período, drawdown mark-to-market.

---

## Ordem sugerida — **executada; sobrou o P2-5**

> Os cinco passos abaixo foram cumpridos. O único item deste relatório que continua aberto é o
> **P2-5 (RAM)**, e ele não é trabalho parado: é decisão de custo que espera o dono.

1. **P0-2 primeiro** (migrar a região) — sem dado de mercado, todo o resto é enfeite num sistema que não roda.
2. **P1-2 depois** (front parando de apagar a credencial) — pré-requisito prático do próximo item.
3. **P0-1** (religar a senha, remover `PERMITIR_SEM_SENHA`, fechar `/docs`).
4. **P1-1** (try/except por posição) — antes de existir posição aberta de verdade, que é quando o bug morde.
5. P1-3 a P1-5, depois P2 na ordem da tabela.
