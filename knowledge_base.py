"""
knowledge_base.py — Motor de Base de Conhecimento Local do J.A.R.V.I.S.

Implementa um mecanismo simples de RAG (Retrieval-Augmented Generation) local:
  - Gerencia arquivos de texto em `data/knowledge_base/`.
  - Cria automaticamente o guia de cibersegurança "Mr. Robot" caso não exista.
  - Busca trechos relevantes por palavras-chave/relevância para injetar no
    System Prompt do modelo (Llama 3.2 via brain.py).

Dependências: nenhuma além da biblioteca padrão.
"""

import datetime
import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent
KNOWLEDGE_BASE_DIR = _SCRIPT_DIR / "data" / "knowledge_base"

MR_ROBOT_GUIDE_FILENAME = "mr_robot_cybersecurity_guide.txt"
ERROR_LEARNINGS_FILENAME = "error_learnings.json"

# Palavras irrelevantes (stopwords PT/EN) removidas da busca.
_STOPWORDS = frozenset({
    "a", "o", "e", "de", "do", "da", "em", "no", "na", "para", "com", "um",
    "uma", "os", "as", "que", "por", "como", "sobre", "se", "eu", "meu",
    "the", "of", "and", "to", "in", "for", "is", "are", "what", "how",
    "whats", "what's", "a", "an", "on", "at", "with", "my", "me",
})

# ---------------------------------------------------------------------------
# Conteúdo do Guia Mr. Robot (criado automaticamente na primeira execução)
# ---------------------------------------------------------------------------

