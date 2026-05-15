// Bible RAG — Timeline view
// Horizontal-scrolling chronological view of every unit in the graph.

const SVG_NS = "http://www.w3.org/2000/svg";

// Eras: (label, start_year, end_year). Negative = BC.
const ERAS = [
  { key: "creation",   label: "Creation & Primeval", start: -4000, end: -2200 },
  { key: "patriarchs", label: "Patriarchs",          start: -2200, end: -1500 },
  { key: "exodus",     label: "Exodus & Conquest",   start: -1500, end: -1050 },
  { key: "kings",      label: "Kingdom",             start: -1050, end:  -586 },
  { key: "exile",      label: "Exile & Return",      start:  -586, end:  -150 },
  { key: "second",     label: "Second Temple",       start:  -150, end:    -4 },
  { key: "christ",     label: "Christ",              start:    -4, end:    33 },
  { key: "apostolic",  label: "Apostolic Age",       start:    33, end:   100 },
  { key: "eschaton",   label: "Eschaton",            start:   100, end:   400 },
];

// Heuristic mapping from slug keywords -> era key.
// Used when a unit has no theographic date.
const KEYWORD_ERA = [
  // Creation
  [/adam|eve|cain|abel|seth|enoch|methuselah|noah|babel|flood|primeval|genesis-5/i, "creation"],
  // Patriarchs
  [/abraham|isaac|jacob|esau|sarah|rebekah|rachel|leah|joseph-sold|melchizedek|hagar|ishmael|patriarch/i, "patriarchs"],
  // Exodus
  [/moses|aaron|miriam|pharaoh|exodus|passover|sinai|tabernacle|manna|bronze-serpent|wilderness|red-sea|joshua|judges|gideon|samson|ruth|boaz|deborah/i, "exodus"],
  // Kings
  [/david|solomon|saul|samuel|absalom|bathsheba|temple-first|elijah|elisha|ahab|jezebel|isaiah|jeremiah|kingdom|zion-davidic/i, "kings"],
  // Exile / Return
  [/exile|babylon|daniel|ezekiel|esther|nehemiah|ezra|cyrus|return|persia|haggai|zechariah|malachi/i, "exile"],
  // Second Temple
  [/maccabe|hasmonean|herod|intertestament|second-temple/i, "second"],
  // Christ
  [/jesus|christ|mary|joseph-husband|nativity|crucifix|resurrection|gospel|sermon-on-the-mount|beatitude|last-supper|gethsemane|calvary|golgotha|magi|baptism-of/i, "christ"],
  // Apostolic
  [/paul|peter|john-the-apostle|stephen|pentecost|acts|epistle|romans|corinth|ephesus|philippi|apostolic/i, "apostolic"],
  // Eschaton
  [/eschaton|second-coming|new-jerusalem|revelation|apocalypse|new-heaven|new-earth|parousia|judgment-day/i, "eschaton"],
];

// Type-level fallback era. Symbols/motifs/numbers etc. tend to be cross-era.
const TYPE_FALLBACK_ERA = {
  person: "kings",
  seed: "patriarchs",
  symbol: "exodus",
  motif: "kings",
  place: "kings",
  number: "exodus",
  title: "kings",
  structure: "exile",
  covenant: "exodus",
  festival: "exodus",
  miracle: "exodus",
  parable: "christ",
  prophecy: "exile",
  theophany: "exodus",
  office: "kings",
  lexeme: "exodus",
};

// Parse "1752–1085 BC" or "33 AD" → midpoint year.
function parseYear(str) {
  if (!str || typeof str !== "string") return null;
  const isBC = /BC/i.test(str);
  const isAD = /AD|CE/i.test(str);
  // Find one or two numbers
  const nums = str.match(/\d+/g);
  if (!nums) return null;
  let y;
  if (nums.length >= 2) {
    y = (parseInt(nums[0]) + parseInt(nums[1])) / 2;
  } else {
    y = parseInt(nums[0]);
  }
  return isBC ? -y : (isAD ? y : -y); // default BC if unspecified
}

// Decide a year for a unit.
function eraFromSlug(slug) {
  for (const [re, key] of KEYWORD_ERA) {
    if (re.test(slug)) return key;
  }
  return null;
}
function eraMidYear(key) {
  const e = ERAS.find(x => x.key === key);
  return e ? (e.start + e.end) / 2 : 0;
}

