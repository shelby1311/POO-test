"""
app.py — Orquestrador Principal do J.A.R.V.I.S.

Ponto de entrada do sistema. Coordena todos os módulos:
config, kill_switch, brain, pc_controller, web_learner e voice_engine.

Fluxo: Init → Loop (ouvir → pensar → agir → falar) → Cleanup.
"""

import sys
import time
import traceback

# ---------------------------------------------------------------------------
# Módulos do J.A.R.V.I.S.
# ---------------------------------------------------------------------------

import config_manager
import kill_switch
import brain
import pc_controller
import web_learner
import voice_engine

# ---------------------------------------------------------------------------
# Constantes do orquestrador
# ---------------------------------------------------------------------------

COMANDOS_SAIDA = ("sair", "desligar", "encerrar", "fechar", "exit", "quit")
TIMEOUT_VOZ = 5          # segundos de escuta por tentativa
TIMEOUT_TEXTO = 30       # fallback: tempo máximo aguardando input

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log(msg: str, nivel: str = "INFO") -> None:
    print(f"[JARVIS {nivel:<5}] {msg}", flush=True)


def _exibir_cabecalho() -> None:
    print()
    print("=" * 60)
    print("   J.A.R.V.I.S. — Just A Rather Very Intelligent System")
    print("=" * 60)
    print()


def _obter_comando_usuario() -> str:
    """
    Tenta obter o comando por voz. Se falhar (timeout/silêncio),
    oferece fallback por texto no terminal.
    """
    # Tenta voz primeiro
    comando = voice_engine.ouvir_microfone(
        timeout=TIMEOUT_VOZ,
        limite_fala=10,
    )
    if comando:
        return comando

    # Fallback: entrada de texto
    try:
        print()
        comando = input("[JARVIS] Digite seu comando (ou 'sair'): ").strip()
        return comando
    except (EOFError, KeyboardInterrupt):
        return "sair"


def _verificar_emergencia() -> bool:
    """Checa kill-switch; retorna True se deve continuar."""
    return kill_switch.verificar_interrupcao()


# ---------------------------------------------------------------------------
# Roteador de ações
# ---------------------------------------------------------------------------


def _executar_acao(resultado: dict) -> None:
    """
    Interpreta o JSON do cérebro e executa a ação correspondente.

    Campos esperados: acao, parametros, resposta_voz, raciocinio.
    """
    acao = resultado.get("acao", "falar")
    params = resultado.get("parametros", {})
    resposta = resultado.get("resposta_voz", "")
    raciocinio = resultado.get("raciocinio", "")

    if raciocinio:
        _log(f"Raciocinio: {raciocinio}", "DEBUG")

    _log(f"Acao decidida: {acao}")

    # --- Roteamento ---

    if acao == "pesquisar_web":
        _tratar_pesquisar_web(params, resposta)

    elif acao == "executar_cmd":
        _tratar_executar_cmd(params, resposta)

    elif acao == "abrir_app":
        _tratar_abrir_app(params, resposta)

    elif acao == "criar_arquivo":
        _tratar_criar_arquivo(params, resposta)

    elif acao == "gerar_codigo":
        _tratar_gerar_codigo(params, resposta)

    elif acao == "refatorar_codigo":
        _tratar_refatorar_codigo(params, resposta)

    elif acao == "analisar_codigo":
        _tratar_analisar_codigo(params, resposta)

    elif acao == "arquitetura":
        _tratar_arquitetura(params, resposta)

    elif acao == "diagnostico_windows":
        _tratar_diagnostico_windows(params, resposta)

    elif acao == "processar_video":
        _tratar_processar_video(params, resposta)

    elif acao == "cyber_defense":
        _tratar_cyber_defense(params, resposta)

    elif acao == "pentest_recon":
        _tratar_pentest_recon(params, resposta)

    elif acao == "pentest_scan":
        _tratar_pentest_scan(params, resposta)

    elif acao == "pentest_report":
        _tratar_pentest_report(params, resposta)

    elif acao == "negar":
        _log("Acao negada pelo cerebro (comando perigoso).", "WARNING")

    else:
        # "falar", "raciocinar", ou qualquer outra — só responde
        pass

    # --- Sempre pronuncia a resposta_voz ---
    if resposta:
        voice_engine.falar(resposta)
    elif acao == "negar":
        voice_engine.falar(
            "Receio que nao posso executar essa acao, senhor. "
            "Ela viola meus protocolos de seguranca."
        )


