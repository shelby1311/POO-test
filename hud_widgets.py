"""
hud_widgets.py — Widgets HUD Sci-Fi para SALLES INDUSTRIES Quantum OS v3.0

Fornece:
  - SallesCore3DOpenGLWidget: esfera 3D de partículas via OpenGL/GLSL
    com bloom, glow, motion blur e sombreamento por GPU dedicada.
  - RadialGaugeWidget: medidor circular HUD estilo Sci-Fi com barra
    de progresso radial animada em vetor (QPainter).
  - HardwareMonitor: leitura de sensores (CPU, GPU, RAM, temperatura)
    via psutil + GPUtil com polling em thread separada.

Requer: PySide6, psutil, GPUtil (opcional)
"""

import math
import random
import time
from typing import Optional

from PySide6.QtCore import (
    Qt, QTimer, Signal, Slot, QThread, QMutex, QMutexLocker,
)
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QRadialGradient,
    QConicalGradient, QPainterPath, QFontDatabase, QSurfaceFormat,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QSizePolicy,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtOpenGL import (
    QOpenGLShader, QOpenGLShaderProgram, QOpenGLBuffer,
    QOpenGLVertexArrayObject,
)

# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTES DE ESTILO
# ═══════════════════════════════════════════════════════════════════════════

COLOR_CYAN = "#00f0ff"
COLOR_BLUE = "#0088ff"
COLOR_GREEN = "#00ff88"
COLOR_NEON_GREEN = "#00ff44"
COLOR_ELECTRIC_BLUE = "#0055ff"
COLOR_ORANGE = "#ff8833"
COLOR_RED = "#ff2244"
COLOR_BG = "#080b10"
COLOR_TEXT = "#c8d6e5"
COLOR_TEXT_DIM = "#5a6a7e"
COLOR_BORDER = "rgba(0, 240, 255, 0.25)"

NUM_PARTICLES = 180
FONT_FAMILY = "Consolas, Courier New, monospace"

# ── Shaders GLSL para o SallesCore3D ──

VERTEX_SHADER = """
#version 330 core

layout(location = 0) in vec3 aPos;
layout(location = 1) in float aSize;
layout(location = 2) in float aAlpha;

uniform mat4 uModelViewProjection;
uniform float uPointScale;

out float vAlpha;
out float vSize;

void main() {
    gl_Position = uModelViewProjection * vec4(aPos, 1.0);
    gl_PointSize = aSize * uPointScale / gl_Position.w;
    vAlpha = aAlpha;
    vSize = aSize;
}
"""

FRAGMENT_SHADER = """
#version 330 core

in float vAlpha;
in float vSize;

uniform vec3 uColor;
uniform float uGlowIntensity;
uniform float uTime;

out vec4 fragColor;

void main() {
    // Distância do centro do ponto (0.5 = borda)
    float dist = length(gl_PointCoord - vec2(0.5)) * 2.0;

    // Core brilhante + glow suave
    float core = exp(-dist * 2.5);
    float glow = exp(-dist * 1.2) * 0.6;
    float outer = exp(-dist * 0.6) * 0.15;

    float alpha = (core + glow + outer) * vAlpha;
    alpha = clamp(alpha, 0.0, 1.0);

    // Cor com saturação no centro
    vec3 color = uColor * (1.0 + core * 0.5);

    fragColor = vec4(color, alpha);
}
"""

# ═══════════════════════════════════════════════════════════════════════════
# SALLES CORE 3D — OpenGL Widget
# ═══════════════════════════════════════════════════════════════════════════

