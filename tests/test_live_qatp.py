"""
Live QATP (quality-assurance test plan) against a running deployment.

Run with:
    PROD_URL=https://shopassistant.verbboard.com pytest tests/test_live_qatp.py -v

All tests are skipped automatically when PROD_URL is not set.

Design principle: these tests verify *contracts* and *user-visible outcomes*,
never implementation details. They check HTTP status codes, JSON shape,
redirect behaviour, content-type headers, and coarse HTML structure. They do
NOT assert on specific CSS class names, JS identifiers, or hard-coded search
names — those change during normal refactoring and must not break the suite.
Search-specific assertions discover a real search at runtime via /api/searches.

Uses httpx so that follow_redirects can be controlled precisely per request.
"""

import os
import re

import httpx
import pytest

PROD_URL = os.environ.get("PROD_URL", "").rstrip("/")

REDIRECT_CODES = (301, 302, 303, 307, 308)

# A syntactically-valid search name that will not exist. Deliberately avoids
# Firestore's reserved __name__ pattern so we exercise the genuine 404 path.
UNKNOWN_SEARCH = "no_such_search_qa_probe"

# Allowed visibility values the public /api/searches endpoint may return.
VISIBILITY_VALUES = {"public", "private", "common"}

# Pattern for a run-date string as returned by /api/results/<name>.
RUN_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------


def _skip():
    if not PROD_URL:
        pytest.skip("PROD_URL not set — skipping live QATP tests")


def _get(path: str, *, follow_redirects: bool = True, timeout: int = 15) -> httpx.Response:
    _skip()
    return httpx.get(PROD_URL + path, follow_redirects=follow_redirects, timeout=timeout)


def _post(path: str, *, json: dict | None = None, timeout: int = 15) -> httpx.Response:
    _skip()
    return httpx.post(PROD_URL + path, json=json, follow_redirects=False, timeout=timeout)


def _put(path: str, *, json: dict | None = None, timeout: int = 15) -> httpx.Response:
    _skip()
    return httpx.put(PROD_URL + path, json=json, follow_redirects=False, timeout=timeout)


def _is_json(resp: httpx.Response) -> bool:
    return "application/json" in resp.headers.get("content-type", "")


def _looks_like_html(body: str) -> bool:
    low = body.lower()
    return "<html" in low and "</html>" in low


@pytest.fixture(scope="module")
def discovered_search():
    """Discover a real search name from the live API.

    Returns the name of the first search exposed by /api/searches, or skips the
    dependent test if none exist. This keeps search-detail tests generic rather
    than hard-coding a name like "wax_coat".
    """
    _skip()
    resp = httpx.get(PROD_URL + "/api/searches", timeout=15)
    if resp.status_code != 200:
        pytest.skip(f"/api/searches returned {resp.status_code}; cannot discover a search")
    data = resp.json()
    if not isinstance(data, list) or not data:
        pytest.skip("No searches available to test /api/search/<name> against")
    name = data[0].get("name")
    if not name:
        pytest.skip("First search entry has no 'name' field to test against")
    return name


@pytest.fixture(scope="module")
def discovered_run(discovered_search):
    """Discover the most recent run date for the discovered search.

    Hits /api/results/<discovered_search> and returns the first date string,
    or skips if no run dates exist yet for that search.
    """
    _skip()
    resp = httpx.get(PROD_URL + f"/api/results/{discovered_search}", timeout=15)
    if resp.status_code != 200:
        pytest.skip(f"/api/results/{discovered_search} returned {resp.status_code}; cannot discover a run date")
    dates = resp.json()
    if not isinstance(dates, list) or not dates:
        pytest.skip(f"No run dates available for search '{discovered_search}'")
    return dates[0]


# ---------------------------------------------------------------------------
# 1. Public HTML pages — status + coarse structure
# ---------------------------------------------------------------------------


