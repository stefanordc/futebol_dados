"""Galileu Gameplay: simulador por rodadas, banca em BRL e progresso privado.

O usuário não recebe resultados nem placares até finalizar a rodada.
A identidade da sessão é um token aleatório em cookie HttpOnly; somente o hash
fica no Supabase (schema privado). Sem autenticação, sessões são por navegador.
Odds históricas importadas não comprovam que estavam disponíveis pré-jogo.
"""
from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
from time import monotonic
from zoneinfo import ZoneInfo

from psycopg2 import errors
from db import fetch_all, get_conn
import queries_nostradamus as ns
import queries_estrategias

COOKIE="galileu_gameplay"
TZ=ZoneInfo("America/Sao_Paulo")
COMMISSION=Decimal("0.045")
MAX_BANK=Decimal("1000000000")
CENTS=Decimal("0.01")
CACHE_SECONDS=90
_cache_at=0.0
_cache_day=None
_cache_rows=None


def today():
    return datetime.now(TZ).date()


def _date(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError("Informe uma data de corte válida.") from None


def _money(value, label, maximum=MAX_BANK, allow_zero=False):
    if isinstance(value, bool) or value is None:
        raise ValueError(label+" inválido.")
    try:
        number=Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(label+" inválido.") from None
    if not number.is_finite() or (number<0 if allow_zero else number<=0) or number>maximum:
        raise ValueError(label+" fora do intervalo permitido.")
    if number!=number.quantize(CENTS):
        raise ValueError(label+" deve ter no máximo duas casas decimais.")
    return number.quantize(CENTS)


def _pct(value):
    amount=_money(value,"Gestão (%)",Decimal("100"))
    return amount


def _brl(value):
    return float(Decimal(value).quantize(CENTS,rounding=ROUND_HALF_UP))


def _rounded(value):
    return Decimal(value).quantize(CENTS,rounding=ROUND_HALF_UP)


def _hash(token):
    return sha256(token.encode("utf-8")).hexdigest() if token and len(token)<=200 else None


def _catalog():
    """Cache curto do catálogo; nenhum resultado é devolvido diretamente."""
    global _cache_at,_cache_day,_cache_rows
    day=today()
    if _cache_rows is not None and _cache_day==day and monotonic()-_cache_at<CACHE_SECONDS:
        return _cache_rows
    completed=fetch_all(ns.RAW.format(competition=""),(day-timedelta(days=1),))
    rounds=fetch_all("SELECT id,rodada FROM public.jogos WHERE data<%s",(day,))
    labels={int(r["id"]):r.get("rodada") for r in rounds}
    all_rows=[]
    for item in completed:
        row=dict(item)
        row["data"]=_date(row["data"])
        row["rodada"]=labels.get(row["id"])
        all_rows.append(row)
    # Jogos ainda sem placar também podem ser exibidos. Eles só serão
    # liquidados quando todos os confrontos da rodada tiverem terminado.
    future=fetch_all("""
      SELECT j.id,j.data,j.temporada,j.campeonato_id,c.nome AS campeonato,
             j.rodada,j.casa_id,j.fora_id,
             h.clube AS mandante,v.clube AS visitante,
             j.gols_casa,j.gols_fora,
             oa.odd_1_ft AS api_odd_1_ft,
             oa.odd_x_ft AS api_odd_x_ft,
             oa.odd_2_ft AS api_odd_2_ft,
             oa.over_ft_0_5 AS api_over_ft_0_5,
             oa.over_ft_1_5 AS api_over_ft_1_5,
             oa.over_ft_2_5 AS api_over_ft_2_5,
             oa.over_ft_3_5 AS api_over_ft_3_5,
             oa.under_ft_2_5 AS api_under_ft_2_5,
             oa.btts_yes AS api_btts_yes,
             oa.btts_no AS api_btts_no,
             oa.lay_odd_1_ft AS api_lay_odd_1_ft,
             oa.lay_odd_x_ft AS api_lay_odd_x_ft,
             oa.lay_odd_2_ft AS api_lay_odd_2_ft,
             oa.lay_cs_1_0 AS api_lay_cs_1_0,
             oa.lay_cs_0_1 AS api_lay_cs_0_1
      FROM public.jogos j
      JOIN public.campeonatos c ON c.id=j.campeonato_id
      JOIN public.clubes h ON h.id=j.casa_id
      JOIN public.clubes v ON v.id=j.fora_id
      LEFT JOIN LATERAL (
         SELECT MAX(o.odd_1_ft) AS odd_1_ft,
                MAX(o.odd_x_ft) AS odd_x_ft,
                MAX(o.odd_2_ft) AS odd_2_ft,
                MAX(o.over_ft_0_5) AS over_ft_0_5,
                MAX(o.over_ft_1_5) AS over_ft_1_5,
                MAX(o.over_ft_2_5) AS over_ft_2_5,
                MAX(o.over_ft_3_5) AS over_ft_3_5,
                MAX(o.under_ft_2_5) AS under_ft_2_5,
                MAX(o.btts_yes) AS btts_yes,
                MAX(o.btts_no) AS btts_no,
                MAX(o.lay_odd_1_ft) AS lay_odd_1_ft,
                MAX(o.lay_odd_x_ft) AS lay_odd_x_ft,
                MAX(o.lay_odd_2_ft) AS lay_odd_2_ft,
                MAX(o.lay_cs_1_0) AS lay_cs_1_0,
                MAX(o.lay_cs_0_1) AS lay_cs_0_1
         FROM public.odds o
         WHERE o.mandante_id=j.casa_id AND o.visitante_id=j.fora_id
           AND o.data_jogo::date=j.data
           AND REPLACE(o.temporada,'-','/')=j.temporada
           AND LOWER(BTRIM(o.campeonato))=LOWER(BTRIM(c.nome))
         HAVING COUNT(*)=1
      ) oa ON TRUE
      WHERE j.data >= %s AND (j.gols_casa IS NULL OR j.gols_fora IS NULL)
      ORDER BY j.data,j.id
      LIMIT 3500
    """,(day,))
    for item in future:
        row=dict(item)
        row["data"]=_date(row["data"])
        all_rows.append(row)
    all_rows.sort(key=lambda r:(r["data"],int(r["id"])))
    _cache_rows=all_rows
    _cache_day=day
    _cache_at=monotonic()
    return all_rows


def _month_end(day):
    return day.replace(day=monthrange(day.year,day.month)[1])


def _rounds(cutoff, catalog):
    """Janelas de até 10 dias, sem ultrapassar o mês civil.

    Em cada Próxima rodada, o corte vira a MAIOR DATA dos jogos exibidos.
    Se não houver partidas nos próximos dez dias, oferece uma janela vazia
    e permite avançar até o limite do período (sem revelar placares).
    """
    ordered=sorted(
        (r for r in catalog if r["data"]>cutoff),
        key=lambda r:(r["data"],int(r["campeonato_id"]),int(r["id"]))
    )
    if not ordered:
        return []
    last_day=ordered[-1]["data"]
    windows=[]
    position=0
    cursor=cutoff
    while cursor<last_day:
        first=cursor+timedelta(days=1)
        limit=min(cursor+timedelta(days=10),_month_end(first))
        games=[]
        while position<len(ordered) and ordered[position]["data"]<=limit:
            games.append(ordered[position])
            position+=1
        next_cut=max(g["data"] for g in games) if games else limit
        windows.append({
            "corte":cursor,
            "limite":limit,
            "proximo_corte":next_cut,
            "jogos":games,
        })
        cursor=next_cut
    return windows


def _round_at(rounds,index):
    return rounds[index]["jogos"] if 0<=index<len(rounds) else []


def _window_at(rounds,index):
    return rounds[index] if 0<=index<len(rounds) else None


def _history(catalog):
    histories=defaultdict(list)
    for row in catalog:
        if row["gols_casa"] is None or row["gols_fora"] is None or row["data"]>=today():
            continue
        for side,club in (("home",row["casa_id"]),("away",row["fora_id"])):
            key=(row["campeonato_id"],row["temporada"],club)
            histories[key].append((row["data"],int(row["id"]),ns._history_item(row,side)))
    for history in histories.values():
        history.sort(key=lambda x:(x[0],x[1]))
    return histories


def _team_stats(histories,game,club,window):
    history=histories.get((game["campeonato_id"],game["temporada"],club),())
    entries=[item for dt,_,item in history if dt<game["data"]]
    return ns._stats(entries,window),min(len(entries),window)


def _methods():
    methods=[]
    for raw in queries_estrategias.listar():
        if raw.get("objetivo") not in ns.MERCADOS:
            continue
        try:
            conditions=ns._valid_conditions(raw.get("condicoes"))
        except ValueError:
            continue
        league_ids=raw.get("campeonato_ids") or (
            [raw["campeonato_id"]] if raw.get("campeonato_id") else []
        )
        try:
            window=int(raw.get("jogos") or 20)
        except (TypeError,ValueError):
            window=20
        methods.append({
            "id":int(raw["id"]),"versao":int(raw["versao"]),
            "nome":str(raw["nome"]),"objetivo":raw["objetivo"],
            "condicoes":conditions,"ligas":set(int(v) for v in league_ids),
            "jogos":max(5,min(window,1000)),
        })
    return methods


def _market(game,market):
    if market not in ns.MERCADOS:
        return None
    favorite=ns._favorite_home(game)
    try:
        effective=ns._market_for_game(market,favorite)
    except ValueError:
        return None
    odd,origin=ns._odds_for_game(game,effective,None)
    if odd is None:
        return None
    return {"mercado":market,"nome":ns.MERCADOS[market],"odd":round(odd,3),
            "estimada":origin=="lay_estimado","origem":origin,
            "favorito_casa":favorite}


def _available_markets(game):
    return [offer for key in ns.MERCADOS if (offer:=_market(game,key)) is not None]


def _matched(game,stat_home,stat_away,methods):
    if stat_home is None or stat_away is None:
        return []
    favorite=ns._favorite_home(game)
    valid=[]
    for m in methods:
        if m["ligas"] and game["campeonato_id"] not in m["ligas"]:
            continue
        # Mantém os indicadores e odds originais do método.
        found=[]
        for cond in m["condicoes"]:
            if cond.get("tipo")=="odd":
                offer=_market(game,cond["mercado"])
                if offer is None or (
                    cond["odd_min"] is not None and offer["odd"]<cond["odd_min"]
                ) or (
                    cond["odd_max"] is not None and offer["odd"]>cond["odd_max"]
                ):
                    break
                found.append({"tipo":"odd","nome":ns.ODD_FILTER_MARKETS[cond["mercado"]],
                              "odd":offer["odd"],"odd_min":cond["odd_min"],
                              "odd_max":cond["odd_max"]})
            else:
                detail=ns._evaluate_condition(cond,stat_home,stat_away,favorite)
                if detail is None:
                    break
                found.append(detail)
        else:
            offer=_market(game,m["objetivo"])
            if offer is not None:
                valid.append({"id":m["id"],"versao":m["versao"],"nome":m["nome"],
                              "objetivo":m["objetivo"],"mercado":offer,
                              "regras":found})
    return valid


def _games_for_session(sess,catalog,rounds):
    games=_round_at(rounds,0)
    history=_history(catalog)
    methods=_methods()
    public=[]
    for g in games:
        # Dados pré-jogo só usam partidas concluídas em dias anteriores.
        stats={}
        counts={}
        for label,club in (("mandante",g["casa_id"]),("visitante",g["fora_id"])):
            stat,n=_team_stats(history,g,club,20)
            stats[label]=stat
            counts[label]=n
        markets=_available_markets(g)
        method_details=[]
        for m in methods:
            if m["ligas"] and g["campeonato_id"] not in m["ligas"]:
                continue
            h,hn=_team_stats(history,g,g["casa_id"],m["jogos"])
            a,an=_team_stats(history,g,g["fora_id"],m["jogos"])
            method_details.extend(_matched(g,h,a,[m]))
        safe={
            "jogo_id":int(g["id"]),
            "data":g["data"].isoformat(),
            "campeonato":g["campeonato"],
            "campeonato_id":int(g["campeonato_id"]),
            "temporada":g["temporada"],
            "rodada":g.get("rodada") or "Rodada por data",
            "mandante":g["mandante"],"visitante":g["visitante"],
            "odds_match":{
                "mandante":next((m["odd"] for m in markets if m["mercado"]=="back_mandante"),None),
                "empate":next((m["odd"] for m in markets if m["mercado"]=="back_empate"),None),
                "visitante":next((m["odd"] for m in markets if m["mercado"]=="back_visitante"),None),
            },
            "mercados":markets,
            "metodos":method_details,
            "estatisticas":stats,"amostra":counts,
        }
        if sess["fase"] in ("revelada","concluida"):
            # Resultados são acrescentados APENAS quando o servidor salvou
            # a finalização desta rodada, nunca antes.
            safe["placar"]={"mandante":g["gols_casa"],"visitante":g["gols_fora"]}
        public.append(safe)
    return games,public


def _token_session(token):
    digest=_hash(token)
    if not digest:
        return None
    rows=fetch_all("SELECT * FROM galileu_private.sessoes WHERE token_hash=%s",(digest,))
    return rows[0] if rows else None


def _bet_rows(sid):
    return fetch_all("""
      SELECT e.id,e.jogo_id,e.indice_rodada,e.tipo,e.metodo_id,e.metodo_versao,e.metodo_nome,e.mercado,
             e.odd,e.stake,e.status,e.lucro_prejuizo,e.cotacao_estimada,
             j.data,c.nome AS campeonato,h.clube AS mandante,v.clube AS visitante
      FROM galileu_private.entradas e
      JOIN public.jogos j ON j.id=e.jogo_id
      JOIN public.campeonatos c ON c.id=j.campeonato_id
      JOIN public.clubes h ON h.id=j.casa_id
      JOIN public.clubes v ON v.id=j.fora_id
      WHERE e.sessao_id=%s
      ORDER BY e.id
    """,(sid,))


def _closed_game_ids(sid,round_index):
    """Fechamentos não descartam entradas e não revelam placar."""
    return {int(r["jogo_id"]) for r in fetch_all("""
      SELECT jogo_id FROM galileu_private.jogos_finalizados
      WHERE sessao_id=%s AND indice_rodada=%s
    """,(sid,round_index))}


def _summary(bets,initial):
    """ROI = lucro líquido / soma das stakes (responsabilidades no Lay)."""
    def metric(rows):
        resolved=[r for r in rows if r["status"] in ("green","red")]
        pnl=sum((Decimal(r["lucro_prejuizo"]) for r in resolved),Decimal("0"))
        staked=sum((Decimal(r["stake"]) for r in resolved),Decimal("0"))
        green=sum(r["status"]=="green" for r in resolved)
        red=sum(r["status"]=="red" for r in resolved)
        return {"entradas":len(rows),"greens":green,"reds":red,
                "pendentes":len(rows)-len(resolved),
                "win_rate":round(100*green/(green+red),2) if green+red else 0,
                "lucro_prejuizo":_brl(pnl),
                "roi":round(float(pnl/staked*100),2) if staked else 0}
    monthly=defaultdict(list)
    for b in bets:
        monthly[str(b["data"])[:7]].append(b)
    response=[]
    cumulative=Decimal(initial)
    for month,items in sorted(monthly.items()):
        result=metric(items)
        cumulative+=Decimal(str(result["lucro_prejuizo"]))
        by_strategy=defaultdict(list)
        by_league=defaultdict(list)
        by_club=defaultdict(list)
        for b in items:
            by_strategy[b["metodo_nome"] if b["tipo"]=="metodo" else "Entrada manual"].append(b)
            by_league[b["campeonato"]].append(b)
            for club in (b["mandante"],b["visitante"]):
                by_club[club].append(b)
        def group(groups):
            return [{"nome":key,**metric(value)} for key,value in sorted(groups.items())]
        response.append({
            "mes":month,"banca_fim":_brl(cumulative),**result,
            "por_estrategia":group(by_strategy),
            "por_liga":group(by_league),"por_clube":group(by_club),
        })
    return response


def _monthly_boundary(rounds,index):
    current=_round_at(rounds,index)
    if not current:
        return False,None
    month=max(g["data"] for g in current).strftime("%Y-%m")
    # Encerrar o mês na última rodada COM JOGOS daquele mês; períodos
    # vazios entre dezembro/janeiro não adiam indevidamente o fechamento.
    following=next((window["jogos"] for window in rounds[index+1:]
                    if window["jogos"]),None)
    if following is None or min(g["data"] for g in following).strftime("%Y-%m")!=month:
        return True,month
    return False,None


def _default_stake(sess):
    if sess["stake_fixa"] is not None:
        return _brl(sess["stake_fixa"])
    return _brl(_rounded(Decimal(sess["banca_atual"])*Decimal(sess["gestao_pct"])/100))


def estado(token):
    sess=_token_session(token)
    if sess is None:
        return {"iniciado":False}
    catalog=_catalog()
    current_cutoff=_date(sess.get("corte_atual") or sess["corte"])
    rounds=_rounds(current_cutoff,catalog)
    raw_games,games=_games_for_session(sess,catalog,rounds)
    window=_window_at(rounds,0)
    bets=_bet_rows(sess["id"])
    current=[b for b in bets if b["indice_rodada"]==sess["indice_rodada"]]
    by_game=defaultdict(list)
    for bet in current:
        by_game[int(bet["jogo_id"])].append({
            "id":int(bet["id"]),"tipo":bet["tipo"],
            "metodo_id":int(bet["metodo_id"]) if bet.get("metodo_id") is not None else None,
            "metodo":bet["metodo_nome"],"mercado":bet["mercado"],
            "odd":float(bet["odd"]),"stake":_brl(bet["stake"]),
            "status":bet["status"],
            "lucro_prejuizo":_brl(bet["lucro_prejuizo"])
            if bet["lucro_prejuizo"] is not None else None,
        })
    closed=_closed_game_ids(sess["id"],sess["indice_rodada"])
    # Os jogos fechados desaparecem da lista, mas continuam no calendário
    # completo para liquidação de TODAS as entradas em Finalizar rodada.
    visible=[]
    for g in games:
        g["entradas"]=by_game.get(g["jogo_id"],[])
        if g["jogo_id"] not in closed:
            visible.append(g)
    boundary,month=_monthly_boundary(rounds,0)
    revealed=sess["fase"] in ("revelada","concluida")
    history=_summary(bets,sess["banca_inicial"])
    resumo_rodada=[]
    if revealed:
        # Apenas após a finalização da rodada: relatório de TODAS as
        # entradas, inclusive dos jogos removidos da lista individual.
        placares={int(g["id"]):g for g in raw_games}
        for bet in current:
            jogo=placares.get(int(bet["jogo_id"]))
            resumo_rodada.append({
                "jogo_id":int(bet["jogo_id"]),
                "confronto":str(bet["mandante"])+" × "+str(bet["visitante"]),
                "metodo":bet["metodo_nome"] if bet["tipo"]=="metodo" else "Manual",
                "mercado":bet["mercado"],
                "odd":float(bet["odd"]),
                "stake":_brl(bet["stake"]),
                "status":bet["status"],
                "lucro_prejuizo":_brl(bet["lucro_prejuizo"])
                    if bet["lucro_prejuizo"] is not None else None,
                "placar":(
                    str(jogo["gols_casa"])+" × "+str(jogo["gols_fora"])
                    if jogo is not None else None
                ),
            })
    return {
        "iniciado":True,
        "fase":sess["fase"],"versao":int(sess["versao"]),
        "corte":_date(sess["corte"]).isoformat(),
        "corte_atual":current_cutoff.isoformat(),
        "limite_janela":window["limite"].isoformat() if window else None,
        "banca_inicial":_brl(sess["banca_inicial"]),
        "banca_atual":_brl(sess["banca_atual"]),
        "gestao_pct":float(sess["gestao_pct"]),
        "stake_fixa":_brl(sess["stake_fixa"]) if sess["stake_fixa"] is not None else None,
        "stake_padrao":_default_stake(sess),
        "rodada_indice":int(sess["indice_rodada"])+1,
        "rodada_atual":{
            "jogos":len(games),
            "inicio":min((g["data"] for g in raw_games),default=None).isoformat() if raw_games else None,
            "fim":max((g["data"] for g in raw_games),default=None).isoformat() if raw_games else None,
        },
        "jogos":visible,
        "jogos_finalizados":len(closed),
        "resumo_rodada":resumo_rodada,
        "entradas":len(bets),
        "mes_encerrado":month if revealed and boundary else None,
        "resumo_mensal":history,
        "pode_avancar":revealed and len(rounds)>1,
        "periodo_vazio":not bool(raw_games),
        "pode_pular_vazio":sess["fase"]=="aberta" and not raw_games and len(rounds)>1,
        "aviso":"Gameplay histórica com odds importadas sem prova de disponibilidade pré-jogo. Lay é estimado; nenhuma aposta é executada.",
    }


def iniciar(token,payload):
    if not isinstance(payload,dict):
        raise ValueError("Dados inválidos.")
    if _token_session(token):
        raise ValueError("Já existe progresso salvo neste navegador. Use Reiniciar progresso se desejar começar de novo.")
    cutoff=_date(payload.get("corte"))
    if cutoff>=today():
        raise ValueError("Para iniciar, escolha uma data de corte anterior a hoje.")
    initial=_money(payload.get("banca_inicial"),"Banca inicial")
    percent=_pct(payload.get("gestao_pct"))
    # Nunca reutiliza token recebido do navegador; só o servidor o gera.
    import secrets
    new_token=secrets.token_urlsafe(40)
    catalog=_catalog()
    if not _rounds(cutoff,catalog):
        raise ValueError("Não há rodadas cadastradas depois dessa data de corte.")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
              INSERT INTO galileu_private.sessoes
                (token_hash,corte,corte_atual,banca_inicial,banca_atual,gestao_pct)
              VALUES (%s,%s,%s,%s,%s,%s)
              RETURNING id
            """,(_hash(new_token),cutoff,cutoff,initial,initial,percent))
            cur.fetchone()
        conn.commit()
    return new_token


def _lock(cur,token):
    digest=_hash(token)
    if digest is None:
        raise ValueError("Sua sessão não foi encontrada. Inicie o Galileu.")
    cur.execute("SELECT * FROM galileu_private.sessoes WHERE token_hash=%s FOR UPDATE",(digest,))
    sess=cur.fetchone()
    if sess is None:
        raise ValueError("Sua sessão não foi encontrada. Inicie o Galileu.")
    return sess


def registrar(token,payload):
    if not isinstance(payload,dict):
        raise ValueError("Entrada inválida.")
    gid=payload.get("jogo_id")
    if type(gid) is not int or gid<1:
        raise ValueError("Jogo inválido.")
    stake=_money(payload.get("stake"),"Stake")
    kind=payload.get("tipo")
    if kind not in ("manual","metodo"):
        raise ValueError("Selecione Entrada manual ou Entrada do método.")
    catalog=_catalog()
    with get_conn() as conn:
        with conn.cursor() as cur:
            sess=_lock(cur,token)
            if sess["fase"]!="aberta":
                raise ValueError("A rodada já foi finalizada. Não é possível criar entradas.")
            rounds=_rounds(_date(sess.get("corte_atual") or sess["corte"]),catalog)
            current=_round_at(rounds,0)
            game=next((g for g in current if int(g["id"])==gid),None)
            if game is None:
                raise ValueError("Este jogo não pertence à rodada atual.")
            cur.execute("""
                SELECT 1 FROM galileu_private.jogos_finalizados
                WHERE sessao_id=%s AND jogo_id=%s
            """,(sess["id"],gid))
            if cur.fetchone():
                raise ValueError("Este jogo foi finalizado. Não é possível adicionar entradas.")
            cur.execute("""
                SELECT COALESCE(SUM(stake),0) AS comprometido
                FROM galileu_private.entradas
                WHERE sessao_id=%s AND indice_rodada=%s
            """,(sess["id"],sess["indice_rodada"]))
            committed=Decimal(cur.fetchone()["comprometido"])
            if stake>Decimal(sess["banca_atual"])-committed:
                raise ValueError("Stake excede a banca disponível após entradas já confirmadas nesta rodada.")
            if kind=="metodo":
                methods=_methods()
                hist=_history(catalog)
                matched=[]
                for m in methods:
                    if m["ligas"] and game["campeonato_id"] not in m["ligas"]:
                        continue
                    h,_=_team_stats(hist,game,game["casa_id"],m["jogos"])
                    a,_=_team_stats(hist,game,game["fora_id"],m["jogos"])
                    matched.extend(_matched(game,h,a,[m]))
                method_id=payload.get("metodo_id")
                if type(method_id) is not int:
                    raise ValueError("Selecione um método validado.")
                method=next((m for m in matched if m["id"]==method_id),None)
                if method is None:
                    raise ValueError("Método não validado para este confronto.")
                if payload.get("metodo_versao")!=method["versao"]:
                    raise ValueError("O método foi alterado. Atualize a rodada.")
                offer=method["mercado"]
                name=method["nome"]
                version=method["versao"]
                market=method["objetivo"]
            else:
                market=payload.get("mercado")
                if not isinstance(market,str):
                    raise ValueError("Selecione o mercado da entrada.")
                offer=_market(game,market)
                if offer is None:
                    raise ValueError("Este mercado não possui cotação histórica válida para o jogo.")
                method_id=None
                version=None
                name=None
            try:
                cur.execute("""
                  INSERT INTO galileu_private.entradas
                    (sessao_id,jogo_id,indice_rodada,tipo,metodo_id,metodo_versao,
                     metodo_nome,mercado,odd,stake,cotacao_estimada,favorito_casa)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,(sess["id"],gid,sess["indice_rodada"],kind,method_id,version,
                     name,market,offer["odd"],stake,offer["estimada"],offer["favorito_casa"]))
            except errors.UniqueViolation:
                raise ValueError("Você já fez uma entrada neste método para este jogo.") from None
            cur.execute("""
              UPDATE galileu_private.sessoes
              SET versao=versao+1,atualizado_em=now() WHERE id=%s
            """,(sess["id"],))
        conn.commit()
    return {"mensagem":"Entrada virtual confirmada. O placar permanece oculto até finalizar a rodada."}


