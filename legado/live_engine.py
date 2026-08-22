"""
Engine de PAPER TRADING ao vivo: roda com dados REAIS da Binance em tempo real,
dinheiro FICTICIO. Aplica trend + Gestor de Banca. Grava o estado em
estado_live.json (lido pelo dashboard). Sobrevive a reinicio (recarrega o estado).

Rodar:  python live_engine.py          (loop continuo)
        python live_engine.py --once   (um ciclo so, p/ teste)
"""
import os
import sys
import json
import time
from dataclasses import replace

import ccxt
import pandas as pd

from config import PADRAO
from estrategias.trend import TrendFollowing
from gestao_banca import GestorBanca

# ---------------- CONFIG ----------------
ATIVOS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TIMEFRAME = "15m"
POLL_SEG = 30
RISCO = 0.03          # agressivo
BANCA0 = 1000.0
DIR = os.path.dirname(os.path.abspath(__file__))
ESTADO = os.path.join(DIR, "estado_live.json")

cfg = replace(PADRAO, timeframe=TIMEFRAME, max_posicoes=len(ATIVOS),
              risco_por_trade=RISCO, banca_inicial=BANCA0, alavancagem=3.0,
              max_risco_aberto=RISCO * len(ATIVOS) + 0.001)
ex = ccxt.binance({"enableRateLimit": True})
TF_H = ex.parse_timeframe(TIMEFRAME) / 3600.0


def _novo_ativo():
    return dict(pos=0, entry=None, entry_eq=None, stop=None, frac=0.0,
                bars=0, locked=0, ent_dt=None, last_ts=None, preco=None)


