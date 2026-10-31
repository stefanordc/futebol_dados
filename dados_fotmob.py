import json
import logging
import os
import random
import re
import subprocess
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import psycopg2
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

DIR = Path(__file__).resolve().parent
ARQUIVO_IDS = DIR / "id_jogos.txt"
PASTA_RAW = DIR / "fotmob_raw"
CCODE3 = "EUA"                 # como no link informado
CCODE3_ALTERNATIVOS = ("USA",)  # tentados se o primeiro não devolver odds
PROVEDOR_ODDS = "Bet365_default"
TEMPORADA = None               # o FotMob não informa a temporada no matchDetails; ex.: "2026/2027".
                               # Se None, é inferida pela data (jul-dez = ano/ano+1; jan-jun = ano-1/ano)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("fotmob")

BASE_URL = "https://www.fotmob.com/api/data"
HOME_URL = "https://www.fotmob.com/"
BRASILIA_TZ = timezone(timedelta(hours=-3))
FONTE = "fotmob"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def g(dado, *caminho, default=None):
    """Acesso seguro a dicts/listas aninhados."""
    for chave in caminho:
        if isinstance(dado, dict):
            dado = dado.get(chave)
        elif isinstance(dado, list) and isinstance(chave, int) and -len(dado) <= chave < len(dado):
            dado = dado[chave]
        else:
            return default
        if dado is None:
            return default
    return dado


def _to_int(valor):
    if valor in (None, "") or isinstance(valor, bool):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _to_float(valor):
    if valor in (None, "") or isinstance(valor, bool):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _norm(n):
    """Float inteiro vira int (3.0 -> 3)."""
    return int(n) if isinstance(n, float) and n.is_integer() else n


_NUM = r"-?\d+(?:[.,]\d+)?"


def _num(texto):
    return _norm(float(texto.replace(",", ".")))


def parse_valor(v):
    """Interpreta valores do FotMob e devolve (valor, total, percentual).

    Aceita número, "451 (83%)", "12/25 (48%)" e "56%"."""
    if v is None or isinstance(v, bool):
        return None, None, None
    if isinstance(v, (int, float)):
        return _norm(v), None, None
    texto = str(v).strip()
    m = re.match(rf"^({_NUM})\s*/\s*({_NUM})(?:\s*\(({_NUM})%\))?$", texto)
    if m:
        return _num(m[1]), _num(m[2]), _num(m[3]) if m[3] else None
    m = re.match(rf"^({_NUM})\s*(?:\(({_NUM})%\))?\s*%?$", texto)
    if m:
        return _num(m[1]), None, _num(m[2]) if m[2] else None
    return None, None, None


def total_derivado(valor, total, pct):
    """Total exato quando existe; senão, estimado pelo percentual (marcado como derivado)."""
    if total is not None:
        return total, False
    if valor is not None and pct:
        return int(round(valor * 100 / pct)), True
    return None, False


def definir(linha, derivados, coluna, valor, derivado=False):
    """Grava valor na linha; valores derivados nunca sobrescrevem valores exatos."""
    if derivado:
        if coluna in linha:
            return
        derivados.add(coluna)
    else:
        derivados.discard(coluna)
    linha[coluna] = valor


def preencher(linha, derivados, spec, valor, total, pct):
    coluna, coluna_total = spec
    if valor is not None:
        definir(linha, derivados, coluna, valor)
    if coluna_total:
        t, derivado = total_derivado(valor, total, pct)
        if t is not None:
            definir(linha, derivados, coluna_total, t, derivado)


def _indexar(especificacoes):
    return {alias: (coluna, total) for aliases, coluna, total in especificacoes for alias in aliases}


# ---------------------------------------------------------------------------
# Países: nome em português (como é conhecido no Brasil) e continente
# Formato: ISO2 | ISO3 | nome em inglês | nome em português
# ---------------------------------------------------------------------------

_BLOCO_PAISES = """
# Europa
AL|ALB|Albania|Albânia
AD|AND|Andorra|Andorra
AT|AUT|Austria|Áustria
BY|BLR|Belarus|Bielorrússia
BE|BEL|Belgium|Bélgica
BA|BIH|Bosnia and Herzegovina|Bósnia e Herzegovina
BG|BGR|Bulgaria|Bulgária
HR|HRV|Croatia|Croácia
CY|CYP|Cyprus|Chipre
CZ|CZE|Czechia|República Tcheca
DK|DNK|Denmark|Dinamarca
EE|EST|Estonia|Estônia
FO|FRO|Faroe Islands|Ilhas Faroé
FI|FIN|Finland|Finlândia
FR|FRA|France|França
GE|GEO|Georgia|Geórgia
DE|DEU|Germany|Alemanha
GI|GIB|Gibraltar|Gibraltar
GR|GRC|Greece|Grécia
HU|HUN|Hungary|Hungria
IS|ISL|Iceland|Islândia
IE|IRL|Ireland|Irlanda
IT|ITA|Italy|Itália
XK|XKX|Kosovo|Kosovo
LV|LVA|Latvia|Letônia
LI|LIE|Liechtenstein|Liechtenstein
LT|LTU|Lithuania|Lituânia
LU|LUX|Luxembourg|Luxemburgo
MT|MLT|Malta|Malta
MD|MDA|Moldova|Moldávia
MC|MCO|Monaco|Mônaco
ME|MNE|Montenegro|Montenegro
NL|NLD|Netherlands|Holanda
MK|MKD|North Macedonia|Macedônia do Norte
NO|NOR|Norway|Noruega
PL|POL|Poland|Polônia
PT|PRT|Portugal|Portugal
RO|ROU|Romania|Romênia
RU|RUS|Russia|Rússia
SM|SMR|San Marino|San Marino
RS|SRB|Serbia|Sérvia
SK|SVK|Slovakia|Eslováquia
SI|SVN|Slovenia|Eslovênia
ES|ESP|Spain|Espanha
SE|SWE|Sweden|Suécia
CH|CHE|Switzerland|Suíça
TR|TUR|Turkey|Turquia
UA|UKR|Ukraine|Ucrânia
GB|GBR|United Kingdom|Reino Unido
VA|VAT|Vatican City|Vaticano
ENG|ENG|England|Inglaterra
SCO|SCO|Scotland|Escócia
WAL|WAL|Wales|País de Gales
NIR|NIR|Northern Ireland|Irlanda do Norte
# Ásia
AF|AFG|Afghanistan|Afeganistão
AM|ARM|Armenia|Armênia
AZ|AZE|Azerbaijan|Azerbaijão
BH|BHR|Bahrain|Bahrein
BD|BGD|Bangladesh|Bangladesh
BT|BTN|Bhutan|Butão
BN|BRN|Brunei|Brunei
KH|KHM|Cambodia|Camboja
CN|CHN|China|China
HK|HKG|Hong Kong|Hong Kong
IN|IND|India|Índia
ID|IDN|Indonesia|Indonésia
IR|IRN|Iran|Irã
IQ|IRQ|Iraq|Iraque
IL|ISR|Israel|Israel
JP|JPN|Japan|Japão
JO|JOR|Jordan|Jordânia
KZ|KAZ|Kazakhstan|Cazaquistão
KW|KWT|Kuwait|Kuwait
KG|KGZ|Kyrgyzstan|Quirguistão
LA|LAO|Laos|Laos
LB|LBN|Lebanon|Líbano
MO|MAC|Macau|Macau
MY|MYS|Malaysia|Malásia
MV|MDV|Maldives|Maldivas
MN|MNG|Mongolia|Mongólia
MM|MMR|Myanmar|Mianmar
NP|NPL|Nepal|Nepal
KP|PRK|North Korea|Coreia do Norte
OM|OMN|Oman|Omã
PK|PAK|Pakistan|Paquistão
PS|PSE|Palestine|Palestina
PH|PHL|Philippines|Filipinas
QA|QAT|Qatar|Catar
SA|SAU|Saudi Arabia|Arábia Saudita
SG|SGP|Singapore|Singapura
KR|KOR|South Korea|Coreia do Sul
LK|LKA|Sri Lanka|Sri Lanka
SY|SYR|Syria|Síria
TW|TWN|Taiwan|Taiwan
TJ|TJK|Tajikistan|Tajiquistão
TH|THA|Thailand|Tailândia
TL|TLS|Timor-Leste|Timor-Leste
TM|TKM|Turkmenistan|Turcomenistão
AE|ARE|United Arab Emirates|Emirados Árabes Unidos
UZ|UZB|Uzbekistan|Uzbequistão
VN|VNM|Vietnam|Vietnã
YE|YEM|Yemen|Iêmen
# África
DZ|DZA|Algeria|Argélia
AO|AGO|Angola|Angola
BJ|BEN|Benin|Benin
BW|BWA|Botswana|Botsuana
BF|BFA|Burkina Faso|Burkina Faso
BI|BDI|Burundi|Burundi
CV|CPV|Cape Verde|Cabo Verde
CM|CMR|Cameroon|Camarões
CF|CAF|Central African Republic|República Centro-Africana
TD|TCD|Chad|Chade
KM|COM|Comoros|Comores
CG|COG|Congo|Congo
CD|COD|DR Congo|República Democrática do Congo
CI|CIV|Ivory Coast|Costa do Marfim
DJ|DJI|Djibouti|Djibuti
EG|EGY|Egypt|Egito
GQ|GNQ|Equatorial Guinea|Guiné Equatorial
ER|ERI|Eritrea|Eritreia
SZ|SWZ|Eswatini|Essuatíni
ET|ETH|Ethiopia|Etiópia
GA|GAB|Gabon|Gabão
GM|GMB|Gambia|Gâmbia
GH|GHA|Ghana|Gana
GN|GIN|Guinea|Guiné
GW|GNB|Guinea-Bissau|Guiné-Bissau
KE|KEN|Kenya|Quênia
LS|LSO|Lesotho|Lesoto
LR|LBR|Liberia|Libéria
LY|LBY|Libya|Líbia
MG|MDG|Madagascar|Madagascar
MW|MWI|Malawi|Malaui
ML|MLI|Mali|Mali
MR|MRT|Mauritania|Mauritânia
MU|MUS|Mauritius|Maurício
MA|MAR|Morocco|Marrocos
MZ|MOZ|Mozambique|Moçambique
NA|NAM|Namibia|Namíbia
NE|NER|Niger|Níger
NG|NGA|Nigeria|Nigéria
RE|REU|Réunion|Reunião
RW|RWA|Rwanda|Ruanda
ST|STP|Sao Tome and Principe|São Tomé e Príncipe
SN|SEN|Senegal|Senegal
SC|SYC|Seychelles|Seicheles
SL|SLE|Sierra Leone|Serra Leoa
SO|SOM|Somalia|Somália
ZA|ZAF|South Africa|África do Sul
SS|SSD|South Sudan|Sudão do Sul
SD|SDN|Sudan|Sudão
TZ|TZA|Tanzania|Tanzânia
TG|TGO|Togo|Togo
TN|TUN|Tunisia|Tunísia
UG|UGA|Uganda|Uganda
ZM|ZMB|Zambia|Zâmbia
ZW|ZWE|Zimbabwe|Zimbábue
# América do Sul
AR|ARG|Argentina|Argentina
BO|BOL|Bolivia|Bolívia
BR|BRA|Brazil|Brasil
CL|CHL|Chile|Chile
CO|COL|Colombia|Colômbia
EC|ECU|Ecuador|Equador
GF|GUF|French Guiana|Guiana Francesa
GY|GUY|Guyana|Guiana
PY|PRY|Paraguay|Paraguai
PE|PER|Peru|Peru
SR|SUR|Suriname|Suriname
UY|URY|Uruguay|Uruguai
VE|VEN|Venezuela|Venezuela
# América do Norte
CA|CAN|Canada|Canadá
US|USA|United States|Estados Unidos
MX|MEX|Mexico|México
GL|GRL|Greenland|Groenlândia
BM|BMU|Bermuda|Bermudas
# América Central
BZ|BLZ|Belize|Belize
CR|CRI|Costa Rica|Costa Rica
SV|SLV|El Salvador|El Salvador
GT|GTM|Guatemala|Guatemala
HN|HND|Honduras|Honduras
NI|NIC|Nicaragua|Nicarágua
PA|PAN|Panama|Panamá
AG|ATG|Antigua and Barbuda|Antígua e Barbuda
BS|BHS|Bahamas|Bahamas
BB|BRB|Barbados|Barbados
CU|CUB|Cuba|Cuba
DM|DMA|Dominica|Dominica
DO|DOM|Dominican Republic|República Dominicana
GD|GRD|Grenada|Granada
HT|HTI|Haiti|Haiti
JM|JAM|Jamaica|Jamaica
KN|KNA|Saint Kitts and Nevis|São Cristóvão e Névis
LC|LCA|Saint Lucia|Santa Lúcia
MF|MAF|Saint Martin|São Martinho
VC|VCT|Saint Vincent and the Grenadines|São Vicente e Granadinas
TT|TTO|Trinidad and Tobago|Trinidad e Tobago
PR|PRI|Puerto Rico|Porto Rico
CW|CUW|Curaçao|Curaçao
AW|ABW|Aruba|Aruba
KY|CYM|Cayman Islands|Ilhas Cayman
GP|GLP|Guadeloupe|Guadalupe
MQ|MTQ|Martinique|Martinica
MS|MSR|Montserrat|Montserrat
TC|TCA|Turks and Caicos Islands|Ilhas Turks e Caicos
VG|VGB|British Virgin Islands|Ilhas Virgens Britânicas
VI|VIR|US Virgin Islands|Ilhas Virgens Americanas
# Oceania
AU|AUS|Australia|Austrália
NZ|NZL|New Zealand|Nova Zelândia
FJ|FJI|Fiji|Fiji
PG|PNG|Papua New Guinea|Papua-Nova Guiné
SB|SLB|Solomon Islands|Ilhas Salomão
VU|VUT|Vanuatu|Vanuatu
NC|NCL|New Caledonia|Nova Caledônia
WS|WSM|Samoa|Samoa
TO|TON|Tonga|Tonga
KI|KIR|Kiribati|Kiribati
TV|TUV|Tuvalu|Tuvalu
NR|NRU|Nauru|Nauru
PW|PLW|Palau|Palau
FM|FSM|Micronesia|Micronésia
MH|MHL|Marshall Islands|Ilhas Marshall
CK|COK|Cook Islands|Ilhas Cook
AS|ASM|American Samoa|Samoa Americana
GU|GUM|Guam|Guam
PF|PYF|French Polynesia|Polinésia Francesa
MP|MNP|Northern Mariana Islands|Ilhas Marianas do Norte
"""

