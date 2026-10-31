"""Agregações de perfis para evitar N consultas HTTP por partida.
Não modifica dados; somente SELECTs parametrizados no PostgreSQL.
"""
from __future__ import annotations

from collections import defaultdict

from db import fetch_all, fetch_one
from queries import _serialize


def perfil_arbitro(arbitro_id: int, temporada: str | None = None) -> dict | None:
    base = fetch_one("""
        SELECT a.id, a.nome, a.foto, a.id_fotmob, p.nome AS pais
        FROM arbitros a LEFT JOIN paises p ON p.id = a.pais_id
        WHERE a.id = %s
    """, (arbitro_id,))
    if not base:
        return None

    entity = _serialize(base)
    seasons = [
        r["temporada"] for r in fetch_all("""
            SELECT DISTINCT temporada FROM jogos
            WHERE arbitro_id = %s AND temporada IS NOT NULL
            ORDER BY temporada DESC
        """, (arbitro_id,))
    ]
    selected = temporada if temporada in seasons else None

    # Uma linha por jogo. As estatísticas de cada lado são agregadas,
    # evitando duplicação de partidas ao juntar "estatisticas".
    rows = fetch_all("""
        WITH jogos_arbitro AS (
            SELECT j.id, j.data, j.temporada, j.campeonato_id,
                   j.casa_id, j.fora_id, j.gols_casa, j.gols_fora
            FROM jogos j
            WHERE j.arbitro_id = %s
              AND j.gols_casa IS NOT NULL
              AND (%s::text IS NULL OR j.temporada = %s)
        )
        SELECT j.id, j.data, j.temporada, c.nome AS campeonato,
               c.id AS campeonato_id,
               ca.clube AS casa, fa.clube AS fora,
               j.gols_casa, j.gols_fora,
               SUM(e.faltas_cometidas) FILTER (WHERE e.mando = 'Casa') AS faltas_casa,
               SUM(e.faltas_cometidas) FILTER (WHERE e.mando = 'Fora') AS faltas_fora,
               SUM(e.cartao_amarelo) FILTER (WHERE e.mando = 'Casa') AS amarelos_casa,
               SUM(e.cartao_amarelo) FILTER (WHERE e.mando = 'Fora') AS amarelos_fora,
               SUM(e.cartao_vermelho) FILTER (WHERE e.mando = 'Casa') AS vermelhos_casa,
               SUM(e.cartao_vermelho) FILTER (WHERE e.mando = 'Fora') AS vermelhos_fora,
               SUM(e.impedimentos) FILTER (WHERE e.mando = 'Casa') AS impedimentos_casa,
               SUM(e.impedimentos) FILTER (WHERE e.mando = 'Fora') AS impedimentos_fora
        FROM jogos_arbitro j
        JOIN campeonatos c ON c.id = j.campeonato_id
        JOIN clubes ca ON ca.id = j.casa_id
        JOIN clubes fa ON fa.id = j.fora_id
        LEFT JOIN estatisticas e ON e.jogo_id = j.id AND e.periodo = 'Completo'
        GROUP BY j.id, j.data, j.temporada, c.id, c.nome,
                 ca.clube, fa.clube, j.gols_casa, j.gols_fora
        ORDER BY j.data DESC NULLS LAST, j.id DESC
        LIMIT 1200
    """, (arbitro_id, selected, selected))

    games = [_serialize(r) for r in rows]
    aggregations = defaultdict(list)
    for g in games:
        aggregations[(g["campeonato_id"], g["campeonato"])].append(g)

    def total(items: list[dict], key: str):
        values = [float(v[key]) for v in items if v.get(key) is not None]
        return round(sum(values), 2) if values else None

    def summarize(items: list[dict]):
        n = len(items)
        home = sum(g["gols_casa"] > g["gols_fora"] for g in items)
        away = sum(g["gols_casa"] < g["gols_fora"] for g in items)
        draw = n - home - away
        def pct(count): return round(100 * count / n, 1) if n else None
        keys = ("faltas_casa", "faltas_fora", "amarelos_casa", "amarelos_fora",
                "vermelhos_casa", "vermelhos_fora", "impedimentos_casa", "impedimentos_fora")
        t = {k: total(items, k) for k in keys}
        def both(a, b):
            return round(t[a]+t[b], 2) if t[a] is not None and t[b] is not None else None
        return {
            "jogos": n, "vitorias_mandante": home, "vitorias_visitante": away,
            "empates": draw, "pct_mandante": pct(home), "pct_visitante": pct(away),
            "pct_empates": pct(draw), "pct_mandante_ou_empate": pct(home+draw),
            "faltas": both("faltas_casa", "faltas_fora"),
            "amarelos": both("amarelos_casa", "amarelos_fora"),
            "vermelhos": both("vermelhos_casa", "vermelhos_fora"),
            "impedimentos": both("impedimentos_casa", "impedimentos_fora"),
            **t,
        }

    lines = []
    for (comp_id, comp_name), group in aggregations.items():
        lines.append({"campeonato_id": comp_id, "campeonato": comp_name,
                      **summarize(group)})
    lines.sort(key=lambda x: (-x["jogos"], x["campeonato"]))
    if not entity.get("foto") and entity.get("id_fotmob"):
        entity["foto"] = "https://images.fotmob.com/image_resources/playerimages/{}.png".format(entity["id_fotmob"])

    return {
        "tipo": "arbitro", "entidade": entity, "temporada": selected,
        "temporadas": seasons, "linhas": lines,
        "resumo": summarize(games), "jogos": games,
        "parcial": len(games) >= 1200,
    }


