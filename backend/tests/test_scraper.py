import socket

import pytest

import scraper
from scraper import ScrapeError


@pytest.mark.parametrize("value,expected", [
    ("https://example.com/a", True),
    ("http://x.org", True),
    ("  https://example.com  ", True),
    ("ftp://example.com", False),
    ("example.com", False),
    ("just a note", False),
])
def test_is_url(value, expected):
    assert scraper.is_url(value) is expected


@pytest.mark.parametrize("url,expected", [
    ("https://github.com/psf/requests", "repo"),
    ("https://arxiv.org/abs/1706.03762", "paper"),
    ("https://example.com/paper.pdf", "paper"),
    ("https://www.youtube.com/watch?v=x", "video"),
    ("https://docs.python.org/3/", "documentation"),
    ("https://example.com/docs/intro", "documentation"),
    ("https://example.com/blog/post", "article"),
])
def test_detect_content_type_from_url(url, expected):
    assert scraper.detect_content_type(url) == expected


def test_detect_content_type_text():
    assert scraper.detect_content_type(None, "short") == "note"
    assert scraper.detect_content_type(None, "x" * 700) == "text"


def test_domain_strips_www():
    assert scraper.domain_of("https://www.Example.com/x") == "example.com"


HTML = """
<html><head><title>Fallback</title><meta property="og:title" content="Real Title">
<meta name="description" content="A description."></head>
<body>
  <nav>Home | About</nav>
  <div class="cookie-banner">Accept cookies</div>
  <article><h1>Heading</h1><p>The actual article content lives here.</p>
  <div class="related-posts">Other stuff</div></article>
  <footer>Copyright</footer>
  <script>alert(1)</script>
</body></html>
"""


def test_parse_html_strips_boilerplate():
    out = scraper.parse_html(HTML, "https://www.example.com/post")
    assert out.title == "Real Title"
    assert "actual article content" in out.text
    for junk in ("Home | About", "Accept cookies", "Other stuff", "Copyright", "alert"):
        assert junk not in out.text
    assert out.source == "example.com"
    # short body: the meta description is prepended
    assert out.text.startswith("A description.")


def test_parse_text_title_and_note():
    out = scraper.parse_text("# My idea\nsome details\nsome details")
    assert out.title == "My idea"
    assert out.content_type == "note"
    assert out.text.count("some details") == 1  # repeated lines collapsed


def test_parse_text_empty():
    assert scraper.parse_text("   ").title == "Untitled note"


# --- SSRF guard --------------------------------------------------------------
def _fake_resolve(ip):
    def resolver(host, port, *a, **kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 80))]
    return resolver


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254",
                                "0.0.0.0", "::1", "fc00::1", "::ffff:127.0.0.1"])
def test_blocks_non_public(monkeypatch, ip):
    monkeypatch.setattr(scraper, "ALLOW_PRIVATE_URLS", False)
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve(ip))
    with pytest.raises(ScrapeError, match="non-public"):
        scraper.check_url_allowed("http://internal.test/")


def test_allows_public(monkeypatch):
    monkeypatch.setattr(scraper, "ALLOW_PRIVATE_URLS", False)
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolve("93.184.216.34"))
    scraper.check_url_allowed("https://example.com/")


def test_opt_out_allows_private(monkeypatch):
    monkeypatch.setattr(scraper, "ALLOW_PRIVATE_URLS", True)
    scraper.check_url_allowed("http://localhost:8080/")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://x", "http://"])
def test_rejects_bad_schemes(url):
    with pytest.raises(ScrapeError):
        scraper.check_url_allowed(url)


class _Resp:
    def __init__(self, location=None, url=""):
        self.headers = {"location": location} if location else {"content-type": "text/html"}
        self.is_redirect = location is not None
        self.url = url

    def close(self):
        pass


def test_redirect_to_private_is_blocked(monkeypatch):
    monkeypatch.setattr(scraper, "ALLOW_PRIVATE_URLS", False)
    ips = {"public.test": "93.184.216.34", "evil.test": "127.0.0.1"}
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda h, p, *a, **k: [(socket.AF_INET, 1, 6, "", (ips[h], 80))])
    monkeypatch.setattr(scraper.requests, "get",
                        lambda url, **kw: _Resp(location="http://evil.test/admin"))
    with pytest.raises(ScrapeError, match="non-public"):
        scraper._fetch("http://public.test/")


def test_too_many_redirects(monkeypatch):
    monkeypatch.setattr(scraper, "check_url_allowed", lambda u: None)
    monkeypatch.setattr(scraper.requests, "get", lambda url, **kw: _Resp(location="/again"))
    with pytest.raises(ScrapeError, match="Too many redirects"):
        scraper._fetch("http://public.test/")
