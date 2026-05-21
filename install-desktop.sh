#!/bin/bash

# Ensure we are running from the source directory
if [ ! -d "src/inlinea" ]; then
    echo "Error: Please run this script from the root of the inlinea source directory."
    exit 1
fi

SRC_DIR=$(pwd)
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"

echo "Setting up Inlinea desktop integration..."

# 1. Create binary wrapper
mkdir -p "$BIN_DIR"
cat <<EOF > "$BIN_DIR/inlinea"
#!/bin/bash
cd "$SRC_DIR" && python3 -m inlinea "\$@"
EOF
chmod +x "$BIN_DIR/inlinea"
echo "Created executable wrapper at $BIN_DIR/inlinea"

# 2. Install icon
mkdir -p "$ICON_DIR"
if [ -f "data/icons/inlinea.png" ]; then
    cp data/icons/inlinea.png "$ICON_DIR/"
    echo "Installed application icon"
fi

# 3. Install desktop entry
mkdir -p "$APP_DIR"
cp data/com.inlinea.app.desktop "$APP_DIR/"
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$APP_DIR"
fi
echo "Installed desktop entry"

echo ""
echo "Desktop integration complete!"
echo "You can now right-click any PDF -> 'Open With' -> 'Inlinea'."
echo "(Note: Ensure $BIN_DIR is in your system PATH)"
