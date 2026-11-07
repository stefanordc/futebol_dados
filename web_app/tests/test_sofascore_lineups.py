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

    def test_direto_sem_bater_na_api_externa(self):
        f=fixture()
        f["id_sofascore"]=14083322
        with patch.object(sofa,"_get_match",return_value=f), \
             patch.object(sofa,"_same_match_id") as mirrored, \
             patch.object(sofa,"_external_match") as external:
            result=sofa.resolve_match_id(202)
        self.assertEqual(result["id"],14083322)
        self.assertEqual(result["fonte"],"vinculo")
        mirrored.assert_not_called()
        external.assert_not_called()

    def test_busca_correspondente_na_mesma_data_sem_violar_unique(self):
        with patch.object(sofa,"_get_match",return_value=fixture()), \
             patch.object(sofa,"_same_match_id",return_value=14083322), \
             patch.object(sofa,"_external_match") as external:
            result=sofa.resolve_match_id(202)
        self.assertEqual(result["id"],14083322)
        self.assertEqual(result["fonte"],"jogo_correspondente")
        external.assert_not_called()

    def test_sofa_match_por_ids_dos_clubes_e_data(self):
        with patch.object(sofa,"_get_match",return_value=fixture()), \
             patch.object(sofa,"_same_match_id",return_value=None), \
             patch.object(sofa,"_events",side_effect=[
                 [event(15000000),event(13000000,home_id=999)],
             ]):
            result=sofa.resolve_match_id(202)
        self.assertEqual(result["id"],15000000)
        self.assertEqual(result["fonte"],"sofascore_api")

    def test_nao_adivinha_id_de_outro_jogo(self):
        with patch.object(sofa,"_events",side_effect=[
            [event(13000000,home_id=999)],[],[]
        ]):
            ident,status=sofa._external_match(fixture())
        self.assertIsNone(ident)
        self.assertEqual(status,"not_found")

    def test_resposta_indisponivel_encerra_e_mostra_opcao_manual(self):
        with patch.object(sofa,"_get_match",return_value=fixture()), \
             patch.object(sofa,"_same_match_id",return_value=None), \
             patch.object(sofa,"_events",return_value=None) as events:
            result=sofa.resolve_match_id(202)
        self.assertIsNone(result["id"])
        self.assertEqual(result["fonte"],"upstream_unavailable")
        events.assert_called_once()

    def test_id_ambiguo_nao_e_usado(self):
        with patch.object(sofa,"_events",return_value=[
            event(111),event(222)
        ]):
            ident,status=sofa._external_match(fixture())
        self.assertIsNone(ident)
        self.assertEqual(status,"ambiguous")

    def test_sem_correspondencia_sem_api_retorna_vazio(self):
        with patch.object(sofa,"_get_match",return_value=fixture()), \
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
