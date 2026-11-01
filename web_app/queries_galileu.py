"""Galileu: sinais pré-jogo usando métodos salvos do Nostradamus.

Uma seleção só é oferecida quando todas as condições se verificam com
jogos COMPLETOS de dias anteriores. O confronto alvo nunca participa
de seus próprios indicadores. As entradas confirmadas são registradas
uma vez por partida, sem opção de editar ou excluir.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from psycopg2.extras import Json
from psycopg2 import errors

from db import fetch_all, get_conn
import queries_nostradamus as ns

BRAZIL=ZoneInfo("America/Sao_Paulo")
INITIAL_BANK=100
MAX_METHODS=50
MAX_SELECTION=80

SCHEDULE="""
SELECT j.id,j.data,j.campeonato_id,c.nome AS campeonato,j.temporada,j.rodada,
       j.casa_id,j.fora_id,h.clube AS mandante,v.clube AS visitante
FROM jogos j
JOIN campeonatos c ON c.id=j.campeonato_id
JOIN clubes h ON h.id=j.casa_id
JOIN clubes v ON v.id=j.fora_id
WHERE j.data >= %s
  AND j.gols_casa IS NULL AND j.gols_fora IS NULL
ORDER BY j.data,j.campeonato_id,j.id
LIMIT 1400
"""

REPORT="""
SELECT e.id,e.jogo_id,e.metodo_nome,e.objetivo,e.confirmado_em,
       e.campeonato_id,c.nome AS campeonato,
       e.casa_id,e.fora_id,h.clube AS mandante,v.clube AS visitante,
       j.data, j.gols_casa,j.gols_fora
