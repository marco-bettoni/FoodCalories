"""Tests for vision validation and demo mode (no live Ollama required)."""

import pytest

import config
import vision


def test_schema_and_prompt_versions_bumped():
    assert config.PROMPT_VERSION.startswith("v12")
    assert config.SCHEMA_VERSION == "v12"


def test_prompt_requires_english_generic_names():
    prompt = vision.DEFAULT_PROMPT.lower()
    assert "english" in prompt
    assert "dish_name" in prompt
    assert "dish_confidence" in prompt
    assert "unspecified meat" in prompt
    assert "do not" in prompt or "never" in prompt
    assert "count" in prompt
    assert "grams_per_piece" in prompt
    assert "filename" in prompt
    assert "jianbing" in prompt
    assert "ai_calorie_estimate" in prompt
    assert "allergens" in prompt
    assert "spiciness" in prompt
    assert "suggested_servings" in prompt
    assert "family" in prompt or "shared" in prompt
    assert "components" in prompt
    assert "null" in prompt
    assert "preparation" in prompt
    assert "raw" in prompt and "cooked" in prompt
    assert "crudit" in prompt or "hummus" in prompt
    # Dish names must not be treated as ingredients
    assert "never the complete dish" in prompt or "never the\n  complete dish" in prompt or "food components" in prompt


def test_validate_meal_result_ok():
    data = {
        "dish_name": "Rice bowl",
        "ingredients": [
            {"name": "rice", "grams": 200},
        ],
    }
    result = vision.validate_meal_result(data)
    assert result["dish_name"] == "Rice bowl"
    assert result["ingredients"][0]["grams"] == 200
    assert result["suggested_servings"] == 1
    assert result["spiciness"] == "unknown"
    assert result["allergens"] == []
    assert "visible" not in result["ingredients"][0]
    assert "assumptions" not in result


def test_optional_null_dish_name():
    result = vision.validate_meal_result(
        {
            "dish_name": None,
            "dish_confidence": None,
            "ingredients": [{"name": "apple", "grams": 180}],
        }
    )
    assert result["dish_name"] is None
    assert result["dish_confidence"] is None
    assert result["ingredients"][0]["name"] == "apple"


def test_dish_confidence_accepted():
    result = vision.validate_meal_result(
        {
            "dish_name": "Spaghetti carbonara",
            "dish_confidence": "High",
            "ingredients": [{"name": "pasta", "grams": 200}],
        }
    )
    assert result["dish_name"] == "Spaghetti carbonara"
    assert result["dish_confidence"] == "high"


def test_invalid_dish_confidence_becomes_null():
    result = vision.validate_meal_result(
        {
            "dish_name": "Fried chicken",
            "dish_confidence": "maybe",
            "ingredients": [{"name": "fried chicken", "grams": 200}],
        }
    )
    assert result["dish_confidence"] is None


def test_numeric_dish_confidence_mapped():
    result = vision.validate_meal_result(
        {
            "dish_name": "chocolates",
            "dish_confidence": 0.95,
            "ingredients": [{"name": "chocolate", "grams": 50}],
        }
    )
    assert result["dish_confidence"] == "high"


def test_unknown_dish_becomes_null():
    result = vision.validate_meal_result(
        {
            "dish_name": "Unknown dish",
            "ingredients": [{"name": "banana", "grams": 120}],
        }
    )
    assert result["dish_name"] is None


def test_family_servings_and_ai_estimate():
    result = vision.validate_meal_result(
        {
            "dish_name": "Hot pot",
            "is_family_sized": True,
            "suggested_servings": 4,
            "ai_calorie_estimate": 2200,
            "allergens": ["soy", "wheat", "Shellfish"],
            "spiciness": "hot",
            "ingredients": [{"name": "broth", "grams": 800}],
        }
    )
    assert result["is_family_sized"] is True
    assert result["suggested_servings"] == 4
    assert result["ai_calorie_estimate"] == 2200
    assert "soy" in result["allergens"]
    assert "wheat/gluten" in result["allergens"]
    assert "crustaceans" in result["allergens"]
    assert result["spiciness"] == "hot"


def test_malformed_empty_response_raises():
    with pytest.raises(ValueError):
        vision.validate_meal_result(None)
    with pytest.raises(ValueError):
        vision.validate_meal_result("")


def test_merge_shrimp_prawn_duplicates():
    result = vision.validate_meal_result(
        {
            "dish_name": "Mala xiang guo",
            "ingredients": [
                {"name": "prawns", "grams": 100, "count": 5, "grams_per_piece": 20},
                {"name": "shrimp", "grams": 100, "count": 5, "grams_per_piece": 20},
                {"name": "tofu", "grams": 120},
            ],
        }
    )
    names = [item["name"].lower() for item in result["ingredients"]]
    assert names.count("prawns") + names.count("shrimp") == 1
    merged = result["ingredients"][0]
    assert merged["grams"] == 200
    assert merged["count"] == 10


