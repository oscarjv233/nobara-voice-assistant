#!/usr/bin/env python3
"""
Nobara AI Voice Assistant - Hands-Free Wake Word Daemon.
Uses openWakeWord (100% local ONNX inference, ~1% CPU) to listen for
wake words (e.g. 'Hey Jarvis', 'Alexa') and trigger nobara-voice-assistant.
Includes safety guards against self-triggering while assistant is speaking.
"""
import sys
import os
import time
import signal
import subprocess
import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(PROJECT_DIR, "config", "config.env")
ASSISTANT_BIN = os.path.join(PROJECT_DIR, "bin", "nobara-voice-assistant")
PID_FILE = "/tmp/nobara_assistant.pid"
LIVE_STATUS_FILE = "/tmp/nobara_assistant_live.json"
WAKE_PID_FILE = "/tmp/nobara_assistant_wakeword.pid"

def load_config():
    config = {
        "WAKE_WORD_ENABLED": "false",
        "WAKE_WORD_MODEL": "hey_jarvis",
        "WAKE_WORD_THRESHOLD": "0.5"
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip().strip('"').strip("'")
    return config

def main():
    config = load_config()
    target_model = config.get("WAKE_WORD_MODEL", "hey_jarvis")
    try:
        threshold = float(config.get("WAKE_WORD_THRESHOLD", "0.5"))
    except ValueError:
        threshold = 0.5

    # Check if openwakeword is available
    try:
        import openwakeword
        from openwakeword.model import Model
    except ImportError:
        sys.stderr.write("openWakeWord not installed. Run: pip install --user openwakeword\n")
        sys.exit(1)

    with open(WAKE_PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    running = True
    def handle_sig(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    model = Model()
    if target_model not in model.models:
        # Fallback to first available model
        avail = list(model.models.keys())
        target_model = avail[0] if avail else "hey_jarvis"

    # 1280 samples at 16000Hz = 80ms per chunk (2560 bytes)
    CHUNK_SAMPLES = 1280
    CHUNK_BYTES = CHUNK_SAMPLES * 2

    cmd = ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    try:
        while running:
            # Check if assistant is currently recording or executing
            is_busy = False
            if os.path.exists(PID_FILE):
                is_busy = True
            elif os.path.exists(LIVE_STATUS_FILE):
                try:
                    with open(LIVE_STATUS_FILE, "r", encoding="utf-8") as f:
                        import json
                        data = json.load(f)
                        if data.get("status") == "RUNNING":
                            is_busy = True
                except Exception:
                    pass

            if is_busy:
                # Flush pipe buffer and sleep briefly
                time.sleep(0.3)
                proc.stdout.read(CHUNK_BYTES * 4)
                continue

            chunk = proc.stdout.read(CHUNK_BYTES)
            if not chunk or len(chunk) < CHUNK_BYTES:
                break

            samples = np.frombuffer(chunk, dtype=np.int16)
            pred = model.predict(samples)

            score = pred.get(target_model, 0.0)
            if score >= threshold:
                # Wake word detected! Trigger voice assistant
                env = os.environ.copy()
                env["DISPLAY"] = env.get("DISPLAY", ":0")
                env["WAYLAND_DISPLAY"] = env.get("WAYLAND_DISPLAY", "wayland-0")
                subprocess.Popen([ASSISTANT_BIN], env=env)

                # Reset openwakeword state and cooldown
                model.reset()
                time.sleep(3.0)

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=0.3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        if os.path.exists(WAKE_PID_FILE):
            try:
                os.remove(WAKE_PID_FILE)
            except Exception:
                pass

if __name__ == "__main__":
    main()
