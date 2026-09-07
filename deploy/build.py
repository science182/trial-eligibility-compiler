"""Assemble the Vercel deployment package from the repository.

One source of truth: `runtime/` and `public/` are generated here from src/,
data/ and ui/static/. Never edit them by hand -- re-run this.

    python3 deploy/build.py

Everything the serverless functions need sits under a single `runtime/`
directory because Vercel's `includeFiles` takes one glob, and one plain glob
that cannot be misread beats two clever ones.

What this does beyond copying:

* Slims the corpus. The local cache carries each trial's full eligibility text
  for debugging; the deployed UI never reads it. Dropping it takes ~4MB off a
  bundle that pays for its size on every cold start.
* Adds a use notice to the page. A public URL means anyone can paste a note in,
  including a patient, and this is explicitly not patient-facing.
* Leaves the runtime dependency-free (requirements.txt is empty), so there is
  no install step that can fail at build time.

`retrieve.py` is deliberately not shipped: it is the only module that imports
sklearn and numpy, and nothing on the query path uses it.
"""

import pickle
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "data" / "eval"))

LIB_MODULES = [
    "aggregate.py", "compile.py", "conditions.py", "dates.py", "display.py",
    "drugs.py", "evaluate.py", "extract.py", "onco.py", "patient.py",
    "service.py", "split.py", "units.py",
]

NOTICE = """
  <div class="notice" role="note">
    <strong>Demonstration only &mdash; not medical advice.</strong>
    Decision support for trial coordinators and clinicians, not for patients,
    and no treatment recommendation is made. <strong>Do not upload or paste
    real patient data:</strong> this is a public demo. Recruiting status comes
    from a fixed
    registry snapshot and is often stale &mdash; verify every trial with its
    site before acting on it. Files are read in your browser and never
    uploaded; the text you match is sent to the server, held only for that
    request, and never stored &mdash; see <a href="/privacy.html">Privacy</a>.
  </div>
"""

NOTICE_CSS = """
/* ── appended by deploy/build.py: public-deployment use notice ── */
.notice {
  background: var(--warn-bg); border-bottom: 1px solid #f0dcb4;
  color: var(--warn); font-size: 11.5px; line-height: 1.45;
  padding: 7px 18px;
}
.notice strong { color: #6d4200; font-weight: 600; }

/* The page is already a flex column whose split pane claims the remaining
   height, so the notice slots in as one more band without a layout override. */
"""


def check_imports(rt):
    """Import the shipped package the way the serverless handler will.

    A module added to src/ but not to LIB_MODULES fails here, at build time,
    instead of on the first request after a deploy.
    """
    import subprocess
    probe = "import sys; sys.path.insert(0, %r); import service, personas" % str(rt)
    r = subprocess.run([sys.executable, "-c", probe],
                       capture_output=True, text=True, cwd=str(OUT))
    if r.returncode:
        tail = (r.stderr.strip().splitlines() or ["unknown error"])[-1]
        raise SystemExit(f"  runtime/ is incomplete -- {tail}\n"
                         f"  add the missing module to LIB_MODULES in "
                         f"deploy/build.py")


def build_runtime():
    """Modules and the compiled corpus, in one directory."""
    rt = OUT / "runtime"
    shutil.rmtree(rt, ignore_errors=True)
    rt.mkdir(parents=True)
    for name in LIB_MODULES:
        shutil.copy2(ROOT / "src" / name, rt / name)
    shutil.copy2(ROOT / "data" / "eval" / "personas.py", rt / "personas.py")

    from loader import compile_corpus
    compiled, meta = compile_corpus()
    slim = {
        tid: {k: v for k, v in m.items() if k != "eligibility_text"}
        for tid, m in meta.items()
    }
    target = rt / "corpus.pkl"
    with target.open("wb") as f:
        pickle.dump((compiled, slim), f, protocol=4)

    check_imports(rt)
    n = sum(len(v) for v in compiled.values())
    print(f"  runtime/   {len(LIB_MODULES) + 1} modules, {len(compiled)} "
          f"trials, {n} criteria, corpus {target.stat().st_size / 1e6:.1f} MB")


def build_public():
    pub = OUT / "public"
    shutil.rmtree(pub, ignore_errors=True)
    pub.mkdir(parents=True)
    for f in (ROOT / "ui" / "static").iterdir():
        if f.is_file():
            shutil.copy2(f, pub / f.name)

    html_path = pub / "index.html"
    html = html_path.read_text()
    assert "</header>" in html, "header markup changed; notice has nowhere to go"
    html_path.write_text(html.replace("</header>", "</header>\n" + NOTICE, 1))

    css_path = pub / "style.css"
    css_path.write_text(css_path.read_text() + NOTICE_CSS)
    print(f"  public/    {len(list(pub.iterdir()))} files, use notice added")


def main():
    print("assembling the Vercel package")
    build_runtime()
    build_public()
    (OUT / "requirements.txt").write_text("")   # stdlib only
    here = OUT.resolve()
    print("\nverify:  python3 deploy/smoke.py")
    print("deploy:  the CLI deploys the CURRENT directory, so cd first --")
    print(f"           cd {here} && npx vercel --prod")
    print("         running it from the repository root uploads the repo, "
          "which has no\n         public/ or api/, and every route 404s.")


if __name__ == "__main__":
    main()