async function placeUnits(nodes) {
  // For each node, derive a year. We do a best-effort second pass for persons
  // by fetching theographic data for the persons we care about.
  // To keep network minimal, we only fetch person unit details (there are ~15).
  const personSlugs = nodes
    .filter(n => n.data.type === "person")
    .map(n => n.data.id);

  const personDates = {};
  await Promise.all(personSlugs.map(async slug => {
    try {
      const r = await fetch(`/api/unit/${encodeURIComponent(slug)}`);
      if (!r.ok) return;
      const d = await r.json();
      const t = d.theographic;
      if (t) {
        const y = parseYear(t.birth) ?? parseYear(t.death);
        if (y != null) personDates[slug] = y;
      }
    } catch (_) {}
  }));

  const placed = nodes.map(n => {
    const slug = n.data.id;
    const type = n.data.type;
    let year = personDates[slug];
    if (year == null) {
      const key = eraFromSlug(slug) || TYPE_FALLBACK_ERA[type] || "kings";
      // Jitter a bit within the era so dots spread
      const e = ERAS.find(x => x.key === key);
      const span = e.end - e.start;
      // deterministic jitter from slug hash
      let h = 0;
      for (let i = 0; i < slug.length; i++) h = (h * 31 + slug.charCodeAt(i)) | 0;
      const t = ((Math.abs(h) % 1000) / 1000); // 0..1
      year = e.start + span * (0.15 + 0.7 * t);
    }
    return { ...n.data, year };
  });
  return placed;
}

// ---------- Render ----------
function el(tag, attrs = {}, parent = null) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

function yearLabel(y) {
  const a = Math.abs(Math.round(y));
  return y < 0 ? `${a} BC` : `${a} AD`;
}

let SVG, SCALE_X, HEIGHT, WIDTH;
const PAD_LEFT = 80, PAD_RIGHT = 80, AXIS_Y = 0;
const ERA_TOP = 28, AXIS_OFFSET = 60;
const PX_PER_YEAR = 0.9; // tunable: total width = span * PX_PER_YEAR

function scaleX(year) {
  // Map from ERAS.start (min) … ERAS.end (max) → [PAD_LEFT, WIDTH-PAD_RIGHT]
  const min = ERAS[0].start;
  const max = ERAS[ERAS.length - 1].end;
  return PAD_LEFT + ((year - min) / (max - min)) * (WIDTH - PAD_LEFT - PAD_RIGHT);
}

