"""Consultas da página da liga."""

from __future__ import annotations

from db import fetch_all, fetch_one
from queries import LOGO_LIGA, LOGO_TIME, _serialize


def info_liga(campeonato_id: int) -> dict | None:
    row = fetch_one(
        """
        SELECT c.id, c.nome, c.logo, c.id_fotmob, c.id_sofascore, p.nome AS pais
        FROM campeonatos c
        LEFT JOIN paises p ON p.id = c.pais_id
        WHERE c.id = %s
        """,
        (campeonato_id,),
    )
    if not row:
        return None
    item = _serialize(row)
    if not item.get("logo") and item.get("id_fotmob"):
        item["logo"] = LOGO_LIGA.format(id=item["id_fotmob"])
    return item


def temporadas_liga(campeonato_id: int) -> list[str]:
    rows = fetch_all(
        """
        SELECT DISTINCT temporada
        FROM jogos
        WHERE campeonato_id = %s AND gols_casa IS NOT NULL AND temporada IS NOT NULL
        ORDER BY temporada DESC
        """,
        (campeonato_id,),
    )
    return [r["temporada"] for r in rows]


def temporada_atual(campeonato_id: int) -> str | None:
    temps = temporadas_liga(campeonato_id)
    return temps[0] if temps else None


def _logo_clube(id_fotmob):
    return LOGO_TIME.format(id=id_fotmob) if id_fotmob else None


def classificacao(campeonato_id: int, temporada: str) -> list[dict]:
    rows = fetch_all(
        """
        WITH jogos_ok AS (
          SELECT * FROM jogos
          WHERE campeonato_id = %s AND temporada = %s AND gols_casa IS NOT NULL
        ),
        lados AS (
          SELECT casa_id AS clube_id, gols_casa AS gf, gols_fora AS gs,
                 CASE WHEN gols_casa > gols_fora THEN 1 ELSE 0 END AS v,
                 CASE WHEN gols_casa = gols_fora THEN 1 ELSE 0 END AS e,
                 CASE WHEN gols_casa < gols_fora THEN 1 ELSE 0 END AS d,
                 CASE WHEN gols_fora = 0 THEN 1 ELSE 0 END AS clean_sheets,
                 CASE WHEN gols_casa = 0 THEN 1 ELSE 0 END AS clean_goals
          FROM jogos_ok
          UNION ALL
          SELECT fora_id, gols_fora, gols_casa,
                 CASE WHEN gols_fora > gols_casa THEN 1 ELSE 0 END,
                 CASE WHEN gols_fora = gols_casa THEN 1 ELSE 0 END,
                 CASE WHEN gols_fora < gols_casa THEN 1 ELSE 0 END,
                 CASE WHEN gols_casa = 0 THEN 1 ELSE 0 END,
                 CASE WHEN gols_fora = 0 THEN 1 ELSE 0 END
          FROM jogos_ok
        ),
        agg AS (
          SELECT clube_id,
                 COUNT(*) AS j,
                 SUM(v) AS v, SUM(e) AS e, SUM(d) AS d,
                 SUM(gf) AS gp, SUM(gs) AS gc,
                 SUM(v)*3 + SUM(e) AS pts,
                 SUM(clean_sheets) AS clean_sheets,
                 SUM(clean_goals) AS clean_goals
          FROM lados
          GROUP BY clube_id
        )
        SELECT a.*, c.clube,
               cf.id_externo AS id_fotmob
        FROM agg a
        JOIN clubes c ON c.id = a.clube_id
        LEFT JOIN clubes_fontes cf ON cf.clube_id = c.id AND cf.fonte = 'fotmob'
        ORDER BY a.pts DESC, (a.gp - a.gc) DESC, a.gp DESC, c.clube
        """,
        (campeonato_id, temporada),
    )
    out = []
    for i, r in enumerate(rows, start=1):
        item = _serialize(r)
        item["posicao"] = i
        item["sg"] = (item.get("gp") or 0) - (item.get("gc") or 0)
        item["logo"] = _logo_clube(item.get("id_fotmob"))
        out.append(item)
    return out


