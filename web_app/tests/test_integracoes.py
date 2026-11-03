"""Testes das integrações sem consultar API real e sem gravar dados reais."""
import io
import json
from pathlib import Path
from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import patch,MagicMock
import queries_integracoes as qi
import queries_vinculos as qv

CLUBS=[{"id":1,"clube":"Flamengo","pais_id":1,"pais":"Brasil"},
       {"id":2,"clube":"Atlético","pais_id":1,"pais":"Brasil"},
       {"id":3,"clube":"Corinthians","pais_id":1,"pais":"Brasil"}]
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

    def test_csv_futpythontrader(self):
        raw=(b"Match_ID,Country,Season,League,Date,Home,Away,Odd_1_FT,Odd_X_FT,Odd_2_FT\n"
             b"123,Brazil,2026,Serie A Betano,02/11/2026,Flamengo,Corinthians,1.9,3.1,4.2\n")
        rows=qi._parse_response(raw,"text/csv")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["Odd_1_FT"],"1.9")
        self.assertEqual(qi._pick(rows[0],qi.HOME_KEYS),"Flamengo")
        self.assertEqual(qi._pick(rows[0],qi.AWAY_KEYS),"Corinthians")
        self.assertEqual(qi._pick(rows[0],qi.ID_KEYS),"123")
        self.assertEqual(qi._parse_game_date(rows[0]),"2026-11-02T00:00:00")

    def test_csv_preview_query_key_sem_persistencia(self):
        class CsvResponse:
            headers={"Content-Type":"text/csv"}
            def read(self,n):
                return b"Match_ID,Home,Away,Odd_1_FT\n1,Flamengo,Corinthians,1.80\n"
            def __enter__(self):return self
            def __exit__(self,*args):pass
        opener=MagicMock()
        opener.open.return_value=CsvResponse()
        qi._PREVIEWS.clear()
        with patch.dict(qi.os.environ,{"ODDS_API_ALLOWED_HOSTS":"futpythontrader.com.br"}),\
             patch.object(qi.socket,"getaddrinfo",return_value=[(2,1,6,"",("8.8.8.8",443))]),\
             patch.object(qi,"build_opener",return_value=opener),\
             patch.object(qi,"fetch_all",return_value=CLUBS):
            result=qi.preview({"base":"https://futpythontrader.com.br",
                "caminho":"/api/download/brazil/serie-a-betano/2026",
                "chave":"MINHA_CHAVE","cabecalho":"api_key"})
        req=opener.open.call_args.args[0]
        self.assertIn("api_key=MINHA_CHAVE",req.full_url)
        self.assertEqual(result["colunas"],["Match_ID","Home","Away","Odd_1_FT"])
        self.assertNotIn("MINHA_CHAVE",str(qi._PREVIEWS))

    def test_catalogo_filtra_pais_e_alias(self):
        clubes=CLUBS+[{"id":99,"clube":"Alavés","pais":"Espanha"}]
        with patch.object(qi,"fetch_all",return_value=clubes):
            catalogo=qi._catalogo_pais("Brazil")
            self.assertEqual(len(catalogo),3)
            self.assertNotIn(99,{c["id"] for c in catalogo})
            self.assertEqual([c["id"] for c in qi._catalogo_pais("Spain")],[99])
            self.assertEqual(qi._catalogo_pais("País inexistente"),[])
            revisao=qi._clubes_preview([{"Home":"Flamengo","Away":"Alavés"}],"Brasil")
        self.assertEqual(len(revisao["catalogo"]),3)
        alaves=next(c for c in revisao["clubes"] if c["original"]=="Alavés")
        self.assertIsNone(alaves["clube_id"])
        self.assertNotIn(99,[s["id"] for s in alaves["sugestoes"]])

    def test_api_neerlandesa_vincula_clubes_exatos_automaticamente(self):
        self.assertEqual(qi._metadata("/api/download/netherlands/eredivisie/2026"),
                         ("2026","Eredivisie","Holanda"))
        holanda=[
            {"id":192,"clube":"Feyenoord","pais":"Holanda"},
            {"id":182,"clube":"Excelsior","pais":"Holanda"},
            {"id":190,"clube":"ADO Den Haag","pais":"Holanda"},
        ]
        with patch.object(qi,"fetch_all",return_value=holanda):
            self.assertEqual(len(qi._catalogo_pais("Netherlands")),3)
            self.assertEqual(len(qi._catalogo_pais("Países Baixos")),3)
            result=qi._clubes_preview(
                [{"Home":"Feyenoord","Away":"Excelsior"},
                 {"Home":"Den Haag","Away":"Feyenoord"}],"Netherlands")
        by_name={c["original"]:c for c in result["clubes"]}
        self.assertEqual(by_name["Feyenoord"]["clube_id"],192)
        self.assertEqual(by_name["Excelsior"]["clube_id"],182)
        self.assertTrue(by_name["Feyenoord"]["correspondencia_automatica"])
        self.assertTrue(by_name["Excelsior"]["correspondencia_automatica"])
        self.assertIsNone(by_name["Den Haag"]["clube_id"])
        self.assertEqual(by_name["Den Haag"]["sugestoes"][0]["id"],190)

    def test_ao_trocar_pais_preserva_somente_edicoes_manuais(self):
        js=(Path(__file__).resolve().parents[1]/"static"/"js"/"integracoes.js").read_text(encoding="utf-8")
        self.assertIn('if(tr.dataset.manuallyEdited!=="1")continue',js)
        self.assertIn('document.querySelectorAll("#int-api-clubs tr")',js)
        self.assertIn('input.addEventListener("input"',js)
        self.assertIn('select.addEventListener("change"',js)

    def test_revisar_clubes_apos_alterar_pais(self):
        qi._PREVIEWS["pais"]={"rows":[{"Home":"Flamengo","Away":"Alavés"}],
                               "criado":qi.time.monotonic()}
        clubes=CLUBS+[{"id":99,"clube":"Alavés","pais":"Espanha"}]
        with patch.object(qi,"fetch_all",return_value=clubes):
            resultado=qi.revisar_clubes({"preview_id":"pais","pais":"Espanha"})
        self.assertEqual([c["id"] for c in resultado["catalogo"]],[99])
        alaves=next(c for c in resultado["clubes"] if c["original"]=="Alavés")
        self.assertEqual(alaves["clube_id"],99)

    def test_importacao_recusa_clube_de_outro_pais(self):
        qi._PREVIEWS["fora"]={"criado":qi.time.monotonic(),
            "columns":["Home","Away"],"country":"Brasil","league":"Serie A",
            "season":"2026","rows":[{"Home":"Flamengo","Away":"Alavés"}]}
        clubes=CLUBS+[{"id":99,"clube":"Alavés","pais":"Espanha"}]
        with patch.object(qi,"fetch_all",return_value=clubes),\
             patch.object(qi,"get_conn") as conn:
            with self.assertRaisesRegex(ValueError,"não pertence ao país"):
                qi.importar({"preview_id":"fora","colunas":["Home","Away"],
                    "clubes":[
                        {"original":"Flamengo","padronizado":"Flamengo","clube_id":1},
                        {"original":"Alavés","padronizado":"Alavés","clube_id":99}],
                    "pais":"Brasil"})
            conn.assert_not_called()

    def test_colunas_automatica_partida_e_odds(self):
        columns=["Match_ID","Country","Season","Div","League","Date","Time",
                 "Round","Home","Away","Home_Score","Away_Score","Bookie_1X2_FT",
                 "Odd_1_FT","Odd_X_FT","Over_FT_2_5","BTTS_Yes","CS_1_0",
                 "AH_Home_neg_0_5","EH_Home_neg_1","xG_Home_FT"]
        result=qi._default_columns(columns)
        for name in ("Match_ID","Home","Away","Odd_1_FT","CS_1_0"):
            self.assertIn(name,result)
        for name in ("Time","Bookie_1X2_FT","xG_Home_FT",
                     "AH_Home_neg_0_5","EH_Home_neg_1"):
            self.assertNotIn(name,result)

    def test_autopreenchimento_de_clubes_com_estado(self):
        catalogo=[
            {"id":7,"clube":"Chapecoense","pais":"Brasil"},
            {"id":8,"clube":"Bragantino","pais":"Brasil"},
            {"id":9,"clube":"Corinthians","pais":"Brasil"},
            {"id":10,"clube":"Coritiba","pais":"Brasil"},
            {"id":99,"clube":"Alavés","pais":"Espanha"},
        ]
        with patch.object(qi,"fetch_all",return_value=catalogo):
            result=qi._clubes_preview([
                {"Home":"Chapecoense-SC","Away":"Bragantino"},
                {"Home":"Corinthians","Away":"Coritiba"},
            ],"Brazil")
        self.assertEqual(len(result["catalogo"]),4)
        chapecoense=next(c for c in result["clubes"]
                          if c["original"]=="Chapecoense-SC")
        self.assertEqual(chapecoense["clube_id"],7)
        self.assertEqual(chapecoense["padronizado"],"Chapecoense")
        self.assertTrue(chapecoense["correspondencia_automatica"])
        self.assertEqual(chapecoense["similaridade_automatica"],98)
        self.assertTrue(all(c["clube_id"] is not None for c in result["clubes"]))
        self.assertTrue(all(c["correspondencia_automatica"] for c in result["clubes"]))

    def test_handicap_removido_da_previa_historico_e_importacao(self):
        cols=["Match_ID","Home","Away","Odd_1_FT","AH_Home_neg_1_5",
              "Bookie_AH_neg_1_5","EH_Home_neg_1","Bookie_EH_neg_1"]
        self.assertEqual(qi._default_columns(cols),
                         ["Match_ID","Home","Away","Odd_1_FT"])
        with patch.object(qi,"fetch_all",return_value=[{"colunas":cols}]):
            self.assertEqual(qi._last_columns(),
                             ["Match_ID","Home","Away","Odd_1_FT"])
        qi._PREVIEWS["handicap"]={
            "criado":qi.time.monotonic(),
            "columns":cols,
            "rows":[{"Home":"Bragantino","Away":"Corinthians"}],
            "country":"Brasil","league":"Serie A","season":"2026"
        }
        with self.assertRaisesRegex(ValueError,"Escolha colunas existentes"):
            qi.importar({"preview_id":"handicap",
                         "colunas":["AH_Home_neg_1_5"],"clubes":[]})
        self.assertTrue(qi._is_handicap_column("Bookie_EH_neg_1"))
        self.assertFalse(qi._is_handicap_column("Odd_1_FT"))

    def test_checkbox_usa_lista_e_destaque_e_renderiza(self):
        js=(Path(__file__).resolve().parents[1]/"static"/"js"/"integracoes.js").read_text(encoding="utf-8")
        self.assertIn('const checkboxes=$$("#int-api-columns input[type=checkbox]")',js)
        self.assertIn('const total=$$("#int-api-columns input[type=checkbox]").length',js)
        self.assertIn('const selected=$$("#int-api-columns input[type=checkbox]:checked").length',js)
        self.assertIn('tr.classList.toggle("int-match-auto",on)',js)
        self.assertNotIn('const checkboxes=$("#int-api-columns input[type=checkbox]")',js)

    def test_controles_chave_e_loading_importacao_ui(self):
        root=Path(__file__).resolve().parents[1]
        html=(root/"templates"/"api_connect.html").read_text(encoding="utf-8")
        css=(root/"static"/"css"/"integracoes.css").read_text(encoding="utf-8")
        js=(root/"static"/"js"/"integracoes.js").read_text(encoding="utf-8")
        self.assertIn('id="int-api-save-key" checked',html)
        self.assertIn('class="int-save-switch"',html)
        self.assertIn('id="int-api-delete-key" class="int-delete-key" disabled',html)
        self.assertIn('id="int-api-key-status" role="status"',html)
        self.assertIn('id="int-import-loader" class="int-loader-overlay" hidden',html)
        self.assertIn('role="dialog" aria-modal="true"',html)
        self.assertIn('id="int-loader-console"',html)
        self.assertIn('role="progressbar"',html)
        self.assertIn('progresso indeterminado',html.lower())
        self.assertIn('integracoes.js?v=10',html)
        self.assertIn('integracoes.css?v=4',html)
        self.assertIn('.int-loader-overlay[hidden]{display:none!important}',css)
        self.assertIn('prefers-reduced-motion:reduce',css)
        self.assertIn('function beginImportLoader(total,seasonCount)',js)
        self.assertIn('function endImportLoader()',js)
        self.assertIn('beginImportLoader(data.total,seasonCount)',js)
        self.assertIn('finally{endImportLoader();btn.disabled=false;}',js)
        self.assertIn('function updateKeyUI(saved,error=false)',js)
        self.assertIn('deleteButton.disabled=!saved||error',js)
        self.assertIn('await keyStatus()',js)
        self.assertNotIn('Math.random()',js)

    def test_lay_simulado_escada_e_fonte_preferida(self):
        self.assertEqual(qi._simulated_lay("1.85"),1.86)
        self.assertEqual(qi._simulated_lay("2.00"),2.02)
        self.assertEqual(qi._simulated_lay("3.00"),3.05)
        self.assertEqual(qi._simulated_lay("2.38",asian=True),2.39)
        self.assertIsNone(qi._simulated_lay("1000"))
        row={"Odd_1_FT":"1.85","Odd_X_FT":"3.10",
             "Bookie_1X2_FT":"Bet365","Over_FT_2_5":"2.08",
             "Bookie_OU_FT_2_5":"Pinnacle",
             "CS_1_0":"7.5","Bookie_CS_1_0":"Outra Casa",
             "Home":"Flamengo","xG_Home_FT":"1.5"}
        data=qi._enriquecer_lay(row,["Home","Odd_1_FT","Odd_X_FT",
                                      "Over_FT_2_5","CS_1_0"])
        self.assertEqual(data["Lay_Simulado_Odd_1_FT"],1.86)
        self.assertEqual(data["Lay_Simulado_Over_FT_2_5"],2.10)
        self.assertEqual(data["_metodo_lay_simulado"]["comissao_pct"],4.5)
        self.assertFalse(data["_metodo_lay_simulado"]["precificacao_real"])
        self.assertEqual(data["_bookmakers_das_odds"]["Odd_1_FT"]["bookmaker"],"Bet365")
        self.assertTrue(data["_bookmakers_das_odds"]["Over_FT_2_5"]["preferencial"])
        self.assertFalse(data["_bookmakers_das_odds"]["CS_1_0"]["preferencial"])
        self.assertNotIn("Lay_Simulado_Home",data)

    def test_reutiliza_colunas_da_ultima_importacao(self):
        with patch.object(qi,"fetch_all",return_value=[
            {"colunas":["Home","Away","Odd_2_FT"]}
        ]):
            selected=qi._last_columns()
        self.assertEqual(selected,["Home","Away","Odd_2_FT"])
        self.assertEqual([c for c in selected if c in ["Home","Away"]],
                         ["Home","Away"])

    def test_fisico_colunas_e_nomenclatura_lay(self):
        row={"Match_ID":"zoPwpY9j","Date":"25/02/2026",
             "Home_Score":"2","Odd_1_FT":"2.10","Bookie_1X2_FT":"bet365",
             "Home":"Gremio","Away":"Atletico-MG"}
        result=qi._linha_colunas(row,[
            "Match_ID","Date","Home_Score","Odd_1_FT","Home","Away"])
        self.assertEqual(result["match_id"],"zoPwpY9j")
        self.assertEqual(result["home_score"],2)
        self.assertEqual(result["date"].isoformat(),"2026-02-25")
        self.assertEqual(result["odd_1_ft"],qi.Decimal("2.10"))
        self.assertEqual(result["lay_odd_1_ft"],qi.Decimal("2.12"))
        self.assertEqual(result["bookie_odd_1_ft"],"bet365")
        self.assertNotIn("Lay_Simulado_Odd_1_FT",result)

    def test_importacao_sem_dados_novos_nao_registra_lote(self):
        qi._PREVIEWS["repetido"]={"criado":qi.time.monotonic(),
          "host":"api.exemplo.com","path":"/api/download/brazil/serie-a-betano/2026",
          "season":"2026","league":"Serie A Betano","country":"Brasil",
          "columns":["Home","Away","Odd_1_FT"],
          "rows":[{"Home":"Flamengo","Away":"Atlético","Odd_1_FT":"1.80"}]}
        fake=MagicMock()
        cur=fake.cursor.return_value.__enter__.return_value
        cur.fetchone.side_effect=[{"id":10},None]
        @contextmanager
        def conn():yield fake
        with patch.object(qi,"get_conn",conn),patch.object(qi,"fetch_all",return_value=CLUBS):
            result=qi.importar({"preview_id":"repetido",
                "colunas":["Home","Away","Odd_1_FT"],
                "clubes":[{"original":"Flamengo","padronizado":"Flamengo","clube_id":1},
                           {"original":"Atlético","padronizado":"Atlético","clube_id":2}]})
        self.assertEqual(result["inseridos"],0)
        self.assertEqual(result["ignorados"],1)
        self.assertIsNone(result["importacao_id"])
        fake.rollback.assert_called_once()
        fake.commit.assert_not_called()

    def test_chave_salva_no_cofre_apos_previa(self):
        payload={"matches":[{"Home":"Flamengo","Away":"Atlético","Odd_1_FT":"1.8"}]}
        opener=MagicMock()
        opener.open.return_value=Response(payload)
        with patch.object(qi,"build_opener",return_value=opener),\
             patch.object(qi.socket,"getaddrinfo",
                 return_value=[(2,1,6,"",("8.8.8.8",443))]),\
             patch.object(qi,"fetch_all",return_value=CLUBS),\
             patch.object(qi.keyring,"set_password") as save,\
             patch.object(qi.keyring,"get_password",return_value=None):
            qi.preview({"base":"https://futpythontrader.com.br",
              "caminho":"/api/download/brazil/serie-a-betano/2026",
              "chave":"TESTE_NAO_REAL","cabecalho":"api_key",
              "salvar_chave":True})
        save.assert_called_once_with(qi._KEYRING_SERVICE,
                                     "futpythontrader.com.br","TESTE_NAO_REAL")

    def test_lista_temporadas_ano_simples_e_intervalo(self):
        brasil="/api/download/brazil/serie-a-betano/2026"
        bulgaria="/api/download/bulgaria/vtora-liga/2026-2027"
        self.assertEqual(qi._temporadas_da_requisicao(
            brasil,"2026, 2025, 2024, 2026\n2023; 2022; 2021"),
            ["2026","2025","2024","2023","2022","2021"])
        self.assertEqual(qi._temporadas_da_requisicao(
            bulgaria,"2026-2027, 2025-2026, 2024-2025"),
            ["2026-2027","2025-2026","2024-2025"])
        self.assertEqual(qi._metadata(bulgaria),
                         ("2026-2027","Vtora Liga","Bulgária"))
        self.assertEqual(qi._temporadas_da_requisicao(brasil,""),["2026"])
        with self.assertRaisesRegex(ValueError,"Não misture"):
            qi._temporadas_da_requisicao(brasil,"2026, 2025-2026")
        with self.assertRaisesRegex(ValueError,"consecutivo"):
            qi._temporadas_da_requisicao(bulgaria,"2026-2028")
        with self.assertRaisesRegex(ValueError,"1 a 12"):
            qi._temporadas_da_requisicao(brasil,",".join(str(x) for x in range(2020,2033)))

    def test_previa_consulta_duas_temporadas_sem_repetir_chave(self):
        resp1=Response({"matches":[
            {"Match_ID":"id26","Home":"Flamengo","Away":"Corinthians",
             "Season":"2026","Odd_1_FT":"2.1"}]})
        resp2=Response({"matches":[
            {"Match_ID":"id25","Home":"Flamengo","Away":"Corinthians",
             "Season":"2025","Odd_1_FT":"1.9"}]})
        opener=MagicMock()
        opener.open.side_effect=[resp1,resp2]
        with patch.object(qi.socket,"getaddrinfo",
                          return_value=[(2,1,6,"",("8.8.8.8",443))]),\
             patch.object(qi,"build_opener",return_value=opener),\
             patch.object(qi,"fetch_all",return_value=CLUBS),\
             patch.object(qi,"_last_columns",return_value=None),\
             patch.object(qi.keyring,"get_password",return_value=None):
            result=qi.preview({
                "base":"https://futpythontrader.com.br",
                "caminho":"/api/download/brazil/serie-a-betano/2026",
                "temporadas":"2026, 2025","chave":"EXEMPLO_TESTE",
                "cabecalho":"api_key"
            })
        self.assertEqual(result["total"],2)
        self.assertEqual(result["temporadas"],["2026","2025"])
        self.assertEqual([x["partidas"] for x in result["temporadas_resultado"]],[1,1])
        urls=[call.args[0].full_url for call in opener.open.call_args_list]
        self.assertIn("/2026?api_key=EXEMPLO_TESTE",urls[0])
        self.assertIn("/2025?api_key=EXEMPLO_TESTE",urls[1])
        stored=qi._PREVIEWS[result["preview_id"]]
        self.assertEqual(stored["row_seasons"],["2026","2025"])
        self.assertNotIn("EXEMPLO_TESTE",str(stored))

    def test_previa_relata_temporada_sem_resposta(self):
        from urllib.error import HTTPError
        opener=MagicMock()
        opener.open.side_effect=[
            HTTPError("https://futpythontrader.com.br",404,"Not Found",None,None),
            Response({"matches":[{"Home":"Flamengo","Away":"Corinthians","Match_ID":"B"}]})
        ]
        with patch.object(qi.socket,"getaddrinfo",
                          return_value=[(2,1,6,"",("8.8.8.8",443))]),\
             patch.object(qi,"build_opener",return_value=opener),\
             patch.object(qi,"fetch_all",return_value=CLUBS),\
             patch.object(qi,"_last_columns",return_value=None),\
             patch.object(qi.keyring,"get_password",return_value=None):
            result=qi.preview({
                "base":"https://futpythontrader.com.br",
                "caminho":"/api/download/brazil/serie-a-betano/2026",
                "temporadas":"2026, 2025"
            })
        self.assertEqual(result["total"],1)
        self.assertEqual([x["status"] for x in result["temporadas_resultado"]],
                         ["erro","ok"])
        self.assertEqual(result["temporadas_resultado"][0]["mensagem"],"HTTP 404")
        self.assertEqual(qi._PREVIEWS[result["preview_id"]]["row_seasons"],["2025"])

    def test_importacao_multitemporada_mantem_ano_da_url(self):
        qi._PREVIEWS["multiseason"]={
          "criado":qi.time.monotonic(),
          "host":"futpythontrader.com.br",
          "path":"/api/download/brazil/serie-a-betano/2026",
          "paths":{"2026":"/api/download/brazil/serie-a-betano/2026",
                   "2025":"/api/download/brazil/serie-a-betano/2025"},
          "season":"2026","country":"Brasil","league":"Serie A Betano",
          "multiplas_temporadas":True,
          "row_seasons":["2026","2025"],
          "columns":["Home","Away","Match_ID","Season","Odd_1_FT"],
          "rows":[
              {"Home":"Flamengo","Away":"Corinthians","Match_ID":"A",
               "Season":"2025","Odd_1_FT":"2.1"},
              {"Home":"Flamengo","Away":"Corinthians","Match_ID":"B",
               "Season":"2026","Odd_1_FT":"1.8"}
          ]}
        fake=MagicMock()
        cur=fake.cursor.return_value.__enter__.return_value
        cur.fetchone.side_effect=[{"id":101},{"id":1001},
                                  {"id":102},{"id":1002}]
        @contextmanager
        def conn():yield fake
        with patch.object(qi,"get_conn",conn),\
             patch.object(qi,"fetch_all",return_value=CLUBS):
            result=qi.importar({
                "preview_id":"multiseason","colunas":["Home","Away","Match_ID",
                    "Season","Odd_1_FT"],"temporada":"2026, 2025",
                "clubes":[{"original":"Flamengo","padronizado":"Flamengo","clube_id":None},
                           {"original":"Corinthians","padronizado":"Corinthians","clube_id":None}]})
        self.assertEqual(result["inseridos"],2)
        self.assertEqual([x["temporada"] for x in result["importacoes"]],["2026","2025"])
        inserts=[call.args[1] for call in cur.execute.call_args_list
                 if len(call.args)>1 and isinstance(call.args[1],list)]
        self.assertEqual(len(inserts),2)
        self.assertEqual([params[4] for params in inserts],["2026","2025"])
        self.assertEqual([params[0] for params in inserts],[101,102])
        fake.commit.assert_called_once()

    def test_importacao_atomica_commit_sem_chave(self):
        qi._PREVIEWS.clear()
        qi._PREVIEWS["abc"]={"criado":qi.time.monotonic(),"host":"api.exemplo.com",
         "path":"/api/download/brazil/serie-a-betano/2026",
         "season":"2026","league":"Serie A Betano","country":"Brasil",
         "columns":["home_team","away_team","odds"],"rows":[
         {"home_team":"Flamengo","away_team":"Atlético","odds":1.75}]}
        fake=MagicMock()
        cursor=fake.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect=[{"id":5},{"id":99},{"clube_id":1},{"clube_id":2}]
        @contextmanager
        def conn():yield fake
        with patch.object(qi,"get_conn",conn),patch.object(qi,"fetch_all",
            return_value=CLUBS):
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
