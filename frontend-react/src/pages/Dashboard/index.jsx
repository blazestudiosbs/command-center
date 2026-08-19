import { useEffect, useState } from "react";
import StatCard from "../../components/StatCard";
import Panel from "../../components/Panel";
import BriefingPanel from "../../components/BriefingPanel";
import AnalysisPanel from "../../components/AnalysisPanel";
import ProjectPanel from "../../components/ProjectPanel";
import RouterPanel from "../../components/RouterPanel";
import { getStatus, getAnalysis, getBriefing, getAdvisorRecommendations } from "../../services/api";

export default function DashboardPage() {
  const [status, setStatus] = useState(null);
  const [advisorRecommendations, setAdvisorRecommendations] = useState([]);
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

    async function loadAdvisor() {
      try {
        const recommendations = await getAdvisorRecommendations();
        setAdvisorRecommendations(recommendations || []);
      } catch (err) {
        setAdvisorRecommendations([]);
      }
    }

    loadStatus();
    loadAdvisor();
    const timer = setInterval(() => {
      loadStatus();
      loadAdvisor();
    }, 30000);
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
  const advisorSummary = advisorRecommendations[0];

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
          <Panel title="Advisor Summary">
            {advisorSummary ? (
              <div className="answer">
                <strong>{advisorSummary.title}</strong>
                <p>{advisorSummary.summary}</p>
                <p><span className="label">Priority:</span> {advisorSummary.priority}</p>
                <p><span className="label">Action:</span> {advisorSummary.action}</p>
              </div>
            ) : (
              <p className="answer">Loading advisor recommendations...</p>
            )}
          </Panel>
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
