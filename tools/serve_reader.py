#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.server
import ipaddress
import mimetypes
import posixpath
import socketserver
import urllib.parse
from pathlib import Path


ALLOWED_PATHS = {
    "/": "index.html",
    "/index.html": "index.html",
    "/styles.css": "styles.css",
    "/app.js": "app.js",
    "/data/search-index.json": "data/search-index.json",
    "/demo/search-index.json": "demo/search-index.json",
}

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


class ReaderHandler(http.server.BaseHTTPRequestHandler):
    server_version = "ChatArchiveReader/1.0"

    def do_GET(self) -> None:
        self.serve_allowed_file(send_body=True)

    def do_HEAD(self) -> None:
        self.serve_allowed_file(send_body=False)

    def serve_allowed_file(self, send_body: bool) -> None:
        if not self.is_allowed_host():
            self.send_error(403, "Forbidden")
            return

        parsed = urllib.parse.urlsplit(self.path)
        request_path = posixpath.normpath(urllib.parse.unquote(parsed.path))
        if request_path not in ALLOWED_PATHS:
            self.send_error(404, "Not found")
            return

        file_path = Path.cwd() / ALLOWED_PATHS[request_path]
        if not file_path.is_file():
            self.send_error(404, "Not found")
            return

        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", self.guess_content_type(file_path))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def is_allowed_host(self) -> bool:
        host_header = self.headers.get("Host", "")
        if not host_header:
            return False

        host = host_header.strip().lower()
        if host.startswith("["):
            end = host.find("]")
            hostname = host[1:end] if end != -1 else host
        else:
            hostname = host.split(":", 1)[0]
        return hostname in {"127.0.0.1", "localhost", "::1"}

    def guess_content_type(self, file_path: Path) -> str:
        if file_path.suffix == ".js":
            return "application/javascript; charset=utf-8"
        if file_path.suffix == ".css":
            return "text/css; charset=utf-8"
        if file_path.suffix == ".json":
            return "application/json; charset=utf-8"
        return mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"

    def end_headers(self) -> None:
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the local ChatGPT archive reader.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.host.lower() != "localhost":
        try:
            host_address = ipaddress.ip_address(args.host)
        except ValueError:
            print("For privacy, this reader only binds to loopback addresses.")
            print("Use 127.0.0.1, ::1, or localhost.")
            return 1
        if not host_address.is_loopback:
            print("For privacy, this reader only binds to loopback addresses.")
            print("Use 127.0.0.1, ::1, or localhost.")
            return 1

    root = Path.cwd()
    index_path = root / "data" / "search-index.json"
    demo_index_path = root / "demo" / "search-index.json"
    if not index_path.exists() and not demo_index_path.exists():
        print("No search index was found.")
        print("Run .\\build-index.cmd or keep demo\\search-index.json available.")
        return 1

    with socketserver.TCPServer((args.host, args.port), ReaderHandler) as httpd:
        print(f"Serving {root}")
        print(f"Open http://{args.host}:{args.port}")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