MR_ROBOT_GUIDE_CONTENT = """\
============================================================
J.A.R.V.I.S. — GUIA DE CIBERSEGURANÇA (MR. ROBOT)
Base de Conhecimento Local — RAG
============================================================

AVISO LEGAL: Este material é exclusivamente EDUCACIONAL, para uso ÉTICO em
ambientes AUTORIZADOS e laboratórios próprios (CTF, homelab, pentest
contratado). O objetivo é ensinar DEFESA, DETECÇÃO, DIAGNÓSTICO e HARDENING.

## NMAP — Network Mapper
Ferramenta de varredura/descoberta de rede e enumeração de portas e serviços.
- Teoria: envia pacotes (TCP SYN, UDP, ICMP) e analisa respostas para mapear
  hosts ativos, portas abertas, serviços, versões e sistema operacional.
- Uso defensivo: inventário de ativos, auditoria da superfície de exposição,
  validação de regras de firewall e detecção de serviços desatualizados.
- Detecção: varreduras geram muitas conexões SYN a várias portas em pouco
  tempo — identificáveis por IDS (Snort/Suricata) e logs de firewall.
- Comandos de diagnóstico (uso autorizado):
    nmap -sS -sV -O -T4 <alvo>     # scan SYN + versão + SO
    nmap -sn <rede>/24             # descoberta de hosts (ping sweep)
    nmap -sC -sV -p- <alvo>        # scripts padrão + todas as portas
- Hardening: reduza serviços expostos, feche portas desnecessárias, use
  allowlist de IP e segmente a rede.

## METASPLOIT FRAMEWORK
Plataforma de desenvolvimento/execução de exploits e testes de penetração.
- Teoria: módulos (exploit, payload, auxiliary, post) automatizam exploração,
  geração de payloads e pós-exploração, com banco de assinaturas (CVE).
- Uso defensivo: validar se sistemas estão vulneráveis a CVEs conhecidas,
  testar a detecção do SOC e gerar evidências objetivas de risco.
- Comandos (uso autorizado):
    msfconsole
    search cve:2021 type:exploit
    use auxiliary/scanner/portscan/tcp
    use exploit/multi/handler        # listener para callback
- Hardening: gestão de patches, segmentação, EDR, monitoramento de tráfego
  de saída e restrição de execução de binários.

## AIRCRACK-NG
Suíte para auditoria de redes Wi-Fi (WEP/WPA/WPA2).
- Teoria: captura de pacotes 802.11 em modo monitor, obtenção do handshake
  e ataque de dicionário/força bruta contra a senha (PSK).
- Uso defensivo: auditar a robustez da senha do próprio Wi-Fi e detectar
  tentativas de desautenticação (deauth).
- Comandos (uso autorizado, apenas em rede própria):
    airmon-ng start wlan0
    airodump-ng wlan0mon
    aircrack-ng -w wordlist.txt captura.cap
- Hardening: use WPA2/WPA3 com senha longa, desabilite WPS, isole a rede de
  convidados e monitore frames de deauth.

## MIMIKATZ
Ferramenta de pós-exploração para extração de credenciais em memória (Windows).
- Teoria: lê LSASS, SAM, tickets Kerberos e senhas em texto claro/reversíveis
  para demonstrar roubo de credenciais.
- Uso defensivo: demonstrar o impacto de credenciais em cache e validar
  controles como Credential Guard e LSA Protection.
- Comandos (uso autorizado, em laboratório):
    sekurlsa::logonpasswords
    lsadump::sam
    sekurlsa::pth                 # pass-the-hash (demonstração)
- Hardening: habilite Windows Defender Credential Guard, LSA Protection
  (RunAsPPL), use MFA, separe contas privilegiadas e limpe caches.

## CAN-UTILS
Ferramentas para interagir com barramento CAN (automotivo/industrial).
- Teoria: envia/escuta frames CAN para diagnóstico e auditoria de sistemas
  embarcados, veículos e ICS.
- Uso defensivo: auditoria de segurança veicular e detecção de mensagens
  anômalas no barramento.
- Comandos (uso autorizado):
    candump can0
    cansend can0 <id>#<dados>
    ip link set can0 up type can bitrate 500000
- Hardening: segmente o barramento, autentique ECUs, valide IDs/mensagens e
  monitore tráfego CAN anômalo.

## STEGHIDE
Esteganografia — ocultação de dados dentro de imagens/áudio.
- Teoria: esconde payloads ou mensagens em arquivos de mídia sem alterar
  perceptivelmente o conteúdo (técnicas como LSB).
- Uso defensivo: detectar exfiltração de dados por canais encobertos e
  analisar arquivos suspeitos.
- Comandos (uso autorizado):
    steghide embed -cf capa.jpg -ef segredo.txt -p senha
    steghide extract -sf capa.jpg -p senha
    steghide info capa.jpg
- Hardening: DLP, inspeção de tráfego, monitoramento de saída e análise
  forense de arquivos.

## SHRED
Destruição segura de arquivos (sobrescrita múltipla).
- Teoria: sobrescreve o conteúdo várias vezes para impedir recuperação
  forense em mídia magnética (menos eficaz em SSD/TRIM).
- Uso defensivo: descarte seguro de dados sensíveis e higienização de mídia.
- Comandos:
    shred -z -n 3 arquivo.txt
    shred -v -z -n 1 /dev/sdX     # cuidado: destrutivo e irreversível
- Hardening: criptografia de disco (LUKS/BitLocker) e sanitização certificada
  ou destruição física para mídias.

## WIRESHARK / TSHARK
Análise de tráfego de rede (sniffer e análise de pacotes).
- Uso defensivo: investigação de incidentes, análise de protocolos e detecção
  de anomalias de tráfego.
- Comandos:
    tshark -i eth0 -Y "tcp.port == 443"
    tshark -r captura.pcapng -Y "http.request"

## HYDRA / JOHN THE RIPPER
Hydra: força bruta online de serviços (SSH, HTTP, FTP).
John: quebra de hashes offline.
- Uso defensivo: auditar a política de senhas e identificar hashes fracos.
- Hardening: MFA, lockout, senhas fortes e hashing moderno (bcrypt/argon2).

## BURP SUITE / SQLMAP / NIKTO
Teste de aplicações web (proxy de interceptação, SQL injection, scan de
servidor web).
- Uso defensivo: identificar OWASP Top 10, SQL injection e configurações
  inseguras em aplicações próprias.
- Hardening: prepared statements, WAF, validação de entrada e headers seguros.

## SNORT / SURICATA / FAIL2BAN
IDS/IPS (detecção/prevenção de intrusão) e prevenção de força bruta.
- Uso defensivo: assinaturas de ataque, bloqueio de IPs reincidentes e
  correlação de eventos.
- Hardening: regras atualizadas, centralização de logs (SIEM) e fail2ban
  para serviços expostos (SSH, HTTP).

## HARDENING LINUX
- Atualização contínua, princípio do menor privilégio, SSH por chave,
  firewall (nftables/ufw), SELinux/AppArmor, auditoria (auditd), remoção de
  serviços desnecessários, criptografia (LUKS) e fail2ban.

## HARDENING WINDOWS
- Patch management, BitLocker, Credential Guard, LSA Protection, ASR (Attack
  Surface Reduction), Windows Defender, AppLocker/WDAC, MFA, Sysmon para
  logging e segmentação de rede.

## OWASP TOP 10
- A01 Broken Access Control, A02 Cryptographic Failures, A03 Injection,
  A04 Insecure Design, A05 Security Misconfiguration, A06 Vulnerable and
  Outdated Components, A07 Identification and Authentication Failures,
  A08 Software and Data Integrity Failures, A09 Security Logging and
  Monitoring Failures, A10 Server-Side Request Forgery (SSRF).

## MITRE ATT&CK
- Taxonomia de táticas/técnicas adversárias: Initial Access, Execution,
  Persistence, Privilege Escalation, Defense Evasion, Credential Access,
  Discovery, Lateral Movement, Collection, Exfiltration e Impact.
- Uso defensivo: mapear detecções para técnicas e priorizar controles.

## RESPOSTA A INCIDENTES E FORENSE
- Ciclo: Preparação → Identificação → Contenção → Erradicação → Recuperação
  → Lições aprendidas. Preservar evidências (imagem forense, hashes, cadeia
  de custódia), análise de memória (Volatility), logs e timeline.
"""


