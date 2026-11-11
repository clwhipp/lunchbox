import runpy
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

SETTINGS = Path(__file__).resolve().parents[2] / "schoolmenu/config/settings.py"


def test_required_secret(monkeypatch):
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        runpy.run_path(str(SETTINGS))


def test_school_must_be_supported(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-only-settings-key")
    monkeypatch.setenv("SCHOOL", "NOT_A_SCHOOL")
    with pytest.raises(ImproperlyConfigured, match="SCHOOL"):
        runpy.run_path(str(SETTINGS))


def test_grade_must_be_supported(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-only-settings-key")
    monkeypatch.setenv("GRADE", "99")
    with pytest.raises(ImproperlyConfigured, match="SUPPORTED_GRADES"):
        runpy.run_path(str(SETTINGS))


def test_calendar_public_url_and_refresh_interval_defaults_are_validated(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-only-settings-key")
    monkeypatch.setenv("CALENDAR_PUBLIC_BASE_URL", "https://menus.example.test/lunchbox/")
    monkeypatch.delenv("CALENDAR_REFRESH_INTERVAL_SECONDS", raising=False)

    configured = runpy.run_path(str(SETTINGS))

    assert configured["CALENDAR_PUBLIC_BASE_URL"] == "https://menus.example.test/lunchbox"
    assert configured["CALENDAR_REFRESH_INTERVAL_SECONDS"] == 21600


@pytest.mark.parametrize(
    "url",
    [
        "http://menus.example.test",
        "https://user:password@menus.example.test",
        "https://menus.example.test?token=bad",
        "https://menus.example.test#fragment",
    ],
)
def test_calendar_public_url_requires_https_without_credentials_or_query(monkeypatch, url):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-only-settings-key")
    monkeypatch.setenv("CALENDAR_PUBLIC_BASE_URL", url)

    with pytest.raises(ImproperlyConfigured, match="CALENDAR_PUBLIC_BASE_URL"):
        runpy.run_path(str(SETTINGS))


@pytest.mark.parametrize("interval", ["not-a-number", "59", "604801"])
def test_calendar_refresh_interval_rejects_invalid_values(monkeypatch, interval):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-only-settings-key")
    monkeypatch.setenv("CALENDAR_REFRESH_INTERVAL_SECONDS", interval)

    with pytest.raises(ImproperlyConfigured, match="CALENDAR_REFRESH_INTERVAL_SECONDS"):
        runpy.run_path(str(SETTINGS))