# Códigos da FIFA (usados pelo FotMob) que diferem do ISO-3, e variações de nome em inglês
_ALIASES_CODIGO = """
GER:DE NED:NL SUI:CH POR:PT CRO:HR DEN:DK GRE:GR BUL:BG LAT:LV MON:MC KOS:XK
RSA:ZA ALG:DZ ANG:AO CHA:TD CGO:CG CTA:CF EQG:GQ GAM:GM GBS:GW GUI:GN LBA:LY MAD:MG
MTN:MR MRI:MU SEY:SC SUD:SD TAN:TZ TOG:TG ZAM:ZM ZIM:ZW BOT:BW LES:LS LBR:LR MAW:MW
CRC:CR CHI:CL PAR:PY URU:UY ESA:SV GUA:GT HAI:HT HON:HN NCA:NI TRI:TT CUW:CW
IRI:IR KSA:SA UAE:AE TPE:TW INA:ID PHI:PH SIN:SG SRI:LK MAS:MY VIE:VN LIB:LB KUW:KW
OMA:OM MYA:MM BAN:BD BHU:BT CAM:KH MGL:MN NEP:NP FIJ:FJ SOL:SB VAN:VU TAH:PF
"""
_ALIASES_NOME = {
    "usa": "US", "united states of america": "US", "czech republic": "CZ", "türkiye": "TR", "turkiye": "TR",
    "côte d'ivoire": "CI", "cote d'ivoire": "CI", "korea republic": "KR", "korea dpr": "KP",
    "congo dr": "CD", "democratic republic of the congo": "CD", "republic of the congo": "CG",
    "cabo verde": "CV", "curacao": "CW",
    "holland": "NL", "republic of ireland": "IE", "bosnia-herzegovina": "BA", "bosnia & herzegovina": "BA",
    "macedonia": "MK", "swaziland": "SZ", "china pr": "CN", "uae": "AE", "chinese taipei": "TW",
    "east timor": "TL", "russian federation": "RU", "viet nam": "VN",
    "the gambia": "GM", "gambia, the": "GM",
    "macao": "MO", "reunion": "RE", "réunion": "RE",
    "tahiti": "PF", "u.s. virgin islands": "VI", "us virgin islands": "VI",
    "united states virgin islands": "VI",
}

# Códigos de competições sem país
_PAISES_ESPECIAIS = {"int": ("Internacional", "Internacional"), "intl": ("Internacional", "Internacional"),
                     "eur": ("Europa", "Europa")}


def _construir_paises():
    paises, indice, continente = {}, {}, None
    for linha in _BLOCO_PAISES.strip().splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if linha.startswith("#"):
            continente = linha[1:].strip()
            continue
        iso2, iso3, en, pt = linha.split("|")
        paises[iso2] = (pt, continente)
        for chave in (iso2, iso3, en, pt):
            indice[chave.lower()] = iso2
    for par in _ALIASES_CODIGO.split():
        cod, iso2 = par.split(":")
        indice[cod.lower()] = iso2
    for nome, iso2 in _ALIASES_NOME.items():
        indice[nome.lower()] = iso2
    return paises, indice


_PAISES, _INDICE_PAISES = _construir_paises()
_PAISES_NAO_ENCONTRADOS = set()


def pais_info(nome=None, codigo=None):
    """Devolve (nome do país em português, continente). Se não achar, devolve (original, None)."""
    for chave in (codigo, nome):
        if not chave:
            continue
        k = str(chave).strip().lower()
        if k in _PAISES_ESPECIAIS:
            return _PAISES_ESPECIAIS[k]
        iso2 = _INDICE_PAISES.get(k)
        if iso2:
            return _PAISES[iso2]
    original = nome or codigo
    if original and original not in _PAISES_NAO_ENCONTRADOS:
        _PAISES_NAO_ENCONTRADOS.add(original)
        logger.warning("País não mapeado: %r (acrescente em _BLOCO_PAISES).", original)
    return (original, None) if original else (None, None)


def traduzir_pais(valor=None, codigo=None):
    return pais_info(valor, codigo)[0]


# ---------------------------------------------------------------------------
# Traduções e padronização
# ---------------------------------------------------------------------------

PERIODOS = {
    "all": "Completo", "firsthalf": 1, "secondhalf": 2,
    "firstextrahalf": "Prorrogação (1º tempo)", "secondextrahalf": "Prorrogação (2º tempo)",
    "penaltyshootout": "Disputa de pênaltis",
}
MANDO = {"casa": "Casa", "fora": "Fora"}
# Nas finalizações o período é numérico: 1 e 2 (tempos normais); 3, 4 e 5 para prorrogação e pênaltis
PERIODOS_FINALIZACAO = {
    "firsthalf": 1, "secondhalf": 2, "firstextrahalf": 3, "secondextrahalf": 4, "penaltyshootout": 5,
}
EVENTOS_FINALIZACAO = {
    "goal": "Gol", "attemptsaved": "Defendida", "miss": "Para fora",
    "post": "Trave", "blocked": "Bloqueada",
}
TIPOS_FINALIZACAO = {
    "rightfoot": "Pé direito", "leftfoot": "Pé esquerdo", "header": "Cabeça",
    "otherbodypart": "Outra parte do corpo", "otherbodyparts": "Outra parte do corpo",
}
SITUACOES_JOGADA = {
    "regularplay": "Jogada normal", "fromcorner": "Escanteio", "setpiece": "Bola parada",
    "fastbreak": "Contra-ataque", "penalty": "Pênalti", "throwinsetpiece": "Lateral",
    "freekick": "Falta", "individualplay": "Jogada individual",
}
# Posição genérica (reserva, quando a posição exata não é encontrada)
POSICOES = {0: "Goleiro", 1: "Defensor", 2: "Meio-campista", 3: "Atacante"}

# Posição exata (positionLabel.label do FotMob) -> português
POSICOES_EXATAS = {
    "GK": "Goleiro",
    "CB": "Zagueiro", "LCB": "Zagueiro", "RCB": "Zagueiro", "SW": "Líbero",
    "LB": "Lateral-esquerdo", "RB": "Lateral-direito",
    "LWB": "Ala-esquerdo", "RWB": "Ala-direito",
    "DM": "Volante", "CDM": "Volante", "LDM": "Volante", "RDM": "Volante",
    "CM": "Meio-campista central", "LCM": "Meio-campista central", "RCM": "Meio-campista central",
    "AM": "Meia-atacante", "CAM": "Meia-atacante", "LAM": "Meia-atacante", "RAM": "Meia-atacante",
    "LM": "Meia-esquerda", "RM": "Meia-direita",
    "LW": "Ponta-esquerda", "RW": "Ponta-direita",
    "ST": "Centroavante", "CF": "Centroavante", "LST": "Centroavante", "RST": "Centroavante",
    "SS": "Segundo atacante",
}

# positionId da escalação/playerStats -> rótulo curto (mesmo vocabulário de positionLabel)
POSICAO_POR_POSITION_ID = {
    11: "GK",
    32: "RB", 33: "CB", 34: "CB", 35: "CB", 36: "CB", 37: "CB", 38: "LB",
    51: "RB", 59: "LB", 62: "RWB", 68: "LWB",
    64: "DM", 65: "DM", 66: "DM", 67: "DM",
    71: "RM", 72: "RM", 73: "CM", 74: "CM", 75: "CM", 76: "CM", 77: "CM",
    78: "LM", 79: "LM",
    82: "RW", 83: "RW", 84: "AM", 85: "AM", 86: "AM", 87: "LW", 88: "LW",
    95: "AM", 103: "RW", 104: "ST", 105: "ST", 106: "ST", 107: "LW", 115: "ST",
}

# Cache de posição principal via playerData (reservas sem positionId no jogo)
_CACHE_POSICAO_PLAYER = {}


def traduzir(tabela, valor, escopo, nao_mapeados):
    """Traduz um valor categórico; se desconhecido, mantém o original e registra."""
    if valor in (None, ""):
        return None
    traduzido = tabela.get(str(valor).replace(" ", "").lower())
    if traduzido is None:
        registrar(nao_mapeados, escopo, str(valor), "valor categórico sem tradução", valor)
        return valor
    return traduzido


def registrar(nao_mapeados, escopo, chave, titulo, exemplo):
    nao_mapeados.setdefault((escopo, str(chave), str(titulo)), exemplo)


def traduzir_posicao_exata(rotulo, nao_mapeados=None):
    """Converte rótulo curto do FotMob (CB, LB, AM…) para português."""
    if rotulo in (None, ""):
        return None
    chave = str(rotulo).strip().upper()
    traduzida = POSICOES_EXATAS.get(chave)
    if traduzida:
        return traduzida
    if nao_mapeados is not None:
        registrar(nao_mapeados, "jogadores:posicao", rotulo, "posição sem tradução", rotulo)
    return str(rotulo).strip()


def mapear_posicoes(no, saida):
    """Varre o JSON por positionLabel e positionId. Devolve {id_jogador: rótulo_curto}."""
    if isinstance(no, dict):
        pid = _to_int(no.get("playerId") or no.get("id"))
        if pid is not None:
            rotulo = g(no, "positionLabel", "label")
            if rotulo:
                saida.setdefault(pid, str(rotulo).strip().upper())
            else:
                pos_id = _to_int(no.get("positionId"))
                if pos_id is not None and pos_id in POSICAO_POR_POSITION_ID:
                    saida.setdefault(pid, POSICAO_POR_POSITION_ID[pos_id])
        for v in no.values():
            mapear_posicoes(v, saida)
    elif isinstance(no, list):
        for v in no:
            mapear_posicoes(v, saida)
    return saida


_PRIMARY_KEY_PARA_ROTULO = {
    "goalkeeper": "GK", "keeper": "GK",
    "centerback": "CB", "leftcenterback": "CB", "rightcenterback": "CB",
    "leftback": "LB", "rightback": "RB",
    "leftwingback": "LWB", "rightwingback": "RWB",
    "defensivemidfielder": "DM", "centerdefensivemidfielder": "DM",
    "leftdefensivemidfielder": "DM", "rightdefensivemidfielder": "DM",
    "centermidfielder": "CM", "leftcentermidfielder": "CM", "rightcentermidfielder": "CM",
    "attackingmidfielder": "AM", "centerattackingmidfielder": "AM",
    "leftmidfielder": "LM", "rightmidfielder": "RM",
    "leftwinger": "LW", "rightwinger": "RW",
    "striker": "ST", "centerforward": "ST", "forward": "ST",
}


def _rotulo_de_player_data(dados):
    """Extrai o rótulo curto (CB, ST…) de um payload playerData."""
    desc = dados.get("positionDescription") if isinstance(dados, dict) else None
    if not isinstance(desc, dict):
        return None
    for item in desc.get("positions") or []:
        if not isinstance(item, dict):
            continue
        if item.get("isMainPosition"):
            lab = g(item, "strPosShort", "label")
            if lab:
                return str(lab).strip().upper()
    for item in desc.get("positions") or []:
        if not isinstance(item, dict):
            continue
        lab = g(item, "strPosShort", "label")
        if lab:
            return str(lab).strip().upper()
    chave = (g(desc, "primaryPosition", "key") or "").replace(" ", "").lower()
    if chave in _PRIMARY_KEY_PARA_ROTULO:
        return _PRIMARY_KEY_PARA_ROTULO[chave]
    return None


def buscar_posicao_player_data(pid):
    """Busca a posição principal do jogador na API playerData (com cache)."""
    pid = _to_int(pid)
    if pid is None:
        return None
    if pid in _CACHE_POSICAO_PLAYER:
        return _CACHE_POSICAO_PLAYER[pid]
    url = f"{BASE_URL}/playerData?id={pid}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
        rotulo = _rotulo_de_player_data(dados)
    except Exception as exc:
        logger.debug("playerData %s falhou: %s", pid, exc)
        rotulo = None
    _CACHE_POSICAO_PLAYER[pid] = rotulo
    return rotulo


def limpar_provedor(nome):
    """'Bet365_default' -> 'Bet365'."""
    if not nome:
        return nome
    return re.sub(r"[_\s-]*default$", "", str(nome), flags=re.I).strip() or str(nome)


# ---------------------------------------------------------------------------
# Mapeamento das estatísticas (FotMob -> colunas do schema)
# Cada alias é comparado em minúsculas com a "key" e o "title" do FotMob.
# Formato: (aliases, coluna, coluna_do_total | None)
# ---------------------------------------------------------------------------

MAPA_EQUIPE = _indexar([
    (("ballpossesion", "ballpossession", "ball possession"), "posse_bola", None),
    (("expected_goals", "expected goals (xg)"), "xg", None),
    (("expected_goals_open_play", "xg open play"), "xg_jogada_normal", None),
    (("expected_goals_set_play", "xg set play"), "xg_jogada_ensaiada", None),
    (("expected_goals_non_penalty", "non-penalty xg"), "xg_sem_penalti", None),
    (("expected_goals_on_target", "xg on target (xgot)"), "xgot", None),
    (("total_shots", "total shots"), "total_chutes", None),
    (("shotsontarget", "shots on target"), "chutes_certos", None),
    (("shotsofftarget", "shots off target"), "chutes_fora", None),
    (("blocked_shots", "blocked shots"), "chutes_bloqueados", None),
    (("shots_woodwork", "hit_woodwork", "hit woodwork"), "chutes_trave", None),
    (("shots_inside_box", "shots inside box"), "chutes_dentro_area", None),
    (("shots_outside_box", "shots outside box"), "chutes_fora_area", None),
    (("big_chance", "big chances"), "grandes_chances", None),
    (("big_chance_missed_title", "big chances missed"), "grandes_chances_perdidas", None),
    (("passes",), "passes", None),
    (("accurate_passes", "accurate passes"), "passes_certos", "passes"),
    (("own_half_passes", "own half"), "passes_campo_defesa", None),
    (("opposition_half_passes", "opposition half"), "passes_campo_ataque", None),
    (("long_balls_accurate", "accurate long balls"), "passes_longos_certos", "passes_longos"),
    (("accurate_crosses", "crosses", "accurate crosses"), "cruzamentos_certos", "cruzamentos"),
    (("corners",), "escanteios", None),
    (("player_throws", "throws"), "laterais", None),
    (("touches_opp_box", "touches in opposition box"), "toques_area_adversaria", None),
    (("offsides",), "impedimentos", None),
    (("matchstats.headers.tackles", "tackles", "tackles won"), "desarmes", None),
    (("interceptions",), "interceptacoes", None),
    (("shot_blocks", "blocks"), "bloqueios", None),
    (("clearances",), "bolas_afastadas", None),
    (("keeper_saves", "keeper saves"), "defesas_goleiro", None),
    (("duel_won", "duels won"), "disputas_ganhas", None),
    (("ground_duels_won", "ground duels won"), "disputas_chao_ganhas", "disputas_chao"),
    (("aerials_won", "aerial duels won"), "disputas_aereas_ganhas", "disputas_aereas"),
    (("dribbles_succeeded", "successful dribbles"), "dribles_certos", "dribles"),
    (("fouls", "fouls committed"), "faltas_cometidas", None),
    (("yellow_cards", "yellow cards"), "cartao_amarelo", None),
    (("red_cards", "red cards"), "cartao_vermelho", None),
])

