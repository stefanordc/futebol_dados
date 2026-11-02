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

    def test_mando_filtra_favorito_e_zebra_independente_de_casa_fora(self):
        partidas=[game(i,self.start+timedelta(days=i),gf=2,ga=0)
                  for i in range(10)]
        for i,g in enumerate(partidas):
            g["api_odd_1_ft"]=1.50 if i<7 else 4.20
            g["api_odd_2_ft"]=4.20 if i<7 else 1.50
        criterio={"lado":"favorito","mando_preferido":"mandante",
                  "metrica":"pontos_jogo","comparador":"ge",
                  "referencia":"valor","valor":0}
        mandante=ns.testar(config(self.cutoff,goal="over_25",
                                    conditions=[criterio]),rows=partidas)
        self.assertEqual(mandante["entradas"],2)
        self.assertTrue(all(detail["condicoes"][0]["mando"]=="mandante"
            for detail in mandante["resultados"][0]["jogos"]))
        criterio["mando_preferido"]="visitante"
        visitante=ns.testar(config(self.cutoff,goal="over_25",
                                     conditions=[criterio]),rows=partidas)
        self.assertEqual(visitante["entradas"],3)
        self.assertTrue(all(detail["condicoes"][0]["mando"]=="visitante"
            for detail in visitante["resultados"][0]["jogos"]))
        criterio["mando_preferido"]="indiferente"
        indiscriminado=ns.testar(config(self.cutoff,goal="over_25",
                                        conditions=[criterio]),rows=partidas)
        self.assertEqual(indiscriminado["entradas"],5)
        criterio["lado"]="zebra"
        criterio["mando_preferido"]="mandante"
        self.assertEqual(ns.testar(config(self.cutoff,goal="over_25",
            conditions=[criterio]),rows=partidas)["entradas"],3)
        criterio["mando_preferido"]="visitante"
        self.assertEqual(ns.testar(config(self.cutoff,goal="over_25",
            conditions=[criterio]),rows=partidas)["entradas"],2)

    def test_mando_indiferente_e_padrao_salvo_e_ambos_fica_indiferente(self):
        base={"lado":"favorito","metrica":"xg","comparador":"gt",
              "referencia":"valor","valor":1}
        normalized=ns._valid_conditions([base])[0]
        self.assertEqual(normalized["mando_preferido"],"indiferente")
        self.assertEqual(ns._valid_conditions(
            [{**base,"mando_preferido":"visitante"}])[0]["mando_preferido"],
            "visitante")
        for invalid in ("casa","fora",None,False,1,[],{}):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                ns._valid_conditions([{**base,"mando_preferido":invalid}])
        both={**base,"lado":"ambos","mando_preferido":"mandante"}
        with self.assertRaisesRegex(ValueError,"Indiferente"):
            ns._valid_conditions([both])
        both["mando_preferido"]="indiferente"
        self.assertEqual(ns._valid_conditions([both])[0]["mando_preferido"],
                         "indiferente")
        cond=ns._valid_conditions([base])[0]
        home={"xg":1.5}
        away={"xg":0.8}
        # Condição sem campo de mando continua sem restringir partidas antigas.
        self.assertIsNotNone(ns._evaluate_condition(cond,home,away,True))
        self.assertIsNotNone(ns._evaluate_condition(cond,home,away,False))

    def test_ambos_exige_duas_equipes_acima_do_limite(self):
        rule_both={"lado":"ambos","metrica":"xg","comparador":"ge",
                   "referencia":"valor","valor":0.7}
        output=ns.testar(config(self.cutoff,goal="over_25",
                                 conditions=[rule_both]),rows=self.rows)
        self.assertEqual(output["entradas"],5)
        detail=output["resultados"][0]["jogos"][0]["condicoes"][0]
        self.assertEqual(detail["mando"],"ambos")
        self.assertEqual(detail["observado_mandante"],1.5)
        self.assertEqual(detail["observado_visitante"],0.7)
        rule_both["valor"]=1.0
        self.assertEqual(ns.testar(config(self.cutoff,goal="over_25",
            conditions=[rule_both]),rows=self.rows)["entradas"],0)
        with self.assertRaisesRegex(ValueError,"Ambos requer"):
            ns._valid_conditions([{**rule_both,"referencia":"adversario"}])

    def test_odds_minimas_maximas_mercado_independente_objetivo(self):
        jogos=[game(i,self.start+timedelta(days=i),gf=2,ga=1) for i in range(10)]
        for i,row in enumerate(jogos):
            row["api_over_ft_2_5"]=round(1.30+0.1*i,2)
        odd_cond={"tipo":"odd","mercado":"over_25","odd_min":1.80,
                  "odd_max":2.10}
        output=ns.testar(config(self.cutoff,goal="ambos_marcam",
                                 conditions=[odd_cond]),rows=jogos)
        self.assertEqual(output["entradas"],4)
        detail=output["resultados"][0]["jogos"][0]["condicoes"][0]
        self.assertEqual(detail["tipo"],"odd")
        self.assertEqual(detail["mercado"],"over_25")
        self.assertAlmostEqual(detail["odd"],1.8)
        self.assertEqual(detail["fonte"],"api_casa")
        # Sem limite superior e sem cotação o critério não aceita a partida.
        del odd_cond["odd_max"]
        self.assertEqual(ns.testar(config(self.cutoff,goal="ambos_marcam",
            conditions=[odd_cond]),rows=jogos)["entradas"],5)
        for row in jogos[5:]:
            row["api_over_ft_2_5"]=None
        self.assertEqual(ns.testar(config(self.cutoff,goal="ambos_marcam",
            conditions=[odd_cond]),rows=jogos)["entradas"],0)

    def test_odd_favorito_nao_usa_preco_ficticio_e_lay_e_estimado(self):
        jogos=[game(i,self.start+timedelta(days=i),gf=2,ga=0) for i in range(10)]
        for row in jogos:
            row.update(api_odd_1_ft=1.60,api_odd_2_ft=4.30,
                       api_lay_odd_1_ft=1.61)
        cond={"tipo":"odd","mercado":"back_favorito",
              "odd_min":1.60,"odd_max":1.70}
        output=ns.testar(config(self.cutoff,goal="over_25",odd=8.0,
                                 conditions=[cond]),rows=jogos)
        self.assertEqual(output["entradas"],5)
        self.assertAlmostEqual(output["resultados"][0]["jogos"][0]["condicoes"][0]["odd"],1.6)
        cond["mercado"]="lay_favorito"
        lay=ns.testar(config(self.cutoff,goal="over_25",
                            conditions=[cond]),rows=jogos)
        self.assertEqual(lay["entradas"],5)
        self.assertEqual(lay["resultados"][0]["jogos"][0]["condicoes"][0]["fonte"],
                         "lay_estimado")
        cond["odd_min"]=1.7
        self.assertEqual(ns.testar(config(self.cutoff,goal="over_25",
            conditions=[cond]),rows=jogos)["entradas"],0)

    def test_rejeita_filtro_odd_sem_mercado_ou_limites_validos(self):
        valid={"tipo":"odd","mercado":"over_25","odd_min":1.6}
        self.assertEqual(ns._valid_conditions([valid])[0]["odd_min"],1.6)
        for changes in ({"mercado":"fake"},{"mercado":None},
                        {"odd_min":None},{"odd_min":0.99},
                        {"odd_min":float("nan")},{"odd_min":True},
                        {"odd_min":4.1,"odd_max":3.9},
                        {"odd_max":1001}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                ns._valid_conditions([{**valid,**changes}])

    def test_indicadores_fisicos_e_diferencas_por_partida(self):
        jogos=[]
        for i in range(10):
            r=game(i,self.start+timedelta(days=i),gf=2,ga=0)
            r.update(home_km=112,away_km=103,home_sprints=148,away_sprints=122)
            jogos.append(r)
        conds=[
            {"lado":"mandante","metrica":"km","comparador":"gt","referencia":"adversario"},
            {"lado":"mandante","metrica":"sprints_diff","comparador":"ge",
             "referencia":"valor","valor":20},
            {"lado":"visitante","metrica":"km_diff","comparador":"lt",
             "referencia":"valor","valor":0},
        ]
        data=ns.testar(config(self.cutoff,conditions=conds),rows=jogos)
        self.assertEqual(data["entradas"],5)
        for entry in data["resultados"][0]["jogos"]:
            detail=entry["condicoes"]
            self.assertEqual(detail[0]["observado"],112)
            self.assertEqual(detail[0]["comparado"],103)
            self.assertEqual(detail[1]["observado"],26)
            self.assertEqual(detail[2]["observado"],-9)

    def test_dados_fisicos_faltantes_nao_viram_zero(self):
        records=[ns._history_item(game(i,self.start+timedelta(days=i)), "home")
                 for i in range(5)]
        for r in records:
            self.assertIsNone(r["km"])
            self.assertIsNone(r["sprints"])
            self.assertIsNone(r["km_diff"])
        physical=ns._stats(records,5)
        self.assertIsNone(physical["km"])
        self.assertIsNone(physical["sprints"])
        self.assertIsNone(physical["km_diff"])
        r=game(55,self.start)
        r.update(home_km=120,away_km=None,home_sprints=0,away_sprints=130)
        item=ns._history_item(r,"home")
        self.assertEqual(item["km"],120)
        self.assertIsNone(item["km_diff"])
        self.assertIsNone(item["sprints"])
        self.assertIsNone(item["sprints_diff"])

    def test_cobertura_fisica_exige_60_porcento_no_recorte(self):
        rows=[]
        for i in range(5):
            row=game(i,self.start+timedelta(days=i))
            row.update(home_km=112 if i<2 else None,
                       away_km=100 if i<2 else None,
                       home_sprints=120 if i<2 else None,
                       away_sprints=110 if i<2 else None)
            rows.append(ns._history_item(row,"home"))
        stats=ns._stats(rows,5)
        self.assertIsNone(stats["km"])
        self.assertIsNone(stats["sprints"])
        self.assertIsNone(stats["km_diff"])
        row=game(5,self.start+timedelta(days=5))
        row.update(home_km=110,away_km=100,home_sprints=120,away_sprints=110)
        rows[2]=ns._history_item(row,"home")
        stats=ns._stats(rows,5)
        self.assertAlmostEqual(stats["km"],(112*2+110)/3)
        self.assertAlmostEqual(stats["km_diff"],(12*2+10)/3)

    def test_fisicos_apenas_partidas_anteriores_e_mesmo_dia_excluido(self):
        rowlist=[]
        for i in range(7):
            match=game(i,self.start+timedelta(days=i),gf=1,ga=0)
            # A partir do 6º jogo, dados físicos são favoráveis ao visitante;
            # o filtro de 5 jogos anteriores deve reagir apenas no dia seguinte.
            if i<6:
                match.update(home_km=110,away_km=90,home_sprints=150,away_sprints=110)
            else:
                match.update(home_km=30,away_km=190,home_sprints=50,away_sprints=240)
            rowlist.append(match)
        # No jogo 7, histórico anterior tem 5 registros positivos;
        # o registro do próprio jogo (i=6) não pode entrar na condição.
        cfg=config(self.cutoff,conditions=[{"lado":"mandante","metrica":"km",
                 "comparador":"gt","referencia":"adversario"}],window="5")
        result=ns.testar(cfg,rows=rowlist)
        self.assertEqual(result["entradas"],2)
        self.assertTrue(all(x["condicoes"][0]["observado"]==110 for x in result["resultados"][0]["jogos"]))

    def test_sql_fisicos_somente_id_sofascore_com_clube_mapeado(self):
        self.assertIn("j.id_sofascore IS NULL OR fh.id_jogo=j.id_sofascore",ns.RAW)
        self.assertIn("fa.id_jogo=fh.id_jogo",ns.RAW)
        self.assertIn("hsrc.id_externo=fh.id_clube::text",ns.RAW)
        self.assertIn("asrc.id_externo=fa.id_clube::text",ns.RAW)
        self.assertIn("fh.temporada=j.temporada",ns.RAW)
        self.assertIn("fh.data=j.data",ns.RAW)
        self.assertIn("CASE c.nome WHEN 'LaLiga' THEN 'Espanhol'",ns.RAW)
        self.assertIn("HAVING COUNT(*)=1",ns.RAW)
        self.assertIn("j.data<CURRENT_DATE",ns.RAW)

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
        self.assertAlmostEqual(lay["unidades"],-3.045)  # 4,5% em 1 green, 4 reds

    def test_preco_real_e_resultado_por_100_reais_com_streaks(self):
        partidas=[game(i,self.start+timedelta(days=i),gf=2,ga=0)
                  for i in range(10)]
        odds=[2.10,1.70,2.00,3.00,2.25]
        for i,odd in enumerate(odds,start=5):
            partidas[i]["api_odd_1_ft"]=odd
            partidas[i]["api_bookie_odd_1_ft"]="bet365"
        partidas[7]["gols_casa"]=0
        partidas[7]["gols_fora"]=2
        partidas[8]["gols_casa"]=0
        partidas[8]["gols_fora"]=1
        out=ns.testar(config(self.cutoff),rows=partidas)
        summary=out["resultados"][0]
        self.assertEqual((summary["greens"],summary["reds"]),(3,2))
        self.assertEqual(summary["win_rate"],60.0)
        self.assertEqual(summary["cotadas"],5)
        self.assertEqual(summary["maior_good_run"],2)
        self.assertEqual(summary["maior_bad_run"],2)
        self.assertEqual(summary["unidades"],1.05)
        self.assertAlmostEqual(summary["valor_reais"],105.0)
        self.assertAlmostEqual(summary["odd_media"],2.21)
        self.assertEqual(out["stake_reais"],100)
        self.assertEqual(summary["jogos"][0]["tipo_odd"],"api_casa")
        self.assertEqual(summary["jogos"][0]["bookmaker"],"bet365")
        self.assertEqual(summary["jogos"][0]["valor_reais"],110.0)
        self.assertEqual(summary["jogos"][2]["valor_reais"],-100.0)

    def test_lucro_medio_somente_sobre_entradas_cotadas(self):
        partidas=[game(i,self.start+timedelta(days=i),gf=2,ga=0)
                  for i in range(10)]
        for i in (5,6,7):
            partidas[i]["api_odd_1_ft"]=2.0
        partidas[7]["gols_casa"]=0
        partidas[7]["gols_fora"]=1
        result=ns.testar(config(self.cutoff),rows=partidas)["resultados"][0]
        self.assertEqual(result["entradas"],5)
        self.assertEqual(result["cotadas"],3)
        self.assertEqual(result["unidades"],1.0)
        self.assertEqual(result["valor_reais"],100.0)
        self.assertAlmostEqual(result["lucro_medio_entrada"],33.33)
        partidas=[{k:v for k,v in row.items() if k!="api_odd_1_ft"} for row in partidas]
        result=ns.testar(config(self.cutoff),rows=partidas)["resultados"][0]
        self.assertIsNone(result["lucro_medio_entrada"])

    def test_multiplos_campeonatos_mantem_historia_separada(self):
        partidas=[]
        for league_id in (1,2,3):
            for i in range(10):
                item=game(league_id*100+i,self.start+timedelta(days=i),
                          comp=league_id,gf=2,ga=0)
                item["campeonato"]=f"Liga {league_id}"
                item["api_odd_1_ft"]=2.0
                partidas.append(item)
        cfg={**config(self.cutoff),"campeonato_ids":[1,3]}
        out=ns.testar(cfg,rows=partidas)
        self.assertEqual(out["campeonato_ids"],[1,3])
        self.assertEqual(out["entradas"],10)
        self.assertEqual([x["campeonato"] for x in out["resultados"]],
                         ["Liga 1","Liga 3"])
        self.assertTrue(all(x["entradas"]==5 for x in out["resultados"]))
        all_cfg={**cfg,"campeonato_ids":[]}
        self.assertEqual(ns.testar(all_cfg,rows=partidas)["entradas"],15)
        legacy={**cfg,"campeonato_id":2}
        legacy.pop("campeonato_ids")
        self.assertEqual(ns.testar(legacy,rows=partidas)["entradas"],5)

    def test_valida_lista_de_campeonatos_sem_duplicatas(self):
        for invalid in ([1,1],[0],[True],["1"],list(range(1,33)),{},2):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                ns.ligas_selecionadas({"campeonato_ids":invalid})
        self.assertEqual(ns.ligas_selecionadas({"campeonato_ids":[3,1]}),[1,3])
        self.assertIsNone(ns.ligas_selecionadas({"campeonato_ids":[]}))
        self.assertEqual(ns.ligas_selecionadas({"campeonato_id":6}),[6])

    def test_sql_parametriza_filtro_de_multiplos_campeonatos(self):
        rows=[]
        with patch.object(ns,"fetch_all",return_value=rows) as query:
            ns.testar({**config(self.cutoff),"campeonato_ids":[2,1]})
        sql, params=query.call_args.args
        self.assertIn("j.campeonato_id = ANY(%s::integer[])",sql)
        self.assertEqual(params[1],[1,2])

    def test_favorito_zebra_exige_odds_1_e_2_reais_e_distintas(self):
        self.assertTrue(ns._favorite_home({"api_odd_1_ft":1.45,"api_odd_2_ft":6.2}))
        self.assertFalse(ns._favorite_home({"api_odd_1_ft":5.8,"api_odd_2_ft":1.9}))
        for row in (
            {"api_odd_1_ft":2.5,"api_odd_2_ft":2.5},
            {"api_odd_1_ft":None,"api_odd_2_ft":3.2},
            {"api_odd_1_ft":0.0,"api_odd_2_ft":3.2},
            {"api_odd_1_ft":float("nan"),"api_odd_2_ft":3.2},
            {"odd_casa":1.6,"odd_fora":4.1},
        ):
            self.assertIsNone(ns._favorite_home(row))
        self.assertEqual(ns._role_to_side("favorito",False),"visitante")
        self.assertEqual(ns._role_to_side("zebra",False),"mandante")
        self.assertEqual(ns._role_to_side("favorito",True),"mandante")
        self.assertEqual(ns._role_to_side("zebra",True),"visitante")

    def test_condicoes_favorito_zebra_recalculam_com_o_mando(self):
        rows=[game(i,self.start+timedelta(days=i),gf=2,ga=0)
              for i in range(10)]
        for i,r in enumerate(rows):
            r["api_odd_1_ft"],r["api_odd_2_ft"] = (
                (1.5,4.2) if i<7 else (4.2,1.5))
        condition={"lado":"favorito","metrica":"gols_feitos","comparador":"gt",
                   "referencia":"valor","valor":1.5}
        res=ns.testar(config(self.cutoff,conditions=[condition]),rows=rows)
        self.assertEqual(res["entradas"],2)
        self.assertTrue(all(j["condicoes"][0]["mando"]=="mandante"
                            for j in res["resultados"][0]["jogos"]))
        condition={"lado":"zebra","metrica":"gols_feitos","comparador":"lt",
                   "referencia":"valor","valor":1.0}
        res=ns.testar(config(self.cutoff,conditions=[condition]),rows=rows)
        self.assertEqual(res["entradas"],2)
        self.assertTrue(all(j["condicoes"][0]["mando"]=="visitante"
                            for j in res["resultados"][0]["jogos"]))

    def test_back_favorito_e_zebra_com_odds_especificas_do_time(self):
        rows=[game(i,self.start+timedelta(days=i),gf=2,ga=0)
              for i in range(10)]
        for i,r in enumerate(rows):
            r["api_odd_1_ft"],r["api_odd_2_ft"] = (
                (1.6,3.4) if i<7 else (4.5,1.8))
            r["api_bookie_odd_1_ft"]="bet365"
            r["api_bookie_odd_2_ft"]="pinnacle"
        neutral={"lado":"favorito","metrica":"pontos_jogo","comparador":"ge",
                 "referencia":"valor","valor":0}
        fav=ns.testar(config(self.cutoff,goal="back_favorito",
                           conditions=[neutral]),rows=rows)["resultados"][0]
        self.assertEqual((fav["entradas"],fav["greens"],fav["reds"]),(5,2,3))
        self.assertAlmostEqual(fav["unidades"],-1.8)
        self.assertEqual(fav["jogos"][0]["favorito"],"Clube Casa")
        self.assertEqual(fav["jogos"][0]["mando_favorito"],"mandante")
        self.assertEqual(fav["jogos"][0]["odd"],1.6)
        self.assertEqual(fav["jogos"][0]["bookmaker"],"bet365")
        self.assertEqual(fav["jogos"][2]["favorito"],"Clube Fora")
        self.assertEqual(fav["jogos"][2]["mando_favorito"],"visitante")
        self.assertEqual(fav["jogos"][2]["placar_favorito"],"0x2")
        self.assertEqual(fav["jogos"][2]["odd"],1.8)
        self.assertEqual(fav["jogos"][2]["bookmaker"],"pinnacle")
        zebra=ns.testar(config(self.cutoff,goal="back_zebra",
                             conditions=[neutral]),rows=rows)["resultados"][0]
        self.assertEqual((zebra["greens"],zebra["reds"]),(3,2))
        self.assertAlmostEqual(zebra["unidades"],8.5)
        self.assertEqual(zebra["jogos"][0]["odd"],3.4)
        self.assertEqual(zebra["jogos"][2]["odd"],4.5)

    def test_ignora_empates_e_odds_ausentes_sem_inventar_classificacao(self):
        rows=[game(i,self.start+timedelta(days=i),gf=2,ga=0)
              for i in range(10)]
        for r in rows:
            r["api_odd_1_ft"]=2.0
            r["api_odd_2_ft"]=4.0
        rows[7]["api_odd_2_ft"]=2.0
        rows[8]["api_odd_2_ft"]=None
        neutral={"lado":"favorito","metrica":"pontos_jogo","comparador":"ge",
                 "referencia":"valor","valor":0}
        out=ns.testar(config(self.cutoff,goal="lay_zebra",
                             conditions=[neutral]),rows=rows)
        self.assertEqual(out["sem_classificacao"],2)
        self.assertEqual(out["entradas"],3)
        self.assertEqual(out["resultados"][0]["cotadas"],0)
        # Estratégia legada continua calculável com dados sem Match Odds:
        old=ns.testar(config(self.cutoff,goal="back_mandante"),rows=self.rows)
        self.assertEqual(old["entradas"],5)

    def test_referencia_adversario_aplica_time_oposto_do_favorito(self):
        c={"lado":"favorito","metrica":"gols_feitos","comparador":"gt",
           "referencia":"adversario"}
        normalized=ns._valid_conditions([c])[0]
        home=ns._history_item(game(2,self.start,gf=3,ga=1),"home")
        away=ns._history_item(game(2,self.start,gf=3,ga=1),"away")
        home={"gols_feitos":3}
        away={"gols_feitos":1}
        self.assertEqual(ns._evaluate_condition(normalized,home,away,True)["mando"],"mandante")
        self.assertIsNone(ns._evaluate_condition(normalized,home,away,False))
        other={"lado":"zebra","metrica":"gols_feitos","comparador":"gt",
               "referencia":"favorito","metrica_ref":"gols_feitos","valor":0}
        parsed=ns._valid_conditions([other])[0]
        self.assertEqual(parsed["referencia"],"favorito")
        self.assertIsNone(ns._evaluate_condition(parsed,home,away,True))

    def test_entradas_sem_preco_nao_inventam_lucro(self):
        r=ns.testar(config(self.cutoff),rows=self.rows)["resultados"][0]
        self.assertEqual(r["entradas"],5)
        self.assertEqual(r["maior_good_run"],5)
        self.assertEqual(r["maior_bad_run"],0)
        self.assertEqual(r["cotadas"],0)
        self.assertIsNone(r["unidades"])
        self.assertIsNone(r["valor_reais"])
        self.assertIsNone(r["odd_media"])

    def test_lay_usa_apenas_lay_estimado_identificado(self):
        partidas=[{**g} for g in self.rows]
        for i in range(5,10):
            partidas[i].update(api_odd_1_ft=2.10,api_lay_odd_1_ft=2.12)
        for i in (5,6,8,9):
            partidas[i]["gols_casa"]=0
            partidas[i]["gols_fora"]=1
        out=ns.testar(config(self.cutoff,goal="lay_mandante"),rows=partidas)
        summary=out["resultados"][0]
        self.assertEqual(summary["cotadas"],5)
        self.assertTrue(all(j["tipo_odd"]=="lay_estimado" for j in summary["jogos"]))
        self.assertAlmostEqual(summary["unidades"],round(4*(0.955/1.12)-1,3))
        self.assertIsNone(ns._odds_for_game(
            {"api_odd_1_ft":2.1,"data":self.start},
            "lay_mandante",None)[0])
        self.assertEqual(ns._odds_for_game(
            {"api_lay_cs_1_0":8.2},"lay_1x0",None),
            (8.2,"lay_estimado"))
        self.assertEqual(ns._odds_for_game({"api_odd_1_ft":2.1},
            "lay_goleada_mandante",None),(None,None))

    def test_api_tem_mercados_e_pareamento_estrito_na_sql(self):
        for fragment in ("o.mandante_id=j.casa_id",
                         "o.visitante_id=j.fora_id",
                         "o.data_jogo::date=j.data",
                         "REPLACE(o.temporada,'-','/')=j.temporada",
                         "LOWER(BTRIM(o.campeonato))=LOWER(BTRIM(c.nome))",
                         "HAVING COUNT(*)=1",
                         "oa.odd_1_ft AS api_odd_1_ft",
                         "oa.lay_odd_x_ft AS api_lay_odd_x_ft"):
            self.assertIn(fragment,ns.RAW)
        for market in ("back_empate","over_05","over_25","under_25",
                       "ambos_marcam","ambos_nao","lay_1x0"):
            self.assertIn(market,ns.API_MARKETS)

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
        payload=config(cutoff,goal="lay_visitante",
                       window="20",conditions=rules)
        payload["campeonato_id"]=None  # Todos os campeonatos.
        result=ns.testar(payload,rows=data)
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
