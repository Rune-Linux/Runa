#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_HOME="$HOME/.local/bin"
APP_DATA_DIR="$DATA_HOME/rune-aur-helper"
VENV_DIR="$APP_DATA_DIR/venv"

echo "Installing Rune AUR Helper..."
echo ""

echo "Checking dependencies..."
deps_missing=0

if ! command -v git &> /dev/null; then
    echo "  [MISSING] git"
    deps_missing=1
fi

if ! command -v makepkg &> /dev/null; then
    echo "  [MISSING] makepkg (base-devel)"
    deps_missing=1
fi

if ! python3 -c "import gi; gi.require_version('Gtk', '3.0')" 2>/dev/null; then
    echo "  [MISSING] python-gobject gtk3"
    deps_missing=1
fi

if [ $deps_missing -eq 1 ]; then
    echo ""
    echo "Missing dependencies. Install them with:"
    echo "  sudo pacman -S git base-devel python-gobject gtk3"
    echo ""
    read -p "Would you like to install them now? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo pacman -S --needed git base-devel python-gobject gtk3
    else
        echo "Aborting installation."
        exit 1
    fi
fi

echo ""
echo "Setting up dedicated virtual environment in $VENV_DIR..."

mkdir -p "$APP_DATA_DIR"
python -m venv "$VENV_DIR"

echo "Installing Python package into the virtual environment..."
"$VENV_DIR/bin/pip" install "$PROJECT_ROOT"

echo "Creating launcher in $BIN_HOME..."
mkdir -p "$BIN_HOME"
LAUNCHER="$BIN_HOME/rune-aur-helper"
cat > "$LAUNCHER" <<EOF
#!/bin/sh
"$VENV_DIR/bin/python" -m rune "$@"
EOF
chmod +x "$LAUNCHER"

echo "Installing desktop entry..."
mkdir -p "$HOME/.local/share/applications"
cp "$PROJECT_ROOT/data/rune-aur-helper.desktop" "$HOME/.local/share/applications/"

if command -v update-desktop-database &> /dev/null; then
    update-desktop-database ~/.local/share/applications 2>/dev/null || true
fi

echo ""
echo "============================================"
echo "Installation complete!"
echo "============================================"
echo ""
echo "You can now run 'rune-aur-helper' from the terminal"
echo "or find 'Rune AUR Helper' in your application menu."
echo ""
echo "Note: You may need to log out and back in for the"
echo "application menu entry to appear."
