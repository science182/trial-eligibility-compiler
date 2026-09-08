"""Aggregate-only usage counters.

The site's most credible claim is its privacy page, so the constraint here is
not "collect less than average" -- it is that every sentence on /privacy.html
stays literally true and a reader can confirm it from this file.

What that rules out, and why:

* No cookie, no localStorage id, no fingerprint, no session id. Nothing here
  can tell whether two requests came from the same person, which is what makes
  the numbers aggregates rather than a record of anybody.
* No IP address, not even hashed. A hashed IP is still a per-visitor key.
* No full referrer URL. A referring URL can carry a search query or the path of
  a private page, so only the *host* is kept, and only when it is a host we
  already know the name of -- everything else collapses to "other".
* Nothing derived from the clinical note. Not its length, not a word from it,
  not whether it matched. The note is the one thing this service exists to not
  retain, and a counter is not a good enough reason to start.

Storage is a Redis-compatible KV over its HTTP API (Upstash, which is what
Vercel's marketplace provisions). Reached with urllib so the runtime keeps its
zero-dependency property, which is the reason cold starts are ~1s.

Unconfigured, every function here is a no-op that returns quietly. That matters
for two audiences: someone who clones the repo gets a working site without
signing up for anything, and a counter outage can never take the tool down.
"""

import json
import os
import re
import urllib.error
import urllib.request
from datetime import date, timedelta

# Vercel's marketplace integration injects the KV_* pair; a store created
# directly at Upstash uses the UPSTASH_* names. Accepting both means the
# integration can be set up either way without editing code.
def _env(*names):
    for n in names:
        v = os.environ.get(n)
        if v:
            return v.strip()
    return ""


URL = _env("KV_REST_API_URL", "UPSTASH_REDIS_REST_URL").rstrip("/")
TOKEN = _env("KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_TOKEN")

P = "tec:"                      # key prefix, so the store can be shared
DAY_TTL = 60 * 60 * 24 * 400    # per-day keys expire; only totals are forever
TIMEOUT = 2.0                   # a slow counter must not become a slow page

# Events, and what each one means in the funnel. Kept as a closed set so a
# typo in the client cannot create an unbounded number of keys.
EVENTS = {
    "visit": "v",     # the page was opened
    "doc": "d",       # a document was loaded (test document or the visitor's)
    "match": "m",     # a match was actually run
}

# Answers to the one optional question the tool asks after a match: who are you.
# Traffic is anonymous by design, which makes it impossible to tell 5,000
# engineers from 5,000 coordinators -- and that is the only distinction that
# decides whether this project is worth continuing. A self-declared answer from
# a closed set is the least invasive instrument that can tell them apart: it is
# volunteered, it is one of five words, and it is added to a total rather than
# attached to anybody.
ROLES = ("screens_patients", "clinician", "researcher", "engineer", "curious")

# Referrers are only recorded under a name from this list. An arrivals report
# exists to answer "which post worked", and that question only ever has a
# handful of candidate answers -- so an allowlist loses nothing and removes any
# chance of a stray URL becoming a key.
KNOWN = {
    "news.ycombinator.com": "hacker news",
    "hn.algolia.com": "hacker news",
    "reddit.com": "reddit",
    "old.reddit.com": "reddit",
    "linkedin.com": "linkedin",
    "lnkd.in": "linkedin",
    "github.com": "github",
    "x.com": "x",
    "twitter.com": "x",
    "t.co": "x",
    "bsky.app": "bluesky",
    "mastodon.social": "mastodon",
    "lobste.rs": "lobsters",
    "google.com": "search",
    "duckduckgo.com": "search",
    "bing.com": "search",
    "substack.com": "newsletter",
    "ycombinator.com": "hacker news",
}

_HOST = re.compile(r"^[a-z0-9.-]{1,80}$")


