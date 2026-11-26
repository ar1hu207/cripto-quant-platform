#!/usr/bin/env bash
# [LIVE-10] `python -m execucao` com o ambiente da conta R, no servidor, sempre como `cripto`.
#
#   sudo bash deploy/r.sh estado
#   sudo bash deploy/r.sh config chave=valor ...          (o único caminho que AFROUXA em binance)
#   sudo bash deploy/r.sh config-de /home/cripto/cripto-bot/trading.db perda_total_max=60 ...
#   sudo bash deploy/r.sh panico                          (prefira deploy/panico.sh: tenta o serviço antes)
#
# Os arquivos de ambiente são lidos pelo Python como o systemd os lê (`execucao._carregar_env`),
# sem `source`: nenhum valor é executado pelo bash. `DB_PATH` e `CONTA` da R vencem o `.env` da A.
# Como root, o Python roda como `cripto`: arquivo do banco ou do log criado por root impede o
# serviço de subir depois.
set -u

RAIZ="${RAIZ:-/home/cripto/cripto-bot}"
PASTA_R="${PASTA_R:-/home/cripto/cripto-bot-r}"
USUARIO="${USUARIO:-cripto}"

cd "$RAIZ" || { echo "r.sh: pasta $RAIZ não existe"; exit 2; }
CMD=(env CONTA=R CORRETORA_HABILITADA=1 TZ=America/Sao_Paulo
     DB_PATH="$PASTA_R/trading.db" LOG_PATH="$PASTA_R/plataforma.log"
     ARQUIVOS_ENV="$RAIZ/.env:$PASTA_R/corretora.env"
     "$RAIZ/venv/bin/python" -m execucao "$@")
if [ "$(id -un)" = "$USUARIO" ]; then
    exec "${CMD[@]}"
elif [ "$(id -u)" = "0" ]; then
    exec runuser -u "$USUARIO" -- "${CMD[@]}"
else
    exec sudo -n -u "$USUARIO" -- "${CMD[@]}"
fi
