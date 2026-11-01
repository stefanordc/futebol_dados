"""Nostradamus: testes de ausência de vazamento temporal e liquidação."""
from datetime import date,datetime,timedelta
from unittest import TestCase
from unittest.mock import patch
import queries_nostradamus as ns


def game(i,day,gf=1,ga=0,comp=1,season="2026/2027",odd_created=None):
    return {
      "id":i,"data":day,"temporada":season,"campeonato_id":comp,"campeonato":"Liga Teste",
      "casa_id":1,"fora_id":2,"mandante":"Clube Casa","visitante":"Clube Fora",
      "gols_casa":gf,"gols_fora":ga,
      "odd_casa":2.1,"odd_empate":3.2,"odd_fora":4.0,"odd_criada":odd_created,
      "home_xg":1.5,"away_xg":0.7,"home_xgot":1.3,"away_xgot":0.3,
      "home_chutes":12,"away_chutes":6,
      "home_chutes_certos":5,"away_chutes_certos":2,
      "home_passes_certos":450,"away_passes_certos":290,
      "home_posse":60,"away_posse":40,
      "home_grandes_chances":3,"away_grandes_chances":1,
      "home_escanteios":6,"away_escanteios":3,
      "home_dribles_certos":7,"away_dribles_certos":4,
      "home_faltas":9,"away_faltas":12,
      "home_duelos_aereos":11,"away_duelos_aereos":7,
    }


def rule(metrica="xg",comparador="gt",margem=0):
    return {"metrica":metrica,"comparador":comparador,"margem":margem}


def config(corte,goal="back_mandante",odd=None,window="5",conditions=None):
    return {"corte":corte.isoformat(),"jogos":window,"objetivo":goal,
            "campeonato_id":1,"condicoes":conditions or [rule()],
            "odd_hipotetica":odd,"comissao_pct":2}


