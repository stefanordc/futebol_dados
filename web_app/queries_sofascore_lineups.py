"""Vinculação de partidas FotMob/Sofascore para o widget de escalações.

Prioridade: ID registrado -> dados_fisicos (data, campeonato, mandante;
depois visitante) -> partida equivalente em jogos.
Sem correspondência, gerar alerta; nunca inventar ID.
"""
from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from db import fetch_all, fetch_one, execute

_API_ROOTS = (
    "https://www.sofascore.com/api/v1",
    "https://api.sofascore.com/api/v1",
)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/",
}
_CACHE_LOCK = threading.Lock()
_DAILY_CACHE: dict[str, tuple[float, list[dict] | None]] = {}
_CACHE_SECONDS = 10 * 60


def _number(value) -> int | None:
    try:
        value = int(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return value if 0 < value < 2**63 else None


def _name(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    tokens = re.findall(r"[a-z0-9]+", normalized)
    drop = {"fc", "cf", "sc", "rc", "ac", "de", "da", "do", "the", "club"}
    return " ".join(t for t in tokens if t not in drop)


def _read_json(path: str) -> dict | None:
    for root in _API_ROOTS:
        req = Request(root + path, headers=_HEADERS)
        try:
            with urlopen(req, timeout=3.5) as response:
                if response.status != 200:
                    continue
                payload = response.read(7_000_001)
                if len(payload) > 7_000_000:
                    continue
                data = json.loads(payload.decode("utf-8"))
                if isinstance(data, dict):
                    return data
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            continue
    return None


def _events(day: date) -> list[dict] | None:
    key = day.isoformat()
    with _CACHE_LOCK:
        entry = _DAILY_CACHE.get(key)
        if entry and time.monotonic() < entry[0]:
            return entry[1]
    doc = _read_json("/sport/football/scheduled-events/" + key)
    found = doc.get("events") if isinstance(doc, dict) else None
    events = [x for x in found if isinstance(x, dict)] if isinstance(found, list) else None
    with _CACHE_LOCK:
        if len(_DAILY_CACHE) > 150:
            _DAILY_CACHE.clear()
        _DAILY_CACHE[key] = (time.monotonic() + _CACHE_SECONDS, events)
    return events


def _teams_match(event: dict, match: dict) -> bool:
    home = event.get("homeTeam") or {}
    away = event.get("awayTeam") or {}
    expected_home = _number(match.get("sofa_casa_id"))
    expected_away = _number(match.get("sofa_fora_id"))
    actual_home = _number(home.get("id"))
    actual_away = _number(away.get("id"))

    if expected_home is not None and actual_home != expected_home:
        return False
    if expected_away is not None and actual_away != expected_away:
        return False

    if expected_home is None:
        if _name(home.get("name")) != _name(match.get("casa")):
            return False
    if expected_away is None:
        if _name(away.get("name")) != _name(match.get("fora")):
            return False
    return True


def _get_match(match_id: int) -> dict | None:
    return fetch_one(
        """
        SELECT j.id, j.data, j.id_sofascore, j.casa_id, j.fora_id,
               c.nome AS campeonato, c.id_sofascore AS campeonato_sofascore,
               home.clube AS casa, away.clube AS fora,
               home_sofa.id_externo AS sofa_casa_id,
               away_sofa.id_externo AS sofa_fora_id
        FROM jogos j
        JOIN campeonatos c ON c.id = j.campeonato_id
        JOIN clubes home ON home.id = j.casa_id
        JOIN clubes away ON away.id = j.fora_id
        LEFT JOIN clubes_fontes home_sofa ON home_sofa.clube_id=j.casa_id
             AND home_sofa.fonte='sofascore'
        LEFT JOIN clubes_fontes away_sofa ON away_sofa.clube_id=j.fora_id
             AND away_sofa.fonte='sofascore'
        WHERE j.id = %s
        """,
        (match_id,),
    )


def _same_match_id(match: dict) -> int | None:
    # Existe duplicação histórica de jogos importados de FotMob e Sofascore,
    # mas id_sofascore é UNIQUE. Consultar a outra linha, não copiar o ID.
    found = fetch_one(
        """
        SELECT MIN(id_sofascore) AS sofa_id
        FROM jogos
        WHERE casa_id = %s AND fora_id = %s AND data = %s
          AND id_sofascore IS NOT NULL AND id_sofascore > 0
        HAVING COUNT(DISTINCT id_sofascore) = 1
        """,
        (match["casa_id"], match["fora_id"], match["data"]),
    )
    return _number(found.get("sofa_id")) if found else None



# Tabelas de origem usam nomes diferentes para a mesma liga.
# IDs confirmados em dados_fisicos.id_campeonato, não IDs internos de jogos.
_PHYSICAL_LEAGUE_IDS = {
    "laliga": 8, "espanhol": 8,
    "serie a": 23, "italiano": 23,
    "premier league": 17, "ingles": 17,
    "bundesliga": 35, "alemao": 35,
    "ligue 1": 34, "frances": 34,
    "eredivisie": 37, "holandes": 37,
    "brasileiro": 325,
    "portugues": 238, "liga portugal": 238,
    "belga": 38, "mls": 242,
    "dinamarques": 20,
}


def _same_physical_league(row: dict, match: dict) -> bool:
    observed = _number(row.get("id_campeonato"))
    expected = _number(match.get("campeonato_sofascore"))
    if expected and observed == expected:
        return True
    league = _name(match.get("campeonato"))
    row_league = _name(row.get("campeonato"))
    if observed and _PHYSICAL_LEAGUE_IDS.get(league) == observed:
        return True
    # Para ligas sem mapeamento de IDs, aceitar apenas nome exato normalizado.
    return bool(league and league == row_league)


def _same_physical_club(row: dict, match: dict, side: str) -> bool:
    expected_id = _number(match.get("sofa_casa_id" if side == "Casa" else "sofa_fora_id"))
    actual_id = _number(row.get("id_clube"))
    if expected_id and actual_id:
        return expected_id == actual_id
    expected_name = _name(match.get("casa" if side == "Casa" else "fora"))
    return bool(expected_name and expected_name == _name(row.get("clube")))


def _physical_match(match: dict) -> tuple[int | None, str]:
    """Localiza o ID por mandante e, se necessário, pelo visitante.

    Valida data e liga antes de considerar os clubes. Quando a outra equipe
    possui uma linha no mesmo id_jogo, ela também deve corresponder à partida.
    IDs ambíguos nunca são escolhidos ao acaso.
    """
    rows = fetch_all(
        """
        SELECT id_jogo, data, id_campeonato, campeonato,
               id_clube, clube, mando
        FROM dados_fisicos
        WHERE data = %s AND id_jogo IS NOT NULL
        """,
        (match["data"],),
    )
    league_rows = [
        row for row in rows
        if _number(row.get("id_jogo")) and _same_physical_league(row, match)
    ]
    # Mando ("Casa" / "Fora") vem da própria tabela de dados físicos.
    ids_by_side: dict[str, set[int]] = {}
    for side in ("Casa", "Fora"):
        counterpart = "Fora" if side == "Casa" else "Casa"
        matches = set()
        for row in league_rows:
            if str(row.get("mando") or "").casefold().strip() != side.casefold():
                continue
            if not _same_physical_club(row, match, side):
                continue
            identifier = _number(row["id_jogo"])
            if not identifier:
                continue
            opposite = [
                r for r in league_rows
                if _number(r.get("id_jogo")) == identifier
                and str(r.get("mando") or "").casefold().strip() == counterpart.casefold()
            ]
            if opposite and not any(
                _same_physical_club(other, match, counterpart) for other in opposite
            ):
                continue
            matches.add(identifier)
        ids_by_side[side] = matches
        if len(matches) == 1:
            return next(iter(matches)), (
                "dados_fisicos_mandante" if side == "Casa" else "dados_fisicos_visitante"
            )
    # Se o mandante teve múltiplos IDs, a identificação única do visitante
    # pode desambiguar sem perder o critério de correspondência.
    common = ids_by_side.get("Casa", set()) & ids_by_side.get("Fora", set())
    if len(common) == 1:
        return next(iter(common)), "dados_fisicos_ambos"
    if any(len(group) > 1 for group in ids_by_side.values()):
        return None, "dados_fisicos_ambiguo"
    return None, "dados_fisicos_nao_encontrado"



def _external_match(match: dict) -> tuple[int | None, str]:
    raw_date = match.get("data")
    if isinstance(raw_date, date):
        day = raw_date
    else:
        try:
            day = date.fromisoformat(str(raw_date)[:10])
        except (ValueError, TypeError):
            return None, "invalid_date"

    # Dias próximos cobrem partidas cujo fuso local diverge da data UTC.
    # Só usar evento de dentro do recorte e com os dois clubes confirmados.
    saw_response = False
    for day_to_search in (day, day - timedelta(days=1), day + timedelta(days=1)):
        events = _events(day_to_search)
        if events is None:
            # Se nem a agenda do próprio dia abriu, não sobrecarregar
            # o provedor com mais duas datas que também falharão.
            if day_to_search == day:
                return None, "upstream_unavailable"
            continue
        saw_response = True
        candidates = []
        for event in events:
            event_id = _number(event.get("id"))
            if not event_id or not _teams_match(event, match):
                continue
            stamp = event.get("startTimestamp")
            if stamp is not None:
                try:
                    from datetime import datetime, timezone
                    event_day = datetime.fromtimestamp(int(stamp),tz=timezone.utc).date()
                    if abs((event_day-day).days)>1:
                        continue
                except (TypeError,ValueError,OverflowError,OSError):
                    continue
            candidates.append(event_id)
        unique = set(candidates)
        if len(unique)==1:
            return next(iter(unique)), "sofascore_api"
        if len(unique)>1:
            return None, "ambiguous"
    return None, "not_found" if saw_response else "upstream_unavailable"


def resolve_match_id(match_id: int, online: bool = True) -> dict:
    if type(match_id) is not int or match_id <= 0:
        raise ValueError("Jogo inválido.")
    match = _get_match(match_id)
    if not match:
        return {"id":None,"fonte":"not_found","mensagem":"Jogo não encontrado."}

    direct = _number(match.get("id_sofascore"))
    if direct:
        return {"id":direct,"fonte":"vinculo","mensagem":None}
    # Primeira consulta à tabela de dados físicos: mandante, depois visitante.
    # Não depender da API pública do Sofascore, que pode bloquear requisições.
    physical, reason = _physical_match(match)
    if physical:
        return {"id":physical,"fonte":reason,"mensagem":None}
    duplicate = _same_match_id(match)
    if duplicate:
        return {"id":duplicate,"fonte":"jogo_correspondente","mensagem":None}

    if reason == "dados_fisicos_ambiguo":
        message = (
            "ALERTA: existem múltiplos IDs possíveis em dados_fisicos para "
            "a data, o campeonato e os clubes desta partida. "
            "Nenhum ID foi selecionado automaticamente."
        )
    else:
        message = (
            "ALERTA: ID do Sofascore não encontrado na tabela dados_fisicos "
            "pela data, campeonato e time mandante nem pelo visitante. "
            "Confira o vínculo do jogo ou informe o ID manualmente."
        )
    return {"id":None,"fonte":reason,"mensagem":message}


def parse_user_id(value: str | int) -> int:
    if isinstance(value, int):
        identifier=_number(value)
    else:
        value=str(value or "").strip()
        if value.isdecimal():
            identifier=_number(value)
        else:
            # Aceitar somente domínios oficiais, URLs com identificador do jogo.
            m = re.fullmatch(
                r"https?://(?:www\.)?sofascore\.com/(?:[^\s#?]+)"
                r"(?:\?[^\s#]*)?#id:(\d+)(?:\b.*)?",
                value,
                flags=re.IGNORECASE,
            )
            identifier=_number(m.group(1)) if m else None
    if not identifier:
        raise ValueError("Informe um ID numérico ou link Sofascore com #id:12345678.")
    return identifier


def set_match_id(match_id: int, value: str | int) -> dict:
    identifier = parse_user_id(value)
    match = _get_match(match_id)
    if not match:
        raise ValueError("Jogo não encontrado.")

    linked = _same_match_id(match)
    if linked and linked != identifier:
        raise ValueError("Esta partida já possui outro ID Sofascore associado a uma linha equivalente.")
    other = fetch_one(
        "SELECT id,casa_id,fora_id,data FROM jogos WHERE id_sofascore=%s LIMIT 1",
        (identifier,),
    )
    if other:
        # IDs compartilhados entre cópias do mesmo jogo são resolvidos
        # na leitura, sem violar a restrição UNIQUE de jogos.id_sofascore.
        if (other["casa_id"] != match["casa_id"] or
            other["fora_id"] != match["fora_id"] or
            other["data"] != match["data"]):
            raise ValueError("Este ID já está vinculado a outra partida.")
        return {"id":identifier,"fonte":"jogo_correspondente","mensagem":None}

    # Validar pelos clubes/dia se a API de evento estiver disponível.
    doc = _read_json("/event/" + str(identifier))
    if doc and isinstance(doc.get("event"), dict):
        event = doc["event"]
        if not _teams_match(event, match):
            raise ValueError("O ID pertence a clubes diferentes dos desta partida.")
        stamp = event.get("startTimestamp")
        if stamp is not None:
            from datetime import datetime, timezone
            event_day=datetime.fromtimestamp(int(stamp),tz=timezone.utc).date()
            raw_date=match["data"] if isinstance(match["data"],date) else date.fromisoformat(str(match["data"])[:10])
            if abs((event_day-raw_date).days)>1:
                raise ValueError("O ID pertence a outra data.")

    affected = execute(
        "UPDATE jogos SET id_sofascore=%s WHERE id=%s AND id_sofascore IS NULL",
        (identifier, match_id),
    )
    if not affected:
        # Outro processo preencheu o campo; verifique a correspondência.
        fresh = _get_match(match_id)
        if _number(fresh.get("id_sofascore")) != identifier:
            raise ValueError("O ID deste jogo foi atualizado por outro processo.")
    return {"id":identifier,"fonte":"vinculo_manual","mensagem":None}
