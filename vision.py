"""
Ollama vision-language image analysis.

This module talks to the local Ollama model.
It returns structured food identification data.
It does NOT calculate the classroom calorie total — that happens in nutrition.py.
An optional ai_calorie_estimate field is for educational comparison only.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Literal

from ollama import Client
from pydantic import BaseModel, Field, ValidationError, field_validator

import cache
import config
import images
from food_policy import BASIC_FOOD_ALLOWLIST, COMPOSITE_DISH_TOKENS, VAGUE_SAUCE_KEYS

# ==========================================
# PROMPT (documented constant — keep concise)
# ==========================================

DEFAULT_PROMPT = """
Analyse the FOOD in this photograph. Use visual evidence only, never
the filename. Return one valid JSON object, without Markdown.

TASK
Estimate the calories of the MAIN MEAL a person intends to eat.
Identify its main edible components, their approximate edible weights,
and the number of servings pictured.

FOCUS
- Focus on the primary plated, wrapped or served food.
- Ignore decorative food, ingredients arranged around a product for
  photography, background dishes, props, packaging and table decoration.
- For example, loose tomatoes beside a gyro sandwich are not necessarily
  part of the sandwich. Do not count them unless clearly included.
- Include a separate sauce or dip only when its TYPE is visually clear
  and it is clearly served for eating with the main food, such as
  mayonnaise beside French fries or yellow curry sauce with fish balls.
- Never invent vague sauce names such as "sauce", "sauce, unspecified",
  "generic sauce" or "unknown sauce". If the sauce type cannot be
  recognised, omit the sauce entirely.
- Ignore negligible herbs, spices and garnishes.
- Include calorie-significant foods, coatings, fillings and sauces.
- Do not list the same edible component twice. Merge overlapping pieces
  of the same food into one ingredient with a combined edible weight.
- Do not invent balancing ingredients to force agreement with the
  independent calorie estimate.

PREPARATION
- Decide raw vs cooked from the meal context, not from habit.
- Vegetables served as crudités, salad or a dip platter (hummus with
  carrot, radish, tomato, cucumber, pepper) are normally raw.
- Vegetables incorporated into a stir-fry, braise, curry or sweet-and-
  sour sauce are normally cooked.
- Fried foods (fried chicken, French fries, youtiao) should be named
  as fried when visually supported.
- Include the preparation in the ingredient name when it matters,
  for example "raw carrot", "cooked bell pepper", "raw onion".
- If preparation genuinely cannot be determined, do not invent one;
  use a plain name only when raw vs cooked is unimportant for that food.

DISH AND COMPONENTS
- dish_name is the recognised complete dish, or null when uncertain.
  Prefer null over inventing a precise name. A correct generic name
  is better than an invented specific name.
- Prefer dish_name "Siu mai" when open-topped steamed pork dumplings
  in a bamboo steamer are recognisable. List components as "dumpling"
  with piece count and average weight — do not invent wrapper/filling
  splits for finished dumplings.
- Curry fish balls: list fish balls and visible curry sauce as
  separate components. Estimate sauce weight realistically for the
  bowl (often about 40–120 g for one snack serving).
- ingredients must contain basic edible FOOD COMPONENTS, never the
  complete dish name.
- Example: "jianbing" is a dish name, not a nutritional component.
  Its identifiable components may include a cooked wheat wrapper,
  egg, crispy fried cracker and a specific sauce when visible.
- Example: a burger may contain one burger bun, one patty, cheese
  and substantial condiments.
- Use concise English names appropriate for a generic food database.
- Preserve important differences: beef vs pork, raw vs cooked fish,
  fried vs plain chicken, rice noodles vs wheat noodles.
- When meat species cannot be identified, use "unspecified meat".
- Do not invent invisible fillings or exact recipes.
- Do not decompose finished foods into hypothetical raw flour,
  sugar, water, milk or butter.
- For an indivisible food that cannot be decomposed reliably,
  report only components genuinely identifiable; the independent
  AI calorie estimate must still cover the complete food.

WEIGHTS AND PIECES
- Estimate edible cooked weight for ONE person's portion of what is
  pictured, excluding bones, shells and packaging.
- Use realistic amounts for one ordinary meal. Avoid implausibly
  large single-person fish, meat or sauce quantities.
- A sandwich with two bread halves usually contains ONE bun or pita.
  Do not count the halves as two complete breads.
- Count pieces only for independently edible objects such as
  dumplings, chocolates, candies, buns or separate fried pieces.
- Do not count chopped vegetables, tomato slices, rice grains,
  noodles or sauces as separate food portions.
- Large trays may legitimately contain many chocolates.
  Estimate count and average grams per piece without arbitrary limits.
- grams must equal count × grams_per_piece when both are provided.
- Avoid double-counting: a fried food's nutritional value may already
  include absorbed oil; do not add the same oil again.
- Do not count wrappers and fillings separately when a finished
  dumpling, bun or similar unit is pictured whole.

SERVINGS
- A single burger, sandwich, wrap, crepe, bowl or personal plate
  normally represents ONE serving.
- A visibly shared family platter, large communal dish, hotpot or
  whole shared fish may represent several servings.
- suggested_servings refers to the entire photographed meal.
- All ingredient grams and ai_calorie_estimate refer to the entire
  photographed meal, BEFORE division by suggested_servings.
- Never infer multiple servings merely because a sandwich contains
  several ingredients or a bun is cut into pieces.

CALORIES
- Provide an independent, approximate ai_calorie_estimate in kcal
  for the ENTIRE main meal, including substantial components that
  cannot be identified individually.
- This estimate must not be calculated from foods.csv.
- Do not add the independent AI estimate to component calories.
- Do not invent ingredients solely to match the AI calorie estimate.
- Do not underestimate a whole meal merely because only vegetables
  or garnishes could be identified.
- If food is visible but its composition is uncertain, preserve a
  reasonable whole-meal estimate rather than inventing ingredients.

RETURN THESE JSON FIELDS
dish_name: string or null
dish_confidence: high, medium, low or null
is_family_sized: boolean
suggested_servings: number, minimum 1
ai_calorie_estimate: number or null
ingredients: array of objects with
  name: concise English component name
  grams: estimated edible grams
  count: number or null
  grams_per_piece: number or null

