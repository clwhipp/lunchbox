"""Decode SchoolCafe's JSON-string thumbnails and cache bounded public images."""

import base64
import json
from functools import lru_cache
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

from .thumbnail_cache import DiskThumbnailCache, ThumbnailService

MAX_RESPONSE = 256 * 1024
MAX_IMAGE = 128 * 1024


def fetch_thumbnail(pe_id: int) -> tuple[bytes, str] | None:
    """Fetch and validate one SchoolCafe JSON/base64 thumbnail."""
    url = "https://onlineservice.primeroedge.com/SchoolCafeAPIs/api/GetThumbnailImage?"
    request = Request(
        url + urlencode({"menuItemId": pe_id}), headers={"Accept": "application/json"}
    )
    try:
        with urlopen(request, timeout=5) as response:
            raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            return None
        encoded = json.loads(raw)
        if not isinstance(encoded, str):
            return None
        content = base64.b64decode(encoded, validate=True)
        if len(content) > MAX_IMAGE:
            return None
        if content.startswith(b"\xff\xd8\xff"):
            return content, "image/jpeg"
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return content, "image/png"
    except (URLError, TimeoutError, ValueError):
        return None
    return None


@lru_cache(maxsize=256)
def thumbnail_bytes(school_id: str, pe_id: int, hour: int) -> tuple[bytes, str] | None:
    """Use the persistent scope-keyed cache, fetching from SchoolCafe on a miss."""
    del hour  # The hourly LRU key bounds positive and negative in-process results.
    cache = DiskThumbnailCache(
        Path(settings.THUMBNAIL_CACHE_DIR),
        max_image_bytes=MAX_IMAGE,
        max_cache_bytes=settings.THUMBNAIL_CACHE_MAX_BYTES,
    )
    service = ThumbnailService(
        cache,
        fetch_thumbnail,
        ttl_seconds=settings.THUMBNAIL_CACHE_TTL_SECONDS,
    )
    return service.get(school_id, pe_id)
