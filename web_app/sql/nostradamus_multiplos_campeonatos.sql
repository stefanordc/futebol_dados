-- Suporte a múltiplas ligas por estratégia sem perder o filtro legado.
-- NULL não é usado: ARRAY[]::integer[] representa todos os campeonatos.
BEGIN;
ALTER TABLE public.nostradamus_estrategias
  ADD COLUMN IF NOT EXISTS campeonato_ids integer[] NOT NULL DEFAULT '{}'::integer[];

UPDATE public.nostradamus_estrategias
SET campeonato_ids=ARRAY[campeonato_id]
WHERE campeonato_id IS NOT NULL
  AND cardinality(campeonato_ids)=0;

ALTER TABLE public.nostradamus_estrategias
  DROP CONSTRAINT IF EXISTS nostradamus_estrategias_campeonato_ids_validos;
ALTER TABLE public.nostradamus_estrategias
  ADD CONSTRAINT nostradamus_estrategias_campeonato_ids_validos
  CHECK (cardinality(campeonato_ids)<=30 AND 0<ALL(campeonato_ids));
COMMIT;
