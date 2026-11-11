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


def test_thumbnail_cache_defaults_and_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-only-settings-key")
    database = tmp_path / "schoolcafe.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(database))
    monkeypatch.delenv("THUMBNAIL_CACHE_DIR", raising=False)
    monkeypatch.delenv("THUMBNAIL_CACHE_TTL_SECONDS", raising=False)
    monkeypatch.delenv("THUMBNAIL_CACHE_MAX_BYTES", raising=False)

    defaults = runpy.run_path(str(SETTINGS))
    assert defaults["THUMBNAIL_CACHE_DIR"] == tmp_path / "thumbnail-cache"
    assert defaults["THUMBNAIL_CACHE_TTL_SECONDS"] == 2592000
    assert defaults["THUMBNAIL_CACHE_MAX_BYTES"] == 134217728

    cache_dir = tmp_path / "image-store"
    monkeypatch.setenv("THUMBNAIL_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("THUMBNAIL_CACHE_TTL_SECONDS", "60")
    monkeypatch.setenv("THUMBNAIL_CACHE_MAX_BYTES", "4096")
    configured = runpy.run_path(str(SETTINGS))
    assert configured["THUMBNAIL_CACHE_DIR"] == cache_dir
    assert configured["THUMBNAIL_CACHE_TTL_SECONDS"] == 60
    assert configured["THUMBNAIL_CACHE_MAX_BYTES"] == 4096


@pytest.mark.parametrize(
    "name,value",
    [
        ("THUMBNAIL_CACHE_TTL_SECONDS", "0"),
        ("THUMBNAIL_CACHE_TTL_SECONDS", "not-a-number"),
        ("THUMBNAIL_CACHE_MAX_BYTES", "0"),
        ("THUMBNAIL_CACHE_MAX_BYTES", "invalid"),
    ],
)
def test_thumbnail_cache_settings_must_be_positive_integers(monkeypatch, name, value):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-only-settings-key")
    monkeypatch.setenv(name, value)
    with pytest.raises(ImproperlyConfigured, match=name):
        runpy.run_path(str(SETTINGS))


def test_thumbnail_cache_directory_must_be_absolute(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-only-settings-key")
    monkeypatch.setenv("THUMBNAIL_CACHE_DIR", "relative/cache")
    with pytest.raises(ImproperlyConfigured, match="THUMBNAIL_CACHE_DIR"):
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
