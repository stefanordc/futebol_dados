"""Persistência das estratégias Nostradamus no Postgres/Supabase.

Este servidor é destinado a localhost, com uma única banca/usuário. NÃO
publique os endpoints mutáveis sem autenticação e isolamento por usuário.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from psycopg2 import errors
from psycopg2.extras import Json
from db import fetch_all, get_conn
import queries_nostradamus as ns

COLS="""id,nome,objetivo,corte,jogos,campeonato_id,condicoes,
        odd_hipotetica,comissao_pct,versao,criado_em,atualizado_em"""
BASE=f"SELECT {COLS} FROM public.nostradamus_estrategias"

def listar():
    return fetch_all(BASE+" ORDER BY criado_em DESC, id DESC")

def _validate(body):
    if not isinstance(body,dict):raise ValueError("Dados inválidos.")
    nome=body.get("nome")
    if not isinstance(nome,str) or not 1<=len(nome.strip())<=80:
        raise ValueError("Informe o nome da estratégia (1 a 80 caracteres).")
    objetivo=body.get("objetivo")
    if objetivo not in ns.MERCADOS:raise ValueError("Objetivo inválido.")
    corte=body.get("corte")
    try:dt=date.fromisoformat(corte)
    except (ValueError,TypeError):raise ValueError("Data de corte inválida.") from None
    if dt>date.today():raise ValueError("Corte não pode estar no futuro.")
    jogos=str(body.get("jogos","20"))
    if jogos not in {"5","10","20","temporada"}:
        raise ValueError("Janela de jogos inválida.")
    liga=body.get("campeonato_id")
    if liga in ("",None):liga=None
    elif type(liga) is not int or liga<1:raise ValueError("Campeonato inválido.")
    conditions=ns._valid_conditions(body.get("condicoes"))
    odd=body.get("odd_hipotetica")
    if odd in ("",None):odd=None
    else:
        if isinstance(odd,bool):raise ValueError("Odd inválida.")
        try:odd=Decimal(str(odd))
        except Exception:raise ValueError("Odd inválida.") from None
        if not odd.is_finite() or not Decimal("1.01")<=odd<=Decimal("1000"):
            raise ValueError("Odd deve estar entre 1,01 e 1000.")
    commission=body.get("comissao_pct",2)
    if isinstance(commission,bool):raise ValueError("Comissão inválida.")
    try:commission=Decimal(str(commission))
    except Exception:raise ValueError("Comissão inválida.") from None
    if not commission.is_finite() or not Decimal("0")<=commission<=Decimal("30"):
        raise ValueError("Comissão inválida.")
    return dict(nome=nome.strip(),objetivo=objetivo,corte=dt,jogos=jogos,
                campeonato_id=liga,condicoes=conditions,
                odd_hipotetica=odd,comissao_pct=commission)

def _params(v):
    return (v["nome"],v["objetivo"],v["corte"],v["jogos"],v["campeonato_id"],
            Json(v["condicoes"]),v["odd_hipotetica"],v["comissao_pct"])

INSERT="""INSERT INTO public.nostradamus_estrategias
          (nome,objetivo,corte,jogos,campeonato_id,condicoes,odd_hipotetica,comissao_pct)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING """+COLS

def criar(payload):
    v=_validate(payload)
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(INSERT,_params(v))
                return dict(cur.fetchone())
    except errors.UniqueViolation:
        raise ValueError("Já existe uma estratégia com esse nome.") from None

def editar(strategy_id,payload):
    if type(strategy_id) is not int or strategy_id<1:raise ValueError("ID inválido.")
    v=_validate(payload)
    ver=payload.get("versao")
    if type(ver) is not int or ver<1:
        raise ValueError("Versão da estratégia inválida; recarregue antes de editar.")
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE public.nostradamus_estrategias
                        SET nome=%s,objetivo=%s,corte=%s,jogos=%s,
                            campeonato_id=%s,condicoes=%s,odd_hipotetica=%s,
                            comissao_pct=%s,versao=versao+1,atualizado_em=now()
                        WHERE id=%s AND versao=%s
                        RETURNING """+COLS,(*_params(v),strategy_id,ver))
                item=cur.fetchone()
                if not item:
                    raise ValueError("Estratégia alterada em outra sessão ou não encontrada. Recarregue.")
                return dict(item)
    except errors.UniqueViolation:
        raise ValueError("Já existe outra estratégia com esse nome.") from None

def importar(payload):
    """Migra estratégia antiga sem perder método homônimo com regras diferentes."""
    values=payload.get("estrategias") if isinstance(payload,dict) else None
    if not isinstance(values,list) or len(values)>50:
        raise ValueError("Importe no máximo 50 estratégias.")
    validated=[_validate(item) for item in values]
    inserted=0
    existing_count=0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for original in validated:
                original_name=original["nome"]
                for attempt in range(101):
                    suffix=f" (importada {attempt})" if attempt else ""
                    current={**original,"nome":original_name[:80-len(suffix)]+suffix}
                    cur.execute("""SELECT objetivo,corte,jogos,campeonato_id,condicoes,
                                          odd_hipotetica,comissao_pct
                                   FROM public.nostradamus_estrategias
                                   WHERE lower(btrim(nome))=lower(%s)""",(current["nome"],))
                    old=cur.fetchone()
                    if old:
                        if (old["objetivo"]==current["objetivo"]
                            and old["corte"]==current["corte"]
                            and old["jogos"]==current["jogos"]
                            and old["campeonato_id"]==current["campeonato_id"]
                            and old["condicoes"]==current["condicoes"]
                            and old["odd_hipotetica"]==current["odd_hipotetica"]
                            and old["comissao_pct"]==current["comissao_pct"]):
                            existing_count+=1
                            break
                        continue
                    cur.execute(INSERT.replace(" RETURNING "+COLS,
                        " ON CONFLICT DO NOTHING RETURNING id"),_params(current))
                    if cur.fetchone():
                        inserted+=1
                        break
                else:
                    raise ValueError("Não foi possível importar duplicatas; cópia local preservada.")
    return {"importadas":inserted,"existentes":existing_count}
