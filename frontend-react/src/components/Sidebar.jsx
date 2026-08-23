export default function Sidebar({ items, active, onSelect, user, onSignOut }) {
  const groups = items.reduce((result, item) => {
    const group = item.group || "Command Center";
    if (!result[group]) result[group] = [];
    result[group].push(item);
    return result;
  }, {});

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="sidebar-brand-mark">V</span>
        <div><strong>Command Center</strong><small>Vera operations</small></div>
      </div>
      <nav className="sidebar-nav" aria-label="Command Center navigation">
        {Object.entries(groups).map(([group, groupItems]) => (
          <section className="sidebar-group" key={group}>
            <h2>{group}</h2>
            <ul>
              {groupItems.map((item) => (
                <li key={item.id}>
                  <button type="button" aria-current={active === item.id ? "page" : undefined}
                    className={active === item.id ? "sidebar-link active" : "sidebar-link"}
                    onClick={() => onSelect(item.id)}>{item.label}</button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </nav>
      <div className="sidebar-account">
        <div><span>{user?.username?.slice(0, 1).toUpperCase()}</span><p><strong>{user?.username}</strong><small>Owner</small></p></div>
        <button type="button" onClick={onSignOut}>Sign out</button>
      </div>
    </aside>
  );
}
