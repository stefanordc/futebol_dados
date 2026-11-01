"""Indicadores físicos por jogo/clube, com IDs de origem distintos.

Dados físicos usam id_campeonato / id_jogo / id_clube da origem.
O site usa IDs internos em campeonatos, jogos e clubes.
Não exige placar para calcular médias de KM e sprints. Apenas consultas SELECT.
"""
from __future__ import annotations

from functools import lru_cache
from db import fetch_all, fetch_one
from queries import _serialize, clube_match_key


# Nomes de competições duplicadas por fonte no cadastro existente.
# Comparação por nome + país; nunca assume que id interno seja id externo.
_NOMES_ORIGEM = {
    "LaLiga": "Espanhol",
    "Serie A": "Italiano",
    "Premier League": "Inglês",
}


@lru_cache(maxsize=64)
def _campeonato_origem(campeonato_id: int) -> int | None:
    """Descobre o campeonato em dados_fisicos sem misturar IDs internos/externos."""
    item = fetch_one("""
        SELECT c.nome, c.id_sofascore, p.nome AS pais
        FROM campeonatos c
        LEFT JOIN paises p ON p.id = c.pais_id
        WHERE c.id = %s
    """, (campeonato_id,))
    if not item:
        return None
    if item.get("id_sofascore") is not None:
        return int(item["id_sofascore"])

    nome = _NOMES_ORIGEM.get(item["nome"], item["nome"])
    pais = item.get("pais")
    if not pais:
        return None
    encontrados = fetch_all("""
        SELECT DISTINCT id_campeonato
        FROM dados_fisicos
        WHERE LOWER(TRIM(campeonato)) = LOWER(TRIM(%s))
          AND LOWER(TRIM(pais)) = LOWER(TRIM(%s))
          AND id_campeonato IS NOT NULL
        LIMIT 2
    """, (nome, pais))
    # Se houver mais de um ID externo para o mesmo nome/país, não adivinhar.
    return int(encontrados[0]["id_campeonato"]) if len(encontrados) == 1 else None


# Primeiro usa o mapeamento de IDs do SofaScore.
# Para brasileiros (sem clubes_fontes SofaScore), utiliza nome EXATO único
# no cadastro, sem normalização fuzzy nem associação por id_clube arbitrário.
# A confirmação do clube participante na edição é feita na consulta filtrada.
_BASE = """
WITH base AS (
    SELECT f.id_campeonato AS campeonato_origem, f.id_jogo AS jogo_origem,
           f.temporada, f.pais, f.clube,
           COALESCE(cf.clube_id, pelo_nome.clube_id) AS clube_id,
           LOWER(TRIM(COALESCE(f.mando,''))) AS mando,
           NULLIF(f.distancia_percorrida, 0) AS km,
           NULLIF(f.sprints, 0) AS sprints,
           CASE
             WHEN j.gols_casa IS NULL OR j.gols_fora IS NULL THEN NULL
             WHEN COALESCE(cf.clube_id,pelo_nome.clube_id) = j.casa_id
                  THEN j.gols_casa > j.gols_fora
             WHEN COALESCE(cf.clube_id,pelo_nome.clube_id) = j.fora_id
                  THEN j.gols_fora > j.gols_casa
             ELSE NULL
           END AS venceu
    FROM dados_fisicos f
    LEFT JOIN clubes_fontes cf
      ON cf.fonte = 'sofascore' AND cf.id_externo = f.id_clube::text
    LEFT JOIN LATERAL (
       SELECT CASE WHEN COUNT(*) = 1 THEN MIN(c.id) END AS clube_id
       FROM clubes c
       WHERE LOWER(TRIM(c.clube)) = LOWER(TRIM(f.clube))
    ) pelo_nome ON cf.clube_id IS NULL
    LEFT JOIN jogos j ON j.id_sofascore = f.id_jogo
    WHERE (f.distancia_percorrida > 0 OR f.sprints > 0)
      AND f.temporada = %s
      {filtros_origem}
)
SELECT b.clube_id, MIN(b.clube) AS clube,
       COUNT(DISTINCT (b.campeonato_origem,b.jogo_origem)) AS jogos_fisico,
       SUM(b.km) AS sum_distancia_percorrida,
       AVG(b.km) AS avg_distancia_percorrida,
       SUM(b.sprints) AS sum_sprints,
       AVG(b.sprints) AS avg_sprints,
       COUNT(b.km) AS jogos_km, COUNT(b.sprints) AS jogos_sprints,
       AVG(b.km) FILTER(WHERE b.mando = 'casa') AS km_casa,
       AVG(b.km) FILTER(WHERE b.mando = 'fora') AS km_fora,
       AVG(b.sprints) FILTER(WHERE b.mando = 'casa') AS sprints_casa,
       AVG(b.sprints) FILTER(WHERE b.mando = 'fora') AS sprints_fora,
       COUNT(b.km) FILTER(WHERE b.mando = 'casa') AS jogos_km_casa,
       COUNT(b.km) FILTER(WHERE b.mando = 'fora') AS jogos_km_fora,
       COUNT(b.sprints) FILTER(WHERE b.mando = 'casa') AS jogos_sprints_casa,
       COUNT(b.sprints) FILTER(WHERE b.mando = 'fora') AS jogos_sprints_fora,
       COUNT(*) FILTER(WHERE b.km > r.km AND r.km IS NOT NULL
                         AND b.venceu IS NOT NULL) AS jogos_mais_km,
       COUNT(*) FILTER(WHERE b.km > r.km AND r.km IS NOT NULL
                         AND b.venceu) AS vit_mais_km,
       COUNT(*) FILTER(WHERE b.sprints > r.sprints AND r.sprints IS NOT NULL
                         AND b.venceu IS NOT NULL) AS jogos_mais_sprints,
       COUNT(*) FILTER(WHERE b.sprints > r.sprints AND r.sprints IS NOT NULL
                         AND b.venceu) AS vit_mais_sprints
FROM base b
LEFT JOIN base r
  ON r.campeonato_origem = b.campeonato_origem
 AND r.jogo_origem = b.jogo_origem
 AND r.clube_id <> b.clube_id
WHERE b.clube_id IS NOT NULL {filtro_participacao}
GROUP BY b.clube_id
"""


