# Deploy no Railway (validação) — passo a passo

App: FastAPI + worker do bot (loop 24/7) + SQLite. Roda 1 instância sempre ligada,
com volume persistente pro banco e login básico. Custo ~US$5/mês (plano Hobby).

## Pré-requisitos
- Conta no Railway (railway.app) — plano Hobby (~US$5/mês; sem free tier).
- Node instalado (pra CLI). Alternativa: dá pra fazer tudo pelo dashboard web.

## 1) Instalar e logar na CLI
```bash
npm i -g @railway/cli
railway login
```

## 2) Criar o projeto (na pasta do app)
```bash
cd "c:/Users/aboni/Pesquisas/1"
railway init          # cria um projeto novo no Railway
```

## 3) Criar o VOLUME persistente (CRUCIAL — senão o banco some a cada deploy)
No dashboard do Railway → seu serviço → aba **Volumes** → **New Volume**:
- Mount path: `/data`

## 4) Variáveis de ambiente (serviço → aba Variables)
| Variável     | Valor                          | Pra quê                                   |
|--------------|--------------------------------|-------------------------------------------|
| `DB_PATH`    | `/data/trading.db`             | banco no volume persistente               |
| `DASH_USER`  | (escolha um usuário)           | login do dashboard                        |
| `DASH_PASS`  | (escolha uma senha FORTE)      | senha do dashboard (ativa o login básico) |
| `PORT`       | (automático — não precisa criar)| porta que o Railway injeta                |

> Sem `DASH_PASS`, o app fica SEM senha. Em produção pública, sempre defina.

## 5) Healthcheck (opcional, recomendado)
Serviço → Settings → **Health Check Path**: `/health` (livre de login, retorna ok).

## 6) Deploy
```bash
railway up            # sobe a pasta atual e builda (lê requirements.txt + Procfile)
```
O start é o `Procfile`: `uvicorn api:app --host 0.0.0.0 --port $PORT`.

## 7) Abrir
```bash
railway domain        # gera uma URL pública
```
Abra a URL → o navegador pede usuário/senha (DASH_USER/DASH_PASS). Pronto.

## Depois do deploy — IMPORTANTE
- O banco no servidor **nasce limpo**: banca R$1000, **bot DESLIGADO**, settings padrão.
  (O histórico local NÃO vai junto — `trading.db` está no `.gitignore`.)
- No painel **🤖 Auto-trade**, **ligue o bot** e ajuste o que quiser (máx posições, etc.).
- Trailing stop e alavancagem∝convicção já vêm ligados por padrão.

## Cuidados
- **1 instância só** (não escale réplicas): o worker é singleton + SQLite. Replica = 2 bots + conflito.
- **Não exponha sem `DASH_PASS`** — `/reset`, `/panico` e `/auto` mexem no estado.
- Migrar pra VPS depois (quando sair da validação) é fácil: mesma stack, só copiar o `trading.db` do volume.
