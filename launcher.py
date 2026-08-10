"""
launcher.py — Interface HUD da SALLES INDUSTRIES v2.0 (Quantum OS / Sci-Fi)

Interface gráfica cyberpunk com esfera 3D de partículas reativas (Salles Core 3D),
painel de configurações, console de chat textual interativo e inicialização
unificada em segundo plano.

Design Dark Glassmorphism com bordas ciano, transições de cor reativas ao estado
do assistente (Ciano → Verde Neon / Azul Elétrico) e animação fluida a 60 FPS.

Capacidades:
  - Salles Core 3D: partículas projetadas nos eixos X, Y, Z com rotação contínua
  - Reatividade a áudio/estado: pulsa e transiciona cores com voice_engine.ouvindo()
  - Inicialização unificada em segundo plano (config, kill_switch, brain, voice)
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
    QPainterPath,
    QAction,
    QTextCursor,
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
    QCheckBox,
    QScrollBar,
    QProgressBar,
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
    import voice_engine
except ImportError:
    voice_engine = None  # type: ignore[assignment]

try:
    import kill_switch
except ImportError:
    kill_switch = None  # type: ignore[assignment]


# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTES DE ESTILO HUD — DARK GLASSMORPHISM
# ═══════════════════════════════════════════════════════════════════════════

COLOR_BG = "#080b10"
COLOR_PANEL_BG = "rgba(8, 11, 16, 0.90)"
COLOR_CYAN = "#00f0ff"
COLOR_BLUE = "#0088ff"
COLOR_ELECTRIC_BLUE = "#0055ff"
COLOR_GREEN = "#00ff88"
COLOR_NEON_GREEN = "#00ff44"
COLOR_ORANGE = "#ff8833"
COLOR_RED = "#ff2244"
COLOR_BORDER = "rgba(0, 240, 255, 0.25)"
COLOR_BORDER_ACTIVE = "rgba(0, 240, 255, 0.60)"
COLOR_TEXT = "#c8d6e5"
COLOR_TEXT_BRIGHT = "#e8f0ff"
COLOR_TEXT_DIM = "#5a6a7e"

FONT_FAMILY = "Consolas, Courier New, monospace"

STYLESHEET = f"""
/* ===== GLOBAL ===== */
QMainWindow {{
    background-color: {COLOR_BG};
}}

QWidget {{
    color: {COLOR_TEXT};
    font-family: {FONT_FAMILY};
    font-size: 12px;
}}

/* ===== TAB WIDGET ===== */
QTabWidget::pane {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    background-color: {COLOR_PANEL_BG};
}}

QTabBar::tab {{
    background: rgba(0, 0, 0, 0.35);
    border: 1px solid {COLOR_BORDER};
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    padding: 6px 16px;
    color: {COLOR_TEXT_DIM};
    font-weight: bold;
    font-size: 11px;
    letter-spacing: 2px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background: {COLOR_PANEL_BG};
    color: {COLOR_CYAN};
    border-color: {COLOR_BORDER_ACTIVE};
}}

QTabBar::tab:hover:!selected {{
    color: {COLOR_TEXT};
    background: rgba(0, 240, 255, 0.06);
}}

/* ===== GROUP BOX ===== */
QGroupBox {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    margin-top: 14px;
    padding: 18px 12px 10px 12px;
    background-color: {COLOR_PANEL_BG};
    font-weight: bold;
    font-size: 13px;
    color: {COLOR_CYAN};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
    color: {COLOR_CYAN};
}}

/* ===== SLIDERS ===== */
QSlider::groove:horizontal {{
    background: rgba(0, 240, 255, 0.10);
    height: 6px;
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLOR_BLUE}, stop:1 {COLOR_CYAN});
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
    border: 1px solid {COLOR_CYAN};
}}

QSlider::handle:horizontal:hover {{
    border: 1px solid white;
}}

QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLOR_BLUE}, stop:1 {COLOR_CYAN});
    border-radius: 3px;
}}

/* ===== COMBO BOX ===== */
QComboBox {{
    background: rgba(0, 0, 0, 0.4);
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 4px 10px;
    color: {COLOR_TEXT_BRIGHT};
    min-height: 22px;
}}

