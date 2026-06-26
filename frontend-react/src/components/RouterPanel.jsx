import Panel from "./Panel";

export default function RouterPanel({ router }) {
  if (!router) {
    return (
      <Panel title="Router">
        <p className="answer">Router health data unavailable.</p>
      </Panel>
    );
  }

  return (
    <Panel title="Router">
      <div className="list">
        <div className="row">
          <strong>{router.name}</strong>
          <span>{router.host}</span>
        </div>
        <div className="row">
          <strong>Status</strong>
          <span>{router.status}</span>
        </div>
        <div className="row">
          <strong>Latency</strong>
          <span>{router.latency_ms ?? "unknown"} ms</span>
        </div>
        <div className="row">
          <strong>Internet</strong>
          <span>{router.internet_online ? "online" : "offline"}</span>
        </div>
        <div className="row">
          <strong>DNS</strong>
          <span>{router.dns_online ? "online" : "offline"}</span>
        </div>
        <div className="row">
          <strong>Admin Page</strong>
          <span>{router.web_admin_online ? "reachable" : "unreachable"}</span>
        </div>
      </div>
    </Panel>
  );
}
