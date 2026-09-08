/* Trial Eligibility Compiler — UI.

   Navigation model: a verdict strip that answers the query in one line, a list
   on the left, a detail pane on the right. Selection follows the arrow keys and
   the detail updates with it, so scanning forty trials costs forty keystrokes
   and no clicks.

   Two things here are deliberate rather than incidental:

   - The list ranks by how much checkable evidence a trial actually offered, not
     just by state. "Eligible" on one criterion and "eligible" on fifteen are
     different findings, and a flat list hides that.
   - The 421 ruled-out trials collapse into their reasons. Grouped, they stop
     being noise and become an explanation of why the field narrowed. */

const $  = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

/* Order is the list order. Dated trials lead because they are the finding the
   hero states and the one no categorical matcher produces; "eligible now" is
   larger but less interesting, and "not eligible" is 84% of the corpus. */
const STATES = [
  { key: "eligible_on_date", cls: "warn", sw: "var(--warn)", label: "Eligible from a date" },
  { key: "eligible_now",     cls: "ok",   sw: "var(--ok)",   label: "Eligible now" },
  { key: "undetermined",     cls: "neut", sw: "var(--neut)", label: "Needs data" },
  { key: "blocked",          cls: "bad",  sw: "var(--bad)",  label: "Not eligible" },
];
const CLS   = Object.fromEntries(STATES.map((s) => [s.key, s.cls]));
const SW    = Object.fromEntries(STATES.map((s) => [s.key, s.sw]));
const LABEL = Object.fromEntries(STATES.map((s) => [s.key, s.label]));
const VDOT  = { met: "var(--ok)", pending: "var(--warn)",
                undetermined: "var(--neut)", not_met: "var(--bad)" };

/* A trial resolved on one or two criteria is a real match on thin evidence.
   Saying so is more useful than silently ranking it last. */
const WEAK = 2;

let DATA = null, SAMPLE = null;
let filter = null, selId = null, blockedOpen = false, blockedFilter = null;
let palOpen = false, palCursor = 0, palHits = [];
let SAMPLE_LOADED = false;      // did the input come from the test document?
let metOpen = false;      // 'already satisfied' starts collapsed

const esc = (s) => String(s).replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* "lab:CREATININE_CLEARANCE" -> "creatinine clearance"; "date:TOXICITY" ->
   "toxicity date". The prefix says what kind of gap it is. */
function fieldLabel(f) {
  const [kind, rest] = f.includes(":") ? f.split(":") : ["", f];
  const n = (rest || f || "").replace(/_/g, " ").toLowerCase();
  return { lab: n, date: `${n} date`, comorbidity: `${n} status`,
           biomarker: `${n} test`, therapy: `prior ${n}`,
           condition: `${n} status` }[kind] || n;
}

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

/* Sites arrive from the registry as "City Region Country" with no separators:
   "Birmingham Alabama United States", "Guangzhou Guangdong China". Full strings
   wrap to three lines in a list row.

   The rule is deliberately conservative. A US site becomes "Birmingham, AL",
   which is how anyone in the US writes it. Elsewhere the region is dropped only
   when it is a province we can name, because a blind "drop the last word" turns
   "Tel Aviv Israel" into "Tel, Israel". Anything unrecognised is left alone --
   a slightly long label beats a wrong one. */
const US_STATE = {
  Alabama:"AL", Alaska:"AK", Arizona:"AZ", Arkansas:"AR", California:"CA",
  Colorado:"CO", Connecticut:"CT", Delaware:"DE", Florida:"FL", Georgia:"GA",
  Hawaii:"HI", Idaho:"ID", Illinois:"IL", Indiana:"IN", Iowa:"IA", Kansas:"KS",
  Kentucky:"KY", Louisiana:"LA", Maine:"ME", Maryland:"MD", Massachusetts:"MA",
  Michigan:"MI", Minnesota:"MN", Mississippi:"MS", Missouri:"MO", Montana:"MT",
  Nebraska:"NE", Nevada:"NV", Ohio:"OH", Oklahoma:"OK", Oregon:"OR",
  Pennsylvania:"PA", Tennessee:"TN", Texas:"TX", Utah:"UT", Vermont:"VT",
  Virginia:"VA", Washington:"WA", Wisconsin:"WI", Wyoming:"WY",
  "New Hampshire":"NH", "New Jersey":"NJ", "New Mexico":"NM", "New York":"NY",
  "North Carolina":"NC", "North Dakota":"ND", "Rhode Island":"RI",
  "South Carolina":"SC", "South Dakota":"SD", "West Virginia":"WV",
  "District of Columbia":"DC", "Puerto Rico":"PR",
};

