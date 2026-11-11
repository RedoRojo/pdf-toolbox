#!/usr/bin/env bash
# CLI launcher for PDF Toolbox: resolves the Python environment and runs cli.py.
# IMPORTANT: never `cd` here. Output files default to the caller's working directory.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
CONDA_ENV_PY="${PDF_TOOLBOX_PYTHON:-$HOME/miniconda3/envs/pdf-toolkit/bin/python}"

if [ -x "$CONDA_ENV_PY" ]; then
    PYTHON_CMD="$CONDA_ENV_PY"
elif [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_CMD="$SCRIPT_DIR/.venv/bin/python"
elif [ -x "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON_CMD="$SCRIPT_DIR/venv/bin/python"
else
    if command -v conda >/dev/null 2>&1; then
        eval "$(conda shell.bash hook 2>/dev/null || true)"
        conda activate pdf-toolkit 2>/dev/null || true
    fi
    PYTHON_CMD="$(command -v python3 || command -v python)"
fi

exec "$PYTHON_CMD" "$SCRIPT_DIR/cli.py" "$@"
