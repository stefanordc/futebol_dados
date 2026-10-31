CAMPEONATO = "Norueguês"
PAIS = "Noruega"
TEMPORADA = "2024"

# python -u "C:\Users\stefano.faria\Desktop\analise_dados\dados_futebol\jogos_ogol\minutos_gols.py"

ARQUIVO_IDS = r"C:\Users\stefano.faria\Desktop\analise_dados\dados_futebol\jogos_ogol\id_jogos.txt"
ARQUIVO_CLUBES = r"C:\Users\stefano.faria\Desktop\analise_dados\dados_futebol\jogos_ogol\clubes_sofascore.json"

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
from psycopg2.extras import execute_values
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("sofascore_minutos_gols")

BASE_URL = "https://www.sofascore.com/api/v1"
BRASILIA_TZ = timezone(timedelta(hours=-3))
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


def carregar_json_map(path):
    if not path or not os.path.exists(path):
        logger.warning("Arquivo de padronização não encontrado: %s (tratado como vazio)", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            conteudo = f.read().strip()
        if not conteudo:
            return {}
        data = json.loads(conteudo)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("Erro ao carregar %s: %s", path, e)
        return {}


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


def ler_ids(arquivo: Path) -> list[int]:
    if not arquivo.is_file():
        raise FileNotFoundError(f"Arquivo de IDs não encontrado: {arquivo}")

    resultado = []
    vistos = set()
    texto = arquivo.read_text(encoding="utf-8-sig")
    for numero, linha in enumerate(texto.splitlines(), start=1):
        linha = linha.strip()
        if not linha or linha.startswith("#") or linha.lower() in ("id_jogo", "jogo_id"):
            continue
        id_texto = re.split(r"[;,\t ]", linha, maxsplit=1)[0].strip()
        if not id_texto.isdecimal():
            logger.warning("Linha %d ignorada (ID inválido): %r", numero, linha)
            continue
        id_jogo = int(id_texto)
        if id_jogo not in vistos:
            vistos.add(id_jogo)
            resultado.append(id_jogo)
    return resultado


def gerar_dados_jogo(evento: dict, clubes_map: dict) -> dict | None:
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
        return clubes_map.get(str(clube.get("id"))) or clube.get("name") or ""

    torneio = evento.get("tournament") or {}
    unique = torneio.get("uniqueTournament") or {}
    campeonato_id = _to_int(unique.get("id")) or _to_int(torneio.get("id"))

    return {
        "id_jogo": _to_int(evento.get("id")),
        "data": data,
        "id_campeonato": campeonato_id,
        "campeonato": CAMPEONATO,
        "pais": PAIS,
        "temporada": str(TEMPORADA),
        "id_mandante": id_casa,
        "mandante": clube_padronizado(casa),
        "id_visitante": id_fora,
        "visitante": clube_padronizado(fora),
    }


COLUNAS_GOLS = [
    "data", "temporada", "pais", "campeonato",
    "id_jogo", "id_clube", "clube", "lado", "minuto", "placar",
]


def extrair_gols(resposta: dict, jogo: dict) -> list[dict]:
    linhas = []
    for inc in (resposta or {}).get("incidents", []):
        if inc.get("incidentType") != "goal":
            continue

        eh_casa = inc.get("isHome")
        if eh_casa is None:
            logger.warning("Jogo %s: gol sem isHome, ignorado: %s", jogo["id_jogo"], inc.get("id"))
            continue

        if eh_casa:
            lado, id_clube, clube = "casa", jogo["id_mandante"], jogo["mandante"]
        else:
            lado, id_clube, clube = "fora", jogo["id_visitante"], jogo["visitante"]

        minuto = _to_int(inc.get("time"))
        if minuto is not None:
            minuto += _to_int(inc.get("addedTime")) or 0

        gols_casa = _to_int(inc.get("homeScore"))
        gols_fora = _to_int(inc.get("awayScore"))
        placar = f"{gols_casa}-{gols_fora}" if gols_casa is not None and gols_fora is not None else None

        linhas.append({
            "data": jogo["data"],
            "temporada": jogo["temporada"],
            "pais": jogo["pais"],
            "campeonato": jogo["campeonato"],
            "id_jogo": jogo["id_jogo"],
            "id_clube": id_clube,
            "clube": clube,
            "lado": lado,
            "minuto": minuto,
            "placar": placar,
        })

    linhas.sort(key=lambda l: (l["minuto"] is None, l["minuto"] or 0))
    return linhas


def salvar_gols(linhas: list[dict]):
    if not linhas:
        return
    atualizaveis = [c for c in COLUNAS_GOLS if c not in ("id_jogo", "placar")]
    update = ", ".join(f"{c} = EXCLUDED.{c}" for c in atualizaveis)
    sql = f"""
        INSERT INTO minutos_gols ({", ".join(COLUNAS_GOLS)})
        VALUES %s
        ON CONFLICT (id_jogo, placar) DO UPDATE SET {update}
    """
    valores = [tuple(l.get(c) for c in COLUNAS_GOLS) for l in linhas]
    with conexao_bd() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, valores)


