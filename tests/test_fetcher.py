from unittest.mock import MagicMock, patch

import httpx

from core.fetcher import fetch_page, fetch_page_text


def _mock_response(status_code: int, text: str, url: str = "https://example.com") -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.url = url
    return r


def test_fetch_page_text_returns_text_on_200():
    html = "<html><body><p>Hello world</p></body></html>"
    with patch("httpx.get", return_value=_mock_response(200, html)):
        result = fetch_page_text("https://example.com")
    assert "Hello world" in result


def test_fetch_page_text_returns_empty_on_404():
    with patch("httpx.get", return_value=_mock_response(404, "Not Found")):
        result = fetch_page_text("https://example.com")
    assert result == ""


def test_fetch_page_text_returns_empty_on_500():
    with patch("httpx.get", return_value=_mock_response(500, "Server Error")):
        result = fetch_page_text("https://example.com")
    assert result == ""


def test_fetch_page_text_returns_empty_on_timeout():
    with patch("httpx.get", side_effect=httpx.TimeoutException("timed out")):
        result = fetch_page_text("https://example.com")
    assert result == ""


def test_fetch_page_text_returns_empty_on_connection_error():
    with patch("httpx.get", side_effect=Exception("connection refused")):
        result = fetch_page_text("https://example.com")
    assert result == ""


def test_fetch_page_text_strips_script_tags():
    html = "<html><body><p>Useful text</p><script>alert('bad')</script></body></html>"
    with patch("httpx.get", return_value=_mock_response(200, html)):
        result = fetch_page_text("https://example.com")
    assert "Useful text" in result
    assert "alert" not in result


def test_fetch_page_text_strips_style_tags():
    html = "<html><head><style>body { color: red; }</style></head><body><p>Content</p></body></html>"
    with patch("httpx.get", return_value=_mock_response(200, html)):
        result = fetch_page_text("https://example.com")
    assert "Content" in result
    assert "color: red" not in result


def test_fetch_page_text_strips_nav_tags():
    html = "<html><body><nav>Menu items</nav><p>Main content</p></body></html>"
    with patch("httpx.get", return_value=_mock_response(200, html)):
        result = fetch_page_text("https://example.com")
    assert "Main content" in result
    assert "Menu items" not in result


def test_fetch_page_text_strips_footer_tags():
    html = "<html><body><p>Product info</p><footer>Copyright 2024</footer></body></html>"
    with patch("httpx.get", return_value=_mock_response(200, html)):
        result = fetch_page_text("https://example.com")
    assert "Product info" in result
    assert "Copyright 2024" not in result


def test_fetch_page_text_truncates_long_content():
    long_text = "A" * 5000
    html = f"<html><body><p>{long_text}</p></body></html>"
    with patch("httpx.get", return_value=_mock_response(200, html)):
        result = fetch_page_text("https://example.com")
    assert len(result) <= 3500


# --- fetch_page ---


def test_fetch_page_returns_final_url_after_redirect():
    html = "<html><body><p>Product</p></body></html>"
    final = "https://real-shop.com/product"
    with patch("httpx.get", return_value=_mock_response(200, html, url=final)):
        url, text, alternates = fetch_page("https://redirect.example.com/xyz")
    assert url == final
    assert "Product" in text
    assert alternates == []


def test_fetch_page_returns_original_url_on_exception():
    with patch("httpx.get", side_effect=Exception("network error")):
        url, text, alternates = fetch_page("https://example.com")
    assert url == "https://example.com"
    assert text == ""
    assert alternates == []


def test_fetch_page_returns_final_url_on_non_200():
    with patch("httpx.get", return_value=_mock_response(404, "Not Found", url="https://real.com/404")):
        url, text, alternates = fetch_page("https://redirect.example.com")
    assert url == "https://real.com/404"
    assert text == ""
    assert alternates == []


# --- fetch_page: hreflang alternates ---


def test_fetch_page_collects_hreflang_alternates():
    html = """<html><head>
      <link rel="canonical" href="https://shop.com/us/products/coat">
      <link rel="alternate" href="https://shop.com/products/coat" hreflang="en-GB">
      <link rel="alternate" href="https://shop.com/us/products/coat" hreflang="en-US">
    </head><body><p>Coat</p></body></html>"""
    final = "https://shop.com/us/products/coat"
    with patch("httpx.get", return_value=_mock_response(200, html, url=final)):
        _, _, alternates = fetch_page("https://shop.com/us/products/coat")
    assert "https://shop.com/products/coat" in alternates
    assert "https://shop.com/us/products/coat" in alternates


def test_fetch_page_resolves_relative_alternate_hrefs():
    html = """<html><head>
      <link rel="alternate" href="/products/coat" hreflang="en-GB">
    </head><body><p>Coat</p></body></html>"""
    final = "https://shop.com/us/products/coat"
    with patch("httpx.get", return_value=_mock_response(200, html, url=final)):
        _, _, alternates = fetch_page("https://shop.com/us/products/coat")
    assert alternates == ["https://shop.com/products/coat"]


def test_fetch_page_ignores_alternate_links_without_hreflang():
    """rel="alternate" is also used for RSS feeds etc. — only hreflang-tagged
    ones are locale mirrors of this same page."""
    html = """<html><head>
      <link rel="alternate" type="application/rss+xml" href="https://shop.com/feed.xml">
    </head><body><p>Coat</p></body></html>"""
    with patch("httpx.get", return_value=_mock_response(200, html)):
        _, _, alternates = fetch_page("https://shop.com/products/coat")
    assert alternates == []


def test_fetch_page_ignores_cross_domain_alternates():
    """This is untrusted third-party HTML — a page must not be able to
    declare an "alternate" pointing at some unrelated site and have that URL
    treated as already-seen by the caller's dedup set."""
    html = """<html><head>
      <link rel="alternate" href="https://shop.com/products/coat" hreflang="en-GB">
      <link rel="alternate" href="https://evil.example.com/unrelated-product" hreflang="en-US">
    </head><body><p>Coat</p></body></html>"""
    final = "https://shop.com/products/coat"
    with patch("httpx.get", return_value=_mock_response(200, html, url=final)):
        _, _, alternates = fetch_page("https://shop.com/products/coat")
    assert alternates == ["https://shop.com/products/coat"]


def test_fetch_page_caps_number_of_alternates():
    links = "".join(f'<link rel="alternate" href="https://shop.com/p/{i}" hreflang="en-{i}">' for i in range(50))
    html = f"<html><head>{links}</head><body><p>Coat</p></body></html>"
    with patch("httpx.get", return_value=_mock_response(200, html, url="https://shop.com/products/coat")):
        _, _, alternates = fetch_page("https://shop.com/products/coat")
    assert len(alternates) <= 20
