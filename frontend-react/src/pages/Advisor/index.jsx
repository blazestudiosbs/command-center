import { useEffect, useState } from "react";
import Panel from "../../components/Panel";
import { getAdvisorRecommendations } from "../../services/api";

export default function AdvisorPage() {
  const [recommendations, setRecommendations] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadRecommendations() {
    setLoading(true);
    setError("");

    try {
      const data = await getAdvisorRecommendations();
      setRecommendations(data);
    } catch (err) {
      setError(err.message || "Unable to load recommendations.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRecommendations();
  }, []);

  return (
    <div className="page-content">
      <header className="page-header">
        <div>
          <h1>Advisor</h1>
          <p className="page-subtitle">Hardware and service recommendations based on your system status.</p>
        </div>
        <div className="panel-actions">
          <button type="button" onClick={loadRecommendations} disabled={loading}>
            Refresh Recommendations
          </button>
        </div>
      </header>

      <Panel title="Recommendations">
        {loading && <p className="answer">Loading recommendations...</p>}
        {error && <p className="answer">Error: {error}</p>}
        {!loading && !error && (!recommendations || recommendations.length === 0) && (
          <p className="answer">No recommendations available yet.</p>
        )}
        <div className="list">
          {recommendations?.map((item, index) => (
            <section className="card" key={`${item.title}-${index}`}>
              <div className="row">
                <span className="label">Category</span>
                <strong>{item.category}</strong>
              </div>
              <div className="row">
                <span className="label">Priority</span>
                <strong>{item.priority}</strong>
              </div>
              <div className="row">
                <span className="label">Title</span>
                <strong>{item.title}</strong>
              </div>
              <div className="row">
                <span className="label">Summary</span>
                <span>{item.summary}</span>
              </div>
              <div className="row">
                <span className="label">Reason</span>
                <span>{item.reason}</span>
              </div>
              <div className="row">
                <span className="label">Estimated Cost</span>
                <span>{item.estimated_cost}</span>
              </div>
              <div className="row">
                <span className="label">Benefit</span>
                <span>{item.benefit}</span>
              </div>
              <div className="row">
                <span className="label">Action</span>
                <span>{item.action}</span>
              </div>
            </section>
          ))}
        </div>
      </Panel>
    </div>
  );
}
