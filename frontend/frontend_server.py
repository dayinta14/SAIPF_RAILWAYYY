"""Server frontend SAIPF yang stabil untuk Windows.

Frontend: http://127.0.0.1:5510/index.html
Backend : http://127.0.0.1:8000

Port 5510 dipakai agar tidak bentrok dengan server lama pada port 5500.
"""
from __future__ import annotations

import http.client
import mimetypes
import posixpath
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

HOST = "127.0.0.1"
PORT = 5510
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
ROOT = Path(__file__).resolve().parent


class FrontendHandler(BaseHTTPRequestHandler):
    server_version = "SAIPFFrontendFix/2.0"

    def do_GET(self):  # noqa: N802
        self._route()

    def do_HEAD(self):  # noqa: N802
        self._route(head_only=True)

    def do_POST(self):  # noqa: N802
        self._route()

    def do_PUT(self):  # noqa: N802
        self._route()

    def do_DELETE(self):  # noqa: N802
        self._route()

    def do_PATCH(self):  # noqa: N802
        self._route()

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def _route(self, head_only: bool = False):
        parsed = urlsplit(self.path)
        path = unquote(parsed.path or "/")

        if path == "/frontend-health":
            payload = b'{"status":"ok","service":"saipf-frontend","port":5510}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if not head_only:
                self.wfile.write(payload)
            return

        if path == "/health" or path.startswith("/api/"):
            self._proxy_to_backend(head_only=head_only)
            return

        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        self._serve_static(path, head_only=head_only)

    def _proxy_to_backend(self, head_only: bool = False):
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else None
        headers = {}
        for name, value in self.headers.items():
            if name.lower() not in {"host", "connection", "accept-encoding", "content-length"}:
                headers[name] = value
        if body is not None:
            headers["Content-Length"] = str(len(body))

        connection = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=600)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            self.send_response(response.status, response.reason)
            for name, value in response.getheaders():
                if name.lower() not in {"transfer-encoding", "connection", "content-length", "content-encoding"}:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if not head_only:
                self.wfile.write(payload)
        except (ConnectionRefusedError, TimeoutError, OSError) as exc:
            payload = (
                '{"detail":"Backend SAIPF belum berjalan di http://127.0.0.1:8000. '
                'Jalankan START_BACKEND_FIX_TESSERACT.bat terlebih dahulu."}'
            ).encode("utf-8")
            self.send_response(502, "Backend unavailable")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if not head_only:
                self.wfile.write(payload)
            print(f"[PROXY ERROR] {exc}")
        finally:
            connection.close()

    def _serve_static(self, request_path: str, head_only: bool = False):
        path = request_path
        # Mendukung URL lama yang menyertakan nama folder.
        prefix = "/SAIPF_Frontend_HTML_CSS_JS/"
        if path.startswith(prefix):
            path = "/" + path[len(prefix):]

        if path in {"", "/"}:
            path = "/index.html"

        normalized = posixpath.normpath(path).lstrip("/")
        candidate = (ROOT / normalized).resolve()

        if ROOT not in candidate.parents and candidate != ROOT:
            self.send_error(403, "Forbidden")
            return

        if candidate.is_dir():
            candidate = candidate / "index.html"

        # Fallback ke index untuk route tanpa ekstensi.
        if not candidate.exists() and "." not in Path(normalized).name:
            candidate = ROOT / "index.html"

        if not candidate.exists() or not candidate.is_file():
            payload = (
                "<!doctype html><html><head><meta charset='utf-8'><title>SAIPF - File tidak ditemukan</title>"
                "<style>body{font-family:Arial;padding:40px;background:#f5f7fb}main{max-width:700px;margin:auto;background:white;padding:28px;border-radius:16px}code{background:#eef2f7;padding:3px 6px}</style>"
                "</head><body><main><h1>File frontend tidak ditemukan</h1>"
                "<p>Buka alamat <code>http://127.0.0.1:5510/index.html</code>.</p>"
                "<p>Pastikan <code>index.html</code>, folder <code>css</code>, dan folder <code>js</code> berada satu folder dengan <code>frontend_server.py</code>.</p>"
                "</main></body></html>"
            ).encode("utf-8")
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if not head_only:
                self.wfile.write(payload)
            return

        content = candidate.read_bytes()
        content_type, _ = mimetypes.guess_type(str(candidate))
        if not content_type:
            content_type = "application/octet-stream"
        self.send_response(200)
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        else:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        if not head_only:
            self.wfile.write(content)

    def log_message(self, fmt, *args):
        print(f"[FRONTEND] {self.address_string()} - {fmt % args}")


def main():
    required = [ROOT / "index.html", ROOT / "css" / "style.css", ROOT / "js" / "app.js"]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        print("[ERROR] File frontend tidak lengkap:")
        for item in missing:
            print(f"  - {item}")
        input("Tekan Enter untuk menutup...")
        return

    try:
        server = ThreadingHTTPServer((HOST, PORT), FrontendHandler)
    except OSError as exc:
        print(f"[ERROR] Port {PORT} tidak dapat digunakan: {exc}")
        print("Tutup server frontend lama lalu jalankan kembali.")
        input("Tekan Enter untuk menutup...")
        return

    print("=" * 66)
    print(" SAIPF FRONTEND FIX 404 BERJALAN")
    print(f" Frontend : http://{HOST}:{PORT}/index.html")
    print(f" Backend  : http://{BACKEND_HOST}:{BACKEND_PORT}/docs")
    print(" Jangan tutup jendela ini selama frontend digunakan.")
    print("=" * 66)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
