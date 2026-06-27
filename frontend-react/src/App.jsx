import { useState } from "react";
import "./App.css";
import Sidebar from "./components/Sidebar";
import DashboardPage from "./pages/Dashboard";
import ProjectsPage from "./pages/Projects";
import InfrastructurePage from "./pages/Infrastructure";
import AdvisorPage from "./pages/Advisor";
import MinecraftPage from "./pages/Minecraft";
import PlexPage from "./pages/Plex";
import SecurityPage from "./pages/Security";
import DevelopmentPage from "./pages/Development";
import AutomationPage from "./pages/Automation";
import SettingsPage from "./pages/Settings";

const navItems = [
  { id: "dashboard", label: "Dashboard" },
  { id: "advisor", label: "Advisor" },
  { id: "projects", label: "Projects" },
  { id: "infrastructure", label: "Infrastructure" },
  { id: "minecraft", label: "Minecraft" },
  { id: "plex", label: "Plex" },
  { id: "security", label: "Security" },
  { id: "development", label: "Development" },
  { id: "automation", label: "Automation" },
  { id: "settings", label: "Settings" },
];

const pageMap = {
  dashboard: DashboardPage,
  advisor: AdvisorPage,
  projects: ProjectsPage,
  infrastructure: InfrastructurePage,
  minecraft: MinecraftPage,
  plex: PlexPage,
  security: SecurityPage,
  development: DevelopmentPage,
  automation: AutomationPage,
  settings: SettingsPage,
};

function App() {
  const [activePage, setActivePage] = useState("dashboard");
  const ActivePage = pageMap[activePage] ?? DashboardPage;

  return (
    <div className="app-shell">
      <Sidebar items={navItems} active={activePage} onSelect={setActivePage} />
      <main className="main-content">
        <ActivePage />
      </main>
    </div>
  );
}

export default App;
