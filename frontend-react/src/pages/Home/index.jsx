import { useEffect, useState } from "react";
import { getHomeAssistantOverview } from "../../services/api";

export default function HomePage() {
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      setOverview(await getHomeAssistantOverview());
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Home Assistant unavailable");
    }
  }

  useEffect(() => { load(); }, []);

  const entities = overview?.entities || [];
  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Home</h1>
          <p className="page-subtitle">Read-only Home Assistant awareness. Device control is not connected.</p>
        </div>
        <button type="button" className="secondary-button" onClick={load}>Refresh</button>
      </header>
      {error && <p className="journal-error">{error}</p>}
      <section className="home-status">
        <span><small>Status</small><strong>{overview?.status?.status || "loading"}</strong></span>
        <span><small>Connection</small><strong>{overview?.status?.connection_status || "checking"}</strong></span>
        <span><small>Entities</small><strong>{entities.length}</strong></span>
        <span><small>Access</small><strong>Read only</strong></span>
      </section>
      {overview && !overview.status.configured && <p className="answer">Add Home Assistant configuration to the private server environment to connect this view.</p>}
      <section className="home-entities" aria-label="Home Assistant entities">
        {entities.map((entity) => (
          <article className="home-entity" key={entity.entity_id}>
            <div><strong>{entity.name}</strong><small>{entity.entity_id}</small></div>
            <span>{entity.state}{entity.unit ? ` ${entity.unit}` : ""}</span>
          </article>
        ))}
      </section>
    </div>
  );
}