class TestPublicHTMLPages:
    """Public HTML routes must return 200 and serve a real HTML document."""

    @pytest.mark.parametrize("path", ["/", "/privacy", "/terms"])
    def test_returns_200(self, path):
        resp = _get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"

    @pytest.mark.parametrize("path", ["/", "/privacy", "/terms"])
    def test_content_type_is_html(self, path):
        resp = _get(path)
        assert "text/html" in resp.headers.get(
            "content-type", ""
        ), f"{path} content-type is not text/html: {resp.headers.get('content-type')!r}"

    @pytest.mark.parametrize("path", ["/", "/privacy", "/terms"])
    def test_is_well_formed_html(self, path):
        body = _get(path).text
        assert _looks_like_html(body), f"{path} did not return a well-formed HTML document"

    @pytest.mark.parametrize("path", ["/", "/privacy", "/terms"])
    def test_has_title_tag(self, path):
        body = _get(path).text
        assert "<title>" in body.lower(), f"{path} HTML missing a <title> tag"

    @pytest.mark.parametrize("path", ["/", "/privacy", "/terms"])
    def test_body_is_non_trivial(self, path):
        body = _get(path).text
        assert len(body) > 200, f"{path} HTML is suspiciously short ({len(body)} bytes)"


class TestSpaCatchAll:
    """The catch-all route must serve the SPA shell, not a hard 404."""

    def test_arbitrary_path_serves_spa_shell(self):
        resp = _get("/some_unlikely_path_" + "x" * 8)
        assert resp.status_code == 200, f"catch-all returned {resp.status_code}; expected 200 (SPA shell)"

    def test_spa_shell_is_html(self):
        resp = _get("/some_unlikely_path_" + "x" * 8)
        assert _looks_like_html(resp.text), "catch-all did not return an HTML document"

    def test_discovered_search_page_serves_html(self, discovered_search):
        resp = _get("/" + discovered_search)
        assert resp.status_code == 200, f"/{discovered_search} returned {resp.status_code}; expected 200"
        assert _looks_like_html(resp.text), f"/{discovered_search} did not return HTML"


# ---------------------------------------------------------------------------
# 2. Static assets & manifest — served, not 404
# ---------------------------------------------------------------------------


class TestStaticSurface:
    """The static mount and manifest must be reachable.

    We probe the static mount generically rather than asserting specific
    filenames exist; a missing-but-mounted asset returns 404 while an
    unmounted prefix would behave differently. We only assert the manifest
    contract, which is a stable route.
    """

    def test_manifest_returns_200(self):
        resp = _get("/manifest.json")
        assert resp.status_code == 200, f"/manifest.json returned {resp.status_code}"

    def test_manifest_content_type(self):
        resp = _get("/manifest.json")
        ct = resp.headers.get("content-type", "")
        assert "manifest" in ct or "json" in ct, f"/manifest.json content-type unexpected: {ct!r}"

    def test_manifest_is_valid_json(self):
        resp = _get("/manifest.json")
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"/manifest.json is not valid JSON: {exc}")
        assert isinstance(data, dict), "/manifest.json did not parse to a JSON object"

    def test_static_mount_is_present(self):
        """A request under /static for a missing file should 404 (mount exists),
        not return the SPA shell. This verifies the static mount is wired up
        without depending on any particular asset filename."""
        resp = _get("/static/__definitely_missing__.nope")
        assert (
            resp.status_code == 404
        ), f"/static/<missing> returned {resp.status_code}; expected 404 from the static mount"


# ---------------------------------------------------------------------------
# 3. JSON API — /api/searches
# ---------------------------------------------------------------------------


class TestApiSearches:
    """GET /api/searches must return a JSON array of search summary objects."""

    def test_returns_200(self):
        resp = _get("/api/searches")
        assert resp.status_code == 200, f"/api/searches returned {resp.status_code}"

    def test_content_type_is_json(self):
        resp = _get("/api/searches")
        assert _is_json(resp), "/api/searches content-type is not JSON"

    def test_body_is_json_array(self):
        data = _get("/api/searches").json()
        assert isinstance(data, list), f"/api/searches body is not a JSON array; got {type(data)}"

    def test_entries_have_name_field(self):
        """Each entry must carry a 'name' the UI can route to. We assert only
        the field the API contract guarantees, not optional metadata."""
        data = _get("/api/searches").json()
        for i, item in enumerate(data):
            assert isinstance(item, dict), f"/api/searches item[{i}] is not an object: {item!r}"
            assert "name" in item and item["name"], f"/api/searches item[{i}] missing a non-empty 'name': {item}"


