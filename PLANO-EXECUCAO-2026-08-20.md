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

**Decisão do dono, registrada em 2026-08-22, antes do despacho da onda 2: o legado vai para
`legado/`, não é deletado.** O card recomendava deletar ("o git guarda tudo"); a decisão foi mover,
com um `legado/README.md` declarando que nada ali é importado pela plataforma viva. O que a escolha
compra: a reorganização deixa de ser irreversível na árvore de trabalho — desfazer é um `mv` — e o
M4, que é pesquisa, continua conseguindo olhar `backtest.py`, `monte_carlo.py` e `estrategias/` sem
precisar de arqueologia no `git log`. O que ela custa: `legado/` fica no repositório até alguém
decidir apagá-lo. A alternativa continua disponível a custo zero depois do M4, porque mover não
destrói nada.

**O que de fato quebra na reorganização, medido em 2026-08-22 e não estimado.** O mapa de módulos
do card é de 2026-08-19; a matriz o reconferiu montando o grafo de imports por AST sobre a `main`
`1646b04`. As três listas do card estão **corretas** — o fecho transitivo de `api.py` dá exatamente
os onze módulos que ele chama de plataforma viva (`alertas`, `api`, `autotrader`, `db`, `dca`,
`indicadores`, `logbot`, `mercado`, `scoring`, `signal_engine`, `simulador`), e `config.py` é
importado **só** por módulos do legado, o que torna a morte dele limpa. O que o card não viu:

- **`scoring.py` e `indicadores.py` são compartilhados entre plataforma e pesquisa.** `scoring` é
  importado por `signal_engine` (vivo) e por `backtest_plataforma`, `validacao` e os
  `validar_reversao*` (pesquisa); `indicadores` é importado por `scoring` (vivo) e por
  `scalp_backtest`. Eles **ficam na raiz** — mas isso significa que `pesquisa/validacao.py` vai
  fazer `import scoring` de um módulo que não está mais no mesmo diretório. Rodar
  `python pesquisa/validacao.py` põe `pesquisa/` no `sys.path`, **não** a raiz, e o import falha.
  É a quebra concreta desta onda, e ela tem que ser resolvida deliberadamente: `python -m
  pesquisa.validacao` a partir da raiz (com `pesquisa/__init__.py`), ou um shim de `sys.path` no
  topo dos módulos de pesquisa. Escolher em silêncio, não — o critério de aceite do card já exige
  `validacao.py` executando depois da mudança.
- **`dados.py` é compartilhado entre pesquisa e legado**, e por isso `legado/monte_carlo.py` vai
  deixar de importar. Isso é **aceitável e precisa estar escrito**: o `legado/README.md` declara que
  nada ali é importado pela plataforma **e que os módulos de lá não são mais executáveis no lugar
  onde estão** — quem quiser rodar um, o git tem a versão que rodava.

**Segunda decisão do dono, mesma data: o M3 é deployado na VM depois do merge, com verificação.**
A plataforma viva não sai da raiz (decisão 3 acima), então o `uvicorn api:app` do service não muda —
mas o `git checkout` na VM vai mover ~30 arquivos, e isso é ato deliberado, não consequência. O
deploy é `cripto-deploy` (backup, congelamento, `py_compile` no venv de produção, restart), a
verificação é `/health` com o SHA novo mais `/status` e equity nova, e o rollback é
`bash deploy/atualizar.sh <sha>` — testado no `P2-3`. **É trabalho da matriz, não do worker**
(`CLAUDE.md` §6).

**Um fato do `P2-17` que o card não sabia: o `CLAUDE.md` já existe.** Foi escrito pela matriz do M2
(148 linhas, dentro do teto de ~150 do card). O `P2-17` deixa de ser "criar dois documentos" e passa
a ser **criar o `ARQUITETURA.md` e reconciliar o `CLAUDE.md` com o critério de aceite** — que hoje
falha em três itens: não tem mapa de módulos, não tem a seção de comandos, e a lista de invariantes
não menciona CDN no `web/` nem a franquia de banda. Vale a regra do §13 do `ORQUESTRACAO-ORCA.md`:
card pode estar errado sobre um fato, e o fato manda.

#### 4d. O que a onda 1 mudou para a onda 2 — escrito em 2026-08-22, depois do merge do `P2-6`

O `T-TESTE` entregou, e a entrega **estreita o território do `T-ESTRUTURA`** em três pontos. Está
aqui e não no briefing porque é o plano que o auditor lê (§9.2).

**1. Três scripts da raiz deixaram de ser movíveis.** A linha "todo `*.py` da raiz" da tabela da
§4c precisa desta exceção: `prova_m1.py`, `test_sim.py` e `test_auth.py` **ficam onde estão**. Eles
não são scripts soltos — são três das seis provas que `tests/test_provas_existentes.py` executa por
subprocesso, com `cwd` na raiz. Mover qualquer um quebra a suíte por caminho, não por lógica, e o
`P2-16` tem `pytest` verde no critério de aceite. `test_sim.py` e `test_auth.py` **casam com
`test_*.py`** e por isso parecem candidatos naturais a ir para `tests/` — é justamente a armadilha:
o `pytest.ini` os mantém fora da coleta de propósito (`testpaths = tests`), porque são programas que
se rodam por `python <arquivo>`, e coletá-los faria o pytest importá-los e executar duas provas
dentro do próprio processo, fora do isolamento das fixtures.