def finalizar_jogo(token,payload):
    """Oculta um jogo da lista atual, preservando apostas e liquidação."""
    if not isinstance(payload,dict) or type(payload.get("jogo_id")) is not int or payload["jogo_id"]<1:
        raise ValueError("Jogo inválido.")
    gid=payload["jogo_id"]
    catalog=_catalog()
    with get_conn() as conn:
        with conn.cursor() as cur:
            sess=_lock(cur,token)
            if sess["fase"]!="aberta":
                raise ValueError("A rodada não está aberta para finalizar jogos.")
            rounds=_rounds(_date(sess.get("corte_atual") or sess["corte"]),catalog)
            if not any(int(g["id"])==gid for g in _round_at(rounds,0)):
                raise ValueError("Jogo fora da rodada atual.")
            cur.execute("""
                INSERT INTO galileu_private.jogos_finalizados
                  (sessao_id,jogo_id,indice_rodada)
                VALUES (%s,%s,%s)
                ON CONFLICT (sessao_id,jogo_id) DO NOTHING
                RETURNING jogo_id
            """,(sess["id"],gid,sess["indice_rodada"]))
            if not cur.fetchone():
                raise ValueError("Este jogo já foi finalizado.")
            cur.execute("""
                UPDATE galileu_private.sessoes
                SET versao=versao+1,atualizado_em=now()
                WHERE id=%s
            """,(sess["id"],))
        conn.commit()
    return {"mensagem":"Jogo finalizado e removido da lista. Entradas preservadas para a apuração da rodada."}


