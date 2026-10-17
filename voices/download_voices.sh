#!/usr/bin/env bash
# ==============================================================================
# Download official Piper Spanish voice models (HuggingFace)
# ==============================================================================
set -e

VOICES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main"

download_voice() {
    local name="$1"
    local path_prefix="$2"
    echo "Descargando voz: $name..."
    if [ ! -f "$VOICES_DIR/${name}.onnx" ]; then
        curl -L "$BASE_URL/$path_prefix/${name}.onnx" -o "$VOICES_DIR/${name}.onnx"
    fi
    if [ ! -f "$VOICES_DIR/${name}.onnx.json" ]; then
        curl -L "$BASE_URL/$path_prefix/${name}.onnx.json" -o "$VOICES_DIR/${name}.onnx.json"
    fi
}

echo "==> Comprobando modelos de voz Piper en $VOICES_DIR..."

# 1. DaveFX Medium (Hombre - España)
download_voice "es_ES-davefx-medium" "es/es_ES/davefx/medium"

# 2. Sharvard Medium (Hombre & Mujer - España)
download_voice "es_ES-sharvard-medium" "es/es_ES/sharvard/medium"

# 3. Daniela High (Mujer Natural - Argentina/Neutro)
download_voice "es_AR-daniela-high" "es/es_AR/daniela/high"

echo "==> Voces listas."
