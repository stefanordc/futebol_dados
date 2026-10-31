import argparse
import json
import logging
import os
import random
import re
import subprocess
import time
import urllib.request
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("coleta_id_jogo")

DIR = Path(__file__).resolve().parent
PERFIS = [
    {
        "campeonatos": str(DIR / "campeonatos.json"),
        "ids": str(DIR / "id_jogos_sofascore.txt"),
    },
    {
        "campeonatos": r"C:\Users\stefa\Desktop\Portfólio 2026\dados_futebol\padronizacao\campeonatos.json",
        "ids": r"C:\Users\stefa\Desktop\Portfólio 2026\dados_futebol\id_jogos.txt",
    },
]


def escolher_perfil():
    """Usa o perfil cujo campeonatos.json existe neste computador (o primeiro, se nenhum existir)."""
    return next((p for p in PERFIS if os.path.isfile(p["campeonatos"])), PERFIS[0])


_perfil = escolher_perfil()
ARQUIVO_CAMPEONATOS = _perfil["campeonatos"]
ARQUIVO_IDS = _perfil["ids"]

BASE_URL = "https://www.sofascore.com/api/v1"
HOME_URL = "https://www.sofascore.com/"
BRASILIA_TZ = timezone(timedelta(hours=-3))
CHAVES_FIXAS = {"link_base", "campeonato", "pais"}
MAX_PAGINAS = 100
TENTATIVAS = 5
PAUSA_REQUISICAO = (1.5, 3.0)

JS_FETCH = """
var done = arguments[arguments.length - 1];
fetch(arguments[0], {
    method: 'GET',
    headers: {'Accept': '*/*', 'X-Requested-With': arguments[1]},
    credentials: 'include',
    cache: 'no-store'
})
.then(function(r) {
    return r.text().then(function(t) { done({status: r.status, body: t}); });
})
.catch(function(e) { done({status: 0, body: String(e)}); });
"""


class SofascoreHTTPError(RuntimeError):
    def __init__(self, status, url):
        super().__init__(f"HTTP {status} em {url}")
        self.status = status
        self.url = url


def _ler_texto(caminho):
    dados = Path(caminho).read_bytes()
    if dados.startswith((b"\xff\xfe", b"\xfe\xff")):
        return dados.decode("utf-16")
    try:
        return dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        return dados.decode("cp1252", errors="replace")


def _to_int(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def carregar_env(*bases):
    """Procura o .env nas pastas-base e até 3 níveis acima. Não sobrescreve variáveis já definidas."""
    candidatos = []
    explicito = os.environ.get("SOFASCORE_ENV", "").strip().strip('"')
    if explicito:
        candidatos.append(Path(explicito))
    pastas = []
    for base in bases:
        atual = Path(base).resolve()
        for _ in range(4):
            if atual not in pastas:
                pastas.append(atual)
            if atual.parent == atual:
                break
            atual = atual.parent
    candidatos += [p / ".env" for p in pastas]
    for env_path in candidatos:
        if not env_path.is_file():
            continue
        for linha in _ler_texto(env_path).splitlines():
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


def usa_banco():
    return bool(os.environ.get("SUPABASE_DB_URL"))


@contextmanager
def conexao_bd():
    conn = psycopg2.connect(os.environ["SUPABASE_DB_URL"])
    try:
        yield conn
    finally:
        conn.close()


def maior_data_no_banco(conn, id_campeonato, nome_campeonato, temporada):
    """Maior data em jogos para o campeonato Sofascore + temporada."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT MAX(j.data)
            FROM jogos j
            JOIN campeonatos c ON c.id = j.campeonato_id
            WHERE c.id_sofascore = %s AND j.temporada = %s
            """,
            (id_campeonato, str(temporada)),
        )
        valor = cur.fetchone()[0]
        if valor is None and nome_campeonato:
            cur.execute(
                """
                SELECT MAX(j.data)
                FROM jogos j
                JOIN campeonatos c ON c.id = j.campeonato_id
                WHERE lower(btrim(c.nome)) = lower(btrim(%s)) AND j.temporada = %s
                """,
                (nome_campeonato, str(temporada)),
            )
            valor = cur.fetchone()[0]
    if isinstance(valor, datetime):
        return valor.date()
    return valor


