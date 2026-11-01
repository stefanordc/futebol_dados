"""Modelo x1: regressão de Poisson regularizada e projeções probabilísticas.

Só leitura de jogos e estatísticas do PostgreSQL. Sem bibliotecas de ML externas.
As probabilidades são estimativas, não preços de mercado ou garantia de lucro.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime

from db import fetch_all
from queries import _serialize

RADAR_BASE = ["Ataque", "Defesa", "Criatividade", "Gols", "Evitar gols", "Eficiência"]
RADAR_ESP = ["Força ofensiva", "Força defensiva", "Bola parada ofensiva",
             "Bola parada defensiva", "Bola aérea ofensiva", "Bola aérea defensiva"]
SCORE_LABELS = [(h,a) for h in range(5) for a in range(5)]


def _clamp(x, low, high):
    return max(low, min(high, x))


def _num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _models(camp, season, home, away):
    # Até três temporadas, com maior importância dos jogos recentes.
    seasons = fetch_all("""
        SELECT DISTINCT temporada FROM jogos WHERE campeonato_id=%s
          AND temporada IS NOT NULL AND gols_casa IS NOT NULL
        ORDER BY temporada DESC LIMIT 3
    """, (camp,))
    available = [r["temporada"] for r in seasons]
    if season not in available:
        raise ValueError("Temporada sem jogos concluídos nesta competição.")
    selected = available[available.index(season):]
    rows = fetch_all("""
        SELECT id, temporada, data, casa_id, fora_id, gols_casa, gols_fora
        FROM jogos
        WHERE campeonato_id=%s AND temporada=ANY(%s)
          AND gols_casa IS NOT NULL AND gols_fora IS NOT NULL
        ORDER BY data NULLS FIRST, id
        LIMIT 1800
    """, (camp, selected))
    games = [_serialize(r) for r in rows]
    if len(games) < 20:
        raise ValueError("A competição precisa de ao menos 20 jogos concluídos para esta análise.")
    ids = {int(g["casa_id"]) for g in games} | {int(g["fora_id"]) for g in games}
    if home not in ids or away not in ids:
        raise ValueError("Um dos clubes não possui jogos registrados nesta competição.")
    n = len(games)
    # Medição das forças sem compartilhar dados futuros, quando a temporada já terminou.
    train = games
    team_ids = sorted(ids)
    att = {i:0.0 for i in team_ids}
    defense = {i:0.0 for i in team_ids}
    mean_h = _clamp(sum(int(g["gols_casa"]) for g in train)/n,0.4,3.5)
    mean_a = _clamp(sum(int(g["gols_fora"]) for g in train)/n,0.4,3.5)
    # Treino supervisionado: descida de gradiente de perda Poisson + ridge.
    # Vetores ofensivos/defensivos e efeito casa, com regularização.
    logs = (math.log(mean_h),math.log(mean_a))
    home_effect = 0.0
    for epoch in range(170):
        grad_a=defaultdict(float)
        grad_d=defaultdict(float)
        seen=defaultdict(float)
        gh=0.0
        for g in train:
            h=int(g["casa_id"]);v=int(g["fora_id"])
            # Se disponível, jogo da temporada atual recebe peso maior.
            w=0.70**selected.index(g["temporada"])
            l_h=_clamp(math.exp(_clamp(logs[0]+home_effect+att[h]-defense[v],-2.4,2.0)),0.15,7.4)
            l_a=_clamp(math.exp(_clamp(logs[1]+att[v]-defense[h],-2.4,2.0)),0.15,7.4)
            dh=w*(l_h-int(g["gols_casa"]))
            da=w*(l_a-int(g["gols_fora"]))
            grad_a[h]+=dh;grad_d[v]-=dh
            grad_a[v]+=da;grad_d[h]-=da
            seen[h]+=w;seen[v]+=w;gh+=dh
        lr=0.18*(1-0.55*epoch/170)
        home_effect=_clamp(home_effect-lr*(gh/max(n,1)+0.25*home_effect),-0.4,0.4)
        for club in team_ids:
            k=max(3,seen[club])
            att[club]=_clamp(att[club]-lr*(grad_a[club]/k+0.18*att[club]),-0.85,0.85)
            defense[club]=_clamp(defense[club]-lr*(grad_d[club]/k+0.18*defense[club]),-0.85,0.85)
    lam_h=_clamp(math.exp(logs[0]+home_effect+att[home]-defense[away]),0.2,4.3)
    lam_a=_clamp(math.exp(logs[1]+att[away]-defense[home]),0.2,4.3)
    # Tamanho da amostra de cada clube na temporada escolhida
    counts={i:sum(g["temporada"]==season and (g["casa_id"]==i or g["fora_id"]==i) for g in games) for i in (home,away)}
    return games,lam_h,lam_a,counts,{"n":n,"temporadas":selected,"media_casa":round(mean_h,3),"media_fora":round(mean_a,3)}


def _team_stats(camp,season):
    # Agregação por clube/mandante-visitante; a média de xG é um proxy adicional.
    rows=fetch_all("""
        SELECT e.clube_id,
          COUNT(DISTINCT e.jogo_id) AS jogos,
          AVG(e.xg) AS xg,
          AVG(e.xg_jogada_ensaiada) AS bola_parada,
          AVG(e.total_chutes) AS chutes,
          AVG(e.chutes_certos) AS chutes_certos,
          AVG(e.grandes_chances) AS chances,
          AVG(e.passes_certos) AS passes,
          AVG(e.desarmes) AS desarmes,
          AVG(e.interceptacoes) AS interceptacoes,
          AVG(e.bloqueios) AS bloqueios,
          AVG(e.disputas_aereas_ganhas) AS aereas_ganhas,
          AVG(e.disputas_aereas) AS aereas,
          AVG(CASE WHEN e.mando='Casa' THEN j.gols_casa ELSE j.gols_fora END) AS gols,
          AVG(CASE WHEN e.mando='Casa' THEN j.gols_fora ELSE j.gols_casa END) AS sofridos,
          AVG(CASE WHEN e.mando='Casa' THEN 1.0*(j.gols_fora=0)::int
                   ELSE 1.0*(j.gols_casa=0)::int END) AS clean_sheets
        FROM estatisticas e JOIN jogos j ON j.id=e.jogo_id
        WHERE j.campeonato_id=%s AND j.temporada=%s AND j.gols_casa IS NOT NULL
          AND e.periodo='Completo'
        GROUP BY e.clube_id
    """,(camp,season))
    return {int(r["clube_id"]):_serialize(r) for r in rows}


def _normalize(value,items,invert=False):
    value=_num(value)
    nums=sorted(x for x in (_num(v) for v in items) if x is not None)
    if value is None or len(nums)<4:
        return None
    # Percentil entre as equipes da própria competição (robustez por comparação).
    # 100 corresponde ao topo da amostra, não a 100% de acerto.
    rank=sum(x<value for x in nums)+0.5*sum(x==value for x in nums)
    pct=round(100*rank/len(nums))
    return 100-pct if invert else pct


def _radars(club,all_teams):
    def strength(row,key):
        def v(k):return _num(row.get(k))
        if key=="ataque":return v("xg") if v("xg") is not None else v("chutes")
        if key=="defesa":return v("sofridos")
        if key=="criatividade":return v("chances") if v("chances") is not None else v("passes")
        if key=="gols":return v("gols")
        if key=="evitar":return v("sofridos")
        if key=="eficiencia":return v("gols")/v("chutes") if v("chutes") else None
        if key=="parada_of":return v("bola_parada")
        if key=="parada_def":return None  # xG de bola parada sofrido não existe nesse agregado.
        if key=="aerea_of":return v("aereas_ganhas")
        if key=="aerea_def":return v("aereas_ganhas")/v("aereas") if v("aereas") else None
        return None
    keys1=["ataque","defesa","criatividade","gols","evitar","eficiencia"]
    keys2=["ataque","defesa","parada_of","parada_def","aerea_of","aerea_def"]
    def group(keys,labels):
        values=[]
        for k in keys:
            v=strength(club,k)
            peers=[strength(x,k) for x in all_teams]
            values.append(_normalize(v,peers,k in ("defesa","evitar")))
        return {"labels":labels,"values":values}
    return {"geral":group(keys1,RADAR_BASE),"fundamentos":group(keys2,RADAR_ESP),
            "jogos_com_estatisticas":club.get("jogos")}


def _poisson(k,lam):
    return math.exp(-lam+k*math.log(lam)-math.lgamma(k+1))


def _dist(lh,la,max_goals=13):
    # Todas as combinações 0..13 + probabilidade residual agregada em 'Outro'.
    return {(h,a):_poisson(h,lh)*_poisson(a,la) for h in range(max_goals+1) for a in range(max_goals+1)}


def _markets(lh,la):
    probs=_dist(lh,la)
    p=lambda f:sum(v for (h,a),v in probs.items() if f(h,a))
    pt=sum(probs.values())
    residual=max(0.0,1-pt)
    # Em caudas omitidas, o resultado exato dificilmente influencia; inclusão conservadora
    # nas probabilidades de vitória conforme parcela proporcional das médias de gols.
    residual_home=residual*lh/(lh+la)
    residual_away=residual*la/(lh+la)
    over=lambda line:1-sum(_poisson(k,lh+la) for k in range(int(line)+1))
    btts=(1-math.exp(-lh))*(1-math.exp(-la))
    pv_home=p(lambda h,a:h>a)+residual_home
    pv_away=p(lambda h,a:h<a)+residual_away
    draw=_clamp(1-pv_home-pv_away,0,1)
    # Mandante/visitante chegar a 1-0 ao intervalo de 60min, como estado exato no 60'.
    h60=lh*2/3;a60=la*2/3
    first_home=(1-math.exp(-(lh+la)))*lh/(lh+la)
    first_away=(1-math.exp(-(lh+la)))*la/(lh+la)
    market={
        "over_05_ht":1-math.exp(-0.46*(lh+la)),
        "over_05_ft":over(.5),"over_15":over(1.5),"over_25":over(2.5),
        "over_35":over(3.5),"under_35":1-over(3.5),"ambos_marcam":btts,
        "goleada_mandante":p(lambda h,a:h-a>=3)+residual_home,
        "goleada_visitante":p(lambda h,a:a-h>=3)+residual_away,
        "mandante_1x0_60":_poisson(1,h60)*_poisson(0,a60),
        "visitante_1x0_60":_poisson(0,h60)*_poisson(1,a60),
        "mandante_abrir":first_home,"visitante_abrir":first_away,
        "mandante":pv_home,"empate":draw,"visitante":pv_away,
        "mandante_ou_empate":1-pv_away,"visitante_ou_empate":1-pv_home,
        "lay_mandante":1-pv_home,"lay_visitante":1-pv_away,
        "lay_goleada_mandante":1-(p(lambda h,a:h-a>=3)+residual_home),
        "lay_goleada_visitante":1-(p(lambda h,a:a-h>=3)+residual_away),
        "placar_1x0":probs[(1,0)],"placar_0x1":probs[(0,1)],
        "lay_1x0":1-probs[(1,0)],"lay_0x1":1-probs[(0,1)],
    }
    order=[
      (1,0),(1,1),(2,0),(3,0),(2,1),(2,2),(3,1),(3,2),(3,3),
      (0,1),(0,2),(0,3),(1,2),(1,3),(2,3),
      (0,0),(0,4),(4,0),(4,1),(1,4),(4,2),(2,4),(4,3),(3,4),(4,4),
    ]
    out=[{"placar":f"{h}x{a}","probabilidade":round(probs[(h,a)],6)} for h,a in order]
    other=max(0.0,1-sum(e["probabilidade"] for e in out))
    out.append({"placar":"Outro placar","probabilidade":round(other,6)})
    return market,out


def _odds(market,commission=0.02,edge=0.03):
    items={}
    for key in [
        "mandante","visitante","over_05_ft","over_15","over_25","ambos_marcam",
        "lay_mandante","lay_visitante","lay_goleada_mandante",
        "lay_goleada_visitante","lay_1x0","lay_0x1",
    ]:
        lay=key.startswith("lay_")
        p=market[key[4:]] if lay and key[4:] in market else None
        if lay and key=="lay_goleada_mandante":p=market["goleada_mandante"]
        if lay and key=="lay_goleada_visitante":p=market["goleada_visitante"]
        if lay and key=="lay_1x0":p=market["placar_1x0"]
        if lay and key=="lay_0x1":p=market["placar_0x1"]
        if not lay:p=market[key]
        p=_clamp(p or 0,1e-7,1-1e-7)
        fair=1/p
        # EV alvo em unidade apostada (back = stake; lay = valor ganho se seleção perder).
        # Lay gera EV positivo se odds ofertadas < limite. Comissão incide no ganho lay.
        threshold=1+((1-p)*(1-commission)-edge)/p if lay else (1+edge)/p
        items[key]={
            "prob_evento":round(p,6),"odd_justa":round(fair,3),
            "limite_odd_ev_3pct":round(threshold,3) if threshold>=1.01 else None,
            "sentido":"maxima" if lay else "minima"
        }
    return items


def avaliar(campeonato_id,mandante_id,visitante_id,temporada=None):
    if mandante_id==visitante_id:
        raise ValueError("Mandante e visitante devem ser clubes diferentes.")
    meta=fetch_all("""
        SELECT c.id,c.nome, p.nome AS pais, j.temporada,
               count(distinct j.id) AS jogos
        FROM campeonatos c JOIN jogos j ON j.campeonato_id=c.id
        LEFT JOIN paises p ON p.id=c.pais_id
        WHERE c.id=%s AND j.gols_casa IS NOT NULL
        GROUP BY c.id,c.nome,p.nome,j.temporada
        ORDER BY j.temporada DESC
    """,(campeonato_id,))
    if not meta:raise ValueError("Campeonato não encontrado ou sem jogos.")
    seasons=[r["temporada"] for r in meta]
    temporada=temporada if temporada in seasons else seasons[0]
    clubs=fetch_all("""
        SELECT c.id,c.clube, cf.id_externo AS fotmob_id
        FROM clubes c
        JOIN (
          SELECT casa_id id FROM jogos WHERE campeonato_id=%s AND temporada=%s
          UNION SELECT fora_id id FROM jogos WHERE campeonato_id=%s AND temporada=%s
        ) t ON t.id=c.id
        LEFT JOIN clubes_fontes cf ON cf.clube_id=c.id AND cf.fonte='fotmob'
        ORDER BY c.clube
    """,(campeonato_id,temporada,campeonato_id,temporada))
    club_map={int(x["id"]):_serialize(x) for x in clubs}
    if mandante_id not in club_map or visitante_id not in club_map:
        raise ValueError("Selecione dois clubes participantes desta edição.")
    games,lh,la,counts,info=_models(campeonato_id,temporada,mandante_id,visitante_id)
    stats=_team_stats(campeonato_id,temporada)
    a=stats.get(mandante_id,{});b=stats.get(visitante_id,{})
    if min(counts.values())<4:raise ValueError("Amostra insuficiente: cada clube precisa de 4 jogos concluídos.")
    # Ajuste conservador com xG se houver cobertura estatística suficiente.
    league_xg=[_num(s.get("xg")) for s in stats.values()]
    league_xg=[x for x in league_xg if x is not None]
    xga=_num(a.get("xg"));xgb=_num(b.get("xg"))
    if xga is not None and xgb is not None and len(league_xg)>=4:
        mu=sum(league_xg)/len(league_xg)
        if mu>0:
            lh=_clamp(0.8*lh+0.2*lh*_clamp(xga/mu,0.65,1.5),0.2,4.3)
            la=_clamp(0.8*la+0.2*la*_clamp(xgb/mu,0.65,1.5),0.2,4.3)
            info["ajuste_xg"]=True
    probs,scores=_markets(lh,la)
    peer=list(stats.values())
    report_home=club_map[mandante_id]["clube"];report_away=club_map[visitante_id]["clube"]
    maxres=max(scores[:-1],key=lambda x:x["probabilidade"])
    quality_note=("Há poucos jogos para pelo menos um clube, portanto a incerteza é elevada."
                  if min(counts.values())<10 else
                  "O modelo é uma estimativa de gols e não incorpora escalações confirmadas, lesões nem odds ao vivo.")
    report=[
        f"Para {report_home} x {report_away}, o modelo estima {lh:.2f} gol(s) do mandante e "
        f"{la:.2f} do visitante. As chances aproximadas de vitória são "
        f"{probs['mandante']*100:.1f}% para {report_home}, {probs['empate']*100:.1f}% de empate "
        f"e {probs['visitante']*100:.1f}% para {report_away}. Entre os placares detalhados, "
        f"{maxres['placar']} é o mais provável ({maxres['probabilidade']*100:.1f}%).",
        f"A projeção de mais de 2,5 gols é {probs['over_25']*100:.1f}% e a de ambos marcarem "
        f"é {probs['ambos_marcam']*100:.1f}%. A análise considera {info['n']} partidas do histórico "
        f"da competição, com regularização das forças de ataque e defesa e ajuste parcial por xG quando disponível. "
        f"{quality_note}"
    ]
    return {
        "campeonato":{"id":campeonato_id,"nome":meta[0]["nome"],"pais":meta[0]["pais"]},
        "temporada":temporada,
        "mandante":{**club_map[mandante_id],"jogos":counts[mandante_id],"xg_jogo":xga,
                    "radar":_radars(a,peer) if a else None},
        "visitante":{**club_map[visitante_id],"jogos":counts[visitante_id],"xg_jogo":xgb,
                    "radar":_radars(b,peer) if b else None},
        "gols_esperados":{"mandante":round(lh,3),"visitante":round(la,3)},
        "probabilidades":{k:round(v,6) for k,v in probs.items()},
        "placares":scores,"odds":_odds(probs),
        "modelo":{"nome":"Poisson regularizado por time","amostra_jogos":info["n"],
                  "temporadas_treino":info["temporadas"],"ajuste_xg":info.get("ajuste_xg",False),
                  "jogos_mandante":counts[mandante_id],"jogos_visitante":counts[visitante_id],
                  "aviso":"Projeção estatística hipotética, não calibrada em validação externa. HT usa fração estimada de 46% dos gols; 1x0 aos 60' é o placar exato no minuto 60. Força aérea defensiva usa disputas aéreas ganhas como proxy; bola parada defensiva fica sem nota quando faltam dados.",
                  "criterio_goleada":"Diferença de pelo menos 3 gols ao final."},
        "relatorio":report,
    }
