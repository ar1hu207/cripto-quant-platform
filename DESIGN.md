# DESIGN.md - Cripto Bot Terminal

Fonte da verdade do sistema visual do painel (`web/index.html`). O CSS e os `style` inline dos
renders JS sao projecoes deste arquivo. Se divergirem, este arquivo vence.

**Direcao atual: transposicao do design system do CoinMarketCap, tema escuro.**
Decidido em 2026-08-22 pelo dono do projeto, substituindo a direcao navy/glassmorphism da secao 4
do `PLANO-FRONTEND-REDESIGN.md`. Aquela secao esta obsoleta; o que vale e este arquivo.

Este documento nao descreve o CMC de memoria. Os valores abaixo foram **medidos** carregando
coinmarketcap.com em navegador real e lendo o `:root` deles (rampas completas, os dois temas),
mais a medicao do que estava renderizado (frequencia de cor, fonte, raio, peso, e o componente
de tabela). O que nao veio deles esta marcado como **desvio declarado**, com o motivo.

---

## Context

- Artifact type: dashboard / data tool. Terminal de paper trading, alta densidade numerica.
- Positioning: technical, utilitario. Instrumento de operacao.
- Audience: o dono do projeto, sessao longa, numero mudando a cada 3s.
  Primary action: decidir sobre um sinal (confirmar ou pular) sem ler errado.
- Adjectives: denso, plano, direto, familiar, noturno.
- Aesthetic essence: **planilha viva**.
- Single-minded proposition: parece um terminal de mercado que voce ja sabe usar.
- Mode: **dark only**. Density: dense.
- Constraints: arquivo unico `web/index.html`, sem build, sem framework, sem script de terceiro
  (libs vendoradas em `web/vendor/`), IDs e handlers globais preservados, funciona em monolito
  (`API_BASE` vazio) e split (Vercel + backend separado).

## Aesthetic

- Direction: **CoinMarketCap night**. Plano, hairline, raio pequeno, zero vidro, zero aura,
  zero sombra decorativa. A hierarquia vem de **peso e tamanho de fonte**, nao de superficie.
- Defining trait: **a tabela e a protagonista**. Ela nao mora dentro de um card; ela ocupa a
  largura e o resto da pagina se organiza em volta. Card so existe para o que nao e tabela.
- Signature move: **a linha da tabela termina em sparkline**. Toda linha que representa algo que
  se move no tempo (posicao, plano DCA, faixa de conviccao) fecha com a mini-curva daquilo, do
  mesmo jeito que o CMC fecha cada moeda com o 7d. E o que faz uma grade de numeros virar leitura.

---

## Color

Paleta escura do CMC, com **quatro correcoes de contraste**. O sistema deles reprova WCAG AA em
quatro tokens, e o nosso plano trata contraste como portao, nao enfeite. Cada correcao clareia o
token **dentro da propria rampa**, preservando matiz e saturacao (a maior mexe +0.17 de
luminancia).

### Superficies e linha

| token | valor | origem CMC |
|---|---|---|
| `--bg` | `#0D1421` | `--c-color-background-2` |
| `--bg-el` | `#171924` | `--c-color-background-1`. Fundo *raised* do chrome (topbar, status bar). Nao se chama `--bg2`: esse nome era o alias morto do tema navy e reaproveita-lo apagaria a fronteira entre token e alias. |
| `--surface` | `#222531` | `--c-color-surface-1` (= gray-100 dark) |
| `--surface2` | `#2B2E3D` | `--c-color-surface-2` |
| `--line` | `#323546` | gray-200 dark. **A borda de 1px e o separador universal deste tema.** |
| `--line2` | `#53596A` | gray-300 dark, para borda que precisa aparecer (input, chip ativo) |

### Texto

| token | valor | contraste (page / surface / surface2) | nota |
|---|---|---|---|
| `--txt` | `#FFFFFF` | 18.44 / 15.25 / 13.45 | `--c-color-text-primary` |
| `--txt2` | `#A1A7BB` | 7.69 / 6.36 / 5.61 | `--c-color-text-secondary` |
| `--txt3` | `#9197A9` | 6.32 / 5.23 / 4.61 | **corrigido**. O `--c-color-text-caption` deles e `#646B80` e da 2.87:1 no card |

