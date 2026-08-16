"""
virtual_lab.py — Cyber Range & Virtual Lab Manager (J.A.R.V.I.S.)

Gerencia containers Docker e distribuições WSL2 para testar scripts e
ferramentas de forma isolada, sem afetar o host Windows. Toda operação roda
via subprocesso e retorna (sucesso, resumo) — projetada para ser chamada
dentro de uma QThread (AutomacaoWorker).

Comando principal: /lab <ação> [argumentos]

Ações:
  - status            — verifica disponibilidade de Docker e WSL2
  - list              — lista containers em execução
  - up <imagem>       — sobe um container isolado (ex.: /lab up python:3.12-slim)
  - exec <id> <cmd>   — executa um comando dentro do container
  - down <id>         — para e remove o container
  - wsl <cmd>         — executa um comando dentro do WSL2 (padrão: uname -a)
"""

import shutil
import subprocess
from typing import Tuple


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _log(mensagem: str, nivel: str = "INFO") -> None:
    print(f"[LAB {nivel:<5}] {mensagem}", flush=True)


def _docker_disponivel() -> bool:
    return shutil.which("docker") is not None


def _wsl_disponivel() -> bool:
    return shutil.which("wsl") is not None


def _rodar(comando: list[str], timeout: int = 120) -> Tuple[bool, str, str]:
    """Executa um comando e devolve (sucesso, stdout, stderr)."""
    try:
        proc = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return False, "", f"Comando não encontrado: {comando[0]}"
    except subprocess.TimeoutExpired:
        return False, "", f"Timeout ({timeout}s) ao executar: {' '.join(comando)}"
    except Exception as exc:
        return False, "", f"Falha ao executar: {exc}"

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    return proc.returncode == 0, stdout, stderr


def _status_lab() -> Tuple[bool, str]:
    linhas = ["CYBER RANGE / VIRTUAL LAB — STATUS", "─" * 40]
    linhas.append(f"Docker: {'DISPONÍVEL' if _docker_disponivel() else 'indisponível'}")
    linhas.append(f"WSL2:   {'DISPONÍVEL' if _wsl_disponivel() else 'indisponível'}")

    if _docker_disponivel():
        ok, out, err = _rodar(["docker", "version", "--format", "{{.Server.Version}}"], timeout=30)
        linhas.append(f"Docker Engine: {out if ok and out else (err or 'não detectado')}")
        ok, out, _ = _rodar(["docker", "ps", "--format", "{{.Names}} ({{.Image}})"], timeout=30)
        containers = [c for c in out.splitlines() if c.strip()] if ok else []
        linhas.append(f"Containers ativos: {len(containers)}")
    if _wsl_disponivel():
        ok, out, _ = _rodar(["wsl", "-l", "-q"], timeout=30)
        distros = [d for d in (out or "").splitlines() if d.strip()] if ok else []
        linhas.append(f"Distros WSL: {', '.join(distros) if distros else 'nenhuma'}")
    return True, "\n".join(linhas)


def _list_containers() -> Tuple[bool, str]:
    if not _docker_disponivel():
        return False, "Docker não está instalado ou não está no PATH."
    ok, out, err = _rodar(
        ["docker", "ps", "--format", "table {{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Names}}"],
        timeout=30,
    )
    if not ok:
        return False, f"Falha ao listar containers: {err or out}"
    return True, f"CONTAINERS ATIVOS\n{'─' * 40}\n{out or '(nenhum)'}"


def _subir_container(imagem: str) -> Tuple[bool, str]:
    if not _docker_disponivel():
        return False, "Docker não está instalado ou não está no PATH."
    if not imagem:
        return False, "Informe a imagem. Ex.: /lab up python:3.12-slim"
    nome = f"jarvis-lab-{abs(hash(imagem)) % 100000}"
    ok, out, err = _rodar(
        ["docker", "run", "-d", "--rm", "--name", nome, imagem, "sleep", "infinity"],
        timeout=180,
    )
    if not ok:
        return False, f"Falha ao subir container '{imagem}': {err or out}"
    cid = (out or "").strip()[:12]
    return True, (
        f"CONTAINER ISOLADO INICIADO\n{'─' * 40}\n"
        f"ID: {cid}\nNome: {nome}\nImagem: {imagem}\n\n"
        f"Execute comandos com: /lab exec {nome} <comando>"
    )


def _executar_no_container(container_id: str, comando: str) -> Tuple[bool, str]:
    if not _docker_disponivel():
        return False, "Docker não está instalado ou não está no PATH."
    if not container_id or not comando:
        return False, "Uso: /lab exec <id> <comando>"
    ok, out, err = _rodar(["docker", "exec", container_id] + comando.split(), timeout=180)
    if not ok:
        return False, f"Falha ao executar no container: {err or out}"
    return True, f"SAÍDA ({container_id})\n{'─' * 40}\n{out or '(sem saída)'}"


def _derrubar_container(container_id: str) -> Tuple[bool, str]:
    if not _docker_disponivel():
        return False, "Docker não está instalado ou não está no PATH."
    if not container_id:
        return False, "Informe o ID/nome do container. Ex.: /lab down <id>"
    _rodar(["docker", "stop", container_id], timeout=60)
    ok, out, err = _rodar(["docker", "rm", container_id], timeout=60)
    if not ok:
        return False, f"Falha ao remover container: {err or out}"
    return True, f"Container '{container_id}' removido com sucesso."


def _executar_wsl(comando: str) -> Tuple[bool, str]:
    if not _wsl_disponivel():
        return False, "WSL não está instalado ou não está no PATH."
    comando = comando or "uname -a"
    ok, out, err = _rodar(["wsl"] + comando.split(), timeout=120)
    if not ok:
        return False, f"Falha ao executar no WSL: {err or out}"
    return True, f"WSL2 — '{comando}'\n{'─' * 40}\n{out or '(sem saída)'}"


# ---------------------------------------------------------------------------
# Interpretador do comando /lab
# ---------------------------------------------------------------------------

_ACOES_LAB = {
    "status": _status_lab,
    "list": _list_containers,
    "up": _subir_container,
    "exec": _executar_no_container,
    "down": _derrubar_container,
    "wsl": _executar_wsl,
}


def interpretar_e_executar(comando: str) -> Tuple[bool, str]:
    """
    Interpreta o corpo do comando `/lab <ação> [argumentos]` e executa.

    Retorna (sucesso, resumo) compatível com o AutomacaoWorker.
    """
    texto = (comando or "").strip()
    if not texto:
        return False, (
            "Uso: /lab <ação> [argumentos]\n"
            "Ações: status | list | up <imagem> | exec <id> <cmd> | "
            "down <id> | wsl <cmd>"
        )

    partes = texto.split(maxsplit=1)
    acao = partes[0].lower()
    resto = partes[1].strip() if len(partes) > 1 else ""

    if acao in ("exec",):
        sub = resto.split(maxsplit=1)
        if len(sub) < 2:
            return False, "Uso: /lab exec <id> <comando>"
        return _executar_no_container(sub[0], sub[1])

    funcao = _ACOES_LAB.get(acao)
    if funcao is None:
        return False, f"Ação desconhecida: '{acao}'. Use /lab para ver as ações."

    _log(f"Executando ação '{acao}' — '{resto[:60]}'")
    return funcao(resto) if resto else funcao()


# ---------------------------------------------------------------------------
# Teste seguro (apenas status, sem subir containers)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S — Cyber Range & Virtual Lab Manager (teste)")
    print("=" * 60)
    ok, resumo = _status_lab()
    print(resumo)
