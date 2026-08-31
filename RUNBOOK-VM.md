# RUNBOOK-VM.md — operar a VM do cripto-bot

**Versão completa do operacional que o `CLAUDE.md` §5 resume.** Tudo aqui foi executado de
verdade em 2026-08-22 (backup, transferências, deploy do M1); nada é teoria.

## 1. Fatos

| | |
|---|---|
| VM | `vm-cripto-bot` · `rg-cripto-bot` · southafricanorth · `Standard_B2ats_v2` (1 GiB) |
| Host | `cripto-bot-24517.southafricanorth.cloudapp.azure.com` |
| App | `/home/ubuntu/cripto-bot/` · serviço systemd `cripto-bot` · uvicorn em `127.0.0.1:8000` |
| Banco | `/home/ubuntu/cripto-bot/trading.db` (SQLite — a única cópia viva) |
| Venv | `/home/ubuntu/cripto-bot/venv/` — use `venv/bin/python` para compilar/testar |
| API | atrás de auth (`DASH_PASS`); sem credencial, tudo responde 401 |

## 2. Acesso: esqueça o SSH, use o plano de controle

O NSG libera a porta 22 para **um único IP**, e o IP do dono é residencial dinâmico — o SSH
morre com *Connection timed out* toda vez que a rede dele muda, sem aviso. **Não conserte a
regra de NSG**: é fronteira do classificador (`CLAUDE.md` §8).

O caminho que sempre funciona não passa pela rede:

```bash
az vm run-command invoke -g rg-cripto-bot -n vm-cripto-bot \
  --command-id RunShellScript --scripts @script.sh \
  --query "value[0].message" -o tsv
```

**As três armadilhas (todas mordidas na prática):**

1. **Sempre `--scripts @arquivo`, nunca inline.** Inline quebra com aspas aninhadas
   (`sqlite3 "SELECT ..."` dentro de `echo "..."`) e **morre no meio deixando estado parcial**;
   e acima de ~30 KB estoura o limite de linha de comando do Windows. Um `@arquivo` de 38 KB
   passou sem problema.
2. **A saída trunca em 4.095 caracteres.** Planeje o script para imprimir só o que importa
   (contagens, hashes, `tail -n`), não dumps.
3. **Uma execução por vez.** Chamada durante outra devolve `Conflict`. Cada chamada custa
   ~45 s (a Azure provisiona a execução). **Não ponha loop com `sleep` dentro do script** —
   bloqueia as chamadas seguintes por minutos.

## 3. Levar arquivo para a VM

Empacote, base64, e monte o script de envio programaticamente:

```bash
tar -czf /tmp/pacote.tgz arq1.py arq2.py
base64 -w0 /tmp/pacote.tgz > pacote.b64          # ~1.33x o tamanho
sha256sum /tmp/pacote.tgz                          # guarde para conferir lá
# gere envio.sh contendo:  echo '<b64>' | base64 -d > /tmp/pacote.tgz
#                          sha256sum /tmp/pacote.tgz   (confira contra o local!)
#                          tar -xzf /tmp/pacote.tgz -C /tmp/stage
az vm run-command invoke ... --scripts @envio.sh
```

Sempre para `/tmp/stage` primeiro — **nunca direto por cima do que roda** — e compile lá com o
Python de produção (`/home/ubuntu/cripto-bot/venv/bin/python -m py_compile ...`) antes da troca.

## 4. Trazer arquivo da VM

**Prefira o blob** — desde 22/08 é o caminho barato: mande a VM subir
(`curl -X PUT -H 'x-ms-blob-type: BlockBlob' --data-binary @arq "https://criptobotbkp28836.blob.core.windows.net/trading-db/<nome>?<SAS>"`)
e baixe do blob com `az storage blob download --auth-mode key`.

O caminho antigo (fatiar `base64 | cut -c<ini>-<fim>` em janelas de 4.000 chars pelo
run-command) funciona mas custa caro: 215 KB = 54 chamadas = ~40 minutos. Só use se o blob
estiver indisponível.

## 5. Deploy

### 5.0 O caminho normal, desde 2026-08-22 (`P2-3` fechado)

A VM **é** repositório git. `/home/ubuntu/cripto-bot` está na branch `main`, com árvore limpa, e
autentica no GitHub por **deploy key SSH somente-leitura** (`/home/ubuntu/.ssh/deploy_cripto`,
600; a pública é deploy key read-only do repo). ⚠️ **O repositório é PÚBLICO** —
conferido em 31/08 por `gh repo view ar1hu207/cripto-quant-platform --json visibility`.
A chave não guarda segredo de leitura nenhum: o que ela garante é que a VM **não consegue
dar push**. Não escreva nada no repo contando com privacidade. Deploy é um comando:

