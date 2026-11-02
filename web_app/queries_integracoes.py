"""Prévia segura e importação atômica de CSV ou JSON de odds em um servidor local.

IMPORTANTE: endpoint sem autenticação destina-se apenas a loopback. A chave nunca
é persistida, nem na prévia em memória, nem nas tabelas de odds.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit, urljoin, urlencode
from urllib.request import Request, build_opener, HTTPSHandler, HTTPHandler, HTTPRedirectHandler
from urllib.error import URLError, HTTPError
from ipaddress import ip_address
from collections import OrderedDict
import csv
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import io
import json
import os
import re
import secrets
import socket
import time

from psycopg2.extras import Json
from db import fetch_all, get_conn
from queries_vinculos import _suggest, key

_PREVIEWS={}
LIMIT_BYTES=16_000_000
LIMIT_ROWS=5000
TTL=1200
SAFE_KEY=re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")
PRIVATE_FIELD=re.compile(r"(api[_-]?key|token|password|secret|authorization|cookie)",re.I)
HOME_KEYS=("Home","Home_Team","home_team","homeTeam","home_name","homeName","home","mandante","team1","time_casa","teams.home.name","participants.home.name","competitors.home.name")
AWAY_KEYS=("Away","Away_Team","away_team","awayTeam","away_name","awayName","away","visitante","team2","time_fora","teams.away.name","participants.away.name","competitors.away.name")
ID_KEYS=("Match_ID","id","match_id","event_id","fixture_id","game_id","matchId")
DATE_KEYS=("Date","date","start_time","startTime","commence_time","kickoff","utcDate","data","datetime")

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def _pick(row,keys):
    for k in keys:
        val=row
        for part in k.split("."):
            val=val.get(part) if isinstance(val,dict) else None
        if isinstance(val,dict):
            val=val.get("name") or val.get("nome") or val.get("shortName")
        if val is not None and str(val).strip():return str(val).strip()
    return None

def _rows(payload):
    if isinstance(payload,list):return payload
    if not isinstance(payload,dict):raise ValueError("API deve retornar JSON de partidas.")
    for k in ("matches","fixtures","events","games","results","data","response","items","odds"):
        inner=payload.get(k)
        if isinstance(inner,list):return inner
        if isinstance(inner,dict):
            try:return _rows(inner)
            except ValueError:pass
    # Um evento por resposta.
    if _pick(payload,HOME_KEYS) and _pick(payload,AWAY_KEYS):return [payload]
    raise ValueError("Não encontrei uma lista de partidas na resposta da API.")

def _parse_response(raw, content_type=""):
    """Interpreta CSV da FutPythonTrader ou listas JSON de outras fontes."""
    try:
        decoded=raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("A API não retornou UTF-8 válido.") from None
    if "json" in content_type or decoded.lstrip().startswith(("{","[")):
        try:
            return _rows(json.loads(decoded))
        except (ValueError,TypeError):
            raise ValueError("Resposta JSON inválida ou sem partidas.") from None
    if decoded.lstrip().startswith("<"):
        raise ValueError("A API retornou HTML, não CSV ou JSON. Confira a chave e a rota.")
    try:
        reader=csv.DictReader(io.StringIO(decoded, newline=""))
        if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)):
            raise ValueError("CSV sem cabeçalhos válidos ou com colunas repetidas.")
        if len(reader.fieldnames)>300:
            raise ValueError("A API retornou mais de 300 colunas.")
        rows=[]
        for row in reader:
            if None in row:
                raise ValueError("CSV com campos extras em uma das linhas.")
            rows.append(row)
            if len(rows)>LIMIT_ROWS:
                raise ValueError("CSV excede 5.000 partidas por importação.")
    except csv.Error:
        raise ValueError("CSV inválido retornado pela API.") from None
    if rows and not (_pick(rows[0],HOME_KEYS) and _pick(rows[0],AWAY_KEYS)):
        raise ValueError("Não encontrei as colunas Home e Away no CSV.")
    return rows

def _parse_game_date(row):
    value=_pick(row,DATE_KEYS)
    if not value:return None
    for fmt in ("%d/%m/%Y","%d-%m-%Y","%Y/%m/%d"):
        try:return datetime.strptime(value,fmt).isoformat()
        except ValueError:pass
    try:return datetime.fromisoformat(value.replace("Z","+00:00")).isoformat()
    except ValueError:return None

def _metadata(path):
    parts=[p for p in path.split("/") if p]
    year=next((p for p in reversed(parts) if re.fullmatch(r"20\d{2}(?:[-/]20\d{2})?",p)),None)
    country=next((p.title() for p in parts if p.lower() in
                  ("brazil","brasil","england","spain","italy","germany","france")),None)
    country={"Brazil":"Brasil","England":"Inglaterra","Spain":"Espanha",
             "Italy":"Itália","Germany":"Alemanha","France":"França"}.get(country,country)
    league=parts[-2].replace("-"," ").title() if len(parts)>=2 and year else None
    return year,league,country

def _url(base,path):
    base=base.strip()
    p=urlsplit(base)
    host=p.hostname
    allowed={"futpythontrader.com.br"} | {h.strip().lower() for h in os.getenv("ODDS_API_ALLOWED_HOSTS","").split(",") if h.strip()}
    if not host or p.scheme!="https" or not allowed or host.lower() not in allowed:
        raise ValueError("Configure ODDS_API_ALLOWED_HOSTS no .env e informe base HTTPS autorizada.")
    if p.username or p.password or p.query or p.fragment or p.port not in (None,443):
        raise ValueError("URL base contém credenciais, porta ou parâmetros não permitidos.")
    if not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path or "\\" in path or ".." in path:
        raise ValueError("Use somente caminho relativo absoluto da API, sem parâmetros ou credenciais.")
    # Bloquear endpoints internos, loopback, rede privada e resolvedores inesperados.
    try:addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    except socket.gaierror:raise ValueError("Host da API não pôde ser resolvido.") from None
    if not addresses or any(not ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("API não pode apontar para localhost ou rede privada.")
    return urljoin(f"https://{host}/",path.lstrip("/")),host.lower()

# Normalização do país digitado e dos nomes persistidos em public.paises.
PAIS_EQUIVALENCIAS={
    "br":"brasil","bra":"brasil","brazil":"brasil","brasil":"brasil",
    "england":"inglaterra","inglaterra":"inglaterra",
    "spain":"espanha","espana":"espanha","espanha":"espanha",
    "germany":"alemanha","deutschland":"alemanha","alemanha":"alemanha",
    "italy":"italia","italia":"italia",
    "france":"franca","franca":"franca",
    "argentina":"argentina","portugal":"portugal",
    "united states":"estados unidos","usa":"estados unidos",
}

def _pais_normalizado(nome):
    valor=key(nome)
    return PAIS_EQUIVALENCIAS.get(valor,valor)

def _catalogo_pais(pais):
    """Só exibe clubes de public.clubes do país escolhido."""
    if not isinstance(pais,str) or not 1<=len(pais.strip())<=100:
        return []
    todos=fetch_all("""SELECT c.id,c.clube,p.nome AS pais
                         FROM public.clubes c
                         JOIN public.paises p ON p.id=c.pais_id
                         ORDER BY c.clube""")
    alvo=_pais_normalizado(pais)
    return [c for c in todos if _pais_normalizado(c["pais"])==alvo]

def _clubes_preview(rows,pais):
    catalogo=_catalogo_pais(pais)
    nomes=sorted(set(n for row in rows
        for n in (_pick(row,HOME_KEYS),_pick(row,AWAY_KEYS)) if n))
    por_nome={}
    for c in catalogo:
        por_nome.setdefault(key(c["clube"]),[]).append(c)
    resultados=[]
    for nome in nomes:
        iguais=por_nome.get(key(nome),[])
        igual=iguais[0] if len(iguais)==1 else None
        resultados.append({"original":nome,
                           "padronizado":igual["clube"] if igual else nome,
                           "clube_id":igual["id"] if igual else None,
                           "sugestoes":_suggest(nome,catalogo)})
    return {"catalogo":catalogo,"clubes":resultados,"pais":pais}

def revisar_clubes(payload):
    """Atualiza as opções após o usuário alterar o país da importação."""
    if not isinstance(payload,dict):
        raise ValueError("Requisição inválida.")
    token=payload.get("preview_id")
    pais=payload.get("pais")
    if not isinstance(token,str) or token not in _PREVIEWS:
        raise ValueError("Prévia expirada. Consulte a API novamente.")
    prev=_PREVIEWS[token]
    if time.monotonic()-prev["criado"]>TTL:
        _PREVIEWS.pop(token,None)
        raise ValueError("Prévia expirada. Consulte a API novamente.")
    if not isinstance(pais,str) or not 1<=len(pais.strip())<=100:
        raise ValueError("Informe um país válido.")
    return _clubes_preview(prev["rows"],pais.strip())

# Colunas da partida e mercados de odds disponíveis no CSV do provedor.
# Odds simuladas são SEMPRE identificadas como simuladas: não são cotações Betfair.
MATCH_COLUMNS={"Match_ID","Country","Season","Div","League","Date","Round",
               "Home","Away","Home_Score","Away_Score"}
ODDS_COLUMN=re.compile(
    r"^(?:Odd_[12X]_(?:FT|HT)|Over_(?:FT|HT)_\d+_\d+|"
    r"Under_(?:FT|HT)_\d+_\d+|BTTS_(?:Yes|No)|DC_(?:1X|12|X2)|"
    r"CS_\d+_\d+|AH_(?:Home|Away)_(?:neg|pos)_\d+(?:_\d+)?|"
    r"EH_(?:Home|Draw|Away)_(?:neg_)?\d+|odds?)$",
    re.I
)
FAVORITE_BOOKMAKERS=("bet365","pinnacle","pinacle")

def _is_odd_column(column):
    return bool(ODDS_COLUMN.fullmatch(column))

def _default_columns(columns):
    selected=[c for c in columns if c in MATCH_COLUMNS or _is_odd_column(c)]
    return selected or list(columns)

def _last_columns():
    # Persistência já existente no banco: o último lote confirmado tem seu
    # conjunto de colunas gravado em odds_importacoes.colunas.
    recent=fetch_all("""SELECT colunas FROM public.odds_importacoes
                        ORDER BY id DESC LIMIT 1""")
    if recent and isinstance(recent[0].get("colunas"),list):
        return [c for c in recent[0]["colunas"] if isinstance(c,str)]
    return None

def _bookmaker_column(odd):
    if odd.startswith("Odd_"):
        return "Bookie_1X2_"+odd.rsplit("_",1)[-1]
    if odd.startswith(("Over_","Under_")):
        p=odd.split("_")
        if len(p)==4:
            return "Bookie_OU_"+p[1]+"_"+p[2]+"_"+p[3]
    if odd.startswith("BTTS_"):
        return "Bookie_BTTS"
    if odd.startswith("DC_"):
        return "Bookie_DC"
    if odd.startswith(("CS_","AH_","EH_")):
        return "Bookie_"+odd if odd.startswith("CS_") else (
            "Bookie_"+odd.replace("AH_Home_","AH_").replace("AH_Away_","AH_")
                      .replace("EH_Home_","EH_").replace("EH_Draw_","EH_")
                      .replace("EH_Away_","EH_"))
    return None

# Escada válida do Exchange. Um tick acima do Back é apenas uma HIPÓTESE
# de spread mínimo e não representa o melhor Lay negociável na Betfair.
TICK_BANDS=[
    (Decimal("2"),Decimal("0.01")),
    (Decimal("3"),Decimal("0.02")),
    (Decimal("4"),Decimal("0.05")),
    (Decimal("6"),Decimal("0.10")),
    (Decimal("10"),Decimal("0.20")),
    (Decimal("20"),Decimal("0.50")),
    (Decimal("30"),Decimal("1")),
    (Decimal("50"),Decimal("2")),
    (Decimal("100"),Decimal("5")),
    (Decimal("1000"),Decimal("10"))
]

def _simulated_lay(back,asian=False):
    try:
        price=Decimal(str(back).replace(",","."))
    except (InvalidOperation,ValueError,TypeError):
        return None
    if not price.is_finite() or not Decimal("1.01")<=price<Decimal("1000"):
        return None
    if asian:
        result=(price/Decimal("0.01")).to_integral_value(rounding=ROUND_FLOOR)*Decimal("0.01")+Decimal("0.01")
        return float(result) if result<=1000 else None
    for upper,step in TICK_BANDS:
        if price < upper:
            # Níveis são ancorados nas fronteiras da escada.
            base={Decimal("2"):Decimal("1"),Decimal("3"):Decimal("2"),
                  Decimal("4"):Decimal("3"),Decimal("6"):Decimal("4"),
                  Decimal("10"):Decimal("6"),Decimal("20"):Decimal("10"),
                  Decimal("30"):Decimal("20"),Decimal("50"):Decimal("30"),
                  Decimal("100"):Decimal("50"),Decimal("1000"):Decimal("100")}[upper]
            n=((price-base)/step).to_integral_value(rounding=ROUND_FLOOR)+1
            candidate=base+n*step
            return float(candidate) if candidate<=1000 else None
    return None

def _enriquecer_lay(row,columns):
    selected={c:row.get(c) for c in columns}
    bookmakers={}
    generated=0
    for c in columns:
        if not _is_odd_column(c):
            continue
        bookie_column=_bookmaker_column(c)
        bookie=str(row.get(bookie_column) or "").strip() if bookie_column else ""
        if bookie:
            normalized=key(bookie).replace(" ","")
            bookmakers[c]={"bookmaker":bookie,
                            "preferencial":any(k in normalized for k in FAVORITE_BOOKMAKERS)}
        lay=_simulated_lay(row.get(c),asian=c.startswith("AH_"))
        if lay is not None:
            selected["Lay_Simulado_"+c]=lay
            generated+=1
    if generated:
        selected["_metodo_lay_simulado"]={
            "descricao":"Aproximacao ilustrativa de 1 tick acima do Back; nao e cotacao real nem executavel.",
            "spread":"1 tick de escada Betfair","comissao_pct":4.5,
            "precificacao_real":False,"liquidez_verificada":False,
            "quantidade":generated
        }
    if bookmakers:
        selected["_bookmakers_das_odds"]=bookmakers
    return selected

def preview(payload):
    if not isinstance(payload,dict):raise ValueError("Requisição inválida.")
    base=str(payload.get("base",""))
    path=str(payload.get("caminho",""))
    url,host=_url(base,path)
    api_key=payload.get("chave","")
    header=payload.get("cabecalho","api_key")
    if header not in ("api_key","x-api-key","Authorization"):
        raise ValueError("Método de autenticação inválido.")
    if not isinstance(api_key,str) or len(api_key)>1024 or "\n" in api_key or "\r" in api_key:
        raise ValueError("Chave de API inválida.")
    headers={"Accept":"text/csv, application/json","User-Agent":"DadosFutebolImporter/1.1"}
    if api_key:
        if header=="api_key":
            # O provedor recebe a chave na query string; não a registramos.
            url += "?" + urlencode({"api_key":api_key})
        else:
            headers[header]="Bearer "+api_key if header=="Authorization" else api_key
    req=Request(url,headers=headers,method="GET")
    opener=build_opener(HTTPSHandler(),_NoRedirect())
    try:
        with opener.open(req,timeout=30) as response:
            content_type=(response.headers.get("Content-Type") or "").lower()
            raw=response.read(LIMIT_BYTES+1)
            if len(raw)>LIMIT_BYTES:raise ValueError("Resposta excede o limite de 16 MB.")
    except HTTPError as exc:
        if exc.code in (401,403):
            raise ValueError("Chave de API inválida ou acesso não autorizado.") from None
        raise ValueError(f"Falha na API (HTTP {exc.code}). Verifique o caminho.") from None
    except (URLError,TimeoutError,OSError):
        raise ValueError("Falha ao consultar a API. Confira host, chave e caminho.") from None
    rows=_parse_response(raw,content_type)
    if not rows or len(rows)>LIMIT_ROWS:
        raise ValueError("Prévia aceita entre 1 e 5.000 partidas por importação.")
    if any(not isinstance(row,dict) for row in rows):
        raise ValueError("Cada partida deve conter colunas identificáveis.")
    columns=list(OrderedDict.fromkeys(k for row in rows for k in row
        if SAFE_KEY.fullmatch(k) and not PRIVATE_FIELD.search(k)))
    if len(columns)>300:raise ValueError("A API retornou mais de 300 colunas.")
    season,league,country=_metadata(path)
    revisao=_clubes_preview(rows,country)
    saved=_last_columns()
    selected=[c for c in saved if c in columns] if saved is not None else _default_columns(columns)
    if not selected:
        selected=_default_columns(columns)
    now=time.monotonic()
    for k,v in list(_PREVIEWS.items()):
        if now-v["criado"]>TTL:_PREVIEWS.pop(k,None)
    token=secrets.token_urlsafe(24)
    _PREVIEWS[token]={"rows":rows,"columns":columns,"criado":now,
                       "host":host,"path":path,"season":season,"league":league,"country":country}
    return {"preview_id":token,"colunas":columns,"colunas_marcadas":selected,
            "selecao_origem":"ultima_importacao" if saved is not None else "recomendada",
            "temporada":season,"campeonato":league,
            **revisao,"total":len(rows),
            "exemplo":{c:rows[0].get(c) for c in columns},
            "aviso":"Revise as sugestões antes de importar. Nenhum dado foi salvo."}

def importar(payload):
    if not isinstance(payload,dict):raise ValueError("Requisição inválida.")
    token=payload.get("preview_id")
    if not isinstance(token,str) or token not in _PREVIEWS:
        raise ValueError("Prévia expirada. Consulte a API novamente.")
    prev=_PREVIEWS[token]
    if time.monotonic()-prev["criado"]>TTL:
        _PREVIEWS.pop(token,None)
        raise ValueError("Prévia expirada. Consulte a API novamente.")
    columns=payload.get("colunas")
    if not isinstance(columns,list) or not columns or len(columns)!=len(set(columns)) or any(c not in prev["columns"] for c in columns):
        raise ValueError("Escolha colunas existentes na prévia.")
    aliases=payload.get("clubes")
    if not isinstance(aliases,list):raise ValueError("Revise os nomes dos clubes.")
    names={n for row in prev["rows"] for n in (_pick(row,HOME_KEYS),_pick(row,AWAY_KEYS)) if n}
    if {x.get("original") for x in aliases if isinstance(x,dict)}!=names or len(aliases)!=len(names):
        raise ValueError("A lista de clubes mudou desde a prévia.")
    country=payload.get("pais") or prev["country"]
    valid_ids={c["id"] for c in _catalogo_pais(country)}
    normalized={}
    for x in aliases:
        name=x.get("padronizado")
        cid=x.get("clube_id")
        if not isinstance(name,str) or not 1<=len(name.strip())<=150:
            raise ValueError("Nome de clube inválido.")
        if cid in ("",None):cid=None
        elif type(cid) is not int or cid not in valid_ids:
            raise ValueError("Clube não pertence ao país selecionado. Revise a vinculação.")
        normalized[x["original"]]=(name.strip(),cid)
    league=payload.get("campeonato") or prev["league"]
    season=payload.get("temporada") or prev["season"]
    for field,val in (("país",country),("campeonato",league),("temporada",season)):
        if not isinstance(val,str) or not 1<=len(val.strip())<=100:
            raise ValueError(f"Informe {field}.")
    # Não compartilhar tokens de consulta depois da confirmação.
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO odds_importacoes
              (origem,caminho,pais,campeonato,temporada,colunas,total_registros)
              VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
              (prev["host"],prev["path"],country,league,season,Json(columns),len(prev["rows"])))
            batch=cur.fetchone()["id"]
            for i,row in enumerate(prev["rows"],start=1):
                h=_pick(row,HOME_KEYS)
                a=_pick(row,AWAY_KEYS)
                home,home_id=normalized.get(h,(h,None))
                away,away_id=normalized.get(a,(a,None))
                eid=_pick(row,ID_KEYS)
                dt=_parse_game_date(row)
                chosen=_enriquecer_lay(row,columns)
                cur.execute("""INSERT INTO odds
                    (importacao_id,linha_origem,fonte,partida_externa_id,temporada,
                     campeonato,pais,data_jogo,mandante,visitante,mandante_id,
                     visitante_id,dados)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (batch,i,prev["host"],eid,season,league,country,dt,home,away,
                     home_id,away_id,Json(chosen)))
            # Ligações explícitas com clubes_fontes. Não substitui mapeamento.
            for original,(display,cid) in normalized.items():
                if cid is None:continue
                eid="odds:"+prev["host"]+":"+original.strip().lower()
                cur.execute("""INSERT INTO clubes_fontes
                  (clube_id,fonte,id_externo,nome_externo)
                  VALUES (%s,'odds_api',%s,%s)
                  ON CONFLICT (fonte,id_externo) DO NOTHING
                  RETURNING clube_id""",(cid,eid,original))
                result=cur.fetchone()
                if not result:
                    cur.execute("""SELECT clube_id FROM clubes_fontes
                                   WHERE fonte='odds_api' AND id_externo=%s""",(eid,))
                    existing=cur.fetchone()
                    if not existing or existing["clube_id"]!=cid:
                        raise ValueError("Vínculo divergente já existente. Revise os clubes.")
        conn.commit()
    _PREVIEWS.pop(token,None)
    return {"importacao_id":batch,"inseridos":len(prev["rows"]),"colunas":columns,
            "lay":"simulado_um_tick","comissao_pct":4.5}

def ultimas():
    return fetch_all("""SELECT id,origem,caminho,pais,campeonato,temporada,
                        total_registros,criado_em FROM odds_importacoes
                        ORDER BY criado_em DESC LIMIT 30""")
