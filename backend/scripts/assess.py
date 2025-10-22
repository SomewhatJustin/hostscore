#!/usr/bin/env python
"""Manual assessment runner to aid interactive debugging."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_DIR = PROJECT_ROOT / "api"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from api.browser import BrowserManager  # type: ignore  # noqa: E402
from api.extract import render_listing  # type: ignore  # noqa: E402
from api.heuristics import run_heuristics  # type: ignore  # noqa: E402
from api.models import AssessmentResponse  # type: ignore  # noqa: E402
from api.utils import normalize_listing_url  # type: ignore  # noqa: E402


async def assess(
    url: str,
    headless: bool,
    max_concurrency: int,
    debug: bool,
    dump_state: Optional[Path],
    dump_html: Optional[Path],
    dump_photo_modal: Optional[Path],
    dump_amenities_modal: Optional[Path],
) -> None:
    manager = BrowserManager(headless=headless, max_concurrency=max_concurrency)
    try:
        normalized = normalize_listing_url(url)
        content = await render_listing(
            normalized,
            manager,
            capture_debug=debug,
        )
        heuristics = run_heuristics(content)
        response = AssessmentResponse(
            overall=heuristics.overall,
            section_scores=heuristics.section_scores,
            photo_stats=heuristics.photo_stats,
            copy_stats=heuristics.copy_stats,
            trust_signals=heuristics.trust_stats,
            amenities=heuristics.amenities,
            top_fixes=heuristics.recommendations,
        )
        print(json.dumps(response.model_dump(), indent=2))
        if debug:
            debug_info = {
                "has_preloaded_state": bool(content.debug.get("preloaded_state")),
                "photo_modal": content.debug.get("photo_modal"),
                "amenities_modal": content.debug.get("amenities_modal"),
            }
            debug_payload = {
                "photo_count": len(content.photos),
                "photo_examples": [photo.__dict__ for photo in content.photos[:5]],
                "amenities_listed": content.amenities_listed[:20],
                "house_rules": content.house_rules[:10],
                "debug_info": debug_info,
                "responses": content.debug.get("responses", [])[:10],
            }
            print("\n# Debug payload\n")
            print(json.dumps(debug_payload, indent=2))

        if dump_state:
            raw_state = content.debug.get("preloaded_state_raw")
            dump_state.parent.mkdir(parents=True, exist_ok=True)
            with dump_state.open("w", encoding="utf-8") as fh:
                json.dump(raw_state, fh, ensure_ascii=False, indent=2)
            print(f"\nWrote preloaded state to {dump_state}")
        if dump_html:
            dump_html.parent.mkdir(parents=True, exist_ok=True)
            html_content = content.debug.get("raw_html", "")
            dump_html.write_text(html_content or "", encoding="utf-8")
            print(f"Wrote raw HTML to {dump_html}")
        if dump_photo_modal:
            dump_photo_modal.parent.mkdir(parents=True, exist_ok=True)
            modal_html = content.debug.get("photo_modal_html", "")
            dump_photo_modal.write_text(modal_html or "", encoding="utf-8")
            print(f"Wrote photo modal HTML to {dump_photo_modal}")
        if dump_amenities_modal:
            dump_amenities_modal.parent.mkdir(parents=True, exist_ok=True)
            amenities_html = content.debug.get("amenities_modal_html", "")
            dump_amenities_modal.write_text(amenities_html or "", encoding="utf-8")
            print(f"Wrote amenities modal HTML to {dump_amenities_modal}")
    finally:
        await manager.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Assess an Airbnb listing manually.")
    parser.add_argument("url", help="Listing URL")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run Chromium with a visible window for debugging.",
    )
    parser.add_argument("--max-concurrency", type=int, default=2, help="Playwright concurrency limit.")
    parser.add_argument("--debug", action="store_true", help="Dump extra extraction details.")
    parser.add_argument(
        "--dump-state",
        type=Path,
        help="Write window.__PRELOADED_STATE__ to the given path (debug only).",
    )
    parser.add_argument("--dump-html", type=Path, help="Write rendered HTML to path (debug only).")
    parser.add_argument("--dump-photo-modal", type=Path, help="Write captured photo modal HTML to path.")
    parser.add_argument("--dump-amenities-modal", type=Path, help="Write captured amenities modal HTML to path.")
    args = parser.parse_args()

    asyncio.run(
        assess(
            args.url,
            headless=not args.headed,
            max_concurrency=args.max_concurrency,
            debug=any(
                [
                    args.debug,
                    args.dump_state is not None,
                    args.dump_html is not None,
                    args.dump_photo_modal is not None,
                    args.dump_amenities_modal is not None,
                ]
            ),
            dump_state=args.dump_state,
            dump_html=args.dump_html,
            dump_photo_modal=args.dump_photo_modal,
            dump_amenities_modal=args.dump_amenities_modal,
        )
    )


if __name__ == "__main__":
    main()
