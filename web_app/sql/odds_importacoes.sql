-- Tabelas locais para importação revisável de odds.
-- Nunca armazene tokens de API nem URL com parâmetros de autenticação.
CREATE TABLE IF NOT EXISTS public.odds_importacoes (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 origem text NOT NULL,
 caminho text NOT NULL,
 pais text,
 campeonato text,
 temporada text,
 colunas jsonb NOT NULL DEFAULT '[]'::jsonb,
 total_registros integer NOT NULL DEFAULT 0,
 criado_em timestamptz NOT NULL DEFAULT now(),
 atualizado_em timestamptz NOT NULL DEFAULT now(),
 CONSTRAINT odds_importacoes_colunas_json CHECK (jsonb_typeof(colunas)='array')
);
CREATE TABLE IF NOT EXISTS public.odds (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 importacao_id bigint NOT NULL REFERENCES public.odds_importacoes(id) ON DELETE RESTRICT,
 linha_origem integer NOT NULL,
 fonte text NOT NULL,
 partida_externa_id text,
 temporada text,
 campeonato text,
 pais text,
 data_jogo timestamptz,
 mandante text,
 visitante text,
 mandante_id integer REFERENCES public.clubes(id) ON DELETE SET NULL,
 visitante_id integer REFERENCES public.clubes(id) ON DELETE SET NULL,
 dados jsonb NOT NULL DEFAULT '{}'::jsonb,
 criado_em timestamptz NOT NULL DEFAULT now(),
 atualizado_em timestamptz NOT NULL DEFAULT now(),
 CONSTRAINT odds_dados_obj CHECK (jsonb_typeof(dados)='object'),
 CONSTRAINT odds_importacao_linha_unique UNIQUE(importacao_id,linha_origem)
);
CREATE INDEX IF NOT EXISTS odds_por_campeonato_temporada ON public.odds(campeonato,temporada);
CREATE INDEX IF NOT EXISTS odds_por_data_jogo ON public.odds(data_jogo);
CREATE INDEX IF NOT EXISTS odds_por_mandante ON public.odds(mandante_id);
CREATE INDEX IF NOT EXISTS odds_por_visitante ON public.odds(visitante_id);
CREATE INDEX IF NOT EXISTS dados_fisicos_clube_externo_idx ON public.dados_fisicos(id_clube);
ALTER TABLE public.odds ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.odds_importacoes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.odds,public.odds_importacoes FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON SEQUENCE public.odds_id_seq,public.odds_importacoes_id_seq FROM PUBLIC,anon,authenticated,service_role;
-- Tudo é executado apenas pela conexão Postgres confiável do backend local.