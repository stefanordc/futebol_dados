"""Backtest de cenários ao vivo com gols reais no minuto de entrada.

Não são usadas odds pré-jogo como se fossem odds in-play. Os resultados
financeiros só aparecem com uma cotação hipotética informada pelo usuário.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from collections import defaultdict

from db import fetch_all
import queries_nostradamus as ns


# Só considera jogos com mapa de finalizações e TODOS os gols conferindo
# com o placar oficial, inclusive gols contra. Sem essa conferência, a
# ausência de evento poderia produzir placares parciais inventados.
SQL = """
WITH gols AS (
    SELECT f.jogo_id,
      COUNT(*) FILTER (
        WHERE f.tipo_evento='Gol' AND (
          (f.mando='Casa' AND COALESCE(f.foi_gol_contra,false)=false)
          OR (f.mando='Fora' AND f.foi_gol_contra=true)
        )
      ) AS gols_casa_conferidos,
      COUNT(*) FILTER (
        WHERE f.tipo_evento='Gol' AND (
          (f.mando='Fora' AND COALESCE(f.foi_gol_contra,false)=false)
          OR (f.mando='Casa' AND f.foi_gol_contra=true)
        )
      ) AS gols_fora_conferidos,
      COUNT(*) FILTER (
        WHERE f.tipo_evento='Gol'
          AND (f.minuto+COALESCE(f.minuto_adicional,0))<=%s
          AND (
            (f.mando='Casa' AND COALESCE(f.foi_gol_contra,false)=false)
            OR (f.mando='Fora' AND f.foi_gol_contra=true)
          )
      ) AS gols_casa_minuto,
      COUNT(*) FILTER (
        WHERE f.tipo_evento='Gol'
          AND (f.minuto+COALESCE(f.minuto_adicional,0))<=%s
          AND (
            (f.mando='Fora' AND COALESCE(f.foi_gol_contra,false)=false)
            OR (f.mando='Casa' AND f.foi_gol_contra=true)
          )
      ) AS gols_fora_minuto
    FROM public.finalizacoes f
    WHERE f.tipo_evento='Gol' OR f.tipo_evento IS NOT NULL
    GROUP BY f.jogo_id
)
SELECT j.id,j.data,j.campeonato_id,c.nome AS campeonato,
       h.clube AS mandante,v.clube AS visitante,
       j.gols_casa,j.gols_fora,
       g.gols_casa_minuto,g.gols_fora_minuto,
       oa.odd_1_ft AS api_odd_1_ft,
       oa.odd_2_ft AS api_odd_2_ft
FROM public.jogos j
JOIN public.campeonatos c ON c.id=j.campeonato_id
JOIN public.clubes h ON h.id=j.casa_id
JOIN public.clubes v ON v.id=j.fora_id
JOIN gols g ON g.jogo_id=j.id
LEFT JOIN LATERAL (
  SELECT MAX(o.odd_1_ft) AS odd_1_ft,MAX(o.odd_2_ft) AS odd_2_ft
  FROM public.odds o
  WHERE o.mandante_id=j.casa_id AND o.visitante_id=j.fora_id
    AND o.data_jogo::date=j.data
    AND REPLACE(o.temporada,'-','/')=j.temporada
    AND LOWER(BTRIM(o.campeonato))=LOWER(BTRIM(c.nome))
  HAVING COUNT(*)=1
) oa ON TRUE
WHERE j.data<=%s AND j.data<CURRENT_DATE
  AND j.gols_casa IS NOT NULL AND j.gols_fora IS NOT NULL
  AND g.gols_casa_conferidos=j.gols_casa
  AND g.gols_fora_conferidos=j.gols_fora
  AND (%s::integer[] IS NULL OR j.campeonato_id=ANY(%s::integer[]))
