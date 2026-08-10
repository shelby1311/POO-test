"""
voice_engine.py — Motor de Voz e Áudio do J.A.R.V.I.S. (STT/TTS)

Síntese de fala offline (pyttsx3 + SAPI5) e reconhecimento de voz
(speech_recognition + Google STT) totalmente em português.

Inclui coordenação entre fala e escuta: o microfone é pausado
enquanto o Jarvis fala, evitando que ele processe a própria voz.
"""

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

# Recognizer STT (reutilizável)
_recognizer: Optional[sr.Recognizer] = None
_microfone: Optional[sr.Microphone] = None

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _log(mensagem: str, nivel: str = "INFO") -> None:
    print(f"[VOICE {nivel:<5}] {mensagem}", flush=True)


def _obter_engine() -> pyttsx3.Engine:
    """Singleton do engine TTS com voz pt-BR configurada."""
    global _engine
    if _engine is None:
        _engine = pyttsx3.init()
        _configurar_voz_portugues(_engine)
    return _engine


def _configurar_voz_portugues(engine: pyttsx3.Engine) -> None:
    """Seleciona a voz em português (Maria) se disponível."""
    voices = engine.getProperty("voices")
    voz_pt = None
    voz_en = None

    for v in voices:
        langs = [l.lower() for l in (v.languages or [])]
        if any("pt" in l for l in langs) or "brazil" in v.name.lower():
            voz_pt = v
            break
        if any("en" in l for l in langs):
            voz_en = v

    if voz_pt:
        engine.setProperty("voice", voz_pt.id)
        _log(f"Voz TTS: {voz_pt.name}", "INFO")
    elif voz_en:
        engine.setProperty("voice", voz_en.id)
        _log(f"Voz pt-BR nao encontrada. Fallback: {voz_en.name}", "WARNING")
    else:
        _log("Nenhuma voz SAPI5 detectada.", "WARNING")

    # Ajustes de fala
    engine.setProperty("rate", 190)     # palavras/minuto (padrão ~200)
    engine.setProperty("volume", 0.9)   # 0.0 a 1.0


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


def falar(texto: str) -> bool:
    """
    Sintetiza o texto em voz (pt-BR) usando pyttsx3/SAPI5.

    Enquanto fala, sinaliza a flag global _falando para que o listener
    de microfone pause e não processe a própria voz do Jarvis.

    Args:
        texto: Texto a ser falado.

    Returns:
        True se a fala foi concluída, False em caso de erro.
    """
    if not texto or not texto.strip():
        return False

    texto = texto.strip()
    _log(f"JARVIS: {texto}")

    with _tts_lock:
        try:
            engine = _obter_engine()

            # Sinaliza que está falando → listener pausa
            _falando.set()

            engine.say(texto)
            engine.runAndWait()

            return True

        except Exception as exc:
            _log(f"Erro no TTS: {exc}", "ERROR")
            return False

        finally:
            # Libera o listener
            _falando.clear()
            # Pequena pausa para o microfone reativar
            time.sleep(0.1)


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
