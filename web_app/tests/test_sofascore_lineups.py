"""Escalações: identificação confiável de jogo e fallback sem inventar ID."""
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

import queries_sofascore_lineups as sofa


def fixture():
    return {
        "id": 202, "data": date(2026, 10, 31), "id_sofascore": None,
        "casa_id": 4, "fora_id": 17,
        "casa": "Rayo Vallecano", "fora": "Celta Vigo",
        "sofa_casa_id": "2818", "sofa_fora_id": "2821",
        "campeonato": "LaLiga", "campeonato_sofascore": None,
    }


def event(identifier, home_id=2818, away_id=2821, day=date(2026, 10, 31)):
    start=int(datetime(day.year,day.month,day.day,15,tzinfo=timezone.utc).timestamp())
    return {
        "id": identifier,
        "homeTeam": {"id":home_id,"name":"Rayo Vallecano"},
        "awayTeam": {"id":away_id,"name":"Celta Vigo"},
        "startTimestamp":start,
    }


class LineupResolutionTests(unittest.TestCase):
    def setUp(self):
        sofa._DAILY_CACHE.clear()


    def test_direto_sem_consultar_dados_fisicos(self):
        match=fixture()
        match["id_sofascore"]=16421100
        with patch.object(sofa,"_get_match",return_value=match), \
             patch.object(sofa,"_physical_match") as physical, \
             patch.object(sofa,"_same_match_id") as duplicate:
            result=sofa.resolve_match_id(202)
        self.assertEqual(result["id"],16421100)
        self.assertEqual(result["fonte"],"vinculo")
        physical.assert_not_called()
        duplicate.assert_not_called()

    def test_league_laliga_identifica_espanhol_id_oito(self):
        match=fixture()
        row={"id_campeonato":8,"campeonato":"Espanhol"}
        self.assertTrue(sofa._same_physical_league(row,match))
        self.assertFalse(sofa._same_physical_league(
            {"id_campeonato":23,"campeonato":"Italiano"},match
        ))

    def test_mandante_encontra_id_por_data_campeonato_e_clube(self):
        with patch.object(sofa,"fetch_all",return_value=[
            {"id_jogo":16421100,"id_campeonato":8,"campeonato":"Espanhol",
             "clube":"Rayo Vallecano","id_clube":2818,"mando":"Casa"},
            {"id_jogo":16421100,"id_campeonato":8,"campeonato":"Espanhol",
             "clube":"Celta Vigo","id_clube":2821,"mando":"Fora"},
        ]) as query:
            match_id,source=sofa._physical_match(fixture())
        self.assertEqual(match_id,16421100)
        self.assertEqual(source,"dados_fisicos_mandante")
        sql,args=query.call_args.args
        self.assertIn("FROM dados_fisicos",sql)
        self.assertIn("data = %s",sql)
        self.assertEqual(args,(date(2026,10,31),))

    def test_visitante_e_consultado_se_mandante_nao_constar(self):
        with patch.object(sofa,"fetch_all",return_value=[
            {"id_jogo":16421100,"id_campeonato":8,"campeonato":"Espanhol",
             "clube":"Celta Vigo","id_clube":2821,"mando":"Fora"}
        ]):
            match_id,source=sofa._physical_match(fixture())
        self.assertEqual(match_id,16421100)
        self.assertEqual(source,"dados_fisicos_visitante")

    def test_nao_aceita_mandante_com_visitante_incorreto(self):
        with patch.object(sofa,"fetch_all",return_value=[
            {"id_jogo":16421100,"id_campeonato":8,"campeonato":"Espanhol",
             "clube":"Rayo Vallecano","id_clube":2818,"mando":"Casa"},
            {"id_jogo":16421100,"id_campeonato":8,"campeonato":"Espanhol",
             "clube":"Outro Clube","id_clube":999,"mando":"Fora"},
        ]):
            identifier,source=sofa._physical_match(fixture())
        self.assertIsNone(identifier)
        self.assertEqual(source,"dados_fisicos_nao_encontrado")

    def test_nao_usa_id_de_outra_liga_ou_clube(self):
        with patch.object(sofa,"fetch_all",return_value=[
            {"id_jogo":123,"id_campeonato":23,"campeonato":"Italiano",
             "clube":"Rayo Vallecano","id_clube":2818,"mando":"Casa"},
            {"id_jogo":321,"id_campeonato":8,"campeonato":"Espanhol",
             "clube":"Outro","id_clube":999,"mando":"Casa"},
        ]):
            identifier,source=sofa._physical_match(fixture())
        self.assertIsNone(identifier)
        self.assertEqual(source,"dados_fisicos_nao_encontrado")

    def test_ids_ambiguos_nao_sao_escolhidos_ao_acaso(self):
        with patch.object(sofa,"fetch_all",return_value=[
            {"id_jogo":222,"id_campeonato":8,"campeonato":"Espanhol",
             "clube":"Rayo Vallecano","id_clube":2818,"mando":"Casa"},
            {"id_jogo":333,"id_campeonato":8,"campeonato":"Espanhol",
             "clube":"Rayo Vallecano","id_clube":2818,"mando":"Casa"},
        ]):
            identifier,source=sofa._physical_match(fixture())
        self.assertIsNone(identifier)
        self.assertEqual(source,"dados_fisicos_ambiguo")

    def test_resolver_prioriza_dados_fisicos_antes_de_outra_tabela(self):
        with patch.object(sofa,"_get_match",return_value=fixture()), \
             patch.object(sofa,"_physical_match",
                          return_value=(16421100,"dados_fisicos_mandante")), \
             patch.object(sofa,"_same_match_id") as previous, \
             patch.object(sofa,"_external_match") as external:
            result=sofa.resolve_match_id(202)
        self.assertEqual(result["id"],16421100)
        self.assertEqual(result["fonte"],"dados_fisicos_mandante")
        previous.assert_not_called()
        external.assert_not_called()

    def test_jogo_correspondente_se_nao_houver_dados_fisicos(self):
        with patch.object(sofa,"_get_match",return_value=fixture()), \
             patch.object(sofa,"_physical_match",
                          return_value=(None,"dados_fisicos_nao_encontrado")), \
             patch.object(sofa,"_same_match_id",return_value=14083322):
            result=sofa.resolve_match_id(202)
        self.assertEqual(result["id"],14083322)
        self.assertEqual(result["fonte"],"jogo_correspondente")

    def test_sem_dados_fisicos_nem_clubes_mostra_alerta(self):
        with patch.object(sofa,"_get_match",return_value=fixture()), \
             patch.object(sofa,"_physical_match",
                          return_value=(None,"dados_fisicos_nao_encontrado")), \
             patch.object(sofa,"_same_match_id",return_value=None), \
             patch.object(sofa,"_external_match") as external:
            result=sofa.resolve_match_id(202)
        self.assertIsNone(result["id"])
        self.assertEqual(result["fonte"],"dados_fisicos_nao_encontrado")
        self.assertIn("ALERTA",result["mensagem"])
        self.assertIn("mandante",result["mensagem"])
        self.assertIn("visitante",result["mensagem"])
        external.assert_not_called()

    def test_ambiguidade_gera_alerta(self):
        with patch.object(sofa,"_get_match",return_value=fixture()), \
             patch.object(sofa,"_physical_match",
                          return_value=(None,"dados_fisicos_ambiguo")), \
             patch.object(sofa,"_same_match_id",return_value=None):
            result=sofa.resolve_match_id(202)
        self.assertIn("múltiplos",result["mensagem"])
        self.assertIsNone(result["id"])

    def test_sem_api_retorna_alerta_igual(self):
        with patch.object(sofa,"_get_match",return_value=fixture()), \
             patch.object(sofa,"_physical_match",
                          return_value=(None,"dados_fisicos_nao_encontrado")), \
             patch.object(sofa,"_same_match_id",return_value=None), \
             patch.object(sofa,"_external_match") as external:
            result=sofa.resolve_match_id(202,online=False)
        self.assertIsNone(result["id"])
        external.assert_not_called()

    def test_parse_id_de_link_oficial(self):
        self.assertEqual(sofa.parse_user_id(
            "https://www.sofascore.com/pt/football/match/remo-palmeiras/nOsmP#id:15238233"),
            15238233)
        self.assertEqual(sofa.parse_user_id("15238233"),15238233)
        with self.assertRaises(ValueError):
            sofa.parse_user_id("https://malicioso.com/pt/football/match/x#id:123")
        with self.assertRaises(ValueError):
            sofa.parse_user_id("https://www.sofascore.com/pt/football/match/x")
        with self.assertRaises(ValueError):
            sofa.parse_user_id("id:abc")

    def test_manual_nao_sobrescreve_jogo_de_outro_time(self):
        with patch.object(sofa,"_get_match",return_value=fixture()), \
             patch.object(sofa,"_same_match_id",return_value=None), \
             patch.object(sofa,"fetch_one",return_value={
                 "id": 99,"casa_id":77,"fora_id":17,"data":date(2026,10,31)
             }),patch.object(sofa,"execute") as execute:
            with self.assertRaisesRegex(ValueError,"outra partida"):
                sofa.set_match_id(202,"14083241")
        execute.assert_not_called()

    def test_manual_valida_id_pela_api_se_disponivel(self):
        with patch.object(sofa,"_get_match",return_value=fixture()), \
             patch.object(sofa,"_same_match_id",return_value=None), \
             patch.object(sofa,"fetch_one",return_value=None), \
             patch.object(sofa,"_read_json",return_value={
                 "event":event(15123456,home_id=999)
             }),patch.object(sofa,"execute") as execute:
            with self.assertRaisesRegex(ValueError,"clubes diferentes"):
                sofa.set_match_id(202,"15123456")
        execute.assert_not_called()

    def test_manual_grava_correto_quando_id_livre(self):
        with patch.object(sofa,"_get_match",return_value=fixture()), \
             patch.object(sofa,"_same_match_id",return_value=None), \
             patch.object(sofa,"fetch_one",return_value=None), \
             patch.object(sofa,"_read_json",return_value={"event":event(15123456)}), \
             patch.object(sofa,"execute",return_value=1) as execute:
            result=sofa.set_match_id(202,"15123456")
        self.assertEqual(result["id"],15123456)
        self.assertEqual(execute.call_count,1)
        self.assertIn("id_sofascore=%s",execute.call_args.args[0])


if __name__=="__main__":
    unittest.main()
