import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Monitor, Moon, Sun } from "lucide-react";
import { useState } from "react";
import { api, post, date, type Capabilities } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ErrorNotice, Heading, Loading } from "../components/ui";
import { CliCredentials } from "./CliAccess";
export function Settings() {
  const { user, refresh, provider, emailVerified } = useAuth();
  const cache = useQueryClient();
  const [name, setName] = useState(user?.name || "");
  const [theme, setTheme] = useState(user?.theme || "system");
  const [saved, setSaved] = useState(false);
  const sessions = useQuery({
    queryKey: ["sessions"],
    queryFn: () =>
      api<
        {
          id: string;
          created_at: string;
          expires_at: string;
          agent: string;
          current: boolean;
        }[]
      >("/auth/sessions"),
  });
  const caps = useQuery({
    queryKey: ["capabilities"],
    queryFn: () => api<Capabilities>("/capabilities"),
  });
  const update = useMutation({
    mutationFn: () =>
      api("/auth/profile", {
        method: "PATCH",
        body: JSON.stringify({ name, theme }),
      }),
    onSuccess: async () => {
      localStorage.setItem("gp-theme", theme);
      await refresh();
      setSaved(true);
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) =>
      api("/auth/sessions/" + id, { method: "DELETE" }),
    onSuccess: () => void cache.invalidateQueries({ queryKey: ["sessions"] }),
  });
  const verification = useMutation({
    mutationFn: () => post<{ message: string }>("/auth/email-verification"),
  });
  return (
    <div className="page settings-page">
      <Heading
        title="Make yourself at home."
        description="Your profile, appearance and active sessions."
      />
      <div className="settings-layout">
        <section>
          <h2>Profile & appearance</h2>
          {update.error && <ErrorNotice error={update.error} />}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              update.mutate();
            }}
          >
            <label>
              Name
              <input
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setSaved(false);
                }}
                required
                maxLength={80}
              />
            </label>
            {provider === "firebase" && (
              <div className="notice subtle">
                <p>
                  {emailVerified
                    ? "Your email is verified with Firebase."
                    : "Your email has not been verified yet."}
                </p>
                {!emailVerified && (
                  <>
                    {verification.error && (
                      <ErrorNotice error={verification.error} />
                    )}
                    {verification.data && (
                      <p role="status">{verification.data.message}</p>
                    )}
                    <button
                      type="button"
                      className="button"
                      disabled={verification.isPending}
                      onClick={() => verification.mutate()}
                    >
                      {verification.isPending
                        ? "Sending…"
                        : "Send verification email"}
                    </button>
                    <button
                      type="button"
                      className="button"
                      onClick={() => void refresh()}
                    >
                      Check verification
                    </button>
                  </>
                )}
              </div>
            )}
            <label>
              Email address
              <input value={user?.email || ""} disabled />
              <small>Email changes are not currently available.</small>
            </label>
            <fieldset className="theme-options">
              <legend>Appearance</legend>
              {(["light", "dark", "system"] as const).map((t) => (
                <label key={t} className={theme === t ? "active" : ""}>
                  <input
                    type="radio"
                    name="theme"
                    value={t}
                    checked={theme === t}
                    onChange={() => {
                      setTheme(t);
                      setSaved(false);
                    }}
                  />
                  {t === "light" ? (
                    <Sun size={19} />
                  ) : t === "dark" ? (
                    <Moon size={19} />
                  ) : (
                    <Monitor size={19} />
                  )}
                  <span>{t}</span>
                </label>
              ))}
            </fieldset>
            <button className="button primary" disabled={update.isPending}>
              {saved ? (
                <>
                  <Check size={16} />
                  Saved
                </>
              ) : update.isPending ? (
                "Saving…"
              ) : (
                "Save preferences"
              )}
            </button>
          </form>
          <CliCredentials />
          <h2>Connected services</h2>
          {caps.isPending ? (
            <Loading />
          ) : caps.error ? (
            <ErrorNotice error={caps.error} />
          ) : (
            <dl className="definition-list">
              <div>
                <dt>AI synthesis</dt>
                <dd>
                  {caps.data?.llm_configured
                    ? "Configured on server"
                    : "Not configured · graph search is available"}
                </dd>
              </div>
              <div>
                <dt>GitHub API</dt>
                <dd>
                  {caps.data?.github_authenticated
                    ? "Server credential configured"
                    : "Public access without a token"}
                </dd>
              </div>
              <div>
                <dt>Password reset email</dt>
                <dd>
                  {caps.data?.password_reset_email
                    ? "Configured on server"
                    : "Not configured"}
                </dd>
              </div>
            </dl>
          )}
          <p className="small muted">
            Provider connections are managed through server configuration.
            Secrets are never sent to your browser.
          </p>
        </section>
        <section>
          <h2>Active sessions</h2>
          <p className="muted">Revoke sessions you no longer recognize.</p>
          {revoke.error && <ErrorNotice error={revoke.error} />}{" "}
          {sessions.isPending ? (
            <Loading />
          ) : sessions.error ? (
            <ErrorNotice error={sessions.error} />
          ) : (
            sessions.data?.map((s) => (
              <div className="session-row" key={s.id}>
                <Monitor size={20} />
                <div>
                  <strong>
                    {s.current ? "This browser" : "Browser session"}
                  </strong>
                  <p>{s.agent.slice(0, 100)}</p>
                  <small>
                    Opened {date(s.created_at)} · Expires {date(s.expires_at)}
                  </small>
                </div>
                {!s.current && (
                  <button
                    className="text-button"
                    disabled={revoke.isPending}
                    onClick={() => revoke.mutate(s.id)}
                  >
                    Revoke
                  </button>
                )}
              </div>
            ))
          )}
        </section>
      </div>
    </div>
  );
}