MAPA_INDIVIDUAL = _indexar([
    (("minutes_played", "minutes played"), "minutos", None),
    (("goals",), "gols", None),
    (("assists",), "assistencias", None),
    (("rating_title", "fotmob rating"), "rating", None),
    (("expected_goals", "expected goals (xg)"), "xg", None),
    (("expected_goals_on_target_variant", "expected_goals_on_target", "expected goals on target (xgot)"), "xgot", None),
    (("expected_assists", "expected assists (xa)"), "xa", None),
    (("xg_and_xa", "expected_goals_and_expected_assists", "xg + xa"), "xg_xa", None),
    (("line_breaking_passes", "line breaking passes"), "passes_rompendo_linhas", None),
    (("expected_goals_non_penalty", "non-penalty xg"), "xg_sem_penalti", None),
    (("total_shots", "total shots"), "chutes_total", None),
    (("shotsontarget", "shots on target"), "chutes_certos", None),
    (("shotsofftarget", "shots off target"), "chutes_fora", None),
    (("accurate_passes", "accurate passes"), "passes_certos", None),
    (("chances_created", "chances created"), "chances_criadas", None),
    (("touches",), "toques_bolas", None),
    (("touches_opp_box", "touches in opposition box"), "toques_area_adversaria", None),
    (("passes_into_final_third", "passes into final third"), "passes_terco_final", None),
    (("accurate_crosses", "crosses"), "cruzamentos_certos", "cruzamentos"),
    (("long_balls_accurate", "accurate long balls"), "passes_longos_certos", "passes_longos"),
    (("defensive_actions", "defensive actions"), "acoes_defensivas", None),
    (("matchstats.headers.tackles", "tackles", "tackles won"), "desarmes", None),
    (("recoveries",), "recuperacao_posse_bola", None),
    (("shot_blocks", "blocks"), "bloqueios", None),
    (("clearances",), "bolas_afastadas", None),
    (("headed_clearance", "headed clearance"), "bolas_afastadas_cabeca", None),
    (("interceptions",), "interceptacoes", None),
    (("dribbled_past", "dribbled past"), "dribles_sofridos", None),
    (("ground_duels_won", "ground duels won"), "disputas_chao_ganhas", "disputas_chao"),
    (("aerials_won", "aerial duels won"), "disputas_aereas_ganhas", "disputas_aereas"),
    (("was_fouled", "was fouled"), "faltas_sofridas", None),
    (("fouls", "fouls committed"), "faltas_cometidas", None),
    # --- acrescentados a partir da aba nao_mapeados
    (("offsides",), "impedimentos", None),
    (("big_chance_created_team_title", "big chances created"), "grandes_chances_criadas", None),
    (("blocked_shots", "blocked shots"), "chutes_bloqueados", None),
    (("corners",), "escanteios", None),
    (("dispossessed",), "perdas_posse_bola", None),
    (("dribbles_succeeded", "successful dribbles"), "dribles_certos", "dribles"),
    (("duel_lost", "duels lost"), "disputas_perdidas", None),
    (("duel_won", "duels won"), "disputas_ganhas", None),
    (("expected_goals_on_target_faced", "xgot faced"), "xgot_sofrido", None),
    (("goals_conceded", "goals conceded"), "gols_sofridos", None),
    (("goals_prevented", "goals prevented"), "gols_evitados", None),
    (("keeper_diving_save", "diving save"), "defesas_com_mergulho", None),
    (("keeper_high_claim", "high claim"), "bolas_altas_seguradas", None),
    (("keeper_sweeper", "acted as sweeper"), "acoes_como_libero", None),
    (("player_throws", "throws"), "laterais", None),
    (("punches",), "socos_na_bola", None),
    (("saves",), "defesas", None),
    (("saves_inside_box", "saves inside box"), "defesas_dentro_area", None),
    (("shot_accuracy", "shot accuracy"), "precisao_chutes", None),
    # --- acrescentados a partir da aba nao_mapeados (rodada seguinte)
    (("shots_woodwork", "hit_woodwork", "hit woodwork"), "chutes_trave", None),
    (("big_chance_missed_title", "big chances missed"), "grandes_chances_perdidas", None),
    (("penalties_won", "penalties won"), "penaltis_ganhos", None),
    (("conceded_penalties", "conceded penalty"), "penaltis_concedidos", None),
    (("clearance_off_the_line", "clearance off the line"), "cortes_em_cima_da_linha", None),
    (("missed_penalty", "missed penalty"), "penaltis_perdidos", None),
    (("last_man_tackle", "last man tackle"), "desarme_ultimo_homem", None),
    (("errors_led_to_goal", "error led to goal"), "erros_levaram_gol", None),
    (("owngoal", "own goal"), "gols_contra", None),
    (("saved_penalties", "saved penalties"), "penaltis_defendidos", None),
])

COLS_ESTATISTICAS = [
    "posse_bola", "xg", "xg_jogada_normal", "xg_jogada_ensaiada", "xg_sem_penalti", "xgot",
    "total_chutes", "chutes_certos", "chutes_fora", "chutes_bloqueados", "chutes_trave",
    "chutes_dentro_area", "chutes_fora_area", "grandes_chances", "grandes_chances_perdidas",
    "passes", "passes_certos", "passes_campo_defesa", "passes_campo_ataque", "passes_longos",
    "passes_longos_certos", "cruzamentos", "cruzamentos_certos", "escanteios", "laterais",
    "toques_area_adversaria", "impedimentos", "desarmes", "interceptacoes", "bloqueios",
    "bolas_afastadas", "defesas_goleiro", "disputas_ganhas", "disputas_chao",
    "disputas_chao_ganhas", "disputas_aereas", "disputas_aereas_ganhas", "dribles",
    "dribles_certos", "faltas_cometidas", "faltas_recebidas", "cartao_amarelo", "cartao_vermelho",
]
COLS_INDIVIDUAL = [
    "rating", "minutos", "gols", "assistencias", "xg", "xgot", "xa", "xg_xa", "xg_sem_penalti",
    "chutes_total", "chutes_certos", "chutes_fora", "passes_certos", "chances_criadas",
    "toques_bolas", "toques_area_adversaria", "passes_terco_final", "passes_rompendo_linhas",
    "cruzamentos", "cruzamentos_certos", "passes_longos", "passes_longos_certos",
    "acoes_defensivas", "desarmes", "bolas_roubadas", "bloqueios", "bolas_afastadas",
    "bolas_afastadas_cabeca", "interceptacoes", "recuperacao_posse_bola", "dribles_sofridos",
    "disputas_chao", "disputas_chao_ganhas", "disputas_aereas", "disputas_aereas_ganhas",
    "faltas_sofridas", "faltas_cometidas",
    # acrescentadas a partir da aba nao_mapeados
    "impedimentos", "grandes_chances_criadas", "chutes_bloqueados", "escanteios", "perdas_posse_bola",
    "dribles", "dribles_certos", "disputas_perdidas", "disputas_ganhas", "xgot_sofrido",
    "gols_sofridos", "gols_evitados", "defesas_com_mergulho", "bolas_altas_seguradas",
    "acoes_como_libero", "laterais", "socos_na_bola", "defesas", "defesas_dentro_area",
    "precisao_chutes",
    # acrescentadas a partir da aba nao_mapeados (rodada seguinte)
    "chutes_trave", "grandes_chances_perdidas", "penaltis_ganhos", "penaltis_concedidos",
    "cortes_em_cima_da_linha", "penaltis_perdidos", "desarme_ultimo_homem",
    "erros_levaram_gol", "gols_contra", "penaltis_defendidos",
]


# ---------------------------------------------------------------------------
# Navegador (mesma ideia do scraper do Sofascore: navegador real com depuração)
# ---------------------------------------------------------------------------

def _porta_debug():
    valor = os.environ.get("FOTMOB_PORTA", os.environ.get("SOFASCORE_PORTA", "9222")).strip()
    return int(valor) if valor.isdigit() else 9222


def _pasta_perfil():
    return Path(os.environ.get("FOTMOB_PERFIL") or (Path.home() / "fotmob_perfil"))


def _achar_navegador():
    candidatos = []
    env = os.environ.get("BROWSER_PATH", "").strip().strip('"')
    if env:
        candidatos.append(env)
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    candidatos += [
        rf"{pf}\BraveSoftware\Brave-Browser\Application\brave.exe",
        rf"{pf86}\BraveSoftware\Brave-Browser\Application\brave.exe",
        rf"{local}\BraveSoftware\Brave-Browser\Application\brave.exe",
        rf"{pf}\Google\Chrome\Application\chrome.exe",
        rf"{pf86}\Google\Chrome\Application\chrome.exe",
        rf"{local}\Google\Chrome\Application\chrome.exe",
        rf"{pf86}\Microsoft\Edge\Application\msedge.exe",
        rf"{pf}\Microsoft\Edge\Application\msedge.exe",
    ]
    return next((c for c in candidatos if c and os.path.isfile(c)), None)


def _versao_chromium(porta):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/json/version", timeout=2) as r:
            info = json.loads(r.read().decode("utf-8"))
        m = re.search(r"/(\d+\.\d+\.\d+\.\d+)", info.get("Browser", ""))
        return m.group(1) if m else "desconhecida"
    except Exception:
        return None


def _garantir_navegador_depuracao():
    porta = _porta_debug()
    versao = _versao_chromium(porta)
    if versao:
        logger.info("Navegador com depuração já aberto na porta %d (Chromium %s).", porta, versao)
        return None, versao
    caminho = _achar_navegador()
    if not caminho:
        raise RuntimeError(
            "Nenhum navegador encontrado. Defina BROWSER_PATH com o caminho do brave.exe / chrome.exe / msedge.exe."
        )
    perfil = _pasta_perfil()
    perfil.mkdir(parents=True, exist_ok=True)
    logger.info("Abrindo navegador: %s (perfil: %s)", caminho, perfil)
    proc = subprocess.Popen([
        caminho, f"--remote-debugging-port={porta}", f"--user-data-dir={perfil}",
        "--no-first-run", "--no-default-browser-check", "--window-size=1280,900", HOME_URL,
    ])
    for _ in range(80):
        time.sleep(0.5)
        versao = _versao_chromium(porta)
        if versao:
            return proc, versao
    raise RuntimeError(
        f"O navegador não respondeu na porta {porta}. Feche todas as janelas dele "
        "(ou use outra porta em FOTMOB_PORTA) e tente de novo."
    )


def criar_driver_anexado():
    proc, versao = _garantir_navegador_depuracao()
    opcoes = webdriver.ChromeOptions()
    opcoes.add_experimental_option("debuggerAddress", f"127.0.0.1:{_porta_debug()}")
    opcoes.page_load_strategy = "eager"
    driver = None
    try:
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", versao or ""):
            service = Service(ChromeDriverManager(driver_version=versao).install())
        else:
            service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opcoes)
    except Exception as e:
        logger.warning("webdriver_manager falhou (%s). Tentando o Selenium Manager.",
                       str(e).splitlines()[0] if str(e) else type(e).__name__)
    if driver is None:
        driver = webdriver.Chrome(options=opcoes)
    driver.set_page_load_timeout(45)
    driver.implicitly_wait(0)
    return driver, proc


def abrir_pagina(driver, url, timeout_s=30):
    try:
        driver.set_page_load_timeout(timeout_s)
        driver.get(url)
    except TimeoutException:
        logger.warning("Timeout ao abrir %s; interrompendo o carregamento pendente.", url)
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass


JS_FETCH_SAME_ORIGIN = """
var done = arguments[arguments.length - 1];
fetch(arguments[0], {method: 'GET', headers: {'Accept': 'application/json, */*'},
                     credentials: 'include', cache: 'no-store'})
.then(function(r) { return r.text().then(function(t) { done({status: r.status, body: t}); }); })
.catch(function(e) { done({status: 0, body: String(e)}); });
"""


