import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, GitBranch, Network } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api, post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Brand, ErrorNotice } from "../components/ui";
export function Auth({
  signup = false,
  reset = false,
}: {
  signup?: boolean;
  reset?: boolean;
}) {
  const auth = useAuth();
  const provider = useQuery({
    queryKey: ["auth-config"],
    queryFn: () => api<{ provider: "local" | "firebase" }>("/auth/config"),
    staleTime: 60000,
    retry: false,
  });
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token");
  const requestedNext = params.get("next") || "";
  const next = /^\/cli\/authorize\?code=[A-Fa-f0-9-]{8,9}$/.test(requestedNext)
    ? requestedNext
    : "/workspace";
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [message, setMessage] = useState("");
  if (auth.user && !reset) return <Navigate to={next} replace />;
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      if (reset) {
        const result = await post<{ message: string }>(
          token ? "/auth/password-reset/confirm" : "/auth/password-reset",
          token ? { token, password } : { email },
        );
        setMessage(result.message);
      } else {
        await post(
          signup ? "/auth/register" : "/auth/login",
          signup ? { email, name, password } : { email, password },
        );
        await auth.refresh();
        navigate(next, { replace: true });
      }
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-layout">
      <aside className="auth-story">
        <Brand />
        <div>
          <Network size={44} strokeWidth={1} />
          <h2>
            Get the whole
            <br />
            picture of your code.
          </h2>
          <p>
            From a single function to the connections that matter. Explore your
            repository with the evidence in reach.
          </p>
          <div className="auth-trace">
            <span>Source</span>
            <i />
            <span>Graph</span>
            <i />
            <span>Context</span>
          </div>
        </div>
        <span className="auth-foot">
          <GitBranch size={15} /> Built around your repository.
        </span>
      </aside>
      <main className="auth-form-wrap">
        <div className="auth-form">
          <Link className="back-link" to="/">
            Back to GraphPilot
          </Link>
          <h1>
            {reset
              ? "Reset your password"
              : signup
                ? "Make room for clarity."
                : "Good to see you."}
          </h1>
          <p>
            {reset
              ? token
                ? "Choose a new password for your account."
                : provider.data?.provider === "firebase"
                  ? "Firebase will email a one-time link to reset your password."
                  : "We’ll send a one-time link when email delivery is configured."
              : signup
                ? "Create your GraphPilot workspace."
                : "Log in to pick up the thread."}
          </p>
          {error !== undefined && <ErrorNotice error={error} />}{" "}
          {message ? (
            <div className="notice">
              {message}
              <Link to="/login">
                Go to login <ArrowRight size={16} />
              </Link>
            </div>
          ) : (
            <form onSubmit={submit}>
              {signup && (
                <label>
                  Your name
                  <input
                    autoComplete="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    maxLength={80}
                  />
                </label>
              )}
              {(!reset || !token) && (
                <label>
                  Email address
                  <input
                    type="email"
                    autoComplete="email"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    maxLength={254}
                  />
                </label>
              )}
              {(!reset || token) && (
                <label>
                  Password
                  <input
                    aria-label="Password"
                    type="password"
                    autoComplete={
                      signup || reset ? "new-password" : "current-password"
                    }
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={signup || reset ? 12 : 1}
                    maxLength={128}
                  />
                  {(signup || reset) && (
                    <small>Use at least 12 characters.</small>
                  )}
                </label>
              )}
              {!signup && !reset && (
                <Link className="forgot-link" to="/reset-password">
                  Forgot password?
                </Link>
              )}
              <button className="button primary wide" disabled={busy}>
                {busy
                  ? "Working…"
                  : reset
                    ? "Reset password"
                    : signup
                      ? "Create workspace"
                      : "Log in"}
                <ArrowRight size={17} />
              </button>
            </form>
          )}
          {!reset && (
            <p className="auth-switch">
              {signup ? "Already have a workspace?" : "New to GraphPilot?"}{" "}
              <Link
                to={
                  (signup ? "/login" : "/signup") +
                  (next === "/workspace"
                    ? ""
                    : "?next=" + encodeURIComponent(next))
                }
              >
                {signup ? "Log in" : "Create an account"}
              </Link>
            </p>
          )}
          <p className="auth-privacy">
            {provider.data?.provider === "firebase" && (
              <>
                New accounts use Firebase Authentication.
                <br />
              </>
            )}
            Your source stays behind repository permissions.
            <br />A model connection is optional.
          </p>
        </div>
      </main>
    </div>
  );
}
