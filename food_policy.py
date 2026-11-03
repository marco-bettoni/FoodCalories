"""
Shared food-name policy used by vision (post-process) and nutrition (display).

Keep these lists in one place so both modules apply the same rules.
"""

from __future__ import annotations

# Unnamed sauces must never enter matching or the calorie table.
VAGUE_SAUCE_KEYS = frozenset(
    {
        "sauce",
        "generic sauce",
        "mixed sauce",
        "unknown sauce",
        "unspecified sauce",
        "sauce unspecified",
        "sauce, unspecified",
        "dipping sauce",
        "dip sauce",
        "generic dip",
        "table dip",
        "mixed dipping sauce",
        "dipping sauce, generic",
    }
)

# Composite meal names that must never appear as CSV ingredients.
COMPOSITE_DISH_TOKENS = frozenset(
    {
        "jianbing",
        "carbonara",
        "gyro",
        "doner",
        "döner",
        "beshbarmak",
        "malatang",
        "hotpot",
        "hot pot",
        "poon choi",
        "dapanji",
        "zhajiangmian",
        "plov",
        "pilaf",
        "kung pao",
        "cheeseburger",
        "hamburger",
        "crepe",
        "crêpe",
        "pizza",
        "ramen",
        "pho",
        "biryani",
        "lasagna",
        "lasagne",
    }
)

# Basic foods that may legitimately equal dish_name (apple photo → apple).
BASIC_FOOD_ALLOWLIST = frozenset(
    {
        "apple",
        "banana",
        "orange",
        "chocolate",
        "candy",
        "cake",
        "bread",
        "egg",
        "rice",
        "pasta",
        "noodles",
        "dumpling",
        "dumplings",
        "xiaolongbao",
        "pierogi",
        "tofu",
        "fish",
        "chicken",
        "pork",
        "beef",
        "fries",
        "mayonnaise",
        "pastry",
    }
)
