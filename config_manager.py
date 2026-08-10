"""
config_manager.py — Gerenciamento de configuração do J.A.R.V.I.S.

Responsável por carregar, validar e persistir o arquivo config.json,
bem como preparar o ambiente de execução (diretórios necessários).
"""

import json
import os
import sys
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

    print("\nTeste concluído com sucesso.")
