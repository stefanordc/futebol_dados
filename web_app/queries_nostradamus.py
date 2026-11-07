"""Nostradamus: backtest cronológico sem vazamento de jogos futuros.

Só usa dados de partidas CONCLUÍDAS antes da data de cada entrada.
As condições permitem selecionar mandante ou visitante e comparar com valor fixo ou indicador de outra equipe.
Odds registradas após o início (data do jogo) nunca são consideradas históricas.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from itertools import groupby
from math import isfinite
from db import fetch_all
from goleada_correct_score import SCORE_KEYS, estimate_goleada_quotes

METRICAS = {
    "pontos_jogo": "Pontos por jogo",
    "aproveitamento": "Aproveitamento (%)",
    "gols_feitos": "Gols marcados por jogo",
    "gols_sofridos": "Gols sofridos por jogo",
    "saldo": "Saldo médio por jogo",
    "vitorias_pct": "Vitórias (%)",
    "clean_sheets_pct": "Jogos sem sofrer gols (%)",
    "xg": "xG por jogo",
    "xgot": "xGOT por jogo",
    "chutes": "Finalizações por jogo",
    "chutes_certos": "Finalizações certas por jogo",
    "passes_certos": "Passes certos por jogo",
    "passes_por_gol": "Passes certos para marcar 1 gol",
    "chutes_por_gol": "Finalizações para marcar 1 gol",
    "xg_conversao": "Conversão de xG em gols (%)",
    "posse": "Posse de bola (%)",
    "grandes_chances": "Grandes chances por jogo",
    "escanteios": "Escanteios por jogo",
    "dribles_certos": "Dribles certos por jogo",
    "faltas": "Faltas cometidas por jogo",
    "duelos_aereos": "Duelos aéreos ganhos por jogo",
    "km": "Dados físicos · Distância percorrida (km/jogo)",
    "sprints": "Dados físicos · Sprints por jogo",
    "km_diff": "Dados físicos · Diferença de km por jogo",
    "sprints_diff": "Dados físicos · Diferença de sprints por jogo",
}
COMPARADORES = {"gt":">","ge":">=","lt":"<","le":"<=","eq":"=","ne":"!="}
MERCADOS = {
    "back_favorito":"Back favorito",
    "lay_favorito":"Lay favorito",
    "back_zebra":"Back zebra",
    "lay_zebra":"Lay zebra",
    "back_mandante":"Back mandante (estratégia antiga)",
    "lay_mandante":"Lay mandante (estratégia antiga)",
    "back_visitante":"Back visitante (estratégia antiga)",
    "lay_visitante":"Lay visitante (estratégia antiga)",
    "back_empate":"Back empate",
    "lay_empate":"Lay empate",
    "over_05":"Over 0,5",
    "over_15":"Over 1,5",
    "over_25":"Over 2,5",
    "over_35":"Over 3,5",
    "under_25":"Under 2,5",
    "under_35":"Under 3,5",
    "ambos_marcam":"Ambos marcam",
    "ambos_nao":"Ambos não marcam",
    "back_goleada_mandante":"Back goleada mandante (modelo Correct Score)",
    "back_goleada_visitante":"Back goleada visitante (modelo Correct Score)",
    "lay_goleada_favorito":"Lay goleada favorito",
    "lay_goleada_zebra":"Lay goleada zebra",
    "lay_goleada_mandante":"Lay goleada mandante (estratégia antiga)",
    "lay_goleada_visitante":"Lay goleada visitante (estratégia antiga)",
    "lay_1x0":"Lay placar 1x0",
    "lay_0x1":"Lay placar 0x1",
}

RAW = """
SELECT j.id,j.data,j.temporada,j.campeonato_id,c.nome AS campeonato,
       j.casa_id,j.fora_id,h.clube AS mandante,v.clube AS visitante,
       j.gols_casa,j.gols_fora,
       oh.odd_casa,oh.odd_empate,oh.odd_fora,oh.criado_em AS odd_criada,
       oa.odd_1_ft AS api_odd_1_ft,
       oa.odd_x_ft AS api_odd_x_ft,
       oa.odd_2_ft AS api_odd_2_ft,
       oa.over_ft_0_5 AS api_over_ft_0_5,
       oa.over_ft_1_5 AS api_over_ft_1_5,
       oa.over_ft_2_5 AS api_over_ft_2_5,
       oa.over_ft_3_5 AS api_over_ft_3_5,
       oa.under_ft_2_5 AS api_under_ft_2_5,
       oa.under_ft_3_5 AS api_under_ft_3_5,
       oa.btts_yes AS api_btts_yes,
       oa.btts_no AS api_btts_no,
       oa.lay_odd_1_ft AS api_lay_odd_1_ft,
       oa.lay_odd_x_ft AS api_lay_odd_x_ft,
       oa.lay_odd_2_ft AS api_lay_odd_2_ft,
       oa.lay_cs_1_0 AS api_lay_cs_1_0,
       oa.lay_cs_0_1 AS api_lay_cs_0_1,
       oa.bookie_odd_1_ft AS api_bookie_odd_1_ft,
       oa.bookie_odd_x_ft AS api_bookie_odd_x_ft,
       oa.bookie_odd_2_ft AS api_bookie_odd_2_ft,
       oa.bookie_over_ft_0_5 AS api_bookie_over_ft_0_5,
       oa.bookie_over_ft_1_5 AS api_bookie_over_ft_1_5,
       oa.bookie_over_ft_2_5 AS api_bookie_over_ft_2_5,
       oa.bookie_over_ft_3_5 AS api_bookie_over_ft_3_5,
       oa.bookie_under_ft_2_5 AS api_bookie_under_ft_2_5,
       oa.bookie_under_ft_3_5 AS api_bookie_under_ft_3_5,
       oa.bookie_btts_yes AS api_bookie_btts_yes,
       oa.bookie_btts_no AS api_bookie_btts_no,
       oa.bookie_cs_1_0 AS api_bookie_cs_1_0,
       oa.bookie_cs_0_1 AS api_bookie_cs_0_1,
       oa.cs_0_0 AS api_cs_0_0,
       oa.cs_0_1 AS api_cs_0_1,
       oa.cs_0_2 AS api_cs_0_2,
       oa.cs_0_3 AS api_cs_0_3,
       oa.cs_1_0 AS api_cs_1_0,
       oa.cs_1_1 AS api_cs_1_1,
       oa.cs_1_2 AS api_cs_1_2,
       oa.cs_1_3 AS api_cs_1_3,
       oa.cs_2_0 AS api_cs_2_0,
       oa.cs_2_1 AS api_cs_2_1,
       oa.cs_2_2 AS api_cs_2_2,
       oa.cs_2_3 AS api_cs_2_3,
       oa.cs_3_0 AS api_cs_3_0,
       oa.cs_3_1 AS api_cs_3_1,
       oa.cs_3_2 AS api_cs_3_2,
       oa.cs_3_3 AS api_cs_3_3,
       ec.xg AS home_xg,ea.xg AS away_xg,
       ec.xgot AS home_xgot,ea.xgot AS away_xgot,
       ec.total_chutes AS home_chutes,ea.total_chutes AS away_chutes,
       ec.chutes_certos AS home_chutes_certos,ea.chutes_certos AS away_chutes_certos,
       ec.passes_certos AS home_passes_certos,ea.passes_certos AS away_passes_certos,
       ec.posse_bola AS home_posse,ea.posse_bola AS away_posse,
       ec.grandes_chances AS home_grandes_chances,ea.grandes_chances AS away_grandes_chances,
       ec.escanteios AS home_escanteios,ea.escanteios AS away_escanteios,
       ec.dribles_certos AS home_dribles_certos,ea.dribles_certos AS away_dribles_certos,
       ec.faltas_cometidas AS home_faltas,ea.faltas_cometidas AS away_faltas,
       ec.disputas_aereas_ganhas AS home_duelos_aereos,ea.disputas_aereas_ganhas AS away_duelos_aereos,
       fis.home_km,fis.away_km,fis.home_sprints,fis.away_sprints
