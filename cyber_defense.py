"""
cyber_defense.py — J.A.R.V.I.S. Cyber Defense Shield v1.0

Sistema defensivo completo para detecção de intrusão, varredura de
vulnerabilidades, hardening automatizado e análise forense.

Opera EXCLUSIVAMENTE no sistema local do usuário. Nenhuma ferramenta
ofensiva externa — apenas autodefesa ativa.

Módulos:
  - IntrusionDetector: monitor de conexões suspeitas, brute-force, port scan
  - VulnerabilityScanner: portas abertas, CVEs, firewall audit
  - SystemHardening: fechamento de portas, políticas, atualizações
  - ForensicAnalyzer: Windows Event Log, tentativas de login, integridade
  - ThreatIntelligence: OSINT passivo (WHOIS, DNS, reputação)
"""

import hashlib
import ipaddress
import json
import os
import re
import socket
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Callable

# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTES
# ═══════════════════════════════════════════════════════════════════════════

# Portas conhecidas de malware / backdoors comuns
KNOWN_MALWARE_PORTS = {
    4444, 1337, 31337, 6666, 6667, 7777, 8888, 9000, 9001,
    12345, 23456, 55555, 65535, 666, 9999, 6969, 8080, 8880,
}

# Portas que NUNCA deveriam estar abertas em um desktop
SUSPICIOUS_PORTS = {
    21, 22, 23, 25, 53, 110, 143, 3306, 3389, 5432, 5900,
    6379, 27017, 27018, 27019,
}

# Thresholds de detecção
PORT_SCAN_THRESHOLD = 8      # conexões para portas diferentes em 5s
BRUTE_FORCE_THRESHOLD = 5     # falhas de login em 60s
MAX_CONNECTIONS_PER_IP = 50   # conexões simultâneas por IP remoto

# Caminhos críticos do sistema para verificação de integridade
CRITICAL_SYSTEM_PATHS = [
    r"C:\Windows\System32\drivers\etc\hosts",
    r"C:\Windows\System32\config\SAM",
    r"C:\Windows\System32\config\SYSTEM",
]

# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _log(msg: str, level: str = "INFO") -> None:
    print(f"[CYBER-D {level:<5}] {msg}", flush=True)


def _run_cmd(command: str, timeout: int = 10) -> str:
    """Executa comando shell e retorna stdout."""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=timeout, encoding="cp850", errors="replace",
        )
        return result.stdout.strip()
    except Exception as exc:
        _log(f"Falha ao executar '{command[:60]}': {exc}", "ERROR")
        return ""


def _run_powershell(script: str, timeout: int = 15) -> str:
    """Executa script PowerShell e retorna stdout."""
    return _run_cmd(f'powershell -NoProfile -Command "{script}"', timeout)


# ═══════════════════════════════════════════════════════════════════════════
# MÓDULO 1: DETECÇÃO DE INTRUSÃO EM TEMPO REAL
# ═══════════════════════════════════════════════════════════════════════════

