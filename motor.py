"""
Nucleo do sistema (igual em backtest e, depois, ao vivo).
Orquestra: estrategia gera Sinal -> Gestor de Banca dimensiona/autoriza -> Execucao.
Fase 1: uma estrategia, uma posicao por vez. (Portfolio multi-estrategia vem na Fase 2.)
"""
import numpy as np

from execucao import ExecucaoSimulada


def rodar(df, estrategia, gestor, cfg, execucao=None, tf_horas=1.0, i_inicio=0, i_fim=None):
    execucao = execucao or ExecucaoSimulada(cfg.slippage)
    df = estrategia.preparar(df)   # indicadores na serie TODA (warmup correto)
    closes = df["close"].values
    ts = df["datetime"].values
    n = len(df)
    i_fim = n if i_fim is None else i_fim

    pos = 0
    entry_price = entry_equity = stop_price = None
    frac = 0.0
    bars_held = 0
    locked = 0
    trades, eq_curve = [], []

    def fechar(motivo):
        nonlocal pos, entry_price, entry_equity, stop_price, frac, bars_held
        exit_price = execucao.preco_saida(price, pos)
        bruto = pos * (exit_price / entry_price - 1) * frac
        funding = cfg.funding_8h * (bars_held * tf_horas / 8.0) * frac
        taxa = 2 * cfg.taxa_por_lado * frac
        pnl = bruto - funding - taxa
        taxa_paga = taxa * entry_equity
        gestor.registrar_resultado(pnl)
        trades.append({
            "entrada_dt": ent_dt, "saida_dt": ts[i],
            "direcao": "LONG" if pos == 1 else "SHORT",
            "entrada": float(entry_price), "saida": float(exit_price),
            "frac": frac, "ret_liq_%": pnl * 100, "motivo": motivo,
            "taxa_paga": taxa_paga,
        })
        pos, entry_price, stop_price, frac, bars_held = 0, None, None, 0.0, 0

    for i in range(i_inicio, i_fim):
        price = closes[i]
        gestor.novo_dia_se_preciso(ts[i])
        sinal = estrategia.avaliar(df, i, pos)

        # marca a mercado (banca realizada + nao realizado da posicao aberta)
        if pos != 0:
            unreal = pos * (price / entry_price - 1) * frac
            unreal -= cfg.funding_8h * (bars_held * tf_horas / 8.0) * frac
            equity_marcada = entry_equity * (1 + unreal)
        else:
            equity_marcada = gestor.banca
        eq_curve.append((ts[i], equity_marcada))

        # gestao de posicao aberta
        if pos != 0:
            if sinal.trailing and sinal.stop_dist > 0:  # arrasta o stop a favor
                if pos == 1:
                    stop_price = max(stop_price, price * (1 - sinal.stop_dist))
                else:
                    stop_price = min(stop_price, price * (1 + sinal.stop_dist))
            bateu_stop = (pos == 1 and price <= stop_price) or (pos == -1 and price >= stop_price)
            if bateu_stop:
                dir_antiga = pos
                fechar("stop")
                locked = dir_antiga
            elif sinal.direcao != pos:
                fechar("regime")

        # limpa trava quando o regime sai da direcao travada
        if locked != 0 and sinal.direcao != locked:
            locked = 0
        alvo = 0 if (locked != 0 and sinal.direcao == locked) else sinal.direcao

        # abrir nova posicao
        if pos == 0 and alvo != 0:
            risco_aberto = 0.0
            if gestor.pode_abrir(risco_aberto, n_posicoes=0):
                frac = gestor.fracao_nocional(sinal.stop_dist)
                if frac > 0:
                    pos = alvo
                    entry_price = execucao.preco_entrada(price, pos)
                    entry_equity = gestor.banca
                    ent_dt = ts[i]
                    stop_price = entry_price * (1 - pos * sinal.stop_dist)
                    bars_held = 0

        if pos != 0:
            bars_held += 1

    return {
        "trades": trades, "eq_curve": eq_curve,
        "banca_final": gestor.banca, "banca_inicial": cfg.banca_inicial,
        "dias_travados": gestor.dias_travados,
        "bh_%": (closes[i_fim - 1] / closes[i_inicio] - 1) * 100,
    }
