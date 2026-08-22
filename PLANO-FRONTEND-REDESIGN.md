# Plano de Redesign do Frontend — "Mesa de trading à meia-noite"

> **Handoff para outra sessão.** Este documento é auto-contido: a sessão que for implementar
> **não tem** o histórico da conversa onde ele nasceu. Leia inteiro antes de tocar em código.
> Escopo: **reestilizar apenas `web/index.html`** (skin + layout). **Zero** mudança de backend,
> lógica, endpoints ou dados. As decisões de direção já foram travadas pelo dono do projeto
> (ver §4) — não as re-pergunte; implemente-as.

---

## 1. Contexto do projeto (o que é isso)

Plataforma de **paper trading** de cripto (dinheiro fictício, preço real da Binance). Um bot
opera sozinho (opcional) e o painel mostra tudo ao vivo.

- **Backend:** `api.py` (FastAPI). Serve o `web/` via `StaticFiles` **e** expõe JSON. Endpoint
  central: `GET /estado` (o front faz **polling a cada 3s** e reconstrói o `innerHTML` dos painéis).
  Outros: `/sentimento`, `/funding`, `/saidas`, `/precos`, `/candles`, `/analise`, `/book`,
  `/smartmoney`; ações `POST /confirmar /fechar /panico /scan /reset /auto /dca /dca/aportar /dca/remover /pular`.
- **Frontend:** **um único arquivo** `web/index.html` (~877 linhas) = CSS inline (bloco `<style>`)
  + JS vanilla. Sem framework. Libs **vendoradas** em `web/vendor/` (Chart.js 4.4.1 e
  Lightweight-Charts 4.1.3 — carregadas por `<script src="vendor/...">`, **nada de CDN de terceiro**).
- **Deploy split (Vercel + backend separado):** `web/config.js` pode definir `window.API_BASE`.
  Quando setado, o front vira cross-origin e manda credencial de Basic Auth no header
  (guardada em `localStorage['cbAuth']`). Quando vazio (monolito), o backend serve o próprio HTML.
  **Isso tudo precisa continuar funcionando** após o redesign.

## 2. Objetivo

Trazer a pegada visual de um dashboard **dark, navy, glassmorphism com acento azul vivo**
(referência descrita em §3) — **adaptada** para um terminal de trading de **alta densidade**.
É adotar a **vibe**, não copiar ao pé da letra.

## 3. A referência (descrição — a imagem não acompanha este arquivo)

Dashboard de gestão de tarefas "G.Take", dark:
- **Fundo:** navy profundo em gradiente, com **céu estrelado sutil** no topo e um leve brilho de
  paisagem/montanha embaixo. Atmosférico.
- **Cards:** **glassmorphism** — painel escuro translúcido, borda branca suave, cantos
  arredondados (~16–20px), `backdrop-blur`; alguns com um **glow radial azul** por dentro.
- **Acento:** **azul vivo** (~#3b82f6) — logo, item de nav ativo (ícone quadrado arredondado com
  gradiente azul), botões primários, barras de progresso, e o título hero com **gradiente**.
- **Sidebar** à esquerda (ícone + label; Settings/Log out fixos embaixo).
- **Tipografia:** sans limpa (tipo Inter/Poppins). Coluna direita de cards de resumo. Pills de
  filtro com chevron, pilhas de avatares, mini gráfico de área.

> ⚠️ **OBSOLETO desde 2026-08-22.** As decisões desta seção (navy, glassmorphism, vidro no
> resumo, Space Grotesk, sidebar) foram substituídas pelo dono do projeto por uma transposição do
> design system do **CoinMarketCap, tema escuro**. A direção vigente está em `DESIGN.md` na raiz,
> que é a fonte da verdade. Esta seção fica no arquivo só como registro do que foi tentado antes.
> O resto do plano (§1 contexto, §8 restrições críticas, §10 critério de aceite) **continua
> valendo** — em especial a lista de IDs/handlers que não podem quebrar e o portão de contraste.

## 4. Decisões TRAVADAS (não repergunte)