# ---------------------------------------------------------------------------
# A. /api/searches — visibility field
# ---------------------------------------------------------------------------


class TestApiSearchesVisibility:
    """Every search entry returned by GET /api/searches must expose a
    'visibility' field with a recognised value."""

    def test_entries_have_visibility_field(self):
        data = _get("/api/searches").json()
        if not isinstance(data, list) or not data:
            pytest.skip("/api/searches returned an empty list — nothing to assert")
        for i, item in enumerate(data):
            assert "visibility" in item, f"/api/searches item[{i}] is missing the 'visibility' field: {item!r}"

    def test_visibility_values_are_known(self):
        data = _get("/api/searches").json()
        if not isinstance(data, list) or not data:
            pytest.skip("/api/searches returned an empty list — nothing to assert")
        for i, item in enumerate(data):
            v = item.get("visibility")
            assert v in VISIBILITY_VALUES, (
                f"/api/searches item[{i}] has unrecognised visibility {v!r}; "
                f"expected one of {sorted(VISIBILITY_VALUES)}"
            )


# ---------------------------------------------------------------------------
# 4. JSON API — /api/search/<name> (discovered at runtime)
# ---------------------------------------------------------------------------


class TestApiSearchDetail:
    """GET /api/search/<name> contract, tested against a discovered search."""

    def test_returns_200(self, discovered_search):
        resp = _get("/api/search/" + discovered_search)
        assert resp.status_code == 200, f"/api/search/{discovered_search} returned {resp.status_code}"

    def test_content_type_is_json(self, discovered_search):
        resp = _get("/api/search/" + discovered_search)
        assert _is_json(resp), f"/api/search/{discovered_search} content-type is not JSON"

    def test_has_expected_shape(self, discovered_search):
        data = _get("/api/search/" + discovered_search).json()
        for field in ("search_name", "criteria", "preferred_shops"):
            assert field in data, f"/api/search/{discovered_search} missing '{field}': {data}"

    def test_search_name_matches_request(self, discovered_search):
        data = _get("/api/search/" + discovered_search).json()
        assert data.get("search_name") == discovered_search, (
            f"/api/search/{discovered_search} returned search_name " f"{data.get('search_name')!r}"
        )

    def test_nonexistent_search_returns_404(self):
        resp = _get("/api/search/" + UNKNOWN_SEARCH)
        assert resp.status_code == 404, f"/api/search/<missing> returned {resp.status_code}; expected 404"

    def test_nonexistent_search_404_is_json(self):
        resp = _get("/api/search/" + UNKNOWN_SEARCH)
        assert _is_json(resp), "/api/search/<missing> 404 response is not JSON"


# ---------------------------------------------------------------------------
# 5. JSON API — /api/me (anonymous)
# ---------------------------------------------------------------------------


class TestApiMe:
    """GET /api/me for an anonymous client must report an anonymous identity."""

    def test_returns_200(self):
        resp = _get("/api/me")
        assert resp.status_code == 200, f"/api/me returned {resp.status_code}"

    def test_content_type_is_json(self):
        resp = _get("/api/me")
        assert _is_json(resp), "/api/me content-type is not JSON"

    def test_anonymous_identity(self):
        data = _get("/api/me").json()
        assert data.get("anonymous") is True, f"/api/me anonymous flag is {data.get('anonymous')!r}; expected True"
        assert "role" in data, f"/api/me missing 'role': {data}"


# ---------------------------------------------------------------------------
# 6. Auth routes
# ---------------------------------------------------------------------------


class TestAuthRoutes:
    """Auth endpoints must behave correctly for unauthenticated requests."""

    def test_login_redirects_or_unconfigured(self):
        """GET /auth/login redirects to the IdP (3xx) or reports 503 when OAuth
        is not configured. Either is an acceptable contract."""
        resp = _get("/auth/login", follow_redirects=False)
        assert resp.status_code in REDIRECT_CODES + (
            503,
        ), f"/auth/login returned {resp.status_code}; expected a redirect or 503"

    def test_logout_returns_200(self):
        resp = _post("/auth/logout")
        assert resp.status_code == 200, f"POST /auth/logout returned {resp.status_code}"

    def test_logout_acknowledges(self):
        data = _post("/auth/logout").json()
        assert data.get("ok") is True, f"POST /auth/logout body is {data!r}; expected ok=true"