class TestNostradamus(TestCase):
    def setUp(self):
        self.cutoff=date.today()-timedelta(days=2)
        self.start=self.cutoff-timedelta(days=12)
        self.rows=[game(i,self.start+timedelta(days=i),gf=2,ga=0) for i in range(10)]

    def test_no_futuro_e_sem_odd_pos_jogo(self):
        rows=self.rows+[game(15,date.today()+timedelta(days=1)),
                        game(16,date.today())]
        data=ns.testar(config(self.cutoff),rows=rows)
        self.assertEqual(data["entradas"],5)
        self.assertEqual(data["resultados"][0]["greens"],5)
        self.assertEqual(data["resultados"][0]["reds"],0)
        self.assertEqual(data["resultados"][0]["cotadas"],0)
        self.assertIsNone(data["resultados"][0]["unidades"])
        self.assertTrue(all(j["data"]<date.today().isoformat() for j in data["resultados"][0]["jogos"]))

    def test_no_lookahead_propria_partida(self):
        # Quinta partida com xG alto mas quatro anteriores sem diferença: não pode
        # aproveitar xG do próprio jogo para entrar na estratégia.
        rows=[game(i,self.start+timedelta(days=i)) for i in range(6)]
        for row in rows[:5]:
            row["home_xg"]=1.0
            row["away_xg"]=1.0
        rows[-1]["home_xg"]=9.0
        data=ns.testar(config(self.cutoff),rows=rows)
        self.assertEqual(data["entradas"],0)

    def test_mesmo_dia_nao_vaza(self):
        rows=[game(i,self.start+timedelta(days=i),2,0) for i in range(5)]
        x=game(10,self.start+timedelta(days=5))
        y=game(11,self.start+timedelta(days=5))
        y["gols_casa"]=9
        rows.extend([x,y])
        data=ns.testar(config(self.cutoff,conditions=[rule("pontos_jogo","gt")]),rows=rows)
        self.assertEqual(data["entradas"],2)

    def test_back_lay_e_cotacao_hipotetica(self):
        rows=self.rows.copy()
        rows[7]={**rows[7],"gols_casa":0,"gols_fora":2}
        back=ns.testar(config(self.cutoff,odd=2),rows=rows)["resultados"][0]
        lay=ns.testar(config(self.cutoff,goal="lay_mandante",odd=2),rows=rows)["resultados"][0]
        self.assertEqual(back["greens"],4)
        self.assertEqual(back["reds"],1)
        self.assertEqual(back["cotadas"],5)
        self.assertAlmostEqual(back["unidades"],3)
        self.assertEqual(lay["greens"],1)
        self.assertEqual(lay["reds"],4)
        self.assertAlmostEqual(lay["unidades"],-3.02)

    def test_odds_registradas_pre_jogo(self):
        x=game(20,self.start+timedelta(days=6),odd_created=datetime.combine(self.start,datetime.min.time()))
        y=game(21,self.start+timedelta(days=7),odd_created=datetime.now())
        self.assertEqual(ns._odds_for_game(x,"back_mandante",None)[0],2.1)
        self.assertIsNone(ns._odds_for_game(y,"back_mandante",None)[0])
        self.assertIsNone(ns._odds_for_game(x,"over_25",None)[0])

    def test_invalid_conditions(self):
        with self.assertRaises(ValueError):
            ns.testar(config(self.cutoff,conditions=[rule()]*11),rows=self.rows)
        with self.assertRaises(ValueError):
            ns.testar(config(self.cutoff,conditions=[rule("__sql_injection__")]),rows=self.rows)
        with self.assertRaises(ValueError):
            ns.testar(config(self.cutoff,conditions=[rule("xg","LIKE")]),rows=self.rows)
        with self.assertRaises(ValueError):
            ns.testar(config(date.today()+timedelta(days=1)),rows=self.rows)

    def test_sem_cobertura_nao_preenche_nulos(self):
        rows=[{**r,"home_xg":None} for r in self.rows]
        self.assertEqual(ns.testar(config(self.cutoff),rows=rows)["entradas"],0)

    def test_visitante_gols_sofridos_superior_a_15(self):
        # Nenhum nome de estratégia é necessário para executar o backtest.
        c={"lado":"visitante","metrica":"gols_sofridos","comparador":"gt",
           "referencia":"valor","metrica_ref":"gols_sofridos","valor":1.5}
        result=ns.testar(config(self.cutoff,conditions=[c]),rows=self.rows)
        self.assertEqual(result["entradas"],5)
        item=result["resultados"][0]["jogos"][0]["condicoes"][0]
        self.assertEqual(item["lado"],"visitante")
        self.assertEqual(item["observado"],2.0)
        self.assertEqual(item["comparado"],1.5)
        self.assertEqual(item["referencia"],"valor")

    def test_valor_fixo_para_mandante_independente_do_visitante(self):
        c={"lado":"mandante","metrica":"gols_feitos","comparador":"gt",
           "referencia":"valor","valor":1.8}
        self.assertEqual(ns.testar(config(self.cutoff,conditions=[c]),rows=self.rows)["entradas"],5)
        c["valor"]=2.0
        self.assertEqual(ns.testar(config(self.cutoff,conditions=[c]),rows=self.rows)["entradas"],0)

    def test_comparar_equipes_com_indicadores_distintos(self):
        c={"lado":"mandante","metrica":"chutes","comparador":"gt",
           "referencia":"visitante","metrica_ref":"chutes_certos","valor":4.0}
        data=ns.testar(config(self.cutoff,conditions=[c]),rows=self.rows)
        self.assertEqual(data["entradas"],5)  # 12 > 2 + 4
        c["valor"]=10
        self.assertEqual(ns.testar(config(self.cutoff,conditions=[c]),rows=self.rows)["entradas"],0)

    def test_visitante_contra_indicador_do_mandante(self):
        c={"lado":"visitante","metrica":"gols_sofridos","comparador":"gt",
           "referencia":"mandante","metrica_ref":"gols_sofridos","valor":0}
        data=ns.testar(config(self.cutoff,conditions=[c]),rows=self.rows)
        self.assertEqual(data["entradas"],5)  # visitante sofreu 2, mandante sofreu 0

    def test_compativel_com_estrategias_salvas_antigas(self):
        old=ns._valid_conditions([{"metrica":"xg","comparador":"gt","margem":0.4}])[0]
        self.assertEqual(old["lado"],"mandante")
        self.assertEqual(old["referencia"],"visitante")
        self.assertEqual(old["metrica_ref"],"xg")
        self.assertEqual(old["valor"],0.4)
        result=ns.testar(config(self.cutoff,conditions=[rule("xg","gt",0.4)]),rows=self.rows)
        self.assertEqual(result["entradas"],5)  # 1.5 > 0.7 + 0.4

    def test_validacao_das_novas_referencias(self):
        base={"lado":"visitante","metrica":"gols_sofridos","comparador":"gt",
              "referencia":"valor","valor":1.5}
        for update in ({"lado":"inexistente"},{"referencia":"SQL"},
                       {"valor":None},{"valor":""},{"valor":float("nan")},
                       {"metrica_ref":"inexistente"}):
            with self.subTest(update=update),self.assertRaises(ValueError):
                ns._valid_conditions([{**base,**update}])
        self.assertEqual(ns._valid_conditions([base])[0]["valor"],1.5)

    def test_mesmo_dia_nao_vaza_em_comparacao_de_valor(self):
        rows=[game(i,self.start+timedelta(days=i),gf=0,ga=0) for i in range(5)]
        same_day=self.start+timedelta(days=5)
        rows.extend([game(100,same_day,gf=4,ga=0),game(101,same_day,gf=6,ga=0)])
        c={"lado":"mandante","metrica":"gols_feitos","comparador":"gt",
           "referencia":"valor","valor":1.5}
        self.assertEqual(ns.testar(config(self.cutoff,conditions=[c]),rows=rows)["entradas"],0)

    def test_mesmo_indicador_adversario_mandante(self):
        condition={"lado":"mandante","metrica":"xg",
                   "comparador":"gt","referencia":"adversario"}
        normalized=ns._valid_conditions([condition])[0]
        self.assertEqual(normalized["valor"],0)
        self.assertEqual(normalized["metrica_ref"],"xg")
        output=ns.testar(config(self.cutoff,conditions=[condition]),rows=self.rows)
        self.assertEqual(output["entradas"],5)
        detail=output["resultados"][0]["jogos"][0]["condicoes"][0]
        self.assertEqual(detail["observado"],1.5)
        self.assertEqual(detail["comparado"],0.7)
        self.assertEqual(detail["referencia"],"adversario")

    def test_mesmo_indicador_adversario_visitante(self):
        condition={"lado":"visitante","metrica":"gols_sofridos",
                   "comparador":"ge","referencia":"adversario"}
        output=ns.testar(config(self.cutoff,conditions=[condition]),rows=self.rows)
        self.assertEqual(output["entradas"],5)
        detail=output["resultados"][0]["jogos"][0]["condicoes"][0]
        self.assertEqual(detail["observado"],2.0)
        self.assertEqual(detail["comparado"],0.0)

    def test_valor_absoluto_igual_maior_e_igual(self):
        base={"lado":"visitante","metrica":"gols_sofridos","referencia":"valor"}
        for op,number,expected in (("gt",1.5,5),("ge",2,5),
                                  ("eq",2,5),("gt",2,0),("eq",1.5,0)):
            with self.subTest(op=op,value=number):
                cond={**base,"comparador":op,"valor":number}
                self.assertEqual(
                    ns.testar(config(self.cutoff,conditions=[cond]),rows=self.rows)["entradas"],
                    expected,
                )

    def test_adversario_sem_margem_nem_metricas_diferentes(self):
        base={"lado":"mandante","metrica":"xg","comparador":"gt",
              "referencia":"adversario"}
        for update in ({"valor":1},{"margem":0.5},
                       {"metrica_ref":"xgot"},{"referencia":"invalido"}):
            with self.subTest(update=update),self.assertRaises(ValueError):
                ns._valid_conditions([{**base,**update}])
        self.assertEqual(ns._valid_conditions([{**base,"valor":0}])[0]["valor"],0)

    def test_mesmo_indicador_adversario_sem_vazamento_do_mesmo_dia(self):
        rows=[game(i,self.start+timedelta(days=i)) for i in range(5)]
        for item in rows:
            item["home_xg"]=1
            item["away_xg"]=1
        day=self.start+timedelta(days=5)
        rows.extend([game(40,day),game(41,day)])
        condition={"lado":"mandante","metrica":"xg","comparador":"gt",
                   "referencia":"adversario"}
        self.assertEqual(ns.testar(config(self.cutoff,conditions=[condition]),rows=rows)["entradas"],0)

    def test_ate_20_jogos_disponiveis_inclui_ligas_europeias(self):
        # Cenário 01/01/2025: Europa tem 15-19 jogos por equipe.
        # A seleção "20" não pode excluí-las por não terem 20 jogos completos.
        cutoff=date(2025,1,1)
        first=date(2024,8,15)
        data=[]
        leagues=[("Brasileiro",6,38,"2024"),
                 ("Bundesliga",8,15,"2024/2025"),
                 ("LaLiga",1,19,"2024/2025"),
                 ("Premier League",5,19,"2024/2025"),
                 ("Serie A",3,18,"2024/2025")]
        game_id=1000
        for liga,liga_id,count,season in leagues:
            for i in range(count):
                game_id+=1
                start=(date(2024,4,1) if liga=="Brasileiro" else first)
                item=game(game_id,start+timedelta(days=i*7),
                          gf=2,ga=0,comp=liga_id,season=season)
                item["campeonato"]=liga
                data.append(item)
        rules=[
          {"lado":"mandante","metrica":"xg","comparador":"gt",
           "referencia":"adversario"},
          {"lado":"visitante","metrica":"gols_sofridos","comparador":"ge",
           "referencia":"valor","valor":0.8}
        ]
        result=ns.testar(config(cutoff,goal="lay_visitante",
                               window="20",conditions=rules),rows=data)
        grouped={r["campeonato"]:r for r in result["resultados"]}
        self.assertEqual(set(grouped),set(name for name,*_ in leagues))
        for name,_,games_count,_ in leagues:
            expected=games_count-5
            self.assertEqual(grouped[name]["entradas"],expected,name)
            self.assertEqual(grouped[name]["greens"],expected,name)
            self.assertEqual(grouped[name]["reds"],0,name)
            self.assertEqual(grouped[name]["jogos"][0]["historico_mandante"],5)
            self.assertEqual(grouped[name]["jogos"][0]["historico_visitante"],5)
            self.assertLessEqual(grouped[name]["jogos"][-1]["historico_mandante"],20)

    def test_janela_10_e_20_exigem_cinco_jogos_e_nunca_utilizam_hoje(self):
        d=self.start
        data=[game(i,d+timedelta(days=i)) for i in range(8)]
        data.append(game(99,date.today()))
        data.append(game(100,date.today()+timedelta(days=1)))
        for window in ("5","10","20","temporada"):
            with self.subTest(window=window):
                result=ns.testar(config(self.cutoff,window=window),rows=data)
                self.assertEqual(result["entradas"],3)
                self.assertEqual(result["resultados"][0]["jogos"][0]["historico_mandante"],5)
                self.assertEqual(result["resultados"][0]["jogos"][0]["historico_visitante"],5)

    def test_sem_amostra_minima_ainda_exclui_partida(self):
        data=[game(i,self.start+timedelta(days=i)) for i in range(5)]
        for window in ("5","10","20","temporada"):
            result=ns.testar(config(self.cutoff,window=window),rows=data)
            self.assertEqual(result["entradas"],0)

    def test_mercados_e_limites_lay(self):
        self.assertTrue(ns._settle("over_25",2,1))
        self.assertFalse(ns._settle("lay_goleada_mandante",3,0))
        self.assertTrue(ns._settle("lay_goleada_mandante",2,0))
        self.assertTrue(ns._settle("lay_1x0",2,1))
        self.assertAlmostEqual(ns._units(True,"lay_mandante",3.0,.02),.49)
        self.assertEqual(ns._units(False,"lay_mandante",3.0,.02),-1)
        self.assertEqual(ns._units(False,"back_mandante",2.2,.02),-1)


if __name__=="__main__":
    import unittest
    unittest.main()
