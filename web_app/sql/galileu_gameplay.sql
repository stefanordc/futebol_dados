-- Galileu Gameplay: estado privado por navegador; nada exposto no Data API.
BEGIN;
CREATE SCHEMA IF NOT EXISTS galileu_private;
REVOKE ALL ON SCHEMA galileu_private FROM PUBLIC, anon, authenticated;
CREATE TABLE IF NOT EXISTS galileu_private.sessoes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash char(64) NOT NULL UNIQUE,
  corte date NOT NULL,
  banca_inicial numeric(16,2) NOT NULL CHECK (banca_inicial>0),
  banca_atual numeric(16,2) NOT NULL CHECK (banca_atual>=0),
  gestao_pct numeric(6,3) NOT NULL CHECK (gestao_pct>0 AND gestao_pct<=100),
  stake_fixa numeric(16,2) CHECK (stake_fixa IS NULL OR stake_fixa>0),
  indice_rodada integer NOT NULL DEFAULT 0 CHECK (indice_rodada>=0),
  fase text NOT NULL DEFAULT 'aberta' CHECK (fase IN ('aberta','revelada','concluida')),
  versao integer NOT NULL DEFAULT 1,
  criado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS galileu_private.entradas (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  sessao_id uuid NOT NULL REFERENCES galileu_private.sessoes(id) ON DELETE CASCADE,
  jogo_id integer NOT NULL REFERENCES public.jogos(id),
  indice_rodada integer NOT NULL,
  tipo text NOT NULL CHECK (tipo IN ('manual','metodo')),
  metodo_id bigint,
  metodo_versao integer,
  metodo_nome text,
  mercado text NOT NULL,
  odd numeric(10,3) NOT NULL CHECK (odd>=1.01 AND odd<=1000),
  stake numeric(16,2) NOT NULL CHECK (stake>0),
  cotacao_estimada boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente','green','red')),
  lucro_prejuizo numeric(16,2),
  criada_em timestamptz NOT NULL DEFAULT now(),
  finalizada_em timestamptz,
  CONSTRAINT galileu_jogo_unico UNIQUE(sessao_id,jogo_id),
  CONSTRAINT galileu_status_financeiro CHECK (
    (status='pendente' AND lucro_prejuizo IS NULL AND finalizada_em IS NULL)
    OR (status IN ('green','red') AND lucro_prejuizo IS NOT NULL AND finalizada_em IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS galileu_entradas_sessao_rodada ON galileu_private.entradas(sessao_id,indice_rodada);
CREATE INDEX IF NOT EXISTS galileu_entradas_sessao_status ON galileu_private.entradas(sessao_id,status);
REVOKE ALL ON galileu_private.sessoes,galileu_private.entradas FROM PUBLIC,anon,authenticated;
REVOKE USAGE ON SCHEMA galileu_private FROM anon,authenticated;
ALTER TABLE galileu_private.sessoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE galileu_private.entradas ENABLE ROW LEVEL SECURITY;
COMMIT;