def _log(mensagem: str, nivel: str = "INFO") -> None:
    """Emite uma mensagem de log formatada no terminal."""
    print(f"[KBASE {nivel:<5}] {mensagem}")


def _extrair_termos(query: str) -> list[str]:
    """Extrai termos relevantes (sem stopwords) de uma consulta."""
    tokens = re.findall(r"[a-z0-9][a-z0-9\-+]*", query.lower())
    termos: list[str] = []
    for token in tokens:
        if len(token) < 3 and token not in ("ip", "tcp", "udp", "syn", "ssd"):
            continue
        if token in _STOPWORDS:
            continue
        if token not in termos:
            termos.append(token)
    return termos


# ---------------------------------------------------------------------------
# Gerenciador da base de conhecimento
# ---------------------------------------------------------------------------


class KnowledgeBaseManager:
    """
    Gerencia os arquivos de texto da base de conhecimento local e realiza
    buscas por palavras-chave/relevância para alimentar o contexto do modelo.
    """

    def __init__(self, base_dir: Path | None = None):
        self._base_dir = Path(base_dir) if base_dir else KNOWLEDGE_BASE_DIR
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Criação automática do guia
    # ------------------------------------------------------------------

    def carregar_e_salvar_guia_mr_robot(self) -> Path:
        """
        Garante a existência do arquivo `mr_robot_cybersecurity_guide.txt`.

        Se o arquivo ainda não existir, cria-o com o conteúdo padrão do guia.
        Retorna o caminho (Path) do arquivo.
        """
        caminho = self._base_dir / MR_ROBOT_GUIDE_FILENAME
        if not caminho.exists():
            try:
                caminho.write_text(MR_ROBOT_GUIDE_CONTENT, encoding="utf-8")
                _log(f"Guia Mr. Robot criado em: {caminho}", "INFO")
            except OSError as exc:
                _log(f"Falha ao criar guia Mr. Robot: {exc}", "ERROR")
        return caminho

    # ------------------------------------------------------------------
    # Busca por relevância
    # ------------------------------------------------------------------

    def buscar_contexto_relevante(self, query: str, max_trechos: int = 3) -> str:
        """
        Busca trechos relevantes nos arquivos da base de conhecimento.

        A busca é feita por palavras-chave (com remoção de stopwords) e
        pontuação de relevância por seção. Retorna uma string com os trechos
        mais relevantes, ou "" caso nada seja encontrado.
        """
        query = (query or "").strip()
        if not query:
            return ""

        termos = self._extrair_termos(query)
        if not termos:
            return ""

        # Garante que o guia exista antes de buscar.
        self.carregar_e_salvar_guia_mr_robot()

        resultados: list[tuple[int, str, str]] = []
        for arquivo in self._listar_arquivos():
            try:
                conteudo = arquivo.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            for titulo, corpo in self._dividir_em_secoes(conteudo):
                score = self._pontuar_secao(titulo, corpo, termos)
                if score > 0:
                    resultados.append((score, titulo, corpo))

        if not resultados:
            return ""

        # Ordena por relevância (maior score primeiro).
        resultados.sort(key=lambda item: item[0], reverse=True)

        trechos: list[str] = []
        for score, titulo, corpo in resultados[:max_trechos]:
            corpo_limpo = corpo.strip()
            trechos.append(f"## {titulo}\n{corpo_limpo[:1200]}")

        return "\n\n".join(trechos)

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _listar_arquivos(self) -> list[Path]:
        """Lista todos os arquivos .txt da base de conhecimento."""
        return sorted(
            p for p in self._base_dir.glob("*.txt") if p.is_file()
        )

    def _extrair_termos(self, query: str) -> list[str]:
        """Extrai termos relevantes (sem stopwords) de uma consulta."""
        return _extrair_termos(query)

    def _dividir_em_secoes(self, conteudo: str) -> list[tuple[str, str]]:
        """
        Divide o conteúdo em seções usando linhas `## Título` como delimitador.
        Retorna uma lista de tuplas (título, corpo).
        """
        secoes: list[tuple[str, str]] = []
        titulo_atual = ""
        corpo_atual: list[str] = []

        for linha in conteudo.splitlines():
            match = re.match(r"^##\s+(.+)$", linha.strip())
            if match:
                if titulo_atual:
                    secoes.append((titulo_atual, "\n".join(corpo_atual)))
                titulo_atual = match.group(1).strip()
                corpo_atual = []
            else:
                corpo_atual.append(linha)

        if titulo_atual:
            secoes.append((titulo_atual, "\n".join(corpo_atual)))
        return secoes

    def _pontuar_secao(self, titulo: str, corpo: str, termos: list[str]) -> int:
        """
        Pontua uma seção pela ocorrência dos termos de busca.

        Ocorrências no título valem mais (peso 5) do que no corpo (peso 1).
        """
        score = 0
        texto_corpo = corpo.lower()
        texto_titulo = titulo.lower()
        for termo in termos:
            padrao = rf"\b{re.escape(termo)}\b"
            score += len(re.findall(padrao, texto_corpo))
            score += 5 * len(re.findall(padrao, texto_titulo))
        return score

    def indexar_diretorio_projeto(self, caminho_pasta: str) -> int:
        """
        Varre recursivamente um diretório de projeto e indexa o conteúdo de
        arquivos de código/documentação na base de conhecimento local (RAG).

        Lê arquivos .py, .js, .ts, .md, .txt e .json, ignorando diretórios
        como .git, node_modules, __pycache__, venv e dist.

        O conteúdo é estruturado em blocos (um por arquivo) com cabeçalho
        `## <caminho_relativo>` e salvo em `data/knowledge_base/`, permitindo
        que a IA responda dúvidas e sugira refatorações sobre o projeto.

        Returns:
            Número de arquivos indexados.
        """
        raiz = Path(caminho_pasta).resolve()
        if not raiz.is_dir():
            _log(f"Diretório inválido para indexação: {raiz}", "ERROR")
            return 0

        extensoes = {".py", ".js", ".ts", ".md", ".txt", ".json"}
        ignorados = {
            ".git", "node_modules", "__pycache__", "venv", ".venv",
            "dist", "build", ".idea", ".vscode",
        }

        blocos: list[str] = []
        total = 0
        for arquivo in sorted(raiz.rglob("*")):
            if not arquivo.is_file():
                continue
            if any(parte in ignorados for parte in arquivo.parts):
                continue
            if arquivo.suffix.lower() not in extensoes:
                continue
            try:
                conteudo = arquivo.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            rel = arquivo.relative_to(raiz).as_posix()
            # Limita arquivos muito grandes para não inchar o índice.
            if len(conteudo) > 20000:
                conteudo = conteudo[:20000] + "\n... (conteúdo truncado)"
            blocos.append(f"## {rel}\n{conteudo}")
            total += 1

        if not blocos:
            _log(f"Nenhum arquivo indexável em: {raiz}", "WARNING")
            return 0

        nome_indice = f"projeto_{raiz.name}.txt"
        destino = self._base_dir / nome_indice
        cabecalho = (
            f"# ÍNDICE DE PROJETO: {raiz.name}\n"
            f"# Caminho: {raiz}\n"
            f"# Arquivos indexados: {total}\n\n"
        )
        try:
            destino.write_text(cabecalho + "\n\n".join(blocos), encoding="utf-8")
        except OSError as exc:
            _log(f"Falha ao salvar índice do projeto: {exc}", "ERROR")
            return 0

        _log(f"Projeto '{raiz.name}' indexado: {total} arquivos -> {destino}", "INFO")
        return total


