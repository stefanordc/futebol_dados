"""Radar do técnico: consulta SQL agregada por jogos realmente comandados.

Evita a sequência de centenas de requisições às páginas de clubes/jogos
que falhava com HTTP 500. Não usa os resultados de outros treinadores.
"""
from __future__ import annotations

from db import fetch_one
from queries import _serialize

_BASE = """
WITH partidas AS (
    SELECT j.id, j.campeonato_id, j.casa_id AS clube_id,
           j.gols_casa AS gm, j.gols_fora AS gs
    FROM jogos j
    WHERE j.temporada = %s AND j.tecnico_casa_id = %s
      AND j.gols_casa IS NOT NULL AND j.gols_fora IS NOT NULL
    UNION ALL
    SELECT j.id, j.campeonato_id, j.fora_id AS clube_id,
           j.gols_fora AS gm, j.gols_casa AS gs
    FROM jogos j
    WHERE j.temporada = %s AND j.tecnico_fora_id = %s
      AND j.gols_casa IS NOT NULL AND j.gols_fora IS NOT NULL
), scoped AS (
    SELECT p.*, e.total_chutes, e.xg, e.grandes_chances,
           e.bloqueios, e.interceptacoes, e.passes_certos
    FROM partidas p
    LEFT JOIN estatisticas e ON e.jogo_id = p.id
      AND e.clube_id = p.clube_id AND e.periodo = 'Completo'
"""

_SELECT = """
)
SELECT COUNT(*) AS jogos,
       SUM(gm) AS gols_marcados, SUM(gs) AS gols_sofridos,
       COUNT(*) FILTER (WHERE gs = 0) AS clean_sheets,
       COUNT(*) FILTER (WHERE gm > gs) AS vitorias,
       COUNT(*) FILTER (WHERE gm = gs) AS empates,
       SUM(total_chutes) AS finalizacoes, COUNT(total_chutes) AS jogos_finalizacoes,
       SUM(xg) AS xg, COUNT(xg) AS jogos_xg,
       SUM(grandes_chances) AS grandes_chances,
       COUNT(grandes_chances) AS jogos_chances,
       SUM(bloqueios) AS bloqueios, COUNT(bloqueios) AS jogos_bloqueios,
       SUM(interceptacoes) AS interceptacoes, COUNT(interceptacoes) AS jogos_interceptacoes,
       SUM(passes_certos) AS passes_certos, COUNT(passes_certos) AS jogos_passes
FROM scoped
"""


def radar_tecnico(
    tecnico_id: int,
    temporada: str,
    campeonato_id: int | None = None,
    clube_id: int | None = None,
) -> dict:
    if not isinstance(tecnico_id, int) or tecnico_id <= 0:
        raise ValueError("Técnico inválido.")
    if not isinstance(temporada, str) or not temporada.strip():
        raise ValueError("Informe uma temporada válida.")

    conditions = []
    params: list[object] = [temporada, tecnico_id, temporada, tecnico_id]

    if campeonato_id is not None:
        if campeonato_id <= 0:
            raise ValueError("Campeonato inválido.")
        conditions.append("p.campeonato_id = %s")
        params.append(campeonato_id)
    if clube_id is not None:
        if clube_id <= 0:
            raise ValueError("Clube inválido.")
        conditions.append("p.clube_id = %s")
        params.append(clube_id)

    where = "\n WHERE " + " AND ".join(conditions) if conditions else ""
    row = fetch_one(_BASE + where + _SELECT, tuple(params))
    result = _serialize(row) if row else {}
    total = int(result.get("jogos") or 0)

    return {
        "tecnico_id": tecnico_id,
        "temporada": temporada,
        "campeonato_id": campeonato_id,
        "clube_id": clube_id,
        "jogos": total,
        "metricas": result,
        "aviso": (
            "Menos de cinco partidas. Os índices podem oscilar bastante."
            if 0 < total < 5 else
            "Não há jogos finalizados neste recorte."
            if total == 0 else None
        ),
        "origem": "jogos comandados pelo técnico e estatisticas de período Completo",
    }
