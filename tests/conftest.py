import json
from datetime import date
from pathlib import Path

import pytest

from schoolmenu.provider import School
from schoolmenu.services import Selection

SAMPLES = Path(__file__).resolve().parent.parent / "docs/api_samples"


@pytest.fixture
def weekly():
    return json.loads((SAMPLES / "weekly-2026-11-09.json").read_text())


@pytest.fixture
def daily():
    return json.loads((SAMPLES / "daily-2026-11-09.json").read_text())


@pytest.fixture
def selection():
    return Selection(School.NORTHEAST_ELEMENTARY, "01", date(2026, 11, 9))


@pytest.fixture(autouse=True)
def no_accidental_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must supply an explicit transport fixture")

    monkeypatch.setattr("schoolmenu.provider.urlopen", blocked)
    monkeypatch.setattr("schoolmenu.images.urlopen", blocked)
