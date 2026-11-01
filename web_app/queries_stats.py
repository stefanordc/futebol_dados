"""Consultas da página de estatísticas (coletiva / individual / técnicos / árbitros)."""

from __future__ import annotations

from db import fetch_all, fetch_one
from queries import LOGO_TIME, _serialize, clube_match_key

FOTO_PESSOA = "https://images.fotmob.com/image_resources/playerimages/{id}.png"

# Grupos de métricas coletivas (coluna em estatisticas → rótulo)
GRUPOS_COLETIVAS = {
    "ataque": [
        ("xg", "xG"),
        ("xg_jogada_normal", "xG jogada normal"),
        ("xg_jogada_ensaiada", "xG jogada ensaiada"),
        ("xg_sem_penalti", "xG sem pênaltis"),
        ("xgot", "xGOT"),
        ("total_chutes", "Total de chutes"),
        ("chutes_certos", "Chutes no gol"),
        ("chutes_fora", "Chutes para fora"),
        ("chutes_bloqueados", "Chutes bloqueados"),
        ("chutes_trave", "Chutes na trave"),
        ("chutes_dentro_area", "Chutes dentro da área"),
        ("chutes_fora_area", "Chutes de fora da área"),
        ("grandes_chances", "Grandes chances"),
        ("grandes_chances_perdidas", "Grandes chances perdidas"),
        ("toques_area_adversaria", "Toques na área adversária"),
    ],
    "passes": [
        ("posse_bola", "Posse de bola (%)"),
        ("passes", "Passes"),
        ("passes_certos", "Passes certos"),
        ("passes_campo_defesa", "Passes no campo de defesa"),
        ("passes_campo_ataque", "Passes no campo de ataque"),
        ("passes_longos", "Passes longos"),
        ("passes_longos_certos", "Passes longos certos"),
        ("cruzamentos", "Cruzamentos"),
        ("cruzamentos_certos", "Cruzamentos certos"),
        ("escanteios", "Escanteios"),
        ("laterais", "Laterais"),
        ("impedimentos", "Impedimentos"),
    ],
    "defesa": [
        ("desarmes", "Desarmes"),
        ("interceptacoes", "Interceptações"),
        ("bloqueios", "Bloqueios"),
        ("bolas_afastadas", "Bolas afastadas"),
        ("defesas_goleiro", "Defesas do goleiro"),
        ("disputas_ganhas", "Disputas ganhas"),
        ("disputas_chao", "Disputas no chão"),
        ("disputas_chao_ganhas", "Disputas no chão ganhas"),
        ("disputas_aereas", "Disputas aéreas"),
        ("disputas_aereas_ganhas", "Disputas aéreas ganhas"),
    ],
    "duelos": [
        ("dribles", "Dribles"),
        ("dribles_certos", "Dribles certos"),
        ("faltas_cometidas", "Faltas cometidas"),
        ("faltas_recebidas", "Faltas recebidas"),
        ("cartao_amarelo", "Cartões amarelos"),
        ("cartao_vermelho", "Cartões vermelhos"),
    ],
    "fisicos": [
        ("distancia_percorrida", "Distância (km)"),
        ("pct_vit_mais_km", "% vit. +KM"),
        ("sprints", "Sprints"),
        ("pct_vit_mais_sprints", "% vit. +Sprints"),
    ],
}

GRUPOS_LABELS = {
    "apostas": "Apostas",
    "ataque": "Ataque",
    "passes": "Posse e passes",
    "defesa": "Defesa",
    "duelos": "Duelos e disciplina",
    "fisicos": "Dados físicos",
    "rating": "Rating",
    "minutos": "Minutos",
    "finalizacoes": "Finalizações",
}

# Grupos da página do clube (estatísticas) — ordem das abas
GRUPOS_CLUBE = {
    "ataque": "Ataque",
    "passes": "Posse e passes",
    "defesa": "Defesa",
    "duelos": "Duelos e disciplina",
    "fisicos": "Dados físicos",
    "rating": "Rating",
    "minutos": "Minutos",
    "comportamento": "Comportamento",
}

# Distância até o centro do gol. FotMob usa metros: comprimento 105, largura 68.
_PITCH_LEN = 105.0
_PITCH_WID = 68.0
_DIST_M = (
    f"SQRT(POWER({_PITCH_LEN} - f.coordenada_x, 2) + POWER(f.coordenada_y - {_PITCH_WID / 2}, 2))"
)
_IS_GOL = "LOWER(COALESCE(f.tipo_evento, '')) LIKE '%%gol%%'"
_IS_CERTA = "LOWER(COALESCE(f.tipo_evento, '')) IN ('gol', 'defendida')"

METRICAS_INDIVIDUAIS = {
    "gols": ("SUM(COALESCE(i.gols,0))", "Gols"),
    "assistencias": ("SUM(COALESCE(i.assistencias,0))", "Assistências"),
    "rating": ("AVG(i.rating)", "Nota"),
    "xg": ("SUM(COALESCE(i.xg,0))", "xG"),
    "xa": ("SUM(COALESCE(i.xa,0))", "xA"),
    "chutes_total": ("SUM(COALESCE(i.chutes_total,0))", "Chutes"),
    "desarmes": ("SUM(COALESCE(i.desarmes,0))", "Desarmes"),
    "passes_certos": ("SUM(COALESCE(i.passes_certos,0))", "Passes certos"),
}


def _logo(id_fotmob):
    return LOGO_TIME.format(id=id_fotmob) if id_fotmob else None


def _fisicos_lookup(temporada: str, pais: str | None = None,
                    mando: str | None = None) -> tuple[dict, dict]:
    """Lê dados físicos da nova tabela dados_fisicos, com IDs externos SofaScore."""
    from queries_dados_fisicos import fisicos_lookup
    return fisicos_lookup(temporada, pais, mando)


def _aplicar_fisicos(item: dict, by_id: dict, by_key: dict) -> None:
    fis = by_id.get(item.get("clube_id")) or by_key.get(clube_match_key(item.get("clube")))
    if not fis:
        return
    for col in (
        "distancia_percorrida",
        "sprints",
        "pct_vit_mais_km",
        "pct_vit_mais_sprints",
    ):
        item[f"sum_{col}"] = fis.get(f"sum_{col}")
        item[f"avg_{col}"] = fis.get(f"avg_{col}")
    item["jogos_fisico"] = fis.get("jogos_fisico")
    item["jogos_mais_km"] = fis.get("jogos_mais_km")
    item["jogos_mais_sprints"] = fis.get("jogos_mais_sprints")


def clubes_campeonato(campeonato_id: int, temporada: str | None = None) -> list[dict]:
    return clubes_filtro(campeonato_id=campeonato_id, temporada=temporada)


