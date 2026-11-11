#!/bin/bash
# RSSpad Launcher for Linux Mint Cinnamon
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

export PATH="$HOME/.local/bin:$PATH"
export GDK_RENDERING=similar
export PYTHONDONTWRITEBYTECODE=1

PY_BIN="/usr/bin/python3"
[ -x "$PY_BIN" ] || PY_BIN="python3"
cd "$SCRIPT_DIR"
exec "$PY_BIN" -B "$SCRIPT_DIR/rsspad.py" "$@"
