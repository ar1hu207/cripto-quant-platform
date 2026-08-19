# REVISÃO TÉCNICA — ITEM 1 (Reality Check + FDR + purga)

**Objeto revisado:** `ITEM1-VALIDACAO-RIGOROSA.md` (proposta, 2026-07-24)
**Revisor:** parecer estatístico independente · **Data:** 2026-07-24
**Arquivos conferidos linha a linha:** `validacao.py`, `backtest_plataforma.py`, `scoring.py`,
`PLANO-REPOS-QUANT.md`, `BASE-CONHECIMENTO-TRADING.md` §3.5/§5, `tune.py`, `sweep.py`, `experimentos.py`

---

## VEREDITO

**Implementar, com as mudanças F1–F19 abaixo.**

O documento está acima da média do gênero: todas as referências de linha da §1 e §2 conferem, o
algoritmo do White's Reality Check está correto no ponto crítico (índices de bloco compartilhados
entre configs), o Benjamini-Hochberg está correto, o contrato de causalidade da §3.6 está bem
escrito, e a §4 faz as perguntas certas.

O que ele erra, erra por **otimismo sobre o quanto os testes novos resolvem** — e por adicionar
~120 graus de liberdade (`criterio` × `modo` × `atribuir` × `block` × `purga`) num item cujo
propósito declarado é *reduzir* graus de liberdade.

**A frase que resume o parecer:** o instrumento proposto fica mais rigoroso na aparência e continua
com o mesmo poder. Um instrumento sem poder que emite veredito binário produz "não tem edge" tanto
quando não tem quanto quando não dá pra saber. O conserto está em **F6, F7 e F14** — não no Reality
Check.

---

## INSTRUÇÕES DE IMPLEMENTAÇÃO

### 🔴 Bloqueantes — sem isso, não implemente

#### F1 — Bootstrap de bloco não pode receber a lista de trades
A spec §3.2 diz "usar como modo padrão em `bootstrap_ci()`". **Errado como escrito.** A lista
`oos_pnls` que chega em `validacao.py:156` **não está ordenada no tempo**: é construída concatenando
ativo a ativo em `validacao.py:120-123` (`for c in COINS: tr += ...`) e depois filtrada por fold em
`validacao.py:141`. A ordem final é *(fold, moeda, tempo)*.

Um bootstrap de bloco nessa ordem forma "blocos" que atravessam fronteiras de moeda e saltam no
tempo — ruído estruturado, não preservação de autocorrelação. **Seria pior que o IID, porque parece
mais rigoroso.**

```python
# bootstrap_ci só aceita modo="bloco" sobre série temporal de pnl_por_periodo.
def bootstrap_ci(serie, modo="iid", eh_serie_temporal=False, ...):
    if modo == "bloco" and not eh_serie_temporal:
        raise ValueError("bootstrap de bloco exige série ordenada no tempo "
                         "(saída de pnl_por_periodo), não lista de trades")
```

#### F2 — Ordem de operações: seed → golden file → refatoração
Hoje `python validacao.py` é irreproduzível (`validacao.py:106` usa `random` global sem seed), então
o critério de aceite *"`walk_forward_tendencia()` mantém funcionando idêntico"* é **inverificável**.

1. Adicione **só** a seed (`random.Random(seed)`, nunca o módulo global). Rode.
2. **Congele a saída como golden file**, com o dataset cacheado em `dados_cache/`.
3. Refatore. O teste de regressão exige reprodução bit-a-bit do golden.
4. Só então adicione features novas.

Inverter essa ordem transforma o critério de aceite numa frase sem teste por trás.

#### F3 — Trave tudo sob um `PADRAO`; mude o critério default
`criterio` (3) × `modo` (2) × `atribuir` (2) × `block` (5) × `purga` (2) = **120 maneiras de rodar a
régua**. Um item que existe para detectar snooping está multiplicando a superfície de snooping por
120. Alguém — talvez você, daqui a um ano, cansado — vai rodar as variantes e reportar a melhor.

```python
PADRAO = dict(criterio="sharpe", modo="expandindo", atribuir="saida",
              block=5, purga=True, n_boot=2000, seed=42)
```

- O **veredito é computado exclusivamente sob `PADRAO`**. Sempre.
- As demais variantes rodam em `sensibilidade(res)`, que imprime **todas de uma vez, sempre**, como
  diagnóstico — nunca como escolha do chamador.
- `walk_forward` **não aceita** `criterio`/`modo`/`atribuir` como argumento livre no caminho do veredito.

Note a troca do default: **soma bruta de PnL é seletor conhecidamente ruim** (favorece a config que
mais opera) — é exatamente o que o P5 da proposta diagnostica, mas a assinatura da §3.6 manteve
`criterio="pnl"`. Default = `"sharpe"`.

#### F4 — O embargo está mal aplicado
Em López de Prado (AFML cap. 7), o embargo existe **porque em cross-validation parte do treino vem
DEPOIS do teste** — impede que observações posteriores ao teste vazem informação de volta via
features serialmente correlacionadas.

