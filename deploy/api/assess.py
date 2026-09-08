"""POST /api/assess -- run one report against the compiled corpus.

The corpus is read at module import, not per request, so a warm instance pays
only for extraction and evaluation. That is the whole claim of the system: the
reasoning happened once, offline, at compile time.
"""

import sys
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _counters  # noqa: E402
from _runtime import (corpus, quiet, rate_limited,  # noqa: E402
                      read_json, reply)
from service import assess_payload  # noqa: E402

# Long enough for a full multi-page note, short enough that the function is not
# a place to push bulk text at.
MAX_REPORT = 60_000


@quiet
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if rate_limited(self):
            return reply(self, {"error": "Too many requests. Wait a minute and "
                                         "try again."}, 429)
        req = read_json(self)
        if req is None:
            return reply(self, {"error": "expected a JSON body"}, 400)

        report = (req.get("report") or "").strip()
        if not report:
            return reply(self, {"error": "empty report"}, 400)
        if len(report) > MAX_REPORT:
            return reply(self, {"error": f"report exceeds {MAX_REPORT} "
                                         f"characters"}, 413)

        raw = req.get("index_date")
        try:
            idx = datetime.strptime(raw, "%Y-%m-%d").date() if raw else date.today()
        except (ValueError, TypeError):
            idx = date.today()

        try:
            compiled, meta = corpus()
            reply(self, assess_payload(compiled, meta, report, idx))
            # After the bytes are written, so the counter's round trip is not
            # in front of the visitor's result. Nothing about the report is
            # passed in -- this adds 1 to an integer and nothing else.
            _counters.record("match")
            return
        except Exception as e:                        # noqa: BLE001
            # The page must render something rather than showing a dead
            # spinner. The message carries the exception only -- never the
            # report, which would put clinical text into the platform's logs.
            return reply(self, {"error": f"{type(e).__name__}: {e}"}, 500)

    def do_GET(self):
        return reply(self, {"error": "POST a report to this endpoint"}, 405)
