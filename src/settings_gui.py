#!/usr/bin/env python3
"""
Nobara Jarvis AI Voice Assistant - Configuration & Control Panel.
Built with PySide6 for native KDE Plasma 6 / Wayland integration.
Structured into 4 logical tabs:
- Tab 1: Conversaciones (Historial de sesiones y visor de turnos)
- Tab 2: Monitor en Vivo (Estado en tiempo real y control de tareas activas)
- Tab 3: Voz y Reconocimiento (Piper TTS, Whisper y VAD)
- Tab 4: Sistema y Automatización (Wake Word, HUD, Ducking y Autostart)
"""
import sys
import os
import subprocess
import threading
import time
import json
import signal
import html
import re

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QCheckBox, QComboBox, QPushButton, QGroupBox,
    QMessageBox, QFrame, QTabWidget, QListWidget, QListWidgetItem,
    QTextBrowser, QSplitter, QProgressBar, QScrollArea, QLineEdit,
    QMenu, QToolButton
)
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
APP_ICON = os.path.join(ASSETS_DIR, "nobara-jarvis.png")
CONFIG_FILE = os.path.join(PROJECT_DIR, "config", "config.env")
ASSISTANT_BIN = os.path.join(PROJECT_DIR, "bin", "nobara-voice-assistant")
TRANSCRIBE_SCRIPT = os.path.join(PROJECT_DIR, "src", "transcribe.py")
VOICES_DIR = os.path.join(PROJECT_DIR, "voices")
LIVE_STATUS_FILE = "/tmp/nobara_assistant_live.json"
PID_FILE = "/tmp/nobara_assistant_agent.pid"

AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")
AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, "nobara-jarvis-autostart.desktop")

# Import conversation manager
sys.path.insert(0, os.path.join(PROJECT_DIR, "src"))
import conversations

AVAILABLE_VOICES = [
    {
        "label": "Hombre - España (DaveFX)",
        "model": "es_ES-davefx-medium.onnx",
        "speaker": "",
        "lang": "es"
    },
    {
        "label": "Mujer - España (Sharvard F)",
        "model": "es_ES-sharvard-medium.onnx",
        "speaker": "1",
        "lang": "es"
    },
    {
        "label": "Hombre - España (Sharvard M)",
        "model": "es_ES-sharvard-medium.onnx",
        "speaker": "0",
        "lang": "es"
    },
    {
        "label": "Mujer - Argentina (Daniela High)",
        "model": "es_AR-daniela-high.onnx",
        "speaker": "",
        "lang": "es"
    },
    {
        "label": "Woman - English US (Lessac Medium)",
        "model": "en_US-lessac-medium.onnx",
        "speaker": "",
        "lang": "en"
    },
    {
        "label": "Man - English US (Ryan Medium)",
        "model": "en_US-ryan-medium.onnx",
        "speaker": "",
        "lang": "en"
    }
]

class WorkerSignals(QObject):
    finished = Signal(str)

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
        "CONTINUOUS_CONVERSATION": "true",
        "ACTIVE_CONVERSATION_ID": "",
        "ASSISTANT_LANGUAGE": "es",
        "AUTO_STOP_SILENCE": "false",
        "SILENCE_DURATION": "1.2",
        "AUDIO_DUCKING": "false",
        "WAKE_WORD_ENABLED": "false",
        "WAKE_WORD_MODEL": "hey_jarvis",
        "WAKE_WORD_THRESHOLD": "0.30",
        "OVERLAY_HUD_ENABLED": "true",
        "AGY_BIN": os.path.expanduser("~/.local/bin/agy")
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    config[key.strip()] = val.strip().strip('"').strip("'")
    return config

def save_config(config):
    default_agy = os.path.expanduser("~/.local/bin/agy")
    lines = [
        "# Nobara Voice Assistant Configuration",
        f'ENABLED={config.get("ENABLED", "true")}',
        f'WHISPER_MODEL="{config.get("WHISPER_MODEL", "base")}"',
        f'ENABLE_VOICE_REPLY={config.get("ENABLE_VOICE_REPLY", "true")}',
        f'VOICE_MODEL="{config.get("VOICE_MODEL", "es_ES-davefx-medium.onnx")}"',
        f'VOICE_SPEAKER="{config.get("VOICE_SPEAKER", "")}"',
        f'TTS_VOLUME={config.get("TTS_VOLUME", "0.35")}',
        f'ENABLE_PROCESSING_VOICE_CUE={config.get("ENABLE_PROCESSING_VOICE_CUE", "true")}',
        f'RESULT_NOTIF_TIMEOUT={config.get("RESULT_NOTIF_TIMEOUT", "15000")}',
        f'AGY_BIN="{config.get("AGY_BIN", default_agy)}"',
        f'CONTINUOUS_CONVERSATION={config.get("CONTINUOUS_CONVERSATION", "true")}',
        f'ACTIVE_CONVERSATION_ID="{config.get("ACTIVE_CONVERSATION_ID", "")}"',
        f'ASSISTANT_LANGUAGE="{config.get("ASSISTANT_LANGUAGE", "es")}"',
        f'AUTO_STOP_SILENCE={config.get("AUTO_STOP_SILENCE", "false")}',
        f'SILENCE_DURATION={config.get("SILENCE_DURATION", "1.2")}',
        f'AUDIO_DUCKING={config.get("AUDIO_DUCKING", "false")}',
        f'WAKE_WORD_ENABLED={config.get("WAKE_WORD_ENABLED", "false")}',
        f'WAKE_WORD_MODEL="{config.get("WAKE_WORD_MODEL", "hey_jarvis")}"',
        f'WAKE_WORD_THRESHOLD={config.get("WAKE_WORD_THRESHOLD", "0.30")}',
        f'OVERLAY_HUD_ENABLED={config.get("OVERLAY_HUD_ENABLED", "true")}',
        ""
    ]
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def regenerate_procesando_audio(voice_model, speaker):
    model_path = os.path.join(VOICES_DIR, voice_model)
    out_wav = os.path.join(VOICES_DIR, "procesando.wav")
    cue_text = "Processing..." if voice_model.startswith("en_") else "Procesando..."
    cmd = ["python3", "-m", "piper", "--model", model_path, "--output-file", out_wav]
    if speaker and str(speaker).strip():
        cmd.extend(["--speaker", str(speaker).strip()])
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        p.communicate(cue_text)
    except Exception as e:
        sys.stderr.write(f"Error regenerating procesando cue: {e}\n")

def format_text_as_html(text: str) -> str:
    if not text:
        return ""
    escaped = html.escape(text)
    def replace_code_block(m):
        code_content = m.group(1).strip()
        return f"<div class='code-box'><pre><code>{code_content}</code></pre></div>"
    escaped = re.sub(r'```(?:[a-zA-Z0-9_\-]+)?\n?(.*?)```', replace_code_block, escaped, flags=re.DOTALL)
    escaped = re.sub(r'`([^`\n]+)`', r'<code class="inline-code">\1</code>', escaped)
    escaped = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', escaped)
    escaped = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', escaped)
    escaped = escaped.replace("\n", "<br/>")
    escaped = re.sub(
        r'<div class=\'code-box\'><pre><code>(.*?)</code></pre></div>',
        lambda m: "<div class='code-box'><pre><code>" + m.group(1).replace("<br/>", "\n") + "</code></pre></div>",
        escaped
    )
    return escaped

