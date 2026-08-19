import { useState } from "react";
import { login } from "../../services/api";


export default function LoginPage({ onAuthenticated }) {
  const [username, setUsername] = useState("bruce");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const result = await login(username, password);
      setPassword("");
      onAuthenticated(result.user);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(detail || "Unable to sign in.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <div>
          <p className="login-eyebrow">Command Center</p>
          <h1>Welcome back</h1>
          <p className="page-subtitle">Sign in to continue to Vera and your home operations.</p>
        </div>

        <label>
          Username
          <input
            name="username"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
          />
        </label>

        <label>
          Password
          <input
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>

        {error && <p className="login-error" role="alert">{error}</p>}

        <button type="submit" disabled={loading}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
