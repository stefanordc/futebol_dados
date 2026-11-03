"""Validação do assistente quantitativo sem banco, sem API e sem dados futuros."""
from __future__ import annotations
from datetime import date,timedelta
from unittest import TestCase
from unittest.mock import patch
import queries_nostradamus as ns
import queries_nostradamus_ai as ai


def sample(outcome_flipped=False):
    cutoff=date.today()-timedelta(days=2)
    start=cutoff-timedelta(days=61)
    rows=[]
    for i in range(50):
        # As primeiras 5 partidas servem somente para construir o histórico.
        lost=i%4==0
        if outcome_flipped and i>=36:
            lost=not lost
        odd=1.20 if i%4==0 else 2.10
        rows.append({
            "id":i+1, "data":start+timedelta(days=i),
            "temporada":"2025/2026","campeonato_id":1,
            "campeonato":"Liga Teste","casa_id":1,"fora_id":2,
            "mandante":"Clube A","visitante":"Clube B",
            "gols_casa":0 if lost else 2,
            "gols_fora":1 if lost else 0,
            "api_odd_1_ft":odd,"api_odd_2_ft":4.5,
            "api_over_ft_2_5":2.4 if i%4==0 else 1.8,
            "home_xg":1.5,"away_xg":0.7,
            "home_chutes_certos":5,"away_chutes_certos":3,
            "home_escanteios":6,"away_escanteios":2,
            "home_chutes":12,"away_chutes":7,
            "home_passes_certos":310,"away_passes_certos":230,
        })
    return rows,cutoff


def config(cutoff):
    return {
        "corte":cutoff.isoformat(),"jogos":"20",
        "objetivo":"back_mandante","campeonato_ids":[1],
        "condicoes":[{"lado":"favorito","mando_preferido":"indiferente",
                      "metrica":"pontos_jogo","comparador":"ge",
                      "referencia":"valor","valor":0}],
        "odd_hipotetica":None,
    }


class TestNostradamusAI(TestCase):
    def test_treino_anterior_e_validacao_posterior_com_corte_preservado(self):
        rows,cutoff=sample()
        result=ai.analisar(config(cutoff),rows)
        self.assertEqual(result["corte"],cutoff.isoformat())
        self.assertTrue(result["data_divisao"]<cutoff.isoformat())
        self.assertGreaterEqual(result["base_treino"]["entradas"],8)
        self.assertGreaterEqual(result["base_validacao"]["entradas"],5)
        self.assertEqual(result["base_treino"]["entradas"]+
                         result["base_validacao"]["entradas"],45)
        self.assertLessEqual(len(result["sugestoes"]),3)
        for suggestion in result["sugestoes"]:
            self.assertIn(suggestion["condicao"]["tipo"],("odd","indicador"))
            self.assertIn("validacao",suggestion)
            self.assertIn("treino",suggestion)
            self.assertNotIn("resultado_garantido",suggestion)
            self.assertGreater(suggestion["treino"]["media_reais"],
                               result["base_treino"]["media_reais"])
            ns._valid_conditions([suggestion["condicao"]])

    def test_alterar_resultado_do_futuro_nao_muda_as_regras_treinadas(self):
        before,cutoff=sample()
        after,_=sample(outcome_flipped=True)
        original=ai.analisar(config(cutoff),before)
        modified=ai.analisar(config(cutoff),after)
        self.assertEqual(
            [s["condicao"] for s in original["sugestoes"]],
            [s["condicao"] for s in modified["sugestoes"]],
        )
        self.assertNotEqual(original["base_validacao"]["total_reais"],
                            modified["base_validacao"]["total_reais"])

    def test_tambem_pode_sugerir_remover_regra_que_prejudica_resultado(self):
        rows, cutoff=sample()
        payload=config(cutoff)
        payload["condicoes"].append({
            "lado":"favorito","mando_preferido":"indiferente",
            "metrica":"gols_feitos","comparador":"ge",
            "referencia":"valor","valor":0,
        })
        # A regra adicional restringe o universo e deve ser reavaliada
        # exclusivamente com os mesmos dados e a mesma data de corte.
        original_testar=ns.testar
        calls=[]
        def monitor(config_,rows=None,capture=False):
            calls.append((config_["corte"],len(config_["condicoes"]),rows is not None))
            return original_testar(config_,rows=rows,capture=capture)
        with patch.object(ns,"testar",side_effect=monitor):
            result=ai.analisar(payload,rows)
        self.assertTrue(all(day==cutoff.isoformat() for day,_,_ in calls))
        self.assertTrue(any(count==1 for _,count,_ in calls))
        self.assertTrue(all(with_rows for _,_,with_rows in calls))
        for suggestion in result["sugestoes"]:
            self.assertIn(suggestion["acao"],("adicionar","remover"))
            if suggestion["acao"]=="remover":
                self.assertIn(suggestion["indice"],(0,1))
                self.assertIsNone(suggestion["condicao"])
            else:
                self.assertIsNotNone(suggestion["condicao"])

    def test_remocao_elegivel_nao_exige_espaco_para_adicionar(self):
        rows, cutoff=sample()
        payload=config(cutoff)
        payload["condicoes"]=payload["condicoes"]*10
        result=ai.analisar(payload,rows)
        self.assertIn("sugestoes",result)
        self.assertEqual(result["corte"],cutoff.isoformat())
        self.assertTrue(all(s["acao"]=="remover" for s in result["sugestoes"]))

    def test_sem_odds_nao_gera_lucros_ficticios(self):
        rows,cutoff=sample()
        for row in rows:
            row["api_odd_1_ft"]=None
        result=ai.analisar(config(cutoff),rows)
        self.assertEqual(result["sugestoes"],[])
        self.assertIn("Amostra insuficiente",result["mensagem"])

    def test_analise_usa_mesma_data_e_nao_reconsulta_dados(self):
        rows,cutoff=sample()
        with patch.object(ns,"fetch_all",side_effect=AssertionError("SQL inesperado")):
            result=ai.analisar(config(cutoff),rows)
        self.assertEqual(result["corte"],cutoff.isoformat())

    def test_poucas_condicoes_ou_datas_invalida(self):
        rows,cutoff=sample()
        many=config(cutoff)
        many["condicoes"]=many["condicoes"]*10
        result=ai.analisar(many,rows)
        self.assertEqual(result["sugestoes"],[])
        self.assertIn("Limite de 10",result["mensagem"])
        invalid=config(cutoff)
        invalid["corte"]="3000-01-01"
        with self.assertRaises(ValueError):
            ai.analisar(invalid,rows)

    def test_mercados_odd_nao_usa_cotacao_hipotetica(self):
        rows,cutoff=sample()
        row={"partida":rows[0],"favorito_casa":True,
             "stats_casa":{},"stats_fora":{}}
        self.assertEqual(ai._odd(row,"back_favorito"),1.20)
        self.assertEqual(ai._odd(row,"over_25"),2.4)
        self.assertIsNone(ai._odd(row,"lay_favorito"))
        self.assertTrue(ai._passes(row,{"tipo":"odd","mercado":"back_favorito",
                                        "odd_min":1.20,"odd_max":None}))
        self.assertFalse(ai._passes(row,{"tipo":"odd","mercado":"back_favorito",
                                         "odd_min":2.00,"odd_max":None}))
