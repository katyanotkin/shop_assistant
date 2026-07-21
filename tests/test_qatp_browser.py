"""
Browser-driven QATP (quality-assurance test plan) against a locally-running
dev server, using Playwright to drive real Chrome instead of raw HTTP.

Run with (from repo root):
    PYTHONPATH=. .venv/bin/python -m uvicorn web.main:app --port 8000 &
    QATP_BROWSER=1 PYTHONPATH=. .venv/bin/pytest tests/test_qatp_browser.py -v
    pkill -f "uvicorn web.main:app"

All tests are skipped automatically unless QATP_BROWSER=1 is set AND a server
answers at QATP_BASE_URL (default http://localhost:8000). This mirrors
test_live_qatp.py's PROD_URL-gate skip style, except the gate is a local env
var + liveness probe rather than a deployed URL, because this suite needs a
real running app to click through (Playwright drives the actual browser DOM,
not just HTTP responses).

Requires `.env` with GOOGLE_CLOUD_PROJECT and ADMIN_PASSWORD set, and
`gcloud auth application-default login` already done — like the rest of this
repo, there is no Firestore emulator or mocking here. Every request in this
suite hits real Firestore and, where a search is actually generated/run, real
Vertex AI/Gemini.

WHY SYNTHETIC USERS, NOT THE REAL GOOGLE ACCOUNTS
--------------------------------------------------
The product owner has exactly two real Google accounts used for their OWN
manual testing: katyanotkin@gmail.com (free tier) and
kate.middlesex@gmail.com (premium tier). Free is capped at 1 search total /
20 runs per month; premium is capped at 2 search-creations/day / 100 runs per
month. Logging in as either of those from an automated suite that creates and
runs searches would burn the owner's own manual-testing quota every time this
suite runs — and real Google OAuth (/auth/login -> /auth/callback) can't be
scripted headlessly anyway (no test bypass, real 2FA-capable accounts).

So this suite never touches those two accounts. Instead it mints SYNTHETIC
users directly in Firestore (`core.firestore_client.upsert_user`, role via
`update_user_role`) under the recognisable `@example.test` domain, then signs
into the browser as that user by minting a real session JWT with
`core.auth.create_session_token` (using the SAME session_secret the running
app process reads from .env) and injecting it as the `sa_session` cookie via
`context.add_cookies(...)`. This is a legitimate session — indistinguishable
to the app from a real Google login — without ever exercising OAuth or
spending the owner's real quota. Every synthetic user and every search/run
doc this suite creates is deleted in a fixture finalizer, registered
immediately after creation (not "code after yield") so a failure partway
through setup or the test itself still cleans up whatever was already
created.

DO NOT "fix" this to log in as the real accounts — that is the one thing this
file must never do.

Admin flows (password login) are fine to automate as-is: they're not tied to
a real Google identity, and mirror .claude/skills/verify/SKILL.md's pattern.

Button-text collision gotcha (from the verify skill): "Save" appears on both
the create panel (#cs-save-btn) and the edit panel (#edit-save-btn); prefer
ID selectors over loose text/role selectors throughout this file for exactly
that reason.

CSS text-transform gotcha: several UI labels ("Your picks", "Matches", etc.)
are rendered with `text-transform: uppercase` in app.css. Playwright's
`inner_text()` reflects the browser's rendered (visually transformed) text,
not the literal DOM text content — so assertions against that copy compare
case-insensitively rather than hardcoding the visual casing.
"""

import datetime as dt
import os

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

import core.firestore_client as fc
import web.main as web_main
from core.auth import create_session_token, user_doc_id

QATP_BROWSER = os.environ.get("QATP_BROWSER") == "1"
BASE_URL = os.environ.get("QATP_BASE_URL", "http://localhost:8000").rstrip("/")

# Mirrors app.js's NEW_SEARCH_GATE_MSG — there is no server-side constant to
# import for this one (unlike PREMIUM_DAILY_LIMIT_MSG below), since the free
# 1-search gate is purely a client-side UI affordance; the server enforces it
# via a 403 on save instead.
FREE_TIER_GATE_MSG = "Consider premium tier for another search."


