import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, KeyRound } from "lucide-react";
import { useEffect, useState } from "react";
import { api, date, type ModelCredentialStatus } from "../lib/api";
import { ErrorNotice, Loading } from "./ui";

const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  openrouter: "OpenRouter",
};

export function ModelCredentials() {
  const cache = useQueryClient();
  const status = useQuery({
    queryKey: ["model-credential"],
    queryFn: () => api<ModelCredentialStatus>("/model"),
  });
  const [provider, setProvider] = useState<"openai" | "openrouter">(
    "openrouter",
  );
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);

  // The key only ever lives in this component's memory: clear it when the
  // form unmounts on navigation. It is never put in browser storage.
  useEffect(() => () => setApiKey(""), []);

  const saved = useMutation({
    mutationFn: () =>
      api<ModelCredentialStatus>("/model", {
        method: "PUT",
        body: JSON.stringify({
          provider,
          model: model.trim(),
          api_key: apiKey,
        }),
      }),
    onSuccess: async () => {
      setApiKey("");
      setModel("");
      setEditing(false);
      await cache.invalidateQueries({ queryKey: ["model-credential"] });
      await cache.invalidateQueries({ queryKey: ["capabilities"] });
    },
    onSettled: () => setApiKey(""),
  });
  const removed = useMutation({
    mutationFn: () => api<{ message: string }>("/model", { method: "DELETE" }),
    onSuccess: async () => {
      setApiKey("");
      setModel("");
      setEditing(false);
      setConfirming(false);
      await cache.invalidateQueries({ queryKey: ["model-credential"] });
      await cache.invalidateQueries({ queryKey: ["capabilities"] });
    },
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (apiKey.trim() && model.trim()) saved.mutate();
  }

  const row = status.data;
  const configured = !!row?.configured && !editing;
  return (
    <section className="model-credentials">
      <h2>AI synthesis with your own key</h2>
      <p className="muted">
        Graph search, evidence and citations work without any model. To get a
        written answer you can add your own provider key: your provider bills
        your account, and bounded repository excerpts are sent to that provider
        over HTTPS only when you ask a question.
      </p>
      {status.isPending ? (
        <Loading />
      ) : status.error ? (
        <ErrorNotice error={status.error} />
      ) : !row?.byok_available ? (
        <p className="notice subtle">
          An administrator must enable encrypted key storage before you can add
          a key. Graph search remains available.
        </p>
      ) : (
        <>
          {configured ? (
            <div>
              <dl className="definition-list">
                <div>
                  <dt>Provider</dt>
                  <dd>
                    {PROVIDER_LABELS[row?.provider ?? ""] ??
                      row?.provider ??
                      "—"}
                  </dd>
                </div>
                <div>
                  <dt>Model</dt>
                  <dd>{row?.model}</dd>
                </div>
                <div>
                  <dt>Key updated</dt>
                  <dd>{date(row?.updated_at)}</dd>
                </div>
              </dl>
              {saved.isSuccess && (
                <p role="status">
                  <Check size={14} /> Credentials saved.
                </p>
              )}
              {removed.error && <ErrorNotice error={removed.error} />}
              <div className="github-account-actions">
                <button
                  type="button"
                  className="button"
                  onClick={() => {
                    setEditing(true);
                    saved.reset();
                    removed.reset();
                  }}
                >
                  Replace credentials
                </button>
                {confirming ? (
                  <>
                    <button
                      type="button"
                      className="button"
                      disabled={removed.isPending}
                      onClick={() => removed.mutate()}
                    >
                      {removed.isPending ? "Removing…" : "Confirm removal"}
                    </button>
                    <button
                      type="button"
                      className="text-button"
                      disabled={removed.isPending}
                      onClick={() => setConfirming(false)}
                    >
                      Keep key
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => setConfirming(true)}
                  >
                    Remove key
                  </button>
                )}
              </div>
            </div>
          ) : (
            <form onSubmit={submit}>
              {!row?.configured &&
                (removed.isSuccess ? (
                  <p role="status">{removed.data?.message}</p>
                ) : (
                  <p className="notice subtle">
                    <KeyRound size={16} />
                    No key saved yet — answers stay graph-only until you add
                    one.
                  </p>
                ))}
              <label>
                Provider
                <select
                  value={provider}
                  onChange={(e) =>
                    setProvider(e.target.value as "openai" | "openrouter")
                  }
                >
                  <option value="openrouter">OpenRouter</option>
                  <option value="openai">OpenAI</option>
                </select>
              </label>
              <label>
                <span id="byok-model-label">Model</span>
                <input
                  aria-labelledby="byok-model-label"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder={
                    provider === "openrouter"
                      ? "openrouter/free"
                      : "Your model ID"
                  }
                  required
                  minLength={1}
                  maxLength={120}
                  aria-describedby="model-hint"
                />
                <small id="model-hint">
                  Use a Chat Completions model supported by your provider.
                </small>
              </label>
              <label>
                <span id="byok-key-label">API key</span>
                <input
                  aria-labelledby="byok-key-label"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  required
                  minLength={10}
                  maxLength={256}
                  autoComplete="new-password"
                  aria-describedby="key-hint"
                />
                <small id="key-hint">
                  Stored encrypted, never shown again and never kept in browser
                  storage.
                </small>
              </label>
              {saved.error && <ErrorNotice error={saved.error} />}
              <div className="github-account-actions">
                <button
                  className="button primary"
                  disabled={saved.isPending || !apiKey.trim() || !model.trim()}
                >
                  {saved.isPending ? "Saving…" : "Save credentials"}
                </button>
                {editing && (
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => {
                      setEditing(false);
                      setApiKey("");
                      saved.reset();
                    }}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </form>
          )}
          <p className="small muted">
            Your key is stored encrypted for your account. You can replace or
            remove it at any time. Saving a key does not test it or contact the
            model provider.
          </p>
        </>
      )}
    </section>
  );
}