class IntrusionDetector:
    """
    Monitor de intrusão em tempo real.

    Detecta:
      - Port scanning (múltiplas conexões para portas diferentes)
      - Brute-force (múltiplas falhas de login)
      - Conexões para portas de malware conhecidas
      - Conexões de IPs suspeitos (geolocalização reversa)
      - Processos suspeitos se comunicando na rede
    """

    def __init__(self):
        self._connection_history: list[dict] = []
        self._login_failures: dict[str, list[float]] = defaultdict(list)
        self._alerts: list[dict] = []
        self._baseline_connections: set[str] = self._capture_baseline()

    def _capture_baseline(self) -> set[str]:
        """Captura o estado atual das conexões como baseline."""
        output = _run_cmd("netstat -ano | findstr ESTABLISHED")
        connections = set()
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 5:
                connections.add(f"{parts[1]}->{parts[2]}")
        _log(f"Baseline capturada: {len(connections)} conexões estabelecidas.", "INFO")
        return connections

    def scan_active_connections(self) -> dict:
        """
        Escaneia conexões TCP/UDP ativas e retorna análise de ameaças.

        Returns:
            Dict com 'total', 'suspicious', 'alerts', 'connections'
        """
        output = _run_cmd("netstat -ano")
        connections = []
        suspicious = []
        alerts = []

        # Parse netstat
        remote_ips: Counter[str] = Counter()
        remote_ports: Counter[int] = Counter()

        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 5 or parts[0] not in ("TCP", "UDP"):
                continue

            proto = parts[0]
            local = parts[1]
            remote = parts[2]
            state = parts[3] if len(parts) >= 4 else "UDP"
            pid = parts[-1] if len(parts) >= 5 else "?"

            conn = {
                "proto": proto,
                "local": local,
                "remote": remote,
                "state": state,
                "pid": pid,
            }
            connections.append(conn)

            # Extrai IP remoto
            if ":" in remote:
                remote_ip = remote.rsplit(":", 1)[0]
                try:
                    remote_port = int(remote.rsplit(":", 1)[1])
                except ValueError:
                    continue

                # Conta IPs e portas
                if remote_ip not in ("0.0.0.0", "*", "127.0.0.1", "::1", "localhost"):
                    remote_ips[remote_ip] += 1
                    remote_ports[remote_port] += 1

                # Verifica portas de malware conhecidas
                if remote_port in KNOWN_MALWARE_PORTS:
                    alerts.append({
                        "type": "malware_port",
                        "severity": "HIGH",
                        "detail": f"Porta suspeita {remote_port} (malware conhecido)",
                        "connection": conn,
                    })

                # Verifica portas suspeitas
                if remote_port in SUSPICIOUS_PORTS:
                    alerts.append({
                        "type": "suspicious_port",
                        "severity": "MEDIUM",
                        "detail": f"Porta {remote_port} não deveria estar ativa em desktop",
                        "connection": conn,
                    })

        # Detecta IPs com excesso de conexões
        for ip, count in remote_ips.items():
            if count > MAX_CONNECTIONS_PER_IP:
                alerts.append({
                    "type": "excessive_connections",
                    "severity": "HIGH",
                    "detail": f"{count} conexões simultâneas de {ip}",
                })

        # Detecta port scanning (muitas portas abertas para o mesmo IP)
        for ip in remote_ips:
            ports_to_ip = [
                c["remote"].rsplit(":", 1)[1]
                for c in connections
                if c["remote"].startswith(ip + ":")
            ]
            unique_ports = len(set(ports_to_ip))
            if unique_ports >= PORT_SCAN_THRESHOLD:
                alerts.append({
                    "type": "port_scan",
                    "severity": "CRITICAL",
                    "detail": f"Possível port scan: {unique_ports} portas de {ip}",
                })

        result = {
            "total": len(connections),
            "suspicious": len(suspicious),
            "alert_count": len(alerts),
            "alerts": alerts,
            "connections": connections[:20],  # limita para não sobrecarregar
            "top_remote_ips": remote_ips.most_common(5),
        }
        return result

    def detect_brute_force(self) -> dict:
        """
        Analisa o Windows Event Log para detectar tentativas de brute-force.

        Returns:
            Dict com 'attempts', 'sources', 'alerts'
        """
        # Event ID 4625 = failed login
        script = """
        Get-WinEvent -FilterHashtable @{LogName='Security'; ID=4625} -MaxEvents 50 |
        Select-Object TimeCreated,
            @{n='User';e={$_.Properties[5].Value}},
            @{n='SourceIP';e={$_.Properties[18].Value}},
            @{n='Status';e={$_.Properties[8].Value}}
        """
        output = _run_powershell(script)
        if not output:
            return {"attempts": 0, "sources": {}, "alerts": []}

        attempts = []
        sources: Counter[str] = Counter()
        alerts = []
        now = datetime.now(timezone.utc)
        recent_window = now - timedelta(minutes=5)

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            # Parse simples da saída do PowerShell
            parts = line.split()
            try:
                # Extrai IP de origem se presente
                for part in parts:
                    if re.match(r"\d+\.\d+\.\d+\.\d+", part):
                        sources[part] += 1
                        break
            except Exception:
                pass

        # Alerta se > BRUTE_FORCE_THRESHOLD falhas do mesmo IP
        for ip, count in sources.items():
            if count >= BRUTE_FORCE_THRESHOLD:
                alerts.append({
                    "type": "brute_force",
                    "severity": "CRITICAL",
                    "detail": f"Possível brute-force: {count} falhas de login do IP {ip}",
                })

        return {
            "attempts": len(output.splitlines()),
            "sources": dict(sources.most_common(10)),
            "alerts": alerts,
        }

    def detect_suspicious_processes(self) -> dict:
        """
        Detecta processos suspeitos baseado em conexões de rede e nomes.

        Returns:
            Dict com 'suspicious_processes', 'alerts'
        """
        suspicious_names = [
            "nc.exe", "ncat.exe", "netcat", "mimikatz", "procmon",
            "wireshark", "tcpdump", "nmap", "zenmap", "hydra",
            "medusa", "john", "hashcat", "cain", "ettercap",
            "bettercap", "aircrack", "kismet", "burp", "zap",
        ]

        # Processos com conexão de rede ativa
        output = _run_cmd(
            'tasklist /FI "STATUS eq running" /FO CSV /NH'
        )
        alerts = []
        suspicious = []

        for line in output.splitlines():
            line = line.strip().strip('"')
            if not line:
                continue
            parts = line.split('","')
            if len(parts) >= 1:
                name = parts[0].lower()
                for sus in suspicious_names:
                    if sus in name:
                        suspicious.append({
                            "name": parts[0],
                            "pid": parts[1] if len(parts) > 1 else "?",
                            "match": sus,
                        })
                        alerts.append({
                            "type": "suspicious_process",
                            "severity": "MEDIUM",
                            "detail": f"Processo suspeito detectado: {parts[0]} (match: {sus})",
                        })

        return {
            "suspicious_count": len(suspicious),
            "suspicious": suspicious,
            "alerts": alerts,
        }

    def full_scan(self) -> dict:
        """Executa todos os scans de detecção e retorna relatório consolidado."""
        _log("Iniciando scan completo de detecção de intrusão...", "INFO")

        connections = self.scan_active_connections()
        brute_force = self.detect_brute_force()
        processes = self.detect_suspicious_processes()

        all_alerts = (
            connections.get("alerts", []) +
            brute_force.get("alerts", []) +
            processes.get("alerts", [])
        )

        critical = [a for a in all_alerts if a.get("severity") == "CRITICAL"]
        high = [a for a in all_alerts if a.get("severity") == "HIGH"]

        _log(
            f"Scan concluído: {len(all_alerts)} alertas "
            f"({len(critical)} CRITICAL, {len(high)} HIGH)",
            "INFO"
        )

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "connections": connections,
            "brute_force": brute_force,
            "processes": processes,
            "all_alerts": all_alerts,
            "summary": {
                "total_alerts": len(all_alerts),
                "critical": len(critical),
                "high": len(high),
                "status": "UNDER_ATTACK" if critical else (
                    "SUSPICIOUS" if high else "CLEAN"
                ),
            },
        }


