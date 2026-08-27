# -*- coding: utf-8 -*-
"""[CX-2] Anexa o open interest aos paineis JA baixados e salva. Uma vez, nao por config."""
import pickle, time
from pesquisa import validacao as V
t0 = time.time()
dfs = pickle.load(open("_paineis.pkl", "rb"))
print(f"paineis em cache: {len(dfs)} moedas", flush=True)
com = V.paineis_com_oi(dfs)
pickle.dump(com, open("_paineis_oi.pkl", "wb"))
print(f"=== salvo _paineis_oi.pkl em {(time.time()-t0)/60:.1f} min ===", flush=True)
