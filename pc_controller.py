"""
pc_controller.py — Controle e Automação do Computador (J.A.R.V.I.S.)

Fornece funções de automação de mouse, teclado, execução de comandos,
abertura de aplicativos e captura de tela.

Toda ação perigosa (clique, digitação) é protegida pela trava de emergência
do kill_switch.py — a verificação ocorre ANTES e DURANTE cada operação.
"""

import ast
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import datetime
import webbrowser
from pathlib import Path
from typing import Optional, Tuple, Callable

import pyautogui

from config_manager import (
    carregar_configuracao,
    validar_e_preparar_ambiente,
    registrar_evento_telemetria,
    salvar_configuracao,
    expurgar_cache,
)
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


# ---------------------------------------------------------------------------
# Comandos de diagnóstico / leitura local liberados por padrão
# ---------------------------------------------------------------------------
# Estes comandos são SOMENTE de leitura e diagnóstico local — não alteram o
# estado do sistema. Por isso são executados na categoria "falar/executar"
# mesmo quando nenhum `confirmation_callback` é fornecido.
_COMANDOS_DIAGNOSTICO_SEGUROS: tuple[str, ...] = (
    r"^\s*nmap\b",
    r"^\s*arp\b",
    r"^\s*ping\b",
    r"^\s*ipconfig\b",
    r"^\s*netstat\b",
    r"^\s*nslookup\b",
    r"^\s*tracert\b",
    r"^\s*getmac\b",
    r"^\s*route\s+print\b",
    r"^\s*systeminfo\b",
    r"^\s*tasklist\b",
)


def _eh_diagnostico_seguro(comando: str) -> bool:
    """Indica se o comando é de diagnóstico/leitura local (não requer confirmação)."""
    cmd = (comando or "").strip()
    return any(re.match(padrao, cmd, re.IGNORECASE) for padrao in _COMANDOS_DIAGNOSTICO_SEGUROS)


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


# ---------------------------------------------------------------------------
# Helpers de URL (abrir no navegador padrão)
# ---------------------------------------------------------------------------

_DOMINIOS_COMUNS = re.compile(
    r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?"
    r"(\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)+$"
)
_EXTENSOES_EXECUTAVEIS = {
    ".exe", ".bat", ".cmd", ".msi", ".py", ".lnk", ".jar", ".ps1", ".vbs",
}


def _parece_url(valor: str) -> bool:
    """Indica se o valor parece uma URL/domínio (não um programa)."""
    v = (valor or "").strip()
    low = v.lower()
    if low.startswith(("http://", "https://", "www.")):
        return True
    if " " in v or "/" in v or "\\" in v:
        return False
    if os.path.splitext(v)[1].lower() in _EXTENSOES_EXECUTAVEIS:
        return False
    return bool(_DOMINIOS_COMUNS.match(v))


def _abrir_url(url: str) -> bool:
    """Abre uma URL no navegador padrão."""
    url = (url or "").strip()
    if not url:
        return False
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    try:
        webbrowser.open(url)
        _log(f"URL aberta no navegador: {url}")
        return True
    except Exception as exc:
        _log(f"Falha ao abrir URL '{url}': {exc}", "ERROR")
        return False


def _parse_lista_urls(valor: str) -> Optional[list[str]]:
    """Parse seguro de uma string de lista (ex.: \"['a.com', 'b.com']\")."""
    v = (valor or "").strip()
    if not (v.startswith("[") and v.endswith("]")):
        return None
    try:
        itens = ast.literal_eval(v)
    except (ValueError, SyntaxError):
        itens = re.findall(r"[\"']([^\"']+)[\"']", v)
    if isinstance(itens, (list, tuple)):
        return [str(x).strip() for x in itens if str(x).strip()]
    return None


