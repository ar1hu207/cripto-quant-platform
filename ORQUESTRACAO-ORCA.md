# Orquestração de sessões com a CLI do Orca

**Data:** 2026-08-22 · **Para:** a sessão-matriz que vai distribuir os tickets do M2
**Tudo abaixo foi verificado contra a CLI real desta máquina**, não escrito de memória.
Quando algo não foi testado, está marcado ⚠️ **NÃO VERIFICADO**.

---

## 1. O que é a sessão-matriz

A **matriz** é a sessão que despacha: ela cria as worktrees, lança os agentes, colhe os
resultados e é a única que fala com o Trello e com a `main`. Os **workers** codam e param.

Regra que não se quebra: **worker não faz push, não mergeia, não toca no Trello, não acessa a
VM.** Ele termina com commits na própria branch e um relatório. Quem integra é a matriz.

O motivo é concreto: em 2026-08-21 duas sessões numeraram cards ao mesmo tempo e seis números
passaram a responder por dois cards diferentes. Estado compartilhado precisa de um escritor só.

---

## 2. Fatos desta máquina (verificados em 2026-08-22)

```
orca                → C:/Users/aboni/AppData/Local/Programs/orca/resources/bin/orca
orca status         → runtime "ready", app rodando
repo registrado     → id 2d306948-2caa-4336-b5b8-0c6c30773d2e
                      path C:/Users/aboni/Pesquisas/1  (ar1hu207/cripto-quant-platform)
worktrees nascem em → C:/Users/aboni/orca/workspaces/1/<nome>
orca account list   → NENHUMA conta gerenciada (ver §6)
```

O esquema completo de 231 comandos sai em `orca agent-context --json`. Leia de lá em vez de
adivinhar flag.

---

## 3. ⚠️ A armadilha que já mordeu: a `main` LOCAL fica velha

`orca worktree create --base-branch main` usa a **branch local**, não `origin/main`. E a local
fica para trás sempre que alguém empurra com `git push origin HEAD:main` a partir de uma worktree
— que é como esta sessão empurrou a noite inteira.

Em 2026-08-22 a `main` local estava **27 commits atrás**: uma worktree criada ali nasceria sem o
M1 e sem o M6 inteiros, e ninguém perceberia até o merge.

**Antes de qualquer despacho, sempre:**

```bash
git -C C:/Users/aboni/Pesquisas/1 fetch origin main:main
git -C C:/Users/aboni/Pesquisas/1 rev-list --count main..origin/main    # tem que dar 0
```

O `fetch origin main:main` adianta a branch local sem precisar de checkout — importante, porque o
checkout compartilhado costuma estar noutra branch com 7-8 sessões do usuário dentro dele.

---

## 4. Despachar um worker

```bash
orca worktree create \
  --repo id:2d306948-2caa-4336-b5b8-0c6c30773d2e \
  --name t-<territorio> \
  --base-branch main \
  --agent claude \
  --prompt "$(cat brief-<territorio>.md)" \
  --json
```

**Com `--agent --json`, o handle do agente vem em `result.agentTerminalHandle`.** Runtimes mais
antigos devolvem só `result.startupTerminal.handle` — trate os dois. Guarde o handle: é por ele
que a matriz colhe o resultado.

Sobre linhagem: por padrão o Orca registra a worktree nova como **filha** do contexto que a criou,
e isso aparece em `parentWorktreeId` / `childWorktreeIds` no `worktree ps`. É o que amarra os
workers à matriz. Use `--parent-worktree active` para explicitar, ou `--no-parent` quando a tarefa
for realmente independente.

⚠️ **VERIFICADO EM 2026-08-22, e a resposta é não: `--agent claude` NÃO funciona nesta máquina.**
A worktree nasce certa (base e SHA corretos), mas sem conta gerenciada (§6) o agente não sobe — o
Orca abre um PowerShell cru e **digita o briefing inteiro dentro dele**. O terminal fica preso em
continuação de linha (`>>` repetido) e nada executa. Não é perigoso, é só inerte, e passa
despercebido se você olhar só o JSON de criação, que volta `ok: true` e até um handle.

**Como saber em 10 segundos:** `orca terminal list --json`, ache o terminal cujo `worktreePath`
seja o da worktree nova, e olhe o `preview`. Se for `>>` repetido, o agente não subiu.

O caminho que funcionou está no §6(b). E a lição vale além do Orca: **confirme o primeiro worker
antes de abrir a frota** — o custo de descobrir isso com um é um minuto, com quatro é a onda toda.

---

## 5. Colher o resultado — o ponto que o usuário mais quer

```bash
orca terminal wait --terminal <handle> --for exit --timeout-ms 3600000 --json
orca terminal read --terminal <handle> --json
```

