# PERF-FRONT — `P2-37`, 2026-08-22

Território `T-FRONT-PERF` (plano §4e). Base `origin/main` = **`1bb6908`**. Branch `t-front-perf`.
Arquivos tocados: **só `web/index.html`** (mais este documento).

Escrito para quem chegar depois. Se você está aqui porque o Lighthouse voltou a cair, comece
pelo §1: **a primeira pergunta não é "o que está lento", é "a medição vale?"**.

---

## 0. Veredito, em quatro linhas

1. **O Speed Index de 7,2 s não reproduz.** Três rodadas na produção deram 1,3 s / 0,9 s / 0,9 s.
   Era ruído de máquina, como a §4e suspeitava. Os 10 pontos que ele "perdia" não existiam.
2. **O buraco real é outro, e é maior do que a §4e previa: o LCP.** Ele está em 2,1 s (score
   0,55–0,60), não nos 1,1 s / 0,91 do relatório de origem. Sozinho responde por ~11 dos 14 pontos.
3. **A causa do LCP é a espera pelo backend**, não peso de página — e boa parte dela é *setup de
   conexão* (672 ms de DNS+TCP+TLS até a África do Sul), que é o que dá para atacar do front.
4. Os quatro defeitos que a §4e lista como reais foram corrigidos e **medidos em A/B controlado**.
   Falta o passo que não é meu: o número final na produção só existe depois do merge (§9).

---

## 1. O comando exato

Copiável, e é o mesmo nas três medições deste documento — o do dono em 20:48, as minhas de
origem e as do A/B. Trocar qualquer flag invalida a comparação.

```bash
export CHROME_PATH="C:/Program Files/Google/Chrome/Application/chrome.exe"

npx -y lighthouse@13.4.0 https://cripto-quant-dashboard.vercel.app/ \
  --preset=desktop \
  --only-categories=performance,accessibility,best-practices,seo \
  --chrome-flags="--headless=new --no-sandbox --disable-gpu" \
  --output=json --output-path=./lh.json --quiet
```

O `--preset=desktop` já implica: `formFactor` desktop, `screenEmulation` desabilitado,
`cpuSlowdownMultiplier` 1, throttling `rttMs` 40 / `throughputKbps` 10240, `throttlingMethod`
`simulate`.

Duas armadilhas de ambiente no Windows, as duas já pagas:

- No fim da execução o `chrome-launcher` estoura `EPERM ... rmSync` limpando o próprio tempdir.
  **O JSON já foi escrito nesse ponto.** Se você põe isso num laço, use `|| true` — senão o
  laço morre depois da primeira rodada e você mede um terço do que pensa que mediu.
- Rodar em série, uma por vez. Duas instâncias do Lighthouse na mesma máquina medem uma à outra.

Para extrair as cinco métricas de um JSON sem abrir o relatório:

```bash
node -e "const r=require('./lh.json');
for(const id of ['first-contentful-paint','largest-contentful-paint','total-blocking-time',
                 'cumulative-layout-shift','speed-index'])
  console.log(id, r.audits[id].displayValue, 'score', r.audits[id].score);
console.log('perf', r.categories.performance.score, 'benchmarkIndex', r.environment.benchmarkIndex);"
```

---

## 2. Passo 1 — a medição de origem **não** reproduz

O relatório do dono (2026-08-22 20:48) deu **performance 0,86** com **Speed Index 7,2 s /
score 0,00** — dez dos catorze pontos perdidos numa métrica só. O plano §4e já desconfiava da
medição. **A desconfiança estava certa: o 7,2 s não reproduz.**

Três rodadas na mesma URL, mesmo comando, mesma máquina, em série:

| Rodada | `fetchTime` | `benchmarkIndex` | perf | FCP | LCP | TBT | CLS | **Speed Index** |
|---|---|---|---|---|---|---|---|---|
| 1 | 20:58:41Z | **1336** | 0,86 | 1,1 s (0,79) | 2,2 s (0,55) | 0 ms (1,00) | 0,029 (1,00) | **1,3 s (0,89)** |
| 2 | 20:59:25Z | **2148** | 0,89 | 0,9 s (0,92) | 2,1 s (0,58) | 0 ms (1,00) | 0,001 (1,00) | **0,9 s (0,99)** |
| 3 | 20:59:41Z | **2164** | 0,89 | 0,9 s (0,92) | 2,1 s (0,60) | 0 ms (1,00) | 0,001 (1,00) | **0,9 s (0,98)** |
| **mediana** | | 2148 | **0,89** | 888 ms | 2134 ms | 0 ms | 0,001 | **894 ms** |

