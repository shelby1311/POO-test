"""
meeting_summarizer.py — Smart Audio & Meeting Summarizer (J.A.R.V.I.S.)

Captura áudio local do microfone, transcreve offline via faster-whisper e gera
automaticamente um resumo em Markdown. Projetado para rodar dentro de uma
QThread (AutomacaoWorker) — a gravação é bloqueante apenas dentro da thread.

Comando principal: /record [duração_em_segundos]

Fluxo:
  1. Grava o microfone por N segundos (padrão 60) → WAV em data/meetings/.
  2. Transcreve via web_learner.transcrever_audio_whisper (offline).
  3. Gera resumo Markdown (heurística + LLM local opcional) em data/meetings/.
"""

import datetime
import re
from pathlib import Path
from typing import Optional, Tuple

try:
    from config_manager import carregar_configuracao
except ImportError:  # pragma: no cover
    def carregar_configuracao() -> dict:
        return {}

try:
    import web_learner
except ImportError:  # pragma: no cover
    web_learner = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

_STOPWORDS = set(
    """a o e de do da em um uma os as para com por no na que se não não mais
    como foi foram ser ter mas ou ao aos é são está eu você ele ela nós eles
    elas isso isso the of and to in is it for on with as are was were be
    this that have has had not but or from by at an we you they i he she""".split()
)


def _log(mensagem: str, nivel: str = "INFO") -> None:
    print(f"[MEETING {nivel:<5}] {mensagem}", flush=True)


def _diretorio_reunioes() -> Path:
    config = carregar_configuracao()
    data_dir = Path(config.get("data_directory", "data"))
    meetings = data_dir / "meetings"
    meetings.mkdir(parents=True, exist_ok=True)
    return meetings


# ---------------------------------------------------------------------------
# Gravação de áudio
# ---------------------------------------------------------------------------

def gravar_audio(
    duracao_segundos: int = 60,
    caminho_saida: Optional[str] = None,
    taxa: int = 16000,
) -> Tuple[bool, str]:
    """
    Grava o microfone por `duracao_segundos` e salva em WAV.

    Usa pyaudio (se disponível) com fallback para speech_recognition.
    Retorna (sucesso, caminho_do_arquivo_ou_erro).
    """
    if caminho_saida is None:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho_saida = str(_diretorio_reunioes() / f"gravacao_{ts}.wav")

    try:
        return _gravar_com_pyaudio(duracao_segundos, caminho_saida, taxa)
    except ImportError:
        _log("pyaudio indisponível — tentando speech_recognition.", "WARNING")
        return _gravar_com_speech_recognition(duracao_segundos, caminho_saida)
    except Exception as exc:
        return False, f"Falha ao gravar áudio: {exc}"


def _gravar_com_pyaudio(
    duracao_segundos: int, caminho_saida: str, taxa: int
) -> Tuple[bool, str]:
    import pyaudio
    import wave

    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = taxa

    pa = pyaudio.PyAudio()
    sample_width = pa.get_sample_size(FORMAT)
    stream = pa.open(
        format=FORMAT, channels=CHANNELS, rate=RATE,
        input=True, frames_per_buffer=CHUNK,
    )
    frames: list[bytes] = []
    total_chunks = int(RATE / CHUNK * duracao_segundos)
    _log(f"Gravando por {duracao_segundos}s...")

    try:
        for _ in range(total_chunks):
            frames.append(stream.read(CHUNK, exception_on_overflow=False))
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()

    with wave.open(caminho_saida, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(sample_width)
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))

    _log(f"Áudio salvo: {caminho_saida}")
    return True, caminho_saida


def _gravar_com_speech_recognition(
    duracao_segundos: int, caminho_saida: str
) -> Tuple[bool, str]:
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
            audio = recognizer.listen(
                source, timeout=duracao_segundos + 5,
                phrase_time_limit=duracao_segundos,
            )
        with open(caminho_saida, "wb") as f:
            f.write(audio.get_wav_data())
        return True, caminho_saida
    except sr.WaitTimeoutError:
        return False, "Nenhum áudio detectado (timeout)."
    except Exception as exc:
        return False, f"Falha na gravação via speech_recognition: {exc}"


# ---------------------------------------------------------------------------
# Transcrição e resumo
# ---------------------------------------------------------------------------

