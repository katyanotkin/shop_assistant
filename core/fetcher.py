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


def fetch_page_text(url: str, timeout: float = 12.0) -> str:
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers=_HEADERS)
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        return text[:_MAX_TEXT_CHARS]
    except Exception:
        return ""
