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
  const [summary, setSummary] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (append = false) => {
    try {
      const offset = append ? entries.length : 0;
      const data = await getDecisionJournal(25, offset);
      setEntries((current) => append ? [...current, ...data.entries] : data.entries);
      setSummary(data.summary);
      setHasMore(data.has_more);
      setError("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Decision Journal unavailable");
    } finally {
      setLoading(false);
    }
  }, [entries.length]);

  useEffect(() => {
    load(false);
    // Initial load only; later pagination changes entries.length.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Decision Journal</h1>
          <p className="page-subtitle">Why Vera chose a route, what it cost, and whether it worked.</p>
        </div>
        <button type="button" className="secondary-button" onClick={() => load(false)}>Refresh</button>
      </header>

      {error && <p className="journal-error">{error}</p>}
      {summary && (
        <section className="journal-summary" aria-label="Decision summary">
          <span><small>Total entries</small><strong>{summary.total_entries}</strong></span>
          <span><small>Local routes</small><strong>{summary.local_routes}</strong></span>
          <span><small>Cloud routes</small><strong>{summary.cloud_routes}</strong></span>
          <span><small>Failures</small><strong>{summary.failures}</strong></span>
          <span><small>Cloud cost</small><strong>{money(summary.actual_cloud_cost_usd)}</strong></span>
        </section>
      )}
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
          {hasMore && (
            <button type="button" className="secondary-button journal-load-more" onClick={() => load(true)}>
              Load more
            </button>
          )}
        </section>
      )}
    </div>
  );
}
