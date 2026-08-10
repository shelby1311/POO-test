"""
web_learner.py — Auto-Pesquisa e Aprendizado Contínuo v2.0 (RAG + Video + Padrões)

Capacidades expandidas:
  - Pesquisa web via DuckDuckGo HTML + raspagem de páginas
  - Extração e processamento de transcrições/legendas de vídeos (locais e web)
  - Análise de padrões comunicativos para humanização contínua da fala
  - Armazenamento vetorial (ChromaDB) e fallback SQLite + FTS5
  - Adaptação linguística contínua baseada em conteúdo consumido

Zero dependências externas obrigatórias além da stdlib.
chromadb é opcional (fallback automático para SQLite).
"""

import json
import os
import re
import sqlite3
import time
import urllib.request
import urllib.parse
import urllib.error
import hashlib
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from config_manager import carregar_configuracao

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

DUCKDUCKGO_HTML = "https://html.duckduckgo.com/html/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
MAX_RESULTADOS_BUSCA = 5
MAX_PAGINAS_RASPAR = 3
TAMANHO_CHUNK = 500       # caracteres por chunk
OVERLAP_CHUNK = 100       # sobreposição entre chunks
TIMEOUT_REQUISICAO = 15

# ---------------------------------------------------------------------------
# Constantes para análise de padrões comunicativos
# ---------------------------------------------------------------------------

# Conectivos comuns em português que indicam fala natural
CONECTIVOS_ABERTURA = [
    "então", "bom", "olha", "olha só", "bem", "certo",
    "veja bem", "assim", "pois bem", "ora", "lá vai",
]

CONECTIVOS_TRANSICAO = [
    "aliás", "inclusive", "a propósito", "por falar nisso",
    "digamos", "quer dizer", "ou seja", "isto é", "na verdade",
    "de fato", "aliás", "ademais", "além disso",
]

CONECTIVOS_FECHAMENTO = [
    "resumindo", "em suma", "enfim", "concluindo",
    "é isso", "basicamente", "em poucas palavras", "no fim das contas",
]

EXPRESSOES_ENGAJAMENTO = [
    "certo?", "né?", "tá?", "entende?", "viu?",
    "tudo bem?", "ok?", "beleza?", "faz sentido?",
    "me entende?", "dá pra acompanhar?",
]

CONTRAÇÕES_INFORMAIS = {
    "está": "tá", "estou": "tô", "você": "cê",
    "para": "pra", "não é": "né", "estamos": "tamo",
}

# Padrões de ironia sutil (característicos do Jarvis)
PADROES_IRONIA = [
    r"\bcomo se (não|eu )",
    r"\b(surpreendentemente|curiosamente|estranhamente)\b",
    r"\bparece que\b.*\bnão\b",
    r"\bquem diria\b",
    r"\bironicamente\b",
]

# ---------------------------------------------------------------------------
# Helpers — Log
# ---------------------------------------------------------------------------

def _log(mensagem: str, nivel: str = "INFO") -> None:
    print(f"[WEB-LRN {nivel:<5}] {mensagem}", flush=True)


