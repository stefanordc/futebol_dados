"""Coleta IDs dos jogos finalizados no FotMob após a última data no banco.

Lê campeonatos_fotmob.json (um ou vários campeonatos/temporadas) e grava
id_jogos.txt no mesmo formato JSON da coleta Sofascore.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from dados_fotmob import (
    BASE_URL,
    ClienteFotmob,
    BRASILIA_TZ,
    carregar_variaveis_de_ambiente,
    conexao_bd,
    maior_data_campeonato,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("coleta_jogos_fotmob")

DIR = Path(__file__).resolve().parent
ARQUIVO_CAMPEONATOS = DIR / "campeonatos_fotmob.json"
ARQUIVO_IDS = DIR / "id_jogos.txt"


def _to_int(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def ler_campeonatos_fotmob(caminho=None) -> list[dict]:
    """Uma entrada por (campeonato, temporada).

    Formato de campeonatos_fotmob.json:
      {
        "87": {
          "campeonato": "Espanhol",
          "pais": "Espanha",
          "ccode3": "ESP",
          "temporadas": ["2026/2027", "2025/2026"]
        }
      }

    Também aceita o formato antigo com link_base e chaves numéricas de temporada
    (ignoradas — no FotMob a temporada é a string "AAAA/AAAA").
    """
    arquivo = Path(caminho or ARQUIVO_CAMPEONATOS)
    if not arquivo.is_file():
        raise FileNotFoundError(f"campeonatos_fotmob.json não encontrado: {arquivo}")
    dados = json.loads(arquivo.read_text(encoding="utf-8-sig"))
    itens = []
    for id_camp, info in dados.items():
        if not isinstance(info, dict):
            continue
        id_campeonato = _to_int(id_camp)
        if not id_campeonato:
            logger.warning("Chave de campeonato inválida ignorada: %r", id_camp)
            continue
        nome = str(info.get("campeonato") or info.get("nome") or "").strip() or f"Campeonato {id_campeonato}"
        pais = str(info.get("pais") or "").strip() or None
        ccode3 = str(info.get("ccode3") or "INT").strip().upper()

        temporadas: list[str] = []
        if isinstance(info.get("temporadas"), list):
            temporadas = [str(t).strip() for t in info["temporadas"] if str(t).strip()]
        elif isinstance(info.get("temporadas"), dict):
            temporadas = [str(t).strip() for t in info["temporadas"].keys() if str(t).strip()]
        else:
            # Compat: {"97268": "2026/2027"} ou {"2026/2027": true}
            for chave, valor in info.items():
                if chave in ("link_base", "campeonato", "nome", "pais", "ccode3", "temporadas"):
                    continue
                if isinstance(valor, str) and "/" in valor:
                    temporadas.append(valor.strip())
                elif isinstance(chave, str) and "/" in chave:
                    temporadas.append(chave.strip())

        # Dedup preservando ordem
        vistos = set()
        temporadas_ok = []
        for t in temporadas:
            if t not in vistos:
                vistos.add(t)
                temporadas_ok.append(t)
        if not temporadas_ok:
            logger.warning("Campeonato %s (%s) sem temporadas; ignorado.", id_campeonato, nome)
            continue

        link_base = info.get("link_base")
        for temporada in temporadas_ok:
            itens.append({
                "id_campeonato": id_campeonato,
                "campeonato": nome,
                "pais": pais,
                "ccode3": ccode3,
                "temporada": temporada,
                "link_base": link_base,
            })
    return itens


def url_liga(camp: dict) -> str:
    """Monta a URL da API de leagues para a temporada pedida."""
    season = quote(str(camp["temporada"]), safe="")
    if camp.get("link_base"):
        base = str(camp["link_base"]).rstrip("&?")
        sep = "&" if "?" in base else "?"
        # Garante season na URL (substitui se já existir)
        if "season=" in base:
            base = re.sub(r"([?&])season=[^&]*", rf"\1season={season}", base)
            if "season=" not in base:
                base = f"{base}{sep}season={season}"
            return base
        return f"{base}{sep}season={season}"
    return (
        f"{BASE_URL}/leagues?id={camp['id_campeonato']}"
        f"&ccode3={camp['ccode3']}&season={season}"
    )


def _data_jogo(jogo: dict):
    status = jogo.get("status") if isinstance(jogo.get("status"), dict) else {}
    iso = status.get("utcTime") or jogo.get("statusTime") or jogo.get("time")
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(BRASILIA_TZ).date()
    except ValueError:
        return None


def _jogo_finalizado_fixture(jogo: dict) -> bool:
    status = jogo.get("status") if isinstance(jogo.get("status"), dict) else {}
    if status.get("finished") is True:
        return True
    reason = status.get("reason") if isinstance(status.get("reason"), dict) else {}
    chave = str(reason.get("longKey") or reason.get("shortKey") or "").lower()
    return chave in ("finished", "fulltime_short", "fulltime")


def extrair_ids_apos_data(payload: dict, data_minima) -> list[int]:
    """Só jogos FINALIZADOS com data >= última coletada (corte por data, não por rodada).

    data_minima = maior data com placar no banco; jogos com data menor são ignorados.
    O mesmo dia ainda entra (pode faltar um jogo). Ordena por data ascendente.
    """
    matches = (payload.get("fixtures") or {}).get("allMatches") or []
    vistos: set[int] = set()
    escolhidos: list[tuple] = []  # (data, id)
    for jogo in matches:
        if not isinstance(jogo, dict) or not _jogo_finalizado_fixture(jogo):
            continue
        data = _data_jogo(jogo)
        if data is None:
            continue
        # data == última: ainda pode haver jogo do mesmo dia não coletado
        if data_minima is not None and data < data_minima:
            continue
        mid = _to_int(jogo.get("id"))
        if mid is None or mid in vistos:
            continue
        vistos.add(mid)
        escolhidos.append((data, mid))
    escolhidos.sort(key=lambda x: (x[0], x[1]))
    return [mid for _, mid in escolhidos]


def gravar_json(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    carregar_variaveis_de_ambiente(DIR)
    if not os.environ.get("SUPABASE_DB_URL"):
        raise RuntimeError(f"SUPABASE_DB_URL ausente: configure no .env em {DIR}")

    campeonatos = ler_campeonatos_fotmob()
    if not campeonatos:
        logger.warning("Nenhum campeonato/temporada em %s.", ARQUIVO_CAMPEONATOS)
        return
    logger.info("%d campeonato(s)/temporada(s) em %s", len(campeonatos), ARQUIVO_CAMPEONATOS)

    saida = {"campeonatos": []}
    cliente = ClienteFotmob()
    try:
        with conexao_bd() as conn:
            for i, camp in enumerate(campeonatos, start=1):
                rotulo = f"{camp['campeonato']} {camp['temporada']}"
                ultima = maior_data_campeonato(conn, camp["id_campeonato"], camp["temporada"])
                logger.info(
                    "[%d/%d] %s | id=%s | última data no banco=%s",
                    i, len(campeonatos), rotulo, camp["id_campeonato"], ultima or "(nenhuma)",
                )
                entrada = {
                    "id_campeonato": camp["id_campeonato"],
                    "campeonato": camp["campeonato"],
                    "pais": camp.get("pais"),
                    "temporada": camp["temporada"],
                    "ids_jogos": [],
                }
                try:
                    url = url_liga(camp)
                    logger.info("   GET %s", url)
                    dados = cliente.fetch_json(url, tentativas=3)
                    if not isinstance(dados, dict):
                        raise RuntimeError(f"Resposta inválida de {url}")
                    ids = extrair_ids_apos_data(dados, ultima)
                    entrada["ids_jogos"] = ids
                    logger.info(
                        "   %d jogo(s) finalizado(s) com data >= %s (só finalizados; corte por data).",
                        len(ids), ultima or "o início",
                    )
                except Exception as e:
                    entrada["erro"] = str(e)
                    logger.error("   Falha em %s: %s", rotulo, e)
                saida["campeonatos"].append(entrada)
    finally:
        cliente.close()
        time.sleep(0.5)

    total = sum(len(c.get("ids_jogos") or []) for c in saida["campeonatos"])
    gravar_json(ARQUIVO_IDS, saida)
    logger.info("FINAL: %d ID(s) em %d campeonato(s) | salvos em %s", total, len(saida["campeonatos"]), ARQUIVO_IDS)


if __name__ == "__main__":
    main()
