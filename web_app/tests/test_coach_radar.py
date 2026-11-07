"""Novo radar do técnico: um único agregado por temporada/clube/liga."""
import unittest
from decimal import Decimal
from unittest.mock import patch

import queries_coach_radar as radar


class CoachRadarTests(unittest.TestCase):
    def test_uma_consulta_so_com_jogos_do_tecnico(self):
        payload = {
            "jogos": 11, "gols_marcados": 16,
            "gols_sofridos": 21, "clean_sheets": 2,
            "vitorias": 2, "empates": 4,
            "finalizacoes": 133, "jogos_finalizacoes": 11,
            "xg": Decimal("14.39"), "jogos_xg": 11,
            "grandes_chances": 23, "jogos_chances": 11,
            "bloqueios": 37, "jogos_bloqueios": 11,
            "interceptacoes": 84, "jogos_interceptacoes": 11,
            "passes_certos": 3431, "jogos_passes": 11,
        }
        with patch.object(radar, "fetch_one", return_value=payload) as fetch:
            result = radar.radar_tecnico(8, "2026/2027")
        fetch.assert_called_once()
        sql, args = fetch.call_args.args
        self.assertEqual(args, ("2026/2027", 8, "2026/2027", 8))
        self.assertIn("j.tecnico_casa_id = %s", sql)
        self.assertIn("j.tecnico_fora_id = %s", sql)
        self.assertIn("e.periodo = 'Completo'", sql)
        self.assertNotIn("SELECT * FROM jogos", sql)
        self.assertEqual(result["jogos"], 11)
        self.assertEqual(result["metricas"]["xg"], 14.39)
        self.assertIsNone(result["aviso"])

    def test_filtros_respeitam_campeonato_e_clube(self):
        with patch.object(radar, "fetch_one", return_value={"jogos": 4}) as fetch:
            result = radar.radar_tecnico(8, "2026/2027", campeonato_id=7, clube_id=92)
        sql, args = fetch.call_args.args
        self.assertIn("p.campeonato_id = %s", sql)
        self.assertIn("p.clube_id = %s", sql)
        self.assertEqual(args, ("2026/2027", 8, "2026/2027", 8, 7, 92))
        self.assertEqual(result["jogos"], 4)
        self.assertIn("Menos de cinco", result["aviso"])

    def test_sem_partidas_nao_finge_estatisticas(self):
        with patch.object(radar, "fetch_one", return_value={
            "jogos": 0, "gols_marcados": None, "gols_sofridos": None
        }):
            result = radar.radar_tecnico(8, "2026/2027")
        self.assertEqual(result["jogos"], 0)
        self.assertIsNone(result["metricas"]["gols_marcados"])
        self.assertIn("Não há jogos", result["aviso"])

    def test_dados_ausentes_nao_viram_zero(self):
        with patch.object(radar, "fetch_one", return_value={
            "jogos": 3, "finalizacoes": None, "jogos_finalizacoes": 0
        }):
            result = radar.radar_tecnico(8, "2026/2027")
        self.assertIsNone(result["metricas"]["finalizacoes"])
        self.assertEqual(result["metricas"]["jogos_finalizacoes"], 0)

    def test_parametros_invalidos_antes_do_banco(self):
        with patch.object(radar, "fetch_one") as fetch:
            for fn in (
                lambda: radar.radar_tecnico(-3, "2026/2027"),
                lambda: radar.radar_tecnico(8, ""),
                lambda: radar.radar_tecnico(8, "2026/2027", clube_id=-1),
                lambda: radar.radar_tecnico(8, "2026/2027", campeonato_id=0),
            ):
                with self.assertRaises(ValueError):
                    fn()
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
