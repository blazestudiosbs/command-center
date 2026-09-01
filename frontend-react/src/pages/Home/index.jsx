import { useEffect, useState } from "react";
import { confirmHomeLightAction, executeHomeLightAction, getHomeAssistantOverview, getPendingHomeLightActions, setHomeLightPermission } from "../../services/api";

export default function HomePage() {
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function load() {
    try {
      const [nextOverview, actions] = await Promise.all([getHomeAssistantOverview(), getPendingHomeLightActions()]);
      setOverview(nextOverview); setPending(actions);
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Home Assistant unavailable");
    }
  }

  useEffect(() => { load(); }, []);

  async function changePermission(entity, enabled) {
    setBusy(true); setMessage("");
    try {
      await setHomeLightPermission(entity.entity_id, enabled);
      setOverview((current) => ({ ...current, entities: current.entities.map((item) => item.entity_id === entity.entity_id ? { ...item, control_enabled: enabled } : item) }));
      setMessage(`${entity.name} control ${enabled ? "enabled" : "disabled"}.`);
    } catch (err) { setError(err.response?.data?.detail || err.message); }
    finally { setBusy(false); }
  }

  async function execute(entity, action) {
    setBusy(true); setMessage("");
    try {
      const result = await executeHomeLightAction({ entity_id: entity.entity_id, action });
      setMessage(`${result.entity_name} was turned ${action === "turn_on" ? "on" : "off"} and verified.`);
      await load();
    } catch (err) { setError(err.response?.data?.detail || err.message); }
    finally { setBusy(false); }
  }

  async function confirm(action) {
    setBusy(true); setMessage("");
    try {
      const result = await confirmHomeLightAction(action.id);
      setPending((current) => current.filter((item) => item.id !== action.id));
      setMessage(`${result.entity_name} was turned ${result.action === "turn_on" ? "on" : "off"}.`);
      await load();
    } catch (err) { setError(err.response?.data?.detail || err.message); }
    finally { setBusy(false); }
  }

  const entities = overview?.entities || [];
  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Home</h1>
          <p className="page-subtitle">Home Assistant awareness with direct, verified control for individually approved lights.</p>
        </div>
        <button type="button" className="secondary-button" onClick={load}>Refresh</button>
      </header>
      {error && <p className="journal-error">{error}</p>}
      {message && <p className="monitoring-check-message">{message}</p>}
      <section className="home-status">
        <span><small>Status</small><strong>{overview?.status?.status || "loading"}</strong></span>
        <span><small>Connection</small><strong>{overview?.status?.connection_status || "checking"}</strong></span>
        <span><small>Entities</small><strong>{entities.length}</strong></span>
        <span><small>Control</small><strong>Approved lights only</strong></span>
      </section>
      {overview?.hidden_group_members > 0 && <p className="answer">{overview.hidden_group_members} physical light {overview.hidden_group_members === 1 ? "entity is" : "entities are"} consolidated under Home Assistant light groups.</p>}
      {overview && !overview.status.configured && <p className="answer">Add Home Assistant configuration to the private server environment to connect this view.</p>}
      <section className="home-entities" aria-label="Home Assistant entities">
        {entities.map((entity) => (
          <article className="home-entity" key={entity.entity_id}>
            <div><strong>{entity.name}</strong><small>{entity.entity_id}{entity.group_members?.length ? ` · group of ${entity.group_members.length}` : ""}</small></div>
            <span>{entity.state}{entity.unit ? ` ${entity.unit}` : ""}</span>
            {entity.domain === "light" && <div>
              <label><input type="checkbox" disabled={busy} checked={entity.control_enabled} onChange={(event) => changePermission(entity, event.target.checked)} /> Vera control</label>
              {entity.control_enabled && <><button type="button" className="text-button" disabled={busy || entity.state === "on" || entity.state === "unavailable"} onClick={() => execute(entity, "turn_on")}>Turn on</button><button type="button" className="text-button" disabled={busy || entity.state === "off" || entity.state === "unavailable"} onClick={() => execute(entity, "turn_off")}>Turn off</button></>}
            </div>}
          </article>
        ))}
      </section>
      <section className="panel">
        <h2>Pending light actions</h2>
        {pending.length === 0 && <p className="answer">No light actions are awaiting confirmation.</p>}
        <div className="home-entities">{pending.map((action) => <article className="home-entity" key={action.id}><div><strong>{action.entity_name}</strong><small>{action.action.replace("_", " ")} · expires {new Date(action.expires_utc).toLocaleTimeString()}</small></div><button type="button" className="secondary-button" disabled={busy} onClick={() => confirm(action)}>Confirm</button></article>)}</div>
      </section>
    </div>
  );
}
