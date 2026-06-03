from __future__ import annotations

import hashlib
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from core.db import PROJECT_ROOT


DEFAULT_AVATAR_CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "avatar_cache"
AVATAR_ASSET_PREFIX = "/assets/avatar_cache"
MAX_AVATAR_BYTES = 3 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 8

_IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
}


@dataclass(frozen=True)
class AvatarCacheResult:
    local_path: str
    error: str = ""


def avatar_public_url(local_path: str) -> str:
    if not local_path:
        return ""
    if local_path.startswith(("http://", "https://")):
        return local_path
    path = Path(local_path)
    try:
        relative = path.resolve().relative_to(DEFAULT_AVATAR_CACHE_DIR.resolve())
    except ValueError:
        try:
            relative = path.resolve().relative_to(PROJECT_ROOT.resolve())
        except ValueError:
            relative = path
        if relative.parts[:3] == ("data", "processed", "avatar_cache"):
            relative = Path(*relative.parts[3:])
    return f"{AVATAR_ASSET_PREFIX}/{relative.as_posix()}"


def cache_avatar_url(
    avatar_url: str,
    platform: str,
    cache_dir: Path = DEFAULT_AVATAR_CACHE_DIR,
    force: bool = False,
) -> AvatarCacheResult:
    url = avatar_url.strip()
    if not url:
        return AvatarCacheResult(local_path="")
    platform_dir = _platform_cache_dir(platform, cache_dir)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return AvatarCacheResult(local_path="", error="unsupported avatar URL scheme")

    platform_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    cached = _existing_cached_file(platform_dir, digest)
    if cached is not None and not force:
        return AvatarCacheResult(local_path=str(cached))

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "OSGE-avatar-cache/1.0",
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif,*/*;q=0.5",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get_content_type()
            extension = _image_extension(url, content_type)
            if extension is None:
                return AvatarCacheResult(local_path="", error=f"unsupported content type: {content_type}")
            payload = _read_limited(response)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return AvatarCacheResult(local_path="", error=str(exc))

    target = platform_dir / f"{digest}{extension}"
    temp = target.with_suffix(f"{target.suffix}.tmp")
    temp.write_bytes(payload)
    temp.replace(target)
    return AvatarCacheResult(local_path=str(target))


def _existing_cached_file(cache_dir: Path, digest: str) -> Path | None:
    for extension in _IMAGE_EXTENSIONS.values():
        path = cache_dir / f"{digest}{extension}"
        if path.exists() and path.is_file():
            return path
    return None


def _platform_cache_dir(platform: str, cache_dir: Path) -> Path:
    safe = "".join(ch for ch in platform.strip().lower() if ch.isalnum() or ch in {"_", "-"})
    return cache_dir / (safe or "unknown")


def _image_extension(url: str, content_type: str) -> str | None:
    if content_type in _IMAGE_EXTENSIONS:
        return _IMAGE_EXTENSIONS[content_type]
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix in set(_IMAGE_EXTENSIONS.values()):
        return suffix
    guessed = mimetypes.guess_extension(content_type or "")
    if guessed in set(_IMAGE_EXTENSIONS.values()):
        return guessed
    return None


def _read_limited(response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_AVATAR_BYTES:
            raise OSError(f"avatar exceeds {MAX_AVATAR_BYTES} bytes")
        chunks.append(chunk)
    return b"".join(chunks)
