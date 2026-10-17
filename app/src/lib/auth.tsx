import { createContext, useContext, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, post, type User } from "./api";
type AuthSession = {
  user: User | null;
  auth_provider?: "local" | "firebase";
  email_verified?: boolean | null;
};
const AuthContext = createContext<{
  user: User | null;
  loading: boolean;
  error: Error | null;
  refresh: () => Promise<unknown>;
  logout: () => Promise<void>;
  provider: "local" | "firebase" | null;
  emailVerified: boolean | null;
}>({
  user: null,
  loading: true,
  error: null,
  refresh: async () => {},
  logout: async () => {},
  provider: null,
  emailVerified: null,
});
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const cache = useQueryClient();
  const session = useQuery({
    queryKey: ["session"],
    queryFn: async (): Promise<AuthSession> => {
      try {
        return await api<AuthSession>("/auth/session");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return { user: null };
        throw e;
      }
    },
    retry: false,
    staleTime: 30000,
  });
  const user = session.data?.user || null;
  useEffect(() => {
    const theme = user?.theme || localStorage.getItem("gp-theme") || "system";
    document.documentElement.dataset.theme =
      theme === "system"
        ? matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : theme;
  }, [user?.theme]);
  return (
    <AuthContext.Provider
      value={{
        user,
        provider: session.data?.auth_provider || null,
        emailVerified: session.data?.email_verified ?? null,
        loading: session.isPending,
        error: session.error,
        refresh: () => cache.invalidateQueries({ queryKey: ["session"] }),
        logout: async () => {
          await post("/auth/logout");
          cache.clear();
          location.assign("/login");
        },
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
export const useAuth = () => useContext(AuthContext);
