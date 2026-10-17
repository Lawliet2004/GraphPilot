import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  Code2,
  FileCode2,
  GitBranch,
  Network,
  Search,
  Waypoints,
} from "lucide-react";
import { Brand } from "../components/ui";
import { useAuth } from "../lib/auth";
export function Landing() {
  const { user } = useAuth();
  const [example, setExample] = useState("checkout");
  const examples: Record<
    string,
    { path: string; code: string; relation: string }
  > = {
    checkout: {
      path: "service.py:4–6",
      code: "def checkout(items):\n    return total(items)",
      relation: "checkout calls total",
    },
    total: {
      path: "math_ops.py:8–10",
      code: "def total(values):\n    return sum(normalize(v) for v in values)",
      relation: "total calls normalize",
    },
    normalize: {
      path: "math_ops.py:3–5",
      code: "def normalize(value):\n    return max(0, value)",
      relation: "Direct caller: total",
    },
  };
  return (
    <div className="landing">
      <header className="landing-nav">
        <Brand />
        <nav aria-label="Public navigation">
          <a href="#how-it-works">How it works</a>
          <a href="#architecture">Architecture</a>
          <a href="#get-started">Get started</a>
        </nav>
        <div>
          {user ? (
            <Link className="button primary" to="/workspace">
              Open workspace <ArrowUpRight size={15} />
            </Link>
          ) : (
            <>
              <Link className="login-link" to="/login">
                Log in
              </Link>
              <Link className="button primary" to="/signup">
                Create workspace <ArrowUpRight size={15} />
              </Link>
            </>
          )}
        </div>
      </header>
      <main>
        <section className="landing-hero">
          <div className="hero-copy">
            <h1>
              Code makes
              <br />
              more sense.
              <br />
              <span>Connected.</span>
            </h1>
            <p>
              See how your code fits together. Trace dependencies, investigate
              changes and ask questions with the source in reach.
            </p>
            <div className="hero-actions">
              <Link
                className="button primary"
                to={user ? "/workspace" : "/signup"}
              >
                Explore your code <ArrowRight size={18} />
              </Link>
              <a className="button text-button" href="#graph-preview">
                See the connections <ArrowDown size={16} />
              </a>
            </div>
            <div className="hero-assurances">
              <span>
                <Check size={14} />
                Powered by FalkorDB
              </span>
              <span>
                <Check size={14} />
                No AI key required
              </span>
            </div>
          </div>
          <div className="hero-visual" id="graph-preview">
            <div className="preview-top">
              <span>
                <GitBranch size={14} />
                reference / main
              </span>
              <span className="illustrative">Illustrative fixture</span>
            </div>
            <div className="preview-graph">
              <svg
                viewBox="0 0 600 340"
                role="img"
                aria-label="Illustrative static call chain: test_checkout calls checkout, which calls total, which calls normalize."
              >
                <defs>
                  <marker
                    id="arrow"
                    markerWidth="7"
                    markerHeight="7"
                    refX="6"
                    refY="3.5"
                    orient="auto"
                  >
                    <path d="M0 0L7 3.5L0 7" fill="none" stroke="#a0a8bc" />
                  </marker>
                </defs>
                <g className="preview-edges" markerEnd="url(#arrow)">
                  <path d="M104 75C150 75 150 178 212 178" />
                  <path d="M315 177C380 177 350 75 410 75" />
                  <path d="M462 101C462 155 494 215 457 246" />
                  <path d="M105 280C166 280 175 198 220 190" />
                </g>
                <g className="diagram-labels">
                  <text x="143" y="107">
                    CALLS
                  </text>
                  <text x="339" y="110">
                    CALLS
                  </text>
                  <text x="474" y="180">
                    CALLS
                  </text>
                  <text x="152" y="264">
                    DEFINES
                  </text>
                </g>
                <g className="diagram-nodes">
                  <rect x="20" y="47" width="137" height="52" rx="9" />
                  <text x="88" y="78">
                    test_checkout
                  </text>
                  <rect
                    className="active"
                    x="209"
                    y="149"
                    width="130"
                    height="56"
                    rx="9"
                  />
                  <text x="274" y="182">
                    checkout
                  </text>
                  <rect x="401" y="47" width="114" height="52" rx="9" />
                  <text x="458" y="78">
                    total
                  </text>
                  <rect x="380" y="245" width="140" height="52" rx="9" />
                  <text x="450" y="277">
                    normalize
                  </text>
                  <rect
                    className="file-node"
                    x="27"
                    y="253"
                    width="116"
                    height="49"
                    rx="9"
                  />
                  <text x="85" y="283">
                    service.py
                  </text>
                </g>
              </svg>
              <div className="preview-legend">
                <span>
                  <i />
                  Function
                </span>
                <span>
                  <i />
                  File
                </span>
                <span>Static call relationships</span>
              </div>
            </div>
            <div className="preview-evidence">
              <div>
                <FileCode2 size={15} />
                <span>{examples[example].path}</span>
                <span>Source evidence</span>
              </div>
              <pre>{examples[example].code}</pre>
              <p>
                <Waypoints size={14} />
                {examples[example].relation}
              </p>
            </div>
            <div className="example-switcher">
              <span>Inspect a symbol</span>
              {Object.keys(examples).map((key) => (
                <button
                  key={key}
                  className={key === example ? "active" : ""}
                  onClick={() => setExample(key)}
                >
                  {key}
                  <ChevronRight size={12} />
                </button>
              ))}
            </div>
          </div>
        </section>
        <section className="landing-principle" id="how-it-works">
          <div>
            <h2>
              Less searching in circles.
              <br />
              More following the thread.
            </h2>
            <p>
              A repository is more than a collection of files. GraphPilot gives
              its connections a place to live, and gives you a path back to the
              evidence.
            </p>
          </div>
          <div className="capability-rows">
            <article>
              <Network size={25} />
              <div>
                <h3>See the structure</h3>
                <p>
                  Explore files, Python functions, classes and static
                  dependencies in an interactive, bounded graph.
                </p>
              </div>
              <span>Graph explorer</span>
            </article>
            <article>
              <GitBranch size={25} />
              <div>
                <h3>Connect the history</h3>
                <p>
                  Bring available GitHub commits, issues, pull requests and
                  workflow metadata into the investigation.
                </p>
              </div>
              <span>History & context</span>
            </article>
            <article>
              <Search size={25} />
              <div>
                <h3>Ask with evidence</h3>
                <p>
                  Retrieve graph context without a model. Add a local or hosted
                  model for cited synthesis when you want it.
                </p>
              </div>
              <span>Context explorer</span>
            </article>
          </div>
        </section>
        <section className="architecture-section" id="architecture">
          <div>
            <h2>
              A clear path.
              <br />
              From source to understanding.
            </h2>
            <p>
              Your repositories are authoritative. PostgreSQL tracks access and
              durable jobs. FalkorDB connects the evidence. One backend keeps
              permissions in scope.
            </p>
            <Link className="text-link" to="/signup">
              Build your workspace <ArrowRight size={16} />
            </Link>
          </div>
          <div
            className="architecture-diagram"
            aria-label="Architecture: repository sources flow through safe ingestion into FalkorDB and the GraphPilot application."
          >
            <div>
              <Code2 size={21} />
              <strong>Repository sources</strong>
              <span>Public GitHub · ZIP · Allowed local Git</span>
            </div>
            <ArrowDown size={19} />
            <div>
              <Waypoints size={21} />
              <strong>Ingest & resolve</strong>
              <span>Read source · Parse Python · Record provenance</span>
            </div>
            <ArrowDown size={19} />
            <div className="architecture-db">
              <Network size={22} />
              <strong>FalkorDB</strong>
              <span>Typed, scoped relationships</span>
            </div>
            <ArrowDown size={19} />
            <div>
              <Search size={21} />
              <strong>Explore with context</strong>
              <span>Graph search · Source evidence · Optional AI</span>
            </div>
          </div>
        </section>
        <section className="getting-started" id="get-started">
          <div>
            <h2>
              Your next investigation
              <br />
              starts here.
            </h2>
            <p>
              Run GraphPilot locally, create an account and connect your first
              repository. Basic indexing and search need no paid services.
            </p>
            <Link
              className="button primary"
              to={user ? "/workspace" : "/signup"}
            >
              Create your workspace <ArrowUpRight size={16} />
            </Link>
          </div>
          <ol>
            <li>
              <span>Install & configure</span>
              <p>
                Copy <code>.env.example</code>, set your database password and
                permitted origins, then start the services.
              </p>
              <code>docker compose up --build -d</code>
            </li>
            <li>
              <span>Connect your source</span>
              <p>
                Use a public GitHub URL, a source ZIP or a permitted
                server-local Git path.
              </p>
            </li>
            <li>
              <span>Follow a connection</span>
              <p>
                Find a known function, expand its neighbors and open the exact
                source evidence.
              </p>
            </li>
          </ol>
        </section>
      </main>
      <footer className="landing-footer">
        <Brand />
        <span>Code intelligence. Grounded in evidence.</span>
        <a
          href="https://github.com/FalkorDB/FalkorDB"
          target="_blank"
          rel="noreferrer"
        >
          Built with FalkorDB <ArrowUpRight size={14} />
        </a>
      </footer>
    </div>
  );
}
