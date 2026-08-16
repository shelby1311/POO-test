"""
multimodal_ingestor.py — Multimodal Ingestor & Knowledge Extractor (J.A.R.V.I.S.)

Processa 4 tipos de entrada e transforma em conhecimento estruturado na
base local (RAG):

  - TXT / MD:        leitura de texto direta com encoding seguro.
  - PDF:             extração de texto (pypdf → pdfplumber → OCR) com fallback.
  - FOTO (PNG/JPG):  OCR (pytesseract) + descrição da imagem.
  - VÍDEO (MP4/MKV): extração de áudio + transcrição (faster-whisper) e
                     captura de keyframes (OpenCV).

Fluxo de `processar_arquivo()`:
  1. Extrai o conteúdo bruto (chamado dentro de uma QThread — AutomacaoWorker).
  2. Envia o conteúdo ao `brain.py` para estruturar um resumo executivo.
  3. Salva a síntese em `data/knowledge_base/` para enriquecer a memória RAG.

Bibliotecas opcionais (pypdf, pdfplumber, pytesseract, PIL, cv2, faster-whisper)
são importadas sob demanda; quando ausentes, o módulo emite mensagens
informativas e NÃO lança exceções.
"""

import datetime
import re
from pathlib import Path
from typing import Optional

try:
    import brain
except ImportError:  # pragma: no cover
    brain = None  # type: ignore[assignment]

try:
    import knowledge_base
except ImportError:  # pragma: no cover
    knowledge_base = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_TIPOS_TEXTO = {".txt", ".md", ".markdown"}
_TIPOS_PDF = {".pdf"}
_TIPOS_IMAGEM = {".png", ".jpg", ".jpeg"}
_TIPOS_VIDEO = {".mp4", ".mkv"}

# Limite de caracteres enviado ao LLM para o resumo (evita estourar contexto).
_LIMITE_CONTEXTO = 8000

# Modelo faster-whisper usado na transcrição de vídeo.
_WHISPER_MODEL = "base"
_WHISPER_DEVICE = "cpu"
_WHISPER_COMPUTE = "int8"

# Número máximo de keyframes extraídos de um vídeo.
_MAX_KEYFRAMES = 5


def _log(mensagem: str, nivel: str = "INFO") -> None:
    """Log formatado no terminal."""
    print(f"[INGEST {nivel:<5}] {mensagem}", flush=True)


# ---------------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------------


