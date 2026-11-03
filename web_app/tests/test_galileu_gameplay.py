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
        self.assertEqual(gl._default_stake(s),20.44)
        s["stake_fixa"]=Decimal("23.55")
        self.assertEqual(gl._default_stake(s),23.55)
        self.assertEqual(gl._money("20.00","Stake"),Decimal("20.00"))
        for bad in ("-1","0","2.999","NaN","Infinity",True,None,""):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                gl._money(bad,"Stake")
        for bad in (0,101,-1,"1.222",None):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                gl._pct(bad)

    def test_rodadas_seguem_competicao_e_ordem_de_datas(self):
        catalog=fixtures()
        rounds=gl._rounds(date(2026,10,17),catalog)
        first=gl._round_at(rounds,0)
        second=gl._round_at(rounds,1)
        self.assertEqual(len(first),2)
        self.assertEqual(len(second),2)
        self.assertEqual({r["campeonato_id"] for r in first},{1,2})
        self.assertTrue(all(r["rodada"]=="Rodada 9" for r in first))
        self.assertTrue(all(r["rodada"]=="Rodada 10" for r in second))
        done,month=gl._monthly_boundary(rounds,0)
        self.assertFalse(done)
        self.assertIsNone(month)

    def test_corte_31_dez_nao_exibe_marco_2025_na_rodada_um(self):
        def item(number,day,league=1):
            return {"id":number,"data":date.fromisoformat(day),
                    "campeonato_id":league}
        catalog=[
            item(1,"2025-01-01"),item(2,"2025-01-03",2),
            item(3,"2025-01-10"),item(4,"2025-01-11"),
            item(5,"2025-01-20"),item(6,"2025-03-30",3),
        ]
        rounds=gl._rounds(date(2024,12,31),catalog)
        self.assertEqual([g["id"] for g in gl._round_at(rounds,0)],[1,2,3])
        self.assertEqual(rounds[0]["corte"],date(2024,12,31))
        self.assertEqual(rounds[0]["limite"],date(2025,1,10))
        self.assertEqual(rounds[0]["proximo_corte"],date(2025,1,10))
        self.assertEqual([g["id"] for g in gl._round_at(rounds,1)],[4,5])
        self.assertEqual(rounds[1]["corte"],date(2025,1,10))
        self.assertEqual(rounds[1]["limite"],date(2025,1,20))
        self.assertNotIn(6,[g["id"] for g in gl._round_at(rounds,0)])

    def test_corte_25_jan_limita_jan_e_abre_fev_somente_depois(self):
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
        self.assertEqual(rounds[1]["limite"],date(2025,2,10))
        self.assertEqual(gl._monthly_boundary(rounds,0),(True,"2025-01"))

    def test_ultimo_jogo_antecede_final_mes_sem_cruzar_janeiro(self):
        catalog=[
            {"id":1,"data":date(2025,1,27),"campeonato_id":1},
            {"id":2,"data":date(2025,2,1),"campeonato_id":2},
        ]
        rounds=gl._rounds(date(2025,1,25),catalog)
        self.assertEqual(rounds[0]["limite"],date(2025,1,31))
        self.assertEqual(rounds[0]["proximo_corte"],date(2025,1,27))
        self.assertFalse(rounds[1]["jogos"])
        self.assertEqual(rounds[1]["proximo_corte"],date(2025,1,31))
        self.assertEqual(rounds[2]["corte"],date(2025,1,31))
        self.assertEqual([g["id"] for g in rounds[2]["jogos"]],[2])
        # O resumo de janeiro aparece na última rodada COM jogos,
        # não fica esperando o período vazio de 28 a 31.
        self.assertEqual(gl._monthly_boundary(rounds,0),(True,"2025-01"))

    def test_periodos_sem_jogos_nao_pulam_mais_de_dez_dias(self):
        catalog=[{"id":8,"data":date(2025,3,30),"campeonato_id":1}]
        rounds=gl._rounds(date(2024,12,31),catalog)
        self.assertTrue(len(rounds)>5)
        self.assertEqual(rounds[0]["limite"],date(2025,1,10))
        self.assertEqual(gl._round_at(rounds,0),[])
        self.assertEqual(rounds[-1]["jogos"][0]["id"],8)
        for window in rounds:
            self.assertLessEqual((window["limite"]-window["corte"]).days,10)
            self.assertEqual(window["limite"].month,
                             (window["corte"]+timedelta(days=1)).month)
        for one,two in zip(rounds,rounds[1:]):
            self.assertEqual(two["corte"],one["proximo_corte"])

    def test_proxima_atualiza_corte_sem_alterar_corte_inicial(self):
        from contextlib import contextmanager
        catalog=fixtures()
        sess=session(phase="revelada")
        executed=[]
        class Cursor:
            def execute(self,sql,params):
                executed.append((sql,params))
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
        self.assertEqual(result["corte_atual"],"2026-10-20")
        self.assertTrue(any("corte_atual=%s" in sql for sql,_ in executed))
        self.assertFalse(any(" SET corte=" in sql for sql,_ in executed))
        params=executed[-1][1]
        self.assertEqual(params[1],date(2026,10,20))
        self.assertEqual(params[2],"aberta")

    def test_estado_retomado_usa_ultimo_corte_salvo_nao_indice(self):
        catalog=fixtures()
        sess=session()
        sess["corte_atual"]=date(2026,10,20)
        sess["indice_rodada"]=1
        with patch.object(gl,"_token_session",return_value=sess), \
             patch.object(gl,"_catalog",return_value=catalog), \
             patch.object(gl,"_methods",return_value=[]), \
             patch.object(gl,"_bet_rows",return_value=[]):
            result=gl.estado("token")
        self.assertEqual(result["corte"],"2026-10-17")
        self.assertEqual(result["corte_atual"],"2026-10-20")
        self.assertEqual(result["limite_janela"],"2026-10-30")
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
             patch.object(gl,"_bet_rows",return_value=[]):
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

    def test_token_hash_nao_retorna_token(self):
        digest=gl._hash("token-secreto-e-aleatorio")
        self.assertEqual(len(digest),64)
        self.assertNotEqual(digest,"token-secreto-e-aleatorio")
        self.assertIsNone(gl._hash(None))


if __name__=="__main__":
    import unittest
    unittest.main()
