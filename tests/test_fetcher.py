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
        url, text = fetch_page("https://redirect.example.com/xyz")
    assert url == final
    assert "Product" in text


def test_fetch_page_returns_original_url_on_exception():
    with patch("httpx.get", side_effect=Exception("network error")):
        url, text = fetch_page("https://example.com")
    assert url == "https://example.com"
    assert text == ""


def test_fetch_page_returns_final_url_on_non_200():
    with patch("httpx.get", return_value=_mock_response(404, "Not Found", url="https://real.com/404")):
        url, text = fetch_page("https://redirect.example.com")
    assert url == "https://real.com/404"
    assert text == ""
