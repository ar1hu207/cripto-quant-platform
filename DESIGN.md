# DESIGN.md — Apollux · direção Pulse (v2)

Fonte da verdade do sistema visual do front (`web/index.html` + `web/app/`). O CSS da casca e o CSS
escopado de cada view são projeções deste arquivo. Se divergirem, este arquivo vence.

**Direção atual: Apollux, direção Pulse, paleta padrão Elétrico.** Decidido pelo dono em
2026-11-12 ("do jeito que está no mock, está perfeito"): marca Apollux, agente Apollo, seletor de
12 paletas lembrado no `localStorage`. Fonte do desenho: os mockups em `DS/mockups/d4-pulse.html` e
`DS/mockups/pulse-views/` (fora do git, do dono) e o brand book `DS/BRAND-BOOK-2026-11-12.md`.

Os valores abaixo foram **medidos** no front em produção local (Chromium, 1366 px, `getComputedStyle`
e o próprio `web/app/paletas.js`), não copiados de memória do mock. Contraste calculado pela fórmula
WCAG 2.1 sobre os hex das 12 paletas.

Histórico: de 2026-08-22 a 2026-11-12 a direção foi a transposição do CoinMarketCap night (tabela
protagonista, hairline, raio pequeno); ela vive intacta em `web/classico.html` e no histórico do git
deste arquivo.

---

## Contexto

- Tipo: terminal de operação + ferramenta de análise. Um operador (o dono), sessão longa, número
  mudando a cada 3 s.
- Ação principal: decidir sobre um sinal ou uma posição sem ler errado, e saber em um olhar se o
  Apollo está ligado, se a trava disparou e quanto o dia já custou.
- Adjetivos: vivo, noturno, preciso, elétrico, honesto.
- Essência: **um instrumento com presença**. O Apollo é uma esfera de partículas que respira;
  os números são o chão firme em volta dela.
- Modo: **escuro apenas**. Densidade: média (cards com respiro, tabelas densas dentro).
- Restrições: estático, sem build, sem framework (`web/` + `web/app/`), libs vendoradas em
  `web/vendor/`, nenhum script de terceiro (CLAUDE.md §2), funciona em monolito (`API_BASE` vazio,
  `uvicorn api:app`) e separado (Vercel + backend no dl380).

## Regras que não se negociam

1. **Tudo por token.** Nenhuma cor literal nas views: elas usam `var(--x)` e `rgba(var(--x-rgb),a)`.
   O canvas e o Lightweight-Charts, que só aceitam string, leem os tokens do `:root` na hora
   (`APX.cor`, `APX.rgba`) e repintam no evento `paleta`.
2. **O acento nunca vai em P&L.** Lucro é `--pos`, prejuízo é `--neg`, sempre, nas 12 paletas.
   O acento é marca, foco, estado do Apollo e ação primária.
3. **Número de mock não entra.** Ou é dado real de uma rota, ou é estado vazio dito em palavras.
   O que o mock mostrava sem rota que o sustente vira "em breve" com a fase.
4. **Movimento respeita `prefers-reduced-motion`**: sem contagem, sem traçado, sem entrada; canvas
   desenha um frame só.

---

## Cor

### Os tokens

Cada paleta define 15 valores (`web/app/paletas.js`, `window.APOLLUX_PALETAS`); a casca
(`app/casca.js · aplicaPaleta`) os escreve no `:root` e deriva os canais RGB e os níveis de brilho.

| token CSS | campo da paleta | papel |
|---|---|---|
| `--bg` | `bg` | fundo da página |
| `--panel` | `panel` | superfície de card |
| `--panel2` | `panel2` | superfície dentro de card (item de lista, input, caixa) |
| `--line` · `--line2` | `line` · `line2` | hairline padrão · borda que precisa aparecer (input, botão ghost) |
| `--txt` · `--txt2` · `--mute` | `text` · `text2` · `mute` | texto principal · secundário · rótulo e legenda |
| `--accent` | `accent` | marca, foco, Apollo, ação primária. **Nunca P&L** |
| `--accent-ink` | `on` | texto sobre o acento (botão primário) |
| `--pos` · `--neg` | `pos` · `neg` | alta/lucro/LONG · baixa/prejuízo/SHORT |
| `--warn` · `--info` | `warn` · `info` | aviso, guarda perto do teto · informação neutra, Donchian |
| `--glow` | `glow` | intensidade do brilho da paleta (0,20 Osso → 0,50 Neon) |
| `--glow-hi` · `--glow-lo` · `--glow-xlo` | derivados | `glow × 1,6` (teto 1) · `× 0,5` · `× 0,25` |
| `--{bg,panel,txt,line,accent,pos,neg,warn}-rgb` | derivados | o mesmo hex como `r,g,b`, para alfa |

