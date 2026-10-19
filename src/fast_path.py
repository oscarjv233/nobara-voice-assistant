#!/usr/bin/env python3
"""
Nobara AI Voice Assistant - Fast Path Multimedia & System Controller.
Executes common multimedia, volume, and system actions in <30ms locally
via PipeWire (wpctl) and KDE Plasma MPRIS (qdbus / playerctl),
bypassing the cloud LLM entirely for instant sub-second response.
"""
import sys
import os
import re
import json
import subprocess

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.5)
        return res.stdout.strip()
    except Exception:
        return ""

def get_mpris_players():
    """Find active MPRIS media players via qdbus or playerctl."""
    # First check playerctl if installed
    players = run_cmd(["qdbus"]).splitlines()
    mpris_list = [p.strip() for p in players if "org.mpris.MediaPlayer2" in p]
    return mpris_list

def control_mpris(action):
    """action: PlayPause, Next, Previous, Stop"""
    # Try playerctl first if present
    if run_cmd(["which", "playerctl"]):
        cmd_map = {
            "PlayPause": ["playerctl", "play-pause"],
            "Next": ["playerctl", "next"],
            "Previous": ["playerctl", "previous"],
            "Stop": ["playerctl", "stop"],
            "Play": ["playerctl", "play"],
            "Pause": ["playerctl", "pause"]
        }
        if action in cmd_map:
            run_cmd(cmd_map[action])
            return True

    # Fallback to direct qdbus on all active players
    players = get_mpris_players()
    if not players:
        return False
    success = False
    for p in players:
        res = subprocess.run(
            ["qdbus", p, "/org/mpris/MediaPlayer2", f"org.mpris.MediaPlayer2.Player.{action}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if res.returncode == 0:
            success = True
    return success

def get_current_volume():
    """Returns integer percentage 0-100 of default sink."""
    out = run_cmd(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
    # Output format: 'Volume: 0.65' or 'Volume: 0.65 [MUTED]'
    m = re.search(r"Volume:\s+([0-9\.]+)", out)
    if m:
        try:
            return int(round(float(m.group(1)) * 100))
        except Exception:
            pass
    return 50

def get_hardware_status(lang="es"):
    """Reads sensors output for AMD/Intel GPU and CPU temperatures."""
    sensors_out = run_cmd(["sensors"])
    gpu_temp = None
    cpu_temp = None

    # Parse GPU edge or junction
    # edge:         +51.0°C
    m_gpu = re.search(r"(?:edge|junction|temp1):\s+\+([0-9\.]+)°C", sensors_out)
    if m_gpu:
        gpu_temp = int(float(m_gpu.group(1)))

    # Parse CPU Package id 0 or Tctl
    m_cpu = re.search(r"(?:Package id 0|Tctl|CPU|temp1):\s+\+([0-9\.]+)°C", sensors_out)
    if m_cpu:
        cpu_temp = int(float(m_cpu.group(1)))

    if lang == "en":
        parts = []
        if gpu_temp is not None:
            parts.append(f"GPU is at {gpu_temp} degrees")
        if cpu_temp is not None:
            parts.append(f"CPU is at {cpu_temp} degrees")
        return ". ".join(parts) + "." if parts else "Hardware sensors are normal."
    else:
        parts = []
        if gpu_temp is not None:
            parts.append(f"La gráfica está a {gpu_temp} grados")
        if cpu_temp is not None:
            parts.append(f"la CPU a {cpu_temp} grados")
        return " y ".join(parts) + "." if parts else "Los sensores están en rangos normales."

def try_fast_path(text, lang="es"):
    raw = text.lower().strip()
    # Normalize accents
    clean = raw
    for a, b in [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")]:
        clean = clean.replace(a, b)

    is_en = (lang == "en")

    # -------------------------------------------------------------------------
    # 1. HARDWARE STATUS (Nobara Gaming Check)
    # -------------------------------------------------------------------------
    if any(q in clean for q in [
        "como va la grafica", "temperatura de la grafica", "como va el pc",
        "como va el ordenador", "temperatura del ordenador", "estado del hardware",
        "gpu temp", "hardware status", "how is the gpu", "temperature of the pc"
    ]):
        reply = get_hardware_status(lang)
        title = "🎮 Hardware Status" if is_en else "🎮 Estado del Hardware"
        return {"handled": True, "reply": reply, "title": title}

    # -------------------------------------------------------------------------
    # 2. MEDIA CONTROLS (MPRIS / Spotify / Brave / Firefox / VLC)
    # -------------------------------------------------------------------------
    # Next track
    if any(q in clean for q in [
        "siguiente cancion", "pasa de cancion", "pasa la cancion", "pasa la musica",
        "salta de cancion", "next song", "next track", "skip song"
    ]):
        control_mpris("Next")
        reply = "Next track." if is_en else "Siguiente canción."
        title = "⏭️ Media"
        return {"handled": True, "reply": reply, "title": title}

    # Previous track
    if any(q in clean for q in [
        "cancion anterior", "anterior cancion", "cancion previa",
        "previous song", "previous track"
    ]):
        control_mpris("Previous")
        reply = "Previous track." if is_en else "Canción anterior."
        title = "⏮️ Media"
        return {"handled": True, "reply": reply, "title": title}

    # Stop media
    if any(q in clean for q in [
        "para la musica", "parar musica", "detener musica", "stop music", "stop media"
    ]):
        control_mpris("Stop")
        reply = "Music stopped." if is_en else "Música detenida."
        title = "⏹️ Media"
        return {"handled": True, "reply": reply, "title": title}

    # Play / Resume media
    if any(q in clean for q in [
        "reanuda la musica", "reanudar musica", "continua la musica",
        "resume music", "play music", "reproducir musica"
    ]):
        control_mpris("Play")
        reply = "Playing music." if is_en else "Reproduciendo música."
        title = "▶️ Media"
        return {"handled": True, "reply": reply, "title": title}

    # Play / Pause toggle
    if any(q in clean for q in [
        "pausa la musica", "pausar musica", "pausa el video", "pausar el video",
        "pause music", "pause video", "play pause"
    ]) or clean in ["pausa", "pausar", "pause"]:
        control_mpris("PlayPause")
        reply = "Music paused." if is_en else "Música pausada."
        title = "⏯️ Media"
        return {"handled": True, "reply": reply, "title": title}

    # -------------------------------------------------------------------------
    # 3. VOLUME & MUTE CONTROLS (PipeWire wpctl)
    # -------------------------------------------------------------------------
    # Specific volume: "volumen al 70%", "pon el volumen al 50", "set volume to 80"
    m_vol = re.search(r"(?:volumen al|pon el volumen al|volumen en|set volume to)\s+(\d{1,3})%?", clean)
    if m_vol:
        val = min(100, max(0, int(m_vol.group(1))))
        decimal_val = round(val / 100.0, 2)
        run_cmd(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", str(decimal_val)])
        reply = f"Volume set to {val}%." if is_en else f"Volumen puesto al {val}%."
        title = "🔊 Volumen" if not is_en else "🔊 Volume"
        return {"handled": True, "reply": reply, "title": title}

    # Volume Up
    if any(q in clean for q in [
        "sube el volumen", "subir volumen", "mas volumen", "subelo",
        "volume up", "increase volume", "louder"
    ]):
        run_cmd(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%+"])
        cur = get_current_volume()
        reply = f"Volume at {cur}%." if is_en else f"Volumen subido al {cur}%."
        title = "🔊 Volumen" if not is_en else "🔊 Volume"
        return {"handled": True, "reply": reply, "title": title}

    # Volume Down
    if any(q in clean for q in [
        "baja el volumen", "bajar volumen", "menos volumen", "bajalo",
        "volume down", "decrease volume", "quieter"
    ]):
        run_cmd(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-"])
        cur = get_current_volume()
        reply = f"Volume at {cur}%." if is_en else f"Volumen bajado al {cur}%."
        title = "🔉 Volumen" if not is_en else "🔉 Volume"
        return {"handled": True, "reply": reply, "title": title}

    # Mute/Unmute Output
    if any(q in clean for q in [
        "silencia el audio", "silenciar audio", "silencia el sonido", "mute audio",
        "desmutea", "quitar silencio", "unmute"
    ]) or clean in ["silencio", "mute"]:
        run_cmd(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])
        reply = "Audio toggle mute." if is_en else "Audio silenciado/activado."
        title = "🔇 Audio"
        return {"handled": True, "reply": reply, "title": title}

    # Mute/Unmute Mic
    if any(q in clean for q in [
        "silencia el microfono", "silencia el micro", "silenciar microfono",
        "mute mic", "mute microphone", "unmute mic"
    ]):
        run_cmd(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "toggle"])
        reply = "Microphone toggle mute." if is_en else "Micrófono conmutado."
        title = "🎙️ Micro"
        return {"handled": True, "reply": reply, "title": title}

    # -------------------------------------------------------------------------
    # 4. SYSTEM QUICK ACTIONS
    # -------------------------------------------------------------------------
    # Lock screen
    if any(q in clean for q in [
        "bloquea la pantalla", "bloquear pantalla", "bloquear sesion",
        "lock screen", "lock session"
    ]):
        run_cmd(["loginctl", "lock-session"])
        reply = "Screen locked." if is_en else "Pantalla bloqueada."
        title = "🔒 Sistema" if not is_en else "🔒 System"
        return {"handled": True, "reply": reply, "title": title}

    # Time / Date
    if any(q in clean for q in ["que hora es", "dime la hora", "what time is it"]):
        import datetime
        now = datetime.datetime.now()
        time_str = now.strftime("%H:%M")
        reply = f"It is {time_str}." if is_en else f"Son las {time_str}."
        title = "🕒 Hora" if not is_en else "🕒 Time"
        return {"handled": True, "reply": reply, "title": title}

    if any(q in clean for q in ["que dia es hoy", "que fecha es hoy", "what date is today", "what day is today"]):
        import datetime
        now = datetime.datetime.now()
        if is_en:
            reply = f"Today is {now.strftime('%A, %B %d')}."
        else:
            dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
            meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
            reply = f"Hoy es {dias[now.weekday()]}, {now.day} de {meses[now.month-1]}."
        title = "📅 Fecha" if not is_en else "📅 Date"
        return {"handled": True, "reply": reply, "title": title}

    return {"handled": False}

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"handled": False}))
        sys.exit(0)

    text = sys.argv[1]
    lang = sys.argv[2] if len(sys.argv) > 2 else "es"
    res = try_fast_path(text, lang)
    print(json.dumps(res))

if __name__ == "__main__":
    main()
