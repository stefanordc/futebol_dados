"""Atualiza odds das temporadas correntes dos campeonatos já importados.

GitHub Actions: exige SUPABASE_DB_URL e FUTPYTHONTRADER_API_KEY em Secrets.
A chave NUNCA é enviada aos logs. Novos clubes sem vínculo confiável são
ignorados, não associados por adivinhação.
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# O mesmo importador do aplicativo, sem duplicar sua lógica de mercados.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import queries_integracoes as qi  # noqa: E402
from db import fetch_all, get_conn  # noqa: E402
from psycopg2 import sql  # noqa: E402

SOURCE_HOST = "futpythontrader.com.br"
BASE = "https://" + SOURCE_HOST
PATH_RE = re.compile(r"^/api/download/([a-z0-9-]+)/([a-z0-9-]+)/(20\d{2}(?:-20\d{2})?)$")
MAX_LEAGUES = 50


def current_season(sample_season: str, today: datetime) -> str:
    """Competições divididas viram o ano em julho; anuais usam ano civil."""
    year = today.year
    if re.fullmatch(r"20\d{2}-20\d{2}", sample_season):
        first = year if today.month >= 7 else year - 1
        return f"{first}-{first + 1}"
    if re.fullmatch(r"20\d{2}", sample_season):
        return str(year)
    raise ValueError("Temporada inválida no histórico.")


def discover_targets(records: list[dict], today: datetime) -> list[dict]:
    """Uma única rota por país/liga, usando histórico confirmado no Supabase.

    Se a temporada atual já foi importada, seus metadados prevalecem.
    Caso contrário, usa o último cadastro da competição.
    """
    targets = {}
    for r in records:
        path = str(r.get("caminho") or "")
        m = PATH_RE.fullmatch(path)
        if not m or str(r.get("origem") or "").lower() != SOURCE_HOST:
            continue
        base_path = "/api/download/" + m.group(1) + "/" + m.group(2)
        current = current_season(m.group(3), today)
        # Não misturar anos simples com intervalos da mesma rota.
        if ("-" in m.group(3)) != ("-" in current):
            continue
        target_path = base_path + "/" + current
        candidate = {
            "path": target_path,
            "season": current,
            "country": str(r.get("pais") or ""),
            "league": str(r.get("campeonato") or ""),
            "already_current": path == target_path,
            "id": int(r.get("id") or 0),
        }
        previous = targets.get(base_path)
        if previous is None or (
            (candidate["already_current"], candidate["id"])
            > (previous["already_current"], previous["id"])
        ):
            targets[base_path] = candidate
    if len(targets) > MAX_LEAGUES:
        raise ValueError("Número de competições acima do limite.")
    return sorted(targets.values(), key=lambda x: x["path"])


def alias_links(host: str, country: str) -> dict[str, dict]:
    """Vínculos já aprovados pelo usuário + país validado no banco."""
    records = fetch_all(
        """SELECT f.nome_externo, f.clube_id, c.clube, p.nome AS pais
           FROM public.clubes_fontes f
           JOIN public.clubes c ON c.id=f.clube_id
           JOIN public.paises p ON p.id=c.pais_id
           WHERE f.fonte='odds_api' AND f.id_externo LIKE %s""",
        ("odds:" + host + ":%",),
    )
    result: dict[str, dict] = {}
    for record in records:
        if qi._pais_normalizado(record["pais"]) != qi._pais_normalizado(country):
            continue
        name = str(record["nome_externo"])
        candidate = {"clube_id": record["clube_id"], "padronizado": record["clube"]}
        # Conflitos são removidos, nunca resolvidos com correspondência arbitrária.
        if name in result and result[name] != candidate:
            result[name] = {"clube_id": None, "padronizado": name}
        else:
            result[name] = candidate
    return result


def resolve_clubs(clubs: list[dict], remembered: dict) -> list[dict]:
    aliases = []
    for club in clubs:
        name = club["original"]
        candidate = remembered.get(name)
        if candidate is None:
            candidate = {
                "clube_id": club.get("clube_id"),
                "padronizado": club.get("padronizado") or name,
            }
        aliases.append({
            "original": name,
            "clube_id": candidate["clube_id"],
            "padronizado": candidate["padronizado"],
        })
    return aliases


def odds_changes(rows: list[dict], season: str, columns: list[str], aliases: list[dict]):
    """Só cotações válidas e bookmakers, nunca sobrescreve metadados do jogo."""
    selected = [c for c in columns if qi._is_odd_column(c)]
    known = {x["original"]: x for x in aliases if x["clube_id"] is not None}
    out = []
    for row in rows:
        h = qi._pick(row, qi.HOME_KEYS)
        a = qi._pick(row, qi.AWAY_KEYS)
        match_id = qi._pick(row, qi.ID_KEYS)
        if not match_id or h not in known or a not in known:
            continue
        values = qi._linha_colunas(row, selected)
        changes = {k: v for k, v in values.items()
                   if v is not None and (qi._is_odd_column(k) or
                                         k.startswith(("lay_", "bookie_")))}
        if changes:
            out.append((match_id, known[h]["clube_id"],
                        known[a]["clube_id"], changes))
    return out


def update_existing(season: str, candidates: list, available_columns: set[str]) -> int:
    """Atualização apenas de valores que efetivamente mudaram."""
    changed = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for external, home_id, away_id, changes in candidates:
                cols = [k for k in changes if k in available_columns]
                if not cols:
                    continue
                vals = [changes[c] for c in cols]
                assignment = sql.SQL(", ").join(
                    sql.SQL("{}=%s").format(sql.Identifier(c)) for c in cols
                )
                differences = sql.SQL(" OR ").join(
                    sql.SQL("{} IS DISTINCT FROM %s").format(sql.Identifier(c)) for c in cols
                )
                query = (
                    sql.SQL("UPDATE public.odds SET ")
                    + assignment
                    + sql.SQL(", atualizado_em=NOW() WHERE fonte=%s AND temporada=%s ")
                    + sql.SQL("AND partida_externa_id=%s AND mandante_id=%s ")
                    + sql.SQL("AND visitante_id=%s AND (")
                    + differences
                    + sql.SQL(")")
                )
                params = (vals + [SOURCE_HOST, season, external, home_id, away_id]
                          + vals)
                cur.execute(query, params)
                changed += cur.rowcount
        conn.commit()
    return changed


def run() -> int:
    # Nunca abrir URL com credenciais se Secrets não estiverem configurados.
    api_key = os.environ.get("FUTPYTHONTRADER_API_KEY", "").strip()
    dsn = os.environ.get("SUPABASE_DB_URL", "").strip()
    if not api_key or not dsn:
        print("Faltam Secrets FUTPYTHONTRADER_API_KEY e/ou SUPABASE_DB_URL.", file=sys.stderr)
        return 2

    today = datetime.now(ZoneInfo("America/Sao_Paulo"))
    records = fetch_all(
        """SELECT id,origem,caminho,pais,campeonato,temporada
           FROM public.odds_importacoes ORDER BY id DESC"""
    )
    targets = discover_targets(records, today)
    if not targets:
        print("Não há campeonatos importados com caminhos válidos.", file=sys.stderr)
        return 1

    available = {
        row["column_name"] for row in fetch_all(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema='public' AND table_name='odds'"""
        )
    }
    summary = Counter()
    failures = []
    for target in targets:
        path = target["path"]
        print(f"Consultando {path}")
        try:
            result = qi.preview({
                "base": BASE, "caminho": path,
                "chave": api_key, "cabecalho": "api_key",
                "salvar_chave": False,
            })
            token = result["preview_id"]
            preview_data = qi._PREVIEWS[token]
            raw_rows = list(preview_data["rows"])
            aliases = resolve_clubs(
                result["clubes"], alias_links(SOURCE_HOST, target["country"])
            )
            by_name = {x["original"]: x for x in aliases}
            # Sem ID canônico confiável: não gravar a partida.
            approved = [
                row for row in raw_rows
                if by_name.get(qi._pick(row, qi.HOME_KEYS), {}).get("clube_id")
                and by_name.get(qi._pick(row, qi.AWAY_KEYS), {}).get("clube_id")
            ]
            skipped = len(raw_rows) - len(approved)
            if not approved:
                qi._PREVIEWS.pop(token, None)
                print(f"Sem partidas vinculadas: {len(raw_rows)} ignoradas.")
                summary["sem_vinculo"] += skipped
                continue
            preview_data["rows"] = approved
            preview_data["row_seasons"] = [target["season"]] * len(approved)
            approved_names = {
                name
                for row in approved
                for name in (qi._pick(row, qi.HOME_KEYS), qi._pick(row, qi.AWAY_KEYS))
                if name
            }
            linked_aliases = [a for a in aliases if a["original"] in approved_names]
            columns = qi._default_columns(result["colunas"])
            candidates = odds_changes(approved, target["season"], columns, linked_aliases)
            stats = qi.importar({
                "preview_id": token,
                "colunas": columns,
                "clubes": linked_aliases,
                "pais": target["country"],
                "campeonato": target["league"],
                "temporada": target["season"],
            })
            updated = update_existing(target["season"], candidates, available)
            print(f"Novos: {stats['inseridos']}; atualizados: {updated}; "
                  f"existentes: {stats['ignorados']}; sem vínculo: {skipped}")
            summary["novos"] += stats["inseridos"]
            summary["atualizados"] += updated
            summary["existentes"] += stats["ignorados"]
            summary["sem_vinculo"] += skipped
            summary["ligas"] += 1
        except Exception as error:
            # Não registrar a URL da requisição, pois ela contém a api_key.
            failures.append(path)
            print(f"Falha na competição {path}: {type(error).__name__}", file=sys.stderr)
    print("RESUMO:", dict(summary))
    if failures:
        print("Competições com erro:", ", ".join(failures), file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run())
