# Deploy — Backend na Azure (VM) + Front no Vercel

Arquitetura: **front estático no Vercel** (`web/`) chamando o **backend FastAPI numa VM
Ubuntu da Azure**, atrás do **Caddy** com HTTPS automático.

> **Leia a §0 antes.** Existe um caminho mais simples que faz a mesma coisa.

---

## 0. Antes de começar: você precisa mesmo separar?

O backend **já serve o front sozinho** (`GET /` → `web/index.html`). Separar não é errado,
mas repare no que acontece:

| | Monolito (tudo na VM) | Split (front no Vercel) |
|---|---|---|
| HTTPS no backend | necessário | **igualmente necessário** |
| CORS | não existe | precisa configurar |
| Autenticação | Basic Auth nativo do navegador | header explícito + tela de login |
| Deploys | 1 | 2, e precisam ficar em sincronia |
| URL bonita | `https://…cloudapp.azure.com` | `https://…vercel.app` |

O ponto que decide: **página HTTPS não pode chamar `http://IP:8000`** — o navegador bloqueia
como *mixed content*. Então o backend precisa de HTTPS de qualquer forma. E **uma vez que ele
tem HTTPS, servir o `index.html` a partir dele é de graça.**

**Quando o split se justifica de verdade:** se você for reescrever o front num framework
(Next.js/React) e quiser preview deploy por branch, CDN e build pipeline. Aí o Vercel ganha.
Para o `index.html` estático de hoje, ele empata e custa mais peças.

- **Só o monolito?** → siga o `DEPLOY-AZURE.md` + a **§2.6 (Caddy/HTTPS)** deste arquivo. Pare aí.
- **Split mesmo?** → siga tudo.

---

## 1. A VM na Azure

Igual ao `DEPLOY-AZURE.md` (§1-§2), **com uma diferença obrigatória**: a VM precisa de um
**nome DNS**, porque certificado TLS não é emitido para IP puro.

### 1.1 Criar
Portal → **Virtual machines → Create**:
- **Image:** Ubuntu Server 24.04 LTS · **Size:** `Standard_B2ats_v2` (2 vCPU / 1 GiB, AMD x64)
  — é o que está no tier gratuito de 750 h/mês da sua oferta. **Não** use `B1s`: ele saiu do
  gratuito e passa a consumir crédito.
- **Disco:** **Premium SSD, 64 GiB (P6)** — o tier gratuito cobre 2 × P6 de 64 GB
- **Authentication:** SSH public key · **Username:** `ubuntu` (bate com o `.service`)
- **Inbound ports:** deixe só SSH (22) por ora

### 1.2 Dar um nome DNS ao IP público ← passo novo, não pule
Portal → **Public IP address** da VM → **Configuration** → **DNS name label**:

```
meu-bot   →   meu-bot.brazilsouth.cloudapp.azure.com
```

Esse hostname é gratuito e o Let's Encrypt emite certificado pra ele. Anote — vai em três
lugares: Caddyfile, `CORS_ORIGINS` e `config.js`.

### 1.3 Abrir portas no NSG
Portal → VM → **Networking → Add inbound port rule**:

| Porta | Protocolo | Source | Por quê |
|---|---|---|---|
| 22 | TCP | **My IP** | SSH — restrinja |
| 80 | TCP | Any | desafio ACME do Let's Encrypt + redirect → HTTPS |
| 443 | TCP | Any | o app |

**Não abra a 8000.** Com o Caddy na frente, o uvicorn escuta só em `127.0.0.1`.

> **Sobre `Source: Any` no 443:** o fetch do front roda **no navegador do usuário**, não nos
> servidores do Vercel — então travar por IP quebraria seu acesso via 4G/outra rede. A proteção
> aqui é HTTPS + `DASH_PASS` forte. Use uma senha longa e aleatória, não a de sempre.

---

## 2. Backend na VM

### 2.1 Sistema
```bash
ssh -i chave.pem ubuntu@SEU_IP
sudo apt update && sudo apt install -y python3-venv python3-pip
```