/* Provinces common in this corpus. Unlisted ones simply stay in the label. */
const PROVINCE = new Set([
  "Guangdong","Shandong","Jiangsu","Zhejiang","Sichuan","Hunan","Hubei","Henan",
  "Hebei","Fujian","Anhui","Shaanxi","Liaoning","Jilin","Heilongjiang","Yunnan",
  "Guangxi","Jiangxi","Shanxi","Gansu","Tianjin","Chongqing","Beijing","Shanghai",
  "Ontario","Quebec","Alberta","Manitoba","Saskatchewan","Nova Scotia",
  "British Columbia","New Brunswick","Newfoundland and Labrador",
  "New South Wales","Victoria","Queensland","Western Australia",
  "South Australia","Tasmania",
]);

const COUNTRIES = ["United States","United Kingdom","Republic of Korea","Korea",
  "Taiwan","China","Japan","Canada","Australia","Germany","France","Spain",
  "Italy","Netherlands","Belgium","Denmark","Sweden","Norway","Finland",
  "Poland","Austria","Switzerland","Ireland","Portugal","Greece","Czechia",
  "Hungary","Romania","Israel","Turkey","India","Brazil","Mexico","Argentina",
  "Chile","Singapore","Thailand","Malaysia","New Zealand","South Africa"];

function siteLabel(site) {
  if (!site) return "";
  const country = COUNTRIES.find((c) => site.endsWith(c));
  if (!country) return site;
  let head = site.slice(0, -country.length).trim();
  if (!head) return country;

  if (country === "United States") {
    for (const [name, code] of Object.entries(US_STATE)) {
      if (head.endsWith(name)) {
        const city = head.slice(0, -name.length).trim();
        return city ? `${city}, ${code}` : code;
      }
    }
    return `${head}, US`;
  }
  // Drop a province only when we can name it.
  for (const prov of PROVINCE) {
    if (head.endsWith(prov) && head.length > prov.length) {
      head = head.slice(0, -prov.length).trim();
      break;
    }
  }
  return `${head}, ${country}`;
}

/* The list row has room for a city, not a full address: the detail pane shows
   "Guangzhou, China", the row shows "Guangzhou". Truncating the full string
   instead produced "Guangzhou," and "San Francisc". */
function cityLabel(site) {
  const full = siteLabel(site);
  return full.includes(",") ? full.slice(0, full.indexOf(",")) : full;
}

function phaseLabel(phase) {
  if (!phase || phase === "NA") return "";
  const n = phase.replace(/PHASE/g, "").split(/[,\s]+/).filter(Boolean);
  return n.length ? `Phase ${n.join("/")}` : "";
}

