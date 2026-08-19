"""
Dashboard (UI) do paper trading ao vivo. Le estado_live.json e mostra.
Rodar:  streamlit run dashboard.py
"""
import os
import json

import pandas as pd
import streamlit as st

DIR = os.path.dirname(os.path.abspath(__file__))
ESTADO = os.path.join(DIR, "estado_live.json")

st.set_page_config(page_title="Cripto Bot - Live", layout="wide")
st.markdown('<meta http-equiv="refresh" content="5">', unsafe_allow_html=True)  # auto-refresh 5s
st.title("🤖 Cripto Bot — Paper Trading ao vivo")

if not os.path.exists(ESTADO):
    st.warning("Engine ainda nao rodou. Rode `python live_engine.py` em outro terminal.")
    st.stop()

with open(ESTADO, encoding="utf-8") as f:
    e = json.load(f)

banca0 = e["banca_inicial"]
total = e.get("equity_total", e["banca"])
lucro = total - banca0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Banca inicial", f"R$ {banca0:,.2f}")
c2.metric("Equity atual", f"R$ {total:,.2f}", f"{lucro/banca0*100:+.2f}%")
c3.metric("Caixa (realizado)", f"R$ {e['banca']:,.2f}")
c4.metric("Atualizado", str(e.get("atualizado", "-"))[11:19])

if e.get("equity_hist"):
    dfh = pd.DataFrame(e["equity_hist"], columns=["t", "equity"])
    dfh["t"] = pd.to_datetime(dfh["t"])
    st.line_chart(dfh.set_index("t")["equity"], height=260)

col_a, col_b = st.columns(2)
with col_a:
    st.subheader("Posições abertas")
    abertas = []
    for a, x in e["ativos"].items():
        if x["pos"] != 0:
            pnl = (x["pos"] * (x["preco"] / x["entry"] - 1) * 100) if x["preco"] and x["entry"] else 0
            abertas.append({"Ativo": a, "Direção": "LONG" if x["pos"] == 1 else "SHORT",
                            "Entrada": x["entry"], "Atual": x["preco"], "P&L %": round(pnl, 2)})
    st.table(pd.DataFrame(abertas) if abertas else pd.DataFrame([{"status": "nenhuma posição aberta"}]))

with col_b:
    st.subheader("Mercado")
    nome = {1: "LONG", -1: "SHORT", 0: "—"}
    st.table(pd.DataFrame([{"Ativo": a, "Preço": x["preco"], "Posição": nome[x["pos"]]}
                           for a, x in e["ativos"].items()]))

st.subheader("Últimos trades")
if e.get("trades"):
    st.dataframe(pd.DataFrame(e["trades"][::-1]), height=260, use_container_width=True)
else:
    st.write("Nenhum trade fechado ainda — o bot está observando o mercado.")

cf = e.get("cfg", {})
st.caption(f"⚙️ {cf.get('ativos')} | {cf.get('timeframe')} | risco "
           f"{cf.get('risco', 0)*100:.0f}% | paper trading (dinheiro fictício) | dados reais Binance")
