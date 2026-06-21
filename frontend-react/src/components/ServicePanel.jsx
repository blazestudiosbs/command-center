import Panel from "./Panel";

export default function ServicePanel({ services }) {
  const serviceList = Array.isArray(services) ? services : [];

  return (
    <Panel title="Services">
      <div className="list">
        {serviceList.length === 0 && (
          <div className="row">
            <strong>No services detected</strong>
            <span>Waiting for backend service data</span>
          </div>
        )}

        {serviceList.map((s) => (
          <div className="row" key={s.name}>
            <strong>{s.name}</strong>
            <span>{s.status} | {s.detail}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
