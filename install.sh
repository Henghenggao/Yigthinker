#!/usr/bin/env bash
# Yigthinker one-line installer
# Usage: curl -fsSL https://raw.githubusercontent.com/gaoyu/Yigthinker/master/install.sh | bash
set -euo pipefail

main() {
    if command -v uv &>/dev/null; then
        echo "uv found: $(uv --version)"
    else
        echo "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh

        # Make uv available in current session
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

        if ! command -v uv &>/dev/null; then
            echo "Error: uv installation failed. Install manually: https://docs.astral.sh/uv/"
            exit 1
        fi
    fi

    echo ""
    echo "Starting Yigthinker installer..."
    echo ""
    uvx yigthinker install
}

main
