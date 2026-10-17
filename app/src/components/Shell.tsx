import {
  Activity,
  ArrowUpRight,
  FolderGit2,
  LogOut,
  Menu,
  PanelLeftClose,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";
import { NavLink, Outlet, Link, Navigate, useLocation } from "react-router-dom";
import { useState } from "react";
import { useAuth } from "../lib/auth";
import { Brand, ErrorNotice, Loading } from "./ui";
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
export function Shell() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
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
        <Menu />
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
        <div className="workspace-label">Your workspace</div>
        <nav aria-label="Main navigation" onClick={() => setOpen(false)}>
          <NavLink to="/workspace">
            <FolderGit2 size={18} />
            Repositories
          </NavLink>
          <NavLink to="/activity">
            <Activity size={18} />
            Activity
          </NavLink>
          {user?.role === "admin" && (
            <NavLink to="/admin">
              <ShieldCheck size={18} />
              Administration
            </NavLink>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-note">
            <span className="live-dot" />
            Evidence comes first.
            <p>
              Explore relationships.
              <br />
              Check the source.
            </p>
            <Link to="/" className="sidebar-about">
              About GraphPilot <ArrowUpRight size={14} />
            </Link>
          </div>
          <nav aria-label="Account">
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
            <PanelLeftClose size={15} />
          </div>
        </div>
      </aside>
      <div className="app-content">
        <header className="topbar">
          <span>
            Workspace <span className="crumb-divider">/</span> Code intelligence
          </span>
          <Link to="/connect">
            Connect a repository <ArrowUpRight size={14} />
          </Link>
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
    </div>
  );
}
