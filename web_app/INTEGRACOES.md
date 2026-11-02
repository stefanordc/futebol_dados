# Conciliação de clubes e importação de odds

## Administração local

Páginas:
- `/vincular-clubes`: duas abas, **Dados físicos** e **Clubes das APIs de odds**.
- `/apostas/nostradamus/conectar-api`: prévia, revisão de clubes, seleção de colunas e importação.
- Na página Nostradamus existe a aba **Conectar API** e a sidebar inclui **Vincular Clubes**.

A lista de origem ignora registros que já estão em `clubes_fontes` e nomes exatamente iguais com correspondência única. Na aba física, o catálogo de destino inclui apenas clubes **ainda sem vínculo SofaScore**, mesmo se possuírem referência FotMob (no banco atual todos os clubes têm ao menos uma fonte). Para APIs, permite ligar outros clubes existentes, pois uma equipe pode ter múltiplas fontes.

Vínculos confirmados são gravados em `clubes_fontes`, com `fonte='sofascore'` ou `fonte='odds_api'`. Não modifica IDs nem nomes de `clubes` e bloqueia substituição silenciosa de vínculos existentes.

## Conectar API

A URL de exemplo `/api/download/brazil/serie-a-betano/2026` é apenas o **caminho**. Configure o domínio do provedor no `.env` (ex.: `ODDS_API_ALLOWED_HOSTS=api.seu-provedor.com`) e informe o endereço base HTTPS na página. O hostname do exemplo é ilustrativo.

- A chave da API pode ser enviada no cabeçalho `x-api-key` ou como `Authorization: Bearer`. Nunca salva no banco, cookie, URL, HTML de resposta nem localStorage.
- O servidor exige hostname explicitamente autorizado, DNS público, HTTPS, sem redirecionamentos nem parâmetros de URL, limite de 2MB, timeout de 12 segundos, até 500 partidas JSON, até 100 colunas.
- Tipos de lista comuns aceitos: array, `matches`, `fixtures`, `events`, `games`, `data`, `results`, `response` e outros. Quando o formato da API específica for conhecido, pode ser necessário adaptar o parser sem mudar o banco.
- Os clubes únicos são apresentados para edição. Correspondências sugeridas usam similaridade de nomes; o usuário escolhe livremente um clube cadastrado ou deixa sem referência.
- Temporada, campeonato e país são sugeridos pelo caminho; podem ser corrigidos antes de gravar.
- Todas as colunas retornadas entram na prévia. O usuário pode desmarcar qualquer coluna (inclusive todas menos uma); só as selecionadas ficam em `odds.dados`.
- Importação persiste **em uma transação** um registro em `odds_importacoes` e uma linha por partida em `odds`, com IDs, timestamps, informações padronizadas, metadados, payload JSON e vínculos aceitos.
- Nenhuma escrita ocorre na prévia. A prévia é mantida **somente na RAM do servidor** por até 20 minutos para impedir modificação arbitrária de registros pelo navegador; um reinício do processo exige nova consulta. Não é mecanismo de armazenamento do usuário.
- **Atenção:** `odds` guarda JSON bruto selecionado conforme a API, sem transformar automaticamente mercados em odds 1X2 padronizadas. A integração com Nostradamus/backtesting dependerá dos campos e das informações de data de cotação que a API efetivamente oferecer; não presumimos preços históricos anteriores aos jogos.

## Segurança e persistência

Tabelas `odds` e `odds_importacoes` estão em `public` com RLS habilitado e sem permissões diretas de Data API para `anon`, `authenticated` ou `service_role`. O backend usa a conexão Postgres de `SUPABASE_DB_URL`. **Rotas administrativas só respondem ao loopback (127.0.0.1 ou ::1); não publique essa ferramenta sem autenticação.**

## Testar

```powershell
cd "C:\Users\stefano.faria\Desktop\analise_dados\dados_futebol\jogos_ogol\web_app"
git status
git pull --ff-only origin main
python app.py
```

Verifique as duas páginas, importe um JSON de teste da sua API autorizada e consulte `SELECT id, criado_em, total_registros FROM odds_importacoes ORDER BY id DESC`; e `SELECT * FROM odds ORDER BY id DESC LIMIT 5`.

Os testes do CI usam dados fictícios e não importam odds nem alteram clubes reais.
