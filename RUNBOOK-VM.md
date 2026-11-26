# RUNBOOK-VM.md — operar a VM do cripto-bot

**Versão completa do operacional que o `CLAUDE.md` §5 resume.** Tudo aqui foi executado de
verdade em 2026-08-22 (backup, transferências, deploy do M1); nada é teoria.

## 0. Produção saiu da Azure em 2026-11-02

A assinatura foi suspensa em 02/11 02:30 UTC (`SpendingLimitReached`, crédito de US$100 de
estudante) e desalocou a VM. Quem consumiu foi a `vm-dev-box`, na mesma assinatura. Disco e blob
seguem lá, inacessíveis até reativar: **o histórico anterior a 02/11 só existe neles.** O resto
deste runbook descreve a VM e **não vale para o dl380**.

| | |
|---|---|
| Host | dl380 do Rogério, contêiner `arthur` (`ssh dl380`, login do Cloudflare Access vence em 24 h) |
| App | `/home/cripto/cripto-bot/`, usuário `cripto`, serviço systemd `cripto-bot` em `127.0.0.1:8000` |
| Unit | a de `deploy/cripto-bot.service` trocando `ubuntu` por `cripto`, mais `Environment=TZ=America/Sao_Paulo` (o contêiner é UTC e compartilhado) |
| Entrada | Tailscale Funnel, tailnet do dono: `https://arthur-dl380.taild8de53.ts.net` |
| Python | 3.12 por `uv`, no usuário `cripto`; o sistema tem 3.13 e o CI roda 3.12 |

**`cripto-deploy` não existe aqui**, e `deploy/atualizar.sh` tem o caminho da VM fixo. **Backup
ainda não existe**: disco único, sem cron, e o blob está fora. Medido em 02/11 com `auto_trade=0`:
1,5% de uma thread, 387 MB de RAM, 72/72 no scan.

### 0.1 A conta R (dinheiro real), no dl380

Unit: `deploy/cripto-bot-r.service` (cabeçalho com a instalação). Desde o `[LIVE-14]` a R roda
**isolada das outras três** (o procedimento está em "Isolar a chave", abaixo):

| | |
|---|---|
| Usuário | `cripto-r`, de sistema, sem shell de login. A, B e C seguem como `cripto` |
| Código | `/opt/cripto-r/app`, checkout próprio, de root. O `git pull` da A não o troca |
| Python | `/opt/cripto-r/venv` (e o interpretador em `/opt/cripto-r/python`), de root |
| Estado | `/var/lib/cripto-r/` (700 `cripto-r`): `corretora.env`, `r.env`, `trading.db`, `plataforma.log`, `backup/` |
| Rede | porta 8003 só em loopback; o painel a alcança por `/testeR` na A |

Todo comando abaixo roda **no servidor**, com caminho absoluto (o `arthur` não entra em
`/home/cripto`). `deploy/r.sh` é o `python -m execucao` com o ambiente da R:
`sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh ...` (sem shell de login não atrapalha: o
`sudo -u` roda o `bash` direto). Nada da R mora em pasta que o `cripto` escreva.

**A escada para ligar** (cada degrau só depois do anterior conferido):

