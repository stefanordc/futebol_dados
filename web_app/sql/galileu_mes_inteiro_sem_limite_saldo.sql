-- Galileu: mês inteiro e simulação de todas as entradas sem limite de saldo.
-- Execute uma única vez no Postgres/Supabase existente antes de iniciar a versão nova.
-- Banca e bases mensais podem ser negativas após a liquidação virtual.
-- A banca inicial cadastrada continua exigindo valor positivo.
BEGIN;

ALTER TABLE galileu_private.sessoes
  DROP CONSTRAINT IF EXISTS sessoes_banca_atual_check;

ALTER TABLE galileu_private.fechamentos_mensais
  DROP CONSTRAINT IF EXISTS fechamentos_mensais_banca_base_inicio_check,
  DROP CONSTRAINT IF EXISTS fechamentos_mensais_banca_fechamento_check,
  DROP CONSTRAINT IF EXISTS fechamentos_mensais_banca_base_seguinte_check;

COMMIT;
