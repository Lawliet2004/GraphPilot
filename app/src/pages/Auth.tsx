import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  Eye,
  EyeOff,
  GitBranch,
  LoaderCircle,
  Network,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError, post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Brand, ErrorNotice } from "../components/ui";

type FieldErrors = Partial<Record<"name" | "email" | "password", string>>;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [message, setMessage] = useState("");
  if (auth.user && !reset) return <Navigate to={next} replace />;
  const showEmail = !reset || !token;
  const showPasswordField = !reset || !!token;
  const newPassword = signup || reset;
  const title = reset
    ? "Reset password"
    : signup
      ? "Create account"
      : "Log in";
  const busyLabel = reset
    ? "Sending…"
    : signup
      ? "Creating account…"
      : "Logging in…";
  const buttonLabel = reset
    ? "Reset password"
    : signup
      ? "Create account"
      : "Log in";
  function validate() {
    const errors: FieldErrors = {};
    if (signup && !name.trim()) errors.name = "Enter your name.";
    if (showEmail && !EMAIL.test(email.trim()))
      errors.email = "Enter a valid email address.";
    if (showPasswordField) {
      if (newPassword && password.length < 12)
        errors.password = "Use at least 12 characters.";
      else if (!newPassword && !password)
        errors.password = "Enter your password.";
    }
    return errors;
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;
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
        const result = await post<{ verification_email_sent?: boolean }>(
          signup ? "/auth/register" : "/auth/login",
          signup ? { email, name, password } : { email, password },
        );
        await auth.refresh();
        navigate(next, {
          replace: true,
          state: signup
            ? { verificationEmailSent: result.verification_email_sent ?? null }
            : undefined,
        });
      }
    } catch (e) {
      setError(
        !signup && !reset && e instanceof ApiError && e.status === 409
          ? new Error(
              "This account has not been linked to Firebase sign-in yet. Ask an administrator to link your account, then log in again.",
            )
          : e,
      );
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
          <h1>{title}</h1>
          <p className="auth-lede">
            {reset
              ? token
                ? "Choose a new password for your account."
                : provider.data?.provider === "firebase"
                  ? "Firebase will email a one-time link to reset your password."
                  : "We’ll send a one-time link when email delivery is configured."
              : signup
                ? "Create your GraphPilot workspace."
                : "Welcome back. Pick up where you left off."}
          </p>
          {error !== undefined && <ErrorNotice error={error} />}
          {message ? (
            <div className="notice" role="status">
              {message}
              <Link to="/login">
                Go to login <ArrowRight size={16} />
              </Link>
            </div>
          ) : (
            <form onSubmit={submit} noValidate>
              {signup && (
                <div className="field">
                  <label htmlFor="auth-name">Your name</label>
                  <input
                    id="auth-name"
                    autoComplete="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    maxLength={80}
                    aria-invalid={!!fieldErrors.name}
                    aria-describedby={fieldErrors.name ? "auth-name-error" : undefined}
                  />
                  {fieldErrors.name && (
                    <p className="field-error" id="auth-name-error">
                      {fieldErrors.name}
                    </p>
                  )}
                </div>
              )}
              {showEmail && (
                <div className="field">
                  <label htmlFor="auth-email">Email address</label>
                  <input
                    id="auth-email"
                    type="email"
                    autoComplete="email"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    maxLength={254}
                    aria-invalid={!!fieldErrors.email}
                    aria-describedby={fieldErrors.email ? "auth-email-error" : undefined}
                  />
                  {fieldErrors.email && (
                    <p className="field-error" id="auth-email-error">
                      {fieldErrors.email}
                    </p>
                  )}
                </div>
              )}
              {showPasswordField && (
                <div className="field">
                  <div className="field-row">
                    <label htmlFor="auth-password">Password</label>
                    {!signup && !reset && (
                      <Link className="forgot-link" to="/reset-password">
                        Forgot password?
                      </Link>
                    )}
                  </div>
                  <div className="password-field">
                    <input
                      id="auth-password"
                      type={showPassword ? "text" : "password"}
                      autoComplete={newPassword ? "new-password" : "current-password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      maxLength={128}
                      aria-invalid={!!fieldErrors.password}
                      aria-describedby={
                        fieldErrors.password
                          ? "auth-password-error"
                          : newPassword
                            ? "auth-password-hint"
                            : undefined
                      }
                    />
                    <button
                      type="button"
                      className="password-toggle"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      aria-pressed={showPassword}
                      onClick={() => setShowPassword((shown) => !shown)}
                    >
                      {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                    </button>
                  </div>
                  {fieldErrors.password ? (
                    <p className="field-error" id="auth-password-error">
                      {fieldErrors.password}
                    </p>
                  ) : (
                    newPassword && (
                      <p className="field-hint" id="auth-password-hint">
                        Use at least 12 characters.
                      </p>
                    )
                  )}
                </div>
              )}
              <button
                className="button primary wide"
                disabled={busy}
                aria-busy={busy}
              >
                {busy ? (
                  <LoaderCircle className="spin" size={17} />
                ) : null}
                {busy ? busyLabel : buttonLabel}
                {!busy && <ArrowRight size={17} />}
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
