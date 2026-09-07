"""Single chokepoint for every model call in the system.

Nothing else in the codebase may call a model. Everything goes through
`complete()`, which logs call count, token count, and latency per query -- those
logs are the source for the 9.3 cost metric, so this exists from day one rather
than being retrofitted.

Design constraints, in priority order:

1. THE DEMO MUST NOT TOUCH THE NETWORK. Every response is cached to disk by a
   hash of (model, prompt). A rate-limit error or a dropped connection during a
   five-minute demo is unrecoverable, so the demo path reads the cache and the
   network is never on the critical path.
2. FREE TIER. Default provider is the Gemini REST API, called with `requests`
   so the project keeps its zero-dependency install. No SDK, no key in code.
3. SWAPPABLE. Provider is one function. Switching to another vendor -- or to a
   local model -- does not touch extract.py or the evaluator.
4. NEVER FABRICATE. With no key and no cache entry, `complete()` raises
   LLMUnavailable. Callers fall back to the deterministic path; nothing invents
   a patient value.
"""

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "cache" / "llm"
LOG_PATH = ROOT / "data" / "cache" / "llm_calls.jsonl"

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Free tier is $0. Kept as a table so the 9.3 slide can also show what the same
# workload would cost on a paid tier, which is the more honest comparison.
COST_PER_MTOK = {
    "free": (0.0, 0.0),
}


class LLMUnavailable(RuntimeError):
    """No key and no cached response. Callers must degrade, not guess."""


@dataclass
class Call:
    model: str
    prompt_hash: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    cached: bool = False
    error: str = ""

    @property
    def total_tokens(self):
        return self.prompt_tokens + self.completion_tokens


@dataclass
class CallLog:
    """Per-query accounting. Reset at the start of each patient query."""
    calls: list = field(default_factory=list)

    def add(self, call):
        self.calls.append(call)
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(asdict(call)) + "\n")

    def reset(self):
        self.calls = []

    @property
    def network_calls(self):
        return sum(1 for c in self.calls if not c.cached)

    @property
    def total_tokens(self):
        return sum(c.total_tokens for c in self.calls)

    @property
    def wall_seconds(self):
        return sum(c.latency_s for c in self.calls)

    def summary(self, tier="free"):
        rate_in, rate_out = COST_PER_MTOK.get(tier, (0.0, 0.0))
        tin = sum(c.prompt_tokens for c in self.calls)
        tout = sum(c.completion_tokens for c in self.calls)
        return {
            "calls": len(self.calls),
            "network_calls": self.network_calls,
            "cached_calls": len(self.calls) - self.network_calls,
            "prompt_tokens": tin,
            "completion_tokens": tout,
            "total_tokens": tin + tout,
            "wall_seconds": round(self.wall_seconds, 3),
            "usd": round(tin / 1e6 * rate_in + tout / 1e6 * rate_out, 6),
        }


LOG = CallLog()


def _key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _hash(model, prompt, schema):
    blob = json.dumps([model, prompt, schema], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def _cache_path(h):
    return CACHE_DIR / f"{h}.json"


def read_cache(h):
    p = _cache_path(h)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def write_cache(h, payload):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(h).write_text(json.dumps(payload, indent=1))


# ------------------------------------------------------------ transport

def _gemini_request(model, prompt, schema, temperature, timeout):
    """One HTTP call. Returns (text, prompt_tokens, completion_tokens)."""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    if schema:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = schema

    req = urllib.request.Request(
        f"{API_BASE}/{model}:generateContent",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "x-goog-api-key": _key()},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"unexpected response shape: {data}") from e
    usage = data.get("usageMetadata", {})
    return (text,
            usage.get("promptTokenCount", 0),
            usage.get("candidatesTokenCount", 0))


# Swapped out in tests so the whole path runs without a key or a network.
TRANSPORT = _gemini_request

RETRYABLE = {429, 500, 502, 503, 504}


def complete(prompt, schema=None, model=None, temperature=0.0,
             timeout=60, retries=4, use_cache=True):
    """Prompt in, text out. Cached, logged, retried with backoff.

    Raises LLMUnavailable when there is no cached response and no key, so the
    caller can fall back to the deterministic path instead of guessing.
    """
    model = model or DEFAULT_MODEL
    h = _hash(model, prompt, schema)

    if use_cache:
        hit = read_cache(h)
        if hit is not None:
            LOG.add(Call(model, h, hit.get("prompt_tokens", 0),
                         hit.get("completion_tokens", 0), 0.0, cached=True))
            return hit["text"]

    if not _key():
        raise LLMUnavailable(
            "GEMINI_API_KEY is not set and this prompt is not cached")

    delay = 2.0
    last = None
    for attempt in range(retries):
        t0 = time.time()
        try:
            text, tin, tout = TRANSPORT(model, prompt, schema, temperature,
                                        timeout)
            call = Call(model, h, tin, tout, round(time.time() - t0, 3))
            LOG.add(call)
            write_cache(h, {"text": text, "prompt_tokens": tin,
                            "completion_tokens": tout, "model": model})
            return text
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in RETRYABLE or attempt == retries - 1:
                LOG.add(Call(model, h, latency_s=round(time.time() - t0, 3),
                             error=f"HTTP {e.code}"))
                raise
            # Free tiers throttle; back off rather than hammering the quota.
            time.sleep(delay)
            delay *= 2
        except Exception as e:                       # noqa: BLE001
            last = e
            if attempt == retries - 1:
                LOG.add(Call(model, h, latency_s=round(time.time() - t0, 3),
                             error=type(e).__name__))
                raise
            time.sleep(delay)
            delay *= 2
    raise last


def complete_json(prompt, schema=None, **kw):
    """`complete` plus a JSON parse that fails closed rather than half-parsing."""
    text = complete(prompt, schema=schema, **kw)
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    try:
        return json.loads(t)
    except json.JSONDecodeError as e:
        raise ValueError(f"model did not return valid JSON: {e}") from e


def available():
    return bool(_key())


def cache_size():
    return len(list(CACHE_DIR.glob("*.json"))) if CACHE_DIR.exists() else 0
