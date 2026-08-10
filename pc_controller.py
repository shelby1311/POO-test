"""
pc_controller.py — Controle e Automação do Computador (J.A.R.V.I.S.)

Fornece funções de automação de mouse, teclado, execução de comandos,
abertura de aplicativos e captura de tela.

Toda ação perigosa (clique, digitação) é protegida pela trava de emergência
do kill_switch.py — a verificação ocorre ANTES e DURANTE cada operação.
"""

import os
import subprocess
import time
import datetime
from pathlib import Path
from typing import Optional, Tuple, Callable

import pyautogui

from config_manager import carregar_configuracao, validar_e_preparar_ambiente
from kill_switch import verificar_interrupcao, esta_acionado

try:
    import security
except ImportError:
    security = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Configuração do pyautogui
# ---------------------------------------------------------------------------

# Desabilitamos o failsafe nativo (canto 0,0) porque o kill_switch já provê
# uma trava de emergência mais robusta e explícita.
pyautogui.FAILSAFE = False

# Pausa padrão entre ações do pyautogui (segurança adicional)
pyautogui.PAUSE = 0.1

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _log(mensagem: str, nivel: str = "INFO") -> None:
    """Log formatado no terminal."""
    print(f"[PC-CTRL {nivel:<5}] {mensagem}", flush=True)


def _verificar_antes_acao(nome_acao: str) -> bool:
    """
    Checa a trava de emergência antes de uma ação automatizada.
    Retorna True se pode prosseguir, False se deve abortar.
    """
    if esta_acionado():
        if not verificar_interrupcao():
            _log(f"Ação '{nome_acao}' cancelada pelo usuário.", "WARNING")
            return False
    return True


def _resolver_diretorio_screenshots() -> Path:
    """Devolve o caminho absoluto do diretório de screenshots."""
    config = carregar_configuracao()
    data_dir = Path(config.get("data_directory", "data"))
    screenshots_dir = data_dir / "screenshots"
    return screenshots_dir


# ---------------------------------------------------------------------------
# API pública — Automação
# ---------------------------------------------------------------------------


def clicar_coordenada(
    x: int,
    y: int,
    duracao: float = 0.3,
    botao: str = "left",
    cliques: int = 1,
) -> bool:
    """
    Move o mouse até (x, y) com animação suave e clica.

    Args:
        x, y: Coordenadas de destino em pixels (absolutas).
        duracao: Tempo da animação de movimento (0 = instantâneo).
        botao: 'left', 'right' ou 'middle'.
        cliques: Número de cliques (2 = duplo-clique).

    Returns:
        True se o clique foi executado, False se foi abortado.
    """
    nome_acao = f"clicar em ({x}, {y})"
    _log(f"Iniciando: {nome_acao}")

    if not _verificar_antes_acao(nome_acao):
        return False

    try:
        pyautogui.moveTo(x, y, duration=duracao)

        if not _verificar_antes_acao(nome_acao):
            return False

        pyautogui.click(x, y, clicks=cliques, button=botao)
        _log(f"Concluído: {nome_acao}")
        return True

    except (pyautogui.FailSafeException, Exception) as exc:
        _log(f"Falha ao {nome_acao}: {exc}", "ERROR")
        return False


def digitar_texto(
    texto: str,
    intervalo: float = 0.05,
) -> bool:
    """
    Digita um texto caractere por caractere, verificando a trava de
    emergência entre cada tecla.

    Args:
        texto: String a ser digitada.
        intervalo: Pausa entre teclas (segundos). 0.05 é seguro e natural.

    Returns:
        True se o texto foi digitado completamente, False se foi abortado.
    """
    nome_acao = f"digitar {len(texto)} caractere(s)"
    _log(f"Iniciando: {nome_acao}")

    if not _verificar_antes_acao(nome_acao):
        return False

    digitados = 0
    try:
        for char in texto:
            # Verifica trava a cada 5 caracteres (performance)
            if digitados % 5 == 0:
                if not _verificar_antes_acao(nome_acao):
                    _log(f"Digitados {digitados}/{len(texto)} antes do aborto.", "WARNING")
                    return False

            # Trata caracteres especiais que o pyautogui.write pode errar
            if char == "\n":
                pyautogui.press("enter")
            elif char == "\t":
                pyautogui.press("tab")
            else:
                pyautogui.write(char, interval=intervalo)

            digitados += 1
            time.sleep(intervalo * 0.5)  # micro-pausa extra

        _log(f"Concluído: {nome_acao}")
        return True

    except (pyautogui.FailSafeException, Exception) as exc:
        _log(f"Falha ao digitar (posição {digitados}): {exc}", "ERROR")
        return False


