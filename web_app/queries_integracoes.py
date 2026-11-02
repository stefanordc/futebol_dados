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
from psycopg2 import sql
import keyring
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
        sugestoes=_suggest(nome,catalogo)
        # Sufixos de UF em clubes brasileiros (Chapecoense-SC -> Chapecoense)
        # não devem impedir correspondências fortes, desde que inequívocas.
        uf={"ac","al","ap","am","ba","ce","df","es","go","ma","mt","ms",
            "mg","pa","pb","pr","pe","pi","rj","rn","rs","ro","rr","sc",
            "sp","se","to"}
        partes=key(nome).split()
        sem_uf=" ".join(partes[:-1]) if (
            _pais_normalizado(pais)=="brasil" and len(partes)>1
            and partes[-1] in uf) else ""
        candidatas=por_nome.get(sem_uf,[]) if sem_uf else []
        por_uf=candidatas[0] if len(candidatas)==1 else None
        principal=sugestoes[0] if sugestoes else None
        segundo=sugestoes[1] if len(sugestoes)>1 else None
        forte=(principal is not None and principal["similaridade"]>=95 and
               (segundo is None or principal["similaridade"]-segundo["similaridade"]>=5))
        escolhido=igual or por_uf or (
            next((c for c in catalogo if c["id"]==principal["id"]),None)
            if forte else None
        )
        confianca=100 if igual else (98 if por_uf else (
            principal["similaridade"] if escolhido and principal else None))
        resultados.append({"original":nome,
                           "padronizado":escolhido["clube"] if escolhido else nome,
                           "clube_id":escolhido["id"] if escolhido else None,
                           "correspondencia_automatica":bool(escolhido),
                           "similaridade_automatica":confianca,
                           "sugestoes":sugestoes})
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
# Handicap asiático (AH) e europeu (EH) ficam fora do importador.
HANDICAP_COLUMN=re.compile(r"^(?:Bookie_)?(?:AH|EH)_",re.I)

def _is_handicap_column(column):
    return isinstance(column,str) and bool(HANDICAP_COLUMN.match(column))

def _is_odd_column(column):
    return bool(ODDS_COLUMN.fullmatch(column))

def _default_columns(columns):
    allowed=[c for c in columns if not _is_handicap_column(c)]
    selected=[c for c in allowed if c in MATCH_COLUMNS or _is_odd_column(c)]
    return selected or allowed

def _last_columns():
    # Persistência já existente no banco: o último lote confirmado tem seu
    # conjunto de colunas gravado em odds_importacoes.colunas.
    recent=fetch_all("""SELECT colunas FROM public.odds_importacoes
                        ORDER BY id DESC LIMIT 1""")
    if recent and isinstance(recent[0].get("colunas"),list):
        return [c for c in recent[0]["colunas"]
                if isinstance(c,str) and not _is_handicap_column(c)]
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

# Credenciais ficam no cofre de senhas do sistema operacional,
# sob o usuário Windows que iniciou este servidor. Nunca no JavaScript ou Supabase.
_KEYRING_SERVICE="DadosFutebol - API de odds"

def _chave_armazenada(host):
    try:
        return keyring.get_password(_KEYRING_SERVICE,host)
    except Exception:
        return None

def status_chave(base):
    _,host=_url(str(base),"/api/download")
    return {"salva":bool(_chave_armazenada(host))}

def excluir_chave(base):
    _,host=_url(str(base),"/api/download")
    try:
        if _chave_armazenada(host):
            keyring.delete_password(_KEYRING_SERVICE,host)
    except Exception as exc:
        raise ValueError("Não foi possível excluir a chave do cofre do sistema.") from exc
    return {"salva":False}

def _nome_coluna(source):
    if not isinstance(source,str) or not SAFE_KEY.fullmatch(source):
        raise ValueError("Nome de coluna inválido.")
    name=source.lower()
    if name.startswith("lay_simulado_"):
        name="lay_"+name[len("lay_simulado_"):]
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}",name):
        raise ValueError("Nome de coluna incompatível com PostgreSQL.")
    return name

def _tipo_coluna(source):
    name=_nome_coluna(source)
    if name=="date": return "date"
    if name in ("home_score","away_score"): return "integer"
    if name.startswith("lay_") or _is_odd_column(source): return "numeric(12,4)"
    return "text"

