import Panel from "./Panel";

export default function ProjectPanel({ projects }) {
  return (
    <Panel title="Projects">
      <div className="list">
        {projects.map((p) => (
          <div className="row" key={p.name}>
            <strong>{p.name}</strong>
            <span>{p.type} | {p.priority} | {p.status}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}