def abrir_aplicativo(comando_ou_caminho: str) -> bool:
    """
    Abre um programa ou aplicativo usando subprocess.Popen.

    Aceita tanto caminhos absolutos (ex: 'C:\\Windows\\notepad.exe')
    quanto comandos do PATH (ex: 'notepad', 'calc').

    No Windows, tenta também via 'start' caso o Popen direto falhe.

    Args:
        comando_ou_caminho: Programa a ser aberto.

    Returns:
        True se o processo foi iniciado, False caso contrário.
    """
    nome_acao = f"abrir '{comando_ou_caminho}'"
    _log(f"Iniciando: {nome_acao}")

    if not _verificar_antes_acao(nome_acao):
        return False

    try:
        # Tenta abrir diretamente
        subprocess.Popen(
            comando_ou_caminho,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _log(f"Aplicativo iniciado: {comando_ou_caminho}")
        return True

    except FileNotFoundError:
        # Fallback: tenta com 'start' (Windows)
        _log("Popen direto falhou, tentando via 'start'...", "DEBUG")
        try:
            subprocess.Popen(
                f'start "" "{comando_ou_caminho}"',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _log(f"Aplicativo iniciado (via start): {comando_ou_caminho}")
            return True
        except Exception as exc2:
            _log(f"Falha ao abrir '{comando_ou_caminho}': {exc2}", "ERROR")
            return False

    except Exception as exc:
        _log(f"Falha ao abrir '{comando_ou_caminho}': {exc}", "ERROR")
        return False


def executar_comando_cmd(
    comando: str,
    timeout: int = 30,
    shell: bool = True,
    confirmation_callback: Optional[Callable[[str, str], bool]] = None,
    dry_run: bool = False,
) -> Tuple[bool, str, str]:
    """
    Executa um comando no terminal e retorna stdout, stderr.

    Args:
        comando: Comando a ser executado.
        timeout: Tempo máximo de espera em segundos.
        shell: Se True, passa pela shell do sistema.
        confirmation_callback: Se fornecido, chamado para comandos perigosos
            com a assinatura callback(mensagem, nivel) -> bool.
            Retorna True se o usuário confirmou.
        dry_run: Se True, apenas simula (não executa de fato).

    Returns:
        Tupla (sucesso: bool, stdout: str, stderr: str).
    """
    nome_acao = f"executar '{comando[:60]}{'...' if len(comando) > 60 else ''}'"
    _log(f"Iniciando: {nome_acao}")

    if not _verificar_antes_acao(nome_acao):
        return False, "", "Cancelado pelo usuário (kill-switch)."

    # ── Verificação de segurança ──
    if security is not None:
        precisa, nivel, msg = security.requires_confirmation(comando)
        if precisa:
            _log(f"Comando requer confirmação [{nivel}]: {comando[:80]}", "WARNING")
            if confirmation_callback is not None:
                if not confirmation_callback(msg, nivel):
                    _log("Comando cancelado pelo usuário (security check).", "WARNING")
                    return False, "", "Cancelado pelo usuário (confirmação de segurança)."
            else:
                _log(
                    f"Comando [{nivel}] BLOQUEADO — sem callback de confirmação.",
                    "WARNING",
                )
                return False, "", (
                    f"Comando bloqueado por segurança [{nivel}]. "
                    f"Confirmação do usuário necessária."
                )

    # ── Modo Dry-Run ──
    if dry_run:
        _log(f"[DRY-RUN] Simulação: '{comando[:80]}'", "INFO")
        return True, f"[DRY-RUN] Comando simulado: {comando}", ""

    try:
        resultado = subprocess.run(
            comando,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="cp850",       # Terminal Windows (pt-BR)
            errors="replace",        # Não quebra com caracteres inválidos
        )

        stdout = resultado.stdout.strip()
        stderr = resultado.stderr.strip()

        if resultado.returncode == 0:
            _log(f"Comando concluído (rc=0, {len(stdout)} bytes stdout)", "INFO")
            return True, stdout, stderr
        else:
            _log(
                f"Comando falhou (rc={resultado.returncode}): {stderr[:120]}",
                "WARNING",
            )
            return False, stdout, stderr

    except subprocess.TimeoutExpired:
        _log(f"Timeout ({timeout}s) ao executar comando.", "ERROR")
        return False, "", f"Timeout após {timeout} segundos."
    except FileNotFoundError as exc:
        _log(f"Comando não encontrado: {exc}", "ERROR")
        return False, "", f"Comando não encontrado: {exc}"
    except Exception as exc:
        _log(f"Erro inesperado: {exc}", "ERROR")
        return False, "", str(exc)


def tirar_screenshot(caminho_destino: Optional[str] = None) -> Tuple[bool, str]:
    """
    Captura a tela atual e salva em arquivo PNG.

    Args:
        caminho_destino: Caminho completo do arquivo .png.
            Se None, gera um nome automático com timestamp em
            <data_directory>/screenshots/.

    Returns:
        Tupla (sucesso: bool, caminho_absoluto: str).
        caminho_absoluto contém o path do arquivo salvo ou mensagem de erro.
    """
    if not _verificar_antes_acao("screenshot"):
        return False, "Cancelado pelo kill-switch."

    # Resolve caminho de destino
    if caminho_destino is None:
        screenshots_dir = _resolver_diretorio_screenshots()
        try:
            screenshots_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _log(f"Falha ao criar diretório de screenshots: {exc}", "ERROR")
            return False, str(exc)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho_destino = str(screenshots_dir / f"screenshot_{timestamp}.png")
    else:
        # Garante extensão .png
        if not caminho_destino.lower().endswith(".png"):
            caminho_destino += ".png"

    _log(f"Capturando tela -> {caminho_destino}")

    try:
        screenshot = pyautogui.screenshot()
        screenshot.save(caminho_destino)
        tamanho_kb = os.path.getsize(caminho_destino) // 1024
        _log(f"Screenshot salvo ({tamanho_kb} KB): {caminho_destino}")
        return True, os.path.abspath(caminho_destino)

    except pyautogui.FailSafeException:
        _log("Screenshot abortado pelo failsafe do pyautogui.", "WARNING")
        return False, "Failsafe do pyautogui acionado."
    except Exception as exc:
        _log(f"Falha ao capturar screenshot: {exc}", "ERROR")
        return False, str(exc)


# ---------------------------------------------------------------------------
# Teste seguro (sem ações invasivas)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S — Teste do PC Controller")
    print("=" * 60)

    # Garante ambiente
    validar_e_preparar_ambiente()

    # --------------------------------------------------
    # Teste 1: Screenshot (sempre seguro)
    # --------------------------------------------------
    print("\n[1] Testando tirar_screenshot()...")
    ok, caminho = tirar_screenshot()
    if ok:
        print(f"    Screenshot salvo em: {caminho}")
    else:
        print(f"    Falha: {caminho}")

    # --------------------------------------------------
    # Teste 2: Comando seguro (echo)
    # --------------------------------------------------
    print("\n[2] Testando executar_comando_cmd('echo Hello from JARVIS')...")
    sucesso, stdout, stderr = executar_comando_cmd("echo Hello from JARVIS")
    if sucesso:
        print(f"    stdout: {stdout}")
    else:
        print(f"    stderr: {stderr}")

    # --------------------------------------------------
    # Teste 3: Comando que lista diretório
    # --------------------------------------------------
    print("\n[3] Testando executar_comando_cmd('dir /B')...")
    sucesso, stdout, stderr = executar_comando_cmd("dir /B")
    if sucesso:
        linhas = stdout.splitlines()
        print(f"    {len(linhas)} itens no diretório atual:")
        for linha in linhas[:10]:
            print(f"      - {linha}")
        if len(linhas) > 10:
            print(f"      ... e mais {len(linhas) - 10} itens.")
    else:
        print(f"    Erro: {stderr}")

    # --------------------------------------------------
    # Teste 4: Verificação de funções de mouse/teclado
    # (apenas confirma existência, sem executar)
    # --------------------------------------------------
    print("\n[4] Funções de mouse/teclado disponíveis (não executadas):")
    print(f"    clicar_coordenada(x, y)  -- {clicar_coordenada}")
    print(f"    digitar_texto(texto)      -- {digitar_texto}")
    print(f"    abrir_aplicativo(app)     -- {abrir_aplicativo}")

    print("\n[PC-CTRL] Teste concluído.")
