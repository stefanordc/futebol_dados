"""Regressões da apuração mensal sem limite de saldo no Galileu."""
from datetime import date
from decimal import Decimal
from unittest import TestCase

import queries_galileu_gameplay as gl


def jogo(jid,day,home=2,away=0):
    return {"id":jid,"data":date.fromisoformat(day),
            "gols_casa":home,"gols_fora":away}


def entrada(eid,jid,stake,odd="2.00",market="back_mandante"):
    return {"id":eid,"jogo_id":jid,"stake":Decimal(stake),"odd":Decimal(odd),
            "mercado":market,"favorito_casa":True}


class TestProgramadas(TestCase):
    def test_entradas_em_dias_diferentes_podem_superar_a_banca_original(self):
        games={1:jogo(1,"2025-01-01"),2:jogo(2,"2025-01-02",0,2),
               3:jogo(3,"2025-01-03")}
        entries=[entrada(1,1,"80"),entrada(2,2,"110"),entrada(3,3,"20")]
        result,bank=gl._liquidar_entradas_por_data(entries,games,Decimal("100"))
        self.assertEqual([r[1] for r in result],["green","red","green"])
        self.assertEqual([r[2] for r in result],
                         [Decimal("80.00"),Decimal("-110.00"),Decimal("20.00")])
        self.assertEqual(bank,Decimal("90.00"))
        self.assertGreater(sum(r["stake"] for r in entries),Decimal("100"))

    def test_todas_entradas_sao_liquidadas_mesmo_com_saldo_baixo(self):
        games={1:jogo(1,"2025-01-01",0,2),2:jogo(2,"2025-01-02")}
        entries=[entrada(11,1,"80"),entrada(12,2,"30")]
        result,bank=gl._liquidar_entradas_por_data(entries,games,Decimal("100"))
        self.assertEqual(result,[(11,"red",Decimal("-80.00")),
                                 (12,"green",Decimal("30.00"))])
        self.assertEqual(bank,Decimal("50.00"))

    def test_mesmo_dia_liquida_todas_as_entradas(self):
        games={1:jogo(1,"2025-01-01"),2:jogo(2,"2025-01-01"),
               3:jogo(3,"2025-01-02")}
        entries=[entrada(10,1,"80"),entrada(11,2,"80"),entrada(12,3,"80")]
        result,bank=gl._liquidar_entradas_por_data(entries,games,Decimal("100"))
        self.assertEqual([r[1] for r in result],["green","green","green"])
        self.assertEqual(bank,Decimal("340.00"))
        self.assertEqual(result[1][2],Decimal("80.00"))

    def test_mesmo_dia_ordenacao_por_id_sem_prioridade_de_saldo(self):
        games={1:jogo(1,"2025-01-01"),2:jogo(2,"2025-01-01",0,2)}
        entries=[entrada(12,2,"60"),entrada(10,1,"60")]
        result,bank=gl._liquidar_entradas_por_data(entries,games,Decimal("100"))
        self.assertEqual(result,[(10,"green",Decimal("60.00")),
                                 (12,"red",Decimal("-60.00"))])
        self.assertEqual(bank,Decimal("100.00"))

    def test_lay_e_back_sempre_apurados_no_mesmo_dia(self):
        games={1:jogo(1,"2025-01-01",2,0),2:jogo(2,"2025-01-01",2,0)}
        entries=[entrada(1,1,"80","3.00","lay_zebra"),entrada(2,2,"30")]
        result,bank=gl._liquidar_entradas_por_data(entries,games,Decimal("100"))
        self.assertEqual(result[0],(1,"green",Decimal("38.20")))
        self.assertEqual(result[1],(2,"green",Decimal("30.00")))
        self.assertEqual(bank,Decimal("168.20"))

    def test_banca_negativa_nao_impede_apuracao(self):
        games={1:jogo(1,"2025-01-01",0,2),2:jogo(2,"2025-01-02",0,2)}
        entries=[entrada(1,1,"120"),entrada(2,2,"80")]
        result,bank=gl._liquidar_entradas_por_data(entries,games,Decimal("100"))
        self.assertEqual(result,[(1,"red",Decimal("-120.00")),
                                 (2,"red",Decimal("-80.00"))])
        self.assertEqual(bank,Decimal("-100.00"))

    def test_apuracao_historica_ainda_identifica_sem_saldo_antigo(self):
        bets=[
            {"data":date(2025,1,1),"status":"green",
             "stake":Decimal("80"),"lucro_prejuizo":Decimal("80"),
             "metodo_nome":"Over 2,5","tipo":"metodo","campeonato":"L1",
             "mandante":"A","visitante":"B"},
            {"data":date(2025,1,2),"status":"sem_saldo",
             "stake":Decimal("80"),"lucro_prejuizo":Decimal("0"),
             "metodo_nome":"Over 2,5","tipo":"metodo","campeonato":"L1",
             "mandante":"A","visitante":"C"},
            {"data":date(2025,1,3),"status":"pendente",
             "stake":Decimal("20"),"lucro_prejuizo":None,
             "metodo_nome":None,"tipo":"manual","campeonato":"L1",
             "mandante":"D","visitante":"E"}
        ]
        x=gl._summary(bets,Decimal("100"))[0]
        self.assertEqual(x["entradas"],3)
        self.assertEqual(x["executadas"],1)
        self.assertEqual(x["nao_executadas"],1)
        self.assertEqual(x["pendentes"],1)
        self.assertEqual(x["greens"],1)
        self.assertEqual(x["reds"],0)
        self.assertEqual(x["lucro_prejuizo"],80.0)
        self.assertEqual(x["roi"],100.0)

    def test_nao_aceita_jogo_ausente(self):
        with self.assertRaisesRegex(ValueError,"não pertence à rodada"):
            gl._liquidar_entradas_por_data([entrada(1,999,"20")],
                                          {},Decimal("100"))

    def test_zero_programacoes_preserva_banca(self):
        updates,bank=gl._liquidar_entradas_por_data([],{},Decimal("42.50"))
        self.assertEqual(updates,[])
        self.assertEqual(bank,Decimal("42.50"))