```bash
# 0. Antes: chave do DEMO no corretora.env, unit instalada, canal de alerta da R definido.
#    Telegram (o token não passa por chat nem por linha de comando: `-` lê da entrada padrão):
#      sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh config telegram_token=- telegram_chat_id=<id>  # cola, Enter (sem eco)
#    ou push: abrir o painel na aba Conta real e inscrever o aparelho.

# 1. PAPEL com a estratégia da A (risco da A, decisão do dono em 25/11) e os números desta conta.
#    `config-de` lê o banco da A só para leitura e NÃO copia auto_trade, corretora*, banca,
#    teto de perda nem Telegram. (Feito em 26/11.) Para refazer: o `cripto-r` não lê
#    /home/cripto, então a cópia do banco da A é feita pelo `cripto` (dono dele, com o python
#    dele) e entregue por root; root não roda python do `cripto` nem abre o banco dele.
#    Confira antes onde está o banco da A: `sudo grep DB_PATH /home/cripto/cripto-bot/.env`.
sudo -u cripto /home/cripto/cripto-bot/venv/bin/python /home/cripto/cripto-bot/deploy/backup_banco.py \
     /home/cripto/cripto-bot/trading.db /tmp/copia-a --manter 1     # imprime o nome da cópia
sudo install -o cripto-r -g cripto-r -m 600 /tmp/copia-a/trading-*.db /var/lib/cripto-r/copia-a.db
sudo rm -rf /tmp/copia-a
#    O comando imprime todos os limites como ficaram: leia antes do degrau 2.
sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh config-de /var/lib/cripto-r/copia-a.db \
     banca_alocada=200 perda_total_max=60 \
     noite_ativo=1 noite_inicio=19:30 noite_fim=08:15     # ajuste à hora em que o dl380 desliga/volta
sudo rm /var/lib/cripto-r/copia-a.db

# 2. DEMO (dinheiro de mentira, ordens de verdade). auto_trade tem de estar 0 para trocar.
sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh config corretora=demo
sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh estado          # confere conta x livro

# 3. Para o real: feche tudo no demo, volte ao papel, zere o livro, troque a chave no
#    /var/lib/cripto-r/corretora.env (BINANCE_KEY/BINANCE_SECRET) e entre em binance SEM enviar nada.
sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh config corretora=papel
sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh reset RESET     # zera o livro (recusa se já houve dinheiro real)
sudo systemctl restart cripto-bot-r                                 # recarrega o corretora.env
sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh config corretora=binance corretora_dry_run=1   # imprime TODOS os limites
sudo journalctl -u cripto-bot-r -n 80 --no-pager                    # as ordens montadas, nenhuma enviada

# 4. Envio real: só aqui, no servidor (pelo painel é recusado).
sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh config corretora_dry_run=0

# 5. O dono liga o auto_trade (painel ou `config auto_trade=1`). Nada liga sozinho.
```

Na conta R, em QUALQUER modo, o painel **só aperta**: teto por ordem, banca, perda total,
risco, exposição e alavancagem não sobem por HTTP, e o canal de alerta (Telegram) não muda por
HTTP. Afrouxar é `sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh config chave=valor`, que
imprime os limites como ficaram. O teto de perda total é sticky e só solta subindo o teto,
também por aqui.

**Pânico sem painel:** `sudo cripto-panico-r`. Tenta o serviço; se ele não confirmar, PARA a
unit e fecha direto na corretora. A unit fica parada no fim: religar é ato seu. A cópia de root
sai do checkout de root, e de novo a cada deploy em que `deploy/panico.sh` mudar (leia o diff):

```bash
sudo install -o root -g root -m 755 /opt/cripto-r/app/deploy/panico.sh /usr/local/sbin/cripto-panico-r
sudo cmp /opt/cripto-r/app/deploy/panico.sh /usr/local/sbin/cripto-panico-r && echo igual
```

**Deploy da R.** Desde o `[LIVE-14]` a R tem checkout próprio: a receita do dl380 (o `git merge`
em `/home/cripto/cripto-bot` e o restart de A, B e C) **não troca o código da R**. A R vai para
o mesmo commit em seguida, por root, sempre por `git checkout` e nunca copiando arquivo:

```bash
SHA=<o commit da main que A, B e C acabaram de receber>
sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh config auto_trade=0   # congela (o deploy nunca religa)
sudo systemctl start cripto-bot-r-backup                                  # backup antes de trocar o código
sudo git -C /opt/cripto-r/app fetch -q origin
sudo git -C /opt/cripto-r/app diff --stat HEAD "$SHA" -- deploy/ requirements.txt   # o que muda fora do .py
sudo git -C /opt/cripto-r/app checkout -q --detach "$SHA"
sudo /opt/cripto-r/venv/bin/python -m compileall -q /opt/cripto-r/app/*.py   # portão; o __pycache__ fica de root
# Só se requirements.txt mudou (o uv de root, nunca o da home do cripto; o .lock que ele recria sai 0666):
#   sudo /opt/cripto-r/uv/bin/uv pip install --compile-bytecode --python /opt/cripto-r/venv/bin/python \
#        -r /opt/cripto-r/app/requirements.txt && sudo chmod 644 /opt/cripto-r/venv/.lock
# Só se a unit, o drop-in, o backup ou o pânico mudaram: os `install` do cabeçalho de cada um,
# do checkout de root, e `sudo systemctl daemon-reload`.
sudo systemctl restart cripto-bot-r
curl -s http://127.0.0.1:8003/health                                      # o commit novo, e "ok"
sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh estado
```

**Backup diário da R** (o banco do dinheiro real não tinha nenhum): timer do systemd
(`deploy/cripto-bot-r-backup.timer`, instalação no cabeçalho do `.service` dele), ao meio-dia de
São Paulo e, se o servidor estava desligado na hora, assim que ele liga. Não é cron: o cron das
03:17 caía com o dl380 desligado e nunca rodava. Cópia pela API de backup do SQLite (nunca `cp`
do banco vivo), `integrity_check` na cópia, permissão só do dono, 30 dias, em
`/var/lib/cripto-r/backup/`, como `cripto-r`. Manual: `sudo systemctl start cripto-bot-r-backup`
e `sudo journalctl -u cripto-bot-r-backup -n 3 --no-pager`. **Copie a pasta para fora do dl380**
de vez em quando: disco único.