const fmtDate = (iso, withYear = true) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]}${withYear ? " " + y : ""}`;
};

function daysFromIndex(iso) {
  if (!iso || !DATA) return null;
  const ms = Date.parse(iso + "T00:00:00Z") - Date.parse(DATA.patient.index_date + "T00:00:00Z");
  return Math.round(ms / 86400000);
}

/* "EGFR EXON19DEL" -> "EGFR exon 19 del";  "PD_L1 OVEREXPRESSION" -> "PD-L1
   overexpression". Gene symbols stay upper case because that is how they are
   written on a pathology report; variant codes like L858R keep their case too. */
const GENE_LABEL = { PD_L1: "PD-L1", ROS1: "ROS1", HER2: "HER2" };

function bioLabel(raw) {
  const [gene, ...rest] = String(raw).split(" ");
  const g = GENE_LABEL[gene] || gene;
  let a = rest.join(" ").toLowerCase().replace(/_/g, " ")
    .replace(/^exon\s*(\d+)\s*(del|ins)\w*$/, (m, n, k) => `exon ${n} ${k}`)
    .replace(/\b([a-z]\d{2,4}[a-z])\b/g, (m) => m.toUpperCase());
  return a ? `${g} ${a}` : g;
}

/* ─────────────────────────────────────────────── evidence ── */

function evidence(t) {
  const n = t.rows.length;
  const met = t.rows.filter((r) => r.verdict === "met").length;
  const pend = t.rows.filter((r) => r.verdict === "pending").length;
  return { n, met, pend, weak: n <= WEAK };
}

/* Six segments standing for volume of evidence, not a percentage: a 15-criterion
   trial fills the bar, a 1-criterion trial shows a single mark. */
function covBar(t) {
  const { n, pend, weak } = evidence(t);
  const on = Math.max(1, Math.min(6, Math.round(n / 2)));
  let out = "";
  for (let i = 0; i < 6; i++) {
    const cls = i < on ? (pend && i === on - 1 ? "on pend" : "on") : "";
    out += `<i class="covseg ${cls}"></i>`;
  }
  const { met } = evidence(t);
  return `<div class="cov"><span class="covtxt">${met}/${n}</span>
          <span class="covbar">${out}</span></div>`;
}

/* ─────────────────────────────────────────────────── strip ── */

function renderStrip() {
  const counts = {};
  DATA.trials.forEach((t) => (counts[t.state] = (counts[t.state] || 0) + 1));

  // Hero: lead with the output nothing else produces — a specific date.
  const dated = DATA.trials.filter((t) => t.state === "eligible_on_date")
                           .sort((a, b) => a.eligible_date.localeCompare(b.eligible_date));
  let hero;
  if (dated.length) {
    const parts = dated.map((t) => `<span class="d">${fmtDate(t.eligible_date, false)}</span>`)
      .join(`<span class="sep">·</span>`);
    const year = dated[dated.length - 1].eligible_date.slice(0, 4);
    hero = `<div class="over">${dated.length} trial${dated.length > 1 ? "s" : ""}
              open${dated.length > 1 ? "" : "s"} on a specific date</div>
            <div class="big">${parts}<span class="d">${year}</span></div>`;
  } else {
    const n = counts.eligible_now || 0;
    hero = `<div class="over">Matched against ${DATA.timing.trials} recruiting trials</div>
            <div class="big plain">${n} eligible now</div>`;
  }
  $("#hero").innerHTML = hero;

  $("#proof").innerHTML = `
    <div class="perf" style="gap:8px">
      <span><b>${DATA.timing.trials}</b> trials</span><span>·</span>
      <span><b>${Math.round(DATA.timing.total_ms)} ms</b></span>
    </div>
    <span class="zero"><span class="dot"></span>${DATA.timing.model_calls} model calls</span>`;

  $("#counts").innerHTML = STATES.map((s) => `
    <button class="cnt" data-state="${s.key}" aria-pressed="${filter === s.key}">
      <span class="sw" style="background:${s.sw}"></span>
      <b>${counts[s.key] || 0}</b>
      <span class="l">${s.key === "eligible_on_date" && dated.length
        ? "Eligible from " + fmtDate(dated[0].eligible_date, false) : s.label}</span>
    </button>`).join("");

  // Facts, not prose. The note itself is one click away, in the detail pane.
  const p = DATA.patient;
  const chips = [
    p.age && `${p.age} ${p.sex === "female" ? "F" : p.sex === "male" ? "M" : ""}`.trim(),
    p.stage && `Stage ${p.stage}${
      p.histology_label ? " " + p.histology_label : ""}`,
    p.ecog !== null && p.ecog !== undefined && `ECOG ${p.ecog}`,
    ...(p.biomarkers || []).map(bioLabel),
    p.labs && `${p.labs} labs`,
  ].filter(Boolean);

  const h = DATA.missing_headline;
  $("#work").innerHTML = h && h.tests ? `
    <button class="work-line" id="work-go">
      <span class="sw" style="background:var(--neut)"></span>
      <b>${h.tests} tests</b> would resolve <b>${h.criteria} criteria</b>
      across <b>${h.trials} trials</b>
      <span class="work-list">${DATA.missing.slice(0, 4)
        .map((m) => esc(m.label || fieldLabel(m.field))).join(" · ")}</span>
      <span class="chev">→</span>
    </button>` : "";

  $("#patient").innerHTML = `
    <span class="pname">${esc(
      SAMPLE_LOADED && SAMPLE ? SAMPLE.name : "Patient")}</span>
    ${chips.map((c) => `<span class="pchip">${esc(c)}</span>`).join("")}`;
}

/* ──────────────────────────────────────────────────── list ── */

function ranked(state) {
  // Within a state, strongest evidence first. Dated trials sort by date, since
  // "which opens soonest" is the question a coordinator is actually asking.
  const ts = DATA.trials.filter((t) => t.state === state);
  if (state === "eligible_on_date") {
    return ts.sort((a, b) => a.eligible_date.localeCompare(b.eligible_date));
  }
  return ts.sort((a, b) => evidence(b).n - evidence(a).n);
}

function rowHtml(t) {
  const ev = evidence(t);
  // Each part is its own element: the CSS truncates the last one, and a bare
  // text node cannot be selected as :last-child.
  const meta = [`<span class="rid">${t.id}</span>`,
                phaseLabel(t.phase) && `<span>${esc(phaseLabel(t.phase))}</span>`,
                cityLabel(t.site) && `<span>${esc(cityLabel(t.site))}</span>`]
    .filter(Boolean).join(`<span class="mdot">·</span>`);
  const days = daysFromIndex(t.eligible_date);

  return `
    <button class="row ${ev.weak ? "weak" : ""} ${selId === t.id ? "sel" : ""}"
            data-id="${t.id}">
      <span class="rbar" style="background:${ev.weak ? "#C2CDC6" : SW[t.state]}"></span>
      <span class="rmain">
        <span class="rtitle">${esc(t.title || t.id)}</span>
        <span class="rmeta">${meta}${ev.weak
          ? `<span>·</span><span class="tag-weak">limited evidence</span>` : ""}</span>
        ${t.state === "blocked" && t.blocking_reason
          ? `<span class="rwhy">${esc(t.blocking_reason)}</span>` : ""}
      </span>
      <span class="rright">
        ${t.eligible_date ? `<span class="rdate">${fmtDate(t.eligible_date, false)}${
          days !== null && days >= 0 ? ` · ${days}d` : ""}</span>` : ""}
        ${covBar(t)}
      </span>
    </button>`;
}

function blockedHtml(group) {
  const reasons = {};
  group.forEach((t) => {
    const k = t.blocking_reason || "no single blocking criterion";
    reasons[k] = (reasons[k] || 0) + 1;
  });
  const sorted = Object.entries(reasons).sort((a, b) => b[1] - a[1]);
  const top = sorted.slice(0, 6);
  const rest = sorted.length - top.length;

  return `
    <div class="blk">
      <button class="blkhd" id="blk-toggle">
        <span class="sw" style="background:var(--bad)"></span>
        <b>${group.length} not eligible</b>
        <span class="sub">by reason</span>
        <span class="chev">${blockedOpen ? "▴" : "▾"}</span>
      </button>
      ${blockedOpen ? top.map(([r, n]) => `
        <button class="blkrow" data-reason="${esc(r)}"><b>${n}</b>
          <span>${esc(r)}</span></button>`).join("")
        + (rest > 0 ? `<div class="blkmore">+ ${rest} more reason${rest > 1 ? "s" : ""}</div>` : "")
      : ""}
    </div>`;
}

/* A narrowed list must say so and offer a way back. Escape already did this,
   but only for someone who knew Escape did this. */
function renderFilterBar() {
  const bar = $("#filterbar");
  if (!bar) return;
  let what = "", n = 0;
  if (blockedFilter) {
    what = blockedFilter;
    n = DATA.trials.filter((t) => t.state === "blocked" &&
                                  t.blocking_reason === blockedFilter).length;
  } else if (filter) {
    what = LABEL[filter];
    // Count the state, not the rendered rows: the blocked group renders as a
    // collapsed summary, so counting rows would report zero.
    n = DATA.trials.filter((t) => t.state === filter).length;
  }
  bar.hidden = !what;
  // Clear the text when hidden, so nothing stale can be read back later.
  $("#filter-what").textContent = what ? `${what} · ${n}` : "";
}

function renderList() {
  let html = "";
  for (const s of STATES) {
    let group = ranked(s.key);
    if (filter && filter !== s.key) continue;

    if (s.key === "blocked") {
      if (blockedFilter) group = group.filter((t) => t.blocking_reason === blockedFilter);
      if (!group.length) continue;
      // Only expand into rows when the coordinator has picked a reason.
      if (blockedFilter) {
        html += `<div class="grp">${esc(blockedFilter)} · ${group.length}</div>`
              + group.map(rowHtml).join("");
      } else {
        html += blockedHtml(group);
      }
      continue;
    }
    if (!group.length) continue;
    html += `<div class="grp">${s.label} · ${group.length}</div>`
          + group.map(rowHtml).join("");
  }
  $("#list").innerHTML = html || `<div class="empty">No trials match that filter.</div>`;
  wireList();
  renderFilterBar();
}

function wireList() {
  $$(".row").forEach((r) => r.addEventListener("click", () => select(r.dataset.id)));
  const bt = $("#blk-toggle");
  if (bt) bt.addEventListener("click", () => { blockedOpen = !blockedOpen; renderList(); });
  $$(".blkrow").forEach((b) => b.addEventListener("click", () => {
    blockedFilter = b.dataset.reason; filter = "blocked";
    renderStrip(); wireStrip(); renderList();
    $("#list").scrollTop = 0;
    const first = $$(".row")[0];
    if (first) select(first.dataset.id);
  }));
}

/* ────────────────────────────────────────────────── detail ── */

function critHtml(r) {
  const notes = [];
  // The reason now prints dates as prose, so compare the rendered form -- the
  // ISO comparison this replaced never matched and printed the date twice.
  if (r.anchor_date && !r.reason.includes(fmtDate(r.anchor_date))) {
    notes.push(`anchored to ${fmtDate(r.anchor_date)}`);
  }
  (r.assumed || []).forEach((a) => notes.push(a));
  return `
    <button class="c" data-spans='${esc(JSON.stringify(r.spans || []))}'>
      <span class="cdot" style="background:${VDOT[r.verdict]}"></span>
      <span class="cmain">
        <span class="ctype">${esc(r.type.replace(/_/g, " "))}${
          r.inclusion ? "" : ` <span class="ex">· EXCL</span>`}</span>
        <span class="creason">${esc(r.reason)}</span>
        <span class="craw">${esc(r.raw_text)}</span>
        ${notes.length ? `<span class="craw">${esc(notes.join(" · "))}</span>` : ""}
      </span>
      ${r.eligible_date
        ? `<span class="cwhen">${fmtDate(r.eligible_date, false)}</span>` : ""}
    </button>`;
}

function stateLine(t) {
  const days = daysFromIndex(t.eligible_date);
  switch (t.state) {
    case "eligible_now":
      return `<div class="dstate ok"><span class="dot"></span>Eligible now
              <small>${evidence(t).n} criteria checked</small></div>`;
    case "eligible_on_date":
      return `<div class="dstate warn"><span class="dot"></span>
              Opens ${fmtDate(t.eligible_date)}
              <small>in ${days} day${days === 1 ? "" : "s"}</small></div>`;
    case "undetermined":
      return `<div class="dstate neut"><span class="dot"></span>Needs data
              <small>${t.rows.filter((r) => r.verdict === "undetermined").length}
              unresolved</small></div>`;
    default:
      return `<div class="dstate bad"><span class="dot"></span>Not eligible
              <small>${esc(t.blocking_reason || "")}</small></div>`;
  }
}

/* Every claim the interface makes about a trial should be checkable against the
   registry it came from, in one click. */
const CTGOV = (id) => `https://clinicaltrials.gov/study/${encodeURIComponent(id)}`;

