"""/api/pulse -- the usage counters, written and read.

    POST  record one event   {"e": "visit", "r": "<referring URL>"}
    GET   read the counters  -> the same JSON /stats.html renders

The read side is deliberately public and unauthenticated. The whole point of
counting this way is that a visitor can check what is being counted; a private
dashboard would ask them to take the privacy page on trust instead. There is
nothing here but integers -- no visitor is identifiable in the response
because no visitor was identifiable in what was stored. See _counters.py.
"""

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _counters  # noqa: E402
from _runtime import quiet, read_json, reply  # noqa: E402

MAX_DAYS = 120


@quiet
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # 204 regardless of outcome. The client fires this with sendBeacon and
        # cannot act on a failure, so an error code would only mean a red line
        # in somebody's console for a counter that does not matter to them.
        req = read_json(self, limit=2000) or {}
        try:
            _counters.record(str(req.get("e") or ""), req.get("r"))
        except Exception:                             # noqa: BLE001
            pass
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):
        q = parse_qs(urlparse(self.path).query)
        try:
            days = int((q.get("days") or ["30"])[0])
        except ValueError:
            days = 30
        days = max(1, min(days, MAX_DAYS))
        try:
            return reply(self, _counters.report(days))
        except Exception as e:                        # noqa: BLE001
            return reply(self, {"error": f"{type(e).__name__}: {e}",
                                "configured": _counters.configured()}, 500)