# ---------------------------------------------------------------------------
# HTML Parser — extração de texto puro
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    """Extrai texto visível de HTML, removendo tags, scripts e estilos."""

    def __init__(self):
        super().__init__()
        self.texto: list[str] = []
        self._skip = False
        self._skip_tags = {"script", "style", "noscript", "head", "nav", "footer"}

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in self._skip_tags:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._skip_tags:
            self._skip = False
        # Adiciona quebra de linha após elementos de bloco
        if tag.lower() in ("p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
            self.texto.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            texto = data.strip()
            if texto:
                self.texto.append(texto + " ")

    def obter_texto(self) -> str:
        raw = "".join(self.texto)
        # Colapsa whitespace
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _extrair_texto_html(html: str) -> str:
    """Converte HTML em texto puro."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    texto = parser.obter_texto()
    # Remove linhas muito curtas (ruído de navegação)
    linhas = [l for l in texto.splitlines() if len(l.strip()) > 20]
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# DuckDuckGo HTML — busca e extração de links
# ---------------------------------------------------------------------------

class _DDGResultParser(HTMLParser):
    """Extrai links e snippets dos resultados do DuckDuckGo HTML."""

    def __init__(self):
        super().__init__()
        self.resultados: list[dict] = []
        self._current: Optional[dict] = None
        self._in_result = False
        self._in_snippet = False
        self._next_is_link = False

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = dict(attrs)

        if tag == "a" and "result__a" in attrs_dict.get("class", ""):
            self._current = {"url": "", "titulo": "", "snippet": ""}
            self._next_is_link = True
            self._in_result = True

        if self._in_result and tag == "a" and self._next_is_link:
            href = attrs_dict.get("href", "")
            if href.startswith("//"):
                href = "https:" + href
            # DuckDuckGo usa l.php?uddg=URL_REAL como intermediário
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            if "uddg" in params:
                href = urllib.parse.unquote(params["uddg"][0])
            self._current["url"] = href
            self._next_is_link = False

        if tag == "a" and "result__snippet" in attrs_dict.get("class", ""):
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_snippet:
            self._in_snippet = False
        if tag == "div" and self._current and self._current.get("url"):
            self.resultados.append(self._current)
            self._current = None
            self._in_result = False

    def handle_data(self, data: str) -> None:
        if self._current and self._next_is_link:
            self._current["titulo"] += data.strip()
        if self._in_snippet and self._current:
            self._current["snippet"] += data.strip()


def _buscar_duckduckgo(query: str, max_resultados: int = MAX_RESULTADOS_BUSCA) -> list[dict]:
    """Pesquisa no DuckDuckGo HTML e retorna lista de {url, titulo, snippet}."""
    params = urllib.parse.urlencode({"q": query})
    url = f"{DUCKDUCKGO_HTML}?{params}"

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_REQUISICAO) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        _log(f"Falha na busca DuckDuckGo: {exc}", "ERROR")
        return []

    parser = _DDGResultParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    resultados = parser.resultados[:max_resultados]
    _log(f"DuckDuckGo retornou {len(resultados)} resultados para '{query[:60]}'")
    return resultados


# ---------------------------------------------------------------------------
# Raspagem de páginas
# ---------------------------------------------------------------------------

def _raspar_pagina(url: str) -> Optional[str]:
    """Baixa e extrai o texto principal de uma página web."""
    _log(f"Raspando: {url[:80]}...", "DEBUG")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_REQUISICAO) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                _log(f"Ignorando tipo de conteúdo: {content_type}", "DEBUG")
                return None
            raw = resp.read(500_000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        _log(f"HTTP {exc.code} em {url[:60]}", "WARNING")
        return None
    except Exception as exc:
        _log(f"Falha ao raspar {url[:60]}: {exc}", "WARNING")
        return None

    return _extrair_texto_html(raw)


# ---------------------------------------------------------------------------
# Chunking (divisão em pedaços)
# ---------------------------------------------------------------------------

def _dividir_em_chunks(
    texto: str,
    tamanho: int = TAMANHO_CHUNK,
    overlap: int = OVERLAP_CHUNK,
) -> list[str]:
    """
    Divide um texto longo em chunks de ~tamanho caracteres,
    com sobreposição entre chunks consecutivos.
    """
    if len(texto) <= tamanho:
        return [texto] if texto.strip() else []

    chunks = []
    inicio = 0
    while inicio < len(texto):
        fim = min(inicio + tamanho, len(texto))
        if fim < len(texto):
            for pontuacao in (". ", "! ", "? ", "\n"):
                idx = texto.rfind(pontuacao, inicio + tamanho // 2, fim)
                if idx != -1:
                    fim = idx + len(pontuacao)
                    break
        chunk = texto[inicio:fim].strip()
        if chunk:
            chunks.append(chunk)
        inicio = fim - overlap if fim < len(texto) else fim

    return chunks


# ---------------------------------------------------------------------------
# Backend de armazenamento — ChromaDB (primário)
# ---------------------------------------------------------------------------

_CHROMA_COLLECTION = "jarvis_memory"
_CHROMA_LINGUISTIC_COLLECTION = "jarvis_linguistic_patterns"


class _ChromaBackend:
    """Backend de busca vetorial usando chromadb."""

    def __init__(self, persist_dir: str):
        self._persist_dir = persist_dir
        self._client = None
        self._collection = None
        self._linguistic_collection = None
        self._inicializado = False
        self._inicializar()

    def _inicializar(self) -> bool:
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=self._persist_dir)
            self._collection = self._client.get_or_create_collection(
                name=_CHROMA_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            # Segunda collection para padrões linguísticos
            self._linguistic_collection = self._client.get_or_create_collection(
                name=_CHROMA_LINGUISTIC_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            self._inicializado = True
            _log("ChromaDB inicializado com sucesso (2 collections).")
            return True
        except Exception as exc:
            _log(f"Falha ao iniciar ChromaDB: {exc}. Usando fallback SQLite.", "WARNING")
            self._inicializado = False
            return False

    @property
    def disponivel(self) -> bool:
        return self._inicializado

    def adicionar(self, chunks: list[str], metadados: dict, collection: str = "memory") -> None:
        if not self._inicializado or not chunks:
            return
        col = self._linguistic_collection if collection == "linguistic" else self._collection
        n = col.count()
        ids = [f"{collection}_{n + i}_{hashlib.md5(c.encode()).hexdigest()[:8]}"
               for i, c in enumerate(chunks)]
        metas = [{**metadados, "chunk_index": i} for i in range(len(chunks))]
        try:
            col.add(documents=chunks, metadatas=metas, ids=ids)
            _log(f"{len(chunks)} chunk(s) indexados no ChromaDB ({collection}).", "INFO")
        except Exception as exc:
            _log(f"Falha ao indexar no ChromaDB: {exc}", "ERROR")

    def consultar(self, query: str, n: int = 3, collection: str = "memory") -> list[dict]:
        if not self._inicializado:
            return []
        col = self._linguistic_collection if collection == "linguistic" else self._collection
        try:
            results = col.query(query_texts=[query], n_results=n)
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances", [[]])[0]

            saida = []
            for i, doc in enumerate(docs):
                item = {"texto": doc}
                if i < len(metas):
                    item["metadados"] = metas[i]
                if i < len(dists):
                    item["distancia"] = round(dists[i], 4)
                saida.append(item)
            return saida
        except Exception as exc:
            _log(f"Falha na consulta ChromaDB: {exc}", "ERROR")
            return []

    def contar(self) -> int:
        if not self._inicializado:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Backend de armazenamento — SQLite (fallback)
# ---------------------------------------------------------------------------

class _SQLiteBackend:
    """Backend de busca por palavras-chave usando SQLite."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._criar_tabelas()

    def _criar_tabelas(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                texto TEXT NOT NULL,
                fonte TEXT,
                topico TEXT,
                data TEXT NOT NULL,
                chunk_index INTEGER DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(texto, fonte, topico, content=memory, content_rowid=id)
        """)
        # Tabela para padrões linguísticos
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS linguistic_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                pattern_value TEXT NOT NULL,
                frequency INTEGER DEFAULT 1,
                source TEXT,
                data TEXT NOT NULL,
                UNIQUE(pattern_type, pattern_value)
            )
        """)
        self._conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory BEGIN
                INSERT INTO memory_fts(rowid, texto, fonte, topico)
                VALUES (new.id, new.texto, new.fonte, new.topico);
            END;
            CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory BEGIN
                INSERT INTO memory_fts(memory_fts, rowid, texto, fonte, topico)
                VALUES ('delete', old.id, old.texto, old.fonte, old.topico);
            END;
        """)
        self._conn.commit()

    @property
    def disponivel(self) -> bool:
        return True

    def adicionar(self, chunks: list[str], metadados: dict, collection: str = "memory") -> None:
        if collection == "linguistic":
            self._adicionar_padroes_linguisticos(chunks, metadados)
            return

        data_str = metadados.get("data", datetime.now(timezone.utc).isoformat())
        fonte = metadados.get("fonte", "")
        topico = metadados.get("topico", "")
        rows = [(c, fonte, topico, data_str, i) for i, c in enumerate(chunks)]
        try:
            self._conn.executemany(
                "INSERT INTO memory (texto, fonte, topico, data, chunk_index) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()
        except Exception as exc:
            _log(f"Falha ao inserir no SQLite: {exc}", "ERROR")

    def _adicionar_padroes_linguisticos(self, patterns: list[str], metadados: dict) -> None:
        """Armazena padrões linguísticos na tabela dedicada."""
        data_str = metadados.get("data", datetime.now(timezone.utc).isoformat())
        source = metadados.get("fonte", "")
        pattern_type = metadados.get("tipo", "desconhecido")

        for p in patterns:
            try:
                self._conn.execute(
                    """INSERT INTO linguistic_patterns
                       (pattern_type, pattern_value, frequency, source, data)
                       VALUES (?, ?, 1, ?, ?)
                       ON CONFLICT(pattern_type, pattern_value)
                       DO UPDATE SET frequency = frequency + 1,
                                     data = excluded.data""",
                    (pattern_type, p.strip(), source, data_str),
                )
            except Exception:
                pass
        self._conn.commit()

    def consultar(self, query: str, n: int = 3, collection: str = "memory") -> list[dict]:
        if collection == "linguistic":
            return self._consultar_padroes(query, n)

        try:
            rows = self._conn.execute(
                """
                SELECT m.texto, m.fonte, m.topico, m.data, m.chunk_index,
                       rank
                FROM memory_fts f
                JOIN memory m ON m.id = f.rowid
                WHERE memory_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, n),
            ).fetchall()

            if not rows:
                like_term = f"%{query}%"
                rows_raw = self._conn.execute(
                    "SELECT texto, fonte, topico, data, chunk_index "
                    "FROM memory WHERE texto LIKE ? OR topico LIKE ? "
                    "LIMIT ?",
                    (like_term, like_term, n),
                ).fetchall()
                return [
                    {
                        "texto": r[0],
                        "metadados": {"fonte": r[1], "topico": r[2], "data": r[3]},
                    }
                    for r in rows_raw
                ]

            return [
                {
                    "texto": r[0],
                    "metadados": {"fonte": r[1], "topico": r[2], "data": r[3]},
                }
                for r in rows
            ]
        except Exception as exc:
            _log(f"Falha na consulta SQLite: {exc}", "ERROR")
            return []

    def _consultar_padroes(self, query: str, n: int = 3) -> list[dict]:
        """Consulta padrões linguísticos."""
        try:
            rows = self._conn.execute(
                """SELECT pattern_type, pattern_value, frequency, source, data
                   FROM linguistic_patterns
                   WHERE pattern_type LIKE ? OR pattern_value LIKE ?
                   ORDER BY frequency DESC
                   LIMIT ?""",
                (f"%{query}%", f"%{query}%", n),
            ).fetchall()
            return [
                {
                    "texto": f"[{r[0]}] {r[1]} (freq: {r[2]})",
                    "metadados": {"tipo": r[0], "fonte": r[3], "data": r[4]},
                }
                for r in rows
            ]
        except Exception:
            return []

    def contar(self) -> int:
        try:
            return self._conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
        except Exception:
            return 0


