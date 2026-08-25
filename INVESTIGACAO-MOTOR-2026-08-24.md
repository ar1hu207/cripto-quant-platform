# Investigação do motor — 2026-08-24

**Origem:** o dono olhou o resultado do dia (−88,39, trava diária acionada) e pediu uma análise
do motor. **Fonte dos números:** `trading.db` da VM de produção (`az vm run-command`, prod em
`90ef52c`), 47 trades fechados entre 2026-08-19 23:58 e 2026-08-24 04:42. Nada aqui vem do
`trading.db` local, que está vazio (`CLAUDE.md` §0).

**O que este documento NÃO é.** Não é uma proposta de melhorar o resultado. O walk-forward +
DSR já concluiu que não existe edge deployável, e o `VEREDITO-M4.md` estendeu a conclusão à
política que roda ao vivo (`C trailing`: 5.342 trades OOS, Sharpe 0,645, DSR 0,060, *sem
evidência de edge*). O que se procurou aqui foi **defeito de construção** — erro de unidade ou
de aritmética que erra sempre para o mesmo lado, e cuja existência independe de haver edge.
Achou-se quatro. O primeiro é grave.

---

## 0. O quadro, antes de qualquer diagnóstico

| dia | n | P&L | wins | taxa |
|---|---:|---:|---:|---:|
| 19/08 | 1 | −2,89 | 0 | 0,97 |
| 20/08 | 15 | +78,85 | 7 | 22,74 |
| 21/08 | 14 | +374,86 | 8 | 18,34 |
| 22/08 | 6 | +34,68 | 4 | 6,93 |
| 23/08 | 6 | −87,57 | 2 | 9,89 |
| 24/08 | 5 | −88,39 | 0 | 6,17 |

Banca 1000 → **1309,54**. Ganho médio **+40,45**, perda média **−20,77**, acerto 44,7%,
profit factor 1,57. **A assimetria pedida ao trailing existe**: erra mais vezes do que acerta e
mesmo assim fecha positivo, porque os acertos são o dobro dos erros.

Isto precisa ficar escrito porque contradiz a leitura que motivou a investigação: o motor
**não** está "perdendo muito e ganhando pouco". Com n=47 em 5 dias, nem o +374 do dia 21 nem o
−88 de hoje sustentam conclusão — ambos são ruído. O defeito abaixo não foi encontrado olhando
o P&L; foi encontrado olhando a geometria, e o P&L só serviu para confirmá-lo.

---

## 1. GRAVE — o trailing e o stop estão em unidades diferentes, e há uma faixa onde vencer é impossível

### A causa

- Stop: `stop_dist = 3 * atr / c` (`scoring.py:53`) — **relativo à volatilidade do ativo**.
- Trailing: `trailing_dist = 0.02`, aplicado como `preco * (1 - trail_d)`
  (`simulador.py:326-334`) — **porcentagem seca do preço**.

Duas grandezas que precisam conversar, medidas em réguas diferentes. A razão trailing/stop não
é uma escolha do sistema: ela cai onde cair, e varia ~50× entre os ativos da carteira.

### A consequência, deduzida antes de olhar o resultado

O trailing arma quando o preço anda `+trail_d` e, no mesmo instante, põe o stop em
`preço × (1 − trail_d)` — isto é, **de volta na entrada**. Para travar lucro algum, o preço
precisa passar de `2 × trail_d`. Em unidades de stop (R), o gatilho de lucro fica em:

```
R_necessário = 2 · trail_d / sd          (sd = distância relativa entrada→stop)
```

| ativo/tf observado | sd | R necessário para o trailing lucrar |
|---|---:|---:|
| TRX 5m | 0,19% | **21,0 R** |
| faixa média | 1,5% | **2,7 R** |
| BCH | 8,8% | **0,45 R** |

Quando `sd ≈ trail_d`, o trade tem exatamente dois desfechos: bate o stop (−1R) ou o trailing
arrasta até a entrada (~0R). **O ramo vencedor não existe.** Não é probabilidade baixa — é
ausência de ramo.

### A confirmação em produção

47 trades, agrupados pela distância do stop. `trail_d = 2%`:

