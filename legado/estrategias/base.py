"""Contrato comum de toda estrategia."""
from dataclasses import dataclass


@dataclass
class Sinal:
    """O que uma estrategia emite numa barra."""
    direcao: int = 0          # +1 long, -1 short, 0 sem sinal/flat
    stop_dist: float = 0.0    # distancia ate o stop, FRACAO do preco (ex 0.03 = 3%)
    qualidade: float = 1.0    # 0..1 confianca do setup (p/ priorizar/dimensionar)
    motivo: str = ""
    trailing: bool = True      # o motor deve arrastar o stop a favor?


class Estrategia:
    nome = "base"

    def preparar(self, df):
        """Calcula indicadores proprios. Retorna o df (e pode guardar arrays em self)."""
        return df

    def avaliar(self, df, i, pos=0) -> Sinal:
        """Avalia a barra i (pos = posicao atual: +1/-1/0).
        NUNCA pode olhar dados de i+1 em diante (look-ahead)."""
        raise NotImplementedError
