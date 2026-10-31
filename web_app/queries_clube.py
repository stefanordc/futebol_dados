"""Página do clube: geral, estatísticas, elenco, análise."""

from __future__ import annotations

from db import fetch_all, fetch_one
from queries import _serialize, clube_match_key
from queries_stats import (
    GRUPOS_CLUBE,
    GRUPOS_LABELS,
    FOTO_PESSOA,
    _lado_gol,
    _logo,
    _pct,
    _score_at,
    _t_gol,
    coletivas_tabela,
    minutos_analise,
)

_ORDEM_POS = [
    ("goleiro", "Goleiro"),
    ("lateral-direito", "Lateral-direito"),
    ("lateral-esquerdo", "Lateral-esquerdo"),
    ("zagueiro", "Zagueiro"),
    ("volante", "Volante"),
    ("meia", "Meia"),
    ("atacante", "Atacante"),
    ("tecnico", "Técnico"),
]


def _bloco_posicao(posicao: str | None) -> str:
    p = (posicao or "").casefold()
    if "goleiro" in p:
        return "goleiro"
    if "lateral" in p and "direit" in p:
        return "lateral-direito"
    if "lateral" in p and "esquerd" in p:
        return "lateral-esquerdo"
    if "ala" in p and "direit" in p:
        return "lateral-direito"
    if "ala" in p and "esquerd" in p:
        return "lateral-esquerdo"
    if "zagueiro" in p or "defensor" in p:
        return "zagueiro"
    if "volante" in p:
        return "volante"
    if "meia" in p or "meio" in p:
        return "meia"
    if any(x in p for x in ("atacante", "ponta", "centroavante", "avançado", "avancado")):
        return "atacante"
    return "meia"


def clube_base(clube_id: int) -> dict | None:
    row = fetch_one(
        """
        SELECT c.id, c.clube, cf.id_externo AS id_fotmob, p.nome AS pais
        FROM clubes c
        LEFT JOIN clubes_fontes cf ON cf.clube_id = c.id AND cf.fonte = 'fotmob'
        LEFT JOIN paises p ON p.id = c.pais_id
        WHERE c.id = %s
        """,
        (clube_id,),
    )
    if not row:
        return None
    item = _serialize(row)
    item["logo"] = _logo(item.get("id_fotmob"))
    item["nome"] = item.get("clube")
    return item


def temporadas_clube(clube_id: int) -> list[str]:
    rows = fetch_all(
        """
        SELECT DISTINCT temporada FROM jogos
        WHERE (casa_id = %s OR fora_id = %s) AND temporada IS NOT NULL
          AND gols_casa IS NOT NULL
        ORDER BY temporada DESC
        """,
        (clube_id, clube_id),
    )
    return [r["temporada"] for r in rows]


def campeonatos_clube(clube_id: int, temporada: str | None = None) -> list[dict]:
    filtros = [
        "(j.casa_id = %s OR j.fora_id = %s)",
        "j.gols_casa IS NOT NULL",
    ]
    params: list = [clube_id, clube_id]
    if temporada:
        filtros.append("j.temporada = %s")
        params.append(temporada)
    rows = fetch_all(
        f"""
        SELECT c.id, c.nome, COUNT(j.id) AS jogos
        FROM jogos j
        JOIN campeonatos c ON c.id = j.campeonato_id
        WHERE {" AND ".join(filtros)}
        GROUP BY c.id, c.nome
        ORDER BY c.nome
        """,
        params,
    )
    return [_serialize(r) for r in rows]


def _sql_jogo_escopo(
    alias: str = "j",
    *,
    campeonato_id: int | None = None,
    mando: str | None = None,
    clube_id: int | None = None,
) -> tuple[str, list]:
    """Fragmento AND … + params para campeonato/mando no escopo do clube."""
    parts: list[str] = []
    params: list = []
    if campeonato_id:
        parts.append(f"{alias}.campeonato_id = %s")
        params.append(campeonato_id)
    mando_n = (mando or "todos").strip().lower()
    if clube_id and mando_n == "casa":
        parts.append(f"{alias}.casa_id = %s")
        params.append(clube_id)
    elif clube_id and mando_n == "fora":
        parts.append(f"{alias}.fora_id = %s")
        params.append(clube_id)
    return ((" AND " + " AND ".join(parts)) if parts else ""), params


