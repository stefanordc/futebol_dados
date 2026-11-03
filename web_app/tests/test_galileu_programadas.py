"""Regressões de liquidação cronológica de entradas programadas do Galileu."""
from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

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

    def test_se_faltar_saldo_futuro_a_entrada_nao_e_executada(self):
        games={1:jogo(1,"2025-01-01",0,2),2:jogo(2,"2025-01-02")}
        entries=[entrada(11,1,"80"),entrada(12,2,"30")]
        result,bank=gl._liquidar_entradas_por_data(entries,games,Decimal("100"))
        self.assertEqual(result,[ (11,"red",Decimal("-80.00")),
                                  (12,"sem_saldo",Decimal("0.00")) ])
        self.assertEqual(bank,Decimal("20.00"))

    def test_mesmo_dia_nao_usa_lucro_de_outra_partida(self):
        games={1:jogo(1,"2025-01-01"),2:jogo(2,"2025-01-01"),
               3:jogo(3,"2025-01-02")}
        entries=[entrada(10,1,"80"),entrada(11,2,"80"),
                 entrada(12,3,"80")]
        result,bank=gl._liquidar_entradas_por_data(entries,games,Decimal("100"))
        self.assertEqual([r[1] for r in result],["green","sem_saldo","green"])
        self.assertEqual(bank,Decimal("260.00"))
        self.assertEqual(result[1][2],Decimal("0.00"))

    def test_mesmo_dia_prioriza_registro_antigo_independente_da_ordem_recebida(self):
        games={1:jogo(1,"2025-01-01"),2:jogo(2,"2025-01-01",0,2)}
        entries=[entrada(12,2,"60"),entrada(10,1,"60")]
        result,bank=gl._liquidar_entradas_por_data(entries,games,Decimal("100"))
        self.assertEqual(result,[ (10,"green",Decimal("60.00")),
                                  (12,"sem_saldo",Decimal("0.00")) ])
        self.assertEqual(bank,Decimal("160.00"))

    def test_lay_responsabilidade_e_reservada_sem_antecipar_comissao(self):
        games={1:jogo(1,"2025-01-01",2,0),
               2:jogo(2,"2025-01-01",2,0)}
        entries=[entrada(1,1,"80","3.00","lay_zebra"),
                 entrada(2,2,"30")]
        result,bank=gl._liquidar_entradas_por_data(entries,games,Decimal("100"))
        self.assertEqual(result[0],(1,"green",Decimal("38.20")))
        self.assertEqual(result[1],(2,"sem_saldo",Decimal("0.00")))
        self.assertEqual(bank,Decimal("138.20"))

    def test_nao_revela_placar_e_nao_conta_sem_saldo_como_red(self):
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
