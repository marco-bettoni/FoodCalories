"""
Persistent image-analysis cache.

Cache key = SHA-256 of:
    image bytes + model name + prompt version + schema version
    + preprocess version + image max side

Results are stored as simple JSON files under .cache/analyses/.
Failed or invalid model responses must never be written here.
User-edited quantities are also never saved as the original AI result.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import config


def ensure_cache_dir(cache_dir: Path | None = None) -> Path:
    """Create the cache directory if it does not exist. Return its path."""
    path = cache_dir if cache_dir is not None else config.CACHE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_cache_key(
    image_bytes: bytes,
    model_name: str | None = None,
    prompt_version: str | None = None,
    schema_version: str | None = None,
    preprocess_version: str | None = None,
    image_max_side: int | None = None,
) -> str:
    """
    Build a SHA-256 hex digest used as the cache file name.

    The key changes if the image, model, prompt, schema, preprocess
    version or resolution changes, so outdated results are not reused.
    """
    model = model_name if model_name is not None else config.OLLAMA_MODEL
    prompt_ver = prompt_version if prompt_version is not None else config.PROMPT_VERSION
    schema_ver = schema_version if schema_version is not None else config.SCHEMA_VERSION
    prep_ver = (
        preprocess_version
        if preprocess_version is not None
        else config.PREPROCESS_VERSION
    )
    max_side = (
        image_max_side if image_max_side is not None else config.IMAGE_MAX_SIDE
    )

    # Create a hasher and feed it each component
    hasher = hashlib.sha256()
    hasher.update(image_bytes)
    hasher.update(model.encode("utf-8"))
    hasher.update(prompt_ver.encode("utf-8"))
    hasher.update(schema_ver.encode("utf-8"))
    hasher.update(prep_ver.encode("utf-8"))
    hasher.update(str(int(max_side)).encode("utf-8"))

    # Return the hexadecimal digest string
    return hasher.hexdigest()


def cache_path_for_key(cache_key: str, cache_dir: Path | None = None) -> Path:
    """Return the JSON file path for a given cache key."""
    directory = ensure_cache_dir(cache_dir)
    return directory / f"{cache_key}.json"


def load_cached_result(
    cache_key: str,
    cache_dir: Path | None = None,
) -> dict | None:
    """
    Load a cached analysis result.

    Returns the dictionary if the file exists and is valid JSON
    with the expected structure. Returns None on miss or corruption.
    """
    path = cache_path_for_key(cache_key, cache_dir)

    # Conditional: file missing = cache miss
    if not path.exists():
        return None

    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        # Invalid cached JSON — treat as a miss
        return None

    # Basic structure check before trusting the file
    if not isinstance(data, dict):
        return None
    if "ingredients" not in data or not isinstance(data["ingredients"], list):
        return None

    return data


def save_cached_result(
    cache_key: str,
    result: dict,
    cache_dir: Path | None = None,
) -> Path:
    """
    Save a validated AI analysis result as JSON.

    Only call this with successful, validated responses.
    """
    path = cache_path_for_key(cache_key, cache_dir)

    with path.open("w", encoding="utf-8") as file:
        json.dump(result, file, indent=2, ensure_ascii=False)

    return path


def clear_cache(cache_dir: Path | None = None) -> int:
    """Delete all cached JSON files. Returns how many files were removed."""
    directory = ensure_cache_dir(cache_dir)
    removed = 0

    # Loop over every .json file in the cache directory
    for path in directory.glob("*.json"):
        path.unlink()
        removed += 1

    return removed