1. **Sidebar à esquerda** substitui as abas de cima (Painel/Gráfico).
2. **"Tunado pra dados"** (NÃO full-imersivo): vidro + aura azul **só nos cards de resumo**;
   **superfície sólida e nítida** sob tabelas/métricas (contraste é prioridade). Estrelas de
   fundo **bem discretas**, nunca atrás de dado.
3. **Tipografia:** **Space Grotesk** nos títulos/hero/seções + **Inter** (com `tabular-nums`) nos
   dados + **mono** nas células numéricas densas.
4. **Verde/vermelho reservados só para dinheiro/direção** (P&L, LONG/SHORT). A referência é
   azul-mono porque é gerenciador de tarefas; **trading precisa** de verde/vermelho. Azul = marca,
   ações, nav ativa, progress, aura. Gold = avisos.

## 5. Design system (tokens concretos — ponto de partida)

Fontes via Google Fonts (como já é hoje com Inter) **ou** vendoradas em `web/vendor/fonts/`
(recomendado, pra bater com a filosofia "sem terceiro"; se vendorar, use `@font-face` local).
Adicionar Space Grotesk + JetBrains Mono (ou similar mono).

```css
:root{
  /* canvas / atmosfera */
  --bg:#0a1020; --bg-grad-top:#0e1730; --aura:rgba(59,130,246,.18);
  /* superfícies */
  --glass:rgba(23,33,58,.55);            /* vidro: SÓ cards de resumo */
  --glass-border:rgba(255,255,255,.08);
  --surface:#131c30;                     /* sólido: tabelas/métricas/painéis de dados */
  --surface2:#182337;                    /* elevado / inputs */
  --border:#233150; --border2:#2e3d5e;
  /* texto (VERIFICAR ≥4.5:1 sobre --surface) */
  --txt:#e8ecf5; --muted:#94a1bd; --muted2:#aab4cc;
  /* acento azul */
  --accent:#3b82f6; --accent2:#60a5fa; --accent-bg:rgba(59,130,246,.14);
  /* semânticos = dinheiro (NÃO usar pra outra coisa) */
  --green:#16c784; --green-bg:rgba(22,199,132,.12);
  --red:#ea3943;   --red-bg:rgba(234,57,67,.12);
  --gold:#f0b90b;
  /* forma / motion */
  --r-card:16px; --r-inner:10px;
  --shadow:0 10px 30px rgba(0,0,0,.35);
  --blur:14px;
  --font-display:'Space Grotesk',system-ui,sans-serif;
  --font-ui:'Inter',system-ui,sans-serif;
  --font-mono:'JetBrains Mono',ui-monospace,'Cascadia Mono',monospace;
}
body{ background:
  radial-gradient(1100px 600px at 85% -10%, var(--aura), transparent),
  linear-gradient(180deg, var(--bg-grad-top), var(--bg)); }
```

**Regras:** distribuição ~60-30-10 (navy / azul / verde-vermelho). **Nunca** gradiente em número
ou métrica (permitido só no título hero, se quiser). Uma sombra por elemento (não empilhar borda
hairline + drop-shadow difusa). Raio ≤16px em card pequeno.

**Signature move:** card **hero de equity com aura azul + sparkline** ao vivo, sobre uma grade de
vidro calma.

## 6. Estrutura/layout alvo

- **Sidebar fixa à esquerda** (~230px desktop; colapsa/vira topo no mobile): marca no topo →
  nav **Dashboard** e **Gráfico** (item ativo com ícone azul-gradiente) → embaixo, ações
  **Escanear / Pânico / Reset**, o badge **AO VIVO** e o login/logout. Substitui `.tabs` e a
  `.toolbar` do header atual.
- **Topbar** enxuta no conteúdo (título/estado + resumo rápido).
- **Bento** na `view-painel`:
  - Linha 1: **hero equity** (largo) + 3 stat cards (Banca, Posições, Sinais).
  - Coluna principal: **Sinais**, **Posições**, **Journal**.
  - Trilho direito: **Auto-trade**, **Sentimento**, **Funding**, **DCA**, **Métricas**.
  - (A grade atual já é `.cards` + `.panel` + `.two`; reorganizar em bento com sidebar.)
