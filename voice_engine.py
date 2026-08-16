"""
voice_engine.py — Motor de Voz e Áudio do J.A.R.V.I.S. (STT/TTS)

Síntese de fala (pyttsx3 + SAPI5 ou Edge-TTS neural) e reconhecimento de voz
(speech_recognition + Google STT) totalmente em português.

Inclui coordenação entre fala e escuta: o microfone é pausado
enquanto o Jarvis fala, evitando que ele processe a própria voz.
Suporte a barge-in: interrompe a fala quando o usuário começa a falar.
"""

import asyncio
import os
import subprocess
import tempfile
import threading
import time
from typing import Optional

import pyttsx3
import speech_recognition as sr

from config_manager import carregar_configuracao

# ---------------------------------------------------------------------------
# Estado global (thread-safe)
# ---------------------------------------------------------------------------

# Flag: True enquanto o Jarvis está falando → listener deve pausar
_falando = threading.Event()
_falando.clear()

# Lock para proteger acesso ao engine TTS
_tts_lock = threading.Lock()

# Engine TTS (inicializado sob demanda)
_engine: Optional[pyttsx3.Engine] = None

# Configuração do motor TTS: "sapi5" ou "edge"
_tts_engine_type: str = "sapi5"

# Flag para barge-in: True = interromper fala atual
_barge_in = threading.Event()
_barge_in.clear()

# Recognizer STT (reutilizável)
_recognizer: Optional[sr.Recognizer] = None
_microfone: Optional[sr.Microphone] = None

# Flag para usar normalizador de fala no TTS
_use_speech_normalizer = True

try:
    from speech_normalizer import normalize_for_speech, full_pipeline
except ImportError:
    _use_speech_normalizer = False
    def normalize_for_speech(t, **kw): return t
    def full_pipeline(t, **kw): return t

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _log(mensagem: str, nivel: str = "INFO") -> None:
    print(f"[VOICE {nivel:<5}] {mensagem}", flush=True)


def _obter_engine() -> pyttsx3.Engine:
    """Singleton do engine TTS com voz masculina estilo J.A.R.V.I.S. configurada."""
    global _engine
    if _engine is None:
        _engine = pyttsx3.init()
        _configurar_voz_jarvis(_engine)
    return _engine


# Palavras-chave usadas para identificar vozes masculinas no SAPI5.
_VOZES_MASCULINAS = (
    "daniel", "antonio", "jose", "david", "mark", "george", "ryan",
    "christopher", "guy", "eric", "prabhat", "enrique", "male",
)


def _configurar_voz_jarvis(engine: pyttsx3.Engine) -> None:
    """
    Seleciona uma voz MASCULINA (estilo J.A.R.V.I.S. — calma, grave e articulada).

    Prioridade de seleção:
      1. Voz masculina em português (pt-BR);
      2. Voz masculina em inglês (timbre de mordomo britânico);
      3. Qualquer voz em português;
      4. Qualquer voz disponível.
    """
    voices = engine.getProperty("voices")
    voz_pt_masc = None
    voz_masc = None
    voz_pt = None
    voz_any = None

    for v in voices:
        nome = (v.name or "").lower()
        langs = [l.lower() for l in (v.languages or [])]
        gender = str(getattr(v, "gender", "") or "").lower()
        is_pt = any("pt" in l for l in langs) or "brazil" in nome
        is_masc = (gender == "male") or any(k in nome for k in _VOZES_MASCULINAS)

        if is_pt and is_masc and voz_pt_masc is None:
            voz_pt_masc = v
        elif is_masc and voz_masc is None:
            voz_masc = v
        elif is_pt and voz_pt is None:
            voz_pt = v
        elif voz_any is None:
            voz_any = v

    escolhida = voz_pt_masc or voz_masc or voz_pt or voz_any
    if escolhida is not None:
        engine.setProperty("voice", escolhida.id)
        _log(f"Voz TTS (J.A.R.V.I.S.): {escolhida.name}", "INFO")
    else:
        _log("Nenhuma voz SAPI5 detectada.", "WARNING")

    # Ajustes de fala — tom grave, calmo e articulado (estilo Jarvis).
    engine.setProperty("rate", 178)     # palavras/minuto (mais pausado e claro)
    engine.setProperty("volume", 0.95)  # 0.0 a 1.0


