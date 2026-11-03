#!/usr/bin/env bash
set -euo pipefail

# ==========================================
# FoodCalories macOS / Linux setup
# ==========================================

cd "$(dirname "$0")"

SKIP_MODEL=0
if [[ "${1:-}" == "--skip-model" ]]; then
  SKIP_MODEL=1
fi

echo
echo "=== FoodCalories setup ==="
echo "Project: $(pwd)"
echo

# 1. Check Python
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "[ERROR] Python was not found on PATH."
  echo "Install Python 3.11 or 3.12 and re-run setup.sh"
  exit 1
fi

echo "[OK] $($PYTHON --version 2>&1)"

# 2. Create virtual environment if missing
if [[ ! -x ".venv/bin/python" ]]; then
  echo "Creating virtual environment .venv ..."
  "$PYTHON" -m venv .venv
else
  echo "[OK] Virtual environment already exists"
fi

# 3. Install dependencies
echo "Installing Python packages from requirements.txt ..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
echo "[OK] Dependencies installed"

if [[ "$SKIP_MODEL" -eq 1 ]]; then
  echo
  echo "[--skip-model] Skipping Ollama model checks."
  echo "Setup finished."
  exit 0
fi

# 4. Check Ollama CLI
if ! command -v ollama >/dev/null 2>&1; then
  echo "[ERROR] Ollama was not found on PATH."
  echo "Install Ollama from https://ollama.com then re-run setup.sh"
  exit 1
fi

echo "[OK] $(ollama --version 2>&1)"
echo "Note: qwen3-vl:4b-instruct requires Ollama 0.12.7 or newer."
echo "If your version is older, update Ollama manually. This script will not upgrade it."

# 5. Check Ollama service
if ! curl -sf http://localhost:11434/api/tags >/dev/null; then
  echo "[ERROR] Ollama service is not reachable at http://localhost:11434"
  echo "Start the Ollama application and re-run setup.sh"
  exit 1
fi
echo "[OK] Ollama service is reachable"

# 6/7. Check / pull model
MODEL="${OLLAMA_MODEL:-qwen3-vl:4b-instruct}"

if ollama show "$MODEL" >/dev/null 2>&1; then
  echo "[OK] Model already installed: $MODEL"
else
  echo "Model $MODEL not found locally. Downloading..."
  if ! ollama pull "$MODEL"; then
    echo "[ERROR] Failed to download $MODEL"
    echo "Fallback suggestion: OLLAMA_MODEL=gemma3:4b ./setup.sh"
    exit 1
  fi
fi

echo
echo "=== Setup completed successfully ==="
echo "Run the app with: ./run.sh"
exit 0