class SallesCore3DOpenGLWidget(QOpenGLWidget):
    """
    Esfera 3D de partículas Sci-Fi renderizada via OpenGL + GLSL Shaders.

    Pipeline de GPU dedicada:
      - 180 partículas na superfície de uma esfera (Fibonacci sphere)
      - Rotação nos 3 eixos (X, Y, Z) com velocidades por estado
      - Bloom/glow via fragment shader com decaimento exponencial
      - Pulsação reativa ao estado (standby, active, speaking, processing)
      - 60 FPS estáveis com processamento na GPU
    """

    statusChanged = Signal(str)

    def __init__(self, parent=None):
        # Configura o formato de superfície OpenGL
        fmt = QSurfaceFormat()
        fmt.setSamples(4)         # 4x MSAA anti-aliasing
        fmt.setSwapInterval(1)    # VSync
        QSurfaceFormat.setDefaultFormat(fmt)

        super().__init__(parent)
        self._state = "standby"
        self._target_state = "standby"
        self._phase_x = 0.0
        self._phase_y = 0.0
        self._phase_z = 0.0
        self._pulse = 0.0
        self._target_pulse = 0.0
        self._program: Optional[QOpenGLShaderProgram] = None
        self._vao: Optional[QOpenGLVertexArrayObject] = None
        self._vbo: Optional[QOpenGLBuffer] = None
        self._initialized = False
        self._particle_data: list[tuple[float, float, float]] = []
        self._sizes: list[float] = []
        self._alphas: list[float] = []
        self.setMinimumSize(200, 200)

        # Timer de animação a ~60 FPS
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    # ── OpenGL Init ──

    def initializeGL(self) -> None:
        from PySide6.QtOpenGL import QOpenGLVersionProfile
        # Shader program
        self._program = QOpenGLShaderProgram(self)
        self._program.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Vertex, VERTEX_SHADER)
        self._program.addShaderFromSourceCode(
            QOpenGLShader.ShaderTypeBit.Fragment, FRAGMENT_SHADER)
        self._program.link()
        self._program.bind()

        # Gera partículas na esfera
        self._generate_particles()

        # Vertex data: x, y, z, size, alpha (interleaved)
        num = len(self._particle_data)
        vertices = []
        for i in range(num):
            x, y, z = self._particle_data[i]
            vertices.extend([x, y, z, self._sizes[i], self._alphas[i]])

        import numpy as np
        data = np.array(vertices, dtype=np.float32)

        self._vao = QOpenGLVertexArrayObject()
        self._vao.create()
        self._vao.bind()

        self._vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._vbo.create()
        self._vbo.bind()
        self._vbo.allocate(data.tobytes(), data.nbytes)

        # Layout: pos (3 floats) + size (1 float) + alpha (1 float) = 5 floats
        stride = 5 * 4  # 5 floats * 4 bytes
        # aPos @ location 0
        self._program.setAttributeBuffer(0, 0x1406, 0, 3, stride)  # GL_FLOAT
        self._program.enableAttributeArray(0)
        # aSize @ location 1
        self._program.setAttributeBuffer(1, 0x1406, 3 * 4, 1, stride)
        self._program.enableAttributeArray(1)
        # aAlpha @ location 2
        self._program.setAttributeBuffer(2, 0x1406, 4 * 4, 1, stride)
        self._program.enableAttributeArray(2)

        self._vao.release()
        self._program.release()

        self._initialized = True

    def _generate_particles(self) -> None:
        """Distribui partículas uniformemente na superfície da esfera (Fibonacci)."""
        self._particle_data = []
        self._sizes = []
        self._alphas = []
        for i in range(NUM_PARTICLES):
            y = 1.0 - (2.0 * i / (NUM_PARTICLES - 1))
            radius_at_y = math.sqrt(1.0 - y * y)
            theta = 2.399963 * i  # golden angle
            x = math.cos(theta) * radius_at_y
            z = math.sin(theta) * radius_at_y
            self._particle_data.append((x, y, z))
            self._sizes.append(random.uniform(1.5, 6.0))
            self._alphas.append(random.uniform(0.25, 1.0))

    # ── Paint ──

    def paintGL(self) -> None:
        if not self._initialized or self._program is None:
            return

        from PySide6.QtGui import QMatrix4x4, QVector3D
        import numpy as np

        # Cor conforme estado
        colors = {
            "standby": QVector3D(0.0, 0.94, 1.0),        # ciano
            "active": QVector3D(0.0, 1.0, 0.53),          # verde neon
            "speaking": QVector3D(0.0, 0.33, 1.0),        # azul elétrico
            "processing": QVector3D(0.0, 0.94, 1.0),     # ciano
        }
        color = colors.get(self._state, colors["standby"])

        self._program.bind()
        self._vao.bind()

        w = self.width()
        h = self.height()
        aspect = w / max(h, 1)

        # Matriz de projeção
        projection = QMatrix4x4()
        projection.perspective(45.0, aspect, 0.1, 100.0)

        # Matriz de view (câmera)
        view = QMatrix4x4()
        view.translate(0.0, 0.0, -5.5)  # afasta câmera

        # Rotação acumulada
        model = QMatrix4x4()
        model.rotate(self._phase_x * 180.0 / math.pi, 1.0, 0.0, 0.0)
        model.rotate(self._phase_y * 180.0 / math.pi, 0.0, 1.0, 0.0)
        model.rotate(self._phase_z * 180.0 / math.pi, 0.0, 0.0, 1.0)

        # Pulsação: escala uniforme
        pulse_scale = 1.0 + self._pulse * 0.25
        model.scale(pulse_scale)

        mvp = projection * view * model

        self._program.setUniformValue("uModelViewProjection", mvp)
        self._program.setUniformValue("uColor", color)
        self._program.setUniformValue(
            "uGlowIntensity", 0.5 + self._pulse * 0.5)
        self._program.setUniformValue("uTime", float(time.time() % 1000))
        self._program.setUniformValue(
            "uPointScale", float(min(w, h)) * 0.015)

        # Clear com cor de fundo
        from PySide6.QtGui import QOpenGLFunctions
        gl = self.context().functions()
        gl.glClearColor(0.031, 0.043, 0.063, 1.0)
        gl.glClear(0x00004000 | 0x00000100)  # GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT
        gl.glEnable(0x0BE1)  # GL_DEPTH_TEST
        gl.glEnable(0x8642)  # GL_PROGRAM_POINT_SIZE
        gl.glEnable(0x0B71)  # GL_DEPTH_TEST
        gl.glEnable(0x0BC0)  # GL_ALPHA_TEST  (approx via blend)
        gl.glEnable(0x0BE2)  # GL_BLEND
        gl.glBlendFunc(0x0302, 0x0303)  # GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA (approx)

        gl.glDrawArrays(0x0000, 0, NUM_PARTICLES)  # GL_POINTS

        self._vao.release()
        self._program.release()

    # ── Tick / State ──

    def _tick(self) -> None:
        speeds = {
            "standby": (0.008, 0.005, 0.003),
            "active": (0.025, 0.018, 0.012),
            "speaking": (0.035, 0.028, 0.020),
            "processing": (0.030, 0.022, 0.015),
        }
        sx, sy, sz = speeds.get(self._state, speeds["standby"])

        if self._state != self._target_state:
            sx *= 1.8; sy *= 1.8; sz *= 1.8

        self._phase_x = (self._phase_x + sx) % (2 * math.pi)
        self._phase_y = (self._phase_y + sy) % (2 * math.pi)
        self._phase_z = (self._phase_z + sz) % (2 * math.pi)

        pulse_diff = self._target_pulse - self._pulse
        self._pulse += pulse_diff * 0.15
        if abs(pulse_diff) < 0.001:
            self._pulse = self._target_pulse

        if self._state != self._target_state:
            self._state = self._target_state

        self.update()

    def set_state(self, state: str) -> None:
        if state not in ("standby", "active", "speaking", "processing"):
            return
        if self._target_state != state:
            self._target_state = state
            pulses = {"standby": 0.0, "active": 0.35, "speaking": 0.85, "processing": 0.55}
            self._target_pulse = pulses.get(state, 0.0)
            self.statusChanged.emit(state)


