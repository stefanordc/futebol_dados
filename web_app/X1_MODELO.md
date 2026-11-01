# Apostas → x1: modelo experimental de confrontos

## Uso
Abra `/apostas`, depois a aba **x1 · Analisar confronto** (`/apostas/x1`).
Selecione campeonato, temporada, mandante e visitante (todos obrigatórios).
A API nova é `GET /api/apostas/x1?campeonato_id=...&mandante_id=...&visitante_id=...&temporada=...`.

## Como são estimadas as probabilidades
- Modelo supervisionado: regressão de contagem de gols Poisson, com forças ofensivas e defensivas por time, efeito casa e regularização ridge ajustada por gradiente. Treinamento limitado a até 3 temporadas com pesos maiores para dados recentes.
- Ajuste opcional de xG (20% conservador) se houver estatísticas suficientes, relativo à média da competição.
- Distribuição de gols Poisson **independente** por equipe, truncada apenas para agregação da tabela de placares. O x1 não usa informações sobre escalação confirmada, lesões, suspensões, transferências, minuto real de gols ou cotações de mercado.
- Over HT = aproximação de 46% da intensidade total de gols; "1x0 até 60" significa **placar exato no minuto 60**, obtido por 2/3 da intensidade total.
- Goleada = diferença de ao menos 3 gols ao final. A chance de abrir placar considera a hipótese de tempos exponenciais com taxas constantes e 0x0 como possibilidade.
- Intervalos de confiança e validação temporal fora da amostra **ainda não implementados**: não chamar de previsão calibrada ou sistema profissional validado.
- Precisa de ao menos 20 jogos registrados na competição e 4 jogos de cada clube na temporada escolhida.

## Radars
Os valores são **percentis relativos aos clubes da edição da competição** (0-100), não ratings absolutos nem avaliações oficiais EA/FIFA. Bola parada ofensiva usa xG de jogadas ensaiadas; faltam dados específicos de xG de bola parada sofrido, então o eixo defensivo fica sem nota. Jogo aéreo usa disputas aéreas como proxy, não um indicador situacional de ataque/defesa.

## Odds / EV
- **Odd justa** `1/P(evento)`: representa EV 0 (sem custos).
- **Back**: EV (por stake) = `P(evento)*odd - 1`; odds acima de `(1+0.03)/P` resultam em EV **modelado** +3% (sem considerar comissão back).
- **Lay**: EV (por stake do backer) = `(1-P)*(1-0.02) - P*(odd-1)`, com 2% de comissão hipotética sobre ganho; preços abaixo de `1+((1-P)*(1-0.02)-0.03)/P` dão EV modelado de pelo menos +3%. O risco financeiro real de lay é a responsabilidade `odd-1`.
- O programa **não obtém odds atuais**: a comparação é feita com preço digitado pelo usuário. Não existe oportunidade de valor comprovada sem odd real.
- Baixa amostra e modelos não calibrados podem causar erros relevantes. Use apenas como exploração estatística, não recomendação financeira ou incentivo a apostas.

## Operação
Execute `python app.py` em `web_app`. Não exige novas dependências Python nem migração no banco.
Os endpoints antigos permanecem inalterados. A consulta é somente leitura e pode levar alguns segundos em campeonatos grandes; índices de `jogos(campeonato_id, temporada)` e `estatisticas(jogo_id, periodo)` ajudam.

## Checklist
- [ ] Sidebar sem barra horizontal na versão recolhida e expandida
- [ ] Apostas antiga preservada e botão x1 acessível
- [ ] Filtros obrigatórios e mandante diferente de visitante
- [ ] Erro claro em campeonato com menos de 20 jogos
- [ ] Soma das probabilidades 1X2 ≈ 100%; mapa de placares ≈ 100%
- [ ] Troca de tema e uso em mobile
- [ ] Modo de odds back/lay testado e valores positivos apenas com odd oferecida adequada
- [ ] Banco local verificado e performance mensurada; validação estatística fora da amostra antes de uso decisório
