// Bible RAG — Reading Thread (Wikipedia-like deep dive)

const START_PICKS = [
  { slug: "seed:Abraham-Isaac",        label: "Abraham & Isaac",       sub: "Genesis 22 → Calvary" },
  { slug: "seed:Passover-Lamb",        label: "The Passover Lamb",     sub: "Exodus 12 → John 1:29" },
  { slug: "person:David",              label: "King David",            sub: "Shepherd-king typology" },
  { slug: "seed:Jonah-Three-Days",     label: "Jonah's Three Days",    sub: "Resurrection sign" },
  { slug: "seed:Bronze-Serpent",       label: "The Bronze Serpent",    sub: "Numbers 21 → John 3" },
  { slug: "seed:Melchizedek",          label: "Melchizedek",           sub: "Eternal priesthood" },
  { slug: "seed:Manna-Bread-Of-Life",  label: "Manna & Bread of Life", sub: "Exodus 16 → John 6" },
  { slug: "seed:Adam-Second-Adam",     label: "The Two Adams",         sub: "Romans 5 typology" },
];

const TOP_N = 12;

const state = {
  current: null,
  trail: [],          // [{slug, title}]
  tab: "out",         // "out" | "in"
};

const $ = sel => document.querySelector(sel);

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

// ----- Start screen -----
function renderStart() {
  $("#content").innerHTML = `
    <div class="start-screen">
      <h2>Pull a thread.</h2>
      <p>Pick any seed, person, or typology. We'll show you what it is and the strongest patterns that connect it across scripture. Click any card to follow the thread further — like Wikipedia for the Bible.</p>
      <div class="start-grid">
        ${START_PICKS.map(p => `
          <div class="start-card" data-slug="${escapeHtml(p.slug)}">
            <div class="label">${escapeHtml(p.label)}</div>
            <div class="sub">${escapeHtml(p.sub)}</div>
          </div>`).join("")}
      </div>
    </div>
  `;
  $("#content").querySelectorAll(".start-card").forEach(c => {
    c.addEventListener("click", () => loadUnit(c.dataset.slug));
  });
}

// ----- Trail (reading path) -----
function renderTrail() {
  const list = $("#trail-list");
  if (!state.trail.length) {
    list.innerHTML = `<div style="color: var(--text-tertiary); font-size: 12px; padding: 8px 10px;">No path yet — click a card.</div>`;
    return;
  }
  list.innerHTML = state.trail.map((t, i) => `
    <div class="trail-item ${t.slug === state.current ? 'current' : ''}" data-slug="${escapeHtml(t.slug)}">
      ${escapeHtml(t.title)}
    </div>
  `).join("");
  list.querySelectorAll(".trail-item").forEach(el => {
    el.addEventListener("click", () => loadUnit(el.dataset.slug));
  });
}

// ----- Article -----
async function loadUnit(slug) {
  if (!slug) return;
  $("#content").innerHTML = `<div id="loader">Loading…</div>`;
  try {
    const r = await fetch(`/api/unit/${encodeURIComponent(slug)}`);
    if (!r.ok) throw new Error("Not found: " + slug);
    const d = await r.json();
    state.current = slug;
    // Append to trail if not last
    const last = state.trail[state.trail.length - 1];
    if (!last || last.slug !== slug) {
      // If the slug is already earlier in the trail, truncate to it
      const idx = state.trail.findIndex(t => t.slug === slug);
      if (idx >= 0) state.trail = state.trail.slice(0, idx + 1);
      else state.trail.push({ slug, title: d.title });
    }
    renderUnit(d);
    renderTrail();
    window.scrollTo({ top: 0, behavior: "smooth" });
    history.replaceState(null, "", `#${encodeURIComponent(slug)}`);
  } catch (e) {
    $("#content").innerHTML = `<p style="color: var(--motif); padding: 40px 0;">${escapeHtml(e.message)}</p>`;
  }
}

function rankNeighbors(arr) {
  // Sort by score desc, nulls last; prefer fulfills/prefigures edges.
  const weight = t => {
    if (!t) return 0;
    if (t === "fulfills" || t === "prefigures" || t === "typifies") return 2;
    if (t === "shares_lexeme") return -1;
    return 1;
  };
  return [...arr].sort((a, b) => {
    const wa = weight(a.edge_type), wb = weight(b.edge_type);
    if (wa !== wb) return wb - wa;
    const sa = a.score == null ? -Infinity : a.score;
    const sb = b.score == null ? -Infinity : b.score;
    return sb - sa;
  });
}

