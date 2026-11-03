"""
Nutritional data loading and calorie calculations.

IMPORTANT: calories are calculated in ordinary Python.
The AI model only identifies foods and estimates grams.
It must never invent kcal values used in the final total.
"""

from __future__ import annotations

import csv
import difflib
from pathlib import Path

import config
from food_policy import BASIC_FOOD_ALLOWLIST, COMPOSITE_DISH_TOKENS, VAGUE_SAUCE_KEYS

# Re-export shared policy sets (historical private names used in tests/debugging).
_VAGUE_SAUCE_KEYS = VAGUE_SAUCE_KEYS
_COMPOSITE_DISH_TOKENS = COMPOSITE_DISH_TOKENS
_BASIC_FOOD_ALLOWLIST = BASIC_FOOD_ALLOWLIST


def normalise_food_key(text: str) -> str:
    """
    Normalise a food name for case-insensitive matching.

    Lowercases the string and collapses unnecessary whitespace.
    Example: "  Pork   Belly " → "pork belly"
    """
    return " ".join(str(text).strip().lower().split())


# Colour words often prefixed by VLMs ("green bell pepper").
# Stripping them is safe only when the remaining phrase still matches uniquely.
_COLOUR_WORDS = {
    "green",
    "red",
    "yellow",
    "orange",
    "purple",
    "white",
    "black",
    "brown",
    "pink",
    "golden",
}


def _singular_plural_variants(key: str) -> list[str]:
    """Return simple singular/plural spelling variants for one key."""
    variants = [key]
    if len(key) <= 3:
        return variants
    if key.endswith("ies") and len(key) > 4:
        variants.append(key[:-3] + "y")
    elif key.endswith("oes") and len(key) > 4:
        variants.append(key[:-2])
    elif key.endswith("ses") and len(key) > 4:
        variants.append(key[:-2])
    elif key.endswith("s") and not key.endswith("ss"):
        variants.append(key[:-1])
    else:
        variants.append(key + "s")
    return variants