class LiveEngine:
    def __init__(self):
        self.gestor = GestorBanca(cfg)
        self.ativos = {a: _novo_ativo() for a in ATIVOS}
        self.trades = []
        self.equity_hist = []
        self._carregar()

    def _carregar(self):
        if not os.path.exists(ESTADO):
            return
        try:
            with open(ESTADO, encoding="utf-8") as f:
                e = json.load(f)
            g = self.gestor
            g.banca = e["banca"]; g.pico = e["pico"]
            g.banca_inicio_dia = e["banca_inicio_dia"]; g.pnl_dia = e["pnl_dia"]
            g.travado_dia = e["travado_dia"]; g.kill = e["kill"]; g.dias_travados = e["dias_travados"]
            g.dia_atual = pd.Timestamp(e["dia"]).date() if e.get("dia") else None
            for a in ATIVOS:
                if a in e["ativos"]:
                    self.ativos[a] = e["ativos"][a]
            self.trades = e.get("trades", [])
            self.equity_hist = e.get("equity_hist", [])
            print("estado anterior recarregado.")
        except Exception as ex_:
            print("aviso: estado nao carregado:", ex_)

    def _salvar(self, total):
        g = self.gestor
        e = dict(banca=g.banca, banca_inicial=cfg.banca_inicial, pico=g.pico,
                 banca_inicio_dia=g.banca_inicio_dia, pnl_dia=g.pnl_dia,
                 travado_dia=g.travado_dia, kill=g.kill, dias_travados=g.dias_travados,
                 dia=str(g.dia_atual) if g.dia_atual else None, ativos=self.ativos,
                 trades=self.trades[-50:], equity_hist=self.equity_hist[-2000:],
                 equity_total=round(total, 2), atualizado=str(pd.Timestamp.now()),
                 cfg=dict(risco=RISCO, timeframe=TIMEFRAME, ativos=ATIVOS))
        with open(ESTADO, "w", encoding="utf-8") as f:
            json.dump(e, f, indent=2, default=str)

    def _unreal(self, a):
        st = self.ativos[a]
        if st["pos"] == 0 or not st["preco"] or not st["entry"]:
            return 0.0
        return st["entry_eq"] * st["pos"] * (st["preco"] / st["entry"] - 1) * st["frac"]

    def _fechar(self, a, preco, motivo, dt):
        st = self.ativos[a]
        bruto = st["pos"] * (preco / st["entry"] - 1) * st["frac"]
        taxa = 2 * cfg.taxa_por_lado * st["frac"]
        funding = cfg.funding_8h * (st["bars"] * TF_H / 8.0) * st["frac"]
        pnl = bruto - taxa - funding
        self.gestor.registrar_resultado(pnl)
        self.trades.append(dict(ativo=a, dir="LONG" if st["pos"] == 1 else "SHORT",
                                entrada=round(st["entry"], 4), saida=round(preco, 4),
                                ret_pct=round(pnl * 100, 2), motivo=motivo, dt=str(dt)))
        st.update(pos=0, entry=None, stop=None, frac=0.0, bars=0)

    def _processar(self, a, estr, df, i, preco):
        st = self.ativos[a]
        s = estr.avaliar(df, i, st["pos"])
        if st["pos"] != 0:
            if s.trailing and s.stop_dist > 0:
                if st["pos"] == 1:
                    st["stop"] = max(st["stop"], preco * (1 - s.stop_dist))
                else:
                    st["stop"] = min(st["stop"], preco * (1 + s.stop_dist))
            bateu = (st["pos"] == 1 and preco <= st["stop"]) or (st["pos"] == -1 and preco >= st["stop"])
            if bateu:
                d = st["pos"]; self._fechar(a, preco, "stop", df["datetime"].iloc[i]); st["locked"] = d
            elif s.direcao != st["pos"]:
                self._fechar(a, preco, "regime", df["datetime"].iloc[i])
        if st["locked"] != 0 and s.direcao != st["locked"]:
            st["locked"] = 0
        alvo = 0 if (st["locked"] != 0 and s.direcao == st["locked"]) else s.direcao
        if st["pos"] == 0 and alvo != 0:
            n_pos = sum(1 for x in self.ativos.values() if x["pos"] != 0)
            if self.gestor.pode_abrir(n_pos * cfg.risco_por_trade, n_pos):
                frac = self.gestor.fracao_nocional(s.stop_dist)
                if frac > 0:
                    st.update(pos=alvo, entry=preco, entry_eq=self.gestor.banca,
                              stop=preco * (1 - alvo * s.stop_dist), bars=0,
                              ent_dt=str(df["datetime"].iloc[i]), frac=frac)

    def ciclo(self):
        for a in ATIVOS:
            try:
                raw = ex.fetch_ohlcv(a, timeframe=TIMEFRAME, limit=300)
            except Exception as ex_:
                print(f"falha fetch {a}: {ex_}"); continue
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
            estr = TrendFollowing(cfg); df = estr.preparar(df)
            i = len(df) - 2  # ultima barra FECHADA (a -1 ainda esta se formando)
            if i < 1:
                continue
            st = self.ativos[a]
            st["preco"] = float(df["close"].iloc[-1])
            ts_bar = int(df["timestamp"].iloc[i])
            if st["last_ts"] != ts_bar:  # barra nova fechada -> decide
                self.gestor.novo_dia_se_preciso(df["datetime"].iloc[i])
                self._processar(a, estr, df, i, float(df["close"].iloc[i]))
                st["last_ts"] = ts_bar
                if st["pos"] != 0:
                    st["bars"] += 1
        total = self.gestor.banca + sum(self._unreal(a) for a in ATIVOS)
        self.equity_hist.append([str(pd.Timestamp.now()), round(total, 2)])
        self._salvar(total)
        return total

    def run(self, once=False):
        print(f"ENGINE AO VIVO | {ATIVOS} | {TIMEFRAME} | risco {RISCO*100:.0f}% | "
              f"banca ficticia R${cfg.banca_inicial:.0f} | poll {POLL_SEG}s")
        while True:
            total = self.ciclo()
            abertas = [a for a, x in self.ativos.items() if x["pos"] != 0]
            print(f"[{pd.Timestamp.now().strftime('%H:%M:%S')}] equity R$ {total:,.2f} | "
                  f"caixa R$ {self.gestor.banca:,.2f} | posicoes: {abertas or 'nenhuma'}")
            if once:
                break
            time.sleep(POLL_SEG)


if __name__ == "__main__":
    LiveEngine().run(once="--once" in sys.argv)
