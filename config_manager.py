"""
config_manager.py — Gerenciamento de configuração do J.A.R.V.I.S.

Responsável por carregar, validar e persistir o arquivo config.json,
bem como preparar o ambiente de execução (diretórios necessários).
"""

import datetime
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

CONFIG_FILE_NAME = "config.json"

CONFIG_PADRAO: dict = {
    "cpu_threads": 4,
    "gpu_layers": 20,
    "max_ram_gb": 8,
    "data_directory": str(Path(__file__).resolve().parent / "data"),
    "hotkey_pause": "esc",
    "log_level": "INFO",
}

SUBDIRETORIOS_DATA = ["logs", "memory", "downloads"]

# ---------------------------------------------------------------------------
# Funções internas
# ---------------------------------------------------------------------------


def _caminho_config() -> Path:
    """Devolve o caminho absoluto do config.json (mesmo diretório deste script)."""
    return Path(__file__).resolve().parent / CONFIG_FILE_NAME


def _log(mensagem: str, nivel: str = "INFO") -> None:
    """Emite uma mensagem de log formatada no terminal."""
    print(f"[{nivel.upper():<5}] {mensagem}")


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def carregar_configuracao(caminho: Path | None = None) -> dict:
    """
    Carrega o arquivo config.json e devolve um dicionário com as configurações.

    Se o arquivo não existir, cria-o a partir do CONFIG_PADRAO.
    Em caso de JSON inválido, emite um alerta e retorna o padrão.
    """
    if caminho is None:
        caminho = _caminho_config()

    if not caminho.exists():
        _log(
            f"Arquivo de configuração não encontrado em {caminho}. "
            "Criando com valores padrão.",
            "WARNING",
        )
        try:
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(CONFIG_PADRAO, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            _log(f"Falha ao criar config.json: {exc}", "ERROR")
            return dict(CONFIG_PADRAO)
        return dict(CONFIG_PADRAO)

    try:
        with open(caminho, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        _log(f"Erro ao ler config.json: {exc}. Usando valores padrão.", "ERROR")
        return dict(CONFIG_PADRAO)

    # Garante que todas as chaves esperadas existam (merge com padrão)
    completo = dict(CONFIG_PADRAO)
    completo.update(config)
    return completo


def salvar_configuracao(novas_configs: dict, caminho: Path | None = None) -> bool:
    """
    Atualiza o config.json com os valores fornecidos em *novas_configs*.

    Apenas as chaves presentes em CONFIG_PADRAO são persistidas; chaves
    desconhecidas são ignoradas com um aviso de log.

    Retorna True em caso de sucesso, False em caso de falha.
    """
    if caminho is None:
        caminho = _caminho_config()

    # 1. Carrega a configuração atual (garante merge com padrão)
    atual = carregar_configuracao(caminho)

    # 2. Filtra apenas chaves conhecidas
    validas = {}
    ignoradas = []
    for chave, valor in novas_configs.items():
        if chave in CONFIG_PADRAO:
            validas[chave] = valor
        else:
            ignoradas.append(chave)

    if ignoradas:
        _log(
            f"Chaves desconhecidas ignoradas: {', '.join(ignoradas)}",
            "WARNING",
        )

    if not validas:
        _log("Nenhuma chave válida fornecida para salvar.", "WARNING")
        return False

    # 3. Aplica as alterações
    atual.update(validas)

    # 4. Persiste em disco
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(atual, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        _log(f"Falha ao escrever config.json: {exc}", "ERROR")
        return False

    _log(f"Configuração salva com sucesso. Chaves atualizadas: {list(validas)}")
    return True


def validar_e_preparar_ambiente(config: dict | None = None) -> bool:
    """
    Verifica a existência do data_directory e cria a estrutura de diretórios
    necessária (logs/, memory/, downloads/).

    Retorna True se o ambiente está pronto, False em caso de falha.
    """
    if config is None:
        config = carregar_configuracao()

    data_dir = Path(config.get("data_directory", CONFIG_PADRAO["data_directory"]))

    _log(f"Preparando ambiente em: {data_dir}")

    # Cria o diretório raiz de dados, se necessário
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _log(f"Falha ao criar data_directory '{data_dir}': {exc}", "ERROR")
        return False

    # Cria as subpastas esperadas
    for sub in SUBDIRETORIOS_DATA:
        sub_path = data_dir / sub
        try:
            sub_path.mkdir(parents=True, exist_ok=True)
            _log(f"  Subdiretório OK: {sub_path}", "DEBUG")
        except OSError as exc:
            _log(f"Falha ao criar subdiretório '{sub_path}': {exc}", "ERROR")
            return False

    _log("Ambiente validado e pronto.")
    return True


# ---------------------------------------------------------------------------
# Diagnóstico de hardware e auto-configuração para Llama 3.2
# ---------------------------------------------------------------------------


def analisar_hardware_maquina() -> dict:
    """
    Diagnostica o hardware da máquina e calcula as configurações recomendadas
    para executar o Llama 3.2 com máximo desempenho local.

    Usa psutil (CPU/RAM) e GPUtil (GPU/VRAM). Se alguma dependência não estiver
    instalada ou falhar, os campos correspondentes são preenchidos com valores
    neutros e a coleta segue adiante.

    Returns:
        Dict com as chaves:
          - ram_total_gb, ram_disponivel_gb
          - cpu_cores_fisicos, cpu_threads_logicos
          - gpus: lista de {modelo, vram_total_gb, vram_livre_gb, load}
          - recomendacoes: {cpu_threads, gpu_layers, max_ram_gb, vram_target_gb,
                            gpu_offload, descricao}
    """
    info: dict = {
        "ram_total_gb": 0.0,
        "ram_disponivel_gb": 0.0,
        "cpu_cores_fisicos": 0,
        "cpu_threads_logicos": 0,
        "gpus": [],
        "recomendacoes": {},
    }

    # ── CPU / RAM via psutil ──
    try:
        import psutil
    except ImportError:
        psutil = None

    if psutil is not None:
        try:
            vm = psutil.virtual_memory()
            info["ram_total_gb"] = round(vm.total / (1024 ** 3), 2)
            info["ram_disponivel_gb"] = round(vm.available / (1024 ** 3), 2)
            info["cpu_cores_fisicos"] = psutil.cpu_count(logical=False) or 0
            info["cpu_threads_logicos"] = psutil.cpu_count(logical=True) or 0
        except Exception as exc:
            _log(f"psutil: falha ao coletar CPU/RAM — {exc}", "WARNING")

    # ── GPU / VRAM via GPUtil ──
    try:
        import GPUtil
    except ImportError:
        GPUtil = None

    if GPUtil is not None:
        try:
            for gpu in GPUtil.getGPUs():
                info["gpus"].append({
                    "modelo": gpu.name,
                    "vram_total_gb": round(gpu.memoryTotal / 1024.0, 2),
                    "vram_livre_gb": round(gpu.memoryFree / 1024.0, 2),
                    "load": round(gpu.load * 100.0, 1),
                })
        except Exception as exc:
            _log(f"GPUtil: falha ao coletar GPU — {exc}", "WARNING")

    info["recomendacoes"] = _calcular_recomendacoes_llama(info)
    return info


def _calcular_recomendacoes_llama(info: dict) -> dict:
    """
    Calcula configurações recomendadas para rodar o Llama 3.2 (3B) com máximo
    desempenho, a partir dos dados coletados por analisar_hardware_maquina().
    """
    ram_total = info.get("ram_total_gb", 0.0) or 0.0
    cores_fisicos = info.get("cpu_cores_fisicos", 0) or 0
    threads_logicos = info.get("cpu_threads_logicos", 0) or 0
    gpus = info.get("gpus", []) or []

    # CPU threads: prioriza núcleos físicos (evita overhead de hyper-threading).
    # O modelo 3B satura por volta de 4–8 threads; acima disso o ganho é marginal.
    base_threads = cores_fisicos or threads_logicos or 4
    cpu_threads = max(2, min(base_threads, 8))

    # RAM: reserva ~2 GB para o SO e demais processos; aloca o restante até um
    # teto útil para o modelo 3B quantizado.
    ram_utilizavel = max(1.0, ram_total - 2.0)
    max_ram_gb = max(2, min(int(ram_utilizavel), 16))

    # GPU: direciona camadas para VRAM conforme a memória disponível.
    gpu_layers = 0
    vram_target_gb = 0.0
    if gpus:
        vram_total = gpus[0].get("vram_total_gb", 0.0) or 0.0
        if vram_total >= 8.0:
            gpu_layers = 40          # offload total na GPU
        elif vram_total >= 6.0:
            gpu_layers = 32
        elif vram_total >= 4.0:
            gpu_layers = 24
        elif vram_total >= 2.0:
            gpu_layers = 12
        else:
            gpu_layers = 0           # VRAM insuficiente → execução em CPU
        # Reserva margem de VRAM para o SO/monitor.
        vram_target_gb = round(min(vram_total, 4.0), 2)

    gpu_offload = gpu_layers > 0

    if gpu_offload:
        descricao = (
            f"GPU '{gpus[0].get('modelo', 'desconhecida')}' detectada "
            f"({gpus[0].get('vram_total_gb', 0.0):.2f} GB VRAM). "
            f"{gpu_layers} camadas direcionadas à VRAM."
        )
    else:
        descricao = (
            "Sem GPU com VRAM suficiente detectada — execução do Llama 3.2 "
            "totalmente em CPU."
        )

    return {
        "cpu_threads": cpu_threads,
        "gpu_layers": gpu_layers,
        "max_ram_gb": max_ram_gb,
        "vram_target_gb": vram_target_gb,
        "gpu_offload": gpu_offload,
        "descricao": descricao,
    }


def auto_configurar_hardware(caminho: Path | None = None) -> dict:
    """
    Analisa o hardware e persiste as configurações recomendadas no config.json.

    Atualiza apenas as chaves de desempenho (cpu_threads, gpu_layers,
    max_ram_gb) com os valores calculados por analisar_hardware_maquina().

    Returns:
        O dicionário de recomendações aplicadas (ou {} em caso de falha).
    """
    info = analisar_hardware_maquina()
    recomendacoes = info.get("recomendacoes", {})
    if not recomendacoes:
        _log("Sem recomendações de hardware para aplicar.", "WARNING")
        return {}

    novas = {
        "cpu_threads": recomendacoes.get("cpu_threads"),
        "gpu_layers": recomendacoes.get("gpu_layers"),
        "max_ram_gb": recomendacoes.get("max_ram_gb"),
    }

    if salvar_configuracao(novas, caminho):
        _log(
            "Auto-configuração de hardware aplicada: "
            f"cpu_threads={novas['cpu_threads']}, "
            f"gpu_layers={novas['gpu_layers']}, "
            f"max_ram_gb={novas['max_ram_gb']}.",
            "INFO",
        )
        return recomendacoes

    _log("Falha ao persistir a auto-configuração de hardware.", "ERROR")
    return {}


# ---------------------------------------------------------------------------
# Paleta de comandos rápidos
# ---------------------------------------------------------------------------

COMANDOS_PALETTE: list[dict] = [
    {
        "nome": "/git-sync",
        "descricao": "git add . + commit (mensagem via IA) + push",
        "categoria": "git",
    },
    {
        "nome": "/cleanup",
        "descricao": "Limpa arquivos temporários de data/downloads e cache",
        "categoria": "sistema",
    },
    {
        "nome": "/net-check",
        "descricao": "Diagnóstico de rede (ping, latência e portas abertas)",
        "categoria": "rede",
    },
    {
        "nome": "/autofix",
        "descricao": "Corrige automaticamente um código colado no chat",
        "categoria": "código",
    },
    {
        "nome": "/research",
        "descricao": "Deep Research: pesquisa profunda e relatório Markdown",
        "categoria": "pesquisa",
    },
    {
        "nome": "/inspect",
        "descricao": "Inspeção de segurança dos scripts em downloads",
        "categoria": "segurança",
    },
    {
        "nome": "/metrics",
        "descricao": "Resumo das métricas de desenvolvimento",
        "categoria": "telemetria",
    },
    {
        "nome": "/web",
        "descricao": "Automação web headless (pesquisar, acessar, baixar, preencher, screenshot)",
        "categoria": "automação",
    },
    {
        "nome": "/mode",
        "descricao": "Perfis de trabalho (dev, focus, gaming)",
        "categoria": "sistema",
    },
    {
        "nome": "/snap",
        "descricao": "Captura de tela + análise de contexto visual",
        "categoria": "visão",
    },
    {
        "nome": "/lab",
        "descricao": "Cyber Range: containers Docker/WSL2 isolados",
        "categoria": "laboratório",
    },
    {
        "nome": "/self-audit",
        "descricao": "Auto-auditoria de código (otimizações memória/CPU)",
        "categoria": "código",
    },
    {
        "nome": "/record",
        "descricao": "Grava áudio, transcreve (Whisper) e resume reunião",
        "categoria": "áudio",
    },
    {
        "nome": "/db-schema",
        "descricao": "Inspeciona schema de banco (SQLite/PostgreSQL/MySQL)",
        "categoria": "banco de dados",
    },
    {
        "nome": "/db-query",
        "descricao": "Executa query somente leitura",
        "categoria": "banco de dados",
    },
    {
        "nome": "/db-ask",
        "descricao": "Gera SQL a partir de linguagem natural",
        "categoria": "banco de dados",
    },
    {
        "nome": "/net-map",
        "descricao": "Varre a rede local e mapeia dispositivos/portas",
        "categoria": "rede",
    },
]


def obter_comandos_palette() -> list[dict]:
    """Devolve a lista de comandos rápidos pré-configurados."""
    return [dict(c) for c in COMANDOS_PALETTE]


# ---------------------------------------------------------------------------
# Telemetria de desenvolvimento (métricas de uso)
# ---------------------------------------------------------------------------

def _diretorio_metricas() -> Path:
    config = carregar_configuracao()
    data_dir = Path(config.get("data_directory", "data"))
    metrics_dir = data_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    return metrics_dir


def _arquivo_metricas_hoje() -> Path:
    hoje = datetime.date.today().isoformat()
    return _diretorio_metricas() / f"metrics_{hoje}.json"


def _carregar_metricas_hoje() -> dict:
    arq = _arquivo_metricas_hoje()
    if arq.exists():
        try:
            return json.loads(arq.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "comandos_executados": 0,
        "pesquisas": 0,
        "commits_git": 0,
        "amostras_ram": [],
        "amostras_vram": [],
    }


def _salvar_metricas_hoje(metricas: dict) -> None:
    try:
        _arquivo_metricas_hoje().write_text(
            json.dumps(metricas, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        _log(f"Falha ao salvar métricas: {exc}", "ERROR")


def registrar_evento_telemetria(tipo: str, quantidade: int = 1) -> None:
    """Registra um evento de uso (comando, pesquisa, commit)."""
    chave = {
        "comando": "comandos_executados",
        "pesquisa": "pesquisas",
        "commit": "commits_git",
    }.get(tipo)
    if not chave:
        return
    metricas = _carregar_metricas_hoje()
    metricas[chave] = int(metricas.get(chave, 0)) + quantidade
    _salvar_metricas_hoje(metricas)


def registrar_amostra_hardware(ram: float, vram) -> None:
    """Registra uma amostra de uso de RAM/VRAM (média diária)."""
    metricas = _carregar_metricas_hoje()
    metricas.setdefault("amostras_ram", []).append(round(ram, 1))
    if vram is not None:
        metricas.setdefault("amostras_vram", []).append(round(vram, 1))
    metricas["amostras_ram"] = metricas["amostras_ram"][-2000:]
    metricas["amostras_vram"] = metricas["amostras_vram"][-2000:]
    _salvar_metricas_hoje(metricas)


def obter_resumo_metricas() -> dict:
    """Resumo das métricas de desenvolvimento (hoje + total + médias)."""
    metricas = _carregar_metricas_hoje()
    ram = metricas.get("amostras_ram", [])
    vram = metricas.get("amostras_vram", [])
    media_ram = round(sum(ram) / len(ram), 1) if ram else 0.0
    media_vram = round(sum(vram) / len(vram), 1) if vram else None

    total = {"comandos": 0, "pesquisas": 0, "commits": 0}
    for arq in _diretorio_metricas().glob("metrics_*.json"):
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        total["comandos"] += int(d.get("comandos_executados", 0))
        total["pesquisas"] += int(d.get("pesquisas", 0))
        total["commits"] += int(d.get("commits_git", 0))

    return {
        "hoje": {
            "comandos": metricas.get("comandos_executados", 0),
            "pesquisas": metricas.get("pesquisas", 0),
            "commits": metricas.get("commits_git", 0),
        },
        "total": total,
        "media_ram": media_ram,
        "media_vram": media_vram,
    }


# ---------------------------------------------------------------------------
# Autocorreção do ambiente (self-healing)
# ---------------------------------------------------------------------------

def verificar_porta_ollama(host: str = "localhost", port: int = 11434,
                           timeout: float = 1.5) -> bool:
    """Verifica se a porta do Ollama está respondendo."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def reiniciar_servico_ollama() -> bool:
    """Encerra processos órfãos do Ollama e reinicia o serviço em background."""
    for proc in ("ollama.exe", "ollama_llama_server.exe", "ollama_runner.exe"):
        subprocess.run(
            f"taskkill /F /IM {proc}",
            shell=True, capture_output=True, text=True,
        )
    time.sleep(1)
    try:
        import brain
        return brain.garantir_servico_ollama()
    except Exception as exc:
        _log(f"Falha ao reiniciar Ollama: {exc}", "ERROR")
        return False


def verificar_espaco_disco(limiar_percent: float = 5.0) -> dict:
    """Verifica o espaço livre em C: e D:. Retorna um dict por unidade."""
    resultado: dict = {}
    for drive in ("C:\\", "D:\\"):
        try:
            uso = shutil.disk_usage(drive)
            percent_livre = uso.free / uso.total * 100.0
            resultado[drive] = {
                "total_gb": round(uso.total / (1024 ** 3), 1),
                "livre_gb": round(uso.free / (1024 ** 3), 1),
                "percent_livre": round(percent_livre, 1),
                "critico": percent_livre < limiar_percent,
            }
        except OSError:
            continue
    return resultado


def expurgar_cache() -> tuple[bool, str]:
    """Remove pastas __pycache__ e arquivos temporários do projeto."""
    raiz = Path(__file__).resolve().parent
    pycache = 0
    for p in raiz.rglob("__pycache__"):
        try:
            shutil.rmtree(p)
            pycache += 1
        except OSError:
            pass

    temp = raiz / "data" / "temp"
    temp_removidos = 0
    if temp.is_dir():
        for item in temp.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                temp_removidos += 1
            except OSError:
                pass

    return True, (
        f"Expurgo concluído: {pycache} cache(s) __pycache__, "
        f"{temp_removidos} item(ns) temporários removidos."
    )


# ---------------------------------------------------------------------------
# Execução direta (teste / diagnóstico)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S — Teste do ConfigManager")
    print("=" * 60)

    # 1. Carregar configuração
    cfg = carregar_configuracao()
    print("\n[1] Configuração carregada:")
    for chave, valor in cfg.items():
        print(f"    {chave}: {valor}")

    # 2. Validar e preparar ambiente
    print("\n[2] Validando e preparando ambiente...")
    if validar_e_preparar_ambiente(cfg):
        print("    Ambiente OK.")
    else:
        print("    [ERRO] Falha na preparação do ambiente.")
        sys.exit(1)

    # 3. Testar salvamento de uma alteração
    print("\n[3] Testando salvar_configuracao (alterando log_level para DEBUG)...")
    if salvar_configuracao({"log_level": "DEBUG"}):
        # Recarrega para confirmar
        cfg2 = carregar_configuracao()
        print(f"    log_level após salvamento: {cfg2.get('log_level')}")

    # 4. Restaurar valor original
    print("\n[4] Restaurando log_level para INFO...")
    salvar_configuracao({"log_level": "INFO"})

    # 5. Diagnóstico de hardware (somente leitura)
    print("\n[5] Diagnóstico de hardware:")
    hw = analisar_hardware_maquina()
    print(f"    RAM total: {hw['ram_total_gb']} GB | "
          f"disponível: {hw['ram_disponivel_gb']} GB")
    print(f"    CPU: {hw['cpu_cores_fisicos']} cores / "
          f"{hw['cpu_threads_logicos']} threads")
    for g in hw["gpus"]:
        print(f"    GPU: {g['modelo']} — {g['vram_total_gb']} GB VRAM")
    print(f"    Recomendações: {hw['recomendacoes']}")

    print("\nTeste concluído com sucesso.")
