#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -m venv "$ROOT/.venv"
if ! "$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"; then
  printf 'Default PyPI failed; retrying with the Tsinghua PyPI mirror.\n' >&2
  "$ROOT/.venv/bin/python" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r "$ROOT/requirements.txt"
fi
"$ROOT/.venv/bin/python" -m pip install --no-deps -e "$ROOT"
"$ROOT/.venv/bin/python" "$ROOT/scripts/bootstrap.py" --root "$ROOT" --check
printf 'SETUP PASS: activate with source .venv/bin/activate; runtime data is in ./workspace\n'
printf '%s\n' 'CODEX NEXT: open this repository in Codex and send: 安装这个仓库并创建每日任务'
printf '%s\n' 'CODEX CONTRACT: CODEX_SETUP.md'
