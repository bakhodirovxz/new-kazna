import re

from app.core.middleware import HSTS, SECURITY_HEADERS
from tests.ops.repo import repo_path


def _caddy() -> str:
    return repo_path("deploy/caddy/Caddyfile.prod").read_text(encoding="utf-8")


def test_caddy_prod_basics() -> None:
    text = _caddy()
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for needle in (
        "admin off", "auto_https disable_redirects", "http_port 8080", "https_port 8443",
        "max_size 1MB", "tls /run/secrets/tls_cert /run/secrets/tls_key", "-Server", "-Via",
        "bind 127.0.0.1", "reverse_proxy api:8000", "handle_errors", "@dotseg",
    ):
        assert needle in text, needle
    assert "tls internal" not in code
    assert "acme" not in code.lower()  # izohlardan tashqari


def test_probes_blocked_before_api_proxy() -> None:
    text = _caddy()
    api = text.index("handle /api/*")
    for probe in ("/api/v1/healthz", "/api/v1/readyz"):
        match = re.search(r"handle " + re.escape(probe) + r" \{\s*respond 404\s*\}", text)
        assert match, probe
        assert match.start() < api, probe


def test_security_headers_match_backend() -> None:
    text = _caddy()
    for name, value in SECURITY_HEADERS.items():
        assert f'{name} "{value}"' in text, name
    assert f'Strict-Transport-Security "{HSTS}"' in text


def test_tls_only_modern_protocols() -> None:
    text = _caddy()
    assert "protocols tls1.2 tls1.3" in text
    match = re.search(r"ciphers ([^\n]+)", text)
    assert match
    ciphers = match.group(1).split()
    assert ciphers
    assert all(c.startswith("TLS_ECDHE_") and ("GCM" in c or "CHACHA20" in c) for c in ciphers)


def test_dotfile_matcher_before_spa_in_dev_and_prod() -> None:
    for name in ("Caddyfile.prod", "Caddyfile.dev"):
        text = repo_path(f"deploy/caddy/{name}").read_text(encoding="utf-8")
        assert "orig_uri.path}.matches" in text, name
        assert "not path /.well-known/*" in text, name
        assert text.index("handle @dotseg") < text.index("handle /api/*"), name
        assert text.index("handle @dotseg") < text.index("file_server"), name


def test_web_image_caddy_has_no_file_capability() -> None:
    # Yangi fayl sifatida yoziladi: cap_net_bind_service ko'chmaydi (cap_drop ALL: EPERM yo'q).
    text = repo_path("frontend/Dockerfile").read_text(encoding="utf-8")
    assert "COPY --from=caddy-build /caddy-nocap /usr/bin/caddy" in text