function renderDetail() {
  const t = DATA.trials.find((x) => x.id === selId);
  if (!t) {
    $("#detail").innerHTML = `<div class="empty">Select a trial</div>`;
    return;
  }
  const open = t.rows.filter((r) => r.verdict !== "met");
  const met  = t.rows.filter((r) => r.verdict === "met");
  const meta = [
    `<a class="rid ctlink" href="${CTGOV(t.id)}" target="_blank"
        rel="noopener noreferrer">${t.id} <span class="ext">↗</span></a>`,
    phaseLabel(t.phase) && `<span>${esc(phaseLabel(t.phase))}</span>`,
    t.sponsor && `<span>${esc(t.sponsor)}</span>`,
    siteLabel(t.site) && `<span>${esc(siteLabel(t.site))}</span>`]
    .filter(Boolean).join(`<span class="mdot">·</span>`);

  // Never name the patient's gender here: the note is whatever was uploaded,
  // and "why she is not eligible" is wrong for half of them. Shorter, too.
  const openLabel = t.state === "blocked" ? "Blocking"
    : t.state === "eligible_on_date" ? "Waiting on"
    : "Unresolved";

  $("#detail").innerHTML = `
    <div class="dhead">
      <div class="dtitle">${esc(t.title || t.id)}</div>
      <div class="dmeta">${meta}</div>
      ${stateLine(t)}
    </div>
    ${open.length ? `<div class="dsec">${openLabel} · ${open.length}</div>
       <div class="crit">${open.map(critHtml).join("")}</div>` : ""}
    ${met.length ? `
       <button class="dsec-toggle" id="met-toggle">
         <span class="dsec">Satisfied · ${met.length}</span>
         <span class="chev">${metOpen ? "hide" : "show"}</span>
       </button>
       ${metOpen ? `<div class="crit">${met.map(critHtml).join("")}</div>` : ""}`
     : ""}
    ${!t.rows.length ? `<div class="dsec">No machine-checkable criteria</div>
       <p class="dnote">Every criterion here is free text. The system
       abstains rather than guessing.</p>` : ""}
    <div class="src">
      <a href="${CTGOV(t.id)}" target="_blank" rel="noopener noreferrer">
        ClinicalTrials.gov <span class="ext">↗</span></a>
      · snapshot ${DATA.source ? fmtDate(DATA.source.snapshot) : ""}
      · verify status with the site
    </div>
    <div class="note" id="note">
      <div class="notehd"><b>Source note</b>
        <span id="note-hint">click a criterion to highlight its source</span>
      </div>
      <div class="notebody" id="notebody"></div>
    </div>`;

  renderNote();
  $("#met-toggle")?.addEventListener("click", () => {
    metOpen = !metOpen;
    renderDetail();
  });
  $$(".c").forEach((c) => c.addEventListener("click", () => {
    $$(".c.act").forEach((x) => x.classList.remove("act"));
    c.classList.add("act");
    highlight(JSON.parse(c.dataset.spans || "[]"));
  }));
}

