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
import queries_nostradamus_aovivo as live
import queries_galileu_melhorias as melhorias

COOKIE="galileu_gameplay"
TZ=ZoneInfo("America/Sao_Paulo")
COMMISSION=Decimal("0.045")
MAX_BANK=Decimal("1000000000")
CENTS=Decimal("0.01")
# O catálogo é custoso (histórico, odds e indicadores físicos), mas seus dados
# históricos não mudam a cada entrada. Reutilize por quinze minutos.
LIVE_METHOD_BASE=1_000_000_000_000  # IDs exclusivos para cenários ao vivo
CACHE_SECONDS=15*60
_cache_at=0.0
_cache_day=None
_cache_rows=None
_history_catalog=None
_history_data=None


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
    """Uma janela por mês civil, sem revelar placares antes da finalização.

    Na primeira janela, respeita a data de corte escolhida pelo usuário.
    Os próximos meses são completos, inclusive meses vazios, para permitir
    o fechamento mensal sem saltar datas.
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
        limit=_month_end(first)
        games=[]
        while position<len(ordered) and ordered[position]["data"]<=limit:
            games.append(ordered[position])
            position+=1
        next_cut=limit
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
    # Construção dos históricos é proporcional ao total de jogos e antes
    # acontecia a cada clique em Confirmar. O cache usa identidade do
    # catálogo (e é naturalmente invalidado quando o catálogo é renovado).
    global _history_catalog,_history_data
    if catalog is _history_catalog and _history_data is not None:
        return _history_data
    histories=defaultdict(list)
    for row in catalog:
        if row["gols_casa"] is None or row["gols_fora"] is None or row["data"]>=today():
            continue
        for side,club in (("home",row["casa_id"]),("away",row["fora_id"])):
            key=(row["campeonato_id"],row["temporada"],club)
            histories[key].append((row["data"],int(row["id"]),ns._history_item(row,side)))
    for history in histories.values():
        history.sort(key=lambda x:(x[0],x[1]))
    _history_catalog=catalog
    _history_data=histories
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
    # Cenários salvos na aba Ao vivo são métodos independentes, com
    # identificadores que não colidem com o cadastro pré-jogo.
    for raw in live.listar_cenarios():
        try:
            config=dict(raw["configuracao"])
            # O corte salvo limita o backtest, não o período de uso no Galileu.
            config["corte"]=today().isoformat()
            config=live._config(config)
            # simular() valida o payload de entrada novamente; a data
            # do formulário deve permanecer como ISO, não objeto date.
            config["corte"]=config["corte"].isoformat()
        except (TypeError,ValueError,KeyError):
            continue
        methods.append({
            "id":LIVE_METHOD_BASE+int(raw["id"]),
            "versao":int(raw["versao"]),
            "nome":"Ao vivo · "+str(raw["nome"]),
            "objetivo":config["mercado"],
            "condicoes":config["condicoes"],
            "ligas":set(config["campeonato_ids"] or []),
            "jogos":1000 if config["jogos"]=="temporada" else int(config["jogos"]),
            "tipo":"ao_vivo",
            "configuracao":config,
        })
    return methods


def _live_offers(games,methods,catalog,disabled=None):
    """Aplica cenários salvos ao placar REAL no minuto, nunca ao final.

    Os resultados finais não entram nas condições de seleção. Todas as odds
    são estimadas naquele minuto pelo mesmo modelo do Nostradamus ao vivo.
    O retorno para a tela contém só o método e sua odd, sem revelar placares.
    """
    subset=[m for m in methods if m.get("tipo")=="ao_vivo"]
    if not subset or not games:
        return {}
    disabled=disabled or {}
    past=[g for g in games if _date(g["data"])<today()
          and g.get("gols_casa") is not None and g.get("gols_fora") is not None]
    if not past:
        return {}
    active=[m for m in subset if any(
        not _is_disabled(m["id"],g["data"],disabled) for g in past
    )]
    if not active:
        return {}
    ids=[int(g["id"]) for g in past]
    by_minute={}
    for minute in {m["configuracao"]["minuto"] for m in active}:
        # Restringe a CTE ao mês em curso: não consulta todos os lances
        # históricos a cada atualização da página.
        sql=live.SQL.replace(
            "WHERE f.tipo_evento='Gol' OR f.tipo_evento IS NOT NULL",
            "WHERE f.jogo_id=ANY(%s::integer[]) AND "
            "(f.tipo_evento='Gol' OR f.tipo_evento IS NOT NULL)"
        )
        if sql==live.SQL:
            raise RuntimeError("Não foi possível restringir os gols à rodada.")
        # Ordem dos placeholders na SQL:
        # (1) minuto dos gols do mandante, (2) minuto dos gols do visitante,
        # (3) IDs da rodada no WHERE da CTE, (4) data de corte,
        # (5–6) filtro opcional por campeonato.
        by_minute[minute]=fetch_all(
            sql,(minute,minute,ids,today(),None,None))
    result=defaultdict(list)
    for method in active:
        cfg=method["configuracao"]
        current_rows=[
            r for r in by_minute[cfg["minuto"]]
            if not _is_disabled(method["id"],r["data"],disabled)
        ]
        if not current_rows:
            continue
        # O mesmo backtest do Nostradamus decide placar/minuto, estatísticas
        # pré-jogo e odd. Nenhum detalhe é truncado para o Galileu.
        matches=live.simular(
            cfg,rows=current_rows,history_rows=catalog,
            detail_limit=len(current_rows)
        )
        for matched in matches["detalhes"]:
            if matched["odd"] is None:
                continue  # Mercado decidido ou sem preço modelável.
            result[int(matched["id"])].append({
                "id":method["id"],"versao":method["versao"],
                "nome":method["nome"],"objetivo":method["objetivo"],
                "tipo":"ao_vivo",
                "mercado":{
                    "mercado":method["objetivo"],
                    "nome":ns.MERCADOS[method["objetivo"]],
                    "odd":matched["odd"],"estimada":True,
                    "origem":matched["cotacao"],
                    "favorito_casa":next((
                        ns._favorite_home(r) for r in current_rows
                        if int(r["id"])==int(matched["id"])
                    ),None)
                },
                "regras":[],  # Não antecipar os gols do minuto ao usuário.
            })
    return result


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
            "estimada":origin in ("lay_estimado","modelo_cs_back","modelo_cs_lay"),
            "origem":origin,
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


def _disabled_methods(sid):
    """Métodos removidos somente desta gameplay, nunca do Nostradamus."""
    return {
        int(row["metodo_id"]):{
            "nome":str(row["nome_metodo"]),
            "desde":str(row["efetivo_desde"]),
        }
        for row in fetch_all("""
            SELECT metodo_id,nome_metodo,efetivo_desde
            FROM galileu_private.metodos_desativados
            WHERE sessao_id=%s ORDER BY metodo_id
        """,(sid,))
    }


def _is_disabled(method_id,game_date,disabled):
    """Respeita o início da retirada, sem alterar os meses já percorridos."""
    record=disabled.get(int(method_id))
    return bool(record and str(game_date)[:7]>=record["desde"])


def _games_for_session(sess,catalog,rounds,methods=None,disabled=None):
    games=_round_at(rounds,0)
    history=_history(catalog)
    if methods is None:
        methods=_methods()
    if disabled is None:
        disabled=_disabled_methods(sess["id"])
    live_offers=_live_offers(games,methods,catalog,disabled)
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
            if m.get("tipo")=="ao_vivo":
                continue
            if _is_disabled(m["id"],g["data"],disabled):
                continue
            if m["ligas"] and g["campeonato_id"] not in m["ligas"]:
                continue
            h,hn=_team_stats(history,g,g["casa_id"],m["jogos"])
            a,an=_team_stats(history,g,g["fora_id"],m["jogos"])
            method_details.extend(_matched(g,h,a,[m]))
        method_details.extend(live_offers.get(int(g["id"]),[]))
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


def _sync_live_entries(token,sess,raw_games,public_games):
    """Programa automaticamente TODOS os métodos validados no mês.

    Inclui métodos pré-jogo e cenários ao vivo; respeita exclusões e jogos
    finalizados. Uma combinação (sessão, jogo, método) só é criada uma vez.
    O salvamento é atômico e nunca revela resultados antes da liquidação.
    """
    if sess["fase"]!="aberta":
        return 0
    original={int(g["id"]):g for g in raw_games}
    candidates=[]
    for game in public_games:
        gid=int(game["jogo_id"])
        raw=original.get(gid)
        if raw is None:
            continue
        for method in game["metodos"]:
            # Os métodos pré-jogo e os cenários ao vivo são programados
            # sem seleção manual. Cada método conserva seu próprio mercado.
            offer=method["mercado"]
            candidates.append((gid,raw,method,offer))
    if not candidates:
        return 0
    from psycopg2.extras import execute_values
    with get_conn() as conn:
        with conn.cursor() as cur:
            locked=_lock(cur,token)
            if locked["fase"]!="aberta" or int(locked["indice_rodada"])!=int(sess["indice_rodada"]):
                return 0
            cur.execute("""
                SELECT metodo_id,efetivo_desde
                FROM galileu_private.metodos_desativados
                WHERE sessao_id=%s
            """,(sess["id"],))
            disabled={
                int(row["metodo_id"]):{"desde":str(row["efetivo_desde"])}
                for row in cur.fetchall()
            }
            cur.execute("""
                SELECT jogo_id FROM galileu_private.jogos_finalizados
                WHERE sessao_id=%s AND indice_rodada=%s
            """,(sess["id"],sess["indice_rodada"]))
            closed={int(row["jogo_id"]) for row in cur.fetchall()}
            data=[]
            for gid,raw,method,offer in candidates:
                if gid in closed or _is_disabled(method["id"],raw["data"],disabled):
                    continue
                data.append((
                    sess["id"],gid,sess["indice_rodada"],"metodo",
                    method["id"],method["versao"],method["nome"],
                    method["objetivo"],offer["odd"],
                    _rounded(_default_stake(locked)),
                    bool(offer.get("estimada",False)),
                    offer["favorito_casa"],
                ))
            if not data:
                return 0
            execute_values(cur,"""
                INSERT INTO galileu_private.entradas
                    (sessao_id,jogo_id,indice_rodada,tipo,metodo_id,metodo_versao,
                     metodo_nome,mercado,odd,stake,cotacao_estimada,favorito_casa)
                VALUES %s
                ON CONFLICT DO NOTHING
                RETURNING id
            """,data,page_size=len(data))
            inserted=cur.fetchall()
            if inserted:
                cur.execute("""
                    UPDATE galileu_private.sessoes
                    SET versao=versao+1,atualizado_em=now()
                    WHERE id=%s
                """,(sess["id"],))
        conn.commit()
    return len(inserted)


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


def _fechamentos(sid):
    return fetch_all("""
        SELECT mes,indice_rodada,banca_base_inicio,banca_fechamento,
               aporte,saque,banca_base_seguinte,gestao_pct_antes,
               gestao_pct_depois,stake_fixa_antes,stake_fixa_depois,criado_em
        FROM galileu_private.fechamentos_mensais
        WHERE sessao_id=%s ORDER BY mes
    """,(sid,))


def _movimentacoes(sid):
    return fetch_all("""
        SELECT id,mes_referencia,tipo,valor,banca_antes,banca_depois,
               gestao_pct_antes,gestao_pct_depois,
               stake_fixa_antes,stake_fixa_depois,criado_em
        FROM galileu_private.movimentacoes
        WHERE sessao_id=%s ORDER BY id
    """,(sid,))


def _format_movimento(row):
    return {
        "id":int(row["id"]),"mes":str(row["mes_referencia"]),"tipo":row["tipo"],
        "valor":_brl(row["valor"]),
        "banca_antes":_brl(row["banca_antes"]),
        "banca_depois":_brl(row["banca_depois"]),
        "gestao_pct_antes":float(row["gestao_pct_antes"])
            if row["gestao_pct_antes"] is not None else None,
        "gestao_pct_depois":float(row["gestao_pct_depois"])
            if row["gestao_pct_depois"] is not None else None,
        "stake_fixa_antes":_brl(row["stake_fixa_antes"])
            if row["stake_fixa_antes"] is not None else None,
        "stake_fixa_depois":_brl(row["stake_fixa_depois"])
            if row["stake_fixa_depois"] is not None else None,
        "criado_em":row["criado_em"].isoformat(),
    }


def relatorios(token):
    """Relatório privado que não carrega odds, estatísticas nem placares."""
    sess=_token_session(token)
    if sess is None:
        return {"iniciado":False}
    fechamentos=_fechamentos(sess["id"])
    bets=_bet_rows(sess["id"])
    movements=_movimentacoes(sess["id"])
    monthly=_summary(bets,sess["banca_inicial"],fechamentos)
    overall=[b for b in bets if b["status"] in ("green","red")]
    profit=sum((Decimal(b["lucro_prejuizo"]) for b in overall),Decimal("0"))
    exposure=sum((Decimal(b["stake"]) for b in overall),Decimal("0"))
    funding=sum((Decimal(c["aporte"])-Decimal(c["saque"]) for c in fechamentos),Decimal("0"))
    return {
        "iniciado":True,
        "banca_original":_brl(sess["banca_inicial"]),
        "banca_base_mes":_brl(sess["banca_base_mes"]),
        "banca_atual":_brl(sess["banca_atual"]),
        "mes_base":str(sess["mes_base"]),
        "gestao_pct":float(sess["gestao_pct"]),
        "stake_padrao":_default_stake(sess),
        "aporte_total":_brl(sum((Decimal(c["aporte"]) for c in fechamentos),Decimal("0"))),
        "saque_total":_brl(sum((Decimal(c["saque"]) for c in fechamentos),Decimal("0"))),
        "lucro_prejuizo_total":_brl(profit),
        "roi_total":round(float(profit/exposure*100),2) if exposure else 0,
        "patrimonio_conferido":_brl(Decimal(sess["banca_inicial"])+funding+profit),
        "resumo_mensal":monthly,
        "agrupamentos":_financial_group_results(bets),
        "movimentacoes":[_format_movimento(m) for m in movements],
        "fechamentos":[{
            "mes":str(c["mes"]),"banca_base_inicio":_brl(c["banca_base_inicio"]),
            "banca_fechamento":_brl(c["banca_fechamento"]),
            "aporte":_brl(c["aporte"]),"saque":_brl(c["saque"]),
            "banca_base_seguinte":_brl(c["banca_base_seguinte"]),
        } for c in fechamentos],
        "entradas":len(bets),
    }


def _closed_game_ids(sid,round_index):
    """Fechamentos não descartam entradas e não revelam placar."""
    return {int(r["jogo_id"]) for r in fetch_all("""
      SELECT jogo_id FROM galileu_private.jogos_finalizados
      WHERE sessao_id=%s AND indice_rodada=%s
    """,(sid,round_index))}


def _method_monthly_table(bets,method_catalog,disabled,month):
    """Um registro por método, inclusive sem apostas; sequência só de greens/reds.

    A ordem considera data da partida e ID da entrada, sem vazamento
    dos resultados para telas de rodada aberta. Sem saldo/pendente não
    geram green ou red nem interrompem uma sequência liquidada.
    """
    grouped=defaultdict(list)
    manual=[]
    for bet in bets:
        if str(bet["data"])[:7]!=month:
            continue
        if bet.get("tipo")=="metodo" and bet.get("metodo_id") is not None:
            grouped[int(bet["metodo_id"])].append(bet)
        else:
            manual.append(bet)
    named={int(m["id"]):str(m["nome"]) for m in method_catalog}
    for mid,info in disabled.items():
        named.setdefault(mid,info["nome"])
    for mid,entries in grouped.items():
        named.setdefault(mid,str(entries[-1].get("metodo_nome") or "Método "+str(mid)))

    def totals(items):
        green=red=best_good=best_bad=good=bad=0
        pnl=Decimal("0")
        resolved=0
        for entry in sorted(items,key=lambda e:(str(e["data"]),int(e["id"]))):
            status=entry["status"]
            if status not in ("green","red"):
                continue
            resolved+=1
            pnl+=Decimal(str(entry["lucro_prejuizo"]))
            if status=="green":
                green+=1
                good+=1
                bad=0
                best_good=max(best_good,good)
            else:
                red+=1
                bad+=1
                good=0
                best_bad=max(best_bad,bad)
        return {
            "entradas":len(items),"executadas":resolved,
            "nao_executadas":sum(e["status"]=="sem_saldo" for e in items),
            "greens":green,"reds":red,
            "win_rate":round(green/resolved*100,2) if resolved else 0,
            "lucro_prejuizo":_brl(pnl),
            "maior_good_run":best_good,"maior_bad_run":best_bad,
        }

    result=[]
    for mid,name in named.items():
        record=disabled.get(mid)
        result.append({
            "metodo_id":mid,"nome":name,
            "desativado_desde":record["desde"] if record else None,
            "ativo_no_mes":not bool(record and record["desde"]<=month),
            **totals(grouped.get(mid,[])),
        })
    result.sort(key=lambda x:(-x["entradas"],x["nome"].casefold(),x["metodo_id"]))
    # Entradas manuais são mostradas em linha de referência, mas não podem
    # ser removidas como se representassem um método cadastrado.
    if manual:
        result.append({"metodo_id":None,"nome":"Entradas manuais",
                       "desativado_desde":None,"ativo_no_mes":False,
                       **totals(manual)})
    return result


def _method_loss_streak_alerts(bets,method_catalog,month):
    """Alerta apenas quando os três meses civis até o fechamento têm saldo negativo.

    Considera o lucro líquido de entradas executadas (green/red), agrupadas
    pelo ID estável do método. Lucro, empate, ausência de entradas ou mês sem
    execução interrompem a sequência. Não compara contagens de reds.
    """
    reference=date.fromisoformat(str(month)+"-01")
    last_three=[]
    for _ in range(3):
        last_three.append(reference.strftime("%Y-%m"))
        reference=(reference-timedelta(days=1)).replace(day=1)
    last_three.reverse()
    required=set(last_three)
    profit=defaultdict(lambda:defaultdict(lambda:Decimal("0")))
    names={int(m["id"]):str(m["nome"]) for m in method_catalog}
    for bet in bets:
        if (bet.get("tipo")!="metodo" or bet.get("metodo_id") is None
                or bet.get("status") not in ("green","red")
                or bet.get("lucro_prejuizo") is None):
            continue
        month_key=str(bet["data"])[:7]
        if month_key not in required:
            continue
        method_id=int(bet["metodo_id"])
        profit[method_id][month_key]+=Decimal(str(bet["lucro_prejuizo"]))
        if method_id not in names:
            names[method_id]=str(bet.get("metodo_nome") or "Método "+str(method_id))
    alerts=[]
    for method_id,balances in profit.items():
        if not all(balances.get(m,Decimal("0"))<0 for m in last_three):
            continue
        alerts.append({
            "metodo_id":method_id,
            "nome":names[method_id],
            "meses":[{"mes":m,"lucro_prejuizo":_brl(balances[m])} for m in last_three],
            "prejuizo_total":_brl(sum((balances[m] for m in last_three),Decimal("0"))),
        })
    return sorted(alerts,key=lambda item:(item["nome"].casefold(),item["metodo_id"]))


def _financial_group_results(bets):
    """Resultados auditáveis por método, liga e clube, sem inventar cotações.

    Executadas e ROI consideram apenas green/red. Entradas programadas e
    sem saldo são contabilizadas, mas não viram greens/reds ou lucro.
    Uma entrada é atribuída aos dois clubes do confronto; o total por
    clube não é somável entre equipes.
    """
    groups={"por_metodo":defaultdict(list),
            "por_liga":defaultdict(list),
            "por_clube":defaultdict(list)}
    for entry in bets:
        name=(str(entry.get("metodo_nome") or "Método sem nome").strip()
              if entry.get("tipo")=="metodo" else "Entrada manual")
        # O identificador identifica um método mesmo após renomeações;
        # as versões são agregadas sob seu ID estável.
        method_id=entry.get("metodo_id") if entry.get("tipo")=="metodo" else None
        method_key=("m",str(method_id)) if method_id is not None else ("n",name)
        groups["por_metodo"][method_key].append(entry)
        groups["por_liga"][str(entry.get("campeonato") or "Não informado")].append(entry)
        for club in {str(entry.get("mandante") or "Não informado"),
                     str(entry.get("visitante") or "Não informado")}:
            groups["por_clube"][club].append(entry)

    def summarize(rows):
        done=[r for r in rows if r["status"] in ("green","red")]
        stake=sum((Decimal(str(r["stake"])) for r in done),Decimal("0"))
        profit=sum((Decimal(str(r["lucro_prejuizo"])) for r in done),Decimal("0"))
        greens=sum(r["status"]=="green" for r in done)
        reds=sum(r["status"]=="red" for r in done)
        return {
            "entradas":len(rows),"executadas":len(done),
            "nao_executadas":sum(r["status"]=="sem_saldo" for r in rows),
            "pendentes":sum(r["status"]=="pendente" for r in rows),
            "greens":greens,"reds":reds,
            "win_rate":round(100*greens/len(done),2) if done else 0,
            "stake_executada":_brl(stake),
            "lucro_prejuizo":_brl(profit),
            "roi":round(float(profit/stake*100),2) if stake else 0,
        }

    results={}
    for group,values in groups.items():
        output=[]
        for key,rows in values.items():
            if group=="por_metodo" and isinstance(key,tuple):
                name=(rows[-1].get("metodo_nome") or "Método sem nome") if key[0]=="m" else key[1]
            else:
                name=key
            output.append({"nome":str(name),**summarize(rows)})
        output.sort(key=lambda row:(-row["entradas"],row["nome"].casefold()))
        results[group]=output
    return results


def _summary(bets,initial,fechamentos=None):
    """ROI = lucro líquido / soma das stakes (responsabilidades no Lay)."""
    def metric(rows):
        resolved=[r for r in rows if r["status"] in ("green","red")]
        pnl=sum((Decimal(r["lucro_prejuizo"]) for r in resolved),Decimal("0"))
        staked=sum((Decimal(r["stake"]) for r in resolved),Decimal("0"))
        green=sum(r["status"]=="green" for r in resolved)
        red=sum(r["status"]=="red" for r in resolved)
        skipped=sum(r["status"]=="sem_saldo" for r in rows)
        pending=sum(r["status"]=="pendente" for r in rows)
        return {"entradas":len(rows),"executadas":len(resolved),
                "nao_executadas":skipped,"greens":green,"reds":red,
                "pendentes":pending,
                "win_rate":round(100*green/(green+red),2) if green+red else 0,
                "lucro_prejuizo":_brl(pnl),
                "roi":round(float(pnl/staked*100),2) if staked else 0}
    monthly=defaultdict(list)
    for b in bets:
        monthly[str(b["data"])[:7]].append(b)
    closings={str(row["mes"]):row for row in (fechamentos or [])}
    for month in closings:
        monthly.setdefault(month,[])
    response=[]
    cumulative=Decimal(initial)
    for month,items in sorted(monthly.items()):
        result=metric(items)
        opening=cumulative
        closing_balance=opening+Decimal(str(result["lucro_prejuizo"]))
        closing=closings.get(month)
        if closing:
            opening=Decimal(closing["banca_base_inicio"])
            closing_balance=Decimal(closing["banca_fechamento"])
            cumulative=Decimal(closing["banca_base_seguinte"])
        else:
            cumulative=closing_balance
        breakdown=_financial_group_results(items)
        response.append({
            "mes":month,"banca_inicio":_brl(opening),
            "banca_fechamento":_brl(closing_balance),
            "aporte":_brl(closing["aporte"]) if closing else 0.0,
            "saque":_brl(closing["saque"]) if closing else 0.0,
            "banca_fim":_brl(cumulative),
            "fechado":bool(closing),
            **result,
            "por_estrategia":breakdown["por_metodo"],
            "por_liga":breakdown["por_liga"],"por_clube":breakdown["por_clube"],
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


def _closing_boundary(rounds):
    """Fechamento também nos meses sem partidas, ao atingir o último dia."""
    boundary,month=_monthly_boundary(rounds,0)
    if boundary:
        return True,month,False
    window=_window_at(rounds,0)
    if window and not window["jogos"] and window["limite"]==_month_end(window["limite"]):
        return True,window["limite"].strftime("%Y-%m"),True
    return False,None,False


def _default_stake(sess):
    if sess["stake_fixa"] is not None:
        return _brl(sess["stake_fixa"])
    base=Decimal(sess["banca_base_mes"] if sess.get("banca_base_mes") is not None else sess["banca_inicial"])
    # Não há percentual positivo de uma banca zerada/negativa; usar o mínimo
    # editável apenas para não bloquear o modo de simulação sem saldo.
    return _brl(max(CENTS,_rounded(base*Decimal(sess["gestao_pct"])/100)))


def estado(token):
    sess=_token_session(token)
    if sess is None:
        return {"iniciado":False}
    catalog=_catalog()
    current_cutoff=_date(sess.get("corte_atual") or sess["corte"])
    rounds=_rounds(current_cutoff,catalog)
    method_catalog=_methods()
    disabled=_disabled_methods(sess["id"])
    raw_games,games=_games_for_session(
        sess,catalog,rounds,methods=method_catalog,disabled=disabled)
    auto_count=_sync_live_entries(token,sess,raw_games,games)
    if auto_count:
        sess=dict(sess)
        sess["versao"]=int(sess["versao"])+1
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
    boundary,month,empty_closure=_closing_boundary(rounds)
    revealed=sess["fase"] in ("revelada","concluida")
    closure_access=revealed or (empty_closure and sess["fase"]=="aberta")
    fechamentos=_fechamentos(sess["id"])
    history=_summary(bets,sess["banca_inicial"],fechamentos)
    mes_fechado=any(str(row["mes"])==month for row in fechamentos) if month else False
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
    method_performance=(_method_monthly_table(
        bets,method_catalog,disabled,month)
        if closure_access and boundary and month else [])
    improvement_flags=(melhorias.sequencias_prejuizo(
        bets,month,method_catalog)
        if method_performance else {})
    for item in method_performance:
        flag=improvement_flags.get(item["metodo_id"])
        item.update({
            "melhoria_elegivel":bool(flag),
            "meses_prejuizo_consecutivos":flag["meses_prejuizo_consecutivos"] if flag else 0,
            "prejuizo_acumulado":flag["prejuizo_acumulado"] if flag else 0,
            "meses_prejuizo":flag["meses_prejuizo"] if flag else [],
        })
    return {
        "iniciado":True,
        "fase":sess["fase"],"versao":int(sess["versao"]),
        "corte":_date(sess["corte"]).isoformat(),
        "corte_atual":current_cutoff.isoformat(),
        "limite_janela":window["limite"].isoformat() if window else None,
        "banca_inicial":_brl(sess["banca_inicial"]),
        "banca_base_mes":_brl(sess["banca_base_mes"]),
        "mes_base":str(sess["mes_base"]),
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
        "entradas_mes":len(current),
        # Não descontamos stakes apenas programadas do saldo atual.
        "saldo_disponivel":_brl(sess["banca_atual"]),
        "exposicao_programada":_brl(sum(
            (Decimal(b["stake"]) for b in current if b["status"]=="pendente"),
            Decimal("0"))),
        "entradas_automaticas":auto_count,
        "entradas_automaticas_ao_vivo":sum(
            1 for bet in current
            if bet["tipo"]=="metodo" and bet.get("metodo_id") is not None
            and int(bet["metodo_id"])>=LIVE_METHOD_BASE
        ),
        "entradas_ao_vivo_mes":sum(
            1 for bet in current
            if bet["tipo"]=="metodo" and bet.get("metodo_id") is not None
            and int(bet["metodo_id"])>=LIVE_METHOD_BASE
        ),
        "mes_encerrado":month if closure_access and boundary else None,
        "metodos_fechamento":method_performance,
        "alertas_prejuizo_3_meses":_method_loss_streak_alerts(
            bets,method_catalog,month)
            if closure_access and boundary and month else [],
        "metodos_catalogo":[
            {"id":m["id"],"nome":m["nome"]}
            for m in sorted(method_catalog,key=lambda m:m["nome"].casefold())
        ],
        "metodos_desativados":[{
            "metodo_id":mid,"nome":info["nome"],"efetivo_desde":info["desde"]
        } for mid,info in sorted(disabled.items())],
        "fechamento_pendente":bool(closure_access and boundary and not mes_fechado),
        "fechamento_realizado":bool(closure_access and boundary and mes_fechado),
        "resumo_mensal":history,
        "pode_avancar":revealed and len(rounds)>1,
        "periodo_vazio":not bool(raw_games),
        "pode_pular_vazio":sess["fase"]=="aberta" and not raw_games and len(rounds)>1,
        "aviso":"Gameplay histórica: as entradas dos métodos pré-jogo e ao vivo são programadas automaticamente. Os jogos e placares só aparecem no resultado após finalizar o mês. Todas as entradas são liquidadas sem limite de saldo; a banca virtual pode ficar negativa. Odds históricas e preços Lay modelados não comprovam disponibilidade para execução real.",
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
                (token_hash,corte,corte_atual,banca_inicial,banca_base_mes,
                 mes_base,banca_atual,gestao_pct)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
              RETURNING id
            """,(_hash(new_token),cutoff,cutoff,initial,initial,
                 (cutoff+timedelta(days=1)).strftime("%Y-%m"),initial,percent))
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


