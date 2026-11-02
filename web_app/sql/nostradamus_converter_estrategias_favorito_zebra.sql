-- Converte APENAS estratégias salvas: mandante -> favorito, visitante -> zebra.
-- Backup privado para auditoria e eventual restauração.
BEGIN;
CREATE SCHEMA IF NOT EXISTS nostradamus_private;
REVOKE ALL ON SCHEMA nostradamus_private FROM PUBLIC,anon,authenticated,service_role;
CREATE TABLE IF NOT EXISTS nostradamus_private.estrategias_antes_favorito (
    estrategia_id bigint PRIMARY KEY,
    nome text NOT NULL,
    objetivo text NOT NULL,
    condicoes jsonb NOT NULL,
    versao integer NOT NULL,
    backup_em timestamptz NOT NULL DEFAULT NOW()
);
REVOKE ALL ON nostradamus_private.estrategias_antes_favorito
 FROM PUBLIC,anon,authenticated,service_role;
INSERT INTO nostradamus_private.estrategias_antes_favorito
    (estrategia_id,nome,objetivo,condicoes,versao)
SELECT id,nome,objetivo,condicoes,versao
FROM public.nostradamus_estrategias
WHERE objetivo IN ('back_mandante','lay_mandante','back_visitante','lay_visitante')
   OR EXISTS (SELECT 1 FROM jsonb_array_elements(condicoes) x
         WHERE x->>'lado' IN ('mandante','visitante')
            OR x->>'referencia' IN ('mandante','visitante'))
ON CONFLICT (estrategia_id) DO NOTHING;

WITH convertidas AS (
 SELECT e.id,
    jsonb_agg(
      (CASE WHEN c.value->>'lado' IN ('mandante','visitante')
            THEN jsonb_set(c.value,'{lado}',
               to_jsonb(CASE c.value->>'lado'
                           WHEN 'mandante' THEN 'favorito'
                           ELSE 'zebra' END),true)
            ELSE c.value END)
       || CASE WHEN c.value->>'referencia' IN ('mandante','visitante')
               THEN jsonb_build_object('referencia',
                     CASE c.value->>'referencia' WHEN 'mandante'
                          THEN 'favorito' ELSE 'zebra' END)
               ELSE '{}'::jsonb END
      ORDER BY c.ord
    ) AS novas_condicoes
 FROM public.nostradamus_estrategias e
 CROSS JOIN LATERAL jsonb_array_elements(e.condicoes) WITH ORDINALITY c(value,ord)
 GROUP BY e.id
)
UPDATE public.nostradamus_estrategias e
SET condicoes=c.novas_condicoes,
    objetivo=CASE e.objetivo
      WHEN 'back_mandante' THEN 'back_favorito'
      WHEN 'lay_mandante' THEN 'lay_favorito'
      WHEN 'back_visitante' THEN 'back_zebra'
      WHEN 'lay_visitante' THEN 'lay_zebra'
      ELSE e.objetivo END,
    versao=e.versao+1,
    atualizado_em=now()
FROM convertidas c
WHERE e.id=c.id
 AND (e.objetivo IN ('back_mandante','lay_mandante','back_visitante','lay_visitante')
  OR EXISTS (SELECT 1 FROM jsonb_array_elements(e.condicoes) x
             WHERE x->>'lado' IN ('mandante','visitante')
                OR x->>'referencia' IN ('mandante','visitante')));
COMMIT;