def _server_is_up() -> bool:
    try:
        httpx.get(BASE_URL, timeout=2)
        return True
    except Exception:
        return False


def _skip_reason() -> str | None:
    if not QATP_BROWSER:
        return "QATP_BROWSER=1 not set — skipping browser QATP suite (see module docstring to run it)"
    if not _server_is_up():
        return f"No live server reachable at {BASE_URL} — start it first (see module docstring)"
    return None


pytestmark = pytest.mark.skipif(bool(_skip_reason()), reason=_skip_reason() or "")


def _delete_run_doc(search_name: str, run_date: str) -> None:
    """No delete_run helper exists in firestore_client — this suite is the
    only test file that writes a run doc directly, so drop straight to the
    collection reference rather than adding a prod code path just for tests."""
    fc.get_db().collection("shop_results").document(search_name).collection("runs").document(run_date).delete()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        yield b
        b.close()


@pytest.fixture
def synthetic_user(request):
    """Factory fixture: synthetic_user(email, role, display_name) -> dict with
    a ready-to-inject session cookie for that email.

    `email` MUST be under @example.test — enforced here so a copy-paste typo
    can never accidentally mint a session for one of the two real accounts.
    Cleanup (fc.delete_user) is registered via request.addfinalizer
    IMMEDIATELY after the Firestore write succeeds, not as code after a
    yield — so if a later step in the *same* factory call raises (e.g. an
    invalid role), or the test itself fails, the already-created user is
    still deleted.
    """

    def _make(email: str, role: str = "free", display_name: str = "QATP Probe"):
        if not email.endswith("@example.test"):
            raise ValueError(f"synthetic QATP users must use the @example.test domain, got {email!r}")
        fc.upsert_user(email=email, display_name=display_name, photo_url="")
        request.addfinalizer(lambda: fc.delete_user(email))
        if role != "free":
            fc.update_user_role(user_doc_id(email), role)
        token = create_session_token(
            {"email": email, "display_name": display_name, "photo_url": "", "role": role},
            web_main._settings.session_secret,
        )
        cookie = {"name": "sa_session", "value": token, "url": BASE_URL}
        return {"email": email, "role": role, "token": token, "cookie": cookie}

    return _make


@pytest.fixture
def redaction_search(request):
    """Seed a public search, owned by a synthetic user, with pinned_finds +
    example_urls + a run containing a match — directly via fc.save_search_config
    / fc.save_run (no UI, no Gemini call needed; this is synthetic fixture
    data, not a claim about a real product). Used to check the personal-layer
    redaction contract on GET /api/results/<search>/<date>.
    """
    owner_email = "qatp_redaction_owner@example.test"
    search_name = "qatp_redaction_probe"
    run_date = dt.date.today().isoformat()

    config = {
        "search_name": search_name,
        "title": "QATP Redaction Probe",
        "active": True,
        "visibility": "public",
        "owner_id": owner_email,
        "criteria": {"category": ["qatp synthetic widget"]},
        "preferred_shops": [],
        "created_at": dt.datetime.now(dt.timezone.utc),
        "pinned_finds": [
            {
                "url": "https://example.test/pinned-product",
                "title": "QATP Pinned Product",
                "price": 42.0,
                "score": 9.5,
                "matched": ["material"],
                "unmatched": [],
                "notes": "synthetic test pin",
                "is_new": False,
                "pinned_at": run_date,
            }
        ],
        "example_urls": ["https://example.test/reference-product"],
    }
    fc.save_search_config(config)
    request.addfinalizer(lambda: fc.delete_search_config(search_name))

    run = {
        "search_name": search_name,
        "run_date": run_date,
        "matches": [
            {
                "url": "https://example.test/match-product",
                "title": "QATP Match Product",
                "price": 55.0,
                "score": 8.5,
                "matched": ["category"],
                "unmatched": [],
                "notes": "synthetic test match",
                "is_new": False,
            }
        ],
        "partial_matches": [],
        "no_match": False,
        "total_candidates": 3,
        "feedback": {},
    }
    fc.save_run(search_name, run_date, run)
    request.addfinalizer(lambda: _delete_run_doc(search_name, run_date))

    return {"search_name": search_name, "owner_email": owner_email, "run_date": run_date}


