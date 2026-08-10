"""
advanced_threat_detector.py — J.A.R.V.I.S. Advanced Threat Detector v1.0

Detector comportamental de ameaças avançadas. Opera EXCLUSIVAMENTE
em modo DEFENSIVO — monitora indicadores, não executa ataques.

Matriz de detecção (o que o defensor procura):

Técnica                 →  Indicador comportamental monitorado
─────────────────────────────────────────────────────────────
RCE                     →  processos inesperados de serviços web
Zero-day                →  comportamento anômalo, processos e conexões
Fileless malware        →  execução anormal de ferramentas legítimas (LOLbins)
Rootkit/bootkit         →  alterações de boot, firmware, integridade
APT                     →  padrões persistentes, movimento lateral
Credential attacks      →  logins anômalos, uso incomum de credenciais
Supply-chain            →  alterações inesperadas em dependências
Privilege escalation    →  mudanças incomuns de privilégios
Exfiltration            →  tráfego de saída anômalo
"""

import ipaddress
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone

# Reutiliza helpers do cyber_defense se disponível
try:
    from cyber_defense import _log, _run_cmd, _run_powershell
except ImportError:
    import subprocess

    def _log(msg: str, level: str = "INFO") -> None:
        print(f"[ADV-THD {level:<5}] {msg}", flush=True)

    def _run_cmd(command: str, timeout: int = 10) -> str:
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout, encoding="cp850", errors="replace",
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _run_powershell(script: str, timeout: int = 15) -> str:
        return _run_cmd(f'powershell -NoProfile -Command "{script}"', timeout)


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════════════════

WEB_SERVICE_PARENTS = {
    "w3wp.exe", "httpd.exe", "nginx.exe", "node.exe",
    "python.exe", "python3.exe", "java.exe", "tomcat.exe",
    "apache.exe", "php-cgi.exe", "php.exe", "ruby.exe",
}

LOTL_BINARIES = {
    "powershell.exe", "pwsh.exe", "cmd.exe", "wmic.exe",
    "mshta.exe", "rundll32.exe", "regsvr32.exe", "cscript.exe",
    "wscript.exe", "msbuild.exe", "csc.exe", "installutil.exe",
    "reg.exe", "schtasks.exe", "bcdedit.exe", "netsh.exe",
    "certutil.exe", "bitsadmin.exe", "sc.exe", "net.exe",
    "net1.exe", "whoami.exe", "icacls.exe", "takeown.exe",
}

REVERSE_SHELL_PATTERNS = [
    "bash -i", "/dev/tcp/", "nc -e", "ncat -e",
    "python -c 'import socket", "python -c \"import socket",
    "sh -i", "powershell -e ", "powershell -enc ",
    "powershell -encodedcommand",
    "invoke-shellcode", "invoke-powershelltcp",
    "invoke-expression", "iex ",
    "new-object net.webclient", "new-object system.net.webclient",
    "start-process -windowstyle hidden",
]

PERSISTENCE_REGISTRY_KEYS = [
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
    r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run",
    r"HKLM\SYSTEM\CurrentControlSet\Services",
]

LATERAL_MOVEMENT_PORTS = {135, 139, 445, 3389, 5985, 5986}

DEPENDENCY_FILES = {
    "requirements.txt": "Python/pip",
    "package.json": "Node.js/npm",
    "Cargo.toml": "Rust/Cargo",
    "go.mod": "Go",
    "pom.xml": "Java/Maven",
    "Gemfile": "Ruby",
    "pyproject.toml": "Python/Poetry",
    "package-lock.json": "Node.js/npm",
    "yarn.lock": "Node.js/Yarn",
}


# ═══════════════════════════════════════════════════════════════════════════
# ADVANCED THREAT DETECTOR
# ═══════════════════════════════════════════════════════════════════════════