def _obter_recognizer() -> tuple[sr.Recognizer, Optional[sr.Microphone]]:
    """Singleton do recognizer e microfone."""
    global _recognizer, _microfone
    if _recognizer is None:
        _recognizer = sr.Recognizer()
        _recognizer.energy_threshold = 300
        _recognizer.dynamic_energy_threshold = True
        _recognizer.pause_threshold = 0.8

    if _microfone is None:
        try:
            _microfone = sr.Microphone()
            _log("Microfone inicializado.", "INFO")
        except Exception as exc:
            _log(f"Microfone indisponivel: {exc}", "WARNING")
            _microfone = None

    return _recognizer, _microfone


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def definir_tts_engine(tipo: str) -> None:
    """
    Define o motor TTS: 'sapi5' (offline, nativo) ou 'edge' (neural, alta qualidade).
    Edge-TTS requer conexão com internet.
    """
    global _tts_engine_type
    if tipo in ("sapi5", "edge"):
        _tts_engine_type = tipo
        _log(f"Motor TTS definido: {tipo}")
    else:
        _log(f"Motor TTS desconhecido: {tipo}. Use 'sapi5' ou 'edge'.", "WARNING")


def falar(texto: str, bloquear_barge_in: bool = True) -> bool:
    """
    Sintetiza o texto em voz (pt-BR).

    Suporta dois motores:
      - sapi5 (padrão): pyttsx3 nativo do Windows, offline
      - edge: Microsoft Edge TTS (neural), alta qualidade, requer internet

    Enquanto fala, sinaliza a flag _falando para que o listener
    de microfone pause.

    Suporte a barge-in: se _barge_in for setado durante a fala,
    interrompe imediatamente.

    Args:
        texto: Texto a ser falado.
        bloquear_barge_in: Se True, monitora _barge_in e interrompe a fala.

    Returns:
        True se a fala foi concluída, False em caso de erro ou interrupção.
    """
    if not texto or not texto.strip():
        return False

    texto = texto.strip()

    # ── Normalização fonética para fala natural ──
    if _use_speech_normalizer:
        texto = normalize_for_speech(texto, voice_style="jarvis")

    _log(f"JARVIS: {texto}")

    # Reset barge-in antes de começar
    _barge_in.clear()

    with _tts_lock:
        try:
            # Sinaliza que está falando → listener pausa
            _falando.set()

            if _tts_engine_type == "edge":
                return _falar_edge(texto, bloquear_barge_in)
            else:
                return _falar_sapi5(texto, bloquear_barge_in)

        except Exception as exc:
            _log(f"Erro no TTS: {exc}", "ERROR")
            return False

        finally:
            # Libera o listener
            _falando.clear()
            time.sleep(0.1)


def _falar_sapi5(texto: str, bloquear_barge_in: bool) -> bool:
    """Síntese via pyttsx3/SAPI5 com suporte a barge-in."""
    engine = _obter_engine()

    if not bloquear_barge_in:
        engine.say(texto)
        engine.runAndWait()
        return True

    # Modo com barge-in: divide em frases e verifica entre cada uma
    frases = [f.strip() for f in texto.replace("!", ".").replace("?", ".").split(".") if f.strip()]
    if not frases:
        frases = [texto]

    for frase in frases:
        if _barge_in.is_set():
            _log("Barge-in acionado — interrompendo fala.", "INFO")
            engine.stop()
            return False
        engine.say(frase)
        engine.runAndWait()

    return True


