"""
Application configuration.

All settings live here so students can change the model or host
without editing vision.py or app.py. Nothing here is shown in the UI.
"""

import os
from pathlib import Path

# ==========================================
# PROJECT PATHS (relative, portable)
# ==========================================

# Path to this file's directory = project root
PROJECT_ROOT = Path(__file__).resolve().parent

# Nutritional reference CSV (editable in any text editor or spreadsheet)
FOODS_CSV_PATH = PROJECT_ROOT / "foods.csv"

# Directory for cached AI analysis results (ignored by Git)
CACHE_DIR = PROJECT_ROOT / ".cache" / "analyses"

# ==========================================
# OLLAMA SETTINGS
# ==========================================


def _normalise_ollama_host(raw: str) -> str:
    """
    Turn a host setting into a usable HTTP base URL.

    Accepts values such as:
      http://localhost:11434
      localhost:11434
      0.0.0.0:11434   (bind address → rewritten to localhost for clients)
    """
    value = (raw or "").strip()
    if not value:
        return "http://localhost:11434"

    # Add scheme if the user only provided host:port
    if "://" not in value:
        value = "http://" + value

    # 0.0.0.0 is a server bind address, not a client target
    value = value.replace("://0.0.0.0", "://127.0.0.1")
    return value.rstrip("/")


# Host where the local Ollama service listens
# Override with environment variable: set OLLAMA_HOST=http://...
OLLAMA_HOST = _normalise_ollama_host(
    os.environ.get("OLLAMA_HOST", "http://localhost:11434")
)

# Vision-language model name
# Override with: set OLLAMA_MODEL=gemma3:4b
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3-vl:4b-instruct")

# Low temperature = more consistent JSON responses
OLLAMA_TEMPERATURE = float(os.environ.get("OLLAMA_TEMPERATURE", "0.2"))

# Modest context window so the model fits on RTX 3080 / 3060
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))

# ==========================================
# IMAGE PREPROCESSING
# ==========================================

# Longest side (pixels) sent to Ollama. Display uses the original upload.
# 768 balances shared-dish coverage against simpler single-food photos;
# incomplete primary passes retry once at IMAGE_FALLBACK_MAX_SIDE.
IMAGE_MAX_SIDE = int(os.environ.get("IMAGE_MAX_SIDE", "768"))

# Bump when preprocess behaviour changes (resize policy, JPEG quality, etc.)
PREPROCESS_VERSION = "v12"

# Higher resolution used once when the primary pass looks incomplete.
IMAGE_FALLBACK_MAX_SIDE = int(os.environ.get("IMAGE_FALLBACK_MAX_SIDE", "1024"))

# ==========================================
# CACHE / SCHEMA VERSIONS
# ==========================================

# Bump these when the prompt or expected JSON shape changes,
# so old cache entries are not reused incorrectly.
PROMPT_VERSION = "v14"
SCHEMA_VERSION = "v13"

# ==========================================
# STUDENT EXERCISE
# ==========================================
# Add a new setting here, for example a daily calorie target:
# DAILY_CALORIE_TARGET = int(os.environ.get("DAILY_CALORIE_TARGET", "2000"))
