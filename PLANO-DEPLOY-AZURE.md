# Plano de Deploy — Bot de Trading (FastAPI) na Azure + Front no Vercel

Documento de handoff. Self-contained: dá pra ler sem acesso ao repositório.

**Stack:** Python 3.12 · FastAPI + uvicorn · SQLite (WAL) · front HTML/JS estático
**Alvo:** VM Ubuntu 24.04 na Azure (Azure for Students) + Caddy (TLS) + Vercel (front)
**Status:** provisionamento roteirizado, ainda **não executado**

---

## 1. O que é o sistema

Plataforma de **paper trading** de cripto (dinheiro fictício). Um processo FastAPI serve a API
e o painel, e **uma thread worker** roda em background a cada 15 s: marca posições a preço de
mercado, fecha stop/liquidação, roda scan de sinais e grava snapshot de equity.

Dados de mercado vêm da Binance via `ccxt`, **somente endpoints públicos**. Não existe chave de
exchange no projeto, não há custódia e não há ordem real — o que limita bastante o impacto de
um comprometimento.

### Restrições que ditam o desenho

| Restrição | Consequência |
|---|---|
| Worker é **singleton** | 1 instância só. Nada de escala horizontal ou autoscale. |
| **SQLite com `journal_mode=WAL`** | Precisa de disco local. WAL não funciona confiável em filesystem de rede. |
| Worker precisa ficar **vivo 24/7** | Serverless e tiers que hibernam estão descartados. |
| Estado no disco (`trading.db`) | Disco persistente obrigatório; é o histórico inteiro. |

---

## 2. Arquitetura alvo

```
Navegador (HTTPS)
   │
   ├──► Vercel (estático: web/)              index.html, config.js, vendor/*
   │
   └──► Caddy :443  (TLS Let's Encrypt automático)     ← VM Azure
             │  reverse_proxy
             ▼
        uvicorn 127.0.0.1:8000  (FastAPI + worker thread)
             │
             ▼
        SQLite WAL em disco local (Premium SSD P6)
```

O front no Vercel chama a API na VM via `window.API_BASE`. O backend também serve o mesmo
`web/index.html` em `GET /` como fallback.

---

## 3. Decisões e justificativa

### 3.1 VM, não App Service
App Service daria HTTPS grátis e Easy Auth, mas o `/home` persistente dele é **Azure Files
(rede)**. **SQLite em WAL não funciona de forma confiável em filesystem de rede** — WAL exige
memória compartilhada que o share não oferece. Risco de lock e corrupção de banco. VM com disco
local resolve.

### 3.2 Região: **South Africa North**

> ⚠️ **Revisado em 2026-08-20.** Esta seção dizia *"North Central US (não Brazil South)"* e
> justificava a escolha com uma afirmação **falsa** — que Brazil South não teria nenhum SKU da
> família B. Foi essa frase que pôs a VM nos EUA e deixou o bot cego por HTTP 451 durante todo
> o primeiro deploy (ver `STATUS-SISTEMA-2026-08-19.md`, cards [P0-2] e [P2-4] no Trello).
> A região em produção hoje é **`southafricanorth`** (commit `a84af4f`), e a decisão real é a
> interseção de duas restrições:
>
> 1. **Azure Policy da assinatura** (*"Allowed resource deployment regions"*) só aceita
>    `canadacentral`, `centralus`, `northcentralus`, `southafricanorth`, `spaincentral`.
> 2. **A Binance devolve 451** para IPs dos EUA e do Canadá — a VM funciona, mas o bot fica
>    cego. Isso elimina `centralus`, `northcentralus` e `canadacentral`.
>
> Sobra `southafricanorth` (`spaincentral` está na UE, também geo-bloqueada pela Binance).
>
> **Sobre a frase errada.** Brazil South *tem* a família B: a API `Microsoft.Compute/skus` lista
> **32 SKUs B** na região, o `B2ats_v2` inclusive. O que é verdade é uma coisa diferente — nesta
> **assinatura** todos os 32 voltam com `NotAvailableForSubscription`, e é por isso que
> `az vm list-skus -l brazilsouth` (sem `--all`) devolve lista vazia e o levantamento original
> concluiu "nenhum da família B". A conclusão operacional estava certa; o motivo, não. E a
> diferença importa: um limite de assinatura se resolve com quota/suporte, uma região que não tem
> o SKU, não. De todo modo a Azure Policy acima já barra `brazilsouth` antes disso.
>
> *Verificado em 2026-08-20 com `Microsoft.Compute/skus?$filter=location eq 'brazilsouth'` e
> `az policy assignment list`.* O parágrafo abaixo fica como registro do raciocínio original.