def match_query_variants(query: str) -> list[str]:
    """
    Build safe normalisation variants for matching.

    Order matters: try the original phrase first, then colour-stripped
    and singular/plural forms. Does not invent preparation methods.
    """
    base = normalise_food_key(query)
    if not base:
        return []

    ordered: list[str] = []
    seen: set[str] = set()

    def add(text: str) -> None:
        cleaned = normalise_food_key(text)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            ordered.append(cleaned)

    add(base)

    # Drop leading/embedded colour adjectives: "green bell pepper" → "bell pepper"
    words = base.split()
    without_colour = [word for word in words if word not in _COLOUR_WORDS]
    if without_colour and without_colour != words:
        add(" ".join(without_colour))

    # Cautious VLM phrasing → CSV-friendly keys (does not invent a specific food)
    # "unspecified meat" → "meat" (matches Meat, unspecified, cooked)
    if "unspecified" in words:
        without_unspecified = [word for word in words if word != "unspecified"]
        if without_unspecified:
            add(" ".join(without_unspecified))
    # "bao bun" / "steamed bao" often used for plain steamed buns
    if base in {"bao bun", "bao buns", "steamed bao", "steamed bao bun"}:
        add("steamed bun")
    if base in {
        "grilled meat",
        "roast meat",
        "roasted meat",
        "cooked meat",
        "sliced meat",
    }:
        add("meat")
    if base in {"cream puff pastry", "puff pastry shell", "choux shell"}:
        add("cream puff")
    if base in {"seafood dumpling", "seafood dumplings"}:
        add("dumpling")
    if base in {"fish fillet", "fish fillets"}:
        add("fish")
    if base in {"green vegetables", "mixed vegetables", "vegetables", "veg"}:
        add("mixed vegetables")
    if base in {
        "wheat wrapper",
        "cooked wheat wrapper",
        "crepe wrapper",
        "thin wheat wrapper",
        "savoury wrapper",
        "savory wrapper",
    }:
        add("wheat wrapper")
    if base in {
        "fried cracker",
        "crispy fried cracker",
        "crispy cracker",
        "jianbing cracker",
    }:
        add("fried cracker")
    if base in {"french fries", "fries", "potato fries", "chips"}:
        add("french fries")
        add("fried potato")
    if base in {"mayonnaise", "mayo", "mayonnaise sauce"}:
        add("mayonnaise")
    if base in {"sweet pastry", "baked pastry", "pastry"}:
        add("sweet pastry")
    if base in {"chili sauce", "chilli sauce", "chili dipping sauce"}:
        add("sweet chilli sauce")
    if base in {"crushed nuts", "chopped nuts", "mixed nuts"}:
        add("mixed nuts")
    if base in {"seafood", "mixed seafood"}:
        add("seafood")
    if base in {"braised pork", "braised pork belly"}:
        add("pork belly")
    if base in {"whole fish", "grilled fish", "fried fish fillet", "fish fillet"}:
        add("fish")
    if base in {"broccoli greens"}:
        add("broccoli")
    if base in {"pita bread", "pita"}:
        add("pita bread")
        add("flatbread")
    if base in {"bun", "buns"}:
        add("steamed bun")
        add("burger bun")
    if base in {"unspecified meat patty", "meat patty", "burger meat patty"}:
        add("beef patty")
    if base in {"soft-boiled egg", "soft boiled egg", "softboiled egg"}:
        add("egg")
    if base in {"cooked scrambled egg", "scrambled egg", "scrambled eggs"}:
        add("fried egg")
    if base in {"tahini sauce", "tahini"}:
        add("sesame paste")
        add("tahini")
    if base in {"puff pastry"}:
        add("cream puff")
    if base in {
        "siu mai",
        "shumai",
        "steamed shumai",
        "pork siu mai",
        "siu mai dumpling",
    }:
        add("dumpling")
    if base in {
        "curry gravy",
        "yellow curry sauce",
        "fish ball curry sauce",
        "fishball curry sauce",
    }:
        add("curry sauce")
    if base in {
        "sweet-and-sour sauce",
        "sweet sour sauce",
    }:
        add("sweet and sour sauce")
    if base in {
        "prepared jellyfish",
        "cooked jellyfish",
        "seasoned jellyfish",
    }:
        add("jellyfish")
    if base in {
        "grated parmesan",
        "parmigiano reggiano",
        "parmesan cheese",
    }:
        add("parmesan")
    # Drop a leading "cooked "/"raw " only when the remainder is still specific
    for prefix in ("cooked ", "raw ", "fresh ", "melted "):
        if base.startswith(prefix) and len(base) > len(prefix) + 2:
            remainder = base[len(prefix) :]
            add(remainder)
            # Keep vegetable/meat prep honesty: do not invent the opposite prep
    if base.endswith(" chunks") or base.endswith(" cubes"):
        add(base.rsplit(" ", 1)[0])
    if base.endswith(" pieces"):
        add(base[: -len(" pieces")])
    if "udon" in words:
        add("wheat noodles")
        add("noodles")
    if base in {"cooked spaghetti", "spaghetti"}:
        add("pasta")
        add("spaghetti")
    if base in {"cooked pizza dough", "pizza dough cooked"}:
        add("pizza dough")
        add("pizza crust")
    if base in {"cooked cake", "cake cooked"}:
        add("cake")
    if base in {"cooked corn", "corn cooked", "sweetcorn"}:
        add("sweet corn")
        add("corn")
    if base in {"cooked tofu", "tofu cooked"}:
        add("tofu")
    if base in {"cooked fish fillet", "fish fillet cooked"}:
        add("fish")
    if base in {"meatballs", "meatball", "cooked meatballs"}:
        add("minced meat")
    if "sweet potato" in base and ("cube" in base or "cubes" in base):
        add("sweet potato")
    if base in {"baked dough", "fried dough"}:
        add("wheat wrapper")
        add("steamed bun")
    # Singular / plural for the full phrase and its last token
    for candidate in list(ordered):
        for variant in _singular_plural_variants(candidate):
            add(variant)
        parts = candidate.split()
        if len(parts) >= 2:
            for ending in _singular_plural_variants(parts[-1]):
                add(" ".join(parts[:-1] + [ending]))

    return ordered