- `--for exit` espera o agente terminar; `--for tui-idle` espera ele ficar ocioso.
- `terminal read` devolve **o fluxo acumulado**, com escapes removidos. Use `--screen` quando a
  resposta depender de *como a tela está desenhada* e não do que foi emitido — o resultado informa
  `source: stream|screen`, então dá para saber qual pergunta foi respondida.
- `--cursor` e `--limit` paginam saída longa.

**Mas não confie no relatório do worker.** O que vale é o git:

```bash
git -C C:/Users/aboni/orca/workspaces/1/<nome> log --oneline main..HEAD
git -C C:/Users/aboni/orca/workspaces/1/<nome> diff --name-only main...HEAD
```

O segundo comando é o **portão de fronteira**: cruze a lista de arquivos com o território
declarado na §4 do `PLANO-EXECUCAO-2026-08-20.md`. Arquivo fora do território reprova o trabalho
mesmo com o código bom.

### Acompanhar a frota

```bash
orca worktree ps --limit 20 --json
```

Devolve, por worktree: `branch`, `workspaceStatus`, `lastActivityAt`, `parentWorktreeId`,
`childWorktreeIds`, `linkedIssue`. É o painel da matriz.

---

## 6. ⚠️ Não há conta gerenciada — decida antes de despachar

`orca account list` devolve **nenhuma conta Claude e nenhuma Codex**. Existem dois caminhos:

**(a)** `orca account add --agent claude` — login interativo, **o usuário precisa fazer**. Depois
disso o `--agent claude` do §4 deve funcionar.

**(b) Fallback que já foi usado com sucesso nesta sessão:** criar a worktree sem `--agent` e subir
o CLI local, que já está autenticado:

```bash
orca worktree create --repo id:<repoId> --name t-x --base-branch main --json
orca terminal create --worktree branch:t-x \
  --command "claude -p \"$(cat brief.md)\" --permission-mode bypassPermissions --session-id <uuid>" --json
```

Fixar `--session-id` é o que permite ao usuário entrar depois com `claude --resume <uuid>` de
dentro da worktree. Sem isso, não há como conversar com o worker.

⚠️ **VERIFICADO EM 2026-08-22: não funciona sem conta gerenciada** — ver o §4. Enquanto
`orca account list` estiver vazio, **use (b)**.

**Refinamento de (b), usado para despachar as duas ondas do M2.** O `orca terminal create` também
serve, mas o `--command` passa por um shell do Windows, e um briefing de 12 KB com markdown,
crases e aspas não sobrevive à citação. O que funcionou foi mais simples: criar a worktree pelo
Orca (**sem** `--agent`) e lançar o CLI local a partir da própria sessão-matriz, com o briefing
vindo de arquivo:

```bash
orca worktree create --repo id:<repoId> --name t-<territorio> --base-branch main --json
cd C:/Users/aboni/orca/workspaces/1/t-<territorio>
claude -p "$(cat /caminho/brief-<territorio>.md)" --permission-mode bypassPermissions        --session-id <uuid-fixo>
```

Rodando isso **em segundo plano pela ferramenta de shell da própria matriz**, o harness avisa
quando cada worker termina — o que substitui o `orca terminal wait` do §5 e não depende de handle
nenhum. A worktree continua sendo do Orca e aparece no app; só quem lança o agente é outro.

Guarde o `--session-id`: é por ele que o dono entra depois com `claude --resume <uuid>` de dentro
da worktree.

---

## 7. Como dividir o M2 — território, não card

**Não despache um agente por card.** Contado nas citações `arquivo:linha` dos documentos de
investigação: `api.py` é tocado por 10 cards e `simulador.py` por 6. Um agente por card poria sete
agentes editando `api.py` ao mesmo tempo.

⚠️ **A tabela abaixo é histórica.** As ondas do M2 foram redesenhadas em 2026-08-22 (commit
`f3d2ce9`): quatro agentes viravam cinco violações das regras do próprio plano — `T-OPERACAO` era
território de VM, que worker não acessa; quatro agentes estouram o teto de três da §9.11; e o
`P2-15` exigia escrita em `api.py`, que o `T-SINAL` só podia ler. **A fonte é a §4 + §4b do
`PLANO-EXECUCAO-2026-08-20.md`, não esta tabela.** Ela fica aqui porque o raciocínio de "por que
não um agente por card" continua valendo:

| Onda | Agente | Arquivos | Cards |
|---|---|---|---|
| 1 | `T-SINAL` | `signal_engine.py`, `autotrader.py` | P2-9, P1-9, P2-15 |
| 1 ‖ | `T-EXEC` | `simulador.py`, `validacao.py` | P2-10 |
| 1 ‖ | `T-MERCADO` | `mercado.py`, `dca.py` | P1-5, P2-13 |
| 1 ‖ | `T-OPERACAO` | `logbot.py`, `deploy/`, VM | P2-1, P2-3, P2-5 |
| 2 ▸ | `T-API-DADOS` | `api.py`, `db.py` | P2-11, P1-4 |

