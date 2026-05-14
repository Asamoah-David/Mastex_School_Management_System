#!/usr/bin/env bash
# Generate a fully pinned lock file from requirements.txt (pip-tools).
# Install: pip install 'pip-tools>=7.3'
# Output: requirements-lock.txt at repo root (review before committing).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python -m pip install -q 'pip-tools>=7.3'
pip-compile requirements.txt -o requirements-lock.txt --resolver=backtracking
echo "Wrote requirements-lock.txt"
