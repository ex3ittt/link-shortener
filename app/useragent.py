from urllib.parse import urlsplit

_BOTS = ("bot", "crawler", "spider", "preview", "facebookexternalhit", "telegrambot", "vkshare", "whatsapp", "curl", "wget", "python-requests", "httpx")
_MOBILE = ("iphone", "android", "mobile", "ipad", "ipod", "windows phone")


def device(user_agent: str | None) -> str:
    """Rough bucket: messenger link previews are counted separately from people."""
    ua = (user_agent or "").lower()
    if not ua or any(b in ua for b in _BOTS):
        return "bot"
    if any(m in ua for m in _MOBILE):
        return "mobile"
    return "desktop"


def referrer_host(referer: str | None) -> str | None:
    if not referer:
        return None
    host = (urlsplit(referer).hostname or "").lower()
    return host.removeprefix("www.")[:255] or None
