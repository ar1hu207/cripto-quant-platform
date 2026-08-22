"""
LEGADO -- parametros do trilho das fases 1-2. NAO e a fonte da verdade do sistema. [P2-16]

Este arquivo se declarava a fonte unica da verdade dos parametros, e era mentira desde
que a plataforma nasceu: quem manda nos parametros que rodam e `db.CONFIG_PADRAO` mais a
tabela `config` do banco, validada por catalogo no `POST /config` (ver `db.py`). Os dois
discordavam em numero, nao so em estilo -- risco por trade 0,5% aqui contra 3% la,
alavancagem 1x aqui contra 10x la.

Duas declaracoes de autoridade sobre a mesma coisa, com valores diferentes, num repositorio
onde o trabalho e feito por sessoes de agente sem memoria: e o convite a editar o arquivo
errado que o [P2-16] veio remover. Nada da plataforma viva importa este modulo -- so
`live_engine`, `monte_carlo`, `otimizar_risco`, `run_*`, `validar`, `validar_fase2` e
`validar_periodos_fase2`, todos aqui no `legado/`. Ver `legado/README.md`.
"""
from dataclasses import dataclass


@dataclass
class Config:
    # --- mercado ---
    par: str = "ETH/USDT"
    timeframe: str = "1h"     # comeca em 1h (cache pronto); plano alvo = 15m
    dias: int = 540

    # --- banca / risco (Gestor de Banca) ---
    banca_inicial: float = 1000.0
    risco_por_trade: float = 0.005    # 0,5% da banca por trade
    limite_perda_dia: float = 0.02    # -2% no dia -> trava ate amanha
    meta_lucro_dia: float = 0.03      # +3% no dia -> trava (se usar_trava_lucro)
    usar_trava_lucro: bool = False    # testaremos com e sem
    max_posicoes: int = 2             # (relevante a partir do portfolio, Fase 2)
    max_risco_aberto: float = 0.015   # soma do risco aberto <= 1,5%
    kill_switch_dd: float = 0.20      # drawdown total -20% -> para tudo
    alavancagem: float = 1.0          # 1x (dados mostraram que mais piora)

    # --- custos ---
    taxa_por_lado: float = 0.0002     # maker 0,02% (ida+volta = 0,04%)
    funding_8h: float = 0.0001
    slippage: float = 0.0

    # --- estrategia trend ---
    ema_rapida: int = 20
    ema_lenta: int = 50
    adx_periodo: int = 14
    adx_min: float = 25.0
    atr_periodo: int = 14
    trail_atr: float = 3.0

    # --- estrategia mean-reversion ---
    bb_periodo: int = 20
    bb_k: float = 2.0
    rsi_periodo: int = 14
    rsi_baixo: float = 35.0
    rsi_alto: float = 65.0
    mr_stop_atr: float = 2.5
    mr_adx_max: float = 20.0    # so opera mean-rev quando ADX < isso (mercado lateral)


PADRAO = Config()
