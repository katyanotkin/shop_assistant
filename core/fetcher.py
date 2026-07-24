from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 " "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
_MAX_TEXT_CHARS = 3500
DEFAULT_FETCH_TIMEOUT = 8.0
_MAX_ALTERNATE_URLS = 20


def _alternate_urls(soup: BeautifulSoup, final_url: str) -> list[str]:
    """Locale/language mirrors of this exact page, declared via
    <link rel="alternate" hreflang="..."> — the standard i18n SEO convention.

    Many international shops (Rydale among them) serve the same product at
    several locale-prefixed paths (e.g. /products/x and /us/products/x) with
    no redirect between them and a self-referencing <link rel="canonical">
    on each, so canonical alone can't catch the duplicate — hreflang alternates
    are the mechanism that actually ties the variants together.

    This is untrusted third-party HTML, so two guards apply: alternates are
    restricted to the same host as final_url (a page can't declare an
    "alternate" pointing at some unrelated site and get that URL treated as
    already-seen), and the result is capped (real hreflang blocks rarely
    exceed a handful of locales; an unbounded page could otherwise dump
    thousands of entries into the caller's dedup set).
    """
    host = urlparse(final_url).netloc
    urls = []
    for tag in soup.find_all("link", rel="alternate"):
        href = tag.get("href")
        if not href or not tag.get("hreflang"):
            continue
        resolved = urljoin(final_url, href)
        if urlparse(resolved).netloc != host:
            continue
        urls.append(resolved)
        if len(urls) >= _MAX_ALTERNATE_URLS:
            break
    return urls


def fetch_page(url: str, timeout: float = DEFAULT_FETCH_TIMEOUT) -> tuple[str, str, list[str]]:
    """Returns (final_url, text, alternate_urls) — final_url is the URL after
    following redirects; alternate_urls are other locale/language URLs this
    page declares as equivalent to itself (see `_alternate_urls`)."""
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers=_HEADERS)
        final_url = str(r.url)
        if r.status_code != 200:
            print(f"    fetch failed ({r.status_code}): {url}")
            return final_url, "", []
        soup = BeautifulSoup(r.text, "html.parser")
        alternates = _alternate_urls(soup, final_url)
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        return final_url, text[:_MAX_TEXT_CHARS], alternates
    except Exception as e:
        print(f"    fetch failed ({type(e).__name__}: {e}): {url}")
        return url, "", []


def fetch_page_text(url: str, timeout: float = DEFAULT_FETCH_TIMEOUT) -> str:
    _, text, _ = fetch_page(url, timeout=timeout)
    return text