# ---------------------------------------------------------------------------
# D. /auth/login — OAuth configured: must redirect to Google
# ---------------------------------------------------------------------------


class TestAuthLoginOAuth:
    """Now that OAuth is configured in production, /auth/login must issue a
    redirect whose Location header points to accounts.google.com."""

    def test_login_is_a_redirect(self):
        resp = _get("/auth/login", follow_redirects=False)
        assert resp.status_code in REDIRECT_CODES, (
            f"GET /auth/login returned {resp.status_code}; expected a 3xx redirect. " "OAuth may not be configured."
        )

    def test_login_redirects_to_google(self):
        resp = _get("/auth/login", follow_redirects=False)
        location = resp.headers.get("location", "")
        assert "accounts.google.com" in location, (
            f"GET /auth/login Location header is {location!r}; " "expected it to contain 'accounts.google.com'"
        )


# ---------------------------------------------------------------------------
# 7. Admin protection — guarded routes must not leak to anonymous clients
# ---------------------------------------------------------------------------


class TestAdminProtection:
    """Admin surfaces must redirect or reject unauthenticated access."""

    def test_admin_page_redirects(self):
        resp = _get("/admin", follow_redirects=False)
        assert (
            resp.status_code in REDIRECT_CODES
        ), f"/admin returned {resp.status_code}; expected a redirect for anonymous user"

    def test_admin_page_does_not_serve_200(self):
        resp = _get("/admin", follow_redirects=False)
        assert resp.status_code != 200, "/admin served 200 without auth — not protected"

    def test_admin_me_reports_not_admin(self):
        resp = _get("/api/admin/me")
        assert resp.status_code == 200, f"/api/admin/me returned {resp.status_code}"
        assert resp.json().get("admin") is False, "/api/admin/me reports admin=true for an anonymous client"

    @pytest.mark.parametrize("path", ["/api/admin/searches", "/api/admin/search/anything"])
    def test_guarded_api_rejects_anonymous(self, path):
        resp = _get(path, follow_redirects=False)
        assert resp.status_code in (
            401,
            403,
        ), f"{path} returned {resp.status_code} for anonymous client; expected 401/403"


# ---------------------------------------------------------------------------
# B. /api/results/{search_name} — run-date list
# ---------------------------------------------------------------------------


class TestApiResultsDates:
    """GET /api/results/<name> must return a JSON array of date strings."""

    def test_returns_200(self, discovered_search):
        resp = _get(f"/api/results/{discovered_search}")
        assert resp.status_code == 200, f"/api/results/{discovered_search} returned {resp.status_code}"

    def test_content_type_is_json(self, discovered_search):
        resp = _get(f"/api/results/{discovered_search}")
        assert _is_json(resp), f"/api/results/{discovered_search} content-type is not JSON"

    def test_body_is_json_array(self, discovered_search):
        data = _get(f"/api/results/{discovered_search}").json()
        assert isinstance(data, list), f"/api/results/{discovered_search} body is not a JSON array; got {type(data)}"

    def test_entries_look_like_dates(self, discovered_search):
        """Every element in the array must be a YYYY-MM-DD date string."""
        data = _get(f"/api/results/{discovered_search}").json()
        if not data:
            pytest.skip(f"No run dates returned for '{discovered_search}' — nothing to validate")
        for i, entry in enumerate(data):
            assert isinstance(entry, str) and RUN_DATE_RE.match(entry), (
                f"/api/results/{discovered_search} item[{i}] {entry!r} " "does not match YYYY-MM-DD"
            )

    def test_unknown_search_returns_404(self):
        resp = _get(f"/api/results/{UNKNOWN_SEARCH}")
        assert resp.status_code == 404, f"/api/results/<missing> returned {resp.status_code}; expected 404"


# ---------------------------------------------------------------------------
# C. /api/results/{search_name}/{run_date} — run result shape
# ---------------------------------------------------------------------------