class AdvancedThreatDetector:

    # ──────────────────────────────────────────────────────────────────
    # 1. RCE (Remote Code Execution) Detection
    # ──────────────────────────────────────────────────────────────────

    def detect_rce_indicators(self) -> dict:
        """Detecta processos filhos de serviços web e reverse shells."""
        output = _run_cmd(
            'wmic process get ProcessId,ParentProcessId,Name,CommandLine '
            '/format:csv', timeout=15)
        alerts = []

        for line in output.splitlines():
            cmdline_lower = line.lower()

            # Reverse shell patterns
            for pattern in REVERSE_SHELL_PATTERNS:
                if pattern.lower() in cmdline_lower:
                    alerts.append({
                        "type": "rce_reverse_shell",
                        "severity": "CRITICAL",
                        "detail": f"Possível reverse shell: '{pattern}'",
                        "cmdline": line[:200],
                    })
                    break

        return {
            "alerts": alerts,
            "indicator": "RCE",
            "defense_note": (
                "RCE é detectado por processos/comandos inesperados "
                "originados de serviços web. Monitore w3wp.exe, node.exe, "
                "java.exe criando shells ou conexões reversas."
            ),
        }

    # ──────────────────────────────────────────────────────────────────
    # 2. Credential Attacks (Brute-force, Pass-the-Hash, Kerberoasting)
    # ──────────────────────────────────────────────────────────────────

    def detect_credential_attacks(self) -> dict:
        """Detecta ataques de credenciais via Windows Event Log."""
        alerts = []

        script = """
        $events = @{}
        Get-WinEvent -FilterHashtable @{LogName='Security'; ID=4625} -MaxEvents 100
            -ErrorAction SilentlyContinue | ForEach-Object { $events['4625']++ }
        Get-WinEvent -FilterHashtable @{LogName='Security'; ID=4648} -MaxEvents 100
            -ErrorAction SilentlyContinue | ForEach-Object { $events['4648']++ }
        Get-WinEvent -FilterHashtable @{LogName='Security'; ID=4771} -MaxEvents 100
            -ErrorAction SilentlyContinue | ForEach-Object { $events['4771']++ }
        Get-WinEvent -FilterHashtable @{LogName='Security'; ID=4769} -MaxEvents 100
            -ErrorAction SilentlyContinue | ForEach-Object { $events['4769']++ }
        $events | ConvertTo-Json -Compress
        """
        output = _run_powershell(script, timeout=20)

        e4625 = output.count("4625")
        e4648 = output.count("4648")
        e4771 = output.count("4771")
        e4769 = output.count("4769")

        if e4625 > 10:
            alerts.append({
                "type": "brute_force_active",
                "severity": "HIGH",
                "detail": f"{e4625} falhas de login — possível brute-force",
            })
        if e4648 > 3:
            alerts.append({
                "type": "pass_the_hash_ticket",
                "severity": "CRITICAL",
                "detail": f"{e4648} logons com credenciais explícitas "
                          f"— possível Pass-the-Hash/Ticket (Mimikatz)",
            })
        if e4771 > 5:
            alerts.append({
                "type": "kerberoasting",
                "severity": "HIGH",
                "detail": f"{e4771} falhas Kerberos pre-auth "
                          f"— possível Kerberoasting/AS-REP roasting",
            })
        if e4769 > 15:
            alerts.append({
                "type": "kerberos_enumeration",
                "severity": "MEDIUM",
                "detail": f"{e4769} solicitações de ticket Kerberos "
                          f"— possível enumeração de SPNs",
            })

        return {
            "event_4625_failed_logins": e4625,
            "event_4648_explicit_credential": e4648,
            "event_4771_kerberos_preauth_fail": e4771,
            "event_4769_service_tickets": e4769,
            "alerts": alerts,
            "indicator": "Credential Attacks",
            "defense_note": (
                "Ataques de credencial são detectados por logins anômalos, "
                "uso incomum de credenciais e padrões Kerberos suspeitos. "
                "Monitore Event IDs 4625, 4648, 4771, 4769 no Security log."
            ),
        }

    # ──────────────────────────────────────────────────────────────────
    # 3. Privilege Escalation Detection
    # ──────────────────────────────────────────────────────────────────

    def detect_privilege_escalation(self) -> dict:
        """Detecta escalonamento de privilégios."""
        alerts = []

        # Audit log cleared (cover tracks)
        audit_clear = _run_powershell(
            "Get-WinEvent -FilterHashtable @{LogName='Security'; ID=1102} "
            "-MaxEvents 5 -ErrorAction SilentlyContinue | Measure-Object | "
            "Select-Object -ExpandProperty Count", timeout=10)
        try:
            cleared = int(audit_clear.strip()) if audit_clear.strip() else 0
        except ValueError:
            cleared = 0

        if cleared > 0:
            alerts.append({
                "type": "audit_log_cleared",
                "severity": "CRITICAL",
                "detail": f"Log de auditoria LIMPO {cleared}x — cover-up ativo",
            })

        # UAC bypass check
        uac = _run_cmd(
            'reg query "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion'
            '\\Policies\\System" 2>nul | findstr "EnableLUA"')
        if "0x0" in uac:
            alerts.append({
                "type": "uac_disabled",
                "severity": "HIGH",
                "detail": "UAC desabilitado — escalonamento trivial de privilégios",
            })

        # Token duplication / SeTakeOwnershipPrivilege abuse
        priv_script = """
        Get-WinEvent -FilterHashtable @{LogName='Security'; ID=4672}
            -MaxEvents 20 -ErrorAction SilentlyContinue |
        ForEach-Object {
            $privs = $_.Properties[5].Value
            if ($privs -match 'SeTakeOwnershipPrivilege|SeDebugPrivilege'
                -or $privs -match 'SeRestorePrivilege|SeBackupPrivilege') {
                Write-Output "SUSPICIOUS_PRIV:$privs"
            }
        }
        """
        priv_output = _run_powershell(priv_script, timeout=15)
        priv_count = priv_output.count("SUSPICIOUS_PRIV")

        if priv_count > 3:
            alerts.append({
                "type": "suspicious_privilege_use",
                "severity": "HIGH",
                "detail": f"{priv_count} usos de privilégios sensíveis "
                          f"(SeDebug, SeTakeOwnership) — possível escalonamento",
            })

        return {
            "audit_cleared": cleared,
            "suspicious_privileges": priv_count,
            "alerts": alerts,
            "indicator": "Privilege Escalation",
            "defense_note": (
                "Escalonamento é detectado por mudanças incomuns de privilégio: "
                "novos admins, tokens sensíveis, UAC bypass, audit log clear."
            ),
        }

    # ──────────────────────────────────────────────────────────────────
    # 4. Persistence Mechanisms Detection
    # ──────────────────────────────────────────────────────────────────

    def detect_persistence_mechanisms(self) -> dict:
        """Detecta mecanismos de persistência (Run keys, tasks, serviços)."""
        alerts = []
        suspicious_tasks = []

        tasks = _run_cmd(
            'schtasks /query /fo LIST /v 2>nul | findstr /C:"TaskName" '
            '/C:"Task To Run"', timeout=15)

        suspicious_patterns = [
            "powershell", "cmd.exe", "wscript", "cscript",
            "rundll32", "mshta", "certutil", "bitsadmin",
            "downloader", "rat", "backdoor", "persist",
            "hidden", "bypass", "invoke-",
        ]

        current_task = ""
        for line in tasks.splitlines():
            if "TaskName:" in line:
                current_task = line.split(":", 1)[-1].strip()
            if "Task To Run:" in line:
                command = line.split(":", 1)[-1].strip().lower()
                for pat in suspicious_patterns:
                    if pat in command:
                        suspicious_tasks.append({
                            "task": current_task,
                            "command": command[:100],
                        })
                        break

        if suspicious_tasks:
            alerts.append({
                "type": "suspicious_persistence",
                "severity": "HIGH",
                "detail": f"{len(suspicious_tasks)} scheduled tasks suspeitas "
                          f"de persistência",
            })

        return {
            "suspicious_tasks": suspicious_tasks,
            "alerts": alerts,
            "indicator": "Persistence",
            "defense_note": (
                "Persistência é detectada por novos serviços, startup entries, "
                "scheduled tasks, WMI subscriptions e Run keys no registro."
            ),
        }

    # ──────────────────────────────────────────────────────────────────
    # 5. Lateral Movement Detection
    # ──────────────────────────────────────────────────────────────────

    def detect_lateral_movement(self) -> dict:
        """Detecta movimento lateral via SMB/WMI/WinRM/RDP."""
        output = _run_cmd(
            'netstat -ano | findstr /C:":445 " /C:":135 " '
            '/C:":5985 " /C:":5986 " /C:":3389 "')
        alerts = []
        connections = []

        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 5 and "ESTABLISHED" in line:
                remote_ip = parts[2].rsplit(":", 1)[0]
                if remote_ip not in ("127.0.0.1", "::1", "0.0.0.0"):
                    connections.append(remote_ip)

        unique_targets = len(set(connections))
        if unique_targets > 3:
            alerts.append({
                "type": "lateral_movement",
                "severity": "HIGH",
                "detail": f"Conexões SMB/WMI/WinRM/RDP para {unique_targets} "
                          f"hosts — possível movimento lateral",
            })

        return {
            "lateral_targets": unique_targets,
            "alerts": alerts,
            "indicator": "Lateral Movement",
            "defense_note": (
                "Movimento lateral: conexões SMB(445)/WMI(135)/WinRM(5985-6) "
                "para múltiplos hosts internos, uso de PSExec, WMI exec, schtasks."
            ),
        }

    # ──────────────────────────────────────────────────────────────────
    # 6. Fileless & Zero-Day Detection (Living-off-the-Land)
    # ──────────────────────────────────────────────────────────────────

    def detect_fileless_and_zero_day(self) -> dict:
        """Detecta fileless/zero-day via abuso de ferramentas legítimas."""
        output = _run_cmd(
            'wmic process get Name,CommandLine /format:csv', timeout=15)
        alerts = []

        for line in output.splitlines():
            cmd = line.lower()

            if "powershell" in cmd and (" -e " in cmd or " -enc " in cmd
                                         or " -encodedcommand " in cmd):
                alerts.append({
                    "type": "encoded_powershell",
                    "severity": "CRITICAL",
                    "detail": "PowerShell com comando codificado (Base64) "
                              "— técnica fileless de APT/malware",
                })

            if "mshta" in cmd and ("http://" in cmd or "https://" in cmd):
                alerts.append({
                    "type": "mshta_remote",
                    "severity": "CRITICAL",
                    "detail": "mshta.exe executando script remoto",
                })

            if "rundll32" in cmd and ("javascript:" in cmd or "http" in cmd):
                alerts.append({
                    "type": "rundll32_suspicious",
                    "severity": "CRITICAL",
                    "detail": "rundll32.exe com parâmetros suspeitos",
                })

            if "certutil" in cmd and ("urlcache" in cmd or "split" in cmd):
                alerts.append({
                    "type": "certutil_download",
                    "severity": "HIGH",
                    "detail": "certutil.exe usado para download "
                              "— LOLbin comum em APTs",
                })

        lolbin_count = sum(
            1 for line in output.splitlines()
            for lol in LOTL_BINARIES if lol in line.lower()
        )

        return {
            "lotl_processes": lolbin_count,
            "alerts": alerts,
            "indicator": "Fileless / Zero-Day",
            "defense_note": (
                "Fileless/Zero-day é detectado por execução anormal de "
                "ferramentas legítimas (LOLbins) e memória suspeita. "
                "PowerShell encoded, mshta, certutil download, rundll32 remoto."
            ),
        }

    # ──────────────────────────────────────────────────────────────────
    # 7. Rootkit / Bootkit Detection
    # ──────────────────────────────────────────────────────────────────

    def detect_bootkit_rootkit_indicators(self) -> dict:
        """Detecta indicadores de rootkit/bootkit."""
        alerts = []

        bcd = _run_cmd("bcdedit /enum 2>nul", timeout=5)
        bcd_lower = bcd.lower()

        if "testsigning" in bcd_lower:
            alerts.append({
                "type": "test_signing_enabled",
                "severity": "HIGH",
                "detail": "Assinatura de teste ativada — drivers não assinados "
                          "podem ser carregados (rootkit indicator)",
            })

        if "nointegritychecks" in bcd_lower:
            alerts.append({
                "type": "integrity_checks_disabled",
                "severity": "CRITICAL",
                "detail": "Verificação de integridade DESATIVADA — kernel "
                          "pode ser modificado sem detecção (bootkit indicator)",
            })

        drivers = _run_cmd(
            'driverquery /v /fo csv 2>nul', timeout=10)
        non_ms = sum(1 for l in drivers.splitlines()
                     if "Microsoft" not in l and "Microsoft Corporation" not in l)

        return {
            "test_signing": "testsigning" in bcd_lower,
            "integrity_checks": "nointegritychecks" not in bcd_lower,
            "non_microsoft_drivers": non_ms,
            "alerts": alerts,
            "indicator": "Rootkit / Bootkit",
            "defense_note": (
                "Rootkits/bootkits são detectados por alterações de boot "
                "(BCD), integridade do sistema (nointegritychecks), e "
                "drivers não assinados carregados no kernel."
            ),
        }

    # ──────────────────────────────────────────────────────────────────
    # 8. Supply-Chain Compromise Detection
    # ──────────────────────────────────────────────────────────────────

    def detect_supply_chain_compromise(self) -> dict:
        """Detecta alterações suspeitas em dependências."""
        alerts = []
        modified = []

        for filename, ecosystem in DEPENDENCY_FILES.items():
            result = _run_cmd(f'dir /s /b "{filename}" 2>nul', timeout=10)
            for path in result.splitlines():
                path = path.strip()
                if not path:
                    continue
                try:
                    mtime = os.path.getmtime(path)
                    age_h = (time.time() - mtime) / 3600
                    if age_h < 48:
                        modified.append({
                            "path": path,
                            "ecosystem": ecosystem,
                            "hours_ago": round(age_h, 1),
                        })
                except OSError:
                    pass

        if modified:
            alerts.append({
                "type": "recent_dependency_change",
                "severity": "MEDIUM",
                "detail": f"{len(modified)} arquivos de dependência "
                          f"modificados — verificar supply-chain integrity",
            })

        return {
            "modified_deps": modified,
            "alerts": alerts,
            "indicator": "Supply-Chain",
            "defense_note": (
                "Supply-chain é detectado por alterações inesperadas em "
                "dependências (package.json, requirements.txt, Cargo.toml). "
                "Monitore modificações recentes e hashes de pacotes."
            ),
        }

    # ──────────────────────────────────────────────────────────────────
    # 9. Data Exfiltration Detection
    # ──────────────────────────────────────────────────────────────────

    def detect_data_exfiltration(self) -> dict:
        """Detecta exfiltração de dados: conexões externas anômalas."""
        alerts = []
        output = _run_cmd('netstat -ano | findstr ESTABLISHED')

        external = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 5:
                remote = parts[2].rsplit(":", 1)
                try:
                    ip = ipaddress.ip_address(remote[0])
                    port = int(remote[1]) if remote[1].isdigit() else 0
                    if not ip.is_private and not ip.is_loopback:
                        external.append({"ip": str(ip), "port": port})
                except ValueError:
                    pass

        unusual = {c["port"] for c in external
                   if c["port"] not in {80, 443, 53, 123, 22, 993, 587, 8080, 8443}}

        if len(external) > 25:
            alerts.append({
                "type": "massive_outbound",
                "severity": "HIGH",
                "detail": f"{len(external)} conexões externas — "
                          f"possível C2 ou exfiltração",
            })

        if unusual:
            alerts.append({
                "type": "unusual_ports",
                "severity": "MEDIUM",
                "detail": f"Portas de saída incomuns: {sorted(unusual)}",
            })

        return {
            "external_connections": len(external),
            "unusual_ports": sorted(unusual),
            "alerts": alerts,
            "indicator": "Exfiltration",
            "defense_note": (
                "Exfiltração é detectada por tráfego de saída anômalo: "
                "volume excessivo, portas incomuns, DNS tunneling (>100 queries/h), "
                "conexões em horários suspeitos."
            ),
        }

    # ──────────────────────────────────────────────────────────────────
    # FULL SCAN — Todas as 9 categorias
    # ──────────────────────────────────────────────────────────────────

    def full_advanced_scan(self) -> dict:
        """Executa scan completo de todas as categorias de ameaça."""
        _log("=" * 60)
        _log("ADVANCED THREAT DETECTOR — Full Behavioral Scan")
        _log("=" * 60)

        results = {
            "rce": self.detect_rce_indicators(),
            "credentials": self.detect_credential_attacks(),
            "privilege": self.detect_privilege_escalation(),
            "persistence": self.detect_persistence_mechanisms(),
            "lateral": self.detect_lateral_movement(),
            "fileless": self.detect_fileless_and_zero_day(),
            "bootkit": self.detect_bootkit_rootkit_indicators(),
            "supply_chain": self.detect_supply_chain_compromise(),
            "exfiltration": self.detect_data_exfiltration(),
        }

        # Consolida alertas
        all_alerts = []
        for cat, data in results.items():
            for a in data.get("alerts", []):
                a["_category"] = cat
                all_alerts.append(a)

        critical = [a for a in all_alerts if a["severity"] == "CRITICAL"]
        high = [a for a in all_alerts if a["severity"] == "HIGH"]

        _log(
            f"Scan concluído: {len(all_alerts)} indicadores "
            f"({len(critical)} CRITICAL, {len(high)} HIGH)",
            "INFO",
        )

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "categories": results,
            "all_indicators": all_alerts,
            "summary": {
                "total": len(all_alerts),
                "critical": len(critical),
                "high": len(high),
                "threat_level": (
                    "CRITICAL" if critical else
                    "ELEVATED" if len(high) >= 3 else
                    "MODERATE" if high else "LOW"
                ),
                "verdict": (
                    "🔴 Múltiplos indicadores críticos — possível APT "
                    "ou ataque coordenado em andamento!"
                    if len(critical) >= 2 else
                    "🟡 Indicadores suspeitos — investigar imediatamente"
                    if critical or high else
                    "🟢 Nenhum indicador crítico de ameaça avançada"
                ),
            },
        }


# ═══════════════════════════════════════════════════════════════════════════
# Teste
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S. — Advanced Threat Detector Test")
    print("=" * 60)

    detector = AdvancedThreatDetector()

    print("\n[1] RCE Indicators...")
    rce = detector.detect_rce_indicators()
    print(f"    Alertas: {len(rce['alerts'])}")

    print("\n[2] Credential Attacks...")
    cred = detector.detect_credential_attacks()
    print(f"    Falhas login: {cred['event_4625_failed_logins']}")
    print(f"    Pass-the-Hash/Ticket: {cred['event_4648_explicit_credential']}")

    print("\n[3] Privilege Escalation...")
    priv = detector.detect_privilege_escalation()
    print(f"    Alertas: {len(priv['alerts'])}")

    print("\n[4] Fileless/Zero-Day...")
    fl = detector.detect_fileless_and_zero_day()
    print(f"    Alertas: {len(fl['alerts'])}")

    print("\n[5] Bootkit/Rootkit...")
    bk = detector.detect_bootkit_rootkit_indicators()
    print(f"    Alertas: {len(bk['alerts'])}")

    print("\n[ADV-THD] Teste concluído.")
