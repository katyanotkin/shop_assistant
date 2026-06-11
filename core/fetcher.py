import httpx
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
_MAX_TEXT_CHARS = 3500


def fetch_page(url: str, timeout: float = 12.0) -> tuple[str, str]:
    """Returns (final_url, text) — final_url is the URL after following redirects."""
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers=_HEADERS)
        final_url = str(r.url)
        if r.status_code != 200:
            return final_url, ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        return final_url, text[:_MAX_TEXT_CHARS]
    except Exception:
        return url, ""


def fetch_page_text(url: str, timeout: float = 12.0) -> str:
    _, text = fetch_page(url, timeout=timeout)
    return text
