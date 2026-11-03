#!/usr/bin/env bash
set -euo pipefail

# ==========================================
# FoodCalories macOS / Linux setup
# ==========================================

cd "$(dirname "$0")"
ROOT="$(pwd)"

# Ensure common macOS system tools remain reachable even if PATH is minimal.
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH}"

SKIP_MODEL=0
ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --skip-model) SKIP_MODEL=1 ;;
    --yes|-y) ASSUME_YES=1 ;;
  esac
done

LAB_MSG="For reliable performance during the class, use a PolyU laboratory PC with the prepared AI environment."
MODEL="${OLLAMA_MODEL:-qwen3-vl:4b-instruct}"
# Approximate download size shown before pulling (student-facing).
MODEL_SIZE_HINT="~3.3 GB"

echo
echo "=== FoodCalories setup ==="
echo "Project: ${ROOT}"
echo

# ------------------------------------------
# 0. Hardware / environment preflight
# ------------------------------------------
if [[ -f "${ROOT}/scripts/check_system.sh" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT}/scripts/check_system.sh"
  _fc_print_report
else
  echo "[WARN] scripts/check_system.sh missing; skipping hardware check."
  FC_ASSESSMENT="UNKNOWN"
  FC_DISK_AVAIL_GB="unknown"
fi

if [[ "${FC_ASSESSMENT:-UNKNOWN}" == "UNSUITABLE" ]]; then
  echo "[WARN] This computer looks unsuitable for local AI inference."
  echo "$LAB_MSG"
  echo "Setup will continue so you can still inspect the code and run tests."
  echo
fi

# Disk space: need room for venv (~200 MB) and optionally the model.
if [[ "${FC_DISK_AVAIL_GB:-unknown}" != "unknown" ]]; then
  if (( FC_DISK_AVAIL_GB < 1 )); then
    echo "[ERROR] Insufficient disk space (less than 1 GB free)."
    echo "Free some disk space and try again."
    exit 1
  fi
  if [[ "$SKIP_MODEL" -eq 0 ]] && (( FC_DISK_AVAIL_GB < 5 )); then
    echo "[ERROR] Less than 5 GB free disk space."
    echo "The AI model download needs about ${MODEL_SIZE_HINT}."
    echo "Free disk space, or re-run with: ./setup.sh --skip-model"
    exit 1
  fi
fi

# ------------------------------------------
# 1. Check Python (prefer 3.11–3.13, accept 3.10+)
# ------------------------------------------
pick_python() {
  local cand ver major minor
  for cand in python3.12 python3.11 python3.13 python3.14 python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then
      ver="$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
      if [[ -z "$ver" ]]; then
        continue
      fi
      major="${ver%%.*}"
      minor="${ver#*.}"
      if (( major > 3 || (major == 3 && minor >= 10) )); then
        echo "$cand"
        return 0
      fi
    fi
  done
  return 1
}

if ! PYTHON="$(pick_python)"; then
  echo "[ERROR] A supported Python was not found on PATH."
  echo "Install Python 3.11 or 3.12 (3.10+ also works) and re-run ./setup.sh"
  echo "On macOS with Homebrew: brew install python@3.12"
  exit 1
fi

PY_FULL="$("$PYTHON" --version 2>&1)"
echo "[OK] ${PY_FULL} (${PYTHON})"

# ------------------------------------------
# 2. Create virtual environment if missing
# ------------------------------------------
if [[ ! -x ".venv/bin/python" ]]; then
  echo "Creating virtual environment .venv ..."
  if ! "$PYTHON" -m venv .venv; then
    echo "[ERROR] Failed to create the virtual environment."
    echo "Check that your Python install includes the venv module."
    exit 1
  fi
else
  echo "[OK] Virtual environment already exists"
fi

# ------------------------------------------
# 3. Install dependencies
# ------------------------------------------
echo "Installing Python packages from requirements.txt ..."
if ! .venv/bin/python -m pip install --upgrade pip; then
  echo "[ERROR] Failed to upgrade pip inside .venv"
  exit 1
fi
if ! .venv/bin/python -m pip install -r requirements.txt; then
  echo "[ERROR] Failed to install Python dependencies."
  echo "Check your network connection and re-run ./setup.sh"
  exit 1
fi
echo "[OK] Dependencies installed"

if [[ "$SKIP_MODEL" -eq 1 ]]; then
  echo
  echo "[--skip-model] Skipping Ollama model checks."
  echo "=== Setup finished (Python environment ready) ==="
  if [[ "${FC_ASSESSMENT:-}" == "LIMITED" || "${FC_ASSESSMENT:-}" == "UNSUITABLE" ]]; then
    echo
    echo "Note: installation succeeded, but hardware suitability is ${FC_ASSESSMENT}."
    echo "$LAB_MSG"
  fi
  echo "Run the app with: ./run.sh"
  exit 0
fi

# ------------------------------------------
# 4. Check Ollama CLI
# ------------------------------------------
if ! command -v ollama >/dev/null 2>&1; then
  echo "[ERROR] Ollama was not found on PATH."
  echo "Install Ollama from https://ollama.com then re-run ./setup.sh"
  echo "Do not use sudo for this classroom setup."
  exit 1
fi

echo "[OK] $(ollama --version 2>&1 | head -n 1)"
echo "Note: ${MODEL} requires Ollama 0.12.7 or newer."
echo "If your version is older, update Ollama manually. This script will not upgrade it."

# ------------------------------------------
# 5. Check Ollama service
# ------------------------------------------
if ! curl -sf http://localhost:11434/api/tags >/dev/null; then
  echo "[ERROR] Ollama service is not reachable at http://localhost:11434"
  echo "On macOS: open the Ollama app from Applications, wait a few seconds, then re-run ./setup.sh"
  echo "On Linux: run  ollama serve  in another terminal, then re-run ./setup.sh"
  exit 1
fi
echo "[OK] Ollama service is reachable"

# ------------------------------------------
# 6/7. Check / pull model (explicit consent)
# ------------------------------------------
if ollama show "$MODEL" >/dev/null 2>&1; then
  echo "[OK] Model already installed: $MODEL"
else
  echo
  echo "Model ${MODEL} is not installed locally."
  echo "Download size is approximately ${MODEL_SIZE_HINT}."
  echo "This may take several minutes depending on your network."
  echo
  reply=""
  if [[ "$ASSUME_YES" -eq 1 || "${FOODCALORIES_ASSUME_YES:-}" == "1" ]]; then
    reply="y"
    echo "[--yes] Proceeding with model download."
  elif [[ -t 0 ]]; then
    read -r -p "Download ${MODEL} now? [y/N] " reply
  else
    echo "[ERROR] Model download requires confirmation, but no interactive terminal is available."
    echo "Re-run with:  ./setup.sh --yes"
    echo "Or skip model checks:  ./setup.sh --skip-model"
    echo "Or download later:  ollama pull ${MODEL}"
    exit 1
  fi
  case "$reply" in
    y|Y|yes|YES)
      echo "Downloading ${MODEL} ..."
      if ! ollama pull "$MODEL"; then
        echo "[ERROR] Failed to download ${MODEL}"
        echo "Fallback suggestion: OLLAMA_MODEL=gemma3:4b ./setup.sh"
        exit 1
      fi
      echo "[OK] Model downloaded: $MODEL"
      ;;
    *)
      echo "[ERROR] Model download skipped."
      echo "Install it later with:  ollama pull ${MODEL}"
      echo "Or re-run:  ./setup.sh"
      echo "Or skip model checks with:  ./setup.sh --skip-model"
      exit 1
      ;;
  esac
fi

echo
echo "=== Setup completed successfully ==="
if [[ "${FC_ASSESSMENT:-}" == "LIMITED" || "${FC_ASSESSMENT:-}" == "UNSUITABLE" ]]; then
  echo
  echo "Installation succeeded. Hardware assessment: ${FC_ASSESSMENT}."
  echo "$LAB_MSG"
fi
echo "Run the app with: ./run.sh"
exit 0
