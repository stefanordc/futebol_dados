import re
import sys
import time
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ----------------------------------------------------------------------
# Configuração: altere apenas o link abaixo
# ----------------------------------------------------------------------
URL = "https://www.transfermarkt.com.br/major-league-soccer/startseite/wettbewerb/MLS1/plus/?saison_id=2009"
CAMINHO_SAIDA = Path(r"C:\Users\stefano.faria\Desktop\valor_mercado.xlsx")

#  python -u "C:\Users\stefano.faria\Desktop\analise_dados\dados_futebol\jogos_ogol\valor_mercado.py"

# ----------------------------------------------------------------------

PASTA_DEBUG = Path(__file__).parent

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

PAUSA_ENTRE_REQUISICOES = 2  # segundos, evita bloqueio do site
MAX_TENTATIVAS = 3
COLUNAS = ["Temporada", "Clube", "Valor de mercado", "Escudo"]

# Multiplicadores dos sufixos usados pelo site
MULTIPLICADORES = {"bi.": Decimal("1e9"), "mi.": Decimal("1e6"), "mil": Decimal("1e3")}


def separar_url(url: str) -> tuple[str, int]:
    """Divide o link em (URL sem query string, temporada inicial)."""
    partes = urlparse(url.strip())
    parametros = parse_qs(partes.query)
    if "saison_id" not in parametros:
        sys.exit("O link precisa conter '?saison_id=ANO' (ex.: ...?saison_id=2010).")
    url_base = f"{partes.scheme}://{partes.netloc}{partes.path}"
    return url_base, int(parametros["saison_id"][0])


def baixar_pagina(
    sessao: requests.Session, url: str, params: dict | None = None
) -> BeautifulSoup:
    """Baixa uma página, com pausa entre requisições e novas tentativas em caso de falha."""
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        time.sleep(PAUSA_ENTRE_REQUISICOES * tentativa)
        try:
            resposta = sessao.get(url, params=params, headers=HEADERS, timeout=30)
            resposta.raise_for_status()
            return BeautifulSoup(resposta.text, "html.parser")
        except requests.RequestException as erro:
            print(f"  Falha ({tentativa}/{MAX_TENTATIVAS}) em {url}: {erro}")
            if tentativa == MAX_TENTATIVAS:
                raise


def listar_temporadas(soup: BeautifulSoup) -> list[int]:
    """Lê as temporadas disponíveis no dropdown da página."""
    select = soup.find("select", {"name": "saison_id"})
    return sorted(int(op["value"]) for op in select.find_all("option"))


def formatar_temporada(ano: int) -> str:
    """2010 -> '2010/2011'."""
    return f"{ano}/{ano + 1}"


def converter_valor(texto: str) -> int | None:
    """Converte '€ 553.50 mi.' em 553500000. Retorna None se não for um valor monetário."""
    padrao = re.search(r"([\d.,]+)\s*(bi\.|mi\.|mil)", texto.lower())
    if not padrao:
        return None
    numero = Decimal(padrao.group(1).replace(",", "."))
    return int(numero * MULTIPLICADORES[padrao.group(2)])


def valor_total_da_linha(linha) -> int | None:
    """
    Retorna o valor de mercado total do clube: a última célula 'rechts' com
    valor monetário (a anterior é a média por jogador).
    """
    valores = [
        converter_valor(td.get_text(strip=True))
        for td in linha.find_all("td", class_="rechts", recursive=False)
    ]
    valores = [v for v in valores if v is not None]
    return valores[-1] if valores else None


def obter_escudo(
    sessao: requests.Session, url_clube: str, cache: dict[str, str | None]
) -> str | None:
    """Abre a página do clube e retorna a URL do escudo em tamanho grande."""
    if url_clube in cache:
        return cache[url_clube]

    escudo = None
    try:
        soup = baixar_pagina(sessao, url_clube)
        imagem = soup.select_one("div.data-header__profile-container img")
        escudo = imagem.get("src") if imagem else None
        if escudo is None:
            print(f"  Aviso: escudo não encontrado em {url_clube}")
    except requests.RequestException:
        print(f"  Aviso: não foi possível abrir {url_clube}")

    cache[url_clube] = escudo
    return escudo


def extrair_clubes(
    sessao: requests.Session,
    soup: BeautifulSoup,
    url_base: str,
    temporada: int,
    cache_escudos: dict[str, str | None],
) -> list[dict]:
    """Extrai valor de mercado e escudo de cada clube, ignorando a linha de totais (tfoot)."""
    rotulo = formatar_temporada(temporada)
    tabela = soup.select_one("table.items")
    if tabela is None:
        print(f"  Aviso: tabela não encontrada em {rotulo}")
        return []

    registros = []
    for linha in tabela.select("tbody > tr"):
        link_clube = linha.select_one("td.hauptlink a")
        if not link_clube:
            continue

        clube = link_clube.get_text(strip=True)
        valor = valor_total_da_linha(linha)
        if valor is None:
            print(f"  Aviso: {clube} ({rotulo}) sem valor de mercado reconhecido")

        url_clube = urljoin(url_base, link_clube["href"])
        escudo = obter_escudo(sessao, url_clube, cache_escudos)

        registros.append(
            {
                "Temporada": rotulo,
                "Clube": clube,
                "Valor de mercado": valor,
                "Escudo": escudo,
            }
        )
    return registros


def salvar_html_debug(soup: BeautifulSoup, temporada: int) -> None:
    """Guarda o HTML recebido para investigar temporadas sem resultado."""
    caminho = PASTA_DEBUG / f"debug_{temporada}.html"
    caminho.write_text(str(soup), encoding="utf-8")
    print(f"  HTML salvo em {caminho}")


def salvar_excel(df: pd.DataFrame, caminho: Path) -> None:
    """Salva o DataFrame formatando o valor com separador de milhar."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(caminho, engine="openpyxl") as escritor:
        df.to_excel(escritor, index=False, sheet_name="Valor de mercado")
        planilha = escritor.sheets["Valor de mercado"]
        for celula in planilha["C"][1:]:
            celula.number_format = "#,##0"  # exibido como 553.500.000 no Excel em pt-BR
        planilha.column_dimensions["A"].width = 14
        planilha.column_dimensions["B"].width = 28
        planilha.column_dimensions["C"].width = 20
        planilha.column_dimensions["D"].width = 70


def main() -> None:
    url_base, temporada_inicial = separar_url(URL)
    registros: list[dict] = []
    cache_escudos: dict[str, str | None] = {}

    with requests.Session() as sessao:
        soup = baixar_pagina(sessao, url_base, {"saison_id": temporada_inicial})
        temporadas = [t for t in listar_temporadas(soup) if t >= temporada_inicial]
        print(f"Temporadas a coletar: {temporadas[0]} até {temporadas[-1]}")

        for temporada in temporadas:
            if temporada != temporada_inicial:
                soup = baixar_pagina(sessao, url_base, {"saison_id": temporada})

            clubes = extrair_clubes(sessao, soup, url_base, temporada, cache_escudos)
            if not clubes:
                salvar_html_debug(soup, temporada)
            registros.extend(clubes)
            print(f"{formatar_temporada(temporada)}: {len(clubes)} clubes")

    df = pd.DataFrame(registros, columns=COLUNAS)
    salvar_excel(df, CAMINHO_SAIDA)
    print(f"\nArquivo salvo em: {CAMINHO_SAIDA} ({len(df)} linhas)")


if __name__ == "__main__":
    main()

    import winsound

    winsound.Beep(1000, 500)