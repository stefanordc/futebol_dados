-- Migração opcional para PostgreSQL/Supabase.
-- Leia e execute em uma janela de manutenção. NÃO é aplicada automaticamente.
-- O frontend funciona sem esta migração, mas os índices podem acelerar as consultas.

CREATE INDEX IF NOT EXISTS idx_df_jogos_camp_temp ON jogos(campeonato_id, temporada, data);
CREATE INDEX IF NOT EXISTS idx_df_jogos_arbitro_temp ON jogos(arbitro_id, temporada, data)
  WHERE arbitro_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_df_jogos_casa_temp ON jogos(casa_id, temporada);
CREATE INDEX IF NOT EXISTS idx_df_jogos_fora_temp ON jogos(fora_id, temporada);
CREATE INDEX IF NOT EXISTS idx_df_estatisticas_jogo_completo ON estatisticas(jogo_id, mando)
  WHERE periodo = 'Completo';
CREATE INDEX IF NOT EXISTS idx_df_finalizacoes_jogo ON finalizacoes(jogo_id);

-- VIEW de apoio à classificação, por clube / competição / temporada.
-- Uma view regular reflete atualizações imediatamente. Ela NÃO é cache:
-- os índices e consultas agregadas são o principal ganho de performance.
CREATE OR REPLACE VIEW vw_df_classificacao AS
WITH lados AS (
    SELECT campeonato_id, temporada, casa_id AS clube_id,
           gols_casa AS gf, gols_fora AS gc,
           CASE WHEN gols_casa>gols_fora THEN 1 ELSE 0 END AS v,
           CASE WHEN gols_casa=gols_fora THEN 1 ELSE 0 END AS e,
           CASE WHEN gols_casa<gols_fora THEN 1 ELSE 0 END AS d
    FROM jogos
    WHERE gols_casa IS NOT NULL AND gols_fora IS NOT NULL
    UNION ALL
    SELECT campeonato_id, temporada, fora_id AS clube_id,
           gols_fora, gols_casa,
           CASE WHEN gols_fora>gols_casa THEN 1 ELSE 0 END,
           CASE WHEN gols_fora=gols_casa THEN 1 ELSE 0 END,
           CASE WHEN gols_fora<gols_casa THEN 1 ELSE 0 END
    FROM jogos
    WHERE gols_casa IS NOT NULL AND gols_fora IS NOT NULL
)
SELECT campeonato_id, temporada, clube_id,
       COUNT(*) AS jogos,
       SUM(v) AS vitorias, SUM(e) AS empates, SUM(d) AS derrotas,
       SUM(gf) AS gols_marcados, SUM(gc) AS gols_sofridos,
       SUM(gf-gc) AS saldo_gols,
       SUM(3*v+e) AS pontos,
       ROUND(100.0*SUM(3*v+e)/NULLIF(3*COUNT(*),0),2) AS aproveitamento
FROM lados
GROUP BY campeonato_id, temporada, clube_id;
