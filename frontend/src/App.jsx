import { useEffect, useState } from "react";

const API = "http://127.0.0.1:8001";
const BUSY = ["pending", "running"];
const SEV_COLOR = { high: "#b42318", medium: "#b54708", low: "#475467" };

const box = {
  background: "#fff",
  border: "1px solid #e4e7ec",
  borderRadius: 10,
  padding: "14px 18px",
};

function Card({ label, value, color }) {
  return (
    <div style={{ ...box, minWidth: 120 }}>
      <div style={{ fontSize: 28, fontWeight: 700, color: color || "inherit" }}>{value}</div>
      <div style={{ color: "#667085", fontSize: 14 }}>{label}</div>
    </div>
  );
}

function BarChart({ title, counts }) {
  const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, n]) => n));
  return (
    <div style={{ ...box, flex: 1, minWidth: 280 }}>
      <h3 style={{ marginTop: 0 }}>{title}</h3>
      {entries.length === 0 && <p style={{ color: "#667085" }}>No data</p>}
      {entries.map(([name, n]) => (
        <div key={name} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span style={{ width: 90 }}>{name}</span>
          <div style={{ flex: 1, background: "#eef0f3", borderRadius: 4 }}>
            <div
              style={{
                width: `${(n / max) * 100}%`,
                background: "#3b6cf6",
                height: 18,
                borderRadius: 4,
              }}
            />
          </div>
          <span style={{ width: 40, textAlign: "right" }}>{n}</span>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [repoUrl, setRepoUrl] = useState("https://github.com/pallets/flask");
  const [analysisId, setAnalysisId] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [tool, setTool] = useState("");
  const [category, setCategory] = useState("");
  const [openId, setOpenId] = useState(null);

  async function startAnalysis(e) {
    e.preventDefault();
    setError("");
    setData(null);
    setAnalysisId(null);
    setTool("");
    setCategory("");
    setOpenId(null);
    setSubmitting(true);
    try {
      const res = await fetch(`${API}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: repoUrl }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "Request failed");
      setAnalysisId(body.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  // Poll until the analysis finishes, then a few more times to pick up AI explanations
  useEffect(() => {
    if (!analysisId) return;
    let stopped = false;
    let timer;
    let extraPolls = 0;

    async function poll() {
      try {
        const params = new URLSearchParams();
        if (tool) params.set("tool", tool);
        if (category) params.set("category", category);
        const res = await fetch(`${API}/analysis/${analysisId}?${params}`);
        const body = await res.json();
        if (stopped) return;
        setData(body);
        if (BUSY.includes(body.status)) {
          timer = setTimeout(poll, 3000);
        } else if (extraPolls < 8) {
          extraPolls += 1;
          timer = setTimeout(poll, 3000);
        }
      } catch {
        if (!stopped) setError("Could not reach the backend");
      }
    }

    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [analysisId, tool, category]);

  const busy = data && BUSY.includes(data.status);
  const bySeverity = data?.findings_by_severity || {};
  const wholeTotal = Object.values(data?.findings_by_tool || {}).reduce((a, b) => a + b, 0);

  return (
    <div style={{ maxWidth: 1000, margin: "32px auto", padding: "0 16px" }}>
      <h1 style={{ marginBottom: 16 }}>Code Review & Repository Analyzer</h1>

      <form onSubmit={startAnalysis} style={{ display: "flex", gap: 8 }}>
        <input
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          placeholder="https://github.com/owner/repo"
          style={{ flex: 1, padding: 10, fontSize: 16 }}
        />
        <button type="submit" disabled={submitting} style={{ padding: "10px 18px", fontSize: 16 }}>
          {submitting ? "Starting..." : "Analyze"}
        </button>
      </form>

      {error && <p style={{ color: "#b42318" }}>Error: {error}</p>}

      {data && (
        <div style={{ marginTop: 24 }}>
          <p>
            <b>Status:</b> {data.status}
            {busy && " (working... this can take a minute)"}
          </p>
          {data.error && <p style={{ color: "#b42318" }}>{data.error}</p>}

          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
            <Card label="Total findings" value={wholeTotal} />
            <Card label="High" value={bySeverity.high || 0} color={SEV_COLOR.high} />
            <Card label="Medium" value={bySeverity.medium || 0} color={SEV_COLOR.medium} />
            <Card label="Low" value={bySeverity.low || 0} color={SEV_COLOR.low} />
          </div>

          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 24 }}>
            <BarChart title="Findings by tool" counts={data.findings_by_tool} />
            <BarChart title="Findings by category" counts={data.findings_by_category} />
          </div>

          <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 8 }}>
            <h2 style={{ margin: 0, flex: 1 }}>
              Findings ({data.findings.length} shown of {data.total_findings})
            </h2>
            <select value={tool} onChange={(e) => setTool(e.target.value)} style={{ padding: 6 }}>
              <option value="">All tools</option>
              {Object.keys(data.findings_by_tool).map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <select value={category} onChange={(e) => setCategory(e.target.value)} style={{ padding: 6 }}>
              <option value="">All categories</option>
              {Object.keys(data.findings_by_category).map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <table style={{ ...box, width: "100%", borderCollapse: "collapse", padding: 0 }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #e4e7ec" }}>
                <th style={{ padding: 8 }}>Severity</th>
                <th style={{ padding: 8 }}>Tool</th>
                <th style={{ padding: 8 }}>Location</th>
                <th style={{ padding: 8 }}>Rule</th>
                <th style={{ padding: 8 }}>Message</th>
                <th style={{ padding: 8 }}>AI</th>
              </tr>
            </thead>
            <tbody>
              {data.findings.map((f) => (
                <FindingRow
                  key={f.id}
                  f={f}
                  open={openId === f.id}
                  onToggle={() => setOpenId(openId === f.id ? null : f.id)}
                />
              ))}
            </tbody>
          </table>
          {data.findings.length === 0 && !busy && (
            <p style={{ color: "#667085" }}>No findings match.</p>
          )}
        </div>
      )}
    </div>
  );
}

function FindingRow({ f, open, onToggle }) {
  const cell = { padding: 8, verticalAlign: "top", borderBottom: "1px solid #f0f1f3" };
  return (
    <>
      <tr onClick={onToggle} style={{ cursor: "pointer" }}>
        <td style={{ ...cell, color: SEV_COLOR[f.severity], fontWeight: 600 }}>{f.severity}</td>
        <td style={cell}>{f.tool}</td>
        <td style={{ ...cell, fontFamily: "monospace", fontSize: 13 }}>
          {f.file_path}
          {f.line ? `:${f.line}` : ""}
        </td>
        <td style={cell}>{f.rule_id}</td>
        <td style={cell}>{f.message}</td>
        <td style={cell}>{f.ai_explanation ? "✨" : ""}</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={6} style={{ padding: "8px 16px 14px", background: "#f9fafb" }}>
            {f.ai_explanation ? (
              <div style={{ whiteSpace: "pre-wrap" }}>{f.ai_explanation}</div>
            ) : (
              <span style={{ color: "#667085" }}>
                No AI explanation (only the top 10 findings are explained).
              </span>
            )}
          </td>
        </tr>
      )}
    </>
  );
}