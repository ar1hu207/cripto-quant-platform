#!/usr/bin/env bash
# Provisiona a VM do cripto-bot na Azure.
# Rodar do Git Bash, na raiz do projeto:  bash deploy/provisionar-azure.sh
set -euo pipefail

# ------------------------------------------------------------------- parâmetros
RG="${RG:-rg-cripto-bot}"
# A região é ditada por DUAS restrições:
#  1) a assinatura tem Azure Policy "Allowed resource deployment regions" e só aceita
#     canadacentral, centralus, northcentralus, southafricanorth, spaincentral;
#  2) a Binance geo-bloqueia (HTTP 451) EUA, Canadá, Holanda e a UE — então o bot fica
#     CEGO nessas regiões, por mais que a VM funcione. Aprendido na prática em US.
# A interseção das duas deixa UMA opção: southafricanorth.
#
# Correção de 2026-08-20: este comentário afirmava que "Brazil South NÃO oferece a família B".
# Como afirmação sobre a REGIÃO, é falsa — a API de Compute SKUs lista 32 SKUs da família B em
# brazilsouth, o B2ats_v2 inclusive. O que é verdade é sobre a ASSINATURA: todos os 32 voltam com
# `NotAvailableForSubscription`, e por isso `az vm list-skus -l brazilsouth` (sem `--all`) devolve
# lista vazia. Some-se a isso a Azure Policy da restrição 1, que já barra brazilsouth de saída.
# Conclusão prática igual, motivo diferente — e o motivo errado no comentário foi o que empurrou
# o primeiro deploy para northcentralus e deixou o bot cego por 451 (STATUS-SISTEMA-2026-08-19.md).
# Verificado em 2026-08-20 via Microsoft.Compute/skus e `az policy assignment list`.
LOCAL="${LOCAL:-southafricanorth}"
VM="vm-cripto-bot"
TAMANHO="Standard_B2ats_v2"        # 2 vCPU / 1 GiB, AMD x64 — 750 h/mês grátis
IMAGEM="Canonical:ubuntu-24_04-lts:server:latest"
USUARIO="ubuntu"                   # NÃO mudar: cripto-bot.service depende deste nome
DNS_LABEL="cripto-bot-${RANDOM}"   # vira <label>.${LOCAL}.cloudapp.azure.com
CHAVE="$HOME/.ssh/cripto-bot"
# IP liberado no SSH. Detectado na hora — IP residencial é dinâmico e hardcodar
# significa script quebrado na próxima vez. Sobrescreva com: MEU_IP=1.2.3.4 bash ...
MEU_IP="${MEU_IP:-$(curl -sS https://api.ipify.org)}"
[ -n "$MEU_IP" ] || { echo "ERRO: não consegui detectar seu IP público. Passe MEU_IP=... "; exit 1; }

AZ="$(command -v az || echo '/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd')"

# ------------------------------------------------------------------------ 1/6
echo "==> 1/6 chave SSH"
if [ ! -f "$CHAVE" ]; then
  mkdir -p "$HOME/.ssh"
  ssh-keygen -t ed25519 -N "" -f "$CHAVE" -C "cripto-bot"
  echo "    chave criada em $CHAVE"
else
  echo "    já existe, reaproveitando"
fi

# ------------------------------------------------------------------------ 2/6
echo "==> 2/6 resource group $RG em $LOCAL"
"$AZ" group create --name "$RG" --location "$LOCAL" --output none

# ------------------------------------------------------------------------ 3/6
# --nsg-rule NONE: o padrão do 'vm create' abriria o SSH pra internet inteira.
# As regras entram no passo 4, com o 22 restrito ao seu IP.
echo "==> 3/6 VM $VM ($TAMANHO) — leva ~2 min"
"$AZ" vm create \
  --resource-group "$RG" \
  --name "$VM" \
  --location "$LOCAL" \
  --image "$IMAGEM" \
  --size "$TAMANHO" \
  --admin-username "$USUARIO" \
  --ssh-key-values "${CHAVE}.pub" \
  --public-ip-sku Standard \
  --public-ip-address-dns-name "$DNS_LABEL" \
  --os-disk-size-gb 64 \
  --storage-sku Premium_LRS \
  --nsg-rule NONE \
  --output none
