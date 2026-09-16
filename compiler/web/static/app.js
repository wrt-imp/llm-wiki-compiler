// Graph browser: fetch /api/graph and render it with cytoscape.js.
// If the CDN import failed (offline), fall back to a plain text listing.

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

async function main() {
  const banner = document.getElementById("banner");
  let data;
  try {
    const response = await fetch("/api/graph");
    if (!response.ok) throw new Error("HTTP " + response.status);
    data = await response.json();
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
    layout: layoutOptions(metadata.direction),
    wheelSensitivity: 0.2,
    minZoom: 0.2,
    maxZoom: 4,
  });

  const infoBody = document.getElementById("info-body");
  cy.on("tap", "node", (event) => {
    infoBody.innerHTML = describeSelection(event.target);
  });
  cy.on("tap", (event) => {
    if (event.target === cy) infoBody.textContent = "Click a node to see its details.";
  });

  const search = document.getElementById("search");
  search.addEventListener("input", () => {
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
      if (matches.length > 0) cy.fit(matches, 60);
    });
  });
}

main();
