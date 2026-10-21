import pytest

from app import codes
from app.useragent import device, referrer_host


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://donstu.ru/abitur/", "https://donstu.ru/abitur/"),
        ("donstu.ru/abitur", "https://donstu.ru/abitur"),
        ("  http://example.com  ", "http://example.com"),
    ],
)
def test_normalize_accepts(raw, expected):
    assert codes.normalize_url(raw, "sho.rt") == expected


@pytest.mark.parametrize("raw", ["", "javascript:alert(1)", "ftp://files.example.com", "https://sho.rt/abc", "not a url", "https://nodot"])
def test_normalize_rejects(raw):
    with pytest.raises(codes.BadUrl):
        codes.normalize_url(raw, "sho.rt")


def test_random_codes_avoid_lookalike_characters():
    sample = "".join(codes.random_code(50) for _ in range(40))
    assert not set(sample) & set("0O1lI")


@pytest.mark.parametrize("alias", ["abitur", "vi14-raspisanie", "Den_Otkrytyh_Dverey"])
def test_alias_ok(alias):
    assert codes.is_valid_alias(alias)


@pytest.mark.parametrize("alias", ["ab", "-start", "с-кириллицей", "api", "DOCS", "a" * 40, "has space"])
def test_alias_rejected(alias):
    assert not codes.is_valid_alias(alias)


def test_token_hashing():
    token = codes.new_token()
    assert codes.tokens_match(token, codes.hash_token(token))
    assert not codes.tokens_match(token + "x", codes.hash_token(token))


@pytest.mark.parametrize(
    ("ua", "kind"),
    [
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X)", "mobile"),
        ("Mozilla/5.0 (Linux; Android 16; Pixel 9)", "mobile"),
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 15_6) AppleWebKit/605.1.15", "desktop"),
        ("TelegramBot (like TwitterBot)", "bot"),
        ("curl/8.9", "bot"),
        (None, "bot"),
    ],
)
def test_device(ua, kind):
    assert device(ua) == kind


def test_referrer_host():
    assert referrer_host("https://www.vk.com/feed?w=1") == "vk.com"
    assert referrer_host(None) is None
