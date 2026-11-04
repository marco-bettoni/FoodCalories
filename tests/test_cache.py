"""Tests for persistent image-analysis cache."""

import json
from pathlib import Path

import cache
import config


def test_build_cache_key_changes_with_image():
    key_a = cache.build_cache_key(b"image-a", model_name="model-x")
    key_b = cache.build_cache_key(b"image-b", model_name="model-x")
    assert key_a != key_b
    assert len(key_a) == 64


def test_build_cache_key_changes_with_model():
    key_a = cache.build_cache_key(b"same", model_name="model-a")
    key_b = cache.build_cache_key(b"same", model_name="model-b")
    assert key_a != key_b


def test_build_cache_key_changes_with_prompt_version():
    key_a = cache.build_cache_key(
        b"same",
        model_name="m",
        prompt_version="v1",
        schema_version="v2",
    )
    key_b = cache.build_cache_key(
        b"same",
        model_name="m",
        prompt_version="v2",
        schema_version="v2",
    )
    assert key_a != key_b


def test_build_cache_key_changes_with_schema_version():
    key_a = cache.build_cache_key(
        b"same",
        model_name="m",
        prompt_version="v2",
        schema_version="v1",
    )
    key_b = cache.build_cache_key(
        b"same",
        model_name="m",
        prompt_version="v2",
        schema_version="v2",
    )
    assert key_a != key_b


def test_default_versions_are_v13():
    key = cache.build_cache_key(b"photo")
    explicit = cache.build_cache_key(
        b"photo",
        prompt_version=config.PROMPT_VERSION,
        schema_version=config.SCHEMA_VERSION,
        preprocess_version=config.PREPROCESS_VERSION,
        image_max_side=config.IMAGE_MAX_SIDE,
    )
    assert key == explicit
    assert config.PROMPT_VERSION.startswith("v13")
    assert config.SCHEMA_VERSION == "v13"


def test_build_cache_key_changes_with_resolution():
    key_a = cache.build_cache_key(b"same", image_max_side=1024)
    key_b = cache.build_cache_key(b"same", image_max_side=768)
    assert key_a != key_b


def test_build_cache_key_changes_with_preprocess_version():
    key_a = cache.build_cache_key(b"same", preprocess_version="v9")
    key_b = cache.build_cache_key(b"same", preprocess_version="v10")
    assert key_a != key_b


def test_cache_hit_and_miss(tmp_path: Path):
    key = cache.build_cache_key(b"photo", model_name="test-model")
    assert cache.load_cached_result(key, cache_dir=tmp_path) is None

    payload = {
        "dish_name": "Test dish",
        "ingredients": [
            {"name": "egg", "grams": 50},
        ],
    }
    cache.save_cached_result(key, payload, cache_dir=tmp_path)

    loaded = cache.load_cached_result(key, cache_dir=tmp_path)
    assert loaded is not None
    assert loaded["dish_name"] == "Test dish"
    assert loaded["ingredients"][0]["name"] == "egg"
    assert loaded["ingredients"][0]["grams"] == 50


def test_cache_reuse_same_key(tmp_path: Path):
    key = cache.build_cache_key(b"reuse-me", model_name="m", prompt_version="v2", schema_version="v2")
    cache.save_cached_result(
        key,
        {"dish_name": None, "ingredients": [{"name": "apple", "grams": 180}]},
        cache_dir=tmp_path,
    )
    again = cache.build_cache_key(b"reuse-me", model_name="m", prompt_version="v2", schema_version="v2")
    assert again == key
    loaded = cache.load_cached_result(again, cache_dir=tmp_path)
    assert loaded["ingredients"][0]["name"] == "apple"


def test_invalid_cached_json(tmp_path: Path):
    key = "abc123"
    bad_path = cache.cache_path_for_key(key, cache_dir=tmp_path)
    bad_path.write_text("{not-json", encoding="utf-8")
    assert cache.load_cached_result(key, cache_dir=tmp_path) is None


def test_cached_json_missing_ingredients(tmp_path: Path):
    key = "def456"
    path = cache.cache_path_for_key(key, cache_dir=tmp_path)
    path.write_text(json.dumps({"dish_name": "x"}), encoding="utf-8")
    assert cache.load_cached_result(key, cache_dir=tmp_path) is None


def test_clear_cache(tmp_path: Path):
    key = cache.build_cache_key(b"z", model_name="m")
    cache.save_cached_result(
        key,
        {"dish_name": "d", "ingredients": []},
        cache_dir=tmp_path,
    )
    assert cache.clear_cache(cache_dir=tmp_path) == 1
    assert cache.load_cached_result(key, cache_dir=tmp_path) is None
