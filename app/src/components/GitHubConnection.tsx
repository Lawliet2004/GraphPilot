import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitFork, ArrowRight, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api, post, type Repo } from "../lib/api";
import { useAuth } from "../lib/auth";
import { ErrorNotice, Loading } from "./ui";

type Choice = {
  id: number;
  full_name: string;
  private: boolean;
  default_branch: string;
};

export function GitHubConnection() {
  const { user } = useAuth();
  const cache = useQueryClient();
  const navigate = useNavigate();
  const [installation, setInstallation] = useState(0);
  const [repository, setRepository] = useState(0);
  const [branch, setBranch] = useState("main");
  const [page, setPage] = useState(1);
  const status = useQuery({
    queryKey: ["github-connection", user?.id],
    queryFn: () =>
      api<{
        configured: boolean;
        connected: boolean;
        login: string | null;
        install_url: string | null;
      }>("/integrations/github"),
  });
  const installations = useQuery({
    queryKey: ["github-installations", user?.id],
    queryFn: () =>
      api<{ id: number; account: string }[]>(
        "/integrations/github/installations",
      ),
    enabled: !!status.data?.connected,
  });
  const selectedInstallation = installation || installations.data?.[0]?.id || 0;
  const choices = useQuery({
    queryKey: ["github-repositories", user?.id, selectedInstallation, page],
    queryFn: () =>
      api<{ repositories: Choice[]; has_more: boolean }>(
        `/integrations/github/installations/${selectedInstallation}/repositories?page=${page}`,
      ),
    enabled: !!status.data?.connected && !!selectedInstallation,
  });
  const authorize = useMutation({
    mutationFn: async () => {
      const result = await post<{ url: string }>(
        "/integrations/github/authorize",
      );
      const destination = new URL(result.url);
      if (
        destination.origin !== "https://github.com" ||
        destination.pathname !== "/login/oauth/authorize"
      )
        throw new Error("GitHub returned an unexpected authorization address.");
      location.assign(destination.href);
    },
  });
  const disconnect = useMutation({
    mutationFn: () => api("/integrations/github", { method: "DELETE" }),
    onSuccess: () =>
      cache.invalidateQueries({ queryKey: ["github-connection", user?.id] }),
  });
  const connect = useMutation({
    mutationFn: () =>
      post<{ repository: Repo }>("/integrations/github/repositories", {
        installation_id: selectedInstallation,
        repository_id: repository,
        branch,
      }),
    onSuccess: async (result) => {
      await cache.invalidateQueries({ queryKey: ["repositories"] });
      navigate(`/repositories/${result.repository.id}`);
    },
  });
  return (
    <section className="github-connection" aria-labelledby="github-title">
      <div className="github-account-heading">
        <div>
          <h2 id="github-title">
            <GitFork size={21} aria-hidden="true" /> Connect your GitHub account
          </h2>
          <p>Choose the public and private repositories GraphPilot can read.</p>
        </div>
        {status.data?.configured && !status.data.connected && (
          <button
            className="button primary"
            disabled={authorize.isPending}
            onClick={() => authorize.mutate()}
          >
            {authorize.isPending ? "Opening GitHub…" : "Continue with GitHub"}
            <ArrowRight size={16} />
          </button>
        )}
      </div>
      {status.isPending && <Loading />}
      {[
        status.error,
        installations.error,
        choices.error,
        authorize.error,
        disconnect.error,
        connect.error,
      ]
        .filter(Boolean)
        .map((error, i) => (
          <ErrorNotice key={i} error={error} />
        ))}
      {status.data && !status.data.configured && (
        <p className="notice subtle">
          GitHub account connection is not available yet. You can add a public
          repository URL or upload a ZIP below.
        </p>
      )}
      {status.data?.connected && (
        <>
          <div className="github-account-actions">
            <p>
              Connected as <strong>{status.data.login}</strong>
            </p>
            <button
              className="button"
              onClick={() => authorize.mutate()}
              disabled={authorize.isPending}
            >
              Reconnect
            </button>
            <button
              className="button"
              onClick={() => disconnect.mutate()}
              disabled={disconnect.isPending}
            >
              {disconnect.isPending ? "Disconnecting…" : "Disconnect"}
            </button>
            {status.data.install_url && (
              <a
                className="button"
                href={status.data.install_url}
                target="_blank"
                rel="noreferrer"
              >
                Choose repositories in GitHub
                <ExternalLink size={15} />
              </a>
            )}
          </div>
          {installations.isPending ? (
            <Loading />
          ) : !installations.error && !installations.data?.length ? (
            <p className="notice">
              Install the GraphPilot GitHub App on your account, select
              repositories, then{" "}
              <button
                className="text-button"
                onClick={() => void installations.refetch()}
              >
                refresh your connections
              </button>
              .
            </p>
          ) : (
            <form
              className="github-picker"
              onSubmit={(e) => {
                e.preventDefault();
                connect.mutate();
              }}
            >
              <label>
                GitHub account
                <select
                  value={selectedInstallation}
                  onChange={(e) => {
                    setInstallation(Number(e.target.value));
                    setPage(1);
                    setRepository(0);
                  }}
                >
                  {installations.data?.map((i) => (
                    <option value={i.id} key={i.id}>
                      {i.account}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Authorized repository
                <select
                  value={repository || ""}
                  required
                  onChange={(e) => {
                    const value = Number(e.target.value);
                    setRepository(value);
                    setBranch(
                      choices.data?.repositories.find((r) => r.id === value)
                        ?.default_branch || "main",
                    );
                  }}
                >
                  <option value="">
                    {choices.isPending
                      ? "Loading repositories…"
                      : "Choose a repository"}
                  </option>
                  {choices.data?.repositories.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.full_name}
                      {r.private ? " · Private" : " · Public"}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Branch
                <input
                  value={branch}
                  onChange={(e) => setBranch(e.target.value)}
                  required
                  maxLength={200}
                />
              </label>
              <button
                className="button primary"
                disabled={!repository || connect.isPending}
              >
                {connect.isPending
                  ? "Connecting…"
                  : "Connect selected repository"}
                <ArrowRight size={16} />
              </button>
              {(page > 1 || choices.data?.has_more) && (
                <div className="github-account-actions">
                  <button
                    type="button"
                    className="button"
                    disabled={page === 1 || choices.isFetching}
                    onClick={() => {
                      setPage((p) => p - 1);
                      setRepository(0);
                    }}
                  >
                    Previous
                  </button>
                  <span>Page {page}</span>
                  <button
                    type="button"
                    className="button"
                    disabled={!choices.data?.has_more || choices.isFetching}
                    onClick={() => {
                      setPage((p) => p + 1);
                      setRepository(0);
                    }}
                  >
                    Next
                  </button>
                </div>
              )}
              {choices.data?.repositories.length === 0 && (
                <p>
                  No repositories are available. Check your selection in GitHub,
                  then refresh.
                </p>
              )}
            </form>
          )}
        </>
      )}
    </section>
  );
}