def _settlement(market,favorite_home,home,away,odd,stake):
    try:
        actual=ns._market_for_game(market,favorite_home)
    except ValueError:
        raise ValueError("Não é possível determinar o mercado da entrada confirmada.")
    hit=ns._settle(actual,int(home),int(away))
    # Em Lay, a stake é a responsabilidade máxima. A comissão incide
    # somente sobre o lucro, e não sobre a responsabilidade.
    if actual.startswith("lay_"):
        pnl=stake*(Decimal("1")-COMMISSION)/(Decimal(odd)-1) if hit else -stake
    else:
        pnl=stake*(Decimal(odd)-1) if hit else -stake
    return "green" if hit else "red",_rounded(pnl)


def finalizar(token):
    catalog=_catalog()
    with get_conn() as conn:
        with conn.cursor() as cur:
            sess=_lock(cur,token)
            if sess["fase"]!="aberta":
                raise ValueError("Esta rodada já foi finalizada.")
            games=_round_at(_rounds(_date(sess.get("corte_atual") or sess["corte"]),catalog),0)
            if not games:
                raise ValueError("Não existem jogos para finalizar.")
            if any(g["data"]>=today() or g["gols_casa"] is None or g["gols_fora"] is None for g in games):
                raise ValueError("Há jogos ainda não concluídos. Os placares e o lucro não podem ser revelados agora.")
            by_id={int(g["id"]):g for g in games}
            cur.execute("""
              SELECT * FROM galileu_private.entradas
              WHERE sessao_id=%s AND indice_rodada=%s AND status='pendente'
              ORDER BY id FOR UPDATE
            """,(sess["id"],sess["indice_rodada"]))
            entries=cur.fetchall()
            profit=Decimal("0")
            for entry in entries:
                game=by_id.get(int(entry["jogo_id"]))
                if game is None:
                    raise ValueError("Uma entrada não pertence à rodada atual.")
                status,amount=_settlement(
                    entry["mercado"],entry["favorito_casa"],
                    game["gols_casa"],game["gols_fora"],
                    entry["odd"],Decimal(entry["stake"]))
                cur.execute("""
                  UPDATE galileu_private.entradas
                  SET status=%s,lucro_prejuizo=%s,finalizada_em=now()
                  WHERE id=%s
                """,(status,amount,entry["id"]))
                profit+=amount
            new_bank=Decimal(sess["banca_atual"])+profit
            if new_bank<0:
                raise ValueError("Saldo inválido. Revise o valor das entradas confirmadas.")
            cur.execute("""
              UPDATE galileu_private.sessoes
              SET banca_atual=%s,fase='revelada',versao=versao+1,atualizado_em=now()
              WHERE id=%s
            """,(_rounded(new_bank),sess["id"]))
        conn.commit()
    return {"mensagem":"Rodada finalizada. Resultados e lucro/prejuízo liberados."}