### 2.2 Subir o código (do seu PC, na pasta do projeto)
```bash
ssh -i chave.pem ubuntu@SEU_IP "mkdir -p ~/cripto-bot"
scp -i chave.pem *.py requirements.txt ubuntu@SEU_IP:/home/ubuntu/cripto-bot/
scp -i chave.pem -r web/ ubuntu@SEU_IP:/home/ubuntu/cripto-bot/
scp -i chave.pem -r estrategias/ ubuntu@SEU_IP:/home/ubuntu/cripto-bot/
scp -i chave.pem deploy/cripto-bot.service deploy/cripto-bot.env.example ubuntu@SEU_IP:/home/ubuntu/cripto-bot/
```

### 2.3 Ambiente Python
```bash
cd ~/cripto-bot && python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
```

### 2.4 `.env`
```bash
cp cripto-bot.env.example .env && nano .env && chmod 600 .env
```
Preencha:
```
DB_PATH=/home/ubuntu/cripto-bot/trading.db
DASH_USER=admin
DASH_PASS=<senha longa e aleatória — gere com: openssl rand -base64 24>
CORS_ORIGINS=https://SEU-PROJETO.vercel.app
```
`CORS_ORIGINS` é a origem **exata**, com `https://` e **sem barra no fim**. Você só sabe a URL
depois da §3 — pode voltar aqui e reiniciar o serviço.

### 2.5 systemd — escutando só em localhost
Edite o `ExecStart` de `cripto-bot.service` **trocando `--host 0.0.0.0` por `--host 127.0.0.1`**
(quem fala com a internet agora é o Caddy):
```
ExecStart=/home/ubuntu/cripto-bot/venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000
```
```bash
sudo cp cripto-bot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now cripto-bot
systemctl status cripto-bot          # "active (running)"
curl -s localhost:8000/health        # {"status":"ok",...}
```

### 2.6 Caddy — HTTPS automático
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```
Coloque seu hostname no `/etc/caddy/Caddyfile` (modelo pronto em `deploy/Caddyfile`):
```
meu-bot.brazilsouth.cloudapp.azure.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8000
}
```
```bash
sudo systemctl reload caddy
sudo journalctl -u caddy -f          # acompanhe a emissão do certificado
```

**Teste:** `https://meu-bot.brazilsouth.cloudapp.azure.com/health` → `{"status":"ok"}` com
cadeado, sem aviso. Se falhar: 99% é porta 80 fechada no NSG ou hostname errado no Caddyfile.

---

## 3. Front no Vercel

O front vive em **`web/`** — pasta separada de propósito: se você apontasse o Vercel pra raiz
do projeto, ele publicaria `db.py`, `api.py`, `autotrader.py` e até o `trading.db` como
arquivos estáticos baixáveis. **Nunca aponte o Vercel pra raiz.**

### 3.1 Apontar o front pro backend
Edite `web/config.js`:
```js
window.API_BASE = "https://meu-bot.brazilsouth.cloudapp.azure.com";
```
Tem que ser `https://`. Com `http://` o navegador bloqueia tudo silenciosamente.

### 3.2 Deploy
```bash
npm i -g vercel
cd web
vercel            # preview
vercel --prod     # produção
```
Ou pelo painel: **Add New → Project** → importe o repositório → **Root Directory: `web`** →
Framework Preset: **Other** → Deploy.

### 3.3 Fechar o círculo do CORS
Pegue a URL final (`https://seu-projeto.vercel.app`), volte na VM:
```bash
nano ~/cripto-bot/.env                  # CORS_ORIGINS=https://seu-projeto.vercel.app
sudo systemctl restart cripto-bot
```
Se for usar **preview deploys** (a URL muda por branch), inclua as origens que for usar,
separadas por vírgula. Não deixe `*` num backend público.

---

## 4. O que mudou no código (já aplicado)

