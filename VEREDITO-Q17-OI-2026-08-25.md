# [Q-17] Veredito — divergência open interest × preço

> Rodada de 2026-08-25, `main` = `1d04857` + `2deef5d`/`a792aa6`/`0d9cf6d`.
> Hipótese, grade e prognóstico fixados **antes** em `PRE-REGISTRO-Q17-OI-2026-08-25.md`.
> Saída literal completa em `RODADA-Q17-OI-2026-08-25.txt` (148 linhas), colada em trechos aqui.

---

## 1. O veredito

> ## `SEM EVIDÊNCIA DE EDGE`
>
> **Caso 1 da §7.2 do `VEREDITO-M4.md`: registrar o desvio, não trocar o default.**
> Nada muda no `scoring`, no `signal_engine`, no `autotrader` ou na config de produção.

```
=> VEREDITO: SEM EVIDENCIA DE EDGE (IC-bloco (-3.4988, 12.3203) inclui 0
   ou PSR 0.8856 <= 0,95 ou RC p = 0.1614 > 0,05).
   IC95% do Sharpe anualizado: [-0.664 ; 1.986].
   O teste NAO exclui edges de Sharpe ate 1.986 -- MDS = 1.574.
   Ausencia de evidencia nao e evidencia de ausencia. [F7]
```

---

## 2. Onde eu errei o prognóstico, e isso é o mais interessante da rodada

O pré-registro §5 escreveu, antes de qualquer número:

> *"Espero `SEM EVIDÊNCIA DE EDGE`, **e a `"off"` vencendo na maioria dos folds**."*

**Acertei o veredito e errei a segunda metade — e ela não errou por pouco.** O treino,
escolhendo por Sharpe entre 24 configs (das quais 6 eram `"off"`), escolheu o portão de open
interest em **cinco folds de cinco**:

```
 fold   config (conv/adx)   trades    pnl OOS
    1  (55, 22, 'concorda')      824  R$  +1073
    2  (65, 22, 'concorda')      616  R$  +3780
    3  (65, 22, 'concorda')      587  R$   -712
    4  (65, 22, 'concorda')      518  R$  +1208
    5  (55, 22, 'concorda')      653  R$  -1567
```

A hipótese nula estava na grade, disponível em todo fold, e **nunca foi escolhida**. Registro
isso como erro meu de prognóstico, não como achado — pelo motivo da §3.

E a comparação com o baseline, re-medido na mesma janela, anda toda na mesma direção:

| | baseline (`C trailing 2%`) | com portão de OI | |
|---|---|---|---|
| Sharpe anualizado | 0,620 | **0,731** | ↑ |
| PSR | 0,8447 | **0,8856** | ↑ |
| DSR (melhor config in-sample) | 0,0119 | **0,0506** | ↑ 4× |
| Reality Check `p` | 0,2009 | **0,1614** | ↓ |
| Hansen SPA `p` | — | 0,1484 | |
| trades OOS | 5.330 | 3.198 | **−40,0%** |
| P&L OOS | +R$ 4.842 | +R$ 3.782 | −21,9% |
| **P&L por trade** | R$ 0,908 | **R$ 1,183** | **+30,2%** |
| win rate | 61,2% | 60,4% | ≈ |

Cortar 40% dos trades e perder só 22% do P&L é exatamente a direção que o `[Q-14]` pergunta
("entrar em MENOS e MELHORES"). **E ainda assim não é evidência de nada.**

---

## 3. Por que nada disso é evidência — e um número que derruba sozinho

**Os quatro portões da régua dizem não, e nenhum chega perto de passar:**

- IC-bloco da média/dia `(-3,4988 ; 12,3203)` — **inclui zero**;
- PSR `0,8856` contra o limiar `0,95`;
- Reality Check `p = 0,1614` contra `0,05`;
- DSR da melhor config `0,0506` contra `0,95`;
- FDR (BH, q=0,10): **0 de 24** configs sobrevivem.

**E o IC do Sharpe do portão, `(-0,664 ; 1,986)`, contém confortavelmente o 0,620 do
baseline.** Ou seja: `0,731 > 0,620` **não é uma diferença demonstrada**. É a mesma ressalva
que o `INVESTIGACAO-MOTOR` §7.3 já fez sobre outra ordenação.

### 3.1 O número que derruba sozinho: **todo o lucro é um fold**

A régua imprimiu `maior fold = 1.0 do total`. Fazendo a conta:

```
folds:          +1073   +3780   −712   +1208   −1567
total:          +3782
SEM o fold 2:      +2          <-- dois reais
```

**O fold 2 é 99,95% do resultado.** Tirando ele, os outros quatro folds somam **R$ 2** em três
anos. E o baseline é *menos* concentrado nisso (`maior fold = 0.64`), não mais.

Um resultado que depende inteiramente de um sexto da janela não é um resultado — é uma janela.
Isto sozinho bastaria para o veredito, mesmo que os testes tivessem passado.

**Folds positivos: 3/5** — igual ao baseline, e a própria régua avisa que com 5 folds isso dá
`p = 0,19` e é diagnóstico, nunca portão.

---

## 4. Um defeito da MINHA grade, encontrado pela rodada

**`concorda_tend` é degenerado: ele deu contagem de trades idêntica a `concorda` nas seis
comparações**, sem exceção:

