"""Tests for nutritional loading and calorie calculations."""

from pathlib import Path

import pytest

import config
import nutrition

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "foods_sample.csv"


@pytest.fixture
def foods():
    return nutrition.load_foods(FIXTURE_CSV)


def test_config_points_to_root_foods_csv():
    assert config.FOODS_CSV_PATH == config.PROJECT_ROOT / "foods.csv"
    assert config.FOODS_CSV_PATH.name == "foods.csv"
    assert "data" not in config.FOODS_CSV_PATH.parts[-2:]


def test_missing_csv_raises_clear_error(tmp_path: Path):
    missing = tmp_path / "foods.csv"
    with pytest.raises(FileNotFoundError) as exc_info:
        nutrition.load_foods(missing)
    message = str(exc_info.value)
    assert "foods.csv" in message
    assert str(missing) in message


def test_load_foods_exact_names(foods):
    assert "Pasta" in foods.by_name
    assert foods.by_name["Pasta"] == 131
    assert foods.by_name["Egg"] == 155


def test_exact_canonical_match(foods):
    assert nutrition.match_food("Pasta", foods) == "Pasta"
    assert nutrition.match_food("pasta", foods) == "Pasta"
    assert nutrition.match_food("  EGG  ", foods) == "Egg"


def test_alias_match(foods):
    assert nutrition.match_food("spaghetti", foods) == "Pasta"
    assert nutrition.match_food("cooked white rice", foods) == "Rice"
    assert nutrition.match_food("fresh apple", foods) == "Apple"


def test_duplicate_alias_is_ambiguous(foods):
    # sharedalias points at two different foods
    assert nutrition.match_food("sharedalias", foods) is None


def test_unmatched_ingredient(foods):
    assert nutrition.match_food("mystery garnish", foods) is None


def test_fuzzy_suggest_does_not_assign(foods):
    # Close name may be suggested, but match_food stays unmatched
    assert nutrition.match_food("pastaa", foods) is None
    suggestions = nutrition.suggest_foods("pastaa", foods)
    assert "Pasta" in suggestions


def test_calories_for_ingredient_basic():
    # 150 g pasta at 131 kcal/100 g = 196.5
    assert nutrition.calories_for_ingredient(150, 131) == 196.5


def test_calories_for_ingredient_invalid_weights():
    assert nutrition.calories_for_ingredient(-10, 165) == 0.0
    assert nutrition.calories_for_ingredient(100, -1) == 0.0
    assert nutrition.calories_for_ingredient(None, 165) == 0.0


def test_empty_ingredient_list(foods):
    result = nutrition.calculate_meal_calories([], foods)
    assert result["total_kcal"] is None
    assert result["rows"] == []
    assert result["unmatched"] == []
    assert result["estimate_status"] == "incomplete"


def test_unknown_food_is_unmatched_incomplete(foods):
    result = nutrition.calculate_meal_calories(
        [{"name": "mystery garnish", "grams": 20}],
        foods,
    )
    assert result["total_kcal"] is None
    assert "mystery garnish" in result["unmatched"]
    assert result["rows"][0]["matched"] is False
    assert result["rows"][0]["kcal"] is None
    assert result["estimate_status"] == "incomplete"


def test_partial_estimate(foods):
    result = nutrition.calculate_meal_calories(
        [
            {"name": "pasta", "grams": 100},
            {"name": "mystery garnish", "grams": 20},
        ],
        foods,
    )
    assert result["estimate_status"] == "partial"
    assert result["total_kcal"] == 131.0
    assert "mystery garnish" in result["unmatched"]


def test_quantity_change_recalculates(foods):
    base = nutrition.calculate_meal_calories(
        [{"name": "egg", "grams": 50}],
        foods,
    )
    doubled = nutrition.calculate_meal_calories(
        [{"name": "egg", "grams": 100}],
        foods,
    )
    assert base["total_kcal"] == 77.5
    assert doubled["total_kcal"] == 155.0


def test_manual_matched_food_override(foods):
    result = nutrition.calculate_meal_calories(
        [
            {
                "name": "mystery garnish",
                "grams": 100,
                "matched_food": "Broccoli",
            }
        ],
        foods,
    )
    assert result["total_kcal"] == 34.0
    assert result["unmatched"] == []
    assert result["estimate_status"] == "complete"


