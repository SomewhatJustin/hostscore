"""Playwright lifecycle management for the assessor backend."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
    Error as PlaywrightError,
)


class BrowserManager:
    """Singleton manager that provides Playwright browser contexts."""

    def __init__(
        self,
        headless: bool = True,
        max_concurrency: int = 4,
        disable_sandbox: bool = True,
    ) -> None:
        self._headless = headless
        self._max_concurrency = max_concurrency
        self._disable_sandbox = disable_sandbox
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def _ensure_browser(self) -> Browser:
        async with self._lock:
            if self._browser and not self._browser.is_connected():
                await self._dispose_browser_locked()
            if self._browser:
                return self._browser
            if not self._playwright:
                self._playwright = await async_playwright().start()
            launch_args = []
            chromium_sandbox = True
            if self._disable_sandbox:
                launch_args.extend(
                    [
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--single-process",
                        "--disable-gpu",
                        "--no-zygote",
                    ]
                )
                chromium_sandbox = False
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless,
                args=launch_args,
                chromium_sandbox=chromium_sandbox,
            )
            return self._browser

    @asynccontextmanager
    async def context(self) -> AsyncIterator[BrowserContext]:
        """Yield a browser context while respecting concurrency limits."""
        await self._semaphore.acquire()
        try:
            last_exc: Optional[PlaywrightError] = None
            for attempt in range(2):
                browser = await self._ensure_browser()
                try:
                    context = await browser.new_context()
                except PlaywrightError as exc:
                    if self._is_browser_closed_error(exc) and attempt == 0:
                        last_exc = exc
                        await self._handle_browser_disconnect()
                        continue
                    raise
                try:
                    yield context
                finally:
                    try:
                        await context.close()
                    except PlaywrightError:
                        pass
                return
            if last_exc:
                raise last_exc
        finally:
            self._semaphore.release()

    @asynccontextmanager
    async def page(self) -> AsyncIterator[Page]:
        """Yield a Playwright page scoped to a fresh context."""
        last_exc: Optional[PlaywrightError] = None
        for attempt in range(2):
            async with self.context() as context:
                try:
                    page = await context.new_page()
                except PlaywrightError as exc:
                    if self._is_browser_closed_error(exc) and attempt == 0:
                        last_exc = exc
                        await self._handle_browser_disconnect()
                        continue
                    raise
                try:
                    yield page
                finally:
                    try:
                        await page.close()
                    except PlaywrightError:
                        pass
                return
        if last_exc:
            raise last_exc

    async def close(self) -> None:
        """Tear down the global browser instance."""
        async with self._lock:
            await self._dispose_browser_locked()
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

    async def _handle_browser_disconnect(self) -> None:
        """Clear cached browser references after an unexpected shutdown."""
        async with self._lock:
            await self._dispose_browser_locked()

    async def _dispose_browser_locked(self) -> None:
        if self._browser:
            browser = self._browser
            self._browser = None
            try:
                await browser.close()
            except PlaywrightError:
                pass

    @staticmethod
    def _is_browser_closed_error(exc: PlaywrightError) -> bool:
        message = getattr(exc, "message", str(exc))
        return "Target closed" in message or "has been closed" in message