def _new_context(browser, cookie: dict | None = None):
    context = browser.new_context(base_url=BASE_URL)
    if cookie:
        context.add_cookies([cookie])
    return context


# ---------------------------------------------------------------------------
# 1. Free-tier user: create exactly one search, get gated, run it, see results
# ---------------------------------------------------------------------------


class TestFreeTierLifecycle:
    """A free-tier synthetic user can create exactly one search through the
    real UI form, is then gated with a disabled button + tooltip, and can run
    their one search to see real results rendered in the DOM."""

    def test_create_gate_and_run(self, browser, synthetic_user, request):
        user = synthetic_user("qatp_free_probe@example.test", role="free", display_name="QATP Free Probe")
        context = _new_context(browser, user["cookie"])
        page = context.new_page()
        try:
            page.goto("/")
            page.wait_for_selector("#search-list")

            new_btn = page.locator("#new-search-btn")
            expect(new_btn).to_be_visible()
            expect(new_btn).to_be_enabled()

            new_btn.click()
            page.locator("#cs-title").fill("QATP Free Coat Probe")
            page.locator("#cs-desc").fill(
                "Synthetic QATP test search — do not action: a warm waxed cotton coat, size M, under $200."
            )
            with page.expect_response(
                lambda r: r.url.endswith("/api/user/search/generate") and r.request.method == "POST",
                timeout=60000,
            ) as gen_info:
                page.locator("#cs-generate-btn").click()
            gen_resp = gen_info.value
            assert gen_resp.ok, f"generate failed: {gen_resp.status} {gen_resp.text()}"
            search_name = gen_resp.json()["search_name"]
            request.addfinalizer(lambda: fc.delete_search_config(search_name))

            expect(page.locator("#cs-preview")).to_be_visible(timeout=30000)
            page.locator("#cs-save-btn").click()
            expect(page.locator("#cs-save-msg")).to_have_text("Saved.", timeout=15000)

            # Gated: exactly one search allowed on the free plan.
            gated_btn = page.locator("#new-search-btn")
            expect(gated_btn).to_be_disabled(timeout=15000)
            assert gated_btn.get_attribute("title") == FREE_TIER_GATE_MSG, (
                f"expected the free-tier gate tooltip {FREE_TIER_GATE_MSG!r}, "
                f"got {gated_btn.get_attribute('title')!r}"
            )
            gate_span = page.locator(".new-search-gate-msg")
            expect(gate_span).to_have_text(FREE_TIER_GATE_MSG)

            # Run it — real pipeline (grounded search + fetch + rank), can take a
            # while. Timeout matches Cloud Run's request timeout (600s, set in
            # cloudbuild.yaml) rather than hardcoding a shorter client-side
            # ceiling that would time out before the server's own limit does.
            run_btn = page.locator("#cs-run-btn")
            expect(run_btn).to_be_visible()
            with page.expect_response(
                lambda r: r.url.endswith(f"/api/user/search/{search_name}/run") and r.request.method == "POST",
                timeout=620000,
            ) as run_info:
                run_btn.click()
            run_resp = run_info.value
            assert run_resp.ok, f"run failed: {run_resp.status} {run_resp.text()}"
            request.addfinalizer(lambda: _delete_run_doc(search_name, dt.date.today().isoformat()))

            # After a successful run the app navigates back to the results view.
            page.wait_for_selector(
                "#results-panel .run-meta, #results-panel .empty-state",
                timeout=30000,
            )
            body_text = page.locator("#results-panel").inner_text()
            assert "Run failed" not in body_text, f"results panel shows a run failure: {body_text[:300]!r}"
        finally:
            context.close()


# ---------------------------------------------------------------------------
# 2. Premium-tier user: 2-per-day creation quota (generate+save, then clone)
# ---------------------------------------------------------------------------


