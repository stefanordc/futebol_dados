"""Testes da integração dados_fisicos com IDs internos e externos.

Testes unitários sem acesso ao banco: protegem os mapeamentos e filtros SQL.
"""
import unittest
from unittest.mock import patch
import queries_dados_fisicos as fisicos
import queries_x1


class TestCampeonatos(unittest.TestCase):
    def tearDown(self):
        fisicos._campeonato_origem.cache_clear()

    @patch.object(fisicos, "fetch_all")
    @patch.object(fisicos, "fetch_one")
    def test_laliga_busca_espanhol_por_pais_e_nome(self, one, all_rows):
        fisicos._campeonato_origem.cache_clear()
        one.return_value = {"nome":"LaLiga","pais":"Espanha","id_sofascore":None}
        all_rows.return_value = [{"id_campeonato":8}]
        self.assertEqual(fisicos._campeonato_origem(1),8)
        self.assertEqual(all_rows.call_args.args[1],("Espanhol","Espanha"))

    @patch.object(fisicos, "fetch_all")
    @patch.object(fisicos, "fetch_one")
    def test_serie_a_e_premier_league(self, one, all_rows):
        for id, name, country, from_name, source_id in [
            (3, "Serie A", "Itália", "Italiano", 23),
            (5, "Premier League", "Inglaterra", "Inglês", 17),
            (6, "Brasileiro", "Brasil", "Brasileiro", 325),
        ]:
            fisicos._campeonato_origem.cache_clear()
            one.return_value = {"nome":name,"pais":country,"id_sofascore":None}
            all_rows.return_value = [{"id_campeonato":source_id}]
            self.assertEqual(fisicos._campeonato_origem(id),source_id)
            self.assertEqual(all_rows.call_args.args[1],(from_name,country))

    @patch.object(fisicos, "fetch_all")
    @patch.object(fisicos, "fetch_one")
    def test_identificador_sofascore_direto(self, one, all_rows):
        fisicos._campeonato_origem.cache_clear()
        one.return_value = {"nome":"Espanhol","pais":"Espanha","id_sofascore":8}
        self.assertEqual(fisicos._campeonato_origem(2),8)
        all_rows.assert_not_called()

    @patch.object(fisicos, "fetch_all")
    @patch.object(fisicos, "fetch_one")
    def test_ambiguo_nao_mapeia(self, one, all_rows):
        fisicos._campeonato_origem.cache_clear()
        one.return_value = {"nome":"Brasileiro","pais":"Brasil","id_sofascore":None}
        all_rows.return_value = [{"id_campeonato":325},{"id_campeonato":326}]
        self.assertIsNone(fisicos._campeonato_origem(6))

    @patch.object(fisicos,"_campeonato_origem",return_value=325)
    @patch.object(fisicos,"fetch_all")
    def test_consulta_usa_temporada_e_id_fisico_e_participacao(self, fetch, mapped):
        fetch.return_value=[{
          "clube_id":88,"clube":"Flamengo",
          "jogos_fisico":32,"avg_distancia_percorrida":96.74,
          "avg_sprints":110.125,"jogos_km":32,"jogos_sprints":32,
          "jogos_mais_km":0,"vit_mais_km":0,
          "jogos_mais_sprints":0,"vit_mais_sprints":0
        }]
        by_id,by_name=fisicos.fisicos_lookup("2026",campeonato_id=6)
        self.assertEqual(by_id[88]["jogos_km"],32)
        self.assertEqual(by_id[88]["avg_sprints"],110.125)
        self.assertIsNone(by_id[88]["avg_pct_vit_mais_km"])
        self.assertTrue(by_name)
        query, args=fetch.call_args.args
        self.assertEqual(args,["2026",325,6,"2026"])
        self.assertIn("f.id_campeonato = %s",query)
        self.assertIn("jj.campeonato_id = %s",query)
        self.assertIn("COALESCE(cf.clube_id, pelo_nome.clube_id)",query)
        self.assertIn("LEFT JOIN jogos j", query)

    @patch.object(fisicos, "_campeonato_origem", return_value=None)
    @patch.object(fisicos, "fetch_all")
    def test_mapeamento_nao_existe_sem_consulta(self, fetch, mapped):
        self.assertEqual(fisicos.fisicos_lookup("2026",campeonato_id=98),({},{}))
        fetch.assert_not_called()


class TestAjusteX1(unittest.TestCase):
    @patch("queries_dados_fisicos.fisicos_lookup")
    def test_ajuste_limitado_e_nao_inventa_amostras(self, lookup):
        clubs = {
            i: {
              "jogos_km":12,"jogos_sprints":12,
              "avg_distancia_percorrida":float(90+i*6),
              "avg_sprints":float(90+i*10),
            } for i in (1,2,3,4)
        }
        lookup.return_value=(clubs,{})
        effect=queries_x1._physical_adjustment(6,"2026",1,4)
        self.assertTrue(effect["aplicado"])
        self.assertGreater(effect["fator_visitante"],1)
        self.assertLess(effect["fator_mandante"],1)
        self.assertTrue(.959<=effect["fator_mandante"]<=1.041)
        self.assertTrue(.959<=effect["fator_visitante"]<=1.041)

        clubs[1]["jogos_km"]=2
        lookup.return_value=(clubs,{})
        neutral=queries_x1._physical_adjustment(6,"2026",1,4)
        self.assertFalse(neutral["aplicado"])
        self.assertEqual(neutral["fator_mandante"],1.0)


if __name__=="__main__":
    unittest.main()
