-- Galileu: entradas independentes por jogo e fechamento individual sem apagar apostas.
BEGIN;
ALTER TABLE galileu_private.entradas
  DROP CONSTRAINT IF EXISTS galileu_jogo_unico;

-- Métodos são exclusivos por jogo e sessão, independentemente da versão.
CREATE UNIQUE INDEX IF NOT EXISTS galileu_entradas_metodo_unico
  ON galileu_private.entradas(sessao_id, jogo_id, metodo_id)
  WHERE tipo = 'metodo';

CREATE TABLE IF NOT EXISTS galileu_private.jogos_finalizados (
  sessao_id uuid NOT NULL REFERENCES galileu_private.sessoes(id) ON DELETE CASCADE,
  jogo_id integer NOT NULL REFERENCES public.jogos(id),
  indice_rodada integer NOT NULL CHECK (indice_rodada >= 0),
  finalizado_em timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (sessao_id,jogo_id)
);
ALTER TABLE galileu_private.jogos_finalizados ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON galileu_private.jogos_finalizados FROM PUBLIC, anon, authenticated;
COMMIT;