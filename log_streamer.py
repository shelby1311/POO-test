"""
log_streamer.py — Live Log Streamer (monitor de erros em tempo real).

Implementa LogStreamerWorker (QThread) que acompanha arquivos de log ou a
saída de um processo ativo, emitindo sinais Qt com classificação de severidade
(ERRO, AVISO, INFO) e detectando blocos de erro/stack trace para envio ao
diagnóstico do brain.py.

Dependências: PySide6 + biblioteca padrão.
"""

import re
import subprocess
import time

from PySide6.QtCore import QThread, Signal

# ── Padrões de severidade ──
_PADRAO_ERRO = re.compile(
    r"\b(error|erro|exception|traceback|fatal|critical|failed|falha)\b",
    re.IGNORECASE,
)
_PADRAO_AVISO = re.compile(r"\b(warning|warn|aviso|alerta|deprecat)\w*\b", re.IGNORECASE)


def classificar_severidade(linha: str) -> str:
    """Classifica uma linha de log em 'ERRO', 'AVISO' ou 'INFO'."""
    if _PADRAO_ERRO.search(linha):
        return "ERRO"
    if _PADRAO_AVISO.search(linha):
        return "AVISO"
    return "INFO"


class LogStreamerWorker(QThread):
    """
    Monitora um arquivo de log (modo tail) ou a saída de um processo ativo.

    Sinais:
      - lineRead(str, str): (linha, severidade)
      - errorChunk(str): bloco de erro/stack trace detectado
    """

    lineRead = Signal(str, str)
    errorChunk = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._caminho: str | None = None
        self._comando: list | None = None
        self._parar = False
        self._buffer_erro: list[str] = []

    # ── Configuração ──

    def monitorar_arquivo(self, caminho: str) -> None:
        """Configura o worker para seguir (tail) um arquivo de log."""
        self._caminho = caminho
        self._comando = None

    def monitorar_processo(self, comando: list) -> None:
        """Configura o worker para ler a saída (stdout/stderr) de um processo."""
        self._comando = comando
        self._caminho = None

    def parar(self) -> None:
        """Solicita a parada da thread."""
        self._parar = True
        self.wait(3000)

    # ── Execução ──

    def run(self) -> None:
        self._parar = False
        self._buffer_erro = []
        try:
            if self._caminho:
                self._acompanhar_arquivo(self._caminho)
            elif self._comando:
                self._acompanhar_processo(self._comando)
        except Exception as exc:
            self.lineRead.emit(f"[LogStreamer] Erro interno: {exc}", "ERRO")
        finally:
            self._flush_erro()

    def _acompanhar_arquivo(self, caminho: str) -> None:
        try:
            with open(caminho, "r", encoding="utf-8", errors="replace") as f:
                f.seek(0, 2)  # começa a partir do fim (tail)
                while not self._parar:
                    linha = f.readline()
                    if linha:
                        self._processar_linha(linha.rstrip("\n"))
                    else:
                        time.sleep(0.2)
        except FileNotFoundError:
            self.lineRead.emit(f"[LogStreamer] Arquivo não encontrado: {caminho}", "ERRO")
        except OSError as exc:
            self.lineRead.emit(f"[LogStreamer] Falha ao ler arquivo: {exc}", "ERRO")

    def _acompanhar_processo(self, comando: list) -> None:
        try:
            proc = subprocess.Popen(
                comando,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            self.lineRead.emit(f"[LogStreamer] Falha ao iniciar processo: {exc}", "ERRO")
            return

        if proc.stdout is None:
            return

        for linha in proc.stdout:
            if self._parar:
                proc.terminate()
                break
            self._processar_linha(linha.rstrip("\n"))

    # ── Processamento de linhas ──

    def _processar_linha(self, linha: str) -> None:
        if not linha.strip():
            return
        severidade = classificar_severidade(linha)
        self.lineRead.emit(linha, severidade)

        if severidade == "ERRO":
            self._buffer_erro.append(linha)
            # Evita buffer infinito em logs muito verbosos.
            if len(self._buffer_erro) >= 25:
                self._flush_erro()
        else:
            self._flush_erro()

    def _flush_erro(self) -> None:
        """Emite o bloco de erro acumulado (stack trace) e limpa o buffer."""
        if self._buffer_erro:
            chunk = "\n".join(self._buffer_erro)
            self._buffer_erro = []
            self.errorChunk.emit(chunk)
