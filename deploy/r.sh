#!/usr/bin/env bash
# [LIVE-10] `python -m execucao` com o ambiente da conta R, no servidor, sempre como `cripto-r`.
#
#   sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh estado
#   sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh config chave=valor ...   (o único caminho que AFROUXA)
#   sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh config-de /var/lib/cripto-r/copia-a.db perda_total_max=60 ...
#   sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh reset RESET
#   sudo -u cripto-r bash /opt/cripto-r/app/deploy/r.sh panico   (prefira `sudo cripto-panico-r`: tenta o serviço antes)
#
# [LIVE-14] Caminho absoluto sempre: o `arthur` não entra em /home/cripto, e a R não usa mais
# nada de lá. Este arquivo mora no checkout de root da R (/opt/cripto-r/app), que o `cripto`
# (o processo da A, exposto na internet) não escreve. O `cripto-r` não tem shell de login:
# `sudo -u cripto-r bash ...` roda o bash direto, não precisa de shell. Como root também
# funciona (o Python cai para `cripto-r`), mas não é preciso.
#
# Os arquivos de ambiente são lidos pelo Python como o systemd os lê (`execucao._carregar_env`),
# sem `source`: nenhum valor é executado pelo bash. São os dois da R (r.env e corretora.env),
# não o .env da A. Como root, o Python roda como `cripto-r`: arquivo do banco ou do log criado
# por root impede o serviço de subir depois.
set -u

OPT_R="${OPT_R:-/opt/cripto-r}"
RAIZ="$OPT_R/app"
PASTA_R="${PASTA_R:-/var/lib/cripto-r}"
USUARIO="${USUARIO:-cripto-r}"

cd "$RAIZ" || { echo "r.sh: pasta $RAIZ não existe"; exit 2; }
CMD=(env CONTA=R CORRETORA_HABILITADA=1 TZ=America/Sao_Paulo
     DB_PATH="$PASTA_R/trading.db" LOG_PATH="$PASTA_R/plataforma.log"
     ARQUIVOS_ENV="$PASTA_R/r.env:$PASTA_R/corretora.env"
     GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0="$RAIZ"
     "$OPT_R/venv/bin/python" -m execucao "$@")
if [ "$(id -un)" = "$USUARIO" ]; then
    exec "${CMD[@]}"
elif [ "$(id -u)" = "0" ]; then
    exec runuser -u "$USUARIO" -- "${CMD[@]}"
else
    exec sudo -n -u "$USUARIO" -- "${CMD[@]}"
fi