**2. A suíte precisa do repositório ser um checkout git, e isso é intencional.** A prova do `api.py`
(escrita no M2 pelo `P2-3`) afirma que `/health` devolve o commit em produção, e para isso roda
`git rev-parse HEAD`. Consequência para quem audita: **rodar a suíte numa cópia sem `.git` a
reprova por um motivo que não é defeito.** A matriz descobriu isso do jeito caro, acusando o worker
antes de conferir — a auditoria passou a usar `git worktree add --detach` em vez de `copytree`. Não
é limitação a consertar: é o `P2-3` fazendo o que foi pedido.

**3. `db.metricas()` tem um defeito latente registrado, e ele muda o que "pytest verde" significa.**
O card `P2-36` (`oDireXwJ`) nasceu do achado: `metricas()` classifica os trades tolerando NULL
(`db.py:259-260`) e **soma a coluna crua** duas linhas abaixo (`db.py:261-262`) — um `pnl_reais`
NULL levanta `TypeError` e derruba o `/estado`. Latente hoje, porque `simulador.fechar()` é o único
INSERT em `trades` e sempre passa float. O teste existe, marcado `xfail(strict=True)`: **no dia em
que o `P2-36` fechar, o xfail vira XPASS e quebra a suíte**, obrigando a promover o teste. Quem
mexer em `db.py` sem fechar o card não é pego; quem consertar sem promover o teste é. Era o efeito
desejado.

**4. Uma linha do `CLAUDE.md` ficou falsa, e o conserto é da onda 3.** O §6 diz "o `test_sim.py`
**não roda** localmente — depende do banco da VM". Depois do `P2-6` ele roda: foi reescrito no
padrão do `prova_m1.py`, com banco temporário, dados semeados por ele mesmo e sem rede. O
`T-TESTE` viu e **não consertou**, corretamente — `CLAUDE.md` é território do `T-DOCS`. Entra na
lista do `P2-17` como item obrigatório, e serve de exemplo do que a §13 do `ORQUESTRACAO-ORCA.md`
chama de documentação que apodrece: o card mudou o mundo, o documento continuou descrevendo o
mundo antigo, e só não passou despercebido porque o worker escreveu no relatório o que **não** pôde
fazer.

**Portão do M3:** sessão nova, prompt frio, faz um fix — e o teste pega uma regressão plantada de propósito.

> ### ✅ Portão do M3 — RODADO em 2026-08-22, nas duas metades, e depois deployado
>
> Merges: `95096fe` (T-TESTE), `3498ca4` (T-ESTRUTURA), `e5fb090` (T-DOCS). Deploy na VM pelo
> `cripto-deploy`: `7c65df1 → e5fb090`, com backup, congelamento, `py_compile` no venv de produção,
> restart e verificação.
>
> A frase do portão — *"sessão nova, prompt frio, faz um fix, e o teste pega uma regressão plantada
> de propósito"* — tem **duas** metades, e cada uma foi rodada como comando da matriz, não como
> relato de worker.
>
> **Metade 1 — o teste pega regressão plantada.** A matriz plantou **sete** regressões reais, uma
> por vez, em worktree separada, e exigiu que a suíte ficasse vermelha:
>
> | Regressão plantada | Resultado |
> |---|---|
> | trava diária deixa de ser sticky | PEGOU (3 failed) |
> | `_pnl` perde o cap na margem | PEGOU |
> | direção do `_pnl` invertida | PEGOU |
> | liquidação ignora a alavancagem | PEGOU |
> | cap do sizing ignora `max_frac` | PEGOU (2 failed) |
> | `_alavancagem` sem teto `lev_max` | PEGOU (2 failed) |
> | sizing opera banca morta | PEGOU (2 failed) |
>
> Uma oitava tentativa — trocar a ordem de piso e cap no `_tamanho` — **não** foi pega, e conferindo,
> **a suíte estava certa e a mutação errada**: a guarda `cap < min_valor → return 0` logo acima
> garante `cap >= min_valor`, então as duas ordens são equivalentes. Fica registrado porque auditoria
> que erra e diz que acertou é pior que auditoria nenhuma.
>
> **A metade 1 foi rodada duas vezes**: na branch do `T-TESTE` e de novo **sobre a `main` já com o
> `P2-16` mesclado** — que é o único momento em que a reorganização e a rede de segurança existem
> juntas. A regressão da trava diária continuou sendo pega depois de 44 arquivos mudarem de lugar.
>
> **Metade 2 — a sessão fria acerta lendo só o contrato.** A matriz criou um diretório **vazio**
> contendo **apenas o `CLAUDE.md`** e rodou uma sessão sem repositório, sem histórico e sem contexto.
> Ela acertou onde vive a configuração (`db.CONFIG_PADRAO` + tabela `config`, e que o `config.py`
> foi para `legado/`), listou os **sete** invariantes, **recusou** trocar `web/vendor/` por CDN
> citando a credencial no `localStorage` e oferecendo a alternativa certa, **recusou** converter
> timestamps para UTC explicando que o banco inteiro é naive-SP, e soube o comando de teste e a saída
> esperada — inclusive que o `1 xfailed` é card em aberto, não teste quebrado.
>
> **O estado do repositório que o marco deixa:**
>
> | Antes do M3 | Depois |
> |---|---|
> | pytest não instalado, nenhum teste rodando | `python -m pytest` → **143 passed, 1 xfailed** (~36 s) |
> | cinco provas reexecutáveis, uma a uma, de memória | um comando executa as seis e confere **exit code E contagem de asserções** |
> | `test_sim.py` sem asserção nenhuma, saindo 0 nos dois casos | 13 asserções, banco temporário, sem rede |
> | 51 `.py` na raiz misturando três eras | 14 na raiz (11 da plataforma + 3 provas), `pesquisa/` e `legado/` |
> | dois arquivos reivindicando "Fonte UNICA da verdade" | um: `db.py:49` |
> | `ARQUITETURA.md` não existia | 457 linhas, **91 citações `arquivo:linha`, todas resolvem** |
> | `CLAUDE.md` sem mapa de módulos, sem comandos, sem CDN nem banda nos invariantes | os cinco blocos do card, 195 linhas |
>
> **Produção depois do deploy:**
> ```json
> "scan": {"total": 52, "ok": 51, "falhas": 0, "ultimo_erro": null, "fluxo_indisponivel": 0}
> "funding": {"medidos": 0, "falhas": 0}   "saudavel": true   "posicoes_abertas": 0
> /health: {"status":"ok","versao":"0.3","commit":"e5fb0904f04311b4e9838bd334420e462cd8c695"}
> ```
> `pesquisa/` e `legado/` chegaram na VM; o `uvicorn api:app` não mudou, como a decisão 3 da §4c
> previu. `auto_trade` foi restaurado para `1` depois da verificação — e **a guarda que segura hoje é
> a trava diária**, engatada em `2026-08-22`, que é o comportamento sticky do `CLAUDE.md` §2.
>
> **Dois achados do marco que viraram trabalho novo, nenhum deles no plano original:**
>
> - **`P2-36`** (`oDireXwJ`) — `db.metricas()` soma `pnl_reais` cru depois de classificar tolerando
>   NULL; um NULL derruba o `/estado`. Latente hoje. O teste já está plantado como
>   `xfail(strict=True)`: quem consertar sem promover o teste **quebra a suíte**.
> - **`analise_dia.py` está na raiz da VM e não é rastreado pelo git** — sobra do deploy por cópia
>   manual da era M1, que o `git status` da VM confirma como untracked. É exatamente a classe de
>   armadilha que o `P2-16` veio remover, só que do lado de produção, onde a reorganização do
>   repositório não alcança.

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

