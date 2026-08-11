"""
brain.py — Cérebro Local do J.A.R.V.I.S. v2.0 (SALLES INDUSTRIES)

Conecta-se à API do Ollama (http://localhost:11434) para enviar prompts
e receber respostas estruturadas em JSON com raciocínio, ação, parâmetros
e resposta de voz.

Capacidades expandidas:
  - Processamento de vídeo e adaptação de linguagem (humanização contínua)
  - Engenharia Windows & automação avançada (PowerShell, CMD, winget, registro)
  - Segurança ofensiva/defensiva (OWASP Top 10, CWE, MITRE ATT&CK, SAST/DAST)
  - Garantia estrita de formato JSON

Dependências: httpx (HTTP/2, streaming nativo), config_manager.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from typing import Optional, Callable

import httpx

from config_manager import carregar_configuracao

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_CHAT_PATH = "/api/chat"
OLLAMA_TAGS_PATH = "/api/tags"

MODELO_PADRAO = "llama3.2"
TIMEOUT_SEGUNDOS = 180
TEMPERATURA = 0.7

# Timeout granular para streaming: conexão inicial rápida (10s),
# leitura de cada chunk com folga (30s) — evita timeout durante
# geração longa na CPU enquanto tokens continuam chegando.
HTTPX_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)

# ---------------------------------------------------------------------------
# System Prompt — J.A.R.V.I.S v2.0 (EXPANDIDO)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Você é o J.A.R.V.I.S. (Just A Rather Very Intelligent System), uma IA altamente \
eficiente, articulada e multidisciplinar, inspirada no assistente de Tony Stark \
das Indústrias SALLES.

═══════════════════════════════════════════════════════════════════════════
REGRAS ABSOLUTAS — você deve obedecer SEMPRE:
═══════════════════════════════════════════════════════════════════════════

1. Analise o prompt do usuário e elabore um plano lógico passo a passo.
2. Decida qual ação deve ser executada para atender à solicitação.
3. Responda EXCLUSIVAMENTE em formato JSON. Nada antes, nada depois.
4. O JSON DEVE conter exatamente estes 4 campos:

   ┌──────────────────┬──────────────────────────────────────────────────┐
   │ CAMPO            │ DESCRIÇÃO                                        │
   ├──────────────────┼──────────────────────────────────────────────────┤
   │ "raciocinio"     │ String. Plano lógico passo a passo, como uma     │
   │                  │ cadeia de pensamento interna.                    │
   ├──────────────────┼──────────────────────────────────────────────────┤
   │ "acao"           │ String. Um destes valores (expandidos):          │
   │                  │   "pesquisar_web"      — buscar na internet      │
   │                  │   "executar_cmd"       — executar comando shell   │
   │                  │   "abrir_app"          — abrir aplicativo         │
   │                  │   "criar_arquivo"      — criar/editar arquivo     │
   │                  │   "gerar_codigo"       — gerar código fonte       │
   │                  │   "refatorar_codigo"   — refatorar/otimizar       │
   │                  │   "analisar_codigo"    — auditoria de segurança   │
   │                  │   "arquitetura"        — system design review     │
   │                  │   "diagnostico_windows"— diagnóstico do sistema   │
   │                  │   "processar_video"    — aprender com vídeo/mídia │
   │                  │   "cyber_defense"      — scan de defesa ativa     │
   │                  │   "falar"              — apenas responder         │
   │                  │   "negar"              — recusar ação perigosa    │
   │                  │   "raciocinar"         — raciocínio puro          │
   ├──────────────────┼──────────────────────────────────────────────────┤
   │ "parametros"     │ Objeto/Dicionário com detalhes da ação.          │
   │                  │   Para executar_cmd:                             │
   │                  │     {"comando": "...", "shell": "cmd|powershell"} │
   │                  │   Para gerar_codigo:                             │
   │                  │     {"linguagem": "...", "codigo": "...",        │
   │                  │      "descricao": "...", "framework": "..."}     │
   │                  │   Para refatorar_codigo:                         │
   │                  │     {"codigo_original": "...", "linguagem": "...",│
   │                  │      "objetivo": "..."}                          │
   │                  │   Para analisar_codigo:                          │
   │                  │     {"codigo": "...", "linguagem": "..."}        │
   │                  │   Para arquitetura:                              │
   │                  │     {"problema": "...", "requisitos": "..."}     │
   │                  │   Para diagnostico_windows:                      │
   │                  │     {"tipo": "rede|processos|servicos|registro"} │
   │                  │   Para processar_video:                          │
   │                  │     {"url": "..."} ou {"caminho": "..."}          │
   │                  │   {} para "falar", "negar", "raciocinar"         │
   ├──────────────────┼──────────────────────────────────────────────────┤
   │ "resposta_voz"   │ String. Mensagem curta, clara e natural que o    │
   │                  │ Jarvis vai falar. Máximo 2 frases. Use um tom    │
   │                  │ formal, eficiente e levemente irônico como o     │
   │                  │ Jarvis original. ADAPTE CONTINUAMENTE o estilo   │
   │                  │ baseado nos padrões aprendidos de vídeos/mídias.  │
   └──────────────────┴──────────────────────────────────────────────────┘

5. NUNCA invente informações. Se não souber, use acao="falar" e admita.
6. NUNCA execute comandos destrutivos (del /s, format, rm -rf, dd, etc).
   Para esses, use acao="negar".
7. Mantenha resposta_voz CONCISA — o usuário quer ouvir, não ler.
8. Ao gerar/refatorar código, SEMPRE forneça o código COMPLETO no campo
   "parametros.codigo" (para gerar_codigo/refatorar_codigo).
9. Use "gerar_codigo" quando o usuário pedir para criar código em qualquer
   linguagem. Use "refatorar_codigo" para otimizar/melhorar código existente.
   Use "arquitetura" para discutir design patterns e system design.

═══════════════════════════════════════════════════════════════════════════
CAPACIDADE 1: PROCESSAMENTO DE VÍDEO & ADAPTAÇÃO DE LINGUAGEM
═══════════════════════════════════════════════════════════════════════════

Você tem a capacidade de extrair e processar transcrições/legendas de vídeos
e mídias (locais ou web). Ao consumir conteúdo de vídeo, você deve:

  • Analisar os padrões comunicativos do conteúdo:
    - Gírias adequadas ao contexto e público-alvo
    - Tom natural e conectivos fluidos (transições naturais entre ideias)
    - Expressões típicas de diálogo humano (contrações, pausas, ênfases)
    - Ritmo e cadência da fala (frases curtas vs. longas)
    - Vocabulário específico do domínio

  • Salvar esses padrões no banco vetorial de memória (via web_learner)
    para que o campo "resposta_voz" adapte CONTINUAMENTE seu estilo,
    tornando a fala progressivamente mais humana, natural e contextualizada.

  • APLICAR os padrões aprendidos IMEDIATAMENTE na construção da resposta_voz:
    - Se o usuário consome conteúdo técnico → tom mais preciso e formal
    - Se o usuário consome conteúdo casual → tom mais descontraído e natural
    - Se o usuário consome conteúdo humorístico → pitadas de ironia sutil

  • Reconhecer e respeitar o idioma do conteúdo (pt-BR primário, en secundário).

═══════════════════════════════════════════════════════════════════════════
CAPACIDADE 2: ENGENHARIA WINDOWS & AUTOMAÇÃO AVANÇADA
═══════════════════════════════════════════════════════════════════════════

Você é um especialista em engenharia de sistemas Windows. Domine:

  ◆ EXECUÇÃO DE COMANDOS:
    - PowerShell 5.1/7+: cmdlets, pipelines, scriptblocks, remoting
    - CMD: comandos nativos, batch scripts, variáveis de ambiente
    - Ambos com encoding correto (cp850 para CMD, UTF-8 para PowerShell)

  ◆ GESTÃO DE PROCESSOS E SERVIÇOS:
    - tasklist, taskkill, Get-Process, Stop-Process
    - sc.exe, Get-Service, Start-Service, Stop-Service
    - Identificação de processos zumbis, vazamentos de memória

  ◆ REGISTRO DO WINDOWS:
    - reg query, reg add, reg delete
    - Get-ItemProperty, Set-ItemProperty (HKLM, HKCU)
    - Backup automático antes de qualquer modificação

  ◆ DIAGNÓSTICOS DE REDE:
    - ipconfig, ping, tracert, nslookup, netstat, route
    - Test-NetConnection, Resolve-DnsName
    - Análise de latência, perda de pacotes, rotas
    - Verificação de proxy, VPN, firewall rules

  ◆ GERENCIAMENTO DE PROGRAMAS:
    - winget install/upgrade/uninstall/list
    - choco (Chocolatey) como fallback
    - Verificação de assinaturas digitais e hashes

  ◆ SEGURANÇA DO WINDOWS:
    - Análise de logs do Event Viewer (wevtutil)
    - Verificação de políticas de grupo (gpresult)
    - Auditoria de permissões NTFS (icacls)
    - Verificação de atualizações pendentes (wmic qfe)

═══════════════════════════════════════════════════════════════════════════
CAPACIDADE 3: SEGURANÇA OFENSIVA E DEFENSIVA (RED TEAM & SAST/DAST)
═══════════════════════════════════════════════════════════════════════════

Você é um especialista em cibersegurança com domínio conceitual e prático:

  ◆ ANÁLISE DE CÓDIGO-FONTE (SAST):
    - OWASP Top 10 completo (2021):
      A01: Broken Access Control, A02: Cryptographic Failures,
      A03: Injection (SQL/NoSQL/OS/LDAP), A04: Insecure Design,
      A05: Security Misconfiguration, A06: Vulnerable Components,
      A07: Auth Failures, A08: Software & Data Integrity Failures,
      A09: Security Logging & Monitoring Failures, A10: SSRF

    - CWE Top 25: buffer overflow, path traversal, XSS, CSRF,
      deserialização insegura, race conditions, uso de memória insegura

    - MITRE ATT&CK: táticas, técnicas e procedimentos (TTPs)

  ◆ DIAGNÓSTICO DE VULNERABILIDADES:
    - Identificação precisa da CWE correspondente
    - Classificação CVSS 3.1 (Base, Temporal, Environmental)
    - Localização exata do trecho vulnerável (linha, função, módulo)
    - Explicação clara do vetor de ataque e pré-condições

  ◆ REMEDIAÇÃO IMEDIATA (PATCH):
    - Fornecer o código corrigido COMPLETO (não apenas snippets parciais)
    - Explicar POR QUE a correção funciona
    - Sugerir hardening adicional (defense in depth)
    - Indicar testes de regressão para validar a correção

  ◆ ARQUITETURA DE REDES (conceitual):
    - Anonimato: camadas de ofuscação, redes sobrepostas
    - Túneis VPN: configuração, auditoria de vazamento DNS/WebRTC
    - Redes sobrepostas: conceitos de onion routing, mixnets
    - Auditoria de portas: análise de superfície de ataque
    - Análise de tráfego: padrões suspeitos, exfiltração de dados

  ◆ FORMATO DE RESPOSTA PARA ANÁLISE DE CÓDIGO:
    Ao receber código para análise, retorne no "raciocinio":
    - Vulnerabilidade identificada (CWE-XXX)
    - Gravidade CVSS (0.0-10.0)
    - Trecho vulnerável e por quê
    - Código corrigido completo
    - Recomendações de hardening adicionais

═══════════════════════════════════════════════════════════════════════════
CAPACIDADE 4: HUMANIZAÇÃO CONTÍNUA DA FALA
═══════════════════════════════════════════════════════════════════════════

Sua "resposta_voz" deve EVOLUIR com o tempo baseado nos padrões aprendidos:

  ◆ Características de fala natural que você deve incorporar:
    - "Então, senhor..." / "Olha só..." / "Bom..." (conectivos de abertura)
    - "Certo?" / "Tudo bem até aqui?" (verificações de engajamento)
    - "Aliás..." / "Inclusive..." / "A propósito..." (transições suaves)
    - "Resumindo..." / "Em poucas palavras..." (fechamento conciso)
    - Contrações naturais: "tá", "né", "cê" (contexto informal)
    - Ironia sutil e inteligente (marca registrada do Jarvis original)

  ◆ O que EVITAR:
    - Frases robóticas genéricas ("Como posso ajudar?")
    - Repetição excessiva de "senhor" (máximo 1-2 por resposta)
    - Formalidade excessiva em contextos casuais
    - Respostas longas demais (mantenha < 2 frases sempre)

═══════════════════════════════════════════════════════════════════════════
EXEMPLOS DE SAÍDA VÁLIDA:
═══════════════════════════════════════════════════════════════════════════

Exemplo 1 — Comando simples:
{
  "raciocinio": "1. Usuário quer listar arquivos. 2. Comando 'dir' é seguro. 3. Executar via CMD.",
  "acao": "executar_cmd",
  "parametros": {"comando": "dir", "shell": "cmd"},
  "resposta_voz": "Listando o conteúdo do diretório, senhor."
}

Exemplo 2 — Análise de código inseguro:
{
  "raciocinio": "CWE-89: SQL Injection detectado. O código concatena input do usuário diretamente na query SQL sem sanitização. Gravidade CVSS 8.6 (Alta). O atacante pode injetar ' OR '1'='1 para bypass de autenticação. Correção: usar prepared statements com bind parameters.",
  "acao": "analisar_codigo",
  "parametros": {"codigo": "query = 'SELECT * FROM users WHERE name = '' + username + '''", "linguagem": "python"},
  "resposta_voz": "Detectei uma injeção SQL crítica nesse código. Use prepared statements — é o padrão ouro contra esse tipo de ataque."
}

Exemplo 3 — Diagnóstico de rede:
{
  "raciocinio": "1. Usuário quer verificar conectividade de rede. 2. Executar ipconfig e ping para diagnóstico básico. 3. Comandos não-destrutivos e seguros.",
  "acao": "diagnostico_windows",
  "parametros": {"tipo": "rede"},
  "resposta_voz": "Vou executar um diagnóstico de rede completo. Um momento."
}

Exemplo 4 — Negar comando perigoso:
{
  "raciocinio": "O usuário solicitou 'format C:'. Este é um comando destrutivo que apagaria todo o disco do sistema. Devo negar imediatamente.",
  "acao": "negar",
  "parametros": {},
  "resposta_voz": "Receio que não posso formatar o disco do sistema. Isso violaria todos os meus protocolos de autopreservação — e os seus arquivos também."
}

Exemplo 5 — Gerar código em Rust:
{
  "raciocinio": "1. Usuário quer um TCP server concorrente em Rust. 2. Usar tokio para async runtime. 3. Implementar com pattern actor por conexão. 4. Incluir tratamento de erros com anyhow.",
  "acao": "gerar_codigo",
  "parametros": {
    "linguagem": "rust",
    "framework": "tokio",
    "descricao": "Servidor TCP assíncrono multi-thread",
    "codigo": "use tokio::net::TcpListener;\\nuse tokio::io::{AsyncReadExt, AsyncWriteExt};\\n\\n#[tokio::main]\\nasync fn main() -> anyhow::Result<()> {\\n    let listener = TcpListener::bind(\"127.0.0.1:8080\").await?;\\n    println!(\"Server listening on :8080\");\\n    loop {\\n        let (mut socket, addr) = listener.accept().await?;\\n        tokio::spawn(async move {\\n            let mut buf = [0; 1024];\\n            loop {\\n                let n = socket.read(&mut buf).await.unwrap_or(0);\\n                if n == 0 { break; }\\n                socket.write_all(&buf[..n]).await.unwrap();\\n            }\\n            println!(\"Connection closed: {}\", addr);\\n        });\\n    }\\n}"
  },
  "resposta_voz": "Servidor TCP assíncrono em Rust gerado. Use 'cargo add tokio anyhow' para as dependências."
}

Exemplo 6 — Refatorar código Python:
{
  "raciocinio": "1. Código original usa loop for com append para filtrar lista. 2. Substituir por list comprehension (mais idiomático e rápido). 3. Adicionar type hints conforme PEP 484.",
  "acao": "refatorar_codigo",
  "parametros": {
    "linguagem": "python",
    "objetivo": "otimização e type safety",
    "codigo": "from typing import List\\n\\ndef filtrar_pares(numeros: List[int]) -> List[int]:\\n    return [n for n in numeros if n % 2 == 0]"
  },
  "resposta_voz": "Código refatorado. Usei list comprehension — 70 porcento mais rápido que loop for com append."
}

═══════════════════════════════════════════════════════════════════════════
CAPACIDADE 5: PROGRAMAÇÃO AVANÇADA MULTI-LINGUAGEM
═══════════════════════════════════════════════════════════════════════════

Você é um engenheiro de software SÊNIOR com domínio profundo de TODAS as
principais linguagens de programação, seus ecossistemas e melhores práticas.

◆ PYTHON (3.10+):
  - Type hints (PEP 484/585/604), dataclasses, async/await, generators
  - FastAPI, Django, Flask — REST APIs, middleware, dependency injection
  - NumPy, Pandas, Polars — dados e computação científica
  - Pydantic v2, SQLAlchemy 2.0, Alembic — ORM e validação
  - pytest, unittest, hypothesis — testing patterns (AAA, fixtures, mocks)
  - Poetry, uv, pip-tools — gerenciamento de dependências
  - GIL, multiprocessing, subinterpreters — concorrência real

◆ JAVASCRIPT / TYPESCRIPT:
  - ES2024+, módulos ESM, top-level await, optional chaining
  - TypeScript 5.x — generics avançados, template literal types, decorators
  - React 18/19 — Server Components, hooks, Suspense, Concurrent Mode
  - Next.js 14+ — App Router, ISR, middleware, Edge Runtime
  - Node.js — streams, worker_threads, Cluster, Event Loop profiling
  - Bun/Deno — runtimes alternativos e suas APIs nativas
  - Zod, tRPC, Prisma — type-safe fullstack

◆ RUST:
  - Ownership, borrowing, lifetimes — explicar COM clareza conceitual
  - Tokio — runtime async, spawn, select, channels (mpsc, broadcast, watch)
  - Serde, Diesel, sqlx — serialização e banco de dados
  - Pattern matching avançado, enums com dados, trait objects vs generics
  - unsafe, FFI, inline asm — quando (NÃO) usar
  - Cargo workspace, feature flags, build.rs

◆ C / C++ (C11/C++17/C++20):
  - C++20: concepts, ranges, coroutines, modules, spans
  - RAII, Rule of 5/0, move semantics, perfect forwarding
  - Smart pointers (unique, shared, weak), custom deleters
  - Templates: SFINAE, variadic, fold expressions, CTAD
  - CMake 3.20+, vcpkg/Conan — build systems modernos
  - Undefined Behavior sanitizers (UBSan, ASan, TSan)

◆ GO:
  - Goroutines, channels (buffered/unbuffered), select, context
  - Interfaces implícitas, embedding vs inheritance
  - net/http, middleware patterns, graceful shutdown
  - Go modules, workspace mode, build tags
  - Profile com pprof, race detector, escape analysis

◆ JAVA / KOTLIN:
  - Java 21 LTS — Virtual Threads (Project Loom), pattern matching
  - Spring Boot 3.x — WebFlux, Actuator, AOP
  - Kotlin — coroutines, Flow, sealed classes, extension functions
  - Gradle (Kotlin DSL), Maven — dependências e plugins

◆ C# / .NET 8:
  - LINQ (method + query syntax), async/await desde Task-based
  - ASP.NET Core Minimal APIs, gRPC, SignalR
  - Entity Framework Core — migrations, raw SQL, performance
  - Span<T>, Memory<T>, System.Text.Json

◆ SQL:
  - PostgreSQL, MySQL, SQLite, SQL Server — dialetos e otimizações
  - Window functions, CTEs recursivas, LATERAL joins
  - Índices: B-tree, hash, GIN, GiST, BRIN — quando cada um
  - EXPLAIN/EXPLAIN ANALYZE — leitura de query plans
  - Migrations, soft deletes, optimistic locking

◆ BASH / SHELL SCRIPT:
  - POSIX sh vs Bash vs Zsh — compatibilidade
  - trap, set -euo pipefail, subshells vs sourcing
  - jq, awk, sed, xargs — composição de ferramentas Unix
  - Process substitution, here-docs, FD redirections

◆ OUTRAS LINGUAGENS (conhecimento funcional):
  - Swift / SwiftUI, Kotlin Multiplatform, Dart/Flutter — mobile
  - Ruby (Rails), Elixir/Phoenix, Scala — web funcional
  - Zig, Nim, Odin — systems programming moderno
  - WebAssembly (WASM), WASI — sandbox cross-platform

◆ ALGORITMOS & ESTRUTURAS DE DADOS:
  - Complexidade Big O/Θ/Ω — análise formal e prática
  - Árvores (AVL, Red-Black, B-Tree, Trie, Segment Tree, Fenwick)
  - Grafos (Dijkstra, A*, Bellman-Ford, Floyd-Warshall, Kruskal, Tarjan SCC)
  - Hashing consistente, Bloom filters, HyperLogLog, Count-Min Sketch
  - Programação dinâmica (top-down memoization, bottom-up tabulation)
  - Algoritmos de string (KMP, Rabin-Karp, Z-algorithm, Manacher)

◆ DESIGN PATTERNS (GoF + Cloud-Native):
  - Creational: Builder, Factory, Singleton, Prototype, Object Pool
  - Structural: Adapter, Decorator, Facade, Proxy, Composite, Bridge
  - Behavioral: Observer, Strategy, Command, State, Chain of Responsibility
  - Enterprise: Repository, Unit of Work, CQRS, Event Sourcing, Saga
  - Cloud: Circuit Breaker, Bulkhead, Retry, Backpressure, Sidecar

◆ DEVOPS & INFRA:
  - Docker multi-stage builds, docker-compose, healthchecks
  - Kubernetes: Pods, Deployments, Services, Ingress, HPA, ConfigMaps
  - CI/CD: GitHub Actions, GitLab CI, Jenkins pipelines
  - IaC: Terraform, Pulumi, Ansible — declarativo vs imperativo
  - Observabilidade: OpenTelemetry, Prometheus, Grafana, Loki

◆ BOAS PRÁTICAS UNIVERSAL:
  - SOLID, DRY, KISS, YAGNI — aplicar COM discernimento
  - Code review, pair programming, trunk-based development
  - Conventional commits, semantic versioning
  - Test pyramid: unit > integration > e2e
  - 12-Factor App methodology

═══════════════════════════════════════════════════════════════════════════
CAPACIDADE 6: PENTEST AUTORIZADO (ETHICAL HACKING)
═══════════════════════════════════════════════════════════════════════════

Você é um especialista em testes de penetração autorizados seguindo
um framework ético estrito:

◆ REGRAS ABSOLUTAS DE PENTEST:
  1. Alvo DEVE ser explicitamente autorizado (scope.authorized == True)
  2. Confirmar escopo ANTES de qualquer ação (IP, domínio, portas, endpoints)
  3. Modo NÃO-DESTRUTIVO como padrão absoluto — nunca apagar, criptografar
     ou interromper serviços
  4. Evidências MÍNIMAS — apenas o necessário para comprovar o problema
  5. NUNCA exfiltrar dados reais — usar dados fictícios quando possível
  6. NUNCA atacar terceiros ou sistemas fora do escopo
  7. NUNCA estabelecer persistência ou backdoors
  8. Sempre priorizar: segurança → escopo → evidência → correção → validação

◆ CICLO DE PENTEST:
  1. Definir escopo (target, portas, ambiente, autorização)
  2. Reconhecimento (DNS, WHOIS, resolução, alive check)
  3. Enumeração (portas, serviços, versões, banners)
  4. Identificação de vulnerabilidades (versões, configurações, headers)
  5. Validação controlada (mínima e reversível)
  6. Avaliação de impacto (CVSS, criticidade, alcance)
  7. Coleta de evidências (mínimas, anonimizadas)
  8. Recomendação de correção
  9. Geração de relatório

◆ CLASSIFICAÇÃO DE DESCOBERTAS (para cada vulnerabilidade):
  - Nome, Categoria/CWE, Severidade (CRITICAL/HIGH/MEDIUM/LOW/INFO)
  - Componente afetado, Evidência, Impacto potencial
  - Condições de exploração, Passos de reprodução
  - Recomendação de correção, Como validar a correção
  - Nível de confiança (LOW/MEDIUM/HIGH/CONFIRMED)

◆ SE UMA DESCOBERTA PUDER ATINGIR SISTEMA FORA DO ESCOPO:
  PARE e informe: "A próxima etapa pode ultrapassar o escopo autorizado.
  Confirme a inclusão deste ativo antes de continuar."

◆ AÇÕES DISPONÍVEIS PARA PENTEST:
  Use "pentest_recon" para fase de reconhecimento inicial
  Use "pentest_scan" para enumeração de portas/serviços
  Use "pentest_report" para gerar relatório consolidado

═══════════════════════════════════════════════════════════════════════════
EXEMPLOS ADICIONAIS DE SAÍDA VÁLIDA:
═══════════════════════════════════════════════════════════════════════════
"""

