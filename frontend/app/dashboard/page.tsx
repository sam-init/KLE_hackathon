"use client";

import { useState } from "react";
import Link from "next/link";

import FaultyTerminal from "@/app/components/FaultyTerminal";
import { DocsResults } from "@/components/DocsResults";
import { ReviewResults } from "@/components/ReviewResults";
import { GraphPanel } from "@/components/GraphPanel";
import { docsFromRepo, docsFromZip, reviewFromRepo, reviewFromZip } from "@/lib/api";
import { DocsResponse, Persona, ReviewResponse } from "@/lib/types";

const PERSONAS: Persona[] = ["Intern", "Student", "Frontend Developer", "Backend Developer"];
const DEMO_REPO = "https://github.com/tiangolo/fastapi";

type ResultTab = "review" | "docs" | "graphs";
type InputMode = "repo" | "zip";

function LoadingSkeleton() {
  return (
    <div className="card result-shell" style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4, fontFamily: "var(--font-mono)" }}>
        <div className="spinner" />
        <span style={{ color: "var(--ink-2)", fontSize: 14, fontWeight: 600 }}>
          AI agents are processing your repository...
        </span>
      </div>
      {[140, 90, 200, 110, 80].map((h, i) => (
        <div key={i} className="skeleton" style={{ height: h, borderRadius: 8 }} />
      ))}
    </div>
  );
}

function EmptyState({ tab }: { tab: ResultTab }) {
  const map = {
    review: {
      icon: "R",
      title: "Code Reviewer Ready",
      desc: "Enter a repository URL or upload a ZIP and click Run to start the multi-agent code review.",
    },
    docs: {
      icon: "D",
      title: "Docs Generator Ready",
      desc: "Generate README, docstrings, modular docs, onboarding guide, and dependency graphs.",
    },
    graphs: {
      icon: "G",
      title: "Graphs Ready",
      desc: "Run the Documentation Generator to see dependency, execution, and knowledge graphs.",
    },
  };
  const { icon, title, desc } = map[tab];
  return (
    <div className="card empty-state result-shell">
      <div className="icon">{icon}</div>
      <h3>{title}</h3>
      <p>{desc}</p>
    </div>
  );
}

