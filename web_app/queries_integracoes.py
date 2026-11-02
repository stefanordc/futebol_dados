"""Prévia segura e importação atômica de JSON de odds em um servidor local.

IMPORTANTE: endpoint sem autenticação destina-se apenas a loopback. A chave nunca
é persistida, nem na prévia em memória, nem nas tabelas de odds.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit, urljoin
from urllib.request import Request, build_opener, HTTPSHandler, HTTPHandler, HTTPRedirectHandler
from urllib.error import URLError, HTTPError
from ipaddress import ip_address
from collections import OrderedDict
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
LIMIT_BYTES=2_000_000
LIMIT_ROWS=500
TTL=1200
SAFE_KEY=re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")
PRIVATE_FIELD=re.compile(r"(api[_-]?key|token|password|secret|authorization|cookie)",re.I)
HOME_KEYS=("home_team","homeTeam","home_name","homeName","home","mandante","team1","time_casa","teams.home.name","participants.home.name","competitors.home.name")
AWAY_KEYS=("away_team","awayTeam","away_name","awayName","away","visitante","team2","time_fora","teams.away.name","participants.away.name","competitors.away.name")
ID_KEYS=("id","match_id","event_id","fixture_id","game_id","matchId")
DATE_KEYS=("date","start_time","startTime","commence_time","kickoff","utcDate","data","datetime")

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
    allowed={h.strip().lower() for h in os.getenv("ODDS_API_ALLOWED_HOSTS","").split(",") if h.strip()}
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

def preview(payload):
    if not isinstance(payload,dict):raise ValueError("Requisição inválida.")
    base=str(payload.get("base",""))
    path=str(payload.get("caminho",""))
    url,host=_url(base,path)
    api_key=payload.get("chave","")
    header=payload.get("cabecalho","x-api-key")
    if header not in ("x-api-key","Authorization"):raise ValueError("Cabeçalho de chave inválido.")
    if not isinstance(api_key,str) or len(api_key)>1024 or "\n" in api_key or "\r" in api_key:
        raise ValueError("Chave de API inválida.")
    headers={"Accept":"application/json","User-Agent":"DadosFutebolImporter/1.0"}
    if api_key:headers[header]="Bearer "+api_key if header=="Authorization" else api_key
    req=Request(url,headers=headers,method="GET")
    opener=build_opener(HTTPSHandler(),_NoRedirect())
    try:
        with opener.open(req,timeout=12) as response:
            if "json" not in (response.headers.get("Content-Type") or "").lower():
                raise ValueError("A API não retornou JSON.")
            raw=response.read(LIMIT_BYTES+1)
            if len(raw)>LIMIT_BYTES:raise ValueError("Resposta excede o limite de 2 MB.")
    except (HTTPError,URLError,TimeoutError,OSError) as exc:
        raise ValueError("Falha ao consultar a API autorizada. Confira host, chave e caminho.") from exc
    try:data=json.loads(raw)
    except (ValueError,UnicodeDecodeError):raise ValueError("JSON inválido.") from None
    rows=_rows(data)
    if not rows or len(rows)>LIMIT_ROWS:
        raise ValueError("Prévia aceita entre 1 e 500 registros por importação.")
    if any(not isinstance(row,dict) for row in rows):
        raise ValueError("Cada partida precisa ser um objeto JSON.")
    columns=list(OrderedDict.fromkeys(k for row in rows for k in row
        if SAFE_KEY.fullmatch(k) and not PRIVATE_FIELD.search(k)))
    if len(columns)>100:raise ValueError("A API retornou mais de 100 colunas.")
    teams=sorted(set(n for row in rows for n in (_pick(row,HOME_KEYS),_pick(row,AWAY_KEYS)) if n))
    clubs=fetch_all("SELECT id,clube FROM clubes ORDER BY clube")
    unique={}
    for c in clubs:unique.setdefault(key(c["clube"]),[]).append(c)
    clubs_preview=[]
    for name in teams:
        matches=unique.get(key(name),[])
        best=matches[0] if len(matches)==1 else None
        clubs_preview.append({"original":name,"padronizado":best["clube"] if best else name,
          "clube_id":best["id"] if best else None,"sugestoes":_suggest(name,clubs)})
    season,league,country=_metadata(path)
    now=time.monotonic()
    for k,v in list(_PREVIEWS.items()):
        if now-v["criado"]>TTL:_PREVIEWS.pop(k,None)
    token=secrets.token_urlsafe(24)
    _PREVIEWS[token]={"rows":rows,"columns":columns,"criado":now,
                       "host":host,"path":path,"season":season,"league":league,"country":country}
    return {"preview_id":token,"colunas":columns,"temporada":season,"campeonato":league,
            "pais":country,"clubes":clubs_preview,"catalogo":clubs,"total":len(rows),
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
    valid_ids={c["id"] for c in fetch_all("SELECT id FROM clubes")}
    normalized={}
    for x in aliases:
        name=x.get("padronizado")
        cid=x.get("clube_id")
        if not isinstance(name,str) or not 1<=len(name.strip())<=150:
            raise ValueError("Nome de clube inválido.")
        if cid in ("",None):cid=None
        elif type(cid) is not int or cid not in valid_ids:
            raise ValueError("Clube de referência inválido.")
        normalized[x["original"]]=(name.strip(),cid)
    country=payload.get("pais") or prev["country"]
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
                dt=_pick(row,DATE_KEYS)
                if dt:
                    try:
                        parsed=datetime.fromisoformat(dt.replace("Z","+00:00"))
                        dt=parsed.isoformat() if parsed.tzinfo else None
                    except ValueError:dt=None
                chosen={c:row.get(c) for c in columns}
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
    return {"importacao_id":batch,"inseridos":len(prev["rows"]),"colunas":columns}

def ultimas():
    return fetch_all("""SELECT id,origem,caminho,pais,campeonato,temporada,
                        total_registros,criado_em FROM odds_importacoes
                        ORDER BY criado_em DESC LIMIT 30""")
