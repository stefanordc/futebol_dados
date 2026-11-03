"""Regressões do preço simulado de goleada sobre odds de Correct Score."""
from datetime import date, timedelta
from math import exp, factorial, isclose
from unittest import TestCase

import goleada_correct_score as cs
import queries_nostradamus as ns
from test_nostradamus import game, config


def synthetic(home=2.15, away=0.85, margin=1.15):
    # Odds CS inversamente proporcionais à probabilidade Poisson vezes
    # overround uniforme (que se cancela nas razões entre placares vizinhos).
    def pmf(goals, lam):
        return exp(-lam) * lam ** goals / factorial(goals)
    return tuple(1.0 / (margin * pmf(h, home) * pmf(a, away))
                 for h,a in cs.SCORE_KEYS)


def game_with_scores(game_row, odds):
    for (h,a),value in zip(cs.SCORE_KEYS,odds):
        game_row[f"api_cs_{h}_{a}"]=value
    return game_row


class TestGoleadaCorrectScore(TestCase):
    def test_recupera_gols_esperados_e_inclui_caudas_4_mais(self):
        odds=synthetic(home=2.15,away=0.85)
        result=cs.estimate_goleada_quotes(odds)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["gols_esperados_mandante"],2.15,places=2)
        self.assertAlmostEqual(result["gols_esperados_visitante"],0.85,places=2)
        self.assertEqual(result["placares_disponiveis"],16)
        self.assertGreater(result["probabilidade_mandante"],0)
        self.assertGreater(result["probabilidade_visitante"],0)
        # P(4x0) é positivo e não consta na grade CS de 0 a 3.
        tail=exp(-2.15)*2.15**4/factorial(4)*exp(-0.85)
        self.assertGreater(tail,0)
        exact_3_0=exp(-2.15)*2.15**3/factorial(3)*exp(-0.85)
        self.assertGreater(result["probabilidade_mandante"],exact_3_0+tail)
        self.assertGreater(result["back_goleada_mandante"],1.01)
        self.assertGreater(result["lay_goleada_mandante"],
                           result["back_goleada_mandante"])

    def test_escada_classic_usa_um_tick_no_lay(self):
        examples=[0.5,1/2.1,1/3.5,1/5.7,1/9.5,1/11.7,1/26,1/77,1/250]
        for p in examples:
            back,lay=cs._classic_price_pair(p)
            self.assertIsNotNone(back)
            self.assertIsNotNone(lay)
            i=cs._LADDER_CENTS.index(round(back*100))
            self.assertEqual(lay,cs._LADDER_CENTS[i+1]/100)
            self.assertLessEqual(back,1/p+0.00001)
            self.assertGreater(lay,back)
        self.assertEqual(cs._classic_price_pair(0.0005),(None,None))

    def test_nao_inventa_precos_sem_placares_suficientes(self):
        vals=list(synthetic())
        for i in range(6): vals[i]=None
        self.assertIsNone(cs.estimate_goleada_quotes(tuple(vals)))
        vals=list(synthetic())
        vals[0]="dados invalidos"
        vals[1]=float("nan")
        self.assertIsNotNone(cs.estimate_goleada_quotes(tuple(vals)))
        self.assertIsNone(cs.estimate_goleada_quotes(tuple([None]*16)))

    def test_favorito_zebra_utilizam_mesmo_modelo_e_o_lado_correto(self):
        g=game_with_scores(game(90,date.today()-timedelta(days=4)),synthetic())
        g["api_odd_1_ft"]=1.75
        g["api_odd_2_ft"]=4.2
        home=ns._market_for_game("lay_goleada_favorito",ns._favorite_home(g))
        away=ns._market_for_game("lay_goleada_zebra",ns._favorite_home(g))
        self.assertEqual((home,away),("lay_goleada_mandante","lay_goleada_visitante"))
        hodd,horigin=ns._odds_for_game(g,home,None)
        aodd,aorigin=ns._odds_for_game(g,away,None)
        self.assertEqual(horigin,aorigin)
        self.assertEqual(horigin,"modelo_cs_lay")
        self.assertGreater(hodd,1)
        self.assertGreater(aodd,1)
        # Quando o favorito é visitante, os papéis trocam sem alterar preços.
        g["api_odd_1_ft"]=4.2
        g["api_odd_2_ft"]=1.75
        self.assertEqual(ns._market_for_game("lay_goleada_favorito",ns._favorite_home(g)),away)
        self.assertEqual(ns._market_for_game("lay_goleada_zebra",ns._favorite_home(g)),home)

    def test_quatro_cotacoes_ficam_disponiveis_em_filtro_e_objetivo(self):
        g=game_with_scores(game(91,date.today()-timedelta(days=4)),synthetic())
        prices=ns._model_cs_quotes(g)
        for market in ("back_goleada_mandante","back_goleada_visitante",
                       "lay_goleada_mandante","lay_goleada_visitante"):
            odd,origin=ns._odds_for_game(g,market,None)
            self.assertEqual(odd,prices[market])
            self.assertEqual(origin,"modelo_cs_lay" if market.startswith("lay_")
                             else "modelo_cs_back")
            self.assertIn(market,ns.MERCADOS)
            self.assertIn(market,ns.ODD_FILTER_MARKETS)
        self.assertEqual(ns._odds_for_game(g,"lay_goleada_visitante",3.7),
                         (3.7,"hipotetica"))
        self.assertTrue(ns._settle("back_goleada_mandante",3,0))
        self.assertFalse(ns._settle("back_goleada_mandante",2,0))
        self.assertTrue(ns._settle("back_goleada_visitante",0,3))
        self.assertFalse(ns._settle("back_goleada_visitante",0,2))

    def test_backtest_lay_zebra_tem_odds_e_valor_financeiro(self):
        cutoff=date.today()-timedelta(days=2)
        rows=[]
        for i in range(10):
            row=game_with_scores(
                game(i,cutoff-timedelta(days=12-i),gf=3 if i%2 else 2,ga=0),
                synthetic())
            row["api_odd_1_ft"]=1.75
            row["api_odd_2_ft"]=4.2
            rows.append(row)
        result=ns.testar(config(cutoff,goal="lay_goleada_zebra"),rows=rows)
        self.assertGreater(result["total"]["entradas"],0)
        self.assertEqual(result["total"]["cotadas"],result["total"]["entradas"])
        self.assertIsNotNone(result["total"]["unidades"])
        self.assertIsNotNone(result["total"]["odd_media"])
        self.assertEqual(result["resultados"][0]["jogos"][0]["tipo_odd"],"modelo_cs_lay")
        self.assertIsNotNone(result["resultados"][0]["jogos"][0]["goleada_cs"])