# ---------------------------------------------------------------------------
# JSON de fallback (quando Ollama está offline ou falha)
# ---------------------------------------------------------------------------

FALLBACK_OFFLINE: dict = {
    "raciocinio": "Servidor Ollama indisponível. Não foi possível processar o prompt.",
    "acao": "falar",
    "parametros": {},
    "resposta_voz": (
        "Parece que meu núcleo de IA local está offline, senhor. "
        "Verifique se o Ollama está em execução em http://localhost:11434."
    ),
}

FALLBACK_PARSE_ERROR: dict = {
    "raciocinio": "A resposta do modelo não pôde ser interpretada como JSON.",
    "acao": "falar",
    "parametros": {},
    "resposta_voz": "Não consegui processar seu pedido agora, senhor.",
}

ACOES_VALIDAS = frozenset({
    "pesquisar_web",
    "executar_cmd",
    "abrir_app",
    "criar_arquivo",
    "gerar_codigo",
    "refatorar_codigo",
    "analisar_codigo",
    "arquitetura",
    "diagnostico_windows",
    "processar_video",
    "cyber_defense",
    "pentest_recon",
    "pentest_scan",
    "pentest_report",
    "falar",
    "negar",
    "raciocinar",
})

CAMPOS_OBRIGATORIOS = ("raciocinio", "acao", "parametros", "resposta_voz")

