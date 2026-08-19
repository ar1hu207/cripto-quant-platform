"""
Meta: R$150/dia. Em que tamanho de banca isso vira realidade, e em quanto tempo
se chega la (R$1.000 inicial + aporte mensal + reinvestindo tudo).
"""
START = 1000.0
META_DIA = 150.0
DIAS_ANO = 250


def projeta(ret_ano, aporte, anos=8):
    r = (1 + ret_ano) ** (1 / 12) - 1
    banca_alvo = META_DIA / (ret_ano / DIAS_ANO)   # banca que rende R$150/dia nesse ritmo
    b = START
    atingiu = None
    serie = {}
    for m in range(1, anos * 12 + 1):
        b = b * (1 + r) + aporte
        if atingiu is None and b >= banca_alvo:
            atingiu = m
        if m % 12 == 0:
            serie[m // 12] = b
    return banca_alvo, atingiu, serie


for aporte in [500, 1000]:
    print(f"\n{'='*60}\n APORTE R${aporte}/mes (+ reinvestir tudo)\n{'='*60}")
    for ret in [0.20, 0.50, 0.70]:
        alvo, m, serie = projeta(ret, aporte)
        quando = f"{m/12:.1f} anos" if m else ">8 anos"
        print(f"\n retorno {ret*100:.0f}%/ano  ->  R$150/dia exige banca de R${alvo:,.0f}  ->  atingido em {quando}")
        print("   trajetoria: " + " | ".join(f"ano {a}: R${v:,.0f}" for a, v in serie.items() if a <= 6))