Precedência na abertura: `?paleta=` na URL (ou no hash) > `localStorage['pulse.paleta']` > `eletrico`.
O `<head>` já nasce com os valores do Elétrico, então a primeira pintura não pisca.

### As 12 paletas, medidas

Contraste WCAG 2.1 de cada par que a interface usa para texto. Alvo: 4,5:1 (AA, texto normal).
**Nenhum par fica abaixo de 4,5 em nenhuma paleta** (o menor é `mute` sobre `panel2` na Violeta,
4,59). Fonte: `web/app/paletas.js`, calculado em 2026-11-12.

| paleta | família | bg | panel | accent | pos | neg | warn | text/panel | text2/panel | mute/panel | mute/panel2 | accent/panel | on/accent | pos/panel | neg/panel | warn/panel |
|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Neon (neon) | verde | `#030705` | `#0A1410` | `#00FF88` | `#34D399` | `#FF4D6D` | `#FFD166` | 17,88 | 8,16 | 4,94 | 4,62 | 13,98 | 14,13 | 9,75 | 5,83 | 13,00 |
| Elétrico (eletrico) | azul | `#03060C` | `#0A1220` | `#4DA3FF` | `#34D399` | `#FF5C6A` | `#FFC24D` | 16,64 | 7,81 | 5,16 | 4,80 | 7,14 | 7,28 | 9,75 | 6,24 | 11,67 |
| Solar (solar) | âmbar | `#0A0704` | `#15100A` | `#FFB020` | `#3FD98C` | `#FF5A5F` | `#FF7A1A` | 17,65 | 9,21 | 5,74 | 5,44 | 10,34 | 10,27 | 10,37 | 6,20 | 7,25 |
| Ouro (ouro) | dourado | `#0B0A08` | `#141210` | `#E2C275` | `#3FD98C` | `#FF5A5F` | `#FF8A3D` | 16,58 | 8,51 | 5,23 | 4,91 | 10,86 | 10,65 | 10,25 | 6,12 | 7,97 |
| Holo (holo) | ciano | `#04080A` | `#0A1418` | `#19E6FF` | `#2BE39A` | `#FF5C6A` | `#FFB020` | 17,41 | 8,72 | 5,68 | 5,29 | 12,26 | 11,97 | 11,15 | 6,21 | 10,20 |
| Magenta (magenta) | rosa | `#0A040A` | `#150A14` | `#FF3DA6` | `#34D399` | `#FF6B4D` | `#FFD166` | 17,59 | 8,09 | 4,90 | 4,62 | 5,96 | 6,01 | 10,06 | 6,88 | 13,42 |
| Violeta (violeta) | roxo | `#06050C` | `#0E0C1A` | `#8B6CFF` | `#34D399` | `#FF5C6A` | `#FFC24D` | 16,57 | 7,79 | 4,84 | 4,59 | 5,24 | 5,29 | 10,06 | 6,44 | 12,04 |
| Osso (osso) | mono | `#0B0B0C` | `#121214` | `#E8E4D9` | `#3FD98C` | `#FF5A5F` | `#E3B341` | 16,00 | 6,70 | 5,46 | 5,17 | 14,73 | 14,75 | 10,26 | 6,13 | 9,61 |
| Aço (aco) | azul-cinza | `#0A0C10` | `#111419` | `#9FB3C8` | `#3FD98C` | `#FF5A5F` | `#E3B341` | 15,71 | 7,59 | 4,93 | 4,61 | 8,57 | 8,72 | 10,12 | 6,05 | 9,48 |
| Lima (lima) | verde-amarelo | `#0A0A06` | `#131408` | `#D4FF3F` | `#3FD98C` | `#FB7185` | `#FF8A3D` | 17,32 | 9,38 | 5,77 | 5,41 | 16,07 | 15,66 | 10,18 | 6,90 | 7,92 |
| Menta (menta) | verde-água | `#040908` | `#0A1513` | `#5CF0C8` | `#4ADE80` | `#FF5C6A` | `#FFD166` | 17,84 | 9,00 | 5,70 | 5,36 | 13,06 | 12,04 | 10,67 | 6,19 | 12,89 |
| Coral (coral) | laranja | `#0B0605` | `#160C0A` | `#FF6A3D` | `#3FD98C` | `#FF2D6F` | `#FFD166` | 17,46 | 8,53 | 5,42 | 5,15 | 6,76 | 6,71 | 10,55 | 5,37 | 13,35 |

Os demais valores de cada paleta:

