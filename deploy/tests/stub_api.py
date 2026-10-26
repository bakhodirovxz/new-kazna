"""API o'rnini bosuvchi stub (Caddyfile.prod testi): tanani TO'LIQ o'qiydi (Caddy'ning `max_size`
cheklovi faqat tana o'qilganda ishlaydi — haqiqiy API ham o'qiydi), metod va yo'lni qaytaradi."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def _reply(self) -> None:
        remaining = int(self.headers.get("Content-Length") or 0)
        while remaining > 0:
            chunk = self.rfile.read(min(65536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
        body = f"stub {self.command} {self.path}".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _reply
    do_POST = _reply

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()  # noqa: S104 — sinov konteyneri
