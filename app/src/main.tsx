import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@fontsource-variable/manrope";
import "@fontsource/ibm-plex-mono/400.css";
import "./styles.css";
import { AuthProvider } from "./lib/auth";
import { Protected, Shell } from "./components/Shell";
import { Landing } from "./pages/Landing";
import { Auth } from "./pages/Auth";
import { Dashboard } from "./pages/Dashboard";
import { Connect } from "./pages/Connect";
import { RepositoryPage } from "./pages/Repository";
import { Settings } from "./pages/Settings";
import { Admin } from "./pages/Admin";
import { Activity } from "./pages/Activity";
const cache = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: true },
    mutations: { retry: false },
  },
});
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={cache}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Auth />} />
            <Route path="/signup" element={<Auth signup />} />
            <Route path="/reset-password" element={<Auth reset />} />
            <Route element={<Protected />}>
              <Route element={<Shell />}>
                <Route path="/workspace" element={<Dashboard />} />
                <Route path="/connect" element={<Connect />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/activity" element={<Activity />} />
                <Route path="/admin" element={<Admin />} />
                <Route path="/repositories/:id" element={<RepositoryPage />} />
                {[
                  "overview",
                  "context",
                  "history",
                  "impact",
                  "diagnostics",
                ].map((view) => (
                  <Route
                    key={view}
                    path={"/repositories/:id/" + view}
                    element={<RepositoryPage view={view} />}
                  />
                ))}
              </Route>
            </Route>
            <Route
              path="*"
              element={
                <div className="empty">
                  <h1>This page isn’t here.</h1>
                  <p>Follow the link back to your workspace.</p>
                  <Link className="button primary" to="/workspace">
                    Open workspace
                  </Link>
                </div>
              }
            />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