#### 4f. Territórios do M4 — reescritos em 2026-08-23, depois do merge do M3

**A tabela do M4 acima ficou falsa, e não por descuido.** Ela nomeia `validacao.py`, `tune.py`,
`validar_oos.py` e `backtest*.py` **na raiz** — e o `P2-16` (M3) mudou todos de lugar. Hoje eles
são `pesquisa/validacao.py`, `pesquisa/tune.py`, `pesquisa/validar_oos.py` e
`pesquisa/backtest_plataforma.py`. Um portão P2 rodado contra a tabela antiga reprovaria trabalho
correto por caminho, e um briefing transcrito dela mandaria o worker editar arquivo que não existe.

É o caso que a §14.3 do `ORQUESTRACAO-ORCA.md` descreve: **marco serial estreita o marco seguinte, e
a mudança tem de ser escrita antes do despacho, não descoberta pelo worker.** Esta seção é essa
escrita. **É esta tabela que o portão P2 cruza** — não a do M4 acima, não o briefing.

| Onda | Território | Cards | Arquivos que pode escrever |
|---|---|---|---|
| 1 | **`T-REGUA`** | `Q-1` (`xqtBId7v`) · `Q-2` (`4ba2vwNp`) | `pesquisa/validacao.py` · `pesquisa/tune.py` · `pesquisa/validar_oos.py` · `pesquisa/validar_reversao.py` · `pesquisa/validar_reversao_maker.py` · `pesquisa/validar_swing.py` · `pesquisa/__init__.py` · `legado/README.md` · `README.md` · `ITEM1-VALIDACAO-RIGOROSA.md` · `tests/test_validacao.py` (novo) |
| 1 ‖ | **`T-EXEC-REAL`** | `P2-18` (`T4hQp3XN`) · `Q-6` (`l3trY9PM`) | `simulador.py` · `pesquisa/dados.py` · `ARQUITETURA.md` · `tests/test_pnl.py` · `tests/test_execucao_real.py` (novo) |
| 1 ‖ | **`T-SIZING`** | `P2-8` (`TjtftLyj`) · `P1-11` (`e8elDr7G`, metade) | `autotrader.py` · `tests/test_sizing.py` |
| 2 ▸ | **`T-PORTFOLIO`** | `Q-5` (`fPL6lccf`) | `pesquisa/backtest_portfolio.py` (novo) · `tests/test_portfolio.py` (novo) |
| 2 ▸ ‖ | **`T-DECLARACAO`** | `Q-3` (`CA6ezdNV`) · `P2-36` (`oDireXwJ`) · `P1-11` (a outra metade) | `db.py` · `api.py` · `ARQUITETURA.md` · `tests/test_metricas.py` · `tests/test_config_perfis.py` (novo) |
| 3 ▸ | **`T-EDGE`** | `P1-10` (`lz5wVY9l`) · conclui `Q-4` (`Fe0UpFaF`) | `pesquisa/backtest_plataforma.py` · `pesquisa/validacao.py` · `VEREDITO-M4.md` (novo) |

`ARQUITETURA.md` aparece em dois territórios e isso é legal **só porque as ondas são seriais** —
a onda 2 nasce quando a 1 mergeou, como o `README.md` do M3 (§4c). Dentro de uma onda, nenhuma
sobreposição.