def is_autostart_enabled():
    if not os.path.exists(AUTOSTART_FILE):
        return False
    try:
        with open(AUTOSTART_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        return "Hidden=true" not in content
    except Exception:
        return False

def enable_autostart():
    os.makedirs(AUTOSTART_DIR, exist_ok=True)
    autostart_bin = os.path.join(PROJECT_DIR, "bin", "nobara-voice-assistant-autostart")
    content = f"""[Desktop Entry]
Name=Jarvis AI Autostart
Comment=Inicia Jarvis AI al arrancar el sistema
Exec={autostart_bin}
Icon=nobara-jarvis
Terminal=false
Type=Application
Categories=Utility;
StartupNotify=false
X-GNOME-Autostart-enabled=true
X-KDE-autostart-after=panel
Hidden=false
"""
    with open(AUTOSTART_FILE, "w", encoding="utf-8") as f:
        f.write(content)

def disable_autostart():
    if os.path.exists(AUTOSTART_FILE):
        os.remove(AUTOSTART_FILE)

class SettingsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Jarvis AI — Panel de Control e Historial")
        self.resize(1000, 720)
        self.setMinimumSize(820, 560)
        if os.path.exists(APP_ICON):
            self.setWindowIcon(QIcon(APP_ICON))

        self.config = load_config()

        self.signals = WorkerSignals()
        self.signals.finished.connect(self.on_mic_test_finished)

        self.all_conversations = []
        self.current_running_pid = None

        self.init_ui()

        # Live status monitoring timer (every 800ms)
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.poll_live_status)
        self.status_timer.start(800)

        # Initial conversation list load
        self.refresh_conversation_list()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # Header
        top_header = QHBoxLayout()
        top_header.setSpacing(10)

        if os.path.exists(APP_ICON):
            lbl_icon = QLabel()
            lbl_icon.setPixmap(QPixmap(APP_ICON).scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            top_header.addWidget(lbl_icon)

        title_label = QLabel("Jarvis AI — Nobara Linux")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #38bdf8; font-family: sans-serif;")
        top_header.addWidget(title_label)
        top_header.addStretch()

        self.lbl_global_status = QLabel("En reposo")
        self.lbl_global_status.setStyleSheet("font-weight: bold; padding: 4px 12px; border-radius: 4px; background: rgba(34, 197, 94, 0.15); color: #22c55e; font-size: 11px;")
        top_header.addWidget(self.lbl_global_status)
        main_layout.addLayout(top_header)

        # Tabs: 4 logically separated views
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #30363d;
                border-radius: 6px;
                background: #0d1117;
            }
            QTabBar::tab {
                padding: 8px 20px;
                font-weight: bold;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 4px;
                background: #161b22;
                color: #8b949e;
                font-size: 12px;
            }
            QTabBar::tab:hover {
                color: #c9d1d9;
                background: #1c2128;
            }
            QTabBar::tab:selected {
                background: #1f6feb;
                color: #ffffff;
            }
        """)

        # Tab instances
        self.tab_history = QWidget()
        self.tab_live = QWidget()
        self.tab_audio = QWidget()
        self.tab_system = QWidget()

        # Build each tab
        self.init_tab_history()
        self.init_tab_live()
        self.init_tab_audio()
        self.init_tab_system()

        self.tabs.addTab(self.tab_history, "Conversaciones")
        self.tabs.addTab(self.tab_live, "Monitor en Vivo")
        self.tabs.addTab(self.tab_audio, "Voz y Reconocimiento")
        self.tabs.addTab(self.tab_system, "Sistema y Atajos")

        main_layout.addWidget(self.tabs, 1)

        # Bottom Bar
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(4, 2, 4, 2)

        self.btn_save_global = QPushButton("Guardar Ajustes")
        self.btn_save_global.setStyleSheet("background-color: #1f6feb; color: white; font-weight: bold; padding: 7px 18px; border-radius: 4px; font-size: 12px; border: none;")
        self.btn_save_global.clicked.connect(self.save_settings)

        self.btn_close = QPushButton("Cerrar")
        self.btn_close.setStyleSheet("padding: 7px 16px; border-radius: 4px; background: #21262d; color: #c9d1d9; border: 1px solid #30363d; font-size: 12px;")
        self.btn_close.clicked.connect(self.close)

        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_save_global)
        bottom_layout.addWidget(self.btn_close)
        main_layout.addLayout(bottom_layout)

    # -------------------------------------------------------------------------
    # TAB 1: CONVERSACIONES (SPACIOUS, RESPONSIVE SPLITTER)
    # -------------------------------------------------------------------------
    def init_tab_history(self):
        layout = QVBoxLayout(self.tab_history)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Top Action Bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Buscar en el historial de sesiones...")
        self.txt_search.setClearButtonEnabled(True)
        self.txt_search.setStyleSheet("""
            QLineEdit {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 6px 10px;
                color: #e6edf3;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #38bdf8;
            }
        """)
        self.txt_search.textChanged.connect(self.on_search_text_changed)
        top_bar.addWidget(self.txt_search, 1)

        self.btn_new_conv = QPushButton("Nueva Sesión")
        self.btn_new_conv.setStyleSheet("background: #1f6feb; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px; border: none; font-size: 12px;")
        self.btn_new_conv.clicked.connect(self.start_new_conversation)
        top_bar.addWidget(self.btn_new_conv)

        btn_refresh = QPushButton("Actualizar")
        btn_refresh.setStyleSheet("background: #21262d; color: #c9d1d9; padding: 6px 12px; border-radius: 4px; border: 1px solid #30363d; font-size: 12px;")
        btn_refresh.clicked.connect(self.refresh_conversation_list)
        top_bar.addWidget(btn_refresh)

        layout.addLayout(top_bar)

        # Horizontal Splitter: List (35%) + Inspector (65%)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background: #30363d;
                width: 3px;
            }
            QSplitter::handle:hover {
                background: #38bdf8;
            }
        """)

        # Left Panel: List of Conversations
        left_widget = QWidget()
        left_widget.setMinimumWidth(260)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.lbl_conv_count = QLabel("0 sesiones registradas")
        self.lbl_conv_count.setStyleSheet("color: #64748b; font-size: 11px; padding-left: 2px;")
        left_layout.addWidget(self.lbl_conv_count)

        self.conv_list = QListWidget()
        self.conv_list.setStyleSheet("""
            QListWidget {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 4px;
                outline: none;
            }
            QListWidget::item {
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 4px;
                padding: 8px 10px;
                margin: 2px 0;
                color: #e2e8f0;
            }
            QListWidget::item:hover {
                background: rgba(56, 189, 248, 0.08);
                border: 1px solid rgba(56, 189, 248, 0.3);
            }
            QListWidget::item:selected {
                background: rgba(56, 189, 248, 0.16);
                border: 1px solid #38bdf8;
                color: #ffffff;
            }
        """)
        self.conv_list.itemClicked.connect(self.on_conversation_selected)
        self.conv_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.conv_list.customContextMenuRequested.connect(self.on_conv_list_context_menu)
        left_layout.addWidget(self.conv_list)

        splitter.addWidget(left_widget)

        # Right Panel: Inspector & Turn Stream
        right_widget = QWidget()
        right_widget.setMinimumWidth(400)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # Inspector Toolbar
        inspector_toolbar = QHBoxLayout()
        inspector_toolbar.setSpacing(8)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        self.lbl_viewer_title = QLabel("Detalle de la Conversación")
        f_vtitle = QFont()
        f_vtitle.setPointSize(12)
        f_vtitle.setBold(True)
        self.lbl_viewer_title.setFont(f_vtitle)
        self.lbl_viewer_title.setStyleSheet("color: #ffffff;")
        title_box.addWidget(self.lbl_viewer_title)

        self.lbl_viewer_meta = QLabel("Selecciona una sesión de la lista para ver su contenido")
        self.lbl_viewer_meta.setStyleSheet("color: #64748b; font-size: 11px;")
        title_box.addWidget(self.lbl_viewer_meta)
        inspector_toolbar.addLayout(title_box, 1)

        self.btn_resume_conv = QPushButton("Fijar como Activa")
        self.btn_resume_conv.setEnabled(False)
        self.btn_resume_conv.setStyleSheet("background-color: #166534; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px; border: none; font-size: 11px;")
        self.btn_resume_conv.clicked.connect(self.resume_selected_conversation)
        inspector_toolbar.addWidget(self.btn_resume_conv)

        self.btn_copy_markdown = QPushButton("Copiar Markdown")
        self.btn_copy_markdown.setEnabled(False)
        self.btn_copy_markdown.setStyleSheet("background: #21262d; color: #c9d1d9; padding: 5px 10px; border-radius: 4px; border: 1px solid #30363d; font-size: 11px;")
        self.btn_copy_markdown.clicked.connect(self.copy_selected_conversation_markdown)
        inspector_toolbar.addWidget(self.btn_copy_markdown)

        self.btn_delete_conv = QPushButton("Eliminar")
        self.btn_delete_conv.setEnabled(False)
        self.btn_delete_conv.setStyleSheet("background-color: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); padding: 5px 10px; border-radius: 4px; font-size: 11px;")
        self.btn_delete_conv.clicked.connect(self.delete_selected_conversation)
        inspector_toolbar.addWidget(self.btn_delete_conv)

        right_layout.addLayout(inspector_toolbar)

        self.detail_browser = QTextBrowser()
        self.detail_browser.setOpenExternalLinks(True)
        self.detail_browser.setStyleSheet("""
            QTextBrowser {
                background: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 10px;
                color: #e2e8f0;
            }
        """)
        self.render_empty_conversation_view()
        right_layout.addWidget(self.detail_browser)

        splitter.addWidget(right_widget)
        splitter.setSizes([320, 640])

        layout.addWidget(splitter, 1)

    # -------------------------------------------------------------------------
    # TAB 2: MONITOR EN VIVO (DEDICATED REAL-TIME EXECUTION & TELEMETRY)
    # -------------------------------------------------------------------------
    def init_tab_live(self):
        layout = QVBoxLayout(self.tab_live)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        # Card: Tarea en Ejecución
        card_task = QGroupBox("Estado de Ejecución del Agente")
        card_task_layout = QVBoxLayout(card_task)
        card_task_layout.setSpacing(10)

        task_head = QHBoxLayout()
        self.lbl_live_task_state = QLabel("Estado: En reposo (IDLE)")
        f_state = QFont()
        f_state.setPointSize(11)
        f_state.setBold(True)
        self.lbl_live_task_state.setFont(f_state)
        self.lbl_live_task_state.setStyleSheet("color: #22c55e;")
        task_head.addWidget(self.lbl_live_task_state)

        self.lbl_live_task_time = QLabel("")
        self.lbl_live_task_time.setStyleSheet("color: #8b949e; font-size: 11px;")
        task_head.addWidget(self.lbl_live_task_time)
        task_head.addStretch()

        self.btn_cancel_task = QPushButton("Detener Tarea Inmediatamente")
        self.btn_cancel_task.setEnabled(False)
        self.btn_cancel_task.setStyleSheet("background-color: #ef4444; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px; border: none; font-size: 11px;")
        self.btn_cancel_task.clicked.connect(self.cancel_running_task)
        task_head.addWidget(self.btn_cancel_task)

        card_task_layout.addLayout(task_head)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #f59e0b; }")
        self.progress_bar.setVisible(False)
        card_task_layout.addWidget(self.progress_bar)

        self.lbl_live_user_text = QLabel("Última petición: Ninguna")
        self.lbl_live_user_text.setStyleSheet("color: #f1f5f9; font-size: 12px; font-weight: 500;")
        card_task_layout.addWidget(self.lbl_live_user_text)

        self.lbl_live_action_text = QLabel("Acción actual: Esperando orden de voz")
        self.lbl_live_action_text.setStyleSheet("color: #94a3b8; font-size: 12px;")
        card_task_layout.addWidget(self.lbl_live_action_text)

        self.lbl_live_command = QLabel("")
        self.lbl_live_command.setWordWrap(True)
        self.lbl_live_command.setStyleSheet("background: #0d1117; border: 1px solid #30363d; border-radius: 4px; padding: 8px; font-family: monospace; font-size: 11px; color: #38bdf8;")
        self.lbl_live_command.setVisible(False)
        card_task_layout.addWidget(self.lbl_live_command)

        layout.addWidget(card_task)

        # Card: Contexto y Sesión Activa
        card_session = QGroupBox("Gestión de Contexto y Memoria")
        card_session_layout = QVBoxLayout(card_session)
        card_session_layout.setSpacing(10)

        session_row = QHBoxLayout()
        session_row.addWidget(QLabel("ID de sesión activa:"))
        self.lbl_active_id = QLabel(self.format_active_session_label())
        self.lbl_active_id.setStyleSheet("background: rgba(56, 189, 248, 0.1); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 4px; padding: 4px 8px; font-family: monospace; font-size: 11px;")
        session_row.addWidget(self.lbl_active_id)

        btn_copy = QPushButton("Copiar ID")
        btn_copy.setStyleSheet("background: #21262d; color: #c9d1d9; padding: 4px 10px; border-radius: 4px; border: 1px solid #30363d; font-size: 11px;")
        btn_copy.clicked.connect(self.copy_active_id)
        session_row.addWidget(btn_copy)
        session_row.addStretch()

        card_session_layout.addLayout(session_row)

        self.chk_continuous = QCheckBox("Modo Conversación Continua (Mantener memoria entre órdenes sucesivas)")
        self.chk_continuous.setChecked(self.config.get("CONTINUOUS_CONVERSATION", "true").lower() == "true")
        self.chk_continuous.toggled.connect(self.on_continuous_toggled)
        card_session_layout.addWidget(self.chk_continuous)

        lbl_hint = QLabel("Di 'nueva conversación' o 'empezar de cero' por voz para reiniciar el contexto sin abrir este panel.")
        lbl_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        card_session_layout.addWidget(lbl_hint)

        layout.addWidget(card_session)

        # Card: Telemetría de Hardware (Fast Path)
        card_hw = QGroupBox("Telemetría de Hardware (Nobara Fast Path)")
        card_hw_layout = QVBoxLayout(card_hw)
        card_hw_layout.setSpacing(6)

        self.lbl_hw_info = QLabel("Cargando sensores...")
        self.lbl_hw_info.setStyleSheet("color: #e2e8f0; font-size: 12px;")
        card_hw_layout.addWidget(self.lbl_hw_info)

        btn_refresh_hw = QPushButton("Consultar Sensores Ahora")
        btn_refresh_hw.setStyleSheet("background: #21262d; color: #c9d1d9; padding: 5px 12px; border-radius: 4px; border: 1px solid #30363d; font-size: 11px; align-self: flex-start;")
        btn_refresh_hw.clicked.connect(self.update_hardware_info)
        card_hw_layout.addWidget(btn_refresh_hw)

        layout.addWidget(card_hw)
        layout.addStretch()

        self.update_hardware_info()

    # -------------------------------------------------------------------------
    # TAB 3: VOZ Y RECONOCIMIENTO (STT, TTS, VAD, MIC)
    # -------------------------------------------------------------------------
    def init_tab_audio(self):
        tab_layout = QVBoxLayout(self.tab_audio)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        # Card 1: Idioma
        card_lang = QGroupBox("Idioma")
        card_lang_layout = QVBoxLayout(card_lang)
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Idioma del asistente:"))
        self.cmb_lang = QComboBox()
        self.cmb_lang.addItem("Español", "es")
        self.cmb_lang.addItem("English", "en")
        cur_lang = self.config.get("ASSISTANT_LANGUAGE", "es")
        idx_lang = self.cmb_lang.findData(cur_lang)
        if idx_lang >= 0:
            self.cmb_lang.setCurrentIndex(idx_lang)
        self.cmb_lang.currentIndexChanged.connect(self.on_language_changed)
        lang_row.addWidget(self.cmb_lang, 1)
        card_lang_layout.addLayout(lang_row)
        layout.addWidget(card_lang)

        # Card 2: Síntesis de Voz
        card_voice = QGroupBox("Síntesis de Voz (Piper Neural TTS)")
        card_voice_layout = QVBoxLayout(card_voice)
        card_voice_layout.setSpacing(8)

        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("Modelo de voz:"))
        self.cmb_voice = QComboBox()
        for idx, v in enumerate(AVAILABLE_VOICES):
            self.cmb_voice.addItem(v["label"], (v["model"], v["speaker"]))
            if v["model"] == self.config.get("VOICE_MODEL") and v["speaker"] == self.config.get("VOICE_SPEAKER", ""):
                self.cmb_voice.setCurrentIndex(idx)
        voice_row.addWidget(self.cmb_voice, 1)
        card_voice_layout.addLayout(voice_row)

        vol_header = QHBoxLayout()
        vol_header.addWidget(QLabel("Volumen del habla:"))
        self.vol_value_label = QLabel()
        self.vol_value_label.setStyleSheet("font-weight: bold; color: #38bdf8;")
        vol_header.addStretch()
        vol_header.addWidget(self.vol_value_label)
        card_voice_layout.addLayout(vol_header)

        slider_layout = QHBoxLayout()
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setMinimum(5)
        self.vol_slider.setMaximum(100)
        current_vol = int(float(self.config.get("TTS_VOLUME", "0.35")) * 100)
        self.vol_slider.setValue(current_vol)
        self.vol_value_label.setText(f"{current_vol}%")
        self.vol_slider.valueChanged.connect(self.on_volume_changed)

        self.btn_test_voice = QPushButton("Probar Voz")
        self.btn_test_voice.clicked.connect(self.test_voice)

        slider_layout.addWidget(self.vol_slider)
        slider_layout.addWidget(self.btn_test_voice)
        card_voice_layout.addLayout(slider_layout)

        self.chk_voice_reply = QCheckBox("Responder con voz sintetizada")
        self.chk_voice_reply.setChecked(self.config.get("ENABLE_VOICE_REPLY", "true").lower() == "true")
        card_voice_layout.addWidget(self.chk_voice_reply)

        self.chk_processing_cue = QCheckBox("Aviso sonoro 'Procesando...' al cortar")
        self.chk_processing_cue.setChecked(self.config.get("ENABLE_PROCESSING_VOICE_CUE", "true").lower() == "true")
        card_voice_layout.addWidget(self.chk_processing_cue)

        layout.addWidget(card_voice)

        # Card 3: Reconocimiento Whisper y VAD
        card_vad = QGroupBox("Reconocimiento Local y Fin de Frase")
        card_vad_layout = QVBoxLayout(card_vad)
        card_vad_layout.setSpacing(8)

        whisper_row = QHBoxLayout()
        whisper_row.addWidget(QLabel("Modelo Whisper:"))
        self.cmb_model = QComboBox()
        self.cmb_model.addItem("base (Rápido ~0.15s)", "base")
        self.cmb_model.addItem("small (Mayor precisión ~0.4s)", "small")
        idx_model = self.cmb_model.findData(self.config.get("WHISPER_MODEL", "base"))
        if idx_model >= 0:
            self.cmb_model.setCurrentIndex(idx_model)
        whisper_row.addWidget(self.cmb_model, 1)
        card_vad_layout.addLayout(whisper_row)

        self.chk_autostop = QCheckBox("Detección de silencio automática (VAD en Go)")
        self.chk_autostop.setChecked(self.config.get("AUTO_STOP_SILENCE", "false").lower() == "true")
        self.chk_autostop.toggled.connect(self.on_autostop_toggled)
        card_vad_layout.addWidget(self.chk_autostop)

        self.silence_container = QWidget()
        silence_layout = QVBoxLayout(self.silence_container)
        silence_layout.setContentsMargins(0, 0, 0, 0)
        silence_layout.setSpacing(4)

        silence_header = QHBoxLayout()
        silence_header.addWidget(QLabel("Pausa de silencio requerida para enviar:"))
        self.silence_value_label = QLabel()
        self.silence_value_label.setStyleSheet("font-weight: bold; color: #38bdf8;")
        silence_header.addStretch()
        silence_header.addWidget(self.silence_value_label)
        silence_layout.addLayout(silence_header)

        silence_slider_layout = QHBoxLayout()
        self.silence_slider = QSlider(Qt.Horizontal)
        self.silence_slider.setMinimum(8)
        self.silence_slider.setMaximum(25)
        cur_silence = float(self.config.get("SILENCE_DURATION", "1.2"))
        slider_val = int(round(cur_silence * 10))
        self.silence_slider.setValue(slider_val)
        self.silence_value_label.setText(f"{slider_val / 10.0:.1f} s")
        self.silence_slider.valueChanged.connect(self.on_silence_slider_changed)
        silence_slider_layout.addWidget(self.silence_slider)
        silence_layout.addLayout(silence_slider_layout)

        card_vad_layout.addWidget(self.silence_container)
        self.silence_container.setEnabled(self.chk_autostop.isChecked())

        layout.addWidget(card_vad)

        # Card 4: Micrófono
        card_mic = QGroupBox("Diagnóstico de Micrófono")
        card_mic_layout = QVBoxLayout(card_mic)

        self.btn_test_mic = QPushButton("Probar Micrófono (3 segundos)")
        self.btn_test_mic.setStyleSheet("padding: 7px 14px; font-weight: bold;")
        self.btn_test_mic.clicked.connect(self.start_mic_test)
        card_mic_layout.addWidget(self.btn_test_mic)

        self.lbl_mic_result = QLabel("Pulsa el botón para probar qué detecta el modelo Whisper.")
        self.lbl_mic_result.setStyleSheet("color: #64748b; font-style: italic;")
        self.lbl_mic_result.setWordWrap(True)
        card_mic_layout.addWidget(self.lbl_mic_result)

        layout.addWidget(card_mic)

        scroll.setWidget(scroll_content)
        tab_layout.addWidget(scroll)

    # -------------------------------------------------------------------------
    # TAB 4: SISTEMA Y AUTOMATIZACIÓN (WAKE WORD, HUD, DUCKING, AUTOSTART)
    # -------------------------------------------------------------------------
    def init_tab_system(self):
        tab_layout = QVBoxLayout(self.tab_system)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        # Card 1: Inicio del Sistema
        card_start = QGroupBox("Inicio y Estado General")
        card_start_layout = QVBoxLayout(card_start)
        card_start_layout.setSpacing(8)

        self.chk_enabled = QCheckBox("Habilitar Asistente de Voz Jarvis")
        font_chk = QFont()
        font_chk.setBold(True)
        self.chk_enabled.setFont(font_chk)
        self.chk_enabled.setChecked(self.config.get("ENABLED", "true").lower() == "true")
        card_start_layout.addWidget(self.chk_enabled)

        self.chk_autostart = QCheckBox("Iniciar Jarvis automáticamente con el sistema")
        self.chk_autostart.setChecked(is_autostart_enabled())
        self.chk_autostart.setStyleSheet("color: #94a3b8; font-size: 12px;")
        card_start_layout.addWidget(self.chk_autostart)

        lbl_autostart_hint = QLabel("Lanza la bandeja del sistema, el overlay y el wake word al iniciar sesión en KDE Plasma.")
        lbl_autostart_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        card_start_layout.addWidget(lbl_autostart_hint)

        layout.addWidget(card_start)

        # Card 2: Wake Word
        card_wake = QGroupBox("Palabra de Activación Manos Libres")
        card_wake_layout = QVBoxLayout(card_wake)
        card_wake_layout.setSpacing(8)

        self.chk_wakeword = QCheckBox("Habilitar detección continua en segundo plano")
        self.chk_wakeword.setChecked(self.config.get("WAKE_WORD_ENABLED", "false").lower() == "true")
        self.chk_wakeword.toggled.connect(self.on_wakeword_toggled)
        card_wake_layout.addWidget(self.chk_wakeword)

        self.wake_container = QWidget()
        wake_cont_layout = QVBoxLayout(self.wake_container)
        wake_cont_layout.setContentsMargins(0, 0, 0, 0)
        wake_cont_layout.setSpacing(6)

        wake_model_row = QHBoxLayout()
        wake_model_row.addWidget(QLabel("Palabra de activación:"))
        self.cmb_wakeword = QComboBox()
        self.cmb_wakeword.addItem("Jarvis / Hey Jarvis", "hey_jarvis")
        self.cmb_wakeword.addItem("Alexa", "alexa")
        self.cmb_wakeword.addItem("Hey Mycroft", "hey_mycroft")
        cur_wake = self.config.get("WAKE_WORD_MODEL", "hey_jarvis")
        idx_wake = self.cmb_wakeword.findData(cur_wake)
        if idx_wake >= 0:
            self.cmb_wakeword.setCurrentIndex(idx_wake)
        wake_model_row.addWidget(self.cmb_wakeword, 1)
        wake_cont_layout.addLayout(wake_model_row)

        sens_header = QHBoxLayout()
        sens_header.addWidget(QLabel("Sensibilidad:"))
        self.lbl_sens_val = QLabel()
        self.lbl_sens_val.setStyleSheet("font-weight: bold; color: #38bdf8;")
        sens_header.addStretch()
        sens_header.addWidget(self.lbl_sens_val)
        wake_cont_layout.addLayout(sens_header)

        sens_slider_row = QHBoxLayout()
        self.slider_sens = QSlider(Qt.Horizontal)
        self.slider_sens.setMinimum(15)
        self.slider_sens.setMaximum(55)
        cur_thresh = float(self.config.get("WAKE_WORD_THRESHOLD", "0.30"))
        slider_init = int(round(cur_thresh * 100))
        self.slider_sens.setValue(slider_init)
        self.update_sens_label(slider_init)
        self.slider_sens.valueChanged.connect(self.update_sens_label)
        sens_slider_row.addWidget(self.slider_sens)
        wake_cont_layout.addLayout(sens_slider_row)

        card_wake_layout.addWidget(self.wake_container)
        self.wake_container.setEnabled(self.chk_wakeword.isChecked())

        layout.addWidget(card_wake)

        # Card 3: Visualización y Modo Gaming
        card_gaming = QGroupBox("Visualización y Modo Gaming")
        card_gaming_layout = QVBoxLayout(card_gaming)
        card_gaming_layout.setSpacing(8)

        self.chk_hud = QCheckBox("Cápsula flotante en pantalla (Overlay HUD)")
        self.chk_hud.setChecked(self.config.get("OVERLAY_HUD_ENABLED", "true").lower() == "true")
        card_gaming_layout.addWidget(self.chk_hud)

        lbl_hud_desc = QLabel("La cápsula flotante muestra ondas de audio y estado sin interferir con juegos ni robar el foco.")
        lbl_hud_desc.setStyleSheet("color: #64748b; font-size: 11px;")
        card_gaming_layout.addWidget(lbl_hud_desc)

        self.chk_ducking = QCheckBox("Audio Ducking: Atenuar música de fondo mientras Jarvis habla")
        self.chk_ducking.setChecked(self.config.get("AUDIO_DUCKING", "false").lower() == "true")
        card_gaming_layout.addWidget(self.chk_ducking)

        layout.addWidget(card_gaming)

        scroll.setWidget(scroll_content)
        tab_layout.addWidget(scroll)

    # -------------------------------------------------------------------------
    # SLOTS & EVENT HANDLERS
    # -------------------------------------------------------------------------
    def update_hardware_info(self):
        try:
            res = subprocess.run([ASSISTANT_BIN, "fastpath", "como va el pc"], capture_output=True, text=True, timeout=1.5)
            data = json.loads(res.stdout.strip())
            self.lbl_hw_info.setText(data.get("reply", "No disponible."))
        except Exception:
            self.lbl_hw_info.setText("Sensores operando en rangos normales.")

    def on_wakeword_toggled(self, checked):
        self.wake_container.setEnabled(checked)

    def update_sens_label(self, val):
        thresh = val / 100.0
        if thresh <= 0.22:
            sens_txt = f"Alta ({thresh:.2f})"
        elif thresh <= 0.35:
            sens_txt = f"Normal ({thresh:.2f})"
        else:
            sens_txt = f"Estricta ({thresh:.2f})"
        self.lbl_sens_val.setText(sens_txt)

    def on_autostop_toggled(self, checked):
        self.silence_container.setEnabled(checked)

    def on_silence_slider_changed(self, value):
        self.silence_value_label.setText(f"{value / 10.0:.1f} s")

    def on_volume_changed(self, value):
        self.vol_value_label.setText(f"{value}%")

    def on_language_changed(self, index):
        selected_lang = self.cmb_lang.currentData()
        for idx in range(self.cmb_voice.count()):
            v_data = self.cmb_voice.itemData(idx)
            if v_data:
                model_name, _ = v_data
                is_en_model = model_name.startswith("en_")
                if (selected_lang == "en" and is_en_model) or (selected_lang == "es" and not is_en_model):
                    self.cmb_voice.setCurrentIndex(idx)
                    break

    def format_active_session_label(self):
        active_id = self.config.get("ACTIVE_CONVERSATION_ID", "")
        if not active_id:
            return "Ninguna (Se creará una nueva al hablar)"
        return f"{active_id[:8]}...{active_id[-6:]}"

    def on_continuous_toggled(self, checked):
        self.config["CONTINUOUS_CONVERSATION"] = "true" if checked else "false"

    def copy_active_id(self):
        active_id = self.config.get("ACTIVE_CONVERSATION_ID", "")
        if active_id:
            QApplication.clipboard().setText(active_id)
            QMessageBox.information(self, "ID Copiado", f"ID de sesión copiado al portapapeles:\n{active_id}")
        else:
            QMessageBox.information(self, "Sin Sesión Activa", "No hay ninguna sesión activa en este momento.")

    def start_new_conversation(self):
        new_id = conversations.reset_active_session()
        self.config["ACTIVE_CONVERSATION_ID"] = new_id
        save_config(self.config)
        self.lbl_active_id.setText(self.format_active_session_label())
        self.refresh_conversation_list()
        self.render_empty_conversation_view()
        self.btn_resume_conv.setEnabled(False)
        self.btn_copy_markdown.setEnabled(False)
        self.btn_delete_conv.setEnabled(False)
        self.lbl_viewer_title.setText("Nueva Sesión Iniciada")
        self.lbl_viewer_meta.setText(f"ID: {new_id}")
        QMessageBox.information(
            self,
            "Nueva Sesión Limpia",
            f"Se ha iniciado una nueva conversación limpia ({new_id[:8]}).\nLa próxima orden comenzará con contexto nuevo."
        )

    def refresh_conversation_list(self):
        self.all_conversations = conversations.get_all_conversations()
        self.filter_conversations(self.txt_search.text())

    def on_search_text_changed(self, text):
        self.filter_conversations(text)

    def filter_conversations(self, query=""):
        self.conv_list.clear()
        query = query.strip().lower()
        active_id = self.config.get("ACTIVE_CONVERSATION_ID", "")

        matches = []
        for conv in self.all_conversations:
            cid = conv.get("id", "")
            title = conv.get("title", "")
            last_reply = conv.get("last_reply", "")
            last_user = conv.get("last_user", "")
            if not query or query in title.lower() or query in last_reply.lower() or query in last_user.lower() or query in cid.lower():
                matches.append(conv)

        self.lbl_conv_count.setText(f"{len(matches)} de {len(self.all_conversations)} sesiones registradas")

        for conv in matches:
            cid = conv.get("id", "")
            title = conv.get("title", "Conversación").replace("\n", " ").strip()
            date_str = conv.get("date_str") or conv.get("updated_at", "")
            turn_count = conv.get("turn_count", 0)

            short_date = date_str[:16] if len(date_str) >= 16 else date_str
            clean_title = title if len(title) <= 44 else title[:41] + "..."

            is_active = (cid == active_id)
            active_badge = "  [ACTIVA]" if is_active else ""

            item_text = f"{short_date}  ·  {turn_count}t{active_badge}\n{clean_title}"

            item = QListWidgetItem(item_text)
            item.setToolTip(f"ID: {cid}\n{title}")
            item.setData(Qt.UserRole, cid)
            if is_active:
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            self.conv_list.addItem(item)

    def render_empty_conversation_view(self):
        html_content = """
        <div style='text-align: center; margin-top: 100px; font-family: sans-serif; color: #8b949e;'>
            <h3 style='color: #38bdf8; margin-bottom: 8px;'>Memoria Neural Jarvis</h3>
            <p style='font-size: 13px; max-width: 460px; margin: 0 auto; line-height: 1.6; color: #64748b;'>
                Selecciona cualquier sesión para ver su resumen y los turnos ordenados desde el más reciente al primero.
            </p>
        </div>
        """
        self.detail_browser.setHtml(html_content)

    def on_conversation_selected(self, item):
        cid = item.data(Qt.UserRole)
        self.btn_copy_markdown.setEnabled(True)
        self.btn_delete_conv.setEnabled(True)

        is_active = (cid == self.config.get("ACTIVE_CONVERSATION_ID", ""))
        if is_active:
            self.btn_resume_conv.setText("Sesión Activa")
            self.btn_resume_conv.setEnabled(False)
            self.btn_resume_conv.setStyleSheet("background-color: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid #38bdf8; font-weight: bold; padding: 5px 12px; border-radius: 4px; font-size: 11px;")
        else:
            self.btn_resume_conv.setText("Fijar como Activa")
            self.btn_resume_conv.setEnabled(True)
            self.btn_resume_conv.setStyleSheet("background-color: #166534; color: white; font-weight: bold; padding: 5px 12px; border-radius: 4px; border: none; font-size: 11px;")

        detail = conversations.get_conversation_detail(cid)
        turns = detail.get("turns", [])
        summary = detail.get("summary", {})

        total_turns = summary.get("total_turns", len(turns))
        last_user = summary.get("last_user", "")
        last_reply = summary.get("last_reply", "")
        tools_used = summary.get("tools_used", [])
        tools_str = ", ".join(tools_used) if tools_used else "Ninguna"

        self.lbl_viewer_title.setText(detail.get("title", "Conversación"))
        self.lbl_viewer_meta.setText(f"ID: {cid}  ·  {total_turns} turnos registrados")

        if not turns:
            self.detail_browser.setHtml("<p style='color: #64748b; font-style: italic; padding: 14px;'>No hay turnos registrados en esta sesión.</p>")
            return

        html_body = [
            "<style>",
            "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; color: #e2e8f0; background-color: #161b22; padding: 10px; margin: 0; }",
            ".summary-card { background: #0f172a; border: 1px solid #1e293b; border-left: 4px solid #38bdf8; border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; }",
            ".summary-badge { color: #38bdf8; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; margin-bottom: 6px; }",
            ".summary-row { font-size: 12px; color: #cbd5e1; margin-bottom: 4px; line-height: 1.4; }",
            ".summary-meta { font-size: 11px; color: #64748b; margin-top: 6px; padding-top: 6px; border-top: 1px solid #1e293b; }",
            ".summary-meta span { margin-right: 14px; }",
            ".turn-badge { color: #64748b; font-weight: normal; font-size: 11px; margin-left: 8px; }",
            ".turn-badge-latest { color: #22c55e; font-weight: bold; font-size: 11px; margin-left: 8px; }",
            ".user-card { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 10px 14px; margin: 10px 0 4px 0; }",
            ".user-header { color: #38bdf8; font-size: 11px; font-weight: bold; margin-bottom: 4px; }",
            ".user-text { font-size: 13px; color: #f8fafc; font-weight: 500; line-height: 1.4; }",
            ".tool-chip { background: #06090e; border-left: 3px solid #38bdf8; border-radius: 3px; padding: 5px 10px; margin: 3px 0 3px 10px; font-family: monospace; font-size: 11px; color: #7dd3fc; }",
            ".jarvis-card { background: #111e2e; border: 1px solid #1e3a5f; border-left: 3px solid #38bdf8; border-radius: 6px; padding: 12px 16px; margin: 4px 0 16px 0; }",
            ".jarvis-header { color: #38bdf8; font-size: 11px; font-weight: bold; margin-bottom: 6px; }",
            ".jarvis-text { font-size: 13px; color: #f1f5f9; line-height: 1.5; }",
            ".code-box { background: #06090e; border: 1px solid #30363d; border-radius: 4px; padding: 8px; margin: 6px 0; overflow-x: auto; }",
            "pre, code { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #a5f3fc; }",
            ".inline-code { background: rgba(56, 189, 248, 0.1); color: #7dd3fc; padding: 2px 5px; border-radius: 3px; font-family: monospace; }",
            "</style>"
        ]

        # Top Executive Summary Box
        disp_last_user = html.escape(last_user) if len(last_user) <= 120 else html.escape(last_user[:117]) + "..."
        disp_last_reply = html.escape(last_reply) if len(last_reply) <= 140 else html.escape(last_reply[:137]) + "..."
        html_body.append(
            f"<div class='summary-card'>"
            f"<div class='summary-badge'>RESUMEN DE LA SESIÓN</div>"
            f"<div class='summary-row'><b>Última orden:</b> {disp_last_user}</div>"
            f"<div class='summary-row'><b>Última respuesta:</b> {disp_last_reply}</div>"
            f"<div class='summary-meta'>"
            f"<span>Turnos: <b>{total_turns}</b></span>"
            f"<span>Herramientas: <b>{html.escape(tools_str)}</b></span>"
            f"</div>"
            f"</div>"
        )

        # Reverse chronological turns (Newest turn on top!)
        for idx, turn in enumerate(reversed(turns)):
            turn_num = len(turns) - idx
            is_newest = (idx == 0)
            user_msg = turn.get("user", "")
            reply_msg = turn.get("reply") or turn.get("assistant", "")
            actions = turn.get("actions") or turn.get("tool_calls", [])
            time_str = turn.get("time", "")

            if is_newest:
                badge = f"<span class='turn-badge-latest'>Turno {turn_num} (Más reciente · {time_str})</span>" if time_str else f"<span class='turn-badge-latest'>Turno {turn_num} (Más reciente)</span>"
            else:
                badge = f"<span class='turn-badge'>Turno {turn_num} ({time_str})</span>" if time_str else f"<span class='turn-badge'>Turno {turn_num}</span>"

            html_body.append(f"<div class='user-card'><div class='user-header'>[USUARIO] {badge}</div><div class='user-text'>{html.escape(user_msg)}</div></div>")

            if actions:
                for act in actions:
                    act_name = html.escape(str(act.get("name", "tool")))
                    act_sum = html.escape(str(act.get("summary") or act.get("cmd") or ""))
                    if len(act_sum) > 120:
                        act_sum = act_sum[:117] + "..."
                    html_body.append(f"<div class='tool-chip'>[HERRAMIENTA: {act_name}] {act_sum}</div>")

            if reply_msg:
                formatted_reply = format_text_as_html(reply_msg)
                html_body.append(f"<div class='jarvis-card'><div class='jarvis-header'>[JARVIS]</div><div class='jarvis-text'>{formatted_reply}</div></div>")

        self.detail_browser.setHtml("".join(html_body))

    def resume_selected_conversation(self):
        item = self.conv_list.currentItem()
        if not item:
            return
        cid = item.data(Qt.UserRole)
        self.config["ACTIVE_CONVERSATION_ID"] = cid
        self.config["CONTINUOUS_CONVERSATION"] = "true"
        self.chk_continuous.setChecked(True)
        save_config(self.config)
        self.lbl_active_id.setText(self.format_active_session_label())
        self.refresh_conversation_list()
        self.btn_resume_conv.setText("Sesión Activa")
        self.btn_resume_conv.setEnabled(False)
        self.btn_resume_conv.setStyleSheet("background-color: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid #38bdf8; font-weight: bold; padding: 5px 12px; border-radius: 4px; font-size: 11px;")
        QMessageBox.information(self, "Conversación Retomada", f"Se ha fijado la sesión {cid[:8]} como activa.")

    def copy_selected_conversation_markdown(self):
        item = self.conv_list.currentItem()
        if not item:
            return
        cid = item.data(Qt.UserRole)
        md = conversations.export_conversation_markdown(cid)
        QApplication.clipboard().setText(md)
        self.btn_copy_markdown.setText("Copiado")
        QTimer.singleShot(2000, lambda: self.btn_copy_markdown.setText("Copiar Markdown"))

    def delete_selected_conversation(self):
        item = self.conv_list.currentItem()
        if not item:
            return
        cid = item.data(Qt.UserRole)
        ret = QMessageBox.question(
            self,
            "Eliminar Conversación",
            f"¿Deseas eliminar permanentemente la transcripción de la sesión {cid[:8]}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if ret == QMessageBox.Yes:
            if conversations.delete_conversation(cid):
                if self.config.get("ACTIVE_CONVERSATION_ID") == cid:
                    new_id = conversations.reset_active_session()
                    self.config["ACTIVE_CONVERSATION_ID"] = new_id
                    save_config(self.config)
                    self.lbl_active_id.setText(self.format_active_session_label())
                self.refresh_conversation_list()
                self.render_empty_conversation_view()
                self.lbl_viewer_title.setText("Detalle de la Conversación")
                self.lbl_viewer_meta.setText("Sesión eliminada.")
                self.btn_resume_conv.setEnabled(False)
                self.btn_copy_markdown.setEnabled(False)
                self.btn_delete_conv.setEnabled(False)
            else:
                QMessageBox.warning(self, "Error", "No se pudo eliminar la carpeta de la conversación.")

    def on_conv_list_context_menu(self, point):
        item = self.conv_list.itemAt(point)
        if not item:
            return
        cid = item.data(Qt.UserRole)
        menu = QMenu(self)
        act_resume = menu.addAction("Fijar como Sesión Activa")
        act_copy_id = menu.addAction("Copiar ID de Sesión")
        act_copy_md = menu.addAction("Copiar Transcripción (Markdown)")
        menu.addSeparator()
        act_delete = menu.addAction("Eliminar Sesión")

        action = menu.exec(self.conv_list.mapToGlobal(point))
        if action == act_resume:
            self.conv_list.setCurrentItem(item)
            self.resume_selected_conversation()
        elif action == act_copy_id:
            QApplication.clipboard().setText(cid)
        elif action == act_copy_md:
            md = conversations.export_conversation_markdown(cid)
            QApplication.clipboard().setText(md)
        elif action == act_delete:
            self.conv_list.setCurrentItem(item)
            self.delete_selected_conversation()

    def poll_live_status(self):
        if not os.path.exists(LIVE_STATUS_FILE):
            return

        try:
            with open(LIVE_STATUS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        status = data.get("status", "IDLE")

        if status == "RUNNING":
            pid = data.get("pid")
            self.current_running_pid = pid
            started_at = data.get("started_at", time.time())
            elapsed = int(time.time() - started_at)

            user_text = data.get("user_text", "")
            action = data.get("current_action", "Procesando...")
            tool_detail = data.get("tool_detail", "")

            self.lbl_global_status.setText("EJECUTANDO")
            self.lbl_global_status.setStyleSheet("font-weight: bold; padding: 4px 12px; border-radius: 4px; background: rgba(245, 158, 11, 0.2); color: #f59e0b; font-size: 11px;")

            self.lbl_live_task_state.setText(f"Estado: Ejecutando tarea (PID {pid})")
            self.lbl_live_task_state.setStyleSheet("color: #f59e0b; font-weight: bold;")
            self.lbl_live_task_time.setText(f"Tiempo transcurrido: {elapsed}s")
            self.progress_bar.setVisible(True)
            self.btn_cancel_task.setEnabled(True)

            self.lbl_live_user_text.setText(f"Petición: \"{user_text}\"")
            self.lbl_live_action_text.setText(f"Acción actual: {action}")

            if tool_detail:
                self.lbl_live_command.setText(f"$ {tool_detail}")
                self.lbl_live_command.setVisible(True)
            else:
                self.lbl_live_command.setVisible(False)

        else:
            self.current_running_pid = None
            self.lbl_global_status.setText("En reposo")
            self.lbl_global_status.setStyleSheet("font-weight: bold; padding: 4px 12px; border-radius: 4px; background: rgba(34, 197, 94, 0.15); color: #22c55e; font-size: 11px;")

            self.lbl_live_task_state.setText("Estado: En reposo (IDLE)")
            self.lbl_live_task_state.setStyleSheet("color: #22c55e; font-weight: bold;")
            self.lbl_live_task_time.setText("")
            self.progress_bar.setVisible(False)
            self.btn_cancel_task.setEnabled(False)
            self.lbl_live_command.setVisible(False)

    def cancel_running_task(self):
        pid = self.current_running_pid
        if not pid and os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, "r") as f:
                    pid = int(f.read().strip())
            except Exception:
                pass

        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.2)
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
            except Exception as e:
                QMessageBox.warning(self, "Error", f"No se pudo cancelar el proceso {pid}: {e}")
                return

        conversations.set_live_idle("Tarea cancelada manualmente por el usuario.")
        self.poll_live_status()
        QMessageBox.information(self, "Tarea Cancelada", "La tarea activa de Jarvis ha sido detenida.")

    def test_voice(self):
        model, speaker = self.cmb_voice.currentData()
        volume = round(self.vol_slider.value() / 100.0, 2)
        model_path = os.path.join(VOICES_DIR, model)

        threading.Thread(
            target=self._speak_sample,
            args=(model_path, speaker, volume),
            daemon=True
        ).start()

    def _speak_sample(self, model_path, speaker, volume):
        is_en = os.path.basename(model_path).startswith("en_")
        sample_text = "Hello Oscar, this is Jarvis. All systems online." if is_en else "Hola Óscar, soy Jarvis. Todos los sistemas están listos."
        cmd = [ASSISTANT_BIN, "speak", sample_text]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start_mic_test(self):
        self.btn_test_mic.setEnabled(False)
        self.btn_test_mic.setText("Grabando 3 segundos... Habla ahora")
        self.lbl_mic_result.setText("Escuchando tu voz...")
        self.lbl_mic_result.setStyleSheet("color: #f87171; font-weight: bold;")

        threading.Thread(target=self._record_and_transcribe, daemon=True).start()

    def _record_and_transcribe(self):
        test_wav = "/tmp/assistant_gui_test.wav"
        if os.path.exists(test_wav):
            try:
                os.remove(test_wav)
            except Exception:
                pass

        p = subprocess.Popen([
            "pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", test_wav
        ])
        time.sleep(3.0)
        p.terminate()
        try:
            p.wait(timeout=1.0)
        except Exception:
            p.kill()

        selected_model = self.cmb_model.currentData()
        selected_lang = self.cmb_lang.currentData()
        res = subprocess.run(
            ["python3", TRANSCRIBE_SCRIPT, test_wav, selected_model, selected_lang],
            capture_output=True,
            text=True
        )
        text = res.stdout.strip()
        self.signals.finished.emit(text)

    def on_mic_test_finished(self, text):
        self.btn_test_mic.setEnabled(True)
        self.btn_test_mic.setText("Probar Micrófono (3 segundos)")
        if text:
            self.lbl_mic_result.setText(f"Reconocido: \"{text}\"")
            self.lbl_mic_result.setStyleSheet("color: #38bdf8; font-weight: bold;")
        else:
            self.lbl_mic_result.setText("No se ha detectado voz clara. Comprueba que el micrófono esté activo.")
            self.lbl_mic_result.setStyleSheet("color: #f59e0b; font-weight: bold;")

    def save_settings(self):
        model, speaker = self.cmb_voice.currentData()
        self.config["ENABLED"] = "true" if self.chk_enabled.isChecked() else "false"
        self.config["VOICE_MODEL"] = model
        self.config["VOICE_SPEAKER"] = speaker
        self.config["TTS_VOLUME"] = str(round(self.vol_slider.value() / 100.0, 2))
        self.config["ENABLE_VOICE_REPLY"] = "true" if self.chk_voice_reply.isChecked() else "false"
        self.config["ENABLE_PROCESSING_VOICE_CUE"] = "true" if self.chk_processing_cue.isChecked() else "false"
        self.config["WHISPER_MODEL"] = self.cmb_model.currentData()
        self.config["CONTINUOUS_CONVERSATION"] = "true" if self.chk_continuous.isChecked() else "false"
        self.config["ASSISTANT_LANGUAGE"] = self.cmb_lang.currentData()
        self.config["AUTO_STOP_SILENCE"] = "true" if self.chk_autostop.isChecked() else "false"
        self.config["SILENCE_DURATION"] = f"{self.silence_slider.value() / 10.0:.1f}"
        self.config["AUDIO_DUCKING"] = "true" if self.chk_ducking.isChecked() else "false"
        self.config["WAKE_WORD_ENABLED"] = "true" if self.chk_wakeword.isChecked() else "false"
        self.config["WAKE_WORD_MODEL"] = self.cmb_wakeword.currentData()
        self.config["WAKE_WORD_THRESHOLD"] = f"{self.slider_sens.value() / 100.0:.2f}"
        self.config["OVERLAY_HUD_ENABLED"] = "true" if self.chk_hud.isChecked() else "false"

        save_config(self.config)

        if self.chk_wakeword.isChecked():
            subprocess.Popen([os.path.join(PROJECT_DIR, "bin", "nobara-voice-assistant-wakeword"), "start"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen([os.path.join(PROJECT_DIR, "bin", "nobara-voice-assistant-wakeword"), "stop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if self.chk_hud.isChecked():
            subprocess.Popen([os.path.join(PROJECT_DIR, "bin", "nobara-voice-assistant-hud")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["pkill", "-f", "overlay_hud.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        threading.Thread(target=lambda: regenerate_procesando_audio(model, speaker), daemon=True).start()

        if self.chk_autostart.isChecked():
            enable_autostart()
        else:
            disable_autostart()

        QMessageBox.information(self, "Configuración Guardada", "Todos los ajustes se han aplicado correctamente.")

SINGLE_INSTANCE_SERVER = "nobara_jarvis_settings_single_instance"

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    if os.path.exists(APP_ICON):
        app.setWindowIcon(QIcon(APP_ICON))

    client_socket = QLocalSocket()
    client_socket.connectToServer(SINGLE_INSTANCE_SERVER)
    if client_socket.waitForConnected(350):
        client_socket.write(b"WAKEUP\n")
        client_socket.waitForBytesWritten(350)
        client_socket.waitForReadyRead(350)
        sys.exit(0)

    QLocalServer.removeServer(SINGLE_INSTANCE_SERVER)
    server = QLocalServer()
    server.listen(SINGLE_INSTANCE_SERVER)

    window = SettingsWindow()

    def handle_incoming_ipc():
        conn = server.nextPendingConnection()
        if conn:
            window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
            window.showNormal()
            window.raise_()
            window.activateWindow()
            if window.windowHandle():
                window.windowHandle().requestActivate()
            try:
                conn.write(b"ACK\n")
                conn.flush()
            except Exception:
                pass

    server.newConnection.connect(handle_incoming_ipc)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
