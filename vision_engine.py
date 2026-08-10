"""
vision_engine.py — J.A.R.V.I.S. Vision & Audio Hardware Engine v1.0

Gerencia hardware de entrada: webcams e microfones.
Oferece enumeração de dispositivos, captura de vídeo/áudio,
reconhecimento facial e configuração persistente via config.json.

Requer: opencv-python, speech_recognition, face_recognition (opcional)
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO PERSISTENTE
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_VISION_CONFIG = {
    "camera_id": 0,
    "microphone_id": None,
    "audio_sensitivity": 0.5,
    "facial_recognition_enabled": False,
    "authorized_face_image": "",
    "capture_interval_ms": 1000,
    "auto_start_webcam": False,
}

_config_path = Path(__file__).resolve().parent / "vision_config.json"


def _log(msg: str, level: str = "INFO") -> None:
    print(f"[VISION {level:<5}] {msg}", flush=True)


def load_config() -> dict:
    if _config_path.exists():
        try:
            with open(_config_path, "r", encoding="utf-8") as f:
                return {**DEFAULT_VISION_CONFIG, **json.load(f)}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_VISION_CONFIG)


def save_config(config: dict) -> None:
    with open(_config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════
# ENUMERAÇÃO DE DISPOSITIVOS
# ═══════════════════════════════════════════════════════════════════════════

def list_webcams() -> list[dict]:
    """Enumera todas as webcams disponíveis no sistema."""
    try:
        import cv2
    except ImportError:
        _log("opencv-python não instalado.", "ERROR")
        return []

    cameras = []
    for i in range(10):
        try:
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                cameras.append({
                    "id": i,
                    "resolution": f"{w}x{h}",
                    "fps": round(fps, 1),
                })
                cap.release()
        except Exception:
            continue
    return cameras


def list_microphones() -> list[dict]:
    """Enumera todos os microfones disponíveis."""
    try:
        import speech_recognition as sr
    except ImportError:
        _log("speech_recognition não instalado.", "ERROR")
        return []

    mics = []
    for index, name in enumerate(sr.Microphone.list_microphone_names()):
        mics.append({"id": index, "name": name})
    return mics


def detect_hardware() -> dict:
    """Detecta todo o hardware de entrada disponível."""
    return {
        "webcams": list_webcams(),
        "microphones": list_microphones(),
        "timestamp": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# CAPTURA DE WEBCAM
# ═══════════════════════════════════════════════════════════════════════════

class WebcamCapture:
    """Gerencia captura de webcam com suporte a reconhecimento facial."""

    def __init__(self, camera_id: int = 0):
        self.camera_id = camera_id
        self._cap = None
        self._known_faces: list = []       # encodings
        self._known_names: list[str] = []   # nomes
        self._face_recognition_loaded = False

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def open(self) -> bool:
        try:
            import cv2
            self._cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
            if not self._cap.isOpened():
                _log(f"Falha ao abrir câmera {self.camera_id}", "ERROR")
                return False
            _log(f"Câmera {self.camera_id} aberta", "INFO")
            return True
        except ImportError:
            _log("opencv-python não instalado", "ERROR")
            return False

    def close(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None
            try:
                import cv2
                cv2.destroyAllWindows()
            except ImportError:
                pass

    def capture_frame(self) -> Optional[object]:
        """Captura um frame da webcam. Retorna numpy array (BGR) ou None."""
        if not self.is_open:
            return None
        ret, frame = self._cap.read()
        return frame if ret else None

    def load_authorized_face(self, image_path: str, name: str) -> bool:
        """Carrega foto de referência para reconhecimento facial."""
        try:
            import face_recognition
            import cv2

            if not os.path.isfile(image_path):
                _log(f"Arquivo de rosto não encontrado: {image_path}", "ERROR")
                return False

            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)
            if not encodings:
                _log("Nenhum rosto detectado na imagem de referência.", "ERROR")
                return False

            self._known_faces.append(encodings[0])
            self._known_names.append(name)
            self._face_recognition_loaded = True
            _log(f"Rosto autorizado carregado: {name}", "INFO")
            return True

        except ImportError:
            _log("face_recognition não instalado. pip install face-recognition", "ERROR")
            return False

    def identify_face(self, frame) -> tuple[Optional[str], list]:
        """
        Identifica rostos no frame.
        
        Returns:
            (nome_identificado, lista_de_localizações)
            nome_identificado = None se nenhum rosto conhecido encontrado
        """
        if not self._face_recognition_loaded:
            return None, []

        try:
            import face_recognition
            import cv2

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            locations = face_recognition.face_locations(rgb)

            if not locations:
                return None, []

            encodings = face_recognition.face_encodings(rgb, locations)
            for encoding in encodings:
                matches = face_recognition.compare_faces(
                    self._known_faces, encoding, tolerance=0.6)
                if True in matches:
                    idx = matches.index(True)
                    return self._known_names[idx], locations

            return "Desconhecido", locations

        except ImportError:
            return None, []


# ═══════════════════════════════════════════════════════════════════════════
# CAPTURA DE ÁUDIO COM SELEÇÃO DE MICROFONE
# ═══════════════════════════════════════════════════════════════════════════

class AudioCapture:
    """Gerencia captura de áudio com microfone selecionável."""

    def __init__(self, mic_index: Optional[int] = None):
        self.mic_index = mic_index
        self._recognizer = None
        self._sensitivity = 0.5

    @property
    def recognizer(self):
        if self._recognizer is None:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
            self._recognizer.energy_threshold = 300
            self._recognizer.dynamic_energy_threshold = True
            self._recognizer.pause_threshold = 0.8
        return self._recognizer

    def set_sensitivity(self, value: float) -> None:
        """Ajusta sensibilidade do microfone (0.0 a 1.0)."""
        self._sensitivity = max(0.1, min(1.0, value))
        # Converte para energy_threshold (300 = padrão, 100 = sensível, 1000 = baixa)
        self.recognizer.energy_threshold = int(1000 - self._sensitivity * 900)

    def listen(
        self,
        timeout: int = 5,
        phrase_limit: int = 10,
        language: str = "pt-BR",
    ) -> str:
        """
        Escuta pelo microfone selecionado e converte fala em texto.

        Args:
            timeout: Segundos de silêncio antes de desistir.
            phrase_limit: Duração máxima da fala.
            language: Código do idioma.

        Returns:
            Texto transcrito ou string vazia.
        """
        try:
            import speech_recognition as sr

            mic_kwargs = {}
            if self.mic_index is not None:
                mic_kwargs["device_index"] = self.mic_index

            with sr.Microphone(**mic_kwargs) as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                audio = self.recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_limit)

            return self.recognizer.recognize_google(audio, language=language)

        except ImportError:
            _log("speech_recognition não instalado", "ERROR")
            return ""
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as exc:
            _log(f"Erro no serviço de transcrição: {exc}", "ERROR")
            return ""
        except Exception as exc:
            _log(f"Erro na captura de áudio: {exc}", "ERROR")
            return ""

    def start_background_listening(
        self,
        callback: Callable[[str], None],
        language: str = "pt-BR",
    ) -> None:
        """
        Inicia escuta em background thread.
        callback(texto_transcrito) é chamado quando fala é detectada.
        """
        import threading

        def _loop():
            while True:
                try:
                    text = self.listen(timeout=5, language=language)
                    if text:
                        callback(text)
                except Exception as exc:
                    _log(f"Erro no loop de escuta: {exc}", "ERROR")
                    time.sleep(1)

        thread = threading.Thread(target=_loop, daemon=True)
        thread.start()


# ═══════════════════════════════════════════════════════════════════════════
# GERENCIADOR UNIFICADO DE HARDWARE
# ═══════════════════════════════════════════════════════════════════════════

class HardwareManager:
    """Gerencia toda a configuração de hardware de entrada."""

    def __init__(self):
        self.config = load_config()
        self.webcam: Optional[WebcamCapture] = None
        self.audio: Optional[AudioCapture] = None

    def setup(self) -> dict:
        """Configura hardware baseado na config atual."""
        status = {"webcam": False, "microphone": False, "face_recognition": False}

        # Webcam
        if self.config.get("camera_id") is not None:
            self.webcam = WebcamCapture(self.config["camera_id"])
            status["webcam"] = self.webcam.open()

        # Microfone
        mic_id = self.config.get("microphone_id")
        self.audio = AudioCapture(mic_id)
        self.audio.set_sensitivity(self.config.get("audio_sensitivity", 0.5))
        status["microphone"] = True  # AudioCapture é lazy

        # Reconhecimento facial
        if self.config.get("facial_recognition_enabled"):
            face_img = self.config.get("authorized_face_image", "")
            if face_img and self.webcam and self.webcam.is_open:
                status["face_recognition"] = self.webcam.load_authorized_face(
                    face_img, "Usuário Autorizado"
                )

        _log(f"Hardware configurado: {status}")
        return status

    def update_config(self, **kwargs) -> None:
        """Atualiza configuração e persiste."""
        self.config.update(kwargs)
        save_config(self.config)

    def shutdown(self) -> None:
        if self.webcam:
            self.webcam.close()


# ═══════════════════════════════════════════════════════════════════════════
# Teste
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S. Vision Engine — Teste de Hardware")
    print("=" * 60)

    # 1. Detectar hardware
    print("\n[1] Detectando hardware...")
    hw = detect_hardware()
    print(f"    Webcams: {len(hw['webcams'])}")
    for cam in hw["webcams"]:
        print(f"      ID {cam['id']}: {cam['resolution']} @ {cam['fps']}fps")
    print(f"    Microfones: {len(hw['microphones'])}")
    for mic in hw["microphones"][:5]:
        print(f"      ID {mic['id']}: {mic['name'][:60]}")

    # 2. Testar webcam (captura 1 frame)
    if hw["webcams"]:
        cam_id = hw["webcams"][0]["id"]
        print(f"\n[2] Testando webcam ID {cam_id}...")
        cam = WebcamCapture(cam_id)
        if cam.open():
            frame = cam.capture_frame()
            if frame is not None:
                import cv2
                print(f"    Frame capturado: {frame.shape}")
                # Salva frame de teste
                cv2.imwrite("test_frame.jpg", frame)
                print(f"    Salvo em test_frame.jpg")
            cam.close()
        else:
            print("    Falha ao abrir webcam")

    print("\n[VISION] Teste concluído.")