# ---------------------------------------------------------------------------
# Backend unificado
# ---------------------------------------------------------------------------

def _criar_backend() -> object:
    """Factory: tenta ChromaDB, fallback para SQLite."""
    config = carregar_configuracao()
    data_dir = Path(config.get("data_directory", "data"))
    memory_dir = data_dir / "memory"

    chroma_dir = str(memory_dir / "chromadb")
    backend = _ChromaBackend(chroma_dir)
    if backend.disponivel:
        return backend

    _log("Usando SQLite + FTS5 como backend de memória.", "INFO")
    db_path = str(memory_dir / "jarvis_memory.db")
    return _SQLiteBackend(db_path)


_backend: Optional[object] = None


def _obter_backend() -> object:
    """Singleton do backend de armazenamento."""
    global _backend
    if _backend is None:
        _backend = _criar_backend()
    return _backend


# ═══════════════════════════════════════════════════════════════════════════
# ANÁLISE DE PADRÕES COMUNICATIVOS (NOVO)
# ═══════════════════════════════════════════════════════════════════════════

def _extrair_padroes_comunicativos(texto: str) -> dict:
    """
    Analisa um texto (transcrição/legenda) e extrai padrões comunicativos
    para humanização da fala do J.A.R.V.I.S.

    Retorna um dicionário com os padrões detectados categorizados.
    """
    texto_lower = texto.lower()
    palavras = re.findall(r'\b\w+\b', texto_lower)
    frases = [s.strip() for s in re.split(r'[.!?]+', texto) if s.strip()]

    padroes = {
        "conectivos_abertura": [],
        "conectivos_transicao": [],
        "conectivos_fechamento": [],
        "expressoes_engajamento": [],
        "contracoes_informais": [],
        "padroes_ironia": [],
        "vocabulario_frequente": [],
        "tamanho_medio_frases": 0,
        "idiomas_detectados": [],
    }

    # Detecta conectivos
    for conectivo in CONECTIVOS_ABERTURA:
        pattern = r'\b' + re.escape(conectivo) + r'\b'
        matches = re.findall(pattern, texto_lower)
        if matches:
            padroes["conectivos_abertura"].append(conectivo)

    for conectivo in CONECTIVOS_TRANSICAO:
        pattern = r'\b' + re.escape(conectivo) + r'\b'
        matches = re.findall(pattern, texto_lower)
        if matches:
            padroes["conectivos_transicao"].append(conectivo)

    for conectivo in CONECTIVOS_FECHAMENTO:
        pattern = r'\b' + re.escape(conectivo) + r'\b'
        matches = re.findall(pattern, texto_lower)
        if matches:
            padroes["conectivos_fechamento"].append(conectivo)

    for expr in EXPRESSOES_ENGAJAMENTO:
        pattern = r'\b' + re.escape(expr.replace("?", r"\?")) + r'\b'
        matches = re.findall(pattern, texto_lower)
        if matches:
            padroes["expressoes_engajamento"].append(expr)

    # Detecta contrações
    for formal, informal in CONTRAÇÕES_INFORMAIS.items():
        if informal in palavras:
            padroes["contracoes_informais"].append(informal)

    # Detecta padrões de ironia
    for pattern in PADROES_IRONIA:
        if re.search(pattern, texto_lower):
            padroes["padroes_ironia"].append(pattern)

    # Vocabulário frequente (top 15 palavras significativas)
    stopwords = {
        "de", "a", "o", "que", "e", "do", "da", "em", "um", "para",
        "com", "não", "uma", "os", "no", "se", "na", "por", "mais",
        "as", "dos", "como", "mas", "foi", "ao", "ele", "das", "tem",
        "the", "is", "of", "and", "to", "a", "in", "that", "it",
        "for", "was", "on", "are", "be", "have", "with", "this",
    }
    palavras_filtradas = [p for p in palavras if p not in stopwords and len(p) > 2]
    freq = Counter(palavras_filtradas)
    padroes["vocabulario_frequente"] = [w for w, _ in freq.most_common(15)]

    # Tamanho médio de frases
    if frases:
        tamanhos = [len(f.split()) for f in frases]
        padroes["tamanho_medio_frases"] = round(sum(tamanhos) / len(tamanhos), 1)

    # Detecta idiomas (heurística simples)
    has_pt = bool(re.search(r'\b(de|do|da|que|não|com|para|uma|é|mas)\b', texto_lower))
    has_en = bool(re.search(r'\b(the|is|of|and|that|for|was|are|with|this)\b', texto_lower))
    if has_pt:
        padroes["idiomas_detectados"].append("pt-BR")
    if has_en:
        padroes["idiomas_detectados"].append("en")

    return padroes


