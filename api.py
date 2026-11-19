"""
Backend FastAPI — leitura + fluxo de confirmação (propor → confirmar → posição).
Worker em background mantém o sistema VIVO: marca posições no preço real,
fecha em stop/liquidação e roda scans periódicos.

Rodar:  uvicorn api:app --port 8000      |  Docs: http://localhost:8000/docs
"""
import base64
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from urllib.parse import quote, urlparse

import ccxt
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import alvos
import db
import simulador
import signal_engine
import mercado
import dca
import autotrader
import logbot
import push
from logbot import log
from versao import VERSAO

POLL_ATUALIZAR = 15   # marca posições a cada 15s
INTERVALO_SCAN = 60   # [P2-15] scan de sinais a cada 60s, por RELÓGIO (ver _scan_devido)
_worker_on = {"v": True}
_health = {"iniciado": None, "ultimo_ciclo": None, "ciclos": 0, "erros": 0}
_saidas = {"v": [], "t": None}   # recomendações de saída ativa + monotonic do cálculo ([F-9])
SAIDAS_TTL_S = 30     # [F-9] o painel reusa o cálculo por até 30 s em vez de pedir 2 req/posição
_auto = {"v": {"ativo": False}}   # último ciclo do auto-trader
_poda = {"dia": None, "ultimo": None}   # [P2-11] retenção da curva de equity, 1x/dia
_scan_sched = {"proximo": 0.0}          # [P2-15] instante (monotonic) do próximo scan; 0 = já vence

# [vigia] Quanto tempo sem ciclo completo conta como "o bot parou". O ciclo leva ~7,5 s
# (F-10) mais os 15 s de sono; 300 s são ~13 ciclos perdidos, folga para um scan lento ou
# uma rede engasgada sem virar alarme falso. É o mesmo número no watchdog do systemd
# (`WatchdogSec` em `deploy/cripto-bot.service`) e no `/health` que a vigia externa lê.
VIGIA_CICLO_S = 300
_INICIO_MONO = time.monotonic()
_vigia = {"ultimo": None}               # monotonic do último ciclo COMPLETO


def _sd_notify(msg: bytes) -> bool:
    """[vigia] Avisa o systemd (protocolo sd_notify) sem dependência nova. No-op fora dele.

    Com `WatchdogSec` na unit, o systemd mata e reinicia o serviço se este aviso parar de
    chegar -- que é o caso que nada cobria: processo VIVO com o ciclo parado (thread do worker
    presa ou morta). `Restart=always` só pega processo que morre; métrica da Azure só vê a VM.
    """
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return False
    if addr.startswith("@"):                  # socket abstrato do Linux
        addr = "\0" + addr[1:]
    try:
        import socket
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
            s.connect(addr)
            s.sendall(msg)
        return True
    except (OSError, AttributeError):         # AttributeError: AF_UNIX não existe no Windows
        return False


def _scan_devido(agora=None):
    """[P2-15] O scan vence AGORA? Ao dizer que sim, já reagenda o próximo.

    Era `_health["ciclos"] % CICLOS_POR_SCAN == 0`, avaliado DENTRO do try do ciclo. Quando
    uma exceção anterior abortava o try (o caso do [P1-1]), aquele slot era perdido e o scan
    seguinte só vinha 4 ciclos depois: sob falha intermitente o intervalo real virava 2-3
    minutos, sem ninguém ter decidido isso. Contar ciclos EXECUTADOS mede o que sobreviveu;
    o que a cadência precisa medir é tempo, e quem mede tempo é relógio.

    Reagenda ANTES de rodar, e é chamada de FORA do try do ciclo — as duas coisas juntas são
    o card. Reagendamento depois de um `except` que pode ser pulado é o mesmo bug com outra
    roupa. Está extraída do worker porque a regra não é testável dentro de um `while True`
    com `sleep`: com o instante como parâmetro, `python api.py` prova a cadência sem esperar.
    """
    agora = time.monotonic() if agora is None else agora
    if agora < _scan_sched["proximo"]:
        return False
    _scan_sched["proximo"] = agora + INTERVALO_SCAN
    return True


def _banca_e_equity():
    """(banca, equity total) lidos do MESMO instante. Sem o BEGIN cada SELECT via um retrato
    diferente: um fechamento com lucro entre os dois somava a banca velha ao unreal já sem a
    posição, e o ponto gravado na curva saía abaixo do real (entrava no drawdown e, se fosse o
    primeiro do dia, virava a base da trava diária)."""
    with db.conectar() as c:
        c.execute("BEGIN")
        banca = c.execute("SELECT atual FROM banca WHERE id=1").fetchone()["atual"]
        unreal = c.execute("SELECT COALESCE(SUM(pnl),0) FROM posicoes WHERE status='aberta'").fetchone()[0]
    return banca, banca + (unreal or 0)


def equity_total():
    return _banca_e_equity()[1]


def _saidas_decidem(cfg):
    """[F-9] O auto-trader FECHA pelo gestor de saída? Só com `auto_fechar_saida` ligado E o
    trailing desligado -- a mesma condição do passo 1 de `autotrader.auto_executar`. Fora
    dela a recomendação não decide nada no ciclo, e calculá-la a cada 15 s por posição (livro
    de ofertas + trades na rede) era o desperdício que o [F-9] mediu: zero `auto-saida` em 62
    trades. Lê a condição do lugar que a aplica, para as duas não divergirem."""
    return (autotrader._verdade(cfg.get("auto_fechar_saida", "1"))
            and not autotrader._verdade(cfg.get("trailing_ativo", "1")))


def _calcular_saidas():
    abertas = db.listar("posicoes", 50, "WHERE status='aberta'")
    cfg = db.get_config()                   # uma leitura para todas, e não uma por posição
    v = [r for r in (signal_engine.avaliar_saida(p, cfg) for p in abertas) if r]
    _saidas.update(v=v, t=time.monotonic())
    return v


def worker():
    _health["iniciado"] = str(pd.Timestamp.now())
    log("worker iniciado")
    while _worker_on["v"]:
        try:
            simulador.processar_ordens()                # [EX-1] ordens post-only: enche ou expira
            simulador.atualizar()                       # marca/fecha posições no preço real
            # [F-9] o gestor de saída só roda no ciclo quando o auto-trader PODE agir sobre ele;
            # com o trailing ligado (o vivo), quem pede é o painel, sob demanda (`GET /saidas`).
            saidas = _calcular_saidas() if _saidas_decidem(db.get_config()) else []
            dca.processar_devidos()                     # aportes DCA vencidos
            try:
                _auto["v"] = autotrader.auto_executar(saidas)   # bot abre/fecha sozinho (se ligado)
            except Exception as e:                      # falha do bot não derruba o snapshot de equity abaixo
                _health["erros"] += 1
                log(f"auto-trader erro: {e}", "error")
            banca_agora, equity_agora = _banca_e_equity()   # as duas do mesmo instante
            with db.conectar() as c:                    # snapshot de equity p/ o gráfico
                c.execute("INSERT INTO equity(ts,banca,equity_total) VALUES(?,?,?)",
                          (str(pd.Timestamp.now()), banca_agora, equity_agora))
            _health["ultimo_ciclo"] = str(pd.Timestamp.now())
            _vigia["ultimo"] = time.monotonic()
            _sd_notify(b"WATCHDOG=1")           # [vigia] só ciclo COMPLETO alimenta o watchdog
        except Exception as e:                          # nunca derruba o loop
            _health["erros"] += 1
            log(f"worker erro: {e}", "error")
        # [P2-15] o scan sai de dentro do try acima: falha na marcação não consome mais o
        # slot da varredura. Fica DEPOIS do ciclo, e não antes, porque marcar posição é o
        # caminho do stop/liquidação — atrasá-lo pela duração do scan seria trocar um
        # instrumento impreciso por um risco real. O auto-trader passa a consumir o sinal
        # no ciclo seguinte (15s), folgado dentro dos `auto_freshness_min` (12 min).
        if _scan_devido():
            try:
                signal_engine.scan()                    # atualiza sinais
            except Exception as e:                      # já reagendado: erro não trava a cadência
                _health["erros"] += 1
                log(f"scan erro: {e}", "error")
        # [P2-11] retenção da curva de equity, 1x por dia. Bloco PRÓPRIO, fora do try
        # acima: faxina de banco não pode nem derrubar o ciclo nem ser derrubada por ele.
        # Marca o dia ANTES de podar — se a poda falhar, ela volta amanhã e não a cada 15s
        # martelando o mesmo banco. Roda também no primeiro ciclo após um start, que é o
        # que faz o deploy num banco antigo se acertar sozinho.
        hoje = str(pd.Timestamp.now().date())
        if _poda["dia"] != hoje:
            _poda["dia"] = hoje
            try:
                _poda["ultimo"] = db.podar_equity()
                log(f"[P2-11] poda da equity: {_poda['ultimo']}")
            except Exception as e:
                _health["erros"] += 1
                log(f"poda da equity falhou: {e}", "error")
        _health["ciclos"] += 1
        time.sleep(POLL_ATUALIZAR)


@asynccontextmanager
async def lifespan(app):
    _guarda_conta()                 # [AB-1] antes de abrir banco: conta B no banco da A não sobe
    db.init_db()
    threading.Thread(target=worker, daemon=True).start()
    push.iniciar()                  # [PUSH-2] o relogio do resumo periodico; sem chave, no-op
    yield
    _worker_on["v"] = False


# Login básico (HTTP Basic): ativo só quando DASH_PASS está setado (deploy público).
# Local fica sem senha. O navegador guarda o login e o manda nos fetch automaticamente.
# Lido ANTES de criar o app porque decide se /docs e /openapi.json existem.
DASH_USER = os.environ.get("DASH_USER", "admin")
DASH_PASS = os.environ.get("DASH_PASS", "")

# Não existe bandeira para servir o painel sem senha na internet. Existiu uma
# (PERMITIR_SEM_SENHA) e foi exatamente ela que deixou /reset, /panico, /config e /auto
# abertos para qualquer um em produção: a guarda que recusa acesso externo sem DASH_PASS
# só protege se não houver como desligá-la. Sem senha, o backend atende só loopback.
# Com senha, /docs e /openapi.json somem — mapa da API não é coisa de deploy público.
app = FastAPI(title="Cripto Bot API", version=VERSAO, lifespan=lifespan,
              docs_url=None if DASH_PASS else "/docs",
              redoc_url=None if DASH_PASS else "/redoc",
              openapi_url=None if DASH_PASS else "/openapi.json")
# Origens do front. Local/monolito: "*". Front separado (Vercel): liste a origem exata,
# ex CORS_ORIGINS="https://meu-bot.vercel.app" (várias separadas por vírgula).
# O add_middleware do CORS mora DEPOIS de auth_basica (fim deste bloco): a ordem decide
# quem embrulha quem, e o CORS precisa embrulhar a auth. Ver a nota lá embaixo.
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]

LOOPBACK = {"127.0.0.1", "::1"}

# [AB-1] Teste A/B. A conta B é uma SEGUNDA instância deste mesmo código, com banco, log e
# banca próprios (`DB_PATH`, `LOG_PATH`), escutando só em loopback. Esta instância (A) a
# expõe em `/testeB/...` repassando a requisição: o Funnel e o CORS continuam com uma porta
# e uma origem só, e a autenticação continua sendo a desta porta (o middleware abaixo roda
# antes do repasse) -- e a B confere a MESMA credencial de novo, porque lê o mesmo `.env`.
# As descobertas dos backtests entram no código atrás de chaves de config: a B as liga, a A
# fica como está. Mesmo código, mesmo mercado, mesma hora -- a diferença é só a config.
#
# [AB-2] A conta C é a terceira instância, do mesmo jeito: cópia da config da A com UMA
# diferença de regra (`tp_resto_livre`, T50/T51), exposta em `/testeC/...`. Conta nova é uma
# linha em `_url_teste`, uma unit em `deploy/` e uma pasta própria -- o resto é o mesmo código.
CONTA = (os.environ.get("CONTA") or "A").strip().upper()
TESTEB_URL = (os.environ.get("TESTEB_URL") or "http://127.0.0.1:8001").rstrip("/")
TESTEC_URL = (os.environ.get("TESTEC_URL") or "http://127.0.0.1:8002").rstrip("/")
CONTAS_TESTE = ("B", "C")
HEALTH_PUBLICOS = ("/health",) + tuple(f"/teste{c}/health" for c in CONTAS_TESTE)
MARCA_CONTA = ".conta"          # arquivo na pasta do banco: diz de qual conta a pasta é


def _url_teste(conta):
    """Endereço da instância de teste. Lido na chamada, não no import: é o que deixa o teste
    apontar a conta para um servidor falso sem reimportar o módulo."""
    return {"B": TESTEB_URL, "C": TESTEC_URL}[conta]


def _dona_da_pasta(pasta):
    """A conta gravada na marca da pasta, ou None se a pasta não tem marca."""
    try:
        with open(os.path.join(pasta, MARCA_CONTA), encoding="utf-8") as f:
            return f.read().strip().upper() or None
    except OSError:
        return None


