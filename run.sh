#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "[ERROR] Virtual environment not found."
  echo "Run ./setup.sh first."
  exit 1
fi

echo "Starting AI Food Calorie Estimator..."
exec .venv/bin/python -m streamlit run app.py
