#!/usr/bin/env python3
"""
Nobara AI Voice Assistant - KDE Plasma System Tray Monitor & Quick Menu.
Integrates into the system tray next to the Plasma clock with dynamic status icons:
  🟢 Idle / En reposo
  🔴 Recording / Grabando voz
  🔵 Processing / Ejecutando tarea de AGY
Right-click quick menu allows:
  - Triggering voice
  - Resetting conversation session
  - Toggling English / Spanish
  - Toggling TTS voice response
  - Toggling Gaming Audio Ducking
  - Stopping / Silencing running tasks
  - Opening the full Control Panel & History
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

# Import conversation reset helper
sys.path.insert(0, os.path.join(PROJECT_DIR, "src"))
try:
    import conversations
except Exception:
    conversations = None

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
    config = load_config()
    config[key] = str(value)
    lines = []
    found = False
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith(f"{key}="):
                    lines.append(f'{key}="{value}"' if isinstance(value, str) and not value.lower() in ("true", "false") else f"{key}={value}")
                    found = True
                else:
                    lines.append(line.rstrip("\r\n"))
    if not found:
        lines.append(f"{key}={value}")

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def make_tray_icon(state):
    """
    Renders a crisp 64x64 icon on the fly:
    - 'idle': Subtle teal/green microphone with dark badge
    - 'recording': Glowing pulsating red recording circle
    - 'processing': Neon blue active gear/circle
    """
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)

    if state == "recording":
        # Glowing red badge
        painter.setBrush(QBrush(QColor(231, 76, 60, 240)))
        painter.setPen(QPen(QColor(255, 255, 255), 3))
        painter.drawEllipse(6, 6, 52, 52)
        # Inner white dot
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(22, 22, 20, 20)

    elif state == "processing":
        # Neon blue badge
        painter.setBrush(QBrush(QColor(41, 128, 185, 240)))
        painter.setPen(QPen(QColor(93, 173, 226), 3))
        painter.drawEllipse(6, 6, 52, 52)
        # Inner rotating accent / gear symbol
        painter.setPen(QPen(QColor(255, 255, 255), 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(32, 18, 32, 46)
        painter.drawLine(18, 32, 46, 32)
        painter.drawLine(22, 22, 42, 42)
        painter.drawLine(22, 42, 42, 22)

    else: # idle
        jarvis_icon = os.path.join(ASSETS_DIR, "nobara-jarvis-64.png")
        if os.path.exists(jarvis_icon):
            return QIcon(jarvis_icon)

        # Fallback drawing
        painter.setBrush(QBrush(QColor(0, 229, 255, 230)))
        painter.setPen(QPen(QColor(255, 255, 255, 180), 2))
        painter.drawEllipse(8, 8, 48, 48)
        painter.end()
        return QIcon(pix)

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
        self.tray.setToolTip("Jarvis AI — Nobara Linux (En reposo)")

        self.tray.activated.connect(self.on_tray_activated)

        self.build_menu()
        self.tray.show()

        # Polling timer for assistant state (every 400ms)
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_state)
        self.timer.start(400)

    def build_menu(self):
        config = load_config()
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background: #1e222b;
                color: #e0e0e0;
                border: 1px solid #3d4452;
                border-radius: 8px;
                padding: 6px;
                font-family: sans-serif;
            }
            QMenu::item {
                padding: 6px 20px 6px 24px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #2b7bb9;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: #3d4452;
                margin: 4px 8px;
            }
        """)

        # 1. Trigger Voice Shortcut
        act_trigger = QAction("🎙️ Hablar / Grabar Orden", menu)
        act_trigger.triggered.connect(self.trigger_assistant)
        menu.addAction(act_trigger)

        # 2. Reset conversation
        act_reset = QAction("➕ Nueva Conversación", menu)
        act_reset.triggered.connect(self.reset_conversation)
        menu.addAction(act_reset)

        menu.addSeparator()

        # 3. Toggle Language
        cur_lang = config.get("ASSISTANT_LANGUAGE", "es")
        lang_text = "🌐 Idioma: Español 🇪🇸" if cur_lang == "es" else "🌐 Language: English 🇺🇸"
        self.act_lang = QAction(lang_text, menu)
        self.act_lang.triggered.connect(self.toggle_language)
        menu.addAction(self.act_lang)

        # 4. Toggle Voice Reply
        voice_on = config.get("ENABLE_VOICE_REPLY", "true").lower() == "true"
        self.act_voice = QAction("🔊 Voz del Asistente (TTS)", menu)
        self.act_voice.setCheckable(True)
        self.act_voice.setChecked(voice_on)
        self.act_voice.triggered.connect(self.toggle_voice_reply)
        menu.addAction(self.act_voice)

        # 5. Toggle Gaming Ducking
        ducking_on = config.get("AUDIO_DUCKING", "false").lower() == "true"
        self.act_ducking = QAction("🎮 Modo Gaming (Audio Ducking)", menu)
        self.act_ducking.setCheckable(True)
        self.act_ducking.setChecked(ducking_on)
        self.act_ducking.triggered.connect(self.toggle_ducking)
        menu.addAction(self.act_ducking)

        menu.addSeparator()

        # 6. Stop / Panic
        act_stop = QAction("🛑 Detener Tarea / Silenciar Audio", menu)
        act_stop.triggered.connect(self.panic_stop)
        menu.addAction(act_stop)

        # 7. Open Settings GUI
        act_settings = QAction("⚙️ Panel de Ajustes e Historial...", menu)
        font_bold = QFont()
        font_bold.setBold(True)
        act_settings.setFont(font_bold)
        act_settings.triggered.connect(self.open_settings)
        menu.addAction(act_settings)

        menu.addSeparator()

        # 8. Quit Tray
        act_quit = QAction("🚪 Salir de la Bandeja", menu)
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
        if conversations:
            conversations.reset_active_session()
            self.tray.showMessage(
                "Asistente Nobara",
                "Nueva conversación iniciada. Contexto limpio.",
                QSystemTrayIcon.Information,
                2500
            )

    def toggle_language(self):
        config = load_config()
        cur_lang = config.get("ASSISTANT_LANGUAGE", "es")
        new_lang = "en" if cur_lang == "es" else "es"
        update_config_value("ASSISTANT_LANGUAGE", new_lang)
        self.act_lang.setText("🌐 Idioma: Español 🇪🇸" if new_lang == "es" else "🌐 Language: English 🇺🇸")
        self.tray.showMessage(
            "Idioma Cambiado / Language Changed",
            f"El asistente responderá en {'Español' if new_lang == 'es' else 'English'}.",
            QSystemTrayIcon.Information,
            2000
        )

    def toggle_voice_reply(self, checked):
        update_config_value("ENABLE_VOICE_REPLY", "true" if checked else "false")

    def toggle_ducking(self, checked):
        update_config_value("AUDIO_DUCKING", "true" if checked else "false")

    def panic_stop(self):
        # Run panic stop
        subprocess.run([ASSISTANT_BIN, "--silence"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Also kill agent PID if running
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
        # 1. Is mic recording?
        is_recording = False
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, "r") as f:
                    pid = int(f.read().strip())
                # Check if process alive
                os.kill(pid, 0)
                is_recording = True
            except Exception:
                pass

        if is_recording:
            if self.current_state != "recording":
                self.current_state = "recording"
                self.tray.setIcon(self.icons["recording"])
                self.tray.setToolTip("🎙️ Asistente Nobara: Grabando voz...")
            return

        # 2. Is AGY executing a task?
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
                self.tray.setToolTip("⚡ Asistente Nobara: Procesando tarea...")
            return

        # 3. Idle
        if self.current_state != "idle":
            self.current_state = "idle"
            self.tray.setIcon(self.icons["idle"])
            self.tray.setToolTip("🟢 Asistente de Voz Nobara (En reposo)")

def main():
    tray_app = AssistantTrayApp()
    sys.exit(tray_app.app.exec())

if __name__ == "__main__":
    main()