def ler_campeonatos_json(caminho):
    """Devolve uma lista com uma entrada por (campeonato, temporada)."""
    arquivo = Path(caminho)
    if not arquivo.is_file():
        raise FileNotFoundError(f"campeonatos.json não encontrado: {arquivo}")
    dados = json.loads(_ler_texto(arquivo))
    itens = []
    for id_camp, info in dados.items():
        if not isinstance(info, dict):
            continue
        nome = str(info.get("campeonato") or "").strip()
        pais = str(info.get("pais") or "").strip()
        if not nome or not pais:
            logger.warning("Campeonato %s ignorado (faltam campeonato ou pais).", id_camp)
            continue
        for chave, temporada in info.items():
            if chave in CHAVES_FIXAS or not str(chave).isdecimal():
                continue
            itens.append({
                "id_campeonato": int(id_camp),
                "campeonato": nome,
                "pais": pais,
                "temporada": str(temporada),
                "season_id": int(chave),
            })
    return itens


def _porta_debug():
    valor = os.environ.get("SOFASCORE_PORTA", "9222").strip()
    return int(valor) if valor.isdigit() else 9222


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
    for caminho in candidatos:
        if caminho and os.path.isfile(caminho):
            return caminho
    return None


def _versao_chromium(porta):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/json/version", timeout=2) as r:
            info = json.loads(r.read().decode("utf-8"))
        m = re.search(r"/(\d+\.\d+\.\d+\.\d+)", info.get("Browser", ""))
        return m.group(1) if m else "desconhecida"
    except Exception:
        return None


def criar_driver():
    porta = _porta_debug()
    versao = _versao_chromium(porta)
    proc = None
    if versao:
        logger.info("Navegador com depuração já aberto na porta %d (Chromium %s).", porta, versao)
    else:
        caminho = _achar_navegador()
        if not caminho:
            raise RuntimeError("Nenhum navegador encontrado. Defina BROWSER_PATH com o caminho do brave.exe/chrome.exe.")
        perfil = Path(os.environ.get("SOFASCORE_PERFIL") or (Path.home() / "sofascore_perfil"))
        perfil.mkdir(parents=True, exist_ok=True)
        logger.info("Abrindo navegador: %s (perfil: %s)", caminho, perfil)
        proc = subprocess.Popen([
            caminho, f"--remote-debugging-port={porta}", f"--user-data-dir={perfil}",
            "--no-first-run", "--no-default-browser-check", "--window-size=1280,900",
            HOME_URL,
        ])
        for _ in range(80):
            time.sleep(0.5)
            versao = _versao_chromium(porta)
            if versao:
                break
        else:
            raise RuntimeError(f"O navegador não respondeu na porta {porta}. Feche as janelas dele e tente de novo.")

    opcoes = webdriver.ChromeOptions()
    opcoes.add_experimental_option("debuggerAddress", f"127.0.0.1:{porta}")
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


def abrir_url(driver, url, tentativas=2):
    for t in range(1, tentativas + 1):
        try:
            driver.get(url)
            break
        except TimeoutException:
            logger.warning("Timeout ao abrir %s (tentativa %d/%d).", url, t, tentativas)
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass
            if "sofascore.com" in (driver.current_url or ""):
                break
        except WebDriverException as e:
            logger.warning("Erro ao abrir %s (tentativa %d/%d): %s", url, t, tentativas, str(e).splitlines()[0])
            time.sleep(2)
    time.sleep(random.uniform(2.0, 3.5))


def garantir_origem(driver):
    try:
        atual = driver.current_url or ""
    except WebDriverException:
        atual = ""
    if not atual.startswith(HOME_URL.rstrip("/")):
        abrir_url(driver, HOME_URL)


