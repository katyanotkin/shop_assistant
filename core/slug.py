import re
import unicodedata

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_length: int = 64) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = _NON_ALNUM_RE.sub("_", normalized.lower()).strip("_")
    slug = slug[:max_length].strip("_")
    return slug or "search"