function renderNote() {
  const { report, spans } = DATA.patient;
  const marks = Object.entries(spans).map(([k, [s, e]]) => ({ k, s, e }))
    .filter((m) => m.e > m.s).sort((a, b) => a.s - b.s || b.e - a.e);
  let html = "", cur = 0;
  for (const m of marks) {
    if (m.s < cur) continue;                        // drop overlaps, first wins
    html += esc(report.slice(cur, m.s));
    html += `<mark data-span="${m.s}-${m.e}">${esc(report.slice(m.s, m.e))}</mark>`;
    cur = m.e;
  }
  html += esc(report.slice(cur));
  $("#notebody").innerHTML = html;
}

function highlight(spans) {
  $$("#notebody mark.on").forEach((m) => m.classList.remove("on"));
  let first = null;
  for (const [s, e] of spans || []) {
    const m = $(`#notebody mark[data-span="${s}-${e}"]`);
    if (m) { m.classList.add("on"); first = first || m; }
  }
  const hint = $("#note-hint");
  if (first) {
    first.scrollIntoView({ block: "center", behavior: "smooth" });
    if (hint) hint.textContent = "highlighted: the line this was computed from";
  } else if (hint) {
    hint.textContent = "no verbatim source in the note";
  }
}

function select(id, scroll = false) {
  selId = id;
  $$(".row").forEach((r) => r.classList.toggle("sel", r.dataset.id === id));
  if (scroll) {
    const row = $(`.row[data-id="${id}"]`);
    const box = $("#list");
    if (row && box) {
      const r = row.getBoundingClientRect(), b = box.getBoundingClientRect();
      // Already fully visible: leave the scroll position alone. Nudging it
      // pushes the group heading off the top for no reason.
      if (r.top < b.top || r.bottom > b.bottom) {
        row.scrollIntoView({ block: "nearest" });
      }
    }
  }
  renderDetail();
}

