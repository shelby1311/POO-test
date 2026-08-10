"""
speech_normalizer.py — J.A.R.V.I.S. Natural Speech Pre-Processor v1.0

Transforma texto escrito em texto otimizado para síntese de voz natural.
Aplica normalização fonética, substituição de siglas, formatação SSML
e remoção de caracteres que causam pausas mecânicas no TTS.

Técnicas aplicadas:
  1. Dicionário de pronúncia (Regex) — siglas, termos técnicos, pontuação
  2. Formatação SSML — prosody, phoneme, break para controle de entonação
  3. Adaptação de output de LLM — remove marcadores que travam a leitura
"""

import re
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════════
# DICIONÁRIO DE PRONÚNCIA FONÉTICA
# ═══════════════════════════════════════════════════════════════════════════

PHONETIC_DICTIONARY: dict[str, str] = {
    # Siglas e acrônimos comuns — soletração → pronúncia fluida
    r'\bJ\.\s*A\.\s*R\.\s*V\.\s*I\.\s*S\.?\b': 'Járvis',
    r'\bJARVIS\b': 'Járvis',
    r'\bAI\b': 'I A',
    r'\bIA\b': 'I A',
    r'\bOK\b': 'Oquêi',
    r'\bCPU\b': 'Cê Pê U',
    r'\bGPU\b': 'Gê Pê U',
    r'\bRAM\b': 'Rãm',
    r'\bSSD\b': 'Ésse Ésse Dê',
    r'\bHDD\b': 'Agá Dê Dê',
    r'\bUSB\b': 'U Ésse Bê',
    r'\bHTTP\b': 'Agá Tê Tê Pê',
    r'\bHTTPS\b': 'Agá Tê Tê Pê Ésse',
    r'\bAPI\b': 'A Pê I',
    r'\bJSON\b': 'Jêison',
    r'\bSQL\b': 'Ésse Quê Éle',
    r'\bHTML\b': 'Agá Tê Éme Éle',
    r'\bCSS\b': 'Cê Ésse Ésse',
    r'\bJS\b': 'Jáva Script',
    r'\bDNS\b': 'Dê Éne Ésse',
    r'\bIP\b': 'I Pê',
    r'\bTCP\b': 'Tê Cê Pê',
    r'\bUDP\b': 'U Dê Pê',
    r'\bVPN\b': 'Vê Pê Éne',
    r'\bURL\b': 'U Érre Éle',
    r'\bXML\b': 'Xis Éme Éle',
    r'\bCSV\b': 'Cê Ésse Vê',
    r'\bPDF\b': 'Pê Dê Éfe',
    r'\bRCE\b': 'Érre Cê E',
    r'\bCVE\b': 'Cê Vê E',
    r'\bCWE\b': 'Cê Dabliú E',
    r'\bOWASP\b': 'Óuasp',
    r'\bSSH\b': 'Ésse Ésse Agá',
    r'\bFTP\b': 'Éfe Tê Pê',
    r'\bSMB\b': 'Ésse Éme Bê',
    r'\bLDAP\b': 'Éle Dáp',
    r'\bNFS\b': 'Éne Éfe Ésse',
    r'\bRDP\b': 'Érre Dê Pê',
    r'\bWMI\b': 'Dabliú Éme I',
    r'\bOSINT\b': 'Óssint',
    r'\bMITM\b': 'Míteme',
    r'\bXSS\b': 'Xis Ésse Ésse',
    r'\bSSRF\b': 'Ésse Ésse Érre Éfe',
    r'\bSQLi\b': 'Ésse Quê Éle Injéction',

    # Termos técnicos
    r'\bOllama\b': 'Olâma',
    r'\bPySide\b': 'Pí Saide',
    r'\bPyTorch\b': 'Pí Tórtch',
    r'\bchromadb\b': 'Crôma Dê Bê',

    # Contrações e fluência
    r'\bsenhor\b': 'senhôr',
    r'\bDoutor\b': 'Doutôr',
    r'\bobrigado\b': 'obrigádo',
}

# ═══════════════════════════════════════════════════════════════════════════
# PADRÕES DE LIMPEZA DE TEXTO
# ═══════════════════════════════════════════════════════════════════════════

