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
    goals={
        key:_int_exact(payload.get(key),label)
        for key,label in (
            ("gols_favorito","Gols do favorito"),
            ("gols_zebra","Gols da zebra"),
            ("gols_mandante","Gols do mandante"),
            ("gols_visitante","Gols do visitante"),
            ("gols_total","Total de gols"),
            ("diferenca_gols","Diferença de gols")
        )
    }
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
            "odd_hipotetica":odd,"campeonato_ids":leagues,**goals}


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
    for key,value in (
        ("gols_mandante",h),("gols_visitante",a),("gols_total",h+a)
    ):
        if config[key] is not None and config[key]!=value:
            return None
    if config["gols_favorito"] is not None:
        if favorite is None or config["gols_favorito"]!=(h if favorite_home else a):
            return None
    if config["gols_zebra"] is not None:
        if underdog is None or config["gols_zebra"]!=(a if favorite_home else h):
            return None
    # Mercados com favorito/zebra precisam de classificação pelas odds 1X2.
    if config["mercado"] in (
        "back_favorito","lay_favorito","back_zebra","lay_zebra",
        "lay_goleada_favorito","lay_goleada_zebra"
    ) and favorite_home is None:
        return None
    return favorite_home,leader


def simular(payload,rows=None):
    c=_config(payload)
    games=rows if rows is not None else fetch_all(SQL,(
        c["minuto"],c["minuto"],c["corte"],
        c["campeonato_ids"],c["campeonato_ids"]))
    by_league=defaultdict(ns._novo_resumo)
    overall=ns._novo_resumo()
    details=[]
    eligible=0
    for raw in sorted(games,key=lambda g:(str(g["data"]),int(g["id"]))):
        day=raw["data"]
        if isinstance(day,str):
            day=date.fromisoformat(day)
        if day>c["corte"] or day>=date.today() or (
            c["campeonato_ids"] is not None and
            raw["campeonato_id"] not in c["campeonato_ids"]
        ):
            continue
        if raw.get("gols_casa_minuto") is None or raw.get("gols_fora_minuto") is None:
            continue
        eligible+=1
        match=_matches(raw,c)
        if match is None:
            continue
        favorite_home,leader=match
        settled_market=ns._market_for_game(c["mercado"],favorite_home)
        won=ns._settle(settled_market,int(raw["gols_casa"]),int(raw["gols_fora"]))
        units=ns._units(won,settled_market,c["odd_hipotetica"],0.045)
        ns._registrar_entrada(by_league[str(raw["campeonato"])],won,c["odd_hipotetica"],units)
        ns._registrar_entrada(overall,won,c["odd_hipotetica"],units)
        if len(details)<400:
            details.append({
                "id":raw["id"],"data":day.isoformat(),"campeonato":raw["campeonato"],
                "mandante":raw["mandante"],"visitante":raw["visitante"],
                "placar_minuto":str(raw["gols_casa_minuto"])+"x"+str(raw["gols_fora_minuto"]),
                "placar_final":str(raw["gols_casa"])+"x"+str(raw["gols_fora"]),
                "lider":leader,
                "favorito":(raw["mandante"] if favorite_home else raw["visitante"])
                    if favorite_home is not None else None,
                "mercado":settled_market,"green":won,
                "odd":c["odd_hipotetica"],
                "unidades":round(units,3) if units is not None else None,
                "valor_reais":round(units*100,2) if units is not None else None,
            })
    summaries=[]
    for league,record in sorted(by_league.items()):
        record["campeonato"]=league
        ns._fechar_resumo(record)
        del record["jogos"]
        summaries.append(record)
    ns._fechar_resumo(overall)
    del overall["jogos"]
    return {
        "configuracao":{**c,"corte":c["corte"].isoformat()},
        "jogos_com_placar_auditavel":eligible,
        "entradas":overall["entradas"],
        "total":overall,
        "resultados":summaries,
        "detalhes":details,
        "limite_detalhes":400,
        "aviso":"O placar no minuto indicado é reconstruído com gols reais da tabela "
                "finalizacoes; jogos com placar de gols inconsistente são excluídos. "
                "O minuto inclui os gols registrados até o término desse minuto. "
                "Favorito e zebra são identificados por odds 1X2 associadas ao jogo, "
                "sem garantia de captura antes do evento. "
                "A simulação não comprova que havia possibilidade de entrada no minuto indicado. "
                "Não há odds in-play históricas: o financeiro só é calculado quando uma odd "
                "hipotética é informada; stake/responsabilidade = R$ 100 e comissão Lay = 4,5%. "
                "Os greens e reds usam o placar final; não constituem recomendação de aposta."
    }
