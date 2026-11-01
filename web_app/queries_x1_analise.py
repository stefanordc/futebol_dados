"""X1: comparação descritiva por equipe e últimos N jogos concluídos.

A análise não se confunde com a regressão de Poisson para probabilidades.
Não usa os resultados de partidas futuras; não inventa estatísticas ausentes.
Somente consultas SELECT, sem migrações.
"""
from __future__ import annotations

import math
from collections import defaultdict
from statistics import variance, stdev
from datetime import date

from db import fetch_all
from queries import _serialize
from queries_dados_fisicos import _campeonato_origem

LIMITS = {"5": 5, "10": 10, "20": 20, "temporada": None}
STATS = [
    "xg", "xgot", "xg_jogada_normal", "xg_jogada_ensaiada", "xg_sem_penalti",
    "total_chutes", "chutes_certos", "chutes_fora", "chutes_bloqueados",
    "chutes_trave", "chutes_dentro_area", "chutes_fora_area",
    "grandes_chances", "grandes_chances_perdidas", "passes", "passes_certos",
    "passes_longos", "passes_longos_certos", "cruzamentos", "cruzamentos_certos",
    "escanteios", "toques_area_adversaria", "impedimentos", "desarmes",
    "interceptacoes", "bloqueios", "bolas_afastadas", "defesas_goleiro",
    "disputas_ganhas", "disputas_chao", "disputas_chao_ganhas",
    "disputas_aereas", "disputas_aereas_ganhas", "dribles", "dribles_certos",
    "faltas_cometidas", "faltas_recebidas", "cartao_amarelo", "cartao_vermelho",
]
# Posse é percentual e por isso usa a média, nunca soma de percentuais.
STATS.append("posse_bola")

_GAMES = """
WITH escolhidos AS (
    SELECT j.id, j.data, j.campeonato_id, j.temporada,
           j.casa_id, j.fora_id, j.gols_casa, j.gols_fora,
           CASE WHEN j.casa_id=%s THEN %s ELSE %s END AS clube_id,
           CASE WHEN j.casa_id=%s THEN j.fora_id ELSE j.casa_id END AS rival_id,
           CASE WHEN j.casa_id=%s THEN 'Casa' ELSE 'Fora' END AS mando,
           CASE WHEN j.casa_id=%s THEN j.gols_casa ELSE j.gols_fora END AS gf,
           CASE WHEN j.casa_id=%s THEN j.gols_fora ELSE j.gols_casa END AS ga
    FROM jogos j
    WHERE j.campeonato_id=%s AND j.temporada=%s
      AND (j.casa_id=%s OR j.fora_id=%s)
      AND j.gols_casa IS NOT NULL AND j.gols_fora IS NOT NULL
      AND (j.data IS NULL OR j.data<=CURRENT_DATE)
    ORDER BY j.data DESC NULLS LAST,j.id DESC
    LIMIT %s
)
SELECT j.*, c.clube AS clube_nome,
       {cols}
FROM escolhidos j
JOIN clubes c ON c.id=j.clube_id
LEFT JOIN estatisticas ef
  ON ef.jogo_id=j.id AND ef.clube_id=j.clube_id AND ef.periodo='Completo'
LEFT JOIN estatisticas ec
  ON ec.jogo_id=j.id AND ec.clube_id=j.rival_id AND ec.periodo='Completo'
ORDER BY j.data DESC NULLS LAST,j.id DESC
"""


def _number(v):
    try:
        result=float(v)
        return result if math.isfinite(result) else None
    except (ValueError,TypeError):
        return None


def _sum_covered(rows,key):
    known=[_number(r.get(key)) for r in rows]
    values=[n for n in known if n is not None]
    return round(sum(values),6) if values else None


def _ratio(a,b,scale=1):
    return round(a*scale/b,5) if a is not None and b is not None and b>0 else None


def _pct(a,b):
    return _ratio(a,b,100)


def _variance(values):
    return round(variance(values),5) if len(values)>=2 else None


def _get_match_rows(camp,season,team,limit):
    fields=",\n       ".join(
        f"ef.{name} AS {name}, ec.{name} AS rival_{name}" for name in STATS
    )
    n=limit if limit is not None else 10000
    sql=_GAMES.format(cols=fields)
    args=[team,team,team,team,team,team,team,camp,season,team,team,n]
    return [_serialize(r) for r in fetch_all(sql,args)]