def geral_clube(
    clube_id: int,
    temporada: str,
    *,
    campeonato_id: int | None = None,
    mando: str | None = None,
) -> dict:
    mando_n = (mando or "todos").strip().lower()
    camp_sql = " AND j.campeonato_id = %s" if campeonato_id else ""
    lados = []
    params: list = []
    if mando_n != "fora":
        lados.append(
            f"""
          SELECT j.campeonato_id,
                 CASE WHEN j.gols_casa > j.gols_fora THEN 1 ELSE 0 END AS v,
                 CASE WHEN j.gols_casa = j.gols_fora THEN 1 ELSE 0 END AS e,
                 CASE WHEN j.gols_casa < j.gols_fora THEN 1 ELSE 0 END AS d,
                 j.gols_casa AS gm, j.gols_fora AS gs,
                 CASE WHEN j.gols_fora = 0 THEN 1 ELSE 0 END AS cs,
                 CASE WHEN j.gols_casa = 0 THEN 1 ELSE 0 END AS cg,
                 j.id AS jogo_id
          FROM jogos j
          WHERE j.temporada = %s AND j.gols_casa IS NOT NULL AND j.casa_id = %s{camp_sql}
            """
        )
        params.extend([temporada, clube_id])
        if campeonato_id:
            params.append(campeonato_id)
    if mando_n != "casa":
        lados.append(
            f"""
          SELECT j.campeonato_id,
                 CASE WHEN j.gols_fora > j.gols_casa THEN 1 ELSE 0 END,
                 CASE WHEN j.gols_fora = j.gols_casa THEN 1 ELSE 0 END,
                 CASE WHEN j.gols_fora < j.gols_casa THEN 1 ELSE 0 END,
                 j.gols_fora, j.gols_casa,
                 CASE WHEN j.gols_casa = 0 THEN 1 ELSE 0 END,
                 CASE WHEN j.gols_fora = 0 THEN 1 ELSE 0 END,
                 j.id
          FROM jogos j
          WHERE j.temporada = %s AND j.gols_casa IS NOT NULL AND j.fora_id = %s{camp_sql}
            """
        )
        params.extend([temporada, clube_id])
        if campeonato_id:
            params.append(campeonato_id)
    if not lados:
        return {"linhas": [], "total": None}

    cart_params = [clube_id, temporada]
    cart_camp = ""
    if campeonato_id:
        cart_camp = " AND jo.campeonato_id = %s"
        cart_params.append(campeonato_id)
    params.extend(cart_params)

    rows = fetch_all(
        f"""
        WITH lados AS (
          {" UNION ALL ".join(lados)}
        ),
        cartoes AS (
          SELECT jo.campeonato_id,
                 SUM(COALESCE(e.cartao_amarelo,0)) AS amarelos,
                 SUM(COALESCE(e.cartao_vermelho,0)) AS vermelhos
          FROM estatisticas e
          JOIN jogos jo ON jo.id = e.jogo_id
          WHERE e.clube_id = %s AND e.periodo = 'Completo' AND jo.temporada = %s{cart_camp}
          GROUP BY jo.campeonato_id
        )
        SELECT c.id AS campeonato_id, c.nome AS campeonato,
               COUNT(*) AS jogos,
               SUM(l.v) AS v, SUM(l.e) AS e, SUM(l.d) AS d,
               SUM(l.gm) AS gols_marcados, SUM(l.gs) AS gols_sofridos,
               SUM(l.cs) AS clean_sheets, SUM(l.cg) AS clean_goals,
               COALESCE(MAX(ca.amarelos), 0) AS amarelos,
               COALESCE(MAX(ca.vermelhos), 0) AS vermelhos
        FROM lados l
        JOIN campeonatos c ON c.id = l.campeonato_id
        LEFT JOIN cartoes ca ON ca.campeonato_id = c.id
        GROUP BY c.id, c.nome
        ORDER BY jogos DESC, c.nome
        """,
        params,
    )
    linhas = []
    tot = {
        "campeonato": "Total temporada",
        "jogos": 0,
        "v": 0,
        "e": 0,
        "d": 0,
        "gols_marcados": 0,
        "gols_sofridos": 0,
        "clean_sheets": 0,
        "clean_goals": 0,
        "amarelos": 0,
        "vermelhos": 0,
    }
    for r in rows:
        item = _serialize(r)
        j = item.get("jogos") or 0
        item["saldo"] = (item.get("gols_marcados") or 0) - (item.get("gols_sofridos") or 0)
        pts = (item.get("v") or 0) * 3 + (item.get("e") or 0)
        item["aproveitamento"] = round(100.0 * pts / (j * 3), 1) if j else None
        item["media_gols_marcados"] = round((item.get("gols_marcados") or 0) / j, 2) if j else None
        item["media_gols_sofridos"] = round((item.get("gols_sofridos") or 0) / j, 2) if j else None
        linhas.append(item)
        for k in ("jogos", "v", "e", "d", "gols_marcados", "gols_sofridos", "clean_sheets", "clean_goals", "amarelos", "vermelhos"):
            tot[k] += item.get(k) or 0
    j = tot["jogos"]
    tot["saldo"] = tot["gols_marcados"] - tot["gols_sofridos"]
    tot["aproveitamento"] = round(100.0 * (tot["v"] * 3 + tot["e"]) / (j * 3), 1) if j else None
    tot["media_gols_marcados"] = round(tot["gols_marcados"] / j, 2) if j else None
    tot["media_gols_sofridos"] = round(tot["gols_sofridos"] / j, 2) if j else None
    tot["is_total"] = True
    return {"linhas": linhas, "total": tot}


