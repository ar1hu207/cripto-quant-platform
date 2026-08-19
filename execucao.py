"""
Abstracao de execucao (principio de paridade backtest<->live).
Hoje: ExecucaoSimulada (backtest). Depois (Fase 5): ExecucaoCCXT (testnet/real),
implementando a mesma interface, sem o motor precisar saber a diferenca.
"""


class Execucao:
    def preco_entrada(self, preco, direcao):
        raise NotImplementedError

    def preco_saida(self, preco, direcao):
        raise NotImplementedError


class ExecucaoSimulada(Execucao):
    """Preenche no preco do candle, com slippage opcional contra o trader."""

    def __init__(self, slippage=0.0):
        self.slippage = slippage

    def preco_entrada(self, preco, direcao):
        return preco * (1 + self.slippage * direcao)

    def preco_saida(self, preco, direcao):
        return preco * (1 - self.slippage * direcao)
