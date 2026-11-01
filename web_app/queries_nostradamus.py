"""Nostradamus: backtest cronológico sem vazamento de jogos futuros.

Só usa dados de partidas CONCLUÍDAS antes da data de cada entrada.
As condições sempre comparam mandante à equipe visitante.
Odds registradas após o início (data do jogo) nunca são consideradas históricas.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from itertools import groupby
from math import isfinite
from db import fetch_all

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
}
COMPARADORES = {"gt":">","ge":">=","lt":"<","le":"<=","eq":"=","ne":"!="}
MERCADOS = {
    "back_mandante":"Back mandante",
    "lay_mandante":"Lay mandante",
    "back_visitante":"Back visitante",
    "lay_visitante":"Lay visitante",
    "back_empate":"Back empate",
    "lay_empate":"Lay empate",
    "over_05":"Over 0,5",
    "over_15":"Over 1,5",
    "over_25":"Over 2,5",
    "over_35":"Over 3,5",
    "under_25":"Under 2,5",
    "ambos_marcam":"Ambos marcam",
    "ambos_nao":"Ambos não marcam",
    "lay_goleada_mandante":"Lay goleada mandante",
    "lay_goleada_visitante":"Lay goleada visitante",
    "lay_1x0":"Lay placar 1x0",
    "lay_0x1":"Lay placar 0x1",
}

RAW = """
SELECT j.id,j.data,j.temporada,j.campeonato_id,c.nome AS campeonato,
       j.casa_id,j.fora_id,h.clube AS mandante,v.clube AS visitante,
       j.gols_casa,j.gols_fora,
       oh.odd_casa,oh.odd_empate,oh.odd_fora,oh.criado_em AS odd_criada,
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
       ec.disputas_aereas_ganhas AS home_duelos_aereos,ea.disputas_aereas_ganhas AS away_duelos_aereos
FROM jogos j
JOIN campeonatos c ON c.id=j.campeonato_id
JOIN clubes h ON h.id=j.casa_id
JOIN clubes v ON v.id=j.fora_id
LEFT JOIN estatisticas ec ON ec.jogo_id=j.id AND ec.clube_id=j.casa_id AND ec.periodo='Completo'
LEFT JOIN estatisticas ea ON ea.jogo_id=j.id AND ea.clube_id=j.fora_id AND ea.periodo='Completo'
LEFT JOIN odds_fotmob oh ON oh.jogo_id=j.id
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

def _stats(history,amount):
    selected=history[-amount:] if amount is not None else history
    if len(selected)<(amount or 5):
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
            "grandes_chances","escanteios","dribles_certos","faltas","duelos_aereos")
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

def _valid_conditions(conditions):
    if not isinstance(conditions,list) or not 1<=len(conditions)<=10:
        raise ValueError("Escolha entre 1 e 10 condições.")
    parsed=[]
    for c in conditions:
        if not isinstance(c,dict) or c.get("metrica") not in METRICAS or c.get("comparador") not in COMPARADORES:
            raise ValueError("Métrica ou comparador inválido.")
        margin=_n(c.get("margem",0))
        if margin is None or not -10000<=margin<=10000:
            raise ValueError("Margem inválida.")
        parsed.append((c["metrica"],c["comparador"],margin))
    return parsed

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
      "over_35":total>=4,"under_25":total<=2,
      "ambos_marcam":goals_home>0 and goals_away>0,
      "ambos_nao":goals_home==0 or goals_away==0,
      "lay_goleada_mandante":goals_home-goals_away<3,
      "lay_goleada_visitante":goals_away-goals_home<3,
      "lay_1x0":not(goals_home==1 and goals_away==0),
      "lay_0x1":not(goals_home==0 and goals_away==1),
    }
    return events[key]

def _odds_for_game(r,market,manual):
    if manual is not None:return manual,"hipotetica"
    # odds_fotmob contém cotações de back de casas, não odds LAY
    # executáveis em bolsa de apostas. Nunca reutilizá-las como lay.
    if market.startswith("lay_"):return None,None
    source={"back_mandante":"odd_casa","lay_mandante":"odd_casa",
            "back_visitante":"odd_fora","lay_visitante":"odd_fora",
            "back_empate":"odd_empate","lay_empate":"odd_empate"}.get(market)
    if not source:return None,None
    created=r.get("odd_criada")
    if not created:return None,None
    if isinstance(created,str):
        try:created=datetime.fromisoformat(created.replace("Z","+00:00"))
        except ValueError:return None,None
    if created.date()>=r["data"]:
        return None,None
    o=_n(r.get(source))
    return (o,"registrada_antes") if o is not None and 1.01<=o<=1000 else (None,None)

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