# Caracteres que causam pausas mecânicas no TTS
MECHANICAL_PUNCTUATION = [
    (r'[-_]{2,}', ' ... '),           # travessões longos → pausa
    (r'\*{1,2}([^*]+)\*{1,2}', r'\1'), # remove **negrito** e *itálico*
    (r'`{1,3}[^`]+`{1,3}', ' código '),# substitui `code` por "código"
    (r'\[([^\]]+)\]\([^)]+\)', r'\1'),  # links markdown → só texto
    (r'#{1,6}\s+', ''),                 # remove headers markdown
    (r'^\s*[-*+]\s+', ''),              # remove bullets de lista
    (r'^\s*\d+[.)]\s+', ''),            # remove números de lista
    (r'[<>]', ' '),                      # remove brackets HTML/XML
    (r'[{}]', ' '),                      # remove chaves
    (r'[\[\]]', ' '),                    # remove colchetes
]

# ═══════════════════════════════════════════════════════════════════════════
# NORMALIZADOR PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════

def normalize_for_speech(
    text: str,
    use_phonetics: bool = True,
    voice_style: str = "jarvis",
) -> str:
    """
    Prepara texto para síntese de voz natural.

    Args:
        text: Texto original (do LLM).
        use_phonetics: Aplica dicionário fonético.
        voice_style: 'jarvis' (formal, grave), 'natural' (neutro), 'casual'.

    Returns:
        Texto normalizado pronto para TTS.
    """
    if not text:
        return ""

    result = text.strip()

    # ── 1. Remove marcações de código ──
    result = re.sub(r'```[\s\S]*?```', ' [código omitido] ', result)
    result = re.sub(r'`([^`]+)`', r' \1 ', result)

    # ── 2. Remove pontuação mecânica ──
    for pattern, replacement in MECHANICAL_PUNCTUATION:
        result = re.sub(pattern, replacement, result, flags=re.MULTILINE)

    # ── 3. Remove parênteses e conteúdo (opcional) ──
    result = re.sub(r'\([^)]*\)', '', result)

    # ── 4. Normaliza siglas e termos ──
    if use_phonetics:
        for pattern, replacement in PHONETIC_DICTIONARY.items():
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    # ── 5. Substitui caracteres problemáticos ──
    result = result.replace('"', '')
    result = result.replace("'", '')
    result = result.replace('&', ' e ')
    result = result.replace('%', ' por cento ')
    result = result.replace('@', ' arroba ')
    result = result.replace('#', ' ')

    # ── 6. Normaliza pontuação para pausas naturais ──
    result = re.sub(r'[.]{3,}', '... ', result)     # reticências
    result = re.sub(r'[!]{2,}', '! ', result)        # múltiplas exclamações
    result = re.sub(r'[?]{2,}', '? ', result)        # múltiplas interrogações
    result = re.sub(r'\s+', ' ', result)              # colapsa whitespace

    # ── 7. Ajustes por estilo ──
    if voice_style == "jarvis":
        # Tom mais formal e pausado
        result = result.replace('. ', '. ... ')
        result = result.replace('? ', '? ... ')
        result = result.replace(': ', ': ... ')

    result = result.strip()

    return result


def to_ssml(
    text: str,
    voice_name: str = "pt-BR-AntonioNeural",
    rate: str = "medium",
    pitch: str = "-3st",
    volume: str = "medium",
) -> str:
    """
    Converte texto normalizado para SSML (Speech Synthesis Markup Language).

    Compatível com: Azure Speech, Google Cloud TTS, Amazon Polly, Edge-TTS.

    Args:
        text: Texto já normalizado.
        voice_name: Nome da voz neural.
        rate: Velocidade (x-slow, slow, medium, fast, x-fast).
        pitch: Tom relativo (-5st a +5st).
        volume: Volume (silent, x-soft, soft, medium, loud, x-loud).

    Returns:
        String SSML formatada.
    """
    # Primeiro normaliza
    normalized = normalize_for_speech(text)

    # Aplica SSML para controle fino
    ssml = (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="pt-BR">\n'
        f'  <voice name="{voice_name}">\n'
        f'    <prosody rate="{rate}" pitch="{pitch}" volume="{volume}">\n'
        f'      {normalized}\n'
        f'    </prosody>\n'
        f'  </voice>\n'
        f'</speak>'
    )
    return ssml


