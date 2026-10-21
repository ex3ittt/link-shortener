import hashlib
import re
import secrets
from urllib.parse import urlsplit

ALPHABET = "23456789abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"
"""Base57: no 0/O, 1/l/I — a code read aloud or retyped from a slide still works."""

# "javascript:…", "mailto:…" — but not "example.com:8080", where a port follows.
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:(?!\d)")

ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,31}$")

# Paths the app itself owns; an alias must never shadow them.
RESERVED = {"api", "docs", "redoc", "openapi.json", "static", "health", "favicon.ico", "robots.txt"}


def random_code(length: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def is_valid_alias(alias: str) -> bool:
    return bool(ALIAS.match(alias)) and alias.lower() not in RESERVED


def new_token() -> str:
    return secrets.token_urlsafe(24)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_match(token: str, token_hash: str) -> bool:
    return secrets.compare_digest(hash_token(token), token_hash)


class BadUrl(ValueError):
    pass


def normalize_url(raw: str, own_host: str) -> str:
    """Accepts what people paste ("example.com/page") and rejects what's unsafe."""
    url = raw.strip()
    if not url:
        raise BadUrl("пустая ссылка")
    if not SCHEME.match(url):
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise BadUrl("поддерживаются только http и https")
    host = (parts.hostname or "").lower()
    if not host or "." not in host and host != "localhost":
        raise BadUrl("не похоже на адрес сайта")
    if host == own_host.lower():
        # A short link to a short link is a redirect loop waiting to happen.
        raise BadUrl("это уже короткая ссылка")
    if len(url) > 4096:
        raise BadUrl("слишком длинная ссылка")
    return url
