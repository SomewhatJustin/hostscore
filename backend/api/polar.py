"""Polar checkout integration utilities."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


logger = logging.getLogger(__name__)


POLAR_API_BASE_LIVE = "https://api.polar.sh"
POLAR_API_BASE_SANDBOX = "https://sandbox-api.polar.sh"


@dataclass
class PolarConfig:
    """Configuration for a Polar environment."""

    access_token: str
    product_id: str
    api_base: str


class PolarService:
    """Client for interacting with Polar's checkout API."""

    def __init__(
        self,
        *,
        sandbox: Optional[PolarConfig] = None,
        live: Optional[PolarConfig] = None,
        success_url_template: Optional[str] = None,
        return_url: Optional[str] = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._sandbox = sandbox
        self._live = live
        self._success_url_template = success_url_template
        self._return_url = return_url
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def aclose(self) -> None:
        await self._client.aclose()

    def is_available(self) -> bool:
        return any([self._sandbox, self._live])

    def has_environment(self, environment: str) -> bool:
        try:
            self._get_config(environment)
            return True
        except ValueError:
            return False

    def _get_config(self, environment: str) -> PolarConfig:
        env = environment.lower()
        if env == "sandbox":
            if not self._sandbox:
                raise ValueError("Polar sandbox environment is not configured.")
            return self._sandbox
        if env == "live":
            if not self._live:
                raise ValueError("Polar live environment is not configured.")
            return self._live
        raise ValueError(f"Unknown Polar environment '{environment}'.")

    async def create_checkout(
        self,
        *,
        environment: str,
        metadata: Optional[Dict[str, Any]] = None,
        success_url_override: Optional[str] = None,
        return_url_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        config = self._get_config(environment)

        success_url = success_url_override or self._success_url_template
        if not success_url:
            raise ValueError("POLAR_SUCCESS_URL is not configured.")

        payload: Dict[str, Any] = {
            "products": [config.product_id],
            "success_url": success_url,
        }
        if metadata:
            payload["metadata"] = metadata
        return_url = return_url_override or self._return_url
        if return_url:
            payload["return_url"] = return_url

        headers = {
            "Authorization": f"Bearer {config.access_token}",
        }

        response = await self._client.post(
            f"{config.api_base}/v1/checkouts/",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()
        logger.debug(
            "Created Polar checkout %s in %s environment", data.get("id"), environment
        )
        return data

    async def get_checkout(self, *, environment: str, checkout_id: str) -> Dict[str, Any]:
        config = self._get_config(environment)
        headers = {
            "Authorization": f"Bearer {config.access_token}",
        }
        response = await self._client.get(
            f"{config.api_base}/v1/checkouts/{checkout_id}",
            headers=headers,
        )
        response.raise_for_status()
        return response.json()

