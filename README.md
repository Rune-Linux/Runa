# Rune AUR Helper

A graphical AUR (Arch User Repository) package manager for Linux. Works on any desktop environment that supports GTK3.

## Features

- **Search AUR packages** by name, description, keywords, or maintainer
- **View package details** including votes, popularity, maintainer, and out-of-date status
- **Select multiple packages** for batch installation
- **Built-in password dialog** for sudo authentication
- **Live installation progress** with detailed log output
- **Lightweight** - pure Python with GTK3, no external AUR helpers required

## Requirements

- Arch Linux (or Arch-based distro)
- Python 3.9+
- GTK3 and PyGObject
- git
- base-devel (for makepkg)

## Project Structure

```
rune-package-manager/
├── src/
│   └── rune/
│       ├── __init__.py         # Package metadata
│       ├── __main__.py         # Entry point for python -m rune
│       ├── api/
│       │   ├── __init__.py
│       │   └── aur.py          # AUR RPC API client
│       ├── core/
│       │   ├── __init__.py
│       │   └── installer.py    # Package installation logic
│       └── gui/
│           ├── __init__.py
│           ├── app.py          # Main application window
│           ├── dialogs.py      # Password and progress dialogs
│           └── widgets.py      # Custom GTK widgets
├── data/
│   └── rune-aur-helper.desktop # Desktop entry file
├── scripts/
│   ├── install.sh              # Installation script
│   └── uninstall.sh            # Uninstallation script
├── pyproject.toml              # Python package configuration
├── README.md
└── LICENSE
```

## Installation

### Quick Install

```bash
git clone https://github.com/yourusername/rune-aur-helper.git
cd rune-aur-helper
chmod +x scripts/install.sh
./scripts/install.sh
```

The install script will:
1. Check for dependencies and offer to install them
2. Install the Python package in development mode
3. Add a desktop entry for your application menu

### Manual Install

1. Install dependencies:
```bash
sudo pacman -S git base-devel python-gobject gtk3
```

2. Install the package:
```bash
pip install --user -e .
```

3. (Optional) Install the desktop entry:
```bash
cp data/rune-aur-helper.desktop ~/.local/share/applications/
```

### Running Without Installation

```bash
cd rune-aur-helper
python -m rune
```

## Usage

1. Launch the application from your menu or run `rune-aur-helper`
2. Enter a search term (minimum 2 characters)
   - **Maintainer** - find packages by maintainer
4. Click **Search** or press Enter
5. Check the packages you want to install
6. Click **Install Selected**
7. Enter your password when prompted
```bash
./scripts/uninstall.sh
```

Or manually:
```bash
pip uninstall rune-aur-helper
rm ~/.local/share/applications/rune-aur-helper.desktop
rm -rf ~/.cache/rune-aur-helper
```

## How It Works

Rune AUR Helper uses:
- The official [AUR RPC API](https://aur.archlinux.org/rpc) for searching packages
- `git clone` to download package sources
This is the same process as manually installing AUR packages, just automated with a nice GUI.

## Security Notes

- Your sudo password is only used for `pacman -U` and dependency installation commands
- Password is passed via stdin and not stored
- Build directory is in `~/.cache/rune-aur-helper`
- Always review PKGBUILDs of packages you don't trust

## Troubleshooting

### "Missing required tools" error
Install the required tools:
```bash
sudo pacman -S git base-devel
```

### "PyGObject not found" error
Install GTK3 Python bindings:
```bash
sudo pacman -S python-gobject gtk3
```

### Build fails
- Check if you have all required dependencies
- Some packages may need additional dependencies - check the package's AUR page
- Try building manually to see detailed errors

## Development

### Setting up for development

```bash
git clone https://github.com/yourusername/rune-aur-helper.git
cd rune-aur-helper
pip install -e ".[dev]"
```

### Running tests

```bash
pytest
```

### Type checking

```bash
mypy src/rune
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions welcome! Please feel free to submit issues and pull requests.