def _tratar_pesquisar_web(params: dict, resposta_padrao: str) -> None:
    """Executa pesquisa web e consulta memória."""
    query = params.get("query") or params.get("url") or params.get("topico", "")
    if not query:
        voice_engine.falar("Sobre qual topico devo pesquisar, senhor?")
        query = _obter_comando_usuario()
        if not query or query.lower() in COMANDOS_SAIDA:
            return

    _log(f"Pesquisando na web: '{query}'")
    voice_engine.falar(f"Pesquisando sobre {query}, senhor. Um momento.")

    # Aprende (raspa + chunk + armazena)
    n_chunks = web_learner.pesquisar_e_aprender(query, max_paginas=2)

    if n_chunks > 0:
        # Consulta a memória recém-preenchida
        memoria = web_learner.consultar_memoria(query, n_resultados=3)
        if memoria:
            contexto = "\n".join(
                f"- {m['texto'][:300]}" for m in memoria
            )
            _log(f"Contexto recuperado da memoria:\n{contexto}", "DEBUG")

        voice_engine.falar(
            f"Pesquisa concluida, senhor. Aprendi {n_chunks} "
            f"fragmentos sobre {query}."
        )
    else:
        voice_engine.falar(
            "Nao consegui acessar a web no momento, senhor. "
            "Verifique sua conexao de rede."
        )


def _tratar_executar_cmd(params: dict, resposta_padrao: str) -> None:
    """Executa comando no terminal."""
    comando = params.get("comando", "")
    if not comando:
        voice_engine.falar("Qual comando devo executar, senhor?")
        return

    _log(f"Executando comando: {comando}")
    sucesso, stdout, stderr = pc_controller.executar_comando_cmd(comando)

    if sucesso:
        if stdout:
            _log(f"Saida: {stdout[:500]}")
            # Se a saída for curta, fala ela
            if len(stdout) < 200:
                voice_engine.falar(f"Comando executado. Resultado: {stdout}")
            else:
                voice_engine.falar("Comando executado com sucesso, senhor.")
        else:
            voice_engine.falar("Comando executado com sucesso, senhor.")
    else:
        _log(f"Erro: {stderr[:200]}", "ERROR")
        voice_engine.falar(f"O comando falhou, senhor. {stderr[:150]}")


def _tratar_abrir_app(params: dict, resposta_padrao: str) -> None:
    """Abre um aplicativo/programa."""
    app = params.get("app") or params.get("programa") or params.get("comando", "")
    if not app:
        voice_engine.falar("Qual aplicativo devo abrir, senhor?")
        return

    _log(f"Abrindo aplicativo: {app}")
    ok = pc_controller.abrir_aplicativo(app)
    if ok:
        voice_engine.falar(f"{app} aberto, senhor.")
    else:
        voice_engine.falar(f"Nao consegui abrir {app}, senhor.")


def _tratar_criar_arquivo(params: dict, resposta_padrao: str) -> None:
    """Cria/edita um arquivo em disco."""
    arquivo = params.get("arquivo", "")
    conteudo = params.get("conteudo", "")
    if not arquivo:
        voice_engine.falar("Qual o nome do arquivo, senhor?")
        return

    try:
        with open(arquivo, "w", encoding="utf-8") as f:
            f.write(conteudo)
        _log(f"Arquivo criado: {arquivo}")
        voice_engine.falar(f"Arquivo {arquivo} criado, senhor.")
    except OSError as exc:
        _log(f"Falha ao criar arquivo: {exc}", "ERROR")
        voice_engine.falar(f"Nao consegui criar o arquivo, senhor. {exc}")


def _tratar_gerar_codigo(params: dict, resposta_padrao: str) -> None:
    """Exibe código gerado com opção de salvar."""
    codigo = params.get("codigo", "")
    linguagem = params.get("linguagem", "desconhecida")
    if not codigo:
        voice_engine.falar("Nenhum código foi gerado, senhor.")
        return
    _log(f"Código {linguagem} gerado: {len(codigo)} caracteres")
    print(f"\n{'─' * 50}")
    print(codigo[:2000])
    if len(codigo) > 2000:
        print(f"... ({len(codigo) - 2000} caracteres restantes)")
    print(f"{'─' * 50}\n")


def _tratar_refatorar_codigo(params: dict, resposta_padrao: str) -> None:
    """Exibe código refatorado."""
    codigo = params.get("codigo", "")
    linguagem = params.get("linguagem", "desconhecida")
    objetivo = params.get("objetivo", "melhoria geral")
    if not codigo:
        voice_engine.falar("Nenhum código refatorado foi gerado, senhor.")
        return
    _log(f"Código refatorado ({linguagem}, objetivo={objetivo}): {len(codigo)} caracteres")
    print(f"\n{'─' * 50}")
    print(codigo[:2000])
    if len(codigo) > 2000:
        print(f"... ({len(codigo) - 2000} caracteres restantes)")
    print(f"{'─' * 50}\n")


