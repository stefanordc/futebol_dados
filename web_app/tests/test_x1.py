"""Testes sem PostgreSQL para o módulo x1 (dados simulados)."""
import unittest
from unittest.mock import patch

import queries_x1


def fake_fetch(sql, params):
    if "SELECT c.id,c.nome" in sql:
        return [{"id": 10, "nome": "Liga Exemplo", "pais": "Exemplo",
                 "temporada": "2026/2027", "jogos": 36}]
    if "SELECT c.id,c.clube" in sql:
        return [{"id": 1, "clube": "Mandante", "fotmob_id": 100},
                {"id": 2, "clube": "Visitante", "fotmob_id": 200}]
    if "SELECT DISTINCT temporada FROM jogos" in sql:
        return [{"temporada": "2026/2027"}]
    if "SELECT id, temporada, data, casa_id" in sql:
        return [
            {"id": i+1, "temporada": "2026/2027", "data": "2026-10-01",
             "casa_id": 1 if i % 2 == 0 else 2,
             "fora_id": 2 if i % 2 == 0 else 1,
             "gols_casa": (i*3) % 4, "gols_fora": (i+1) % 3}
            for i in range(36)
        ]
    if "FROM estatisticas e JOIN jogos j" in sql:
        return [
            {"clube_id": 1, "jogos": 18, "xg": 1.8, "bola_parada": 0.15,
             "chutes": 14, "chutes_certos": 5, "chances": 3.2,
             "passes": 450, "desarmes": 12, "interceptacoes": 11,
             "bloqueios": 4, "aereas_ganhas": 9, "aereas": 17,
             "gols": 1.8, "sofridos": 1.2, "clean_sheets": 0.3},
            {"clube_id": 2, "jogos": 18, "xg": 1.2, "bola_parada": 0.08,
             "chutes": 10, "chutes_certos": 3, "chances": 2,
             "passes": 390, "desarmes": 14, "interceptacoes": 13,
             "bloqueios": 5, "aereas_ganhas": 8, "aereas": 18,
             "gols": 1.1, "sofridos": 1.7, "clean_sheets": 0.2},
        ]
    raise AssertionError("Consulta não reconhecida: "+sql[:140])


class TestX1(unittest.TestCase):
    def test_poisson_placares(self):
        probs, scores = queries_x1._markets(1.5, 1.2)
        self.assertAlmostEqual(probs["mandante"]+probs["empate"]+probs["visitante"], 1, places=6)
        self.assertAlmostEqual(sum(row["probabilidade"] for row in scores), 1, delta=0.00005)
        self.assertAlmostEqual(probs["over_25"]+probs["under_35"],
                               1-probs["over_35"]+probs["over_25"], places=6)
        self.assertGreater(probs["over_05_ft"], probs["over_15"])
        self.assertGreater(probs["over_15"], probs["over_25"])
        self.assertGreater(probs["mandante_ou_empate"], probs["mandante"])
        self.assertGreater(probs["visitante_ou_empate"], probs["visitante"])

    def test_odds_break_even(self):
        p,_ = queries_x1._markets(1.3, 1.1)
        odds=queries_x1._odds(p)
        self.assertAlmostEqual(odds["mandante"]["odd_justa"],1/p["mandante"],places=2)
        self.assertEqual(odds["lay_mandante"]["sentido"],"maxima")
        self.assertEqual(odds["mandante"]["sentido"],"minima")
        self.assertGreater(odds["mandante"]["limite_odd_ev_3pct"],odds["mandante"]["odd_justa"])
        self.assertLess(odds["lay_mandante"]["limite_odd_ev_3pct"],odds["lay_mandante"]["odd_justa"])

    @patch("queries_x1.fetch_all", side_effect=fake_fetch)
    def test_full_analysis(self, _fetch):
        result=queries_x1.avaliar(10,1,2,"2026/2027")
        self.assertEqual(result["campeonato"]["id"],10)
        self.assertEqual(result["mandante"]["clube"],"Mandante")
        self.assertEqual(result["visitante"]["clube"],"Visitante")
        self.assertEqual(result["modelo"]["amostra_jogos"],36)
        self.assertEqual(len(result["relatorio"]),2)
        self.assertTrue(0<result["probabilidades"]["ambos_marcam"]<1)

    def test_same_team_rejected(self):
        with self.assertRaises(ValueError):
            queries_x1.avaliar(10,1,1)


if __name__=="__main__":
    unittest.main()