**Chave sem restrição de IP (decisão do dono, 26/11/2026).** O IP de saída do dl380 é dinâmico:
chave presa a IP pararia a cada troca (-2015), com posição aberta. Então a chave real é criada
SEM IP, e o `corretora.env` leva `BINANCE_CHAVE_SEM_IP=1`. O que continua barrado: saque,
transferência, spot, margem, portfolio margin e opções. O risco aceito: se a chave vazar para
fora do servidor, quem a tiver opera a conta de futuros de qualquer lugar (não saca), até o saldo
dela. Por isso: na conta de futuros só o que se aceita perder; a chave não sai do dl380 (nem
backup, nem print, nem chat); `/status` mostra `chave_aviso`. A Binance pode APAGAR chave sem IP
que fique 30 dias sem uso: com a R parada esse tempo, crie outra. Quando houver IP fixo (proxy
num servidor com IP fixo, ou IP fixo do provedor), prenda a chave a ele e tire a linha.

**Isolar a chave (feito em 26/11/2026, `[LIVE-14]`).** As quatro units rodavam como `cripto`, e
quem tomasse o processo da A (exposto na internet) lia o `corretora.env` e o
`/proc/<pid>/environ` da R, lia e escrevia o banco dela e, o pior, **alterava o código que a R
executa** (o checkout e o venv da A são do `cripto`). Por isso a receita que estava aqui (usuário
novo + `setfacl` dando ao `cripto-r` leitura do código da A) não fechava o furo: a R seguiria
rodando código que o `cripto` escreve, e no restart seguinte rodaria o do invasor com o usuário
novo. Isolar exige que nada que a R execute ou leia seja gravável pelo `cripto`: código, venv,
interpretador, env files e a própria pasta de estado (fora de `/home/cripto`, que é dele e onde
ele poderia renomear a pasta da R e pôr outra no lugar). O que foi feito, com a R em papel,
`auto_trade=0`, sem posição e saldo zero:

```bash
# usuário
sudo useradd --system --user-group --home-dir /var/lib/cripto-r --no-create-home \
     --shell /usr/sbin/nologin cripto-r
# código: checkout próprio, de root
sudo install -d -o root -g root -m 755 /opt/cripto-r
sudo git clone -q https://github.com/ar1hu207/cripto-quant-platform.git /opt/cripto-r/app
sudo git -C /opt/cripto-r/app checkout -q --detach <sha>
# python: uv de root vindo do PyPI (o da home do cripto não serve: ele o altera), o mesmo
# CPython da A (3.12.16) baixado de novo, e as MESMAS versões de pacote da A (lista conferida
# com diff: 40 = 40)
sudo python3 -m venv /opt/cripto-r/uv && sudo /opt/cripto-r/uv/bin/pip install -q uv==0.13.6
sudo env UV_PYTHON_INSTALL_DIR=/opt/cripto-r/python UV_PYTHON_BIN_DIR=/opt/cripto-r/python/bin \
     /opt/cripto-r/uv/bin/uv python install 3.12.16
sudo env UV_PYTHON_INSTALL_DIR=/opt/cripto-r/python /opt/cripto-r/uv/bin/uv venv \
     --python /opt/cripto-r/python/cpython-3.12.16-linux-x86_64-gnu/bin/python3.12 /opt/cripto-r/venv
sudo /opt/cripto-r/uv/bin/uv pip install --compile-bytecode --python /opt/cripto-r/venv/bin/python \
     -r /opt/cripto-r/app/requirements.txt -c <versões da A>
sudo chmod 644 /opt/cripto-r/python/.lock /opt/cripto-r/venv/.lock     # o uv os cria 0666
# estado: R parada, backup (.backup + integrity_check) e então mv, sem ler nada
sudo systemctl stop cripto-bot-r-backup.timer cripto-bot-r
sudo install -d -o cripto-r -g cripto-r -m 700 /var/lib/cripto-r /var/lib/cripto-r/backup
sudo mv /home/cripto/cripto-bot-r/{corretora.env,trading.db,trading.db-wal,trading.db-shm,.conta,plataforma.log} /var/lib/cripto-r/
sudo mv /home/cripto/backup-r/* /var/lib/cripto-r/backup/
# r.env: só as chaves que a plataforma lê do ambiente (levantadas no código: DASH_USER,
# DASH_PASS, CORS_ORIGINS, VAPID_PUBLIC, VAPID_PRIVATE, VAPID_SUB; o resto vai no ExecStart)
sudo sh -c "umask 077; grep -E '^[[:space:]]*(DASH_USER|DASH_PASS|VAPID_PUBLIC|VAPID_PRIVATE|VAPID_SUB|CORS_ORIGINS)[[:space:]]*=' \
     /home/cripto/cripto-bot/.env > /var/lib/cripto-r/r.env"
sudo chown -R cripto-r:cripto-r /var/lib/cripto-r
sudo rmdir /home/cripto/cripto-bot-r /home/cripto/backup-r
# units do checkout de root; o pânico de novo, conferido com cmp
sudo install -m 644 /opt/cripto-r/app/deploy/cripto-bot-r.service /opt/cripto-r/app/deploy/cripto-bot-r-backup.service \
     /opt/cripto-r/app/deploy/cripto-bot-r-backup.timer /etc/systemd/system/
sudo install -D -m 644 /opt/cripto-r/app/deploy/cripto-bot-r.service.d/zzzz-depois-do-lxc.conf \
     /etc/systemd/system/cripto-bot-r.service.d/zzzz-depois-do-lxc.conf
sudo systemctl daemon-reload && sudo systemctl start cripto-bot-r cripto-bot-r-backup.timer
```

