-- Filtro de clubes no backtesting e nas estratégias salvas.
-- Sem seleção (array vazio) significa todos os clubes da(s) liga(s) escolhida(s).
-- Compatível com estratégias antigas, que continuam sem restrição de clubes.
ALTER TABLE public.nostradamus_estrategias
    ADD COLUMN IF NOT EXISTS clube_ids integer[] NOT NULL DEFAULT '{}'::integer[];

COMMENT ON COLUMN public.nostradamus_estrategias.clube_ids IS
    'IDs internos de clubes que podem participar do backtest; vazio = qualquer clube.';