def fundamentos_clube(clube_id: int, temporada: str,
                       campeonato_id: int | None = None,
                       mando: str | None = None) -> dict:
    """Um único agregado sobre partidas e finalizações, sem busca por jogo."""
    return _serialize(fetch_one("""
        WITH selecionados AS (
            SELECT j.id FROM jogos j
            WHERE (j.casa_id = %s OR j.fora_id = %s)
              AND j.temporada = %s AND j.gols_casa IS NOT NULL
              AND (%s::int IS NULL OR j.campeonato_id = %s)
              AND (%s::text IS NULL OR %s = 'todos'
                   OR (%s = 'casa' AND j.casa_id = %s)
                   OR (%s = 'fora' AND j.fora_id = %s))
        ),
        agregado AS (
            SELECT
                COUNT(DISTINCT j.id) AS jogos_com_finalizacoes,
                COUNT(*) FILTER (WHERE f.tipo_evento IS NOT NULL AND
                    (LOWER(f.tipo_evento) LIKE '%%gol%%' OR LOWER(f.tipo_evento) LIKE '%%goal%%')) AS gols_registrados,
                COUNT(*) FILTER (WHERE f.situacao_jogada IS NOT NULL AND
                    (LOWER(f.tipo_evento) LIKE '%%gol%%' OR LOWER(f.tipo_evento) LIKE '%%goal%%')) AS gols_classificados,
                COUNT(*) FILTER (WHERE
                    (LOWER(f.tipo_evento) LIKE '%%gol%%' OR LOWER(f.tipo_evento) LIKE '%%goal%%')
                    AND (LOWER(COALESCE(f.situacao_jogada,'')) LIKE '%%penalt%%'
                        OR LOWER(COALESCE(f.situacao_jogada,'')) LIKE '%%corner%%'
                        OR LOWER(COALESCE(f.situacao_jogada,'')) LIKE '%%escante%%'
                        OR LOWER(COALESCE(f.situacao_jogada,'')) LIKE '%%falta%%'
                        OR LOWER(COALESCE(f.situacao_jogada,'')) LIKE '%%set piece%%'
                        OR LOWER(COALESCE(f.situacao_jogada,'')) LIKE '%%bola parada%%')
                    AND ((f.clube_id = %s AND NOT (LOWER(COALESCE(f.foi_gol_contra::text,'false')) IN ('true','t','1')))
                      OR (f.clube_id <> %s AND (LOWER(COALESCE(f.foi_gol_contra::text,'false')) IN ('true','t','1'))))) AS bola_parada_pro,
                COUNT(*) FILTER (WHERE
                    (LOWER(f.tipo_evento) LIKE '%%gol%%' OR LOWER(f.tipo_evento) LIKE '%%goal%%')
                    AND (LOWER(COALESCE(f.situacao_jogada,'')) LIKE '%%penalt%%'
                        OR LOWER(COALESCE(f.situacao_jogada,'')) LIKE '%%corner%%'
                        OR LOWER(COALESCE(f.situacao_jogada,'')) LIKE '%%escante%%'
                        OR LOWER(COALESCE(f.situacao_jogada,'')) LIKE '%%falta%%'
                        OR LOWER(COALESCE(f.situacao_jogada,'')) LIKE '%%set piece%%'
                        OR LOWER(COALESCE(f.situacao_jogada,'')) LIKE '%%bola parada%%')
                    AND ((f.clube_id <> %s AND NOT (LOWER(COALESCE(f.foi_gol_contra::text,'false')) IN ('true','t','1')))
                      OR (f.clube_id = %s AND (LOWER(COALESCE(f.foi_gol_contra::text,'false')) IN ('true','t','1'))))) AS bola_parada_contra,
                COUNT(*) FILTER (WHERE
                    (LOWER(f.tipo_evento) LIKE '%%gol%%' OR LOWER(f.tipo_evento) LIKE '%%goal%%')
                    AND (LOWER(COALESCE(f.tipo_finalizacao,'')) LIKE '%%head%%'
                      OR LOWER(COALESCE(f.tipo_finalizacao,'')) LIKE '%%cabeca%%'
                      OR LOWER(COALESCE(f.tipo_finalizacao,'')) LIKE '%%cabeça%%')
                    AND ((f.clube_id = %s AND NOT (LOWER(COALESCE(f.foi_gol_contra::text,'false')) IN ('true','t','1')))
                      OR (f.clube_id <> %s AND (LOWER(COALESCE(f.foi_gol_contra::text,'false')) IN ('true','t','1'))))) AS cabeca_pro,
                COUNT(*) FILTER (WHERE
                    (LOWER(f.tipo_evento) LIKE '%%gol%%' OR LOWER(f.tipo_evento) LIKE '%%goal%%')
                    AND (LOWER(COALESCE(f.tipo_finalizacao,'')) LIKE '%%head%%'
                      OR LOWER(COALESCE(f.tipo_finalizacao,'')) LIKE '%%cabeca%%'
                      OR LOWER(COALESCE(f.tipo_finalizacao,'')) LIKE '%%cabeça%%')
                    AND ((f.clube_id <> %s AND NOT (LOWER(COALESCE(f.foi_gol_contra::text,'false')) IN ('true','t','1')))
                      OR (f.clube_id = %s AND (LOWER(COALESCE(f.foi_gol_contra::text,'false')) IN ('true','t','1'))))) AS cabeca_contra
            FROM selecionados j JOIN finalizacoes f ON f.jogo_id = j.id
        )
        SELECT agregado.*, (SELECT COUNT(*) FROM selecionados) AS jogos FROM agregado
    """, (clube_id, clube_id, temporada, campeonato_id, campeonato_id,
           mando, mando, mando, clube_id, mando, clube_id,
           clube_id, clube_id, clube_id, clube_id,
           clube_id, clube_id, clube_id, clube_id)) or {})