def is_approximate_identification(matched_name: str | None) -> bool:
    """
    Return True when the CSV entry is a deliberately generic placeholder.

    Example: "Meat, unspecified, cooked" can supply calories, but the UI
    should label it as an approximate identification.
    """
    if not matched_name:
        return False
    return "unspecified" in matched_name.lower()


def is_vague_sauce_name(name: str | None) -> bool:
    """
    Return True for unnamed / unspecified sauces that must be omitted.

    Specific sauces (curry, mayonnaise, soy…) stay eligible for matching.
    """
    key = normalise_food_key(name or "")
    if not key:
        return False
    if key in VAGUE_SAUCE_KEYS:
        return True
    if key.startswith("sauce,") or key.startswith("sauce "):
        remainder = key.split(",", 1)[-1].strip() if "," in key else key[6:].strip()
        if remainder in {"", "unspecified", "generic", "unknown", "mixed"}:
            return True
    return False


# Tiny unmatched garnish names the UI may hide (still excluded from totals).
_NEGLIGIBLE_GARNISH_TOKENS = frozenset(
    {
        "salt",
        "pepper",
        "black pepper",
        "white pepper",
        "spice",
        "spices",
        "herb",
        "herbs",
        "fresh herbs",
        "seasoning",
        "garnish",
        "chili flake",
        "chilli flake",
        "chili flakes",
        "chilli flakes",
        "red chili",
        "red chilli",
        "red chili flakes",
        "red chilli flakes",
        "chili",
        "chilli",
        "dill",
        "fresh dill",
    }
)


def is_negligible_unmatched(name: str, grams: float | None, matched: str | None) -> bool:
    """
    Return True for tiny unmatched garnish rows that should not clutter the UI.

    Substantial unmatched foods remain significant for incomplete-estimate warnings.
    """
    if matched:
        return False
    key = normalise_food_key(name)
    try:
        weight = float(grams) if grams is not None else 0.0
    except (TypeError, ValueError):
        weight = 0.0
    if weight > 0 and weight < 8:
        return True
    if key in _NEGLIGIBLE_GARNISH_TOKENS and weight < 25:
        return True
    # Common micro-garnish phrases even when unmatched
    garnish_fragments = (
        "flake",
        "garnish",
        "seasoning",
        "spice",
        "herb",
        "parsley",
        "coriander",
        "cilantro",
        "spring onion",
        "green onion",
        "scallion",
        "sesame seed",
    )
    if weight < 25 and any(fragment in key for fragment in garnish_fragments):
        return True
    if weight <= 25 and ("chili" in key or "chilli" in key):
        return True
    return False


def suggested_servings_value(analysis: dict | None) -> float:
    """
    Read-only suggested serving count from vision output.

    Ordinary single-person meals default to 1. Shared platters use the
    model estimate, capped for classroom safety.
    """
    if not analysis:
        return 1.0
    raw = analysis.get("suggested_servings")
    try:
        servings = float(raw) if raw is not None else 1.0
    except (TypeError, ValueError):
        servings = 1.0
    if analysis.get("is_family_sized") and servings < 2:
        servings = 2.0
    if servings < 1:
        servings = 1.0
    if servings > 20:
        servings = 20.0
    return servings


def format_amount(row: dict) -> str:
    """Human-readable portion amount for the read-only component table."""
    count = row.get("count")
    if "grams_display" in row:
        grams = float(row.get("grams_display") or 0)
    else:
        grams = float(row.get("grams") or 0)
    gpp = row.get("grams_per_piece")
    # Only show piece arithmetic when there is more than one piece
    if count is not None and float(count) > 1:
        count_f = float(count)
        if gpp is not None and float(gpp) > 0:
            return f"{count_f:g} × {float(gpp):.0f} g"
        return f"{count_f:g} pieces"
    if grams <= 0:
        return ""
    if grams >= 10:
        return f"{grams:.0f} g"
    return f"{grams:.1f} g"


def _parse_ai_calorie_estimate(analysis: dict) -> float | None:
    """Read the VLM whole-photo kcal guess; None when missing or unusable."""
    raw = analysis.get("ai_calorie_estimate")
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return value


