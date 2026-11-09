import runpy
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

SETTINGS = Path(__file__).resolve().parents[2] / "schoolmenu/config/settings.py"


def test_required_secret(monkeypatch):
    monkeypatch.delenv("DJANGO_SECRET_KEY")
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        runpy.run_path(str(SETTINGS))


def test_grade_must_be_supported(monkeypatch):
    monkeypatch.setenv("GRADE", "99")
    with pytest.raises(ImproperlyConfigured, match="SUPPORTED_GRADES"):
        runpy.run_path(str(SETTINGS))
