# Web app — Análise de jogos

Interface estilo FotMob (sem notícias), alimentada pelo Postgres do projeto.

## Subir

```bash
cd web_app
pip install -r requirements.txt
python app.py
```

Abra http://127.0.0.1:8000

O `.env` usado é o da pasta pai (`jogos_ogol/.env`), com `SUPABASE_DB_URL`.

## Páginas

- `/` — últimos jogos inseridos, agrupados por liga
- `/jogo/{id}` — estatísticas, mapa de chutes, escalação e informações