- **`view-grafico`** (Lightweight Charts + book/smart money/análise): manter a estrutura,
  só re-tematizar.

## 7. Mapa de componentes a reestilizar

Cada painel vira card de dados (superfície **sólida**), com título em Space Grotesk. Cards de
**resumo** (hero equity, stat cards, status do auto-trade) podem usar **vidro + aura**.

| Bloco | Onde | Tratamento |
|---|---|---|
| Header/marca + toolbar | `<header>`, `.brand`, `.toolbar` | vira **sidebar** |
| Abas Painel/Gráfico | `.tabs`/`.tab` | vira nav da sidebar |
| Stat cards | `.cards .card`, `.card.hero` | hero=vidro+aura+sparkline; resto sólido |
| Auto-trade | `#auto-panel` + `.auto-*` | card de status (vidro leve), toggle azul, chips |
| Sentimento | `#sentimento` (gauge Fear&Greed) | manter gauge, re-tematizar cores |
| Funding | `#funding`, `.fund-*` | barras azul/verde/vermelho, sólido |
| DCA | `#dca`, `.dca-form` | tabela sólida + form com inputs novos |
| Curva de capital | `#chart` (Chart.js) | linha azul-gradiente sobre navy |
| Métricas | `#metricas`, `.mstats/.mstat` | grade de tiles sólidos |
| Sinais | `#pendentes`, `.sig/.conv/.tag/.why-chip/.entry-status` | cards nítidos, tag long/short verde/vermelho |
| Posições/Journal | `#posicoes`/`#trades` (tabelas) | tabela sólida: texto à esq, número tabular à dir |
| Banners de risco | `#risco-guard`, `.rg-*` | manter, re-tematizar |
| Gráfico + laterais | `#view-grafico`, `#tvchart`, `#g-*` | navy/azul; velas verde/vermelho |
| Modal confirmar | `.overlay/.modal` + `#m-*` | vidro, animar do gatilho |
| Toast | `#toast` | re-tematizar |

## 8. Restrições CRÍTICAS (não quebrar nada)

1. **Só `web/index.html`.** Nenhum arquivo de backend, nenhum endpoint, nenhuma lógica.
2. **Mantenha TODOS os `id` e os `onclick`.** O JS mira elementos por `id` e chama funções globais.
   IDs usados: `equity, pnl, banca, npos, npend, cfg, risco-guard, auto-panel, auto-toggle,
   auto-status, auto-log, a-conv, a-lev, a-lev-lbl, a-risco, a-maxpos, a-levmodo, sentimento,
   funding, dca, dca-ativo, dca-valor, dca-freq, chart, metricas, pendentes, posicoes, trades,
   view-painel, view-grafico, tv-ativo, tv-tfs, tvchart, g-analise, g-book, g-smart, g-posicoes,
   g-trades, overlay, m-titulo, m-sub, m-valor, m-lev, m-risco, m-prev, m-conf, toast`.
   Handlers: `escanear, panico, resetar, aba, toggleAuto, salvarAuto, criarDca, aportarDca,
   removerDca, abrirModal, fecharModal, confirmarTrade, pular, fechar, analisarSinal, mudarTf,
   toggleIndicadores, toggleExpand, usarSugestao, previa, sairLogin`. Também os `data-v` das abas
   e `data-tf` dos botões de timeframe (o JS liga/desliga `.on` por eles).
3. **PEGA-RATÃO — cor mora em DOIS lugares.** Muitos renders JS injetam `innerHTML` com
   `style="..."` e **cores cravadas**. Trocar só o `<style>` deixa metade do app com a cor velha.
   Atualize também os inline styles nestas funções: `carregar` (equity/pnl, `risco-guard`, cards de
   `pendentes`, tabela `posicoes`, tabela `trades`, `metricas`), `carregarSentimento` (gauge
   Fear&Greed usa `#ea3943/#f0b90b/#16c784`), `carregarFunding`, `renderAnalise`, `carregarBook`
   e `carregarSmartMoney` (`#16c784/#ea3943`), `sidebar`, `renderAuto`, `previa` (preview do modal).
   **Temas de gráfico** também: no `carregar` o Chart.js usa `borderColor:'#16c784'`,
   `grid:{color:'#1a2030'}`, `ticks:{color:'#7e89a3'}`; em `initTV` o Lightweight-Charts usa
   `textColor:'#7c869c'`, `grid #1a2030`, `borderColor #222a3a`, velas `#16c784/#ea3943`; em
   `garanteIndSeries` as EMAs/Bollinger usam `#2dd4bf/#f0b90b/rgba(150,140,225,..)`. Re-tematizar
   tudo pra navy/azul (velas e P&L continuam verde/vermelho).
