# Frontend Dados Futebol

Frontend em HTML, CSS e JavaScript puro sobre o backend FastAPI existente.

## Interface
- Sidebar premium com Campeonatos, Jogos, Clubes, Jogadores, Técnicos, Árbitros, Estatísticas e Apostas.
- Temas claro/escuro persistentes.
- Página de Campeonatos: `/static/campeonatos.html`, usa `/api/ligas`.
- Estatísticas: Finalizações Realizadas, Finalizações Sofridas e Gols, sem endpoints novos.

## Limites
- O backend atual oferece partidas históricas, não calendário ao vivo.
- Finalizações Sofridas e Gols consultam os detalhes das partidas do clube e podem demorar.
- Categorias de gols só são apresentadas quando há dados identificáveis.
- O mapa atual de finalizações tem limite de 400 posições segundo a API existente.

## Rodar
Entre na pasta `web_app`, instale `requirements.txt` e execute `python app.py`.
Acesse `http://127.0.0.1:8000`. Mantenha o arquivo `.env` fora de commits.

## Sincronizar atualização
`git fetch origin && git switch main && git pull --ff-only origin main` (após merge do PR).
Antes, salve/commite alterações locais ou use `git stash` se necessário.
