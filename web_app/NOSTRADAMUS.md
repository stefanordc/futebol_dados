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
- Exige janela histórica completa: 5, 10, 20 ou pelo menos 5 jogos na opção temporada. Dados faltantes não são convertidos em zero; estatísticas exigem pelo menos 60% de cobertura (e 3 partidas).
- Por segurança, odds históricas provenientes de `odds_fotmob` só entram se `criado_em::date < jogos.data` e somente para mercados 1X2 registrados. As odds capturadas após os jogos **não são odds pré-jogo** e são descartadas.
- Odd manual é **hipotética**, aplicada igualmente a todas as entradas, explicitamente rotulada. Sem odd admissível, exibe greens/reds/win rate, mas retorno financeiro em unidades não é calculável.
- Para back: 1u de risco; ganho `odd - 1` e red `-1`. Para lay: 1u de **responsabilidade**; green `(1-comissão)/(odd-1)`, red `-1`. A comissão é configurável (padrão 2%). Sem garantia de vantagem futura.

## Backend e testes
- Nova API de metadados `GET /api/apostas/nostradamus/metadata` e backtest `POST /api/apostas/nostradamus/testar`, sem mudanças de esquema ou de rotas antigas do x1.
- Testes unitários cronológicos cobrem vazamento temporal, empate do mesmo dia, mercados, odds pós-jogo, cobertura ausente, limites de condições e unidades back/lay.
- Dados brutos usam os jogos e `estatisticas` do Supabase, em consulta SQL somente leitura. Limite de processamento 20.000 partidas para controlar a memória; conjuntos acima desse tamanho necessitariam paginação ou pré-agregação.
- O modelo não faz previsão de jogos futuros; serve apenas para simular estratégias em amostras históricas, sujeitas a viés de seleção e sobreajuste.
