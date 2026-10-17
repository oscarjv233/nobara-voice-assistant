#!/usr/bin/env python3
"""
PipeWire Audio Recorder with Auto-Stop Voice Activity Detection (VAD).
Captures 16kHz mono audio via pw-record and writes standard WAV.

If --auto-stop is enabled:
  - Measures ambient noise floor.
  - Detects speech onset (filters out momentary keyboard clicks).
  - Triggers stop and assistant processing automatically after silence duration (e.g. 1.2s).
Supports manual interrupt at any time via SIGINT/SIGTERM.
"""
import sys
import os
import time
import signal
import wave
import argparse
import subprocess
import numpy as np

def main():
    parser = argparse.ArgumentParser(description="PipeWire audio recorder with VAD silence auto-stop")
    parser.add_argument("--output", required=True, help="Destination WAV file path")
    parser.add_argument("--auto-stop", action="store_true", help="Enable silence auto-stop")
    parser.add_argument("--silence", type=float, default=1.2, help="Seconds of silence to trigger auto-stop")
    parser.add_argument("--timeout", type=float, default=25.0, help="Maximum recording duration in seconds")
    parser.add_argument("--trigger-cmd", default="", help="Command to run when auto-stop fires")
    args = parser.parse_args()

    out_path = args.output
    auto_stop = args.auto_stop
    silence_limit = max(0.6, float(args.silence))
    max_timeout = float(args.timeout)
    trigger_cmd = args.trigger_cmd or os.path.expanduser("~/.local/bin/nobara-voice-assistant")

    running = True

    def handle_signal(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # 16000 Hz, 1 channel, 16-bit (2 bytes per sample)
    # 50ms chunk = 16000 * 0.05 = 800 samples = 1600 bytes
    CHUNK_DURATION = 0.05
    CHUNK_BYTES = 1600

    cmd = ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    wf = wave.open(out_path, "wb")
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(16000)

    start_time = time.time()
    noise_samples = []
    noise_floor = 180.0
    speech_threshold = 400.0
    has_spoken = False
    consecutive_voice_chunks = 0
    silence_elapsed = 0.0
    auto_triggered = False

    try:
        while running:
            chunk = proc.stdout.read(CHUNK_BYTES)
            if not chunk or len(chunk) < CHUNK_BYTES:
                break

            wf.writeframes(chunk)

            elapsed = time.time() - start_time
            if elapsed >= max_timeout:
                if has_spoken:
                    auto_triggered = True
                break

            if auto_stop:
                samples = np.frombuffer(chunk, dtype=np.int16)
                rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))

                # Phase 1: Calibrate noise floor in the first 250ms (5 chunks)
                if len(noise_samples) < 5:
                    noise_samples.append(rms)
                    if len(noise_samples) == 5:
                        # Cap noise floor at 450.0 so starting to speak early doesn't make threshold impossible
                        noise_floor = min(float(np.mean(noise_samples)), 450.0)
                        # Adaptive threshold: at least 350.0, or 2.0x ambient noise, capped at 850.0
                        speech_threshold = max(350.0, min(noise_floor * 2.0, 850.0))
                    continue

                # Phase 2: Detect speech onset & silence
                if not has_spoken:
                    if rms > speech_threshold:
                        consecutive_voice_chunks += 1
                        # Require 2 chunks (100ms) of sound above threshold to eliminate keyboard clicks
                        if consecutive_voice_chunks >= 2:
                            has_spoken = True
                            silence_elapsed = 0.0
                    else:
                        consecutive_voice_chunks = 0
                        # If user hasn't started speaking within 7 seconds, auto-stop
                        if elapsed > 7.0:
                            auto_triggered = True
                            break
                else:
                    if rms < speech_threshold:
                        silence_elapsed += CHUNK_DURATION
                        if silence_elapsed >= silence_limit:
                            auto_triggered = True
                            break
                    else:
                        # Reset silence counter if user resumes talking
                        silence_elapsed = 0.0

    finally:
        # Clean shutdown
        try:
            wf.close()
        except Exception:
            pass

        try:
            proc.terminate()
            proc.wait(timeout=0.2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    if auto_triggered and trigger_cmd and os.path.exists(out_path):
        # Fire trigger in background so nobara-voice-assistant handles stopping & processing
        try:
            env = os.environ.copy()
            env["DISPLAY"] = env.get("DISPLAY", ":0")
            env["WAYLAND_DISPLAY"] = env.get("WAYLAND_DISPLAY", "wayland-0")
            subprocess.Popen([trigger_cmd], env=env)
        except Exception as e:
            sys.stderr.write(f"Error triggering assistant: {e}\n")

if __name__ == "__main__":
    main()