def test_invalid_weight_string(foods):
    result = nutrition.calculate_meal_calories(
        [{"name": "egg", "grams": "not-a-number"}],
        foods,
    )
    assert result["rows"][0]["grams"] == 0.0
    assert result["total_kcal"] == 0.0


def test_meal_total(foods):
    result = nutrition.calculate_meal_calories(
        [
            {"name": "chicken breast", "grams": 100},
            {"name": "rice", "grams": 100},
        ],
        foods,
    )
    assert result["total_kcal"] == 295.0
    assert result["estimate_status"] == "complete"


def test_aliases_column_header_supported(tmp_path: Path):
    csv_file = tmp_path / "foods.csv"
    csv_file.write_text(
        "name,aliases,kcal_per_100g\n"
        "Potato,potato|boiled potato,87\n",
        encoding="utf-8",
    )
    loaded = nutrition.load_foods(csv_file)
    assert nutrition.match_food("boiled potato", loaded) == "Potato"


def test_root_foods_csv_loads_when_present():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    assert len(db.by_name) >= 50
    # Generic pasta alias should resolve without silent invention
    assert nutrition.match_food("pasta", db) is not None


def test_resolve_portion_from_pieces():
    portion = nutrition.resolve_portion(
        {"name": "chocolate", "count": 4, "grams_per_piece": 15}
    )
    assert portion["grams"] == 60.0
    assert portion["count"] == 4.0
    assert portion["grams_per_piece"] == 15.0


def test_resolve_portion_infers_grams_per_piece():
    portion = nutrition.resolve_portion(
        {"name": "apple", "grams": 180, "count": 1}
    )
    assert portion["grams"] == 180.0
    assert portion["grams_per_piece"] == 180.0


def test_piece_calories(foods):
    result = nutrition.calculate_meal_calories(
        [
            {
                "name": "dark chocolate",
                "count": 4,
                "grams_per_piece": 15,
            }
        ],
        foods,
    )
    # Fixture dark chocolate = 546 kcal/100g → 60 g = 327.6
    assert result["rows"][0]["grams"] == 60.0
    assert result["rows"][0]["kcal"] == 327.6
    assert result["rows"][0]["kcal_per_piece"] == 81.9
    assert result["estimate_status"] == "complete"


def test_approximate_identification_flag(foods):
    # Fixture has no "unspecified" food; create a tiny temp DB
    approx_db = nutrition.FoodsDatabase()
    approx_db.by_name["Meat, unspecified, cooked"] = 250.0
    approx_db._canonical_lookup["meat, unspecified, cooked"] = (
        "Meat, unspecified, cooked"
    )
    approx_db._alias_lookup["meat"] = ["Meat, unspecified, cooked"]
    result = nutrition.calculate_meal_calories(
        [{"name": "meat", "grams": 100}],
        approx_db,
    )
    assert result["rows"][0]["approximate"] is True
    assert result["rows"][0]["name"] == "Meat, unspecified, cooked"


def test_root_csv_generic_and_specific_matches():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()

    # Generic animal words → cooked generics, not cuts
    assert nutrition.match_food("beef", db) == "Beef, cooked"
    assert nutrition.match_food("pork", db) == "Pork, cooked"
    assert nutrition.match_food("meat", db) == "Meat, unspecified, cooked"

    # Specific cuts / preparations stay specific
    assert nutrition.match_food("pork belly", db) == "Pork belly, cooked"
    assert nutrition.match_food("beef brisket", db) == "Beef brisket, cooked"
    assert nutrition.match_food("fried chicken", db) == "Chicken, fried"
    assert nutrition.match_food("roast duck", db) == "Duck, roasted"

    # Display name is the CSV canonical form
    meal = nutrition.calculate_meal_calories(
        [{"name": "pork belly", "grams": 80}],
        db,
    )
    assert meal["rows"][0]["name"] == "Pork belly, cooked"
    assert meal["rows"][0]["matched"] is True


