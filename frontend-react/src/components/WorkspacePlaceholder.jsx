export default function WorkspacePlaceholder({ title, subtitle, description }) {
  return (
    <div className="page-content">
      <header className="page-header">
        <div><h1>{title}</h1><p className="page-subtitle">{subtitle}</p></div>
        <span className="workspace-status">Planned</span>
      </header>
      <section className="workspace-empty-state">
        <span aria-hidden="true">◆</span>
        <div><h2>Workspace foundation ready</h2><p>{description}</p></div>
      </section>
    </div>
  );
}
