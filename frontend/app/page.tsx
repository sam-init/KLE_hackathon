import Link from "next/link";

const FEATURES = [
  {
    icon: "🔍",
    title: "Multi-Agent Code Review",
    desc: "Six specialized AI agents inspect PRs for bugs, security, performance, readability, architecture, and accessibility issues — in parallel.",
    color: "#e4b5ff",
  },
  {
    icon: "📚",
    title: "Documentation Generator",
    desc: "Generate README files, docstrings, modular docs, onboarding guides, and interactive dependency graphs from your repository source code.",
    color: "#dcbaf0",
  },
  {
    icon: "🧩",
    title: "Persona-Aware Output",
    desc: "Adapt review tone and explanation depth for Interns, Students, Frontend Engineers, and Backend Engineers automatically.",
    color: "#ab00ff",
  },
];

const STATS = [
  { dot: "#e4b5ff", label: "Code Review" },
  { dot: "#56d364", label: "Docs Generator" },
  { dot: "#dcbaf0", label: "Graph Visuals" },
  { dot: "#ab00ff", label: "Persona-Aware" },
];

export default function HomePage() {
  return (
    <>
      {/* ── Nav ── */}
      <nav className="nav">
        <span className="nav-brand">⚡ Voxr AI</span>
        <span className="nav-sep" />
        <Link href="/dashboard" className="btn btn-primary btn-sm">
          Open Dashboard →
        </Link>
      </nav>

      <main className="container hero">
        <div style={{ maxWidth: 760 }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              padding: "4px 14px",
              background: "rgba(88,166,255,0.1)",
              border: "1px solid rgba(88,166,255,0.25)",
              borderRadius: 999,
              fontSize: 12,
              fontWeight: 700,
              color: "var(--accent)",
              marginBottom: 20,
              letterSpacing: "0.05em",
              textTransform: "uppercase",
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "var(--success)",
                display: "inline-block",
              }}
            />
            Multi-Agent AI Platform
          </div>

          <h1>Ship Better Pull Requests With Multi-Agent AI Reviews</h1>
          <p>
            DevPilot AI combines six specialized review agents with automated documentation
            generation — giving teams instant README files, docstrings, dependency graphs, and
            actionable inline findings.
          </p>

          <div style={{ display: "flex", gap: 12, marginTop: 28, flexWrap: "wrap" }}>
            <Link href="/dashboard" className="btn btn-primary btn-demo">
              🚀 Open Dashboard
            </Link>
            <a href="#features" className="btn btn-secondary">
              Explore Features
            </a>
          </div>

          <div className="stat-row" style={{ marginTop: 32 }}>
            {[
              { dot: "#58a6ff", label: "Code Review" },
              { dot: "#3fb950", label: "Docs Generator" },
              { dot: "#d29922", label: "Graph Visuals" },
              { dot: "#bc8cff", label: "Persona-Aware" },
            ].map(({ dot, label }) => (
              <span key={label} className="stat-pill">
                <span className="dot" style={{ background: dot }} />
                {label}
              </span>
            ))}
          </div>
        </div>

        <section
          id="features"
          className="grid"
          style={{
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            marginTop: 60,
          }}
        >
          {[
            {
              icon: "🔍",
              title: "Code Reviewer",
              desc: "Six specialized agents inspect PR-ready code for bugs, security, performance, readability, architecture, and accessibility issues.",
              color: "#58a6ff",
            },
            {
              icon: "📚",
              title: "Documentation Generator",
              desc: "Generate README files, docstrings, modular docs, onboarding guides, and interactive graph visuals from repository source code.",
              color: "#3fb950",
            },
            {
              icon: "🧩",
              title: "Persona-Aware Output",
              desc: "Adapt review tone and explanation depth for interns, students, frontend engineers, and backend engineers automatically.",
              color: "#d29922",
            },
          ].map(({ icon, title, desc, color }) => (
            <article key={title} className="card" style={{ borderTop: `2px solid ${color}` }}>
              <div style={{ fontSize: 28, marginBottom: 10 }}>{icon}</div>
              <h3 style={{ margin: "0 0 8px", color: "var(--ink)" }}>{title}</h3>
              <p style={{ margin: 0, color: "var(--ink-2)", fontSize: 14 }}>{desc}</p>
            </article>
          ))}
        </section>
      </main>
    </>
  );
}
