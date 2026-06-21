import { useEffect, useState } from "react";
import "./App.css";

import { getAnalysis, getBriefing, getStatus } from "./services/api";
import StatCard from "./components/StatCard";
import BriefingPanel from "./components/BriefingPanel";
import AnalysisPanel from "./components/AnalysisPanel";
import ProjectPanel from "./components/ProjectPanel";
import DockerPanel from "./components/DockerPanel";
import NetworkPanel from "./components/NetworkPanel";

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

    const timer = setInterval(loadStatus, 30000);
    return () => clearInterval(timer);
  }, []);

  if (!status) {
    return <main className="page">Loading Command Center...</main>;
  }

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
        <StatCard label="Health" value={status.health} />
        <StatCard label="Health Score" value={`${status.health_score}/100`} />
        <StatCard label="CPU" value={`${status.cpu_usage_percent}%`} />
        <StatCard label="Memory" value={`${status.memory_used_percent}%`} />
        <StatCard label="Disk" value={`${status.disk_used_percent}%`} />
        <StatCard label="Projects" value={status.projects.length} />
        <StatCard label="Docker" value={`${status.docker.running}/${status.docker.total}`} />
        <StatCard label="Network" value={status.network_devices.length} />
        <StatCard label="Uptime" value={status.uptime} />
      </section>

      <BriefingPanel
        briefing={briefing}
        loading={loading === "briefing"}
        onGenerate={runBriefing}
      />

      <AnalysisPanel
        analysis={analysis}
        loading={loading === "analysis"}
        onAnalyze={runAnalysis}
      />

      <ProjectPanel projects={status.projects} />
      <DockerPanel docker={status.docker} />
      <NetworkPanel devices={status.network_devices} />
    </main>
  );
}

export default App;
