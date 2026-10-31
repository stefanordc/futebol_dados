"""Detalhe e edição de clube/jogador/técnico/árbitro (tabelas raiz)."""

from __future__ import annotations

from db import execute, fetch_all, fetch_one, get_conn
from queries import _serialize
from queries_stats import FOTO_PESSOA

class EntidadeEditError(Exception):
    """Erro de validação / conflito ao editar entidade."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


# Métricas da tabela individual, por aba (chave → rótulo). AVG para rating; resto SUM.
GRUPOS_JOGADOR = {
    "resumo": [
        ("rating", "Nota"),
        ("gols", "Gols"),
        ("assistencias", "Assistências"),
        ("xg", "xG"),
        ("xa", "xA"),
        ("chutes_total", "Chutes"),
        ("chutes_certos", "Chutes no gol"),
        ("passes_certos", "Passes certos"),
        ("desarmes", "Desarmes"),
        ("interceptacoes", "Interceptações"),
        ("dribles_certos", "Dribles certos"),
        ("faltas_cometidas", "Faltas cometidas"),
    ],
    "ataque": [
        ("gols", "Gols"),
        ("assistencias", "Assistências"),
        ("xg", "xG"),
        ("xgot", "xGOT"),
        ("xa", "xA"),
        ("xg_xa", "xG + xA"),
        ("xg_sem_penalti", "xG sem pênalti"),
        ("chutes_total", "Chutes"),
        ("chutes_certos", "Chutes no gol"),
        ("chutes_fora", "Chutes para fora"),
        ("chutes_bloqueados", "Chutes bloqueados"),
        ("chutes_trave", "Chutes na trave"),
        ("precisao_chutes", "Precisão de chutes (%)"),
        ("grandes_chances_criadas", "Grandes chances criadas"),
        ("grandes_chances_perdidas", "Grandes chances perdidas"),
        ("toques_area_adversaria", "Toques na área adversária"),
        ("penaltis_ganhos", "Pênaltis ganhos"),
        ("penaltis_perdidos", "Pênaltis perdidos"),
        ("gols_contra", "Gols contra"),
        ("impedimentos", "Impedimentos"),
    ],
    "passes": [
        ("toques_bolas", "Toques"),
        ("passes_certos", "Passes certos"),
        ("chances_criadas", "Chances criadas"),
        ("passes_terco_final", "Passes no terço final"),
        ("passes_rompendo_linhas", "Passes rompendo linhas"),
        ("cruzamentos", "Cruzamentos"),
        ("cruzamentos_certos", "Cruzamentos certos"),
        ("passes_longos", "Passes longos"),
        ("passes_longos_certos", "Passes longos certos"),
        ("escanteios", "Escanteios"),
        ("laterais", "Laterais"),
        ("perdas_posse_bola", "Perdas de posse"),
    ],
    "defesa": [
        ("acoes_defensivas", "Ações defensivas"),
        ("desarmes", "Desarmes"),
        ("bolas_roubadas", "Bolas roubadas"),
        ("bloqueios", "Bloqueios"),
        ("bolas_afastadas", "Bolas afastadas"),
        ("bolas_afastadas_cabeca", "Bolas afastadas de cabeça"),
        ("interceptacoes", "Interceptações"),
        ("recuperacao_posse_bola", "Recuperações de posse"),
        ("dribles_sofridos", "Dribles sofridos"),
        ("cortes_em_cima_da_linha", "Cortes em cima da linha"),
        ("desarme_ultimo_homem", "Desarme de último homem"),
        ("erros_levaram_gol", "Erros que levaram a gol"),
    ],
    "duelos": [
        ("dribles", "Dribles"),
        ("dribles_certos", "Dribles certos"),
        ("disputas_chao", "Disputas no chão"),
        ("disputas_chao_ganhas", "Disputas no chão ganhas"),
        ("disputas_aereas", "Disputas aéreas"),
        ("disputas_aereas_ganhas", "Disputas aéreas ganhas"),
        ("disputas_ganhas", "Disputas ganhas"),
        ("disputas_perdidas", "Disputas perdidas"),
        ("faltas_sofridas", "Faltas sofridas"),
        ("faltas_cometidas", "Faltas cometidas"),
    ],
    "goleiro": [
        ("defesas", "Defesas"),
        ("defesas_dentro_area", "Defesas dentro da área"),
        ("defesas_com_mergulho", "Defesas com mergulho"),
        ("gols_sofridos", "Gols sofridos"),
        ("xgot_sofrido", "xGOT sofrido"),
        ("gols_evitados", "Gols evitados"),
        ("bolas_altas_seguradas", "Bolas altas seguradas"),
        ("socos_na_bola", "Socos na bola"),
        ("acoes_como_libero", "Ações como líbero"),
        ("penaltis_defendidos", "Pênaltis defendidos"),
        ("penaltis_concedidos", "Pênaltis concedidos"),
    ],
}

GRUPOS_JOGADOR_LABELS = {
    "resumo": "Resumo",
    "ataque": "Ataque",
    "passes": "Posse e passes",
    "defesa": "Defesa",
    "duelos": "Duelos",
    "goleiro": "Goleiro",
}


def _cols_individual() -> set[str]:
    rows = fetch_all(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'individual'
        """
    )
    return {r["column_name"] for r in rows}


