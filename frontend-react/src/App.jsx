import { useEffect, useState } from "react";
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
import LoginPage from "./pages/Login";
import JournalPage from "./pages/Journal";
import HomePage from "./pages/Home";
import MonitoringPage from "./pages/Monitoring";
import GmailPage from "./pages/Gmail";
import AgentsPage from "./pages/Agents";
import CalendarPage from "./pages/Calendar";
import ReleasesPage from "./pages/Releases";
import { getCurrentUser, logout } from "./services/api";
import VeraControl from "./components/VeraControl";

const navItems = [
  { id: "dashboard", label: "Dashboard", group: "Overview" },
  { id: "advisor", label: "Advisor", group: "Overview" },
  { id: "journal", label: "Decision Journal", group: "Overview" },
  { id: "home", label: "Home", group: "Connected services" },
  { id: "gmail", label: "Gmail", group: "Connected services" },
  { id: "calendar", label: "Calendar", group: "Connected services" },
  { id: "minecraft", label: "Minecraft", group: "Connected services" },
  { id: "plex", label: "Plex", group: "Connected services" },
  { id: "monitoring", label: "Monitoring", group: "Operations" },
  { id: "agents", label: "Agent Permissions", group: "Operations" },
  { id: "security", label: "Security", group: "Operations" },
  { id: "development", label: "Development", group: "Operations" },
  { id: "releases", label: "Releases", group: "Operations" },
  { id: "projects", label: "Projects", group: "Workspace" },
  { id: "infrastructure", label: "Infrastructure", group: "Workspace" },
  { id: "automation", label: "Automation", group: "Workspace" },
  { id: "settings", label: "Settings", group: "Workspace" },
];

const pageMap = {
  dashboard: DashboardPage,
  advisor: AdvisorPage,
  journal: JournalPage,
  home: HomePage,
  monitoring: MonitoringPage,
  gmail: GmailPage,
  calendar: CalendarPage,
  agents: AgentsPage,
  projects: ProjectsPage,
  infrastructure: InfrastructurePage,
  minecraft: MinecraftPage,
  plex: PlexPage,
  security: SecurityPage,
  development: DevelopmentPage,
  releases: ReleasesPage,
  automation: AutomationPage,
  settings: SettingsPage,
};

function App() {
  const [activePage, setActivePage] = useState("dashboard");
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const ActivePage = pageMap[activePage] ?? DashboardPage;

  useEffect(() => {
    getCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setAuthLoading(false));
  }, []);

  async function signOut() {
    try {
      await logout();
    } finally {
      setUser(null);
    }
  }

  if (authLoading) {
    return <main className="login-shell"><p>Checking session…</p></main>;
  }

  if (!user) {
    return <LoginPage onAuthenticated={setUser} />;
  }

  return (
    <div className="app-shell">
      <Sidebar items={navItems} active={activePage} onSelect={setActivePage} user={user} onSignOut={signOut} />
      <main className="main-content">
        <VeraControl />
        <ActivePage />
      </main>
    </div>
  );
}

export default App;
