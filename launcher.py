"""
launcher.py — Interface HUD da SALLES INDUSTRIES v2.0 (Quantum OS / Sci-Fi)

Interface gráfica cyberpunk com esfera 3D de partículas reativas (Salles Core 3D),
painel de configurações, console de chat textual interativo e inicialização
unificada em segundo plano.

Design Dark Glassmorphism com bordas ciano, transições de cor reativas ao estado
do assistente (Ciano → Verde Neon / Azul Elétrico) e animação fluida a 60 FPS.

Capacidades:
  - Salles Core 3D: partículas projetadas nos eixos X, Y, Z com rotação contínua
  - Reatividade a estado: pulsa e transiciona cores conforme o processamento
  - Inicialização unificada em segundo plano (config, kill_switch, brain, hardware)
  - Chat Console Multithread via QThread (processamento assíncrono)
  - Histórico estilizado ([VOCÊ] ciano, [J.A.R.V.I.S.] verde neon)
  - Suporte a todas as ações expandidas (analisar_codigo, diagnostico_windows, etc.)

Requer: PySide6, config_manager (projeto J.A.R.V.I.S.)
"""

import math
import os
import random
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QTimer,
    QRectF,
    QPointF,
    Signal,
    Slot,
    QPropertyAnimation,
    QEasingCurve,
    QThread,
    QMutex,
    QMutexLocker,
)
from PySide6.QtGui import (
    QPainter,
    QColor,
    QBrush,
    QPen,
    QFont,
    QFontDatabase,
    QRadialGradient,
    QLinearGradient,
    QConicalGradient,
    QPainterPath,
    QAction,
    QTextCursor,
    QIcon,
    QPixmap,
    QShortcut,
    QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QSlider,
    QLabel,
    QComboBox,
    QGroupBox,
    QFrame,
    QSpacerItem,
    QSizePolicy,
    QMessageBox,
    QTabWidget,
    QTextEdit,
    QLineEdit,
    QScrollBar,
    QProgressBar,
    QSystemTrayIcon,
    QMenu,
    QDialog,
    QListWidget,
    QListWidgetItem,
)

# ---------------------------------------------------------------------------
# Tenta importar config_manager (ajusta path se necessário)
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

try:
    import config_manager
except ImportError:
    config_manager = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Tenta importar módulos do núcleo J.A.R.V.I.S.
# ---------------------------------------------------------------------------

try:
    import brain
except ImportError:
    brain = None  # type: ignore[assignment]

try:
    import pc_controller
except ImportError:
    pc_controller = None  # type: ignore[assignment]

try:
    import web_learner
except ImportError:
    web_learner = None  # type: ignore[assignment]

try:
    import kill_switch
except ImportError:
    kill_switch = None  # type: ignore[assignment]

try:
    import hud_widgets
except ImportError:
    hud_widgets = None  # type: ignore[assignment]

try:
    import security
except ImportError:
    security = None  # type: ignore[assignment]

try:
    import cyber_defense
except ImportError:
    cyber_defense = None  # type: ignore[assignment]

try:
    import web_automation
except ImportError:
    web_automation = None  # type: ignore[assignment]

try:
    import vision_engine
except ImportError:
    vision_engine = None  # type: ignore[assignment]

try:
    import virtual_lab
except ImportError:
    virtual_lab = None  # type: ignore[assignment]

try:
    import self_optimizer
except ImportError:
    self_optimizer = None  # type: ignore[assignment]

try:
    import meeting_summarizer
except ImportError:
    meeting_summarizer = None  # type: ignore[assignment]

try:
    import database_assistant
except ImportError:
    database_assistant = None  # type: ignore[assignment]

try:
    import network_mapper
except ImportError:
    network_mapper = None  # type: ignore[assignment]

try:
    import multimodal_ingestor
except ImportError:
    multimodal_ingestor = None  # type: ignore[assignment]

try:
    from global_hotkey import GlobalHotkeyListener
except ImportError:
    GlobalHotkeyListener = None  # type: ignore[assignment]


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTES DE ESTILO HUD — DARK GLASSMORPHISM
# ═══════════════════════════════════════════════════════════════════════════

# Paleta "Dark Futuristic Command Center / Cyberpunk HUD" (SALLES INDUSTRIES)
COLOR_BG = "#080C14"            # fundo quase preto azul-marinho
COLOR_BG_DEEP = "#101D2B"       # azul profundo
COLOR_PANEL_BG = "rgba(16, 29, 43, 0.72)"   # vidro escuro translúcido
COLOR_PANEL_BG_SOLID = "#0C141E"

COLOR_CYAN = "#18DDE5"          # ciano neon
COLOR_TURQUOISE = "#19BFC5"     # turquesa
COLOR_MAGENTA = "#E22F91"       # magenta neon
COLOR_PURPLE = "#7B3FA8"        # roxo
COLOR_NEON_BLUE = "#2499D8"     # azul elétrico
COLOR_BLUE = "#2499D8"
COLOR_ELECTRIC_BLUE = "#2499D8"

COLOR_GREEN = "#19BFC5"         # turquesa (estado ativo/ok)
COLOR_NEON_GREEN = "#18DDE5"
COLOR_ORANGE = "#FF804D"        # laranja
COLOR_RED = "#FF5C58"           # coral (alerta/crítico)
COLOR_CORAL = "#FF5C58"

COLOR_BORDER = "rgba(24, 221, 229, 0.22)"
COLOR_BORDER_HOVER = "rgba(24, 221, 229, 0.55)"
COLOR_BORDER_SOFT = "rgba(24, 221, 229, 0.16)"
COLOR_BORDER_ACTIVE = "rgba(24, 221, 229, 0.55)"

COLOR_TEXT = "#A8D5D8"          # texto principal (azulado claro)
COLOR_TEXT_SECONDARY = "#50777D"  # texto secundário
COLOR_TEXT_BRIGHT = "#C9E8EA"
COLOR_TEXT_DIM = "#3A4F55"

FONT_FAMILY = "Consolas, 'Segoe UI', 'Courier New', monospace"

STYLESHEET = f"""
/* ===================== GLOBAL ===================== */
QMainWindow {{
    background: qradialgradient(cx:0.35, cy:0.25, radius:1.4,
        fx:0.35, fy:0.25, stop:0 {COLOR_BG_DEEP}, stop:1 {COLOR_BG});
}}

QWidget {{
    color: {COLOR_TEXT};
    font-family: {FONT_FAMILY};
    font-size: 12px;
}}

/* ===================== TABS (Holographic glass) ===================== */
QTabWidget::pane {{
    background: {COLOR_PANEL_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
    top: -1px;
}}

QTabBar::tab {{
    background: rgba(8, 12, 20, 0.55);
    border: 1px solid {COLOR_BORDER_SOFT};
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    padding: 8px 16px;
    color: {COLOR_TEXT_SECONDARY};
    font-size: 10px;
    letter-spacing: 1px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    color: {COLOR_CYAN};
    border: 1px solid {COLOR_BORDER_ACTIVE};
    background: rgba(16, 29, 43, 0.85);
}}

QTabBar::tab:hover {{
    color: {COLOR_TEXT_BRIGHT};
    border: 1px solid {COLOR_BORDER_HOVER};
}}

/* ===================== HUD CARD (Glassmorphism) ===================== */
QFrame#hudCard {{
    background-color: {COLOR_PANEL_BG};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
}}

QFrame#hudCard:hover {{
    border: 1px solid {COLOR_BORDER_HOVER};
}}

QFrame#separator {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 transparent, stop:0.5 {COLOR_CYAN}, stop:1 transparent);
    max-height: 1px;
    border: none;
}}

/* ===================== HEADERS / LABELS ===================== */
QLabel#titleLabel {{
    color: {COLOR_TEXT_BRIGHT};
    font-size: 24px;
    font-weight: bold;
    letter-spacing: 9px;
}}

QLabel#subtitleLabel {{
    color: {COLOR_CYAN};
    font-size: 10px;
    letter-spacing: 4px;
}}

QLabel#sectionHeader {{
    color: {COLOR_CYAN};
    font-size: 12px;
    font-weight: bold;
    letter-spacing: 3px;
}}

QLabel#valueLabel {{
    color: {COLOR_CYAN};
    font-weight: bold;
    font-size: 12px;
}}

QLabel#metricTitle {{
    color: {COLOR_TEXT_SECONDARY};
    font-size: 10px;
    letter-spacing: 1px;
}}

QLabel#chipTitle {{
    color: {COLOR_TEXT_DIM};
    font-size: 9px;
    letter-spacing: 2px;
}}

QLabel#chipValue {{
    color: {COLOR_TEXT_BRIGHT};
    font-weight: bold;
    font-size: 12px;
}}

QLabel#statusValue {{
    color: {COLOR_MAGENTA};
    font-weight: bold;
    font-size: 12px;
}}

/* ===================== BUTTONS ===================== */
QPushButton {{
    background: rgba(0, 240, 255, 0.08);
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 8px 18px;
    color: {COLOR_CYAN};
    font-weight: bold;
    font-size: 11px;
    letter-spacing: 2px;
}}

QPushButton:hover {{
    background: rgba(0, 240, 255, 0.16);
    border: 1px solid {COLOR_BORDER_HOVER};
    color: {COLOR_TEXT_BRIGHT};
}}

QPushButton:pressed {{
    background: rgba(0, 240, 255, 0.28);
}}

/* Quick action buttons — chamfered corners */
QPushButton#quickAction {{
    background: rgba(10, 14, 22, 0.9);
    border: 1px solid {COLOR_BORDER};
    border-radius: 2px 10px 2px 10px;
    padding: 9px 12px;
    text-align: left;
    color: {COLOR_TEXT_SECONDARY};
    font-size: 11px;
    letter-spacing: 1px;
}}

QPushButton#quickAction:hover {{
    border: 1px solid {COLOR_MAGENTA};
    color: {COLOR_TEXT_BRIGHT};
    background: rgba(255, 0, 127, 0.08);
}}

/* Sci-fi send button — angled cut */
QPushButton#btnEnviar {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLOR_MAGENTA}, stop:0.5 {COLOR_PURPLE}, stop:1 {COLOR_CYAN});
    color: #04060a;
    font-size: 12px;
    padding: 9px 20px;
    border: none;
    border-radius: 2px 12px 2px 12px;
    letter-spacing: 2px;
    font-weight: bold;
}}

QPushButton#btnEnviar:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLOR_CYAN}, stop:1 {COLOR_NEON_BLUE});
}}

QPushButton#btnEnviar:pressed {{
    background: {COLOR_CYAN};
}}

QPushButton#btnEnviar:disabled {{
    background: rgba(0, 240, 255, 0.12);
    color: {COLOR_TEXT_DIM};
}}

/* ===================== LINE EDIT (glow focus) ===================== */
QLineEdit#chatInput {{
    background: rgba(0, 0, 0, 0.55);
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 10px 12px;
    color: {COLOR_TEXT_BRIGHT};
    font-size: 13px;
}}

QLineEdit#chatInput:focus {{
    border: 1px solid {COLOR_CYAN};
    background: rgba(0, 0, 0, 0.7);
}}

/* ===================== CHAT HISTORY ===================== */
QTextEdit#chatHistory {{
    background: rgba(4, 7, 12, 0.6);
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
    padding: 10px;
    color: {COLOR_TEXT};
    font-size: 12px;
    selection-background-color: rgba(0, 240, 255, 0.18);
}}

QTextEdit#chatHistory:focus {{
    border: 1px solid {COLOR_BORDER_HOVER};
}}

/* ===================== TASK FEED ===================== */
QTextEdit#taskFeed {{
    background: rgba(4, 7, 12, 0.5);
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 8px;
    color: {COLOR_TEXT_SECONDARY};
    font-size: 11px;
    selection-background-color: rgba(0, 240, 255, 0.18);
}}

/* ===================== SCROLLBAR ===================== */
QScrollBar:vertical {{
    background: rgba(0, 0, 0, 0.3);
    width: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background: rgba(0, 240, 255, 0.25);
    border-radius: 4px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: rgba(0, 240, 255, 0.5);
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* ===================== PROGRESS BAR ===================== */
QProgressBar {{
    background: rgba(0, 0, 0, 0.4);
    border: 1px solid {COLOR_BORDER};
    border-radius: 3px;
    height: 10px;
    text-align: center;
    color: {COLOR_CYAN};
    font-size: 9px;
}}

QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLOR_MAGENTA}, stop:1 {COLOR_CYAN});
    border-radius: 2px;
}}

/* ===================== STATUS BAR (rodapé de controle) ===================== */
QLabel#statusBarLabel {{
    color: {COLOR_CYAN};
    font-size: 14px;
    font-weight: bold;
    letter-spacing: 3px;
}}

/* ===================== CHAT (painel flutuante glassmorphism) ===================== */
QWidget#chatPanel {{
    background: rgba(10, 16, 26, 0.55);
    border: 1px solid {COLOR_BORDER};
    border-radius: 12px;
}}
"""

