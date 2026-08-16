"""
global_hotkey.py — Atalho global para abrir/ocultar o J.A.R.V.I.S.

Usa `pynput` para registrar um atalho global de teclado em uma thread de
segundo plano que NÃO bloqueia a GUI Qt. A comunicação com a thread principal
do Qt é feita via Qt Signal (thread-safe / queued connection).

Atalhos registrados:
  - Alt+Space       (primário)
  - Ctrl+Shift+J    (fallback, caso Alt+Space esteja ocupado pelo SO)
"""

from PySide6.QtCore import QObject, Signal


class GlobalHotkeyListener(QObject):
    """
    Monitora um atalho global de teclado e emite `triggered` quando acionado.

    O listener do pynput roda em sua própria thread (daemon); o Signal
    `triggered` é entregue na thread principal do Qt de forma segura.
    """

    triggered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._listener = None
        self._ativo = False

    def iniciar(self) -> bool:
        """
        Inicia o listener em background.

        Retorna True se o atalho foi registrado com sucesso, False caso a
        biblioteca `pynput` esteja indisponível ou o registro falhe.
        """
        if self._ativo:
            return True

        try:
            from pynput import keyboard
        except ImportError:
            return False

        try:
            self._listener = keyboard.GlobalHotKeys({
                "<alt>+<space>": self._emitir,
                "<ctrl>+<shift>+j": self._emitir,
            })
            self._listener.daemon = True
            self._listener.start()
            self._ativo = True
            return True
        except Exception:
            self._listener = None
            self._ativo = False
            return False

    def parar(self) -> None:
        """Encerra o listener de atalho global."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self._ativo = False

    def _emitir(self) -> None:
        """Callback chamado pela thread do pynput."""
        self.triggered.emit()