class ClienteFotmob:
    """Busca JSONs do FotMob por camadas: fetch na página -> navegação direta -> __NEXT_DATA__."""

    def __init__(self):
        self.driver, self.proc = criar_driver_anexado()
        abrir_pagina(self.driver, HOME_URL)
        time.sleep(random.uniform(3, 5))

    def close(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        if self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                pass

    def _via_fetch(self, url):
        atual = self.driver.current_url or ""
        if "fotmob.com" not in atual:
            abrir_pagina(self.driver, HOME_URL)
            time.sleep(1.5)
        self.driver.set_script_timeout(25)
        r = self.driver.execute_async_script(JS_FETCH_SAME_ORIGIN, url)
        if not isinstance(r, dict):
            return 0, ""
        return int(r.get("status") or 0), r.get("body") or ""

    def _via_navegacao(self, url):
        abrir_pagina(self.driver, url)
        time.sleep(random.uniform(1.5, 3.0))
        elementos = self.driver.find_elements(By.TAG_NAME, "pre")
        texto = elementos[0].text if elementos else ""
        if not texto:
            texto = self.driver.execute_script("return document.body ? document.body.innerText : '';") or ""
        texto = texto.strip()
        return (200, texto) if texto[:1] in ("{", "[") else (0, texto[:200])

    def fetch_json(self, url, tentativas=2):
        for tentativa in range(1, tentativas + 1):
            for nome, camada in (("fetch", self._via_fetch), ("navegacao", self._via_navegacao)):
                try:
                    status, corpo = camada(url)
                except Exception as e:
                    logger.info("Camada %s falhou: %s", nome, str(e).splitlines()[0] if str(e) else type(e).__name__)
                    continue
                if status == 200:
                    try:
                        return json.loads(corpo)
                    except ValueError:
                        logger.info("Camada %s: resposta não é JSON.", nome)
                        continue
                logger.info("Camada %s respondeu HTTP %s para %s", nome, status, url)
            time.sleep(random.uniform(2, 4) * tentativa)
        return None

    def _next_data(self, id_jogo):
        abrir_pagina(self.driver, f"https://www.fotmob.com/match/{id_jogo}")
        time.sleep(random.uniform(4, 6))
        texto = self.driver.execute_script(
            "var e = document.getElementById('__NEXT_DATA__'); return e ? e.textContent : null;"
        )
        if not texto:
            return None
        try:
            return g(json.loads(texto), "props", "pageProps")
        except ValueError:
            return None

    def match_details(self, id_jogo):
        dados = self.fetch_json(f"{BASE_URL}/matchDetails?matchId={id_jogo}")
        if isinstance(dados, dict) and ("general" in dados or "content" in dados):
            return dados
        logger.warning("matchDetails não respondeu pela API; tentando o __NEXT_DATA__ da página do jogo.")
        dados = self._next_data(id_jogo)
        if isinstance(dados, dict) and ("general" in dados or "content" in dados):
            return dados
        raise RuntimeError("Não foi possível obter matchDetails por nenhuma das camadas.")

    def match_odds(self, id_jogo):
        reserva = None
        for ccode in (CCODE3, *CCODE3_ALTERNATIVOS):
            url = f"{BASE_URL}/matchOdds?matchId={id_jogo}&ccode3={ccode}&bettingProvider={PROVEDOR_ODDS}"
            dados = self.fetch_json(url)
            if dados is None:
                continue
            reserva = reserva or dados
            if extrair_odds_1x2(dados):
                logger.info("Odds 1X2 encontradas com ccode3=%s.", ccode)
                return dados
        if reserva is None:
            logger.warning("matchOdds não respondeu em nenhuma tentativa.")
        return reserva


# ---------------------------------------------------------------------------
# Extração
# ---------------------------------------------------------------------------

def _nome(obj):
    if not isinstance(obj, dict):
        return str(obj) if obj else None
    n = obj.get("name")
    if isinstance(n, dict):
        return n.get("fullName") or " ".join(x for x in (n.get("firstName"), n.get("lastName")) if x) or None
    return n or obj.get("fullName") or " ".join(
        x for x in (obj.get("firstName"), obj.get("lastName")) if x) or None


def _foto_jogador(pid):
    return f"https://images.fotmob.com/image_resources/playerimages/{pid}.png" if pid else None


def _logo_campeonato(lid):
    return f"https://images.fotmob.com/image_resources/logo/leaguelogo/{lid}.png" if lid else None


def extrair_estatisticas_equipe(content, ids_clubes, nomes_clubes, id_jogo, nao_mapeados):
    """Uma linha por clube e período (Completo, 1º e 2º tempo)."""
    periodos = g(content, "stats", "Periods", default={}) or {}
    linhas = []
    for periodo_en, bloco in periodos.items():
        por_lado = {"casa": {}, "fora": {}}
        derivados = {"casa": set(), "fora": set()}
        for grupo in (bloco or {}).get("stats") or []:
            for item in grupo.get("stats") or []:
                valores = item.get("stats")
                if not isinstance(valores, list) or len(valores) != 2 or all(v is None for v in valores):
                    continue  # cabeçalho de grupo
                brutos = item.get("rawStats") if isinstance(item.get("rawStats"), list) else []
                chave, titulo = str(item.get("key") or ""), str(item.get("title") or "")
                spec = MAPA_EQUIPE.get(chave.lower()) or MAPA_EQUIPE.get(titulo.lower())
                if spec is None:
                    registrar(nao_mapeados, "estatisticas", chave, titulo, valores)
                    continue
                for i, lado in enumerate(("casa", "fora")):
                    raw = brutos[i] if i < len(brutos) and isinstance(brutos[i], dict) else None
                    if raw is not None and raw.get("value") is not None:
                        valor, _, _ = parse_valor(raw.get("value"))
                        total, _, _ = parse_valor(raw.get("total"))
                        pct = None
                    else:
                        valor, total, pct = parse_valor(valores[i])
                    preencher(por_lado[lado], derivados[lado], spec, valor, total, pct)
        por_lado["casa"]["faltas_recebidas"] = por_lado["fora"].get("faltas_cometidas")
        por_lado["fora"]["faltas_recebidas"] = por_lado["casa"].get("faltas_cometidas")
        periodo = PERIODOS.get(str(periodo_en).lower(), periodo_en)
        for lado in ("casa", "fora"):
            if not por_lado[lado]:
                continue
            linhas.append({
                "jogo_id_fotmob": id_jogo,
                "clube_id_fotmob": ids_clubes[lado],
                "clube": nomes_clubes[lado],
                "mando": MANDO.get(lado, lado),
                "periodo": periodo,
                **{c: por_lado[lado].get(c) for c in COLS_ESTATISTICAS},
            })
    return linhas


def _id_jogador_fotmob(dados, chave=None):
    """FotMob às vezes manda id=0 e o ID real em optaId / na chave do dict."""
    for candidato in (dados.get("id") if isinstance(dados, dict) else None,
                      dados.get("optaId") if isinstance(dados, dict) else None,
                      chave):
        pid = _to_int(candidato)
        if pid:  # ignora None e 0
            return pid
    return None


def extrair_individual(content, lado_por_clube, nomes_por_clube, id_jogo, nao_mapeados):
    linhas = []
    for chave_jogador, dados in (content.get("playerStats") or {}).items():
        if not isinstance(dados, dict):
            continue
        if not dados.get("stats"):
            continue  # reserva que não entrou
        pid = _id_jogador_fotmob(dados, chave_jogador)
        tid = _to_int(dados.get("teamId"))
        linha, derivados = {}, set()
        for grupo in dados.get("stats") or []:
            for titulo, entrada in (grupo.get("stats") or {}).items():
                if not isinstance(entrada, dict) or entrada.get("key") is None:
                    continue  # itens sem chave (ex.: "Shotmap") não são estatísticas
                chave = str(entrada.get("key") or "")
                stat = entrada.get("stat") if isinstance(entrada.get("stat"), dict) else {}
                spec = MAPA_INDIVIDUAL.get(chave.lower()) or MAPA_INDIVIDUAL.get(str(titulo).lower())
                if spec is None:
                    registrar(nao_mapeados, "individual", chave, titulo, stat.get("value"))
                    continue
                valor, _, _ = parse_valor(stat.get("value"))
                total, _, _ = parse_valor(stat.get("total"))
                preencher(linha, derivados, spec, valor, total, None)
        linhas.append({
            "jogo_id_fotmob": id_jogo,
            "clube_id_fotmob": tid,
            "clube": nomes_por_clube.get(tid),
            "jogador_id_fotmob": pid,
            "jogador": dados.get("name"),
            "mando": MANDO.get(lado_por_clube.get(tid), lado_por_clube.get(tid)),
            **{c: linha.get(c) for c in COLS_INDIVIDUAL},
        })
    return linhas


def tipo_evento_finalizacao(chute, nao_mapeados):
    """No FotMob, finalizações bloqueadas também vêm como AttemptSaved; separamos pelo isBlocked."""
    evento = chute.get("eventType")
    if chute.get("isBlocked") and str(evento).lower() != "goal":
        return "Bloqueada"
    return traduzir(EVENTOS_FINALIZACAO, evento, "finalizacoes:tipo_evento", nao_mapeados)


def periodo_finalizacao(chute, nao_mapeados):
    bruto = chute.get("period")
    if bruto in (None, ""):
        return None
    numero = PERIODOS_FINALIZACAO.get(str(bruto).replace(" ", "").lower())
    if numero is None:
        registrar(nao_mapeados, "finalizacoes:periodo", str(bruto), "período sem número", bruto)
        return bruto
    return numero


def extrair_finalizacoes(content, lado_por_clube, nomes_por_clube, nomes_jogadores, id_jogo, nao_mapeados):
    linhas = []
    for chute in g(content, "shotmap", "shots", default=[]) or []:
        tid = _to_int(chute.get("teamId"))
        id_goleiro = _to_int(chute.get("keeperId"))  # só vem preenchido em gols e defesas
        linhas.append({
            "jogo_id_fotmob": id_jogo,
            "clube_id_fotmob": tid,
            "clube": nomes_por_clube.get(tid),
            "mando": MANDO.get(lado_por_clube.get(tid), lado_por_clube.get(tid)),
            "jogador_id_fotmob": _to_int(chute.get("playerId")),
            "jogador": chute.get("playerName") or chute.get("fullName"),
            "id_finalizacao_fotmob": _to_int(chute.get("id")),
            "tipo_evento": tipo_evento_finalizacao(chute, nao_mapeados),
            "minuto": _to_int(chute.get("min")),
            "minuto_adicional": _to_int(chute.get("minAdded")),
            "periodo": periodo_finalizacao(chute, nao_mapeados),
            "coordenada_x": _to_float(chute.get("x")),
            "coordenada_y": _to_float(chute.get("y")),
            "foi_bloqueada": chute.get("isBlocked"),
            "foi_no_alvo": chute.get("isOnTarget"),
            "bloqueio_x": _to_float(chute.get("blockedX")),
            "bloqueio_y": _to_float(chute.get("blockedY")),
            "local_x_gol": _to_float(chute.get("goalCrossedY")),
            "altura_z_gol": _to_float(chute.get("goalCrossedZ")),
            "xg": _to_float(chute.get("expectedGoals")),
            "xgot": _to_float(chute.get("expectedGoalsOnTarget")),
            "tipo_finalizacao": traduzir(TIPOS_FINALIZACAO, chute.get("shotType"), "finalizacoes:tipo_finalizacao", nao_mapeados),
            "situacao_jogada": traduzir(SITUACOES_JOGADA, chute.get("situation"), "finalizacoes:situacao_jogada", nao_mapeados),
            "foi_gol_contra": chute.get("isOwnGoal"),
            "foi_dentro_da_area": chute.get("isFromInsideBox"),
            "coordenada_chute_gol_x": _to_float(g(chute, "onGoalShot", "x")),
            "coordenada_chute_gol_y": _to_float(g(chute, "onGoalShot", "y")),
            "defendido_em_cima_da_linha": chute.get("isSavedOffLine"),
            "goleiro_id_fotmob": id_goleiro,
            "goleiro": nomes_jogadores.get(id_goleiro),
        })
    return linhas


# ---------------------------------------------------------------------------
# Odds
# ---------------------------------------------------------------------------

def _odd(x):
    """Converte para odd decimal (> 1). Aceita número, texto e fração (5/2)."""
    if isinstance(x, dict):
        for k in ("decimal", "decimalOdds", "odds", "value", "price"):
            if k in x:
                return _odd(x[k])
        return None
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x) if x > 1 else None
    if isinstance(x, str):
        t = x.strip().replace(",", ".")
        m = re.fullmatch(r"(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)", t)
        if m:
            return round(1 + float(m[1]) / float(m[2]), 2)
        try:
            v = float(t)
            return v if v > 1 else None
        except ValueError:
            return None
    return None


_ROTULOS = {"1": 0, "home": 0, "h": 0, "casa": 0, "x": 1, "draw": 1, "d": 1, "empate": 1,
            "2": 2, "away": 2, "a": 2, "fora": 2}


def achar_1x2(dados):
    """Procura, em qualquer ponto do JSON, um conjunto casa/empate/fora. Devolve (odds, caminho) ou None."""
    candidatos = []

    def visita(no, caminho):
        if isinstance(no, dict):
            baixo = {str(k).lower(): v for k, v in no.items()}
            for trio in (("home", "draw", "away"), ("1", "x", "2"), ("homewin", "draw", "awaywin")):
                if all(t in baixo for t in trio):
                    vals = [_odd(baixo[t]) for t in trio]
                    if all(v is not None for v in vals):
                        candidatos.append((vals, "/".join(caminho)))
            for k, v in no.items():
                visita(v, caminho + [str(k)])
        elif isinstance(no, list):
            achados = {}
            for item in no:
                if not isinstance(item, dict):
                    continue
                rotulo = next((str(item[k]).strip().lower() for k in ("name", "label", "outcome", "type", "selection", "key")
                               if k in item and isinstance(item[k], (str, int))), None)
                valor = next((_odd(item[k]) for k in ("oddsDecimal", "odds", "value", "price", "decimal", "decimalOdds")
                              if k in item and _odd(item[k]) is not None), None)
                if rotulo in _ROTULOS and valor is not None:
                    achados.setdefault(_ROTULOS[rotulo], valor)
            if len(achados) == 3:
                candidatos.append(([achados[0], achados[1], achados[2]], "/".join(caminho)))
            for i, item in enumerate(no):
                visita(item, caminho + [str(i)])

    visita(dados, [])
    if not candidatos:
        return None
    preferido = next((c for c in candidatos if re.search(r"1x2|match|full|winner", c[1], re.I)), candidatos[0])
    return preferido


def extrair_odds_1x2(dados):
    """Devolve (odd_casa, odd_empate, odd_fora) ou None. Formato do FotMob: odds.resolvedOddsMarket.selections."""
    selecoes = g(dados, "odds", "resolvedOddsMarket", "selections")
    if isinstance(selecoes, list):
        achados = {}
        for sel in selecoes:
            if not isinstance(sel, dict):
                continue
            posicao = _ROTULOS.get(str(sel.get("name") or "").strip().lower(),
                                   _ROTULOS.get(str(sel.get("team") or "").strip().lower()))
            valor = _odd(sel.get("oddsDecimal"))
            if posicao is not None and valor is not None:
                achados.setdefault(posicao, valor)
        if len(achados) == 3:
            return achados[0], achados[1], achados[2]
    achado = achar_1x2(dados)  # plano B: procura em qualquer ponto do JSON
    return tuple(achado[0]) if achado else None