def test_bulk_rice_loses_count_one():
    result = vision.validate_meal_result(
        {
            "dish_name": None,
            "ingredients": [
                {"name": "rice", "grams": 200, "count": 1, "grams_per_piece": 200},
            ],
        }
    )
    item = result["ingredients"][0]
    assert item["count"] is None
    assert item["grams_per_piece"] is None
    assert item["grams"] == 200


def test_individual_food_recognition_schema():
    result = vision.validate_meal_result(
        {
            "dish_name": None,
            "ingredients": [{"name": "dark chocolate", "grams": 20}],
        }
    )
    assert len(result["ingredients"]) == 1
    assert result["ingredients"][0]["name"] == "dark chocolate"


def test_optional_piece_fields():
    result = vision.validate_meal_result(
        {
            "dish_name": None,
            "ingredients": [
                {
                    "name": "chocolate",
                    "grams": 60,
                    "count": 4,
                    "grams_per_piece": 15,
                }
            ],
        }
    )
    item = result["ingredients"][0]
    assert item["count"] == 4
    assert item["grams_per_piece"] == 15
    assert item["grams"] == 60


def test_validate_rejects_negative_grams():
    with pytest.raises(ValueError):
        vision.validate_meal_result(
            {
                "dish_name": "x",
                "ingredients": [
                    {"name": "egg", "grams": -5},
                ],
            }
        )


def test_validate_rejects_empty_name():
    with pytest.raises(ValueError):
        vision.validate_meal_result(
            {
                "dish_name": "x",
                "ingredients": [
                    {"name": "  ", "grams": 10},
                ],
            }
        )


def test_legacy_estimated_grams_accepted():
    result = vision.validate_meal_result(
        {
            "dish_name": "Bowl",
            "ingredients": [
                {"name": "rice", "estimated_grams": 150, "visible": True},
            ],
            "assumptions": ["ignored"],
        }
    )
    assert result["ingredients"][0]["grams"] == 150
    assert "visible" not in result["ingredients"][0]


def test_demo_mode_analyse_meal():
    result = vision.analyse_meal(b"unused", demo_mode=True)
    assert result["demo_mode"] is True
    assert result["from_cache"] is False
    assert len(result["ingredients"]) >= 1
    assert "assumptions" not in result
    assert "allergens" in result
    assert "spiciness" in result
    assert all("grams" in item for item in result["ingredients"])


def test_extract_json_object_with_fences():
    text = """```json
{"dish_name": null, "ingredients": [{"name": "apple", "grams": 160}]}
```"""
    raw = vision._extract_json_object(text)
    assert raw["dish_name"] is None
    assert raw["ingredients"][0]["name"] == "apple"


def test_portion_sanity_caps_implausible_mass():
    result = vision.validate_meal_result(
        {
            "dish_name": None,
            "is_family_sized": False,
            "ingredients": [
                {"name": "sea urchin", "grams": 3400},
                {"name": "rice", "grams": 200},
            ],
        }
    )
    by_name = {item["name"]: item for item in result["ingredients"]}
    assert by_name["sea urchin"]["grams"] == 80.0
    assert by_name["rice"]["grams"] == 200.0
    assert any("sea urchin" in warning.lower() for warning in result["warnings"])


def test_recipe_hallucinations_dropped():
    result = vision.validate_meal_result(
        {
            "dish_name": "Strawberry cake",
            "ingredients": [
                {"name": "cake", "grams": 300},
                {"name": "flour", "grams": 200},
                {"name": "butter", "grams": 100},
                {"name": "water", "grams": 50},
            ],
        }
    )
    names = [item["name"].lower() for item in result["ingredients"]]
    assert "cake" in names
    assert "flour" not in names
    assert "butter" not in names
    assert "water" not in names


def test_piece_fields_reconciled():
    result = vision.validate_meal_result(
        {
            "dish_name": None,
            "ingredients": [
                {
                    "name": "dumpling",
                    "grams": 999,
                    "count": 8,
                    "grams_per_piece": 25,
                }
            ],
        }
    )
    item = result["ingredients"][0]
    assert item["grams"] == 200.0
    assert item["count"] == 8
    assert item["grams_per_piece"] == 25


def test_dumpling_wrapper_and_filling_collapsed():
    result = vision.validate_meal_result(
        {
            "dish_name": None,
            "ingredients": [
                {
                    "name": "dumpling wrapper",
                    "grams": 120,
                    "count": 6,
                    "grams_per_piece": 20,
                },
                {
                    "name": "meat filling",
                    "grams": 90,
                    "count": 6,
                    "grams_per_piece": 15,
                },
            ],
        }
    )
    names = [item["name"].lower() for item in result["ingredients"]]
    assert len(result["ingredients"]) == 1
    assert "dumpling" in names[0]
    assert "wrapper" not in names[0]
    assert result["ingredients"][0]["grams"] == 210.0
    assert any("dumpling" in w.lower() for w in result["warnings"])


