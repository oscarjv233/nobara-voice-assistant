#!/usr/bin/env python3
"""
Agent runner for Nobara AI Voice Assistant.
Executes Antigravity CLI (agy) with live streaming, real-time status tracking,
conversation continuity, intent detection, and KDE Plasma 6 Wayland display support.
"""
import sys
import os
import json
import time
import re
import signal
import subprocess

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(PROJECT_DIR, "config", "config.env")
LIVE_STATUS_FILE = "/tmp/nobara_assistant_live.json"
PID_FILE = "/tmp/nobara_assistant_agent.pid"

RESET_KEYWORDS = [
    # Spanish keywords
    r"^nueva conversaci[oó]n",
    r"^nuevo tema",
    r"^reinicia(?:r)? (?:la )?conversaci[oó]n",
    r"^reinicia(?:r)? (?:el )?contexto",
    r"^empezar de cero",
    r"^empecemos de cero",
    r"^olvida lo anterior",
    r"^olvida la conversaci[oó]n",
    r"^limpia(?:r)? (?:el )?contexto",
    r"^limpia(?:r)? (?:la )?conversaci[oó]n",
    # English keywords
    r"^new conversation",
    r"^new topic",
    r"^reset conversation",
    r"^reset (?:the )?context",
    r"^start over",
    r"^start from scratch",
    r"^forget (?:the )?previous",
    r"^forget everything",
    r"^clear (?:the )?context",
    r"^clear (?:the )?conversation"
]

def load_config():
    config = {
        "ENABLED": "true",
        "WHISPER_MODEL": "base",
        "ENABLE_VOICE_REPLY": "true",
        "VOICE_MODEL": "es_ES-davefx-medium.onnx",
        "VOICE_SPEAKER": "",
        "TTS_VOLUME": "0.35",
        "ENABLE_PROCESSING_VOICE_CUE": "true",
        "RESULT_NOTIF_TIMEOUT": "15000",
        "AGY_BIN": os.path.expanduser("~/.local/bin/agy"),
        "CONTINUOUS_CONVERSATION": "true",
        "ACTIVE_CONVERSATION_ID": "",
        "ASSISTANT_LANGUAGE": "es"
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    config[key.strip()] = val.strip().strip('"').strip("'")
    return config

def update_config_value(key: str, value: str):
    """Update or insert a key in config.env safely."""
    lines = []
    found = False
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith(f"{key}="):
                    lines.append(f'{key}="{value}"\n')
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f'{key}="{value}"\n')
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