Return no explanations. Never use the filename.
""".strip()

# Sample payload for offline unit tests (not shown in the UI)
DEMO_MEAL_RESULT: dict[str, Any] = {
    "dish_name": "Chicken rice bowl",
    "dish_confidence": "medium",
    "is_family_sized": False,
    "suggested_servings": 1,
    "ai_calorie_estimate": 520,
    "ingredients": [
        {"name": "chicken breast", "grams": 150},
        {"name": "rice", "grams": 180},
        {"name": "broccoli", "grams": 80},
    ],
}

DishConfidence = Literal["high", "medium", "low"]

# Synonym groups used to merge duplicate component rows after parsing.
_DUPLICATE_NAME_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"shrimp", "prawn", "prawns", "shrimps"}),
    frozenset({"cilantro", "coriander", "coriander leaves", "fresh coriander", "fresh cilantro"}),
    frozenset({"scallion", "scallions", "green onion", "green onions", "spring onion", "spring onions"}),
)

# Soft edible-mass caps (grams). Over-cap values are reduced and flagged.
_DEFAULT_MASS_CAP_G = 1200.0
_FAMILY_MASS_CAP_G = 2500.0

# Exact names the small VLM often invents as raw recipe components — drop them.
_RECIPE_HALLUCINATION_NAMES = frozenset(
    {
        "flour",
        "wheat flour",
        "rice flour",
        "glutinous rice flour",
        "sugar",
        "white sugar",
        "brown sugar",
        "butter",
        "water",
        "salt",
        "pepper",
        "black pepper",
        "baking powder",
        "baking soda",
        "flavoring",
        "flavouring",
        "vanilla",
        "vanilla extract",
        "yeast",
    }
)

# Shared policy sets (re-exported under historical private names).
_VAGUE_SAUCE_NAMES = VAGUE_SAUCE_KEYS
_COMPOSITE_DISH_TOKENS = COMPOSITE_DISH_TOKENS
_BASIC_FOOD_ALLOWLIST = BASIC_FOOD_ALLOWLIST


def _is_vague_sauce_name(name: str) -> bool:
    """Return True for unnamed sauces the model invents without visual type."""
    key = " ".join(str(name or "").strip().lower().split())
    if not key:
        return False
    if key in VAGUE_SAUCE_KEYS:
        return True
    if key.startswith("sauce,") or key.startswith("sauce "):
        remainder = key.split(",", 1)[-1].strip() if "," in key else key[6:].strip()
        if remainder in {"", "unspecified", "generic", "unknown", "mixed"}:
            return True
    return False


def _prefer_siu_mai_dish_name(
    dish_name: str | None,
    items: list[dict[str, Any]],
) -> str | None:
    """
    Prefer dish_name "Siu mai" when dumplings look like open-topped shumai.

    Nutritional rows stay generic ("dumpling"); only the display title changes.
    Never overwrite a clear Xiaolongbao / soup-dumpling identification.
    """
    current = (dish_name or "").strip()
    current_key = current.lower()
    if any(
        token in current_key
        for token in ("xiaolongbao", "xiao long bao", "soup dumpling", "汤包")
    ):
        return current or None

    names = [
        " ".join(str(item.get("name") or "").strip().lower().split()) for item in items
    ]
    if any(
        "xiaolongbao" in name or "soup dumpling" in name for name in names if name
    ):
        return current or None

    if current_key in {"siu mai", "shumai", "steamed siu mai", "pork siu mai"}:
        return "Siu mai"

    has_siu_mai_token = any(
        "siu mai" in name or name == "shumai" or name.endswith(" shumai")
        for name in names
        if name
    )
    if has_siu_mai_token:
        return "Siu mai"

    return dish_name if current else None

# Soft tokens: edible alone (egg, milk) but recipe noise when paired with flour/sugar.
_SOFT_RECIPE_TOKENS = frozenset(
    {
        "milk",
        "egg",
        "eggs",
    }
)

# Hard recipe markers — when two or more hard names appear, treat as recipe invention.
_HARD_RECIPE_TOKENS = frozenset(
    {
        "flour",
        "wheat flour",
        "rice flour",
        "glutinous rice flour",
        "sugar",
        "white sugar",
        "butter",
        "water",
        "flavoring",
        "flavouring",
        "baking powder",
        "baking soda",
        "yeast",
        "vanilla",
        "vanilla extract",
    }
)

# Kept for older tests / documentation of the former cluster set.
_RECIPE_CLUSTER_TOKENS = _HARD_RECIPE_TOKENS | _SOFT_RECIPE_TOKENS

_WHOLE_DUMPLING_TOKENS = (
    "dumpling",
    "dumplings",
    "jiaozi",
    "gyoza",
    "potsticker",
    "potstickers",
    "pierogi",
    "siu mai",
    "shumai",
    "xiaolongbao",
    "soup dumpling",
)

_WRAPPER_TOKENS = (
    "dumpling wrapper",
    "dumpling skin",
    "dumpling dough",
    "pastry wrapper",
    "wonton wrapper",
    "jiaozi wrapper",
    "gyoza skin",
)

_FILLING_TOKENS = (
    "filling",
    "meat filling",
    "dumpling filling",
    "minced meat",
    "ground meat",
)


# ==========================================
# PYDANTIC SCHEMA (structured output)
# ==========================================


class Ingredient(BaseModel):
    """One food item identified in the image."""

    name: str = Field(..., min_length=1)
    grams: float = Field(..., ge=0)
    # Optional piece fields for countable foods (apples, chocolates, buns)
    count: float | None = None
    grams_per_piece: float | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Ingredient name cannot be empty")
        return cleaned

    @field_validator("grams", mode="before")
    @classmethod
    def coerce_grams(cls, value: Any) -> float:
        try:
            grams = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("grams must be a number") from exc
        if grams < 0:
            raise ValueError("grams cannot be negative")
        return grams

    @field_validator("count", mode="before")
    @classmethod
    def coerce_count(cls, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            count = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("count must be a number") from exc
        if count <= 0:
            return None
        return count

    @field_validator("grams_per_piece", mode="before")
    @classmethod
    def coerce_grams_per_piece(cls, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            grams = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("grams_per_piece must be a number") from exc
        if grams < 0:
            raise ValueError("grams_per_piece cannot be negative")
        return grams


class MealAnalysis(BaseModel):
    """Full structured response expected from the vision model."""

    dish_name: str | None = None
    dish_confidence: DishConfidence | None = None
    is_family_sized: bool = False
    suggested_servings: float = 1.0
    ai_calorie_estimate: float | None = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    # Filled by Python post-validation when portions look implausible
    warnings: list[str] = Field(default_factory=list)

    @field_validator("dish_name", mode="before")
    @classmethod
    def normalise_dish_name(cls, value: Any) -> str | None:
        # Prefer null over placeholder labels such as "Unknown dish"
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.lower() in {"unknown", "unknown dish", "n/a", "none", "null"}:
            return None
        return text

    @field_validator("dish_confidence", mode="before")
    @classmethod
    def normalise_dish_confidence(cls, value: Any) -> str | None:
        if value is None or value == "":
            return None
        # Some models return a probability instead of high/medium/low
        if isinstance(value, (int, float)):
            score = float(value)
            if score >= 0.8:
                return "high"
            if score >= 0.5:
                return "medium"
            if score > 0:
                return "low"
            return None
        text = str(value).strip().lower()
        if text in {"high", "medium", "low"}:
            return text
        return None

    @field_validator("is_family_sized", mode="before")
    @classmethod
    def coerce_family_sized(cls, value: Any) -> bool:
        if value is None or value == "":
            return False
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y"}:
            return True
        if text in {"0", "false", "no", "n"}:
            return False
        return bool(value)

    @field_validator("suggested_servings", mode="before")
    @classmethod
    def coerce_servings(cls, value: Any) -> float:
        if value is None or value == "":
            return 1.0
        try:
            servings = float(value)
        except (TypeError, ValueError):
            return 1.0
        if servings < 1:
            return 1.0
        # Cap absurd model outputs for classroom safety
        if servings > 20:
            return 20.0
        return servings

    @field_validator("ai_calorie_estimate", mode="before")
    @classmethod
    def coerce_ai_kcal(cls, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            kcal = float(value)
        except (TypeError, ValueError):
            return None
        if kcal < 0:
            return None
        return kcal


# ==========================================
# VALIDATION HELPERS
# ==========================================


def _duplicate_group_key(name: str) -> str:
    """Map synonym ingredient names onto one merge key."""
    key = name.strip().lower()
    for group in _DUPLICATE_NAME_GROUPS:
        if key in group:
            return sorted(group)[0]
    return key


def _merge_duplicate_ingredients(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merge obvious duplicate components (e.g. shrimp + prawns).

    Keeps the first display name; sums grams and counts when present.
    """
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        # Keep blank names so Pydantic can reject them later
        if not name:
            order_key = f"__empty_{len(order)}"
            merged[order_key] = dict(item)
            order.append(order_key)
            continue
        group = _duplicate_group_key(name)
        if group not in merged:
            merged[group] = {
                "name": name,
                "grams": float(item.get("grams") or 0),
                "count": item.get("count"),
                "grams_per_piece": item.get("grams_per_piece"),
            }
            order.append(group)
            continue

        existing = merged[group]
        existing["grams"] = float(existing.get("grams") or 0) + float(item.get("grams") or 0)
        # Prefer keeping piece fields only when both sides have them
        left_count = existing.get("count")
        right_count = item.get("count")
        if left_count is not None and right_count is not None:
            existing["count"] = float(left_count) + float(right_count)
            total = float(existing["grams"])
            count = float(existing["count"])
            existing["grams_per_piece"] = (total / count) if count else None
        else:
            existing["count"] = None
            existing["grams_per_piece"] = None

    return [merged[key] for key in order]