**Veredito: o Speed Index de 7,2 s era ruído de máquina.** Ele reproduz em 0,9–1,3 s, com score
0,89–0,99 em vez de 0,00. Não existe conserto de front para ele porque não existe o defeito.

Nota sobre o `benchmarkIndex`, que é onde a leitura fica mais interessante do que o esperado.
O plano previa que ele **subiria** acima de 2496 se a origem tivesse sido medida numa máquina
engasgada. Ele **desceu**: 1336, 2148, 2164, todos abaixo dos 2496 da origem. Ou seja, a minha
máquina estava **mais** carregada que a do dono (o agente `T-DOCS` do M3 roda em paralelo), e
ainda assim o Speed Index voltou ao normal. Isso reforça o veredito em vez de enfraquecê-lo:
se nem numa máquina pior o número volta a aparecer, ele não era da página.

A correlação interna confirma: a rodada 1 é a de `benchmarkIndex` mais baixo (1336, máquina mais
lenta) **e** a de piores FCP/SI. As rodadas 2 e 3, com `benchmarkIndex` ~2150, batem entre si em
todas as cinco métricas. A dispersão do painel é a dispersão da máquina.

### 2b. O buraco não sumiu — ele mudou de lugar

Descobrir que o SI era ruído **não fecha o card**, e aqui o §4e ficou desatualizado por conta da
própria medição ruim que ele denunciava. O §4e registra `LCP 1,1 s / score 0,91`, perdendo 2,2
pontos. O que reproduz é:

**LCP 2,1–2,2 s, score 0,55–0,60 — perdendo ~10 a 11 pontos dos 25 do peso.** As três rodadas
concordam. Agora é o LCP que carrega o buraco quase inteiro, e os 0,89 de mediana já são melhores
que os 0,86 de origem sem que uma linha tivesse sido tocada.

**Qual é o elemento de LCP, e por que ele é lento** — isto é o que importa para a próxima sessão:

```
LCP element: body > div#gate > form#gate-form > div#gate-foot
nodeLabel:   "autenticando em\nhttps://cripto-bot-24517.southafricanorth..."
fases:       timeToFirstByte 93 ms  |  elementRenderDelay 1385 ms
```

A primeira tela deste painel **não é markup**. O `#gate-foot` nasce vazio no HTML e fica em
`display:none` até `gateAbre()`. Quem chama `gateAbre()` é o tratamento de **401**. Então a
sequência que o Lighthouse mede é:

```
documento (93 ms)  →  <head> bloqueante  →  script inline do fim do <body>
                   →  cargaInicial() dispara ~5 fetch
                   →  401 volta da VM na África do Sul
                   →  gate aparece  →  LCP
```

O documento chega em 93 ms e a tela espera 1385 ms **pelo backend**. Todo o trabalho deste card é
encurtar esse trecho: tirar peso do `<head>` para o script inline rodar antes, e adiantar o
começo da conversa com a VM.

---

## 3. Antes e depois

### 3a. Por que o "depois" é local, e por que ele vale

**Não dá para medir o depois em produção antes do merge**, e o merge é do dono: `web/` publica
sozinho no Vercel ao entrar na `main` (plano §9.9 — aqui o merge **é** a publicação). Worker não
faz push, não mergeia, não deploya.

Então o depois é um **A/B local controlado**: dois servidores estáticos com gzip, na mesma
máquina, no mesmo intervalo, servindo `1bb6908` e o `HEAD` desta branch, com as duas cópias
apontando para o mesmo backend — para o LCP ser o **mesmo elemento** (o gate) que em produção.

O elo que faz esse A/B valer é o hash, no padrão do `CLAUDE.md` §7:

```
producao : ca3342f79ca12c60  119448 bytes
1bb6908  : ca3342f79ca12c60  119448 bytes    => byte a byte igual (normalizando CRLF)
HEAD     : 614e64ba7725283d  126120 bytes
```

**O que está em produção hoje é exatamente `1bb6908:web/index.html`.** Logo o "base" do A/B é o
código de produção, e o delta medido é o delta que o deploy vai entregar.