O usuário está em São Paulo, então Brazil South era o default óbvio. **Não é viável.**

~~Levantamento via `az vm list-skus` na assinatura real: Brazil South oferece 492 SKUs de VM,
**nenhum da família B** — a única família dentro do tier gratuito. O menor SKU disponível lá é
2 vCPU / 4 GiB.~~ *(incorreto — ver a revisão acima)* Preços reais (Azure Retail Prices API,
Linux, consumo):

| SKU (menor disponível em Brazil South) | US$/h | US$/mês | Crédito de US$ 100 dura |
|---|---|---|---|
| `Standard_D2als_v6` | 0,1290 | 94,17 | **1,1 mês** |
| `Standard_DC2as_v6` | 0,1460 | 106,58 | 0,9 mês |
| `Standard_D2s_v6` | 0,1610 | 117,53 | 0,9 mês |

Ficar no Brasil consome o crédito inteiro em ~1 mês. Fora do Brasil, a VM é **gratuita**.

**Latência não é critério aqui.** O único componente sensível é o navegador carregando o
painel — ~130 ms a mais numa página que faz poll a cada 3.000 ms. O bot fala com a Binance em
ciclos de 15 s, e os servidores da Binance ficam na Ásia (nem SP nem Chicago estão perto).

Regiões onde `Standard_B2ats_v2` está **liberada para esta assinatura** (23 no total; 12 vêm
com `NotAvailableForSubscription` e foram excluídas): `northcentralus`, `westcentralus`,
`canadaeast`, `chilecentral`, `koreacentral`, `swedencentral`, `southafricanorth`,
`polandcentral`, `eastasia`, entre outras.

~~`northcentralus` escolhida por ser região madura e sem restrição.~~ **Escolha revista em
2026-08-20: `southafricanorth`** — `northcentralus` é geo-bloqueada pela Binance (451) e a maior
parte da lista acima não passa na Azure Policy da assinatura. `chilecentral` (mais próxima do
Brasil) já havia sido descartada por ser região nova — risco de falta de capacidade — e também
não consta na policy.

### 3.3 Tamanho: `Standard_B2ats_v2` (AMD x64)

> **Nota de 2026-08-20 (card [P2-5]).** Em `southafricanorth` a assinatura tem liberado, entre
> outros, o `Standard_B2als_v2` (2 vCPU / **4 GiB**) — mesma região, resolvível com
> `az vm resize` e um reboot, sem reprovisionar nada. O custo da troca é sair das 750 h/mês
> gratuitas (que cobrem só `B2ats_v2` e `B2pts_v2`) e passar a consumir o crédito. É essa a
> decisão do [P2-5], depois de medir o pico de memória com o scan rodando de verdade.

O tier gratuito do Azure for Students dá **750 h/mês** de `B2pts v2` (ARM) **e** `B2ats v2`
(AMD). O mês tem ~730 h, então **uma** VM 24/7 cabe.

⚠️ **`B1s` saiu do tier gratuito.** Documentação e tutoriais antigos ainda mandam usar B1s;
hoje isso passa a consumir crédito (~US$ 8-10/mês).

Escolhido **AMD x64** e não ARM: a VM tem **1 GiB de RAM**. Se faltar wheel `aarch64` de algum
pacote, o `pip` compila do fonte e estoura a memória. `numpy`/`pandas` têm wheels ARM hoje, mas
x64 elimina a categoria de risco por ~US$ 0,001/h de diferença.

### 3.4 TLS: Caddy + DNS label da Azure

O front no Vercel é HTTPS, e **página HTTPS não pode chamar `http://IP:8000`** (mixed content
bloqueado pelo navegador). Logo o backend precisa de HTTPS — o que exige um hostname, já que
Let's Encrypt não emite para IP puro.

Solução sem custo: o **DNS name label** do Public IP da Azure gera
`<label>.southafricanorth.cloudapp.azure.com`, e o Caddy emite/renova o certificado sozinho.