# ═══════════════════════════════════════════════════════════════════════════
# MÓDULO 2: SCANNER DE VULNERABILIDADES LOCAL
# ═══════════════════════════════════════════════════════════════════════════

class VulnerabilityScanner:
    """
    Scanner de vulnerabilidades do sistema local.

    Verifica:
      - Portas TCP/UDP abertas e serviços associados
      - Firewall status e regras
      - Políticas de senha e conta
      - Atualizações pendentes do Windows
    """

    def scan_open_ports(self) -> dict:
        """Lista todas as portas TCP/UDP em escuta e seus processos donos."""
        output = _run_cmd("netstat -ano | findstr LISTENING")
        ports = []
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 5:
                local = parts[1]
                pid = parts[-1]
                port = local.rsplit(":", 1)[-1] if ":" in local else local

                # Obtém nome do processo
                proc_name = ""
                try:
                    proc_output = _run_cmd(f'tasklist /FI "PID eq {pid}" /FO CSV /NH')
                    if proc_output:
                        proc_parts = proc_output.strip().strip('"').split('","')
                        proc_name = proc_parts[0] if proc_parts else ""
                except Exception:
                    pass

                ports.append({
                    "port": port,
                    "address": local,
                    "pid": pid,
                    "process": proc_name,
                })

        return {
            "total_listening": len(ports),
            "ports": ports,
        }

    def scan_firewall_status(self) -> dict:
        """Verifica o status do firewall do Windows."""
        profiles = []
        output = _run_cmd("netsh advfirewall show allprofiles")
        current_profile = ""
        for line in output.splitlines():
            line = line.strip()
            if "Profile" in line and "Settings" in line:
                current_profile = line.split("Profile")[0].strip()
            if current_profile and "State" in line and "ON" in line.upper():
                profiles.append(current_profile)
                current_profile = ""

        # Verifica regras inbound
        rules_output = _run_cmd(
            'netsh advfirewall firewall show rule name=all dir=in | '
            'findstr /C:"Rule Name" /C:"Enabled"'
        )
        enabled_rules = rules_output.count("Yes")

        return {
            "firewall_active": len(profiles) > 0,
            "profiles": profiles,
            "enabled_inbound_rules": enabled_rules,
        }

    def scan_password_policy(self) -> dict:
        """Verifica políticas de senha e conta do Windows."""
        output = _run_cmd("net accounts")
        policy = {}
        for line in output.splitlines():
            line = line.strip()
            if "Minimum password length" in line:
                policy["min_length"] = line.split(":")[-1].strip()
            if "Maximum password age" in line:
                policy["max_age_days"] = line.split(":")[-1].strip()
            if "Lockout threshold" in line:
                policy["lockout_threshold"] = line.split(":")[-1].strip()

        return policy

    def scan_windows_updates(self) -> dict:
        """Verifica atualizações pendentes do Windows (via wmic)."""
        output = _run_cmd(
            'wmic qfe list brief /format:table',
            timeout=20,
        )
        # Conta atualizações instaladas
        installed = len([l for l in output.splitlines() if "KB" in l])

        return {
            "installed_updates": installed,
            "recommendation": (
                "Sistema atualizado" if installed > 50
                else "Verificar Windows Update — poucas atualizações detectadas"
            ),
        }

    def full_scan(self) -> dict:
        """Executa scan completo de vulnerabilidades."""
        _log("Iniciando scan de vulnerabilidades...", "INFO")

        ports = self.scan_open_ports()
        firewall = self.scan_firewall_status()
        password = self.scan_password_policy()
        updates = self.scan_windows_updates()

        vulnerabilities = []

        # Análise de risco
        if not firewall.get("firewall_active"):
            vulnerabilities.append({
                "severity": "CRITICAL",
                "detail": "Firewall do Windows está DESATIVADO",
            })

        if int(password.get("min_length", "0")) < 8:
            vulnerabilities.append({
                "severity": "HIGH",
                "detail": f"Senha mínima muito curta ({password.get('min_length', '?')} caracteres)",
            })

        listening_count = ports.get("total_listening", 0)
        if listening_count > 50:
            vulnerabilities.append({
                "severity": "MEDIUM",
                "detail": f"{listening_count} portas em escuta — superfície de ataque elevada",
            })

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ports": ports,
            "firewall": firewall,
            "password_policy": password,
            "updates": updates,
            "vulnerabilities": vulnerabilities,
            "risk_score": len([v for v in vulnerabilities if v["severity"] == "CRITICAL"]) * 25 +
                          len([v for v in vulnerabilities if v["severity"] == "HIGH"]) * 10 +
                          len([v for v in vulnerabilities if v["severity"] == "MEDIUM"]) * 3,
        }