# ═══════════════════════════════════════════════════════════════════════════
# PROCESSAMENTO DE VÍDEO (NOVO)
# ═══════════════════════════════════════════════════════════════════════════

def processar_video_para_aprendizado(
    url: Optional[str] = None,
    caminho: Optional[str] = None,
    idioma: str = "pt",
) -> tuple[int, dict]:
    """
    Processa um vídeo (URL do YouTube ou arquivo local) para extrair
    transcrições/legendas e aprender padrões comunicativos.

    Tenta múltiplas estratégias:
      1. YouTube: youtube_transcript_api (se disponível)
      2. YouTube: scraping da página de transcrição
      3. Arquivo local: suporte a arquivos .srt, .vtt, .sbv

    Args:
        url: URL do vídeo (YouTube, Vimeo, etc.)
        caminho: Caminho para arquivo de vídeo ou legenda local
        idioma: Código do idioma preferido (padrão: pt)

    Returns:
        Tupla (num_chunks_armazenados, padroes_detectados).
    """
    transcricao = ""

    # Estratégia 1: URL do YouTube com youtube_transcript_api
    if url and ("youtube.com" in url or "youtu.be" in url):
        transcricao = _extrair_transcricao_youtube(url, idioma)

    # Estratégia 2: URL genérica — tenta buscar legendas associadas
    if not transcricao and url:
        transcricao = _extrair_transcricao_url_generica(url)

    # Estratégia 3: Arquivo local (legenda .srt/.vtt/.sbv)
    if not transcricao and caminho:
        transcricao = _extrair_transcricao_arquivo_local(caminho)

    # Estratégia 4: Se nada funcionou, usa a URL diretamente como fonte de texto
    if not transcricao and url:
        _log("Nenhuma transcrição encontrada. Tentando raspar a página como fallback.", "WARNING")
        texto_pagina = _raspar_pagina(url)
        if texto_pagina:
            transcricao = texto_pagina

    if not transcricao or len(transcricao.strip()) < 50:
        _log("Não foi possível obter transcrição significativa do vídeo.", "ERROR")
        return 0, {}

    _log(f"Transcrição obtida: {len(transcricao)} caracteres.", "INFO")

    # 1. Extrai padrões comunicativos
    padroes = _extrair_padroes_comunicativos(transcricao)
    _log(f"Padrões detectados: {json.dumps({k: v for k, v in padroes.items() if v}, ensure_ascii=False)[:300]}")

    # 2. Divide transcrição em chunks
    chunks = _dividir_em_chunks(transcricao)

    # 3. Armazena na memória com metadados de vídeo
    backend = _obter_backend()
    agora = datetime.now(timezone.utc).isoformat()
    fonte = url or caminho or "video_desconhecido"

    metadados = {
        "fonte": fonte,
        "topico": "aprendizado_video",
        "data": agora,
        "titulo": f"Transcrição de vídeo: {fonte[:100]}",
        "tipo": "transcricao_video",
        "idiomas": ",".join(padroes.get("idiomas_detectados", [])),
    }

    if chunks:
        backend.adicionar(chunks, metadados)
        _log(f"{len(chunks)} chunk(s) da transcrição armazenados.", "INFO")

    # 4. Armazena padrões linguísticos extraídos separadamente
    _armazenar_padroes_linguisticos(padroes, fonte, agora)

    return len(chunks), padroes