def clubes_filtro(
    *,
    campeonato_id: int | None = None,
    temporada: str | None = None,
    pais: str | None = None,
) -> list[dict]:
    """Clubes no escopo atual (país / campeonato / temporada)."""
    filtros = ["j.gols_casa IS NOT NULL"]
    params: list = []
    if campeonato_id:
        filtros.append("j.campeonato_id = %s")
        params.append(campeonato_id)
    if temporada:
        filtros.append("j.temporada = %s")
        params.append(temporada)
    if pais:
        filtros.append("p.nome = %s")
        params.append(pais)
    rows = fetch_all(
        f"""
        SELECT DISTINCT c.id, c.clube, cf.id_externo AS id_fotmob
        FROM jogos j
        JOIN clubes c ON c.id IN (j.casa_id, j.fora_id)
        JOIN campeonatos camp ON camp.id = j.campeonato_id
        LEFT JOIN paises p ON p.id = camp.pais_id
        LEFT JOIN clubes_fontes cf ON cf.clube_id = c.id AND cf.fonte = 'fotmob'
        WHERE {" AND ".join(filtros)}
        ORDER BY c.clube, c.id
        """,
        params,
    )
    out = []
    for r in rows:
        item = _serialize(r)
        item["logo"] = _logo(item.get("id_fotmob"))
        out.append(item)
    # reforço alfabético (pt) no Python
    out.sort(key=lambda x: (x.get("clube") or "").casefold())
    return out


def paises_com_dados() -> list[str]:
    rows = fetch_all(
        """
        SELECT DISTINCT p.nome
        FROM campeonatos c
        JOIN paises p ON p.id = c.pais_id
        JOIN jogos j ON j.campeonato_id = c.id AND j.gols_casa IS NOT NULL
        ORDER BY p.nome
        """
    )
    return [r["nome"] for r in rows if r.get("nome")]


def ligas_filtro(
    pais: str | None = None,
    *,
    clube_id: int | None = None,
    temporada: str | None = None,
) -> list[dict]:
    params: list = []
    filtros = ["1=1"]
    if pais:
        filtros.append("p.nome = %s")
        params.append(pais)
    if clube_id:
        filtros.append(
            """EXISTS (
              SELECT 1 FROM jogos jx
              WHERE jx.campeonato_id = c.id AND jx.gols_casa IS NOT NULL
                AND (jx.casa_id = %s OR jx.fora_id = %s)
                {temp}
            )""".format(temp="AND jx.temporada = %s" if temporada else "")
        )
        params.extend([clube_id, clube_id])
        if temporada:
            params.append(temporada)
    where = " AND ".join(filtros)
    rows = fetch_all(
        f"""
        SELECT c.id, c.nome, p.nome AS pais, c.logo, c.id_fotmob,
               COUNT(j.id) AS total_jogos
        FROM campeonatos c
        LEFT JOIN paises p ON p.id = c.pais_id
        LEFT JOIN jogos j ON j.campeonato_id = c.id AND j.gols_casa IS NOT NULL
        WHERE {where}
        GROUP BY c.id, c.nome, p.nome, c.logo, c.id_fotmob
        HAVING COUNT(j.id) > 0
        ORDER BY p.nome, c.nome
        """,
        params,
    )
    out = []
    for r in rows:
        item = _serialize(r)
        if not item.get("logo") and item.get("id_fotmob"):
            from queries import LOGO_LIGA

            item["logo"] = LOGO_LIGA.format(id=item["id_fotmob"])
        out.append(item)
    return out


def temporadas_filtro(
    campeonato_id: int | None = None,
    pais: str | None = None,
    clube_id: int | None = None,
) -> list[str]:
    params: list = []
    filtros = ["j.gols_casa IS NOT NULL", "j.temporada IS NOT NULL"]
    if campeonato_id:
        filtros.append("j.campeonato_id = %s")
        params.append(campeonato_id)
    if pais:
        filtros.append("p.nome = %s")
        params.append(pais)
    if clube_id:
        filtros.append("(j.casa_id = %s OR j.fora_id = %s)")
        params.extend([clube_id, clube_id])
    where = " AND ".join(filtros)
    rows = fetch_all(
        f"""
        SELECT DISTINCT j.temporada
        FROM jogos j
        JOIN campeonatos c ON c.id = j.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        WHERE {where}
        ORDER BY j.temporada DESC
        """,
        params,
    )
    return [r["temporada"] for r in rows]


def _t_gol(g: dict) -> float:
    minuto = int(g.get("minuto") or 0)
    add = int(g.get("minuto_adicional") or 0)
    return minuto + (0.01 * add if add else 0)


def _lado_gol(g: dict, casa_id: int, fora_id: int) -> str:
    """Retorna 'casa' ou 'fora' (quem se beneficiou do gol)."""
    cid = g.get("clube_id")
    contra = bool(g.get("foi_gol_contra"))
    if cid == casa_id:
        return "fora" if contra else "casa"
    if cid == fora_id:
        return "casa" if contra else "fora"
    mando = (g.get("mando") or "").casefold()
    if "casa" in mando:
        return "fora" if contra else "casa"
    return "casa" if contra else "fora"


def _score_at(eventos: list[tuple[float, int]], t_limit: float) -> tuple[int, int]:
    eu = eles = 0
    for t, delta in eventos:
        if t > t_limit:
            break
        if delta > 0:
            eu += 1
        else:
            eles += 1
    return eu, eles


def _pct(n: int, total: int) -> float:
    return round(100.0 * n / total, 1) if total else 0.0