def _guarda_conta():
    """[AB-1] A conta B NÃO sobe se o banco ou o log dela forem os da A.

    Nasceu de um incidente, em 10/11, no primeiro deploy: o `.env` da A define `DB_PATH`, e no
    systemd o `EnvironmentFile` vence o `Environment=` da unit. A B subiu em cima do banco da A
    -- dois workers no mesmo banco -- e a configuração "da B" foi gravada na produção (49 s com
    `auto_trade=0`; o `/reset` da B, que viria em seguida, teria apagado o histórico da A).

    A unit agora força o caminho no `ExecStart`, mas a garantia não pode depender de a unit
    estar certa: a A mora no diretório do código, e a B nunca. A versão-sintoma seria só
    consertar a unit -- e o próximo `.env` ou a próxima unit copiada repetiriam o erro.

    **[AB-2] Com três contas, "não é o da A" deixou de bastar.** A unit da C nasce copiada da
    unit da B: esquecer de trocar o `DB_PATH` poria a C no banco da B, e a regra acima deixava
    (a pasta da B não é a raiz). Cada pasta de conta de teste passa a ter uma marca, `.conta`,
    com a letra da dona:
      - marca de OUTRA conta -> não sobe (vale para a A também: ela não abre banco de teste);
      - pasta sem marca e SEM banco -> conta nova: grava a marca e sobe;
      - pasta sem marca e COM banco -> só a B a adota, porque o banco dela nasceu em 10/11,
        antes da marca existir. Qualquer outra conta recusa: banco que já existe e não diz de
        quem é não é dela. (Restaurou um backup numa pasta nova? Grave a letra em `.conta`.)
    Só a pasta do BANCO recebe marca. A do log é conferida e nunca gravada: se um `LOG_PATH`
    errado pudesse marcar a pasta onde caiu, a conta com a unit errada tomaria a pasta da outra
    e a dona é que passaria a ser recusada no boot seguinte."""
    raiz = os.path.dirname(os.path.realpath(__file__))
    for nome, caminho in (("DB_PATH", db.DB), ("LOG_PATH", logbot.LOG_FILE)):
        pasta = os.path.dirname(os.path.realpath(caminho))
        if CONTA != "A" and pasta == raiz:
            raise RuntimeError(f"conta {CONTA} recusada: {nome}={caminho} é o da conta A. Defina "
                               f"um caminho próprio (deploy/cripto-bot-{CONTA.lower()}.service).")
        dona = _dona_da_pasta(pasta)
        if dona and dona != CONTA:
            raise RuntimeError(f"conta {CONTA} recusada: {nome}={caminho} está na pasta da conta "
                               f"{dona} ({MARCA_CONTA}). Cada conta tem a pasta dela.")
        if dona or CONTA == "A" or nome != "DB_PATH":
            continue
        if os.path.exists(caminho) and CONTA != "B":
            raise RuntimeError(f"conta {CONTA} recusada: {nome}={caminho} já existe e a pasta não "
                               f"tem a marca {MARCA_CONTA}. Se o banco é mesmo da conta {CONTA}, "
                               "grave a letra nesse arquivo; se não é, corrija o caminho.")
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, MARCA_CONTA), "w", encoding="utf-8") as f:
            f.write(CONTA + "\n")
# A senha tem 24 caracteres alfanuméricos (~10^43 combinações): força bruta é inviável
# por construção, então o throttle serve para conter scanner barulhento, não como defesa
# principal. Valores folgados porque o painel dispara ~5 requisições paralelas por ciclo
# e uma credencial velha no localStorage gastaria o limite antes da pessoa recarregar.
AUTH_MAX_FALHAS = 15       # senhas erradas antes de bloquear o IP
AUTH_BLOQUEIO_S = 120      # duração do bloqueio
_falhas = {}               # ip -> (n_falhas, bloqueado_ate)
_falhas_lock = threading.Lock()


def _via_proxy(request: Request) -> bool:
    """Requisição chegou por proxy reverso (Caddy) = veio da internet, não é acesso local."""
    return bool(request.headers.get("x-forwarded-for") or request.headers.get("x-forwarded-proto"))


def _cliente_ip(request: Request) -> str:
    """IP real do cliente. Só confia no X-Forwarded-For quando o peer direto é o nosso
    proxy local — senão qualquer um forjaria o header e escaparia do bloqueio."""
    peer = request.client.host if request.client else ""
    xff = request.headers.get("x-forwarded-for", "")
    if peer in LOOPBACK and xff:
        # O ÚLTIMO item, não o primeiro. Há um proxy só na frente (Funnel ou Caddy), e o que ELE
        # escreve é o último: proxy que anexa entrega "o que o cliente mandou, IP real". Lendo o
        # primeiro, quem errava a senha trocava de "IP" a cada tentativa e nunca era bloqueado.
        # Com proxy que sobrescreve o cabeçalho há um item só, e dá no mesmo.
        return xff.split(",")[-1].strip()
    return peer


def _origem_local(origem: str) -> bool:
    """O cabeçalho Origin aponta para esta própria máquina? "null" (file://, iframe sandbox) e
    qualquer coisa que não parseie contam como de fora."""
    try:
        host = urlparse(origem).hostname
    except ValueError:
        return False
    return host in ("localhost", "127.0.0.1", "::1")


def _registrar_falha(ip: str):
    agora = time.time()
    with _falhas_lock:
        if len(_falhas) > 5000:                                  # poda: XFF forjado não vira vazamento
            for k, (_, ate) in list(_falhas.items()):
                if agora > ate:
                    _falhas.pop(k, None)
        n = _falhas.get(ip, (0, 0.0))[0] + 1
        _falhas[ip] = (n, agora + AUTH_BLOQUEIO_S if n >= AUTH_MAX_FALHAS else 0.0)
        return n


@app.middleware("http")
async def auth_basica(request: Request, call_next):
    # OPTIONS = preflight do CORS: o navegador manda SEM Authorization, e exigir credencial
    # nele mataria todo fetch do front separado. Com o CORSMiddleware por fora, o preflight
    # do navegador já é respondido lá e nem chega aqui; isto cobre o OPTIONS avulso.
    # /testeB/health é o /health da conta B: público pelo mesmo motivo (o painel o lê antes do
    # login para dizer se o backend está de pé), e não expõe nada além da idade do ciclo.
    # Só GET: a isenção era por caminho, e um POST anônimo em /testeB/health tinha o corpo lido
    # em memória e repassado à conta B sem credencial nenhuma. [AB-2] Vale igual para a C.
    if request.method == "OPTIONS" or (request.method == "GET"
                                       and request.url.path in HEALTH_PUBLICOS):
        return await call_next(request)

    if not DASH_PASS:
        # SEM SENHA: só acesso local direto. Se veio de fora (IP não-loopback) ou por proxy,
        # RECUSA em vez de servir o painel aberto pra internet. Esquecer o DASH_PASS no .env
        # é o erro mais provável do deploy — aqui ele falha alto em vez de falhar aberto.
        peer = request.client.host if request.client else ""
        if peer not in LOOPBACK or _via_proxy(request):
            log(f"acesso externo recusado: DASH_PASS não definido (peer={peer})", "error")
            return PlainTextResponse(
                "Backend exposto sem DASH_PASS. Defina DASH_PASS no .env e reinicie o serviço.",
                status_code=503)
        # Loopback não basta: o NAVEGADOR do dono também é loopback. Sem senha e com CORS "*",
        # qualquer página aberta nele mandava `POST /reset`, `/panico` ou `/config` para
        # 127.0.0.1:8000 e era atendida. Quem denuncia é o Origin, que o navegador manda em todo
        # POST e em todo GET entre origens, e que o painel local (servido por este processo)
        # manda apontando para cá. curl e script não mandam Origin, e seguem entrando.
        # Limite declarado: GET por DNS rebinding chega sem Origin; fecha-se com senha.
        origem = request.headers.get("origin")
        if origem is not None and not _origem_local(origem):
            log(f"origem recusada no modo sem senha: {origem[:120]}", "error")
            return PlainTextResponse(
                "Sem DASH_PASS o backend só atende o painel aberto nesta própria máquina.",
                status_code=403)
        return await call_next(request)

    ip = _cliente_ip(request)
    with _falhas_lock:
        bloqueado_ate = _falhas.get(ip, (0, 0.0))[1]
    espera = bloqueado_ate - time.time()
    if espera > 0:
        return PlainTextResponse(f"Tentativas demais. Tente de novo em {int(espera)}s.",
                                 status_code=429, headers={"Retry-After": str(int(espera) + 1)})

    h = request.headers.get("authorization", "")
    tentou = h.startswith("Basic ")        # mandou credencial (ainda que errada)?
    ok = False
    if tentou:
        try:
            u, _, p = base64.b64decode(h[6:]).decode("utf-8", "ignore").partition(":")
            ok = secrets.compare_digest(u, DASH_USER) and secrets.compare_digest(p, DASH_PASS)
        except Exception:
            ok = False
    if not ok:
        # Só conta como tentativa de invasão quem MANDOU credencial errada. Requisição sem
        # credencial nenhuma é só a primeira batida na porta — o próprio painel faz ~5 delas
        # por ciclo antes do login, e contá-las bloqueava o usuário legítimo em segundos.
        # Força bruta precisa enviar senhas para testá-las, então a proteção continua inteira.
        if tentou:
            n = _registrar_falha(ip)
            if n >= AUTH_MAX_FALHAS:
                log(f"IP {ip} bloqueado por {AUTH_BLOQUEIO_S}s após {n} senhas erradas", "error")
        return PlainTextResponse("Auth necessária", status_code=401,
                                 headers={"WWW-Authenticate": 'Basic realm="Cripto Bot"'})
    with _falhas_lock:
        _falhas.pop(ip, None)                                    # login certo zera o contador
    return await call_next(request)


# CORS registrado DEPOIS da auth de propósito: no Starlette o último middleware adicionado é
# o mais EXTERNO, então assim o CORS embrulha a auth em vez de ficar por dentro dela.
#
# Por dentro, toda resposta que a auth devolve sozinha — 401, 429, 503 — saía sem o header
# Access-Control-Allow-Origin, porque o CORSMiddleware nunca chegava a rodar. Para o painel
# no Vercel isso não é "401": é falha de CORS. O fetch REJEITA, o `if(r.status===401)` do
# front nunca executa, o prompt de senha nunca aparece e o painel parece backend fora do ar.
# Ficou latente enquanto o backend respondia tudo aberto (200 sempre passava pelo CORS) e
# apareceu inteiro no primeiro deploy com DASH_PASS: ligar a senha derrubou o login.
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


# ---------- catálogo de configuração ----------
# Lista FECHADA do que pode ser gravado na config, com tipo e faixa. Sem isto, POST /config
# aceitava qualquer chave com qualquer valor e o erro só aparecia lá no float() de
# guarda_risco() — ou seja, longe da causa e no caminho de TODO /estado.
#
# Onde isto deveria morar: em db.py, ao lado do CONFIG_PADRAO, que é o registro natural das
# chaves. Ficou aqui porque db.py é território de outro agente nesta onda (§3 do
# PLANO-EXECUCAO-2026-08-20). Levar para lá é trabalho do [P2-11]/[P2-16].
_TFS = ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d")

CONFIG_CATALOGO = {
    # risco — faixas apertadas de propósito: um dígito a mais aqui é dinheiro
    "risco_por_trade":      ("float", 0.001, 0.2),
    "limite_perda_dia":     ("float", 0.0, 0.5),      # 0 = trava no primeiro centavo de perda
    "risco_aberto_max":     ("float", 0.0, 1.0),      # 0 = sem teto (semântica existente)
    "exposicao_max":        ("float", 0.0, 1.0),      # 0 = sem teto (semântica existente)
    "taxa_por_lado":        ("float", 0.0, 0.01),
    # execucao [EX-1]. `exec_modo` e a unica chave desta secao que muda COMPORTAMENTO -- as
    # outras tres so parametrizam. Faixas apertadas pelo mesmo motivo das de risco: o ganho
    # inteiro do post-only mora em ~0,03% por lado ([CX-1]), entao um digito a mais em
    # `taxa_maker` apaga o efeito que a feature existe para capturar.
    "exec_modo":            ("enum", ("mercado", "post_only")),
    "taxa_maker":           ("float", 0.0, 0.01),
    "exec_maker_off":       ("float", 0.0, 0.05),     # 0 = limite no proprio preco
    "exec_ordem_ttl_s":     ("float", 0.0, 86400.0),  # 0 = expira no proximo ciclo
    "alavancagem_padrao":   ("float", 1.0, 50.0),
    # scanner / sinais
    "timeframe":            ("enum", _TFS),
    "timeframes":           ("lista_tf",),
    "ativos":               ("pares",),
    "min_conviccao":        ("float", 0.0, 100.0),
    "adx_min":              ("float", 0.0, 100.0),
    "adx_max_rev":          ("float", 0.0, 100.0),
    "min_fatores":          ("int", 0, 10),
    "exigir_fluxo":         ("bool",),
    "reversao_ativa":       ("bool",),
    "alvo_roe":             ("float", 0.0, 1000.0),
    # auto-trader
    "auto_trade":           ("bool",),
    "auto_conviccao_min":   ("float", 0.0, 100.0),
    "auto_max_posicoes":    ("int", 1, 20),
    "auto_max_valor_frac":  ("float", 0.001, 1.0),
    "auto_fechar_saida":    ("bool",),
    "auto_freshness_min":   ("float", 0.5, 1440.0),
    "auto_cooldown_min":    ("float", 0.0, 1440.0),
    # [RAJ-1] teto de rajada (autotrader.auto_executar). 0 em `auto_rajada_max` = desligado. A
    # janela não admite 0: "N entradas em zero minutos" não barra nada e leria como ligado.
    "auto_rajada_max":      ("int", 0, 20),
    "auto_rajada_janela_min": ("float", 1.0, 1440.0),
    # [AG-2] tamanho menor no ativo agitado (autotrader._fracao_agitacao). Corte 0 = desligado.
    # A fração não passa de 1 nem chega a 0: a chave só REDUZ o risco de um sinal, e "reduzir a
    # zero" é não operar, que é outra decisão e tem outra chave.
    "auto_agitacao_corte":  ("float", 0.0, 10.0),
    "auto_agitacao_frac":   ("float", 0.1, 1.0),
    # [EST-1] O corte é queda: positivo faria a regra pegar toda venda, e abaixo de −50% em 7
    # dias não sobra amostra para a medida dizer nada.
    "auto_esticado_modo":   ("enum", ("off", "meio", "veto")),
    "auto_esticado_ret7":   ("float", -50.0, -1.0),
    "auto_lev_modo":       ("enum", ("conviccao", "fixo", "risco")),
    "auto_lev_margem_frac": ("float", 0.0, 1.0),      # [LEV-1] 0 = exposicao_max / auto_max_posicoes
    "auto_lev_min":         ("float", 1.0, 50.0),
    "auto_lev_max":         ("float", 1.0, 50.0),
    "trailing_ativo":       ("bool",),
    # [N-13][P-3] O trailing mede em R desde a onda A, e as tres chaves abaixo sao o que
    # DECIDE esse comportamento -- sem verbete aqui o `POST /config` as recusava como "chave
    # desconhecida" e elas so valeriam pelo default. A consequencia nao era cosmetica: em
    # producao, reverter a politica de saida exigiria um DEPLOY em vez de um clique, e e por
    # isso que a decisao D-7 segurou a VM ate este item fechar.
    #
    # Faixas: nenhuma das duas admite 0, e a ausencia e deliberada -- `arma_r=0` armaria o
    # trailing no instante da abertura (stop colado na entrada, todo trade morre no primeiro
    # ruido) e `dist_r=0` poria o stop EM CIMA do preco. O piso de 0,1R e o mesmo espirito do
    # piso 0,001 de `trailing_dist`: apertar pode, zerar e outra coisa. O teto de 10R e
    # folgado de proposito -- acima disso o trailing nunca arma na vida util de um trade
    # intraday, o que equivale a `trailing_ativo=0` dito de um jeito que ninguem le no painel.
    "trailing_unidade":     ("enum", ("R", "preco")),
    "trailing_arma_r":      ("float", 0.1, 10.0),
    "trailing_dist_r":      ("float", 0.1, 10.0),
    "trailing_dist":        ("float", 0.001, 0.5),
    # [TP-1] take profit por estrutura (alvos.py). Pisos: alvo a menos de 0,3R não paga a
    # taxa de ida e volta com folga; fração precisa somar algo > 0 (normalizada em alvos.fracoes).
    "tp_ativo":             ("bool",),
    "tp_n":                 ("int", 1, 5),
    # As duas listas eram "texto": qualquer coisa de até 60 caracteres entrava. "-0.5,1.5" soma 1
    # e passava pela normalização de `alvos.fracoes`; a fração negativa fazia o `fechar_parcial`
    # CREDITAR dinheiro e aumentar a margem. E `tp_fallback_r` negativo ou zero punha o alvo do
    # lado do prejuízo ou em cima da entrada, que "batia" no primeiro poll. Faixa: (0, teto], o
    # zero fica de fora; no máximo 5 itens, que é o teto de `tp_n`.
    "tp_fracoes":           ("lista_num", 0.0, alvos.FRAC_MAX, 5),
    "tp_min_r":             ("float", 0.3, 10.0),
    "tp_max_r":             ("float", 1.0, 30.0),
    "tp_forca_min":         ("float", 0.0, 20.0),
    "tp_fallback_r":        ("lista_num", 0.0, alvos.R_MAX, 5),
    "tp_resto_livre":       ("bool",),
    "tp_so_intactos":       ("bool",),          # [SR-2]
    # [TD-1] filtro de lado pela tendência do diário (tendencia.py, T38)
    "tendencia_filtro":     ("enum", ("off", "d1", "d2")),
    # estado / integrações. `trava_dia_em` NÃO está aqui de propósito: limpar a trava à mão é
    # relaxar invariante (CLAUDE.md §2), e o `POST /config` a soltava no mesmo dia com um
    # `{"trava_dia_em": ""}`. Quem escreve nela é só `guarda_risco()` (trava) e o `/reset`.
    "telegram_token":       ("texto", 200),
    "telegram_chat_id":     ("texto", 64),
}