### 3.5 Nota sobre o split front/backend
O backend já serve o front sozinho. Separar não traz ganho técnico neste momento — o backend
precisa de HTTPS de qualquer forma, e com HTTPS servir o `index.html` sai de graça. O split
custa CORS + rework de autenticação. Foi mantido por decisão do dono do projeto (o front deve
migrar para framework no futuro, onde preview-por-branch e CDN passam a valer).

---

## 4. Estado atual

**Feito:**
- Azure CLI 2.89.1 instalado e autenticado (`az login`)
- Assinatura *Azure for Students* ativa: US$ 100 / 100, expira em **18/08/2027**
- SKUs e restrições levantados; região e tamanho decididos
- Código preparado para o split (CORS, guarda de exposição, throttle, front em `web/`)
- Script de provisionamento escrito e validado (`bash -n`)

**Pendente:** executar o provisionamento e as fases 2-4 abaixo.

**Não foi possível pré-verificar cota:** `az vm list-usage` retorna vazio em assinatura de
estudante (limitação da própria API). Se a família `BASv2` estiver com cota 0, o `vm create`
falha com erro explícito → pedir aumento em *Subscription → Usage + quotas* (grátis) ou trocar
para outra região da lista da §3.2.

---

## 5. Fase 1 — Provisionamento (`deploy/provisionar-azure.sh`)

```bash
#!/usr/bin/env bash
set -euo pipefail

RG="rg-cripto-bot"
LOCAL="southafricanorth"
VM="vm-cripto-bot"
TAMANHO="Standard_B2ats_v2"
IMAGEM="Canonical:ubuntu-24_04-lts:server:latest"
USUARIO="ubuntu"                   # NÃO mudar: o systemd unit depende deste nome
DNS_LABEL="cripto-bot-${RANDOM}"
CHAVE="$HOME/.ssh/cripto-bot"
MEU_IP="${MEU_IP:-$(curl -sS https://api.ipify.org)}"   # detectado em runtime

# 1. chave SSH dedicada (ed25519)
[ -f "$CHAVE" ] || ssh-keygen -t ed25519 -N "" -f "$CHAVE" -C "cripto-bot"

# 2. resource group — tudo num grupo só, para blast radius contido
az group create --name "$RG" --location "$LOCAL" --output none

# 3. VM. --nsg-rule NONE porque o padrão abriria SSH para 0.0.0.0/0
az vm create \
  --resource-group "$RG" --name "$VM" --location "$LOCAL" \
  --image "$IMAGEM" --size "$TAMANHO" \
  --admin-username "$USUARIO" --ssh-key-values "${CHAVE}.pub" \
  --public-ip-sku Standard --public-ip-address-dns-name "$DNS_LABEL" \
  --os-disk-size-gb 64 --storage-sku Premium_LRS \
  --nsg-rule NONE --output none

# 4. regras de rede
NSG="$(az network nsg list -g "$RG" --query "[0].name" -o tsv)"
# --nsg-rule NONE normalmente ainda cria o NSG; o script real trata o caso de não ter
# criado (cria um e anexa à NIC) antes de aplicar as regras abaixo.
az network nsg rule create -g "$RG" --nsg-name "$NSG" --name ssh \
  --priority 1000 --access Allow --protocol Tcp --destination-port-ranges 22 \
  --source-address-prefixes "$MEU_IP" --output none
az network nsg rule create -g "$RG" --nsg-name "$NSG" --name http-acme \
  --priority 1010 --access Allow --protocol Tcp --destination-port-ranges 80 \
  --source-address-prefixes Internet --output none
az network nsg rule create -g "$RG" --nsg-name "$NSG" --name https \
  --priority 1020 --access Allow --protocol Tcp --destination-port-ranges 443 \
  --source-address-prefixes Internet --output none

# 5a. fuso horário — a VM nasce em UTC (ver §5.1)
az vm run-command invoke -g "$RG" -n "$VM" --command-id RunShellScript --output none \n  --scripts "timedatectl set-timezone America/Sao_Paulo"

# 5b. swap de 2 GB — 1 GiB de RAM é apertado para pandas
az vm run-command invoke -g "$RG" -n "$VM" --command-id RunShellScript --output none \
  --scripts "if ! swapon --show | grep -q /swapfile; then \
    fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && \
    swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab; fi"

# 6. saída
az vm show -d -g "$RG" -n "$VM" --query "{ip:publicIps, fqdn:fqdns}" -o table
```

