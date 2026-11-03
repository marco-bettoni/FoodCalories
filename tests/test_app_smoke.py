"""Streamlit smoke test for the refined FoodCalories UI."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

import config

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_app_loads_minimal_header():
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()

    assert not at.exception

    # Brand header rendered via markdown
    markdown_text = "\n".join(m.value for m in at.markdown)
    assert "FoodCalories" in markdown_text
    assert "Estimate calories from a photograph." in markdown_text

    # Technical UI chrome must be absent
    combined = markdown_text.lower()
    assert "settings" not in combined
    assert "ollama host" not in combined
    assert "demonstration mode" not in combined
    assert "pipeline" not in combined
    assert "from cache" not in combined

    # Analyse step removed — upload triggers analysis automatically
    button_labels = [b.label for b in at.button]
    assert "Analyse" not in button_labels


def test_app_source_is_read_only_demonstration():
    source = APP_PATH.read_text(encoding="utf-8")
    assert "bar_chart" not in source
    assert "download_button" not in source
    assert "data_editor" not in source
    assert "st.selectbox" not in source
    assert "st.number_input" not in source
    assert "At least" not in source
    assert "Other food (estimated)" not in source
    assert "Estimate unavailable" in source
    assert ">Food<" in source or "Food</th>" in source
    assert "fc-total" in source
    assert "Approx." in source
    assert "Upload or paste a food photograph" in source
    assert "webp" in source.lower()
    assert "st.selectbox" not in source
    assert "Pieces" not in source
    assert "g / piece" not in source
    assert "Analyse" not in source or "Analysing" in source
    assert "analyse_meal" in source
    assert "kcal" in source
    assert "build_display_estimate" in source
    assert 'use_cache=True' in source


def test_app_auto_analyse_on_upload_path():
    source = APP_PATH.read_text(encoding="utf-8")
    assert "needs_analysis" in source
    assert "st.button(\"Analyse\"" not in source
    assert "st.button('Analyse'" not in source


def test_app_uses_root_foods_path():
    assert config.FOODS_CSV_PATH == config.PROJECT_ROOT / "foods.csv"