def _goal_types(rows,team):
    ids=[int(r["id"]) for r in rows]
    if not ids:
        return {"tipos":None,"jogos_com_mapa":0,"gols_classificados":0,"gols_situacao":0}
    events=fetch_all("""
        SELECT f.jogo_id, f.clube_id, f.tipo_evento,
               f.tipo_finalizacao, f.situacao_jogada, f.foi_gol_contra
        FROM finalizacoes f
        WHERE f.jogo_id=ANY(%s) AND f.clube_id=%s
    """,(ids,team))
    grouped=defaultdict(list)
    for e in events:
        grouped[e["jogo_id"]].append(e)
    names={
        "pe_direito":0,"pe_esquerdo":0,"cabeca":0,"bola_parada":0,
        "escanteio":0,"falta":0,"penalti":0,"individual":0,
        "contra_ataque":0,"jogada_normal":0,
    }
    body_count=situation_count=goal_count=0
    for es in grouped.values():
        for e in es:
            if "gol" not in (e.get("tipo_evento") or "").casefold():
                continue
            if e.get("foi_gol_contra"):
                continue
            goal_count+=1
            body=(e.get("tipo_finalizacao") or "").casefold()
            situation=(e.get("situacao_jogada") or "").casefold()
            if body:
                body_count+=1
            if situation:
                situation_count+=1
            if "direito" in body or "rightfoot" in body:
                names["pe_direito"]+=1
            if "esquerdo" in body or "leftfoot" in body:
                names["pe_esquerdo"]+=1
            if "cabeça" in body or "cabeca" in body or "header" in body:
                names["cabeca"]+=1
            if any(x in situation for x in ("bola parada","escanteio","falta","pênalti","penalti","corner","free kick","set piece")):
                names["bola_parada"]+=1
            if "escanteio" in situation or "corner" in situation:
                names["escanteio"]+=1
            if "falta" in situation or "free kick" in situation:
                names["falta"]+=1
            if "pênalti" in situation or "penalti" in situation:
                names["penalti"]+=1
            if "individual" in situation or "solo" in situation:
                names["individual"]+=1
            if "contra-ataque" in situation or "counter" in situation:
                names["contra_ataque"]+=1
            if "normal" in situation or "open play" in situation:
                names["jogada_normal"]+=1
    # Ausência de mapas não é contagem zero.
    return {
        "tipos":names if grouped and goal_count else None,
        "jogos_com_mapa":len(grouped),
        "gols_classificados":body_count,
        "gols_situacao":situation_count,
        "gols_em_eventos":goal_count,
    }


def _physical_rows(rows,source,season,club):
    """Relaciona o recorte por data/clube; exige correspondência única de partida."""
    if not rows or source is None:
        return {}
    ids=[int(r["id"]) for r in rows]
    # Nos brasileiros o id_jogo externo pode não existir em jogos.
    # Confere data, nome do clube e mando para evitar mistura de clubes.
    data=fetch_all("""
        SELECT j.id AS jogo_id, f.distancia_percorrida AS km, f.sprints
        FROM jogos j
        JOIN clubes c ON c.id=%s
        LEFT JOIN clubes_fontes cf
          ON cf.clube_id=c.id AND cf.fonte='sofascore'
        JOIN dados_fisicos f
          ON f.id_campeonato=%s AND f.temporada=%s
         AND (f.id_clube::text = cf.id_externo
              OR LOWER(TRIM(f.clube))=LOWER(TRIM(c.clube)))
         AND f.data=j.data
         AND LOWER(TRIM(f.mando)) =
           CASE WHEN j.casa_id=c.id THEN 'casa' ELSE 'fora' END
        WHERE j.id=ANY(%s)
          AND c.id IN(j.casa_id,j.fora_id)
    """,(club,source,season,ids))
    # Deduplicação conservadora em caso de dois registros de origem iguais.
    match=defaultdict(list)
    for r in data:
        match[int(r["jogo_id"])].append(r)
    return {game:items[0] for game,items in match.items() if len(items)==1}


