// Bible RAG — Sigma.js + Graphology + ForceAtlas2
// Auto-layout, vibrant colors, smooth WebGL rendering.

const COLORS = {
    seed:      '#a78bfa',
    symbol:    '#2dd4bf',
    motif:     '#fb923c',
    person:    '#f472b6',
    place:     '#facc15',
    number:    '#38bdf8',
    title:     '#4ade80',
    structure: '#c084fc',
    covenant:  '#ef4444',
    festival:  '#eab308',
    miracle:   '#06b6d4',
    parable:   '#84cc16',
    prophecy:  '#d946ef',
    theophany: '#e0e7ff',
    office:    '#f97316',
    lexeme:    '#94a3b8',
};

const EDGE_COLOR_DEFAULT = 'rgba(120, 130, 170, 0.18)';
const EDGE_COLOR_MOTIF   = 'rgba(251, 146, 60, 0.28)';

let sigmaInstance = null;
let graph = null;
let highlightedNode = null;
let allEdges = [];  // Snapshot of every edge so PaRDeS toggles re-add hidden ones.

async function init() {
    const [graphData, hubsData] = await Promise.all([
        fetch('/api/graph').then(r => r.json()),
        fetch('/api/hubs?top_n=15').then(r => r.json()),
    ]);

    // Build the Graphology graph
    graph = new graphology.Graph({ multi: false });

    for (const n of graphData.elements.nodes) {
        const t = n.data.type;
        graph.addNode(n.data.id, {
            label: n.data.label,
            unitType: t,
            color: COLORS[t] || '#888',
            // Random initial position; ForceAtlas2 will rearrange.
            x: Math.random(),
            y: Math.random(),
            size: 8, // base; updated below by degree
        });
    }

    allEdges = graphData.elements.edges;
    for (const e of allEdges) {
        if (graph.hasEdge(e.data.source, e.data.target)) continue;
        graph.addEdge(e.data.source, e.data.target, {
            edgeType: e.data.type,
            pardes: e.data.pardes,
            color: e.data.type === 'has_motif' ? EDGE_COLOR_MOTIF : EDGE_COLOR_DEFAULT,
            size: 1,
        });
    }

    // Size nodes by degree — hubs are visually dominant
    graph.forEachNode((node, attrs) => {
        const deg = graph.degree(node);
        graph.setNodeAttribute(node, 'size', 5 + Math.sqrt(deg) * 3);
    });

    // ForceAtlas2 layout — settles into a nice arrangement automatically
    const settings = graphologyLibrary.layoutForceAtlas2.inferSettings(graph);
    graphologyLibrary.layoutForceAtlas2.assign(graph, {
        iterations: 600,
        settings: {
            ...settings,
            gravity: 1.5,
            scalingRatio: 18,
            slowDown: 1.6,
            barnesHutOptimize: true,
            strongGravityMode: false,
            adjustSizes: true,
        },
    });

    // Render with Sigma
    sigmaInstance = new Sigma(graph, document.getElementById('sigma-container'), {
        renderEdgeLabels: false,
        labelColor: { color: '#e6e9f2' },
        labelSize: 12,
        labelWeight: '500',
        labelFont: 'Inter, sans-serif',
        labelDensity: 0.7,
        labelGridCellSize: 80,
        labelRenderedSizeThreshold: 6,
        defaultEdgeColor: EDGE_COLOR_DEFAULT,
        zIndex: true,
    });

    sigmaInstance.on('clickNode', ({ node }) => {
        highlightNode(node);
        loadDetail(node);
    });

    sigmaInstance.on('enterNode', ({ node }) => {
        const label = graph.getNodeAttribute(node, 'label');
        showHover(label);
        document.body.style.cursor = 'pointer';
    });

    sigmaInstance.on('leaveNode', () => {
        hideHover();
        document.body.style.cursor = 'default';
    });

    populateHubs(hubsData.hubs);
    wireSearch();
    wireControls();
    wirePardesToggles();
}

function highlightNode(nodeId) {
    if (!graph) return;
    if (highlightedNode) {
        graph.setNodeAttribute(highlightedNode, 'highlighted', false);
    }
    graph.setNodeAttribute(nodeId, 'highlighted', true);
    highlightedNode = nodeId;

    // Soft camera animation to center the node
    const attrs = graph.getNodeAttributes(nodeId);
    sigmaInstance.getCamera().animate(
        { x: attrs.x, y: attrs.y, ratio: 0.5 },
        { duration: 600 },
    );
    sigmaInstance.refresh();
}

function showHover(text) {
    const el = document.getElementById('hover-info');
    el.textContent = text;
    el.classList.add('visible');
}

function hideHover() {
    document.getElementById('hover-info').classList.remove('visible');
}

function populateHubs(hubs) {
    const list = document.getElementById('hubs-list');
    list.innerHTML = hubs.map(h => `
        <li data-slug="${h.slug}">
            <span class="dot" style="background:${COLORS[h.type]}; width:8px; height:8px"></span>
            <span class="hub-title">${h.title}</span>
            <span class="degree">${h.degree}</span>
        </li>
    `).join('');
    list.querySelectorAll('li').forEach(li => {
        li.addEventListener('click', () => {
            const slug = li.dataset.slug;
            highlightNode(slug);
            loadDetail(slug);
        });
    });
}

