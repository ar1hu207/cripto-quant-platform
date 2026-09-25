# Pré-registro — `[N-19]` Swing 4h/1d a 1x

> **Escrito ANTES de rodar qualquer número.** É isto que impede o resultado de escolher a
> hipótese. Nada abaixo pode ser editado depois que a primeira rodada sair; o que mudar entra
> como adendo datado, com o motivo.
>
> Base: `main` = `f0e8ab7`. Território: `terr/n19-swing`. Onda 3 da V2.

---

## 1. A hipótese, e de onde ela vem

A `BASE-CONHECIMENTO-TRADING.md` §6.1 registra, desde junho, a única coisa que este projeto já
declarou como sobrevivente:

> *"O único perfil que sobreviveu: **trend-following sem alavancagem, timeframe maior**
> (~10%/ano real, defensivo)."*

**Nunca virou trabalho.** O `PLANO-V2` a lista como `N-19` e anota: *"está escrito desde junho e
nunca virou trabalho"*.

**H1:** o mesmo sinal de tendência, operado em **4h ou 1d** e a **1x**, tem expectativa
superior à do perfil que roda hoje (1h, 10x) **depois de custo** — e a diferença vem de
**turnover**, não de acertar mais.

**H0 (a que o desenho tem de poder escolher):** o perfil de hoje não é pior. Ele entra na
comparação como linha própria, não como pano de fundo.

## 2. Por que este card e não outro

A Onda 3 declarou que **turnover baixo é o ALVO, não efeito colateral**. O `N-19` é o único item
da onda em que o turnover cai **por construção** (barra maior), e não por um filtro escolhido —
filtro escolhido é onde o sobreajuste mora, e três tentativas de agosto (`Q-8`, `Q-9`, `Q-11`)
morreram exatamente aí.

E a 1x o custo por round-trip deixa de ser o termo dominante: `taxa/risco = 2·taxa_lado/sd`, e
com barra de 1d o `sd` (3×ATR diário) é uma ordem de grandeza maior que o de 5m.

## 3. 🚦 O portão que este card NÃO pode contornar: benchmark

**Trend-following a 1x em cripto é comprado quase o tempo todo.** Num período em que cripto
subiu, "~10%/ano" pode ser **beta puro** — estar comprado, não ter habilidade.

A régua já sabe disso e avisa sozinha (`validacao.py:2558-2572`): quando a exposição líquida está
longe de zero, *"parte deste P&L é BETA, e o zero deixa de ser um benchmark defensável"*, e
**veredito POSITIVO não se emite**.

**Portanto, declarado antes de rodar:**

- O Reality Check deste card roda com `benchmark = buy-and-hold` das mesmas 12 moedas, na mesma
  grade diária, com o mesmo custo de entrada e saída. **Não com zero.**
- A `exposicao_liquida` é reportada em toda linha. Se ela vier alta e o RC contra benchmark der
  `p` alto, **a conclusão é "é beta"** — e isso é entrega, não fracasso.
- **Se o benchmark não puder ser construído, o card devolve INCONCLUSIVO e para.** Não se emite
  positivo contra zero.

## 4. A grade — pequena e fechada agora

Cinco perfis. Dentro de cada um, a grade de entrada **já estabelecida** do projeto
(`min_conv` ∈ {50, 55, 65} × `adx_min` ∈ {22, 25} = 6 configs), escolhida **dentro do fold de
treino**.

| perfil | tf | lev | papel |
|---|---|---|---|
| `atual` | 1h | 10x | **H0** — o que roda hoje |
| `swing-4h-1x` | 4h | 1x | H1 |
| `swing-1d-1x` | 1d | 1x | H1 |
| `swing-4h-2x` | 4h | 2x | gradiente |
| `swing-1d-2x` | 1d | 2x | gradiente |

**O que NÃO varia**, e é o que mantém a comparação com um fator só: política de saída (a viva),
`trailing` na unidade do stop (`N-13`), custo, moedas, janela (`DIAS=1095`), e o `PADRAO` travado
da régua — incluindo `atribuir="entrada"`, porque o `C-4` **é decisão do dono e continua parada**.

**Nenhuma dimensão nova é aberta depois.** Se algo pedir dimensão nova, vira card próprio com
pré-registro próprio.

## 5. Critério de aceite — o que faz o card fechar POSITIVO

Todos, simultaneamente, para pelo menos um perfil `swing`:

