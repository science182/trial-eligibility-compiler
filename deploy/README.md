# Deploying to Vercel

The demo runs locally with `python3 ui/app.py` and needs nothing else. This
directory exists because a shared URL is easier to hand to a judge than a
clone-and-run. **The recorded demo should still be the local one** — it has no
cold start and no network between the click and the render.

## Deploy

```bash
python3 deploy/build.py && python3 deploy/smoke.py
```

Then deploy. **The Vercel CLI deploys whatever directory you are standing in**,
so the `cd` is the whole trick:

```bash
cd /Users/sujaalgelle/Downloads/SiRNADesign-main/trialcompiler/deploy && npx vercel --prod
```

`npx` fetches the CLI without installing it globally. The first run opens a
browser to log in and asks a few setup questions; accept the defaults — the
answers that matter are already in `vercel.json`. When it asks for a project
name, give it something meaningful like `trial-eligibility-compiler`; the
default is the directory name, which is just `deploy`.

### If every route 404s

You deployed the wrong directory. Running `vercel` from the repository root
uploads `SiRNADesign-main/`, which contains a Jupyter notebook and no `public/`,
no `api/` and no `vercel.json` — so there is nothing to serve and Vercel returns
`404: NOT_FOUND` for `/`. The project slug in the URL tells you which directory
went up: `si-rnad-esign-main` is the repo root, not this package.

Fix it by deleting that project in the Vercel dashboard, removing the stray
`.vercel` directory it left at the repo root, and deploying again from here.
Alternatively keep the project and set **Settings → Build & Deployment → Root
Directory** to `trialcompiler/deploy`, which preserves the existing URL.

Nothing here needs an API key. There is no `GEMINI_API_KEY` on the deployed
path: the query path is `extract_rules`, which is deterministic and offline.

## What gets built

`build.py` is the only thing that writes `runtime/` and `public/`. Don't edit
those by hand; edit `src/` or `ui/static/` and re-run it.

```
api/assess.py     POST /api/assess    one report against the compiled corpus
api/samples.py    GET  /api/samples   demo personas, no corpus load
api/_runtime.py   shared: import paths, corpus loading, JSON replies
runtime/          13 modules + corpus.pkl (3.8 MB), one includeFiles glob
public/           the UI, plus a use notice build.py injects
vercel.json       function limits and security headers
```

Total package ~4 MB. Cold start is dominated by unpickling the corpus, about
0.1s. Warm requests are extraction plus evaluation, about 110ms for 500 trials.

## Three things that differ from local, and why

**The filesystem is read-only.** `loader.load_corpus()` recompiles and *writes*
its cache on a miss, which raises on Vercel. The handlers therefore read
`runtime/corpus.pkl` directly and never import `loader`. `smoke.py` asserts
that `loader` is absent from `sys.modules` after a request, so this can't
regress silently.

**Nothing is logged.** The request body is a clinical note. It is held in
memory for one request, never written to disk, and never echoed into a log
line — including on the error path, where logging the input is most tempting.
`_runtime.quiet` suppresses the default access log for the same reason.

**The page carries a use notice.** Locally the only user is whoever started the
server. A public URL can be opened by a patient, so the deployed page states
that it is not medical advice, not patient-facing, and not a place to paste
real patient data. `build.py` injects it and `smoke.py` fails if it is missing.

## Before sharing the URL

Recruiting status is a fixed snapshot from ClinicalTrials.gov, and it goes
stale. If the link will be up for more than a few weeks, either re-run
`python3 src/fetch.py` and rebuild, or take it down. A trial list that silently
ages is worse than no trial list.
