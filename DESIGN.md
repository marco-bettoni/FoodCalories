# Design System

## Visual Theme

Apple-inspired product utility. Light, quiet, editorial restraint. Mood: "morning kitchen counter — soft daylight, one olive accent, no clutter."

## Color Strategy

Restrained. Pure white surface. Olive primary reserved for focus rings and accents. Neutrals for type and hairlines. Upload browse control uses dark ink with white label.

## Colors

```css
:root {
  --bg: oklch(1.000 0.000 0);
  --surface: oklch(0.985 0.000 0);
  --ink: oklch(0.220 0.010 110);
  --muted: oklch(0.380 0.012 110);
  --line: oklch(0.820 0.005 110);
  --primary: oklch(0.420 0.090 110);
  --primary-hover: oklch(0.360 0.090 110);
  --danger: oklch(0.450 0.120 25);
  --focus: oklch(0.420 0.090 110);
  --btn-on-dark: #ffffff;
  --btn-on-primary: #ffffff;
}
```

## Typography

System UI stack (`-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif`).
Heading ~2rem / 600. Subtitle ~1.05rem / 400 muted. Metric ~clamp(2.75rem, 8vw, 5.5rem) / 600 with explicit `kcal` unit (~72–88 px on desktop). Optional muted portion weight under the metric (`Approx. N g per serving`). Body 1rem. Table 0.95rem with tabular numerals; final bold Total row.

## Layout

Max content width ~920px, centered. Generous vertical rhythm (1.5–2.5rem). Desktop: photo left (height-capped), calorie summary right; full-width component table below as proof. Narrow: single column. Uploader stays visible during and after analysis. Table: quiet header labels, hairline row rules, right-aligned amount/kcal with tabular numerals, bold Total separated by an olive primary rule; cells inset so text never touches edges. No cards.

## Components

- File uploader: native Streamlit, JPG/JPEG/PNG/WebP; browse control is dark ink with white label (never black-on-black). Supports drag-and-drop and Ctrl+V / ⌘V paste into the page. Hint: “Upload or paste a food photograph” (empty state only). Analysis starts automatically after upload or paste — no Analyse button, no editors. Uploader stays visible after results.
- Results: optional dish name (omit when null), one prominent personal-portion figure with explicit `kcal`, optional approximate serving weight from verified edible components.
- Display modes: (1) matched CSV components → `{n} kcal` + Total row (headline equals row sum); (2) no credible matched component → “Estimate unavailable”. No `Other food (estimated)`, no `At least` prefix.
- Shared dishes only: muted note with estimated serving count from the photograph.
- Read-only component table: Food | Amount | kcal. Amounts and calories are for one suggested serving. Vague sauces, unmatched rows and garnish crumbs are omitted (not shown as dashes). Dish names never appear as component rows. Integer kcal rows must sum to the headline.
- Never invent CSV calories from AI. Never invent a balancing calorie row. Never silently add the AI estimate to the CSV total. The independent AI calorie estimate is for educational comparison only and is not rendered in the student-facing UI.
- Disclaimer: one muted caption — “Photographic estimates are approximate.”

## Motion

Minimal. Streamlit defaults only. No decorative animation.
