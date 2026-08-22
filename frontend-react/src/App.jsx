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
import { getCurrentUser, logout } from "./services/api";
import VeraControl from "./components/VeraControl";

const navItems = [
  { id: "dashboard", label: "Dashboard" },
  { id: "advisor", label: "Advisor" },
  { id: "journal", label: "Decision Journal" },
  { id: "home", label: "Home" },
  { id: "monitoring", label: "Monitoring" },
  { id: "gmail", label: "Gmail" },
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
  journal: JournalPage,
  home: HomePage,
  monitoring: MonitoringPage,
  gmail: GmailPage,
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
      <Sidebar items={navItems} active={activePage} onSelect={setActivePage} />
      <main className="main-content">
        <VeraControl />
        <div className="session-bar">
          <span>Signed in as {user.username}</span>
          <button type="button" className="secondary-button" onClick={signOut}>Sign out</button>
        </div>
        <ActivePage />
      </main>
    </div>
  );
}

export default App;
