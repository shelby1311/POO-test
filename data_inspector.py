"""
data_inspector.py — Cyber Sandbox & Inspector (inspeção estática de scripts).

Analisa arquivos (.ps1, .bat, .py, .exe) em busca de padrões suspeitos:
obfuscamento, IPs/domínios externos hardcoded, execuções dinâmicas
(Invoke-Expression/eval/exec/subprocess) e modificações críticas no Registro
do Windows.

Dependências: biblioteca padrão.
"""

import re
from pathlib import Path

# ── Padrões suspeitos ──
_PADRAO_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_PADRAO_URL = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)

_PADRAO_EXEC_DINAMICA = re.compile(
    r"(Invoke-Expression|IEX\b|eval\s*\(|exec\s*\(|os\.system\s*\(|"
    r"subprocess\.|Start-Process|powershell\s+.*-EncodedCommand|"
    r"FromBase64String|atob\s*\()",
    re.IGNORECASE,
)

_PADRAO_REGISTRO = re.compile(
    r"(reg\s+add|Set-ItemProperty|New-ItemProperty|Remove-ItemProperty|"
    r"HKCU|HKLM|HKEY_LOCAL_MACHINE|HKEY_CURRENT_USER|Set-Item\s)",
    re.IGNORECASE,
)

_PADRAO_OBFUSCACAO = re.compile(
    r"(-enc\b|-EncodedCommand|FromBase64String|base64|StringFromCharCode|"
    r"\\x[0-9a-fA-F]{2}|[A-Za-z0-9+/]{40,}={0,2})",
    re.IGNORECASE,
)

_REDES_INTERNAS = ("127.", "10.", "192.168.", "172.", "0.", "169.254.")


def _detectar_suspeitos(texto: str) -> list[str]:
    """Detecta padrões suspeitos em um conteúdo textual."""
    suspeitos: list[str] = []

    if _PADRAO_EXEC_DINAMICA.search(texto):
        suspeitos.append(
            "Execução dinâmica detectada (Invoke-Expression / IEX / eval / exec / subprocess)."
        )
    if _PADRAO_REGISTRO.search(texto):
        suspeitos.append(
            "Modificação crítica no Registro do Windows (reg add / Set-ItemProperty / HKLM / HKCU)."
        )

    ips = _PADRAO_IP.findall(texto)
    ips_externos = sorted({ip for ip in ips if not ip.startswith(_REDES_INTERNAS)})
    if ips_externos:
        suspeitos.append(f"IP(s) externo(s) hardcoded: {', '.join(ips_externos[:5])}.")

    urls = sorted(set(_PADRAO_URL.findall(texto)))
    if urls:
        suspeitos.append(f"URL(s) externa(s) hardcoded: {', '.join(urls[:5])}.")

    if _PADRAO_OBFUSCACAO.search(texto):
        suspeitos.append("Possível ofuscamento (Base64 / EncodedCommand / hex).")

    return suspeitos


def analisar_arquivo(caminho: str) -> dict:
    """
    Analisa estaticamente um arquivo e retorna um dicionário:
      {arquivo, seguro, suspeitos, [erro]}.
    """
    arq = Path(caminho)
    if not arq.is_file():
        return {"arquivo": str(arq), "seguro": True, "suspeitos": [], "erro": "Arquivo não encontrado."}

    extensao = arq.suffix.lower()
    suspeitos: list[str] = []

    if extensao == ".exe":
        try:
            raw = arq.read_bytes()
            texto = raw.decode("latin-1", errors="ignore")
        except OSError as exc:
            return {"arquivo": str(arq), "seguro": False, "suspeitos": [f"Falha ao ler binário: {exc}"]}
        suspeitos = _detectar_suspeitos(texto)
        if not suspeitos:
            suspeitos.append("Arquivo binário (.exe) — análise limitada a strings ASCII.")
    else:
        try:
            conteudo = arq.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"arquivo": str(arq), "seguro": False, "suspeitos": [f"Falha ao ler arquivo: {exc}"]}
        suspeitos = _detectar_suspeitos(conteudo)

    return {
        "arquivo": str(arq),
        "seguro": len(suspeitos) == 0,
        "suspeitos": suspeitos,
    }


def inspecionar_pasta_downloads() -> list[dict]:
    """Varre `data/downloads/` e analisa arquivos .ps1/.bat/.py/.exe."""
    from config_manager import carregar_configuracao

    config = carregar_configuracao()
    downloads = Path(config.get("data_directory", "data")) / "downloads"
    if not downloads.is_dir():
        return []

    extensoes = {".ps1", ".bat", ".py", ".exe"}
    resultados: list[dict] = []
    for arq in sorted(downloads.rglob("*")):
        if arq.is_file() and arq.suffix.lower() in extensoes:
            resultados.append(analisar_arquivo(str(arq)))
    return resultados


# ---------------------------------------------------------------------------
# Execução direta (teste)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S — Teste do Data Inspector")
    print("=" * 60)

    for r in inspecionar_pasta_downloads():
        status = "VERIFICADO - SEGURO" if r.get("seguro") else "ALERTA DE RISCO"
        print(f"\n[{status}] {r['arquivo']}")
        for s in r.get("suspeitos", []):
            print(f"   • {s}")

    print("\nTeste concluído.")