def estatisticas_jogador(jogador_id: int, temporada: str) -> dict:
    """Agrega métricas da temporada do jogador, organizadas por abas."""
    cols = _cols_individual()
    agg_parts = ["COUNT(DISTINCT i.jogo_id) AS jogos", "SUM(COALESCE(i.minutos,0)) AS minutos"]
    used: list[tuple[str, str]] = []
    for pares in GRUPOS_JOGADOR.values():
        for chave, label in pares:
            if chave not in cols or chave in {c for c, _ in used}:
                continue
            if chave == "rating":
                agg_parts.append("ROUND(AVG(i.rating)::numeric, 2) AS rating")
            elif chave == "precisao_chutes":
                # média da precisão já em %
                agg_parts.append(
                    "ROUND(AVG(i.precisao_chutes)::numeric, 1) AS precisao_chutes"
                )
            else:
                agg_parts.append(f"SUM(COALESCE(i.{chave},0)) AS {chave}")
            used.append((chave, label))

    row = fetch_one(
        f"""
        SELECT {", ".join(agg_parts)}
        FROM individual i
        JOIN jogos jo ON jo.id = i.jogo_id
        WHERE i.jogador_id = %s AND jo.temporada = %s AND jo.gols_casa IS NOT NULL
        """,
        (jogador_id, temporada),
    )
    dados = _serialize(row) or {}
    jogos = float(dados.get("jogos") or 0) or 0.0

    grupos_out: dict[str, list[dict]] = {}
    for gkey, pares in GRUPOS_JOGADOR.items():
        itens = []
        for chave, label in pares:
            if chave not in cols:
                continue
            soma = dados.get(chave)
            if soma is None:
                continue
            # esconder goleiro vazio se tudo zero
            media = None
            if chave == "rating" or chave == "precisao_chutes":
                media = soma
            elif jogos:
                media = round(float(soma) / jogos, 2)
            itens.append(
                {
                    "chave": chave,
                    "label": label,
                    "soma": soma,
                    "media": media,
                }
            )
        # omitir aba goleiro se sem defesas relevantes
        if gkey == "goleiro":
            if not any(
                (it["soma"] or 0) not in (0, 0.0, None)
                for it in itens
                if it["chave"] in ("defesas", "gols_sofridos", "xgot_sofrido", "penaltis_defendidos")
            ):
                continue
        if itens:
            grupos_out[gkey] = itens

    return {
        "jogos": dados.get("jogos") or 0,
        "minutos": dados.get("minutos") or 0,
        "grupos": {k: GRUPOS_JOGADOR_LABELS[k] for k in grupos_out},
        "metricas": grupos_out,
    }

_TABELAS = {
    "clube": ("clubes", "clube", None),
    "jogador": ("jogadores", "nome", "foto"),
    "tecnico": ("tecnicos", "nome", None),
    "arbitro": ("arbitros", "nome", "foto"),
}


def _mesclar_clube_duplicado(manter_id: int, absorver_id: int) -> None:
    """Reaponta FKs do clube absorvido para o mantido e apaga o duplicado."""
    if manter_id == absorver_id:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            for sql in (
                "UPDATE jogos SET casa_id = %s WHERE casa_id = %s",
                "UPDATE jogos SET fora_id = %s WHERE fora_id = %s",
                "UPDATE estatisticas SET clube_id = %s WHERE clube_id = %s",
                "UPDATE finalizacoes SET clube_id = %s WHERE clube_id = %s",
                "UPDATE individual SET clube_id = %s WHERE clube_id = %s",
                "UPDATE clubes_fontes SET clube_id = %s WHERE clube_id = %s",
            ):
                cur.execute(sql, (manter_id, absorver_id))
            cur.execute("DELETE FROM clubes WHERE id = %s", (absorver_id,))
        conn.commit()