Limites, ditos na cara: o servidor local não é a CDN do Vercel, e o backend do A/B é local, com
RTT ~0 em vez dos ~333 ms da África do Sul. Por isso os **valores absolutos locais são melhores
que os de produção nos dois lados** — e por isso a comparação que vale é base vs head, nunca
local vs produção. O ganho do `preconnect`, em particular, é **subestimado** aqui: contra um
backend local não há DNS, TCP nem TLS para adiantar (ver §5).

### 3b. As cinco métricas, por nome e valor

3 rodadas por lado, medianas. Score entre parênteses.

| Métrica | LOCAL base `1bb6908` | LOCAL head (5 commits) | Δ |
|---|---|---|---|
| **First Contentful Paint** | 790 ms (0,95) | **270 ms (1,00)** | **−520 ms** |
| **Largest Contentful Paint** | 798 ms (0,97) | **497 ms (1,00)** | **−301 ms** |
| **Total Blocking Time** | 0 ms (1,00) | 0 ms (1,00) | = |
| **Cumulative Layout Shift** | 0,001 (1,00) | 0,001 (1,00) | = |
| **Speed Index** | 790 ms (0,99) | **280 ms (1,00)** | **−510 ms** |
| **performance** | **0,99** | **1,00** | +0,01 |

Rodadas individuais, com `benchmarkIndex`, porque mediana sem dispersão esconde exatamente o
erro que este card investigou:

| | `bi` | perf | FCP | LCP | TBT | CLS | SI |
|---|---|---|---|---|---|---|---|
| base 1 | 2773 | 1,00 | 0,5 s | 0,6 s | 0 ms | 0,001 | 0,5 s |
| base 2 | 2951 | 0,99 | 0,8 s | 0,8 s | 0 ms | 0,001 | 0,8 s |
| base 3 | 2013 | 0,99 | 0,8 s | 0,8 s | 0 ms | 0,001 | 0,8 s |
| head 1 | 2554 | **1,00** | 0,3 s | 0,5 s | 0 ms | 0,001 | 0,3 s |
| head 2 | 2789 | **1,00** | 0,3 s | 0,5 s | 0 ms | 0,001 | 0,3 s |
| head 3 | 2316 | **1,00** | 0,3 s | 0,5 s | 0 ms | 0,001 | 0,3 s |

O head dá **1,00 nas três**, com `benchmarkIndex` variando de 2316 a 2789; o base oscila entre
0,99 e 1,00 no mesmo intervalo. O head é mais estável que o base, não só melhor.

### 3c. Os diagnósticos, que discriminam melhor que o score

O A/B local **satura**: o base já dá 0,99 porque localhost não tem a latência da África do Sul.
Quem separa os dois lados sem ambiguidade são as auditorias:

| Auditoria | base `1bb6908` | head |
|---|---|---|
| `render-blocking-insight` | **0** — 580 ms em 4 recursos | **0,5** — só o `config.js` |
| `unused-javascript` | **0** — 106 KiB | **1** — passa |
| `non-composited-animations` | 1 — *2 animated elements found* | **`null`** — nada a reportar |
| `forced-reflow-insight` | 0 — `939:3ms`, `1691:368ms`, `874:52ms` | 0 — `1776:68ms` (um só) |
| `lcp-breakdown` → `elementRenderDelay` | **665 ms** | **180 ms** |

### 3d. A prova causal: quando a primeira chamada ao backend sai

Esta é a medida que melhor explica o card, porque é exatamente a grandeza que os consertos movem.
Instante em que o `GET /estado` **parte**, contado do começo do documento:

| | base | head |
|---|---|---|
| rodada 1 | 375 ms | **63 ms** |
| rodada 2 | 565 ms | **53 ms** |
| rodada 3 | 346 ms | **53 ms** |

**A conversa com o backend começa ~300–500 ms antes.** Como o LCP é o gate, e o gate depende da
resposta do backend, isso é o LCP inteiro.

---

## 4. O que mudou, e por quê — uma linha cada

Cinco commits, um por assunto. O raciocínio completo (causa, por que ataca a causa, e qual seria
a versão-sintoma) está na mensagem de cada commit, como manda o `CLAUDE.md` §3 / plano §9.5.