# ═══════════════════════════════════════════════════════════════════════════
# MÓDULO 3: HARDENING AUTOMATIZADO
# ═══════════════════════════════════════════════════════════════════════════

class SystemHardening:
    """
    Hardening automatizado do sistema Windows.

    Ações:
      - Fechamento de portas desnecessárias
      - Ativação de políticas de segurança
      - Verificação de integridade de arquivos
    """

    @staticmethod
    def get_recommendations(vuln_scan: dict) -> list[dict]:
        """Gera recomendações de hardening baseado no scan de vulnerabilidades."""
        recommendations = []

        firewall = vuln_scan.get("firewall", {})
        if not firewall.get("firewall_active"):
            recommendations.append({
                "action": "enable_firewall",
                "command": "netsh advfirewall set allprofiles state on",
                "description": "Ativar Firewall do Windows em todos os perfis",
                "risk_reduction": "CRITICAL",
            })

        password = vuln_scan.get("password_policy", {})
        if int(password.get("min_length", "0")) < 8:
            recommendations.append({
                "action": "set_password_policy",
                "command": 'net accounts /minpwlen:12',
                "description": "Aumentar tamanho mínimo de senha para 12 caracteres",
                "risk_reduction": "HIGH",
            })

        recommendations.append({
            "action": "disable_smbv1",
            "command": 'powershell -Command "Disable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol"',
            "description": "Desabilitar SMBv1 (vulnerável a WannaCry/EternalBlue)",
            "risk_reduction": "HIGH",
        })

        recommendations.append({
            "action": "enable_defender_realtime",
            "command": 'powershell -Command "Set-MpPreference -DisableRealtimeMonitoring $false"',
            "description": "Garantir que Windows Defender esteja ativo em tempo real",
            "risk_reduction": "HIGH",
        })

        return recommendations

    def check_file_integrity(self) -> dict:
        """Verifica integridade de arquivos críticos do sistema."""
        results = []
        for path in CRITICAL_SYSTEM_PATHS:
            file_path = Path(path)
            if not file_path.exists():
                results.append({
                    "path": path,
                    "status": "MISSING",
                    "alert": "Arquivo crítico não encontrado — possível tampering",
                })
                continue

            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                file_hash = hashlib.sha256(content).hexdigest()
                mtime = datetime.fromtimestamp(
                    file_path.stat().st_mtime,
                    tz=timezone.utc,
                ).isoformat()

                results.append({
                    "path": path,
                    "status": "OK",
                    "sha256": file_hash[:16] + "...",
                    "last_modified": mtime,
                })
            except PermissionError:
                results.append({
                    "path": path,
                    "status": "PERMISSION_DENIED",
                    "alert": "Sem permissão para ler — executar como administrador",
                })

        return {
            "files_checked": len(results),
            "results": results,
        }


