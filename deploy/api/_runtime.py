"""Shared serverless runtime: import paths, corpus loading, JSON replies.

Underscore-prefixed so Vercel treats it as a helper rather than a route.

Two things differ from the local server and both are consequences of where
this runs:

* The filesystem is read only. `loader.load_corpus()` recompiles and *writes*
  its cache on a miss, which would raise here, so the corpus is read straight
  from the pickle built by deploy/build.py. A missing or unreadable cache is a
  build failure and is reported as one rather than silently recompiling.
* Nothing is logged. The request body is a clinical note. It is held in memory
  for the length of one request, never written to disk, and never echoed into
  a log line -- including on the error path, where the temptation to log the
  input is strongest.
"""

import hashlib
import json
import pickle
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# The pickle holds `compile.Criterion` and friends, so those modules have to
# resolve at their original top-level names.
for p in (str(ROOT / "runtime"), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

CORPUS = ROOT / "runtime" / "corpus.pkl"

_loaded = None
_load_error = None


def corpus():
    """(compiled, meta), loaded once per warm instance."""
    global _loaded, _load_error
    if _loaded is None and _load_error is None:
        try:
            t0 = time.time()
            with CORPUS.open("rb") as f:
                _loaded = pickle.load(f)
            print(f"corpus loaded: {len(_loaded[0])} trials "
                  f"in {time.time() - t0:.2f}s", flush=True)
        except Exception as e:                        # noqa: BLE001
            _load_error = f"{type(e).__name__}: {e}"
    if _load_error:
        raise RuntimeError(f"compiled corpus unavailable ({_load_error}); "
                           f"run `python3 deploy/build.py` and redeploy")
    return _loaded


# ── rate limiting ────────────────────────────────────────────────────────
# MEASURED CAVEAT: this is close to useless in production, and it is kept only
# because it costs nothing and does bound a single hot instance.
#
# A 70-request burst against the deployed site returned 70x 200 -- the limiter
# never fired, because Vercel spread the burst across several ephemeral
# instances and each one has its own counter. It only bites when one caller
# keeps hitting one warm instance.
#
# The real control is Vercel's own firewall (Project -> Firewall), which sees
# every request before it reaches a function. Do not treat this function as
# protection; treat it as a courtesy 429 for an obvious loop.
#
# The key is a hash of the forwarded IP, never the address itself: this process
# has no business holding identifiable data about a caller, and a truncated
# digest is enough to count against.
_BUCKET = {}
_LIMIT = 60             # requests
_WINDOW = 60.0          # seconds


def _client_key(handler):
    fwd = (handler.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return hashlib.sha256((fwd or "unknown").encode()).hexdigest()[:16]


def rate_limited(handler):
    """True when this caller has exceeded the window. Prunes as it goes."""
    now = time.time()
    key = _client_key(handler)
    hits = [t for t in _BUCKET.get(key, ()) if now - t < _WINDOW]
    hits.append(now)
    _BUCKET[key] = hits
    if len(_BUCKET) > 2000:                     # bound the map on a warm instance
        cutoff = now - _WINDOW
        for k in [k for k, v in _BUCKET.items() if not v or v[-1] < cutoff]:
            _BUCKET.pop(k, None)
    return len(hits) > _LIMIT


def reply(handler, obj, code=200):
    body = json.dumps(obj).encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    # A pasted note must not be retained by any cache between here and the
    # browser, and the response is derived entirely from it.
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler, limit=200_000):
    """Request body as a dict. Returns None if it is unusable or oversized."""
    n = int(handler.headers.get("Content-Length") or 0)
    if n <= 0 or n > limit:
        return None
    try:
        return json.loads(handler.rfile.read(n) or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def quiet(cls):
    """Suppress the default access log, which would record request lines."""
    cls.log_message = lambda self, fmt, *a: None
    return cls