A, B e C não foram tocadas (units, código, permissões e `.env` como estavam; o `.env` da A só
foi lido para gerar o `r.env`). A rota `/testeR` da A segue falando com `127.0.0.1:8003`.

**Pendência (decisão do dono): a senha do painel da R é a da A.** O `r.env` nasceu copiado do
`.env` da A, então quem tomar a A conhece a `DASH_PASS` da R. Pelo HTTP os limites do dinheiro só
apertam, mas dá para ligar o `auto_trade` e disparar o pânico. Separar exige uma senha própria
no `r.env` e o painel mandando credencial diferente para a aba Conta real (hoje o repasse
`/testeR` da A usa a mesma).

**Endurecer a unit (feito em 26/11/2026, `[LIVE-14]`).** Primeiro a causa de o
`NoNewPrivileges=yes` da unit não valer (`systemctl show` dizia `no`, o processo tinha
`NoNewPrivs: 0`): o gerador `/etc/systemd/system-generators/lxc` do contêiner (distrobuilder)
grava a cada boot e `daemon-reload` o `/run/systemd/system/service.d/zzz-lxc-service.conf`, que
vale para **todo** serviço e põe `NoNewPrivileges=no`, `ProtectKernelTunables=no`,
`ProtectControlGroups=no` (e `ProtectProc`/`ProcSubset`/`PrivateNetwork` no padrão). Drop-in
vence a unit, e os drop-ins são aplicados pela ordem do nome do arquivo, de qualquer
diretório. Diretiva escrita na unit que esse arquivo também define não vale, e o
`override.conf` do `systemctl edit` ordena antes dele e também não vale. Por isso o drop-in da R
se chama `zzzz-depois-do-lxc.conf` e as três moram nele.

Teste: um drop-in `zzzz-teste.conf` (`systemctl edit --stdin --drop-in=zzzz-teste.conf`), uma
diretiva por vez, acumulando, com restart e espera de um ciclo completo, mais `/health`,
journal e log sem erro a cada passo, e no fim o scan da Binance (72/72, 0 falhas) dentro da
sandbox inteira. **O contêiner aceitou todas** (`NoNewPrivileges`, `PrivateTmp`,
`ProtectSystem=strict` + `ReadWritePaths=/var/lib/cripto-r`, `ProtectHome`, `PrivateDevices`,
`ProtectKernelTunables/Modules/Logs`, `ProtectControlGroups`, `RestrictAddressFamilies=AF_INET
AF_INET6 AF_UNIX`, `RestrictNamespaces`, `LockPersonality`, `RestrictSUIDSGID`,
`CapabilityBoundingSet=` vazio, `SystemCallFilter=@system-service`). Foram para a unit e para o
drop-in versionados, e o de teste saiu (`systemctl revert cripto-bot-r`, que só apaga drop-in:
a unit em `/etc` não tem versão de fornecedor e fica). `systemd-analyze security cripto-bot-r`:
**9.2 UNSAFE → 2.0 OK**. Conferir sempre no processo:

```bash
PID=$(systemctl show -p MainPID --value cripto-bot-r)
grep -E 'NoNewPrivs|CapBnd|Seccomp' /proc/$PID/status     # NoNewPrivs 1, CapBnd 0, Seccomp 2
```

