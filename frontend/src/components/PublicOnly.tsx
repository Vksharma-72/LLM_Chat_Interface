import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";

/** Wraps /login and /register: authenticated users are sent to /chat. */
export default function PublicOnly({ children }: { children: ReactNode }) {
  const accessToken = useAuthStore((state) => state.accessToken);
  if (accessToken) {
    return <Navigate to="/chat" replace />;
  }
  return <>{children}</>;
}