**`pesquisa/backtest_plataforma.py` é o eixo do pacote** — `validacao`, `tune`, `validar_oos`,
`validar_reversao*` e `validar_swing` todos o importam. Ele **não** é território de ninguém nas
ondas 1 e 2, de propósito: quem o reescreve é o `T-EDGE`, e reescrevê-lo é metade do `P1-10`
(implementar as políticas B e C no `backtest_ativo`). Worker das ondas 1-2 que precisar dele **lê e
para**.

##### O que já se sabe que os cards erram — conferir é entrega, não desvio (§14.4)

1. **O critério de aceite do `Q-2` está escrito para o layout antigo.** Ele manda rodar
   `grep -rn "ROBUSTO\|POSITIVO" *.py`, glob de raiz que hoje não acha nada. O comando válido é
   `grep -rn "ROBUSTO\|POSITIVO" --include=*.py .`.
2. **O `Q-2` não nomeia todos os culpados.** Ele lista `tune.py`, `validar_oos.py`,
   `validar_reversao.py` e `validar_reversao_maker.py`. O comando acima acha **um quinto**:
   `pesquisa/validar_swing.py:40` imprime `"  ROBUSTO ✅"` pela mesma metodologia de split-por-moedas,
   e o docstring dele diz `"Acha o melhor corte ROBUSTO (positivo nos dois) pra virar o default"` —
   é a armadilha exata que o card descreve. Ele está no território do `T-REGUA` por isso.
3. **`legado/` já está limpo:** `grep` nos `legado/*.py` não acha nenhum veredito. A preferência 1
   do card (mover para `legado/`) é coerente com o que o `P2-16` fez, e é a que a matriz recomenda.
4. **A lista de território nomeia as ORIGENS e não os DESTINOS, e isso quase reprovou código certo.**
   Levantado pelo worker do `T-REGUA` em 2026-08-23. A tabela acima dá a ele `pesquisa/tune.py` e
   irmãos; a preferência 1, que a própria §4f recomenda, **cria** `legado/tune.py` e mais quatro. Um
   `git diff --name-only` cruzado literalmente com a lista marcaria os cinco destinos como fora do
   território. **Os cinco `legado/<nome>.py` são território do `T-REGUA` por decorrência do card**, e
   ficam declarados aqui. Regra geral que decorre: **território que autoriza mover arquivo autoriza o
   caminho de destino** — e quando o destino for outro diretório, escreva-o na tabela, porque o
   portão não infere.
5. **O `Q-1` cita uma seção que não existe, e o briefing repetiu o erro.** O card manda seguir *"a
   ordem de impacto que a própria revisão definiu (§F32)"*. Conferido: `grep -rn "F32" --include=*.md .`
   **não acha nada no repositório inteiro**, e os achados do `REVISAO-ITEM1.md` param em **`F19`**. Os
   seis consertos vêm da lista ordenada no fim do `F19`, mais `F14`, `F1`/§3.2 e `F3`. A matriz
   transcreveu `§F32` do card para o briefing sem conferir — é a §14.4 outra vez, e desta vez o erro
   atravessou card **e** briefing sem ninguém notar até o worker abrir o arquivo.

##### O `P1-11` fecha em duas ondas, e isso está declarado ANTES (§13)

O card pede quatro coisas, e elas moram em três territórios:

| Item do aceite | Onde | Onda |
|---|---|---|
| cap geométrico da lev + teste unitário (`stop_dist=5%`, lev 20 → ≤14) | `autotrader.py` — `T-SIZING` | 1 |
| log do cap quando ele agir | `autotrader.py` — `T-SIZING` | 1 |
| contagem exposta em `/status` | `api.py` — `T-DECLARACAO` | 2 |
| fluxo manual avisa/recusa geometria degenerada | `web/index.html` — **nenhum território do M4** | — |

O último item é front, e **nenhum território deste marco escreve em `web/`**: o merge na `main`
publica no Vercel (§9.9), e front é território do M5/M6 desde o dia 1 (§9.2). Vira card novo, criado
pela matriz. **Dois commits num card, autorizados aqui e agora** — é o que separa isso de worker
atravessando fronteira.

> ⚠️ **Corrigido em 2026-08-23, no mesmo dia, e o erro era desta seção.** A linha acima dizia que o
> item do fluxo manual é `web/index.html` e só isso. **É falso, e um aviso no front não é guarda.**
> O worker do `T-SIZING` conferiu em vez de acreditar no briefing e mediu: `_alavancagem` tem **uma
> única** chamada em todo o repositório (`autotrader.py:163`), e `POST /confirmar` recebe
> `alavancagem` **do cliente** e a repassa direto para `simulador.abrir` (`api.py:681`). O cap
> geométrico do `P1-11` protege o auto-trader e **não alcança o fluxo manual**; quem tiver a
> credencial do painel abre 20x com stop de 9,5% por `curl`, sem carregar o navegador — a mesma
> forma da bandeira `PERMITIR_SEM_SENHA` que o `CLAUDE.md` §2 registra.
>
> A recusa virou o card **`P1-12`** (`xD9xBfoe`, `toca-risco`), com duas opções e uma recomendada: a
> rota (`api.py`) protege uma porta, o ponto de estrangulamento (`simulador.abrir`) protege a casa.
> O território dele é declarado quando a onda 2 for desenhada, depois de colher a onda 1 — não agora
> (§14.3 do `ORQUESTRACAO-ORCA.md`). O aviso visual no painel continua sendo card de front separado.
>
> **A lição, que é a mesma da §14.4 e agora tem um segundo caso:** a §4f foi escrita por quem ia
> auditar, e um território errado escrito pela matriz é invisível para o portão de fronteira — ele
> compara o diff com a lista, e a lista é que estava errada. O que pegou foi o briefing **pedir** que
> o worker conferisse os fatos do briefing.