```
(50,22): concorda 5272 | concorda_tend 5272        (55,25): 4305 | 4305
(50,25): concorda 4959 | concorda_tend 4959        (65,22): 3174 | 3174
(55,22): concorda 4690 | concorda_tend 4690        (65,25): 3154 | 3154
```

O motivo é mecânico e eu deveria tê-lo visto ao desenhar a grade: o motor **já** exige
`adx >= adx_min` para entrar em tendência, então "filtrar só quando há tendência" não recorta
nada além do que `concorda` recorta. A grade tem **4 modos declarados e 3 distintos**.

**Não corrigi a grade nem re-rodei.** Trocar a grade depois de ver o dado é uma tentativa nova
que teria de ser contada, e a §4 do pré-registro proíbe exatamente isso. O efeito de deixar
como está é que `n_trials = 940` conta 4 modos onde havia 3 — ou seja, **pune mais do que
deveria**, que é o único lado em que este projeto aceita errar.

---

## 5. Dois fatos sobre o open interest que a rodada mediu de passagem

**1. `d_oi > 0` acontece em ~76% das barras.** O portão `concorda` corta 40% dos trades, não
50% — o open interest tem tendência secular de alta em três anos, então a diferença de uma
barra não é cara-ou-coroa. Consequência: o filtro é **fraco**, e qualquer desenho futuro que
o suponha simétrico está errado.

**2. Por isso o modo `peso` AUMENTA os trades** (6.461 → 6.888 em `(50,25)`): com 76% de
concordância, o bônus de `+10` deixa passar mais sinais do que a punição de `−10` barra.

**3. A cobertura do dado foi 99,9%** — `26.249/26.279` barras com `d_oi` medido, idêntico nas
12 moedas. As 30 que faltam são a borda D+1 de hoje. O cano da Fase 1 aguentou a janela inteira.

---

## 6. Uma correção ao plano: o MDS real é 1,574, não 1,436

O `PLANO-Q17-INFORMACAO` §2 publicou `MDS = 1,436` para as sete fontes, calculado com
`T = 1095`. **A rodada mediu `MDS = 1,574`, com `T = 911`.**

A diferença é legítima e eu deveria ter previsto: o `T` que alimenta o MDS é o da série **OOS**,
que começa em `bordas[1]` — cinco sextos da janela, porque o primeiro segmento é treino puro e
nunca foi testado. `1095 × 5/6 ≈ 911`.

Não muda nenhuma conclusão do plano (`1,574 < MDS_LIMITE = 2,0`, todas as fontes seguem
testáveis), mas a tabela precisa dizer o número certo. **Corrigido no plano nesta mesma data.**

---

## 7. O que isto significa para o card, e o que NÃO significa

**Significa:** a pergunta do `[Q-17]` foi respondida com o instrumento do projeto. "Smart money"
virou uma hipótese mecânica, falseável, medida sobre 3 anos e 12 moedas, e a resposta é *não há
evidência de que ela carregue informação além do preço*. **O default não muda.** Isso é entrega.

**Não significa** que o open interest seja inútil. O MDS de 1,574 diz que o teste **não exclui**
edges de Sharpe até 1,986. Ausência de evidência não é evidência de ausência (`[F7]`), e a régua
imprime isso justamente para ninguém escrever a frase errada.

**E não autoriza** a próxima tentativa disfarçada de "ajuste". Qualquer uma destas é uma rodada
nova, com `n_trials` maior, e pré-registro próprio:

- limiar em `d_oi` (só filtrar quando a variação passa de X);
- z-score do OI em janela (respeitando o teto de 14 dias da §4 do plano);
- OI em valor (`sum_open_interest_value`) em vez de contratos;
- as razões long/short — que continuam **barradas**, porque não reconciliam com o caminho ao
  vivo (§4.2 do plano), independentemente do que qualquer rodada mostrar.

---

## 8. Proveniência

```
comando:      python -m pesquisa.validacao oi
PADRAO:       criterio=sharpe modo=expandindo atribuir=entrada block=5 n_boot=2000 seed=42
purga:        ATIVA
n_trials:     940 (piso contado cumulativo: 820 − 30 + 120, arredondado para cima)
janela:       1h, 1095 dias, 12 moedas, LEV 10x fixo
calibracao:   controle nulo rejeitou 7/200 paineis sem sinal (taxa 0,035) -> CALIBRADO
              banda exata [4 ; 16] = [0,02 ; 0,08] | IC da taxa (0,01419 ; 0,07078)
ACF lag 1:    0,1492 contra banda ±0,0649 -> autocorrelacao REAL, o bootstrap de bloco age
```

**A rodada foi interrompida duas vezes** (o harness derrubando a árvore de processos do shell;
sem erro no log, sem órfão, sem pressão de memória). Foi refeita num processo destacado. A
reprodução é exata: o baseline devolveu `IC-bloco (-5.4918, 16.4387)`, `PSR 0.8447`,
`RC p = 0.2009` nas **duas** execuções, e as 24 contagens de trades bateram config a config.
`seed=42` travado fazendo o seu trabalho.

Da interrupção saiu um conserto que fica: `gerar_por_cfg_paralelo` agora aceita `checkpoint` e
grava cada config assim que ela sai, com grava-e-renomeia. Morte no meio passou a custar uma
config em vez da varredura inteira — defeito que já tinha cortado o `T-REGUA` duas vezes.
