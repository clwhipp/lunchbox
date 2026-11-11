import base64
import json
import os
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from urllib.error import URLError

import pytest
from django.test import override_settings

from schoolmenu import images


@pytest.fixture(autouse=True)
def clear_photo_cache(tmp_path):
    with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
        images.thumbnail_bytes.cache_clear()
        yield
        images.thumbnail_bytes.cache_clear()


def test_actual_json_string_thumbnail_and_cache(monkeypatch):
    sample = (Path(__file__).parents[1] / "fixtures/thumbnail.json").read_bytes()
    fetch = Mock(side_effect=lambda *a, **k: BytesIO(sample))
    monkeypatch.setattr(images, "urlopen", fetch)
    content, mime = images.thumbnail_bytes("northeast", 32008, 1)
    assert content.startswith(b"\xff\xd8\xff") and mime == "image/jpeg"
    assert len(content) > 1000
    assert images.thumbnail_bytes("northeast", 32008, 1) == (content, mime)
    assert fetch.call_count == 1
    images.thumbnail_bytes("northeast", 32008, 2)
    assert fetch.call_count == 1
    request = fetch.call_args.args[0]
    assert request.full_url.endswith("?menuItemId=32008")
    assert request.get_header("Accept") == "application/json"


@pytest.mark.parametrize(
    "data",
    [
        b"not-json",
        b"{}",
        b'"not-base64!"',
        b'""',
        json.dumps(base64.b64encode(b"<svg>untrusted</svg>").decode()).encode(),
        b'"' + b"A" * (images.MAX_RESPONSE + 1) + b'"',
        json.dumps(base64.b64encode(b"\xff\xd8\xff" + b"a" * images.MAX_IMAGE).decode()).encode(),
    ],
)
def test_invalid_oversized_or_active_images_are_rejected(monkeypatch, data):
    monkeypatch.setattr(images, "urlopen", lambda *a, **k: BytesIO(data))
    assert images.thumbnail_bytes("northeast", 1, 1) is None


def test_png_and_transport_errors(monkeypatch):
    content = b"\x89PNG\r\n\x1a\n" + b"png content"
    monkeypatch.setattr(
        images,
        "urlopen",
        lambda *a, **k: BytesIO(json.dumps(base64.b64encode(content).decode()).encode()),
    )
    assert images.thumbnail_bytes("northeast", 1, 1) == (content, "image/png")
    for pe_id, error in enumerate([URLError("down"), TimeoutError()], start=2):
        monkeypatch.setattr(images, "urlopen", Mock(side_effect=error))
        assert images.thumbnail_bytes("northeast", pe_id, 1) is None


def test_disk_cache_survives_memory_cache_clear(monkeypatch, tmp_path):
    sample = (Path(__file__).parents[1] / "fixtures/thumbnail.json").read_bytes()
    fetch = Mock(side_effect=[BytesIO(sample), AssertionError("fresh disk hit must not fetch")])
    monkeypatch.setattr(images, "urlopen", fetch)

    with override_settings(
        THUMBNAIL_CACHE_DIR=tmp_path,
        THUMBNAIL_CACHE_TTL_SECONDS=30 * 24 * 60 * 60,
        THUMBNAIL_CACHE_MAX_BYTES=1024 * 1024,
    ):
        first = images.thumbnail_bytes("northeast", 32008, 1)
        images.thumbnail_bytes.cache_clear()
        second = images.thumbnail_bytes("northeast", 32008, 2)

    assert first == second
    assert len(list(tmp_path.rglob("*.img"))) == 1
    assert fetch.call_count == 1


def test_disk_cache_is_scoped_by_school(monkeypatch, tmp_path):
    first_image = b"\xff\xd8\xffschool-one"
    second_image = b"\x89PNG\r\n\x1a\nschool-two"
    fetch = Mock(
        side_effect=[
            BytesIO(json.dumps(base64.b64encode(first_image).decode()).encode()),
            BytesIO(json.dumps(base64.b64encode(second_image).decode()).encode()),
        ]
    )
    monkeypatch.setattr(images, "urlopen", fetch)

    with override_settings(
        THUMBNAIL_CACHE_DIR=tmp_path,
        THUMBNAIL_CACHE_TTL_SECONDS=30 * 24 * 60 * 60,
        THUMBNAIL_CACHE_MAX_BYTES=1024 * 1024,
    ):
        first = images.thumbnail_bytes("school-one", 32008, 1)
        second = images.thumbnail_bytes("school-two", 32008, 1)

    assert first == (first_image, "image/jpeg")
    assert second == (second_image, "image/png")
    assert fetch.call_count == 2
    assert len(list(tmp_path.rglob("*.img"))) == 2
    assert all("32008" not in path.name for path in tmp_path.rglob("*.img"))