def test_root_csv_new_entries_and_precedence():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    assert nutrition.match_food("bacon", db) == "Bacon, cooked"
    assert nutrition.match_food("shumai", db) == "Dumpling, cooked"
    assert nutrition.match_food("noodles", db) == "Noodles, cooked"
    assert nutrition.match_food("char siu", db) == "Char siu pork"
    assert nutrition.match_food("roast pork", db) == "Roast pork, cooked"
    assert nutrition.match_food("xiaolongbao", db) == "Xiaolongbao, steamed"
    assert nutrition.match_food("dumpling", db) == "Dumpling, cooked"
    assert nutrition.match_food("cake", db) == "Cake, plain"
    assert nutrition.match_food("cream puff", db) == "Choux pastry, baked"
    assert nutrition.match_food("seaweed", db) == "Seaweed, rehydrated"
    assert nutrition.match_food("dried seaweed", db) == "Seaweed, dried"
    # Specific noodle types still beat the generic "noodles" row
    assert nutrition.match_food("wheat noodles", db) == "Wheat noodles, cooked"
    assert nutrition.match_food("rice noodles", db) == "Rice noodles, cooked"
    meal = nutrition.calculate_meal_calories(
        [{"name": "bacon", "grams": 40}],
        db,
    )
    assert meal["estimate_status"] == "complete"
    assert meal["total_kcal"] == round(540 * 0.4, 1)


def test_root_csv_no_ambiguous_aliases():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    conflicts = {
        alias: names
        for alias, names in db._alias_lookup.items()
        if len(names) > 1
    }
    assert conflicts == {}


def test_safe_normalisation_colour_and_plural():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    # Preparation required; colour strip preserves raw/cooked tokens
    assert nutrition.match_food("raw green bell pepper", db) == "Bell pepper, raw"
    assert nutrition.match_food("cooked red bell pepper", db) == "Bell pepper, cooked"
    assert nutrition.match_food("green bell pepper", db) is None
    # Specific noodle phrases still resolve
    assert nutrition.match_food("rice noodles", db) == "Rice noodles, cooked"
    assert nutrition.match_food("wheat noodles", db) == "Wheat noodles, cooked"
    # Cautious VLM phrasing maps to the generic unspecified-meat row
    assert nutrition.match_food("unspecified meat", db) == "Meat, unspecified, cooked"
    assert nutrition.match_food("bao bun", db) == "Steamed bun, plain"
    # Preparation-aware onion / carrot; bare names do not invent prep
    assert nutrition.match_food("onion", db) is None
    assert nutrition.match_food("cooked onion", db) == "Onion, cooked"
    assert nutrition.match_food("raw onion", db) == "Onion, raw"
    assert nutrition.match_food("raw carrot", db) == "Carrot, raw"
    assert nutrition.match_food("cooked carrot", db) == "Carrot, cooked"
    assert nutrition.match_food("scallion", db) == "Spring onion, fresh"
    assert nutrition.match_food("ground meat", db) == "Minced meat, cooked"
    # Audit targets remain unique
    assert nutrition.match_food("egg", db) == "Egg, boiled"
    assert nutrition.match_food("roast duck", db) == "Duck, roasted"
    assert nutrition.match_food("fried chicken", db) == "Chicken, fried"
    assert nutrition.match_food("oil", db) == "Oil, vegetable"
    assert nutrition.match_food("chocolate", db) == "Chocolate, generic"


def test_negligible_unmatched_garnish_helper():
    assert nutrition.is_negligible_unmatched("salt", 2, None) is True
    assert nutrition.is_negligible_unmatched("mystery cake", 120, None) is False
    assert nutrition.is_negligible_unmatched("onion", 40, "Onion, cooked") is False


def test_large_piece_count_calories_are_deterministic():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    # 100 chocolates × 8 g is a plausible mixed-tray estimate; Python owns kcal
    meal = nutrition.calculate_meal_calories(
        [
            {
                "name": "chocolate",
                "count": 100,
                "grams_per_piece": 8,
            }
        ],
        db,
    )
    assert meal["rows"][0]["grams"] == 800.0
    assert meal["rows"][0]["kcal_per_piece"] == round(540 * 8 / 100, 1)
    assert meal["total_kcal"] == round(540 * 8, 1)
    assert meal["estimate_status"] == "complete"


