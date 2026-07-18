import {
  createContext,
  FormEvent,
  useCallback,
  useContext,
  useMemo,
  useEffect,
  useState,
} from "react";
import { apiRequest } from "./api";

type Principal = {
  actor: string;
  scopes: string[];
  project_id: string | null;
};

type AuthContextValue = {
  principal: Principal;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const auth = useContext(AuthContext);
  if (!auth) {
    throw new Error("useAuth must be used within an AuthGate provider");
  }
  return auth;
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [loading, setLoading] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const authContext = useMemo<AuthContextValue>(
    () => ({ principal: principal!, logout }),
    [principal, logout],
  );

  const loadPrincipal = useCallback(async () => {
    try {
      setPrincipal(await apiRequest<Principal>("/auth/me"));
    } catch {
      setPrincipal(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPrincipal();
    const requireAuth = () => setPrincipal(null);
    window.addEventListener("ontology-auth-required", requireAuth);
    return () => window.removeEventListener("ontology-auth-required", requireAuth);
  }, [loadPrincipal]);

  async function login(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const authenticated = await apiRequest<Principal>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setPassword("");
      setPrincipal(authenticated);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  }

  async function logout() {
    try {
      await apiRequest<void>("/auth/logout", { method: "POST" });
    } finally {
      setPrincipal(null);
    }
  }

  if (loading) return <div className="auth-loading">Checking authentication…</div>;
  if (!principal) {
    return (
      <main className="auth-page">
        <form className="auth-card" onSubmit={login}>
          <div className="auth-eyebrow">Ontology Platform</div>
          <h1>Sign in</h1>
          <p>Use the bootstrap administrator account configured for this deployment.</p>
          <label>
            Username
            <input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label>
            Password
            <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          {error ? <div className="auth-error" role="alert">Authentication failed.</div> : null}
          <button type="submit">Sign in</button>
        </form>
      </main>
    );
  }

  return (
    <AuthContext.Provider value={authContext}>
      {children}
    </AuthContext.Provider>
  );
}