# ---------------------------------------------------------------------------
# Montagem das tabelas
# ---------------------------------------------------------------------------

def temporada_do_jogo(general, info, data):
    """Temporada informada, ou inferida pela data quando o FotMob não a traz."""
    temporada = (TEMPORADA or general.get("parentLeagueSeason") or g(info, "Tournament", "parentLeagueSeason")
                 or g(info, "Tournament", "selectedSeason"))
    if temporada or not data:
        return temporada
    inicio = data.year if data.month >= 7 else data.year - 1
    logger.warning("Temporada não informada pelo FotMob; inferida pela data: %s/%s. "
                   "Defina TEMPORADA no topo do script se não for essa.", inicio, inicio + 1)
    return f"{inicio}/{inicio + 1}"


def pais_do_clube(equipe, pais_campeonato):
    """País do clube: dado da própria equipe, se o FotMob trouxer; senão, o do campeonato (quando nacional)."""
    if isinstance(equipe, dict):
        nome, cod = equipe.get("country") or equipe.get("countryName"), equipe.get("countryCode") or equipe.get("ccode")
        if nome or cod:
            return pais_info(nome, cod)[0]
    return pais_campeonato


def jogo_finalizado(det) -> bool:
    """True só quando o FotMob marca a partida como finalizada."""
    if not isinstance(det, dict):
        return False
    general = det.get("general") or {}
    header = det.get("header") or {}
    if general.get("finished") or g(header, "status", "finished"):
        return True
    # Alguns payloads só trazem a chave textual do resultado
    reason = g(header, "status", "reason", "longKey") or g(header, "status", "reason", "shortKey")
    if isinstance(reason, str) and reason.lower() in ("finished", "fulltime_short", "fulltime"):
        return True
    return False


def montar_tabelas(det, odds_json, id_jogo):
    if not jogo_finalizado(det):
        logger.info("Jogo %s ignorado: status não finalizado.", id_jogo)
        return None

    nao_mapeados = {}
    agora = datetime.now(BRASILIA_TZ).replace(tzinfo=None, microsecond=0)  # timestamp da coleta
    general = det.get("general") or {}
    header = det.get("header") or {}
    content = det.get("content") or {}
    info = g(content, "matchFacts", "infoBox", default={}) or {}

    # --- times e placar
    ids = {
        "casa": _to_int(g(general, "homeTeam", "id") or g(header, "teams", 0, "id")),
        "fora": _to_int(g(general, "awayTeam", "id") or g(header, "teams", 1, "id")),
    }
    nomes = {
        "casa": g(general, "homeTeam", "name") or g(header, "teams", 0, "name"),
        "fora": g(general, "awayTeam", "name") or g(header, "teams", 1, "name"),
    }
    gols = {"casa": _to_int(g(header, "teams", 0, "score")), "fora": _to_int(g(header, "teams", 1, "score"))}
    lado_por_clube = {ids["casa"]: "casa", ids["fora"]: "fora"}
    nomes_por_clube = {ids["casa"]: nomes["casa"], ids["fora"]: nomes["fora"]}

    # --- posição exata: positionLabel / positionId no JSON do jogo
    posicao_rotulo = mapear_posicoes(det, {})

    # --- escalações, técnicos e jogadores
    lineup = content.get("lineup") or {}
    if isinstance(lineup.get("homeTeam"), dict):
        equipes = [lineup["homeTeam"], lineup.get("awayTeam") or {}]
    elif isinstance(lineup.get("lineup"), list):
        equipes = lineup["lineup"]
    else:
        equipes = []

    def posicao_jogador(pid, generica, position_id=None):
        rotulo = posicao_rotulo.get(pid)
        if not rotulo and position_id is not None:
            rotulo = POSICAO_POR_POSITION_ID.get(_to_int(position_id))
            if rotulo:
                posicao_rotulo.setdefault(pid, rotulo)
        if rotulo:
            return traduzir_posicao_exata(rotulo, nao_mapeados)
        return POSICOES.get(_to_int(generica))

    tecnicos, jogadores = {}, {}
    for eq in equipes:
        tid = _to_int(eq.get("id") or eq.get("teamId"))
        coach = eq.get("coach")
        if isinstance(coach, list):
            coach = coach[0] if coach else None
        if isinstance(coach, dict) and (coach.get("id") or _nome(coach)):
            tecnicos[tid] = {
                "id_fotmob": _to_int(coach.get("id")), "nome": _nome(coach),
                "nacionalidade": traduzir_pais(coach.get("countryName"), coach.get("countryCode")),
            }
        for p in (eq.get("starters") or []) + (eq.get("subs") or []):
            pid = _to_int(p.get("id"))
            if pid is None:
                continue
            jogadores[pid] = {
                "id_fotmob": pid, "nome": _nome(p),
                "posicao": posicao_jogador(pid, p.get("usualPlayingPositionId"), p.get("positionId")),
                "nacionalidade": traduzir_pais(
                    p.get("countryName") or p.get("nationality"),
                    p.get("countryCode") or p.get("ccode"),
                ),
                "foto": _foto_jogador(pid),
            }

    # Só inclui quem de fato jogou (tem stats). Fantasmas com id=0/sem escalação são ignorados.
    for chave, dados in (content.get("playerStats") or {}).items():
        if not isinstance(dados, dict) or not dados.get("stats"):
            continue
        pid = _id_jogador_fotmob(dados, chave)
        if pid is None:
            continue
        pos = posicao_jogador(
            pid,
            g(dados, "usualPosition") or g(dados, "usualPlayingPositionId"),
            dados.get("positionId"),
        )
        nac = traduzir_pais(
            dados.get("countryName") or dados.get("nationality"),
            dados.get("countryCode") or dados.get("ccode"),
        )
        if pid in jogadores:
            # Preferir posição exata (já mapeada) sobre genérica já gravada
            if pid in posicao_rotulo:
                jogadores[pid]["posicao"] = traduzir_posicao_exata(posicao_rotulo[pid], nao_mapeados)
            elif not jogadores[pid].get("posicao") and pos:
                jogadores[pid]["posicao"] = pos
            if not jogadores[pid].get("nacionalidade") and nac:
                jogadores[pid]["nacionalidade"] = nac
        else:
            jogadores[pid] = {
                "id_fotmob": pid, "nome": dados.get("name"),
                "posicao": pos, "nacionalidade": nac, "foto": _foto_jogador(pid),
            }

    # Reservas / fora da escalação sem positionId: posição principal via playerData
    for pid, j in jogadores.items():
        if pid in posicao_rotulo:
            continue
        rotulo = buscar_posicao_player_data(pid)
        if not rotulo:
            continue
        posicao_rotulo[pid] = rotulo
        j["posicao"] = traduzir_posicao_exata(rotulo, nao_mapeados)

    nomes_jogadores = {pid: j["nome"] for pid, j in jogadores.items()}

    # --- campeonato
    id_camp = _to_int(general.get("parentLeagueId") or general.get("leagueId"))
    nome_camp = general.get("parentLeagueName") or general.get("leagueName")
    pais_camp, continente_camp = pais_info(None, general.get("countryCode"))
    if pais_camp == continente_camp:  # competição internacional/continental: não tem país
        pais_camp_tabela = None
        pais_para_clubes = None
    else:
        pais_camp_tabela = pais_camp
        pais_para_clubes = pais_camp

    # --- jogo
    iso = general.get("matchTimeUTCDate") or g(header, "status", "utcTime")
    data = None
    if iso:
        try:
            data = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(BRASILIA_TZ).date()
        except ValueError:
            logger.warning("Data do jogo em formato inesperado: %r", iso)
    temporada = temporada_do_jogo(general, info, data)
    rodada_bruta = general.get("matchRound") or general.get("leagueRoundName")
    rodada = f"Rodada {rodada_bruta}" if str(rodada_bruta or "").isdigit() else rodada_bruta

    arbitro = info.get("Referee") if isinstance(info.get("Referee"), dict) else {}
    estadio = info.get("Stadium") if isinstance(info.get("Stadium"), dict) else {}
    publico = info.get("Attendance")
    publico = _to_int(publico.get("value") if isinstance(publico, dict) else publico)

    jogo = {
        "id_fotmob": id_jogo, "temporada": temporada, "data": data,
        "campeonato_id_fotmob": id_camp, "campeonato": nome_camp, "rodada": rodada,
        "casa_id_fotmob": ids["casa"], "casa": nomes["casa"], "gols_casa": gols["casa"],
        "gols_fora": gols["fora"], "fora_id_fotmob": ids["fora"], "fora": nomes["fora"],
        "tecnico_casa_id_fotmob": g(tecnicos, ids["casa"], "id_fotmob"),
        "tecnico_casa": g(tecnicos, ids["casa"], "nome"),
        "tecnico_fora_id_fotmob": g(tecnicos, ids["fora"], "id_fotmob"),
        "tecnico_fora": g(tecnicos, ids["fora"], "nome"),
        "arbitro_id_fotmob": _to_int(arbitro.get("id")),
        "arbitro": arbitro.get("text"),
        "estadio": estadio.get("name"),
        "capacidade": _to_int(estadio.get("capacity")),
        "publico": publico,
    }

    # --- fatos
    estatisticas = extrair_estatisticas_equipe(content, ids, nomes, id_jogo, nao_mapeados)
    individual = extrair_individual(content, lado_por_clube, nomes_por_clube, id_jogo, nao_mapeados)
    finalizacoes = extrair_finalizacoes(content, lado_por_clube, nomes_por_clube, nomes_jogadores,
                                        id_jogo, nao_mapeados)

    # --- odds
    odds_linhas = []
    if odds_json:
        achado = extrair_odds_1x2(odds_json)
        if achado:
            provedor = odds_json.get("persistentKey") if isinstance(odds_json, dict) else None
            odds_linhas.append({
                "jogo_id_fotmob": id_jogo, "odd_casa": achado[0], "odd_empate": achado[1],
                "odd_fora": achado[2], "casa_de_apostas": limpar_provedor(provedor or PROVEDOR_ODDS),
            })
        else:
            logger.warning("Odds 1X2 não identificadas automaticamente; veja o JSON salvo em fotmob_raw.")

    # --- clubes
    clubes_info = {}
    for lado in ("casa", "fora"):
        equipe = general.get("homeTeam" if lado == "casa" else "awayTeam")
        clubes_info[lado] = {"clube_id": ids[lado], "clube": nomes[lado],
                             "pais": pais_do_clube(equipe, pais_para_clubes)}

    # --- dimensões (países com continente)
    arbitro_pais, arbitro_continente = (pais_info(arbitro.get("country"), arbitro.get("countryCode"))
                                        if arbitro else (None, None))
    nomes_paises = {}

    def add_pais(nome):
        if not nome:
            return
        p, c = pais_info(nome)
        if p and p != c:  # ignora "Internacional"/"Europa" (competições, não países)
            nomes_paises[p] = c

    add_pais(pais_camp_tabela)
    add_pais(arbitro_pais)
    for j in jogadores.values():
        add_pais(j["nacionalidade"])
    for t in tecnicos.values():
        add_pais(t["nacionalidade"])
    for c in clubes_info.values():
        add_pais(c["pais"])

    abas = {
        "paises": pd.DataFrame(
            [{"nome": n, "continente": c} for n, c in sorted(nomes_paises.items())],
            columns=["nome", "continente"]),
        "campeonatos": pd.DataFrame(
            [{"id_fotmob": id_camp, "nome": nome_camp, "pais": pais_camp_tabela, "continente": continente_camp,
              "logo": _logo_campeonato(id_camp)}] if id_camp else [],
            columns=["id_fotmob", "nome", "pais", "continente", "logo"]),
        "clubes": pd.DataFrame(
            [{"clube_id": c["clube_id"], "clube": c["clube"], "pais": c["pais"]} for c in clubes_info.values()],
            columns=["clube_id", "clube", "pais"]),
        "clubes_fontes": pd.DataFrame(
            [{"clube": c["clube"], "pais": c["pais"], "fonte": FONTE, "id_externo": c["clube_id"],
              "nome_externo": c["clube"]} for c in clubes_info.values()],
            columns=["clube", "pais", "fonte", "id_externo", "nome_externo"]),
        "tecnicos": pd.DataFrame(list(tecnicos.values()), columns=["id_fotmob", "nome", "nacionalidade"]),
        "arbitros": pd.DataFrame(
            [{"id_fotmob": _to_int(arbitro.get("id")), "nome": arbitro.get("text"), "nacionalidade": arbitro_pais,
              "foto": None}] if arbitro.get("text") else [],
            columns=["id_fotmob", "nome", "nacionalidade", "foto"]),
        "jogadores": pd.DataFrame(
            [{"id_fotmob": j["id_fotmob"], "nome": j["nome"], "posicao": j["posicao"],
              "nacionalidade": j["nacionalidade"], "foto": j["foto"]} for j in jogadores.values()],
            columns=["id_fotmob", "nome", "posicao", "nacionalidade", "foto"]),
        "jogos": pd.DataFrame([jogo], columns=list(jogo)),
        "odds_fotmob": pd.DataFrame(
            odds_linhas, columns=["jogo_id_fotmob", "odd_casa", "odd_empate", "odd_fora", "casa_de_apostas"]),
        "estatisticas": pd.DataFrame(
            estatisticas, columns=["jogo_id_fotmob", "clube_id_fotmob", "clube", "mando", "periodo"] + COLS_ESTATISTICAS),
        "individual": pd.DataFrame(
            individual, columns=["jogo_id_fotmob", "clube_id_fotmob", "clube", "jogador_id_fotmob", "jogador", "mando"]
            + COLS_INDIVIDUAL),
        "finalizacoes": pd.DataFrame(finalizacoes, columns=[
            "jogo_id_fotmob", "clube_id_fotmob", "clube", "mando", "jogador_id_fotmob", "jogador",
            "id_finalizacao_fotmob", "tipo_evento", "minuto", "minuto_adicional", "periodo",
            "coordenada_x", "coordenada_y", "foi_bloqueada", "foi_no_alvo", "bloqueio_x", "bloqueio_y",
            "local_x_gol", "altura_z_gol", "xg", "xgot", "tipo_finalizacao", "situacao_jogada",
            "foi_gol_contra", "foi_dentro_da_area", "coordenada_chute_gol_x", "coordenada_chute_gol_y",
            "defendido_em_cima_da_linha", "goleiro_id_fotmob", "goleiro"]),
        "nao_mapeados": pd.DataFrame(
            [{"escopo": e, "chave": c, "titulo": t, "exemplo": str(ex)[:120]}
             for (e, c, t), ex in sorted(nao_mapeados.items())],
            columns=["escopo", "chave", "titulo", "exemplo"]),
    }

    # --- timestamps da coleta em todas as tabelas
    for df in abas.values():
        df["criado_em"] = agora
        df["atualizado_em"] = agora
    return abas


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------