def component_is_dish_name(component: str, dish_name: str | None) -> bool:
    """
    Return True when a component merely repeats a composite dish name.

    Basic foods (apple, chocolate) may equal dish_name and still match CSV.
    """
    dish = normalise_food_key(dish_name or "")
    name = normalise_food_key(component or "")
    if not dish or not name:
        return False

    stop = {"the", "a", "an", "and", "with", "of", "prepared", "cooked"}
    dish_tokens = [t for t in dish.replace(",", " ").split() if t not in stop]
    name_tokens = [t for t in name.replace(",", " ").split() if t not in stop]
    joined_dish = " ".join(dish_tokens)
    joined_name = " ".join(name_tokens)

    for token in COMPOSITE_DISH_TOKENS:
        if token in name and token in dish:
            return True

    if joined_name != joined_dish and name != dish:
        return False

    if joined_name in BASIC_FOOD_ALLOWLIST or name in BASIC_FOOD_ALLOWLIST:
        return False
    return True


def components_incomplete_vs_ai(
    csv_portion: float | None,
    ai_portion: float | None,
    *,
    matched_count: int,
) -> bool:
    """
    Consistency check: CSV subtotal looks incomplete relative to the AI guess.

    Same serving scale required for both values. Flags garnish-only or
    obviously partial CSV totals — not merely a high AI guess when CSV
    already describes a substantial matched meal.
    """
    if ai_portion is None or ai_portion <= 0:
        return False
    if csv_portion is None:
        return True
    # Substantial matched personal portion → trust CSV even if AI differs
    if csv_portion >= 200 and matched_count >= 2:
        return False
    if csv_portion >= 280 and matched_count >= 1:
        return False
    # Tiny matched mass for what the model treats as a full meal
    if csv_portion < 100 and ai_portion >= 250:
        return True
    # Extreme gap with a still-small CSV (e.g. vegetables-only crepe)
    if csv_portion < 180 and csv_portion < 0.30 * ai_portion and ai_portion >= 300:
        return True
    return False


def _round_component_display(components: list[dict], target_kcal: float | None) -> list[dict]:
    """
    Round grams and kcal for display so integer kcal rows sum to the headline.

    The final edible row absorbs any ±1 kcal rounding remainder when a target
    is supplied. Amounts stay realistic.
    """
    if not components:
        return []

    rounded: list[dict] = []
    for row in components:
        entry = dict(row)
        grams = float(entry.get("grams") or 0)
        if grams >= 10:
            entry["grams_display"] = float(round(grams))
        elif grams > 0:
            entry["grams_display"] = round(grams, 1)
        else:
            entry["grams_display"] = 0.0
        entry["kcal_display"] = int(round(float(entry.get("kcal") or 0)))
        rounded.append(entry)

    if target_kcal is None:
        return rounded

    target = int(round(float(target_kcal)))
    edible_sum = sum(int(row["kcal_display"]) for row in rounded)
    if rounded:
        drift = target - edible_sum
        if drift != 0:
            rounded[-1]["kcal_display"] = int(rounded[-1]["kcal_display"]) + drift
            rounded[-1]["kcal"] = float(rounded[-1]["kcal_display"])

    return rounded