class TestPremiumCreateQuota:
    """A premium synthetic user can create 2 searches in one UTC day via the
    UI (one generated+saved, one cloned from a public search), after which
    both the "+New search" button and sidebar Copy buttons show the disabled
    quota-reached state with the right message. The Copy button lands the
    user in the edit panel of a genuinely new, private clone."""

    def test_two_creates_reach_quota(self, browser, synthetic_user, request):
        user = synthetic_user("qatp_premium_probe@example.test", role="premium", display_name="QATP Premium Probe")
        context = _new_context(browser, user["cookie"])
        page = context.new_page()
        try:
            page.goto("/")
            page.wait_for_selector("#search-list li")

            new_btn = page.locator("#new-search-btn")
            expect(new_btn).to_be_visible()
            expect(new_btn).to_be_enabled()

            # Creation #1: generate + save via the UI form.
            new_btn.click()
            page.locator("#cs-title").fill("QATP Premium Probe Search 1")
            page.locator("#cs-desc").fill(
                "Synthetic QATP test search — do not action: a bathroom storage cabinet under $100."
            )
            with page.expect_response(
                lambda r: r.url.endswith("/api/user/search/generate") and r.request.method == "POST",
                timeout=60000,
            ) as gen_info:
                page.locator("#cs-generate-btn").click()
            name1 = gen_info.value.json()["search_name"]
            request.addfinalizer(lambda: fc.delete_search_config(name1))

            expect(page.locator("#cs-preview")).to_be_visible(timeout=30000)
            page.locator("#cs-save-btn").click()
            expect(page.locator("#cs-save-msg")).to_have_text("Saved.", timeout=15000)

            # Not at quota yet (1 of 2) — the button stays enabled.
            expect(page.locator("#new-search-btn")).to_be_enabled()

            page.locator("#cs-cancel-btn").click()

            # Creation #2: clone a public search via a sidebar Copy button.
            clone_btn = page.locator(".btn-clone").first
            expect(clone_btn).to_be_visible(timeout=15000)
            expect(clone_btn).to_be_enabled()
            with page.expect_response(
                lambda r: "/clone" in r.url and r.request.method == "POST",
                timeout=30000,
            ) as clone_info:
                clone_btn.click()
            clone_resp = clone_info.value
            assert clone_resp.ok, f"clone failed: {clone_resp.status} {clone_resp.text()}"
            name2 = clone_resp.json()["search_name"]
            request.addfinalizer(lambda: fc.delete_search_config(name2))
            assert name2 != name1, "clone must create a NEW search, not overwrite the first one"

            # Clicking Copy must land the user in the edit panel of the new
            # private clone (not e.g. the read-only results view).
            expect(page.locator(".breadcrumb-current")).to_contain_text("Editing", timeout=15000)
            expect(page.locator("#edit-title")).to_be_visible()

            page.locator("#edit-cancel-btn").click()

            # Now at quota (2 of 2): both affordances show the disabled state
            # with the quota-reached message.
            gated_new_btn = page.locator("#new-search-btn")
            expect(gated_new_btn).to_be_disabled(timeout=15000)
            assert gated_new_btn.get_attribute("title") == web_main.PREMIUM_DAILY_LIMIT_MSG

            gated_clone_btn = page.locator(".btn-clone").first
            expect(gated_clone_btn).to_be_disabled(timeout=15000)
            assert gated_clone_btn.get_attribute("title") == web_main.PREMIUM_DAILY_LIMIT_MSG
        finally:
            context.close()


# ---------------------------------------------------------------------------
# 3. Personal-layer redaction on a public search's results page
# ---------------------------------------------------------------------------


