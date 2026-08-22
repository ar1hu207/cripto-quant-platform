"""
Motor de PORTFOLIO multi-ativo: roda a mesma estrategia em varios ativos ao
mesmo tempo, com UMA banca compartilhada gerida pelo Gestor de Banca.
A diversificacao (quando um ativo esta lateral, outro pode estar em tendencia)
suaviza a curva de capital = mais consistencia.

Obs: a marcacao intra-trade da equity e aproximada; o retorno final e exato.
"""
import numpy as np
import pandas as pd


class _Ativo:
    """Estado e logica de UM ativo dentro do portfolio."""

    def __init__(self, nome, df, estrategia, cfg, tf_horas):
        self.nome, self.cfg, self.tf_horas = nome, cfg, tf_horas
        self.df = estrategia.preparar(df)
        self.estr = estrategia
        self.closes = self.df["close"].values
        self.ts = self.df["timestamp"].values
        self.dt = self.df["datetime"].values
        self.pos = 0
        self.entry_price = self.entry_equity = self.stop_price = self.ent_dt = None
        self.frac = 0.0
        self.bars_held = 0
        self.locked = 0
        self.alvo = 0
        self.sinal = None
        self.i_atual = 0
        self.price_atual = 0.0
        self.trades = []
        self.idx_map = []

    def _fechar(self, gestor, motivo):
        price = self.price_atual
        bruto = self.pos * (price / self.entry_price - 1) * self.frac
        funding = self.cfg.funding_8h * (self.bars_held * self.tf_horas / 8.0) * self.frac
        taxa = 2 * self.cfg.taxa_por_lado * self.frac
        pnl = bruto - funding - taxa
        gestor.registrar_resultado(pnl)
        self.trades.append({
            "ativo": self.nome, "entrada_dt": self.ent_dt, "saida_dt": self.dt[self.i_atual],
            "direcao": "LONG" if self.pos == 1 else "SHORT",
            "ret_liq_%": pnl * 100, "motivo": motivo, "taxa_paga": taxa * self.entry_equity,
        })
        self.pos, self.entry_price, self.stop_price, self.frac, self.bars_held = 0, None, None, 0.0, 0

    def passo_gestao(self, k, gestor):
        i = self.idx_map[k]
        self.i_atual = i
        price = self.closes[i]
        self.price_atual = price
        s = self.sinal = self.estr.avaliar(self.df, i, self.pos)

        if self.pos != 0:
            if s.trailing and s.stop_dist > 0:
                if self.pos == 1:
                    self.stop_price = max(self.stop_price, price * (1 - s.stop_dist))
                else:
                    self.stop_price = min(self.stop_price, price * (1 + s.stop_dist))
            bateu = (self.pos == 1 and price <= self.stop_price) or \
                    (self.pos == -1 and price >= self.stop_price)
            if bateu:
                d = self.pos
                self._fechar(gestor, "stop")
                self.locked = d
            elif s.direcao != self.pos:
                self._fechar(gestor, "regime")

        if self.locked != 0 and s.direcao != self.locked:
            self.locked = 0
        self.alvo = 0 if (self.locked != 0 and s.direcao == self.locked) else s.direcao
        if self.pos != 0:
            self.bars_held += 1

    def abrir(self, gestor):
        frac = gestor.fracao_nocional(self.sinal.stop_dist)
        if frac <= 0:
            return
        self.pos = self.alvo
        self.entry_price = self.price_atual
        self.entry_equity = gestor.banca
        self.ent_dt = self.dt[self.i_atual]
        self.stop_price = self.entry_price * (1 - self.pos * self.sinal.stop_dist)
        self.bars_held = 0
        self.frac = frac

    def unreal_dolar(self):
        if self.pos == 0:
            return 0.0
        unreal = self.pos * (self.price_atual / self.entry_price - 1) * self.frac
        unreal -= self.cfg.funding_8h * (self.bars_held * self.tf_horas / 8.0) * self.frac
        return self.entry_equity * unreal


def rodar_portfolio(dados, fabrica_estrategia, gestor, cfg, tf_horas=1.0, inicio=None, fim=None):
    ativos = [_Ativo(nome, df, fabrica_estrategia(), cfg, tf_horas) for nome, df in dados.items()]

    # alinha no tempo (timestamps comuns a todos)
    comuns = sorted(set.intersection(*[set(a.ts) for a in ativos]))
    if inicio is not None:
        ini_ms = pd.Timestamp(inicio).value // 1_000_000
        comuns = [t for t in comuns if t >= ini_ms]
    if fim is not None:
        fim_ms = pd.Timestamp(fim).value // 1_000_000
        comuns = [t for t in comuns if t <= fim_ms]
    for a in ativos:
        pos_por_ts = {t: i for i, t in enumerate(a.ts)}
        a.idx_map = [pos_por_ts[t] for t in comuns]
    ref = ativos[0]

    eq_curve = []
    for k in range(len(comuns)):
        dt_k = ref.dt[ref.idx_map[k]]
        gestor.novo_dia_se_preciso(dt_k)
        for a in ativos:                      # 1) sinal + gestao de posicao aberta
            a.passo_gestao(k, gestor)
        for a in ativos:                      # 2) abrir novas, respeitando caps GLOBAIS
            if a.pos == 0 and a.alvo != 0:
                n_pos = sum(1 for x in ativos if x.pos != 0)
                if gestor.pode_abrir(n_pos * cfg.risco_por_trade, n_pos):
                    a.abrir(gestor)
        total = gestor.banca + sum(a.unreal_dolar() for a in ativos)
        eq_curve.append((dt_k, total))

    bhs = [a.closes[a.idx_map[-1]] / a.closes[a.idx_map[0]] - 1 for a in ativos]
    return {
        "trades": [t for a in ativos for t in a.trades], "eq_curve": eq_curve,
        "banca_final": gestor.banca, "banca_inicial": cfg.banca_inicial,
        "dias_travados": gestor.dias_travados, "bh_%": float(np.mean(bhs)) * 100,
    }