FROM galileu_apostas e
JOIN jogos j ON j.id=e.jogo_id
JOIN campeonatos c ON c.id=e.campeonato_id
JOIN clubes h ON h.id=e.casa_id
JOIN clubes v ON v.id=e.fora_id
ORDER BY e.confirmado_em DESC,e.id DESC
"""

def _today():
    return datetime.now(BRAZIL).date()

def _date(raw):
    try:
        return date.fromisoformat(str(raw))
    except (ValueError,TypeError):
        raise ValueError("Informe uma data válida (AAAA-MM-DD).") from None

def _methods(raw):
    if not isinstance(raw,list) or len(raw)>MAX_METHODS:
        raise ValueError("Envie até 50 métodos salvos.")
    results=[]
    for m in raw:
        if not isinstance(m,dict):raise ValueError("Estratégia inválida.")
        name=m.get("nome")
        if not isinstance(name,str) or not name.strip() or len(name.strip())>80:
            raise ValueError("Todo método precisa de um nome salvo.")
        objective=m.get("objetivo")
        if objective not in ns.MERCADOS:
            raise ValueError("Objetivo do método inválido.")
        league=m.get("campeonato_id")
        if league in ("",None):league=None
        elif type(league) is not int or league<=0:
            raise ValueError("Liga do método inválida.")
        normalized=ns._valid_conditions(m.get("condicoes"))
        results.append({
            "nome":name.strip(),"objetivo":objective,
            "campeonato_id":league,"condicoes":normalized
        })
    return results

def _schedule(cutoff,rows=None):
    if rows is None:rows=fetch_all(SCHEDULE,(cutoff,))
    filtered=[]
    for r in rows:
        row=dict(r)
        d=_date(row["data"])
        if d<cutoff or row.get("gols_casa") is not None or row.get("gols_fora") is not None:
            continue
        row["data"]=d
        filtered.append(row)
    filtered.sort(key=lambda x:(x["data"],int(x["id"])))
    # Próxima rodada disponível por competição/temporada. Quando a data
    # de referência cai entre jogos da mesma rodada, usa os restantes.
    first_round={}
    selected=[]
    for g in filtered:
        key=(g["campeonato_id"],g["temporada"])
        rodada=(g.get("rodada") or "").strip()
        if key not in first_round:
            first_round[key]=rodada or f"data:{g['data']}"
        if (rodada or f"data:{g['data']}")==first_round[key]:
            selected.append(g)
    return selected[:140]

def _historical(target_date,rows=None):
    if rows is None:
        # RAW exige data <= param e data < CURRENT_DATE. Nunca usa o
        # banco para ler partidas posteriores à data atual.
        rows=fetch_all(ns.RAW.format(competition=""),(min(target_date-timedelta(days=1),_today()-timedelta(days=1)),))
    records=defaultdict(list)
    horizon=min(target_date,_today())
    for row in rows:
        d=_date(row["data"])
        if d>=horizon or row.get("gols_casa") is None or row.get("gols_fora") is None:
            continue
        for side,club,gf,ga in (
            ("home",row["casa_id"],row["gols_casa"],row["gols_fora"]),
            ("away",row["fora_id"],row["gols_fora"],row["gols_casa"]),
        ):
            item={"gf":int(gf),"ga":int(ga)}
            for field in ("xg","xgot","chutes","chutes_certos","passes_certos","posse",
                          "grandes_chances","escanteios","dribles_certos","faltas","duelos_aereos"):
                item[field]=row.get(side+"_"+field)
            key=(row["campeonato_id"],row["temporada"],club)
            records[key].append((d,int(row["id"]),item))
    for items in records.values():items.sort(key=lambda p:(p[0],p[1]))
    return records

def _stats_for(history,key,asof,window=20):
    rows=[item for dt,_,item in history.get(key,()) if dt<asof]
    return ns._stats(rows,window),min(window,len(rows))

def _methods_as_public(methods):
    return [{"nome":m["nome"],"objetivo":m["objetivo"],
             "objetivo_nome":ns.MERCADOS[m["objetivo"]],
             "condicoes":m["condicoes"]} for m in methods]

def sinais(payload,fixtures=None,history=None,registered_ids=None):
    if not isinstance(payload,dict):raise ValueError("Dados inválidos.")
    cutoff=_date(payload.get("data"))
    today=_today()
    # DB registra datas sem horário de início. Hoje é deliberadamente excluído:
    # um jogo de hoje pode já ter começado.
    if cutoff<=today:
        raise ValueError("Escolha uma data a partir de amanhã; não há horário de início confiável.")
    methods=_methods(payload.get("estrategias"))
    if not methods:
        return {"data":cutoff.isoformat(),"jogos":[],"total":0,
                "metodos":0,"objetivos":ns.MERCADOS,
                "mensagem":"Salve pelo menos uma estratégia no Nostradamus neste navegador."}
    candidates=_schedule(cutoff,fixtures)
    if not candidates:
        return {"data":cutoff.isoformat(),"jogos":[],"total":0,
                "metodos":len(methods),"objetivos":ns.MERCADOS,
                "mensagem":"Não existem partidas futuras nas próximas rodadas cadastradas."}
    historical=_historical(cutoff,history)
    if registered_ids is None:
        registered_ids={x["jogo_id"] for x in fetch_all(
            "SELECT jogo_id FROM galileu_apostas WHERE jogo_id=ANY(%s)",
            ([g["id"] for g in candidates],)
        )}
    results=[]
    cache={}
    for g in candidates:
        if g["id"] in registered_ids:continue
        ids=((g["campeonato_id"],g["temporada"],g["casa_id"]),
             (g["campeonato_id"],g["temporada"],g["fora_id"]))
        metrics=[]
        coverage=[]
        for key in ids:
            # Não contam jogos de data >= confronto, nem jogos do futuro
            cache_key=(key,g["data"])
            if cache_key not in cache:
                cache[cache_key]=_stats_for(historical,key,g["data"])
            stat,count=cache[cache_key]
            metrics.append(stat);coverage.append(count)
        home,away=metrics
        if home is None or away is None:continue
        matched=[]
        for mi,m in enumerate(methods):
            if m["campeonato_id"] is not None and m["campeonato_id"]!=g["campeonato_id"]:
                continue
            found=[]
            for cond in m["condicoes"]:
                value=ns._evaluate_condition(cond,home,away)
                if value is None:break
                found.append(value)
            else:
                matched.append({
                    "metodo_idx":mi,"nome":m["nome"],"objetivo":m["objetivo"],
                    "objetivo_nome":ns.MERCADOS[m["objetivo"]],
                    "regras":found,
                })
        if matched:
            # Resposta não inclui placar ou estatísticas posteriores.
            results.append({
                "jogo_id":g["id"],"data":g["data"].isoformat(),
                "campeonato":g["campeonato"],"campeonato_id":g["campeonato_id"],
                "temporada":g["temporada"],"rodada":g.get("rodada"),
                "mandante":g["mandante"],"visitante":g["visitante"],
                "casa_id":g["casa_id"],"fora_id":g["fora_id"],
                "metodos":matched,
                "amostra":{"mandante":coverage[0],"visitante":coverage[1]},
                "estatisticas":{"mandante":home,"visitante":away},
            })
    return {"data":cutoff.isoformat(),"jogos":results,"total":len(results),
            "metodos":len(methods),"objetivos":ns.MERCADOS,
            "mensagem":"Somente próximas rodadas cadastradas; mínimo de 5 e máximo de 20 jogos concluídos anteriores à data de cada confronto. Sem resultados de jogos futuros."}

def confirmar(payload):
    if not isinstance(payload,dict):raise ValueError("Dados inválidos.")
    selected=payload.get("apostas")
    if not isinstance(selected,list) or not 1<=len(selected)<=MAX_SELECTION:
        raise ValueError("Marque de 1 a 80 partidas.")
    ids=[]
    for x in selected:
        if not isinstance(x,dict) or type(x.get("jogo_id")) is not int:
            raise ValueError("Identificador de partida inválido.")
        if type(x.get("metodo_idx")) is not int:
            raise ValueError("Escolha um método para cada partida.")
        if x.get("objetivo") not in ns.MERCADOS:
            raise ValueError("Entrada inválida.")
        ids.append(x["jogo_id"])
    if len(set(ids))!=len(ids):
        raise ValueError("Há partidas duplicadas na seleção.")
    # Recalcula os sinais na hora do commit, não confia em lista enviada
    # pelo navegador. A validação só considera métodos válidos e histórico
    # estritamente anterior ao confronto.
    signals=sinais(payload)
    by_id={r["jogo_id"]:r for r in signals["jogos"]}
    methods=_methods(payload.get("estrategias"))
    confirmed=[]
    for item in selected:
        game=by_id.get(item["jogo_id"])
        if game is None:raise ValueError("Uma partida não está mais elegível para o método.")
        idx=item["metodo_idx"]
        match=next((m for m in game["metodos"] if m["metodo_idx"]==idx),None)
        if match is None:raise ValueError("O método não corresponde ao jogo selecionado.")
        confirmed.append((game,methods[idx],item["objetivo"]))
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                for game,method,objective in confirmed:
                    # Travamento de jogo para evitar gravação se o placar chegou.
                    cur.execute("SELECT data,gols_casa,gols_fora FROM jogos WHERE id=%s FOR UPDATE",
                                (game["jogo_id"],))
                    live=cur.fetchone()
                    if (live is None or live["data"]<=_today() or
                        live["gols_casa"] is not None or live["gols_fora"] is not None):
                        raise ValueError("A partida já começou ou deixou de ser elegível.")
                    cur.execute("""
                        INSERT INTO galileu_apostas
                          (jogo_id,campeonato_id,casa_id,fora_id,metodo_nome,
                           metodo_objetivo,objetivo,condicoes,amostra_mandante,amostra_visitante)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING id
                    """,(game["jogo_id"],game["campeonato_id"],game["casa_id"],game["fora_id"],
                         method["nome"],method["objetivo"],objective,
                         Json(method["condicoes"]),game["amostra"]["mandante"],
                         game["amostra"]["visitante"]))
                    cur.fetchone()
                    # Somente confirma; nenhum identificador ou placar de jogo é alterado.
            conn.commit()
    except errors.UniqueViolation:
        raise ValueError("Pelo menos uma partida já foi confirmada. Nenhuma nova entrada foi registrada.") from None
    return {"registradas":len(selected),"mensagem":"Entradas registradas no banco. Não existe opção de desfazer, editar ou excluir na aplicação."}

def relatorio(rows=None):
    if rows is None:rows=fetch_all(REPORT)
    today=_today()
    all_bets=[]
    for r in rows:
        d=_date(r["data"])
        settled=(d<today and r.get("gols_casa") is not None and r.get("gols_fora") is not None)
        hit=ns._settle(r["objetivo"],int(r["gols_casa"]),int(r["gols_fora"])) if settled else None
        all_bets.append({
            "id":r["id"],"jogo_id":r["jogo_id"],"data":d.isoformat(),
            "campeonato":r["campeonato"],"mandante":r["mandante"],"visitante":r["visitante"],
            "metodo":r["metodo_nome"],"objetivo":r["objetivo"],
            "objetivo_nome":ns.MERCADOS.get(r["objetivo"],r["objetivo"]),
            "status":"green" if hit is True else "red" if hit is False else "pendente",
            "confirmado_em":r["confirmado_em"].isoformat() if isinstance(r["confirmado_em"],datetime) else str(r["confirmado_em"]),
        })
    def counter(items):
        greens=sum(b["status"]=="green" for b in items)
        reds=sum(b["status"]=="red" for b in items)
        resolved=greens+reds
        return {"entradas":len(items),"greens":greens,"reds":reds,"pendentes":len(items)-resolved,
                "win_rate":round(100*greens/resolved,2) if resolved else None,
                "unidades":greens-reds}
    by_league=defaultdict(list)
    by_club=defaultdict(list)
    for b in all_bets:
        by_league[b["campeonato"]].append(b)
        for club in {b["mandante"],b["visitante"]}:
            by_club[club].append(b)
    summary=counter(all_bets)
    return {"banca_inicial":INITIAL_BANK,"banca_atual":INITIAL_BANK+summary["unidades"],
            "resumo":summary,
            "por_liga":[{"nome":name,**counter(items)} for name,items in sorted(by_league.items())],
            "por_clube":[{"nome":name,**counter(items)} for name,items in sorted(by_club.items())],
            "entradas":all_bets,
            "nota":"Banca virtual inicial de 100u; cada green soma +1u e cada red subtrai −1u; pendentes não alteram a banca. Win rate considera somente entradas resolvidas. Cada partida aparece para os dois clubes na tabela por clube. Os registros confirmados não podem ser editados ou excluídos pela aplicação."}
