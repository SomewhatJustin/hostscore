"""Utility helpers for request validation and network hygiene."""

from __future__ import annotations

import re
from typing import List, Tuple
from urllib.parse import urlsplit, urlunsplit


_AIRBNB_HOST_PATTERN = re.compile(r"(^|\.)airbnb\.(com|co\.uk|ca|de|fr|it|es|com\.au)$")
_IM_WIDTH_PATTERN = re.compile(r"[?&]im_w=(\d+)")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def normalize_listing_url(raw_url: str) -> str:
    """Normalize Airbnb listing URLs for consistent cache keys."""
    parts = urlsplit(raw_url.strip())
    scheme = parts.scheme or "https"
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")

    if not netloc:
        raise ValueError("URL must include a host.")
    if not _AIRBNB_HOST_PATTERN.search(netloc):
        raise ValueError("Only Airbnb domains are supported.")
    if "/rooms/" not in path:
        raise ValueError("URL must reference an Airbnb room listing.")

    normalized = urlunsplit((scheme, netloc, path, "", ""))
    return normalized


def build_cache_key(
    url: str,
    *,
    report_type: str,
    user_id: str | None = None,
    credit_id: str | None = None,
) -> str:
    """Return a deterministic cache key scoped to user/report context."""

    normalized = normalize_listing_url(url)
    parts = [normalized.lower(), report_type.lower()]
    if user_id:
        parts.append(user_id.lower())
    if credit_id:
        parts.append(credit_id.lower())
    return "::".join(parts)


def parse_srcset(srcset: str) -> List[Tuple[str, int]]:
    """Parse a srcset string into (url, width) tuples."""
    entries: List[Tuple[str, int]] = []
    for candidate in srcset.split(","):
        parts = candidate.strip().split()
        if not parts:
            continue
        url = parts[0]
        width = 0
        if len(parts) > 1 and parts[1].endswith("w"):
            spec = parts[1][:-1]
            if spec.isdigit():
                width = int(spec)
        entries.append((url, width))
    return entries


def extract_im_width(url: str) -> int:
    """Return width inferred from Airbnb's im_w query parameter."""
    match = _IM_WIDTH_PATTERN.search(url)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return 0
    return 0