### Acento e semanticos

| token | valor | papel | nota |
|---|---|---|---|
| `--accent` | `#3861FB` | **preenche**: botao primario, barra, marca | blue-500. Branco por cima da 4.92:1 |
| `--accent-txt` | `#6B90FF` | **escreve**: link, aba ativa, chip azul | **corrigido**. O `#6188FF` deles da 4.15:1 no elevado |
| `--pos` | `#16C784` | alta, lucro, LONG | green-500, passa em tudo. **Ja era a cor do projeto** |
| `--neg` | `#EF6C73` | baixa, prejuizo, SHORT | **corrigido**. O `#EA3943` deles da 3.75:1 no card |
| `--warn` | `#F5B97F` | aviso, atencao | `--c-color-reminder` (beige-500) |

### Tintas (fundo de chip, banner, celula destacada)

Sao os tons `-800` da rampa do CMC, feitos exatamente para isto no tema escuro:

| tinta | valor | texto por cima | contraste |
|---|---|---|---|
| `--pos-bg` | `#173C37` | `--pos` | 5.49:1 |
| `--neg-bg` | `#411F2A` | `--neg` | 4.86:1 |
| `--accent-bg` | `#1E274F` | `--accent-txt` | 4.84:1 |
| `--warn-bg` | `#433936` | `--warn` | 6.46:1 |

**Variacao de alpha declarada.** Chip e banner semantico precisam de uma borda que diga a mesma
coisa que a tinta sem gritar. Em vez de inventar um terceiro hex por familia, a borda e o proprio
token a **34%** - o valor que a secao Components ja fixa para o botao destrutivo, estendido aos
irmaos: `--pos-b`, `--neg-b`, `--warn-b`. E a unica excecao a regra "nenhuma cor fora de token".

### Regra de par (vale em todo lugar)

Texto colorido sobre a **propria tinta** e onde tema escuro reprova sem avisar: a tinta levanta a
luminancia do fundo e come o contraste. Por isso azul tem dois papeis: `--accent` **preenche**,
`--accent-txt` **escreve**. Verde, vermelho corrigido e warn nao precisam do par: passam sobre a
propria tinta.

### Distribuicao

Neutro domina (~70%). Azul aparece so em acao, link e estado ativo (~20%). Verde e vermelho
somam ~10% e **so falam de dinheiro e direcao**: P&L, LONG/SHORT, vela, entrada/stop, status de
entrada. Nunca em nav ativa, foco, botao primario ou estado de interface.

---

## Typography

**Inter, e so Inter.** E o que o CMC usa, medido: 647 de 647 elementos com texto. Sem face de
display, sem mono. A hierarquia sai de peso e tamanho.

