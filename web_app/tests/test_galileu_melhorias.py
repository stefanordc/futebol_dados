"""Varinha de otimização de métodos com 2+ meses consecutivos negativos."""
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import queries_galileu_melhorias as opt
import queries_galileu_gameplay as gl


RULE={
    "tipo":"indicador",
    "lado":"favorito",
    "mando_preferido":"indiferente",
    "metrica":"xg",
    "comparador":"ge",
    "referencia":"valor",
    "valor":1.5,
}
RULE_TWO={
    "tipo":"indicador",
    "lado":"zebra",
    "mando_preferido":"indiferente",
    "metrica":"escanteios",
    "comparador":"ge",
    "referencia":"valor",
    "valor":3,
}
METHODS=[
    {"id":21,"nome":"Lay zebra"},
    {"id":22,"nome":"Over 2,5"},
    {"id":gl.LIVE_METHOD_BASE+35,"nome":"Ao vivo · Lay empate"},
]


def entry(month,amount,method=21,status="red",category="metodo"):
    return {
        "metodo_id":method,"metodo_nome":"Método",
        "data":month+"-10",
        "tipo":category,"status":status,
        "lucro_prejuizo":Decimal(str(amount)),
    }


class NegativeStreakTests(unittest.TestCase):
    def test_dois_meses_consecutivos_disparam_varinha(self):
        bets=[entry("2026-05",-15),entry("2026-06",-20)]
        result=opt.sequencias_prejuizo(bets,"2026-06",METHODS)
        self.assertEqual(result[21]["meses_prejuizo_consecutivos"],2)
        self.assertEqual(result[21]["prejuizo_acumulado"],-35)
        self.assertEqual([r["mes"] for r in result[21]["meses_prejuizo"]],
                         ["2026-06","2026-05"])

    def test_quatro_meses_negativos_continuam_elegiveis(self):
        bets=[entry(f"2026-{m:02d}",-10) for m in (3,4,5,6)]
        result=opt.sequencias_prejuizo(bets,"2026-06",METHODS)
        self.assertEqual(result[21]["meses_prejuizo_consecutivos"],4)

    def test_lucro_zero_sem_entrada_e_meses_isolados_interrompem(self):
        for intermission in ([entry("2026-05",5)], [entry("2026-05",0)],
                             [],[entry("2026-05",-3,status="pendente")]):
            with self.subTest(intermission=intermission):
                bets=[entry("2026-04",-30),*intermission,entry("2026-06",-20)]
                self.assertNotIn(21,opt.sequencias_prejuizo(bets,"2026-06",METHODS))

    def test_so_vale_o_resultado_liquido_das_entradas_executadas(self):
        bets=[
            entry("2026-05",-30),entry("2026-05",10,status="green"),
            entry("2026-06",-20),entry("2026-06",60,status="pendente"),
            entry("2026-06",150,status="sem_saldo"),
        ]
        result=opt.sequencias_prejuizo(bets,"2026-06",METHODS)
        self.assertEqual(result[21]["prejuizo_acumulado"],-40)

    def test_outros_metodos_e_manuaise_futuro_nao_contaminam(self):
        bets=[
            entry("2026-05",-50),entry("2026-06",-20),
            entry("2026-06",200,method=22),
            entry("2026-06",200,method=21,category="manual"),
            entry("2026-07",1000),
            entry("2026-05",-10,method=999),
            entry("2026-06",-10,method=999),
            entry("2026-05",-5,method=gl.LIVE_METHOD_BASE+35),
            entry("2026-06",-8,method=gl.LIVE_METHOD_BASE+35)
        ]
        result=opt.sequencias_prejuizo(bets,"2026-06",METHODS)
        self.assertEqual(result[21]["prejuizo_acumulado"],-70)
        self.assertNotIn(22,result)
        self.assertNotIn(999,result)
        self.assertEqual(result[gl.LIVE_METHOD_BASE+35]["meses_prejuizo_consecutivos"],2)


