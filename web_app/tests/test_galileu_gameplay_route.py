"""Smoke test ASGI: primeira abertura da gameplay não consulta o Supabase."""
import asyncio
import json
from unittest import TestCase
from unittest.mock import patch

from app import app
import queries_galileu_gameplay as game


async def get_without_cookie():
    result=[]
    async def send(message):
        result.append(message)
    async def receive():
        return {"type":"http.request","body":b"","more_body":False}
    scope={
      "type":"http","asgi":{"version":"3.0"},"http_version":"1.1",
      "method":"GET","scheme":"http","server":("127.0.0.1",8000),
      "client":("127.0.0.1",50000),
      "root_path":"","path":"/api/apostas/galileu/gameplay/estado",
      "raw_path":b"/api/apostas/galileu/gameplay/estado",
      "query_string":b"","headers":[(b"host",b"127.0.0.1:8000")],
    }
    await app(scope,receive,send)
    status=next(m["status"] for m in result if m["type"]=="http.response.start")
    body=b"".join(m.get("body",b"") for m in result if m["type"]=="http.response.body")
    return status,json.loads(body.decode("utf-8"))


class TestGameplayHTTP(TestCase):
    def test_primeira_abertura_sem_cookie(self):
        with patch.object(game,"fetch_all",side_effect=AssertionError("Não pode consultar banco")):
            status,body=asyncio.run(get_without_cookie())
        self.assertEqual(status,200)
        self.assertEqual(body,{"iniciado":False})

    def test_token_ausente_nao_consulta_db(self):
        with patch.object(game,"fetch_all",side_effect=AssertionError("Sem cookie sem consulta")):
            self.assertEqual(game.estado(None),{"iniciado":False})
            self.assertEqual(game.estado(""),{"iniciado":False})
