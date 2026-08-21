"""Prova do P0-1: o backend não serve nada para a internet sem credencial.

Cada cenário roda num processo próprio porque DASH_PASS é lido no import do api.py.
    python test_auth.py            # roda os três cenários
    python test_auth.py com_senha  # um só
"""
import base64
import os
import subprocess
import sys
import tempfile

CENARIOS = ("com_senha", "sem_senha", "bandeira_velha")
SENHA = "SenhaForteDeTeste123456xy"
ORIGEM = "https://cripto-quant-dashboard.vercel.app"   # front separado, como em produção


def rodar(cenario):
    os.environ["DB_PATH"] = os.path.join(tempfile.gettempdir(), f"test_auth_{cenario}.db")
    if cenario == "com_senha":
        os.environ["DASH_PASS"] = SENHA
        os.environ["CORS_ORIGINS"] = ORIGEM        # front no Vercel: origem exata, não "*"
    else:
        os.environ.pop("DASH_PASS", None)
        if cenario == "bandeira_velha":
            # o .env que deixou o painel aberto por 24h; a bandeira não existe mais no código
            os.environ["PERMITIR_SEM_SENHA"] = "1"

    from fastapi.testclient import TestClient
    import api, db
    db.init_db()
    # client=127.0.0.1 porque o peer default do TestClient ("testclient") não é loopback
    c = TestClient(api.app, client=("127.0.0.1", 5555))
    fora = {"x-forwarded-for": "203.0.113.9", "x-forwarded-proto": "https"}   # veio do Caddy
    auth = {"authorization": "Basic " + base64.b64encode(f"admin:{SENHA}".encode()).decode()}
    logado = {**fora, **auth}
    cross = {**fora, "origin": ORIGEM}             # o painel do Vercel chamando a VM
    ok = True

    def check(rotulo, obtido, esperado):
        nonlocal ok
        bom = obtido == esperado
        ok = ok and bom
        print(f"  {'PASS' if bom else 'FALHA'}  {rotulo}: {obtido} (esperado {esperado})")

    print(f"[{cenario}]")
    if cenario == "com_senha":
        check("GET /estado sem credencial", c.get("/estado", headers=fora).status_code, 401)
        check("POST /auto sem credencial", c.post("/auto", json={"ativo": True}, headers=fora).status_code, 401)
        check("POST /reset sem credencial", c.post("/reset", json={"confirmar": "RESET"}, headers=fora).status_code, 401)
        check("GET /docs sem credencial", c.get("/docs", headers=fora).status_code, 401)
        # 404 autenticado = a rota não existe mesmo, não é só o 401 do middleware
        check("GET /docs autenticado", c.get("/docs", headers=logado).status_code, 404)
        check("GET /redoc autenticado", c.get("/redoc", headers=logado).status_code, 404)
        check("GET /openapi.json autenticado", c.get("/openapi.json", headers=logado).status_code, 404)
        check("GET /health (monitoramento segue aberto)", c.get("/health", headers=fora).status_code, 200)
        check("GET /estado autenticado", c.get("/estado", headers=logado).status_code, 200)
        check("POST /reset autenticado sem confirmar", c.post("/reset", json={}, headers=logado).status_code, 400)
        check("POST /reset autenticado confirmando", c.post("/reset", json={"confirmar": "RESET"}, headers=logado).status_code, 200)

        # Resposta da auth SEM Access-Control-Allow-Origin não é 401 para o navegador: é falha
        # de CORS. O fetch rejeita, o front nunca vê o status, o prompt de senha nunca abre e
        # o painel parece backend fora do ar. Foi o que ligar o DASH_PASS causou.
        def acao(r):
            return r.headers.get("access-control-allow-origin")

        check("401 sem credencial devolve ACAO ao front", acao(c.get("/estado", headers=cross)), ORIGEM)
        check("401 com senha errada devolve ACAO", acao(c.get("/estado", headers={**cross, "authorization": "Basic eGX6"})), ORIGEM)
        check("200 autenticado devolve ACAO", acao(c.get("/estado", headers={**cross, **auth})), ORIGEM)
        check("preflight OPTIONS passa", c.options("/estado", headers={**cross, "access-control-request-method": "GET",
                                                                      "access-control-request-headers": "authorization"}).status_code, 200)
        check("origem estranha é recusada", c.options("/estado", headers={**fora, "origin": "https://invasor.example",
                                                                          "access-control-request-method": "GET"}).status_code, 400)
        # 429 por último: bloqueia o IP do cenário e envenenaria os checks acima
        for _ in range(api.AUTH_MAX_FALHAS):
            c.get("/estado", headers={**cross, "authorization": "Basic eGX6"})
        r429 = c.get("/estado", headers=cross)
        check("429 do throttle devolve ACAO", (r429.status_code, acao(r429)), (429, ORIGEM))
    else:
        check("GET /estado de fora", c.get("/estado", headers=fora).status_code, 503)
        check("POST /reset de fora", c.post("/reset", json={"confirmar": "RESET"}, headers=fora).status_code, 503)
        check("GET / de fora", c.get("/", headers=fora).status_code, 503)
        r503 = c.get("/estado", headers={**fora, "origin": ORIGEM})
        check("503 devolve ACAO (front vê o motivo, não erro de CORS)",
              r503.headers.get("access-control-allow-origin"), "*")
        check("GET /estado local direto (dev sem senha segue funcionando)", c.get("/estado").status_code, 200)
    return ok


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sys.exit(0 if rodar(sys.argv[1]) else 1)
    falhou = [c for c in CENARIOS
              if subprocess.run([sys.executable, __file__, c], cwd=os.path.dirname(os.path.abspath(__file__))).returncode]
    print("FALHOU: " + ", ".join(falhou) if falhou else "OK — todos os cenários passaram")
    sys.exit(1 if falhou else 0)
