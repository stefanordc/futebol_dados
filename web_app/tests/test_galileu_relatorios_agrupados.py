"""Relatórios da gameplay: agrupamentos visíveis, ROI e execução sem saldo."""
from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

import queries_galileu_gameplay as gl


def aposta(identificador,month,kind,method,mid,league,home,away,status,stake,pnl):
    return {
        "id":identificador,"data":date.fromisoformat(month),
        "tipo":kind,"metodo_nome":method,"metodo_id":mid,
        "campeonato":league,"mandante":home,"visitante":away,
        "status":status,"stake":Decimal(str(stake)),
        "lucro_prejuizo":Decimal(str(pnl)) if pnl is not None else None,
    }


class TestRelatorioAgrupado(TestCase):
    def setUp(self):
        self.bets=[
            aposta(1,"2026-01-10","metodo","Over 2,5",7,"Premier League",
                   "Arsenal","Chelsea","green","20","30"),
            aposta(2,"2026-01-11","metodo","Over 2,5",7,"LaLiga",
                   "Real Madrid","Barcelona","red","20","-20"),
            aposta(3,"2026-02-12","metodo","Over 2,5",7,"Premier League",
                   "Arsenal","Chelsea","sem_saldo","20","0"),
            aposta(4,"2026-02-13","manual",None,None,"LaLiga",
                   "Real Madrid","Barcelona","pendente","20",None),
            aposta(5,"2026-02-14","metodo","Lay favorito",8,"LaLiga",
                   "Barcelona","Valencia","green","10","4"),
        ]

    def test_consolidacao_por_metodo_nao_conta_sem_saldo_como_red(self):
        result=gl._financial_group_results(self.bets)
        byname={r["nome"]:r for r in result["por_metodo"]}
        self.assertEqual(set(byname),{"Over 2,5","Lay favorito","Entrada manual"})
        over=byname["Over 2,5"]
        self.assertEqual(over["entradas"],3)
        self.assertEqual(over["executadas"],2)
        self.assertEqual(over["nao_executadas"],1)
        self.assertEqual(over["greens"],1)
        self.assertEqual(over["reds"],1)
        self.assertEqual(over["lucro_prejuizo"],10.0)
        self.assertEqual(over["stake_executada"],40.0)
        self.assertEqual(over["roi"],25.0)
        self.assertEqual(over["win_rate"],50.0)
        self.assertEqual(byname["Entrada manual"]["pendentes"],1)
        self.assertEqual(byname["Entrada manual"]["executadas"],0)

    def test_consolidacao_liga_e_clube_nao_soma_duas_vezes_o_mesmo_clube(self):
        result=gl._financial_group_results(self.bets)
        leagues={r["nome"]:r for r in result["por_liga"]}
        self.assertEqual(leagues["Premier League"]["entradas"],2)
        self.assertEqual(leagues["Premier League"]["nao_executadas"],1)
        self.assertEqual(leagues["LaLiga"]["entradas"],3)
        self.assertEqual(leagues["LaLiga"]["lucro_prejuizo"],-16.0)
        clubs={r["nome"]:r for r in result["por_clube"]}
        self.assertEqual(clubs["Arsenal"]["entradas"],2)
        self.assertEqual(clubs["Chelsea"]["entradas"],2)
        self.assertEqual(clubs["Barcelona"]["entradas"],3)
        self.assertEqual(clubs["Barcelona"]["lucro_prejuizo"],-16.0)

    def test_relatorio_privado_entrega_agrupamentos_consolidados_e_por_mes(self):
        session={"id":"sessao","banca_inicial":Decimal("1000.00"),
                 "banca_base_mes":Decimal("1000.00"),
                 "banca_atual":Decimal("1014.00"),
                 "mes_base":"2026-02",
                 "gestao_pct":Decimal("2.00"),
                 "stake_fixa":None}
        with patch.object(gl,"_token_session",return_value=session), \\
             patch.object(gl,"_fechamentos",return_value=[]), \\
             patch.object(gl,"_bet_rows",return_value=self.bets), \\
             patch.object(gl,"_movimentacoes",return_value=[]):
            report=gl.relatorios("cookie_de_teste")
        self.assertTrue(report["iniciado"])
        self.assertEqual(report["lucro_prejuizo_total"],14.0)
        self.assertEqual(len(report["agrupamentos"]["por_metodo"]),3)
        self.assertEqual(len(report["agrupamentos"]["por_liga"]),2)
        self.assertEqual(len(report["agrupamentos"]["por_clube"]),6)
        months={m["mes"]:m for m in report["resumo_mensal"]}
        self.assertEqual(months["2026-01"]["entradas"],2)
        self.assertEqual(months["2026-02"]["nao_executadas"],1)
        self.assertTrue(months["2026-02"]["por_estrategia"])
        self.assertTrue(months["2026-02"]["por_liga"])
        self.assertTrue(months["2026-02"]["por_clube"])

    def test_agrupamentos_sem_entradas_exibem_listas_vazias(self):
        result=gl._financial_group_results([])
        self.assertEqual(result,{"por_metodo":[],"por_liga":[],"por_clube":[]})
