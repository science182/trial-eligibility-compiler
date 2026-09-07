"""Exercise the deployment package before it goes anywhere.

Serves the built `public/` and routes /api/* to the real serverless handler
functions, so what is checked here is the code Vercel will run -- not a
re-implementation of it.

    python3 deploy/smoke.py            # assert, then exit
    python3 deploy/smoke.py --serve    # assert, then keep serving for the browser

The read-only-filesystem check is the one worth understanding. Vercel gives a
function a read-only filesystem outside /tmp, and `loader.load_corpus()`
recompiles and *writes* its cache on a miss. If `loader` ever appears in
sys.modules after a request, some import has pulled the corpus builder onto
the query path and the deployment will fail the first time the cache is cold.
"""

import json
import sys
from datetime import date
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
PUBLIC = HERE / "public"
sys.path.insert(0, str(HERE / "api"))

import assess as assess_fn  # noqa: E402
import samples as samples_fn  # noqa: E402

PORT = 8731
BASE = f"http://127.0.0.1:{PORT}"


class Dispatch(SimpleHTTPRequestHandler):
    """Vercel's file-system routing, locally: api/<name>.py -> /api/<name>."""

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(PUBLIC), **kw)

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/samples":
            return samples_fn.handler.do_GET(self)
        if path == "/api/assess":
            return assess_fn.handler.do_GET(self)
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path == "/api/assess":
            return assess_fn.handler.do_POST(self)
        self.send_error(404)


def get(path):
    with urllib.request.urlopen(BASE + path) as r:
        return r.status, r.read()


def post(path, obj, raw=None):
    body = raw if raw is not None else json.dumps(obj).encode()
    req = urllib.request.Request(BASE + path, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


CHECKS = []


def check(name):
    def wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return wrap


@check("the page serves and carries the use notice")
def _page():
    code, body = get("/")
    assert code == 200, code
    html = body.decode()
    assert "not medical advice" in html, "use notice missing from index.html"
    # Source-wrapped, so match a phrase that survives the line break.
    assert "Do not upload or paste" in html, "data-entry warning missing"
    assert "Trial Eligibility Compiler" in html


@check("static assets serve")
def _assets():
    for path in ("/app.js", "/style.css"):
        code, body = get(path)
        assert code == 200 and body, path
    assert b".notice" in get("/style.css")[1], "notice CSS not appended"


@check("/api/samples returns the persona without touching the corpus")
def _samples():
    code, body = get("/api/samples")
    assert code == 200, code
    rows = json.loads(body)
    assert rows and rows[0]["key"] == "maya_torres", rows
    assert "EGFR" in rows[0]["report"]


@check("/api/assess reproduces the demo state")
def _assess():
    rows = json.loads(get("/api/samples")[1])
    p = rows[0]
    code, out = post("/api/assess", {"report": p["report"],
                                     "index_date": p["index_date"]})
    assert code == 200, out
    counts = {}
    for t in out["trials"]:
        counts[t["state"]] = counts.get(t["state"], 0) + 1
    assert out["timing"]["model_calls"] == 0
    assert out["timing"]["trials"] == 500, out["timing"]
    # The figures the video script reads aloud.
    assert counts == {"eligible_now": 42, "eligible_on_date": 2,
                      "undetermined": 35, "blocked": 421}, counts

    blocked = next(t for t in out["trials"] if t["id"] == "NCT06357533")
    assert "EGFR" in (blocked["blocking_reason"] or ""), blocked["blocking_reason"]
    row = next(r for r in blocked["rows"] if r["type"] == "BIOMARKER"
               and r["cls"] == "bad")
    assert row["spans"], "provenance spans missing -- click-to-highlight is dead"

    # Asserted as an interval, not an absolute date. The persona is rebased to
    # today before it is served, so pinning a literal date here would fail every
    # day after it was written -- exactly the rot the rebasing exists to fix.
    dated = next(t for t in out["trials"] if t["id"] == "NCT06946927")
    idx = date.fromisoformat(out["patient"]["index_date"])
    opens = date.fromisoformat(dated["eligible_date"])
    assert (opens - idx).days == 11, f"{idx} -> {opens}"
    assert opens >= date.today(), f"served a past date: {opens}"


@check("bad input is refused without a stack trace")
def _bad_input():
    assert post("/api/assess", {"report": "   "})[0] == 400
    assert post("/api/assess", {}, raw=b"not json")[0] == 400
    assert post("/api/assess", {"report": "x" * 60_001})[0] == 413
    # A report with no recognisable content must still render, not 500.
    code, out = post("/api/assess", {"report": "Patient seen in clinic."})
    assert code == 200 and "trials" in out, out


@check("the rate limiter refuses a flood and lets normal use through")
def _rate_limit():
    # 60/minute, verified here against ONE process. In production Vercel spreads
    # a burst across instances and this does not fire -- measured: 70 requests,
    # 70x 200. Real protection is Vercel's firewall. See _runtime.py.
    body = {"report": "Patient seen in clinic."}
    codes = [post("/api/assess", body)[0] for _ in range(70)]
    assert codes[0] == 200, codes[0]
    assert 429 in codes, "a 70-request burst was never rate limited"
    assert codes.count(200) >= 55, f"limiter fired too early: {codes.count(200)}"


@check("legal pages ship and say the necessary things")
def _legal():
    for path, must in (
        ("/privacy.html", ["Do not upload identifiable patient data",
                           "not written to disk", "No cookies"]),
        ("/terms.html", ["Not medical advice", "not for patients",
                         "as is"]),
        ("/about.html", ["60.3%", "0.36"]),
    ):
        code, body = get(path)
        assert code == 200, f"{path} -> {code}"
        html = body.decode()
        for phrase in must:
            assert phrase in html, f"{path} missing: {phrase}"
    # The tool itself must reach them.
    home = get("/")[1].decode()
    for href in ("/privacy.html", "/terms.html", "/about.html"):
        assert href in home, f"home page does not link {href}"


@check("crawler and share metadata are present")
def _meta():
    home = get("/")[1].decode()
    for tag in ('og:title', 'og:description', 'name="description"',
                'rel="canonical"', 'favicon.svg'):
        assert tag in home, f"missing {tag}"
    assert get("/robots.txt")[0] == 200
    assert get("/sitemap.xml")[0] == 200
    assert get("/favicon.svg")[0] == 200


@check("the corpus builder never reaches the query path")
def _read_only():
    assert "loader" not in sys.modules, (
        "loader was imported -- load_corpus() writes its cache and will raise "
        "on Vercel's read-only filesystem")
    assert "llm" not in sys.modules, "llm writes a disk cache and a call log"
    assert "sklearn" not in sys.modules and "numpy" not in sys.modules, (
        "an eval-only dependency reached the runtime bundle")


def main():
    for required in (PUBLIC / "index.html", HERE / "runtime" / "corpus.pkl"):
        if not required.exists():
            sys.exit(f"missing {required.relative_to(HERE)} -- "
                     f"run `python3 deploy/build.py` first")

    srv = HTTPServer(("127.0.0.1", PORT), Dispatch)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    failed = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"  ok    {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}\n        {e}")

    size = sum(f.stat().st_size for f in HERE.rglob("*")
               if f.is_file() and "__pycache__" not in f.parts)
    print(f"\n  {len(CHECKS) - failed}/{len(CHECKS)} checks, "
          f"package {size / 1e6:.1f} MB")

    if "--serve" in sys.argv and not failed:
        print(f"\n  {BASE}   (ctrl-c to stop)")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    srv.shutdown()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
