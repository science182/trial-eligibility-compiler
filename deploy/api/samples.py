"""GET /api/samples -- the demo personas.

Deliberately does not touch the corpus. It is the first request the page makes,
and making it wait on a 2MB unpickle would put a cold start in front of an
empty screen.
"""

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _counters  # noqa: E402
from _runtime import quiet, reply  # noqa: E402
from personas import PERSONAS  # noqa: E402
from service import parse_local_date, rebase_persona  # noqa: E402


@quiet
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Rebased to today: the fixture is pinned to a fixed index date, and a
        # public demo that keeps announcing a date which has already passed
        # contradicts its own central claim.
        q = parse_qs(urlparse(self.path).query)
        today = parse_local_date((q.get("today") or [None])[0])
        reply(self, [
            {"key": k, "name": r["name"], "report": r["report"],
             "index_date": r["index_date"].isoformat()}
            for k, v in PERSONAS.items()
            for r in (rebase_persona(v, today),)
        ])
        _counters.record("doc")