def test_build_display_estimate_personal_portion():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    analysis = {
        "dish_name": "Family noodles",
        "is_family_sized": True,
        "suggested_servings": 4,
        "ai_calorie_estimate": 9999,
        "ingredients": [
            {"name": "wheat noodles", "grams": 400},
            {"name": "beef", "grams": 200},
        ],
    }
    display = nutrition.build_display_estimate(analysis, db)
    meal = nutrition.calculate_meal_calories(analysis["ingredients"], db)
    expected = float(int(round(meal["total_kcal"] / 4)))
    assert display["estimate_ready"] is True
    assert display["portion_kcal"] == expected
    assert display["show_serving_count"] is True
    # VLM estimate must never become the displayed total
    assert display["portion_kcal"] != 9999
    # Component table is scaled to one serving and matches the headline
    row_sum = sum(int(row.get("kcal_display", round(row["kcal"]))) for row in display["components"])
    assert row_sum == display["portion_kcal"]


def test_build_display_estimate_omits_unmatched_keeps_csv():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    analysis = {
        "dish_name": None,
        "suggested_servings": 1,
        "ai_calorie_estimate": None,
        "ingredients": [
            {"name": "rice", "grams": 180},
            {"name": "mystery protein slab", "grams": 150},
        ],
    }
    display = nutrition.build_display_estimate(analysis, db)
    rice_kcal = nutrition.calories_for_ingredient(180, db.by_name["Rice, cooked"])
    assert display["incomplete"] is True
    assert display["display_mode"] == "csv"
    assert display["estimate_ready"] is True
    assert display["portion_kcal"] == float(int(round(rice_kcal)))
    assert all(row["name"].lower() != "mystery protein slab" for row in display["components"])
    assert all("other food" not in row["name"].lower() for row in display["components"])


def test_build_display_estimate_never_uses_ai_for_headline():
    """AI above CSV must stay internal; headline remains matched CSV sum."""
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    analysis = {
        "dish_name": "Burger",
        "suggested_servings": 1,
        "ai_calorie_estimate": 100,
        "ingredients": [
            {"name": "burger bun", "grams": 80},
            {"name": "beef patty", "grams": 120},
            {"name": "mystery topping", "grams": 40},
        ],
    }
    display = nutrition.build_display_estimate(analysis, db)
    csv_sub = display["csv_portion_kcal"]
    assert csv_sub is not None and csv_sub > 100
    assert display["display_mode"] == "csv"
    assert display["portion_kcal"] == float(int(round(csv_sub)))
    assert display["total_label"] == "Total"
    assert display["ai_portion_kcal"] == 100.0
    assert all("other food" not in row["name"].lower() for row in display["components"])


def test_build_display_estimate_ai_not_added_when_above_csv():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    analysis = {
        "dish_name": None,
        "suggested_servings": 1,
        "ai_calorie_estimate": 900,
        "ingredients": [
            {"name": "rice", "grams": 100},
            {"name": "mystery protein slab", "grams": 150},
        ],
    }
    display = nutrition.build_display_estimate(analysis, db)
    rice_kcal = nutrition.calories_for_ingredient(100, db.by_name["Rice, cooked"])
    assert display["display_mode"] == "csv"
    assert display["portion_kcal"] == float(int(round(rice_kcal)))
    assert display["ai_portion_kcal"] == 900.0
    assert all(not row.get("is_other_estimate") for row in display["components"])
    assert all("other food" not in row["name"].lower() for row in display["components"])
    row_sum = sum(int(row.get("kcal_display", round(row["kcal"]))) for row in display["components"])
    assert row_sum == display["portion_kcal"]
    # AI must not be added on top of CSV
    assert display["portion_kcal"] != display["csv_portion_kcal"] + 900


def test_build_display_estimate_unavailable_when_nothing():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    analysis = {
        "dish_name": None,
        "suggested_servings": 1,
        "ai_calorie_estimate": None,
        "ingredients": [{"name": "mystery slab", "grams": 100}],
    }
    display = nutrition.build_display_estimate(analysis, db)
    assert display["display_mode"] == "unavailable"
    assert display["estimate_ready"] is False
    assert display["portion_kcal"] is None


