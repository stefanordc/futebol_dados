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


## Gráficos radar dos perfis (índices próprios, não oficiais)

Nas páginas `/clube/{id}`, `/jogador/{id}` e `/tecnico/{id}`, o frontend exibe um radar SVG sem biblioteca externa.

- **Clube e técnico (6 eixos):** Ataque, Defesa, Criatividade, Gols, Evitar gols, Eficiência.
- **Jogador (3 ofensivos + 3 defensivos):** Finalização, Criação, Drible, Desarme, Interceptação, Duelos.
- **Normalização:** índices heurísticos de 0 a 100 com referências fixas por jogo (jogadores: por 90 minutos); médias e taxas são limitadas a 100. Não são notas oficiais do FIFA nem predições.
- **Ataque e criação:** chutes, xG, chances e passes; **gols:** gols marcados por jogo; **defesa/evitar gols:** gols sofridos, jogos sem sofrer gols e eventos defensivos; **eficiência:** conversão de chutes e aproveitamento de pontos.
- **Jogador:** métricas reais de finalização, chances/assistências, dribles, desarmes, interceptações e duelos por 90 min; não substitui avaliações específicas de goleiros.
- **Técnico:** identifica os jogos em que ele consta nos detalhes (`tecnico_casa_id` ou `tecnico_fora_id`), aplica as métricas do time *nessas partidas*, e compara a força ofensiva com a defensiva. Diferença de pelo menos 12 pontos define a tendência ofensiva/defensiva; diferenças menores indicam equilíbrio. A classificação é uma aproximação estatística, não uma descrição tática observada.
- **Cobertura e desempenho:** até 100 partidas candidatas mais recentes para o técnico, quatro chamadas concorrentes; a análise informa amostras pequenas e consultas que falharem. Categorias sem dados são apresentadas como `—`. A área do radar não é preenchida quando há eixos ausentes.
- **Filtros:** temporada e, no perfil de clube, campeonato e mando; reprocessa quando a página é atualizada pelos filtros originais.

## Aba Gols

Usa o filtro Clube principal da página Estatísticas. Quando ele está em “Todos os clubes”, mostra o ranking por clube e o resumo agregado. O seletor de clube dentro da aba Gols foi removido.
