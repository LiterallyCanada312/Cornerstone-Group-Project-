"""Standalone room layout editor.

Serves room_layout_editor.html on localhost, opens it in the user's browser,
waits for the page to POST the exported JSON to /save, then exits.

Usage:
    python editor.py                              # writes to Rooms/layout.json
    python editor.py -o Rooms/felix_room.json    # custom output path
    python editor.py --port 9000                 # custom port
"""

import argparse
import http.server
import socketserver
import threading
import webbrowser
from pathlib import Path

EDITOR_DIR = Path(__file__).parent
EDITOR_HTML = EDITOR_DIR / "room_layout_editor.html"
DEFAULT_OUTPUT = EDITOR_DIR / "Rooms" / "layout.json"

PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Room Layout Editor</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/dist/tabler-icons.min.css">
<style>
:root {
  --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --color-background-primary: #ffffff;
  --color-background-secondary: #f3f3f3;
  --color-background-tertiary: #fafafa;
  --color-text-primary: #1a1a1a;
  --color-text-secondary: #666666;
  --color-text-danger: #c62828;
  --color-border-primary: #888888;
  --color-border-secondary: #cccccc;
  --color-border-tertiary: #e5e5e5;
  --border-radius-md: 4px;
  --border-radius-lg: 6px;
}
html, body { height: 100%; }
body { margin: 0; padding: 16px; background: #f7f7f7; font-family: var(--font-sans); }
.sr-only { position: absolute; left: -9999px; }
</style>
</head>
<body>
__FRAGMENT__
</body>
</html>
"""


def _build_page() -> bytes:
    fragment = EDITOR_HTML.read_text(encoding="utf-8")
    return PAGE_TEMPLATE.replace("__FRAGMENT__", fragment).encode("utf-8")


class _ReusableServer(socketserver.TCPServer):
    allow_reuse_address = True


def launch_editor(output_path: Path, port: int = 8765) -> Path:
    """Open the editor in a browser and block until the user exports JSON.

    Returns the path the JSON was written to.
    """
    if not EDITOR_HTML.exists():
        raise FileNotFoundError(f"Editor HTML not found: {EDITOR_HTML}")

    page = _build_page()
    saved = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args, **_kwargs):
            pass

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path != "/save":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", "0"))
            data = self.rfile.read(length)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(data)
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
            saved.set()

    httpd = _ReusableServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}/"
    print(f"  [editor] serving at {url}")
    print(f"  [editor] will write JSON to {output_path}")
    print(f"  [editor] (press Ctrl+C to cancel)")
    webbrowser.open(url)

    try:
        saved.wait()
    except KeyboardInterrupt:
        print("\n  [editor] cancelled.")
        httpd.shutdown()
        httpd.server_close()
        raise

    httpd.shutdown()
    httpd.server_close()
    print(f"  [editor] saved layout to {output_path}")
    return output_path


def main():
    ap = argparse.ArgumentParser(description="Room layout editor — saves a JSON layout file.")
    ap.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT),
                    help=f"Where to write the JSON (default: {DEFAULT_OUTPUT})")
    ap.add_argument("--port", type=int, default=8765, help="Local server port (default: 8765)")
    args = ap.parse_args()
    launch_editor(Path(args.output), port=args.port)


if __name__ == "__main__":
    main()
