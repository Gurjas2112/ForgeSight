"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "./AuthProvider";
import { authConfigured } from "@/lib/supabase";

/** Client-side route guard. Redirects to /login when auth is configured but no session.
 *  If Supabase env isn't configured (pure local/demo), it lets the page through. */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth();
  const router = useRouter();
  const mustAuth = authConfigured();

  useEffect(() => {
    if (mustAuth && !loading && !session) router.replace("/login");
  }, [mustAuth, loading, session, router]);

  if (mustAuth && (loading || !session)) {
    return <div className="max-w-7xl mx-auto px-5 py-10 text-sm text-[#8B98A5]">Checking your session…</div>;
  }
  return <>{children}</>;
}
