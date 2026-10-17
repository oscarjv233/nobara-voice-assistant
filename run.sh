#!/usr/bin/env bash
# ==============================================================================
# Nobara AI Voice Assistant - Quick Launcher
# Usage:
#   ./run.sh           -> Opens the Settings and Live Monitor GUI
#   ./run.sh --toggle  -> Triggers the voice assistant recording/processing toggle
#   ./run.sh --install -> Runs the full automated system installer
# ==============================================================================
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export DISPLAY="${DISPLAY:-:0}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export XDG_CURRENT_DESKTOP="KDE"
export PATH="$HOME/.gemini/antigravity-cli/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

case "$1" in
    --install|-i)
        exec "$PROJECT_DIR/install.sh"
        ;;
    --toggle|-t)
        exec "$PROJECT_DIR/bin/nobara-voice-assistant"
        ;;
    *)
        exec "$PROJECT_DIR/bin/nobara-voice-assistant-settings"
        ;;
esac