QComboBox:hover {{
    border: 1px solid {COLOR_CYAN};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox QAbstractItemView {{
    background: #111820;
    border: 1px solid {COLOR_BORDER};
    color: {COLOR_TEXT};
    selection-background-color: rgba(0, 240, 255, 0.15);
}}

/* ===== BUTTONS ===== */
QPushButton {{
    background: rgba(0, 240, 255, 0.08);
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 8px 20px;
    color: {COLOR_CYAN};
    font-weight: bold;
    font-size: 12px;
    letter-spacing: 1px;
}}

QPushButton:hover {{
    background: rgba(0, 240, 255, 0.18);
    border: 1px solid {COLOR_CYAN};
    color: {COLOR_TEXT_BRIGHT};
}}

QPushButton:pressed {{
    background: rgba(0, 240, 255, 0.30);
}}

QPushButton#btnActivate {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLOR_BLUE}, stop:1 {COLOR_CYAN});
    color: #000;
    font-size: 15px;
    padding: 14px 40px;
    border-radius: 6px;
    border: none;
    letter-spacing: 3px;
}}

QPushButton#btnActivate:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00aaff, stop:1 #44ffff);
    color: #000;
}}

QPushButton#btnActivate:pressed {{
    background: {COLOR_CYAN};
}}

QPushButton#btnEnviar {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLOR_BLUE}, stop:1 {COLOR_CYAN});
    color: #000;
    font-size: 12px;
    padding: 8px 18px;
    border-radius: 4px;
    border: none;
    letter-spacing: 2px;
    font-weight: bold;
}}

QPushButton#btnEnviar:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00aaff, stop:1 #44ffff);
}}

QPushButton#btnEnviar:pressed {{
    background: {COLOR_CYAN};
}}

QPushButton#btnEnviar:disabled {{
    background: rgba(0, 240, 255, 0.15);
    color: {COLOR_TEXT_DIM};
}}

/* ===== LABELS ===== */
QLabel#valueLabel {{
    color: {COLOR_CYAN};
    font-weight: bold;
    font-size: 12px;
}}

QLabel#statusLabel {{
    color: {COLOR_CYAN};
    font-size: 22px;
    font-weight: bold;
    letter-spacing: 6px;
}}

QLabel#titleLabel {{
    color: {COLOR_TEXT_BRIGHT};
    font-size: 30px;
    font-weight: bold;
    letter-spacing: 10px;
}}

QLabel#consoleHeader {{
    color: {COLOR_CYAN};
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 3px;
}}

/* ===== LINE EDIT ===== */
QLineEdit {{
    background: rgba(0, 0, 0, 0.50);
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    padding: 8px 12px;
    color: {COLOR_TEXT_BRIGHT};
    font-family: {FONT_FAMILY};
    font-size: 13px;
}}

QLineEdit:focus {{
    border: 1px solid {COLOR_CYAN};
    background: rgba(0, 0, 0, 0.65);
}}

/* ===== TEXT EDIT ===== */
QTextEdit#chatHistory {{
    background: rgba(0, 0, 0, 0.55);
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 10px;
    color: {COLOR_TEXT};
    font-family: {FONT_FAMILY};
    font-size: 12px;
    selection-background-color: rgba(0, 240, 255, 0.18);
}}

QTextEdit#chatHistory:focus {{
    border: 1px solid {COLOR_CYAN};
}}

/* ===== SCROLLBAR ===== */
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
    background: rgba(0, 240, 255, 0.50);
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* ===== CHECKBOX ===== */
QCheckBox {{
    color: {COLOR_TEXT_DIM};
    spacing: 6px;
    font-size: 11px;
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {COLOR_BORDER};
    border-radius: 3px;
    background: rgba(0, 0, 0, 0.4);
}}

QCheckBox::indicator:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLOR_BLUE}, stop:1 {COLOR_CYAN});
    border: 1px solid {COLOR_CYAN};
}}

QCheckBox::indicator:hover {{
    border: 1px solid {COLOR_CYAN};
}}

/* ===== PROGRESS BAR ===== */
QProgressBar {{
    background: rgba(0, 0, 0, 0.4);
    border: 1px solid {COLOR_BORDER};
    border-radius: 3px;
    height: 14px;
    text-align: center;
    color: {COLOR_CYAN};
    font-size: 10px;
}}

QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {COLOR_BLUE}, stop:1 {COLOR_CYAN});
    border-radius: 2px;
}}

