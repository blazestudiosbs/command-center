import { useEffect, useState } from "react";
import "./App.css";
import { getAnalysis, getBriefing, getStatus } from "./services/api";
import StatCard from "./components/StatCard";
import Panel from "./components/Panel";

function App() {
  const [status, setStatus] = useState(null);
  const [analysis, setAnalysis] = useState("");
  const [briefing, setBriefing] = useState("");
  const [loading, setLoading] = useState("");

  async function loadStatus() {
    const data = await getStatus();
    setStatus(data);
  }

  async function runAnalysis() {
    setLoading("analysis");
    setAnalysis(await getAnalysis());
    setLoading("");
  }

  async function runBriefing() {
    setLoading("briefing");
    setBriefing(await getBriefing());
    setLoading("");
  }

  useEffect(() => {
    loadStatus();
  }, []);

  if (!status) return <main className="page">Loading Command Center...</main>;

  return (
    <main className="page">
      <header className="header">
        <div>
          <h1>Command Center</h1>
          <p className="subtitle">Brain online. Watching the machine-room lanterns.</p>
        </div>
        <button onClick={loadStatus}>Refresh</button>
      </header>

      <section className="grid">
        <StatCard label="Health" value={status.health} />
        <StatCard label="Health Score" value={`${status.health_score}/100`} />
        <StatCard label="CPU" value={`${status.cpu_usage_percent}%`} />
        <StatCard label="Memory" value={`${status.memory_used_percent}%`} />
        <StatCard label="Disk" value={`${status.disk_used_percent}%`} />
        <StatCard label="Uptime" value={status.uptime} />
      </section>

      <Panel title="Daily Briefing">
        <button onClick={runBriefing}>Generate Briefing</button>
        <p className="answer">{loading === "briefing" ? "Generating briefing..." : briefing}</p>
      </Panel>

      <Panel title="AI Analysis">
        <button onClick={runAnalysis}>Analyze Status</button>
        <p className="answer">{loading === "analysis" ? "Analyzing status..." : analysis}</p>
      </Panel>

      <Panel title="Projects">
        <div className="list">
          {status.projects.map((p) => (
            <div className="row" key={p.name}>
              <strong>{p.name}</strong>
              <span>{p.type} | {p.priority} | {p.status}</span>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Docker">
        <div className="list">
          {status.docker.containers.map((c) => (
            <div className="row" key={c.name}>
              <strong>{c.name}</strong>
              <span>{c.status} | {c.image}</span>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Network">
        <div className="list">
          {status.network_devices.map((d) => (
            <div className="row" key={d.ip}>
              <strong>{d.name}</strong>
              <span>{d.ip} | {d.state}</span>
            </div>
          ))}
        </div>
      </Panel>
    </main>
  );
}

export default App;