O `Q-3` tem a mesma forma: o item *"o painel mostra qual perfil está ativo"* é front e sai junto, no
mesmo card novo. O que o `T-DECLARACAO` entrega do `Q-3` é o mecanismo (`db.py`), o catálogo
(`api.py`) e o racional escrito.

##### O que o território não isola aqui (§9.2b)

- **`db.CONFIG_PADRAO` é esquema-de-configuração**, e o `Q-3` mexe nele. Nenhum outro card do M4
  toca — mas `db.py` também é o `P2-36`. Por isso os dois estão no **mesmo** território, não em
  paralelo: o portão de fronteira aprovaria os dois e o merge é que quebraria.
- **`P2-36` quebra a suíte de propósito ao fechar.** `tests/test_metricas.py` está
  `xfail(strict=True)`; consertar `db.metricas()` vira XPASS e reprova o `pytest` até o teste ser
  promovido (§4d, ponto 3, e `CLAUDE.md` §6). Quem pegar o `T-DECLARACAO` precisa saber disso antes
  de abrir o arquivo.
- **`CLAUDE.md` é da matriz, não de worker** (`ORQUESTRACAO-ORCA.md` §8). O `Q-3` pede que ele
  declare *"mudar defaults de risco = decisão humana"*, e o `Q-2` pode invalidar a linha do
  `README.md:55` que lista `tune` e `validar_*` como pesquisa viva. As duas escritas ficam com a
  matriz, na integração.

##### Quatro dos dez cards são `toca-risco` — o auditor roda os portões e PARA (§9.8)

`P2-8`, `P2-18`, `P1-11` e `Q-3`. Os três primeiros **apertam** guarda, e apertar pode
(`CLAUDE.md` §2); ainda assim o veredito final é do dono. O `Q-3` é o oposto e o mais delicado: ele
propõe mexer no `risco_por_trade` (3%), na `alavancagem_padrao` (10x) e no `auto_lev_max` (20x) que
estão **vivos em produção com posição aberta**. A instrução da matriz para o `T-DECLARACAO` é a
metade reversível do "alinhar **ou** declarar" do card: **construir os dois perfis e escrever o
racional; não trocar o default vivo.** Trocar é assinatura do dono.

##### Por que a onda 1 tem esta forma

Os quatro cards do `T-REGUA` da tabela antiga viraram dois. `P2-8` e `P1-11` saíram para o
`T-SIZING` porque **os dois editam `autotrader._tamanho`/`_alavancagem`** e nenhum dos dois toca
`pesquisa/validacao.py` — juntá-los ao `Q-1` era herança de quando `scoring.py` e `autotrader.py`
apareciam na mesma linha da §4. `P1-11` inclusive **precisa** que `_alavancagem` passe a receber
`stop_dist`, que é assinatura que o `_tamanho` do `P2-8` também mexe: são o mesmo diff, e separá-los
em agentes paralelos é o erro que a §3 descreve.

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

#### 4g. Territórios das ondas 2 e 3 do M4 — declarados em 2026-08-23, depois de colher a onda 1

A onda 1 fechou e mergeou (`1804427`, `9fc76a5`, `1c38059`). O `ORQUESTRACAO-ORCA.md` §14.3 manda
reler o território da onda seguinte **depois** da colheita e **antes** do despacho, porque cada onda
estreita a próxima. Esta seção é essa releitura, e ela tem conteúdo: **o M4 cresceu de 10 para 13
cards**, e os três novos nasceram da auditoria da onda 1, não do planejamento.

| Onda | Território | Cards | Arquivos que pode escrever |
|---|---|---|---|
| 2 | **`T-PORTFOLIO`** | `Q-5` (`fPL6lccf`) | `pesquisa/backtest_portfolio.py` (novo) · `tests/test_portfolio.py` (novo) |
| 2 ‖ | **`T-DECLARACAO`** | `Q-3` (`CA6ezdNV`) · `P2-36` (`oDireXwJ`) · `P1-11` (a metade do `/status`) | `db.py` · `api.py` · `tests/test_metricas.py` · `tests/test_config.py` (novo) |
| 2 ‖ | **`T-GUARDA`** | `P1-12` (`xD9xBfoe`) · `P2-38` (`JS5YAkvV`) | `simulador.py` · `autotrader.py` · `ARQUITETURA.md` · `tests/test_guarda_risco.py` · `tests/test_sizing.py` · **`tests/test_abrir.py`** (acrescentado em 2026-08-23 — ver abaixo) |
| 3 ▸ | **`T-EDGE`** | `Q-7` (`W5GPISAV`) **→** `P1-10` (`lz5wVY9l`) · conclui `Q-4` (`Fe0UpFaF`) | `pesquisa/backtest_plataforma.py` · `pesquisa/validacao.py` · `tests/test_validacao.py` · `VEREDITO-M4.md` (novo) |

##### As três decisões de fronteira que este desenho toma, e o porquê de cada uma

**1. `P1-12` vai para `simulador.abrir`, e por isso mora com o `P2-38`, não com o `api.py`.** O card
oferece duas opções; a matriz recomenda a **B**, o ponto de estrangulamento. Os dois fluxos passam
por `abrir()`, então a recusa ali não se contorna por rota nova, cliente novo ou `curl` — e
`api.py:682` **já traduz** `ValueError` para `{ok: false, erro}`, então a rota não precisa mudar.
Consequência de território: `P1-12` é `simulador.py`, e o `P2-38` também (`_risco_posicao` mora lá,
mais a inversa em `autotrader._tamanho`). Os dois no mesmo território **não é conveniência: é a §3**
— eles editam o mesmo par de arquivos.

