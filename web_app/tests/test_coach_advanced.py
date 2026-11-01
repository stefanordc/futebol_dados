"""Testes dos agregados do técnico sem acessar o banco real."""
import unittest
from unittest.mock import patch

import queries_tecnico_avancadas as query


class TestTecnicoAvancadas(unittest.TestCase):
    def test_sem_temporada_nao_consulta(self):
        with patch.object(query, "fetch_all") as fetch:
            result=query.estatisticas_tecnico(13,"")
            fetch.assert_not_called()
        self.assertEqual(result["linhas"],[])

    def test_consulta_exclusiva_do_tecnico_e_temporada(self):
        response=[
            [{"campeonato_id":20,"clube_id":5,"campeonato":"Liga A","clube":"Clube A",
              "jogos":10,"gols_marcados":14,"gols_sofridos":8,
              "clean_sheets":4,"clean_goals":2,
              "vitorias":6,"empates":2,"derrotas":2,
              "partidas_com_estatisticas":9,
              "finalizacoes_feitas":120,"finalizacoes_certas":43,
              "finalizacoes_sofridas":80,"finalizacoes_certas_sofridas":30,
              "duelos_aereos":80,"duelos_aereos_ganhos":52,
              "duelos_aereos_adversario":79,"duelos_aereos_adversario_ganhos":27,
              "xg":15.2,"xg_sofrido":11.4,"xg_bola_parada":2.1}],
            [{"campeonato_id":20,"clube_id":5,
              "pe_direito":6,"pe_esquerdo":3,"cabeca":2,"bola_parada":3,
              "escanteio":1,"falta":1,"penalti":1,"individual":1,
              "gols_contra_a_favor":1,"gols_registrados":13,
              "gols_com_tipo_finalizacao":12,"gols_com_situacao":11}],
        ]
        with patch.object(query,"fetch_all",side_effect=response) as fetch:
            result=query.estatisticas_tecnico(42,"2026/2027")
        self.assertEqual(fetch.call_count,2)
        for args in fetch.call_args_list:
            sql,values=args.args
            self.assertEqual(values,("2026/2027",42,"2026/2027",42))
            self.assertIn("tecnico_casa_id",sql)
            self.assertIn("tecnico_fora_id",sql)
            self.assertIn("j.gols_casa IS NOT NULL",sql)
        item=result["linhas"][0]
        self.assertEqual(item["clean_sheets"],4)
        self.assertEqual(item["clean_goals"],2)
        self.assertEqual(item["finalizacoes_sofridas"],80)
        self.assertEqual(item["eficiencia_aerea"],65.0)
        self.assertEqual(item["precisao_finalizacoes"],35.8)
        self.assertEqual(item["gols_tipos"]["cabeca"],2)
        self.assertEqual(item["gols_tipos"]["gols_registrados"],13)

    def test_indisponibilidade_nao_vira_zero(self):
        self.assertIsNone(query._ratio(None,10))
        self.assertIsNone(query._ratio(4,0))
        self.assertIsNone(query._sum([{"x":None}],"x"))


if __name__ == "__main__":
    unittest.main()