def _clube_mesmo_nome(entidade_id: int, nome: str) -> dict | None:
    return fetch_one(
        """
        SELECT c2.id, c2.clube
        FROM clubes c
        JOIN clubes c2
          ON c2.id <> c.id
         AND lower(btrim(c2.clube)) = lower(btrim(%s))
         AND COALESCE(c2.pais_id, -1) = COALESCE(c.pais_id, -1)
        WHERE c.id = %s
        LIMIT 1
        """,
        (nome, entidade_id),
    )


def atualizar_entidade(
    tipo: str,
    entidade_id: int,
    *,
    nome: str | None = None,
    foto: str | None = None,
) -> bool:
    meta = _TABELAS.get(tipo)
    if not meta:
        return False
    tabela, col_nome, col_foto = meta
    sets = []
    params: list = []
    if nome is not None:
        nome = nome.strip()
        if not nome:
            return False
        # Clube: se o nome já existe no mesmo país, mescla o duplicado
        if tipo == "clube":
            dup = _clube_mesmo_nome(entidade_id, nome)
            if dup:
                _mesclar_clube_duplicado(entidade_id, int(dup["id"]))
        sets.append(f"{col_nome} = %s")
        params.append(nome)
    if foto is not None and col_foto:
        sets.append(f"{col_foto} = %s")
        params.append(foto.strip() or None)
    if not sets:
        return False
    params.append(entidade_id)
    try:
        n = execute(
            f"UPDATE {tabela} SET {', '.join(sets)}, atualizado_em = now() WHERE id = %s",
            params,
        )
    except Exception as e:
        # UniqueViolation e afins
        msg = str(getattr(e, "diag", None).message_primary if getattr(e, "diag", None) else e)
        if "unique" in msg.lower() or "duplicate" in msg.lower():
            raise EntidadeEditError(
                "Já existe outro registro com este nome. Escolha um nome diferente.",
                status=409,
            ) from e
        raise
    return n > 0


def detalhe_jogador(jogador_id: int, temporada: str | None = None) -> dict | None:
    base = fetch_one(
        """
        SELECT j.id, j.nome, j.posicao, j.nacionalidade, j.foto,
               jf.id_externo AS id_fotmob
        FROM jogadores j
        LEFT JOIN jogadores_fontes jf ON jf.jogador_id = j.id AND jf.fonte = 'fotmob'
        WHERE j.id = %s
        """,
        (jogador_id,),
    )
    if not base:
        return None
    item = _serialize(base)
    if not item.get("foto") and item.get("id_fotmob"):
        item["foto"] = FOTO_PESSOA.format(id=item["id_fotmob"])

    temps = fetch_all(
        """
        SELECT DISTINCT jo.temporada
        FROM individual i
        JOIN jogos jo ON jo.id = i.jogo_id
        WHERE i.jogador_id = %s AND jo.temporada IS NOT NULL
        ORDER BY jo.temporada DESC
        """,
        (jogador_id,),
    )
    temporadas = [r["temporada"] for r in temps]
    if temporada not in temporadas:
        temporada = temporadas[0] if temporadas else None

    linhas = []
    if temporada:
        linhas = fetch_all(
            """
            SELECT c.id AS campeonato_id, c.nome AS campeonato,
                   cl.id AS clube_id, cl.clube,
                   COUNT(DISTINCT i.jogo_id) AS jogos,
                   SUM(COALESCE(i.minutos,0)) AS minutos,
                   SUM(COALESCE(i.gols,0)) AS gols,
                   SUM(COALESCE(i.assistencias,0)) AS assistencias,
                   ROUND(AVG(i.rating)::numeric, 2) AS rating
            FROM individual i
            JOIN jogos jo ON jo.id = i.jogo_id
            JOIN campeonatos c ON c.id = jo.campeonato_id
            JOIN clubes cl ON cl.id = i.clube_id
            WHERE i.jogador_id = %s AND jo.temporada = %s AND jo.gols_casa IS NOT NULL
            GROUP BY c.id, c.nome, cl.id, cl.clube
            ORDER BY jogos DESC
            """,
            (jogador_id, temporada),
        )
    stats = (
        estatisticas_jogador(jogador_id, temporada) if temporada else {"jogos": 0, "minutos": 0, "grupos": {}, "metricas": {}}
    )
    return {
        "tipo": "jogador",
        "entidade": item,
        "temporada": temporada,
        "temporadas": temporadas,
        "linhas": [_serialize(r) for r in linhas],
        "estatisticas": stats,
    }


