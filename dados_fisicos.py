import json
import logging
import os
import random
import re
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

import psycopg2
import requests
import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

DIR = Path(__file__).resolve().parent
ARQUIVO_IDS = DIR / "id_jogos_sofascore.txt"
ARQUIVO_CLUBES = DIR / "clubes.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("sofascore_coleta")

BASE_URL = "https://www.sofascore.com/api/v1"
BRASILIA_TZ = timezone(timedelta(hours=-3))
FONTE = "sofascore"
PERIODO_FISICO = "Completo"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
ACCEPT_LANGUAGE = "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"


def carregar_variaveis_de_ambiente(pasta_projeto):
    env_path = pasta_projeto / ".env"
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            chave = chave.strip()
            valor = valor.strip().strip('"').strip("'")
            os.environ.setdefault(chave, valor)


def _to_int(valor):
    if valor in (None, ""):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _to_float(valor):
    if valor in (None, ""):
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


CHAVES_ID = ("id", "id_clube", "sofascore_id", "id_sofascore", "team_id")
CHAVES_NOME = ("nome", "name", "clube", "nome_clube", "nome_padronizado", "padronizado")


def carregar_mapa_clubes(path):
    """Devolve {id_do_clube (str): nome exatamente como está no arquivo}."""
    if not path or not os.path.exists(path):
        logger.error("Arquivo de clubes NÃO encontrado: %s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            dados = json.load(f)
    except Exception as e:
        logger.error("Erro ao ler %s: %s", path, e)
        return {}

    mapa = {}

    def achar(item, chaves):
        for c in chaves:
            if c in item and item[c] not in (None, ""):
                return item[c]
        return None

    if isinstance(dados, dict):
        for chave, valor in dados.items():
            if isinstance(valor, dict):
                # {"123": {"nome": "Clube"}}
                nome = achar(valor, CHAVES_NOME)
                id_clube = achar(valor, CHAVES_ID) or chave
                if nome:
                    mapa[str(id_clube).strip()] = nome
            elif isinstance(valor, (str, int)):
                chave_s, valor_s = str(chave).strip(), str(valor).strip()
                if chave_s.isdecimal() and not valor_s.isdecimal():
                    mapa[chave_s] = valor            # {"123": "Clube"}
                elif valor_s.isdecimal() and not chave_s.isdecimal():
                    mapa[valor_s] = chave            # {"Clube": 123}
    elif isinstance(dados, list):
        for item in dados:
            if not isinstance(item, dict):
                continue
            id_clube = achar(item, CHAVES_ID)
            nome = achar(item, CHAVES_NOME)
            if id_clube is not None and nome:
                mapa[str(id_clube).strip()] = nome

    logger.info("Padronização de clubes: %d IDs carregados de %s", len(mapa), path)
    if not mapa:
        logger.error("Nenhum clube foi reconhecido em %s. Verifique o formato do arquivo.", path)
    return mapa


def _modo_navegador():
    modo = os.environ.get("SOFASCORE_MODO", "navegador").strip().lower()
    return "uc" if modo == "uc" else "navegador"


def _porta_debug():
    valor = os.environ.get("SOFASCORE_PORTA", "9222").strip()
    return int(valor) if valor.isdigit() else 9222


def _pasta_perfil():
    return Path(os.environ.get("SOFASCORE_PERFIL") or (Path.home() / "sofascore_perfil"))


def _headless_ativo():
    valor = os.environ.get("SOFASCORE_HEADLESS", "1").strip().lower()
    return valor not in ("0", "false", "no", "nao", "não")


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


def _garantir_navegador_depuracao():
    porta = _porta_debug()
    versao = _versao_chromium(porta)
    if versao:
        logger.info("Navegador com depuração já aberto na porta %d (Chromium %s).", porta, versao)
        return None, versao

    caminho = _achar_navegador()
    if not caminho:
        raise RuntimeError(
            "Nenhum navegador encontrado. Defina BROWSER_PATH com o caminho do "
            "brave.exe / chrome.exe / msedge.exe."
        )
    perfil = _pasta_perfil()
    perfil.mkdir(parents=True, exist_ok=True)
    logger.info("Abrindo navegador: %s (perfil: %s)", caminho, perfil)
    proc = subprocess.Popen([
        caminho,
        f"--remote-debugging-port={porta}",
        f"--user-data-dir={perfil}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,900",
        "https://www.sofascore.com/",
    ])
    for _ in range(80):
        time.sleep(0.5)
        versao = _versao_chromium(porta)
        if versao:
            return proc, versao
    raise RuntimeError(
        f"O navegador não respondeu na porta {porta}. Feche todas as janelas dele "
        "(ou use outra porta em SOFASCORE_PORTA) e tente de novo."
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


def _montar_opcoes_uc(headless):
    options = uc.ChromeOptions()
    options.page_load_strategy = "eager"
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=pt-BR")
    prefs = {
        "profile.default_content_setting_values.notifications": 2,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.default_content_setting_values.cookies": 1,
        "intl.accept_languages": "pt-BR,pt,en-US,en",
    }
    options.add_experimental_option("prefs", prefs)
    return options


def _iniciar_uc(headless):
    kwargs = {"options": _montar_opcoes_uc(headless), "headless": headless}
    versao = os.environ.get("CHROME_VERSION_MAIN", "").strip()
    if versao.isdigit():
        kwargs["version_main"] = int(versao)
    return uc.Chrome(**kwargs)


def criar_driver_chrome():
    headless = _headless_ativo()
    try:
        driver = _iniciar_uc(headless)
    except Exception as e:
        primeira_linha_erro = str(e).splitlines()[0] if str(e) else type(e).__name__
        logger.warning("Falha ao iniciar undetected-chromedriver: %s", primeira_linha_erro)
        driver = None
        if "only supports Chrome version" in str(e) or "session not created" in str(e):
            logger.info("Possível incompatibilidade de versão do ChromeDriver. Limpando cache e tentando novamente.")
            _limpar_cache_undetected_chromedriver()
            try:
                driver = _iniciar_uc(headless)
            except Exception as e2:
                logger.warning("Falha após limpar o cache: %s", str(e2).splitlines()[0])
        if driver is None:
            logger.info("Utilizando Selenium padrão como alternativa.")
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager
            chrome_options = webdriver.ChromeOptions()
            chrome_options.page_load_strategy = "eager"
            if headless:
                chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--lang=pt-BR")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(45)
    driver.implicitly_wait(0)
    _injetar_anti_deteccao(driver)
    return driver


def _limpar_cache_undetected_chromedriver():
    import shutil
    possiveis_caches = [
        Path.home() / "appdata" / "roaming" / "undetected_chromedriver",
        Path.home() / "AppData" / "Roaming" / "undetected_chromedriver",
        Path.home() / ".local" / "share" / "undetected_chromedriver",
        Path.home() / "Library" / "Application Support" / "undetected_chromedriver",
    ]
    for cache_dir in possiveis_caches:
        if cache_dir.is_dir():
            try:
                shutil.rmtree(cache_dir)
            except Exception as e:
                logger.warning("Não foi possível remover o cache em %s: %s", cache_dir, e)


def _injetar_anti_deteccao(driver):
    script = "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": script})
    except Exception:
        try:
            driver.execute_script(script)
        except Exception:
            pass
    try:
        ua = driver.execute_script("return navigator.userAgent") or ""
        if "Headless" in ua:
            driver.execute_cdp_cmd(
                "Network.setUserAgentOverride",
                {"userAgent": ua.replace("HeadlessChrome", "Chrome"), "acceptLanguage": ACCEPT_LANGUAGE},
            )
    except Exception:
        pass


