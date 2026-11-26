#!/usr/bin/env bash
# [LIVE-5] Pânico da conta R sem painel e sem depender do serviço estar de pé.
#
# Roda NO SERVIDOR. Como root, pela CÓPIA de root ([LIVE-12]): `sudo cripto-panico-r`.
#   Instalar (uma vez, e de novo só depois de ler o diff deste arquivo), do checkout de root:
#     sudo install -o root -g root -m 755 /opt/cripto-r/app/deploy/panico.sh /usr/local/sbin/cripto-panico-r
#     sudo cmp /opt/cripto-r/app/deploy/panico.sh /usr/local/sbin/cripto-panico-r && echo igual
#   Nunca de /home/cripto: root instalaria um arquivo que o usuário `cripto` (o processo da A,
#   exposto na internet) pode alterar, e invadir a A viraria root no próximo pânico.
#   Como `cripto-r` (`sudo -u cripto-r bash /opt/cripto-r/app/deploy/panico.sh`) também
#   funciona, mas sem conseguir parar a unit.
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
# visível em `ps` por até 170 s); e o Python roda sempre como o usuário da R (como root ele
# criava `-wal`/`-shm` e log com dono root, e o serviço não subia mais).
#
# [LIVE-14] A R roda como `cripto-r`, com código e venv de root em /opt/cripto-r e o estado em
# /var/lib/cripto-r. A senha do painel vem do r.env da R, não mais do .env da A.
set -u

OPT_R="${OPT_R:-/opt/cripto-r}"
RAIZ="$OPT_R/app"
PASTA_R="${PASTA_R:-/var/lib/cripto-r}"
PORTA="${PORTA:-8003}"
UNIT="${UNIT:-cripto-bot-r}"
USUARIO="${USUARIO:-cripto-r}"

cd "$RAIZ" || { echo "panico: pasta $RAIZ não existe"; exit 2; }

# Uma chave do r.env, como o systemd a lê, sem executar nada.
ler() {
    sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$PASTA_R/r.env" 2>/dev/null | tail -n 1 \
        | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/"
}

if [ ! -r "$PASTA_R/r.env" ]; then
    echo "panico: não consigo ler $PASTA_R/r.env como $(id -un); rode como root ou como $USUARIO"
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
# Para SEMPRE que não estiver parado ([LIVE-12]): em crash-loop a unit fica "activating"
# entre as tentativas, o `is-active` dizia "não está de pé", e o systemd a religava 5 s depois,
# no meio do caminho direto. `stop` também cancela o restart pendente.
PAROU=0
estado="$(systemctl is-active "$UNIT" 2>/dev/null)"
case "$estado" in
    inactive|failed|unknown|"") ;;
    *)
        if [ "$(id -u)" = "0" ]; then
            systemctl stop "$UNIT"
        else
            sudo -n systemctl stop "$UNIT" 2>/dev/null
        fi
        estado="$(systemctl is-active "$UNIT" 2>/dev/null)"
        case "$estado" in
            inactive|failed) PAROU=1; echo "panico: serviço $UNIT parado" ;;
            *)
                echo "panico: AVISO: $UNIT segue '$estado' (sem root?). Seguindo assim mesmo: fechar"
                echo "        vale mais que o risco de os dois agirem juntos. Depois: sudo systemctl stop $UNIT" ;;
        esac ;;
esac

CMD=(env CONTA=R CORRETORA_HABILITADA=1 TZ=America/Sao_Paulo
     DB_PATH="$PASTA_R/trading.db" LOG_PATH="$PASTA_R/plataforma.log"
     ARQUIVOS_ENV="$PASTA_R/r.env:$PASTA_R/corretora.env"
     GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0="$RAIZ"
     "$OPT_R/venv/bin/python" -m execucao panico)
if [ "$(id -un)" = "$USUARIO" ]; then
    "${CMD[@]}"
elif [ "$(id -u)" = "0" ]; then
    runuser -u "$USUARIO" -- "${CMD[@]}"
else
    sudo -n -u "$USUARIO" -- "${CMD[@]}" || {
        echo "panico: rode como root (sudo cripto-panico-r) ou como $USUARIO"; exit 2; }
fi
st=$?
if [ "$PAROU" = "1" ]; then
    echo "panico: o serviço $UNIT ficou PARADO. Religar (com tudo conferido): sudo systemctl start $UNIT"
fi
exit $st
