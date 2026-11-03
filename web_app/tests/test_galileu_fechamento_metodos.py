"""Fechamento Galileu: desempenho mensal e retirada futura de métodos."""
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

import queries_galileu_gameplay as gl


def bet(identifier,day,method_id,status,pnl=0,method_name="Método A"):
    return {
        "id":identifier,"data":date.fromisoformat(day),
        "tipo":"metodo" if method_id is not None else "manual",
        "metodo_id":method_id,"metodo_nome":method_name,
        "status":status,"lucro_prejuizo":Decimal(str(pnl)),
        "stake":Decimal("20"),
    }


def method(mid,name):
    return {"id":mid,"versao":1,"nome":name,"objetivo":"over_25",
            "condicoes":[],"ligas":set(),"jogos":20}


class TestFechamentoMetodos(TestCase):
    def test_tabela_mensal_sequencias_somente_executadas(self):
        bets=[
            bet(8,"2026-10-21",7,"green",10),
            bet(6,"2026-10-15",7,"red",-20),
            bet(4,"2026-10-09",7,"green",15),
            bet(5,"2026-10-10",7,"red",-20),
            bet(7,"2026-10-20",7,"sem_saldo",0),
            bet(3,"2026-10-08",7,"green",10),
            bet(9,"2026-10-25",7,"pendente",0),
            bet(1,"2026-10-07",8,"red",-20,method_name="Método B"),
            bet(20,"2026-11-01",7,"red",-20), # Fora do mês
            bet(2,"2026-10-12",None,"green",13,method_name="Manual"),
        ]
        result=gl._method_monthly_table(
            bets,[method(7,"Método A"),method(8,"Método B"),
                  method(9,"Método sem entradas")],{},"2026-10")
        a=next(row for row in result if row["metodo_id"]==7)
        self.assertEqual(a["entradas"],7)
        self.assertEqual(a["executadas"],5)
        self.assertEqual(a["nao_executadas"],1)
        self.assertEqual((a["greens"],a["reds"]),(3,2))
        self.assertEqual(a["win_rate"],60)
        self.assertEqual(a["lucro_prejuizo"],-5.0)
        self.assertEqual((a["maior_good_run"],a["maior_bad_run"]),(2,2))
        self.assertEqual(next(x for x in result if x["metodo_id"]==9)["entradas"],0)
        manual=next(x for x in result if x["metodo_id"] is None)
        self.assertEqual(manual["nome"],"Entradas manuais")
        self.assertFalse(manual["ativo_no_mes"])

    def test_alerta_somente_tres_meses_civis_seguidos_de_prejuizo(self):
        entries=[
            bet(1,"2026-01-12",7,"red",-20,method_name="Lay zebra"),
            bet(2,"2026-02-10",7,"green",8,method_name="Lay zebra"),
            bet(3,"2026-02-11",7,"red",-20,method_name="Lay zebra"),
            bet(4,"2026-03-10",7,"red",-5,method_name="Lay zebra"),
            # Mesmo nome, porém outro ID; não pode misturar métodos.
            bet(5,"2026-01-10",8,"red",-20,method_name="Lay zebra"),
            bet(6,"2026-02-10",8,"green",25,method_name="Lay zebra"),
            bet(7,"2026-03-10",8,"red",-20,method_name="Lay zebra"),
            # Apostas manuais não representam um método.
            bet(8,"2026-01-10",None,"red",-20,method_name="Manual"),
            bet(9,"2026-02-10",None,"red",-20,method_name="Manual"),
            bet(10,"2026-03-10",None,"red",-20,method_name="Manual"),
            # Meses fora da janela não entram na contagem.
            bet(11,"2025-12-10",7,"red",-100,method_name="Lay zebra"),
        ]
        alerts=gl._method_loss_streak_alerts(
            entries,[method(7,"Lay zebra"),method(8,"Lay zebra")],"2026-03")
        self.assertEqual(len(alerts),1)
        self.assertEqual(alerts[0]["metodo_id"],7)
        self.assertEqual(alerts[0]["prejuizo_total"],-37.0)
        self.assertEqual([m["mes"] for m in alerts[0]["meses"]],
                         ["2026-01","2026-02","2026-03"])
        self.assertEqual([m["lucro_prejuizo"] for m in alerts[0]["meses"]],
                         [-20.0,-12.0,-5.0])

    def test_alerta_nao_dispara_com_lucro_no_mes_intermediario(self):
        entries=[
            bet(1,"2026-01-10",7,"red",-20),
            bet(2,"2026-02-10",7,"green",10),
            bet(3,"2026-03-10",7,"red",-20),
        ]
        self.assertEqual(gl._method_loss_streak_alerts(
            entries,[method(7,"Método A")],"2026-03"),[])

    def test_alerta_nao_dispara_com_mes_zerado_ou_sem_execucao(self):
        entries=[
            bet(1,"2026-01-10",7,"red",-20),
            bet(2,"2026-02-10",7,"red",-20),
            bet(3,"2026-03-10",7,"green",20),
            bet(4,"2026-03-11",7,"red",-20),
            bet(5,"2026-01-10",8,"red",-20),
            bet(6,"2026-02-10",8,"sem_saldo",0),
            bet(7,"2026-03-10",8,"red",-20),
            bet(8,"2026-01-10",9,"red",-20),
            bet(9,"2026-03-10",9,"red",-20),
        ]
        self.assertEqual(gl._method_loss_streak_alerts(
            entries,[method(7,"A"),method(8,"B"),method(9,"C")],"2026-03"),[])

    def test_alerta_atravessa_dezembro_para_janeiro(self):
        entries=[
            bet(1,"2026-11-10",7,"red",-5),
            bet(2,"2026-12-10",7,"red",-10),
            bet(3,"2027-01-10",7,"red",-15),
        ]
        alerts=gl._method_loss_streak_alerts(
            entries,[method(7,"A")],"2027-01")
        self.assertEqual(len(alerts),1)
        self.assertEqual([r["mes"] for r in alerts[0]["meses"]],
                         ["2026-11","2026-12","2027-01"])
        # Ainda são apenas dois meses negativos no fechamento de dezembro.
        self.assertEqual(gl._method_loss_streak_alerts(
            entries,[method(7,"A")],"2026-12"),[])

    def test_desativacao_nao_retroage_e_metodo_removido_permanece_listado(self):
        disabled={7:{"nome":"Método antigo","desde":"2026-11"}}
        october=gl._method_monthly_table([],[method(7,"Novo nome")],
                                          disabled,"2026-10")
        november=gl._method_monthly_table([],[],disabled,"2026-11")
        self.assertTrue(october[0]["ativo_no_mes"])
        self.assertEqual(november[0]["nome"],"Método antigo")
        self.assertFalse(november[0]["ativo_no_mes"])
        self.assertTrue(gl._is_disabled(7,date(2026,11,2),disabled))
        self.assertFalse(gl._is_disabled(7,date(2026,10,31),disabled))

    def test_rodada_so_esconde_metodo_no_mes_seguinte(self):
        jan={"id":1,"data":date(2026,1,28),"campeonato_id":1,
             "campeonato":"Liga","temporada":"2026",
             "casa_id":1,"fora_id":2,"mandante":"A","visitante":"B"}
        feb={**jan,"id":2,"data":date(2026,2,2)}
        matches=[{"id":7,"nome":"M","mercado":{"odd":2.0}}]
        with patch.object(gl,"_history",return_value={}), \
             patch.object(gl,"_team_stats",return_value=({"xg":1},10)), \
             patch.object(gl,"_available_markets",return_value=[]), \
             patch.object(gl,"_matched",return_value=matches):
            _,public=gl._games_for_session(
                {"id":"sessao","fase":"aberta"},[],
                [{"jogos":[jan,feb]}],
                methods=[method(7,"M")],
                disabled={7:{"nome":"M","desde":"2026-02"}})
        self.assertEqual(len(public[0]["metodos"]),1)
        self.assertEqual(public[1]["metodos"],[])

    def test_fechamento_grava_retirada_no_mes_seguinte_em_transacao(self):
        calls=[]
        class Cursor:
            def execute(self,query,params):
                calls.append((query,params))
            def fetchone(self): return None
        class Conn:
            def cursor(self):
                @contextmanager
                def ctx(): yield Cursor()
                return ctx()
            def commit(self): calls.append(("COMMIT",None))
        @contextmanager
        def conn(): yield Conn()
        session={
            "id":"sid","fase":"revelada","corte":date(2026,10,17),
            "corte_atual":date(2026,10,20),
            "mes_base":"2026-10","indice_rodada":2,
            "banca_atual":Decimal("1050"),
            "banca_base_mes":Decimal("1000"),
            "gestao_pct":Decimal("2"),"stake_fixa":None,
        }
        payload={"fazer_aporte":False,"fazer_saque":False,
                 "alterar_stake":False,"retirar_metodos":[7,9]}
        with patch.object(gl,"_catalog",return_value=[]), \
             patch.object(gl,"_methods",return_value=[
                 method(7,"Método A"),method(9,"Método sem entradas")]), \
             patch.object(gl,"_rounds",return_value=[]), \
             patch.object(gl,"_closing_boundary",
                          return_value=(True,"2026-10",False)), \
             patch.object(gl,"_lock",return_value=session), \
             patch.object(gl,"get_conn",conn):
            result=gl.fechar_mes("token",payload)
        inserts=[p for q,p in calls if
                 "INSERT INTO galileu_private.metodos_desativados" in q]
        self.assertEqual(inserts,[
            ("sid",7,"Método A","2026-11"),
            ("sid",9,"Método sem entradas","2026-11"),
        ])
        self.assertEqual(result["metodos_retirados"],2)
        self.assertEqual(result["banca_base_seguinte"],1050)
        self.assertEqual(calls[-1][0],"COMMIT")

    def test_retiradas_invalidas_nao_alteram_banco(self):
        payload={"fazer_aporte":False,"fazer_saque":False,
                 "alterar_stake":False}
        for methods in ([7,7],["7"],[0],True,list(range(501))):
            with self.subTest(methods=methods):
                with self.assertRaises(ValueError):
                    gl.fechar_mes("token",{**payload,"retirar_metodos":methods})
        with patch.object(gl,"_catalog",return_value=[]), \
             patch.object(gl,"_methods",return_value=[method(7,"A")]):
            with self.assertRaisesRegex(ValueError,"não está mais cadastrado"):
                gl.fechar_mes("token",{**payload,"retirar_metodos":[888]})

    def test_entrada_individual_rejeita_metodo_desativado(self):
        game={"id":12,"data":date(2026,11,15)}
        session={
            "id":"sid","fase":"aberta","corte":date(2026,10,31),
            "corte_atual":date(2026,10,31),"banca_atual":Decimal("1000"),
        }
        calls=[]
        class Cursor:
            def execute(self,query,params):
                calls.append(query)
            def fetchone(self):
                if "metodos_desativados" in calls[-1]:
                    return {"efetivo_desde":"2026-11"}
                return None
        class Conn:
            def cursor(self):
                @contextmanager
                def ctx(): yield Cursor()
                return ctx()
        @contextmanager
        def conn(): yield Conn()
        with patch.object(gl,"_catalog",return_value=[]), \
             patch.object(gl,"_rounds",return_value=[{"jogos":[game]}]), \
             patch.object(gl,"_lock",return_value=session), \
             patch.object(gl,"get_conn",conn):
            with self.assertRaisesRegex(ValueError,"retirado da gameplay"):
                gl.registrar("token",{
                    "jogo_id":12,"tipo":"metodo","stake":"20.00",
                    "metodo_id":7,"metodo_versao":1})
        self.assertFalse(any("INSERT INTO galileu_private.entradas" in q for q in calls))

    def test_entrada_em_lote_tambem_rejeita_metodo_desativado(self):
        game={"id":12,"data":date(2026,11,15),
              "campeonato_id":1}
        session={
            "id":"sid","fase":"aberta","corte":date(2026,10,31),
            "corte_atual":date(2026,10,31),"banca_atual":Decimal("1000"),
            "versao":1,"indice_rodada":2,
        }
        calls=[]
        class Cursor:
            def execute(self,query,params): calls.append(query)
            def fetchall(self):
                if "metodos_desativados" in calls[-1]:
                    return [{"metodo_id":7,"efetivo_desde":"2026-11"}]
                return []
        class Conn:
            def cursor(self):
                @contextmanager
                def ctx(): yield Cursor()
                return ctx()
        @contextmanager
        def conn(): yield Conn()
        with patch.object(gl,"_catalog",return_value=[]), \
             patch.object(gl,"_rounds",return_value=[{"jogos":[game]}]), \
             patch.object(gl,"_methods",return_value=[method(7,"M")]), \
             patch.object(gl,"_lock",return_value=session), \
             patch.object(gl,"get_conn",conn):
            with self.assertRaisesRegex(ValueError,"foi alterado"):
                gl.registrar_metodos_em_lote("token",{
                    "stake":"20.00","versao":1,
                    "selecoes":[{"jogo_id":12,"metodo_id":7,
                                 "metodo_versao":1}]})
        self.assertFalse(any("INSERT INTO galileu_private.entradas" in q for q in calls))