def transcrever_audio(caminho_audio: str) -> str:
    """Transcreve um arquivo de áudio via faster-whisper offline."""
    if web_learner is None:
        _log("web_learner indisponível.", "ERROR")
        return ""
    try:
        return web_learner.transcrever_audio_whisper(caminho_audio, model_size="base", idioma="pt")
    except Exception as exc:
        _log(f"Falha na transcrição: {exc}", "ERROR")
        return ""


def _palavras_frequentes(texto: str, limite: int = 10) -> list[tuple[str, int]]:
    palavras = re.findall(r"[A-Za-zÀ-ÿ0-9]+", texto.lower())
    freq: dict[str, int] = {}
    for p in palavras:
        if len(p) > 3 and p not in _STOPWORDS:
            freq[p] = freq.get(p, 0) + 1
    return sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[:limite]


def _resumo_llm(transcricao: str) -> str:
    """Gera um resumo via LLM local (opcional)."""
    try:
        import brain
    except ImportError:
        return ""
    if not hasattr(brain, "consultar_texto_livre"):
        return ""
    try:
        return (brain.consultar_texto_livre(
            "Você é um assistente de reuniões. Gere um resumo objetivo em "
            "Markdown com: tópicos principais, decisões e ações/pendências. "
            "Responda apenas o resumo em Markdown.",
            "Transcrição da reunião:\n" + transcricao[:6000],
        ) or "").strip()
    except Exception:
        return ""


def gerar_resumo_markdown(
    transcricao: str, duracao_segundos: int, caminho_audio: str
) -> str:
    """Gera o documento Markdown do resumo da reunião."""
    palavras = len(transcricao.split())
    top = _palavras_frequentes(transcricao)

    linhas = [
        "# Resumo de Reunião",
        "",
        f"- **Data:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Duração:** {duracao_segundos}s",
        f"- **Áudio:** {caminho_audio}",
        f"- **Palavras transcritas:** {palavras}",
        "",
        "## Tópicos Frequentes",
        "",
    ]
    if top:
        for palavra, n in top:
            linhas.append(f"- **{palavra}** ({n})")
    else:
        linhas.append("(nenhum tópico identificado)")
    linhas.append("")

    resumo_llm = _resumo_llm(transcricao)
    if resumo_llm:
        linhas.append("## Resumo (IA)")
        linhas.append("")
        linhas.append(resumo_llm)
        linhas.append("")

    linhas += [
        "## Transcrição",
        "",
        transcricao if transcricao else "(transcrição vazia)",
    ]
    return "\n".join(linhas)


def gravar_e_resumir(duracao_segundos: int = 60) -> Tuple[bool, str]:
    """
    Fluxo completo do /record: grava → transcreve → resume → salva Markdown.

    Returns:
        (sucesso, resumo_para_chat)
    """
    duracao = max(5, min(int(duracao_segundos or 60), 3600))
    ok, caminho_audio = gravar_audio(duracao)
    if not ok:
        return False, caminho_audio

    transcricao = transcrever_audio(caminho_audio)
    if not transcricao:
        return False, "Transcrição vazia — nenhuma fala detectada ou Whisper indisponível."

    markdown = gerar_resumo_markdown(transcricao, duracao, caminho_audio)

    caminho_md = ""
    try:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho_md = str(_diretorio_reunioes() / f"resumo_{ts}.md")
        Path(caminho_md).write_text(markdown, encoding="utf-8")
    except OSError as exc:
        _log(f"Falha ao salvar resumo: {exc}", "WARNING")

    resumo_chat = (
        f"REUNIÃO RESUMIDA\n{'─' * 40}\n"
        f"Áudio: {caminho_audio}\n"
        f"Resumo: {caminho_md or '(não salvo)'}\n"
        f"Palavras transcritas: {len(transcricao.split())}\n\n"
        f"{markdown[:2500]}"
    )
    return True, resumo_chat


# ---------------------------------------------------------------------------
# Teste direto (sem gravar — apenas helpers)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S — Meeting Summarizer (teste)")
    print("=" * 60)
    print("Use /record no chat para gravar e resumir uma reunião.")
    print("Helpers:", _palavras_frequentes("reunião reunião sobre o projeto projeto do banco"))
