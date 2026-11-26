#!/usr/bin/env bash
# [LIVE-5] Pânico da conta R sem painel e sem depender do serviço estar de pé.
#
# Roda NO SERVIDOR, como o usuário `cripto` (ou root):  bash deploy/panico.sh
#
# Dois caminhos, nesta ordem:
#   1. o serviço responde -> POST /panico nele (o mesmo botão do painel);
#   2. o serviço não responde -> `python -m execucao panico`, que fala direto com a corretora
#      usando o banco e a chave da conta R. É o caminho para o dia em que o processo travou e a
#      posição continua aberta lá.
# Nos dois o `auto_trade` é desligado ANTES de fechar ([P1-7]), as entradas pendentes são
# canceladas na corretora e toda posição é fechada a mercado (reduce-only: nunca abre o lado
# oposto, nem rodando duas vezes).
#
# Se nem isto funcionar (servidor fora do ar): o stop de cada posição está NA Binance e
# continua valendo. Fechar à mão é no aplicativo da Binance, em Futuros > Posições.
set -u

RAIZ="${RAIZ:-/home/cripto/cripto-bot}"
PASTA_R="${PASTA_R:-/home/cripto/cripto-bot-r}"
PORTA="${PORTA:-8003}"

cd "$RAIZ" || { echo "panico: pasta $RAIZ não existe"; exit 2; }
set -a
# shellcheck disable=SC1091
. "$RAIZ/.env"
[ -f "$PASTA_R/corretora.env" ] && . "$PASTA_R/corretora.env"
set +a

echo "panico: tentando o serviço em 127.0.0.1:$PORTA ..."
# 170 s: o pânico espera a reconciliação em curso soltar a conta, e cada chamada dela à
# corretora pode levar até 10 s. Cortar antes disso seria desistir de um pânico que ia funcionar.
if resposta=$(curl -sS -m 170 -u "${DASH_USER:-admin}:${DASH_PASS:-}" \
                   -X POST "http://127.0.0.1:$PORTA/panico"); then
    echo "panico: resposta do serviço: $resposta"
    # Só "ok":true encerra. Com "ok":false o bot foi desligado mas alguma coisa ficou aberta
    # (`falhas` diz o quê): o caminho direto abaixo tenta de novo, e é ele quem dá o código de saída.
    case "$resposta" in
        *'"ok":true'*'"auto_desligado":true'*) exit 0 ;;
    esac
    echo "panico: o serviço NÃO confirmou tudo fechado; indo pelo caminho direto"
else
    echo "panico: o serviço não respondeu; indo pelo caminho direto"
fi

exec env CONTA=R CORRETORA_HABILITADA=1 TZ=America/Sao_Paulo \
     DB_PATH="$PASTA_R/trading.db" LOG_PATH="$PASTA_R/plataforma.log" \
     "$RAIZ/venv/bin/python" -m execucao panico
