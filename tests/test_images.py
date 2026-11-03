"""Tests for image loading, WebP support and sample scanning."""

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

import config
import images


def _make_bytes(mode: str = "RGB", size=(64, 48), fmt: str = "JPEG") -> bytes:
    if mode == "RGBA":
        image = Image.new("RGBA", size, color=(200, 100, 50, 128))
    else:
        image = Image.new("RGB", size, color=(200, 100, 50))
    if fmt == "JPEG":
        image = image.convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def test_supported_extensions_include_webp():
    assert ".webp" in images.SUPPORTED_EXTENSIONS
    assert ".jpg" in images.SUPPORTED_EXTENSIONS
    assert ".png" in images.SUPPORTED_EXTENSIONS


def test_prepare_jpeg_and_png_and_webp():
    for fmt in ("JPEG", "PNG", "WEBP"):
        raw = _make_bytes(fmt=fmt)
        prepared = images.prepare_image_bytes(raw, max_side=32)
        opened = Image.open(BytesIO(prepared))
        assert opened.format == "JPEG"
        assert opened.mode == "RGB"
        assert max(opened.size) <= 32


def test_prepare_flattens_rgba():
    raw = _make_bytes(mode="RGBA", fmt="PNG")
    prepared = images.prepare_image_bytes(raw, max_side=64)
    opened = Image.open(BytesIO(prepared))
    assert opened.mode == "RGB"


def test_corrupt_image_raises():
    with pytest.raises(ValueError):
        images.open_image(b"not-an-image")


def test_list_sample_images_recursive():
    samples = config.PROJECT_ROOT / "samples"
    if not samples.exists():
        pytest.skip("samples/ missing")
    found = images.list_sample_images(samples)
    assert found
    rels = [p.relative_to(samples).as_posix() for p in found]
    # verify/ subdirectory must be included
    assert any(r.startswith("verify/") for r in rels)
    # WebP samples must be included when present in the curated tree
    on_disk_webps = list(samples.rglob("*.webp")) + list(samples.rglob("*.WEBP"))
    webps = [r for r in rels if r.lower().endswith(".webp")]
    assert len(webps) == len(on_disk_webps)
    # README and other non-images excluded
    assert all(Path(r).suffix.lower() in images.SUPPORTED_EXTENSIONS for r in rels)


def test_real_sample_webp_and_rgba_misnamed_jpg_load():
    samples = config.PROJECT_ROOT / "samples"
    webp = samples / "Hong Kong Poon Choi.webp"
    rgba_jpg = samples / "verify" / "chocolate.jpg"
    if webp.exists():
        prepared = images.prepare_image_bytes(webp.read_bytes())
        assert Image.open(BytesIO(prepared)).mode == "RGB"
    if rgba_jpg.exists():
        # Extension says jpg but content is RGBA PNG — must still load
        prepared = images.prepare_image_bytes(rgba_jpg.read_bytes())
        assert Image.open(BytesIO(prepared)).mode == "RGB"
