"""Testes isolados: rodadas, sigilo pré-fechamento, aposta e balanços em reais."""
from datetime import date,timedelta
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch, MagicMock
import queries_galileu_gameplay as gl
import queries_nostradamus as ns
from test_nostradamus import game


DAY=date(2026,11,2)


def fixtures():
    first=date(2026,10,10)
    rows=[]
    for i in range(7):
        r=game(i+1,first+timedelta(days=i),gf=2,ga=0,comp=1,
               season="2026/2027")
        r["rodada"]="Rodada 8"
        r["api_odd_1_ft"]=1.65
        r["api_odd_x_ft"]=3.5
        r["api_odd_2_ft"]=5.2
        r["api_over_ft_2_5"]=1.91
        rows.append(r)
    for comp in (1,2):
        for n in (0,1):
            r=game(100+comp*10+n,first+timedelta(days=10+n*8),
                   gf=3 if n==0 else 0,ga=1,
                   comp=comp,season="2026/2027")
            r["rodada"]="Rodada "+str(9+n)
            r["api_odd_1_ft"]=1.65
            r["api_odd_x_ft"]=3.5
            r["api_odd_2_ft"]=5.2
            r["api_over_ft_2_5"]=1.91
            r["campeonato"]="Liga "+str(comp)
            rows.append(r)
    return rows


def session(phase="aberta"):
    return {"id":"session_uuid","token_hash":"a"*64,
            "corte":date(2026,10,17),
            "corte_atual":date(2026,10,17),
            "banca_inicial":Decimal("1000.00"),
            "banca_base_mes":Decimal("1000.00"),
            "mes_base":"2026-10",
            "banca_atual":Decimal("1022.00"),
            "gestao_pct":Decimal("2.00"),
            "stake_fixa":None,"indice_rodada":0,"fase":phase,
            "versao":1}