A onda 2 espera a 1 fechar, porque `api.py` é território do `T-SINAL` na onda 1.

**Ataque o `P2-3` cedo.** Ele põe git na VM e transforma o deploy em `git pull && systemctl
restart`. Enquanto não existir, cada card do M2 vai precisar chegar na VM pelo caminho difícil —
ver a memória `deploy-vm-cripto-bot`.

---

## 8. O que pôr no briefing de cada worker

1. **O card inteiro embutido** — o worker não tem token do Trello.
2. **A lista de arquivos permitidos**, e a instrução de **parar e reportar** se precisar de um de
   fora, nunca editar.
3. **Proibições:** sem `push`, sem merge, sem trocar de branch, sem Trello, sem VM/SSH/`az`, sem
   mexer em `settings.json` ou `CLAUDE.md`.
4. **Registro de raciocínio obrigatório na mensagem do commit:** a causa, por que a correção ataca
   a causa, e **como seria a versão-sintoma que ele não fez**. Foi isso que permitiu aprovar cards
   `toca-risco` lendo diff em vez de acreditar em relato — e os workers escreveram sem portão
   obrigando, só porque o briefing pediu.
5. **O comando do critério de aceite, com a saída colada no relatório.** "Validado" sem comando
   rodado não conta.
6. **Exija que a prova fique NO REPOSITÓRIO, reexecutável.** Aprendido na onda 1 do M2, e custou
   caro: dois dos três workers escreveram provas excelentes em arquivo temporário e as perderam
   ao terminar. O relatório listava `10 passaram, 0 falharam` e **não havia o que reexecutar** —
   a matriz teve de escrever a auditoria do zero, duas vezes. O terceiro pôs a prova dentro do
   próprio módulo do território (`python simulador.py` roda 11 asserções) e foi reexecutado em
   segundos.

   Repare na armadilha: um arquivo `prova_<x>.py` novo **reprova no portão de fronteira** se não
   estiver na lista do território. Então ou o território declara o arquivo de prova, ou a prova
   mora dentro de um módulo que já é do território, sob `if __name__ == "__main__"`. Diga qual
   no briefing — senão o worker escolhe o temporário, que é o que não sobrevive.
7. **Peça o número do card no assunto do commit** (`[P2-9] ...`). Um território da onda 1 entregou
   quatro commits sem prefixo: o trabalho estava certo, mas ligar commit a card virou leitura de
   mensagem em vez de `git log --oneline | grep`. Convenção barata, auditoria muito mais rápida.

---

## 9. Fronteiras que o classificador bloqueia — não insista

Editar `settings.json` de permissões · alterar regra de NSG · `az role assignment create` ·
lançar `nohup claude -p` sem a regra `Bash(nohup claude -p *)` em `permissions.allow`.

Todas são a mesma família: **o agente ampliando o próprio alcance.** Peça ao usuário e siga.
Insistir queima chamadas e não passa — nesta sessão perdi seis tentativas no `role assignment`
antes de aceitar e ir para a alternativa.

---

## 10. Estado em 2026-08-22, para a matriz não redescobrir

- **M1 e M6 fechados.** M1 mergeado *e* deployado na VM; M6 no ar no Vercel.
- **30 cards em ✅ Feito**, 24 em Triagem, 1 em Validando (`Q-4`, acumulando amostra até o M4).
- **`auto_trade=1`**, mas a trava diária disparou hoje e solta sozinha na virada do dia.
- **Backup diário existe** desde hoje, 03:17, para Azure Blob.
- A série `P2-` é sequência compartilhada — **fluxo novo nasce com prefixo próprio** (a pesquisa
  quant virou `Q-1..6` depois de colidir duas vezes num dia).
- **Chave canônica de um card é o shortLink do Trello**, nunca o `[P2-n]` do título.

## 13. O que a onda 1 do M2 ensinou sobre COLHER (2026-08-22)

O §5 diz como ler o terminal. O que faltava era o que fazer com o que se lê.

- **A colheita é git, e a auditoria é comando seu, não do worker.** Os três territórios da onda 1
  passaram no portão de fronteira de primeira — nenhum arquivo fora da lista, árvore limpa. O que
  não passou de graça foi o P1: sem a prova versionada (§8.6), a matriz escreveu duas auditorias
  independentes, de 22 e 18 asserções. **Deu mais trabalho e valeu mais**: auditoria independente
  pega o que o teste do autor não pega por construção, porque nasce da mesma leitura errada.
