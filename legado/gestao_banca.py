"""
★ Gestor de Banca ★  - o coracao da consistencia.
Decide o TAMANHO da posicao (risco fixo por trade) e se PODE operar
(limite de perda diaria, exposicao, kill-switch). Os sinais dizem "pra onde";
o gestor diz "quanto" e "se pode".
"""
import pandas as pd


class GestorBanca:
    def __init__(self, cfg):
        self.cfg = cfg
        self.banca = cfg.banca_inicial          # equity realizado
        self.pico = cfg.banca_inicial
        self.dia_atual = None
        self.banca_inicio_dia = cfg.banca_inicial
        self.pnl_dia = 0.0
        self.travado_dia = False
        self.kill = False
        # estatisticas
        self.dias_travados = 0
        self.travas_lucro = 0

    def novo_dia_se_preciso(self, ts):
        dia = pd.Timestamp(ts).date()
        if dia != self.dia_atual:
            self.dia_atual = dia
            self.banca_inicio_dia = self.banca
            self.pnl_dia = 0.0
            self.travado_dia = False

    def pode_abrir(self, risco_aberto, n_posicoes):
        if self.kill or self.travado_dia:
            return False
        if n_posicoes >= self.cfg.max_posicoes:
            return False
        if risco_aberto + self.cfg.risco_por_trade > self.cfg.max_risco_aberto + 1e-9:
            return False
        return True

    def fracao_nocional(self, stop_dist):
        """Tamanho da posicao (fracao da banca) p/ arriscar exatamente risco_por_trade.
        Se o stop bater, a perda e ~risco_por_trade, qualquer que seja a volatilidade."""
        if stop_dist <= 0:
            return 0.0
        return min(self.cfg.alavancagem, self.cfg.risco_por_trade / stop_dist)

    def registrar_resultado(self, pnl_fracao):
        """pnl_fracao = resultado do trade como fracao da banca (ja liquido de taxa/funding)."""
        self.banca *= (1 + pnl_fracao)
        self.pico = max(self.pico, self.banca)
        self.pnl_dia = self.banca / self.banca_inicio_dia - 1

        if not self.travado_dia and self.pnl_dia <= -self.cfg.limite_perda_dia:
            self.travado_dia = True
            self.dias_travados += 1
        if (self.cfg.usar_trava_lucro and not self.travado_dia
                and self.pnl_dia >= self.cfg.meta_lucro_dia):
            self.travado_dia = True
            self.travas_lucro += 1
        if self.banca / self.pico - 1 <= -self.cfg.kill_switch_dd:
            self.kill = True