| Commit | O que | Por quê |
|---|---|---|
| `7ee6193` | As duas libs de gráfico saem do `<head>` e entram por `carregarLib()` sob demanda | 124 KB bloqueavam a renderização antes de existir markup, com 92,3% e 88,9% do código nunca executados no carregamento; nenhuma das duas desenha a primeira tela |
| `3e07f24` | `preconnect` ao backend, com a origem lida de `window.API_BASE` | a primeira tela espera um 401 de um host com o qual o browser ainda não tem conexão — e essa conexão custa 672 ms (§5) |
| `f08c724` | O anel do pulso vira `::after` animando `opacity`+`transform` | `box-shadow` não é composto: cada quadro do ponto "ao vivo" repintava, `infinite`, para sempre |
| `8b6fae1` | A primeira `folgaStatusBar()` vai para `requestAnimationFrame` | ler `offsetHeight` no boot forçava o layout do documento inteiro ali, e as requisições saíam só depois — o trabalho é o mesmo, a ordem é que estava errada |
| `bf3dd93` | A folha do Google Fonts entra como `preload` e vira `stylesheet` no `onload` | ela custava 294 ms de render-blocking para mostrar o fallback que o `&display=swap` ia mostrar de qualquer jeito |

Três detalhes que valem para quem for mexer nisto de novo:

- **O `@keyframes pulse` tinha TRÊS clientes, não dois.** O Lighthouse achou os dois `span.dot`;
  o terceiro é o `.auto-badge.on` da aba Auto-trade, invisível na medição só porque o auto-trade
  estava desligado. Trocar o keyframe sem tratar o terceiro faria o badge **escalar** em vez de
  pulsar. Entrou junto.
- **O `forced-reflow-insight` continua em score 0**, e isso é esperado. O layout tem que
  acontecer; o que o commit muda é a ordem (rede primeiro). Perseguir o score aqui levaria a
  trocar a medida por altura fixa — que é bug de layout em tela estreita, não conserto.
- **Sobrou robustez de graça.** Com as duas libs bloqueadas na rede, o `HEAD` mantém tiles,
  tabelas, status bar e guarda de risco de pé com **zero `PAGEERROR`**. O base, no mesmo teste,
  cospe 7× `Chart is not defined`. O `s.onerror` do `carregarLib` resolve `false` em vez de
  rejeitar, e quem chama testa o retorno.

---

## 5. Os dois itens de backend — confirmados, e um deles estava mal diagnosticado

O §4e mandou **reportar, não consertar**. Reportado, e com uma correção de leitura em cada um.

Medido direto contra `https://cripto-bot-24517.southafricanorth.cloudapp.azure.com`:

```
=== preflight OPTIONS /estado ===
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://cripto-quant-dashboard.vercel.app
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 600            <-- JÁ EXISTE

=== 3 requisições na MESMA conexão ===
req1  connect=0,358s  tls=0,707s  ttfb=1,046s
req2  connect=0        tls=0        ttfb=0,340s
req3  connect=0        tls=0        ttfb=0,338s

=== RTT puro (TCP connect), 3 amostras ===
0,334s   0,333s   0,336s
```

**1. Preflight CORS — o `Access-Control-Max-Age` já está lá, valendo 600 s.** A premissa do §4e
("o backend não manda `Access-Control-Max-Age`") está errada. O que o relatório viu foram cinco
preflights porque o cache de preflight é por URL e o Lighthouse sempre parte de cache frio; eles
saem **em paralelo**, custando ~1 RTT de parede, não cinco. **Não vira card.**

**2. "Latência do uvicorn — `serverResponseTime` 334,8 ms" é uma atribuição errada.** Na conexão
quente o TTFB é 338 ms e o RTT puro de TCP é 333 ms: o servidor pensa **~5 ms**. Os 334 ms são
**um round-trip até a África do Sul**, não uvicorn. Otimizar o backend não move esse número —
ele é geografia. As saídas reais são mudar a região da VM ou aceitar o RTT, e **as duas são
decisão de custo do dono**, não conserto de código. Se virar card, é card de região, não de
uvicorn.

**3. O que a medição revelou e o §4e não tinha:** o *setup* de conexão custa **672 ms**
(DNS 8 ms + handshake TCP 325 ms + handshake TLS 339 ms) antes de qualquer byte útil. É o maior item isolado do
caminho crítico de produção, e é exatamente o que o commit `3e07f24` tira de dentro dele. Como o
A/B local usa backend local, **esse ganho não aparece nos números do §3** — ele só será visível
na primeira medição pós-deploy.

---

## 6. O que **não** mudou, e por quê