class TestApiResultsRunDetail:
    """GET /api/results/<name>/<date> must return a well-shaped result object."""

    def test_returns_200(self, discovered_search, discovered_run):
        resp = _get(f"/api/results/{discovered_search}/{discovered_run}")
        assert resp.status_code == 200, f"/api/results/{discovered_search}/{discovered_run} returned {resp.status_code}"

    def test_content_type_is_json(self, discovered_search, discovered_run):
        resp = _get(f"/api/results/{discovered_search}/{discovered_run}")
        assert _is_json(resp), f"/api/results/{discovered_search}/{discovered_run} content-type is not JSON"

    def test_body_is_json_object(self, discovered_search, discovered_run):
        data = _get(f"/api/results/{discovered_search}/{discovered_run}").json()
        assert isinstance(data, dict), (
            f"/api/results/{discovered_search}/{discovered_run} body is not a JSON object; " f"got {type(data)}"
        )

    def test_has_matches_key(self, discovered_search, discovered_run):
        data = _get(f"/api/results/{discovered_search}/{discovered_run}").json()
        assert "matches" in data, (
            f"/api/results/{discovered_search}/{discovered_run} missing 'matches' key: " f"{list(data.keys())}"
        )
        assert isinstance(data["matches"], list), f"'matches' should be a list; got {type(data['matches'])}"

    def test_has_partial_matches_key(self, discovered_search, discovered_run):
        data = _get(f"/api/results/{discovered_search}/{discovered_run}").json()
        assert "partial_matches" in data, (
            f"/api/results/{discovered_search}/{discovered_run} missing 'partial_matches' key: " f"{list(data.keys())}"
        )
        assert isinstance(
            data["partial_matches"], list
        ), f"'partial_matches' should be a list; got {type(data['partial_matches'])}"

    def test_match_items_have_required_fields(self, discovered_search, discovered_run):
        """Each item in 'matches' and 'partial_matches' must carry at minimum
        url, score, and title (title may be null but the key must be present)."""
        data = _get(f"/api/results/{discovered_search}/{discovered_run}").json()
        required = {"url", "score", "title"}
        for list_key in ("matches", "partial_matches"):
            items = data.get(list_key, [])
            for i, item in enumerate(items):
                missing = required - set(item.keys())
                assert not missing, (
                    f"/api/results/{discovered_search}/{discovered_run} "
                    f"{list_key}[{i}] missing fields {missing}: {item!r}"
                )


# ---------------------------------------------------------------------------
# E. PUT /api/feedback/{search_name}/{run_date}/batch — admin protected
# ---------------------------------------------------------------------------


class TestFeedbackBatchProtection:
    """PUT /api/feedback/<name>/<date>/batch must reject unauthenticated callers."""

    def test_rejects_anonymous_with_dummy_date(self, discovered_search):
        """Use a future dummy date (2099-01-01) so the auth check fires before
        any date-validation logic that might 404 on unknown dates."""
        resp = _put(
            f"/api/feedback/{discovered_search}/2099-01-01/batch",
            json={},
        )
        assert resp.status_code in (401, 403), (
            f"PUT /api/feedback/{discovered_search}/2099-01-01/batch "
            f"returned {resp.status_code} for anonymous client; expected 401/403"
        )


# ---------------------------------------------------------------------------
# F. POST /api/admin/run/{name} — admin protected
# ---------------------------------------------------------------------------


class TestAdminRunProtection:
    """POST /api/admin/run/<name> must reject unauthenticated callers."""

    def test_rejects_anonymous(self):
        resp = _post("/api/admin/run/anything")
        assert resp.status_code in (401, 403), (
            f"POST /api/admin/run/anything returned {resp.status_code} " "for anonymous client; expected 401/403"
        )


# ---------------------------------------------------------------------------
# G. POST /api/admin/search/generate — admin protected
# ---------------------------------------------------------------------------


class TestAdminSearchGenerateProtection:
    """POST /api/admin/search/generate must reject unauthenticated callers."""

    def test_rejects_anonymous(self):
        resp = _post("/api/admin/search/generate", json={})
        assert resp.status_code in (401, 403), (
            f"POST /api/admin/search/generate returned {resp.status_code} " "for anonymous client; expected 401/403"
        )