def _descobrir_user_agent(driver):
    try:
        ua = driver.execute_script("return navigator.userAgent") or ""
        if ua:
            return ua.replace("HeadlessChrome", "Chrome")
    except Exception:
        pass
    return USER_AGENT


def abrir_pagina_com_tolerancia(driver, url, timeout_s=30, tentativas=2):
    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            driver.set_page_load_timeout(timeout_s)
            driver.get(url)
            return True
        except TimeoutException as e:
            ultimo_erro = e
            logger.warning(
                "Timeout ao abrir %s (tentativa %d/%d). Interrompendo o carregamento pendente.",
                url, tentativa, tentativas,
            )
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass
            try:
                atual = (driver.current_url or "").lower()
                if "sofascore.com" in atual:
                    return True
            except Exception:
                pass
        except WebDriverException as e:
            ultimo_erro = e
            logger.warning(
                "Erro do Chrome ao abrir %s (tentativa %d/%d): %s",
                url, tentativa, tentativas, str(e).splitlines()[0],
            )
            if _erro_de_sessao(e):
                break
        except Exception as e:
            ultimo_erro = e
            logger.warning(
                "Erro ao abrir %s (tentativa %d/%d): %s",
                url, tentativa, tentativas, str(e).splitlines()[0],
            )
        if tentativa < tentativas:
            time.sleep(1.5)
    logger.warning(
        "Não foi possível concluir a abertura de %s. Último erro: %s",
        url, str(ultimo_erro).splitlines()[0] if ultimo_erro else "desconhecido",
    )
    return False


def fechar_driver(driver):
    try:
        if driver:
            driver.quit()
    except OSError as e:
        if getattr(e, "winerror", None) != 6:
            logger.warning("Erro ao fechar navegador: %s", e)
    except Exception as e:
        logger.warning("Erro ao fechar navegador: %s", e)
    finally:
        try:
            if driver is not None:
                service = getattr(driver, "service", None)
                if service is not None:
                    service.process = None
        except Exception:
            pass


def _erro_de_sessao(excecao):
    texto = str(excecao).lower()
    return any(termo in texto for termo in (
        "invalid session id", "session not created", "no such window",
        "target window already closed", "chrome not reachable", "disconnected",
        "web view not found", "not connected to devtools",
    ))


def emitir_som_conclusao():
    try:
        import winsound
        winsound.Beep(1000, 500)
    except ImportError:
        pass


def construir_sessao_requests(driver, user_agent=None):
    if curl_requests is not None:
        sessao = curl_requests.Session(impersonate="chrome")
        headers = {}
    else:
        sessao = requests.Session()
        headers = {"User-Agent": user_agent or USER_AGENT}
    headers.update({
        "Accept": "*/*",
        "Accept-Language": ACCEPT_LANGUAGE,
        "Referer": "https://www.sofascore.com/",
        "Origin": "https://www.sofascore.com",
    })
    sessao.headers.update(headers)
    try:
        cookies = driver.get_cookies()
    except Exception as e:
        logger.warning("Não foi possível ler os cookies do navegador: %s", str(e).splitlines()[0])
        cookies = []
    for cookie in cookies:
        try:
            sessao.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"))
        except Exception:
            pass
    return sessao


class SofascoreHTTPError(RuntimeError):
    def __init__(self, status, url):
        super().__init__(f"HTTP {status} em {url}")
        self.status = status
        self.url = url


