"""Playwright lifecycle management for the assessor backend."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright


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
            browser = await self._ensure_browser()
            context = await browser.new_context()
            try:
                yield context
            finally:
                await context.close()
        finally:
            self._semaphore.release()

    @asynccontextmanager
    async def page(self) -> AsyncIterator[Page]:
        """Yield a Playwright page scoped to a fresh context."""
        async with self.context() as context:
            page = await context.new_page()
            try:
                yield page
            finally:
                await page.close()

    async def close(self) -> None:
        """Tear down the global browser instance."""
        async with self._lock:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
