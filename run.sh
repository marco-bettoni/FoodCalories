#!/usr/bin/env bash
set -euo pipefail

# ==========================================
# FoodCalories launcher (macOS / Linux)
# ==========================================

cd "$(dirname "$0")"
ROOT="$(pwd)"

# Ensure common macOS system tools remain reachable even if PATH is minimal.
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH}"

LAB_MSG="For reliable performance during the class, use a PolyU laboratory PC with the prepared AI environment."
MODEL="${OLLAMA_MODEL:-qwen3-vl:4b-instruct}"

echo
echo "=== FoodCalories ==="
echo "Project: ${ROOT}"
echo

# ------------------------------------------
# Hardware warning (non-fatal)
# ------------------------------------------
if [[ -f "${ROOT}/scripts/check_system.sh" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT}/scripts/check_system.sh"
  if [[ "${FC_ASSESSMENT:-}" == "LIMITED" || "${FC_ASSESSMENT:-}" == "UNSUITABLE" || "${FC_ASSESSMENT:-}" == "UNKNOWN" ]]; then
    echo "Hardware assessment: ${FC_ASSESSMENT}"
    if [[ -n "${FC_ASSESS_DETAIL:-}" ]]; then
      echo "${FC_ASSESS_DETAIL}"
    fi
    if [[ "${FC_ASSESSMENT}" == "LIMITED" || "${FC_ASSESSMENT}" == "UNSUITABLE" ]]; then
      echo "$LAB_MSG"
    fi
    echo
  else
    echo "[OK] Hardware assessment: ${FC_ASSESSMENT} (${FC_TOTAL_RAM_GB} GB RAM, ${FC_ARCH_LABEL})"
  fi
fi

# ------------------------------------------
# Virtual environment
# ------------------------------------------
if [[ ! -x ".venv/bin/python" ]]; then
  echo "[ERROR] Virtual environment not found."
  echo "Run ./setup.sh first."
  exit 1
fi

# ------------------------------------------
# Required Python packages
# ------------------------------------------
if ! .venv/bin/python -c "import streamlit, ollama, pydantic, PIL" >/dev/null 2>&1; then
  echo "[ERROR] Required Python packages are missing from .venv"
  echo "Re-run: ./setup.sh --skip-model"
  exit 1
fi
echo "[OK] Python packages"

# ------------------------------------------
# Ollama connectivity
# ------------------------------------------
if ! command -v ollama >/dev/null 2>&1; then
  echo "[ERROR] Ollama was not found on PATH."
  echo "Install Ollama from https://ollama.com then run ./setup.sh"
  exit 1
fi

if ! curl -sf http://localhost:11434/api/tags >/dev/null; then
  echo "[ERROR] Cannot reach Ollama at http://localhost:11434"
  echo "On macOS: open the Ollama app, wait a few seconds, then run ./run.sh again."
  exit 1
fi
echo "[OK] Ollama service"

# ------------------------------------------
# Model present (do not auto-download)
# ------------------------------------------
if ! ollama show "$MODEL" >/dev/null 2>&1; then
  echo "[ERROR] Model not installed: ${MODEL}"
  echo "Install it with:  ollama pull ${MODEL}"
  echo "Or run:  ./setup.sh"
  echo "Approximate download size: ~3.3 GB"
  exit 1
fi
echo "[OK] Model available: ${MODEL}"

# ------------------------------------------
# Avoid stacking duplicate Streamlit servers
# ------------------------------------------
if curl -sf http://localhost:8501 >/dev/null 2>&1; then
  echo
  echo "[WARN] Something is already responding on http://localhost:8501"
  echo "Open that address in your browser, or stop the other process first."
  echo "Starting another instance may confuse the classroom demo."
  echo
fi

echo
echo "Starting FoodCalories (Streamlit)..."
echo "When ready, open the Local URL shown below (usually http://localhost:8501)"
echo

exec .venv/bin/python -m streamlit run app.py \
  --server.headless true \
  --browser.gatherUsageStats false
