"""Testes da aba Comportamento: abertura do placar pelo adversário."""
import unittest
from unittest.mock import patch

from queries_clube import comportamento_clube


def fixture():
    # Clube 1 mandante em cinco partidas e visitante em uma.
    games = [
        {"id": 10, "casa_id": 1, "fora_id": 2, "gols_casa": 0, "gols_fora": 1}, # rival abriu e venceu
        {"id": 11, "casa_id": 1, "fora_id": 2, "gols_casa": 0, "gols_fora": 2}, # rival abriu e ampliou
        {"id": 12, "casa_id": 1, "fora_id": 2, "gols_casa": 1, "gols_fora": 1}, # rival sofreu empate
        {"id": 13, "casa_id": 1, "fora_id": 2, "gols_casa": 2, "gols_fora": 1}, # rival perdeu de virada
        {"id": 14, "casa_id": 1, "fora_id": 2, "gols_casa": 1, "gols_fora": 0}, # clube abriu e venceu
        {"id": 15, "casa_id": 2, "fora_id": 1, "gols_casa": 0, "gols_fora": 0}, # sem gol
    ]
    events=[]
    def goal(jogo,minute,club):
        events.append({"jogo_id":jogo,"minuto":minute,"minuto_adicional":0,
                       "mando":None,"foi_gol_contra":False,"clube_id":club})
    goal(10,10,2)
    goal(11,10,2);goal(11,25,2)
    goal(12,10,2);goal(12,36,1)
    goal(13,10,2);goal(13,35,1);goal(13,70,1)
    goal(14,10,1)
    return games,events


class TestComportamentoAdversario(unittest.TestCase):
    @patch("queries_clube.fetch_all")
    def test_cinco_cartoes_e_mesmo_denominador(self, fetch):
        fetch.side_effect=list(fixture())
        result=comportamento_clube(1, "2026/2027")
        self.assertEqual(result["jogos"],6)
        cards={c["chave"]:c for c in result["adversario_cards"]}
        expected={
            "adversario_abriu":(4,66.7),
            "adversario_ampliou":(1,16.7),
            "adversario_venceu":(2,33.3),
            "adversario_empatou":(1,16.7),
            "adversario_perdeu":(1,16.7),
        }
        self.assertEqual(len(cards),5)
        for key,(games,pct) in expected.items():
            self.assertEqual(cards[key]["n"],games,key)
            self.assertEqual(cards[key]["pct"],pct,key)
        original={c["chave"]:c["n"] for c in result["cards"]}
        self.assertEqual(original["abriu"],1)
        self.assertEqual(original["abriu_venceu"],1)

    @patch("queries_clube.fetch_all")
    def test_filtros_por_campeonato_e_mando(self, fetch):
        games,events=fixture()
        fetch.side_effect=[games,events]
        result=comportamento_clube(1,"2026/2027",campeonato_id=7,mando="fora")
        self.assertEqual(result["jogos"],1)
        self.assertEqual([c["n"] for c in result["adversario_cards"]],[0]*5)
        self.assertEqual(fetch.call_count,2)
        for call in fetch.call_args_list:
            query,params=call.args
            self.assertIn("j.campeonato_id = %s",query)
            self.assertEqual(params,["2026/2027",1,1,7])

    @patch("queries_clube.fetch_all")
    def test_sem_jogos(self,fetch):
        fetch.side_effect=[[],[]]
        result=comportamento_clube(1,"2026/2027")
        self.assertEqual(result["jogos"],0)
        self.assertTrue(all(x["pct"]==0 and x["n"]==0 for x in result["adversario_cards"]))


if __name__=="__main__":
    unittest.main()
