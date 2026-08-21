# Plano de execução — os 35 cards abertos

**Data:** 2026-08-20 · **Origem:** investigação de 2026-08-19 (`STATUS-SISTEMA`,
`INVESTIGACAO-LOGICA`, `INVESTIGACAO-TRADING`) · **Quadro:** [Trello Trading Bot](https://trello.com/b/haBYRC0E/trading-bot)

> **Documento auto-contido.** A sessão que for executar não tem o histórico da conversa onde ele
> nasceu. Leia até a §3 antes de pegar qualquer card.

---

## 1. Que fase é esta

O `PLANO-SPRINTS.md` (2026-06-10) é o plano de **construção** — Sprints 0 a 8. Os Sprints 0-7
estão entregues e rodando em produção; só o Sprint 8 (camada LLM) nunca foi feito, e era opcional.

Estes 35 cards **não são o Sprint 9**. O sistema foi construído e a investigação de 2026-08-19
descobriu que **ele mente**: engole erro de rede em silêncio, zera funding sem avisar, valida a
estratégia errada. É uma fase de natureza oposta à de construir — e por isso se planeja diferente.

## 2. Por que marcos com portão, e não sprints com prazo

**Descartado: sprint com caixa de tempo.**

1. **A velocidade é imprevisível por natureza.** O `[P1-3]` são duas linhas (`min(limite, 500)`).
   O `[P1-10]` é revalidar a estratégia que está viva porque o veredito "sem edge" mediu outra —
   dias de pesquisa, com resposta desconhecida. Os dois na mesma sprint de duas semanas é ficção.
2. **Não existe crédito parcial.** Metade de uma guarda de risco é uma guarda desligada. Metade de
   um card de pesquisa não ensina nada.
3. **Não há quem sincronizar.** Sprint serve pra alinhar um time. Aqui é uma pessoa com agentes.
4. **O quadro já modela fluxo.** As listas do Trello são *estado*
   (Triagem → Priorizado → Fazendo → Validando → Feito), decisão deliberada. Sprint seria um
   segundo eixo brigando com o primeiro.

**Adotado: marco com portão.** Cada marco é **uma frase que passa a ser verdade e continua
verdade**, com portão verificável por comando — mesmo estilo dos critérios de aceite dos cards.
Avança-se quando o portão passa, não quando chega sexta.

**O agrupamento não é por área** (backend/front/lógica). É por **dependência epistêmica** — o que
precisa ser verdade pra próxima coisa significar alguma coisa:

```
guardas          →  instrumentos           →  régua
o sistema vivo      os números que ele         a validação pode estar
pode se machucar    te mostra podem ser        medindo a estratégia
                    mentira                    errada
```

É uma corrente, não três gavetas. Não adianta consertar a régua se o P&L que ela lê tem funding
zerado por engano (`[P2-10]`). Separar por backend/front/lógica quebraria a corrente no meio.

**No Trello:** labels `M1`…`M5`, somadas às de prioridade e área. As listas continuam sendo estado.
Filtre por `label:` para ver um marco. Descartados: listas por sprint (destrói lista=estado) e
datas de entrega (implica prazo).

---

## 3. Os marcos

### 🛡️ M1 — "Posso deixar rodando sem olhar" · 8 cards

O sistema está no ar **agora**, com posições abertas, sem ninguém olhando. Menor marco, mais urgente.

| Card | Assunto |
|---|---|
| **`[P1-1]`** ⭐ | Falha de rede paralisa o ciclo — a posição fica sem stop, sem trailing, sem checagem de liquidação |
| `[P1-6]` | Confirmar o mesmo sinal 2× abre duas posições |
| `[P1-7]` | `/panico` fecha tudo mas deixa o auto-trader ligado — kill-switch que se desmata |
| `[P1-8]` | `POST /config` aceita qualquer valor; um typo derruba `/estado` e o worker |
| `[P2-12]` | `/reset` não limpa a trava diária |
| `[P2-14]` | Recusa por teto de margem vira HTTP 500 no `/confirmar` |
| `[P2-2]` | Sem backup do `trading.db` — perda de dado é irreversível |
| `[P1-3]` | `/trades?limite` sem teto |

**Portão:** derrubar a rede da VM por 5 min com posição aberta → o ciclo continua, a posição segue
vigiada, o `/status` denuncia. E existe backup de ontem **fora** da VM.

**Ligar aqui, colher no M4:** a instrumentação do `[P2-22]` (validação prospectiva do portão de
fluxo) precisa de tempo de mercado acumulando. É o único card que não dá pra comprimir depois.

### 📏 M2 — "O que eu leio é medição, não chute" · 11 cards

Todo número que o M4 vai usar nasce aqui.

| Card | Assunto |
|---|---|
| **`[P2-10]`** ⭐ | Falha de rede zera o funding silenciosamente — corrompe o P&L que a pesquisa lê |
| `[P2-9]` | Portão de fluxo falha-aberto: `book()` indisponível deixa o sinal passar sem checagem |
| `[P1-9]` | Dedupe sem janela temporal seca a fila de sinais; sinais `novo` nunca expiram |
| `[P2-15]` | `ultimo_erro` nunca é limpo; a cadência do scan deriva quando o ciclo falha |
| `[P2-11]` | Tabela `equity` sem limite, sem índice, gráfico mostra só ~2h |
| `[P1-5]` | `breadth()` conta o ativo antes de a soma poder falhar |
| `[P1-4]` | `_amostrar()` não reduz nada entre 126 e 249 pontos |
| `[P2-13]` | `/estado` dispara rede por plano DCA a cada poll de 3s |
| `[P2-3]` | A VM não é repositório git — não se sabe qual commit está rodando |
| `[P2-1]` | Sem rotação de log |
| `[P2-5]` | RAM: VM é `B2ats_v2` (1 GiB); `B2als_v2` (4 GiB) está liberado na mesma região |

**Portão:** todo número no painel ou é medido, ou está declaradamente ausente — nenhum é um zero
que na verdade é um erro engolido.

### 🧱 M3 — "Um agente novo não quebra o que não entende" · 3 cards

`[P2-17]` CLAUDE.md + ARQUITETURA.md · `[P2-6]` testes rodando · `[P2-16]` organizar o repo e
matar o config duplo (`config.py` × `db.CONFIG_PADRAO`)

**Está no meio, não no fim, de propósito.** Daqui pra frente o trabalho é pesado — M4 é pesquisa,
M5 é redesign — e será tocado por agentes em sessões novas, sem o histórico. Sem CLAUDE.md e sem
teste, cada sessão re-deriva as convenções e reintroduz os bugs que o M1 e o M2 fecharam.

**Ordem obrigatória:** o `[P2-16]` mexe em 50+ arquivos. Só pode acontecer **depois** do `[P2-3]`
(saber o que está deployado) e **depois** do M1 (não quebrar a guarda enquanto move arquivo).

**Portão:** sessão nova, prompt frio, faz um fix — e o teste pega uma regressão plantada de propósito.

### 🔬 M4 — "A régua mede a estratégia que eu opero" · 10 cards

Aqui mora a pergunta que justifica o projeto.

| Card | Assunto |
|---|---|
| **`[P1-10]`** ⭐⭐ | A política de saída viva nunca foi backtestada — o veredito "sem edge" mediu outra estratégia |
| `[P2-19]` | Implementar os consertos da régua de validação (Item 1 revisado) |
| `[P2-20]` | Aposentar `tune.py` e `validar_oos.py` — vereditos pela metodologia já descartada |
| `[P2-23]` | Paridade de portfólio: o vivo é multi-ativo com slots e tetos, o backtest é isolado |
| `[P2-24]` | Micro-realismo do modelo de execução |
| `[P2-18]` | Fill otimista no stop ao vivo — paper superestima |
| `[P1-11]` | Alavancagem por convicção ignora a geometria stop × liquidação |
| `[P2-8]` | Piso de R$10 no sizing fura o `risco_por_trade` em banca pequena |
| `[P2-21]` | Defaults de risco contradizem a base de conhecimento |
| `[P2-22]` | Validação prospectiva do portão de fluxo (instrumentado no M1) |

**Portão:** rodar a validação corrigida sobre a política que está **viva** e ter um veredito de edge
em que se aposta. É o único marco cujo resultado pode ser *"o projeto muda de direção"*.

### 🎨 M5 — Front · 2 cards · **paralelo aos demais**

`[P1-2]` credencial descartada a cada F5 · Implementação de novo front-end

O `PLANO-FRONTEND-REDESIGN.md` restringe o escopo a `web/index.html`, zero mudança de backend. É o
único bloco sem dependência de M1-M4 e sem arquivo compartilhado — roda numa sessão separada.

⚠️ **Colisão conhecida:** o `[P2-14]` (M1) toca o tratamento de erro do front, e o redesign
reescreve o front. Ou o `[P2-14]` entra antes, ou vira requisito dentro do redesign.

---

## 4. Ordem de execução

```
M1 ──► M2 ──► M3 ──► M4          (a corrente epistêmica)
 │
 └──► M5 em paralelo, sessão separada
```

Decidido em 2026-08-20, com a alternativa considerada e recusada: **furar a fila e ir direto ao
`[P1-10]` depois do M1**. Recusada porque o M4 lê números que o M2 conserta — funding zerado
(`[P2-10]`), fill otimista no stop (`[P2-18]`), portão falha-aberto (`[P2-9]`). Fazer a pesquisa
antes é arriscar um segundo veredito inválido, que é exatamente o erro que o `[P1-10]` denuncia.

---

## 5. Regras de execução

- **Um card por vez em 🔨 Fazendo.** O quadro é estado real, não intenção.
- **Card fechado = commit + portão verificado.** O comentário de fechamento cita o commit e o
  comando que provou o critério de aceite.
- **Nada pula de Fazendo direto pra Feito** se o efeito é observável em produção: passa por
  🔍 Validando, e a evidência vai no card (foi assim que o `[P0-2]` fechou).
- **Card que mexe em guarda de risco** (label `toca-risco`) não relaxa invariante sem decisão
  humana explícita registrada no card.

---

## 6. Estado em 2026-08-20

| Lista | Cards |
|---|---|
| ✅ Feito | 3 — `[P0-2]`, `[P2-4]`, `[P2-7]` |
| 🔍 Validando em produção | 2 — `[P0-1]`, `[P1-2]` |
| 🎯 Priorizado | 1 — `[P1-1]` |
| 📥 Triagem | 32 |

Produção: VM em `southafricanorth`, backend atrás de autenticação, scan saudável, worker rodando
com posições abertas e banca fictícia acima da inicial.

**Próximo card:** `[P1-1]` — é o único em Priorizado, abre o M1, e é o que morde primeiro com
posição aberta em produção.
