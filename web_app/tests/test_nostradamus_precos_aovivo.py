"""Testes determinísticos da precificação estimada, sem resultado final na entrada."""
from unittest import TestCase

import queries_nostradamus_precos_aovivo as model


def row(home=2,away=0,with_market=True):
    return {
        "gols_casa_minuto":home,"gols_fora_minuto":away,
        "api_odd_1_ft":1.55 if with_market else None,
        "api_odd_2_ft":4.9 if with_market else None,
        "api_over_ft_2_5":1.85 if with_market else None,
        "api_under_ft_2_5":2.1 if with_market else None
    }


class TestEstimativaAoVivo(TestCase):
    def test_lay_empate_em_desvantagem_de_dois_gols(self):
        odd,source,event=model.cotar(row(),60,"lay_empate")
        self.assertGreater(odd,1.01)
        self.assertLess(odd,1.6)
        self.assertEqual(source,"modelo_poisson_ou_1x2")
        self.assertGreater(event,0)
        self.assertLess(event,1)
        # Equilíbrio no placar aumenta a probabilidade de empate.
        odd_draw,_,event_draw=model.cotar(row(0,0),60,"lay_empate")
        self.assertGreater(odd_draw,odd)
        self.assertGreater(event_draw,event)

    def test_modelo_nunca_acessa_gols_finais(self):
        first=row(2,0)
        first.update({"gols_casa":2,"gols_fora":0})
        second={**first,"gols_casa":4,"gols_fora":5}
        self.assertEqual(model.cotar(first,60,"lay_empate"),
                         model.cotar(second,60,"lay_empate"))

    def test_mais_tempo_para_reacao_muda_odd(self):
        at50=model.cotar(row(),50,"lay_empate")[0]
        at70=model.cotar(row(),70,"lay_empate")[0]
        self.assertLess(at70,at50)

    def test_odds_pre_jogo_calibram_estimativa_e_ausencia_nao_bloqueia(self):
        good=model.cotar(row(),60,"lay_empate")
        blank=model.cotar(row(with_market=False),60,"lay_empate")
        self.assertNotEqual(good[0],blank[0])
        self.assertEqual(blank[1],"modelo_poisson_neutro")
        self.assertGreater(blank[0],1.01)

    def test_mercados_ja_decididos_nao_recebem_preco_falso(self):
        over=model.cotar(row(home=3,away=0),60,"over_25")
        self.assertIsNone(over[0])
        self.assertEqual(over[1],"mercado_sem_cotacao")
        under=model.cotar(row(home=4,away=0),60,"under_35")
        self.assertIsNone(under[0])
        self.assertEqual(under[1],"mercado_sem_cotacao")

    def test_odds_manuais_nao_entram_no_modelo(self):
        r=row()
        odd=model.cotar(r,60,"lay_empate")[0]
        r["odd_hipotetica"]=1.11
        self.assertEqual(model.cotar(r,60,"lay_empate")[0],odd)

    def test_mercados_lay_back_e_gols_sao_modelados(self):
        r=row(1,0)
        for market in ("lay_empate","back_empate","lay_visitante","back_mandante",
                       "over_25","under_35","ambos_marcam","ambos_nao",
                       "lay_goleada_mandante","lay_1x0"):
            with self.subTest(market=market):
                odd,source,_=model.cotar(r,60,market)
                self.assertGreater(odd,1.0)
                self.assertTrue(source.startswith("modelo_poisson"))
