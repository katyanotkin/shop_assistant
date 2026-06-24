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

import httpx
import pytest

PROD_URL = os.environ.get("PROD_URL", "").rstrip("/")

REDIRECT_CODES = (301, 302, 303, 307, 308)

# A syntactically-valid search name that will not exist. Deliberately avoids
# Firestore's reserved __name__ pattern so we exercise the genuine 404 path.
UNKNOWN_SEARCH = "no_such_search_qa_probe"

# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------


def _skip():
    if not PROD_URL:
        pytest.skip("PROD_URL not set — skipping live QATP tests")


def _get(path: str, *, follow_redirects: bool = True, timeout: int = 15) -> httpx.Response:
    _skip()
    return httpx.get(PROD_URL + path, follow_redirects=follow_redirects, timeout=timeout)


def _post(path: str, *, timeout: int = 15) -> httpx.Response:
    _skip()
    return httpx.post(PROD_URL + path, follow_redirects=False, timeout=timeout)


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
