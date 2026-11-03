-- Gestão Galileu: stake % sobre banca-base mensal, fechamentos auditáveis e fluxo de caixa.
-- Migração aditiva: preserva sessões e entradas da gameplay.
BEGIN;
ALTER TABLE galileu_private.sessoes
    ADD COLUMN IF NOT EXISTS banca_base_mes numeric(16,2),
    ADD COLUMN IF NOT EXISTS mes_base char(7);

UPDATE galileu_private.sessoes
SET banca_base_mes=COALESCE(banca_base_mes,banca_inicial),
    mes_base=COALESCE(mes_base,to_char((corte + interval '1 day')::date,'YYYY-MM'))
WHERE banca_base_mes IS NULL OR mes_base IS NULL;

ALTER TABLE galileu_private.sessoes
    ALTER COLUMN banca_base_mes SET NOT NULL,
    ALTER COLUMN mes_base SET NOT NULL;

CREATE TABLE IF NOT EXISTS galileu_private.fechamentos_mensais (
    sessao_id uuid NOT NULL REFERENCES galileu_private.sessoes(id) ON DELETE CASCADE,
    mes char(7) NOT NULL,
    indice_rodada integer NOT NULL,
    banca_base_inicio numeric(16,2) NOT NULL,
    banca_fechamento numeric(16,2) NOT NULL,
    aporte numeric(16,2) NOT NULL DEFAULT 0 CHECK (aporte >= 0),
    saque numeric(16,2) NOT NULL DEFAULT 0 CHECK (saque >= 0),
    banca_base_seguinte numeric(16,2) NOT NULL,
    gestao_pct_antes numeric(6,3) NOT NULL,
    gestao_pct_depois numeric(6,3) NOT NULL,
    stake_fixa_antes numeric(16,2),
    stake_fixa_depois numeric(16,2),
    criado_em timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (sessao_id,mes),
    CONSTRAINT galileu_fechamento_mes_format CHECK (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$')
);
CREATE TABLE IF NOT EXISTS galileu_private.movimentacoes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sessao_id uuid NOT NULL REFERENCES galileu_private.sessoes(id) ON DELETE CASCADE,
    mes_referencia char(7) NOT NULL,
    tipo text NOT NULL CHECK (tipo IN ('aporte','saque','reajuste_stake','virada_mes')),
    valor numeric(16,2) NOT NULL DEFAULT 0 CHECK (valor >= 0),
    banca_antes numeric(16,2) NOT NULL,
    banca_depois numeric(16,2) NOT NULL,
    gestao_pct_antes numeric(6,3),
    gestao_pct_depois numeric(6,3),
    stake_fixa_antes numeric(16,2),
    stake_fixa_depois numeric(16,2),
    criado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS galileu_movimentos_sessao_mes
    ON galileu_private.movimentacoes(sessao_id,mes_referencia,id);
CREATE INDEX IF NOT EXISTS galileu_fechamentos_sessao_mes
    ON galileu_private.fechamentos_mensais(sessao_id,mes);
ALTER TABLE galileu_private.movimentacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE galileu_private.fechamentos_mensais ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON galileu_private.fechamentos_mensais,
    galileu_private.movimentacoes FROM PUBLIC,anon,authenticated;
REVOKE ALL ON SEQUENCE galileu_private.movimentacoes_id_seq FROM PUBLIC,anon,authenticated;
COMMIT;