/* ───────────────────────────────────────── command palette ── */

function openPalette() {
  palOpen = true; palCursor = 0;
  $("#palette").hidden = false;
  $("#palette-q").value = "";
  paletteSearch("");
  $("#palette-q").focus();
}
function closePalette() { palOpen = false; $("#palette").hidden = true; }

function paletteSearch(q) {
  const s = q.trim().toLowerCase();
  palHits = (DATA ? DATA.trials : []).filter((t) => !s ||
    (t.title + " " + t.id + " " + (t.site || "") + " " + (t.blocking_reason || ""))
      .toLowerCase().includes(s)).slice(0, 40);
  palCursor = 0;
  paletteRender();
}
function paletteRender() {
  $("#palette-results").innerHTML = palHits.length
    ? palHits.map((t, i) => `
        <button class="presult ${i === palCursor ? "on" : ""}" data-id="${t.id}">
          <span class="sw" style="background:${SW[t.state]}"></span>
          <span class="pt">${esc(t.title || t.id)}</span>
          <span class="pid">${t.id}</span>
        </button>`).join("")
    : `<div class="pnone">No trial matches that.</div>`;
  $$(".presult").forEach((b) => b.addEventListener("click", () => {
    jumpTo(b.dataset.id);
  }));
}
function jumpTo(id) {
  const t = DATA.trials.find((x) => x.id === id);
  closePalette();
  if (!t) return;
  // Make sure the row is actually in the list before selecting it.
  if (filter && filter !== t.state) { filter = null; renderStrip(); wireStrip(); }
  if (t.state === "blocked") { blockedFilter = t.blocking_reason; filter = "blocked"; }
  renderList();
  select(id, true);
}

/* ───────────────────────────────────────────────── keyboard ── */

document.addEventListener("keydown", (e) => {
  const typing = /^(INPUT|TEXTAREA)$/.test(e.target.tagName);

  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    if (DATA) palOpen ? closePalette() : openPalette();
    return;
  }
  if (palOpen) {
    if (e.key === "Escape") { e.preventDefault(); closePalette(); }
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      palCursor = Math.max(0, Math.min(palHits.length - 1,
        palCursor + (e.key === "ArrowDown" ? 1 : -1)));
      paletteRender();
      $$(".presult")[palCursor]?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (palHits[palCursor]) jumpTo(palHits[palCursor].id);
    }
    return;
  }
  if (!DATA || typing) return;

  if (e.key === "/") { e.preventDefault(); openPalette(); return; }

  const rows = $$(".row");
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const i = rows.findIndex((r) => r.dataset.id === selId);
    const next = rows[Math.max(0, Math.min(rows.length - 1,
      (i < 0 ? (e.key === "ArrowDown" ? -1 : 0) : i) + (e.key === "ArrowDown" ? 1 : -1)))];
    if (next) select(next.dataset.id, true);
  } else if (e.key === "Escape") {
    // Step back one level: filtered list -> all trials -> the document.
    if (blockedFilter || filter) { clearFilter(); return; }
    showIntake();
    return;
  }
});

/* ───────────────────────────────────────────────────── flow ── */