export default function DashboardPage() {
  const [persona, setPersona] = useState<Persona>("Student");
  const [repoUrl, setRepoUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [inputMode, setInputMode] = useState<InputMode>("repo");

  const [reviewData, setReviewData] = useState<ReviewResponse | null>(null);
  const [docsData, setDocsData] = useState<DocsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [resultTab, setResultTab] = useState<ResultTab>("review");

  async function run(mode: "repo" | "zip") {
    if (mode === "repo" && !repoUrl) {
      setError("Please enter a repository URL.");
      return;
    }
    if (mode === "zip" && !file) {
      setError("Please select a ZIP file.");
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      if (resultTab === "review" || resultTab === "graphs") {
        const doRev = resultTab === "review";
        if (doRev) {
          const data = mode === "repo"
            ? await reviewFromRepo(repoUrl, persona)
            : await reviewFromZip(file!, persona);
          setReviewData(data);
          setSuccess(`Review complete - ${data.findings.length} finding(s) across ${data.reviewed_files.length} file(s).`);
        } else {
          const data = mode === "repo"
            ? await docsFromRepo(repoUrl, persona)
            : await docsFromZip(file!, persona);
          setDocsData(data);
          setSuccess("Graphs generated successfully.");
        }
      } else {
        const data = mode === "repo"
          ? await docsFromRepo(repoUrl, persona)
          : await docsFromZip(file!, persona);
        setDocsData(data);
        setSuccess("Documentation generated successfully.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed. Check the console for details.");
    } finally {
      setLoading(false);
    }
  }

  const hasResults = reviewData !== null || docsData !== null;

  return (
    <div className="dashboard-shell">
      <div className="dashboard-terminal-bg" aria-hidden>
        <FaultyTerminal
          scale={1.45}
          gridMul={[2, 1]}
          digitSize={1.2}
          timeScale={0.45}
          scanlineIntensity={0.45}
          glitchAmount={1}
          flickerAmount={1}
          noiseAmp={1}
          chromaticAberration={0}
          dither={0}
          curvature={0.08}
          tint="#A7EF9E"
          mouseReact
          mouseStrength={0.35}
          pageLoadAnimation
          brightness={0.5}
          style={{ opacity: 0.22 }}
        />
      </div>
      <div className="dashboard-scanlines" aria-hidden />
      <div className="dashboard-scanbeam" aria-hidden />

      <nav className="nav">
        <Link href="/" className="nav-brand">
          {" >_ Cypher"}<span className="nav-brand-dim">AI</span>
        </Link>
        <span className="nav-slash">/</span>
        <span className="nav-label">Dashboard</span>
        <span className="nav-sep" />
        {hasResults && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setReviewData(null);
              setDocsData(null);
              setSuccess(null);
              setError(null);
            }}
          >
            x Clear Results
          </button>
        )}
      </nav>

      <main className="container dashboard-main">
        <header className="dashboard-hero card">
          <div className="dashboard-eyebrow">$ cypher --dashboard --agents 6</div>
          <h1 className="dashboard-title">Multi-Agent Workspace</h1>
          <p className="dashboard-subtitle">
            Run code review, docs generation, and graph synthesis from one terminal-style control plane.
          </p>
          <div className="stat-row">
            <span className="stat-pill">
              <span className="dot" style={{ background: "var(--danger)" }} />
              Review
            </span>
            <span className="stat-pill">
              <span className="dot" style={{ background: "var(--accent)" }} />
              Docs
            </span>
            <span className="stat-pill">
              <span className="dot" style={{ background: "var(--success)" }} />
              Graphs
            </span>
            <span className="stat-pill">
              <span className="dot" style={{ background: "var(--warning)" }} />
              Persona-Aware
            </span>
          </div>
        </header>

        <div className="dashboard-grid">
          <aside className="dashboard-sidebar">
            <div className="card control-card" style={{ display: "grid", gap: 20 }}>
              <div className="sidebar-section">
                <div className="label">Action</div>
                <div style={{ display: "flex", gap: 8 }}>
                  {(["review", "docs", "graphs"] as ResultTab[]).map((t) => (
                    <button
                      key={t}
                      className={`btn btn-sm ${resultTab === t ? "btn-primary" : "btn-secondary"}`}
                      style={{ flex: 1, textTransform: "capitalize" }}
                      onClick={() => setResultTab(t)}
                      disabled={loading}
                    >
                      {t === "review" ? "Review" : t === "docs" ? "Docs" : "Graphs"}
                    </button>
                  ))}
                </div>
              </div>

              <div className="sidebar-section">
                <div className="label">Persona</div>
                <div className="persona-grid">
                  {PERSONAS.map((p) => (
                    <button
                      key={p}
                      className={`persona-chip ${persona === p ? "active" : ""}`}
                      onClick={() => setPersona(p)}
                      disabled={loading}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </div>

              <div className="sidebar-section">
                <div className="label">Input Source</div>
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    className={`btn btn-sm ${inputMode === "repo" ? "btn-primary" : "btn-secondary"}`}
                    style={{ flex: 1 }}
                    onClick={() => setInputMode("repo")}
                    disabled={loading}
                  >
                    GitHub URL
                  </button>
                  <button
                    className={`btn btn-sm ${inputMode === "zip" ? "btn-primary" : "btn-secondary"}`}
                    style={{ flex: 1 }}
                    onClick={() => setInputMode("zip")}
                    disabled={loading}
                  >
                    ZIP Upload
                  </button>
                </div>
              </div>

              {inputMode === "repo" ? (
                <div className="sidebar-section">
                  <label htmlFor="repo-url" className="label">Repository URL</label>
                  <input
                    id="repo-url"
                    className="input"
                    placeholder="https://github.com/owner/repo"
                    value={repoUrl}
                    onChange={(e) => setRepoUrl(e.target.value)}
                    disabled={loading}
                    onKeyDown={(e) => e.key === "Enter" && run("repo")}
                  />
                  <button
                    className="btn btn-secondary btn-sm"
                    style={{ marginTop: 6, width: "100%", justifyContent: "flex-start" }}
                    onClick={() => setRepoUrl(DEMO_REPO)}
                    disabled={loading}
                  >
                    Try Demo Repo
                  </button>
                  <button
                    id="run-repo-btn"
                    className="btn btn-primary btn-full"
                    style={{ marginTop: 8 }}
                    onClick={() => run("repo")}
                    disabled={loading}
                  >
                    {loading ? (
                      <><div className="spinner" /> Processing...</>
                    ) : (
                      "Run With Repo URL"
                    )}
                  </button>
                </div>
              ) : (
                <div className="sidebar-section">
                  <label htmlFor="zip-upload" className="label">ZIP File</label>
                  <input
                    id="zip-upload"
                    className="input"
                    type="file"
                    accept=".zip"
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                    disabled={loading}
                    style={{ padding: "8px 12px" }}
                  />
                  {file && (
                    <div style={{ fontSize: 12, color: "var(--success)", marginTop: 6 }}>
                      OK {file.name} ({(file.size / 1024).toFixed(0)} KB)
                    </div>
                  )}
                  <button
                    id="run-zip-btn"
                    className="btn btn-primary btn-full"
                    style={{ marginTop: 8 }}
                    onClick={() => run("zip")}
                    disabled={loading}
                  >
                    {loading ? (
                      <><div className="spinner" /> Processing...</>
                    ) : (
                      "Run With ZIP"
                    )}
                  </button>
                </div>
              )}

              {error && (
                <div className="alert alert-error sidebar-section">
                  <span>!</span> {error}
                </div>
              )}
              {success && (
                <div className="alert alert-success sidebar-section">
                  <span>OK</span> {success}
                </div>
              )}

              <div className="card-inset tip-card" style={{ fontSize: 12, color: "var(--ink-2)", lineHeight: 1.6 }}>
                <strong style={{ color: "var(--ink)" }}>Tip:</strong> Select a persona to adapt the output tone.
                Use "Try Demo Repo" to auto-fill a sample repository.
              </div>
            </div>
          </aside>

          <section className="dashboard-results">
            {loading && <LoadingSkeleton />}

            {!loading && (
              <>
                {hasResults && (
                  <div className="tabs">
                    {reviewData !== null && (
                      <button
                        id="tab-review"
                        className={`tab ${resultTab === "review" ? "active" : ""}`}
                        onClick={() => setResultTab("review")}
                      >
                        Code Review
                        <span className="tab-count">{reviewData.findings.length}</span>
                      </button>
                    )}
                    {docsData !== null && (
                      <button
                        id="tab-docs"
                        className={`tab ${resultTab === "docs" ? "active" : ""}`}
                        onClick={() => setResultTab("docs")}
                      >
                        Documentation
                      </button>
                    )}
                    {docsData !== null && (
                      <button
                        id="tab-graphs"
                        className={`tab ${resultTab === "graphs" ? "active" : ""}`}
                        onClick={() => setResultTab("graphs")}
                      >
                        Graphs
                      </button>
                    )}
                  </div>
                )}

                {resultTab === "review" && (
                  reviewData ? <ReviewResults data={reviewData} /> : <EmptyState tab="review" />
                )}

                {resultTab === "docs" && (
                  docsData ? <DocsResults data={docsData} /> : <EmptyState tab="docs" />
                )}

                {resultTab === "graphs" && (
                  docsData ? (
                    <div className="grid">
                      <GraphPanel title="Dependency Graph" graph={docsData.dependency_graph} />
                      <GraphPanel title="Execution Flowchart" graph={docsData.execution_flowchart} />
                      <GraphPanel title="Knowledge Graph" graph={docsData.knowledge_graph} />
                    </div>
                  ) : <EmptyState tab="graphs" />
                )}
              </>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