class TestPersonalLayerRedaction:
    """A public search's results page must hide "Your picks" (pinned finds)
    and the "Products like this" reference note from anyone but the owner,
    while still showing scores/matches to everyone. Folds in scenario 5 (the
    feedback-label copy) for the owner view, since it's the same rendered
    page and avoids a second real pipeline run."""

    def test_anonymous_does_not_see_personal_layers(self, browser, redaction_search):
        context = _new_context(browser)  # no cookie: genuinely anonymous
        page = context.new_page()
        try:
            page.goto(f"/{redaction_search['search_name']}")
            page.wait_for_selector("#results-panel .card", timeout=20000)
            body = page.locator("#results-panel").inner_text()
            assert "QATP Match Product" in body, "anonymous view is missing the match — scores/matches must show"
            # score 8.5 rounds to 9 (Math.round) in the score badge.
            assert "9" in page.locator("#results-panel .score-badge").first.inner_text()
            # .section-heading / .ref-note-label render with text-transform:
            # uppercase, so compare case-insensitively (see module docstring).
            body_lower = body.lower()
            assert "your picks" not in body_lower, "anonymous view leaked the owner's pinned finds section"
            assert "products like this" not in body_lower, "anonymous view leaked the owner's reference-products note"
        finally:
            context.close()

    def test_owner_sees_personal_layers_and_feedback_copy(self, browser, synthetic_user, redaction_search):
        user = synthetic_user(redaction_search["owner_email"], role="free", display_name="QATP Redaction Owner")
        context = _new_context(browser, user["cookie"])
        page = context.new_page()
        try:
            page.goto(f"/{redaction_search['search_name']}")
            page.wait_for_selector("#results-panel .card", timeout=20000)
            body = page.locator("#results-panel").inner_text()
            body_lower = body.lower()
            assert "QATP Match Product" in body
            assert "your picks" in body_lower, "owner view should show their pinned finds section"
            assert "products like this (your references):" in body_lower, "owner view should show the reference note"

            # Scenario 5: the per-result / run-notes feedback copy renders for
            # real in this owner-owned view (not just present in source).
            expect(page.locator(".feedback-label", has_text="Feedback on QATP Match Product")).to_be_visible()
            expect(page.locator(".feedback-label", has_text="Teach this search")).to_be_visible()
        finally:
            context.close()


# ---------------------------------------------------------------------------
# 4. Admin: password login, promote a user's role, verify it persists
# ---------------------------------------------------------------------------


class TestAdminPromoteUser:
    """Admin signs in with the real password form (per the verify skill),
    promotes a synthetic user's role via the Users tab UI, and the promotion
    persists across a fresh page load (a genuine server re-fetch, not just
    optimistic client state)."""

    def test_password_login_and_promote_role(self, browser, synthetic_user, request):
        admin_password = web_main._settings.admin_password
        if not admin_password:
            pytest.skip("ADMIN_PASSWORD not set — cannot exercise the admin password-login flow")

        target = synthetic_user("qatp_admin_promote_probe@example.test", role="free", display_name="QATP Promote Probe")

        context = _new_context(browser)
        page = context.new_page()
        try:
            page.goto("/admin/login")
            page.fill('input[name="password"]', admin_password)
            page.get_by_role("button", name="Sign in with password").click()
            page.wait_for_url(f"{BASE_URL}/admin")
            # admin.js's init() binds the #btn-users click listener only after
            # its first async fetch resolves — wait for that fetch's visible
            # side effect (the sidebar populating) before clicking Users, or
            # the click can land before the listener is attached.
            page.wait_for_selector("#admin-search-list li")

            page.get_by_role("button", name="Users", exact=True).click()
            row = page.locator("tr", has_text=target["email"])
            expect(row).to_be_visible(timeout=15000)
            role_select = row.locator(".role-select")
            expect(role_select).to_have_value("free")

            role_select.select_option("premium")
            expect(row.locator(".role-saved-msg")).to_have_text("Saved", timeout=15000)

            # Verify it persisted server-side: full page reload, re-fetch from scratch.
            page.reload()
            page.wait_for_url(f"{BASE_URL}/admin")
            page.wait_for_selector("#admin-search-list li")
            page.get_by_role("button", name="Users", exact=True).click()
            row_after_reload = page.locator("tr", has_text=target["email"])
            expect(row_after_reload).to_be_visible(timeout=15000)
            expect(row_after_reload.locator(".role-select")).to_have_value("premium")

            db_user = fc.get_user(target["email"])
            assert db_user is not None and db_user.get("role") == "premium", "role update did not persist in Firestore"
        finally:
            context.close()


