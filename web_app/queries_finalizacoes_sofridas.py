"""Finalizações sofridas por clube, usando somente as finalizações do adversário.

As agregações respeitam os filtros globais (país, liga, temporada,
mando do clube que sofre a finalização e clube).
"""
from __future__ import annotations

from db import fetch_all
from queries import _serialize
from queries_stats import _DIST_M, _IS_GOL, _IS_CERTA, _logo, _PITCH_WID, _PITCH_LEN


_DEFENSOR = "(CASE WHEN f.clube_id = j.casa_id THEN j.fora_id ELSE j.casa_id END)"
_NAO_CONTRA = "LOWER(COALESCE(f.foi_gol_contra::text, 'false')) NOT IN ('true', 't', '1')"


def _filtros(temporada, campeonato_id, pais, mando, clube_id):
    cond = [
        "j.gols_casa IS NOT NULL", "f.coordenada_x IS NOT NULL",
        "f.coordenada_y IS NOT NULL",
        "f.clube_id IN (j.casa_id, j.fora_id)",
        _NAO_CONTRA,
    ]
    params = []
    if temporada:
        cond.append("j.temporada = %s")
        params.append(temporada)
    if campeonato_id:
        cond.append("j.campeonato_id = %s")
        params.append(campeonato_id)
    if pais:
        cond.append("p.nome = %s")
        params.append(pais)
    if mando in ("casa", "fora"):
        cond.append(_DEFENSOR + (" = j.casa_id" if mando == "casa" else " = j.fora_id"))
    if clube_id:
        cond.append(_DEFENSOR + " = %s")
        params.append(clube_id)
    return " AND ".join(cond), params


def _mapa(*, temporada=None, campeonato_id=None, pais=None,
          mando=None, clube_id: int, limite=400):
    where, params = _filtros(temporada, campeonato_id, pais, mando, clube_id)
    rows = fetch_all(f"""
        SELECT f.coordenada_x, f.coordenada_y, f.tipo_evento,
               f.foi_no_alvo, f.minuto, jg.nome AS jogador
        FROM finalizacoes f
        JOIN jogos j ON j.id = f.jogo_id
        JOIN campeonatos c ON c.id = j.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        LEFT JOIN jogadores jg ON jg.id = f.jogador_id
        WHERE {where}
        ORDER BY j.data DESC NULLS LAST, f.id DESC
        LIMIT %s
    """, (*params, limite))
    result = []
    for row in rows:
        item = _serialize(row)
        x = item.get("coordenada_x")
        y = item.get("coordenada_y")
        if x is None or y is None:
            continue
        item["left"] = round(max(0, min(100, 100 * float(y) / _PITCH_WID)), 2)
        item["top"] = round(max(0, min(100, 100 * (_PITCH_LEN - float(x)) / _PITCH_LEN)), 2)
        result.append(item)
    return result


def consultar(*, temporada=None, campeonato_id=None, pais=None,
              mando=None, clube_id=None, mapa_clube_id=None,
              page=1, page_size=20, ordenar="gols", ordem="desc",
              escopo="clube"):
    if escopo == "mapa":
        return {"mapa": _mapa(
            temporada=temporada, campeonato_id=campeonato_id, pais=pais,
            mando=mando, clube_id=clube_id)}
    where, params = _filtros(temporada, campeonato_id, pais, mando, clube_id)
    sort_cols = {
        "clube": "cl.clube", "jogos": "jogos",
        "chutes": "chutes", "certas": "certas", "gols": "gols",
        "dist_chute": "dist_chute", "dist_certa": "dist_certa", "dist_gol": "dist_gol",
    }
    sort = sort_cols.get(ordenar, "gols")
    direction = "ASC" if ordem == "asc" else "DESC"
    rows = fetch_all(f"""
        SELECT {_DEFENSOR} AS clube_id, cl.clube,
               cf.id_externo AS id_fotmob,
               c.nome AS campeonato, c.id AS campeonato_id,
               COUNT(DISTINCT j.id) AS jogos,
               COUNT(*) AS chutes,
               COUNT(*) FILTER (WHERE {_IS_CERTA}) AS certas,
               COUNT(*) FILTER (WHERE {_IS_GOL}) AS gols,
               ROUND(AVG({_DIST_M})::numeric, 1) AS dist_chute,
               ROUND(AVG({_DIST_M}) FILTER (WHERE {_IS_CERTA})::numeric, 1) AS dist_certa,
               ROUND(AVG({_DIST_M}) FILTER (WHERE {_IS_GOL})::numeric, 1) AS dist_gol
        FROM finalizacoes f
        JOIN jogos j ON j.id = f.jogo_id
        JOIN clubes cl ON cl.id = {_DEFENSOR}
        JOIN campeonatos c ON c.id = j.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        LEFT JOIN clubes_fontes cf ON cf.clube_id = cl.id AND cf.fonte = 'fotmob'
        WHERE {where}
        GROUP BY {_DEFENSOR}, cl.clube, cf.id_externo, c.nome, c.id
        ORDER BY {sort} {direction} NULLS LAST, cl.clube
    """, params)
    items = []
    for row in rows:
        item = _serialize(row)
        item["logo"] = _logo(item.get("id_fotmob"))
        jogos = item.get("jogos") or 1
        for key in ("chutes", "certas", "gols"):
            item[key + "_media"] = round(float(item.get(key) or 0) / jogos, 2)
        items.append(item)
    page_size = max(5, min(int(page_size), 100))
    page = max(1, int(page))
    pages = max(1, (len(items) + page_size - 1) // page_size)
    page = min(page, pages)
    slice_items = items[(page - 1) * page_size:page * page_size]
    selected = mapa_clube_id if any(x["clube_id"] == mapa_clube_id for x in slice_items) else (
        slice_items[0]["clube_id"] if slice_items else None)
    result_map = _mapa(
        temporada=temporada, campeonato_id=campeonato_id, pais=pais,
        mando=mando, clube_id=selected) if selected else []
    return {
        "linhas": slice_items, "total": len(items),
        "page": page, "page_size": page_size, "pages": pages,
        "ordenar": ordenar if ordenar in sort_cols else "gols",
        "ordem": "asc" if direction == "ASC" else "desc",
        "mapa_clube_id": selected, "mapa": result_map,
    }
