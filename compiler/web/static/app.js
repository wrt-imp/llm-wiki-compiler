// Graph browser: fetch /api/graph and render it with cytoscape.js.
// If the CDN import failed (offline), fall back to a plain text listing.
//
// What the user arranges (node positions, zoom/pan, the search box) is saved
// through /api/layout, so closing the page and coming back restores it.

const RANK_DIRECTION = { TD: "TB", TB: "TB", BT: "BT", LR: "LR", RL: "RL" };

function edgeId(edge) {
  return edge.source + "|" + edge.type + "|" + edge.target;
}

function elementsFrom(data) {
  const nodes = data.nodes.map((node) => ({
    data: {
      id: node.id,
      label: node.title || node.id,
      kind: node.kind || "",
      line: node.metadata && node.metadata.line ? node.metadata.line : "",
    },
  }));
  const edges = data.edges.map((edge) => ({
    data: {
      id: edgeId(edge),
      source: edge.source,
      target: edge.target,
      label: edge.type || "",
    },
  }));
  return nodes.concat(edges);
}

function stylesheet() {
  return [
    {
      selector: "node",
      style: {
        "background-color": "#4c6ef5",
        "border-color": "#8ea9ff",
        "border-width": 1,
        label: "data(label)",
        color: "#e8ecf3",
        "font-size": 12,
        "text-valign": "center",
        "text-halign": "center",
        width: "label",
        height: "label",
        padding: "10px",
        shape: "round-rectangle",
      },
    },
    { selector: "node.dim", style: { opacity: 0.2 } },
    {
      selector: "node.match",
      style: { "background-color": "#f7b32b", "border-color": "#ffe08a" },
    },
    {
      selector: "edge",
      style: {
        width: 1.6,
        "line-color": "#6b7688",
        "target-arrow-color": "#6b7688",
        "target-arrow-shape": "triangle",
        "curve-style": "bezier",
        label: "data(label)",
        color: "#b9c4d6",
        "font-size": 11,
        "text-background-color": "#12151c",
        "text-background-opacity": 0.85,
        "text-background-padding": "2px",
      },
    },
    { selector: "edge.dim", style: { opacity: 0.15 } },
  ];
}

function layoutOptions(direction) {
  const rankDir = RANK_DIRECTION[direction] || "TB";
  if (typeof window.cytoscapeDagre !== "undefined") {
    return {
      name: "dagre",
      rankDir: rankDir,
      nodeSep: 40,
      rankSep: 70,
      fit: true,
      padding: 40,
    };
  }
  return { name: "breadthfirst", directed: true, spacingFactor: 1.2, padding: 40 };
}

function renderFallback(data, banner) {
  banner.hidden = false;
  banner.textContent = "cytoscape.js 未加载（离线？），已降级为文本视图。";
  const container = document.getElementById("cy");
  const nodes = data.nodes
    .map((node) => "<li><code>" + node.id + "</code> — " + (node.title || "") + "</li>")
    .join("");
  const edges = data.edges
    .map(
      (edge) =>
        "<li><code>" +
        edge.source +
        "</code> —" +
        (edge.type || "→") +
        "→ <code>" +
        edge.target +
        "</code></li>"
    )
    .join("");
  container.innerHTML =
    '<div class="fallback"><h3>Nodes (' +
    data.nodes.length +
    ")</h3><ul>" +
    (nodes || "<li>(none)</li>") +
    "</ul><h3>Edges (" +
    data.edges.length +
    ")</h3><ul>" +
    (edges || "<li>(none)</li>") +
    "</ul></div>";
}

function describeSelection(node) {
  const data = node.data();
  const list = (collection, direction) => {
    const items = collection.map((edge) => {
      const edgeData = edge.data();
      const other = direction === "in" ? edgeData.source : edgeData.target;
      const label = edgeData.label ? " <code>" + edgeData.label + "</code>" : "";
      return (
        "<li>" + (direction === "in" ? "←" : "→") + " <code>" + other + "</code>" + label + "</li>"
      );
    });
    return items.length ? items.join("") : "<li>(none)</li>";
  };
  return (
    "<h3>" +
    data.label +
    "</h3><dl><dt>id</dt><dd><code>" +
    data.id +
    "</code></dd><dt>kind</dt><dd>" +
    (data.kind || "—") +
    "</dd>" +
    (data.line ? "<dt>line</dt><dd>" + data.line + "</dd>" : "") +
    "</dl><h2>Outgoing</h2><ul>" +
    list(node.outgoers("edge"), "out") +
    "</ul><h2>Incoming</h2><ul>" +
    list(node.incomers("edge"), "in") +
    "</ul>"
  );
}

const LAYOUT_URL = "/api/layout";
const SAVE_DELAY_MS = 350;

function round(value, digits) {
  const factor = Math.pow(10, digits);
  return Math.round(value * factor) / factor;
}

async function fetchLayout() {
  try {
    const response = await fetch(LAYOUT_URL);
    if (!response.ok) throw new Error("HTTP " + response.status);
    return await response.json();
  } catch (error) {
    return null;
  }
}

function currentState(cy, search) {
  const positions = {};
  cy.nodes().forEach((node) => {
    const point = node.position();
    positions[node.id()] = { x: round(point.x, 2), y: round(point.y, 2) };
  });
  return {
    positions: positions,
    view: {
      zoom: round(cy.zoom(), 4),
      pan: { x: round(cy.pan().x, 2), y: round(cy.pan().y, 2) },
    },
    search: search.value,
  };
}

function postState(payload, options) {
  const request = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
  if (options && options.keepalive) request.keepalive = true;
  return fetch(LAYOUT_URL, request);
}

