#!/usr/bin/env bash
# install-desktop.sh — Register Inlinea in the system "Open With" menu
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_FILE="$SCRIPT_DIR/com.inlinea.app.desktop"
TARGET_DIR="$HOME/.local/share/applications"

if [ ! -f "$DESKTOP_FILE" ]; then
    echo "Error: $DESKTOP_FILE not found."
    exit 1
fi

mkdir -p "$TARGET_DIR"

# Copy desktop file and patch the Exec path to point to the real install dir
sed "s|INSTALL_DIR|$SCRIPT_DIR|g" "$DESKTOP_FILE" > "$TARGET_DIR/com.inlinea.app.desktop"

# Update the MIME database so the system picks it up
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$TARGET_DIR" 2>/dev/null || true
fi

echo "✓ Installed Inlinea desktop entry to $TARGET_DIR/com.inlinea.app.desktop"
echo "  You can now right-click a PDF → Open With → Inlinea"