```bash
az vm run-command invoke -g rg-cripto-bot -n vm-cripto-bot --command-id RunShellScript   --scripts @deploy.sh --query "value[0].message" -o tsv
# onde deploy.sh contém:
#   cd /home/ubuntu/cripto-bot
#   sudo -u ubuntu git fetch -q origin
#   sudo -u ubuntu bash -c 'git show origin/main:deploy/atualizar.sh > ~/.deploy-tmp/atualizar.sh'
#   sudo -u ubuntu bash ~/.deploy-tmp/atualizar.sh          # ou:  cripto-deploy
```

O `deploy/atualizar.sh` versionado faz a §5.1 inteira sozinho e **para** em cada portão: aborta
com árvore suja, aborta se o backup falhar, aborta voltando ao commit anterior se o `py_compile`
falhar no venv de produção. **Não religa o `auto_trade`** — imprime o comando. Ao final imprime
também o rollback pronto: `bash deploy/atualizar.sh <sha-anterior>`.

Qual commit está rodando: `curl -s http://127.0.0.1:8000/health` (único endpoint sem auth).

Três armadilhas descobertas no primeiro uso real:

1. **Rode como `ubuntu`, não como root.** O repositório é do `ubuntu`; git como root deixa objetos
   root-owned e o próximo `git status` reclama de *dubious ownership*. O script usa `sudo` só nos
   dois passos que precisam (backup e `systemctl`).
2. **O backup precisa de `sudo`** — lê `/etc/cripto-bot-backup.sas` (600 root) e escreve em
   `/var/log/cripto-backup.log`. Sem isso o deploy aborta no passo 1, corretamente.
3. **Não escreva o script em `/tmp` como root se já existir um lá de outro dono**:
   `fs.protected_regular` bloqueia, o redirect falha em silêncio e a **versão velha** roda. Use
   `~ubuntu/.deploy-tmp/`.

### 5.1 Passo a passo manual (o que o script automatiza)

Vale como referência, e é o caminho a seguir se o script estiver indisponível. **Commit na `main`
não significa código rodando** — o deploy continua sendo um ato deliberado. Ordem obrigatória:

1. **Backup imediato**: `/usr/local/bin/cripto-backup.sh` (roda o fluxo completo e sobe ao blob)
2. **Snapshot para rollback**: `cp *.py /home/ubuntu/rollback-$(date +%Y%m%d-%H%M%S)/`
3. **md5 dos arquivos que vão mudar** — é a prova do antes/depois
4. **`auto_trade=0`** (`UPDATE config SET valor='0' WHERE chave='auto_trade'`) **e** conferir
   `SELECT COUNT(*) FROM posicoes WHERE status='aberta'` — ideal deployar com zero
5. **Staging**: enviar para `/tmp/stage` (§3), conferir sha256, `py_compile` com o venv
6. **Troca**: `cp /tmp/stage/*.py .` + `chown ubuntu:ubuntu` + `systemctl restart cripto-bot`
7. **Verificar, nesta ordem**: `systemctl is-active` · `journalctl -u cripto-bot -n 10`
   (procurar "worker iniciado", zero traceback) · `PRAGMA integrity_check` · contagens de
   `sinais/trades/banca` iguais às de antes · equity nova sendo gravada
   (`SELECT COUNT(*) FROM equity WHERE ts > '<hora do restart>'` crescendo = ciclo vivo)
8. **Só então** `auto_trade=1`

Se a trava diária estiver ativa (`config.trava_dia_em` = hoje), o bot não abre posição mesmo
ligado — **é comportamento correto**, ver `CLAUDE.md` §2. Não limpe.

## 6. Backup

| | |
|---|---|
| Agendamento | `/etc/cron.d/cripto-backup` — diário às **03:17** |
| Script | `/usr/local/bin/cripto-backup.sh` · log em `/var/log/cripto-backup.log` |
| Fluxo | `sqlite3 .backup` → `integrity_check` (aborta se falhar) → `gzip -9` → PUT no blob → retenção local 7 dias |
| Destino | conta `criptobotbkp28836`, container privado `trading-db` |
| Credencial | SAS em `/etc/cripto-bot-backup.sas` (600, root) — permissão **`cw` apenas**: cria e escreve, não lê/apaga/lista |