function render(units, edges) {
  const wrap = document.getElementById("timeline-wrap");
  HEIGHT = wrap.clientHeight;
  const totalYears = ERAS[ERAS.length - 1].end - ERAS[0].start;
  WIDTH = Math.max(wrap.clientWidth, totalYears * PX_PER_YEAR + PAD_LEFT + PAD_RIGHT);

  SVG = document.getElementById("timeline-svg");
  SVG.setAttribute("width", WIDTH);
  SVG.setAttribute("height", HEIGHT);
  SVG.innerHTML = "";

  // Era bands
  ERAS.forEach((e, i) => {
    const x1 = scaleX(e.start), x2 = scaleX(e.end);
    el("rect", {
      class: "era-band" + (i % 2 ? " alt" : ""),
      x: x1, y: 0, width: x2 - x1, height: HEIGHT
    }, SVG);
    el("line", {
      class: "era-divider",
      x1: x2, x2: x2, y1: 0, y2: HEIGHT
    }, SVG);
    const label = el("text", {
      class: "era-label",
      x: (x1 + x2) / 2,
      y: ERA_TOP,
      "text-anchor": "middle"
    }, SVG);
    label.textContent = e.label;
  });

  // Axis line
  const axisY = HEIGHT - 40;
  el("line", {
    class: "axis",
    x1: PAD_LEFT, x2: WIDTH - PAD_RIGHT, y1: axisY, y2: axisY
  }, SVG);
  // Ticks at era boundaries
  ERAS.forEach(e => {
    const x = scaleX(e.start);
    el("line", { class: "axis-tick", x1: x, x2: x, y1: axisY, y2: axisY + 6 }, SVG);
    const t = el("text", {
      class: "axis-tick-label",
      x: x, y: axisY + 20, "text-anchor": "middle"
    }, SVG);
    t.textContent = yearLabel(e.start);
  });
  // Final tick
  const lastEnd = ERAS[ERAS.length - 1].end;
  const xEnd = scaleX(lastEnd);
  el("line", { class: "axis-tick", x1: xEnd, x2: xEnd, y1: axisY, y2: axisY + 6 }, SVG);
  const tEnd = el("text", {
    class: "axis-tick-label",
    x: xEnd, y: axisY + 20, "text-anchor": "middle"
  }, SVG);
  tEnd.textContent = yearLabel(lastEnd);

  // Lane assignment (vertical layout to avoid overlap)
  // Sort by x, then greedy assign into lanes where x is far enough.
  const LANE_H = 22;
  const TOP_BAND = 56; // below era labels
  const BOTTOM_BAND = axisY - 30;
  const LANES = Math.max(8, Math.floor((BOTTOM_BAND - TOP_BAND) / LANE_H));

  // Pre-compute x per unit
  const placed = units.map(u => ({ ...u, x: scaleX(u.year), lane: -1 }));
  placed.sort((a, b) => a.x - b.x);
  const laneCursor = new Array(LANES).fill(-Infinity);
  for (const u of placed) {
    // Prefer lanes based on type "band" so seeds tend to cluster
    // Just find first lane where laneCursor[i] + minGap <= u.x
    const minGap = 70 + (u.label?.length || 4) * 4;
    let chosen = -1;
    // Try a stable starting lane derived from type for visual grouping
    const typeOrder = ["seed","person","place","covenant","prophecy","festival","miracle","theophany","title","office","parable","symbol","motif","structure","number","lexeme"];
    const start = Math.max(0, typeOrder.indexOf(u.type)) % LANES;
    for (let i = 0; i < LANES; i++) {
      const li = (start + i) % LANES;
      if (laneCursor[li] + minGap <= u.x) { chosen = li; break; }
    }
    if (chosen === -1) chosen = (start + LANES - 1) % LANES;
    u.lane = chosen;
    u.y = TOP_BAND + chosen * LANE_H + 8;
    laneCursor[chosen] = u.x;
  }

  // Index by slug for edge lookup
  const bySlug = {};
  placed.forEach(u => { bySlug[u.id] = u; });

  // Draw arcs first (so dots sit on top)
  const arcLayer = el("g", { class: "arc-layer" }, SVG);
  // Highlight typological / fulfills connections
  const importantEdgeTypes = new Set([
    "fulfills", "prefigures", "prefigured_by", "typifies", "typified_by",
    "has_motif", "uses_symbol"
  ]);
  edges.forEach(e => {
    const a = bySlug[e.data.source];
    const b = bySlug[e.data.target];
    if (!a || !b) return;
    // Only arc edges that meaningfully cross time
    const dx = Math.abs(a.x - b.x);
    if (dx < 30) return;
    const t = e.data.type || "";
    if (!importantEdgeTypes.has(t)) {
      // Skip lexeme noise + keep visually quiet
      if (t === "shares_lexeme" || t === "co_occurs_with") return;
    }
    // Limit total arcs to keep readable: skip ~half of less-important
    if (t !== "fulfills" && t !== "prefigures" && Math.random() > 0.35) return;

    const x1 = a.x, x2 = b.x;
    const xm = (x1 + x2) / 2;
    const lift = Math.min(180, 30 + dx * 0.18);
    // Curve upward
    const yBase = Math.min(a.y, b.y) - 6;
    const d = `M ${x1} ${a.y} Q ${xm} ${yBase - lift} ${x2} ${b.y}`;
    const path = el("path", {
      class: "arc" + (t === "fulfills" || t === "prefigures" ? " fulfills" : ""),
      d
    }, arcLayer);
    path.dataset.from = a.id;
    path.dataset.to = b.id;
  });

  // Draw dots + labels
  const dotLayer = el("g", { class: "dot-layer" }, SVG);
  placed.forEach(u => {
    const isMajor = u.type === "seed" || u.type === "person";
    const r = isMajor ? 6 : 4;
    const dot = el("circle", {
      class: "unit-dot " + u.type,
      cx: u.x, cy: u.y, r,
      stroke: "#0b0e17", "stroke-width": 1.5
    }, dotLayer);
    dot.dataset.slug = u.id;
    dot.addEventListener("mouseenter", evt => showTip(evt, u));
    dot.addEventListener("mousemove", moveTip);
    dot.addEventListener("mouseleave", hideTip);
    dot.addEventListener("click", () => openDetail(u.id));

    if (isMajor || u.label.length < 18) {
      const lbl = el("text", {
        class: "unit-label" + (isMajor ? " bright" : ""),
        x: u.x + r + 4, y: u.y + 3.5
      }, dotLayer);
      lbl.textContent = u.label;
    }
  });
}