1. **Veredito da régua** sob o `PADRAO` travado, com `benchmark = buy-and-hold` (§3).
2. **Turnover ≥ 10× menor** que o do perfil `atual`, medido em trades/ano. Se o turnover não cair
   uma ordem de grandeza, **a hipótese do card não foi testada** — foi testada outra coisa.
3. **CPCV (`N-7`)**: mediana das trajetórias positiva, e a fração de trajetórias positivas
   reportada. O bloco B decide sobre a **mediana**, nunca sobre a melhor.
4. **PBO (`N-8`)** reportado. PBO alto derruba, mesmo com Sharpe bom.
5. `exposicao_liquida` reportada e discutida em texto, não só impressa.

**Qualquer um faltando ⇒ o card fecha NEGATIVO ou INCONCLUSIVO, com o motivo escrito.**

## 6. O que já sei que pode derrubar, e vou reportar mesmo se derrubar

- **Trades demais de menos.** Em 1d com 3 anos e 12 moedas, o número de trades pode ficar baixo
  demais para a régua responder. Se o MDS explodir, o veredito é INCONCLUSIVO **por falta de
  poder** — não "sem edge". A distinção é a lição do `[F6]`.
- **Beta.** Ver §3. É o desfecho mais provável e está declarado antes.
- **A janela.** 1.095 dias pegam um ciclo de cripto quase inteiro, mas **um** ciclo. Estender com
  o `dados_bulk` (2020-09 em diante) é a continuação natural, e **não** entra aqui — mudaria a
  janela e quebraria a comparação com tudo que já foi medido.

## 7. Orçamento estatístico

5 perfis × 6 configs × 5 folds = **150 seleções**. Cada rodada é registrada no log append-only do
`[N-9]` (`registrar_tentativa`), e o `n_trials` declarado sai de lá — **não do meu julgamento**,
que foi exatamente a crítica de 25/08.

⚠️ **Defeito encontrado ao preparar este card:** o `tentativas.jsonl` vive em
`pesquisa/dados_cache/`, que é *gitignored* e **por worktree**. Nesta worktree nova ele está
**vazio** — ou seja, o histórico cumulativo de tentativas do projeto **não é reconstituível**.
Isso derrota metade do propósito do `[N-9]`. Vira card próprio; aqui fica registrado e o
`n_trials` deste card é declarado com a tabela de sensibilidade ao lado (6 / 30 / 100 / 1000 /
10000), para que o leitor escolha o piso em vez de aceitar o meu.

## 8. Como reproduzir

```bash
python -m pesquisa.validacao n19        # a ser adicionado em pesquisa/n19_swing.py
```

O código do card mora em `pesquisa/n19_swing.py` — módulo próprio, **sem editar
`validacao.py`**, para não colidir com outros trabalhos da Onda 3.

---

## Adendo 1 — 2026-09-24 (o corpo acima NÃO foi editado)

**Procedência.** Este arquivo foi escrito em 2026-09-09 às 23:43 (mtime do arquivo na worktree
`wt/n19`, branch `terr/n19-swing`) e ficou **fora do git** até 2026-09-24, quando a varredura de
pendências o achou. Nenhum número do `[N-19]` foi rodado nesse intervalo: `pesquisa/n19_swing.py`
não existe em branch nenhuma, e não há `tentativas.jsonl` em lugar nenhum. O arquivo entra no
repositório byte a byte igual ao de 09/09 (sha256 `3f7a4054b9cfc6a0…` antes deste adendo).

**Três coisas mudaram desde a escrita, e quem for rodar o card tem de saber antes:**

1. **O `C-4` foi decidido** (dono, 24/09): o `PADRAO` da régua passou a `atribuir="saida"`. A §4
   pinava `"entrada"` *porque o C-4 estava parado*; o motivo deixou de existir. **O card roda
   sob o `PADRAO` vigente (`"saida"`)**, e a linha `"entrada"` sai lado a lado em
   `sensibilidade()`, como para qualquer veredito.
2. **A política viva mudou** (dono, 09/09): o trailing do vivo é **3R/3R**, não o 1R/1R da D-5.
   "A política de saída (a viva)" da §4 passa a significar 3R/3R; o espelho da pesquisa já
   acompanha (`[paridade 3R]`).
3. **O defeito da §7 foi corrigido** (`[N-9b]`): o `tentativas.jsonl` agora mora no checkout
   principal do clone, o mesmo para todas as worktrees. O `n_trials` deste card pode sair do
   log — continua valendo a tabela de sensibilidade ao lado, porque o log só conta daqui pra
   frente.

O resto — hipótese, grade, portão de benchmark, critério de aceite — fica como está.

