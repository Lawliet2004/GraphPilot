import {
  AlertCircle,
  ArrowRight,
  GitBranch,
  LoaderCircle,
  Network,
  Plus,
} from "lucide-react";
import { Link } from "react-router-dom";
export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link className="brand" to="/">
      <Network size={26} strokeWidth={1.6} />
      {!compact && (
        <span>
          GraphPilot<span className="brand-dot">.</span>
        </span>
      )}
    </Link>
  );
}
export function Loading({
  label = "Loading your workspace…",
}: {
  label?: string;
}) {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={22} />
      <span>{label}</span>
    </div>
  );
}
export function ErrorNotice({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div className="notice error" role="alert">
      <AlertCircle size={18} />
      <div>
        <strong>Something needs attention</strong>
        <p>
          {error instanceof Error
            ? error.message
            : "The request could not be completed."}
        </p>
        {retry && (
          <button className="text-button" onClick={retry}>
            Try again <ArrowRight size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Network size={32} strokeWidth={1.3} />
      </span>
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function ConnectLink() {
  return (
    <Link className="button primary" to="/connect">
      <Plus size={16} />
      Add repository
    </Link>
  );
}
export function Branch({ name }: { name: string }) {
  return (
    <span className="branch">
      <GitBranch size={13} />
      {name}
    </span>
  );
}
export function Status({ status }: { status: string }) {
  return (
    <span className={"status status-" + status}>
      <span />
      {status.replace("-", " ")}
    </span>
  );
}
export function Heading({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
}
