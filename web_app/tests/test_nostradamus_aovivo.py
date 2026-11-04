"""Backtest ao vivo por placar no minuto de entrada — sem cotações inventadas."""
from datetime import date
from unittest import TestCase
from unittest.mock import patch

import queries_nostradamus_aovivo as live


def config(**updates):
    base={
        "corte":"2026-10-30","minuto":60,"vencendo":"favorito",
        "diferenca_gols":2,"mercado":"lay_visitante",
        "odd_hipotetica":3.0,"campeonato_ids":[],
    }
    base.update(updates)
    return base


def partida(identifier,fav_home,h60,a60,final_home,final_away,day="2026-10-01"):
    return {
        "id":identifier,"data":date.fromisoformat(day),"campeonato_id":1,
        "campeonato":"Liga Teste","mandante":"Casa","visitante":"Fora",
        "gols_casa_minuto":h60,"gols_fora_minuto":a60,
        "gols_casa":final_home,"gols_fora":final_away,
        "api_odd_1_ft":1.5 if fav_home else 4.0,
        "api_odd_2_ft":4.0 if fav_home else 1.5,
    }


class TestAoVivo(TestCase):
    def test_favorito_vencendo_por_dois_aos_60_e_lay_visitante(self):
        rows=[
            partida(1,True,2,0,2,1),   # Lay visitante é green.
            partida(2,False,0,2,0,3),  # Favorito visitante: Lay visitante é red.
            partida(3,True,1,0,2,1),   # Diferença de apenas 1 no minuto.
            partida(4,True,2,0,3,2,day="2026-11-01"),  # Fora do corte.
        ]
        result=live.simular(config(),rows=rows)
        total=result["total"]
        self.assertEqual(result["entradas"],2)
        self.assertEqual((total["greens"],total["reds"]),(1,1))
        self.assertEqual(total["win_rate"],50.0)
        self.assertEqual(total["valor_reais"],-52.25)
        self.assertEqual([d["placar_minuto"] for d in result["detalhes"]],["2x0","0x2"])
        self.assertEqual([d["green"] for d in result["detalhes"]],[True,False])
        self.assertEqual([d["mercado"] for d in result["detalhes"]],["lay_visitante"]*2)

    def test_placar_exato_gols_favorito_zebra_total_mandante_visitante(self):
        rows=[partida(1,True,2,0,3,1),partida(2,False,0,2,0,3)]
        result=live.simular(config(gols_total=2,gols_favorito=2,gols_zebra=0,
            gols_mandante=2,gols_visitante=0),rows=rows)
        self.assertEqual(result["entradas"],1)
        self.assertEqual(result["detalhes"][0]["id"],1)
        self.assertEqual(result["detalhes"][0]["placar_final"],"3x1")

    def test_sem_odd_manual_modela_cotacao_e_calcula_financeiro(self):
        rows=[partida(1,True,2,0,2,1)]
        result=live.simular(config(odd_hipotetica=None),rows=rows)
        self.assertEqual(result["total"]["greens"],1)
        self.assertIsNotNone(result["total"]["valor_reais"])
        self.assertGreater(result["detalhes"][0]["odd"],1.0)
        self.assertIsNotNone(result["detalhes"][0]["valor_reais"])
        self.assertTrue(result["detalhes"][0]["cotacao"].startswith("modelo_poisson"))
        self.assertTrue(result["odd_automatica"])
        self.assertEqual(result["cotadas_modeladas"],1)
        self.assertIn("Não há odds in-play históricas",result["aviso"])

    def test_modelo_lay_empate_diferencia_placares_e_minutos(self):
        rows=[
            partida(1,True,2,0,2,1),
            partida(2,True,1,0,2,1),
        ]
        out=live.simular(config(odd_hipotetica=None,mercado="lay_empate",
                               vencendo="qualquer",diferenca_gols=None),rows=rows)
        self.assertEqual(out["entradas"],2)
        p={g["id"]:g["odd"] for g in out["detalhes"]}
        self.assertGreater(p[1],p[2], "Lay empate tem odd maior quando o empate é menos provável")
        self.assertEqual(out["total"]["cotadas"],2)
        later=live.simular(config(odd_hipotetica=None,mercado="lay_empate",
                                 minuto=75,vencendo="qualquer",diferenca_gols=None),rows=rows)
        self.assertGreater(later["detalhes"][0]["odd"],p[1])

    def test_em_qualquer_placar_aceita_empate_com_gap_zero(self):
        rows=[partida(1,True,0,0,1,1),
              partida(2,False,0,2,0,3)]
        result=live.simular(config(vencendo="empate",diferenca_gols=0,
            mercado="lay_empate",odd_hipotetica=2.2),rows=rows)
        self.assertEqual(result["entradas"],1)
        self.assertEqual(result["detalhes"][0]["id"],1)
        self.assertFalse(result["detalhes"][0]["green"])

    def test_nao_inventa_favorito_quando_odds_faltam(self):
        row=partida(1,True,2,0,3,0)
        row["api_odd_1_ft"]=None
        row["api_odd_2_ft"]=None
        self.assertEqual(live.simular(config(),rows=[row])["entradas"],0)
        result=live.simular(config(vencendo="mandante",mercado="lay_visitante"),rows=[row])
        self.assertEqual(result["entradas"],1)

    def test_valida_minuto_placar_e_odd_e_diferenca(self):
        invalid=[
            ({"minuto":0},"minuto"),
            ({"minuto":91},"minuto"),
            ({"minuto":60.5},"minuto"),
            ({"diferenca_gols":-1},"Diferença"),
            ({"gols_total":3.5},"Total"),
            ({"vencendo":"empate","diferenca_gols":2},"empate"),
            ({"mercado":"inexistente"},"mercado"),
            ({"odd_hipotetica":1.0},"Odd"),
        ]
        for altered,error in invalid:
            with self.subTest(altered=altered):
                with self.assertRaisesRegex(ValueError,error):
                    live.simular(config(**altered),rows=[])

    def test_nao_consulta_banco_quando_rows_fornecidas(self):
        with patch.object(live,"fetch_all",side_effect=AssertionError("consulta inesperada")):
            self.assertEqual(live.simular(config(),rows=[])["entradas"],0)

    def test_minimo_maximo_gols_de_cada_equipe_e_multiplas_ligas(self):
        rows=[
            partida(1,True,2,0,2,1),
            partida(2,False,0,2,0,3),
            partida(3,True,3,1,3,2),
            {**partida(4,True,2,0,2,1),"campeonato_id":2},
        ]
        result=live.simular(config(
            vencendo="qualquer",diferenca_gols=None,campeonato_ids=[1,2],
            gols_favorito_min=2,gols_favorito_max=2,
            gols_zebra_min=0,gols_zebra_max=0,
            gols_mandante_min=0,gols_mandante_max=2,
            gols_visitante_min=0,gols_visitante_max=2),rows=rows)
        self.assertEqual([item["id"] for item in result["detalhes"]],[1,2,4])
        one=live.simular(config(
            campeonato_ids=[2],gols_favorito_min=2,gols_zebra_max=0),rows=rows)
        self.assertEqual([item["id"] for item in one["detalhes"]],[4])

    def test_minimos_maximos_invalidos_e_mais_de_dez_condicoes(self):
        for values in (
            {"gols_mandante_min":3,"gols_mandante_max":2},
            {"gols_favorito_min":3,"gols_favorito_max":1},
            {"gols_zebra_max":-1},
            {"gols_visitante_min":2.5},
            {"condicoes":[{"metrica":"xg","comparador":"gt"}]*11},
            {"jogos":"3"},
        ):
            with self.subTest(values=values),self.assertRaises(ValueError):
                live.simular(config(**values),rows=[])

    def test_condicoes_pre_jogo_usam_historico_anterior_e_mesmo_editor(self):
        def past(identifier,day,home=2,away=0):
            return {
                "id":identifier,"data":date.fromisoformat(day),
                "temporada":"2026/2027","campeonato_id":1,
                "casa_id":1,"fora_id":2,"gols_casa":home,"gols_fora":away,
                "api_odd_1_ft":1.5,"api_odd_2_ft":4.0,
                "home_xg":1.8,"away_xg":0.5
            }
        history=[past(i,"2026-10-"+str(1+i).zfill(2)) for i in range(5)]
        history.append(past(99,"2026-10-10",3,1))
        live_row=partida(99,True,2,0,3,1,day="2026-10-10")
        rule={"lado":"favorito","mando_preferido":"mandante",
              "metrica":"gols_feitos","comparador":"ge",
              "referencia":"valor","valor":2}
        result=live.simular(config(condicoes=[rule]),rows=[live_row],history_rows=history)
        self.assertEqual(result["entradas"],1)
        self.assertEqual(result["detalhes"][0]["condicoes"][0]["observado"],2)
        # Um jogo no mesmo dia não pode completar o mínimo de 5 jogos prévios.
        result=live.simular(config(condicoes=[rule]),rows=[live_row],
            history_rows=history[:4]+[past(98,"2026-10-10",2,0),history[-1]])
        self.assertEqual(result["entradas"],0)
        wrong={**rule,"valor":3}
        result=live.simular(config(condicoes=[wrong]),rows=[live_row],history_rows=history)
        self.assertEqual(result["entradas"],0)

    def test_ia_separa_treino_cronologico_e_validacao_sem_otimismo_futuro(self):
        from unittest.mock import patch
        import queries_nostradamus_ai as ai
        candidates=[]
        for i in range(20):
            stats={"xg":2.0 if i<7 else 0.4}
            candidates.append({
                "id":i+1,"data":"2026-10-"+str(i+1).zfill(2),
                "partida":{"api_odd_1_ft":1.5,"api_odd_2_ft":4.0},
                "stats_casa":stats,"stats_fora":stats,
                "favorito_casa":True,
                "unidades":0.95 if i<7 else -1.0,
                "passes_initial":True
            })
        proposed={
            "tipo":"indicador","lado":"favorito","mando_preferido":"indiferente",
            "metrica":"xg","comparador":"ge","referencia":"valor","valor":1.5
        }
        with patch.object(live,"simular",return_value={"_dados_otimizacao":candidates}), \
             patch.object(ai,"_proposals",return_value=[proposed]):
            outcome=live.analisar(config(condicoes=[]))
        self.assertEqual(outcome["sugestoes"][0]["acao"],"adicionar")
        self.assertEqual(outcome["base_treino"]["entradas"],13)
        self.assertEqual(outcome["base_validacao"]["entradas"],7)
        self.assertEqual(outcome["sugestoes"][0]["avaliacao"],"Sem confirmação na validação")
        self.assertEqual(outcome["data_divisao"],"2026-10-13")

    def test_lay_empate_com_odd_hipotetica_apura_financeiro(self):
        rows=[partida(1,True,2,0,2,1),partida(2,True,2,0,2,2)]
        result=live.simular(config(mercado="lay_empate",odd_hipotetica=2.0),rows=rows)
        self.assertEqual((result["total"]["greens"],result["total"]["reds"]),(1,1))
        self.assertEqual(result["total"]["valor_reais"],-4.5)
        self.assertEqual(result["total"]["cotadas"],2)

    def test_salvar_cenario_privado_confirma_depois_do_commit(self):
        from contextlib import contextmanager
        from unittest.mock import MagicMock
        conn=MagicMock()
        cur=conn.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value={
            "id":7,"nome":"Lay empate 60","versao":1,
            "configuracao":config()
        }
        @contextmanager
        def fake():yield conn
        with patch.object(live,"get_conn",fake):
            saved=live.criar_cenario({**config(),"nome":"Lay empate 60"})
        self.assertEqual(saved["id"],7)
        sql,args=cur.execute.call_args.args
        self.assertIn("INSERT INTO nostradamus_private.estrategias_ao_vivo",sql)
        self.assertEqual(args[0],"Lay empate 60")
        self.assertEqual(args[1].adapted["campeonato_ids"],[])
        self.assertEqual(args[1].adapted["corte"],"2026-10-30")
        conn.commit.assert_called_once()

    def test_editar_cenario_exige_versao_e_exclusao_e_separada(self):
        from contextlib import contextmanager
        from unittest.mock import MagicMock
        conn=MagicMock()
        cur=conn.cursor.return_value.__enter__.return_value
        cur.fetchone.side_effect=[
            {"id":7,"nome":"Editado","versao":2},
            {"id":7,"nome":"Editado"}
        ]
        @contextmanager
        def fake():yield conn
        with patch.object(live,"get_conn",fake):
            saved=live.editar_cenario(7,{**config(),"nome":"Editado","versao":1})
            deleted=live.excluir_cenario(7,2)
        self.assertEqual(saved["versao"],2)
        self.assertTrue(deleted["excluido"])
        self.assertEqual(conn.commit.call_count,2)
        self.assertIn("DELETE FROM nostradamus_private.estrategias_ao_vivo",
                      cur.execute.call_args.args[0])
        with self.assertRaisesRegex(ValueError,"Versão inválida"):
            live.editar_cenario(7,{**config(),"nome":"Editado"})
        with self.assertRaises(ValueError):
            live.excluir_cenario(7,True)

    def test_sql_exige_gols_auditaveis_e_odds_pareadas(self):
        self.assertIn("g.gols_casa_conferidos=j.gols_casa",live.SQL)
        self.assertIn("g.gols_fora_conferidos=j.gols_fora",live.SQL)
        self.assertIn("f.foi_gol_contra=true",live.SQL)
        self.assertIn("f.minuto+COALESCE(f.minuto_adicional,0)",live.SQL)
        self.assertIn("HAVING COUNT(*)=1",live.SQL)
        self.assertIn("j.data<CURRENT_DATE",live.SQL)
