"""Nostradamus no Supabase: validação de CRUD, importação e versão."""
from datetime import date, timedelta
from unittest import TestCase
import queries_estrategias as st

def valid():
    return {
        "nome":"Mandante xG maior", "objetivo":"back_mandante",
        "corte":(date.today()-timedelta(days=1)).isoformat(),
        "jogos":"20","campeonato_id":None,
        "condicoes":[{"lado":"mandante","metrica":"xg",
                     "comparador":"gt","referencia":"adversario"}],
        "odd_hipotetica":None,"comissao_pct":2
    }

class TestEstratégias(TestCase):
    def test_validar_condicoes_e_salvar_sem_margem(self):
        result=st._validate(valid())
        self.assertEqual(result["nome"],"Mandante xG maior")
        self.assertEqual(result["jogos"],"20")
        self.assertEqual(result["condicoes"][0]["referencia"],"adversario")
        self.assertEqual(result["condicoes"][0]["valor"],0)

    def test_estrategias_antigas_preservadas(self):
        body=valid()
        body["condicoes"]=[{"metrica":"xg","comparador":"gt","margem":0.4}]
        self.assertEqual(st._validate(body)["condicoes"][0]["valor"],0.4)

    def test_condicao_com_valor_absoluto(self):
        body=valid()
        body["condicoes"]=[{"lado":"visitante","metrica":"gols_sofridos",
                             "comparador":"ge","referencia":"valor","valor":1.5}]
        self.assertEqual(st._validate(body)["condicoes"][0]["valor"],1.5)

    def test_recusa_nome_invalido_corte_futuro_e_metodo_invalido(self):
        for changes in (
            {"nome":""},{"nome":"x"*81},{"objetivo":"sem_mercado"},
            {"jogos":"50"},{"campeonato_id":-1},
            {"corte":(date.today()+timedelta(days=1)).isoformat()},
            {"comissao_pct":-1},{"comissao_pct":31},
            {"odd_hipotetica":1.0},{"odd_hipotetica":float("nan")},
            {"condicoes":[]}
        ):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                st._validate({**valid(),**changes})

    def test_esquema_guarda_condicoes_json_e_versao_otimista(self):
        self.assertTrue(any("versao=versao+1" in str(x) for x in st.editar.__code__.co_consts))
        self.assertTrue(any("ON CONFLICT DO NOTHING" in str(x) for x in st.importar.__code__.co_consts))
