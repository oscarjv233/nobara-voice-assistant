#!/usr/bin/env python3
"""
Speech-to-Text module using faster-whisper.
Includes audio normalization and hallucination suppression.
"""
import sys
import wave
import numpy as np
from faster_whisper import WhisperModel

def load_and_normalize_audio(file_path):
    try:
        with wave.open(file_path, "rb") as wf:
            n_channels = wf.getnchannels()
            frames = wf.readframes(wf.getnframes())
            audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            if n_channels > 1:
                audio = audio.reshape(-1, n_channels).mean(axis=1)

            # Silence gate: Check if there is enough sound energy
            max_amp = np.max(np.abs(audio)) if len(audio) > 0 else 0
            if max_amp < 0.005:
                return None

            # Normalize audio
            audio = (audio / max_amp) * 0.92
            return audio
    except Exception as e:
        sys.stderr.write(f"Error loading wave file: {e}\n")
        return None

def transcribe(audio_path, model_name="base", language="es"):
    audio = load_and_normalize_audio(audio_path)
    if audio is None or len(audio) == 0:
        return ""

    try:
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, info = model.transcribe(
            audio,
            language=language or "es",
            beam_size=5,
            condition_on_previous_text=False,
            compression_ratio_threshold=2.4,
            no_speech_threshold=0.6,
            temperature=0.0
        )
        text = " ".join([seg.text.strip() for seg in segments]).strip()
        return text
    except Exception as e:
        sys.stderr.write(f"Transcription error: {e}\n")
        return ""

def main():
    if len(sys.argv) < 2:
        sys.exit(1)

    audio_file = sys.argv[1]
    model_name = sys.argv[2] if len(sys.argv) > 2 else "base"
    lang = sys.argv[3] if len(sys.argv) > 3 else "es"

    text = transcribe(audio_file, model_name=model_name, language=lang)
    print(text)

if __name__ == "__main__":
    main()
