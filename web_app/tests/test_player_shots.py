"""Perfis de linha/goleiro: precisão, defesas, pênaltis e dados auditáveis."""
import unittest
from decimal import Decimal
from unittest.mock import patch
import queries_player_shots as shots


def lance(ident,kind="Pé direito",event="Gol",penalty=False,
          x=32.78,z=1.20,goalie=2):
    return {
        "id":ident, "jogo_id":101, "jogador_id":1,"goleiro_id":goalie,
        "mando":"Casa", "tipo_evento":event,
        "tipo_finalizacao":kind,
        "situacao_jogada":"Pênalti" if penalty else "Jogada normal",
        "foi_no_alvo":event in ("Gol","Defendida"),
        "foi_gol_contra":False,
        "foi_bloqueada":event=="Bloqueada",
        "coordenada_x":Decimal("95.00"),"coordenada_y":Decimal("32.78"),
        "local_x_gol":None if x is None else Decimal(str(x)),
        "altura_z_gol":None if z is None else Decimal(str(z)),
        "xg":Decimal("0.34"),"xgot":Decimal("0.60"),
        "minuto":61,"minuto_adicional":None,
        "data":"2026-11-04","temporada":"2026",
        "atacante":"Jogador A","campeonato":"Brasileiro",
    }


class TestPlayersShots(unittest.TestCase):
    def test_linha_tipo_conta_acerto_como_chute_no_alvo(self):
        records=[
            lance(1,event="Gol"),
            lance(2,event="Defendida"),
            lance(3,event="Para fora"),
            lance(4,kind="Cabeça",event="Bloqueada"),
            lance(5,kind="Pé esquerdo",event="Gol"),
        ]
        result=shots.summarize(records)
        self.assertEqual(result["tipo"],"linha")
        self.assertEqual(result["resumo"]["tentativas"],5)
        self.assertEqual(result["resumo"]["no_alvo"],3)
        self.assertEqual(result["resumo"]["gols"],2)
        self.assertEqual(result["resumo"]["acerto_pct"],60.0)
        right=next(x for x in result["tipos"] if x["chave"]=="direito")
        self.assertEqual((right["acertos"],right["tentativas"]),(2,3))
        self.assertEqual(right["acerto_pct"],66.7)

    def test_penalti_mostra_todos_os_lados_inclusive_zero(self):
        records=[
            lance(1,penalty=True,event="Gol",x=37.25,z=.15),
            lance(2,penalty=True,event="Defendida",x=37.25,z=1.0),
            lance(3,penalty=True,event="Para fora",x=31.0,z=2.7),
            lance(4,penalty=False,event="Gol",x=34.0,z=1.0),
        ]
        result=shots.summarize(records)
        p=result["penaltis"]
        self.assertEqual((p["tentativas"],p["gols"],p["acertos"]),(3,1,1))
        self.assertEqual(p["acerto_pct"],33.3)
        self.assertEqual([x["chave"] for x in p["lados"]],
                         ["esquerda","centro","direita"])
        self.assertEqual([x["tentativas"] for x in p["lados"]],[2,0,1])
        self.assertEqual([x["tentativas"] for x in p["alturas"]],[1,1,1])
        self.assertEqual(len(p["mapa"]),3)
        self.assertFalse(p["salto_goleiro_disponivel"])

    def test_goleiro_so_chutes_no_alvo_vao_ao_denominador_taxa_defesas(self):
        rows=[
            lance(1,event="Defendida"),
            lance(2,event="Gol"),
            lance(3,event="Para fora"),
            lance(4,event="Defendida",kind="Pé esquerdo"),
        ]
        result=shots.summarize(rows,goalkeeper=True)
        self.assertEqual(result["tipo"],"goleiro")
        self.assertEqual(result["resumo"]["tentativas"],4)
        self.assertEqual(result["resumo"]["no_alvo"],3)
        self.assertEqual(result["resumo"]["defesas"],2)
        self.assertEqual(result["resumo"]["gols"],1)
        self.assertEqual(result["resumo"]["acerto_pct"],66.7)
        right=next(x for x in result["tipos"] if x["chave"]=="direito")
        self.assertEqual((right["acertos"],right["no_alvo"]),(1,2))
        self.assertEqual(right["acerto_pct"],50.0)

    def test_goleiro_penaltis_nao_inventam_lado_de_salto(self):
        rows=[
            lance(1,event="Defendida",penalty=True,x=31,z=.3),
            lance(2,event="Gol",penalty=True,x=37,z=1.8),
            lance(3,event="Para fora",penalty=True,x=34,z=4),
        ]
        p=shots.summarize(rows,goalkeeper=True)["penaltis"]
        self.assertEqual((p["defesas"],p["gols"],p["tentativas"]),(1,1,3))
        self.assertEqual(p["acerto_pct"],33.3)
        self.assertFalse(p["salto_goleiro_disponivel"])
        self.assertEqual(len(p["lados"]),3)

    def test_sem_penaltis_nao_exibe_aba(self):
        self.assertIsNone(shots.summarize([lance(1)])["penaltis"])
        self.assertIsNone(shots.summarize([])["penaltis"])
        self.assertEqual(shots.summarize([])["resumo"]["acerto_pct"],0)

    def test_nulos_e_proprio_gol_nao_criam_coordenadas_ou_gols_falsos(self):
        row=lance(1,event="Gol",penalty=True,x=None,z=None)
        row["foi_gol_contra"]=True
        result=shots.summarize([row])
        self.assertEqual(result["resumo"]["gols"],0)
        self.assertEqual(result["penaltis"]["gols"],0)
        self.assertEqual(result["penaltis"]["sem_lado"],1)
        self.assertEqual(result["penaltis"]["sem_altura"],1)
        self.assertIsNone(result["mapa"][0]["local_x_gol"])

    def test_consulta_temporada_filtro_parametrizado(self):
        player={"id":11,"nome":"Exemplo","posicao":"Goleiro"}
        with patch.object(shots,"fetch_one",return_value=player),\
             patch.object(shots,"fetch_all",return_value=[lance(1,penalty=True)]) as q:
            answer=shots.consultar(11,"2026")
        self.assertEqual(answer["tipo"],"goleiro")
        self.assertEqual(answer["temporada"],"2026")
        sql,values=q.call_args.args
        self.assertIn("f.goleiro_id = %s",sql)
        self.assertIn("jo.temporada = %s",sql)
        self.assertEqual(values,(11,"2026"))
        self.assertEqual(answer["mapa_total"],1)

    def test_consulta_jogador_de_linha_nao_vaza_lances_de_outro_jogador(self):
        with patch.object(shots,"fetch_one",return_value={
            "id":11,"nome":"Exemplo","posicao":"Centroavante"
        }),patch.object(shots,"fetch_all",return_value=[]) as q:
            result=shots.consultar(11,"2026")
        self.assertEqual(result["tipo"],"linha")
        self.assertIn("f.jogador_id = %s",q.call_args.args[0])
        self.assertNotIn("f.goleiro_id = %s",q.call_args.args[0])

if __name__=="__main__":
    unittest.main()
