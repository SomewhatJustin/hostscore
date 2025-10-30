"""LLM integration for refining heuristic results."""

from __future__ import annotations

import logging
import json
import textwrap
from typing import Optional

from httpx import AsyncClient, HTTPStatusError
from pydantic import BaseModel, ConfigDict
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from .heuristics import sort_top_fixes
from .models import AssessmentResponse, TopFix

SYSTEM_PROMPT = (
    "You are a conversion copy expert helping hosts improve Airbnb listings. "
    "Only return valid JSON. Keep each fix short (<=180 characters) and actionable. "
    "When assessing amenities, rely on the provided listing context to confirm evidence."
)

USER_PROMPT_TEMPLATE = textwrap.dedent(
    """
    Given the heuristic assessment and listing context below, adjust the overall score by at most +/-5 points if justified,
    return up to 5 prioritized fixes, and reclassify the amenities evidence list. Respond strictly with JSON matching this schema:
    {{
      "overall_adjustment": integer in [-5,5],
      "top_fixes": [
        {{"impact":"high|medium|low","reason":string,"how_to_fix":string}}
      ],
      "amenities": {{
        "text_hits": [string],
        "likely_present_not_listed": [string],
        "listed_no_text_evidence": [string]
      }}
    }}

    Heuristic assessment:
    {assessment_json}

    Listing context:
    {context_json}
    """
)


def _prepare_context_payload(context: Optional[dict[str, object]] = None) -> dict[str, object]:
    """Trim and normalize listing context fields before sending to the LLM."""

    context = context or {}

    def _trim(text: Optional[str], limit: int) -> str:
        if not text:
            return ""
        text = text.strip()
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    house_rules = context.get("house_rules") or []
    reviews = context.get("reviews") or []
    amenities_listed = context.get("amenities_listed") or []

    return {
        "summary": _trim(str(context.get("summary", "")), 400),
        "description": _trim(str(context.get("description", "")), 1200),
        "house_rules": [str(item)[:160] for item in list(house_rules)[:8]],
        "reviews": [str(item)[:200] for item in list(reviews)[:4]],
        "amenities_listed": [str(item) for item in list(amenities_listed)[:40]],
    }


LISTING_OPTIMIZATION_GUIDANCE = textwrap.dedent(
    """
    Photography quick wins:
    - Stage and declutter every room before shooting.
    - Capture images in natural daylight and supplement with warm interior lighting to avoid shadows.
    - Shoot at eye level from corners to show depth and keep vertical lines straight.
    - Highlight signature amenities or views and include at least one clear shot of every space plus exterior context.
    - Lead with a standout cover photo, sequence the gallery to show variety first, and add captions that clarify features.

    Listing description quick wins:
    - Open with the strongest selling points so skimmers understand the value immediately.
    - Use a warm, guest-focused tone that helps the reader picture their stay.
    - Spotlight unique amenities and location perks with clear guest benefits.
    - Weave in relevant keywords (property type, neighborhood, amenities) without sounding like a checklist.
    - Break copy into scannable sections or bullets and set honest expectations about quirks.
    - Keep the title fresh so key hooks appear in search results alongside the description improvements.
    """
)


OVERVIEW_SYSTEM_PROMPT = (
    "You are a seasoned Airbnb growth coach delivering concise, actionable overviews to listing owners. "
    "Write in second person, keep the tone encouraging yet candid, and ground every point in supplied evidence."
)


OVERVIEW_USER_PROMPT_TEMPLATE = textwrap.dedent(
    """
    Craft a high-level overview for the listing owner using the assessment snapshot and trimmed context below. Tie praise and 
    opportunities directly to the evidence provided, and explain why each recommendation will move bookings. Keep the response 
    under 220 words and structure it with short paragraphs or bullet sections so it reads quickly.

    Assessment snapshot (JSON):
    {assessment_json}

    Listing context (JSON):
    {context_json}

    Reference guidance to reinforce your coaching:
    {guidance}

    Requirements:
    - Start with a one-sentence celebration of what the host is doing well.
    - Include a focused section on strengths anchored in metrics, quotes, or photo stats.
    - Include a focused section on improvement opportunities that links to the suggested fixes or low scores.
    - Close with a short rationale that explains why these moves will improve conversions.
    - Avoid generic platitudes; be specific and use the host's language when possible.
    """
)


class LLMSettings(BaseModel):
    """Configuration for Haiku API requests."""

    model_config = ConfigDict(extra="forbid")

    api_key: str
    endpoint: str = "https://api.anthropic.com/v1/messages"
    model: str = "claude-haiku-4-5"
    timeout_seconds: int = 10
    max_output_tokens: int = 512


logger = logging.getLogger(__name__)


