"""A curva do /estado amostrada por TEMPO, não por posição.

A série de equity tem 15 s nas últimas 48 h e 5 min antes (poda do [P2-11]). O `_amostrar`
pega ~125 pontos igualmente espaçados em POSIÇÃO, então ~80% deles caíam nos 2 últimos dias e
os anteriores ficavam com 1 ponto a cada ~10 h: vales somem do gráfico e o "DD atual" do painel
mede o pico numa curva sem os picos. `_amostrar_tempo` espaça os pontos no relógio.
"""
from datetime import datetime, timedelta

import api


def _serie_podada(dias=11, agora=datetime(2026, 11, 13, 9, 30)):
    """Formato real da tabela depois da poda: 5 min até 48 h atrás, 15 s daí em diante."""
    s, t, corte = [], agora - timedelta(days=dias), agora - timedelta(hours=48)
    while t <= agora:
        s.append({"ts": str(t), "banca": 10000.0, "equity_total": 10000.0 + len(s) % 97})
        t += timedelta(seconds=15 if t >= corte else 300)
    return s


def _maior_buraco_h(amostra):
    t = [datetime.fromisoformat(p["ts"][:19]) for p in amostra]
    return max((b - a).total_seconds() for a, b in zip(t, t[1:])) / 3600


def test_o_defeito_que_motivou_a_troca_existe_no_amostrar_por_posicao():
    s = _serie_podada()
    assert _maior_buraco_h(api._amostrar(s)) > 8          # medido: ~10 h sem ponto nenhum


def test_por_tempo_nao_deixa_buraco_maior_que_duas_fatias():
    s = _serie_podada()
    a = api._amostrar_tempo(s)
    fatia_h = 11 * 24 / 124
    assert _maior_buraco_h(a) <= 2 * fatia_h + 0.1       # ~4,3 h no pior caso, era ~10 h


def test_mesmo_teto_de_tamanho_do_payload():
    for dias in (1, 3, 11, 90):
        assert len(api._amostrar_tempo(_serie_podada(dias))) <= 126


def test_primeiro_e_ultimo_ponto_e_ordem_cronologica():
    s = _serie_podada()
    a = api._amostrar_tempo(s)
    assert a[0] is s[0] and a[-1] is s[-1]
    assert [p["ts"] for p in a] == sorted(p["ts"] for p in a)


def test_serie_curta_passa_intacta():
    s = _serie_podada()[:100]
    assert api._amostrar_tempo(s) == s


def test_ts_com_microssegundos_e_sem_parseiam_igual():
    s = _serie_podada(dias=3)
    s[5]["ts"] = s[5]["ts"] + ".719727"
    assert len(api._amostrar_tempo(s)) <= 126


def test_ts_ilegivel_cai_no_amostrar_antigo_em_vez_de_quebrar_o_estado():
    s = _serie_podada(dias=3)
    s[7]["ts"] = "lixo"
    assert api._amostrar_tempo(s) == api._amostrar(s)
