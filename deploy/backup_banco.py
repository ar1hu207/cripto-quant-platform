"""[LIVE-10] Backup de um banco SQLite vivo, com prova de integridade e rotação.

    python deploy/backup_banco.py <banco> <pasta-destino> [--manter N]

Feito para o banco da conta R (dinheiro real), que no dl380 não tinha backup nenhum (revisão
de 26/11). Serve para qualquer conta.

Nunca `cp` do banco vivo (CLAUDE.md §1): o bot escreve a cada ciclo, e a cópia de arquivo pega
uma página no meio da escrita. Aqui a cópia é a API de backup do SQLite (a mesma do `.backup` do
`sqlite3`), que copia um retrato consistente com o bot rodando. Depois, `PRAGMA integrity_check`
na CÓPIA: se não der "ok", ela é apagada e a saída é 1, para o cron (e quem olha o log) saber
que o backup daquela noite não existe. As `N` cópias mais novas ficam; as outras saem.

Agendado por `deploy/cripto-bot-r-backup.timer` ([LIVE-12]): o cron das 03:17 que estava aqui
caía na hora em que o dl380 está DESLIGADO (e o contêiner está em UTC), e cron não recupera a
execução perdida; o timer, com `Persistent=true`, roda ao ligar se perdeu a hora. A cópia sai
com permissão só do dono (`umask 077`): leva a config inteira, inclusive o token do Telegram.
A pasta de destino é só deste banco: a rotação apaga `<nome>-*.db` além das N mais novas.
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime


def _integridade(caminho):
    c = sqlite3.connect(caminho)
    try:
        return c.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        c.close()


def fazer(banco, destino, manter=30, agora=None):
    """Devolve o caminho da cópia íntegra; levanta RuntimeError se a cópia não passou."""
    if not os.path.isfile(banco):
        raise RuntimeError(f"banco {banco} não existe")
    os.makedirs(destino, exist_ok=True)
    nome = os.path.splitext(os.path.basename(banco))[0]
    carimbo = (agora or datetime.now()).strftime("%Y%m%d-%H%M%S")
    copia = os.path.join(destino, f"{nome}-{carimbo}.db")
    origem = sqlite3.connect(f"file:{banco}?mode=ro", uri=True, timeout=30)
    try:
        alvo = sqlite3.connect(copia)
        try:
            origem.backup(alvo)
        finally:
            alvo.close()
    finally:
        origem.close()
    ok = _integridade(copia)
    if ok != "ok":
        os.remove(copia)
        raise RuntimeError(f"integrity_check da cópia deu {ok!r}: cópia apagada")
    copias = sorted(f for f in os.listdir(destino)
                    if f.startswith(nome + "-") and f.endswith(".db"))
    for velha in copias[:-manter] if manter > 0 else []:
        os.remove(os.path.join(destino, velha))
    return copia


def main(argv=None):
    os.umask(0o077)
    ap = argparse.ArgumentParser(description="backup íntegro de um banco SQLite vivo")
    ap.add_argument("banco")
    ap.add_argument("destino")
    ap.add_argument("--manter", type=int, default=30)
    a = ap.parse_args(argv)
    try:
        copia = fazer(a.banco, a.destino, a.manter)
    except Exception as e:
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S} backup FALHOU: {e}")
        return 1
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} backup ok: {copia} "
          f"({os.path.getsize(copia)} bytes, integrity_check ok)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
