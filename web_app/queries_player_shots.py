"""Finalizações individuais, defesas e pênaltis por temporada.

Dados auditáveis da tabela finalizacoes. Não inferir mergulho do goleiro
a partir do destino da bola (são eventos diferentes).
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from math import isfinite

from db import fetch_all, fetch_one

PENALTY_LABEL = "Pênalti"
GOAL_WIDTH = 7.32
GOAL_CENTER_X = 34.0
LEFT_POST = GOAL_CENTER_X - GOAL_WIDTH / 2
RIGHT_POST = GOAL_CENTER_X + GOAL_WIDTH / 2
SAVED = "defendida"
GOAL = "gol"


def _number(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if isfinite(number) else None


def _pct(numerator, denominator):
    return round(100 * numerator / denominator, 1) if denominator else 0.0


def _is_goal(row):
    return str(row.get("tipo_evento") or "").casefold().strip() == GOAL and not row.get("foi_gol_contra")


def _is_saved(row):
    return str(row.get("tipo_evento") or "").casefold().strip() == SAVED


def _on_target(row):
    # O FotMob pode marcar falso em um gol raro; o gol e a defesa
    # continuam sendo finalizações ao alvo.
    return _is_goal(row) or _is_saved(row) or row.get("foi_no_alvo") is True


def _side(row):
    x = _number(row.get("local_x_gol"))
    if x is None or x < 0 or x > 68:
        return None
    # A orientação é a MESMA de goalPosition() em shot-visuals.js.
    # "Esquerda" e "direita" são as posições na imagem do gol de frente.
    if x > LEFT_POST + GOAL_WIDTH * 2 / 3:
        return "esquerda"
    if x < LEFT_POST + GOAL_WIDTH / 3:
        return "direita"
    return "centro"


def _height(row):
    z = _number(row.get("altura_z_gol"))
    if z is None or z < 0 or z > 8:
        return None
    # Representa a altura da bola na linha do gol, não o gesto do atleta.
    if z <= 0.6:
        return "rasteiro"
    if z <= 1.5:
        return "meia_altura"
    return "alto"


def _groups(rows, field, options):
    result = []
    total = len(rows)
    for key, label in options:
        selected = [r for r in rows if (r.get(field) or "") == key]
        attempts = len(selected)
        goals = sum(_is_goal(r) for r in selected)
        saves = sum(_is_saved(r) for r in selected)
        result.append({
            "chave": key, "label": label, "tentativas": attempts,
            "gols": goals, "defesas": saves,
            "distribuicao_pct": _pct(attempts, total),
            "acerto_pct": _pct(goals, attempts),
        })
    return result


def _penalties(rows, keeper):
    penalties = [r for r in rows if r["penalti"]]
    if not penalties:
        return None
    goals = sum(_is_goal(r) for r in penalties)
    saves = sum(_is_saved(r) for r in penalties)
    on_target = sum(_on_target(r) for r in penalties)
    sides = _groups(penalties, "lado_gol", [
        ("esquerda", "Esquerda"), ("centro", "Centro"), ("direita", "Direita")
    ])
    heights = _groups(penalties, "altura_gol", [
        ("rasteiro", "Rasteiro"), ("meia_altura", "Meia-altura"), ("alto", "Alto")
    ])
    return {
        "tentativas": len(penalties), "gols": goals, "defesas": saves,
        "no_alvo": on_target,
        "acertos": saves if keeper else goals,
        "acerto_pct": _pct(saves if keeper else goals, len(penalties)),
        "lados": sides,
        "alturas": heights,
        "sem_lado": sum(r["lado_gol"] is None for r in penalties),
        "sem_altura": sum(r["altura_gol"] is None for r in penalties),
        "mapa": penalties,
        # Não há trajetória corporal, lado do salto nem tipo da defesa na tabela.
        "salto_goleiro_disponivel": False,
    }


def _shot_type(kind):
    k = str(kind or "").strip().casefold()
    if k == "pé direito":
        return "direito", "Pé direito"
    if k == "pé esquerdo":
        return "esquerdo", "Pé esquerdo"
    if k == "cabeça":
        return "cabeca", "Cabeça"
    return "outros", "Outros"


def summarize(rows, goalkeeper=False):
    """Função pura para cálculo e testes, não altera os dados originais."""
    prepared = []
    for row in rows:
        item = dict(row)
        item["tipo_chute"], item["tipo_chute_label"] = _shot_type(row.get("tipo_finalizacao"))
        item["gol"] = bool(_is_goal(row))
        item["defesa"] = bool(_is_saved(row))
        item["no_alvo"] = bool(_on_target(row))
        item["penalti"] = str(row.get("situacao_jogada") or "").strip().casefold() == "pênalti"
        item["lado_gol"] = _side(row)
        item["altura_gol"] = _height(row)
        for field in ("coordenada_x", "coordenada_y", "local_x_gol", "altura_z_gol", "xg", "xgot"):
            item[field] = _number(row.get(field))
        prepared.append(item)

    total = len(prepared)
    goals = sum(item["gol"] for item in prepared)
    saved = sum(item["defesa"] for item in prepared)
    accurate = sum(item["no_alvo"] for item in prepared)
    types = []
    for key, label in [
        ("direito", "Pé direito"), ("esquerdo", "Pé esquerdo"),
        ("cabeca", "Cabeça"), ("outros", "Outros")
    ]:
        subset = [r for r in prepared if r["tipo_chute"] == key]
        attempts = len(subset)
        if attempts == 0 and key == "outros":
            continue
        count = sum(r["no_alvo"] for r in subset)
        types.append({
            "chave": key, "label": label,
            "tentativas": attempts, "acertos": count,
            "acerto_pct": _pct(count, attempts),
            "gols": sum(r["gol"] for r in subset),
        })

    penalty = _penalties(prepared, goalkeeper)
    # Deixar explícito que só são contabilizados goleiros identificados.
    result = {
        "tipo": "goleiro" if goalkeeper else "linha",
        "resumo": {
            "tentativas": total, "no_alvo": accurate, "gols": goals,
            "defesas": saved,
            "acertos": saved if goalkeeper else accurate,
            "acerto_pct": _pct(saved, accurate) if goalkeeper else _pct(accurate, total),
            "fora_bloqueada": sum(
                str(r.get("tipo_evento") or "").casefold() in
                ("para fora", "bloqueada", "trave") for r in prepared
            ),
        },
        "tipos": types,
        "penaltis": penalty,
        "mapa": prepared,
        "cobertura": ("Somente finalizações com goleiro identificado no banco. "
                      "Não representa necessariamente todas as finalizações sofridas."
                      if goalkeeper else "Finalizações atribuídas ao jogador na temporada."),
    }
    return result


def consultar(jogador_id: int, temporada: str | None = None):
    if type(jogador_id) is not int or jogador_id <= 0:
        raise ValueError("Jogador inválido.")
    info = fetch_one("SELECT id, nome, posicao FROM jogadores WHERE id = %s", (jogador_id,))
    if not info:
        return None
    goalkeeper = "goleiro" in str(info.get("posicao") or "").casefold()

    filters = ["f.goleiro_id = %s" if goalkeeper else "f.jogador_id = %s",
               "jo.gols_casa IS NOT NULL"]
    args = [jogador_id]
    if temporada:
        filters.append("jo.temporada = %s")
        args.append(temporada)
    rows = fetch_all(
        """
        SELECT f.id, f.jogo_id, f.jogador_id, f.goleiro_id,
               f.mando, f.tipo_evento, f.tipo_finalizacao, f.situacao_jogada,
               f.foi_no_alvo, f.foi_gol_contra, f.foi_bloqueada,
               f.defendido_em_cima_da_linha, f.minuto, f.minuto_adicional,
               f.coordenada_x, f.coordenada_y, f.local_x_gol, f.altura_z_gol,
               f.xg, f.xgot, jo.data, jo.temporada,
               a.nome AS atacante, co.nome AS campeonato
        FROM finalizacoes f
        JOIN jogos jo ON jo.id = f.jogo_id
        LEFT JOIN jogadores a ON a.id = f.jogador_id
        LEFT JOIN campeonatos co ON co.id = jo.campeonato_id
        WHERE """ + " AND ".join(filters) + """
        ORDER BY jo.data DESC, f.minuto DESC NULLS LAST, f.id DESC
        """,
        tuple(args),
    )
    result = summarize(rows, goalkeeper=goalkeeper)
    result["jogador_id"] = jogador_id
    result["temporada"] = temporada
    result["jogador"] = info["nome"]
    # Mapas de interface recebem os lances mais recentes, mas todos os
    # registros participam dos percentuais e denominadores.
    result["mapa_total"] = len(result["mapa"])
    result["mapa"] = result["mapa"][:900]
    if result["penaltis"]:
        result["penaltis"]["mapa"] = result["penaltis"]["mapa"][:300]
    return result
