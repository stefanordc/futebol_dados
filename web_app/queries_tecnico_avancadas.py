"""Estatísticas avançadas de técnicos, agregadas apenas nos jogos sob seu comando.

Somente SELECT. Não modifica as consultas/rotas existentes.
"""
from __future__ import annotations

from db import fetch_all
from queries import _serialize


_SCOPE = """
WITH jogos_tecnico AS (
    SELECT j.id, j.campeonato_id, j.casa_id AS clube_id,
           j.fora_id AS rival_id, j.gols_casa AS gm, j.gols_fora AS gs
    FROM jogos j
    WHERE j.temporada = %s AND j.tecnico_casa_id = %s
      AND j.gols_casa IS NOT NULL AND j.gols_fora IS NOT NULL
    UNION ALL
    SELECT j.id, j.campeonato_id, j.fora_id, j.casa_id,
           j.gols_fora, j.gols_casa
    FROM jogos j
    WHERE j.temporada = %s AND j.tecnico_fora_id = %s
      AND j.gols_casa IS NOT NULL AND j.gols_fora IS NOT NULL
)
"""

# Colunas já utilizadas no módulo de estatísticas da aplicação.
# Campos não encontrados no registro de uma partida ficam NULL — nunca viram 0.
_DETAIL = """
SELECT j.campeonato_id, j.clube_id, c.nome AS campeonato, cl.clube, COUNT(*) AS jogos,
       SUM(j.gm) AS gols_marcados, SUM(j.gs) AS gols_sofridos,
       COUNT(*) FILTER (WHERE j.gs = 0) AS clean_sheets,
       COUNT(*) FILTER (WHERE j.gm = 0) AS clean_goals,
       SUM((j.gm > j.gs)::int) AS vitorias,
       SUM((j.gm = j.gs)::int) AS empates,
       SUM((j.gm < j.gs)::int) AS derrotas,
       COUNT(e.jogo_id) AS partidas_com_estatisticas,
       SUM(e.total_chutes) AS finalizacoes_feitas,
       SUM(e.chutes_certos) AS finalizacoes_certas,
       SUM(r.total_chutes) AS finalizacoes_sofridas,
       SUM(r.chutes_certos) AS finalizacoes_certas_sofridas,
       SUM(e.disputas_aereas) AS duelos_aereos,
       SUM(e.disputas_aereas_ganhas) AS duelos_aereos_ganhos,
       SUM(r.disputas_aereas) AS duelos_aereos_adversario,
       SUM(r.disputas_aereas_ganhas) AS duelos_aereos_adversario_ganhos,
       SUM(e.xg) AS xg,
       SUM(r.xg) AS xg_sofrido,
       SUM(e.xg_jogada_ensaiada) AS xg_bola_parada
FROM jogos_tecnico j
JOIN campeonatos c ON c.id = j.campeonato_id
JOIN clubes cl ON cl.id = j.clube_id
LEFT JOIN estatisticas e ON e.jogo_id = j.id
    AND e.clube_id = j.clube_id AND e.periodo = 'Completo'
LEFT JOIN estatisticas r ON r.jogo_id = j.id
    AND r.clube_id = j.rival_id AND r.periodo = 'Completo'
GROUP BY j.campeonato_id, j.clube_id, c.nome, cl.clube
"""

