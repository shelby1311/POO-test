"""
self_optimizer.py — Code Evolution Engine (J.A.R.V.I.S.)

Analisa estaticamente o código-fonte do projeto em busca de oportunidades de
otimização de memória/CPU e gera um relatório de refatoração em Markdown.

Comando principal: /self-audit [caminho]

A análise é determinística (regex sobre o código-fonte) e funciona offline;
opcionalmente enriquece o relatório com recomendações do LLM local quando o
Ollama está disponível. Nunca modifica arquivos — apenas gera relatórios.
"""

import datetime
import re
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Regras de inspeção
# ---------------------------------------------------------------------------

# Cada regra: (nome, categoria, regex, sugestão, severidade)
REGRAS: list[tuple[str, str, re.Pattern, str, str]] = [
    (
        "string-concat-loop",
        "CPU/memória",
        re.compile(r"\b\w+\s*\+=\s*[\"']"),
        "Concatenar strings com '+=' em loop é O(n²). Use uma lista e '\\n'.join().",
        "média",
    ),
    (
        "range-len",
        "CPU",
        re.compile(r"\brange\s*\(\s*len\s*\("),
        "Use enumerate() em vez de range(len(...)) para iterar com índice.",
        "média",
    ),
    (
        "dict-keys",
        "CPU",
        re.compile(r"\bfor\s+\w+\s+in\s+\w+\.keys\s*\(\s*\)"),
        "Iterar .keys() é redundante: itere o dicionário diretamente (for k in d).",
        "baixa",
    ),
    (
        "sum-list",
        "memória",
        re.compile(r"\b(sum|min|max|any|all)\s*\(\s*\["),
        "Evite criar uma lista intermediária: use expressão geradora (sum(x for x in ...)).",
        "média",
    ),
    (
        "read-whole-file",
        "memória",
        re.compile(r"\.read\s*\(\s*\)\s*$"),
        "Ler o arquivo inteiro em memória pode estourar RAM. Considere iterar por linhas.",
        "baixa",
    ),
    (
        "list-rebuild",
        "CPU/memória",
        re.compile(r"\b\w+\s*=\s*\w+\s*\+\s*\["),
        "Reconstruir uma lista com '+ [x]' em loop é O(n²). Use .append(x).",
        "média",
    ),
    (
        "import-star",
        "manutenção",
        re.compile(r"\bfrom\s+[\w.]+\s+import\s+\*"),
        "Evite 'import *': importe apenas os nomes necessários (clareza e performance).",
        "baixa",
    ),
]

# Extensões de arquivo consideradas no audit.
EXTENSOES = (".py",)


def _log(mensagem: str, nivel: str = "INFO") -> None:
    print(f"[SELF-OPT {nivel:<5}] {mensagem}", flush=True)


def _diretorio_relatorios() -> Path:
    try:
        from config_manager import carregar_configuracao
        data_dir = Path(carregar_configuracao().get("data_directory", "data"))
    except Exception:
        data_dir = Path("data")
    reports = data_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    return reports


def _analisar_arquivo(caminho: Path) -> dict:
    """Analisa um único arquivo Python e devolve suas métricas e achados."""
    try:
        linhas = caminho.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {"arquivo": str(caminho), "erro": str(exc), "linhas": 0, "achados": []}

    achados: list[dict] = []
    for numero, linha in enumerate(linhas, 1):
        for nome, categoria, padrao, sugestao, severidade in REGRAS:
            if padrao.search(linha):
                achados.append({
                    "arquivo": str(caminho),
                    "linha": numero,
                    "trecho": linha.strip()[:120],
                    "regra": nome,
                    "categoria": categoria,
                    "sugestao": sugestao,
                    "severidade": severidade,
                })

    return {
        "arquivo": str(caminho),
        "linhas": len(linhas),
        "achados": achados,
    }


def analisar_projeto(raiz: Optional[str] = None) -> dict:
    """
    Percorre os arquivos .py do projeto e agrega métricas + achados.

    Returns:
        {"raiz", "arquivos", "total_linhas", "achados", "por_severidade"}
    """
    raiz_path = Path(raiz) if raiz else Path(__file__).resolve().parent
    arquivos = sorted(raiz_path.rglob("*.py"))

    # Ignora caches e ambientes virtuais.
    arquivos = [
        p for p in arquivos
        if "__pycache__" not in p.parts
        and ".venv" not in p.parts
        and "venv" not in p.parts
    ]

    resultados = [_analisar_arquivo(p) for p in arquivos]
    achados = []
    total_linhas = 0
    for r in resultados:
        total_linhas += r.get("linhas", 0)
        achados.extend(r.get("achados", []))

    por_severidade = {"alta": 0, "média": 0, "baixa": 0}
    for a in achados:
        sev = a["severidade"]
        por_severidade[sev] = por_severidade.get(sev, 0) + 1

    return {
        "raiz": str(raiz_path),
        "arquivos": len(arquivos),
        "total_linhas": total_linhas,
        "achados": achados,
        "por_severidade": por_severidade,
    }


