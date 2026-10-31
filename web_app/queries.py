"""Consultas usadas pela API do web app."""

from __future__ import annotations

import unicodedata
from decimal import Decimal

from db import fetch_all, fetch_one

LOGO_TIME = "https://images.fotmob.com/image_resources/logo/teamlogo/{id}.png"
LOGO_LIGA = "https://images.fotmob.com/image_resources/logo/leaguelogo/{id}.png"


def _num(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (int, float)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def _serialize(row: dict | None) -> dict | None:
    if not row:
        return None
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = _num(v) if isinstance(v, Decimal) else v
    return out


def listar_ligas() -> list[dict]:
    rows = fetch_all(
        """
        SELECT c.id, c.nome, c.logo, c.id_fotmob, c.id_sofascore,
               p.nome AS pais,
               COUNT(j.id) AS total_jogos
        FROM campeonatos c
        LEFT JOIN paises p ON p.id = c.pais_id
        LEFT JOIN jogos j ON j.campeonato_id = c.id AND j.gols_casa IS NOT NULL
        GROUP BY c.id, c.nome, c.logo, c.id_fotmob, c.id_sofascore, p.nome
        HAVING COUNT(j.id) > 0
        ORDER BY total_jogos DESC, c.nome
        """
    )
    result = []
    for r in rows:
        item = _serialize(r)
        if not item.get("logo") and item.get("id_fotmob"):
            item["logo"] = LOGO_LIGA.format(id=item["id_fotmob"])
        result.append(item)
    return result


def ultimos_jogos(limite: int = 200, campeonato_id: int | None = None) -> list[dict]:
    """Só jogos da última rodada (maior número) da temporada mais recente de cada campeonato."""
    params: list = []
    filtro_camp = ""
    if campeonato_id:
        filtro_camp = "AND j.campeonato_id = %s"
        params.append(campeonato_id)
    params.append(limite)
    rows = fetch_all(
        f"""
        WITH base AS (
          SELECT
            j.id, j.data, j.temporada, j.rodada, j.gols_casa, j.gols_fora,
            j.criado_em, j.estadio, j.id_fotmob, j.id_sofascore,
            j.campeonato_id, j.casa_id, j.fora_id,
            NULLIF(regexp_replace(COALESCE(j.rodada, ''), '[^0-9]', '', 'g'), '')::int AS n_rodada
          FROM jogos j
          WHERE j.gols_casa IS NOT NULL
            {filtro_camp}
        ),
        ultima_temporada AS (
          SELECT DISTINCT ON (campeonato_id)
            campeonato_id, temporada
          FROM base
          ORDER BY campeonato_id, data DESC NULLS LAST, id DESC
        ),
        max_rodada AS (
          SELECT b.campeonato_id, b.temporada, MAX(b.n_rodada) AS max_n
          FROM base b
          JOIN ultima_temporada u
            ON u.campeonato_id = b.campeonato_id
           AND u.temporada IS NOT DISTINCT FROM b.temporada
          WHERE b.n_rodada IS NOT NULL
          GROUP BY b.campeonato_id, b.temporada
        )
        SELECT
          b.id, b.data, b.temporada, b.rodada, b.gols_casa, b.gols_fora,
          b.criado_em, b.estadio, b.id_fotmob, b.id_sofascore,
          c.id AS campeonato_id, c.nome AS campeonato, c.logo AS campeonato_logo,
          c.id_fotmob AS campeonato_id_fotmob, p.nome AS pais,
          ca.id AS casa_id, ca.clube AS casa,
          fa.id AS fora_id, fa.clube AS fora,
          cf_casa.id_externo AS casa_id_fotmob,
          cf_fora.id_externo AS fora_id_fotmob
        FROM base b
        JOIN max_rodada m
          ON m.campeonato_id = b.campeonato_id
         AND m.temporada IS NOT DISTINCT FROM b.temporada
         AND b.n_rodada = m.max_n
        JOIN campeonatos c ON c.id = b.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        JOIN clubes ca ON ca.id = b.casa_id
        JOIN clubes fa ON fa.id = b.fora_id
        LEFT JOIN clubes_fontes cf_casa
          ON cf_casa.clube_id = ca.id AND cf_casa.fonte = 'fotmob'
        LEFT JOIN clubes_fontes cf_fora
          ON cf_fora.clube_id = fa.id AND cf_fora.fonte = 'fotmob'
        ORDER BY b.data DESC NULLS LAST, b.id DESC
        LIMIT %s
        """,
        params,
    )
    out = []
    for r in rows:
        item = _serialize(r)
        item["casa_logo"] = (
            LOGO_TIME.format(id=item["casa_id_fotmob"]) if item.get("casa_id_fotmob") else None
        )
        item["fora_logo"] = (
            LOGO_TIME.format(id=item["fora_id_fotmob"]) if item.get("fora_id_fotmob") else None
        )
        if not item.get("campeonato_logo") and item.get("campeonato_id_fotmob"):
            item["campeonato_logo"] = LOGO_LIGA.format(id=item["campeonato_id_fotmob"])
        out.append(item)
    return out


def detalhe_jogo(jogo_id: int) -> dict | None:
    jogo = fetch_one(
        """
        SELECT
          j.id, j.data, j.temporada, j.rodada, j.gols_casa, j.gols_fora,
          j.estadio, j.capacidade, j.publico, j.id_fotmob, j.id_sofascore,
          j.criado_em,
          c.id AS campeonato_id, c.nome AS campeonato, c.logo AS campeonato_logo,
          c.id_fotmob AS campeonato_id_fotmob, p.nome AS pais,
          ca.id AS casa_id, ca.clube AS casa,
          fa.id AS fora_id, fa.clube AS fora,
          cf_casa.id_externo AS casa_id_fotmob,
          cf_fora.id_externo AS fora_id_fotmob,
          j.tecnico_casa_id, j.tecnico_fora_id,
          tc.nome AS tecnico_casa, tf.nome AS tecnico_fora,
          a.id AS arbitro_id, a.nome AS arbitro, a.foto AS arbitro_foto,
          pa.nome AS arbitro_pais
        FROM jogos j
        JOIN campeonatos c ON c.id = j.campeonato_id
        LEFT JOIN paises p ON p.id = c.pais_id
        JOIN clubes ca ON ca.id = j.casa_id
        JOIN clubes fa ON fa.id = j.fora_id
        LEFT JOIN clubes_fontes cf_casa
          ON cf_casa.clube_id = ca.id AND cf_casa.fonte = 'fotmob'
        LEFT JOIN clubes_fontes cf_fora
          ON cf_fora.clube_id = fa.id AND cf_fora.fonte = 'fotmob'
        LEFT JOIN tecnicos tc ON tc.id = j.tecnico_casa_id
        LEFT JOIN tecnicos tf ON tf.id = j.tecnico_fora_id
        LEFT JOIN arbitros a ON a.id = j.arbitro_id
        LEFT JOIN paises pa ON pa.id = a.pais_id
        WHERE j.id = %s
        """,
        (jogo_id,),
    )
    if not jogo:
        return None
    item = _serialize(jogo)
    item["casa_logo"] = (
        LOGO_TIME.format(id=item["casa_id_fotmob"]) if item.get("casa_id_fotmob") else None
    )
    item["fora_logo"] = (
        LOGO_TIME.format(id=item["fora_id_fotmob"]) if item.get("fora_id_fotmob") else None
    )
    if not item.get("campeonato_logo") and item.get("campeonato_id_fotmob"):
        item["campeonato_logo"] = LOGO_LIGA.format(id=item["campeonato_id_fotmob"])

    item["estatisticas"] = estatisticas_jogo(jogo_id)
    item["finalizacoes"] = finalizacoes_jogo(jogo_id)
    item["gols"] = gols_jogo(jogo_id)
    item["escalacao"] = escalacao_jogo(jogo_id)
    item["dados_fisicos"] = dados_fisicos_lookup(item)
    item["odds"] = odds_jogo(jogo_id)
    item["arbitro_stats"] = arbitro_resumo(item.get("arbitro_id"), item.get("campeonato_id"))
    return item


def estatisticas_jogo(jogo_id: int) -> dict:
    rows = fetch_all(
        """
        SELECT e.*, cl.clube
        FROM estatisticas e
        JOIN clubes cl ON cl.id = e.clube_id
        WHERE e.jogo_id = %s
        ORDER BY e.periodo, e.mando
        """,
        (jogo_id,),
    )
    completo = {"Casa": None, "Fora": None}
    por_periodo = []
    for r in rows:
        item = _serialize(r)
        if item.get("periodo") == "Completo":
            mando = item.get("mando") or ""
            if mando in completo:
                completo[mando] = item
        por_periodo.append(item)
    return {"completo": completo, "todos": por_periodo}


def finalizacoes_jogo(jogo_id: int) -> list[dict]:
    rows = fetch_all(
        """
        SELECT f.*,
               j.nome AS jogador, j.foto AS jogador_foto,
               g.nome AS goleiro,
               cl.clube
        FROM finalizacoes f
        LEFT JOIN jogadores j ON j.id = f.jogador_id
        LEFT JOIN jogadores g ON g.id = f.goleiro_id
        JOIN clubes cl ON cl.id = f.clube_id
        WHERE f.jogo_id = %s
        ORDER BY f.minuto NULLS LAST, f.minuto_adicional NULLS LAST, f.id
        """,
        (jogo_id,),
    )
    return [_serialize(r) for r in rows]


def gols_jogo(jogo_id: int) -> list[dict]:
    """Gols da partida (finalizações tipo Gol), com placar parcial acumulado."""
    rows = fetch_all(
        """
        SELECT f.id, f.mando, f.minuto, f.minuto_adicional, f.foi_gol_contra,
               f.xg, f.tipo_finalizacao, f.situacao_jogada,
               f.jogador_id, f.clube_id,
               j.nome AS jogador, j.foto AS jogador_foto,
               cl.clube
        FROM finalizacoes f
        LEFT JOIN jogadores j ON j.id = f.jogador_id
        JOIN clubes cl ON cl.id = f.clube_id
        WHERE f.jogo_id = %s
          AND lower(f.tipo_evento) LIKE '%%gol%%'
        ORDER BY COALESCE(f.minuto, 0), COALESCE(f.minuto_adicional, 0), f.id
        """,
        (jogo_id,),
    )
    gols = []
    placar_casa = placar_fora = 0
    for r in rows:
        item = _serialize(r)
        contra = bool(item.get("foi_gol_contra"))
        mando = item.get("mando")
        # Gol contra: conta para o adversário
        if (mando == "Casa" and not contra) or (mando == "Fora" and contra):
            placar_casa += 1
        else:
            placar_fora += 1
        item["placar_casa"] = placar_casa
        item["placar_fora"] = placar_fora
        gols.append(item)
    return gols


def _norm_nome(nome: str | None) -> str:
    if not nome:
        return ""
    return " ".join(str(nome).casefold().split())


def _norm_clube_key(nome: str | None) -> str:
    """Normaliza nome de clube para cruzar FotMob ↔ Sofascore (acentos/espaços)."""
    if not nome:
        return ""
    s = unicodedata.normalize("NFKD", str(nome))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.casefold().replace("-", " ").replace(".", " ")
    return " ".join(s.split())


_CLUBE_ALIAS_PARES = (
    ("athletic bilbao", "athletic club"),
    ("atletico madrid", "atletico de madrid"),
    ("la coruna", "deportivo a coruna", "deportivo la coruna"),
    ("alaves", "deportivo alaves"),
    ("betis", "real betis"),
    ("real racing", "racing santander", "racing de santander"),
    ("malaga",),
)

_CLUBE_ALIAS_MAP: dict[str, str] = {}
for _grupo in _CLUBE_ALIAS_PARES:
    _canon = _grupo[0]
    for _nome in _grupo:
        _CLUBE_ALIAS_MAP[_nome] = _canon


def clube_match_key(nome: str | None) -> str:
    key = _norm_clube_key(nome)
    return _CLUBE_ALIAS_MAP.get(key, key)


def _clubes_do_jogo_batem(casa_a: str | None, fora_a: str | None, casa_b: str | None, fora_b: str | None) -> bool:
    ka, kb = {clube_match_key(casa_a), clube_match_key(fora_a)}, {clube_match_key(casa_b), clube_match_key(fora_b)}
    ka.discard("")
    kb.discard("")
    return bool(ka) and ka == kb


def dados_fisicos_lookup(jogo: dict) -> dict:
    """Busca KM/sprints por data + campeonato + (casa OU fora).

    Os dados físicos costumam vir do Sofascore em outro jogo_id; por isso a
    busca não exige o mesmo id interno — só o cruzamento dos clubes/data.
    """
    data = jogo.get("data")
    casa = jogo.get("casa")
    fora = jogo.get("fora")
    if not data or (not casa and not fora):
        return {
            "encontrado": False,
            "motivo": "Jogo sem data ou clubes para cruzar dados físicos.",
            "casa": None,
            "fora": None,
        }

    # 1) Mesmo jogo_id (já gravado junto)
    direto = fetch_all(
        """
        SELECT e.mando, e.distancia_percorrida, e.sprints, cl.clube, e.jogo_id
        FROM estatisticas e
        JOIN clubes cl ON cl.id = e.clube_id
        WHERE e.jogo_id = %s
          AND e.periodo = 'Completo'
          AND (e.distancia_percorrida IS NOT NULL OR e.sprints IS NOT NULL)
        """,
        (jogo["id"],),
    )
    if len(direto) >= 1:
        return _montar_fisicos(direto, origem="mesmo_jogo")

    # 2) Mesma data com físicos; cruza clubes por nome normalizado (FotMob ↔ Sofascore)
    candidatos = fetch_all(
        """
        SELECT e.mando, e.distancia_percorrida, e.sprints, cl.clube, e.jogo_id,
               ca.clube AS casa_nome, fa.clube AS fora_nome, c.nome AS campeonato
        FROM jogos j
        JOIN campeonatos c ON c.id = j.campeonato_id
        JOIN clubes ca ON ca.id = j.casa_id
        JOIN clubes fa ON fa.id = j.fora_id
        JOIN estatisticas e ON e.jogo_id = j.id AND e.periodo = 'Completo'
        JOIN clubes cl ON cl.id = e.clube_id
        WHERE j.data = %s
          AND j.id <> %s
          AND (e.distancia_percorrida IS NOT NULL OR e.sprints IS NOT NULL)
        ORDER BY e.jogo_id, e.mando
        """,
        (data, jogo["id"]),
    )
    rows = [
        r
        for r in candidatos
        if _clubes_do_jogo_batem(casa, fora, r.get("casa_nome"), r.get("fora_nome"))
    ]

    if not rows:
        return {
            "encontrado": False,
            "motivo": (
                "Dados físicos não encontrados para esta data/campeonato/clubes. "
                "Provavelmente os clubes da casa e de fora ainda não estão sincronizados "
                "entre FotMob e Sofascore."
            ),
            "casa": None,
            "fora": None,
        }
    return _montar_fisicos(rows, origem="cruzamento")


def _montar_fisicos(rows: list[dict], origem: str) -> dict:
    casa = fora = None
    for r in rows:
        item = _serialize(r)
        if item.get("mando") == "Casa":
            casa = item
        elif item.get("mando") == "Fora":
            fora = item
    return {
        "encontrado": True,
        "origem": origem,
        "jogo_id_fonte": (rows[0].get("jogo_id") if rows else None),
        "casa": casa,
        "fora": fora,
    }


def escalacao_jogo(jogo_id: int) -> dict:
    rows = fetch_all(
        """
        SELECT i.*,
               j.nome, j.posicao, j.foto, j.nacionalidade,
               cl.clube
        FROM individual i
        JOIN jogadores j ON j.id = i.jogador_id
        JOIN clubes cl ON cl.id = i.clube_id
        WHERE i.jogo_id = %s
        ORDER BY i.mando, COALESCE(i.minutos, 0) DESC, j.nome
        """,
        (jogo_id,),
    )
    casa, fora = [], []
    for r in rows:
        item = _serialize(r)
        item["linha"] = _linha_posicao(item.get("posicao"))
        item["slot"] = _slot_posicao(item.get("posicao"))
        (casa if item.get("mando") == "Casa" else fora).append(item)

    return {
        "casa": _montar_formacao(casa),
        "fora": _montar_formacao(fora),
    }


def _linha_posicao(posicao: str | None) -> int:
    """0=GK, 1=DEF, 2=MID, 3=FWD."""
    p = (posicao or "").casefold()
    if "goleiro" in p:
        return 0
    if any(x in p for x in ("zagueiro", "lateral", "defensor", "ala-")):
        return 1
    if any(x in p for x in ("volante", "meio", "meia")):
        return 2
    if any(x in p for x in ("ponta", "atacante", "centroavante", "avançado", "avançado")):
        return 3
    return 2


def _slot_posicao(posicao: str | None) -> float:
    """Ordem horizontal aproximada (-1 esquerda … 1 direita)."""
    p = (posicao or "").casefold()
    if "esquerd" in p or "esquerda" in p:
        return -1.0
    if "direit" in p:
        return 1.0
    if "goleiro" in p or "zagueiro" in p or "volante" in p or "central" in p or "centro" in p:
        return 0.0
    if "ponta-esquerda" in p or "meia-esquerda" in p or "ala-esquerdo" in p:
        return -1.0
    if "ponta-direita" in p or "meia-direita" in p or "ala-direito" in p:
        return 1.0
    return 0.0


def _montar_formacao(jogadores: list[dict]) -> dict:
    """Separa titulares (top 11 por minutos) e banco; posiciona no campo."""
    ordenados = sorted(jogadores, key=lambda j: (-(j.get("minutos") or 0), -(j.get("rating") or 0)))
    titulares = ordenados[:11]
    reservas = ordenados[11:]
    # melhor em campo
    motm = max(jogadores, key=lambda j: j.get("rating") or 0, default=None)
    if motm:
        for j in titulares:
            j["motm"] = j.get("jogador_id") == motm.get("jogador_id") or j.get("id") == motm.get("id")

    # Substituições: saiu (<90' entre titulares) / entrou (reservas com minutos)
    for j in titulares:
        mins = j.get("minutos")
        j["saiu"] = mins is not None and float(mins) < 90
        j["entrou"] = False
    for j in reservas:
        mins = j.get("minutos")
        j["entrou"] = mins is not None and float(mins) > 0
        j["saiu"] = False

    por_linha: dict[int, list] = {0: [], 1: [], 2: [], 3: []}
    for j in titulares:
        por_linha[j["linha"]].append(j)
    for linha, lista in por_linha.items():
        lista.sort(key=lambda j: (j.get("slot") or 0, j.get("nome") or ""))
        n = len(lista)
        for i, j in enumerate(lista):
            # posição no campo (0–100). Casa ataca para cima na metade esquerda da UI.
            if n == 1:
                x = 50.0
            else:
                x = 12.0 + (76.0 * i / (n - 1))
            y_base = {0: 92, 1: 72, 2: 48, 3: 24}[linha]
            j["x"] = round(x, 1)
            j["y"] = y_base

    return {"titulares": titulares, "reservas": reservas, "motm_id": (motm or {}).get("jogador_id")}


def odds_jogo(jogo_id: int) -> dict | None:
    row = fetch_one(
        """
        SELECT odd_casa, odd_empate, odd_fora
        FROM odds_fotmob
        WHERE jogo_id = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (jogo_id,),
    )
    return _serialize(row)


def arbitro_resumo(arbitro_id: int | None, campeonato_id: int | None) -> dict | None:
    if not arbitro_id:
        return None
    row = fetch_one(
        """
        SELECT
          COUNT(DISTINCT j.id) AS jogos,
          ROUND(AVG(e.cartao_amarelo)::numeric, 1) AS amarelos_por_jogo,
          ROUND(AVG(e.faltas_cometidas)::numeric, 1) AS faltas_por_jogo
        FROM jogos j
        JOIN estatisticas e ON e.jogo_id = j.id AND e.periodo = 'Completo'
        WHERE j.arbitro_id = %s
          AND (%s::int IS NULL OR j.campeonato_id = %s)
        """,
        (arbitro_id, campeonato_id, campeonato_id),
    )
    return _serialize(row)