JS_FETCH_SAME_ORIGIN = """
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

MARCAS_PAGINA_BLOQUEADA = (
    "just a moment", "access denied", "attention required",
    "verify you are human", "captcha", "forbidden",
)


def _esperar_enter(timeout_s):
    fim = time.monotonic() + timeout_s
    try:
        import msvcrt
        while time.monotonic() < fim:
            if msvcrt.kbhit():
                if msvcrt.getwch() in ("\r", "\n"):
                    return True
            time.sleep(0.2)
        return False
    except ImportError:
        import select
        try:
            pronto, _, _ = select.select([sys.stdin], [], [], timeout_s)
        except Exception:
            time.sleep(timeout_s)
            return False
        if pronto:
            sys.stdin.readline()
            return True
        return False


def _status_do_erro_json(dados):
    if isinstance(dados, dict) and isinstance(dados.get("error"), dict):
        return _to_int(dados["error"].get("code")) or 403
    return None


class ClienteSofascore:

    HOME_URL = "https://www.sofascore.com/"
    ORIGEM = "https://www.sofascore.com"

    def __init__(self):
        self.modo = _modo_navegador()
        self.driver = None
        self.proc = None
        self.sessao = None
        self.user_agent = USER_AGENT
        self._ultimo_request = 0.0
        self._fator_lentidao = 1.0
        self._falhas_totais_seguidas = 0
        self._requests_na_sessao = 0
        limite = os.environ.get("SOFASCORE_REQ_POR_SESSAO", "40").strip()
        self.limite_sessao = int(limite) if limite.isdigit() and int(limite) > 0 else 40
        logger.info("Modo de navegador: %s", self.modo)
        if self.modo == "uc" and curl_requests is None:
            logger.info(
                "curl_cffi não instalado — a camada HTTP usa 'requests' puro, mais fácil de "
                "detectar. Recomendado: pip install curl_cffi"
            )
        self._iniciar_navegador()


    def _iniciar_navegador(self):
        if self.modo == "navegador":
            self.driver, proc = criar_driver_anexado()
            if proc is not None:
                self.proc = proc
        else:
            self.driver = criar_driver_chrome()
        self.user_agent = _descobrir_user_agent(self.driver)
        self._aquecer()
        self.renovar_sessao()

    def _pagina_bloqueada(self):
        try:
            titulo = (self.driver.title or "").lower()
            corpo = (self.driver.execute_script(
                "return (document.body && document.body.innerText || '').slice(0, 400);"
            ) or "").lower()
        except Exception:
            return False
        return any(m in titulo or m in corpo for m in MARCAS_PAGINA_BLOQUEADA)

    def _pausa_manual(self, motivo):
        logger.warning("%s", motivo)
        valor = os.environ.get("SOFASCORE_ESPERA_MANUAL", "600").strip()
        espera = int(valor) if valor.isdigit() and int(valor) > 0 else 600
        confirmou = False
        if sys.stdin is not None and sys.stdin.isatty():
            print(
                "\n>>> Olhe a janela do navegador aberta pelo script. Se houver verificação "
                "(captcha/'verifique que você é humano'), resolva-a lá.\n"
                f">>> Pressione ENTER para continuar agora, ou aguarde {espera // 60} min "
                "que o script continua sozinho com uma sessão nova..."
            )
            confirmou = _esperar_enter(espera)
        else:
            time.sleep(espera)
        if confirmou:
            self.renovar_sessao()
        else:
            self.trocar_identidade("Espera automática concluída.")

    def _aquecer(self, tentativas=3):
        for tentativa in range(1, tentativas + 1):
            abrir_pagina_com_tolerancia(self.driver, self.HOME_URL)
            time.sleep(random.uniform(2.0, 4.0))
            try:
                self.driver.execute_script("window.scrollTo(0, 400);")
            except Exception:
                pass
            if not self._pagina_bloqueada():
                return True
            logger.warning("Página inicial parece bloqueada (tentativa %d/%d).", tentativa, tentativas)
            if self.modo == "navegador":
                self._pausa_manual("Verificação detectada na página inicial.")
            else:
                time.sleep(random.uniform(5, 10) * tentativa)
        logger.warning("Aquecimento terminou com possível bloqueio; seguindo mesmo assim.")
        return False

    def renovar_sessao(self):
        self.sessao = construir_sessao_requests(self.driver, self.user_agent)

    def reiniciar(self):
        if self.modo == "navegador":
            logger.warning("Recarregando a página inicial no navegador real...")
            abrir_pagina_com_tolerancia(self.driver, self.HOME_URL)
            time.sleep(random.uniform(3, 6))
            if self._pagina_bloqueada():
                self._pausa_manual("Página inicial ainda parece bloqueada.")
            else:
                self.renovar_sessao()
            return
        logger.warning("Reiniciando navegador e sessão (novo fingerprint e cookies)...")
        fechar_driver(self.driver)
        self.driver = None
        time.sleep(random.uniform(2, 5))
        self._iniciar_navegador()

    def _sessao_responde(self, url, tentativas=4):
        for i in range(1, tentativas + 1):
            try:
                status, corpo = self._via_navegador(url)
                if status == 200:
                    try:
                        dados = json.loads(corpo)
                    except ValueError:
                        dados = None
                    if dados is not None and not _status_do_erro_json(dados):
                        return True
            except Exception:
                pass
            if i == 2:
                try:
                    status, _ = self._via_navegacao(url)
                    if status == 200:
                        return True
                except Exception:
                    pass
            time.sleep(random.uniform(4, 7) * i)
        return False

    def trocar_identidade(self, motivo="", url_teste=None):
        logger.warning("Renovando a sessão do navegador (cookies e armazenamento limpos). %s", motivo)
        for comando, params in (
            ("Network.clearBrowserCookies", {}),
            ("Network.clearBrowserCache", {}),
            ("Storage.clearDataForOrigin", {"origin": self.ORIGEM, "storageTypes": "all"}),
        ):
            try:
                self.driver.execute_cdp_cmd(comando, params)
            except Exception:
                pass
        try:
            self.driver.delete_all_cookies()
        except Exception:
            pass
        time.sleep(random.uniform(3, 6))
        abrir_pagina_com_tolerancia(self.driver, self.HOME_URL)
        time.sleep(random.uniform(8, 12))
        try:
            self.driver.execute_script("window.scrollTo(0, 400);")
        except Exception:
            pass
        time.sleep(random.uniform(2, 4))
        if url_teste:
            if self._sessao_responde(url_teste):
                logger.info("Sessão nova validada; seguindo a coleta.")
            else:
                logger.warning("A sessão nova ainda não obteve resposta da API; o fluxo normal vai tratar.")
        self.renovar_sessao()
        self._requests_na_sessao = 0

    def abrir_pagina(self, url, espera=(3, 5)):
        abrir_pagina_com_tolerancia(self.driver, url)
        time.sleep(random.uniform(*espera))
        self.renovar_sessao()

    def close(self):
        fechar_driver(self.driver)
        self.driver = None
        if self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None


    def _via_navegador(self, url):
        if self.driver is None:
            raise RuntimeError("navegador indisponível")
        try:
            atual = self.driver.current_url or ""
        except Exception:
            atual = ""
        if not atual.startswith(self.ORIGEM):
            abrir_pagina_com_tolerancia(self.driver, self.HOME_URL)
            time.sleep(random.uniform(1.0, 2.0))
        self.driver.set_script_timeout(25)
        resultado = self.driver.execute_async_script(
            JS_FETCH_SAME_ORIGIN, url, "%06x" % random.getrandbits(24)
        )
        if not isinstance(resultado, dict):
            return 0, ""
        return int(resultado.get("status") or 0), resultado.get("body") or ""

    def _via_http(self, url):
        if self.sessao is None:
            self.renovar_sessao()
        resp = self.sessao.get(url, timeout=20)
        return resp.status_code, resp.text

    def _via_navegacao(self, url):
        if self.driver is None:
            raise RuntimeError("navegador indisponível")
        abrir_pagina_com_tolerancia(self.driver, url, timeout_s=30, tentativas=1)
        time.sleep(random.uniform(1.5, 3.0))
        texto = ""
        elementos = self.driver.find_elements(By.TAG_NAME, "pre")
        if elementos:
            texto = elementos[0].text
        if not texto:
            texto = self.driver.execute_script(
                "return document.body ? document.body.innerText : '';"
            ) or ""
        texto = texto.strip()
        try:
            if url.split("?")[0] not in (self.driver.current_url or ""):
                return 0, ""
        except Exception:
            pass
        if texto.startswith("{") or texto.startswith("["):
            try:
                dados = json.loads(texto)
            except ValueError:
                return 0, texto
            codigo = _status_do_erro_json(dados)
            if codigo:
                return codigo, texto
            return 200, texto
        return (403 if self._pagina_bloqueada() else 0), texto


    def _respeitar_intervalo(self):
        if self.modo == "navegador":
            minimo = random.uniform(1.5, 3.0) * self._fator_lentidao
        else:
            minimo = random.uniform(0.6, 1.4) * self._fator_lentidao
        decorrido = time.monotonic() - self._ultimo_request
        if decorrido < minimo:
            time.sleep(minimo - decorrido)
        self._ultimo_request = time.monotonic()
        self._requests_na_sessao += 1

    def _registrar_sucesso(self):
        self._falhas_totais_seguidas = 0
        self._fator_lentidao = max(1.0, self._fator_lentidao * 0.9)

    def _camadas(self, tentativa):
        if self.modo == "navegador":
            return [("navegador", self._via_navegador), ("navegacao", self._via_navegacao)]
        camadas = [("navegador", self._via_navegador), ("http", self._via_http)]
        if tentativa >= 3:
            camadas.append(("navegacao", self._via_navegacao))
        return camadas


    def fetch_json(self, url, tentativas=5):
        ultimo_erro = None
        bloqueios = 0
        for tentativa in range(1, tentativas + 1):
            if self.driver is None:
                try:
                    self._iniciar_navegador()
                except Exception as e:
                    ultimo_erro = f"navegador: {str(e).splitlines()[0] if str(e) else type(e).__name__}"
                    time.sleep(random.uniform(3, 6))
                    continue

            if self.modo == "navegador" and self._requests_na_sessao >= self.limite_sessao:
                try:
                    self.trocar_identidade(
                        f"Rotação preventiva após {self._requests_na_sessao} requests.",
                        url_teste=url,
                    )
                except Exception as e:
                    logger.warning("Falha ao renovar a sessão: %s", str(e).splitlines()[0] if str(e) else e)

            bloqueado = False
            for nome, camada in self._camadas(tentativa):
                self._respeitar_intervalo()
                try:
                    status, corpo = camada(url)
                except Exception as e:
                    ultimo_erro = f"{nome}: {str(e).splitlines()[0] if str(e) else type(e).__name__}"
                    logger.debug("Camada %s falhou: %s", nome, ultimo_erro)
                    if _erro_de_sessao(e):
                        try:
                            self.reiniciar()
                        except Exception as e2:
                            logger.warning("Falha ao reiniciar o navegador: %s", e2)
                        break
                    continue

                if status == 200:
                    try:
                        dados = json.loads(corpo)
                    except ValueError:
                        ultimo_erro = f"{nome}: resposta não é JSON"
                        continue
                    codigo = _status_do_erro_json(dados)
                    if codigo == 404:
                        self._registrar_sucesso()
                        raise SofascoreHTTPError(404, url)
                    if codigo:
                        ultimo_erro = f"{nome}: HTTP {codigo} (JSON de erro)"
                        logger.info("Camada '%s' devolveu JSON de erro (HTTP %s).", nome, codigo)
                        if codigo in (403, 429):
                            bloqueado = True
                        continue
                    self._registrar_sucesso()
                    return dados
                if status == 404:
                    self._registrar_sucesso()
                    raise SofascoreHTTPError(404, url)

                ultimo_erro = f"{nome}: HTTP {status}"
                logger.info("Camada '%s' respondeu HTTP %s.", nome, status)
                if status in (403, 429):
                    bloqueado = True

            if tentativa == tentativas:
                break

            self._fator_lentidao = min(self._fator_lentidao * 1.5, 5.0)
            if bloqueado:
                bloqueios += 1
                if self.modo == "navegador":
                    base = min(240, 45 * 2 ** (bloqueios - 1))
                else:
                    base = min(90, 4 * 2 ** bloqueios)
                espera = base * random.uniform(0.8, 1.3)
                logger.warning(
                    "Bloqueio detectado em %s (tentativa %d/%d). Aguardando %.0fs antes de repetir.",
                    url, tentativa, tentativas, espera,
                )
                time.sleep(espera)
                if bloqueios == 1 and self.modo == "navegador":
                    try:
                        self.trocar_identidade("Bloqueio detectado.", url_teste=url)
                    except Exception as e:
                        logger.warning("Falha ao renovar a sessão: %s", str(e).splitlines()[0] if str(e) else e)
                elif bloqueios >= 2:
                    if self.modo == "navegador":
                        self._pausa_manual(
                            "A API continua bloqueando. Na janela do script, abra esta URL numa aba "
                            f"e veja se os dados carregam (resolva qualquer verificação): {url}"
                        )
                    else:
                        try:
                            self.reiniciar()
                        except Exception as e:
                            logger.warning("Falha ao reiniciar o navegador: %s", e)
            else:
                time.sleep(random.uniform(1, 3) * tentativa)

        self._falhas_totais_seguidas += 1
        if self._falhas_totais_seguidas >= 3:
            if self.modo == "navegador":
                self._pausa_manual(
                    f"{self._falhas_totais_seguidas} requisições seguidas falharam."
                )
            else:
                espera = random.uniform(120, 240)
                logger.warning(
                    "%d requisições seguidas falharam. Cooldown de %.0fs e reinício do navegador.",
                    self._falhas_totais_seguidas, espera,
                )
                time.sleep(espera)
                try:
                    self.reiniciar()
                except Exception as e:
                    logger.warning("Falha ao reiniciar o navegador: %s", e)
            self._falhas_totais_seguidas = 0
            self._fator_lentidao = max(self._fator_lentidao, 2.0)

        raise RuntimeError(f"Falha ao buscar {url} após múltiplas tentativas: {ultimo_erro}")



# --- IDs, extração e banco (sprints + KM) ------------------------------------

COLUNAS_DADOS_FISICOS = [
    "id_jogo", "data", "id_campeonato", "campeonato", "pais", "temporada", "fase",
    "id_clube", "nome_clube", "mando", "distancia_percorrida", "sprints",
]


def ler_fonte_ids(arquivo: Path) -> list[dict]:
    """Lê id_jogos_sofascore.txt (JSON da coleta_jogos_id) e devolve campeonatos com IDs.

    Formato esperado:
      {"campeonatos": [{"id_campeonato", "campeonato", "pais", "temporada", "ids_jogos": [...]}]}
    """
    if not arquivo.is_file():
        raise FileNotFoundError(
            f"Arquivo de IDs não encontrado: {arquivo}. "
            "Rode coleta_jogos_id.py antes."
        )

    texto = arquivo.read_text(encoding="utf-8-sig").strip()
    if not texto:
        raise ValueError(f"{arquivo} está vazio.")

    try:
        dados = json.loads(texto)
    except ValueError as e:
        raise ValueError(
            f"{arquivo} precisa ser o JSON gerado por coleta_jogos_id.py ({e})."
        ) from e

    if isinstance(dados, dict):
        lista = dados.get("campeonatos")
    elif isinstance(dados, list):
        lista = dados
    else:
        lista = None
    if not isinstance(lista, list):
        raise ValueError(f'O JSON de {arquivo} não tem a lista "campeonatos".')

    resultado = []
    vistos = set()
    for posicao, item in enumerate(lista, start=1):
        if not isinstance(item, dict):
            logger.warning("Item %d do JSON ignorado (não é um objeto).", posicao)
            continue

        campeonato = str(item.get("campeonato") or "").strip()
        pais = str(item.get("pais") or "").strip()
        temporada = str(item.get("temporada") or "").strip()
        if not campeonato or not pais or not temporada:
            raise ValueError(
                f"Campeonato #{posicao} do JSON está sem 'campeonato', 'pais' ou 'temporada'."
            )
        if item.get("erro"):
            logger.warning(
                "%s %s veio com erro (%s); serão usados só os IDs que existirem.",
                campeonato, temporada, item.get("erro"),
            )

        ids = []
        for valor in item.get("ids_jogos") or []:
            id_jogo = _to_int(valor)
            if id_jogo is None:
                logger.warning("%s %s: ID inválido ignorado: %r", campeonato, temporada, valor)
                continue
            if id_jogo in vistos:
                continue
            vistos.add(id_jogo)
            ids.append(id_jogo)

        resultado.append({
            "id_campeonato": _to_int(item.get("id_campeonato")),
            "campeonato": campeonato,
            "pais": pais,
            "temporada": temporada,
            "ids": ids,
        })
    return resultado


def gerar_dados_jogo(evento: dict, clubes_map: dict, camp: dict) -> dict | None:
    status = (evento.get("status") or {}).get("type", "")
    if status != "finished":
        logger.info("Jogo %s ignorado: status %s (não finalizado).", evento.get("id"), status)
        return None

    timestamp = evento.get("startTimestamp")
    if not timestamp:
        raise ValueError("Evento sem startTimestamp")
    data = datetime.fromtimestamp(int(timestamp), tz=BRASILIA_TZ).date()

    casa = evento.get("homeTeam") or {}
    fora = evento.get("awayTeam") or {}
    id_casa = _to_int(casa.get("id"))
    id_fora = _to_int(fora.get("id"))
    if not id_casa or not id_fora:
        raise ValueError("Evento sem identificadores dos dois clubes")

    def clube_padronizado(clube: dict):
        id_clube = str(clube.get("id"))
        nome = clubes_map.get(id_clube)
        if nome:
            return nome
        logger.warning(
            "Clube ID %s (%s) não está no clubes.json; usando o nome da API.",
            id_clube, clube.get("name"),
        )
        return clube.get("name") or ""

    torneio = evento.get("tournament") or {}
    unique = torneio.get("uniqueTournament") or {}
    campeonato_api = _to_int(unique.get("id")) or _to_int(torneio.get("id"))
    campeonato_id = camp.get("id_campeonato") or campeonato_api
    if camp.get("id_campeonato") and campeonato_api and camp["id_campeonato"] != campeonato_api:
        logger.warning(
            "Jogo %s: o ID do campeonato no JSON (%s) difere do da API (%s); usando o do JSON.",
            evento.get("id"), camp["id_campeonato"], campeonato_api,
        )
    round_info = evento.get("roundInfo") or {}
    rodada = round_info.get("round")
    fase = (
        f"Rodada {rodada}" if rodada is not None else (
            round_info.get("name") or round_info.get("slug") or ""
        )
    )

    return {
        "id_jogo": _to_int(evento.get("id")),
        "data": data,
        "id_campeonato": campeonato_id,
        "campeonato": camp["campeonato"],
        "pais": camp["pais"],
        "temporada": str(camp["temporada"]),
        "fase": fase,
        "id_mandante": id_casa,
        "mandante": clube_padronizado(casa),
        "id_visitante": id_fora,
        "visitante": clube_padronizado(fora),
    }


def extrair_dados_fisicos(resposta: dict) -> tuple[dict, dict]:
    """Só sprints e KM do período ALL (jogo completo), por lado."""
    casa = {"distancia_percorrida": None, "sprints": None}
    fora = {"distancia_percorrida": None, "sprints": None}
    for bloco in (resposta or {}).get("statistics", []):
        if bloco.get("period") != "ALL":
            continue
        for grupo in bloco.get("groups", []) or []:
            for item in grupo.get("statisticsItems", []) or []:
                chave = item.get("key")
                if chave == "kilometersCovered":
                    casa["distancia_percorrida"] = _to_float(item.get("homeValue"))
                    fora["distancia_percorrida"] = _to_float(item.get("awayValue"))
                elif chave == "numberOfSprints":
                    casa["sprints"] = _to_int(item.get("homeValue"))
                    fora["sprints"] = _to_int(item.get("awayValue"))
        break
    return casa, fora


def linhas_dados_fisicos(jogo: dict, casa: dict, fora: dict) -> list[dict]:
    base = {
        "id_jogo": jogo["id_jogo"],
        "data": jogo["data"],
        "id_campeonato": jogo["id_campeonato"],
        "campeonato": jogo["campeonato"],
        "pais": jogo["pais"],
        "temporada": jogo["temporada"],
        "fase": jogo["fase"],
    }
    return [
        {
            **base,
            "id_clube": jogo["id_mandante"],
            "nome_clube": jogo["mandante"],
            "mando": "Casa",
            "distancia_percorrida": casa.get("distancia_percorrida"),
            "sprints": casa.get("sprints"),
        },
        {
            **base,
            "id_clube": jogo["id_visitante"],
            "nome_clube": jogo["visitante"],
            "mando": "Fora",
            "distancia_percorrida": fora.get("distancia_percorrida"),
            "sprints": fora.get("sprints"),
        },
    ]


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


def garantir_pais(cur, nome, cache):
    if not nome:
        return None
    if nome in cache:
        return cache[nome]
    cur.execute("SELECT id FROM paises WHERE lower(btrim(nome)) = lower(btrim(%s))", (nome,))
    row = cur.fetchone()
    if row:
        cache[nome] = row[0]
        return row[0]
    cur.execute("INSERT INTO paises (nome) VALUES (%s) RETURNING id", (nome,))
    cache[nome] = cur.fetchone()[0]
    return cache[nome]


def garantir_campeonato_sofascore(cur, id_sofascore, nome, pais_id, cache):
    if id_sofascore in cache:
        return cache[id_sofascore]
    cur.execute("SELECT id FROM campeonatos WHERE id_sofascore = %s", (id_sofascore,))
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE campeonatos
            SET nome = COALESCE(%s, nome),
                pais_id = COALESCE(%s, pais_id),
                atualizado_em = now()
            WHERE id = %s
            """,
            (nome, pais_id, row[0]),
        )
        cache[id_sofascore] = row[0]
        return row[0]
    # Liga já criada pelo FotMob (mesmo nome + país): só amarra o id_sofascore
    if nome:
        cur.execute(
            """
            SELECT id FROM campeonatos
            WHERE lower(btrim(nome)) = lower(btrim(%s))
              AND COALESCE(pais_id, -1) = COALESCE(%s, -1)
              AND id_sofascore IS NULL
            LIMIT 1
            """,
            (nome, pais_id),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                """
                UPDATE campeonatos
                SET id_sofascore = %s, atualizado_em = now()
                WHERE id = %s
                """,
                (id_sofascore, row[0]),
            )
            cache[id_sofascore] = row[0]
            return row[0]
    cur.execute(
        """
        INSERT INTO campeonatos (id_sofascore, nome, pais_id)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (id_sofascore, nome or f"Campeonato {id_sofascore}", pais_id),
    )
    cache[id_sofascore] = cur.fetchone()[0]
    return cache[id_sofascore]


def garantir_clube_sofascore(cur, id_externo, nome_externo, pais_id, cache):
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
        (clube_id, FONTE, chave, nome),
    )
    cache[chave] = cur.fetchone()[0]
    return cache[chave]


def resolver_jogo_id(cur, jogo: dict, campeonato_id, casa_id, fora_id):
    """Localiza o jogo pelo id_sofascore ou por data+times; cria se ainda não existir."""
    id_sofascore = int(jogo["id_jogo"])
    cur.execute("SELECT id FROM jogos WHERE id_sofascore = %s", (id_sofascore,))
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE jogos
            SET temporada = COALESCE(%s, temporada),
                data = COALESCE(%s, data),
                campeonato_id = COALESCE(%s, campeonato_id),
                rodada = COALESCE(%s, rodada),
                casa_id = COALESCE(%s, casa_id),
                fora_id = COALESCE(%s, fora_id),
                atualizado_em = now()
            WHERE id = %s
            """,
            (
                jogo.get("temporada"), jogo.get("data"), campeonato_id, jogo.get("fase"),
                casa_id, fora_id, row[0],
            ),
        )
        return row[0]

    cur.execute(
        """
        SELECT id FROM jogos
        WHERE data = %s AND campeonato_id = %s AND casa_id = %s AND fora_id = %s
        """,
        (jogo.get("data"), campeonato_id, casa_id, fora_id),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE jogos
            SET id_sofascore = %s,
                temporada = COALESCE(%s, temporada),
                rodada = COALESCE(%s, rodada),
                atualizado_em = now()
            WHERE id = %s AND id_sofascore IS NULL
            """,
            (id_sofascore, jogo.get("temporada"), jogo.get("fase"), row[0]),
        )
        return row[0]

    cur.execute(
        """
        INSERT INTO jogos (
          id_sofascore, temporada, data, campeonato_id, rodada, casa_id, fora_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            id_sofascore, jogo.get("temporada"), jogo.get("data"), campeonato_id,
            jogo.get("fase"), casa_id, fora_id,
        ),
    )
    return cur.fetchone()[0]