def apostas_analise(
    *,
    temporada: str | None = None,
    campeonato_id: int | None = None,
    pais: str | None = None,
    clube_id: int | None = None,
    mando: str | None = None,
) -> dict:
    """Mercados de apostas + placares mais frequentes (escopo filtrado)."""
    temps = temporadas_filtro(campeonato_id, pais, clube_id)
    if temporada not in temps:
        temporada = temps[0] if temps else None
    if not temporada:
        return {
            "grupos": GRUPOS_LABELS,
            "grupo": "apostas",
            "metricas": [],
            "linhas": [],
            "total": 0,
            "page": 1,
            "page_size": 1,
            "pages": 1,
            "temporada": None,
            "temporadas": [],
            "apostas": None,
        }

    filtros = ["j.temporada = %s", "j.gols_casa IS NOT NULL"]
    params: list = [temporada]
    if campeonato_id:
        filtros.append("j.campeonato_id = %s")
        params.append(campeonato_id)
    if pais:
        filtros.append("p.nome = %s")
        params.append(pais)
    if clube_id:
        filtros.append("(j.casa_id = %s OR j.fora_id = %s)")
        params.extend([clube_id, clube_id])
    where = " AND ".join(filtros)
    mando_n = (mando or "todos").strip().lower()

    jogos = fetch_all(
        f"""
        SELECT j.id, j.casa_id, j.fora_id, j.gols_casa, j.gols_fora
        FROM jogos j
        JOIN campeonatos c ON c.id = j.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        WHERE {where}
        ORDER BY j.data, j.id
        """,
        params,
    )
    if clube_id and mando_n in ("casa", "fora"):
        jogos = [
            j
            for j in jogos
            if (mando_n == "casa" and j["casa_id"] == clube_id)
            or (mando_n == "fora" and j["fora_id"] == clube_id)
        ]

    gols_rows = fetch_all(
        f"""
        SELECT f.jogo_id, f.minuto, f.minuto_adicional, f.mando, f.foi_gol_contra, f.clube_id
        FROM finalizacoes f
        JOIN jogos j ON j.id = f.jogo_id
        JOIN campeonatos c ON c.id = j.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        WHERE {where}
          AND LOWER(COALESCE(f.tipo_evento, '')) LIKE '%%gol%%'
        ORDER BY f.jogo_id, COALESCE(f.minuto, 0), COALESCE(f.minuto_adicional, 0), f.id
        """,
        params,
    )
    gols_por_jogo: dict[int, list] = {}
    for g in gols_rows:
        gols_por_jogo.setdefault(g["jogo_id"], []).append(g)

    n = len(jogos)
    over05_ht = over05_ft = over15 = over25 = over35 = under35 = 0
    btts = goleada_casa = goleada_fora = 0
    placares: dict[str, int] = {}

    for j in jogos:
        gc = int(j["gols_casa"] or 0)
        gf = int(j["gols_fora"] or 0)
        total = gc + gf
        if total >= 1:
            over05_ft += 1
        if total >= 2:
            over15 += 1
        if total >= 3:
            over25 += 1
        if total >= 4:
            over35 += 1
        if total <= 3:
            under35 += 1
        if gc > 0 and gf > 0:
            btts += 1
        if gc - gf >= 3:
            goleada_casa += 1
        if gf - gc >= 3:
            goleada_fora += 1
        key = f"{gc}-{gf}"
        placares[key] = placares.get(key, 0) + 1

        eventos = []
        for g in gols_por_jogo.get(j["id"], []):
            lado = _lado_gol(g, j["casa_id"], j["fora_id"])
            eventos.append((_t_gol(g), 1 if lado == "casa" else -1))
        eventos.sort(key=lambda x: x[0])
        ht_casa, ht_fora = _score_at(eventos, 45.999)
        if ht_casa + ht_fora >= 1:
            over05_ht += 1

    barras = [
        {"chave": "over05_ht", "label": "Over 0,5HT", "pct": _pct(over05_ht, n), "n": over05_ht},
        {"chave": "over05_ft", "label": "Over 0,5FT", "pct": _pct(over05_ft, n), "n": over05_ft},
        {"chave": "over15", "label": "Over 1,5", "pct": _pct(over15, n), "n": over15},
        {"chave": "over25", "label": "Over 2,5", "pct": _pct(over25, n), "n": over25},
        {"chave": "over35", "label": "Over 3,5", "pct": _pct(over35, n), "n": over35},
        {"chave": "under35", "label": "Under 3,5", "pct": _pct(under35, n), "n": under35},
        {"chave": "btts", "label": "Ambos marcam", "pct": _pct(btts, n), "n": btts},
        {
            "chave": "goleada_casa",
            "label": "Goleadas do mandante",
            "pct": _pct(goleada_casa, n),
            "n": goleada_casa,
        },
        {
            "chave": "goleada_fora",
            "label": "Goleadas do visitante",
            "pct": _pct(goleada_fora, n),
            "n": goleada_fora,
        },
    ]
    top_placares = [
        {"placar": k, "jogos": v, "pct": _pct(v, n)}
        for k, v in sorted(placares.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    ]

    return {
        "grupos": GRUPOS_LABELS,
        "grupo": "apostas",
        "metricas": [],
        "linhas": [],
        "total": n,
        "page": 1,
        "page_size": n or 1,
        "pages": 1,
        "temporada": temporada,
        "temporadas": temps,
        "apostas": {"jogos": n, "barras": barras, "placares": top_placares},
    }


def coletivas_tabela(
    *,
    campeonato_id: int | None = None,
    pais: str | None = None,
    temporada: str | None = None,
    grupo: str = "ataque",
    clube_ids: list[int] | None = None,
    page: int = 1,
    page_size: int = 20,
    ordenar: str | None = None,
    ordem: str = "desc",
    mando: str | None = None,
    clube_id: int | None = None,
) -> dict:
    """Tabela coletiva: 1 linha por clube, colunas = métricas do grupo (soma + média)."""
    if grupo not in GRUPOS_LABELS:
        grupo = "ataque"
    if grupo == "apostas":
        return apostas_analise(
            temporada=temporada,
            campeonato_id=campeonato_id,
            pais=pais,
            clube_id=clube_id,
            mando=mando,
        )
    if grupo == "minutos":
        return minutos_coletivas(
            campeonato_id=campeonato_id,
            pais=pais,
            temporada=temporada,
            page=page,
            page_size=page_size,
            ordenar=ordenar,
            ordem=ordem,
            clube_id=clube_id,
            mando=mando,
        )

    temps = temporadas_filtro(campeonato_id, pais)
    if temporada not in temps:
        temporada = temps[0] if temps else None
    # Filtro de um clube (toolbar) → clube_ids
    if clube_id and not clube_ids:
        clube_ids = [clube_id]
    if not temporada:
        return {
            "grupos": GRUPOS_LABELS,
            "grupo": grupo,
            "metricas": [],
            "linhas": [],
            "total": 0,
            "page": 1,
            "page_size": page_size,
            "temporada": None,
            "temporadas": [],
        }

    if grupo == "rating":
        pares = [("rating", "Nota")]
        col_sql = "NULL::float AS sum_rating, NULL::float AS avg_rating"
    elif grupo == "fisicos":
        pares = GRUPOS_COLETIVAS["fisicos"]
        col_sql = ", ".join(
            f"NULL::float AS sum_{c}, NULL::float AS avg_{c}" for c, _ in pares
        )
    else:
        pares = GRUPOS_COLETIVAS.get(grupo, GRUPOS_COLETIVAS["ataque"])
        col_sql = ", ".join(f"SUM(e.{c}) AS sum_{c}, AVG(e.{c}) AS avg_{c}" for c, _ in pares)

    filtros = [
        "j.temporada = %s",
        "j.gols_casa IS NOT NULL",
        "e.periodo = 'Completo'",
    ]
    params: list = [temporada]

    if campeonato_id:
        filtros.append("j.campeonato_id = %s")
        params.append(campeonato_id)
    if pais:
        filtros.append("p.nome = %s")
        params.append(pais)
    if clube_ids:
        ph = ",".join(["%s"] * len(clube_ids))
        filtros.append(f"e.clube_id IN ({ph})")
        params.extend(clube_ids)
    mando_n = (mando or "todos").strip().lower()
    if mando_n in ("casa", "fora"):
        filtros.append("e.mando = %s")
        params.append("Casa" if mando_n == "casa" else "Fora")

    where = " AND ".join(filtros)

    rows = fetch_all(
        f"""
        SELECT e.clube_id,
               cl.clube,
               cf.id_externo AS id_fotmob,
               c.nome AS campeonato,
               c.id AS campeonato_id,
               p.nome AS pais,
               COUNT(DISTINCT e.jogo_id) AS jogos,
               {col_sql}
        FROM estatisticas e
        JOIN jogos j ON j.id = e.jogo_id
        JOIN clubes cl ON cl.id = e.clube_id
        JOIN campeonatos c ON c.id = j.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        LEFT JOIN clubes_fontes cf ON cf.clube_id = cl.id AND cf.fonte = 'fotmob'
        WHERE {where}
        GROUP BY e.clube_id, cl.clube, cf.id_externo, c.nome, c.id, p.nome
        """,
        params,
    )

    ratings = {}
    if grupo == "rating":
        rparams = [temporada]
        rfiltros = ["jo.temporada = %s", "jo.gols_casa IS NOT NULL", "i.rating IS NOT NULL"]
        if campeonato_id:
            rfiltros.append("jo.campeonato_id = %s")
            rparams.append(campeonato_id)
        if pais:
            rfiltros.append("p.nome = %s")
            rparams.append(pais)
        if clube_ids:
            ph = ",".join(["%s"] * len(clube_ids))
            rfiltros.append(f"i.clube_id IN ({ph})")
            rparams.extend(clube_ids)
        rwhere = " AND ".join(rfiltros)
        for r in fetch_all(
            f"""
            WITH por_jogo AS (
              SELECT i.clube_id, jo.campeonato_id, i.jogo_id,
                     AVG(i.rating) AS media_jogo
              FROM individual i
              JOIN jogos jo ON jo.id = i.jogo_id
              JOIN campeonatos c ON c.id = jo.campeonato_id
              LEFT JOIN paises p ON p.id = c.pais_id
              WHERE {rwhere}
              GROUP BY i.clube_id, jo.campeonato_id, i.jogo_id
            )
            SELECT clube_id, campeonato_id,
                   ROUND(SUM(media_jogo)::numeric, 2) AS sum_rating,
                   ROUND(AVG(media_jogo)::numeric, 2) AS avg_rating
            FROM por_jogo
            GROUP BY clube_id, campeonato_id
            """,
            rparams,
        ):
            s = _serialize(r)
            ratings[(r["clube_id"], r["campeonato_id"])] = (
                s.get("sum_rating"),
                s.get("avg_rating"),
            )

    # Dados físicos vêm do Sofascore (outro campeonato/clube_id); cruza por id ou nome.
    fis_by_id: dict = {}
    fis_by_key: dict = {}
    if grupo == "fisicos":
        pais_fis = pais
        if not pais_fis and campeonato_id:
            prow = fetch_one(
                """
                SELECT p.nome AS pais
                FROM campeonatos c
                LEFT JOIN paises p ON p.id = c.pais_id
                WHERE c.id = %s
                """,
                (campeonato_id,),
            )
            pais_fis = (prow or {}).get("pais")
        fis_by_id, fis_by_key = _fisicos_lookup(temporada, pais_fis, mando=mando)

    linhas = []
    for r in rows:
        item = _serialize(r)
        cid = item["clube_id"]
        camp_id = item["campeonato_id"]
        if grupo == "rating":
            soma, media = ratings.get((cid, camp_id), (None, None))
            item["sum_rating"] = soma
            item["avg_rating"] = media
        if grupo == "fisicos":
            _aplicar_fisicos(item, fis_by_id, fis_by_key)
        item["logo"] = _logo(item.get("id_fotmob"))
        vals = {}
        for col, _label in pares:
            vals[col] = {
                "soma": item.get(f"sum_{col}"),
                "media": item.get(f"avg_{col}"),
            }
        item["valores"] = vals
        linhas.append(item)

    # ordenação
    sort_key = ordenar or (pares[0][0] if pares else "jogos")
    reverse = (ordem or "desc").lower() != "asc"

    def _sort_val(linha):
        if sort_key == "clube":
            return (linha.get("clube") or "").lower()
        if sort_key == "jogos":
            return linha.get("jogos") or 0
        if sort_key == "pais":
            return (linha.get("pais") or "").lower()
        if sort_key == "campeonato":
            return (linha.get("campeonato") or "").lower()
        v = (linha.get("valores") or {}).get(sort_key) or {}
        # preferir média para ordenar
        val = v.get("media")
        if val is None:
            val = v.get("soma")
        return val if val is not None else -999999

    linhas.sort(key=_sort_val, reverse=reverse)

    total = len(linhas)
    page = max(1, int(page or 1))
    page_size = max(1, min(100, int(page_size or 20)))
    if clube_ids:
        # modo comparação: sem paginação forçada
        page_slice = linhas
        page = 1
        page_size = max(len(linhas), 1)
    else:
        start = (page - 1) * page_size
        page_slice = linhas[start : start + page_size]

    return {
        "grupos": GRUPOS_LABELS,
        "grupo": grupo,
        "metricas": [{"chave": c, "label": lab} for c, lab in pares],
        "linhas": page_slice,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "temporada": temporada,
        "temporadas": temps,
        "ordenar": sort_key,
        "ordem": "desc" if reverse else "asc",
        "mando": (mando or "todos").lower(),
    }


def minutos_analise(
    *,
    clube_id: int | None = None,
    temporada: str | None = None,
    campeonato_id: int | None = None,
    pais: str | None = None,
    mando: str | None = None,
) -> dict:
    """Gols por minuto + % tempo vencendo/empatando/perdendo.

    Sem clube_id: agrega todos os clubes do escopo (padrão do portal).
    mando: todos | casa | fora.
    """
    filtros = ["j.gols_casa IS NOT NULL"]
    params: list = []
    if clube_id:
        filtros.append("(j.casa_id = %s OR j.fora_id = %s)")
        params.extend([clube_id, clube_id])
    if temporada:
        filtros.append("j.temporada = %s")
        params.append(temporada)
    if campeonato_id:
        filtros.append("j.campeonato_id = %s")
        params.append(campeonato_id)
    if pais:
        filtros.append("p.nome = %s")
        params.append(pais)
    where = " AND ".join(filtros)
    mando_n = (mando or "todos").strip().lower()

    jogos = fetch_all(
        f"""
        SELECT j.id, j.casa_id, j.fora_id, j.gols_casa, j.gols_fora
        FROM jogos j
        JOIN campeonatos c ON c.id = j.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        WHERE {where}
        ORDER BY j.data, j.id
        """,
        params,
    )
    gols_rows = fetch_all(
        f"""
        SELECT f.jogo_id, f.minuto, f.minuto_adicional, f.mando, f.foi_gol_contra, f.clube_id
        FROM finalizacoes f
        JOIN jogos j ON j.id = f.jogo_id
        JOIN campeonatos c ON c.id = j.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        WHERE {where}
          AND LOWER(COALESCE(f.tipo_evento, '')) LIKE '%%gol%%'
        ORDER BY f.jogo_id, COALESCE(f.minuto, 0), COALESCE(f.minuto_adicional, 0), f.id
        """,
        params,
    )
    gols_por_jogo: dict[int, list] = {}
    for g in gols_rows:
        gols_por_jogo.setdefault(g["jogo_id"], []).append(g)

    hist = {m: 0 for m in range(1, 91)}
    hist[91] = 0  # 90+
    vencendo = empatando = perdendo = 0.0
    perspectivas = 0

    def _processar(jogo: dict, perspective_id: int):
        nonlocal vencendo, empatando, perdendo, perspectivas
        perspectivas += 1
        jid = jogo["id"]
        eventos = []
        for g in gols_por_jogo.get(jid, []):
            minuto = int(g.get("minuto") or 0)
            add = int(g.get("minuto_adicional") or 0)
            t = minuto + (0.01 * add if add else 0)
            contra = bool(g.get("foi_gol_contra"))
            do_clube = g.get("clube_id") == perspective_id
            a_favor = (not do_clube) if contra else do_clube
            if a_favor:
                bucket = 91 if minuto >= 90 else max(1, min(90, minuto or 1))
                hist[bucket] += 1
            eventos.append((t, 1 if a_favor else -1))

        eventos.sort(key=lambda x: x[0])
        placar_eu = placar_eles = 0
        t_prev = 0.0
        fim = 90.0

        def _acum(dt: float):
            nonlocal vencendo, empatando, perdendo
            if dt <= 0:
                return
            if placar_eu > placar_eles:
                vencendo += dt
            elif placar_eu < placar_eles:
                perdendo += dt
            else:
                empatando += dt

        for t, delta in eventos:
            t_clip = min(max(t, 0.0), fim)
            _acum(t_clip - t_prev)
            t_prev = t_clip
            if delta > 0:
                placar_eu += 1
            else:
                placar_eles += 1
        _acum(fim - t_prev)

    for jogo in jogos:
        candidatos = []
        if clube_id:
            if jogo["casa_id"] == clube_id:
                candidatos.append(jogo["casa_id"])
            elif jogo["fora_id"] == clube_id:
                candidatos.append(jogo["fora_id"])
        else:
            candidatos = [jogo["casa_id"], jogo["fora_id"]]

        for pid in candidatos:
            eh_casa = pid == jogo["casa_id"]
            if mando_n == "casa" and not eh_casa:
                continue
            if mando_n == "fora" and eh_casa:
                continue
            _processar(jogo, pid)

    total_t = vencendo + empatando + perdendo
    pct = lambda x: round(100.0 * x / total_t, 1) if total_t else 0.0
    gols_minuto = [{"minuto": m, "label": str(m), "gols": hist[m]} for m in range(1, 90)]
    gols_minuto.append({"minuto": 90, "label": "90+", "gols": hist[90] + hist[91]})

    return {
        "clube_id": clube_id,
        "jogos": len(jogos),
        "perspectivas": perspectivas,
        "gols_por_minuto": gols_minuto,
        "estado": {
            "vencendo": pct(vencendo),
            "empatando": pct(empatando),
            "perdendo": pct(perdendo),
            "minutos_vencendo": round(vencendo, 1),
            "minutos_empatando": round(empatando, 1),
            "minutos_perdendo": round(perdendo, 1),
        },
    }


def minutos_coletivas(
    *,
    campeonato_id: int | None = None,
    pais: str | None = None,
    temporada: str | None = None,
    page: int = 1,
    page_size: int = 20,
    ordenar: str | None = None,
    ordem: str = "desc",
    clube_id: int | None = None,
    mando: str | None = None,
) -> dict:
    temps = temporadas_filtro(campeonato_id, pais)
    if temporada not in temps:
        temporada = temps[0] if temps else None
    if not temporada:
        return {
            "grupos": GRUPOS_LABELS,
            "grupo": "minutos",
            "metricas": [],
            "linhas": [],
            "total": 0,
            "page": 1,
            "page_size": page_size,
            "temporada": None,
            "temporadas": [],
            "mapa_clube_id": None,
            "minutos": None,
        }

    filtros = ["j.temporada = %s", "j.gols_casa IS NOT NULL"]
    params: list = [temporada]
    if campeonato_id:
        filtros.append("j.campeonato_id = %s")
        params.append(campeonato_id)
    if pais:
        filtros.append("p.nome = %s")
        params.append(pais)
    where = " AND ".join(filtros)

    rows = fetch_all(
        f"""
        WITH lados AS (
          SELECT j.casa_id AS clube_id, j.campeonato_id, j.id AS jogo_id
          FROM jogos j
          JOIN campeonatos c ON c.id = j.campeonato_id
          LEFT JOIN paises p ON p.id = c.pais_id
          WHERE {where}
          UNION ALL
          SELECT j.fora_id, j.campeonato_id, j.id
          FROM jogos j
          JOIN campeonatos c ON c.id = j.campeonato_id
          LEFT JOIN paises p ON p.id = c.pais_id
          WHERE {where}
        )
        SELECT l.clube_id, cl.clube, cf.id_externo AS id_fotmob,
               c.nome AS campeonato, c.id AS campeonato_id, p.nome AS pais,
               COUNT(DISTINCT l.jogo_id) AS jogos
        FROM lados l
        JOIN clubes cl ON cl.id = l.clube_id
        JOIN campeonatos c ON c.id = l.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        LEFT JOIN clubes_fontes cf ON cf.clube_id = cl.id AND cf.fonte = 'fotmob'
        GROUP BY l.clube_id, cl.clube, cf.id_externo, c.nome, c.id, p.nome
        """,
        (*params, *params),
    )
    linhas = []
    for r in rows:
        item = _serialize(r)
        item["logo"] = _logo(item.get("id_fotmob"))
        item["valores"] = {}
        linhas.append(item)

    sort_key = ordenar or "jogos"
    reverse = (ordem or "desc").lower() != "asc"

    def _sv(l):
        if sort_key == "clube":
            return (l.get("clube") or "").lower()
        return l.get("jogos") or 0

    linhas.sort(key=_sv, reverse=reverse)
    total = len(linhas)
    alvo = clube_id if clube_id and any(l["clube_id"] == clube_id for l in linhas) else None

    minutos = minutos_analise(
        clube_id=alvo,
        temporada=temporada,
        campeonato_id=campeonato_id,
        pais=pais,
        mando=mando,
    )

    clubes = [
        {
            "id": l["clube_id"],
            "clube": l["clube"],
            "logo": l.get("logo"),
            "campeonato": l.get("campeonato"),
            "campeonato_id": l.get("campeonato_id"),
            "jogos": l.get("jogos"),
        }
        for l in linhas
    ]

    return {
        "grupos": GRUPOS_LABELS,
        "grupo": "minutos",
        "metricas": [],
        "linhas": [],
        "clubes": clubes,
        "total": total,
        "page": 1,
        "page_size": total or page_size,
        "pages": 1,
        "temporada": temporada,
        "temporadas": temps,
        "ordenar": sort_key,
        "ordem": "desc" if reverse else "asc",
        "mapa_clube_id": alvo,
        "mando": (mando or "todos").lower(),
        "minutos": minutos,
    }


def coletivas_clubes(
    campeonato_id: int,
    temporada: str,
    clube_ids: list[int],
    grupo: str = "ataque",
) -> dict:
    """Compat: comparação de clubes selecionados (liga)."""
    ids = clube_ids[:5]
    data = coletivas_tabela(
        campeonato_id=campeonato_id,
        temporada=temporada,
        grupo=grupo,
        clube_ids=ids,
        page=1,
        page_size=5,
    )
    clubes = []
    for cid in ids:
        row = next((l for l in data["linhas"] if l["clube_id"] == cid), None)
        if row:
            clubes.append(
                {"id": row["clube_id"], "clube": row["clube"], "logo": row.get("logo")}
            )
        else:
            # ainda listar clube mesmo sem stats
            info = fetch_one(
                """
                SELECT c.id, c.clube, cf.id_externo AS id_fotmob
                FROM clubes c
                LEFT JOIN clubes_fontes cf ON cf.clube_id = c.id AND cf.fonte = 'fotmob'
                WHERE c.id = %s
                """,
                (cid,),
            )
            if info:
                item = _serialize(info)
                clubes.append(
                    {"id": item["id"], "clube": item["clube"], "logo": _logo(item.get("id_fotmob"))}
                )
    data["clubes"] = clubes
    return data


def _scope_filtros(
    alias_jogo: str = "jo",
    *,
    campeonato_id: int | None,
    temporada: str | None,
    pais: str | None,
) -> tuple[str, list]:
    filtros = [f"{alias_jogo}.gols_casa IS NOT NULL"]
    params: list = []
    if temporada:
        filtros.append(f"{alias_jogo}.temporada = %s")
        params.append(temporada)
    if campeonato_id:
        filtros.append(f"{alias_jogo}.campeonato_id = %s")
        params.append(campeonato_id)
    if pais:
        filtros.append("p.nome = %s")
        params.append(pais)
    return " AND ".join(filtros), params


def individuais_filtros(
    temporada: str | None = None,
    campeonato_id: int | None = None,
    pais: str | None = None,
) -> dict:
    where, params = _scope_filtros(
        "jo", campeonato_id=campeonato_id, temporada=temporada, pais=pais
    )
    join_pais = "JOIN campeonatos c ON c.id = jo.campeonato_id LEFT JOIN paises p ON p.id = c.pais_id"
    posicoes = fetch_all(
        f"""
        SELECT DISTINCT jg.posicao
        FROM individual i
        JOIN jogos jo ON jo.id = i.jogo_id
        JOIN jogadores jg ON jg.id = i.jogador_id
        {join_pais}
        WHERE {where} AND jg.posicao IS NOT NULL
        ORDER BY jg.posicao
        """,
        params,
    )
    nacionalidades = fetch_all(
        f"""
        SELECT DISTINCT jg.nacionalidade
        FROM individual i
        JOIN jogos jo ON jo.id = i.jogo_id
        JOIN jogadores jg ON jg.id = i.jogador_id
        {join_pais}
        WHERE {where} AND jg.nacionalidade IS NOT NULL
        ORDER BY jg.nacionalidade
        """,
        params,
    )
    clubes = fetch_all(
        f"""
        SELECT DISTINCT cl.id, cl.clube, cf.id_externo AS id_fotmob
        FROM individual i
        JOIN jogos jo ON jo.id = i.jogo_id
        JOIN clubes cl ON cl.id = i.clube_id
        LEFT JOIN clubes_fontes cf ON cf.clube_id = cl.id AND cf.fonte = 'fotmob'
        {join_pais}
        WHERE {where}
        ORDER BY cl.clube
        """,
        params,
    )
    clubes_out = []
    for r in clubes:
        item = _serialize(r)
        item["logo"] = _logo(item.get("id_fotmob"))
        clubes_out.append(item)
    return {
        "posicoes": [r["posicao"] for r in posicoes],
        "nacionalidades": [r["nacionalidade"] for r in nacionalidades],
        "clubes": clubes_out,
        "metricas": {k: v[1] for k, v in METRICAS_INDIVIDUAIS.items()},
    }


def individuais_ranking(
    temporada: str | None = None,
    campeonato_id: int | None = None,
    pais: str | None = None,
    metrica: str = "gols",
    limite: int = 50,
    posicao: str | None = None,
    clube_id: int | None = None,
    nacionalidade: str | None = None,
    ordenar: str | None = None,
    ordem: str = "desc",
    mando: str | None = None,
) -> list[dict]:
    expr, _ = METRICAS_INDIVIDUAIS.get(metrica, METRICAS_INDIVIDUAIS["gols"])
    where, params = _scope_filtros(
        "jo", campeonato_id=campeonato_id, temporada=temporada, pais=pais
    )
    if posicao:
        where += " AND jg.posicao = %s"
        params.append(posicao)
    if clube_id:
        where += " AND i.clube_id = %s"
        params.append(clube_id)
    if nacionalidade:
        where += " AND jg.nacionalidade = %s"
        params.append(nacionalidade)
    mando_n = (mando or "todos").strip().lower()
    if mando_n in ("casa", "fora"):
        where += " AND i.mando = %s"
        params.append("Casa" if mando_n == "casa" else "Fora")

    sort_map = {
        "valor": "valor",
        "gols": "valor",
        "jogos": "jogos",
        "rating": "rating_medio",
        "rating_medio": "rating_medio",
        "nome": "jg.nome",
        "clube": "cl.clube",
        "posicao": "jg.posicao",
        "nacionalidade": "jg.nacionalidade",
        "campeonato": "campeonato",
    }
    sort_col = sort_map.get(ordenar or "valor", "valor")
    direction = "ASC" if (ordem or "desc").lower() == "asc" else "DESC"

    rows = fetch_all(
        f"""
        SELECT jg.id AS jogador_id, jg.nome, jg.foto, jg.posicao, jg.nacionalidade,
               cl.id AS clube_id, cl.clube, cf.id_externo AS clube_id_fotmob,
               c.nome AS campeonato, c.id AS campeonato_id,
               {expr} AS valor,
               COUNT(DISTINCT i.jogo_id) AS jogos,
               ROUND(AVG(i.rating)::numeric, 2) AS rating_medio
        FROM individual i
        JOIN jogos jo ON jo.id = i.jogo_id
        JOIN jogadores jg ON jg.id = i.jogador_id
        JOIN clubes cl ON cl.id = i.clube_id
        JOIN campeonatos c ON c.id = jo.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        LEFT JOIN clubes_fontes cf ON cf.clube_id = cl.id AND cf.fonte = 'fotmob'
        WHERE {where}
        GROUP BY jg.id, jg.nome, jg.foto, jg.posicao, jg.nacionalidade,
                 cl.id, cl.clube, cf.id_externo, c.nome, c.id
        HAVING {expr} IS NOT NULL
        ORDER BY {sort_col} {direction} NULLS LAST, jg.nome
        LIMIT %s
        """,
        (*params, limite),
    )
    out = []
    for i, r in enumerate(rows, start=1):
        item = _serialize(r)
        item["posicao_rank"] = i
        item["clube_logo"] = _logo(item.get("clube_id_fotmob"))
        jogos = item.get("jogos") or 0
        valor = item.get("valor")
        if metrica == "rating":
            item["valor_soma"] = None
            item["valor_media"] = valor
        else:
            item["valor_soma"] = valor
            item["valor_media"] = round(float(valor) / jogos, 2) if valor is not None and jogos else None
        out.append(item)
    return out


def tecnicos_ranking(
    temporada: str | None = None,
    campeonato_id: int | None = None,
    pais: str | None = None,
    ordenar: str | None = None,
    ordem: str = "desc",
    mando: str | None = None,
) -> list[dict]:
    filtros = ["j.gols_casa IS NOT NULL"]
    params: list = []
    if temporada:
        filtros.append("j.temporada = %s")
        params.append(temporada)
    if campeonato_id:
        filtros.append("j.campeonato_id = %s")
        params.append(campeonato_id)
    if pais:
        filtros.append("p.nome = %s")
        params.append(pais)
    where = " AND ".join(filtros)
    mando_n = (mando or "todos").strip().lower()
    lados_parts: list[str] = []
    if mando_n != "fora":
        lados_parts.append(
            """
          SELECT tecnico_casa_id AS tecnico_id, casa_id AS clube_id,
                 CASE WHEN gols_casa > gols_fora THEN 3
                      WHEN gols_casa = gols_fora THEN 1 ELSE 0 END AS pts,
                 CASE WHEN gols_casa > gols_fora THEN 1 ELSE 0 END AS v,
                 CASE WHEN gols_casa = gols_fora THEN 1 ELSE 0 END AS e,
                 CASE WHEN gols_casa < gols_fora THEN 1 ELSE 0 END AS d,
                 CASE WHEN gols_fora = 0 THEN 1 ELSE 0 END AS clean_sheets,
                 CASE WHEN gols_casa = 0 THEN 1 ELSE 0 END AS clean_goals
          FROM jogos_ok WHERE tecnico_casa_id IS NOT NULL
            """
        )
    if mando_n != "casa":
        lados_parts.append(
            """
          SELECT tecnico_fora_id, fora_id,
                 CASE WHEN gols_fora > gols_casa THEN 3
                      WHEN gols_fora = gols_casa THEN 1 ELSE 0 END,
                 CASE WHEN gols_fora > gols_casa THEN 1 ELSE 0 END,
                 CASE WHEN gols_fora = gols_casa THEN 1 ELSE 0 END,
                 CASE WHEN gols_fora < gols_casa THEN 1 ELSE 0 END,
                 CASE WHEN gols_casa = 0 THEN 1 ELSE 0 END,
                 CASE WHEN gols_fora = 0 THEN 1 ELSE 0 END
          FROM jogos_ok WHERE tecnico_fora_id IS NOT NULL
            """
        )
    if not lados_parts:
        return []
    lados_sql = " UNION ALL ".join(lados_parts)
    sort_map = {
        "pts": "pts",
        "jogos": "jogos",
        "pts_por_jogo": "pts_por_jogo",
        "nome": "t.nome",
        "clube": "clube",
        "v": "v",
        "clean_sheets": "clean_sheets",
        "clean_goals": "clean_goals",
    }
    sort_col = sort_map.get(ordenar or "pts", "pts")
    direction = "ASC" if (ordem or "desc").lower() == "asc" else "DESC"

    rows = fetch_all(
        f"""
        WITH jogos_ok AS (
          SELECT j.*, camp.nome AS campeonato
          FROM jogos j
          JOIN campeonatos camp ON camp.id = j.campeonato_id
          LEFT JOIN paises p ON p.id = camp.pais_id
          WHERE {where}
        ),
        lados AS (
          {lados_sql}
        )
        SELECT t.id, t.nome, t.nacionalidade, t.id_fotmob,
               COUNT(*) AS jogos,
               SUM(l.v) AS v, SUM(l.e) AS e, SUM(l.d) AS d,
               SUM(l.pts) AS pts,
               ROUND(AVG(l.pts)::numeric, 2) AS pts_por_jogo,
               SUM(l.clean_sheets) AS clean_sheets,
               SUM(l.clean_goals) AS clean_goals,
               ROUND(AVG(l.clean_sheets)::numeric, 2) AS clean_sheets_media,
               ROUND(AVG(l.clean_goals)::numeric, 2) AS clean_goals_media,
               MODE() WITHIN GROUP (ORDER BY c.clube) AS clube
        FROM lados l
        JOIN tecnicos t ON t.id = l.tecnico_id
        JOIN clubes c ON c.id = l.clube_id
        GROUP BY t.id, t.nome, t.nacionalidade, t.id_fotmob
        ORDER BY {sort_col} {direction} NULLS LAST, jogos DESC
        """,
        params,
    )
    out = []
    for i, r in enumerate(rows, start=1):
        item = _serialize(r)
        item["posicao"] = i
        item["foto"] = FOTO_PESSOA.format(id=item["id_fotmob"]) if item.get("id_fotmob") else None
        out.append(item)
    return out


def arbitros_ranking(
    temporada: str | None = None,
    campeonato_id: int | None = None,
    pais: str | None = None,
    ordenar: str | None = None,
    ordem: str = "desc",
) -> list[dict]:
    filtros = ["j.gols_casa IS NOT NULL"]
    params: list = []
    if temporada:
        filtros.append("j.temporada = %s")
        params.append(temporada)
    if campeonato_id:
        filtros.append("j.campeonato_id = %s")
        params.append(campeonato_id)
    if pais:
        filtros.append("pa.nome = %s")
        params.append(pais)
    where = " AND ".join(filtros)
    sort_map = {
        "jogos": "jogos",
        "nome": "a.nome",
        "amarelos_por_jogo": "amarelos_por_jogo",
        "vermelhos_por_jogo": "vermelhos_por_jogo",
        "faltas_por_jogo": "faltas_por_jogo",
    }
    sort_col = sort_map.get(ordenar or "jogos", "jogos")
    direction = "ASC" if (ordem or "desc").lower() == "asc" else "DESC"

    rows = fetch_all(
        f"""
        SELECT a.id, a.nome, a.foto, p.nome AS pais,
               COUNT(DISTINCT j.id) AS jogos,
               ROUND(SUM(e.cartao_amarelo)::numeric / 2, 0) AS amarelos,
               ROUND(SUM(e.cartao_vermelho)::numeric / 2, 0) AS vermelhos,
               ROUND(SUM(e.faltas_cometidas)::numeric / 2, 0) AS faltas,
               ROUND(AVG(e.cartao_amarelo)::numeric, 2) AS amarelos_por_jogo,
               ROUND(AVG(e.cartao_vermelho)::numeric, 2) AS vermelhos_por_jogo,
               ROUND(AVG(e.faltas_cometidas)::numeric, 2) AS faltas_por_jogo
        FROM jogos j
        JOIN arbitros a ON a.id = j.arbitro_id
        LEFT JOIN paises p ON p.id = a.pais_id
        JOIN campeonatos c ON c.id = j.campeonato_id
        LEFT JOIN paises pa ON pa.id = c.pais_id
        JOIN estatisticas e ON e.jogo_id = j.id AND e.periodo = 'Completo'
        WHERE {where}
        GROUP BY a.id, a.nome, a.foto, p.nome
        ORDER BY {sort_col} {direction} NULLS LAST, a.nome
        """,
        params,
    )
    return [_serialize(r) | {"posicao": i} for i, r in enumerate(rows, start=1)]


def _fin_scope(temporada, campeonato_id, pais, mando: str | None = None):
    filtros = ["j.gols_casa IS NOT NULL", "f.coordenada_x IS NOT NULL", "f.coordenada_y IS NOT NULL"]
    params: list = []
    if temporada:
        filtros.append("j.temporada = %s")
        params.append(temporada)
    if campeonato_id:
        filtros.append("j.campeonato_id = %s")
        params.append(campeonato_id)
    if pais:
        filtros.append("p.nome = %s")
        params.append(pais)
    mando_n = (mando or "todos").strip().lower()
    if mando_n in ("casa", "fora"):
        filtros.append("f.mando = %s")
        params.append("Casa" if mando_n == "casa" else "Fora")
    return " AND ".join(filtros), params


def finalizacoes_clubes(
    *,
    temporada: str | None = None,
    campeonato_id: int | None = None,
    pais: str | None = None,
    ordenar: str | None = None,
    ordem: str = "desc",
    page: int = 1,
    page_size: int = 20,
    clube_id: int | None = None,
    mando: str | None = None,
) -> dict:
    where, params = _fin_scope(temporada, campeonato_id, pais, mando=mando)
    sort_map = {
        "clube": "cl.clube",
        "chutes": "chutes",
        "certas": "certas",
        "gols": "gols",
        "dist_chute": "dist_chute",
        "dist_certa": "dist_certa",
        "dist_gol": "dist_gol",
        "jogos": "jogos",
    }
    sort_col = sort_map.get(ordenar) or sort_map["gols"]
    direction = "ASC" if (ordem or "desc").lower() == "asc" else "DESC"

    rows = fetch_all(
        f"""
        SELECT f.clube_id, cl.clube, cf.id_externo AS id_fotmob,
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
        JOIN clubes cl ON cl.id = f.clube_id
        JOIN campeonatos c ON c.id = j.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        LEFT JOIN clubes_fontes cf ON cf.clube_id = cl.id AND cf.fonte = 'fotmob'
        WHERE {where}
        GROUP BY f.clube_id, cl.clube, cf.id_externo, c.nome, c.id
        ORDER BY {sort_col} {direction} NULLS LAST, cl.clube
        """,
        params,
    )
    linhas = []
    for r in rows:
        item = _serialize(r)
        item["logo"] = _logo(item.get("id_fotmob"))
        jogos = item.get("jogos") or 1
        for k in ("chutes", "certas", "gols"):
            item[f"{k}_media"] = round(float(item.get(k) or 0) / jogos, 2)
        linhas.append(item)

    total = len(linhas)
    page = max(1, int(page or 1))
    page_size = max(1, min(100, int(page_size or 20)))
    start = (page - 1) * page_size
    page_rows = linhas[start : start + page_size]

    mapa = []
    alvo = clube_id or (page_rows[0]["clube_id"] if page_rows else None)
    if alvo:
        mapa = finalizacoes_mapa(
            temporada=temporada,
            campeonato_id=campeonato_id,
            pais=pais,
            clube_id=alvo,
            mando=mando,
        )

    return {
        "linhas": page_rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "ordenar": ordenar or "gols",
        "ordem": "desc" if direction == "DESC" else "asc",
        "mapa_clube_id": alvo,
        "mapa": mapa,
    }


def finalizacoes_jogadores(
    *,
    temporada: str | None = None,
    campeonato_id: int | None = None,
    pais: str | None = None,
    ordenar: str | None = None,
    ordem: str = "desc",
    limite: int = 50,
    jogador_id: int | None = None,
    clube_id: int | None = None,
    mando: str | None = None,
) -> dict:
    where, params = _fin_scope(temporada, campeonato_id, pais, mando=mando)
    if clube_id:
        where += " AND f.clube_id = %s"
        params.append(clube_id)
    sort_map = {
        "nome": "jg.nome",
        "clube": "cl.clube",
        "chutes": "chutes",
        "certas": "certas",
        "gols": "gols",
        "dist_chute": "dist_chute",
        "dist_certa": "dist_certa",
        "dist_gol": "dist_gol",
        "jogos": "jogos",
    }
    sort_col = sort_map.get(ordenar) or sort_map["gols"]
    direction = "ASC" if (ordem or "desc").lower() == "asc" else "DESC"

    rows = fetch_all(
        f"""
        SELECT jg.id AS jogador_id, jg.nome, jg.foto, jg.posicao,
               cl.id AS clube_id, cl.clube, cf.id_externo AS clube_id_fotmob,
               c.nome AS campeonato,
               COUNT(DISTINCT j.id) AS jogos,
               COUNT(*) AS chutes,
               COUNT(*) FILTER (WHERE {_IS_CERTA}) AS certas,
               COUNT(*) FILTER (WHERE {_IS_GOL}) AS gols,
               ROUND(AVG({_DIST_M})::numeric, 1) AS dist_chute,
               ROUND(AVG({_DIST_M}) FILTER (WHERE {_IS_CERTA})::numeric, 1) AS dist_certa,
               ROUND(AVG({_DIST_M}) FILTER (WHERE {_IS_GOL})::numeric, 1) AS dist_gol
        FROM finalizacoes f
        JOIN jogos j ON j.id = f.jogo_id
        JOIN jogadores jg ON jg.id = f.jogador_id
        JOIN clubes cl ON cl.id = f.clube_id
        JOIN campeonatos c ON c.id = j.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        LEFT JOIN clubes_fontes cf ON cf.clube_id = cl.id AND cf.fonte = 'fotmob'
        WHERE {where}
        GROUP BY jg.id, jg.nome, jg.foto, jg.posicao, cl.id, cl.clube, cf.id_externo, c.nome
        ORDER BY {sort_col} {direction} NULLS LAST, jg.nome
        LIMIT %s
        """,
        (*params, limite),
    )
    linhas = []
    for i, r in enumerate(rows, start=1):
        item = _serialize(r)
        item["posicao_rank"] = i
        item["clube_logo"] = _logo(item.get("clube_id_fotmob"))
        jogos = item.get("jogos") or 1
        for k in ("chutes", "certas", "gols"):
            item[f"{k}_media"] = round(float(item.get(k) or 0) / jogos, 2)
        linhas.append(item)

    mapa = []
    alvo_j = jogador_id or (linhas[0]["jogador_id"] if linhas else None)
    alvo_c = None
    if alvo_j:
        row = next((x for x in linhas if x["jogador_id"] == alvo_j), linhas[0] if linhas else None)
        alvo_c = row["clube_id"] if row else None
        mapa = finalizacoes_mapa(
            temporada=temporada,
            campeonato_id=campeonato_id,
            pais=pais,
            jogador_id=alvo_j,
            clube_id=alvo_c,
            mando=mando,
        )

    return {
        "linhas": linhas,
        "ordenar": ordenar or "gols",
        "ordem": "desc" if direction == "DESC" else "asc",
        "mapa_jogador_id": alvo_j,
        "mapa": mapa,
    }


def finalizacoes_mapa(
    *,
    temporada: str | None = None,
    campeonato_id: int | None = None,
    pais: str | None = None,
    clube_id: int | None = None,
    jogador_id: int | None = None,
    limite: int = 400,
    mando: str | None = None,
) -> list[dict]:
    where, params = _fin_scope(temporada, campeonato_id, pais, mando=mando)
    if clube_id:
        where += " AND f.clube_id = %s"
        params.append(clube_id)
    if jogador_id:
        where += " AND f.jogador_id = %s"
        params.append(jogador_id)
    rows = fetch_all(
        f"""
        SELECT f.coordenada_x, f.coordenada_y, f.tipo_evento, f.foi_no_alvo,
               f.xg, f.minuto, jg.nome AS jogador,
               ROUND(({_DIST_M})::numeric, 1) AS distancia_m
        FROM finalizacoes f
        JOIN jogos j ON j.id = f.jogo_id
        JOIN campeonatos c ON c.id = j.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        LEFT JOIN jogadores jg ON jg.id = f.jogador_id
        WHERE {where}
        ORDER BY COALESCE(f.minuto, 0), f.id
        LIMIT %s
        """,
        (*params, limite),
    )
    out = []
    for r in rows:
        item = _serialize(r)
        x = float(item["coordenada_x"])
        y = float(item["coordenada_y"])
        # FotMob: x = comprimento (0→105), y = largura (0→68). Ataque para cima.
        item["left"] = round(100.0 * y / _PITCH_WID, 2)
        item["top"] = round(100.0 * (_PITCH_LEN - x) / _PITCH_LEN, 2)
        te = (item.get("tipo_evento") or "").lower()
        if "gol" in te:
            item["classe"] = "gol"
        elif te == "defendida":
            item["classe"] = "certa"
        else:
            item["classe"] = "outra"
        out.append(item)
    return out