async function loadDetail(slug) {
    const r = await fetch(`/api/unit/${encodeURIComponent(slug)}`).then(r => r.json());
    const html = `
        <div class="detail-header">
            <h2>${r.title}</h2>
            <div class="meta">
                <span class="badge ${r.type}">${r.type}</span>
                ${r.status ? `<span class="badge">${r.status}</span>` : ''}
                ${r.confidence ? `<span class="badge">conf: ${r.confidence}</span>` : ''}
            </div>
        </div>
        <div class="body">${marked.parse(r.body_md || '')}</div>
        ${theographicSection(r.theographic)}
        ${neighborSection('Connects to', r.neighbors_out)}
        ${neighborSection('Referenced by', r.neighbors_in)}
    `;
    document.getElementById('detail-panel').innerHTML = html;
    document.querySelectorAll('#detail-panel .neighbor').forEach(el => {
        el.addEventListener('click', () => {
            const s = el.dataset.slug;
            highlightNode(s);
            loadDetail(s);
        });
    });
}

function theographicSection(t) {
    if (!t) return '';
    const rows = [];
    if (t.birth) rows.push(['Born', t.birth + (t.birth_place ? ` · ${t.birth_place.name}` : '')]);
    if (t.death) rows.push(['Died', t.death + (t.death_place ? ` · ${t.death_place.name}` : '')]);
    if (t.father) rows.push(['Father', t.father]);
    if (t.mother) rows.push(['Mother', t.mother]);
    if (t.gender) rows.push(['Gender', t.gender]);
    if (!rows.length) return '';
    return `
        <div class="theographic">
            <h3>Biographical (Theographic)</h3>
            <dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>
            ${t.summary ? `<details class="theo-summary"><summary>Easton's summary</summary>${marked.parse(t.summary)}</details>` : ''}
        </div>
    `;
}

function scoreColor(s) {
    if (s == null) return null;
    if (s >= 0.85) return '#34d399';   // emerald — canonical
    if (s >= 0.65) return '#a78bfa';   // violet — plausible
    if (s >= 0.45) return '#fbbf24';   // amber — thin
    return '#94a3b8';                  // gray — weak (still shown)
}

function neighborSection(label, items) {
    if (!items || items.length === 0) return '';
    return `
        <div class="neighbors">
            <h3>${label} (${items.length})</h3>
            ${items.map(n => {
                const c = scoreColor(n.score);
                const badge = (n.score != null)
                    ? `<span class="score-badge" style="background:${c}" title="${(n.rationale || '').replace(/"/g, '&quot;')}">${n.score.toFixed(2)}</span>`
                    : '';
                return `
                <div class="neighbor" data-slug="${n.slug}" ${n.rationale ? `title="${n.rationale.replace(/"/g, '&quot;')}"` : ''}>
                    ${badge}
                    <span class="edge-type">${n.edge_type.replace(/_/g, ' ')}</span>
                    <span class="neighbor-title">${n.title}</span>
                </div>`;
            }).join('')}
        </div>
    `;
}

function wireSearch() {
    const input = document.getElementById('search-input');
    const results = document.getElementById('search-results');
    let timer = null;

    input.addEventListener('input', () => {
        clearTimeout(timer);
        const q = input.value.trim();
        if (!q) { results.innerHTML = ''; return; }
        timer = setTimeout(async () => {
            const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`).then(r => r.json());
            results.innerHTML = r.results.map(x => `
                <div class="result" data-slug="${x.slug}">
                    <div class="title">${x.title}</div>
                    <div class="snippet">${(x.snippet || '').replace(/<<(.+?)>>/g, '<mark>$1</mark>')}</div>
                </div>
            `).join('');
            results.querySelectorAll('.result').forEach(el => {
                el.addEventListener('click', () => {
                    const s = el.dataset.slug;
                    highlightNode(s);
                    loadDetail(s);
                });
            });
        }, 180);
    });
}

function wirePardesToggles() {
    const toggles = document.querySelectorAll('.pardes-toggle input');
    const applyFilter = () => {
        const active = new Set();
        document.querySelectorAll('.pardes-toggle').forEach(t => {
            const cb = t.querySelector('input');
            if (cb.checked) active.add(t.dataset.layer);
        });
        if (!graph) return;
        // Edges that exist in `graph` already — toggle visibility via hidden attr.
        graph.forEachEdge((edge, attrs) => {
            const visible = active.has(attrs.pardes || 'remez');
            graph.setEdgeAttribute(edge, 'hidden', !visible);
        });
        sigmaInstance.refresh();
    };
    toggles.forEach(cb => cb.addEventListener('change', applyFilter));
}

function wireControls() {
    document.getElementById('btn-relayout').addEventListener('click', () => {
        if (!graph) return;
        // Quick re-jitter and re-run for variety
        graph.forEachNode((node) => {
            graph.setNodeAttribute(node, 'x', Math.random());
            graph.setNodeAttribute(node, 'y', Math.random());
        });
        graphologyLibrary.layoutForceAtlas2.assign(graph, {
            iterations: 600,
            settings: {
                gravity: 1.5,
                scalingRatio: 18,
                slowDown: 1.6,
                barnesHutOptimize: true,
                adjustSizes: true,
            },
        });
        sigmaInstance.refresh();
    });

    document.getElementById('btn-reset-zoom').addEventListener('click', () => {
        sigmaInstance.getCamera().animatedReset();
    });
}

document.addEventListener('DOMContentLoaded', init);