# ---------------------------------------------------------------------------
# 4b. Regression: numeric criteria fields (max_price) must not crash the
# shared criteria-form edit renderer, in either the admin or user-facing UI.
# ---------------------------------------------------------------------------
# criteria-form.js's CRITERIA_FIELDS loop left non-array values un-stringified
# ("raw ?? \"\"" instead of "String(raw ?? \"\")"), so max_price — the one
# "number"-typed field in the manifest — reached esc() as a raw JS number.
# A truthy number defeats esc()'s "s || \"\"" falsy-guard (numbers have no
# .replace method), throwing "(s || \"\").replace is not a function" and
# aborting the whole renderConfigHeader(cfg) + renderEdit(cfg) + ... template
# literal before any of it is assigned — so the header never rendered either,
# not just the price field. Found via a real admin session on wax_coat
# (max_price: 500); reproduced here with synthetic data instead.


class TestEditPanelNumericField:
    """A search with a numeric max_price must open cleanly in the admin edit
    panel (shared rendering code with the user-facing edit panel — see
    criteria-form.js's CRITERIA_FIELDS loop)."""

    def test_admin_edit_panel_renders_max_price_without_crashing(self, browser, request):
        admin_password = web_main._settings.admin_password
        if not admin_password:
            pytest.skip("ADMIN_PASSWORD not set — cannot exercise the admin password-login flow")

        search_name = "qatp_numeric_field_probe"
        fc.save_search_config(
            {
                "search_name": search_name,
                "title": "QATP Numeric Field Probe",
                "active": True,
                "visibility": "private",
                "owner_id": "admin",
                "criteria": {"category": ["qatp synthetic widget"], "max_price": 500},
                "preferred_shops": [],
            }
        )
        request.addfinalizer(lambda: fc.delete_search_config(search_name))

        context = _new_context(browser)
        page = context.new_page()
        errs = []
        page.on("console", lambda msg: errs.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: errs.append(str(exc)))
        try:
            page.goto("/admin/login")
            page.fill('input[name="password"]', admin_password)
            page.get_by_role("button", name="Sign in with password").click()
            page.wait_for_url(f"{BASE_URL}/admin")
            page.wait_for_selector("#admin-search-list li")

            page.locator("#admin-search-list li", has_text="QATP Numeric Field Probe").click()
            expect(page.locator(".config-search-name")).to_have_text("QATP Numeric Field Probe", timeout=15000)
            expect(page.locator('input[name="max_price"]')).to_have_value("500")
            assert not errs, f"console/page errors while rendering the edit panel: {errs}"
        finally:
            context.close()


# ---------------------------------------------------------------------------
# 5. Feedback-label relabel sanity check — /feedback page heading
# ---------------------------------------------------------------------------
# The per-result "Feedback on <product>" / run-notes "Teach this search"
# halves of this scenario are covered above in TestPersonalLayerRedaction
# (owner view), where a real rendered results page with feedback UI already
# exists — no need for a second real pipeline run just to see that copy.


class TestSiteFeedbackPage:
    """The general /feedback page renders the "Site feedback" heading for real."""

    def test_site_feedback_heading_renders(self, browser):
        context = _new_context(browser)
        page = context.new_page()
        try:
            page.goto("/feedback")
            expect(page.locator("h1")).to_have_text("Site feedback")
        finally:
            context.close()


# ---------------------------------------------------------------------------
# 6. Edit-panel breadcrumb + in-place save (no full selectSearch() reload)
# ---------------------------------------------------------------------------
# Regression coverage for commit c6d75a9 ("fix: intuitive nav between results
# and edit-config panel"): both the create and edit panels now show a
# breadcrumb wired to the existing closeCreatePanel(), and saving an edit no
# longer calls selectSearch() / refetches /api/results or /api/search — it
# patches the criteria bar and document.title in place, leaving only the
# pre-existing /api/searches sidebar refresh. Reuses the redaction_search
# fixture (an owned search + run seeded directly via Firestore, no Gemini
# call) purely to make #edit-search-btn reachable through selectSearch.