def _strip_piece_fields_for_bulk_foods(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Clear misleading count=1 fields on bulk masses and non-piece foods.

    Countable finished items (dumplings, buns, cakes, chocolates…) keep pieces.
    """
    piece_tokens = (
        "cake",
        "ball",
        "dumpling",
        "pierogi",
        "bun",
        "roll",
        "cracker",
        "chocolate",
        "candy",
        "sweet",
        "tart",
        "puff",
        "cookie",
        "biscuit",
        "apple",
        "banana",
        "egg",
        "siu mai",
        "shumai",
        "xiaolongbao",
    )
    cleaned: list[dict[str, Any]] = []
    for item in items:
        entry = dict(item)
        name = str(entry.get("name") or "").lower()
        is_piece_food = any(token in name for token in piece_tokens)
        count = entry.get("count")
        # count of 1 on a non-piece food is almost always a model artefact
        if count is not None and float(count) <= 1 and not is_piece_food:
            entry["count"] = None
            entry["grams_per_piece"] = None
        cleaned.append(entry)
    return cleaned


def _reconcile_piece_fields(item: dict[str, Any]) -> dict[str, Any]:
    """
    Keep count, grams_per_piece and grams internally consistent.

    Prefer count × grams_per_piece when both piece fields are present.
    """
    entry = dict(item)
    try:
        count = float(entry["count"]) if entry.get("count") is not None else None
    except (TypeError, ValueError):
        count = None
    try:
        gpp = (
            float(entry["grams_per_piece"])
            if entry.get("grams_per_piece") is not None
            else None
        )
    except (TypeError, ValueError):
        gpp = None
    try:
        grams = float(entry["grams"]) if entry.get("grams") is not None else None
    except (TypeError, ValueError):
        grams = None

    if count is not None and count <= 0:
        count = None
    if gpp is not None and gpp < 0:
        gpp = None

    if count is not None and gpp is not None:
        grams = count * gpp
    elif count is not None and grams is not None and grams >= 0 and gpp is None and count > 0:
        gpp = grams / count

    entry["count"] = count
    entry["grams_per_piece"] = gpp
    if grams is not None:
        entry["grams"] = grams
    return entry


def _mass_cap_for_name(name: str, *, family_sized: bool) -> float:
    """Return a soft edible-mass cap for one ingredient name."""
    key = name.strip().lower()
    # Exact or near-exact caps first (avoid substring traps like "sesame seed bun")
    exact_caps = {
        "sea urchin": 80.0,
        "sea urchin roe": 80.0,
        "uni": 80.0,
        "abalone": 200.0,
        "sea cucumber": 250.0,
        "oil": 40.0,
        "sesame oil": 40.0,
        "chilli oil": 40.0,
        "chili oil": 40.0,
        "honey": 40.0,
        "sesame": 25.0,
        "sesame seed": 25.0,
        "sesame seeds": 25.0,
        "sauce": 80.0,
        "soy sauce": 80.0,
        "oyster sauce": 80.0,
        "curry sauce": 120.0,
        "fish ball curry sauce": 120.0,
        "sweet and sour sauce": 100.0,
        "mayonnaise": 40.0,
        "mayo": 40.0,
        "fish balls": 250.0,
        "fish ball": 250.0,
    }
    if key in exact_caps:
        return exact_caps[key]
    # Phrase endings: "light soy sauce", "toasted sesame oil"
    for phrase, cap in exact_caps.items():
        if key.endswith(" " + phrase):
            return cap
    return _FAMILY_MASS_CAP_G if family_sized else _DEFAULT_MASS_CAP_G


def _looks_like_wrapper(name: str) -> bool:
    key = name.strip().lower()
    return any(token in key for token in _WRAPPER_TOKENS)


def _looks_like_filling(name: str) -> bool:
    key = name.strip().lower()
    return any(token in key for token in _FILLING_TOKENS)


def _looks_like_whole_dumpling(name: str) -> bool:
    key = name.strip().lower()
    if _looks_like_wrapper(key) or _looks_like_filling(key):
        return False
    return any(token in key for token in _WHOLE_DUMPLING_TOKENS)


def _collapse_dumpling_parts(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Merge wrapper + filling rows into one whole dumpling unit.

    Avoids double-counting when the small VLM invents a recipe split.
    """
    warnings: list[str] = []
    wrappers: list[dict[str, Any]] = []
    fillings: list[dict[str, Any]] = []
    wholes: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if _looks_like_wrapper(name):
            wrappers.append(item)
        elif _looks_like_filling(name):
            fillings.append(item)
        elif _looks_like_whole_dumpling(name):
            wholes.append(item)
        else:
            others.append(item)

    if not wrappers and not fillings:
        return items, warnings

    # Prefer an existing whole-dumpling name; otherwise synthesise "dumpling"
    if wholes:
        base = dict(wholes[0])
        extras = wholes[1:]
    else:
        total_grams = sum(float(x.get("grams") or 0) for x in wrappers + fillings)
        total_count = 0.0
        for x in wrappers + fillings:
            try:
                if x.get("count") is not None:
                    total_count += float(x["count"])
            except (TypeError, ValueError):
                pass
        # Wrapper and filling often both list the same piece count — take max
        counts = []
        for x in wrappers + fillings:
            try:
                if x.get("count") is not None:
                    counts.append(float(x["count"]))
            except (TypeError, ValueError):
                pass
        count = max(counts) if counts else None
        gpp = (total_grams / count) if count and count > 0 else None
        base = {
            "name": "dumpling",
            "grams": total_grams if total_grams > 0 else 0,
            "count": count,
            "grams_per_piece": gpp,
        }
        extras = []
        warnings.append(
            "Merged dumpling wrapper/filling into a whole dumpling unit"
        )

    # If wholes already exist, drop wrapper/filling to avoid double-count
    if wholes:
        warnings.append(
            "Dropped dumpling wrapper/filling rows to avoid double-counting"
        )
        return others + [base] + extras, warnings

    return others + [base] + extras, warnings


def _looks_like_finished_food(name: str) -> bool:
    """Return True when a name looks like a finished edible item."""
    key = name.strip().lower()
    finished_tokens = (
        "cake",
        "pastry",
        "tart",
        "puff",
        "bun",
        "dumpling",
        "mooncake",
        "cookie",
        "biscuit",
        "candy",
        "chocolate",
        "sweet",
        "pudding",
        "mochi",
        "ball",
        "wrapper",
        "cracker",
        "pancake",
        "apple",
        "banana",
        "fries",
        "mayonnaise",
        "mayo",
        "ketchup",
        "patty",
        "egg",
        "bread",
        "pita",
        "flatbread",
    )
    return any(token in key for token in finished_tokens)


def _names_refer_to_same_dish(component: str, dish_name: str | None) -> bool:
    """
    Return True when a component name is clearly the same complete dish.

    Basic single foods (apple, chocolate) may equal dish_name.
    Composite meal names must never become CSV ingredients.
    """
    dish = (dish_name or "").strip().lower()
    name = (component or "").strip().lower()
    if not dish or not name:
        return False

    stop = {"the", "a", "an", "and", "with", "of", "prepared", "cooked"}
    dish_tokens = [t for t in dish.replace(",", " ").split() if t not in stop]
    name_tokens = [t for t in name.replace(",", " ").split() if t not in stop]
    joined_dish = " ".join(dish_tokens)
    joined_name = " ".join(name_tokens)

    # Distinctive composite dish token present in both
    for token in COMPOSITE_DISH_TOKENS:
        if token in name and token in dish:
            return True

    if joined_name != joined_dish and name != dish:
        return False

    # Exact match: allow basic foods, reject everything else as a dish label
    if joined_name in BASIC_FOOD_ALLOWLIST or name in BASIC_FOOD_ALLOWLIST:
        return False
    return True


def _drop_dish_named_components(
    items: list[dict[str, Any]],
    *,
    dish_name: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Remove ingredient rows that merely repeat the dish name."""
    warnings: list[str] = []
    kept: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if _names_refer_to_same_dish(name, dish_name):
            warnings.append(
                f"Rejected dish-name component '{name}' (not a basic food)"
            )
            continue
        kept.append(item)
    return kept, warnings


def _merge_sandwich_bread_halves(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Collapse two near-identical bread/pita rows into one sandwich unit.

    A cut bun or pita is still one bread, not two complete breads.
    """
    warnings: list[str] = []
    bread_tokens = (
        "pita",
        "burger bun",
        "hamburger bun",
        "sesame bun",
        "bread bun",
        "flatbread",
        "wrap bread",
        "lavash",
    )

    def is_bread(name: str) -> bool:
        key = name.strip().lower()
        if key in {"bread", "bun", "pita", "pita bread"}:
            return True
        return any(token in key for token in bread_tokens)

    breads: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if is_bread(name):
            breads.append(dict(item))
        else:
            others.append(item)

    if len(breads) < 2:
        return items, warnings

    # Two similar ~50–120 g breads → one bun/pita
    try:
        weights = [float(b.get("grams") or 0) for b in breads]
    except (TypeError, ValueError):
        return items, warnings
    if len(breads) == 2 and all(40 <= w <= 140 for w in weights):
        primary = breads[0]
        # Prefer the heavier half as the single-bread mass (typical whole pita)
        primary["grams"] = max(weights)
        primary["count"] = None
        primary["grams_per_piece"] = None
        warnings.append(
            "Merged sandwich bread halves into one bun/pita portion"
        )
        return others + [primary], warnings

    return items, warnings


def _salvage_finished_from_dish(
    dish_name: str | None,
) -> dict[str, Any] | None:
    """
    Build one BASIC food component from a dish hint when filtering wiped all rows.

    Never salvages the complete dish name as an ingredient.
    """
    dish = (dish_name or "").strip().lower()
    if not dish:
        return None
    # Ordered: more specific phrases first — components only, never dish names
    salvage_rules: tuple[tuple[tuple[str, ...], str, float], ...] = (
        (("jianbing", "chinese savoury crepe", "savory crepe"), "wheat wrapper", 120.0),
        (("crepe", "crêpe", "thin pancake"), "wheat wrapper", 100.0),
        (("cream puff", "chou"), "cream puff", 80.0),
        (("dumpling", "jiaozi", "gyoza", "xiaolongbao", "siu mai"), "dumpling", 250.0),
        (("pastries", "pastry", "tart", "egg tart", "sesame ball"), "pastry", 80.0),
        (("cake", "gateau", "gâteau"), "cake", 400.0),
        (("chocolate",), "chocolate", 200.0),
        (("candy", "sweet", "sweets"), "candy", 60.0),
        (("apple",), "apple", 180.0),
        (("banana",), "banana", 120.0),
        (("fries", "french fry", "chips"), "french fries", 150.0),
        (("burger", "hamburger"), "burger bun", 80.0),
        (("gyro", "doner", "döner", "kebab"), "pita bread", 100.0),
    )
    for tokens, food_name, grams in salvage_rules:
        if any(token in dish for token in tokens):
            return {
                "name": food_name,
                "grams": grams,
                "count": 1.0 if food_name in {"apple", "banana", "cream puff"} else None,
                "grams_per_piece": grams
                if food_name in {"apple", "banana", "cream puff"}
                else None,
            }
    return None


def _drop_recipe_cluster(
    items: list[dict[str, Any]],
    *,
    dish_name: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Drop raw-recipe clusters without wiping legitimate finished foods.

    Hard recipe names (flour, sugar, butter…) are always dropped.
    Soft names (egg, milk) stay unless they appear beside hard recipe rows.
    When filtering would leave nothing, salvage one finished food from dish_name.
    """
    warnings: list[str] = []
    hard_rows: list[dict[str, Any]] = []
    soft_rows: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        if name in _RECIPE_HALLUCINATION_NAMES or name in _HARD_RECIPE_TOKENS:
            hard_rows.append(item)
            continue
        if name in _SOFT_RECIPE_TOKENS:
            soft_rows.append(item)
            continue
        kept.append(item)

    has_finished = any(
        _looks_like_finished_food(str(item.get("name") or "")) for item in kept
    )
    # Recipe invention: hard markers present → drop hard (+ soft when no finished food)
    drop_soft = bool(hard_rows) and (has_finished or bool(kept) or len(hard_rows) >= 2)

    if hard_rows:
        for item in hard_rows:
            name = str(item.get("name") or "ingredient")
            warnings.append(f"Ignored uncertain recipe ingredient: {name}")

    if drop_soft:
        for item in soft_rows:
            name = str(item.get("name") or "ingredient")
            warnings.append(f"Ignored uncertain recipe ingredient: {name}")
        soft_rows = []

    result = kept + soft_rows

    if not result:
        salvage = _salvage_finished_from_dish(dish_name)
        if salvage is not None:
            warnings.append(
                f"Salvaged finished food '{salvage['name']}' after recipe-cluster drop"
            )
            return [salvage], warnings
        if hard_rows or soft_rows:
            warnings.append(
                "Ignored unfinished recipe-style ingredients without a finished food"
            )
        return [], warnings

    return result, warnings


def _fix_chocolate_piece_counts(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Expand implausible single-piece chocolate masses into tray-style counts.

    Small VLMs often return count=1 with hundreds of grams for assortments.
    Typical tray pieces are about 5–10 g.
    """
    warnings: list[str] = []
    fixed: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        name = str(entry.get("name") or "").strip().lower()
        is_chocolate = "chocolate" in name or name in {"candy", "chocolates"}
        try:
            grams = float(entry.get("grams") or 0)
        except (TypeError, ValueError):
            grams = 0.0
        try:
            count = float(entry["count"]) if entry.get("count") is not None else None
        except (TypeError, ValueError):
            count = None
        if is_chocolate and grams >= 80 and (count is None or count <= 1):
            gpp = 8.0
            new_count = max(1.0, round(grams / gpp))
            entry["count"] = new_count
            entry["grams_per_piece"] = gpp
            entry["grams"] = new_count * gpp
            warnings.append(
                f"Adjusted chocolate/candy piece count to {new_count:g} × {gpp:.0f} g"
            )
        fixed.append(entry)
    return fixed, warnings


def _correct_honey_mislabelled_cake(
    items: list[dict[str, Any]],
    *,
    dish_name: str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Small VLMs often label cake glaze/crumb as honey.

    When the dish looks like cake and honey appears without cake, rename
    that honey row to cake (same mass). Does not invent new rows.
    """
    warnings: list[str] = []
    dish = (dish_name or "").strip().lower()
    cake_hint = "cake" in dish or "gateau" in dish
    names = [str(item.get("name") or "").strip().lower() for item in items]
    has_cake = any("cake" in name for name in names)
    has_honey = any(name == "honey" or name.endswith(" honey") for name in names)
    has_fruit = any(
        token in " ".join(names)
        for token in ("strawberry", "blueberry", "raspberry", "fruit")
    )
    if has_cake or not has_honey:
        return items, warnings
    if not (cake_hint or has_fruit):
        return items, warnings

    corrected: list[dict[str, Any]] = []
    for item in items:
        entry = dict(item)
        name = str(entry.get("name") or "").strip().lower()
        if name == "honey" or name.endswith(" honey"):
            entry["name"] = "cake"
            warnings.append(
                "Corrected honey label to cake for a cake-like photograph"
            )
        corrected.append(entry)
    return corrected, warnings


def _apply_portion_sanity(
    items: list[dict[str, Any]],
    *,
    family_sized: bool,
    dish_name: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Conservative checks for implausible masses and inconsistent pieces.

    Caps absurd edible weights and records warnings. Does not invent foods.
    """
    warnings: list[str] = []

    without_dish, dish_warnings = _drop_dish_named_components(
        items,
        dish_name=dish_name,
    )
    warnings.extend(dish_warnings)
    bread_merged, bread_warnings = _merge_sandwich_bread_halves(without_dish)
    warnings.extend(bread_warnings)
    collapsed, dump_warnings = _collapse_dumpling_parts(bread_merged)
    warnings.extend(dump_warnings)
    clustered, cluster_warnings = _drop_recipe_cluster(
        collapsed,
        dish_name=dish_name,
    )
    warnings.extend(cluster_warnings)
    cake_fixed, cake_warnings = _correct_honey_mislabelled_cake(
        clustered,
        dish_name=dish_name,
    )
    warnings.extend(cake_warnings)
    chocolate_fixed, chocolate_warnings = _fix_chocolate_piece_counts(cake_fixed)
    warnings.extend(chocolate_warnings)

    cleaned: list[dict[str, Any]] = []

    for item in chocolate_fixed:
        if not isinstance(item, dict):
            continue
        entry = _reconcile_piece_fields(item)
        name = str(entry.get("name") or "").strip() or "food"
        name_key = name.lower()

        # Drop invented recipe components; keep finished foods (cake, pastry…)
        if name_key in _RECIPE_HALLUCINATION_NAMES:
            warnings.append(
                f"Ignored uncertain recipe ingredient: {name}"
            )
            continue

        # Drop vague sauces — never invent calories for "sauce, unspecified"
        if _is_vague_sauce_name(name):
            warnings.append(
                f"Ignored vague sauce label: {name}"
            )
            continue

        # Normalise siu mai component rows to generic dumpling for CSV reuse
        if name_key in {
            "siu mai",
            "shumai",
            "steamed shumai",
            "pork siu mai",
            "siu mai dumpling",
        }:
            entry["name"] = "dumpling"
            warnings.append(
                "Normalised siu mai component to dumpling for CSV matching"
            )
            name = "dumpling"
            name_key = "dumpling"

        grams = float(entry.get("grams") or 0)
        cap = _mass_cap_for_name(name, family_sized=family_sized)

        if grams <= 0:
            continue

        if grams > cap:
            warnings.append(
                f"Uncertain portion for {name}: "
                f"model estimated {grams:.0f} g; capped at {cap:.0f} g"
            )
            # Preserve piece fields proportionally when present
            count = entry.get("count")
            if count is not None and float(count) > 0:
                entry["grams_per_piece"] = cap / float(count)
            entry["grams"] = cap

        cleaned.append(entry)

    # Last resort: if every row was dropped, salvage from the dish name
    if not cleaned:
        salvage = _salvage_finished_from_dish(dish_name)
        if salvage is not None:
            warnings.append(
                f"Salvaged finished food '{salvage['name']}' after empty post-process"
            )
            cleaned = [salvage]

    return cleaned, warnings


def _normalise_raw_payload(data: Any) -> Any:
    """
    Accept a small amount of legacy field naming so old fixtures can migrate.

    Converts estimated_grams → grams and keeps optional piece fields.
    """
    if not isinstance(data, dict):
        return data

    family_sized = bool(data.get("is_family_sized", False))
    # Unknown extra keys (e.g. legacy allergens/spiciness) are dropped here
    # so old cached JSON still validates against the current schema.
    cleaned: dict[str, Any] = {
        "dish_name": data.get("dish_name"),
        "dish_confidence": data.get("dish_confidence"),
        "is_family_sized": family_sized,
        "suggested_servings": data.get("suggested_servings", 1),
        "ai_calorie_estimate": data.get(
            "ai_calorie_estimate",
            data.get("ai_total_kcal"),
        ),
        "ingredients": [],
        "warnings": list(data.get("warnings") or []),
    }

    raw_ingredients = data.get("ingredients") or []
    if not isinstance(raw_ingredients, list):
        return data

    for item in raw_ingredients:
        if not isinstance(item, dict):
            cleaned["ingredients"].append(item)
            continue
        grams = item.get("grams", item.get("estimated_grams"))
        entry: dict[str, Any] = {
            "name": item.get("name"),
            "grams": grams,
        }
        if "count" in item:
            entry["count"] = item.get("count")
        if "grams_per_piece" in item:
            entry["grams_per_piece"] = item.get("grams_per_piece")
        cleaned["ingredients"].append(entry)

    cleaned["ingredients"] = _strip_piece_fields_for_bulk_foods(cleaned["ingredients"])
    cleaned["ingredients"] = _merge_duplicate_ingredients(cleaned["ingredients"])
    return cleaned


def validate_meal_result(data: Any) -> dict:
    """
    Validate raw model output and return a plain dictionary.

    Raises ValueError if the data cannot be coerced into MealAnalysis.
    Empty or malformed payloads raise ValueError (callers handle gracefully).
    """
    if data is None:
        raise ValueError("Invalid model output: empty response")
    if isinstance(data, str) and not data.strip():
        raise ValueError("Invalid model output: empty response")

    try:
        meal = MealAnalysis.model_validate(_normalise_raw_payload(data))
    except ValidationError as exc:
        raise ValueError(f"Invalid model output: {exc}") from exc

    # Soft portion checks run after schema validation (flags, does not invent foods)
    payload = meal.model_dump()
    sane_items, portion_warnings = _apply_portion_sanity(
        payload["ingredients"],
        family_sized=bool(payload.get("is_family_sized")),
        dish_name=payload.get("dish_name"),
    )
    payload["ingredients"] = sane_items
    preferred_dish = _prefer_siu_mai_dish_name(payload.get("dish_name"), sane_items)
    if preferred_dish:
        payload["dish_name"] = preferred_dish
    payload["warnings"] = list(payload.get("warnings") or []) + portion_warnings
    return payload


def _salvage_truncated_json(text: str) -> Any:
    """
    Best-effort repair when a long model reply cuts off mid-string.

    Keeps classroom runs usable on busy photographs without inventing fields.
    """
    start = text.find("{")
    if start < 0:
        raise ValueError("Model response did not contain a JSON object")
    snippet = text[start:]

    # Trim to the last complete ingredient object if the array was cut off
    ingredients_key = snippet.find('"ingredients"')
    if ingredients_key >= 0:
        array_start = snippet.find("[", ingredients_key)
        if array_start >= 0:
            last_complete = snippet.rfind("}")
            if last_complete > array_start:
                head = snippet[: last_complete + 1]
                # Close the ingredients array and the root object if needed
                if head.count("[") > head.count("]"):
                    head += "]"
                if head.count("{") > head.count("}"):
                    head += "}"
                try:
                    return json.loads(head)
                except json.JSONDecodeError:
                    pass

    # Progressive close of braces / brackets
    candidate = snippet.rstrip().rstrip(",")
    for closer in ("]}", "}", "]}", "\"]}"):
        try:
            return json.loads(candidate + closer)
        except json.JSONDecodeError:
            continue
    raise ValueError("Could not salvage truncated JSON from model response")


def _extract_json_object(text: str) -> Any:
    """
    Parse JSON from a model reply.

    Some models wrap JSON in markdown fences; strip those first.
    Truncated replies are salvaged when possible.
    """
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Model returned an empty response")

    # Conditional: remove markdown code fences if present
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        # Drop first fence line and optional trailing fence
        if len(lines) >= 2:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return _salvage_truncated_json(cleaned)


# ==========================================
# OLLAMA CALL
# ==========================================


def check_ollama_available(host: str | None = None) -> tuple[bool, str]:
    """
    Check whether the Ollama HTTP service is reachable.

    This probes ``GET {host}/api/tags``. It does **not** check whether the
    configured vision model is installed — use ``model_is_installed()`` for that.

    Args:
        host: Optional Ollama base URL. When omitted, uses ``config.OLLAMA_HOST``
            (already normalised, e.g. ``http://localhost:11434``).

    Returns:
        ``(True, message)`` when the service answers HTTP 200.
        ``(False, message)`` when the host is unreachable, times out, or
        returns a non-200 status. The message is safe to show to beginners.

    Expected failures:
        - Ollama not running → connection refused / URL error
        - Wrong host or port → connection error or timeout (5 seconds)
        - HTTP error from the service → non-200 status message
    """
    base = (host or config.OLLAMA_HOST).rstrip("/")
    url = f"{base}/api/tags"

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status == 200:
                return True, "Ollama service is reachable"
            return False, f"Ollama returned HTTP {response.status}"
    except urllib.error.URLError as exc:
        # Covers refused connections, DNS failures, and request timeouts.
        return False, f"Cannot reach Ollama at {base}: {exc.reason}"
    except Exception as exc:  # noqa: BLE001 - educational surface area
        return False, f"Ollama check failed: {exc}"


def list_local_models(host: str | None = None) -> list[str]:
    """Return names of models currently installed in Ollama."""
    base = (host or config.OLLAMA_HOST).rstrip("/")
    url = f"{base}/api/tags"

    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    names: list[str] = []
    for item in payload.get("models", []):
        name = item.get("name") or item.get("model")
        if name:
            names.append(name)
    return names


def model_is_installed(model_name: str | None = None, host: str | None = None) -> bool:
    """Return True if the configured (or given) model appears in ollama list."""
    target = (model_name or config.OLLAMA_MODEL).strip()
    try:
        installed = list_local_models(host=host)
    except Exception:  # noqa: BLE001
        return False

    # Exact name match, or same base name before the tag
    target_base = target.split(":")[0]
    for name in installed:
        if name == target:
            return True
        if name.split(":")[0] == target_base and (
            ":" not in target or name.startswith(target)
        ):
            return True
    return False


def _prepare_image_bytes(
    image_bytes: bytes,
    max_side: int | None = None,
) -> bytes:
    """Downscale / normalise image bytes before sending them to Ollama."""
    side = int(max_side) if max_side is not None else int(config.IMAGE_MAX_SIDE)
    try:
        return images.prepare_image_bytes(image_bytes, max_side=side)
    except ValueError:
        # If Pillow cannot decode the bytes, send them unchanged
        return image_bytes


# ---------------------------------------------------------------------------
# How FoodCalories talks to Ollama (teaching notes for beginners / Cline)
# ---------------------------------------------------------------------------
# Client comes from the ``ollama`` Python package (see requirements.txt).
# host     → which machine/port runs the Ollama service (config.OLLAMA_HOST)
# model    → which installed vision-language model to use (config.OLLAMA_MODEL)
# messages → the conversation sent to the model; here one user turn
# role     → "user" marks this message as the human/application input
# content  → the text prompt describing the task
# images   → a list of photograph payloads as raw image bytes
# format   → "json" asks Ollama for a JSON-formatted answer
# stream   → False waits for the full reply (no token chunks)
# options  → inference settings such as temperature and context size
# response.message.content → the model's text (JSON string, sometimes already
#                            parsed by the SDK into a dict)
# json.loads / _extract_json_object → turn JSON text into Python objects
# validate_meal_result → schema check; valid JSON can still be the wrong shape
#
# Minimal copyable example (EXAMPLE ONLY — not production config):
#
#   from ollama import Client
#   import json
#
#   # Example setup (replace with your own host/model/image path)
#   example_host = "http://localhost:11434"
#   example_model = "qwen3-vl:4b-instruct"
#   example_prompt = "List the main foods in this photo as JSON."
#   with open("samples/verify/apple.jpg", "rb") as image_file:
#       example_image_bytes = image_file.read()
#
#   client = Client(host=example_host)
#   response = client.chat(
#       model=example_model,
#       messages=[
#           {
#               "role": "user",
#               "content": example_prompt,
#               "images": [example_image_bytes],
#           }
#       ],
#       format="json",
#       stream=False,
#       options={"temperature": 0.2, "num_ctx": 4096},
#   )
#   content = response.message.content
#   data = content if isinstance(content, dict) else json.loads(str(content))
#   # data is now a Python dict; still validate it against your schema.
#
# Production behaviour lives in ``_call_ollama_vision`` below (host, model,
# preprocessing, options, and MealAnalysis validation come from this project).
# ---------------------------------------------------------------------------


def _call_ollama_vision(
    image_bytes: bytes,
    prompt: str,
    *,
    max_side: int | None = None,
) -> dict:
    """
    Send a food photograph and prompt to Ollama; return a validated meal dict.

    Steps (in order):
      1. Receive ``image_bytes`` and ``prompt``.
      2. Preprocess/resize the image when required (``_prepare_image_bytes``).
      3. Create an Ollama ``Client`` for ``config.OLLAMA_HOST``.
      4. Call ``client.chat`` with the vision model, prompt and image bytes.
      5. Request structured JSON via ``format="json"`` (``stream=False``).
      6. Read ``response.message.content``.
      7. Parse JSON text into a Python object when needed.
      8. Validate with ``validate_meal_result`` (schema may still reject it).
      9. Return the validated dictionary, or raise ``ValueError`` on bad output.

    Configuration (host, model, temperature, num_ctx, image size) comes from
    ``config.py``. Callers such as ``analyse_meal`` handle retries and cache.
    """
    # 1–2. Prepare image bytes for the model (downscale / JPEG normalise).
    prepared = _prepare_image_bytes(image_bytes, max_side=max_side)

    # 3. Client aimed at the configured Ollama service.
    client = Client(host=config.OLLAMA_HOST)

    # 4–5. One user message: text prompt + photograph bytes; ask for JSON.
    response = client.chat(
        model=config.OLLAMA_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
                "images": [prepared],
            }
        ],
        format="json",
        stream=False,
        options={
            "temperature": config.OLLAMA_TEMPERATURE,
            "num_ctx": config.OLLAMA_NUM_CTX,
        },
    )

    # 6. Model text lives on the chat response message.
    content = response.message.content
    if not content:
        raise ValueError("Model returned an empty response")

    # 7. SDK may already return a dict; otherwise parse JSON text.
    if isinstance(content, dict):
        raw = content
    else:
        raw = _extract_json_object(str(content))

    # 8–9. Schema validation; propagate ValueError to callers.
    return validate_meal_result(raw)


def _usable_ingredients(payload: dict) -> bool:
    """True when at least one ingredient has a positive edible mass."""
    for item in payload.get("ingredients") or []:
        try:
            if float(item.get("grams") or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _recognition_looks_incomplete(payload: dict) -> bool:
    """
    Heuristic: empty components, or a tiny CSV-like mass with a large AI guess.

    Used only to decide whether to retry at a higher image resolution.
    """
    if not _usable_ingredients(payload):
        return True
    ai = payload.get("ai_calorie_estimate")
    try:
        ai_kcal = float(ai) if ai is not None else None
    except (TypeError, ValueError):
        ai_kcal = None
    total_grams = 0.0
    for item in payload.get("ingredients") or []:
        try:
            total_grams += float(item.get("grams") or 0)
        except (TypeError, ValueError):
            continue
    # Very little mass identified while AI claims a full meal
    if ai_kcal is not None and ai_kcal >= 250 and total_grams < 40:
        return True
    return False


def analyse_meal(
    image_bytes: bytes,
    *,
    use_cache: bool = True,
    prompt: str | None = None,
    demo_mode: bool = False,
    max_side: int | None = None,
) -> dict:
    """
    Identify foods and estimated portions in an image.

    Arguments:
        image_bytes: raw bytes of a JPG/PNG/WebP photograph
        use_cache: reuse a previous result when True
        prompt: optional custom prompt (defaults to DEFAULT_PROMPT)
        demo_mode: return DEMO_MEAL_RESULT without calling Ollama (tests only)
        max_side: longest image side sent to Ollama (default: config.IMAGE_MAX_SIDE)

    Returns:
        A dictionary with dish fields and ingredients, plus meta:
        from_cache, demo_mode, cache_key, image_max_side.
    """
    active_prompt = prompt if prompt is not None else DEFAULT_PROMPT
    side = int(max_side) if max_side is not None else int(config.IMAGE_MAX_SIDE)

    # Demonstration path for automated tests only
    if demo_mode:
        result = validate_meal_result(DEMO_MEAL_RESULT)
        result["from_cache"] = False
        result["demo_mode"] = True
        result["cache_key"] = None
        result["image_max_side"] = side
        return result

    # Build the cache key from image + model + versions + resolution
    cache_key = cache.build_cache_key(image_bytes, image_max_side=side)

    # Conditional: try the cache first
    if use_cache:
        cached = cache.load_cached_result(cache_key)
        if cached is not None:
            # Re-validate cached JSON before trusting it
            try:
                result = validate_meal_result(cached)
            except ValueError:
                result = None
            if result is not None:
                result["from_cache"] = True
                result["demo_mode"] = False
                result["cache_key"] = cache_key
                result["image_max_side"] = side
                return result

    # Check that Ollama is reachable before calling the model
    ok, message = check_ollama_available()
    if not ok:
        raise RuntimeError(
            f"AI service unavailable. {message}. "
            "Start Ollama and try again."
        )

    if not model_is_installed():
        raise RuntimeError(
            f"Model '{config.OLLAMA_MODEL}' is not installed. "
            f"Run: ollama pull {config.OLLAMA_MODEL}"
        )

    def _run_once(*, resolve_side: int) -> dict:
        return _call_ollama_vision(image_bytes, active_prompt, max_side=resolve_side)

    # Primary recognition call. On malformed JSON or no usable ingredients,
    # retry once with the same canonical prompt at the same resolution.
    # Custom prompts skip retries so callers keep full control.
    first_error: Exception | None = None
    result: dict | None = None
    try:
        result = _run_once(resolve_side=side)
    except (ValueError, json.JSONDecodeError) as err:
        if prompt is not None:
            raise
        first_error = err

    if prompt is None and (result is None or not _usable_ingredients(result)):
        try:
            retry = _run_once(resolve_side=side)
        except (ValueError, json.JSONDecodeError):
            retry = None
        if retry is not None and (result is None or _usable_ingredients(retry)):
            result = retry

    if result is None:
        if first_error is not None:
            raise first_error
        raise RuntimeError("Recognition failed without a usable model response.")

    # Incomplete recognition → one higher-resolution retry with the same prompt
    fallback_side = int(config.IMAGE_FALLBACK_MAX_SIDE)
    if (
        prompt is None
        and _recognition_looks_incomplete(result)
        and fallback_side > side
    ):
        try:
            hi_res = _run_once(resolve_side=fallback_side)
        except (ValueError, json.JSONDecodeError):
            hi_res = None
        if hi_res is not None and (
            _usable_ingredients(hi_res)
            and not _recognition_looks_incomplete(hi_res)
        ):
            result = hi_res
            side = fallback_side
            cache_key = cache.build_cache_key(image_bytes, image_max_side=side)

    # Save validated results. Empty ingredient lists are still valid JSON,
    # but skipping the cache keeps a later Analyse free to try again.
    if _usable_ingredients(result):
        cache.save_cached_result(cache_key, result)

    result["from_cache"] = False
    result["demo_mode"] = False
    result["cache_key"] = cache_key
    result["image_max_side"] = side
    return result


# Extension points for new recognition fields:
# 1) DEFAULT_PROMPT — ask the model for extra JSON keys (single canonical prompt)
# 2) MealAnalysis — validate those keys
# 3) app.py — render them in the read-only results UI
# After prompt or schema changes, bump config.PROMPT_VERSION / SCHEMA_VERSION.