def _valor_coluna(source,value):
    if value in (None,""):return None
    name=_nome_coluna(source)
    if name=="date":
        value=str(value).strip()
        for fmt in ("%d/%m/%Y","%d-%m-%Y","%Y-%m-%d"):
            try:return datetime.strptime(value,fmt).date()
            except ValueError:pass
        return None
    if _tipo_coluna(source)=="integer":
        try:return int(value) if re.fullmatch(r"[+-]?\d+",str(value).strip()) else None
        except (ValueError,TypeError):return None
    if _tipo_coluna(source)=="numeric(12,4)":
        try:
            n=Decimal(str(value).replace(",","."))
            return n if n.is_finite() else None
        except (InvalidOperation,ValueError,TypeError):
            return None
    return str(value)[:1000]

def _linha_colunas(row,selected):
    """Transforma campos CSV e odds Lay em colunas físicas PostgreSQL."""
    out={}
    for source in selected:
        if _is_handicap_column(source):continue
        out[_nome_coluna(source)]=_valor_coluna(source,row.get(source))
        if _is_odd_column(source):
            lay=_simulated_lay(row.get(source))
            if lay is not None:
                out["lay_"+_nome_coluna(source)]=Decimal(str(lay))
            bookie=_bookmaker_column(source)
            if bookie and row.get(bookie):
                out["bookie_"+_nome_coluna(source)]=str(row[bookie])[:200]
    return out

def _preparar_colunas(cur,colunas):
    """Cria campos novos de uma API autorizada sem usar SQL interpolado."""
    if not colunas:return
    if len(colunas)>700:raise ValueError("Número de colunas acima do limite de segurança.")
    alteracoes=[]
    for name,typ in sorted(colunas.items()):
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}",name):
            raise ValueError("Nome de coluna inválido.")
        if typ not in ("text","date","integer","numeric(12,4)"):
            raise ValueError("Tipo de coluna não suportado.")
        alteracoes.append(sql.SQL("ADD COLUMN IF NOT EXISTS {} {}").format(
            sql.Identifier(name),sql.SQL(typ)))
    cur.execute(sql.SQL("ALTER TABLE public.odds ") + sql.SQL(", ").join(alteracoes))

MAX_TEMPORADAS=12
MAX_ROWS_BATCH=20000
TEMPORADA_PATTERN=re.compile(r"20\d{2}(?:-20\d{2})?$")

def _temporadas_da_requisicao(path,entrada):
    """Aceita lista colada com vírgula, ponto e vírgula ou quebra de linha."""
    original=path.rstrip("/").rsplit("/",1)[-1]
    if entrada in (None,""):
        return [original] if TEMPORADA_PATTERN.fullmatch(original) else [None]
    if not isinstance(entrada,str) or len(entrada)>350:
        raise ValueError("Informe até 12 temporadas separadas por vírgula ou quebra de linha.")
    items=[x.strip() for x in re.split(r"[,;\n\r]+",entrada) if x.strip()]
    if not items or len(items)>MAX_TEMPORADAS:
        raise ValueError("Informe de 1 a 12 temporadas.")
    intervalos=bool(re.fullmatch(r"20\d{2}-20\d{2}",original))
    if not TEMPORADA_PATTERN.fullmatch(original):
        raise ValueError("O caminho da API precisa terminar com uma temporada válida.")
    unique=list(dict.fromkeys(items))
    for item in unique:
        if not TEMPORADA_PATTERN.fullmatch(item):
            raise ValueError(f"Temporada inválida: {item}. Use 2026 ou 2026-2027.")
        if ("-" in item)!=intervalos:
            raise ValueError("Não misture temporadas simples e intervalos na mesma URL.")
        if "-" in item:
            a,b=map(int,item.split("-"))
            if b!=a+1:
                raise ValueError(f"Intervalo inválido: {item}. O segundo ano deve ser consecutivo.")
    return unique

def _download_temporada(opener,url,headers):
    request=Request(url,headers=headers,method="GET")
    with opener.open(request,timeout=30) as response:
        content_type=(response.headers.get("Content-Type") or "").lower()
        raw=response.read(LIMIT_BYTES+1)
        if len(raw)>LIMIT_BYTES:
            raise ValueError("Resposta excede o limite de 16 MB.")
    rows=_parse_response(raw,content_type)
    if len(rows)>LIMIT_ROWS:
        raise ValueError("A temporada excede o limite de 5.000 partidas.")
    if any(not isinstance(row,dict) for row in rows):
        raise ValueError("A resposta possui partidas inválidas.")
    return rows