def _extrair_transcricao_youtube(url: str, idioma: str = "pt") -> str:
    """Tenta extrair transcrição do YouTube via youtube_transcript_api."""
    try:
        import youtube_transcript_api
        from youtube_transcript_api.formatters import TextFormatter

        # Extrai o video_id
        video_id = None
        if "v=" in url:
            video_id = url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in url:
            video_id = url.split("youtu.be/")[1].split("?")[0]

        if not video_id:
            return ""

        # Tenta idioma preferido primeiro, depois fallback
        transcript = None
        try:
            transcript = youtube_transcript_api.YouTubeTranscriptApi.get_transcript(
                video_id, languages=[idioma, f"{idioma}-BR", "en"]
            )
        except Exception:
            try:
                transcript_list = youtube_transcript_api.YouTubeTranscriptApi.list_transcripts(video_id)
                # Pega a primeira transcrição disponível (manual ou automática)
                for t in transcript_list:
                    transcript = t.fetch()
                    break
            except Exception:
                pass

        if transcript:
            formatter = TextFormatter()
            texto = formatter.format_transcript(transcript)
            _log(f"Transcrição YouTube obtida: {len(texto)} caracteres.", "INFO")
            return texto

    except ImportError:
        _log("youtube_transcript_api não instalado. Tentando método alternativo.", "DEBUG")
    except Exception as exc:
        _log(f"Erro ao extrair transcrição YouTube: {exc}", "DEBUG")

    # Fallback: scraping direto
    return _extrair_transcricao_url_generica(url)