def build_display_estimate(analysis: dict, foods: FoodsDatabase | None = None) -> dict:
    """
    Build the read-only UI payload for one suggested personal portion.

    Calorie policy (CSV components only; AI estimate stays internal):

      1. Matched edible CSV components → headline = their personal-portion sum,
         Total row matches the headline.
      2. Vague sauces, unmatched names and garnishes are omitted — never shown
         as dashes, invented rows or balancing calories.
      3. Estimate unavailable when no credible matched component remains.

    Never invent an "Other food (estimated)" row. Never prefix "At least".
    Never silently add the independent AI estimate to the CSV total.
    dish_name is never matched to foods.csv.
    """
    if foods is None:
        foods = load_foods()

    dish_name_raw = analysis.get("dish_name")
    if isinstance(dish_name_raw, str):
        dish_name = dish_name_raw.strip() or None
    else:
        dish_name = None

    # Drop any ingredient that is clearly the complete dish name
    ingredients: list[dict] = []
    for item in list(analysis.get("ingredients") or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if component_is_dish_name(name, dish_name):
            continue
        if is_vague_sauce_name(name):
            continue
        ingredients.append(item)

    servings = suggested_servings_value(analysis)
    is_family = bool(analysis.get("is_family_sized")) or servings > 1.05

    meal = calculate_meal_calories(ingredients, foods)

    visible_rows: list[dict] = []
    significant_unmatched: list[str] = []

    for row in meal["rows"]:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        grams = row.get("grams")
        original = str(row.get("original_name") or name)
        if is_vague_sauce_name(name) or is_vague_sauce_name(original):
            continue
        if not row.get("matched"):
            if is_negligible_unmatched(name, grams, None):
                continue
            significant_unmatched.append(name)
            continue
        # Hide matched micro-garnishes from the visible list
        try:
            weight = float(grams or 0)
        except (TypeError, ValueError):
            weight = 0.0
        key = normalise_food_key(name)
        garnish_tokens = (
            "spring onion",
            "green onion",
            "scallion",
            "sesame",
            "herb",
            "parsley",
            "coriander",
            "cilantro",
            "ginger",
            "garlic",
            "dill",
            "chili",
            "chilli",
        )
        if weight > 0 and weight < 40 and any(token in key for token in garnish_tokens):
            # Keep calorie-dense oils/sauces even when small
            if "oil" not in key and "sauce" not in key and "mayo" not in key:
                continue
        if weight > 0 and weight < 8 and "onion" in key:
            continue
        if weight <= 0 or row.get("kcal") is None:
            continue
        visible_rows.append(row)

    # Scale whole-dish matched rows down to one suggested serving
    scale = 1.0 / servings if servings > 0 else 1.0
    components: list[dict] = []
    for row in visible_rows:
        count = row.get("count")
        scaled_count = float(count) * scale if count is not None else None
        components.append(
            {
                "name": row["name"],
                "grams": float(row["grams"]) * scale,
                "count": scaled_count,
                "grams_per_piece": row.get("grams_per_piece"),
                "kcal": float(row["kcal"]) * scale,
            }
        )

    status = meal["estimate_status"]
    whole_kcal = meal["total_kcal"]
    # Recalculate from visible rows only (garnishes / vague sauces already dropped)
    visible_whole = sum(float(row.get("kcal") or 0) for row in visible_rows)
    csv_portion = round(visible_whole * scale, 1) if visible_rows else None
    matched_count = len(visible_rows)

    ai_whole = _parse_ai_calorie_estimate(analysis)
    ai_portion = round(ai_whole * scale, 1) if ai_whole is not None else None

    # Teaching helper only — never drives the headline
    csv_incomplete = components_incomplete_vs_ai(
        csv_portion,
        ai_portion,
        matched_count=matched_count,
    )

    display_mode = "unavailable"
    portion_kcal: float | None = None
    estimate_ready = False
    incomplete = bool(significant_unmatched) or status != "complete"
    clarification = ""
    total_label = "Total"

    if csv_portion is not None and csv_portion > 0 and matched_count >= 1:
        display_mode = "csv"
        portion_kcal = csv_portion
        estimate_ready = True
    else:
        display_mode = "unavailable"
        portion_kcal = None
        estimate_ready = False
        components = []
        incomplete = True

    edible_grams = sum(float(row.get("grams") or 0) for row in components)
    portion_grams: float | None = None
    if edible_grams >= 40 and components:
        portion_grams = edible_grams

    components = _round_component_display(components, portion_kcal)
    if portion_kcal is not None:
        portion_kcal = float(int(round(float(portion_kcal))))
    if portion_grams is not None:
        portion_grams = float(round(portion_grams))

    return {
        "dish_name": dish_name,
        "servings": servings,
        "is_family_sized": is_family,
        "show_serving_count": is_family and servings > 1.05,
        "whole_dish_kcal": whole_kcal,
        "portion_kcal": portion_kcal,
        "portion_grams": portion_grams,
        "estimate_ready": estimate_ready,
        "incomplete": incomplete,
        "display_mode": display_mode,
        "clarification": clarification,
        "total_label": total_label,
        "csv_portion_kcal": csv_portion,
        "ai_portion_kcal": ai_portion,
        "components": components,
        "significant_unmatched": significant_unmatched,
        "meal": meal,
        "csv_incomplete_vs_ai": csv_incomplete,
    }


def resolve_portion(item: dict) -> dict:
    """
    Keep grams, piece count and grams-per-piece internally consistent.

    Rules (applied in Python, never by the model):
      - If count and grams_per_piece are both present → grams = count × grams_per_piece
      - If count and total grams are present but grams_per_piece is missing
        → grams_per_piece = grams / count
      - Never double-count: one total grams value drives calorie math

    Returns: {"grams": float, "count": float|None, "grams_per_piece": float|None}
    """
    # --- parse grams ---
    grams_raw = item.get("grams", item.get("estimated_grams"))
    try:
        grams = float(grams_raw) if grams_raw is not None else None
    except (TypeError, ValueError):
        grams = None
    if grams is not None and grams < 0:
        grams = 0.0

    # --- parse optional count ---
    count_raw = item.get("count")
    count: float | None
    try:
        count = float(count_raw) if count_raw is not None else None
    except (TypeError, ValueError):
        count = None
    if count is not None and count <= 0:
        count = None

    # --- parse optional grams per piece ---
    gpp_raw = item.get("grams_per_piece")
    grams_per_piece: float | None
    try:
        grams_per_piece = float(gpp_raw) if gpp_raw is not None else None
    except (TypeError, ValueError):
        grams_per_piece = None
    if grams_per_piece is not None and grams_per_piece < 0:
        grams_per_piece = 0.0

    # Prefer piece arithmetic for the total when both piece fields exist
    if count is not None and grams_per_piece is not None:
        grams = count * grams_per_piece
    elif count is not None and grams is not None and grams_per_piece is None:
        grams_per_piece = grams / count
    elif grams is None:
        grams = 0.0

    return {
        "grams": float(grams if grams is not None else 0.0),
        "count": count,
        "grams_per_piece": grams_per_piece,
    }


class FoodsDatabase:
    """
    In-memory nutritional reference loaded from foods.csv.

    CSV columns: name, alias|aliases, kcal_per_100g
    """

    def __init__(self) -> None:
        # Canonical display name -> kcal per 100 g
        self.by_name: dict[str, float] = {}
        # Normalised canonical name -> display name
        self._canonical_lookup: dict[str, str] = {}
        # Normalised alias -> list of display names (length > 1 means ambiguous)
        self._alias_lookup: dict[str, list[str]] = {}

    def names(self) -> list[str]:
        """Return sorted canonical food names for dropdowns."""
        return sorted(self.by_name.keys(), key=str.lower)

    def kcal(self, display_name: str) -> float | None:
        """Return kcal/100g for a canonical display name, or None."""
        return self.by_name.get(display_name)


def load_foods(csv_path: Path | None = None) -> FoodsDatabase:
    """
    Load the nutritional CSV into a FoodsDatabase.

    Raises FileNotFoundError with a clear classroom message if the file
    is missing. Does not fall back to any other CSV path.
    """
    path = csv_path if csv_path is not None else config.FOODS_CSV_PATH

    if not path.exists():
        raise FileNotFoundError(
            f"Nutritional dataset not found at:\n{path}\n\n"
            "Expected a project-root file named foods.csv with columns:\n"
            "name,alias,kcal_per_100g\n\n"
            "Create or restore that file, then reload the app."
        )

    db = FoodsDatabase()

    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            name_raw = (row.get("name") or row.get("food") or "").strip()
            kcal_raw = (row.get("kcal_per_100g") or "").strip()
            if not name_raw or not kcal_raw:
                continue

            try:
                kcal = float(kcal_raw)
            except ValueError:
                continue

            # Keep the first occurrence of a canonical name
            key = normalise_food_key(name_raw)
            if key in db._canonical_lookup:
                continue

            db.by_name[name_raw] = kcal
            db._canonical_lookup[key] = name_raw

            # Support both "alias" and "aliases" column headers
            alias_field = row.get("alias")
            if alias_field is None:
                alias_field = row.get("aliases")
            alias_text = (alias_field or "").strip()

            if not alias_text:
                continue

            for part in alias_text.split("|"):
                alias = normalise_food_key(part)
                # Ignore empty aliases and aliases that duplicate the canonical name
                if not alias or alias == key:
                    continue
                hits = db._alias_lookup.setdefault(alias, [])
                # Ignore repeated aliases for the same food; keep collisions
                if name_raw not in hits:
                    hits.append(name_raw)

    return db


def list_food_names(foods: FoodsDatabase | None = None) -> list[str]:
    """Return sorted food names from the reference database."""
    if foods is None:
        foods = load_foods()
    return foods.names()


def _lookup_exact(key: str, foods: FoodsDatabase) -> str | None | bool:
    """
    Look up one normalised key.

    Returns:
      - display name on a unique hit
      - False when the key is ambiguous across multiple foods
      - None on a miss
    """
    if key in foods._canonical_lookup:
        return foods._canonical_lookup[key]

    alias_hits = foods._alias_lookup.get(key, [])
    if len(alias_hits) == 1:
        return alias_hits[0]
    if len(alias_hits) > 1:
        return False
    return None


def match_food(name: str, foods: FoodsDatabase) -> str | None:
    """
    Match an AI-identified food name to a CSV reference name.

    Strategy:
      1. Exact canonical-name match (case-insensitive, whitespace-normalised)
      2. Exact alias match (aliases split on '|')
      3. Safe normalisation variants (colour adjectives, singular/plural)
      4. Never silently choose among ambiguous aliases
      5. Never silently fuzzy-assign calories
      6. Never match vague / unspecified sauces

    Returns the matched display name, or None if unmatched / ambiguous.
    """
    if is_vague_sauce_name(name):
        return None

    variants = match_query_variants(name)
    if not variants:
        return None

    for key in variants:
        if is_vague_sauce_name(key):
            continue
        hit = _lookup_exact(key, foods)
        if hit is False:
            # Ambiguous: do not silently pick one
            return None
        if isinstance(hit, str):
            # Reject CSV rows that are themselves vague sauce placeholders
            if is_vague_sauce_name(hit):
                return None
            return hit

    return None


def suggest_foods(
    name: str,
    foods: FoodsDatabase,
    *,
    limit: int = 5,
) -> list[str]:
    """
    Conservative fuzzy suggestions for the UI.

    Never used to assign calorie values automatically.
    """
    query = normalise_food_key(name)
    if not query:
        return []

    candidates = foods.names()
    # difflib compares lowercase forms, then map back to display names
    lower_map = {normalise_food_key(n): n for n in candidates}
    close = difflib.get_close_matches(query, list(lower_map.keys()), n=limit, cutoff=0.72)
    return [lower_map[item] for item in close]


def calories_for_ingredient(grams: float, kcal_per_100g: float) -> float:
    """
    Calculate calories for one ingredient.

    Core formula:
        calories = grams * kcal_per_100g / 100

    Invalid or negative weights return 0.0.
    """
    if grams is None or grams < 0:
        return 0.0
    if kcal_per_100g is None or kcal_per_100g < 0:
        return 0.0

    return grams * kcal_per_100g / 100.0


def _merge_identical_component_rows(rows: list[dict]) -> list[dict]:
    """
    Merge rows that map to the same canonical food (or same unmatched name).

    Different preparations stay separate (Carrot, raw ≠ Carrot, cooked).
    Grams and counts are summed; kcal is recalculated from the merged mass.
    """
    merged: dict[str, dict] = {}
    order: list[str] = []

    for row in rows:
        matched = row.get("matched_food")
        if matched:
            key = f"matched::{normalise_food_key(matched)}"
        else:
            key = f"unmatched::{normalise_food_key(row.get('name') or '')}"
        if not key.endswith("::"):
            pass
        if key not in merged:
            merged[key] = dict(row)
            order.append(key)
            continue

        existing = merged[key]
        existing["grams"] = float(existing.get("grams") or 0) + float(row.get("grams") or 0)
        left_count = existing.get("count")
        right_count = row.get("count")
        if left_count is not None and right_count is not None:
            existing["count"] = float(left_count) + float(right_count)
            total_g = float(existing["grams"])
            count = float(existing["count"])
            existing["grams_per_piece"] = (total_g / count) if count else None
        else:
            existing["count"] = None
            existing["grams_per_piece"] = None

        if existing.get("matched") and existing.get("kcal_per_100g") is not None:
            kcal = calories_for_ingredient(
                float(existing["grams"]),
                float(existing["kcal_per_100g"]),
            )
            existing["kcal"] = round(kcal, 1)
            if existing.get("count") and float(existing["count"]) > 0:
                existing["kcal_per_piece"] = round(kcal / float(existing["count"]), 1)
            else:
                existing["kcal_per_piece"] = None

    return [merged[key] for key in order]


def calculate_meal_calories(
    ingredients: list[dict],
    foods: FoodsDatabase | None = None,
) -> dict:
    """
    Calculate calories for a list of ingredients.

    Each ingredient dict may contain:
        - name: food name from the AI (used only when matched_food is absent)
        - grams / estimated_grams: portion weight
        - count / grams_per_piece: optional piece fields
        - matched_food: optional manual override of the CSV food name

    Returns a dictionary with:
        - rows: per-ingredient breakdown (display name = matched CSV name when known)
        - total_kcal: sum of matched ingredient calories
        - unmatched: list of ingredient names with no CSV match
        - estimate_status: "complete" | "partial" | "incomplete"
    """
    if foods is None:
        foods = load_foods()

    rows: list[dict] = []

    for item in ingredients:
        original_name = str(item.get("name", "")).strip()
        portion = resolve_portion(item)
        grams = portion["grams"]
        count = portion["count"]
        grams_per_piece = portion["grams_per_piece"]

        # Prefer a manually chosen reference food if present
        manual_match = item.get("matched_food")
        matched: str | None = None
        if manual_match:
            candidate = str(manual_match).strip()
            if candidate and candidate in foods.by_name:
                matched = candidate
            else:
                # Allow case-insensitive manual selection
                matched = foods._canonical_lookup.get(normalise_food_key(candidate))
        else:
            matched = match_food(original_name, foods)

        # Display the CSV canonical name when matched; otherwise the VLM name
        display_name = matched if matched else original_name
        approximate = is_approximate_identification(matched)

        if matched is None:
            rows.append(
                {
                    "name": display_name,
                    "original_name": original_name,
                    "matched_food": None,
                    "grams": grams,
                    "count": count,
                    "grams_per_piece": grams_per_piece,
                    "kcal_per_100g": None,
                    "kcal": None,
                    "kcal_per_piece": None,
                    "matched": False,
                    "approximate": False,
                }
            )
            continue

        kcal_per_100g = foods.by_name[matched]
        kcal = calories_for_ingredient(grams, kcal_per_100g)
        kcal_per_piece = None
        if count is not None and count > 0:
            kcal_per_piece = round(kcal / count, 1)

        rows.append(
            {
                "name": display_name,
                "original_name": original_name,
                "matched_food": matched,
                "grams": grams,
                "count": count,
                "grams_per_piece": grams_per_piece,
                "kcal_per_100g": kcal_per_100g,
                "kcal": round(kcal, 1),
                "kcal_per_piece": kcal_per_piece,
                "matched": True,
                "approximate": approximate,
            }
        )

    rows = _merge_identical_component_rows(rows)

    unmatched: list[str] = []
    total_kcal = 0.0
    matched_count = 0
    for row in rows:
        if row.get("matched"):
            matched_count += 1
            total_kcal += float(row.get("kcal") or 0)
        else:
            unmatched.append(str(row.get("original_name") or row.get("name") or ""))

    # Honest labelling for totals
    if matched_count == 0:
        status = "incomplete"
    elif unmatched:
        status = "partial"
    else:
        status = "complete"

    return {
        "rows": rows,
        "total_kcal": round(total_kcal, 1) if matched_count else None,
        "unmatched": unmatched,
        "estimate_status": status,
        "matched_count": matched_count,
    }


# ==========================================
# STUDENT EXERCISE
# ==========================================
# Add a function that highlights high-calorie ingredients, for example:
#
# def high_calorie_ingredients(rows: list[dict], threshold: float = 200.0) -> list[dict]:
#     """Return rows whose kcal is above the threshold."""
#     result = []
#     for row in rows:
#         if (row.get("kcal") or 0) >= threshold:
#             result.append(row)
#     return result