| Arquivo | Mudança | Por quê |
|---|---|---|
| `web/index.html` | front movido pra `web/` | impedir que o deploy estático publique os `.py` e o `.db` |
| `web/index.html` | `apiFetch()` centraliza os 9 `fetch` | prefixa `API_BASE` e injeta `Authorization` num lugar só |
| `web/index.html` | login (prompt) + `localStorage` | em cross-origin o navegador **não** anexa Basic Auth sozinho |
| `web/config.js` | novo, define `window.API_BASE` | vazio = mesma origem; preenchido = backend remoto |
| `web/vercel.json` | novo | estático puro, sem build; `config.js` sem cache |
| `web/vendor/` | chart.js e lightweight-charts baixados | tira o CDN de terceiro do caminho — era vetor de XSS capaz de roubar a credencial |
| `api.py` | `CORS_ORIGINS` por env | origem explícita em vez de `*` |
| `api.py` | auth ignora `OPTIONS` | **corrige bug real** — ver abaixo |
| `api.py` | guarda de exposição sem `DASH_PASS` | falha alto em vez de falhar aberto — ver §4.5 |
| `api.py` | throttle de login por IP | brute force em 443 aberto pra `Any` |
| `api.py` | mount `/vendor` + rota `/config.js` | o front referencia; sem isso, 404 no modo monolito |
| `api.py` | `FileResponse` → `web/index.html` | acompanhou a mudança de pasta |
| `deploy/Caddyfile` | novo | HTTPS automático |
| `deploy/cripto-bot.env.example` | `CORS_ORIGINS` documentado | |

### O bug do preflight (vale entender)
`auth_basica` é registrado **depois** do `CORSMiddleware`, e o Starlette monta a pilha ao
contrário — então a auth era a camada **mais externa**. O preflight `OPTIONS` do CORS é enviado
pelo navegador **sem** header `Authorization`, levava **401**, e o `CORSMiddleware` nunca
chegava a rodar. Resultado: **todo** fetch cross-origin falharia, com mensagem inútil no
console. Corrigido liberando `OPTIONS` na auth. No modo monolito isso nunca apareceu porque
same-origin não faz preflight.

### Compatibilidade
Tudo é retrocompatível: com `API_BASE = ""` e sem `CORS_ORIGINS`, o comportamento é **idêntico
ao de hoje** — `uvicorn api:app --port 8000` e `http://localhost:8000` seguem funcionando
igual, sem senha e sem CORS.

---

## 4.5 Autenticação — o que existe e o que ela cobre

**A autenticação é HTTP Basic**, num middleware que cobre **tudo** menos `/health` (healthcheck)
e o preflight `OPTIONS` (não carrega dado). Os 11 endpoints `POST` que mudam estado
(`/reset`, `/auto`, `/panico`, `/confirmar`, `/fechar`, `/config`, `/dca/*`…) estão todos atrás dela.

### Contexto de risco (para calibrar o esforço)
**Não existe chave de exchange no projeto.** Todos os `ccxt.*()` são instanciados sem
credencial, só endpoint público. Ninguém saca dinheiro seu porque não há dinheiro nem chave.
O que um invasor conseguiria: bagunçar o banco de paper trading, ler seu histórico e abusar
da sua VM. É por isso que Basic Auth + HTTPS é proporcional aqui, e não uma gambiarra.

### As três proteções

**1. Guarda de exposição — o footgun principal**
Esquecer `DASH_PASS` no `.env` é o erro mais provável do deploy, e antes ele **falhava aberto**:
o middleware simplesmente desligava e servia o painel inteiro pra internet, sem avisar.
Agora, sem `DASH_PASS` o app só aceita **acesso local direto**. Qualquer requisição de IP
não-loopback, **ou** que chegue com header de proxy (`X-Forwarded-For`/`X-Forwarded-Proto` —
ou seja, passou pelo Caddy), leva **503** com a mensagem do que fazer. Falha alto, não aberto.
Isso não exige configuração nenhuma: o dev local continua sem senha, o deploy não sobe sem ela.

**2. Throttle de login por IP**
8 tentativas erradas → o IP fica bloqueado por 5 minutos (**429** com `Retry-After`).
O IP real vem do `X-Forwarded-For`, mas **só quando o peer direto é o proxy local** — senão
qualquer um forjaria o header pra escapar do bloqueio. O dicionário de falhas se poda sozinho
acima de 5000 entradas (XFF forjado não vira vazamento de memória).