# ---------- [Q-3] o racional por parâmetro de risco ----------
# O catálogo acima diz o que é ACEITÁVEL (tipo e faixa). Isto diz o que foi ESCOLHIDO, e por
# quê — que é a metade que faltava e a razão de o [Q-3] existir.
#
# O card nasceu de uma contradição: a `BASE-CONHECIMENTO-TRADING.md`, escrita com as nossas
# próprias medições, conclui 0,5-1% de risco e alavancagem ≤2x, e o que está vivo é 3% e
# 10x/20x. A contradição não é o defeito — é decisão do dono, com o motivo dele: a meta é o
# bot preparado para a semana de ganho grande (`PLANO-V2` Parte 0, 29/08), e 3%/10x é o
# perfil que ele escolheu para ela. O defeito era não estar escrito em lugar nenhum que a
# escolha foi deliberada, qual seria o perfil conservador equivalente, e o que muda quando
# isto encostar em dinheiro real.
#
# [F-20] Até 2026-09-24 este bloco e os verbetes abaixo diziam que a agressividade existia
# para ACELERAR um experimento de ver o "no edge" acontecer. Era a direção antiga, que o dono
# desautorizou em 26/08 (`NORTE.md`): um racional de risco que descreve um objetivo que o
# projeto não tem mais é o rótulo mentindo sobre o dial. Os números não mudaram — o porquê sim.
#
# [EX-1] Racional das chaves de execucao, para o `GET /catalogo`:
#   exec_modo       -- "mercado" e o de hoje: o sinal vira posicao na hora, pagando taker nas
#                      duas pernas. "post_only" faz o sinal virar uma ORDEM que descansa a
#                      `exec_maker_off` do preco e so vira posicao se o preco vier ate ela; se
#                      nao vier em `exec_ordem_ttl_s`, a ordem morre E O SINAL MORRE COM ELA.
#                      Medido: o [CX-1] leva o Sharpe de 0,955 para ~1,25 e faz o Reality Check
#                      passar; o [CX-3] mostrou que o atalho (esperar e mandar a mercado) nao
#                      vale nada, porque o ganho e a TAXA e nao o preco.
#   taxa_maker      -- cobrada so na perna de ENTRADA. A saida continua em `taxa_por_lado`
#                      (taker), porque stop e trailing sao ordem a mercado por natureza [CX-4].
#   exec_maker_off  -- o [CX-1] mediu 0,05%, 0,10% e 0,20% praticamente iguais. Fundo demais
#                      derruba o fill sem pagar de volta.
#   exec_ordem_ttl_s-- 3600 = a janela de 1h que o backtest mediu. Mudar isto muda o que a
#                      medicao quer dizer.
#
# Formato: texto por chave, servido pelo `GET /catalogo`. Chave sem racional aqui é chave sem
# decisão registrada — e o `None` no catálogo diz isso em vez de inventar uma justificativa.
CONFIG_RACIONAL = {
    "risco_por_trade": (
        "VIVO 3%. A base (§5, linhas 178-182) põe 0,5-1% como conservador, 1-2% moderado e "
        "chama >3% de território de ruína em sequência de perdas. MANTIDO em 3% por decisão "
        "do dono, e pelo motivo dele: a meta é o bot preparado para aproveitar a semana de "
        "ganho grande, não 15-30%/ano (PLANO-V2 Parte 0). O custo fica escrito ao lado: o "
        "[F-16] calculou 3% como ~2,8× Kelly sobre o edge estimado, e acima de 2× o "
        "crescimento esperado é negativo mesmo com edge real. Enquanto não existir medidor "
        "que distinga a oportunidade boa da ruim (N-10b), 3% é aposta UNIFORME, não "
        "proporcional à evidência. O que torna o número defensável são as três guardas em "
        "volta: trava diária sticky, teto de risco aberto e dinheiro fictício. Tire qualquer "
        "uma e 3% deixa de ser defensável. No perfil `conservador`: 1%."),
    "alavancagem_padrao": (
        "VIVO 10x. A base (§5.4, linha 281) mede o imposto da volatilidade: a mesma "
        "estratégia de +0,1%/dia com vol 2% rende +0,08%/dia a 1x e −1,9%/dia a 10x — "
        "'a 10x a mesma estratégia vira ruína', e o nosso próprio backtest registrou que "
        "'2x sempre pior que 1x'. Essas medições são de NOCIONAL fixo; aqui o tamanho sai do "
        "risco (`autotrader._tamanho`): o nocional é risco/distância-do-stop e, fora dos "
        "tetos de margem, não depende da alavancagem — então 10x decide quanta margem a posição prende e onde fica a "
        "liquidação (~9% adversos), não quanto se perde no stop. MANTIDO por decisão do "
        "dono, pelo mesmo motivo do risco_por_trade. Vale para o fluxo manual e para o modo "
        "`auto_lev_modo=fixo`. No `conservador`: 2x."),
    "auto_lev_modo": (
        "VIVO \"fixo\" desde 2026-08-29 ([N-10]), e o motivo é MEDIÇÃO, não prudência. Em "
        "\"conviccao\" a alavancagem escalava com o score: 60 pontos mapeavam em `auto_lev_min` "
        "e 99 em `auto_lev_max`, ou seja 20 pontos viravam 5,5× mais dinheiro em risco. O "
        "[Q-13] testou essa premissa em 2.945 sinais de tendência com desfecho marcado e ela "
        "não se sustenta: os que bateram no STOP tinham convicção MÉDIA MAIOR (67,10 contra "
        "66,47 dos que bateram no alvo), e o win% por faixa faz 63 → 38 → 45 → 50 → 47 — "
        "serrilha, não escada. A faixa 80-90, que a escala premiava com ~12x, é a PIOR das "
        "cinco. Desligar isto é REALOCAR risco, não reduzi-lo: o dinheiro espalhado sobre "
        "sinais que a medição não distingue entre si é o que falta quando aparecer a "
        "oportunidade que merece 20x (NORTE.md, PLANO-V2 Parte 0). O mecanismo continua "
        "INTEIRO em `autotrader._alavancagem`, dormindo e travado por teste — o `N-10b` está "
        "encarregado de construir um medidor que passe no teste do [Q-13] (win% monotônico "
        "por faixa, em amostra FORA da usada para construí-lo), e no dia em que passar a "
        "escala volta por config, sem reimplementar nada. Fora do perfil `conservador` de "
        "propósito: lá `auto_lev_min`=1 e \"fixo\" usaria `alavancagem_padrao`=2x sempre, o "
        "que SUBIRIA o piso — ver o comentário do `db.PERFIS_RISCO`."),
    "auto_lev_min": (
        "VIVO 2x — o piso da escala por convicção, aplicado na convicção mínima. Não é "
        "garantia de risco e nunca foi: o cap geométrico do [P1-11] desce ABAIXO dele quando "
        "a geometria stop/liquidação exige. No `conservador`: 1x, que é o único perfil que a "
        "base diz ter sobrevivido (§6.1, linha 313: 'trend-following SEM alavancagem')."),
    "auto_lev_max": (
        "VIVO 20x, e é o parâmetro mais delicado dos quatro. A base (§6.4, linha 336) põe o "
        "teto em '1/4 a 1/2 Kelly, nunca acima'. Há um segundo argumento, que o card não "
        "tinha e a onda 1 mediu: a aproximação de liquidação do simulador (`0,9/lev`) é "
        "CONSERVADORA até ~20x e vira OTIMISTA acima — o cruzamento é 20x com mmr 0,5% e 25x "
        "com mmr 0,4% (ARQUITETURA.md §10a). O teto vivo está exatamente em cima da fronteira "
        "em que o paper deixa de ser pessimista, então SUBIR daqui não é só mais risco: é "
        "risco medido por um modelo que passa a errar a favor. Argumento para não subir, "
        "independente do perfil. No `conservador`: 2x."),
    "risco_aberto_max": (
        "VIVO 10% do equity do início do dia, somando o risco-até-o-stop das posições "
        "abertas. É ELE quem manda sobre `auto_max_posicoes` — `simulador.abrir` recusa "
        "quando `risco_ab + r_novo > teto` (simulador.py:185). Com 3% por trade isso significa "
        "que a quarta posição é recusada, e os 5 slots configurados nunca são alcançados. A "
        "tensão '5 × 3% = 15% contra um teto de 10%' se resolve assim: o teto vence, e o "
        "excedente vira config morta em vez de risco. No `conservador` o teto cai para 5% e "
        "passa a caber exatamente 5 × 1%."),
    "auto_max_posicoes": (
        "VIVO 5 slots. Sob o perfil `experimento` este número é INALCANÇÁVEL — o teto de "
        "risco aberto barra na quarta posição (ver `risco_aberto_max`). Fica registrado como "
        "config morta em vez de silenciosamente ajustado: mudá-lo para 3 daria a impressão de "
        "que o slot é a guarda, quando a guarda é o teto agregado. Sob o `conservador` ele "
        "volta a valer, e os dois números concordam por construção."),
    "limite_perda_dia": (
        "VIVO 5% do equity do início do dia, sticky (não solta no mesmo dia). Não é um dos "
        "parâmetros que a base contradiz, mas ele é quem decide quanto tempo um perfil "
        "agressivo sobrevive: a 3% por trade, menos de dois stops cheios trancam o dia; a 1%, "
        "cinco. O mesmo 5% significa coisas diferentes em cada perfil, e por isso ele fica "
        "FORA dos perfis — mexer nele é mexer no freio de emergência, não no acelerador."),
    "trailing_unidade": (
        "VIVO \"R\". 1R é a distância entrada→stop DA ABERTURA (`posicoes.stop_abertura`, "
        "imutável), que é a mesma unidade em que o stop de entrada já é dimensionado (3×ATR). "
        "Substituiu \"preco\" (os 2% de `trailing_dist`) porque a unidade de preço estava "
        "errada de duas maneiras opostas ao mesmo tempo. Primeira: multiplicada pela "
        "alavancagem ela vira ROE — 2% de preço são 4% de ROE a 2x e 40% a 20x, então o "
        "trailing DESARMAVA justamente onde a aposta era maior. Segunda: em unidade de risco "
        "os mesmos 2% valem 3R com stop curto (arma tarde demais) e meio R com stop largo "
        "(arma cedo demais) — o mesmo número significava coisas diferentes a cada trade. A "
        "medição que fecha o argumento: 19 dos 20 trades que foram de lucro a prejuízo NUNCA "
        "armaram o trailing (INVESTIGACAO-MOTOR-2026-08-24 §8), e essa cauda direita é "
        "exatamente o que a meta do dono pede. \"preco\" NÃO é legado morto: é o caminho das "
        "posições abertas antes de `stop_abertura` existir, que não têm R mensurável — para "
        "elas, inventar um R a partir do stop de agora seria o defeito [F-1] renascendo."),
    "trailing_arma_r": (
        "VIVO 3R desde 2026-09-09, decisão do dono (registrada em `config_auditoria`). Lucro, "
        "em R, que ARMA o trailing. Com `trailing_dist_r` também em 3, o stop cai no "
        "zero-a-zero EXATO no instante em que arma. A D-5 (29/08) tinha assinado 1R/1R; a "
        "autópsia da saída de 07/09 mediu, sobre 5.147 sinais do próprio vivo, que 1R/1R "
        "cortava a cauda direita — alargar para 3R/3R rendeu +0,101R por sinal, positivo em 7 "
        "de 8 recortes, com o acerto caindo de 45% para 31% e o maior trade subindo de +7,9R "
        "para +22,7R: convexidade, que é a meta. ⚠️ Não DESLIGUE o trailing para deixar "
        "correr: `trailing_ativo=0` liga o `auto_fechar_saida`, que realiza em `alvo_roe` "
        "(~0,6R) — um cortador mais apertado. Só vale com `trailing_unidade=R`; sob \"preco\" "
        "quem manda é `trailing_dist`."),
    "trailing_dist_r": (
        "VIVO 3R (09/09, mesma decisão). Distância, em R, que o stop mantém atrás do preço "
        "depois de armado. Vale a pena saber ler a relação com `trailing_arma_r`: no instante "
        "em que arma, o stop vai para `entrada + (arma_r − dist_r)×R`, então dist_r > arma_r "
        "arma ABAIXO da entrada e dist_r < arma_r já arma travando lucro. Nenhum dos dois é "
        "afrouxamento — a catraca de `simulador._marcar_uma` só aceita stop que ande a favor, "
        "nunca para trás. Apertar (dist_r menor) trava mais cedo e corta mais vencedor; "
        "afrouxar dá mais corda à cauda direita. Só vale com `trailing_unidade=R`."),
    "exposicao_max": (
        "VIVO 50% da banca em margem somada. Teto de MARGEM, não de risco: limita quanto "
        "capital fica preso, não quanto se pode perder. A base não fala dele, mas ele muda de "
        "papel entre os perfis, e isso foi MEDIDO: sob `experimento` quem barra primeiro é "
        "sempre o `risco_aberto_max`; sob `conservador`, alavancagem baixa exige mais margem "
        "para o mesmo risco (1% com stop de 2% a 2x pede 25% da banca por posição) e a "
        "margem passa a barrar na TERCEIRA — antes do teto de risco e antes dos slots. O "
        "perfil conservador só entrega os 5 slots com stops largos. Subir este teto no perfil "
        "resolveria a aritmética AFROUXANDO uma guarda, o que é decisão do dono; fica medido "
        "em `tests/test_config.py` em vez de resolvido por conta própria."),
    "auto_rajada_max": (
        "VIVO 0 = DESLIGADO. Com N > 0, o bot abre no máximo N entradas do MESMO lado dentro "
        "de `auto_rajada_janela_min` minutos; a vaga barrada vai para o próximo candidato e o "
        "sinal barrado não é consumido. Nasceu de 17/11: quatro SHORTs de rompimento em 14 "
        "minutos, na vela que fez a mínima da manhã, três stops e a trava do dia antes das 9h "
        "-- a mesma informação contada quatro vezes, que nenhum teto via porque todos contam "
        "vaga ou risco e nenhum conta QUANDO. ⚠️ NÃO FOI MEDIDO: é hipótese de um dia ruim, e "
        "o histórico real de 02 a 15/11 não aponta um lado (entradas em bloco: +3,5R em 4 na "
        "conta A, −2,1R em 2 na B). Não é o teto por direção, que o T12 e o histórico de setembro "
        "reprovaram por cortar o dia de tendência: aquele limita posição aberta, este limita "
        "ritmo, e passada a janela o lado abre de novo. Ligar é apertar, não afrouxar -- mas "
        "apertar sem medida também custa, e o lugar de ligar primeiro é uma conta de teste."),
    "auto_rajada_janela_min": (
        "VIVO 30 minutos; só vale com `auto_rajada_max` > 0. Maior que `auto_freshness_min` "
        "(12) de propósito: um sinal barrado por entradas da mesma vela de 15m envelhece antes "
        "de a janela abrir, então barrar não vira entrar atrasado no mesmo movimento. Baixar "
        "para perto de 12 transforma o teto em atraso."),
    "auto_agitacao_corte": (
        "VIVO 0 = DESLIGADO. Com corte > 0, o sinal de tendência cujo `atr_rel` (ATR do sinal "
        "dividido pela mediana dos até 200 sinais anteriores do mesmo ativo e gráfico) é >= "
        "corte abre com `risco_por_trade` x `auto_agitacao_frac`. O valor medido é 1,18: o "
        "terço mais agitado dos trades da regra de produção. MEDIDO em 18/11 em duas janelas: "
        "esse terço rendeu −0,14R por trade em 2023-26 e −0,11R em 2020-22, contra +0,23R e "
        "+0,06R do terço calmo (diferença com IC de 95% fora do zero nas duas, mesmo sentido em "
        "6 de 7 anos). ⚠️ Ressalvas: 2026 foi o ano que inverteu; é a mesma família do medidor "
        "M1/ATR% que passou no lacrado em 02/11, nas mesmas janelas, então concorda com ele e "
        "não é prova nova; é R por trade, e na carteira o T28 não separou tamanho por ATR% do "
        "ruído. NÃO é proteção de dia lateral: nos 10% piores dias corta ~20% da perda, e em "
        "17/11 os três SHORTs stopados estavam calmos. Sem 30 sinais anteriores do ativo no "
        "banco o sinal não tem `atr_rel` e abre inteiro. Ligar é apertar; o lugar de ligar "
        "primeiro é uma conta de teste, depois de ler `sinais.atr_rel` contra o desfecho."),
    "auto_agitacao_frac": (
        "VIVO 0,5 (meio tamanho); só vale com `auto_agitacao_corte` > 0. É a fração do risco no "
        "sinal agitado, e foi com 0,5 que a conta de 18/11 foi feita: a soma de R foi de +2.247 "
        "para +2.820 em 2023-26 e de −4.304 para −2.008 em 2020-22, com 23% e 29% dos 5% "
        "melhores trades no terço reduzido. 1 = não reduz. Abaixo de 0,5 não foi medido."),
    "auto_esticado_modo": (
        "VIVO off. Vale só para SHORT de tendência quando o diário do ativo já caiu: retorno dos "
        "últimos 7 dias FECHADOS <= `auto_esticado_ret7` (−10%). `meio` abre com metade do "
        "`risco_por_trade`; `veto` não vende, e o sinal segue 'novo' com a vaga indo para o "
        "próximo candidato. MEDIDO em 19/11 (T54) nos trades da regra de produção: esse SHORT "
        "rendeu −0,344R por trade em 2023-26 (IC [−0,597; −0,060]) e −0,395R em 2020-22 "
        "([−0,622; −0,178]); o LONG esticado para cima não é pior, por isso a regra só olha a "
        "venda. ⚠️ O outro lado: ao vivo, de 02/11 a 18/11, esses mesmos SHORTs renderam "
        "+20,7R na conta A e +7,2R na B (−4,7R na C), e em 2026 o histórico fica perto de zero "
        "(−0,04R). `veto` teria tirado o lucro de novembro; `meio` paga metade nos dois "
        "cenários. Diário fora do ar com a chave ligada: o sinal é pulado no ciclo. Moeda com "
        "menos de 8 dias de diário abre inteira. Reversão fica de fora (não foi medida)."),
    "auto_esticado_ret7": (
        "VIVO −10 (%); só vale com `auto_esticado_modo` ligado. É o corte que o T54 fixou antes "
        "de rodar (junto com RSI diário < 30, que deu o mesmo sentido). Outros cortes não foram "
        "medidos: mexer aqui é escolher sem régua."),
    "tp_so_intactos": (
        "1 = os alvos de TP só usam topos e fundos que nenhum fechamento posterior atravessou "
        "(1h e 4h; Fibonacci não muda). 0 = como era: todo pivô conta, e no T58 (19/11) 73% "
        "deles já tinham sido rompidos -- alvo mirado num nível que já não segurou nada. O "
        "replay T64 mediu o efeito no TP1 antes de ligar. Só vale para posição aberta depois "
        "da mudança: o plano de TP é calculado uma vez, na abertura."),
}


