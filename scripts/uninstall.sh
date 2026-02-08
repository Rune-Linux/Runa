#!/bin/bash

set -e

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DATA_DIR="$DATA_HOME/rune-aur-helper"
VENV_DIR="$APP_DATA_DIR/venv"
BIN_HOME="$HOME/.local/bin"
LAUNCHER="$BIN_HOME/rune-aur-helper"

echo "Uninstalling Rune AUR Helper..."

echo "Removing launcher..."
if [ -f "$LAUNCHER" ]; then
    rm "$LAUNCHER"
    echo "  Removed $LAUNCHER"
fi

echo "Removing virtual environment..."
if [ -d "$VENV_DIR" ]; then
    rm -rf "$VENV_DIR"
    echo "  Removed $VENV_DIR"
fi

if [ -d "$APP_DATA_DIR" ]; then
    rmdir "$APP_DATA_DIR" 2>/dev/null || true
fi

if [ -f ~/.local/share/applications/rune-aur-helper.desktop ]; then
    rm ~/.local/share/applications/rune-aur-helper.desktop
    echo "  Removed desktop entry"
fi

if command -v update-desktop-database &> /dev/null; then
    update-desktop-database ~/.local/share/applications 2>/dev/null || true
fi

CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/rune-aur-helper"
if [ -d "$CACHE_DIR" ]; then
    rm -rf "$CACHE_DIR"
    echo "  Removed cache directory"
fi

echo ""
echo "Uninstallation complete!"
