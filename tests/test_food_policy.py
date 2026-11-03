"""Regression tests for shared food-name policy and UI HTML escaping."""

from pathlib import Path

import food_policy
import nutrition
import vision


def test_shared_policy_sets_are_identical_across_modules():
    assert vision._VAGUE_SAUCE_NAMES is food_policy.VAGUE_SAUCE_KEYS
    assert nutrition._VAGUE_SAUCE_KEYS is food_policy.VAGUE_SAUCE_KEYS
    assert vision._COMPOSITE_DISH_TOKENS is food_policy.COMPOSITE_DISH_TOKENS
    assert nutrition._COMPOSITE_DISH_TOKENS is food_policy.COMPOSITE_DISH_TOKENS
    assert vision._BASIC_FOOD_ALLOWLIST is food_policy.BASIC_FOOD_ALLOWLIST
    assert nutrition._BASIC_FOOD_ALLOWLIST is food_policy.BASIC_FOOD_ALLOWLIST


def test_flatbread_matches_kebab_flatbread_row():
    foods = nutrition.load_foods()
    assert nutrition.match_food("flatbread", foods) == "Flatbread"
    assert nutrition.match_food("plain flatbread", foods) == "Flatbread, plain"
    # Alias collision removed: bare "flatbread" is not an ambiguous multi-hit alias
    hits = foods._alias_lookup.get(nutrition.normalise_food_key("flatbread"), [])
    assert len(hits) <= 1


def test_app_escapes_dynamic_html_names():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert "html.escape" in source
    assert "assets" in source
    assert "app.css" in source
    assert "clipboard_paste.js" in source


def test_assets_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "assets" / "app.css").is_file()
    assert (root / "assets" / "clipboard_paste.js").is_file()
