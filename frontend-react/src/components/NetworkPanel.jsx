import Panel from "./Panel";

export default function NetworkPanel({ devices }) {
  return (
    <Panel title="Network">
      <div className="list">
        {devices.map((d) => (
          <div className="row" key={d.ip}>
            <strong>{d.name}</strong>
            <span>{d.ip} | {d.state}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