def carregar_variaveis_de_ambiente(pasta=None):
    pasta = Path(pasta or DIR)
    candidatos = [pasta / ".env", pasta.parent / ".env"]
    for env_path in candidatos:
        if not env_path.is_file():
            continue
        for linha in env_path.read_text(encoding="utf-8-sig").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            if linha.lower().startswith("export "):
                linha = linha[7:].strip()
            chave, valor = linha.split("=", 1)
            chave, valor = chave.strip(), valor.strip().strip('"').strip("'")
            if chave and valor:
                os.environ.setdefault(chave, valor)
        logger.info("Variáveis de ambiente lidas de %s", env_path)
        return
    logger.warning("Arquivo .env não encontrado em %s", pasta)


@contextmanager
def conexao_bd():
    dsn = os.environ.get("SUPABASE_DB_URL")
    if not dsn:
        raise RuntimeError(
            "Variável de ambiente SUPABASE_DB_URL não definida. "
            "Configure-a no arquivo .env na raiz do projeto."
        )
    conn = psycopg2.connect(dsn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _limpo(valor):
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(valor, pd.Timestamp):
        return valor.to_pydatetime()
    if hasattr(valor, "item"):
        try:
            return valor.item()
        except Exception:
            pass
    return valor


def _linhas_df(df):
    if df is None or getattr(df, "empty", True):
        return []
    return [{k: _limpo(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def maior_data_campeonato(conn, id_fotmob_campeonato, temporada=None):
    """Maior data de jogo JÁ COLETADO (com placar) do campeonato + temporada.

    Ignora stubs do calendário (gols NULL / datas futuras): o corte incremental
    é por data, não por rodada (antecipados/adiados entram quando a data passar).
    """
    if not id_fotmob_campeonato:
        return None
    with conn.cursor() as cur:
        if temporada:
            cur.execute(
                """
                SELECT MAX(j.data)
                FROM jogos j
                JOIN campeonatos c ON c.id = j.campeonato_id
                WHERE c.id_fotmob = %s AND j.temporada = %s
                  AND j.gols_casa IS NOT NULL
                """,
                (int(id_fotmob_campeonato), str(temporada)),
            )
        else:
            cur.execute(
                """
                SELECT MAX(j.data)
                FROM jogos j
                JOIN campeonatos c ON c.id = j.campeonato_id
                WHERE c.id_fotmob = %s
                  AND j.gols_casa IS NOT NULL
                """,
                (int(id_fotmob_campeonato),),
            )
        valor = cur.fetchone()[0]
    if isinstance(valor, datetime):
        return valor.date()
    return valor


def jogo_ja_existe(conn, id_fotmob):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM jogos WHERE id_fotmob = %s", (int(id_fotmob),))
        row = cur.fetchone()
    return row[0] if row else None


def resumo_jogo_fotmob(conn, id_fotmob):
    """Retorna {id, data, gols_casa, campeonato_id_fotmob, temporada} ou None."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT j.id, j.data, j.gols_casa, j.temporada, c.id_fotmob AS campeonato_id_fotmob
            FROM jogos j
            JOIN campeonatos c ON c.id = j.campeonato_id
            WHERE j.id_fotmob = %s
            """,
            (int(id_fotmob),),
        )
        row = cur.fetchone()
    if not row:
        return None
    data = row[1]
    if isinstance(data, datetime):
        data = data.date()
    return {
        "id": row[0],
        "data": data,
        "gols_casa": row[2],
        "temporada": row[3],
        "campeonato_id_fotmob": row[4],
    }


def garantir_continente(cur, nome, cache):
    if not nome:
        return None
    if nome in cache:
        return cache[nome]
    cur.execute("SELECT id FROM continentes WHERE lower(btrim(nome)) = lower(btrim(%s))", (nome,))
    row = cur.fetchone()
    if row:
        cache[nome] = row[0]
        return row[0]
    cur.execute("INSERT INTO continentes (nome) VALUES (%s) RETURNING id", (nome,))
    cache[nome] = cur.fetchone()[0]
    return cache[nome]


def garantir_pais(cur, nome, continente_nome, cache_paises, cache_continentes):
    if not nome or nome == continente_nome:
        return None
    if nome in cache_paises:
        return cache_paises[nome]
    cur.execute("SELECT id FROM paises WHERE lower(btrim(nome)) = lower(btrim(%s))", (nome,))
    row = cur.fetchone()
    if row:
        cache_paises[nome] = row[0]
        return row[0]
    continente_id = garantir_continente(cur, continente_nome, cache_continentes) if continente_nome else None
    cur.execute(
        "INSERT INTO paises (nome, continente_id) VALUES (%s, %s) RETURNING id",
        (nome, continente_id),
    )
    cache_paises[nome] = cur.fetchone()[0]
    return cache_paises[nome]


def garantir_campeonato(cur, id_fotmob, nome, pais_id, abrangencia, logo, cache):
    if id_fotmob in cache:
        return cache[id_fotmob]
    cur.execute("SELECT id FROM campeonatos WHERE id_fotmob = %s", (id_fotmob,))
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE campeonatos
            SET nome = COALESCE(%s, nome),
                pais_id = COALESCE(%s, pais_id),
                abrangencia = COALESCE(%s, abrangencia),
                logo = COALESCE(%s, logo),
                atualizado_em = now()
            WHERE id = %s
            """,
            (nome, pais_id, abrangencia, logo, row[0]),
        )
        cache[id_fotmob] = row[0]
        return row[0]
    cur.execute(
        """
        INSERT INTO campeonatos (id_fotmob, nome, pais_id, abrangencia, logo)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (id_fotmob, nome or f"Campeonato {id_fotmob}", pais_id, abrangencia, logo),
    )
    cache[id_fotmob] = cur.fetchone()[0]
    return cache[id_fotmob]


def garantir_clube(cur, id_externo, nome_externo, pais_id, cache):
    """Resolve clube interno via clubes_fontes (fonte=fotmob). Nome canônico fica em clubes.clube."""
    chave = str(id_externo)
    if chave in cache:
        return cache[chave]
    cur.execute(
        "SELECT clube_id FROM clubes_fontes WHERE fonte = %s AND id_externo = %s",
        (FONTE, chave),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE clubes_fontes
            SET nome_externo = COALESCE(%s, nome_externo), atualizado_em = now()
            WHERE fonte = %s AND id_externo = %s
            """,
            (nome_externo, FONTE, chave),
        )
        cache[chave] = row[0]
        return row[0]

    nome = (nome_externo or "").strip() or f"Clube {chave}"
    cur.execute(
        """
        SELECT id FROM clubes
        WHERE lower(btrim(clube)) = lower(btrim(%s))
          AND COALESCE(pais_id, -1) = COALESCE(%s, -1)
        """,
        (nome, pais_id),
    )
    row = cur.fetchone()
    if row:
        clube_id = row[0]
    else:
        cur.execute(
            "INSERT INTO clubes (pais_id, clube) VALUES (%s, %s) RETURNING id",
            (pais_id, nome),
        )
        clube_id = cur.fetchone()[0]

    cur.execute(
        """
        INSERT INTO clubes_fontes (clube_id, fonte, id_externo, nome_externo)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (fonte, id_externo) DO UPDATE
          SET nome_externo = EXCLUDED.nome_externo, atualizado_em = now()
        RETURNING clube_id
        """,
        (clube_id, FONTE, chave, nome_externo or nome),
    )
    cache[chave] = cur.fetchone()[0]
    return cache[chave]


def garantir_tecnico(cur, id_fotmob, nome, nacionalidade, cache):
    if not nome and not id_fotmob:
        return None
    if id_fotmob and id_fotmob in cache:
        return cache[id_fotmob]
    if id_fotmob:
        cur.execute("SELECT id FROM tecnicos WHERE id_fotmob = %s", (id_fotmob,))
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE tecnicos
                SET nome = COALESCE(%s, nome),
                    nacionalidade = COALESCE(%s, nacionalidade),
                    atualizado_em = now()
                WHERE id = %s
                """,
                (nome, nacionalidade, row[0]),
            )
            cache[id_fotmob] = row[0]
            return row[0]
        cur.execute(
            """
            INSERT INTO tecnicos (id_fotmob, nome, nacionalidade)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (id_fotmob, nome or f"Técnico {id_fotmob}", nacionalidade),
        )
        cache[id_fotmob] = cur.fetchone()[0]
        return cache[id_fotmob]

    cur.execute(
        "SELECT id FROM tecnicos WHERE id_fotmob IS NULL AND lower(btrim(nome)) = lower(btrim(%s))",
        (nome,),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO tecnicos (nome, nacionalidade) VALUES (%s, %s) RETURNING id",
        (nome, nacionalidade),
    )
    return cur.fetchone()[0]


def garantir_arbitro(cur, id_fotmob, nome, pais_id, foto, cache):
    if not nome and not id_fotmob:
        return None
    if id_fotmob and id_fotmob in cache:
        return cache[id_fotmob]
    if id_fotmob:
        cur.execute("SELECT id FROM arbitros WHERE id_fotmob = %s", (id_fotmob,))
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE arbitros
                SET nome = COALESCE(%s, nome),
                    pais_id = COALESCE(%s, pais_id),
                    foto = COALESCE(%s, foto),
                    atualizado_em = now()
                WHERE id = %s
                """,
                (nome, pais_id, foto, row[0]),
            )
            cache[id_fotmob] = row[0]
            return row[0]
    if nome:
        cur.execute("SELECT id FROM arbitros WHERE lower(btrim(nome)) = lower(btrim(%s))", (nome,))
        row = cur.fetchone()
        if row:
            if id_fotmob:
                cur.execute(
                    """
                    UPDATE arbitros
                    SET id_fotmob = COALESCE(id_fotmob, %s),
                        pais_id = COALESCE(%s, pais_id),
                        foto = COALESCE(%s, foto),
                        atualizado_em = now()
                    WHERE id = %s
                    """,
                    (id_fotmob, pais_id, foto, row[0]),
                )
            if id_fotmob:
                cache[id_fotmob] = row[0]
            return row[0]
    cur.execute(
        """
        INSERT INTO arbitros (id_fotmob, nome, pais_id, foto)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (id_fotmob, nome or f"Árbitro {id_fotmob}", pais_id, foto),
    )
    arb_id = cur.fetchone()[0]
    if id_fotmob:
        cache[id_fotmob] = arb_id
    return arb_id


def garantir_jogador(cur, id_externo, nome, posicao, nacionalidade, foto, cache):
    if not id_externo:
        return None
    chave = str(id_externo)
    if chave in cache:
        return cache[chave]
    cur.execute(
        "SELECT jogador_id FROM jogadores_fontes WHERE fonte = %s AND id_externo = %s",
        (FONTE, chave),
    )
    row = cur.fetchone()
    if row:
        jogador_id = row[0]
        cur.execute(
            """
            UPDATE jogadores
            SET nome = COALESCE(%s, nome),
                posicao = COALESCE(%s, posicao),
                nacionalidade = COALESCE(%s, nacionalidade),
                foto = COALESCE(%s, foto),
                atualizado_em = now()
            WHERE id = %s
            """,
            (nome, posicao, nacionalidade, foto, jogador_id),
        )
        cur.execute(
            """
            UPDATE jogadores_fontes
            SET nome_externo = COALESCE(%s, nome_externo), atualizado_em = now()
            WHERE fonte = %s AND id_externo = %s
            """,
            (nome, FONTE, chave),
        )
        cache[chave] = jogador_id
        return jogador_id

    cur.execute(
        """
        INSERT INTO jogadores (nome, posicao, nacionalidade, foto)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (nome or f"Jogador {chave}", posicao, nacionalidade, foto),
    )
    jogador_id = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO jogadores_fontes (jogador_id, fonte, id_externo, nome_externo)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (fonte, id_externo) DO UPDATE
          SET nome_externo = EXCLUDED.nome_externo, atualizado_em = now()
        RETURNING jogador_id
        """,
        (jogador_id, FONTE, chave, nome or f"Jogador {chave}"),
    )
    cache[chave] = cur.fetchone()[0]
    return cache[chave]


def upsert_jogo(cur, dados):
    cur.execute("SELECT id FROM jogos WHERE id_fotmob = %s", (dados["id_fotmob"],))
    row = cur.fetchone()
    cols = [
        "temporada", "data", "campeonato_id", "rodada", "casa_id", "fora_id",
        "gols_casa", "gols_fora", "tecnico_casa_id", "tecnico_fora_id", "arbitro_id",
        "estadio", "capacidade", "publico",
    ]
    if row:
        sets = ", ".join(f"{c} = %s" for c in cols) + ", atualizado_em = now()"
        cur.execute(
            f"UPDATE jogos SET {sets} WHERE id = %s",
            [dados.get(c) for c in cols] + [row[0]],
        )
        return row[0]
    cur.execute(
        f"""
        INSERT INTO jogos (id_fotmob, {", ".join(cols)})
        VALUES (%s, {", ".join(["%s"] * len(cols))})
        RETURNING id
        """,
        [dados["id_fotmob"]] + [dados.get(c) for c in cols],
    )
    return cur.fetchone()[0]


def upsert_estatisticas(cur, jogo_id, linhas, mapa_clubes):
    for linha in linhas:
        clube_id = mapa_clubes.get(str(linha.get("clube_id_fotmob")))
        if not clube_id:
            continue
        periodo = linha.get("periodo")
        periodo = None if periodo is None else str(periodo)
        valores = {c: linha.get(c) for c in COLS_ESTATISTICAS}
        cur.execute(
            """
            SELECT id FROM estatisticas
            WHERE jogo_id = %s AND clube_id = %s AND periodo IS NOT DISTINCT FROM %s
            """,
            (jogo_id, clube_id, periodo),
        )
        row = cur.fetchone()
        if row:
            sets = ", ".join(f"{c} = %s" for c in COLS_ESTATISTICAS)
            cur.execute(
                f"""
                UPDATE estatisticas
                SET mando = %s, {sets}, atualizado_em = now()
                WHERE id = %s
                """,
                [linha.get("mando")] + [valores[c] for c in COLS_ESTATISTICAS] + [row[0]],
            )
        else:
            cur.execute(
                f"""
                INSERT INTO estatisticas
                  (jogo_id, clube_id, mando, periodo, {", ".join(COLS_ESTATISTICAS)})
                VALUES (%s, %s, %s, %s, {", ".join(["%s"] * len(COLS_ESTATISTICAS))})
                """,
                [jogo_id, clube_id, linha.get("mando"), periodo]
                + [valores[c] for c in COLS_ESTATISTICAS],
            )


def upsert_individual(cur, jogo_id, linhas, mapa_clubes, mapa_jogadores):
    for linha in linhas:
        jogador_id = mapa_jogadores.get(str(linha.get("jogador_id_fotmob")))
        clube_id = mapa_clubes.get(str(linha.get("clube_id_fotmob")))
        if not jogador_id or not clube_id:
            continue
        valores = {c: linha.get(c) for c in COLS_INDIVIDUAL}
        cur.execute(
            "SELECT id FROM individual WHERE jogo_id = %s AND jogador_id = %s",
            (jogo_id, jogador_id),
        )
        row = cur.fetchone()
        if row:
            sets = ", ".join(f"{c} = %s" for c in COLS_INDIVIDUAL)
            cur.execute(
                f"""
                UPDATE individual
                SET clube_id = %s, mando = %s, {sets}, atualizado_em = now()
                WHERE id = %s
                """,
                [clube_id, linha.get("mando")] + [valores[c] for c in COLS_INDIVIDUAL] + [row[0]],
            )
        else:
            cur.execute(
                f"""
                INSERT INTO individual
                  (jogo_id, clube_id, jogador_id, mando, {", ".join(COLS_INDIVIDUAL)})
                VALUES (%s, %s, %s, %s, {", ".join(["%s"] * len(COLS_INDIVIDUAL))})
                """,
                [jogo_id, clube_id, jogador_id, linha.get("mando")]
                + [valores[c] for c in COLS_INDIVIDUAL],
            )


COLS_FINALIZACOES_DB = [
    "mando", "id_finalizacao_fotmob", "tipo_evento", "minuto", "minuto_adicional", "periodo",
    "coordenada_x", "coordenada_y", "foi_bloqueada", "foi_no_alvo", "bloqueio_x", "bloqueio_y",
    "local_x_gol", "altura_z_gol", "xg", "xgot", "tipo_finalizacao", "situacao_jogada",
    "foi_gol_contra", "foi_dentro_da_area", "coordenada_chute_gol_x", "coordenada_chute_gol_y",
    "defendido_em_cima_da_linha",
]


def upsert_finalizacoes(cur, jogo_id, linhas, mapa_clubes, mapa_jogadores):
    for linha in linhas:
        clube_id = mapa_clubes.get(str(linha.get("clube_id_fotmob")))
        if not clube_id:
            continue
        jogador_id = mapa_jogadores.get(str(linha.get("jogador_id_fotmob")))
        goleiro_id = mapa_jogadores.get(str(linha.get("goleiro_id_fotmob")))
        id_ext = linha.get("id_finalizacao_fotmob")
        vals = []
        for c in COLS_FINALIZACOES_DB:
            v = linha.get(c)
            if c == "periodo" and v is not None:
                v = str(v)
            vals.append(v)
        if id_ext is not None:
            cur.execute("SELECT id FROM finalizacoes WHERE id_finalizacao_fotmob = %s", (id_ext,))
            row = cur.fetchone()
            if row:
                sets = ", ".join(f"{c} = %s" for c in COLS_FINALIZACOES_DB)
                cur.execute(
                    f"""
                    UPDATE finalizacoes
                    SET jogo_id = %s, clube_id = %s, jogador_id = %s, goleiro_id = %s,
                        {sets}, atualizado_em = now()
                    WHERE id = %s
                    """,
                    [jogo_id, clube_id, jogador_id, goleiro_id] + vals + [row[0]],
                )
                continue
        cur.execute(
            f"""
            INSERT INTO finalizacoes
              (jogo_id, clube_id, jogador_id, goleiro_id, {", ".join(COLS_FINALIZACOES_DB)})
            VALUES (%s, %s, %s, %s, {", ".join(["%s"] * len(COLS_FINALIZACOES_DB))})
            """,
            [jogo_id, clube_id, jogador_id, goleiro_id] + vals,
        )


def upsert_odds(cur, jogo_id, linhas):
    if not linhas:
        return
    linha = linhas[0]
    cur.execute("SELECT id FROM odds_fotmob WHERE jogo_id = %s", (jogo_id,))
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE odds_fotmob
            SET odd_casa = %s, odd_empate = %s, odd_fora = %s, atualizado_em = now()
            WHERE id = %s
            """,
            (linha.get("odd_casa"), linha.get("odd_empate"), linha.get("odd_fora"), row[0]),
        )
    else:
        cur.execute(
            """
            INSERT INTO odds_fotmob (jogo_id, odd_casa, odd_empate, odd_fora)
            VALUES (%s, %s, %s, %s)
            """,
            (jogo_id, linha.get("odd_casa"), linha.get("odd_empate"), linha.get("odd_fora")),
        )


def salvar_jogo_no_banco(conn, abas, caches=None):
    """Persiste um jogo (e dimensões) no schema normalizado. Retorna id interno do jogo."""
    caches = caches or {}
    cache_continentes = caches.setdefault("continentes", {})
    cache_paises = caches.setdefault("paises", {})
    cache_campeonatos = caches.setdefault("campeonatos", {})
    cache_clubes = caches.setdefault("clubes", {})
    cache_tecnicos = caches.setdefault("tecnicos", {})
    cache_arbitros = caches.setdefault("arbitros", {})
    cache_jogadores = caches.setdefault("jogadores", {})

    jogos = _linhas_df(abas.get("jogos"))
    if not jogos:
        return None
    jogo = jogos[0]

    with conn.cursor() as cur:
        for p in _linhas_df(abas.get("paises")):
            garantir_pais(cur, p.get("nome"), p.get("continente"), cache_paises, cache_continentes)

        camp = (_linhas_df(abas.get("campeonatos")) or [None])[0]
        id_fotmob_camp = jogo.get("campeonato_id_fotmob") or (camp or {}).get("id_fotmob")
        if not id_fotmob_camp:
            raise ValueError(f"Jogo {jogo.get('id_fotmob')} sem campeonato_id_fotmob")
        pais_camp = (camp or {}).get("pais")
        continente_camp = (camp or {}).get("continente")
        pais_id_camp = garantir_pais(cur, pais_camp, continente_camp, cache_paises, cache_continentes)
        abrangencia = None if pais_camp else continente_camp
        campeonato_id = garantir_campeonato(
            cur,
            int(id_fotmob_camp),
            (camp or {}).get("nome") or jogo.get("campeonato"),
            pais_id_camp,
            abrangencia,
            (camp or {}).get("logo"),
            cache_campeonatos,
        )

        mapa_clubes_pais = {}
        for c in _linhas_df(abas.get("clubes")):
            mapa_clubes_pais[str(c.get("clube_id"))] = c.get("pais")
        for c in _linhas_df(abas.get("clubes_fontes")):
            id_ext = c.get("id_externo")
            pais_nome = c.get("pais") or mapa_clubes_pais.get(str(id_ext))
            pais_id = garantir_pais(cur, pais_nome, None, cache_paises, cache_continentes)
            garantir_clube(cur, id_ext, c.get("nome_externo") or c.get("clube"), pais_id, cache_clubes)

        tecnicos_por_fotmob = {
            str(t.get("id_fotmob")): t for t in _linhas_df(abas.get("tecnicos")) if t.get("id_fotmob")
        }
        for t in tecnicos_por_fotmob.values():
            garantir_tecnico(cur, t.get("id_fotmob"), t.get("nome"), t.get("nacionalidade"), cache_tecnicos)

        for a in _linhas_df(abas.get("arbitros")):
            pais_id = garantir_pais(cur, a.get("nacionalidade"), None, cache_paises, cache_continentes)
            garantir_arbitro(cur, a.get("id_fotmob"), a.get("nome"), pais_id, a.get("foto"), cache_arbitros)

        for j in _linhas_df(abas.get("jogadores")):
            garantir_jogador(
                cur, j.get("id_fotmob"), j.get("nome"), j.get("posicao"),
                j.get("nacionalidade"), j.get("foto"), cache_jogadores,
            )

        # Goleiros citados só nas finalizações
        for f in _linhas_df(abas.get("finalizacoes")):
            gid = f.get("goleiro_id_fotmob")
            if gid and str(gid) not in cache_jogadores:
                garantir_jogador(cur, gid, f.get("goleiro") or f"Jogador {gid}",
                                 None, None, None, cache_jogadores)

        casa_id = cache_clubes.get(str(jogo.get("casa_id_fotmob")))
        fora_id = cache_clubes.get(str(jogo.get("fora_id_fotmob")))
        if not casa_id or not fora_id:
            raise ValueError(f"Clubes não resolvidos para jogo {jogo.get('id_fotmob')}")

        tecnico_casa_id = None
        if jogo.get("tecnico_casa_id_fotmob"):
            tecnico_casa_id = garantir_tecnico(
                cur, jogo.get("tecnico_casa_id_fotmob"), jogo.get("tecnico_casa"),
                (tecnicos_por_fotmob.get(str(jogo.get("tecnico_casa_id_fotmob"))) or {}).get("nacionalidade"),
                cache_tecnicos,
            )
        tecnico_fora_id = None
        if jogo.get("tecnico_fora_id_fotmob"):
            tecnico_fora_id = garantir_tecnico(
                cur, jogo.get("tecnico_fora_id_fotmob"), jogo.get("tecnico_fora"),
                (tecnicos_por_fotmob.get(str(jogo.get("tecnico_fora_id_fotmob"))) or {}).get("nacionalidade"),
                cache_tecnicos,
            )
        arbitro_id = None
        if jogo.get("arbitro_id_fotmob") or jogo.get("arbitro"):
            arb_pais = None
            for a in _linhas_df(abas.get("arbitros")):
                if a.get("id_fotmob") == jogo.get("arbitro_id_fotmob") or a.get("nome") == jogo.get("arbitro"):
                    arb_pais = garantir_pais(cur, a.get("nacionalidade"), None, cache_paises, cache_continentes)
                    break
            arbitro_id = garantir_arbitro(
                cur, jogo.get("arbitro_id_fotmob"), jogo.get("arbitro"), arb_pais, None, cache_arbitros,
            )

        jogo_id = upsert_jogo(cur, {
            "id_fotmob": int(jogo["id_fotmob"]),
            "temporada": jogo.get("temporada"),
            "data": jogo.get("data"),
            "campeonato_id": campeonato_id,
            "rodada": jogo.get("rodada"),
            "casa_id": casa_id,
            "fora_id": fora_id,
            "gols_casa": jogo.get("gols_casa"),
            "gols_fora": jogo.get("gols_fora"),
            "tecnico_casa_id": tecnico_casa_id,
            "tecnico_fora_id": tecnico_fora_id,
            "arbitro_id": arbitro_id,
            "estadio": jogo.get("estadio"),
            "capacidade": jogo.get("capacidade"),
            "publico": jogo.get("publico"),
        })

        upsert_estatisticas(cur, jogo_id, _linhas_df(abas.get("estatisticas")), cache_clubes)
        upsert_individual(cur, jogo_id, _linhas_df(abas.get("individual")), cache_clubes, cache_jogadores)
        upsert_finalizacoes(cur, jogo_id, _linhas_df(abas.get("finalizacoes")), cache_clubes, cache_jogadores)
        upsert_odds(cur, jogo_id, _linhas_df(abas.get("odds_fotmob")))

    return jogo_id


def _placar_fixture(jogo: dict):
    """Extrai placar de um item de fixtures.allMatches (só se finalizado)."""
    status = jogo.get("status") if isinstance(jogo.get("status"), dict) else {}
    finished = status.get("finished") is True
    reason = status.get("reason") if isinstance(status.get("reason"), dict) else {}
    chave = str(reason.get("longKey") or reason.get("shortKey") or "").lower()
    if not finished and chave not in ("finished", "fulltime_short", "fulltime"):
        return None, None
    home = jogo.get("home") if isinstance(jogo.get("home"), dict) else {}
    away = jogo.get("away") if isinstance(jogo.get("away"), dict) else {}
    gc = _to_int(home.get("score"))
    gf = _to_int(away.get("score"))
    if gc is not None and gf is not None:
        return gc, gf
    score_str = str(status.get("scoreStr") or "")
    m = re.match(r"\s*(\d+)\s*[-–]\s*(\d+)\s*", score_str)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _data_fixture(jogo: dict):
    status = jogo.get("status") if isinstance(jogo.get("status"), dict) else {}
    iso = status.get("utcTime") or jogo.get("statusTime") or jogo.get("time")
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(BRASILIA_TZ).date()
    except ValueError:
        return None


def _rodada_fixture(jogo: dict) -> str | None:
    bruta = jogo.get("round")
    if bruta is None:
        bruta = jogo.get("roundName")
    if bruta is None:
        return None
    if str(bruta).isdigit():
        return f"Rodada {int(bruta)}"
    return str(bruta).strip() or None


def upsert_jogo_calendario(cur, dados, *, atualizar_placar: bool):
    """Insere/atualiza só o esqueleto do jogo (calendário). Não apaga placar existente."""
    cur.execute(
        "SELECT id, gols_casa, gols_fora FROM jogos WHERE id_fotmob = %s",
        (dados["id_fotmob"],),
    )
    row = cur.fetchone()
    if row:
        jogo_id = row[0]
        if atualizar_placar:
            cur.execute(
                """
                UPDATE jogos SET
                  temporada = %s, data = %s, campeonato_id = %s, rodada = %s,
                  casa_id = %s, fora_id = %s, gols_casa = %s, gols_fora = %s,
                  atualizado_em = now()
                WHERE id = %s
                """,
                (
                    dados["temporada"], dados["data"], dados["campeonato_id"], dados.get("rodada"),
                    dados["casa_id"], dados["fora_id"], dados.get("gols_casa"), dados.get("gols_fora"),
                    jogo_id,
                ),
            )
        else:
            cur.execute(
                """
                UPDATE jogos SET
                  temporada = %s, data = %s, campeonato_id = %s, rodada = %s,
                  casa_id = %s, fora_id = %s, atualizado_em = now()
                WHERE id = %s
                """,
                (
                    dados["temporada"], dados["data"], dados["campeonato_id"], dados.get("rodada"),
                    dados["casa_id"], dados["fora_id"], jogo_id,
                ),
            )
        return jogo_id

    cur.execute(
        """
        INSERT INTO jogos (
          id_fotmob, temporada, data, campeonato_id, rodada,
          casa_id, fora_id, gols_casa, gols_fora
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            dados["id_fotmob"], dados["temporada"], dados["data"], dados["campeonato_id"],
            dados.get("rodada"), dados["casa_id"], dados["fora_id"],
            dados.get("gols_casa"), dados.get("gols_fora"),
        ),
    )
    return cur.fetchone()[0]


def sincronizar_calendario_liga(
    conn,
    payload: dict,
    *,
    id_fotmob_campeonato: int,
    temporada: str,
    nome_campeonato: str | None = None,
    pais: str | None = None,
    caches: dict | None = None,
) -> dict:
    """Grava todos os jogos de fixtures.allMatches (finalizados e futuros).

    Futuros ficam com gols_casa/gols_fora NULL. Finalizados recebem placar do scoreStr.
    Não sobrescreve placar já existente quando o fixture ainda não está finalizado.
    """
    caches = caches or {}
    cache_continentes = caches.setdefault("continentes", {})
    cache_paises = caches.setdefault("paises", {})
    cache_campeonatos = caches.setdefault("campeonatos", {})
    cache_clubes = caches.setdefault("clubes", {})

    matches = (payload.get("fixtures") or {}).get("allMatches") or []
    detalhes = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    nome_camp = (
        nome_campeonato
        or detalhes.get("name")
        or g(payload, "details", "name")
        or f"Campeonato {id_fotmob_campeonato}"
    )
    pais_nome, continente_nome = pais_info(
        pais, detalhes.get("countryCode") or g(payload, "details", "countryCode"),
    )
    if not pais_nome:
        pais_nome = pais

    inseridos = atualizados = ignorados = 0
    with conn.cursor() as cur:
        pais_id = garantir_pais(cur, pais_nome, continente_nome, cache_paises, cache_continentes)
        abrangencia = None if pais_nome else continente_nome
        logo = None
        if isinstance(detalhes.get("logo"), str):
            logo = detalhes.get("logo")
        campeonato_id = garantir_campeonato(
            cur, int(id_fotmob_campeonato), nome_camp, pais_id, abrangencia, logo, cache_campeonatos,
        )

        for jogo in matches:
            if not isinstance(jogo, dict):
                ignorados += 1
                continue
            mid = _to_int(jogo.get("id"))
            home = jogo.get("home") if isinstance(jogo.get("home"), dict) else {}
            away = jogo.get("away") if isinstance(jogo.get("away"), dict) else {}
            casa_ext = _to_int(home.get("id"))
            fora_ext = _to_int(away.get("id"))
            data = _data_fixture(jogo)
            if mid is None or casa_ext is None or fora_ext is None or data is None:
                ignorados += 1
                continue

            casa_id = garantir_clube(cur, casa_ext, home.get("name"), pais_id, cache_clubes)
            fora_id = garantir_clube(cur, fora_ext, away.get("name"), pais_id, cache_clubes)
            gols_casa, gols_fora = _placar_fixture(jogo)
            atualizar_placar = gols_casa is not None and gols_fora is not None

            cur.execute("SELECT id FROM jogos WHERE id_fotmob = %s", (mid,))
            existe = cur.fetchone() is not None
            upsert_jogo_calendario(
                cur,
                {
                    "id_fotmob": mid,
                    "temporada": temporada,
                    "data": data,
                    "campeonato_id": campeonato_id,
                    "rodada": _rodada_fixture(jogo),
                    "casa_id": casa_id,
                    "fora_id": fora_id,
                    "gols_casa": gols_casa,
                    "gols_fora": gols_fora,
                },
                atualizar_placar=atualizar_placar,
            )
            if existe:
                atualizados += 1
            else:
                inseridos += 1

    return {
        "campeonato_id": campeonato_id,
        "total_fixtures": len(matches),
        "inseridos": inseridos,
        "atualizados": atualizados,
        "ignorados": ignorados,
    }


def salvar_json_bruto(pasta, nome, dados):
    if dados is None:
        return
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / nome).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def carregar_fonte_ids(caminho=None):
    """Lê id_jogos.txt gerado por coleta_jogos_fotmob.py.

    Aceita:
      - JSON {"campeonatos": [{"id_campeonato", "campeonato", "pais", "temporada", "ids_jogos": [...]}]}
      - lista plana de IDs (um por linha), sem metadados de campeonato
    Devolve lista de {"id_jogo", "camp": dict|None}.
    """
    caminho = Path(caminho or ARQUIVO_IDS)
    if not caminho.exists():
        raise FileNotFoundError(
            f"Arquivo de IDs não encontrado: {caminho}. "
            "Rode coleta_jogos_fotmob.py antes."
        )
    texto = caminho.read_text(encoding="utf-8-sig").strip()
    if not texto:
        raise ValueError(f"{caminho} está vazio.")

    itens = []
    vistos = set()

    if texto.lstrip().startswith(("{", "[")):
        try:
            dados = json.loads(texto)
        except ValueError as e:
            raise ValueError(f"{caminho} não é um JSON válido ({e}).") from e
        lista = dados.get("campeonatos") if isinstance(dados, dict) else dados
        if not isinstance(lista, list):
            raise ValueError(f'{caminho} precisa ter a lista "campeonatos".')
        for posicao, camp in enumerate(lista, start=1):
            if not isinstance(camp, dict):
                continue
            meta = {
                "id_campeonato": _to_int(camp.get("id_campeonato")),
                "campeonato": (camp.get("campeonato") or "").strip() or None,
                "pais": (camp.get("pais") or "").strip() or None,
                "temporada": str(camp.get("temporada") or "").strip() or None,
            }
            for valor in camp.get("ids_jogos") or []:
                id_jogo = _to_int(valor)
                if id_jogo is None or id_jogo in vistos:
                    continue
                vistos.add(id_jogo)
                itens.append({"id_jogo": id_jogo, "camp": meta})
            if camp.get("erro"):
                logger.warning(
                    "Campeonato #%d (%s %s) veio com erro na coleta: %s",
                    posicao, meta.get("campeonato"), meta.get("temporada"), camp.get("erro"),
                )
    else:
        for linha in texto.splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            id_jogo = _to_int(linha.split()[0])
            if id_jogo is None or id_jogo in vistos:
                continue
            vistos.add(id_jogo)
            itens.append({"id_jogo": id_jogo, "camp": None})

    if not itens:
        raise ValueError(f"Nenhum ID encontrado em {caminho}.")
    return itens


def _aplicar_meta_campeonato(abas, camp):
    """Sobrescreve temporada/nome/país do campeonato com o que veio do JSON de coleta."""
    if not camp:
        return abas
    jogos = abas.get("jogos")
    if jogos is not None and not jogos.empty:
        if camp.get("temporada"):
            jogos["temporada"] = camp["temporada"]
        if camp.get("id_campeonato"):
            jogos["campeonato_id_fotmob"] = camp["id_campeonato"]
        if camp.get("campeonato"):
            jogos["campeonato"] = camp["campeonato"]
    camps = abas.get("campeonatos")
    if camps is not None and not camps.empty:
        if camp.get("id_campeonato"):
            camps["id_fotmob"] = camp["id_campeonato"]
        if camp.get("campeonato"):
            camps["nome"] = camp["campeonato"]
        if camp.get("pais"):
            camps["pais"] = camp["pais"]
            p, c = pais_info(camp["pais"])
            if p and p != c:
                camps["continente"] = c
    return abas


def main():
    global TEMPORADA
    carregar_variaveis_de_ambiente(DIR)
    fonte = carregar_fonte_ids()
    logger.info("%d jogo(s) em %s", len(fonte), ARQUIVO_IDS)

    cliente = ClienteFotmob()
    inseridos = atualizados = ignorados_status = ignorados_data = 0
    falhas = []
    caches = {}
    ultimas_datas = {}
    temporada_original = TEMPORADA

    try:
        with conexao_bd() as conn:
            for i, item in enumerate(fonte, start=1):
                id_jogo = item["id_jogo"]
                camp = item.get("camp") or {}
                TEMPORADA = camp.get("temporada") or temporada_original
                rotulo = ""
                if camp.get("campeonato") or camp.get("temporada"):
                    rotulo = f" ({camp.get('campeonato') or '?'} {camp.get('temporada') or ''})".rstrip()
                try:
                    # Corte antecipado pela data no banco (sem bater na API).
                    id_camp_meta = camp.get("id_campeonato")
                    temp_meta = camp.get("temporada") or TEMPORADA
                    if id_camp_meta:
                        chave_meta = (int(id_camp_meta), str(temp_meta) if temp_meta else None)
                        if chave_meta not in ultimas_datas:
                            ultimas_datas[chave_meta] = maior_data_campeonato(
                                conn, id_camp_meta, temp_meta,
                            )
                            logger.info(
                                "Última data coletada (com placar) %s / %s: %s",
                                id_camp_meta, temp_meta, ultimas_datas[chave_meta] or "(nenhuma)",
                            )
                        ultima_meta = ultimas_datas[chave_meta]
                        resumo = resumo_jogo_fotmob(conn, id_jogo)
                        if resumo and resumo.get("gols_casa") is not None:
                            ignorados_data += 1
                            logger.info(
                                "[%d/%d] Jogo %s ignorado: já coletado (placar em %s).",
                                i, len(fonte), id_jogo, resumo.get("data"),
                            )
                            continue
                        if (
                            resumo
                            and ultima_meta is not None
                            and resumo.get("data") is not None
                            and resumo["data"] < ultima_meta
                        ):
                            ignorados_data += 1
                            logger.info(
                                "[%d/%d] Jogo %s ignorado: data %s < última coletada %s (sem API).",
                                i, len(fonte), id_jogo, resumo["data"], ultima_meta,
                            )
                            continue

                    logger.info("[%d/%d] Coletando matchDetails do jogo %s%s...", i, len(fonte), id_jogo, rotulo)
                    detalhes = cliente.match_details(id_jogo)
                    salvar_json_bruto(PASTA_RAW, f"matchDetails_{id_jogo}.json", detalhes)
                    if not jogo_finalizado(detalhes):
                        ignorados_status += 1
                        logger.info("Jogo %s ignorado: não finalizado.", id_jogo)
                        continue

                    logger.info("[%d/%d] Coletando matchOdds do jogo %s...", i, len(fonte), id_jogo)
                    odds = cliente.match_odds(id_jogo)
                    salvar_json_bruto(PASTA_RAW, f"matchOdds_{id_jogo}.json", odds)

                    abas = montar_tabelas(detalhes, odds, id_jogo)
                    if not abas:
                        ignorados_status += 1
                        continue
                    abas = _aplicar_meta_campeonato(abas, camp)

                    jogo = _linhas_df(abas.get("jogos"))[0]
                    id_camp = jogo.get("campeonato_id_fotmob")
                    temporada = jogo.get("temporada")
                    data_jogo = jogo.get("data")
                    if isinstance(data_jogo, datetime):
                        data_jogo = data_jogo.date()

                    chave_camp = (id_camp, str(temporada) if temporada else None)
                    if chave_camp not in ultimas_datas:
                        ultimas_datas[chave_camp] = maior_data_campeonato(conn, id_camp, temporada)
                        logger.info(
                            "Última data coletada (com placar) %s / %s: %s",
                            id_camp, temporada, ultimas_datas[chave_camp] or "(nenhuma)",
                        )
                    ultima = ultimas_datas[chave_camp]
                    resumo_pos = resumo_jogo_fotmob(conn, id_jogo)
                    ja_coletado = resumo_pos is not None and resumo_pos.get("gols_casa") is not None
                    if ja_coletado:
                        ignorados_data += 1
                        logger.info(
                            "Jogo %s ignorado: já coletado (placar em %s).",
                            id_jogo, resumo_pos.get("data"),
                        )
                        continue
                    if ultima is not None and data_jogo is not None and data_jogo < ultima:
                        # Data antiga: não coleta. Mesmo dia da última ainda pode faltar jogo.
                        ignorados_data += 1
                        logger.info(
                            "Jogo %s ignorado: data %s < última coletada %s.",
                            id_jogo, data_jogo, ultima,
                        )
                        continue

                    existia = jogo_ja_existe(conn, id_jogo) is not None
                    salvar_jogo_no_banco(conn, abas, caches)
                    conn.commit()
                    if existia:
                        atualizados += 1
                        logger.info("Jogo %s atualizado no banco.", id_jogo)
                    else:
                        inseridos += 1
                        logger.info("Jogo %s inserido no banco.", id_jogo)
                    if data_jogo and (ultimas_datas[chave_camp] is None or data_jogo > ultimas_datas[chave_camp]):
                        ultimas_datas[chave_camp] = data_jogo
                except Exception as e:
                    conn.rollback()
                    falhas.append(id_jogo)
                    logger.exception("Falha ao processar jogo %s: %s", id_jogo, e)
    finally:
        TEMPORADA = temporada_original
        cliente.close()

    logger.info(
        "Concluído. inseridos=%d atualizados=%d ignorados_status=%d ignorados_data=%d falhas=%d",
        inseridos, atualizados, ignorados_status, ignorados_data, len(falhas),
    )
    if falhas:
        logger.warning("IDs com falha: %s", falhas)


if __name__ == "__main__":
    main()