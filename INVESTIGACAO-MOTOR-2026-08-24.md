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