- Family: `Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
- Line-height: **130%** em titulo, **150%** em corpo (os dois tokens deles)

Escala medida no `:root` do CMC, e a frequencia real de uso na home deles:

| token | px | uso | frequencia medida no CMC |
|---|---|---|---|
| `--fs-50` | 11 | rotulo minusculo, legenda de eixo | 4 |
| `--fs-75` | 12 | cabecalho de tabela, meta, chip | 60 |
| `--fs-100` | 14 | **corpo e celula de tabela** | 568 (dominante) |
| `--fs-200` | 16 | subtitulo | 3 |
| `--fs-300` | 18 | titulo de secao | - |
| `--fs-600` | 20 | valor de tile | 10 |
| `--fs-800` | 25 | numero grande | - |
| `--fs-1000` | 32 | equity no topo | - |

Pesos: 400 (corpo raro), **500 (padrao - 507 de 647 no CMC)**, 600 (enfase), 700 (cabecalho de
tabela, titulo). O peso 500 como base e uma marca do CMC e a gente adota.

**Desvio declarado: `font-variant-numeric: tabular-nums` em todo numero.** O CMC usa `normal`
(medido). Aqui os numeros sao repintados a cada 3 segundos pelo poll; sem tabular eles mudam de
largura e a coluna dança. Legibilidade em movimento ganha de fidelidade.

**Desvio declarado: Inter como face unica** contraria a regra "sempre um par display + corpo".
E deliberado: o CMC nao tem par, e a densidade do produto pede uma familia so, com hierarquia por
peso. Trocar isso descaracterizaria a transposicao.

---

## Spacing, radius, shadow, border

Escala de espaco do CMC, adotada inteira: **4, 8, 12, 16, 20, 24, 32, 40, 48, 64**.

Raio do CMC: 2, 4, 8, 12, 16, 20, 50%. Medido no que eles renderizam, o uso real e concentrado:
**4px (211 elementos) e 8px (143)**. Adotamos:

| token | valor | uso |
|---|---|---|
| `--r-sm` | 4px | chip, badge, botao pequeno, input |
| `--r` | 8px | tile, card, painel, modal |
| `--r-pill` | 999px | chip de filtro, pilula de status |

**Sombra: praticamente nao existe.** No CMC medido, so 4 elementos tem sombra na home inteira.
A separacao e feita por **borda de 1px `--line`**. Sombra fica reservada a camada que flutua de
verdade (modal, dropdown), usando o `--c-shadow-overlay` deles:
`0 8px 32px rgba(13,20,33,.5), 0 1px 2px rgba(13,20,33,.4)`.

Isto substitui a regra antiga "aresta OU sombra": aqui e **sempre aresta**, e sombra so quando o
elemento esta por cima de outro conteudo.

**Foco e selecao** usam o padrao medido no CMC: anel interno de 1.5px em `--accent`
(`box-shadow: inset 0 0 0 1.5px var(--accent)`), que nao empurra layout. Para foco de teclado
mantemos `outline` visivel de 2px com offset, porque anel interno sozinho e fraco demais como
indicador de foco.

---

## Layout grammar

O que faz o CMC parecer o CMC nao e a cor, e o arranjo. Sai a sidebar, sai o bento, sai o hero
gigante de equity.

```
+----------------------------------------------------------------+
| (o) Cripto Bot   Painel  Grafico       Escanear Panico  Sair    |  topbar 64px, borda embaixo
+----------------------------------------------------------------+
| Sinais   Posicoes   Journal   Metricas   DCA                    |  tab bar, ativo sublinhado
+----------------------------------------------------------------+
| [Equity     ][Banca      ][Posicoes   ][Risco dia ][Exposicao ] |  fileira de tiles
| [R$ 1.309,30][R$ 1.228,71][    1      ][ ##__ 33% ][ ### 67%  ] |  cada um com sparkline
| [+30.93% ~~~][           ][           ][          ][          ] |  ou barra
+----------------------------------------------------------------+
| (Todos) (LONG) (SHORT) (conv >= 60)                             |  barra de chips
+----------------------------------------------------------------+
|  #  Ativo    Lado   Conv  Entrada   Agora     D      P&L    7d  |  cabecalho grudado
|  1  ARB      LONG    61   0,09660   0,09710  +0,5%  +R$80  ~~~  |  tabela protagonista,
|  2  APT      SHORT   74   4,12000   4,09000  +0,7%  +R$ 1  ~~~  |  sem card em volta
+----------------------------------------------------------------+
| AO VIVO . banca R$1.228 . exp 67% . risco dia -R$22 . 22:41     |  status bar fixa embaixo
+----------------------------------------------------------------+
```

- **Topbar** (56px min): marca a esquerda, nav principal (Painel / Grafico) ao lado, acoes a
  direita. Borda de 1px embaixo, fundo `--bg-el`. Substitui a sidebar.
  **Nao gruda no topo** (decisao do P2-28): com a tab bar o conteudo virou uma tela por bloco e a
  rolagem ficou curta, enquanto um topo grudado obrigaria o `th` sticky da tabela a conhecer a
  altura da topbar - numero magico que quebra assim que ela quebra de linha em 390px.
- **Tab bar**: fica logo abaixo da topbar e acima da fileira de tiles, como no diagrama.
  Navega entre blocos de dado. Item ativo = `--txt` peso 600 + sublinhado de 2px em
  `--accent`; inativo = `--txt2` peso 500. Sem fundo, sem pilula.
- **Fileira de tiles**: caixas de borda hairline, raio 8, sem sombra. Rotulo 12px `--txt3`,
  valor 20-25px peso 700, delta com triangulo colorido, e um sparkline ou barra na base.
- **Barra de chips**: pilulas de raio total, borda `--line`, ativo com fundo `--accent-bg`,
  texto `--accent-txt` e borda `--accent`.
- **Tabela**: largura cheia, sem card. `th` 12px/700 em `--txt3`, borda embaixo `--line`,
  **grudado no topo ao rolar** (`position: sticky`). `td` 14px/500, altura de linha ~48px,
  padding 12px 10px, borda embaixo `--line`. Texto a esquerda, numero a direita, tabular.
  Hover de linha: fundo `--surface`.
  **Desvio declarado: prioridade de coluna no lugar de rolagem horizontal.** Rolar a tabela
  dentro de um wrapper e incompativel com cabecalho grudado - o wrapper com `overflow` vira o
  contexto de rolagem e o `sticky` deixa de mirar a viewport. Em vez disso as colunas somem por
  prioridade (`.col-2` em 1100px, `.col-3` em 820px, `.col-4` em 620px) e o que sumiu continua
  legivel na sub-linha expansivel. A pagina nunca rola na horizontal, e o cabecalho gruda em
  qualquer largura.
  Nas tabelas **sem** sub-linha (posicoes, journal, DCA, metricas) a saida e outra: elas cabem
  inteiras acima de 820px, e so abaixo disso o container vira rolador horizontal. Ali o
  cabecalho deixa de grudar - troca deliberada, porque a alternativa era esconder coluna sem
  ter onde por o que sumiu.
- **Status bar** fixa no rodape: 12px, `--txt2`, borda em cima, fundo `--bg-el`. Carrega o que
  precisa estar sempre visivel (banca, exposicao, risco do dia, AO VIVO, hora do ultimo poll).
  **Substitui os banners de risco** que hoje empurram o conteudo para baixo.

### Onde a curva de capital foi parar

O diagrama nao tem lugar para o grafico de equity, e ele nao pode simplesmente sumir: `#chart` e
um dos IDs que o `carregar()` escreve. Ele mora na aba **Metricas** - e a versao detalhada do que
o tile de equity resume, e Metricas e o bloco que fala de desempenho. Fora de uma aba ele
devolveria a pagina de 8000px que a tab bar existe para acabar.

Consequencia tecnica: o Chart.js mede o container na criacao, e dentro de uma aba escondida essa
medida e zero. O `subaba()` chama `chart.resize()` ao entrar em Metricas.

### O que isso custa

A fila de sinais hoje e uma lista de cards (`.sig`) com "por que" em chips, status de entrada e
tres botoes. Virando linha de tabela, os chips de motivo nao cabem na linha. Solucao especificada:
**linha expansivel** - a linha mostra o essencial e um clique abre uma sub-linha com motivos,
stop e os botoes. E o mesmo padrao que o CMC usa para expandir detalhe de moeda.

---

## Components

- **Botao primario**: fundo `--accent`, texto **branco** (4.92:1), raio 4, peso 600, 14px.
  Estados: hover `--accent-hover` `#2444D4`; active idem com `translateY(1px)`;
  disabled opacity .45.
- **Botao secundario**: fundo transparente, borda `--line2`, texto `--txt2`. Hover: fundo
  `--surface2`.
- **Botao destrutivo** (Panico): fundo `--neg-bg`, texto `--neg`, borda `--neg` a 34%.
  Unica excecao a regra "nunca colorir botao por significado": aqui a cor **e** o significado.
- **Chip / badge**: raio total ou 4px, 12px/600, padding 2px 8px. Direcao usa `--pos-bg`/`--neg-bg`.
- **Input**: fundo `--surface2`, borda `--line2`, raio 4, 14px, foco troca borda para `--accent`
  e adiciona `box-shadow: 0 0 0 3px rgba(56,97,251,.3)` (o `--input-shadow-color-focus` deles).
- **Tabela**: especificada acima. Sem zebra - o separador de 1px basta e zebra em tema escuro
  briga com as tintas de linha.
- **Modal**: `--surface`, raio 8, sombra de overlay, backdrop `rgba(23,25,36,.6)`
  (o `--c-color-overlay-bg` deles). Foco no primeiro campo, Esc fecha, foco volta ao gatilho.
- **Estados vazio / carregando / erro**: skeleton com shimmer no primeiro carregamento, `.empty`
  centrado em `--txt3`, `.empty.off` em `--neg` quando o backend caiu.

## Motion

- `--dur` 150ms (estado de controle), `--dur2` 280ms (camada), `--ease` `cubic-bezier(.2,.8,.25,1)`.
- So `transform` e `opacity`. Transicao sempre **nomeada**, nunca `transition:.15s` solto, que
  vira `all` e poe o browser para vigiar propriedade que causa layout.
- `prefers-reduced-motion` zera animacao e shimmer.
- Este tema e mais parado que o anterior de proposito: o unico movimento continuo e o ponto do
  AO VIVO, que significa "o poll esta vivo".

## Graficos

Chart.js e Lightweight-Charts recebem **string de cor**: nao entendem `var()`. O objeto `TEMA` le
os tokens do `:root` em tempo de carga, entao trocar um token troca a vela junto.

| elemento | cor |
|---|---|
| vela | `--pos` / `--neg` |
| curva de capital, sparkline dos tiles e sparkline de linha | `--accent-txt`, area em `rgba(56,97,251,.28)` |
| EMA20 / EMA50 | `--accent-txt` / `--warn` |
| Bollinger | `rgba(161,167,187,.5)` (`--txt2` translucido; a mediana em `.25`) |
| entrada / stop | `--pos` / `--neg` |
| liquidez, posicao aberta | `--warn` |
| grade | `--line` |

## Accessibility

- Contraste: portao de 4.5:1 em **todo** no de texto, verificado por varredura automatizada na
  pagina renderizada, nao por amostra. As quatro correcoes da secao Color existem por causa disso.
- Foco visivel e gerenciado em todo elemento interativo; alvos >= 24px.
- Significado nunca so por cor: direcao tem texto (LONG/SHORT), P&L tem triangulo, risco tem
  rotulo alem da barra.
- `prefers-reduced-motion` respeitado.

## Tokens

```css
:root{
  /* superficie e linha */
  --bg:#0D1421; --bg-el:#171924; --surface:#222531; --surface2:#2B2E3D;
  --line:#323546; --line2:#53596A;
  /* texto */
  --txt:#FFFFFF; --txt2:#A1A7BB; --txt3:#9197A9;
  /* acento: --accent preenche, --accent-txt escreve */
  --accent:#3861FB; --accent-hover:#2444D4; --accent-txt:#6B90FF; --accent-bg:#1E274F;
  /* semanticos: SO dinheiro e direcao */
  --pos:#16C784; --pos-bg:#173C37;
  --neg:#EF6C73; --neg-bg:#411F2A;
  --warn:#F5B97F; --warn-bg:#433936;
  /* borda de chip/banner: o proprio token a 34% (variacao de alpha declarada) */
  --pos-b:rgba(22,199,132,.34); --neg-b:rgba(239,108,115,.34); --warn-b:rgba(245,185,127,.34);
  /* forma */
  --r-sm:4px; --r:8px; --r-pill:999px;
  --shadow-overlay:0 8px 32px rgba(13,20,33,.5),0 1px 2px rgba(13,20,33,.4);
  --overlay-bg:rgba(23,25,36,.6);
  /* tipografia */
  --font:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  --fs-50:11px; --fs-75:12px; --fs-100:14px; --fs-200:16px; --fs-300:18px;
  --fs-600:20px; --fs-800:25px; --fs-1000:32px;
  --lh-head:1.3; --lh-body:1.5;
  /* motion */
  --ease:cubic-bezier(.2,.8,.25,1); --dur:.15s; --dur2:.28s;
}
```

- Adapter: plain CSS custom properties no bloco `<style>` de `web/index.html`.

## Slop audit

- Date: 2026-08-22 | Escopo: o sistema, ainda nao a implementacao.
- O maior risco de slop aqui **nao** e o generico de IA: e clonar o CMC sem pensar. A defesa e a
  lista de desvios declarados (tabular-nums, Inter unica, quatro correcoes de contraste,
  sparkline como fechamento de linha) - cada um com o motivo escrito.
- Tells que a direcao nova elimina de vez: vidro decorativo, aura radial, gradiente em botao,
  sombra difusa empilhada com borda, raio de 16px em elemento pequeno.
- Achado que vale registrar: **o design system do CoinMarketCap reprova WCAG AA em quatro tokens
  do tema escuro** (caption 2.87:1, negative 3.75:1, link no elevado 4.15:1, e negative sobre a
  propria tinta 3.55:1). No tema claro e pior - o verde deles da **2.20:1** sobre branco. Adotar
  a paleta literal seria regredir a acessibilidade que hoje passa em 100% dos nos de texto.

## Changelog

- 2026-08-22 (P2-34): gate de login plano. Sairam 52 regras de atmosfera do tema navy: malha
  tecnica mascarada em radial, varredura animada descendo a tela, entrada em cascata item por
  item, anel pulsante na marca, dois gradientes radiais de fundo, fio de luz no topo do card e a
  sombra de 90px. Ficaram **duas** animacoes, e as duas sao informacao: o ponto do indicador de
  saude ("o backend esta vivo") e o giro do botao enquanto verifica. O shake de senha errada
  tambem fica - e feedback transitorio de erro, nao movimento continuo.
  Nada do que custou uma madrugada saiu: as quatro mensagens distintas (401, 429, sem rede, sem
  `DASH_PASS`), o `/health` ao vivo antes de digitar, o Caps Lock, o olho de mostrar senha e o
  `minmax(0,1fr)` que impedia o card de vazar 34px em 390px.
- 2026-08-22 (P2-33): mapa de cor dos graficos aplicado. As bandas de Bollinger eram
  `rgba(148,161,189,...)`, um cinza que nao correspondia a token nenhum; viraram `--txt2`
  (#A1A7BB) a 50%, variacao de alpha declarada. Area da curva de capital ajustada de `.34` para
  o `.28` que este arquivo fixa. A altura de `#tvchart` deixou de ser numero fixo calibrado na
  topbar do M5 e passou a `calc(100vh - var(--sb-h) - 185px)`, usando a folga MEDIDA da status
  bar - com um numero fixo a vista Grafico nasce rolada assim que a barra quebra de linha.
- 2026-08-22 (P2-32): Sentimento e Funding ganharam a aba **Mercado**, o painel do bot ganhou a
  aba **Auto-trade**. O gauge de Fear & Greed mantem o gradiente vermelho-gold-verde: e o unico
  gradiente do sistema e esta la porque e **escala de medida** - diz o que cada ponta significa -
  e nao decoracao. Os dez `style` inline do `carregarSentimento()` viraram classes; o
  `rgba(10,16,32,.75)` do contorno da agulha (navy morto) virou `--bg`. Funding virou tabela de
  verdade; **nao ganhou sparkline**, e de proposito: o `/funding` devolve o instante, nao serie, e
  inventar curva a partir de um ponto seria desenho, nao dado.
  Nota de largura: `.tbl-met` e a tabela de funding tem `max-width`. "Largura cheia" e regra para
  a tabela larga, que e a protagonista; com duas ou quatro colunas, esticar ate 1392px so afasta
  o rotulo do valor.
- 2026-08-22 (P2-31): Posicoes, Journal, DCA e Metricas na tabela do sistema - largura cheia, sem
  card em volta, cabecalho grudado, numero a direita, hover de linha em `--surface`, sem zebra.
  Posicoes ganhou a coluna de evolucao do P&L. Metricas deixou de ser grade de tiles: os `.mstat`
  davam a 14 numeros de importancia muito diferente o mesmo peso visual, e viraram tabela de duas
  colunas. `#risco-guard` parou de renderizar banner e virou item da status bar (banca, risco do
  dia, exposicao); o banner sobrou so para os dois estados que travam operacao. Registrado acima
  o segundo caso de rolagem de tabela.
- 2026-08-22 (P2-30): a fila de sinais deixou de ser lista de cards e virou tabela com linha
  expansivel. Nota de cor: o sparkline da coluna Tendencia fica **azul**, como todo sparkline
  deste sistema, e nao verde/vermelho como o 7d do CMC. Com LONG e SHORT na mesma tabela, curva
  subindo em verde ao lado de um SHORT diria "bom" quando e "contra"; a leitura de dinheiro fica
  na coluna Delta, que tem o simbolo alem da cor. Novo desvio de tabela registrado acima
  (prioridade de coluna em vez de rolagem horizontal).
- 2026-08-22 (P2-29): cinco tiles planos no lugar do hero de vidro e dos tres stat cards. Risco do
  dia e Exposicao aberta sairam dos banners e viraram tile, com barra E o numero escrito ao lado -
  cor nunca e o unico sinal. `sparkline()` virou generico (serie + alvo) porque agora dois tiles a
  usam. `#npend` continua existindo e sendo escrito, mas mora no rotulo da aba Sinais: o quinto
  tile foi para risco/exposicao, e um contador de fila pertence a aba onde se age sobre ela.
- 2026-08-22 (P2-28): casca nova. Sai a sidebar de 232px, sai o bento de duas colunas, saem os
  banners de risco de largura cheia; entram topbar, tab bar de sete blocos e status bar fixa.
  Os dois botoes de vista continuam `class="tab"` + `data-v` porque `aba()` mira aquele seletor;
  as abas de conteudo usam `.subtab`/`data-sub`, classe diferente de proposito. A folga do rodape
  e **medida em JS**, nao fixa: a status bar quebra de linha em tela estreita e um valor chutado
  cobriria a ultima linha da tabela.
- 2026-08-22 (P2-27): tokens, tipografia e base implantados em `web/index.html`. O `:root` do tema
  navy saiu inteiro, junto com os aliases de transicao (`--card`, `--card2`, `--bg2`, `--mono`) e
  com Space Grotesk e JetBrains Mono. `.mono` sobrevive como classe - o JS escreve `class="mono"`
  em dezenas de lugares - mas deixou de ser familia e passou a significar so `tabular-nums`.
  Dois ajustes que a medicao obrigou: (1) o botao primario trocou texto escuro por **branco**,
  porque escuro sobre o `#3861FB` do CMC da 3.75:1 e reprovava (sobre o `#3b82f6` do tema navy
  dava 5.15:1); (2) as tintas de `.saida-*` eram rgba do verde/gold/vermelho mortos, e o vermelho
  velho a 16% dava 4.23:1 sob o `--neg` novo - viraram `--pos-bg`/`--warn-bg`/`--neg-bg`.
  Nomes de token do `TEMA` dos graficos renomeados junto, senao o objeto passaria a ler
  `undefined` e a vela ficaria sem cor entre este commit e o P2-33.
- 2026-08-22: **reescrito**. Direcao trocada de navy/glassmorphism para transposicao do
  CoinMarketCap tema escuro, por decisao do dono. Valores medidos do site deles, com quatro
  correcoes de contraste dentro da rampa. Sai sidebar/bento/hero-vidro, entra topbar + tab bar +
  fileira de tiles + tabela protagonista + status bar. Historico anterior no git.
- 2026-08-21 (2): P2-22 a P2-25 (direcao navy, obsoleta).
- 2026-08-21: criado no P2-20 (direcao navy, obsoleta).
