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
import threading
import time
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import simulador
import signal_engine
import mercado
import dca
import autotrader
from logbot import log

POLL_ATUALIZAR = 15   # marca posições a cada 15s
INTERVALO_SCAN = 60   # [P2-15] scan de sinais a cada 60s, por RELÓGIO (ver _scan_devido)
_worker_on = {"v": True}
_health = {"iniciado": None, "ultimo_ciclo": None, "ciclos": 0, "erros": 0}
_saidas = {"v": []}   # recomendações de saída ativa, atualizadas pelo worker
_auto = {"v": {"ativo": False}}   # último ciclo do auto-trader
_poda = {"dia": None, "ultimo": None}   # [P2-11] retenção da curva de equity, 1x/dia
_scan_sched = {"proximo": 0.0}          # [P2-15] instante (monotonic) do próximo scan; 0 = já vence


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


def equity_total():
    with db.conectar() as c:
        banca = c.execute("SELECT atual FROM banca WHERE id=1").fetchone()["atual"]
        unreal = c.execute("SELECT COALESCE(SUM(pnl),0) FROM posicoes WHERE status='aberta'").fetchone()[0]
    return banca + (unreal or 0)


def worker():
    _health["iniciado"] = str(pd.Timestamp.now())
    log("worker iniciado")
    while _worker_on["v"]:
        try:
            simulador.atualizar()                       # marca/fecha posições no preço real
            abertas = db.listar("posicoes", 50, "WHERE status='aberta'")
            _saidas["v"] = [r for r in (signal_engine.avaliar_saida(p) for p in abertas) if r]
            dca.processar_devidos()                     # aportes DCA vencidos
            try:
                _auto["v"] = autotrader.auto_executar(_saidas["v"])   # bot abre/fecha sozinho (se ligado)
            except Exception as e:                      # falha do bot não derruba o snapshot de equity abaixo
                _health["erros"] += 1
                log(f"auto-trader erro: {e}", "error")
            with db.conectar() as c:                    # snapshot de equity p/ o gráfico
                c.execute("INSERT INTO equity(ts,banca,equity_total) VALUES(?,?,?)",
                          (str(pd.Timestamp.now()), db.get_banca()["atual"], equity_total()))
            _health["ultimo_ciclo"] = str(pd.Timestamp.now())
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
    db.init_db()
    threading.Thread(target=worker, daemon=True).start()
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
app = FastAPI(title="Cripto Bot API", version="0.3", lifespan=lifespan,
              docs_url=None if DASH_PASS else "/docs",
              redoc_url=None if DASH_PASS else "/redoc",
              openapi_url=None if DASH_PASS else "/openapi.json")
# Origens do front. Local/monolito: "*". Front separado (Vercel): liste a origem exata,
# ex CORS_ORIGINS="https://meu-bot.vercel.app" (várias separadas por vírgula).
# O add_middleware do CORS mora DEPOIS de auth_basica (fim deste bloco): a ordem decide
# quem embrulha quem, e o CORS precisa embrulhar a auth. Ver a nota lá embaixo.
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]

LOOPBACK = {"127.0.0.1", "::1"}
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
        return xff.split(",")[0].strip()
    return peer


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
    if request.url.path == "/health" or request.method == "OPTIONS":
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
    "auto_lev_modo":        ("enum", ("conviccao", "fixo")),
    "auto_lev_min":         ("float", 1.0, 50.0),
    "auto_lev_max":         ("float", 1.0, 50.0),
    "trailing_ativo":       ("bool",),
    "trailing_dist":        ("float", 0.001, 0.5),
    # estado / integrações
    "trava_dia_em":         ("data",),
    "telegram_token":       ("texto", 200),
    "telegram_chat_id":     ("texto", 64),
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

    if tipo == "data":
        if bruto and not _RE_DATA.match(bruto):
            raise ValueError(f"'{chave}': '{valor}' não é uma data AAAA-MM-DD (ou vazio)")
        return bruto

    if len(bruto) > spec[1]:                                 # texto
        raise ValueError(f"'{chave}': passa de {spec[1]} caracteres")
    return bruto


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
    if recusados:
        log(f"config recusada: {recusados}", "error")
        raise HTTPException(422, {"erro": "configuração recusada — nada foi gravado",
                                  "recusados": recusados})
    return aceitos