async def refine_assessment(
    heuristics: AssessmentResponse,
    settings: Optional[LLMSettings],
    client: Optional[AsyncClient] = None,
    context: Optional[dict[str, object]] = None,
) -> AssessmentResponse:
    """Call the LLM to refine heuristics and produce final response."""
    if settings is None or not settings.api_key:
        return heuristics

    assessment_json = heuristics.model_dump()
    context_payload = _prepare_context_payload(context)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        assessment_json=json.dumps(assessment_json, ensure_ascii=True),
        context_json=json.dumps(context_payload, ensure_ascii=True),
    )
    payload = {
        "model": settings.model,
        "max_output_tokens": settings.max_output_tokens,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt}
                ],
            },
        ],
    }

    headers = {
        "x-api-key": settings.api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    http_client = client or AsyncClient(timeout=settings.timeout_seconds)
    data = None
    try:
        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_fixed(0.8),
            retry=retry_if_exception_type(HTTPStatusError),
        ):
            with attempt:
                response = await http_client.post(
                    settings.endpoint,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
    except HTTPStatusError as exc:
        logger.warning(
            "LLM refinement failed with status %s; returning heuristic output.",
            exc.response.status_code if exc.response else "unknown",
        )
        return heuristics
    except Exception as exc:
        logger.exception("LLM refinement error; returning heuristic output.")
        return heuristics
    finally:
        if client is None:
            await http_client.aclose()

    if not data:
        return heuristics

    top_fixes: list[TopFix] = sort_top_fixes(heuristics.top_fixes.copy())
    overall = heuristics.overall

    amenities = heuristics.amenities.model_copy()

    try:
        content = data["content"][0]["text"]
        llm_payload = json.loads(content)
        adjustment = int(llm_payload.get("overall_adjustment", 0))
        adjustment = max(-5, min(5, adjustment))
        overall = max(0, min(100, overall + adjustment))

        llm_fixes = llm_payload.get("top_fixes", [])
        parsed_fixes = []
        for raw in llm_fixes:
            try:
                parsed_fixes.append(
                    TopFix(
                        impact=str(raw.get("impact", "medium")),
                        reason=str(raw.get("reason", "")).strip(),
                        how_to_fix=str(raw.get("how_to_fix", "")).strip(),
                    )
                )
            except Exception:
                continue
        if parsed_fixes:
            top_fixes = sort_top_fixes(parsed_fixes)[:5]

        amenities_payload = llm_payload.get("amenities", {})
        if isinstance(amenities_payload, dict):
            text_hits = amenities_payload.get("text_hits")
            likely_present = amenities_payload.get("likely_present_not_listed")
            listed_no_evidence = amenities_payload.get("listed_no_text_evidence")

            if isinstance(text_hits, list):
                amenities = amenities.model_copy(update={"text_hits": [str(item).strip() for item in text_hits if str(item).strip()]})
            if isinstance(likely_present, list):
                amenities = amenities.model_copy(
                    update={
                        "likely_present_not_listed": [
                            str(item).strip() for item in likely_present if str(item).strip()
                        ]
                    }
                )
            if isinstance(listed_no_evidence, list):
                amenities = amenities.model_copy(
                    update={
                        "listed_no_text_evidence": [
                            str(item).strip() for item in listed_no_evidence if str(item).strip()
                        ]
                    }
                )
    except Exception:
        # Fall back to heuristic-only output on parse errors.
        pass

    enriched = heuristics.model_copy(
        update={"overall": overall, "top_fixes": top_fixes, "amenities": amenities}
    )
    return enriched


async def generate_listing_overview(
    assessment: AssessmentResponse,
    settings: Optional[LLMSettings],
    client: Optional[AsyncClient] = None,
    context: Optional[dict[str, object]] = None,
) -> Optional[str]:
    """Produce a high-level paid-report overview via Sonnet 4.5."""

    if settings is None or not settings.api_key:
        return None

    assessment_payload = assessment.model_dump(mode="json", exclude_none=True)
    assessment_payload.pop("owner_overview", None)

    context_payload = _prepare_context_payload(context)

    user_prompt = OVERVIEW_USER_PROMPT_TEMPLATE.format(
        assessment_json=json.dumps(assessment_payload, ensure_ascii=True),
        context_json=json.dumps(context_payload, ensure_ascii=True),
        guidance=LISTING_OPTIMIZATION_GUIDANCE.strip(),
    )

    payload = {
        "model": settings.model,
        "max_output_tokens": settings.max_output_tokens,
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": OVERVIEW_SYSTEM_PROMPT}]},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt}
                ],
            },
        ],
    }

    headers = {
        "x-api-key": settings.api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    http_client = client or AsyncClient(timeout=settings.timeout_seconds)
    data = None
    try:
        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(2),
            wait=wait_fixed(1.0),
            retry=retry_if_exception_type(HTTPStatusError),
        ):
            with attempt:
                response = await http_client.post(
                    settings.endpoint,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
    except HTTPStatusError as exc:
        logger.warning(
            "LLM overview failed with status %s; skipping overview.",
            exc.response.status_code if exc.response else "unknown",
        )
        return None
    except Exception:
        logger.exception("LLM overview error; skipping overview.")
        return None
    finally:
        if client is None:
            await http_client.aclose()

    if not data:
        return None

    try:
        overview_text = data["content"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        logger.warning("LLM overview response missing text content.")
        return None

    return overview_text if overview_text else None