echo "    VM criada"

# ------------------------------------------------------------------------ 4/6
echo "==> 4/6 regras de rede"
NSG="$("$AZ" network nsg list -g "$RG" --query "[0].name" -o tsv)"
if [ -z "$NSG" ]; then
  # --nsg-rule NONE normalmente ainda cria o NSG; se não criou, criamos e anexamos à NIC.
  echo "    NSG não encontrado — criando"
  NSG="${VM}NSG"
  "$AZ" network nsg create -g "$RG" -n "$NSG" -l "$LOCAL" --output none
  NIC="$("$AZ" vm show -g "$RG" -n "$VM" --query "networkProfile.networkInterfaces[0].id" -o tsv)"
  "$AZ" network nic update --ids "$NIC" --network-security-group "$NSG" --output none
fi

"$AZ" network nsg rule create -g "$RG" --nsg-name "$NSG" --name ssh \
  --priority 1000 --access Allow --protocol Tcp \
  --destination-port-ranges 22 \
  --source-address-prefixes "$MEU_IP" --output none

"$AZ" network nsg rule create -g "$RG" --nsg-name "$NSG" --name http-acme \
  --priority 1010 --access Allow --protocol Tcp \
  --destination-port-ranges 80 \
  --source-address-prefixes Internet --output none

"$AZ" network nsg rule create -g "$RG" --nsg-name "$NSG" --name https \
  --priority 1020 --access Allow --protocol Tcp \
  --destination-port-ranges 443 \
  --source-address-prefixes Internet --output none

echo "    22 (só $MEU_IP) / 80 / 443 abertas — a 8000 fica FECHADA (Caddy na frente)"

# ------------------------------------------------------------------------ 5/6
# Fuso: a VM nasce em UTC. simulador.py usa pd.Timestamp.now().date() para delimitar
# "hoje" na trava diária de perda — em UTC ela resetaria às 21h de Brasília.
echo "==> 5/6 fuso horário America/Sao_Paulo"
"$AZ" vm run-command invoke -g "$RG" -n "$VM" \
  --command-id RunShellScript --output none \
  --scripts "timedatectl set-timezone America/Sao_Paulo"

# 1 GiB de RAM é apertado pro pandas carregando candles de 10 moedas.
echo "==> 5b/6 swap de 2 GB"
"$AZ" vm run-command invoke -g "$RG" -n "$VM" \
  --command-id RunShellScript --output none \
  --scripts "if ! swapon --show | grep -q /swapfile; then \
    fallocate -l 2G /swapfile && chmod 600 /swapfile && \
    mkswap /swapfile && swapon /swapfile && \
    echo '/swapfile none swap sw 0 0' >> /etc/fstab; fi"

# ------------------------------------------------------------------------ 6/6
echo "==> 6/6 dados finais"
IP="$("$AZ" vm show -d -g "$RG" -n "$VM" --query publicIps -o tsv)"
FQDN="$("$AZ" vm show -d -g "$RG" -n "$VM" --query fqdns -o tsv)"

cat <<FIM

  ✅ pronto
  IP público : $IP
  hostname   : $FQDN
  SSH        : ssh -i "$CHAVE" $USUARIO@$FQDN

  Guarde o hostname — ele vai em três lugares:
  /etc/caddy/Caddyfile, CORS_ORIGINS (.env) e web/config.js

  Se seu IP mudar (4G / outra rede), reabra o SSH:
    az network nsg rule update -g $RG --nsg-name $NSG -n ssh \\
      --source-address-prefixes SEU_NOVO_IP

  Para APAGAR tudo e recomeçar do zero:
    az group delete --name $RG --yes
FIM