def preview(payload):
    if not isinstance(payload,dict):raise ValueError("Requisição inválida.")
    base=str(payload.get("base",""))
    path=str(payload.get("caminho",""))
    url,host=_url(base,path)
    seasons=_temporadas_da_requisicao(path,payload.get("temporadas"))
    if len(seasons)>1 and seasons[0] is None:
        raise ValueError("Informe um caminho terminado em temporada.")
    api_key=payload.get("chave","")
    header=payload.get("cabecalho","api_key")
    if header not in ("api_key","x-api-key","Authorization"):
        raise ValueError("Método de autenticação inválido.")
    if not isinstance(api_key,str) or len(api_key)>1024 or "\n" in api_key or "\r" in api_key:
        raise ValueError("Chave de API inválida.")
    nova_chave=api_key.strip()
    if not nova_chave:
        api_key=_chave_armazenada(host) or ""
    salvar=payload.get("salvar_chave",False) is True
    headers={"Accept":"text/csv, application/json","User-Agent":"DadosFutebolImporter/1.2"}
    if api_key and header!="api_key":
        headers[header]="Bearer "+api_key if header=="Authorization" else api_key
    opener=build_opener(HTTPSHandler(),_NoRedirect())
    root=url.rsplit("/",1)[0]
    rows=[]
    row_seasons=[]
    paths={}
    results=[]
    for season in seasons:
        current_path=(path.rsplit("/",1)[0]+"/"+season) if season is not None else path
        current_url=(root+"/"+season) if season is not None else url
        paths[season]=current_path
        if api_key and header=="api_key":
            current_url+="?"+urlencode({"api_key":api_key})
        try:
            season_rows=_download_temporada(opener,current_url,headers)
        except HTTPError as exc:
            if exc.code in (401,403):
                raise ValueError("Chave de API inválida ou acesso não autorizado.") from None
            results.append({"temporada":season,"status":"erro","partidas":0,
                            "mensagem":f"HTTP {exc.code}"})
            continue
        except (URLError,TimeoutError,OSError):
            results.append({"temporada":season,"status":"erro","partidas":0,
                            "mensagem":"Falha de conexão ou limite de tempo."})
            continue
        except ValueError as exc:
            # Mensagens geradas localmente; nunca repassar URL com credenciais.
            results.append({"temporada":season,"status":"erro","partidas":0,
                            "mensagem":str(exc)})
            continue
        results.append({"temporada":season,"status":"ok" if season_rows else "vazio",
                        "partidas":len(season_rows)})
        if len(rows)+len(season_rows)>MAX_ROWS_BATCH:
            raise ValueError("O lote excede 20.000 partidas. Divida a lista de temporadas.")
        rows.extend(season_rows)
        row_seasons.extend([season]*len(season_rows))
    if not rows:
        raise ValueError("Nenhuma partida retornada. Verifique os resultados das temporadas e os caminhos.")
    if nova_chave and salvar:
        try:
            keyring.set_password(_KEYRING_SERVICE,host,nova_chave)
        except Exception as exc:
            raise ValueError("A consulta funcionou, mas não foi possível guardar a chave no cofre do sistema.") from exc
    columns=list(OrderedDict.fromkeys(k for row in rows for k in row
        if SAFE_KEY.fullmatch(k) and not PRIVATE_FIELD.search(k)
        and not _is_handicap_column(k)))
    if len(columns)>300:raise ValueError("A API retornou mais de 300 colunas.")
    season,league,country=_metadata(path)
    revisao=_clubes_preview(rows,country)
    saved=_last_columns()
    selected=[c for c in saved if c in columns] if saved is not None else _default_columns(columns)
    if not selected:selected=_default_columns(columns)
    now=time.monotonic()
    for k,v in list(_PREVIEWS.items()):
        if now-v["criado"]>TTL:_PREVIEWS.pop(k,None)
    token=secrets.token_urlsafe(24)
    _PREVIEWS[token]={"rows":rows,"row_seasons":row_seasons,"paths":paths,
                       "temporadas_resultado":results,"columns":columns,"criado":now,
                       "host":host,"path":path,"season":season,"league":league,"country":country}
    return {"preview_id":token,"colunas":columns,
            "chave_salva":bool(_chave_armazenada(host)),"colunas_marcadas":selected,
            "selecao_origem":"ultima_importacao" if saved is not None else "recomendada",
            "temporada":season,"temporadas":seasons,"temporadas_resultado":results,
            "multiplas_temporadas":payload.get("temporadas") not in (None,""),
            "campeonato":league,**revisao,"total":len(rows),
            "exemplo":{c:rows[0].get(c) for c in columns},
            "aviso":"Revise temporadas com erro e as sugestões de clubes antes de importar."}


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
    if (not isinstance(columns,list) or not columns or len(columns)!=len(set(columns))
        or any(c not in prev["columns"] or _is_handicap_column(c) for c in columns)):
        raise ValueError("Escolha colunas existentes na prévia.")
    aliases=payload.get("clubes")
    if not isinstance(aliases,list):raise ValueError("Revise os nomes dos clubes.")
    names={n for row in prev["rows"] for n in (_pick(row,HOME_KEYS),_pick(row,AWAY_KEYS)) if n}
    if {x.get("original") for x in aliases if isinstance(x,dict)}!=names or len(aliases)!=len(names):
        raise ValueError("A lista de clubes mudou desde a prévia.")
    country=payload.get("pais") or prev["country"]
    league=payload.get("campeonato") or prev["league"]
    season=payload.get("temporada") or prev["season"]
    for field,val in (("país",country),("campeonato",league),("temporada",season)):
        if not isinstance(val,str) or not 1<=len(val.strip())<=100:
            raise ValueError(f"Informe {field}.")
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
    prepared=[]
    column_types={}
    for idx,row in enumerate(prev["rows"],start=1):
        values=_linha_colunas(row,columns)
        prepared.append((idx,row,values))
        for source in columns:
            column_types[_nome_coluna(source)]=_tipo_coluna(source)
            if _is_odd_column(source):
                column_types["lay_"+_nome_coluna(source)]="numeric(12,4)"
                column_types["bookie_"+_nome_coluna(source)]="text"
    # Para repetir a importação, o índice único em (fonte, temporada, partida_externa_id)
    # impede duplicação mesmo com duas requisições simultâneas.
    inserted=0
    ignored=0
    with get_conn() as conn:
        with conn.cursor() as cur:
            _preparar_colunas(cur,column_types)
            cur.execute("""INSERT INTO public.odds_importacoes
                (origem,caminho,pais,campeonato,temporada,colunas,total_registros)
                VALUES (%s,%s,%s,%s,%s,%s,0) RETURNING id""",
                (prev["host"],prev["path"],country,league,season,Json(columns)))
            batch=cur.fetchone()["id"]
            for i,row,values in prepared:
                h=_pick(row,HOME_KEYS)
                a=_pick(row,AWAY_KEYS)
                home,home_id=normalized.get(h,(h,None))
                away,away_id=normalized.get(a,(a,None))
                external=_pick(row,ID_KEYS)
                dt=_parse_game_date(row)
                standard={
                    "importacao_id":batch,"linha_origem":i,
                    "fonte":prev["host"],"partida_externa_id":external,
                    "temporada":season,"campeonato":league,"pais":country,
                    "data_jogo":dt,"mandante":home,"visitante":away,
                    "mandante_id":home_id,"visitante_id":away_id,
                    "lay_origem":"estimado_um_tick",
                    "lay_precificacao_real":False,
                    "lay_liquidez_verificada":False,
                    "lay_comissao_pct":Decimal("4.5")
                }
                standard.update(values)
                keys=list(standard)
                query=sql.SQL("""INSERT INTO public.odds ({}) VALUES ({})
                    ON CONFLICT DO NOTHING RETURNING id""").format(
                    sql.SQL(",").join(map(sql.Identifier,keys)),
                    sql.SQL(",").join([sql.Placeholder() for _ in keys]))
                cur.execute(query,[standard[k] for k in keys])
                if cur.fetchone():
                    inserted+=1
                else:
                    ignored+=1
            if inserted:
                cur.execute("UPDATE public.odds_importacoes SET total_registros=%s WHERE id=%s",
                            (inserted,batch))
                for original,(display,cid) in normalized.items():
                    if cid is None:continue
                    eid="odds:"+prev["host"]+":"+original.strip().lower()
                    cur.execute("""INSERT INTO public.clubes_fontes
                      (clube_id,fonte,id_externo,nome_externo)
                      VALUES (%s,'odds_api',%s,%s)
                      ON CONFLICT (fonte,id_externo) DO NOTHING
                      RETURNING clube_id""",(cid,eid,original))
                    linked=cur.fetchone()
                    if not linked:
                        cur.execute("""SELECT clube_id FROM public.clubes_fontes
                                     WHERE fonte='odds_api' AND id_externo=%s""",(eid,))
                        existing=cur.fetchone()
                        if not existing or existing["clube_id"]!=cid:
                            raise ValueError("Vínculo divergente já existente. Revise os clubes.")
                conn.commit()
            else:
                # Não criar histórico fictício de lote sem registros novos.
                conn.rollback()
                batch=None
    _PREVIEWS.pop(token,None)
    return {"importacao_id":batch,"inseridos":inserted,"ignorados":ignored,
            "colunas":columns,"lay":"estimado_um_tick","comissao_pct":4.5}

def ultimas():
    return fetch_all("""SELECT id,origem,caminho,pais,campeonato,temporada,
                        total_registros,criado_em FROM odds_importacoes
                        ORDER BY criado_em DESC LIMIT 30""")
