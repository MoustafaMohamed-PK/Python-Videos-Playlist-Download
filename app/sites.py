"""
Site detection: is a URL supported by yt-dlp, and by which extractor?

Responsible for:
    - Deciding whether a URL looks downloadable at all (scheme check --
      fast, no imports) before paying the cost of importing yt-dlp.
    - Asking yt-dlp's own extractor registry which site (if any) claims
      a URL, so this app never hardcodes a per-site host list.
    - Replacing the old YouTube-only ``validate_youtube_url`` with a
      site-neutral equivalent.

Deliberately NOT here: any hardcoded list of "supported" hostnames.
yt-dlp ships ~1750 extractors; asking it directly is both more capable
and less maintenance than curating a list that will always lag behind.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import List, Optional

from app.validators import ValidationError

_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)

_lock = threading.Lock()
_extractor_classes: Optional[List] = None


class UnsupportedSiteError(ValidationError):
    """No yt-dlp extractor (other than the generic fallback) matches this URL."""


@dataclass(frozen=True)
class SiteMatch:
    """Result of matching a URL against yt-dlp's extractor registry."""

    supported: bool  # True if any extractor (generic or not) matched
    extractor: str  # ie_key(), e.g. "Vimeo", or "Generic"
    display_name: str  # human-readable IE_NAME
    working: bool  # False if yt-dlp has flagged this extractor as broken
    generic_only: bool  # True if only the catch-all Generic extractor matched


def _load_extractor_classes() -> List:
    """Import and cache yt-dlp's extractor classes.

    Importing ``yt_dlp.extractor`` and instantiating the class list is
    the expensive part of this module (hundreds of ms the first time,
    single-digit ms after) -- done lazily and once so a plain
    ``import app.sites`` (and therefore CLI startup / --help) stays
    fast for users who never actually need it.
    """
    global _extractor_classes
    if _extractor_classes is None:
        with _lock:
            if _extractor_classes is None:
                from yt_dlp.extractor import gen_extractor_classes

                # Extractors with _VALID_URL is False (e.g. embed-only
                # helpers) can never be "suitable" for a bare URL --
                # skip them so suitable() isn't called needlessly.
                _extractor_classes = [
                    ie for ie in gen_extractor_classes() if ie._VALID_URL is not False
                ]
    return _extractor_classes


def match_extractor(url: str) -> SiteMatch:
    """Find which yt-dlp extractor (if any) claims ``url``.

    The generic extractor (``GenericIE``) matches almost anything and is
    yt-dlp's own last-resort fallback, so it is only reported when no
    more specific extractor matches.
    """
    classes = _load_extractor_classes()
    generic = None
    for ie_class in classes:
        if ie_class.ie_key() == "Generic":
            generic = ie_class
            continue
        try:
            suitable = ie_class.suitable(url)
        except Exception:  # noqa: BLE001 - a broken extractor shouldn't crash detection
            suitable = False
        if suitable:
            return SiteMatch(
                supported=True,
                extractor=ie_class.ie_key(),
                display_name=getattr(ie_class, "IE_NAME", ie_class.ie_key()),
                working=ie_class.working(),
                generic_only=False,
            )

    if generic is not None and generic.suitable(url):
        return SiteMatch(
            supported=True,
            extractor="Generic",
            display_name=getattr(generic, "IE_NAME", "Generic"),
            working=generic.working(),
            generic_only=True,
        )

    return SiteMatch(
        supported=False,
        extractor="",
        display_name="",
        working=False,
        generic_only=False,
    )


def validate_media_url(url: str, *, allow_generic: bool = True) -> str:
    """Validate that ``url`` is an http(s) URL some yt-dlp extractor supports.

    Raises :class:`ValidationError` (or its subclass
    :class:`UnsupportedSiteError`) on failure; returns the stripped URL
    on success.
    """
    if not url or not url.strip():
        raise ValidationError("The URL cannot be empty.")
    url = url.strip()

    # Scheme check first and without importing yt-dlp, so a bad scheme
    # (or a typo) fails instantly instead of paying the extractor-import
    # cost only to reject the URL anyway.
    if not _SCHEME_RE.match(url):
        raise ValidationError(
            "That does not look like a valid URL. It must start with "
            "http:// or https://."
        )

    match = match_extractor(url)
    if not match.supported:
        raise UnsupportedSiteError(
            "No supported site recognizes this URL. Run "
            "`yt-dlp --list-extractors` to see everything yt-dlp supports."
        )
    if match.generic_only and not allow_generic:
        raise UnsupportedSiteError(
            "No site-specific extractor recognizes this URL (only yt-dlp's "
            "generic fallback matched)."
        )
    if not match.generic_only and not match.working:
        raise UnsupportedSiteError(
            f"{match.display_name} is currently marked as broken/unsupported "
            "by yt-dlp and cannot be downloaded right now."
        )
    return url
