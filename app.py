"""
FoodCalories — Streamlit demonstration interface.

Architecture reminder for students:
  vision.py     -> identifies foods (AI)
  nutrition.py  -> calculates calories (Python)
  app.py        -> displays a read-only personal-portion estimate
"""

from __future__ import annotations

import html
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import nutrition
import vision

_ASSETS = Path(__file__).resolve().parent / "assets"


def _load_asset(name: str) -> str:
    """Read a text asset next to the application."""
    return (_ASSETS / name).read_text(encoding="utf-8")


# ==========================================
# 1. PAGE SETTINGS AND LIGHT STYLING
# ==========================================

st.set_page_config(
    page_title="FoodCalories",
    page_icon="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'/>",
    layout="centered",
)

# Beginners: CSS only restyles Streamlit; it does not change app logic.
st.markdown(f"<style>\n{_load_asset('app.css')}\n</style>", unsafe_allow_html=True)

st.markdown(
    """
<div class="fc-header">
  <h1 class="fc-brand">FoodCalories</h1>
  <p class="fc-tagline">Estimate calories from a photograph.</p>
</div>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 2. LOAD NUTRITION DATA
# ==========================================

try:
    foods = nutrition.load_foods()
except FileNotFoundError as exc:
    st.error(str(exc))
    st.stop()

# Keep analysis results in session state so Streamlit reruns
# do not trigger another model call for the same photograph.
if "analysis" not in st.session_state:
    st.session_state["analysis"] = None
if "image_bytes" not in st.session_state:
    st.session_state["image_bytes"] = None
if "image_name" not in st.session_state:
    st.session_state["image_name"] = None

# ==========================================
# 3. UPLOAD / PASTE → AUTO-ANALYSE
# ==========================================

uploaded = st.file_uploader(
    "Photograph",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=False,
    label_visibility="collapsed",
)

# Clipboard paste: listen on the parent page and feed Streamlit's file input.
components.html(
    f"<script>\n{_load_asset('clipboard_paste.js')}\n</script>",
    height=0,
)

needs_analysis = False
if uploaded is not None:
    new_bytes = uploaded.getvalue()
    # New photograph clears a previous analysis so totals cannot drift
    if new_bytes != st.session_state.get("image_bytes"):
        st.session_state["analysis"] = None
        needs_analysis = True
    st.session_state["image_bytes"] = new_bytes
    st.session_state["image_name"] = uploaded.name

has_photo = st.session_state["image_bytes"] is not None

# Distill: show the paste hint only before a photograph exists
if not has_photo:
    st.markdown(
        '<p class="fc-paste-hint">Upload or paste a food photograph</p>',
        unsafe_allow_html=True,
    )

# Auto-run inference once per new photograph
if has_photo and (needs_analysis or st.session_state.get("analysis") is None):
    with st.spinner("Analysing…"):
        try:
            result = vision.analyse_meal(
                st.session_state["image_bytes"],
                use_cache=True,
            )
            st.session_state["analysis"] = result
        except Exception as exc:  # noqa: BLE001 - classroom-friendly message
            st.session_state["analysis"] = None
            st.error(str(exc))
            if has_photo:
                st.image(st.session_state["image_bytes"], width="stretch")
            st.stop()

analysis = st.session_state.get("analysis")

if not has_photo or analysis is None:
    st.stop()

# ==========================================
# 4. READ-ONLY RESULTS
# ==========================================

# Hidden teaching fields remain on analysis; never rendered here.

display = nutrition.build_display_estimate(analysis, foods)
dish_name = display["dish_name"]
servings = display["servings"]
show_serving_count = display["show_serving_count"]
portion_kcal = display["portion_kcal"]
portion_grams = display.get("portion_grams")
estimate_ready = display["estimate_ready"]
total_label = display.get("total_label") or "Total"
components_rows = display["components"]

photo_col, summary_col = st.columns([1.05, 1], gap="large")

with photo_col:
    st.image(
        st.session_state["image_bytes"],
        width="stretch",
    )

with summary_col:
    if dish_name:
        safe_dish = html.escape(str(dish_name))
        st.markdown(f'<p class="fc-dish">{safe_dish}</p>', unsafe_allow_html=True)

    if estimate_ready and portion_kcal is not None:
        st.markdown(
            f'<p class="fc-kcal">{portion_kcal:.0f} kcal</p>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<p class="fc-portion-weight">Estimate unavailable</p>',
            unsafe_allow_html=True,
        )

    if estimate_ready and portion_grams is not None and portion_grams > 0:
        st.markdown(
            f'<p class="fc-portion-weight">'
            f"Approx. {portion_grams:.0f} g per serving"
            f"</p>",
            unsafe_allow_html=True,
        )

    if estimate_ready and portion_kcal is not None and show_serving_count:
        st.markdown(
            f'<p class="fc-serving-note">'
            f"Shared dish · about {servings:g} servings in the photograph"
            f"</p>",
            unsafe_allow_html=True,
        )


def _component_row_html(row: dict) -> str:
    """Build one ingredient table row with escaped food names."""
    amount = nutrition.format_amount(row)
    kcal_value = int(row.get("kcal_display", round(float(row.get("kcal") or 0))))
    safe_name = html.escape(str(row["name"]))
    return (
        "<tr>"
        f"<td>{safe_name}</td>"
        f'<td class="fc-amount">{html.escape(amount)}</td>'
        f'<td class="fc-kcal-cell">{kcal_value}</td>'
        "</tr>"
    )


# Full-width component proof under the photo | summary composition
if components_rows:
    rows_html = []
    total_grams = 0.0
    for row in components_rows:
        rows_html.append(_component_row_html(row))
        if "grams_display" in row:
            total_grams += float(row.get("grams_display") or 0)
        else:
            total_grams += float(row.get("grams") or 0)

    # Row kcal values already absorb rounding drift in nutrition.build_display_estimate
    if portion_kcal is not None:
        total_kcal_text = f"{int(round(float(portion_kcal)))}"
    else:
        total_kcal_rows = sum(
            int(row.get("kcal_display", round(float(row.get("kcal") or 0))))
            for row in components_rows
        )
        total_kcal_text = f"{total_kcal_rows}"

    if portion_grams is not None and portion_grams > 0:
        total_amount = f"{portion_grams:.0f} g"
    elif total_grams > 0:
        total_amount = (
            f"{total_grams:.0f} g"
            if total_grams >= 10
            else f"{total_grams:.1f} g"
        )
    else:
        total_amount = ""

    rows_html.append(
        '<tr class="fc-total">'
        f"<td>{html.escape(str(total_label))}</td>"
        f'<td class="fc-amount">{html.escape(total_amount)}</td>'
        f'<td class="fc-kcal-cell">{total_kcal_text}</td>'
        "</tr>"
    )
    table_html = (
        '<div class="fc-table-wrap">'
        '<table class="fc-table" role="table">'
        "<thead><tr>"
        '<th scope="col">Food</th>'
        '<th scope="col">Amount</th>'
        '<th scope="col">kcal</th>'
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
        "</div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)

st.markdown(
    '<p class="fc-note">Photographic estimates are approximate.</p>',
    unsafe_allow_html=True,
)

# Results rendering ends here. New analysis fields from vision.analyse_meal
# can be shown above this note without changing calorie math in nutrition.py.
