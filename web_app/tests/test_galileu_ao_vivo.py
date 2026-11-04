"""Cenários ao vivo salvos no Nostradamus geram entradas automáticas no Galileu."""
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

import queries_galileu_gameplay as gl


def session():
    return {
        "id":"sid-live","indice_rodada":1,"fase":"aberta","versao":4,
        "banca_base_mes":Decimal("1000.00"),"banca_inicial":Decimal("1000.00"),
        "banca_atual":Decimal("800.00"),"gestao_pct":Decimal("2.0"),
        "stake_fixa":None,"mes_base":"2025-01",
        "corte":date(2024,12,31),"corte_atual":date(2024,12,31),
    }


def scenario():
    return {
        "id":17,"versao":3,"nome":"Lay empate aos 60",
        "configuracao":{
            "corte":"2024-12-31","minuto":60,"vencendo":"favorito",
            "diferenca_gols":2,"mercado":"lay_empate","jogos":"20",
            "campeonato_ids":[1],"condicoes":[],"odd_hipotetica":None,
        }
    }


def match(jid,goals60=(2,0),day="2025-01-15"):
    return {
        "id":jid,"data":date.fromisoformat(day),
        "gols_casa":2,"gols_fora":1,
        "gols_casa_minuto":goals60[0],"gols_fora_minuto":goals60[1],
        "temporada":"2024/2025","campeonato_id":1,
        "campeonato":"Brasileiro","casa_id":10,"fora_id":11,
        "mandante":"Time Casa","visitante":"Time Fora",
        "api_odd_1_ft":1.55,"api_odd_2_ft":4.50,
        "api_over_ft_2_5":1.9,"api_under_ft_2_5":2.0,
    }


class Cursor:
    def __init__(self,disabled=None,closed=None,inserted=None):
        self.sql=""
        self.disabled=disabled or []
        self.closed=closed or []
        self.inserted=inserted if inserted is not None else [{"id":11}]
        self.update_count=0
        self.insert_values=None
    def execute(self,sql,params):
        self.sql=sql
        if "UPDATE galileu_private.sessoes" in sql:
            self.update_count+=1
    def fetchall(self):
        if "SELECT metodo_id,efetivo_desde" in self.sql:
            return self.disabled
        if "SELECT jogo_id FROM galileu_private.jogos_finalizados" in self.sql:
            return self.closed
        if self.sql=="bulk-insert":
            return self.inserted
        return []


class FakeConn:
    def __init__(self,cursor):
        self.cur=cursor
        self.commits=0
    @contextmanager
    def cursor(self):
        yield self.cur
    def commit(self):
        self.commits+=1


