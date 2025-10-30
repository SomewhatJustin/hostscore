"""FastAPI entrypoint for the Airbnb listing assessor backend."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import warnings
from datetime import timedelta
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from httpx import AsyncClient, HTTPStatusError
from dotenv import load_dotenv
from urllib3.exceptions import NotOpenSSLWarning
from playwright.async_api import Error as PlaywrightError

from .auth import MagicLinkService, SessionManager
from .browser import BrowserManager
from .cache import AssessmentCache
from .database import Database, User, UserCreditSummary, utcnow
from .emails import ConsoleEmailClient, ResendClient
from .extract import render_listing
from .heuristics import run_heuristics
from .models import (
    AssessmentRequest,
    AssessmentResponse,
    CheckoutConfirmRequest,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CreditSummary,
    MagicLinkRequest,
    ReportEnvelope,
    ReportMeta,
    ReportType,
    SessionResponse,
)
from .polar import (
    POLAR_API_BASE_LIVE,
    POLAR_API_BASE_SANDBOX,
    PolarConfig,
    PolarService,
)
from .scorer import LLMSettings, generate_listing_overview, refine_assessment
from .utils import build_cache_key, normalize_listing_url

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")
warnings.filterwarnings("ignore", category=NotOpenSSLWarning)


def _join_url(base: str, tail: str) -> str:
    base = base.rstrip("/")
    tail = tail.lstrip("/")
    if not base:
        return f"/{tail}" if tail else "/"
    if not tail:
        return base
    return f"{base}/{tail}"


app = FastAPI(
    title="Airbnb Listing Assessor",
    version="0.2.0",
    description="Evaluate Airbnb listings and manage HostScore paid reports.",
)

_cors_origins = [
    origin.strip()
    for origin in os.getenv("API_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if not _cors_origins:
    default_frontend = os.getenv("PUBLIC_APP_BASE_URL")
    if default_frontend:
        _cors_origins = [default_frontend]
    else:
        _cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_startup_lock = asyncio.Lock()
_is_ready = False

_browser_manager: Optional[BrowserManager] = None
_response_cache: Optional[AssessmentCache[str, AssessmentResponse]] = None
_llm_settings: Optional[LLMSettings] = None
_llm_client: Optional[AsyncClient] = None
_overview_settings: Optional[LLMSettings] = None
_overview_client: Optional[AsyncClient] = None
_database: Optional[Database] = None
_magic_links: Optional[MagicLinkService] = None
_session_manager: Optional[SessionManager] = None
_email_sender: Optional[ConsoleEmailClient | ResendClient] = None
_polar_service: Optional[PolarService] = None
_auth_base_url: str = ""
_post_login_redirect: str = ""
_default_checkout_cancel: str = ""


def compose_bonus_summary(assessment: AssessmentResponse) -> str:
    """Derive a lightweight "bonus" summary for paid reports."""

    scores = {
        "photo gallery": assessment.section_scores.photos,
        "listing description": assessment.section_scores.copy_score,
        "amenity clarity": assessment.section_scores.amenities_clarity,
        "trust signals": assessment.section_scores.trust_signals,
    }
    strongest_label, strongest_score = max(scores.items(), key=lambda item: item[1])
    weakest_label, weakest_score = min(scores.items(), key=lambda item: item[1])

    if assessment.top_fixes:
        primary = assessment.top_fixes[0]
        fix_text = (
            f"Lead with {primary.reason.lower()} — {primary.how_to_fix}."
        )
    else:
        fix_text = "Lean into the weakest area to unlock quick wins."

    return (
        f"{strongest_label.title()} is carrying the experience at {strongest_score}%. "
        f"Bring {weakest_label} up from {weakest_score}% to balance the stay. {fix_text}"
    )


async def current_user(request: Request) -> Optional[User]:
    if _session_manager is None or _database is None:
        return None
    token = request.cookies.get(_session_manager.cookie_name)
    if not token:
        return None
    session = _session_manager.verify(token)
    if not session:
        return None
    return await _database.get_user_by_id(session.user_id)


async def require_user(user: Optional[User] = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return user


def _ensure_ready() -> None:
    if not _is_ready or _browser_manager is None or _response_cache is None:
        raise HTTPException(status_code=503, detail="Service initializing, try again.")


@app.on_event("startup")
async def on_startup() -> None:
    """Initialize global resources (Playwright, cache, persistence)."""

    global _is_ready, _browser_manager, _response_cache, _llm_settings, _llm_client
    global _overview_settings, _overview_client
    global _database, _magic_links, _session_manager, _email_sender, _polar_service
    global _auth_base_url, _post_login_redirect, _default_checkout_cancel

    async with _startup_lock:
        if _is_ready:
            return

        max_concurrency = int(os.getenv("MAX_CONCURRENCY", "4"))
        ttl_seconds = int(os.getenv("CACHE_TTL_SECONDS", "900"))
        cache_maxsize = int(os.getenv("CACHE_MAXSIZE", "128"))
        headless = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() != "false"
        disable_sandbox = os.getenv("PLAYWRIGHT_DISABLE_SANDBOX", "true").lower() != "false"

        _browser_manager = BrowserManager(
            headless=headless,
            max_concurrency=max_concurrency,
            disable_sandbox=disable_sandbox,
        )
        _response_cache = AssessmentCache[str, AssessmentResponse](
            maxsize=cache_maxsize,
            ttl_seconds=ttl_seconds,
        )

        db_path = os.getenv("HOSTSCORE_DATABASE_PATH")
        if db_path:
            db_path = str(Path(db_path).expanduser())
        else:
            default_dir = Path("backend") / "data"
            default_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(default_dir / "hostscore.sqlite3")

        _database = Database(db_path)
        await _database.connect()

        session_secret = (
            os.getenv("SESSION_SECRET")
            or os.getenv("MAGIC_LINK_SECRET")
            or "dev-session-secret"
        )
        secure_cookie = os.getenv("SESSION_COOKIE_SECURE", "true").lower() != "false"
        cookie_domain = os.getenv("SESSION_COOKIE_DOMAIN") or None
        session_ttl = int(os.getenv("SESSION_TTL_SECONDS", str(30 * 24 * 3600)))
        _session_manager = SessionManager(
            secret=session_secret,
            secure_cookie=secure_cookie,
            cookie_domain=cookie_domain,
            ttl_seconds=session_ttl,
        )

        magic_secret = os.getenv("MAGIC_LINK_SECRET") or session_secret
        magic_ttl = int(os.getenv("MAGIC_LINK_TTL_SECONDS", "900"))
        issuer = os.getenv("MAGIC_LINK_ISSUER", "hostscore")
        _magic_links = MagicLinkService(
            db=_database,
            secret=magic_secret,
            ttl_seconds=magic_ttl,
            issuer=issuer,
        )

        resend_api_key = os.getenv("RESEND_API_KEY")
        resend_sender = os.getenv("RESEND_SENDER")
        if resend_api_key and resend_sender:
            _email_sender = ResendClient(resend_api_key, sender=resend_sender)
            logger.info("Resend email delivery enabled.")
        else:
            _email_sender = ConsoleEmailClient()
            logger.info("Resend not configured; logging magic links to console.")

        _auth_base_url = (
            os.getenv("AUTH_CALLBACK_BASE_URL")
            or os.getenv("API_BASE_URL")
            or "http://localhost:8000"
        ).rstrip("/")
        _post_login_redirect = (
            os.getenv("POST_LOGIN_REDIRECT_URL")
            or os.getenv("PUBLIC_APP_BASE_URL")
            or "http://localhost:5173"
        ).rstrip("/")
        if not _post_login_redirect:
            _post_login_redirect = "http://localhost:5173"

        _default_checkout_cancel = (
            os.getenv("CHECKOUT_CANCEL_URL")
            or _join_url(_post_login_redirect, "")
        )

        polar_success_url = os.getenv("POLAR_SUCCESS_URL")
        if not polar_success_url:
            logger.warning("POLAR_SUCCESS_URL is not configured; checkout redirection may fail.")
        polar_return_url = os.getenv("POLAR_RETURN_URL") or _default_checkout_cancel

        sandbox_token = os.getenv("POLAR_ACCESS_TOKEN_SANDBOX")
        sandbox_product = os.getenv("POLAR_PRODUCT_ID_SANDBOX")
        sandbox_config = (
            PolarConfig(
                access_token=sandbox_token,
                product_id=sandbox_product,
                api_base=POLAR_API_BASE_SANDBOX,
            )
            if sandbox_token and sandbox_product
            else None
        )

        live_token = os.getenv("POLAR_ACCESS_TOKEN")
        live_product = os.getenv("POLAR_PRODUCT_ID")
        live_config = (
            PolarConfig(
                access_token=live_token,
                product_id=live_product,
                api_base=POLAR_API_BASE_LIVE,
            )
            if live_token and live_product
            else None
        )

        if sandbox_config or live_config:
            _polar_service = PolarService(
                sandbox=sandbox_config,
                live=live_config,
                success_url_template=polar_success_url,
                return_url=polar_return_url,
            )
            if sandbox_config and live_config:
                logger.info("Polar integration enabled (live + sandbox).")
            elif sandbox_config:
                logger.info("Polar integration enabled (sandbox only).")
            else:
                logger.info("Polar integration enabled (live only).")
        else:
            _polar_service = None
            logger.info("Polar integration disabled (missing credentials).")

        api_key = os.getenv("HAIKU_API_KEY")
        if api_key:
            _llm_settings = LLMSettings(
                api_key=api_key,
                model=os.getenv("HAIKU_MODEL", "claude-haiku-4-5"),
                timeout_seconds=int(os.getenv("HAIKU_TIMEOUT_SECONDS", "10")),
                max_output_tokens=int(os.getenv("HAIKU_MAX_OUTPUT_TOKENS", "512")),
            )
            _llm_client = AsyncClient(timeout=_llm_settings.timeout_seconds)
            logger.info("LLM integration enabled.")
        else:
            _llm_settings = None
            _llm_client = None
            logger.info("LLM integration disabled (no HAIKU_API_KEY provided).")

        overview_key = os.getenv("SONNET_API_KEY") or api_key
        if overview_key:
            _overview_settings = LLMSettings(
                api_key=overview_key,
                model=os.getenv("SONNET_MODEL", "claude-sonnet-4-5"),
                timeout_seconds=int(os.getenv("SONNET_TIMEOUT_SECONDS", "15")),
                max_output_tokens=int(os.getenv("SONNET_MAX_OUTPUT_TOKENS", "768")),
            )
            _overview_client = AsyncClient(timeout=_overview_settings.timeout_seconds)
            logger.info("Sonnet overview integration enabled.")
        else:
            _overview_settings = None
            _overview_client = None
            logger.info("Sonnet overview disabled (missing credentials).")

        _is_ready = True
        logger.info("Backend startup complete.")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Dispose of global resources."""

    global _is_ready, _browser_manager, _llm_client, _overview_client, _database, _magic_links
    global _session_manager, _email_sender, _polar_service

    _is_ready = False

    if _browser_manager:
        await _browser_manager.close()
        _browser_manager = None

    if _llm_client:
        await _llm_client.aclose()
        _llm_client = None

    if _overview_client:
        await _overview_client.aclose()
        _overview_client = None

    if isinstance(_email_sender, ResendClient):
        await _email_sender.aclose()
    _email_sender = None

    if _database:
        await _database.close()
        _database = None

    _magic_links = None
    _session_manager = None
    if _polar_service:
        await _polar_service.aclose()
        _polar_service = None

    logger.info("Backend shutdown complete.")


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    """Simple readiness probe for deployment targets."""

    return {"status": "ok" if _is_ready else "initializing"}