class TestEditPanelBreadcrumbAndInPlaceSave:
    """Editing an existing search's config shows a breadcrumb naming which
    search is being edited, and saving patches the criteria bar / page title
    in place instead of doing a full selectSearch() reload."""

    def test_back_button_returns_to_results(self, browser, synthetic_user, redaction_search):
        user = synthetic_user(redaction_search["owner_email"], role="free", display_name="QATP Edit Owner")
        context = _new_context(browser, user["cookie"])
        page = context.new_page()
        try:
            page.goto(f"/{redaction_search['search_name']}")
            page.wait_for_selector("#results-panel .card", timeout=20000)

            expect(page.locator("#edit-search-btn")).to_be_visible()
            page.locator("#edit-search-btn").click()

            expect(page.locator(".breadcrumb-current")).to_have_text('Editing "QATP Redaction Probe"', timeout=15000)
            expect(page.locator("#results-panel")).to_be_hidden()
            expect(page.locator("#create-panel")).to_be_visible()

            page.locator("#edit-panel-back-btn").click()

            expect(page.locator("#results-panel")).to_be_visible()
            expect(page.locator("#create-panel")).to_be_hidden()
        finally:
            context.close()

    def test_save_patches_in_place_without_refetch(self, browser, synthetic_user, redaction_search):
        user = synthetic_user(redaction_search["owner_email"], role="free", display_name="QATP Edit Owner 2")
        context = _new_context(browser, user["cookie"])
        page = context.new_page()
        try:
            page.goto(f"/{redaction_search['search_name']}")
            page.wait_for_selector("#results-panel .card", timeout=20000)

            page.locator("#edit-search-btn").click()
            expect(page.locator(".breadcrumb-current")).to_contain_text("Editing", timeout=15000)

            new_title = "QATP Redaction Probe Edited"
            page.locator("#edit-title").fill(new_title)

            # Track requests only from here on — the edit panel's own initial
            # GET /api/user/search/{name} (to load the editable config) has
            # already happened and is not part of what the save handler does.
            requests_during_save: list[str] = []
            page.on("request", lambda r: requests_during_save.append(f"{r.method} {r.url}"))

            with page.expect_response(
                lambda r: "/api/user/search/" in r.url and r.request.method == "PUT",
                timeout=15000,
            ):
                page.locator("#edit-save-btn").click()

            # Sync point: document.title only flips to the new title via the
            # in-place patch at the very end of the save handler, so waiting
            # for it means every request the handler makes has already fired.
            expect(page).to_have_title(f"{new_title} — TailoredLoop", timeout=15000)

            assert not any(
                "/api/results/" in u for u in requests_during_save
            ), f"save re-fetched results: {requests_during_save}"
            assert not any(
                "/api/search/" in u for u in requests_during_save
            ), f"save re-fetched the public search-config endpoint: {requests_during_save}"
            assert any(
                u.endswith("/api/searches") for u in requests_during_save
            ), f"save should still refresh the sidebar via GET /api/searches: {requests_during_save}"

            expect(page.locator("#create-panel")).to_be_hidden()
            expect(page.locator("#results-panel")).to_be_visible()
            expect(page.locator("#criteria-bar")).to_be_visible()
        finally:
            context.close()

    def test_new_search_panel_breadcrumb(self, browser, synthetic_user):
        user = synthetic_user(
            "qatp_new_search_breadcrumb@example.test", role="free", display_name="QATP New Search Breadcrumb"
        )
        context = _new_context(browser, user["cookie"])
        page = context.new_page()
        try:
            page.goto("/")
            page.wait_for_selector("#search-list")

            new_btn = page.locator("#new-search-btn")
            expect(new_btn).to_be_visible()
            new_btn.click()

            expect(page.locator(".breadcrumb-current")).to_have_text("New search", timeout=15000)
            back_btn = page.locator("#cs-panel-back-btn")
            expect(back_btn).to_be_visible()
            expect(back_btn).to_be_enabled()

            back_btn.click()

            expect(page.locator("#create-panel")).to_be_hidden()
        finally:
            context.close()