> **Efeito colateral aceito:** o bloqueio é verificado **antes** de conferir a senha — então,
> se você errar 8 vezes, fica 5 min de fora **mesmo digitando a senha certa**. É proposital:
> liberar o bloqueio para a senha correta deixaria o atacante seguir testando senhas.
> Se travar você mesmo: `sudo systemctl restart cripto-bot` limpa (a contagem é em memória).

**3. Libs servidas por nós, sem CDN**
A credencial fica no `localStorage` do navegador (`btoa` é codificação, **não** criptografia).
Com `chart.js` e `lightweight-charts` vindo de CDN de terceiro, uma CDN comprometida executaria
JS na sua página e levaria a credencial embora. As duas libs agora vivem em `web/vendor/` e são
servidas pelo Vercel/pelo próprio backend. Sobrou só o Google Fonts, que entrega CSS/fonte e
não executa JS.

### O que continua não tendo
Um usuário só (`DASH_USER`/`DASH_PASS`), sem expiração de sessão e sem revogação — trocar a
senha é editar o `.env` e reiniciar. Para um painel privado de um usuário, isso é adequado.
Se um dia precisar de vários usuários ou login com Google, o caminho é **Cloudflare Access**
na frente (grátis até 50 usuários), que tira autenticação do nosso código por completo.

**A senha é a única coisa entre a internet e o painel.** Use longa e aleatória
(`openssl rand -base64 24`), não a de sempre.

---

## 5. Checklist de validação

```bash
# 1. backend vivo e local
curl -s localhost:8000/health

# 2. HTTPS público
curl -s https://SEU-HOST/health

# 3. auth barrando (deve dar 401)
curl -si https://SEU-HOST/estado | head -1

# 4. auth passando (deve dar 200)
curl -s -u admin:SUA_SENHA https://SEU-HOST/estado | head -c 200

# 5. preflight do CORS (deve dar 200 + access-control-allow-origin, NAO 401)
curl -si -X OPTIONS https://SEU-HOST/estado \
  -H "Origin: https://seu-projeto.vercel.app" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization" | head -12

# 6. guarda de exposição: comente o DASH_PASS do .env, reinicie e confirme 503.
#    Deve responder "Backend exposto sem DASH_PASS". Descomente e reinicie de novo.
curl -s https://SEU-HOST/estado

# 7. throttle: 9 chutes seguidos — o 9o tem que virar 429
for i in $(seq 1 9); do curl -s -o /dev/null -w "%{http_code} " -u admin:errado https://SEU-HOST/estado; done; echo
#    (isso te bloqueia por 5 min; `sudo systemctl restart cripto-bot` limpa)

# 8. estáticos do front servidos pelo backend (modo fallback)
curl -s -o /dev/null -w "%{http_code}\n" -u admin:SUA_SENHA https://SEU-HOST/vendor/chart.umd.min.js
```
O passo 5 é o que teria quebrado tudo silenciosamente — se voltar 401, a correção do `OPTIONS`
não subiu pra VM. Os passos 6 e 7 confirmam que as proteções da §4.5 estão de pé.

Depois, no navegador: abra a URL do Vercel → pede usuário/senha → painel carrega com dados.
Console (F12) sem erro de CORS nem de mixed content.

---

## 6. Manutenção

```bash
# logs
journalctl -u cripto-bot -f
journalctl -u caddy -f
tail -f ~/cripto-bot/plataforma.log

# atualizar backend
scp -i chave.pem *.py ubuntu@SEU_IP:/home/ubuntu/cripto-bot/
ssh -i chave.pem ubuntu@SEU_IP "sudo systemctl restart cripto-bot"

# atualizar front: nada a fazer, push na main publica sozinho (ver abaixo)
# para forcar um deploy fora do fluxo do git:
cd web && vercel --prod
```

### 5.1 O front publica sozinho (GitHub -> Vercel)

O projeto do Vercel esta conectado ao repositorio: **merge na `main` publica o front**. Nao ha
passo manual.

O ajuste que faz isso funcionar nao esta no dashboard, e sim versionado — sao **dois**
`vercel.json`, e a diferenca entre eles nao e acidente:

