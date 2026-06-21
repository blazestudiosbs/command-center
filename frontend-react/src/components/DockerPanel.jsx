import Panel from "./Panel";

export default function DockerPanel({ docker }) {
  return (
    <Panel title="Docker">
      <div className="list">
        {docker.containers.map((c) => (
          <div className="row" key={c.name}>
            <strong>{c.name}</strong>
            <span>{c.status} | {c.image}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