function renderUnit(d) {
  const outRanked = rankNeighbors(d.neighbors_out || []);
  const inRanked  = rankNeighbors(d.neighbors_in  || []);
  const visible = state.tab === "out" ? outRanked : inRanked;
  const top = visible.slice(0, TOP_N);

  const theo = d.theographic;
  const subtitle = theo
    ? [theo.birth ? `Born ${theo.birth}` : null,
       theo.death ? `Died ${theo.death}` : null,
       theo.father ? `Father: ${theo.father}` : null]
       .filter(Boolean).join(" · ")
    : "";

  const renderBody = (typeof marked !== "undefined")
    ? marked.parse(d.body_md || "")
    : `<pre>${escapeHtml(d.body_md || "")}</pre>`;

  $("#content").innerHTML = `
    <article>
      <div class="article-header">
        <span class="badge">${escapeHtml(d.type)}${d.confidence ? " · " + escapeHtml(d.confidence) : ""}</span>
        <h1>${escapeHtml(d.title)}</h1>
        ${subtitle ? `<div class="subtitle">${escapeHtml(subtitle)}</div>` : ""}
      </div>

      <div class="body">${renderBody}</div>

      <section class="connections">
        <div class="connections-header">
          <h2>Connected threads</h2>
          <span class="count">${outRanked.length} outgoing · ${inRanked.length} incoming</span>
        </div>
        <div class="section-tabs">
          <button class="section-tab ${state.tab === 'out' ? 'active' : ''}" data-tab="out">Leads to (${outRanked.length})</button>
          <button class="section-tab ${state.tab === 'in' ? 'active' : ''}" data-tab="in">Referenced by (${inRanked.length})</button>
        </div>
        ${top.length === 0 ? `<p style="color: var(--text-tertiary); font-style: italic;">No connections yet.</p>` : `
        <div class="cards">
          ${top.map(n => {
            const score = n.score == null ? null : Number(n.score);
            const tier = score == null ? "" : (score >= 0.8 ? "score-high" : score >= 0.6 ? "score-mid" : "");
            return `
            <div class="card ${tier}" data-slug="${escapeHtml(n.slug)}">
              <div class="card-type"><span class="card-dot ${escapeHtml(n.type)}"></span>${escapeHtml(n.type)}</div>
              <div class="card-title">${escapeHtml(n.title)}</div>
              <div class="card-edge">${escapeHtml(n.edge_type || "related")}${score != null ? " · " + score.toFixed(2) : ""}</div>
              ${n.rationale ? `<div class="card-rationale">${escapeHtml(n.rationale)}</div>` : ""}
            </div>`;
          }).join("")}
        </div>`}
      </section>
    </article>
  `;

  // Wire up cards
  $("#content").querySelectorAll(".card").forEach(c => {
    c.addEventListener("click", () => loadUnit(c.dataset.slug));
  });
  $("#content").querySelectorAll(".section-tab").forEach(t => {
    t.addEventListener("click", () => {
      state.tab = t.dataset.tab;
      renderUnit(d);
    });
  });
}

// ----- Search -----
let searchTimer;
$("#search").addEventListener("input", e => {
  clearTimeout(searchTimer);
  const q = e.target.value.trim();
  const hits = $("#search-hits");
  if (!q) { hits.innerHTML = ""; return; }
  searchTimer = setTimeout(async () => {
    try {
      const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=8`);
      const d = await r.json();
      if (!d.results.length) {
        hits.innerHTML = `<div style="color: var(--text-tertiary); font-size: 12px; padding: 6px 8px;">No matches.</div>`;
        return;
      }
      hits.innerHTML = d.results.map(r => `
        <div class="search-hit" data-slug="${escapeHtml(r.slug)}">
          <strong style="color: var(--text-primary);">${escapeHtml(r.title)}</strong>
          <div style="font-size: 10px; color: var(--text-tertiary); font-family: 'JetBrains Mono', monospace; margin-top: 2px;">${escapeHtml(r.type)}</div>
        </div>
      `).join("");
      hits.querySelectorAll(".search-hit").forEach(el => {
        el.addEventListener("click", () => {
          loadUnit(el.dataset.slug);
          $("#search").value = "";
          hits.innerHTML = "";
        });
      });
    } catch (_) {}
  }, 200);
});

// ----- Boot -----
(function boot() {
  renderTrail();
  const hash = decodeURIComponent((location.hash || "").replace(/^#/, ""));
  if (hash) loadUnit(hash);
  else renderStart();
})();
