-- Cenários do Nostradamus ao vivo ficam separados dos métodos pré-jogo
-- para nunca serem interpretados pelo Galileu como métodos pré-jogo.
-- Schema privado, não exposto pela Data API do Supabase.
CREATE SCHEMA IF NOT EXISTS nostradamus_private;

CREATE TABLE IF NOT EXISTS nostradamus_private.estrategias_ao_vivo (
    id BIGSERIAL PRIMARY KEY,
    nome VARCHAR(80) NOT NULL CHECK (length(btrim(nome)) BETWEEN 1 AND 80),
    configuracao JSONB NOT NULL CHECK (jsonb_typeof(configuracao)='object'),
    versao INTEGER NOT NULL DEFAULT 1 CHECK (versao>0),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS nostradamus_ao_vivo_nome_unico
    ON nostradamus_private.estrategias_ao_vivo (lower(btrim(nome)));