def test_crepe_matched_veg_uses_csv_not_ai_gap():
    """Matched vegetable rows stay CSV; AI never invents an Other-food gap."""
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    analysis = {
        "dish_name": "Crepe",
        "suggested_servings": 1,
        "ai_calorie_estimate": 480,
        "ingredients": [
            {"name": "spinach", "grams": 30},
            {"name": "mushroom", "grams": 20},
        ],
    }
    display = nutrition.build_display_estimate(analysis, db)
    assert display["display_mode"] == "csv"
    assert display["portion_kcal"] is not None
    assert display["portion_kcal"] < 80
    assert display["ai_portion_kcal"] == 480.0
    assert all("other food" not in row["name"].lower() for row in display["components"])
    row_sum = sum(int(row.get("kcal_display", round(row["kcal"]))) for row in display["components"])
    assert row_sum == display["portion_kcal"]


def test_vague_sauce_never_matched():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    assert nutrition.match_food("sauce", db) is None
    assert nutrition.match_food("sauce, unspecified", db) is None
    assert nutrition.match_food("generic sauce", db) is None
    assert "Sauce, unspecified" not in db.by_name
    assert nutrition.match_food("curry sauce", db) == "Curry sauce, cooked"
    assert nutrition.match_food("mayonnaise", db) == "Mayonnaise"


def test_curry_fish_balls_components():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    analysis = {
        "dish_name": "Curry fish balls",
        "suggested_servings": 1,
        "ai_calorie_estimate": 450,
        "ingredients": [
            {"name": "fish balls", "grams": 150, "count": 6, "grams_per_piece": 25},
            {"name": "curry sauce", "grams": 80},
        ],
    }
    display = nutrition.build_display_estimate(analysis, db)
    assert display["display_mode"] == "csv"
    names = {row["name"] for row in display["components"]}
    assert "Fish balls, cooked" in names
    assert "Curry sauce, cooked" in names
    assert all("other food" not in name.lower() for name in names)
    # 150*1.1 + 80*1.2 = 165 + 96 = 261
    assert display["portion_kcal"] == 261
    row_sum = sum(int(row.get("kcal_display", round(row["kcal"]))) for row in display["components"])
    assert row_sum == 261


def test_siu_mai_uses_dumpling_reference():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    assert nutrition.match_food("siu mai", db) == "Dumpling, cooked"
    assert nutrition.match_food("shumai", db) == "Dumpling, cooked"
    assert "Siu mai, steamed" not in db.by_name
    analysis = {
        "dish_name": "Siu mai",
        "suggested_servings": 1,
        "ai_calorie_estimate": 400,
        "ingredients": [
            {"name": "dumpling", "grams": 180, "count": 6, "grams_per_piece": 30},
        ],
    }
    display = nutrition.build_display_estimate(analysis, db)
    assert display["dish_name"] == "Siu mai"
    assert display["components"][0]["name"] == "Dumpling, cooked"
    assert display["portion_kcal"] == 396  # 180 * 2.2


def test_merge_same_canonical_food_rows():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    meal = nutrition.calculate_meal_calories(
        [
            {"name": "tomato", "grams": 120},
            {"name": "fresh tomato", "grams": 80},
            {"name": "raw carrot", "grams": 50},
        ],
        db,
    )
    tomato_rows = [row for row in meal["rows"] if row["name"] == "Tomato, raw"]
    assert len(tomato_rows) == 1
    assert tomato_rows[0]["grams"] == 200.0
    assert tomato_rows[0]["kcal"] == round(18 * 2.0, 1)


def test_noodles_prawns_example_total():
    """Classroom example: wheat noodles + prawns + carrot ≈ 358 kcal."""
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    analysis = {
        "dish_name": "Noodles with prawns",
        "suggested_servings": 1,
        "ai_calorie_estimate": 400,
        "ingredients": [
            {"name": "wheat noodles", "grams": 180},
            {"name": "prawns", "grams": 100},
            {"name": "cooked carrot", "grams": 30},
        ],
    }
    display = nutrition.build_display_estimate(analysis, db)
    assert display["display_mode"] == "csv"
    assert display["portion_kcal"] == 358
    assert display["total_label"] == "Total"
    assert display["portion_grams"] == 310
    row_sum = sum(int(row.get("kcal_display", round(row["kcal"]))) for row in display["components"])
    assert row_sum == 358


