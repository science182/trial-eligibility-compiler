"""Local web UI. Standard library only.

Flask is installed on this machine, but a judge cloning the repo may not have
it. `http.server` removes the install step and one demo failure mode, and a
single-user local demo needs nothing more.

    python3 ui/app.py     ->  http://localhost:8000

The compiled corpus loads once at startup, so a query is evaluation only.
"""

import json
import sys
import time
from datetime import date, datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data" / "eval"))
STATIC = Path(__file__).resolve().parent / "static"

from loader import load_corpus  # noqa: E402
from service import assess_payload as _assess  # noqa: E402
from service import parse_local_date, rebase_persona  # noqa: E402

print("loading compiled corpus ...", flush=True)
_t0 = time.time()
COMPILED, META = load_corpus()
print(f"  {len(COMPILED)} trials, "
      f"{sum(len(v) for v in COMPILED.values())} criteria "
      f"in {time.time() - _t0:.1f}s", flush=True)

from personas import PERSONAS  # noqa: E402


def assess_payload(report, index_date):
    """The payload lives in src/service.py -- see the note there."""
    return _assess(COMPILED, META, report, index_date)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    def log_message(self, fmt, *args):
        pass                                   # quiet during the demo

    def end_headers(self):
        # No caching, ever. This server exists to be edited and reloaded, and a
        # browser serving yesterday's app.js from cache during a rehearsal is a
        # failure mode with no error message.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/samples":
            # Rebased to the visitor's own today, so the dates they see are
            # real ones in their timezone rather than the server's.
            q = parse_qs(urlparse(self.path).query)
            today = parse_local_date((q.get("today") or [None])[0])
            return self._json([
                {"key": k, "name": r["name"], "report": r["report"],
                 "index_date": r["index_date"].isoformat()}
                for k, v in PERSONAS.items()
                for r in (rebase_persona(v, today),)
            ])
        if path == "/api/pulse":
            # Answered so the local page behaves like the deployed one, but the
            # local server counts nothing: there is no store behind it and a
            # developer reloading a page is not a statistic.
            return self._json({"configured": False, "totals": {}, "daily": [],
                               "sources": {}, "days": 30})
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/pulse":
            self.send_response(204)
            self.end_headers()
            return
        if path != "/api/assess":
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad JSON"}, 400)

        report = (req.get("report") or "").strip()
        if not report:
            return self._json({"error": "empty report"}, 400)
        raw = req.get("index_date")
        try:
            idx = datetime.strptime(raw, "%Y-%m-%d").date() if raw else date.today()
        except ValueError:
            idx = date.today()
        try:
            return self._json(assess_payload(report, idx))
        except Exception as e:                        # noqa: BLE001
            # The page must render something rather than showing a dead spinner.
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)


def main(port=8000):
    print(f"\n  http://localhost:{port}\n")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
