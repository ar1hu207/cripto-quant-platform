#!/bin/bash
# Deploy do cripto-bot na VM: um comando so. [P2-3]
#
#   bash deploy/atualizar.sh              # atualiza para o topo da main
#   bash deploy/atualizar.sh <commit>     # vai para um commit especifico (rollback)
#
# Roda NA VM, dentro de /home/ubuntu/cripto-bot. Antes deste script o deploy era copia
# manual de arquivo e nao havia como saber qual commit estava rodando.
#
# O que ele NAO faz, de proposito: nao mexe no trading.db (esta no .gitignore, e o banco
# vivo e a unica copia), nao mexe no .env, e nao religa o auto_trade se ele ja estava
# desligado antes de voce chamar - religar sozinho seria o script decidindo por voce que
# esta tudo bem.
set -euo pipefail

APP=/home/ubuntu/cripto-bot
ALVO="${1:-origin/main}"
cd "$APP"

echo "== 0. estado antes =="
ANTES=$(git rev-parse --short HEAD)
echo "HEAD atual: $ANTES"
if [ -n "$(git status --porcelain)" ]; then
  echo "ABORTADO: a arvore da VM esta suja. Deploy so a partir de arvore limpa -"
  echo "senao a modificacao local se perde sem ninguem ver. Rode 'git status' e decida."
  git status --short
  exit 1
fi

echo "== 1. backup do banco ANTES de qualquer troca =="
# sudo: o script de backup le /etc/cripto-bot-backup.sas (600 root) e escreve em
# /var/log/cripto-backup.log. Como ubuntu ele falha em "Permission denied" e o deploy
# aborta aqui - foi o que aconteceu na primeira tentativa de deploy do M2.
sudo /usr/local/bin/cripto-backup.sh >/dev/null 2>&1 && echo "backup ok" || {
  echo "ABORTADO: o backup falhou. Nao se troca codigo sem copia integra do banco."; exit 1; }

echo "== 2. congela: auto_trade=0 e conta posicoes abertas =="
AUTO_ANTES=$(sqlite3 trading.db "SELECT valor FROM config WHERE chave='auto_trade';")
sqlite3 trading.db "UPDATE config SET valor='0' WHERE chave='auto_trade';"
ABERTAS=$(sqlite3 trading.db "SELECT COUNT(*) FROM posicoes WHERE status='aberta';")
echo "auto_trade era $AUTO_ANTES, agora 0 · posicoes abertas: $ABERTAS"
[ "$ABERTAS" != "0" ] && echo "AVISO: deployando com posicao aberta. O ideal e zero (RUNBOOK-VM 5.4)."

echo "== 3. busca e move =="
git fetch --quiet origin
git checkout --quiet --detach "$ALVO" 2>/dev/null || git checkout --quiet "$ALVO"
DEPOIS=$(git rev-parse --short HEAD)
echo "HEAD: $ANTES -> $DEPOIS"

echo "== 4. compila com o venv de PRODUCAO antes de subir =="
# `./*.py` e glob de RAIZ, nao recursivo, e continua assim de proposito depois do [P2-16].
#
# Desde o [P2-16] a raiz e exatamente a plataforma viva (os 11 modulos do fecho de `api.py`)
# mais as tres provas que se rodam por `python <arquivo>` -- ou seja, este glob passou a ser
# "tudo que o servico pode importar", que e mais preciso do que era antes da reorganizacao.
# `pesquisa/` e `legado/` ficam de fora, e isso e a decisao, nao o esquecimento dela:
# pesquisa nao e codigo de producao (nada em `api.py` alcanca `pesquisa/`, verificado por AST)
# e legado nem sequer e executavel onde esta (`legado/README.md`). Estender o glob para
# `pesquisa/*.py` abortaria um deploy de PRODUCAO por causa de um script de pesquisa quebrado
# que a producao nunca carrega -- acoplaria a disponibilidade do bot a um arquivo que nao
# participa dele. Quem quiser o portao para pesquisa, o lugar e o pytest/CI, nao aqui.
./venv/bin/python -m py_compile ./*.py || {
  echo "ABORTADO na compilacao. Voltando para $ANTES."; git checkout --quiet "$ANTES"; exit 1; }
echo "compila ok"

echo "== 5. reinicia =="
sudo systemctl restart cripto-bot
sleep 8

echo "== 6. verifica =="
systemctl is-active cripto-bot
journalctl -u cripto-bot -n 15 --no-pager | grep -ciE "traceback" || true
sqlite3 trading.db "PRAGMA integrity_check;"
sleep 15
NOVAS=$(sqlite3 trading.db "SELECT COUNT(*) FROM equity WHERE ts > datetime('now','-1 minutes','localtime');")
echo "linhas de equity no ultimo minuto: $NOVAS  (0 = o ciclo NAO esta girando)"
curl -s --max-time 10 http://127.0.0.1:8000/health; echo

echo
echo "== FIM =="
echo "auto_trade continua 0. Religue a mao, DEPOIS de olhar o /status:"
echo "  sqlite3 $APP/trading.db \"UPDATE config SET valor='1' WHERE chave='auto_trade';\""
echo "Rollback: bash deploy/atualizar.sh $ANTES"