def ids_ja_coletados(ids: list[int]) -> set[int]:
    try:
        with conexao_bd() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT id_jogo FROM minutos_gols WHERE id_jogo = ANY(%s)",
                    (list(ids),),
                )
                return {int(linha[0]) for linha in cur.fetchall()}
    except Exception as e:
        logger.warning("Não foi possível consultar jogos já coletados (%s). Coletando todos.",
                       str(e).splitlines()[0] if str(e) else type(e).__name__)
        return set()


def main():
    arquivo = Path(ARQUIVO_IDS)
    pasta_projeto = arquivo.parent
    carregar_variaveis_de_ambiente(pasta_projeto)

    if not CAMPEONATO.strip() or not PAIS.strip() or not str(TEMPORADA).strip():
        raise ValueError("Preencha CAMPEONATO, PAIS e TEMPORADA no início do código")
    if not os.environ.get("SUPABASE_DB_URL"):
        raise RuntimeError(f"SUPABASE_DB_URL ausente: configure no .env em {pasta_projeto}")

    ids = ler_ids(arquivo)
    logger.info("Campeonato: %s | País: %s | Temporada: %s", CAMPEONATO, PAIS, TEMPORADA)
    logger.info("Arquivo: %s | IDs únicos: %d", arquivo, len(ids))
    if not ids:
        logger.warning("Nenhum ID válido no arquivo. Encerrando.")
        return

    if os.environ.get("SOFASCORE_PULAR_EXISTENTES", "1").strip().lower() not in ("0", "false", "no", "nao", "não"):
        ja_coletados = ids_ja_coletados(ids)
        if ja_coletados:
            logger.info("Pulando %d jogos que já têm gols no banco.", len(ja_coletados))
            ids = [i for i in ids if i not in ja_coletados]
        if not ids:
            logger.info("Nada novo para coletar. Encerrando.")
            return
        logger.info("IDs a coletar: %d", len(ids))

    clubes_map = carregar_json_map(ARQUIVO_CLUBES)
    cliente = None
    total_jogos, total_gols, sem_gols, ignorados, falhas = 0, 0, 0, 0, []
    try:
        cliente = ClienteSofascore()
        for indice, id_jogo in enumerate(ids, start=1):
            logger.info("[%d/%d] Jogo %s", indice, len(ids), id_jogo)
            try:
                resposta = cliente.fetch_json(f"{BASE_URL}/event/{id_jogo}")
                evento = resposta.get("event", resposta)
                if _to_int(evento.get("id")) != id_jogo:
                    raise ValueError("ID retornado diferente do ID solicitado")
                jogo = gerar_dados_jogo(evento, clubes_map)
                if jogo is None:
                    ignorados += 1
                    continue

                linhas = []
                try:
                    resposta_inc = cliente.fetch_json(f"{BASE_URL}/event/{id_jogo}/incidents")
                    linhas = extrair_gols(resposta_inc, jogo)
                except SofascoreHTTPError as e:
                    if e.status != 404:
                        raise
                    logger.warning("Jogo %s sem endpoint de incidentes (404).", id_jogo)

                salvar_gols(linhas)
                total_jogos += 1
                if linhas:
                    total_gols += len(linhas)
                    logger.info("Jogo %s: %d gols salvos em minutos_gols.", id_jogo, len(linhas))
                else:
                    sem_gols += 1
                    logger.info("Jogo %s: nenhum gol encontrado (0x0 ou sem dados).", id_jogo)
            except KeyboardInterrupt:
                raise
            except Exception as e:
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
        "FINAL: jogos=%d | gols=%d | sem gols=%d | não finalizados=%d | falhas=%d",
        total_jogos, total_gols, sem_gols, ignorados, len(falhas),
    )
    if falhas:
        arquivo_falhas = arquivo.with_name("id_jogos_falhas.txt")
        try:
            arquivo_falhas.write_text("\n".join(str(i) for i in falhas) + "\n", encoding="utf-8")
            logger.warning(
                "IDs com erro salvos em %s (copie para id_jogos.txt para nova tentativa): %s",
                arquivo_falhas, falhas,
            )
        except OSError as e:
            logger.warning("Não foi possível salvar %s (%s). IDs com erro: %s", arquivo_falhas, e, falhas)


if __name__ == "__main__":
    try:
        main()
    finally:
        emitir_som_conclusao()