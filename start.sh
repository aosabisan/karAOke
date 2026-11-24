#!/bin/sh
# Aosabi Karaoke - Copyright (c) 2026 aosabi. All rights reserved.
# Linux / macOS start. Needs "uv" (https://docs.astral.sh/uv/). The first start sets up a private Python.
set -e
cd "$(dirname "$0")"
command -v uv >/dev/null 2>&1 || { echo "Please install uv first: https://docs.astral.sh/uv/"; exit 1; }
ENVDIR="${AOSABI_KARAOKE_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/aosabi-karaoke}/program-env"
if [ ! -x "$ENVDIR/bin/python" ]; then
  uv venv --python 3.12 "$ENVDIR"
  uv pip install --python "$ENVDIR/bin/python" -r app/requirements.txt
fi
PYTHONPATH="$(pwd)/app" exec "$ENVDIR/bin/python" -m karaoke "$@"
