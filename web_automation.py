"""
web_automation.py — Browser Automation Worker (J.A.R.V.I.S.)

Automação web 100% assíncrona (headless) usando Playwright quando disponível,
com fallback transparente para httpx (acesso/leitura/download) caso o navegador
não esteja instalado. Todas as operações salvam artefatos em `data/downloads/`.

Ações suportadas (via comando /web <ação> ...):
  - pesquisar <termo>            — busca dinâmica na web e resume o resultado
  - acessar  <url>               — abre a página e extrai título + texto
  - baixar   <url>               — faz o download do arquivo para data/downloads/
  - preencher <url> | <seletor> | <valor> — preenche um formulário e envia
  - screenshot <url>             — captura a página e salva em data/downloads/

Este módulo é pensado para ser chamado dentro de uma QThread (AutomacaoWorker),
portanto nunca deve bloquear a UI principal.
"""

import re
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Tuple

import httpx

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - fallback opcional
    sync_playwright = None  # type: ignore[assignment]

try:
    from config_manager import carregar_configuracao
except ImportError:  # pragma: no cover
    def carregar_configuracao() -> dict:
        return {}


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _log(mensagem: str, nivel: str = "INFO") -> None:
    print(f"[WEB-AUTO {nivel:<5}] {mensagem}", flush=True)


def _diretorio_downloads() -> Path:
    """Devolve (criando se necessário) o diretório data/downloads/."""
    config = carregar_configuracao()
    data_dir = Path(config.get("data_directory", "data"))
    downloads = data_dir / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    return downloads


def _playwright_disponivel() -> bool:
    return sync_playwright is not None


class _TextExtractor(HTMLParser):
    """Extrai texto legível de HTML, descartando script/style/noscript."""

    def __init__(self) -> None:
        super().__init__()
        self._skip = False
        self._partes: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data) -> None:
        if not self._skip:
            self._partes.append(data)


def _extrair_texto_html(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html or "")
    except Exception:
        pass
    texto = " ".join(parser._partes)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _nome_arquivo_de_url(url: str, content_type: str = "") -> str:
    """Deriva um nome de arquivo seguro a partir da URL."""
    nome = url.rstrip("/").split("/")[-1]
    nome = re.sub(r"[?#].*$", "", nome)
    nome = re.sub(r"[^A-Za-z0-9._-]", "_", nome) or "arquivo"
    if not Path(nome).suffix:
        # Tenta inferir extensão a partir do Content-Type.
        ext = {
            "application/pdf": ".pdf",
            "application/zip": ".zip",
            "text/html": ".html",
            "image/png": ".png",
            "image/jpeg": ".jpg",
        }.get(content_type.split(";")[0].strip().lower(), "")
        nome += ext or ".bin"
    return nome


# ---------------------------------------------------------------------------
# Navegação
# ---------------------------------------------------------------------------

def _navegar_playwright(url: str) -> Tuple[str, str]:
    """Abre a URL com Playwright headless e retorna (titulo, texto)."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            titulo = page.title()
            texto = _extrair_texto_html(page.content())
            return titulo, texto
        finally:
            browser.close()


def _navegar_httpx(url: str) -> Tuple[str, str]:
    """Fallback: busca a página via httpx e retorna (titulo, texto)."""
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        resp = client.get(url, headers={"User-Agent": "J.A.R.V.I.S/2.0"})
        resp.raise_for_status()
    html = resp.text
    texto = _extrair_texto_html(html)
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    titulo = m.group(1).strip() if m else url
    return titulo, texto


def _acessar(url: str) -> Tuple[bool, str]:
    """Acessa uma página e devolve um resumo textual."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        if _playwright_disponivel():
            titulo, texto = _navegar_playwright(url)
        else:
            titulo, texto = _navegar_httpx(url)
    except Exception as exc:
        return False, f"Falha ao acessar '{url}': {exc}"

    resumo = (texto or "")[:2500]
    return True, (
        f"PÁGINA ACESSADA\n{'─' * 40}\n"
        f"URL: {url}\nTÍTULO: {titulo or '(sem título)'}\n\n"
        f"CONTEÚDO EXTRAÍDO:\n{resumo or '(sem conteúdo textual)'}"
    )