| paleta | panel2 | line | line2 | text | text2 | mute | on | info | glow |
|---|---|---|---|---|---|---|---|---|---:|
| Neon | `#0F1C16` | `#123D2A` | `#1C5A3E` | `#E8FFF3` | `#8FB3A3` | `#6B8A78` | `#03140A` | `#4DA3FF` | 0,5 |
| Elétrico | `#0F1A2C` | `#16304F` | `#1F4573` | `#EAF2FF` | `#93A9C8` | `#7088A8` | `#04101F` | `#7DD3FC` | 0,45 |
| Solar | `#1C1610` | `#3D2E14` | `#5A431C` | `#FFF6E8` | `#C4B394` | `#9A8C72` | `#1A1000` | `#7DD3FC` | 0,35 |
| Ouro | `#1B1915` | `#3A3220` | `#55492E` | `#F5F1E8` | `#B8AE9A` | `#8F8772` | `#1A1405` | `#7DD3FC` | 0,3 |
| Holo | `#0F1C22` | `#143A44` | `#1D5563` | `#E6FBFF` | `#8FB8C4` | `#6E949F` | `#04181D` | `#7DD3FC` | 0,45 |
| Magenta | `#1E1020` | `#3F1A3D` | `#5C2659` | `#FFF0FA` | `#C49BBE` | `#977691` | `#1C0414` | `#7DD3FC` | 0,45 |
| Violeta | `#151226` | `#2B2550` | `#3E3670` | `#EFEBFF` | `#A79FCB` | `#817AA5` | `#0F0820` | `#7DD3FC` | 0,4 |
| Osso | `#18181B` | `#2A2A2F` | `#3A3A41` | `#EDEDEF` | `#9A9AA3` | `#8A8A92` | `#121212` | `#9FB3C8` | 0,2 |
| Aço | `#171B22` | `#2A313D` | `#3B4553` | `#E9EDF3` | `#9CA7B8` | `#7A8594` | `#0E1218` | `#7DD3FC` | 0,25 |
| Lima | `#1A1B0C` | `#35381A` | `#4C5026` | `#F7F8EC` | `#B8BB9A` | `#8F9272` | `#141800` | `#7DD3FC` | 0,35 |
| Menta | `#0F1C1A` | `#164038` | `#215C50` | `#E9FFFA` | `#93BDB3` | `#71968C` | `#03201A` | `#7DD3FC` | 0,4 |
| Coral | `#1E120F` | `#3F2119` | `#5C3024` | `#FFF1EC` | `#C8A59A` | `#9E8277` | `#1E0A03` | `#7DD3FC` | 0,35 |

---

## Tipografia

Três famílias, todas pelo Google Fonts (a única exceção de terceiro do `web/`, stylesheet sem JS,
carregada sem bloquear: `preload` + `onload`, como no P2-37).

| papel | família | medido |
|---|---|---|
| display (título da view, nome do Apollo, par no gráfico) | **Syne** 600-800 | h1 24 px / 800 / `-0.01em`; h2 de card 16 px / 700 / `-0.01em`; par 22 px / 800; nome do Apollo 34 px / 800 com brilho do acento |
| interface (texto, botão, nav) | **DM Sans** 400-600 | corpo 14 px / 1.45; nav 14 px / 600; botão 12,5 px / 600; botão `sm` 12 px |
| números e rótulos | **Fira Code** 400-600 | valor de KPI 27 px / 600 / `-0.02em`; rótulo de KPI e `eyebrow` 10,5 px / caixa alta / `0.12em`; chip 10,5 px / 600; contador 11 px; célula de tabela 12 px com `tabular-nums` |

Regra: **todo número é Fira Code**, com algarismos tabulares, para que o poll de 3 s não faça a
coluna dançar. Rótulo em caixa alta só em mono e só até 11 px.

## Forma e espaço

| medida | valor |
|---|---|
| raio de card (`--r`) | 14 px |
| raio de botão · input | 9 px · 9 px (`sm`: 8 px) |
| raio de chip · contador/"em breve" | 5 px · pílula (999 px) |
| padding de card · de KPI | 18 px · 18 × 20 px |
| gap entre cards (todas as views) | 18 px |
| grade da casca | sidebar 240 px + conteúdo; ≤ 1024 px a sidebar vira faixa de navegação; ≤ 640 px a nav rola na horizontal |
| gutter lateral no celular | 16 px (com `env(safe-area-inset-*)`) |
| borda | 1 px `--line` em tudo; `--line2` onde a borda precisa aparecer |

## Movimento