def test_honey_mislabelled_cake_corrected():
    result = vision.validate_meal_result(
        {
            "dish_name": "Strawberry honey cake",
            "ingredients": [
                {"name": "strawberry", "grams": 120},
                {"name": "honey", "grams": 80},
            ],
        }
    )
    names = [item["name"].lower() for item in result["ingredients"]]
    assert "cake" in names
    assert "honey" not in names
    assert any("cake" in w.lower() for w in result["warnings"])


def test_recipe_cluster_without_finished_food_salvages_dish():
    result = vision.validate_meal_result(
        {
            "dish_name": "Pastries",
            "ingredients": [
                {"name": "rice flour", "grams": 400},
                {"name": "milk", "grams": 200},
                {"name": "egg", "grams": 100},
                {"name": "flavoring", "grams": 20},
            ],
        }
    )
    # Recipe rows drop; dish name salvages a finished pastry unit
    assert len(result["ingredients"]) == 1
    assert "pastry" in result["ingredients"][0]["name"].lower()
    assert result["warnings"]


def test_lone_fried_egg_not_dropped_as_recipe():
    result = vision.validate_meal_result(
        {
            "dish_name": "Fried egg",
            "ingredients": [{"name": "egg", "grams": 60}],
        }
    )
    assert len(result["ingredients"]) == 1
    assert result["ingredients"][0]["name"].lower() == "egg"


def test_prompt_mentions_burger_and_whole_items():
    prompt = vision.DEFAULT_PROMPT.lower()
    assert "crepe" in prompt or "crêpe" in prompt
    assert "jianbing" in prompt
    assert "mayonnaise" in prompt
    assert "burger" in prompt
    assert "wheat wrapper" in prompt
    assert "components" in prompt


def test_chocolate_tray_count_expanded():
    result = vision.validate_meal_result(
        {
            "dish_name": "chocolate",
            "ingredients": [
                {"name": "chocolate", "grams": 1000, "count": 1, "grams_per_piece": 1000},
            ],
        }
    )
    item = result["ingredients"][0]
    assert item["count"] == 125.0
    assert item["grams_per_piece"] == 8.0
    assert item["grams"] == 1000.0


def test_jianbing_dish_name_rejected_as_ingredient():
    result = vision.validate_meal_result(
        {
            "dish_name": "Jianbing",
            "ingredients": [
                {"name": "jianbing", "grams": 220},
                {"name": "egg", "grams": 50},
                {"name": "wheat wrapper", "grams": 100},
            ],
        }
    )
    names = [item["name"].lower() for item in result["ingredients"]]
    assert "jianbing" not in names
    assert "egg" in names
    assert any("wrapper" in n for n in names)


def test_sandwich_bread_halves_merged():
    result = vision.validate_meal_result(
        {
            "dish_name": "Gyro sandwich",
            "ingredients": [
                {"name": "pita bread", "grams": 90},
                {"name": "pita", "grams": 85},
                {"name": "cooked meat", "grams": 120},
            ],
        }
    )
    breads = [
        item
        for item in result["ingredients"]
        if "pita" in item["name"].lower() or "bread" in item["name"].lower()
    ]
    assert len(breads) == 1
    assert breads[0]["grams"] == 90.0


def test_vague_sauce_dropped_in_validation():
    result = vision.validate_meal_result(
        {
            "dish_name": "Fish with sauce",
            "suggested_servings": 1,
            "ai_calorie_estimate": 400,
            "ingredients": [
                {"name": "cooked fish", "grams": 180},
                {"name": "sauce, unspecified", "grams": 60},
                {"name": "sauce", "grams": 40},
            ],
        }
    )
    names = [item["name"].lower() for item in result["ingredients"]]
    assert any("fish" in name for name in names)
    assert not any(vision._is_vague_sauce_name(name) for name in names)


def test_siu_mai_dish_name_and_dumpling_component():
    result = vision.validate_meal_result(
        {
            "dish_name": "Shumai",
            "suggested_servings": 1,
            "ai_calorie_estimate": 350,
            "ingredients": [
                {
                    "name": "siu mai",
                    "grams": 180,
                    "count": 6,
                    "grams_per_piece": 30,
                },
            ],
        }
    )
    assert result["dish_name"] == "Siu mai"
    assert result["ingredients"][0]["name"] == "dumpling"
    assert result["ingredients"][0]["count"] == 6


def test_curry_fish_balls_keeps_separate_sauce():
    result = vision.validate_meal_result(
        {
            "dish_name": "Curry fish balls",
            "suggested_servings": 1,
            "ai_calorie_estimate": 420,
            "ingredients": [
                {"name": "fish balls", "grams": 150, "count": 6, "grams_per_piece": 25},
                {"name": "curry sauce", "grams": 80},
            ],
        }
    )
    names = {item["name"].lower() for item in result["ingredients"]}
    assert "fish balls" in names
    assert "curry sauce" in names
    sauce = next(item for item in result["ingredients"] if "curry" in item["name"].lower())
    assert float(sauce["grams"]) == 80.0