def _team_report(rows,team,source,season):
    n=len(rows)
    if n==0:
        return {"jogos":0,"metricas":{},"cobertura":{},"tipos_gol":None,
                "recente":[],"filtro":{"primeiro":None,"ultimo":None}}
    scored=[int(r["gf"]) for r in rows]
    conceded=[int(r["ga"]) for r in rows]
    diff=[a-b for a,b in zip(scored,conceded)]
    pts=[3 if x>0 else 1 if x==0 else 0 for x in diff]
    wins=sum(x>0 for x in diff);draws=sum(x==0 for x in diff);losses=n-wins-draws
    metrics={
      "jogos":n,"vitorias":wins,"empates":draws,"derrotas":losses,
      "pontos":sum(pts),"aproveitamento_pct":_pct(sum(pts),3*n),
      "gols_marcados":sum(scored),"gols_sofridos":sum(conceded),
      "saldo_gols":sum(diff),"clean_sheets":sum(a==0 for a in conceded),
      "sem_marcar":sum(g==0 for g in scored),
      "media_pontos":round(sum(pts)/n,5),"vitorias_pct":_pct(wins,n),
      "empates_pct":_pct(draws,n),"derrotas_pct":_pct(losses,n),
      "media_gols_marcados":round(sum(scored)/n,5),
      "media_gols_sofridos":round(sum(conceded)/n,5),
      "variancia_saldo":_variance(diff),
      "variancia_gols_marcados":_variance(scored),
      "desvio_padrao_saldo":round(stdev(diff),5) if n>=2 else None,
      "coef_variacao_gols":_pct(stdev(scored),sum(scored)/n) if n>=2 else None,
      "amplitude_saldo":max(diff)-min(diff),
      "pontos_ultimos_5":sum(pts[:5]),
      "forma":"".join("V" if x>0 else "E" if x==0 else "D" for x in diff[:5]),
    }
    covered={}
    # O denominador de uma média depende da cobertura real da respectiva coluna.
    for col in STATS:
        values=[_number(r.get(col)) for r in rows if _number(r.get(col)) is not None]
        covered[col]=len(values)
        if values:
            metrics[col]=round(sum(values),5) if col!="posse_bola" else round(sum(values)/len(values),5)
            metrics[col+"_por_jogo"]=round(sum(values)/len(values),5)
        else:
            metrics[col]=None
            metrics[col+"_por_jogo"]=None
        # Métricas concedidas pelo adversário para comparar a defesa.
        other="rival_"+col
        values2=[_number(r.get(other)) for r in rows if _number(r.get(other)) is not None]
        covered[other]=len(values2)
        metrics[other]=round(sum(values2),5) if values2 and col!="posse_bola" else (
            round(sum(values2)/len(values2),5) if values2 else None)
        metrics[other+"_por_jogo"]=round(sum(values2)/len(values2),5) if values2 else None

    # Evita viés por cobertura parcial: chutes e gols precisam vir da MESMA amostra.
    def aligned_ratio(key,denkey="gf",fraction=True):
        sample=[r for r in rows if _number(r.get(key)) is not None]
        numerator=sum(_number(r[key]) for r in sample)
        if denkey=="gf":
            denominator=sum(int(r["gf"]) for r in sample)
        elif denkey=="ga":
            denominator=sum(int(r["ga"]) for r in sample)
        else:
            denominator=sum(_number(r.get(denkey)) or 0 for r in sample)
        return _ratio(numerator,denominator) if fraction else _pct(numerator,denominator)
    metrics["chutes_por_gol"]=aligned_ratio("total_chutes")
    metrics["chutes_certos_por_gol"]=aligned_ratio("chutes_certos")
    metrics["passes_certos_por_gol"]=aligned_ratio("passes_certos")
    metrics["grandes_chances_por_gol"]=aligned_ratio("grandes_chances")
    metrics["chutes_sofridos_por_gol"]=aligned_ratio("rival_total_chutes","ga")
    metrics["precisao_finalizacoes_pct"]=_pct(metrics["chutes_certos"],metrics["total_chutes"])
    def matched_conversion(key):
        sample=[r for r in rows if _number(r.get(key)) is not None]
        if not sample:
            return None
        total=sum(_number(r[key]) for r in sample)
        goals=sum(int(r["gf"]) for r in sample)
        return _pct(goals,total)
    metrics["conversao_chutes_pct"]=matched_conversion("total_chutes")
    metrics["acerto_passes_pct"]=_pct(metrics["passes_certos"],metrics["passes"])
    metrics["acerto_aereo_pct"]=_pct(metrics["disputas_aereas_ganhas"],metrics["disputas_aereas"])
    metrics["acerto_dribles_pct"]=_pct(metrics["dribles_certos"],metrics["dribles"])
    metrics["acerto_cruzamentos_pct"]=_pct(metrics["cruzamentos_certos"],metrics["cruzamentos"])
    metrics["eficiencia_xg_pct"]=matched_conversion("xg")
    metrics["xg_por_gol"]=aligned_ratio("xg")
    metrics["gols_menos_xg"]=None
    if covered["xg"]:
        sample=[r for r in rows if r.get("xg") is not None]
        metrics["gols_menos_xg"]=round(sum(int(r["gf"]) for r in sample)-sum(float(r["xg"]) for r in sample),5)
    if covered["rival_xg"]:
        sample=[r for r in rows if r.get("rival_xg") is not None]
        metrics["xga_menos_gols_sofridos"]=round(sum(float(r["rival_xg"]) for r in sample)-sum(int(r["ga"]) for r in sample),5)
    else:metrics["xga_menos_gols_sofridos"]=None
    goal_info=_goal_types(rows,team)
    phys=_physical_rows(rows,source,season,team)
    km=[float(r["km"]) for r in phys.values() if _number(r.get("km")) is not None and float(r["km"])>0]
    sp=[float(r["sprints"]) for r in phys.values() if _number(r.get("sprints")) is not None and float(r["sprints"])>0]
    metrics["distancia_percorrida"]=round(sum(km),5) if km else None
    metrics["distancia_percorrida_por_jogo"]=round(sum(km)/len(km),5) if km else None
    metrics["sprints"]=sum(sp) if sp else None
    metrics["sprints_por_jogo"]=round(sum(sp)/len(sp),5) if sp else None
    covered["distancia_percorrida"]=len(km)
    covered["sprints"]=len(sp)
    for k in ("jogos","gols_classificados","gols_situacao","gols_em_eventos"):
        if k in goal_info:covered[k+"_gol"]=goal_info[k]
    recent=[{"data":r.get("data"),"mando":r["mando"],"gm":r["gf"],"gs":r["ga"],
             "pontos":pts[i],"saldo":diff[i],
             "xg":r.get("xg"),"chutes":r.get("total_chutes")} for i,r in enumerate(rows)]
    return {
        "jogos":n, "metricas":metrics,"cobertura":covered,
        "tipos_gol":goal_info, "recente":recent,
        "filtro":{"primeiro":rows[-1].get("data"),"ultimo":rows[0].get("data")},
        "nota":"Métricas por jogo usam apenas partidas com registro daquele campo; razões por gol utilizam gols da mesma amostra. Resultados usam placares finalizados."
    }


