"""Cotação MODELADA no minuto, nunca histórica nem executável.

Estimativa Poisson dos gols restantes. Ritmo total inferido do mercado
pré-jogo Over/Under 2.5, se disponível; força relativa pelo Match Odds 1X2.
Sem odds pré-jogo, um prior neutro de 2.6 gols/90min é usado explicitamente.
O placar até o minuto filtra o resultado, mas o resultado final nunca é usado
para precificar. A falta de histórico in-play impede aferir liquidez/spread.
"""
from __future__ import annotations

from math import exp, isfinite
import queries_nostradamus as ns

MAX_GOALS=16
FALLBACK_TOTAL_GOALS=2.6


def _price(value):
    try:
        n=float(value)
        return n if isfinite(n) and 1.01<=n<=1000 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _total_goals_from_ou(row):
    over=_price(row.get("api_over_ft_2_5"))
    under=_price(row.get("api_under_ft_2_5"))
    if not (over and under):
        return FALLBACK_TOTAL_GOALS,False
    # Normalizar probabilidades para remover overround pré-jogo.
    under_prob=(1/under)/((1/under)+(1/over))
    lo,hi=.35,7.5
    for _ in range(42):
        mid=(lo+hi)/2
        p=exp(-mid)*(1+mid+mid*mid/2)
        if p>under_prob:
            lo=mid
        else:
            hi=mid
    return (lo+hi)/2,True


def _lambdas(row,minute):
    total,from_ou=_total_goals_from_ou(row)
    home=_price(row.get("api_odd_1_ft"))
    away=_price(row.get("api_odd_2_ft"))
    if home and away:
        # Proporção entre probabilidades de vitória excluindo o empate.
        weight_home=(1/home)/((1/home)+(1/away))
        # Uma diferença moderada ajuda o favorito sem usar o placar futuro.
        # O multiplicador é um parâmetro do modelo, não uma odd observada.
        weight_home=max(.20,min(.80,.5+(.5-weight_home)*-1.1))
        source="modelo_poisson_ou_1x2" if from_ou else "modelo_poisson_1x2"
    else:
        weight_home=.5
        source="modelo_poisson_ou_neutro" if from_ou else "modelo_poisson_neutro"
    fraction=max(0.0,(90-minute)/90)
    return total*weight_home*fraction,total*(1-weight_home)*fraction,source


def _poisson(mu):
    p0=exp(-mu)
    probabilities=[p0]
    for count in range(1,MAX_GOALS):
        probabilities.append(probabilities[-1]*mu/count)
    total=sum(probabilities)
    return [p/total for p in probabilities]


def cotar(row,minute,market):
    """Retorna (odd, origem, probabilidade_do_evento).

    Para Lay, odds=1/P(evento que a aposta contrapõe). O mercado Lay já
    vem normalizado para mandante/visitante pelo módulo do Nostradamus.
    """
    if not 1<=minute<=90 or market not in ns.MERCADOS:
        return None,None,None
    home_now=row.get("gols_casa_minuto")
    away_now=row.get("gols_fora_minuto")
    if home_now is None or away_now is None:
        return None,None,None
    home_now=int(home_now)
    away_now=int(away_now)
    if home_now<0 or away_now<0:
        return None,None,None
    mu_h,mu_a,source=_lambdas(row,minute)
    probs_h=_poisson(mu_h)
    probs_a=_poisson(mu_a)
    success_prob=sum(
        p_h*p_a
        for goal_h,p_h in enumerate(probs_h)
        for goal_a,p_a in enumerate(probs_a)
        if ns._settle(market,home_now+goal_h,away_now+goal_a)
    )
    event_prob=1-success_prob if market.startswith("lay_") else success_prob
    # Preço não definível caso mercado esteja matematicamente decidido
    # ou o evento seja praticamente impossível.
    if event_prob<=.0005 or event_prob>=.9995:
        return None,"mercado_sem_cotacao",round(event_prob,6)
    fair=1/event_prob
    # Spread ilustrativo desfavorável ao apostador (não execução real).
    quoted=fair*(1.03 if market.startswith("lay_") else .97)
    odd=round(max(1.01,min(1000.0,quoted)),2)
    if not 1.01<=odd<=1000:
        return None,"mercado_sem_cotacao",round(event_prob,6)
    return odd,source,round(event_prob,6)