def gerar_relatorio_markdown(resultado: dict) -> str:
    """Gera o relatório Markdown a partir do resultado da análise."""
    linhas = [
        "# Relatório de Auto-Auditoria de Código",
        "",
        f"- **Data:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Diretório:** {resultado['raiz']}",
        f"- **Arquivos analisados:** {resultado['arquivos']}",
        f"- **Linhas de código:** {resultado['total_linhas']}",
        f"- **Achados:** {len(resultado['achados'])}",
        f"  - alta: {resultado['por_severidade'].get('alta', 0)} · "
        f"média: {resultado['por_severidade'].get('média', 0)} · "
        f"baixa: {resultado['por_severidade'].get('baixa', 0)}",
        "",
        "## Achados de Otimização",
        "",
    ]

    if not resultado["achados"]:
        linhas.append("Nenhuma oportunidade de otimização identificada pelas regras atuais.")
    else:
        por_arquivo: dict[str, list[dict]] = {}
        for a in resultado["achados"]:
            por_arquivo.setdefault(a["arquivo"], []).append(a)

        for arquivo, achados in por_arquivo.items():
            linhas.append(f"### {arquivo}")
            linhas.append("")
            for a in achados:
                linhas.append(
                    f"- **[{a['severidade'].upper()}]** linha {a['linha']} "
                    f"({a['categoria']}, regra `{a['regra']}`)"
                )
                linhas.append(f"  - Código: `{a['trecho']}`")
                linhas.append(f"  - Sugestão: {a['sugestao']}")
            linhas.append("")

    return "\n".join(linhas)


def _enriquecer_com_llm(resumo_achados: str) -> str:
    """Opcional: pede recomendações gerais ao LLM local (texto-livre)."""
    try:
        import brain
    except ImportError:
        return ""
    if not hasattr(brain, "consultar_texto_livre"):
        return ""
    try:
        texto = brain.consultar_texto_livre(
            "Você é um engenheiro de software sênior especialista em performance. "
            "Com base nos achados de uma análise estática, escreva um parágrafo "
            "conciso com recomendações priorizadas de refatoração.",
            resumo_achados,
        )
        return (texto or "").strip()
    except Exception:
        return ""


def executar_auto_auditoria(raiz: Optional[str] = None) -> tuple[bool, str]:
    """
    Executa a auto-auditoria completa e salva o relatório Markdown.

    Returns:
        (sucesso, resumo_para_chat)
    """
    try:
        resultado = analisar_projeto(raiz)
    except Exception as exc:
        return False, f"Falha na auto-auditoria: {exc}"

    relatorio = gerar_relatorio_markdown(resultado)

    caminho = ""
    try:
        nome = datetime.datetime.now().strftime("self_audit_%Y%m%d_%H%M%S.md")
        caminho = str(_diretorio_relatorios() / nome)
        Path(caminho).write_text(relatorio, encoding="utf-8")
    except OSError as exc:
        _log(f"Falha ao salvar relatório: {exc}", "WARNING")

    # Resumo para o chat (mais enxuto).
    sev = resultado["por_severidade"]
    resumo = (
        f"AUTO-AUDITORIA CONCLUÍDA\n{'─' * 40}\n"
        f"Arquivos: {resultado['arquivos']} | Linhas: {resultado['total_linhas']}\n"
        f"Achados: {len(resultado['achados'])} "
        f"(alta={sev.get('alta', 0)}, média={sev.get('média', 0)}, "
        f"baixa={sev.get('baixa', 0)})\n"
    )
    if caminho:
        resumo += f"Relatório: {caminho}\n"

    # Enriquecimento opcional com LLM.
    achados_top = resultado["achados"][:20]
    if achados_top:
        bloco = "\n".join(
            f"- [{a['severidade']}] {Path(a['arquivo']).name}:{a['linha']} → {a['sugestao']}"
            for a in achados_top
        )
        recomendacao = _enriquecer_com_llm(
            "Achados da análise estática:\n" + bloco
        )
        if recomendacao:
            resumo += f"\nRECOMENDAÇÕES (LLM):\n{recomendacao}"

    return True, resumo


# ---------------------------------------------------------------------------
# Teste direto
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S — Code Evolution Engine (teste)")
    print("=" * 60)
    ok, resumo = executar_auto_auditoria()
    print(resumo)