FROM jogos j
JOIN campeonatos c ON c.id=j.campeonato_id
JOIN clubes h ON h.id=j.casa_id
JOIN clubes v ON v.id=j.fora_id
LEFT JOIN estatisticas ec ON ec.jogo_id=j.id AND ec.clube_id=j.casa_id AND ec.periodo='Completo'
LEFT JOIN estatisticas ea ON ea.jogo_id=j.id AND ea.clube_id=j.fora_id AND ea.periodo='Completo'
LEFT JOIN odds_fotmob oh ON oh.jogo_id=j.id
-- Cotações da tabela odds, pareadas sem confiar em semelhança aproximada.
-- Exige identificadores de AMBOS os clubes, data, liga e temporada.
-- Se houver mais de uma linha correspondente, nenhuma odd é atribuída.
LEFT JOIN LATERAL (
 SELECT MAX(o.odd_1_ft) AS odd_1_ft,
        MAX(o.odd_x_ft) AS odd_x_ft,
        MAX(o.odd_2_ft) AS odd_2_ft,
        MAX(o.over_ft_0_5) AS over_ft_0_5,
        MAX(o.over_ft_1_5) AS over_ft_1_5,
        MAX(o.over_ft_2_5) AS over_ft_2_5,
        MAX(o.over_ft_3_5) AS over_ft_3_5,
        MAX(o.under_ft_2_5) AS under_ft_2_5,
         MAX(o.under_ft_3_5) AS under_ft_3_5,
        MAX(o.btts_yes) AS btts_yes,
        MAX(o.btts_no) AS btts_no,
        MAX(o.lay_odd_1_ft) AS lay_odd_1_ft,
        MAX(o.lay_odd_x_ft) AS lay_odd_x_ft,
        MAX(o.lay_odd_2_ft) AS lay_odd_2_ft,
        MAX(o.lay_cs_1_0) AS lay_cs_1_0,
        MAX(o.lay_cs_0_1) AS lay_cs_0_1,
        MAX(o.bookie_odd_1_ft) AS bookie_odd_1_ft,
        MAX(o.bookie_odd_x_ft) AS bookie_odd_x_ft,
        MAX(o.bookie_odd_2_ft) AS bookie_odd_2_ft,
        MAX(o.bookie_over_ft_0_5) AS bookie_over_ft_0_5,
        MAX(o.bookie_over_ft_1_5) AS bookie_over_ft_1_5,
        MAX(o.bookie_over_ft_2_5) AS bookie_over_ft_2_5,
        MAX(o.bookie_over_ft_3_5) AS bookie_over_ft_3_5,
        MAX(o.bookie_under_ft_2_5) AS bookie_under_ft_2_5,
         MAX(o.bookie_under_ft_3_5) AS bookie_under_ft_3_5,
        MAX(o.bookie_btts_yes) AS bookie_btts_yes,
        MAX(o.bookie_btts_no) AS bookie_btts_no,
        MAX(o.bookie_cs_1_0) AS bookie_cs_1_0,
        MAX(o.bookie_cs_0_1) AS bookie_cs_0_1,
        MAX(o.cs_0_0) AS cs_0_0,
        MAX(o.cs_0_1) AS cs_0_1,
        MAX(o.cs_0_2) AS cs_0_2,
        MAX(o.cs_0_3) AS cs_0_3,
        MAX(o.cs_1_0) AS cs_1_0,
        MAX(o.cs_1_1) AS cs_1_1,
        MAX(o.cs_1_2) AS cs_1_2,
        MAX(o.cs_1_3) AS cs_1_3,
        MAX(o.cs_2_0) AS cs_2_0,
        MAX(o.cs_2_1) AS cs_2_1,
        MAX(o.cs_2_2) AS cs_2_2,
        MAX(o.cs_2_3) AS cs_2_3,
        MAX(o.cs_3_0) AS cs_3_0,
        MAX(o.cs_3_1) AS cs_3_1,
        MAX(o.cs_3_2) AS cs_3_2,
        MAX(o.cs_3_3) AS cs_3_3
 FROM public.odds o
 WHERE o.mandante_id=j.casa_id AND o.visitante_id=j.fora_id
   AND o.data_jogo::date=j.data
   AND REPLACE(o.temporada,'-','/')=j.temporada
   AND LOWER(BTRIM(o.campeonato))=LOWER(BTRIM(c.nome))
 HAVING COUNT(*)=1
) oa ON TRUE
-- Os IDs físicos são SofaScore. Para partidas sem ID SofaScore
-- (ex.: Brasileiro e Bundesliga FotMob), só aceitamos pareamento
-- único de data, temporada, liga, país e AMBOS os clubes.
LEFT JOIN paises p ON p.id=c.pais_id
LEFT JOIN LATERAL (
 SELECT MAX(NULLIF(fh.distancia_percorrida,0)) AS home_km,
        MAX(NULLIF(fa.distancia_percorrida,0)) AS away_km,
        MAX(NULLIF(fh.sprints,0)) AS home_sprints,
        MAX(NULLIF(fa.sprints,0)) AS away_sprints
 FROM dados_fisicos fh
 JOIN dados_fisicos fa ON fa.id_jogo=fh.id_jogo
   AND fa.id_campeonato=fh.id_campeonato
   AND fa.temporada=fh.temporada AND fa.data=fh.data
 WHERE fh.data=j.data AND fh.temporada=j.temporada
   AND (j.id_sofascore IS NULL OR fh.id_jogo=j.id_sofascore)
   AND LOWER(TRIM(fh.campeonato))=LOWER(TRIM(
       CASE c.nome WHEN 'LaLiga' THEN 'Espanhol'
                   WHEN 'Serie A' THEN 'Italiano'
                   WHEN 'Premier League' THEN 'Inglês'
                   WHEN 'Bundesliga' THEN 'Alemão'
                   ELSE c.nome END))
   AND LOWER(TRIM(fh.pais))=LOWER(TRIM(p.nome))
   AND (
      EXISTS (
       SELECT 1 FROM clubes_fontes hsrc
       WHERE hsrc.fonte='sofascore' AND hsrc.id_externo=fh.id_clube::text
         AND hsrc.clube_id=j.casa_id
      )
      OR (
       NOT EXISTS (
         SELECT 1 FROM clubes_fontes hsrc
         WHERE hsrc.fonte='sofascore' AND hsrc.id_externo=fh.id_clube::text
       )
       AND LOWER(TRIM(fh.clube))=LOWER(TRIM(h.clube))
       AND (SELECT COUNT(*) FROM clubes hname
            WHERE LOWER(TRIM(hname.clube))=LOWER(TRIM(fh.clube)))=1
      )
   )
   AND (
      EXISTS (
       SELECT 1 FROM clubes_fontes asrc
       WHERE asrc.fonte='sofascore' AND asrc.id_externo=fa.id_clube::text
         AND asrc.clube_id=j.fora_id
      )
      OR (
       NOT EXISTS (
         SELECT 1 FROM clubes_fontes asrc
         WHERE asrc.fonte='sofascore' AND asrc.id_externo=fa.id_clube::text
       )
       AND LOWER(TRIM(fa.clube))=LOWER(TRIM(v.clube))
       AND (SELECT COUNT(*) FROM clubes aname
            WHERE LOWER(TRIM(aname.clube))=LOWER(TRIM(fa.clube)))=1
      )
   )
 -- Se mais de um jogo da origem puder representar a partida,
 -- não inventamos um pareamento: todas as medidas ficam nulas.
 HAVING COUNT(*)=1
) fis ON TRUE
WHERE j.data<=%s AND j.data<CURRENT_DATE
  AND j.gols_casa IS NOT NULL AND j.gols_fora IS NOT NULL
  {competition}