class SuggestionsTests(unittest.TestCase):
    def test_eligibilidade_nao_confia_em_ids_da_interface(self):
        with patch.object(gl,"estado",return_value={
            "iniciado":True,"mes_encerrado":"2026-06",
            "metodos_fechamento":[{"metodo_id":21,"melhoria_elegivel":False}]
        }),patch.object(opt,"_source",side_effect=AssertionError("não ler source")):
            with self.assertRaisesRegex(ValueError,"dois meses"):
                opt.sugerir("token",21)

    def test_analise_usa_versao_atual_e_corte_do_fechamento(self):
        state={
            "iniciado":True,"mes_encerrado":"2026-06",
            "metodos_fechamento":[{
                "metodo_id":21,"melhoria_elegivel":True,
                "nome":"Lay zebra","meses_prejuizo_consecutivos":2,
                "prejuizo_acumulado":-40,
                "meses_prejuizo":[{"mes":"2026-06","lucro_prejuizo":-20},
                                  {"mes":"2026-05","lucro_prejuizo":-20}]
            }]
        }
        original={
            "id":21,"versao":4,"nome":"Lay zebra",
            "objetivo":"lay_zebra","corte":date(2024,12,31),
            "jogos":"20","campeonato_ids":[1],"condicoes":[RULE],
            "odd_hipotetica":None,"comissao_pct":4.5,
        }
        outcome={
            "metodo":"Treino e validação separados",
            "mensagem":"Proposta encontrada",
            "sugestoes":[{
                "acao":"adicionar","indice":None,"condicao":RULE_TWO,
                "descricao":"Zebra · escanteios ≥ 3",
                "treino":{"entradas":12,"total_reais":25},
                "validacao":{"entradas":5,"total_reais":10},
                "avaliacao":"Sinal positivo na validação"
            }],
        }
        with patch.object(gl,"estado",return_value=state), \
             patch.object(opt,"_source",return_value=("pre_jogo",original)), \
             patch.object(opt.ai,"analisar",return_value=outcome) as call:
            analyzed=opt.sugerir("token",21)
        self.assertEqual(analyzed["versao_original"],4)
        self.assertEqual(analyzed["mes_referencia"],"2026-06")
        self.assertEqual(analyzed["sugestoes"][0]["nome_sugerido"],
                         "Lay zebra (IA 2026-06 · 1)")
        self.assertEqual(call.call_args.args[0]["corte"],"2026-06-30")
        self.assertEqual(call.call_args.args[0]["condicoes"],[RULE])

    def test_nunca_salva_sem_sugestao_aprovada_pelo_servidor(self):
        analyzed={
            "mes_referencia":"2026-06","versao_original":4,"sugestoes":[]
        }
        with patch.object(opt,"_analysis",return_value=(analyzed,{},{})), \
             patch.object(opt.queries_estrategias,"criar",
                          side_effect=AssertionError("não inserir")):
            with self.assertRaisesRegex(ValueError,"Sugestão indisponível"):
                opt.salvar("token",21,{"indice":0,"mes_referencia":"2026-06",
                                      "versao_original":4})
            with self.assertRaisesRegex(ValueError,"atualizado"):
                opt.salvar("token",21,{"indice":0,"mes_referencia":"2026-05",
                                      "versao_original":4})

    def test_nova_estrategia_pregame_nao_altera_original(self):
        analyzed={
            "mes_referencia":"2026-06","versao_original":4,"tipo":"pre_jogo",
            "sugestoes":[{"acao":"adicionar","condicao":RULE_TWO,
                          "nome_sugerido":"Lay zebra (IA 2026-06 · 1)"}]
        }
        payload={
            "objetivo":"lay_zebra","corte":"2026-06-30","jogos":"20",
            "condicoes":[RULE],"campeonato_ids":[1],
            "odd_hipotetica":None,"comissao_pct":4.5
        }
        original={"nome":"Lay zebra","id":21,"versao":4}
        with patch.object(opt,"_analysis",return_value=(analyzed,payload,original)), \
             patch.object(opt.queries_estrategias,"criar",return_value={
                 "id":67,"nome":"Lay zebra (IA 2026-06 · 1)"
             }) as created:
            result=opt.salvar("token",21,{
                "indice":0,"mes_referencia":"2026-06","versao_original":4
            })
        self.assertTrue(result["criado"])
        self.assertEqual(result["metodo_id"],67)
        self.assertEqual(result["origem_id"],21)
        saved=created.call_args.args[0]
        self.assertEqual(saved["nome"],"Lay zebra (IA 2026-06 · 1)")
        self.assertEqual(len(saved["condicoes"]),2)
        self.assertEqual(payload["condicoes"],[RULE])
        self.assertEqual(original["nome"],"Lay zebra")

    def test_novo_cenario_aovivo_mantem_filtros_do_minuto_e_novo_id(self):
        analyzed={
            "mes_referencia":"2026-06","versao_original":2,"tipo":"ao_vivo",
            "sugestoes":[{"acao":"adicionar","condicao":RULE,
                          "nome_sugerido":"Ao vivo (IA 2026-06 · 1)"}]
        }
        cfg={
            "minuto":60,"vencendo":"favorito","diferenca_gols":2,
            "mercado":"lay_empate","corte":"2026-06-30","jogos":"20",
            "campeonato_ids":[1,2],"odd_hipotetica":None,"condicoes":[],
        }
        with patch.object(opt,"_analysis",return_value=(
                analyzed,cfg,{"nome":"Ao vivo","versao":2})), \
             patch.object(opt.live,"criar_cenario",return_value={
                 "id":35,"nome":"Ao vivo melhorado"
             }) as created:
            result=opt.salvar("token",gl.LIVE_METHOD_BASE+20,{
                "indice":0,"mes_referencia":"2026-06",
                "versao_original":2,"nome":"Ao vivo melhorado"
            })
        self.assertEqual(result["metodo_id"],gl.LIVE_METHOD_BASE+35)
        saved=created.call_args.args[0]
        self.assertEqual(saved["minuto"],60)
        self.assertEqual(saved["diferenca_gols"],2)
        self.assertEqual(saved["mercado"],"lay_empate")
        self.assertEqual(len(saved["condicoes"]),1)

    def test_regras_inexistentes_ou_remocao_invalida_nao_geram_clones(self):
        with self.assertRaisesRegex(ValueError,"Regra de remoção"):
            opt._apply_rule({"condicoes":[RULE]},
                            {"acao":"remover","indice":3},"pre_jogo")
        with self.assertRaisesRegex(ValueError,"Limite de 10"):
            opt._apply_rule({"condicoes":[RULE]*10},
                            {"acao":"adicionar","condicao":RULE_TWO},"pre_jogo")


if __name__=="__main__":
    unittest.main()
