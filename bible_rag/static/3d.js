/* Bible RAG — 3D meaning graph
 *
 * Library: 3d-force-graph (vasturiano) UMD build over three.js.
 * Renders nodes as glowing spheres in 3D, color-coded by unit type,
 * with auto-rotation, hover labels, click-to-open sidebar, and search.
 */

(function () {
  'use strict';

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
    // Taxonomy v2
    'chiasm':           '#22d3ee', 'inclusio':         '#22d3ee',
    'parallelism':      '#67e8f9', 'hapax-legomenon':  '#0891b2',
    'gematria':         '#0e7490', 'acrostic':         '#06b6d4',
    'wordplay':         '#155e75',
    'lament':           '#fb7185', 'oath':             '#f43f5e',
    'doxology':         '#fda4af', 'beatitude':        '#fecdd3',
    'woe':              '#9f1239', 'blessing-form':    '#fecaca',
    'curse-form':       '#7f1d1d', 'enigma':           '#be123c',
    'dream':            '#fbbf24', 'vision':           '#fcd34d',
    'genealogy':        '#92400e', 'naming-etiology':  '#b45309',
    'call-narrative':   '#d97706',
    'typological-fulfillment': '#7c3aed', 'antitype':   '#6d28d9',
    'recapitulation':   '#8b5cf6', 'reversal':         '#a855f7',
    'anti-parallel':    '#581c87', 'anti-motif':       '#3b0764',
    'psalm-type':       '#5eead4', 'song':             '#14b8a6',
    'prayer-formula':   '#0d9488', 'hymn':             '#0f766e',
  };
  const DEFAULT_COLOR = '#94a3b8';

  // ============== DOM ==============
  const $graph = document.getElementById('graph');
  const $loader = document.getElementById('loader');
  const $hoverLabel = document.getElementById('hover-label');
  const $sidebar = document.getElementById('sidebar');
  const $sidebarContent = document.getElementById('sidebar-content');
  const $sidebarClose = document.getElementById('sidebar-close');
  const $searchInput = document.getElementById('search-input');
  const $searchResults = document.getElementById('search-results');
  const $btnReset = document.getElementById('btn-reset');
  const $btnRotate = document.getElementById('btn-rotate');
  const $starfield = document.getElementById('starfield');

  // ============== Starfield ==============
  function drawStarfield() {
    const ctx = $starfield.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const resize = () => {
      $starfield.width = innerWidth * dpr;
      $starfield.height = innerHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      paint();
    };
    function paint() {
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      const count = Math.floor((innerWidth * innerHeight) / 4500);
      for (let i = 0; i < count; i++) {
        const x = Math.random() * innerWidth;
        const y = Math.random() * innerHeight;
        const r = Math.random() * 1.2 + 0.1;
        const a = Math.random() * 0.6 + 0.1;
        ctx.fillStyle = `rgba(255,255,255,${a})`;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    resize();
    window.addEventListener('resize', resize);
  }
  drawStarfield();

  // ============== Graph state ==============
  let Graph = null;
  let rawNodes = [];
  let rawLinks = [];
  let degreeById = new Map();
  let nodeById = new Map();
  let autoRotate = true;
  let hoveredNode = null;

  // ============== Fetch + init ==============
  async function init() {
    let payload;
    try {
      const r = await fetch('/api/graph');
      payload = await r.json();
    } catch (err) {
      console.error('Failed to load /api/graph', err);
      $loader.querySelector('.loader-text').textContent = 'Failed to load graph.';
      return;
    }

    const els = (payload && payload.elements) || { nodes: [], edges: [] };

    // Map Cytoscape-style elements -> 3d-force-graph nodes/links.
    rawNodes = els.nodes.map(n => ({
      id: n.data.id,
      label: n.data.label || n.data.id,
      type: n.data.type || 'seed',
      status: n.data.status,
      confidence: n.data.confidence,
    }));

    rawLinks = els.edges.map(e => ({
      source: e.data.source,
      target: e.data.target,
      type: e.data.type,
    }));

    // Degree count for sizing.
    rawNodes.forEach(n => degreeById.set(n.id, 0));
    rawLinks.forEach(l => {
      degreeById.set(l.source, (degreeById.get(l.source) || 0) + 1);
      degreeById.set(l.target, (degreeById.get(l.target) || 0) + 1);
    });
    rawNodes.forEach(n => nodeById.set(n.id, n));

    buildGraph();

    // Hide loader after first paint.
    setTimeout(() => $loader.classList.add('hidden'), 350);
  }

  function buildGraph() {
    const maxDeg = Math.max(1, ...Array.from(degreeById.values()));

    Graph = ForceGraph3D()($graph)
      .backgroundColor('rgba(0,0,0,0)')
      .showNavInfo(false)
      .graphData({ nodes: rawNodes, links: rawLinks })
      .nodeId('id')
      .nodeLabel(() => '') // we manage hover labels ourselves
      .nodeRelSize(5)
      .nodeVal(n => {
        const d = degreeById.get(n.id) || 0;
        return 2 + (d / maxDeg) * 14;
      })
      .nodeColor(n => COLORS[n.type] || DEFAULT_COLOR)
      .nodeOpacity(0.95)
      .nodeResolution(24)
      .linkColor(() => 'rgba(180, 190, 220, 0.18)')
      .linkWidth(0.4)
      .linkOpacity(0.5)
      .linkDirectionalParticles(0)
      .onNodeHover(node => {
        hoveredNode = node;
        if (node) {
          $graph.style.cursor = 'pointer';
          showHoverLabel(node);
          if (Graph._stopRotate) Graph._stopRotate(true);
        } else {
          $graph.style.cursor = 'default';
          hideHoverLabel();
          if (Graph._stopRotate) Graph._stopRotate(false);
        }
      })
      .onNodeClick(node => {
        // Pause rotation on click; center camera on node.
        setAutoRotate(false);
        focusNode(node);
        openUnit(node.id);
      })
      .onBackgroundClick(() => {
        // empty background click — close sidebar.
        closeSidebar();
      });

    // Forces tuned for a large graph (~860 nodes) — more breathing room,
    // softer radial containment that doesn't fight user drags.
    // Scale link distance with sqrt(node count) so density stays readable.
    const N = rawNodes.length;
    const linkDist = Math.max(60, 22 * Math.sqrt(N / 100));   // ~64 for 850 nodes
    const chargeStrength = -Math.max(120, 18 * Math.sqrt(N));  // ~-525 for 850
    Graph.d3Force('charge').strength(chargeStrength).distanceMax(800);
    Graph.d3Force('link').distance(linkDist).strength(0.5);
    Graph.d3Force('center').strength(0.03);

    // Gentle radial containment for orphans only. Strength is low enough
    // that user drags don't fight visibly with it.
    if (window.d3 && d3.forceRadial) {
      const maxDegLocal = Math.max(1, ...Array.from(degreeById.values()));
      Graph.d3Force('radial', d3.forceRadial(
        n => {
          const d = degreeById.get(n.id) || 0;
          // Orphans target a tight outer shell; connected nodes get a far,
          // loosely-applied target (the link/charge forces dominate them).
          return d === 0 ? 220 : 600;
        },
        0, 0
      ).strength(n => {
        // While the user is dragging a node, 3d-force-graph sets fx/fy/fz.
        // Skip radial pull on dragged nodes to eliminate shake.
        if (n.fx != null || n.fy != null || n.fz != null) return 0;
        const d = degreeById.get(n.id) || 0;
        return d === 0 ? 0.08 : 0;  // ONLY pull orphans, gently
      }));
    }

    // Bloom postprocessing for glow (uses three's UnrealBloomPass if available).
    try {
      const bloomPass = new THREE.UnrealBloomPass(
        new THREE.Vector2(window.innerWidth, window.innerHeight),
        1.1,   // strength
        0.7,   // radius
        0.05   // threshold
      );
      Graph.postProcessingComposer().addPass(bloomPass);
    } catch (err) {
      console.warn('Bloom unavailable', err);
    }

    // Auto-rotate around the scene center.
    setupAutoRotate();

    // Initial camera pull-back — scaled to fit larger graphs.
    const camZ = Math.max(420, 60 * Math.sqrt(N));  // ~1750 for 850 nodes
    setTimeout(() => Graph.cameraPosition({ z: camZ }, { x: 0, y: 0, z: 0 }, 1400), 100);

    // Resize handling.
    window.addEventListener('resize', () => {
      Graph.width(window.innerWidth).height(window.innerHeight);
    });
    Graph.width(window.innerWidth).height(window.innerHeight);
  }

  // ============== Auto-rotate ==============
  function setupAutoRotate() {
    let angle = 0;
    const radius = 360;
    let pausedByHover = false;
    let lastTs = performance.now();

    function tick(ts) {
      const dt = (ts - lastTs) / 1000;
      lastTs = ts;
      if (autoRotate && !pausedByHover) {
        angle += dt * 0.12;  // radians/sec
        const cam = Graph.cameraPosition();
        // Maintain current y, orbit around y-axis at current radius.
        const r = Math.hypot(cam.x, cam.z) || radius;
        Graph.cameraPosition({
          x: r * Math.sin(angle),
          z: r * Math.cos(angle),
          y: cam.y,
        });
      }
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);

    // Recompute angle from current camera position so we don't snap.
    const cam = Graph.cameraPosition();
    angle = Math.atan2(cam.x || 0, cam.z || 1);

    Graph._stopRotate = (pause) => { pausedByHover = !!pause; };
  }

  function setAutoRotate(on) {
    autoRotate = on;
    $btnRotate.textContent = on ? 'Pause rotation' : 'Resume rotation';
  }

  // ============== Hover label ==============
  function showHoverLabel(node) {
    if (!node) return;
    const coords = Graph.graph2ScreenCoords
      ? Graph.graph2ScreenCoords(node.x, node.y, node.z)
      : null;
    $hoverLabel.innerHTML = `<span>${escapeHtml(node.label)}</span><span class="htype">${node.type}</span>`;
    $hoverLabel.hidden = false;
    if (coords) {
      $hoverLabel.style.left = `${coords.x}px`;
      $hoverLabel.style.top = `${coords.y}px`;
    }
    // Keep label glued to node — update on each frame while hovered.
    const update = () => {
      if (hoveredNode !== node) return;
      const c = Graph.graph2ScreenCoords(node.x, node.y, node.z);
      $hoverLabel.style.left = `${c.x}px`;
      $hoverLabel.style.top = `${c.y}px`;
      requestAnimationFrame(update);
    };
    requestAnimationFrame(update);
  }

  function hideHoverLabel() {
    $hoverLabel.hidden = true;
  }

  // ============== Camera focus ==============
  function focusNode(node) {
    if (!node || node.x == null) return;
    const distance = 90;
    const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z);
    Graph.cameraPosition(
      { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
      node,
      1200
    );
  }

  // ============== Sidebar / unit detail ==============
  async function openUnit(slug) {
    $sidebar.classList.add('open');
    $sidebar.setAttribute('aria-hidden', 'false');
    $sidebarContent.innerHTML = `<div style="padding:40px 0;color:var(--ink-2);font-family:'JetBrains Mono',monospace;font-size:12px;">Loading…</div>`;

    try {
      const r = await fetch(`/api/unit/${encodeURIComponent(slug)}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      renderUnit(data);
    } catch (err) {
      $sidebarContent.innerHTML = `<p style="color:var(--ink-2)">Could not load unit: ${escapeHtml(String(err))}</p>`;
    }
  }

  function renderUnit(data) {
    const color = COLORS[data.type] || DEFAULT_COLOR;
    const bodyHtml = data.body_md
      ? marked.parse(data.body_md, { breaks: true })
      : '<p style="color:var(--ink-2)"><em>No body content.</em></p>';

    const neighborItem = (n) => `
      <div class="neighbor-item" data-slug="${escapeHtml(n.slug)}">
        <i style="background:${COLORS[n.type] || DEFAULT_COLOR}"></i>
        <span>${escapeHtml(n.title)}</span>
        <span class="neighbor-edge">${escapeHtml(n.edge_type)}</span>
      </div>`;

    const out = (data.neighbors_out || []).map(neighborItem).join('');
    const inn = (data.neighbors_in || []).map(neighborItem).join('');

    $sidebarContent.innerHTML = `
      <button id="sidebar-close-inner" class="sidebar-close" aria-label="Close">&times;</button>
      <span class="unit-type-pill"><i style="background:${color}"></i>${escapeHtml(data.type)}</span>
      <h1 class="unit-title">${escapeHtml(data.title)}</h1>
      <div class="unit-meta">
        <span>${escapeHtml(data.slug)}</span>
        ${data.status ? `<span>status: ${escapeHtml(data.status)}</span>` : ''}
        ${data.confidence ? `<span>confidence: ${escapeHtml(data.confidence)}</span>` : ''}
      </div>
      <div class="unit-body">${bodyHtml}</div>
      ${out ? `<div class="neighbors"><div class="neighbors-title">Outgoing</div><div class="neighbor-list">${out}</div></div>` : ''}
      ${inn ? `<div class="neighbors"><div class="neighbors-title">Incoming</div><div class="neighbor-list">${inn}</div></div>` : ''}
    `;

    // Wire neighbor clicks.
    $sidebarContent.querySelectorAll('.neighbor-item').forEach(el => {
      el.addEventListener('click', () => {
        const slug = el.getAttribute('data-slug');
        const node = nodeById.get(slug);
        if (node) {
          focusNode(node);
          openUnit(slug);
        } else {
          openUnit(slug);
        }
      });
    });

    const closeInner = document.getElementById('sidebar-close-inner');
    if (closeInner) closeInner.addEventListener('click', closeSidebar);
  }

  function closeSidebar() {
    $sidebar.classList.remove('open');
    $sidebar.setAttribute('aria-hidden', 'true');
  }

  $sidebarClose.addEventListener('click', closeSidebar);

  // ============== Search ==============
  let searchTimer = null;
  $searchInput.addEventListener('input', () => {
    const q = $searchInput.value.trim();
    clearTimeout(searchTimer);
    if (!q) { $searchResults.hidden = true; return; }
    searchTimer = setTimeout(() => runSearch(q), 180);
  });

  $searchInput.addEventListener('focus', () => {
    if ($searchInput.value.trim()) $searchResults.hidden = false;
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.search')) $searchResults.hidden = true;
  });

  async function runSearch(q) {
    try {
      const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=12`);
      const data = await r.json();
      const results = data.results || [];
      if (!results.length) {
        $searchResults.innerHTML = `<div class="search-empty">No matches for "${escapeHtml(q)}"</div>`;
      } else {
        $searchResults.innerHTML = results.map(r => `
          <div class="search-result" data-slug="${escapeHtml(r.slug)}">
            <span class="search-result-dot" style="background:${COLORS[r.type] || DEFAULT_COLOR}"></span>
            <span class="search-result-title">${escapeHtml(r.title)}</span>
            <span class="search-result-type">${escapeHtml(r.type)}</span>
          </div>
        `).join('');
        $searchResults.querySelectorAll('.search-result').forEach(el => {
          el.addEventListener('click', () => {
            const slug = el.getAttribute('data-slug');
            $searchResults.hidden = true;
            $searchInput.value = '';
            const node = nodeById.get(slug);
            if (node) {
              setAutoRotate(false);
              focusNode(node);
              openUnit(slug);
            } else {
              openUnit(slug);
            }
          });
        });
      }
      $searchResults.hidden = false;
    } catch (err) {
      console.error(err);
    }
  }

  // ============== Controls ==============
  $btnReset.addEventListener('click', () => {
    const N = rawNodes.length;
    const camZ = Math.max(420, 60 * Math.sqrt(N));
    Graph.cameraPosition({ x: 0, y: 0, z: camZ }, { x: 0, y: 0, z: 0 }, 1200);
    setAutoRotate(true);
  });

  $btnRotate.addEventListener('click', () => setAutoRotate(!autoRotate));

  // Escape closes sidebar.
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeSidebar();
      $searchResults.hidden = true;
    }
  });

  // ============== Utils ==============
  function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Go.
  init();
})();
