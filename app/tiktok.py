"""
TikTok URL normalization.

Responsible for:
    - Rewriting the TikTok URL shapes yt-dlp's TikTok extractors don't
      recognize into ones they do. yt-dlp only matches
      ``www.tiktok.com/@user/video/<id>`` and the ``vm.``/``vt.``/``/t/``
      short links, but people paste plenty of other shapes:
        * TikTok Lite share links -- ``lite.tiktok.com/t/<code>`` (the
          same short-code namespace as ``www.tiktok.com/t/<code>``) or
          ``lite.tiktok.com/@user/video/<id>``.
        * ``m.tiktok.com/...`` and bare ``tiktok.com/...`` links.
        * Links carrying only the video ID (``/video/<id>``,
          ``/@/video/<id>``, ``/embed/<id>``, ``m.tiktok.com/v/<id>.html``).
    - Filling in the username for ID-only links: TikTok answers
      ``/@/video/<id>`` with HTTP 403, so the canonical URL is looked up
      via TikTok's public oEmbed endpoint.

Short links are resolved here (rather than left to yt-dlp's TikTokVM
extractor) because they can redirect to an ID-only URL, which then
needs the username fix above.

Network access is injectable (``resolve_redirect`` / ``fetch_oembed``)
so tests run offline. Any network failure falls back to the best URL
known so far -- yt-dlp then reports the real error at extraction time.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_TIKTOK_HOST_RE = re.compile(r"^(?:(?:www|m|lite|vm|vt)\.)?tiktok\.com$", re.IGNORECASE)
_SHORT_HOSTS = {"vm.tiktok.com", "vt.tiktok.com"}
_SHORT_PATH_RE = re.compile(r"^/t/[\w-]+/?$")
_CANONICAL_PATH_RE = re.compile(r"^/@[\w.-]+/video/\d+/?$")
_ID_ONLY_PATH_RES = (
    re.compile(r"^/(?:@/)?video/(?P<id>\d+)/?$"),
    re.compile(r"^/embed(?:/v2)?/(?P<id>\d+)/?$"),
    re.compile(r"^/v/(?P<id>\d+)(?:\.html)?/?$"),
)

_TIMEOUT = 15
# Same User-Agent yt-dlp's TikTokVM extractor uses: TikTok answers it
# with a plain HTTP redirect rather than an app-install landing page.
_USER_AGENT = "facebookexternalhit/1.1"

RedirectResolver = Callable[[str], str]
OEmbedFetcher = Callable[[str], Dict[str, Any]]


def _resolve_redirect(url: str) -> str:
    """Follow ``url``'s redirects and return where they end up."""
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        return response.geturl()


def _fetch_oembed(video_url: str) -> Dict[str, Any]:
    query = urllib.parse.urlencode({"url": video_url})
    request = urllib.request.Request(
        f"https://www.tiktok.com/oembed?{query}", headers={"User-Agent": _USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def is_tiktok_url(url: str) -> bool:
    host = urllib.parse.urlsplit(url).hostname or ""
    return bool(_TIKTOK_HOST_RE.match(host))


def _video_id(path: str) -> Optional[str]:
    for pattern in _ID_ONLY_PATH_RES:
        match = pattern.match(path)
        if match:
            return match.group("id")
    return None


def _canonical_from_id(video_id: str, fetch_oembed: OEmbedFetcher) -> Optional[str]:
    try:
        data = fetch_oembed(f"https://www.tiktok.com/@/video/{video_id}")
    except Exception as exc:  # noqa: BLE001 - fall back to the ID-only URL
        logger.info("TikTok oEmbed lookup failed for %s: %s", video_id, exc)
        return None
    username = data.get("author_unique_id")
    if not username or not re.fullmatch(r"[\w.-]+", username):
        return None
    return f"https://www.tiktok.com/@{username}/video/{video_id}"


def normalize_tiktok_url(
    url: str,
    *,
    resolve_redirect: RedirectResolver = _resolve_redirect,
    fetch_oembed: OEmbedFetcher = _fetch_oembed,
) -> str:
    """Return a URL yt-dlp's TikTok extractor can handle, or ``url`` unchanged.

    Non-TikTok URLs are returned untouched without any network access.
    """
    if not is_tiktok_url(url):
        return url

    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    path = parts.path or "/"

    if host in _SHORT_HOSTS or _SHORT_PATH_RE.match(path):
        short_url = (
            url if host in _SHORT_HOSTS else f"https://www.tiktok.com{path}"
        )
        try:
            resolved = resolve_redirect(short_url)
        except Exception as exc:  # noqa: BLE001 - let yt-dlp try the short link
            logger.info("Could not resolve TikTok short link %s: %s", short_url, exc)
            return short_url
        if not is_tiktok_url(resolved) or resolved == short_url:
            return short_url
        url = resolved
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        path = parts.path or "/"

    if _CANONICAL_PATH_RE.match(path):
        # Query strings from share links (?_r=1&is_from_webapp=...) are
        # tracking noise; drop them along with any non-www host.
        return f"https://www.tiktok.com{path}"

    video_id = _video_id(path)
    if video_id:
        return _canonical_from_id(video_id, fetch_oembed) or (
            f"https://www.tiktok.com/@/video/{video_id}"
        )

    if host != "www.tiktok.com":
        # Anything else (profiles, tags, ...) on a host yt-dlp doesn't
        # match: move it to www and let the extractors decide.
        return urllib.parse.urlunsplit(parts._replace(scheme="https", netloc="www.tiktok.com"))
    return url
