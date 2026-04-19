#!/bin/bash
# ccmin install script
# Usage: bash install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CCMIN_SCRIPT="$SCRIPT_DIR/ccmin.py"

# Check if Python 3.8+ is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Please install Python 3.8+."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    echo "Error: Python 3.8+ required. Found: $PYTHON_VERSION"
    exit 1
fi

echo "✓ Python $PYTHON_VERSION detected"

# Make ccmin.py executable
chmod +x "$CCMIN_SCRIPT"

echo ""
echo "Choose installation method:"
echo "  [1] Symlink to /usr/local/bin/ccmin (recommended)"
echo "  [2] Add alias to ~/.bashrc"
echo "  [3] Show manual instructions"
echo ""
read -p "Choose [1]: " choice
choice=${choice:-1}

case $choice in
    1)
        # Try symlink first
        if touch /usr/local/bin/test_ccmin_write 2>/dev/null; then
            rm -f /usr/local/bin/test_ccmin_write
            ln -sf "$CCMIN_SCRIPT" /usr/local/bin/ccmin
            echo "✓ Symlink created: /usr/local/bin/ccmin → $CCMIN_SCRIPT"
            echo "✓ You can now run 'ccmin' from anywhere"
        else
            echo "⚠ Permission denied for /usr/local/bin"
            echo "  Trying sudo..."
            if sudo ln -sf "$CCMIN_SCRIPT" /usr/local/bin/ccmin 2>/dev/null; then
                echo "✓ Symlink created with sudo: /usr/local/bin/ccmin → $CCMIN_SCRIPT"
            else
                echo "⚠ Could not create symlink. Falling back to bashrc method..."
                choice=2
            fi
        fi
        ;;
    2)
        # Add alias to bashrc
        ALIAS_LINE="alias ccmin='python3 $CCMIN_SCRIPT'"
        BASHRC="$HOME/.bashrc"

        if [ -f "$BASHRC" ]; then
            if grep -q "alias ccmin=" "$BASHRC"; then
                echo "✓ ccmin alias already exists in $BASHRC"
            else
                echo "" >> "$BASHRC"
                echo "# ccmin - Claude Code minimal mode launcher" >> "$BASHRC"
                echo "$ALIAS_LINE" >> "$BASHRC"
                echo "✓ Alias added to $BASHRC"
            fi
        else
            echo "$ALIAS_LINE" >> "$BASHRC"
            echo "✓ Created $BASHRC with ccmin alias"
        fi

        echo "✓ Run 'source ~/.bashrc' or restart your shell to use ccmin"
        ;;
    3)
        echo ""
        echo "Manual installation:"
        echo ""
        echo "1. Make ccmin.py executable:"
        echo "   chmod +x $CCMIN_SCRIPT"
        echo ""
        echo "2. Choose one method:"
        echo ""
        echo "   a) Symlink (global access):"
        echo "      ln -s $CCMIN_SCRIPT /usr/local/bin/ccmin"
        echo ""
        echo "   b) Bashrc alias (user access):"
        echo "      echo \"alias ccmin='python3 $CCMIN_SCRIPT'\" >> ~/.bashrc"
        echo "      source ~/.bashrc"
        echo ""
        echo "   c) Direct usage:"
        echo "      python3 $CCMIN_SCRIPT"
        echo ""
        ;;
    *)
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac

if [ $choice -ne 3 ]; then
    echo ""
    echo "🚀 Installation complete!"
    echo ""
    echo "Next steps:"
    echo "  ccmin --init     # Initialize ccmin configuration"
    echo "  ccmin            # Launch Claude in minimal mode"
    echo "  ccmin --help     # Show all commands"
fi