def _tratar_arquitetura(params: dict, resposta_padrao: str) -> None:
    """Exibe recomendações de arquitetura."""
    problema = params.get("problema", "")
    padrao = params.get("padrao", "")
    recomendacao = params.get("recomendacao", "")
    _log(f"Análise de arquitetura — pattern: {padrao or 'não especificado'}")
    if recomendacao:
        print(f"\n{'─' * 50}")
        print(f"📐 ARQUITETURA: {padrao}" if padrao else "📐 ARQUITETURA")
        print(f"{'─' * 50}")
        print(recomendacao[:2000])
        print(f"{'─' * 50}\n")


def _tratar_analisar_codigo(params: dict, resposta_padrao: str) -> None:
    """Exibe resultado da analise de seguranca de codigo."""
    codigo = params.get("codigo", "")
    linguagem = params.get("linguagem", "desconhecida")
    if not codigo:
        voice_engine.falar("Qual codigo devo analisar, senhor?")
        return

    _log(f"Analisando codigo {linguagem} ({len(codigo)} caracteres)...")
    # O raciocinio ja contem a analise completa do cerebro
    # A resposta_voz ja foi pronunciada pelo fluxo principal
    _log(
        f"Analise de seguranca concluida. Verifique o raciocinio para "
        f"detalhes das vulnerabilidades."
    )


def _tratar_diagnostico_windows(params: dict, resposta_padrao: str) -> None:
    """Executa diagnostico do Windows (rede, processos, servicos, registro)."""
    tipo = params.get("tipo", "rede")

    _log(f"Executando diagnostico do Windows [{tipo}]...")

    comandos = {
        "rede": [
            ("ipconfig /all", "Configuracao de rede"),
            ("ping -n 2 8.8.8.8", "Conectividade externa"),
        ],
        "processos": [
            ("tasklist /FI \"STATUS eq RUNNING\" 2>nul", "Processos ativos"),
        ],
        "servicos": [
            ("sc query state= all 2>nul | findstr /C:\"SERVICE_NAME\" /C:\"STATE\"", "Servicos Windows"),
        ],
        "registro": [
            ("reg query \"HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\" /s 2>nul | findstr DisplayName", "Programas instalados"),
        ],
    }

    comandos_executar = comandos.get(tipo, comandos["rede"])

    for cmd, descricao in comandos_executar[:2]:
        _log(f"  [{descricao}] Executando...")
        sucesso, stdout, stderr = pc_controller.executar_comando_cmd(cmd)
        if sucesso and stdout:
            _log(f"  [{descricao}] OK ({len(stdout)} bytes)")
        else:
            _log(f"  [{descricao}] FALHA: {stderr[:100]}")

    # A resposta_voz ja foi pronunciada pelo fluxo principal
    _log("Diagnostico concluido.")


def _tratar_processar_video(params: dict, resposta_padrao: str) -> None:
    """Processa video para aprendizado de padroes linguisticos."""
    url = params.get("url", "")
    caminho = params.get("caminho", "")

    if not url and not caminho:
        voice_engine.falar("Qual video devo processar, senhor?")
        return

    _log(f"Processando video para aprendizado: {url or caminho}")

    try:
        n_chunks, padroes = web_learner.processar_video_para_aprendizado(
            url=url or None,
            caminho=caminho or None,
        )

        if n_chunks > 0:
            categorias = [k for k, v in padroes.items() if v and k != "estatisticas"]
            _log(
                f"Video processado: {n_chunks} fragmentos, "
                f"{len(categorias)} padroes detectados."
            )
            voice_engine.falar(
                f"Video processado, senhor. Aprendi {n_chunks} fragmentos "
                f"e detectei {len(categorias)} padroes comunicativos."
            )
        else:
            _log("Nao foi possivel extrair transcricao do video.", "WARNING")
            voice_engine.falar(
                "Nao consegui extrair a transcricao deste video, senhor."
            )
    except Exception as exc:
        _log(f"Erro ao processar video: {exc}", "ERROR")
        voice_engine.falar(
            "Houve um erro ao processar o video, senhor."
        )


def _tratar_cyber_defense(params: dict, resposta_padrao: str) -> None:
    """Executa scan de defesa cibernética completo."""
    try:
        import cyber_defense
    except ImportError:
        _log("Módulo cyber_defense indisponível.", "ERROR")
        voice_engine.falar(
            "Módulo de defesa cibernética indisponível, senhor."
        )
        return

    target_ip = params.get("target_ip") or params.get("ip", "")
    _log("Executando Cyber Defense Shield scan completo...")

    try:
        report = cyber_defense.generate_defense_report(
            target_ip=target_ip if target_ip else None
        )
        summary = report.get("executive_summary", {})

        _log(f"Cyber Defense: {summary.get('status', 'N/A')}")
        voice_engine.falar(
            f"Scan de defesa concluído, senhor. "
            f"{summary.get('status', 'Sistema verificado')}."
        )
    except Exception as exc:
        _log(f"Erro no Cyber Defense: {exc}", "ERROR")
        voice_engine.falar(
            "Houve um erro ao executar o scan de defesa, senhor."
        )