def fisicos_lookup(temporada: str, pais: str | None = None,
                   mando: str | None = None,
                   campeonato_id: int | None = None) -> tuple[dict, dict]:
    """Médias válidas por clube; resultados ausentes não anulam indicadores físicos."""
    if not temporada:
        return {}, {}

    args: list = [temporada]
    origem = []
    if campeonato_id is not None:
        identificador = _campeonato_origem(int(campeonato_id))
        if identificador is None:
            return {}, {}
        origem.append("AND f.id_campeonato = %s")
        args.append(identificador)

    if pais:
        origem.append("AND LOWER(TRIM(f.pais)) = LOWER(TRIM(%s))")
        args.append(pais)
    if (mando or "").lower() in ("casa", "fora"):
        origem.append("AND LOWER(TRIM(f.mando)) = %s")
        args.append(mando.lower())

    # Com campeonato informado, evita misturar homônimos que não disputam
    # aquela edição (especialmente no fallback por nome para o Brasileiro).
    participacao = ""
    if campeonato_id is not None:
        participacao = """
        AND EXISTS (
            SELECT 1 FROM jogos jj
            WHERE jj.campeonato_id = %s
              AND jj.temporada = %s
              AND b.clube_id IN (jj.casa_id, jj.fora_id)
        )"""
        args.extend((int(campeonato_id), temporada))

    sql = _BASE.format(
        filtros_origem="\n      ".join(origem),
        filtro_participacao=participacao,
    )
    rows = fetch_all(sql, args)
    by_id, by_key = {}, {}
    for record in rows:
        item = _serialize(record)
        for metric, numerator, denominator in (
            ("pct_vit_mais_km", "vit_mais_km", "jogos_mais_km"),
            ("pct_vit_mais_sprints", "vit_mais_sprints", "jogos_mais_sprints"),
        ):
            n = item.get(denominator) or 0
            value = round(100 * (item.get(numerator) or 0) / n, 1) if n else None
            item["sum_" + metric] = value
            item["avg_" + metric] = value
        club_id = int(item["clube_id"])
        by_id[club_id] = item
        by_key[clube_match_key(item["clube"])] = item
    return by_id, by_key
