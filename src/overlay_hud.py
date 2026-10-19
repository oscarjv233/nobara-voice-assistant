#!/usr/bin/env python3
"""
Nobara AI Voice Assistant - Floating HUD Overlay Capsule.
Provides a modern translucent on-screen visualizer:
- Top-center floating capsule with rounded corners and subtle border.
- Does not accept keyboard/mouse focus (does not interfere with games).
- Displays live states (Listening, Processing, Completed).
- Automatically fades out when completed.
"""
import sys
import os
import json
import time
import fcntl

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen

HUD_STATE_FILE = "/tmp/nobara_assistant_hud.json"
HUD_LOCK_FILE = "/tmp/nobara_assistant_hud.lock"
PID_FILE = "/tmp/nobara_assistant.pid"
LIVE_STATUS_FILE = "/tmp/nobara_assistant_live.json"

class WaveformWidget(QWidget):
    """Animated audio level bars."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 20)
        self.phase = 0
        self.active = False
        self.color = QColor(231, 76, 60)

    def set_active(self, active, color=None):
        self.active = active
        if color:
            self.color = color
        self.update()

    def advance(self):
        if self.active:
            self.phase = (self.phase + 1) % 360
            self.update()

    def paintEvent(self, event):
        if not self.active:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(self.color))
        painter.setPen(Qt.NoPen)

        import math
        for i in range(5):
            angle = math.radians(self.phase * 8 + i * 45)
            h = int(4 + 10 * abs(math.sin(angle)))
            x = i * 8 + 1
            y = (self.height() - h) // 2
            painter.drawRoundedRect(x, y, 4, h, 2, 2)
        painter.end()

class FloatingHudWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self.setFixedWidth(440)
        self.setFixedHeight(76)

        self.init_ui()
        self.reposition_top_center()

        self.last_state = "IDLE"
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_hud)

        # Animation tick timer (25 fps)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.on_anim_tick)
        self.anim_timer.start(40)

        # State poll timer (every 100ms)
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_state)
        self.poll_timer.start(100)

        self.hide()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.wave_widget = WaveformWidget()
        top_row.addWidget(self.wave_widget)

        self.lbl_title = QLabel("Escuchando audio...")
        font_title = QFont()
        font_title.setPointSize(10)
        font_title.setBold(True)
        self.lbl_title.setFont(font_title)
        self.lbl_title.setStyleSheet("color: #ffffff;")
        top_row.addWidget(self.lbl_title, 1)

        layout.addLayout(top_row)

        self.lbl_body = QLabel("Habla ahora.")
        font_body = QFont()
        font_body.setPointSize(9)
        self.lbl_body.setFont(font_body)
        self.lbl_body.setStyleSheet("color: #94a3b8;")
        self.lbl_body.setWordWrap(True)
        layout.addWidget(self.lbl_body)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_color = QColor(15, 20, 28, 240)
        border_color = QColor(56, 189, 248, 140) if self.last_state == "PROCESSING" else QColor(231, 76, 60, 140) if self.last_state == "LISTENING" else QColor(71, 85, 105, 120)

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.2))
        painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 14, 14)
        painter.end()

    def reposition_top_center(self):
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.x() + (geom.width() - self.width()) // 2
            y = geom.y() + 20
            self.move(x, y)

    def on_anim_tick(self):
        self.wave_widget.advance()

    def hide_hud(self):
        self.hide()
        self.last_state = "IDLE"

    def poll_state(self):
        # 1. Recording state
        if os.path.exists(PID_FILE):
            if self.last_state != "LISTENING":
                self.last_state = "LISTENING"
                self.lbl_title.setText("Escuchando orden...")
                self.lbl_body.setText("Habla con claridad. Se procesará automáticamente.")
                self.wave_widget.set_active(True, QColor(231, 76, 60))
                self.hide_timer.stop()
                self.show()
                self.update()
            return

        # 2. Processing state
        if os.path.exists(LIVE_STATUS_FILE):
            try:
                with open(LIVE_STATUS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("status") == "RUNNING":
                    if self.last_state != "PROCESSING":
                        self.last_state = "PROCESSING"
                        action = data.get("current_action", "Procesando orden...")
                        user_text = data.get("user_text", "")
                        self.lbl_title.setText("Procesando tarea...")
                        self.lbl_body.setText(f"Entrada: \"{user_text}\"\n{action}")
                        self.wave_widget.set_active(True, QColor(56, 189, 248))
                        self.hide_timer.stop()
                        self.show()
                        self.update()
                    else:
                        action = data.get("current_action", "")
                        tool = data.get("tool_detail", "")
                        if tool:
                            self.lbl_body.setText(f"{action} ({tool})")
                    return
            except Exception:
                pass

        # 3. Completion events
        if os.path.exists(HUD_STATE_FILE):
            try:
                with open(HUD_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                os.remove(HUD_STATE_FILE)
                title = data.get("title", "Asistente Nobara")
                reply = data.get("reply", "Orden completada.")
                self.lbl_title.setText(title)
                self.lbl_body.setText(reply)
                self.wave_widget.set_active(True, QColor(34, 197, 94))
                self.last_state = "DONE"
                self.show()
                self.update()
                self.hide_timer.start(3000)
                return
            except Exception:
                pass

        if self.last_state in ("LISTENING", "PROCESSING"):
            self.last_state = "DONE"
            self.lbl_title.setText("Orden finalizada")
            self.wave_widget.set_active(False)
            self.update()
            self.hide_timer.start(2000)

def main():
    try:
        lock_fd = open(HUD_LOCK_FILE, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, BlockingIOError, PermissionError):
        sys.exit(0)

    app = QApplication.instance() or QApplication(sys.argv)
    hud = FloatingHudWindow()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