def _falar_edge(texto: str, bloquear_barge_in: bool) -> bool:
    """Síntese via Edge-TTS com voz neural de alta qualidade."""
    try:
        import edge_tts
    except ImportError:
        _log("edge-tts não instalado. Fallback para SAPI5.", "WARNING")
        return _falar_sapi5(texto, bloquear_barge_in)

    voz = "pt-BR-AntonioNeural"  # Voz masculina pt-BR de alta qualidade

    async def _sintetizar() -> bool:
        try:
            communicate = edge_tts.Communicate(texto, voz)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
            await communicate.save(tmp_path)

            # Reproduz com verificação de barge-in (Windows Media.SoundPlayer)
            proc = subprocess.Popen(
                ["powershell", "-c",
                 f"(New-Object Media.SoundPlayer '{tmp_path}').PlaySync()"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            while proc.poll() is None:
                if bloquear_barge_in and _barge_in.is_set():
                    proc.terminate()
                    _log("Barge-in acionado — interrompendo Edge-TTS.", "INFO")
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    return False
                time.sleep(0.05)

            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return True
        except Exception as exc:
            _log(f"Erro no Edge-TTS: {exc}", "ERROR")
            return False

    try:
        return asyncio.run(_sintetizar())
    except RuntimeError:
        # Event loop já rodando — usa thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, _sintetizar())
            return future.result(timeout=60)


def solicitar_barge_in() -> None:
    """
    Aciona o barge-in: interrompe a fala atual do J.A.R.V.I.S.
    Chamado quando o sistema detecta que o usuário começou a falar.
    """
    _barge_in.set()
    _log("Solicitação de barge-in recebida.", "DEBUG")


def barge_in_acionado() -> bool:
    """Retorna True se o barge-in foi solicitado."""
    return _barge_in.is_set()


def ouvindo() -> bool:
    """Retorna True se o Jarvis está falando no momento."""
    return _falando.is_set()


def ouvir_microfone(
    timeout: int = 5,
    limite_fala: int = 10,
    idioma: str = "pt-BR",
) -> str:
    """
    Ativa o microfone, escuta e converte fala em texto (pt-BR).

    Usa Google Speech Recognition (gratuito) para transcrição.

    Args:
        timeout: Segundos de silêncio antes de desistir.
        limite_fala: Duração máxima da fala capturada.
        idioma: Código do idioma (padrão: pt-BR).

    Returns:
        String do que foi dito, ou string vazia em caso de
        silêncio, timeout, ou erro.
    """
    recognizer, mic = _obter_recognizer()

    if mic is None:
        _log("Microfone nao disponivel para escuta.", "ERROR")
        return ""

    # Não escuta enquanto o Jarvis está falando
    if _falando.is_set():
        _log("Jarvis esta falando — escuta pausada.", "DEBUG")
        return ""

    try:
        with mic as source:
            _log("Ajustando ruido ambiente...", "DEBUG")
            recognizer.adjust_for_ambient_noise(source, duration=1)

            _log("Ouvindo...", "INFO")
            audio = recognizer.listen(
                source,
                timeout=timeout,
                phrase_time_limit=limite_fala,
            )

        _log("Processando fala...", "DEBUG")
        texto = recognizer.recognize_google(audio, language=idioma)
        _log(f"Usuario disse: '{texto}'")

        return texto

    except sr.WaitTimeoutError:
        _log("Nenhuma fala detectada (timeout).", "DEBUG")
        return ""

    except sr.UnknownValueError:
        _log("Nao foi possivel entender o audio.", "WARNING")
        return ""

    except sr.RequestError as exc:
        _log(f"Erro no servico de reconhecimento: {exc}", "ERROR")
        return ""

    except OSError as exc:
        _log(f"Erro no dispositivo de audio: {exc}", "ERROR")
        # Reseta o microfone para a próxima tentativa
        global _microfone
        _microfone = None
        return ""

    except Exception as exc:
        _log(f"Erro inesperado na escuta: {exc}", "ERROR")
        return ""


def escutar_em_segundo_plano(
    callback,
    timeout: int = 5,
    limite_fala: int = 10,
    idioma: str = "pt-BR",
) -> None:
    """
    Inicia a escuta em uma thread separada. Quando uma fala for detectada,
    chama callback(texto_transcrito).

    Ideal para loops principais onde o Jarvis fica constantemente ouvindo.

    Args:
        callback: Função que recebe a string transcrita.
        timeout: Timeout de escuta por tentativa.
        limite_fala: Duração máxima da fala.
        idioma: Código do idioma.
    """
    def _loop_escuta():
        _log("Escuta em segundo plano iniciada.", "INFO")
        while True:
            try:
                texto = ouvir_microfone(timeout=timeout,
                                        limite_fala=limite_fala,
                                        idioma=idioma)
                if texto:
                    callback(texto)
            except Exception as exc:
                _log(f"Erro no loop de escuta: {exc}", "ERROR")
                time.sleep(1)

    thread = threading.Thread(target=_loop_escuta, daemon=True)
    thread.start()
    return thread


def listar_vozes() -> list[dict]:
    """Lista todas as vozes TTS disponíveis no sistema."""
    engine = _obter_engine()
    voices = engine.getProperty("voices")
    return [
        {
            "id": v.id,
            "name": v.name,
            "languages": v.languages,
            "gender": getattr(v, "gender", "desconhecido"),
        }
        for v in voices
    ]


# ---------------------------------------------------------------------------
# Teste direto
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S — Teste do Voice Engine (STT/TTS)")
    print("=" * 60)

    # 1. Listar vozes
    print("\n[1] Vozes disponiveis:")
    for v in listar_vozes():
        print(f"    - {v['name']} ({v['languages']})")

    # 2. Teste de fala
    print("\n[2] Testando TTS (fala)...")
    falar("Ola, senhor. Sistema de voz do JARVIS online e operacional.")

    # 3. Teste de escuta (interativo)
    print("\n[3] Testando STT (escuta)...")
    print("    Fale algo no microfone (5s de timeout)...")
    texto = ouvir_microfone(timeout=5, limite_fala=5)

    if texto:
        print(f"\n    Voce disse: '{texto}'")
        falar(f"Voce disse: {texto}")
    else:
        print("    Nenhuma fala detectada.")
        falar("Nao detectei nenhuma fala, senhor.")

    print("\n[VOICE] Teste concluido.")