def _pesquisar(termo: str) -> Tuple[bool, str]:
    """Busca o termo no DuckDuckGo e resume os resultados."""
    url = "https://duckduckgo.com/html/?q=" + termo.replace(" ", "+")
    try:
        if _playwright_disponivel():
            titulo, texto = _navegar_playwright(url)
        else:
            titulo, texto = _navegar_httpx(url)
    except Exception as exc:
        return False, f"Falha na pesquisa: {exc}"

    resumo = (texto or "")[:2500]
    return True, (
        f"PESQUISA: '{termo}'\n{'─' * 40}\n"
        f"RESULTADOS (trecho):\n{resumo or '(sem resultados)'}"
    )


def _baixar(url: str) -> Tuple[bool, str]:
    """Baixa um arquivo para data/downloads/ usando streaming assíncrono."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    downloads = _diretorio_downloads()
    try:
        with httpx.Client(follow_redirects=True, timeout=120) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                nome = _nome_arquivo_de_url(url, content_type)
                destino = downloads / nome
                total = 0
                with open(destino, "wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
                        total += len(chunk)
    except Exception as exc:
        return False, f"Falha no download de '{url}': {exc}"

    tamanho_kb = total // 1024
    return True, (
        f"DOWNLOAD CONCLUÍDO\n{'─' * 40}\n"
        f"Arquivo: {destino}\nTamanho: {tamanho_kb} KB"
    )


def _preencher(url: str, seletor: str, valor: str) -> Tuple[bool, str]:
    """Preenche um campo de formulário e submete (requer Playwright)."""
    if not _playwright_disponivel():
        return False, "Preenchimento de formulário requer Playwright instalado."
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.fill(seletor, valor)
                page.press(seletor, "Enter")
                time.sleep(2)
                titulo = page.title()
            finally:
                browser.close()
    except Exception as exc:
        return False, f"Falha ao preencher formulário: {exc}"

    return True, (
        f"FORMULÁRIO PREENCHIDO\n{'─' * 40}\n"
        f"URL: {url}\nSeletor: {seletor}\nValor: {valor}\n"
        f"Título após envio: {titulo or '(sem título)'}"
    )


def _screenshot(url: str) -> Tuple[bool, str]:
    """Captura a página e salva em data/downloads/ (requer Playwright)."""
    if not _playwright_disponivel():
        return False, "Captura de página requer Playwright instalado."
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    downloads = _diretorio_downloads()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    destino = downloads / f"web_{timestamp}.png"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.screenshot(path=str(destino), full_page=True)
            finally:
                browser.close()
    except Exception as exc:
        return False, f"Falha na captura de página: {exc}"

    return True, f"CAPTURA SALVA\n{'─' * 40}\nArquivo: {destino}"


# ---------------------------------------------------------------------------
# Interpretador do comando /web
# ---------------------------------------------------------------------------

_ACOES = {
    "pesquisar": _pesquisar,
    "search": _pesquisar,
    "acessar": _acessar,
    "abrir": _acessar,
    "navegar": _acessar,
    "baixar": _baixar,
    "download": _baixar,
    "screenshot": _screenshot,
    "capturar": _screenshot,
}


def interpretar_e_executar(comando: str) -> Tuple[bool, str]:
    """
    Interpreta o corpo do comando `/web <ação> [argumentos]` e executa a ação.

    Retorna (sucesso, resumo) compatível com o AutomacaoWorker.
    """
    texto = (comando or "").strip()
    if not texto:
        return False, (
            "Uso: /web <ação> <argumentos>\n"
            "Ações: pesquisar <termo> | acessar <url> | baixar <url> |\n"
            "       preencher <url> | <seletor> | <valor> | screenshot <url>"
        )

    partes = texto.split(maxsplit=1)
    acao = partes[0].lower()
    resto = partes[1].strip() if len(partes) > 1 else ""

    if acao == "preencher":
        campos = [c.strip() for c in resto.split("|")]
        if len(campos) < 3:
            return False, "Uso: /web preencher <url> | <seletor> | <valor>"
        return _preencher(campos[0], campos[1], campos[2])

    funcao = _ACOES.get(acao)
    if funcao is None:
        return False, f"Ação desconhecida: '{acao}'. Use /web para ver as ações."
    if not resto:
        return False, f"Ação '{acao}' requer um argumento (termo ou URL)."

    _log(f"Executando ação '{acao}' — '{resto[:80]}'")
    return funcao(resto)


# ---------------------------------------------------------------------------
# Teste seguro (sem rede por padrão)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S — Web Automation Worker (teste)")
    print("=" * 60)
    print(f"Playwright disponível: {_playwright_disponivel()}")
    print(f"Diretório de downloads: {_diretorio_downloads()}")
    print("\nUse interpretar_e_executar() via /web no chat para ações reais.")
