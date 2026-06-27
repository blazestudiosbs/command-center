import { useCallback, useEffect, useState } from "react";
import Panel from "../../components/Panel";
import { getSecurityStatus } from "../../services/api";

function badgeTone(value) {
  if (value === "problem" || value === "public" || value === false) return "problem";
  if (value === "recommendation" || value === "lan" || value === "lan-only") return "recommendation";
  return "good";
}

function StatusBadge({ tone = "good", children }) {
  return <span className={`security-badge ${tone}`}>{children}</span>;
}

function ScoreCard({ score }) {
  const tone = score >= 85 ? "good" : score >= 65 ? "recommendation" : "problem";
  return (
    <div className={`security-score-card ${tone}`}>
      <div>
        <div className="label">Security Score</div>
        <strong>{score == null ? "Loading..." : `${score}/100`}</strong>
      </div>
      <StatusBadge tone={tone}>{tone === "good" ? "Good" : tone === "recommendation" ? "Recommendation" : "Problem"}</StatusBadge>
    </div>
  );
}

function PortList({ ports, emptyText }) {
  if (!ports?.length) {
    return <div className="security-empty">{emptyText}</div>;
  }

  return (
    <div className="security-port-list">
      {ports.map((entry) => (
        <div className="security-port-row" key={`${entry.port}-${entry.protocol}`}>
          <div>
            <strong>{entry.port}</strong>
            <span className="security-port-protocol">/{entry.protocol || "tcp"}</span>
          </div>
          <div className="security-port-meta">
            <span>{entry.processes?.length ? entry.processes.join(", ") : "unknown process"}</span>
            <span>{entry.addresses?.length ? entry.addresses.join(", ") : "unknown address"}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function DockerPorts({ ports }) {
  if (!ports?.length) {
    return <div className="security-empty">No running containers with published ports detected.</div>;
  }

  return (
    <div className="security-table-wrap">
      <table className="security-table">
        <thead>
          <tr>
            <th>Container</th>
            <th>Host</th>
            <th>Container Port</th>
          </tr>
        </thead>
        <tbody>
          {ports.map((port) => (
            <tr key={`${port.container}-${port.host_ip}-${port.host_port}-${port.container_port}`}>
              <td>{port.container}</td>
              <td>{port.host_ip}:{port.host_port}</td>
              <td>{port.container_port}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Recommendations({ recommendations }) {
  if (!recommendations?.length) {
    return <div className="security-empty">No recommendations available.</div>;
  }

  return (
    <div className="security-recommendations">
      {recommendations.map((item) => (
        <div className={`security-recommendation ${item.severity}`} key={`${item.severity}-${item.title}`}>
          <StatusBadge tone={badgeTone(item.severity)}>
            {item.severity === "good" ? "Good" : item.severity === "problem" ? "Problem" : "Recommendation"}
          </StatusBadge>
          <div>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function SecurityPage() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);

  const loadSecurityStatus = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getSecurityStatus();
      setStatus(data);
      setError("");
      setLastUpdated(new Date());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSecurityStatus();
  }, [loadSecurityStatus]);

  const firewallEnabled = Boolean(status?.firewall_enabled);
  const defaultPolicy = status?.default_policy || "unknown";
  const sshExposure = status?.ssh?.exposure || "unknown";

  return (
    <div className="page-content security-page">
      <header className="page-header">
        <div>
          <h1>Security Workspace</h1>
          <p className="page-subtitle">Central security posture monitoring for firewall, SSH, open ports, and Docker exposure.</p>
        </div>
        <div className="security-header-actions">
          <div>
            <div className="label">Last Updated</div>
            <strong>{lastUpdated ? lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "Not loaded"}</strong>
          </div>
          <button disabled={loading} onClick={loadSecurityStatus}>{loading ? "Refreshing..." : "Refresh"}</button>
        </div>
      </header>

      {error ? <div className="action-result failure">Security status error: {error}</div> : null}

      <ScoreCard score={status?.score} />

      <section className="security-grid">
        <Panel title="Firewall">
          <div className="security-kv-list">
            <div>
              <span>Enabled</span>
              <StatusBadge tone={firewallEnabled ? "good" : "problem"}>{firewallEnabled ? "Yes" : "No"}</StatusBadge>
            </div>
            <div>
              <span>Default Policy</span>
              <strong>{defaultPolicy}</strong>
            </div>
            <div>
              <span>Allowed Inbound Rules</span>
              <strong>{status?.ufw?.allowed_inbound_rules?.length ?? 0}</strong>
            </div>
          </div>
        </Panel>

        <Panel title="SSH">
          <div className="security-kv-list">
            <div>
              <span>sshd Running</span>
              <StatusBadge tone={status?.ssh?.running ? "recommendation" : "good"}>{status?.ssh?.running ? "Yes" : "No"}</StatusBadge>
            </div>
            <div>
              <span>Exposure</span>
              <StatusBadge tone={badgeTone(sshExposure)}>{sshExposure}</StatusBadge>
            </div>
          </div>
        </Panel>
      </section>

      <section className="security-grid three-column">
        <Panel title="Public Ports">
          <PortList ports={status?.public_ports} emptyText="No public listening TCP ports detected." />
        </Panel>

        <Panel title="LAN Ports">
          <PortList ports={status?.lan_ports} emptyText="No LAN-only listening TCP ports detected." />
        </Panel>

        <Panel title="Localhost Ports">
          <PortList ports={status?.localhost_ports} emptyText="No localhost-only listening TCP ports detected." />
        </Panel>
      </section>

      <Panel title="Docker Published Ports" className="panel-fullwidth">
        <DockerPorts ports={status?.docker_published_ports} />
      </Panel>

      <Panel title="Recommendations" className="panel-fullwidth">
        <Recommendations recommendations={status?.recommendations} />
      </Panel>
    </div>
  );
}
