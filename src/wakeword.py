#!/usr/bin/env python3
"""
Nobara Jarvis AI Assistant - Hands-Free Wake Word Daemon.
Uses openWakeWord (100% local ONNX inference, ~1% CPU).
Optimized for:
  - Single-model loading to minimize CPU usage.
  - Automatic software gain normalization for quiet / distant microphones.
  - Robust key matching (e.g. 'jarvis', 'hey_jarvis' -> 'hey_jarvis_v0.1').
  - Immediate audio feedback chime when triggered.
  - Automatic sleep/cooldown while assistant is recording or speaking.
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
SOUND_START = "/usr/share/sounds/ocean/stereo/bell.oga"
PID_FILE = "/tmp/nobara_assistant.pid"
LIVE_STATUS_FILE = "/tmp/nobara_assistant_live.json"
WAKE_PID_FILE = "/tmp/nobara_assistant_wakeword.pid"

def load_config():
    config = {
        "WAKE_WORD_ENABLED": "false",
        "WAKE_WORD_MODEL": "hey_jarvis",
        "WAKE_WORD_THRESHOLD": "0.30",
        "TTS_VOLUME": "0.35"
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip().strip('"').strip("'")
    return config

def get_wake_score(pred, target_model):
    target = target_model.lower().replace("hey_", "").replace("_", "")
    for key, score in pred.items():
        clean_key = key.lower().replace("hey_", "").replace("_", "")
        if target in clean_key:
            return float(score)
    # Fallback to max score
    return max(pred.values(), default=0.0)

def main():
    config = load_config()
    target_model = config.get("WAKE_WORD_MODEL", "hey_jarvis")
    try:
        threshold = float(config.get("WAKE_WORD_THRESHOLD", "0.30"))
    except ValueError:
        threshold = 0.30

    volume = config.get("TTS_VOLUME", "0.35")

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

    # Load only the chosen model to keep CPU below 1.5%
    paths = openwakeword.get_pretrained_model_paths()
    clean_target = target_model.replace("hey_", "").lower()
    matched_paths = [p for p in paths if clean_target in os.path.basename(p).lower()]
    if not matched_paths:
        matched_paths = [p for p in paths if "jarvis" in os.path.basename(p).lower()]
    if not matched_paths:
        matched_paths = [paths[0]] if paths else []

    model = Model(wakeword_model_paths=matched_paths)

    # 1280 samples at 16000Hz = 80ms per chunk (2560 bytes)
    CHUNK_SAMPLES = 1280
    CHUNK_BYTES = CHUNK_SAMPLES * 2

    cmd = ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    try:
        while running:
            # Check if assistant is already recording or executing a task
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

            # Digital Gain Normalization: Boost quiet microphones up to optimal range
            max_val = np.max(np.abs(samples))
            if max_val > 100:
                scale = min(3.8, 22000.0 / max(max_val, 1))
                boosted = np.clip(samples.astype(np.float32) * scale, -32768, 32767).astype(np.int16)
            else:
                boosted = samples

            pred = model.predict(boosted)
            score = get_wake_score(pred, target_model)

            if score >= threshold:
                # Wake word detected!
                # Audio chime
                if os.path.exists(SOUND_START):
                    subprocess.Popen(["pw-play", f"--volume={volume}", SOUND_START], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                # Trigger voice assistant
                env = os.environ.copy()
                env["DISPLAY"] = env.get("DISPLAY", ":0")
                env["WAYLAND_DISPLAY"] = env.get("WAYLAND_DISPLAY", "wayland-0")
                subprocess.Popen([ASSISTANT_BIN], env=env)

                # Reset openwakeword state and cooldown
                model.reset()
                time.sleep(3.5)

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