def upsert_fisicos_estatisticas(cur, jogo_id, clube_id, mando, distancia, sprints):
    cur.execute(
        """
        SELECT id FROM estatisticas
        WHERE jogo_id = %s AND clube_id = %s AND periodo IS NOT DISTINCT FROM %s
        """,
        (jogo_id, clube_id, PERIODO_FISICO),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE estatisticas
            SET mando = COALESCE(%s, mando),
                distancia_percorrida = %s,
                sprints = %s,
                atualizado_em = now()
            WHERE id = %s
            """,
            (mando, distancia, sprints, row[0]),
        )
    else:
        cur.execute(
            """
            INSERT INTO estatisticas (
              jogo_id, clube_id, mando, periodo, distancia_percorrida, sprints
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (jogo_id, clube_id, mando, PERIODO_FISICO, distancia, sprints),
        )


def salvar_fisicos_no_banco(conn, linhas: list[dict], caches=None):
    """Persiste KM/sprints em estatisticas (período Completo), resolvendo jogo/clube Sofascore."""
    if not linhas:
        return 0
    caches = caches or {}
    cache_paises = caches.setdefault("paises", {})
    cache_campeonatos = caches.setdefault("campeonatos", {})
    cache_clubes = caches.setdefault("clubes", {})

    # Agrupa as 2 linhas (casa/fora) do mesmo jogo
    por_jogo = {}
    for linha in linhas:
        por_jogo.setdefault(linha["id_jogo"], []).append(linha)

    gravados = 0
    with conn.cursor() as cur:
        for id_sofascore, lados in por_jogo.items():
            amostra = lados[0]
            pais_id = garantir_pais(cur, amostra.get("pais"), cache_paises)
            campeonato_id = garantir_campeonato_sofascore(
                cur, amostra.get("id_campeonato"), amostra.get("campeonato"), pais_id, cache_campeonatos,
            )
            mapa_clubes = {}
            for lado in lados:
                mapa_clubes[lado["id_clube"]] = garantir_clube_sofascore(
                    cur, lado["id_clube"], lado.get("nome_clube"), pais_id, cache_clubes,
                )
            casa_ext = next((l["id_clube"] for l in lados if l.get("mando") == "Casa"), None)
            fora_ext = next((l["id_clube"] for l in lados if l.get("mando") == "Fora"), None)
            casa_id = mapa_clubes.get(casa_ext) if casa_ext is not None else None
            fora_id = mapa_clubes.get(fora_ext) if fora_ext is not None else None
            if not casa_id or not fora_id:
                raise ValueError(f"Clubes não resolvidos para jogo Sofascore {id_sofascore}")

            jogo_id = resolver_jogo_id(cur, amostra, campeonato_id, casa_id, fora_id)
            for lado in lados:
                clube_id = mapa_clubes[lado["id_clube"]]
                upsert_fisicos_estatisticas(
                    cur, jogo_id, clube_id, lado.get("mando"),
                    lado.get("distancia_percorrida"), lado.get("sprints"),
                )
                gravados += 1
    return gravados


def main():
    arquivo = Path(ARQUIVO_IDS)
    pasta_projeto = arquivo.parent
    carregar_variaveis_de_ambiente(pasta_projeto)
    if not os.environ.get("SUPABASE_DB_URL"):
        raise RuntimeError(f"SUPABASE_DB_URL ausente: configure no .env em {pasta_projeto}")

    campeonatos = ler_fonte_ids(arquivo)
    contexto = {}
    for camp in campeonatos:
        logger.info(
            "Campeonato: %s (ID %s) | País: %s | Temporada: %s | IDs: %d",
            camp["campeonato"], camp["id_campeonato"], camp["pais"], camp["temporada"], len(camp["ids"]),
        )
        for id_jogo in camp["ids"]:
            contexto[id_jogo] = camp
    ids = list(contexto)
    logger.info("Arquivo: %s | Campeonatos: %d | IDs únicos: %d", arquivo, len(campeonatos), len(ids))
    if not ids:
        logger.warning("Nenhum ID válido no arquivo. Encerrando.")
        return

    clubes_map = carregar_mapa_clubes(ARQUIVO_CLUBES)
    total_ok = total_sem_stats = ignorados = gravados = 0
    falhas = []
    caches = {}
    cliente = None
    try:
        cliente = ClienteSofascore()
        with conexao_bd() as conn:
            for indice, id_jogo in enumerate(ids, start=1):
                camp = contexto[id_jogo]
                logger.info(
                    "[%d/%d] Jogo %s (%s %s)",
                    indice, len(ids), id_jogo, camp["campeonato"], camp["temporada"],
                )
                try:
                    resposta = cliente.fetch_json(f"{BASE_URL}/event/{id_jogo}")
                    evento = resposta.get("event", resposta)
                    if _to_int(evento.get("id")) != id_jogo:
                        raise ValueError("ID retornado diferente do ID solicitado")
                    jogo = gerar_dados_jogo(evento, clubes_map, camp)
                    if jogo is None:
                        ignorados += 1
                        continue

                    casa = fora = {"distancia_percorrida": None, "sprints": None}
                    try:
                        resposta_stats = cliente.fetch_json(f"{BASE_URL}/event/{id_jogo}/statistics")
                        casa, fora = extrair_dados_fisicos(resposta_stats)
                    except SofascoreHTTPError as e:
                        if e.status != 404:
                            raise
                        logger.warning("Jogo %s sem endpoint de estatísticas (404).", id_jogo)

                    tem_dado = any(
                        v is not None
                        for v in (
                            casa.get("distancia_percorrida"), casa.get("sprints"),
                            fora.get("distancia_percorrida"), fora.get("sprints"),
                        )
                    )
                    if not tem_dado:
                        total_sem_stats += 1
                        logger.info("Jogo %s sem sprints/KM no período ALL.", id_jogo)
                    else:
                        total_ok += 1

                    n = salvar_fisicos_no_banco(conn, linhas_dados_fisicos(jogo, casa, fora), caches)
                    conn.commit()
                    gravados += n
                    logger.info("Jogo %s gravado no banco (%d linha(s)).", id_jogo, n)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    conn.rollback()
                    falhas.append(id_jogo)
                    logger.error("Erro no jogo %s: %s", id_jogo, e)
                if indice % 15 == 0 and indice < len(ids):
                    pausa = random.uniform(25, 45)
                    logger.info("Pausa de %.0fs após %d jogos para aliviar o ritmo.", pausa, indice)
                    time.sleep(pausa)
    finally:
        if cliente is not None:
            cliente.close()

    logger.info(
        "FINAL: gravados=%d | com sprints/KM=%d | sem ALL=%d | não finalizados=%d | falhas=%d",
        gravados, total_ok, total_sem_stats, ignorados, len(falhas),
    )
    if falhas:
        arquivo_falhas = arquivo.with_name("id_jogos_sofascore_falhas.txt")
        falhas_set = set(falhas)
        saida = {"campeonatos": []}
        for camp in campeonatos:
            ids_falha = [i for i in camp["ids"] if i in falhas_set]
            if ids_falha:
                saida["campeonatos"].append({
                    "id_campeonato": camp["id_campeonato"],
                    "campeonato": camp["campeonato"],
                    "pais": camp["pais"],
                    "temporada": camp["temporada"],
                    "ids_jogos": ids_falha,
                })
        try:
            arquivo_falhas.write_text(
                json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            logger.warning("IDs com erro salvos em %s: %s", arquivo_falhas, falhas)
        except OSError as e:
            logger.warning("Não foi possível salvar %s (%s). IDs com erro: %s", arquivo_falhas, e, falhas)


if __name__ == "__main__":
    try:
        main()
    finally:
        emitir_som_conclusao()