# ---------------------------------------------------------------------------
# Memória de autocorreção de erros (error_learnings.json)
# ---------------------------------------------------------------------------


class ErrorLearningsManager:
    """
    Gerencia o arquivo `error_learnings.json` com o histórico de falhas de
    execução e as lições aprendidas (memória de autocorreção de erros).
    """

    def __init__(self, base_dir: Path | None = None):
        self._base_dir = Path(base_dir) if base_dir else KNOWLEDGE_BASE_DIR
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._arquivo = self._base_dir / ERROR_LEARNINGS_FILENAME

    def _carregar(self) -> list[dict]:
        if not self._arquivo.exists():
            return []
        try:
            dados = json.loads(self._arquivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if isinstance(dados, dict):
            return dados.get("aprendizados", [])
        return dados if isinstance(dados, list) else []

    def _salvar(self, registros: list[dict]) -> bool:
        try:
            self._arquivo.write_text(
                json.dumps({"aprendizados": registros}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return True
        except OSError as exc:
            _log(f"Falha ao salvar {ERROR_LEARNINGS_FILENAME}: {exc}", "ERROR")
            return False

    def registrar_erro(
        self,
        comando_ou_prompt: str,
        stdout_stderr: str,
        causa_raiz: str,
        solucao_aplicada: str,
    ) -> bool:
        """Registra uma nova lição aprendida a partir de uma falha."""
        registros = self._carregar()
        registros.append({
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "comando_ou_prompt": comando_ou_prompt,
            "stdout_stderr": stdout_stderr,
            "causa_raiz": causa_raiz,
            "solucao_aplicada": solucao_aplicada,
        })
        # Mantém apenas os 200 registros mais recentes.
        return self._salvar(registros[-200:])

    def buscar_licoes_relevantes(self, query: str, max_registros: int = 3) -> str:
        """
        Busca lições aprendidas similares ao comando/prompt atual.

        Retorna uma string formatada com o contexto de memória, ou "" se nada
        relevante for encontrado.
        """
        query = (query or "").strip()
        if not query:
            return ""
        termos = _extrair_termos(query)
        if not termos:
            return ""

        registros = self._carregar()
        if not registros:
            return ""

        pontuados: list[tuple[int, dict]] = []
        for reg in registros:
            texto = (
                str(reg.get("comando_ou_prompt", "")) + " " +
                str(reg.get("causa_raiz", "")) + " " +
                str(reg.get("stdout_stderr", ""))
            ).lower()
            score = 0
            for termo in termos:
                padrao = rf"\b{re.escape(termo)}\b"
                score += len(re.findall(padrao, texto))
            if score > 0:
                pontuados.append((score, reg))

        if not pontuados:
            return ""

        pontuados.sort(key=lambda item: item[0], reverse=True)

        linhas: list[str] = []
        for score, reg in pontuados[:max_registros]:
            linhas.append(
                "[SISTEMA DE MEMÓRIA]: Em uma execução anterior, o comando "
                f"'{reg.get('comando_ou_prompt', '?')}' falhou pelo motivo "
                f"'{reg.get('causa_raiz', 'falha desconhecida')}'. Aplique a "
                f"solução '{reg.get('solucao_aplicada', 'revisar o erro')}' "
                "aprendida previamente."
            )
        return "\n".join(linhas)

    @staticmethod
    def analisar_causa_raiz(stdout_stderr: str) -> tuple[str, str]:
        """
        Analisa heuristicamente a causa raiz de uma falha a partir do stderr.

        Retorna uma tupla (causa_raiz, solucao_aplicada).
        """
        texto = (stdout_stderr or "").lower()
        if "not recognized" in texto or "não é reconhecido" in texto or "não reconhecido" in texto:
            return ("Comando não encontrado no PATH", "Verificar a grafia do comando e o PATH do sistema.")
        if "access is denied" in texto or "acesso negado" in texto or "permission denied" in texto:
            return ("Permissão insuficiente", "Executar com privilégios adequados e revisar as permissões.")
        if "timeout" in texto or "timed out" in texto:
            return ("Tempo limite excedido", "Aumentar o timeout ou otimizar a operação.")
        if "filenotfounderror" in texto or "no such file" in texto or "não foi possível encontrar" in texto:
            return ("Arquivo ou caminho inexistente", "Verificar o caminho e a existência do arquivo.")
        if "syntax" in texto or "syntaxerror" in texto:
            return ("Erro de sintaxe no script/comando", "Corrigir a sintaxe e validar antes de executar.")
        if "connection refused" in texto or "unreachable" in texto or "não foi possível conectar" in texto:
            return ("Serviço/rede indisponível", "Verificar se o serviço está ativo e a conectividade.")
        return ("Falha genérica de execução", "Revisar o comando e a saída de erro completa.")


# ---------------------------------------------------------------------------
# Execução direta (teste / diagnóstico)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S — Teste do KnowledgeBaseManager")
    print("=" * 60)

    kb = KnowledgeBaseManager()
    caminho = kb.carregar_e_salvar_guia_mr_robot()
    print(f"\n[1] Guia Mr. Robot: {caminho}")
    print(f"    Existe: {caminho.exists()}")

    for consulta in ("nmap scan de portas", "hardening windows", "mimikatz"):
        print(f"\n[2] Busca por: '{consulta}'")
        contexto = kb.buscar_contexto_relevante(consulta, max_trechos=2)
        print(f"    {len(contexto)} caracteres de contexto encontrados.")
        if contexto:
            print("    " + contexto[:200].replace("\n", "\n    ") + " ...")

    print("\nTeste concluído.")