def artilharia(campeonato_id: int, temporada: str, limite: int = 200) -> list[dict]:
    rows = fetch_all(
        """
        SELECT jg.id AS jogador_id, jg.nome, jg.foto, jg.posicao, jg.nacionalidade,
               cl.id AS clube_id, cl.clube,
               cf.id_externo AS clube_id_fotmob,
               SUM(COALESCE(i.gols, 0)) AS gols,
               SUM(COALESCE(i.assistencias, 0)) AS assistencias,
               COUNT(DISTINCT i.jogo_id) AS jogos,
               ROUND(AVG(i.rating)::numeric, 2) AS rating_medio
        FROM individual i
        JOIN jogos jo ON jo.id = i.jogo_id
        JOIN jogadores jg ON jg.id = i.jogador_id
        JOIN clubes cl ON cl.id = i.clube_id
        LEFT JOIN clubes_fontes cf ON cf.clube_id = cl.id AND cf.fonte = 'fotmob'
        WHERE jo.campeonato_id = %s AND jo.temporada = %s AND jo.gols_casa IS NOT NULL
        GROUP BY jg.id, jg.nome, jg.foto, jg.posicao, jg.nacionalidade, cl.id, cl.clube, cf.id_externo
        HAVING SUM(COALESCE(i.gols, 0)) > 0
        ORDER BY gols DESC, assistencias DESC, rating_medio DESC NULLS LAST
        LIMIT %s
        """,
        (campeonato_id, temporada, limite),
    )
    out = []
    for i, r in enumerate(rows, start=1):
        item = _serialize(r)
        item["posicao_rank"] = i
        item["clube_logo"] = _logo_clube(item.get("clube_id_fotmob"))
        out.append(item)
    return out


def artilharia_filtros_de(rows: list[dict]) -> dict:
    posicoes = sorted({r["posicao"] for r in rows if r.get("posicao")})
    nacionalidades = sorted({r["nacionalidade"] for r in rows if r.get("nacionalidade")})
    clubes_map = {}
    for r in rows:
        if r.get("clube_id") and r["clube_id"] not in clubes_map:
            clubes_map[r["clube_id"]] = {
                "id": r["clube_id"],
                "clube": r["clube"],
                "logo": r.get("clube_logo"),
            }
    return {
        "posicoes": posicoes,
        "nacionalidades": nacionalidades,
        "clubes": sorted(clubes_map.values(), key=lambda c: c["clube"]),
    }


def ultima_rodada(campeonato_id: int, temporada: str) -> dict:
    row = fetch_one(
        """
        SELECT MAX(NULLIF(regexp_replace(COALESCE(rodada, ''), '[^0-9]', '', 'g'), '')::int) AS max_n
        FROM jogos
        WHERE campeonato_id = %s AND temporada = %s AND gols_casa IS NOT NULL
        """,
        (campeonato_id, temporada),
    )
    max_n = row["max_n"] if row else None
    if max_n is None:
        return {"rodada": None, "jogos": []}
    jogos = _jogos_rodada(campeonato_id, temporada, max_n)
    return {"rodada": f"Rodada {max_n}", "n_rodada": max_n, "jogos": jogos}


def rodada_destaque(campeonato_id: int, temporada: str) -> int | None:
    """Maior número de rodada que já tem pelo menos um jogo com placar."""
    row = fetch_one(
        """
        SELECT MAX(NULLIF(regexp_replace(COALESCE(rodada, ''), '[^0-9]', '', 'g'), '')::int) AS max_n
        FROM jogos
        WHERE campeonato_id = %s AND temporada = %s AND gols_casa IS NOT NULL
          AND NULLIF(regexp_replace(COALESCE(rodada, ''), '[^0-9]', '', 'g'), '') IS NOT NULL
        """,
        (campeonato_id, temporada),
    )
    return row["max_n"] if row and row.get("max_n") is not None else None