def elenco_clube(
    clube_id: int,
    temporada: str,
    *,
    campeonato_id: int | None = None,
    mando: str | None = None,
) -> dict:
    extra, extra_params = _sql_jogo_escopo(
        "jo", campeonato_id=campeonato_id, mando=mando, clube_id=clube_id
    )
    jogadores = fetch_all(
        f"""
        SELECT jg.id, jg.nome, jg.posicao, jg.foto, jf.id_externo AS id_fotmob, jg.nacionalidade,
               COUNT(DISTINCT i.jogo_id) AS jogos,
               SUM(COALESCE(i.minutos,0)) AS minutos,
               SUM(COALESCE(i.gols,0)) AS gols,
               SUM(COALESCE(i.assistencias,0)) AS assistencias,
               ROUND(AVG(i.rating)::numeric, 2) AS rating
        FROM individual i
        JOIN jogos jo ON jo.id = i.jogo_id
        JOIN jogadores jg ON jg.id = i.jogador_id
        LEFT JOIN jogadores_fontes jf ON jf.jogador_id = jg.id AND jf.fonte = 'fotmob'
        WHERE i.clube_id = %s AND jo.temporada = %s AND jo.gols_casa IS NOT NULL{extra}
        GROUP BY jg.id, jg.nome, jg.posicao, jg.foto, jf.id_externo, jg.nacionalidade
        ORDER BY minutos DESC
        """,
        (clube_id, temporada, *extra_params),
    )
    blocos: dict[str, list] = {k: [] for k, _ in _ORDEM_POS}
    for r in jogadores:
        item = _serialize(r)
        if not item.get("foto") and item.get("id_fotmob"):
            item["foto"] = FOTO_PESSOA.format(id=item["id_fotmob"])
        key = _bloco_posicao(item.get("posicao"))
        blocos.setdefault(key, []).append(item)

    mando_n = (mando or "todos").strip().lower()
    camp_sql = " AND campeonato_id = %s" if campeonato_id else ""
    tec_lados = []
    tec_params: list = []
    if mando_n != "fora":
        tec_lados.append(
            f"""SELECT tecnico_casa_id AS tid FROM jogos
          WHERE temporada = %s AND casa_id = %s AND tecnico_casa_id IS NOT NULL
            AND gols_casa IS NOT NULL{camp_sql}"""
        )
        tec_params.extend([temporada, clube_id])
        if campeonato_id:
            tec_params.append(campeonato_id)
    if mando_n != "casa":
        tec_lados.append(
            f"""SELECT tecnico_fora_id FROM jogos
          WHERE temporada = %s AND fora_id = %s AND tecnico_fora_id IS NOT NULL
            AND gols_casa IS NOT NULL{camp_sql}"""
        )
        tec_params.extend([temporada, clube_id])
        if campeonato_id:
            tec_params.append(campeonato_id)
    tecnicos = (
        fetch_all(
            f"""
        WITH lados AS (
          {" UNION ALL ".join(tec_lados)}
        )
        SELECT t.id, t.nome, t.id_fotmob, t.nacionalidade,
               COUNT(*) AS jogos
        FROM lados l
        JOIN tecnicos t ON t.id = l.tid
        GROUP BY t.id, t.nome, t.id_fotmob, t.nacionalidade
        ORDER BY jogos DESC
        """,
            tec_params,
        )
        if tec_lados
        else []
    )
    for r in tecnicos:
        item = _serialize(r)
        item["posicao"] = "Técnico"
        item["foto"] = FOTO_PESSOA.format(id=item["id_fotmob"]) if item.get("id_fotmob") else None
        blocos["tecnico"].append(item)

    out = []
    for key, label in _ORDEM_POS:
        lista = blocos.get(key) or []
        if lista:
            out.append({"chave": key, "label": label, "itens": lista})
    return {"blocos": out}


