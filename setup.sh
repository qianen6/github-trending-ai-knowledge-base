#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -m venv "$ROOT/.venv"
if ! "$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"; then
  printf 'Default PyPI failed; retrying with the Tsinghua PyPI mirror.\n' >&2
  "$ROOT/.venv/bin/python" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r "$ROOT/requirements.txt"
fi
"$ROOT/.venv/bin/python" "$ROOT/scripts/bootstrap.py" --root "$ROOT" --check
printf 'SETUP PASS: activate with source .venv/bin/activate\n'