def abrir_aplicativo(comando_ou_caminho: str) -> bool:
    """
    Abre um programa, aplicativo ou URL.

    - URL (http://, https://, ou domínio tipo google.com) → navegador padrão.
    - String de lista (ex.: "['google.com', 'youtube.com']") → abre cada URL.
    - Caso contrário → programa via subprocess (com fallback 'start' no Windows).
    """
    nome_acao = f"abrir '{comando_ou_caminho}'"
    _log(f"Iniciando: {nome_acao}")

    if not _verificar_antes_acao(nome_acao):
        return False

    valor = (comando_ou_caminho or "").strip()
    if not valor:
        return False

    # ── URL única ──
    if _parece_url(valor):
        return _abrir_url(valor)

    # ── Lista de URLs (string estilo Python) ──
    lista = _parse_lista_urls(valor)
    if lista is not None:
        if not lista:
            return False
        return any(_abrir_url(u) for u in lista)

    # ── Programa / aplicativo ──
    try:
        subprocess.Popen(
            valor,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _log(f"Aplicativo iniciado: {valor}")
        return True

    except FileNotFoundError:
        _log("Popen direto falhou, tentando via 'start'...", "DEBUG")
        try:
            subprocess.Popen(
                f'start "" "{valor}"',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _log(f"Aplicativo iniciado (via start): {valor}")
            return True
        except Exception as exc2:
            _log(f"Falha ao abrir '{valor}': {exc2}", "ERROR")
            return False

    except Exception as exc:
        _log(f"Falha ao abrir '{valor}': {exc}", "ERROR")
        return False


def _registrar_falha_aprendizado(comando: str, stderr: str) -> None:
    """
    Registra uma falha de execução no sistema de memória de autocorreção.

    Best-effort: qualquer erro aqui é apenas logado, sem interromper o fluxo.
    """
    try:
        import brain
        brain.registrar_erro_aprendizado(comando, stderr)
    except Exception as exc:
        _log(f"Memória de erros indisponível: {exc}", "DEBUG")


# ---------------------------------------------------------------------------
# Helpers de rede (sub-rede local, placeholders e fallback nmap→arp)
# ---------------------------------------------------------------------------

_PLACEHOLDERS_REDE = (
    "<rede>", "<subrede>", "<seu_endereço_ip>", "<seu_endereco_ip>",
    "<ip_da_rede>", "<ip>", "<alvo>", "<target>",
)


def _detectar_subrede_local() -> str:
    """Detecta a sub-rede local no formato CIDR (ex.: 192.168.1.0/24)."""
    ip = ""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        ip = ""
    if not ip:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except OSError:
            ip = ""
    octetos = (ip or "").split(".")
    if len(octetos) == 4 and not ip.startswith("127."):
        return f"{octetos[0]}.{octetos[1]}.{octetos[2]}.0/24"
    return "192.168.1.0/24"


def _substituir_placeholders_rede(comando: str) -> str:
    """Substitui placeholders como '<rede>' pela sub-rede local detectada."""
    if "<" not in comando:
        return comando
    subrede = _detectar_subrede_local()
    resultado = comando
    for ph in _PLACEHOLDERS_REDE:
        resultado = re.sub(re.escape(ph), subrede, resultado, flags=re.IGNORECASE)
    return resultado


def _eh_nmap(comando: str) -> bool:
    cmd = (comando or "").strip().lower()
    return cmd == "nmap" or cmd.startswith("nmap ")


def _comando_nao_encontrado(stderr: str) -> bool:
    s = (stderr or "").lower()
    return any(t in s for t in (
        "not recognized", "não é reconhecido", "nao e reconhecido",
        "not found", "command not found", "no such file",
    ))


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
    # Resolve placeholders de rede (ex.: '<rede>' → 192.168.1.0/24).
    comando = _substituir_placeholders_rede(comando)

    nome_acao = f"executar '{comando[:60]}{'...' if len(comando) > 60 else ''}'"
    _log(f"Iniciando: {nome_acao}")
    registrar_evento_telemetria("comando")

    if not _verificar_antes_acao(nome_acao):
        return False, "", "Cancelado pelo usuário (kill-switch)."

    # ── Verificação de segurança ──
    # Comandos de diagnóstico/leitura local são liberados por padrão e NÃO
    # exigem callback de confirmação, mesmo que o `security` os marcasse.
    if security is not None and not _eh_diagnostico_seguro(comando):
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
            # Fallback nativo: nmap indisponível → usa 'arp -a'.
            if _eh_nmap(comando) and _comando_nao_encontrado(stderr or stdout):
                _log("nmap indisponível — executando fallback nativo 'arp -a'.", "WARNING")
                return executar_comando_cmd(
                    "arp -a",
                    timeout=timeout,
                    shell=shell,
                    confirmation_callback=confirmation_callback,
                    dry_run=dry_run,
                )
            _log(
                f"Comando falhou (rc={resultado.returncode}): {stderr[:120]}",
                "WARNING",
            )
            _registrar_falha_aprendizado(comando, stderr)
            return False, stdout, stderr

    except subprocess.TimeoutExpired:
        _log(f"Timeout ({timeout}s) ao executar comando.", "ERROR")
        _registrar_falha_aprendizado(comando, f"Timeout após {timeout} segundos.")
        return False, "", f"Timeout após {timeout} segundos."
    except FileNotFoundError as exc:
        # Fallback nativo: nmap não encontrado → usa 'arp -a'.
        if _eh_nmap(comando):
            _log("nmap indisponível — executando fallback nativo 'arp -a'.", "WARNING")
            return executar_comando_cmd(
                "arp -a",
                timeout=timeout,
                shell=shell,
                confirmation_callback=confirmation_callback,
                dry_run=dry_run,
            )
        _log(f"Comando não encontrado: {exc}", "ERROR")
        _registrar_falha_aprendizado(comando, str(exc))
        return False, "", f"Comando não encontrado: {exc}"
    except Exception as exc:
        _log(f"Erro inesperado: {exc}", "ERROR")
        _registrar_falha_aprendizado(comando, str(exc))
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
# Comandos de automação (Command Palette)
# ---------------------------------------------------------------------------


def _diretorio_temp() -> Path:
    """Devolve o diretório temporário data/temp (criando se necessário)."""
    config = carregar_configuracao()
    data_dir = Path(config.get("data_directory", "data"))
    temp_dir = data_dir / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def git_sync() -> Tuple[bool, str]:
    """
    Fluxo /git-sync: `git add .`, gera mensagem de commit via IA e `git push`.
    Retorna (sucesso, resumo).
    """
    import brain

    ok, out, err = executar_comando_cmd("git add .", timeout=60)
    if not ok:
        return False, f"git add . falhou: {err or out}"

    _, diff_stat, _ = executar_comando_cmd("git diff --cached --stat", timeout=30)
    _, status, _ = executar_comando_cmd("git status --short", timeout=30)

    if not diff_stat.strip() and not status.strip():
        return True, "Nada para commitar — árvore de trabalho limpa."

    try:
        resultado = brain.processar_prompt(
            "Gere APENAS a mensagem de commit (uma linha, estilo conventional "
            f"commits) para as seguintes mudanças:\n\nSTATUS:\n{status}\n\nSTAT:\n{diff_stat}"
        )
        mensagem = (resultado.get("resposta_voz") or "").strip()
    except Exception as exc:
        _log(f"IA indisponível para mensagem de commit: {exc}", "WARNING")
        mensagem = ""
    if not mensagem:
        mensagem = "chore: atualização automática (J.A.R.V.I.S /git-sync)"

    # Grava a mensagem em arquivo para evitar problemas de quoting no shell.
    tmp_msg = _diretorio_temp() / "commit_msg.txt"
    try:
        tmp_msg.write_text(mensagem, encoding="utf-8")
    except OSError as exc:
        return False, f"Falha ao gravar mensagem de commit: {exc}"

    ok, out, err = executar_comando_cmd(f'git commit -F "{tmp_msg}"', timeout=60)
    if not ok:
        return False, f"git commit falhou: {err or out}"

    ok, out, err = executar_comando_cmd("git push", timeout=120)
    if not ok:
        return False, f"Commit feito, mas push falhou: {err or out}"

    registrar_evento_telemetria("commit")
    return True, f"Git-sync concluído.\n\nCommit: {mensagem}\n\nPush:\n{out or '(sem saída)'}"


def limpar_temporarios() -> Tuple[bool, str]:
    """
    Fluxo /cleanup: limpa arquivos temporários de data/downloads e caches
    __pycache__ do projeto. Retorna (sucesso, resumo).
    """
    config = carregar_configuracao()
    data_dir = Path(config.get("data_directory", "data"))
    downloads = data_dir / "downloads"

    removidos = 0
    erros: list[str] = []
    if downloads.is_dir():
        for item in downloads.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                removidos += 1
            except OSError as exc:
                erros.append(str(exc))

    pycache_limpos = 0
    raiz = Path(__file__).resolve().parent
    for p in raiz.rglob("__pycache__"):
        try:
            shutil.rmtree(p)
            pycache_limpos += 1
        except OSError:
            pass

    resumo = (
        f"Limpeza concluída: {removidos} item(ns) removidos de downloads, "
        f"{pycache_limpos} cache(s) __pycache__ limpo(s)."
    )
    if erros:
        resumo += f"\n⚠ {len(erros)} erro(s) encontrado(s)."
    return True, resumo


def diagnostico_rede() -> Tuple[bool, str]:
    """
    Fluxo /net-check: ping, latência e portas abertas. Retorna (sucesso, resumo).
    """
    secoes: list[str] = []

    ok, out, err = executar_comando_cmd("ping -n 3 8.8.8.8", timeout=30)
    secoes.append(f"[PING / LATÊNCIA — 8.8.8.8]\n{out or err}")

    ok, out, err = executar_comando_cmd("netstat -ano | findstr LISTENING", timeout=30)
    secoes.append(f"[PORTAS EM ESCUTA]\n{out.strip() if out.strip() else '(nenhuma)'}")

    return True, "\n\n".join(secoes)


def _extrair_codigo_resposta(resultado: dict) -> str:
    """Extrai o código corrigido da resposta JSON do brain."""
    codigo = ""
    if isinstance(resultado, dict):
        params = resultado.get("parametros", {})
        if isinstance(params, dict):
            codigo = params.get("codigo", "") or ""
        if not codigo:
            codigo = resultado.get("resposta_voz", "") or ""
    codigo = re.sub(r"```[a-zA-Z0-9]*\n?", "", str(codigo))
    codigo = codigo.replace("```", "")
    return codigo.strip()


def autofix_codigo(codigo: str, max_tentativas: int = 3) -> Tuple[bool, str, str]:
    """
    Agente autônomo testador/corretor de código (/autofix).

    1. Salva o código em `data/temp/test_script.py`.
    2. Executa em subprocesso seguro com timeout.
    3. Se houver erro (Exit Code != 0), pede correção à IA e re-executa
       (até `max_tentativas` vezes).
    4. Retorna (sucesso, código_final, saída_final).
    """
    import brain

    caminho = _diretorio_temp() / "test_script.py"
    codigo_atual = codigo
    ultima_saida = ""

    for tentativa in range(1, max_tentativas + 1):
        try:
            caminho.write_text(codigo_atual, encoding="utf-8")
        except OSError as exc:
            return False, codigo_atual, f"Falha ao gravar script: {exc}"

        try:
            proc = subprocess.run(
                [sys.executable, str(caminho)],
                capture_output=True,
                text=True,
                timeout=60,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return False, codigo_atual, "Timeout (60s) ao executar o script."
        except Exception as exc:
            return False, codigo_atual, f"Falha ao executar o script: {exc}"

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        ultima_saida = (stdout + ("\n" + stderr if stderr else "")).strip()

        if proc.returncode == 0:
            return True, codigo_atual, ultima_saida

        # ── Auto-Dependency Manager ──
        # Detecta ModuleNotFoundError/ImportError, instala o pacote ausente
        # silenciosamente e re-executa o script sem gastar tentativa de IA.
        pacote = _extrair_pacote_ausente(stderr or stdout)
        if pacote:
            ok_inst, msg_inst = instalar_dependencia_ausente(pacote)
            if ok_inst:
                try:
                    proc2 = subprocess.run(
                        [sys.executable, str(caminho)],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        encoding="utf-8",
                        errors="replace",
                    )
                except Exception as exc:
                    proc2 = None
                    ultima_saida = f"{ultima_saida}\n[Auto-Dependency] Re-execução falhou: {exc}"

                if proc2 is not None:
                    saida2 = (proc2.stdout.strip() + ("\n" + proc2.stderr.strip() if proc2.stderr.strip() else "")).strip()
                    if proc2.returncode == 0:
                        return True, codigo_atual, (
                            f"[Auto-Dependency] '{pacote}' instalado e script "
                            f"re-executado com sucesso.\n{saida2}"
                        )
                    ultima_saida = saida2
            else:
                ultima_saida = f"{ultima_saida}\n[Auto-Dependency] {msg_inst}"

        if tentativa >= max_tentativas:
            return False, codigo_atual, (
                f"Falha persistente após {max_tentativas} tentativa(s).\n{ultima_saida}"
            )

        try:
            resultado = brain.processar_prompt(
                "O script Python abaixo falhou. Corrija o código e retorne a "
                "versão COMPLETA corrigida (somente o código, sem explicações):\n\n"
                f"ERRO:\n{stderr or stdout}\n\nCÓDIGO:\n{codigo_atual}"
            )
            codigo_corrigido = _extrair_codigo_resposta(resultado)
        except Exception as exc:
            return False, codigo_atual, f"Falha ao consultar a IA: {exc}"

        if not codigo_corrigido:
            return False, codigo_atual, f"Não foi possível extrair a correção.\n{ultima_saida}"

        codigo_atual = codigo_corrigido

    return False, codigo_atual, ultima_saida


def inspecionar_downloads() -> Tuple[bool, str]:
    """
    Fluxo /inspect: executa o Cyber Sandbox & Inspector sobre os scripts em
    `data/downloads/` e retorna o resultado formatado com selos de segurança.
    """
    try:
        import data_inspector
    except ImportError:
        return False, "Módulo data_inspector indisponível."

    resultados = data_inspector.inspecionar_pasta_downloads()
    if not resultados:
        return True, "Nenhum script (.ps1/.bat/.py/.exe) encontrado em data/downloads/."

    linhas: list[str] = []
    for r in resultados:
        nome = Path(r["arquivo"]).name
        if r.get("seguro"):
            linhas.append(f"[VERIFICADO - SEGURO] {nome}")
        else:
            linhas.append(f"[ALERTA DE RISCO] {nome}")
            for s in r.get("suspeitos", []):
                linhas.append(f"   • {s}")
    return True, "\n".join(linhas)


# ---------------------------------------------------------------------------
# SMART WORKSPACE MANAGER — Gerenciador de modos/perfis (/mode)
# ---------------------------------------------------------------------------

PERFIS_TRABALHO = ("dev", "focus", "gaming")

# Estado global do perfil ativo (consultável por outros módulos).
_modo_atual: str = "normal"


def modo_atual() -> str:
    """Devolve o perfil de trabalho atualmente ativo."""
    return _modo_atual


def _encontrar_vscode() -> Optional[str]:
    """Localiza o executável do VS Code, se instalado."""
    if shutil.which("code"):
        return "code"
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        candidato = os.path.join(local_app_data, "Programs", "Microsoft VS Code", "Code.exe")
        if os.path.isfile(candidato):
            return candidato
    return None


def _modo_dev() -> list[str]:
    """Ações do perfil dev: IDE + terminal + monitoramento de código."""
    acoes: list[str] = []
    raiz = str(Path(__file__).resolve().parent)

    ide = _encontrar_vscode()
    if ide:
        try:
            subprocess.Popen(
                [ide, raiz],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            acoes.append(f"IDE de desenvolvimento aberta no projeto: {raiz}")
        except Exception as exc:
            acoes.append(f"Falha ao abrir IDE: {exc}")
    else:
        acoes.append("VS Code não localizado — abra a IDE manualmente.")

    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "cmd"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        acoes.append("Terminal de suporte iniciado (cmd).")
    except Exception as exc:
        acoes.append(f"Falha ao iniciar terminal: {exc}")

    acoes.append("Monitoramento de código ativado (J.A.R.V.I.S. em modo dev).")
    return acoes


def _modo_focus() -> list[str]:
    """Ações do perfil focus: silencioso + minimizar + prioridade de processos."""
    acoes: list[str] = []

    try:
        subprocess.run(
            'powershell -NoProfile -Command '
            '"(New-Object -ComObject Shell.Application).MinimizeAll()"',
            shell=True, capture_output=True, text=True, timeout=20,
        )
        acoes.append("Janelas/abas não essenciais minimizadas.")
    except Exception as exc:
        acoes.append(f"Não foi possível minimizar janelas: {exc}")

    try:
        executar_comando_cmd(
            "wmic process where \"name='python.exe'\" CALL setpriority 128",
            timeout=20,
        )
        acoes.append("Prioridade dos processos Python elevada (focus).")
    except Exception as exc:
        acoes.append(f"Falha ao ajustar prioridade: {exc}")

    acoes.append("Modo silencioso ativado.")
    return acoes


def _modo_gaming() -> list[str]:
    """Ações do perfil gaming: reduz RAM/VRAM, suspende LLM pesada e limpa cache."""
    acoes: list[str] = []

    try:
        salvar_configuracao({"cpu_threads": 1, "gpu_layers": 0, "max_ram_gb": 4})
        acoes.append("Recursos da LLM reduzidos ao mínimo (cpu_threads=1, gpu_layers=0).")
    except Exception as exc:
        acoes.append(f"Falha ao reduzir recursos: {exc}")

    try:
        ok_cache, resumo_cache = expurgar_cache()
        acoes.append(resumo_cache if ok_cache else f"Cache: {resumo_cache}")
    except Exception as exc:
        acoes.append(f"Falha ao limpar cache: {exc}")

    acoes.append("Threads pesadas da LLM suspensas (modo gaming).")
    return acoes


def aplicar_modo_perfil(perfil: str) -> Tuple[bool, str]:
    """
    Aplica um perfil de trabalho via `/mode <perfil>`.

    Perfis:
      - dev:     abre a IDE no projeto, inicia terminal e ativa monitoramento.
      - focus:   modo silencioso, minimiza janelas e ajusta prioridades.
      - gaming:  reduz RAM/VRAM da LLM ao mínimo e limpa cache.

    Retorna (sucesso, resumo).
    """
    global _modo_atual
    perfil = (perfil or "").strip().lower()

    if perfil not in PERFIS_TRABALHO:
        return False, (
            f"Perfil desconhecido: '{perfil}'. "
            f"Perfis disponíveis: {', '.join(PERFIS_TRABALHO)}."
        )

    _log(f"Aplicando perfil de trabalho: {perfil}")
    if perfil == "dev":
        acoes = _modo_dev()
    elif perfil == "focus":
        acoes = _modo_focus()
    else:
        acoes = _modo_gaming()

    _modo_atual = perfil
    registrar_evento_telemetria("comando")
    corpo = "\n".join(f"  • {a}" for a in acoes)
    return True, f"PERFIL '{perfil.upper()}' ATIVADO\n{corpo}"


# ---------------------------------------------------------------------------
# AUTO-DEPENDENCY MANAGER — Captura de falhas de ambiente
# ---------------------------------------------------------------------------

_PADROES_PACOTE_AUSENTE = (
    re.compile(r"No module named ['\"]([^'\"]+)['\"]"),
    re.compile(r"ModuleNotFoundError:\s*No module named ['\"]([^'\"]+)['\"]"),
    re.compile(r"ImportError:\s*cannot import name '[^']+' from ['\"]([^'\"]+)['\"]"),
    re.compile(r"ImportError:\s*No module named ['\"]([^'\"]+)['\"]"),
)


def _extrair_pacote_ausente(stderr: str) -> Optional[str]:
    """
    Extrai o nome do pacote ausente a partir de um stderr contendo
    `ModuleNotFoundError` ou `ImportError`. Para imports aninhados (ex: `a.b`),
    retorna apenas o módulo de topo (`a`), que é o alvo correto do `pip install`.
    """
    texto = stderr or ""
    for padrao in _PADROES_PACOTE_AUSENTE:
        m = padrao.search(texto)
        if m:
            pacote = m.group(1).strip().split(".")[0]
            if pacote and not pacote.startswith(("__", "self")):
                return pacote
    return None


def instalar_dependencia_ausente(pacote: str) -> Tuple[bool, str]:
    """Instala silenciosamente um pacote via `pip install` (subprocesso)."""
    if not pacote:
        return False, "Nenhum pacote especificado para instalação."
    _log(f"Instalando dependência ausente em background: {pacote}")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", pacote],
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return False, f"Timeout ao instalar '{pacote}'."
    except Exception as exc:
        return False, f"Falha ao instalar '{pacote}': {exc}"

    if proc.returncode == 0:
        _log(f"Pacote '{pacote}' instalado com sucesso.")
        return True, f"Pacote '{pacote}' instalado com sucesso."
    return False, f"Falha ao instalar '{pacote}': {proc.stderr.strip()[:300]}"


def capturar_falha_ambiente(stderr: str) -> Optional[str]:
    """
    API pública do capturador de falhas de ambiente: devolve o pacote ausente
    detectado no stderr (ou None quando a falha não é de dependência).
    """
    return _extrair_pacote_ausente(stderr)


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
