# Deploy no Oracle Cloud "Always Free" (grátis pra sempre) — passo a passo

Roda o bot 24/7 numa VM Ubuntu, com `systemd` mantendo vivo e religando no boot.
Banco SQLite no disco da VM (persiste). Login básico via senha. Custo: R$0.

> Atalho mental: criar VM → abrir a porta (2 lugares!) → instalar Python → subir o app →
> systemd → abrir no navegador. O pega-ratão clássico é a porta (passo 3).

---

## 1) Criar a VM (Always Free)
No console Oracle Cloud → **Compute → Instances → Create Instance**:
- **Image:** Ubuntu 24.04 (já vem com Python 3.12).
- **Shape:** **Ampere A1 (ARM)** — ex.: 1 OCPU / 6 GB (tudo Always Free). Se der "out of capacity",
  troque de **Availability Domain** ou use **VM.Standard.E2.1.Micro** (AMD, 1 GB — funciona, mais apertado).
- **SSH keys:** gere/baixe o par de chaves (guarde o `.key` privado).
- Crie e anote o **Public IP**.

## 2) Conectar
```bash
ssh -i caminho/da/sua-chave.key ubuntu@SEU_IP_PUBLICO
```

## 3) Abrir a porta 8000 — EM DOIS LUGARES (o erro nº1 do Oracle)
**(a) Firewall da nuvem:** console → sua VCN → **Security Lists** → Default → **Add Ingress Rule**:
- Source `0.0.0.0/0` (ou, melhor, **só o seu IP**/32), IP Protocol **TCP**, Destination Port **8000**.

**(b) Firewall da VM (iptables):** as imagens Ubuntu do Oracle bloqueiam tudo por padrão. Na VM:
```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
sudo netfilter-persistent save
```
Sem o passo (b), a porta "abre" na nuvem mas a VM continua recusando. É AQUI que todo mundo trava.

## 4) Instalar dependências do sistema
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
```

## 5) Subir o app pra VM
Do seu **PC (Git Bash/PowerShell)**, na pasta do projeto, mande os arquivos (sem o banco/cache):
```bash
scp -i sua-chave.key *.py requirements.txt ubuntu@SEU_IP:/home/ubuntu/cripto-bot/
scp -i sua-chave.key -r web/ ubuntu@SEU_IP:/home/ubuntu/cripto-bot/
scp -i sua-chave.key deploy/cripto-bot.service deploy/cripto-bot.env.example ubuntu@SEU_IP:/home/ubuntu/cripto-bot/
```
(Antes, crie a pasta na VM: `mkdir -p ~/cripto-bot`.)

## 6) Ambiente Python + dependências (na VM)
```bash
cd ~/cripto-bot
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## 7) Configurar a senha (.env)
```bash
cp cripto-bot.env.example .env
nano .env            # troque DASH_PASS por uma senha FORTE
chmod 600 .env
```

## 8) Instalar e ligar o serviço (systemd)
```bash
sudo cp cripto-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cripto-bot
systemctl status cripto-bot      # deve aparecer "active (running)"
```

## 9) Abrir
No navegador: **http://SEU_IP_PUBLICO:8000** → pede usuário/senha (DASH_USER/DASH_PASS).
No painel **🤖 Auto-trade**, **ligue o bot** (o banco nasce limpo: banca R$1000, bot OFF, settings padrão).

---

## Manutenção
- Logs ao vivo: `journalctl -u cripto-bot -f`
- Reiniciar: `sudo systemctl restart cripto-bot`
- Atualizar código: re-`scp` os `.py`/`web/` e `sudo systemctl restart cripto-bot`

## Segurança (importante)
- Sempre com `DASH_PASS` setado (já é o caso). `/reset`, `/panico`, `/auto` mexem no estado.
- Melhor ainda: no passo 3(a), limite o **Source ao seu IP** em vez de `0.0.0.0/0`.
- Basic Auth em HTTP manda a senha em base64 (não-criptografada). Pra hobby tá ok; se quiser HTTPS,
  o caminho fácil é instalar **Caddy** com um domínio (auto-SSL). Ou, sem expor nada, acessar por
  **túnel SSH**: troque o ExecStart pra `--host 127.0.0.1` e rode `ssh -L 8000:localhost:8000 ubuntu@IP`.
- **1 instância só** (não suba outra) — o worker é singleton + SQLite.
