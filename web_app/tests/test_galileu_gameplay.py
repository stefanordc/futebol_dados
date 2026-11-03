"""Testes isolados: rodadas, sigilo pré-fechamento, aposta e balanços em reais."""
from datetime import date,timedelta
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch
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
            r=game(100+comp*10+n,first+timedelta(days=10+n*7),
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