def buscar_json(driver, url):
    """GET na API a partir da própria página do Sofascore (mesma origem, com os cookies do navegador)."""
    ultimo_erro = None
    for tentativa in range(1, TENTATIVAS + 1):
        time.sleep(random.uniform(*PAUSA_REQUISICAO))
        status, corpo = 0, ""
        try:
            driver.set_script_timeout(25)
            resposta = driver.execute_async_script(JS_FETCH, url, "%06x" % random.getrandbits(24))
            if isinstance(resposta, dict):
                status, corpo = int(resposta.get("status") or 0), resposta.get("body") or ""
        except WebDriverException as e:
            mensagem = str(e).splitlines()[0] if str(e) else type(e).__name__
            if any(t in mensagem.lower() for t in ("invalid session", "no such window", "disconnected", "not reachable")):
                raise RuntimeError(f"Navegador indisponível: {mensagem}") from e
            ultimo_erro = mensagem

        if status == 200:
            try:
                dados = json.loads(corpo)
            except ValueError:
                dados = None
            erro = dados.get("error") if isinstance(dados, dict) else None
            if dados is not None and not isinstance(erro, dict):
                return dados
            status = _to_int(erro.get("code")) or 403 if isinstance(erro, dict) else 0

        if status == 404:
            raise SofascoreHTTPError(404, url)
        ultimo_erro = f"HTTP {status}" if status else (ultimo_erro or "sem resposta")
        if tentativa == TENTATIVAS:
            break
        base = min(240, 30 * 2 ** (tentativa - 1)) if status in (403, 429) else 3 * tentativa
        espera = base * random.uniform(0.8, 1.3)
        logger.warning("%s em %s (tentativa %d/%d). Aguardando %.0fs.", ultimo_erro, url, tentativa, TENTATIVAS, espera)
        time.sleep(espera)
    raise RuntimeError(f"Falha ao buscar {url}: {ultimo_erro}")


def listar_jogos_finalizados(driver, id_campeonato, season_id):
    """Percorre events/last até o fim e devolve ({id_jogo: data em Brasília}, contagem por status, páginas)."""
    base = f"{BASE_URL}/unique-tournament/{id_campeonato}/season/{season_id}/events/last"
    jogos, por_status = {}, Counter()
    for pagina in range(MAX_PAGINAS):
        try:
            dados = buscar_json(driver, f"{base}/{pagina}")
        except SofascoreHTTPError:
            if pagina == 0:
                raise
            break
        eventos = dados.get("events") or []
        for evento in eventos:
            tipo = (evento.get("status") or {}).get("type", "")
            por_status[tipo] += 1
            id_jogo = _to_int(evento.get("id"))
            timestamp = _to_int(evento.get("startTimestamp"))
            if tipo == "finished" and id_jogo is not None and timestamp:
                jogos[id_jogo] = datetime.fromtimestamp(timestamp, tz=BRASILIA_TZ).date()
        logger.info("   página %d: %d evento(s) | finalizados acumulados: %d", pagina, len(eventos), len(jogos))
        if not eventos or not dados.get("hasNextPage"):
            return jogos, por_status, pagina + 1
    raise RuntimeError(f"Limite de {MAX_PAGINAS} páginas excedido.")


def calcular_intervalo(conn, camp, ontem, de_manual, ate_manual):
    """Devolve (data_de | None, data_ate, origem). data_de None = varrer tudo."""
    if de_manual or ate_manual:
        return de_manual, (ate_manual or ontem), "manual"
    try:
        maior = maior_data_no_banco(
            conn, camp["id_campeonato"], camp["campeonato"], camp["temporada"],
        )
    except Exception as e:
        logger.warning(
            "Não foi possível consultar a maior data no banco (%s). Varredura completa.",
            str(e).splitlines()[0],
        )
        return None, ontem, "banco indisponível/incompatível (varredura completa)"
    if maior is None:
        return None, ontem, "sem jogos no banco (varredura completa)"
    return maior + timedelta(days=1), ontem, f"maior data no banco: {maior:%d/%m/%Y}"


