-- Migração UMA VEZ da estrutura antiga (odds.dados JSONB) para colunas físicas.
-- Supabase "Dados Futebol": executada em 02/11/2026, 277 registros preservados.
-- NÃO execute após a migração: a coluna dados já foi removida.
-- Uma cópia integral permanece em odds_private.odds_json_backup.
BEGIN;
CREATE SCHEMA IF NOT EXISTS odds_private;
REVOKE ALL ON SCHEMA odds_private FROM PUBLIC,anon,authenticated,service_role;
CREATE TABLE IF NOT EXISTS odds_private.odds_json_backup (
 odds_id bigint PRIMARY KEY, dados jsonb NOT NULL, backup_em timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON odds_private.odds_json_backup FROM PUBLIC,anon,authenticated,service_role;
INSERT INTO odds_private.odds_json_backup(odds_id,dados)
 SELECT id,dados FROM public.odds ON CONFLICT(odds_id) DO NOTHING;

-- Guardar os nomes antes dos ALTERs: PostgreSQL não permite ALTER na tabela
-- enquanto ela está sendo varrida num FOR diretamente.
CREATE TEMP TABLE odds_migrar_campos ON COMMIT DROP AS
 SELECT DISTINCT k::text AS chave FROM public.odds o,
 LATERAL jsonb_object_keys(o.dados) k
 WHERE k NOT IN ('_bookmakers_das_odds','_metodo_lay_simulado')
   AND k !~* '^(AH_|EH_|Bookie_AH_|Bookie_EH_)';
CREATE TEMP TABLE odds_migrar_bookies ON COMMIT DROP AS
 SELECT DISTINCT e.key::text AS chave FROM public.odds o,
 LATERAL jsonb_each(CASE WHEN jsonb_typeof(o.dados->'_bookmakers_das_odds')='object'
 THEN o.dados->'_bookmakers_das_odds' ELSE '{}'::jsonb END) e;

ALTER TABLE public.odds
 ADD COLUMN IF NOT EXISTS lay_origem text,
 ADD COLUMN IF NOT EXISTS lay_precificacao_real boolean NOT NULL DEFAULT false,
 ADD COLUMN IF NOT EXISTS lay_liquidez_verificada boolean NOT NULL DEFAULT false,
 ADD COLUMN IF NOT EXISTS lay_comissao_pct numeric(5,2);

DO $migrar$
DECLARE item record; coluna text; tipo text; expressao text;
BEGIN
 FOR item IN SELECT chave FROM odds_migrar_campos LOOP
  coluna:=lower(replace(item.chave,'Lay_Simulado_','Lay_'));
  IF length(coluna)>63 OR coluna !~ '^[a-z][a-z0-9_]*$' THEN
   RAISE EXCEPTION 'Nome inválido: %',item.chave;
  END IF;
  IF coluna ~ '^(odd_|over_|under_|btts_|dc_|cs_|lay_)' THEN
   tipo:='numeric(12,4)';
   expressao:=format(
    'CASE WHEN btrim(dados->>%L) ~ %L THEN (btrim(dados->>%L))::numeric(12,4) ELSE NULL END',
    item.chave,'^[+-]?[0-9]+([.][0-9]+)?$',item.chave);
  ELSIF coluna IN ('home_score','away_score') THEN
   tipo:='integer';
   expressao:=format(
    'CASE WHEN btrim(dados->>%L) ~ %L THEN (btrim(dados->>%L))::integer ELSE NULL END',
    item.chave,'^[+-]?[0-9]+$',item.chave);
  ELSIF coluna='date' THEN
   tipo:='date';
   expressao:=format(
    'CASE WHEN dados->>%L ~ %L THEN to_date(dados->>%L,%L) ELSE NULL END',
    item.chave,'^[0-9]{2}/[0-9]{2}/[0-9]{4}$',item.chave,'DD/MM/YYYY');
  ELSE
   tipo:='text';
   expressao:=format('nullif(dados->>%L,%L)',item.chave,'');
  END IF;
  EXECUTE format('ALTER TABLE public.odds ADD COLUMN IF NOT EXISTS %I %s',coluna,tipo);
  EXECUTE format('UPDATE public.odds SET %I = %s WHERE dados ? %L',
                 coluna,expressao,item.chave);
 END LOOP;
 FOR item IN SELECT chave FROM odds_migrar_bookies LOOP
  coluna:='bookie_'||lower(item.chave);
  IF length(coluna)>63 OR coluna !~ '^[a-z][a-z0-9_]*$' THEN CONTINUE; END IF;
  EXECUTE format('ALTER TABLE public.odds ADD COLUMN IF NOT EXISTS %I text',coluna);
  EXECUTE format('UPDATE public.odds SET %I = dados->%L->%L->>%L WHERE dados->%L ? %L',
    coluna,'_bookmakers_das_odds',item.chave,'bookmaker','_bookmakers_das_odds',item.chave);
 END LOOP;
END
$migrar$;

UPDATE public.odds SET
 lay_origem=CASE WHEN dados ? '_metodo_lay_simulado' THEN 'estimado_um_tick' ELSE NULL END,
 lay_precificacao_real=false,lay_liquidez_verificada=false,
 lay_comissao_pct=CASE WHEN (dados->'_metodo_lay_simulado'->>'comissao_pct') ~ '^[0-9]+([.][0-9]+)?$'
 THEN (dados->'_metodo_lay_simulado'->>'comissao_pct')::numeric(5,2) ELSE NULL END;

CREATE UNIQUE INDEX IF NOT EXISTS odds_fonte_temporada_id_unique
 ON public.odds(fonte,temporada,partida_externa_id)
 WHERE nullif(btrim(partida_externa_id),'') IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS odds_sem_id_jogo_unique
 ON public.odds(fonte,temporada,campeonato,data_jogo,mandante,visitante)
 NULLS NOT DISTINCT WHERE nullif(btrim(partida_externa_id),'') IS NULL;
ALTER TABLE public.odds DROP COLUMN IF EXISTS dados;
ALTER TABLE public.odds ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.odds FROM PUBLIC,anon,authenticated,service_role;
COMMIT;
