# PLANO-PRODUTO-UI — de painel do robô a home broker próprio (2026-11-12)

> **Para quê:** o `NORTE.md` diz que o produto é operar sozinho **e** ser ferramenta de análise. O
> painel de hoje (`web/index.html`, 1.855 linhas, "planilha viva" CMC night) atende só o primeiro
> papel. Este plano transforma o front em um home broker próprio — robô, análise, carteira, LLM,
> multi-mercado (cripto → ações BR → índices) e app no celular — por fases, com o motor intacto.
>
> **Status:** passo 1 e 1b entregues em 12/11; nome DECIDIDO (Apollux / Apollo); direção, acento, stack e pasta pendentes (§3).
> O material de escolha fica fora do repo, de propósito:
> - Brand book e direções: `DS/BRAND-BOOK-2026-11-12.md` (copia local; o doc no claude.ai foi apagado em 12/11 por ter sido publicado no workspace errado)
> - Mockups navegáveis (5 direções × 3 acentos × 8 nomes): `DS/mockups/index.html` (local; republicar como artifact so de sessao logada na conta pessoal)
>
> Este arquivo **não está commitado** até o dono decidir nome e direção; depois disso ele entra na
> `main` ao lado dos outros `PLANO-*.md` e os cards do §8 nascem no Trello (a matriz cria, o worker
> não cria — `CLAUDE.md` §4).

---

## 0. O que muda e o que não muda

| Muda | Não muda |
|---|---|
| O front inteiro: casca, navegação, identidade, movimento, 3D | O motor (`signal_engine`, `scoring`, `simulador`, `autotrader`): nenhuma regra de trade entra por aqui |
| A direção visual: sai o CMC night (`DESIGN.md` de 22/08), entra a escolhida no passo 1 | As invariantes do `CLAUDE.md` §2: trava diária, claim atômico, pânico mata a fonte, post-only, `DASH_PASS`, sem script de terceiro, `/estado` enxuto |
| O nome do produto (hoje "Cripto Bot") | A régua (`pesquisa/`): continua portão de qualquer sinal novo |
| O `web/` vira a casca nova (ou `app/`, conforme §5) | O backend FastAPI no dl380 e o banco SQLite; rotas novas entram, as 31 ficam |

A regra de ouro das fases 1-3: **nenhuma funcionalidade de trading nova**. É mudança de casa.
Funcionalidade nova (análise própria, push, LLM, B3) tem fase própria, com critério de aceite próprio.

## 1. O destino, em uma tela

Uma **casca** (nav lateral + conta + robô sempre à vista) com seis módulos ao vivo e quatro em
construção, visíveis na nav com cadeado para a casa já nascer do tamanho que vai ter:

| Módulo | Estado | O que tem | Vem de |
|---|---|---|---|
| **Painel** | ao vivo | equity, P&L dia/mês, trava, posições, ordens, sinais, curva, mercado | `sub-sinais`, `sub-posicoes`, `sub-metricas`, `sub-mercado` |
| **Operar** | ao vivo | mesa manual: gráfico + book, ordem a mercado/post-only, risco e lev por trade | aba `grafico` + modal de confirmar |
| **Robô** | ao vivo | ligar/pausar/pânico, config (risco, modo, guardas), ciclo e journal ao vivo | `sub-auto`, `sub-journal`, `POST /config` |
| **Análise** | ao vivo (raso) → F4 | gráfico com os indicadores do `indicadores.py`, watchlist, screener, notas | aba `grafico` hoje; o resto é F4 |
| **Carteira** | ao vivo (raso) → F4 | alocação, exposição, DCA, correlação entre posições | `sub-dca`, `guarda_risco` |
| **Pesquisa** | ao vivo | vereditos da régua, testes T-n, lacrados | `README.md`, `testes/O-QUE-FUNCIONA.md`, `VEREDITO-*.md` |
| Ações BR | em construção → F8 | Clear/B3, mesmo motor, calendário de pregão | — |
| Fundamentos (LLM) | em construção → F7 | LLM lê balanço e notícia do ativo, com o porquê | card `N-1` |
| Notícias | em construção → F7 | coleta, consolidação, efeito medido | card `N-1` |
| Mobile & Push | em construção → F5 | PWA já instalável (PR #17); push do dia | `web/sw.js`, `manifest.webmanifest` |

Transversal: **seletor de conta** (Paper A / Conta B / Real) na casca, com borda de cor distinta em
Real. Hoje a Conta B existe (`PLANO-CONTA-B`), a Real é a esteira do `PLANO-LIVE-BINANCE`.

## 2. Passo 1 — entregue (identidade visual)

O que foi produzido em 12/11, para o dono escolher:

- **5 direções de design**, cada uma com mockup HTML navegável do Painel, mesmo conteúdo fictício
  nas cinco (comparação justa), elemento 3D próprio e movimento GSAP:
  D1 Command Deck (HUD/Jarvis, globo wireframe) · D2 Volt (lima sobre preto, orbe glossy) ·
  D3 Orbit (cobalto, planeta com satélites) · D4 Pulse (neon, terreno de partículas) ·
  D5 Ledger (monocromático, terreno contido).
- **3 acentos por direção** (15 paletas) e **8 nomes** no wordmark, trocáveis ao vivo em cada
  mockup: Kairós · Farol · Zênite · Orbe · Vigia · Candeia · Vetor · Maré.
- **Tipografia** por direção (display + UI + mono tabular), **linguagem de movimento** (6 momentos
  com temperamento por direção) e **regras de apresentação da informação** (hierarquia de leitura:
  risco → P&L → robô → posições → sinais → curva → mercado → em construção).
- **Passo 1c (12/11):** o mockup Pulse ganhou todas as abas navegáveis (roteador por hash + `DS/mockups/pulse-views/<id>.js` por módulo, contrato em `pulse-views/CONTRATO.md`) e 12 paletas completas (`DS/ds/paletas-pulse.js`, catálogo `DS/ds/paletas-pulse.html`).
- **Passo 1b (12/11, mesmo dia):** o dono aprovou **Volt, Orbit, Pulse e Ledger** e descartou Command Deck.  Cada aprovada ganhou um design system completo em `DS/ds/<direção>-ds.html` (fundamentos com  contraste calculado, componentes com estados, padrões de trading, telas de celular em frames e as  notificações push com regras de disparo), com foco em UX usual. Hub: `DS/index.html`.

## 3. Decisões do dono (todas tomadas em 12/11; a fase 1 está liberada)

| # | Decisão | Opções | Recomendação da sessão | Registrar em |
|---|---|---|---|---|
| D-1 | **Nome** | **DECIDIDO em 12/11: marca Apollux, agente Apollo** (Pítia proposta para o oráculo LLM, não decidido). Varredura: apollux.com.br, .app e .io livres; nenhuma marca igual achada; checar APOLLO/APOLLUX no INPI (classes 36, 42, 9) antes de registrar | registrar domínios e abrir pedido no INPI | `NORTE.md` + `DESIGN.md` |
| D-2 | **Direção visual** | **DECIDIDO em 12/11: Pulse (D4)** — sidebar, faixa de KPIs, terreno de partículas, curva neon. Volt, Orbit e Ledger ficam como referência de componentes | paleta em exploração (D-3): 12 paletas completas em `DS/ds/paletas-pulse.js`, catálogo em `DS/ds/paletas-pulse.html`, seletor no mockup `?paleta=<id>` | `DESIGN.md` v2 |
| D-3 | **Paleta** | **DECIDIDO em 12/11: "a identidade do jeito que está no mock está perfeita"** — padrão Elétrico (o do print dele); **no mesmo dia o dono trocou o padrão para Osso**; seletor das 12 paletas mantido e lembrado por navegador | — | `DESIGN.md` v2 |
| D-4 | **Stack do front** | §5 | **DECIDIDO em 12/11: a stack que já está no Vercel** — `web/` estático, JS sem build, libs em `web/vendor/`. A recomendação Vite + React + TS (§5) fica de lado | `ARQUITETURA.md` §8 |
| D-5 | **Onde mora** | `web/` substituído vs. `app/` novo ao lado | **DECIDIDO em 12/11: no `web/` do projeto atual.** Produção real (assinatura, terceiros) fica para depois: por ora só o dono opera, front no Vercel, backend no dl380 | `CLAUDE.md` §0 |

## 4. Fases

Dependência em linha: F1 → F2 → F3 → (F4 ∥ F5) → F6 → F7 → F8 → F9. Paralelismo só dentro da
fase (`CLAUDE.md` §6). Cada fase fecha com **saída literal colada** no card (§7 do `CLAUDE.md`).

### F1 — Brand book final e `DESIGN.md` v2
- **Entrega:** tokens (cor, tipo, espaço, raio, movimento) como CSS vars; logo/wordmark em SVG;
  componentes-base desenhados: botão, chip, LED, card, KPI, tabela, sparkline, barra de risco,
  gauge; estados (hover, foco, desligado, erro); página de tokens renderizada (storybook-lite).
- **Aceite:** `DESIGN.md` reescrito com os valores **medidos** do mockup escolhido (não de memória);
  contraste AA conferido por script para cada par texto/superfície; página de tokens no Vercel preview.
- **Território:** `DESIGN.md`, os tokens no `<head>` de `web/index.html` e em `web/app/paletas.js` (D-4/D-5), `web/icons/`.

### F2 — Casca nova
- **Entrega:** stack da D-4; autenticação pelo `DASH_PASS` atual (token no `localStorage`, como
  hoje); nav lateral com os 10 módulos (4 com cadeado e página "o que vai ter" + estado vazio
  desenhado); seletor de conta; casca responsiva (390 px → 1440 px); PWA mantida (manifest, sw);
  o elemento 3D da direção no hero do Painel; movimento: entrada, contagem, desenho de curva.
- **Aceite:** deploy em preview do Vercel consumindo o `/estado` do dl380; nenhum `src=http` para
  script no build (libs via bundle, não CDN); CSP do `vercel.json` intacta; Lighthouse ≥ 90 em
  performance no Painel; 60 fps com o 3D ligado em notebook comum.
- **Território (D-4/D-5):** `web/index.html` (casca), `web/app/` (código da casca e views), `web/vendor/` (GSAP vendorado), `web/sw.js` e `web/manifest.webmanifest`, um mount estático de `/app` no `api.py`. O `index.html` antigo fica em `web/classico.html`. `vercel.json` só se a CSP precisar mudar.
- **Aceite revisto pela D-4:** sem build, então "nenhum `src=http`" é `grep -rn "src=['\"]http" web/` vazio, com as libs commitadas em `web/vendor/`.

### F3 — Migração do painel (paridade)
- **Entrega:** cada subview de hoje migra para seu módulo: sinais (confirmar/pular), posições e
  ordens pendentes, journal, métricas + win rate por convicção, DCA, mercado (sentimento, funding),
  auto-trade (config + pânico em 2 passos). Nada novo.
- **Aceite:** checklist item a item contra `web/index.html` (31 rotas consumidas iguais); o dono
  opera um dia inteiro na casca nova; só então o `web/` antigo vira redirect.
- **Território:** `web/app/views/*`; `api.py` só se precisar de rota de leitura nova (e aí é card à parte).
- **Revisto pela D-5:** não há redirect a fazer; a casca nova é o `web/index.html`, e o painel de antes segue em `web/classico.html` até o dono dizer que pode sair.

### F4 — Análise própria e Carteira
- **Entrega:** gráfico (lightweight-charts, já vendorado) com os indicadores do `indicadores.py`
  servidos por rota nova (`GET /indicadores/{par}?tf=`), para a paridade painel = backtest;
  watchlist e screener (ranking por convicção e por ATR%, que o T28 mostrou empatar);
  notas por ativo (tabela nova `notas`); Carteira: alocação alvo, exposição por direção, correlação.
- **Aceite:** o indicador desenhado no gráfico bate com o do `scoring.py` para o mesmo candle
  (teste de paridade); screener devolve em < 1 s para os 24 pares.
- **Território:** `app/modules/analise`, `app/modules/carteira`, `api.py` (rotas novas), `db.py`
  (tabela `notas`) — esquema de banco é serializado (§9.2b do plano de execução).

### F5 — Mobile & Push
- **Entrega:** push Web (VAPID) com tabela `push_subscriptions`; o worker dispara: fechamento do
  dia (lucro/prejuízo + equity), trava disparada, sinal com convicção ≥ limiar configurável,
  ordem preenchida/expirada; notícia entra na F7. Tela de preferências de push no módulo Mobile.
- **Aceite:** push recebido no celular do dono com o mesmo número do `/estado` no mesmo minuto;
  desligar na preferência cessa o envio; sem token nenhum push sai (como o Telegram hoje).
- **Território:** `app/modules/mobile`, `web/sw.js` (ou `app/sw.ts`), `api.py` (rotas de
  subscription), `db.py` (tabela), `alertas.py` (canal push ao lado do Telegram).

### F6 — Conta real (Binance)
- **Entrega:** o `PLANO-LIVE-BINANCE-2026-10-17.md` já descreve a esteira testnet → dry-run →
  live; esta fase é o lado do front: seletor de conta Real com borda distinta, painel de execução
  (fills, slippage, taxa real vs. paper), botão de pânico que fecha na exchange.
- **Aceite:** o do plano LIVE (mede execução, não cria edge) + o front nunca mostra Real como Paper.
- **Território:** o do plano LIVE + `app/modules/operar`.

### F7 — Notícias e Fundamentos (LLM)
- **Entrega:** coleta e consolidação de notícias por ativo (card `N-1`), resumo por LLM (Claude
  API, modelo atual) com o porquê e a fonte; fundamentos (tokenomics, TVL, emissão) na mesma tela;
  efeito **medido** na régua antes de entrar na decisão do motor (`NORTE.md`: display primeiro,
  decisão só com evidência).
- **Aceite:** página do ativo com notícia + resumo + fonte; custo de LLM por dia dentro do teto
  configurado; nenhuma chamada de LLM na thread do worker (fila separada).
- **Território:** `noticias.py` (novo), `llm.py` (novo), `app/modules/fundamentos`, `app/modules/noticias`.

### F8 — Ações BR e índices
- **Entrega:** conector de dados B3 (fonte a decidir: corretora ou provedor), calendário de pregão,
  o mesmo motor em outro mercado com a régua rodada do zero (não se importa veredito de cripto);
  Carteira multi-mercado.
- **Aceite:** walk-forward + DSR em B3 com o mesmo rigor; o módulo sai do cadeado só com dado ao vivo.
- **Território:** `mercado_b3.py` (novo), `pesquisa/` (dados), `app/modules/acoes`.

### F9 — Assinatura
- **Entrega:** multi-tenant (auth real, isolamento por usuário, billing), termos, LGPD, limites de
  uso por plano. **Só depois do portão do lucro** (decisão de 01/11: lucro próprio primeiro).
- **Aceite:** definido quando a fase abrir.

## 5. Stack do front — decisão D-4

**Decidido em 12/11: opção A** (a stack que já está no Vercel). A tabela abaixo é o registro da
recomendação que o dono não seguiu; vale como histórico, não como plano.

| Opção | Prós | Contras | Veredito |
|---|---|---|---|
| A. Vanilla + vendor (como hoje) | zero build; `web/` conhecido; CSP trivial | 1.855 linhas já doem; 10 módulos + 3D + GSAP num arquivo é inviável; sem tipos | não para a casca nova |
| **B. Vite + React + TypeScript** (SPA estática) | build simples; componentes; tipos contra o `/estado`; GSAP, Three (R3F) e lightweight-charts via npm = **bundle próprio, sem CDN** (a regra "sem script de terceiro" continua valendo); `vite-plugin-pwa` mantém a PWA; deploy estático no Vercel | precisa de build no CI; aprender uma estrutura nova | **recomendado** |
| C. Next.js (App Router) | padrão Vercel; SSR/ISR | SSR não serve a um painel autenticado por token que faz poll a cada 3 s; segunda camada de servidor que o projeto não quer (o backend é FastAPI no dl380) | não agora; vira opção na F9 (landing + billing) |

Decisões técnicas que acompanham B: Tailwind com os tokens como CSS vars (o `DESIGN.md` continua
fonte da verdade); roteamento por hash ou `react-router` com fallback no `vercel.json`;
polling do `/estado` como hoje (SSE é card à parte, e a franquia de saída continua mandando no
tamanho da resposta); Three.js só no hero (lazy), GSAP global.

## 6. O que a casca nova herda do `DESIGN.md` atual (e fica)

- A tabela é protagonista e **a linha termina em sparkline**.
- Contraste como portão (os 4 tokens corrigidos do CMC mostram o método: corrigir dentro da rampa).
- Dark only no passo 2; tema claro declarado para a F9.
- Zero script de terceiro em runtime; libs no bundle ou em `vendor/`.
- O `/estado` não engorda: módulo novo que precisa de dado novo ganha rota própria.

## 7. Riscos

| Risco | Mitigação |
|---|---|
| Direção bonita que não aguenta densidade (Operar, tabelas) | o 3D mora só no hero; a F1 desenha a tabela antes de qualquer card |
| Movimento que pisca a cada poll de 3 s | só o delta anima; linha que não mudou fica quieta (regra no brand book) |
| Reescrever o front e quebrar a operação | `web/` continua no ar até a paridade da F3; o dono opera um dia inteiro na casca nova antes do redirect |
| Nome com colisão | checar domínio, INPI e App Store **antes** da F1; o wordmark é texto, trocar custa pouco |
| Push vazando número de conta | push sem token não sai; preferências por tipo; o payload do push não carrega credencial |
| 3D pesado no celular | reduced-motion e `document.hidden` pausam; no celular o 3D vira imagem estática |

## 8. Cards propostos (a matriz cria; prefixo `UI-`)

Pela D-5, todo `app/...` desta tabela lê-se `web/app/...`. UI-0 a UI-7 foram entregues juntas na
branch `feat/front-apollux` (F1+F2+F3), um commit por etapa.

| Card | Fase | Território | Label |
|---|---|---|---|
| UI-0 Decisão de nome, direção, acento e stack (D-1..D-5) | 0 | `NORTE.md`, `DESIGN.md` | decisão-do-dono |
| UI-1 `DESIGN.md` v2 + tokens + página de tokens | F1 | `DESIGN.md`, `app/tokens` | front |
| UI-2 Casca: stack, auth, nav, seletor de conta, PWA | F2 | `app/` | front |
| UI-3 Hero 3D + movimento (entrada, contagem, curva) | F2 | `app/hero` | front |
| UI-4 Páginas "em construção" com estado vazio | F2 | `app/modules/*` | front |
| UI-5 Migração: sinais + posições + ordens | F3 | `app/modules/painel` | front, toca-risco (pânico, confirmar) |
| UI-6 Migração: robô + journal + métricas | F3 | `app/modules/robo` | front, toca-risco (config) |
| UI-7 Migração: DCA + mercado + redirect do `web/` | F3 | `app/modules/carteira`, `web/` | front |
| UI-8 Rota `GET /indicadores` + gráfico com paridade | F4 | `api.py`, `app/modules/analise` | backend, front |
| UI-9 Watchlist, screener, notas (tabela `notas`) | F4 | `db.py`, `api.py`, `app/` | backend, front |
| UI-10 Push Web: VAPID, subscriptions, canal em `alertas.py` | F5 | `db.py`, `api.py`, `alertas.py`, `app/modules/mobile` | backend, front |
| UI-11 Gatilhos de push (fechamento, trava, sinal, ordem) | F5 | `api.py` (worker), `alertas.py` | backend, toca-risco |

F6-F9 ganham cards quando abrirem; os planos `PLANO-LIVE-BINANCE` e `PLANO-MOTOR` já têm os deles.

## 9. Como seguir

1. Dono abre o brand book e os mockups, escolhe (D-1..D-5) e registra no `NORTE.md`.
2. Esta sessão (ou a próxima) grava a decisão aqui, commita este plano e pede os cards à matriz.
3. F1 começa pelo `DESIGN.md` v2 com valores medidos do mockup escolhido, nunca de memória.