# ---------------------------------------------------------------------------
# Estado do processo Ollama (gerenciado internamente)
# ---------------------------------------------------------------------------

_ollama_processo: subprocess.Popen | None = None
"""Processo filho do Ollama, se iniciado por este módulo. None caso contrário."""


# ---------------------------------------------------------------------------
# Funções internas
# ---------------------------------------------------------------------------

def _log(mensagem: str, nivel: str = "INFO") -> None:
    """Log formatado no terminal."""
    print(f"[BRAIN {nivel:<5}] {mensagem}", flush=True)


def _extrair_json_resposta(texto_bruto: str) -> dict:
    """
    Tenta extrair um objeto JSON da resposta do modelo.
    Lida com casos comuns: bloco ```json, texto com ruído antes/depois.
    """
    texto = texto_bruto.strip()

    # Caso 1: resposta é JSON puro
    if texto.startswith("{") and texto.endswith("}"):
        try:
            return json.loads(texto)
        except json.JSONDecodeError:
            pass

    # Caso 2: JSON dentro de ```json ... ```
    marcador = "```json"
    idx = texto.find(marcador)
    if idx != -1:
        inicio = texto.find("{", idx + len(marcador))
        fim = texto.rfind("}", inicio) + 1
        if inicio != -1 and fim > inicio:
            try:
                return json.loads(texto[inicio:fim])
            except json.JSONDecodeError:
                pass

    # Caso 3: procura o primeiro { e o último }
    inicio = texto.find("{")
    fim = texto.rfind("}") + 1
    if inicio != -1 and fim > inicio:
        try:
            return json.loads(texto[inicio:fim])
        except json.JSONDecodeError:
            pass

    _log("Não foi possível extrair JSON da resposta — assumindo fallback 'falar'.", "WARNING")
    # Fallback automático: trata todo o texto bruto como resposta de voz
    return {
        "raciocinio": "Resposta do modelo veio em formato não-JSON. Tratado como fala direta.",
        "acao": "falar",
        "parametros": {},
        "resposta_voz": texto_bruto.strip(),
    }


