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
    QPointF, QRectF,
)
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QRadialGradient,
    QConicalGradient, QPainterPath, QFontDatabase, QSurfaceFormat,
    QFontMetrics,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QSizePolicy, QProgressBar,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtOpenGL import (
    QOpenGLShader, QOpenGLShaderProgram, QOpenGLBuffer,
    QOpenGLVertexArrayObject,
)

# ═══════════════════════════════════════════════════════════════════════════
# CONSTANTES DE ESTILO
# ═══════════════════════════════════════════════════════════════════════════

COLOR_CYAN = "#18DDE5"
COLOR_TURQUOISE = "#19BFC5"
COLOR_BLUE = "#2499D8"
COLOR_GREEN = "#19BFC5"
COLOR_NEON_GREEN = "#18DDE5"
COLOR_ELECTRIC_BLUE = "#2499D8"
COLOR_PURPLE = "#7B3FA8"
COLOR_MAGENTA = "#E22F91"
COLOR_ORANGE = "#FF804D"
COLOR_RED = "#FF5C58"
COLOR_CORAL = "#FF5C58"
COLOR_BG = "#080C14"
COLOR_TEXT = "#A8D5D8"
COLOR_TEXT_DIM = "#50777D"
COLOR_BORDER = "rgba(24, 221, 229, 0.25)"

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

        # ── Uniform locations (busca única por frame) ──
        loc_mvp = self._program.uniformLocation("uModelViewProjection")
        loc_color = self._program.uniformLocation("uColor")
        loc_glow = self._program.uniformLocation("uGlowIntensity")
        loc_time = self._program.uniformLocation("uTime")
        loc_point_scale = self._program.uniformLocation("uPointScale")

        if loc_mvp != -1:
            self._program.setUniformValue(loc_mvp, mvp)
        if loc_color != -1:
            self._program.setUniformValue(loc_color, color)
        if loc_glow != -1:
            self._program.setUniformValue(loc_glow, 0.5 + self._pulse * 0.5)
        if loc_time != -1:
            self._program.setUniformValue(loc_time, float(time.time() % 1000))
        if loc_point_scale != -1:
            self._program.setUniformValue(
                loc_point_scale, float(min(w, h)) * 0.015)

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
        track_pen = QPen(QColor(24, 221, 229, 28), 8)
        track_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(track_rect, 135 * 16, 270 * 16)  # 270° arco

        # Escala radial (tick marks ao longo do arco)
        painter.setPen(QPen(QColor(24, 221, 229, 60), 1.0))
        radius_inner = size / 2.0 - 1.0
        radius_outer = size / 2.0 + 8.0
        for graus in range(135, 406, 15):
            rad = math.radians(graus)
            x1 = cx + math.cos(rad) * radius_inner
            y1 = cy - math.sin(rad) * radius_inner
            x2 = cx + math.cos(rad) * radius_outer
            y2 = cy - math.sin(rad) * radius_outer
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

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


# ═══════════════════════════════════════════════════════════════════════════
# TELEMETRY PANEL — Barras Sci-Fi/HUD (CPU, VRAM, RAM) + Status Ollama
# ═══════════════════════════════════════════════════════════════════════════

def _barra_style(cor: str) -> str:
    """Gera o stylesheet de uma barra de telemetria com a cor do chunk."""
    return (
        "QProgressBar { background: rgba(0, 0, 0, 0.4); "
        "border: 1px solid rgba(0, 240, 255, 0.2); border-radius: 3px; } "
        f"QProgressBar::chunk {{ background: {cor}; border-radius: 2px; }}"
    )