// ---------- Tooltip ----------
const tip = document.getElementById("tooltip");
function showTip(evt, u) {
  tip.innerHTML = `
    <div class="tip-type">${u.type}</div>
    <div class="tip-title">${escapeHtml(u.label)}</div>
    <div class="tip-meta">${yearLabel(u.year)}${u.confidence ? " · " + u.confidence : ""}</div>
  `;
  tip.classList.add("visible");
  moveTip(evt);
}
function moveTip(evt) {
  tip.style.left = (evt.clientX + 14) + "px";
  tip.style.top = (evt.clientY + 14) + "px";
}
function hideTip() { tip.classList.remove("visible"); }

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

// ---------- Detail panel ----------
const detail = document.getElementById("detail");
const detailContent = document.getElementById("detail-content");
document.querySelector(".detail-close").addEventListener("click", () => {
  detail.classList.remove("open");
});

async function openDetail(slug) {
  detail.classList.add("open");
  detailContent.innerHTML = `<p style="color: var(--text-tertiary)">Loading…</p>`;
  try {
    const r = await fetch(`/api/unit/${encodeURIComponent(slug)}`);
    const d = await r.json();
    const out = (d.neighbors_out || []).slice(0, 12);
    const inn = (d.neighbors_in || []).slice(0, 8);
    const renderBody = (typeof marked !== "undefined")
      ? marked.parse(d.body_md || "")
      : `<pre>${escapeHtml(d.body_md || "")}</pre>`;
    detailContent.innerHTML = `
      <h2>${escapeHtml(d.title)}</h2>
      <span class="badge">${d.type}${d.confidence ? " · " + d.confidence : ""}</span>
      <div class="body">${renderBody}</div>
      ${out.length ? `
        <div class="neighbors-section">
          <h3>Leads to</h3>
          ${out.map(n => `
            <div class="neighbor" data-slug="${escapeHtml(n.slug)}">
              <span class="edge-type">${escapeHtml(n.edge_type || "")}</span>
              <span>${escapeHtml(n.title)}</span>
            </div>`).join("")}
        </div>` : ""}
      ${inn.length ? `
        <div class="neighbors-section">
          <h3>Referenced by</h3>
          ${inn.map(n => `
            <div class="neighbor" data-slug="${escapeHtml(n.slug)}">
              <span class="edge-type">${escapeHtml(n.edge_type || "")}</span>
              <span>${escapeHtml(n.title)}</span>
            </div>`).join("")}
        </div>` : ""}
    `;
    detailContent.querySelectorAll(".neighbor").forEach(el => {
      el.addEventListener("click", () => openDetail(el.dataset.slug));
    });
    detailContent.querySelector(".detail-close")?.addEventListener("click", () => detail.classList.remove("open"));
  } catch (e) {
    detailContent.innerHTML = `<p style="color: var(--motif)">Could not load: ${escapeHtml(e.message)}</p>`;
  }
}

// ---------- Intro dismiss ----------
document.getElementById("intro-dismiss").addEventListener("click", () => {
  document.getElementById("intro").classList.add("hidden");
});

// ---------- Boot ----------
(async function boot() {
  try {
    const r = await fetch("/api/graph");
    const data = await r.json();
    const units = await placeUnits(data.elements.nodes);
    render(units, data.elements.edges);
    document.getElementById("loader").classList.add("hidden");
  } catch (e) {
    document.getElementById("loader").textContent = "Failed: " + e.message;
  }
})();

// Re-render on resize (debounced)
let resizeT;
window.addEventListener("resize", () => {
  clearTimeout(resizeT);
  resizeT = setTimeout(async () => {
    const r = await fetch("/api/graph");
    const data = await r.json();
    const units = await placeUnits(data.elements.nodes);
    render(units, data.elements.edges);
  }, 250);
});
