import { useEffect, useState } from "react";
import { getAgents, updateAgentPermission } from "../../services/api";

export default function AgentsPage() {
  const [agents, setAgents] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  async function load() {
    try {
      setAgents(await getAgents());
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Agent permissions unavailable");
    }
  }

  useEffect(() => { load(); }, []);

  async function change(agentId, capability, enabled) {
    const key = `${agentId}:${capability}`;
    setBusy(key);
    try {
      const updated = await updateAgentPermission(agentId, capability, enabled);
      setAgents((current) => current.map((agent) => agent.id === updated.id ? updated : agent));
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Permission could not be changed");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Agent Permissions</h1>
          <p className="page-subtitle">Control which Vera agents may run and what each one is allowed to do.</p>
        </div>
        <button type="button" className="secondary-button" onClick={load}>Refresh</button>
      </header>
      {error && <p className="journal-error">{error}</p>}
      <section className="agent-permission-grid">
        {agents.map((agent) => (
          <article className={`agent-permission-card ${agent.enabled ? "" : "disabled"}`} key={agent.id}>
            <div className="agent-permission-heading">
              <div><h2>{agent.name}</h2><p>{agent.description}</p></div>
              <label className="agent-switch">
                <input
                  type="checkbox"
                  checked={agent.enabled}
                  disabled={busy === `${agent.id}:enabled`}
                  onChange={(event) => change(agent.id, "enabled", event.target.checked)}
                />
                {agent.enabled ? "On" : "Off"}
              </label>
            </div>
            <div className="agent-capabilities">
              {agent.capabilities.map((capability) => (
                <label className={!capability.available ? "locked" : ""} key={capability.id}>
                  <span>{capability.name}{!capability.available && <small>Not available</small>}</span>
                  <input
                    type="checkbox"
                    checked={capability.enabled}
                    disabled={!agent.enabled || !capability.available || busy === `${agent.id}:${capability.id}`}
                    onChange={(event) => change(agent.id, capability.id, event.target.checked)}
                  />
                </label>
              ))}
            </div>
          </article>
        ))}
      </section>
      <p className="answer">Turning an agent off does not delete its data or disconnect its integrations. Locked capabilities cannot be enabled.</p>
    </div>
  );
}