def testar(payload,rows=None):
    if not isinstance(payload,dict):raise ValueError("Dados inválidos.")
    cutoff=payload.get("corte")
    try: cutoff=date.fromisoformat(cutoff)
    except (ValueError,TypeError):raise ValueError("Escolha uma data de corte válida.")
    if cutoff>date.today():raise ValueError("A data de corte não pode estar no futuro.")
    window=str(payload.get("jogos","20"))
    if window not in ("5","10","20","temporada"):raise ValueError("Recorte inválido.")
    market=payload.get("objetivo")
    if market not in MERCADOS:raise ValueError("Selecione um objetivo válido.")
    league=payload.get("campeonato_id")
    if league is not None and (type(league) is not int or league<1):
        raise ValueError("Campeonato inválido.")
    conditions=_valid_conditions(payload.get("condicoes"))
    manual=payload.get("odd_hipotetica")
    if manual in (None,""):manual=None
    else:
        manual=_n(manual)
        if manual is None or not 1.01<=manual<=1000:
            raise ValueError("Odd hipotética deve estar entre 1,01 e 1000.")
    commission=_n(payload.get("comissao_pct",2))
    if commission is None or not 0<=commission<=30:raise ValueError("Comissão inválida.")
    commission/=100.0
    args=[cutoff]
    cond=""
    if league:
        cond="AND j.campeonato_id=%s"
        args.append(league)
    if rows is None:rows=fetch_all(RAW.format(competition=cond),args)
    # Enforce all date/result gates again even with rows supplied by caller.
    filtered=[]
    today=date.today()
    for r in rows:
        d=r["data"]
        if isinstance(d,str):d=date.fromisoformat(d)
        if d<=cutoff and d<today and r.get("gols_casa") is not None and r.get("gols_fora") is not None and (not league or r["campeonato_id"]==league):
            filtered.append({**r,"data":d})
    filtered.sort(key=lambda r:(r["data"],int(r["id"])))
    histories=defaultdict(list)
    leagues=defaultdict(lambda:{"entradas":0,"greens":0,"reds":0,"unidades":0.0,"cotadas":0,"jogos":[]})
    length=None if window=="temporada" else int(window)
    matched_total=0
    for d,games_iter in groupby(filtered,key=lambda r:r["data"]):
        games=list(games_iter)
        # Crucial: evaluate ALL same-day games BEFORE adding any to history.
        for g in games:
            hkey=(g["campeonato_id"],g["temporada"],g["casa_id"])
            akey=(g["campeonato_id"],g["temporada"],g["fora_id"])
            h=_stats(histories[hkey],length)
            a=_stats(histories[akey],length)
            if h is None or a is None:continue
            details=[]
            for key,op,margin in conditions:
                x,y=h.get(key),a.get(key)
                if not _compare(x, y+margin if y is not None else None,op):
                    break
                details.append({"metrica":key,"nome":METRICAS[key],"comparador":COMPARADORES[op],
                                "mandante":round(x,3),"visitante":round(y,3),"margem":margin})
            else:
                matched_total+=1
                name=g["campeonato"];rec=leagues[name]
                hit=_settle(market,int(g["gols_casa"]),int(g["gols_fora"]))
                odd,origin=_odds_for_game(g,market,manual)
                units=_units(hit,market,odd,commission)
                rec["entradas"]+=1
                rec["greens"]+=int(hit)
                rec["reds"]+=int(not hit)
                if units is not None:
                    rec["cotadas"]+=1
                    rec["unidades"]+=units
                if len(rec["jogos"])<400:
                    rec["jogos"].append({
                      "id":g["id"],"data":d.isoformat(),"mandante":g["mandante"],
                      "visitante":g["visitante"],"placar":str(g["gols_casa"])+"x"+str(g["gols_fora"]),
                      "green":hit,"odd":odd,"tipo_odd":origin,
                      "unidades":round(units,3) if units is not None else None,
                      "condicoes":details,
                    })
        for g in games:
            hkey=(g["campeonato_id"],g["temporada"],g["casa_id"])
            akey=(g["campeonato_id"],g["temporada"],g["fora_id"])
            for key,role,opposition in ((hkey,"home","away"),(akey,"away","home")):
                gf=int(g["gols_casa"] if role=="home" else g["gols_fora"])
                ga=int(g["gols_fora"] if role=="home" else g["gols_casa"])
                item={"gf":gf,"ga":ga}
                for field in ("xg","xgot","chutes","chutes_certos","passes_certos","posse",
                              "grandes_chances","escanteios","dribles_certos","faltas","duelos_aereos"):
                    item[field]=g.get(role+"_"+field)
                histories[key].append(item)
    summary=[]
    for league_name,rec in sorted(leagues.items()):
        rec["campeonato"]=league_name
        rec["win_rate"]=round(100*rec["greens"]/rec["entradas"],2) if rec["entradas"] else 0
        rec["unidades"]=round(rec["unidades"],3) if rec["cotadas"] else None
        summary.append(rec)
    return {"objetivo":market,"jogos":window,"corte":cutoff.isoformat(),
            "resultados":summary,"entradas":matched_total,
            "limite_detalhes":400,"odd_hipotetica":manual,
            "aviso":"Somente jogos concluídos anteriores a hoje e até a data de corte. Para cada entrada, as condições usam exclusivamente jogos anteriores à data dela, dentro da mesma liga e temporada. Sem odd comprovadamente anterior ao jogo (ou odd hipotética explícita), unidades indisponíveis. Odds hipotéticas não representam preços executáveis. Back usa risco de 1u; lay, responsabilidade de 1u (comissão sobre greens). Sem garantia de ganhos."}
