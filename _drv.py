# -*- coding: utf-8 -*-
"""Driver da matriz: roda UMA politica do P1-10 por invocacao, com checkpoint.
Nao e territorio de ninguem -- e arquivo temporario da matriz, apagado depois."""
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, ".")
from pesquisa.validacao import (POLITICAS_M4, walk_forward_tendencia, baixar_paineis, FUNDING_8H)

i = int(sys.argv[1])
nome, kw = POLITICAS_M4[i]
print(f"{'='*78}\nPOLITICA {i}: {nome}   {kw}\n{'='*78}", flush=True)
dfs = baixar_paineis()
r = walk_forward_tendencia(funding_8h=FUNDING_8H, com_contraste=False,
                           saida_kw=kw, dfs=dfs, rotulo_extra=f" | saida: {nome}")
print(f"\n### FIM DA POLITICA {i}: {nome} ###", flush=True)
