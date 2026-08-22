# Plano de execução — os 35 cards abertos

**Data:** 2026-08-20 · **Origem:** investigação de 2026-08-19 (`STATUS-SISTEMA`,
`INVESTIGACAO-LOGICA`, `INVESTIGACAO-TRADING`) · **Quadro:** [Trello Trading Bot](https://trello.com/b/haBYRC0E/trading-bot)

> ⚠️ **Renumeração de 2026-08-22.** Os cards de pesquisa quant deste plano eram `P2-19..24`.
> A série do redesign do front (M5/M6) reusou esses mesmos números, e por seis dias dois cards
> diferentes responderam por cada um. A série quant moveu-se para **`Q-1..6`** — está sem
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
| `db.py` | 2 — P2-11, **Q-4** |
| `mercado.py`, `dca.py`, `logbot.py`, `scoring.py`, `config.py`, `live_engine.py`, `test_sim.py` | 1 cada |

> **Q-4 não tem citação `arquivo:linha` nos documentos de investigação** — é instrumentação a
> escrever, não bug a consertar, então esta tabela (extraída das citações) não o via. Território
> declarado abaixo, na §4. Um card sem território na §4 **não é despachável**: o portão de
> fronteira é `git diff --name-only <base>...<branch>` cruzado com a lista desta seção, e sem
> lista não há contra o que conferir. O briefing do agente não serve como fonte — ele não é lido
> por quem audita.

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

**`T-FLUXO-LOG`** ‖ · dono de `signal_engine.py` + `db.py` · 1 card:

| Card | O quê |
|---|---|
| `Q-4` | Instrumentar o portão de fluxo: log de cada decisão + desfecho hipotético, para a validação prospectiva do M4 |

**Por que este card sai no M1 e não no M4:** a validação prospectiva precisa de tempo de mercado
acumulando e não dá pra comprimir depois — se ficar pro M4, você espera semanas paradas. O que
sai agora é só a instrumentação; a conclusão é do M4.

⚠️ **Cruzamento M1↔M2:** `db.py` é do `T-API-DADOS` na onda 2 do M2 (`P2-11`, índices e poda da
tabela `equity`). Enquanto os marcos correrem em série não há conflito — mas os dois cards mexem
no esquema do banco, e quem chegar depois lê o que o primeiro deixou. Não despache os dois juntos.

**Portão do M1:** derrubar a rede da VM por 5 min com posição aberta → o ciclo continua, a posição
segue vigiada, o `/status` denuncia. E existe backup de ontem **fora** da VM.

---

### 📏 M2 — "O que eu leio é medição, não chute" · 11 cards

Todo número que o M4 vai usar nasce aqui.

> **Redesenho das ondas em 2026-08-22 (sessão-matriz do M2).** A tabela original tinha quatro
> agentes na onda 1 e violava duas regras desta mesma seção. O que mudou, e por quê, está na
> §4b logo abaixo — leia antes de despachar. A tabela abaixo é a que vale.

**Onda 1** — três agentes em paralelo, zero arquivo em comum (teto da §9.11):

| Agente | Arquivos | Cards |
|---|---|---|
| **`T-SINAL`** | `signal_engine.py`, `autotrader.py` | `P2-9` (`KEfRnQO7`) portão de fluxo falha-aberto · `P1-9` (`LQeuj96h`) dedupe sem janela seca a fila e sinal `novo` nunca expira |
| **`T-EXEC`** ‖ | `simulador.py`, `validacao.py` | **`P2-10`** ⭐ (`EeldhcE8`) falha de rede zera o funding em silêncio (`except: return 0.0`) — corrompe o P&L que a pesquisa lê |
| **`T-MERCADO`** ‖ | `mercado.py`, `dca.py`, `logbot.py` | `P1-5` (`oEN0olMs`) `breadth()` conta o ativo antes de a soma poder falhar · `P2-13` (`1hPdf23i`) `/estado` dispara rede por plano DCA a cada poll de 3s · `P2-1` (`et5Nuyar`) rotação de log |

**Faixa da matriz, em paralelo à onda 1** — não é worker, é a própria matriz: worker não acessa a
VM (`CLAUDE.md` §6, `ORQUESTRACAO-ORCA.md` §1).

| Quem | Arquivos | Cards |
|---|---|---|
| **matriz** | `deploy/`, VM, Azure | `P2-3` (`ky3fu2DX`) a VM não é repo git — clone, script de deploy, rollback testado · `P2-5` (`pssY5yi2`) medir RAM sob scan real; o `az vm resize` para `B2als_v2` sai do tier gratuito e **é decisão do dono**, não da matriz |

**Onda 2** ▸ — sozinho, porque `api.py` é lido pela onda 1 inteira e escrito só aqui:

| Agente | Arquivos | Cards |
|---|---|---|
| **`T-API-DADOS`** | `api.py`, `db.py`, `signal_engine.py` | `P2-11` (`FUNR7eDR`) equity sem limite, sem índice, gráfico de ~2h · `P1-4` (`vUnnjyx6`) `_amostrar()` não reduz nada entre 126 e 249 pontos · `P2-15` (`3iUCAXf9`) `ultimo_erro` nunca limpo e cadência deriva · **duas linhas herdadas**: o `/health` com o commit em produção (fecha o `P2-3`) e a exposição do contador de falhas de funding no `/status` (fecha o `P2-10`) |

**Portão do M2:** todo número no painel ou é medido, ou está declaradamente ausente — nenhum é um
zero que na verdade é um erro engolido.

> ### ✅ Portão do M2 — RODADO em 2026-08-22, sobre a `main` mesclada e depois em produção
>
> Merges: `27856ea` (T-SINAL), `c911786` (T-MERCADO), `6f2d7bb` (T-EXEC), `6f166fa` (T-API-DADOS).
> Deploy na VM pelo `cripto-deploy`: `f3d2ce9 → 7c65df1`, com backup, congelamento, compilação no
> venv de produção, restart e verificação. **110 asserções verdes** sobre a `main` completa
> (`prova_m1.py` 7, `simulador.py` 11, `db.py prova` 18, `api.py` 27, e três auditorias
> independentes da matriz: 22, 18 e 7).
>
> A frase do portão tem forma mecânica — varredura do repositório atrás de `except` que devolve
> zero, fora de teste e backtest. **Restou uma ocorrência**, `autotrader.ts_val()`, e ela está
> certa: o zero é chave de ordenação em empate, não número que alguém lê. Nenhuma outra.
>
> Cada número do painel, e o que o torna honesto:
>
> | Número | Antes | Agora | Card |
> |---|---|---|---|
> | funding no P&L | `except: return 0.0` — zero falso gravado no banco | `None` no código, `NULL` no banco, `n/d` no log | `P2-10` |
> | fluxo do sinal | portão pulado em silêncio | `"fluxo n/d"` nos motivos + `scan.fluxo_indisponivel` | `P2-9` |
> | `breadth` | ativo entrava em `tot` antes de ter valor | só quem respondeu conta; falha total → `None` | `P1-5` |
> | `ultimo_erro` | erro de horas atrás exibido como atual | zerado a cada scan; forense em `ultimo_erro_historico` | `P2-15` |
> | cadência do scan | contava ciclos executados | agendada por relógio, reagendada antes de rodar | `P2-15` |
> | curva de equity | últimas 500 linhas = 125 min | história inteira, rareada — 126 pontos cobrindo 2d16h | `P2-11`+`P1-4` |
> | commit em produção | não havia | `/health` devolve o SHA, ou `None` declarado | `P2-3` |
>
> Produção depois do deploy:
> ```json
> "scan":    {"total": 72, "ok": 72, "falhas": 0, "ultimo_erro": null,
>             "fluxo_indisponivel": 0, "ultimo_erro_historico": null}
> "funding": {"medidos": 0, "falhas": 0, "ultimo_erro": null}
> "saudavel": true
> /sentimento.breadth: {"pct_subindo": 83, "variacao_media": 2.81, "n": 24}
> /estado.equity_hist: 126 pontos, de 2026-08-19 21:34 a 2026-08-22 14:30
> /health: {"status":"ok","versao":"0.3","commit":"7c65df11c6f2..."}
> ```
>
> **Três cards ficam em 🔍 Validando, e não por falta de prova: por falta de evento.** O `P1-9`
> precisa de um pendente passar da janela, o `P2-10` de um trade fechar, o `P2-15` de uma falha
> de rede acontecer. Os critérios estão provados por comando; o que falta é o mercado.
>
> **Um card fica em 🔨 Fazendo:** o `P2-5`. A medição foi feita e **falhou** nos dois critérios
> (pico 600 MB = 64% dos 892 MiB, contra os 60% pedidos; swap com 112 MiB em uso). O resize para
> `B2als_v2` sai do tier gratuito do Students, e gasto é decisão do dono — o auditor para e
> entrega o parecer (§9.8 em espírito). Anotado junto: o `MemoryMax` do service é `900M` numa VM
> de 892 MiB, ou seja, **acima da RAM física** — não protege nada, e o OOM killer chega antes.

#### 4b. Por que as ondas do M2 mudaram

Quatro correções, todas por regra escrita neste documento — nenhuma por preferência:

1. **`T-OPERACAO` foi dissolvido.** Ele era dono de "`logbot.py`, `deploy/`, VM", e o worker não
   acessa a VM. Dois dos seus três cards (`P2-3`, `P2-5`) são operação de produção e Azure: são
   da matriz por definição, não território despachável. O terceiro (`P2-1`) é uma troca de handler
   em `logbot.py` — código puro, que cabe em qualquer worker.
2. **`P2-1` foi para o `T-MERCADO`.** Território particiona **arquivo** (§3), e `logbot.py` não
   colide com `mercado.py` nem com `dca.py`. Juntar é o que mantém a onda dentro do teto de
   **três workers** da §9.11 — o teto existe porque o auditor é serial, não porque a máquina não
   aguenta. Quatro agentes só enfileirariam diff envelhecendo contra uma base que anda.
3. **`P2-15` desceu para a onda 2.** A correção 2 do card é *agendar o scan por tempo em vez de
   `_health["ciclos"] % CICLOS_POR_SCAN`* — isso é **escrita** em `api.py:55`, e a §4 só dava
   leitura ao `T-SINAL`. A §9.2 já listava o `P2-15` como card que cruza fronteira; aqui ele é
   resolvido movendo o **card inteiro**, não partindo em dois commits em duas ondas. Consequência:
   o `T-API-DADOS` herda `signal_engine.py` na onda 2 — sem conflito, porque o `T-SINAL` já
   mergeou. Território disjunto é exigência **dentro** da onda.
4. **Dois cards fecham em duas ondas, e isso está declarado.** O `P2-3` e o `P2-10` têm cada um
   uma linha final que vive em `api.py`:
   - `P2-3` — `/health` devolvendo o commit em produção (`api.py:390`);
   - `P2-10` — o contador de falhas de funding aparecendo no `/status` (`api.py:405`).

   Nos dois casos o mecanismo nasce na onda 1 / na faixa da matriz, e a linha de exposição em
   `api.py` é do `T-API-DADOS` na onda 2. **O card não sai de 🔨 Fazendo até a segunda parte
   entrar** — o auditor vai encontrar dois commits num card, e este parágrafo é a autorização.
   A alternativa era o worker atravessar fronteira, que a §9.4/P2 reprova mesmo com o código certo.

**Decisão registrada antes da implementação, exigida pelo próprio `P2-9`:** vale a opção **B**
(passar anotado + medir) — o sinal passa, `motivos` ganha `"fluxo n/d"` e `ultimo_scan` ganha o
contador `fluxo_indisponivel`. A sub-pergunta do card ("o auto-trader deve exigir fluxo checado?")
resolve-se assim: **o auto-trader recusa sinal com `"fluxo n/d"` apenas quando `exigir_fluxo=1`**.
Se o humano configurou "exigir fluxo", o bot não pode operar sobre fluxo não verificado; se não
configurou, nada muda. É aperto de guarda, que a §2 do `CLAUDE.md` permite — afrouxamento seria do
dono. E o contador em `/status` é o que impede a degradação de virar silêncio.

**O que esta onda compartilha além de arquivo (§9.2b):** o esquema do banco. Nenhum card da onda 1
mexe em `trading.db`; o `P2-11` (índices e poda da tabela `equity`) mexe, e está sozinho na onda 2,
lendo o que o `Q-4` deixou no M1. Serializado por construção — não por sorte.

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

#### 4c. Territórios do M3 — declarados em 2026-08-22, antes do despacho

Os três cards do M3 **não aparecem na tabela da §3**, e isso não é descuido: a §3 foi extraída das
citações `arquivo:linha` dos documentos de investigação, e teste, reorganização e documento
descrevem **código que ainda não existe** — não têm o que citar (§9.2, ponto cego estrutural).
Território atribuído à mão, portanto, e **é esta tabela que o portão P2 cruza** — não o briefing.

Como o marco é **serial**, os três territórios se sobrepõem no tempo zero: cada um só nasce quando
o anterior mergeou. A sobreposição de arquivo entre eles (`README.md` nos três, `tests/` em dois)
é legal por isso, e **só** por isso.

| Onda | Território | Card | Arquivos que pode escrever |
|---|---|---|---|
| 1 | **`T-TESTE`** | `P2-6` (`TKSi8LdA`) | `tests/` (novo) · `pytest.ini` (novo) · `requirements-dev.txt` (novo) · `test_sim.py` · `test_auth.py` · `README.md` |
| 2 ▸ | **`T-ESTRUTURA`** | `P2-16` (`cnImNkC1`) | todo `*.py` da raiz · `pesquisa/` e `legado/` (novos) · `estrategias/` · `tests/` **só para consertar import** · `deploy/atualizar.sh` · `README.md` · `Procfile` · `DEPLOY-RAILWAY.md` · `DEPLOY-ORACLE.md` |
| 3 ▸ | **`T-DOCS`** | `P2-17` (`oFiBZJSE`) | `ARQUITETURA.md` (novo) · `CLAUDE.md` · `README.md` |

**Três decisões registradas antes da implementação** — o padrão que o `P2-9` estabeleceu no M2:

1. **O `T-TESTE` não edita módulo de plataforma.** Existem cinco provas versionadas e
   reexecutáveis, escritas no M1 e no M2: `python prova_m1.py` (7 asserções), `python simulador.py`
   (11, via `_prova_funding()`), `python db.py prova` (18, via `_prova_p2_11()`), `python api.py`
   (27, via `_prova_api()`) e `python test_auth.py` (3 cenários, subprocesso por cenário). O pytest
   **as embrulha** — importa a função privada ou chama o script por subprocesso — e **não as move**
   para dentro de `tests/`. Mover exigiria escrever em `api.py`, `db.py` e `simulador.py`, que é
   território de plataforma viva; embrulhar custa um arquivo e mantém o diff auditável. Os testes
   novos dos itens 1-4 do card nascem em `tests/`, importando os módulos sem alterá-los.
2. **O `T-ESTRUTURA` herda `tests/` para consertar import, e isso é o ponto do marco.** Mover
   `validacao.py` para `pesquisa/` quebra qualquer teste que o importe. É exatamente a "rede de
   segurança da mudança seguinte" da ordem acima: **o critério de aceite do `P2-16` inclui `pytest`
   verde depois da mudança**, e é ele que prova que o repositório reorganizado ainda é o mesmo
   repositório. O que o `T-ESTRUTURA` **não** pode é alterar a asserção de um teste para fazê-lo
   passar — só o `import`.
3. **A plataforma viva não sai da raiz, e o motivo é o deploy.** O `deploy/cripto-bot.service` roda
   `uvicorn api:app` com `WorkingDirectory=/home/ubuntu/cripto-bot`, e o `deploy/atualizar.sh:51`
   compila `./*.py` — glob de raiz, não recursivo. Manter `api`, `db`, `simulador`, `signal_engine`,
   `scoring`, `indicadores`, `mercado`, `dca`, `autotrader`, `logbot`, `alertas` e `prova_m1.py` na
   raiz é o que torna a reorganização invisível para a VM. Se o worker mover pesquisa para
   `pesquisa/`, o `py_compile` deixa de cobri-la: ou estende o glob no `atualizar.sh`, ou **declara
   no commit** que pesquisa não é código de produção e por isso não precisa do portão de compilação.

**O `T-ESTRUTURA` não deleta nem move sem a decisão do dono registrada.** O card recomenda deletar o
legado ("o git guarda tudo"); a alternativa é `legado/` com um README declarando que nada ali é
importado pela plataforma. É a única escolha do marco que o agente não toma sozinho — vai no
briefing já decidida.

**Um fato do `P2-17` que o card não sabia: o `CLAUDE.md` já existe.** Foi escrito pela matriz do M2
(148 linhas, dentro do teto de ~150 do card). O `P2-17` deixa de ser "criar dois documentos" e passa
a ser **criar o `ARQUITETURA.md` e reconciliar o `CLAUDE.md` com o critério de aceite** — que hoje
falha em três itens: não tem mapa de módulos, não tem a seção de comandos, e a lista de invariantes
não menciona CDN no `web/` nem a franquia de banda. Vale a regra do §13 do `ORQUESTRACAO-ORCA.md`:
card pode estar errado sobre um fato, e o fato manda.

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
       INVESTIGACAO-TRADING-2026-08-19.md  (P1-10..11, Q-1..6)

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


---

## 9. O portão: isolamento, auditor e devolução

> Desenhada pela sessão `1-99` com contraponto da `1-69` (§9.12 traz o registro das mudanças);
> aterrissada em 2026-08-22 por decisão do dono do projeto. Os casos citados são reais, desta
> operação.

A §3 até a §7 dizem como **despachar**. Nada diz como **receber de volta**. Enquanto isso não
existir, "card fechado = commit + portão verificado" (§7) é autodeclaração do agente que escreveu
o código.

### 9.0 Pré-requisitos

**(a) A numeração — resolvido em `origin/main`, mas a lição fica.** A série do front reusou
`P2-19..25`, que o M4 já usava para os cards quant; por seis dias dois cards responderam por cada
número. A série quant saiu da sequência disputada e virou `Q-1..6` (`16fae7e`). A lista `toca-risco`
da §7 foi corrigida junto — `P2-21` virou `Q-3`.

O que **não** se resolve renumerando, e por isso vira regra desta seção:

> A primeira tentativa moveu a série quant para `P2-29..34` e **colidiu de novo no mesmo dia**,
> porque outra sessão criava os cards do M6 exatamente nessa faixa ao mesmo tempo.

`P2-` é sequência compartilhada, e **alocar número é escrita em estado mutável comum — o mesmo
problema do índice do git (§9.1), só que no quadro.** Duas sessões numerando em paralelo colidem
sempre. Duas regras decorrem:

1. **Cada fluxo de trabalho tem prefixo próprio** (`Q-` pesquisa quant, `P0/P1/P2` operação,
   front na sua faixa). Nenhuma sessão cria número em sequência de outro fluxo.
2. **A chave de card no auditor é o shortLink do Trello** (`xqtBId7v`), nunca o `[N]` do título.
   Renumeração acontece; shortLink não muda. Isso vale mesmo com a colisão já desfeita — é o que
   torna o portão imune à próxima.

**(b) A base não é a `main`, e a `main` local fica velha.** Retrato de 2026-08-22, quando
isto foi escrito (a `main` local chegou a ficar **27 commits** atrás no mesmo dia — o push
`origin HEAD:main` a partir de worktrees nunca a adianta):

| Ref | SHA | O que tem |
|---|---|---|
| `origin/main` | `16fae7e` | a verdade — inclui a renumeração `Q-` |
| `main` local | `588c10b` | dois commits atrás; **não** tem a renumeração |
| `HEAD` (checkout) | `de64ead` | `feat/m6-design-system-cmc`; leva `DESIGN.md` e `PLANO-FRONTEND-REDESIGN.md` à frente, e também não tem a renumeração |

Worker que branche do `HEAD` atual sai com dois problemas: carrega dois arquivos alheios para dentro
do próprio diff (e o portão de fronteira reprova código bom), e lê um plano com a numeração antiga.

**Regra:** `git fetch` primeiro; todo território branca de **`origin/main`** explicitamente, e **o
SHA da base vai escrito no card**.

**Contrapartida da base fixa: a documentação congela junto.** O plano mora no repositório, então o
worker lê a versão que existia no SHA dele — inclusive erro já corrigido na `main`. Aconteceu: os
dois territórios do M1 saíram de `16fae7e` e carregam o `Q-1..24` que o `8735e43` consertou.

**A base fixa vale para o código, não para as instruções.** Card e território vão embutidos no
briefing (é o que torna a deriva inofensiva); qualquer releitura do plano é de `origin/main`, não da
cópia da worktree.

```bash
git fetch origin
git worktree add ../1-T-API-GUARDA -b terr/api-guarda origin/main   # base é argumento, não o HEAD
```

### 9.1 Território não isola o git

A §3 resolve colisão **de arquivo**. Não resolve colisão **de repositório**. Dois agentes em
territórios distintos, no mesmo diretório, ainda compartilham um índice e um `HEAD`:

| O que quebra | Como |
|---|---|
| `git commit -am` | varre junto o arquivo meio pronto do outro território |
| "um commit por card" (§3) | morre no primeiro commit concorrente |
| `index.lock` | duas sessões commitando ao mesmo tempo dão erro |
| qualquer teste | lê a árvore de trabalho de outro agente |

**Uma worktree por território, uma branch por território, base `origin/main` explícita.**

Nota de ambiente (Orca): worktree isolada por task é nativo, e é a única coisa que a ferramenta
resolve sozinha. A unidade padrão dela é a task — o que se faz é **mapear task = território**, e aí
o modelo do Orca passa a ser exatamente o que a §3 pede. Não há conflito, há convenção a impor. O
board integrado é GitHub/Linear; com Trello o auditor lê e escreve pela API, com o token permanente.

Cada worktree quer o próprio venv. São cópias, não links.

### 9.2 O mapa de territórios só vale dentro de uma onda

**Esta é a restrição mais perigosa do plano, e ela não está na §4.**

A §4 garante território disjunto **dentro de uma onda**. Não garante nada **entre marcos**:

| Arquivo | Territórios que o reivindicam |
|---|---|
| `simulador.py` | `T-API-GUARDA` (M1), `T-EXEC` (M2), `T-EXEC-REAL` (M4) |
| `validacao.py` | `T-EXEC` (M2), `T-REGUA` (M4) |
| `autotrader.py` | `T-SINAL` (M2), `T-REGUA` (M4) |

Enquanto os marcos correrem **em série**, o mapa vale. Mas uma frota existe para rodar em paralelo —
e no instante em que alguém despacha M1 e M4 juntos, o mapa vira mentira e o portão de fronteira
passa a **aprovar colisão real**, porque cada agente está dentro do próprio território no papel.

**Regra: o paralelismo é dentro do marco, nunca entre marcos.** A única exceção é o M5, que tem
território exclusivo (`web/index.html`) e por isso já roda em paralelo a tudo desde o dia 1 (§4).

Cards que cruzam fronteira, já conhecidos:

| Card | Cruza |
|---|---|
| `P2-15` | `signal_engine.py` (`T-SINAL`) + `api.py` (`T-API-DADOS`) — ondas diferentes |
| `P2-14` | `api.py`+`simulador.py` (M1) + `web/index.html` (M5) — **marcos diferentes**; já anotado na §4 |
| `P2-8` | `autotrader.py`/`scoring.py` (`T-SINAL`, M2) + `validacao.py` (`T-REGUA`, M4) |
| `P1-9` | `signal_engine.py` + `autotrader.py` |
| `P2-10` | `simulador.py` + `validacao.py` |

O `P2-14` é o único que a §4 já pegou. Que os outros quatro tenham passado é a prova de que a
omissão é estrutural, não descuido pontual.

**Regra que fecha a §9.2: território sem lista de arquivos declarada não é despachável.** O portão
P2 é `git diff --name-only` cruzado com uma lista — sem a lista, o portão não existe, e o agente
fica inauditável por construção. Conferir isso custa uma leitura da §4 e é pré-condição do despacho,
não do merge.

> **Caso real, 2026-08-22.** O `Q-4` foi despachado em `terr/fluxo-log` sem território declarado: não
> aparece na tabela de colisão da §3 nem em nenhuma linha de agente da §4 — a única menção é "sai
> junto com o `T-API-GUARDA`" no M1, que diz *quando*, não *o quê*. O worker já editou `db.py`, que
> a §4 dá ao `T-API-DADOS`. Não houve dano: o `T-API-GUARDA`, que roda em paralelo, é dono de
> `api.py` e `simulador.py`, e não há interseção. Mas o portão de fronteira não pôde ser rodado, e o
> território de fato do `Q-4` só existe no briefing — que o auditor nunca viu.

Corolário, na forma dura: **o briefing não pode conter nada que o plano não contenha.** Não basta o
território existir em algum lugar — no instante em que o prompt de despacho declara qualquer coisa
que a §4 não declara, existem duas fontes de verdade, e a que a auditoria lê é a desatualizada. É a
mesma classe de erro da numeração duplicada (§9.0a): dois lugares dizendo a mesma coisa, um errado,
e o errado sendo o consultado. O briefing **transcreve** o plano; nunca acrescenta.

**E o mapa da §3 tem um ponto cego estrutural.** A tabela de colisão foi *extraída* das citações
`arquivo:linha` dos documentos de investigação — logo ela enxerga card que descreve **código que
existe** e é cega a card que descreve **código que ainda não existe**. Instrumentação, teste e
documento não têm citação para extrair, e por isso somem do mapa (`Q-4`, `P2-6`, `P2-17` ao menos).

Consequência para o portão: **ausência na §3 não é prova de que o card não colide** — pode ser
apenas prova de que ele não tinha o que citar. Card dessas três categorias precisa de território
atribuído à mão, e é justamente onde o esquecimento acontece.

### 9.2b O que o território não isola

Esta é a espinha da seção inteira, e vale enunciar de uma vez. **Território particiona arquivo.**
Todo estado compartilhado que *não* é arquivo continua sem dono, e cada um precisou da própria
solução. Em três dias de operação, três apareceram:

| Estado compartilhado | O que acontece sem isolar | Mecanismo |
|---|---|---|
| **Índice e `HEAD` do git** | `commit -am` varre trabalho alheio; `index.lock` colide | worktree por território (§9.1) |
| **Sequência de numeração do quadro** | dois cards com o mesmo número; regra de risco aponta para identificador ambíguo | prefixo por fluxo + escritor único (§9.0a, §9.6b) |
| **Esquema do banco** | dois cards alteram `trading.db`; quem chega depois lê o que o primeiro deixou | serializar: card que mexe em esquema não roda em paralelo com outro que mexa |

O terceiro é o mais traiçoeiro porque **passa no portão de fronteira**: `Q-4` (`T-FLUXO-LOG`, M1) e
`P2-11` (`T-API-DADOS`, M2) são donos de `db.py` em territórios distintos e ondas distintas — cada
um dentro do seu no papel, e ainda assim mexendo na mesma tabela `equity`. O arquivo é territorial;
o esquema que ele cria, não.

**Regra: antes de declarar uma onda, pergunte o que ela compartilha além de arquivo.** Se a resposta
for esquema de banco, migração, sequência de identificador ou qualquer recurso de produção único, o
portão de fronteira não vai pegar — serialize.

### 9.3 O que o auditor enxerga — e o que não enxerga

O auditor vê três coisas: **git, arquivos e Trello**. Não vê o raciocínio de quem escreveu o código.
Isso é a força do portão (checagem independente, não carimbo) e é também um limite duro:

> Um auditor cego ao raciocínio do worker consegue reprovar **fronteira** e **critério de aceite**.
> Não consegue reprovar **"consertou o sintoma"** — ver §9.5.

Regra que decorre: **o auditor nunca aceita a palavra do worker; ele lê o commit.** A mensagem do
worker serve para acordar o auditor, não para informá-lo.

### 9.4 Os portões mecânicos

Para cada card entregue, nesta ordem. Reprovou em um, para.

| # | Portão | Como se verifica | Reprova quando |
|---|---|---|---|
| **P1** | Critério de aceite | roda o checklist do card | item não passa, ou não existe comando que o prove |
| **P2** | Fronteira | `git diff --name-only <SHA-base>...terr/<x>` cruzado com a lista do §4 | tocou arquivo fora do território — **mesmo com o código certo** |
| **P3** | Commit limpo | lê o diff daquele commit isolado | o commit mistura mais de um card |

O **P2 é o mais barato e o que segura a erosão do plano**: uma linha de shell, zero julgamento.
Rode primeiro. Use o SHA da base registrado no card (§9.0b), não o nome de branch.

Violação de fronteira tem duas leituras, e o auditor precisa distinguir: ou o agente extrapolou, ou
**a onda estava errada**. O segundo caso não é falta do worker; é correção de plano e sobe para
decisão humana.

**O P1 não é mecânico em todo marco.** Levantamento por card:

| Marco | O P1 funciona? |
|---|---|
| **M1, M2** | **Sim.** Bug com sintoma reproduzível — é onde o auditor mecânico entrega. |
| **M3** | Não. `P2-16` "repositório organizado", `P2-17` "CLAUDE.md serve para alguma coisa" — a metade verificável passa, a que importa não. |
| **M4** | Não. `P1-10` pede "um veredito de edge em que você aposta"; `Q-4` precisa de semanas de mercado; `Q-3` aceita "alinhar **ou declarar**"; `Q-5`/`Q-6` são julgamento ou escopo aberto. |

**Regra: o portão de M3 e M4 é revisão humana declarada, não checklist.** Assumir isso no desenho —
o risco é o auditor virar carimbo exatamente onde a aposta é maior.

### 9.5 O portão que não é mecânico: raiz ou sintoma

Os três portões acima passam num conserto de sintoma. Exemplo real, `P1-1`:

> Envolver o `for` **inteiro** num try/except passa em "o ciclo continua", passa na fronteira, e o
> diff parece bom — e deixa **toda posição depois da primeira falha** sem stop, sem trailing e sem
> checagem de liquidação. O card pede try/except **por posição**. A diferença é dinheiro.

Como o auditor não vê o raciocínio (§9.3), esse portão só existe se o raciocínio for **escrito**:

- **O worker registra no card**, junto do commit: a causa que identificou, por que a correção ataca
  a causa, e como seria a versão-sintoma que ele **não** fez.
- **O auditor lê isso contra o diff.** Ausência desse registro é reprovação por si só — é a única
  parte auditável.
- **Se ainda restar dúvida, sobe para o humano.** Não se aprova por cansaço.

**Observado em 2026-08-22, e muda o peso desta seção:** o briefing do `T-API-GUARDA` pediu o
registro do raciocínio, e o worker entregou — o `P1-1` saiu com a marcação de uma posição extraída
para função própria, o try/except na chamada dela, os `continue` virados `return`, e o motivo escrito
como comentário no código. A correção de raiz, não a de sintoma, **sem que existisse portão obrigando**.

A leitura certa disso: **pedir no briefing é o que produz o comportamento; o portão é o que pega
quem não fez.** Instrução ensina quem quer acertar, portão pega quem não fez — e as duas coisas
precisam existir, na ordem: primeiro o briefing pede, depois o portão confere.

### 9.6 Quem move o card

**Reivindicação e veredito se separam.**

| Movimento | Quem | Por quê |
|---|---|---|
| 📥 Triagem → 🔨 Fazendo | **worker** | é um *lock*, e só ele sabe a hora que começou. "Fazendo" é a única exclusão mútua entre sessões; precisa ser instantânea |
| 🔨 Fazendo → **qualquer coisa** | **auditor** | veredito de quem fez o trabalho é autodeclaração |

**Nada sai de Fazendo sem o auditor — inclusive voltar para Triagem.** Senão o worker desiste, o
card fica preso e trava o território inteiro.

| Veredito | Destino | O que vai no card |
|---|---|---|
| Passou, efeito observável em produção | 🔍 Validando | commit + comando + saída colada |
| Passou, sem efeito observável | ✅ Feito | commit + comando + saída colada |
| Reprovou | 🔨 Fazendo (segue com o worker) | **qual portão**, o comando que falhou e a saída dele |
| Fronteira estourada por onda mal desenhada | 🧊 Bloqueado | o arquivo em disputa e os dois territórios |

Reprovação sem o comando que falhou não é reprovação, é opinião.

### 9.6b O quadro também é estado compartilhado

Mover card é uma coisa (§9.6). **Criar, renumerar ou renomear é outra, e nenhum portão a cobre** —
todos os três olham para o git. Uma sessão consegue estragar o trabalho de outra sem tocar em uma
linha de código, e isso não é hipótese: aconteceu duas vezes em 2026-08-22, entre duas sessões
apenas (§9.0a). Com oito, é regime permanente.

- **Worker não cria, não renumera, não renomeia card.** Precisa de card novo, reporta; quem cria é
  o auditor.
- **Alocação de número tem um escritor só.** `P2-<próximo livre>` é leitura seguida de escrita sem
  atomicidade, e o quadro não tem lock. Serializar no auditor é o que substitui o lock que não
  existe.
- **Fluxo novo nasce com prefixo próprio**, nunca numa faixa livre da sequência de outro (§9.0a).

O paralelo com a §9.1 é exato: worktree isola a árvore de trabalho, prefixo isola o espaço de nomes.
São o mesmo problema — escrita concorrente em estado compartilhado — resolvidos pela mesma via, que
é dar a cada agente um espaço que só ele escreve.

### 9.7 O que acontece quando reprova

Veredito sem remediação deixa lixo na árvore de todo mundo.

- **O commit reprovado não é revertido pelo auditor.** Ele fica na branch do território; quem
  corrige é o worker dono, com um commit novo em cima. Auditor que reverte vira autor (§9.10).
- **O território não bloqueia.** O worker segue nos outros cards dele enquanto refaz o reprovado —
  o que bloqueia é o **merge** do território, que só sai com todos os cards aprovados (§9.9).
- **Duas reprovações no mesmo card sobem para o humano.** Terceira tentativa sem diagnóstico novo é
  sinal de que o card está mal escrito, não de que o worker é ruim.

### 9.8 `toca-risco` não tem auditor automático

São 10 cards com a label: `P0-1`, `P1-1`, `P1-6`, `P1-7`, `P1-10`, `P1-11`, `P2-2`, `P2-8`,
`P2-18`, `Q-3`. A §7 já manda: invariante de risco não relaxa sem decisão humana registrada no
card.

**Um auditor que aprove esses sozinho converte um portão humano em automático** — é regressão de
segurança vestida de automação, com posição aberta em produção agora. O auditor roda os portões e
**para**, com o parecer pronto para o humano assinar. Ele nunca é o último a dizer sim.

(`Q-3` entrou nessa lista pela renumeração de 2026-08-22 — era `P2-21`. §9.0a.)

### 9.9 O portão do marco

Merge de `terr/*` para a `main` só depois que **todos** os cards do território passaram. O portão do
marco escrito em cada bloco da §4 é rodado sobre a `main` já mesclada, não sobre a branch.

Dois territórios da mesma onda que se contradizem no merge é o caso de uso da skill `orquestrador`:
consolidar as revisões, ordenar por dependência, aplicar sem que um fix quebre o aceite do outro.

Assimetria que muda o peso do merge:

- **Backend** — `main` não é produção; o deploy é cópia manual até o `P2-3` fechar (§7). Errar custa
  retrabalho.
- **Front (M5, `web/index.html`)** — publica sozinho no Vercel ao entrar na `main`. Aqui o merge
  **é** a publicação.

### 9.10 O que o auditor não faz

- **Não corrige o código.** Auditor que edita vira autor e revisor do mesmo diff.
- **Não aprova `toca-risco` sozinho** (§9.8).
- **Não audita em lote no fim da onda.** Audita cada commit quando chega, senão vira o gargalo.

### 9.11 Quantos workers ao mesmo tempo

**Três, no máximo**, e **dentro do mesmo marco** (§9.2). O limite não é a máquina: gerar um diff
leva minutos, lê-lo com cuidado leva uma hora, e o auditor é serial. Frota maior só enfileira diff
esperando revisão — e diff parado envelhece contra uma base que se move.

O M1 tem dois territórios em paralelo, mais o M5 em sessão separada. Cabe. É o teto, não a meta.

---

### 9.12 O que mudou da v1 para a v2

| # | Achado da `1-69` | Onde entrou |
|---|---|---|
| 1 | numeração `[P2-n]` colidiu em 6 números | §9.0a — **já resolvido em `origin/main`** (série quant → `Q-1..6`); virou a regra de prefixo por fluxo + chave = shortLink |
| 2 | base é `feat/m6-design-system-cmc`, não `main` | §9.0b — base é `origin/main` (a `main` local também está velha), SHA no card |
| 3 | mapa de território não vale entre marcos | §9.2 — **a mudança mais importante da v2** |
| 4 | M3 e M4 não têm aceite verificável por comando | §9.4 — portão desses marcos é revisão humana declarada |
| 5 | worker precisa mover Triagem→Fazendo (é lock) | §9.6 — reivindicação separada de veredito |
| 6 | não havia portão para raiz vs sintoma | §9.5 — novo, e é o único não-mecânico |
| 7 | `toca-risco` não pode ter auditor automático | §9.8 — novo |
| 8 | veredito sem remediação | §9.7 — novo |
| 9 | Orca não conflita: task = território | §9.1 — reescrito, era "fricção" na v1 |
| 10 | nenhum portão cobre o worker que mexe no **quadro** | §9.6b — novo, veio da segunda rodada |
| 11 | `Q-4` despachado sem território declarado (caso real) | §9.2 — território sem lista não é despachável; briefing **transcreve**, nunca acrescenta |
| 12 | base fixa congela a documentação junto | §9.0b — base fixa vale pro código, não pras instruções |
| 13 | a tabela da §3 é cega a card sem citação `arquivo:linha` | §9.2 — instrumentação, teste e documento somem do mapa |
| 14 | território não isola esquema de banco | §9.2b — **novo, é a espinha da seção** |
| 15 | o registro do raciocínio funcionou como instrução, antes de virar portão | §9.5 — muda a ordem: briefing pede, portão confere |

Duas correções na direção contrária, verificadas contra o repositório e **aceitas pela `1-69`**:

- O que a branch leva à frente da `main` é `DESIGN.md` e `PLANO-FRONTEND-REDESIGN.md` — **não**
  `web/index.html`. O problema apontado era real; o arquivo do exemplo, não.
- Three-dot (`base...terr`) **não** esconde mudança do território quando a `main` anda: ele mede
  desde a base de fusão, que é exatamente o que se quer. O que quebra o portão é branchar do `HEAD`
  errado (§9.0b), e a correção é fixar a base — não trocar o operador.

Uma decisão que os fatos resolveram melhor que o argumento: na renumeração, o critério que decidiu
não foi "quantos lugares referenciam", foi **o que é imutável**. Os números do front vivem em
mensagem de commit já pushada; os do quant, só em arquivos que uma sessão controla e conferiu por
grep. Renomeia-se o lado mutável. Vale como regra geral para a próxima colisão.
