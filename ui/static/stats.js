/* /stats.html — renders whatever /api/pulse returns.

   No state, no interaction, one fetch. The point of the page is that the
   numbers on it come from an endpoint the reader can open themselves, so this
   file deliberately does no arithmetic that /api/pulse has not already done,
   beyond the two ratios. */

const el = document.getElementById("live");
const esc = (s) => String(s).replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const n = (v) => Number(v || 0).toLocaleString("en-US");

/* Percentages are only honest above a floor. Two visits and one match is not
   "50% conversion", and a launch page that says so invites the reader to
   discount everything else on it. */
const pct = (a, b) => (b >= 25 ? `${Math.round((a / b) * 100)}% of visits` : "—");

function tiles(t) {
  return `<div class="u-tiles">
    <div class="u-tile"><div class="n">${n(t.visit)}</div>
      <div class="k">Visits</div><div class="sub">page opened</div></div>
    <div class="u-tile"><div class="n">${n(t.doc)}</div>
      <div class="k">Documents</div><div class="sub">${esc(pct(t.doc, t.visit))}</div></div>
    <div class="u-tile"><div class="n">${n(t.match)}</div>
      <div class="k">Matches</div><div class="sub">${esc(pct(t.match, t.visit))}</div></div>
  </div>`;
}

function chart(daily) {
  const top = Math.max(1, ...daily.map((d) => d.visit));
  const bars = daily.map((d) => {
    // Matches are drawn inside the visit bar, not stacked on top of it: a match
    // is always a subset of a visit, and stacking would imply otherwise.
    const v = Math.round((d.visit / top) * 100);
    const m = Math.round((Math.min(d.match, d.visit) / top) * 100);
    return `<div class="u-bar" title="${esc(d.date)} · ${d.visit} visits · ${d.match} matches">
      <i class="v" style="height:${Math.max(0, v - m)}%"></i>
      <i class="m" style="height:${m}%"></i></div>`;
  }).join("");
  const first = daily[0], last = daily[daily.length - 1];
  return `<div class="u-chart">
    <h3>Last ${daily.length} days</h3>
    <div class="u-bars">${bars}</div>
    <div class="u-axis"><span>${esc(first.date)}</span><span>${esc(last.date)}</span></div>
    <div class="u-key"><span class="u-kv">visits</span><span class="u-km">matches</span></div>
  </div>`;
}

function sources(src) {
  const rows = Object.entries(src);
  if (!rows.length) return "";
  return `<div class="u-chart"><h3>Where visits came from</h3>
    <table class="u-srcs">${rows.map(([k, v]) =>
      `<tr><td>${esc(k)}</td><td>${n(v)}</td></tr>`).join("")}</table></div>`;
}

fetch("/api/pulse?days=30")
  .then((r) => r.json())
  .then((d) => {
    if (d.configured === false) {
      el.innerHTML = `<p class="u-dim">Counting is not switched on for this
        deployment, so there is nothing to show. The endpoint is live and the
        code is in the repository; it stays a no-op until a counter store is
        configured.</p>`;
      return;
    }
    if (d.error) {
      el.innerHTML = `<p class="u-dim">The counter store did not answer
        (${esc(d.error)}). The tool itself is unaffected — nothing on the
        matching path depends on this.</p>`;
      return;
    }
    el.innerHTML = tiles(d.totals || {}) +
                   ((d.daily || []).length ? chart(d.daily) : "") +
                   sources(d.sources || {});
  })
  .catch(() => {
    el.innerHTML = `<p class="u-dim">Could not reach /api/pulse.</p>`;
  });
