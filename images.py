"""
Image loading helpers for FoodCalories.

Converts uploads to a consistent RGB JPEG for the vision model.
Original files on disk are never modified.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

import config

# Extensions accepted by the uploader and sample scanner
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def is_supported_image_path(path: Path) -> bool:
    """Return True when the path looks like a supported food photograph."""
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def list_sample_images(samples_dir: Path) -> list[Path]:
    """
    Recursively list supported images under samples/.

    Sorted by relative path for stable verification reports.
    """
    if not samples_dir.exists():
        return []
    found = [
        path
        for path in samples_dir.rglob("*")
        if is_supported_image_path(path)
    ]
    return sorted(found, key=lambda p: str(p).lower())


def open_image(image_bytes: bytes) -> Image.Image:
    """
    Open image bytes with Pillow.

    Raises ValueError with a clear message when the file is corrupt
    or not a recognised image format.
    """
    try:
        image = Image.open(BytesIO(image_bytes))
        # Force decode now so corrupt files fail early
        image.load()
    except UnidentifiedImageError as exc:
        raise ValueError("Unsupported or corrupt image file.") from exc
    except OSError as exc:
        raise ValueError(f"Could not read image: {exc}") from exc
    return image


def prepare_image_bytes(
    image_bytes: bytes,
    max_side: int | None = None,
) -> bytes:
    """
    Normalise an upload for the vision model.

    Steps:
      1. Open bytes (format detected from content, not the filename)
      2. Apply EXIF orientation so sideways phone photos are upright
      3. Flatten transparency onto white (RGBA / LA / palette-with-alpha)
      4. Convert to RGB
      5. Downscale so the longest side is at most max_side
         (aspect ratio preserved; no centre-crop)
      6. Encode as JPEG (originals are left unchanged for display)

    Returns JPEG bytes suitable for Ollama.
    """
    side = int(max_side) if max_side is not None else int(config.IMAGE_MAX_SIDE)
    image = open_image(image_bytes)

    # Correct phone / camera orientation using EXIF metadata
    image = ImageOps.exif_transpose(image)

    # Flatten alpha onto white so JPEG encoding stays valid
    if image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, rgba).convert("RGB")
    elif image.mode != "RGB":
        image = image.convert("RGB")

    width, height = image.size
    longest = max(width, height)
    if longest > side:
        scale = side / float(longest)
        image = image.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.Resampling.LANCZOS,
        )

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()
