import base64
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from urllib.error import URLError

import pytest

from schoolmenu import images


@pytest.fixture(autouse=True)
def clear_photo_cache():
    images.thumbnail_bytes.cache_clear()
    yield
    images.thumbnail_bytes.cache_clear()


def test_actual_json_string_thumbnail_and_cache(monkeypatch):
    sample = (Path(__file__).parents[1] / "fixtures/thumbnail.json").read_bytes()
    fetch = Mock(side_effect=lambda *a, **k: BytesIO(sample))
    monkeypatch.setattr(images, "urlopen", fetch)
    content, mime = images.thumbnail_bytes(32008, 1)
    assert content.startswith(b"\xff\xd8\xff") and mime == "image/jpeg"
    assert len(content) > 1000
    assert images.thumbnail_bytes(32008, 1) == (content, mime)
    assert fetch.call_count == 1
    images.thumbnail_bytes(32008, 2)
    assert fetch.call_count == 2
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
    assert images.thumbnail_bytes(1, 1) is None


def test_png_and_transport_errors(monkeypatch):
    content = b"\x89PNG\r\n\x1a\n" + b"png content"
    monkeypatch.setattr(
        images,
        "urlopen",
        lambda *a, **k: BytesIO(json.dumps(base64.b64encode(content).decode()).encode()),
    )
    assert images.thumbnail_bytes(1, 1) == (content, "image/png")
    for pe_id, error in enumerate([URLError("down"), TimeoutError()], start=2):
        monkeypatch.setattr(images, "urlopen", Mock(side_effect=error))
        assert images.thumbnail_bytes(pe_id, 1) is None