# ═══════════════════════════════════════════════════════════════════════════
# SALLES CORE VISUALIZER — Núcleo "Arc Reactor" com anéis concêntricos
# ═══════════════════════════════════════════════════════════════════════════


class SallesCoreVisualizer(QWidget):
    """
    Visualizador circular Sci-Fi com múltiplos anéis concêntricos girando em
    velocidades e direções distintas, gradiente vibrante (Ciano → Magenta) e
    núcleo central pulsante estilo "Arc Reactor".

    Estados: standby (lento), active (médio), processing (rápido).
    """

    statusChanged = Signal(str)  # "standby", "active", "processing"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "standby"
        self._target_state = "standby"
        self._angle = 0.0
        self._pulse = 0.0
        self._target_pulse = 0.0
        self.setMinimumSize(220, 220)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60 FPS

    def set_state(self, state: str) -> None:
        """Define o estado do núcleo (standby / active / processing)."""
        if state not in ("standby", "active", "processing"):
            return
        if self._target_state != state:
            self._target_state = state
            pulses = {"standby": 0.0, "active": 0.45, "processing": 0.7}
            self._target_pulse = pulses.get(state, 0.0)
            self.statusChanged.emit(state)

    def _tick(self) -> None:
        speeds = {"standby": 0.006, "active": 0.02, "processing": 0.03}
        self._angle += speeds.get(self._state, 0.006)
        if self._angle > 2 * math.pi:
            self._angle -= 2 * math.pi

        pulse_diff = self._target_pulse - self._pulse
        self._pulse += pulse_diff * 0.12
        if abs(pulse_diff) < 0.001:
            self._pulse = self._target_pulse

        if self._state != self._target_state:
            self._state = self._target_state
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        base_r = min(w, h) * 0.42

        # ── 1. Glow externo multi-camada (ciano → azul → roxo → magenta) ──
        glow_r = base_r * (1.35 + self._pulse * 0.2)
        glow = QRadialGradient(cx, cy, glow_r)
        glow.setColorAt(0.0, QColor(24, 221, 229, int(50 + 70 * self._pulse)))
        glow.setColorAt(0.35, QColor(36, 153, 216, int(30 + 40 * self._pulse)))
        glow.setColorAt(0.7, QColor(123, 63, 168, int(20 + 25 * self._pulse)))
        glow.setColorAt(1.0, QColor(226, 47, 145, 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2))

        # ── 2. Linhas radiais (spokes) ──
        painter.setPen(QPen(QColor(24, 221, 229, 36), 1.0))
        for ang in range(0, 360, 30):
            rad = math.radians(ang + math.degrees(self._angle) * 0.5)
            x1 = cx + math.cos(rad) * base_r * 0.28
            y1 = cy + math.sin(rad) * base_r * 0.28
            x2 = cx + math.cos(rad) * base_r * 0.96
            y2 = cy + math.sin(rad) * base_r * 0.96
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # ── 3. Tick marks ao redor do anel externo ──
        painter.setPen(QPen(QColor(24, 221, 229, 60), 1.0))
        for ang in range(0, 360, 10):
            rad = math.radians(ang)
            r1 = base_r * 0.97
            r2 = base_r * 1.04
            painter.drawLine(
                QPointF(cx + math.cos(rad) * r1, cy + math.sin(rad) * r1),
                QPointF(cx + math.cos(rad) * r2, cy + math.sin(rad) * r2),
            )

        # ── 4. Anel externo com gradiente cônico (ciano→azul→roxo→magenta→laranja) ──
        outer_r = base_r * 1.02
        conic = QConicalGradient(cx, cy, 0)
        conic.setColorAt(0.0, QColor(24, 221, 229, 210))
        conic.setColorAt(0.25, QColor(36, 153, 216, 210))
        conic.setColorAt(0.5, QColor(123, 63, 168, 210))
        conic.setColorAt(0.75, QColor(226, 47, 145, 210))
        conic.setColorAt(1.0, QColor(255, 128, 77, 210))
        painter.setPen(QPen(QBrush(conic), 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(cx - outer_r, cy - outer_r, outer_r * 2, outer_r * 2))

        # ── 5. Anéis concêntricos giratórios (segmentados) ──
        rings = [
            (base_r * 0.90,  self._angle,         QColor(24, 221, 229, 70)),
            (base_r * 0.74, -self._angle * 1.4,   QColor(226, 47, 145, 80)),
            (base_r * 0.58,  self._angle * 2.1,   QColor(24, 221, 229, 95)),
            (base_r * 0.42, -self._angle * 2.8,   QColor(123, 63, 168, 110)),
        ]
        for radius, angle, color in rings:
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(math.degrees(angle))
            pen = QPen(color, 1.6)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            rect = QRectF(-radius, -radius, radius * 2, radius * 2)
            for seg in range(0, 360, 30):
                painter.drawArc(rect, (seg + 6) * 16, 15 * 16)
            painter.restore()

        # ── 6. Pontos orbitais (marcadores luminosos) ──
        orbitais = [
            (base_r * 0.90,  1.0, QColor(226, 47, 145, 220)),
            (base_r * 0.58, -1.6, QColor(24, 221, 229, 220)),
            (base_r * 0.74,  2.4, QColor(255, 128, 77, 200)),
        ]
        for i, (orb_r, speed, color) in enumerate(orbitais):
            ang = self._angle * speed + i * 2.1
            x = cx + math.cos(ang) * orb_r
            y = cy + math.sin(ang) * orb_r
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(x - 2.5, y - 2.5, 5.0, 5.0))

        # ── 7. Núcleo Arc Reactor (centro pulsante) ──
        core_r = base_r * 0.28 * (1.0 + self._pulse * 0.28)
        core_grad = QRadialGradient(cx, cy, core_r * 2)
        core_grad.setColorAt(0, QColor(201, 232, 234, 235))
        core_grad.setColorAt(0.35, QColor(24, 221, 229, 205))
        core_grad.setColorAt(0.75, QColor(123, 63, 168, 120))
        core_grad.setColorAt(1, QColor(226, 47, 145, 0))
        painter.setBrush(QBrush(core_grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - core_r, cy - core_r, core_r * 2, core_r * 2))

        # Símbolo central (sensor/núcleo de energia)
        inner = core_r * 0.55
        painter.setPen(QPen(QColor(24, 221, 229, 180), 1.1))
        painter.drawLine(
            QPointF(cx - inner, cy), QPointF(cx + inner, cy))
        painter.drawLine(
            QPointF(cx, cy - inner), QPointF(cx, cy + inner))

        # Anel interno de contorno
        painter.setPen(QPen(QColor(24, 221, 229, 170), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(cx - core_r, cy - core_r, core_r * 2, core_r * 2))

        painter.end()


# ═══════════════════════════════════════════════════════════════════════════
# WORKER DE INICIALIZAÇÃO EM SEGUNDO PLANO
# ═══════════════════════════════════════════════════════════════════════════

class InitWorker(QThread):
    """
    Thread que inicializa os subsistemas em paralelo sem congelar a UI.

    Inicializa:
      1. ollama_service — garantia de que o Ollama está rodando
      2. config_manager — validação de diretórios
      3. hardware — diagnóstico e auto-configuração (Llama 3.2)
      4. kill_switch — monitoramento de emergência
      5. brain — verificação da conexão com Ollama
    """

    subsystemReady = Signal(str, bool)    # nome_do_subsistema, sucesso
    allReady = Signal(dict)               # dicionário com status de todos
    progress = Signal(str, int)           # mensagem, percentual

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        results: dict[str, bool] = {}
        steps = [
            ("ollama_service", self._init_ollama_service),
            ("config_manager", self._init_config),
            ("hardware", self._init_hardware),
            ("kill_switch", self._init_killswitch),
            ("brain", self._init_brain),
        ]
        total = len(steps)

        for i, (name, func) in enumerate(steps):
            if self._cancel:
                return
            self.progress.emit(f"Inicializando {name}...", int((i / total) * 100))
            try:
                success = func()
                results[name] = success
                self.subsystemReady.emit(name, success)
                self.progress.emit(
                    f"{name}: {'OK' if success else 'FALHA'}",
                    int(((i + 1) / total) * 100),
                )
            except Exception as exc:
                results[name] = False
                self.subsystemReady.emit(name, False)
                self.progress.emit(f"{name}: ERRO ({exc})", int(((i + 1) / total) * 100))

        if not self._cancel:
            self.allReady.emit(results)

    def _init_ollama_service(self) -> bool:
        """Garante que o servidor Ollama esteja rodando em segundo plano."""
        if brain is None:
            return False
        try:
            self.progress.emit("Iniciando servidor do Ollama em segundo plano...", 5)
            return brain.garantir_servico_ollama()
        except Exception:
            return False

    def _init_config(self) -> bool:
        if config_manager is None:
            return False
        try:
            return config_manager.validar_e_preparar_ambiente()
        except Exception:
            return False

    def _init_killswitch(self) -> bool:
        if kill_switch is None:
            return False
        try:
            kill_switch.iniciar_monitoramento()
            return True
        except Exception:
            return False

    def _init_brain(self) -> bool:
        if brain is None:
            return False
        try:
            online, modelo = brain.verificar_conexao_ollama()
            return online
        except Exception:
            return False

    def _init_hardware(self) -> bool:
        """Diagnostica o hardware e aplica a auto-configuração recomendada."""
        if config_manager is None:
            return False
        try:
            recomendacoes = config_manager.auto_configurar_hardware()
            return bool(recomendacoes)
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════════
# PAINEL DE CONFIGURAÇÕES
# ═══════════════════════════════════════════════════════════════════════════

class SettingsPanel(QWidget):
    """Painel lateral com sliders/combos integrados ao config_manager."""

    configChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config = self._carregar_config()
        self._sliders: dict[str, QSlider] = {}
        self._combos: dict[str, QComboBox] = {}
        self._value_labels: dict[str, QLabel] = {}
        self._build_ui()
        self._carregar_valores()

    def _carregar_config(self) -> dict:
        if config_manager:
            return config_manager.carregar_configuracao()
        return {
            "cpu_threads": 4, "gpu_layers": 20, "max_ram_gb": 8,
            "data_directory": str(_SCRIPT_DIR / "data"),
            "hotkey_pause": "esc", "log_level": "INFO",
        }

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # ── Hardware ──
        hw_group = QGroupBox("HARDWARE")
        hw_layout = QGridLayout(hw_group)
        hw_layout.setVerticalSpacing(10)

        self._add_slider_row(hw_layout, 0, "CPU Threads", "cpu_threads", 1, 16, 1)
        self._add_slider_row(hw_layout, 1, "GPU Layers", "gpu_layers", 0, 40, 0)
        self._add_slider_row(hw_layout, 2, "RAM Max (GB)", "max_ram_gb", 2, 32, 2)
        layout.addWidget(hw_group)

        # ── Segurança ──
        sec_group = QGroupBox("TRACA DE SEGURANCA")
        sec_layout = QGridLayout(sec_group)
        sec_layout.setVerticalSpacing(10)

        self._add_combo_row(sec_layout, 0, "Hotkey Pause", "hotkey_pause",
                            ["esc", "f1", "f2", "f4", "f8", "f12",
                             "space", "tab", "delete", "pause"])
        layout.addWidget(sec_group)

        # ── Logs ──
        log_group = QGroupBox("LOGS & DIAGNOSTICO")
        log_layout = QGridLayout(log_group)
        log_layout.setVerticalSpacing(10)

        self._add_combo_row(log_layout, 0, "Log Level", "log_level",
                            ["DEBUG", "INFO", "WARNING", "ERROR"])

        dir_label = QLabel("Data Directory")
        dir_label.setStyleSheet(f"color: {COLOR_TEXT_DIM};")
        log_layout.addWidget(dir_label, 1, 0)
        self._dir_value = QLabel(self._config.get("data_directory", ""))
        self._dir_value.setObjectName("valueLabel")
        self._dir_value.setWordWrap(True)
        log_layout.addWidget(self._dir_value, 1, 1)
        layout.addWidget(log_group)

        layout.addStretch()

    def _add_slider_row(self, layout: QGridLayout, row: int, label: str,
                        key: str, vmin: int, vmax: int, step: int) -> None:
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {COLOR_TEXT_DIM};")
        layout.addWidget(lbl, row, 0)

        val = QLabel("0")
        val.setObjectName("valueLabel")
        val.setFixedWidth(40)
        layout.addWidget(val, row, 2)
        self._value_labels[key] = val

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(vmin, vmax)
        slider.setSingleStep(max(1, step))
        slider.setPageStep(max(2, step * 2))
        slider.valueChanged.connect(lambda v, k=key: self._on_slider(k, v))
        layout.addWidget(slider, row, 1)
        self._sliders[key] = slider

    def _add_combo_row(self, layout: QGridLayout, row: int, label: str,
                       key: str, options: list[str]) -> None:
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {COLOR_TEXT_DIM};")
        layout.addWidget(lbl, row, 0)

        combo = QComboBox()
        combo.addItems(options)
        combo.currentTextChanged.connect(lambda v, k=key: self._on_combo(k, v))
        layout.addWidget(combo, row, 1, 1, 2)
        self._combos[key] = combo

    def _carregar_valores(self) -> None:
        cfg = self._config
        for key, slider in self._sliders.items():
            val = cfg.get(key, 0)
            slider.blockSignals(True)
            slider.setValue(int(val))
            slider.blockSignals(False)
            self._value_labels[key].setText(str(int(val)))

        for key, combo in self._combos.items():
            val = str(cfg.get(key, ""))
            combo.blockSignals(True)
            idx = combo.findText(val)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def _on_slider(self, key: str, value: int) -> None:
        self._config[key] = value
        if key in self._value_labels:
            self._value_labels[key].setText(str(value))
        self.configChanged.emit()

    def _on_combo(self, key: str, value: str) -> None:
        self._config[key] = value
        self.configChanged.emit()

    def obter_config(self) -> dict:
        return dict(self._config)

    def salvar(self) -> bool:
        if config_manager:
            return config_manager.salvar_configuracao(self._config)
        return False


# ═══════════════════════════════════════════════════════════════════════════
# CHAT WORKER — Processamento em thread separada (QThread)
# ═══════════════════════════════════════════════════════════════════════════

class ChatWorker(QThread):
    """
    Thread que executa brain.pensar() em segundo plano.

    Emite sinais:
      - started: ao iniciar o processamento
      - status(str): status intermediário de progresso
      - finished(dict): ao concluir com o JSON completo
      - error(str): em caso de falha
    """

    started = Signal()
    status = Signal(str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, prompt: str, historico: list | None = None, parent=None):
        super().__init__(parent)
        self._prompt = prompt
        self._historico = historico or []

    def run(self) -> None:
        self.started.emit()
        try:
            if brain is None:
                self.error.emit(
                    "Módulo 'brain' não disponível. "
                    "Verifique a instalação do J.A.R.V.I.S."
                )
                return

            historico_limpo = [
                m for m in self._historico
                if m.get("role") != "system"
            ]

            self.status.emit("[ANALISANDO]")

            # Multi-Agent System: tarefas de código/automação passam pelo
            # pipeline Arquiteto → Coder → Auditor (só publica se aprovado).
            usa_multiagente = (
                hasattr(brain, "classificar_tarefa")
                and hasattr(brain, "orquestrar_agentes")
                and brain.classificar_tarefa(self._prompt)
            )
            if usa_multiagente:
                resultado = brain.orquestrar_agentes(
                    self._prompt, status_callback=self.status.emit
                )
            else:
                resultado = brain.pensar(self._prompt, historico_limpo)

            self.status.emit("[EXECUTANDO EM BACKGROUND]")
            self.status.emit("[CONCLUÍDO]")
            self.finished.emit(resultado)

        except Exception as exc:
            self.error.emit(f"Erro no processamento: {exc}")


# ═══════════════════════════════════════════════════════════════════════════
# CHAT CONSOLE — Painel de Chat Textual Interativo (HUD Console)
# ═══════════════════════════════════════════════════════════════════════════

class ChatConsole(QWidget):
    """
    Console de chat textual estilo terminal cyberpunk.

    Funcionalidades:
    - Histórico HTML: [VOCÊ] em ciano, [J.A.R.V.I.S.] em verde neon
    - Campo de entrada com placeholder e botão ENVIAR
    - Processamento assíncrono via QThread (ChatWorker)
    - Suporte a TODAS as ações expandidas (brain v2.0)
    """

    statusMessage = Signal(str)
    coreStateRequest = Signal(str)  # solicita mudança de estado do Core 3D
    hideRequested = Signal()        # solicita ocultar a janela (ESC no chat)
    tarefaConcluida = Signal(str)   # resumo da tarefa concluída (notificação)
    paletteRequested = Signal()     # solicita abrir a paleta de comandos
    diagnosticoExterno = Signal(str)  # diagnóstico vindo do brain (thread assíncrona)
    moduloAtivo = Signal(str)       # módulo/subagente entrou em execução (acende nó)
    moduloInativo = Signal(str)     # módulo/background concluído (apaga indicador)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: ChatWorker | None = None
        self._historico_contexto: list[dict] = []
        self._ultimo_prompt: str = ""
        self._processando = False
        self._workers: list = []  # workers em background (para cleanup no fechamento)
        self._build_ui()
        self.diagnosticoExterno.connect(self._on_diagnostico_externo)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ── Header ──
        header = QLabel("CONSOLO / CHAT TEXTUAL")
        header.setObjectName("consoleHeader")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        # ── Separator ──
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFixedHeight(2)
        layout.addWidget(sep)

        # ── Histórico ──
        self._history = QTextEdit()
        self._history.setObjectName("chatHistory")
        self._history.setReadOnly(True)
        self._history.setMinimumHeight(200)
        self._history.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        layout.addWidget(self._history, stretch=1)

        # ── Linha de entrada ──
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self._input = QLineEdit()
        self._input.setObjectName("chatInput")
        self._input.setPlaceholderText("Digite seu comando para o J.A.R.V.I.S...")
        self._input.returnPressed.connect(self._on_enviar)
        self._input.setMinimumHeight(36)
        input_row.addWidget(self._input, stretch=1)

        self._btn_enviar = QPushButton("ENVIAR")
        self._btn_enviar.setObjectName("btnEnviar")
        self._btn_enviar.setFixedWidth(90)
        self._btn_enviar.clicked.connect(self._on_enviar)
        input_row.addWidget(self._btn_enviar)

        self._btn_snap = QPushButton("SNAP")
        self._btn_snap.setObjectName("quickAction")
        self._btn_snap.setFixedWidth(64)
        self._btn_snap.setToolTip("Capturar tela e analisar o contexto visual (/snap)")
        self._btn_snap.clicked.connect(self._on_snap_clicked)
        input_row.addWidget(self._btn_snap)

        layout.addLayout(input_row)

        # ESC dentro do chat oculta a janela principal
        self._esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._esc_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._esc_shortcut.activated.connect(self.hideRequested.emit)

        # ── Boas-vindas ──
        self._append_system(
            "CONSOLO J.A.R.V.I.S. v2.0 — SALLES INDUSTRIES Quantum OS\n"
            "Digite um comando ou pergunta para interagir com o assistente.\n"
            "Ações: pesquisar, executar cmd, abrir apps, analisar código,\n"
            "diagnóstico Windows, processar vídeo, e mais."
        )

    # ── Slots ──

    def _on_enviar(self) -> None:
        if self._processando:
            return

        prompt = self._input.text().strip()
        if not prompt:
            return

        # Roteia comandos internos da paleta (/git-sync, /cleanup, /net-check, /autofix, /cmd)
        if prompt.startswith("/"):
            self._executar_comando_palette(prompt)
            return

        # Smart CLI: comandos nativos do PowerShell ($) ou CMD (>)
        if prompt.startswith("$") or prompt.startswith(">"):
            self._executar_smart_cli(prompt)
            return

        self._ultimo_prompt = prompt
        self._append_user(prompt)
        self._input.clear()
        self._set_processando(True)

        # Notifica Core 3D que estamos processando
        self.coreStateRequest.emit("processing")

        self._worker = ChatWorker(prompt, list(self._historico_contexto))
        self._worker.started.connect(self._on_worker_started)
        self._worker.status.connect(self._on_worker_status)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.error.connect(self._worker.deleteLater)
        self._workers.append(self._worker)
        self._worker.start()

    def _on_worker_status(self, mensagem: str) -> None:
        """Exibe um status intermediário de progresso no console."""
        self._append_system(mensagem)
        # Integração visual: acende o nó do subagente ativo (Arquiteto/Coder/Auditor).
        m = mensagem.upper()
        if "ARQUITETO" in m:
            self.moduloAtivo.emit("arquiteto")
        elif "CODER" in m:
            self.moduloAtivo.emit("coder")
        elif "AUDITOR" in m:
            self.moduloAtivo.emit("auditor")

    def focar_input(self) -> None:
        """Foca o campo de entrada do chat (usado pelo atalho global)."""
        self._input.setFocus()

    def _on_worker_started(self) -> None:
        self._append_system("[PROCESSANDO...]")

    def _on_worker_finished(self, resultado: object) -> None:
        self._set_processando(False)

        # ── Extrai resposta_voz de forma resiliente ──
        resposta_voz = ""
        acao = "falar"
        params: dict = {}

        if isinstance(resultado, str):
            # Resposta veio como texto puro → uso direto
            resposta_voz = resultado
        elif isinstance(resultado, dict):
            acao = resultado.get("acao", "falar")
            params = resultado.get("parametros", {})
            # Tenta múltiplas chaves comuns de resposta
            for chave in ("resposta_voz", "resposta", "texto", "message",
                           "content", "response"):
                candidato = resultado.get(chave)
                if isinstance(candidato, str) and candidato.strip():
                    resposta_voz = candidato.strip()
                    break

        # ── Fallback: NUNCA passa string vazia ou só espaços para a UI ──
        if not resposta_voz or not resposta_voz.strip():
            resposta_voz = (
                "Não consegui estruturar uma resposta agora. Tente reformular."
            )

        # Exibe a resposta final limpa
        self._append_jarvis(resposta_voz)

        # Sinaliza o módulo correspondente no HUD (acende o nó orbital).
        self.moduloAtivo.emit(acao)

        # Executa ação
        acao_resultado = self._executar_acao(acao, params, resposta_voz)
        if acao_resultado:
            self._append_system(acao_resultado)

        # Restaura Core
        self.coreStateRequest.emit("active")

        # Atualiza histórico
        self._historico_contexto.append({
            "role": "user",
            "content": (
                f"O usuário disse: '{self._ultimo_prompt}'. "
                f"Você respondeu com a ação '{acao}'."
            ),
        })
        self._historico_contexto.append({
            "role": "assistant",
            "content": resposta_voz,
        })

        if len(self._historico_contexto) > 20:
            self._historico_contexto = self._historico_contexto[-20:]

        # Notifica a bandeja do sistema sobre a conclusão da tarefa.
        self.tarefaConcluida.emit(f"Ação '{acao}' concluída — relatório pronto no chat.")

    def _on_worker_error(self, mensagem: str) -> None:
        self._set_processando(False)
        self._append_error(mensagem)
        self.coreStateRequest.emit("active")

    # ── Comandos internos (Command Palette) ──

    def _executar_comando_palette(self, comando: str) -> None:
        """Roteia comandos internos iniciados por '/'."""
        raw = comando.strip()
        comando = raw.lower()

        if comando in ("/cmd", "/palette", "/help"):
            self.paletteRequested.emit()
            return

        self._append_user(raw)
        self._input.clear()

        if comando == "/git-sync":
            self._rodar_automacao(pc_controller.git_sync, "git-sync")
        elif comando == "/cleanup":
            self._rodar_automacao(pc_controller.limpar_temporarios, "cleanup")
        elif comando == "/net-check":
            self._rodar_automacao(pc_controller.diagnostico_rede, "net-check")
        elif comando.startswith("/autofix"):
            codigo = comando[len("/autofix"):].strip()
            if not codigo:
                # Usa o último prompt do operador (código colado anteriormente).
                codigo = self._ultimo_prompt
            if not codigo:
                self._append_system(
                    "Nenhum código encontrado. Cole o código no chat e depois digite /autofix."
                )
                return
            self._rodar_autofix(codigo)
        elif comando.startswith("/research"):
            tema = comando[len("/research"):].strip()
            if not tema:
                self._append_system("Uso: /research <tema>")
                return
            self._rodar_research(tema)
        elif comando.startswith("/web"):
            acao = raw[len("/web"):].strip()
            self._rodar_web(acao)
        elif comando.startswith("/mode"):
            perfil = comando[len("/mode"):].strip()
            self._rodar_mode(perfil)
        elif comando.startswith("/snap"):
            pergunta = raw[len("/snap"):].strip()
            self._rodar_snap(pergunta)
        elif comando.startswith("/lab"):
            self._rodar_lab(raw[len("/lab"):].strip())
        elif comando.startswith("/self-audit"):
            self._rodar_self_audit(raw[len("/self-audit"):].strip())
        elif comando.startswith("/record"):
            self._rodar_record(raw[len("/record"):].strip())
        elif comando.startswith("/db-schema"):
            self._rodar_db_schema(raw[len("/db-schema"):].strip())
        elif comando.startswith("/db-query"):
            self._rodar_db_query(raw[len("/db-query"):].strip())
        elif comando.startswith("/db-ask"):
            self._rodar_db_ask(raw[len("/db-ask"):].strip())
        elif comando.startswith("/net-map"):
            self._rodar_net_map()
        elif comando.startswith("/ingest"):
            self._rodar_ingest(raw[len("/ingest"):].strip())
        elif comando == "/inspect":
            self._rodar_automacao(pc_controller.inspecionar_downloads, "inspect")
        elif comando == "/metrics":
            self._rodar_automacao(self._obter_metricas, "metrics")
        else:
            self._append_system(
                f"Comando desconhecido: {comando}\nDigite /cmd para ver a lista de comandos."
            )

        self._ultimo_prompt = comando

    def _rodar_research(self, tema: str) -> None:
        """Executa o Deep Research em background."""
        def tarefa():
            if brain is None:
                return False, "Módulo brain indisponível."
            caminho, resumo = brain.executar_pesquisa_profunda(tema)
            if not caminho:
                return False, resumo
            return True, resumo

        self._rodar_automacao(tarefa, "research")

    def _obter_metricas(self) -> tuple[bool, str]:
        """Gera o resumo de métricas de desenvolvimento."""
        if config_manager is None:
            return False, "Módulo config_manager indisponível."
        m = config_manager.obter_resumo_metricas()
        hoje = m["hoje"]
        total = m["total"]
        vram = f"{m['media_vram']}%" if m["media_vram"] is not None else "N/A"
        return True, (
            f"MÉTRICAS (hoje):\n"
            f"  • Comandos: {hoje['comandos']}\n"
            f"  • Pesquisas: {hoje['pesquisas']}\n"
            f"  • Commits: {hoje['commits']}\n\n"
            f"MÉTRICAS (total):\n"
            f"  • Comandos: {total['comandos']}\n"
            f"  • Pesquisas: {total['pesquisas']}\n"
            f"  • Commits: {total['commits']}\n\n"
            f"USO MÉDIO (hoje):\n"
            f"  • RAM: {m['media_ram']}%\n"
            f"  • VRAM: {vram}"
        )

    def _executar_smart_cli(self, prompt: str) -> None:
        """Executa um comando nativo ($ PowerShell / > CMD) em background."""
        if prompt.startswith("$"):
            shell = "powershell"
            comando = prompt[1:].strip()
        else:
            shell = "cmd"
            comando = prompt[1:].strip()

        if not comando:
            self._append_system("Uso: $ <comando PowerShell>  ou  > <comando CMD>")
            return

        self._append_user(prompt)
        self._input.clear()
        self._set_processando(True)
        self._append_system(f"[SMART CLI · {shell.upper()}] {comando}")

        def tarefa():
            if pc_controller is None:
                return True, "Módulo pc_controller indisponível."
            sucesso, stdout, stderr = pc_controller.executar_comando_cmd(comando, timeout=60)
            if sucesso:
                return True, stdout or "(sem saída)"
            traducao = ""
            if brain is not None:
                try:
                    traducao = brain.traduzir_erro_terminal(stderr or stdout)
                except Exception:
                    traducao = ""
            texto = stderr or stdout or "(sem erro)"
            if traducao:
                texto += f"\n\n[TRADUÇÃO DO ERRO EM PORTUGUÊS]\n{traducao}"
            return True, texto

        worker = AutomacaoWorker(tarefa)
        worker.concluido.connect(self._exibir_smartcli)
        worker.falhou.connect(lambda err: self._exibir_smartcli(f"[FALHA] {err}"))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _exibir_smartcli(self, texto: str) -> None:
        """Exibe a saída de um comando nativo em caixa de código Cyberpunk."""
        self._set_processando(False)
        self._append_codigo(texto)
        self.coreStateRequest.emit("active")

    def _append_codigo(self, texto: str) -> None:
        """Renderiza texto em uma caixa de código monoespaçada (HUD)."""
        html = (
            f'<div style="margin: 6px 0; background: rgba(0, 0, 0, 0.45); '
            f'border: 1px solid {COLOR_BORDER}; border-radius: 6px; padding: 8px;">'
            f'<pre style="color: {COLOR_TEXT_SECONDARY}; font-family: {FONT_FAMILY}; '
            f'font-size: 11px; margin: 0; white-space: pre-wrap;">'
            f'{self._escape(texto)}</pre></div>'
        )
        self._history.append(html)
        self._scroll_to_bottom()

    def _rodar_automacao(self, funcao, nome: str) -> None:
        """Executa uma função de automação em background (QThread)."""
        self._append_system(f"[EXECUTANDO {nome.upper()} EM BACKGROUND...]")
        self._set_processando(True)
        self.moduloAtivo.emit(nome)
        worker = AutomacaoWorker(funcao)
        worker.concluido.connect(lambda res: self._on_automacao_ok(nome, res))
        worker.falhou.connect(lambda err: self._on_automacao_err(nome, err))
        worker.finished.connect(worker.deleteLater)
        self._workers.append(worker)
        worker.start()

    def parar_workers(self) -> None:
        """Aguarda (best-effort) os workers em background ao fechar a UI."""
        for w in self._workers:
            try:
                if w.isRunning():
                    w.wait(3000)
            except Exception:
                pass
        self._workers = []

    def _rodar_autofix(self, codigo: str) -> None:
        """Executa o agente /autofix em background."""
        if pc_controller is None:
            self._append_error("Módulo pc_controller indisponível para /autofix.")
            return

        def tarefa():
            sucesso, codigo_final, saida = pc_controller.autofix_codigo(codigo)
            status = (
                "✅ Código corrigido e executado com sucesso."
                if sucesso
                else "❌ Não foi possível corrigir automaticamente."
            )
            return sucesso, f"{status}\n\nSaída final:\n{saida}"

        self._rodar_automacao(tarefa, "autofix")

    def _rodar_web(self, acao: str) -> None:
        """Executa a automação web (/web) em background."""
        if web_automation is None:
            self._append_error("Módulo web_automation indisponível para /web.")
            return
        if not acao:
            self._append_system(
                "Uso: /web <ação> <argumentos>\n"
                "Ações: pesquisar <termo> | acessar <url> | baixar <url> |\n"
                "       preencher <url> | <seletor> | <valor> | screenshot <url>"
            )
            return
        self._rodar_automacao(
            lambda: web_automation.interpretar_e_executar(acao), "web"
        )

    def _rodar_mode(self, perfil: str) -> None:
        """Aplica um perfil de trabalho (/mode) em background."""
        if pc_controller is None:
            self._append_error("Módulo pc_controller indisponível para /mode.")
            return
        if not perfil:
            self._append_system("Uso: /mode <perfil>  (dev | focus | gaming)")
            return
        self._rodar_automacao(
            lambda: pc_controller.aplicar_modo_perfil(perfil), "mode"
        )

    def _rodar_snap(self, pergunta: str) -> None:
        """Captura a tela, extrai o contexto visual e injeta no brain (/snap)."""
        if vision_engine is None:
            self._append_error("Módulo vision_engine indisponível para /snap.")
            return

        def tarefa():
            resultado = vision_engine.capturar_contexto_tela()
            contexto = vision_engine.montar_contexto_visual(resultado)
            if not resultado.get("sucesso"):
                return False, contexto or "Falha ao capturar a tela."

            texto_resposta = ""
            if brain is not None and hasattr(brain, "responder_sobre_tela"):
                try:
                    resposta = brain.responder_sobre_tela(contexto, pergunta)
                    texto_resposta = (resposta.get("resposta_voz") or "").strip()
                except Exception:
                    texto_resposta = ""

            linhas = [f"Captura salva em: {resultado.get('caminho', '')}"]
            if texto_resposta:
                linhas.append("")
                linhas.append("ANÁLISE DO J.A.R.V.I.S.:")
                linhas.append(texto_resposta)
            elif resultado.get("texto"):
                linhas.append("")
                linhas.append("TEXTO EXTRAÍDO (OCR):")
                linhas.append(resultado.get("texto", ""))
            return True, "\n".join(linhas)

        self._rodar_automacao(tarefa, "snap")

    def _on_snap_clicked(self) -> None:
        """Captura rápida de tela a partir do botão SNAP."""
        self._rodar_snap("")

    def _rodar_lab(self, acao: str) -> None:
        """Executa a ação do Cyber Range (/lab) em background."""
        if virtual_lab is None:
            self._append_error("Módulo virtual_lab indisponível para /lab.")
            return
        if not acao:
            self._append_system(
                "Uso: /lab <ação> [args]\n"
                "Ações: status | list | up <imagem> | exec <id> <cmd> | "
                "down <id> | wsl <cmd>"
            )
            return
        self._rodar_automacao(
            lambda: virtual_lab.interpretar_e_executar(acao), "lab"
        )

    def _rodar_self_audit(self, caminho: str) -> None:
        """Executa a auto-auditoria de código (/self-audit) em background."""
        if self_optimizer is None:
            self._append_error("Módulo self_optimizer indisponível para /self-audit.")
            return
        self._rodar_automacao(
            lambda: self_optimizer.executar_auto_auditoria(caminho or None),
            "self-audit",
        )

    def _rodar_record(self, duracao: str) -> None:
        """Grava e resume uma reunião (/record) em background."""
        if meeting_summarizer is None:
            self._append_error("Módulo meeting_summarizer indisponível para /record.")
            return
        try:
            segundos = int(duracao) if duracao.strip() else 60
        except ValueError:
            segundos = 60
        self._append_system(f"[GRAVANDO ÁUDIO POR {segundos}s...]")
        self._rodar_automacao(
            lambda: meeting_summarizer.gravar_e_resumir(segundos), "record"
        )

    def _rodar_db_schema(self, spec: str) -> None:
        """Inspeciona o schema de um banco (/db-schema)."""
        if database_assistant is None:
            self._append_error("Módulo database_assistant indisponível.")
            return
        if not spec:
            self._append_system("Uso: /db-schema <banco>")
            return
        self._rodar_automacao(
            lambda: database_assistant.inspecionar_schema(spec), "db-schema"
        )

    def _rodar_db_query(self, resto: str) -> None:
        """Executa uma query somente leitura (/db-query)."""
        if database_assistant is None:
            self._append_error("Módulo database_assistant indisponível.")
            return
        partes = resto.split(maxsplit=1)
        if len(partes) < 2:
            self._append_system("Uso: /db-query <banco> <sql>")
            return
        spec, sql = partes[0], partes[1]
        self._rodar_automacao(
            lambda: database_assistant.executar_query(spec, sql), "db-query"
        )

    def _rodar_db_ask(self, resto: str) -> None:
        """Gera SQL a partir de linguagem natural (/db-ask)."""
        if database_assistant is None:
            self._append_error("Módulo database_assistant indisponível.")
            return
        partes = resto.split(maxsplit=1)
        if len(partes) < 2:
            self._append_system("Uso: /db-ask <banco> <pergunta>")
            return
        spec, pergunta = partes[0], partes[1]
        self._rodar_automacao(
            lambda: database_assistant.gerar_sql_natural(pergunta, spec), "db-ask"
        )

    def _rodar_net_map(self) -> None:
        """Varre a rede local (/net-map) em background."""
        if network_mapper is None:
            self._append_error("Módulo network_mapper indisponível para /net-map.")
            return
        self._rodar_automacao(network_mapper.executar_varredura, "net-map")

    def _rodar_ingest(self, caminho: str) -> None:
        """Ingere um arquivo multimodal (/ingest <caminho>) em background (QThread)."""
        caminho = (caminho or "").strip().strip('"').strip("'")
        if not caminho:
            self._append_system("Uso: /ingest <caminho_do_arquivo>")
            return
        if multimodal_ingestor is None:
            self._append_error("Módulo multimodal_ingestor indisponível para /ingest.")
            return
        self._append_system(f"[INGESTÃO MULTIMODAL] {caminho}")

        def tarefa() -> tuple[bool, str]:
            ingestor = multimodal_ingestor.MultimodalIngestor()
            ok, resumo, _meta = ingestor.processar_arquivo(caminho)
            return ok, resumo

        self._rodar_automacao(tarefa, "ingest")

    def ingestir_arquivo(self, caminho: str) -> None:
        """API pública de ingestão (usada pelo Drag-and-Drop da janela)."""
        self._rodar_ingest(caminho)

    def _on_automacao_ok(self, nome: str, resumo: str) -> None:
        self._set_processando(False)
        self._append_system(f"[{nome.upper()} CONCLUÍDO]\n{resumo}")
        self.coreStateRequest.emit("active")
        self.moduloInativo.emit(nome)
        self.tarefaConcluida.emit(f"{nome.upper()} concluído.")

    def _on_automacao_err(self, nome: str, erro: str) -> None:
        self._set_processando(False)
        self._append_error(f"[{nome.upper()} FALHOU]\n{erro}")
        self.coreStateRequest.emit("active")
        self.moduloInativo.emit(nome)

    def _on_diagnostico_externo(self, texto: str) -> None:
        """Recebe um diagnóstico vindo do brain (via fila assíncrona)."""
        self._append_system(f"[DIAGNÓSTICO AUTOMÁTICO]\n{texto}")

    def anexar_linha_log(self, linha: str, severidade: str) -> None:
        """Exibe uma linha de log monitorada com destaque de severidade."""
        self._append_system(f"[LOG:{severidade}] {linha}")

    # ── Helpers de exibição ──

    def _append_user(self, texto: str) -> None:
        html = (
            f'<div style="margin: 6px 0;">'
            f'<span style="color: {COLOR_CYAN}; font-weight: bold;">'
            f'[VOCÊ]:</span> '
            f'<span style="color: {COLOR_TEXT_BRIGHT};">{self._escape(texto)}</span>'
            f'</div>'
        )
        self._history.append(html)
        self._scroll_to_bottom()

    def _append_jarvis(self, texto: str) -> None:
        if not texto:
            return
        html = (
            f'<div style="margin: 6px 0;">'
            f'<span style="color: {COLOR_GREEN}; font-weight: bold;">'
            f'[J.A.R.V.I.S.]:</span> '
            f'<span style="color: {COLOR_GREEN};">{self._escape(texto)}</span>'
            f'</div>'
        )
        self._history.append(html)
        self._scroll_to_bottom()

    def _append_system(self, texto: str) -> None:
        html = (
            f'<div style="margin: 4px 0;">'
            f'<span style="color: {COLOR_TEXT_DIM}; font-style: italic;">'
            f'{self._escape(texto)}</span>'
            f'</div>'
        )
        self._history.append(html)
        self._scroll_to_bottom()

    def _append_error(self, texto: str) -> None:
        html = (
            f'<div style="margin: 4px 0;">'
            f'<span style="color: {COLOR_RED}; font-weight: bold;">'
            f'[ERRO]:</span> '
            f'<span style="color: {COLOR_RED};">{self._escape(texto)}</span>'
            f'</div>'
        )
        self._history.append(html)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        cursor = self._history.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._history.setTextCursor(cursor)

    @staticmethod
    def _escape(texto: str) -> str:
        return (
            texto.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )

    def _set_processando(self, ativo: bool) -> None:
        self._processando = ativo
        self._btn_enviar.setEnabled(not ativo)
        self._input.setEnabled(not ativo)
        if not ativo:
            self._input.setFocus()
        if ativo:
            self._btn_enviar.setText("•••")
            self._input.setPlaceholderText("J.A.R.V.I.S. está processando...")
        else:
            self._btn_enviar.setText("ENVIAR")
            self._input.setPlaceholderText("Digite seu comando para o J.A.R.V.I.S...")

    # ── Roteador de ações (expandido) ──

    def _executar_acao(self, acao: str, params: dict, resposta_padrao: str) -> str:
        try:
            if acao == "executar_cmd":
                return self._tratar_executar_cmd(params)
            elif acao == "abrir_app":
                return self._tratar_abrir_app(params)
            elif acao == "pesquisar_web":
                return self._tratar_pesquisar_web(params)
            elif acao == "criar_arquivo":
                return self._tratar_criar_arquivo(params)
            elif acao == "gerar_codigo":
                return self._tratar_gerar_codigo(params)
            elif acao == "refatorar_codigo":
                return self._tratar_refatorar_codigo(params)
            elif acao == "analisar_codigo":
                return self._tratar_analisar_codigo(params)
            elif acao == "arquitetura":
                return self._tratar_arquitetura(params)
            elif acao == "diagnostico_windows":
                return self._tratar_diagnostico_windows(params)
            elif acao == "processar_video":
                return self._tratar_processar_video(params)
            elif acao == "cyber_defense":
                return self._tratar_cyber_defense(params)
            elif acao == "pentest_recon":
                return self._tratar_pentest_recon(params)
            elif acao == "pentest_scan":
                return self._tratar_pentest_scan(params)
            elif acao == "pentest_report":
                return self._tratar_pentest_report(params)
            elif acao == "negar":
                return (
                    "⛔ Ação negada pelo cérebro: comando potencialmente "
                    "perigoso ou viola protocolos de segurança."
                )
            else:
                return ""
        except Exception as exc:
            traceback.print_exc()
            return f"Falha ao executar ação '{acao}': {exc}"

    def _tratar_executar_cmd(self, params: dict) -> str:
        comando = params.get("comando", "")
        shell = params.get("shell", "cmd")
        if not comando:
            return "Nenhum comando especificado para execução."
        if pc_controller is None:
            return f"⚠ Módulo pc_controller indisponível. Comando não executado: '{comando}'"

        # Se for PowerShell, envolve com powershell -Command
        if shell == "powershell":
            comando = f'powershell -Command "{comando}"'

        # ── Verificação de segurança ──
        if security is not None:
            precisa, nivel, msg = security.requires_confirmation(comando)
            if precisa:
                reply = QMessageBox.warning(
                    self,
                    "SALLES INDUSTRIES — Confirmação de Segurança",
                    msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return f"⛔ Comando bloqueado por segurança [{nivel}]. Execução cancelada pelo usuário."

        sucesso, stdout, stderr = pc_controller.executar_comando_cmd(comando)
        if sucesso:
            if stdout:
                return f"✅ Comando executado [{shell}].\nResultado:\n{stdout[:800]}"
            return "✅ Comando executado com sucesso (sem saída)."
        else:
            return f"❌ Comando falhou: {stderr[:300]}"

    def _tratar_abrir_app(self, params: dict) -> str:
        app = params.get("app") or params.get("programa") or params.get("comando", "")
        if not app:
            return "Nenhum aplicativo especificado para abrir."
        if pc_controller is None:
            return f"⚠ Módulo pc_controller indisponível. App não aberto: '{app}'"
        ok = pc_controller.abrir_aplicativo(app)
        if ok:
            return f"✅ Aplicativo '{app}' aberto."
        else:
            return f"❌ Falha ao abrir '{app}'."

    def _tratar_pesquisar_web(self, params: dict) -> str:
        query = params.get("query") or params.get("url") or params.get("topico", "")
        if not query:
            return "Nenhum tópico especificado para pesquisa."
        if web_learner is None:
            return f"⚠ Módulo web_learner indisponível. Pesquisa não realizada: '{query}'"

        n_chunks = web_learner.pesquisar_e_aprender(query, max_paginas=2)
        if n_chunks > 0:
            memoria = web_learner.consultar_memoria(query, n_resultados=3)
            if memoria:
                contexto = "\n".join(f"  • {m['texto'][:250]}..." for m in memoria)
                return (
                    f"✅ Pesquisa concluída. {n_chunks} fragmento(s) "
                    f"aprendido(s) sobre '{query}'.\n\n"
                    f"📚 Contexto recuperado da memória:\n{contexto}"
                )
            return f"✅ Pesquisa concluída. {n_chunks} fragmento(s) armazenado(s) sobre '{query}'."
        else:
            return "⚠ Não foi possível acessar a web no momento. Verifique sua conexão de rede."

    def _tratar_criar_arquivo(self, params: dict) -> str:
        arquivo = params.get("arquivo", "")
        conteudo = params.get("conteudo", "")
        if not arquivo:
            return "Nenhum nome de arquivo especificado."
        try:
            caminho = Path(arquivo)
            caminho.parent.mkdir(parents=True, exist_ok=True)
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(conteudo)
            return f"✅ Arquivo criado: '{caminho}' ({len(conteudo)} caracteres)."
        except OSError as exc:
            return f"❌ Falha ao criar arquivo: {exc}"

    def _tratar_gerar_codigo(self, params: dict) -> str:
        """Exibe o código gerado pelo cérebro com syntax highlight básico."""
        linguagem = params.get("linguagem", "desconhecida")
        codigo = params.get("codigo", "")
        descricao = params.get("descricao", "")
        framework = params.get("framework", "")

        if not codigo:
            return "⚠ Nenhum código foi gerado pelo cérebro."

        # Oferece salvar o código em arquivo
        lines = [
            f"💻 CÓDIGO GERADO — {linguagem.upper()}",
            f"{'─' * 50}",
            f"📝 Descrição: {descricao}" if descricao else "",
            f"📦 Framework: {framework}" if framework else "",
            f"📏 Tamanho: {len(codigo)} caracteres / {len(codigo.splitlines())} linhas",
            f"",
            f"```{linguagem}",
            codigo[:3000],
        ]
        if len(codigo) > 3000:
            lines.append(f"... (truncado — {len(codigo) - 3000} caracteres restantes)")
        lines.append("```")

        # Salva automaticamente se for um caminho válido
        lines.append(f"")
        lines.append(f"💡 Para salvar, diga: 'Jarvis, salve o código como arquivo.py'")

        return "\n".join(l for l in lines if l)

    def _tratar_refatorar_codigo(self, params: dict) -> str:
        """Exibe o código refatorado."""
        linguagem = params.get("linguagem", "desconhecida")
        codigo = params.get("codigo", "")
        objetivo = params.get("objetivo", "melhoria geral")

        if not codigo:
            return "⚠ Nenhum código refatorado foi gerado pelo cérebro."

        lines = [
            f"🔧 CÓDIGO REFATORADO — {linguagem.upper()}",
            f"{'─' * 50}",
            f"🎯 Objetivo: {objetivo}",
            f"📏 Tamanho: {len(codigo)} caracteres",
            f"",
            f"```{linguagem}",
            codigo[:3000],
        ]
        if len(codigo) > 3000:
            lines.append(f"... (truncado)")
        lines.append("```")
        return "\n".join(lines)

    def _tratar_arquitetura(self, params: dict) -> str:
        """Exibe recomendações de arquitetura e design patterns."""
        problema = params.get("problema", "")
        requisitos = params.get("requisitos", "")
        padrao = params.get("padrao", "")
        recomendacao = params.get("recomendacao", "")

        lines = [
            f"🏗️ ANÁLISE DE ARQUITETURA",
            f"{'─' * 50}",
        ]
        if problema:
            lines.append(f"📋 Problema: {problema[:200]}")
        if requisitos:
            lines.append(f"📎 Requisitos: {requisitos[:200]}")
        if padrao:
            lines.append(f"📐 Pattern sugerido: {padrao}")
        if recomendacao:
            lines.append(f"")
            lines.append(f"📝 Recomendação:")
            lines.append(recomendacao[:2000])

        return "\n".join(lines)

    def _tratar_analisar_codigo(self, params: dict) -> str:
        """Exibe o resultado da análise de código (raciocinio do brain)."""
        codigo = params.get("codigo", "")
        linguagem = params.get("linguagem", "desconhecida")
        if not codigo:
            return "Nenhum código fornecido para análise."
        return (
            f"🔍 Análise de Segurança — {linguagem}\n"
            f"{'─' * 40}\n"
            f"O cérebro analisou o código e reportou as vulnerabilidades "
            f"no campo 'raciocinio' da resposta. Verifique os detalhes acima "
            f"no [J.A.R.V.I.S.]."
        )

    def _tratar_diagnostico_windows(self, params: dict) -> str:
        """Executa diagnóstico básico do Windows."""
        tipo = params.get("tipo", "rede")

        if pc_controller is None:
            return "⚠ Módulo pc_controller indisponível."

        comandos = {
            "rede": ["ipconfig /all", "ping -n 2 8.8.8.8", "netstat -ano | findstr ESTABLISHED"],
            "processos": ["tasklist /FI \"STATUS eq RUNNING\" | findstr /V \"svchost\""],
            "servicos": ["sc query state= all | findstr /C:\"SERVICE_NAME\" /C:\"STATE\""],
            "registro": ["reg query \"HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\" /s | findstr DisplayName"],
        }

        cmds = comandos.get(tipo, comandos["rede"])
        resultados = []
        for cmd in cmds[:2]:  # Limita a 2 para não sobrecarregar
            ok, out, err = pc_controller.executar_comando_cmd(cmd)
            if ok and out:
                resultados.append(out[:400])

        if resultados:
            return f"🔧 Diagnóstico [{tipo}]:\n" + "\n───\n".join(resultados)
        return f"⚠ Diagnóstico [{tipo}] não retornou dados."

    def _tratar_processar_video(self, params: dict) -> str:
        """Processa vídeo para aprendizado de padrões linguísticos."""
        url = params.get("url", "")
        caminho = params.get("caminho", "")
        if not url and not caminho:
            return "Nenhum vídeo especificado. Forneça 'url' ou 'caminho'."

        if web_learner is None:
            return "⚠ Módulo web_learner indisponível."

        n_chunks, padroes = web_learner.processar_video_para_aprendizado(
            url=url or None, caminho=caminho or None
        )

        if n_chunks > 0:
            categorias = [k for k, v in padroes.items() if v and k != "estatisticas"]
            return (
                f"✅ Vídeo processado! {n_chunks} fragmentos de transcrição "
                f"armazenados.\n"
                f"📊 Padrões detectados: {len(categorias)} categorias "
                f"({', '.join(categorias[:5])})."
            )
        return "⚠ Não foi possível extrair transcrição do vídeo especificado."

    def _tratar_cyber_defense(self, params: dict) -> str:
        """Executa scan de defesa cibernética completo."""
        target_ip = params.get("target_ip") or params.get("ip", "")

        if cyber_defense is None:
            return "⚠ Módulo cyber_defense indisponível."

        try:
            report = cyber_defense.generate_defense_report(
                target_ip=target_ip if target_ip else None
            )

            summary = report.get("executive_summary", {})
            intrusion = report.get("intrusion", {}).get("summary", {})
            vuln = report.get("vulnerabilities", {})

            lines = [
                f"🛡️ {summary.get('status', 'N/A')}",
                f"",
                f"📊 RESUMO EXECUTIVO:",
                f"   • Alertas de intrusão: {summary.get('intrusion_alerts', 0)}",
                f"   • Score de risco: {summary.get('vulnerability_risk_score', 0)}/100",
                f"   • Recomendações de hardening: {summary.get('hardening_recommendations', 0)}",
                f"",
                f"🔍 DETECÇÃO DE INTRUSÃO:",
                f"   • Conexões ativas: {intrusion.get('total_alerts', 0)} alertas",
                f"   • Status: {intrusion.get('status', 'N/A')}",
                f"",
                f"🛡️ VULNERABILIDADES:",
                f"   • Portas em escuta: {vuln.get('ports', {}).get('total_listening', '?')}",
                f"   • Firewall: {'ATIVO' if vuln.get('firewall', {}).get('firewall_active') else 'DESATIVADO'}",
                f"   • Score de risco: {vuln.get('risk_score', '?')}/100",
            ]

            # Adiciona vulnerabilidades críticas
            vulns = vuln.get("vulnerabilities", [])
            if vulns:
                lines.append(f"")
                lines.append(f"⚠ VULNERABILIDADES ENCONTRADAS:")
                for v in vulns[:5]:
                    lines.append(
                        f"   [{v.get('severity', '?')}] {v.get('detail', '')}"
                    )

            # Adiciona recomendações de hardening
            recommendations = report.get("hardening", {}).get("recommendations", [])
            if recommendations:
                lines.append(f"")
                lines.append(f"🔧 RECOMENDAÇÕES DE HARDENING:")
                for r in recommendations[:5]:
                    lines.append(
                        f"   • [{r.get('risk_reduction', '?')}] "
                        f"{r.get('description', '')}"
                    )

            return "\n".join(lines)

        except Exception as exc:
            return f"❌ Erro ao executar cyber defense scan: {exc}"

    def _tratar_pentest_recon(self, params: dict) -> str:
        """Executa reconhecimento de pentest autorizado."""
        target = params.get("target", "")
        if not target:
            return "⛔ Target não especificado. Forneça 'target' com IP/domínio autorizado."

        try:
            import pentest_engine
        except ImportError:
            return "⚠ Módulo pentest_engine indisponível."

        engine = pentest_engine.PentestEngine()
        ok, msg = engine.set_scope(
            authorized=True, target=target,
            authorized_by=params.get("authorized_by", "Launcher User"),
            environment=params.get("environment", "lab"),
            objective=params.get("objective", "Recon autorizado"),
        )
        if not ok:
            return f"⛔ {msg}"

        recon = engine.recon_target()
        if "error" in recon:
            return f"⛔ {recon['error']}"

        return (
            f"🔍 RECON — {target}\n"
            f"{'─' * 40}\n"
            f"   IP: {recon.get('resolved_ip')}\n"
            f"   Reverse DNS: {recon.get('reverse_dns')}\n"
            f"   HTTP: {'✅' if recon.get('http_reachable') else '❌'}\n"
            f"   HTTPS: {'✅' if recon.get('https_reachable') else '❌'}"
        )

    def _tratar_pentest_scan(self, params: dict) -> str:
        """Executa scan de portas/serviços do pentest."""
        target = params.get("target", "")
        if not target:
            return "⛔ Target não especificado."

        try:
            import pentest_engine
        except ImportError:
            return "⚠ Módulo pentest_engine indisponível."

        ports_param = params.get("ports", [])
        ports = ports_param if isinstance(ports_param, list) and ports_param else None

        engine = pentest_engine.PentestEngine()
        engine.set_scope(
            authorized=True, target=target,
            authorized_by=params.get("authorized_by", "Launcher User"),
            environment=params.get("environment", "lab"),
        )

        scan = engine.scan_ports(ports)
        if "error" in scan:
            return f"⛔ {scan['error']}"

        open_ports = scan.get("open_ports", [])
        lines = [
            f"🔍 PORT SCAN — {target}",
            f"{'─' * 40}",
            f"   Escaneadas: {scan.get('total_scanned')} portas",
            f"   Abertas: {len(open_ports)}",
        ]
        for p in open_ports[:15]:
            lines.append(
                f"   • {p['port']}/tcp — {p['service']}"
                + (f" [{p['banner'][:50]}]" if p.get('banner') else "")
            )
        return "\n".join(lines)

    def _tratar_pentest_report(self, params: dict) -> str:
        """Gera relatório do pentest."""
        target = params.get("target", "")
        if not target:
            return "⛔ Target não especificado."

        try:
            import pentest_engine
        except ImportError:
            return "⚠ Módulo pentest_engine indisponível."

        ports_param = params.get("ports", [])
        ports = ports_param if isinstance(ports_param, list) and ports_param else None

        results = pentest_engine.quick_pentest(
            target=target, ports=ports,
            authorized_by=params.get("authorized_by", "Launcher User"),
            environment=params.get("environment", "lab"),
        )

        if "error" in results:
            return f"⛔ {results['error']}"

        summary = results.get("report", {}).get("executive_summary", {})
        return (
            f"📋 PENTEST REPORT — {target}\n"
            f"{'─' * 40}\n"
            f"   Descobertas: {summary.get('total_findings', 0)}\n"
            f"   Risk Level: {summary.get('risk_level', 'N/A')}\n"
            f"   Risk Score: {summary.get('risk_score', 0)}\n"
            f"   🔴 CRITICAL: {summary.get('severity_breakdown', {}).get('CRITICAL', 0)}\n"
            f"   🟠 HIGH: {summary.get('severity_breakdown', {}).get('HIGH', 0)}\n"
            f"   🟡 MEDIUM: {summary.get('severity_breakdown', {}).get('MEDIUM', 0)}\n"
            f"\n"
            f"💡 Relatório completo via pentest_engine.export_report_markdown()"
        )


# ═══════════════════════════════════════════════════════════════════════════
# AUTOMAÇÃO EM BACKGROUND + COMMAND PALETTE + HEALTH DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════


class AutomacaoWorker(QThread):
    """Executa uma função de automação em segundo plano sem travar a UI."""

    concluido = Signal(str)
    falhou = Signal(str)

    def __init__(self, funcao, parent=None):
        super().__init__(parent)
        self._funcao = funcao

    def run(self) -> None:
        try:
            sucesso, resumo = self._funcao()
        except Exception as exc:
            self.falhou.emit(f"Erro na automação: {exc}")
            return
        if sucesso:
            self.concluido.emit(resumo)
        else:
            self.falhou.emit(resumo)


class NetworkMapPanel(QWidget):
    """Aba do HUD que exibe a topologia da rede local (varredura assíncrona)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: AutomacaoWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QLabel("TOPOLOGIA DA REDE LOCAL")
        header.setStyleSheet(
            f"color: {COLOR_CYAN}; font-size: 14px; font-weight: bold; "
            f"letter-spacing: 3px;")
        layout.addWidget(header)

        self._texto = QTextEdit()
        self._texto.setObjectName("chatHistory")
        self._texto.setReadOnly(True)
        layout.addWidget(self._texto, stretch=1)

        self._btn = QPushButton("RESCANEAR REDE")
        self._btn.clicked.connect(self.rescanear)
        layout.addWidget(self._btn)

        self._texto.setPlainText(
            "Clique em RESCANEAR REDE para mapear os dispositivos da rede local."
        )

    def rescanear(self) -> None:
        if network_mapper is None:
            self._texto.setPlainText("[ERRO] Módulo network_mapper indisponível.")
            return
        if self._worker is not None and self._worker.isRunning():
            return
        self._btn.setEnabled(False)
        self._texto.setPlainText("[VARRENDO A REDE LOCAL...]")
        self._worker = AutomacaoWorker(network_mapper.executar_varredura)
        self._worker.concluido.connect(self._on_ok)
        self._worker.falhou.connect(self._on_err)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.finished.connect(lambda: self._btn.setEnabled(True))
        self._worker.start()

    def _on_ok(self, texto: str) -> None:
        self._texto.setPlainText(texto)

    def _on_err(self, erro: str) -> None:
        self._texto.setPlainText(f"[ERRO] {erro}")


class CommandPaletteDialog(QDialog):
    """Barra de pesquisa rápida de atalhos e automações."""

    comandoSelecionado = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paleta de Comandos — J.A.R.V.I.S")
        self.setMinimumSize(460, 340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._busca = QLineEdit()
        self._busca.setPlaceholderText("Digite para filtrar comandos...")
        self._busca.textChanged.connect(self._filtrar)
        layout.addWidget(self._busca)

        self._lista = QListWidget()
        self._lista.itemActivated.connect(self._selecionar)
        self._lista.itemClicked.connect(self._selecionar)
        layout.addWidget(self._lista)

        self._carregar()
        self._busca.setFocus()

    def _carregar(self) -> None:
        try:
            self._comandos = config_manager.obter_comandos_palette()
        except Exception:
            self._comandos = []
        self._filtrar("")

    def _filtrar(self, texto: str) -> None:
        self._lista.clear()
        texto = texto.lower()
        for cmd in self._comandos:
            nome = cmd.get("nome", "")
            desc = cmd.get("descricao", "")
            if texto in nome.lower() or texto in desc.lower():
                item = QListWidgetItem(f"{nome}  —  {desc}")
                item.setData(Qt.ItemDataRole.UserRole, nome)
                self._lista.addItem(item)

    def _selecionar(self, item) -> None:
        nome = item.data(Qt.ItemDataRole.UserRole)
        self.comandoSelecionado.emit(nome)
        self.accept()


class HealthDashboardWidget(QWidget):
    """Widget compacto de monitoramento (CPU/VRAM/RAM) com limite dinâmico."""

    limiteAlto = Signal(bool)  # True ao ultrapassar 85%, False ao normalizar

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._lbl_cpu = QLabel("CPU: --%")
        self._lbl_ram = QLabel("RAM: --%")
        self._lbl_vram = QLabel("VRAM: --%")
        for lbl in (self._lbl_cpu, self._lbl_ram, self._lbl_vram):
            lbl.setObjectName("valueLabel")
            layout.addWidget(lbl)
        layout.addStretch()

        self._throttled = False
        self._gpu_ticks = 0
        self._vram_cache = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._atualizar)
        self._timer.start(2000)
        # Primeira leitura adiada (não-bloqueante) para não travar o startup.
        QTimer.singleShot(0, self._atualizar)

    def _atualizar(self) -> None:
        cpu = self._ler_cpu()
        ram = self._ler_ram()
        # VRAM cacheada (evita spawnar nvidia-smi a cada 2s).
        self._gpu_ticks += 1
        if self._gpu_ticks >= 5:
            self._gpu_ticks = 0
            self._vram_cache = self._ler_vram()
        vram = self._vram_cache

        self._lbl_cpu.setText(f"CPU: {cpu:.0f}%")
        self._lbl_ram.setText(f"RAM: {ram:.0f}%")
        vram_txt = f"{vram:.0f}%" if vram is not None else "--%"
        self._lbl_vram.setText(f"VRAM: {vram_txt}")

        # Registra amostra de hardware para telemetria (média diária).
        try:
            if config_manager is not None:
                config_manager.registrar_amostra_hardware(ram, vram)
        except Exception:
            pass

        alto = ram > 85.0 or (vram is not None and vram > 85.0)
        if alto and not self._throttled:
            self._throttled = True
            self.limiteAlto.emit(True)
        elif not alto and self._throttled:
            # Histerese: só normaliza abaixo de 75%.
            if ram < 75.0 and (vram is None or vram < 75.0):
                self._throttled = False
                self.limiteAlto.emit(False)

    def _ler_cpu(self) -> float:
        try:
            import psutil
            return psutil.cpu_percent(interval=None)
        except Exception:
            return 0.0

    def _ler_ram(self) -> float:
        try:
            import psutil
            return psutil.virtual_memory().percent
        except Exception:
            return 0.0

    def _ler_vram(self):
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                return round(gpus[0].memoryUtil * 100.0, 1)
        except Exception:
            pass
        return None


# ═══════════════════════════════════════════════════════════════════════════
# JANELA PRINCIPAL — SALLES INDUSTRIES Neural Constellation HUD
# ═══════════════════════════════════════════════════════════════════════════

# Mapeamento comando/ação → nó orbital da constelação (integração visual).
_MODULO_MAP: dict[str, str] = {
    # comandos da paleta
    "web": "web", "lab": "cyber_lab", "inspect": "cyber_lab",
    "net-map": "network", "net-check": "network",
    "db-query": "database", "db-schema": "database", "db-ask": "database",
    "snap": "vision", "self-audit": "optimizer", "research": "memory",
    "autofix": "coder", "record": "memory", "mode": "optimizer",
    # ações do cérebro
    "pesquisar_web": "web", "analisar_codigo": "auditor",
    "gerar_codigo": "coder", "refatorar_codigo": "coder",
    "arquitetura": "arquiteto", "diagnostico_windows": "network",
    "cyber_defense": "cyber_lab", "pentest_recon": "cyber_lab",
    "pentest_scan": "cyber_lab", "pentest_report": "cyber_lab",
    "processar_video": "vision",
}

_STATUS_TEXTO: dict[str, str] = {
    "standby": "[ STANDBY ]",
    "active": "[ ATIVO ]",
    "processing": "[ PROCESSANDO DADOS ]",
}

# Nós orbitais válidos da constelação (ignora ações de pura conversa).
_NODES_VALIDOS: frozenset[str] = frozenset({
    "arquiteto", "coder", "auditor", "cyber_lab", "database",
    "web", "network", "memory", "vision", "optimizer",
})


class LauncherWindow(QMainWindow):
    """Janela principal do Launcher HUD (Constelação Neural Holográfica)."""

    def __init__(self):
        super().__init__()
        self._processo_jarvis: subprocess.Popen | None = None
        self._init_worker: InitWorker | None = None
        self._subsystem_status: dict[str, bool] = {}
        self._tray_icon: QSystemTrayIcon | None = None
        self._hotkey_listener = None
        self._health: HealthDashboardWidget | None = None
        self._log_streamer = None
        self._throttled = False
        self._build_ui()
        self._apply_style()
        # Inicia a inicialização em segundo plano
        self._iniciar_subsistemas()
        # Bandeja do sistema + atalho global de abrir/ocultar
        self._criar_bandeja()
        self._iniciar_hotkey_global()
        # Diagnóstico assíncrono (brain) + Live Log Streamer
        self._configurar_diagnostico()
        self._iniciar_log_streamer()

    def _build_ui(self) -> None:
        self.setWindowTitle("SALLES INDUSTRIES — Neural Constellation HUD")
        self.setMinimumSize(1100, 720)
        self.resize(1280, 800)

        # Pré-inicializa atributos referenciados por outros métodos.
        self._core = None
        self._tree = None
        self._hud_monitor = None
        self._btn_save = None

        # Painel de configurações (aberto sob demanda via diálogo).
        self._settings = SettingsPanel()
        self._settings.configChanged.connect(self._on_config_changed)

        central = QWidget()
        self.setCentralWidget(central)
        # Habilita Drag-and-Drop de arquivos na janela (ingestão multimodal).
        # O widget central NÃO aceita drops, para que o evento chegue à janela.
        self.setAcceptDrops(True)
        central.setAcceptDrops(False)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # ── Header ──
        header = QHBoxLayout()
        header.setSpacing(14)

        title = QLabel("SALLES INDUSTRIES")
        title.setObjectName("titleLabel")
        header.addWidget(title)

        sub = QLabel("NEURAL CONSTELLATION // HUD HOLOGRÁFICO")
        sub.setStyleSheet(
            f"color: {COLOR_CYAN}; font-size: 11px; letter-spacing: 3px;")
        header.addWidget(sub)
        header.addStretch()

        self._btn_config = QPushButton("CONFIG")
        self._btn_config.setObjectName("quickAction")
        self._btn_config.clicked.connect(self._abrir_configuracoes)
        header.addWidget(self._btn_config)

        self._btn_activate = QPushButton("INICIAR  J.A.R.V.I.S.")
        self._btn_activate.setObjectName("btnActivate")
        self._btn_activate.clicked.connect(self._on_activate)
        self._btn_activate.setEnabled(False)  # Só ativa após init
        header.addWidget(self._btn_activate)
        root.addLayout(header)

        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFixedHeight(2)
        root.addWidget(sep)

        # ── Conteúdo central: árvore de diagnóstico + constelação ──
        content = QHBoxLayout()
        content.setSpacing(16)

        if hud_widgets is not None and hasattr(hud_widgets, "HudDiagnosticTree"):
            self._tree = hud_widgets.HudDiagnosticTree()
            self._tree.setFixedWidth(252)
            content.addWidget(self._tree)

        if hud_widgets is not None and hasattr(hud_widgets, "NeuralCoreConstellation"):
            self._core = hud_widgets.NeuralCoreConstellation()
        else:
            self._core = SallesCoreVisualizer()
        self._core.setMinimumSize(340, 340)
        self._core.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content.addWidget(self._core, stretch=1)

        root.addLayout(content, stretch=1)

        # ── Rodapé: barra de status + chat glassmorphism ──
        footer = QVBoxLayout()
        footer.setSpacing(10)

        status_bar = QFrame()
        status_bar.setObjectName("hudCard")
        status_row = QHBoxLayout(status_bar)
        status_row.setContentsMargins(14, 8, 14, 8)
        status_row.setSpacing(12)

        self._status_label = QLabel("[ STANDBY ]")
        self._status_label.setObjectName("statusBarLabel")
        status_row.addWidget(self._status_label)

        status_row.addStretch()

        self._detail_label = QLabel("Inicializando subsistemas...")
        self._detail_label.setStyleSheet(
            f"color: {COLOR_TEXT_DIM}; font-size: 11px;")
        status_row.addWidget(self._detail_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedWidth(180)
        self._progress_bar.setFixedHeight(10)
        status_row.addWidget(self._progress_bar)

        footer.addWidget(status_bar)

        # Chat integrado em painel flutuante glassmorphism.
        self._chat_console = ChatConsole()
        self._chat_console.setObjectName("chatPanel")
        self._chat_console.coreStateRequest.connect(self._on_core_state_request)
        self._chat_console.hideRequested.connect(self.hide)
        self._chat_console.tarefaConcluida.connect(self._notificar_tarefa_concluida)
        self._chat_console.paletteRequested.connect(self._abrir_paleta_comandos)
        self._chat_console.moduloAtivo.connect(self._on_modulo_ativo)
        self._chat_console.moduloInativo.connect(self._on_modulo_inativo)
        # Evita que o histórico/input do chat interceptem o drop de arquivos.
        if hasattr(self._chat_console, "_history"):
            self._chat_console._history.setAcceptDrops(False)
        if hasattr(self._chat_console, "_input"):
            self._chat_console._input.setAcceptDrops(False)
        footer.addWidget(self._chat_console, stretch=1)

        root.addLayout(footer, stretch=1)

        # Health dashboard (oculto) — preserva a lógica de throttle dinâmico.
        self._health = HealthDashboardWidget(self)
        self._health.limiteAlto.connect(self._on_limite_recursos)

        # Atalho interno: Ctrl+Shift+P abre a paleta de comandos.
        self._palette_shortcut = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        self._palette_shortcut.activated.connect(self._abrir_paleta_comandos)

    def _apply_style(self) -> None:
        self.setStyleSheet(STYLESHEET)

    # ── Drag-and-Drop (ingestão multimodal) ──

    def dragEnterEvent(self, event) -> None:
        """Aceita o arrasto de arquivos locais sobre a janela."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        """Recebe arquivos soltos na janela e dispara a ingestão multimodal."""
        arquivos = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.toLocalFile()
        ]
        if not arquivos:
            event.ignore()
            return
        event.acceptProposedAction()
        for caminho in arquivos:
            if hasattr(self, "_chat_console"):
                self._chat_console.ingestir_arquivo(caminho)

    # ── Inicialização em segundo plano ──

    def _iniciar_subsistemas(self) -> None:
        """Inicia a inicialização paralela dos subsistemas."""
        self._init_worker = InitWorker()
        self._init_worker.progress.connect(self._on_init_progress)
        self._init_worker.subsystemReady.connect(self._on_subsystem_ready)
        self._init_worker.allReady.connect(self._on_all_ready)
        self._init_worker.start()

    @Slot(str, int)
    def _on_init_progress(self, mensagem: str, percentual: int) -> None:
        self._detail_label.setText(mensagem)
        self._progress_bar.setValue(percentual)

    @Slot(str, bool)
    def _on_subsystem_ready(self, nome: str, sucesso: bool) -> None:
        self._subsystem_status[nome] = sucesso
        status_icon = "✓" if sucesso else "✗"
        self._detail_label.setText(
            f"{status_icon} {nome} — {'OK' if sucesso else 'FALHA'}"
        )

    @Slot(dict)
    def _on_all_ready(self, results: dict) -> None:
        all_ok = all(results.values())
        if all_ok:
            self._detail_label.setText("Todos os subsistemas prontos. Pronto para iniciar.")
            self._status_label.setText("CORE READY")
            self._progress_bar.setValue(100)
            if self._core is not None:
                self._core.set_state("standby")
        else:
            falhas = [k for k, v in results.items() if not v]
            self._detail_label.setText(
                f"Atenção: {', '.join(falhas)} não inicializaram."
            )
            self._status_label.setText("CORE DEGRADED")
            self._progress_bar.setValue(100)
        self._btn_activate.setEnabled(True)
        self._progress_bar.setVisible(False)

        # Notifica a bandeja sobre o resultado da inicialização.
        if all_ok:
            self.notificar_operador(
                "J.A.R.V.I.S. pronto",
                "Todos os subsistemas inicializados com sucesso.",
                "INFO",
            )
        else:
            self.notificar_operador(
                "J.A.R.V.I.S. — inicialização parcial",
                "Alguns subsistemas falharam. Verifique o console.",
                "WARNING",
            )

    # ── Slots ──

    def _atualizar_btn_save(self, texto: str, estilo: str = "") -> None:
        """Atualiza o botão de salvar de forma segura (evita crash se destruído)."""
        btn = getattr(self, "_btn_save", None)
        if btn is None:
            return
        try:
            btn.setText(texto)
            btn.setStyleSheet(estilo)
        except RuntimeError:
            # Objeto Qt já destruído (diálogo fechado) — ignora com segurança.
            pass

    @Slot()
    def _on_config_changed(self) -> None:
        self._atualizar_btn_save(
            "SALVAR CONFIGURACOES *",
            f"QPushButton {{ border: 1px solid {COLOR_ORANGE}; "
            f"color: {COLOR_ORANGE}; }}",
        )

    @Slot()
    def _on_save(self) -> None:
        if self._settings.salvar():
            self._atualizar_btn_save("SALVAR CONFIGURACOES", "")
            QMessageBox.information(
                self, "SALLES INDUSTRIES",
                "Configurações salvas com sucesso.")
        else:
            QMessageBox.warning(
                self, "SALLES INDUSTRIES",
                "Falha ao salvar configurações. Verifique as permissões.")

    @Slot(str)
    def _on_core_state_request(self, state: str) -> None:
        """Recebe solicitação de mudança de estado do núcleo (HUD reativo)."""
        if self._core is not None:
            self._core.set_state(state)
        self._status_label.setText(_STATUS_TEXTO.get(state, f"[ {state.upper()} ]"))

    # ── Integração visual-funcional (acendimento dos nós orbitais) ──

    @Slot(str)
    def _on_modulo_ativo(self, nome: str) -> None:
        """Acende o nó orbital do módulo/subagente que entrou em execução."""
        if nome == "ingest":
            # Ingestão multimodal envolve Visão + Memória.
            self._pulsar_modulo("vision")
            self._pulsar_modulo("memory")
            return
        node = _MODULO_MAP.get(nome, nome)
        if node not in _NODES_VALIDOS:
            return  # ações de pura conversa não acendem módulos
        self._pulsar_modulo(node)

    @Slot(str)
    def _on_modulo_inativo(self, nome: str) -> None:
        """Apaga indicadores quando um módulo em background é concluído."""
        if nome == "ingest":
            if self._tree is not None:
                self._tree.set_item("runner", False, "IDLE")
            return
        node = _MODULO_MAP.get(nome, nome)
        if node not in _NODES_VALIDOS or self._tree is None:
            return
        self._tree.set_item("runner", False, "IDLE")
        if node == "network":
            self._tree.set_item("network", False, "READY")
        elif node == "cyber_lab":
            self._tree.set_item("lab", False, "READY")

    def _pulsar_modulo(self, node: str) -> None:
        """Pulsa o nó orbital e atualiza a árvore de diagnóstico."""
        if self._core is not None and hasattr(self._core, "pulse_node"):
            self._core.pulse_node(node)
        if self._tree is not None:
            self._tree.set_item("runner", True, "RUNNING")
            if node == "network":
                self._tree.set_item("network", True, "SCANNING")
            elif node == "cyber_lab":
                self._tree.set_item("lab", True, "RUNNING")

    def _abrir_configuracoes(self) -> None:
        """Abre o painel de configurações em um diálogo modal."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Configurações — SALLES INDUSTRIES")
        dlg.setMinimumSize(440, 460)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)
        lay.addWidget(self._settings, stretch=1)
        self._btn_save = QPushButton("SALVAR CONFIGURACOES")
        self._btn_save.clicked.connect(self._on_save)
        lay.addWidget(self._btn_save)
        dlg.exec()

    # ── Command Palette ──

    def _abrir_paleta_comandos(self) -> None:
        """Abre a barra de pesquisa rápida de comandos."""
        dlg = CommandPaletteDialog(self)
        dlg.comandoSelecionado.connect(self._on_comando_selecionado)
        dlg.exec()

    def _on_comando_selecionado(self, comando: str) -> None:
        """Recebe um comando selecionado na paleta e o encaminha ao chat."""
        self._chat_console._input.setText(comando)
        self._chat_console._on_enviar()

    # ── Otimização dinâmica de hardware ──

    def _on_limite_recursos(self, alto: bool) -> None:
        """Aplica/restaura o throttle dinâmico de recursos do Llama 3.2."""
        if config_manager is None:
            return
        if alto:
            if not self._throttled:
                self._throttled = True
                try:
                    config_manager.salvar_configuracao({"cpu_threads": 2, "gpu_layers": 0})
                except Exception:
                    pass
                self.notificar_operador(
                    "Otimização dinâmica",
                    "Alto consumo de RAM/VRAM detectado. Recursos do Llama 3.2 limitados.",
                    "WARNING",
                )
        else:
            if self._throttled:
                self._throttled = False
                try:
                    config_manager.auto_configurar_hardware()
                except Exception:
                    pass
                self.notificar_operador(
                    "Otimização dinâmica",
                    "Consumo normalizado. Recursos do Llama 3.2 restaurados.",
                    "INFO",
                )

    # ── Diagnóstico assíncrono + Live Log Streamer ──

    def _configurar_diagnostico(self) -> None:
        """Registra o callback que recebe diagnósticos do brain (thread)."""
        if brain is None:
            return

        def callback(resultado):
            texto = ""
            if isinstance(resultado, dict):
                texto = resultado.get("resposta_voz", "") or ""
            else:
                texto = str(resultado)
            self._chat_console.diagnosticoExterno.emit(texto)

        try:
            brain.configurar_diagnostico_callback(callback)
        except Exception:
            pass

    def _iniciar_log_streamer(self) -> None:
        """Inicia o monitor de log em tempo real (arquivo padrão, se existir)."""
        try:
            from log_streamer import LogStreamerWorker
        except ImportError:
            return
        alvo = _SCRIPT_DIR / "data" / "logs" / "jarvis.log"
        if not alvo.exists():
            return  # sem arquivo de log para monitorar no momento
        self._log_streamer = LogStreamerWorker(self)
        self._log_streamer.lineRead.connect(self._chat_console.anexar_linha_log)
        self._log_streamer.errorChunk.connect(self._on_log_error)
        self._log_streamer.monitorar_arquivo(str(alvo))
        self._log_streamer.start()

    def _on_log_error(self, chunk: str) -> None:
        """Envia um bloco de erro detectado para o diagnóstico do brain."""
        self._chat_console._append_system(f"[ERRO DETECTADO NO LOG]\n{chunk}")
        try:
            if brain is not None:
                brain.enfileirar_diagnostico(chunk)
        except Exception:
            pass

    @Slot()
    def _on_activate(self) -> None:
        if self._processo_jarvis is not None:
            reply = QMessageBox.question(
                self, "SALLES INDUSTRIES",
                "O sistema já está ativo. Deseja desligar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self._desligar_nucleo()
            return

        # Salva antes de iniciar
        self._settings.salvar()
        self._atualizar_btn_save("SALVAR CONFIGURACOES", "")

        # Ativa UI
        if self._core is not None:
            self._core.set_state("active")
        self._status_label.setText("SALLES CORE: ACTIVE")
        self._status_label.setStyleSheet(
            f"color: {COLOR_GREEN}; font-size: 20px; font-weight: bold; "
            f"letter-spacing: 4px;")
        self._detail_label.setText("SALLES CORE ativo — J.A.R.V.I.S. operacional...")
        self._btn_activate.setText("DESLIGAR  SISTEMA")
        self._btn_activate.setStyleSheet(
            f"QPushButton#btnActivate {{ "
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 {COLOR_RED}, stop:1 {COLOR_ORANGE}); "
            f"color: white; font-size: 15px; padding: 14px 40px; "
            f"border-radius: 6px; border: none; letter-spacing: 3px; }}")

        # Spawna app.py
        app_path = _SCRIPT_DIR / "app.py"

        # Inicia monitor de hardware
        if self._hud_monitor is not None:
            self._hud_monitor.start_monitoring()

        try:
            self._processo_jarvis = subprocess.Popen(
                [sys.executable, str(app_path)],
                cwd=str(_SCRIPT_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._detail_label.setText(
                f"SALLES CORE ativo — J.A.R.V.I.S. (PID {self._processo_jarvis.pid})...")
        except Exception as exc:
            QMessageBox.critical(
                self, "SALLES INDUSTRIES",
                f"Falha ao iniciar J.A.R.V.I.S.:\n{exc}")
            self._restaurar_ui_inativa()

    def _desligar_nucleo(self) -> None:
        if self._processo_jarvis:
            try:
                self._processo_jarvis.terminate()
                self._processo_jarvis.wait(timeout=5)
            except Exception:
                try:
                    self._processo_jarvis.kill()
                except Exception:
                    pass
            self._processo_jarvis = None

        # Encerra o processo do Ollama se tiver sido iniciado pelo launcher
        try:
            if brain is not None:
                brain.encerrar_ollama()
        except Exception:
            pass

        self._restaurar_ui_inativa()

    def _restaurar_ui_inativa(self) -> None:
        # Para monitor de hardware
        if self._hud_monitor is not None:
            self._hud_monitor.stop_monitoring()

        if self._core is not None:
            self._core.set_state("standby")
        self._status_label.setText("CORE STANDBY")
        self._status_label.setStyleSheet(
            f"color: {COLOR_CYAN}; font-size: 22px; font-weight: bold; "
            f"letter-spacing: 6px;")
        self._detail_label.setText("Aguardando inicializacao do sistema...")
        self._btn_activate.setText("INICIAR  J.A.R.V.I.S.")
        self._btn_activate.setStyleSheet("")

    # ── System Tray + Hotkey Global + Notificações ──

    def _criar_icone_neon(self) -> QIcon:
        """Gera um ícone Sci-Fi neon (núcleo ciano com anel magenta)."""
        pm = QPixmap(64, 64)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = cy = 32.0
        painter.setPen(QPen(QColor(COLOR_MAGENTA), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(cx - 28, cy - 28, 56, 56))
        grad = QRadialGradient(cx, cy, 22)
        grad.setColorAt(0, QColor(240, 253, 255))
        grad.setColorAt(0.5, QColor(COLOR_CYAN))
        grad.setColorAt(1, QColor(COLOR_PURPLE))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(QRectF(cx - 22, cy - 22, 44, 44))
        painter.end()
        return QIcon(pm)

    def _criar_bandeja(self) -> None:
        """Cria o ícone da bandeja do sistema com menu de contexto."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray_icon = QSystemTrayIcon(self._criar_icone_neon(), self)
        self._tray_icon.setToolTip("J.A.R.V.I.S. — SALLES INDUSTRIES")

        menu = QMenu()
        menu.addAction("Exibir Central J.A.R.V.I.S", self._mostrar_janela)
        menu.addAction("Status de Tarefas em Background", self._notificar_status_tarefas)
        menu.addSeparator()
        menu.addAction("Sair / Encerrar Sistema", self._encerrar_sistema)

        self._tray_icon.setContextMenu(menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_janela()

    def _iniciar_hotkey_global(self) -> None:
        """Inicia o listener do atalho global (Alt+Space / Ctrl+Shift+J)."""
        self._hotkey_listener = None
        if GlobalHotkeyListener is None:
            return
        self._hotkey_listener = GlobalHotkeyListener(self)
        self._hotkey_listener.triggered.connect(self._toggle_janela)
        if not self._hotkey_listener.iniciar():
            self._hotkey_listener = None

    def _toggle_janela(self) -> None:
        """Abre/oculta a janela conforme o estado atual."""
        if self.isMinimized():
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self._focar_chat()
        elif not self.isVisible():
            self._mostrar_janela()
        elif not self.isActiveWindow():
            self.raise_()
            self.activateWindow()
            self._focar_chat()
        else:
            self.hide()

    def _mostrar_janela(self) -> None:
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._focar_chat()

    def _focar_chat(self) -> None:
        if hasattr(self, "_chat_console"):
            self._chat_console.focar_input()

    def notificar_operador(self, titulo: str, mensagem: str, nivel: str = "INFO") -> None:
        """Exibe uma notificação nativa na bandeja do sistema."""
        if getattr(self, "_tray_icon", None) is None:
            return
        icones = {
            "INFO": QSystemTrayIcon.MessageIcon.Information,
            "WARNING": QSystemTrayIcon.MessageIcon.Warning,
            "ERROR": QSystemTrayIcon.MessageIcon.Critical,
        }
        try:
            self._tray_icon.showMessage(
                titulo,
                mensagem,
                icones.get(nivel.upper(), QSystemTrayIcon.MessageIcon.Information),
                4000,
            )
        except Exception:
            pass
        if nivel.upper() == "ERROR":
            QApplication.beep()

    def _notificar_status_tarefas(self) -> None:
        status = ", ".join(
            f"{k}={'OK' if v else 'FALHA'}" for k, v in self._subsystem_status.items()
        ) or "Sem dados."
        self.notificar_operador("Status de Background", f"Subsistemas: {status}", "INFO")

    def _notificar_tarefa_concluida(self, mensagem: str) -> None:
        """Notifica a bandeja apenas quando a janela estiver oculta."""
        if not self.isVisible():
            self.notificar_operador("Tarefa Concluída", mensagem, "INFO")

    def _parar_threads_background(self) -> None:
        """Encerra threads em background (log streamer, workers do chat)."""
        try:
            if self._log_streamer is not None:
                self._log_streamer.parar()
        except Exception:
            pass
        try:
            self._chat_console.parar_workers()
        except Exception:
            pass

    def _encerrar_sistema(self) -> None:
        try:
            if self._hotkey_listener is not None:
                self._hotkey_listener.parar()
        except Exception:
            pass
        try:
            if self._tray_icon is not None:
                self._tray_icon.hide()
        except Exception:
            pass
        self._parar_threads_background()
        self._desligar_nucleo()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        if self._init_worker and self._init_worker.isRunning():
            self._init_worker.cancel()
            self._init_worker.wait(2000)
        self._parar_threads_background()
        self._desligar_nucleo()
        event.accept()


# ═══════════════════════════════════════════════════════════════════════════
# PONTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SALLES INDUSTRIES — Quantum OS v2.0")
    # Mantém o app vivo na bandeja mesmo com a janela oculta.
    app.setQuitOnLastWindowClosed(False)

    window = LauncherWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
