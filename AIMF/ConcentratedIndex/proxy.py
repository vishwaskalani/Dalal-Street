"""
ConcentratedIndex — Local Proxy Server
=======================================
Forwards Yahoo Finance requests from your browser with proper headers.
Uses only Python standard library — no pip installs needed.

Usage:
    python proxy.py

Then open ConcentratedIndex.html in your browser.
Keep this terminal running while using the dashboard.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.parse import urlparse, parse_qs, unquote
import sys

PORT = 5001

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://finance.yahoo.com/",
    "Origin":          "https://finance.yahoo.com",
}


class ProxyHandler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        # Health-check endpoint
        if parsed.path == "/health":
            self._respond(200, b'{"status":"ok"}')
            return

        if parsed.path != "/proxy":
            self._respond(404, b'{"error":"Not found"}')
            return

        params = parse_qs(parsed.query)
        if "url" not in params:
            self._respond(400, b'{"error":"Missing ?url= parameter"}')
            return

        target = unquote(params["url"][0])

        # Safety: only allow Yahoo Finance
        if "finance.yahoo.com" not in target:
            self._respond(403, b'{"error":"Only Yahoo Finance URLs are allowed"}')
            return

        try:
            req  = Request(target, headers=HEADERS)
            with urlopen(req, timeout=12) as resp:
                body = resp.read()
            self._respond(200, body)
            ticker = target.split("/chart/")[-1].split("?")[0] if "/chart/" in target else target
            print(f"  ✓  {ticker}")
        except Exception as exc:
            msg = str(exc).encode()
            print(f"  ✗  {target.split('?')[0]}  →  {exc}", file=sys.stderr)
            self._respond(502, b'{"error":"' + msg + b'"}')

    def _respond(self, code: int, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, *_):
        pass  # we handle our own printing


if __name__ == "__main__":
    server = HTTPServer(("localhost", PORT), ProxyHandler)
    print(f"\n  ConcentratedIndex Proxy")
    print(f"  Running on  →  http://localhost:{PORT}")
    print(f"  Health check →  http://localhost:{PORT}/health")
    print(f"\n  Open ConcentratedIndex.html in your browser.")
    print(f"  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Proxy stopped.")
        server.shutdown()
