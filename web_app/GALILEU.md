# Galileu — registro de estratégias e banca virtual

## Telas
- `/apostas/galileu`: data de referência a partir de amanhã, jogos da próxima rodada **cadastrada** de cada competição, somente quando alguma estratégia salva no **mesmo navegador** for satisfeita. Não mostra placares futuros.
- O método salvo no Nostradamus define condições e um objetivo de mercado. Ao encontrar mais de uma estratégia para o confronto, é possível escolher qual. Há um segundo seletor para ajustar qual **entrada/mercado** será registrada nesse jogo (independente do mercado original do método).
- Clique no nome do confronto para abrir comparação das estatísticas anteriores (até 20 jogos por time, mínimo de 5, mesma liga e temporada) e clique em **Ver regras do método** para ver as condições com valores observados.
- Checkbox seleciona uma entrada por partida. O botão de confirmação exige confirmação explícita e grava atomicamente no Supabase.

## Persistência e imutabilidade
- Nova tabela `public.galileu_apostas` (DDL em `web_app/sql/galileu_apostas.sql`) com `UNIQUE(jogo_id)` para evitar duplicar a entrada no mesmo confronto.
- Cada linha armazena o nome do método, objetivo original, mercado escolhido, **snapshot das condições**, clubes, competição, amostra histórica e timestamp. Os métodos salvos continuam locais no Nostradamus; para outro navegador, salve novamente.
- Um trigger impede operações SQL `UPDATE` e `DELETE` sobre linhas já registradas; a API não fornece nenhuma operação de reversão. Administradores do banco ainda podem alterar o esquema ou remover a tabela, portanto “imutável” refere-se à aplicação e à proteção operacional das linhas, não a impossibilidade criptográfica absoluta.
- RLS ativado; nenhum acesso direto da Data API é concedido a `anon` ou `authenticated`. O backend Python grava usando a conexão existente `SUPABASE_DB_URL`. **Produto para uso local, sem autenticação multiusuário**.
- Para evitar registrar partida já iniciada, exige **data > hoje (America/Sao_Paulo)**, porque o banco atual registra somente a data do jogo, não horário de kickoff. Na revalidação, a transação bloqueia a linha do jogo e rejeita placares já registrados.
- O backend recalcula a aderência do método na confirmação, não confia em partidas ou condições precalculadas pelo navegador.
- Partidas futuras **nunca** entram nas estatísticas: SQL do Nostradamus limita a jogos concluídos até ontem e, dentro de cada jogo candidato, os indicadores exigem datas anteriores ao confronto.

## Relatório
- `/apostas/galileu/relatorio`: banca inicial **100 unidades virtuais**, banca atual **100 + greens − reds**.
- Resolvida: partida com data passada e placar conhecido; **green +1u**, **red −1u**. Uma entrada futura ou ainda sem placar fica **pendente**; não altera banca.
- Win rate é greens / (greens + reds), não inclui pendentes.
- Resumo por campeonato e por clube. Por clube, a mesma entrada figura para o mandante **e** visitante, portanto somar as linhas por clube duplica o número geral de partidas.
- Não envolve dinheiro, odds, execução de apostas ou garantias de ganho.

## Testes
- `python -m unittest discover -s tests -p 'test_galileu.py' -v`
- `node --check static/js/galileu.js`
- `node --check static/js/galileu-report.js`
- Testa: exclusão de jogos futuros/do mesmo dia do histórico; seleção de rodadas; método filtrado por liga; mínimo de cinco jogos; banca virtual e registros pendentes; rejeição de seleção inválida.

## Instalação
1. Rode a migration `web_app/sql/galileu_apostas.sql` no Supabase (já preparada para projeto conectado).
2. Atualize `main` localmente com `git pull --ff-only origin main` (salve modificações locais primeiro).
3. Reinicie `python app.py`; acesse `http://127.0.0.1:8000/apostas/galileu`.
4. Salve pelo menos uma estratégia no Nostradamus, no mesmo navegador e domínio.
