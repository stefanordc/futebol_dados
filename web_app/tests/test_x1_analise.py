"""Testes determinísticos da análise descritiva do x1 sem PostgreSQL."""
import unittest
from unittest.mock import patch
import queries_x1_analise as q


def match(i, gf, ga, xg, shots, passes):
    result={
        "id":i,"data":f"2026-10-{i:02d}","clube_id":19,"clube_nome":"Clube Teste",
        "mando":"Casa" if i%2 else "Fora","gf":gf,"ga":ga,
        "xg":xg,"total_chutes":shots,"chutes_certos":shots//2 if shots is not None else None,
        "passes_certos":passes,"posse_bola":60 if shots is not None else None
    }
    return result


class TestAnalysis(unittest.TestCase):
    def test_amostra_e_variancia(self):
        rows=[
            match(10,2,0,1.0,10,100),
            match(9,0,1,None,None,None),
            match(8,1,1,0.8,5,200),
        ]
        with patch.object(q,"_goal_types",return_value={"tipos":None,"jogos_com_mapa":0}),patch.object(q,"_physical_rows",return_value={
            10:{"km":80,"sprints":110},8:{"km":100,"sprints":130}
        }):
            result=q._team_report(rows,19,8,"2026/2027")
        m=result["metricas"]
        self.assertEqual(result["jogos"],3)
        self.assertEqual((m["vitorias"],m["empates"],m["derrotas"]),(1,1,1))
        self.assertAlmostEqual(m["variancia_saldo"],2.33333,places=4)
        self.assertEqual(m["chutes_por_gol"],5)
        self.assertAlmostEqual(m["chutes_certos_por_gol"],2.33333,places=4)
        self.assertEqual(m["passes_certos_por_gol"],100)
        self.assertEqual(m["precisao_finalizacoes_pct"],46.66667)
        self.assertAlmostEqual(m["eficiencia_xg_pct"],166.66667,places=4)
        self.assertAlmostEqual(m["gols_menos_xg"],1.2)
        self.assertEqual(m["xg_por_jogo"],0.9)
        self.assertEqual(result["cobertura"]["xg"],2)
        self.assertEqual(result["cobertura"]["passes_certos"],2)
        self.assertEqual(m["distancia_percorrida"],180)
        self.assertEqual(m["distancia_percorrida_por_jogo"],90)
        self.assertEqual(m["sprints_por_jogo"],120)
        self.assertEqual(result["cobertura"]["distancia_percorrida"],2)

    def test_sem_gol_com_xg_tem_conversao_zero(self):
        with patch.object(q,"_goal_types",return_value={"tipos":None,"jogos_com_mapa":0}),patch.object(q,"_physical_rows",return_value={}):
            result=q._team_report([match(11,0,2,1.2,12,140)],19,8,"2026/2027")
        self.assertEqual(result["metricas"]["eficiencia_xg_pct"],0)
        self.assertEqual(result["metricas"]["conversao_chutes_pct"],0)
        self.assertIsNone(result["metricas"]["chutes_por_gol"])
        self.assertIsNone(result["metricas"]["variancia_saldo"])

    def test_dados_ausentes_nao_viram_zero(self):
        rows=[match(1,1,0,None,None,None)]
        with patch.object(q,"_goal_types",return_value={"tipos":None,"jogos_com_mapa":0}),patch.object(q,"_physical_rows",return_value={}):
            result=q._team_report(rows,19,None,"2026/2027")
        self.assertIsNone(result["metricas"]["total_chutes"])
        self.assertIsNone(result["metricas"]["xg"])
        self.assertIsNone(result["metricas"]["eficiencia_xg_pct"])
        self.assertIsNone(result["metricas"]["passes_certos_por_gol"])
        self.assertEqual(result["cobertura"]["xg"],0)

    @patch.object(q,"_campeonato_origem",return_value=8)
    @patch.object(q,"_team_report")
    @patch.object(q,"_get_match_rows")
    def test_recortes_independentes_por_clube(self, rows, report, source):
        rows.side_effect=[[],[]]
        report.side_effect=[{"jogos":4},{"jogos":6}]
        for selection,limit in [("5",5),("10",10),("20",20),("temporada",None)]:
            rows.reset_mock()
            data=q.analisar(1,"2026/2027",19,20,selection)
            self.assertEqual(data["recorte"],selection)
            self.assertEqual(rows.call_args_list[0].args,(1,"2026/2027",19,limit))
            self.assertEqual(rows.call_args_list[1].args,(1,"2026/2027",20,limit))
            self.assertEqual(data["mandante"]["jogos"],4)
            self.assertEqual(data["visitante"]["jogos"],6)

    def test_recorte_e_times_invalidos(self):
        with self.assertRaises(ValueError):
            q.analisar(1,"2026/2027",3,4,"3")
        with self.assertRaises(ValueError):
            q.analisar(1,"2026/2027",3,3,"20")

    def test_gols_classificados_com_sobreposicao(self):
        rows=[{"id":15}]
        events=[
            {"jogo_id":15,"clube_id":3,"tipo_evento":"Gol","tipo_finalizacao":"Pé direito","situacao_jogada":"Pênalti","foi_gol_contra":False},
            {"jogo_id":15,"clube_id":3,"tipo_evento":"Gol","tipo_finalizacao":"Cabeça","situacao_jogada":"Escanteio","foi_gol_contra":False},
            {"jogo_id":15,"clube_id":3,"tipo_evento":"Gol","tipo_finalizacao":"Pé esquerdo","situacao_jogada":"Jogada normal","foi_gol_contra":False},
            {"jogo_id":15,"clube_id":3,"tipo_evento":"Gol","tipo_finalizacao":"Pé direito","situacao_jogada":"Falta","foi_gol_contra":True},
        ]
        with patch.object(q,"fetch_all",return_value=events):
            result=q._goal_types(rows,3)
        self.assertEqual(result["gols_em_eventos"],3)
        self.assertEqual(result["tipos"]["bola_parada"],2)
        self.assertEqual(result["tipos"]["penalti"],1)
        self.assertEqual(result["tipos"]["cabeca"],1)
        self.assertEqual(result["tipos"]["pe_esquerdo"],1)


if __name__=="__main__":
    unittest.main()