def rodadas_liga(campeonato_id: int, temporada: str) -> list[dict]:
    """Todas as rodadas em ordem crescente, cada uma com todos os jogos."""
    rows = fetch_all(
        """
        SELECT DISTINCT NULLIF(regexp_replace(COALESCE(rodada, ''), '[^0-9]', '', 'g'), '')::int AS n_rodada
        FROM jogos
        WHERE campeonato_id = %s AND temporada = %s
          AND NULLIF(regexp_replace(COALESCE(rodada, ''), '[^0-9]', '', 'g'), '') IS NOT NULL
        ORDER BY n_rodada ASC
        """,
        (campeonato_id, temporada),
    )
    return [
        {
            "rodada": f"Rodada {r['n_rodada']}",
            "n_rodada": r["n_rodada"],
            "jogos": _jogos_rodada(campeonato_id, temporada, r["n_rodada"]),
        }
        for r in rows
        if r.get("n_rodada") is not None
    ]


def _jogos_rodada(campeonato_id: int, temporada: str, n_rodada: int) -> list[dict]:
    rows = fetch_all(
        """
        SELECT j.id, j.data, j.rodada, j.gols_casa, j.gols_fora,
               ca.clube AS casa, fa.clube AS fora,
               cf_casa.id_externo AS casa_id_fotmob,
               cf_fora.id_externo AS fora_id_fotmob
        FROM jogos j
        JOIN clubes ca ON ca.id = j.casa_id
        JOIN clubes fa ON fa.id = j.fora_id
        LEFT JOIN clubes_fontes cf_casa ON cf_casa.clube_id = ca.id AND cf_casa.fonte = 'fotmob'
        LEFT JOIN clubes_fontes cf_fora ON cf_fora.clube_id = fa.id AND cf_fora.fonte = 'fotmob'
        WHERE j.campeonato_id = %s AND j.temporada = %s
          AND NULLIF(regexp_replace(COALESCE(j.rodada, ''), '[^0-9]', '', 'g'), '')::int = %s
        ORDER BY j.data NULLS LAST, j.id
        """,
        (campeonato_id, temporada, n_rodada),
    )
    out = []
    for r in rows:
        item = _serialize(r)
        item["casa_logo"] = _logo_clube(item.get("casa_id_fotmob"))
        item["fora_logo"] = _logo_clube(item.get("fora_id_fotmob"))
        out.append(item)
    return out


def detalhe_liga(campeonato_id: int, temporada: str | None = None) -> dict | None:
    info = info_liga(campeonato_id)
    if not info:
        return None
    temps = temporadas_liga(campeonato_id)
    temp = temporada if temporada in temps else (temps[0] if temps else None)
    if not temp:
        return {
            **info,
            "temporadas": [],
            "temporada": None,
            "classificacao": [],
            "artilharia": [],
            "artilharia_filtros": {"posicoes": [], "nacionalidades": [], "clubes": []},
            "ultima_rodada": {"rodada": None, "jogos": []},
            "rodadas": [],
            "rodada_destaque": None,
            "clubes": [],
        }
    tabela = classificacao(campeonato_id, temp)
    arts = artilharia(campeonato_id, temp)
    rodadas = rodadas_liga(campeonato_id, temp)
    destaque = rodada_destaque(campeonato_id, temp)
    if destaque is None and rodadas:
        destaque = rodadas[-1]["n_rodada"]
    return {
        **info,
        "temporadas": temps,
        "temporada": temp,
        "classificacao": tabela,
        "artilharia": arts,
        "artilharia_filtros": artilharia_filtros_de(arts),
        "ultima_rodada": ultima_rodada(campeonato_id, temp),
        "rodadas": rodadas,
        "rodada_destaque": destaque,
        "clubes": [
            {"id": r["clube_id"], "clube": r["clube"], "logo": r.get("logo")}
            for r in tabela
        ],
    }