**2. `ARQUITETURA.md` é do `T-GUARDA`, não do `T-DECLARACAO`.** A opção C do `P2-38` é documentar em
`ARQUITETURA.md` §10 ("aproximações conhecidas do modelo"), que é exatamente onde o `Q-6` pôs as
irmãs dela. O `Q-3` não precisa do arquivo: o próprio card manda registrar o racional **no catálogo
de config do `P1-8`** (campo "racional" por parâmetro, em `api.py`) e nos comentários do
`db.CONFIG_PADRAO`. Território de doc tem um dono por onda.

**3. `Q-7` vai para a onda 3, junto do `P1-10` e ANTES dele.** Os dois escrevem
`pesquisa/validacao.py`, então não podem ser paralelos. E a ordem importa: o `Q-7` mexe no MDS, o MDS
é **portão** de emissão de veredito, e o `P1-10` é quem emite o veredito do marco. Rodar o `P1-10`
com o MDS subestimado é decidir a pergunta central do projeto com o instrumento que o `Q-7` diz estar
descalibrado. **Serial, `Q-7` primeiro.**

##### Correção da própria §4g, no mesmo dia: `tests/test_abrir.py` é do `T-GUARDA`

O `P1-12` põe uma recusa nova em `simulador.abrir()`. **Um card que adiciona recusa ao ponto de
estrangulamento inevitavelmente encosta nos testes que chamam esse ponto** — e a lista original
não trazia `tests/test_abrir.py`, que é justamente o arquivo de quem exercita `abrir()`.

O worker fez o certo: rodou a suíte, viu
`tests/test_abrir.py::test_teto_de_risco_desligado_deixa_passar` falhar, **não editou o arquivo**
(§9.4/P2 reprova arquivo fora da lista mesmo com o código certo), e subiu para a matriz com o
conserto descrito. A suíte na branch ficou em `1 failed, 490 passed, 1 xfailed`.

O teste faz `simulador.abrir(sid, 100.0, 20)` com preço 100 e stop 95 — `stop_dist` de 5% a 20x, que
é **exatamente a geometria degenerada** que o `P1-12` passou a recusar. A alavancagem alta ali existe
só para inflar o risco e provar que o teto desligado deixa passar; a geometria não é o assunto do
teste. Conserto que preserva a intenção: baixar a lev (a 10x a liquidação fica a 9% contra stop de
5%, geometria sadia) mantendo o risco grande.

**A leitura certa disto é a da §9.4: não é o agente extrapolando, é a onda que estava mal
desenhada** — e correção de plano é da matriz. É a mesma classe de erro da §4f de hoje de manhã, em
que a lista nomeava a origem do `git mv` e não o destino: **território que autoriza mudar um
comportamento autoriza os testes desse comportamento.** O portão não infere.

##### O que a onda 1 deixou pronto e muda o trabalho da onda 2

- **`autotrader._alavancagem` agora recebe `stop_dist`** e devolve lev capada pela geometria; a
  contagem vive em `autotrader.CAPS_GEOMETRIA` (`{"total", "ultimo"}`) e em `res["caps_geometria"]`
  por ciclo. **É isso que o `T-DECLARACAO` expõe em `/status`** — o nome não precisa ser descoberto.
- **`autotrader._tamanho` devolve `0.0` onde antes inflava para o piso.** Quem for reusar o sizing
  (o `Q-5` vai) tem de tratar o zero como "pular o sinal", não como erro.
- **`simulador._fill_stop` existe** e o `motivo_saida` pode terminar em `-gap`. Backtest de portfólio
  que compare com o histórico vivo precisa saber.
- **A régua tem `MDS_LIMITE`, `T_EFETIVO_MINIMO` e `PADRAO` travado**, e `walk_forward` **recusa**
  `criterio`/`modo`/`atribuir`/`block`/`purga` por assinatura. O `P1-10` roda a régua nova; ele não
  a re-parametriza.
- **`pesquisa/backtest_plataforma.py:82` não grava `ts_saida`**, e por isso a purga de borda de fold
  está implementada e **desliga sozinha** (`purga: INATIVA` no relatório). O vazamento da §2/P2
  continua presente e **não medido**, e empurra o resultado para **cima** — contra a conclusão
  negativa. **É a primeira coisa que o `T-EDGE` conserta**, porque o arquivo é dele.

##### O que continua fora de todo território do M4

O aviso visual no painel — a geometria degenerada mostrada antes do clique (`P1-11`) e o perfil de
risco ativo (`Q-3`). É `web/index.html`, o merge na `main` publica no Vercel (§9.9), e front é
território do M5/M6 desde o dia 1. Vira card de front próprio, criado pela matriz quando a onda 2
fechar — antes disso não há o que mostrar.

##### O `Q-3` é `toca-risco` e mexe no que está VIVO — a instrução é a metade reversível

O card propõe alinhar `risco_por_trade` (3%), `alavancagem_padrao` (10x) e `auto_lev_max` (20x) à
`BASE-CONHECIMENTO-TRADING.md`, que conclui 0,5-1% e lev ≤2x. **A instrução ao worker é construir os
dois perfis (`experimento` e `conservador`) e escrever o racional por parâmetro — sem trocar o
default vivo.** Trocar é assinatura do dono, e ele decide com os dois perfis na mão em vez de no
abstrato. O card autoriza isso explicitamente: *"alinhar **OU** declarar"*.