# ---------- modelos ----------
class ConfirmarReq(BaseModel):
    sinal_id: int
    valor_reais: float
    alavancagem: float = 10.0


class IdReq(BaseModel):
    id: int


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


@app.get("/config.js")
def config_js():
    return FileResponse(os.path.join(WEB, "config.js"), media_type="application/javascript")


@app.get("/health")
def health():
    return {"status": "ok", "versao": "0.3"}


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
    return {**_health, "worker_on": _worker_on["v"], "scan": sc, "marcacao": mk,
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
        c.execute("INSERT INTO config(chave,valor) VALUES('trava_dia_em','') "
                  "ON CONFLICT(chave) DO UPDATE SET valor=''")
    # estado derivado em memória: sem isto o painel exibe, até o próximo ciclo (15s),
    # recomendações de saída e um contador de marcação de posições que não existem mais.
    _saidas["v"] = []
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


@app.get("/estado")
def estado():
    """Tudo que a UI precisa num request só."""
    return {
        "banca": db.get_banca(),
        "equity_total": round(equity_total(), 2),
        "config": db.get_config(),
        "pendentes": db.listar("sinais", 30, "WHERE status='novo'"),
        "posicoes": db.listar("posicoes", 50, "WHERE status='aberta'"),
        "trades": db.listar("trades", 30),
        # [P2-11] a série INTEIRA (a poda a mantém pequena), reduzida a ~125 pontos pelo
        # _amostrar. Era `listar("equity", 500)[::-1]`: 500 linhas de 15s = 125 minutos, ou
        # seja o "gráfico da banca" mostrava ~2h e nunca a trajetória — que é a única
        # leitura que ele existe para dar. O formato do payload não muda (ts/banca/
        # equity_total, em ordem cronológica), então o front não muda junto.
        "equity_hist": _amostrar(db.serie_equity()),
        "metricas": db.metricas(),
        "risco": simulador.guarda_risco(),
        "dca": dca.listar(),
        "auto": _auto["v"],
    }


@app.get("/metricas")
def metricas():
    return db.metricas()


@app.get("/config")
def get_config():
    return db.get_config()


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


@app.get("/candles")
def candles(ativo: str = "BTC/USDT", tf: str = "15m",
            limite: int = Query(200, ge=1, le=1000)):
    # 1000 é o teto do próprio fetch_ohlcv spot: acima disso o ccxt já corta com
    # min(limit, 1000) (ccxt/binance.py) e devolve 200 sem dizer que truncou; abaixo de 1
    # a Binance recusa e a exceção vira 500. Os dois casos deixam de existir aqui na borda.
    raw = simulador.ex.fetch_ohlcv(ativo, timeframe=tf, limit=limite)
    return [{"time": int(c[0] // 1000), "open": c[1], "high": c[2],
             "low": c[3], "close": c[4]} for c in raw]


@app.get("/sentimento")
def sentimento():
    return mercado.sentimento()


@app.get("/smartmoney")
def smartmoney(ativo: str = "BTC/USDT"):
    return mercado.smartmoney(ativo)


@app.get("/book")
def book(ativo: str = "BTC/USDT"):
    return mercado.book(ativo)


@app.get("/saidas")
def saidas():
    """Recomendações de saída ativa por posição (lucro + reversão)."""
    return _saidas["v"]


@app.get("/precos")
def precos(ativos: str = ""):
    """Preço ao vivo de uma lista de ativos (ex: ?ativos=BTC/USDT,ETH/USDT)."""
    lista = [a.strip() for a in ativos.split(",") if a.strip()]
    return mercado.precos(lista) if lista else {}


@app.get("/analise")
def analise(ativo: str = "BTC/USDT", tf: str = "15m", limite: int = 200):
    """Indicadores + leitura do cenário pro modo 'analisar sinal'."""
    return signal_engine.analise(ativo, tf, limite)


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
    if g["risco_aberto_max_rs"] is not None:
        with db.conectar() as c:
            sig = c.execute("SELECT ativo,stop_sugerido FROM sinais WHERE id=?", (req.sinal_id,)).fetchone()
        if sig:
            preco = simulador.preco_ao_vivo(sig["ativo"])
            r_novo = simulador._risco_posicao(req.valor_reais, req.alavancagem, preco, sig["stop_sugerido"])
            if g["risco_aberto_rs"] + r_novo > g["risco_aberto_max_rs"]:
                return {"ok": False, "erro": f"📊 Teto de exposição — risco aberto R${g['risco_aberto_rs']:.2f} "
                        f"+ R${r_novo:.2f} deste trade passa o limite R${g['risco_aberto_max_rs']:.2f}. "
                        f"Feche uma posição ou reduza o tamanho."}
    try:
        pid = simulador.abrir(req.sinal_id, req.valor_reais, req.alavancagem)
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
    db.set_config("auto_trade", "0")            # mata o bot ANTES de fechar
    _auto["v"] = {"ativo": False, "motivo": "desligado pelo pânico"}   # /estado não mostra ciclo velho
    log("PÂNICO: auto-trader desligado", "error")
    abertas = db.listar("posicoes", 200, "WHERE status='aberta'")
    n, total = 0, 0.0
    for p in abertas:
        try:
            pnl = simulador.fechar(p["id"], "panico")
            if pnl is not None:
                total += pnl
                n += 1
        except Exception as e:
            log(f"panico erro pos {p['id']}: {e}", "error")
    pulados = 0
    if pular_pendentes:
        with db.conectar() as c:
            pulados = c.execute("UPDATE sinais SET status='pulado' WHERE status='novo'").rowcount
    return {"ok": True, "fechadas": n, "pnl": round(total, 2),
            "auto_desligado": True, "pendentes_pulados": pulados}


@app.post("/pular")
def pular(req: IdReq):
    with db.conectar() as c:
        c.execute("UPDATE sinais SET status='pulado' WHERE id=?", (req.id,))
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
    aceitos = _validar_lote(body)
    for k, v in aceitos.items():
        db.set_config(k, v)
    return db.get_config()


AUTO_PERMITIDAS = {"auto_trade", "auto_conviccao_min", "auto_max_posicoes", "auto_max_valor_frac",
                   "auto_fechar_saida", "auto_freshness_min", "alavancagem_padrao", "risco_por_trade",
                   "auto_lev_modo", "auto_lev_min", "auto_lev_max", "auto_cooldown_min", "exposicao_max",
                   "trailing_ativo", "trailing_dist"}


@app.post("/auto")
def set_auto(body: dict):
    """Liga/desliga e ajusta o auto-trader (experimento). Whitelist de chaves E validação
    de valores: a whitelist sozinha deixava passar auto_max_posicoes="banana"."""
    aceitos = _validar_lote(body, AUTO_PERMITIDAS)
    for k, v in aceitos.items():
        db.set_config(k, v)
    cfg = db.get_config()
    return {"ok": True, "config": {k: cfg[k] for k in AUTO_PERMITIDAS if k in cfg},
            "estado": _auto["v"]}


@app.post("/dca")
def dca_criar(req: DcaReq):
    dca.criar(req.ativo, req.valor_aporte, req.freq_dias)
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
    dca.remover(req.id)
    return {"ok": True}


# ---------- provas de regressao do territorio T-API-DADOS ----------
# No proprio modulo, e nao num script solto, porque prova fora do repositorio nao e
# reexecutavel. Importar api.py nao abre banco nem rede (init_db so roda no lifespan).
#
#     python api.py           # asseracoes; exit 1 se qualquer uma falhar


def _prova_api():
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
    import tempfile
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

    print("\n  %d passaram, %d falharam" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    import sys
    try:                                   # console do Windows em cp1252 mutila o acento
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(_prova_api())
