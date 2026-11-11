"""Persistent thumbnail storage and cache-first image source orchestration."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ImagePayload = tuple[bytes, str]
ImageFetcher = Callable[[int], ImagePayload | None]


@dataclass(frozen=True)
class CachedThumbnail:
    content: bytes
    content_type: str
    stored_at: float


class DiskThumbnailCache:
    """Store validated images in a bounded, content-safe local directory."""

    def __init__(self, root: Path, *, max_image_bytes: int, max_cache_bytes: int):
        if max_image_bytes <= 0 or max_cache_bytes <= 0:
            raise ValueError("Thumbnail cache size limits must be positive")
        self.root = Path(root)
        self.max_image_bytes = max_image_bytes
        self.max_cache_bytes = max_cache_bytes

    @staticmethod
    def _content_type(content: bytes) -> str | None:
        if content.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        return None

    def accepts(self, image: ImagePayload) -> bool:
        content, content_type = image
        return len(content) <= self.max_image_bytes and self._content_type(content) == content_type

    @staticmethod
    def _discard(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def _path(self, school_id: str, pe_id: int) -> Path:
        identity = f"schoolcafe.thumbnail.v1\0{school_id}\0{pe_id}".encode()
        digest = hashlib.sha256(identity).hexdigest()
        return self.root / digest[:2] / f"{digest}.img"

    def get(self, school_id: str, pe_id: int) -> CachedThumbnail | None:
        path = self._path(school_id, pe_id)
        try:
            stat = path.stat()
            if stat.st_size > self.max_image_bytes:
                self._discard(path)
                return None
            content = path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError:
            return None
        if len(content) > self.max_image_bytes:
            self._discard(path)
            return None
        content_type = self._content_type(content)
        if content_type is None:
            self._discard(path)
            return None
        return CachedThumbnail(content, content_type, stat.st_mtime)

    def put(self, school_id: str, pe_id: int, image: ImagePayload) -> bool:
        content, content_type = image
        if not self.accepts(image) or len(content) > self.max_cache_bytes:
            return False

        path = self._path(school_id, pe_id)
        temporary_path: str | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".thumbnail-", dir=path.parent, delete=False
            ) as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = temporary.name
            os.replace(temporary_path, path)
            temporary_path = None
        except OSError:
            return False
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
        self.prune()
        return True

    def prune(self) -> None:
        """Evict least-recently-written files until the configured bound is met."""
        files = []
        try:
            for path in self.root.rglob("*.img"):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                files.append((stat.st_mtime, path, stat.st_size))
        except OSError:
            return
        total_bytes = sum(size for _, _, size in files)
        if total_bytes <= self.max_cache_bytes:
            return
        for _stored_at, path, size in sorted(files, key=lambda item: (item[0], str(item[1]))):
            try:
                path.unlink()
                total_bytes -= size
            except OSError:
                continue
            if total_bytes <= self.max_cache_bytes:
                break


class ThumbnailService:
    """Return fresh disk images first; fetch, validate, and persist on misses."""

    def __init__(
        self,
        cache: DiskThumbnailCache,
        fetch_image: ImageFetcher,
        *,
        ttl_seconds: int,
    ):
        if ttl_seconds <= 0:
            raise ValueError("Thumbnail cache TTL must be positive")
        self.cache = cache
        self.fetch_image = fetch_image
        self.ttl_seconds = ttl_seconds

    def get(self, school_id: str, pe_id: int, *, now: float | None = None) -> ImagePayload | None:
        current_time = time.time() if now is None else now
        cached = self.cache.get(school_id, pe_id)
        if cached is not None and current_time - cached.stored_at <= self.ttl_seconds:
            return cached.content, cached.content_type

        try:
            refreshed = self.fetch_image(pe_id)
        except (OSError, TimeoutError):
            refreshed = None
        if refreshed is not None and self.cache.accepts(refreshed):
            self.cache.put(school_id, pe_id, refreshed)
            return refreshed
        if cached is not None:
            return cached.content, cached.content_type
        return None