def apply_phoneme(text: str, word: str, ipa_pronunciation: str) -> str:
    """
    Força a pronúncia fonética de uma palavra específica usando IPA.

    Args:
        text: Texto contendo a palavra.
        word: Palavra a ser substituída.
        ipa_pronunciation: Pronúncia em IPA (International Phonetic Alphabet).

    Returns:
        Texto com tag <phoneme> SSML.

    Exemplo:
        apply_phoneme("JARVIS online", "JARVIS", "ˈdʒɑːrvɪs")
        → '<phoneme alphabet="ipa" ph="ˈdʒɑːrvɪs">JARVIS</phoneme> online'
    """
    return text.replace(
        word,
        f'<phoneme alphabet="ipa" ph="{ipa_pronunciation}">{word}</phoneme>',
    )


# ═══════════════════════════════════════════════════════════════════════════
# FILTRO DE RESPOSTA DO LLM (pré-TTS)
# ═══════════════════════════════════════════════════════════════════════════

LLM_OUTPUT_FILTERS = [
    # Remove blocos de código
    (r'```[\s\S]*?```', ' [trecho de código] '),
    # Remove emojis
    (r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
     r'\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF'
     r'\U00002702-\U000027B0\U000024C2-\U0001F251'
     r'✅❌⚠️🔴🟡🟢💻🔍📊🛡️🎯🏗️🔧📋📝📐📦💡⛔]',
     ''),
    # Remove tabelas markdown
    (r'\|[^\n]*\|', ''),
    # Remove linhas de separação
    (r'^[-=]{3,}$', '', re.MULTILINE),
    # Junta linhas fragmentadas em parágrafo único
    (r'\n{2,}', '. '),
    (r'\n', ' '),
]


def filter_llm_output(text: str) -> str:
    """
    Filtra saída do LLM removendo elementos que prejudicam a leitura por TTS.

    Remove: blocos de código, emojis, tabelas, separadores,
    e converte quebras de linha em fluxo de parágrafo.
    """
    result = text
    for pattern, replacement, *flags in LLM_OUTPUT_FILTERS:
        flag = flags[0] if flags else 0
        result = re.sub(pattern, replacement, result, flags=flag)

    # Colapsa espaços múltiplos
    result = re.sub(r'\s+', ' ', result)
    result = re.sub(r'\.\s*\.', '. ', result)

    return result.strip()


def full_pipeline(text: str, style: str = "jarvis") -> str:
    """
    Pipeline completo: filtra saída do LLM → normaliza fonética → SSML.

    Args:
        text: Texto bruto da resposta do LLM.
        style: 'jarvis', 'natural', ou 'casual'.

    Returns:
        Texto pronto para o melhor TTS disponível.
    """
    # 1. Filtra elementos visuais/markdown
    clean = filter_llm_output(text)

    # 2. Normaliza para fala natural
    speech_ready = normalize_for_speech(clean, voice_style=style)

    return speech_ready


# ═══════════════════════════════════════════════════════════════════════════
# Teste
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S. Speech Normalizer — Teste")
    print("=" * 60)

    # Texto de exemplo (saída típica do LLM)
    raw_text = (
        "✅ **J.A.R.V.I.S. online**, senhor.\n\n"
        "```python\nprint('hello')\n```\n\n"
        "A CPU está em 45% e a GPU em 60%.\n"
        "O scan de RCE via HTTP revelou uma CVE-2021-41773.\n"
        "A API está respondendo em JSON no endpoint /api/v1.\n\n"
        "🔴 CRITICAL: Corrigir **SQL Injection** imediatamente.\n"
        "🟡 MEDIUM: Atualizar o DNS para HTTPS.\n"
    )

    print("\n[1] Texto original:")
    print(f"    {raw_text[:200]}...")

    print("\n[2] Após filter_llm_output():")
    filtered = filter_llm_output(raw_text)
    print(f"    {filtered[:300]}")

    print("\n[3] Após normalize_for_speech():")
    normalized = normalize_for_speech(filtered)
    print(f"    {normalized[:300]}")

    print("\n[4] SSML gerado:")
    ssml = to_ssml(normalized, pitch="-3st")
    print(f"    {ssml[:300]}...")

    print("\n[5] Pipeline completo:")
    ready = full_pipeline(raw_text)
    print(f"    {ready[:300]}")

    print("\n[SPEECH-NORM] Teste concluído.")