Depois de mexer em unit ou drop-in: `restart` e `/health` (diretiva que o contêiner recusa
derruba o serviço no boot, com `status=226/NAMESPACE` ou parecido no journal). Se cair:
`sudo systemctl revert cripto-bot-r`, reinstalar a unit do checkout de root, e só depois o
drop-in.

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

A regra `ssh` do NSG está em **`Deny`** desde 2026-09-24. Ela liberava a porta 22 para um
único IP residencial dinâmico, e naquela data o IP liberado já não era o do
dono: a porta ficava aberta para quem herdasse aquele IP, e fechada para o dono. **Não
reabra a regra**: é fronteira do classificador (`CLAUDE.md` §8), e o caminho abaixo não
precisa dela.

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
| Action group | `ag-cripto-bot` (em `rg-cripto-bot`) → e-mail do dono |
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

### O que estes alertas NÃO pegam — e o que passou a pegar (2026-09-24)

As três regras veem a VM, nunca o processo. Processo morto com a VM viva, ciclo parado com
o processo vivo e banco que quebra o ciclo ficavam invisíveis. A afirmação que estava aqui
— *"quem cobriria é o `alertas.py`"* — **era falsa**: ele só avisa de trade aberto e fechado,
e de DENTRO do processo. Bot morto não manda mensagem dizendo que morreu. E publicar métrica
própria na Azure exige `az role assignment create`, que a assinatura Students recusa (§8 do
`CLAUDE.md`). O que cobre hoje, sem custo e sem token:

| camada | o quê | o que faz |
|---|---|---|
| auto-cura | `WatchdogSec=300` + `NotifyAccess=main` na unit; o worker avisa a cada ciclo COMPLETO (`api._sd_notify`) | 5 min sem ciclo → o systemd mata e o `Restart=always` devolve |
| sinal | `/health` público responde **503** com `"status": "ciclo parado"` e `ciclo_ha_s` | nos primeiros 300 s do processo responde 200 (restart de deploy não vira alarme) |
| aviso | `.github/workflows/vigia.yml`, a cada 15 min, 3 tentativas | falhou → o GitHub manda **e-mail** ao dono |

`trava do dia disparada` não é incidente: é a guarda funcionando, e o painel mostra.

⚠️ **A unit NÃO é instalada pelo `cripto-deploy`.** Depois de mergear uma mudança nela:

```bash
sudo cp /home/ubuntu/cripto-bot/deploy/cripto-bot.service /etc/systemd/system/cripto-bot.service
sudo systemctl daemon-reload && sudo systemctl restart cripto-bot
systemctl show cripto-bot -p WatchdogUSec -p NotifyAccess -p MemoryMax   # 5min / main / 796917760
```

O Telegram continua opcional, e para o que ele é: notificação de **trade**. As chaves já
estão no catálogo do `POST /config` e no `db.CONFIG_PADRAO`:

```bash
#   1. @BotFather no Telegram -> /newbot -> guardar o token
#   2. @userinfobot -> devolve o seu chat id
#   3. gravar (de dentro da VM; o backend só atende loopback sem credencial):
curl -s -X POST http://127.0.0.1:8000/config      -u "admin:$DASH_PASS" -H 'Content-Type: application/json'      -d '{"telegram_token":"<TOKEN>","telegram_chat_id":"<CHAT_ID>"}'
```

### O lock barra TODA exclusão no RG, não só a da VM

Descoberto testando, não deduzido: apagar uma regra de alerta dentro de `rg-cripto-bot` volta
`ScopeLocked`. O `CanNotDelete` vale para o grupo inteiro, então qualquer exclusão — alerta,
regra, recurso auxiliar — passa por tirar e recolocar:

```bash
az lock delete --name protege-cripto-bot -g rg-cripto-bot
# ... a operação que precisa apagar ...
az lock create --name protege-cripto-bot --lock-type CanNotDelete -g rg-cripto-bot
```

Não afeta escrita: o backup diário continua subindo blob normalmente com o lock no lugar
(conferido em 31/08 rodando o `cripto-backup.sh` com o lock ativo). O que ele impede é
exatamente o acidente que se quer impedir — um `az group delete` levar VM, disco, IP e o
storage dos backups de uma vez, que hoje moram todos no mesmo grupo.

**Rever quando:** o e-mail do action group mudar de dono · a VM mudar de tamanho (o teto de
100 MB foi calibrado para os 892 MiB de hoje) · o `MemoryHigh`/`MemoryMax` do §5 mudar.
