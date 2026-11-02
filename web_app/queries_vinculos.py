"""Conciliação de identidades de clubes. Não altera os clubes existentes."""
from __future__ import annotations

import difflib
import re
import unicodedata
from db import fetch_all, get_conn

def key(value):
    text=unicodedata.normalize("NFKD",str(value or "")).casefold()
    text="".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",text)).strip()

def _suggest(name,clubs,limit=3):
    indexed={key(c["clube"]):c for c in clubs if key(c["clube"])}
    exact=indexed.get(key(name))
    if exact:return [{"id":exact["id"],"clube":exact["clube"],"similaridade":100}]
    ranked=sorted(((difflib.SequenceMatcher(None,key(name),key(c["clube"])).ratio(),c)
                   for c in clubs),key=lambda x:x[0],reverse=True)
    return [{"id":c["id"],"clube":c["clube"],"similaridade":round(score*100)}
            for score,c in ranked[:limit] if score>=.46]

def listar(fonte="fisicos"):
    clubs=fetch_all("SELECT id,clube,pais_id FROM public.clubes ORDER BY clube")
    refs=fetch_all("SELECT clube_id,fonte,id_externo FROM public.clubes_fontes")
    with_ref={r["clube_id"] for r in refs}
    # Na lista física, só entram clubes SEM vínculo SofaScore. Ter FotMob não exclui.
    # Todos já têm ao menos uma referência FotMob no cadastro atual.
    ids_sofa={r['clube_id'] for r in refs if r['fonte']=='sofascore'}
    ids_odds={r["clube_id"] for r in refs if r["fonte"]=="odds_api"}
    if fonte=="sem_referencia":
        targets=[c for c in clubs if c["id"] not in with_ref]
    elif fonte=="fisicos":
        targets=[c for c in clubs if c["id"] not in ids_sofa]
    else:
        targets=[c for c in clubs if c["id"] not in ids_odds]
    if fonte in ("fisicos","sem_referencia"):
        sources=fetch_all("""SELECT id_clube::text AS externo_id,
                            MIN(clube) AS nome, COUNT(*) AS registros,
                            MIN(pais) AS pais
                            FROM public.dados_fisicos
                            GROUP BY id_clube ORDER BY MIN(clube)""")
        reference_source="sofascore"
    elif fonte=="api":
        sources=fetch_all("""SELECT x.externo_id,MIN(x.nome) AS nome,
                                COUNT(*) AS registros, MIN(x.pais) AS pais
                             FROM (
                              SELECT ('odds:'||fonte||':'||lower(btrim(mandante))) AS externo_id,
                                     mandante AS nome,pais FROM public.odds WHERE mandante IS NOT NULL
                              UNION ALL
                              SELECT ('odds:'||fonte||':'||lower(btrim(visitante))) AS externo_id,
                                     visitante AS nome,pais FROM public.odds WHERE visitante IS NOT NULL
                             ) x
                             GROUP BY x.externo_id ORDER BY MIN(x.nome)""")
        reference_source="odds_api"
    else:raise ValueError("Fonte inválida.")
    mapped={r["id_externo"] for r in refs if r["fonte"]==reference_source}
    normalized={}
    for c in clubs:normalized.setdefault(key(c["clube"]),[]).append(c)
    pending=[]
    exact_count=0
    for src in sources:
        # Um mapeamento explícito ou um nome único idêntico não exige revisão.
        if src["externo_id"] in mapped:continue
        exact=normalized.get(key(src["nome"]),[])
        if len(exact)==1:
            exact_count+=1
            continue
        pending.append({**src,"sugestoes":_suggest(src["nome"],targets)})
    return {"fonte":fonte,"pendentes":pending,"clubes":targets,
            "total":len(pending),"ja_equivalentes_por_nome":exact_count,
            "aviso":"A correspondência por nome idêntico e único é automática na visualização. Apenas ligações confirmadas são gravadas em clubes_fontes."}

def vincular(payload):
    fonte=payload.get("fonte")
    if fonte not in ("fisicos","api","sem_referencia"):raise ValueError("Fonte inválida.")
    rows=payload.get("vinculos")
    if not isinstance(rows,list) or not 1<=len(rows)<=100:
        raise ValueError("Selecione de 1 a 100 vínculos.")
    source="sofascore" if fonte in ("fisicos","sem_referencia") else "odds_api"
    ids=[str(x.get("externo_id","")) for x in rows]
    if len(set(ids))!=len(ids):raise ValueError("ID externo repetido.")
    available={x["externo_id"]:x for x in listar(fonte)["pendentes"]}
    # Lista só clubes sem referência para físico; para API podem ter outras fontes.
    allowed={c["id"] for c in listar(fonte)["clubes"]}
    pending=[]
    for x in rows:
        eid=str(x.get("externo_id",""))
        club=x.get("clube_id")
        if eid not in available or type(club) is not int or club not in allowed:
            raise ValueError("Vínculo inválido, já existente ou não disponível. Atualize a página.")
        pending.append((club,source,eid,available[eid]["nome"]))
    with get_conn() as conn:
        with conn.cursor() as cur:
            for item in pending:
                cur.execute("""INSERT INTO public.clubes_fontes
                               (clube_id,fonte,id_externo,nome_externo)
                               VALUES (%s,%s,%s,%s)
                               ON CONFLICT (fonte,id_externo) DO NOTHING
                               RETURNING id""",item)
                if not cur.fetchone():
                    raise ValueError("Um clube já foi vinculado em outra sessão. Atualize.")
        conn.commit()
    return {"vinculados":len(pending)}
