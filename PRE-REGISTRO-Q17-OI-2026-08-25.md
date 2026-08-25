# [Q-17] Pré-registro — divergência open interest × preço

> **Escrito ANTES de qualquer número.** Base: `main` = `1d04857` + `2deef5d` (a Fase 1).
> Enquanto este documento era escrito, o único processo rodando era o **download** do
> histórico — baixar dado não é ver resultado. Nenhum backtest com open interest tinha sido
> executado quando as decisões abaixo foram fixadas.
>
> Autorização do dono para rodar: 2026-08-25, *"manda bala"*. A hipótese é a que o
> `PLANO-Q17-INFORMACAO-2026-08-25.md` §6/Fase 2 recomendou; o dono não expressou preferência
> diferente, então **a escolha é minha e fica registrada como minha**.

---

## 1. Por que este documento existe antes da rodada

O `n_trials` deste projeto é um **piso contado**, não uma estimativa (`[F10]`). Escolher a
hipótese *depois* de olhar o dado é uma tentativa que não entra na conta — e é exatamente o
data-snooping que a régua existe para punir. O protocolo é o mesmo que barrou o `[Q-8]`, o
`[Q-9]` e o `[Q-11]`:

1. a hipótese entra na **grade do treino**, nunca no rótulo da rodada;
2. **"sem filtro" entra na grade como hipótese nula** — se o open interest não ajudar, o treino
   escolhe operar sem ele, e isso é resposta;
3. a grade é **pequena e declarada ANTES**;
4. `n_trials` **cumulativo**.

Depois de publicado, trocar qualquer coisa aqui é uma tentativa nova e tem de ser contada.

---

## 2. A hipótese, em uma frase falseável

> **Preço subindo com open interest subindo é dinheiro NOVO entrando na direção do movimento;
> preço subindo com open interest CAINDO é posição sendo desmontada — short se cobrindo —, e
> esse movimento morre quando a cobertura acaba.**

O mesmo candle verde significa duas coisas opostas conforme o OI. O `scoring` de hoje não
consegue distinguir as duas: ele lê **preço e volume do próprio ativo**, e nada mais. O open
interest é a primeira informação do projeto que **não é derivada do candle**.

**A pergunta que a régua responde:** condicionar a entrada à concordância entre a direção do
sinal e a variação do open interest melhora a expectância, ou o OI não carrega informação além
da que o preço já dá?

### 2.1 A definição mecânica, sem margem de interpretação

Para a barra `i`, com a série de open interest alinhada pela regra da Fase 1
(`valor_da_barra(T) = dump[T − 15 min]`, sem look-ahead):

```
d_oi(i)   = sum_open_interest(i) − sum_open_interest(i−1)
concorda  = d_oi(i) > 0
```

> ### ⚠️ EMENDA — 2026-08-25, ANTES da rodada, com zero resultado visto
>
> **A versão original desta seção estava mecanicamente errada, e a correção está aqui em vez
> de reescrita em silêncio.** Eu havia escrito `concorda = (d_oi * direcao) > 0`.
>
> **Por que está errado.** O open interest sobe quando **posição nova é aberta**, e todo
> contrato tem um comprado e um vendido — logo o OI **não tem lado**. Quem tem lado é o
> preço, e a direção do preço já é a direção do sinal. Então:
>
> | preço | OI | o que é | o sinal está |
> |---|---|---|---|
> | sobe | sobe | longs novos | confirmado |
> | cai | sobe | shorts novos | confirmado |
> | sobe | cai | short se cobrindo | não confirmado |
> | cai | cai | long liquidando | não confirmado |
>
> Confirmação é `d_oi > 0` nos dois sentidos. A fórmula antiga, num SHORT, exigia OI
> **caindo** — exatamente o desmonte que a hipótese quer rejeitar. Ficaria invertida em
> metade dos trades.
>
> **Quem pegou, e quando.** `test_a_confirmacao_independe_da_direcao`, escrito para separar
> justamente as duas fórmulas pelo lado SHORT, que é onde elas discordam. Pegou **antes de a
> régua rodar**: nenhum resultado de edge tinha sido produzido, e nenhuma unidade de
> `n_trials` tinha sido gasta. É correção de definição, não escolha pós-fato.
>
> **O que isso NÃO autoriza.** A emenda é de mecânica, não de conveniência. Depois de a régua
> rodar, nenhuma linha deste documento se mexe — nem esta.

Nada de limiar, nada de janela, nada de suavização, e **nenhuma referência à direção**. Uma
diferença e um sinal. Três motivos:

- **lookback de uma barra** passa folgado no teto de paridade de 14 dias (§4 do plano) — o bot
  ao vivo consegue calcular isso com uma chamada ao REST;
- **zero parâmetro livre** significa zero superfície de sobreajuste dentro da própria feature;
  o único grau de liberdade é o modo, e ele está na grade;
- se a versão mais crua não mostrar nada, versões mais elaboradas (z-score, janela, limiar)
  são **tentativas adicionais** e teriam de ser contadas — não é para começar pela mais
  flexível.

