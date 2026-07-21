#!/usr/bin/env python3
"""Local preview server for the static marketing site — clean URLs, no build step.

Serves the repo root so /features resolves to features.html, / to index.html, and
real files (css/, dist/, data/) are served verbatim. Loopback only.

    python tools/serve-site.py [--port 8080]
"""
from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CleanURLHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        local = super().translate_path(path)
        p = Path(local)
        # /features -> features.html when the extension-less file has no dir/index.
        if not p.exists() and not p.suffix and (p.parent / f"{p.name}.html").exists():
            return str(p.parent / f"{p.name}.html")
        return local

    def end_headers(self) -> None:
        # No caching in preview, so edits show on reload.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    handler = functools.partial(CleanURLHandler, directory=str(ROOT))
    with socketserver.ThreadingTCPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"serving {ROOT} at http://localhost:{args.port}  (Ctrl-C to stop)")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