_VERDADEIRO = {"1", "true", "sim", "on", "yes"}
_FALSO = {"0", "false", "nao", "não", "off", "no"}
_RE_PAR = re.compile(r"^[A-Z0-9]{2,15}/[A-Z]{2,6}$")
_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validar_config(chave, valor):
    """Coage e valida UM par chave/valor. Devolve a string a gravar ou levanta ValueError
    com o motivo — a mensagem é o produto: quem apanhou do 422 precisa saber o que corrigir."""
    if chave not in CONFIG_CATALOGO:
        raise ValueError(f"'{chave}': chave desconhecida")
    spec = CONFIG_CATALOGO[chave]
    tipo = spec[0]
    bruto = str(valor).strip() if valor is not None else ""

    if tipo in ("float", "int"):
        _, lo, hi = spec
        try:
            n = float(bruto.replace(",", "."))
        except ValueError:
            raise ValueError(f"'{chave}': '{valor}' não é número")
        if not (lo <= n <= hi):        # nan/inf caem aqui: nenhuma comparação com nan é True
            raise ValueError(f"'{chave}': {bruto} fora da faixa permitida [{lo}, {hi}]")
        if tipo == "int":
            if n != int(n):
                raise ValueError(f"'{chave}': {bruto} precisa ser inteiro")
            return str(int(n))
        return str(n)

    if tipo == "bool":
        v = bruto.lower()
        if v in _VERDADEIRO:
            return "1"
        if v in _FALSO:
            return "0"
        raise ValueError(f"'{chave}': '{valor}' não é 0/1")

    if tipo == "enum":
        if bruto not in spec[1]:
            raise ValueError(f"'{chave}': '{valor}' não é uma opção válida {list(spec[1])}")
        return bruto

    if tipo == "lista_tf":
        itens = [t.strip() for t in bruto.split(",") if t.strip()]
        if not 1 <= len(itens) <= 6:
            raise ValueError(f"'{chave}': informe de 1 a 6 timeframes")
        for t in itens:
            if t not in _TFS:
                raise ValueError(f"'{chave}': timeframe '{t}' inválido {list(_TFS)}")
        return ",".join(itens)

    if tipo == "pares":
        # teto de 60 pares: o scan é ativos × timeframes chamadas de rede por ciclo — uma
        # lista gigante não é erro de tipo, é o worker estourando o tempo do ciclo.
        itens = [a.strip().upper() for a in bruto.split(",") if a.strip()]
        if not 1 <= len(itens) <= 60:
            raise ValueError(f"'{chave}': informe de 1 a 60 pares")
        for a in itens:
            if not _RE_PAR.match(a):
                raise ValueError(f"'{chave}': par '{a}' fora do formato BASE/QUOTE")
        return ",".join(itens)

    if tipo == "lista_num":
        _, piso, teto, max_itens = spec
        itens = [x.strip() for x in bruto.split(",") if x.strip()]
        if not 1 <= len(itens) <= max_itens:
            raise ValueError(f"'{chave}': informe de 1 a {max_itens} números separados por vírgula")
        nums = []
        for x in itens:
            try:
                n = float(x)
            except ValueError:
                raise ValueError(f"'{chave}': '{x}' não é número")
            if not (piso < n <= teto):     # piso EXCLUSIVO; nan/inf caem aqui, como no float
                raise ValueError(f"'{chave}': {x} fora da faixa permitida ({piso}, {teto}]")
            nums.append(n)
        return ",".join(str(int(n)) if n == int(n) else repr(n) for n in nums)

    if tipo == "data":
        if bruto and not _RE_DATA.match(bruto):
            raise ValueError(f"'{chave}': '{valor}' não é uma data AAAA-MM-DD (ou vazio)")
        return bruto

    if len(bruto) > spec[1]:                                 # texto
        raise ValueError(f"'{chave}': passa de {spec[1]} caracteres")
    return bruto


# Chaves cujo VALOR não sai em resposta nenhuma. O `/estado` devolvia a config inteira a cada
# poll de 3 s, com o `telegram_token` dentro; o `GET /config` e a auditoria também. Quem tem o
# token manda mensagem em nome do bot. A tela nunca precisou do valor, só de saber se EXISTE
# ("configurado" / "não configurado"), e é isso que a máscara preserva: vazio continua vazio.
SEGREDOS = {"telegram_token"}
MASCARA = "••••••••"


def _config_publica(cfg):
    """A config como ela pode sair pela API: segredo preenchido vira máscara."""
    return {k: (MASCARA if k in SEGREDOS and v else v) for k, v in cfg.items()}


def _sem_mascara(body):
    """Tira do corpo o segredo que voltou como máscara: um cliente que reenvia o formulário
    inteiro devolveria a máscara, e gravá-la apagaria o token de verdade."""
    if not isinstance(body, dict):
        return body
    return {k: v for k, v in body.items() if not (k in SEGREDOS and v == MASCARA)}


def _validar_lote(body, permitidas=None):
    """Valida o corpo INTEIRO antes de gravar qualquer coisa. Tudo-ou-nada de propósito:
    meia configuração aplicada (parte nova, parte velha) é um estado que ninguém pediu e
    que o operador não consegue nomear pra desfazer."""
    if not isinstance(body, dict) or not body:
        raise HTTPException(422, "corpo precisa ser um objeto {chave: valor} não vazio")
    recusados, aceitos = [], {}
    for k, v in body.items():
        if permitidas is not None and k not in permitidas:
            recusados.append(f"'{k}': não é ajustável por este endpoint")
            continue
        try:
            aceitos[k] = _validar_config(k, v)
        except ValueError as e:
            recusados.append(str(e))
    if not recusados:
        recusados = _validar_cruzado(aceitos)
    if recusados:
        log(f"config recusada: {recusados}", "error")
        raise HTTPException(422, {"erro": "configuração recusada — nada foi gravado",
                                  "recusados": recusados})
    return aceitos


