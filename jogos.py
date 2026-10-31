import argparse
import random
import re
import sys
import time
from collections import Counter

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE_URL = "https://www.ogol.com.br"
COMPETICAO_URL = f"{BASE_URL}/competicao/bundesliga/11"
PAGE_SUFIXO = "?fase_in=0&equipa=0&estado=&filtro=&op=calendario&page={n}"

OUTPUT_PATH = r"C:\Users\stefano.faria\Desktop\temporario.xlsx"

ROW_SELECTOR = "table.stats tbody tr[data-lj]"
EDICAO_SELECTOR = 'a[href^="/edicao/"]'
MAX_RETRIES = 3
MAX_PAGES = 50  # trava de segurança por temporada

COLUNAS_FINAIS = [
    "jogo_id",
    "data",
    "temporada",
    "hora",
    "rodada",
    "id_casa",
    "casa",
    "gols_casa",
    "gols_fora",
    "fora",
    "id_fora",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = window.chrome || { runtime: {} };
"""


# ----------------------------------------------------------------------
# Navegador / anti-bot
# ----------------------------------------------------------------------
def pausa(minimo=1.5, maximo=3.5):
    time.sleep(random.uniform(minimo, maximo))


def criar_contexto(p, headless: bool):
    browser = p.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent=USER_AGENT,
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        viewport={"width": 1366, "height": 768},
        extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"},
    )
    context.add_init_script(STEALTH_JS)
    context.route(
        "**/*",
        lambda route: route.abort()
        if route.request.resource_type in ("image", "font", "media")
        else route.continue_(),
    )
    return browser, context


def baixar_html(page, url: str, seletor: str) -> str:
    """Abre a URL, espera o seletor existir no DOM (cobre telas de verificação) e devolve o HTML."""
    ultimo_erro = None
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            # "attached": o primeiro match pode estar em menu oculto e nunca ficar visível
            page.wait_for_selector(seletor, state="attached", timeout=45000)
            page.mouse.wheel(0, random.randint(300, 900))
            pausa(0.5, 1.2)
            return page.content()
        except PWTimeout as e:
            ultimo_erro = e
            print(f"  [!] Tentativa {tentativa}/{MAX_RETRIES} falhou em {url}", file=sys.stderr)
            pausa(4, 8)
    raise RuntimeError(
        f"Não foi possível carregar {url}. Tente rodar com --headed. Erro: {ultimo_erro}"
    )


# ----------------------------------------------------------------------
# Lista de temporadas
# ----------------------------------------------------------------------
def listar_edicoes(html: str):
    """
    Devolve os links de edição da competição, do mais recente para o mais antigo.
    Ex.: ['/edicao/1-bundesliga-2026-27/220062', ..., '/edicao/1-bundesliga-1963-1964/844']
    Só mantém o prefixo mais comum (ex.: '1-bundesliga'), para ignorar outras competições.
    """
    soup = BeautifulSoup(html, "html.parser")
    achados = {}  # href -> prefixo (dict mantém a ordem e remove duplicados)
    for a in soup.select(EDICAO_SELECTOR):
        href = a["href"].split("?")[0].rstrip("/")
        m = re.fullmatch(r"/edicao/(.+?)-(\d{4}(?:-\d{2,4})?)/(\d+)", href)
        if m:
            achados[href] = m.group(1)

    if not achados:
        return []

    prefixo, _ = Counter(achados.values()).most_common(1)[0]
    return [href for href, pref in achados.items() if pref == prefixo]


def extrair_temporada(href: str):
    """
    '/edicao/1-bundesliga-2015-2016/87251' -> '2015/2016'
    '/edicao/1-bundesliga-2025-26/202253'  -> '2025/26'
    '/edicao/brasileirao-2026/12345'       -> '2026'
    """
    m = re.search(r"/edicao/[^/]+?-(\d{4})(?:-(\d{2,4}))?/\d+", href)
    if not m:
        return None
    ano1, ano2 = m.group(1), m.group(2)
    return f"{ano1}/{ano2}" if ano2 else ano1


# ----------------------------------------------------------------------
# Parsing da tabela de jogos
# ----------------------------------------------------------------------
def parse_placar(texto: str):
    m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", texto or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def parse_rodada(texto: str):
    """'R1' -> 1. Se não houver número, devolve o texto original."""
    if not texto:
        return None
    digitos = re.sub(r"\D", "", texto)
    return int(digitos) if digitos else texto


def id_da_logo(td):
    if td is None:
        return None
    img = td.select_one("img")
    if img is None:
        return None
    m = re.search(r"/equipas/(\d+)_imgbank", img.get("src", ""))
    return int(m.group(1)) if m else None


def id_do_link(a):
    if a is None:
        return None
    m = re.search(r"/equipe/[^/?]+/(\d+)", a.get("href", ""))
    return int(m.group(1)) if m else None


def ids_do_h2h(a):
    """Dois IDs do link h2h (t101-t108). A ordem NÃO é casa/fora."""
    if a is None:
        return set()
    m = re.search(r"/t(\d+)-t(\d+)", a.get("href", ""))
    return {int(m.group(1)), int(m.group(2))} if m else set()


def parse_pagina(html: str):
    """Extrai os jogos e o maior número de página visto na paginação."""
    soup = BeautifulSoup(html, "html.parser")
    jogos = []

    for tr in soup.select(ROW_SELECTOR):
        tds_data = tr.select_one("td.date")
        td_casa = tr.select_one("td.text.home")
        td_fora = tr.select_one("td.text.away")
        casa = td_casa.select_one("a") if td_casa else None
        fora = td_fora.select_one("a") if td_fora else None
        resultado = tr.select_one("td.result a")
        fase = tr.select_one("td.phase")
        h2h = tr.select_one("td.h2h a")

        hora = tds_data.find_next_sibling("td").get_text(strip=True) if tds_data else None
        gols_casa, gols_fora = parse_placar(resultado.get_text(strip=True) if resultado else None)

        id_casa = id_da_logo(td_casa.find_next_sibling("td") if td_casa else None)
        id_fora = id_da_logo(td_fora.find_previous_sibling("td") if td_fora else None)

        if id_casa is None:
            id_casa = id_do_link(casa)
        if id_fora is None:
            id_fora = id_do_link(fora)

        ids_h2h = ids_do_h2h(h2h)
        if len(ids_h2h) == 2:
            if id_casa is None and id_fora is not None:
                restante = ids_h2h - {id_fora}
                id_casa = next(iter(restante)) if len(restante) == 1 else None
            elif id_fora is None and id_casa is not None:
                restante = ids_h2h - {id_casa}
                id_fora = next(iter(restante)) if len(restante) == 1 else None

        conferido = None
        if len(ids_h2h) == 2 and id_casa is not None and id_fora is not None:
            conferido = {id_casa, id_fora} == ids_h2h

        jogos.append(
            {
                "jogo_id": tr.get("id"),
                "data": tds_data.get_text(strip=True) if tds_data else None,
                "hora": hora,
                "rodada": parse_rodada(fase.get_text(strip=True) if fase else None),
                "id_casa": id_casa,
                "casa": casa.get_text(strip=True) if casa else None,
                "gols_casa": gols_casa,
                "gols_fora": gols_fora,
                "id_fora": id_fora,
                "fora": fora.get_text(strip=True) if fora else None,
                "_ids_conferem": conferido,
            }
        )

    max_pagina = 1
    for a in soup.select("div.zz-pagination a[href]"):
        m = re.search(r"[?&]page=(\d+)", a["href"])
        if m:
            max_pagina = max(max_pagina, int(m.group(1)))

    return jogos, max_pagina


# ----------------------------------------------------------------------
# Uma temporada completa
# ----------------------------------------------------------------------
def raspar_temporada(page, href: str, temporada: str) -> pd.DataFrame:
    calendario_url = f"{BASE_URL}{href}/calendario"
    todos = []
    ultima_pagina = 1
    n = 1

    while n <= ultima_pagina and n <= MAX_PAGES:
        url = calendario_url if n == 1 else calendario_url + PAGE_SUFIXO.format(n=n)
        print(f"   [{n}/{ultima_pagina}] {url}")

        html = baixar_html(page, url, ROW_SELECTOR)
        jogos, max_pagina = parse_pagina(html)
        ultima_pagina = max(ultima_pagina, max_pagina)
        todos.extend(jogos)

        n += 1
        if n <= ultima_pagina:
            pausa()

    df = pd.DataFrame(todos).drop_duplicates(subset="jogo_id").reset_index(drop=True)
    df["temporada"] = temporada
    return df


def validar_temporada(df: pd.DataFrame, temporada: str):
    """Mostra avisos de qualidade para uma temporada."""
    avisos = []

    sem_id = df[df["id_casa"].isna() | df["id_fora"].isna()]
    if len(sem_id):
        avisos.append(f"{len(sem_id)} jogos sem id_casa ou id_fora")

    divergentes = df[df["_ids_conferem"] == False]  # noqa: E712
    if len(divergentes):
        avisos.append(f"{len(divergentes)} jogos com IDs diferentes do h2h")

    pares = pd.concat(
        [
            df[["id_casa", "casa"]].set_axis(["id", "nome"], axis=1),
            df[["id_fora", "fora"]].set_axis(["id", "nome"], axis=1),
        ]
    ).dropna().drop_duplicates()
    if (pares.groupby("id")["nome"].nunique() > 1).any():
        avisos.append("há IDs com mais de um nome de time")

    clubes = pares["id"].nunique()
    esperado = clubes * (clubes - 1)
    if len(df) != esperado:
        avisos.append(f"{len(df)} jogos, mas {clubes} clubes indicam {esperado}")

    status = "OK" if not avisos else "ATENÇÃO"
    print(f"   -> {temporada}: {len(df)} jogos, {clubes} clubes [{status}]")
    for av in avisos:
        print(f"      [ATENÇÃO] {av}", file=sys.stderr)


# ----------------------------------------------------------------------
# Excel
# ----------------------------------------------------------------------
def montar_saida(partes: list) -> pd.DataFrame:
    df = pd.concat(partes, ignore_index=True)
    df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.date
    for col in ("id_casa", "id_fora", "gols_casa", "gols_fora"):
        df[col] = df[col].astype("Int64")
    return df[COLUNAS_FINAIS]


def salvar_excel(df: pd.DataFrame, caminho: str, fatal: bool = True) -> bool:
    try:
        df.to_excel(caminho, index=False, sheet_name="calendario")
        return True
    except PermissionError:
        msg = (
            f"Não consegui gravar em {caminho}. "
            "O arquivo provavelmente está aberto no Excel. Feche-o e rode de novo."
        )
        if fatal:
            print(f"\n[ERRO] {msg}", file=sys.stderr)
            sys.exit(1)
        print(f"   [ATENÇÃO] {msg}", file=sys.stderr)
        return False


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main(headless: bool, limite):
    partes = []
    falhas = []

    with sync_playwright() as p:
        browser, context = criar_contexto(p, headless)
        page = context.new_page()

        # aquecimento: home primeiro, para receber cookies como visitante normal
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
            pausa(2, 4)
        except PWTimeout:
            pass

        print(f"Lendo lista de temporadas: {COMPETICAO_URL}")
        html = baixar_html(page, COMPETICAO_URL, EDICAO_SELECTOR)
        edicoes = listar_edicoes(html)  # mais recente -> mais antiga
        if not edicoes:
            browser.close()
            sys.exit("[ERRO] Nenhum link de temporada encontrado na página da competição.")

        if limite:
            edicoes = edicoes[:limite]
        edicoes = list(reversed(edicoes))  # processa da mais antiga para a mais recente
        print(f"{len(edicoes)} temporadas para coletar\n")

        for i, href in enumerate(edicoes, start=1):
            temporada = extrair_temporada(href)
            print(f"[{i}/{len(edicoes)}] Temporada {temporada}  ({href})")
            try:
                df_t = raspar_temporada(page, href, temporada)
                validar_temporada(df_t, temporada)
                partes.append(df_t)

                # checkpoint: salva o que já foi coletado
                salvar_excel(montar_saida([d.copy() for d in partes]), OUTPUT_PATH, fatal=False)
            except RuntimeError as e:
                print(f"   [FALHA] {temporada}: {e}", file=sys.stderr)
                falhas.append(temporada)

            if i < len(edicoes):
                pausa(3, 6)

        browser.close()

    if not partes:
        sys.exit("[ERRO] Nenhuma temporada foi coletada.")

    df = montar_saida(partes)
    salvar_excel(df, OUTPUT_PATH, fatal=True)

    print(f"\nTotal: {len(df)} jogos em {len(partes)} temporadas")
    if falhas:
        print(f"[ATENÇÃO] Temporadas com falha (rode de novo para tentar): {', '.join(falhas)}", file=sys.stderr)
    print(f"Arquivo salvo em: {OUTPUT_PATH}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true", help="abre o navegador visível")
    ap.add_argument("--limite", type=int, default=None, help="coleta só as N temporadas mais recentes (teste)")
    args = ap.parse_args()
    main(headless=not args.headed, limite=args.limite)


import winsound

frequencia = 1000  # 1000 Hz (som mais agudo)
duracao = 500      # 500 milissegundos (meio segundo)

# Emite o som personalizado
winsound.Beep(frequencia, duracao)
