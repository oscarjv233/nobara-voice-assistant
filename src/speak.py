#!/usr/bin/env python3
"""
Text-to-Speech module using local Piper neural voice.
Supports configurable voice models, multi-speaker selection,
markdown cleaning and PipeWire stream volume control.
"""
import sys
import os
import re
import subprocess

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_WAV = "/tmp/nobara_assistant_speech.wav"
CONFIG_FILE = os.path.join(PROJECT_DIR, "config", "config.env")

def get_voice_settings():
    voice_model = os.environ.get("VOICE_MODEL", "es_ES-davefx-medium.onnx")
    speaker = os.environ.get("VOICE_SPEAKER", "")

    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("VOICE_MODEL="):
                    voice_model = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("VOICE_SPEAKER="):
                    speaker = line.split("=", 1)[1].strip().strip('"').strip("'")

    model_path = os.path.join(PROJECT_DIR, "voices", voice_model)
    if not os.path.exists(model_path):
        model_path = os.path.join(PROJECT_DIR, "voices", "es_ES-davefx-medium.onnx")

    return model_path, speaker

def get_tts_volume():
    vol_env = os.environ.get("TTS_VOLUME")
    if vol_env:
        try:
            return float(vol_env)
        except ValueError:
            pass
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("TTS_VOLUME="):
                    try:
                        return float(line.split("=", 1)[1].strip().strip('"').strip("'"))
                    except:
                        pass
    return 0.35

def clean_markdown(text):
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'#+\s*', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_sink_volume():
    try:
        res = subprocess.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], capture_output=True, text=True)
        m = re.search(r"Volume:\s+([0-9\.]+)", res.stdout)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None

def is_audio_ducking_enabled():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("AUDIO_DUCKING="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'").lower() == "true"
    return False

def speak(text, model_path=None, speaker=None, volume=None):
    if not text or not text.strip():
        return

    cleaned = clean_markdown(text)
    if not cleaned:
        return

    default_model, default_speaker = get_voice_settings()
    model_path = model_path or default_model
    speaker = speaker if speaker is not None else default_speaker
    volume = volume if volume is not None else get_tts_volume()

    try:
        cmd = [
            "python3", "-m", "piper",
            "--model", model_path,
            "--output-file", OUTPUT_WAV
        ]
        if speaker and str(speaker).strip():
            cmd.extend(["--speaker", str(speaker).strip()])

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True
        )
        proc.communicate(input=cleaned)

        if os.path.exists(OUTPUT_WAV) and os.path.getsize(OUTPUT_WAV) > 0:
            # Audio Ducking: temporarily lower background media if enabled
            ducked = False
            orig_vol = None
            if is_audio_ducking_enabled():
                orig_vol = get_sink_volume()
                if orig_vol is not None and orig_vol > 0.15:
                    duck_vol = max(0.1, round(orig_vol * 0.45, 2))
                    subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", str(duck_vol)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    ducked = True

            try:
                subprocess.run(
                    ["pw-play", f"--volume={volume}", OUTPUT_WAV],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            finally:
                if ducked and orig_vol is not None:
                    subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", str(orig_vol)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    except Exception as e:
        sys.stderr.write(f"TTS Error: {e}\n")

def main():
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    else:
        text = sys.stdin.read()
    speak(text)

if __name__ == "__main__":
    main()
