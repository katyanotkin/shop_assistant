"""
Smoke tests against a live deployment.

Run with:
    PROD_URL=https://your-app.example.com pytest tests/test_smoke.py -v

All tests are skipped automatically when PROD_URL is not set.
"""

import json
import os
import urllib.error
import urllib.request

import pytest

PROD_URL = os.environ.get("PROD_URL", "").rstrip("/")


def _get(path: str, *, follow_redirects: bool = True) -> tuple[int, str, str]:
    """Return (status_code, body_text, final_url).

    When follow_redirects=False the redirect response itself is returned.
    """
    url = PROD_URL + path
    if follow_redirects:
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace"), resp.url
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace"), url
    else:
        # Build a request that does NOT follow redirects
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: PLR0913
                return None

        opener = urllib.request.build_opener(_NoRedirect)
        try:
            with opener.open(url, timeout=15) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace"), resp.url
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace"), url


# ── helpers ───────────────────────────────────────────────────────────────────


def _skip_if_no_prod_url():
    if not PROD_URL:
        pytest.skip("PROD_URL not set — skipping smoke tests")


# ── tests ─────────────────────────────────────────────────────────────────────


def test_smoke_root_returns_200():
    _skip_if_no_prod_url()
    status, _, _ = _get("/")
    assert status == 200


def test_smoke_api_searches_returns_json_list():
    _skip_if_no_prod_url()
    status, body, _ = _get("/api/searches")
    assert status == 200
    data = json.loads(body)
    assert isinstance(data, list)


def test_smoke_admin_me_returns_not_logged_in():
    _skip_if_no_prod_url()
    status, body, _ = _get("/api/admin/me")
    assert status == 200
    data = json.loads(body)
    assert data == {"admin": False}


def test_smoke_admin_redirects():
    _skip_if_no_prod_url()
    # Try without following redirects first
    status, _, final_url = _get("/admin", follow_redirects=False)
    if status in (301, 302, 303, 307, 308):
        # Good — server sent a redirect
        return
    # If the client followed it anyway, verify we landed on root
    assert final_url.rstrip("/").endswith(PROD_URL.rstrip("/")) or final_url.endswith("/")
