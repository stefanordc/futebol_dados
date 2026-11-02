"""Regressões sem acesso à API nem ao banco para a sincronização semanal."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from unittest import TestCase
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from scripts import sync_odds_weekly as sync


class TestWeeklyOddsSync(TestCase):
    def setUp(self):
        self.today = datetime(2026, 11, 2, tzinfo=ZoneInfo("America/Sao_Paulo"))
        self.records = [
            {"id": 1, "origem": sync.SOURCE_HOST, "caminho":
             "/api/download/brazil/serie-a-betano/2026",
             "pais": "Brasil", "campeonato": "Brasileiro"},
            {"id": 7, "origem": sync.SOURCE_HOST, "caminho":
             "/api/download/england/premier-league/2026-2027",
             "pais": "Inglaterra", "campeonato": "Premier League"},
            {"id": 13, "origem": sync.SOURCE_HOST, "caminho":
             "/api/download/spain/laliga/2026-2027",
             "pais": "Espanha", "campeonato": "LaLiga"},
            {"id": 12, "origem": sync.SOURCE_HOST, "caminho":
             "/api/download/england/premier-league/2021-2022",
             "pais": "Inglaterra", "campeonato": "Premier League"},
            {"id": 14, "origem": sync.SOURCE_HOST, "caminho":
             "/api/download/spain/laliga/2026-2027",
             "pais": "Espanha", "campeonato": "LaLiga"},
        ]

    def test_descobre_tres_ligas_sem_duplicar_laliga(self):
        targets = sync.discover_targets(self.records, self.today)
        self.assertEqual(len(targets), 3)
        self.assertEqual(
            {x["path"] for x in targets},
            {
                "/api/download/brazil/serie-a-betano/2026",
                "/api/download/spain/laliga/2026-2027",
                "/api/download/england/premier-league/2026-2027",
            },
        )
        self.assertTrue(all(t["already_current"] for t in targets))
        laliga = next(t for t in targets if "/laliga/" in t["path"])
        self.assertEqual(laliga["id"], 14)

    def test_virada_da_temporada_europeia_em_julho(self):
        self.assertEqual(sync.current_season(
            "2025-2026", datetime(2027, 2, 5)), "2026-2027")
        self.assertEqual(sync.current_season(
            "2025-2026", datetime(2027, 8, 2)), "2027-2028")
        self.assertEqual(sync.current_season(
            "2026", datetime(2027, 2, 5)), "2027")
        sample = [
            {"id": 3, "origem": sync.SOURCE_HOST,
             "caminho": "/api/download/spain/laliga/2024-2025",
             "pais": "Espanha", "campeonato": "LaLiga"}
        ]
        targets = sync.discover_targets(sample, self.today)
        self.assertEqual(targets[0]["path"],
                         "/api/download/spain/laliga/2026-2027")

    def test_ignora_fonte_ou_caminho_invalido(self):
        invalid = [
            {"id": 1, "origem": "outro-site.com",
             "caminho": "/api/download/brazil/serie-a-betano/2026"},
            {"id": 2, "origem": sync.SOURCE_HOST,
             "caminho": "/api/download/../../admin/2026"},
            {"id": 3, "origem": sync.SOURCE_HOST,
             "caminho": "https://internal/2026"},
        ]
        self.assertEqual(sync.discover_targets(invalid, self.today), [])

    def test_somente_mercados_com_equipes_vinculadas(self):
        rows = [
            {"Home": "Chapecoense-SC", "Away": "Corinthians",
             "Match_ID": "AAA", "Odd_1_FT": "2.10",
             "Bookie_1X2_FT": "bet365"},
            {"Home": "Desconhecido", "Away": "Corinthians",
             "Match_ID": "BBB", "Odd_1_FT": "1.90"},
        ]
        aliases = [
            {"original": "Chapecoense-SC", "clube_id": 99, "padronizado": "Chapecoense"},
            {"original": "Corinthians", "clube_id": 89, "padronizado": "Corinthians"},
            {"original": "Desconhecido", "clube_id": None, "padronizado": "Desconhecido"},
        ]
        rows_for_update = sync.odds_changes(rows, "2026", [
            "Home", "Away", "Match_ID", "Odd_1_FT"], aliases)
        self.assertEqual(len(rows_for_update), 1)
        mid, home, away, changes = rows_for_update[0]
        self.assertEqual((mid, home, away), ("AAA", 99, 89))
        self.assertEqual(str(changes["odd_1_ft"]), "2.10")
        self.assertEqual(str(changes["lay_odd_1_ft"]), "2.12")
        self.assertEqual(changes["bookie_odd_1_ft"], "bet365")
        self.assertNotIn("mandante", changes)

    def test_respeita_vinculos_existentes_sem_inventar_nomes(self):
        preview_clubs = [
            {"original": "Chapecoense-SC", "clube_id": None, "padronizado": "Chapecoense-SC"},
            {"original": "Corinthians", "clube_id": 89, "padronizado": "Corinthians"},
        ]
        remembered = {"Chapecoense-SC":
                      {"clube_id": 99, "padronizado": "Chapecoense"}}
        result = sync.resolve_clubs(preview_clubs, remembered)
        self.assertEqual(result[0]["clube_id"], 99)
        self.assertEqual(result[0]["padronizado"], "Chapecoense")
        self.assertEqual(result[1]["clube_id"], 89)

    def test_nao_abre_banco_sem_secrets(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(sync.run(), 2)

    def test_sql_atualiza_so_cotacao_que_mudou(self):
        cur = MagicMock()
        cur.rowcount = 1
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur

        @contextmanager
        def fake_conn():
            yield conn

        with patch.object(sync, "get_conn", fake_conn):
            count = sync.update_existing(
                "2026",
                [("AAA", 99, 89, {"odd_1_ft": 2.0, "lay_odd_1_ft": 2.02})],
                {"odd_1_ft", "lay_odd_1_ft"},
            )
        self.assertEqual(count, 1)
        self.assertEqual(cur.execute.call_count, 1)
        self.assertEqual(cur.execute.call_args.args[1],
                         [2.0, 2.02, sync.SOURCE_HOST, "2026",
                          "AAA", 99, 89, 2.0, 2.02])
        conn.commit.assert_called_once()