⚠️ **O SAS expira em 2027-08-22.** Rotação: `az storage container generate-sas --account-name
criptobotbkp28836 -n trading-db --permissions cw --expiry <data> --https-only --auth-mode key`
e regravar o arquivo na VM. (Identidade gerenciada seria melhor — zero segredo em disco — mas a
assinatura *Azure for Students* recusa `role assignment` com `MissingSubscription`, mesmo Owner.)

**Restaurar**: baixar do blob → `gunzip` → conferir `integrity_check` e contagens → parar o
serviço → trocar o `trading.db` → subir. Nunca trocar com o serviço rodando.

**Backup manual imediato** (ex.: antes de mexer no banco): rodar o próprio
`/usr/local/bin/cripto-backup.sh` via run-command — já verifica e já sobe.

## 7. Diagnóstico rápido (colar num `@script.sh`)

```bash
cd /home/ubuntu/cripto-bot
systemctl is-active cripto-bot
journalctl -u cripto-bot -n 10 --no-pager | grep -ciE "traceback|error"
sqlite3 trading.db "PRAGMA integrity_check;"
sqlite3 trading.db "SELECT 'abertas='||COUNT(*) FROM posicoes WHERE status='aberta';"
sqlite3 trading.db "SELECT 'banca='||ROUND(atual,2) FROM banca;"
sqlite3 trading.db "SELECT 'auto='||valor FROM config WHERE chave='auto_trade';"
sqlite3 trading.db "SELECT 'trava='||valor FROM config WHERE chave='trava_dia_em';"
sqlite3 trading.db "SELECT 'equity_10min='||COUNT(*) FROM equity WHERE ts > datetime('now','localtime','-10 minutes');"
```

A última linha é o teste de vida do worker: zero por mais de ~1 min = ciclo parado.

## 8. Observabilidade — o que avisa, e o que não avisa

Montado em 2026-08-31. Antes disso não existia canal nenhum: se a VM morresse às 3h da manhã,
a descoberta era abrir o painel e reparar.

| Recurso | O quê |
|---|---|
| Action group | `ag-cripto-bot` (em `rg-cripto-bot`) → e-mail `abonizioa10@gmail.com` |
| `cripto-vm-fora-do-ar` | sev 1 · `VmAvailabilityMetric < 1` · janela e avaliação de 5 min |
| `cripto-memoria-baixa` | sev 2 · `Available Memory Bytes < 104857600` (100 MB) · 5 min |
| `cripto-creditos-cpu-acabando` | sev 3 · `CPU Credits Remaining < 30` · 15 min |
| Boot diagnostics | ligado (managed) — screenshot e serial console quando a VM não sobe |
| Lock | `protege-cripto-bot`, `CanNotDelete`, no RG inteiro (VM, disco, IP e storage de backup) |

As três regras usam **métrica de plataforma**: são medidas pelo host, não por agente dentro da
VM, então continuam reportando mesmo com o convidado travado. Custo: `Alerts Metric Monitored`
a US$ 0,10/mês por regra, e as 10 primeiras entram no grant gratuito.

O de crédito de CPU é o menos óbvio e o mais específico desta máquina: `B2ats_v2` é
**burstable**. Sem crédito, a CPU cai para a baseline e o ciclo do worker degrada **sem erro no
log** — o sintoma é lentidão, não exceção, e o teste de vida do §7 continua verde enquanto isso.

### O que estes alertas NÃO pegam

Processo do bot morto com a VM viva · ciclo parado com processo vivo · banco corrompido ·
trava do dia disparada. Nada disso tem métrica de plataforma. Quem cobriria é o `alertas.py`,
que **está desligado** — o código existe desde o Sprint 7 e sem token é no-op.

```bash
# Ligar o Telegram. As chaves já estão no catálogo do POST /config (api.py:321-322) e no
# db.CONFIG_PADRAO — é config de banco, nunca constante no módulo (CLAUDE.md §1).
#   1. @BotFather no Telegram -> /newbot -> guardar o token
#   2. @userinfobot -> devolve o seu chat id
#   3. gravar (de dentro da VM; o backend só atende loopback sem credencial):
curl -s -X POST http://127.0.0.1:8000/config      -u "admin:$DASH_PASS" -H 'Content-Type: application/json'      -d '{"telegram_token":"<TOKEN>","telegram_chat_id":"<CHAT_ID>"}'
```

**Rever quando:** o e-mail do action group mudar de dono · a VM mudar de tamanho (o teto de
100 MB foi calibrado para os 892 MiB de hoje) · o `MemoryHigh`/`MemoryMax` do §5 mudar.