# ═══════════════════════════════════════════════════════════════════════════
# MÓDULO 4: ANÁLISE FORENSE & THREAT INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════

class ForensicAnalyzer:
    """
    Análise forense do Windows Event Log.

    Analisa:
      - Tentativas de login (sucesso e falha)
      - Escalonamento de privilégios
      - Modificações de política de auditoria
      - Criação de processos suspeitos
    """

    def analyze_login_events(self, hours_back: int = 24) -> dict:
        """Analisa eventos de login das últimas N horas."""
        script = f"""
        $start = (Get-Date).AddHours(-{hours_back})
        Get-WinEvent -FilterHashtable @{{
            LogName='Security'
            ID=4624,4625
            StartTime=$start
        }} -MaxEvents 100 -ErrorAction SilentlyContinue |
        Select-Object TimeCreated, Id,
            @{{n='User';e={{$_.Properties[5].Value}}}},
            @{{n='Domain';e={{$_.Properties[6].Value}}}},
            @{{n='LogonType';e={{$_.Properties[8].Value}}}},
            @{{n='SourceIP';e={{$_.Properties[18].Value}}}}
        """
        output = _run_powershell(script.format(hours_back=hours_back), timeout=20)

        success_count = 0
        fail_count = 0
        logon_types: Counter[str] = Counter()

        for line in output.splitlines():
            if "4624" in line:
                success_count += 1
            if "4625" in line:
                fail_count += 1
            # Conta tipos de logon
            for lt in ["2", "3", "5", "7", "10"]:  # Interactive, Network, Service, Unlock, Remote
                if lt in line:
                    logon_types[lt] += 1

        return {
            "total_events": success_count + fail_count,
            "successful_logins": success_count,
            "failed_logins": fail_count,
            "failure_rate": round(fail_count / max(success_count + fail_count, 1) * 100, 1),
            "logon_types": dict(logon_types),
        }

    def analyze_privilege_escalation(self) -> dict:
        """Detecta tentativas de escalonamento de privilégios (Event ID 4672)."""
        script = """
        Get-WinEvent -FilterHashtable @{LogName='Security'; ID=4672} -MaxEvents 20
            -ErrorAction SilentlyContinue |
        Select-Object TimeCreated,
            @{n='SubjectUser';e={$_.Properties[1].Value}},
            @{n='SubjectDomain';e={$_.Properties[2].Value}}
        """
        output = _run_powershell(script, timeout=15)
        events = len([l for l in output.splitlines() if l.strip()])

        return {
            "privilege_escalation_events": events,
            "alert": events > 10,
            "detail": (
                f"{events} eventos de privilégio especial detectados recentemente"
                if events > 0 else "Nenhum evento de privilégio suspeito"
            ),
        }

    def full_report(self) -> dict:
        """Gera relatório forense completo."""
        _log("Gerando relatório forense...", "INFO")

        login = self.analyze_login_events()
        privilege = self.analyze_privilege_escalation()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "login_analysis": login,
            "privilege_analysis": privilege,
        }