- **O `<style>` inline não foi minificado.** Decisão já registrada no plano §4e, e ela continua
  certa: `unminified-css` promete 5,7 KB, e aquele bloco é comentado linha a linha com o porquê
  de cada token medido do CoinMarketCap. Se o dono quiser os 5,7 KB, o caminho é minificar **no
  build**, não na fonte — e isso é outro card.
- **O `config.js` continua `<script src>` síncrono no `<head>`.** É a última linha do
  `render-blocking-insight` e ela **não sai**: o código da aplicação é um `<script>` inline no
  fim do `<body>`, e script inline roda **antes** de qualquer `defer`. Pôr `defer` aqui faz o
  `API` sumir na hora do boot — a página abre e nenhuma chamada funciona, e o Lighthouse **não
  pega**, porque ele mede a pintura, não se o painel tem dado dentro. Essa auditoria fica em 0,5
  de propósito.
- **Nada de CDN de terceiro, e a exceção não foi estendida.** As libs continuam em
  `web/vendor/`, servidas por nós — a regra do `CLAUDE.md` é sobre a **origem** do script (script
  de terceiro no mesmo documento lê a credencial do `localStorage`), não sobre o instante em que
  ele entra. A folha do Google Fonts continua sendo a única exceção, na mesma URL.
- **A Inter não foi baixada para `web/vendor/`.** Zeraria o round-trip a `fonts.googleapis.com` e
  daria número melhor, mas trocaria uma exceção já registrada e revisada por uma decisão nova de
  fonte — território do `DESIGN.md`, não meu.
- **O `TEMA` (leitura de `getComputedStyle` no boot, `web/index.html:939` na numeração antiga)
  ficou como está.** O §4e o lista como "a mesma classe" do reflow, e é — mas são **2,8 ms**, e
  torná-lo preguiçoso exige mexer em ~15 lugares que leem `TEMA.x`, sendo que `ACCENT_RGB` é
  usado pelo `sparkline()`, que roda no painel sem lib nenhuma. Quinze pontos de risco de
  regressão por 2,8 ms num LCP de 2100 ms é o negócio errado. Além disso é *style recalc*, não
  layout: esse trabalho tem que acontecer antes da pintura de qualquer jeito.
- **O gate continua aparecendo só depois do 401.** Este é o maior lever de LCP que sobrou, e é
  **decisão do dono, não minha** — ver §7.
- **Os quatro 401 no console (`/estado`, `/sentimento`, `/funding`, `/saidas`) continuam lá.**
  Derrubam `errors-in-console` (best-practices 0,96) e competem por banda durante o LCP. Consertar
  é mudar o comportamento do boot, fora do escopo de um card de performance.
- **O `favicon.ico` 404 continua.** Um request desperdiçado por carregamento. É arquivo novo em
  `web/`, fora da lista do território (`web/index.html` e `web/vendor/`).

---

## 7. O que eu quis mudar e parei, porque muda o que se vê

**Mostrar o gate imediatamente, sem esperar o 401.** É de longe o maior ganho de LCP disponível.
O gate é markup que **já existe na página** — ele só está em `display:none`. Os 1385 ms de
`elementRenderDelay` em produção são o tempo até alguém mandar mostrá-lo, e esse alguém é o
tratamento do 401: `<head>` bloqueante + script inline + ida e volta até a VM, nessa ordem. Os
consertos deste card atacam as duas primeiras parcelas; só esta mudança elimina a terceira, que
é a maior. Com o gate visível de saída o LCP cairia para junto do FCP.

**Não fiz, e não é timidez.** Muda o resultado visível para todo mundo — inclusive para quem tem
credencial válida no `localStorage`, que hoje **nunca** vê a tela de login e passaria a ver um
flash dela. Isso é decisão de produto, o `DESIGN.md` é a fonte da verdade visual e o briefing é
explícito: se para ganhar performance for preciso mudar o que se vê, o worker para e reporta.

Fica reportado. Se o dono aprovar, é card novo, e o portão dele é visual, não de número.

---

## 8. Como conferi que o visível não mudou

Com browser de verdade, `web/` servido localmente contra o `api.py` local
(`DASH_PASS` de teste, banco temporário fora do repositório), Playwright 1.62.1, viewport
1440×960, e **comparação de pixel** contra o estado anterior.

**Cobertura:** gate de login · painel · os cinco tiles · as sete sub-abas (Sinais, Posições,
Journal, Métricas, DCA, Mercado, Auto-trade) · aba Gráfico com velas reais da Binance · status
bar · o ponto pulsante.