# As estatísticas das finalizações são filtradas pelo clube que efetivamente
# foi treinado, nunca pelo clube atual nem por todas as partidas do elenco.
_GOALS = r"""
SELECT j.campeonato_id, j.clube_id,
       COUNT(*) FILTER (WHERE f.clube_id = j.clube_id AND NOT f.foi_contra) AS chutes_registrados,
       COUNT(*) FILTER (WHERE f.clube_id = j.rival_id AND NOT f.foi_contra) AS chutes_sofridos_registrados,
       COUNT(*) FILTER (WHERE f.e_gol AND
         ((f.clube_id = j.clube_id AND NOT f.foi_contra)
          OR (f.clube_id = j.rival_id AND f.foi_contra))) AS gols_registrados,
       COUNT(*) FILTER (WHERE f.e_gol AND f.clube_id = j.rival_id AND f.foi_contra)
         AS gols_contra_a_favor,
       COUNT(*) FILTER (WHERE f.e_gol AND f.clube_id = j.clube_id AND NOT f.foi_contra
         AND f.corpo <> '') AS gols_com_tipo_finalizacao,
       COUNT(*) FILTER (WHERE f.e_gol AND f.clube_id = j.clube_id AND NOT f.foi_contra
         AND f.situacao <> '') AS gols_com_situacao,
       COUNT(*) FILTER (WHERE f.e_gol AND f.clube_id = j.clube_id AND NOT f.foi_contra
         AND f.corpo ~ '(rightfoot|pedireit|direito|footright)') AS pe_direito,
       COUNT(*) FILTER (WHERE f.e_gol AND f.clube_id = j.clube_id AND NOT f.foi_contra
         AND f.corpo ~ '(leftfoot|peesquerd|esquerdo|footleft)') AS pe_esquerdo,
       COUNT(*) FILTER (WHERE f.e_gol AND f.clube_id = j.clube_id AND NOT f.foi_contra
         AND f.corpo ~ '(header|cabeca|head)') AS cabeca,
       COUNT(*) FILTER (WHERE f.e_gol AND f.clube_id = j.clube_id AND NOT f.foi_contra
         AND f.situacao ~ '(bolaparada|setpiece|setplay|corner|escanteio|freekick|falta|penalt)') AS bola_parada,
       COUNT(*) FILTER (WHERE f.e_gol AND f.clube_id = j.clube_id AND NOT f.foi_contra
         AND f.situacao ~ '(escanteio|corner)') AS escanteio,
       COUNT(*) FILTER (WHERE f.e_gol AND f.clube_id = j.clube_id AND NOT f.foi_contra
         AND f.situacao ~ '(freekick|tirolivre|cobrancadefalta|faltadireta|faltaindireta)') AS falta,
       COUNT(*) FILTER (WHERE f.e_gol AND f.clube_id = j.clube_id AND NOT f.foi_contra
         AND f.situacao ~ '(penalt)') AS penalti,
       COUNT(*) FILTER (WHERE f.e_gol AND f.clube_id = j.clube_id AND NOT f.foi_contra
         AND f.situacao ~ '(individual|solo)') AS individual
FROM jogos_tecnico j
LEFT JOIN LATERAL (
    SELECT f.clube_id,
       LOWER(COALESCE(f.foi_gol_contra::text, 'false')) IN ('true','t','1') AS foi_contra,
       LOWER(COALESCE(f.tipo_evento,'')) ~ '(gol|goal)' AS e_gol,
       regexp_replace(translate(LOWER(COALESCE(f.tipo_finalizacao,'')),
         'áàâãéêíóôõúç', 'aaaaeeiooouc'),'[^a-z0-9]','','g') AS corpo,
       regexp_replace(translate(LOWER(COALESCE(f.situacao_jogada,'')),
         'áàâãéêíóôõúç', 'aaaaeeiooouc'),'[^a-z0-9]','','g') AS situacao
    FROM finalizacoes f WHERE f.jogo_id = j.id
      AND f.clube_id IN (j.clube_id, j.rival_id)
) f ON TRUE
GROUP BY j.campeonato_id, j.clube_id
"""


def _sum(records, key):
    xs = [float(v[key]) for v in records if v.get(key) is not None]
    return round(sum(xs), 2) if xs else None


def _ratio(num, den):
    return round(100 * float(num) / float(den), 1) if num is not None and den and float(den) > 0 else None


def estatisticas_tecnico(tecnico_id: int, temporada: str) -> dict:
    if tecnico_id <= 0 or not temporada:
        return {"linhas": [], "temporada": temporada}
    args = (temporada, tecnico_id, temporada, tecnico_id)
    general = [_serialize(x) for x in fetch_all(_SCOPE + _DETAIL, args)]
    # Pode não existir mapa de finalizações em parte dos jogos. A ausência é informada.
    goals = [_serialize(x) for x in fetch_all(_SCOPE + _GOALS, args)]
    lookup = {(x["campeonato_id"], x["clube_id"]): x for x in goals}
    for item in general:
        more = lookup.get((item["campeonato_id"], item["clube_id"]), {})
        item["gols_tipos"] = {name: more.get(name) for name in (
            "pe_direito", "pe_esquerdo", "cabeca", "bola_parada", "escanteio",
            "falta", "penalti", "individual", "gols_contra_a_favor",
            "gols_registrados", "gols_com_tipo_finalizacao", "gols_com_situacao")}
        item["eficiencia_aerea"] = _ratio(item.get("duelos_aereos_ganhos"), item.get("duelos_aereos"))
        item["eficiencia_aerea_adversario"] = _ratio(item.get("duelos_aereos_adversario_ganhos"), item.get("duelos_aereos_adversario"))
        item["precisao_finalizacoes"] = _ratio(item.get("finalizacoes_certas"), item.get("finalizacoes_feitas"))
    return {"linhas": general, "temporada": temporada,
            "nota": "As estatísticas são apenas de jogos comandados pelo técnico nesta temporada. 'Clean goals' significa jogo sem marcar. Gols por tipo podem se sobrepor e só contemplam eventos classificados.",
            "tipos_disponiveis": ["pe_direito", "pe_esquerdo", "cabeca", "bola_parada",
                                  "escanteio", "falta", "penalti", "individual"]}
