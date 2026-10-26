"""Caddyfile.prod xatti-harakati: probe'lar yopiq, API proksi, tana limiti, xavfsizlik sarlavhalari,
TLS versiyalari, HTTP→HTTPS, SPA fallback, kesh sarlavhalari, ichki health tashqaridan yopiq.
Faqat stdlib. Chiqish kodi: 0 — hammasi to'g'ri, 1 — xatolar ro'yxati chiqariladi."""

from __future__ import annotations

import http.client
import os
import re
import socket
import ssl
import sys
import time

DEV = os.environ.get("PROBE_TARGET") == "dev"
HOST = "caddy"
NAME = "caddy" if DEV else "ugk.test"
PORT = 443 if DEV else 8443
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; "
    "base-uri 'none'; form-action 'self'"
)
FORCE_BROWSE = (
    "/.git/config", "/.git/HEAD", "/.env", "/.gitignore", "/deploy/compose.prod.yml",
    "/backend/app/core/config.py", "/src/main.tsx", "/package.json", "/.DS_Store",
    "/%2e%2e/etc/passwd", "/assets/../.git/config", "/\\.git/config", "/%5c.git/config",
    "/.well-known/.git/config",
)
failures: list[str] = []


def _ctx(version: ssl.TLSVersion | None = None) -> ssl.SSLContext:
    # Sertifikat va nom TO'LIQ tekshiriladi: ishonch langari — certgen yaratgan sinov sertifikati.
    if DEV:  # dev: `tls internal` — CA ishonchli emas, faqat yo'l xatti-harakati tekshiriladi
        return ssl._create_unverified_context()  # noqa: S323, SLF001
    ctx = ssl.create_default_context(cafile="/certs/tls_cert")
    if version is not None:
        ctx.minimum_version = version
        ctx.maximum_version = version
    return ctx


class _Conn(http.client.HTTPSConnection):
    """caddy:8443 ga ulanadi, lekin SNI va Host — ugk.test."""

    def connect(self) -> None:
        sock = socket.create_connection((HOST, PORT), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=NAME)


def https(method: str, path: str, body: bytes | None = None) -> tuple[int, dict[str, str], bytes]:
    conn = _Conn(NAME, PORT, context=_ctx(), timeout=10)
    try:
        conn.request(method, path, body=body, headers={"Host": NAME})
        resp = conn.getresponse()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, resp.read()
    finally:
        conn.close()


def expect(name: str, condition: bool, detail: object = "") -> None:
    print(("OK   " if condition else "FAIL ") + name + (f" — {detail}" if not condition else ""))
    if not condition:
        failures.append(name)


def wait_ready() -> None:
    for _ in range(60):
        try:
            https("GET", "/")
            return
        except OSError:
            time.sleep(1)
    print("FAIL caddy 60 s ichida tayyor bo'lmadi")
    sys.exit(1)


def force_browse() -> None:
    # Force-browsing (rezolyutsiya 05-29-02/5323): hech qachon 200 va hech qachon SPA index emas.
    _, _, index = https("GET", "/")
    for path in FORCE_BROWSE:
        status, _, fbody = https("GET", path)
        expect(f"force-browse {path}", status in (403, 404) and fbody != index
               and b'id="root"' not in fbody, status)