- **Rode a auditoria de novo DEPOIS do merge, não só na branch.** É o único momento em que dois
  territórios existem juntos. As duas auditorias da onda 1 foram reexecutadas sobre a `main` já
  mesclada; se algum território tivesse mexido no mesmo dicionário do outro, é ali que aparece.
- **Confira o raio de alcance do que o worker mudou no BANCO, não só no código.** O `P2-10` passou
  a gravar `NULL` onde antes ia `0.0`. Isso só é seguro se ninguém somar a coluna — e a única
  forma de saber é varrer o repositório atrás de consumidor (`trades.funding`: zero). O portão de
  fronteira não pega isso: o arquivo era do território, o efeito não.
- **Um card pode fechar em duas ondas, desde que o PLANO diga antes.** Dois cards do M2 tinham a
  linha final em `api.py`, território de outra onda. Declarar isso na §4b antes do despacho é o
  que separa "dois commits num card, autorizado" de "worker atravessou a fronteira".
- **Nem todo card do plano é despachável.** O `T-OPERACAO` do M2 era dono de "logbot.py, deploy/,
  VM" — e worker não acessa a VM. Dois dos três cards dele eram da matriz por definição. Ao ler o
  marco, separe antes de despachar: o que é arquivo vai para worker, o que é produção fica com
  quem tem `az`.
- **Card pode estar errado sobre um fato, e o fato manda.** O `P2-3` afirmava que o repositório é
  público; ele é privado. Isso mudou a execução inteira (o clone precisou de deploy key) e é
  decisão do dono, não da matriz. Verifique os fatos do card antes de executá-lo, não durante.

---

## 11. Operar o Trello pela API (só a matriz)

IDs estáveis do quadro **Trading Bot** (`https://trello.com/b/haBYRC0E`), para a matriz ler e
escrever sem redescobrir:

| Recurso | ID |
|---|---|
| Board | `6a865ec785598352bd1b2c7d` |
| 📥 Triagem | `6a8660d73671baf5cca11716` |
| 🎯 Priorizado | `6a8660d8486c073850e65919` |
| 🔨 Fazendo | `6a8660d9c2ad0ba5601b89ec` |
| 🔍 Validando em produção | `6a8660d9301d47a0ac35d532` |
| ✅ Feito | `6a8660da98dbcdcc67ee0cf7` |
| 🧊 Bloqueado | `6a8660daab864fc011e51ce8` |

Labels de marco: `M1 sobreviver sozinho` (lime) · `M2 numeros verdadeiros` (pink) ·
`M3 base AI-first` (sky_dark) · `M4 regua da pesquisa` (purple_dark) · `M5 front` (blue_dark) ·
`M6 front CMC`. Labels de tipo: `P0-crítico`, `P1-bug`, `P2-operação`, `backend`, `front`,
`infra-azure`, `pesquisa-quant`, `toca-risco`.

**Credenciais: peça ao dono; o token NUNCA entra no repositório.** Existe um token permanente
(expiration=never) que as sessões anteriores guardaram em `trello.py` no scratchpad — se a sua
sessão não o tiver, peça. A URL de autorização usa a API key do dono
(`trello.com/1/authorize?expiration=never&scope=read,write&response_type=token&key=<key>`).

Regras (do `CLAUDE.md` §4 e da §9.6b do plano): chave canônica = **shortLink**; só a matriz
cria/renumera/renomeia card; worker move apenas Triagem→Fazendo; todo fechamento leva commit +
comando de aceite com a saída colada.

## 12. Fallback sem Orca: `claude -p` em worktree manual

Se o Orca estiver fora do ar, o método manual que fechou o M1 e o M6:

```bash
git -C C:/Users/aboni/Pesquisas/1 fetch origin main:main          # SEMPRE primeiro (§3)
git -C C:/Users/aboni/Pesquisas/1 worktree add -b terr/<x> C:/Users/aboni/Pesquisas/wt/<x> main
cd C:/Users/aboni/Pesquisas/wt/<x>
nohup claude -p "$(cat brief.md)" --permission-mode bypassPermissions --session-id <uuid-fixo> > log 2>&1 &
```

- **Fixe o `--session-id`**: é o que permite retomar depois com `claude --resume <uuid>` de
  dentro da worktree. As transcrições ficam em
  `~/.claude/projects/C--Users-aboni-Pesquisas-wt-<x>/<uuid>.jsonl` e **não aparecem** no
  `/resume` de outras pastas — o Claude Code indexa sessão por diretório.
- `claude -p` só imprime **no fim**. O sinal de vida durante a execução é o git da worktree
  (`git log`, `git status`), não o stdout. Não ponha `| tail` no lançamento: o log fica vazio
  e o worker parece travado sem estar.
- Lançar exige a regra `Bash(nohup claude -p *)` em `permissions.allow` do dono — sem ela o
  classificador bloqueia, e agente não edita a própria permissão (`CLAUDE.md` §8).
