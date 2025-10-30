"""Resend integration for transactional emails."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from httpx import AsyncClient, HTTPStatusError

from .auth import MagicLinkSender


logger = logging.getLogger(__name__)


class ResendClient(MagicLinkSender):
    """Minimal async client for Resend magic-link emails."""

    def __init__(
        self,
        api_key: str,
        *,
        sender: str,
        base_url: str = "https://api.resend.com",
        timeout_seconds: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._sender = sender
        self._client = AsyncClient(base_url=base_url, timeout=timeout_seconds)

    async def send_magic_link(self, *, email: str, link: str, expires_at: datetime) -> None:
        payload = {
            "from": self._sender,
            "to": [email],
            "subject": "Your HostScore sign-in link",
            "html": self._build_html(link, expires_at),
            "text": self._build_text(link, expires_at),
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._client.post("/emails", json=payload, headers=headers)
            response.raise_for_status()
        except HTTPStatusError as exc:  # pragma: no cover - network error path
            logger.error(
                "Failed to send magic link to %s: %s", email, exc.response.text if exc.response else exc
            )
            raise

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _build_html(link: str, expires_at: datetime) -> str:
        expiry = expires_at.strftime("%b %d %Y %H:%M %Z")
        return "".join(
            [
                "<p>Welcome back to HostScore!</p>",
                f"<p><a href=\"{link}\">Click here to finish signing in</a>. ",
                "This link works once and expires shortly.",
                f"</p><p><small>Valid until {expiry}.</small></p>",
            ]
        )

    @staticmethod
    def _build_text(link: str, expires_at: datetime) -> str:
        expiry = expires_at.strftime("%b %d %Y %H:%M %Z")
        return (
            "Welcome back to HostScore!\n\n"
            f"Visit this link to sign in: {link}\n"
            "It is one-time use and expires soon.\n\n"
            f"Valid until {expiry}."
        )


class ConsoleEmailClient(MagicLinkSender):
    """Fallback sender that logs magic links during local development."""

    async def send_magic_link(self, *, email: str, link: str, expires_at: datetime) -> None:  # pragma: no cover - logging path
        logger.info("Magic link for %s -> %s (expires %s)", email, link, expires_at.isoformat())