class TestGalileuGameplay(TestCase):
    def setUp(self):
        self.clock=patch.object(gl,"today",return_value=DAY)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_stake_padrao_e_validacao_de_dinheiro(self):
        s=session()
        self.assertEqual(gl._default_stake(s),20.00)
        s["banca_base_mes"]=Decimal("1500.00")
        self.assertEqual(gl._default_stake(s),30.00)
        s["banca_base_mes"]=Decimal("0.00")
        self.assertEqual(gl._default_stake(s),0.01)
        s["stake_fixa"]=Decimal("23.55")
        self.assertEqual(gl._default_stake(s),23.55)
        self.assertEqual(gl._money("20.00","Stake"),Decimal("20.00"))
        for bad in ("-1","0","2.999","NaN","Infinity",True,None,""):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                gl._money(bad,"Stake")
        for bad in (0,101,-1,"1.222",None):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                gl._pct(bad)

    def test_jogos_do_mes_inteiro_na_mesma_etapa(self):
        catalog=fixtures()
        rounds=gl._rounds(date(2026,10,17),catalog)
        self.assertEqual(len(rounds),1)
        october=gl._round_at(rounds,0)
        self.assertEqual(len(october),4)
        self.assertEqual({r["campeonato_id"] for r in october},{1,2})
        self.assertEqual({r["rodada"] for r in october},{"Rodada 9","Rodada 10"})
        self.assertEqual(rounds[0]["limite"],date(2026,10,31))
        self.assertEqual(rounds[0]["proximo_corte"],date(2026,10,31))
        self.assertEqual(gl._monthly_boundary(rounds,0),(True,"2026-10"))

    def test_mes_comecando_em_janeiro_nao_traz_marco(self):
        def item(number,day,league=1):
            return {"id":number,"data":date.fromisoformat(day),
                    "campeonato_id":league}
        catalog=[
            item(1,"2025-01-01"),item(2,"2025-01-03",2),
            item(3,"2025-01-10"),item(4,"2025-01-11"),
            item(5,"2025-01-20"),item(6,"2025-03-30",3),
        ]
        rounds=gl._rounds(date(2024,12,31),catalog)
        self.assertEqual([g["id"] for g in gl._round_at(rounds,0)],[1,2,3,4,5])
        self.assertEqual(rounds[0]["corte"],date(2024,12,31))
        self.assertEqual(rounds[0]["limite"],date(2025,1,31))
        self.assertEqual(rounds[0]["proximo_corte"],date(2025,1,31))
        self.assertFalse(rounds[1]["jogos"])
        self.assertEqual(rounds[1]["limite"],date(2025,2,28))
        self.assertEqual([g["id"] for g in gl._round_at(rounds,2)],[6])

    def test_corte_no_meio_do_mes_respeita_inicio_e_mes_seguinte(self):
        dates=["2025-01-26","2025-01-30","2025-01-31",
               "2025-02-01","2025-02-03"]
        catalog=[{"id":i+1,"data":date.fromisoformat(day),"campeonato_id":1}
                 for i,day in enumerate(dates)]
        rounds=gl._rounds(date(2025,1,25),catalog)
        self.assertEqual([g["id"] for g in gl._round_at(rounds,0)],[1,2,3])
        self.assertEqual(rounds[0]["limite"],date(2025,1,31))
        self.assertEqual(rounds[0]["proximo_corte"],date(2025,1,31))
        self.assertEqual([g["id"] for g in gl._round_at(rounds,1)],[4,5])
        self.assertEqual(rounds[1]["corte"],date(2025,1,31))
        self.assertEqual(rounds[1]["limite"],date(2025,2,28))
        self.assertEqual(gl._monthly_boundary(rounds,0),(True,"2025-01"))

    def test_ultimo_jogo_antes_fim_do_mes_nao_cria_rodada_extra(self):
        catalog=[
            {"id":1,"data":date(2025,1,27),"campeonato_id":1},
            {"id":2,"data":date(2025,2,1),"campeonato_id":2},
        ]
        rounds=gl._rounds(date(2025,1,25),catalog)
        self.assertEqual(len(rounds),2)
        self.assertEqual(rounds[0]["limite"],date(2025,1,31))
        self.assertEqual(rounds[0]["proximo_corte"],date(2025,1,31))
        self.assertEqual([g["id"] for g in rounds[1]["jogos"]],[2])
        self.assertEqual(gl._monthly_boundary(rounds,0),(True,"2025-01"))

    def test_meses_sem_jogos_avancam_uma_vez_por_mes(self):
        catalog=[{"id":8,"data":date(2025,3,30),"campeonato_id":1}]
        rounds=gl._rounds(date(2024,12,31),catalog)
        self.assertEqual(len(rounds),3)
        self.assertEqual([w["limite"] for w in rounds],
                         [date(2025,1,31),date(2025,2,28),date(2025,3,31)])
        self.assertEqual(gl._round_at(rounds,0),[])
        self.assertEqual(gl._round_at(rounds,1),[])
        self.assertEqual(rounds[-1]["jogos"][0]["id"],8)
        for one,two in zip(rounds,rounds[1:]):
            self.assertEqual(two["corte"],one["proximo_corte"])
        self.assertEqual(gl._closing_boundary(rounds),(True,"2025-01",True))

    def test_proxima_atualiza_corte_sem_alterar_corte_inicial(self):
        from contextlib import contextmanager
        catalog=fixtures()
        sess=session(phase="revelada")
        executed=[]
        class Cursor:
            last=""
            def execute(self,sql,params):
                self.last=sql
                executed.append((sql,params))
            def fetchone(self):
                return {"fechado":True} if "fechamentos_mensais" in self.last else None
        class Conn:
            def cursor(self):
                @contextmanager
                def cursor_context():
                    yield Cursor()
                return cursor_context()
            def commit(self):
                pass
        @contextmanager
        def fake_conn():
            yield Conn()
        with patch.object(gl,"_catalog",return_value=catalog), \
             patch.object(gl,"_lock",return_value=sess), \
             patch.object(gl,"get_conn",fake_conn):
            result=gl.proxima("token")
        self.assertEqual(result["corte_atual"],"2026-10-31")
        self.assertTrue(any("corte_atual=%s" in sql for sql,_ in executed))
        self.assertFalse(any(" SET corte=" in sql for sql,_ in executed))
        params=executed[-1][1]
        self.assertEqual(params[1],date(2026,10,31))
        self.assertEqual(params[2],"concluida")

    def test_estado_retomado_usa_ultimo_corte_salvo_nao_indice(self):
        catalog=fixtures()
        sess=session()
        sess["corte_atual"]=date(2026,10,20)
        sess["indice_rodada"]=1
        with patch.object(gl,"_token_session",return_value=sess), \
             patch.object(gl,"_catalog",return_value=catalog), \
             patch.object(gl,"_methods",return_value=[]), \
             patch.object(gl,"_disabled_methods",return_value={}), \
             patch.object(gl,"_bet_rows",return_value=[]), \
             patch.object(gl,"_closed_game_ids",return_value=set()), \
             patch.object(gl,"_fechamentos",return_value=[]):
            result=gl.estado("token")
        self.assertEqual(result["corte"],"2026-10-17")
        self.assertEqual(result["corte_atual"],"2026-10-20")
        self.assertEqual(result["limite_janela"],"2026-10-31")
        self.assertEqual([g["jogo_id"] for g in result["jogos"]],[111,121])

    def test_metodo_so_considera_indicadores_anteriores_e_odds(self):
        rows=fixtures()
        history=gl._history(rows)
        target=next(r for r in rows if r["id"]==110)
        h,count=gl._team_stats(history,target,1,20)
        a,_=gl._team_stats(history,target,2,20)
        self.assertEqual(count,7)
        self.assertEqual(h["xg"],1.5)
        valid=ns._valid_conditions([{
            "lado":"favorito","mando_preferido":"mandante",
            "metrica":"xg","comparador":"ge","referencia":"valor","valor":1.5
        }])
        method={"id":7,"versao":2,"nome":"Favorito xG",
                "objetivo":"back_favorito","condicoes":valid,
                "ligas":set(),"jogos":20}
        matched=gl._matched(target,h,a,[method])
        self.assertEqual(len(matched),1)
        self.assertEqual(matched[0]["mercado"]["odd"],1.65)
        self.assertEqual(matched[0]["id"],7)
        target["api_odd_1_ft"]=None
        self.assertEqual(gl._matched(target,h,a,[method]),[])

    def test_resposta_do_estado_esconde_placar_ate_finalizacao(self):
        catalog=fixtures()
        sess=session()
        with patch.object(gl,"_token_session",return_value=sess), \
             patch.object(gl,"_catalog",return_value=catalog), \
             patch.object(gl,"_methods",return_value=[]), \
             patch.object(gl,"_disabled_methods",return_value={}), \
             patch.object(gl,"_bet_rows",return_value=[]), \
             patch.object(gl,"_closed_game_ids",return_value=set()), \
             patch.object(gl,"_fechamentos",return_value=[]):
            before=gl.estado("my_secret")
            self.assertTrue(before["iniciado"])
            self.assertEqual(before["banca_atual"],1022.0)
            self.assertEqual(before["rodada_atual"]["jogos"],2)
            self.assertNotIn("placar",before["jogos"][0])
            self.assertNotIn("gols_casa",before["jogos"][0])
            self.assertNotIn("gols_fora",before["jogos"][0])
            self.assertNotIn("resultado",before["jogos"][0])
            sess["fase"]="revelada"
            after=gl.estado("my_secret")
            self.assertEqual(after["jogos"][0]["placar"]["mandante"],3)
            self.assertEqual(after["jogos"][0]["placar"]["visitante"],1)

    def test_ganhos_e_perdas_back_lay_comissao_fixa(self):
        self.assertEqual(gl._settlement("back_mandante",True,2,0,
                         Decimal("2.10"),Decimal("20.00")),
                         ("green",Decimal("22.00")))
        self.assertEqual(gl._settlement("back_mandante",True,0,2,
                         Decimal("2.10"),Decimal("20.00")),
                         ("red",Decimal("-20.00")))
        self.assertEqual(gl._settlement("lay_zebra",True,2,0,
                         Decimal("3.00"),Decimal("20.00")),
                         ("green",Decimal("9.55")))
        self.assertEqual(gl._settlement("lay_zebra",True,0,2,
                         Decimal("3.00"),Decimal("20.00")),
                         ("red",Decimal("-20.00")))
        self.assertEqual(gl._settlement("back_favorito",False,0,1,
                         Decimal("1.50"),Decimal("20.00")),
                         ("green",Decimal("10.00")))

    def test_resumo_mensal_roi_por_stake_e_por_grupos(self):
        d=date(2026,10,20)
        bets=[
            {"data":d,"status":"green","stake":Decimal("20.00"),
             "lucro_prejuizo":Decimal("18.00"),"metodo_nome":"XG",
             "tipo":"metodo","campeonato":"Ligue 1",
             "mandante":"PSG","visitante":"Lyon"},
            {"data":d+timedelta(days=1),"status":"red","stake":Decimal("20.00"),
             "lucro_prejuizo":Decimal("-20.00"),"metodo_nome":None,
             "tipo":"manual","campeonato":"Ligue 1",
             "mandante":"Lyon","visitante":"PSG"},
            {"data":date(2026,11,1),"status":"pendente","stake":Decimal("30.00"),
             "lucro_prejuizo":None,"metodo_nome":None,"tipo":"manual",
             "campeonato":"Serie A","mandante":"Inter","visitante":"Roma"},
        ]
        result=gl._summary(bets,Decimal("1000"))
        self.assertEqual(len(result),2)
        octob=result[0]
        self.assertEqual(octob["entradas"],2)
        self.assertEqual(octob["greens"],1)
        self.assertEqual(octob["reds"],1)
        self.assertEqual(octob["win_rate"],50)
        self.assertEqual(octob["lucro_prejuizo"],-2.0)
        self.assertEqual(octob["roi"],-5.0)
        self.assertEqual(octob["banca_fim"],998.0)
        self.assertEqual(len(octob["por_estrategia"]),2)
        self.assertEqual(len(octob["por_clube"]),2)
        november=result[1]
        self.assertEqual(november["pendentes"],1)
        self.assertEqual(november["banca_fim"],998)

    def test_sem_odd_nao_inventa_cotacao(self):
        g=fixtures()[-1]
        g["api_odd_1_ft"]=None
        g["api_odd_2_ft"]=None
        self.assertIsNone(gl._market(g,"back_favorito"))
        self.assertIsNone(gl._market(g,"back_mandante"))
        self.assertEqual([v["mercado"] for v in gl._available_markets(g) if v["mercado"]=="over_25"],["over_25"])

    def test_jogo_finalizado_some_da_lista_sem_apagar_duas_entradas(self):
        catalog=fixtures()
        session_data=session()
        g=next(g for g in catalog if g["id"]==110)
        bets=[
            {"id":1,"jogo_id":110,"indice_rodada":0,"tipo":"metodo",
             "metodo_id":7,"metodo_nome":"Over 2.5","mercado":"over_25",
             "odd":Decimal("1.80"),"stake":Decimal("20.00"),
             "status":"pendente","lucro_prejuizo":None,
             "data":g["data"],"campeonato":"Liga 1",
             "mandante":"Casa","visitante":"Fora"},
            {"id":2,"jogo_id":110,"indice_rodada":0,"tipo":"manual",
             "metodo_id":None,"metodo_nome":None,"mercado":"back_mandante",
             "odd":Decimal("1.65"),"stake":Decimal("20.00"),
             "status":"pendente","lucro_prejuizo":None,
             "data":g["data"],"campeonato":"Liga 1",
             "mandante":"Casa","visitante":"Fora"},
        ]
        with patch.object(gl,"_token_session",return_value=session_data), \
             patch.object(gl,"_catalog",return_value=catalog), \
             patch.object(gl,"_methods",return_value=[]), \
             patch.object(gl,"_disabled_methods",return_value={}), \
             patch.object(gl,"_bet_rows",return_value=bets), \
             patch.object(gl,"_closed_game_ids",return_value={110}), \
             patch.object(gl,"_fechamentos",return_value=[]):
            before=gl.estado("token")
            self.assertEqual(before["rodada_atual"]["jogos"],2)
            self.assertEqual(before["jogos_finalizados"],1)
            self.assertNotIn(110,[x["jogo_id"] for x in before["jogos"]])
            self.assertEqual(before["entradas"],2)
            self.assertEqual(before["resumo_rodada"],[])
            self.assertNotIn("placar",before["jogos"][0])
            session_data["fase"]="revelada"
            for b in bets:
                b["status"]="green"
                b["lucro_prejuizo"]=Decimal("15.00")
            after=gl.estado("token")
            self.assertNotIn(110,[x["jogo_id"] for x in after["jogos"]])
            self.assertEqual(len(after["resumo_rodada"]),2)
            self.assertEqual([x["placar"] for x in after["resumo_rodada"]],["3 × 1","3 × 1"])
            self.assertEqual(sum(x["lucro_prejuizo"] for x in after["resumo_rodada"]),30)

    def test_registrar_manual_duas_entradas_mesmo_jogo(self):
        from contextlib import contextmanager
        events=[]
        class Cursor:
            last=""
            def execute(self,sql,params):
                events.append((sql,params))
                if "jogos_finalizados" in sql:self.last="closed"
                elif "COALESCE(SUM(stake)" in sql:self.last="balance"
                else:self.last="write"
            def fetchone(self):
                if self.last=="closed":return None
                if self.last=="balance":return {"comprometido":Decimal("0")}
                return {"id":len(events)}
        class Conn:
            def cursor(self):
                @contextmanager
                def c():
                    yield Cursor()
                return c()
            def commit(self):pass
        @contextmanager
        def conn():
            yield Conn()
        with patch.object(gl,"_lock",return_value=session()), \
             patch.object(gl,"_catalog",return_value=fixtures()), \
             patch.object(gl,"_market",return_value={
                 "mercado":"over_25","odd":1.8,"estimada":False,
                 "favorito_casa":True}), \
             patch.object(gl,"get_conn",conn):
            for amount in ("20.00","1100.00"):
                result=gl.registrar("token",{
                    "jogo_id":110,"tipo":"manual","mercado":"over_25",
                    "stake":amount})
                self.assertIn("programada",result["mensagem"])
                self.assertEqual(result["entrada"]["stake"],float(amount))
                self.assertEqual(result["entrada"]["mercado"],"over_25")
                self.assertEqual(result["entrada"]["status"],"pendente")
                self.assertEqual(result["versao"],2)
        inserts=[(sql,params) for sql,params in events
                 if "INSERT INTO galileu_private.entradas" in sql]
        self.assertEqual(len(inserts),2)
        self.assertEqual([params[9] for _,params in inserts],
                         [Decimal("20.00"),Decimal("1100.00")])

    def test_validacao_da_entrada_recalcula_somente_metodo_selecionado(self):
        from contextlib import contextmanager
        from unittest.mock import Mock
        catalog=fixtures()
        methods=[
            {"id":7,"versao":3,"nome":"Over 2,5","objetivo":"over_25",
             "condicoes":[],"ligas":set(),"jogos":20},
            {"id":8,"versao":3,"nome":"Lay Zebra","objetivo":"lay_zebra",
             "condicoes":[],"ligas":set(),"jogos":20},
        ]
        class Cursor:
            last=""
            def execute(self,sql,params):
                if "jogos_finalizados" in sql:self.last="closed"
                elif "COALESCE(SUM(stake)" in sql:self.last="balance"
                elif "INSERT INTO galileu_private.entradas" in sql:self.last="insert"
                else:self.last="write"
            def fetchone(self):
                if self.last=="closed":return None
                if self.last=="balance":return {"comprometido":Decimal("0")}
                if self.last=="insert":return {"id":999}
                return {}
        class Conn:
            def cursor(self):
                @contextmanager
                def cursor_context():
                    yield Cursor()
                return cursor_context()
            def commit(self):pass
        @contextmanager
        def fake_conn():
            yield Conn()
        def validate(game,h,a,selected):
            self.assertEqual([m["id"] for m in selected],[8])
            return [{
                "id":8,"nome":"Lay Zebra","versao":3,"objetivo":"lay_zebra",
                "mercado":{"odd":3.15,"estimada":True,"favorito_casa":True}
            }]
        with patch.object(gl,"_catalog",return_value=catalog), \
             patch.object(gl,"_lock",return_value=session()), \
             patch.object(gl,"_methods",return_value=methods), \
             patch.object(gl,"_history",return_value={}), \
             patch.object(gl,"_team_stats",return_value=({},5)) as stats_mock, \
             patch.object(gl,"_matched",side_effect=validate) as matched_mock, \
             patch.object(gl,"get_conn",fake_conn):
            result=gl.registrar("token",{
                "jogo_id":110,"tipo":"metodo","stake":"20.00",
                "metodo_id":8,"metodo_versao":3
            })
        self.assertEqual(matched_mock.call_count,1)
        self.assertEqual(stats_mock.call_count,2)
        self.assertEqual(result["entrada"]["id"],999)
        self.assertEqual(result["entrada"]["metodo_id"],8)
        self.assertEqual(result["entrada"]["metodo"],"Lay Zebra")
        self.assertEqual(result["entrada"]["status"],"pendente")
        self.assertIsNone(result["entrada"]["lucro_prejuizo"])

    def test_historico_reutilizado_no_mesmo_catalogo(self):
        rows=fixtures()
        gl._history_catalog=None
        gl._history_data=None
        with patch.object(ns,"_history_item",wraps=ns._history_item) as spy:
            first=gl._history(rows)
            self.assertGreater(spy.call_count,0)
            calls=spy.call_count
            second=gl._history(rows)
            self.assertIs(second,first)
            self.assertEqual(spy.call_count,calls)
            # Novo catálogo após atualização invalida o histórico.
            another=gl._history(list(rows))
            self.assertIsNot(another,first)
            self.assertGreater(spy.call_count,calls)

    def test_fechar_jogo_individual_registra_progresso_sem_apurar_ou_deletar(self):
        from contextlib import contextmanager
        events=[]
        class Cursor:
            def execute(self,sql,params):events.append((sql,params))
            def fetchone(self):return {"jogo_id":110}
        class Conn:
            def cursor(self):
                @contextmanager
                def c():
                    yield Cursor()
                return c()
            def commit(self):pass
        @contextmanager
        def conn():
            yield Conn()
        with patch.object(gl,"_catalog",return_value=fixtures()), \
             patch.object(gl,"_lock",return_value=session()), \
             patch.object(gl,"get_conn",conn):
            result=gl.finalizar_jogo("token",{"jogo_id":110})
            self.assertIn("removido da lista",result["mensagem"])
            with self.assertRaisesRegex(ValueError,"fora da rodada"):
                gl.finalizar_jogo("token",{"jogo_id":99999})
        self.assertTrue(any("INSERT INTO galileu_private.jogos_finalizados"
                            in sql for sql,_ in events))
        self.assertTrue(any("versao=versao+1" in sql for sql,_ in events))
        self.assertTrue(all("DELETE" not in sql for sql,_ in events))
        self.assertTrue(all("lucro_prejuizo" not in sql for sql,_ in events))

    def test_registrar_recusa_jogo_individual_finalizado(self):
        from contextlib import contextmanager
        class Cursor:
            def execute(self,sql,params):pass
            def fetchone(self):return {"exists":1}
        class Conn:
            def cursor(self):
                @contextmanager
                def c():
                    yield Cursor()
                return c()
        @contextmanager
        def conn():
            yield Conn()
        with patch.object(gl,"_lock",return_value=session()), \
             patch.object(gl,"_catalog",return_value=fixtures()), \
             patch.object(gl,"get_conn",conn):
            with self.assertRaisesRegex(ValueError,"finalizado"):
                gl.registrar("token",{"jogo_id":110,"tipo":"manual",
                                     "stake":"20.00","mercado":"over_25"})

    def test_apuracao_continua_incluindo_varias_entradas_de_jogo_fechado(self):
        from contextlib import contextmanager
        events=[]
        items=[{"id":1,"jogo_id":110,"mercado":"over_25",
                "favorito_casa":True,"odd":Decimal("1.8"),
                "stake":Decimal("20.00")},
               {"id":2,"jogo_id":110,"mercado":"back_mandante",
                "favorito_casa":True,"odd":Decimal("1.65"),
                "stake":Decimal("15.00")}]
        class Cursor:
            last=""
            def execute(self,sql,params):
                self.last="SELECT" if "SELECT * FROM galileu_private.entradas" in sql else "UPDATE"
                events.append((sql,params))
            def fetchall(self):
                return items if self.last=="SELECT" else []
        class Conn:
            def cursor(self):
                @contextmanager
                def c():
                    yield Cursor()
                return c()
            def commit(self):pass
        @contextmanager
        def conn():
            yield Conn()
        with patch.object(gl,"_lock",return_value=session()), \
             patch.object(gl,"_catalog",return_value=fixtures()), \
             patch.object(gl,"get_conn",conn):
            gl.finalizar("token")
        payout=[params for sql,params in events
                if "UPDATE galileu_private.entradas" in sql]
        self.assertEqual(len(payout),2)
        self.assertEqual([x[0] for x in payout],["green","green"])
        self.assertEqual([x[1] for x in payout],
                         [Decimal("16.00"),Decimal("9.75")])
        self.assertTrue(any("UPDATE galileu_private.sessoes" in sql for sql,_ in events))

    def test_entrada_em_lote_somente_metodos_novos_com_commit_unico(self):
        from contextlib import contextmanager
        from psycopg2 import extras
        sess=session()
        events=[]
        committed=[]
        existing={(110,7)}
        catalog=fixtures()
        methods=[
            {"id":7,"versao":3,"nome":"Over 2,5","objetivo":"over_25",
             "condicoes":[],"ligas":set(),"jogos":20},
            {"id":8,"versao":3,"nome":"Lay Zebra","objetivo":"lay_zebra",
             "condicoes":[],"ligas":set(),"jogos":20},
        ]
        class Cursor:
            query=""
            saved=[]
            def execute(self,sql,params):
                self.query=sql
                events.append((sql,params))
            def fetchall(self):
                if "jogos_finalizados" in self.query:return []
                if "SELECT jogo_id,metodo_id" in self.query:
                    return [{"jogo_id":gid,"metodo_id":mid} for gid,mid in existing]
                return self.saved
            def fetchone(self):
                return {"comprometido":Decimal("20.00")}
        class Conn:
            def cursor(self):
                @contextmanager
                def ctx():
                    yield cur
                return ctx()
            def commit(self):committed.append(True)
        cur=Cursor()
        @contextmanager
        def conn():
            yield Conn()
        def matched(g,h,a,selected):
            m=selected[0]
            return [{"id":m["id"],"mercado":{
                "odd":1.8,"estimada":False,"favorito_casa":True}}]
        def batch(cursor,query,values,page_size):
            self.assertEqual(page_size,len(values))
            events.append((query,values))
            cursor.saved=[
                {"id":i+1,"jogo_id":v[1],"tipo":"metodo","metodo_id":v[4],
                 "metodo_nome":v[6],"mercado":v[7],"odd":Decimal("1.8"),
                 "stake":v[9]}
                for i,v in enumerate(values)]
            cursor.query="INSERT"
        payload={"stake":"20.00","versao":1,"selecoes":[
            {"jogo_id":110,"metodo_id":7,"metodo_versao":3},
            {"jogo_id":110,"metodo_id":8,"metodo_versao":3},
            {"jogo_id":120,"metodo_id":7,"metodo_versao":3}]}
        with patch.object(gl,"_catalog",return_value=catalog), \
             patch.object(gl,"_lock",return_value=sess), \
             patch.object(gl,"_methods",return_value=methods), \
             patch.object(gl,"_history",return_value={}), \
             patch.object(gl,"_team_stats",return_value=({},8)), \
             patch.object(gl,"_matched",side_effect=matched) as spy, \
             patch.object(gl,"get_conn",conn), \
             patch.object(extras,"execute_values",side_effect=batch) as inserted:
            result=gl.registrar_metodos_em_lote("token",payload)
        self.assertEqual(len(result["entradas"]),2)
        self.assertEqual(result["ignoradas"],1)
        self.assertEqual(result["versao"],2)
        self.assertEqual([(x["jogo_id"],x["metodo_id"]) for x in result["entradas"]],
                         [(110,8),(120,7)])
        self.assertTrue(all(x["status"]=="pendente" for x in result["entradas"]))
        self.assertTrue(all(x["lucro_prejuizo"] is None for x in result["entradas"]))
        self.assertEqual(spy.call_count,2)
        self.assertEqual(inserted.call_count,1)
        self.assertEqual(len(committed),1)

    def test_lote_sessao_antiga_nao_grava_parcial(self):
        from contextlib import contextmanager
        from psycopg2 import extras
        sess=session()
        committed=[]
        class Cursor:
            query=""
            def execute(self,sql,params):self.query=sql
            def fetchall(self):return []
            def fetchone(self):return None
        cur=Cursor()
        class Conn:
            def cursor(self):
                @contextmanager
                def ctx():yield cur
                return ctx()
            def commit(self):committed.append(True)
        @contextmanager
        def conn():yield Conn()
        payload={"stake":"1100.00","versao":999,"selecoes":[
            {"jogo_id":110,"metodo_id":7,"metodo_versao":3}]}
        with patch.object(gl,"_catalog",return_value=fixtures()), \
             patch.object(gl,"_lock",return_value=sess), \
             patch.object(gl,"get_conn",conn), \
             patch.object(extras,"execute_values") as inserted:
            with self.assertRaisesRegex(ValueError,"modificada em outra aba"):
                gl.registrar_metodos_em_lote("token",payload)
        inserted.assert_not_called()
        self.assertEqual(committed,[])

    def test_lote_rejeita_duplicidade_na_requisicao_sem_tocar_banco(self):
        item={"jogo_id":110,"metodo_id":7,"metodo_versao":3}
        with patch.object(gl,"_catalog",side_effect=AssertionError("não consultar banco")):
            with self.assertRaisesRegex(ValueError,"mais de uma vez"):
                gl.registrar_metodos_em_lote("token",{
                    "stake":"20.00","versao":1,"selecoes":[item,item]})

    def test_fechamento_em_mes_sem_jogos_e_obrigatorio(self):
        from contextlib import contextmanager
        sess=session(phase="aberta")
        sess["corte"]=date(2025,1,21)
        sess["corte_atual"]=date(2025,1,21)
        sess["mes_base"]="2025-01"
        catalog=[{"id":10,"data":date(2025,2,2),"campeonato_id":1}]
        rounds=gl._rounds(sess["corte_atual"],catalog)
        self.assertEqual(gl._round_at(rounds,0),[])
        self.assertEqual(gl._closing_boundary(rounds),(True,"2025-01",True))
        statements=[]
        class Cursor:
            def execute(self,sql,params):statements.append((sql,params))
            def fetchone(self):return None
        class Conn:
            def cursor(self):
                @contextmanager
                def ctx():yield Cursor()
                return ctx()
            def commit(self):statements.append(("COMMIT",None))
        @contextmanager
        def fake_conn():yield Conn()
        with patch.object(gl,"_catalog",return_value=catalog), \
             patch.object(gl,"_lock",return_value=sess), \
             patch.object(gl,"get_conn",fake_conn):
            with self.assertRaisesRegex(ValueError,"fechamento mensal"):
                gl.proxima("token")
            self.assertFalse(any("UPDATE" in sql for sql,_ in statements))
            result=gl.fechar_mes("token",{
                "fazer_aporte":False,"fazer_saque":False,
                "alterar_stake":False})
        self.assertEqual(result["mes"],"2025-01")
        self.assertEqual(result["banca_base_seguinte"],1022)
        self.assertTrue(any("INSERT INTO galileu_private.fechamentos_mensais"
                            in sql for sql,_ in statements))

    def test_relatorio_mensal_separa_lucro_de_aporte_saque(self):
        bets=[
            {"data":date(2025,1,10),"status":"green","stake":Decimal("20"),
             "lucro_prejuizo":Decimal("10"),"metodo_nome":"Método A",
             "tipo":"metodo","campeonato":"Liga 1",
             "mandante":"A","visitante":"B"},
            {"data":date(2025,2,4),"status":"red","stake":Decimal("20"),
             "lucro_prejuizo":Decimal("-20"),"metodo_nome":"Método A",
             "tipo":"metodo","campeonato":"Liga 1",
             "mandante":"A","visitante":"B"},
        ]
        closings=[{"mes":"2025-01","banca_base_inicio":Decimal("1000"),
                   "banca_fechamento":Decimal("1010"),
                   "aporte":Decimal("100"),"saque":Decimal("50"),
                   "banca_base_seguinte":Decimal("1060")}]
        result=gl._summary(bets,Decimal("1000"),closings)
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]["banca_inicio"],1000)
        self.assertEqual(result[0]["banca_fechamento"],1010)
        self.assertEqual(result[0]["lucro_prejuizo"],10)
        self.assertEqual(result[0]["aporte"],100)
        self.assertEqual(result[0]["saque"],50)
        self.assertEqual(result[0]["banca_fim"],1060)
        self.assertEqual(result[0]["roi"],50)
        self.assertEqual(result[1]["banca_inicio"],1060)
        self.assertEqual(result[1]["banca_fechamento"],1040)
        self.assertEqual(result[1]["banca_fim"],1040)
        self.assertEqual(result[1]["roi"],-100)

    def test_fechar_mes_registra_movimentos_e_nova_base_uma_vez(self):
        from contextlib import contextmanager
        sess=session(phase="revelada")
        sess["corte_atual"]=date(2026,10,20)
        sess["banca_atual"]=Decimal("1010")
        rows=fixtures()
        executed=[]
        class Cursor:
            def execute(self,sql,params):executed.append((sql,params))
            def fetchone(self):return None
        class Conn:
            def cursor(self):
                @contextmanager
                def c():yield Cursor()
                return c()
            def commit(self):executed.append(("COMMIT",None))
        @contextmanager
        def fake_conn():yield Conn()
        payload={"fazer_aporte":True,"aporte":"100.00",
                 "fazer_saque":True,"saque":"25.00",
                 "alterar_stake":True,"tipo_stake":"percentual",
                 "valor_stake":"3.00"}
        with patch.object(gl,"_catalog",return_value=rows), \
             patch.object(gl,"_lock",return_value=sess), \
             patch.object(gl,"get_conn",fake_conn):
            outcome=gl.fechar_mes("token",payload)
        self.assertEqual(outcome["banca_fechamento"],1010)
        self.assertEqual(outcome["banca_base_seguinte"],1085)
        kinds=[params[2] for sql,params in executed
               if "INSERT INTO galileu_private.movimentacoes" in sql]
        self.assertEqual(kinds,["aporte","saque","reajuste_stake","virada_mes"])
        closing=[params for sql,params in executed
                 if "INSERT INTO galileu_private.fechamentos_mensais" in sql][0]
        self.assertEqual(closing[3],Decimal("1000"))
        self.assertEqual(closing[7],Decimal("1085"))
        update=[params for sql,params in executed
                if "UPDATE galileu_private.sessoes SET" in sql][0]
        self.assertEqual(update[:3],(Decimal("1085"),Decimal("1085"),"2026-11"))
        self.assertEqual(update[3],Decimal("3.00"))
        self.assertEqual(executed[-1][0],"COMMIT")

    def test_fechar_mes_sem_movimentos_mantem_percentual(self):
        from contextlib import contextmanager
        sess=session(phase="revelada")
        sess["corte_atual"]=date(2026,10,20)
        executed=[]
        class Cursor:
            def execute(self,sql,params):executed.append((sql,params))
            def fetchone(self):return None
        class Conn:
            def cursor(self):
                @contextmanager
                def ctx():yield Cursor()
                return ctx()
            def commit(self):pass
        @contextmanager
        def fake_conn():yield Conn()
        with patch.object(gl,"_catalog",return_value=fixtures()), \
             patch.object(gl,"_lock",return_value=sess), \
             patch.object(gl,"get_conn",fake_conn):
            response=gl.fechar_mes("token",{
                "fazer_aporte":False,"fazer_saque":False,"alterar_stake":False})
        self.assertEqual(response["banca_base_seguinte"],1022)
        kinds=[params[2] for sql,params in executed
               if "INSERT INTO galileu_private.movimentacoes" in sql]
        self.assertEqual(kinds,["virada_mes"])
        update=[params for sql,params in executed
                if "UPDATE galileu_private.sessoes SET" in sql][0]
        self.assertEqual(update[3],Decimal("2.00"))
        self.assertIsNone(update[4])

    def test_fechamento_rejeita_saque_superior_e_duplicidade(self):
        from contextlib import contextmanager
        sess=session(phase="revelada")
        sess["corte_atual"]=date(2026,10,20)
        sql=[]
        class Cursor:
            def __init__(self,existing):self.existing=existing
            def execute(self,query,params):sql.append(query)
            def fetchone(self):return {"ok":1} if self.existing else None
        class Conn:
            def __init__(self,existing):self.existing=existing
            def cursor(self):
                @contextmanager
                def ctx():yield Cursor(self.existing)
                return ctx()
            def commit(self):pass
        @contextmanager
        def fake_conn():yield Conn(False)
        invalid={"fazer_aporte":False,"fazer_saque":True,
                 "saque":"2000.00","alterar_stake":False}
        with patch.object(gl,"_catalog",return_value=fixtures()), \
             patch.object(gl,"_lock",return_value=sess), \
             patch.object(gl,"get_conn",fake_conn):
            with self.assertRaisesRegex(ValueError,"Saque maior"):
                gl.fechar_mes("token",invalid)
        self.assertFalse(any("INSERT" in q for q in sql))
        sql.clear()
        @contextmanager
        def existing_conn():yield Conn(True)
        with patch.object(gl,"_catalog",return_value=fixtures()), \
             patch.object(gl,"_lock",return_value=sess), \
             patch.object(gl,"get_conn",existing_conn):
            with self.assertRaisesRegex(ValueError,"já foi fechado"):
                gl.fechar_mes("token",{
                    "fazer_aporte":False,"fazer_saque":False,"alterar_stake":False})
        self.assertFalse(any("INSERT" in q for q in sql))

    def test_avancar_mes_exige_fechamento_financeiro(self):
        from contextlib import contextmanager
        sess=session(phase="revelada")
        sess["corte_atual"]=date(2026,10,20)
        executed=[]
        class Cursor:
            def execute(self,sql,params):executed.append(sql)
            def fetchone(self):return None
        class Conn:
            def cursor(self):
                @contextmanager
                def ctx():yield Cursor()
                return ctx()
            def commit(self):pass
        @contextmanager
        def fake_conn():yield Conn()
        with patch.object(gl,"_catalog",return_value=fixtures()), \
             patch.object(gl,"_lock",return_value=sess), \
             patch.object(gl,"get_conn",fake_conn):
            with self.assertRaisesRegex(ValueError,"fechamento mensal"):
                gl.proxima("token")
        self.assertFalse(any("UPDATE galileu_private.sessoes" in q for q in executed))

    def test_retirar_metodo_e_imediato_e_cancela_pendentes(self):
        from contextlib import contextmanager
        actions=[]
        class Cursor:
            last=""
            def execute(self,sql,params):
                self.last=sql
                actions.append((sql,params))
            def fetchone(self):
                if "INSERT INTO galileu_private.metodos_desativados" in self.last:
                    return {"metodo_id":7}
                return None
            def fetchall(self):
                if "DELETE FROM galileu_private.entradas" in self.last:
                    return [{"id":100},{"id":101}]
                return []
        class Conn:
            def cursor(self):
                @contextmanager
                def ctx():yield Cursor()
                return ctx()
            def commit(self):actions.append(("COMMIT",None))
        @contextmanager
        def fake_conn():yield Conn()
        methods=[{"id":7,"nome":"Over 2,5"}]
        with patch.object(gl,"_methods",return_value=methods), \
             patch.object(gl,"_lock",return_value=session()), \
             patch.object(gl,"get_conn",fake_conn):
            result=gl.retirar_metodo("token",{"metodo_id":7})
        self.assertEqual(result["metodo_id"],7)
        self.assertEqual(result["entradas_canceladas"],2)
        inserted=[params for sql,params in actions
                  if "INSERT INTO galileu_private.metodos_desativados" in sql]
        self.assertEqual(inserted,[("session_uuid",7,"Over 2,5","2026-10")])
        deleted=[sql for sql,_ in actions if "DELETE FROM galileu_private.entradas" in sql]
        self.assertEqual(len(deleted),1)
        self.assertIn("status='pendente'",deleted[0])
        self.assertIn("tipo='metodo'",deleted[0])
        self.assertTrue(any("versao=versao+1" in sql for sql,_ in actions))
        self.assertEqual(actions[-1][0],"COMMIT")

    def test_retirar_metodo_nao_apaga_resultados_e_oculta_marcacoes(self):
        method={"id":7,"versao":3,"nome":"Over 2,5","objetivo":"over_25",
                "condicoes":[],"ligas":set(),"jogos":20}
        disabled={7:{"desde":"2026-10","nome":"Over 2,5"}}
        games=fixtures()
        with patch.object(gl,"_history",return_value={}), \
             patch.object(gl,"_team_stats",return_value=({},5)), \
             patch.object(gl,"_available_markets",return_value=[]), \
             patch.object(gl,"_matched") as matched:
            _,public=gl._games_for_session(
                session(),games,gl._rounds(date(2026,10,17),games),
                methods=[method],disabled=disabled)
        self.assertTrue(public)
        self.assertTrue(all(not game["metodos"] for game in public))
        matched.assert_not_called()
        self.assertTrue(gl._is_disabled(7,date(2026,10,20),disabled))
        self.assertTrue(gl._is_disabled(7,date(2026,11,20),disabled))

    def test_registrar_entrada_rejeita_metodo_retirado_mesmo_no_mes(self):
        from contextlib import contextmanager
        actions=[]
        class Cursor:
            last=""
            def execute(self,sql,params):
                self.last=sql
                actions.append(sql)
            def fetchone(self):
                if "metodos_desativados" in self.last:
                    return {"efetivo_desde":"2026-11"}
                return None
        class Conn:
            def cursor(self):
                @contextmanager
                def ctx():yield Cursor()
                return ctx()
            def commit(self):raise AssertionError("Não deveria registrar entrada")
        @contextmanager
        def fake_conn():yield Conn()
        with patch.object(gl,"_catalog",return_value=fixtures()), \
             patch.object(gl,"_lock",return_value=session()), \
             patch.object(gl,"get_conn",fake_conn):
            with self.assertRaisesRegex(ValueError,"Método retirado"):
                gl.registrar("token",{
                    "jogo_id":110,"tipo":"metodo","stake":"20.00",
                    "metodo_id":7,"metodo_versao":3})
        self.assertFalse(any("INSERT INTO galileu_private.entradas" in q for q in actions))

    def test_lote_nao_insere_metodo_retirado(self):
        from contextlib import contextmanager
        actions=[]
        class Cursor:
            last=""
            def execute(self,sql,params):
                self.last=sql
                actions.append(sql)
            def fetchall(self):
                if "SELECT metodo_id,efetivo_desde" in self.last:
                    return [{"metodo_id":7,"efetivo_desde":"2026-10"}]
                return []
        class Conn:
            def cursor(self):
                @contextmanager
                def ctx():yield Cursor()
                return ctx()
            def commit(self):raise AssertionError("Não deveria confirmar o lote")
        @contextmanager
        def fake_conn():yield Conn()
        method={"id":7,"versao":3,"nome":"Over 2,5","objetivo":"over_25",
                "condicoes":[],"ligas":set(),"jogos":20}
        with patch.object(gl,"_catalog",return_value=fixtures()), \
             patch.object(gl,"_lock",return_value=session()), \
             patch.object(gl,"_methods",return_value=[method]), \
             patch.object(gl,"get_conn",fake_conn):
            with self.assertRaisesRegex(ValueError,"métodos foi alterado"):
                gl.registrar_metodos_em_lote("token",{
                    "stake":"20.00","versao":1,
                    "selecoes":[{"jogo_id":110,"metodo_id":7,"metodo_versao":3}]})
        self.assertFalse(any("INSERT INTO galileu_private.entradas" in q for q in actions))

    def test_report_api_sem_sessao_nao_carrega_dados_privados(self):
        with patch.object(gl,"fetch_all",side_effect=AssertionError("Sem consultas")):
            self.assertEqual(gl.relatorios(None),{"iniciado":False})

    def test_token_hash_nao_retorna_token(self):
        digest=gl._hash("token-secreto-e-aleatorio")
        self.assertEqual(len(digest),64)
        self.assertNotEqual(digest,"token-secreto-e-aleatorio")
        self.assertIsNone(gl._hash(None))


if __name__=="__main__":
    import unittest
    unittest.main()
