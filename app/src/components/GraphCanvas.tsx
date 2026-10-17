import { useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { Maximize, Minus, Plus } from "lucide-react";
import type { Graph, Node } from "../lib/api";
const colors: Record<string, string> = {
  Repository: "#525d89",
  Branch: "#8390b4",
  File: "#b0b7cc",
  Function: "#c48569",
  Class: "#7a9f8d",
  TestCase: "#a28baa",
  Commit: "#ad9867",
  Issue: "#be7373",
  PullRequest: "#7298ab",
  WorkflowRun: "#ab9c65",
};
export function GraphCanvas({
  graph,
  onSelect,
  selected,
}: {
  graph: Graph;
  onSelect: (node: Node) => void;
  selected?: string;
}) {
  const container = useRef<HTMLDivElement>(null),
    cy = useRef<cytoscape.Core | null>(null);
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  const draw = useRef<() => void>(() => {});
  const [rendered, setRendered] = useState(0);
  draw.current = () => {
    const instance = cy.current,
      box = container.current;
    if (!instance || !box) return;
    const width = box.clientWidth,
      height = box.clientHeight;
    const center = graph.nodes.find((n) => n.id === selected);
    // A legible plot is smaller than the loaded neighborhood. All loaded nodes
    // remain available in the adjacent keyboard list and relationship entries.
    const cap = width < 500 ? 8 : 14;
    const nodes = [
      ...(center ? [center] : []),
      ...graph.nodes.filter((n) => n.id !== selected),
    ].slice(0, cap);
    const ids = new Set(nodes.map((n) => n.id));
    const outer = nodes.filter((n) => n.id !== center?.id);
    const elements: cytoscape.ElementDefinition[] = nodes.map((n) => {
      const index = outer.findIndex((o) => o.id === n.id),
        angle = (2 * Math.PI * index) / Math.max(outer.length, 1) - Math.PI / 2;
      return {
        data: n,
        position:
          n.id === center?.id
            ? { x: width / 2, y: height / 2 - 12 }
            : {
                x: width / 2 + Math.cos(angle) * Math.max(65, width / 2 - 80),
                y: height / 2 - 12 + Math.sin(angle) * (height / 2 - 85),
              },
      };
    });
    elements.push(
      ...graph.edges
        .filter((e) => ids.has(e.source) && ids.has(e.target))
        .map((e) => ({ data: e })),
    );
    instance.elements().remove();
    instance.add(elements);
    instance.layout({ name: "preset", fit: false }).run();
    instance.zoom(1);
    instance.pan({ x: 0, y: 0 });
    if (center) {
      instance.getElementById(center.id).addClass("picked");
      instance.getElementById(center.id).connectedEdges().addClass("related");
    }
    setRendered(nodes.length);
  };
  useEffect(() => {
    if (!container.current) return;
    const instance = cytoscape({
      container: container.current,
      elements: [],
      minZoom: 0.25,
      maxZoom: 3,
      wheelSensitivity: 0.15,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (ele) =>
              colors[String(ele.data("type"))] || "#8692a0",
            label: "data(name)",
            "font-size": 12,
            "font-family": "Manrope Variable, sans-serif",
            color: "#34394a",
            "text-valign": "bottom",
            "text-margin-y": 8,
            "text-max-width": "100px",
            "text-wrap": "ellipsis",
            width: 22,
            height: 22,
            "border-width": 3,
            "border-color": "#fff",
            "text-background-color": "#f1f2f4",
            "text-background-opacity": 0.95,
            "text-background-padding": "2px",
            "overlay-opacity": 0,
          },
        },
        {
          selector: 'node[type="File"]',
          style: { shape: "round-rectangle", width: 24, height: 20 },
        },
        {
          selector: "edge",
          style: {
            width: 1.3,
            "line-color": "#abb3c4",
            "target-arrow-color": "#798399",
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.9,
            "curve-style": "bezier",
            opacity: 0.8,
          },
        },
        {
          selector: ".picked",
          style: {
            "border-width": 4,
            "border-color": "#915842",
            width: 32,
            height: 32,
            "font-weight": "bold",
            "font-size": 14,
          },
        },
        {
          selector: ".related",
          style: {
            "line-color": "#a96850",
            "target-arrow-color": "#a96850",
            width: 2,
            opacity: 1,
          },
        },
        {
          selector: ".hovered",
          style: { label: "data(name)", "font-weight": "bold" },
        },
      ],
    });
    cy.current = instance;
    instance.on("tap", "node", (e) =>
      selectRef.current(e.target.data() as Node),
    );
    instance.on("mouseover", "node", (e) => e.target.addClass("hovered"));
    instance.on("mouseout", "node", (e) => e.target.removeClass("hovered"));
    const resize = new ResizeObserver(() => {
      instance.resize();
      draw.current();
    });
    resize.observe(container.current);
    draw.current();
    return () => {
      resize.disconnect();
      instance.destroy();
      cy.current = null;
    };
  }, []);
  useEffect(() => {
    draw.current();
  }, [graph, selected]);
  return (
    <div className="graph-canvas-wrap">
      <div
        ref={container}
        className="graph-canvas"
        role="img"
        aria-label={`Interactive repository graph. ${rendered} of ${graph.nodes.length} loaded nodes plotted. The node list and connections provide all names and relationship directions.`}
      />
      <span className="plot-coverage">
        {rendered} of {graph.nodes.length} nodes plotted · all available below
      </span>
      <div className="graph-controls">
        <button
          className="icon-button"
          aria-label="Zoom in"
          onClick={() => cy.current?.zoom((cy.current?.zoom() || 1) * 1.2)}
        >
          <Plus size={17} />
        </button>
        <button
          className="icon-button"
          aria-label="Zoom out"
          onClick={() => cy.current?.zoom((cy.current?.zoom() || 1) / 1.2)}
        >
          <Minus size={17} />
        </button>
        <button
          className="icon-button"
          aria-label="Fit graph"
          onClick={() => cy.current?.fit(undefined, 45)}
        >
          <Maximize size={16} />
        </button>
      </div>
      <div className="graph-legend">
        {["File", "Function", "Class", "TestCase"].map((type) => (
          <span key={type}>
            <i style={{ background: colors[type] }} />
            {type === "TestCase" ? "Test case" : type}
          </span>
        ))}
      </div>
    </div>
  );
}