function savedText(state) {
  if (!state) return "布局未能持久化";
  if (state.persisted === false) return "布局持久化已关闭（--no-layout）";
  if (!state.saved_at) return "尚未保存布局";
  return "布局已保存 " + String(state.saved_at).replace("T", " ");
}

async function main() {
  const banner = document.getElementById("banner");
  let data;
  let layoutState = null;
  try {
    const [graphResponse, saved] = await Promise.all([fetch("/api/graph"), fetchLayout()]);
    if (!graphResponse.ok) throw new Error("HTTP " + graphResponse.status);
    data = await graphResponse.json();
    layoutState = saved;
  } catch (error) {
    banner.hidden = false;
    banner.textContent = "无法加载图数据：" + error;
    return;
  }

  const metadata = data.metadata || {};
  document.getElementById("source").textContent =
    (metadata.source || "") + (metadata.direction ? "  (" + metadata.direction + ")" : "");
  document.getElementById("stats").textContent =
    "Nodes: " + data.nodes.length + "    Edges: " + data.edges.length;

  if (typeof cytoscape === "undefined") {
    renderFallback(data, banner);
    return;
  }
  if (typeof window.cytoscapeDagre !== "undefined") {
    cytoscape.use(window.cytoscapeDagre);
  }

  const cy = cytoscape({
    container: document.getElementById("cy"),
    elements: elementsFrom(data),
    style: stylesheet(),
    layout: { name: "preset" },
    wheelSensitivity: 0.2,
    minZoom: 0.2,
    maxZoom: 4,
  });

  const infoBody = document.getElementById("info-body");
  const savedLabel = document.getElementById("saved");
  const search = document.getElementById("search");
  let restoring = true;
  let pending = null;

  cy.on("tap", "node", (event) => {
    infoBody.innerHTML = describeSelection(event.target);
  });
  cy.on("tap", (event) => {
    if (event.target === cy) infoBody.textContent = "Click a node to see its details.";
  });

  const applySearch = ({ fit = true } = {}) => {
    const query = search.value.trim().toLowerCase();
    cy.batch(() => {
      cy.elements().removeClass("match dim");
      if (!query) return;
      const matches = cy.nodes().filter((node) => {
        const nodeData = node.data();
        return (
          String(nodeData.id).toLowerCase().indexOf(query) >= 0 ||
          String(nodeData.label).toLowerCase().indexOf(query) >= 0
        );
      });
      cy.nodes().difference(matches).addClass("dim");
      cy.edges().addClass("dim");
      matches.addClass("match").removeClass("dim");
      matches.connectedEdges().removeClass("dim");
      if (fit && matches.length > 0) cy.fit(matches, 60);
    });
  };

  const runDefaultLayout = (done) => {
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      done();
    };
    const layout = cy.layout(layoutOptions(metadata.direction));
    layout.one("layoutstop", finish);
    layout.run();
    // A layout engine that never reports back would leave the canvas empty, so
    // fall back to fitting whatever positions we have.
    setTimeout(() => {
      if (finished) return;
      try {
        cy.fit(cy.elements(), 40);
      } catch (error) {
        // fitting is best effort; showing the nodes matters more
      }
      finish();
    }, 3000);
  };

  const save = async () => {
    try {
      const response = await postState(currentState(cy, search));
      if (!response.ok) throw new Error("HTTP " + response.status);
      savedLabel.textContent = savedText(await response.json());
      savedLabel.classList.remove("error");
    } catch (error) {
      savedLabel.textContent = "布局保存失败：" + error;
      savedLabel.classList.add("error");
    }
  };

  const scheduleSave = () => {
    if (restoring) return;
    if (pending !== null) clearTimeout(pending);
    pending = setTimeout(() => {
      pending = null;
      save();
    }, SAVE_DELAY_MS);
  };

  const flushSave = () => {
    if (restoring || pending === null) return;
    clearTimeout(pending);
    pending = null;
    postState(currentState(cy, search), { keepalive: true }).catch(() => {});
  };

  const applySaved = (state) => {
    if (!state) return;
    const positions = state.positions || {};
    cy.batch(() => {
      Object.keys(positions).forEach((id) => {
        const node = cy.getElementById(id);
        if (node.nonempty()) node.position(positions[id]);
      });
    });
    if (typeof state.search === "string" && state.search) {
      search.value = state.search;
      applySearch({ fit: false });
    }
    const view = state.view;
    if (view && typeof view.zoom === "number") {
      cy.viewport({ zoom: view.zoom, pan: view.pan || cy.pan() });
    }
  };

  runDefaultLayout(() => {
    applySaved(layoutState);
    restoring = false;
    savedLabel.textContent = savedText(layoutState);
  });

  cy.on("dragfree", "node", scheduleSave);
  cy.on("zoom", scheduleSave);
  cy.on("pan", scheduleSave);
  search.addEventListener("input", () => {
    applySearch();
    scheduleSave();
  });
  window.addEventListener("pagehide", flushSave);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) flushSave();
  });

  const reset = document.getElementById("reset");
  if (reset) {
    reset.addEventListener("click", async () => {
      restoring = true;
      if (pending !== null) {
        clearTimeout(pending);
        pending = null;
      }
      search.value = "";
      cy.elements().removeClass("match dim");
      infoBody.textContent = "Click a node to see its details.";
      try {
        const response = await postState({ reset: true });
        if (!response.ok) throw new Error("HTTP " + response.status);
        savedLabel.textContent = "布局已重置";
        savedLabel.classList.remove("error");
      } catch (error) {
        savedLabel.textContent = "重置失败：" + error;
        savedLabel.classList.add("error");
      }
      runDefaultLayout(() => {
        restoring = false;
      });
    });
  }
}

main();
