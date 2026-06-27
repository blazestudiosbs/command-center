export default function Sidebar({ items, active, onSelect }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <strong>Command Center</strong>
      </div>
      <nav className="sidebar-nav">
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className={active === item.id ? "sidebar-link active" : "sidebar-link"}
                onClick={() => onSelect(item.id)}
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}