ORDER BY j.data ASC,j.id ASC
LIMIT 20000
"""

def _n(v):
    try:
        x=float(v)
        return x if isfinite(x) else None
    except (TypeError,ValueError,OverflowError):
        return None

def _safe_div(a,b):
    return a/b if a is not None and b is not None and b>0 else None

# Histórico comum ao Nostradamus e ao Galileu, sempre de jogos já finalizados.
HISTORICAL_FIELDS=("xg","xgot","chutes","chutes_certos","passes_certos","posse",
                   "grandes_chances","escanteios","dribles_certos","faltas","duelos_aereos")

def _history_item(game,role):
    if role not in ("home","away"):
        raise ValueError("Mando inválido para o histórico.")
    other="away" if role=="home" else "home"
    own_home=role=="home"
    item={
        "gf":int(game["gols_casa"] if own_home else game["gols_fora"]),
        "ga":int(game["gols_fora"] if own_home else game["gols_casa"]),
    }
    for field in HISTORICAL_FIELDS:
        item[field]=game.get(role+"_"+field)
    for field in ("km","sprints"):
        measured=_n(game.get(role+"_"+field))
        opponent=_n(game.get(other+"_"+field))
        # Zero ou negativo indicam registro físico indisponível/incorreto.
        measured=measured if measured is not None and measured>0 else None
        opponent=opponent if opponent is not None and opponent>0 else None
        item[field]=measured
        item[field+"_diff"]=measured-opponent if measured is not None and opponent is not None else None
    return item

def _stats(history,amount):
    # O recorte 10/20 indica um LIMITE máximo, não uma obrigação de ter
    # exatamente N jogos já concluídos naquela temporada. Isso permite
    # ligas de início em agosto também serem avaliadas em janeiro.
    # Exige no mínimo 5 partidas anteriores para evitar amostra minúscula.
    selected=history[-amount:] if amount is not None else history
    if len(selected)<5:
        return None
    n=len(selected)
    goals=[x["gf"] for x in selected]
    conceded=[x["ga"] for x in selected]
    points=[3 if x["gf"]>x["ga"] else 1 if x["gf"]==x["ga"] else 0 for x in selected]
    out={
       "pontos_jogo":sum(points)/n,
       "aproveitamento":100*sum(points)/(3*n),
       "gols_feitos":sum(goals)/n,
       "gols_sofridos":sum(conceded)/n,
       "saldo":(sum(goals)-sum(conceded))/n,
       "vitorias_pct":100*sum(p==3 for p in points)/n,
       "clean_sheets_pct":100*sum(x==0 for x in conceded)/n,
    }
    fields=("xg","xgot","chutes","chutes_certos","passes_certos","posse",
            "grandes_chances","escanteios","dribles_certos","faltas","duelos_aereos",
            "km","sprints","km_diff","sprints_diff")
    for key in fields:
        eligible=[r for r in selected if _n(r.get(key)) is not None]
        # Require reasonable statistical coverage for this feature.
        out[key]=sum(_n(x[key]) for x in eligible)/len(eligible) if len(eligible)>=max(3,int(.6*n+.99999)) else None
    # Aggregate numerator and goals on precisely the same historical matches.
    for feature,outkey in (("passes_certos","passes_por_gol"),("chutes","chutes_por_gol")):
        eligible=[r for r in selected if _n(r.get(feature)) is not None]
        denominator=sum(r["gf"] for r in eligible)
        out[outkey]=(sum(_n(r[feature]) for r in eligible)/denominator) if denominator>0 and len(eligible)>=max(3,int(.6*n+.99999)) else None
    eligible=[r for r in selected if _n(r.get("xg")) is not None]
    total_xg=sum(_n(r["xg"]) for r in eligible)
    out["xg_conversao"]=(100*sum(r["gf"] for r in eligible)/total_xg
                          if total_xg>0 and len(eligible)>=max(3,int(.6*n+.99999)) else None)
    return out

ODD_FILTER_MARKETS = {
    "back_favorito": "Match Odds · Back favorito",
    "back_zebra": "Match Odds · Back zebra",
    "back_empate": "Match Odds · Back empate",
    "over_05": "Over 0,5",
    "over_15": "Over 1,5",
    "over_25": "Over 2,5",
    "over_35": "Over 3,5",
    "under_25": "Under 2,5",
    "under_35": "Under 3,5",
    "ambos_marcam": "Ambos marcam · Sim",
    "ambos_nao": "Ambos marcam · Não",
    "lay_favorito": "Match Odds · Lay favorito (estimado)",
    "lay_zebra": "Match Odds · Lay zebra (estimado)",
    "lay_empate": "Match Odds · Lay empate (estimado)",
    "lay_1x0": "Correct Score · Lay 1x0 (estimado)",
    "lay_0x1": "Correct Score · Lay 0x1 (estimado)",
    "back_goleada_mandante":"Goleada mandante · Back (modelo CS)",
    "back_goleada_visitante":"Goleada visitante · Back (modelo CS)",
    "lay_goleada_mandante":"Goleada mandante · Lay (modelo CS)",
    "lay_goleada_visitante":"Goleada visitante · Lay (modelo CS)",
    "lay_goleada_favorito":"Goleada favorito · Lay (modelo CS)",
    "lay_goleada_zebra":"Goleada zebra · Lay (modelo CS)",
}

def _odd_limit(value, label):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError(label + " inválida.")
    price = _n(value)
    if price is None or not 1.01 <= price <= 1000:
        raise ValueError(label + " deve estar entre 1,01 e 1000.")
    return price


def _valid_conditions(conditions):
    """Normaliza condições novas e antigas, sem execução dinâmica de expressões.

    Novo formato: lado, metrica, comparador, referencia, metrica_ref, valor.
      - referencia='valor': compara a métrica com valor fixo.
      - referencia='adversario': compara mesmo indicador do time oposto, sem ajuste.\n      - referencia='mandante'/'visitante': legado, outra métrica + ajuste.
      - lado='favorito'/'zebra': calculado pelas odds Match Odds 1 e 2 da partida.
    Formato legado: metrica, comparador, margem => mandante x visitante + margem.
    """
    if not isinstance(conditions,list) or not 1<=len(conditions)<=10:
        raise ValueError("Escolha entre 1 e 10 condições.")
    parsed=[]
    for c in conditions:
        if not isinstance(c, dict):
            raise ValueError("Critério inválido.")
        tipo=c.get("tipo","indicador")
        if tipo=="odd":
            market=c.get("mercado")
            if market not in ODD_FILTER_MARKETS:
                raise ValueError("Selecione o mercado da odd.")
            min_odd=_odd_limit(c.get("odd_min"),"Odd mínima")
            max_odd=_odd_limit(c.get("odd_max"),"Odd máxima")
            if min_odd is None and max_odd is None:
                raise ValueError("Informe a odd mínima e/ou a odd máxima.")
            if min_odd is not None and max_odd is not None and min_odd>max_odd:
                raise ValueError("Odd mínima não pode superar a odd máxima.")
            parsed.append({"tipo":"odd","mercado":market,
                           "odd_min":min_odd,"odd_max":max_odd})
            continue
        if tipo!="indicador" or c.get("metrica") not in METRICAS or c.get("comparador") not in COMPARADORES:
            raise ValueError("Métrica ou comparador inválido.")
        lado=c.get("lado","mandante")
        mando=c.get("mando_preferido","indiferente")
        if mando not in ("mandante","visitante","indiferente"):
            raise ValueError("Escolha Mandante, Visitante ou Indiferente para o mando.")
        if lado=="ambos" and mando!="indiferente":
            raise ValueError("Para Ambos, o mando deve ser Indiferente, pois as duas equipes são avaliadas.")
        referencia=c.get("referencia","visitante")
        metrica_ref=c.get("metrica_ref",c["metrica"])
        if lado not in ("mandante","visitante","favorito","zebra","ambos"):
            raise ValueError("Equipe analisada inválida.")
        if lado=="ambos" and referencia!="valor":
            raise ValueError("Ambos requer comparação com valor absoluto: as duas equipes devem atender à condição.")
        if referencia not in ("valor","adversario","mandante","visitante","favorito","zebra"):
            raise ValueError("Referência de comparação inválida.")
        if metrica_ref not in METRICAS:
            raise ValueError("Indicador de referência inválido.")
        if referencia=="adversario":
            # A opção simplificada compara o MESMO indicador, sem margem
            # e do time oposto ao escolhido (nunca de si próprio).
            if c.get("metrica_ref",c["metrica"])!=c["metrica"]:
                raise ValueError("O adversário deve usar o mesmo indicador.")
            if c.get("valor") not in (None,0,0.0,"0","0.0") or c.get("margem") not in (None,0,0.0,"0","0.0"):
                raise ValueError("A comparação com o adversário não aceita margem.")
            valor=0.0
        else:
            # Nunca transformar valores ausentes em 0 silenciosamente.
            raw_value=c.get("valor",c.get("margem",0) if referencia!="valor" else None)
            if isinstance(raw_value,bool) or raw_value in ("",None):
                raise ValueError("Informe um valor numérico válido para a condição.")
            valor=_n(raw_value)
            if valor is None or not -10000<=valor<=10000:
                raise ValueError("Valor de comparação inválido.")
        parsed.append({
            "tipo":"indicador","lado":lado,"mando_preferido":mando,
            "metrica":c["metrica"],"comparador":c["comparador"],
            "referencia":referencia,"metrica_ref":metrica_ref,"valor":valor
        })
    return parsed


def _favorite_home(game):
    """Compara APENAS odds de vitória dos times no Match Odds (1 e 2).

    Empate (X) não é um time. Sem ambas as cotações válidas, ou em empate
    exato de preços, a classificação é indisponível: nunca inferimos pelo placar.
    """
    home=_n(game.get("api_odd_1_ft"))
    away=_n(game.get("api_odd_2_ft"))
    if home is None or away is None:
        return None
    if not 1.01<=home<=1000 or not 1.01<=away<=1000 or home==away:
        return None
    return home<away


def _role_to_side(role, favorite_home):
    if role in ("mandante","visitante"):
        return role
    if favorite_home is None:
        return None
    if role=="favorito":
        return "mandante" if favorite_home else "visitante"
    if role=="zebra":
        return "visitante" if favorite_home else "mandante"
    raise ValueError("Papel de clube não reconhecido.")


def _requires_favorite(market,conditions):
    return market in ("back_favorito","lay_favorito","back_zebra","lay_zebra",
                      "lay_goleada_favorito","lay_goleada_zebra") or any(
        (condition.get("tipo")=="odd" and condition["mercado"] in (
            "back_favorito","lay_favorito","back_zebra","lay_zebra",
            "lay_goleada_favorito","lay_goleada_zebra")) or
        (condition.get("tipo")!="odd" and (
            condition["lado"] in ("favorito","zebra") or
            condition["referencia"] in ("favorito","zebra")))
        for condition in conditions
    )


def _market_for_game(market, favorite_home):
    if market not in ("back_favorito","lay_favorito","back_zebra","lay_zebra",
                       "lay_goleada_favorito","lay_goleada_zebra"):
        return market
    if favorite_home is None:
        raise ValueError("Match Odds não disponíveis para classificar favorito/zebra.")
    if market in ("lay_goleada_favorito","lay_goleada_zebra"):
        # Ambos dependem da menor odd de vitória no Match Odds.
        # Lay goleada zebra é contra uma vitória da zebra por 3+ gols,
        # inclusive quando ela é mandante. Preserve os IDs antigos fixos.
        selected_home=(favorite_home if market=="lay_goleada_favorito"
                       else not favorite_home)
        return "lay_goleada_mandante" if selected_home else "lay_goleada_visitante"
    side=_role_to_side("favorito" if market.endswith("favorito") else "zebra",favorite_home)
    return market.split("_",1)[0]+"_"+side


def _evaluate_condition(cond,home_stats,away_stats,favorite_home=None):
    teams={"mandante":home_stats,"visitante":away_stats}
    if cond["lado"]=="ambos":
        observed_home=home_stats.get(cond["metrica"])
        observed_away=away_stats.get(cond["metrica"])
        reference=cond["valor"]
        if not (_compare(observed_home,reference,cond["comparador"]) and
                _compare(observed_away,reference,cond["comparador"])):
            return None
        return {"tipo":"indicador","lado":"ambos","mando":"ambos",
                "mando_preferido":"indiferente",
                "metrica":cond["metrica"],"nome":METRICAS[cond["metrica"]],
                "comparador":COMPARADORES[cond["comparador"]],
                "observado":None,"observado_mandante":round(observed_home,3),
                "observado_visitante":round(observed_away,3),
                "comparado":round(reference,3),"referencia":"valor",
                "nome_ref":"Valor fixo","metrica_ref":cond["metrica"],
                "valor":reference}
    side=_role_to_side(cond["lado"],favorite_home)
    if side is None:
        return None
    requested=cond.get("mando_preferido","indiferente")
    if requested!="indiferente" and requested!=side:
        return None
    observed=teams[side].get(cond["metrica"])
    if cond["referencia"]=="valor":
        reference=cond["valor"]
        ref_name="Valor fixo"
    elif cond["referencia"]=="adversario":
        opposite="visitante" if side=="mandante" else "mandante"
        reference=teams[opposite].get(cond["metrica"])
        ref_name=METRICAS[cond["metrica"]]+" do adversário"
    else:
        reference_side=_role_to_side(cond["referencia"],favorite_home)
        if reference_side is None:
            return None
        ref_value=teams[reference_side].get(cond["metrica_ref"])
        reference=ref_value+cond["valor"] if ref_value is not None else None
        ref_name=METRICAS[cond["metrica_ref"]]
    if not _compare(observed,reference,cond["comparador"]):
        return None
    return {
        "tipo":"indicador","lado":cond["lado"],"mando":side,
        "mando_preferido":requested,"metrica":cond["metrica"],
        "nome":METRICAS[cond["metrica"]],"comparador":COMPARADORES[cond["comparador"]],
        "observado":round(observed,3),"comparado":round(reference,3),
        "referencia":cond["referencia"],"nome_ref":ref_name,
        "metrica_ref":cond["metrica_ref"],"valor":cond["valor"],
    }

def _compare(left,right,op):
    if left is None or right is None:return False
    return {"gt":lambda:left>right,"ge":lambda:left>=right,
            "lt":lambda:left<right,"le":lambda:left<=right,
            "eq":lambda:abs(left-right)<1e-9,"ne":lambda:abs(left-right)>=1e-9}[op]()

def _settle(key,goals_home,goals_away):
    total=goals_home+goals_away
    win=goals_home>goals_away
    lose=goals_home<goals_away
    events={
      "back_mandante":win,"lay_mandante":not win,
      "back_visitante":lose,"lay_visitante":not lose,
      "back_empate":goals_home==goals_away,"lay_empate":goals_home!=goals_away,
      "over_05":total>=1,"over_15":total>=2,"over_25":total>=3,
      "over_35":total>=4,"under_25":total<=2,"under_35":total<=3,
      "ambos_marcam":goals_home>0 and goals_away>0,
      "ambos_nao":goals_home==0 or goals_away==0,
      "back_goleada_mandante":goals_home-goals_away>=3,
      "back_goleada_visitante":goals_away-goals_home>=3,
      "lay_goleada_mandante":goals_home-goals_away<3,
      "lay_goleada_visitante":goals_away-goals_home<3,
      "lay_1x0":not(goals_home==1 and goals_away==0),
      "lay_0x1":not(goals_home==0 and goals_away==1),
    }
    return events[key]

# O banco contém odds de casas de apostas e Lay ESTIMADO, nunca Lay
# executável na Betfair. Os preços históricos da API podem ter sido obtidos
# após a partida: não afirmar timestamp pré-jogo que a fonte não comprova.
API_MARKETS={
    "back_mandante":("api_odd_1_ft","api_bookie_odd_1_ft"),
    "back_visitante":("api_odd_2_ft","api_bookie_odd_2_ft"),
    "back_empate":("api_odd_x_ft","api_bookie_odd_x_ft"),
    "over_05":("api_over_ft_0_5","api_bookie_over_ft_0_5"),
    "over_15":("api_over_ft_1_5","api_bookie_over_ft_1_5"),
    "over_25":("api_over_ft_2_5","api_bookie_over_ft_2_5"),
    "over_35":("api_over_ft_3_5","api_bookie_over_ft_3_5"),
    "under_25":("api_under_ft_2_5","api_bookie_under_ft_2_5"),
    "under_35":("api_under_ft_3_5","api_bookie_under_ft_3_5"),
    "ambos_marcam":("api_btts_yes","api_bookie_btts_yes"),
    "ambos_nao":("api_btts_no","api_bookie_btts_no"),
    "lay_mandante":("api_lay_odd_1_ft","api_bookie_odd_1_ft"),
    "lay_visitante":("api_lay_odd_2_ft","api_bookie_odd_2_ft"),
    "lay_empate":("api_lay_odd_x_ft","api_bookie_odd_x_ft"),
    "lay_1x0":("api_lay_cs_1_0","api_bookie_cs_1_0"),
    "lay_0x1":("api_lay_cs_0_1","api_bookie_cs_0_1"),
}

def _model_cs_quotes(r):
    values=tuple(_n(r.get(f"api_cs_{home}_{away}")) for home,away in SCORE_KEYS)
    return estimate_goleada_quotes(values)


def _odds_for_game(r,market,manual):
    if manual is not None:return manual,"hipotetica"
    if market in ("back_goleada_mandante","back_goleada_visitante",
                  "lay_goleada_mandante","lay_goleada_visitante"):
        quotes=_model_cs_quotes(r)
        odd=quotes.get(market) if quotes else None
        if odd is None:
            return None,None
        return odd,("modelo_cs_lay" if market.startswith("lay_") else "modelo_cs_back")
    field=API_MARKETS.get(market)
    if field:
        price=_n(r.get(field[0]))
        if price is not None and 1.01<=price<=1000:
            return price,("lay_estimado" if market.startswith("lay_") else "api_casa")
    # Histórico FotMob: aceita Back 1x2 SOMENTE se registro anterior ao jogo.
    if market.startswith("lay_"):return None,None
    source={"back_mandante":"odd_casa","back_visitante":"odd_fora",
            "back_empate":"odd_empate"}.get(market)
    if not source:return None,None
    created=r.get("odd_criada")
    if not created:return None,None
    if isinstance(created,str):
        try:created=datetime.fromisoformat(created.replace("Z","+00:00"))
        except ValueError:return None,None
    if created.date()>=r["data"]:return None,None
    o=_n(r.get(source))
    return (o,"registrada_antes") if o is not None and 1.01<=o<=1000 else (None,None)

def _bookmaker_for_game(r,market,origin):
    if origin not in ("api_casa","lay_estimado"):return None
    column=API_MARKETS.get(market)
    value=r.get(column[1]) if column else None
    return str(value).strip()[:90] if value else None


def _units(success,market,odd,commission):
    if odd is None:return None
    if market.startswith("lay_"):
        # 1u de responsabilidade: perda máxima = 1u, ganho líquido:
        return (1-commission)/(odd-1) if success else -1.0
    return odd-1 if success else -1.0

def ligas_disponiveis():
    return fetch_all("""
       SELECT c.id,c.nome,COUNT(*) AS jogos
       FROM jogos j JOIN campeonatos c ON c.id=j.campeonato_id
       WHERE j.data<CURRENT_DATE
         AND j.gols_casa IS NOT NULL AND j.gols_fora IS NOT NULL
       GROUP BY c.id,c.nome
       ORDER BY c.nome
    """)


def clubes_disponiveis():
    """Clubes que disputaram jogos concluídos, agrupados por campeonato.

    A lista é carregada uma vez no metadata; o navegador filtra por
    campeonatos selecionados sem fazer consultas a cada clique.
    """
    return fetch_all("""
        WITH participacoes AS (
            SELECT j.casa_id AS clube_id,j.campeonato_id
            FROM jogos j WHERE j.data < CURRENT_DATE
                AND j.gols_casa IS NOT NULL AND j.gols_fora IS NOT NULL
            UNION
            SELECT j.fora_id AS clube_id,j.campeonato_id
            FROM jogos j WHERE j.data < CURRENT_DATE
                AND j.gols_casa IS NOT NULL AND j.gols_fora IS NOT NULL
        )
        SELECT c.id,c.clube AS nome,
               ARRAY_AGG(DISTINCT p.campeonato_id ORDER BY p.campeonato_id)
                    AS campeonato_ids
        FROM participacoes p JOIN clubes c ON c.id=p.clube_id
        GROUP BY c.id,c.clube
        ORDER BY c.clube,c.id
    """)


def clubes_selecionados(payload):
    """IDs válidos, ou None quando nenhum filtro de clubes foi definido."""
    if not isinstance(payload,dict):
        raise ValueError("Dados inválidos.")
    ids=payload.get("clube_ids",[])
    if ids is None:
        ids=[]
    if not isinstance(ids,list) or len(ids)>1000:
        raise ValueError("Selecione no máximo 1000 clubes.")
    if any(type(club) is not int or club < 1 for club in ids):
        raise ValueError("Clube inválido.")
    if len(ids)!=len(set(ids)):
        raise ValueError("Há clubes repetidos.")
    return sorted(ids) if ids else None


def ligas_selecionadas(payload):
    """Retorna lista de IDs, ou None quando o filtro significa todas as ligas.

    Compatível com estratégias antigas que possuem apenas campeonato_id.
    """
    if not isinstance(payload,dict):
        raise ValueError("Dados inválidos.")
    if "campeonato_ids" in payload:
        ids=payload["campeonato_ids"]
        if ids is None:
            ids=[]
        if not isinstance(ids,list) or len(ids)>30:
            raise ValueError("Selecione no máximo 30 campeonatos.")
        if any(type(league) is not int or league<1 for league in ids):
            raise ValueError("Campeonato inválido.")
        if len(ids)!=len(set(ids)):
            raise ValueError("Há campeonatos repetidos.")
        return sorted(ids) if ids else None
    old=payload.get("campeonato_id")
    if old in (None,""):
        return None
    if type(old) is not int or old<1:
        raise ValueError("Campeonato inválido.")
    return [old]


def _novo_resumo():
    """Acumulador sem arredondar: o rodapé não soma médias já arredondadas."""
    return {"entradas":0,"greens":0,"reds":0,"unidades":0.0,
            "cotadas":0,"odds_soma":0.0,"good_run":0,"bad_run":0,
            "maior_good_run":0,"maior_bad_run":0,"jogos":[]}


def _registrar_entrada(rec,green,odd,units):
    """Sequências seguem a ordem cronológica, inclusive no agregado das ligas."""
    rec["entradas"]+=1
    rec["greens"]+=int(green)
    rec["reds"]+=int(not green)
    if green:
        rec["good_run"]+=1
        rec["bad_run"]=0
        rec["maior_good_run"]=max(rec["maior_good_run"],rec["good_run"])
    else:
        rec["bad_run"]+=1
        rec["good_run"]=0
        rec["maior_bad_run"]=max(rec["maior_bad_run"],rec["bad_run"])
    if units is not None:
        rec["cotadas"]+=1
        rec["unidades"]+=units
        rec["odds_soma"]+=odd


def _fechar_resumo(rec):
    """Retorna métricas ponderadas por entradas, com cobertura de odds explícita."""
    rec["win_rate"]=round(100*rec["greens"]/rec["entradas"],2) if rec["entradas"] else 0
    rec["odd_media"]=round(rec["odds_soma"]/rec["cotadas"],2) if rec["cotadas"] else None
    rec["lucro_medio_entrada"]=round(rec["unidades"]*100/rec["cotadas"],2) if rec["cotadas"] else None
    rec["valor_reais"]=round(rec["unidades"]*100,2) if rec["cotadas"] else None
    rec["unidades"]=round(rec["unidades"],3) if rec["cotadas"] else None
    del rec["odds_soma"]
    del rec["good_run"]
    del rec["bad_run"]
    return rec


def testar(payload,rows=None,capture=False):
    if not isinstance(payload,dict):raise ValueError("Dados inválidos.")
    cutoff=payload.get("corte")
    try: cutoff=date.fromisoformat(cutoff)
    except (ValueError,TypeError):raise ValueError("Escolha uma data de corte válida.")
    if cutoff>date.today():raise ValueError("A data de corte não pode estar no futuro.")
    window=str(payload.get("jogos","20"))
    if window not in ("5","10","20","temporada"):raise ValueError("Recorte inválido.")
    market=payload.get("objetivo")
    if market not in MERCADOS:raise ValueError("Selecione um objetivo válido.")
    leagues_selected=ligas_selecionadas(payload)
    allowed=set(leagues_selected) if leagues_selected is not None else None
    clubs_selected=clubes_selecionados(payload)
    allowed_clubs=set(clubs_selected) if clubs_selected is not None else None
    conditions=_valid_conditions(payload.get("condicoes"))
    manual=payload.get("odd_hipotetica")
    if manual in (None,""):manual=None
    else:
        manual=_n(manual)
        if manual is None or not 1.01<=manual<=1000:
            raise ValueError("Odd hipotética deve estar entre 1,01 e 1000.")
    # Comissão fixa solicitada para o simulador Nostradamus.
    # Não representa a comissão contratual real da conta Betfair.
    commission=0.045
    args=[cutoff]
    cond=""
    if leagues_selected is not None:
        cond="AND j.campeonato_id = ANY(%s::integer[])"
        args.append(leagues_selected)
    if rows is None:rows=fetch_all(RAW.format(competition=cond),args)
    # Enforce all date/result gates again even with rows supplied by caller.
    filtered=[]
    today=date.today()
    for r in rows:
        d=r["data"]
        if isinstance(d,str):d=date.fromisoformat(d)
        if d<=cutoff and d<today and r.get("gols_casa") is not None and r.get("gols_fora") is not None and (allowed is None or r["campeonato_id"] in allowed):
            filtered.append({**r,"data":d})
    filtered.sort(key=lambda r:(r["data"],int(r["id"])))
    histories=defaultdict(list)
    leagues=defaultdict(_novo_resumo)
    total=_novo_resumo()
    length=None if window=="temporada" else int(window)
    matched_total=0
    sem_classificacao=0
    requires_classification=_requires_favorite(market,conditions)
    captured=[]
    for d,games_iter in groupby(filtered,key=lambda r:r["data"]):
        games=list(games_iter)
        # Crucial: evaluate ALL same-day games BEFORE adding any to history.
        for g in games:
            # Filtro de participantes vale só para as entradas: todas as
            # partidas continuam alimentando o histórico pré-jogo abaixo.
            if allowed_clubs is not None and not (
                g["casa_id"] in allowed_clubs or g["fora_id"] in allowed_clubs
            ):
                continue
            fav_home=_favorite_home(g)
            if requires_classification and fav_home is None:
                sem_classificacao+=1
                continue
            hkey=(g["campeonato_id"],g["temporada"],g["casa_id"])
            akey=(g["campeonato_id"],g["temporada"],g["fora_id"])
            h=_stats(histories[hkey],length)
            a=_stats(histories[akey],length)
            if h is None or a is None:continue
            details=[]
            for condition in conditions:
                if condition.get("tipo")=="odd":
                    criterion_market=_market_for_game(condition["mercado"],fav_home)
                    criterion_odd,criterion_source=_odds_for_game(g,criterion_market,None)
                    if criterion_odd is None or (
                        condition["odd_min"] is not None and criterion_odd<condition["odd_min"]
                    ) or (
                        condition["odd_max"] is not None and criterion_odd>condition["odd_max"]
                    ):
                        break
                    evaluated={"tipo":"odd","mercado":condition["mercado"],
                               "nome":ODD_FILTER_MARKETS[condition["mercado"]],
                               "odd":criterion_odd,"fonte":criterion_source,
                               "odd_min":condition["odd_min"],"odd_max":condition["odd_max"]}
                else:
                    evaluated=_evaluate_condition(condition,h,a,fav_home)
                if evaluated is None:
                    break
                details.append(evaluated)
            else:
                matched_total+=1
                name=g["campeonato"];rec=leagues[name]
                settled_market=_market_for_game(market,fav_home)
                hit=_settle(settled_market,int(g["gols_casa"]),int(g["gols_fora"]))
                odd,origin=_odds_for_game(g,settled_market,manual)
                units=_units(hit,settled_market,odd,commission)
                _registrar_entrada(rec,hit,odd,units)
                _registrar_entrada(total,hit,odd,units)
                if capture:
                    # Somente atributos conhecidos na data do jogo (o histórico
                    # é montado ANTES de acrescentar partidas do mesmo dia).
                    captured.append({
                        "id":g["id"],"data":d.isoformat(),"unidades":units,
                        "cotacao":origin,"odd":odd,"partida":g,
                        "stats_casa":h,"stats_fora":a,"favorito_casa":fav_home,
                    })
                if len(rec["jogos"])<400:
                    rec["jogos"].append({
                      "id":g["id"],"data":d.isoformat(),"mandante":g["mandante"],
                      "visitante":g["visitante"],"placar":str(g["gols_casa"])+"x"+str(g["gols_fora"]),
                      "green":hit,"odd":odd,"tipo_odd":origin,
                      "bookmaker":_bookmaker_for_game(g,settled_market,origin),
                      "favorito":(g["mandante"] if fav_home else g["visitante"]) if fav_home is not None else None,
                      "zebra":(g["visitante"] if fav_home else g["mandante"]) if fav_home is not None else None,
                      "mando_favorito":_role_to_side("favorito",fav_home) if fav_home is not None else None,
                      "mando_zebra":_role_to_side("zebra",fav_home) if fav_home is not None else None,
                      "odd_favorito":_n(g.get("api_odd_1_ft" if fav_home else "api_odd_2_ft")) if fav_home is not None else None,
                      "odd_zebra":_n(g.get("api_odd_2_ft" if fav_home else "api_odd_1_ft")) if fav_home is not None else None,
                      "placar_favorito":(str(g["gols_casa"])+"x"+str(g["gols_fora"]) if fav_home else
                                          str(g["gols_fora"])+"x"+str(g["gols_casa"])) if fav_home is not None else None,
                      "unidades":round(units,3) if units is not None else None,
                      "valor_reais":round(units*100,2) if units is not None else None,
                      "historico_mandante":min(len(histories[hkey]),length) if length is not None else len(histories[hkey]),
                      "historico_visitante":min(len(histories[akey]),length) if length is not None else len(histories[akey]),
                      "condicoes":details,
                      "goleada_cs":_model_cs_quotes(g) if (
                          "goleada" in market or any(
                            c.get("tipo")=="odd" and "goleada" in c["mercado"]
                            for c in conditions)) else None,
                    })
        for g in games:
            hkey=(g["campeonato_id"],g["temporada"],g["casa_id"])
            akey=(g["campeonato_id"],g["temporada"],g["fora_id"])
            for key,role in ((hkey,"home"),(akey,"away")):
                histories[key].append(_history_item(g,role))
    summary=[]
    for league_name,rec in sorted(leagues.items()):
        rec["campeonato"]=league_name
        summary.append(_fechar_resumo(rec))
    _fechar_resumo(total)
    # O rodapé usa sequências globais por data/ID, não soma as sequências de
    # cada liga. "jogos" não é utilizado no agregado; exclui carga extra.
    del total["jogos"]
    recorte_descrito=("até os últimos "+window+" jogos disponíveis" if window!="temporada"
                     else "todos os jogos disponíveis da temporada")
    response={"objetivo":market,"jogos":window,"corte":cutoff.isoformat(),
            "campeonato_ids":leagues_selected or [],
            "clube_ids":clubs_selected or [],
            "resultados":summary,"total":total,"entradas":matched_total,
            "sem_classificacao":sem_classificacao,
            "limite_detalhes":400,"odd_hipotetica":manual,"stake_reais":100,
            "aviso":"A data de corte limita os jogos analisados. Indicadores usam apenas "
                    +recorte_descrito+" anteriores a cada jogo, com mínimo de 5. "
                    "Favorito é o time com menor odd de vitória no Match Odds (1 ou 2); "
                    "a odd de empate (X) não classifica times. Preços iguais ou ausentes "
                    "não permitem classificar favorito/zebra; essas partidas são ignoradas "
                    "quando o filtro ou mercado depende da classificação. "
                    "O mando escolhido em condições Favorito/Zebra restringe a seleção "
                    "a partidas nas quais essa equipe atua como mandante ou visitante; "
                    "Indiferente aceita ambos os mandos. "
                    "A opção Ambos exige que cada equipe satisfaça o mesmo limite "
                    "do indicador. Filtros de odd usam exclusivamente a cotação "
                    "do mercado escolhido, sem substituir pela odd hipotética; "
                    "sem cotação, a condição não é atendida. "
                    "Win rate e sequências consideram todas as entradas; unidades e resultado "
                    "financeiro consideram SOMENTE entradas cotadas (1 unidade = R$ 100). "
                    "Odds Back são preços de casas do banco; como a data de captura da API "
                    "não comprova preço pré-jogo, o retorno é uma estimativa retrospectiva. "
                    "Odds Lay são estimadas, não executáveis, com comissão fixa de 4,5%. "
                    "As odds de goleada Back/Lay vêm de um modelo Poisson independente "
                    "ajustado aos Correct Scores 0x0–3x3, com projeção das caudas 4+ "
                    "e diferença ilustrativa de um tick na escada Betfair. "
                    "Não são odds reais de mercado nem comprovam disponibilidade pré-jogo. "
                    "Sem Correct Score suficiente, o resultado financeiro fica indisponível. "
                    "O passado não garante resultado futuro."}
    if capture:
        response["_dados_otimizacao"]=captured
        # Uso exclusivo do otimizador: permite simular remoções de regras sem
        # fazer novas consultas ao Supabase. Não é enviado à interface.
        response["_jogos_originais"]=filtered
    return response