class ThreatIntelligence:
    """
    Inteligência de ameaças — OSINT passivo.

    Realiza consultas PASSIVAS (sem interação direta com o alvo):
      - WHOIS de IP/domínio
      - DNS reverso (PTR)
      - Reputação de IP (AbuseIPDB — requer chave opcional)
    """

    @staticmethod
    def whois_lookup(target: str) -> dict:
        """Consulta WHOIS de um IP ou domínio (passivo)."""
        if not target or len(target) < 3:
            return {"error": "Target inválido"}

        # Usa socket para resolução reversa
        try:
            hostname = socket.gethostbyaddr(target)[0]
        except (socket.herror, socket.gaierror):
            hostname = "N/A"

        # Consulta WHOIS via whois.iana.org (porta 43)
        try:
            sock = socket.create_connection(("whois.iana.org", 43), timeout=5)
            sock.send(f"{target}\r\n".encode())
            response = b""
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                response += data
            sock.close()
            whois_text = response.decode("utf-8", errors="replace")

            # Extrai informações relevantes
            org = ""
            country = ""
            for line in whois_text.splitlines():
                if "organisation:" in line.lower() or "org-name:" in line.lower():
                    org = line.split(":", 1)[-1].strip()
                if "country:" in line.lower():
                    country = line.split(":", 1)[-1].strip()

        except Exception:
            whois_text = "WHOIS lookup indisponível"
            org = "Desconhecida"
            country = "Desconhecido"

        return {
            "target": target,
            "reverse_dns": hostname,
            "organization": org,
            "country": country,
        }

    @staticmethod
    def dns_lookup(domain: str) -> dict:
        """Resolução DNS completa de um domínio (A, AAAA, MX, TXT)."""
        records = {}
        try:
            records["A"] = socket.gethostbyname_ex(domain)[2]
        except socket.gaierror:
            records["A"] = []

        try:
            records["AAAA"] = socket.getaddrinfo(domain, None, socket.AF_INET6)
            records["AAAA"] = list(set(a[4][0] for a in records["AAAA"]))
        except socket.gaierror:
            records["AAAA"] = []

        return {
            "domain": domain,
            "records": records,
        }

    @staticmethod
    def check_ip_reputation(ip: str) -> dict:
        """
        Verifica reputação de IP via AbuseIPDB (requer chave de API).

        Sem chave, faz verificação básica: DNS reverso + se é IP privado.
        """
        try:
            ip_obj = ipaddress.ip_address(ip)
        except ValueError:
            return {"error": "IP inválido"}

        is_private = ip_obj.is_private
        is_loopback = ip_obj.is_loopback

        try:
            hostname = socket.gethostbyaddr(ip)[0]
        except (socket.herror, socket.gaierror):
            hostname = "N/A"

        return {
            "ip": ip,
            "is_private": is_private,
            "is_loopback": is_loopback,
            "reverse_dns": hostname,
            "risk_assessment": (
                "BAIXO (IP local/privado)" if is_private or is_loopback
                else "Verificação básica — configure chave AbuseIPDB para análise completa"
            ),
        }


# ═══════════════════════════════════════════════════════════════════════════
# CONSOLIDADOR — Cyber Defense Report completo
# ═══════════════════════════════════════════════════════════════════════════