function progress(on) {
  const el = $("#progress");
  el.className = "bar" + (on ? " go" : " done");
  if (!on) setTimeout(() => (el.className = "bar"), 480);
}

function clearFilter() {
  blockedFilter = null;
  filter = null;
  renderStrip(); wireStrip(); renderList();
  $("#list").scrollTop = 0;
  const first = $$(".row")[0];
  if (first) select(first.dataset.id);
}

function wireStrip() {
  $$(".cnt").forEach((b) => b.addEventListener("click", () => {
    filter = filter === b.dataset.state ? null : b.dataset.state;
    blockedFilter = null;
    if (filter === "blocked") blockedOpen = true;
    renderStrip(); wireStrip(); renderList();
    $("#list").scrollTop = 0;
    const first = $$(".row")[0];
    if (first) select(first.dataset.id);
  }));
  $("#work-go")?.addEventListener("click", () => {
    filter = "undetermined"; blockedFilter = null;
    renderStrip(); wireStrip(); renderList();
    $("#list").scrollTop = 0;
    const first = $$(".row")[0];
    if (first) select(first.dataset.id);
  });
  $("#palette-open")?.addEventListener("click", () => DATA && openPalette());
}

function showIntake() {
  $("#intake").hidden = false;
  $("#strip").hidden = true;
  $("#split").hidden = true;
  $("#perf").hidden = true;
  $("#back").hidden = true;
  $("#crumb").hidden = true;
  resetDocument();
}

function showResults() {
  $("#intake").hidden = true;
  $("#strip").hidden = false;
  $("#split").hidden = false;
  $("#back").hidden = false;
  const crumb = $("#crumb");
  crumb.textContent = SAMPLE_LOADED && SAMPLE
    ? SAMPLE.name : ($("#paper-title").textContent || "Patient");
  crumb.hidden = false;
}

async function run() {
  const report = $("#report").value.trim();
  if (!report) { $("#intake-hint").textContent = "Paste a note first."; return; }

  progress(true);
  $("#run").disabled = true;
  try {
    const res = await fetch("/api/assess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Only the test document carries a fixed index date. For an uploaded
      // note we have no idea when it was written, so the server dates it today.
      body: JSON.stringify({
        report,
        // An uploaded note is dated the visitor's today, not the server's.
        index_date: SAMPLE_LOADED && SAMPLE ? SAMPLE.index_date : localToday(),
      }),
    });
    const d = await res.json();
    if (d.error) throw new Error(d.error);

    DATA = d;
    filter = null; blockedFilter = null; blockedOpen = false;
    showResults();
    renderStrip(); wireStrip(); renderList();

    // Lead with the strongest story available: a dated trial if there is one.
    const dated = ranked("eligible_on_date");
    const first = dated[0] || ranked("eligible_now")[0] || DATA.trials[0];
    if (first) select(first.id);
    $("#list").scrollTop = 0;
  } catch (err) {
    showResults();
    $("#detail").innerHTML = `<div class="err">${esc(err.message)}</div>`;
  } finally {
    $("#run").disabled = false;
    progress(false);
  }
}

$("#run").addEventListener("click", run);
$("#back").addEventListener("click", showIntake);
$("#clear-filter").addEventListener("click", clearFilter);

/* The note is a textarea, so a bare Enter has to keep inserting newlines.
   Cmd/Ctrl-Enter is the standard "submit this composition" gesture. */
$("#report").addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); run(); }
});
$("#palette-q").addEventListener("input", (e) => paletteSearch(e.target.value));
$("#palette").addEventListener("click", (e) => {
  if (e.target.id === "palette") closePalette();
});
$("#palette-open").addEventListener("click", () => DATA && openPalette());

/* ─────────────────────────────────────────────── usage counters ── */
/* Three integers -- opened the page, loaded a document, ran a match -- so the
   question "did anyone use this" has an answer. There is no identifier of any
   kind here: no cookie, no stored id, nothing derived from the note. The only
   thing sent beyond the event name is document.referrer, which the server
   reduces to a known site name ("hacker news") or "other" before storing it.

   sendBeacon rather than fetch: it is queued by the browser and never delays
   rendering, and it still delivers if the visitor leaves immediately -- which
   is exactly the visit most worth counting during a launch.

   sessionStorage holds one flag so a reload inside the same tab is not counted
   twice. That flag never leaves the browser and dies with the tab. */
function pulse(event, referrer) {
  try {
    const body = JSON.stringify({ e: event, r: referrer || "" });
    if (navigator.sendBeacon) {
      navigator.sendBeacon("/api/pulse", new Blob([body], { type: "application/json" }));
    } else {
      fetch("/api/pulse", { method: "POST", body, keepalive: true });
    }
  } catch { /* a counter is never worth an error in a visitor's console */ }
}

