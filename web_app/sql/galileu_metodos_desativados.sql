-- Galileu: métodos desativados por sessão somente para meses futuros.
-- Preserva estratégias do Nostradamus, entradas, resultados e meses anteriores.
BEGIN;
CREATE TABLE IF NOT EXISTS galileu_private.metodos_desativados (
  sessao_id uuid NOT NULL REFERENCES galileu_private.sessoes(id) ON DELETE CASCADE,
  metodo_id bigint NOT NULL CHECK (metodo_id > 0),
  nome_metodo text NOT NULL,
  efetivo_desde char(7) NOT NULL CHECK (
    efetivo_desde ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
  ),
  criado_em timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (sessao_id, metodo_id)
);
CREATE INDEX IF NOT EXISTS galileu_metodos_desativados_mes
  ON galileu_private.metodos_desativados(sessao_id,efetivo_desde);
ALTER TABLE galileu_private.metodos_desativados ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON galileu_private.metodos_desativados FROM PUBLIC,anon,authenticated;
COMMENT ON TABLE galileu_private.metodos_desativados IS
  'Métodos excluídos da gameplay somente nos meses a partir de efetivo_desde; não exclui estratégia ou histórico.';
COMMIT;