# ═══════════════════════════════════════════════════════════════════════════
# RADIAL GAUGE — Medidor Circular HUD Sci-Fi
# ═══════════════════════════════════════════════════════════════════════════

class RadialGaugeWidget(QWidget):
    """
    Medidor circular HUD Sci-Fi com barra de progresso radial animada.

    Desenha um arco circular preenchido até 'value'/'max_value'
    usando QPainter com gradiente cônico. Inclui:
      - Arco de fundo (track) com baixa opacidade
      - Arco de valor com gradiente de cor (verde→amarelo→vermelho)
      - Texto central com valor e unidade
      - Rótulo abaixo do gauge
      - Animação suave de transição (interpolation)
    """

    def __init__(
        self,
        title: str = "",
        unit: str = "%",
        max_value: float = 100.0,
        warn_threshold: float = 70.0,
        danger_threshold: float = 90.0,
        parent=None,
    ):
        super().__init__(parent)
        self._title = title
        self._unit = unit
        self._value: float = 0.0
        self._display_value: float = 0.0  # animated/interpolated
        self._max_value = max_value
        self._warn_threshold = warn_threshold
        self._danger_threshold = danger_threshold
        self.setMinimumSize(100, 110)

        # Timer de animação (interpolação suave)
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._animate)
        self._anim_timer.start(30)  # ~33 FPS para animação

    def set_value(self, value: float) -> None:
        self._value = max(0.0, min(value, self._max_value))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        size = min(w, h) - 16
        cx = w / 2.0
        cy = (h / 2.0) - 6  # ligeiro offset para dar espaço ao label

        # Track (arco de fundo)
        track_rect = self._center_rect(cx, cy, size)
        track_pen = QPen(QColor(0, 240, 255, 30), 8)
        track_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(track_rect, 135 * 16, 270 * 16)  # 270° arco

        # Value arc (arco preenchido)
        ratio = self._display_value / max(self._max_value, 0.001)
        span = int(270 * ratio * 16)  # em 1/16 graus

        # Cor baseada no threshold
        if ratio >= self._danger_threshold / 100.0:
            arc_color = QColor(COLOR_RED)
        elif ratio >= self._warn_threshold / 100.0:
            arc_color = QColor(COLOR_ORANGE)
        else:
            arc_color = QColor(COLOR_CYAN)

        arc_pen = QPen(arc_color, 8)
        arc_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(arc_pen)
        painter.drawArc(track_rect, 135 * 16, span)

        # Glow effect
        glow_pen = QPen(QColor(arc_color.red(), arc_color.green(),
                                arc_color.blue(), 60), 16)
        glow_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(glow_pen)
        painter.drawArc(track_rect, 135 * 16, span)

        # Valor central
        font_val = QFont(FONT_FAMILY.split(",")[0].strip(), 16)
        font_val.setBold(True)
        painter.setFont(font_val)
        painter.setPen(QColor(COLOR_CYAN))
        val_text = f"{self._display_value:.0f}"
        text_rect = self._center_rect(cx, cy - 6, size * 0.6)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, val_text)

        # Unidade (menor, abaixo do valor)
        font_unit = QFont(FONT_FAMILY.split(",")[0].strip(), 8)
        painter.setFont(font_unit)
        painter.setPen(QColor(COLOR_TEXT_DIM))
        unit_rect = self._center_rect(cx, cy + 10, size * 0.6)
        painter.drawText(unit_rect, Qt.AlignmentFlag.AlignCenter, self._unit)

        # Título (abaixo do gauge)
        if self._title:
            font_title = QFont(FONT_FAMILY.split(",")[0].strip(), 9)
            painter.setFont(font_title)
            painter.setPen(QColor(COLOR_TEXT_DIM))
            title_rect = self._center_rect(cx, cy + size / 2 + 4, w, 18)
            title_rect.moveTop(int(cy + size / 2 + 6))
            painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter,
                             self._title.upper())

        painter.end()

    def _animate(self) -> None:
        """Interpola display_value em direção a value."""
        diff = self._value - self._display_value
        if abs(diff) < 0.1:
            self._display_value = self._value
        else:
            self._display_value += diff * 0.15
        self.update()

    @staticmethod
    def _center_rect(cx: float, cy: float, w: float, h: float = None) -> "QRectF":
        from PySide6.QtCore import QRectF
        if h is None:
            h = w
        return QRectF(cx - w / 2, cy - h / 2, w, h)