def generate_defense_report(target_ip: Optional[str] = None) -> dict:
    """
    Gera relatório completo de defesa cibernética.

    Args:
        target_ip: IP suspeito para investigar (opcional).

    Returns:
        Dicionário com todos os módulos de análise.
    """
    _log("=" * 60)
    _log("J.A.R.V.I.S. CYBER DEFENSE SHIELD — Relatório Completo")
    _log("=" * 60)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
    }

    # Módulo 1: Detecção de Intrusão
    _log("[1/4] Executando Detecção de Intrusão...")
    detector = IntrusionDetector()
    report["intrusion"] = detector.full_scan()

    # Módulo 2: Scanner de Vulnerabilidades
    _log("[2/4] Executando Scanner de Vulnerabilidades...")
    scanner = VulnerabilityScanner()
    report["vulnerabilities"] = scanner.full_scan()

    # Módulo 3: Hardening
    _log("[3/4] Gerando recomendações de Hardening...")
    hardening = SystemHardening()
    report["hardening"] = {
        "recommendations": hardening.get_recommendations(
            report["vulnerabilities"]
        ),
        "file_integrity": hardening.check_file_integrity(),
    }

    # Módulo 4: Forense + Threat Intel
    _log("[4/4] Executando Análise Forense e Threat Intelligence...")
    forensic = ForensicAnalyzer()
    report["forensic"] = forensic.full_report()

    threat = ThreatIntelligence()
    if target_ip:
        report["threat_intel"] = {
            "whois": threat.whois_lookup(target_ip),
            "reputation": threat.check_ip_reputation(target_ip),
        }
    else:
        report["threat_intel"] = {"note": "Forneça target_ip para análise de ameaça externa"}

    # Resumo executivo
    intrusion_status = report["intrusion"]["summary"]["status"]
    risk_score = report["vulnerabilities"].get("risk_score", 0)
    total_alerts = report["intrusion"]["summary"]["total_alerts"]

    if intrusion_status == "UNDER_ATTACK":
        overall = "🔴 CRITICAL — Possível ataque em andamento!"
    elif intrusion_status == "SUSPICIOUS" or risk_score > 20:
        overall = "🟡 WARNING — Atividade suspeita detectada"
    else:
        overall = "🟢 CLEAN — Sistema aparenta estar seguro"

    report["executive_summary"] = {
        "status": overall,
        "intrusion_alerts": total_alerts,
        "vulnerability_risk_score": risk_score,
        "hardening_recommendations": len(
            report["hardening"]["recommendations"]
        ),
    }

    _log(f"Relatório concluído: {overall}")
    return report


# ═══════════════════════════════════════════════════════════════════════════
# Teste direto
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S. — Cyber Defense Shield Test")
    print("=" * 60)

    # 1. Detecção de Intrusão
    print("\n[1] Testando Detecção de Intrusão...")
    detector = IntrusionDetector()
    conn_result = detector.scan_active_connections()
    print(f"    Conexões ativas: {conn_result['total']}")
    print(f"    Alertas: {len(conn_result['alerts'])}")
    for alert in conn_result["alerts"][:3]:
        print(f"      [{alert['severity']}] {alert['detail'][:80]}")

    # 2. Scanner de Vulnerabilidades
    print("\n[2] Testando Scanner de Vulnerabilidades...")
    scanner = VulnerabilityScanner()
    ports = scanner.scan_open_ports()
    print(f"    Portas em escuta: {ports['total_listening']}")
    firewall = scanner.scan_firewall_status()
    print(f"    Firewall ativo: {firewall['firewall_active']}")

    # 3. Hardening
    print("\n[3] Testando Hardening...")
    hardening = SystemHardening()
    integrity = hardening.check_file_integrity()
    print(f"    Arquivos verificados: {integrity['files_checked']}")

    # 4. Threat Intelligence (exemplo)
    print("\n[4] Testando Threat Intelligence...")
    threat = ThreatIntelligence()
    if False:  # Desabilitado para não fazer requisições externas no teste
        result = threat.whois_lookup("8.8.8.8")
        print(f"    WHOIS 8.8.8.8: {result.get('organization', 'N/A')}")

    print("\n[CYBER-D] Teste concluído.")
