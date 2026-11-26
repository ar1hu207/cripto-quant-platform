#!/usr/bin/env bash
# [LIVE-5] Pânico da conta R sem painel e sem depender do serviço estar de pé.
#
# Roda NO SERVIDOR, como root ou como o usuário `cripto`:  bash deploy/panico.sh
#
# Dois caminhos, nesta ordem:
#   1. o serviço responde -> POST /panico nele (o mesmo botão do painel);
#   2. o serviço não responde -> PARA o serviço (para os dois não agirem ao mesmo tempo no mesmo
#      banco) e roda `python -m execucao panico`, que fala direto com a corretora usando o banco
#      e a chave da conta R. É o caminho para o dia em que o processo travou e a posição
#      continua aberta lá.
# Nos dois o `auto_trade` é desligado ANTES de fechar ([P1-7]), as entradas pendentes são
# canceladas na corretora e toda posição é fechada a mercado (reduce-only: nunca abre o lado
# oposto, nem rodando duas vezes).
#
# Se nem isto funcionar (servidor fora do ar, ou a Binance recusando a chave porque o IP de
# saída mudou): o stop de cada posição está NA Binance e continua valendo. Fechar à mão é no
# aplicativo da Binance, em Futuros > Posições.
#
# Revisão de 26/11: os arquivos de ambiente NÃO são lidos com `source` (um valor com espaço ou
# `$` era executado pelo bash); a senha do painel não vai na linha de comando do curl (ficava
# visível em `ps` por até 170 s); e o Python roda sempre como `cripto` (como root ele criava
# `-wal`/`-shm` e log com dono root, e o serviço não subia mais).
set -u

RAIZ="${RAIZ:-/home/cripto/cripto-bot}"
PASTA_R="${PASTA_R:-/home/cripto/cripto-bot-r}"
PORTA="${PORTA:-8003}"
UNIT="${UNIT:-cripto-bot-r}"
USUARIO="${USUARIO:-cripto}"

cd "$RAIZ" || { echo "panico: pasta $RAIZ não existe"; exit 2; }

# Uma chave do `.env`, como o systemd a lê, sem executar nada.
ler() {
    sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$RAIZ/.env" 2>/dev/null | tail -n 1 \
        | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}

if [ ! -r "$RAIZ/.env" ]; then
    echo "panico: não consigo ler $RAIZ/.env como $(id -un); rode como root ou como $USUARIO"
fi
U="$(ler DASH_USER)"; U="${U:-admin}"
P="$(ler DASH_PASS)"
# Escapa para o formato de config do curl (entre aspas: \ e " escapados).
P_ESC=${P//\\/\\\\}; P_ESC=${P_ESC//\"/\\\"}
U_ESC=${U//\\/\\\\}; U_ESC=${U_ESC//\"/\\\"}

echo "panico: tentando o serviço em 127.0.0.1:$PORTA ..."
# 170 s: o pânico espera a reconciliação em curso soltar a conta, e cada chamada dela à
# corretora pode levar até 10 s. Cortar antes disso seria desistir de um pânico que ia funcionar.
# A credencial vai pela ENTRADA PADRÃO (`-K -`), não pela linha de comando.
if resposta=$(printf 'user = "%s:%s"\n' "$U_ESC" "$P_ESC" \
              | curl -sS -m 170 -K - -X POST "http://127.0.0.1:$PORTA/panico"); then
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

# O serviço e a linha de comando no mesmo banco ao mesmo tempo: a linha de comando cancelaria
# uma ordem que o serviço está enviando. Parado o serviço, só um age. Ele fica PARADO no fim.
PAROU=0
if systemctl is-active --quiet "$UNIT" 2>/dev/null; then
    if [ "$(id -u)" = "0" ]; then
        systemctl stop "$UNIT" && PAROU=1 && echo "panico: serviço $UNIT parado"
    elif sudo -n systemctl stop "$UNIT" 2>/dev/null; then
        PAROU=1; echo "panico: serviço $UNIT parado"
    else
        echo "panico: AVISO: não consegui parar $UNIT (sem sudo). Seguindo assim mesmo: fechar"
        echo "        vale mais que o risco de os dois agirem juntos. Depois: sudo systemctl stop $UNIT"
    fi
fi

CMD=(env CONTA=R CORRETORA_HABILITADA=1 TZ=America/Sao_Paulo
     DB_PATH="$PASTA_R/trading.db" LOG_PATH="$PASTA_R/plataforma.log"
     ARQUIVOS_ENV="$RAIZ/.env:$PASTA_R/corretora.env"
     "$RAIZ/venv/bin/python" -m execucao panico)
if [ "$(id -un)" = "$USUARIO" ]; then
    "${CMD[@]}"
elif [ "$(id -u)" = "0" ]; then
    runuser -u "$USUARIO" -- "${CMD[@]}"
else
    sudo -n -u "$USUARIO" -- "${CMD[@]}" || {
        echo "panico: rode como root ou como $USUARIO (sudo bash deploy/panico.sh)"; exit 2; }
fi
st=$?
if [ "$PAROU" = "1" ]; then
    echo "panico: o serviço $UNIT ficou PARADO. Religar (com tudo conferido): sudo systemctl start $UNIT"
fi
exit $st