def _validar_cruzado(aceitos):
    """Regras entre DUAS chaves, que a validação chave a chave não enxerga.

    Hoje uma só: `auto_lev_min` não pode passar de `auto_lev_max`. Cada uma cabia na sua faixa
    (1 a 50) e a dupla invertida entrava; em `autotrader._alavancagem` o piso vence o teto de
    propósito (`tests/test_sizing.py` trava isso, para o erro não virar 1x calado), então o
    "TETO de alavancagem" do painel deixava de ser teto. Recusar aqui fecha o caso sem mexer
    naquela decisão. O valor que não veio no corpo é o que está gravado."""
    if not {"auto_lev_min", "auto_lev_max"} & aceitos.keys():
        return []
    try:
        vigente = db.get_config()
    except Exception:                       # sem banco não há par para cruzar
        vigente = {}
    try:
        piso = float(aceitos.get("auto_lev_min", vigente.get("auto_lev_min")))
        teto = float(aceitos.get("auto_lev_max", vigente.get("auto_lev_max")))
    except (TypeError, ValueError):
        return []
    if piso > teto:
        return [f"'auto_lev_min' ({piso:g}) não pode ser maior que 'auto_lev_max' ({teto:g})"]
    return []


# ---------- modelos ----------
# Id acima do INTEGER do SQLite estourava OverflowError dentro do driver e virava 500 em quatro
# rotas. Fora da faixa é 422, com o motivo.
ID_MAX = 2 ** 63 - 1


class ConfirmarReq(BaseModel):
    sinal_id: int = Field(ge=1, le=ID_MAX)
    valor_reais: float
    # None = "a da config". Era `= 10.0`: um /confirmar sem o campo abria a 10x cravado, fosse
    # qual fosse o `alavancagem_padrao` (CLAUDE.md §1: nunca constante literal no módulo).
    alavancagem: Optional[float] = None


class IdReq(BaseModel):
    id: int = Field(ge=1, le=ID_MAX)


class DcaReq(BaseModel):
    ativo: str
    valor_aporte: float
    freq_dias: float = 7


class ResetReq(BaseModel):
    confirmar: str = ""
    incluir_dca: bool = False       # ver o contrato do /reset


# ---------- leitura ----------
@app.get("/")
def home():
    return FileResponse(os.path.join(WEB, "index.html"))


WEB = os.path.join(os.path.dirname(__file__), "web")
_VENDOR = os.path.join(WEB, "vendor")
if os.path.isdir(_VENDOR):
    app.mount("/vendor", StaticFiles(directory=_VENDOR), name="vendor")
else:
    # StaticFiles levanta RuntimeError em diretório ausente e derrubaria o processo inteiro.
    # Sem as libs o gráfico não renderiza, mas API, worker e risco seguem de pé.
    log(f"AVISO: {_VENDOR} não existe — /vendor não montado (gráficos não vão carregar)", "error")
# Front Apollux: casca e views em web/app/ (index.html carrega app/*.js por caminho relativo).
_APP = os.path.join(WEB, "app")
if os.path.isdir(_APP):
    app.mount("/app", StaticFiles(directory=_APP), name="app")
else:
    log(f"AVISO: {_APP} não existe — /app não montado (o painel não vai carregar)", "error")


@app.get("/config.js")
def config_js():
    # O `web/config.js` versionado é o do Vercel e aponta para o backend de PRODUÇÃO. Servi-lo
    # daqui fazia o painel aberto em http://localhost:8000 falar com a produção (com `/reset` e
    # `/panico` a um clique), nunca com este processo. Quando é o backend que entrega o front, o
    # front fala com ele: base vazia = mesma origem, que é o que o próprio arquivo documenta.
    return Response('window.API_BASE = "";\n', media_type="application/javascript",
                    headers={"Cache-Control": "no-store"})


