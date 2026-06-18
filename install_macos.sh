#!/bin/bash
# iScout Mechanic-Ti VisualPlatformSetUp – macOS installation helper
# Run this once on a macOS machine after cloning the repository.

set -e

PYTHON=python3
PIP="$PYTHON -m pip"

echo "=== iScout Mechanic-Ti VisualPlatform – macOS Setup ==="

# Check Python ≥ 3.10
PYVER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python version: $PYVER"

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment…"
    $PYTHON -m venv .venv
fi

source .venv/bin/activate

echo "Installing dependencies…"
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "=== Done! ==="
echo ""
echo "To run the application:"
echo "  source .venv/bin/activate"
echo "  python main.py"
echo ""
echo "To build a standalone macOS .app bundle:"
echo "  pip install py2app"
echo "  python setup_macos.py py2app"
echo "  open dist/iScout\\ Mechanic-Ti\\ VisualPlatform.app"