def analise_elenco(
    clube_id: int,
    temporada: str,
    *,
    campeonato_id: int | None = None,
    mando: str | None = None,
) -> dict:
    metricas = [
        ("gols", "Gols", "SUM(COALESCE(i.gols,0))"),
        ("assistencias", "Assistências", "SUM(COALESCE(i.assistencias,0))"),
        ("faltas_cometidas", "Faltas", "SUM(COALESCE(i.faltas_cometidas,0))"),
        ("dribles_certos", "Dribles certos", "SUM(COALESCE(i.dribles_certos,0))"),
        ("desarmes", "Desarmes", "SUM(COALESCE(i.desarmes,0))"),
        ("interceptacoes", "Interceptações", "SUM(COALESCE(i.interceptacoes,0))"),
        ("passes_certos", "Passes certos", "SUM(COALESCE(i.passes_certos,0))"),
        ("chutes_certos", "Chutes certos", "SUM(COALESCE(i.chutes_certos,0))"),
        ("rating", "Nota", "AVG(i.rating)"),
    ]
    tops = []
    extra, extra_params = _sql_jogo_escopo(
        "jo", campeonato_id=campeonato_id, mando=mando, clube_id=clube_id
    )
    # descobrir colunas existentes em individual
    cols = {
        r["column_name"]
        for r in fetch_all(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'individual'
            """
        )
    }
    for chave, label, expr in metricas:
        needed = []
        if chave == "cartoes":
            needed = ["cartao_amarelo", "cartao_vermelho"]
        elif chave == "rating":
            needed = ["rating"]
        else:
            needed = [chave]
        if any(c not in cols for c in needed):
            continue
        rows = fetch_all(
            f"""
            SELECT jg.id, jg.nome, jg.foto, jf.id_externo AS id_fotmob, jg.posicao,
                   {expr} AS valor,
                   COUNT(DISTINCT i.jogo_id) AS jogos
            FROM individual i
            JOIN jogos jo ON jo.id = i.jogo_id
            JOIN jogadores jg ON jg.id = i.jogador_id
            LEFT JOIN jogadores_fontes jf ON jf.jogador_id = jg.id AND jf.fonte = 'fotmob'
            WHERE i.clube_id = %s AND jo.temporada = %s AND jo.gols_casa IS NOT NULL{extra}
            GROUP BY jg.id, jg.nome, jg.foto, jf.id_externo, jg.posicao
            HAVING {expr} IS NOT NULL
            ORDER BY valor DESC NULLS LAST, jogos DESC
            LIMIT 5
            """,
            (clube_id, temporada, *extra_params),
        )
        itens = []
        for r in rows:
            item = _serialize(r)
            if not item.get("foto") and item.get("id_fotmob"):
                item["foto"] = FOTO_PESSOA.format(id=item["id_fotmob"])
            itens.append(item)
        tops.append({"chave": chave, "label": label, "itens": itens})
    return {"tops": tops}


def clubes_comparaveis(clube_id: int, temporada: str) -> list[dict]:
    rows = fetch_all(
        """
        SELECT DISTINCT c.id, c.clube, cf.id_externo AS id_fotmob
        FROM jogos j
        JOIN clubes c ON c.id IN (j.casa_id, j.fora_id)
        LEFT JOIN clubes_fontes cf ON cf.clube_id = c.id AND cf.fonte = 'fotmob'
        WHERE j.temporada = %s AND j.gols_casa IS NOT NULL AND c.id <> %s
        ORDER BY c.clube
        """,
        (temporada, clube_id),
    )
    out = []
    for r in rows:
        item = _serialize(r)
        item["logo"] = _logo(item.get("id_fotmob"))
        out.append(item)
    return out


def comportamento_clube(
    clube_id: int,
    temporada: str,
    *,
    campeonato_id: int | None = None,
    mando: str | None = None,
) -> dict:
    filtros = ["j.temporada = %s", "j.gols_casa IS NOT NULL", "(j.casa_id = %s OR j.fora_id = %s)"]
    params: list = [temporada, clube_id, clube_id]
    if campeonato_id:
        filtros.append("j.campeonato_id = %s")
        params.append(campeonato_id)
    where = " AND ".join(filtros)
    mando_n = (mando or "todos").strip().lower()

    jogos = fetch_all(
        f"""
        SELECT j.id, j.casa_id, j.fora_id, j.gols_casa, j.gols_fora
        FROM jogos j
        WHERE {where}
        ORDER BY j.data, j.id
        """,
        params,
    )
    if mando_n in ("casa", "fora"):
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
    abriu = ampliou = abriu_venceu = abriu_empatou = abriu_perdeu = 0
    over05_ht = over05_ft = over15 = over25 = over35 = under35 = 0
    btts = goleada_apl = goleada_sof = venceu_ht = vencia_10_60 = perdia_10_60 = 0

    for j in jogos:
        eh_casa = j["casa_id"] == clube_id
        gm = int((j["gols_casa"] if eh_casa else j["gols_fora"]) or 0)
        gs = int((j["gols_fora"] if eh_casa else j["gols_casa"]) or 0)
        total = gm + gs
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
        if gm > 0 and gs > 0:
            btts += 1
        if gm - gs >= 3:
            goleada_apl += 1
        if gs - gm >= 3:
            goleada_sof += 1

        eventos = []
        for g in gols_por_jogo.get(j["id"], []):
            lado = _lado_gol(g, j["casa_id"], j["fora_id"])
            a_favor = (lado == "casa") if eh_casa else (lado == "fora")
            eventos.append((_t_gol(g), 1 if a_favor else -1))
        eventos.sort(key=lambda x: x[0])

        ht_eu, ht_eles = _score_at(eventos, 45.999)
        if ht_eu + ht_eles >= 1:
            over05_ht += 1
        if ht_eu > ht_eles:
            venceu_ht += 1

        eu60, eles60 = _score_at(eventos, 60.0)
        if eu60 == 1 and eles60 == 0:
            vencia_10_60 += 1
        if eu60 == 0 and eles60 == 1:
            perdia_10_60 += 1

        if not eventos:
            continue
        # primeiro gol
        if eventos[0][1] > 0:
            abriu += 1
            # ampliou: marcou de novo enquanto ainda ganhava
            eu = eles = 0
            ampliou_ok = False
            for _, delta in eventos:
                if delta > 0:
                    eu += 1
                    if eu >= 2 and eu > eles:
                        ampliou_ok = True
                else:
                    eles += 1
            if ampliou_ok:
                ampliou += 1
            if gm > gs:
                abriu_venceu += 1
            elif gm == gs:
                abriu_empatou += 1
            else:
                abriu_perdeu += 1

    cards = [
        {"chave": "abriu", "label": "Jogos que o clube abriu o placar", "pct": _pct(abriu, n), "n": abriu},
        {
            "chave": "ampliou",
            "label": "Jogos que o clube abriu o placar e ampliou",
            "pct": _pct(ampliou, n),
            "n": ampliou,
        },
        {
            "chave": "abriu_venceu",
            "label": "Jogos que o clube abriu o placar e venceu",
            "pct": _pct(abriu_venceu, n),
            "n": abriu_venceu,
        },
        {
            "chave": "abriu_empatou",
            "label": "Jogos que o clube abriu o placar e sofreu o empate",
            "pct": _pct(abriu_empatou, n),
            "n": abriu_empatou,
        },
        {
            "chave": "abriu_perdeu",
            "label": "Jogos que o clube abriu o placar e perdeu",
            "pct": _pct(abriu_perdeu, n),
            "n": abriu_perdeu,
        },
    ]
    barras = [
        {"chave": "over05_ht", "label": "Over 0,5HT", "pct": _pct(over05_ht, n), "n": over05_ht},
        {"chave": "over05_ft", "label": "Over 0,5FT", "pct": _pct(over05_ft, n), "n": over05_ft},
        {"chave": "over15", "label": "Over 1,5", "pct": _pct(over15, n), "n": over15},
        {"chave": "over25", "label": "Over 2,5", "pct": _pct(over25, n), "n": over25},
        {"chave": "over35", "label": "Over 3,5", "pct": _pct(over35, n), "n": over35},
        {"chave": "under35", "label": "Under 3,5", "pct": _pct(under35, n), "n": under35},
        {"chave": "btts", "label": "Ambos marcam", "pct": _pct(btts, n), "n": btts},
        {
            "chave": "goleada_apl",
            "label": "Goleadas aplicadas",
            "pct": _pct(goleada_apl, n),
            "n": goleada_apl,
        },
        {
            "chave": "goleada_sof",
            "label": "Goleadas sofridas",
            "pct": _pct(goleada_sof, n),
            "n": goleada_sof,
        },
        {"chave": "venceu_ht", "label": "Venceu no HT", "pct": _pct(venceu_ht, n), "n": venceu_ht},
        {
            "chave": "vencia_10_60",
            "label": "Vencia por 1-0 até os 60 minutos",
            "pct": _pct(vencia_10_60, n),
            "n": vencia_10_60,
        },
        {
            "chave": "perdia_10_60",
            "label": "Perdia por 1-0 até os 60 minutos",
            "pct": _pct(perdia_10_60, n),
            "n": perdia_10_60,
        },
    ]
    return {"jogos": n, "cards": cards, "barras": barras}


def jogos_clube(
    clube_id: int,
    temporada: str,
    *,
    campeonato_id: int | None = None,
    mando: str | None = None,
) -> dict:
    filtros = ["j.temporada = %s", "j.gols_casa IS NOT NULL", "(j.casa_id = %s OR j.fora_id = %s)"]
    params: list = [temporada, clube_id, clube_id]
    if campeonato_id:
        filtros.append("j.campeonato_id = %s")
        params.append(campeonato_id)
    mando_n = (mando or "todos").strip().lower()
    if mando_n == "casa":
        filtros.append("j.casa_id = %s")
        params.append(clube_id)
    elif mando_n == "fora":
        filtros.append("j.fora_id = %s")
        params.append(clube_id)
    where = " AND ".join(filtros)

    rows = fetch_all(
        f"""
        SELECT j.id, j.data, j.temporada, j.estadio,
               j.gols_casa, j.gols_fora,
               c.id AS campeonato_id, c.nome AS campeonato,
               ca.id AS casa_id, ca.clube AS casa,
               fa.id AS fora_id, fa.clube AS fora,
               cf_casa.id_externo AS casa_id_fotmob,
               cf_fora.id_externo AS fora_id_fotmob,
               a.id AS arbitro_id, a.nome AS arbitro,
               (
                 SELECT ROUND(AVG(i.rating)::numeric, 2)
                 FROM individual i
                 WHERE i.jogo_id = j.id AND i.clube_id = j.casa_id AND i.rating IS NOT NULL
               ) AS rating_casa,
               (
                 SELECT ROUND(AVG(i.rating)::numeric, 2)
                 FROM individual i
                 WHERE i.jogo_id = j.id AND i.clube_id = j.fora_id AND i.rating IS NOT NULL
               ) AS rating_fora
        FROM jogos j
        JOIN campeonatos c ON c.id = j.campeonato_id
        JOIN clubes ca ON ca.id = j.casa_id
        JOIN clubes fa ON fa.id = j.fora_id
        LEFT JOIN clubes_fontes cf_casa
          ON cf_casa.clube_id = ca.id AND cf_casa.fonte = 'fotmob'
        LEFT JOIN clubes_fontes cf_fora
          ON cf_fora.clube_id = fa.id AND cf_fora.fonte = 'fotmob'
        LEFT JOIN arbitros a ON a.id = j.arbitro_id
        WHERE {where}
        ORDER BY j.data DESC NULLS LAST, j.id DESC
        """,
        params,
    )

    # Índice de físicos Sofascore: data + nomes normalizados dos clubes
    fis_idx = _fisicos_por_data_temporada(temporada)

    linhas = []
    for r in rows:
        item = _serialize(r)
        item["casa_logo"] = _logo(item.get("casa_id_fotmob"))
        item["fora_logo"] = _logo(item.get("fora_id_fotmob"))
        fis = _fisicos_do_jogo(item, fis_idx)
        item["km_casa"] = fis.get("km_casa")
        item["km_fora"] = fis.get("km_fora")
        item["sprints_casa"] = fis.get("sprints_casa")
        item["sprints_fora"] = fis.get("sprints_fora")
        linhas.append(item)
    return {"linhas": linhas, "total": len(linhas)}


def _fisicos_por_data_temporada(temporada: str) -> dict[tuple, dict]:
    """Mapa (data, frozenset nomes-chave) → {casa|fora: {km, sprints, clube}}."""
    rows = fetch_all(
        """
        SELECT j.data, j.id AS jogo_id,
               ca.clube AS casa_nome, fa.clube AS fora_nome,
               e.mando, e.distancia_percorrida, e.sprints, cl.clube
        FROM jogos j
        JOIN clubes ca ON ca.id = j.casa_id
        JOIN clubes fa ON fa.id = j.fora_id
        JOIN estatisticas e ON e.jogo_id = j.id AND e.periodo = 'Completo'
        JOIN clubes cl ON cl.id = e.clube_id
        WHERE j.temporada = %s
          AND (e.distancia_percorrida IS NOT NULL OR e.sprints IS NOT NULL)
        ORDER BY j.data, j.id, e.mando
        """,
        (temporada,),
    )
    idx: dict[tuple, dict] = {}
    for r in rows:
        key = (
            str(r["data"]),
            frozenset(
                {
                    clube_match_key(r.get("casa_nome")),
                    clube_match_key(r.get("fora_nome")),
                }
                - {""}
            ),
        )
        slot = idx.setdefault(key, {"casa": None, "fora": None})
        lado = (r.get("mando") or "").strip()
        # Preferir o lado pelo mando; se o nome bater com casa/fora do jogo físico, ok
        payload = {
            "km": r.get("distancia_percorrida"),
            "sprints": r.get("sprints"),
            "clube": r.get("clube"),
            "clube_key": clube_match_key(r.get("clube")),
        }
        if lado == "Casa":
            slot["casa"] = payload
        elif lado == "Fora":
            slot["fora"] = payload
    return idx


def _fisicos_do_jogo(jogo: dict, fis_idx: dict[tuple, dict]) -> dict:
    """Cruza jogo FotMob com físicos Sofascore pelos nomes dos clubes (iguais/alias)."""
    key = (
        str(jogo.get("data")),
        frozenset(
            {clube_match_key(jogo.get("casa")), clube_match_key(jogo.get("fora"))} - {""}
        ),
    )
    slot = fis_idx.get(key)
    if not slot:
        return {"km_casa": None, "km_fora": None, "sprints_casa": None, "sprints_fora": None}

    casa_key = clube_match_key(jogo.get("casa"))
    fora_key = clube_match_key(jogo.get("fora"))
    fis_casa = slot.get("casa")
    fis_fora = slot.get("fora")

    def _lado_para(target_key: str, prefer):
        if prefer and prefer.get("clube_key") == target_key:
            return prefer
        for cand in (fis_casa, fis_fora):
            if cand and cand.get("clube_key") == target_key:
                return cand
        # mando Casa/Fora do jogo físico (mesma data + par de clubes)
        return prefer

    lado_casa = _lado_para(casa_key, fis_casa)
    lado_fora = _lado_para(fora_key, fis_fora)
    return {
        "km_casa": (lado_casa or {}).get("km"),
        "km_fora": (lado_fora or {}).get("km"),
        "sprints_casa": (lado_casa or {}).get("sprints"),
        "sprints_fora": (lado_fora or {}).get("sprints"),
    }


def estatisticas_clube(
    clube_id: int,
    temporada: str,
    grupo: str = "ataque",
    comparar_id: int | None = None,
    *,
    campeonato_id: int | None = None,
    mando: str | None = None,
) -> dict:
    opcoes = clubes_comparaveis(clube_id, temporada)
    grupos = GRUPOS_CLUBE
    if grupo == "minutos":
        minutos = minutos_analise(
            clube_id=clube_id,
            temporada=temporada,
            campeonato_id=campeonato_id,
            mando=mando,
        )
        minutos_cmp = None
        if comparar_id and comparar_id != clube_id:
            minutos_cmp = minutos_analise(
                clube_id=comparar_id,
                temporada=temporada,
                campeonato_id=campeonato_id,
                mando=mando,
            )
        return {
            "grupos": grupos,
            "grupo": "minutos",
            "metricas": [],
            "linhas": [],
            "minutos": minutos,
            "minutos_comparar": minutos_cmp,
            "comparar_id": comparar_id,
            "clubes_opcoes": opcoes,
        }
    if grupo == "comportamento":
        return {
            "grupos": grupos,
            "grupo": "comportamento",
            "metricas": [],
            "linhas": [],
            "comportamento": comportamento_clube(
                clube_id,
                temporada,
                campeonato_id=campeonato_id,
                mando=mando,
            ),
            "comparar_id": comparar_id,
            "clubes_opcoes": opcoes,
        }

    ids = [clube_id]
    if comparar_id and comparar_id != clube_id:
        ids.append(comparar_id)
    data = coletivas_tabela(
        temporada=temporada,
        campeonato_id=campeonato_id,
        grupo=grupo if grupo in GRUPOS_LABELS else "ataque",
        clube_ids=ids,
        page=1,
        page_size=10,
        clube_id=clube_id,
        mando=mando,
    )
    data["grupos"] = grupos
    data["comparar_id"] = comparar_id
    data["clubes_opcoes"] = opcoes
    return data


def detalhe_clube(
    clube_id: int,
    *,
    temporada: str | None = None,
    aba: str = "geral",
    comparar_id: int | None = None,
    grupo: str = "ataque",
    campeonato_id: int | None = None,
    mando: str | None = None,
) -> dict | None:
    base = clube_base(clube_id)
    if not base:
        return None
    temps = temporadas_clube(clube_id)
    if temporada not in temps:
        temporada = temps[0] if temps else None
    camps = campeonatos_clube(clube_id, temporada) if temporada else []
    if campeonato_id and not any(c["id"] == campeonato_id for c in camps):
        campeonato_id = None
    mando_n = (mando or "todos").strip().lower()
    if mando_n not in ("todos", "casa", "fora"):
        mando_n = "todos"
    out = {
        "clube": base,
        "temporada": temporada,
        "temporadas": temps,
        "aba": aba,
        "grupos": GRUPOS_CLUBE,
        "campeonatos": camps,
        "campeonato_id": campeonato_id,
        "mando": mando_n,
    }
    if not temporada:
        return out
    kw = {"campeonato_id": campeonato_id, "mando": mando_n}
    if aba == "jogos":
        out["jogos"] = jogos_clube(clube_id, temporada, **kw)
    elif aba == "geral":
        out["geral"] = geral_clube(clube_id, temporada, **kw)
    elif aba == "elenco":
        out["elenco"] = elenco_clube(clube_id, temporada, **kw)
    elif aba == "analise":
        out["analise"] = analise_elenco(clube_id, temporada, **kw)
    elif aba == "estatisticas":
        out["estatisticas"] = estatisticas_clube(
            clube_id, temporada, grupo=grupo, comparar_id=comparar_id, **kw
        )
    else:
        out["jogos"] = jogos_clube(clube_id, temporada, **kw)
        out["aba"] = "jogos"
    return out
