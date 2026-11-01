## Favoritômetro — funcionamento

O painel **x1 → Favoritômetro** apresenta um **índice de força relativa**, de 0 a 100 dividido entre dois clubes. Ele não é a probabilidade 1X2 nem garantia de favoritismo real. Ao lado, a projeção Poisson existente mostra **separadamente** as probabilidades de vitória mandante, empate e vitória visitante.

**Componentes do índice, na configuração inicial:**
- 65%: comparação entre chances de vitória do Poisson existentes, condicionadas ao não empate. O Poisson já contém força técnica e mando de campo.
- 15%: pontos médios dos clubes no recorte escolhido.
- 10%: saldo médio de gols no recorte.
- 5%: saldo de xG criado menos xG concedido, somente com >=60% de cobertura e pelo menos 3 jogos por equipe.
- 5%: pontos do mandante **jogando em casa** contra pontos do visitante **jogando fora**, desde que ambos os recortes tenham >=3 partidas.
- Pesos são renormalizados quando há métricas indisponíveis; evidências descritivas têm sua influência reduzida proporcionalmente para menos de 20 partidas. Sem dados suficientes não é atribuído índice.
- Escalas e pesos são **heurísticos, não calibrados por backtesting**. O índice NÃO deve ser descrito como “chance de ganhar”. O Poisson 1X2 é exibido à parte.

**Narrativa:**
- Uma justificativa escrita de forma determinística, em português, acompanha sempre o resultado. Ela cita apenas o modelo e os dados comparados.
- O botão **Gerar justificativa com IA** chama `POST /api/apostas/x1/favoritometro/texto`. É opcional, executado **somente por clique** e não altera resultados. Requer `OPENAI_API_KEY` definido no ambiente do **servidor**, nunca no navegador ou em arquivo versionado. `OPENAI_TEXT_MODEL` permite configurar o modelo (padrão `gpt-5.5`). Usa Responses API com `store:false` e `timeout=15`. O serviço externo tem custos de API e pode falhar. Nesses casos mantém a narrativa determinística.
- Para Windows PowerShell, antes de iniciar o servidor:
  ```powershell
  $env:OPENAI_API_KEY = "SUA_CHAVE_API"
  $env:OPENAI_TEXT_MODEL = "gpt-5.5"
  python app.py
  ```
  Não coloque chaves no GitHub nem em código JavaScript. Para usar apenas o gerador local, não configure a chave.

**Layout:**
- Tabelas da aba **Análise de dados** centralizadas incluindo os nomes e o cabeçalho, mantendo a rolagem horizontal responsiva para tabelas grandes.
- Favoritômetro com barra proporcional laranja (mandante) e azul (visitante), identificação por escudo quando disponível, resumo, probabilidades 1X2 e explicação das evidências.

**Validação e limites:** Node e unittest para índices, cenários insuficientes, custos/segredos e respostas com mock. A interface e a resposta de IA real ainda precisam ser conferidas com o localhost e uma chave do usuário. Nenhuma migração ou tabela alterada.
