"""Cotações ILUSTRATIVAS de goleada a partir dos 16 Correct Scores (0x0 a 3x3).

Não é preço Betfair: estima médias de gols por Poisson independente
usando razões entre odds adjacentes (reduz o efeito de uma margem
multiplicativa da casa). Projeta também 4+ gols, ausentes na grade.
Para o spread sintético usa um tick da escada Betfair CLASSIC.
Não há garantia de disponibilidade pré-jogo nem liquidez.
"""
from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache
from math import exp, isfinite
from statistics import median


# Valores permitidos pela escada CLASSIC do Exchange (em centavos).
_BANDS = (
    (101, 200, 1),
    (202, 300, 2),
    (305, 400, 5),
    (410, 600, 10),
    (620, 1000, 20),
    (1050, 2000, 50),
    (2100, 3000, 100),
    (3200, 5000, 200),
    (5500, 10000, 500),
    (11000, 100000, 1000),
)
_LADDER_CENTS = tuple(
    cents for lo, hi, step in _BANDS
    for cents in range(lo, hi + 1, step)
)
SCORE_KEYS = tuple((home, away) for home in range(4) for away in range(4))
MODEL = "poisson_correct_score_0a3_v1"


def _probabilities(lam: float) -> tuple[float, ...]:
    # Até 30 gols é numericamente suficiente no domínio do modelo (lam <= 6).
    values = [exp(-lam)]
    for goals in range(1, 31):
        values.append(values[-1] * lam / goals)
    return tuple(values)


def _classic_price_pair(probability: float) -> tuple[float | None, float | None]:
    if not isfinite(probability) or probability <= 0:
        return None, None
    fair = 1 / probability
    # Odds acima de 1000 não podem ser negociadas na escada CLASSIC.
    if fair < 1.01 or fair >= 1000:
        return None, None
    index = bisect_right(_LADDER_CENTS, fair * 100 + 1e-8) - 1
    if index < 0 or index + 1 >= len(_LADDER_CENTS):
        return None, None
    return _LADDER_CENTS[index] / 100, _LADDER_CENTS[index + 1] / 100


@lru_cache(maxsize=16384)
def estimate_goleada_quotes(scores: tuple[float | None, ...]) -> dict | None:
    """Recebe odds CS 0x0, 0x1,...,3x3 e devolve quatro preços simulados.

    Exige pelo menos 12 placares e 6 pares adjacentes por direção.
    Usa medianas de lambda=i*odd_anterior/odd_atual para reduzir
    distorções de margens locais em um mercado de resultados exatos.
    """
    if len(scores) != 16:
        return None
    valid = []
    for item in scores:
        try:
            price = float(item) if item is not None else None
        except (TypeError, ValueError, OverflowError):
            price = None
        valid.append(price if price is not None and isfinite(price) and price > 1 else None)
    if sum(v is not None for v in valid) < 12:
        return None
    by_score = dict(zip(SCORE_KEYS, valid))
    home_estimators = []
    away_estimators = []
    for home in range(4):
        for away in range(4):
            current = by_score[(home, away)]
            if current is None:
                continue
            if home:
                previous = by_score[(home - 1, away)]
                if previous is not None:
                    home_estimators.append(home * previous / current)
            if away:
                previous = by_score[(home, away - 1)]
                if previous is not None:
                    away_estimators.append(away * previous / current)
    if len(home_estimators) < 6 or len(away_estimators) < 6:
        return None
    lam_home = median(home_estimators)
    lam_away = median(away_estimators)
    if not (0.1 <= lam_home <= 6 and 0.1 <= lam_away <= 6):
        return None
    home_pmf = _probabilities(lam_home)
    away_pmf = _probabilities(lam_away)
    home_cumulative = []
    away_cumulative = []
    sum_home = sum_away = 0.0
    for home, away in zip(home_pmf, away_pmf):
        sum_home += home
        sum_away += away
        home_cumulative.append(sum_home)
        away_cumulative.append(sum_away)
    p_home = sum(
        home_pmf[goals] * away_cumulative[goals - 3]
        for goals in range(3, len(home_pmf))
    )
    p_away = sum(
        away_pmf[goals] * home_cumulative[goals - 3]
        for goals in range(3, len(away_pmf))
    )
    back_home, lay_home = _classic_price_pair(p_home)
    back_away, lay_away = _classic_price_pair(p_away)
    return {
        "back_goleada_mandante": back_home,
        "lay_goleada_mandante": lay_home,
        "back_goleada_visitante": back_away,
        "lay_goleada_visitante": lay_away,
        "probabilidade_mandante": round(p_home, 6),
        "probabilidade_visitante": round(p_away, 6),
        "gols_esperados_mandante": round(lam_home, 3),
        "gols_esperados_visitante": round(lam_away, 3),
        "modelo": MODEL,
        "placares_disponiveis": sum(v is not None for v in valid),
    }
