# X1 — análise descritiva de desempenho

**Rota:** `/apostas/x1`. Selecione campeonato, temporada, mandante, visitante e janela (5, 10, 20 jogos ou temporada inteira; padrão 20).

**API nova somente leitura:** `/api/apostas/x1/analise?campeonato_id=1&mandante_id=19&visitante_id=20&temporada=2026/2027&jogos=20`.

## Regras de amostragem

- Considera os últimos N jogos **concluídos** de cada time na competição e temporada selecionadas; inclui casa e fora, ordenado por data e ID. Exclui partidas com data futura e placar incompleto. Pode retornar menos que N jogos se não houver N partidas.
- Amostras são independentes: não são apenas confrontos diretos. A janela não modifica o modelo Poisson de probabilidades, que continua usando sua própria base de treinamento. Não existe vazamento de dados de placares futuros.
- Estatísticas de partida são obtidas de `estatisticas` para `periodo='Completo'` e o clube/rival correspondente; tipos de gol de `finalizacoes`; KM e sprints de `dados_fisicos`, com identificação segura pela competição de origem e pela data, nome/ID de clube e mando.
- Total de cada estatística = soma dos valores registrados. Média = total / jogos **com valor disponível** para aquela estatística, e não / número total de partidas quando houver lacunas. Cobertura `X/Y jogos` fica exibida por indicador.
- Razões (chutes/gol, passes certos/gol) usam gols SOMENTE nos jogos com a respectiva estatística. Se não houver gol na amostra coberta, a divisão é indisponível, não infinita.
- Precisão de chutes = chutes no alvo / chutes totais. Conversão de chutes = gols / chutes na mesma subamostra.
- Eficiência de conversão de xG = gols / xG na mesma subamostra ×100. Gols acima/abaixo do xG = soma(gols − xG) apenas em jogos com xG. Valores acima de 100% não provam superioridade sustentável em finalização, e podem refletir variância.
- Variância do saldo = variância **amostral** dos saldos (gols a favor − contra por jogo), com divisor n−1; desvios maiores significam mais dispersão, não necessariamente pior qualidade. Exige n ≥ 2. Variância não é alterada pelo controle total/média, porque é indicador de dispersão.
- Tipos de gol permitem sobreposição (ex.: pênalti + pé direito). A média de tipos usa número de partidas com mapa de finalizações; somas de tipos não representam o total de gols. Gol sem classificação suficiente não recebe classificação presumida.

## Navegação

Sub-abas: Resumo e resultados; Ataque e conversão; Defesa; Construção e passes; Tipos de gol; Consistência e jogos; Dados físicos; Disputas e disciplina.

A alternância **Média por jogo / Total** afeta contagens e volumes. Percentuais, razões, variâncias, posse de bola e indicadores já normalizados mantêm suas unidades.

## Escopo de segurança / testes

- Rota nova e arquivos frontend adicionados; nenhuma alteração em tabelas, migrations, contratos antigos de API ou motor Poisson.
- Testes automatizados com dados simulados cobrem variância amostral, razões alinhadas por cobertura, conversão de xG, zeros reais, nulos, metas de recorte e tipagem sobreposta de gols.
- Queries SQL baseadas na tabela `estatisticas` foram executadas no Supabase da aplicação. É necessária confirmação visual no localhost e validação de desempenho para uso contínuo.
