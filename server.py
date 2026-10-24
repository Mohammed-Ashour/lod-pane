"""Developer-only loopback server for the Word task pane.

Word loads the pane from this process through a trusted localhost certificate.
The server has no hosted deployment and uses no third-party packages.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import ssl
from urllib.parse import parse_qs, urlsplit

import lodpane

WEB = Path(__file__).parent / "word"
ASSETS = {"/": ("index.html", "text/html"), "/word.html": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css"), "/icon.png": ("icon.png", "image/png"), "/help": ("../SETUP.md", "text/plain")}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Do not put selected words, document excerpts, or notes in access logs.
        pass

    def respond(self, status, body, content_type="application/json"):
        data = json.dumps(body, ensure_ascii=False).encode() if content_type == "application/json" else body
        self.send_response(status)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type != "image/png" else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' https://appsforoffice.microsoft.com; style-src 'self'; connect-src 'self' https://appsforoffice.microsoft.com; img-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self' https://*.office.com https://*.officeapps.live.com https://*.microsoft365.com https://*.cloud.microsoft")
        self.end_headers()
        self.wfile.write(data)

    def handle_request(self, method):
        expected = {"localhost:" + str(self.server.server_port), "127.0.0.1:" + str(self.server.server_port)}
        if self.headers.get("Host") not in expected:
            self.respond(403, {"error": "Local requests only."})
            return
        url = urlsplit(self.path)
        origin = self.headers.get("Origin")
        if origin and origin not in {"https://" + host for host in expected}:
            self.respond(403, {"error": "Origin not allowed."})
            return
        try:
            if url.path.startswith("/api/"):
                # Non-simple header blocks cross-origin browser reads and CSRF. No CORS.
                if self.headers.get("X-LOD-Pane") != "1":
                    self.respond(403, {"error": "Open LOD pane to use the local API."})
                    return
                payload = None
                if method == "POST":
                    if self.headers.get_content_type() != "application/json":
                        self.respond(415, {"error": "JSON required."})
                        return
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 12_000:
                        raise ValueError("Request is too large or empty.")
                    payload = json.loads(self.rfile.read(length))
                params = parse_qs(url.query)
                if method == "GET" and url.path == "/api/lookup":
                    result = lodpane.lookup(params.get("word", [""])[0])
                elif method == "GET" and url.path == "/api/entry":
                    result = {"entry": lodpane.entry(params.get("id", [""])[0])}
                elif method == "GET" and url.path == "/api/words":
                    result = lodpane.saved_words()
                elif method == "GET" and url.path == "/api/preferences":
                    result = lodpane.preferences()
                elif method == "POST" and url.path == "/api/preferences":
                    result = lodpane.preferences(payload)
                elif method == "POST" and url.path == "/api/save":
                    result = lodpane.save_word(payload)
                elif method == "POST" and url.path == "/api/delete":
                    if not isinstance(payload, dict):
                        raise ValueError("Invalid saved word.")
                    lodpane.delete_word(payload.get("key"), payload.get("baseUpdated"))
                    result = {"ok": True}
                else:
                    self.respond(404, {"error": "Not found."})
                    return
                self.respond(200, result)
            elif method == "GET" and url.path in ASSETS:
                filename, mime = ASSETS[url.path]
                self.respond(200, (WEB / filename).read_bytes(), mime)
            else:
                self.respond(404, {"error": "Not found."})
        except (ValueError, TypeError) as error:
            self.respond(400, {"error": str(error)})
        except lodpane.DictionaryUnavailable as error:
            self.respond(503, {"error": str(error)})
        except OSError:
            self.respond(500, {"error": "Cannot access local vocabulary. Check the data folder permissions; your note has not been discarded."})
        except Exception:
            self.respond(500, {"error": "Could not complete this request. Your note is still in the pane. Please try again."})

    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    certs = Path.home() / ".office-addin-dev-certs"
    parser.add_argument("--cert", type=Path, default=certs / "localhost.crt")
    parser.add_argument("--key", type=Path, default=certs / "localhost.key")
    parser.add_argument("--port", type=int, default=43127)
    args = parser.parse_args()
    if not args.cert.is_file() or not args.key.is_file():
        parser.error("Install the localhost certificate first: npx office-addin-dev-certs install. See SETUP.md.")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(args.cert), str(args.key))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print(f"Word companion at https://localhost:{args.port}. Keep this process running while using Word.")
    print("Vocabulary: " + str(lodpane.data_directory()))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
