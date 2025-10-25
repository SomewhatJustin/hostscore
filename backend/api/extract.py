"""HTML extraction routines for Airbnb listings."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

from bs4 import BeautifulSoup, Tag
from playwright.async_api import Page, Response
from trafilatura import extract as trafilatura_extract

from .browser import BrowserManager
from .utils import DEFAULT_USER_AGENT, extract_im_width, parse_srcset


_GENERIC_ALT_PATTERNS = (
    re.compile(r"\b(?:listing\s+)?image\s*\d+(?:\s+of\s+\d+)?$", re.I),
    re.compile(r"\bphoto\s*\d+(?:\s+of\s+\d+)?$", re.I),
)
_BACKGROUND_URL_PATTERN = re.compile(r"url\((?:'|\")?(.*?)(?:'|\")?\)")
_LEGACY_GALLERY_LABEL = re.compile(r"\b(?:listing\s+)?image\s*\d+(?:\s+of\s+\d+)?$", re.I)


@dataclass
class PhotoMeta:
    """Metadata extracted for a single photo asset."""

    url: str
    width: Optional[int] = None
    height: Optional[int] = None
    alt: Optional[str] = None
    srcset: List[str] = field(default_factory=list)


@dataclass
class ListingContent:
    """Structured snapshot of the listing content."""

    url: str
    title: str
    summary: str
    description: str
    full_text: str
    amenities_listed: List[str] = field(default_factory=list)
    house_rules: List[str] = field(default_factory=list)
    reviews: List[str] = field(default_factory=list)
    photos: List[PhotoMeta] = field(default_factory=list)
    uses_legacy_gallery: bool = False
    debug: dict = field(default_factory=dict)


async def render_listing(
    url: str,
    browser_manager: BrowserManager,
    wait_after_load_ms: int = 1200,
    scroll_timeout_ms: int = 500,
    capture_debug: bool = False,
) -> ListingContent:
    """Render a listing URL with Playwright and return structured content."""

    async with browser_manager.page() as page:
        await _prepare_page(page)
        captured_responses: List[str] = []

        if capture_debug:

            def _store_response(response: Response) -> None:
                try:
                    if "api" in response.url or "graphql" in response.url:
                        captured_responses.append(
                            f"{response.status} {response.url}"
                        )
                except Exception:
                    return

            page.on("response", _store_response)

        payload_task = asyncio.create_task(_wait_for_listing_payload(page))
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        if wait_after_load_ms:
            await page.wait_for_timeout(wait_after_load_ms)
        await _auto_scroll(page, scroll_timeout_ms)
        # Allow any lazy content to settle.
        await page.wait_for_timeout(500)

        html = await page.content()
        preloaded_state = await _gather_listing_payload(payload_task)
        if not preloaded_state:
            preloaded_state = await _get_preloaded_state(page)
        photo_modal_html = await _capture_photo_modal(page)
        amenities_modal_html, amenities_items = await _capture_amenities_modal(page)

    listing = extract_listing(
        html,
        url,
        photo_overlay_html=photo_modal_html,
        amenities_html=amenities_modal_html,
        amenities_items=amenities_items,
        preloaded_state=preloaded_state,
    )

    if capture_debug:
        listing.debug.update(
            {
                "preloaded_state": bool(preloaded_state),
                "photo_modal": bool(photo_modal_html),
                "amenities_modal": bool(amenities_modal_html),
                "raw_html": html,
                "photo_modal_html": photo_modal_html,
                "amenities_modal_html": amenities_modal_html,
                "amenities_items": amenities_items,
                "preloaded_state_raw": preloaded_state,
                "responses": captured_responses[:50],
            }
        )

    return listing


async def _prepare_page(page: Page) -> None:
    await page.set_extra_http_headers({"user-agent": DEFAULT_USER_AGENT})
    await page.set_viewport_size({"width": 1280, "height": 900})


async def _auto_scroll(page: Page, scroll_timeout_ms: int) -> None:
    await page.evaluate(
        """async (pause) => {
            await new Promise((resolve) => {
                let totalHeight = 0;
                const distance = 600;
                const timer = setInterval(() => {
                    window.scrollBy(0, distance);
                    totalHeight += distance;
                    if (totalHeight >= document.body.scrollHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, pause);
            });
        }""",
        scroll_timeout_ms,
    )


async def _wait_for_listing_payload(page: Page) -> Optional[dict]:
    try:
        response: Response = await page.wait_for_event(
            "response",
            lambda res: (
                res.status == 200
                and (
                    "StaysPdpSections" in res.url
                    or "PdpPlatformSections" in res.url
                    or "PdpSections" in res.url
                )
            ),
            timeout=15000,
        )
    except Exception:
        return None

    try:
        return await response.json()
    except Exception:
        try:
            import json

            body = await response.text()
            return json.loads(body)
        except Exception:
            return None


async def _gather_listing_payload(task: asyncio.Task) -> Optional[dict]:
    if task is None:
        return None
    try:
        return await task
    except Exception:
        task.cancel()
        return None


async def _get_preloaded_state(page: Page) -> Optional[dict]:
    return await page.evaluate(
        """() => {
            try {
                const state = window.__PRELOADED_STATE__;
                return state ? JSON.parse(JSON.stringify(state)) : null;
            } catch (err) {
                return null;
            }
        }"""
    )


async def _capture_photo_modal(page: Page) -> Optional[str]:
    selectors = [
        "button:has-text(\"Show all photos\")",
        "button:has-text(\"Show all\")",
        "button:has-text(\"Photos\")",
        "[data-testid=\"photo-tour-button\"]",
        "[data-testid=\"structured-gallery-view-all-button\"]",
    ]
    for selector in selectors:
        element = await page.query_selector(selector)
        if not element:
            continue
        opened = False
        try:
            await page.evaluate("(el) => el.click()", element)
            await page.wait_for_timeout(600)
            # Dismiss translation modal if it appears.
            translation_dialog = await page.query_selector('[data-testid=\"translation-announce-modal\"]')
            if translation_dialog:
                close_btn = await translation_dialog.query_selector('button[aria-label=\"Close\"]')
                if close_btn:
                    await page.evaluate("(el) => el.click()", close_btn)
                    await page.wait_for_timeout(200)
                    await page.evaluate("(el) => el.click()", element)
                    await page.wait_for_timeout(600)
            dialog = await page.query_selector('div[role=\"dialog\"]')
            if not dialog:
                continue
            if await dialog.query_selector('[data-testid=\"translation-announce-modal\"]'):
                close_btn = await dialog.query_selector('button[aria-label=\"Close\"]')
                if close_btn:
                    await page.evaluate("(el) => el.click()", close_btn)
                    await page.wait_for_timeout(200)
                continue
            opened = True
            await page.evaluate(
                """() => {
                    const dialog = document.querySelector('div[role="dialog"]');
                    if (!dialog) return;
                    const scrollers = dialog.querySelectorAll('[data-testid="structured-gallery-scroll-container"], [data-testid="modal-container"]');
                    scrollers.forEach((node) => {
                        node.scrollTop = 0;
                        const step = () => {
                            node.scrollBy(0, 600);
                            if (node.scrollTop + node.clientHeight < node.scrollHeight) {
                                requestAnimationFrame(step);
                            }
                        };
                        requestAnimationFrame(step);
                    });
                }"""
            )
            await page.wait_for_timeout(800)
            html = await page.evaluate(
                """() => {
                    const dialog = document.querySelector('div[role="dialog"]');
                    return dialog ? dialog.outerHTML : null;
                }"""
            )
            if html:
                return html
        except Exception:
            continue
        finally:
            if opened:
                await _close_modal(page)
    return None


async def _capture_amenities_modal(page: Page) -> tuple[Optional[str], List[str]]:
    selectors = [
        '[data-testid="pdp-show-all-amenities-button"]',
        'button:has-text("Show all amenities")',
        'button:has-text("Show all")',
        'button:has-text("See all amenities")',
    ]

    async def _open(selector: str, depth: int = 0) -> tuple[Optional[str], List[str]]:
        if depth > 4:
            return None, []
        buttons = await page.query_selector_all(selector)
        if not buttons and selector == selectors[-1]:
            buttons = await page.query_selector_all("button")
        scored_buttons = []
        for candidate in buttons:
            try:
                text = (await candidate.inner_text() or "").strip()
            except Exception:
                continue
            lowered = text.lower()
            score = 0
            if "amenit" in lowered:
                score += 3
            if "show all" in lowered or "see all" in lowered:
                score += 2
            if "amenities" in lowered:
                score += 1
            if score == 0 and selector != selectors[-1]:
                continue
            scored_buttons.append((score, candidate, lowered))
        scored_buttons.sort(key=lambda item: item[0], reverse=True)
        if not scored_buttons:
            return None, []
        for _, button, _lowered in scored_buttons:
            await page.evaluate('(el) => el.scrollIntoView({block: "center"})', button)
            await page.wait_for_timeout(150)
            await page.evaluate('(el) => el.click()', button)
            await page.wait_for_timeout(600)
            dialog = None
            dialogs = await page.query_selector_all('div[role="dialog"]')
            for candidate_dialog in reversed(dialogs):
                try:
                    text = (await candidate_dialog.inner_text() or "").lower()
                except Exception:
                    continue
                if "amenit" in text or "what this place offers" in text:
                    dialog = candidate_dialog
                    break
            if not dialog:
                await page.wait_for_timeout(200)
                continue
            translation_modal = await dialog.query_selector('[data-testid="translation-announce-modal"]')
            text_content = (await dialog.inner_text()) or ''
            lowered_content = text_content.lower()
            if translation_modal or 'translation settings' in lowered_content or 'translation on' in lowered_content:
                close_btn = await dialog.query_selector('button[aria-label="Close"]')
                if close_btn:
                    await page.evaluate('(el) => el.click()', close_btn)
                    await page.wait_for_timeout(200)
                return await _open(selector, depth + 1)
            if 'amenit' not in lowered_content and 'what this place offers' not in lowered_content:
                await _close_modal(page)
                await page.wait_for_timeout(200)
                continue
            await page.evaluate(
                """(dialog) => {
                    if (!dialog) return;
                    const scrollContainer = dialog.querySelector('[data-testid="amenity-modal"]') || dialog;
                    if (!scrollContainer) return;
                    let traversed = 0;
                    const total = scrollContainer.scrollHeight;
                    while (traversed < total) {
                        scrollContainer.scrollBy(0, 800);
                        traversed += 800;
                    }
                }""",
                dialog,
            )
            await page.wait_for_timeout(600)
            html = await page.evaluate(
                """(dialog) => dialog ? dialog.outerHTML : null""",
                dialog,
            )
            items = await page.evaluate(
                """(dialog) => {
                    if (!dialog) return [];
                    const results = [];
                    const nodes = dialog.querySelectorAll('[data-testid="pdp-section-amenities-item"], [data-testid="amenity-item"], ul[role="list"] li');
                    nodes.forEach((node) => {
                        const text = (node.innerText || '').trim();
                        if (text) {
                            results.push(text);
                        }
                    });
                    return results;
                }""",
                dialog,
            )
            await _close_modal(page)
            cleaned = [item for item in items if item]
            if cleaned:
                return html, cleaned
            await page.wait_for_timeout(200)
        return None, []

    for selector in selectors:
        html, items = await _open(selector)
        if items:
            return html, items
    return None, []


async def _close_modal(page: Page) -> None:
    try:
        close_button = page.locator('button[aria-label="Close"], button:has-text("Close")')
        if await close_button.count():
            await close_button.first.click(force=True)
            await page.wait_for_timeout(300)
            return
    except Exception:
        pass
    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(200)
    except Exception:
        return


def extract_listing(
    html: str,
    url: str,
    photo_overlay_html: Optional[str] = None,
    amenities_html: Optional[str] = None,
    amenities_items: Optional[List[str]] = None,
    preloaded_state: Optional[dict] = None,
) -> ListingContent:
    """Parse rendered HTML into structured listing content."""
    soup = BeautifulSoup(html, "html.parser")
    overlay_soup = BeautifulSoup(photo_overlay_html, "html.parser") if photo_overlay_html else None
    amenities_soup = BeautifulSoup(amenities_html, "html.parser") if amenities_html else None

    title = _pick_text(
        soup,
        selectors=[
            '[data-testid="title"]',
            '[data-testid="photo-viewer-detail-title"]',
            "h1",
        ],
    )
    summary = _pick_summary(soup)
    description = _pick_description(soup)
    full_text = trafilatura_extract(html, include_comments=False, favor_precision=True) or ""
    amenities_listed = _extract_amenities(soup, amenities_soup, preloaded_state, amenities_items)
    house_rules = _extract_house_rules(soup)
    reviews = _extract_reviews(soup, limit=2)
    uses_legacy_gallery = _detect_legacy_gallery(soup, overlay_soup)
    photos = _extract_photos(soup, overlay_soup, preloaded_state)

    return ListingContent(
        url=url,
        title=title,
        summary=summary,
        description=description,
        full_text=full_text,
        amenities_listed=amenities_listed,
        house_rules=house_rules,
        reviews=reviews,
        photos=photos,
        uses_legacy_gallery=uses_legacy_gallery,
    )


def _pick_text(soup: BeautifulSoup, selectors: List[str]) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node and (text := node.get_text(" ", strip=True)):
            return text
    return ""


def _pick_summary(soup: BeautifulSoup) -> str:
    summary = _pick_text(
        soup,
        selectors=[
            '[data-testid="place_breadcrumb"]',
            '[data-testid="subtitle"]',
            "h2",
        ],
    )
    if summary:
        return summary
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    meta = soup.find("meta", attrs={"property": "og:description"})
    return meta["content"].strip() if meta and meta.get("content") else ""


def _pick_description(soup: BeautifulSoup) -> str:
    section = soup.select_one('[data-section-id="DESCRIPTION_DEFAULT"]')
    if not section:
        section = soup.select_one('[data-testid="listing-description"]')
    paragraphs: List[str] = []
    if section:
        for node in section.select("p, span"):
            text = node.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)
    description = "\n".join(paragraphs)
    return description


def _extract_amenities(
    soup: BeautifulSoup,
    amenities_soup: Optional[BeautifulSoup] = None,
    preloaded_state: Optional[dict] = None,
    external_items: Optional[List[str]] = None,
) -> List[str]:
    items: List[str] = []

    def normalize_text(raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        parts = [part.strip() for part in raw.split("\n") if part.strip()]
        if not parts:
            return None
        primary = " ".join(parts[0].split())
        if not primary or primary.lower().startswith("unavailable:"):
            return None
        return primary

    def collect(container: Optional[BeautifulSoup]) -> None:
        if not container:
            return
        section = container.select_one('[data-section-id="AMENITIES_DEFAULT"]')
        if section:
            for node in section.select('[data-testid="amenity-item"]'):
                text = normalize_text(node.get_text("\n", strip=True))
                if text:
                    items.append(text)
        for node in container.select('[itemprop="amenityFeature"] span'):
            text = normalize_text(node.get_text("\n", strip=True))
            if text:
                items.append(text)
        for node in container.select('ul[role="list"] li'):
            if "amenit" in (node.get_text(" ", strip=True) or "").lower():
                continue
            text = normalize_text(node.get_text("\n", strip=True))
            if text:
                items.append(text)
        for node in container.select('[data-testid="pdp-section-amenities-item"]'):
            text = normalize_text(node.get_text("\n", strip=True))
            if text:
                items.append(text)

    collect(soup)
    collect(amenities_soup)
    if external_items:
        for item in external_items:
            text = normalize_text(item.replace("\r", "\n"))
            if text:
                items.append(text)

    return list(dict.fromkeys(items))


def _extract_house_rules(soup: BeautifulSoup) -> List[str]:
    rules: List[str] = []

    def add_rule(text: Optional[str]) -> None:
        cleaned = (text or "").strip()
        if not cleaned:
            return
        lowered = cleaned.lower()
        if lowered in {"show more", "add dates", "house rules"}:
            return
        rules.append(cleaned)

    def drain(container: Optional[BeautifulSoup]) -> None:
        if not container:
            return
        for node in container.select("li, p, span"):
            if node.find_parent("button"):
                continue
            add_rule(node.get_text(" ", strip=True))

    section = soup.select_one('[data-section-id="POLICIES_DEFAULT"]')
    if section:
        heading = section.find(
            lambda tag: tag.name in {"h2", "h3"}
            and "house rules" in tag.get_text(" ", strip=True).lower()
        )
        if heading:
            column = heading.parent.parent if heading.parent else None
            drain(column)

    if not rules:
        legacy_section = soup.select_one('[data-section-id="HOUSE_RULES_DEFAULT"]')
        drain(legacy_section)

    modal = soup.select_one('[aria-label="House rules"]')
    drain(modal)

    # Preserve original order while removing duplicates.
    return list(dict.fromkeys(rules))


def _extract_reviews(soup: BeautifulSoup, limit: int = 2) -> List[str]:
    reviews: List[str] = []
    section = soup.select_one('[data-section-id="REVIEWS_DEFAULT"]')
    if section:
        for node in section.select('[data-testid="review-card"]'):
            text = node.get_text(" ", strip=True)
            if text:
                reviews.append(text)
            if len(reviews) >= limit:
                break
    if reviews:
        return reviews[:limit]
    # Fallback to general review text.
    for node in soup.select('[data-testid="review-item"], [data-testid="review-text"]'):
        text = node.get_text(" ", strip=True)
        if text:
            reviews.append(text)
        if len(reviews) >= limit:
            break
    return reviews[:limit]


def _extract_photos(
    soup: BeautifulSoup,
    overlay_soup: Optional[BeautifulSoup] = None,
    preloaded_state: Optional[dict] = None,
) -> List[PhotoMeta]:
    photos: List[PhotoMeta] = []
    seen_urls = set()

    def _is_generic_alt(text: Optional[str]) -> bool:
        if not text:
            return True
        normalized = " ".join(text.split())
        if not normalized:
            return True
        return any(pattern.search(normalized) for pattern in _GENERIC_ALT_PATTERNS)

    def _aria_reference_text(ref: Optional[str], container: BeautifulSoup) -> Optional[str]:
        if not ref:
            return None
        for ref_id in ref.split():
            target = container.find(id=ref_id)
            if isinstance(target, Tag):
                label = target.get_text(" ", strip=True)
                if label and not _is_generic_alt(label):
                    return label
        return None

    def _infer_photo_label(node: Optional[Tag], container: BeautifulSoup) -> str:
        if not isinstance(node, Tag):
            return ""

        direct_alt = (node.get("alt") or "").strip()
        if direct_alt and not _is_generic_alt(direct_alt):
            return direct_alt

        aria_label = (node.get("aria-label") or "").strip()
        if aria_label and not _is_generic_alt(aria_label):
            return aria_label

        title_attr = (node.get("title") or "").strip()
        if title_attr and not _is_generic_alt(title_attr):
            return title_attr

        labelledby_text = _aria_reference_text(node.get("aria-labelledby"), container)
        if labelledby_text:
            return labelledby_text

        describedby_text = _aria_reference_text(node.get("aria-describedby"), container)
        if describedby_text:
            return describedby_text

        for ancestor in node.parents:
            if not isinstance(ancestor, Tag):
                continue
            ancestor_aria = (ancestor.get("aria-label") or "").strip()
            if ancestor_aria and not _is_generic_alt(ancestor_aria):
                return ancestor_aria

            ancestor_labelledby = _aria_reference_text(
                ancestor.get("aria-labelledby"), container
            )
            if ancestor_labelledby:
                return ancestor_labelledby

            ancestor_describedby = _aria_reference_text(
                ancestor.get("aria-describedby"), container
            )
            if ancestor_describedby:
                return ancestor_describedby

            if ancestor.name == "button":
                button_title = (ancestor.get("title") or "").strip()
                if button_title and not _is_generic_alt(button_title):
                    return button_title
                button_text = ancestor.get_text(" ", strip=True)
                if button_text and not _is_generic_alt(button_text):
                    return button_text

            if ancestor.get("role") == "img":
                role_label = (ancestor.get("aria-label") or "").strip()
                if role_label and not _is_generic_alt(role_label):
                    return role_label

        return direct_alt if direct_alt and not _is_generic_alt(direct_alt) else ""

    def collect(container: BeautifulSoup) -> None:
        for picture in container.find_all("picture"):
            sources = picture.find_all("source")
            candidates = []
            for source in sources:
                srcset = source.get("srcset")
                if srcset:
                    candidates.extend(parse_srcset(srcset))
            img = picture.find("img")
            if img:
                src = img.get("src", "")
                if not candidates and src:
                    width = extract_im_width(src)
                    candidates.append((src, width))
                alt = _infer_photo_label(img, container)
            else:
                alt = ""
            if not candidates and img:
                src = img.get("src", "")
                if src:
                    candidates.append((src, extract_im_width(src)))
            if not candidates:
                continue
            url, width = max(candidates, key=lambda item: item[1])
            if url in seen_urls:
                continue
            seen_urls.add(url)
            photos.append(
                PhotoMeta(
                    url=url,
                    width=width,
                    alt=alt,
                    srcset=[candidate[0] for candidate in candidates],
                )
            )

        for img in container.find_all("img"):
            if img.find_parent("picture"):
                continue
            src = img.get("src", "")
            srcset = img.get("srcset", "")
            candidates = parse_srcset(srcset) if srcset else []
            if not candidates and src:
                width = extract_im_width(src)
                if width or "im_w=" in src:
                    candidates.append((src, width))
            if not candidates:
                continue
            normalized_candidates = []
            for candidate_url, candidate_width in candidates:
                width_hint = candidate_width or extract_im_width(candidate_url)
                normalized_candidates.append((candidate_url, width_hint))
            url, width = max(normalized_candidates, key=lambda item: item[1])
            if url in seen_urls:
                continue
            seen_urls.add(url)
            photos.append(
                PhotoMeta(
                    url=url,
                    width=width,
                    alt=_infer_photo_label(img, container),
                    srcset=[candidate[0] for candidate in normalized_candidates],
                )
            )

        for role_img in container.select('[role="img"]'):
            style_attr = role_img.get("style") or ""
            match = _BACKGROUND_URL_PATTERN.search(style_attr)
            if not match:
                continue
            bg_url = match.group(1)
            if not bg_url or bg_url.startswith("data:"):
                continue
            if bg_url in seen_urls:
                continue
            seen_urls.add(bg_url)
            photos.append(
                PhotoMeta(
                    url=bg_url,
                    width=extract_im_width(bg_url),
                    alt=_infer_photo_label(role_img, container),
                    srcset=[bg_url],
                )
            )

    collect(soup)
    if overlay_soup:
        collect(overlay_soup)

    return photos


def _detect_legacy_gallery(
    soup: BeautifulSoup, overlay_soup: Optional[BeautifulSoup] = None
) -> bool:
    def has_legacy_markers(container: Optional[BeautifulSoup]) -> bool:
        if not container:
            return False
        attr_names = ("aria-label", "alt", "title")
        for attr in attr_names:
            node = container.find(attrs={attr: _LEGACY_GALLERY_LABEL})
            if node:
                return True
        for button in container.select("button"):
            label = button.get_text(" ", strip=True)
            if label and _LEGACY_GALLERY_LABEL.match(label):
                return True
        return False

    return has_legacy_markers(overlay_soup) or has_legacy_markers(soup)
