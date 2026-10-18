import {
  ArrowUpRight,
  FolderGit2,
  LogOut,
  Menu,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Terminal,
  Activity,
  X,
} from "lucide-react";
import {
  NavLink,
  Outlet,
  Link,
  Navigate,
  useLocation,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { api, scoped, type Repo } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Brand, ErrorNotice, Loading } from "./ui";
import { CommandPalette } from "./CommandPalette";

export function Protected() {
  const { user, loading, error, refresh } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (error) return <ErrorNotice error={error} retry={() => void refresh()} />;
  return user ? (
    <Outlet />
  ) : (
    <Navigate to="/login" replace state={{ from: location.pathname }} />
  );
}

const CRUMBS: Record<string, string> = {
  "/workspace": "Repositories",
  "/connect": "Add repository",
  "/tools": "CLI & MCP",
  "/activity": "Jobs & activity",
  "/settings": "Settings",
  "/admin": "Administration",
};

function RepositoryCrumb() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const branch = params.get("branch");
  const revision = params.get("revision");
  const repo = useQuery({
    queryKey: ["repository", id, branch, revision],
    queryFn: () =>
      api<Repo>(scoped(`/repositories/${id}`, { branch, revision })),
    retry: false,
  });
  return <span className="crumb-current">{repo.data?.name ?? "Repository"}</span>;
}

export function Shell() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const inRepository = pathname.startsWith("/repositories/");
  const crumb = inRepository ? null : (CRUMBS[pathname] ?? "Workspace");
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [pathname]);
  const [palette, setPalette] = useState(false);
  const closePalette = useCallback(() => setPalette(false), []);
  const shortcut = /Mac|iPhone|iPad|iPod/.test(navigator.userAgent)
    ? "⌘K"
    : "Ctrl K";
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <div className="app-shell">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <button
        className="mobile-menu icon-button"
        aria-label="Open navigation"
        onClick={() => setOpen(true)}
      >
        <Menu size={20} />
      </button>
      {open && (
        <button
          className="nav-scrim"
          aria-label="Close navigation"
          onClick={() => setOpen(false)}
        />
      )}
      <aside className={"sidebar " + (open ? "open" : "")}>
        <div className="sidebar-brand">
          <Brand />
          <button
            className="icon-button mobile-close"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
          >
            <X size={18} />
          </button>
        </div>
        <nav aria-label="Main navigation" onClick={() => setOpen(false)}>
          <NavLink to="/workspace">
            <FolderGit2 size={18} />
            Repositories
          </NavLink>
          <NavLink to="/activity">
            <Activity size={18} />
            Jobs & activity
          </NavLink>
          <NavLink to="/tools">
            <Terminal size={18} />
            CLI & MCP
          </NavLink>
          {user?.role === "admin" && (
            <NavLink to="/admin">
              <ShieldCheck size={18} />
              Administration
            </NavLink>
          )}
        </nav>
        <div className="sidebar-bottom">
          <nav aria-label="Account" onClick={() => setOpen(false)}>
            <NavLink to="/settings">
              <Settings size={18} />
              Settings
            </NavLink>
            <button onClick={() => void logout()}>
              <LogOut size={18} />
              Log out
            </button>
          </nav>
          <div className="profile">
            <div className="avatar">{user?.name.slice(0, 1).toUpperCase()}</div>
            <div>
              <strong>{user?.name}</strong>
              <span>
                {user?.role === "admin"
                  ? "Administrator"
                  : "Personal workspace"}
              </span>
            </div>
          </div>
          <Link to="/" className="sidebar-about">
            About GraphPilot <ArrowUpRight size={14} />
          </Link>
        </div>
      </aside>
      <div className="app-content">
        <header className="topbar">
          <nav className="crumbs" aria-label="Breadcrumb">
            <span>Workspace</span>
            <span className="crumb-divider" aria-hidden="true">
              /
            </span>
            {inRepository ? (
              <>
                <Link to="/workspace">Repositories</Link>
                <span className="crumb-divider" aria-hidden="true">
                  /
                </span>
                <RepositoryCrumb />
              </>
            ) : (
              <span className="crumb-current">{crumb}</span>
            )}
          </nav>
          <div className="topbar-actions">
            <button
              className="topbar-search"
              aria-label="Search and commands"
              onClick={() => setPalette(true)}
            >
              <Search size={14} />
              <span>Search and commands</span>
              <kbd>{shortcut}</kbd>
            </button>
            <Link className="button primary small-button" to="/connect">
              <Plus size={16} />
              <span className="topbar-link-text">Add repository</span>
            </Link>
          </div>
        </header>
        <main id="main">
          <Outlet />
        </main>
        <footer className="app-footer">
          <span>
            GraphPilot <span className="footer-sep">/</span> Powered by FalkorDB
          </span>
          <span>Follow the evidence.</span>
        </footer>
      </div>
      {palette && <CommandPalette close={closePalette} />}
    </div>
  );
}
