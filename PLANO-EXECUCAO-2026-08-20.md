# Plano de execução — os 35 cards abertos

**Data:** 2026-08-20 · **Origem:** investigação de 2026-08-19 (`STATUS-SISTEMA`,
`INVESTIGACAO-LOGICA`, `INVESTIGACAO-TRADING`) · **Quadro:** [Trello Trading Bot](https://trello.com/b/haBYRC0E/trading-bot)

> ⚠️ **Renumeração de 2026-08-22.** Os cards de pesquisa quant deste plano eram `P2-19..24`.
> A série do redesign do front (M5/M6) reusou esses mesmos números, e por seis dias dois cards
> diferentes responderam por cada um. A série quant moveu-se para **`Q-1..34`** — está sem
> trabalho em curso, enquanto a do front já vive em mensagens de commit, que não se reescrevem.
> A primeira tentativa moveu a série quant para `P2-29..34` e colidiu **de novo** no mesmo dia:
> outra sessão criava os cards do M6 exatamente nessa faixa ao mesmo tempo. A lição é que `P2-` é
> uma sequência compartilhada e duas sessões numerando em paralelo vão colidir sempre. Por isso a
> pesquisa quant saiu da sequência e ganhou prefixo `Q-`.
>
> **A chave canônica de um card é o shortLink do Trello, nunca o número do título.** Qualquer
> automação — auditor de frota inclusive — que resolva card por `[P2-n]` está construída sobre
> areia.
>
> **Documento auto-contido e único.** A sessão que for executar não tem o histórico da conversa
> onde ele nasceu. É a fonte única do plano — se algum outro doc contradisser este, este vale.
> Leia até a §5 antes de despachar qualquer agente.

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
   (Triagem → Priorizado → Fazendo → Validando → Feito), decisão deliberada.

**Adotado: marco com portão.** Cada marco é **uma frase que passa a ser verdade e continua
verdade**, com portão verificável por comando. Avança-se quando o portão passa, não quando chega sexta.

**O agrupamento não é por área** (backend/front/lógica). É por **dependência epistêmica**:

```
guardas          →  instrumentos           →  régua
o sistema vivo      os números que ele         a validação pode estar
pode se machucar    te mostra podem ser        medindo a estratégia
                    mentira                    errada
```

É uma corrente, não três gavetas. Não adianta consertar a régua se o P&L que ela lê tem funding
zerado por engano (`[P2-10]`).

**No Trello:** labels `M1`…`M5`, somadas às de prioridade e área. Listas continuam sendo estado.

---

## 3. A restrição que manda no despacho: colisão de arquivo

Os 35 cards não se distribuem uniformemente pelo código. Contagem real, extraída das citações
`arquivo:linha` dos três documentos de investigação:

| Arquivo | Cards que o tocam |
|---|---|
| **`api.py`** | **10** — P0-1, P1-1, P1-3, P1-4, P1-7, P1-8, P2-11, P2-12, P2-14, P2-15 |
| **`simulador.py`** | **6** — P1-1, P1-6, P1-8, P2-10, P2-14, P2-18 |
| `validacao.py` | 4 — P1-11, P2-8, P2-10, Q-1 |
| `signal_engine.py` | 3 — P1-9, P2-9, P2-15 |
| `trading.db` | 3 — P0-1, P2-2, Q-1 |
| `autotrader.py`, `tune.py`, `validar_oos.py`, `web/index.html` | 2 cada |
| `mercado.py`, `dca.py`, `db.py`, `logbot.py`, `scoring.py`, `config.py`, `live_engine.py`, `test_sim.py` | 1 cada |

**Consequência direta: não despache um agente por card.** Sete agentes paralelos no M1 seriam
sete edições concorrentes em `api.py` — conflito garantido, e cada um revisando um arquivo que os
outros seis estão mudando debaixo dele.

**A unidade de despacho é o território de arquivo.** Um agente é dono de um conjunto de arquivos e
resolve **todos** os cards daquele território numa passada, num commit por card. Dentro de uma
onda, dois agentes nunca compartilham arquivo.

---

## 4. Os marcos e suas ondas de despacho

Legenda: `‖` = rodam em paralelo · `▸` = onda seguinte, só começa quando a anterior fecha.

### 🛡️ M1 — "Posso deixar rodando sem olhar" · 8 cards

O sistema está no ar **agora**, com posições abertas, sem ninguém olhando. Menor marco, mais urgente.

**Onda 1** — dois agentes em paralelo:

**`T-API-GUARDA`** · dono de `api.py` + `simulador.py` · 7 cards, nesta ordem:

| Card | Onde | O quê |
|---|---|---|
| **`P1-1`** ⭐ | `simulador.py:208` | `preco_ao_vivo()` no `for` sem try/except: uma falha de rede paralisa o ciclo inteiro e a posição fica sem stop, sem trailing, sem checagem de liquidação |
| `P1-6` | `simulador.py:117-120` | `abrir()` não checa o status do sinal — confirmar 2× abre duas posições |
| `P1-7` | `api.py:369-382` | `/panico` fecha tudo mas não desliga o auto-trader; reabre em ~15s |
| `P1-8` | `api.py:404-408` → `simulador.py:76-77` | `POST /config` sem validação: um `risco_por_trade:"abc"` derruba `/estado` e o worker |
| `P2-12` | `api.py:236-242` | `/reset` não limpa `trava_dia_em` nem decide sobre o DCA |
| `P2-14` | `api.py:349-366`, `simulador.py:142-146` | recusa por teto de margem vira HTTP 500 no `/confirmar` |
| `P1-3` | `api.py:296`, `/candles` | `limite` sem teto — capar em `min(limite, 500)` |

**`T-INFRA-BACKUP`** ‖ · dono de `deploy/` e da VM · 1 card:

| Card | O quê |
|---|---|
| `P2-2` | Backup do `trading.db` — cron diário com `sqlite3 .backup` + cópia pra fora da VM |

**Ligar aqui, colher no M4:** a instrumentação do `[Q-4]` (log do portão de fluxo por decisão +
desfecho hipotético) precisa de tempo de mercado acumulando. É o único card que não dá pra
comprimir depois — se ficar pro M4, você espera semanas paradas. **Sai junto com o `T-API-GUARDA`.**

**Portão do M1:** derrubar a rede da VM por 5 min com posição aberta → o ciclo continua, a posição
segue vigiada, o `/status` denuncia. E existe backup de ontem **fora** da VM.

---

### 📏 M2 — "O que eu leio é medição, não chute" · 11 cards

Todo número que o M4 vai usar nasce aqui.

**Onda 1** — quatro agentes em paralelo, zero arquivo em comum:

| Agente | Arquivos | Cards |
|---|---|---|
| **`T-SINAL`** | `signal_engine.py`, `autotrader.py`, `api.py:54` (só leitura do `ultimo_scan`) | `P2-9` portão de fluxo falha-aberto · `P1-9` dedupe sem janela seca a fila e sinal `novo` nunca expira · `P2-15` `ultimo_erro` nunca limpo e cadência deriva |
| **`T-EXEC`** ‖ | `simulador.py`, `validacao.py` | **`P2-10`** ⭐ falha de rede zera o funding em silêncio (`except: return 0.0`) — corrompe o P&L que a pesquisa lê |
| **`T-MERCADO`** ‖ | `mercado.py`, `dca.py` | `P1-5` `breadth()` conta o ativo antes de a soma poder falhar · `P2-13` `/estado` dispara rede por plano DCA a cada poll de 3s |
| **`T-OPERACAO`** ‖ | `logbot.py`, `deploy/`, VM | `P2-1` rotação de log · `P2-3` a VM não é repo git, não se sabe qual commit roda · `P2-5` RAM (`B2als_v2` 4 GiB está liberado na mesma região, `az vm resize`) |

**Onda 2** ▸ — sozinho, porque `api.py` é território do `T-SINAL` na onda 1:

| Agente | Arquivos | Cards |
|---|---|---|
| **`T-API-DADOS`** | `api.py`, `db.py` | `P2-11` equity sem limite, sem índice, gráfico de ~2h · `P1-4` `_amostrar()` não reduz nada entre 126 e 249 pontos |

**Portão do M2:** todo número no painel ou é medido, ou está declaradamente ausente — nenhum é um
zero que na verdade é um erro engolido.

---

### 🧱 M3 — "Um agente novo não quebra o que não entende" · 3 cards

**Está no meio, não no fim, de propósito.** Daqui pra frente o trabalho é pesado — M4 é pesquisa,
M5 é redesign — e será tocado por agentes em sessões novas, sem histórico. Sem CLAUDE.md e sem
teste, cada sessão re-deriva as convenções e reintroduz os bugs que o M1 e o M2 fecharam.

**Serial, nas três ondas — e a ordem importa:**

1. **`P2-6`** — pytest instalado e rodando, `test_sim.py` verde. *Primeiro, porque vira a rede de
   segurança da mudança seguinte.*
2. **`P2-16`** ▸ — organizar o repo (plataforma × pesquisa × legado) e **matar o config duplo**
   (`config.py` dataclass legado × `db.CONFIG_PADRAO`, o real). **Agente sozinho, nada em
   paralelo** — mexe em 50+ arquivos e move o chão de todo mundo.
3. **`P2-17`** ▸ — `CLAUDE.md` + `ARQUITETURA.md`. *Por último, para documentar a estrutura final
   em vez de escrever contra um layout que o passo 2 vai destruir.*

**Ordem obrigatória, não preferencial:** o `P2-16` só pode rodar **depois do `P2-3`** (M2 — saber
o que está deployado) e **depois do M1** (não quebrar a guarda enquanto move arquivo). Hoje o
deploy é cópia manual: mover 50 arquivos sem saber qual commit está na VM é como o deploy vira
irreconciliável.

**Portão do M3:** sessão nova, prompt frio, faz um fix — e o teste pega uma regressão plantada de propósito.

---

### 🔬 M4 — "A régua mede a estratégia que eu opero" · 10 cards

Aqui mora a pergunta que justifica o projeto.

**Onda 1** — três agentes em paralelo:

| Agente | Arquivos | Cards |
|---|---|---|
| **`T-REGUA`** | `validacao.py`, `tune.py`, `validar_oos.py`, `scoring.py`, `autotrader.py` | `Q-1` consertos da régua (Item 1 revisado) · `Q-2` aposentar `tune.py`/`validar_oos.py` · `P1-11` cap geométrico de alavancagem (liq antes do stop em alts 1h) · `P2-8` piso de R$10 fura o `risco_por_trade` |
| **`T-EXEC-REAL`** ‖ | `simulador.py`, `backtest*.py` | `P2-18` fill otimista no stop ao vivo · `Q-6` micro-realismo do modelo de execução |
| **`T-DECLARACAO`** ‖ | docs, config | `Q-3` defaults de risco contradizem a base de conhecimento — alinhar ou declarar o experimento |

> Os quatro cards do `T-REGUA` estão juntos porque **todos tocam `validacao.py`**. Separá-los em
> agentes paralelos é o erro que a §3 descreve.

**Onda 2** ▸ · **`T-PORTFOLIO`** — `Q-5` paridade de portfólio: o vivo é multi-ativo/multi-TF com
slots, cooldown e tetos; o backtest é por-ativo isolado, 1 posição, tamanho fixo.

**Onda 3** ▸ · **`P1-10`** ⭐⭐ **sozinho, com tudo acima pronto** — a política de saída viva nunca
foi backtestada; o veredito "sem edge" mediu outra estratégia. Junto conclui o **`Q-4`**
(instrumentado lá no M1).

**Portão do M4:** rodar a validação corrigida sobre a política que está **viva** e ter um veredito
de edge em que se aposta. É o único marco cujo resultado pode ser *"o projeto muda de direção"*.

---

### 🎨 M5 — Front · 2 cards · **paralelo a tudo, desde o dia 1**

Sessão separada. Território exclusivo: **`web/index.html`**. Zero mudança de backend, endpoint ou
dado — o `PLANO-FRONTEND-REDESIGN.md` é um handoff auto-contido e já trava as decisões de direção.

1. `P1-2` — apagar o `localStorage.removeItem('cbAuth')` de `web/index.html:881`. Uma linha.
2. Implementação do novo front-end — seguir o `PLANO-FRONTEND-REDESIGN.md` inteiro.

⚠️ **Colisão conhecida:** o `P2-14` (M1) muda o tratamento de erro do `/confirmar`, que o front
exibe — e o redesign reescreve o front. Ou o `P2-14` entra antes, ou o requisito dele vira item do
redesign. **Decidir antes de soltar o agente do M5**, não durante.

---

## 5. Ordem geral

```
M1 ──► M2 ──► M3 ──► M4          (a corrente epistêmica)
 │
 └──► M5 em paralelo, sessão separada
```

Decidido em 2026-08-20, com a alternativa considerada e **recusada**: furar a fila e ir direto ao
`[P1-10]` depois do M1. Recusada porque o M4 lê números que o M2 conserta — funding zerado
(`P2-10`), fill otimista no stop (`P2-18`), portão falha-aberto (`P2-9`). Fazer a pesquisa antes é
arriscar um segundo veredito inválido, que é exatamente o erro que o `P1-10` denuncia.

---

## 6. Como despachar um agente

Um agente = um território = uma sessão. Modelo de prompt:

```
Você é dono do território <T-NOME> do M<n> do PLANO-EXECUCAO-2026-08-20.md.

Leia primeiro, nesta ordem:
  1. PLANO-EXECUCAO-2026-08-20.md  (§3 colisão de arquivo, §4 seu marco, §7 regras)
  2. CLAUDE.md e ARQUITETURA.md    (se já existirem — M3)
  3. O documento de investigação do seu card:
       STATUS-SISTEMA-2026-08-19.md        (P0-*, P1-1..5, P2-1..7)
       INVESTIGACAO-LOGICA-2026-08-19.md   (P1-6..9, P2-8..18)
       INVESTIGACAO-TRADING-2026-08-19.md  (P1-10..11, Q-1..24)

Seus arquivos: <lista>. NÃO edite nenhum arquivo fora dessa lista — outro agente
é dono dele nesta mesma onda. Se precisar de um, pare e reporte.

Seus cards, nesta ordem: <lista com file:linha>

Para cada card: um commit, mensagem explicando a causa (não o sintoma), e o
comando que prova o critério de aceite rodado e colado no resultado.
```

## 7. Regras de execução

- **Um card por vez em 🔨 Fazendo** no Trello. O quadro é estado real, não intenção.
- **Dentro de uma onda, agente nenhum toca arquivo de outro.** Se precisar, a onda estava errada:
  pare e re-planeje, não edite.
- **Card fechado = commit + portão verificado.** O comentário de fechamento cita o commit e o
  comando que provou o critério de aceite.
- **Nada pula de Fazendo direto pra Feito** se o efeito é observável em produção: passa por
  🔍 Validando com a evidência no card (foi assim que o `P0-2` fechou).
- **Card com label `toca-risco` não relaxa invariante** sem decisão humana explícita registrada no
  card. São eles: P0-1, P1-1, P1-6, P1-7, P1-10, P1-11, P2-2, P2-8, P2-18, Q-3.
- **O deploy ainda é cópia manual** até o `P2-3` fechar. Commit na `main` **não** significa que a
  VM está rodando aquilo.

---

## 8. Estado em 2026-08-20

| Lista | Cards |
|---|---|
| ✅ Feito | 3 — `P0-2`, `P2-4`, `P2-7` |
| 🔍 Validando em produção | 2 — `P0-1`, `P1-2` |
| 🎯 Priorizado | 1 — `P1-1` |
| 📥 Triagem | 32 |

Produção: VM em `southafricanorth`, backend atrás de autenticação, scan saudável, worker rodando
com posições abertas e banca fictícia acima da inicial.

**Primeiro despacho:** `T-API-GUARDA` e `T-INFRA-BACKUP` em paralelo, abrindo o M1. E o `M5` numa
sessão separada, se o `P2-14` já estiver decidido.