Um número da onda 1 que o `Q-3` precisa ter na mão e não estava no card: a aproximação de liquidação
`0,9/lev` é conservadora até **lev 20** e vira **otimista acima** (`ARQUITETURA.md` §10, medido no
`Q-6`). O `auto_lev_max` vivo é exatamente 20 — o teto está em cima da fronteira.

---

#### 4e. `T-FRONT-PERF` — território do `P2-37`, declarado em 2026-08-22

O M5/M6 fechou o front, e a primeira medição externa dele — Lighthouse 13.4.0 no domínio de
produção, rodada pelo dono em 2026-08-22 20:48 — deu **performance 0,86**. Este território existe
para atacar isso. Ele é **paralelo a tudo pela mesma razão que o M5 sempre foi** (§4, M5): o front
tem território exclusivo e não encosta em backend, endpoint ou dado.

| Território | Card | Arquivos que pode escrever |
|---|---|---|
| **`T-FRONT-PERF`** | `P2-37` (`rpABcTFh`) | `web/index.html` · `web/vendor/` · `PERF-FRONT-2026-08-22.md` (novo) |

Fora da lista, e o motivo de cada um: `README.md` é do `T-DOCS` na onda 3 do M3, que roda agora;
`DESIGN.md` é a fonte da verdade visual e **o resultado visível não pode mudar** — se para ganhar
performance for preciso mudar o que se vê, o worker para e reporta; e nada de backend, porque o
card é de front e a §4 do M5 diz "zero mudança de backend, endpoint ou dado".

**A aritmética do 0,86, para não se atacar o número errado.** O peso é `TBT 30 · LCP 25 · CLS 25 ·
FCP 10 · SI 10`, e três das cinco métricas já estão em 1,00:

| Métrica | Valor | Score | Perde |
|---|---|---|---|
| Total Blocking Time | 0 ms | 1,00 | — |
| Cumulative Layout Shift | 0 | 1,00 | — |
| Largest Contentful Paint | 1,1 s | 0,91 | 2,2 pts |
| First Contentful Paint | 1,1 s | 0,78 | 2,2 pts |
| **Speed Index** | **7,2 s** | **0,00** | **10 pts** |

**Todo o buraco é o Speed Index**, e os 4,4 pontos restantes são FCP e LCP empatados em 1,1 s.

**⚠️ A medição é suspeita, e conferir isso é o primeiro passo do card — não o último.** O relatório
denuncia a própria máquina: `benchmarkIndex` 2496, `lh:storage:clearBrowserCaches` levando **4,06 s**
e `lh:gather:getBenchmarkIndex` **1,02 s**. O `fetchTime` é 20:48 de 2026-08-22 — o mesmo intervalo
em que esta máquina rodava os workers do M3 e várias execuções da suíte de testes. E o sintoma
combina com máquina saturada, não com front lento: `observedFirstPaint` = `observedFirstContentfulPaint`
= **11.560 ms**, ou seja **nem o fundo da página pintou** por 11,5 s, enquanto a thread principal
ficava **ociosa** entre 1.440 ms e 4.164 ms (tabela `main-thread-tasks`). Os sete primeiros quadros
do filmstrip são o mesmo JPEG de cor chapada. Página que não pinta com CPU ociosa e rede terminada
não é página lenta; é ambiente de medição ruim.

**Regra que decorre: nada se conserta antes de a medição ser reproduzida com a máquina quieta.** Se
o Speed Index voltar ao normal sozinho, o card muda de tamanho — vira FCP+LCP, que é real e vale
4,4 pontos — e a conclusão "o 0,86 era a máquina" é uma entrega tão legítima quanto um patch.

**O que é defeito de verdade, medido e independente do ruído da máquina.** Estes saem do relatório e
não dependem de cronômetro:

1. **Quatro recursos bloqueiam a renderização no `<head>`**, e o Lighthouse estima 840 ms de FCP/LCP
   nisso: `vendor/chart.umd.min.js` (72,6 KB transferidos), `vendor/lightweight-charts...js`
   (51,9 KB), `config.js` e a folha do Google Fonts. Os três scripts são `<script src>` **síncronos**
   em `web/index.html:15-17`, antes de existir uma linha de markup.
   ⚠️ **A armadilha do `defer`, e ela é real:** o código da aplicação é um `<script>` **inline no fim
   do `<body>`**, e script inline roda **antes** de qualquer script `defer`. Pôr `defer` no
   `config.js` faz o `API` sumir na hora do boot. As duas bibliotecas são outro caso — o inline só
   as usa quando desenha gráfico —, mas isso tem que ser **verificado**, não suposto.
2. **124 KB do que bloqueia é código que a primeira tela não usa.** `unused-javascript` mede
   `lightweight-charts` **92,3% não usado** (47,9 KB) e `chart.umd.min.js` **58,4%** (34,2 KB). São
   as bibliotecas de gráfico, e gráfico não é a primeira coisa que a página mostra. Carregá-las sob
   demanda tira o peso do caminho crítico inteiro, em vez de só adiá-lo.
3. **A animação `pulse` não é composta.** `web/index.html:197` anima `box-shadow`, que o compositor
   não sabe fazer — cada quadro do ponto "ao vivo" repinta. O `non-composited-animations` aponta
   exatamente `body > div.statusbar > span.sb-live > span.dot`. O equivalente composto anima
   `opacity`/`transform` num pseudo-elemento, e **o resultado visível tem que ser o mesmo**.
