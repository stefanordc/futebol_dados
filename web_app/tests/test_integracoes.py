"""Testes das integrações sem consultar API real e sem gravar dados reais."""
import io
import json
from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import patch,MagicMock
import queries_integracoes as qi
import queries_vinculos as qv

CLUBS=[{"id":1,"clube":"Flamengo","pais_id":1},
       {"id":2,"clube":"Atlético","pais_id":1},
       {"id":3,"clube":"Corinthians","pais_id":1}]
FIS=[{"externo_id":"123","nome":"Flamengo","registros":5,"pais":"Brasil"},
     {"externo_id":"321","nome":"Atletico MG","registros":6,"pais":"Brasil"},
     {"externo_id":"987","nome":"Outra equipe","registros":1,"pais":"Brasil"}]

class TestVinculos(TestCase):
    def test_normalizacao_e_sugestao(self):
        self.assertEqual(qv.key("Atlético-MG"),"atletico mg")
        self.assertEqual(qv._suggest("atletico",CLUBS)[0]["id"],2)

    def test_omite_mapeados_e_exatos_e_restringe_destino_sofascore(self):
        refs=[{"clube_id":1,"fonte":"fotmob","id_externo":"a"},
              {"clube_id":2,"fonte":"fotmob","id_externo":"b"},
              {"clube_id":3,"fonte":"sofascore","id_externo":"999"}]
        def query(sql):
            if "FROM public.clubes ORDER" in sql:return CLUBS
            if "FROM public.clubes_fontes" in sql:return refs
            return FIS
        with patch.object(qv,"fetch_all",side_effect=query):
            r=qv.listar("fisicos")
        self.assertEqual([x["externo_id"] for x in r["pendentes"]],["321","987"])
        self.assertEqual({x["id"] for x in r["clubes"]},{1,2})

    def test_confere_vinculos_antes_de_gravar(self):
        fake=MagicMock()
        cur=fake.cursor.return_value.__enter__.return_value
        cur.fetchone.return_value={"id":99}
        @contextmanager
        def conn():
            yield fake
        data={"fonte":"fisicos","vinculos":[{"externo_id":"321","clube_id":2}]}
        with patch.object(qv,"listar",return_value={"pendentes":[FIS[1]],"clubes":CLUBS}),patch.object(qv,"get_conn",conn):
            self.assertEqual(qv.vincular(data)["vinculados"],1)
        fake.commit.assert_called_once()

class Response:
    headers={"Content-Type":"application/json"}
    def __init__(self,data):self.payload=json.dumps(data).encode()
    def read(self,n):return self.payload[:n]
    def __enter__(self):return self
    def __exit__(self,*args):pass

class TestIntegracoes(TestCase):
    def test_parse_estrutura_e_temporada(self):
        self.assertEqual(len(qi._rows({"data":{"matches":[{"id":1}]}})),1)
        self.assertEqual(qi._metadata("/api/download/brazil/serie-a-betano/2026"),
                         ("2026","Serie A Betano","Brasil"))

    def test_clubes_em_json_aninhado(self):
        row={"teams":{"home":{"name":"Flamengo"},"away":{"name":"Atlético"}}}
        self.assertEqual(qi._pick(row,qi.HOME_KEYS),"Flamengo")
        self.assertEqual(qi._pick(row,qi.AWAY_KEYS),"Atlético")

    def test_bloqueia_hosts_desconhecidos_e_privados(self):
        with patch.dict(qi.os.environ,{"ODDS_API_ALLOWED_HOSTS":"api.exemplo.com"}):
            with self.assertRaises(ValueError):
                qi._url("https://outro.exemplo.com","/api/download")
            with patch.object(qi.socket,"getaddrinfo",return_value=[
                (2,1,6,"",("127.0.0.1",443))]):
                with self.assertRaises(ValueError):
                    qi._url("https://api.exemplo.com","/api/download")
            with self.assertRaises(ValueError):
                qi._url("http://api.exemplo.com","/api/download")

    def test_previa_retorna_colunas_e_sugestoes_sem_gravar_chave(self):
        payload={"matches":[{"id":"A","home_team":"Flamengo",
                 "away_team":"Atletico MG","odds":1.85,"token_private":"nao_importar"}]}
        response=Response(payload)
        opener=MagicMock();opener.open.return_value=response
        qi._PREVIEWS.clear()
        with patch.dict(qi.os.environ,{"ODDS_API_ALLOWED_HOSTS":"api.exemplo.com"}),\
             patch.object(qi.socket,"getaddrinfo",return_value=[(2,1,6,"",("8.8.8.8",443))]),\
             patch.object(qi,"build_opener",return_value=opener),\
             patch.object(qi,"fetch_all",return_value=CLUBS):
            result=qi.preview({"base":"https://api.exemplo.com",
                "caminho":"/api/download/brazil/serie-a-betano/2026",
                "chave":"CHAVE-SECRETA","cabecalho":"x-api-key"})
        self.assertEqual(result["temporada"],"2026")
        self.assertIn("odds",result["colunas"])
        self.assertNotIn("token_private",result["colunas"])
        self.assertEqual(len(result["clubes"]),2)
        self.assertNotIn("CHAVE-SECRETA",str(qi._PREVIEWS))
        self.assertEqual(len(qi._PREVIEWS),1)

    def test_importacao_atomica_commit_sem_chave(self):
        qi._PREVIEWS.clear()
        qi._PREVIEWS["abc"]={"criado":qi.time.monotonic(),"host":"api.exemplo.com",
         "path":"/api/download/brazil/serie-a-betano/2026",
         "season":"2026","league":"Serie A Betano","country":"Brasil",
         "columns":["home_team","away_team","odds"],"rows":[
         {"home_team":"Flamengo","away_team":"Atlético","odds":1.75}]}
        fake=MagicMock()
        cursor=fake.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect=[{"id":5},{"clube_id":1},{"clube_id":2}]
        @contextmanager
        def conn():yield fake
        with patch.object(qi,"get_conn",conn),patch.object(qi,"fetch_all",
            return_value=[{"id":1},{"id":2}]):
            out=qi.importar({"preview_id":"abc","colunas":["odds"],
                 "clubes":[{"original":"Flamengo","padronizado":"Flamengo","clube_id":1},
                           {"original":"Atlético","padronizado":"Atlético","clube_id":2}]})
        self.assertEqual(out["inseridos"],1)
        self.assertEqual(out["colunas"],["odds"])
        fake.commit.assert_called_once()
        self.assertNotIn("abc",qi._PREVIEWS)

    def test_importacao_nao_aceita_coluna_inventada(self):
        qi._PREVIEWS["abc"]={"criado":qi.time.monotonic(),"columns":["odds"]}
        with self.assertRaises(ValueError):
            qi.importar({"preview_id":"abc","colunas":["senha"],"clubes":[]})

if __name__=="__main__":
    import unittest
    unittest.main()