def retirar_metodo(token,payload):
    """Retira um método desta gameplay imediatamente, preservando o histórico.

    A exclusão atômica das entradas pendentes impede que sejam liquidadas.
    As entradas já apuradas e os métodos do Nostradamus permanecem intactos.
    """
    if not isinstance(payload,dict) or type(payload.get("metodo_id")) is not int:
        raise ValueError("Selecione um método válido para retirar.")
    method_id=payload["metodo_id"]
    if method_id<=0:
        raise ValueError("Selecione um método válido para retirar.")
    method=next((m for m in _methods() if m["id"]==method_id),None)
    if method is None:
        raise ValueError("Este método não está mais cadastrado no Nostradamus.")
    with get_conn() as conn:
        with conn.cursor() as cur:
            sess=_lock(cur,token)
            cur.execute("""
                INSERT INTO galileu_private.metodos_desativados
                    (sessao_id,metodo_id,nome_metodo,efetivo_desde)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (sessao_id,metodo_id) DO NOTHING
                RETURNING metodo_id
            """,(sess["id"],method_id,method["nome"],str(sess["mes_base"])))
            if cur.fetchone() is None:
                raise ValueError("Este método já foi retirado do Galileu.")
            cur.execute("""
                DELETE FROM galileu_private.entradas
                WHERE sessao_id=%s AND metodo_id=%s
                  AND tipo='metodo' AND status='pendente'
                RETURNING id
            """,(sess["id"],method_id))
            canceladas=len(cur.fetchall())
            cur.execute("""
                UPDATE galileu_private.sessoes
                SET versao=versao+1,atualizado_em=now()
                WHERE id=%s
            """,(sess["id"],))
        conn.commit()
    return {
        "mensagem":"Método retirado do Galileu. Não haverá novas entradas com ele.",
        "metodo_id":method_id,
        "entradas_canceladas":canceladas,
    }


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
            # Modo de simulação: toda entrada válida será liquidada ao fim
            # do mês, mesmo quando sua stake supera a banca virtual.
            if kind=="metodo":
                method_id=payload.get("metodo_id")
                if type(method_id) is not int:
                    raise ValueError("Selecione um método validado.")
                cur.execute("""
                    SELECT efetivo_desde FROM galileu_private.metodos_desativados
                    WHERE sessao_id=%s AND metodo_id=%s
                """,(sess["id"],method_id))
                disabled_row=cur.fetchone()
                if disabled_row:
                    raise ValueError("Método retirado da gameplay do Galileu. Atualize a rodada.")
                # A confirmação só precisa revalidar o método selecionado,
                # em vez de recalcular TODOS os métodos a cada entrada.
                selected=next((m for m in _methods() if m["id"]==method_id),None)
                if selected is None or (
                    selected["ligas"] and game["campeonato_id"] not in selected["ligas"]
                ):
                    raise ValueError("Método não validado para este confronto.")
                if payload.get("metodo_versao")!=selected["versao"]:
                    raise ValueError("O método foi alterado. Atualize a rodada.")
                if selected.get("tipo")=="ao_vivo":
                    method=next(iter(_live_offers(
                        [game],[selected],catalog
                    ).get(gid,[])),None)
                else:
                    hist=_history(catalog)
                    h,_=_team_stats(hist,game,game["casa_id"],selected["jogos"])
                    a,_=_team_stats(hist,game,game["fora_id"],selected["jogos"])
                    method=next(iter(_matched(game,h,a,[selected])),None)
                if method is None:
                    raise ValueError("Método não validado para este confronto.")
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
                  RETURNING id
                """,(sess["id"],gid,sess["indice_rodada"],kind,method_id,version,
                     name,market,offer["odd"],stake,offer["estimada"],offer["favorito_casa"]))
                created=cur.fetchone()
            except errors.UniqueViolation:
                raise ValueError("Você já fez uma entrada neste método para este jogo.") from None
            cur.execute("""
              UPDATE galileu_private.sessoes
              SET versao=versao+1,atualizado_em=now() WHERE id=%s
            """,(sess["id"],))
        conn.commit()
    # A entrada já está persistida. A UI atualiza somente o card e o contador:
    # não precisa executar /estado (catálogo completo + todos os métodos).
    return {
        "mensagem":"Entrada virtual programada e salva. Será liquidada ao finalizar o mês.",
        "versao":int(sess["versao"])+1,
        "entrada":{
            "id":int(created["id"]),
            "tipo":kind,
            "metodo_id":method_id,
            "metodo":name,
            "mercado":market,
            "odd":float(offer["odd"]),
            "stake":_brl(stake),
            "status":"pendente",
            "lucro_prejuizo":None,
        },
    }


def registrar_metodos_em_lote(token,payload):
    """Confirma vários métodos da rodada de forma atômica.

    Não aceita odds, nomes de clubes ou preços vindos do navegador.
    Revalida a correspondência de cada método no servidor, bloqueia a sessão
    durante a operação e usa um único INSERT para todas as entradas.
    """
    if not isinstance(payload,dict):
        raise ValueError("Informe as entradas a confirmar.")
    stake=_money(payload.get("stake"),"Stake")
    expected_version=payload.get("versao")
    if type(expected_version) is not int:
        raise ValueError("Atualize a rodada antes de confirmar as entradas.")
    requested=payload.get("selecoes")
    if not isinstance(requested,list) or not requested or len(requested)>5000:
        raise ValueError("Selecione de 1 a 5000 entradas válidas para o mês.")
    selections=[]
    seen=set()
    for item in requested:
        if not isinstance(item,dict):
            raise ValueError("Seleção de método inválida.")
        gid=item.get("jogo_id")
        mid=item.get("metodo_id")
        ver=item.get("metodo_versao")
        if type(gid) is not int or gid<=0 or type(mid) is not int or mid<=0 or type(ver) is not int:
            raise ValueError("Seleção de jogo ou método inválida.")
        key=(gid,mid)
        if key in seen:
            raise ValueError("A mesma combinação de jogo e método foi enviada mais de uma vez.")
        seen.add(key)
        selections.append((gid,mid,ver))

    catalog=_catalog()
    with get_conn() as conn:
        with conn.cursor() as cur:
            sess=_lock(cur,token)
            if sess["fase"]!="aberta":
                raise ValueError("Finalize a rodada atual antes de começar novas entradas.")
            if int(sess["versao"])!=expected_version:
                raise ValueError("A rodada foi modificada em outra aba. Recarregue para conferir as entradas.")
            rounds=_rounds(_date(sess.get("corte_atual") or sess["corte"]),catalog)
            games={int(g["id"]):g for g in _round_at(rounds,0)}
            if not games:
                raise ValueError("Não há jogos nesta rodada.")
            methods={m["id"]:m for m in _methods()}
            cur.execute("""
              SELECT metodo_id,efetivo_desde
              FROM galileu_private.metodos_desativados
              WHERE sessao_id=%s
            """,(sess["id"],))
            disabled_lote={
                int(r["metodo_id"]):{"desde":str(r["efetivo_desde"])}
                for r in cur.fetchall()
            }
            cur.execute("""
              SELECT jogo_id FROM galileu_private.jogos_finalizados
              WHERE sessao_id=%s AND indice_rodada=%s
            """,(sess["id"],sess["indice_rodada"]))
            closed={int(r["jogo_id"]) for r in cur.fetchall()}
            cur.execute("""
              SELECT jogo_id,metodo_id FROM galileu_private.entradas
              WHERE sessao_id=%s AND indice_rodada=%s AND tipo='metodo'
            """,(sess["id"],sess["indice_rodada"]))
            previously_used={(int(r["jogo_id"]),int(r["metodo_id"])) for r in cur.fetchall()}
            # Entradas são programadas para o mês todo, sem limite de
            # saldo. Removemos apenas os métodos já inseridos, não os manuais.
            remaining=[(gid,mid,ver) for gid,mid,ver in selections
                       if (gid,mid) not in previously_used]
            if not remaining:
                raise ValueError("Todas as entradas desses métodos já foram registradas.")
            # Sem bloqueio por banca: qualquer stake positiva válida pode
            # ser programada, independentemente do total das entradas.
            histories=_history(catalog)
            prepared=[]
            stat_cache={}
            for gid,mid,ver in remaining:
                game=games.get(gid)
                method=methods.get(mid)
                if game is None or gid in closed:
                    raise ValueError("Um dos jogos não está mais disponível. Atualize a rodada.")
                if method is None or method["versao"]!=ver or (
                    method["ligas"] and game["campeonato_id"] not in method["ligas"]
                ) or _is_disabled(mid,game["data"],disabled_lote):
                    raise ValueError("Um dos métodos foi alterado. Atualize a rodada.")
                if method.get("tipo")=="ao_vivo":
                    validated=_live_offers([game],[method],catalog).get(gid,[])
                else:
                    cache_key=(gid,method["jogos"])
                    if cache_key not in stat_cache:
                        home,_=_team_stats(histories,game,game["casa_id"],method["jogos"])
                        away,_=_team_stats(histories,game,game["fora_id"],method["jogos"])
                        stat_cache[cache_key]=(home,away)
                    home,away=stat_cache[cache_key]
                    validated=_matched(game,home,away,[method])
                if not validated:
                    raise ValueError("Um dos métodos não atende mais às regras. Atualize a rodada.")
                matched=validated[0]
                offer=matched["mercado"]
                prepared.append((
                    sess["id"],gid,sess["indice_rodada"],"metodo",
                    mid,ver,method["nome"],method["objetivo"],offer["odd"],
                    stake,offer["estimada"],offer["favorito_casa"],
                ))
            # Único INSERT transacional, sem confirmações parciais.
            # O índice único parcial no banco impede repetir método/jogo.
            from psycopg2.extras import execute_values
            try:
                execute_values(cur,"""
                  INSERT INTO galileu_private.entradas
                    (sessao_id,jogo_id,indice_rodada,tipo,metodo_id,metodo_versao,
                     metodo_nome,mercado,odd,stake,cotacao_estimada,favorito_casa)
                  VALUES %s
                  RETURNING id,jogo_id,tipo,metodo_id,metodo_nome,mercado,odd,stake
                """,prepared,page_size=len(prepared))
                saved=cur.fetchall()
            except errors.UniqueViolation:
                raise ValueError(
                    "Um dos métodos já possui entrada neste jogo. Atualize a rodada."
                ) from None
            if len(saved)!=len(prepared):
                raise ValueError("Não foi possível confirmar todas as entradas.")
            cur.execute("""
              UPDATE galileu_private.sessoes
              SET versao=versao+1,atualizado_em=now() WHERE id=%s
            """,(sess["id"],))
        conn.commit()
    return {
        "mensagem":str(len(saved))+" entradas virtuais programadas para o mês. Todas serão liquidadas no fechamento.",
        "versao":int(sess["versao"])+1,
        "ignoradas":len(selections)-len(saved),
        "entradas":[{
            "id":int(row["id"]),
            "jogo_id":int(row["jogo_id"]),
            "tipo":row["tipo"],
            "metodo_id":int(row["metodo_id"]),
            "metodo":row["metodo_nome"],
            "mercado":row["mercado"],
            "odd":float(row["odd"]),
            "stake":_brl(row["stake"]),
            "status":"pendente",
            "lucro_prejuizo":None,
        } for row in saved],
    }


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


def _liquidar_entradas_por_data(entries, by_id, banca_inicial):
    """Liquida todas as entradas, sem limite de saldo ou priorização por stake.

    A banca virtual é meramente contábil e pode tornar-se negativa. Jogos
    do mesmo dia não precisam competir pela banca: todos serão liquidados
    usando odds, placares e stakes registradas, em ordem determinística.
    """
    ordered=[]
    for entry in entries:
        game=by_id.get(int(entry["jogo_id"]))
        if game is None:
            raise ValueError("Uma entrada não pertence à rodada atual.")
        ordered.append((_date(game["data"]),int(entry["id"]),entry,game))
    bank=Decimal(banca_inicial)
    updates=[]
    for _,entry_id,entry,game in sorted(ordered,key=lambda x:(x[0],x[1])):
        status,pnl=_settlement(
            entry["mercado"],entry["favorito_casa"],
            game["gols_casa"],game["gols_fora"],
            entry["odd"],Decimal(entry["stake"]))
        amount=_rounded(pnl)
        updates.append((entry_id,status,amount))
        bank=_rounded(bank+amount)
    return updates,bank


def finalizar(token):
    catalog=_catalog()
    sess=_token_session(token)
    if sess and sess["fase"]=="aberta":
        methods=_methods()
        disabled=_disabled_methods(sess["id"])
        rounds=_rounds(_date(sess.get("corte_atual") or sess["corte"]),catalog)
        raw,public=_games_for_session(
            sess,catalog,rounds,methods=methods,disabled=disabled)
        _sync_live_entries(token,sess,raw,public)
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
            updates,new_bank=_liquidar_entradas_por_data(
                entries,by_id,sess["banca_atual"])
            for entry_id,status,amount in updates:
                cur.execute("""
                  UPDATE galileu_private.entradas
                  SET status=%s,lucro_prejuizo=%s,finalizada_em=now()
                  WHERE id=%s
                """,(status,amount,entry_id))
            cur.execute("""
              UPDATE galileu_private.sessoes
              SET banca_atual=%s,fase='revelada',versao=versao+1,atualizado_em=now()
              WHERE id=%s
            """,(_rounded(new_bank),sess["id"]))
        conn.commit()
    return {
        "mensagem":"Mês finalizado. Todas as entradas programadas foram liquidadas, sem limite de saldo.",
        "executadas":sum(status in ("green","red") for _,status,_ in updates),
        "sem_saldo":sum(status=="sem_saldo" for _,status,_ in updates),
        "banca_final":_brl(new_bank),
    }


def fechar_mes(token,payload):
    """Fecha o mês uma única vez e registra movimentações em uma transação."""
    if not isinstance(payload,dict):
        raise ValueError("Informe aporte, saque e ajuste de stake.")
    for key in ("fazer_aporte","fazer_saque","alterar_stake"):
        if type(payload.get(key)) is not bool:
            raise ValueError("Responda Sim ou Não para aporte, saque e stake.")
    to_disable=payload.get("retirar_metodos",[])
    if not isinstance(to_disable,list) or len(to_disable)>500 or any(
        type(mid) is not int or mid<=0 for mid in to_disable
    ) or len(to_disable)!=len(set(to_disable)):
        raise ValueError("Informe uma lista válida, sem repetições, dos métodos a retirar.")
    aporte=_money(payload.get("aporte"),"Aporte") if payload["fazer_aporte"] else Decimal("0")
    saque=_money(payload.get("saque"),"Saque") if payload["fazer_saque"] else Decimal("0")
    mode=payload.get("tipo_stake") if payload["alterar_stake"] else "manter"
    if mode=="percentual":
        rate=_pct(payload.get("valor_stake"))
        fixed=None
    elif mode=="fixo":
        rate=None
        fixed=_money(payload.get("valor_stake"),"Stake fixa")
    elif mode=="manter":
        rate=None
        fixed=None
    else:
        raise ValueError("Informe a nova stake como percentual ou valor financeiro.")
    catalog=_catalog()
    method_names={m["id"]:m["nome"] for m in _methods()} if to_disable else {}
    if any(mid not in method_names for mid in to_disable):
        raise ValueError("Um dos métodos selecionados não está mais cadastrado no Nostradamus.")
    with get_conn() as conn:
        with conn.cursor() as cur:
            sess=_lock(cur,token)
            rounds=_rounds(_date(sess.get("corte_atual") or sess["corte"]),catalog)
            boundary,month,empty_closure=_closing_boundary(rounds)
            if sess["fase"]!="revelada" and not (
                sess["fase"]=="aberta" and empty_closure
            ):
                raise ValueError("Finalize a rodada antes de fechar o mês.")
            if not boundary or not month:
                raise ValueError("Este período não representa o fechamento do mês.")
            if month!=str(sess["mes_base"]):
                raise ValueError("O mês da sessão está diferente do calendário. Recarregue a página.")
            cur.execute("""
              SELECT 1 FROM galileu_private.fechamentos_mensais
              WHERE sessao_id=%s AND mes=%s
            """,(sess["id"],month))
            if cur.fetchone():
                raise ValueError("Este mês já foi fechado e não pode ser movimentado novamente.")
            closing=Decimal(sess["banca_atual"])
            after_deposit=closing+aporte
            if saque>max(Decimal("0"),after_deposit):
                raise ValueError("Saque maior que o saldo positivo disponível, incluindo o aporte.")
            next_base=_rounded(after_deposit-saque)
            next_rate=rate if rate is not None else Decimal(sess["gestao_pct"])
            next_fixed=(fixed if mode=="fixo" else None) if payload["alterar_stake"] \
                else (Decimal(sess["stake_fixa"]) if sess["stake_fixa"] is not None else None)
            # Stake fixa é um parâmetro da simulação, sem limite de banca.
            next_month=(date(int(month[:4]),int(month[5:7]),1)+timedelta(days=32)).replace(day=1).strftime("%Y-%m")
            for mid in to_disable:
                cur.execute("""
                    INSERT INTO galileu_private.metodos_desativados
                      (sessao_id,metodo_id,nome_metodo,efetivo_desde)
                    VALUES (%s,%s,%s,%s)
                    ON CONFLICT (sessao_id,metodo_id) DO NOTHING
                """,(sess["id"],mid,method_names[mid],next_month))
            cur.execute("""
              INSERT INTO galileu_private.fechamentos_mensais
                (sessao_id,mes,indice_rodada,banca_base_inicio,banca_fechamento,
                 aporte,saque,banca_base_seguinte,gestao_pct_antes,gestao_pct_depois,
                 stake_fixa_antes,stake_fixa_depois)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,(
                sess["id"],month,sess["indice_rodada"],
                sess["banca_base_mes"],closing,aporte,saque,next_base,
                sess["gestao_pct"],next_rate,sess["stake_fixa"],next_fixed,
            ))
            cursor_bank=closing
            def movimento(kind,value,bank_before,bank_after,pct_before,pct_after,
                          fixed_before,fixed_after):
                cur.execute("""
                    INSERT INTO galileu_private.movimentacoes
                    (sessao_id,mes_referencia,tipo,valor,banca_antes,banca_depois,
                     gestao_pct_antes,gestao_pct_depois,
                     stake_fixa_antes,stake_fixa_depois)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,(sess["id"],month,kind,value,bank_before,bank_after,
                     pct_before,pct_after,fixed_before,fixed_after))
            if aporte:
                movimento("aporte",aporte,cursor_bank,cursor_bank+aporte,
                          sess["gestao_pct"],sess["gestao_pct"],
                          sess["stake_fixa"],sess["stake_fixa"])
                cursor_bank+=aporte
            if saque:
                movimento("saque",saque,cursor_bank,cursor_bank-saque,
                          sess["gestao_pct"],sess["gestao_pct"],
                          sess["stake_fixa"],sess["stake_fixa"])
                cursor_bank-=saque
            if payload["alterar_stake"]:
                movimento("reajuste_stake",Decimal("0"),cursor_bank,cursor_bank,
                          sess["gestao_pct"],next_rate,sess["stake_fixa"],next_fixed)
            movimento("virada_mes",Decimal("0"),cursor_bank,cursor_bank,
                      sess["gestao_pct"],next_rate,sess["stake_fixa"],next_fixed)
            cur.execute("""
              UPDATE galileu_private.sessoes SET
                banca_atual=%s,banca_base_mes=%s,mes_base=%s,
                gestao_pct=%s,stake_fixa=%s,
                versao=versao+1,atualizado_em=now()
              WHERE id=%s
            """,(next_base,next_base,next_month,next_rate,next_fixed,sess["id"]))
        conn.commit()
    return {
        "mensagem":"Mês fechado. Banca-base do próximo mês atualizada e movimentos registrados.",
        "mes":month,
        "banca_fechamento":_brl(closing),
        "aporte":_brl(aporte),"saque":_brl(saque),
        "banca_base_seguinte":_brl(next_base),
        "metodos_retirados":len(to_disable),
    }


def proxima(token):
    catalog=_catalog()
    with get_conn() as conn:
        with conn.cursor() as cur:
            sess=_lock(cur,token)
            current_cutoff=_date(sess.get("corte_atual") or sess["corte"])
            rounds=_rounds(current_cutoff,catalog)
            current=_window_at(rounds,0)
            boundary,month,empty_closure=_closing_boundary(rounds)
            if sess["fase"]=="revelada" or (
                sess["fase"]=="aberta" and current and not current["jogos"]
            ):
                if boundary:
                    cur.execute("""
                        SELECT 1 FROM galileu_private.fechamentos_mensais
                        WHERE sessao_id=%s AND mes=%s
                    """,(sess["id"],month))
                    if not cur.fetchone():
                        raise ValueError("Antes de avançar, conclua o fechamento mensal: aporte, saque e stake.")
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
            # Corte atualizado = último dia do mês, mesmo se não houver jogos.
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
    raise ValueError(
        "Use o fechamento mensal para registrar mudanças de stake no histórico financeiro."
    )


def reiniciar(token):
    digest=_hash(token)
    if digest:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM galileu_private.sessoes WHERE token_hash=%s",(digest,))
            conn.commit()
    return {"mensagem":"Progresso reiniciado. Configure uma nova banca para começar."}
