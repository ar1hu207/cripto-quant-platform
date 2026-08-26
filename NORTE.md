# NORTE.md — para onde este projeto aponta

> **Leia este arquivo antes do `CLAUDE.md`.** O `CLAUDE.md` diz como se trabalha aqui; este diz
> **para quê**. Quando os dois divergirem, este manda, e o `CLAUDE.md` é que se conserta.
>
> Ele existe porque em 24-25/08/2026 uma sessão inteira operou contra o objetivo do dono sem
> perceber: os documentos diziam que o projeto não era pra dar dinheiro, a sessão acreditou, e
> mediu quatro vezes para confirmar um "não" enquanto o dono queria construir sinal novo.

---

## A direção, nas palavras do dono (2026-08-26)

> *"Operar posições sozinho com day trade, swing trade e gestão da carteira (de cripto por
> enquanto), e tornar essa ferramenta numa ferramenta poderosa pra análise de mercado:
> consolidar notícias, com momentum de mercado, análise fundamentalista mais pra frente,
> análise técnica, tudo isso. (…) Eu quero fazer essa ferramenta ganhar dinheiro, me ajudar a
> analisar criptoativos. É pra ser uma ferramenta lucrativa."*

E antes, sobre comportamento (25/08): entrar em **menos** trades mas nos **mais certos**;
**enxergar o cenário** (se o dia inteiro vai pra um lado, entrar em várias oportunidades); e
**não entrar em nada sem fundamento**.

## Os dois papéis — e nenhum dos dois é opcional

1. **Operar sozinho.** Day trade, swing trade e **gestão de carteira**, em cripto por enquanto.
2. **Analisar com ele.** Uma ferramenta que o dono abre para entender um criptoativo — notícia,
   momentum, posicionamento, técnica, e mais pra frente fundamento, consolidados no mesmo lugar
   e com o *porquê* à vista.

O segundo papel não é enfeite do primeiro: "me ajudar a analisar criptoativos" é pedido
explícito. Um painel que só lista sinal e posição atende metade da direção.

## Os cinco pilares e o estado real de cada um

| Pilar | Hoje | O que falta |
|---|---|---|
| **Análise técnica** | ✅ `indicadores.py` + `scoring.py`, confluência EMA/ADX/RSI/Donchian | nada estrutural — falta edge, e o `Q-15` diz onde procurar |
| **Day trade autônomo** | ✅ `signal_engine.py` + `autotrader.py`, ciclo de 15 s, guardas de risco | é o que existe de mais maduro |
| **Swing trade** | ❌ o motor é 1h intraday | regime 1d/4h, stop largo, alavancagem baixa (card `SW-1`) |
| **Gestão de carteira** | 🟡 risco por trade e teto de exposição existem (`simulador.guarda_risco`); `pesquisa/backtest_portfolio.py` mede carteira na régua | **a carteira não é objeto de decisão**: não há alocação alvo, rebalance, nem correlação entre posições. `motor_portfolio.py` está em `legado/`. O `dca.py` roda como anexo, não como parte da carteira |
| **Momentum de mercado** | 🟡 o **fluxo taker entra na decisão**: é portão de entrada (`signal_engine.py:87-98`, config `exigir_fluxo`) e sinal do gestor de saída (`:147-153`). Mas `funding_ranking()`, `sentimento()`, `fear_greed()`, `breadth()`, `smartmoney()` e `zonas_liquidez()` só são lidos pelo `api.py` — **display puro** | trazer o que já é coletado para dentro da decisão, com efeito **medido** e não achado. Barato: o coletor existe |
| **Notícias** | ❌ nada | card `N-1`: coleta, consolidação e efeito medido |
| **Fundamentalista** | ❌ nada | o dono disse "mais pra frente" — fica declarado, não esquecido |

## O que muda de enquadramento (e por que estava errado)

- **Paper trading é estágio, não identidade.** "Dinheiro fictício, sem chave de exchange" é
  descrição do estágio de hoje, e o destino é operar. Todo documento que apresenta o paper como
  *o que o projeto é* aponta pro lugar errado.
- **A pesquisa é meio, não fim.** A régua (`pesquisa/`) existe para que o lucro, quando vier,
  esteja atrás de evidência. Ela é **portão**, não produto.
- **`SEM EVIDÊNCIA DE EDGE` é o piso da busca, não a meta.** As medições são verdadeiras e caras
  — ficam onde estão, com os números intactos. O que muda é a frase em volta delas.

## O que NÃO muda — e não se rediscute

- **A régua fica.** É o que separa "ganhei R$600 em dois dias" de "tenho um sistema".
- **Não se ajusta parâmetro até o backtest ficar bonito.** É o jeito mais comum de perder
  dinheiro real. Fora disso — dado novo, mercado novo, estrutura nova, custo menor, entrada nova
  — tudo está na mesa.
- **Os invariantes de risco do `CLAUDE.md` §2.** Apertar guarda pode; afrouxar, só o dono.

## O número que orienta o próximo passo (`Q-15`, medido em 2026-08-26)

Mesma janela, mesma grade, mesma política. 5.424 trades OOS em 911 dias. **Só a taxa muda:**

| taxa/lado | PnL OOS | Sharpe anual | IC95% média/dia (bloco) | PSR | RC p | veredito |
|---|---|---|---|---|---|---|
| taker 0,05% (hoje) | +5.167 | 0,955 | (−2,13; 13,64) | 0,950 | 0,141 | sem evidência |
| maker 0,02% | +6.885 | 1,263 | (−0,36; 15,66) | 0,988 | 0,071 | sem evidência, por um fio |
| 0% | +8.031 | 1,466 | (0,78; 16,96) | 0,996 | **0,035** | **edge sobrevive** |

**O sinal não é vazio: ele está a ~0,03% por lado de passar nos três portões.** A taxa de hoje
come 36% do lucro bruto. O número de trades é idêntico nos três níveis — a taxa não filtra
entrada, só raspa o PnL depois.

**Ressalva que não vira ladainha, dita uma vez:** 0% não existe, e o nível maker aqui só trocou
o número da taxa — **não modelou não-preenchimento de ordem limite nem seleção adversa**. Que o
maker seja alcançável é medição nova, não conclusão deste teste.

## Como isso vira trabalho — PROPOSTA, pendente de decisão do dono

Marcos no formato do `PLANO-EXECUCAO-2026-08-20.md` §2: cada um é **uma frase que passa a ser
verdade e continua verdade**.

- **"O custo para de comer o edge"** — execução post-only/maker com fill medido, menos trades,
  taxa real da conta. É a alavanca mais barata que já apareceu e não depende de sinal novo.
- **"A carteira é o objeto, não o trade"** — alocação, exposição agregada, correlação, rebalance,
  DCA integrado, e o swing (`SW-1`) como regime paralelo ao day trade.
- **"O bot enxerga fora do candle"** — notícias (`N-1`) e posicionamento (`Q-17`). Primeiro passo
  dos dois **não é medir edge, é medir se dá pra medir**: a Binance serve ~30 dias de OI e
  long/short ratio, e com série curta a régua devolve INCONCLUSIVO por falta de poder, não por
  falta de sinal.
- **"Análise, não só sinal"** — a tela por criptoativo que consolida os pilares com o porquê à
  vista. É o segundo papel da ferramenta.

A ordem entre eles é decisão do dono e **ainda não foi tomada**. Não invente uma.