/* ===== SEPARATOR ===== */
QFrame#separator {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 transparent, stop:0.5 {COLOR_CYAN}, stop:1 transparent);
    max-height: 1px;
}}
"""

# ═══════════════════════════════════════════════════════════════════════════
# SALLES CORE 3D — Esfera de partículas reativas nos eixos X, Y, Z
# ═══════════════════════════════════════════════════════════════════════════

# Número de partículas na esfera
NUM_PARTICLES = 180
# Raio base da esfera (proporcional ao tamanho do widget)
BASE_RADIUS_RATIO = 0.38


class Particle3D:
    """Partícula 3D com posição e velocidade angular."""
    __slots__ = ("x", "y", "z", "base_x", "base_y", "base_z", "size", "brightness")

    def __init__(self, x: float, y: float, z: float):
        self.x = x
        self.y = y
        self.z = z
        self.base_x = x
        self.base_y = y
        self.base_z = z
        self.size = random.uniform(1.0, 4.0)
        self.brightness = random.uniform(0.3, 1.0)


class SallesCore3DWidget(QWidget):
    """
    Esfera 3D de partículas reativas — Salles Core 3D.

    Partículas são projetadas nos eixos X, Y e Z, girando continuamente
    a 60 FPS. O raio pulsa e as cores transicionam (Ciano → Verde Neon /
    Azul Elétrico) em sincronia com o estado de fala/processamento.

    Reatividade:
      - Standby: ciano, rotação lenta, sem pulso
      - Active: verde neon, rotação rápida
      - Speaking: azul elétrico, pulso intenso, partículas expandem
      - Processing: ciano pulsante, rotação acelerada
    """

    statusChanged = Signal(str)  # "standby", "active", "speaking", "processing"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "standby"       # standby, active, speaking, processing
        self._target_state = "standby"
        self._phase_x = 0.0
        self._phase_y = 0.0
        self._phase_z = 0.0
        self._pulse = 0.0
        self._target_pulse = 0.0
        self._particles: list[Particle3D] = []
        self._min_size = 200
        self.setMinimumSize(self._min_size, self._min_size)

        # Gera partículas na superfície da esfera
        self._generate_particles()

        # Timer de animação a ~60 FPS
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60 fps

        # Timer de polling do voice_engine (a cada 100ms)
        self._voice_timer = QTimer(self)
        self._voice_timer.timeout.connect(self._poll_voice_state)
        self._voice_timer.start(100)

    def _generate_particles(self) -> None:
        """Distribui partículas uniformemente na superfície de uma esfera."""
        self._particles = []
        for i in range(NUM_PARTICLES):
            # Distribuição Fibonacci sphere (uniforme)
            y = 1.0 - (2.0 * i / (NUM_PARTICLES - 1))
            radius_at_y = math.sqrt(1.0 - y * y)
            theta = 2.399963 * i  # golden angle * i
            x = math.cos(theta) * radius_at_y
            z = math.sin(theta) * radius_at_y
            self._particles.append(Particle3D(x, y, z))

    def _tick(self) -> None:
        """Atualiza rotação, pulso e transições de cor."""
        # Velocidades conforme estado
        speeds = {
            "standby": (0.008, 0.005, 0.003),
            "active": (0.025, 0.018, 0.012),
            "speaking": (0.035, 0.028, 0.020),
            "processing": (0.030, 0.022, 0.015),
        }
        sx, sy, sz = speeds.get(self._state, speeds["standby"])

        # Acelera durante transição de estado
        if self._state != self._target_state:
            sx *= 1.8
            sy *= 1.8
            sz *= 1.8

        self._phase_x = (self._phase_x + sx) % (2 * math.pi)
        self._phase_y = (self._phase_y + sy) % (2 * math.pi)
        self._phase_z = (self._phase_z + sz) % (2 * math.pi)

        # Suaviza transição de pulso
        pulse_diff = self._target_pulse - self._pulse
        self._pulse += pulse_diff * 0.15
        if abs(pulse_diff) < 0.001:
            self._pulse = self._target_pulse

        # Suaviza transição de estado
        if self._state != self._target_state:
            # Transição instantânea do estado para resposta rápida
            self._state = self._target_state

        self.update()

    def _poll_voice_state(self) -> None:
        """Verifica estado do voice_engine para reatividade."""
        if voice_engine is None:
            return

        try:
            is_speaking = voice_engine.ouvindo()
            if self._state == "active" and is_speaking:
                self.set_state("speaking")
            elif self._state == "speaking" and not is_speaking:
                self.set_state("active")
        except Exception:
            pass  # Silencia erros de polling

    def set_state(self, state: str) -> None:
        """Define o estado da esfera com transição suave."""
        if state not in ("standby", "active", "speaking", "processing"):
            return
        if self._target_state != state:
            self._target_state = state
            # Define pulso alvo conforme estado
            pulses = {"standby": 0.0, "active": 0.35, "speaking": 0.85, "processing": 0.55}
            self._target_pulse = pulses.get(state, 0.0)
            self.statusChanged.emit(state)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        radius = min(w, h) * BASE_RADIUS_RATIO

        # Raio pulsante
        pulsed_radius = radius * (1.0 + self._pulse * 0.25)

        # Cores conforme estado
        colors = {
            "standby": (QColor(COLOR_CYAN), QColor(COLOR_CYAN)),
            "active": (QColor(COLOR_GREEN), QColor(COLOR_NEON_GREEN)),
            "speaking": (QColor(COLOR_ELECTRIC_BLUE), QColor(COLOR_BLUE)),
            "processing": (QColor(COLOR_CYAN), QColor(COLOR_GREEN)),
        }
        primary_color, secondary_color = colors.get(self._state, colors["standby"])

        # ── Outer glow ──
        glow_alpha = int(12 + 18 * self._pulse)
        for i in range(6, 0, -1):
            alpha = glow_alpha + i * 5
            glow_r = pulsed_radius + i * 10
            glow = QRadialGradient(cx, cy, glow_r)
            glow.setColorAt(0, QColor(primary_color.red(), primary_color.green(),
                                       primary_color.blue(), alpha))
            glow.setColorAt(1, QColor(primary_color.red(), primary_color.green(),
                                       primary_color.blue(), 0))
            painter.setBrush(QBrush(glow))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2))

        # ── Draw particles (3D → 2D projection) ──
        # Pre-calc rotation matrices
        cos_x, sin_x = math.cos(self._phase_x), math.sin(self._phase_x)
        cos_y, sin_y = math.cos(self._phase_y), math.sin(self._phase_y)
        cos_z, sin_z = math.cos(self._phase_z), math.sin(self._phase_z)

        # Perspective factor
        perspective = 3.5

        # Sort particles by projected Z for depth
        projected: list[tuple[float, float, float, Particle3D]] = []

        for p in self._particles:
            # Rotate around X axis
            y1 = p.base_y * cos_x - p.base_z * sin_x
            z1 = p.base_y * sin_x + p.base_z * cos_x

            # Rotate around Y axis
            x2 = p.base_x * cos_y + z1 * sin_y
            z2 = -p.base_x * sin_y + z1 * cos_y

            # Rotate around Z axis
            x3 = x2 * cos_z - y1 * sin_z
            y3 = x2 * sin_z + y1 * cos_z

            z_final = z2

            # Perspective projection
            factor = perspective / (perspective + z_final)
            px = cx + x3 * pulsed_radius * factor
            py = cy + y3 * pulsed_radius * factor

            # Depth sorting: particles farther = smaller, dimmer
            projected.append((px, py, z_final, p))

        # Sort by depth (back to front)
        projected.sort(key=lambda t: t[2], reverse=True)

        # Draw particles
        for px, py, z_depth, particle in projected:
            # Depth attenuation
            depth_factor = (z_depth + 1.0) / 2.0  # 0 (back) to 1 (front)
            depth_factor = max(0.15, min(1.0, depth_factor))

            # Size: bigger when closer + pulse effect
            size = particle.size * (0.6 + 0.4 * depth_factor) * (1.0 + self._pulse * 0.8)

            # Color: secondary (back) to primary (front)
            r = int(secondary_color.red() + (primary_color.red() - secondary_color.red()) * depth_factor)
            g = int(secondary_color.green() + (primary_color.green() - secondary_color.green()) * depth_factor)
            b = int(secondary_color.blue() + (primary_color.blue() - secondary_color.blue()) * depth_factor)

            # Alpha: brightness * depth * pulse glow
            alpha = int((40 + 80 * depth_factor * particle.brightness) * (1.0 + self._pulse * 1.2))
            alpha = min(255, alpha)

            painter.setBrush(QBrush(QColor(r, g, b, alpha)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(px - size / 2, py - size / 2, size, size))

        # ── Core glow (centro brilhante da esfera) ──
        core_radius = pulsed_radius * 0.18
        core_grad = QRadialGradient(cx, cy, core_radius * 3)
        core_alpha = int(180 + 60 * self._pulse)
        core_grad.setColorAt(0, QColor(255, 255, 255, 200))
        core_grad.setColorAt(0.3, QColor(primary_color.red(), primary_color.green(),
                                          primary_color.blue(), core_alpha))
        core_grad.setColorAt(1, QColor(primary_color.red(), primary_color.green(),
                                        primary_color.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QRectF(cx - core_radius * 3, cy - core_radius * 3,
                                    core_radius * 6, core_radius * 6))

        # ── Axis rings (X, Y, Z) ──
        ring_pen = QPen(QColor(primary_color.red(), primary_color.green(),
                                primary_color.blue(), 35 + int(30 * self._pulse)), 0.8)

        # X-axis ring (horizontal)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.save()
        painter.translate(cx, cy)
        painter.scale(1.0, 0.25)  # flatten for X-axis perspective
        painter.drawEllipse(QRectF(-pulsed_radius, -pulsed_radius,
                                    pulsed_radius * 2, pulsed_radius * 2))
        painter.restore()

        # Y-axis ring (vertical)
        painter.save()
        painter.translate(cx, cy)
        painter.scale(0.25, 1.0)  # flatten for Y-axis perspective
        painter.drawEllipse(QRectF(-pulsed_radius, -pulsed_radius,
                                    pulsed_radius * 2, pulsed_radius * 2))
        painter.restore()

        # Z-axis ring (circular, facing viewer)
        painter.drawEllipse(QRectF(cx - pulsed_radius, cy - pulsed_radius,
                                    pulsed_radius * 2, pulsed_radius * 2))

        # ── Core text ──
        state_texts = {
            "standby": "SALLES\nCORE 3D",
            "active": "SYSTEM\nACTIVE",
            "speaking": "VOICE\nLINK",
            "processing": "PROCESS\nING...",
        }
        text = state_texts.get(self._state, "SYSTEM\nREADY")

        font = QFont(FONT_FAMILY.split(",")[0].strip(), 9)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        painter.setFont(font)
        painter.setPen(QColor(COLOR_TEXT_BRIGHT))
        text_rect = QRectF(cx - core_radius * 2, cy - core_radius * 0.8,
                           core_radius * 4, core_radius * 2.5)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text)

        # ── FPS counter (debug, canto inferior) ──
        fps_font = QFont(FONT_FAMILY.split(",")[0].strip(), 7)
        painter.setFont(fps_font)
        painter.setPen(QColor(COLOR_TEXT_DIM))
        painter.drawText(QRectF(4, h - 16, 80, 14),
                         Qt.AlignmentFlag.AlignLeft,
                         f"{self._state.upper()}")

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
      3. kill_switch — monitoramento de emergência
      4. brain — verificação da conexão com Ollama
      5. voice_engine — microfone e síntese de voz
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
            ("kill_switch", self._init_killswitch),
            ("brain", self._init_brain),
            ("voice_engine", self._init_voice),
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

    def _init_voice(self) -> bool:
        if voice_engine is None:
            return False
        try:
            # Testa microfone e TTS listando vozes
            vozes = voice_engine.listar_vozes()
            return len(vozes) > 0
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
    Thread que executa brain.pensar() em segundo plano para não
    congelar a animação 3D do Salles Core.
    """

    started = Signal()
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

            resultado = brain.pensar(self._prompt, historico_limpo)
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
    - Síntese de voz opcional via voice_engine (checkbox)
    """

    statusMessage = Signal(str)
    coreStateRequest = Signal(str)  # solicita mudança de estado do Core 3D

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: ChatWorker | None = None
        self._historico_contexto: list[dict] = []
        self._ultimo_prompt: str = ""
        self._voz_ativada = True
        self._processando = False
        self._build_ui()

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
        self._input.setPlaceholderText("Digite seu comando para o J.A.R.V.I.S...")
        self._input.returnPressed.connect(self._on_enviar)
        self._input.setMinimumHeight(36)
        input_row.addWidget(self._input, stretch=1)

        self._btn_enviar = QPushButton("ENVIAR")
        self._btn_enviar.setObjectName("btnEnviar")
        self._btn_enviar.setFixedWidth(90)
        self._btn_enviar.clicked.connect(self._on_enviar)
        input_row.addWidget(self._btn_enviar)

        layout.addLayout(input_row)

        # ── Toggle de voz ──
        self._check_voz = QCheckBox("Ativar resposta por voz (TTS)")
        self._check_voz.setChecked(self._voz_ativada)
        self._check_voz.toggled.connect(self._on_toggle_voz)
        layout.addWidget(self._check_voz)

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

        self._ultimo_prompt = prompt
        self._append_user(prompt)
        self._input.clear()
        self._set_processando(True)

        # Notifica Core 3D que estamos processando
        self.coreStateRequest.emit("processing")

        self._worker = ChatWorker(prompt, list(self._historico_contexto))
        self._worker.started.connect(self._on_worker_started)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.error.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_toggle_voz(self, checked: bool) -> None:
        self._voz_ativada = checked

    def _on_worker_started(self) -> None:
        self._append_system("[PROCESSANDO...]")

    def _on_worker_finished(self, resultado: dict) -> None:
        self._set_processando(False)

        resposta_voz = resultado.get("resposta_voz", "")
        acao = resultado.get("acao", "falar")
        params = resultado.get("parametros", {})

        # Exibe resposta
        self._append_jarvis(resposta_voz)

        # Executa ação
        acao_resultado = self._executar_acao(acao, params, resposta_voz)
        if acao_resultado:
            self._append_system(acao_resultado)

        # Voz
        if self._voz_ativada and resposta_voz and voice_engine:
            try:
                self.coreStateRequest.emit("speaking")
                voice_engine.falar(resposta_voz)
            except Exception as exc:
                self._append_error(f"Erro no TTS: {exc}")

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

    def _on_worker_error(self, mensagem: str) -> None:
        self._set_processando(False)
        self._append_error(mensagem)
        self.coreStateRequest.emit("active")

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
            elif acao == "analisar_codigo":
                return self._tratar_analisar_codigo(params)
            elif acao == "diagnostico_windows":
                return self._tratar_diagnostico_windows(params)
            elif acao == "processar_video":
                return self._tratar_processar_video(params)
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


# ═══════════════════════════════════════════════════════════════════════════
# JANELA PRINCIPAL — SALLES INDUSTRIES Quantum OS Launcher v2.0
# ═══════════════════════════════════════════════════════════════════════════

class LauncherWindow(QMainWindow):
    """Janela principal do Launcher HUD v2.0."""

    def __init__(self):
        super().__init__()
        self._processo_jarvis: subprocess.Popen | None = None
        self._init_worker: InitWorker | None = None
        self._subsystem_status: dict[str, bool] = {}
        self._build_ui()
        self._apply_style()
        # Inicia a inicialização em segundo plano
        self._iniciar_subsistemas()

    def _build_ui(self) -> None:
        self.setWindowTitle("SALLES INDUSTRIES — Quantum OS Launcher v2.0")
        self.setMinimumSize(1000, 650)
        self.resize(1150, 720)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(20)

        # ── LEFT: Salles Core 3D + Status ──
        left_panel = QVBoxLayout()
        left_panel.setSpacing(12)

        # Title
        title = QLabel("SALLES INDUSTRIES")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_panel.addWidget(title)

        # Subtitle
        sub = QLabel("QUANTUM OPERATING SYSTEM")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color: {COLOR_CYAN}; font-size: 11px; letter-spacing: 4px;")
        left_panel.addWidget(sub)

        # Separator
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFixedHeight(2)
        left_panel.addWidget(sep)

        # Salles Core 3D
        self._reactor = SallesCore3DWidget()
        self._reactor.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_panel.addWidget(self._reactor, stretch=1)

        # Status text
        self._status_label = QLabel("CORE STANDBY")
        self._status_label.setObjectName("statusLabel")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_panel.addWidget(self._status_label)

        self._detail_label = QLabel("Inicializando subsistemas...")
        self._detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail_label.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 11px;")
        left_panel.addWidget(self._detail_label)

        # Progress bar de inicialização
        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self._progress_bar.setFixedHeight(12)
        left_panel.addWidget(self._progress_bar)

        left_panel.addSpacing(8)

        # ── Activate button ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._btn_activate = QPushButton("INICIAR  J.A.R.V.I.S.")
        self._btn_activate.setObjectName("btnActivate")
        self._btn_activate.setFixedWidth(320)
        self._btn_activate.clicked.connect(self._on_activate)
        self._btn_activate.setEnabled(False)  # Só ativa após init
        btn_layout.addWidget(self._btn_activate)
        btn_layout.addStretch()
        left_panel.addLayout(btn_layout)

        root.addLayout(left_panel, stretch=3)

        # ── RIGHT: QTabWidget ──
        self._tab_widget = QTabWidget()
        self._tab_widget.setMinimumWidth(400)
        self._tab_widget.setDocumentMode(True)

        # Aba 1: Configurações
        self._settings = SettingsPanel()
        self._settings.configChanged.connect(self._on_config_changed)

        settings_container = QWidget()
        settings_layout = QVBoxLayout(settings_container)
        settings_layout.setContentsMargins(14, 14, 14, 14)
        settings_layout.setSpacing(8)

        settings_header = QLabel("CONFIGURACOES")
        settings_header.setStyleSheet(
            f"color: {COLOR_CYAN}; font-size: 14px; font-weight: bold; "
            f"letter-spacing: 3px; padding-bottom: 4px;")
        settings_layout.addWidget(settings_header)

        settings_layout.addWidget(self._settings, stretch=1)

        self._btn_save = QPushButton("SALVAR CONFIGURACOES")
        self._btn_save.clicked.connect(self._on_save)
        settings_layout.addWidget(self._btn_save)

        self._tab_widget.addTab(settings_container, "CONFIGURACOES")

        # Aba 2: Console de Chat
        self._chat_console = ChatConsole()
        self._chat_console.coreStateRequest.connect(self._on_core_state_request)
        self._tab_widget.addTab(self._chat_console, "CONSOLO / CHAT")

        root.addWidget(self._tab_widget, stretch=2)

    def _apply_style(self) -> None:
        self.setStyleSheet(STYLESHEET)

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
            self._reactor.set_state("standby")
        else:
            falhas = [k for k, v in results.items() if not v]
            self._detail_label.setText(
                f"Atenção: {', '.join(falhas)} não inicializaram."
            )
            self._status_label.setText("CORE DEGRADED")
            self._progress_bar.setValue(100)
        self._btn_activate.setEnabled(True)
        self._progress_bar.setVisible(False)

    # ── Slots ──

    @Slot()
    def _on_config_changed(self) -> None:
        self._btn_save.setText("SALVAR CONFIGURACOES *")
        self._btn_save.setStyleSheet(
            f"QPushButton {{ border: 1px solid {COLOR_ORANGE}; "
            f"color: {COLOR_ORANGE}; }}")

    @Slot()
    def _on_save(self) -> None:
        if self._settings.salvar():
            self._btn_save.setText("SALVAR CONFIGURACOES")
            self._btn_save.setStyleSheet("")
            QMessageBox.information(
                self, "SALLES INDUSTRIES",
                "Configurações salvas com sucesso.")
        else:
            QMessageBox.warning(
                self, "SALLES INDUSTRIES",
                "Falha ao salvar configurações. Verifique as permissões.")

    @Slot(str)
    def _on_core_state_request(self, state: str) -> None:
        """Recebe solicitação de mudança de estado do Core 3D."""
        self._reactor.set_state(state)

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
        self._btn_save.setText("SALVAR CONFIGURACOES")
        self._btn_save.setStyleSheet("")

        # Ativa UI
        self._reactor.set_state("active")
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
        self._reactor.set_state("standby")
        self._status_label.setText("CORE STANDBY")
        self._status_label.setStyleSheet(
            f"color: {COLOR_CYAN}; font-size: 22px; font-weight: bold; "
            f"letter-spacing: 6px;")
        self._detail_label.setText("Aguardando inicializacao do sistema...")
        self._btn_activate.setText("INICIAR  J.A.R.V.I.S.")
        self._btn_activate.setStyleSheet("")

    def closeEvent(self, event) -> None:
        if self._init_worker and self._init_worker.isRunning():
            self._init_worker.cancel()
            self._init_worker.wait(2000)
        self._desligar_nucleo()
        event.accept()


# ═══════════════════════════════════════════════════════════════════════════
# PONTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SALLES INDUSTRIES — Quantum OS v2.0")

    window = LauncherWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
