import { useEffect, useState } from "react";
import axios from "axios";
import "./App.css";

function App() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    axios
      .get("/api/status")
      .then((res) => setStatus(res.data))
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <main className="page">Error: {error}</main>;
  if (!status) return <main className="page">Loading Command Center...</main>;

  return (
    <main className="page">
      <h1>Command Center</h1>
      <p className="subtitle">React dashboard connected to FastAPI.</p>

      <section className="grid">
        <Card label="Health" value={status.health} />
        <Card label="Health Score" value={`${status.health_score}/100`} />
        <Card label="Hostname" value={status.hostname} />
        <Card label="CPU Usage" value={`${status.cpu_usage_percent}%`} />
        <Card label="Memory Used" value={`${status.memory_used_percent}%`} />
        <Card label="Disk Used" value={`${status.disk_used_percent}%`} />
        <Card label="Projects" value={status.projects?.length ?? 0} />
        <Card label="Network Devices" value={status.network_devices?.length ?? 0} />
        <Card label="Docker Running" value={`${status.docker?.running ?? 0}/${status.docker?.total ?? 0}`} />
        <Card label="Uptime" value={status.uptime} />
      </section>
    </main>
  );
}

function Card({ label, value }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

export default App;
