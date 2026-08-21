# DESIGN.md - Cripto Bot Terminal

Fonte da verdade do sistema visual do painel (`web/index.html`). O CSS e os `style` inline dos
renders JS sao projecoes deste arquivo. Se divergirem, este arquivo vence.

Origem das decisoes: `PLANO-FRONTEND-REDESIGN.md` (secao 4, "Decisoes TRAVADAS"). Este documento
nao reabre aquelas decisoes; ele as traduz em tokens, regras e criterios verificaveis.

## Context (from discovery)

- Artifact type: dashboard / data tool. Terminal de paper trading, alta densidade numerica.
- Positioning: technical. Instrumento de operacao, nao pagina de marketing.
- Audience: o dono do projeto, sessao longa, olhando numero que muda a cada 3s.
  Primary action: decidir sobre um sinal (confirmar ou pular) sem ler errado.
- Adjectives: calmo, premium, denso, honesto, noturno.
- Visual word translations:
  - calmo: fundo navy sem ruido, movimento so onde comunica estado, zero brilho gratuito
  - premium: vidro e aura restritos ao resumo, sombra unica por elemento, espaco generoso entre secoes
  - denso: numero em tabular-nums, tabela com separador leve, trilho lateral aproveitando a largura
  - honesto: verde e vermelho reservados a dinheiro, nunca decorativos; nada de gradiente em metrica
  - noturno: base #0a1020, nunca preto puro, texto off-white
- Aesthetic essence (3 words): mesa, meia-noite, instrumento.
- Single-minded proposition: um instrumento calmo onde o numero e o produto.
- Archetype: Sage.
- References: admirar dashboards navy com glass no resumo (a referencia G.Take descrita na secao 3
  do plano, pela atmosfera e pela sidebar). Evitar: copiar a baixa densidade dela, e evitar o
  terminal cyberpunk de neon sobre preto puro.
- Mode: dark only. Density: dense.
- Constraints: arquivo unico `web/index.html`, sem build, sem framework, sem script de terceiro
  (libs vendoradas em `web/vendor/`), IDs e handlers globais preservados, funciona em monolito
  (`API_BASE` vazio) e split (Vercel + backend separado).

## Aesthetic

- Direction: "mesa de trading a meia-noite". Navy profundo, acento azul vivo, vidro seletivo.
- Defining trait: **vidro no resumo, solido no dado**. Superficie translucida so onde o conteudo e
  agregado (hero, stat cards, status do auto-trade). Sob tabela, metrica e qualquer numero que se
  le, a superficie e opaca. Legibilidade ganha de atmosfera, sempre.
- Signature move: **card hero de equity com aura azul e sparkline ao vivo** desenhado a partir do
  `equity_hist` que o poll de 3s ja traz. Um unico elemento atmosferico na tela, e ele mostra dado.

## Typography

- Display: Space Grotesk | source: Google Fonts | license: OFL
- Body/data: Inter (com `font-variant-numeric: tabular-nums`) | source: Google Fonts | license: OFL
- Mono: JetBrains Mono | source: Google Fonts | license: OFL | uso: celula numerica densa, rotulo
  tecnico, valores no gate de login
- Scale: ratio 1.25 (Major Third), base 14px (densidade de terminal; corpo de dado nunca abaixo de 13px)

| step | size | line-height | uso |
|---|---|---|---|
| hero | 38px | 1.05 | valor de equity no card hero |
| stat | 26px | 1.1 | valor dos stat cards |
| h1 | 18px | 1.3 | marca na sidebar |
| h2 | 12px | 1.4 | titulo de painel (uppercase, tracking .6px) |
| body | 14px | 1.5 | texto e celula de tabela |
| small | 11.5px | 1.5 | rotulo, meta, legenda |

- Weights: 400 / 500 / 600 / 700 / 800. Measure: nao se aplica (sem texto corrido longo).
- Tracking: -1px no hero, -.5px no stat, +.6px nos rotulos uppercase.

## Color