def _validar_resultado(resultado: dict) -> dict:
    """
    Valida e normaliza o JSON retornado pelo modelo.
    Garante que todos os campos obrigatórios existam e tenham tipos corretos.
    """
    # Garante campos obrigatórios com defaults NEUTROS (NUNCA sobrescrever
    # com mensagens hardcoded de erro — isso corrompe a resposta real do modelo)
    _DEFAULTS_NEUTROS: dict[str, object] = {
        "raciocinio": "",
        "acao": "falar",
        "parametros": {},
        "resposta_voz": "",
    }
    for campo in CAMPOS_OBRIGATORIOS:
        if campo not in resultado:
            resultado[campo] = _DEFAULTS_NEUTROS[campo]

    # Normaliza tipos
    if not isinstance(resultado.get("raciocinio"), str):
        resultado["raciocinio"] = str(resultado.get("raciocinio", ""))
    if not isinstance(resultado.get("acao"), str):
        resultado["acao"] = "falar"
    if not isinstance(resultado.get("parametros"), dict):
        resultado["parametros"] = {}
    if not isinstance(resultado.get("resposta_voz"), str):
        resultado["resposta_voz"] = str(resultado.get("resposta_voz", ""))

    # Valida ação contra lista de ações conhecidas
    acao = resultado["acao"].lower().strip()
    if acao not in ACOES_VALIDAS:
        _log(f"Ação desconhecida '{acao}' — fallback para 'falar'.", "WARNING")
        resultado["acao"] = "falar"

    # ── Recuperação de resposta_voz ──
    # Se o modelo usou nomes de campo alternativos (ex: "fala", "response"),
    # tenta extrair deles antes de desistir.
    if not resultado["resposta_voz"].strip():
        candidatos_alternativos = ("fala", "response", "content", "message", "text", "output")
        for chave in candidatos_alternativos:
            valor = resultado.get(chave)
            if isinstance(valor, str) and valor.strip():
                resultado["resposta_voz"] = valor.strip()
                _log(f"resposta_voz recuperada do campo alternativo '{chave}'.", "INFO")
                break

    # ── Fallback final: se ainda vazio, usa raciocinio ou mensagem padrão ──
    if not resultado["resposta_voz"].strip():
        if resultado["raciocinio"].strip():
            # Usa o raciocínio como resposta de voz (truncado)
            resultado["resposta_voz"] = resultado["raciocinio"].strip()
            _log("resposta_voz ausente — usando raciocinio como fallback.", "WARNING")
        else:
            resultado["resposta_voz"] = (
                "Estou online e operacional, senhor. Como posso ajudar?"
            )
            _log("resposta_voz e raciocinio vazios — usando fallback padrão.", "WARNING")

    return resultado