def detalhe_tecnico(tecnico_id: int, temporada: str | None = None) -> dict | None:
    base = fetch_one(
        "SELECT id, nome, nacionalidade, id_fotmob FROM tecnicos WHERE id = %s",
        (tecnico_id,),
    )
    if not base:
        return None
    item = _serialize(base)
    item["foto"] = FOTO_PESSOA.format(id=item["id_fotmob"]) if item.get("id_fotmob") else None

    temps = fetch_all(
        """
        SELECT DISTINCT temporada FROM jogos
        WHERE (tecnico_casa_id = %s OR tecnico_fora_id = %s) AND temporada IS NOT NULL
        ORDER BY temporada DESC
        """,
        (tecnico_id, tecnico_id),
    )
    temporadas = [r["temporada"] for r in temps]
    if temporada not in temporadas:
        temporada = temporadas[0] if temporadas else None

    linhas = []
    if temporada:
        rows = fetch_all(
            """
            WITH lados AS (
              SELECT campeonato_id, casa_id AS clube_id,
                     CASE WHEN gols_casa > gols_fora THEN 1 ELSE 0 END AS v,
                     CASE WHEN gols_casa = gols_fora THEN 1 ELSE 0 END AS e,
                     CASE WHEN gols_casa < gols_fora THEN 1 ELSE 0 END AS d
              FROM jogos
              WHERE temporada = %s AND gols_casa IS NOT NULL AND tecnico_casa_id = %s
              UNION ALL
              SELECT campeonato_id, fora_id,
                     CASE WHEN gols_fora > gols_casa THEN 1 ELSE 0 END,
                     CASE WHEN gols_fora = gols_casa THEN 1 ELSE 0 END,
                     CASE WHEN gols_fora < gols_casa THEN 1 ELSE 0 END
              FROM jogos
              WHERE temporada = %s AND gols_casa IS NOT NULL AND tecnico_fora_id = %s
            )
            SELECT c.id AS campeonato_id, c.nome AS campeonato,
                   cl.id AS clube_id, cl.clube,
                   COUNT(*) AS jogos, SUM(v) AS v, SUM(e) AS e, SUM(d) AS d,
                   SUM(v)*3 + SUM(e) AS pts
            FROM lados l
            JOIN campeonatos c ON c.id = l.campeonato_id
            JOIN clubes cl ON cl.id = l.clube_id
            GROUP BY c.id, c.nome, cl.id, cl.clube
            ORDER BY pts DESC
            """,
            (temporada, tecnico_id, temporada, tecnico_id),
        )
        linhas = [_serialize(r) for r in rows]
    return {
        "tipo": "tecnico",
        "entidade": item,
        "temporada": temporada,
        "temporadas": temporadas,
        "linhas": linhas,
    }


def detalhe_arbitro(arbitro_id: int, temporada: str | None = None) -> dict | None:
    base = fetch_one(
        "SELECT id, nome, nacionalidade, id_fotmob, foto FROM arbitros WHERE id = %s",
        (arbitro_id,),
    )
    if not base:
        return None
    item = _serialize(base)
    if not item.get("foto") and item.get("id_fotmob"):
        item["foto"] = FOTO_PESSOA.format(id=item["id_fotmob"])

    temps = fetch_all(
        """
        SELECT DISTINCT temporada FROM jogos
        WHERE arbitro_id = %s AND temporada IS NOT NULL
        ORDER BY temporada DESC
        """,
        (arbitro_id,),
    )
    temporadas = [r["temporada"] for r in temps]
    if temporada not in temporadas:
        temporada = temporadas[0] if temporadas else None

    linhas = []
    if temporada:
        rows = fetch_all(
            """
            SELECT c.id AS campeonato_id, c.nome AS campeonato,
                   COUNT(*) AS jogos,
                   SUM(COALESCE(j.gols_casa,0) + COALESCE(j.gols_fora,0)) AS gols
            FROM jogos j
            JOIN campeonatos c ON c.id = j.campeonato_id
            WHERE j.arbitro_id = %s AND j.temporada = %s AND j.gols_casa IS NOT NULL
            GROUP BY c.id, c.nome
            ORDER BY jogos DESC
            """,
            (arbitro_id, temporada),
        )
        linhas = [_serialize(r) for r in rows]
    return {
        "tipo": "arbitro",
        "entidade": item,
        "temporada": temporada,
        "temporadas": temporadas,
        "linhas": linhas,
    }
