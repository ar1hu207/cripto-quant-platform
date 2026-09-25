# MEDIÇÃO — a trava diária custa dinheiro? (2026-09-24)

**Pergunta do dono.** A trava diária (para de abrir posição quando o equity do dia cai 5% em
relação ao início do dia, contando o não realizado) disparou em **8 dos 14 dias** entre 11 e
24/09. Em três deles o dia fechou bem positivo (18/09 +R$318, 23/09 +R$190, 24/09 +R$417).
Ela está barrando os dias bons?

**Resposta curta: não, nesta amostra.** Sem a trava, os sinais barrados teriam virado **41
posições** e **−R$195 (−4,5R)** nos sete dias travados que o backup cobre. Os dias travados que
fecharam positivos ganharam com posições abertas **antes** da trava (e, em 23/09, com um
fechamento manual de +R$258), não com os sinais que ela barrou.

Decisão do dono na mesma data: medir antes de mexer. Recomendação: **manter a trava como
está** e remedir quando houver 30+ dias travados.

---

## Método

`python -m pesquisa.medicao_trava <backup-do-trading.db>` (backup do blob de 24/09 03:17).

- **Janelas:** do disparo da trava (`config_auditoria`, `trava_dia_em`) até a virada do dia.
  O backup cobre 11, 14, 16, 18, 20, 22 e 23/09. O de 24/09 disparou depois do backup.
- **Seleção:** réplica do `autotrader.auto_executar` minuto a minuto — sinais `novo` que
  passaram no fluxo, convicção ≥ 60, frescor ≤ 12 min, cooldown de 30 min, um por ativo,
  5 slots, teto de margem de 50%, teto de risco aberto de 10% do equity do início do dia.
  O **livro real** (posições que já estavam abertas) ocupa slot, ativo, margem e risco.
- **Execução:** post-only a 0,10% do preço, TTL de 1h; enche se a vela de 1m toca o limite.
- **Gestão:** stop de abertura, trailing **3R/3R** (o vivo desde 09/09), 10x fixo, 3% de risco,
  maker 0,02% na entrada e taker 0,05% na saída. Dentro da vela, o stop é checado **antes** do
  trailing (o lado conservador); vela que abre além do stop sai na abertura (gap).
- **Preço:** velas de 1m do **spot** da Binance, que é a fonte do `preco_ao_vivo` do bot.

## Validação — o simulador contra o que produção fez

| teste | resultado |
|---|---|
| preenchimento das 49 ordens desde 09/09 | **49/49** (39 cheias, 10 expiradas) |
| desfecho dos 34 trades não-manuais | motivo **30/34**, correlação em R **0,93** |
| soma do P&L desses 34 | real +R$389,76 × simulado +R$289,87 |

O viés é **conservador** e concentrado: o trade #99 (ETH) armou o trailing e voltou na mesma
vela de 1m; o bot, que marca a cada ~8–30 s, viu a ordem certa e saiu com +R$116; o simulador,
que só vê máxima e mínima da vela, checa o stop primeiro e registra −R$22. Sem esse trade o
simulador erra para **cima** em R$38 nos outros 33.

## Resultado

| dia | trava | ordens | cheias | ganhos | perdas | P&L simulado | em R | dia real |
|---|---|---|---|---|---|---|---|---|
| 11/09 | 09:55 | 10 | 10 | 2 | 8 | −R$64,13 | −2,13 | −R$65,85 |
| 14/09 | 15:11 | 9 | 7 | 3 | 4 | +R$11,47 | +0,43 | −R$1,59 |
| 16/09 | 18:07 | 1 | 1 | 1 | 0 | +R$9,34 | +0,38 | −R$56,94 |
| 18/09 | 10:02 | 2 | 1 | 0 | 1 | −R$11,98 | −0,34 | +R$318,16 |
| 20/09 | 01:49 | 16 | 13 | 5 | 8 | −R$83,66 | −1,56 | +R$2,59 |
| 22/09 | 02:35 | 7 | 4 | 1 | 3 | −R$26,35 | −0,58 | −R$154,55 |
| 23/09 | 06:56 | 7 | 5 | 2 | 3 | −R$29,72 | −0,68 | +R$189,94 |
| **total** | | **52** | **41** | | | **−R$195,03** | **−4,48** | |

Saídas simuladas: 26 stop, 12 trailing, 3 ainda abertas no fim do dado (marcadas a mercado).
Maior ganho +R$64,92; maior perda −R$57,96. **Nenhum dia travado teria virado dia grande.**

## Leitura

- A trava não está cortando a cauda direita. A cauda direita destes dias veio de posições que
  já estavam abertas, e a trava não fecha posição: ela só impede abrir outra.
- A pergunta tinha fundamento: a trava conta o **não realizado**, e o trailing 3R/3R deixa a
  posição oscilar mais antes de pagar. É isso que a faz disparar com frequência. O que esta
  medição mostra é que, disparando, ela barrou sinais que em média perderam.
- **Limite da amostra:** 7 dias e 41 trades. O que ela exclui é "a trava está custando muito";
  ela não prova que a trava ajuda. Mesmo corrigindo o viés médio do simulador, o contrafactual
  fica perto de −R$75: sem sinal de custo.

## O que a manchete de +R$1.070 mistura (07/09 → 24/09)

Medido no banco vivo em 24/09: 40 trades, +R$1.069,96. Por motivo de saída:

| motivo | trades | P&L |
|---|---|---|
| `trailing-gap` (o bot) | 10 | +R$1.096,76 |
| `stop-gap` (o bot) | 26 | −R$815,76 |
| `manual` (o dono pelo painel) | 4 | **+R$788,95** |

**74% do lucro do período veio de quatro fechamentos manuais.** As saídas do próprio bot somam
+R$281. O 3R/3R tem a forma que a autópsia previu (poucos ganhos grandes pagando muitas perdas
de 1R), mas o número de manchete mistura o bot e o dono, e qualquer veredito sobre o 3R/3R tem
de separar os dois. O sufixo `-gap` está em 100% das saídas por stop porque o `[P2-18]` marca
qualquer fill diferente do gatilho, não só gap grande.
