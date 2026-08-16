"""
network_mapper.py — Network Topology Mapper (J.A.R.V.I.S.)

Varredura LEVE da rede local para identificar dispositivos conectados e mapear
portas abertas, sem depender de privilégios elevados ou de libs pesadas (sem
scapy). Usa socket (TCP connect) com timeout curto e concorrência limitada,
além de enriquecer os dados com a tabela ARP do sistema (`arp -a`).

Comando principal: /net-map [faixa]

O resultado estruturado pode ser consumido pelo HUD (launcher) para exibir a
topologia da rede em uma aba dedicada.
"""

import concurrent.futures
import ipaddress
import re
import socket
import subprocess
from typing import Optional

# Portas comuns varridas em cada host descoberto (mantém a varredura leve).
PORTAS_COMUNS = [22, 80, 443, 445, 3389, 8080, 3306, 5432]


def _log(mensagem: str, nivel: str = "INFO") -> None:
    print(f"[NET-MAP {nivel:<5}] {mensagem}", flush=True)


def _obter_rede_local() -> Optional[ipaddress.IPv4Network]:
    """Descobre a sub-rede IPv4 local (via psutil) ou assume /24 como fallback."""
    try:
        import psutil
        for _, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    ip = addr.address
                    netmask = addr.netmask or "255.255.255.0"
                    try:
                        return ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)
                    except ValueError:
                        continue
    except Exception:
        pass

    # Fallback: usa o IP local e assume máscara /24.
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ipaddress.IPv4Network(f"{ip}/24", strict=False)
    except Exception:
        pass
    return None


def _porta_aberta(ip: str, porta: int, timeout: float) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        resultado = s.connect_ex((ip, porta))
        return resultado == 0
    except OSError:
        return False
    finally:
        s.close()


def _host_ativo(ip: str, portas: list[int], timeout: float) -> bool:
    return any(_porta_aberta(ip, p, timeout) for p in portas)


def _obter_tabela_arp() -> dict[str, str]:
    """Mapeia IP → MAC a partir da tabela ARP do sistema (`arp -a`)."""
    try:
        proc = subprocess.run(
            ["arp", "-a"], capture_output=True, text=True,
            timeout=10, errors="replace",
        )
        saida = proc.stdout or ""
    except Exception:
        return {}

    macs: dict[str, str] = {}
    for linha in saida.splitlines():
        m = re.search(
            r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{11,17})", linha
        )
        if m:
            macs[m.group(1)] = m.group(2)
    return macs


def mapear_rede_local(
    timeout: float = 0.6,
    portas: Optional[list[int]] = None,
    max_workers: int = 40,
) -> dict:
    """
    Varre a sub-rede local identificando hosts ativos e portas abertas.

    Returns:
        {"rede", "hosts", "total", "arp", "timestamp"}
    """
    portas = portas or PORTAS_COMUNS
    rede = _obter_rede_local()
    if rede is None:
        return {
            "rede": "desconhecida", "hosts": [], "total": 0,
            "arp": {}, "timestamp": "",
        }

    ips = [str(ip) for ip in rede.hosts()]
    arp = _obter_tabela_arp()

    def _varrer(ip: str) -> Optional[dict]:
        abertas = [p for p in portas if _porta_aberta(ip, p, timeout)]
        if abertas:
            return {
                "ip": ip,
                "mac": arp.get(ip, "desconhecido"),
                "portas": abertas,
            }
        return None

    hosts: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for resultado in executor.map(_varrer, ips):
            if resultado:
                hosts.append(resultado)

    return {
        "rede": str(rede),
        "hosts": hosts,
        "total": len(hosts),
        "arp": arp,
        "timestamp": _timestamp(),
    }


def _timestamp() -> str:
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def formatar_relatorio_rede(resultado: dict) -> str:
    """Formata o resultado da varredura em um relatório textual."""
    linhas = [
        "TOPOLOGIA DA REDE LOCAL",
        "─" * 40,
        f"Rede: {resultado.get('rede', '?')}",
        f"Dispositivos ativos: {resultado.get('total', 0)}",
        f"Instante: {resultado.get('timestamp', '')}",
        "",
    ]
    hosts = resultado.get("hosts", [])
    if not hosts:
        linhas.append("Nenhum dispositivo respondendo foi encontrado.")
    for h in hosts:
        portas = ", ".join(str(p) for p in h.get("portas", []))
        linhas.append(
            f"• {h['ip']}  [MAC {h.get('mac', '?')}]  portas: {portas or '-'}"
        )
    return "\n".join(linhas)


def executar_varredura() -> tuple[bool, str]:
    """Fluxo completo do /net-map: varre e retorna (sucesso, relatório)."""
    try:
        resultado = mapear_rede_local()
    except Exception as exc:
        return False, f"Falha na varredura de rede: {exc}"
    return True, formatar_relatorio_rede(resultado)


# ---------------------------------------------------------------------------
# Teste direto (varredura real da rede local)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S — Network Topology Mapper (teste)")
    print("=" * 60)
    ok, relatorio = executar_varredura()
    print(relatorio)