def gravar_json(caminho, dados):
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    with open(caminho, "w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(texto)


def main():
    parser = argparse.ArgumentParser(description="Coleta IDs de jogos finalizados do Sofascore.")
    parser.add_argument("--temporada", help="Só esta temporada, como está no JSON (ex.: 2026/2027).")
    parser.add_argument("--campeonato", help="Só este id_campeonato (ex.: 17).")
    parser.add_argument("--de", help="Data inicial manual AAAA-MM-DD (ignora o banco).")
    parser.add_argument("--ate", help="Data final manual AAAA-MM-DD (padrão: ontem).")
    args = parser.parse_args()

    de_manual = date.fromisoformat(args.de) if args.de else None
    ate_manual = date.fromisoformat(args.ate) if args.ate else None

    arquivo_ids = Path(ARQUIVO_IDS)
    carregar_env(arquivo_ids.parent, Path(__file__).resolve().parent, Path.cwd())

    campeonatos = ler_campeonatos_json(ARQUIVO_CAMPEONATOS)
    if args.temporada:
        campeonatos = [c for c in campeonatos if c["temporada"] == args.temporada]
    if args.campeonato:
        campeonatos = [c for c in campeonatos if str(c["id_campeonato"]) == str(args.campeonato)]
    if not campeonatos:
        logger.warning("Nenhum campeonato/temporada para coletar com esses filtros.")
        return

    hoje = datetime.now(BRASILIA_TZ).date()
    ontem = hoje - timedelta(days=1)
    logger.info("Hoje (Brasília): %s | coleta até: %s | %d campeonato(s)/temporada(s)", hoje, ontem, len(campeonatos))

    plano = []
    if usa_banco():
        with conexao_bd() as conn:
            for camp in campeonatos:
                de, ate, origem = calcular_intervalo(conn, camp, ontem, de_manual, ate_manual)
                rotulo = f"{camp['campeonato']} {camp['temporada']}"
                if de is not None and de > ate:
                    logger.info("%s: em dia (%s). Nada a coletar.", rotulo, origem)
                    continue
                de_txt = f"{de:%d/%m/%Y}" if de else "início do calendário"
                logger.info("%s: %s -> %s até %s", rotulo, origem, de_txt, f"{ate:%d/%m/%Y}")
                plano.append((camp, de, ate))
    else:
        logger.info("SUPABASE_DB_URL ausente: varrendo todas as temporadas até ontem (sem filtro do banco).")
        for camp in campeonatos:
            de, ate = de_manual, (ate_manual or ontem)
            rotulo = f"{camp['campeonato']} {camp['temporada']}"
            de_txt = f"{de:%d/%m/%Y}" if de else "início do calendário"
            logger.info("%s: varredura completa -> %s até %s", rotulo, de_txt, f"{ate:%d/%m/%Y}")
            plano.append((camp, de, ate))

    if not plano:
        logger.info("Tudo atualizado. Nada a coletar.")
        return

    saida = {"campeonatos": []}
    diagnostico = {"gerado_em": datetime.now().isoformat(timespec="seconds"), "campeonatos": []}
    driver = proc = None
    falhas = 0
    try:
        driver, proc = criar_driver()
        for i, (camp, de, ate) in enumerate(plano, start=1):
            rotulo = f"{camp['campeonato']} {camp['temporada']}"
            logger.info("[%d/%d] %s", i, len(plano), rotulo)
            entrada = {
                "id_campeonato": camp["id_campeonato"],
                "campeonato": camp["campeonato"],
                "pais": camp["pais"],
                "temporada": camp["temporada"],
                "ids_jogos": [],
            }
            diag = {"campeonato": camp["campeonato"], "temporada": camp["temporada"],
                    "de": de.isoformat() if de else None, "ate": ate.isoformat()}
            try:
                garantir_origem(driver)
                jogos, por_status, paginas = listar_jogos_finalizados(driver, camp["id_campeonato"], camp["season_id"])
                ids = sorted(i for i, data in jogos.items() if (de is None or data >= de) and data <= ate)
                entrada["ids_jogos"] = ids
                datas = list(jogos.values())
                diag["diagnostico"] = {
                    "paginas": paginas,
                    "eventos_por_status": dict(por_status),
                    "finalizados_na_temporada": len(jogos),
                    "finalizados_no_intervalo": len(ids),
                    "primeira_data": min(datas).isoformat() if datas else None,
                    "ultima_data": max(datas).isoformat() if datas else None,
                }
                logger.info("   %d finalizado(s) na temporada | %d no intervalo | status: %s",
                            len(jogos), len(ids), dict(por_status))
            except KeyboardInterrupt:
                logger.warning("Interrompido pelo usuário. Gravando os campeonatos já concluídos.")
                break
            except Exception as e:
                falhas += 1
                diag["erro"] = str(e)
                logger.error("   Falha em %s: %s", rotulo, e)
            saida["campeonatos"].append(entrada)
            diagnostico["campeonatos"].append(diag)
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass

    total = sum(len(c["ids_jogos"]) for c in saida["campeonatos"])
    arquivo_ids.parent.mkdir(parents=True, exist_ok=True)
    arquivo_diag = arquivo_ids.with_name("id_jogos_diagnostico.json")
    gravar_json(arquivo_ids, saida)
    gravar_json(arquivo_diag, diagnostico)
    logger.info("FINAL: %d ID(s) em %d campeonato(s) | falhas: %d", total, len(saida["campeonatos"]), falhas)
    logger.info("IDs salvos em %s", arquivo_ids)
    logger.info("Diagnóstico salvo em %s", arquivo_diag)


if __name__ == "__main__":
    main()