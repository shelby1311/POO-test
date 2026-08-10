"""
kill_switch.py — Trava de Emergência do J.A.R.V.I.S.

Monitora teclado e mouse em segundo plano. Aciona uma flag global de parada
emergencial quando o usuário pressiona a hotkey configurada ou move o mouse
bruscamente (>60 px em um único evento).

Oferece funções para verificação periódica durante tarefas automatizadas,
permitindo pausar, retomar ou cancelar a execução.
"""

import sys
import threading
import time
import math
from typing import Optional

from pynput import keyboard, mouse

from config_manager import carregar_configuracao

# ---------------------------------------------------------------------------
# Estado global (thread-safe)
# ---------------------------------------------------------------------------

# Evento que sinaliza parada emergencial — setado = emergência ativa
_emergency_stop = threading.Event()

# Lock para proteger o acesso ao motivo do acionamento
_lock = threading.Lock()
_motivo_acionamento: Optional[str] = None


# ---------------------------------------------------------------------------
# Mapeamento: string de config → pynput Key
# ---------------------------------------------------------------------------

_TECLA_MAP: dict[str, keyboard.Key] = {
    "esc": keyboard.Key.esc,
    "escape": keyboard.Key.esc,
    "tab": keyboard.Key.tab,
    "caps_lock": keyboard.Key.caps_lock,
    "shift": keyboard.Key.shift,
    "ctrl": keyboard.Key.ctrl,
    "alt": keyboard.Key.alt,
    "enter": keyboard.Key.enter,
    "space": keyboard.Key.space,
    "backspace": keyboard.Key.backspace,
    "delete": keyboard.Key.delete,
    "insert": keyboard.Key.insert,
    "home": keyboard.Key.home,
    "end": keyboard.Key.end,
    "page_up": keyboard.Key.page_up,
    "page_down": keyboard.Key.page_down,
    "up": keyboard.Key.up,
    "down": keyboard.Key.down,
    "left": keyboard.Key.left,
    "right": keyboard.Key.right,
    "f1": keyboard.Key.f1,
    "f2": keyboard.Key.f2,
    "f3": keyboard.Key.f3,
    "f4": keyboard.Key.f4,
    "f5": keyboard.Key.f5,
    "f6": keyboard.Key.f6,
    "f7": keyboard.Key.f7,
    "f8": keyboard.Key.f8,
    "f9": keyboard.Key.f9,
    "f10": keyboard.Key.f10,
    "f11": keyboard.Key.f11,
    "f12": keyboard.Key.f12,
    "print_screen": keyboard.Key.print_screen,
    "scroll_lock": keyboard.Key.scroll_lock,
    "pause": keyboard.Key.pause,
    "media_volume_up": keyboard.Key.media_volume_up,
    "media_volume_down": keyboard.Key.media_volume_down,
    "media_volume_mute": keyboard.Key.media_volume_mute,
    "media_play_pause": keyboard.Key.media_play_pause,
}


def _resolver_tecla(nome: str):
    """Converte o nome da tecla (string) para pynput Key ou caractere."""
    nome_lower = nome.lower().strip()
    if nome_lower in _TECLA_MAP:
        return _TECLA_MAP[nome_lower]
    # Caractere simples (ex: 'a', '1')
    if len(nome_lower) == 1:
        return keyboard.KeyCode.from_char(nome_lower)
    return None


# ---------------------------------------------------------------------------
# Listeners (teclado e mouse)
# ---------------------------------------------------------------------------

# Guardamos referências para poder parar depois
_teclado_listener: Optional[keyboard.Listener] = None
_mouse_listener: Optional[mouse.Listener] = None

# Última posição do mouse para cálculo de delta
_ultimo_x = 0
_ultimo_y = 0
_pos_lock = threading.Lock()


def _on_press(tecla_alvo, key) -> None:
    """Callback do listener de teclado: compara com a hotkey configurada."""
    # Normaliza KeyCode para char, mantém Key especial como é
    tecla_pressionada = key
    if hasattr(key, "char") and key.char is not None:
        tecla_pressionada = key.char

    alvo = tecla_alvo
    # Se o alvo for KeyCode, normaliza também
    if hasattr(tecla_alvo, "char") and tecla_alvo.char is not None:
        alvo = tecla_alvo.char

    if tecla_pressionada == alvo:
        _acionar("hotkey")


def _on_move(limiar_px: int, x: int, y: int) -> None:
    """Callback do listener de mouse: detecta movimento brusco."""
    global _ultimo_x, _ultimo_y
    with _pos_lock:
        dx = x - _ultimo_x
        dy = y - _ultimo_y
        _ultimo_x = x
        _ultimo_y = y

    distancia = math.hypot(dx, dy)
    if distancia > limiar_px:
        _acionar(f"mouse (delta={distancia:.0f} px)")