- Strategy: navy como dominante porque a tela fica aberta horas e qualquer saturacao de fundo
  cansa. O acento azul (#3b82f6, oklch H 259.8) e um azul verdadeiro, nao indigo/violeta: a faixa
  H 250-320 e o oceano vermelho da UI gerada por IA, e H 259.8 fica na borda fria dela, longe do
  #6366f1 (H ~274) que e o centro do clone. A diferenciacao real deste projeto nao vem do matiz e
  sim do signature move e da regra de que verde e vermelho so falam de dinheiro.
- Distribution: 60 navy / 30 azul / 10 verde-vermelho.
- Palette (role -> OKLCH | hex):
  - bg: oklch(0.176 0.035 267.3) | #0a1020
  - bg-grad-top: oklch(0.211 0.051 267.1) | #0e1730
  - surface (solida, sob dado): oklch(0.229 0.041 264.9) | #131c30
  - surface2 (elevada, input): oklch(0.256 0.041 261.8) | #182337
  - glass (so resumo): rgba(23,33,58,.55), composta sobre bg = #11192e
  - fg: oklch(0.943 0.013 266.7) | #e8ecf5
  - muted: oklch(0.708 0.044 265.6) | #94a1bd
  - muted2: oklch(0.770 0.036 267.6) | #aab4cc
  - border: oklch(0.317 0.059 264.8) | #233150
  - border2: oklch(0.363 0.061 264.9) | #2e3d5e
  - accent: oklch(0.623 0.188 259.8) | #3b82f6
  - accent2: oklch(0.714 0.143 254.6) | #60a5fa
  - success/alta: oklch(0.734 0.163 159.8) | #16c784
  - error/baixa: oklch(0.663 0.192 20.8) | #f2555e
  - warning: oklch(0.813 0.165 86.7) | #f0b90b
- Regra semantica dura: verde e vermelho **so** para dinheiro e direcao (P&L, LONG/SHORT, vela,
  alerta de risco). Nunca para nav ativa, foco, botao primario ou estado de UI. Azul faz esse
  trabalho. Gold faz aviso.
- Nota sobre o error: o plano propunha #ea3943, que reprova o gate de contraste (4.18:1 sobre
  surface, 4.30:1 sobre o vidro). Substituido por #f2555e (5.04:1 e 5.19:1), o vermelho mais
  proximo do original que passa. O #ea3943 sobrevive apenas como preenchimento translucido
  (`--red-bg`) e nas velas do grafico, onde e forma e nao texto.

## Spacing, radius, shadow

- Spacing base: 4px. Escala usada: 4, 6, 8, 10, 14, 18, 22, 28.
- Ritmo: 8-10px dentro de um grupo, 14px entre cards da mesma secao, 22-28px entre secoes.
- Radius: 16px (card) e 10px (interno). Nada acima de 16px em card pequeno.
- Shadow: **uma por elemento**. Card de dado usa borda definida e nenhuma sombra. Card de vidro usa
  sombra suave e borda quase invisivel (rgba branca .08), nunca as duas com peso. Sombra e preto
  transparente, nunca cinza opaco, nunca colorida com glow.

## Layout and composition

- Grid: sidebar fixa 232px + conteudo. Dentro do conteudo, bento: linha de resumo (hero 1.6fr +
  3 stat cards) e depois duas colunas, principal (fluida) e trilho direito (340px).
- Coluna principal: Curva de capital, Sinais, Posicoes, Journal. Trilho direito: Auto-trade,
  Sentimento, Funding, DCA, Metricas. Criterio: o que se le em sequencia fica na coluna larga; o
  que se consulta de relance fica no trilho.
- Signature layout move: o hero de equity ocupa a largura de tres stat cards e e o unico elemento
  com aura; a grade inteira e calma para que ele seja o unico ponto de gravidade.
- Density: dense. Scanning: F (rotulo a esquerda, numero a direita).
- Responsive: desktop-first com quebras em 1180px (trilho desce), 900px (sidebar vira topo,
  stat cards em 2 colunas) e 560px (stat cards em 1 coluna). Sem scroll horizontal: tabela larga
  rola dentro do proprio wrapper, nunca a pagina.

## Components and states