| faixa de sd | n | wins | P&L | saídas por *trailing* | R médio |
|---|---:|---:|---:|---:|---:|
| A `<0,5%` | 8 | 3 | +3,80 | 3 | −5,36 |
| B `0,5–1%` | 8 | 4 | −1,60 | 3 | −0,16 |
| **C `1–2%`** | **11** | **0** | **−242,08** | **0** | **−1,07** |
| D `2–4%` | 10 | 7 | +160,00 | 5 | +0,47 |
| E `>4%` | 10 | 7 | +389,42 | 6 | +0,48 |

A faixa C é a previsão da fórmula, sem exceção: **11 trades, zero vitórias, zero saídas por
trailing, R médio −1,07** (= o stop cheio). Os −242 dela são 78% de tudo que o motor ganhou no
período. Na faixa E, onde `trail_d` cabe folgado dentro do stop, o trailing funciona como
desenhado: 6 saídas por trailing, R médio +0,98.

### O que corrigir

Expressar o trailing na **mesma unidade do stop** (múltiplo de ATR), para que a razão
trailing/stop seja constante entre ativos em vez de acidental. Isto não escolhe um resultado —
escolhe uma unidade.

---

## 2. A taxa consome o risco, e a proporção é uma identidade

Custo do round-trip = `2 · taxa_lado · valor · lev`. Risco até o stop = `valor · lev · sd`.
Logo:

```
taxa / risco = 2 · taxa_lado / sd = 0,001 / sd
```

**Não depende de tamanho, nem de alavancagem, nem de edge.** Só do stop. Conferido contra
produção — trade #46 (TRX): `sd = 0,189%` → previsto 0,529; medido `0,989 / 1,87 = 0,529`.