class TestGalileuAoVivo(TestCase):
    def setUp(self):
        clock=patch.object(gl,"today",return_value=date(2026,11,2))
        clock.start()
        self.addCleanup(clock.stop)

    def test_metodo_ao_vivo_tem_id_estavel_e_nao_confunde_pregame(self):
        with patch.object(gl.queries_estrategias,"listar",return_value=[]), \
             patch.object(gl.live,"listar_cenarios",return_value=[scenario()]):
            methods=gl._methods()
        self.assertEqual(len(methods),1)
        m=methods[0]
        self.assertEqual(m["id"],gl.LIVE_METHOD_BASE+17)
        self.assertEqual(m["versao"],3)
        self.assertEqual(m["tipo"],"ao_vivo")
        self.assertEqual(m["nome"],"Ao vivo · Lay empate aos 60")
        self.assertEqual(m["configuracao"]["corte"],"2026-11-02")
        self.assertEqual(m["objetivo"],"lay_empate")

    def test_regras_no_minuto_correto_geram_oferta_com_odd_modelada(self):
        raw=[match(101),match(102,(1,0))]
        with patch.object(gl.queries_estrategias,"listar",return_value=[]), \
             patch.object(gl.live,"listar_cenarios",return_value=[scenario()]):
            methods=gl._methods()
        queries=[]
        def fetch(sql,params):
            queries.append((sql,params))
            return raw
        with patch.object(gl,"fetch_all",side_effect=fetch):
            offers=gl._live_offers(raw,methods,raw)
        self.assertEqual(list(offers),[101])
        self.assertEqual(len(offers[101]),1)
        offer=offers[101][0]
        self.assertEqual(offer["tipo"],"ao_vivo")
        self.assertEqual(offer["id"],gl.LIVE_METHOD_BASE+17)
        self.assertEqual(offer["objetivo"],"lay_empate")
        self.assertTrue(offer["mercado"]["estimada"])
        self.assertGreater(offer["mercado"]["odd"],1.01)
        self.assertIn("modelo_poisson",offer["mercado"]["origem"])
        self.assertEqual(offer["regras"],[])
        self.assertEqual(len(queries),1)
        sql,params=queries[0]
        self.assertIn("f.jogo_id=ANY(%s::integer[])",sql)
        self.assertEqual(params[0:2],(60,60))
        self.assertEqual(params[2],[101,102])
        self.assertEqual(params[3],date(2026,11,2))
        self.assertEqual(params[4:6],(None,None))
        # Os parâmetros do WHERE são posteriores aos parâmetros
        # dos dois COUNT FILTER da CTE, independentemente da ordem
        # textual em que aparecem as cláusulas SQL.
        first_minute=sql.index("AND (f.minuto+COALESCE(f.minuto_adicional,0))<=%s")
        second_minute=sql.index("AND (f.minuto+COALESCE(f.minuto_adicional,0))<=%s",first_minute+1)
        game_filter=sql.index("f.jogo_id=ANY(%s::integer[])")
        self.assertLess(first_minute,second_minute)
        self.assertLess(second_minute,game_filter)
        self.assertEqual(sql.count("%s"),len(params))

    def test_nao_registra_se_metodo_foi_retirado(self):
        m={
            "id":gl.LIVE_METHOD_BASE+17,"tipo":"ao_vivo",
            "nome":"Ao vivo · Lay empate","versao":1,"objetivo":"lay_empate",
            "configuracao":{"minuto":60},
        }
        with patch.object(gl,"fetch_all",side_effect=AssertionError("Não consultar gols")):
            offers=gl._live_offers([match(101)],[m],[match(101)],{
                m["id"]:{"desde":"2025-01"}
            })
        self.assertEqual(offers,{})

    def test_registra_automaticamente_uma_stake_de_2_porcento_da_base(self):
        mid=gl.LIVE_METHOD_BASE+17
        game=match(101)
        public=[{
            "jogo_id":101,
            "metodos":[{
                "id":mid,"versao":3,"tipo":"ao_vivo",
                "nome":"Ao vivo · Lay empate aos 60",
                "objetivo":"lay_empate",
                "mercado":{"odd":8.21,"favorito_casa":True}
            }]
        }]
        cur=Cursor()
        conn=FakeConn(cur)
        @contextmanager
        def get_conn():
            yield conn
        def execute_values(cursor,query,records,page_size=None):
            cursor.insert_values=records
            cursor.sql="bulk-insert"
            self.assertIn("ON CONFLICT DO NOTHING",query)
        with patch.object(gl,"get_conn",get_conn), \
             patch.object(gl,"_lock",return_value=session()), \
             patch("psycopg2.extras.execute_values",side_effect=execute_values):
            count=gl._sync_live_entries("token",session(),[game],public)
        self.assertEqual(count,1)
        self.assertEqual(cur.update_count,1)
        self.assertEqual(conn.commits,1)
        self.assertEqual(len(cur.insert_values),1)
        saved=cur.insert_values[0]
        self.assertEqual(saved[1],101)
        self.assertEqual(saved[4],mid)
        self.assertEqual(saved[7],"lay_empate")
        self.assertEqual(saved[8],8.21)
        self.assertEqual(saved[9],Decimal("20.00"))
        self.assertTrue(saved[10])
        self.assertTrue(saved[11])

    def test_entrada_automatica_nao_duplica_nem_altera_versao(self):
        mid=gl.LIVE_METHOD_BASE+17
        cur=Cursor(inserted=[])
        conn=FakeConn(cur)
        @contextmanager
        def get_conn():
            yield conn
        def execute_values(cursor,query,records,page_size=None):
            cursor.insert_values=records
            cursor.sql="bulk-insert"
            self.assertIn("ON CONFLICT DO NOTHING",query)
        public=[{"jogo_id":101,"metodos":[{
            "id":mid,"versao":1,"tipo":"ao_vivo","nome":"Live",
            "objetivo":"lay_empate",
            "mercado":{"odd":2.0,"favorito_casa":True}
        }]}]
        with patch.object(gl,"get_conn",get_conn), \
             patch.object(gl,"_lock",return_value=session()), \
             patch("psycopg2.extras.execute_values",side_effect=execute_values):
            count=gl._sync_live_entries("token",session(),[match(101)],public)
        self.assertEqual(count,0)
        self.assertEqual(cur.update_count,0)
        self.assertEqual(conn.commits,1)

    def test_nunca_insere_em_jogo_finalizado_ou_sessao_fechada(self):
        mid=gl.LIVE_METHOD_BASE+17
        public=[{"jogo_id":101,"metodos":[{
            "id":mid,"versao":1,"tipo":"ao_vivo","nome":"Live",
            "objetivo":"lay_empate",
            "mercado":{"odd":2.0,"favorito_casa":True}
        }]}]
        cur=Cursor(closed=[{"jogo_id":101}])
        conn=FakeConn(cur)
        @contextmanager
        def get_conn():
            yield conn
        with patch.object(gl,"get_conn",get_conn), \
             patch.object(gl,"_lock",return_value=session()), \
             patch("psycopg2.extras.execute_values",side_effect=AssertionError("Não inserir")):
            self.assertEqual(gl._sync_live_entries("token",session(),[match(101)],public),0)
        self.assertEqual(cur.update_count,0)
        closed=session()
        closed["fase"]="revelada"
        self.assertEqual(gl._sync_live_entries("token",closed,[match(101)],public),0)

    def test_estado_e_finalizar_acionam_a_sincronizacao(self):
        from pathlib import Path
        source=(Path(__file__).resolve().parents[1]/
                "queries_galileu_gameplay.py").read_text(encoding="utf8")
        self.assertIn("auto_count=_sync_live_entries(token,sess,raw_games,games)",source)
        self.assertIn("_sync_live_entries(token,sess,raw,public)",source)
        self.assertIn('"entradas_automaticas_ao_vivo":auto_count',source)
