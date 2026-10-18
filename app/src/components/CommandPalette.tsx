import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  FileCode2,
  FolderGit2,
  LoaderCircle,
  MessageSquare,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Terminal,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, type Repo } from "../lib/api";
import { useAuth } from "../lib/auth";

type Action = {
  id: string;
  group: string;
  label: string;
  hint?: string;
  keywords: string;
  to: string;
  icon: React.ElementType;
};

export function CommandPalette({ close }: { close: () => void }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const results = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const repos = useQuery({
    queryKey: ["repositories"],
    queryFn: () => api<Repo[]>("/repositories"),
  });
  const actions = useMemo<Action[]>(() => {
    const list: Action[] = [
      {
        id: "nav-workspace",
        group: "Go to",
        label: "Repositories",
        hint: "Workspace",
        keywords: "workspace repositories dashboard home",
        to: "/workspace",
        icon: FolderGit2,
      },
      {
        id: "nav-connect",
        group: "Go to",
        label: "Add repository",
        keywords: "add connect repository github archive upload new source",
        to: "/connect",
        icon: Plus,
      },
      {
        id: "nav-tools",
        group: "Go to",
        label: "CLI & MCP",
        keywords:
          "cli mcp developer tools command terminal runner codespace git ask",
        to: "/tools",
        icon: Terminal,
      },
      {
        id: "nav-activity",
        group: "Go to",
        label: "Jobs & activity",
        keywords: "activity events audit history",
        to: "/activity",
        icon: Activity,
      },
      {
        id: "nav-settings",
        group: "Go to",
        label: "Settings",
        keywords: "settings profile theme appearance cli access credentials",
        to: "/settings",
        icon: Settings,
      },
    ];
    if (user?.role === "admin") {
      list.push({
        id: "nav-admin",
        group: "Go to",
        label: "Administration",
        keywords: "administration users members access health jobs",
        to: "/admin",
        icon: ShieldCheck,
      });
    }
    for (const r of repos.data ?? []) {
      for (const [tab, suffix, icon] of [
        ["Ask", "", MessageSquare],
        ["Graph", "/code", FileCode2],
        ["History", "/activity", Activity],
      ] as const) {
        list.push({
          id: `repo-${r.id}-${tab.toLowerCase()}`,
          group: "Repositories",
          label: r.name,
          hint: `${tab} · ${r.branch}`,
          keywords: `${r.name} ${tab} ${r.branch} repository`,
          to: "/repositories/" + r.id + suffix,
          icon,
        });
      }
    }
    return list;
  }, [repos.data, user?.role]);
  const shown = useMemo(() => {
    const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return actions;
    return actions.filter((a) =>
      terms.every((t) =>
        (a.label + " " + a.keywords).toLowerCase().includes(t),
      ),
    );
  }, [actions, query]);
  const groups = useMemo(() => {
    const map = new Map<string, { action: Action; index: number }[]>();
    shown.forEach((action, index) => {
      const bucket = map.get(action.group) ?? [];
      bucket.push({ action, index });
      map.set(action.group, bucket);
    });
    return [...map.entries()];
  }, [shown]);
  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    const previousFocus = document.activeElement;
    if (!el.open) el.showModal();
    input.current?.focus();
    const cancel = (e: Event) => {
      e.preventDefault();
      close();
    };
    const click = (e: MouseEvent) => {
      if (e.target === el) close();
    };
    el.addEventListener("cancel", cancel);
    el.addEventListener("click", click);
    return () => {
      el.removeEventListener("cancel", cancel);
      el.removeEventListener("click", click);
      if (el.open) el.close();
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
        previousFocus.focus();
      }
    };
  }, [close]);
  const mounted = useRef(location.pathname);
  useEffect(() => {
    if (location.pathname !== mounted.current) close();
    mounted.current = location.pathname;
  }, [location.pathname, close]);
  useEffect(() => setActive(0), [query]);
  useEffect(() => {
    results.current
      ?.querySelector('[aria-selected="true"]')
      ?.scrollIntoView({ block: "nearest" });
  }, [active]);
  function open(action: Action) {
    navigate(action.to);
    close();
  }
  function keys(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!shown.length) return;
      setActive(
        (a) =>
          (a + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length,
      );
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      setActive(e.key === "Home" ? 0 : Math.max(0, shown.length - 1));
    } else if (e.key === "Enter" && shown[active]) {
      e.preventDefault();
      open(shown[active]);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="command-palette"
      aria-label="Command palette"
    >
      <div className="palette-panel">
        <div className="palette-input">
          <Search size={16} />
          <input
            ref={input}
            role="combobox"
            aria-expanded="true"
            aria-controls="palette-results"
            aria-activedescendant={
              shown[active] ? "palette-option-" + active : undefined
            }
            aria-label="Search repositories and commands"
            placeholder="Search repositories and commands…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={keys}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <div
          className="palette-results"
          id="palette-results"
          role="listbox"
          ref={results}
          aria-label="Matching repositories and commands"
        >
          {repos.isPending && (
            <div className="palette-state">
              <LoaderCircle className="spin" size={17} />
              Loading repositories…
            </div>
          )}
          {repos.error && (
            <div className="palette-state">
              <span>{repos.error.message}</span>
              <button
                className="text-button"
                onClick={() => void repos.refetch()}
              >
                Try again
              </button>
            </div>
          )}
          {!repos.isPending && !shown.length && !repos.error && (
            <div className="palette-state">
              {query
                ? `No repositories or commands match “${query}”.`
                : "Nothing to show yet."}
            </div>
          )}
          {groups.map(([name, items]) => (
            <div
              className="palette-group"
              key={name}
              role="group"
              aria-label={name}
            >
              <div className="palette-heading">{name}</div>
              {items.map(({ action, index }) => {
                const Icon = action.icon;
                return (
                  <div
                    key={action.id}
                    id={"palette-option-" + index}
                    role="option"
                    aria-selected={index === active}
                    className="palette-item"
                    onMouseEnter={() => setActive(index)}
                    onClick={() => open(action)}
                  >
                    <Icon size={15} />
                    <span className="palette-label">{action.label}</span>
                    {action.hint && (
                      <span className="palette-hint">{action.hint}</span>
                    )}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
        <div className="palette-footer">
          <span>
            <kbd>↑</kbd>
            <kbd>↓</kbd> Navigate
          </span>
          <span>
            <kbd>↵</kbd> Open
          </span>
          <span>
            <kbd>esc</kbd> Close
          </span>
        </div>
      </div>
    </dialog>
  );
}
