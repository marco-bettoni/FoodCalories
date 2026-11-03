# Product

## Register

product

## Users

Beginner Python and AI course students. They open the app in a lab or on a laptop, upload one food photograph, and need to see an estimated calorie total without configuring models, hosts or pipelines.

## Product Purpose

FoodCalories estimates calories from a photograph using a local Ollama vision model for ingredient recognition and ordinary Python for calorie math against an editable CSV. Success is a calm upload → automatic analysis → read-only personal-portion estimate that stays understandable to first-year programmers.

## Brand Personality

Quiet, precise, restrained. Feels like a careful Apple utility: clear type, generous space, one obvious action.

## Anti-references

Dashboard clutter, settings sidebars, pipeline walkthroughs, emoji-heavy teaching UIs, purple SaaS gradients, card stacks, hero-metric marketing layouts, cache or inference status badges, ingredient editors, quantity controls.

## Design Principles

1. One job per screen: identify food, show a personal-portion estimate.
2. Hide infrastructure: model, host and cache stay in config and code, not the interface.
3. Honest numbers: prefer reliable CSV math from identifiable basic food components (never dish names). Headline kcal equals the sum of displayed matched rows. Omit unmatched, vague sauces and garnishes. Never invent an “Other food (estimated)” balancing row, never invent CSV calories from AI, never silently add the AI estimate to the CSV total. When no credible matched component remains, show “Estimate unavailable”.
4. Beginner-readable code over clever abstraction.
5. Restraint over decoration: whitespace and typography carry hierarchy.

## Accessibility & Inclusion

WCAG AA contrast for body text on light surfaces. Prefer reduced motion. Keep controls native and labelled. Do not rely on colour alone for unmatched state.