@app.post("/assess", response_model=ReportEnvelope)
async def assess_listing(payload: AssessmentRequest, request: Request) -> ReportEnvelope:
    """Assess an Airbnb listing and return structured feedback."""

    _ensure_ready()

    if _database is None:
        raise HTTPException(status_code=503, detail="Database unavailable.")

    try:
        normalized_url = normalize_listing_url(str(payload.url))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    user = await current_user(request)
    credit = None

    if payload.report_type is ReportType.paid:
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required for paid reports.")
        credit = await _database.reserve_credit(user.id)
        if credit is None:
            raise HTTPException(
                status_code=status.HTTP_302_FOUND,
                detail="Not enough credits.",
                headers={"Location": "/not-enough-credits"},
            )

    cache_key = build_cache_key(
        normalized_url,
        report_type=payload.report_type.value,
        user_id=user.id if user else None,
        credit_id=credit.id if credit else None,
    )

    cache_miss = False
    full_response = None
    if not payload.force:
        full_response = _response_cache.get(cache_key)

    if full_response is None:
        logger.info("Assessing listing %s", normalized_url)
        try:
            content = await render_listing(normalized_url, _browser_manager)  # type: ignore[arg-type]
        except PlaywrightError as exc:
            if credit:
                await _database.release_credit(credit.id)
            logger.exception("Playwright failed to render %s", normalized_url)
            raise HTTPException(status_code=502, detail="Failed to render Airbnb listing.") from exc
        except Exception as exc:  # pragma: no cover - catch-all for resiliency
            if credit:
                await _database.release_credit(credit.id)
            logger.exception("Unexpected error rendering %s", normalized_url)
            raise HTTPException(status_code=500, detail="Unexpected error rendering listing.") from exc

        heuristics = run_heuristics(content)
        preliminary = AssessmentResponse(
            overall=heuristics.overall,
            section_scores=heuristics.section_scores,
            photo_stats=heuristics.photo_stats,
            copy_stats=heuristics.copy_stats,
            amenities=heuristics.amenities,
            trust_signals=heuristics.trust_stats,
            top_fixes=heuristics.recommendations,
        )

        context_payload = {
            "summary": content.summary,
            "description": content.description,
            "house_rules": content.house_rules,
            "reviews": content.reviews,
            "amenities_listed": content.amenities_listed,
        }

        refined = await refine_assessment(
            preliminary,
            _llm_settings,
            _llm_client,
            context=context_payload,
        )

        overview_text = None
        if payload.report_type is ReportType.paid:
            overview_text = await generate_listing_overview(
                refined,
                _overview_settings,
                _overview_client,
                context=context_payload,
            )

        summary = compose_bonus_summary(refined)
        full_response = refined.model_copy(update={"bonus_summary": summary, "owner_overview": overview_text})
        cache_miss = True
    else:
        cache_miss = False

    top_fixes = list(full_response.top_fixes)
    top_fixes_limited = top_fixes[:5]
    full_response = full_response.model_copy(update={"top_fixes": top_fixes_limited})
    if payload.report_type is ReportType.paid:
        public_response = full_response
    else:
        hidden_limit = min(3, len(top_fixes_limited))
        public_response = full_response.model_copy(
            update={
                "top_fixes": top_fixes_limited[hidden_limit:],
                "bonus_summary": None,
                "owner_overview": None,
            }
        )

    hidden_count = max(0, len(top_fixes_limited) - len(public_response.top_fixes))

    if cache_miss:
        _response_cache.set(cache_key, full_response)

    payload_json = json.dumps(
        full_response.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    try:
        await _database.log_report(
            user_id=user.id if user else None,
            listing_url=normalized_url,
            report_type=payload.report_type.value,
            credit_id=credit.id if credit else None,
            payload_hash=payload_hash,
            payload=payload_json,
        )
        if credit:
            await _database.redeem_credit(credit.id)
    except Exception as exc:  # pragma: no cover - persistence failure
        if credit:
            await _database.release_credit(credit.id)
        logger.exception("Failed to persist report for %s", normalized_url)
        raise HTTPException(status_code=500, detail="Failed to record report.") from exc

    credit_summary: Optional[UserCreditSummary] = None
    if user:
        credit_summary = await _database.get_credit_summary(user.id)

    meta = ReportMeta(
        report_type=payload.report_type,
        is_paid=payload.report_type is ReportType.paid,
        credit_id=credit.id if credit else None,
        hidden_fix_count=hidden_count,
        credits_remaining=credit_summary.available if credit_summary else None,
        next_credit_expiration=credit_summary.next_expiration if credit_summary else None,
    )

    return ReportEnvelope(report=public_response, meta=meta)


@app.post("/auth/magic-link", status_code=status.HTTP_204_NO_CONTENT)
async def request_magic_link(payload: MagicLinkRequest) -> Response:
    if _magic_links is None or _email_sender is None:
        raise HTTPException(status_code=503, detail="Service initializing, try again.")

    magic_link = await _magic_links.issue(payload.email)
    logger.debug("Magic link token for %s: %s", payload.email, magic_link.token)
    callback_url = f"{_auth_base_url}/auth/callback?token={magic_link.token}"
    await _email_sender.send_magic_link(
        email=magic_link.user.email,
        link=callback_url,
        expires_at=magic_link.expires_at,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/auth/callback")
async def consume_magic_link(token: str) -> Response:
    if _magic_links is None or _session_manager is None or _database is None:
        raise HTTPException(status_code=503, detail="Service initializing, try again.")

    try:
        user = await _magic_links.consume(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await _database.touch_last_login(user.id)
    cookie_value, _ = _session_manager.issue(user)

    redirect_url = _post_login_redirect or "/"
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(**_session_manager.cookie_args(cookie_value))
    return response


@app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    if _session_manager is not None:
        response.set_cookie(**_session_manager.clearing_args())
    return response


@app.get("/auth/session", response_model=SessionResponse)
async def session_state(request: Request) -> SessionResponse:
    user = await current_user(request)
    if not user or _database is None:
        return SessionResponse(authenticated=False)

    summary = await _database.get_credit_summary(user.id)
    credits = CreditSummary(available=summary.available, next_expiration=summary.next_expiration)
    return SessionResponse(authenticated=True, email=user.email, credits=credits)


@app.post("/checkout/session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    payload: CheckoutSessionRequest,
    user: User = Depends(require_user),
) -> CheckoutSessionResponse:
    if _polar_service is None or not _polar_service.is_available():
        raise HTTPException(status_code=503, detail="Polar integration disabled.")

    if payload.environment:
        environment = payload.environment
    else:
        environment = "live" if _polar_service.has_environment("live") else "sandbox"
    if not _polar_service.has_environment(environment):
        raise HTTPException(status_code=503, detail=f"Polar {environment} environment is not configured.")

    success_url_override = str(payload.success_url) if payload.success_url else None
    return_url_override = str(payload.cancel_url) if payload.cancel_url else _default_checkout_cancel

    metadata = {
        "user_id": user.id,
        "email": user.email,
        "environment": environment,
    }

    try:
        checkout = await _polar_service.create_checkout(
            environment=environment,
            metadata=metadata,
            success_url_override=success_url_override,
            return_url_override=return_url_override,
        )
    except HTTPStatusError as exc:  # pragma: no cover - API error
        logger.exception("Polar checkout creation failed with status %s", exc.response.status_code)
        raise HTTPException(status_code=502, detail="Unable to start checkout.") from exc
    except Exception as exc:  # pragma: no cover - network failure
        logger.exception("Failed to start Polar checkout for %s", user.email)
        raise HTTPException(status_code=502, detail="Unable to start checkout.") from exc

    checkout_id = checkout.get("id")
    checkout_url = checkout.get("url")
    if not checkout_id or not checkout_url:
        logger.error("Polar checkout response missing id or url: %s", checkout)
        raise HTTPException(status_code=502, detail="Incomplete checkout response from Polar.")

    return CheckoutSessionResponse(
        checkout_id=checkout_id,
        checkout_url=checkout_url,
        environment=environment,
    )


@app.post("/checkout/confirm", response_model=SessionResponse)
async def confirm_checkout(
    payload: CheckoutConfirmRequest,
    user: User = Depends(require_user),
) -> SessionResponse:
    if _polar_service is None or _database is None:
        raise HTTPException(status_code=503, detail="Polar integration disabled.")

    environment = payload.environment or "live"
    if not _polar_service.has_environment(environment):
        # fallback to sandbox if live missing
        if environment == "live" and _polar_service.has_environment("sandbox"):
            environment = "sandbox"
        else:
            raise HTTPException(status_code=503, detail=f"Polar {environment} environment is not configured.")

    try:
        checkout = await _polar_service.get_checkout(environment=environment, checkout_id=payload.checkout_id)
    except HTTPStatusError as exc:  # pragma: no cover - API error
        logger.exception("Failed to retrieve Polar checkout %s", payload.checkout_id)
        raise HTTPException(status_code=502, detail="Unable to verify checkout.") from exc

    status = (checkout.get("status") or "").lower()
    if status != "succeeded":
        raise HTTPException(status_code=409, detail="Checkout has not completed successfully yet.")

    metadata = checkout.get("metadata") or {}
    owner_id = str(metadata.get("user_id", ""))
    if owner_id and owner_id != user.id:
        raise HTTPException(status_code=403, detail="Checkout belongs to another user.")

    if checkout.get("customer_email") and not owner_id:
        customer_email = str(checkout.get("customer_email")).lower()
        if customer_email != user.email.lower():
            raise HTTPException(status_code=403, detail="Checkout email mismatch.")

    checkout_id = str(checkout.get("id"))
    if await _database.transaction_exists(checkout_id):
        logger.info("Polar checkout %s already processed", checkout_id)
    else:
        expires_at = utcnow() + timedelta(days=30)
        await _database.create_credit(user.id, expires_at)

        amount_total = int(checkout.get("total_amount") or 0)
        currency = str(checkout.get("currency") or "USD").upper()

        await _database.record_transaction(
            user_id=user.id,
            provider="polar",
            external_id=checkout_id,
            amount_cents=amount_total,
            currency=currency,
        )
        await _database.touch_last_login(user.id)
        logger.info("Granted report credit to %s via Polar checkout %s", user.email, checkout_id)

    summary = await _database.get_credit_summary(user.id)
    credits = CreditSummary(available=summary.available, next_expiration=summary.next_expiration)
    return SessionResponse(authenticated=True, email=user.email, credits=credits)