class MultimodalIngestor:
    """Processa arquivos multimodais e os converte em conhecimento RAG."""

    def processar_arquivo(self, caminho: str) -> tuple[bool, str, dict]:
        """
        Processa um arquivo e o ingere na base de conhecimento.

        Args:
            caminho: Caminho do arquivo (txt/md/pdf/png/jpg/mp4/mkv).

        Returns:
            Tupla (sucesso: bool, resumo_mensagem: str, metadados: dict).
        """
        caminho = str(caminho or "").strip().strip('"').strip("'")
        if not caminho:
            return False, "Nenhum caminho de arquivo informado.", {}

        arquivo = Path(caminho).expanduser()
        if not arquivo.exists() or not arquivo.is_file():
            return False, f"Arquivo não encontrado ou inválido: {caminho}", {}

        tipo = self._detectar_tipo(arquivo)
        if tipo is None:
            return False, (
                f"Tipo de arquivo não suportado: '{arquivo.suffix or '(sem extensão)'}'. "
                f"Formatos aceitos: TXT/MD, PDF, PNG/JPG, MP4/MKV."
            ), {}

        try:
            conteudo = self._extrair_conteudo(arquivo, tipo)
            if not conteudo or not conteudo.strip():
                return False, (
                    f"Não foi possível extrair conteúdo do arquivo '{arquivo.name}'. "
                    f"Verifique se ele não está vazio/corrompido e se as dependências "
                    f"opcionais estão instaladas."
                ), {"tipo": tipo, "arquivo": str(arquivo)}

            resumo = self._resumir(conteudo, arquivo, tipo)
            destino = self._salvar_sintese(arquivo, tipo, conteudo, resumo)

            metadados = {
                "tipo": tipo,
                "arquivo": str(arquivo),
                "nome": arquivo.name,
                "tamanho_bytes": arquivo.stat().st_size,
                "tamanho_conteudo": len(conteudo),
                "sintese_salva": destino,
            }
            mensagem = (
                f"✅ Ingestão concluída [{tipo.upper()}] — {arquivo.name}\n\n"
                f"📄 RESUMO EXECUTIVO:\n{resumo}\n\n"
                f"📚 Síntese salva em:\n{destino}"
            )
            return True, mensagem, metadados

        except Exception as exc:
            _log(f"Falha na ingestão de '{arquivo.name}': {exc}", "ERROR")
            return False, f"Falha na ingestão de '{arquivo.name}': {exc}", {}

    # ------------------------------------------------------------------
    # Detecção de tipo
    # ------------------------------------------------------------------

    def _detectar_tipo(self, arquivo: Path) -> Optional[str]:
        ext = arquivo.suffix.lower()
        if ext in _TIPOS_TEXTO:
            return "texto"
        if ext in _TIPOS_PDF:
            return "pdf"
        if ext in _TIPOS_IMAGEM:
            return "imagem"
        if ext in _TIPOS_VIDEO:
            return "video"
        return None

    # ------------------------------------------------------------------
    # Extração de conteúdo bruto
    # ------------------------------------------------------------------

    def _extrair_conteudo(self, arquivo: Path, tipo: str) -> str:
        if tipo == "texto":
            return self._extrair_texto(arquivo)
        if tipo == "pdf":
            return self._extrair_pdf(arquivo)
        if tipo == "imagem":
            return self._extrair_imagem(arquivo)
        if tipo == "video":
            return self._extrair_video(arquivo)
        return ""

    def _extrair_texto(self, arquivo: Path) -> str:
        """Lê texto com encoding seguro (tenta utf-8, depois latin-1, depois ignore)."""
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return arquivo.read_text(encoding=encoding)
            except (UnicodeDecodeError, UnicodeError):
                continue
            except OSError as exc:
                _log(f"Falha ao ler '{arquivo.name}': {exc}", "ERROR")
                return ""
        try:
            return arquivo.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            _log(f"Falha ao ler '{arquivo.name}': {exc}", "ERROR")
            return ""

    def _extrair_pdf(self, arquivo: Path) -> str:
        """Extrai texto de PDF: pypdf → pdfplumber → OCR (fallback)."""
        texto = self._pdf_pypdf(arquivo)
        if texto:
            return texto

        texto = self._pdf_pdfplumber(arquivo)
        if texto:
            return texto

        texto = self._pdf_ocr(arquivo)
        if texto:
            return texto

        return (
            "[AVISO] Não foi possível extrair texto do PDF. "
            "Instale 'pypdf' ou 'pdfplumber' (texto) ou 'pdf2image'+'pytesseract' "
            "(OCR) para habilitar a leitura de PDFs."
        )

    def _pdf_pypdf(self, arquivo: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""
        try:
            reader = PdfReader(str(arquivo))
            partes = [(pagina.extract_text() or "") for pagina in reader.pages]
            return "\n\n".join(p for p in partes if p.strip())
        except Exception as exc:
            _log(f"pypdf falhou em '{arquivo.name}': {exc}", "WARNING")
            return ""

    def _pdf_pdfplumber(self, arquivo: Path) -> str:
        try:
            import pdfplumber
        except ImportError:
            return ""
        try:
            with pdfplumber.open(str(arquivo)) as pdf:
                partes = [(pagina.extract_text() or "") for pagina in pdf.pages]
            return "\n\n".join(p for p in partes if p.strip())
        except Exception as exc:
            _log(f"pdfplumber falhou em '{arquivo.name}': {exc}", "WARNING")
            return ""

    def _pdf_ocr(self, arquivo: Path) -> str:
        try:
            import pytesseract
            from pdf2image import convert_from_path
        except ImportError:
            return ""
        try:
            paginas = convert_from_path(str(arquivo))
            partes = []
            for i, img in enumerate(paginas, 1):
                texto = pytesseract.image_to_string(img, lang="por+eng")
                if texto.strip():
                    partes.append(f"--- página {i} ---\n{texto}")
            return "\n\n".join(partes)
        except Exception as exc:
            _log(f"OCR do PDF falhou em '{arquivo.name}': {exc}", "WARNING")
            return ""

    def _extrair_imagem(self, arquivo: Path) -> str:
        """Extrai texto via OCR e gera uma descrição da imagem."""
        texto_ocr = self._ocr_imagem(arquivo)
        descricao = self._descrever_imagem(arquivo, texto_ocr)
        partes = []
        if descricao:
            partes.append(descricao)
        if texto_ocr:
            partes.append("TEXTO EXTRAÍDO (OCR):\n" + texto_ocr)
        if not partes:
            return (
                "[AVISO] Não foi possível analisar a imagem. Instale "
                "'pytesseract' e 'Pillow' para habilitar OCR."
            )
        return "\n\n".join(partes)

    def _ocr_imagem(self, arquivo: Path) -> str:
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            return ""
        try:
            img = Image.open(arquivo)
            try:
                return (pytesseract.image_to_string(img, lang="por+eng") or "").strip()
            except Exception:
                return (pytesseract.image_to_string(img) or "").strip()
        except Exception as exc:
            _log(f"OCR da imagem falhou em '{arquivo.name}': {exc}", "WARNING")
            return ""

    def _descrever_imagem(self, arquivo: Path, texto_ocr: str) -> str:
        try:
            from PIL import Image
            with Image.open(arquivo) as img:
                largura, altura = img.size
                fmt = img.format or arquivo.suffix.lstrip(".")
        except Exception:
            largura = altura = None
            fmt = arquivo.suffix.lstrip(".")
        partes = []
        if largura and altura:
            partes.append(f"Imagem de {largura}x{altura} pixels (formato {fmt}).")
        if texto_ocr:
            partes.append(
                f"A imagem contém texto legível via OCR: "
                f"{texto_ocr[:160]}{'...' if len(texto_ocr) > 160 else ''}"
            )
        return " ".join(partes)

    def _extrair_video(self, arquivo: Path) -> str:
        """Extrai transcrição (áudio) e keyframes (visual) do vídeo."""
        partes: list[str] = []

        transcricao = self._transcrever_video(arquivo)
        if transcricao:
            partes.append("TRANSCRIÇÃO DO ÁUDIO:\n" + transcricao)
        else:
            partes.append(
                "[AVISO] Transcrição indisponível. Instale 'faster-whisper' "
                "para habilitar a transcrição de vídeo."
            )

        keyframes = self._extrair_keyframes(arquivo)
        if keyframes:
            partes.append(keyframes)
        else:
            partes.append(
                "[AVISO] Extração de keyframes indisponível. Instale "
                "'opencv-python' para habilitar a análise visual."
            )

        return "\n\n".join(partes)

    def _transcrever_video(self, arquivo: Path) -> str:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            return ""
        try:
            modelo = WhisperModel(
                _WHISPER_MODEL, device=_WHISPER_DEVICE, compute_type=_WHISPER_COMPUTE
            )
            segmentos, _info = modelo.transcribe(str(arquivo), vad_filter=True)
            trechos = [seg.text.strip() for seg in segmentos]
            texto = " ".join(t for t in trechos if t).strip()
            return texto
        except Exception as exc:
            _log(f"Transcrição falhou em '{arquivo.name}': {exc}", "WARNING")
            return ""

    def _extrair_keyframes(self, arquivo: Path) -> str:
        try:
            import cv2
        except ImportError:
            return ""

        try:
            cap = cv2.VideoCapture(str(arquivo))
            if not cap.isOpened():
                cap.release()
                return ""

            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            n = min(_MAX_KEYFRAMES, total) if total > 0 else 0

            linhas = [f"KEYFRAMES — {total} frames, ~{fps:.1f} fps"]
            for i in range(n):
                pos = int((i + 0.5) * total / n)
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
                ok, frame = cap.read()
                if not ok:
                    continue
                texto = self._ocr_frame(frame)
                resumo = (texto[:140] + "...") if texto else "(sem texto detectado)"
                linhas.append(f"  • frame {pos}: {resumo}")
            cap.release()
            return "\n".join(linhas)
        except Exception as exc:
            _log(f"Extração de keyframes falhou em '{arquivo.name}': {exc}", "WARNING")
            return ""

    def _ocr_frame(self, frame) -> str:
        try:
            import pytesseract
            from PIL import Image
            import cv2
        except ImportError:
            return ""
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            try:
                return (pytesseract.image_to_string(img, lang="por+eng") or "").strip()
            except Exception:
                return (pytesseract.image_to_string(img) or "").strip()
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Resumo executivo via brain.py
    # ------------------------------------------------------------------

    def _resumir(self, conteudo: str, arquivo: Path, tipo: str) -> str:
        """Gera um resumo executivo usando o brain; usa heurística como fallback."""
        if brain is not None:
            try:
                system = (
                    "Você é o J.A.R.V.I.S., assistente executivo da SALLES INDUSTRIES. "
                    "Gere um RESUMO EXECUTIVO conciso do conteúdo fornecido, em "
                    "português (pt-BR), destacando os tópicos principais, ideias-chave "
                    "e pontos acionáveis. Use marcadores. Não invente informações."
                )
                prompt = (
                    f"ARQUIVO: {arquivo.name}\nTIPO: {tipo}\n\n"
                    f"CONTEÚDO:\n{conteudo[:_LIMITE_CONTEXTO]}"
                )
                texto = brain.consultar_texto_livre(system, prompt)
                if texto and texto.strip():
                    return texto.strip()
            except Exception as exc:
                _log(f"Resumo via brain falhou: {exc}", "WARNING")

        return self._resumo_heuristico(conteudo)

    @staticmethod
    def _resumo_heuristico(conteudo: str) -> str:
        """Fallback local: primeiras linhas do conteúdo como resumo."""
        linhas = [l.strip() for l in conteudo.splitlines() if l.strip()]
        trecho = "\n".join(linhas[:8])
        return f"[Resumo heurístico]\n{trecho[:600]}"

    # ------------------------------------------------------------------
    # Persistência na base de conhecimento (RAG)
    # ------------------------------------------------------------------

    def _salvar_sintese(
        self, arquivo: Path, tipo: str, conteudo: str, resumo: str
    ) -> str:
        """Salva a síntese em `data/knowledge_base/` como arquivo .txt indexável."""
        if knowledge_base is not None:
            base_dir = Path(getattr(knowledge_base, "KNOWLEDGE_BASE_DIR", Path("data") / "knowledge_base"))
        else:
            base_dir = Path(__file__).resolve().parent / "data" / "knowledge_base"

        base_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", arquivo.stem).strip("_")[:40] or "arquivo"
        destino = base_dir / f"ingest_{timestamp}_{slug}.txt"

        cabecalho = (
            f"# INGESTÃO MULTIMODAL\n"
            f"# Arquivo original: {arquivo}\n"
            f"# Tipo: {tipo}\n"
            f"# Data: {datetime.datetime.now().isoformat(timespec='seconds')}\n\n"
            f"## RESUMO EXECUTIVO\n{resumo}\n\n"
            f"## CONTEÚDO BRUTO\n{conteudo[:20000]}\n"
        )
        destino.write_text(cabecalho, encoding="utf-8")
        _log(f"Síntese salva em: {destino}", "INFO")
        return str(destino)


# ---------------------------------------------------------------------------
# Execução direta (teste / diagnóstico)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("=" * 60)
    print(" J.A.R.V.I.S — Teste do Multimodal Ingestor")
    print("=" * 60)

    if len(sys.argv) < 2:
        print("Uso: py multimodal_ingestor.py <caminho_do_arquivo>")
        sys.exit(1)

    ingestor = MultimodalIngestor()
    ok, mensagem, meta = ingestor.processar_arquivo(sys.argv[1])
    print(f"\nSucesso: {ok}")
    print(f"\n{mensagem}")
    print(f"\nMetadados: {meta}")