| arquivo | quem usa | `outputDirectory` |
|---|---|---|
| `vercel.json` (raiz) | deploy automatico pelo GitHub | `web` |
| `web/vercel.json` | `cd web && vercel --prod` (CLI) | `.` |

O Root Directory do projeto e `.`, entao o build vindo do GitHub le a **raiz** do repositorio.
Sem o `vercel.json` da raiz apontando `outputDirectory` para `web`, esse build publicaria a raiz
— onde **nao existe `index.html`** (a URL de producao daria 404) e onde estao `api.py`,
`signal_engine.py` e os documentos de estrategia, que virariam publicos. Credencial e banco nao:
`.env` e `*.db` estao no `.gitignore` e nem chegam no GitHub.

Os dois arquivos publicam exatamente o mesmo site; existem porque cada caminho enxerga a arvore
a partir de um lugar diferente. **Mexeu num, confira o outro.**

**O front no Vercel e a cópia em `~/cripto-bot/web/` são o mesmo arquivo.** Se editar o
`index.html`, publique nos dois — ou aceite que o acesso direto pela URL da Azure fique
desatualizado (ele continua funcionando como fallback).

---

## 7. Créditos, custo e riscos

- **Custo:** `B1s` Linux 24/7 fica na casa de US$ 8-10/mês, mais disco (~US$ 2-4/mês).
- **Azure for Students** (oferta `MS-AZR-0170P`): US$ 100 de crédito por 12 meses, **sem cartão
  de crédito**, renovável a cada ano enquanto você for aluno ativo.
- **O que é gratuito por 12 meses** (confirmado no portal, aba *Serviços gratuitos*):

  | Recurso | Cota grátis/mês | O que usar |
  |---|---|---|
  | Máquina Virtual Linux | **750 h** de `B2pts v2` (Arm) **e** `B2ats v2` (AMD) | `Standard_B2ats_v2` |
  | Azure Managed Disks | **2 × 64 GB P6** (Premium SSD) | disco do SO como P6 64 GiB |
  | Transferência de saída | **15 GB** | ver aviso abaixo |

  O mês tem ~730 h, então **uma** VM 24/7 cabe dentro das 750 h e **não** consome o crédito.
  - ⚠️ **`B1s` NÃO está mais no gratuito.** Só as `v2` da tabela. Escolher `B1s` (ou redimensionar
    pra `B2s`) passa a descontar do crédito na hora.
  - ⚠️ **Egress de 15 GB/mês.** O painel faz poll a cada 3 s; deixado aberto 24/7 isso passa
    tranquilamente de 15 GB/mês e começa a custar. O front já pausa o polling quando a aba fica
    oculta — mas feche a aba quando não estiver olhando.
  - ⚠️ **Renovação anual.** O crédito e a assinatura expiram em 12 meses. Se não renovar, a VM
    para — e o bot com ela. Marque no calendário.
- **Crédito acabou = VM parada = bot morto.** Configure um **budget alert** (Cost Management →
  Budgets) em ~70% do crédito. Não descubra pelo painel offline.
- **Economia:** `Stop (deallocate)` quando não estiver usando. Mas aí o worker para e o paper
  trading perde continuidade — decida o que importa mais.
- **1 instância só.** Worker singleton + SQLite com WAL. Não escale horizontalmente.
- **Backup do banco:** `scp ubuntu@SEU_IP:~/cripto-bot/trading.db ./backup.db`. É o histórico
  inteiro de trades e métricas. Ninguém faz backup até perder.

### Por que VM e não Azure App Service
App Service dá HTTPS grátis e Easy Auth, o que é tentador. Mas o `/home` persistente dele é
**Azure Files (rede)**, e **SQLite em modo WAL não funciona de forma confiável em filesystem
de rede** — WAL precisa de memória compartilhada que o share não oferece. Como o `db.py` liga
`PRAGMA journal_mode=WAL`, o App Service traria risco de lock e de corrupção de banco. VM com
disco local é a escolha certa aqui.

### Alternativa se o DNS da Azure der problema
**Cloudflare Tunnel** (`cloudflared`): HTTPS e domínio sem abrir porta nenhuma no NSG, de
graça. É mais uma dependência externa, mas resolve TLS e exposição de uma vez só.