- Button hierarchy: primario preenchido em azul (`--accent`), secundario com borda sobre
  `surface2`, terciario so texto. Ranking por importancia, nunca cor por significado. Excecao
  unica e deliberada: Panico e vermelho porque a cor **e** o significado (dinheiro/risco).
- Estados: todo botao tem rest, hover (brightness 1.12, so em `hover:hover`), active
  (brightness .92 + translateY 1px), disabled (opacity .5, sem transform), focus-visible
  (outline 2px `--accent`, offset 2px). Nav da sidebar tem ainda selected (`.on`).
- Inputs: label visivel sempre, nunca placeholder como label. Foco troca a borda para `--accent`
  e adiciona anel `rgba(59,130,246,.13)`. Erro mantem o valor digitado.
- Tables: texto a esquerda, numero a direita em tabular-nums, separador `1px solid var(--border)`
  no topo da celula, sem borda externa pesada.
- Overlays: modal com role=dialog, foco no primeiro campo, Esc fecha, foco volta ao gatilho.
- Empty / loading / error: skeleton `.skel` com shimmer no primeiro carregamento, `.empty` para
  vazio, `.empty.off` para backend fora do ar. Os tres sao desenhados, nao improvisados.
- Focus ring: outline 2px `--accent` com offset 2px. Nunca removido sem substituto.

## Motion

- Duration: 150ms (estado de controle), 300ms (entrada de camada), 450-500ms (entrada do gate).
- Easing: `cubic-bezier(.2,.8,.25,1)` para entrada. Sem bounce, sem elastic.
- O que anima: apenas `transform` e `opacity`. Excecao herdada e aceita: `filter: brightness` nos
  botoes, que nao causa layout e e mais barato que trocar background.
- reduced-motion: `prefers-reduced-motion: reduce` zera animacao e transicao globalmente e desliga
  o shimmer do skeleton e a varredura do gate.
- Signature motion: a aura do hero nao pulsa. O unico movimento continuo da tela e o `.dot` do
  badge AO VIVO, porque ele significa "o poll esta vivo".

## Iconography

- Sidebar: SVG inline, grid 24, stroke 1.75, linecap e linejoin round, `currentColor`. Um so
  sistema para os seis itens (Painel, Grafico, Escanear, Panico, Resetar, Sair).
- Todo botao so-icone tem nome acessivel (`aria-label` ou texto em `.sr-only`).
- Divida conhecida: os titulos de painel ainda usam emoji como icone, o que o sistema acima nao
  cobre. Fica para o P2-25 (acabamento), junto da auditoria anti-slop.

## Imagery and illustration

- Nao ha imagem. A unica textura e a malha de 34px do gate de login, mascarada em radial, e a aura
  radial do fundo. Nada de blob, orb, ilustracao isometrica ou foto de banco de imagem.
- Text-over-image: nao se aplica; nenhum texto assenta sobre imagem.

## Dark mode

- Modo unico. Base #0a1020, nao preto puro. Texto #e8ecf5, nao branco puro.
- Elevacao por lightness: bg 0.176 -> surface 0.229 -> surface2 0.256 -> border 0.317 -> border2 0.363.
- Acento no escuro e o proprio `--accent`; `--accent2` e o irmao mais claro para texto sobre
  superficie escura.
- Bordas sao mais claras que a superficie. Sem glow colorido por reflexo.

## Accessibility

