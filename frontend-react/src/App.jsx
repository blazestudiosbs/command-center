import { useEffect, useState } from "react";
import "./App.css";

import { getAnalysis, getBriefing, getStatus } from "./services/api";
import StatCard from "./components/StatCard";
import BriefingPanel from "./components/BriefingPanel";
import AnalysisPanel from "./components/AnalysisPanel";
import ProjectPanel from "./components/ProjectPanel";
import DockerPanel from "./components/DockerPanel";
import NetworkPanel from "./components/NetworkPanel";
import ServicePanel from "./components/ServicePanel";
import RouterPanel from "./components/RouterPanel";

function App() {
  const [status, setStatus] = useState(null);
  const [analysis, setAnalysis] = useState("");
  const [briefing, setBriefing] = useState("");
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");

  async function loadStatus() {
    try {
      const data = await getStatus();
      setStatus(data);
      setError("");
    } catch (err) {
      setError(err.message);
    }
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
    const timer = setInterval(loadStatus, 30000);
    return () => clearInterval(timer);
  }, []);

  if (error) return <main className="page">Error: {error}</main>;
  if (!status) return <main className="page">Loading Command Center...</main>;

  const services = status.services ?? [];
  const projects = status.projects ?? [];
  const docker = status.docker ?? { running: 0, total: 0, containers: [] };
  const network = status.network_devices ?? [];

  return (
    <main className="page">
      <header className="header">
        <div>
          <h1>Command Center</h1>
          <p className="subtitle">Brain online. System observer active.</p>
        </div>
        <button onClick={loadStatus}>Refresh</button>
      </header>

      <section className="grid">
        <StatCard label="Health" value={status.health ?? "unknown"} />
        <StatCard label="Health Score" value={`${status.health_score ?? 0}/100`} />
        <StatCard label="CPU" value={`${status.cpu_usage_percent ?? 0}%`} />
        <StatCard label="Memory" value={`${status.memory_used_percent ?? 0}%`} />
        <StatCard label="Disk" value={`${status.disk_used_percent ?? 0}%`} />
        <StatCard label="Projects" value={projects.length} />
        <StatCard label="Services" value={services.length} />
        <StatCard label="Docker" value={`${docker.running}/${docker.total}`} />
        <StatCard label="Network" value={network.length} />
        <StatCard label="Uptime" value={status.uptime ?? "unknown"} />
      </section>

      <BriefingPanel briefing={briefing} loading={loading === "briefing"} onGenerate={runBriefing} />
      <AnalysisPanel analysis={analysis} loading={loading === "analysis"} onAnalyze={runAnalysis} />
      <ProjectPanel projects={projects} />
      <ServicePanel services={services} />
      <DockerPanel docker={docker} />
      <NetworkPanel devices={network} />
      <RouterPanel router={status.router_health} />
    </main>
  );
}

export default App;