def main() -> int:
    wait_ready()
    if DEV:
        force_browse()
        print(f"Jami xato: {len(failures)}")
        return 1 if failures else 0

    for probe in ("/api/v1/healthz", "/api/v1/readyz"):
        status, _, body = https("GET", probe)
        expect(f"{probe} tashqaridan 404", status == 404 and not body.startswith(b"stub"), status)

    status, headers, body = https("GET", "/api/v1/auth/me")
    expect("/api proksi", status == 200 and body == b"stub GET /api/v1/auth/me", (status, body[:60]))
    expect("API Content-Disposition", headers.get("content-disposition") == 'attachment; filename="api.json"',
           headers.get("content-disposition"))

    status, _, _ = https("POST", "/api/v1/auth/login", body=b"x" * (1536 * 1024))
    expect("tana > 1 MB → 413", status == 413, status)

    status, headers, body = https("GET", "/")
    expect("/ → 200 text/html", status == 200 and headers.get("content-type", "").startswith("text/html"), status)
    expect("CSP", headers.get("content-security-policy") == CSP, headers.get("content-security-policy"))
    expect("HSTS", headers.get("strict-transport-security") == "max-age=63072000; includeSubDomains")
    expect("nosniff", headers.get("x-content-type-options") == "nosniff")
    expect("X-Frame-Options", headers.get("x-frame-options") == "DENY")
    expect("Referrer-Policy", headers.get("referrer-policy") == "no-referrer")
    expect("Server sarlavhasi yo'q", "server" not in headers, headers.get("server"))
    expect("index.html no-cache", headers.get("cache-control") == "no-cache", headers.get("cache-control"))

    asset = re.search(rb"(/assets/[^\"']+\.js)", body)
    expect("index.html asset ko'rsatadi", asset is not None)
    status, headers, _ = https("GET", asset.group(1).decode() if asset else "/assets/none.js")
    expect("asset immutable", status == 200 and "immutable" in headers.get("cache-control", ""), status)
    status, _, _ = https("GET", "/assets/nope.js")
    expect("yo'q asset → 404", status == 404, status)
    status, _, body = https("GET", "/deep/link")
    expect("SPA fallback", status == 200 and b'id="root"' in body, status)

    for version in (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3):
        with socket.create_connection((HOST, 8443), 10) as raw, _ctx(version).wrap_socket(
            raw, server_hostname=NAME
        ) as tls:
            cipher = tls.cipher()
            aead = cipher is not None and ("GCM" in cipher[0] or "CHACHA20" in cipher[0])
            expect(f"{version.name} AEAD", aead, cipher)

    _, headers, _ = https("GET", "/api/v1/auth/me")
    expect("API: Via sarlavhasi yo'q", "via" not in headers, headers.get("via"))
    status, headers, _ = https("GET", "//evil.com/x")
    expect("// → 308 /", status == 308 and headers.get("location") == "/",
           (status, headers.get("location")))
    status, headers, _ = https("GET", "/assets/nope.js")
    expect("Caddy xatosi: CSP + no-store", headers.get("content-security-policy") == CSP
           and headers.get("cache-control") == "no-store", headers.get("cache-control"))
    status, headers, _ = https("POST", "/api/v1/auth/login", body=b"x" * (1536 * 1024))
    expect("413: CSP + no-store", status == 413 and headers.get("content-security-policy") == CSP
           and headers.get("cache-control") == "no-store", (status, headers.get("cache-control")))

    force_browse()

    for probe in ("/api/v1/healthz/", "/api/v1/healthz;x", "/api/v1/healthz%2f", "/api/v1/readyz/",
                  "/api/v1//healthz", "/api//v1/healthz", "/api/v1//readyz"):
        status, _, fbody = https("GET", probe)
        expect(f"probe variant {probe}", status == 404 and not fbody.startswith(b"stub"), status)

    # I1: notanish Host / SNI'siz — bo'sh 200 emas.
    for host in ("evil.test", "10.0.0.1"):
        plain = http.client.HTTPConnection(HOST, 8080, timeout=10)
        plain.request("GET", "/x?y=1", headers={"Host": host})
        resp = plain.getresponse()
        expect(f"8080 Host={host} → 308 UGK_DOMAIN", resp.status == 308
               and resp.getheader("Location") == f"https://{NAME}/x?y=1",
               (resp.status, resp.getheader("Location")))
        plain.close()
    conn = _Conn(NAME, PORT, context=_ctx(), timeout=10)
    conn.request("GET", "/", headers={"Host": "evil.test"})
    resp = conn.getresponse()
    expect("8443 Host=evil.test → 421 + sarlavhalar", resp.status == 421
           and resp.getheader("Content-Security-Policy") == CSP and resp.getheader("Server") is None,
           (resp.status, resp.getheader("Server")))
    conn.close()
    nosni = ssl.create_default_context(cafile="/certs/tls_cert")
    nosni.check_hostname = False
    with socket.create_connection((HOST, PORT), 10) as raw, nosni.wrap_socket(raw) as tls:
        san = (tls.getpeercert() or {}).get("subjectAltName")
        expect("SNI'siz handshake → domen sertifikati", san == (("DNS", NAME),), san)

    plain = http.client.HTTPConnection(HOST, 8080, timeout=10)
    plain.request("GET", "/x?y=1", headers={"Host": NAME})
    resp = plain.getresponse()
    expect("HTTP → HTTPS 308", resp.status == 308 and resp.getheader("Location") == f"https://{NAME}/x?y=1",
           (resp.status, resp.getheader("Location")))
    plain.close()

    try:
        socket.create_connection((HOST, 8081), 3).close()
        expect("8081 tashqaridan yopiq", False, "ulanish muvaffaqiyatli")
    except OSError:
        expect("8081 tashqaridan yopiq", True)

    print(f"Jami xato: {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