def _commit_em_producao(raiz=None):
    """[P2-3] Hash do commit que ESTE processo está rodando.

    A VM não é repositório git e o deploy é cópia manual, então "commit na main" nunca
    significou "código rodando" — não havia como responder *qual* código está na VM sem
    comparar md5 de arquivo a arquivo. Publicar o hash no /health é o que transforma isso
    numa pergunta com resposta.

    Ordem: `COMMIT_SHA` do ambiente (o deploy pode injetá-lo onde não há git) → `git
    rev-parse` → **None**. None DECLARADO, nunca `"desconhecido"` ou `"dev"`: string
    inventada responde à pergunta com algo que parece resposta, e a checagem de deploy
    passaria a comparar com um valor que nunca foi um commit. É o portão do M2, o mesmo
    princípio que o [P2-10] acabou de aplicar ao funding não medido.

    `raiz` existe para a prova conseguir apontar para um diretório sem git."""
    sha = (os.environ.get("COMMIT_SHA") or "").strip()
    if sha:
        return sha
    try:
        r = subprocess.run(["git", "-C", raiz or os.path.dirname(os.path.abspath(__file__)),
                            "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:               # sem git instalado, sem repositório, timeout: tudo é None
        pass
    return None


# Lido UMA vez, no import. Nunca por requisição: /health é o endpoint de saúde e o único
# que responde sem autenticação — pôr um subprocesso no caminho dele seria dar a quem bate
# na porta um `fork` de graça. E o commit de um processo não muda enquanto ele vive.
COMMIT = _commit_em_producao()


def _estado_vigia(agora=None):
    """[vigia] (vivo, idade do último ciclo em s). Nos primeiros `VIGIA_CICLO_S` do processo
    conta como vivo mesmo sem ciclo: um restart de deploy não pode virar alarme."""
    agora = time.monotonic() if agora is None else agora
    ultimo = _vigia["ultimo"]
    idade = None if ultimo is None else round(agora - ultimo, 1)
    subindo = agora - _INICIO_MONO <= VIGIA_CICLO_S
    return (idade is not None and idade <= VIGIA_CICLO_S) or subindo, idade


def _repassar(conta, metodo, caminho, query, corpo, auth, ctype):
    """[AB-1] A requisição vai para a instância B como veio, e a resposta volta como veio.
    Erro HTTP da B (401, 422...) é devolvido com o status DELA: mascarar como 502 esconderia,
    por exemplo, uma config recusada pelo catálogo. [AB-2] `conta` diz qual instância."""
    # `caminho` chega DECODIFICADO: um espaço ou caractere de controle nele estourava InvalidURL
    # (que não é URLError) e a rota respondia 500. Recodificado, a B devolve o 404 dela.
    url = f"{_url_teste(conta)}/{quote(caminho, safe='/')}" + (f"?{query}" if query else "")
    cab = {k: v for k, v in (("Authorization", auth), ("Content-Type", ctype)) if v}
    req = urllib.request.Request(url, data=corpo if metodo == "POST" else None,
                                 headers=cab, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "application/json")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "text/plain")


def _repassar_b(metodo, caminho, query, corpo, auth, ctype):
    return _repassar("B", metodo, caminho, query, corpo, auth, ctype)


def _repassar_c(metodo, caminho, query, corpo, auth, ctype):
    return _repassar("C", metodo, caminho, query, corpo, auth, ctype)


async def _rota_teste(conta, repassar, caminho, request):
    # Só a A repassa. Na própria B a rota não existe, senão uma config errada de TESTEB_URL
    # faria a B chamar a si mesma em laço. [AB-2] Nem B repassa para C, nem C para B: uma conta
    # de teste alcançando a outra seria um caminho a mais para gravar na conta errada.
    if CONTA != "A":
        raise HTTPException(404, f"rota /teste{conta} só existe na conta A")
    corpo = await request.body()
    try:
        st, dados, ctype = await run_in_threadpool(
            repassar, request.method, caminho, request.url.query, corpo,
            request.headers.get("Authorization"), request.headers.get("Content-Type"))
    except (urllib.error.URLError, OSError) as e:
        return PlainTextResponse(f"Teste {conta} fora do ar: {e}", status_code=502)
    return Response(content=dados, status_code=st, media_type=ctype)


@app.api_route("/testeB/{caminho:path}", methods=["GET", "POST"])
async def teste_b(caminho: str, request: Request):
    return await _rota_teste("B", _repassar_b, caminho, request)


@app.api_route("/testeC/{caminho:path}", methods=["GET", "POST"])
async def teste_c(caminho: str, request: Request):
    return await _rota_teste("C", _repassar_c, caminho, request)


@app.get("/health")
def health():
    # [vigia] Público de propósito: é o que a vigia externa (`.github/workflows/vigia.yml`) lê
    # sem credencial. 503 quando o ciclo parou -- "o processo responde" deixou de bastar,
    # porque processo vivo com worker parado era exatamente o buraco. Não expõe nada além da
    # idade do ciclo: nem posição, nem banca, nem config.
    vivo, idade = _estado_vigia()
    corpo = {"status": "ok" if vivo else "ciclo parado", "versao": VERSAO, "commit": COMMIT,
             "ciclo_ha_s": idade, "conta": CONTA}
    return corpo if vivo else JSONResponse(corpo, status_code=503)


@app.get("/status")
def status():
    sc = signal_engine.ultimo_scan
    mk = simulador.ultima_marcacao
    # cego = o scan rodou e NENHUMA moeda respondeu (rede, geo-bloqueio, exchange fora).
    # Sem este sinal, o /status dizia "0 erros" com o bot sem enxergar o mercado.
    cego = sc["total"] > 0 and sc["ok"] == 0
    # cego nas POSIÇÕES: o ciclo tentou marcar e nenhuma foi marcada. É mais grave que o
    # scan cego — posição não marcada é posição sem stop, sem trailing e sem liquidação.
    cego_pos = mk["total"] > 0 and mk["ok"] == 0
    # [P2-10] o funding que NÃO foi medido já para de virar zero no banco — mas medição
    # ausente que ninguém vê é silêncio com outro nome. `funding_medicao` é cumulativo
    # (não zera por ciclo, ao contrário de `scan`): é a contagem da vida do processo, e é
    # por ela que se percebe um 451 que só afeta o endpoint de futuros. Publicado do mesmo
    # jeito que `scan` e `marcacao` — o dicionário inteiro, sob a sua chave.
    #
    # `saudavel` NÃO mudou: continua `not (cego or cego_pos)`. Falha de funding não cega o
    # bot (ele segue marcando e fechando posição), e transformá-la em critério de saúde
    # seria mexer no detector de cegueira, que é decisão do dono (CLAUDE.md §2).
    #
    # [P1-11] O cap geométrico da alavancagem (`autotrader._cap_geometrico`) só existia no
    # log e no resumo de UM ciclo — e o resumo de um ciclo é descartado pelo seguinte, então
    # ninguém conseguia responder "quantas vezes isso já agiu?". `CAPS_GEOMETRIA` é estado de
    # módulo, cumulativo na vida do processo, e sai aqui inteiro (`total` + `ultimo`), do
    # mesmo jeito que `scan`, `marcacao` e `funding`.
    #
    # Sai no `/status` e NÃO no `/estado` de propósito: o painel faz poll do `/estado` a cada
    # 3s e a franquia de saída da Azure é 15 GB/mês (CLAUDE.md §2) — o `/status` o front só
    # busca no portão de login (`web/index.html:909,951`). Contagem de guarda é diagnóstico,
    # não telemetria de tempo real.
    #
    # `saudavel` também não olha isto: o cap agindo é a guarda FUNCIONANDO. Um bot que capa
    # 100% dos trades está saudável e mal configurado, que são coisas diferentes — quem lê
    # `total` alto contra `ciclos` decide, e a decisão é do dono.
    return {**_health, "worker_on": _worker_on["v"], "scan": sc, "marcacao": mk,
            "funding": simulador.funding_medicao,
            "caps_geometria": autotrader.CAPS_GEOMETRIA,
            # [P2-39] o teto de TAMANHO, ao lado do teto de ALAVANCAGEM. Os dois capam, e
            # capavam — só que este capava calado. Publicado do mesmo jeito e pela mesma
            # razão: quem lê `total` alto contra `ciclos` decide, e a decisão é do dono.
            "caps_tamanho": autotrader.CAPS_TAMANHO,
            "saudavel": not (cego or cego_pos),
            "posicoes_abertas": len(db.listar("posicoes", 100, "WHERE status='aberta'"))}


@app.post("/reset")
def reset(req: ResetReq):
    """Devolve a simulação ao estado inicial. CONTRATO COMPLETO do que o reset toca:

    APAGA     sinais, posições, trades e a curva de equity.
    RESTAURA  a banca para o valor inicial.
    LIMPA     `trava_dia_em` — a trava diária é sticky por design (não destrava no mesmo
              dia), então sem isto o sistema "novo" nascia travado até a virada do dia,
              com banca cheia e zero trades. Estado impossível de diagnosticar pelo painel.
    PRESERVA  a configuração (risco, alavancagem, ativos, auto_trade) — reset é da
              SIMULAÇÃO, não dos parâmetros do experimento.
    PRESERVA  os planos de DCA e seu acumulado, salvo `{"incluir_dca": true}`. O DCA é
              acumulação de longo prazo com banca conceitualmente separada: zerá-lo junto
              com um reset de trade ativo apaga meses de aporte por um clique que a pessoa
              acha que só limpa a mesa. Fica opt-in explícito.

    Irreversível e sem backup do trading.db ([P2-2]): exige `{"confirmar": "RESET"}` para
    que um POST solto — curl, scanner, clique errado — não apague o histórico de pesquisa."""
    if req.confirmar != "RESET":
        raise HTTPException(400, 'Reset apaga todo o histórico. Envie {"confirmar": "RESET"}.')
    tabelas = ["sinais", "posicoes", "trades", "equity"]
    if req.incluir_dca:
        tabelas.append("dca")
    with db.conectar() as c:                    # tudo numa transação só: reset pela metade
        for t in tabelas:                       # é pior que reset nenhum
            c.execute(f"DELETE FROM {t}")
        c.execute("UPDATE banca SET atual=inicial WHERE id=1")
        # [EX-1] A ordem pendente sobrevivia ao reset e enchia na conta zerada, apontando para um
        # sinal que acabou de ser apagado. Na mesma transação: reset pela metade é pior que nenhum.
        _cancelar_ordens("reset", c)
        # [F-15] O reset e o UNICO escritor de config que nao passa pelo `db.set_config`, e
        # continua nao passando: a limpeza da trava tem de cair na MESMA transacao dos DELETEs
        # (reset pela metade e pior que reset nenhum), e `set_config` abre a sua propria. Entao
        # ele chama a auditoria a mao, com a conexao que ja tem. Sem esta linha, o unico caminho
        # que solta a trava diaria seria tambem o unico invisivel na auditoria -- e a trava e
        # justamente uma das guardas cujo afrouxamento o CLAUDE.md §2 manda registrar.
        db._auditar_config(c, "trava_dia_em", "", "POST /reset")
        c.execute("INSERT INTO config(chave,valor) VALUES('trava_dia_em','') "
                  "ON CONFLICT(chave) DO UPDATE SET valor=''")
    # estado derivado em memória: sem isto o painel exibe, até o próximo ciclo (15s),
    # recomendações de saída e um contador de marcação de posições que não existem mais.
    _saidas.update(v=[], t=None)
    _auto["v"] = {"ativo": False}
    simulador.ultima_marcacao.update(ts=None, total=0, ok=0, falhas=0, ultimo_erro=None)
    return {"ok": True, "trava_dia_limpa": True, "dca_apagado": req.incluir_dca}


def _amostrar(seq, alvo=125):
    """Reduz a série para ~alvo pontos, preservando o intervalo e o ponto mais recente.
    A curva de equity é reenviada inteira a cada poll de 3s e sozinha era 72% do payload
    (51 KB de 71 KB). Com franquia de saída de 15 GB/mês na Azure, isso importa.

    [P1-4] Passo FRACIONÁRIO. Era `passo = len(seq) // alvo` + `seq[::passo]`: divisão
    inteira, então qualquer len entre `alvo` e `2*alvo - 1` dava passo=1 e a série voltava
    INTEIRA — a função não reduzia nada justamente na faixa em que ela começa a ser
    necessária, e a economia só ligava no dobro do alvo (medido: 200 -> 200, 249 -> 249).
    Indexar por `round(i * n / alvo)` faz o passo médio ser n/alvo mesmo quando ele é
    fracionário. O `| {n - 1}` garante o ponto mais recente, que é o requisito original."""
    n = len(seq)
    if n <= alvo:
        return seq
    idx = sorted({min(round(i * n / alvo), n - 1) for i in range(alvo)} | {n - 1})
    return [seq[i] for i in idx]


def _amostrar_tempo(serie, alvo=125):
    """Reduz a curva de equity a ~alvo pontos igualmente espaçados no TEMPO.

    O `_amostrar` acima é uniforme em POSIÇÃO, e a série não é uniforme no tempo: a poda
    do [P2-11] guarda 15 s nas últimas 48 h e 5 min antes. Com 11 dias de banca, ~80% das
    linhas estão nos 2 últimos dias, então ~100 dos 125 pontos caíam ali e os 9 dias
    anteriores ficavam com 1 ponto a cada ~10 h. O gráfico escondia os vales desses dias, o
    "DD atual" do painel media o pico numa curva sem os picos, e o P&L do mês pela curva
    pegava um ponto "antes do dia 1" que podia ser de horas antes (o painel documenta esse
    erro, de R$ 80).

    Um balde por fatia de tempo e, de cada balde, o ÚLTIMO ponto (o critério da poda: o
    último ponto da janela é o valor daquele instante). O primeiro e o último ponto da série
    entram sempre. Mesmo teto do `_amostrar` (franquia de saída, CLAUDE.md §2) e mesmo
    formato: o front não precisa mudar por causa disto. A versão-sintoma seria subir o
    `alvo` até o passado ficar visível — pagando em franquia o que é erro de amostragem.
    Se algum `ts` não parsear, devolve o `_amostrar`: pior, mas não errado.
    """
    n = len(serie)
    if n <= alvo:
        return serie
    try:
        t = [datetime.fromisoformat(str(p["ts"])[:19]).timestamp() for p in serie]
    except (ValueError, KeyError, TypeError):
        return _amostrar(serie, alvo)
    t0, span = t[0], t[-1] - t[0]
    if span <= 0:
        return _amostrar(serie, alvo)
    ultimo = {}
    for i, ti in enumerate(t):                     # em ordem: o último índice de cada balde vence
        ultimo[min(alvo - 2, max(0, int((ti - t0) / span * (alvo - 1))))] = i
    idx = sorted(set(ultimo.values()) | {0, n - 1})
    return [serie[i] for i in idx]


@app.get("/estado")
def estado():
    """Tudo que a UI precisa num request só."""
    cfg = db.get_config()
    return {
        "banca": db.get_banca(),
        "equity_total": round(equity_total(), 2),
        "config": _config_publica(cfg),
        # [Q-3] o nome do perfil de risco vigente ('experimento'|'conservador'|
        # 'personalizado'), DERIVADO da config acima — não é chave no banco (db.perfil_ativo).
        # Vem no /estado, e não no /status, apesar do poll de 3s: é uma string curta (~25 B),
        # e o painel repinta a config a cada poll, então no /status ela congelaria no valor do
        # login e um badge de risco desatualizado é pior que badge nenhum. O `cfg` acima é
        # reusado de propósito: zero consulta a mais.
        "perfil_risco": db.perfil_ativo(cfg),
        "pendentes": db.listar("sinais", 30, "WHERE status='novo'"),
        "posicoes": db.listar("posicoes", 50, "WHERE status='aberta'"),
        "trades": db.listar("trades", 30),
        # [P2-11] a série INTEIRA (a poda a mantém pequena), reduzida a ~125 pontos pelo
        # _amostrar. Era `listar("equity", 500)[::-1]`: 500 linhas de 15s = 125 minutos, ou
        # seja o "gráfico da banca" mostrava ~2h e nunca a trajetória — que é a única
        # leitura que ele existe para dar. O formato do payload não muda (ts/banca/
        # equity_total, em ordem cronológica), então o front não muda junto.
        # Amostrada por TEMPO, não por posição: ver `_amostrar_tempo`.
        "equity_hist": _amostrar_tempo(db.serie_equity()),
        "metricas": db.metricas(),
        "risco": simulador.guarda_risco(),
        "dca": dca.listar(),
        # [EX-1] SO as pendentes, e com teto. O CLAUDE.md §2 e explicito: o `/estado` e servido
        # a cada poll de 3s e engorda-lo gasta franquia continuamente. Pendente e naturalmente
        # pouca coisa -- o teto de margem limita quantas existem ao mesmo tempo --, mas a tabela
        # `ordens` guarda tambem expirada e preenchida, que so crescem. Historico de ordem se le
        # por rota propria, nao no poll.
        #
        # Elas PRECISAM aparecer: uma ordem pendente ja reserva exposicao nos tetos, entao um
        # painel que nao a mostra esconde risco comprometido.
        "ordens": db.listar("ordens", 20, "WHERE status='pendente'"),
        "auto": _auto["v"],
    }


@app.get("/metricas")
def metricas():
    return db.metricas()


@app.get("/config")
def get_config():
    return _config_publica(db.get_config())


# [F-15][N-26] A ressalva viaja JUNTO com o dado, e não num README que ninguém abre quando
# está com a pergunta na mão. O card nasceu de "quando o `auto_trade` foi religado?", e a
# resposta continua sendo "não dá para saber": esta tabela vale daqui pra frente, e inventar
# a linha que falta seria trocar um "não sei" por um "sei errado" — que é a única coisa pior.
NOTA_AUDITORIA = (
    "A auditoria de config começa em 2026-08-29 ([F-15]). Mudança anterior a essa data NÃO "
    "existe aqui e não foi reconstruída — não há de onde: a tabela `config` guarda só o valor "
    "vigente e o log já rotacionou. Em particular, QUANDO O `auto_trade` FOI RELIGADO continua "
    "sem resposta, e é a pergunta que originou este registro. Lista vazia significa 'nada "
    "mudou desde que isto passou a ser gravado', nunca 'nada mudou'.")


@app.get("/config/auditoria")
def config_auditoria(limite: int = Query(100, ge=1, le=500), chave: str = ""):
    """[F-15][N-26] Quando cada chave de config mudou, de que valor para qual, e por qual porta.

    Rota PROPRIA, e não um campo do `/estado`, por decisão de custo: o painel faz poll do
    `/estado` a cada 3s contra uma franquia de saída de 15 GB/mês (CLAUDE.md §2), e histórico
    é exatamente o tipo de dado que só se lê quando alguém pergunta. Pendurá-lo no poll faria
    o sistema pagar continuamente por uma resposta pedida uma vez por mês.

    A `nota` vai no corpo de propósito. Ela é a metade honesta da entrega: a tabela nasceu em
    2026-08-29 e não há de onde reconstruir o que veio antes — inclusive a pergunta que
    originou o card. Uma lista que sai vazia sem dizer isso deixa quem lê concluir que nada
    mudou, e essa é a única leitura pior do que não ter auditoria nenhuma.
    """
    linhas = db.auditoria_config(limite, chave.strip() or None)
    for l in linhas:                        # a trilha diz QUE o segredo mudou, não para quanto
        if l["chave"] in SEGREDOS:
            for campo in ("valor_antigo", "valor_novo"):
                if l[campo]:
                    l[campo] = MASCARA
    return {"nota": NOTA_AUDITORIA, "chave": chave.strip() or None,
            "total": len(linhas), "linhas": linhas}


@app.get("/catalogo")
def catalogo():
    """[Q-3] O contrato da config, legível por quem opera: o que cada parâmetro aceita, o que
    é o padrão, POR QUE ele é o que é, e quais perfis de risco existem.

    Rota própria, e não campo no `/estado`, porque isto é texto estático de alguns KB e o
    painel faz poll do `/estado` a cada 3s com franquia de 15 GB/mês (CLAUDE.md §2). Uma tela
    de configuração busca isto uma vez; um mostrador não busca nunca.

    NÃO devolve valores vigentes — para isso existe o `GET /config`. Duplicar o valor aqui
    duplicaria também o `telegram_token` em mais uma resposta, sem ganho."""
    params = {}
    for chave, spec in CONFIG_CATALOGO.items():
        tipo = spec[0]
        d = {"tipo": tipo, "padrao": db.CONFIG_PADRAO.get(chave),
             "racional": CONFIG_RACIONAL.get(chave)}       # None = decisão não registrada
        if tipo in ("float", "int"):
            d["min"], d["max"] = spec[1], spec[2]
        elif tipo == "lista_num":          # `min` é EXCLUSIVO aqui (ver `_validar_config`)
            d["min"], d["max"], d["max_itens"] = spec[1], spec[2], spec[3]
        elif tipo == "enum":
            d["opcoes"] = list(spec[1])
        elif tipo == "texto":
            d["max_chars"] = spec[1]
        params[chave] = d
    return {"parametros": params, "perfis": db.PERFIS_RISCO,
            "perfil_ativo": db.perfil_ativo()}


class PerfilReq(BaseModel):
    perfil: str


@app.post("/perfil")
def set_perfil(req: PerfilReq):
    """[Q-3] Aplica um perfil de risco INTEIRO — o "trocável por um comando" do card.

    Os valores do perfil passam pelo `_validar_lote`, o MESMO caminho do `POST /config`. Não é
    cerimônia: gravar direto com `db.set_config` daria ao perfil uma via expressa para o
    banco, e um perfil editado no código passaria por cima das faixas do catálogo sem que
    nada acusasse — exatamente a classe de coisa que o [P1-8] fechou.

    Trocar o perfil ativo é decisão do DONO, não de agente (plano §9.8, `toca-risco`): esta
    rota é o mecanismo, e ela é simétrica — dá para voltar pelo mesmo comando. Fica logada
    como mudança de risco, porque é o que ela é."""
    if req.perfil not in db.PERFIS_RISCO:
        raise HTTPException(422, f"perfil desconhecido: escolha um de {list(db.PERFIS_RISCO)}")
    antes = db.perfil_ativo()
    aceitos = _validar_lote(db.PERFIS_RISCO[req.perfil])
    db.set_configs(aceitos, f"POST /perfil:{req.perfil}")     # todas as chaves ou nenhuma
    cfg = db.get_config()
    log(f"perfil de risco: {antes} -> {req.perfil} ({aceitos})")
    return {"ok": True, "perfil_ativo": db.perfil_ativo(cfg), "perfil_anterior": antes,
            "config": {k: cfg[k] for k in db.PERFIS_RISCO[req.perfil] if k in cfg}}


@app.get("/pendentes")
def pendentes():
    return db.listar("sinais", 30, "WHERE status='novo'")


@app.get("/posicoes")
def posicoes():
    return db.listar("posicoes", 50, "WHERE status='aberta'")


# TETO DE ITENS POR REQUISIÇÃO. Quem escolhe quanto o servidor materializa é o servidor,
# não o cliente. `limite` chegava como inteiro livre e ia direto para o LIMIT do SQLite:
# ?limite=100000000 traz a tabela inteira para a RAM de um host de 1 GiB — e no SQLite
# LIMIT NEGATIVO significa SEM LIMITE, então ?limite=-1 é o mesmo DoS com menos dígitos.
#
# Query(ge=, le=) e não min(): capar em silêncio faz o cliente acreditar que recebeu tudo.
# O 422 nomeia o teto para quem pediu demais, na requisição em que ele pediu.
@app.get("/trades")
def trades(limite: int = Query(50, ge=1, le=500)):
    return db.listar("trades", limite)


# ENTRADA DAS ROTAS DE MERCADO. `ativo` e `tf` iam crus da query para o ccxt: um par mal
# formado ou um timeframe inventado virava exceção da corretora e 500, com uma ida à rede no
# caminho. Validar aqui devolve 422 com o motivo, sem sair da máquina. Par bem formado que a
# corretora não lista ainda vai à rede, e a recusa DELA volta como 502 legível em vez de 500.
MAX_PARES = 60          # o mesmo teto da chave `ativos` no catálogo


def _par(ativo):
    if not _RE_PAR.match(ativo or ""):
        raise HTTPException(422, f"ativo '{str(ativo)[:40]}' fora do formato BASE/QUOTE (ex.: BTC/USDT)")
    return ativo


def _tf(tf):
    if tf not in _TFS:
        raise HTTPException(422, f"timeframe '{str(tf)[:20]}' inválido: use um de {list(_TFS)}")
    return tf


def _na_corretora(fn, *a, **k):
    try:
        return fn(*a, **k)
    except ccxt.BaseError as e:
        raise HTTPException(502, f"a corretora recusou: {type(e).__name__}: {str(e)[:160]}")


@app.get("/candles")
def candles(ativo: str = "BTC/USDT", tf: str = "15m",
            limite: int = Query(200, ge=1, le=1000)):
    # 1000 é o teto do próprio fetch_ohlcv spot: acima disso o ccxt já corta com
    # min(limit, 1000) (ccxt/binance.py) e devolve 200 sem dizer que truncou; abaixo de 1
    # a Binance recusa e a exceção vira 500. Os dois casos deixam de existir aqui na borda.
    raw = _na_corretora(simulador.ex.fetch_ohlcv, _par(ativo), timeframe=_tf(tf), limit=limite)
    return [{"time": int(c[0] // 1000), "open": c[1], "high": c[2],
             "low": c[3], "close": c[4]} for c in raw]


@app.get("/sentimento")
def sentimento():
    return mercado.sentimento()


@app.get("/smartmoney")
def smartmoney(ativo: str = "BTC/USDT"):
    return _na_corretora(mercado.smartmoney, _par(ativo))


@app.get("/book")
def book(ativo: str = "BTC/USDT"):
    return mercado.book(_par(ativo))


@app.get("/saidas")
def saidas():
    """Recomendações de saída ativa por posição (lucro + reversão).

    [F-9] Com o trailing ligado o worker não calcula mais isto a cada ciclo; quem pede é o
    painel, e o cálculo sai daqui, reusado por `SAIDAS_TTL_S`. Painel fechado = zero
    requisição de rede para uma recomendação que ninguém lê."""
    t = _saidas["t"]
    if t is None or time.monotonic() - t > SAIDAS_TTL_S:
        return _calcular_saidas()
    return _saidas["v"]


@app.get("/precos")
def precos(ativos: str = ""):
    """Preço ao vivo de uma lista de ativos (ex: ?ativos=BTC/USDT,ETH/USDT)."""
    lista = [a.strip() for a in ativos.split(",") if a.strip()]
    if len(lista) > MAX_PARES:
        raise HTTPException(422, f"no máximo {MAX_PARES} ativos por requisição")
    return mercado.precos([_par(a) for a in lista]) if lista else {}


@app.get("/analise")
def analise(ativo: str = "BTC/USDT", tf: str = "15m",
            limite: int = Query(200, ge=1, le=1000)):      # o mesmo teto do /candles, pelo mesmo motivo
    """Indicadores + leitura do cenário pro modo 'analisar sinal'."""
    return _na_corretora(signal_engine.analise, _par(ativo), _tf(tf), limite)


@app.get("/funding")
def funding():
    """Ranking de funding (anualizado) de todas as moedas — gatilho do carry."""
    return mercado.funding_ranking()


# ---------- ações ----------
@app.post("/confirmar")
def confirmar(req: ConfirmarReq):
    g = simulador.guarda_risco()
    if g["trava_dia"]:
        return {"ok": False, "erro": f"🛑 Trava diária ativa — perda do dia R${g['pnl_dia']:.2f} "
                f"atingiu o limite (R${g['limite_rs']:.2f}). Sem novos trades hoje."}
    lev = (req.alavancagem if req.alavancagem is not None
           else simulador._cfg_float(db.get_config(), "alavancagem_padrao", 10.0))
    if g["risco_aberto_max_rs"] is not None:
        with db.conectar() as c:
            sig = c.execute("SELECT ativo,direcao,preco,stop_sugerido FROM sinais WHERE id=?",
                            (req.sinal_id,)).fetchone()
        if sig:
            preco = simulador.preco_ao_vivo(sig["ativo"])
            # O MESMO stop que o `abrir()` vai gravar: recomposto pela distância RELATIVA do
            # sinal sobre o preço de agora. Este pré-check usava o stop absoluto do sinal contra
            # o preço ao vivo; com o preço andado a favor ele media um risco maior que o real
            # (R$27 para um trade de R$10) e recusava o que cabia no teto.
            stop = sig["stop_sugerido"]
            if sig["preco"] and stop:
                d = 1 if sig["direcao"] == "LONG" else -1
                stop = preco * (1 - d * abs(sig["preco"] - stop) / sig["preco"])
            r_novo = simulador._risco_posicao(req.valor_reais, lev, preco, stop)
            if g["risco_aberto_rs"] + r_novo > g["risco_aberto_max_rs"]:
                return {"ok": False, "erro": f"📊 Teto de exposição — risco aberto R${g['risco_aberto_rs']:.2f} "
                        f"+ R${r_novo:.2f} deste trade passa o limite R${g['risco_aberto_max_rs']:.2f}. "
                        f"Feche uma posição ou reduza o tamanho."}
    try:
        # [EX-1] `executar` despacha pelo `exec_modo`: com `mercado` (default) e o `abrir()` de
        # sempre e o contrato da rota nao muda. Com `post_only` a resposta passa a devolver
        # `ordem_id` em vez de `posicao_id`, e quem le o painel PRECISA ver essa diferenca --
        # uma ordem pendente nao e uma posicao, e chamar as duas de "aberta" seria mentir sobre
        # exposicao.
        tipo, ident = simulador.executar(req.sinal_id, req.valor_reais, lev)
        if tipo == "ordem":
            return {"ok": True, "tipo": "ordem", "ordem_id": ident,
                    "msg": "ordem post-only colocada — vira posição se o preço vier até ela"}
        pid = ident
    except ValueError as e:
        # abrir() diz "nao, e por este motivo" levantando ValueError. Sem traduzir isso para o
        # contrato {ok:false, erro} o FastAPI trata a RECUSA como falha do servidor: 500, e o
        # painel mostra "erro" generico para uma decisao deliberada do sistema. Os pre-checks
        # acima nunca vao cobrir tudo por construcao — o teto de MARGEM e o claim atomico do
        # sinal so existem dentro do lock de abrir(), e trava/risco ainda podem tripar entre o
        # check e a abertura. Quem sabe o motivo e abrir(); aqui so se traduz. Mesmo tratamento
        # que o auto-trader ja da (autotrader.py:166). Excecao que NAO e ValueError (rede, banco)
        # continua subindo como 500: aquilo e falha de verdade, e mentir sobre ela seria pior.
        return {"ok": False, "erro": f"{'🛑' if 'trava' in str(e) else '📊'} {e}"}
    return {"ok": True, "posicao_id": pid}


@app.post("/panico")
def panico(pular_pendentes: bool = False):
    """Kill-switch: DESLIGA o auto-trader e fecha TODAS as posições abertas no preço ao vivo.

    Desligar vem PRIMEIRO de propósito: se fechar alguma posição falhar no meio, o bot já
    está morto e não reabre. Quem aperta o botão quer parar o sistema, não redistribuir a
    carteira — e religar passa a exigir ação explícita no painel.

    `pular_pendentes=1` marca também os sinais 'novo' como pulados. Fica DESLIGADO por
    padrão: é decisão de produto (a fila pendente é combustível para religar por engano,
    mas o auto-trader já só opera sinal com até `auto_freshness_min` minutos, então ela
    envelhece sozinha) e o card [P1-7] a deixou explicitamente em aberto."""
    # Desligar e cancelar acontecem SOB o lock de abertura. "Antes de fechar" não bastava: um
    # ciclo do bot que já tinha lido `auto_trade=1` e estava buscando preço na rede abria a
    # posição DEPOIS deste ponto, e o pânico não volta para fechá-la. Com o lock, a entrada do
    # bot ou terminou antes (e a posição dela está na lista que se fecha abaixo) ou confere o
    # `auto_trade` depois, dentro do mesmo lock, e desiste (`simulador._checar_tetos`). O mesmo
    # vale para ordem enchendo: `_abrir_da_ordem` só enche ordem ainda 'pendente', sob este lock.
    with simulador._abrir_lock:
        db.set_config("auto_trade", "0", "POST /panico")    # mata o bot ANTES de fechar
        _auto["v"] = {"ativo": False, "motivo": "desligado pelo pânico"}   # /estado não mostra ciclo velho
        # [EX-1] Ordem post-only pendente é posição esperando o preço: sem cancelar aqui, ela
        # enchia no ciclo seguinte e o pânico deixava o sistema com posição aberta.
        canceladas = _cancelar_ordens("panico")
    log("PÂNICO: auto-trader desligado", "error")
    # -1 = sem LIMIT (SQLite). Eram 200: o kill-switch promete TODAS, e com 205 abertas sobravam 5.
    abertas = db.listar("posicoes", -1, "WHERE status='aberta'")
    n, total, falhas = 0, 0.0, []
    for p in abertas:
        try:
            pnl = simulador.fechar(p["id"], "panico")
            if pnl is not None:
                total += pnl
                n += 1
        except Exception as e:
            # A falha de UMA posição não interrompe as outras, mas também não pode sumir: a
            # resposta dizia só `fechadas: n`, e o painel anunciava o pânico como sucesso com
            # uma posição ainda viva. Quem ficou aberta volta nomeada em `falhas`.
            falhas.append({"id": p["id"], "ativo": p["ativo"], "erro": f"{type(e).__name__}: {str(e)[:120]}"})
            log(f"panico erro pos {p['id']}: {e}", "error")
    pulados = 0
    if pular_pendentes:
        with db.conectar() as c:
            pulados = c.execute("UPDATE sinais SET status='pulado' WHERE status='novo'").rowcount
    return {"ok": not falhas, "fechadas": n, "pnl": round(total, 2),
            "auto_desligado": True, "pendentes_pulados": pulados,
            "ordens_canceladas": canceladas, "falhas": falhas}


def _cancelar_ordens(motivo, con=None):
    """Cancela toda ordem pendente. Cancela, e não apaga: a tabela `ordens` é o log de fill do
    post-only (PLANO-V2 D-2), e a ordem que não chegou a encher também é medição."""
    sql = ("UPDATE ordens SET status='cancelada', motivo=?, resolvida_em=? "
           "WHERE status='pendente'")
    args = (motivo, str(pd.Timestamp.now()))
    if con is not None:
        return con.execute(sql, args).rowcount
    with db.conectar() as c:
        return c.execute(sql, args).rowcount


@app.post("/pular")
def pular(req: IdReq):
    # Só sinal na fila: sem `status='novo'` o pular reescrevia um sinal já confirmado (que virou
    # posição) para 'pulado', e o histórico passava a dizer que a posição veio de um sinal pulado.
    with db.conectar() as c:
        n = c.execute("UPDATE sinais SET status='pulado' WHERE id=? AND status='novo'",
                      (req.id,)).rowcount
    if n != 1:
        return {"ok": False, "erro": "sinal não está mais na fila"}
    return {"ok": True}


@app.post("/fechar")
def fechar(req: IdReq):
    try:                                     # mesmo contrato do /confirmar: recusa do dominio nao e 500
        pnl = simulador.fechar(req.id, "manual")
    except ValueError as e:
        return {"ok": False, "erro": f"📊 {e}"}
    return {"ok": True, "pnl": pnl}          # pnl=None => ja estava fechada (nao e erro)


@app.post("/scan")
def scan_now():
    res, novos = signal_engine.scan()
    return {"varridos": len(res), "novos": novos}


@app.post("/config")
def set_config(body: dict):
    """Grava configuração VALIDADA. Chave fora do catálogo, tipo errado ou valor fora de
    faixa -> 422 dizendo o que foi recusado, em vez de gravar lixo que só explode depois,
    longe daqui, dentro de guarda_risco()."""
    limpo = _sem_mascara(body)
    if body and not limpo:                  # só veio a máscara de volta: nada a gravar
        return _config_publica(db.get_config())
    aceitos = _validar_lote(limpo)
    db.set_configs(aceitos, "POST /config")
    return _config_publica(db.get_config())


AUTO_PERMITIDAS = {"auto_trade", "auto_conviccao_min", "auto_max_posicoes", "auto_max_valor_frac",
                   "auto_fechar_saida", "auto_freshness_min", "alavancagem_padrao", "risco_por_trade",
                   "auto_lev_modo", "auto_lev_min", "auto_lev_max", "auto_cooldown_min", "exposicao_max",
                   "trailing_ativo", "trailing_dist"}


@app.post("/auto")
def set_auto(body: dict):
    """Liga/desliga e ajusta o auto-trader (experimento). Whitelist de chaves E validação
    de valores: a whitelist sozinha deixava passar auto_max_posicoes="banana"."""
    aceitos = _validar_lote(body, AUTO_PERMITIDAS)
    db.set_configs(aceitos, "POST /auto")
    cfg = db.get_config()
    return {"ok": True, "config": {k: cfg[k] for k in AUTO_PERMITIDAS if k in cfg},
            "estado": _auto["v"]}


# [PUSH-1] Notificacao nativa no celular. As quatro rotas ficam atras da mesma senha do painel
# (o middleware `auth_basica` roda antes). A chave PUBLICA sai daqui porque o aparelho precisa
# dela para se inscrever; a privada nunca sai do `.env`. Na conta B estas rotas chegam pelo
# repasse `/testeB/push/...`, e cada conta guarda as proprias inscricoes no proprio banco.
class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushInscricaoReq(BaseModel):
    endpoint: str
    keys: PushKeys


class PushSairReq(BaseModel):
    endpoint: str


class PushTesteReq(BaseModel):
    endpoint: Optional[str] = None


class PushPrefsReq(BaseModel):
    endpoint: str
    prefs: dict


@app.get("/push/chave")
def push_chave(endpoint: Optional[str] = None):
    """`inscrito` diz se ESTE aparelho (o `endpoint` dele) recebe desta conta: o mesmo aparelho
    pode estar inscrito na A e nao na B, e o app precisa saber qual botao mostrar."""
    ativo, motivo = push.estado()
    subs = push.inscricoes()
    meu = next((x for x in subs if endpoint and x["endpoint"] == endpoint), None)
    return {"ativo": ativo, "chave": push.chave_publica() if ativo else None, "motivo": motivo,
            "conta": CONTA, "aparelhos": len(subs), "inscrito": meu is not None,
            # [PUSH-2] as preferencias DESTE aparelho, e o catalogo que o app desenha
            "prefs": meu["prefs"] if meu else None,
            "catalogo": {"tipos": list(push.TIPOS), "modos": list(push.MODOS),
                         "resumo_h": list(push.RESUMO_H)}}


@app.post("/push/inscrever")
def push_inscrever(req: PushInscricaoReq, request: Request):
    ativo, motivo = push.estado()
    if not ativo:
        return {"ok": False, "erro": motivo}
    try:
        n = push.inscrever(req.endpoint, req.keys.p256dh, req.keys.auth,
                           request.headers.get("user-agent", ""))
    except ValueError as e:
        return {"ok": False, "erro": str(e)}
    log(f"push: aparelho inscrito ({n} no total)")
    return {"ok": True, "aparelhos": n}


@app.post("/push/sair")
def push_sair(req: PushSairReq):
    return {"ok": True, "removidas": push.sair(req.endpoint)}


@app.post("/push/teste")
def push_teste(req: PushTesteReq):
    """Entrega SINCRONA, para o app dizer na hora se chegou ao servico de push."""
    r = push.enviar_agora(*push.MSG_TESTE, "#painel", "teste", so=req.endpoint)
    return {**r, "ok": r["ok"] > 0, "enviados": r["ok"]}


@app.post("/push/prefs")
def push_prefs(req: PushPrefsReq):
    """[PUSH-2] O que ESTE aparelho recebe: cada tipo na hora / so no resumo / desligado, o
    intervalo do resumo e o horario silencioso. Valor fora do catalogo e recusado, nao adivinhado."""
    try:
        p = push.salvar_prefs(req.endpoint, req.prefs)
    except ValueError as e:
        return {"ok": False, "erro": str(e)}
    if p is None:
        return {"ok": False, "erro": "este aparelho nao esta inscrito nesta conta"}
    log(f"push: preferencias de um aparelho mudaram: {req.prefs}")
    return {"ok": True, "prefs": p}


@app.post("/push/resumo")
def push_resumo(req: PushSairReq):
    """[PUSH-2] Manda o resumo agora, para ver como ele chega; nao mexe no relogio do agendado."""
    r = push.enviar_resumo_agora(req.endpoint)
    return {**r, "ok": r["ok"] > 0}


@app.post("/dca")
def dca_criar(req: DcaReq):
    try:                                     # mesmo contrato do /confirmar: recusa do dominio nao e 500
        dca.criar(req.ativo, req.valor_aporte, req.freq_dias)
    except ValueError as e:
        return {"ok": False, "erro": f"📊 {e}"}
    return {"ok": True}


@app.post("/dca/aportar")
def dca_aportar(req: IdReq):
    try:                                     # idem: ValueError do dominio vira recusa, nao 500
        preco = dca.aportar(req.id)
    except ValueError as e:
        return {"ok": False, "erro": f"📊 {e}"}
    return {"ok": preco is not None, "preco": preco}


@app.post("/dca/remover")
def dca_remover(req: IdReq):
    if not dca.remover(req.id):
        return {"ok": False, "erro": "📊 plano não encontrado (ou já removido)"}
    return {"ok": True}


# ---------- provas de regressao do territorio T-API-DADOS ----------
# No proprio modulo, e nao num script solto, porque prova fora do repositorio nao e
# reexecutavel. Importar api.py nao abre banco nem rede (init_db so roda no lifespan).
#
#     python api.py           # asseracoes; exit 1 se qualquer uma falhar


def _prova_api():
    import tempfile
    ok = fail = 0

    def check(nome, cond, detalhe=""):
        nonlocal ok, fail
        print(("  PASSA  " if cond else "  FALHA  ") + nome + ("" if cond else "  <- " + str(detalhe)))
        if cond:
            ok += 1
        else:
            fail += 1

    # ---------- [P1-4] _amostrar reduz na faixa em que antes nao reduzia nada
    # A tabela de medicao do card (2026-08-19) e o teste: era 200 -> 200 e 249 -> 249.
    print("  [P1-4] _amostrar(alvo=125)")
    print("      entrada -> saida:", {n: len(_amostrar(list(range(n)))) for n in
                                      (124, 125, 126, 200, 249, 250, 500)})
    for n in (200, 249):
        check("%d pontos reduzem para ~125" % n, len(_amostrar(list(range(n)))) <= 126,
              str(len(_amostrar(list(range(n))))))
    check("124 pontos passam intactos (abaixo do alvo)", _amostrar(list(range(124))) == list(range(124)))
    check("250 e 500 continuam em ~125",
          len(_amostrar(list(range(250)))) <= 126 and len(_amostrar(list(range(500)))) <= 126)
    # varredura: as tres propriedades que a funcao promete, para todo tamanho ate 3x o alvo
    falhou_ult = falhou_teto = falhou_ordem = falhou_1o = None
    for n in range(1, 601):
        seq = list(range(n))
        a = _amostrar(seq)
        if a[-1] != seq[-1]:
            falhou_ult = n
        if len(a) > 126:
            falhou_teto = (n, len(a))
        if a != sorted(a):
            falhou_ordem = n
        if a[0] != seq[0]:
            falhou_1o = n
    check("o ultimo ponto da serie esta SEMPRE na amostra", falhou_ult is None, "n=%s" % falhou_ult)
    check("o primeiro ponto tambem (preserva o intervalo)", falhou_1o is None, "n=%s" % falhou_1o)
    check("nenhum tamanho ate 600 passa de 126 pontos", falhou_teto is None, str(falhou_teto))
    check("a ordem cronologica e preservada", falhou_ordem is None, "n=%s" % falhou_ordem)
    # criterio "o grafico mantem a mesma forma visual": a amostragem e uniforme, entao
    # media e extremos da amostra acompanham os da serie inteira.
    import math
    curva = [1000 + 200 * math.sin(i / 40) for i in range(500)]
    am = _amostrar(curva)
    dm = abs(sum(am) / len(am) - sum(curva) / len(curva))
    check("a forma da curva sobrevive (media %.2f, topo %.2f, fundo %.2f de erro)"
          % (dm, abs(max(am) - max(curva)), abs(min(am) - min(curva))),
          dm < 1 and abs(max(am) - max(curva)) < 1 and abs(min(am) - min(curva)) < 1)

    # ---------- [P2-15] a cadencia do scan para de derivar quando o ciclo falha
    print("  [P2-15] cadencia do scan (INTERVALO_SCAN=%ds, ciclo=%ds)"
          % (INTERVALO_SCAN, POLL_ATUALIZAR))
    ciclos = [i * POLL_ATUALIZAR for i in range(41)]        # 10 minutos de worker
    aborta = lambda i: i % 3 != 0                          # 2 de cada 3 ciclos abortam o try

    def intervalos(d):
        return [b - a for a, b in zip(d, d[1:])]

    # O MODELO DO BUG: `ciclos % 4 == 0` avaliado DENTRO do try. O contador sempre avanca,
    # mas o scan so acontece se o ciclo chegou ate ele -- entao a falha come o slot.
    antigo = [t for i, t in enumerate(ciclos) if i % 4 == 0 and not aborta(i)]
    check("modelo do bug: sob falha intermitente a cadencia ANTIGA ia a %ds"
          % max(intervalos(antigo)), max(intervalos(antigo)) > INTERVALO_SCAN, str(antigo))

    # A CORRECAO: `_scan_devido` e chamada de FORA do try, entao `aborta` nao a alcanca --
    # por isso a lista abaixo nao filtra por ela. Que esteja fora do try se ve no diff;
    # que a cadencia nao derive por conta do relogio e o que se prova aqui.
    _scan_sched["proximo"] = 0.0
    novo_d = [t for t in ciclos if _scan_devido(float(t))]
    check("agendado por relogio, o scan vem a cada %ds mesmo com os ciclos falhando"
          % INTERVALO_SCAN, set(intervalos(novo_d)) == {INTERVALO_SCAN}, str(novo_d))

    # reagendou ANTES de rodar: mesmo que o proprio scan levante, o proximo continua a 60s
    _scan_sched["proximo"] = 0.0
    _scan_devido(1000.0)                                   # "rodou" e explodiu logo depois
    check("scan que levanta nao trava a cadencia (reagenda antes de rodar)",
          _scan_devido(1000.0 + INTERVALO_SCAN - 1) is False
          and _scan_devido(1000.0 + INTERVALO_SCAN) is True)

    # ---------- [P2-15] scan verde apaga o erro do painel, sem apagar o forense
    # /status le o banco; aponta para um TEMPORARIO -- o trading.db local esta vazio.
    db.DB = os.path.join(tempfile.mkdtemp(), "prova_api.db")
    db.init_db()
    signal_engine.ultimo_scan.update(ts="2026-08-22 10:00:00", total=3, ok=0, falhas=3,
                                     ultimo_erro="BTC/USDT 15m: ExchangeError: 451",
                                     ultimo_erro_historico="2026-08-22 10:00:00 BTC/USDT 15m: "
                                                           "ExchangeError: 451")
    st = status()
    check("scan cego: /status mostra o erro e saudavel=False",
          st["scan"]["ultimo_erro"] and st["saudavel"] is False, str(st["scan"]))
    # exatamente o que scan() faz ao comecar uma varredura, agora com ultimo_erro=None
    signal_engine.ultimo_scan.update(ts="2026-08-22 11:00:00", total=0, ok=0, falhas=0,
                                     fluxo_indisponivel=0, ultimo_erro=None)
    signal_engine.ultimo_scan.update(total=3, ok=3, falhas=0)          # varredura 100% verde
    st = status()
    check("scan verde depois de scan com falha: /status sem ultimo_erro atual",
          st["scan"]["ultimo_erro"] is None, str(st["scan"]))
    check("o forense sobrevive em ultimo_erro_historico",
          "451" in (st["scan"]["ultimo_erro_historico"] or ""),
          str(st["scan"]["ultimo_erro_historico"]))
    check("/status continua expondo saudavel exatamente como hoje", st["saudavel"] is True)
    check("o contador do [P2-9] segue publicado (sem regressao)",
          "fluxo_indisponivel" in st["scan"])

    # ---------- [P2-10] o contador de falhas de funding aparece no /status
    simulador.funding_medicao.update(medidos=7, falhas=2,
                                     ultimo_erro="BTC/USDT: ExchangeNotAvailable: 451",
                                     ultimo_erro_ts="2026-08-22 09:30:00")
    st = status()
    check("/status publica o contador de funding",
          st.get("funding", {}).get("falhas") == 2 and st["funding"]["medidos"] == 7,
          str(st.get("funding")))
    check("e publica o motivo da ultima falha, nao so a contagem",
          "451" in (st["funding"]["ultimo_erro"] or ""), str(st["funding"]["ultimo_erro"]))
    check("falha de funding NAO derruba saudavel (criterio inalterado)",
          st["saudavel"] is True, str(st["saudavel"]))
    check("scan e marcacao seguem publicados ao lado (sem regressao)",
          "scan" in st and "marcacao" in st)

    # ---------- [P2-3] /health responde QUAL commit esta rodando
    # [vigia] a prova nao sobe o worker; um ciclo recente fixado aqui mantem o /health no
    # ramo 200, que e o que esta prova confere (versao e commit), sem depender do relogio.
    _vigia["ultimo"] = time.monotonic()
    print("  [P2-3] /health =", health())
    h = health()
    # a auto-checagem confere que a versao VEM DA FONTE UNICA -- nunca que ela vale um
    # numero especifico. Cravar o numero aqui foi o que transformou "esqueci de subir a
    # versao" em "nao pode subir a versao" (ver `versao.py`).
    check("/health continua com status e versao, e a versao vem de versao.VERSAO",
          h["status"] == "ok" and h["versao"] == VERSAO, str(h))
    check("/health devolve o commit", "commit" in h)
    check("o commit vem do valor lido no import, nao de um subprocesso por requisicao",
          h["commit"] is COMMIT)
    check("neste repositorio o commit e o HEAD de verdade",
          h["commit"] == subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                        text=True).stdout.strip(), str(h["commit"]))
    sem_git = _commit_em_producao(raiz=tempfile.mkdtemp())
    check("sem git, devolve None DECLARADO -- nunca 'desconhecido' nem 'dev'",
          sem_git is None, repr(sem_git))
    os.environ["COMMIT_SHA"] = "deadbeefcafe"
    try:
        check("COMMIT_SHA do ambiente tem precedencia (deploy sem git)",
              _commit_em_producao() == "deadbeefcafe")
    finally:
        os.environ.pop("COMMIT_SHA", None)

    print("\n  %d passaram, %d falharam" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    try:                                   # console do Windows em cp1252 mutila o acento
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(_prova_api())