**Resultado:** o cromo todo bate. Os diffs residuais são **o relógio da status bar e dado vivo**
— preço novo, sinais que o bot gerou entre as duas capturas. Verificado olhando os PNGs de diff,
não só o número: o diff da aba Gráfico (4,3%) é vela e escala de preço; o do painel (1,55%) são
dois sinais novos (`OP` e `ATOM`) que não existiam na captura anterior. Layout, tipografia,
espaçamento e cor: zero.

**O pulso, que é o item de risco visual do card**, foi comparado **quadro a quadro**: os três
elementos que usam o `@keyframes pulse` (os dois `.dot` e o `.auto-badge.on`), com a animação
congelada em 0, 200, 400, 700, 1000, 1400 e 1800 ms, servindo a versão antiga e a nova em
paralelo em duas portas.

```
velho animacoes: ["dot:pulse@1800","dot:pulse@1800","auto-badge on:pulse@2000","auto-badge:"]
novo  animacoes: ["dot:pulse@1800","dot:pulse@1800","auto-badge on:pulse@2000","auto-badge:"]

velho-pulso-0.png     -> 0 px diferentes (0.000%)
velho-pulso-200.png   -> 0 px diferentes (0.000%)
velho-pulso-400.png   -> 0 px diferentes (0.000%)
velho-pulso-700.png   -> 0 px diferentes (0.000%)
velho-pulso-1000.png  -> 0 px diferentes (0.000%)
velho-pulso-1400.png  -> 0 px diferentes (0.000%)
velho-pulso-1800.png  -> 0 px diferentes (0.000%)
```

**Zero pixel de diferença nos sete instantes do ciclo**, mesmo nome de animação e mesma duração,
e o `.auto-badge` sem `.on` segue sem animação alguma. O ponto pulsa igual — só que composto.

Provas não-visuais do mesmo teste, depois do login:

```
chartJs "function"   lwc "object"   tvCanvas 7   tiles 5
paddingBottom "41px" (idêntico)     --sb-h "33px" (idêntico)
fonte "Inter, -apple-system, BlinkMacSystemFont, ..."   interCarregada true
PAGEERRORS []
```

E o teste de rede hostil, com `**/vendor/**` abortado:

```
Chart "undefined"  LWC "undefined"  tiles 5  linhas 43  statusbar true
equityTile "R$ 1.000,00"  riscoGuard "banca R$ 1.000,00 risco dia R$ 0,00 ..."
PAGEERRORS []
```

---

## 9. Portão do `P2-37` — leitura honesta

O plano §4e define: *"Passa com performance ≥ 0,95 e as cinco métricas nomeadas, **ou** com a
demonstração de que o valor de origem não reproduz — e aí o veredito é esse, escrito."*

**Passa pelos dois caminhos, e é importante que passe pelos dois, porque nenhum sozinho fecharia
o card honestamente:**

1. **O valor de origem não reproduz.** Speed Index 7,2 s / score 0,00 volta como 0,9–1,3 s /
   score 0,89–0,99 em três rodadas. Demonstrado no §2, com `benchmarkIndex` de cada rodada.
2. **Performance ≥ 0,95 com as cinco métricas nomeadas**, no A/B local: `1,00` nas três rodadas
   do head, contra `0,99` do base — FCP 270 ms, LCP 497 ms, TBT 0 ms, CLS 0,001, SI 280 ms.

**O que ainda falta, e só o dono pode destravar:** a medição em produção **depois** do merge.
Ela não existe neste documento porque o merge é publicação (plano §9.9) e é decisão do dono.

**Rode o comando do §1 logo depois do deploy e cole aqui.** O que esperar, e o que significaria
cada resultado:

- **LCP deve cair bem mais que os 301 ms do A/B local**, porque em produção entra o ganho que o
  A/B não consegue medir: os 672 ms de setup de conexão que o `preconnect` tira do caminho
  crítico (§5).
- **Se o LCP não melhorar em produção**, o suspeito nº 1 é o `preconnect` não estar valendo — e
  a checagem é uma linha no DevTools: `document.querySelectorAll('link[rel=preconnect]')` tem que
  devolver **três** entradas (googleapis, gstatic e o backend, esta última com
  `crossorigin="anonymous"`).
- **Se o Speed Index voltar a dar 7,2 s**, não conserte nada antes de olhar o `benchmarkIndex` e
  o `lh:storage:clearBrowserCaches` do próprio relatório. Foi essa a lição inteira deste card.
