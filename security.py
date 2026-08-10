"""
security.py — Módulo de Segurança para J.A.R.V.I.S. v3.0

Classifica comandos por nível de risco e fornece mecanismos de
confirmação para ações potencialmente perigosas.

Níveis de risco:
  - safe: comandos de leitura/informação
  - dangerous_modify: comandos que modificam o sistema
  - destructive: comandos que podem causar danos irreversíveis
"""

import re
from typing import Literal

RiskLevel = Literal["safe", "dangerous_modify", "destructive"]

# ═══════════════════════════════════════════════════════════════════════════
# PADRÕES DE COMANDOS PERIGOSOS
# ═══════════════════════════════════════════════════════════════════════════

DESTRUCTIVE_PATTERNS: list[str] = [
    # Destruição de disco/partição
    r"\bformat\b", r"\bfdisk\b", r"\bdiskpart\b.*\bclean\b",
    r"\bdd\b.*\bif=\b", r"\bdd\b.*\bof=\b",
    # Remoção recursiva
    r"\brm\s+-rf\b", r"\brmdir\s+/[sS]\b", r"\bdel\s+/[fF].*/[sS]\b",
    r"\bRemove-Item\b.*\b-Recurse\b.*\b-Force\b",
    # Destruição de sistema
    r"\bdel\s+%systemroot%", r"\brmdir\s+%systemroot%",
    r"\bdel\s+C:\\\\Windows", r"\bRemove-Item\s+C:\\\\Windows",
    # Registro destrutivo
    r"\breg\s+delete\b.*\bHKLM\\\\SOFTWARE\\\\Microsoft\\\\Windows\\\\CurrentVersion",
    r"\breg\s+delete\b.*\bHKLM\\\\SYSTEM",
    # Bootloader
    r"\bbcdedit\b.*\b/delete\b", r"\bbootrec\b.*\b/fixmbr\b",
    # Rede destrutiva
    r"\bnetsh\s+firewall\s+set\s+opmode\s+disable\b",
    r"\bnetsh\s+int\s+ip\s+reset\b",
    # SQL Injection / DROP
    r"\bDROP\s+(TABLE|DATABASE)\b", r"\bTRUNCATE\s+TABLE\b",
]

DANGEROUS_MODIFY_PATTERNS: list[str] = [
    # Modificação de registro
    r"\breg\s+add\b", r"\breg\s+delete\b",
    # Serviços do sistema
    r"\bsc\s+stop\b", r"\bsc\s+delete\b", r"\bsc\s+config\b",
    r"\bStop-Service\b", r"\bDisable-Service\b",
    # Processos do sistema
    r"\btaskkill\b.*\b/f\b",
    r"\bStop-Process\b.*\b-Force\b",
    # Instalação/desinstalação
    r"\bwinget\s+install\b", r"\bwinget\s+uninstall\b",
    r"\bchoco\s+install\b", r"\bchoco\s+uninstall\b",
    r"\bnpm\s+(install|uninstall)\s+-g\b",
    r"\bpip\s+(install|uninstall)\b",
    # Políticas de grupo
    r"\bgpupdate\b", r"\bgpresult\b",
    # Limpeza de disco
    r"\bcleanmgr\b", r"\bdiskpart\b",
    # Alteração de senha
    r"\bnet\s+user\b.*\b/add\b",
    r"\bnet\s+localgroup\s+administrators\b",
    # Firewall
    r"\bnetsh\s+firewall\b",
    r"\bNew-NetFirewallRule\b", r"\bSet-NetFirewallRule\b",
]

SAFE_PREFIXES = [
    # Comandos de leitura/diagnóstico
    r"^\s*echo\b", r"^\s*dir\b", r"^\s*ls\b", r"^\s*type\b",
    r"^\s*cat\b", r"^\s*whoami\b", r"^\s*hostname\b",
    r"^\s*date\b", r"^\s*time\b", r"^\s*ver\b",
    r"^\s*ping\b", r"^\s*nslookup\b", r"^\s*tracert\b",
    r"^\s*ipconfig\b", r"^\s*netstat\b", r"^\s*route\s+print\b",
    r"^\s*tasklist\b", r"^\s*systeminfo\b",
    r"^\s*Get-Process\b", r"^\s*Get-Service\b",
    r"^\s*Get-EventLog\b", r"^\s*Get-WmiObject\b",
    r"^\s*python\b", r"^\s*node\b", r"^\s*npm\s+run\b",
    r"^\s*git\s+(status|log|diff|branch)\b",
    r"^\s*pip\s+(list|freeze|show)\b",
    r"^\s*where\b", r"^\s*which\b", r"^\s*set\b",
]


def classify_command(command: str) -> RiskLevel:
    """
    Classifica um comando por nível de risco.

    Args:
        command: String do comando a ser analisado.

    Returns:
        'safe', 'dangerous_modify', ou 'destructive'
    """
    cmd_normalized = command.strip()

    # 1. Verifica padrões destrutivos primeiro
    for pattern in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, cmd_normalized, re.IGNORECASE):
            return "destructive"

    # 2. Verifica padrões de modificação perigosa
    for pattern in DANGEROUS_MODIFY_PATTERNS:
        if re.search(pattern, cmd_normalized, re.IGNORECASE):
            return "dangerous_modify"

    # 3. Verifica prefixos seguros
    for pattern in SAFE_PREFIXES:
        if re.search(pattern, cmd_normalized, re.IGNORECASE):
            return "safe"

    # 4. Default: se não sabemos, é potencialmente perigoso
    return "dangerous_modify"


def get_confirmation_message(command: str, level: RiskLevel) -> str:
    """
    Retorna uma mensagem de confirmação apropriada para o nível de risco.

    Args:
        command: O comando a ser executado.
        level: Nível de risco classificado.

    Returns:
        String HTML formatada para exibição no dialog.
    """
    cmd_short = command[:120] + ("..." if len(command) > 120 else "")

    if level == "destructive":
        return (
            f"<b>⚠ PERIGO — COMANDO DESTRUTIVO</b><br><br>"
            f"O comando a seguir pode causar <b>danos irreversíveis</b> "
            f"ao sistema:<br><br>"
            f"<code>{cmd_short}</code><br><br>"
            f"<b>Tem certeza ABSOLUTA que deseja executar?</b>"
        )
    elif level == "dangerous_modify":
        return (
            f"<b>⚠ ATENÇÃO — COMANDO DE MODIFICAÇÃO</b><br><br>"
            f"Este comando irá <b>modificar</b> o sistema:<br><br>"
            f"<code>{cmd_short}</code><br><br>"
            f"<b>Deseja prosseguir?</b>"
        )
    else:
        return (
            f"<b>Confirmar execução:</b><br><br>"
            f"<code>{cmd_short}</code>"
        )


def requires_confirmation(command: str) -> tuple[bool, RiskLevel, str]:
    """
    Verifica se um comando requer confirmação do usuário.

    Returns:
        Tupla (requires: bool, level: RiskLevel, message: str)
    """
    level = classify_command(command)
    if level == "safe":
        return False, level, ""
    return True, level, get_confirmation_message(command, level)
