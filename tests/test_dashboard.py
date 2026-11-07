"""Smoke test: the dashboard script runs end to end without raising, on the committed serving data."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
DATA = APP.parent / "data"


@pytest.mark.skipif(not (DATA / "metrics.json").exists(), reason="run `p2p all` first")
def test_dashboard_renders_without_exceptions():
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception, [e.message for e in at.exception]
    assert len(at.tabs) == 9


@pytest.mark.skipif(not (DATA / "metrics.json").exists(), reason="run `p2p all` first")
def test_dashboard_controls_update_cleanly():
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    at.selectbox[0].set_value("three_way_after_gr").run()
    at.slider[1].set_value(25).run()
    assert not at.exception, [e.message for e in at.exception]