def analisar(campeonato_id:int, temporada:str, mandante_id:int,
            visitante_id:int, ultimos:str="20"):
    if ultimos not in LIMITS:
        raise ValueError("Recorte deve ser 5, 10, 20 ou temporada.")
    if mandante_id==visitante_id:
        raise ValueError("Mandante e visitante precisam ser diferentes.")
    limit=LIMITS[ultimos]
    source=_campeonato_origem(campeonato_id)
    result={}
    for label,team in (("mandante",mandante_id),("visitante",visitante_id)):
        rows=_get_match_rows(campeonato_id,temporada,team,limit)
        result[label]=_team_report(rows,team,source,temporada)
        if rows:result[label]["nome"]=rows[0]["clube_nome"]
    return {"campeonato_id":campeonato_id,"temporada":temporada,"recorte":ultimos,
            **result,
            "metodologia":{
              "ordem":"Últimos jogos concluídos da competição e temporada por clube (não somente confrontos diretos).",
              "variancia":"Variância amostral do saldo de gols por jogo (gols marcados − sofridos), dividida por n−1; quanto maior, mais irregular o saldo, não necessariamente pior.",
              "conversao_xg":"Gols / soma do xG em partidas com xG. 100% representa gols iguais ao xG; >100% significa gols acima do xG.",
              "gols_tipos":"Contagens entre gols identificados em eventos de finalização; classificações se sobrepõem e dependem da cobertura.",
              "precisao":"A análise é descritiva. O modelo preditivo x1 utiliza treinamento próprio; modificar o recorte não altera suas probabilidades."
            }}