**Barra sem open interest medido é `NaN`, e `NaN` não filtra nada.** A Fase 1 devolve `NaN` onde
o dump não alcança (o D+1 de hoje, e qualquer buraco). Nessas barras o portão **deixa passar**,
para que a ausência de dado não vire, sem querer, uma segunda estratégia — "não operar quando o
dado falta" é outra hipótese, não esta.

---

## 3. A grade, declarada aqui e travada

Quatro modos de `oi_modo`, e o primeiro é a **hipótese nula**:

| `oi_modo` | o que faz |
|---|---|
| `"off"` | **nula** — o open interest não é consultado. É a estratégia de hoje, sem mudança. |
| `"concorda"` | recusa o sinal quando `d_oi <= 0` (desmonte de posição) |
| `"concorda_tend"` | idem, mas só quando `adx >= adx_min` (em tendência); fora disso passa |
| `"peso"` | não recusa: soma `+10` de convicção quando concorda, `−10` quando discorda |

Cruzada com a grade padrão da régua (`min_conv ∈ {50, 55, 65}` × `adx_min ∈ {22, 25}`):

```
3 × 2 × 4 = 24 configs
```

**Nada além disso será varrido.** Não haverá varredura de limiar de `d_oi`, de janela, nem das
outras colunas do dump — as razões long/short **não reconciliam** com o caminho ao vivo (§4.2 do
plano) e por isso estão barradas de decidir, hoje, independentemente do que a régua disser.

### 3.1 `n_trials` cumulativo

O piso contado do projeto está em **820** (a rodada do `[Q-12]`, hoje,
`VEREDITO-M4-PRODUCAO-2026-08-25.md`). A parcela deste arquivo era `GRID × N_FOLDS = 30`; esta
rodada faz `24 × 5 = 120`.

```
820 − 30 + 120 = 910          →  N_TRIALS_OI = 910
```

Arredondo **para cima**, para **940**, absorvendo a rodada de baseline que roda junto. Piso
maior significa `SR0` maior, DSR menor, e portanto a direção que **desfavorece quem está
medindo** — o único lado em que este projeto aceita errar.

---

## 4. O que decide o veredito, e o que NÃO decide

O veredito sai do `walk_forward` sob o `PADRÃO` travado, como todas as rodadas do M4. Nada de
critério novo, nada de variante escolhida depois.

O baseline (`C trailing 2% fixo`, a política que roda ao vivo) é **re-medido na mesma janela**,
não citado do `VEREDITO-M4.md`: aquele número saiu de outra data, e comparar Sharpe de janelas
diferentes é comparar duas coisas com um fator a mais — o fator seria o dia.

**As três saídas possíveis, todas entrega:**

1. **Edge.** DSR acima do limiar com a grade escolhendo um `oi_modo` diferente de `"off"` na
   maioria dos folds. Aí o card avança para a Fase 4 do desenho — e ainda assim nada entra em
   produção antes de o dono assinar.
2. **Sem evidência de edge.** Caso 1 da §7.2 do `VEREDITO-M4.md`: **registrar o desvio, não
   trocar o default**. É o desfecho mais provável pelo histórico deste projeto, e continua sendo
   entrega.
3. **Inconclusivo.** Se o MDS estourar `MDS_LIMITE = 2,0` ou o `T_efetivo` cair — o que **não**
   se espera aqui, porque o T é o mesmo 1095 de sempre e o dado cobre a janela inteira.

**O que este pré-registro proíbe explicitamente:** ler o resultado e depois decidir que "na
verdade a hipótese era com limiar de 2%", ou "era só nas alts", ou "era só em tendência forte".
Qualquer uma dessas é uma rodada nova, com `n_trials` maior, e tem de ser declarada antes.

---

## 5. Prognóstico registrado antes do número

Escrito para que a rodada possa me contrariar, e para que eu não possa dizer depois que já
sabia.

**Espero `SEM EVIDÊNCIA DE EDGE`**, e a `"off"` vencendo na maioria dos folds. Razões:

- as quatro políticas de saída já saíram sem edge sobre este mesmo universo (`VEREDITO-M4.md`);
- o open interest agregado da exchange é público e olhado por todo mundo — informação que todos
  têm tende a já estar no preço;
- a divergência OI×preço é folclore de mesa antes de ser resultado publicado, e este projeto já
  reprovou três folclores seguidos (`Q-8`, `Q-9`, `Q-11`).

**O que me faria mudar de ideia:** `"concorda_tend"` vencendo consistentemente com DSR acima do
baseline re-medido. Seria coerente com o mecanismo — a distinção entre dinheiro novo e cobertura
de short só deveria importar quando existe tendência para sustentar.

**E o resultado que eu trataria com mais desconfiança que qualquer outro:** o `"peso"` ganhando
por pouco. Ele mexe na convicção, e a convicção **ainda não foi verificada** — o `[Q-13]` é
justamente "a convicção prevê acerto?", e está aberto. Ganho via `"peso"` seria ganho apoiado
num pressuposto não testado, e eu o reportaria como tal em vez de como achado.