# ═══════════════════════════════════════════════════════════════════════════
# HARDWARE MONITOR — Leitura de sensores em thread separada
# ═══════════════════════════════════════════════════════════════════════════

class HardwareMonitor(QThread):
    """
    Thread que lê sensores de hardware (CPU, RAM, GPU, temperatura)
    via psutil + GPUtil e emite sinais com os valores atuais.

    Sinais:
      - cpuPercent(float): % de uso da CPU
      - ramPercent(float): % de uso da RAM
      - gpuPercent(float): % de uso da GPU (None se indisponível)
      - gpuTemp(float): temperatura da GPU em °C
      - cpuTemp(float): temperatura da CPU em °C (estimada)
    """

    cpuPercent = Signal(float)
    ramPercent = Signal(float)
    gpuPercent = Signal(float)
    gpuTemp = Signal(float)
    cpuTemp = Signal(float)

    def __init__(self, interval_ms: int = 1000, parent=None):
        super().__init__(parent)
        self._interval = interval_ms / 1000.0
        self._running = False

    def run(self) -> None:
        self._running = True
        try:
            import psutil
        except ImportError:
            psutil = None

        try:
            import GPUtil
        except ImportError:
            GPUtil = None

        while self._running:
            try:
                # CPU
                if psutil:
                    cpu = psutil.cpu_percent(interval=0.1)
                    self.cpuPercent.emit(cpu)

                    # RAM
                    ram = psutil.virtual_memory().percent
                    self.ramPercent.emit(ram)

                    # CPU Temp (via psutil sensors)
                    temps = psutil.sensors_temperatures()
                    cpu_temp = 0.0
                    for name, entries in temps.items():
                        for entry in entries:
                            if "core" in entry.label.lower() or "cpu" in name.lower():
                                cpu_temp = max(cpu_temp, entry.current)
                    if cpu_temp > 0:
                        self.cpuTemp.emit(cpu_temp)

                # GPU
                if GPUtil:
                    gpus = GPUtil.getGPUs()
                    if gpus:
                        gpu = gpus[0]
                        self.gpuPercent.emit(gpu.load * 100.0)
                        self.gpuTemp.emit(gpu.temperature)
            except Exception:
                pass

            time.sleep(self._interval)

    def stop(self) -> None:
        self._running = False
        self.wait(2000)


