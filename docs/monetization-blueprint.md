# Monetization Blueprint

## Goals
- Offer a free assessment that reveals partial insights, upselling to a paid full report.
- Charge $10 per paid report and allow purchasing additional credits as needed.
- Keep implementation lightweight while fitting existing FastAPI + SvelteKit architecture.

## User Experience
- Landing workflow:
  - Anonymous visitors run the free flow and see 2 of the top 5 recommended fixes.
  - Remaining fixes are blurred with copy that highlights the value of the paid report and teases the bonus section.
- Upgrade prompts:
  - Sticky bottom drawer and button copy such as “Unlock 8 more fixes + bonus insights.”
  - Clicking upgrade initiates login (if needed) and then Stripe Checkout.
- Post-upgrade UI:
  - Header shows authenticated user’s email, credits remaining (only if logged in), and two CTAs: “Free report” and “Paid report.”
  - Bonus section (text summary with next steps) is visible in the paid report response only.

## Authentication & Sessions
- Magic-link system via Resend:
  - User enters email in the upgrade flow.
  - Backend generates a signed, single-use token (JWT) with 15 minute expiry and sends link via Resend.
  - On click, session cookie (HttpOnly, Secure) is issued and user redirected back to the page.
- No dashboards or profile management; session data limited to identity and credit metadata.

## Stripe Integration
- One-time product priced at $10 for a single paid report credit.
- Hosted Stripe Checkout handles payment; front end redirects logged-in users straight to Checkout.
- Stripe webhook (verify signatures) processes `checkout.session.completed` events:
  - Normalize customer email, upsert user record, increment credits, set `expires_at = now() + 30 days`.
  - Record transaction row for audit and compliance.
- Allow repeated purchases; each checkout adds one credit with its own 30-day expiration timestamp.

## Credits & Access Control
- Schema sketch (PostgreSQL):
  - `users(id uuid pk, email citext unique, created_at timestamptz, last_login timestamptz)`
  - `credits(id uuid pk, user_id fk, expires_at timestamptz, redeemed_at timestamptz null)`
  - `reports(id uuid pk, user_id fk, listing_url text, type enum('free','paid'), credit_id fk null, created_at timestamptz, payload_hash text)`
- On paid report request:
  - Backend finds the earliest unexpired, unredeemed credit; if none, respond 302 → `/not-enough-credits`.
  - Reserve credit, run analysis, finalize cache entry, mark credit redeemed on success. On failure, release reservation.
- Free reports do not consume credits but still log in `reports`.

## Caching & Data Handling
- Reuse `backend/api/cache.py` to keep recent report payloads warm for faster repeat views.
- Cache entries tagged with `user_id`, `listing_url`, `report_type`, `credit_id` so responses never leak between users.
- Cache hit returns the stored payload; paid cache entries still require session verification before serving.

## Static “Not Enough Credits” Page
- Route `/not-enough-credits` in the SvelteKit app:
  - Copy explaining credit depletion.
  - CTA button “Buy another report” linking to Checkout creation endpoint.
  - Secondary link to support email (e.g., `support@hostscore.com`).

## Simplifications for MVP
- No rate limiting, analytics pipelines, or webhook event dashboards.
- No team sharing or delegated credits.
- No dashboards; surface status inline via header and report components.
- Stripe is the sole payment provider; no Apple Pay integration beyond Checkout defaults.
- Bonus section limited to text summary and next steps; richer visualizations can come later.

## Next Implementation Steps
1. Model tables and migrations for users, credits, reports.
2. Implement magic-link endpoints (issue, consume) and Resend integration.
3. Add Stripe Checkout session creation endpoint and webhook handler.
4. Gate paid report API path behind credit check and integrate cache tagging.
5. Update frontend: free vs paid flows, upgrade drawer, credit-aware header, static “Not Enough Credits” page.
6. Document operational runbooks and webhook secrets in `MASTERPLAN.md`.

