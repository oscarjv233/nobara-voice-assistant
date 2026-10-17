#!/usr/bin/env bash
# ==============================================================================
# Nobara / Linux AI Voice Assistant - Complete Automated Installer
# Sets up dependencies, voices, Antigravity CLI, rules, shortcuts & desktop apps.
# Open Source (MIT License)
# ==============================================================================
set -e

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
PROJECT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}"
echo "=============================================================================="
echo "      🎙️  Nobara / Linux AI Voice Assistant — Instalador Automático          "
echo "=============================================================================="
echo -e "${NC}"
echo "Este script configurará todo lo necesario para ejecutar el Asistente de Voz"
echo "impulsado por Antigravity (agy), Whisper (STT local) y Piper (TTS neural)."
echo ""

# ------------------------------------------------------------------------------
# 1. Detección del Gestor de Paquetes y Dependencias del Sistema
# ------------------------------------------------------------------------------
echo -e "${YELLOW}[1/6] Comprobando dependencias del sistema...${NC}"

PACKAGES_MISSING=()

check_cmd() {
    command -v "$1" >/dev/null 2>&1
}

# Essential tools
if ! check_cmd pw-record || ! check_cmd pw-play; then
    PACKAGES_MISSING+=("pipewire-utils")
fi
if ! check_cmd notify-send; then
    PACKAGES_MISSING+=("libnotify")
fi
if ! check_cmd python3; then
    PACKAGES_MISSING+=("python3")
fi
if ! check_cmd git; then
    PACKAGES_MISSING+=("git")
fi
if ! check_cmd curl; then
    PACKAGES_MISSING+=("curl")
fi

