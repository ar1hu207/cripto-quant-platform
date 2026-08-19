"""
Projecao: R$1.000 inicial + R$500/mes de aporte, 12 meses, reinvestindo tudo.
Mostra a banca final em varios cenarios de retorno e separa o que e SEU deposito
do que e lucro do bot.
"""
START = 1000.0
APORTE = 500.0
MESES = 12
CENARIOS = {
    "Ruim (-20%/ano)": -0.20,
    "Conservador (+20%/ano)": 0.20,
    "Agressivo (+50%/ano)": 0.50,
    "Otimo (+80%/ano)": 0.80,
}


def projeta(ret_ano):
    r = (1 + ret_ano) ** (1 / 12) - 1
    b = START
    hist = [b]
    for _ in range(MESES):
        b = b * (1 + r) + APORTE
        hist.append(b)
    return hist


deposito = START + APORTE * MESES
print(f"Aporte R$500/mes por 12 meses | voce DEPOSITA no total: R${deposito:,.0f} "
      f"(R$1.000 + R$6.000)\n")
print(f"{'Cenario':<24}{'banca fim ano':>15}{'seu deposito':>14}{'lucro do bot':>14}")
print("-" * 67)
for nome, ra in CENARIOS.items():
    fim = projeta(ra)[-1]
    print(f"{nome:<24}{fim:>15,.0f}{deposito:>14,.0f}{fim-deposito:>+14,.0f}")

print("\nMes a mes (cenario Agressivo +50%/ano):")
for i, b in enumerate(projeta(0.50)):
    print(f"  mes {i:>2}: R$ {b:>8,.0f}")
