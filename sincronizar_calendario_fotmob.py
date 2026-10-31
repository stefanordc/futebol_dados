"""Sincroniza o calendário completo (todas as rodadas) a partir do FotMob.

Lê campeonatos_fotmob.json e grava em jogos todos os fixtures.allMatches,
incluindo partidas futuras (sem placar).
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from coleta_jogos_fotmob import ler_campeonatos_fotmob, url_liga
from dados_fotmob import (
    ClienteFotmob,
    carregar_variaveis_de_ambiente,
    conexao_bd,
    sincronizar_calendario_liga,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("sincronizar_calendario_fotmob")

DIR = Path(__file__).resolve().parent


def main() -> None:
    carregar_variaveis_de_ambiente(DIR)
    if not os.environ.get("SUPABASE_DB_URL"):
        raise RuntimeError(f"SUPABASE_DB_URL ausente: configure no .env em {DIR}")

    campeonatos = ler_campeonatos_fotmob()
    if not campeonatos:
        logger.warning("Nenhum campeonato/temporada em campeonatos_fotmob.json.")
        return

    cliente = ClienteFotmob()
    try:
        with conexao_bd() as conn:
            caches: dict = {}
            for i, camp in enumerate(campeonatos, start=1):
                rotulo = f"{camp['campeonato']} {camp['temporada']}"
                logger.info(
                    "[%d/%d] %s | id_fotmob=%s",
                    i, len(campeonatos), rotulo, camp["id_campeonato"],
                )
                url = url_liga(camp)
                logger.info("   GET %s", url)
                payload = cliente.fetch_json(url, tentativas=3)
                if not isinstance(payload, dict):
                    raise RuntimeError(f"Resposta inválida de {url}")
                resumo = sincronizar_calendario_liga(
                    conn,
                    payload,
                    id_fotmob_campeonato=camp["id_campeonato"],
                    temporada=camp["temporada"],
                    nome_campeonato=camp.get("campeonato"),
                    pais=camp.get("pais"),
                    caches=caches,
                )
                conn.commit()
                logger.info(
                    "   fixtures=%s | inseridos=%s | atualizados=%s | ignorados=%s | campeonato_id=%s",
                    resumo["total_fixtures"],
                    resumo["inseridos"],
                    resumo["atualizados"],
                    resumo["ignorados"],
                    resumo["campeonato_id"],
                )
    finally:
        cliente.close()
        time.sleep(0.5)

    logger.info("Calendário sincronizado.")


if __name__ == "__main__":
    main()