def test_disk_cache_prunes_oldest_files_to_a_bounded_size(monkeypatch, tmp_path):
    responses = [
        BytesIO(
            json.dumps(base64.b64encode(b"\xff\xd8\xff" + bytes([index]) * 9).decode()).encode()
        )
        for index in range(3)
    ]
    monkeypatch.setattr(images, "urlopen", Mock(side_effect=responses))

    with override_settings(
        THUMBNAIL_CACHE_DIR=tmp_path,
        THUMBNAIL_CACHE_TTL_SECONDS=30 * 24 * 60 * 60,
        THUMBNAIL_CACHE_MAX_BYTES=24,
    ):
        cached_files = []
        for pe_id, stored_at in zip((1, 2, 3), (100, 200, 300), strict=True):
            assert images.thumbnail_bytes("northeast", pe_id, 1) is not None
            created = set(tmp_path.rglob("*.img")) - set(cached_files)
            assert len(created) == 1
            cache_file = created.pop()
            os.utime(cache_file, (stored_at, stored_at))
            cached_files.append(cache_file)

    assert not cached_files[0].exists()
    assert cached_files[1].exists() and cached_files[2].exists()
    assert sum(path.stat().st_size for path in tmp_path.rglob("*.img")) <= 24


def test_stale_disk_image_is_refreshed_and_served_stale_on_fetch_failure(monkeypatch, tmp_path):
    old_image = b"\xff\xd8\xffold-image"
    new_image = b"\x89PNG\r\n\x1a\nnew-image"
    old_response = json.dumps(base64.b64encode(old_image).decode()).encode()
    new_response = json.dumps(base64.b64encode(new_image).decode()).encode()
    fetch = Mock(side_effect=[BytesIO(old_response), BytesIO(new_response), URLError("offline")])
    monkeypatch.setattr(images, "urlopen", fetch)

    with override_settings(
        THUMBNAIL_CACHE_DIR=tmp_path,
        THUMBNAIL_CACHE_TTL_SECONDS=60,
        THUMBNAIL_CACHE_MAX_BYTES=1024 * 1024,
    ):
        assert images.thumbnail_bytes("northeast", 1, 1) == (old_image, "image/jpeg")
        cache_file = next(tmp_path.rglob("*.img"))
        old_time = cache_file.stat().st_mtime - 120
        os.utime(cache_file, (old_time, old_time))

        images.thumbnail_bytes.cache_clear()
        refreshed = images.thumbnail_bytes("northeast", 1, 2)
        assert fetch.call_count == 2
        assert refreshed == (new_image, "image/png")
        cache_file = next(tmp_path.rglob("*.img"))
        old_time = cache_file.stat().st_mtime - 120
        os.utime(cache_file, (old_time, old_time))

        images.thumbnail_bytes.cache_clear()
        assert images.thumbnail_bytes("northeast", 1, 3) == (new_image, "image/png")

    assert fetch.call_count == 3


@pytest.mark.parametrize("corrupt_content", [b"not-an-image", b"x" * (images.MAX_IMAGE + 1)])
def test_corrupt_disk_cache_is_replaced(monkeypatch, tmp_path, corrupt_content):
    image = b"\xff\xd8\xffvalid-image"
    response = json.dumps(base64.b64encode(image).decode()).encode()
    fetch = Mock(side_effect=[BytesIO(response), BytesIO(response)])
    monkeypatch.setattr(images, "urlopen", fetch)

    with override_settings(
        THUMBNAIL_CACHE_DIR=tmp_path,
        THUMBNAIL_CACHE_TTL_SECONDS=30 * 24 * 60 * 60,
        THUMBNAIL_CACHE_MAX_BYTES=1024 * 1024,
    ):
        assert images.thumbnail_bytes("northeast", 1, 1) == (image, "image/jpeg")
        next(tmp_path.rglob("*.img")).write_bytes(corrupt_content)
        images.thumbnail_bytes.cache_clear()
        assert images.thumbnail_bytes("northeast", 1, 2) == (image, "image/jpeg")

    assert fetch.call_count == 2


def test_cache_storage_failure_does_not_discard_fetched_image(monkeypatch, tmp_path):
    sample = (Path(__file__).parents[1] / "fixtures/thumbnail.json").read_bytes()
    cache_dir = tmp_path / "not-a-directory"
    cache_dir.write_text("occupied")
    monkeypatch.setattr(images, "urlopen", lambda *a, **k: BytesIO(sample))

    with override_settings(
        THUMBNAIL_CACHE_DIR=cache_dir,
        THUMBNAIL_CACHE_TTL_SECONDS=30 * 24 * 60 * 60,
        THUMBNAIL_CACHE_MAX_BYTES=1024 * 1024,
    ):
        assert images.thumbnail_bytes("northeast", 32008, 1) is not None

    assert cache_dir.is_file()


def test_invalid_injected_image_source_is_not_served(monkeypatch, tmp_path):
    monkeypatch.setattr(images, "fetch_thumbnail", lambda pe_id: (b"<svg>", "image/svg+xml"))

    with override_settings(
        THUMBNAIL_CACHE_DIR=tmp_path,
        THUMBNAIL_CACHE_TTL_SECONDS=30 * 24 * 60 * 60,
        THUMBNAIL_CACHE_MAX_BYTES=1024 * 1024,
    ):
        assert images.thumbnail_bytes("northeast", 1, 1) is None