def proxima(token):
    catalog=_catalog()
    with get_conn() as conn:
        with conn.cursor() as cur:
            sess=_lock(cur,token)
            current_cutoff=_date(sess.get("corte_atual") or sess["corte"])
            rounds=_rounds(current_cutoff,catalog)
            current=_window_at(rounds,0)
            if sess["fase"]=="revelada":
                pass
            elif sess["fase"]=="aberta" and current and not current["jogos"]:
                # Período sem partidas: só avançar o calendário, sem
                # inventar placares, entradas ou balanço.
                pass
            else:
                raise ValueError("Finalize a rodada antes de avançar.")
            if current is None:
                raise ValueError("Não há períodos disponíveis.")
            next_cutoff=current["proximo_corte"]
            # Corte atualizado = última data da lista. Se a lista for vazia,
            # o corte avança até o limite de dez dias/fim do mês.
            exists=len(rounds)>1
            cur.execute("""
              UPDATE galileu_private.sessoes
              SET indice_rodada=indice_rodada+%s,
                  corte_atual=%s,fase=%s,versao=versao+1,
                  atualizado_em=now()
              WHERE id=%s
            """,(1 if exists else 0,next_cutoff,
                 "aberta" if exists else "concluida",sess["id"]))
        conn.commit()
    return {"mensagem":"Próximo período carregado."
                        if exists else "Simulação concluída: não há mais jogos.",
            "corte_atual":next_cutoff.isoformat()}