- Contrast (verificado, alvo 4.5:1 sobre `--surface` #131c30):
  fg 14.35:1, muted 6.54:1, muted2 8.18:1, accent 4.62:1, accent2 6.68:1, green 7.71:1,
  error #f2555e 5.04:1, gold 9.42:1. Sobre o vidro composto #11192e todos sobem.
- Focus: visivel e gerenciado em todo elemento interativo.
- Keyboard: totalmente operavel. Alvos >= 24px.
- Color independence: direcao nunca depende so de cor. LONG/SHORT tem texto, P&L tem
  simbolo triangular, risco tem rotulo alem da barra.
- Reduced motion: respeitado.

## Tokens (source of truth)

```css
:root{
  --bg:#0a1020; --bg-grad-top:#0e1730; --aura:rgba(59,130,246,.18);
  --glass:rgba(23,33,58,.55); --glass-border:rgba(255,255,255,.08);
  --surface:#131c30; --surface2:#182337;
  --border:#233150; --border2:#2e3d5e;
  --txt:#e8ecf5; --muted:#94a1bd; --muted2:#aab4cc;
  --accent:#3b82f6; --accent2:#60a5fa; --accent-bg:rgba(59,130,246,.14);
  --green:#16c784; --green-bg:rgba(22,199,132,.12);
  --red:#f2555e;   --red-bg:rgba(234,57,67,.12);
  --gold:#f0b90b;
  --r-card:16px; --r-inner:10px;
  --shadow:0 10px 30px rgba(0,0,0,.35);
  --blur:14px;
  --font-display:'Space Grotesk',system-ui,sans-serif;
  --font-ui:'Inter',system-ui,sans-serif;
  --font-mono:'JetBrains Mono',ui-monospace,'Cascadia Mono',monospace;
}
```

- Adapter: plain CSS custom properties, declaradas no bloco `<style>` de `web/index.html`.
- Aliases de transicao: `--card`, `--card2`, `--bg2` e `--mono` continuam existindo apontando para
  os tokens novos, porque os paineis ainda nao migrados (P2-22 a P2-24) miram esses nomes. Eles
  saem quando o ultimo painel migrar.

## Cards and surfaces

- Card de dado: `background: var(--surface)`, `border: 1px solid var(--border)`, radius 16px,
  padding 18px 20px, **sem sombra**.
- Card de resumo: `background: var(--glass)`, `backdrop-filter: blur(14px)`,
  `border: 1px solid var(--glass-border)`, radius 16px, `box-shadow: var(--shadow)`.
- Nunca card dentro de card dentro de card. Bloco interno usa `surface2` sem borda propria quando
  ja esta dentro de um card com borda.

## Slop audit

- Date: 2026-08-21 | Result: corrigidos 4 tells, 2 desvios declarados, 1 divida registrada.
- Corrigidos:
  1. **Gradiente em metrica**: `.card.hero .val` pintava o valor de equity com
     `linear-gradient(90deg,#fff,#9fe9d4)` em background-clip:text. Removido. O numero e o produto;
     legibilidade ganha de enfeite. Tambem e proibicao explicita da secao 5 do plano.
  2. **Contraste reprovando**: `--red` #ea3943 dava 4.18:1 sobre a superficie nova. Trocado por
     #f2555e (5.04:1).
  3. **Borda hairline + sombra difusa no mesmo elemento**: card de dado agora tem borda e nenhuma
     sombra; card de vidro tem sombra e borda quase invisivel. Uma coisa por elemento.
  4. **Cor semantica em UI**: nav ativa e botao primario usavam verde (`--green-bg`/`--green`),
     gastando o vocabulario de dinheiro em estado de interface. Agora azul.
- Desvios declarados (a checklist da skill marca, o plano trava, o plano vence):
  1. **Space Grotesk** e listada pela checklist como tell de convergencia. Mantida: e decisao
     travada do dono (secao 4.3 do plano) e faz um trabalho concreto aqui, que e separar titulo de
     dado sem introduzir uma serifada num terminal.
  2. **Inter** e listada como face proibida. Mantida como face de **dado**, nao de display, pela
     razao que motivou a escolha original: `tabular-nums` de qualidade em grade numerica densa. O
     display e Space Grotesk, entao o par display+body existe e nao e a mesma fonte.
- Divida registrada: emoji ainda funciona como icone nos titulos de painel e em varios botoes fora
  da sidebar. Fora do escopo de P2-20/P2-21. Enderecar no P2-25.
- Gate de acessibilidade: passa (contraste medido acima, foco visivel, operavel por teclado, alvos
  >= 24px, significado nunca so por cor, reduced-motion respeitado).

## Changelog

- 2026-08-21: criado no P2-20. Tokens navy/azul, shell com sidebar, bento, e o hero de equity com
  aura e sparkline do P2-21. Paineis, tabelas e graficos ainda rodam nos aliases de transicao e
  serao migrados em P2-22, P2-23 e P2-24.