4. **Preservar comportamento:** login/`API_BASE` (split Vercel), libs vendoradas, `polling` +
   **pausa por `visibilitychange`**, **skeletons** (`.skel`), **`:focus-visible`**,
   **`prefers-reduced-motion`**, atributos **aria** (roles, aria-live do toast, aria-pressed nas
   abas/toggles), e o **modal** (role=dialog, foco no 1º campo, Esc fecha, restaura foco).
5. **Contraste (gate, não enfeite):** vidro translúcido facilmente reprova 4.5:1. Todo **texto de
   dado** fica sobre superfície **opaca o suficiente**. Rodar uma verificação de contraste no fim.
6. **Responsivo:** sem scroll horizontal no mobile; tabelas largas já usam wrappers roláveis
   (`#posicoes/#trades/#dca/#metricas` têm `overflow-x:auto`) — manter. Sidebar colapsa no mobile.

## 9. Fases de execução (ordem sugerida)

1. **`DESIGN.md`** (fonte da verdade — ver skill `frontend-design-deslop`) + **tokens** + **shell**
   (sidebar, bento skeleton, fundo navy/aura, fontes).
2. **Resumo:** hero equity (aura + sparkline) + stat cards + banners de risco.
3. **Painéis:** auto-trade, sentimento, funding, DCA, métricas (CSS **e** inline styles do JS).
4. **Tabelas:** sinais, posições, journal.
5. **Gráficos:** Chart.js (equity) + Lightweight-Charts (velas) re-tematizados.
6. **Acabamento:** modal, toast, chips de filtro, motion (ease-out ≤300ms, só transform/opacity,
   respeitar reduced-motion) + **auditoria anti-slop** (`references/slop-checklist.md` da skill) e
   **contraste**.

## 10. Critério de aceite

- [ ] Bate a vibe: navy profundo + azul vivo + vidro nos resumos + sidebar; premium e calmo.
- [ ] **Todos** os painéis renderizam certo com dados reais (abrir com o backend rodando e o bot ligado).
- [ ] Nada funcional quebrou: abrir/fechar trade, auto-trade toggle/salvar, DCA, escanear, pânico,
      reset, troca de aba, gráfico + timeframes + indicadores, modal, login/split.
- [ ] Contraste ≥4.5:1 no texto de dados; `focus-visible`, `reduced-motion`, aria e skeletons intactos.
- [ ] Sem scroll horizontal no mobile; sidebar colapsa.
- [ ] Verde/vermelho só em dinheiro/direção; **zero gradiente em número**.
- [ ] Funciona nos dois modos: monolito (`API_BASE` vazio) e split (`API_BASE` setado).

## 11. Notas honestas de design (por que assim)

- A referência é **baixa densidade** (gerenciador de tarefas); nosso app é **alta densidade**
  (tabelas, grades de número). Copiar vidro/estrelas atrás de tabela **mata a legibilidade** — por
  isso "tunado pra dados": vidro/aura no resumo, sólido no dado.
- **Verde/vermelho ficam.** É semântica de dinheiro; abrir mão disso pra ficar azul-mono seria
  bonito e **errado** pra um terminal de trading.
- **Nada de gradiente em métrica.** Gradiente só no título hero (opcional). Números são o produto:
  legibilidade > enfeite.

---

**Como rodar/testar localmente:** `uvicorn api:app --port 8000` (na raiz do projeto) e abrir
`http://localhost:8000`. O front é servido pelo próprio backend no modo monolito.
