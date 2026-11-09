"""Decode SchoolCafe's JSON-string thumbnails and cache bounded public images."""

import base64
import json
from functools import lru_cache
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MAX_RESPONSE = 256 * 1024
MAX_IMAGE = 128 * 1024


@lru_cache(maxsize=256)
def thumbnail_bytes(pe_id: int, hour: int) -> tuple[bytes, str] | None:
    """The hour key expires both positive and negative entries without a worker."""
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