def test_dish_name_never_matched_as_ingredient():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    analysis = {
        "dish_name": "Jianbing",
        "suggested_servings": 1,
        "ai_calorie_estimate": 450,
        "ingredients": [
            {"name": "jianbing", "grams": 220},
            {"name": "egg", "grams": 50},
        ],
    }
    display = nutrition.build_display_estimate(analysis, db)
    assert all("jianbing" not in row["name"].lower() for row in display["components"])
    # Dish-name row rejected; egg alone stays CSV (AI never becomes the headline)
    assert display["display_mode"] == "csv"
    assert display["ai_portion_kcal"] == 450.0


def test_reject_component_same_as_dish_helper():
    assert nutrition.component_is_dish_name("Jianbing", "Jianbing") is True
    assert nutrition.component_is_dish_name("egg", "Jianbing") is False
    assert nutrition.component_is_dish_name("wheat wrapper", "Jianbing") is False


def test_root_csv_v10_aliases():
    if not config.FOODS_CSV_PATH.exists():
        pytest.skip("root foods.csv not present yet")
    db = nutrition.load_foods()
    assert nutrition.match_food("celery", db) == "Celery, cooked"
    assert nutrition.match_food("sesame seed bun", db) == "Burger bun"
    assert nutrition.match_food("pierogi", db) == "Pierogi, cooked"
    assert nutrition.match_food("tzatziki", db) == "Tzatziki sauce"
    assert nutrition.match_food("strawberry cake", db) == "Cake, plain"
    assert nutrition.match_food("purple sweet potato", db) == "Sweet potato, cooked"
    assert nutrition.match_food("lemon tea", db) == "Lemon tea, sweetened"
    assert nutrition.match_food("mayonnaise", db) == "Mayonnaise"
    assert nutrition.match_food("fries", db) == "Potato, fried"
    # Composite dish names removed from CSV — must not match as foods
    assert nutrition.match_food("crepe", db) is None
    assert nutrition.match_food("jianbing", db) is None
    assert "Crepe, cooked" not in db.by_name
    assert "Jianbing, prepared" not in db.by_name
    assert nutrition.match_food("wheat wrapper", db) == "Wheat wrapper, cooked"
    assert nutrition.match_food("fried cracker", db) == "Fried cracker, crispy"
    assert nutrition.match_food("cream sauce", db) == "Cream sauce"
    assert nutrition.match_food("salad dressing", db) == "Salad dressing"
    assert nutrition.match_food("dipping sauce", db) is None
    assert nutrition.match_food("sweet and sour sauce", db) == "Sweet and sour sauce"
    assert nutrition.match_food("parmesan", db) == "Parmesan cheese"
    assert nutrition.match_food("cooked jellyfish", db) == "Jellyfish, prepared"
    assert db.by_name["Seitan, cooked"] == 130
    assert db.by_name["Fish balls, cooked"] == 110
    assert db.by_name["Dumpling, cooked"] == 220
    assert db.by_name["Mayonnaise"] == 680
    assert db.by_name["Cream sauce"] == 180
    assert nutrition.match_food("pizza crust", db) == "Pizza dough, baked"
    assert nutrition.match_food("raw radish", db) == "Radish, raw"
    assert nutrition.match_food("cooked tomato", db) == "Tomato, cooked"
    assert nutrition.match_food("fried egg", db) == "Egg, fried"
    assert nutrition.match_food("ketchup", db) == "Tomato ketchup"
    assert nutrition.match_food("sweet pastry", db) == "Sweet pastry, baked"
    assert nutrition.match_food("pastry", db) == "Sweet pastry, baked"
    assert nutrition.match_food("braised pork", db) == "Pork belly, cooked"
    assert nutrition.match_food("crushed nuts", db) == "Nuts, mixed"
    assert nutrition.match_food("seafood", db) == "Seafood, mixed, cooked"
    assert nutrition.match_food("whole fish", db) == "Fish, cooked"
    conflicts = {
        alias: names
        for alias, names in db._alias_lookup.items()
        if len(names) > 1
    }
    assert conflicts == {}
