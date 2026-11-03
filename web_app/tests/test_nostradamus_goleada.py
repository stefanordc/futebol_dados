"""Lay goleada: margem exata de 3 gols e favorito por Match Odds."""
from datetime import date
from unittest import TestCase

import queries_nostradamus as ns
import queries_estrategias as qs


class TestLayGoleada(TestCase):
    def test_mercados_estao_no_catalogo(self):
        self.assertEqual(ns.MERCADOS["lay_goleada_favorito"],"Lay goleada favorito")
        self.assertEqual(ns.MERCADOS["lay_goleada_zebra"],"Lay goleada zebra")
        self.assertEqual(ns.MERCADOS["lay_goleada_visitante"],"Lay goleada visitante (estratégia antiga)")

    def test_favorito_mandante_perde_lay_em_vitoria_por_tres_ou_mais(self):
        market=ns._market_for_game("lay_goleada_favorito",True)
        self.assertEqual(market,"lay_goleada_mandante")
        self.assertTrue(ns._settle(market,2,0))
        self.assertTrue(ns._settle(market,2,2))
        self.assertFalse(ns._settle(market,3,0))
        self.assertFalse(ns._settle(market,5,1))

    def test_favorito_visitante_perde_lay_em_vitoria_por_tres_ou_mais(self):
        market=ns._market_for_game("lay_goleada_favorito",False)
        self.assertEqual(market,"lay_goleada_visitante")
        self.assertTrue(ns._settle(market,0,2))
        self.assertTrue(ns._settle(market,2,2))
        self.assertFalse(ns._settle(market,0,3))
        self.assertFalse(ns._settle(market,1,5))

    def test_zebra_visitante_perde_lay_se_vencer_por_tres_ou_mais(self):
        market=ns._market_for_game("lay_goleada_zebra",True)
        self.assertEqual(market,"lay_goleada_visitante")
        self.assertTrue(ns._settle(market,2,0))
        self.assertTrue(ns._settle(market,1,3))
        self.assertFalse(ns._settle(market,0,3))
        self.assertFalse(ns._settle(market,1,5))

    def test_zebra_mandante_perde_lay_se_vencer_por_tres_ou_mais(self):
        market=ns._market_for_game("lay_goleada_zebra",False)
        self.assertEqual(market,"lay_goleada_mandante")
        self.assertTrue(ns._settle(market,0,2))
        self.assertTrue(ns._settle(market,3,1))
        self.assertFalse(ns._settle(market,3,0))
        self.assertFalse(ns._settle(market,4,1))

    def test_lay_goleada_zebra_requer_classificacao_das_odds(self):
        self.assertTrue(ns._requires_favorite("lay_goleada_zebra",[]))
        with self.assertRaisesRegex(ValueError,"Match Odds"):
            ns._market_for_game("lay_goleada_zebra",None)

    def test_lay_goleada_visitante_e_fixo_no_mando(self):
        market=ns._market_for_game("lay_goleada_visitante",True)
        self.assertEqual(market,"lay_goleada_visitante")
        self.assertTrue(ns._settle(market,3,0))
        self.assertFalse(ns._settle(market,0,3))

    def test_sem_classificacao_nao_inventa_favorito(self):
        self.assertTrue(ns._requires_favorite("lay_goleada_favorito",[]))
        with self.assertRaisesRegex(ValueError,"Match Odds"):
            ns._market_for_game("lay_goleada_favorito",None)
        game={"api_odd_1_ft":None,"api_odd_2_ft":3}
        self.assertIsNone(ns._favorite_home(game))
        game={"api_odd_1_ft":2,"api_odd_2_ft":2}
        self.assertIsNone(ns._favorite_home(game))

    def test_nao_inventa_cotacao_lay_goleada(self):
        game={"api_odd_1_ft":1.7,"api_odd_2_ft":4.5}
        self.assertEqual(ns._odds_for_game(game,"lay_goleada_mandante",None),(None,None))
        self.assertEqual(ns._odds_for_game(game,"lay_goleada_visitante",None),(None,None))
        self.assertEqual(ns._odds_for_game(game,"lay_goleada_mandante",2.4),
                         (2.4,"hipotetica"))

    def test_estrategia_aceita_ambos_objetivos(self):
        # Objetivos fazem parte da lista de valores aceitos pela validação.
        for objetivo in ("lay_goleada_favorito","lay_goleada_zebra"):
            self.assertIn(objetivo,ns.MERCADOS)