def _extrair_transcricao_url_generica(url: str) -> str:
    """Tenta extrair legendas/transcrição de URL genérica."""
    try:
        # Tenta buscar arquivos .srt/.vtt associados à página
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT_REQUISICAO) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Procura por URLs de legendas no HTML
        caption_patterns = [
            r'"(https?://[^"]*\.(?:srt|vtt|sbv)[^"]*)"',
            r'"(https?://[^"]*caption[^"]*)"',
            r'"(https?://[^"]*transcript[^"]*)"',
            r'"(https?://[^"]*subtitle[^"]*)"',
        ]

        for pattern in caption_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches[:3]:
                try:
                    cap_req = urllib.request.Request(match, headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(cap_req, timeout=10) as cap_resp:
                        caption_text = cap_resp.read().decode("utf-8", errors="replace")
                    texto_limpo = _limpar_texto_legenda(caption_text)
                    if len(texto_limpo) > 100:
                        _log(f"Legenda encontrada via URL: {match[:80]}", "INFO")
                        return texto_limpo
                except Exception:
                    continue

    except Exception as exc:
        _log(f"Falha na extração genérica: {exc}", "DEBUG")

    return ""


def _extrair_transcricao_arquivo_local(caminho: str) -> str:
    """Lê legendas de arquivo local (.srt, .vtt, .sbv)."""
    arquivo = Path(caminho)
    if not arquivo.exists():
        _log(f"Arquivo não encontrado: {caminho}", "WARNING")
        return ""

    try:
        texto = arquivo.read_text(encoding="utf-8", errors="replace")
        texto_limpo = _limpar_texto_legenda(texto)
        if len(texto_limpo) > 50:
            _log(f"Legenda carregada de arquivo local: {len(texto_limpo)} caracteres.", "INFO")
            return texto_limpo
    except Exception as exc:
        _log(f"Erro ao ler arquivo local: {exc}", "ERROR")

    return ""


def _limpar_texto_legenda(texto: str) -> str:
    """
    Remove marcações de tempo e formatação de arquivos .srt/.vtt/.sbv,
    retornando apenas o texto falado.
    """
    # Remove cabeçalhos VTT
    texto = re.sub(r'WEBVTT.*?\n\n', '', texto, flags=re.DOTALL | re.IGNORECASE)

    # Remove timestamps: 00:00:00,000 --> 00:00:05,000
    texto = re.sub(r'\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}', '', texto)

    # Remove números de sequência isolados (1, 2, 3...)
    texto = re.sub(r'^\d+\s*$', '', texto, flags=re.MULTILINE)

    # Remove tags HTML/VTT como <c> </c> <00:00:00> <v Nome>
    texto = re.sub(r'<[^>]+>', '', texto)

    # Remove linhas de estilo VTT (::cue)
    texto = re.sub(r'^::.*$', '', texto, flags=re.MULTILINE)

    # Remove coordenadas de posicionamento
    texto = re.sub(r'(align|position|size|line):[^\n]*', '', texto)

    # Remove linhas em branco múltiplas
    texto = re.sub(r'\n\s*\n', '\n', texto)

    # Junta linhas fragmentadas típicas de legendas
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    return " ".join(linhas)


def _armazenar_padroes_linguisticos(padroes: dict, fonte: str, data_str: str) -> None:
    """Armazena padrões linguísticos extraídos no banco vetorial."""
    backend = _obter_backend()
    total = 0

    categorias = [
        ("conectivos_abertura", "abertura"),
        ("conectivos_transicao", "transicao"),
        ("conectivos_fechamento", "fechamento"),
        ("expressoes_engajamento", "engajamento"),
        ("contracoes_informais", "contracao"),
        ("padroes_ironia", "ironia"),
        ("vocabulario_frequente", "vocabulario"),
    ]

    for campo, tipo in categorias:
        valores = padroes.get(campo, [])
        if valores:
            meta = {
                "fonte": fonte,
                "data": data_str,
                "tipo": tipo,
                "categoria": "padrao_linguistico",
            }
            backend.adicionar(valores, meta, collection="linguistic")
            total += len(valores)

    if total > 0:
        _log(f"{total} padrões linguísticos armazenados no banco.", "INFO")


# ═══════════════════════════════════════════════════════════════════════════
# ANÁLISE DE PADRÕES COMUNICATIVOS (API PÚBLICA)
# ═══════════════════════════════════════════════════════════════════════════

def analisar_padroes_comunicativos(texto: str) -> dict:
    """
    Analisa um texto e retorna os padrões comunicativos detectados.

    Útil para analisar transcrições de diálogos, entrevistas,
    vídeos ou qualquer conteúdo textual para adaptação da fala.

    Args:
        texto: Texto a ser analisado (transcrição, legenda, etc.)

    Returns:
        Dicionário com padrões categorizados e estatísticas.
    """
    if not texto or len(texto.strip()) < 50:
        return {"erro": "Texto muito curto para análise significativa."}

    padroes = _extrair_padroes_comunicativos(texto)

    # Adiciona estatísticas descritivas
    palavras = re.findall(r'\b\w+\b', texto.lower())
    frases = [s.strip() for s in re.split(r'[.!?]+', texto) if s.strip()]

    padroes["estatisticas"] = {
        "total_palavras": len(palavras),
        "total_frases": len(frases),
        "tamanho_medio_frases": padroes.pop("tamanho_medio_frases", 0),
        "densidade_conectivos": round(
            sum(1 for p in palavras if p in CONECTIVOS_ABERTURA + CONECTIVOS_TRANSICAO + CONECTIVOS_FECHAMENTO)
            / max(1, len(palavras)) * 100, 1
        ),
    }

    return padroes


def obter_padroes_aprendidos(tipo: Optional[str] = None, limite: int = 20) -> list[dict]:
    """
    Recupera padrões linguísticos aprendidos do banco de memória.

    Args:
        tipo: Filtrar por tipo (abertura, transicao, fechamento, etc.)
              None retorna todos.
        limite: Número máximo de resultados.

    Returns:
        Lista de padrões com frequência.
    """
    backend = _obter_backend()
    query = tipo if tipo else "padrao"
    return backend.consultar(query, n=limite, collection="linguistic")


# ═══════════════════════════════════════════════════════════════════════════
# API pública (original mantida + expandida)
# ═══════════════════════════════════════════════════════════════════════════

def pesquisar_e_aprender(
    topico: str,
    max_paginas: int = MAX_PAGINAS_RASPAR,
) -> int:
    """
    Pesquisa um tópico na web (DuckDuckGo), raspa o conteúdo das páginas
    encontradas, divide em chunks e salva no banco de memória.

    Args:
        topico: Termo de busca / assunto a pesquisar.
        max_paginas: Número máximo de páginas a raspar.

    Returns:
        Número total de chunks armazenados.
    """
    _log(f"Iniciando pesquisa e aprendizado sobre: '{topico}'")

    # 1. Busca DuckDuckGo
    resultados = _buscar_duckduckgo(topico)
    if not resultados:
        _log("Nenhum resultado encontrado na web.", "WARNING")
        return 0

    # 2. Raspa as páginas
    paginas_raspadas = 0
    total_chunks = 0
    backend = _obter_backend()
    agora = datetime.now(timezone.utc).isoformat()

    for res in resultados:
        if paginas_raspadas >= max_paginas:
            break

        url = res.get("url", "")
        if not url or not url.startswith("http"):
            continue

        texto = _raspar_pagina(url)
        if not texto or len(texto) < 50:
            continue

        paginas_raspadas += 1

        # 3. Divide em chunks
        chunks = _dividir_em_chunks(texto)
        if not chunks:
            continue

        # 4. Salva no backend
        metadados = {
            "fonte": url,
            "topico": topico,
            "data": agora,
            "titulo": res.get("titulo", ""),
        }
        backend.adicionar(chunks, metadados)
        total_chunks += len(chunks)

        # Pausa educada entre requisições
        time.sleep(0.5)

    _log(
        f"Aprendizado concluído: {paginas_raspadas} página(s) raspadas, "
        f"{total_chunks} chunk(s) armazenados."
    )
    return total_chunks


def consultar_memoria(query: str, n_resultados: int = 3) -> list[dict]:
    """
    Consulta a memória aprendida por textos semanticamente similares à query.

    Args:
        query: Pergunta ou termo de busca.
        n_resultados: Número máximo de resultados.

    Returns:
        Lista de dicionários [{texto, metadados: {fonte, topico, data}}, ...].
    """
    _log(f"Consultando memória: '{query[:80]}'")
    backend = _obter_backend()
    resultados = backend.consultar(query, n_resultados)

    if not resultados:
        _log("Nenhum resultado encontrado na memória.", "INFO")
    else:
        _log(f"{len(resultados)} resultado(s) encontrados.", "INFO")

    return resultados


def estatisticas_memoria() -> dict:
    """Retorna estatísticas do banco de memória."""
    backend = _obter_backend()
    return {
        "total_chunks": backend.contar(),
        "backend": type(backend).__name__,
    }


# ═══════════════════════════════════════════════════════════════════════════
# WHISPER LOCAL — Transcrição de áudio/vídeo com faster-whisper
# ═══════════════════════════════════════════════════════════════════════════

_whisper_model = None
"""Cache do modelo Whisper carregado."""


def _obter_modelo_whisper(model_size: str = "base"):
    """Carrega e cacheia o modelo faster-whisper sob demanda."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    try:
        from faster_whisper import WhisperModel
        _log(f"Carregando modelo faster-whisper '{model_size}'...", "INFO")
        _whisper_model = WhisperModel(
            model_size, device="cpu", compute_type="int8")
        _log("Modelo Whisper carregado com sucesso.", "INFO")
        return _whisper_model
    except ImportError:
        _log("faster-whisper não instalado. Use: pip install faster-whisper", "ERROR")
        return None
    except Exception as exc:
        _log(f"Falha ao carregar Whisper: {exc}", "ERROR")
        return None


def transcrever_audio_whisper(
    audio_path: str,
    model_size: str = "base",
    idioma: str = "pt",
) -> str:
    """
    Transcreve um arquivo de áudio/vídeo usando faster-whisper local.

    Suporta formatos: .wav, .mp3, .mp4, .ogg, .flac, .m4a, .webm, etc.

    Args:
        audio_path: Caminho para o arquivo de áudio/vídeo.
        model_size: Tamanho do modelo ('tiny', 'base', 'small', 'medium', 'large-v2').
        idioma: Código do idioma (None = auto-detecção).

    Returns:
        Texto transcrito, ou string vazia em caso de falha.
    """
    if not os.path.isfile(audio_path):
        _log(f"Arquivo não encontrado: {audio_path}", "ERROR")
        return ""

    model = _obter_modelo_whisper(model_size)
    if model is None:
        return ""

    _log(f"Transcrevendo: {audio_path} (modelo={model_size}, idioma={idioma})", "INFO")

    try:
        segments, info = model.transcribe(
            audio_path,
            language=idioma if idioma else None,
            beam_size=5,
            vad_filter=True,
        )

        texto = " ".join(segment.text for segment in segments).strip()

        _log(
            f"Transcrição concluída: {len(texto)} caracteres, "
            f"idioma detectado={info.language} (prob={info.language_probability:.2f})",
            "INFO",
        )
        return texto

    except Exception as exc:
        _log(f"Erro na transcrição Whisper: {exc}", "ERROR")
        return ""


def baixar_audio_youtube(url: str, output_dir: str = ".") -> str | None:
    """
    Baixa o áudio de um vídeo do YouTube usando yt-dlp.

    Args:
        url: URL do vídeo do YouTube.
        output_dir: Diretório de destino para o áudio.

    Returns:
        Caminho do arquivo de áudio baixado (.mp3), ou None em caso de falha.
    """
    try:
        import yt_dlp
    except ImportError:
        _log("yt-dlp não instalado. Use: pip install yt-dlp", "ERROR")
        return None

    os.makedirs(output_dir, exist_ok=True)
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "quiet": True,
        "no_warnings": True,
    }

    _log(f"Baixando áudio do YouTube: {url[:80]}...", "INFO")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "audio")
            # yt-dlp renomeia para .mp3 após o post-processing
            filename = os.path.join(output_dir, f"{title}.mp3")
            # Sanitiza nome do arquivo
            safe_title = "".join(
                c for c in title if c.isalnum() or c in " _-").strip()
            filename_safe = os.path.join(output_dir, f"{safe_title}.mp3")

            if os.path.isfile(filename_safe):
                _log(f"Áudio baixado: {filename_safe}", "INFO")
                return filename_safe
            elif os.path.isfile(filename):
                _log(f"Áudio baixado: {filename}", "INFO")
                return filename

            # Tenta encontrar qualquer .mp3 no diretório
            for f in os.listdir(output_dir):
                if f.endswith(".mp3"):
                    found = os.path.join(output_dir, f)
                    _log(f"Áudio encontrado: {found}", "INFO")
                    return found

            _log("Áudio baixado mas arquivo .mp3 não localizado.", "WARNING")
            return None

    except Exception as exc:
        _log(f"Falha ao baixar áudio do YouTube: {exc}", "ERROR")
        return None


def processar_video_com_whisper(
    url: str | None = None,
    caminho: str | None = None,
    model_size: str = "base",
    idioma: str = "pt",
) -> tuple[int, dict]:
    """
    Pipeline completo: download (se URL) → transcrição Whisper → chunking → ChromaDB.

    Args:
        url: URL do YouTube (opcional).
        caminho: Caminho para arquivo de áudio/vídeo local (opcional).
        model_size: Tamanho do modelo Whisper.
        idioma: Código do idioma.

    Returns:
        Tupla (num_chunks_armazenados, padroes_detectados).
    """
    audio_path = None
    temp_dir = None

    try:
        if url and ("youtube.com" in url or "youtu.be" in url):
            # Cria diretório temporário para o download
            config = carregar_configuracao()
            data_dir = config.get("data_directory", "data")
            temp_dir = os.path.join(data_dir, "downloads", "whisper_temp")
            audio_path = baixar_audio_youtube(url, temp_dir)
        elif caminho:
            audio_path = caminho

        if not audio_path or not os.path.isfile(audio_path):
            _log("Nenhum arquivo de áudio disponível para transcrição.", "ERROR")
            return 0, {}

        # Transcrição
        transcricao = transcrever_audio_whisper(audio_path, model_size, idioma)
        if not transcricao or len(transcricao.strip()) < 50:
            _log("Transcrição muito curta ou vazia.", "WARNING")
            return 0, {}

        # Padrões comunicativos
        padroes = _extrair_padroes_comunicativos(transcricao)

        # Chunking e armazenamento
        chunks = _dividir_em_chunks(transcricao)
        backend = _obter_backend()
        agora = datetime.now(timezone.utc).isoformat()
        fonte = url or caminho or "whisper_transcricao"

        metadados = {
            "fonte": fonte,
            "topico": "transcricao_whisper",
            "data": agora,
            "titulo": f"Transcrição Whisper: {fonte[:100]}",
            "tipo": "transcricao_audio",
            "idiomas": ",".join(padroes.get("idiomas_detectados", [])),
        }

        if chunks:
            backend.adicionar(chunks, metadados)
            _log(f"{len(chunks)} chunk(s) da transcrição armazenados.", "INFO")

        # Padrões linguísticos
        _armazenar_padroes_linguisticos(padroes, fonte, agora)

        # Limpeza: remove arquivo temporário
        if temp_dir and audio_path and audio_path.startswith(temp_dir):
            try:
                os.remove(audio_path)
            except OSError:
                pass

        return len(chunks), padroes

    except Exception as exc:
        _log(f"Erro no pipeline Whisper: {exc}", "ERROR")
        return 0, {}


# ---------------------------------------------------------------------------
# Teste direto
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S — Teste do Web Learner v2.0 (RAG + Video)")
    print("=" * 60)

    # 1. Teste de análise de padrões comunicativos
    print("\n[1] Testando análise de padrões comunicativos...")
    texto_teste = (
        "Então, olha só, eu tava pensando aqui... será que a gente consegue "
        "fazer isso de um jeito mais simples? Tipo, basicamente é só seguir "
        "o fluxo, né? Aliás, inclusive, tem um detalhe importante que eu "
        "esqueci de mencionar. Resumindo: é isso aí, beleza? Curiosamente, "
        "parece que o óbvio nem sempre é tão óbvio assim."
    )
    padroes = analisar_padroes_comunicativos(texto_teste)
    print(f"    Padrões detectados:")
    for k, v in padroes.items():
        if v:
            print(f"      {k}: {v}")

    # 2. Teste de processamento de vídeo (URL opcional)
    print("\n[2] Testando processamento de vídeo...")
    print("    (forneça uma URL de vídeo ou pressione Enter para pular)")
    url_video = input("    URL do vídeo (YouTube): ").strip()
    if url_video:
        n_chunks, padroes_video = processar_video_para_aprendizado(url=url_video)
        print(f"    -> {n_chunks} chunk(s) armazenados.")
        if padroes_video:
            print(f"    -> {len(padroes_video)} categorias de padrões detectadas.")
    else:
        print("    Pulando teste de vídeo.")

    # 3. Pesquisa web
    print("\n[3] Testando pesquisa web...")
    topico_teste = "Python programming language"
    print(f"    Pesquisando: '{topico_teste}'")
    chunks = pesquisar_e_aprender(topico_teste, max_paginas=2)
    print(f"    -> {chunks} chunk(s) armazenados.")

    # 4. Estatísticas
    stats = estatisticas_memoria()
    print(f"\n[4] Estatísticas da memória: {json.dumps(stats)}")

    # 5. Consultar padrões aprendidos
    print("\n[5] Consultando padrões linguísticos aprendidos...")
    padroes_aprendidos = obter_padroes_aprendidos(limite=5)
    for p in padroes_aprendidos:
        print(f"    {p.get('texto', p.get('metadados', {}).get('tipo', '?'))[:120]}")

    print("\n[WEB-LRN] Teste concluído.")
