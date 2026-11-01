# Nostradamus — backtest e navegação x1

## Interface
- Página `/apostas` redireciona para `/apostas/x1`. As duas páginas acessíveis na navegação são **x1** e **Nostradamus**, em `/apostas/nostradamus`; todas as sub-abas existentes do x1 permanecem.
- Liga → Rodadas: jogos sem placar têm link para `/apostas/x1?campeonato_id=...&temporada=...&mandante_id=...&visitante_id=...`, que preenche os filtros e inicia a análise.
- Nostradamus: data de corte, recorte 5/10/20 jogos ou temporada até a data, uma das ligas ou todas, objetivo back/lay e até 10 condições **AND** de mandante ou visitante contra valor fixo ou outro indicador. O nome é opcional para simular e obrigatório somente para salvar.
- Cada condição contém equipe analisada (mandante/visitante), indicador, comparador, referência (valor fixo, indicador do mandante ou indicador do visitante), indicador de referência quando aplicável, e valor desejado (ou ajuste somado à métrica de referência).
- Exemplo independente: **Visitante → Gols sofridos por jogo → > → Valor fixo → 1,5**.
- Exemplo comparativo: **Mandante → xG por jogo → > → Indicador do visitante → xG por jogo → ajuste 0**.
- Estratégias anteriores com os campos `metrica`, `comparador`, `margem` são interpretadas como mandante x visitante + margem, sem mudar resultados; elas são migradas ao serem carregadas no formulário.
- Configurações salvas no `localStorage` do próprio navegador (não sincronizadas com o Supabase). Limite de 50 estratégias, carregar/excluir disponíveis.
- Tabela por campeonato com entradas, green, red, win rate, cotadas e unidades. Expansão '+' revela até 400 partidas por liga com as métricas que atenderam os critérios.

## Segurança temporal (essencial)
- **Somente jogos concluídos e com data anterior ao dia atual**, e `data <= corte` (ambas as restrições também no SQL). Datas futuras nunca entram nos resultados.
- Histórico é organizado por **(campeonato, temporada, clube)**.
- Em cada partida de data D, as condições usam SOMENTE partidas anteriores a D. Os jogos de D só são inseridos no histórico depois que TODAS as partidas daquele dia foram avaliadas. Sem utilização dos eventos ou estatísticas da própria partida candidata.
- Usa até os últimos 5, 10 ou 20 jogos disponíveis, com mínimo de cinco partidas anteriores por clube; na opção temporada, todos os anteriores daquela temporada com mínimo de cinco. Dados faltantes não são convertidos em zero; estatísticas exigem pelo menos 60% de cobertura (e 3 partidas).
- Por segurança, odds históricas provenientes de `odds_fotmob` só entram se `criado_em::date < jogos.data` e somente para mercados 1X2 registrados. As odds capturadas após os jogos **não são odds pré-jogo** e são descartadas.
- Odd manual é **hipotética**, aplicada igualmente a todas as entradas, explicitamente rotulada. Sem odd admissível, exibe greens/reds/win rate, mas retorno financeiro em unidades não é calculável.
- Para back: 1u de risco; ganho `odd - 1` e red `-1`. Para lay: 1u de **responsabilidade**; green `(1-comissão)/(odd-1)`, red `-1`. A comissão é configurável (padrão 2%). Sem garantia de vantagem futura.

## Backend e testes
- Nova API de metadados `GET /api/apostas/nostradamus/metadata` e backtest `POST /api/apostas/nostradamus/testar`, sem mudanças de esquema ou de rotas antigas do x1.
- Testes unitários cronológicos cobrem vazamento temporal, empate do mesmo dia, mercados, odds pós-jogo, cobertura ausente, limites de condições e unidades back/lay.
- Dados brutos usam os jogos e `estatisticas` do Supabase, em consulta SQL somente leitura. Limite de processamento 20.000 partidas para controlar a memória; conjuntos acima desse tamanho necessitariam paginação ou pré-agregação.
- O modelo não faz previsão de jogos futuros; serve apenas para simular estratégias em amostras históricas, sujeitas a viés de seleção e sobreajuste.

## Construtor simplificado (novembro/2026)

- Ao criar uma condição, selecione **equipe analisada**, **indicador** e **comparador** (>, >=, <, <=, =, !=).
- **Comparar com → Valor absoluto:** informe o limite numérico, como visitante · gols sofridos/jogo > 1,5.
- **Comparar com → Mesmo indicador do adversário:** compara automaticamente o indicador selecionado com o mesmo indicador da outra equipe, sem valor numérico e sem margem. Ex.: mandante · xG > xG visitante, ou visitante · gols sofridos <= gols sofridos mandante.
- Os critérios são avaliados só com histórico disponível **antes da partida**. Dados ausentes nunca são presumidos iguais a 0.
- Estratégias antigas com comparação personalizada e margem continuam carregando na modalidade **Regra personalizada (salva anteriormente)**, que exibe referência original, indicador original e ajuste. Novas condições oferecem só as duas opções simples.
- O nome segue opcional para simular e obrigatório somente ao salvar.

## Correção — corte em 01/01/2025 e janela de 20 jogos

O código antigo exigia obrigatoriamente **20 jogos anteriores já disputados na mesma temporada**. Em 01/01/2025, as equipes tinham no máximo 15 (Bundesliga), 19 (LaLiga/Premier League) e 18 (Serie A) partidas na temporada 2024/25; por isso somente o Brasileiro passava. Esse filtro era excessivo.

Agora, **até N jogos (mínimo de 5)** significa:
- 5: os cinco jogos anteriores, desde que existam pelo menos cinco;
- 10: até dez jogos anteriores; caso existam só 5–9, usa todos os disponíveis;
- 20: até vinte jogos anteriores; caso existam só 5–19, usa os disponíveis;
- temporada: todos os jogos anteriores daquela temporada, mínimo cinco.
- Recortes **nunca usam partidas da data da entrada ou posteriores**. A chave histórica ainda é **(campeonato, temporada, clube)**, evitando misturar temporadas na análise. A data de corte limita somente os jogos elegíveis como entrada e o histórico.

Consultas no Supabase para `j.data < 2025-01-01` confirmaram os dados das cinco ligas (Brasileiro: 380; Premier League: 188; LaLiga: 181; Serie A: 178; Bundesliga: 135) e que todas possuíam xG para os dois clubes.

Também removidas as colunas de resumo **Entradas cotadas** e **Resultado (u)**, mantendo Entradas, Greens, Reds e Win rate. No detalhamento do jogo, a interface indica quantas partidas históricas de cada equipe entraram no cálculo e mantém odds opcionais para quem as informou. Retornos financeiros não entram na tabela-resumo.
