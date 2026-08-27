# [CX-3] Pré-registro — foi a TAXA ou foi o PREÇO de entrada?

> Escrito em **2026-08-27**, antes de qualquer backtest desta grade.
> A pergunta é do dono, e ela é boa o bastante para virar card.

## 1. A pergunta

O `[CX-1]` mediu que execução post-only leva Sharpe de 0,955 para ~1,25. Mas ela mudou **duas
coisas ao mesmo tempo**:

1. **o preço de entrada** — em vez de entrar no open, espera o preço vir até um nível melhor;
2. **a taxa** — 0,02% de maker em vez de 0,05% de taker, e sem slippage.

**Qual das duas produziu o ganho?** O card anterior não separa, e a diferença é prática:

- Se foi **o preço**, existe um caminho muito mais simples que post-only, e é a proposta do
  dono: *o bot fica olhando o preço e, quando bate o nível, manda a mercado*. Não depende de a
  corretora te tratar como maker, não tem ordem pendurada, não tem fila.
- Se foi **a taxa**, a proposta não captura nada, e post-only de verdade é obrigatório.

## 2. O modo novo: `entrada="gatilho"`

Enche **exatamente** como o post-only — mesma condição, mesmo `maker_off` — mas paga **taxa de
taker e slippage**, porque ordem a mercado consome a fila. É a proposta do dono, em código.

O desenho isola: `gatilho` tem o preço melhor e **não** tem a taxa menor.

| comparação | isola |
|---|---|
| `gatilho` × `taker` | o efeito do **preço de entrada** sozinho |
| `gatilho` × `maker` (mesmo offset) | o efeito da **taxa** sozinho |

## 3. A grade

5 níveis × 6 configs = 30 backtests. Mesma janela, mesma política, `lev_modo="conviccao"`,
grade de 6 configs **sem** dimensão de OI — a mesma do `[CX-1]`, para os números encaixarem.

Níveis: taker (baseline) · gatilho 0,05% · gatilho 0,10% · gatilho 0,20% · maker 0,10%
(referência dentro da própria rodada, para não depender de reprodução entre rodadas).

`n_trials = 1210`, o mesmo dos anteriores. **Quarta visita à mesma janela** — o viés declarado
no `[CX-2]` §3 continua valendo e continua sem conserto estatístico.

## 4. Prognóstico (antes dos números)

**Aposto que foi a TAXA, e que a proposta do dono NÃO captura o ganho.** Espero `gatilho` muito
mais perto do `taker` do que do `maker`.

**A razão é uma evidência que já está na mesa:** a curva do `[CX-1]` era **plana** — Sharpe
1,203 / 1,249 / 1,250 para concessões de 0,05%, 0,10% e 0,20%. Se o ganho viesse do preço de
entrada, pedir um preço **melhor** deveria ter ajudado **mais**, e a curva subiria com o offset.
Ela não subiu. O que ficou constante nos três níveis foi a taxa de maker — e é o constante que
explica um resultado constante.

**O que me faria estar errado:** o offset também perde trades, e perda de trade e preço melhor
podem estar se cancelando, produzindo uma curva plana por coincidência de duas forças opostas.
Se for isso, `gatilho` sobe junto e a proposta do dono funciona.

**Número que registro:** espero `gatilho` com Sharpe entre 0,95 e 1,10 — acima do taker por
causa do preço, mas longe dos ~1,25 do maker.

## 5. O que este card decide

Se eu estiver certo, o caminho para lucro passa por **post-only de verdade** na plataforma, e a
pergunta seguinte é se a Binance preenche. Se eu estiver errado, o caminho é **muito** mais
curto — basta o bot esperar o preço e mandar a mercado, que é código simples e sem dependência
de comportamento da corretora.