if [ ${#PACKAGES_MISSING[@]} -gt 0 ]; then
    echo -e "${YELLOW}Faltan herramientas del sistema: ${PACKAGES_MISSING[*]}${NC}"
    echo "Instalando a través del gestor de paquetes de tu distribución..."
    
    if check_cmd dnf; then
        sudo dnf install -y pipewire-utils libnotify python3 python3-pip git curl konsole
    elif check_cmd pacman; then
        sudo pacman -S --needed --noconfirm pipewire libnotify python python-pip git curl konsole
    elif check_cmd apt; then
        sudo apt update && sudo apt install -y pipewire-bin libnotify-bin python3 python3-pip git curl konsole
    else
        echo -e "${RED}No se detectó un gestor de paquetes compatible (dnf/pacman/apt).${NC}"
        echo "Por favor instala manualmente: pipewire-utils, libnotify, python3, pip, curl y konsole."
    fi
else
    echo -e "${GREEN}✓ Todas las herramientas base del sistema están disponibles.${NC}"
fi

# ------------------------------------------------------------------------------
# 2. Dependencias de Python (Whisper, Piper, PySide6)
# ------------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[2/6] Instalando dependencias de Python...${NC}"
echo "Instalando faster-whisper, piper-tts, PySide6, numpy y openwakeword..."

# Install python dependencies with pip (user-level)
python3 -m pip install --upgrade --user faster-whisper piper-tts PySide6 numpy sounddevice openwakeword 2>/dev/null || \
pip install --upgrade faster-whisper piper-tts PySide6 numpy sounddevice openwakeword

echo -e "${GREEN}✓ Dependencias de Python instaladas correctamente.${NC}"

# ------------------------------------------------------------------------------
# 3. Modelos de Voz Locales (Piper Neural TTS)
# ------------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[3/6] Verificando modelos de voz neurales...${NC}"
mkdir -p "$PROJECT_DIR/voices"

DEFAULT_VOICE="$PROJECT_DIR/voices/es_ES-davefx-medium.onnx"
DEFAULT_JSON="$PROJECT_DIR/voices/es_ES-davefx-medium.onnx.json"
EN_VOICE="$PROJECT_DIR/voices/en_US-lessac-medium.onnx"
EN_JSON="$PROJECT_DIR/voices/en_US-lessac-medium.onnx.json"

if [ ! -f "$DEFAULT_VOICE" ]; then
    echo "Descargando voz en español por defecto (DaveFX Medium)..."
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx" -o "$DEFAULT_VOICE"
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json" -o "$DEFAULT_JSON"
    echo -e "${GREEN}✓ Voz en español descargada.${NC}"
fi

if [ ! -f "$EN_VOICE" ]; then
    echo "Descargando voz en inglés por defecto (Lessac Medium)..."
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx" -o "$EN_VOICE"
    curl -L "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json" -o "$EN_JSON"
    echo -e "${GREEN}✓ Voz en inglés descargada.${NC}"
fi

echo -e "${GREEN}✓ Modelos de voz listos en voices/.${NC}"

# Generar sonido procesando.wav si no existe
if [ ! -f "$PROJECT_DIR/voices/procesando.wav" ]; then
    echo "Generando sonido de confirmación 'Procesando...'..."
    python3 -m piper --model "$DEFAULT_VOICE" --output-file "$PROJECT_DIR/voices/procesando.wav" <<< "Procesando..." 2>/dev/null || true
fi

# Crear archivo de configuración por defecto si no existe
if [ ! -f "$PROJECT_DIR/config/config.env" ]; then
    mkdir -p "$PROJECT_DIR/config"
    cat << 'EOF' > "$PROJECT_DIR/config/config.env"
# ==============================================================================
# Nobara Voice Assistant Configuration (Generated by Control Panel)
# ==============================================================================
ENABLED=true
WHISPER_MODEL="base"
ENABLE_VOICE_REPLY=true
VOICE_MODEL="es_ES-davefx-medium.onnx"
VOICE_SPEAKER=""
TTS_VOLUME=0.35
ENABLE_PROCESSING_VOICE_CUE=true
RESULT_NOTIF_TIMEOUT=15000
AGY_BIN="$HOME/.local/bin/agy"
CONTINUOUS_CONVERSATION=true
ACTIVE_CONVERSATION_ID=""
ASSISTANT_LANGUAGE="es"
AUTO_STOP_SILENCE=false
SILENCE_DURATION=1.2
AUDIO_DUCKING=false
WAKE_WORD_ENABLED=false
WAKE_WORD_MODEL="hey_jarvis"
OVERLAY_HUD_ENABLED=true
EOF
fi

# ------------------------------------------------------------------------------
# 4. Antigravity CLI (agy) e Inicio de Sesión
# ------------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[4/6] Verificando Google Antigravity CLI (agy)...${NC}"

AGY_PATH="$HOME/.local/bin/agy"

if ! check_cmd agy && [ ! -f "$AGY_PATH" ]; then
    echo -e "${CYAN}Antigravity CLI (agy) no está instalado en este sistema.${NC}"
    echo "Descargando e instalando agy oficial..."
    curl -fsSL https://antigravity.google/cli/install.sh | bash
    export PATH="$HOME/.local/bin:$PATH"
fi

if check_cmd agy || [ -f "$AGY_PATH" ]; then
    echo -e "${GREEN}✓ Antigravity CLI detectado en $(command -v agy || echo "$AGY_PATH").${NC}"
    
    # Comprobar si el usuario ya ha iniciado sesión
    if [ ! -d "$HOME/.gemini" ]; then
        echo ""
        echo -e "${YELLOW}╔══════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${YELLOW}║                   ⚠️  INICIO DE SESIÓN REQUERIDO                      ║${NC}"
        echo -e "${YELLOW}╠══════════════════════════════════════════════════════════════════════╣${NC}"
        echo -e "${YELLOW}║ Para que el asistente funcione con tu propia cuenta personal:        ║${NC}"
        echo -e "${YELLOW}║ 1. Abre otra terminal y escribe: agy                                 ║${NC}"
        echo -e "${YELLOW}║ 2. Sigue las instrucciones del navegador para autenticarte.          ║${NC}"
        echo -e "${YELLOW}║ 3. Una vez iniciada sesión, el asistente responderá con tu cuenta.   ║${NC}"
        echo -e "${YELLOW}╚══════════════════════════════════════════════════════════════════════╝${NC}"
        echo ""
    else
        echo -e "${GREEN}✓ Entorno de Antigravity configurado.${NC}"
    fi
else
    echo -e "${RED}No se pudo instalar agy automáticamente. Instálalo con:${NC}"
    echo "  curl -fsSL https://antigravity.google/cli/install.sh | bash"
fi

# ------------------------------------------------------------------------------
# 5. Configuración de Reglas Globales de Visualización (KDE Plasma 6 / Wayland)
# ------------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[5/6] Instalando reglas de entorno gráfico para AGY...${NC}"

mkdir -p "$HOME/.gemini/config"

cat << 'EOF' > "$HOME/.gemini/config/GEMINI.md"
# Reglas de Entorno y Ejecución (Nobara Linux / KDE Plasma 6 / Wayland)

- **Entorno Gráfico y Visualización en Pantalla (Wayland / Xwayland)**:
  - El sistema ejecuta Nobara Linux con KDE Plasma 6 en Wayland.
  - Para cualquier comando de entorno gráfico, las variables de entorno obligatorias son: `DISPLAY=:0` y `WAYLAND_DISPLAY=wayland-0`.
  - **Mostrar aplicaciones o ventanas al usuario (MUY IMPORTANTE)**:
    - Si el usuario te pide abrir un programa, ver información en pantalla, mostrar una ventana, monitor o terminal (ej. "enséñame...", "sácame en pantalla...", "ábreme un terminal con...", "abre el navegador", "muestra el monitor de recursos"):
      - NUNCA ejecutes el comando en segundo plano oculto donde el usuario no pueda verlo.
      - Para mostrar salidas interactivas o comandos en un terminal visible: abre siempre una ventana de Konsole VISIBLE e independiente:
        `DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 kstart -- konsole --separate -e bash -c "<comando>; echo ''; read -p 'Presiona Enter para cerrar...'"`
      - Para aplicaciones gráficas (Dolphin, Navegadores, Ajustes, Steam, etc.): lánzalas de forma visible con:
        `DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 kstart -- <comando>`
      - `kstart --` asegura que la ventana gráfica se abra al frente en el escritorio de Plasma y no bloquee el asistente.
  - **Acciones del sistema sin interfaz**:
    - Si el usuario pide acciones que NO requieren interfaz gráfica (ej: subir/bajar volumen, pausar música, consultar la RAM para responder por voz, cambiar wallpaper, etc.), ejecútalas directamente en bash sin abrir ventanas innecesarias.
  - **Respuestas por voz (TTS)**:
    - Para consultas del asistente de voz, responde siempre de forma concisa y directa (máximo 1 o 2 frases) ya que tu respuesta se leerá por voz con un sintetizador TTS y se mostrará en una notificación.
EOF

echo -e "${GREEN}✓ Reglas de visualización instaladas en ~/.gemini/config/GEMINI.md.${NC}"

# ------------------------------------------------------------------------------
# 6. Enlaces Ejecutables, Acceso al PATH y Menú de Aplicaciones
# ------------------------------------------------------------------------------
echo ""
echo -e "${YELLOW}[6/6] Configurando ejecutables y accesos de escritorio...${NC}"

mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"

# Permisos ejecutables
chmod +x "$PROJECT_DIR/bin/"* "$PROJECT_DIR/src/"*.py "$PROJECT_DIR/"*.sh 2>/dev/null || true

# Enlaces simbólicos
ln -sf "$PROJECT_DIR/bin/nobara-voice-assistant" "$HOME/.local/bin/nobara-voice-assistant"
ln -sf "$PROJECT_DIR/bin/nobara-voice-assistant-settings" "$HOME/.local/bin/nobara-voice-assistant-settings"
ln -sf "$PROJECT_DIR/bin/nobara-voice-assistant-tray" "$HOME/.local/bin/nobara-voice-assistant-tray"
ln -sf "$PROJECT_DIR/bin/nobara-voice-assistant-silence" "$HOME/.local/bin/nobara-voice-assistant-silence"
ln -sf "$PROJECT_DIR/bin/nobara-voice-assistant-wakeword" "$HOME/.local/bin/nobara-voice-assistant-wakeword"
ln -sf "$PROJECT_DIR/bin/nobara-voice-assistant-hud" "$HOME/.local/bin/nobara-voice-assistant-hud"

# Enlaces .desktop
ln -sf "$PROJECT_DIR/desktop/nobara-voice-assistant.desktop" "$HOME/.local/share/applications/nobara-voice-assistant.desktop"
ln -sf "$PROJECT_DIR/desktop/nobara-voice-assistant-settings.desktop" "$HOME/.local/share/applications/nobara-voice-assistant-settings.desktop"
ln -sf "$PROJECT_DIR/desktop/nobara-voice-assistant-tray.desktop" "$HOME/.local/share/applications/nobara-voice-assistant-tray.desktop"
ln -sf "$PROJECT_DIR/desktop/nobara-voice-assistant-silence.desktop" "$HOME/.local/share/applications/nobara-voice-assistant-silence.desktop"

# Autostart para la bandeja del sistema
mkdir -p "$HOME/.config/autostart"
ln -sf "$PROJECT_DIR/desktop/nobara-voice-assistant-tray.desktop" "$HOME/.config/autostart/nobara-voice-assistant-tray.desktop"

# Actualizar base de datos de escritorio si existe
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

# Asegurar que ~/.local/bin está en el PATH
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo "Añadiendo ~/.local/bin al PATH en ~/.bashrc..."
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    export PATH="$HOME/.local/bin:$PATH"
fi

echo -e "${GREEN}✓ Ejecutables enlazados en ~/.local/bin.${NC}"

# ------------------------------------------------------------------------------
# FINALIZACIÓN Y RESUMEN
# ------------------------------------------------------------------------------
echo ""
echo -e "${GREEN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD}                  🎉 ¡Instalación completada con éxito!                       ${NC}"
echo -e "${GREEN}${BOLD}==============================================================================${NC}"
echo ""
echo -e "${BOLD}¿Cómo usar el asistente?${NC}"
echo "1. Panel de Ajustes e Historial:"
echo "   Ejecuta: ${CYAN}nobara-voice-assistant-settings${NC} (o ábrelo desde el menú de inicio)"
echo ""
echo "2. Configurar el Atajo de Teclado en KDE Plasma:"
echo "   - Abre 'Ajustes del Sistema' -> 'Accesos rápidos' (Shortcuts)."
echo "   - Añade un nuevo acceso rápido personalizado o busca 'Asistente de Voz IA'."
echo "   - Comando: ${CYAN}nobara-voice-assistant${NC}"
echo "   - Atajo sugerido: ${BOLD}Meta+Espacio${NC} o ${BOLD}F12${NC} (Pulsar para hablar, pulsar de nuevo para enviar)."
echo ""
echo "3. Inicio de sesión en AGY:"
echo "   Si es la primera vez que usas Antigravity, ejecuta ${CYAN}agy${NC} una vez para iniciar sesión con tu cuenta."
echo ""

read -p "¿Deseas abrir ahora el Panel de Control del Asistente? (s/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[SsYy]$ ]]; then
    DISPLAY=:0 WAYLAND_DISPLAY=wayland-0 "$PROJECT_DIR/bin/nobara-voice-assistant-settings" &
fi