| o quê | como | quando |
|---|---|---|
| contador de KPI | GSAP 1,4 s `power3.out` de 0 ao valor | **só na primeira carga**; nos polls seguintes troca o texto e dá um `flash` de 0,6 s |
| entrada da view | GSAP `y 14 → 0`, opacidade, 0,5 s, `stagger` 0,06 | a cada troca de rota |
| curva de equity | traçado 2 s `power2.inOut`, área entra em 1,2 s | só na primeira carga da view |
| gauge (win rate, convicção) | 1,5 s `power3.out` | só na primeira carga |
| calendário do Dia a dia | células de `scale .5` a 1, `stagger` 6 ms | só na primeira leitura |
| LED de estado | pulsa 1,6 s | contínuo, CSS |
| faixas de luz do fundo | deriva 18 s e 22 s `sine.inOut` | contínuo, GSAP |
| hover de card e botão | 0,18-0,2 s em borda e sombra | CSS |

Com `prefers-reduced-motion` (ou `?static=1`): nada disso anima, o valor final aparece direto.

## Componentes e estados

- **Card**: `--panel`, borda `--line`, raio 14, `card-head` com `h2` à esquerda e um `count` (pílula
  mono) à direita. Estados: normal, hover (borda clareia), vazio (`.empty`, borda tracejada e uma
  frase do que falta), carregando (`.skel`, barra com brilho correndo), erro (frase com a rota que
  falhou), "em breve" (`.soon`, pílula mono tracejada com a fase).
- **KPI**: faixa de 4 colunas com divisória de brilho; rótulo mono, valor mono 27 px, linha de
  contexto mono 11,5 px. P&L com sinal explícito (`+`/`−` tipográfico) e cor `--pos`/`--neg`.
- **Chip**: `long`/`short` (pos/neg), `info`, `neutro`, `warn`. Direção do trade e estado, nunca
  enfeite.
- **Botão**: `primary` (acento cheio, tinta `--accent-ink`), `ghost` (borda `--line2`), `danger`
  (borda e texto `--neg`), `danger solid` (só no confirmar de diálogo destrutivo), `sm`.
- **Guarda**: pílula com LED; `hot` quando a guarda está agindo, `off` quando desligada.
- **Diálogo**: toda ação que mexe em dinheiro ou config passa por ele, na página (nunca `confirm()`):
  diff `antes → depois`, aviso de `toca-risco` quando cabe; reset exige digitar `RESET`.
- **Barra de estado offline**: faixa `--warn` acima do conteúdo quando o `/estado` falha; os números
  ficam, com o aviso de que são o último retrato. 401 volta ao portão de login.
- **Gate (login)**: card central, prova de vida do backend (`/health`, versão e commit), olho para
  mostrar a senha, aviso de Caps Lock, contagem regressiva no 429.

## As três peças vivas

1. **Esfera do Apollo** (`app/apollo-mesh.js`). Esfera de Fibonacci de **pontos, sem linhas**, que
   respira e se deforma quando ele fala. Duas instâncias: `mini` no widget fixo (700 pontos; 360
   em ≤ 640 px) e `full` no topo da #apollo (3.200; 1.400 em ≤ 640 px). API do contrato:
   `setLevel` (mais acesa ligado, apagada desligado), `speak(ms)` (o resumo do "Chamar Apollo"),
   `pulse()` (evento real: posição aberta/fechada, sinal novo, ordem, trava), `pause/resume`.
   Para com a aba escondida **e fora da tela** (IntersectionObserver), e no `destroy`.
2. **Bolhas da carteira** (#carteira). Uma bolha por posição aberta e por plano de DCA, mais a
   bolha tracejada do saldo livre; área proporcional à margem (ou ao valor do DCA), aro `--pos` ou
   `--neg` pelo P&L. Empacotamento por relaxação, arrastáveis com pointer events. DOM, não canvas.
3. **Terreno de partículas** (fundo da curva no #painel). Grade de pontos 50 × 30 (30 × 18 em
   ≤ 640 px) com um pico que respira e segue o mouse; decorativo, declarado como tal na legenda.
   Para fora da tela, com a aba escondida e no `destroy`.

## Gráficos

- Lightweight-Charts (vendorado) para velas: vela `--pos`/`--neg`, EMA 20 `--accent`, EMA 50
  `--warn`, Bollinger `--txt2`, Donchian `--info` tracejado, liquidez `--warn` pontilhada, entrada e
  stop como linhas de preço. Precisão do eixo pela grandeza do preço.
- SVG próprio para curva de equity, gauges, sparklines e calendário: traço do acento com brilho
  (filtro `feGaussianBlur`), área com gradiente do acento a 0,32 → 0.
- Mapa de calor e calendário de P&L: intensidade em 3 degraus de alfa sobre `--pos`/`--neg`.
