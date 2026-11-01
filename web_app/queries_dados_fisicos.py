"""Indicadores físicos por jogo e clube, a partir de dados_fisicos (SofaScore).

id_jogo e id_clube da origem são identificadores EXTERNOS. Ligações verificadas:
jogos.id_sofascore e clubes_fontes(fonte='sofascore', id_externo).
As consultas são somente leitura.
"""
from __future__ import annotations

from db import fetch_all
from queries import _serialize, clube_match_key

_BASE = """
WITH base AS (
    SELECT j.id AS jogo_id, j.campeonato_id, j.temporada, j.casa_id,
           j.fora_id, cf.clube_id, cl.clube,
           CASE WHEN cf.clube_id=j.casa_id THEN 'casa' ELSE 'fora' END AS mando,
           NULLIF(f.distancia_percorrida,0) AS km,
           NULLIF(f.sprints,0) AS sprints,
           CASE WHEN cf.clube_id=j.casa_id
                THEN (j.gols_casa>j.gols_fora)
                ELSE (j.gols_fora>j.gols_casa) END AS venceu
    FROM dados_fisicos f
    JOIN jogos j ON j.id_sofascore = f.id_jogo
    JOIN clubes_fontes cf ON cf.fonte='sofascore'
                         AND cf.id_externo=f.id_clube::text
    JOIN clubes cl ON cl.id=cf.clube_id
    WHERE cf.clube_id IN (j.casa_id,j.fora_id)
      AND (f.distancia_percorrida>0 OR f.sprints>0)
)
SELECT b.clube_id,b.clube,
       COUNT(DISTINCT b.jogo_id) AS jogos_fisico,
       SUM(b.km) AS sum_distancia_percorrida,
       AVG(b.km) AS avg_distancia_percorrida,
       SUM(b.sprints) AS sum_sprints, AVG(b.sprints) AS avg_sprints,
       COUNT(b.km) AS jogos_km, COUNT(b.sprints) AS jogos_sprints,
       AVG(b.km) FILTER (WHERE b.mando='casa') AS km_casa,
       AVG(b.km) FILTER (WHERE b.mando='fora') AS km_fora,
       AVG(b.sprints) FILTER (WHERE b.mando='casa') AS sprints_casa,
       AVG(b.sprints) FILTER (WHERE b.mando='fora') AS sprints_fora,
       COUNT(b.km) FILTER (WHERE b.mando='casa') AS jogos_km_casa,
       COUNT(b.km) FILTER (WHERE b.mando='fora') AS jogos_km_fora,
       COUNT(b.sprints) FILTER (WHERE b.mando='casa') AS jogos_sprints_casa,
       COUNT(b.sprints) FILTER (WHERE b.mando='fora') AS jogos_sprints_fora,
       COUNT(*) FILTER (WHERE b.km>r.km AND r.km IS NOT NULL AND b.venceu IS NOT NULL) AS jogos_mais_km,
       COUNT(*) FILTER (WHERE b.km>r.km AND r.km IS NOT NULL AND b.venceu) AS vit_mais_km,
       COUNT(*) FILTER (WHERE b.sprints>r.sprints AND r.sprints IS NOT NULL AND b.venceu IS NOT NULL) AS jogos_mais_sprints,
       COUNT(*) FILTER (WHERE b.sprints>r.sprints AND r.sprints IS NOT NULL AND b.venceu) AS vit_mais_sprints
FROM base b
LEFT JOIN base r ON r.jogo_id=b.jogo_id AND r.clube_id<>b.clube_id
JOIN campeonatos c ON c.id=b.campeonato_id
LEFT JOIN paises p ON p.id=c.pais_id
WHERE {where}
GROUP BY b.clube_id,b.clube
"""


def fisicos_lookup(temporada: str, pais: str | None = None,
                   mando: str | None = None,
                   campeonato_id: int | None = None) -> tuple[dict,dict]:
    """Agregados de médias, totais, partidas disponíveis e vitórias condicionais.

    Os percentuais descritivos (vitórias quando correu mais) não são parâmetros
    causais: a distância percorrida durante a partida não é conhecida antes dela.
    """
    conditions=["b.temporada = %s"]
    args: list=[temporada]
    if pais:
        conditions.append("p.nome = %s")
        args.append(pais)
    if campeonato_id:
        conditions.append("b.campeonato_id = %s")
        args.append(campeonato_id)
    if (mando or "").lower() in ("casa","fora"):
        conditions.append("b.mando = %s")
        args.append(mando.lower())
    rows=fetch_all(_BASE.format(where=" AND ".join(conditions)),args)
    by_id, by_key={},{}
    for row in rows:
        item=_serialize(row)
        for key,den in [("pct_vit_mais_km","jogos_mais_km"),
                        ("pct_vit_mais_sprints","jogos_mais_sprints")]:
            wins="vit_mais_km" if key.endswith("_km") else "vit_mais_sprints"
            n=item.get(den) or 0
            pct=round(100*item[wins]/n,1) if n else None
            item["sum_"+key]=pct
            item["avg_"+key]=pct
        by_id[int(item["clube_id"])]=item
        by_key[clube_match_key(item["clube"])]=item
    return by_id,by_key