ORDER BY j.data,j.id
LIMIT 20000
"""


def _int_exact(value,name,required=False,low=0,high=30):
    if value in (None,""):
        if required:
            raise ValueError("Informe "+name+".")
        return None
    if type(value) is not int or not low<=value<=high:
        raise ValueError(name+" deve ser um número inteiro de "+str(low)+" a "+str(high)+".")
    return value


def _config(payload):
    if not isinstance(payload,dict):
        raise ValueError("Informe as condições do cenário.")
    minute=_int_exact(payload.get("minuto"),"o minuto",True,1,90)
    try:
        cutoff=date.fromisoformat(payload.get("corte"))
    except (TypeError,ValueError):
        raise ValueError("Informe uma data de corte válida.") from None
    if cutoff>date.today():
        raise ValueError("A data de corte não pode estar no futuro.")
    winner=payload.get("vencendo","favorito")
    if winner not in ("favorito","zebra","mandante","visitante","empate","qualquer"):
        raise ValueError("Escolha quem está vencendo no minuto de entrada.")
    market=payload.get("mercado")
    if market not in ns.MERCADOS:
        raise ValueError("Escolha um mercado de entrada válido.")
    window=str(payload.get("jogos","20"))
    if window not in ("5","10","20","temporada"):
        raise ValueError("Recorte de partidas anteriores inválido.")
    conditions=payload.get("condicoes",[])
    if not isinstance(conditions,list) or len(conditions)>10:
        raise ValueError("Selecione de 0 a 10 condições pré-jogo.")
    conditions=ns._valid_conditions(conditions) if conditions else []
    names={
        "gols_favorito":"Gols do favorito",
        "gols_zebra":"Gols da zebra",
        "gols_mandante":"Gols do mandante",
        "gols_visitante":"Gols do visitante",
        "gols_total":"Total de gols",
        "diferenca_gols":"Diferença de gols",
    }
    goals={key:_int_exact(payload.get(key),label) for key,label in names.items()}
    for role in ("gols_favorito","gols_zebra","gols_mandante","gols_visitante"):
        for suffix,label in (("_min","mínimos"),("_max","máximos")):
            key=role+suffix
            goals[key]=_int_exact(payload.get(key),names[role]+" "+label)
        minimum=goals[role+"_min"]
        maximum=goals[role+"_max"]
        if minimum is not None and maximum is not None and minimum>maximum:
            raise ValueError("O mínimo de "+names[role].lower()+" não pode superar o máximo.")
    if winner=="empate" and goals["diferenca_gols"] not in (None,0):
        raise ValueError("Em um empate, a diferença de gols deve ser zero.")
    odd=payload.get("odd_hipotetica")
    if odd in (None,""):
        odd=None
    else:
        if isinstance(odd,bool):
            raise ValueError("Odd hipotética inválida.")
        odd=ns._n(odd)
        if odd is None or not 1.01<=odd<=1000:
            raise ValueError("Odd hipotética deve estar entre 1,01 e 1000.")
    leagues=ns.ligas_selecionadas(payload)
    return {"minuto":minute,"corte":cutoff,"vencendo":winner,"mercado":market,
            "odd_hipotetica":odd,"campeonato_ids":leagues,
            "jogos":window,"condicoes":conditions,**goals}


def _matches(row,config):
    favorite_home=ns._favorite_home(row)
    h=int(row["gols_casa_minuto"])
    a=int(row["gols_fora_minuto"])
    gap=abs(h-a)
    leader="mandante" if h>a else "visitante" if a>h else "empate"
    favorite="mandante" if favorite_home else "visitante" if favorite_home is False else None
    underdog="visitante" if favorite_home else "mandante" if favorite_home is False else None
    target={"favorito":favorite,"zebra":underdog,
            "mandante":"mandante","visitante":"visitante",
            "empate":"empate","qualquer":leader}[config["vencendo"]]
    if target is None or (config["vencendo"]!="qualquer" and leader!=target):
        return None
    if config["diferenca_gols"] is not None and gap!=config["diferenca_gols"]:
        return None
    numeric={"gols_mandante":h,"gols_visitante":a,"gols_total":h+a}
    if favorite is not None:
        numeric["gols_favorito"]=h if favorite_home else a
        numeric["gols_zebra"]=a if favorite_home else h
    for key in ("gols_mandante","gols_visitante","gols_total",
                "gols_favorito","gols_zebra"):
        exact=config[key]
        minimum=config.get(key+"_min")
        maximum=config.get(key+"_max")
        if exact is None and minimum is None and maximum is None:
            continue
        value=numeric.get(key)
        if value is None or (exact is not None and value!=exact) or (
            minimum is not None and value<minimum
        ) or (maximum is not None and value>maximum):
            return None
    if config["mercado"] in (
        "back_favorito","lay_favorito","back_zebra","lay_zebra",
        "lay_goleada_favorito","lay_goleada_zebra"
    ) and favorite_home is None:
        return None
    return favorite_home,leader


def _contexto_prejogo(rows,game_ids,window,cutoff,allowed):
    """Indicadores somente de partidas anteriores, inclusive sem contaminação
    entre confrontos realizados no mesmo dia.
    """
    from itertools import groupby
    history=defaultdict(list)
    snapshots={}
    length=None if window=="temporada" else int(window)
    normalized=[]
    for row in rows:
        day=row["data"]
        if isinstance(day,str):
            day=date.fromisoformat(day)
        if day>cutoff or day>=date.today() or (
            allowed is not None and row["campeonato_id"] not in allowed
        ):
            continue
        if row.get("gols_casa") is None or row.get("gols_fora") is None:
            continue
        normalized.append({**row,"data":day})
    normalized.sort(key=lambda row:(row["data"],int(row["id"])))
    for day,group in groupby(normalized,key=lambda row:row["data"]):
        games=list(group)
        # Importante: extrair TODOS os indicadores antes de inserir qualquer
        # partida do dia no histórico.
        for g in games:
            if int(g["id"]) not in game_ids:
                continue
            hkey=(g["campeonato_id"],g["temporada"],g["casa_id"])
            akey=(g["campeonato_id"],g["temporada"],g["fora_id"])
            snapshots[int(g["id"])]=(
                g,ns._stats(history[hkey],length),ns._stats(history[akey],length)
            )
        for g in games:
            hkey=(g["campeonato_id"],g["temporada"],g["casa_id"])
            akey=(g["campeonato_id"],g["temporada"],g["fora_id"])
            history[hkey].append(ns._history_item(g,"home"))
            history[akey].append(ns._history_item(g,"away"))
    return snapshots


def _check_conditions(game,stats_home,stats_away,favorite_home,conditions):
    """Usa as mesmas regras/avaliações da aba Simular estratégia."""
    if not conditions:
        return []
    if stats_home is None or stats_away is None or game is None:
        return None
    if ns._requires_favorite("back_empate",conditions) and favorite_home is None:
        return None
    details=[]
    for rule in conditions:
        if rule.get("tipo")=="odd":
            try:
                actual=ns._market_for_game(rule["mercado"],favorite_home)
            except ValueError:
                return None
            price,origin=ns._odds_for_game(game,actual,None)
            if price is None or (
                rule["odd_min"] is not None and price<rule["odd_min"]
            ) or (
                rule["odd_max"] is not None and price>rule["odd_max"]
            ):
                return None
            details.append({
                "tipo":"odd","mercado":rule["mercado"],
                "nome":ns.ODD_FILTER_MARKETS[rule["mercado"]],
                "odd":price,"fonte":origin,
                "odd_min":rule["odd_min"],"odd_max":rule["odd_max"],
            })
        else:
            evaluated=ns._evaluate_condition(rule,stats_home,stats_away,favorite_home)
            if evaluated is None:
                return None
            details.append(evaluated)
    return details


def _live_rows(config,rows):
    allowed=set(config["campeonato_ids"]) if config["campeonato_ids"] is not None else None
    result=[]
    for raw in sorted(rows,key=lambda g:(str(g["data"]),int(g["id"]))):
        day=raw["data"]
        if isinstance(day,str):
            day=date.fromisoformat(day)
        if day>config["corte"] or day>=date.today() or (
            allowed is not None and raw["campeonato_id"] not in allowed
        ) or raw.get("gols_casa_minuto") is None or raw.get("gols_fora_minuto") is None:
            continue
        result.append(({**raw,"data":day},_matches(raw,config)))
    return result


def simular(payload,rows=None,history_rows=None,capture=False):
    c=_config(payload)
    games=rows if rows is not None else fetch_all(SQL,(
        c["minuto"],c["minuto"],c["corte"],
        c["campeonato_ids"],c["campeonato_ids"]))
    live=_live_rows(c,games)
    candidates=[row for row,match in live if match is not None]
    snapshots={}
    if (c["condicoes"] or capture) and candidates:
        if history_rows is None:
            predicate=""
            params=[c["corte"]]
            if c["campeonato_ids"] is not None:
                predicate="AND j.campeonato_id = ANY(%s::integer[])"
                params.append(c["campeonato_ids"])
            history_rows=fetch_all(ns.RAW.format(competition=predicate),params)
        snapshots=_contexto_prejogo(
            history_rows,{int(r["id"]) for r in candidates},c["jogos"],
            c["corte"],set(c["campeonato_ids"]) if c["campeonato_ids"] is not None else None)
    by_league=defaultdict(ns._novo_resumo)
    overall=ns._novo_resumo()
    details=[]
    eligible=len(live)
    candidate_records=[]
    for row,match in live:
        if match is None:
            continue
        favorite_home,leader=match
        ctx=snapshots.get(int(row["id"]))
        pregame=ctx[0] if ctx else None
        stats_home=ctx[1] if ctx else None
        stats_away=ctx[2] if ctx else None
        if c["condicoes"]:
            passed=_check_conditions(pregame,stats_home,stats_away,favorite_home,c["condicoes"])
            if passed is None:
                if capture and pregame is not None and stats_home is not None and stats_away is not None:
                    # Keep historical candidates for testing removal of rules.
                    pass
                else:
                    continue
        else:
            passed=[]
        settled_market=ns._market_for_game(c["mercado"],favorite_home)
        won=ns._settle(settled_market,int(row["gols_casa"]),int(row["gols_fora"]))
        odd=c["odd_hipotetica"]
        units=ns._units(won,settled_market,odd,0.045)
        if capture and ctx and stats_home is not None and stats_away is not None:
            candidate_records.append({
                "id":row["id"],"data":row["data"].isoformat(),
                "partida":pregame,"stats_casa":stats_home,"stats_fora":stats_away,
                "favorito_casa":favorite_home,"unidades":units,
                "passes_initial":passed is not None,
            })
        if passed is None:
            continue
        league=by_league[str(row["campeonato"])]
        ns._registrar_entrada(league,won,odd,units)
        ns._registrar_entrada(overall,won,odd,units)
        item={
            "id":row["id"],"data":row["data"].isoformat(),
            "campeonato":row["campeonato"],
            "mandante":row["mandante"],"visitante":row["visitante"],
            "placar_minuto":str(row["gols_casa_minuto"])+"x"+str(row["gols_fora_minuto"]),
            "placar_final":str(row["gols_casa"])+"x"+str(row["gols_fora"]),
            "lider":leader,
            "favorito":(row["mandante"] if favorite_home else row["visitante"])
                if favorite_home is not None else None,
            "mercado":settled_market,"green":won,
            "odd":odd,"cotacao":"hipotetica" if odd is not None else None,
            "unidades":round(units,3) if units is not None else None,
            "valor_reais":round(units*100,2) if units is not None else None,
            "condicoes":passed,
        }
        if len(details)<400:
            details.append(item)
        if len(league["jogos"])<400:
            league["jogos"].append(item)
    summaries=[]
    for league,record in sorted(by_league.items()):
        record["campeonato"]=league
        ns._fechar_resumo(record)
        summaries.append(record)
    ns._fechar_resumo(overall)
    del overall["jogos"]
    result={
        "configuracao":{**c,"corte":c["corte"].isoformat()},
        "jogos_com_placar_auditavel":eligible,
        "entradas":overall["entradas"],
        "total":overall,
        "resultados":summaries,
        "detalhes":details,
        "limite_detalhes":400,
        "aviso":"O placar no minuto indicado vem da tabela finalizacoes. Jogos com "
                "gols que não conferem com o placar oficial são excluídos. "
                "Condições pré-jogo usam apenas partidas anteriores, com ao menos 5 jogos "
                "do mesmo clube, campeonato e temporada. "
                "Favorito/zebra dependem de odds 1X2 vinculadas, sem garantia de que "
                "a cotação tenha sido capturada antes do jogo. "
                "Não há odds in-play históricas verificáveis: o resultado financeiro "
                "e as sugestões da IA utilizam exclusivamente a odd HIPOTÉTICA informada. "
                "Stake/responsabilidade = R$ 100, comissão Lay = 4,5%. "
                "Uma entrada real no minuto escolhido não é comprovada por esta simulação."
    }
    if capture:
        result["_dados_otimizacao"]=candidate_records
    return result


def analisar(payload,rows=None,history_rows=None):
    """IA quantitativa: sugestões pré-jogo para o MESMO cenário in-play.

    Escolha de regras apenas no treino cronológico. Testa em datas posteriores
    sem utilizar o resultado futuro para a seleção de sugestões.
    """
    from math import ceil
    import queries_nostradamus_ai as ai
    config=_config(payload)
    if config["odd_hipotetica"] is None:
        return {"sugestoes":[],"mensagem":"Informe uma odd hipotética de entrada para analisar o financeiro.",
                "metodo":"IA quantitativa com treino cronológico e validação posterior."}
    result=simular(payload,rows=rows,history_rows=history_rows,capture=True)
    candidates=result.pop("_dados_otimizacao")
    base=[r for r in candidates if r["passes_initial"] and r["unidades"] is not None]
    train,validation,boundary=ai._split(base)
    if len(train)<ai.MIN_BASE_TRAIN or len(validation)<ai.MIN_BASE_VALID:
        return {"sugestoes":[],"corte":config["corte"].isoformat(),
                "base":ai._score(base),
                "mensagem":"Amostra insuficiente: a IA requer pelo menos 8 entradas no treino e 5 na validação, em datas distintas, com indicadores pré-jogo disponíveis.",
                "metodo":"Regras interpretáveis, treino cronológico 65% e validação 35%."}
    base_train=ai._score(train)
    base_valid=ai._score(validation)
    ranked=[]
    rules=config["condicoes"]
    # Inclusões se ainda houver espaço: só filtram a amostra de treino.
    if len(rules)<10:
        existing={str(x) for x in rules}
        for proposed in ai._proposals(train):
            normalized=ns._valid_conditions([proposed])[0]
            if str(normalized) in existing:
                continue
            older=[r for r in train if ai._passes(r,normalized)]
            if len(older)<max(ai.MIN_CANDIDATE_TRAIN,ceil(len(train)*.4)) or len(older)==len(train):
                continue
            score=ai._score(older)
            if score["total_reais"]<=base_train["total_reais"] or (
                score["media_reais"]<=base_train["media_reais"]
            ):
                continue
            ranked.append({
                "acao":"adicionar","condicao":normalized,"indice":None,
                "descricao":ai._display(normalized),"treino":score,
                "ganho":score["total_reais"]-base_train["total_reais"],
                "ganho_medio":score["media_reais"]-base_train["media_reais"]
            })
    # Remoções: avalia também candidatos bloqueados pela regra excluída.
    if len(rules)>0:
        for i in range(len(rules)):
            remaining=[x for j,x in enumerate(rules) if j!=i]
            sampled=[
                r for r in candidates
                if r["unidades"] is not None
                and _check_conditions(r["partida"],r["stats_casa"],r["stats_fora"],
                                      r["favorito_casa"],remaining) is not None
            ]
            older=[r for r in sampled if r["data"]<=boundary]
            if len(older)<max(ai.MIN_CANDIDATE_TRAIN,ceil(len(train)*.4)):
                continue
            score=ai._score(older)
            if score["total_reais"]<=base_train["total_reais"] or (
                score["media_reais"]<=base_train["media_reais"]
            ):
                continue
            ranked.append({
                "acao":"remover","condicao":None,"indice":i,
                "descricao":"Remover regra "+str(i+1)+": "+ai._display_original(rules[i]),
                "treino":score,
                "ganho":score["total_reais"]-base_train["total_reais"],
                "ganho_medio":score["media_reais"]-base_train["media_reais"],
                "validacao_candidates":[r for r in sampled if r["data"]>boundary]
            })
    ranked.sort(key=lambda item:(
        -item["ganho"],-item["ganho_medio"],
        -item["treino"]["entradas"],item["descricao"]
    ))
    top=[]
    for suggestion in ranked[:3]:
        if suggestion["acao"]=="remover":
            newer=suggestion.pop("validacao_candidates")
        else:
            newer=[r for r in validation if ai._passes(r,suggestion["condicao"])]
        validated=ai._score(newer)
        top.append({
            "acao":suggestion["acao"],"indice":suggestion["indice"],
            "descricao":suggestion["descricao"],
            "condicao":suggestion["condicao"],
            "treino":suggestion["treino"],"validacao":validated,
            "avaliacao":("Sinal positivo na validação"
                if len(newer)>=ai.MIN_CANDIDATE_VALID and
                validated["media_reais"] is not None and
                validated["media_reais"]>base_valid["media_reais"]
                else "Sem confirmação na validação")
        })
    return {
        "corte":config["corte"].isoformat(),
        "data_divisao":boundary,
        "base_treino":base_train,"base_validacao":base_valid,
        "sugestoes":top,"avaliadas":len(ranked),
        "metodo":"IA quantitativa: seleção por treino cronológico 65%, validação posterior 35%.",
        "mensagem":("Sugestões selecionadas exclusivamente no treino; avaliação de validação exibida separadamente."
                    if top else "Nenhuma regra melhorou lucro total e médio no treino com amostra mínima."),
        "aviso":"Amostras e valores financeiros dependem de odd hipotética, não de cotações de mercado aos 60 minutos. Resultado retrospectivo não comprova rentabilidade."
    }