def source(referrer):
    """A referring URL reduced to one of a few known names.

    Returns "direct" when there was no referrer at all (a pasted link, a
    bookmark, most apps) and "other" for anything not on the list.
    """
    if not referrer:
        return "direct"
    host = str(referrer).strip().lower()
    host = host.split("//")[-1].split("/")[0].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if not host or not _HOST.match(host):
        return "other"
    if host in KNOWN:
        return KNOWN[host]
    # One level of suffix matching, so old.reddit.com and a country Google both
    # land on the right name without enumerating every subdomain.
    for known, name in KNOWN.items():
        if host.endswith("." + known):
            return name
    # Search engines run a country domain per market (google.co.uk, google.de),
    # and a launch that shows up in search deserves to be legible as search
    # rather than scattered across "other".
    for engine in ("google.", "bing.", "duckduckgo.", "search.yahoo."):
        if host.startswith(engine):
            return "search"
    return "other"


def configured():
    return bool(URL and TOKEN)


def _pipeline(commands):
    """Run a list of Redis commands in one round trip. None on any failure."""
    if not configured() or not commands:
        return None
    req = urllib.request.Request(
        f"{URL}/pipeline",
        data=json.dumps(commands).encode(),
        headers={"Authorization": f"Bearer {TOKEN}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError):
        # Deliberately silent. There is no useful action a caller could take,
        # and a traceback here would be noise in the logs of a working site.
        return None


def record(event, referrer=None, when=None):
    """Add one to the counters for `event`. Safe to call on any path."""
    code = EVENTS.get(event)
    if not code or not configured():
        return
    day = (when or date.today()).isoformat()
    cmds = [
        ["INCR", f"{P}{code}:all"],
        ["INCR", f"{P}{code}:{day}"],
        ["EXPIRE", f"{P}{code}:{day}", str(DAY_TTL)],
    ]
    # Arrivals are only interesting for the visit itself; counting a referrer
    # again on match would double-count the same arrival.
    if event == "visit":
        cmds.append(["HINCRBY", f"{P}ref", source(referrer), "1"])
    _pipeline(cmds)


def record_role(role):
    """Add one to a self-declared role total. Unknown values are dropped."""
    if role not in ROLES or not configured():
        return
    _pipeline([["HINCRBY", f"{P}role", role, "1"]])


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def report(days=30, today=None):
    """Every counter, as plain integers. Never raises."""
    end = today or date.today()
    span = [(end - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]

    if not configured():
        return {"configured": False, "totals": {}, "daily": [],
                "sources": {}, "roles": {}, "days": days}

    cmds = [["GET", f"{P}{c}:all"] for c in EVENTS.values()]
    for code in EVENTS.values():
        cmds.append(["MGET"] + [f"{P}{code}:{d}" for d in span])
    cmds.append(["HGETALL", f"{P}ref"])
    cmds.append(["HGETALL", f"{P}role"])

    res = _pipeline(cmds)
    if res is None:
        return {"configured": True, "error": "counter store unreachable",
                "totals": {}, "daily": [], "sources": {}, "roles": {},
                "days": days}

    out = [r.get("result") if isinstance(r, dict) else r for r in res]
    names = list(EVENTS)
    totals = {names[i]: _int(out[i]) for i in range(len(names))}

    series = {}
    for i, name in enumerate(names):
        row = out[len(names) + i] or []
        series[name] = [_int(v) for v in row] + [0] * (days - len(row))

    daily = [{"date": d, **{n: series[n][i] for n in names}}
             for i, d in enumerate(span)]

    # HGETALL comes back as a flat [field, value, field, value] list.
    def hash_of(flat):
        flat = flat or []
        pairs = {flat[i]: _int(flat[i + 1]) for i in range(0, len(flat) - 1, 2)}
        return dict(sorted(pairs.items(), key=lambda kv: -kv[1]))

    return {"configured": True, "totals": totals, "daily": daily,
            "sources": hash_of(out[-2]),
            "roles": hash_of(out[-1]),
            "days": days}