# ═══════════════════════════════════════════════════════════════════════════
# HUD MONITOR PANEL — Container com múltiplos RadialGauges
# ═══════════════════════════════════════════════════════════════════════════

class HudMonitorPanel(QWidget):
    """
    Painel que agrupa 4 RadialGauges (CPU, RAM, GPU, TEMP)
    conectados ao HardwareMonitor para atualização em tempo real.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._monitor: Optional[HardwareMonitor] = None
        self._gauges: dict[str, RadialGaugeWidget] = {}
        self._value_labels: dict[str, QLabel] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Grid 2x2 de gauges
        grid = QGridLayout()
        grid.setSpacing(12)

        gauge_configs = [
            ("cpu", "CPU", "%", 100, 70, 90, 0, 0),
            ("ram", "RAM", "%", 100, 70, 90, 0, 1),
            ("gpu", "GPU", "%", 100, 75, 90, 1, 0),
            ("temp", "GPU TEMP", "°C", 100, 70, 85, 1, 1),
        ]

        for key, title, unit, max_v, warn, danger, row, col in gauge_configs:
            container = QVBoxLayout()
            container.setSpacing(2)

            gauge = RadialGaugeWidget(
                title=title, unit=unit, max_value=max_v,
                warn_threshold=warn, danger_threshold=danger,
            )
            gauge.setMinimumSize(120, 130)
            self._gauges[key] = gauge
            container.addWidget(gauge, alignment=Qt.AlignmentFlag.AlignCenter)

            grid.addLayout(container, row, col)

        layout.addLayout(grid)
        layout.addStretch()

    def start_monitoring(self) -> None:
        if self._monitor is not None:
            return
        self._monitor = HardwareMonitor()
        self._monitor.cpuPercent.connect(
            lambda v: self._gauges["cpu"].set_value(v))
        self._monitor.ramPercent.connect(
            lambda v: self._gauges["ram"].set_value(v))
        self._monitor.gpuPercent.connect(
            lambda v: self._gauges["gpu"].set_value(v))
        self._monitor.gpuTemp.connect(
            lambda v: self._gauges["temp"].set_value(v))
        self._monitor.start()

    def stop_monitoring(self) -> None:
        if self._monitor:
            self._monitor.stop()
            self._monitor = None