**Portas:** 22 restrita ao IP do operador; 80 aberta (desafio ACME do Let's Encrypt + redirect);
443 aberta. **8000 permanece fechada** — o uvicorn escuta apenas em `127.0.0.1`.

`Source: Any` no 443 é necessário: o `fetch` do front roda **no navegador do usuário final**,
não nos servidores do Vercel. Travar por IP quebraria acesso via 4G/outra rede.

**Rollback:** `az group delete --name rg-cripto-bot --yes` apaga tudo.

### 5.1 Fuso horário — não é cosmético

A VM nasce em **UTC**. O `simulador.py` delimita "hoje" com `pd.Timestamp.now().date()` — hora
**local do servidor** — e essa data define a janela da **trava diária de perda** (bloqueia novos
trades quando o prejuízo do dia passa do limite).

Em UTC o dia viraria às **21:00 de Brasília**: a trava zeraria no meio da noite e a leitura de
"perda do dia" deixaria de bater com o que o operador vê. Por isso o provisionamento roda
`timedatectl set-timezone America/Sao_Paulo`.

Alternativa mais robusta (**não implementada**): tornar o corte de dia explícito no código, com
timezone fixo, em vez de depender do relógio do host.

---

## 6. Fase 2 — Backend na VM

```bash
ssh -i ~/.ssh/cripto-bot ubuntu@<FQDN>
sudo apt update && sudo apt install -y python3-venv python3-pip
```

Copiar código (da máquina local, raiz do projeto). **O `mkdir` é obrigatório** — `scp` não
cria o diretório de destino e falha sem ele:
```bash
ssh -i ~/.ssh/cripto-bot ubuntu@<FQDN> "mkdir -p ~/cripto-bot"

scp -i ~/.ssh/cripto-bot *.py requirements.txt   ubuntu@<FQDN>:/home/ubuntu/cripto-bot/
scp -i ~/.ssh/cripto-bot -r web/               ubuntu@<FQDN>:/home/ubuntu/cripto-bot/
scp -i ~/.ssh/cripto-bot deploy/cripto-bot.service deploy/cripto-bot.env.example \
                                                  ubuntu@<FQDN>:/home/ubuntu/cripto-bot/
```

Ambiente e configuração:
```bash
cd ~/cripto-bot
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp cripto-bot.env.example .env && chmod 600 .env
```

⚠️ Copiar **`web/` inteiro**, incluindo `web/vendor/` (chart.js e lightweight-charts servidos
localmente, sem CDN). O `estrategias/` **não** é usado pelo runtime — só pelos backtests.

`.env`:
```ini
DB_PATH=/home/ubuntu/cripto-bot/trading.db
DASH_USER=admin
DASH_PASS=<openssl rand -base64 24>
CORS_ORIGINS=https://<projeto>.vercel.app
```

`systemd` (`/etc/systemd/system/cripto-bot.service`) — o arquivo do repositório **já vem**
com bind em `127.0.0.1`, já que o Caddy é quem fala com a internet. Sem edição manual:
```ini
[Unit]
Description=Cripto Bot - FastAPI + worker 24/7
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/cripto-bot
EnvironmentFile=/home/ubuntu/cripto-bot/.env
ExecStart=/home/ubuntu/cripto-bot/venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
MemoryMax=900M

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now cripto-bot
curl -s localhost:8000/health      # {"status":"ok",...}
```

---

## 7. Fase 3 — TLS (Caddy)

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

`/etc/caddy/Caddyfile`:
```
cripto-bot-XXXX.southafricanorth.cloudapp.azure.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8000
}
```
```bash
sudo systemctl reload caddy
sudo journalctl -u caddy -f        # acompanhar emissão do certificado
```

Falha na emissão é quase sempre porta 80 fechada no NSG ou hostname divergente do DNS label.

---

## 8. Fase 4 — Front no Vercel

O front está isolado em **`web/`**. ⚠️ **Nunca apontar o Vercel para a raiz do repositório** —
publicaria `api.py`, `db.py` e o `trading.db` como arquivos estáticos baixáveis.

1. `web/config.js` → `window.API_BASE = "https://<FQDN>";` (obrigatoriamente `https`)
2. `cd web && vercel --prod` (ou painel: Root Directory `web`, Framework Preset *Other*)
3. Voltar na VM: `CORS_ORIGINS=https://<projeto>.vercel.app` no `.env` e
   `sudo systemctl restart cripto-bot`

`CORS_ORIGINS` é a origem exata, sem barra final. Preview deploys mudam a URL — incluir as
origens usadas, separadas por vírgula. Não usar `*` em backend público.

---

## 9. Segurança

**Autenticação:** HTTP Basic num middleware que cobre tudo exceto `/health` e o preflight
`OPTIONS`. Todos os 11 endpoints `POST` que mudam estado (`/reset`, `/auto`, `/panico`,
`/confirmar`, `/fechar`, `/config`, `/dca/*`) estão atrás dela.

**Contexto de risco:** não há chave de exchange, custódia nem ordem real. O impacto de um
comprometimento é corromper dados de paper trading e abusar da VM.

Três proteções implementadas:

1. **Guarda de exposição.** Sem `DASH_PASS` definido, o app aceita **apenas acesso local
   direto**; requisição de IP não-loopback **ou** com header de proxy (`X-Forwarded-For` /
   `X-Forwarded-Proto`) recebe **503**. Esquecer a variável no `.env` é o erro mais provável do
   deploy — antes disso o middleware desligava em silêncio e servia o painel aberto. Agora
   **falha alto, não falha aberto.**
2. **Throttle de login por IP.** 8 tentativas erradas → bloqueio de 5 min (429 + `Retry-After`).
   O IP vem do `X-Forwarded-For` **somente quando o peer direto é o proxy local**, senão o
   header seria forjável. O mapa de falhas é podado acima de 5000 entradas.
   *Efeito colateral aceito:* o bloqueio é checado **antes** da verificação da senha — errar 8
   vezes bloqueia mesmo com a senha correta. Liberar para a senha certa permitiria continuar o
   brute force. Reset: `systemctl restart cripto-bot` (contagem é em memória).
3. **Sem CDN de terceiro.** `chart.js` e `lightweight-charts` são servidos localmente
   (`web/vendor/`). A credencial fica em `localStorage` (`btoa` é codificação, não
   criptografia); uma CDN comprometida executaria JS na página e a exfiltraria.

**Bug corrigido no caminho — preflight CORS:** o middleware de auth é registrado *depois* do
`CORSMiddleware`, e o Starlette monta a pilha ao contrário, deixando a auth como camada mais
externa. O preflight `OPTIONS` chega **sem** `Authorization` → 401 → `CORSMiddleware` nunca
executa → **todo** fetch cross-origin falharia com erro opaco no console. Corrigido liberando
`OPTIONS`. Não aparecia no modo monolito porque same-origin não faz preflight.

**Não implementado:** múltiplos usuários, expiração e revogação de sessão. Trocar senha =
editar `.env` + restart. Se surgir necessidade, o caminho é **Cloudflare Access** na frente
(gratuito até 50 usuários), que remove autenticação do código da aplicação.

---

## 10. Validação

```bash
curl -s localhost:8000/health                          # 1. backend local
curl -s https://<FQDN>/health                          # 2. TLS público
curl -si https://<FQDN>/estado | head -1               # 3. deve dar 401
curl -s -u admin:<SENHA> https://<FQDN>/estado         # 4. deve dar 200

# 5. preflight CORS — deve dar 200 + access-control-allow-origin, NÃO 401
curl -si -X OPTIONS https://<FQDN>/estado \
  -H "Origin: https://<projeto>.vercel.app" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization" | head -12

# 6. guarda de exposição — comentar DASH_PASS, restart, esperar 503, descomentar
# 7. throttle — 9 chutes seguidos; o 9º deve virar 429
for i in $(seq 1 9); do
  curl -s -o /dev/null -w "%{http_code} " -u admin:errado https://<FQDN>/estado
done; echo
```

Os passos 5, 6 e 7 são os que validam correções que falham silenciosamente.

---

## 11. Custos e limites do tier gratuito

Azure for Students (`MS-AZR-0170P`): US$ 100 por 12 meses, **sem cartão de crédito**,
renovável anualmente enquanto for aluno ativo. Expira em **18/08/2027**.

| Recurso | Cota gratuita/mês | Uso previsto |
|---|---|---|
| VM Linux | 750 h de `B2pts v2` / `B2ats v2` | ~730 h (24/7) — **cabe** |
| Managed Disks | 2 × 64 GB **P6** (Premium SSD) | 1 × 64 GB P6 |
| Egress | **15 GB** | ver aviso |

⚠️ **Egress de 15 GB/mês é o limite mais fácil de estourar.** O painel faz poll a cada 3 s;
deixado aberto 24/7 passa de 15 GB/mês. O front já pausa o polling com a aba oculta
(`visibilitychange`), mas o hábito de fechar a aba importa.

⚠️ **Redimensionar a VM ou subir uma segunda** sai do gratuito imediatamente.

**Ações recomendadas:** budget alert em ~70% do crédito (Cost Management → Budgets) e
verificação do Cost Analysis após 2-3 dias de operação para confirmar que o custo real é zero.

---

## 12. Operação

```bash
journalctl -u cripto-bot -f
journalctl -u caddy -f
tail -f ~/cripto-bot/plataforma.log

# atualizar backend
scp -i ~/.ssh/cripto-bot *.py ubuntu@<FQDN>:/home/ubuntu/cripto-bot/
ssh -i ~/.ssh/cripto-bot ubuntu@<FQDN> "sudo systemctl restart cripto-bot"

# backup do banco — é o histórico inteiro de trades e métricas
scp -i ~/.ssh/cripto-bot ubuntu@<FQDN>:~/cripto-bot/trading.db ./backup.db
```

---

## 13. Riscos conhecidos e pendências

| # | Risco | Mitigação |
|---|---|---|
| 1 | Cota `BASv2` pode ser 0 (não verificável antes) | Erro explícito no `vm create` → pedir aumento ou trocar região |
| 2 | IP do operador é dinâmico → perde SSH | `az network nsg rule update ... --source-address-prefixes NOVO_IP` |
| 3 | Crédito/assinatura expiram em 18/08/2027 | Budget alert + renovação anual no calendário |
| 4 | Egress de 15 GB pode estourar | Fechar a aba do painel; polling já pausa com aba oculta |
| 5 | Instância única, sem HA | Aceito: `Restart=always` no systemd + reboot automático da VM |
| 6 | Sem backup automatizado do `trading.db` | **Pendente** — avaliar cron + Azure Blob (5 GB grátis) |
| 7 | Front no Vercel e cópia em `~/cripto-bot/web/` podem divergir | Publicar nos dois ou aceitar a URL da Azure como fallback desatualizado |
| 8 | `MemoryMax=900M` em VM de 1 GiB pode gerar restart sob carga do pandas | Swap de 2 GB provisionado; monitorar `journalctl -u cripto-bot` nos primeiros dias e afrouxar se houver OOM |
| 9 | Sem `web/vendor/` os gráficos não carregam | Serviço **não** cai mais (mount condicional); log registra o aviso |

**Decisões que dependem do dono do projeto:** item 6 (backup) e se vale abandonar o split
front/backend (§3.5) para reduzir peças.

---

## 14. Correções aplicadas em revisão

Este plano passou por uma revisão com verificação contra o código real. O que foi encontrado e
corrigido — vale conhecer as classes de erro:

| Gravidade | Achado | Correção |
|---|---|---|
| **Bloqueante** | `scp` sem `mkdir` remoto: o diretório `~/cripto-bot` não existia e o primeiro `scp` falharia | `ssh ... "mkdir -p ~/cripto-bot"` adicionado antes |
| **Alto** | VM nasce em **UTC**; `simulador.py` usa hora local para delimitar o dia da trava de perda, que passaria a virar às 21h BRT | `timedatectl set-timezone America/Sao_Paulo` no provisionamento (§5.1) |
| **Alto** | `cripto-bot.service` no repositório ainda tinha `--host 0.0.0.0`, divergindo do plano — passo manual esquecível que exporia a 8000 | Unit corrigido para `127.0.0.1` na origem |
| **Médio** | `StaticFiles` levanta `RuntimeError` em diretório ausente: sem `web/vendor/` o **serviço inteiro não subia** | Mount condicional + log de aviso |
| **Médio** | Script assumia que `--nsg-rule NONE` cria o NSG; se não criasse, as 3 regras falhariam | Guarda que cria o NSG e anexa à NIC |
| Baixo | Plano mandava copiar `estrategias/`, não usada pelo runtime (só backtests) | Removido do `scp` |

Verificações que **passaram**: 11 endpoints `POST` (contagem confere), `requirements.txt`
completo em relação aos imports do runtime, e nenhuma dependência externa faltando.
