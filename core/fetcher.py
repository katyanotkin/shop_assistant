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


def fetch_page(url: str, timeout: float = DEFAULT_FETCH_TIMEOUT) -> tuple[str, str]:
    """Returns (final_url, text) — final_url is the URL after following redirects."""
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers=_HEADERS)
        final_url = str(r.url)
        if r.status_code != 200:
            print(f"    fetch failed ({r.status_code}): {url}")
            return final_url, ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        return final_url, text[:_MAX_TEXT_CHARS]
    except Exception as e:
        print(f"    fetch failed ({type(e).__name__}: {e}): {url}")
        return url, ""


def fetch_page_text(url: str, timeout: float = DEFAULT_FETCH_TIMEOUT) -> str:
    _, text = fetch_page(url, timeout=timeout)
    return text
