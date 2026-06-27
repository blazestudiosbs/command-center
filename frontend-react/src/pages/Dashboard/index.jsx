import { useEffect, useState } from "react";
import StatCard from "../../components/StatCard";
import BriefingPanel from "../../components/BriefingPanel";
import AnalysisPanel from "../../components/AnalysisPanel";
import ProjectPanel from "../../components/ProjectPanel";
import RouterPanel from "../../components/RouterPanel";
import { getStatus, getAnalysis, getBriefing } from "../../services/api";

export default function DashboardPage() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");
  const [analysis, setAnalysis] = useState("");
  const [briefing, setBriefing] = useState("");

  useEffect(() => {
    async function loadStatus() {
      try {
        const data = await getStatus();
        setStatus(data);
        setError("");
      } catch (err) {
        setError(err.message);
      }
    }

    loadStatus();
    const timer = setInterval(loadStatus, 30000);
    return () => clearInterval(timer);
  }, []);

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

  if (error) return <div className="page-content">Error: {error}</div>;
  if (!status) return <div className="page-content">Loading overview...</div>;

  const projects = status.projects ?? [];
  const routerHealth = status.router_health;

  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p className="page-subtitle">Overview of system health and active workspaces.</p>
        </div>
      </header>

      <section className="dashboard-grid">
        <StatCard label="Health" value={status.health ?? "unknown"} />
        <StatCard label="CPU" value={`${status.cpu_usage_percent ?? 0}%`} />
        <StatCard label="Memory" value={`${status.memory_used_percent ?? 0}%`} />
        <StatCard label="Disk" value={`${status.disk_used_percent ?? 0}%`} />
        <StatCard label="Projects" value={projects.length} />
        <StatCard label="Services" value={status.services?.length ?? 0} />
      </section>

      <section className="workspace-grid">
        <div className="workspace-column">
          <BriefingPanel briefing={briefing} loading={loading === "briefing"} onGenerate={runBriefing} />
          <AnalysisPanel analysis={analysis} loading={loading === "analysis"} onAnalyze={runAnalysis} />
        </div>
        <div className="workspace-column">
          <RouterPanel router={routerHealth} />
          <ProjectPanel projects={projects} />
        </div>
      </section>
    </div>
  );
}