try {
  if (!sessionStorage.getItem("tec.seen")) {
    sessionStorage.setItem("tec.seen", "1");
    pulse("visit", document.referrer);
  }
} catch {
  // Private mode and blocked site data throw on access. Count the visit
  // anyway; an over-count on a reload beats losing the visitor entirely.
  pulse("visit", document.referrer);
}

/* ─────────────────────────────────────────── document intake ── */
/* The landing asks for a document instead of handing you one. Everything is
   read in the browser with FileReader -- the file is never uploaded anywhere;
   only the text you then choose to match is POSTed to /api/assess. */

const MAX_BYTES = 200 * 1024;

/* The server runs in UTC; the visitor does not. Every date this product shows
   is relative to "today", so today has to be the user's, not the datacentre's. */
function localToday() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/* Accept anything that is genuinely text. Browsers report .md and .csv with an
   empty or odd MIME type, so the extension is checked too rather than trusting
   `type` alone. */
const TEXT_EXT = /\.(txt|text|md|markdown|csv|tsv|json|log|rtf|note)$/i;

function looksLikeText(file) {
  return (file.type && file.type.startsWith("text/")) ||
         file.type === "application/json" || TEXT_EXT.test(file.name) ||
         file.type === "";
}

function dropError(msg) {
  let el = $("#drop-err");
  if (!el) {
    el = document.createElement("div");
    el.id = "drop-err"; el.className = "drop-err";
    $("#choose").appendChild(el);
  }
  el.textContent = msg;
}
function clearDropError() { $("#drop-err")?.remove(); }

function showDocument(title, text, hint) {
  clearDropError();
  SAMPLE_LOADED = hint === SAMPLE_HINT;
  $("#report").value = text;
  $("#paper-title").textContent = title;
  $("#intake-hint").textContent = hint || "";
  $("#choose").hidden = true;
  $("#loaded").hidden = false;
  $("#run").focus();
}

function resetDocument() {
  $("#report").value = "";
  $("#loaded").hidden = true;
  $("#choose").hidden = false;
  clearDropError();
  $("#drop").focus();
}

function readFile(file) {
  if (!file) return;
  if (file.size > MAX_BYTES) {
    return dropError(`${file.name} is ${(file.size / 1024).toFixed(0)} KB. ` +
                     `The limit is 200 KB — this reads notes, not archives.`);
  }
  if (!looksLikeText(file)) {
    return dropError(`${file.name} is not a text file. PDF and Word are not ` +
                     `supported here; export or paste the note as plain text.`);
  }
  const fr = new FileReader();
  fr.onerror = () => dropError(`Could not read ${file.name}.`);
  fr.onload = () => {
    const text = String(fr.result || "").trim();
    if (!text) return dropError(`${file.name} is empty.`);
    // A binary file dragged in with a text-ish name shows up as replacement
    // characters; better to say so than to compile mojibake.
    if (/\uFFFD/.test(text.slice(0, 2000))) {
      return dropError(`${file.name} does not look like plain text.`);
    }
    showDocument(file.name, text, `${(file.size / 1024).toFixed(1)} KB · read in your browser`);
    // The test document is counted server-side when /api/samples is fetched,
    // so this path -- and only this path -- reports its own.
    pulse("doc");
  };
  fr.readAsText(file);
}

const SAMPLE_HINT = "test document";

$("#drop").addEventListener("click", () => $("#file").click());
$("#drop").addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#file").click(); }
});
$("#file").addEventListener("change", (e) => {
  readFile(e.target.files[0]);
  e.target.value = "";                  // re-selecting the same file re-fires
});

["dragenter", "dragover"].forEach((ev) =>
  $("#drop").addEventListener(ev, (e) => {
    e.preventDefault(); $("#drop").classList.add("over");
  }));
["dragleave", "drop"].forEach((ev) =>
  $("#drop").addEventListener(ev, (e) => {
    e.preventDefault(); $("#drop").classList.remove("over");
  }));
$("#drop").addEventListener("drop", (e) => readFile(e.dataTransfer?.files?.[0]));

// The page must not navigate away when a file is dropped outside the zone.
["dragover", "drop"].forEach((ev) =>
  window.addEventListener(ev, (e) => {
    if (!$("#drop").contains(e.target)) e.preventDefault();
  }));

$("#use-sample").addEventListener("click", async () => {
  try {
    if (!SAMPLE) SAMPLE = (await (await fetch(`/api/samples?today=${localToday()}`)).json())[0];
    showDocument(`${SAMPLE.name} — oncology progress note`, SAMPLE.report,
                 SAMPLE_HINT);
    $("#intake-hint").textContent =
      `index date ${fmtDate(SAMPLE.index_date)}`;
  } catch {
    dropError("Could not load the test document. Is the server running?");
  }
});

$("#clear-doc").addEventListener("click", resetDocument);