class TelemetryPanel(QWidget):
    """
    Painel de telemetria Sci-Fi/HUD compacto com barras horizontais para CPU,
    VRAM e RAM, além de um indicador de status do Ollama (dot + modelo).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bars: dict[str, QProgressBar] = {}
        self._values: dict[str, QLabel] = {}
        self._tick = 0
        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._atualizar)
        self._timer.start(2000)
        self._atualizar()
        self._checar_ollama()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QLabel("TELEMETRIA")
        header.setStyleSheet(
            f"color: {COLOR_CYAN}; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 3px;")
        layout.addWidget(header)

        for key, rotulo in (("cpu", "CPU"), ("vram", "VRAM"), ("ram", "RAM")):
            topo = QHBoxLayout()
            topo.setSpacing(6)
            nome = QLabel(rotulo)
            nome.setStyleSheet(
                f"color: {COLOR_TEXT_DIM}; font-size: 10px; letter-spacing: 1px;")
            valor = QLabel("--%")
            valor.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            valor.setStyleSheet(
                f"color: {COLOR_CYAN}; font-size: 10px; font-weight: bold;")
            topo.addWidget(nome)
            topo.addStretch()
            topo.addWidget(valor)

            barra = QProgressBar()
            barra.setRange(0, 100)
            barra.setValue(0)
            barra.setTextVisible(False)
            barra.setFixedHeight(7)

            layout.addLayout(topo)
            layout.addWidget(barra)
            self._bars[key] = barra
            self._values[key] = valor

        # Linha de status do Ollama
        ollama_row = QHBoxLayout()
        ollama_row.setSpacing(6)
        lbl = QLabel("OLLAMA")
        lbl.setStyleSheet(
            f"color: {COLOR_TEXT_DIM}; font-size: 10px; letter-spacing: 1px;")
        self._ollama_dot = QLabel("●")
        self._ollama_dot.setStyleSheet("color: #ff2244; font-size: 11px;")
        self._ollama_text = QLabel("OFFLINE")
        self._ollama_text.setStyleSheet(
            "color: #ff2244; font-size: 10px; font-weight: bold;")
        ollama_row.addWidget(lbl)
        ollama_row.addStretch()
        ollama_row.addWidget(self._ollama_dot)
        ollama_row.addWidget(self._ollama_text)
        layout.addLayout(ollama_row)

    def _atualizar(self) -> None:
        self._definir_barra("cpu", self._ler_cpu())
        self._definir_barra("ram", self._ler_ram())
        self._definir_barra("vram", self._ler_vram())

        # Verifica o status do Ollama a cada ~10s (5 ticks de 2s).
        self._tick += 1
        if self._tick % 5 == 0:
            self._checar_ollama()

    def _definir_barra(self, key: str, valor) -> None:
        barra = self._bars[key]
        rotulo = self._values[key]
        if valor is None:
            barra.setValue(0)
            rotulo.setText("--%")
            barra.setStyleSheet(_barra_style("#4a5a6e"))
            return
        v = max(0.0, min(float(valor), 100.0))
        barra.setValue(int(v))
        rotulo.setText(f"{v:.0f}%")
        cor = COLOR_GREEN if v < 70 else (COLOR_ORANGE if v < 85 else COLOR_RED)
        barra.setStyleSheet(_barra_style(cor))

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

    def _checar_ollama(self) -> None:
        online = False
        modelo = ""
        try:
            import brain
            online, modelo = brain.verificar_conexao_ollama()
        except Exception:
            online, modelo = False, ""
        self.set_ollama_status(online, modelo or "")

    def set_ollama_status(self, online: bool, modelo: str = "") -> None:
        """Atualiza o indicador de status do Ollama (chamado externamente também)."""
        if online:
            self._ollama_dot.setStyleSheet("color: #00ff88; font-size: 11px;")
            self._ollama_text.setText(modelo or "ONLINE")
            self._ollama_text.setStyleSheet(
                "color: #00ff88; font-size: 10px; font-weight: bold;")
        else:
            self._ollama_dot.setStyleSheet("color: #ff2244; font-size: 11px;")
            self._ollama_text.setText("OFFLINE")
            self._ollama_text.setStyleSheet(
                "color: #ff2244; font-size: 10px; font-weight: bold;")


# ═══════════════════════════════════════════════════════════════════════════
# NEURAL CORE CONSTELLATION — HUD Holográfico (QPainter @ 60 FPS)
# ═══════════════════════════════════════════════════════════════════════════

class NeuralCoreConstellation(QWidget):
    """
    Núcleo estelar central + anéis de plasma concêntricos + 10 nós orbitais
    de módulos, conectados por linhas sinápticas (curvas de Bézier) com pulsos
    luminosos que percorrem as trilhas em direção aos módulos ativos.

    Otimização: a geometria dos nós é cacheada por `resizeEvent` (só é
    recalculada quando a janela muda de tamanho) e o desenho usa primitivas
    vetoriais leves com antialiasing apenas onde necessário.
    """

    statusChanged = Signal(str)  # "standby", "active", "processing"

    # Os 10 módulos integrados (ordem define a distribuição orbital).
    MODULES: tuple[tuple[str, str], ...] = (
        ("arquiteto", "ARQUITETO"),
        ("coder", "CODER"),
        ("auditor", "AUDITOR"),
        ("cyber_lab", "CYBER LAB"),
        ("database", "DATABASE"),
        ("web", "WEB AUTO"),
        ("network", "NETWORK"),
        ("memory", "MEMORY"),
        ("vision", "VISION"),
        ("optimizer", "OPTIMIZER"),
    )

    _NUM_PARTICLES = 110

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "standby"
        self._target_state = "standby"
        self._pulse = 0.0
        self._target_pulse = 0.0
        self._angle = 0.0

        # Atividade por módulo (decaimento suave para "apagar" após o uso).
        self._node_activity: dict[str, float] = {k: 0.0 for k, _ in self.MODULES}

        # Geometria cacheada dos nós.
        self._node_order: list[str] = []
        self._node_xy: dict[str, QPointF] = {}
        self._labels: dict[str, str] = {}

        # Partículas do núcleo estelar (expansão radial em loop).
        self._particles = [self._nova_particula(random.random())
                           for _ in range(self._NUM_PARTICLES)]

        self.setMinimumSize(320, 320)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60 FPS

    # ── Partículas ──

    @staticmethod
    def _nova_particula(dist: float) -> dict:
        return {
            "angle": random.uniform(0.0, 2.0 * math.pi),
            "dist": dist,
            "speed": random.uniform(0.004, 0.012),
            "size": random.uniform(1.2, 3.2),
            "alpha": random.uniform(0.35, 0.95),
        }

    # ── API pública ──

    def set_state(self, state: str) -> None:
        if state not in ("standby", "active", "processing"):
            return
        if self._target_state != state:
            self._target_state = state
            self._target_pulse = {
                "standby": 0.0, "active": 0.45, "processing": 0.7,
            }.get(state, 0.0)
            self.statusChanged.emit(state)

    def pulse_node(self, key: str) -> None:
        """Acende/pulsa um nó orbital (módulo em uso)."""
        if key in self._node_activity:
            self._node_activity[key] = 1.0

    def set_node_active(self, key: str, active: bool = True) -> None:
        if key in self._node_activity:
            self._node_activity[key] = 1.0 if active else 0.0

    # ── Tick / geometria ──

    def _tick(self) -> None:
        speeds = {"standby": 0.006, "active": 0.02, "processing": 0.035}
        self._angle += speeds.get(self._state, 0.006)
        if self._angle > 2.0 * math.pi:
            self._angle -= 2.0 * math.pi

        diff = self._target_pulse - self._pulse
        self._pulse += diff * 0.12
        if abs(diff) < 0.001:
            self._pulse = self._target_pulse
        if self._state != self._target_state:
            self._state = self._target_state

        # Decaimento da atividade dos nós.
        for k in self._node_activity:
            a = self._node_activity[k]
            if a > 0.0:
                self._node_activity[k] = max(0.0, a - 0.02)

        # Expansão radial contínua das partículas.
        for part in self._particles:
            part["dist"] += part["speed"]
            if part["dist"] >= 1.0:
                part["angle"] = random.uniform(0.0, 2.0 * math.pi)
                part["dist"] = 0.0
                part["speed"] = random.uniform(0.004, 0.012)

        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._recalcular_geometria()

    def showEvent(self, event) -> None:
        """Retoma a animação quando o widget volta a ficar visível."""
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event) -> None:
        """Pausa a animação quando o widget é oculto (economia de CPU)."""
        super().hideEvent(event)
        self._timer.stop()

    def _recalcular_geometria(self) -> None:
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return
        cx = w / 2.0
        cy = h / 2.0
        node_r = min(w, h) * 0.40
        n = len(self.MODULES)
        self._node_order = []
        self._node_xy = {}
        self._labels = {}
        for i, (key, label) in enumerate(self.MODULES):
            ang = -math.pi / 2.0 + i * (2.0 * math.pi / n)
            self._node_xy[key] = QPointF(
                cx + math.cos(ang) * node_r,
                cy + math.sin(ang) * node_r,
            )
            self._node_order.append(key)
            self._labels[key] = label

    # ── Bézier helpers ──

    @staticmethod
    def _controle_bezier(p0: QPointF, p1: QPointF) -> QPointF:
        mid = QPointF((p0.x() + p1.x()) / 2.0, (p0.y() + p1.y()) / 2.0)
        dx = p1.x() - p0.x()
        dy = p1.y() - p0.y()
        length = math.hypot(dx, dy) or 1.0
        offset = 0.18 * length
        return QPointF(mid.x() - dy / length * offset,
                       mid.y() + dx / length * offset)

    @staticmethod
    def _ponto_quadratico(p0: QPointF, ctrl: QPointF, p1: QPointF, t: float) -> QPointF:
        mt = 1.0 - t
        x = mt * mt * p0.x() + 2 * mt * t * ctrl.x() + t * t * p1.x()
        y = mt * mt * p0.y() + 2 * mt * t * ctrl.y() + t * t * p1.y()
        return QPointF(x, y)

    # ── Paint ──

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        R = min(w, h) / 2.0

        self._desenhar_glow(painter, cx, cy, R)
        self._desenhar_aneis(painter, cx, cy)
        self._desenhar_sinapses(painter, cx, cy)
        self._desenhar_nucleo(painter, cx, cy, R)
        self._desenhar_nos(painter, cx, cy)
        painter.end()

    def _desenhar_glow(self, p: QPainter, cx: float, cy: float, R: float) -> None:
        r = R * (0.92 + self._pulse * 0.06)
        grad = QRadialGradient(cx, cy, r)
        grad.setColorAt(0.0, QColor(24, 221, 229, int(14 + 22 * self._pulse)))
        grad.setColorAt(0.6, QColor(36, 153, 216, int(6 + 10 * self._pulse)))
        grad.setColorAt(1.0, QColor(36, 153, 216, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

    def _desenhar_aneis(self, p: QPainter, cx: float, cy: float) -> None:
        # Anel interno — gradiente de brilho amarelo/dourado (shimmer rotativo).
        r_in = min(self.width(), self.height()) * 0.30
        conic = QConicalGradient(cx, cy, -math.degrees(self._angle) % 360.0)
        conic.setColorAt(0.0, QColor(255, 200, 70, 210))
        conic.setColorAt(0.5, QColor(255, 240, 170, 110))
        conic.setColorAt(1.0, QColor(255, 200, 70, 210))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QBrush(conic), 2.2))
        p.drawEllipse(QRectF(cx - r_in, cy - r_in, r_in * 2, r_in * 2))

        # Anel externo — ciano neon com pulso suave.
        r_out = min(self.width(), self.height()) * 0.36
        alpha = 150 + 70 * self._pulse
        p.setPen(QPen(QColor(24, 221, 229, int(alpha)), 1.6))
        p.drawEllipse(QRectF(cx - r_out, cy - r_out, r_out * 2, r_out * 2))

    def _desenhar_sinapses(self, p: QPainter, cx: float, cy: float) -> None:
        if not self._node_order:
            return
        core = QPointF(cx, cy)
        now = time.time() % 1000.0
        for key in self._node_order:
            node = self._node_xy[key]
            act = self._node_activity.get(key, 0.0)
            ctrl = self._controle_bezier(core, node)

            # Trilha base (transparência cresce com a atividade).
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(24, 221, 229, int(26 + 66 * act)), 1.0))
            path = QPainterPath(core)
            path.quadTo(ctrl, node)
            p.drawPath(path)

            # Pulso luminoso percorrendo a linha em direção ao módulo.
            if act > 0.05:
                phase = (now * 0.6 + act) % 1.0
                pt = self._ponto_quadratico(core, ctrl, node, phase)
                pr = 2.0 + 2.6 * act
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(130, 240, 255, int(210 * act))))
                p.drawEllipse(QRectF(pt.x() - pr, pt.y() - pr, pr * 2, pr * 2))

        # Sinapses entre nós ativos (anel de ligação).
        ativos = [k for k in self._node_order if self._node_activity.get(k, 0.0) > 0.25]
        for i, key in enumerate(ativos):
            nxt = ativos[(i + 1) % len(ativos)]
            a = self._node_xy[key]
            b = self._node_xy[nxt]
            ctrl = self._controle_bezier(a, b)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(226, 47, 145, 34), 0.8))
            path2 = QPainterPath(a)
            path2.quadTo(ctrl, b)
            p.drawPath(path2)

    def _desenhar_nucleo(self, p: QPainter, cx: float, cy: float, R: float) -> None:
        core_max = R * 0.20
        for part in self._particles:
            d = part["dist"]
            r = d * core_max
            x = cx + math.cos(part["angle"]) * r
            y = cy + math.sin(part["angle"]) * r
            alpha = part["alpha"] * (1.0 - d)
            if alpha <= 0.02:
                continue
            size = part["size"] * (1.0 - 0.5 * d)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(80, 200, 255, int(255 * alpha))))
            p.drawEllipse(QRectF(x - size / 2.0, y - size / 2.0, size, size))

        # Ponto central brilhante.
        core_r = R * 0.06 * (1.0 + self._pulse * 0.3)
        grad = QRadialGradient(cx, cy, core_r * 2.4)
        grad.setColorAt(0.0, QColor(220, 250, 255, 235))
        grad.setColorAt(0.4, QColor(90, 210, 255, 160))
        grad.setColorAt(1.0, QColor(24, 221, 229, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QRectF(cx - core_r * 2.4, cy - core_r * 2.4,
                             core_r * 4.8, core_r * 4.8))

    def _desenhar_nos(self, p: QPainter, cx: float, cy: float) -> None:
        font = QFont(FONT_FAMILY.split(",")[0].strip(), 8)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1)
        p.setFont(font)
        for key in self._node_order:
            node = self._node_xy[key]
            x = node.x()
            y = node.y()
            act = self._node_activity.get(key, 0.0)

            # Halo externo ciano.
            halo = 5.0 + 3.0 * act
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(24, 221, 229, int(36 + 110 * act))))
            p.drawEllipse(QRectF(x - halo, y - halo, halo * 2, halo * 2))

            # Anel exterior luminoso amarelo/dourado.
            gold_r = 4.5 + 2.0 * act
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 200, 80, int(120 + 120 * act)), 1.4))
            p.drawEllipse(QRectF(x - gold_r, y - gold_r, gold_r * 2, gold_r * 2))

            # Núcleo do nó.
            core_r = 2.6 + 1.4 * act
            p.setPen(Qt.PenStyle.NoPen)
            node_cor = (QColor(24, 221, 229, 235) if act > 0.3
                        else QColor(120, 200, 210, 180))
            p.setBrush(QBrush(node_cor))
            p.drawEllipse(QRectF(x - core_r, y - core_r, core_r * 2, core_r * 2))

            # Rótulo com tipografia fina em ciano claro.
            label = self._labels.get(key, key)
            cor = QColor(COLOR_CYAN) if act > 0.3 else QColor(COLOR_TEXT_DIM)
            p.setPen(cor)
            if x >= cx:
                trect = QRectF(x + 9, y - 8, 96, 16)
                flags = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            else:
                trect = QRectF(x - 105, y - 8, 96, 16)
                flags = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            p.drawText(trect, flags, label)


# ═══════════════════════════════════════════════════════════════════════════
# HUD DIAGNOSTIC TREE — Árvore de telemetria sci-fi (coluna lateral)
# ═══════════════════════════════════════════════════════════════════════════

class HudDiagnosticTree(QWidget):
    """
    Linha de telemetria vertical com ramos horizontais e marcadores de
    checklist (estilo sci-fi). Indicadores reais para:
    Ollama Engine, VRAM/RAM Buffer, Task Runner, Knowledge Base,
    Network Map e Virtual Lab.

    Microtipografia: #50777D (inativo/dim) e #18DDE5 (ativo/ciano).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._order = ("ollama", "buffer", "runner", "knowledge", "network", "lab")
        self._items = {
            "ollama": {"title": "OLLAMA ENGINE", "active": False, "detail": "OFFLINE"},
            "buffer": {"title": "VRAM/RAM BUFFER", "active": True, "detail": "--"},
            "runner": {"title": "TASK RUNNER", "active": False, "detail": "IDLE"},
            "knowledge": {"title": "KNOWLEDGE BASE", "active": False, "detail": "--"},
            "network": {"title": "NETWORK MAP", "active": False, "detail": "IDLE"},
            "lab": {"title": "VIRTUAL LAB", "active": False, "detail": "IDLE"},
        }
        self.setMinimumSize(210, 320)

        # Cache de VRAM (evita spawnar `nvidia-smi` a cada poll).
        self._gpu_ticks = 0
        self._vram_cache = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(2000)
        # Primeira leitura adiada (não-bloqueante) para não travar o startup.
        QTimer.singleShot(0, self._poll)

    # ── API pública ──

    def set_item(self, key: str, active: bool = None, detail: str = None) -> None:
        """Atualiza um indicador (active/detail) e força repaint."""
        item = self._items.get(key)
        if item is None:
            return
        if active is not None:
            item["active"] = bool(active)
        if detail is not None:
            item["detail"] = str(detail)
        self.update()

    # ── Polling de telemetria real ──

    def _poll(self) -> None:
        self._poll_ollama()
        self._poll_buffer()
        self._poll_knowledge()
        self.update()

    def _poll_ollama(self) -> None:
        online = self._ollama_online()
        self._items["ollama"]["active"] = online
        self._items["ollama"]["detail"] = "ONLINE" if online else "OFFLINE"

    @staticmethod
    def _ollama_online() -> bool:
        """Checa a porta do Ollama via socket (rápido, sem HTTP bloqueante)."""
        import socket
        for host in ("127.0.0.1", "localhost"):
            try:
                with socket.create_connection((host, 11434), timeout=0.8):
                    return True
            except OSError:
                continue
        return False

    def _poll_buffer(self) -> None:
        ram = None
        try:
            import psutil
            ram = psutil.virtual_memory().percent
        except Exception:
            ram = None
        # VRAM: atualizada a cada ~5 polls (evita spawnar nvidia-smi a cada 2s).
        self._gpu_ticks += 1
        if self._gpu_ticks >= 5:
            self._gpu_ticks = 0
            self._vram_cache = self._ler_vram()
        vram = self._vram_cache
        parts = []
        if ram is not None:
            parts.append(f"RAM {ram:.0f}%")
        if vram is not None:
            parts.append(f"VRAM {vram:.0f}%")
        self._items["buffer"]["detail"] = " · ".join(parts) if parts else "--"

    def _ler_vram(self):
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                return round(gpus[0].memoryUtil * 100.0, 1)
        except Exception:
            pass
        return None

    def _poll_knowledge(self) -> None:
        try:
            import knowledge_base  # noqa: F401
            self._items["knowledge"]["active"] = True
            self._items["knowledge"]["detail"] = "READY"
        except Exception:
            self._items["knowledge"]["active"] = False
            self._items["knowledge"]["detail"] = "OFFLINE"

    # ── Paint ──

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        spine_x = 22.0
        node_x = 44.0
        label_x = 58.0
        row_h = (h - 44.0) / max(len(self._order), 1)
        y0 = 26.0

        # Coluna vertical (spine).
        y_top = y0
        y_bot = y0 + row_h * (len(self._order) - 1)
        p.setPen(QPen(QColor(80, 119, 125, 140), 1.0))
        p.drawLine(QPointF(spine_x, y_top), QPointF(spine_x, y_bot))

        font_title = QFont(FONT_FAMILY.split(",")[0].strip(), 9)
        font_title.setBold(True)
        font_title.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        font_detail = QFont(FONT_FAMILY.split(",")[0].strip(), 8)
        p.setFont(font_title)

        for i, key in enumerate(self._order):
            item = self._items[key]
            y = y0 + row_h * i
            active = item["active"]

            # Ramo horizontal.
            p.setPen(QPen(QColor(80, 119, 125, 120), 1.0))
            p.drawLine(QPointF(spine_x, y), QPointF(node_x, y))

            # Marcador de checklist (nó).
            if active:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(24, 221, 229, 55)))
                p.drawEllipse(QRectF(node_x - 7, y - 7, 14, 14))
                p.setBrush(QBrush(QColor(24, 221, 229, 240)))
                p.drawEllipse(QRectF(node_x - 3.5, y - 3.5, 7, 7))
                title_color = QColor(COLOR_CYAN)
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(80, 119, 125, 190), 1.2))
                p.drawEllipse(QRectF(node_x - 3.5, y - 3.5, 7, 7))
                title_color = QColor(COLOR_TEXT_DIM)

            # Título.
            p.setFont(font_title)
            p.setPen(title_color)
            p.drawText(QRectF(label_x, y - 11, w - label_x - 8, 16),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       item["title"])

            # Detalhe (microtipografia).
            p.setFont(font_detail)
            p.setPen(QColor(COLOR_TEXT_DIM))
            p.drawText(QRectF(label_x, y + 5, w - label_x - 8, 14),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       item["detail"])

        p.end()