4. **Um reflow forçado de 103 ms no boot.** `forced-reflow-insight` aponta `web/index.html:1691`, que
   é a `folgaStatusBar()` lendo `sb.offsetHeight` de forma síncrona logo depois de mexer no DOM. O
   segundo, de 4 ms, é o `TEMA` na linha 939 lendo `getComputedStyle` — pequeno, mas é a mesma classe.

**O que NÃO se conserta, e por quê — decisão registrada antes da implementação.** O
`unminified-css` promete 5,7 KB minificando o `<style>` inline. **Não minifique.** Aquele bloco é
comentado linha a linha com o porquê de cada token medido do CoinMarketCap, e o `DESIGN.md` §
Typography depende de ele continuar legível; trocar 5,7 KB pela justificativa das decisões de design
é o negócio errado num projeto onde a próxima sessão chega sem histórico. Se o dono quiser os 5,7 KB,
o caminho é minificar **no build**, não na fonte — e isso é outro card.

**Duas coisas que o relatório mostra e não são do front — reportar, não consertar.** Toda primeira
chamada ao backend paga um **preflight CORS** (cinco deles no trace: `/estado`, `/sentimento`,
`/funding`, `/saidas`, `/precos`), cada um custando um round-trip inteiro — o `/estado` gasta
420→769 ms no preflight antes de 769→1142 ms na chamada real. Some-se a isso `serverResponseTime` de
**334,8 ms** na VM. Os dois são backend (`Access-Control-Max-Age` e latência do uvicorn), fora do
território, e viram card novo se o worker os confirmar.

**Portão do `P2-37`:** Lighthouse rodado pelo próprio worker, na mesma URL de produção, **com a
máquina quieta**, antes e depois, com os dois JSONs resumidos no `PERF-FRONT-2026-08-22.md` e a
saída colada no relatório. Passa com **performance ≥ 0,95 e as cinco métricas nomeadas**, ou com a
demonstração de que o valor de origem não reproduz — e aí o veredito é esse, escrito.

**⚠️ Merge deste território É publicação.** O `web/` sobe sozinho para o Vercel ao entrar na `main`
(§9.9). Aqui o merge não é retrabalho se errar: é produção. O portão roda antes, e o dono decide o
merge.

> ### ✅ Portão do `P2-37` — RODADO e PUBLICADO em 2026-08-22
>
> Merge `724881a`. Publicação confirmada por hash: o Vercel serve `614e64ba7725283d`, byte a byte o
> `724881a:web/index.html`.
>
> **O passo 1 tinha razão, e o preço de não tê-lo feito seria consertar o que não estava quebrado.**
> O Speed Index de 7,2 s **não reproduz**: cinco rodadas (três do worker, duas do auditor) deram
> 1,3 / 0,9 / 0,9 / 1,2 / 0,8 s. Era ruído de máquina.
>
> **Mas o buraco não sumiu — mudou de lugar, e é maior do que esta seção previa.** A §4e registrava
> LCP em 1,1 s / 0,91 lendo o relatório ruidoso; o que reproduz é **LCP 2,1–2,3 s, score 0,51–0,60,
> cerca de onze dos catorze pontos**. O elemento de LCP é o `div#gate-foot`, que espera o **401 do
> backend**: `timeToFirstByte 93 ms` contra `elementRenderDelay 1385 ms`. E o maior item isolado do
> caminho crítico é o **setup de conexão — 672 ms** (DNS 8 + TCP 325 + TLS 339) até a África do Sul.
>
> | Produção | perf | FCP | LCP | TBT | CLS | SI |
> |---|---|---|---|---|---|---|
> | antes (mediana de 5) | 0,89 | 1,1 s | **2,1 s (0,55)** | 0 ms | 0,001 | 0,9 s |
> | depois (3 rodadas) | **0,90** | 0,7 s | **2,0 s (0,62)** | 0 ms | 0,001 | 0,8 s |
>
> **O ganho é real e é modesto, e o teto está dito:** o LCP é dominado por esperar o backend
> atravessando um oceano. O maior lever restante era mostrar o gate de saída, e **o dono decidiu que
> não** — quem tem credencial válida no `localStorage` passaria a ver um flash de login a cada
> carregamento, e foi fricção de login que um dia levou a desligar a senha no servidor.
>
> ⚠️ **A11y apareceu em 1,00 e isso não é conserto**: o `td-has-header` voltou `notApplicable`
> porque a tabela de sinais estava vazia na hora da medição. Com sinais pendentes as duas falhas
> voltam. SEO segue em 0,90 — nenhum dos dois estava no escopo.
>
> **Duas premissas desta própria §4e foram derrubadas por medição, e as duas eram do auditor:**
> o `Access-Control-Max-Age: 600` **já existe** (preflight não vira card), e os "334,8 ms de
> latência do uvicorn" são atribuição errada — TTFB 338 ms com RTT de TCP em 333 ms significa que o
> servidor pensa **~5 ms**. É card de **região**, e de custo, não de backend.
>
> **O que fica para a próxima sessão:** `PERF-FRONT-2026-08-22.md` na raiz, com o comando exato
> copiável, o método do A/B ancorado em hash, e as duas armadilhas de ambiente no Windows — o
> `EPERM` do `chrome-launcher` que mata laço de medição, e a regra de nunca rodar duas instâncias do
> Lighthouse em paralelo, porque uma mede a outra.

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