# ---------------------------------------------------------------------------
# Inicialização do sistema
# ---------------------------------------------------------------------------


def inicializar() -> bool:
    """
    Prepara todo o ambiente do J.A.R.V.I.S.
    Retorna True se OK, False se algo crítico falhou.
    """
    _exibir_cabecalho()

    # 1. Ambiente de diretórios
    _log("Preparando ambiente de diretorios...")
    if not config_manager.validar_e_preparar_ambiente():
        _log("FALHA ao preparar ambiente!", "ERROR")
        return False
    _log("Ambiente OK.")

    # 2. Kill-Switch (trava de emergência)
    _log("Ativando trava de emergencia...")
    kill_switch.iniciar_monitoramento()
    _log("Kill-Switch ativo.")

    # 3. Garantir que o Ollama está rodando (inicia em segundo plano se necessário)
    _log("Garantindo servico do Ollama...")
    ollama_online = brain.garantir_servico_ollama()
    if ollama_online:
        online, modelo = brain.verificar_conexao_ollama()
        if modelo:
            _log(f"Ollama online. Modelo: {modelo}")
        else:
            _log("Ollama online, mas sem modelos carregados.", "WARNING")
    else:
        _log("Ollama OFFLINE. Usando fallback JSON para respostas.", "WARNING")

    # 4. Mensagem de boas-vindas
    stats_mem = web_learner.estatisticas_memoria()
    chunks_mem = stats_mem.get("total_chunks", 0)

    mensagem_boas_vindas = (
        "Sistemas J.A.R.V.I.S online e operacionais, senhor. "
        f"Memoria com {chunks_mem} fragmentos indexados. "
        "Estou ouvindo."
    )
    voice_engine.falar(mensagem_boas_vindas)

    return True


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------


def loop_principal() -> None:
    """
    Loop principal de atendimento: ouvir → pensar → agir → falar.
    """
    _log("Entrando no loop principal.", "INFO")

    while True:
        # Verifica kill-switch antes de cada iteração
        if not _verificar_emergencia():
            _log("Kill-switch: usuario cancelou a execucao.", "WARNING")
            break

        # 1. Obter comando do usuário
        print()
        comando = _obter_comando_usuario()

        if not comando:
            continue

        _log(f"Comando recebido: '{comando[:120]}'")

        # 2. Verificar comandos de saída
        if comando.lower() in COMANDOS_SAIDA:
            _log("Comando de saida detectado.", "INFO")
            break

        # 3. Enviar ao cérebro
        try:
            resultado = brain.pensar(comando)
        except Exception as exc:
            _log(f"Erro no brain.pensar(): {exc}", "ERROR")
            traceback.print_exc()
            voice_engine.falar(
                "Meu nucleo de IA encontrou um erro, senhor. "
                "Podemos tentar novamente?"
            )
            continue

        # 4. Executar ação
        try:
            _executar_acao(resultado)
        except Exception as exc:
            _log(f"Erro ao executar acao: {exc}", "ERROR")
            traceback.print_exc()
            voice_engine.falar(
                "Houve uma falha ao executar a acao, senhor."
            )

        # 5. Verificar kill-switch pós-ação
        if not _verificar_emergencia():
            _log("Kill-switch acionado apos acao.", "WARNING")
            break


# ---------------------------------------------------------------------------
# Encerramento
# ---------------------------------------------------------------------------


def encerrar() -> None:
    """Desliga o sistema de forma segura."""
    print()
    _log("Encerrando J.A.R.V.I.S....")

    voice_engine.falar("Desligando sistemas. Ate logo, senhor.")

    kill_switch.parar_monitoramento()

    # Encerra o processo do Ollama se tiver sido iniciado pelo J.A.R.V.I.S.
    brain.encerrar_ollama()

    _log("J.A.R.V.I.S. encerrado. Bom trabalho, senhor.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        if inicializar():
            loop_principal()
    except KeyboardInterrupt:
        print("\n")
        _log("Interrompido pelo usuario (Ctrl+C).", "WARNING")
    except Exception as exc:
        _log(f"Erro fatal: {exc}", "ERROR")
        traceback.print_exc()
    finally:
        encerrar()
        sys.exit(0)