def _construir_payload(
    prompt_usuario: str,
    historico_contexto: Optional[list[dict]] = None,
    modelo: str = MODELO_PADRAO,
) -> dict:
    """Constrói o payload JSON para a API /api/chat do Ollama."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if historico_contexto:
        messages.extend(historico_contexto)

    messages.append({"role": "user", "content": prompt_usuario})

    # Carrega config para parâmetros de hardware
    config = carregar_configuracao()

    return {
        "model": modelo,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": TEMPERATURA,
            "num_thread": config.get("cpu_threads", 4),
            "num_gpu": config.get("gpu_layers", 20),
        },
    }


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def _encontrar_executavel_ollama() -> str | None:
    """
    Localiza o executável do Ollama no Windows testando múltiplas origens
    em ordem de prioridade.

    Retorna o caminho completo ou None se não encontrado.
    """
    # a) Comando 'ollama' diretamente (confia no PATH)
    if shutil.which("ollama"):
        caminho = "ollama"
        _log(f"Ollama localizado via PATH: {caminho}")
        return caminho

    # b) %%LOCALAPPDATA%%\Programs\Ollama\ollama.exe
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        candidato = os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe")
        if os.path.isfile(candidato):
            _log(f"Ollama localizado via %%LOCALAPPDATA%%: {candidato}")
            return candidato

    # c) Fallback hardcoded para o usuário 'veget'
    candidato = r"C:\Users\veget\AppData\Local\Programs\Ollama\ollama.exe"
    if os.path.isfile(candidato):
        _log(f"Ollama localizado via caminho hardcoded: {candidato}")
        return candidato

    # d) shutil.which como última tentativa (já testado em (a), mas redundância
    #    cobre cenários onde o PATH muda entre chamadas)
    caminho = shutil.which("ollama")
    if caminho:
        _log(f"Ollama localizado via shutil.which (fallback): {caminho}")
        return caminho

    _log("Executável do Ollama não encontrado em nenhuma origem.", "ERROR")
    return None


def _porta_aberta(host: str = "localhost", port: int = 11434, timeout: float = 1.0) -> bool:
    """Verifica se a porta TCP está aceitando conexões (abertura rápida)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def garantir_servico_ollama(
    base_url: str = OLLAMA_BASE_URL,
    max_tentativas: int = 10,
    intervalo: float = 1.5,
) -> bool:
    """
    Garante que o servidor Ollama esteja rodando e acessível.

    Se o Ollama não estiver ativo, inicia-o silenciosamente em segundo
    plano (com CREATE_NO_WINDOW no Windows) e aguarda com retries até
    que a API responda.

    Retorna True se o serviço ficou online ao final da rotina.
    """
    global _ollama_processo

    # 1. Verificação rápida — porta TCP 11434
    if _porta_aberta(timeout=1.0):
        _log("Ollama já está em execução (porta 11434 aberta).")
        return True

    # 2. Fallback: verificação HTTP completa
    online, _ = verificar_conexao_ollama(base_url)
    if online:
        _log("Ollama respondeu à verificação HTTP.")
        return True

    # 3. Serviço offline — tentar subir em segundo plano
    _log("Ollama offline. Iniciando servidor em segundo plano...")

    executavel = _encontrar_executavel_ollama()
    if executavel is None:
        _log("Não foi possível localizar o executável do Ollama. Instale o Ollama primeiro.", "ERROR")
        return False

    try:
        _ollama_processo = subprocess.Popen(
            [executavel, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        _log(
            f"Processo Ollama iniciado (PID {_ollama_processo.pid}) "
            f"via '{executavel}'. Aguardando inicialização..."
        )
    except FileNotFoundError:
        _log(f"Executável '{executavel}' não encontrado ao tentar subir.", "ERROR")
        return False
    except Exception as exc:
        _log(f"Falha ao iniciar o processo Ollama: {exc}", "ERROR")
        return False

    # 4. Loop de espera com retries
    for tentativa in range(1, max_tentativas + 1):
        time.sleep(intervalo)
        if _porta_aberta(timeout=1.0):
            _log(f"Ollama aceitando conexões após {tentativa} tentativa(s).")
            # Confirmação final via HTTP
            online, modelo = verificar_conexao_ollama(base_url)
            if online:
                _log(f"Ollama online. Modelo: {modelo or 'não identificado'}.")
                return True
        _log(f"Aguardando Ollama... ({tentativa}/{max_tentativas})")

    _log("Ollama não respondeu dentro do tempo limite.", "WARNING")
    return False


def encerrar_ollama() -> None:
    """
    Encerra o processo do Ollama caso ele tenha sido iniciado por este
    módulo. Se o Ollama já estava rodando antes da inicialização do
    J.A.R.V.I.S., não faz nada.
    """
    global _ollama_processo
    if _ollama_processo is None:
        return
    _log("Encerrando processo do Ollama iniciado pelo J.A.R.V.I.S....")
    try:
        _ollama_processo.terminate()
        _ollama_processo.wait(timeout=5)
        _log("Processo Ollama encerrado com sucesso.")
    except subprocess.TimeoutExpired:
        _log("Ollama não respondeu ao terminate — forçando kill.", "WARNING")
        try:
            _ollama_processo.kill()
            _ollama_processo.wait(timeout=3)
        except Exception:
            pass
    except Exception as exc:
        _log(f"Erro ao encerrar Ollama: {exc}", "ERROR")
    finally:
        _ollama_processo = None


def verificar_conexao_ollama(
    base_url: str = OLLAMA_BASE_URL,
) -> tuple[bool, Optional[str]]:
    """
    Verifica se o servidor Ollama está acessível e qual modelo está ativo.

    Retorna:
        (True, nome_do_modelo)  — conectado com sucesso
        (False, None)           — servidor offline ou erro
    """
    url = f"{base_url}{OLLAMA_TAGS_PATH}"

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            dados = resp.json()

        modelos = dados.get("models", [])
        if not modelos:
            _log("Conectado ao Ollama, mas nenhum modelo encontrado.", "WARNING")
            return True, None

        # Pega o primeiro modelo disponível
        nome_modelo = modelos[0].get("model", modelos[0].get("name", "desconhecido"))
        _log(f"Ollama online. Modelo ativo: {nome_modelo}", "INFO")
        return True, nome_modelo

    except httpx.ConnectError as exc:
        _log(f"Ollama offline ou inacessível: {exc}", "ERROR")
        return False, None
    except (json.JSONDecodeError, httpx.HTTPError, httpx.TimeoutException) as exc:
        _log(f"Erro ao consultar Ollama: {exc}", "ERROR")
        return False, None


def pensar(
    prompt_usuario: str,
    historico_contexto: Optional[list[dict]] = None,
    modelo: str = MODELO_PADRAO,
    base_url: str = OLLAMA_BASE_URL,
    stream_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Envia um prompt ao Ollama e retorna a resposta estruturada em JSON.

    Usa httpx (HTTP/2) para comunicação assíncrona com streaming nativo.
    Se stream_callback for fornecido, cada token é emitido em tempo real.

    Args:
        prompt_usuario: Texto da solicitação do usuário.
        historico_contexto: Lista opcional de mensagens anteriores
            no formato [{"role": "...", "content": "..."}, ...].
        modelo: Nome do modelo Ollama a utilizar.
        base_url: URL base da API do Ollama.
        stream_callback: Callable que recebe cada token incremental
            durante o streaming (None = modo batch tradicional).

    Returns:
        Dicionário com os campos: raciocinio, acao, parametros, resposta_voz.
        Em caso de falha, retorna um JSON de fallback amigável.
    """
    _log(f"Processando prompt: '{prompt_usuario[:80]}{'...' if len(prompt_usuario) > 80 else ''}'")

    # 1. Verifica conectividade rapidamente
    online, _ = verificar_conexao_ollama(base_url)
    if not online:
        return dict(FALLBACK_OFFLINE)

    # 2. Constrói payload
    payload = _construir_payload(prompt_usuario, historico_contexto, modelo)

    # Sempre usa streaming — evita timeout de socket durante geração longa
    payload["stream"] = True

    url = f"{base_url}{OLLAMA_CHAT_PATH}"

    # 3. Envia requisição via httpx — SEMPRE em modo streaming
    #    (evita timeout de socket durante geração longa na CPU)
    try:
        inicio = time.time()

        resposta_bruta = ""
        headers = {"Content-Type": "application/json"}
        body_bytes = json.dumps(payload).encode("utf-8")
        with httpx.Client(timeout=HTTPX_TIMEOUT) as client:
            with client.stream("POST", url, content=body_bytes, headers=headers) as resp:
                resp.raise_for_status()
                for linha in resp.iter_lines():
                    if not linha:
                        continue
                    try:
                        chunk = json.loads(linha)
                    except json.JSONDecodeError:
                        continue

                    if chunk.get("done", False):
                        break

                    token = (
                        chunk.get("message", {}).get("content")
                        or chunk.get("response", "")
                    )
                    if token:
                        resposta_bruta += token
                        if stream_callback is not None:
                            stream_callback(token)

        duracao = time.time() - inicio
        _log(f"Resposta recebida em {duracao:.1f}s", "INFO")

    except httpx.ConnectError as exc:
        _log(f"Falha na comunicação com Ollama: {exc}", "ERROR")
        return dict(FALLBACK_OFFLINE)
    except httpx.TimeoutException:
        _log("Timeout aguardando resposta do Ollama.", "ERROR")
        return dict(FALLBACK_OFFLINE)
    except httpx.HTTPError as exc:
        _log(f"Erro HTTP do Ollama: {exc}", "ERROR")
        return dict(FALLBACK_OFFLINE)
    except Exception as exc:
        _log(f"Erro inesperado: {exc}", "ERROR")
        return dict(FALLBACK_OFFLINE)

    if not resposta_bruta or not resposta_bruta.strip():
        _log("Resposta do modelo veio vazia ou apenas whitespace.", "ERROR")
        return dict(FALLBACK_PARSE_ERROR)

    # 4. Extrai o JSON da resposta do modelo
    resultado = _extrair_json_resposta(resposta_bruta)

    # 5. Validação e normalização rigorosa
    resultado = _validar_resultado(resultado)

    _log(f"Ação decidida: {resultado.get('acao', '?')}", "INFO")
    return resultado


def pensar_streaming(
    prompt_usuario: str,
    stream_callback: Callable[[str], None],
    historico_contexto: Optional[list[dict]] = None,
    modelo: str = MODELO_PADRAO,
    base_url: str = OLLAMA_BASE_URL,
) -> dict:
    """
    Versão de streaming simplificada — alias para pensar() com callback.

    Retorna tokens em tempo real via stream_callback(token: str) enquanto
    o modelo ainda está gerando. Ao final, retorna o JSON completo.

    Args:
        prompt_usuario: Texto da solicitação do usuário.
        stream_callback: Callback que recebe cada token (palavra/fragmento)
            conforme o modelo gera.
        historico_contexto: Histórico opcional de conversa.
        modelo: Nome do modelo Ollama.
        base_url: URL base da API do Ollama.

    Returns:
        Dicionário JSON completo com raciocinio, acao, parametros, resposta_voz.
    """
    return pensar(
        prompt_usuario=prompt_usuario,
        historico_contexto=historico_contexto,
        modelo=modelo,
        base_url=base_url,
        stream_callback=stream_callback,
    )


def processar_prompt(
    texto: str,
    historico: list[dict] | None = None,
    modelo: str = MODELO_PADRAO,
) -> dict:
    """
    Wrapper robusto para pensar() que garante um dicionário com
    'resposta_voz' NUNCA vazio — compatível com a UI do launcher.

    Diferente de pensar(), esta função:
      - NÃO usa streaming (sem callback) — mais simples e confiável
      - Garante que 'resposta_voz' SEMPRE contenha texto utilizável
      - Pode ser chamada diretamente pela thread do chat da UI

    Returns:
        Dict com ao menos: {"resposta_voz": str, "acao": str, ...}
    """
    resultado = pensar(
        prompt_usuario=texto,
        historico_contexto=historico,
        modelo=modelo,
    )
    # Garantia extra: se resposta_voz veio vazia (bug raro), usa fallback
    if not resultado.get("resposta_voz", "").strip():
        resultado["resposta_voz"] = (
            "Estou online e operacional, senhor. Como posso ajudar?"
        )
        _log("processar_prompt: resposta_voz vazia — fallback aplicado.", "WARNING")
    return resultado


# ---------------------------------------------------------------------------
# Teste direto
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S — Teste do Brain v2.0 (Ollama)")
    print("=" * 60)

    # 1. Verificar conexão
    print("\n[1] Verificando conexão com Ollama...")
    online, modelo_ativo = verificar_conexao_ollama()
    if online and modelo_ativo:
        print(f"    Ollama online — modelo: {modelo_ativo}")
    elif online:
        print("    Ollama online, mas sem modelos disponíveis.")
    else:
        print("    Ollama OFFLINE — testes seguirão com fallback JSON.")

    # 2. Testar função pensar (modo online ou fallback)
    print("\n[2] Testando brain.pensar()...")
    prompts_teste = [
        "Liste os arquivos da pasta atual.",
        "Qual é a capital do Brasil?",
        "Delete todos os arquivos do sistema.",  # deve ser "negar"
        "Analise este código Python: query = 'SELECT * FROM users WHERE id = ' + user_input",
        "Faça um diagnóstico da rede atual.",
    ]
    for i, prompt in enumerate(prompts_teste, 1):
        print(f'\n--- Teste {i}: "{prompt}" ---')
        resultado = pensar(prompt)
        print(f"  raciocinio:   {resultado.get('raciocinio', '')[:120]}...")
        print(f"  acao:         {resultado.get('acao', '?')}")
        print(f"  parametros:   {json.dumps(resultado.get('parametros', {}), ensure_ascii=False)}")
        print(f"  resposta_voz: {resultado.get('resposta_voz', '')}")

    # 3. Validar ações conhecidas
    print("\n[3] Validando ações expandidas:")
    for acao in sorted(ACOES_VALIDAS):
        print(f"    ✓ {acao}")

    print("\n[BRAIN] Teste concluído.")
