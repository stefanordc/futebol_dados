"""Testes da justificativa com IA; nunca realiza chamada externa."""
import json
import os
import unittest
from unittest.mock import patch
import queries_x1_texto as textgen


class FakeHTTP:
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,*args):
        return json.dumps({"output":[{"type":"message","content":[{"type":"output_text","text":"O mandante tem mais pontos por jogo. O índice não é probabilidade."}]}]}).encode()
    def __iter__(self):return iter([])


class TestText(unittest.TestCase):
    def setUp(self):
        self.payload={
            "mandante":"Mandante","visitante":"Visitante",
            "temporada":"2026/2027","recorte":"20",
            "indice_mandante":65.2,"indice_visitante":34.8
        }

    @patch.dict(os.environ,{},clear=True)
    @patch.object(textgen,"urlopen")
    def test_sem_api_key_nao_faz_chamada(self,request):
        with self.assertRaisesRegex(RuntimeError,"OPENAI_API_KEY"):
            textgen.gerar_texto(self.payload)
        request.assert_not_called()

    @patch.dict(os.environ,{"OPENAI_API_KEY":"local_fake_key","OPENAI_TEXT_MODEL":"gpt-5.5"})
    @patch.object(textgen,"urlopen")
    def test_requisicao_store_false_sem_chave_no_payload(self,request):
        request.return_value=FakeHTTP()
        # json.load no FakeHTTP lê por iterador? patch json.load como decode de bytes.
        with patch.object(textgen.json,"load",return_value={"output":[{"type":"message","content":[{"type":"output_text","text":"Texto explicativo realista."}]}]}):
            out=textgen.gerar_texto(self.payload)
        self.assertEqual(out,"Texto explicativo realista.")
        call=request.call_args
        body=json.loads(call.args[0].data.decode())
        self.assertFalse(body["store"])
        self.assertIn("não é",body["instructions"].lower())
        self.assertNotIn("local_fake_key",json.dumps(body))
        self.assertEqual(call.kwargs["timeout"],15)

    @patch.dict(os.environ,{"OPENAI_API_KEY":"local_fake_key"})
    @patch.object(textgen,"urlopen")
    def test_indice_invalido_e_limite(self,request):
        bad={**self.payload,"indice_mandante":120}
        with self.assertRaises(ValueError):
            textgen.gerar_texto(bad)
        with self.assertRaises(ValueError):
            textgen.gerar_texto({**self.payload,"campeonato":"x"*6000})
        request.assert_not_called()


if __name__=="__main__":
    unittest.main()
