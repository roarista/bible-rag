// Bible RAG — Sigma.js + Graphology + ForceAtlas2
// Auto-layout, vibrant colors, smooth WebGL rendering.

const COLORS = {
    seed:   '#a78bfa',
    symbol: '#2dd4bf',
    motif:  '#fb923c',
};

const EDGE_COLOR_DEFAULT = 'rgba(120, 130, 170, 0.18)';
const EDGE_COLOR_MOTIF   = 'rgba(251, 146, 60, 0.28)';

let sigmaInstance = null;
let graph = null;
let highlightedNode = null;

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

    for (const e of graphData.elements.edges) {
        if (graph.hasEdge(e.data.source, e.data.target)) continue;
        graph.addEdge(e.data.source, e.data.target, {
            edgeType: e.data.type,
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

function neighborSection(label, items) {
    if (!items || items.length === 0) return '';
    return `
        <div class="neighbors">
            <h3>${label} (${items.length})</h3>
            ${items.map(n => `
                <div class="neighbor" data-slug="${n.slug}">
                    <span class="edge-type">${n.edge_type.replace('_', ' ')}</span>
                    <span>${n.title}</span>
                </div>
            `).join('')}
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
