#!/usr/bin/env python3
"""
Nobara AI Voice Assistant - KDE Plasma System Tray Monitor & Menu.
Provides dynamic status indicators on the system tray:
- Idle
- Recording
- Processing

Interacts directly with the Go backend core binary.
"""
import sys
import os
import time
import json
import subprocess
import signal

from PySide6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu
)
from PySide6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QBrush, QPen, QAction, QFont
)
from PySide6.QtCore import Qt, QTimer

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
APP_ICON = os.path.join(ASSETS_DIR, "nobara-jarvis.png")
CONFIG_FILE = os.path.join(PROJECT_DIR, "config", "config.env")
ASSISTANT_BIN = os.path.join(PROJECT_DIR, "bin", "nobara-voice-assistant")
SETTINGS_BIN = os.path.join(PROJECT_DIR, "bin", "nobara-voice-assistant-settings")
PID_FILE = "/tmp/nobara_assistant.pid"
LIVE_STATUS_FILE = "/tmp/nobara_assistant_live.json"
AGENT_PID_FILE = "/tmp/nobara_assistant_agent.pid"

def load_config():
    config = {
        "ENABLED": "true",
        "ASSISTANT_LANGUAGE": "es",
        "ENABLE_VOICE_REPLY": "true",
        "AUDIO_DUCKING": "false",
        "AUTO_STOP_SILENCE": "false"
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip().strip('"').strip("'")
    return config

def update_config_value(key, value):
    lines = []
    found = False
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith(f"{key}="):
                    lines.append(f'{key}="{value}"' if isinstance(value, str) and value.lower() not in ("true", "false") else f"{key}={value}")
                    found = True
                else:
                    lines.append(line.rstrip("\r\n"))
    if not found:
        lines.append(f"{key}={value}")

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def make_tray_icon(state):
    """
    Renders a crisp 64x64 geometric icon:
    - idle: subtle cyan outline circle
    - recording: bright crimson solid circle
    - processing: deep electric blue circle with crosshairs
    """
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    if state == "recording":
        painter.setBrush(QBrush(QColor(231, 76, 60)))
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawEllipse(12, 12, 40, 40)
    elif state == "processing":
        painter.setBrush(QBrush(QColor(41, 128, 185)))
        painter.setPen(QPen(QColor(93, 173, 226), 2))
        painter.drawEllipse(12, 12, 40, 40)
        painter.setPen(QPen(QColor(255, 255, 255), 3, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(32, 20, 32, 44)
        painter.drawLine(20, 32, 44, 32)
    else:
        painter.setBrush(QBrush(QColor(26, 32, 44)))
        painter.setPen(QPen(QColor(56, 189, 248), 3))
        painter.drawEllipse(14, 14, 36, 36)
        painter.setBrush(QBrush(QColor(56, 189, 248)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(27, 27, 10, 10)

    painter.end()
    return QIcon(pix)

class AssistantTrayApp:
    def __init__(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        if os.path.exists(APP_ICON):
            self.app.setWindowIcon(QIcon(APP_ICON))

        self.icons = {
            "idle": make_tray_icon("idle"),
            "recording": make_tray_icon("recording"),
            "processing": make_tray_icon("processing")
        }

        self.current_state = "idle"
        self.tray = QSystemTrayIcon(self.icons["idle"])
        self.tray.setToolTip("Jarvis AI (En reposo)")

        self.tray.activated.connect(self.on_tray_activated)

        self.build_menu()
        self.tray.show()

        # State poll timer (every 400ms)
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_state)
        self.timer.start(400)

    def build_menu(self):
        config = load_config()
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background: #161b22;
                color: #e6edf3;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 4px;
                font-family: sans-serif;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 18px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #1f6feb;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: #30363d;
                margin: 4px 6px;
            }
        """)

        # Trigger voice action
        act_trigger = QAction("Hablar / Grabar orden", menu)
        act_trigger.triggered.connect(self.trigger_assistant)
        menu.addAction(act_trigger)

        # Reset session
        act_reset = QAction("Nueva conversación", menu)
        act_reset.triggered.connect(self.reset_conversation)
        menu.addAction(act_reset)

        menu.addSeparator()

        # Language toggle
        cur_lang = config.get("ASSISTANT_LANGUAGE", "es")
        lang_text = "Idioma: Español" if cur_lang == "es" else "Language: English"
        self.act_lang = QAction(lang_text, menu)
        self.act_lang.triggered.connect(self.toggle_language)
        menu.addAction(self.act_lang)

        # Voice reply toggle
        voice_on = config.get("ENABLE_VOICE_REPLY", "true").lower() == "true"
        self.act_voice = QAction("Voz sintetizada (TTS)", menu)
        self.act_voice.setCheckable(True)
        self.act_voice.setChecked(voice_on)
        self.act_voice.triggered.connect(self.toggle_voice_reply)
        menu.addAction(self.act_voice)

        # Audio ducking
        ducking_on = config.get("AUDIO_DUCKING", "false").lower() == "true"
        self.act_ducking = QAction("Atenuación de audio (Gaming)", menu)
        self.act_ducking.setCheckable(True)
        self.act_ducking.setChecked(ducking_on)
        self.act_ducking.triggered.connect(self.toggle_ducking)
        menu.addAction(self.act_ducking)

        menu.addSeparator()

        # Stop action
        act_stop = QAction("Detener tarea / Silenciar", menu)
        act_stop.triggered.connect(self.panic_stop)
        menu.addAction(act_stop)

        # Settings
        act_settings = QAction("Panel de ajustes e historial", menu)
        font_bold = QFont()
        font_bold.setBold(True)
        act_settings.setFont(font_bold)
        act_settings.triggered.connect(self.open_settings)
        menu.addAction(act_settings)

        menu.addSeparator()

        # Quit
        act_quit = QAction("Salir", menu)
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.menu = menu

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.open_settings()

    def trigger_assistant(self):
        env = os.environ.copy()
        env["DISPLAY"] = env.get("DISPLAY", ":0")
        env["WAYLAND_DISPLAY"] = env.get("WAYLAND_DISPLAY", "wayland-0")
        subprocess.Popen([ASSISTANT_BIN], env=env)

    def reset_conversation(self):
        subprocess.run([ASSISTANT_BIN, "conversations", "--reset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.tray.showMessage(
            "Asistente Nobara",
            "Nueva conversación iniciada. Contexto limpio.",
            QSystemTrayIcon.Information,
            2000
        )

    def toggle_language(self):
        config = load_config()
        cur_lang = config.get("ASSISTANT_LANGUAGE", "es")
        new_lang = "en" if cur_lang == "es" else "es"
        update_config_value("ASSISTANT_LANGUAGE", new_lang)
        self.act_lang.setText("Idioma: Español" if new_lang == "es" else "Language: English")
        self.tray.showMessage(
            "Idioma actualizado",
            f"El asistente responderá en {'Español' if new_lang == 'es' else 'English'}.",
            QSystemTrayIcon.Information,
            2000
        )

    def toggle_voice_reply(self, checked):
        update_config_value("ENABLE_VOICE_REPLY", "true" if checked else "false")

    def toggle_ducking(self, checked):
        update_config_value("AUDIO_DUCKING", "true" if checked else "false")

    def panic_stop(self):
        subprocess.run([ASSISTANT_BIN, "--silence"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(AGENT_PID_FILE):
            try:
                with open(AGENT_PID_FILE, "r") as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
        self.tray.showMessage("Asistente Nobara", "Audio y tareas silenciadas.", QSystemTrayIcon.Information, 1500)

    def open_settings(self):
        env = os.environ.copy()
        env["DISPLAY"] = env.get("DISPLAY", ":0")
        env["WAYLAND_DISPLAY"] = env.get("WAYLAND_DISPLAY", "wayland-0")
        subprocess.Popen([SETTINGS_BIN], env=env)

    def quit_app(self):
        self.app.quit()

    def poll_state(self):
        # 1. Recording check
        is_recording = False
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, "r") as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                is_recording = True
            except Exception:
                pass

        if is_recording:
            if self.current_state != "recording":
                self.current_state = "recording"
                self.tray.setIcon(self.icons["recording"])
                self.tray.setToolTip("Asistente Nobara: Grabando audio...")
            return

        # 2. Execution check
        is_processing = False
        if os.path.exists(LIVE_STATUS_FILE):
            try:
                with open(LIVE_STATUS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("status") == "RUNNING":
                    is_processing = True
            except Exception:
                pass

        if is_processing:
            if self.current_state != "processing":
                self.current_state = "processing"
                self.tray.setIcon(self.icons["processing"])
                self.tray.setToolTip("Asistente Nobara: Procesando tarea...")
            return

        # 3. Idle state
        if self.current_state != "idle":
            self.current_state = "idle"
            self.tray.setIcon(self.icons["idle"])
            self.tray.setToolTip("Jarvis AI (En reposo)")

def main():
    tray_app = AssistantTrayApp()
    sys.exit(tray_app.app.exec())

if __name__ == "__main__":
    main()
