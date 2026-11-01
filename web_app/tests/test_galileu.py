"""Testes do Galileu: nunca consumir placar futuro, revalidar e preservar banca."""
from datetime import date,timedelta,datetime
from unittest import TestCase
from unittest.mock import patch
import queries_galileu as gl
from test_nostradamus import game

def setup():
    today=date(2026,11,1)
    past=[game(i,today-timedelta(days=11-i),gf=2,ga=0,comp=1,
               season="2026/2027") for i in range(8)]
    for item in past:
        item["campeonato"]="LaLiga"
    future=[
       {"id":901,"data":today+timedelta(days=1),"campeonato_id":1,
        "campeonato":"LaLiga","temporada":"2026/2027","rodada":"Rodada 10",
        "casa_id":1,"fora_id":2,"mandante":"Casa","visitante":"Fora"},
       {"id":902,"data":today+timedelta(days=3),"campeonato_id":1,
        "campeonato":"LaLiga","temporada":"2026/2027","rodada":"Rodada 10",
        "casa_id":1,"fora_id":2,"mandante":"Casa","visitante":"Fora"},
       {"id":903,"data":today+timedelta(days=8),"campeonato_id":1,
        "campeonato":"LaLiga","temporada":"2026/2027","rodada":"Rodada 11",
        "casa_id":1,"fora_id":2,"mandante":"Casa","visitante":"Fora"}
    ]
    method={"nome":"Mais xG em casa","objetivo":"back_mandante",
            "campeonato_id":1,
            "condicoes":[{"lado":"mandante","metrica":"xg",
                         "comparador":"gt","referencia":"adversario"}]}
    return today,past,future,method

class TestGalileu(TestCase):
    def setUp(self):
        self.today,self.past,self.future,self.method=setup()
        self.patch_today=patch.object(gl,"_today",return_value=self.today)
        self.patch_today.start()
        self.addCleanup(self.patch_today.stop)

    def signals(self,methods=None,fixtures=None,history=None,reg=None):
        return gl.sinais({"data":(self.today+timedelta(days=1)).isoformat(),
                          "estrategias":methods if methods is not None else [self.method]},
                         fixtures if fixtures is not None else self.future,
                         history if history is not None else self.past,
                         registered_ids=set() if reg is None else reg)

    def test_somente_proxima_rodada_e_sem_placares(self):
        r=self.signals()
        self.assertEqual([x["jogo_id"] for x in r["jogos"]],[901,902])
        self.assertNotIn("placar",r["jogos"][0])
        self.assertNotIn("gols_casa",r["jogos"][0])
        self.assertEqual(r["jogos"][0]["amostra"],{"mandante":8,"visitante":8})
        self.assertEqual(r["jogos"][0]["metodos"][0]["objetivo"],"back_mandante")

    def test_apenas_metodos_salvos_compatíveis(self):
        other={**self.method,"campeonato_id":2}
        self.assertEqual(self.signals(methods=[other])["total"],0)
        self.assertEqual(self.signals(methods=[])["total"],0)
        condition={"lado":"visitante","metrica":"gols_sofridos",
                   "comparador":"ge","referencia":"valor","valor":1.5}
        second={**self.method,"nome":"Visitante sofre gols","condicoes":[condition]}
        out=self.signals(methods=[self.method,second])
        self.assertEqual(len(out["jogos"][0]["metodos"]),2)

    def test_sem_dados_minimos_ou_jogo_ja_registrado(self):
        self.assertEqual(self.signals(history=self.past[:4])["total"],0)
        r=self.signals(reg={901})
        self.assertEqual([x["jogo_id"] for x in r["jogos"]],[902])

    def test_sem_historico_futuro_ou_do_mesmo_dia(self):
        leaks=[game(90,self.today+timedelta(days=1),gf=0,ga=8,
                    comp=1,season="2026/2027")]
        leaks[0]["campeonato"]="LaLiga"
        leaks[0]["home_xg"]=0
        leaks[0]["away_xg"]=99
        r=self.signals(history=self.past+leaks)
        self.assertEqual(r["total"],2)
        self.assertEqual(r["jogos"][0]["estatisticas"]["mandante"]["xg"],1.5)

    def test_data_presente_ou_passada_rejeitada(self):
        for d in (self.today,self.today-timedelta(days=1)):
            with self.subTest(day=d),self.assertRaises(ValueError):
                gl.sinais({"data":d.isoformat(),"estrategias":[self.method]},
                          self.future,self.past,set())

    def test_registro_e_apuracao_da_banca(self):
        rows=[
            {"id":1,"jogo_id":1,"data":self.today-timedelta(days=2),
             "campeonato":"LaLiga","mandante":"Casa","visitante":"Fora",
             "metodo_nome":"Estratégia A","objetivo":"back_mandante",
             "gols_casa":2,"gols_fora":0,"confirmado_em":datetime.now()},
            {"id":2,"jogo_id":2,"data":self.today-timedelta(days=1),
             "campeonato":"LaLiga","mandante":"Casa","visitante":"Outro",
             "metodo_nome":"Estratégia A","objetivo":"back_mandante",
             "gols_casa":0,"gols_fora":1,"confirmado_em":datetime.now()},
            {"id":3,"jogo_id":3,"data":self.today+timedelta(days=1),
             "campeonato":"LaLiga","mandante":"Casa","visitante":"Terceiro",
             "metodo_nome":"Estratégia B","objetivo":"over_25",
             "gols_casa":None,"gols_fora":None,"confirmado_em":datetime.now()}
        ]
        result=gl.relatorio(rows)
        self.assertEqual(result["banca_inicial"],100)
        self.assertEqual(result["banca_atual"],100)
        self.assertEqual(result["resumo"]["entradas"],3)
        self.assertEqual(result["resumo"]["greens"],1)
        self.assertEqual(result["resumo"]["reds"],1)
        self.assertEqual(result["resumo"]["pendentes"],1)
        self.assertEqual(result["resumo"]["win_rate"],50)
        self.assertEqual(len(result["por_clube"]),4)
        self.assertEqual(result["por_liga"][0]["entradas"],3)

    def test_validacao_das_entradas(self):
        payload={"data":(self.today+timedelta(days=1)).isoformat(),
                 "estrategias":[self.method],
                 "apostas":[{"jogo_id":901,"metodo_idx":0,"objetivo":"back_mandante"}]}
        for selection in ([],[{"jogo_id":901,"metodo_idx":0,"objetivo":"back_mandante"}]*2,
                          [{"jogo_id":901,"metodo_idx":0,"objetivo":"mercado_falso"}]):
            with self.subTest(selection=selection),self.assertRaises(ValueError):
                gl.confirmar({**payload,"apostas":selection})

    def test_impossivel_confirmar_se_metodo_nao_corresponde(self):
        payload={"data":(self.today+timedelta(days=1)).isoformat(),
                 "estrategias":[self.method],
                 "apostas":[{"jogo_id":901,"metodo_idx":9,"objetivo":"back_mandante"}]}
        with patch.object(gl,"sinais",return_value=self.signals()):
            with self.assertRaises(ValueError):
                gl.confirmar(payload)

if __name__=="__main__":
    import unittest
    unittest.main()