def reajustar(token,payload):
    if not isinstance(payload,dict):
        raise ValueError("Informe o reajuste.")
    mode=payload.get("tipo")
    if mode=="percentual":
        rate=_pct(payload.get("valor"))
        fixed=None
    elif mode=="fixo":
        rate=None
        fixed=_money(payload.get("valor"),"Stake fixa")
    else:
        raise ValueError("Escolha Percentual ou Valor financeiro.")
    catalog=_catalog()
    with get_conn() as conn:
        with conn.cursor() as cur:
            sess=_lock(cur,token)
            rounds=_rounds(_date(sess.get("corte_atual") or sess["corte"]),catalog)
            boundary,_=_monthly_boundary(rounds,0)
            if sess["fase"]!="revelada" or not boundary:
                raise ValueError("Reajuste disponível ao encerrar um mês na rodada finalizada.")
            if fixed is not None and fixed>Decimal(sess["banca_atual"]):
                raise ValueError("Stake fixa não pode exceder a banca atual.")
            cur.execute("""
              UPDATE galileu_private.sessoes SET
                gestao_pct=COALESCE(%s,gestao_pct),
                stake_fixa=%s,versao=versao+1,atualizado_em=now()
              WHERE id=%s
            """,(rate,fixed,sess["id"]))
        conn.commit()
    return {"mensagem":"Gestão de stake atualizada para as próximas entradas."}


def reiniciar(token):
    digest=_hash(token)
    if digest:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM galileu_private.sessoes WHERE token_hash=%s",(digest,))
            conn.commit()
    return {"mensagem":"Progresso reiniciado. Configure uma nova banca para começar."}