def _acionar(motivo: str) -> None:
    """Marca a trava de emergência como ativa."""
    with _lock:
        if not _emergency_stop.is_set():
            _emergency_stop.set()
            _motivo_acionamento = motivo  # type: ignore[assignment]  # usado em lambda
    print(
        f"\n[KILL-SWITCH] TRAVA DE EMERGÊNCIA ACIONADA! Motivo: {motivo}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def verificar_interrupcao() -> bool:
    """
    Deve ser chamada periodicamente durante loops de tarefas automatizadas.

    Se a trava de emergência estiver ativa, congela a execução e solicita
    ao usuário que escolha entre retomar ou cancelar.

    Retorna:
        True  → continuar execução (usuário escolheu retomar)
        False → cancelar execução (usuário escolheu cancelar)
    """
    if not _emergency_stop.is_set():
        return True  # Nenhuma interrupção, segue o baile

    with _lock:
        motivo = _motivo_acionamento or "desconhecido"

    print("\n" + "=" * 60)
    print("  ⚠️  J.A.R.V.I.S — TRAVA DE EMERGÊNCIA  ⚠️")
    print(f"  Motivo do acionamento: {motivo}")
    print("=" * 60)

    while True:
        try:
            resposta = input(
                "  Digite [R] para RETOMAR ou [C] para CANCELAR: "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[KILL-SWITCH] Cancelando por interrupção do terminal.")
            return False

        if resposta in ("r", "retomar"):
            _emergency_stop.clear()
            with _lock:
                _motivo_acionamento = None  # type: ignore[assignment]
            print("[KILL-SWITCH] Retomando execução...\n")
            return True
        elif resposta in ("c", "cancelar"):
            print("[KILL-SWITCH] Cancelando tarefa. Voltando ao controle manual.\n")
            return False
        else:
            print("  Opção inválida. Digite 'R' ou 'C'.")


def iniciar_monitoramento(
    hotkey: Optional[str] = None,
    limiar_mouse_px: int = 60,
) -> None:
    """
    Inicia os listeners de teclado e mouse em threads daemon.

    Args:
        hotkey: Nome da tecla de atalho. Se None, usa o valor de config.json.
        limiar_mouse_px: Variação mínima (px) para acionar pelo mouse.
    """
    global _teclado_listener, _mouse_listener

    if _teclado_listener is not None or _mouse_listener is not None:
        print("[KILL-SWITCH] Monitoramento já está ativo.")
        return

    # Resolve hotkey
    if hotkey is None:
        config = carregar_configuracao()
        hotkey = config.get("hotkey_pause", "esc")

    tecla = _resolver_tecla(hotkey)
    if tecla is None:
        print(
            f"[KILL-SWITCH] ERRO: tecla '{hotkey}' não reconhecida. "
            f"Usando 'esc' como fallback."
        )
        tecla = keyboard.Key.esc

    # Reset do estado
    _emergency_stop.clear()
    with _lock:
        _motivo_acionamento = None  # type: ignore[assignment]
    with _pos_lock:
        global _ultimo_x, _ultimo_y
        _ultimo_x = 0
        _ultimo_y = 0

    # Listener de teclado
    _teclado_listener = keyboard.Listener(
        on_press=lambda key: _on_press(tecla, key)
    )
    _teclado_listener.daemon = True
    _teclado_listener.start()

    # Listener de mouse
    _mouse_listener = mouse.Listener(
        on_move=lambda x, y: _on_move(limiar_mouse_px, x, y)
    )
    _mouse_listener.daemon = True
    _mouse_listener.start()

    print(
        f"[KILL-SWITCH] Monitoramento iniciado. "
        f"Hotkey: '{hotkey}' | Limiar mouse: {limiar_mouse_px} px"
    )


def parar_monitoramento() -> None:
    """Encerra os listeners de teclado e mouse."""
    global _teclado_listener, _mouse_listener

    if _teclado_listener is not None:
        _teclado_listener.stop()
        _teclado_listener = None

    if _mouse_listener is not None:
        _mouse_listener.stop()
        _mouse_listener = None

    _emergency_stop.clear()
    print("[KILL-SWITCH] Monitoramento encerrado.")


def esta_acionado() -> bool:
    """Retorna True se a trava de emergência estiver ativa (uso externo)."""
    return _emergency_stop.is_set()


# ---------------------------------------------------------------------------
# Teste direto
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(" J.A.R.V.I.S — Teste do Kill-Switch")
    print("=" * 60)
    print()
    print("Instruções:")
    print(f"  - Pressione a hotkey configurada para acionar a trava.")
    print("  - Mova o mouse rapidamente (>60 px) para acionar a trava.")
    print("  - O monitoramento ficará ativo por 10 segundos.")
    print()

    iniciar_monitoramento()

    # Simula um loop de tarefa que verifica interrupção periodicamente
    inicio = time.time()
    try:
        while time.time() - inicio < 10:
            if not verificar_interrupcao():
                print("[TESTE] Tarefa cancelada pelo usuário.")
                break
            # Simula trabalho
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[TESTE] Interrompido pelo terminal.")
    finally:
        parar_monitoramento()

    print("[TESTE] Fim do teste.")
