# Deploy no Azure (VM Ubuntu) — passo a passo

Roda o bot 24/7 numa VM Linux, com `systemd` mantendo vivo e religando no boot.
SQLite no disco da VM (persiste). Login básico via senha. Usa seus créditos de estudante.

> Reaproveita `deploy/cripto-bot.service` e `deploy/cripto-bot.env.example`.
> Mais simples que o Oracle: SEM o pega-ratão do iptables — só abrir a porta no NSG.

---

## 1) Criar a VM
Portal Azure → **Virtual machines → Create → Azure virtual machine**:
- **Image:** Ubuntu Server 24.04 LTS (Python 3.12 nativo).
- **Size:** `Standard_B2ats_v2` (2 vCPU/1 GiB, AMD) — é o que entra nas 750 h/mês gratuitas do
  Azure for Students. `B1s` saiu do tier gratuito e passa a consumir crédito.
- **Authentication:** SSH public key.
- **Username:** use **`ubuntu`** (pra bater com os arquivos; senão ajuste `User=` e os paths no `.service`).
- **Inbound ports:** deixe SSH (22) marcado. A porta do app a gente abre no passo 3.
- Crie e anote o **Public IP**.

## 2) Conectar
```bash
ssh -i caminho/da/chave.pem ubuntu@SEU_IP_PUBLICO
```

## 3) Abrir a porta 8000 (NSG)
Portal → sua VM → **Networking → Add inbound port rule**:
- Destination port **8000**, Protocol **TCP**, Action **Allow**.
- **Source:** melhor colocar **seu IP** (My IP) em vez de Any. (Se o `ufw` estiver ativo na VM: `sudo ufw allow 8000`.)

## 4) Instalar dependências do sistema
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
```

## 5) Subir o app (do seu PC, na pasta do projeto)
```bash
ssh -i chave.pem ubuntu@SEU_IP "mkdir -p ~/cripto-bot"
scp -i chave.pem *.py requirements.txt ubuntu@SEU_IP:/home/ubuntu/cripto-bot/
scp -i chave.pem -r web/ ubuntu@SEU_IP:/home/ubuntu/cripto-bot/
scp -i chave.pem deploy/cripto-bot.service deploy/cripto-bot.env.example ubuntu@SEU_IP:/home/ubuntu/cripto-bot/
```

## 6) Ambiente Python (na VM)
```bash
cd ~/cripto-bot
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## 7) Senha (.env)
```bash
cp cripto-bot.env.example .env
nano .env            # troque DASH_PASS por uma senha FORTE
chmod 600 .env
```

## 8) Serviço systemd (mantém vivo + religa no boot)
> O `.service` vem com `--host 127.0.0.1` (pressupõe Caddy na frente, ver
> `DEPLOY-VERCEL-AZURE.md` §2.6). Para acesso direto em `http://IP:8000` como descrito
> aqui, troque para `--host 0.0.0.0` antes de copiar.

```bash
sudo cp cripto-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cripto-bot
systemctl status cripto-bot      # "active (running)"
```

## 9) Abrir
Navegador: **http://SEU_IP_PUBLICO:8000** → login (DASH_USER/DASH_PASS).
No painel **🤖 Auto-trade**, **ligue o bot** (banco nasce limpo: banca R$1000, bot OFF, settings padrão).

---

## Manutenção
- Logs: `journalctl -u cripto-bot -f`
- Reiniciar: `sudo systemctl restart cripto-bot`
- Atualizar código: re-`scp` os arquivos + `sudo systemctl restart cripto-bot`

## Atenção (créditos e segurança)
- **Fique de olho nos créditos** — se zerarem/expirarem, a Azure para/derruba a VM (e o bot com ela).
  Pare a VM quando não estiver usando (`Stop`/deallocate) pra economizar.
- Sempre com `DASH_PASS` setado. Restrinja o **Source do NSG ao seu IP**.
- Basic Auth em HTTP manda a senha em base64 (não-criptografada) — ok pra hobby.
- **1 instância só** (worker singleton + SQLite).

## Alternativa mais "gerenciada" (opcional): Azure App Service
Se quiser **HTTPS grátis** (domínio `*.azurewebsites.net`) e **login da Microsoft na frente** (Easy Auth,
sem precisar da senha básica), dá pra usar App Service com **"Always On" ligado** (senão o worker dorme)
e o SQLite em `/home` (que persiste). É mais "sobe e esquece" e mais seguro, porém config específica de
Azure. Me fala se preferir esse caminho que eu preparo o startup command + as app settings.
