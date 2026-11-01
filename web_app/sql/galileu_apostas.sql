-- Galileu: ledger virtual pessoal, somente aplicativo local.
-- Não guarda apostas de dinheiro real ou credenciais de casas de aposta.
CREATE TABLE IF NOT EXISTS public.galileu_apostas (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    jogo_id integer NOT NULL REFERENCES public.jogos(id),
    campeonato_id integer NOT NULL REFERENCES public.campeonatos(id),
    casa_id integer NOT NULL REFERENCES public.clubes(id),
    fora_id integer NOT NULL REFERENCES public.clubes(id),
    metodo_nome text NOT NULL CHECK (length(trim(metodo_nome)) BETWEEN 1 AND 80),
    metodo_objetivo text NOT NULL,
    objetivo text NOT NULL,
    condicoes jsonb NOT NULL CHECK (jsonb_typeof(condicoes) = 'array'),
    amostra_mandante smallint NOT NULL CHECK (amostra_mandante BETWEEN 5 AND 20),
    amostra_visitante smallint NOT NULL CHECK (amostra_visitante BETWEEN 5 AND 20),
    confirmado_em timestamptz NOT NULL DEFAULT now(),
    UNIQUE (jogo_id),
    CHECK (casa_id <> fora_id)
);
CREATE INDEX IF NOT EXISTS galileu_apostas_campeonato_idx ON public.galileu_apostas(campeonato_id);
CREATE INDEX IF NOT EXISTS galileu_apostas_confirmado_em_idx ON public.galileu_apostas(confirmado_em DESC);
ALTER TABLE public.galileu_apostas ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.galileu_apostas FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE public.galileu_apostas_id_seq FROM PUBLIC, anon, authenticated;
-- A aplicação não oferece edição, cancelamento ou exclusão e nem esses
-- comandos são aceitos pelo banco para registros confirmados.
CREATE OR REPLACE FUNCTION public.galileu_bloquear_mutacao()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = public
AS $$
BEGIN
    RAISE EXCEPTION 'Registros confirmados do Galileu são imutáveis';
END;
$$;
REVOKE ALL ON FUNCTION public.galileu_bloquear_mutacao() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS trg_galileu_imutavel ON public.galileu_apostas;
CREATE TRIGGER trg_galileu_imutavel BEFORE UPDATE OR DELETE
ON public.galileu_apostas FOR EACH ROW EXECUTE FUNCTION public.galileu_bloquear_mutacao();
