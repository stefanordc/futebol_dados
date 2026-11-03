-- Novos estados de liquidação do Galileu: programada -> green/red/sem_saldo.
-- As entradas existentes e seus resultados são preservados.
BEGIN;
ALTER TABLE galileu_private.entradas
  DROP CONSTRAINT IF EXISTS entradas_status_check,
  DROP CONSTRAINT IF EXISTS galileu_status_financeiro;
ALTER TABLE galileu_private.entradas
  ADD CONSTRAINT entradas_status_check
    CHECK (status IN ('pendente','green','red','sem_saldo')),
  ADD CONSTRAINT galileu_status_financeiro
    CHECK (
      (status='pendente' AND lucro_prejuizo IS NULL AND finalizada_em IS NULL)
      OR
      (status IN ('green','red') AND lucro_prejuizo IS NOT NULL AND finalizada_em IS NOT NULL)
      OR
      (status='sem_saldo' AND lucro_prejuizo=0 AND finalizada_em IS NOT NULL)
    );
COMMENT ON COLUMN galileu_private.entradas.status IS
  'pendente=entrada programada, green/red=executada e liquidada, sem_saldo=não executada por falta de saldo na data.';
COMMIT;