| sd | fração do risco que vira taxa |
|---:|---:|
| 4% | 2,5% |
| 2% | 5% |
| 1% | 10% |
| 0,19% | **53%** |
| 0,005% (trade #21, ETC) | **2000%** |

**16 dos 47 trades (34%) têm `sd < 1%`.** Existe guarda para stop *longe demais*
(`_liq_antes_do_stop`, P1-12, que recusa geometria em que a liquidação vem antes do stop).
Não existe guarda para stop *perto demais* — e é o mesmo tipo de degeneração, com o sinal
trocado.

O piso a adotar sai de uma declaração de custo, **não do P&L**: "não abro trade cujo
round-trip custe mais que X% do risco" ⇒ `sd_min = 0,001 / X`. Com X = 5%, `sd_min = 2%`.
O número tem de ser escolhido pelo custo aceito e depois submetido à régua — nunca escolhido
por maximizar o resultado desta amostra.

---

## 3. O cap `auto_max_valor_frac` desliga o alvo de risco em silêncio

`_tamanho` (`autotrader.py`) calcula `valor = risco_rs / (lev · sd)` e depois aplica
`min(valor, banca · max_frac)`. Quando o stop é apertado, `valor` explode e o cap **sempre**
morde — e o risco realizado despenca junto:

```
risco_inicial observado em produção:  0,14  …  83,16 R$
config declarada:                     risco_por_trade = 3%  ≈  39 R$
```

Variação de ~600× no risco por trade, num sistema que declara risco fixo. Quando o cap morde,
o trade fica com nocional grande e risco ~zero: **só taxa**. E não há log dizendo que mordeu —
o `[P2-8]` fez o piso `min_valor` filtrar em vez de inflar, mas o teto do outro lado segue mudo.

**Contaminação da medição:** `expectancia_r` e `sqn_r` (`db.py`) dividem P&L por
`risco_inicial`. Com `risco_inicial = 0,14`, o trade #21 vale **R = −17,33** sozinho e domina
média e desvio da amostra inteira:

| corte | n | R médio |
|---|---:|---:|
| todos | 47 | −0,415 |
| `sd ≥ 1%` | 31 | −0,038 |
| `sd ≥ 2%` | 20 | +0,479 |

A métrica não está errada na fórmula — está instável porque a **unidade de risco** que ela usa
como denominador é degenerada na origem. Corrigir a causa (§1 e §2) estabiliza a métrica sem
tocar em `db.py`. Winsorizar o R seria a versão-sintoma: esconderia exatamente o trade que
denuncia o defeito.

---

## 4. `ret_pct` é bruto, `pnl_reais` é líquido

`fechar()` grava `ret_pct = move * alavancagem * 100` (`simulador.py`) — **sem taxa e sem
funding** — enquanto `pnl_reais`, na mesma linha, tem os dois. Quem lê `ret_pct` lê um retorno
que ninguém recebeu, e o erro é sempre para o lado bom. É a mesma doença que o `[P2-18]` curou
no preço de fill (gatilho ≠ execução), sobrevivendo numa outra coluna.

---

## 5. Observado, mas deliberadamente NÃO virou conserto

Três padrões apareceram e **não** entram como correção, porque agir sobre eles seria escolher
regra olhando o resultado desta amostra — que é sobreajuste, não conserto:

- **SHORT: 14 trades, 2 vitórias, −206.** LONG: 33 trades, +515. Com n=14, e numa janela de
  cripto subindo, isto não sustenta nada.
- **O 5m gera 66% dos trades e entrega 5% do resultado** (+15,52, contra +190,07 do 15m e
  +103,95 do 1h), com `sd` médio 1,82% contra ~3,7% dos outros dois — é dele que vem quase toda
  a faixa doente. Desligar o 5m por causa deste número seria seleção pós-fato. O caminho é
  passar a geometria corrigida pela régua e deixar o 5m cair (ou não) por mérito.
- **Sem controle de correlação.** Hoje, três SHORTs simultâneos em alts correlacionados
  (DOT #43, OP #44, INJ #45) foram dimensionados como três apostas independentes.
  `risco_aberto_max` soma risco, não correlação: é uma aposta contada três vezes.

Funil de sinais no período, para dimensionar o desperdício: **1.616 sinais → 47 confirmados**
(868 expirados, 443 rejeitados por fluxo, 255 pulados). Só o 5m responde por 607 expirados.

---

## 6. O que se espera do conserto — e o que NÃO se espera

**Espera-se:** que a faixa C deixe de ser um desfecho de duas pontas ruins e volte a ter ramo
vencedor; que trades cujo round-trip custa metade do risco não sejam abertos; que
`expectancia_r` e `sqn_r` parem de ser dominados por um denominador degenerado.

**Não se espera lucro.** Remover uma perda estrutural não cria edge — são coisas diferentes.
A régua já respondeu "sem evidência de edge" para a política que roda hoje, e a hipótese de
trabalho é que a versão corrigida saia igual, só que mais limpa e com menos sangria de taxa.
O ganho real do conserto é **epistêmico**: hoje 57% dos trades passam por uma saída quebrada,
então o experimento não está medindo a estratégia — está medindo a estratégia mais um defeito.

**Portão:** nada disto vai a produção sem passar por `python -m pesquisa.validacao`
(walk-forward + DSR) e sem assinatura do dono — a mudança é `toca-risco` (`CLAUDE.md` §2:
apertar guarda pode; afrouxar, só o dono).

---

## 7. A régua respondeu — e a resposta não autoriza trocar o default

Rodado em 2026-08-24, 94,9 min, saída completa em `VARREDURA-GEOMETRIA-2026-08-24.log`:

```bash
python -m pesquisa.validacao geometria
```

Grade: `min_conv`(3) × `adx_min`(2) × `k`∈{1, 2, 3, 4} × `sd_min`∈{0%, 1%, 2%, 4%} = **96
configs**, 12 moedas, 1.095 dias de 1h. `n_trials = 550`. O baseline foi **re-medido na mesma
janela**, não citado do `VEREDITO-M4.md`.

| | baseline `C trailing 2% fixo` | varredura `k×ATR + piso sd` |
|---|---:|---:|
| configs na grade | 6 | 96 |
| `n_trials` declarado | 100 | 550 |
| trades OOS | 5.342 | 2.780 |
| win% | 61,2 | 47,6 |
| P&L OOS | +5.040 | +3.426 |
| **Sharpe anualizado** | **0,645** | **0,412** |
| IC95% do Sharpe | (−0,714 ; 1,824) | (−1,016 ; 1,649) |
| PSR | 0,854 | 0,748 |
| DSR (melhor IS) | 0,0625 | 0,0065 |
| Reality Check p | 0,2014 | 0,4148 |
| SPA p | 0,2309 | 0,5037 |
| calibração [Q-7] | 12/200 (0,06) CALIBRADO | 8/200 (0,04) CALIBRADO |
| concentração: maior fold | 0,56 do total | **1,03 do total** |
| **veredito** | **SEM EVIDÊNCIA DE EDGE** | **SEM EVIDÊNCIA DE EDGE** |

**Controle de reprodutibilidade:** o baseline re-medido hoje bateu com o do `VEREDITO-M4.md`
(5.342 trades, win 61,2%, P&L +5.040, Sharpe 0,645, IC idêntico) — a janela andou um dia e o
resultado não andou. O instrumento está estável; a comparação abaixo é entre políticas, não
entre rodadas.

### 7.1 O que o TREINO escolheu, que é a pergunta que a §7.3 do M4 fez

| fold | config escolhida | P&L OOS |
|---:|---|---:|
| 1 | (65, 25, **k=4,0**, **sd_min=0%**) | +1.172 |
| 2 | (65, 25, **k=4,0**, **sd_min=0%**) | +1.303 |
| 3 | (65, 22, k=1,0, sd_min=4%) | −1.006 |
| 4 | (55, 22, **k=4,0**, **sd_min=0%**) | +3.512 |
| 5 | (50, 22, **k=4,0**, **sd_min=0%**) | −1.554 |

Duas respostas, e nenhuma é a que o card esperava:

**(a) O piso de custo não foi escolhido.** `sd_min = 0%` em 4 dos 5 folds. Dado o direito de
usar o piso do `[Q-9]`, o treino recusou. A hipótese nula que a grade carregava de propósito
**sobreviveu** — e isso vale como resposta, não como falha da rodada. Leitura provável: com
`min_conv` alto (65 nos folds 1-2) o portão de convicção já elimina a maior parte dos sinais de
stop curto, e o piso separado passa a cobrar oportunidade sem entregar o que já foi entregue.
`sd_min` e `min_conv` estão medindo coisa parecida.

**(b) `k = 4,0` é o TETO da grade, escolhido em 4 dos 5 folds.** Isto é um *boundary hit*: o
ótimo pode estar fora da grade, e **a rodada não resolveu a pergunta do `k`** — só a moveu.
Reportar "o treino escolheu k=4" sem dizer que 4 era o máximo disponível seria dizer que a
grade respondeu quando ela bateu na parede.

E a direção do boundary hit é o achado que menos se esperava: `k` maior = trailing mais
**largo** = trailing que interfere menos, no limite deixando o stop de entrada correr sozinho.
**O treino, com a escolha livre, está fugindo do trailing.** O limite dessa direção é a
política **A** do M4 (stop sem trailing), que já foi medida: Sharpe **0,124**, DSR 0,0099 — pior
que as duas desta tabela. A comparação não é limpa (A também fecha por flip de regime, C não),
então isto é indício, não prova. Mas indica que a direção que o treino persegue já foi
explorada no extremo e não tem nada lá: a superfície é plana e ruidosa, não uma encosta.

### 7.2 Por que o placar pior NÃO derruba o argumento de unidade

A varredura pontuou abaixo do baseline em tudo. Ler isso como "o 2% fixo é melhor" seria errado
por três razões, e as três já estavam escritas antes dos números:

1. **A maior parte do gap do DSR é o preço declarado da grade maior.** `n_trials` foi de 100
   para 550 porque a busca cresceu 16×. Na tabela de sensibilidade que o próprio relatório
   imprime, a varredura a `n_trials=100` daria DSR **0,0276** em vez de 0,0065. O DSR não caiu
   só porque a política é pior — caiu porque a rodada pagou por ter procurado mais.
2. **Os IC95% de Sharpe se sobrepõem quase inteiros** — (−1,016 ; 1,649) contra
   (−0,714 ; 1,824). A ordenação **não é uma diferença demonstrada**. É a mesma ressalva da §7.3
   do M4, e ela vale igual quando o resultado desagrada.
3. **O argumento da §7.3 nunca foi de performance.** `trailing_dist=2%` mede coisa diferente em
   cada ativo e em cada alavancagem, e isso é verdade sob qualquer placar. O que a rodada
   entrega é que **trocar por `k×ATR` também não compra performance** — some-se ao fato de que
   ela não custa nada, e a troca vira decisão de higiene, não de retorno.

### 7.3 O que esta rodada autoriza, e o que não

**Não autoriza trocar o default.** Duas políticas `SEM_EVIDÊNCIA`, IC sobrepostos, e a
concentração da varredura piorou de forma material: **um único fold responde por 1,03 do lucro
total** (o fold 4, +3.512 contra +3.426 do agregado), contra 0,56 no baseline. Um resultado que
mora inteiro numa dobra não é base para mexer no que roda com dinheiro — nem fictício.

**Não autoriza o piso do `[Q-9]` como está.** O treino recusou. O card não morre — o que morre é
a versão dele que fixa `sd_min` por decreto. Se o piso voltar, volta como o que a §2 deste
documento diz que ele é: uma declaração de custo do dono, aplicada **sabendo** que o
walk-forward não a escolheu sozinha.

**O que fica de pé, e é o produto desta rodada:**

- O pré-requisito que a §7.3 do `VEREDITO-M4` deixou nomeado — *"um `k` varrido no grid é
  pré-requisito de qualquer proposta de troca"* — **foi rodado**, e devolveu boundary hit. A
  próxima grade de `k` tem de subir o teto, e a §7.1 diz para onde ela aponta.
- A faixa doente da §1 é real e continua real: ela é aritmética de produção, não estatística de
  backtest. O que a régua diz é que **consertá-la não paga em Sharpe** — que é exatamente o que
  a §6 previu antes de medir.
- Os defeitos §3 (o cap mudo) e §4 (`ret_pct` bruto) **não dependem desta rodada** e seguem
  válidos: nenhum dos dois é sobre performance.

---

## 8. A pergunta do dono que mudou o rumo: "ele acerta, mas não sabe quando tirar"

Observação do dono, depois da §7: *"o bot acerta a maioria dos trades, mas não sabe quando
tirar — o que era um lucro bom acaba se perdendo."* Testável, e testada: MFE (*Maximum
Favorable Excursion*) dos 47 trades, com os candles de **1 minuto** da janela em que cada
posição ficou aberta.

### 8.1 A percepção estava certa, e a §0 também

| | |
|---|---:|
| trades que **em algum momento** estiveram no lucro (líq. de taxa) | **41 / 47 = 87,2%** |
| trades que **fecharam** no lucro | 21 / 47 = 44,7% |

As duas leituras são verdadeiras e medem coisas diferentes. O motor **entra bem** em quase 9 de
cada 10 trades; ele não fica com o dinheiro. Isso reconcilia a §0 (que dizia "a assimetria
existe") com a percepção de quem olha o painel.

**20 trades foram de lucro a prejuízo:** estavam **+R$230** somados e fecharam **−R$399**.

⚠️ **A soma dos picos (R$1.550) NÃO é um alvo.** Sair no topo de todo trade é retrovisor —
nenhuma regra alcança. Registrar "perdemos R$1.240" seria construir uma referência impossível e
depois cobrar o sistema por não alcançá-la. O número que decide é o dos 20 que viraram: ali não
se trata de pegar o topo, e sim de não devolver ganho que já existia.

### 8.2 A causa — e ela é o espelho exato da §1

**19 dos 20 nunca tiveram o trailing armado.** Ele só arma em `+trailing_dist` de **PREÇO**
(2%); abaixo disso a proteção é **zero** e o stop segue 3×ATR abaixo da entrada. Como o lucro
que o operador vê é **ROE** (= preço × alavancagem), o limiar em preço vira um limiar em ROE que
**escala com a alavancagem**:

| lev | ROE totalmente desprotegido |
|---:|---:|
| 3x | 6% |
| 10x | 20% |
| 14x | 28% |
| 20x | **40%** |

```
#38 NEAR  14x  pico +23,56% ROE = só 1,68% de preço (faltou 0,32pp) -> fechou -27,59%  -R$47,04
#39 UNI   15x  pico +21,27% ROE = só 1,42% de preço (faltou 0,58pp) -> fechou -30,20%  -R$47,00
#40 FIL   11x  pico +17,24% ROE = só 1,57% de preço (faltou 0,43pp) -> fechou -21,29%  -R$14,80
#28 APT   15x  pico  +6,94% ROE = só 0,46% de preço                 -> fechou -57,87%  -R$40,52
```

O efeito é perverso na direção que mais dói: **convicção alta ⇒ alavancagem alta ⇒ mais ROE sem
proteção.** O sistema desprotege exatamente os trades em que mais confia. É o espelho do
`alvo_roe=5` que a §7.3 do `VEREDITO-M4.md` já apontou (fixo em ROE, a 20x dispara com 0,25% de
preço = ruído): **um knob cego à alavancagem para cada lado, nenhum dos dois escolhido — os dois
herdados.**

---

## 9. A régua vinha medindo um sistema que não é o que roda

Rodado em 2026-08-24; saídas literais em `MEDICAO-ZERO-A-ZERO-2026-08-24.md`.

O card `[Q-11]` propôs a guarda `be_em_R` (zero-a-zero disparado em múltiplo de R, e não em
preço nem em ROE — mesma correção de unidade da §1 aplicada ao outro parâmetro). Medi-la exigiu
o `[Q-10]` antes: **a régua roda `LEV` fixo em 10x e a produção roda 2x–20x por convicção**, e o
defeito que a guarda ataca *é* a interação entre alavancagem e limiar. A 10x fixo o limiar é 20%
de ROE para todo mundo, uniforme, e a patologia some — **nenhuma rodada anterior poderia
tê-la encontrado.**

### 9.1 A guarda não passou, e o diagnóstico por braço diz por quê

```
be_em_R   trades      PnL    vezes que o zero-a-zero ARMOU
None      33989    +24045              0
0.5       36841    +21284           5737     <- age muito, resultado PIOR
1.0       34313    +23518            725
1.5       34033    +24331            138     <- quase não arma
```

**Quanto mais a guarda age, pior o resultado.** O braço que "venceu" (1,5R) armou 138 vezes em
34.033 trades — 0,4%: venceu por ser quase indistinguível de não existir. E é **teto da grade**,
mais um *boundary hit*, na mesma direção de sempre — o treino quer a guarda agindo o mínimo. No
fold 1 ele escolheu `None`, sem guarda nenhuma.

A ressalva escrita no card **antes** de medir (*"proteger cedo também mata trade que mergulha e
volta"*) era o risco real, e ela se confirmou: as mesmas oscilações que viram prejuízo são as que
viram lucro grande. O `be_em_R=None` estava na grade como hipótese nula e **sobreviveu de novo**
— terceira vez no dia, depois do `sd_min` e do `k`.

### 9.2 O contraste de atribuição, e o que ele revelou

A rodada da grade mudou **dois** fatores ao mesmo tempo (guarda + alavancagem), então ela não
atribui nada. O contraste isola: braço `be_em_R=None` sozinho, mesmas 6 configs de entrada do
baseline da §7, mesma política, mesma janela — **único fator diferente: `lev_modo`.**

| | Sharpe | IC95% | PSR | RC p | folds + | maior fold |
|---|---:|---:|---:|---:|---:|---:|
| lev **fixo 10x** (baseline §7) | 0,645 | (−0,714 ; 1,824) | 0,854 | 0,2014 | 3/5 | 0,56 |
| lev **convicção**, sem guarda | **0,976** | (−0,353 ; 2,074) | **0,954** | 0,1404 | **4/5** | **0,41** |
| lev convicção + grade de guarda | 0,985 | (−0,345 ; 2,081) | 0,9557 | 0,1434 | 4/5 | 0,41 |

**A alavancagem responde por +0,331 de Sharpe. O zero-a-zero, por +0,009.**

E o ponto que reorganiza tudo: **2x–20x por convicção é o que a produção JÁ RODA**
(`auto_lev_modo=conviccao`, `auto_lev_min=2`, `auto_lev_max=20`, na config do banco). Ou seja, os
vereditos anteriores — inclusive o `SEM EVIDÊNCIA DE EDGE` do `VEREDITO-M4.md` sobre a política
`C trailing`, que é o **produto declarado deste projeto** — foram emitidos sobre uma
configuração que ninguém executa.

### 9.3 O que isso NÃO é

**Não é edge encontrado.** Medido no objeto certo, o veredito é o mesmo:

```
=> VEREDITO: SEM EVIDENCIA DE EDGE
   IC95% do Sharpe anualizado: [-0,353 ; 2,074]   <- ainda inclui o zero
   Reality Check p = 0,1404                        <- longe de 0,05
```

O portão é **conjunção** (IC sem o zero **e** PSR > 0,95 **e** RC p < 0,05). Passou um dos três.
A conclusão do projeto **não muda** — o que muda é que a margem encolheu e agora está medida
sobre o que de fato executa.

**E não é um efeito de tamanho.** `pnl = valor · lev · (move − 2·taxa)` é *exatamente*
proporcional à alavancagem: escalar tudo por um fator constante não move o Sharpe em nada. O que
move é a **variação** — em particular o cap geométrico do `[P1-11]`, que corta a alavancagem
quando o stop é largo. Na prática isso é **dimensionamento por volatilidade**: posição menor no
setup mais volátil. É efeito de gestão de risco, não de previsão — e é a única explicação
compatível com a álgebra acima.

### 9.4 O que fica

- **Card novo, e é o mais importante do dia:** re-emitir o veredito do M4 sobre a configuração
  de produção. Não para buscar um número melhor — para que o `SEM EVIDÊNCIA` do projeto passe a
  descrever o sistema que existe. Enquanto isso não for feito, o `VEREDITO-M4.md` e o
  `README.md` afirmam algo verdadeiro sobre um objeto que não é o nosso.
- **`[Q-11]` fecha como medido e reprovado**, com o mecanismo registrado. A ideia não era ruim —
  ela é derrubada por um fato que só o dado tem.
- **`[Q-10]` fecha como aceito**: foi ele que tornou visível a diferença entre régua e produção.
- A §8.2 (limiar cego à alavancagem) **segue de pé como defeito**, mesmo com a guarda reprovada:
  é incoerência de unidade, não proposta de performance — igual à §1.

---

## 10. `[Q-12]` — o veredito re-emitido sobre a configuração que a produção executa

Rodado em **2026-08-25**, 8,6 min. Saída literal em `VEREDITO-M4-PRODUCAO-2026-08-25.md`.

```bash
python -m pesquisa.validacao politicas-prod
```

As **mesmas quatro políticas** do `POLITICAS_M4`, na mesma régua, nas mesmas janelas e sobre os
mesmos painéis. Único fator alterado: `lev_modo="conviccao"`. `n_trials = 820`.

| política | trades | win% | P&L OOS | Sharpe an. | IC95% Sharpe | DSR | veredito |
|---|---:|---:|---:|---:|---:|---:|---|
| A stop+flip de regime | 2.158 | 28,2 | +902 | 0,176 | (−1,446 ; 1,446) | 0,0012 | SEM_EVIDÊNCIA |
| B auto-saída | 5.925 | 61,4 | −2.454 | −0,408 | (−1,894 ; 0,786) | 0,0001 | SEM_EVIDÊNCIA |
| **C trailing 2% fixo** | 5.434 | 61,6 | **+5.285** | **0,976** | (−0,353 ; 2,074) | 0,0253 | SEM_EVIDÊNCIA |
| C trailing 3×ATR | 3.933 | 50,2 | +4.897 | 0,825 | (−0,634 ; 2,066) | 0,0261 | SEM_EVIDÊNCIA |

### 10.1 O que muda em relação ao `VEREDITO-M4.md`

Contra a tabela original (mesma régua, `LEV` fixo em 10x):

| política | Sharpe a 10x fixo | Sharpe em produção | Δ |
|---|---:|---:|---:|
| A stop+flip | 0,124 | 0,176 | +0,05 |
| B auto-saída | −1,018 | −0,408 | **+0,61** |
| C trailing 2% | 0,645 | 0,976 | **+0,33** |
| C trailing 3×ATR | 0,436 | 0,825 | **+0,39** |

**As quatro melhoraram.** Isso é o achado desta seção, e é mais forte do que o de qualquer
política isolada: o ganho **não é** de uma saída específica — é sistemático, e portanto vem do
**dimensionamento**, não da gestão da posição. É a leitura da §9.3 confirmada num quarto ponto
independente.

**A ordenação entre as políticas não muda:** C 2% > C 3×ATR > A > B, igual ao M4. O
`VEREDITO-M4.md` está **certo no que ordena** e estava medindo o objeto errado no que quantifica.

**O DSR do `C trailing 2%` caiu (0,0602 → 0,0253) e isso não é piora:** o `n_trials` foi de 100
para 820 (piso contado cumulativo do dia). A tabela de sensibilidade que o relatório imprime
recupera o número a qualquer `n_trials` — a comparação com o M4 continua possível, ela só deixou
de ser o default.

### 10.2 O que NÃO muda, e é o que importa

**As quatro continuam `SEM EVIDÊNCIA DE EDGE`.** Nenhum IC de Sharpe exclui o zero; o portão de
conjunção não é vencido por nenhuma. **A conclusão central do projeto sobrevive à correção do
objeto** — e agora ela descreve o sistema que existe, que era o ponto do card.

Um detalhe que vale registrar: a política que **roda ao vivo** (`C trailing 2% fixo`) é a melhor
das quatro sob a configuração de produção. Isso não a valida — `SEM_EVIDÊNCIA` é `SEM_EVIDÊNCIA`
—, mas responde uma pergunta que estava aberta desde o `ITEM1` §8: o default vivo não é pior que
as alternativas medidas. Ele é o topo de um conjunto que inteiro não demonstrou edge.

**Controle de reprodutibilidade:** o `C trailing 2% [prod]` desta rodada bateu linha a linha com
o contraste de atribuição de 24/08 (5.434 trades, win 61,6%, +5.285, Sharpe 0,976, IC idêntico),
rodado por outro caminho de código. Terceira reprodução limpa do dia.

### 10.3 Por que as três hipóteses de conserto não passaram — a leitura conjunta

O `[Q-8]` (trailing em `k×ATR`), o `[Q-9]` (piso de custo) e o `[Q-11]` (zero-a-zero) foram
medidos e nenhum passou. As três falharam nas **mesmas duas** condições do portão (IC incluindo
o zero, Reality Check ≫ 0,05), e cada uma pelo seu caminho: o piso o treino **não escolheu**; o
`k` foi ao **teto da grade**; o zero-a-zero **piora quanto mais age**.

O fio comum: **as três mexem no que acontece DEPOIS da entrada.** Nenhuma altera se a entrada
prevê direção. Uma regra de saída redistribui o formato da distribuição de resultados — troca
muitos ganhos pequenos por poucos grandes, ou o contrário — mas não move o **centro** dela, a
menos que exista estrutura explorável no caminho do preço. E toda regra que age, **custa**: cada
acionamento é um round-trip a mais ou um trade cortado antes de mostrar o que era. Daí as três
convergirem, independentemente, na mesma resposta: *aja o menos possível*.

A §10.1 fecha o argumento pelo outro lado: **o único fator que moveu o número em todas as
quatro políticas foi o tamanho da aposta, não a saída.**

**E o contrapeso, que não pode ser omitido:** `MDS = 1,575`. Com 80% de poder a régua só detecta
Sharpe ≥ ~1,6, e os IC vão até 1,4–2,1. Um edge real de Sharpe 1,0 seria **invisível** para este
instrumento. "Não passou" é *não se provou*, nunca *provou-se inútil* — é o que a linha
`ausência de evidência não é evidência de ausência` imprime em toda rodada.

---

## Reprodução

De dentro da VM, via `az vm run-command --scripts @script.sh`:

```sql
select case when sd<0.005 then 'A <0.5%' when sd<0.01 then 'B 0.5-1%'
            when sd<0.02  then 'C 1-2%'  when sd<0.04 then 'D 2-4%' else 'E >4%' end faixa,
       count(*) n, sum(case when pnl_reais>0 then 1 else 0 end) wins,
       round(sum(pnl_reais),2) pnl, round(avg(pnl_reais/nullif(risco_inicial,0)),2) r_med
from (select *, abs(entrada-stop)/entrada sd from trades where stop is not null)
group by 1 order by 1;
```