def update_live_status(status_dict):
    """Write current execution state to status JSON file."""
    try:
        with open(LIVE_STATUS_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(status_dict, f, ensure_ascii=False, indent=2)
        os.replace(LIVE_STATUS_FILE + ".tmp", LIVE_STATUS_FILE)
    except Exception:
        pass

def update_desktop_notif(notif_id: str, title: str, body: str, icon: str = "system-run"):
    """Update active notification in place using notify-send -r."""
    if not notif_id:
        return
    try:
        subprocess.run(
            ["notify-send", "-r", str(notif_id), "-a", "AI Voice Assistant", "-i", icon, "-t", "0", title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )
    except Exception:
        pass

def check_reset_intent(text: str):
    """
    Check if user wants to reset or start a new conversation.
    Returns (is_pure_reset, remaining_text).
    """
    clean = text.strip()
    for pat in RESET_KEYWORDS:
        m = re.search(pat, clean, re.IGNORECASE)
        if m:
            matched_span = m.span()
            # If the entire text or almost entire text is the reset keyword
            remainder = clean[matched_span[1]:].strip()
            # remove leading separators like ":", ",", "-", "y"
            remainder = re.sub(r'^[,\-:yY\s]+', '', remainder).strip()
            if not remainder:
                return True, ""
            else:
                return False, remainder
    return False, clean

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run AGY agent turn with live feedback")
    parser.add_argument("--text", required=True, help="Transcribed voice text")
    parser.add_argument("--notif-id", default="", help="Notification ID to update")
    parser.add_argument("--force-new", action="store_true", help="Force starting a new conversation")
    args = parser.parse_args()

    raw_text = args.text.strip()
    notif_id = args.notif_id
    config = load_config()
    lang = config.get("ASSISTANT_LANGUAGE", "es").lower()

    is_pure_reset, clean_text = check_reset_intent(raw_text)

    # 1. Pure reset intent: user just said "nueva conversación" or "new conversation"
    if is_pure_reset:
        update_config_value("ACTIVE_CONVERSATION_ID", "")
        reset_msg = "Context reset. Started a new conversation." if lang == "en" else "Contexto reiniciado. He iniciado una nueva conversación."
        update_live_status({
            "status": "IDLE",
            "last_action": "Context reset" if lang == "en" else "Contexto reiniciado",
            "last_response": reset_msg,
            "updated_at": time.time()
        })
        print(reset_msg)
        return

    # If it was a hybrid reset like "nueva conversación: búscame tal archivo"
    if clean_text != raw_text:
        update_config_value("ACTIVE_CONVERSATION_ID", "")
        config["ACTIVE_CONVERSATION_ID"] = ""

    if args.force_new:
        update_config_value("ACTIVE_CONVERSATION_ID", "")
        config["ACTIVE_CONVERSATION_ID"] = ""

    continuous = config.get("CONTINUOUS_CONVERSATION", "true").lower() == "true"
    active_conv_id = config.get("ACTIVE_CONVERSATION_ID", "").strip()

    brain_dir = os.path.expanduser("~/.gemini/antigravity-cli/brain")
    if active_conv_id and not os.path.isdir(os.path.join(brain_dir, active_conv_id)):
        active_conv_id = ""
        update_config_value("ACTIVE_CONVERSATION_ID", "")

    # Build AGY command
    raw_agy = config.get("AGY_BIN", "~/.local/bin/agy")
    agy_bin = os.path.expandvars(os.path.expanduser(raw_agy))
    cmd = [agy_bin, "--dangerously-skip-permissions", "--output-format", "stream-json"]

    if continuous and active_conv_id:
        cmd.extend(["--conversation", active_conv_id])

    # Craft the clear, bulletproof prompt with strict KDE Plasma 6 Wayland visual rules
    if lang == "en":
        prompt = (
            f"User voice instruction on Nobara Linux (KDE Plasma 6 / Wayland): '{clean_text}'.\n"
            "MANDATORY RULES:\n"
            "1. SCREEN VISIBILITY: If the user asks to see, show, open programs, terminals or graphical info, "
            "open VISIBLE windows on their main desktop using DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 kstart -- <command>. "
            "If it's an interactive terminal command (e.g. htop, btop, logs, system stats), open a VISIBLE separate Konsole: "
            "DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 kstart -- konsole --separate -e bash -c \"<command>; echo ''; read -p 'Press Enter to close...'\"\n"
            "NEVER leave graphical apps running hidden in the background.\n"
            "2. SYSTEM ACTIONS: If the user asks for background actions (volume, music pause, querying RAM/CPU stats for speech), execute directly with bash without opening unnecessary windows.\n"
            "3. LANGUAGE & CONCISENESS: Respond STRICTLY in English. Keep your response very concise and direct (maximum 1 or 2 sentences) as it will be read aloud by TTS and shown in a notification."
        )
    else:
        prompt = (
            f"Instrucción de voz del usuario en Nobara Linux (KDE Plasma 6 / Wayland): '{clean_text}'.\n"
            "REGLAS OBLIGATORIAS:\n"
            "1. VISUALIZACIÓN EN PANTALLA: Si el usuario pide ver, mostrar, abrir programas, terminales o información gráfica, "
            "abre ventanas VISIBLES en su escritorio principal con DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 kstart -- <comando>. "
            "Si es un comando de consola que el usuario quiere ver en directo (ej. htop, btop, logs, monitores), abre un terminal de Konsole VISIBLE e independiente: "
            "DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 kstart -- konsole --separate -e bash -c \"<comando>; echo ''; read -p 'Presiona Enter para cerrar...'\"\n"
            "NUNCA dejes aplicaciones gráficas en segundo plano ocultas.\n"
            "2. ACCIONES DEL SISTEMA: Si pide cambiar volumen, pausar, o consultar datos para voz, ejecútalo directamente con bash sin abrir ventanas.\n"
            "3. RESPUESTA: Responde ESTRICTAMENTE en español. Responde de forma muy concisa y directa (máximo 1 o 2 frases) ya que tu respuesta se leerá por voz y en notificación."
        )
    cmd.extend(["-p", prompt])

    # Ensure Wayland / Xwayland graphical environment
    env = os.environ.copy()
    env["DISPLAY"] = env.get("DISPLAY", ":0")
    env["WAYLAND_DISPLAY"] = env.get("WAYLAND_DISPLAY", "wayland-0")
    env["XDG_CURRENT_DESKTOP"] = "KDE"
    env["KDE_FULL_SESSION"] = "true"
    user_home = os.path.expanduser("~")
    env["PATH"] = f"{user_home}/.gemini/antigravity-cli/bin:{user_home}/.local/bin:/usr/local/bin:/usr/bin:/bin:{env.get('PATH', '')}"

    start_time = time.time()
    initial_action = "🧠 Analyzing instruction..." if lang == "en" else "🧠 Analizando orden..."
    live_state = {
        "status": "RUNNING",
        "pid": os.getpid(),
        "started_at": start_time,
        "user_text": clean_text,
        "conversation_id": active_conv_id or ("Starting new..." if lang == "en" else "Iniciando nueva..."),
        "current_action": initial_action,
        "tool_name": "",
        "tool_detail": "",
        "logs": [f"[{time.strftime('%H:%M:%S')}] {'Input' if lang == 'en' else 'Transcripción'}: '{clean_text}'"]
    }
    update_live_status(live_state)

    if notif_id:
        p_title = "🧠 Processing..." if lang == "en" else "🧠 Procesando..."
        p_desc = f"Analyzing: {clean_text[:40]}..." if lang == "en" else f"Interpretando: {clean_text[:40]}..."
        update_desktop_notif(notif_id, p_title, p_desc)

    final_response = ""
    assigned_conv_id = active_conv_id

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env
        )

        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))

        live_state["pid"] = proc.pid
        update_live_status(live_state)

        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue

            event = data.get("event")

            if event == "init":
                assigned_conv_id = data.get("conversation_id", "")
                if continuous and assigned_conv_id:
                    update_config_value("ACTIVE_CONVERSATION_ID", assigned_conv_id)
                live_state["conversation_id"] = assigned_conv_id
                live_state["logs"].append(f"[{time.strftime('%H:%M:%S')}] {'Session connected' if lang == 'en' else 'Sesión conectada'}: {assigned_conv_id[:8]}...")
                update_live_status(live_state)

            elif event == "step_update":
                step_data = data.get("step_update", {})
                stype = step_data.get("step_type")
                state = step_data.get("state")

                if stype == "tool" and state == "ACTIVE":
                    tname = step_data.get("tool_name", "herramienta")
                    tinfo = step_data.get("tool_info", {})
                    params = tinfo.get("parameters", {}) if isinstance(tinfo, dict) else {}
                    cmd_line = params.get("CommandLine", "") if isinstance(params, dict) else ""
                    action_summary = params.get("toolSummary", "") if isinstance(params, dict) else ""

                    if cmd_line:
                        display_action = f"{'Executing' if lang == 'en' else 'Ejecutando'}: {cmd_line[:50]}"
                    elif action_summary:
                        display_action = f"{'Action' if lang == 'en' else 'Acción'}: {action_summary}"
                    else:
                        display_action = f"{'Using' if lang == 'en' else 'Usando'} {tname}"

                    live_state["current_action"] = display_action
                    live_state["tool_name"] = tname
                    live_state["tool_detail"] = cmd_line or action_summary
                    live_state["logs"].append(f"[{time.strftime('%H:%M:%S')}] ⚙️ {display_action}")
                    update_live_status(live_state)

                    if notif_id:
                        e_title = "⚙️ Executing..." if lang == "en" else "⚙️ Ejecutando..."
                        update_desktop_notif(notif_id, e_title, display_action, icon="system-run")

                elif stype == "agent_response" and state == "ACTIVE":
                    live_state["current_action"] = "Generating response..." if lang == "en" else "Generando respuesta..."
                    update_live_status(live_state)

            elif event == "result":
                res = data.get("result", {})
                final_response = res.get("response", "").strip()

        proc.wait()

    except Exception as e:
        final_response = f"Error: {e}" if lang == "en" else f"Error al procesar la instrucción: {e}"
    finally:
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass

        # Cleanup internal logs/warnings if any leaked
        cleaned = []
        for l in final_response.splitlines():
            l_strip = l.strip()
            if "warning: --mode auto" in l_strip or "jetski:" in l_strip:
                continue
            cleaned.append(l)
        final_response = "\n".join(cleaned).strip()

        if not final_response:
            final_response = "Order completed." if lang == "en" else "Orden completada."

        elapsed = round(time.time() - start_time, 1)
        update_live_status({
            "status": "IDLE",
            "last_action": f"Completado en {elapsed}s",
            "last_response": final_response,
            "last_user_text": clean_text,
            "conversation_id": assigned_conv_id,
            "completed_at": time.time()
        })

    print(final_response)

if __name__ == "__main__":
    main()