Num walk-forward **estritamente sequencial**, treino é `[t0, tr_lim)` e teste é `[tr_lim, te_lim)`:
**não existe treino após o teste para embargar.** `embargo_ms` como especificado ("descarta faixa
após a janela de teste") descartaria trades de *teste*, degradando a amostra OOS sem corrigir viés
nenhum.

Ação: **remova o parâmetro**, ou renomeie para `gap_pre_teste_ms` (default 0), definido como
"descarta do treino os trades nos últimos h ms antes de `tr_lim`" — o análogo sequencial legítimo,
que cobre a memória das features (EMA50, Donchian20, o `range(60, ...)` de
`backtest_plataforma.py:39`). **Escreva no docstring que NÃO é o embargo de LdP e por quê.** Deixar
com o nome "embargo" garante que alguém no futuro escreva que aplicou LdP quando não aplicou.

**A purga, por outro lado, está correta** — `ts_saida < tr_lim` é exatamente a formulação de LdP
(remover do treino toda observação cujo span de label se sobreponha ao span do teste).

#### F5 — p-valores: correção de continuidade e recentragem explícita
`#{V*_b > V}/B` pode retornar 0, e p=0 é mentira (com B=2000 a resolução é 5×10⁻⁴). Além disso o
bootstrap é discreto, então empates acontecem e o comparador tem que ser `≥`:

```
p = (1 + #{V*_b >= V}) / (B + 1)
```

E a §3.5 **não diz** como o p-valor por config é calculado. "bootstrap de bloco da média contra 0" é
ambíguo, e a versão intuitiva é errada. Escreva a fórmula na spec — para testar `H0: E[f_k] = 0` é
obrigatório **recentrar**:

```
p_k = (1 + #{ (f_barra*_k − f_barra_k) >= f_barra_k }) / (B + 1)
```

Se o implementador fizer `#{f*_k < 0}/B` (percentil da distribuição não-recentrada), obtém algo
*parecido* mas não equivalente sob assimetria — e a série de PnL é assimétrica por construção,
porque `backtest_plataforma.py:81` trunca a perda em `−valor`.

---

### 🟠 Alto valor — faça junto, não depois

#### F6 — `DIAS: 180 → 1095`
**O gargalo é T, não o teste.** Com T = 180 dias, α = 0,05 unilateral e 80% de poder:

```
SR_diário · sqrt(T) ≈ 2,49  →  SR_diário ≥ 0,186  →  Sharpe ANUALIZADO ≥ 3,5
```

**Essa régua, em 180 dias, só detecta uma estratégia com Sharpe anualizado ~3,5.** Nenhum dos quatro
testes propostos muda isso. Com 3 anos (T≈1095) o mínimo detectável cai para ~1,5.

`DIAS = 180` em `validacao.py:26` é a mudança de maior retorno do Item 1 inteiro e **não está na
proposta**. `dados.baixar_ohlcv` já pagina e cacheia; 1h × 3 anos × 12 moedas ≈ 315k candles.
Custo: uma constante e um download.

#### F7 — Reportar Sharpe anualizado com IC, e o que o teste NÃO exclui
**O veredito negativo atual é mais fraco do que o documento acredita.** Revertendo o IC registrado
(`[−7,4; +3,5]` R$/trade, PnL −807 em 370 trades → média/trade ≈ −2,18, sd/trade ≈ 53,5 sobre
nocional R$1.000):

```
SR/trade IC95%  ≈ [−0,138 ; +0,065]
× sqrt(trades/ano ≈ 900)  →  Sharpe anualizado IC95% ≈ [−4,0 ; +1,9]
```

**O limite superior inclui Sharpe anualizado ~1,9** — uma estratégia excelente. E como os 370 trades
não são independentes (12 moedas correlacionadas), o intervalo verdadeiro é ainda mais largo.

Os dados **não excluem** uma estratégia muito boa; apenas falham em demonstrá-la. *Ausência de
evidência ≠ evidência de ausência.* Um documento cujo produto declarado é o resultado negativo
precisa dessa distinção mais que qualquer outro. Hoje o instrumento arredonda "não consegui medir"
para "não existe".

Nova linha de veredito negativo:

```
=> SEM EVIDÊNCIA DE EDGE. IC95% do Sharpe anualizado: [-4,0 ; +1,9].
   O teste NÃO exclui edges de Sharpe até 1,9 — instrumento sem poder pra isso (MDS=3,5).
```

#### F8 — Dois blocos rotulados, não "4 condições"
Ver Q1 na fundamentação. Reestruture o relatório:

```
BLOCO A — in-sample, família de configs
  nulo: max_k E[f_k] <= 0        objeto: o GRID
  RC p, SPA p, DSR do melhor config in-sample, FDR
  pergunta: "o melhor do grid bateu a sorte NO DADO QUE O ESCOLHEU?"
  papel: DIAGNÓSTICO de quanto do in-sample é artefato de max-de-N

BLOCO B — out-of-sample, o processo
  nulo: E[pnl do processo walk-forward] <= 0     objeto: o PROCEDIMENTO
  IC de bloco da série diária, PSR (sem deflação), Sharpe anualizado + IC, MDS, concentração
  pergunta: "o procedimento de seleção, aplicado cego pra frente, ganha dinheiro?"
  papel: DECISÃO
```

**O Bloco B decide. O Bloco A informa.** O DSR migra para o Bloco A (onde o nulo dele vale); no
Bloco B usa-se PSR simples (`SR* = 0`, sem deflação).

#### F9 — Controle de estratégia nula (adicionar ao escopo)
Rode o mesmo walk-forward completo sobre M ≈ 200 geradores de **sinal aleatório**, casados em
contagem de trades e distribuição de duração com a estratégia real. A distribuição de PnL OOS desses
M é o **nulo empírico do pipeline inteiro** — incluindo seleção, purga, modelo de custo, pooling de
moedas e agregação.

Vale mais que o Reality Check, porque valida o **instrumento**, não uma estatística. Com o gerador
injetável da §3.6 são ~15 linhas. Se o percentil da estratégia real dentro dessa distribuição não
estiver na cauda, acabou a conversa — e acabou de um jeito que nenhum revisor consegue contestar.

#### F10 — `n_trials`: tabela de sensibilidade + piso contado + log pra frente
A sensibilidade do DSR a `n_trials` é **logarítmica** (`SR0 ∝ sqrt(2 ln N)`). Errar em duas ordens de
grandeza apenas dobra o SR0:

| n_trials | fator | SR0 (n=370 trades) |
|---|---|---|
| 6 | 1,30 | 0,068 |
| 30 | 2,07 | 0,108 |
| 100 | 2,53 | 0,132 |
| 1.000 | 3,26 | 0,169 |
| 10.000 | 3,86 | 0,201 |

Publique a tabela e a ansiedade da Q4 deixa de ser problema.

**Piso contado (não chute):** `tune.py:19-21` = 3×2×3 = 18 · `sweep.py:15-19` = 3×3 = 9 ·
`experimentos.py:52-53` = 3×3×2 = 18 · `GRID × N_FOLDS` = 30 · mais os oito `validar_*.py`,
`scalp_backtest.py`, `dca_backtest.py`, `otimizar_risco.py`. **`n_trials = 100` é defensável como
PISO.** Rotule no relatório: `n_trials = 100 (PISO CONTADO, não estimativa)`.

**Correção pra frente:** JSONL append-only escrito pelo próprio runner (hash do grid + timestamp +
seed + resultado) em toda varredura. ~20 linhas. Daqui a um ano `n_trials` é **contado**, não
estimado. Isso tem mais valor científico que o RC inteiro.

#### F11 — Testes: o de ruído puro é fraco demais
Ver §E na fundamentação. Substituições e adições obrigatórias.

#### F12 — Duas linhas que dizem se o RC e o bloco estão fazendo trabalho
```
RC p = 0,31 | p unilateral da melhor config sozinha = 0,28
  -> o grid custou 0,03 de multiplicidade. O grid NÃO é a fonte do snooping.

ACF do PnL diário, lags 1..10: [...] (banda ±1,96/sqrt(T) = ±0,15)
```
Se a ACF for indistinguível de zero em todos os lags — desfecho provável para holds curtos — então
**o P3 estava errado**, o IC IID não estava inflado, e você registra isso na §6 como número. O
instrumento honesto tem que conseguir dizer *"o problema que eu ia consertar não existia"*.

#### F13 — Meça a duração antes de repetir "o efeito é pequeno"
A §2/P2 afirma "hoje o efeito é pequeno (tendência 1h, holds curtos)" **sem medida, e há indício de
que está errado**: em `backtest_plataforma.py:71` o `max_hold` está dentro do ramo
`elif estrategia == "reversao"`. **A tendência não tem time-stop nenhum** — só sai por stop,
liquidação ou flip de regime (`backtest_plataforma.py:73-76`). O hold é ilimitado por construção.

Assim que `ts_saida` existir, a primeira saída a imprimir é a distribuição de duração (mediana, p90,
máximo) e a **fração de trades que cruzam alguma borda de fold**. Se for <2%, registre e siga; se for
15%, o P2 não é atenuação, é achado.

#### F14 — MDS como portão de emissão de veredito (resposta à Q5)
Não fixe piso em contagem de trades. Derive do poder:

> O relatório calcula e imprime o **Sharpe anualizado mínimo detectável (MDS)** com 80% de poder a
> α=0,05, dado o T efetivo. Se `MDS > 2,0`, o walk-forward **não emite veredito** — emite
> `INCONCLUSIVO: instrumento sem poder (MDS = x,x)`.

É a terceira resposta que falta hoje, e é o que vai salvar o Item 2 (portões restritivos → poucos
trades) de um falso positivo por amostra pequena.

Cinto-e-suspensório opcional, **sobre observações quase-independentes, nunca sobre contagem de
trades**: T efetivo ≥ 100 períodos com PnL não-nulo na série diária, e ≥ 3 dos 5 folds com ≥ 10
trades. 370 trades em 12 moedas correlacionadas não são 370 observações.

---

### 🟡 Faça, mas sem ilusão

#### F15 — SPA (Hansen 2005): sim, mas pelo motivo certo
O argumento clássico ("RC sofre com modelos ruins no conjunto") **não se aplica ao grid atual**: com
6 configs correlacionadas a ~0,95, RC e SPA colapsam no mesmo teste t unilateral.

Dois motivos reais para implementar:

1. **A estudentização conserta um defeito do RC como especificado.** Com o máximo de médias *brutas*,
   a config que mais opera tem maior variância e domina o máximo, inflando o quantil nulo. E o grid
   **muda a frequência de trade materialmente** — `min_conv` 50 vs 65 (`validacao.py:27`) muda a
   contagem em múltiplos. Não é hipotético aqui.
2. **O grid que justifica o SPA é o do Item 2**, não o de hoje: `z_entrada(3) × z_stop(2) × k(2) ×
   pares(N)` passa fácil de 100 configs, com muitas ruins por construção (pares não-cointegrados).
   Você está construindo a régua *para esses itens*.

Dado que o bootstrap de bloco já existe, são ~15 linhas:

```
omega_k = desvio-padrão bootstrap de sqrt(T)*f*_k      (as reamostras você já gera)
A_k     = 0.25 * omega_k * sqrt(2*log(log(T))/T)
g_k     = f_k se f_k >= -A_k, senão 0                  (recentragem c/ shrinkage — SPA_c)
T_spa   = max(0, max_k sqrt(T)*f_k/omega_k)
Z*_k    = sqrt(T)*(f*_k - g_k)/omega_k
p_spa   = (1 + #{max_k Z*_k >= T_spa}) / (B+1)
```

Reporte RC e SPA lado a lado. Quando forem iguais (vão ser, em N=6), isso é evidência de que o grid é
~1 teste.

#### F16 — FDR/BH: implemente, tire do veredito
A fórmula da §3.5 está correta (BH 1995). Mas com 6 configs `3 cortes × 2 ADX` sobre os mesmos 12
ativos, as séries têm correlação ~0,9+; os p-valores serão quase idênticos e BH vai passar todos ou
nenhum, nunca discriminar. **Uma condição que não pode falhar independentemente do RC não é uma
condição.**

Mantenha a função (8 linhas, e vai importar de verdade no grid de 100+ do Item 2), **tire do conjunto
do veredito no Item 1**, e marque no relatório como não-informativa em N=6.

*(Nota: BH controla FDR sob independência ou PRDS. Estatísticas de estratégias quase idênticas são
positivamente dependentes → PRDS é defensável, BH puro passa. Não precisa de Benjamini-Yekutieli.)*

#### F17 — Consistência entre folds: diagnóstico, nunca portão
Com 5 folds, a mediana de 5 números tem variância enorme; gatear em "mediana > 0" é um teste de ~1
bit que mata bom e aprova ruim ao acaso. Poder: sob p=0,5, **5 folds positivos de 5** dá p = 0,031 —
mal passa; 4/5 dá p = 0,19. **Diga isso no relatório em vez de usar como critério.**

O que vale, e é mais barato: **concentração no nível de dia** — fração do lucro bruto total vinda dos
5 melhores dias e do melhor fold. Para a tendência (+1841 / −2240 / −1494 / −449 / +1534, soma −808,
consistente com o −807 registrado) isso vai mostrar dispersão gigante em torno de zero, que é a
assinatura de ruído.

---

### ⛔ Não faça

#### F18 — Politis-White (seleção automática de bloco)
Estimação espectral com janela flat-top, ~60 linhas, sujeita a bug silencioso, e o critério que ela
otimiza (MSE do estimador de variância do *stationary* bootstrap) **não é** o que governa o quantil
da estatística de máximo do RC.

Faça em vez disso: **sensibilidade a `block ∈ {1, 2, 5, 10, 20}`** como linha fixa do relatório
(block=1 é o IID, o que já entrega o delta da §3.7 de graça). Mesmo valor, 1/20 do custo e do risco.
Limite `block ≤ T/10`: com T=180 e block=20 são 9 blocos e a distribuição bootstrap fica quase
degenerada.

#### F19 — Variância empírica de SR entre as 6 configs no DSR (Q7)
Sua intuição está certa — `var_sr = 1/n` (`validacao.py:91`) **é** uma simplificação de Bailey-LdP
(que prescrevem `V[SR]` estimada entre os trials). Mas trocar **piora** o instrumento:

- 6 configs quase idênticas têm variância de SR minúscula → SR0 encolhe → **DSR infla**. Régua mais
  frouxa.
- Pior, é incoerente: você usaria `N = 100` para cobrir meses de snooping, mas `V[SR]` medida num
  universo de 6 configs quase iguais. `V[SR]` tem que vir do **mesmo universo** que o `N` declara.

Faça em vez disso, em ordem de impacto: (1) DSR sobre a série diária, não sobre 370 trades
pseudo-independentes; (2) tabela de sensibilidade a `n_trials` (F10); (3) DSR no objeto certo — melhor
config in-sample, não agregado OOS (F8).

---

## FUNDAMENTAÇÃO

### A) Correção estatística

#### A.1 White's Reality Check — algoritmo certo, especificação incompleta
O algoritmo da §3.4 está **correto**: `V = sqrt(T)·max_k(f_k)`, reamostragem com **os mesmos índices
para todas as configs**, recentragem por `f_k`, `p = #{V*_b > V}/B`. É literalmente White (2000).

**O ponto dos índices compartilhados está certo e é a parte que mais gente erra:** sortear índices
independentes por config destruiria a dependência cruzada e produziria um quantil nulo inflado —
você estaria testando contra um universo de configs mais diverso do que o que tem.

Correções: F5 (p-valor), e mais três:

- **`sqrt(T)` é decorativo.** Aparece em `V` e em `V*_b`; cancela na comparação. Mantenha por
  fidelidade à literatura, mas não invente interpretação para o valor de `V`.
- **A H0 do docstring está mal enunciada.** *"a MELHOR das N configs não tem performance esperada > 0"*
  convida exatamente o erro que a Q1 tenta evitar. O nulo composto é `H0: max_k E[f_k] <= 0`, ou seja,
  **nenhuma** config tem performance esperada positiva. Não se seleciona a melhor e depois se testa;
  testa-se a família. Corrija — em seis meses alguém vai ler isso.
- **Falta o benchmark.** O RC é definido sobre performance *relativa*: `f_k,t = pnl_k,t −
  pnl_benchmark,t`. Fixar benchmark = 0 é uma escolha, não uma neutralidade. Numa estratégia
  direcional em cripto, PnL positivo pode ser beta. Adicione `benchmark=None` e, no mínimo, imprima a
  **exposição líquida ponderada por tempo em posição** do fluxo OOS. É a diferença entre "tem alfa" e
  "estava comprado num bull".

#### A.2 Circular block bootstrap vs stationary bootstrap (§3.2)
**Nenhum dos dois está errado; o circular é a escolha certa aqui, e não pelo motivo que a proposta
imagina.**

- White (2000) usa o *stationary bootstrap* (Politis-Romano 1994). Vantagem: reamostras estacionárias
  (invariância ao ponto inicial), menos sensível ao comprimento do bloco (bloco geométrico).
- O CBB (Politis-Romano 1992) tem variância menor e MSE melhor para estimação de variância (Lahiri
  1999), e é **testável de forma determinística** — "blocos contíguos, wrap circular" é asserção
  verificável, coisa que bloco de tamanho aleatório não permite. Os testes da §5 dependem disso.

Recomendação: **CBB como padrão**; SB como opção (3 linhas: `if rng.random() < 1/block: reinicia`)
para checagem de sensibilidade de família. Não vale mais que isso.

**O que importa e a proposta não diz:** o ganho de honestidade não vem do bloco, vem da **agregação
da §3.3**. A dependência dominante nesse dado **não é serial — é contemporânea entre os 12 ativos**.
Doze trades abertos no mesmo dia em ativos correlacionados a 0,8 não são 12 observações. Agregar num
grid diário comum resolve isso; o bloco resolve um problema de segunda ordem. Escreva isso, senão o
esforço vai pro lugar errado.

#### A.3 DSR — a fórmula está certa; a aplicação, não
`validacao.py:94` usa `1 − sk·sr + (ku−1)/4·sr²` com `ku` como 4º momento padronizado bruto. É a
variância de Mertens, é o denominador correto do PSR de Bailey-LdP. **Confere.**

Três problemas de aplicação:

1. **`n = 370` não são 370 observações.** `sqrt(n−1)` em `validacao.py:95` trata trades correlacionados
   entre 12 moedas como independentes. Infla o DSR — direção anti-conservadora, a que dói. Calcule
   também sobre a série diária (n ≈ 150) e reporte os dois. Muda o número muito mais que qualquer
   refinamento de `var_sr`.
2. **DSR aplicado no objeto errado.** O DSR deflaciona o **melhor Sharpe in-sample** pelo número de
   tentativas. O agregado OOS de `validacao.py:148` **não é o máximo de N tentativas** — é um caminho
   único de walk-forward. É incoerência da mesma família da Q1. → F8.
3. `n_trials` cravado em 30 (`validacao.py:149`) → F10.

#### A.4 Nits verificados no código
- `validacao.py:141`: o último fold usa `t["ts"] < te_lim` com `te_lim = t1` — **o último trade da
  série é sempre descartado**. Irrelevante numericamente; conserte de graça.
- `validacao.py:131`: as bordas são fatias de **tempo iguais**, não quantis de contagem de trades (o §1
  chama de "quantis lineares", ambíguo). Folds terão contagens muito desiguais.
- `backtest_plataforma.py:39-83`: **posição aberta no fim da série é descartada silenciosamente**
  (nunca vira trade). É censura à direita e favorece estratégias que seguram perdedor. Consistente
  entre configs (não afeta o RC), mas afeta o nível de PnL. Registre.

---

### B) As 7 questões da §4

#### Q1 — empilhar 4 condições sobre nulos diferentes
**Você está certo no diagnóstico e otimista na conclusão.** Não é "conservador e provavelmente
correto" — é *incoerente como regra de decisão*, por três motivos:

1. ANDar quatro testes controla o erro tipo I (rejeição conjunta ≤ mínimo dos tamanhos), mas você
   **não consegue declarar um nível** e perde poder de forma não-quantificável. Régua sem nível
   declarado não é régua, é ritual.
2. **As quatro condições não são quatro evidências. São ~duas.** `IC-bloco > 0` e `DSR > 0.95` são a
   *mesma estatística* (média OOS sobre erro-padrão) com dois limiares. `RC p ≤ 0.05` e `≥1 config no
   FDR` são *quase a mesma coisa* com 6 configs quase idênticas.
3. **Rodam sobre unidades amostrais diferentes.** RC e FDR sobre PnL diário (T≈180); DSR e IC sobre
   PnL por trade (n=370). Métricas em unidades diferentes, com n diferentes, ANDadas.

Solução: F8. Razão para o Bloco B decidir: rejeitar o nulo do Bloco A **não é nem necessário nem
suficiente** para deployar. Não é necessário — um processo adaptativo pode ganhar OOS sem nenhuma
config fixa significativa in-sample (mudança de regime). Não é suficiente — óbvio. Como a decisão do
projeto é "opera ou não opera", o objeto de interesse é o processo.

#### Q2 — RC ou Hansen SPA?
→ **F15.** Implemente, mas pelo motivo certo (estudentização + o grid do Item 2), não pelo argumento
clássico, que não se aplica a N=6.

#### Q3 — comprimento do bloco
→ **F18** (não implementar Politis-White) + **F12** (imprimir a ACF empírica, que é evidência direta
sobre a premissa do P3). `n^(1/3)` com T=180 dá 5,6 → 5, razoável.

#### Q4 — poder com 6 configs quase idênticas, e `n_trials` honesto
**(a) Poder.** Com ρ ≈ 0,9–0,99 entre configs, a distribuição do máximo sob H0 tende à de uma única
config (para ρ→1, `E[max de N normais] → 0`, não `sqrt(2 ln N) ≈ 1,34` que valeria para 6
independentes). **A penalidade de multiplicidade é quase zero e o RC vai reproduzir o p-valor
unilateral ingênuo da melhor config.**

Isso não é defeito do RC — ele está reportando corretamente que você fez ~1 teste, não 6. O defeito é
a **expectativa**: o RC não vai punir o data snooping do projeto, porque o snooping que importa não
está no grid. → **F12** imprime os dois lado a lado; essa linha vale mais que o RC inteiro, porque
mata a ilusão.

**A restrição que morde não é o teste, é o T.** → **F6, F7, F14.**

**(b) `n_trials` honesto.** Não dá pra recuperar retroativamente. → **F10**: tabela de sensibilidade
(logarítmica — a precisão que você não tem, você também não precisa), piso contado, e log
append-only para que o número futuro seja contado.

#### Q5 — piso de amostra
→ **F14.** Derive do poder, não da contagem. O `n < 5` em `validacao.py:81`/`:104` você está certo em
classificar como guard, não critério.

#### Q6 — consistência entre folds
→ **F17.** Reporte, não gate. A fração de folds positivos com 5 folds praticamente não tem poder.

#### Q7 — variância dos SRs no DSR
→ **F19.** Sua intuição está certa, mas a "melhoria" afrouxaria a régua e seria incoerente.

---

### C) O diagnóstico bate com o código?

**Conferi TODAS as referências de linha da §1 e da §2. Todas conferem.**

`COINS/TF/GRID/N_FOLDS` em `validacao.py:24-28` · `stats` `:66-74` · `deflated_sharpe` `:77-96` ·
`bootstrap_ci` IID sem seed `:99-109` com `random.randrange` global em `:106` · `walk_forward`
`:113-168` · bordas `:131` · seleção/OOS `:136-143` · naive `:146-147` · `n_trials` `:149` · veredito
`:165`. No motor: `ts` de entrada em `backtest_plataforma.py:52` e o dict sem saída em `:82`.

Isso é raro num documento de spec e conta a favor.

#### C.1 O vazamento do P2 é real
`validacao.py:138` soma `t["pnl"]` de todo trade com `ts < tr_lim`, onde `ts` é o timestamp de
**entrada** (`backtest_plataforma.py:52`). Um trade que entra antes da borda e sai depois entrega ao
critério de seleção um P&L determinado por preço dentro da janela de teste. **Vazamento real,
confirmado.** Mas a atenuação declarada não é verificada → **F13**.

#### C.2 `ts_saida` bloqueia a purga? Sim.
Sem timestamp de saída não há como saber quais trades cruzam a borda. `backtest_plataforma.py:82`
confirma. Mudança aditiva e trivial: `"ts_saida": int(tss[i])`. **Grave também
`"barras": i - pos["i0"]`** — custa nada e o Item 3 (dollar bars, duração variável) vai precisar
exatamente disso.

Assimetria a documentar no docstring: a entrada executa no open de `i+1` com `ts = tss[i+1]` (`:52`),
mas a saída é avaliada intrabarra em `i` e o preço é `closes[i]` ou o nível de stop. Então `ts_saida =
tss[i]` é o **início** da barra de saída, não o instante do fill. É conservador (antecipa a saída) e
está certo para purga.

#### C.3 Purga certa, embargo errado
→ **F4.**

#### C.4 O contrato de causalidade da §3.6 está certo e é verificável
Confirmei que o gerador atual é causal: `scoring.py:18-19` (`.shift(1)` do Donchian),
`scoring.py:32` (média de volume só até `i`), `backtest_plataforma.py:51` (execução no open de `i+1`),
`backtest_plataforma.py:68` (`mids[i-1]`).

**Acrescente um teste que force o contrato:** rode o gerador na timeline inteira e depois em `df[:k]`
para vários `k`; assert que os trades com `ts_saida < ts[k]` são idênticos. Se um dia alguém
normalizar pela série toda — que é exatamente o que o Item 2 vai querer fazer, com z-score — esse
teste pega.

---

### D) O que falta e o que é teatro

Além de F6/F7/F9/F10:

#### D.1 Teatro estatístico identificado
1. **FDR/BH no veredito com N=6** — condição que não pode falhar independentemente do RC.
2. **`embargo_ms` num walk-forward sequencial** — parâmetro que não corrige viés nenhum, com nome de
   rigor.
3. **"4 condições"** — ~2 evidências com 4 nomes.
4. **Politis-White se fosse implementado** — sofisticação cujo critério de otimalidade não é o que
   governa a estatística usada.

Nada disso é fatal. Mas os quatro juntos produzem um documento que *parece* mais rigoroso que o
instrumento resultante — precisamente o modo de falha que o projeto existe para evitar.

#### D.2 O gap OOS-vs-naive não tem barra de erro
`validacao.py:164` afirma que "a diferença OOS vs naive mede a INFLAÇÃO do data-snooping". Sem
incerteza atrelada, é um número que pode ser qualquer coisa. Ou dê um IC de bootstrap, ou rebaixe a
afirmação a nota qualitativa.

#### D.3 Nota sobre a §8 (paridade do trailing quebrada)
Registrar como débito fora de escopo é defensável, mas suba um degrau: enquanto `simulador.atualizar()`
tem trailing e `backtest_ativo` não, **a régua valida uma estratégia diferente da que roda ao vivo**.
Para veredito *negativo* é inofensivo. Para qualquer veredito **positivo é bloqueante**. Escreva na §8
com essas palavras.

---

### E) Viabilidade

#### E.1 Dá pra fazer tudo em numpy/math puro? Sim, sem esforço.
- **CBB:** `idx = (starts[:, None] + arange(block)) % n`, achatado e cortado em `T`. Uma linha.
- **Stationary bootstrap:** idem com comprimento geométrico. Três linhas.
- **BH:** sort + comparação vetorizada. Cinco linhas.
- **RC/SPA:** a única peça não-trivial é `omega_k`, obtida de graça como o desvio-padrão das próprias
  médias bootstrap. Não precisa de HAC/Newey-West (que também seriam 10 linhas).
- **Quantil normal:** já resolvido pelo Acklam em `validacao.py:37-63` (erro relativo ~1e-9). Só não
  use para `p` além de ~1e-12; com `n_trials = 10.000`, `p = 0,9999`, ainda está confortável.

**Onde dói: performance, e só se implementarem em loop Python.** O `bootstrap_ci` atual é 5.000 × 370
= 1,85M operações em Python puro (`validacao.py:105-107`) — já é lento. Adicionar RC (2.000 boots) +
FDR (6 × 2.000) + sensibilidade a 5 blocos + 3 critérios, tudo em loop, vira minutos por rodada e mata
a iteração.

Instrução explícita — é a diferença entre 2 ms e 2 minutos:

```python
# gerar a matriz de índices UMA vez: shape (n_boot, T)
idx = block_bootstrap_idx_matriz(T, n_boot, block, rng)   # np.ndarray int
medias = pnl_matriz[:, idx].mean(axis=2)                  # (n_cfg, n_boot)
```

Nada de `for b in range(n_boot)`. Memória: 2.000 × 180 int64 = 2,9 MB. Irrelevante.

#### E.2 A "regra inviolável 7.1" é mais estrita que a regra do próprio projeto
Verifiquei: **nenhum arquivo importa `validacao`**. Ela não está no caminho ao vivo. A regra 6 do
`PLANO-REPOS-QUANT.md:39-42` proíbe dependência no **runtime** e autoriza explicitamente
`requirements-pesquisa.txt` — o próprio plano recomenda `statsmodels` para o ADF do Item 2
(`PLANO-REPOS-QUANT.md:322-326`). A §7.1 do ITEM1 endurece para "sem dependência nova" ponto final.

Aqui não faz diferença (tudo que o Item 1 precisa é trivial em numpy, e eu manteria puro por isso).
Mas **não trate como inviolável**: no Item 2 você vai precisar do ADF e vai bater de frente com a
própria regra que escreveu. Corrija a redação da §7.1 para espelhar a regra 6.

#### E.3 Os testes da §5 — o de ruído puro é fraco demais (detalhe do F11)
**"ruído N(0,1) puro → p alto na maioria das seeds" não é teste de calibração. É smoke test.** Passa
por motivo errado com facilidade: um bug que faça `V*` sistematicamente grande demais produz `p ≈ 1`
sempre e passa com louvor. Você teria um RC que nunca rejeita nada e um teste verde.

**Teste correto — tamanho e uniformidade.** Rode o RC completo M ≥ 200 vezes sobre painéis
independentes de ruído branco com o mesmo `T` e `N`, colete os p-valores e afirme:

1. **Taxa de rejeição** em α=0,05 dentro da banda binomial: com M=200, `[0,02 ; 0,09]`.
2. **Uniformidade dos p-valores** — muito mais forte: `|média − 0,5| < 0,08` e desvio máximo da CDF
   uniforme < 0,15 (KS na mão, 4 linhas). Uniformidade pega os dois modos de falha de uma vez:
   anti-conservador **e** absurdamente conservador. É *a* propriedade que define um teste calibrado.

Marque como `@lento`; na versão rápida use M=50 com banda mais larga.

**Testes que faltam, em ordem de valor:**

1. **Recuperação de autocorrelação.** AR(1) com φ=0,5 conhecido; afirme que o IC de bloco é mais largo
   que o IID por fator próximo de `sqrt((1+φ)/(1−φ)) = 1,73`, tolerância ±25%. Sem isso você testou a
   *mecânica* do bloco, não a *estatística* — a mecânica pode estar perfeita e o bootstrap não estar
   corrigindo nada.
2. **Poder como taxa, não como evento.** "drift injetado → p baixo" numa seed é anedota. Escolha o
   drift que dá 80% de poder nominal e afirme rejeição em ≥70% de 100 réplicas.
3. **Invariância de escala.** RC não-estudentizado é invariante a reescalar *todas* as séries pelo
   mesmo fator; o SPA é invariante a reescalar *cada config* separadamente. Dois asserts que
   distinguem RC de SPA e pegam erro de recentragem.
4. **Redução a N=1.** Com uma config, `reality_check` tem que reproduzir exatamente o p-valor do
   bootstrap unilateral da média. Pega qualquer erro de recentragem por `f_k`.
5. **Purga nos dois sentidos:** trade que cruza a borda fora do treino, **e** `purga=False` reproduz o
   número antigo exatamente.
6. **Golden file de regressão** (F2) — o teste mais importante da lista e o único ausente.
7. **Causalidade do gerador** (C.4).
8. `fdr_bh` com p-valores duplicados, m=1, e q=1,0.

Os testes precisam rodar **sem rede**: hoje `walk_forward` baixa 12 moedas em `validacao.py:115`. A
injeção do gerador da §3.6 resolve para os sintéticos; para o golden, congele um fixture em
`dados_cache/`.

---

## CHECKLIST PARA O AGENTE DE DEV

```
[ ] F2  seed -> golden file -> refatorar (NESTA ORDEM)
[ ] F1  guard: bootstrap de bloco só sobre série temporal
[ ] F3  PADRAO travado; criterio default = "sharpe"; sensibilidade() imprime tudo sempre
[ ] F4  remover/renomear embargo_ms -> gap_pre_teste_ms (default 0) + docstring
[ ] F5  p = (1+#{>=})/(B+1) em TODOS os p-valores; recentragem escrita na spec
[ ] F6  DIAS 180 -> 1095
[ ] F7  relatório imprime Sharpe anualizado + IC de bloco + MDS; veredito diz o que NÃO exclui
[ ] F8  relatório em BLOCO A (in-sample/diagnóstico) e BLOCO B (OOS/decisão); DSR migra p/ A
[ ] F9  controle de estratégia nula (M≈200 sinais aleatórios pelo mesmo pipeline)
[ ] F10 tabela de sensibilidade a n_trials; n_trials=100 como PISO CONTADO; log append-only
[ ] F11 testes: tamanho+uniformidade (M>=200), AR(1), poder como taxa, N=1, escala, golden, causalidade
[ ] F12 imprimir RC p vs p da melhor sozinha; ACF lags 1..10 com banda
[ ] F13 ts_saida + barras; medir duração e fração que cruza borda ANTES de afirmar "efeito pequeno"
[ ] F14 MDS > 2.0 -> veredito INCONCLUSIVO
[ ] F15 SPA com estudentização (~15 linhas)
[ ] F16 fdr_bh implementado mas FORA do veredito no Item 1
[ ] F17 concentração (top-1 fold, top-5 dias) como diagnóstico; nunca portão
[ ] F18 NÃO implementar Politis-White; sensibilidade a block {1,2,5,10,20}
[ ] F19 NÃO trocar var_sr por variância empírica entre as 6 configs
[ ] --  vetorizar tudo com matriz de índices (n_boot, T); nada de for b in range(n_boot)
[ ] --  corrigir §7.1 para espelhar a regra 6 do PLANO (requirements-pesquisa.txt é permitido)
[ ] --  §8: paridade do trailing é BLOQUEANTE para qualquer veredito positivo
```
