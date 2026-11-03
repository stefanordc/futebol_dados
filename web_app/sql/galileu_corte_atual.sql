-- Galileu: data de corte corrente separada da data inicial.
-- Preserva banca, indice, entradas e jogos já registrados.
ALTER TABLE galileu_private.sessoes
  ADD COLUMN IF NOT EXISTS corte_atual date;

UPDATE galileu_private.sessoes
SET corte_atual = corte
WHERE corte_atual IS NULL;

COMMENT ON COLUMN galileu_private.sessoes.corte_atual IS
  'Maior data da última lista exibida, após Próxima rodada; preserva corte inicial.';
