import { useCallback, useEffect, useState } from "react";
import { getDecisionJournal } from "../../services/api";

function money(value) {
  if (value === null || value === undefined) return "—";
  return `$${Number(value).toFixed(6)}`;
}

function timestamp(value) {
  return new Date(value).toLocaleString();
}

export default function JournalPage() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setEntries(await getDecisionJournal(100));
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Decision Journal unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Decision Journal</h1>
          <p className="page-subtitle">Why Vera chose a route, what it cost, and whether it worked.</p>
        </div>
        <button type="button" className="secondary-button" onClick={load}>Refresh</button>
      </header>

      {error && <p className="journal-error">{error}</p>}
      {loading ? <p>Loading decisions…</p> : (
        <section className="journal-list" aria-label="Vera decision history">
          {entries.length === 0 && <p className="answer">No decisions have been recorded yet.</p>}
          {entries.map((entry) => (
            <article className="journal-entry" key={entry.id}>
              <div className="journal-entry-heading">
                <div>
                  <span className={`journal-kind ${entry.kind}`}>{entry.kind.replaceAll("_", " ")}</span>
                  <h2>{entry.title}</h2>
                </div>
                <time dateTime={entry.created_utc}>{timestamp(entry.created_utc)}</time>
              </div>
              <div className="journal-facts">
                <span><small>Decision</small>{entry.decision || "—"}</span>
                <span><small>Domain</small>{entry.domain || "—"}</span>
                <span><small>Route</small>{entry.provider || "—"}</span>
                <span><small>Model</small>{entry.model || "—"}</span>
                <span><small>Estimated</small>{money(entry.estimated_cost_usd)}</span>
                <span><small>Actual</small>{money(entry.actual_cost_usd)}</span>
              </div>
              {entry.reason && <p className="journal-reason">{entry.reason}</p>}
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
